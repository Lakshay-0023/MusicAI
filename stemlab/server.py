"""The server, so the two halves meet.

Drop a song on the page, watch it split, play it. One server does everything:
serves the page, accepts uploads, runs separation in the background, streams
progress, and serves the finished stems.

  POST /tracks            upload a song      -> { job_id }, immediately
  GET  /jobs/{id}/events  progress stream    (server-sent events)
  GET  /tracks            every cached song
  GET  /tracks/{hash}     one song + stem URLs
  GET  /stems/{hash}/{n}  the audio itself
  GET  /                  the player page

Run:  .venv\\Scripts\\python.exe -m stemlab serve
"""

import asyncio
import json
import re
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import analyse, separate, store

UPLOADS = Path("data/uploads")
WEB = Path(__file__).resolve().parent.parent / "web"

# Separation is slow, so an upload cannot be answered by one request. Each
# upload gets a ticket, and the browser follows that ticket's progress.
# In memory only: a finished split lives in the cache on disk, so losing job
# records on restart costs nothing.
JOBS = {}

app = FastAPI(title="stemlab")


def run_split(job_id, path):
    """Runs in a worker thread so the server stays responsive meanwhile."""
    JOBS[job_id]["status"] = "separating"
    try:
        JOBS[job_id]["hash"] = separate.split(path)
        JOBS[job_id]["status"] = "done"
    except Exception as err:
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["error"] = str(err)


@app.post("/tracks")
async def upload(file: UploadFile, background: BackgroundTasks):
    # Only the bare filename - an uploaded name must never be able to steer
    # where the file lands (".." and absolute paths are how that goes wrong).
    name = Path(file.filename or "upload.mp3").name
    UPLOADS.mkdir(parents=True, exist_ok=True)
    dest = UPLOADS / name
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    job_id = uuid4().hex[:12]
    JOBS[job_id] = {"status": "queued", "source": name, "hash": None, "error": None}

    # Runs after this response has been sent, which is what lets the upload
    # return a ticket instantly instead of holding the connection open.
    background.add_task(run_split, job_id, dest)
    return {"job_id": job_id}


@app.get("/jobs/{job_id}/events")
async def job_events(job_id: str):
    """Push status down an open connection until the job settles.

    Server-sent events, not websockets: nothing ever needs to travel back up,
    and this is a plain HTTP response the browser reconnects on its own.
    """
    async def stream():
        while True:
            job = JOBS.get(job_id)
            if job is None:
                yield f"data: {json.dumps({'status': 'error', 'error': 'unknown job'})}\n\n"
                return
            yield f"data: {json.dumps(job)}\n\n"
            if job["status"] in ("done", "error"):
                return
            await asyncio.sleep(0.4)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


@app.get("/tracks")
async def tracks():
    return [{"hash": h, **meta} for h, meta in store.list_cached()]


@app.get("/tracks/{song_hash}")
async def track(song_hash: str):
    meta = load_meta(song_hash)
    return {
        "hash": song_hash,
        **meta,
        "stems": {n: f"/stems/{song_hash}/{n}" for n in store.STEM_NAMES},
    }


# A plain "def", not "async def": FastAPI then runs it in a worker thread, so
# the few seconds of analysis cannot block every other request.
@app.get("/tracks/{song_hash}/beats")
def beats(song_hash: str):
    load_meta(song_hash)
    # Songs split before beat tracking existed get analysed on first request,
    # then cached like everything else.
    return analyse.load(song_hash) or analyse.analyse(song_hash)


@app.get("/stems/{song_hash}/{stem}")
async def stem_audio(song_hash: str, stem: str):
    load_meta(song_hash)
    if stem not in store.STEM_NAMES:
        raise HTTPException(404, "no such stem")

    folder = store.cache_dir(song_hash)
    # Prefer the compressed copy - a tenth the size over the network.
    opus = folder / f"{stem}.opus"
    if opus.exists():
        return FileResponse(opus, media_type="audio/ogg")
    return FileResponse(folder / f"{stem}.wav", media_type="audio/wav")


def load_meta(song_hash):
    """Reject anything that is not a hash we produced, before touching disk."""
    if not re.fullmatch(r"[0-9a-f]{16}", song_hash) or not store.is_cached(song_hash):
        raise HTTPException(404, "unknown track")
    return store.read_meta(song_hash)


# Mounted last: these routes are matched in order, so the API wins and
# everything else falls through to the player page.
app.mount("/", StaticFiles(directory=WEB, html=True), name="web")


def serve(host="127.0.0.1", port=8000):
    import uvicorn
    print(f"stemlab running at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")
