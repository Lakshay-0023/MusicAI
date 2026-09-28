"""Where are the beats?

Runs once per track and writes a small file next to the stems, so nothing
musical has to be worked out while audio is playing.
"""

import librosa
import numpy as np

from ...config import settings
from ...storage import storage

BEATS_FILE = "beats.json"


def detect(track_id: str, beats_per_bar: int | None = None) -> dict:
    """Find the tempo and every beat, from the drum stem.

    The drum stem rather than the full mix: a loud guitar chord looks much
    like a drum hit to a beat tracker, while isolated drums are almost
    nothing but hits. The accuracy is free, since the stem already exists.
    """
    per_bar = beats_per_bar or settings.beats_per_bar
    audio, rate = librosa.load(storage.path(track_id, "Drums.wav"),
                               sr=settings.analysis_sample_rate, mono=True)

    # beat_track looks for sudden rises in loudness, then finds the regular
    # spacing that best explains them - that spacing is the tempo.
    tempo, frames = librosa.beat.beat_track(y=audio, sr=rate)
    times = extend_to_start(librosa.frames_to_time(frames, sr=rate))

    data = {
        "tempo": round(float(np.atleast_1d(tempo)[0]), 2),
        "beatsPerBar": per_bar,
        "beats": [round(float(t), 4) for t in times],
    }
    storage.write_json(track_id, BEATS_FILE, data)
    return data


def extend_to_start(times):
    """Continue the grid backwards to the start of the song.

    Beats are only detected where drums play, so a song with a drum-free
    intro has no grid over it and no way to snap a loop there. Produced music
    holds a steady tempo, so the spacing found later projects back reliably.
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


def load(track_id: str) -> dict | None:
    """Beat data if it has been worked out, otherwise None."""
    if not storage.exists(track_id, BEATS_FILE):
        return None
    return storage.read_json(track_id, BEATS_FILE)
