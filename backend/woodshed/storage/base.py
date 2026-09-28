"""What the rest of the app is allowed to assume about where files live.

Today everything sits on the local disk. When tracks move to object storage,
only an implementation of this protocol changes - no route, service or audio
module has to know.
"""

import json
from pathlib import Path
from typing import Protocol


class TrackStorage(Protocol):
    """One folder-worth of files per track, addressed by track id."""

    def path(self, track_id: str, name: str) -> Path: ...

    def exists(self, track_id: str, name: str) -> bool: ...

    def ensure(self, track_id: str) -> Path: ...

    def read_json(self, track_id: str, name: str) -> dict: ...

    def write_json(self, track_id: str, name: str, data: dict) -> None: ...

    def track_ids(self) -> list[str]: ...


def dumps(data: dict) -> str:
    return json.dumps(data, indent=2)
