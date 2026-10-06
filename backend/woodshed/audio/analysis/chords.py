"""Which chord is playing on every beat?

Runs once per track and writes chords.json next to the stems, like beats.

    harmony stems -> CQT spectrogram -> BTC -> chord probabilities every ~93ms
                                                   |
    beats.json ------------------------------------+  averaged within each beat
                                                   v
              best chord path, where changing costs -> repeats merged -> chords.json

One decision per beat, not per frame: frame by frame the guess flickers
(Em Em G Em Em) on a passing note, and chords change on beats anyway. Then a
cost on changing chord, so a one-beat blip is not worth a change but a real
one is - at three strengths, saved side by side, for the player to choose.
"""

import bisect
import urllib.request

import librosa
import numpy as np

from ...config import settings
from ...storage import storage
from . import beats as beat_analysis
from .btc import CONFIG, FRAMES_PER_WINDOW, WINDOW_SECONDS, label_of
from .source import load_mono

CHORDS_FILE = "chords.json"

# How much a chord change costs, per level of detail (see _decode). Chosen by
# measuring two songs:
#
#                       Ae Dil Hai Mushkil   Besabriyaan
#   0  "all"                  156 changes      101       every beat for itself
#   3  "normal"               103               92       blips gone
#   6  "minimal"               89               73       just the backbone
#   12 (too far)               52               23       real changes vanish
CHANGE_PENALTY = {"all": 0.0, "normal": 3.0, "minimal": 6.0}

# Harte notation ("E:min7") -> the way a chord sheet writes it ("Em7").
SUFFIXES = {
    "maj": "", "min": "m", "dim": "dim", "aug": "aug", "min6": "m6", "maj6": "6",
    "min7": "m7", "minmaj7": "m(maj7)", "maj7": "maj7", "7": "7", "dim7": "dim7",
    "hdim7": "m7b5", "sus2": "sus2", "sus4": "sus4",
}


def detect(track_id: str, stems=None) -> dict:
    """Find the chord on every beat, merge repeats, and save the result."""
    stems = tuple(stems or settings.chord_stems)
    grid = beat_analysis.load(track_id) or beat_analysis.detect(track_id)

    rate = CONFIG["sample_rate"]
    audio = load_mono(track_id, stems, rate)
    duration = len(audio) / rate

    times, probabilities = _frame_probabilities(audio)
    edges, likelihood = _per_beat(times, probabilities, grid["beats"], duration)

    # The same evidence decoded at each level of detail - cheap, so all three
    # are saved and the player can switch between them instantly.
    levels = {}
    for level, penalty in CHANGE_PENALTY.items():
        path = _decode(likelihood, penalty)
        levels[level] = _merge([(edges[i], edges[i + 1], label_of(k)) for i, k in enumerate(path)])

    data = {"chords": levels["normal"], "levels": levels, "stems": list(stems), "method": "btc"}
    storage.write_json(track_id, CHORDS_FILE, data)
    return data


def load(track_id: str) -> dict | None:
    """Chord data if it has been worked out, otherwise None.

    Files from before the detail levels existed count as not worked out, so
    those songs are re-analysed once - seconds, not minutes.
    """
    if not storage.exists(track_id, CHORDS_FILE):
        return None
    data = storage.read_json(track_id, CHORDS_FILE)
    return data if "levels" in data else None


# ---- listening -----------------------------------------------------------------

def _features(audio):
    """What the model sees: a log-magnitude constant-Q spectrogram.

    Constant-Q means the frequency bins are spaced like piano keys - here two
    per semitone over six octaves - so a note is always the same number of bins
    above its octave, whichever octave it is in. The log is there because ears,
    and models trained on what ears care about, judge loudness by ratios.

    Computed in 10-second windows, exactly as BTC was trained: each window gives
    108 frames, and the model reads one window at a time. The song is padded
    with silence to a whole number of windows so every window is full.
    """
    rate, hop = CONFIG["sample_rate"], CONFIG["hop_length"]
    window = int(rate * WINDOW_SECONDS)
    audio = np.pad(audio, (0, (-len(audio)) % window))

    parts, times = [], []
    for start in range(0, len(audio), window):
        cqt = librosa.cqt(audio[start:start + window], sr=rate, hop_length=hop,
                          n_bins=CONFIG["n_bins"], bins_per_octave=CONFIG["bins_per_octave"])
        parts.append(cqt)
        times.append(start / rate + np.arange(cqt.shape[1]) * hop / rate)

    features = np.log(np.abs(np.concatenate(parts, axis=1)) + 1e-6).T
    return features, np.concatenate(times)


def _frame_probabilities(audio):
    """For every ~93ms frame, how likely each of the 170 chords is."""
    import torch

    from .btc import BTC_model

    features, times = _features(audio)

    # weights_only=False: the file also holds the mean and spread of the
    # training data as plain numbers, which the safe loader refuses. It comes
    # from the paper's own repository, which is what makes that acceptable.
    checkpoint = torch.load(_weights_path(), map_location="cpu", weights_only=False)

    # Scale the input the way the training data was scaled, or every value
    # the model sees is off by a constant and its answers are nonsense.
    features = (features - np.asarray(checkpoint["mean"])) / np.asarray(checkpoint["std"])

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = BTC_model().to(device)
    model.load_state_dict(checkpoint["model"])
    model.eval()  # switches dropout off: training-only randomness

    try:
        windows = torch.tensor(features, dtype=torch.float32, device=device)
        windows = windows.view(-1, FRAMES_PER_WINDOW, CONFIG["feature_size"])
        with torch.no_grad():
            scores = model(windows)
        probabilities = torch.softmax(scores, dim=-1).reshape(-1, CONFIG["num_chords"])
        probabilities = probabilities.cpu().numpy()
    finally:
        # Same reason as the beat model: never sit on memory Demucs needs.
        del model
        if device == "cuda":
            torch.cuda.empty_cache()

    return times, probabilities


