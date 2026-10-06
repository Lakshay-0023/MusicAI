"""What is being sung, and exactly when?

Runs once per track and writes lyrics.json next to the stems: every word with
the moment it starts and ends, grouped into lines the way a singer phrases.

    Vocals stem -> Whisper -> words + times -> (Hindi: Devanagari -> Roman) -> lines

It listens to the separated voice, not the song. Whisper was trained on
speech, and drums and guitars confuse it badly; alone, the voice is as close to
speech as singing gets. Works on any audio with singing in it - a released
song or a phone recording of your band - and nothing leaves the machine.
"""

import warnings

import numpy as np

from ...config import settings
from ...storage import storage
from . import roman
from .source import load_mono

LYRICS_FILE = "lyrics.json"
WHISPER_RATE = 16000   # the only rate Whisper accepts

# A pause longer than this between words starts a new line.
LINE_GAP_SECONDS = 0.6
# Lines longer than this are split at a breath, so each reads at a glance.
MAX_WORDS_PER_LINE = 8

# Bollywood songs are often detected as Urdu: the same spoken language, written
# in Arabic script. Devanagari is what can be turned into Roman letters, so both
# are transcribed as Hindi.
HINDUSTANI = ("hi", "ur")

# Triton is a GPU compiler Whisper uses to speed up word timing. It does not
# exist on Windows, so Whisper falls back to its own slower code and says so on
# every chunk. Harmless, and noisy enough to hide a real error.
warnings.filterwarnings("ignore", message="Failed to launch Triton kernels")


def detect(track_id: str, language: str | None = None) -> dict:
    """Transcribe the vocals, word by word, and save the result.

    `language` is a Whisper code ("hi", "en", ...) or "auto"; by default the
    one in config. Told the language, Whisper is far more accurate on singing
    than when it has to guess.
    """
    audio = load_mono(track_id, ("Vocals",), WHISPER_RATE).astype(np.float32)
    language, segments = _transcribe(audio, language or settings.lyrics_language)

    lines = _lines(segments, romanise=language == "hi", audio=audio)
    _hold_line_ends(lines, _loudness(audio))

    data = {
        "language": language,
        "lines": lines,
        "method": f"whisper-{settings.lyrics_model}",
        "heldEnds": True,
    }
    storage.write_json(track_id, LYRICS_FILE, data)
    return data


def load(track_id: str) -> dict | None:
    """Lyrics if they have been worked out, otherwise None.

    Lyrics written before line ends were measured from the voice are brought
    up to date here, once: it needs only the vocal's loudness - a couple of
    seconds - not another minute and a half of Whisper.
    """
    if not storage.exists(track_id, LYRICS_FILE):
        return None
    data = storage.read_json(track_id, LYRICS_FILE)
    if not data.get("heldEnds"):
        audio = load_mono(track_id, ("Vocals",), WHISPER_RATE).astype(np.float32)
        _hold_line_ends(data["lines"], _loudness(audio))
        data["heldEnds"] = True
        storage.write_json(track_id, LYRICS_FILE, data)
    return data


# ---- listening -----------------------------------------------------------------

def _transcribe(audio, language: str):
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = _load_model(device)

    try:
        if language == "auto":
            language = _language(model, audio)
        if language in HINDUSTANI:
            language = "hi"

        result = model.transcribe(
            audio,
            language=language,
            word_timestamps=True,                # a time for every word, not just every line
            condition_on_previous_text=False,    # stops one misheard line repeating itself
            hallucination_silence_threshold=2.0, # skip "words" invented over long silences
            fp16=device == "cuda",
            verbose=None,                        # no console output from inside a server
        )
    finally:
        # Same rule as every model here: never sit on memory Demucs needs.
        del model
        if device == "cuda":
            torch.cuda.empty_cache()

    return language, result["segments"]


