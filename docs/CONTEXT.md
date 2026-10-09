# CONTEXT — read this first

**Purpose of this file:** hand the full picture to a new chat session (or to
future-me) without re-reading a long conversation. It holds the plan, the
current state, the decisions already made and why, and how the work should be
done.

**Companion file:** `README.md` explains how things *work* — audio concepts,
the models, the maths. This file covers *where we are*, *what was decided*, and
*what to do next*. Read both; start here.

**Source of truth for the plan:** a claude.ai artifact the user owns —
`https://claude.ai/artifact/BGN5cmy6GFXzoJuCQaWZ2S` ("Stem practice app — build
plan"). The full plan is reproduced below, so fetching it is optional.

---

## 1. What is being built

**Woodshed** - a stem separation practice app (renamed from stemlab on 2026-09-28). Feed in a song, an AI model splits it into
per-instrument tracks ("stems"), and then you practise inside the song — mute
the guitar and play that part yourself, drop the drums to 10% and keep time,
solo the vocal to learn a melody, loop four bars at 70% speed.

**The one idea underneath all of it:** the AI runs *once*, up front, to produce
the stems. After that the app is an ordinary music player that happens to have
one volume slider per instrument. "Remove the drums" is multiplying one file by
zero. There is no AI in the playback path at all.

**The project splits in two halves that share almost nothing:**

| | The kitchen | The instrument |
| --- | --- | --- |
| Language | Python | JavaScript |
| Speed | Slow — minutes | Instant |
| Runs | Once per song | Every time a slider moves |
| Needs | A GPU | A browser |
| Job | song → stems + analysis | play stems in sync, mix live |
| Status | **Built (phases 0–3, 5, 7)** | **Built (phases 4, 6, 7)**; 8–9 to go |

---

## 2. How the user wants to work

This matters as much as the technical state. Getting it wrong wastes his time.

- **He is learning by building.** Beginner-to-early-intermediate. He explicitly
  asked that teaching be part of the work: *"teaching with the code is
  important task for you so that i know also exactly whats being done."*
  Explain the concept and the *why*, not just the code.
- **Write Python scripts, not PowerShell wrappers.** He pushed back on a `.ps1`
  file — Python is the project's actual language and teaches something
  transferable.
- **He runs the project code himself.** Write the file, then hand him the
  command. *"whatevr code you are runnign make and write the code, i will run
  it and all okay."* Environment plumbing (pip installs, version checks,
  diagnosing PATH) is still fine to run directly.
- **He pushes back, and he is often right.** When he questioned whether the
  clipping problem was real, measuring it proved him right and me wrong. Prefer
  measuring over theorising.
- **Keep `README.md` updated at the end of every phase**, unprompted. He uses
  it as a study reference and wants to be able to answer any what/why/how
  question about the project.
- **Long setup detours frustrate him.** Keep friction short, explain the cause
  when something breaks.

---

## 3. Environment

**Machine:** Windows 11 · 8 GB RAM (only ~5.9 GB visible to apps, the rest
reserved for integrated AMD graphics) · **NVIDIA RTX 3050 Laptop, 4 GB VRAM**.

**Project folder:** `C:\Users\laksh\OneDrive\Desktop\MusicTeacher`

**Layout (restructured 2026-09-28):** `backend/woodshed/` installed as an
editable package, so the `woodshed` command works from anywhere; `frontend/`
holds the browser player; `docs/` holds this file and README.md; `data/` is
never committed. The old `stemlab/` package, `split_song.py` and
`explore_audio.py` were deleted - they are in git history if ever needed.

**Always invoke Python like this:**

```powershell
.venv\Scripts\python.exe <script or -m module>
```

Not bare `python`. Activation and `PATH` order broke this once and cost real
time — the explicit path works regardless of shell state.

**Verified working stack:** Python 3.12.3 · ffmpeg 9.0.1 · audio-separator
0.47.0 · `torch 2.5.1+cu121` · soundfile 0.14.0 · numpy · librosa · audioread.

**Confirm the GPU before any long run:**

```powershell
.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available())"   # must be True
```

**Critical install-order gotcha:** installing `audio-separator[gpu]` *after* a
CUDA torch build silently replaces it with the CPU-only wheel from the default
package index. **Install CUDA torch last:**

```powershell
.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu121 --force-reinstall --no-deps
```

**If a long run dies with no error and no traceback, re-run it under
`-X faulthandler`** and check `$LASTEXITCODE`:

```powershell
.venv\Scripts\python.exe -X faulthandler -m woodshed split "song.mp3"
$LASTEXITCODE
```

`-1073741819` means a crash inside compiled code, and faulthandler prints the
Python stack that ordinary error handling cannot. This is how the `shifts`
crash was found — see §5.

*(There is no "Windows OOM killer". An earlier version of this file said there
was; that was wrong.)*

