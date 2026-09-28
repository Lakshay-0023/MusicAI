"""Stems plus levels, out comes one file. The fast half of the system.

No model is involved and none is needed: separation already did its one job,
and what remains is multiplication and addition.
"""

import numpy as np
import soundfile as sf

from ..config import STEM_NAMES
from ..storage import storage


def load_stems(track_id: str):
    """Read every stem into memory as an array of numbers."""
    stems, rate = {}, None
    for name in STEM_NAMES:
        stems[name], rate = sf.read(storage.path(track_id, f"{name}.wav"))
    return stems, rate


def mix(stems: dict, gains: dict):
    """Volume is multiplying, mixing is adding. That is the whole product.

    Clipped at the end because a sum can exceed the range a speaker can
    travel; past that you get distortion rather than loudness. In practice
    levels only ever come down, so this should never actually fire.
    """
    mixed = sum(stems[name] * gains.get(name, 1.0) for name in stems)
    return np.clip(mixed, -1.0, 1.0)


def render(track_id: str, gains: dict, out_path) -> str:
    stems, rate = load_stems(track_id)
    sf.write(out_path, mix(stems, gains), rate)
    return str(out_path)
