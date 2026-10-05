# Woodshed

Take a song apart, then practise inside it.

Feed in any song, get back separate audio tracks — one per instrument — then
mute, quieten or isolate any of them. Mute the guitar and play the guitar part
yourself. Drop the drums to 10% and keep time with what's left. Solo the vocal
to learn a melody.

---

## About this document

This is the project's **explanation**, not a quick-start guide. It goes phase by
phase and, for each one, answers:

- **What** was built
- **Why** that piece exists at all
- **What was used** and why that choice over the alternatives
- **How it actually works**, in enough depth that nothing is left as magic

If something here still leaves a "but *why* does that work?" question, that is a
gap in this document, not in you.

> Picking the project up fresh? [`CONTEXT.md`](CONTEXT.md) has the current
> state, the remaining plan and the settled decisions. This file explains the
> ideas.

---

## Contents

1. [The one idea underneath everything](#1-the-one-idea-underneath-everything)
2. [Architecture: two halves](#2-architecture-two-halves)
3. [Setup and usage](#3-setup-and-usage)
4. [Phase 0 — The workbench](#4-phase-0--the-workbench)
5. [Phase 1 — Separation](#5-phase-1--separation)
6. [Phase 2 — What audio actually is](#6-phase-2--what-audio-actually-is)
7. [Phase 3 — The command-line tool](#7-phase-3--the-command-line-tool)
8. [Phase 4 — The browser player](#8-phase-4--the-browser-player)
9. [Phase 5 — The server](#9-phase-5--the-server)
10. [Phase 6 — Speed and pitch](#10-phase-6--speed-and-pitch-independently)
11. [Phase 7 — Seeing the song, and looping it](#11-phase-7--seeing-the-song-and-looping-it)
12. [Code structure](#12-code-structure)
13. [What comes next](#13-what-comes-next)
14. [Glossary](#14-glossary)

---

## 1. The one idea underneath everything

A song is a smoothie. Drums, bass, guitar and voice were blended into one
liquid, and normally you cannot get the strawberry back out.

AI models now exist that can un-blend it. Feed in one mixed song, get back
separate files, one per instrument. Each of those files is called a **stem**.

Everything in this project follows from that one fact:

| What the user does | What is actually happening |
| --- | --- |
| "Remove the drums" | Multiply every number in the drums file by `0` |
| "Drums at 30%" | Multiply every number in the drums file by `0.3` |
| "Play everything together" | Add the files together |

**No AI is involved in any of those steps.** The AI runs exactly once, up front,
to produce the stems. After that, the app is an ordinary music player that
happens to have one volume slider per instrument. The rest is arithmetic.

This is worth internalising early, because it explains every structural decision
that follows: the slow AI part and the fast arithmetic part have nothing in
common, so they are built separately, in different languages, running in
different places.

---

## 2. Architecture: two halves

```
┌───────────────────────────────┐         ┌───────────────────────────────┐
│  THE KITCHEN                  │         │  THE INSTRUMENT               │
│                               │  stems  │                               │
│  Python · slow · needs a GPU  │ ──────▶ │  JavaScript · instant         │
│  runs once per song           │         │  runs in the browser          │
│                               │         │                               │
│  song.mp3 → 6 stem files      │         │  plays stems in sync,         │
│  (+ tempo/key later)          │         │  mixes them live              │
└───────────────────────────────┘         └───────────────────────────────┘
        phases 0–3, 5, 7 ✅                       phases 4, 6, 7 ✅, 8–9 to go
```

**Why they are separate.** The kitchen takes ~25 seconds per song and needs a
graphics card. The instrument must respond within milliseconds of your finger
moving. Nothing useful is shared between them, so mixing the two would only make
both harder to reason about.

**Why the mixing happens in the browser, not on the server.** Imagine the
opposite: every slider nudge sends a request, the server renders a new audio
file, sends it back, playback restarts. Every adjustment costs seconds, and
playback stutters. Doing the arithmetic on the listener's own machine makes it
instant, free, and able to work offline. The server only ever ships the stems
once.

**Why Python for the kitchen.** Not preference — every audio and machine
learning library of consequence lives there. PyTorch, librosa, soundfile,
Demucs. Using anything else would mean reimplementing them.

**Why JavaScript for the instrument.** Also not preference. The browser already
contains a professional audio engine (the Web Audio API) with sample-accurate
scheduling and a real mixing graph, available for free, on a device everyone
already owns.

---

## 3. Setup and usage

### Install

```powershell
# ffmpeg — then open a NEW terminal so PATH updates apply
winget install ffmpeg

# Python environment, with the backend as an editable install
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e backend

# CUDA PyTorch — must be installed LAST (see phase 0 for why)
.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu121 --force-reinstall --no-deps

# Only the plain ONNX Runtime — never the GPU build (see phase 0)
.venv\Scripts\python.exe -m pip uninstall -y onnxruntime-gpu onnxruntime
.venv\Scripts\python.exe -m pip install onnxruntime
```

### Verify

```powershell
ffmpeg -version
.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available())"   # must print True
```

### Use

```powershell
# Split a song into six stems — slow the first time, instant afterwards
woodshed split "song.mp3"

# Render a practice track
woodshed mix "song.mp3" --vocals 0 --drums 0.1 --out practice.wav

# List what has been split
woodshed list

# Find the beats in a song split before beat tracking existed
woodshed analyse "song.mp3"

# The web app - page, uploads and stems, all from one server
woodshed serve
# then open http://127.0.0.1:8000
```

> **After any `pip install` in this project, put the CUDA build of PyTorch
> back.** `audio-separator` depends on torch, so installing anything at all
> pulls the CPU-only wheel from PyPI over it. Nothing breaks visibly —
> separation simply becomes many times slower. The exact command is in
> `backend/pyproject.toml`, and `torch.cuda.is_available()` must print `True`
> afterwards.

---

## 4. Phase 0 — The workbench

Installing tools. Nothing visible to show at the end, and that is expected.

### The virtual environment

`python -m venv .venv` creates a private folder of Python libraries used only by
this project.

**Why bother?** Without it, every Python project on your machine shares one pile
of libraries. Project A needs version 1 of something; project B needs version 2.
Installing for B silently breaks A, and the breakage appears weeks later in code
you did not touch. A virtual environment gives each project its own pile, so
they cannot interfere.

The cost is that you must point at that specific Python (`.venv\Scripts\python.exe`)
rather than the system one.

### ffmpeg

The universal audio and video converter. Almost every audio tool in existence
calls it internally rather than reimplementing decoding.

**Why this project needs it.** An mp3 is *compressed* — the raw audio has been
cleverly shrunk, and the file no longer contains the actual sound values. Before
any model can look at the audio, something must expand it back into raw numbers.
That something is ffmpeg. Later it will do the reverse: compress finished stems
so they are small enough to send over a network.

### audio-separator

A Python package that wraps the separation models — downloading model files,
feeding audio through them in chunks, and writing outputs.

**Why not write this yourself?** Running a neural network involves loading
trained weights, constructing the matching architecture, chunking audio so it
fits in memory, running inference, and crossfading the chunks back together.
That is weeks of work with no product benefit. The model itself is the valuable
part, and that is downloaded, not written.

### PyTorch, and why install order matters

PyTorch is the framework the model actually runs on. It comes in two flavours:
a CPU-only build, and a CUDA build that can use an NVIDIA graphics card.

They have the same package name, so **whichever is installed last wins**. If you
install the CUDA build and then install anything that lists `torch` as a
dependency, pip will happily fetch the CPU build from the default index and
overwrite it. Everything still runs — just many times slower — and the only
symptom is `torch.cuda.is_available()` returning `False`.

Hence the rule: install CUDA PyTorch last, with `--force-reinstall --no-deps`,
then verify rather than assume.

### Why only plain ONNX Runtime

ONNX Runtime is a different model-running engine, used by other separation model
families (MDX, VR). Demucs — what this project uses — runs on PyTorch and never
touches it.

`onnxruntime` and `onnxruntime-gpu` install into the **same folder**, so
installing both leaves a mixture of two packages' files. The GPU build also
loads its own CUDA libraries into a process that already has PyTorch's,
different versions of the same thing in one program. Removing the GPU build
avoids the whole situation, and costs nothing, because it was never used.

GPU acceleration in this project comes entirely from PyTorch.

---

## 5. Phase 1 — Separation

Run one song through the model, then listen to every stem carefully.

### Why this came first, before any code

It is the riskiest assumption in the project, and it costs an hour to test. If
the drum stem is clean enough that you would genuinely practise against it,
there is a product. If it is full of watery artifacts, that is far better
learned now than after six weeks of building a player for it.

The rule generalises: **test the assumption that would invalidate everything
else, before building the everything else.**

### What a stem is

An audio file containing one isolated part of a recording. In a studio these
exist naturally — each instrument was recorded to its own track before being
mixed together. For a finished commercial release, those tracks are not public,
so they have to be reconstructed.

### How the model works

The model is **HTDemucs** — Hybrid Transformer Demucs — from Meta's AI research
group.

It was trained on datasets containing both the final mixes *and* the true
isolated stems of many songs (principally a research dataset called MUSDB18).
Shown enough pairs, it learned the statistical relationship between "what a full
mix looks like" and "what its drum track looks like".

**"Hybrid" means it analyses audio two ways at once:**

- **Waveform domain** — the raw sequence of sample values over time. Good at
  sharp, sudden events: a snare hit, a pluck, a kick drum.
- **Spectrogram domain** — the audio converted into a picture of which
  frequencies are present at each moment. Good at sustained, pitched material: a
  held vocal note, a bowed string, a piano chord ringing out.

Those two views are processed in parallel and combined. That is why it handles
both percussive and melodic material reasonably well, where older models were
good at one and weak at the other.

**What it does not do: understand music.** It has no concept of rhythm, key,
chord or song structure. It is pattern matching learned from examples. This is
exactly why it struggles with anything unlike its training data.

### Why separation is never perfect

Two failure modes, both worth being able to name:

- **Bleed** — traces of a removed instrument still faintly present in another
  stem. Mute the drums and you may still hear a ghost of cymbals, because some
  of that cymbal energy was assigned to "Other".
- **Artifacts** — watery, smeared or phasey sounds where an instrument used to
  be.

**Why cymbals and reverb are the hardest.** A cymbal is a wash of energy spread
across almost the entire frequency range — it overlaps with everything, so
there is no clean boundary to cut along. Reverb is worse: it is the sound of an
instrument *smeared through the room*, so vocal reverb is genuinely part vocal
and part everything-else. The model has to guess, and guesses sound like
artifacts.

### Choosing a model

| Model | Stems | Relative cost | Character |
| --- | --- | --- | --- |
| `htdemucs` | 4 | 1× | Vocals, Drums, Bass, Other. The dependable default |
| `htdemucs_ft` | 4 | ~4× | Same four, but four separately fine-tuned models, one specialised per stem, run in sequence. Cleaner, much slower |
| `htdemucs_6s` | 6 | ~1.5× | Adds Guitar and Piano. **Used by this project** |

**Why `htdemucs_6s`.** Practising a *specific instrument* is the entire point of
the app. A guitarist needs a guitar fader; with four stems the guitar is buried
inside "Other" along with everything else. That capability is worth more than a
marginal cleanliness gain on the core four.

**The honest cost:** its guitar and especially its piano separation are rougher
than the Vocals/Drums/Bass split, because there was less training data for them.
Guitar covers **both acoustic and electric** — the model does not distinguish.
Clean acoustic guitar and piano are frequently confused with each other, since
both are struck/plucked strings with similar attack.

**What "Other" contains:** everything the model could not assign to a named
stem — strings, synths, horns, background texture, and any instrument outside
its training experience (sitar, sarod, tabla). It is the leftovers bucket, not
an instrument.

### The `shifts` setting

Demucs can separate the same song several times, each at a slightly different
time offset, then average the results. Small random errors differ between passes
and partly cancel out, so the stems come back marginally cleaner.

The cost is memory: each pass needs its own full-size result buffer, and they
are all held at once. **This project uses one pass** (`shifts: 1`, set in
`separate.py`). On an 8 GB machine that is the difference between finishing and
crashing, it is twice as fast, and the quality difference is small.

### Why a GPU, and what it does not solve

Neural networks are overwhelmingly large matrix multiplications. A CPU has a
handful of powerful, flexible cores; a GPU has thousands of simple ones. That
suits the work far better — roughly 10–20× faster here, the difference between
25 seconds and several minutes.

**But the two memory pools do different jobs, and neither substitutes for the
other:**

| | Graphics memory (VRAM) | System memory (RAM) |
| --- | --- | --- |
| Holds | the model, and the chunk being processed right now | the whole song, and the full-length assembled result |
| Size here | 4 GB | ~5.9 GB usable |

The model works through the song in chunks on the GPU, and each finished chunk
is written back into RAM where the full-length result is assembled. So a large
VRAM does not rescue you from a small RAM, and vice versa.

---

## 6. Phase 2 — What audio actually is

The concept every later phase rests on. No AI, no libraries doing anything
clever — just looking directly at what audio *is*.

### Sound, physically

A speaker makes sound by moving a cone in and out very fast. Push the air, pull
back, push again. Your eardrum copies that movement, and your brain interprets
it as sound.

So a recording is really **a description of how a speaker cone should move over
time**.

### How a computer stores that

The computer writes down where the cone should be, **44,100 times per second**:

- `0.0` — at rest (silence)
- `+1.0` — pushed fully out
- `-1.0` — pulled fully in
- `0.37` — pushed out about a third of the way

Each of those numbers is a **sample**. A four-minute stereo song is roughly 10.5
million samples per channel. A `.wav` file is essentially that list of numbers
written to disk with a small header on the front.

When you load a stem in Python and print its shape, you see exactly this:

```
shape       : (10584000, 2)   ← 10.5 million samples, 2 channels
sample rate : 44100 Hz        ← samples per second, per channel
value range : -0.982 to +0.979
```

### Why 44,100 specifically

To capture a frequency accurately you must sample at **more than twice** that
frequency — a rule called the Nyquist limit. Below that, a high frequency
becomes indistinguishable from a lower one and is recorded wrongly.

Human hearing tops out around 20,000 Hz. Twice that is 40,000, plus some
headroom for the filters that remove everything above the limit, which lands at
44,100. It became the CD standard, and it is still the default everywhere.

The useful analogy is video frame rate: enough still images per second stop
looking like images and start looking like motion. Enough cone positions per
second stop sounding like clicks and start sounding like music.

### Channels

`2` means stereo: one list of numbers for the left speaker, one for the right.
Arrays are shaped `(samples, 2)`. Mono would be one list.

### Bit depth

How precisely each individual sample is stored. 16-bit gives 65,536 possible
positions between fully-out and fully-in — the CD standard, and what the stems
are written as. In Python the numbers are converted to decimals between −1 and
+1 so arithmetic on them is straightforward.

### Mixing is addition

When two instruments play at once in a room, their pressure waves physically add
together before reaching your ear — you receive **one** combined pressure, never
two separate sounds.

Digital audio copies that exactly. Add the sample values of two stems and you
get the sound of both playing together. This is not an approximation or a trick;
it is how waves genuinely combine.

At one instant:

```
Drums   0.4
Bass    0.3
Vocals  0.2
Guitar  0.1
        ---
        1.0   ← where the cone goes
```

### Volume is multiplication

A **gain** is a number you multiply every sample by:

```
Drums   0.4 × 0.1 = 0.04    ← turned down to 10%
Bass    0.3 × 1.0 = 0.3     ← untouched
Vocals  0.2 × 0.0 = 0.0     ← muted
Guitar  0.1 × 1.0 = 0.1
                    ----
                    0.44
```

Note that `× 0` gives exactly zero. Mute is *perfect* — not "very quiet" but
mathematically silent, contributing nothing at all.

**This is the entire product.** One line of Python:

```python
mix = sum(stems[name] * gain for name, gain in gains.items())
```

Everything the browser player does later is this same line, run continuously.

### Why 0.3 does not sound like "30%"

Your ear judges loudness by **ratio**, not by difference. An analogy: one person
talking, then a second joins — a big change. A hundred people talking and a
hundred-and-first joins — unnoticeable. Identical "+1 person", completely
different perception, because your ear compares against what is already there.

That perception is logarithmic, so the numbers and your ears disagree:

| Gain | In decibels | How it sounds |
| --- | --- | --- |
| `1.0` | 0 dB | unchanged |
| `0.5` | −6 dB | slightly quieter |
| `0.3` | −10 dB | about half as loud |
| `0.1` | −20 dB | about a quarter as loud |
| `0.0` | −∞ | silent |

**Decibels** are simply a unit designed to match the ear instead of the maths.
Rule of thumb: every −6 dB halves the number; around −10 dB halves the
*perceived* loudness.

**The practical consequence:** when a change sounds smaller than you expected,
that is your ear, not a bug. Go lower than feels right.

### Clipping, and why it is not a problem here

Because mixing adds, sums can exceed `1.0`. But the cone cannot travel past
fully extended, so anything beyond gets flattened:

```
wanted :  0.5   1.4   1.2   0.8
actual :  0.5   1.0   1.0   0.8
                 ↑     ↑
          different values, now identical
```

The flattened peak is heard as harsh crackling — distortion, not extra loudness.

**Is it a real risk?** This was measured rather than assumed. Peaks across every
realistic slider setting on a test song:

```
everything at 100% (the record)   0.898
mute Vocals                       0.924
mute Drums                        0.720
everything at 50%                 0.449
```

Nothing came close to `1.0`. Commercial records are mastered with headroom
built in, and sliders here only ever reduce. `np.clip(mix, -1, 1)` stays as a
one-line safety net that should never actually fire.

**One counter-intuitive detail worth knowing:** muting a stem can *raise* the
peak (`0.898` → `0.924` above). Samples are signed, so at any instant some stems
push while others pull, partly cancelling. Remove a stem that was pulling, and
more of the pushing is exposed. Removing sound can make the total bigger.

### Why sliders stop at 100%

A deliberate decision, for three reasons:

1. **Boosting a separated stem amplifies its artifacts.** Bleed and smearing
   live inside the stem's numbers; `× 2` doubles the flaws along with the
   instrument. Turning the *other* stems down makes an instrument equally
   prominent without magnifying anything.
2. **`1.0` is a meaningful anchor.** Because the stems sum back to the original,
   `1.0` means exactly "as loud as it was on the record". Above that there is no
   reference point at all.
3. **Loudness is relative**, so boost is never strictly necessary — pulling
   others down achieves the same result with no clipping risk.

Moises, the leading app in this space, also caps at 100% and starts tracks at
75%.

### The residual check

Add all six stems back together, subtract the original song, and see what is
left.

**Why this matters.** If the stems sum back to something very close to the
original, then every slider at 100% gives back the record, and every level you
set behaves the way a listener expects. If they do not, the model is losing or
inventing energy, and "100%" would be a lie. `explore_audio.py` also writes
`rebuilt.wav` so the same check can be made by ear.

---

## 7. Phase 3 — The command-line tool

Turning two hardcoded scripts into a real tool: the complete product, minus the
interface.

| Before | After |
| --- | --- |
| Song path hardcoded in the script | `split <any file>` |
| Gains hardcoded; edit and re-run to change | `mix song.mp3 --drums 0.1 --vocals 0` |
| Re-splitting the same song wasted minutes | Already-split songs recognised instantly |
| Two disconnected scripts | One tool, three commands |

### Why not jump straight to the interface

Two reasons, and the first is the important one.

**Debuggability.** If the audio logic provably works from the command line, then
any problem that appears in the browser is definitively a *browser* problem.
Debugging an unfamiliar UI and an unfamiliar audio pipeline simultaneously, with
no idea which half is at fault, is how projects stall.

**Caching.** Separation is the only slow step in the entire system. Doing it
twice for the same song is the single biggest waste that could be designed in,
and it is far easier to build now than to retrofit later.

### The four modules, and why they are separate

```
woodshed/
  __main__.py   the command line — translates typed text into function calls
  store.py      bookkeeping — hashing, paths, "has this been done?"
  separate.py   song → six stems        (the slow half)
  mixer.py      stems + gains → a file  (the fast half)
```

Each file does one job, and `__main__.py` deliberately contains **no logic at
all**. That matters for what comes next: the web server in phase 5 will call
`separate.split()` and `mixer.render()` directly. If the real work lived inside
the argument-parsing code, it would have to be rewritten to be reused.

The general principle: **keep the thing that decides separate from the thing
that does.** Interfaces change often; logic should not have to change with them.

### Hashing, and why the cache is keyed on it

A **hash function** takes any amount of data and reduces it to a fixed-size
fingerprint:

```
'hello' → 2cf24dba5fb0a30e
'hellp' → fdd7585e08c4e2af     one letter changed, entirely different result
```

Three properties make it right for this job:

1. **Deterministic** — the same bytes always produce the same fingerprint, today
   or next year.
2. **Sensitive** — change one byte anywhere and the fingerprint changes
   completely. Two files cannot be "nearly" the same hash.
3. **One-way** — the original cannot be reconstructed from the fingerprint.
   Irrelevant here, but it is why hashes are also used for passwords.

**Why not just use the filename?** Names lie. You rename a file and it looks
new. Two entirely different songs are both called `track.mp3`. A hash is
computed from the actual audio bytes, so:

- Rename the mp3 → same bytes → same hash → **cache still hits**
- Two different songs, same name → different bytes → **no collision**
- Re-download the same song → identical bytes → **instantly recognised**

The implementation reads the file in 1 MB chunks rather than all at once. For a
7 MB mp3 that hardly matters, but stem `.wav` files exceed 50 MB each, and
loading whole files into memory is a habit that causes real problems on a
memory-limited machine.

### Why `meta.json` is written last

A song counts as cached only if `meta.json` exists, and it is written **after**
every stem has landed.

**Why that ordering matters.** If a split dies halfway through — it takes 25
seconds and anything can interrupt it — the folder holds some stems but no
`meta.json`. So the cache correctly reports "not done" and redoes it, rather
than silently serving a song that is missing its bass.

The general pattern: **write the marker that says "finished" last**, so a
half-finished job can never look complete.

### `index.json`

A web page cannot list files in a folder on your disk — browsers forbid it. So
`split` also writes `data/cache/index.json`, a small list of every cached song,
and the player reads that to fill its dropdown. New splits appear automatically.

This is a placeholder: in phase 5 the server replaces it with a real endpoint.

---

## 8. Phase 4 — The browser player

A page with six sliders that change the mix **while the song plays**. Two files,
no framework, no build step.

### Why it needs a local server

Double-clicking `index.html` does not work. A page opened directly from disk is
forbidden from reading other local files — a security rule, so that a downloaded
web page cannot quietly read your documents. The page's requests for the stems
are blocked.

Serving the folder over HTTP turns those files into ordinary web addresses,
which is allowed. Python includes a server for exactly this:

```powershell
.venv\Scripts\python.exe -m http.server 8000
```

### The Web Audio API and the audio graph

The browser contains a full mixing engine. You do not "play a file" with it. You
build a **graph** of connected nodes and audio flows through it, like patch
cables in a studio:

```
Vocals ─ source → gain ─┐
Drums  ─ source → gain ─┤
Bass   ─ source → gain ─┼→ master gain → speakers
Guitar ─ source → gain ─┤
Piano  ─ source → gain ─┤
Other  ─ source → gain ─┘
```

- A **source** node reads through decoded audio.
- A **gain** node is a volume knob: it multiplies whatever passes through it.
- Where several connections meet one node, they are **added together**
  automatically.

Look at what those two node types do: multiply, and add. It is phase 2's
arithmetic, running continuously in the browser instead of once into a file.

A slider is then genuinely one line:

```js
gains["Drums"].gain.setTargetAtTime(0.3, ctx.currentTime, 0.015);
```

### Loading and decoding

```js
const res = await fetch(`../data/cache/${hash}/Drums.wav`);
buffers["Drums"] = await ctx.decodeAudioData(await res.arrayBuffer());
```

**Decoding** turns encoded file bytes into raw samples in memory — the same
expansion ffmpeg does in the Python half. It is **asynchronous** (`await`)
because it is slow, and JavaScript runs the page on a single thread: doing it
synchronously would freeze the entire page, unresponsive to clicks, until it
finished.

**Everything is loaded before anything starts.** This is not incidental — it is
required for sync. If playback began while files were still arriving, the
fast-loading stems would start first.

**Memory note:** decoding expands compressed audio back to raw samples, so six
stems occupy roughly 500 MB regardless of the file format they arrived in.
Compression shrinks transfer, not memory.

### Keeping six tracks in sync — the core of this phase

The naive approach, six `<audio>` tags, fails. Each begins whenever the browser
gets round to it, and they drift apart by tens of milliseconds. It sounds like a
band that cannot keep time.

The fix is two rules: load everything first, then give them all **one shared
start time, slightly in the future**.

```js
const startAt = ctx.currentTime + 0.1;
for (const name of STEMS) sources[name].start(startAt, from);
```

**Why `startAt` is computed before the loop.** `ctx.currentTime` moves forward
constantly, so reading it *inside* the loop would give each stem a different
value:

```
WRONG — start(ctx.currentTime + 0.1) inside the loop
  Vocals.start(5.100)
  Drums.start(5.101)    ← 1 ms late
  Bass.start(5.102)     ← 2 ms late
```

Computed once and stored, it is just a fixed number that every iteration reuses:

```
RIGHT — startAt fixed at 5.1 before the loop
  Vocals.start(5.1)
  Drums.start(5.1)
  Bass.start(5.1)       ← identical instant
```

**What `start(5.1)` actually does.** It does not play anything. It *books* a
time: it tells the sound card "begin this at 5.1", and the sound card begins it
at exactly 5.1, accurate to the individual sample.

**Why `+ 0.1`.** It buys enough time to finish booking all six before that
instant arrives. Without the gap, the deadline could pass mid-loop and the later
stems would be late. A tenth of a second is an eternity for a computer, and too
short for you to perceive as a delay.

### The audio clock

`ctx.currentTime` is not the browser's ordinary clock. It is driven by the sound
card itself, and is what audio scheduling is measured against — precise to the
sample.

The ordinary clock, and timers built on it, are subject to the page being busy:
rendering, garbage collection, a heavy script. A few milliseconds of hesitation
is invisible on screen and clearly audible in music. Audio timing therefore
never uses it.

### Why pause, resume and seek rebuild everything

An unusual rule governs source nodes:

> **A source is single-use. Once stopped, it can never be started again.**

So "pause" cannot literally pause. What happens is:

**On Pause**
1. Record the current position — say 42 seconds
2. Destroy all six sources

**On Play**
1. Build six brand-new sources
2. Start them at a shared timestamp, **beginning 42 seconds into the audio**

```js
sources[name].start(startAt, from);
//                  ↑         ↑
//             when to begin   where in the song to begin
```

That second argument is what makes it feel like resuming.

**Seeking is the same operation** with a different number: destroy six, create
six, start them all at 90 seconds.

**Crucially, the audio is not reloaded.** The decoded buffers stay in memory
throughout; only the lightweight source objects are discarded and recreated.
That is why pause and seek feel instant despite 300 MB of audio being involved.

### Why sliders never disturb playback

```
Drums buffer → [source] → [gain] → speakers
                  ↑          ↑
            keeps reading   you only touch this
```

The source and the gain are separate nodes. Dragging a slider changes the gain
only; the source carries on reading at the same speed and position, entirely
unaware. Like turning your TV volume down without pausing the show.

This is why sliders cannot knock anything out of sync. All six sources keep
running untouched — you are only changing how loudly each one comes through.

### Tracking position

Two values are recorded when playback starts:

- `offset` — where in the song it began (42 s)
- `startedAt` — what the audio clock read at that moment (5.1)

Current position is then subtraction:

```
position = offset + (clock now − startedAt)
```

At clock 8.1: `42 + (8.1 − 5.1)` = **45 seconds**. That drives the timer and the
moving seek bar, and it stays accurate because it is derived from the audio
clock rather than counted up by a timer.

### Ramping instead of jumping

Setting a gain instantly makes the waveform take a vertical step, heard as a
click. `setTargetAtTime(value, now, 0.015)` glides to the new value over about
15 milliseconds — far too short to feel as a delay, long enough to remove the
click entirely.

### Why audio cannot start until you click

Browsers refuse to let a page produce sound before the user interacts with it,
because otherwise every page you opened could blare at you. The audio engine
therefore starts in a suspended state, and the first Play click is what creates
and resumes it. This is why the first click both loads the song and starts it.

### Design decisions carried over

Sliders run 0–100% with no boost, for the reasons in phase 2, and `0%` is
genuine silence rather than "very quiet".

---

## 9. Phase 5 — The server

Drop a song on the page, watch it split, play it. No terminal.

Until now the two halves never met: the kitchen was run by hand at the command
line, and the player read stems straight off the disk. Phase 5 joins them, and
turns the project from "a thing you can operate" into "a thing someone can
use".

### One server, not two

`woodshed serve` replaces the `http.server` used in phase 4, and does everything:

| Route | Job |
| --- | --- |
| `GET /` | the player page and its script |
| `POST /tracks` | accept an upload, return a ticket |
| `GET /jobs/{id}/events` | stream that job's progress |
| `GET /tracks` | every song already split |
| `GET /tracks/{hash}` | one song, with its stem URLs |
| `GET /stems/{hash}/{stem}` | the audio itself |

**Why one server rather than a separate API and page server.** If the page came
from one address and the data from another, every request between them would be
a *cross-origin* request, which browsers block by default unless the server
sends explicit permission headers (CORS). Serving both from one address makes
them same-origin, and that entire category of problem disappears.

### Why an upload cannot simply wait for the answer

Separation takes ~25 seconds here, minutes on a slower machine. Doing it inside
the upload request fails twice over:

- **It times out.** Browsers, proxies and load balancers all give up on requests
  that take minutes, so the user sees a failure for work that actually
  succeeded.
- **It blocks.** While that request is being handled, the server may be unable
  to answer anyone else.

So the interaction splits into three:

```
1.  POST /tracks               ->  { job_id: "3ad81ead3965" }   returns instantly
2.  (the server works in the background)
3.  GET /jobs/3ad81.../events  ->  queued... separating... done
```

The upload returns a **ticket** rather than a result. Hand back an identifier,
do the work elsewhere, let the client follow it — that is how every system deals
with work that outlives a request.

### How the background work runs

FastAPI's `BackgroundTasks` runs the split *after* the response has been sent.
Because `run_split` is an ordinary synchronous function, FastAPI runs it in a
worker thread rather than on the main event loop, so the server keeps answering
other requests while separation is underway.

Job state lives in a plain dictionary in memory. That is deliberate: a finished
split is already saved in the cache on disk, so losing job records on restart
costs nothing. A database here would be machinery with no benefit — that changes
only once work is spread across several machines.

### Server-sent events, and why not websockets

Progress arrives on a connection the server keeps writing to:

```
data: {"status": "separating", "hash": null}

data: {"status": "done", "hash": "5d024c3e0b9e7939"}
```

That is **server-sent events**: an ordinary HTTP response that never finishes,
marked `Content-Type: text/event-stream`. The browser reads it with
`EventSource`, and reconnects by itself if the connection drops.

**Why not websockets?** A websocket is a two-way channel, needing a protocol
upgrade and its own connection handling. Here nothing ever travels *back up* —
the browser has nothing to say once the upload is done. Choosing the one-way
tool keeps the number of moving parts down.

**Why stages rather than a percentage.** The model reports progress to a
terminal, not through anything this code can read. A fabricated percentage that
jumps or stalls is worse than an honest "separating — about 30 seconds".
Invented precision is not precision.

### Shipping Opus, keeping WAV

After separation, each stem is also written as **Opus**, a modern compressed
format:

```
Drums.wav    37.0 MB
Drums.opus    2.3 MB     16x smaller
```

A whole song goes from ~222 MB to ~14 MB. Over localhost that hardly matters;
over a real network it is the difference between a usable app and an unusable
one.

**The WAVs are kept** because they are lossless. Compression discards
information permanently, so anything re-rendered later should start from the
originals, never from a compressed copy. Compress what you *send*; keep what
you *have*.

**What compression does not fix:** memory. The browser decodes Opus back into
raw samples in order to play it, so six stems still occupy roughly 500 MB while
playing, whatever format they arrived in. Compression shrinks transfer and
storage, not playback memory.

### Video files

A phone recording of a band arrives as video, not audio. Before separation, the
soundtrack is pulled out with ffmpeg and the picture is thrown away:

```
band.mp4  →  ffmpeg -vn  →  audio  →  six stems
```

Forced to 44.1 kHz stereo on the way out, so every song reaching the model looks
the same whatever the camera produced.

**The video is hashed as it arrived**, not the extracted audio. The cache key
stays tied to the file you actually have, so re-uploading the same clip is
recognised immediately. The extracted audio is a temporary working file and is
deleted once separation finishes.

**Worth knowing about recordings of your own band:** the model was trained on
studio recordings — separately miked, properly mixed. A phone in a room gives
it one cheap microphone, reflections off every wall, and total bleed between
instruments. Separation still works, just noticeably rougher. That is a limit of
what the recording contains, not a fault in the model.

### Not trusting the request

Two places where outside data is checked before it can reach the filesystem.

**Uploaded filenames.** Only the bare name is used, never the path that came
with it. Otherwise a name like `../../Windows/System32/something` would let an
upload choose where it lands.

```python
name = Path(file.filename or "upload.mp3").name
```

**Requested stems.** A hash must be exactly sixteen hex characters and must
already exist in the cache; a stem name must be one of the six known names.
Without those checks, `GET /stems/../../secrets/file` is an invitation to read
anything on the disk.

The principle: **data arriving from outside is input to be validated, not
instruction to be followed** — most of all when it is about to become a file
path.

### What this phase makes possible

Everything remaining assumes it. Tempo and beat analysis (phase 7) becomes extra
data served alongside the stems. Handing the app to someone else (phase 9)
becomes a deployment question rather than a rebuild.

---

## 10. Phase 6 — Speed and pitch, independently

Two controls that must not affect each other: play at 70% in the original key,
or transpose up two semitones at the original tempo.

Different musicians need opposite things. A drummer learning a fill wants it
slower, same pitch. A guitarist with a capo wants the key moved, same tempo. A
singer wants the key dropped to fit their range.

### Why these are the same thing to begin with

Pitch is **how often a wave repeats per second**. The note A is a wave
completing 440 cycles a second. At a sample rate of 44,100, one cycle of it
occupies 44,100 / 440 = **100 samples**.

Speed is **how fast the sample list is consumed**. Play it at half rate and
those 100 samples take twice as long to go by, so the cycle completes half as
often: 440 Hz becomes 220 Hz, an octave down.

That is a record player slowing. Not two effects — one effect seen twice. Every
recording has speed and pitch welded together, and pulling them apart requires
rebuilding the audio.

### Time-stretching: the piece that does not exist in nature

Keep playback at 44,100, but change how much *content* there is. Cut the audio
into short overlapping grains, roughly 50 ms each, and re-space them:

```
original :  [A][B][C][D][E]
slower   :  [A][A][B][B][C][C][D][D][E][E]     grains repeated
faster   :  [A]   [C]   [E]                    grains skipped
```

Each grain still plays at normal speed, so nothing changes pitch — there is
simply more or less material to get through. Speed moved, pitch did not.

Pitch-shifting then falls out of the same machinery: stretch to 120% length
(same pitch, slower), then resample back to 100% (record-player effect, pitch
rises). The duration changes cancel; the pitch change does not.

### Why this needs a library

Two failure modes make a naive implementation sound terrible:

- **Transients.** A drum hit lasts a few milliseconds. Repeat a grain
  containing one and you hear the kick **twice**; skip it and the hit vanishes.
  The result is flams, doubled hits, and a watery wash instead of a snap.
- **Phase coherence.** For a sustained note, grains must line up within their
  wave cycles. When they do not, you get a hollow, flanging, underwater sound.

Handling both well means working in the frequency domain and detecting
transients to protect them. That is a research problem, not an afternoon.

### Choosing the library

| Library | Quality | Licence | Verdict |
| --- | --- | --- | --- |
| Rubber Band | excellent | **GPL** | would force this project to be open-sourced |
| **Signalsmith Stretch** | comparable | **MIT** | **chosen** |
| SoundTouch | poor on drums | permissive | time-domain, mangles transients |

Licence is a product decision, not a detail: GPL obliges you to open-source
anything you ship with it. Signalsmith Stretch is MIT, has an officially
maintained Web Audio build (WebAssembly plus AudioWorklet), and ships as a
single self-contained `.mjs` file — no build step, no separate `.wasm` to serve.

It lives in `web/vendor/SignalsmithStretch.mjs`.

### WebAssembly and the audio thread

The library is C++, so it is compiled to **WebAssembly** to run in the browser
at near-native speed. JavaScript is not fast enough for this work.

It runs inside an **AudioWorklet** — a separate real-time thread reserved for
audio. The main browser thread regularly pauses for a few milliseconds to
render the page or reclaim memory. Invisible on screen; clearly **audible as a
click** in music. Audio processing cannot live there.

### The actual design, and why it is not the obvious one

The library works two ways. Given **buffers**, it controls its own playback and
supports both `rate` and `semitones`. Given **live input**, its documentation is
explicit: `rate` is ignored, and only `semitones` applies.

Live input is the only option here, because one stretcher has to sit **after**
the six stems are summed — otherwise the volume sliders would have to be baked
in before stretching, and they would stop being live. Six stretchers, one per
stem, would cost six times the CPU and could drift apart, undoing phase 4's
sync work.

So speed comes from somewhere else: **resampling the six sources**, which is
what `playbackRate` on a buffer source does. That changes speed and pitch
together, record-player style — and the stretcher then corrects the pitch back:

```
speed 0.7  ->  pitch falls by 12 x log2(0.7) = 6.18 semitones
stretcher  ->  +6.18 semitones
               ────────────────────────────────────────────
               70% speed, original key
```

```js
stretch.schedule({ semitones: userSemitones - 12 * Math.log2(speed) });
```

The user's own transpose is simply added to that number. One stretcher, on the
master, live sliders, sync intact.

```
six sources -> six gains -> master gain -> stretch -> speakers
  (resampled by playbackRate)              (corrects pitch)
```

**Why the six stay in sync while resampled:** every source gets the identical
rate, and resampling is deterministic, so they advance through their buffers in
lockstep exactly as before.

### Position tracking has to change

At 70% speed, one second of real time covers 0.7 seconds of the song:

```
position = offset + (clock now - startedAt) x speed
```

And when the speed slider moves mid-playback, everything played so far happened
at the *old* speed. So that position is banked and the clock re-anchored before
the new rate applies:

```js
offset = position();
startedAt = ctx.currentTime;
speed = next;
```

Without that, changing speed would corrupt the playhead.

### Known limits

- The library documents time-stretching as sounding best between **0.75x and
  1.5x**. The slider allows 50-150%, and quality degrades toward the extremes.
- The stretcher introduces latency of tens of milliseconds, so sound lags the
  displayed position slightly. Unnoticeable while listening; it will matter in
  phase 7, when a moving playhead has to line up with what you hear.
- Large pitch shifts sound cartoonish, because a voice's resonances (formants)
  are shifted along with the notes, as though the singer's head changed size.
  The library can compensate for this; it is not enabled yet.

---

## 11. Phase 7 — Seeing the song, and looping it

The phase that makes this a practice tool rather than a player with sliders.

**The problem:** there is one hard passage you want to learn. Without looping
you play it, drag the seek bar back, land somewhere slightly wrong, play it
again, drag back again. Most of the practice time goes into dragging.

**With looping:** select it once and it repeats by itself, indefinitely, while
you play along.

### The waveform

The strip above the transport is the song, drawn.

**The problem it solves:** the song is about 10 million numbers. The canvas is
a few hundred pixels wide. You cannot draw 10 million things in 800 slots.

**So each pixel stands for a chunk of the song:**

```
10,000,000 numbers / 800 pixels = 12,500 numbers per pixel
```

For each pixel, find the **loudest** value in its chunk and draw a line that
tall. Loud sections become tall, quiet ones short, and the shape of the
arrangement becomes visible at a glance.

Reading all 12,500 values per pixel is unnecessary, so it steps through them,
sampling roughly 150 per chunk. Visually identical, several times faster.

This happens in the browser, from audio already decoded in memory. No server
involvement at all.

### Finding the beats

A loop that restarts a fraction of a beat late is useless: you feel the
stumble every time it wraps, and your timing follows what you hear. So the loop
has to restart on a bar line, which means the app has to know where the beats
are.

That is analysis, so it belongs in the kitchen. `woodshed/analyse.py` runs once
per song and writes `beats.json` next to the stems.

**How beat tracking works, in outline.** A beat usually coincides with a sudden
rise in loudness — a kick or snare. So:

```
loudness over time:   ▁▁▁█▁▁▁█▁▁▁█▁▁▁█▁▁▁█
                         ↑   ↑   ↑   ↑   ↑
                       the sudden rises
```

Find those rises, then find the regular spacing that best explains them. That
spacing is the tempo, and the positions are the beats.

**Analyse the drum stem, not the mix.** To a beat tracker, a loud guitar chord
looks much like a drum hit, and a dense arrangement is mostly distraction. The
isolated drum stem contains almost nothing but hits. The accuracy is free,
because Phase 1 already produced that stem.

On the test song this gave 83.35 bpm, with the gap between consecutive beats
identical to the millisecond.

**Extending the grid backwards.** Beats are only detected where drums actually
play, and the test song has no drums for its first twelve seconds — so the
entire intro had no grid, and nothing to snap a loop to. Produced music holds a
steady tempo, so the spacing found later is projected back to the start of the
song.

**Sample rate.** Analysis loads the audio at 22.05 kHz rather than 44.1. No
musical information near 20 kHz tells you where a snare is, and halving the
data cut the time from 31 seconds to 10.

**Bars.** `librosa` reports beats, not which beat starts a bar. The code
assumes four beats to a bar and treats the first detected beat as a bar start.
That is an assumption, and it will be wrong for waltzes and for songs with an
unusual pickup. Getting it properly right needs downbeat detection, which is a
harder problem and a different library.

### Serving the beats

```
GET /tracks/{hash}/beats  ->  { "tempo": 83.35, "beatsPerBar": 4, "beats": [...] }
```

Two details worth noting.

**It is a plain `def`, not `async def`.** FastAPI runs synchronous endpoints in
a worker thread. Analysis takes several seconds, and on the main event loop
that would freeze every other request for its duration.

**It analyses on demand if the file is missing.** Songs split before beat
tracking existed are handled the first time the player asks, then cached like
everything else. The browser does not wait for it either — bar lines simply
appear when the data arrives.

### Snapping

Wherever you release the drag, the start and end jump to the nearest bar line:

```
released at:  bar 17.3          bar 20.8
snapped to:   bar 17            bar 21
```

You never have to be precise, and the result is always musical.

### Why the audio thread does the looping

The obvious implementation is to watch the clock in JavaScript and jump back
when playback passes the end. That is the wrong approach: the main thread
pauses regularly for rendering and memory work, so the jump lands late by
however long the page happened to be busy. Tens of milliseconds, audible, and
different every time round.

Instead each source is told to loop itself:

```js
src.loop = true;
src.loopStart = loop.start;
src.loopEnd = loop.end;
```

The audio engine handles the wrap in its own real-time thread, sample-accurate,
regardless of what the page is doing. JavaScript sets the points and steps
away.

### Position while looping

Elapsed time keeps growing after the loop end, so the playhead has to be folded
back into the loop:

```js
let pos = offset + (clock now - startedAt) * speed;
if (pos > loop.end) pos = loop.start + ((pos - loop.start) % (loop.end - loop.start));
```

That modulo is the whole trick: divide by the loop length and keep the
remainder.

### Mute, solo, and why the slider does not move

Watching what practice actually involves: muting an instrument to play its part
is constant, soloing one to learn it is frequent, and setting something to 37%
almost never happens. A slider makes the rare action easy and the constant one
fiddly — solo would mean dragging five sliders to zero and back.

So each stem has **M** and **S** buttons, as a mixing desk has had for fifty
years, for the same reason: mute and solo are instant, reversible, and they
leave the level setting intact.

**The row dims instead of the slider moving.** Moving the slider to zero would
destroy the level that mute exists to remember — unmute would put you back at
100% rather than your 40%. Dimming the row shows what is silent while the
setting survives. Soloing dims the other five at once, so one glance tells you
what you are hearing.

**Keys 1-6** mute stems, **space** plays and pauses, **arrows** skip five
seconds, **Esc** clears the loop. You are holding an instrument; reaching for
the mouse breaks practice in a way a keystroke does not.

---

## 12. Code structure

### The repository

```
backend/     the Python app, installed with `pip install -e backend`
frontend/    the React app (Vite + TypeScript)
docs/        this file and CONTEXT.md
data/        tracks and uploads - never in version control
```

Running it in development takes two servers: `woodshed serve` for the API on
:8000, and `npm run dev` inside `frontend/` for the app on :5173. Vite forwards
`/tracks`, `/stems` and `/jobs` to the API, so the browser only ever sees one
origin and the code uses plain paths that also work in production. After
`npm run build`, the backend serves the finished files itself.

Separating backend from frontend now means the React port becomes a change
inside one folder, rather than a reorganisation of everything at once.

### The front end

```
frontend/src/
├── audio/
│   ├── AudioEngine.ts     all the sound. ~330 lines, zero React
│   └── types.ts           StemName, Loop, PlayerState
├── api/
│   ├── client.ts          every call the browser makes
│   └── types.ts           Track, BeatData, Job
├── hooks/
│   ├── usePlayer.ts       one engine, its state mirrored into React
│   └── useKeyboard.ts     space, arrows, 1-6, esc
├── components/
│   ├── Waveform.tsx       canvas, bar lines, drag-to-loop
│   ├── Transport.tsx      play, seek, clock, loop chip
│   ├── Mixer.tsx          six stems: mute, solo, level
│   ├── PracticePanel.tsx  speed, pitch, master
│   └── Dropzone.tsx       upload
└── App.tsx                assembles it
```

**React never touches the audio.** `AudioEngine` is a plain TypeScript class
owning the graph, the six sources, the stretcher and the loop. It imports
nothing from React; React owns the screen and calls methods on it.

That separation is not stylistic. React re-renders constantly, and an audio
graph is long-lived and timing-sensitive — rebuilt on render, the
sample-accurate sync between stems would collapse immediately. So the engine
lives in a ref, created once, and a thin hook passes messages.

**Position deliberately never goes through React.** The waveform and the clock
run their own animation frame and read `engine.position` directly. Only
discrete changes — playing, levels, loop points — become React state.
Re-rendering sixty times a second to advance a playhead would be pure waste.

**Why TypeScript.** The engine passes stem names, level maps, loop objects and
buffers between a dozen methods, and those are exactly the places a typo
becomes a silent `undefined` at runtime. Renaming one field in the API response
during the refactor broke the old JavaScript player invisibly; in TypeScript
the editor flags every use the moment it changes.

### The backend

Layered, so that each file has one job and a new feature has an obvious home.

```
backend/woodshed/
├── config.py            all tunable values, in one place
├── tracks.py            what a track is, and how one is identified
│
├── api/                 HTTP only — no logic lives here
│   ├── app.py           assembles the application, mounts routers
│   ├── deps.py          shared validation (is this a real track id?)
│   └── routes/
│       ├── tracks.py    upload, list, fetch one
│       ├── stems.py     serve the audio
│       ├── analysis.py  beats now; chords and key later
│       └── jobs.py      progress streams
│
├── audio/               the slow half — knows nothing about HTTP
│   ├── separation.py    song -> six stems
│   ├── encoding.py      ffmpeg: Opus copies, audio out of video
│   ├── mixing.py        stems + levels -> one file
│   └── analysis/
│       └── beats.py     tempo and beat times, from the drum stem
│
├── jobs/
│   └── registry.py      work that outlives the request that asked for it
│
├── storage/
│   ├── base.py          what the app may assume about where files live
│   └── local.py         the filesystem implementation
│
└── cli.py               turns typed text into calls, nothing more
```

### The rules that keep it this way

**Routes contain no logic.** `api/routes/*` validates input, calls something in
`audio/` or `tracks.py`, and shapes the response. That is why the CLI and the
web API can share every line underneath them — neither owns the work.

**`audio/` knows nothing about the web.** No request objects, no HTTP status
codes, no FastAPI imports. It takes paths and track ids and returns data. That
is what makes it testable, and what would let it run on a separate worker
machine unchanged.

**Files are reached through `storage/`.** Nothing else builds a path by hand.
When tracks move to object storage, one class changes and no route, service or
audio module notices.

**Jobs are behind a registry.** The in-memory implementation is honest about
what it is: a finished track is already on disk, so losing tickets on restart
costs nothing. Swapping it for a Redis-backed registry is one class.

**`config.py` holds the values that differ between machines.** No module
hardcodes a path, a model name or a bitrate.

### Where a new feature goes

Chord detection, key detection, lyric alignment — every one of them follows the
same path, which is the point of this shape:

```
1.  audio/analysis/chords.py    detect(track_id) writes chords.json
                                load(track_id) reads it back
2.  api/routes/analysis.py      one endpoint, four lines
3.  the front end               fetch it, draw it under the waveform
```

No new layer, no change to anything that already works.

---

## 13. What comes next

| Phase | What | Status |
| --- | --- | --- |
| 0 | The workbench | ✅ |
| 1 | Separation | ✅ |
| 2 | What audio actually is | ✅ |
| 3 | The command-line tool | ✅ |
| 4 | The browser player | ✅ |
| 5 | A server, so the two halves meet | ✅ |
| 6 | Speed and pitch, independently | ✅ |
| 7 | Loops that land on the beat | ✅ |
| 8 | More instruments than six | Partly done |
| 9 | Something you can hand to someone | |

**Phase 8 — more instruments.** Already partly done by using the six-stem model.
Going further means chaining models, and the largest open model needs far more
graphics memory than this machine has.

**Phase 9 — shipping.** A local desktop app (costs nothing, no uploads, minimal
legal exposure, but no phone support) or a cloud service (works everywhere, but
you pay for GPU time and take on responsibility for other people's music).

---

## 14. Glossary

| Term | Meaning |
| --- | --- |
| **Stem** | An audio file containing one instrument, extracted from a finished mix |
| **Source separation / demixing** | The task of producing stems from a mix. Two names for one thing |
| **Model / checkpoint** | The trained AI file that does the separating. You download it; you do not make it |
| **Demucs / Spleeter / RoFormer** | Specific models. Spleeter (2019) is audibly behind; Demucs is the dependable default; RoFormer is the current best |
| **Bleed** | Traces of one instrument left behind in another stem |
| **Artifact** | Watery or smeared sound where an instrument was removed |
| **Sample** | One number describing speaker position at one instant |
| **Sample rate** | Samples per second. 44,100 is the CD standard |
| **Bit depth** | How precisely each sample is stored. 16-bit is CD standard |
| **Channels** | Separate lists for left and right. 2 = stereo |
| **Gain** | Volume as a multiplier. `1.0` unchanged, `0` silent |
| **Decibel (dB)** | A loudness unit matching how ears perceive, not how numbers work |
| **Clipping** | Values beyond ±1.0 flattened — distortion, not loudness |
| **Normalising** | Scaling a whole mix so its loudest point just fits |
| **Hash** | A fixed-size fingerprint computed from a file's bytes |
| **Audio graph** | Sources connected through processing nodes to the speakers |
| **Audio clock** | The sound card's own clock, used for sample-accurate scheduling |
| **Buffer** | Decoded audio held in memory, ready to play |
| **VRAM** | Graphics card memory. Limits how much audio the model processes at once |
| **Time-stretching** | Changing speed without changing pitch, or the reverse |
| **Opus** | A modern compressed audio format, roughly a tenth the size of WAV |
