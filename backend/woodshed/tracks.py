"""What a track is, and how one is identified.

A track is identified by a hash of the audio file's bytes, never by its name.
Names lie: files get renamed, and two different songs are both called
track.mp3. A hash is derived from the content, so identical audio always maps
to the same track and different audio never collides.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .config import STEM_NAMES, settings
from .storage import storage

META_FILE = "meta.json"

CHUNK = 1024 * 1024


@dataclass(frozen=True)
class Track:
    id: str
    source: str
    model: str
    stems: tuple[str, ...] = STEM_NAMES

    def as_dict(self) -> dict:
        return {"id": self.id, "source": self.source,
                "model": self.model, "stems": list(self.stems)}


def track_id(path) -> str:
    """A short fingerprint of the file's contents.

    Read in 1MB chunks rather than all at once: stem files run past 50MB and
    loading whole files into memory is a habit that bites on a small machine.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def is_ready(tid: str) -> bool:
    """meta.json is written only after every stem has landed, so its presence
    means a complete track - a run that died halfway never looks finished."""
    return storage.exists(tid, META_FILE)


def read(tid: str) -> Track:
    data = storage.read_json(tid, META_FILE)
    return Track(id=tid, source=data["source"], model=data["model"],
                 stems=tuple(data.get("stems", STEM_NAMES)))


def write(track: Track) -> None:
    storage.write_json(track.id, META_FILE, {
        "source": track.source,
        "model": track.model,
        "stems": list(track.stems),
    })


def all_ready() -> list[Track]:
    return [read(tid) for tid in storage.track_ids() if is_ready(tid)]
