# Woodshed

Take a song apart, then practise inside it.

Feed in any song. An AI model splits it into six separate tracks — vocals,
drums, bass, guitar, piano and everything else — and you practise inside it:
mute the guitar and play that part yourself, slow a solo to 70% without it
dropping in key, loop four bars until they are clean.

## Run it

Setting up needs a few steps in a specific order (the GPU build of PyTorch has
to be installed last), so follow **[SETUP.md](SETUP.md)**. In short, once
installed:

```powershell
woodshed serve                 # terminal 1: the backend, on :8000
cd frontend; npm run dev       # terminal 2: the app, on :5173
```

Then open http://localhost:5173

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
