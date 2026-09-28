"""Work that outlives the request that asked for it.

Separation takes far longer than a web request may last, so an upload gets a
ticket and the client follows that ticket instead. This holds the tickets.

In memory, deliberately: a finished track is already saved, so losing ticket
records on restart costs nothing. Swapping this class for a Redis-backed one
is what changes when work spreads across more than one machine.
"""

import asyncio
from dataclasses import asdict, dataclass, field
from uuid import uuid4


@dataclass
class Job:
    id: str
    source: str
    status: str = "queued"      # queued | running | done | error
    step: str = ""              # what it is doing right now
    track_id: str | None = None
    error: str | None = None

    @property
    def finished(self) -> bool:
        return self.status in ("done", "error")

    def as_dict(self) -> dict:
        return asdict(self) | {"finished": self.finished}


class JobRegistry:
    def __init__(self):
        self._jobs: dict[str, Job] = {}

    def create(self, source: str) -> Job:
        job = Job(id=uuid4().hex[:12], source=source)
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def start(self, job_id: str) -> None:
        self._update(job_id, status="running")

    def step(self, job_id: str, step: str) -> None:
        self._update(job_id, step=step)

    def finish(self, job_id: str, track_id: str) -> None:
        self._update(job_id, status="done", step="done", track_id=track_id)

    def fail(self, job_id: str, message: str) -> None:
        self._update(job_id, status="error", error=message)

    async def watch(self, job_id: str, interval: float = 0.4):
        """Yield the job each time it is worth reporting, until it settles."""
        last = None
        while True:
            job = self.get(job_id)
            if job is None:
                return
            snapshot = job.as_dict()
            if snapshot != last:
                yield snapshot
                last = snapshot
            if job.finished:
                return
            await asyncio.sleep(interval)

    def _update(self, job_id: str, **changes) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        for key, value in changes.items():
            setattr(job, key, value)


jobs = JobRegistry()
