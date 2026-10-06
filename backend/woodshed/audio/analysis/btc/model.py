"""The BTC network, as published, with three changes:

- `np.float` (removed from numpy) is now `float`.
- The training-only loss path and test harness are gone.
- The settings from its run_config.yaml live here as plain values.

Class and attribute names are untouched on purpose: the downloaded weights
are stored under those names, and loading fails if any of them differ.

The idea, briefly: the song is cut into 10-second windows of 108 frames. Each
layer lets every frame look at every other frame in its window - once looking
forwards in time, once backwards - so the guess for a frame is informed by
what came before and after it. That context is what stops the chord flickering.
"""

import math

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

# The large-vocabulary model: 12 roots x 14 qualities, plus X (unknown) and
# N (no chord). Index = root * 14 + quality.
ROOTS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
QUALITIES = ["min", "maj", "dim", "aug", "min6", "maj6", "min7", "minmaj7",
             "maj7", "7", "dim7", "hdim7", "sus2", "sus4"]

SAMPLE_RATE = 22050
WINDOW_SECONDS = 10.0
FRAMES_PER_WINDOW = 108

CONFIG = {
    "sample_rate": SAMPLE_RATE,
    "n_bins": 144,            # 6 octaves...
    "bins_per_octave": 24,    # ...at two bins per semitone
    "hop_length": 2048,       # one frame every ~93ms
    "feature_size": 144,
    "timestep": FRAMES_PER_WINDOW,
    "num_chords": 170,
    "input_dropout": 0.2,
    "layer_dropout": 0.2,
    "attention_dropout": 0.2,
    "relu_dropout": 0.2,
    "num_layers": 8,
    "num_heads": 4,
    "hidden_size": 128,
    "total_key_depth": 128,
    "total_value_depth": 128,
    "filter_size": 128,
}


