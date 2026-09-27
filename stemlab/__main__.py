"""The command line front door.

Its only job is translating typed text into function calls. Keeping it this
thin means the real logic stays testable and reusable - the web server in
Phase 5 will call separate.split() and mixer.render() directly, not this.

  .venv\\Scripts\\python.exe -m stemlab split song.mp3
  .venv\\Scripts\\python.exe -m stemlab mix song.mp3 --vocals 0 --drums 0.1
  .venv\\Scripts\\python.exe -m stemlab list
"""

import argparse
import sys

from . import analyse, mixer, separate, store


def build_parser():
    parser = argparse.ArgumentParser(
        prog="stemlab",
        description="Take a song apart, then practise inside it.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    split_cmd = commands.add_parser("split", help="separate a song into six stems")
    split_cmd.add_argument("song", help="path to an audio file")
    split_cmd.add_argument("--force", action="store_true",
                           help="re-split even if this song is already cached")

    mix_cmd = commands.add_parser("mix", help="blend cached stems into a practice track")
    mix_cmd.add_argument("song", help="path to the same audio file you split")
    mix_cmd.add_argument("--out", default="practice.wav", help="output file")
    # One --vocals / --drums / --bass / ... flag per stem, defaulting to full volume.
    for name in store.STEM_NAMES:
        mix_cmd.add_argument(f"--{name.lower()}", type=float, default=1.0,
                             metavar="GAIN", help=f"{name} volume: 0 = muted, 1 = untouched")

    commands.add_parser("list", help="show which songs have been split")

    analyse_cmd = commands.add_parser("analyse", help="find the beats in a song already split")
    analyse_cmd.add_argument("song", help="path to the audio file")

    serve_cmd = commands.add_parser("serve", help="run the web app")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=8000)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.command == "split":
        separate.split(args.song, force=args.force)

    elif args.command == "mix":
        song_hash = store.hash_file(args.song)
        if not store.is_cached(song_hash):
            sys.exit(f"Not split yet. Run:  python -m stemlab split \"{args.song}\"")

        gains = {name: getattr(args, name.lower()) for name in store.STEM_NAMES}
        print("Gains:", ", ".join(f"{n}={g}" for n, g in gains.items()))

        mixer.render(song_hash, gains, args.out)
        print(f"Wrote {args.out}")

    elif args.command == "analyse":
        song_hash = store.hash_file(args.song)
        if not store.is_cached(song_hash):
            sys.exit(f"Not split yet. Run:  python -m stemlab split \"{args.song}\"")
        found = analyse.analyse(song_hash)
        print(f"{found['tempo']} bpm, {len(found['beats'])} beats -> beats.json")

    elif args.command == "serve":
        from . import server
        server.serve(args.host, args.port)

    elif args.command == "list":
        cached = store.list_cached()
        if not cached:
            print("Nothing split yet.")
        for song_hash, meta in cached:
            print(f"{song_hash}  {meta['model']:<18} {meta['source']}")


if __name__ == "__main__":
    main()