---

## 4. Current state — what exists and what is proven

### Built

```
backend/                      installed with `pip install -e backend`
  pyproject.toml              deps + the `woodshed` console command
  woodshed/
    config.py                 every tunable value
    tracks.py                 what a track is, how one is identified
    cli.py                    split / mix / analyse / list / serve
    api/
      app.py                  assembles the app, mounts routers
      deps.py                 shared validation
      routes/                 tracks · stems · analysis · jobs
    audio/
      separation.py           song -> six stems
      encoding.py             ffmpeg: Opus copies, audio out of video
      mixing.py               stems + levels -> one file
      analysis/beats.py       tempo, beats, downbeats - Beat This! on the summed stems
    jobs/registry.py          tickets for work that outlives a request
    storage/{base,local}.py   where files live, behind one interface

frontend/                     React + Vite + TypeScript
  src/
    audio/AudioEngine.ts      ALL the sound. ~330 lines, zero React
    audio/types.ts            StemName, Loop, PlayerState
    api/{client,types}.ts     every call the browser makes
    lib/bars.ts               barStarts(): downbeats, or every Nth beat for old data
    hooks/usePlayer.ts        one engine, its state mirrored into React
    hooks/useKeyboard.ts      space, arrows, 1-6, esc
    components/               Waveform · Transport · Mixer · PracticePanel · Dropzone
    App.tsx                   assembles it
  public/vendor/SignalsmithStretch.mjs    MIT stretcher, WASM + AudioWorklet
  legacy/                     the old vanilla JS player, kept for comparison
  dist/                       `npm run build` output; the backend serves this

docs/README.md                how it all works, phase by phase
docs/CONTEXT.md               this file
data/cache/<id>/              Vocals.wav + .opus (x6), beats.json, meta.json
data/uploads/                 songs as uploaded
songs/                        his own source files
```

### Commands

```powershell
woodshed split "song.mp3"
woodshed mix "song.mp3" --vocals 0 --drums 0.1 --out practice.wav
woodshed analyse "song.mp3"
woodshed list
```

**Running the app in development needs two servers:**

```powershell
woodshed serve              # the API on :8000

cd frontend && npm run dev  # the React app on :5173  <- work here
```

Vite proxies `/tracks`, `/stems` and `/jobs` through to :8000, so the browser
sees one origin and the code uses plain paths that work unchanged in
production. Note Vite binds to IPv6, so use `localhost:5173`, not `127.0.0.1`.

For production: `npm run build` writes `frontend/dist`, and `woodshed serve`
serves it on its own.

### Proven by running it

- Separation quality on the test song (a Bollywood ballad) judged **good enough
  to build on** — the phase 1 go/no-go decision, passed.
- Stems sum back to the original; `rebuilt.wav` matches the record.
- Mixing/muting works and sounds correct.
- CLI argument parsing verified.

- **React front end built** (2026-09-29): TypeScript compiles clean, the
  production build succeeds (~237 KB, 74 KB gzipped), the dev server serves the
  page, all three API routes proxy correctly and the stretcher loads.
  **Nothing audible or visual has been verified** - playback, sync, sliders,
  waveform drawing and drag-to-loop are all still to be checked by ear and eye.
- **Phase 10 code written** (2026-10-05): Beat This! beats + downbeats,
  `lib/bars.ts`, docs. TypeScript compiles clean, and the meter and tempo
  helpers were checked on synthetic grids (4/4 with a pickup, 3/4). Installed
  and checked by him on real songs: bar lines land on "1" and loops snap
  correctly.
- **Phase 7 built** (2026-09-27): waveform, beat detection, bar lines,
  drag-to-loop with snapping, mute/solo, keyboard shortcuts. He confirmed bar
  lines land correctly and looping works. Beat detection measured 83.35 bpm on
  the test song with millisecond-consistent spacing.
- **Phase 6 built** (2026-09-24): Signalsmith Stretch (MIT) on the master bus.
  Verified the library serves correctly and the page loads; **the audio itself
  is unverified** - no way to listen from a tool session. Ask him whether drums
  still sound clean at 70%.
- **Phase 5 verified end to end** (2026-09-23): uploaded a song over HTTP, got a
  job id back instantly, followed the SSE stream through `separating` to `done`
  with the hash, and confirmed stems serve as Opus (37 MB WAV -> 2.3 MB Opus).
  Path-traversal and unknown-hash requests correctly 404.
- **Cache verified end to end** (2026-09-23): `data/cache/28d2c7721b9c3fc9/`
  holds all six stems renamed to plain names plus `meta.json`, and a second
  `split` of the same file returns instantly. Phase 3's formal "done when" is
  met.

### Model in use

