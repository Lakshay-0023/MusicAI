"""Following work that is already under way."""

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ...jobs import jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}/events")
async def job_events(job_id: str):
    """Push progress down an open connection until the job settles.

    Server-sent events rather than a websocket: nothing ever needs to travel
    back up, and this stays an ordinary HTTP response the browser reconnects
    to by itself.
    """
    async def stream():
        async for snapshot in jobs.watch(job_id):
            yield f"data: {json.dumps(snapshot)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})
