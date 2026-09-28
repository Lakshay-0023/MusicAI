"""Tracks on the local filesystem, one folder per track id."""

import json
from pathlib import Path

from ..config import settings
from .base import dumps


class LocalTrackStorage:
    def __init__(self, root: Path | None = None):
        self.root = root or settings.cache_dir

    def path(self, track_id: str, name: str) -> Path:
        return self.root / track_id / name

    def exists(self, track_id: str, name: str) -> bool:
        return self.path(track_id, name).exists()

    def ensure(self, track_id: str) -> Path:
        folder = self.root / track_id
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def read_json(self, track_id: str, name: str) -> dict:
        return json.loads(self.path(track_id, name).read_text())

    def write_json(self, track_id: str, name: str, data: dict) -> None:
        self.ensure(track_id)
        self.path(track_id, name).write_text(dumps(data))

    def track_ids(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(f.name for f in self.root.iterdir() if f.is_dir())


storage = LocalTrackStorage()
