"""The command line.

Its only job is turning typed text into calls. Keeping it this thin is what
lets the web API and the CLI share exactly the same code underneath.
"""

import argparse
import sys

from . import tracks
from .audio import mixing, separation
from .audio.analysis import beats, chords, lyrics
from .config import STEM_NAMES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="woodshed",
                                     description="Take a song apart, then practise inside it.")
    commands = parser.add_subparsers(dest="command", required=True)

    split = commands.add_parser("split", help="separate a song into stems")
    split.add_argument("song")
    split.add_argument("--force", action="store_true", help="re-split even if already done")

    mix = commands.add_parser("mix", help="blend stems into a practice track")
    mix.add_argument("song")
    mix.add_argument("--out", default="practice.wav")
    for name in STEM_NAMES:
        mix.add_argument(f"--{name.lower()}", type=float, default=1.0, metavar="GAIN",
                         help=f"{name} level: 0 = silent, 1 = untouched")

    analyse = commands.add_parser("analyse", help="find the beats and bars in a song already split")
    analyse.add_argument("song")

    chord = commands.add_parser("chords", help="find the chords in a song already split, bar by bar")
    chord.add_argument("song")
    chord.add_argument("--full-mix", action="store_true",
                       help="let the model hear every stem, vocals and drums too, to compare")

    words = commands.add_parser("lyrics", help="transcribe the vocals of a song already split")
    words.add_argument("song")
    words.add_argument("--language", metavar="CODE",
                       help='what is sung: "hi", "en", ... or "auto" (default from config)')

    commands.add_parser("list", help="show what has been processed")

    serve = commands.add_parser("serve", help="run the web app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    return parser


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)

    if args.command == "split":
        track_id = separation.separate(args.song, force=args.force,
                                       on_step=lambda step: print(f"  {step}"))
        print(f"done -> {track_id}")

    elif args.command == "mix":
        track_id = _require(args.song)
        gains = {name: getattr(args, name.lower()) for name in STEM_NAMES}
        print("Levels:", ", ".join(f"{n}={g}" for n, g in gains.items()))
        mixing.render(track_id, gains, args.out)
        print(f"wrote {args.out}")

    elif args.command == "analyse":
        found = beats.detect(_require(args.song))
        print(f"{found['tempo']} bpm, {found['beatsPerBar']} beats per bar, "
              f"{len(found['downbeats'])} bars  ({found['method']})")

    elif args.command == "chords":
        track_id = _require(args.song)
        found = chords.detect(track_id, STEM_NAMES if args.full_mix else None)
        grid = beats.load(track_id) or beats.detect(track_id)
        print(f"heard: {', '.join(found['stems'])}\n")
        print(chords.chart(grid, found))

    elif args.command == "lyrics":
        found = lyrics.detect(_require(args.song), args.language)
        print(f"language: {found['language']}  ({found['method']})\n")
        for line in found["lines"]:
            minutes, seconds = divmod(int(line["start"]), 60)
            print(f"  {minutes}:{seconds:02d}  " + " ".join(w["text"] for w in line["words"]))

    elif args.command == "list":
        found = tracks.all_ready()
        if not found:
            print("Nothing processed yet.")
        for track in found:
            print(f"{track.id}  {track.model:<18} {track.source}")

    elif args.command == "serve":
        import uvicorn
        from .api import app
        print(f"woodshed running at http://{args.host}:{args.port}")
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


def _require(song: str) -> str:
    track_id = tracks.track_id(song)
    if not tracks.is_ready(track_id):
        sys.exit(f'Not split yet. Run:  python -m woodshed split "{song}"')
    return track_id
