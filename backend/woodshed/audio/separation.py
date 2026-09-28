"""One song in, six stems out. The slow half of the system."""

from pathlib import Path

from audio_separator.separator import Separator

from .. import tracks
from ..config import STEM_NAMES, settings
from ..storage import storage
from . import encoding
from .analysis import beats


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

    # The video is hashed as it arrived, so the track id stays tied to the
    # file the user actually has - only the model sees the extracted audio.
    audio_path = source
    if encoding.is_video(source):
        step("extracting audio")
        audio_path = encoding.extract_audio(source, folder)

    step("separating")
    separator = Separator(output_dir=str(folder), demucs_params=settings.demucs_params)
    separator.load_model(model_filename=settings.separation_model)
    written = separator.separate(str(audio_path))

    if audio_path != source:
        audio_path.unlink(missing_ok=True)

    _rename_outputs(folder, written)

    step("encoding")
    encoding.write_opus_copies(folder)

    step("finding beats")
    beats.detect(tid)

    # Written last on purpose - see tracks.is_ready().
    tracks.write(tracks.Track(id=tid, source=source.name,
                              model=settings.separation_model, stems=STEM_NAMES))
    return tid


def _rename_outputs(folder: Path, written: list[str]) -> None:
    """The model names files "<song>_(Drums)_htdemucs_6s.wav". Rename to a
    plain "Drums.wav" so nothing downstream has to care."""
    for filename in written:
        produced = folder / Path(filename).name
        for name in STEM_NAMES:
            if f"({name})" in produced.name:
                produced.replace(folder / f"{name}.wav")
                break
