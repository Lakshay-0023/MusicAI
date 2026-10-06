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
    # roughly halves the time it takes. It is also the rate Beat This! was
    # trained at, so the model never has to resample.
    analysis_sample_rate: int = 22050

    # Which trained Beat This! weights to use; downloaded on first use.
    beat_model: str = "final0"

    # Only used when the model is unavailable and the meter must be assumed.
    beats_per_bar: int = 4

    # The stems the chord model hears: harmony only. Drums are noise to it, and
    # a sung melody note looks like a chord note. `woodshed chords --full-mix`
    # lets it hear everything, to compare.
    chord_stems: tuple = ("Bass", "Guitar", "Piano", "Other")

    # BTC's trained weights (large vocabulary, 170 chords), fetched on first use.
    chord_model_url: str = ("https://raw.githubusercontent.com/jayg996/BTC-ISMIR19/"
                            "master/test/btc_model_large_voca.pt")

    # Which Whisper model transcribes the vocals. "turbo" is large-v3 with a
    # slimmer decoder: near-best accuracy, ~1.6GB of GPU memory at 16 bits.
    # "small" (~0.5GB) is the fallback if memory ever runs out.
    lyrics_model: str = "turbo"

    # The language sung, as a Whisper code: "hi" (shown in Roman letters),
    # "en", ... or "auto" to let Whisper guess. On singing its guess is poor -
    # it heard a Hindi song as English and wrote English sentences - so it is
    # told. Hindi mode copes with the odd English word in a Bollywood lyric.
    lyrics_language: str = "hi"

    @property
    def web_dir(self) -> Path:
        """The built front end, when there is one.

        In development the React app is served by Vite on its own port and
        talks to this server through a proxy, so nothing is served from here.
        After `npm run build` the finished files appear in frontend/dist and
        this server can serve them itself.
        """
        return REPO_ROOT / "frontend" / "dist"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def models_dir(self) -> Path:
        """Downloaded model weights. Like the stems, never in version control."""
        return self.data_dir / "models"


settings = Settings()
