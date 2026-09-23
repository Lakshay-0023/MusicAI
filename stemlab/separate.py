"""One song in, six stem files out. The slow half of the system.

This is Phase 1's script generalized: any song, cached so it never runs twice
for the same audio.
"""

from pathlib import Path

from audio_separator.separator import Separator

from . import store

MODEL = "htdemucs_6s.yaml"

# shifts=2 (the library default) separates the whole song twice at slightly
# different time offsets and averages the results. Slightly cleaner, but the
# second pass allocates another ~500MB while the first result is still held,
# which crashes this 8GB machine. One pass: twice as fast, half the memory.
DEMUCS_PARAMS = {"segment_size": "Default", "shifts": 1, "overlap": 0.25, "segments_enabled": True}


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
        return song_hash

    print(f"Splitting {song_path.name}")
    print(f"  hash  : {song_hash}")
    print(f"  model : {MODEL}")

    out_dir.mkdir(parents=True, exist_ok=True)

    separator = Separator(output_dir=str(out_dir), demucs_params=DEMUCS_PARAMS)
    separator.load_model(model_filename=MODEL)
    written = separator.separate(str(song_path))

    # The model names its output "<long song name>_(Drums)_htdemucs_6s.wav".
    # Rename to a plain "Drums.wav" so nothing downstream has to care.
    for filename in written:
        produced = out_dir / Path(filename).name
        for name in store.STEM_NAMES:
            if f"({name})" in produced.name:
                produced.replace(out_dir / f"{name}.wav")
                break

    # Written last on purpose - see store.is_cached().
    store.write_meta(song_hash, {
        "source": song_path.name,
        "model": MODEL,
        "stems": store.STEM_NAMES,
    })

    print(f"Done -> {out_dir}")
    return song_hash
