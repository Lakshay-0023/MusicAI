"""Bookkeeping: where cached stems live, and what has already been done.

This module knows nothing about audio. It only answers questions like
"what folder does this song belong in?" and "have we split it before?".
"""

import hashlib
import json
from pathlib import Path

CACHE_ROOT = Path("data/cache")

# The six stems htdemucs_6s produces, in a fixed order so output is predictable.
STEM_NAMES = ["Vocals", "Drums", "Bass", "Guitar", "Piano", "Other"]


def hash_file(path):
    """A short fingerprint derived from the file's actual bytes.

    Read in 1 MB chunks rather than all at once - stem .wav files run to
    50 MB+ each and this machine doesn't have RAM to waste.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def cache_dir(song_hash):
    return CACHE_ROOT / song_hash


def meta_path(song_hash):
    return cache_dir(song_hash) / "meta.json"


def is_cached(song_hash):
    """meta.json is written only after every stem has landed, so its presence
    means a complete split - a run that died halfway never looks finished."""
    return meta_path(song_hash).exists()


def write_meta(song_hash, data):
    meta_path(song_hash).write_text(json.dumps(data, indent=2))


def read_meta(song_hash):
    return json.loads(meta_path(song_hash).read_text())


def list_cached():
    """Every completed split, as (hash, meta) pairs."""
    if not CACHE_ROOT.exists():
        return []
    found = []
    for folder in sorted(CACHE_ROOT.iterdir()):
        if folder.is_dir() and is_cached(folder.name):
            found.append((folder.name, read_meta(folder.name)))
    return found


def write_index():
    """Dump the cache listing to index.json.

    The browser player cannot read the filesystem, so it reads this instead to
    populate its song dropdown.
    """
    index = [{"hash": song_hash, **meta} for song_hash, meta in list_cached()]
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    (CACHE_ROOT / "index.json").write_text(json.dumps(index, indent=2))
    return index