`htdemucs_6s` — six stems: Vocals, Drums, Bass, Guitar, Piano, Other. Chosen
over the 4-stem default because practising a *specific instrument* is the point
of the app. Its guitar and especially piano separation is rougher than the core
three; that tradeoff was made knowingly.

Run with **`shifts: 1`** (`DEMUCS_PARAMS` in `separate.py`), not the library
default of `2`. Two passes hold two full-size result buffers at once and crash
this machine with an access violation when RAM is tight. One pass: half the
peak memory, twice as fast, marginally less polished. **Do not raise this
without a reason** — it is a deliberate fix, not an oversight.

**Video input works** (`.mp4`, `.mov`, `.mkv`, `.webm`, `.3gp`, …). ffmpeg
strips the audio to 44.1 kHz stereo before separation; the picture is dropped
and the extracted audio deleted afterwards. The cache key is a hash of the
*original* file as uploaded, not of the extracted audio. Intended use: phone
recordings of his own band — expect rougher separation than a studio track,
because one room mic gives the model far less to work with.

**Downloading from YouTube or Spotify is out of scope** and was declined when
asked. YouTube's terms prohibit it; Spotify audio is DRM-encrypted and there is
no legitimate route to it. The product is a separation tool for files the user
already has. Do not add `yt-dlp` or similar, and do not integrate the
converter sites he mentioned.

**React never touches the audio.** `AudioEngine.ts` is a plain TypeScript
class that owns the graph, the six sources, the stretcher and the loop; it
imports nothing from React. React owns the screen and calls methods on it,
through `usePlayer`. Two consequences that must not be undone:

- *Position never goes through React.* The waveform and clock run their own
  `requestAnimationFrame` and read `engine.position` directly. Only discrete
  changes - playing, levels, loop points - flow through React state. Pushing a
  playhead through state sixty times a second would be waste.
- *The engine is held in a ref and created once.* If React owned the graph it
  would be rebuilt on render and the sample-accurate sync would collapse.

**The stretcher is loaded at runtime from `public/vendor/`,** not bundled - the
import path is held in a variable so TypeScript treats it as a runtime value
rather than a file to resolve at build time. It must be a **full URL**
(`new URL('/vendor/…', location.origin).href`). A bare `/vendor/…` path makes
the Vite dev server add `?import` and then refuse to transform a public file
("Failed to load url /vendor/SignalsmithStretch.mjs"). Fixed 2026-10-05.

**Looping is done by the audio thread, not JavaScript** (`src.loop = true` with
`loopStart`/`loopEnd`). Watching the clock in JS and jumping manually makes the
wrap land late whenever the page is busy - exactly the stumble that makes
looping useless for practice. Don't "simplify" it into a timer.

**Beat detection uses Beat This!** (phase 10, 2026-10-05), a small PyTorch
beat + downbeat network (checkpoint `final0`, `settings.beat_model`). It runs on
the six stems summed back into a mono mix at 22.05 kHz, because it was trained
on full mixes. The meter (`beatsPerBar`) is the median count of beats between
downbeats. Both grids are extended backwards to the song start. The model is
loaded per call and freed (`torch.cuda.empty_cache()`) so it never holds VRAM
that Demucs needs. Install it with `pip install beat-this
rotary-embedding-torch --no-deps` - never without `--no-deps`, or torch may be
swapped for the CPU build. If it cannot be imported, `detect()` falls back to
the old librosa rule on the DRUM stem with assumed 4/4 (`"method": "librosa"`).
`load()` treats a `beats.json` without `downbeats` as missing, so old tracks
re-analyse on first open. madmom was skipped: hard to install on Windows and
Python 3.11+.

**Mute/solo dim the row rather than moving the slider** - the level has to
survive unmuting.

**Speed and pitch (phase 6) - the design is not the obvious one.** Signalsmith
Stretch in *live input* mode ignores `rate` and honours only `semitones` (its
docs say so explicitly). One stretcher must sit after the six stems are summed,
otherwise the volume sliders would have to be baked in before stretching and
would stop being live; six stretchers would cost 6x CPU and could drift.

So: **speed comes from `playbackRate` on the six buffer sources** (resampling,
which drags pitch with it), and **the stretcher corrects the pitch back**:

```js
stretch.schedule({ semitones: userSemitones - 12 * Math.log2(speed) });
```

Position tracking multiplies elapsed time by `speed`, and the speed slider
re-anchors `offset`/`startedAt` before changing rate - otherwise the playhead
corrupts. Do not "simplify" any of this without re-reading why.

Only plain `onnxruntime` is installed, never `onnxruntime-gpu`. The two install
into the same folder and overwrite each other, and Demucs runs on PyTorch and
never uses ONNX anyway. GPU acceleration comes from `torch ... +cu121`.

---

## 5. Decisions already made — do not re-litigate

### Per-stem gain is capped at 1.0. No boost above the original level.

