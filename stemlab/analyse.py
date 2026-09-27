"""Where are the beats?

Runs once per song, in the kitchen, and writes a small JSON file next to the
stems. The browser reads it to draw bar lines and to snap loop points, so
nothing musical has to be worked out while playing.
"""

import json

import librosa
import numpy as np

from . import store

BEATS_FILE = "beats.json"


def analyse(song_hash, beats_per_bar=4):
    """Find the tempo and every beat, from the drum stem.

    The drum stem, not the full mix: a loud guitar chord looks much like a
    drum hit to a beat tracker, and the isolated drums contain almost nothing
    but hits. Free accuracy, since the stem already exists.
    """
    folder = store.cache_dir(song_hash)
    path = folder / "Drums.wav"

    # 22.05kHz is plenty for finding beats - nothing musical up at 20kHz tells
    # you where a snare is - and it halves the work.
    audio, rate = librosa.load(path, sr=22050, mono=True)

    # beat_track looks for sudden rises in loudness, then finds the regular
    # spacing that best explains them - that spacing is the tempo.
    tempo, frames = librosa.beat.beat_track(y=audio, sr=rate)
    times = librosa.frames_to_time(frames, sr=rate)

    times = extend_to_start(times)

    data = {
        "tempo": round(float(np.atleast_1d(tempo)[0]), 2),
        "beatsPerBar": beats_per_bar,
        "beats": [round(float(t), 4) for t in times],
    }

    (folder / BEATS_FILE).write_text(json.dumps(data))
    return data


def extend_to_start(times):
    """Continue the beat grid backwards to the start of the song.

    Beats are only detected where drums play, so a song with a drum-free
    intro has no grid over that intro - and no way to snap a loop there.
    Produced music holds a steady tempo, so the spacing found later is
    reliable enough to project backwards.
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


def load(song_hash):
    """Beat data if it has been worked out, otherwise None."""
    path = store.cache_dir(song_hash) / BEATS_FILE
    return json.loads(path.read_text()) if path.exists() else None
