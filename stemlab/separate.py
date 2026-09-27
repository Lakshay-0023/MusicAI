"""One song in, six stem files out. The slow half of the system.

This is Phase 1's script generalized: any song, cached so it never runs twice
for the same audio.
"""

import subprocess
from pathlib import Path

from audio_separator.separator import Separator

from . import analyse, store

MODEL = "htdemucs_6s.yaml"

# shifts=2 (the library default) separates the whole song twice at slightly
# different time offsets and averages the results. Slightly cleaner, but the
# second pass allocates another ~500MB while the first result is still held,
# which crashes this 8GB machine. One pass: twice as fast, half the memory.
DEMUCS_PARAMS = {"segment_size": "Default", "shifts": 1, "overlap": 0.25, "segments_enabled": True}


VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".3gp", ".wmv", ".flv"}


def extract_audio(video_path, out_dir):
    """Pull the soundtrack out of a video file; the picture is discarded.

    Phone recordings of a band arrive as video, and the model only ever
    wanted the audio. Forced to 44.1kHz stereo so every song reaching the
    separator looks the same regardless of what the camera produced.
    """
    audio = out_dir / "source.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video_path),
         "-vn", "-ac", "2", "-ar", "44100", str(audio)],
        check=True,
    )
    return audio


def to_opus(out_dir):
    """Write a compressed copy of each stem alongside the WAV.

    Six WAV stems run to ~300MB; the Opus copies are around a tenth of that.
    The WAVs stay because they are lossless - re-rendering anything later
    should start from those, not from a compressed copy.
    """
    for name in store.STEM_NAMES:
        wav = out_dir / f"{name}.wav"
        opus = out_dir / f"{name}.opus"
        if opus.exists() or not wav.exists():
            continue
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
             "-c:a", "libopus", "-b:a", "96k", str(opus)],
            check=True,
        )


def split(song_path, force=False):
    """Separate a song into stems. Returns the song's hash.

    If the song was split before, this returns immediately - separation is
    the only slow step in the whole system, so never pay for it twice.
    """
    song_path = Path(song_path)
    song_hash = store.hash_file(song_path)
    out_dir = store.cache_dir(song_hash)

    if store.is_cached(song_hash) and not force:
        print(f"Already split: {song_hash}  (cached, nothing to do)")
        to_opus(out_dir)
        store.write_index()
        return song_hash

    print(f"Splitting {song_path.name}")
    print(f"  hash  : {song_hash}")
    print(f"  model : {MODEL}")

    out_dir.mkdir(parents=True, exist_ok=True)

    # A video is hashed as it arrived, so the cache key stays tied to the file
    # the user actually has - only the separator gets the extracted audio.
    audio_path = song_path
    if song_path.suffix.lower() in VIDEO_SUFFIXES:
        print("  video -> extracting audio")
        audio_path = extract_audio(song_path, out_dir)

    separator = Separator(output_dir=str(out_dir), demucs_params=DEMUCS_PARAMS)
    separator.load_model(model_filename=MODEL)
    written = separator.separate(str(audio_path))

    if audio_path != song_path:
        audio_path.unlink()

    # The model names its output "<long song name>_(Drums)_htdemucs_6s.wav".
    # Rename to a plain "Drums.wav" so nothing downstream has to care.
    for filename in written:
        produced = out_dir / Path(filename).name
        for name in store.STEM_NAMES:
            if f"({name})" in produced.name:
                produced.replace(out_dir / f"{name}.wav")
                break

    to_opus(out_dir)

    # Beat tracking can fail on material it cannot make sense of, and losing a
    # finished 25-second separation over that would be absurd. The player
    # simply goes without bar lines.
    try:
        beats = analyse.analyse(song_hash)
        print(f"  tempo : {beats['tempo']} bpm, {len(beats['beats'])} beats")
    except Exception as err:
        print(f"  beat detection failed ({err}) - continuing without it")

    # Written last on purpose - see store.is_cached().
    store.write_meta(song_hash, {
        "source": song_path.name,
        "model": MODEL,
        "stems": store.STEM_NAMES,
    })

    store.write_index()

    print(f"Done -> {out_dir}")
    return song_hash