Settled after research and measurement. Three reasons:

1. **Boosting a separated stem amplifies its artifacts.** Stems contain bleed
   and smearing; `×2` doubles the garbage along with the instrument. Turning
   *other* stems down achieves the same prominence without amplifying anything.
2. **`1.0` is a meaningful anchor** — "exactly as loud as it was on the record"
   — because the stems provably sum back to the original. Above `1.0` there is
   no reference.
3. **Loudness is relative**, so boost is never strictly necessary.

Moises (the market leader in this niche) also caps at 100% and defaults tracks
to 75%.

### Clipping is a non-issue here. Measured, not assumed.

Peaks measured across every realistic slider scenario on the test song:

```
everything at 100% (the record)   0.898   ← the record itself has headroom
mute Vocals                       0.924   ← phase cancellation is real but tiny
mute Drums                        0.720
karaoke / drummer / guitarist     all under 0.93
everything at 50%                 0.449
```

**Nothing came close to 1.0.** `np.clip` stays as a one-line safety net that
should never fire. No scaling or normalising logic was added to `mixer.py` —
it would have been solving a problem that does not exist.

*(Note the real finding: muting a stem can slightly **raise** the peak, because
stems partly cancel each other — audio samples are signed, so removing a
negative contribution exposes more of a positive one. Real effect, negligible
magnitude.)*

### The actual level problem, for later

Soloing is *quiet*, not loud:

```
solo Guitar  0.184      solo Piano  0.169      full mix  0.898
```

Soloing the guitar yields roughly one-fifth the level of the full mix (~15 dB
down), so toggling solo on and off means reaching for the volume knob. **This
is a UX issue for the browser player (phase 4+), not a CLI correctness bug.**
Fix it where the sliders are — bring quiet mixes back up automatically. In the
browser this cannot scan ahead for the peak, so use a `DynamicsCompressorNode`
on the master bus as the safety net.

### Cache is keyed by a hash of the file's bytes, not its name

Names lie — files get renamed, and two different songs can both be `track.mp3`.
`meta.json` is written **last**, so its presence marks a split as complete; a
run that dies halfway correctly reads as not-cached instead of silently serving
half a song.

---

## 6. The full plan — all ten phases

Each phase produces something runnable. Nothing is scaffolding to throw away.

### ✅ Phase 0 — Set up the workbench · half a day
Python 3.11+, virtual environment, ffmpeg, audio-separator, git.
**Done when:** `audio-separator --version` and `ffmpeg -version` both print
something.

### ✅ Phase 1 — Split one song and listen hard · 1 hour
Run one well-known song through the model, listen to every stem end to end on
headphones. Listen for **bleed** (traces of the removed instrument) and
smeared artifacts.
**Why first:** the riskiest assumption in the project, testable in an hour. If
the drum stem is clean enough to practise against, there is a product.
**Done when:** you have listened to a full drum stem and made a judgement call.

### ✅ Phase 2 — Learn what audio actually is · half a day
Load stems as arrays, print their shape, mix with different gains, write a
file, and check the stems sum back to the original.
**The lesson:** audio is a list of numbers, 44,100 per second per channel.
Mixing is adding. Volume is multiplying. Mute is multiplying by zero.
**Done when:** you have made a file with the drums quietened and can hear it.

### ✅ Phase 3 — A command-line version of the whole product · 2–3 days
`split` and `mix` commands, sane package structure, caching keyed by file hash.
**Why before the UI:** if the audio logic provably works from the command line,
any later problem is definitively a *browser* problem. Debugging a UI and an
audio pipeline simultaneously is how projects stall.
**Done when:** one command turns a song plus levels into a practice track, and
running it twice is fast the second time.

### ✅ Phase 4 — The browser player
One HTML page, one JS file. Load the stems, play them in perfect sync, one
volume slider each. No server yet — open the file directly.

The browser contains a full audio engine, the **Web Audio API**. You do not
play files with it; you build a *graph* of nodes, like patch cables:

```
drums  → AudioBufferSource → Gain ─┐
bass   → AudioBufferSource → Gain ─┤
vocals → AudioBufferSource → Gain ─┼→ Master Gain → speakers
guitar → AudioBufferSource → Gain ─┤
piano  → AudioBufferSource → Gain ─┤
other  → AudioBufferSource → Gain ─┘
```

```js
const ctx = new AudioContext();

// 1. fetch and decode every stem into memory FIRST
const buffers = await Promise.all(names.map(async name => {
  const res = await fetch(`stems/${name}.opus`);
  return ctx.decodeAudioData(await res.arrayBuffer());
}));

// 2. one source + one gain per stem
const gains = buffers.map(buf => {
  const src = ctx.createBufferSource();
  const gain = ctx.createGain();
  src.buffer = buf;
  src.connect(gain).connect(ctx.destination);
  return { src, gain };
});

// 3. start them all at ONE shared future moment
const t0 = ctx.currentTime + 0.1;
gains.forEach(({ src }) => src.start(t0));

// 4. a slider is now just this
gains[0].gain.gain.value = 0.3;
```

