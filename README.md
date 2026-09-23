# stemlab

Take a song apart, then practise inside it.

Feed in any song, get back separate audio tracks — one per instrument — then
mute, quieten or isolate any of them. Mute the guitar and play the guitar part
yourself. Drop the drums to 10% and keep time with what's left. Solo the vocal
to learn a melody.

This README is the project's full reference: what was built, why each decision
was made, and how every piece works. It is updated at the end of every phase.

> **Picking up this project fresh?** Read [`CONTEXT.md`](CONTEXT.md) first — it
> holds the current state, the full ten-phase plan, and the decisions already
> settled. This README explains how things *work*; that file explains *where we
> are*.

---

## Table of contents

1. [The one idea underneath all of it](#1-the-one-idea-underneath-all-of-it)
2. [Architecture: two halves](#2-architecture-two-halves)
3. [Setup](#3-setup)
4. [Usage](#4-usage)
5. [Phase log — what was built and why](#5-phase-log--what-was-built-and-why)
6. [Concept reference](#6-concept-reference)
7. [Problems hit, and what actually caused them](#7-problems-hit-and-what-actually-caused-them)
8. [Project layout](#8-project-layout)
9. [Roadmap](#9-roadmap)

---

## 1. The one idea underneath all of it

A song is a smoothie. Drums, bass, guitar and voice were blended into one
liquid, and normally you cannot get the strawberry back out.

There are now AI models that can un-blend it: feed in one mixed song, get back
separate files, one per instrument. Each of those files is called a **stem**.

Everything else follows from that single fact:

| What the user does | What is actually happening |
| --- | --- |
| "Remove the drums" | Multiply the drums file by `0` |
| "Drums at 30%" | Multiply the drums file by `0.3` |
| "Play everything together" | Add the files together |

**No AI is involved in any of those steps.** The AI runs exactly once, up
front, to produce the stems. After that the app is an ordinary music player
that happens to have one volume slider per instrument.

---

## 2. Architecture: two halves

The project splits cleanly in two. They have almost nothing in common and are
worth holding apart in your head.

```
┌─────────────────────────────┐        ┌──────────────────────────────┐
│  THE KITCHEN                │        │  THE INSTRUMENT              │
│  Python · slow · runs once  │──────▶ │  JavaScript · instant        │
│  per song · needs a GPU     │ stems  │  runs in the browser         │
│                             │        │                              │
│  song.mp3 → 6 stem files    │        │  plays stems in sync,        │
│  + analysis (tempo, key)    │        │  mixes them live             │
└─────────────────────────────┘        └──────────────────────────────┘
        built in phases 0–3                built in phases 4–9
```

- **The kitchen** is mostly gluing other people's libraries together. Slow,
  heavy, runs once per song. This is what currently exists.
- **The instrument** is where the actual product lives, and where most of the
  remaining time goes. Not built yet.

**Why the mixing happens in the browser and not on the server:** mixing has to
feel instant. If moving a slider meant asking a server to render a new file,
every adjustment would take seconds and the app would be unusable. Doing the
arithmetic on the listener's own machine makes it free, instant and
offline-capable. The server only ever ships the stems once.

---

## 3. Setup

### Requirements

- Python 3.11+ (this project runs 3.12.3)
- ffmpeg on `PATH`
- An NVIDIA GPU is strongly recommended — see
  [why GPU matters](#why-a-gpu-matters-here)

### Install

```powershell
# 1. ffmpeg
winget install ffmpeg
#    then open a NEW terminal so PATH updates take effect

# 2. Python environment
python -m venv .venv
.venv\Scripts\python.exe -m pip install "audio-separator[gpu]" soundfile numpy librosa audioread

# 3. CUDA-enabled PyTorch — must be installed LAST, see the gotcha below
.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu121 --force-reinstall --no-deps

# 4. Drop the GPU build of ONNX Runtime — Demucs never uses it, and it
#    conflicts with the plain build (they share one folder)
.venv\Scripts\python.exe -m pip uninstall -y onnxruntime-gpu onnxruntime
.venv\Scripts\python.exe -m pip install onnxruntime
```

### Verify

```powershell
ffmpeg -version
.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available())"   # must print True
.venv\Scripts\python.exe -m stemlab --help
```

> **Always call `.venv\Scripts\python.exe` explicitly** rather than bare
> `python`. It works regardless of whether the virtual environment is activated
> or what order `PATH` happens to be in — a failure mode that has already cost
> this project time once.

---

## 4. Usage

```powershell
# Split a song into six stems (slow the first time, instant afterwards)
.venv\Scripts\python.exe -m stemlab split "song.mp3"

# Karaoke track: vocals gone
.venv\Scripts\python.exe -m stemlab mix "song.mp3" --vocals 0 --out karaoke.wav

# Drummer's practice track: drums gone, everything else intact
.venv\Scripts\python.exe -m stemlab mix "song.mp3" --drums 0 --out no_drums.wav

# Isolate the guitar to learn a part
.venv\Scripts\python.exe -m stemlab mix "song.mp3" --vocals 0 --drums 0 --bass 0 --piano 0 --other 0 --out guitar_only.wav

# What's been split already?
.venv\Scripts\python.exe -m stemlab list
```

Every stem flag takes a number: `0` = muted, `0.5` = half, `1` = untouched
(the default). Unspecified stems stay at `1`.

---

## 5. Phase log — what was built and why

### Phase 0 — Set up the workbench ✅

Installed the toolchain. Nothing to show for it, and that is normal.

| Piece | What it is | Why it is needed |
| --- | --- | --- |
| **Virtual environment** (`.venv/`) | A private box of Python libraries for this project only | Without it, every Python project on the machine shares one pile of packages, and upgrading something for project B silently breaks project A |
| **ffmpeg** | The universal audio/video converter | Almost every audio tool secretly calls it. It decodes mp3 into the raw uncompressed form the model needs, and will later compress stems for the browser |
| **git** | Undo history for the whole project | You will break something and not remember what you changed |
| **audio-separator** | Python package wrapping the separation models | Handles model downloading, chunking, and audio I/O so none of that has to be written by hand |

**Done when:** `ffmpeg -version` and `audio-separator --version` both print
something instead of "command not found".

---

### Phase 1 — Split one song and listen hard ✅

Ran one known song through the model and listened to every stem end to end.

**Why this came before anything else:** it is the riskiest assumption in the
entire project and it costs one hour to test. If the drum stem is clean enough
to genuinely practise against, there is a product. If the artifacts are
maddening, that is worth learning now rather than after six weeks of building
a player for it.

**What to listen for:**

- **Bleed** — traces of a removed instrument still faintly audible in another
  stem. Muting the drums does not leave silence; it can leave a ghost of
  cymbals smeared into "Other".
- **Artifacts** — watery, smeared or phasey sounds where an instrument used to
  be. Most audible on cymbals and reverb tails.

**Verdict on this project's test song:** quality judged good enough to build
on.

**Output:** `split_song.py` — the original single-purpose script. Superseded by
the `stemlab` package in Phase 3, kept for reference.

---

### Phase 2 — Learn what audio actually is ✅

The concept everything else rests on. Wrote `explore_audio.py`, which does
three things.

**Part 1 — look at the numbers.** Loads each stem and prints its shape:

```
shape       : (10584000, 2)   <- (number of samples, channels)
sample rate : 44100 Hz        <- numbers per second, per channel
value range : -0.982 to +0.979
```

Then prints eight raw consecutive samples so the abstraction becomes something
observed rather than something claimed.

**Part 2 — mixing is arithmetic.** Applies one gain per stem, sums them,
clips, writes `practice.wav`:

```python
mix = sum(stems[name] * gain for name, gain in gains.items())
mix = np.clip(mix, -1.0, 1.0)
```

That single expression is the entire product. The browser player in Phase 4
does exactly this, just continuously while a slider moves instead of once into
a file.

**Part 3 — the residual check.** Adds all six stems back together, subtracts
the original song, and reports what is left over. Also writes `rebuilt.wav`
(all stems at 100%) so the same check can be made by ear.

**Why the residual matters:** if the stems add back up to something very close
to the original, then every slider at 100% gives back the record, and the
volume controls behave the way a listener expects. If they do not, the model
is losing or inventing energy, and a stem at 100% will not sound like the
original.

---

### Phase 3 — A command-line version of the whole product ✅

Turned two hardcoded scripts into a real tool: the complete product, minus the
interface.

**What changed:**

| Before | After |
| --- | --- |
| Song path hardcoded in the script | `split <any file>` |
| Gains hardcoded, edit-and-rerun to change | `mix song.mp3 --drums 0.1 --vocals 0` |
| Re-splitting the same song wasted minutes | Already-split songs are recognised instantly |
| Two disconnected scripts | One tool, three commands |

**Why this came before the browser player** — two reasons:

1. **Debuggability.** Once the audio logic provably works from the command
   line, any problem in the browser is definitively a *browser* problem.
   Debugging a UI and an audio pipeline at the same time is how projects stall.
2. **Caching.** Separation is the only slow step in the entire system. Doing it
   twice for the same song is the single biggest waste that could be designed
   in, and it is far easier to build now than to retrofit.

**The four modules, and why they are separate:**

- **`store.py`** — the bookkeeper. Hashing, cache paths, "has this been done?".
  Knows nothing about audio.
- **`separate.py`** — song in, six stems out. The slow half.
- **`mixer.py`** — stems plus gains, one file out. The fast half.
- **`__main__.py`** — the front door. Only translates typed text into function
  calls.

That last split matters for what comes next: the web server in Phase 5 will
call `separate.split()` and `mixer.render()` directly. If the logic lived
inside the CLI parsing code, it would have to be rewritten to be reused.

**Two design decisions:**

**Cache keyed by file hash, not filename.** Names lie — a file can be renamed,
and two different songs can both be called `track.mp3`. A hash is computed from
the actual bytes, so identical audio always lands in the same cache folder and
different audio never collides. Rename the mp3 and the cache still hits.

**`meta.json` is written last.** Its presence is what marks a split as
complete. If a run dies halfway through (this machine has OOM-killed one
before), the folder holds some stems but no `meta.json`, so it correctly reads
as *not cached* and gets redone rather than silently serving half a song.

**Done when:** one command turns a song plus a set of levels into a practice
track, and running it a second time is fast.

---

## 6. Concept reference

### What is a stem?

An audio file containing one isolated part of a recording — just the drums,
just the vocals. In a professional studio these exist naturally, because each
instrument was recorded to its own track before being mixed together. For a
finished commercial song they no longer exist publicly, which is why they have
to be reconstructed by a model.

### How does the separation model actually work?

The model used here is **HTDemucs** (Hybrid Transformer Demucs), developed by
Meta's AI research group. Trained on datasets of songs where both the final mix
*and* the true isolated stems were available (principally MUSDB18), it learned
the statistical relationship between "what a full mix looks like" and "what its
drum track looks like".

"Hybrid" refers to it analysing audio two ways at once:

- **Waveform domain** — the raw sequence of sample values over time. Good for
  sharp transients like a snare hit.
- **Spectrogram domain** — the audio converted into a picture of which
  frequencies are present at each moment. Good for sustained, pitched content
  like a held vocal note.

Those two views are processed in parallel and combined, which is why it handles
both percussive and melodic material reasonably well.

**What it does not do:** understand music. It has no concept of rhythm, key or
song structure. It is pattern matching learned from examples, which is exactly
why it produces artifacts on anything unlike its training data.

### Model variants, and the tradeoffs

| Model | Stems | Cost | Notes |
| --- | --- | --- | --- |
| `htdemucs` | 4 | 1× | Vocals, Drums, Bass, Other. The dependable default |
| `htdemucs_ft` | 4 | ~4× | Same four stems, but four separately fine-tuned models run back to back — one specialised per stem. Noticeably cleaner, much slower |
| `htdemucs_6s` | 6 | ~1.5× | Adds Guitar and Piano. **Currently used by this project** |

**Why `htdemucs_6s` despite the caveats:** practising a specific instrument is
the point of the app, so having Guitar and Piano as separate stems is worth
more than a marginal quality gain on the core four. Its guitar and especially
its piano separation is rougher than the core Vocals/Drums/Bass split, since
those two sources had less training data.

**What "Other" contains:** everything the model could not assign to a named
stem — strings, synths, horns, background texture. It is the leftovers bucket,
not an instrument.

### Sample rate, samples, channels

A speaker makes sound by moving a cone in and out. Audio is a record of where
that cone should be, measured **44,100 times per second**:

- `0.0` = at rest (silence)
- `+1.0` = pushed fully out
- `-1.0` = pulled fully in

So a four-minute stereo song is roughly 10.5 million numbers per channel. A
`.wav` file is essentially that list written to disk with a small header.

- **Sample rate (44,100 Hz)** — measurements per second. Analogous to frames
  per second in video: enough still images shown fast enough become motion;
  enough cone positions played fast enough become music. 44.1 kHz is the CD
  standard, chosen because human hearing tops out around 20 kHz and capturing a
  frequency requires sampling at more than twice that rate.
- **Channels (2)** — one list for the left speaker, one for the right. That is
  what stereo means. Arrays here have shape `(samples, 2)`.

### Why mixing is addition

When two instruments play at once in a room, their pressure waves physically
add together before reaching your ear. Digital audio models the same thing:
adding the sample values of two stems gives the sound of both playing
simultaneously. This is not an approximation — it is how waves actually
combine.

### Gain, and why 0.3 is not "30% quieter"

A gain is a multiplier applied to every sample. `0.3` means every number
becomes 30% of its original value — that is 30% of the **amplitude**.

Loudness perception is logarithmic, not linear, so the ear does not hear "30%
as loud":

| Gain | In decibels | Roughly sounds like |
| --- | --- | --- |
| `1.0` | 0 dB | Unchanged |
| `0.5` | −6 dB | Noticeably quieter |
| `0.3` | −10 dB | About half as loud |
| `0.1` | −20 dB | About a quarter as loud |
| `0.0` | −∞ | Silent — mathematically impossible to hear |

That `0.0` row is worth knowing: it is the cleanest possible A/B test. If a
"muted" instrument is still audible, no slider value will remove it — the sound
is bleeding in from another stem.

### Clipping

Since mixing adds values, sums can exceed ±1.0. But the speaker cone cannot
travel past fully extended, so anything beyond gets flattened — which sounds
like harsh crackling distortion, not extra loudness. `np.clip(mix, -1, 1)`
forces values back into range explicitly rather than leaving the behaviour to
chance.

### Hashing

A hash function takes any amount of data and reduces it to a fixed-size
fingerprint:

```
'hello' → 2cf24dba5fb0a30e
'hellp' → fdd7585e08c4e2af      # one letter changed, entirely different result
```

Three properties make it the right cache key:

1. **Deterministic** — the same bytes always produce the same fingerprint.
2. **Sensitive** — change one byte anywhere and the fingerprint changes
   completely. Two files cannot be "nearly" the same hash.
3. **One-way** — the original cannot be reconstructed from the hash.

The implementation reads the file in 1 MB chunks rather than all at once. For a
7 MB mp3 that hardly matters, but stem `.wav` files run past 50 MB each, and
loading whole files into memory is a habit that bites hard on a machine with
limited RAM.

### `shifts` — separating the same song more than once

Demucs can separate a song several times, each at a slightly different time
offset, then average the results. Small random misalignments in the model's
output cancel out, so the stems come back marginally cleaner. The library
default is `2`.

The cost is memory: each pass needs its own full-size result buffer, and they
are held simultaneously. **This project uses `shifts: 1`** — one pass, half the
peak memory, roughly twice as fast. On an 8 GB machine that is the difference
between finishing and crashing, and the quality difference is small.

### Why a GPU matters here

Neural networks are mostly large matrix multiplications. A CPU has a handful of
powerful cores; a GPU has thousands of simple ones, which suits that work far
better — often 10–20× faster here.

The second benefit is memory. This machine has 8 GB of system RAM (only ~5.9 GB
visible to applications, the rest reserved for integrated graphics). Running
the model on the CPU makes it compete for that same pool; running it on the
GPU's dedicated 4 GB of VRAM sidesteps the contest.

Note what the GPU does **not** solve. It holds the model and whichever chunk of
audio is being processed, but each finished chunk is written back into ordinary
RAM, where the full-length result is assembled. That assembly is what ran out
of room and crashed — see the `shifts` note above and the crash writeup in
§7. VRAM and RAM are separate pools doing separate jobs; neither substitutes
for the other.

**Current setup:** NVIDIA RTX 3050 Laptop (4 GB VRAM), `torch 2.5.1+cu121`,
driver supporting CUDA 12.5.

---

## 7. Problems hit, and what actually caused them

Worth keeping, because each one has a general lesson.

### `ModuleNotFoundError: No module named 'audioread'`

A transitive dependency that should have been pulled in automatically was not.
Fixed with `pip install audioread`.

**Lesson:** a missing module deep inside a library's own imports usually means
an incomplete dependency spec, not a mistake in your code.

### `FFmpeg is not installed` — despite having just installed it

Installers modify the `PATH` environment variable, but already-open terminals
keep the copy they started with. The fix is a new terminal, or reloading `PATH`
in the current one.

**Lesson:** "installed but not found" almost always means a stale `PATH`.

### `ModuleNotFoundError: No module named 'audio_separator'` — right after it had worked

This one was self-inflicted. Reloading `PATH` with

```powershell
$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + ...
```

**replaces** the entire `PATH`, which wiped out the entry that virtual
environment activation had prepended. So bare `python` silently fell back to
the system install, which had none of the project's packages.

**Lesson:** call `.venv\Scripts\python.exe` explicitly and this whole category
of problem disappears.

### The process vanished mid-run, with no error and no traceback

Separation reached `52/52`, then the process disappeared — no exception, no
message, just a returned prompt and an empty cache folder.

Running it under `-X faulthandler` turned the silent death into a real report:

```
Windows fatal exception: access violation
  File ".../demucs/apply.py", line 217 in apply_model
$LASTEXITCODE → -1073741819
```

Exit code `-1073741819` is `0xC0000005`, an access violation — a crash inside
compiled code, which ordinary Python error handling never sees.

**The cause:** Demucs defaults to `shifts: 2`, meaning it separates the whole
song twice at slightly different time offsets and averages the results for a
small quality gain. Line 217 is where the *second* pass allocates its own
~500MB result buffer while the first pass's buffer is still held. With only
0.64 GB of RAM free, that allocation failed — and failed as a hard crash
rather than a clean `MemoryError`.

**Fix:** `shifts: 1` in `separate.py`. One pass, half the peak memory, about
twice as fast, marginally less polished output.

**Lesson:** `python -X faulthandler` is the tool for a process that dies
without a traceback. It prints a Python stack even when the crash happens
inside a C/C++ library. Pair it with `$LASTEXITCODE` to distinguish a crash
(`-1073741819`) from a clean exit.

*(An earlier version of this file blamed a "Windows out-of-memory killer".
That was wrong — Windows has no such thing, and the run being blamed had
actually completed. The real cause is the one above.)*

### Both `onnxruntime` and `onnxruntime-gpu` installed at once

`audio-separator[gpu]` pulls in `onnxruntime-gpu`, which installs into the
**same folder** as plain `onnxruntime`, so the two overwrite each other. The
GPU build also tried to load CUDA 13 libraries into a process already holding
PyTorch's CUDA 12 ones:

```
WARNING: onnxruntime-gpu is built with CUDA 13.x ...
Failed to load cublas64_13.dll
```

This turned out **not** to be the cause of the crash above, but it is a
genuinely broken state worth clearing. Demucs runs on PyTorch and never touches
ONNX Runtime — that is only used by the MDX and VR model families — so the
plain CPU build is all that is needed:

```powershell
.venv\Scripts\python.exe -m pip uninstall -y onnxruntime-gpu onnxruntime
.venv\Scripts\python.exe -m pip install onnxruntime
```

**Lesson:** two packages that install into one namespace cannot coexist. And a
plausible suspect is not a confirmed cause — this one was ruled out by testing,
not by argument.

### `torch.cuda.is_available()` returned `False` after installing the CUDA build

Install order. `pip install "audio-separator[gpu]"` ran *after* the CUDA
PyTorch build and pulled its own `torch` dependency from the default package
index — which serves the CPU-only wheel — silently replacing it. The telltale
sign was mismatched versions side by side: `torchaudio 2.5.1+cu121` next to
`torch 2.14.0+cpu`.

**Fix:** install CUDA PyTorch **last**, with `--force-reinstall --no-deps`, and
always verify with `torch.cuda.is_available()` rather than assuming.

**Lesson:** pip has no concept of "this specific build must win". Later installs
can quietly overwrite earlier ones.

---

## 8. Project layout

```
MusicTeacher/
├── stemlab/                 # the tool (Phase 3)
│   ├── __init__.py
│   ├── __main__.py          # CLI: split / mix / list
│   ├── store.py             # hashing, cache paths, what's done
│   ├── separate.py          # song  -> six stems        (slow half)
│   └── mixer.py             # stems -> one audio file   (fast half)
│
├── data/
│   └── cache/
│       └── <hash>/          # one folder per song
│           ├── Vocals.wav
│           ├── Drums.wav
│           ├── Bass.wav
│           ├── Guitar.wav
│           ├── Piano.wav
│           ├── Other.wav
│           └── meta.json    # written last = split completed
│
├── split_song.py            # Phase 1 script, kept for reference
├── explore_audio.py         # Phase 2 teaching script
├── README.md
└── .venv/
```

---

## 9. Roadmap

| Phase | What | Status |
| --- | --- | --- |
| 0 | Set up the workbench | ✅ Done |
| 1 | Split one song and listen hard | ✅ Done |
| 2 | Learn what audio actually is | ✅ Done |
| 3 | A command-line version of the whole product | ✅ Done |
| 4 | The browser player — Web Audio API, stems in sync, one slider each | Next |
| 5 | A server, so the two halves meet | |
| 6 | Speed and pitch, independently | |
| 7 | Loops that land on the beat | |
| 8 | More instruments than four | Partly done — already on `htdemucs_6s` |
| 9 | Turn it into something you can hand to someone | |

**Phase 4 preview — the trap worth knowing in advance:** do not play stems with
six `<audio>` tags. They start when they feel like it and drift apart by tens
of milliseconds, which sounds like a badly played band. All stems must be
decoded into memory and started at one shared timestamp computed from the audio
clock.
