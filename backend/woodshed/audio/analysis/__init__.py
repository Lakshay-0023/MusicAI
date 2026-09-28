"""Musical information extracted from a track: beats now, chords and key later.

Each analyser follows the same shape - detect(track_id) writes a JSON file
next to the stems, load(track_id) reads it back - so adding one means adding
a module here and a route, nothing else.
"""

from . import beats

__all__ = ["beats"]
