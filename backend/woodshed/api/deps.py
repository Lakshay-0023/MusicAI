"""Shared checks every route can lean on."""

import re

from fastapi import HTTPException

from .. import tracks

TRACK_ID = re.compile(r"[0-9a-f]{16}")


def require_track(track_id: str) -> tracks.Track:
    """Reject anything that is not a track we produced, before touching disk.

    Path segments arriving from outside are input to be validated, never
    instruction to be followed - most of all when about to become a file path.
    """
    if not TRACK_ID.fullmatch(track_id) or not tracks.is_ready(track_id):
        raise HTTPException(404, "unknown track")
    return tracks.read(track_id)
