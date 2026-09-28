"""Musical information about a track: beats today, chords and key later.

Every analyser gets a route of the same shape here, so adding one is a module
plus an endpoint and nothing else.
"""

from fastapi import APIRouter

from ...audio.analysis import beats
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
