# Section 0: The big picture

[← Index](README.md) · Next: [Section 1, Upload and processing →](01-upload-and-processing.md)

## The project in one sentence

**Woodshed** is a music practice app. You give it any song (MP3 or video). It
separates the song into six instruments, finds the beats, chords and lyrics,
and gives you a player where you can mute or solo instruments, slow the song
down without changing its pitch, loop bars, and read a scrolling chord sheet
with lyrics, karaoke-style.

**A resume line you could use:**

> Built a full-stack AI music-practice app (Python/FastAPI + React/TypeScript)
> that separates songs into instrument stems (Demucs), detects beats (Beat
> This!), chords (BTC transformer with Viterbi smoothing) and lyrics (Whisper +
> MMS forced alignment, Gemini-assisted correction verified against audio), and
> renders a synced chord sheet, all running locally on a 4 GB laptop GPU.

## The one idea underneath everything

```
A song is a smoothie: drums, bass, guitar, voice blended together.
An AI model "un-blends" it ONCE → 6 separate audio files ("stems").
After that, everything you do is simple arithmetic:
   "drums at 30%"  = multiply every drum sample by 0.3
   "play together" = add the stems up
```

That is why the system has **two halves** that share almost nothing:

```
┌────────────────────────────────────┐          ┌────────────────────────────────┐
│ THE KITCHEN (backend, Python)      │  files   │ THE INSTRUMENT (frontend, TS)  │
│ slow · needs a GPU · once per song │ ───────► │ instant · runs in the browser  │
│                                    │          │                                │
│ song → 6 stems, beats, chords,     │          │ plays 6 stems in sync, mixes   │
│ lyrics (saved as files)            │          │ live, loops, chord sheet       │
└────────────────────────────────────┘          └────────────────────────────────┘
```

**Why split it like this:** the slow AI part needs a GPU and takes minutes. The
player must react within milliseconds when you move a slider. So the AI runs
once and saves its results as files, and the browser does the live part.

## The tech stack, and why each piece

| Layer | What we used | Why this, and not something else |
| --- | --- | --- |
| Backend language | **Python** | Every serious audio and ML library is Python-first (PyTorch, librosa, Demucs, Whisper) |
| Web server | **FastAPI** | Modern and fast; built-in request validation (Pydantic); simple background tasks and streaming. Flask is simpler but needs more add-ons; Django is heavy for an API |
| ML runtime | **PyTorch (CUDA build)** | All our models are PyTorch; CUDA uses the GPU |
| Stem separation | **Demucs `htdemucs_6s`** via `audio-separator` | A strong open model with 6 stems (including guitar and piano) |
| Beats | **Beat This!** (2024) | A neural beat and downbeat model, better than librosa's rule-based tracker |
| Chords | **BTC** (2019 transformer) + our **Viterbi** smoothing | Open, small, 170 chord types; the smoothing removes flicker |
| Lyrics | **Whisper turbo** + **MMS forced aligner** | Whisper writes the words; MMS times them about 4× more precisely |
| AI correction | **Gemini 3.8 Flash** | Can listen to audio; you have a key; verified by our own audio check |
| Audio tools | **ffmpeg**, **librosa**, **soundfile** | Decoding and encoding; analysis; reading and writing WAV |
| Frontend | **React + TypeScript + Vite** | React for the UI; TypeScript catches mistakes; Vite gives a fast dev server |
| Browser audio | **Web Audio API** + **Signalsmith Stretch** (WASM) | Sample-accurate playback and mixing; speed without pitch change |

## Folder map

```
MusicTeacher/
├── backend/woodshed/          ← Python package (the kitchen)
│   ├── config.py              ← every setting in one place
│   ├── tracks.py              ← what a "track" is, how it's identified (hash)
│   ├── cli.py                 ← terminal commands (split, lyrics, polish…)
│   ├── api/                   ← web layer ONLY (no logic)
│   │   ├── app.py             ← assembles the FastAPI app
│   │   ├── deps.py            ← shared validation (is this a real track?)
│   │   └── routes/            ← tracks.py, stems.py, analysis.py, jobs.py
│   ├── audio/                 ← the real work (knows nothing about HTTP)
│   │   ├── separation.py      ← song → 6 stems (+ triggers analysis)
│   │   ├── encoding.py        ← ffmpeg: decode, Opus copies, MP3
│   │   ├── mixing.py          ← stems × levels → one file (CLI)
│   │   └── analysis/          ← beats.py, chords.py, lyrics.py, roman.py, btc/
│   ├── ai/                    ← gemini.py (provider), polish.py (lyric fixing)
│   ├── jobs/registry.py       ← tickets for long-running work
│   └── storage/               ← base.py (the rules), local.py (disk)
├── frontend/src/              ← React app (the instrument)
│   ├── audio/AudioEngine.ts   ← ALL sound, no React
│   ├── api/                   ← client.ts (every server call), types.ts
│   ├── components/            ← Waveform, Transport, Mixer, ChordPanel, LyricSheet…
│   ├── lib/                   ← pure logic: chords.ts, sheet.ts, bars.ts, tidy.ts
│   └── App.tsx                ← wires it all together
├── data/                      ← NOT in git: uploads/, cache/<track-id>/, models/
└── docs/                      ← README.md (the "why"), CONTEXT.md (state), deep-dive/
```

## The architecture rules

These are good to quote in an interview, because they show design thinking:

1. **Routes contain no logic.** `api/routes/*` validates input, calls into
   `audio/`, and shapes the response. That is why the terminal commands (CLI)
   and the web app share all the real code.
2. **`audio/` knows nothing about the web.** No HTTP objects, so it could run
   on a separate worker machine unchanged.
3. **Files are only reached through `storage/`.** Moving to cloud storage (S3)
   later means changing one class.
4. **`config.py` holds every tunable value.** No hardcoded paths or model names
   anywhere else.

## Likely interview questions

1. **"What does your project do, in 30 seconds?"** It turns any song into a
   practice session: AI separates the instruments, finds beats, chords and
   lyrics, and a browser player lets you mute, slow down, loop and read a synced
   chord sheet.
2. **"Why is it split into a backend and a frontend like that?"** The AI work
   is slow and needs a GPU, so it runs once per song and saves files. Live
   mixing must react in milliseconds, so it runs in the browser on those files.
3. **"How is the backend organised?"** In layers: thin web routes, an `audio/`
   layer with all the real work, a storage interface, and one config file. The
   CLI and the web API share the same code underneath.
