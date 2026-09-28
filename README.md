# Woodshed

Take a song apart, then practise inside it.

Feed in any song. An AI model splits it into six separate tracks — vocals,
drums, bass, guitar, piano and everything else — and you practise inside it:
mute the guitar and play that part yourself, slow a solo to 70% without it
dropping in key, loop four bars until they are clean.

## Run it

```powershell
pip install -e backend
woodshed serve
```

Then open http://127.0.0.1:8000

## Layout

```
backend/    the Python app - separation, analysis, the HTTP API
frontend/   the browser player - audio graph, mixer, waveform, looping
docs/       how it works, and why
data/       tracks and uploads (not in version control)
```

## Documentation

- **[docs/README.md](docs/README.md)** — how everything works and why each
  decision was made, phase by phase. Start here.
- **[docs/CONTEXT.md](docs/CONTEXT.md)** — current state, remaining plan, and
  decisions already settled.
