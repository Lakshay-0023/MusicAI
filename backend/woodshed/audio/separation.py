"""One song in, six stems out. The slow half of the system."""

import shutil
from pathlib import Path

import numpy as np
import soundfile as sf
from audio_separator.separator import Separator

from .. import tracks
from ..config import STEM_NAMES, settings
from ..storage import storage
from . import encoding
from .analysis import beats, chords, lyrics


def separate(source: Path | str, force: bool = False, on_step=None) -> str:
    """Split a song into stems and return its track id.

    Already-split songs return immediately: separation is the only slow step
    in the system, so it should never be paid for twice.
    """
    source = Path(source)
    tid = tracks.track_id(source)

    def step(message: str) -> None:
        if on_step:
            on_step(message)

    if tracks.is_ready(tid) and not force:
        step("cached")
        encoding.write_opus_copies(storage.ensure(tid))
        return tid

    folder = storage.ensure(tid)

    # The upload is hashed as it arrived, so the track id stays tied to the
    # file the user actually has - only the model sees the decoded audio.
    step("decoding")
    audio_path = encoding.decode(source, folder)

    step("separating")
    try:
        _separate_in_chunks(audio_path, folder, step)
    finally:
        audio_path.unlink(missing_ok=True)

    step("encoding")
    encoding.write_opus_copies(folder)

    step("finding beats")
    beats.detect(tid)

    # Chords are a bonus on top of the stems, never a reason to lose them: if
    # this fails, the track is still finished, and the player asks again later.
    step("finding chords")
    try:
        chords.detect(tid)
    except Exception as error:  # noqa: BLE001 - any failure here is survivable
        step(f"chords skipped ({error})")

    # Same rule for lyrics, the slowest of the three. A song with no singing
    # simply comes back with no lines.
    step("writing down the lyrics")
    try:
        lyrics.detect(tid)
    except Exception as error:  # noqa: BLE001
        step(f"lyrics skipped ({error})")

    # Written last on purpose - see tracks.is_ready().
    tracks.write(tracks.Track(id=tid, source=source.name,
                              model=settings.separation_model, stems=STEM_NAMES))
    return tid


def _separate_in_chunks(audio_path: Path, folder: Path, step) -> None:
    """Separate a song a piece at a time, so memory does not grow with length.

    Given a whole song, Demucs builds all six stems for all of it in memory at
    once: for a 5.7-minute song, one 687MB block on top of its working copies,
    which an 8GB laptop with a browser open could not find ("Unable to
    allocate 687 MiB"). So the song goes through in chunks:

        |----- chunk 1 -----|
                        |XXXX----- chunk 2 -----|
                                            |XXXX----- chunk 3 ---|
                         ^ overlap, crossfaded

    Each chunk is read from the decoded WAV on disk, separated, and its stems
    appended to the six stem files before the next is read, so only one chunk
    is ever in memory: the same few hundred MB for a 3-minute song or a
    15-minute live set.

    Neighbouring chunks overlap, and across the overlap one fades out as the
    next fades in. A cut with no overlap would click: the model sees less
    context at the very edge of a chunk, so its output there is slightly
    different from the same moment heard mid-chunk. Blending the two hides the
    seam completely - Demucs does exactly this inside itself, on smaller
    pieces, for the same reason.
    """
    info = sf.info(str(audio_path))
    rate, total = info.samplerate, info.frames
    length = int(settings.separation_chunk_seconds * rate)
    overlap = int(settings.separation_overlap_seconds * rate)
    count = max(1, -(-total // length))  # chunks needed, rounded up

    parts = folder / "parts"
    parts.mkdir(exist_ok=True)
    separator = Separator(output_dir=str(parts), demucs_params=settings.demucs_params)
    separator.load_model(model_filename=settings.separation_model)

    writers = {name: sf.SoundFile(str(folder / f"{name}.wav"), "w", rate, 2, subtype="PCM_16")
               for name in STEM_NAMES}
    tails = {}     # each stem's last `overlap` frames, held back to blend with the next chunk
    fade_in = np.linspace(0.0, 1.0, overlap, dtype=np.float32)[:, None]

    try:
        for i in range(count):
            if count > 1:
                step(f"separating {i + 1}/{count}")
            start = max(0, i * length - overlap)
            stop = min(total, (i + 1) * length)
            chunk = parts / f"chunk{i:03d}.wav"
            sf.write(str(chunk), sf.read(str(audio_path), start=start, stop=stop, dtype="float32")[0], rate)

            produced = [parts / Path(f).name for f in separator.separate(str(chunk))]
            chunk.unlink(missing_ok=True)
            last = i == count - 1

            for name in STEM_NAMES:
                path = next(p for p in produced if f"({name})" in p.name)
                stem, _ = sf.read(str(path), dtype="float32", always_2d=True)
                path.unlink(missing_ok=True)
                stem = _fit(stem, stop - start)

                if i > 0:
                    # Fade the held-back end of the last chunk into this one's start.
                    stem[:overlap] = tails[name] * (1 - fade_in) + stem[:overlap] * fade_in
                if last:
                    writers[name].write(stem)
                else:
                    writers[name].write(stem[:-overlap])
                    tails[name] = stem[-overlap:]
    finally:
        for writer in writers.values():
            writer.close()
        shutil.rmtree(parts, ignore_errors=True)


def _fit(stem, frames: int):
    """Trim or pad a stem to exactly the chunk's length, so chunks line up
    sample for sample however the model rounded its output."""
    if len(stem) >= frames:
        return stem[:frames]
    return np.pad(stem, ((0, frames - len(stem)), (0, 0)))