def _weights_path():
    """The trained weights, downloaded the first time they are needed (12MB)."""
    path = settings.models_dir / settings.chord_model_url.rsplit("/", 1)[-1]
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(".part")
        # Downloaded under a temporary name and renamed at the end, so an
        # interrupted download is never mistaken for a finished one.
        urllib.request.urlretrieve(settings.chord_model_url, partial)
        partial.replace(path)
    return path


# ---- deciding ------------------------------------------------------------------

def _per_beat(times, probabilities, beat_times, duration):
    """How likely each chord is on each beat: the frames inside it, averaged.

    Averaging probabilities rather than voting frame by frame means a beat that
    is 60% sure of Em throughout beats one stray frame that is 90% sure of G.
    Returns the beat boundaries and a (beats x 170) table of probabilities.
    """
    edges = [0.0] + [t for t in beat_times if 0.0 < t < duration] + [duration]

    rows = []
    for start, end in zip(edges[:-1], edges[1:]):
        lo = bisect.bisect_left(times, start)
        hi = max(bisect.bisect_left(times, end), lo + 1)  # at least one frame
        rows.append(probabilities[lo:hi].mean(axis=0))
    return edges, np.array(rows)


def _decode(likelihood, penalty: float) -> list[int]:
    """The best chord for every beat, when changing chord has a cost.

    With no cost, each beat simply takes its likeliest chord - and a passing
    note becomes a one-beat chord. With a cost, a change has to earn its
    place: the new chord must be likelier, over the beats it lasts, by enough
    to pay for the change. A blip cannot; a real change easily can.

    This is the Viterbi algorithm, the standard way to find the best path
    through a sequence of guesses (chord decoders like Chordino use the same
    idea). It works beat by beat, keeping for every chord the best score of
    any path that ends on it:

        stay on chord k:     best[k] + evidence for k now
        switch to chord k:   best overall - penalty + evidence for k now

    then traces back the choices that produced the winning score. Scores are
    log-probabilities, so "e^penalty times more likely" is what a change needs.
    """
    evidence = np.log(likelihood + 1e-9)
    chords = np.arange(evidence.shape[1])
    score = evidence[0].copy()
    came_from = np.zeros(evidence.shape, dtype=int)

    for beat in range(1, len(evidence)):
        leader = int(np.argmax(score))
        switch = score[leader] - penalty
        stays = score >= switch
        came_from[beat] = np.where(stays, chords, leader)
        score = np.where(stays, score, switch) + evidence[beat]

    path = [int(np.argmax(score))]
    for beat in range(len(evidence) - 1, 0, -1):
        path.append(int(came_from[beat][path[-1]]))
    return path[::-1]


def _merge(per_beat):
    """Consecutive beats with the same chord become one entry."""
    merged = []
    for start, end, label in per_beat:
        if merged and merged[-1]["label"] == label:
            merged[-1]["end"] = round(end, 4)
        else:
            merged.append({"start": round(start, 4), "end": round(end, 4),
                           "label": label, "name": name_of(label)})
    return merged


def name_of(label: str) -> str:
    """'E:min7' -> 'Em7'. N is no chord at all; X is a chord the model could
    hear but not name."""
    if label == "N":
        return "N.C."
    if label == "X":
        return "?"
    root, _, quality = label.partition(":")
    return root + SUFFIXES[quality or "maj"]


# ---- reading it back -----------------------------------------------------------

def chord_at(chords: list[dict], time: float) -> dict | None:
    """The chord playing at `time`, found by binary search over start times."""
    starts = [c["start"] for c in chords]
    i = bisect.bisect_right(starts, time) - 1
    return chords[i] if i >= 0 else None


def chart(grid: dict, found: dict, bars_per_line: int = 4) -> str:
    """The progression as text, bar by bar, one cell per beat.

    A chord is written on the beat it arrives and '.' while it carries on,
    the way a musician would jot it down:

           1 | Em .  .  .  | C  .  .  .  | G  .  .  .  | D  .  .  .  |
    """
    chords, beat_times, bars = found["chords"], grid["beats"], grid["downbeats"]
    width = max((len(c["name"]) for c in chords), default=1) + 1

    lines, row, previous = [], [], None
    for i, start in enumerate(bars):
        end = bars[i + 1] if i + 1 < len(bars) else float("inf")
        cells = []
        for beat in (b for b in beat_times if start - 0.01 <= b < end - 0.01):
            current = chord_at(chords, beat + 0.01)
            name = current["name"] if current else ""
            cells.append(("." if name == previous else name).ljust(width))
            previous = name
        row.append(" ".join(cells))

        if len(row) == bars_per_line or i == len(bars) - 1:
            first_bar = i + 2 - len(row)
            lines.append(f"{first_bar:>5} | " + " | ".join(row) + " |")
            row = []
    return "\n".join(lines)
