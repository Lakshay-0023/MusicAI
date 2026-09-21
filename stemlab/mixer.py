"""Stems plus volumes, out comes one audio file. The fast half of the system.

This is Phase 2's arithmetic generalized. No AI here and none needed: the
model already did its one job, and what's left is multiplication and addition.
"""

import numpy as np
import soundfile as sf

from . import store


def load_stems(song_hash):
    """Read all six stems into memory as arrays of numbers."""
    folder = store.cache_dir(song_hash)
    stems = {}
    sample_rate = None
    for name in store.STEM_NAMES:
        audio, sample_rate = sf.read(folder / f"{name}.wav")
        stems[name] = audio
    return stems, sample_rate


def mix(stems, gains):
    """Volume is multiplying, mixing is adding. That is the entire product.

    Clipping at the end because the sum can exceed +/-1.0, and a speaker cone
    physically cannot travel further than fully out - past that you get
    distortion instead of loudness.
    """
    mixed = sum(stems[name] * gains.get(name, 1.0) for name in stems)
    return np.clip(mixed, -1.0, 1.0)


def render(song_hash, gains, out_path):
    """Load the cached stems, apply the gains, write the result."""
    stems, sample_rate = load_stems(song_hash)
    sf.write(out_path, mix(stems, gains), sample_rate)
    return out_path