> **The trap that catches everyone:** do **not** use six `<audio>` tags. They
> start when they feel like it and drift apart by tens of milliseconds, which
> sounds like a badly played band. Decode all stems into memory and start them
> at one shared timestamp computed from the **audio clock**, not the browser's
> normal clock.

A buffer source cannot be restarted, so seeking means stopping every source,
creating fresh ones, and starting at a new offset. Write that as one
`seek(seconds)` function early.

**Why mix in the browser at all:** it has to be instant. If a slider meant
asking a server to render a file, every adjustment would take seconds. Mixing
on the listener's machine is free, instant and offline-capable; the server
ships stems once.

**Done when:** six sliders, in sync, and pulling drums to zero leaves a backing
track you would actually play along to.

### ✅ Phase 5 — A server, so the two halves meet
A small FastAPI service with four jobs:

```
POST /tracks           → { job_id }        (returns instantly)
GET  /jobs/{id}/events → progress stream   (server-sent events)
GET  /tracks/{id}      → metadata + stem URLs
GET  /stems/{file}     → the audio itself
```

Separation takes minutes; a normal request would time out and block the server.
So: accept the file, hand back a ticket immediately, do the slow work in a
background worker, let the browser subscribe to progress. **Server-sent
events** are one-way (server → browser), which is all that is needed —
websockets are two-way and more machinery than the job requires.

Start with FastAPI background tasks and SQLite. Move to Redis/Celery only with
more than one worker machine; building the queue first is a classic way to
spend a week on nothing.

**Done when:** drop an mp3 on the page, watch a progress bar, the player
appears by itself.

### ✅ Phase 6 — Speed and pitch, independently
Play at 70% speed in the original key; transpose +2 semitones at full speed.
Slowing a file normally drops its pitch (like a record). Separating the two is
**time-stretching** — cutting audio into short overlapping grains and
re-spacing them.

> **Licence matters.** Rubber Band is best known and has a browser build, but
> it is **GPL** — which obliges open-sourcing anything shipped with it.
> **Signalsmith Stretch** is comparable quality under **MIT**. Decide before
> building it in. **Avoid SoundTouch** — it works in the time domain and
> mangles drum transients.

The stretcher is C++ compiled to **WebAssembly**, hosted in an **AudioWorklet**
(a separate real-time audio thread — the main JS thread pauses for rendering
and garbage collection, and a few milliseconds of pause is an audible click).

```
...all stems → Master Gain → StretchWorklet → speakers
                             ↑ ONE stretcher, not six
```

Put exactly one stretcher on the master bus, after summing. Parallel stretchers
melt phones and drift relative to each other.

**Why two independent controls:** a drummer wants tempo changed and pitch left
alone; a guitarist with a capo wants the reverse; a singer wants the key
dropped. A simple playback-rate change cannot do this.

**Done when:** 70% speed at the original key, and +2 semitones at the original
tempo, neither sounding robotic.

### ✅ Phase 7 — Loops that land on the beat (core done)
Waveform display, draggable loop region, bar numbers, count-in click, and a
trainer that raises a loop from 60% to 100% over repetitions. For any of it to
feel musical the app must know where the beats are:

```python
import librosa
y, sr = librosa.load("drums.wav")
tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
beat_times = librosa.frames_to_time(beats, sr=sr)
```

librosa gives tempo and beats fast; **madmom** is stronger for downbeats (which
beat is the "one") and chords. Save results as JSON next to the stems so the
browser just reads them.

**Practical trick: run beat detection on the drum stem, not the full mix** —
everything else is noise to the detector, and the drum stem already exists.

**Why this is the differentiator:** a loop that starts a fraction of a beat
late is useless for practice — you feel the stumble every time it wraps.
Existing apps mostly do separation well and this part thinly.

**Done when:** you can loop bars 17–20 at 70% speed and it lands on the
downbeat every time.

### ▶ Phase 8 — More instruments than four · **NEXT** · *partly done already*
Chain models rather than replacing them:

```
song
 └─ fast 4-stem split        → playable in ~1 minute
     └─ "deep split" button
         ├─ 6-stem model     → adds guitar, piano   ← already using this
         └─ 53-stem model    → strings, brass, sax, organ, kick, snare, hats…
```

The 53-stem model is BS-RoFormer based and wants ~16 GB VRAM — **far beyond
this machine's 4 GB.** Treat it as an opt-in extra, never the default. No
single model is both fast and fine-grained, so give the cheap split
immediately and make the detailed one an explicit choice.

