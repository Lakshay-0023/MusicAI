"""Format conversion. Everything here is ffmpeg doing the actual work."""

import subprocess
from pathlib import Path

from ..config import STEM_NAMES, VIDEO_SUFFIXES, settings


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_SUFFIXES


def decode(source: Path, into: Path) -> Path:
    """Any song or video -> a plain 44.1kHz stereo WAV; a video's picture is dropped.

    Done for every upload, not just videos: a WAV can be read a piece at a
    time straight from disk, which is what lets a long song be separated in
    chunks. Forcing one rate and layout also means everything reaching the
    model looks the same, whatever the phone or the file format produced.
    """
    out = into / "source.wav"
    _run(["-i", str(source), "-vn", "-ac", "2", "-ar", "44100", str(out)])
    return out


def write_opus_copies(folder: Path) -> None:
    """A compressed copy of each stem, about a sixteenth the size.

    The WAVs stay: they are lossless, and anything re-rendered later should
    start from those rather than from a copy that has already lost detail.
    Compress what you send; keep what you have.
    """
    for name in STEM_NAMES:
        wav = folder / f"{name}.wav"
        opus = folder / f"{name}.opus"
        if opus.exists() or not wav.exists():
            continue
        _run(["-i", str(wav), "-c:a", "libopus", "-b:a", settings.opus_bitrate, str(opus)])


def compact_mp3(wav: Path, out: Path) -> Path:
    """A small mono MP3 of a stem, for sending somewhere: ~0.5MB a minute.

    Mono at 64kbps keeps every word clear - it is speech-quality, not
    listening-quality - while a 7-minute vocal stays around 3-4MB.
    """
    _run(["-i", str(wav), "-ac", "1", "-ar", "22050", "-b:a", "64k", str(out)])
    return out


def _run(args: list[str]) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)
