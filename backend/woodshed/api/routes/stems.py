"""Serving the separated audio."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ...config import STEM_NAMES
from ...storage import storage
from ..deps import require_track

router = APIRouter(prefix="/stems", tags=["stems"])


@router.get("/{track_id}/{stem}")
async def get_stem(track_id: str, stem: str):
    require_track(track_id)
    if stem not in STEM_NAMES:
        raise HTTPException(404, "no such stem")

    # The compressed copy where it exists - a fraction of the size to send.
    if storage.exists(track_id, f"{stem}.opus"):
        return FileResponse(storage.path(track_id, f"{stem}.opus"), media_type="audio/ogg")
    return FileResponse(storage.path(track_id, f"{stem}.wav"), media_type="audio/wav")