def _load_model(device: str):
    """Whisper, loaded without ever building it in RAM.

    whisper.load_model reads the 1.6GB file into RAM, then builds a 32-bit
    model beside it - nearly 5GB at once on a machine with about 6GB to spare,
    and it crashes when the browser and editor are open too. Instead:

    1. The file is memory-mapped: its weights stay on disk until touched.
    2. The model is built on PyTorch's "meta" device - the outline of every
       layer, shapes and all, with no memory behind any of it.
    3. The file's weights are attached to that outline as they are
       (assign=True), still 16-bit, still on disk.
    4. Moving to the GPU then reads each weight from disk straight into GPU
       memory: 1.6GB there, almost nothing in RAM.

    The weights stay 16-bit, half of 32-bit's 3.2GB. Whisper converts weights
    to the input's precision as it uses them, so this costs no accuracy worth
    hearing. Its normalisation layers insist on 32-bit, so those are widened.
    """
    import numpy as np
    import torch
    import whisper
    from whisper.model import AudioEncoder, ModelDimensions, TextDecoder, Whisper

    name = settings.lyrics_model
    path = whisper._download(whisper._MODELS[name], str(settings.models_dir / "whisper"), False)
    checkpoint = torch.load(path, map_location="cpu", weights_only=True, mmap=True)
    dims = ModelDimensions(**checkpoint["dims"])

    # Whisper's own constructor also builds a small lookup table with an
    # operation the meta device cannot do, so the two halves are built here
    # and the table is added for real below.
    model = Whisper.__new__(Whisper)
    torch.nn.Module.__init__(model)
    model.dims = dims
    with torch.device("meta"):
        model.encoder = AudioEncoder(dims.n_mels, dims.n_audio_ctx, dims.n_audio_state,
                                     dims.n_audio_head, dims.n_audio_layer)
        model.decoder = TextDecoder(dims.n_vocab, dims.n_text_ctx, dims.n_text_state,
                                    dims.n_text_head, dims.n_text_layer)
    model.load_state_dict(checkpoint["model_state_dict"], assign=True)

    # Two pieces are not in the file, so they are made for real: the mask that
    # stops the decoder peeking at words it has not written yet, and which
    # attention heads track timing - what makes per-word times possible.
    mask = torch.empty(dims.n_text_ctx, dims.n_text_ctx).fill_(-np.inf).triu_(1)
    model.decoder.register_buffer("mask", mask, persistent=False)
    model.set_alignment_heads(whisper._ALIGNMENT_HEADS[name])

    for module in model.modules():
        if isinstance(module, torch.nn.LayerNorm):
            module.float()

    model = model.to(device)
    del checkpoint
    return model


def _language(model, audio) -> str:
    """Whisper's guess at the language, from the busiest 30 seconds of vocals.

    Only used when the language is set to "auto", because on singing the guess
    is poor: for "Ae Dil Hai Mushkil" it said English 35%, Turkish 14%,
    Russian 10%, with Hindi not even in its top five - and once it has decided
    "English", it writes English sentences for Hindi singing.
    """
    import whisper

    span = 30 * WHISPER_RATE
    window = audio
    if len(audio) > span:
        hop = 5 * WHISPER_RATE
        starts = range(0, len(audio) - span + 1, hop)
        loudness = [float(np.mean(audio[s:s + span] ** 2)) for s in starts]
        best = starts[int(np.argmax(loudness))]
        window = audio[best:best + span]

    mel = whisper.log_mel_spectrogram(whisper.pad_or_trim(window), n_mels=model.dims.n_mels)
    mel = mel.to(model.device)
    if model.device.type == "cuda":
        mel = mel.half()
    _, probabilities = model.detect_language(mel)
    return max(probabilities, key=probabilities.get)


# ---- arranging -----------------------------------------------------------------

def _lines(segments, romanise: bool, audio) -> list[dict]:
    """Words grouped into lines, the way a singer phrases them.

    1. A line ends where Whisper ended a segment, or at a real pause.
    2. A line still longer than MAX_WORDS_PER_LINE is split where the singer
       breathes.

    Step 2 cannot use the gaps between Whisper's words: on sustained singing it
    reports none at all - each word runs right up to the next, swallowing the
    breath in between. The breath is still in the audio, though, as a dip in
    the vocal's loudness, so that is what is measured.
    """
    loudness = _loudness(audio)
    lines: list[dict] = []

    for segment in segments:
        current: list[dict] = []
        for word in segment.get("words", []):
            text = word["word"].strip()
            if romanise:
                text = roman.romanise(text).strip()
            if not text:
                continue

            entry = {"text": text, "start": round(word["start"], 3), "end": round(word["end"], 3)}
            if current and entry["start"] - current[-1]["end"] > LINE_GAP_SECONDS:
                lines.extend(_line(part) for part in _split_long(current, loudness))
                current = []
            current.append(entry)

        if current:
            lines.extend(_line(part) for part in _split_long(current, loudness))
    return lines