### Phase 9 — Turn it into something you can hand to someone · open-ended
Two honest paths pulling in opposite directions:

- **Local-first desktop app (Tauri).** Separation runs on the user's machine.
  Costs nothing, uploads nothing, stores nothing — and carries almost no
  copyright exposure. No phone support, and users need a decent computer.
- **Cloud service.** Works on phones and weak laptops. You pay for GPU time,
  store other people's music, and take on real legal responsibility. Rent GPUs
  by the second; fingerprint uploads so a popular song is separated once across
  all users.

> **Legal, read before publishing anything.** YouTube's terms prohibit
> downloading. Every shipping app in this space frames itself as a separation
> tool for files you already own. **Spotify is a hard no** — DRM-protected, no
> legitimate route to the audio. Do not design around it; do not market the app
> as a downloader.

### ▶ Phases 10–13 — The chord finder (started 2026-10-05)
Agreed after research: **no LLM and no agent.** Chords come from automatic
chord estimation (spectrogram → chroma → trained network → smoothing), which is
a fixed pipeline. An LLM is at most an optional "explain this progression"
extra. Website chords are either typed in by people (Ultimate Guitar) or made by
a model like this one (Chordify).

- **10 ✅ Where the bars start** — Beat This! beats + downbeats (see §4).
- **11 Chords** — `audio/analysis/chords.py`, the same detect/load shape.
  Try **BTC** (Bi-directional Transformer, ~170 chord types, PyTorch) first,
  compared against Chordino or autochord. Input is Bass + Other (+ Guitar/Piano)
  stems. Make one chord decision per beat and snap changes to downbeats. Then
  key detection and a "simplify" toggle. Expect about 80% accuracy on
  major/minor and about 65% with 7ths.
- **12 Lyrics + chord sheet (built 2026-10-05).** He wants it to work on *any*
  audio (his own recordings), so lyrics come from **openai-whisper `turbo` on
  the Vocals stem**, not LRCLIB.
  - LRCLIB is left out for now, because it would send song titles off the
    machine. It can come back as an opt-in later.
  - **He wants Roman letters.** Whisper writes Devanagari, and `roman.py`
    converts it to casual Hinglish (schwa deletion). Hindi and Urdu are both
    transcribed as `hi`.
  - The beat-by-beat chart was **dropped at his request** ("too detailed").
    The lyrics sheet is the main view, with a simple per-bar list for
    instrumentals.
- **13 Next:** edit-lyrics mode, key detection and per-song spelling, and
  optional LRCLIB.

---

## 7. Rules that will save weeks

- **Separate once, cache forever**, keyed on a hash of the audio. Cheapest
  optimisation in the system. *(Done in phase 3.)*
- **Check that stems sum back to the original.** If they do not, every level
  you set lies to the user. Build the check into the pipeline, not just phase 2.
- **One stretcher on the master bus.** Never one per stem.
- **Match the input to the analyser.** The old librosa rule wanted the drum stem
  alone. The Beat This! model was trained on full mixes, so it gets the stems
  summed back together. Chord detection will want the harmonic stems.
- **Ship compressed stems (Opus), keep the WAVs.** Six WAV stems is a huge
  download; Opus is ~1/10 the size at transparent quality.
- **Expect bleed and design around it.** An "isolate" mode that ducks the other
  stems is often more useful than full removal, and hides artifacts better.
- **Commit after every phase**, with a message describing what now works.

## 8. What NOT to build

- **Real-time separation.** A live research problem, roughly half the quality.
  Separate once, in advance, forever.
- **Your own model.** Needs many GPUs and multitrack data you do not have.
- **Spotify integration.** No legitimate path to the raw audio.
- **Accounts, payments, mobile apps before phase 7.** None make the product
  better; all can be added later to something that works.

---

## 9. Immediate next steps

**Phase 10 is done and verified (2026-10-05).**

**Phase 11 backend written (2026-10-05).**
- BTC is copied into `audio/analysis/btc/` (MIT; `np.float` fixed; class and
  attribute names untouched so the state dict loads).
- `chords.py` averages frame probabilities per beat and writes `chords.json`
  (`start`/`end`/`label`/`name`).
- Weights auto-download to `data/models/`.
- The CLI prints a bar-by-bar chart with `woodshed chords`, and there is a
  route at `/tracks/{id}/chords`.
- Verified: all state-dict keys match, it runs on CUDA, and synthetic
  C/Am/F/G7 tones came back exactly right.
- **Chord UI built the same day.** `ChordLane` sits under the waveform
  (circle-of-fifths colours; click to seek). `ChordPanel` has a big Now/Next
  with a beat countdown, plus a 4-bars-a-row chart that auto-scrolls (paused
  for 4s after a manual scroll); click a bar to seek, shift-click to loop.
  Names follow the pitch control; Capo and Simple are kept in localStorage via
  `lib/prefs.ts`. Focus mode is the F key. Chords are fetched only after beats
  (avoids a double beat analysis), and `separation.py` runs chords after beats
  inside a try/except so a failure never loses the stems.
