"""Musical information about a track: beats, chords and lyrics today, key later.

Every analyser gets a route of the same shape here, so adding one is a module
plus an endpoint and nothing else.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...ai import gemini, polish
from ...audio.analysis import beats, chords, lyrics
from ..deps import require_track

router = APIRouter(prefix="/tracks", tags=["analysis"])


# A plain def, not async: FastAPI then runs it in a worker thread, so the few
# seconds a first analysis takes cannot freeze every other request.
@router.get("/{track_id}/beats")
def get_beats(track_id: str):
    require_track(track_id)
    # Tracks processed before beat detection existed are analysed on first
    # request, then cached like everything else.
    return beats.load(track_id) or beats.detect(track_id)


@router.get("/{track_id}/chords")
def get_chords(track_id: str):
    require_track(track_id)
    return chords.load(track_id) or chords.detect(track_id)


@router.get("/{track_id}/lyrics")
def get_lyrics(track_id: str):
    require_track(track_id)
    # The slowest of the three on first request - a minute or so for a song.
    return lyrics.load(track_id) or lyrics.detect(track_id)


class PolishRequest(BaseModel):
    lyrics: str | None = None   # the song's lyrics, pasted by the player - optional
    force: bool = False         # use pasted lyrics even if they look like another song


@router.post("/{track_id}/lyrics/polish")
def polish_lyrics(track_id: str, request: PolishRequest):
    """Correct the lyrics with AI. Sends lyrics text only, and only when asked."""
    require_track(track_id)
    try:
        return polish.polish(track_id, request.lyrics, request.force)
    except polish.LyricsMismatch as mismatch:
        # 409 Conflict: the request makes sense, but not for this song.
        raise HTTPException(409, {"message": str(mismatch), "score": mismatch.score,
                                  "byModel": mismatch.by_model}) from mismatch
    except gemini.AIUnavailable as unavailable:
        raise HTTPException(503, {"message": str(unavailable)}) from unavailable
    except ValueError as invalid:
        raise HTTPException(400, {"message": str(invalid)}) from invalid


@router.post("/{track_id}/lyrics/restore")
def restore_lyrics(track_id: str):
    """Undo an AI correction: back to exactly what was heard."""
    require_track(track_id)
    return polish.restore(track_id)
