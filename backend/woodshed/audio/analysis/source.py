"""The audio an analyser listens to.

Each analyser hears a different part of the song: the beat model wants the
whole mix, the chord model only the instruments that carry harmony. Both get it
the same way - load the chosen stems and add them up, since mixing is addition.
"""

import librosa

from ...storage import storage


def load_mono(track_id: str, stems, rate: int):
    """The chosen stems summed into one mono signal at `rate` samples a second.

    Loading at the analysis rate rather than 44.1 kHz halves the memory: about
    130MB for all six stems of a four-minute song.
    """
    mix = None
    for name in stems:
        audio, _ = librosa.load(storage.path(track_id, f"{name}.wav"), sr=rate, mono=True)
        mix = audio if mix is None else mix + audio
    return mix
