"""Musical information extracted from a track: beats, chords and lyrics now,
key later.

Each analyser follows the same shape - detect(track_id) writes a JSON file
next to the stems, load(track_id) reads it back - so adding one means adding
a module here and a route, nothing else.
"""

from . import beats, chords, lyrics

__all__ = ["beats", "chords", "lyrics"]