- Verified: tsc clean, production build OK, and the `lib/chords.ts` logic
  checked on known inputs. He saw it in the browser and called the chords
  "okayish". The beat chart was too detailed for him, which led to phase 12.
- **Phase 12 built (2026-10-05).**
  - **Backend:**
    - `lyrics.py` runs Whisper turbo on the Vocals stem. Its custom loader
      memory-maps the checkpoint and halves the weights (LayerNorm stays
      fp32): about 1.6 GB of VRAM and a 3.2 GB RAM peak.
    - It detects the language from the loudest 30 s of vocals and uses
      `condition_on_previous_text=False` and
      `hallucination_silence_threshold=2`.
    - It writes `lyrics.json` (lines → words with start/end).
    - `roman.py` matches 29/29 test words.
    - There is a `woodshed lyrics` CLI command and a `/tracks/{id}/lyrics`
      route; `separation.py` runs it after chords, in a try/except.
  - **Frontend:**
    - `lib/sheet.ts` pins chords to words. The word being sung wins, unless
      the next word starts within 0.15 s. A short gap goes to the next word;
      a gap over 2 bars becomes an Intro/Instrumental/Outro line. Each line
      shows its opening chord, dimmed.
    - `LyricSheet.tsx` highlights the current line (0.3 s early) and the sung
      words, scrolls to a third of the way down, and seeks when a word is
      clicked.
    - Loading is chained: beats → chords → lyrics.
  - **Verified:** tsc and the build pass, `sheet.ts` was checked on a made-up
    song, and roman.py on test words.
  - **First real run (2026-10-06) failed.** Auto language detection called
    "Ae Dil Hai Mushkil" English (en 35%, with hi not in the top 5), so Whisper
    wrote English sentences. Fixes:
    - `lyrics_language = "hi"` in config, plus a `--language` CLI flag. Forced
      `hi` is nearly word-perfect.
    - A meta-device loader (`assign=True` from the mmap'd checkpoint; the mask
      and alignment heads are made for real). The 3.2 GB-RAM loader crashed
      with an access violation once the browser and editor were open; now
      RAM use is about zero, VRAM 1.6 GB, peak 2.1 GB.
    - Triton warnings are filtered.
    - Line breaks: Whisper word times have no gaps on sung vocals, so lines
      over 8 words are split at the deepest loudness dip in the vocal stem.
  - The whole 5-minute song took 102 s.
  - **UI simplified at his request (2026-10-06).**
    - Now/Next is removed.
    - Only the current line is highlighted (a band plus an accent bar), with no
      word-by-word or chord flashing; upcoming lines stay readable and past
      lines fade.
    - `lib/tidy.ts`: blips are absorbed, repeats merged by displayed name, at
      most 2 changes per bar. The first version, an on/off switch with a
      max(half bar, 1.5 s) floor (156 → 74), was **too sparse** for him. It is
      now a Chords level: All (156) / **Normal = half a bar, the default**
      (113) / Minimal = plus a 1.5 s floor (74). Saved as pref
      `chordDetail`.
    - The tidied list feeds both the lane and the sheet (`shownChords` in
      App).
  - **Chord placement and smoothing redone (2026-10-06), after research into
    how professional apps work.**
    - **Smoothing:** Viterbi decoding with a chord-change penalty in
      `chords.py` (`CHANGE_PENALTY`: all 0, normal 3, minimal 6). All three
      levels are saved in `chords.json["levels"]`, and old files re-detect.
      The browser `tidy.ts` now only merges chords that look identical.
    - **Line ends:** `lyrics._hold_line_ends` stretches each line's last word
      to where the vocal loudness drops 15 dB below the line level (0.3 s
      quiet, max 8 s, never past the next line). Old lyrics.json files are
      upgraded in `load()` via the `heldEnds` flag.
    - **Placement rules in `sheet.ts`:** during a word → the word; within 1
      beat before → the next word; within 1 bar after a line → that line's
      `tail`; within 1 bar before → the next word; otherwise an instrumental
      line.
  - **Forced alignment done (2026-10-08).** He said the remaining errors were
    mostly in the combining.
    - `lyrics._align` uses torchaudio's `MMS_FA` (weights at
      `data/models/mms`, 1.26 GB of VRAM). It aligns per line, in a window of
      the Whisper span ±1 s, bounded by the neighbouring lines; a failing
      line keeps Whisper's times.
    - **Measured against librosa vocal onsets:** median 0.03–0.04 s off
      (Whisper 0.13–0.14 s); 92% within 0.15 s (Whisper 55%).
    - `_hold_line_ends` now only sets `line["held"]` and no longer stretches
      the word, which had kept the D on "jahaan".
    - The `aligned` flag replaces `heldEnds`; `load()` upgrades old files in
      10–20 s.
    - **`sheet.ts`:** a chord in the last quarter of a word with the next word
      within a beat (+0.15 s) is anticipating that word, and the tail rule
      uses `held`.
  - **Still to do from that research:** an LLM correction and romanisation
    pass (he will decide later, postponed); AcoustID + LRCLIB for released
    songs (opt-in); testing ChordFormer vs BTC.
  - **Don't run two GPU jobs at once** (e.g. the CLI while the server is
    analysing). One transient CUDA error happened, probably from that.
