"""Uploading a song, and listing what has been processed."""

import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, UploadFile

from ... import tracks
from ...audio import separation
from ...config import settings
from ...jobs import jobs
from ..deps import require_track

router = APIRouter(prefix="/tracks", tags=["tracks"])


@router.get("")
async def list_tracks():
    return [track.as_dict() for track in tracks.all_ready()]


@router.get("/{track_id}")
async def get_track(track_id: str):
    track = require_track(track_id)
    return track.as_dict() | {
        "stems": {name: f"/stems/{track_id}/{name}" for name in track.stems},
    }


@router.post("")
async def upload(file: UploadFile, background: BackgroundTasks):
    """Accept a song and hand back a ticket, immediately.

    Separation takes far longer than a request may last: it would time out,
    and while it ran the server could not answer anyone else. So the work is
    registered and this returns straight away.
    """
    # Only the bare filename - an uploaded name must never steer where the
    # file lands ("..", absolute paths).
    name = Path(file.filename or "upload.mp3").name
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    destination = settings.uploads_dir / name

    with destination.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    job = jobs.create(name)
    # Runs after this response has been sent, in a worker thread.
    background.add_task(_process, job.id, destination)
    return {"job_id": job.id}


def _process(job_id: str, path: Path) -> None:
    jobs.start(job_id)
    try:
        track_id = separation.separate(path, on_step=lambda s: jobs.step(job_id, s))
        jobs.finish(job_id, track_id)
    except Exception as error:
        jobs.fail(job_id, str(error))