def label_of(index: int) -> str:
    """Model output index -> chord label in the standard (Harte) notation."""
    if index == 169:
        return "N"
    if index == 168:
        return "X"
    root, quality = ROOTS[index // 14], QUALITIES[index % 14]
    return root if quality == "maj" else f"{root}:{quality}"


# ---- building blocks (from utils/transformer_modules.py) --------------------

def _gen_bias_mask(max_length):
    """-inf above the diagonal: stops a frame attending to later frames."""
    np_mask = np.triu(np.full([max_length, max_length], -np.inf), 1)
    torch_mask = torch.from_numpy(np_mask).type(torch.FloatTensor)
    return torch_mask.unsqueeze(0).unsqueeze(1)


def _gen_timing_signal(length, channels, min_timescale=1.0, max_timescale=1.0e4):
    """Sine waves that tell the network where in the window each frame is."""
    position = np.arange(length)
    num_timescales = channels // 2
    log_timescale_increment = (math.log(float(max_timescale) / float(min_timescale))
                               / (float(num_timescales) - 1))
    inv_timescales = min_timescale * np.exp(
        np.arange(num_timescales).astype(float) * -log_timescale_increment)
    scaled_time = np.expand_dims(position, 1) * np.expand_dims(inv_timescales, 0)

    signal = np.concatenate([np.sin(scaled_time), np.cos(scaled_time)], axis=1)
    signal = np.pad(signal, [[0, 0], [0, channels % 2]], "constant", constant_values=[0.0, 0.0])
    signal = signal.reshape([1, length, channels])
    return torch.from_numpy(signal).type(torch.FloatTensor)


class LayerNorm(nn.Module):
    def __init__(self, features, eps=1e-6):
        super().__init__()
        self.gamma = nn.Parameter(torch.ones(features))
        self.beta = nn.Parameter(torch.zeros(features))
        self.eps = eps

    def forward(self, x):
        mean = x.mean(-1, keepdim=True)
        std = x.std(-1, keepdim=True)
        return self.gamma * (x - mean) / (std + self.eps) + self.beta


class SoftmaxOutputLayer(nn.Module):
    """Hidden state -> one score per chord. The LSTM is unused at inference
    but is part of the saved weights, so it has to exist to load them."""

    def __init__(self, hidden_size, output_size):
        super().__init__()
        self.output_size = output_size
        self.output_projection = nn.Linear(hidden_size, output_size)
        self.lstm = nn.LSTM(input_size=hidden_size, hidden_size=int(hidden_size / 2),
                            batch_first=True, bidirectional=True)
        self.hidden_size = hidden_size

    def forward(self, hidden):
        return self.output_projection(hidden)


class MultiHeadAttention(nn.Module):
    """Multi-head attention, as in "Attention Is All You Need"."""

    def __init__(self, input_depth, total_key_depth, total_value_depth, output_depth,
                 num_heads, bias_mask=None, dropout=0.0, attention_map=False):
        super().__init__()
        if total_key_depth % num_heads != 0:
            raise ValueError("Key depth must be divisible by the number of heads.")
        if total_value_depth % num_heads != 0:
            raise ValueError("Value depth must be divisible by the number of heads.")

        self.attention_map = attention_map
        self.num_heads = num_heads
        self.query_scale = (total_key_depth // num_heads) ** -0.5
        self.bias_mask = bias_mask

        self.query_linear = nn.Linear(input_depth, total_key_depth, bias=False)
        self.key_linear = nn.Linear(input_depth, total_key_depth, bias=False)
        self.value_linear = nn.Linear(input_depth, total_value_depth, bias=False)
        self.output_linear = nn.Linear(total_value_depth, output_depth, bias=False)
        self.dropout = nn.Dropout(dropout)

    def _split_heads(self, x):
        shape = x.shape
        return x.view(shape[0], shape[1], self.num_heads,
                      shape[2] // self.num_heads).permute(0, 2, 1, 3)

    def _merge_heads(self, x):
        shape = x.shape
        return x.permute(0, 2, 1, 3).contiguous().view(shape[0], shape[2],
                                                      shape[3] * self.num_heads)

    def forward(self, queries, keys, values):
        queries = self._split_heads(self.query_linear(queries))
        keys = self._split_heads(self.key_linear(keys))
        values = self._split_heads(self.value_linear(values))

        queries *= self.query_scale
        logits = torch.matmul(queries, keys.permute(0, 1, 3, 2))
        if self.bias_mask is not None:
            logits += self.bias_mask[:, :, :logits.shape[-2], :logits.shape[-1]].type_as(logits.data)

        weights = self.dropout(F.softmax(logits, dim=-1))
        outputs = self.output_linear(self._merge_heads(torch.matmul(weights, values)))

        if self.attention_map is True:
            return outputs, weights
        return outputs


class Conv(nn.Module):
    def __init__(self, input_size, output_size, kernel_size, pad_type):
        super().__init__()
        padding = ((kernel_size - 1, 0) if pad_type == "left"
                   else (kernel_size // 2, (kernel_size - 1) // 2))
        self.pad = nn.ConstantPad1d(padding, 0)
        self.conv = nn.Conv1d(input_size, output_size, kernel_size=kernel_size, padding=0)

    def forward(self, inputs):
        inputs = self.pad(inputs.permute(0, 2, 1))
        return self.conv(inputs).permute(0, 2, 1)


class PositionwiseFeedForward(nn.Module):
    def __init__(self, input_depth, filter_size, output_depth, layer_config="ll",
                 padding="left", dropout=0.0):
        super().__init__()
        layers = []
        sizes = ([(input_depth, filter_size)]
                 + [(filter_size, filter_size)] * (len(layer_config) - 2)
                 + [(filter_size, output_depth)])
        for lc, s in zip(list(layer_config), sizes):
            if lc == "l":
                layers.append(nn.Linear(*s))
            elif lc == "c":
                layers.append(Conv(*s, kernel_size=3, pad_type=padding))
            else:
                raise ValueError(f"Unknown layer type {lc}")
        self.layers = nn.ModuleList(layers)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(dropout)

    def forward(self, inputs):
        x = inputs
        for layer in self.layers:
            x = self.dropout(self.relu(layer(x)))
        return x


# ---- the network (from btc_model.py) -----------------------------------------

class self_attention_block(nn.Module):
    def __init__(self, hidden_size, total_key_depth, total_value_depth, filter_size, num_heads,
                 bias_mask=None, layer_dropout=0.0, attention_dropout=0.0, relu_dropout=0.0,
                 attention_map=False):
        super().__init__()
        self.attention_map = attention_map
        self.multi_head_attention = MultiHeadAttention(hidden_size, total_key_depth,
                                                       total_value_depth, hidden_size, num_heads,
                                                       bias_mask, attention_dropout, attention_map)
        self.positionwise_convolution = PositionwiseFeedForward(hidden_size, filter_size, hidden_size,
                                                                layer_config="cc", padding="both",
                                                                dropout=relu_dropout)
        self.dropout = nn.Dropout(layer_dropout)
        self.layer_norm_mha = LayerNorm(hidden_size)
        self.layer_norm_ffn = LayerNorm(hidden_size)

    def forward(self, inputs):
        x = inputs
        x_norm = self.layer_norm_mha(x)
        if self.attention_map is True:
            y, weights = self.multi_head_attention(x_norm, x_norm, x_norm)
        else:
            y = self.multi_head_attention(x_norm, x_norm, x_norm)
        x = self.dropout(x + y)

        y = self.positionwise_convolution(self.layer_norm_ffn(x))
        y = self.dropout(x + y)

        if self.attention_map is True:
            return y, weights
        return y


class bi_directional_self_attention(nn.Module):
    """One layer: attend forwards, attend backwards, combine the two."""

    def __init__(self, hidden_size, total_key_depth, total_value_depth, filter_size, num_heads,
                 max_length, layer_dropout=0.0, attention_dropout=0.0, relu_dropout=0.0):
        super().__init__()
        params = (hidden_size, total_key_depth or hidden_size, total_value_depth or hidden_size,
                  filter_size, num_heads, _gen_bias_mask(max_length),
                  layer_dropout, attention_dropout, relu_dropout, True)
        self.attn_block = self_attention_block(*params)

        params = (hidden_size, total_key_depth or hidden_size, total_value_depth or hidden_size,
                  filter_size, num_heads, torch.transpose(_gen_bias_mask(max_length), dim0=2, dim1=3),
                  layer_dropout, attention_dropout, relu_dropout, True)
        self.backward_attn_block = self_attention_block(*params)

        self.linear = nn.Linear(hidden_size * 2, hidden_size)

    def forward(self, inputs):
        x, weights_list = inputs
        encoder_outputs, weights = self.attn_block(x)
        reverse_outputs, reverse_weights = self.backward_attn_block(x)
        y = self.linear(torch.cat((encoder_outputs, reverse_outputs), dim=2))
        return y, weights_list + [weights, reverse_weights]


class bi_directional_self_attention_layers(nn.Module):
    def __init__(self, embedding_size, hidden_size, num_layers, num_heads, total_key_depth,
                 total_value_depth, filter_size, max_length=100, input_dropout=0.0,
                 layer_dropout=0.0, attention_dropout=0.0, relu_dropout=0.0):
        super().__init__()
        self.timing_signal = _gen_timing_signal(max_length, hidden_size)
        params = (hidden_size, total_key_depth or hidden_size, total_value_depth or hidden_size,
                  filter_size, num_heads, max_length, layer_dropout, attention_dropout, relu_dropout)
        self.embedding_proj = nn.Linear(embedding_size, hidden_size, bias=False)
        self.self_attn_layers = nn.Sequential(
            *[bi_directional_self_attention(*params) for _ in range(num_layers)])
        self.layer_norm = LayerNorm(hidden_size)
        self.input_dropout = nn.Dropout(input_dropout)

    def forward(self, inputs):
        x = self.embedding_proj(self.input_dropout(inputs))
        x += self.timing_signal[:, :inputs.shape[1], :].type_as(inputs.data)
        y, weights_list = self.self_attn_layers((x, []))
        return self.layer_norm(y), weights_list


class BTC_model(nn.Module):
    def __init__(self, config=CONFIG):
        super().__init__()
        self.timestep = config["timestep"]
        self.self_attn_layers = bi_directional_self_attention_layers(
            config["feature_size"], config["hidden_size"], config["num_layers"],
            config["num_heads"], config["total_key_depth"], config["total_value_depth"],
            config["filter_size"], config["timestep"], config["input_dropout"],
            config["layer_dropout"], config["attention_dropout"], config["relu_dropout"])
        self.output_layer = SoftmaxOutputLayer(hidden_size=config["hidden_size"],
                                               output_size=config["num_chords"])

    def forward(self, x):
        """[batch, 108 frames, 144 bins] -> [batch, 108, 170] chord scores."""
        hidden, _ = self.self_attn_layers(x)
        return self.output_layer(hidden)