- BTC cannot name inversions.

**Check the React app by ear and eye** - that is the only thing standing
between it and replacing the old player. Same tests as before: six stems in
sync, sliders live, drag-to-loop wrapping cleanly, speed and pitch independent.

**Then delete `frontend/legacy/`** once it is clearly no better than the new
one. It is in git regardless.

**Still open from the agreed stack** (recommended but not built): Postgres +
SQLAlchemy + Alembic, Redis + RQ instead of in-process background tasks,
Cloudflare R2 for files, Modal or RunPod for serverless GPU, Clerk or Supabase
for auth. Order: database and auth first, then jobs and storage, then features.

**Older notes below.**


**Phase 7 still has two optional pieces from the plan:** a count-in click
before a loop starts, and a trainer that raises a loop from ~60% toward 100%
over repetitions. Neither is built; both are small and only worth doing if real
practice shows they are wanted.

**Then phase 8/9.** Phase 8 is largely satisfied already by using the 6-stem
model; the 53-stem model needs ~16 GB VRAM and is out of reach on this machine.
Phase 9 is the ship-it decision: local desktop app (Tauri) versus cloud
service, with the legal notes in §6.

**Older note - confirm phase 6 sounds right** — play at 70% and judge whether drums stay
snappy, and check ±2 semitones. If quality disappoints, the fallbacks are
enabling formant compensation, or narrowing the slider range (the library
documents 0.75x–1.5x as its comfortable range).

**Then phase 7** — beat-aware looping, the differentiator. Detect beats on the
*drum stem* (everything else is noise to the detector, and the stem already
exists), save as JSON beside the stems, and have the browser snap loops to bar
lines. Note that the stretcher adds tens of milliseconds of latency, so a
moving playhead will need to compensate.

Loose ends worth knowing:

- `data/cache/index.json` still gets written by `split`, but the player now uses
  `GET /tracks`. It is harmless, and useful if the CLI is used without the
  server; drop it if it ever gets in the way.
- Job state is in memory, so a server restart forgets in-flight jobs. Finished
  splits survive on disk, so this only matters mid-separation.
- Progress is reported as stages (`queued` / `separating` / `done`), not
  percentages — the model gives no readable progress signal. Do not invent one.
- Songs longer than ~5 minutes fail on the GPU: Demucs allocates one buffer for
  the whole track (~2 GB for 16 minutes) and 4 GB of VRAM is not enough. A
  16-minute phone video hit this. Workaround is trimming with ffmpeg; the real
  fix is splitting long audio into overlapping segments and crossfading the
  stems back together. Not built yet — he chose to move on.

---

## 10. Glossary

| Term | Meaning |
| --- | --- |
| **Stem** | An audio file containing one instrument, pulled out of a finished mix |
| **Source separation / demixing** | The task of producing stems from a mix. Two names for one thing |
| **Model / checkpoint** | The trained AI file that does the separating. You download it; you do not make it |
| **Demucs / Spleeter / RoFormer** | Specific models. Spleeter (2019) is audibly behind; Demucs is the dependable default; RoFormer is the current best |
| **SDR** | A decibel score for separation cleanliness. ~10 is good, ~5 is rough. Good for comparing models, not for predicting how it sounds |
| **Bleed** | Traces of one instrument left in another stem. The main quality problem |
| **Sample rate** | How many numbers describe one second of audio. 44,100 is the CD standard |
| **Gain** | Volume as a multiplier. `1.0` unchanged, `0` silent |
| **Clipping** | Values beyond ±1.0 chopped flat — harsh distortion, not loudness |
| **Audio graph** | Sound sources connected through processing nodes to the speakers, like patch cables |
| **AudioWorklet** | A separate real-time audio thread in the browser, so page activity cannot cause clicks |
| **WebAssembly** | Compiled C++ running in the browser at near-native speed |
| **Time-stretching** | Changing speed without changing pitch, or the reverse |
| **GPU / VRAM** | The chip the AI runs on and its memory. VRAM limits how much audio fits at once |
| **Chunking** | Processing a long song in overlapping windows, crossfaded back together |
