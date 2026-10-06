"""Where are the beats, and where does each bar start?

Runs once per track and writes a small file next to the stems, so nothing
musical has to be worked out while audio is playing.

Two ways of finding them, best first:

- Beat This!, a small neural network trained on thousands of songs whose
  beats people tapped in by hand. It hears the whole mix, so it needs no
  drums, and it marks downbeats - the "1" of every bar - as well as beats.
- librosa's hand-written rule, kept as a fallback for when the model is not
  installed. It finds beats only, so bars are assumed to start every
  `beats_per_bar` beats counting from the first one.
"""

import librosa
import numpy as np

from ...config import STEM_NAMES, settings
from ...storage import storage
from .source import load_mono

BEATS_FILE = "beats.json"


def detect(track_id: str, beats_per_bar: int | None = None) -> dict:
    """Find the tempo, every beat and every bar start, and save them.

    beats_per_bar is only a fallback: the model works the meter out itself.
    """
    per_bar = beats_per_bar or settings.beats_per_bar

    try:
        beats, downbeats = _neural(track_id)
        method = "beat_this"
    except ImportError:
        beats, downbeats = _rule_based(track_id, per_bar)
        method = "librosa"

    beats = extend_to_start(beats)
    downbeats = extend_to_start(downbeats)

    data = {
        "tempo": tempo_of(beats),
        "beatsPerBar": meter_of(beats, downbeats, per_bar),
        "beats": _rounded(beats),
        "downbeats": _rounded(downbeats),
        "method": method,
    }
    storage.write_json(track_id, BEATS_FILE, data)
    return data


def _neural(track_id: str):
    """Beat This! over the whole song. Raises ImportError when not installed.

    The network turns the audio into a spectrogram and, for every 20ms slice,
    outputs two probabilities: "a beat lands here" and "a bar starts here".
    The peaks of those two curves are the beats and downbeats.
    """
    import torch
    from beat_this.inference import Audio2Beats

    # The whole song: the stems add back up to it, and the whole song is what
    # the model was trained on. The upload itself is not kept.
    mix = load_mono(track_id, STEM_NAMES, settings.analysis_sample_rate)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = Audio2Beats(checkpoint_path=settings.beat_model, device=device, dbn=False)
    try:
        beats, downbeats = model(mix, settings.analysis_sample_rate)
    finally:
        # Kept around, the model would sit in GPU memory the next separation
        # needs. Loading it again costs a second or two, so let it go.
        del model
        if device == "cuda":
            torch.cuda.empty_cache()

    return np.asarray(beats, dtype=float), np.asarray(downbeats, dtype=float)


def _rule_based(track_id: str, per_bar: int):
    """librosa's beat tracker on the drum stem, with bars assumed.

    The drum stem rather than the full mix: a loud guitar chord looks much
    like a drum hit to this rule, while isolated drums are almost nothing but
    hits. The accuracy is free, since the stem already exists.
    """
    audio, rate = librosa.load(storage.path(track_id, "Drums.wav"),
                               sr=settings.analysis_sample_rate, mono=True)

    # beat_track looks for sudden rises in loudness, then finds the regular
    # spacing that best explains them - that spacing is the tempo.
    _, frames = librosa.beat.beat_track(y=audio, sr=rate)
    beats = librosa.frames_to_time(frames, sr=rate)

    # The rule cannot tell which beat is the "1", so guess the first one is.
    return beats, beats[::per_bar]


def extend_to_start(times):
    """Continue a grid backwards to the start of the song.

    Nothing is detected before the music starts, so a song with a quiet intro
    has no grid over it and no way to snap a loop there. Produced music holds
    a steady tempo, so the spacing found later projects back reliably. Works
    the same for beats and for bar starts - only the spacing differs.
    """
    if len(times) < 2:
        return times

    spacing = float(np.median(np.diff(times)))
    earlier = []
    beat = times[0] - spacing
    while beat > 0:
        earlier.append(beat)
        beat -= spacing

    return np.concatenate([np.array(sorted(earlier)), times])


def tempo_of(beats) -> float:
    """Beats per minute, from the typical gap between beats.

    The median rather than the mean, so one missed or doubled beat cannot
    drag the answer.
    """
    if len(beats) < 2:
        return 0.0
    return round(60.0 / float(np.median(np.diff(beats))), 2)


def meter_of(beats, downbeats, fallback: int) -> int:
    """How many beats make a bar: count the beats between each pair of bar
    starts and take the usual answer. 4 for most pop, 3 for a waltz."""
    if len(downbeats) < 2:
        return fallback
    positions = np.searchsorted(beats, downbeats)
    counts = np.diff(positions)
    counts = counts[counts > 0]
    if not len(counts):
        return fallback
    return int(round(float(np.median(counts))))


def _rounded(times) -> list[float]:
    return [round(float(t), 4) for t in times]


def load(track_id: str) -> dict | None:
    """Beat data if it has been worked out, otherwise None.

    Files written before bar starts were detected count as not worked out,
    so older tracks are re-analysed once, the first time they are asked for.
    """
    if not storage.exists(track_id, BEATS_FILE):
        return None
    data = storage.read_json(track_id, BEATS_FILE)
    return data if "downbeats" in data else None
