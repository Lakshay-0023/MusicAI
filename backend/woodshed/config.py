"""Every tunable value in one place.

Anything that might differ between a laptop and a server lives here, so no
module has to hardcode a path or a model name.
"""

from dataclasses import dataclass, field
from pathlib import Path

# backend/woodshed/config.py -> backend/woodshed -> backend -> the repo root
REPO_ROOT = Path(__file__).resolve().parents[2]

# The six sources htdemucs_6s produces, in a fixed order so output is stable.
STEM_NAMES = ("Vocals", "Drums", "Bass", "Guitar", "Piano", "Other")

VIDEO_SUFFIXES = frozenset(
    {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".3gp", ".wmv", ".flv"}
)


@dataclass(frozen=True)
class Settings:
    data_dir: Path = REPO_ROOT / "data"
    web_dir: Path = REPO_ROOT / "frontend"

    separation_model: str = "htdemucs_6s.yaml"

    # shifts=2 (the library default) separates the whole song twice at slightly
    # different offsets and averages them. Marginally cleaner, but the second
    # pass holds another full-length buffer and exhausts an 8GB machine.
    demucs_params: dict = field(default_factory=lambda: {
        "segment_size": "Default",
        "shifts": 1,
        "overlap": 0.25,
        "segments_enabled": True,
    })

    opus_bitrate: str = "96k"

    # Beat tracking needs nothing above a few kHz, and halving the sample rate
    # roughly halves the time it takes.
    analysis_sample_rate: int = 22050
    beats_per_bar: int = 4

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"


settings = Settings()