# Loudness is measured every 20ms.
LOUDNESS_HOP = WHISPER_RATE // 50


def _loudness(audio):
    """The vocal's loudness over time, in decibels."""
    import librosa

    rms = librosa.feature.rms(y=audio, frame_length=1024, hop_length=LOUDNESS_HOP)[0]
    return 20 * np.log10(rms + 1e-9)


def _split_long(words: list[dict], loudness) -> list[list[dict]]:
    """Split a too-long line at its deepest breath, again until all fit.

    Never leaves a single word on its own: each side keeps at least two.
    """
    if len(words) <= MAX_WORDS_PER_LINE:
        return [words]
    _, cut = max((_breath(words[i], words[i + 1], loudness), i) for i in range(1, len(words) - 2))
    return _split_long(words[:cut + 1], loudness) + _split_long(words[cut + 1:], loudness)


def _breath(before: dict, after: dict, loudness) -> float:
    """How deep the loudness dips between two words, in dB below their level.

    Whisper may have hung the breath on either word, so the search runs from
    the last 40% of the first word to the first 40% of the second.
    """
    frame = lambda t: int(t * WHISPER_RATE / LOUDNESS_HOP)
    lo = before["start"] + 0.6 * (before["end"] - before["start"])
    hi = after["start"] + 0.4 * (after["end"] - after["start"])
    around = loudness[frame(before["start"]):frame(after["end"]) + 1]
    inside = loudness[frame(lo):frame(hi) + 1]
    if not len(around) or not len(inside):
        return 0.0
    return float(np.median(around) - inside.min())


# The voice counts as stopped once it is this far below the line's own level.
HELD_DROP_DB = 15
# ...for at least this long, so a breath mid-note does not end it.
HELD_QUIET_SECONDS = 0.3
# A held note is never extended further than this.
HELD_MAX_SECONDS = 8.0


def _hold_line_ends(lines: list[dict], loudness) -> None:
    """Stretch each line's last word to where the voice actually stops.

    Whisper ends a word where its attention moves on, which on a held note is
    far too early: it put the end of a held "Besabriyaa...n" at 36.1s, while
    the voice carried on to 38.1s. Chords played under that held note then
    looked as if they fell in a pause and were pinned to the next line.

    So, from Whisper's end, follow the vocal's loudness until it has dropped
    HELD_DROP_DB below the line's own level and stays there - never past the
    next line's start. Measured on that song: 36.1 -> 38.1s, and a final
    fade-out 52.5 -> 57.0s.
    """
    frames_per_second = WHISPER_RATE / LOUDNESS_HOP
    frame = lambda t: int(t * frames_per_second)
    quiet = int(HELD_QUIET_SECONDS * frames_per_second)

    for i, line in enumerate(lines):
        last = line["words"][-1]
        limit = min(lines[i + 1]["start"] - 0.05 if i + 1 < len(lines) else float("inf"),
                    last["end"] + HELD_MAX_SECONDS, len(loudness) / frames_per_second)

        sung = loudness[frame(line["start"]):frame(line["end"]) + 1]
        if not len(sung):
            continue
        floor = float(np.median(sung)) - HELD_DROP_DB

        f = frame(last["end"])
        while f / frames_per_second < limit and loudness[f:f + quiet].max(initial=-999) >= floor:
            f += 1
        end = round(max(last["end"], min(f / frames_per_second, limit)), 3)
        last["end"] = end
        line["end"] = end


def _line(words: list[dict]) -> dict:
    words[0]["text"] = words[0]["text"][:1].upper() + words[0]["text"][1:]
    return {"start": words[0]["start"], "end": words[-1]["end"], "words": words}
