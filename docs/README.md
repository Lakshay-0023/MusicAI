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
12. [Phase 10 — Where the bars start](#12-phase-10--where-the-bars-start)
13. [Phase 11 — The chords](#13-phase-11--the-chords)
14. [Phase 12 — Lyrics, and the chord sheet](#14-phase-12--lyrics-and-the-chord-sheet)
15. [Code structure](#15-code-structure)
16. [What comes next](#16-what-comes-next)
17. [Glossary](#17-glossary)

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
        phases 0–3, 5, 7, 10 ✅                     phases 4, 6, 7 ✅, 8–9 to go
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

# The beat and bar model — --no-deps so it cannot touch torch (see phase 10)
.venv\Scripts\python.exe -m pip install beat-this rotary-embedding-torch --no-deps

# Whisper, for lyrics — the same --no-deps rule (see phase 12)
.venv\Scripts\python.exe -m pip install openai-whisper --no-deps
.venv\Scripts\python.exe -m pip install tiktoken more-itertools
```

### Verify

```powershell
ffmpeg -version
.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available())"   # must print True
.venv\Scripts\python.exe -c "import beat_this; print('beat model ok')"
```

### Use

```powershell
# Split a song into six stems — slow the first time, instant afterwards
woodshed split "song.mp3"

# Render a practice track
woodshed mix "song.mp3" --vocals 0 --drums 0.1 --out practice.wav

# List what has been split
woodshed list

# Find (or redo) the beats and bar starts of a song already split
woodshed analyse "song.mp3"

# Find the chords, printed bar by bar (--full-mix lets it hear vocals and drums too)
woodshed chords "song.mp3"

# Write down the lyrics from the vocals, line by line with times
woodshed lyrics "song.mp3"

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

### Separating long songs in chunks (added later)

A 5.7-minute song failed with **"Unable to allocate 687 MiB for an array with
shape (6, 2, 15001600)"**. Given a whole song, Demucs builds all six stems for
*all of it* in memory at once: 6 stems × 2 channels × 15 million samples × 4
bytes = 687 MB in one block, plus working copies. With a browser and editor
open, the laptop had about 0.5 GB free.

So now **every song goes through in chunks**:

```
|----- chunk 1 -----|
                |XXXX----- chunk 2 -----|
                                    |XXXX----- chunk 3 -----|
                 ^ 4 s overlap, crossfaded
```

1. The upload is first **decoded to a plain WAV** on disk (ffmpeg), so any
   piece of it can be read without loading the rest.
2. Each 30-second chunk is read, separated, and its stems are **appended** to
   the six stem files before the next chunk is read. Only one chunk is ever
   in memory, so a 3-minute song and a 15-minute live set need the same RAM.
3. Neighbouring chunks overlap by 4 seconds, and across the overlap one
   **fades out as the next fades in**. Cutting with no overlap would click:
   the model sees less context at the very edge of a chunk, so its output
   there differs slightly from the same moment heard mid-chunk. Demucs does
   exactly this inside itself, on smaller pieces, for the same reason.

**Measured on that song:**
- It separated in 86 s, and the stems are exactly the original's length.
- The Phase 2 check (stems add back up to the original) shows **no seams**:
  the leftover error around each join is in the same range as in the middle of
  a chunk.
- 60-second chunks still crashed with ~0.5 GB free. 30-second ones peaked at
  about 0.9 GB of RAM and finished, so 30 s it is
  (`separation_chunk_seconds` in `config.py`).

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

That is analysis, so it belongs in the kitchen. `audio/analysis/beats.py` runs
once per song and writes `beats.json` next to the stems.

> This section describes the first version, a hand-written rule from librosa.
> It is still in the code as a fallback, but [Phase 10](#12-phase-10--where-the-bars-start)
> replaced it with a trained model that also finds where bars start.

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
harder problem and a different library — and is what Phase 10 added.

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

## 12. Phase 10 — Where the bars start

**What was built:** the beat finder was replaced. It now uses a small trained
neural network, **Beat This!**, which finds the beats *and* the **downbeats**,
and works out how many beats are in a bar. `beats.json` gained two fields, and
the bar lines, loop snapping and "bars 13–17" labels now use real bar starts
instead of a guess.

**Why now:** this is the first step towards a chord finder. Chords change on
beats, and nearly always on the **first beat of a bar**. A chord sheet built on
a bar grid that is one beat out puts every chord change in the wrong place.

### Words first: beat, downbeat, meter

```
beat:      1   2   3   4 | 1   2   3   4 | 1   2   3   4
           ↑               ↑               ↑
        downbeats — "the one", where each bar starts

meter = how many beats per bar: 4 for most pop and rock, 3 for a waltz
```

A **pickup** (or anacrusis) is a few notes *before* the first downbeat — "Happy
Birthday" starts on one. Phase 7's rule treated the first beat it heard as
"1", so a song that opens on a pickup had every bar line shifted.

### Two ways to find beats

**Phase 7: a hand-written rule** (`librosa.beat.beat_track`). Someone decided,
in code, what a beat is:

1. **Onset strength** — for each ~23 ms slice, how much louder did it just get?
   Drum hits give tall spikes.
2. **Tempo** — which gap between spikes repeats most? That gap is one beat.
3. **Dynamic programming** — choose the beat times that sit on strong spikes
   *and* stay evenly spaced. Every combination is scored and the best kept.

It is fast and needs no model. But it knows nothing about bars, it needs clear
hits (hence the drum stem), and it assumes one steady tempo.

**Phase 10: a learned model.** Nobody writes down what a beat is. Instead, a
network was shown thousands of songs that people had tapped along to by hand,
and it learned the pattern itself. For every 20 ms of audio it outputs two
numbers:

```
audio ─▶ spectrogram ─▶ network ─▶ P(beat here)     ▁▁█▁▁▁█▁▁▁█▁▁▁█▁
                                  P(downbeat here)  ▁▁█▁▁▁▁▁▁▁▁▁▁▁█▁
                                         peaks = the beats and bar starts
```

Because it learned from real music rather than from a rule about drum hits, it
hears bar starts in the harmony and the phrasing too. It needs no drums, and it
follows a tempo that drifts. This is the same idea apps like Chordify use.
Theirs is private, while Beat This! (from the Johannes Kepler University, 2024)
is open source and small enough for this machine.

### Why it listens to the whole song now

The rule was given the drum stem because a guitar chord fooled it. The model was
trained on **full mixes**, so that is what it should hear — and the chords and
melody are part of how it recognises bar starts. The original upload is not
kept, but the stems add back up to the song (Phase 2: mixing is addition), so
`beats.py` loads all six at 22.05 kHz mono and sums them. That is about 130 MB
for a four-minute song, and 22.05 kHz is the rate the model was trained at, so
nothing is resampled.

### Meter and tempo from the grid

Once beats and downbeats are known, two numbers fall out with no extra model:

- **Beats per bar:** count the beats between each pair of downbeats, take the
  usual answer (the median). A waltz gives 3.
- **Tempo:** 60 ÷ the usual gap between beats. The median again, so one missed
  or doubled beat cannot drag it.

The **extend backwards** trick from Phase 7 is reused unchanged on both lists.
It only needs a list of evenly spaced times, and it does not care whether they
are beats or bars.

### Why the model is loaded every time, then thrown away

The graphics card has 4 GB. Demucs needs most of it during separation. A beat
model kept loaded "for speed" would quietly hold some of that memory forever,
and the next separation would run out. Loading it takes a second or two, so
`beats.py` loads it, uses it, deletes it and tells PyTorch to give the memory
back (`torch.cuda.empty_cache()`).

### Why it is installed with `--no-deps`

`beat-this` declares that it needs `torch`. If pip decides the torch already
installed does not satisfy that, it downloads one from PyPI — the CPU-only
build — and separation silently becomes many times slower (Phase 0).
`--no-deps` means "install only this package, touch nothing else". The packages
it actually uses (`einops`, `soxr`, `tqdm`, `torchaudio`) were already present,
and the plain ones are listed in `pyproject.toml`.

### Keeping the old way as a fallback

If `beat_this` cannot be imported, `detect()` falls back to the Phase 7 rule
and records `"method": "librosa"`, guessing bars as every 4th beat as before.
The app never breaks because an optional model is missing.

### What changed in the data

```
GET /tracks/{hash}/beats  ->  {
  "tempo": 83.35,
  "beatsPerBar": 4,          now measured, not assumed
  "beats": [...],
  "downbeats": [...],        new: where each bar starts
  "method": "beat_this"      new: which detector produced it
}
```

**Old songs upgrade themselves.** `load()` treats a `beats.json` without
`downbeats` as missing, so the route re-analyses it the first time the song is
opened. No migration script.

**The front end asks one question:** "where do bars start?". `lib/bars.ts`
answers it with the downbeats when they exist, otherwise every `beatsPerBar`-th
beat. The waveform's bar lines, the loop snapping and the loop label all call
it, instead of each repeating the "every 4th beat" guess.

---

## 13. Phase 11 — The chords

**What was built:** `woodshed chords "song.mp3"` prints the song's chords bar by
bar, and `GET /tracks/{hash}/chords` serves them to the browser. There is no
interface for them yet. This step is about getting the chords *right*, checked
against a chord sheet you trust, before anything is drawn.

```
    1 | Em  .   .   .   | C   .   .   .   | G   .   .   .   | D   .   .   .   |
    5 | Em  .   .   .   | C   .   .   .   | G   .   D   .   | ...
```

A chord is written on the beat it arrives, and `.` while it carries on.

### No language model, and why

Chord sites get their chords one of two ways. On Ultimate Guitar and similar
sites, **people** work them out by ear and type them in. Apps like Chordify use a
**model** like the one here. Finding chords is a music-analysis task called
*automatic chord estimation*. It needs a network that reads a spectrogram, not
one that reads text. An LLM cannot hear that bar 12 is E minor. At most it could
*explain* a progression once it has been found.

### Step 1: what the model sees — the constant-Q transform

A normal spectrogram (Phase 7's idea) spaces its frequency bins evenly: 0 Hz,
10 Hz, 20 Hz... Music is not spaced evenly. Each octave *doubles* the frequency,
so the twelve notes from A2 (110 Hz) to A3 span 110 Hz, while A5 to A6 spans
880 Hz. Even bins waste most of their resolution up high and blur the low notes
together.

The **constant-Q transform (CQT)** spaces its bins like piano keys instead.
Here it uses **two bins per semitone over six octaves: 144 bins**. A note is
then always the same number of bins above the one an octave below it,
whichever octave it is in. That regularity is what makes chords recognisable.

```
          C    C#   D    D#   E    F    F#   G  ...   (two bins each)
octave 3  ░░   ░░   ░░   ░░   ██   ░░   ░░   ██      E and G sounding
octave 4  ██   ░░   ░░   ░░   ░░   ░░   ░░   ░░      C sounding
                                                → C major (C, E, G)
```

**Chroma**, which you will see mentioned everywhere, is the CQT folded into 12
bins, one per note name, with the octaves added together. BTC uses the full 144
bins rather than chroma, because *which octave* matters too. The lowest note
is usually the root, which is how it tells Am (A in the bass) from C6 (C in
the bass), though both contain the same four note names. It does not name
inversions (C/E), because those are not among its 170 chords.

The values are then **logged** (`log(|CQT| + 1e-6)`). Loudness is judged by
ratios, by ears and by models trained on what ears care about. Without the log,
one loud bass note would drown every other number.

### Step 2: the model — BTC

**BTC (Bi-directional Transformer for Chord recognition)**, Park et al., 2019.
It is MIT-licensed, so it can be used and shipped. It knows **170 chords**:

```
12 roots × 14 types   maj  min  7  maj7  min7  6  min6  dim  aug
                      dim7  m7b5  m(maj7)  sus2  sus4
+ N (no chord)  + X (a chord it can hear but not name)
```

It cuts the song into **10-second windows of 108 frames** (one per ~93 ms).
Inside a window, every frame can look at every other frame, once looking
forwards in time and once backwards. That is the "bi-directional" part, and it
is what *attention* means in a transformer. So the guess for a frame is
informed by what comes before and after it, the same way you know a passing
note is not a chord change because you heard what followed.

The output is, for every frame, a probability for each of the 170 chords.

**Normalising the input.** The weights file also stores the *mean* and *spread*
of the training data. Our features are scaled by exactly those numbers
(`(x − mean) / std`) before the model sees them. Skip that, and every value is
off by a constant and the answers are nonsense. It is the most common mistake
when reusing someone else's model.

**`model.eval()`** switches off *dropout*, a training trick that randomly
blanks parts of the network so it cannot rely on any one part. During training
that helps. When you want an answer, it is just noise.

### Why the code is copied in, not installed

BTC is a GitHub repository, not a pip package, and its code uses `np.float`.
That was removed from numpy years ago, so the original crashes on numpy 2. So
the network itself, about 200 lines, lives in `audio/analysis/btc/` with its
licence. Two rules apply:

- **Every class and attribute name is unchanged.** The weights file stores each
  number under a name like
  `self_attn_layers.self_attn_layers.0.attn_block.multi_head_attention.query_linear.weight`.
  Rename anything and `load_state_dict` refuses to load.
- **Training code was left behind**, and with it three dependencies we would
  never use.

The weights (12 MB) **download on first use** into `data/models/`, the same way
Beat This! fetches its own. They are written under a temporary name and renamed
at the end, so an interrupted download is never mistaken for a finished one.

### Step 3: one decision per beat

This is the reason Phase 10 came first.

```
frames (~93ms):  Em Em Em G  Em Em | C  C  C  C  Am C |
                          ↑ passing note        ↑ stray frame
per beat:            Em            |        C         |
```

For each beat, the probabilities of every frame inside it are **averaged**, and
the likeliest chord wins. Averaging rather than voting means a beat that is
steadily 60% sure of Em outweighs one stray frame that is 90% sure of G.
Consecutive beats with the same chord are then merged into one entry:

```json
{ "start": 12.48, "end": 15.31, "label": "E:min", "name": "Em" }
```

`label` is the standard research notation (Harte notation, `root:quality`).
`name` is how a chord sheet writes it.

### Step 4: which instruments it hears

By default, **Bass + Guitar + Piano + Other**: the harmony, without the drums or
the voice. Drums are pure noise to a chord model. A sung melody note can look
like a chord note: sing a D over a C chord and the model hears something closer
to Cadd9.

The model was trained on full mixes, though, so this is a guess to test, not a
fact. `--full-mix` lets it hear all six stems. Run both on a song whose chords
you know, and keep whichever is right more often. The setting is
`chord_stems` in `config.py`.

### What accuracy to expect

Published results for models like this on pop and rock: about **80%** of the
song's time correct on plain major/minor, and about **65%** once 7ths, sus
chords and inversions count. Chordify is in the same range. Expect:

- **Mostly right:** the main chords of verses and choruses.
- **Sometimes wrong:** maj vs maj7, sus4 resolving to maj, chords on weak beats.
- **Never shown:** inversions. A C/E is reported as plain C.
- **Often wrong:** fast jazz changes, and songs where the harmony is only
  implied by a bass line and a vocal.

A test with synthetic C, Am, F and G7 chords, played as tones with known
answers, came back exactly right, including the 7th.

### The chord view in the player

The chords are shown two ways: a map of the whole song, and the sheet you
read while playing.

```
┌ waveform ──────────────────────────────────────────────────────┐
│ ▁▃▅█▅▃▁▃▅▇▅▃▁▃▅█▅▃▁▃▅▇▅▃▁▃▅█▅▃▁▃▅▇▅▃▁                             │
├ chord lane ────────────────────────────────────────────────────┤  1. the map
│ Em    │ C     │ G  │ D  │ Em    │ C     │ G  │ D  │ ...            │
└────────────────────────────────────────────────────────────────┘
┌ Chords ─ pitch +2 · Chords All|Normal|Minimal · [Simple] · Capo − 2 + · [Focus] ┐
│   (faded)  Tu mera khuda tu hi dua                                        │
│ ┃ Bb7            Ebm                                                     │  2. the sheet:
│ ┃ E dil hai      mushkil mujhe          ← the line being sung, in a band  │     lyrics with chords,
│   F#                 Bbm7                                                 │     like simple karaoke
│   Aajmaati hai       teri kami          ← coming up, clearly readable     │     (phase 12)
└──────────────────────────────────────────────────────────────────────────┘
```

**1. The chord lane is the map.** It sits directly under the waveform, on the
same time axis, so the two read as one surface. Its job is the song's *shape*:
where the chorus comes back, how long the bridge is. Click a block to jump
there.

**Colour follows the circle of fifths.** Each root gets a hue, and roots a
fifth apart (C→G→D→A…) get neighbouring hues. Chords a fifth apart are the ones
that live together in a key, so a song's usual chords form a family of
colours, and a repeated section *looks* repeated before you hear it. The
formula is one line: `hue = (root × 7 mod 12) × 30°`. Multiplying by 7 walks
the circle of fifths, because seven semitones is a fifth.

**2. The sheet is the lyrics, with chords written in** — see phase 12.

**What was tried first, and dropped.** Two earlier designs, both removed after
using them:
- **A beat-by-beat chart:** four bars a row, each beat with a tick that lit up
  as it passed. Accurate, but too much: it is a session musician's view, and
  reading beats was more work than playing them.
- **A big "Now / Next" display** above the sheet: the current chord huge, the
  next one with a countdown in beats. It sounded useful, but it was a second
  thing to watch. The sheet already shows the next line *and its chords*, so
  it was redundant.

What people actually learn songs from is lyrics with chords above the words,
so that is the whole view. The beat grid still does its job underneath: it is
why every chord change lands on the right moment.

For songs with no singing, a simpler fallback remains: chords bar by bar, four
bars a row, names only. Click a bar to jump there.

### Choices that change the names, not the chords

The server stores one thing: research notation (`E:min7`). How it is
*written* depends on choices the player makes while practising, so that
translation happens in the browser (`lib/chords.ts`). Changing a choice is
instant and never touches the server.

| Choice | What it does | Why |
| --- | --- | --- |
| **Pitch** (practice panel) | Names follow it: +2 turns Em into F#m | Chords should name what you *hear* |
| **Capo** | Shows the shapes to play: capo 2 turns F#m into Em | Guitarists think in shapes |
| **Simple** | Drops 7ths, 6ths and sus: Cmaj7 → C | Learning a song before polishing it |

Capo, Simple and the Chords level are remembered between visits (browser
storage, wrapped so a blocked storage never breaks the page).

### How many chords: All · Normal · Minimal

The model decides a chord on **every beat**, under a second each. So a passing
bass note, a melody note, or a moment of doubt between two similar chords (Em
and G share two of their three notes) becomes a chord change lasting a
fraction of a second. A human transcriber ignores those blips.

**The proper fix: make changing chord cost something.** Professional chord
decoders (Chordino, madmom, ChordFormer) do not take each beat's likeliest
chord on its own. They find the best *path* through the song, where every
change has a price. A real change easily pays it: the new chord is clearly
likelier for the bars it lasts. A one-beat blip cannot, so it never appears.

This is the **Viterbi algorithm**, the standard way to find the best path
through a sequence of guesses. Beat by beat, it keeps for every chord the best
score of any path ending on it:

```
stay on chord k:     best[k]               + evidence for k on this beat
switch to chord k:   best overall − penalty + evidence for k on this beat
```

Then it traces back the choices that built the winning score. Scores are
log-probabilities, so a penalty of 3 means a change must be about e³ ≈ 20
times better supported than staying put.

**One penalty per level, all decoded on the server** and saved side by side
in `chords.json`, so switching is instant:

| Level | Penalty | Ae Dil Hai Mushkil | Besabriyaan |
| --- | --- | --- | --- |
| **All** | 0, every beat for itself | 156 changes | 101 |
| **Normal** (default) | 3 | 103 | 92 |
| **Minimal** | 6 | 89 | 73 |
| *(too far)* | 12 | 52 | 23: real changes vanish ("D A G" loses its D and A) |

**What it replaced.** The first version tidied the chords afterwards, in the
browser, with hand-made rules: drop chords under half a bar, under 1.5 s at
the strictest, and at most two per bar. Tuned on one song, the strict setting
was **too sparse** and removed real changes. A rule about *length* cannot tell
a short real chord from a short mistake. A cost weighed against the *evidence*
can: it keeps a short chord the model is sure of, and drops a long-ish one it
was never sure about.

The browser still does one small job (`lib/tidy.ts`). Chords that *look* the
same once displayed merge, so with Simple on, G → G7 → G reads as one G.
Songs analysed before this are re-analysed once when opened, which takes
seconds.

### Focus mode

Press **F**. Upload, song picker, mixer and practice panel disappear. The
waveform, transport, chords and lyrics stay, and get bigger. Setting up and
playing are different activities, and while playing, every control on screen
is clutter. One key back.

### Following the song without re-rendering

The same rule as the waveform and the clock: **position never goes through
React.** Each view runs its own animation frame and writes straight to the
page — the text of Now/Next, a class on the current bar, the playhead's
`left`. Each frame does almost nothing: a binary search for the current chord,
and a DOM write *only if something changed*. React re-renders only when the
song, the chords or a choice changes.

### Loading order, and why

When a song opens, the browser asks for the **beats, then the chords, then the
lyrics**, each only after the last has answered. For a song never analysed,
each request triggers analysis on the server, and chord detection needs the
beats. Asked at once, the server would run the beat model twice and could have
three models loaded side by side on a 4 GB GPU. Chained, each runs once, alone. While it works,
the panel says *Listening for chords…*. If it fails, a **try again** link asks
for the chords alone, without reloading six stems.

New uploads now find chords during processing (`finding chords` in the
progress line). That step can fail, for example if the weights cannot be
downloaded offline, without losing the stems. The song finishes anyway, and the
player asks again later.

---

## 14. Phase 12 — Lyrics, and the chord sheet

**What was built:** the app writes down what is sung, word by word with the
moment each word starts, and shows it as a chord sheet: lyrics with every
chord written above the word it lands on. The current line is highlighted,
words light up as they are sung, and the sheet scrolls with the song. It works
on **any audio with singing in it**: released songs, your own band, a phone
recording. Nothing leaves the machine.

```
[Intro]  Em  C
G
Kaise bataaun main tumhein
D          Am
Mere liye  tum  kaun ho
[Outro]  Em
```

### Where lyrics on websites come from — and why not use them

Lyric sites and apps get their text from licensed databases (Musixmatch,
LyricFind) or from volunteers. Some, like LRCLIB, also have timings. They only
know *released* songs, though. A recording of your own band is in none of
them. So the lyrics come from the audio itself, which is **speech
recognition**.

### Whisper, on the vocals stem

**Whisper** is OpenAI's open-source speech recognition model. It was trained
on 680,000 hours of speech in about 100 languages, and it runs locally.

Whisper is a speech model, and a song is not speech: drums and guitars sit on
top of the voice and confuse it badly. Phase 1 already solved that. **The
Vocals stem is the voice alone**, as close to speech as singing gets. This is
the separation investment paying off a second time.

The model is **`turbo`**: large-v3, Whisper's most accurate, with a slimmer
decoder. It has 809 million weights.

### Fitting it on this laptop

Two memory problems, both solved in `lyrics.py`:

- **GPU (4 GB).** 809M weights × 4 bytes (32-bit) = 3.2 GB, too close to 4 GB
  once working memory is added. Stored as **16-bit (half precision)** it is
  1.6 GB. Whisper already computes in 16-bit on a GPU, so storing the weights
  that way loses nothing audible. The exception is its **normalisation
  layers**, which insist on 32-bit, so they are left alone.
- **RAM (~6 GB free).** Whisper's own loader reads the 1.6 GB file into memory
  *and* builds a 3.2 GB model beside it, nearly 5 GB at once. A first fix
  (memory-map the file, but still build the model in RAM) peaked at 3.2 GB.
  That still **crashed** with an access violation once the browser and editor
  were open. The final loader never builds the model in RAM at all:
  1. **Memory-map** the file, so its weights stay on disk until touched.
  2. Build the model on PyTorch's **meta device**: the outline of every layer,
     with shapes but no memory behind them.
  3. **Attach** the file's weights to that outline as they are (`assign=True`):
     still 16-bit, still on disk.
  4. **Move to the GPU**: each weight is read from disk straight into GPU memory.

  Measured: almost no extra RAM, 1.6 GB of GPU memory, 2.1 GB at peak while
  transcribing, all released afterwards. Two small pieces are not in the file
  and are made for real: the decoder's mask, and the table of which attention
  heads track timing. That second one is also why Whisper's own constructor
  cannot be used: it builds the table with an operation the meta device does
  not support.

Then, as with every model here, it is deleted and the GPU memory released the
moment the transcription is done.

### Words, with times

Asked for `word_timestamps`, Whisper reports when each word starts and ends.
It works this out from its **attention**: some of the heads in its decoder
consistently "look at" the part of the audio where the current word is spoken.
Following those heads across the transcript lines each word up with its moment
in the audio.

Three settings keep the output honest on music:

| Setting | Why |
| --- | --- |
| `condition_on_previous_text=False` | By default each 30 s chunk is told what the last one said. On singing, one misheard line then repeats down the whole song. |
| `hallucination_silence_threshold=2.0` | Over long silences (an instrumental break on the vocal stem), Whisper can *invent* words. This skips them. |
| **The language is told, not guessed** | See below. |

**Never let it guess the language.** The first version let Whisper detect the
language, from the loudest 30 s of vocals. On *Ae Dil Hai Mushkil* it said
English 35%, Turkish 14%, Russian 10%, with Hindi not in its top five. Having
decided "English", it wrote **English sentences for Hindi singing**: "Ae dil
hai mushkil" came out as "This soul is also my soul". Not a single word was
usable.

Told `language="hi"`, the same song came back nearly word-perfect:

```
e dil hai mushkil mujhe aajmaati hai teri kami
ye rooh bhi meri ye jism bhi mera
utna mera nahin jitna hua tera
```

So the language is a setting (`lyrics_language = "hi"` in `config.py`), and
`woodshed lyrics song.mp3 --language en` covers an English song. Hindi mode
copes with the odd English word in a Bollywood lyric. `"auto"` still exists,
but do not expect much from it on singing.

**Hindi and Urdu are treated as one.** Spoken, they are the same language;
written, Hindi uses Devanagari and Urdu the Arabic script. In auto mode
Bollywood songs are often detected as Urdu. Both are transcribed as Hindi,
because Devanagari is what the next step can read.

**The Triton warnings.** Triton is a GPU compiler Whisper uses to speed up
word timing. It does not exist on Windows, so Whisper falls back to slower
code and warns on every chunk. They are harmless, and they are now hidden so a
real error is not lost among them.

### Devanagari → Roman letters

Whisper writes Hindi most accurately in Devanagari. Asked to write Roman
letters directly, it tends to *translate into English* instead. So it writes
Devanagari, and `roman.py` converts the result into **casual Roman spelling**,
the way lyrics are written online. "कैसे बताऊँ" becomes "kaise bataaun", not the
scholarly "kaise batāūṁ".

Devanagari is a syllable script. Each consonant carries a built-in "a" (क is
*ka*), and vowel marks change it (कि *ki*, की *kee*). The rules are a table
lookup, except for one, which decides whether the result sounds like Hindi:

**Schwa deletion.** Spoken Hindi drops that built-in "a" in predictable
places:

```
end of a word:            दिल     di-la     → dil
between two vowels:       समझना   sa-ma-jha-na → samajhna
but never stacking three
consonants:               ज़िंदगी   zin-da-gi → zindagi   (not zindgi)
```

Without it, every word comes out sounding like Sanskrit. A few casual-spelling
conventions finish the job: long vowels doubled mid-word but not at the end
(जाना *jaana*, तेरी *teri*), में as *mein*, a nasal before p/b/m written as m
(संभल *sambhal*). Checked against 29 common lyric words, it matched all 29.
It is rules, not a model, so some spellings will differ from yours. Editing
lyrics is the planned fix.

### Words into lines

The plan was "a pause between words starts a new line". It never fired: on
sustained singing Whisper reports **no gaps at all**. Each word runs right up
to the next and swallows the breath in between ("gujaara" lasting 1.5 s).

The breath is still in the audio, though, as a **dip in the vocal's loudness**.
It is not true silence, because reverb fills it in, but it is a dip. So:

1. A line ends where Whisper ended a segment, or at a real pause (over 0.6 s).
2. A line still over **8 words** is split at its **deepest breath dip**,
   measured over the end of one word and the start of the next. That repeats
   until every line fits, never leaving a single word alone.

Result on the test song:

```
Ye rooh bhi meri ye jism bhi mera
Utna mera nahin jitna hua tera
Junoon hai mera
Banu main tere kaabil tere bina gujaara
```

Mostly at real phrase ends, sometimes one word off. **What was tried and
dropped:**
- Plain silence detection: the reverb meant the voice was almost never silent.
- Choosing every break in the song together to fit an ideal line length: the
  dip signal is too noisy for that to beat the simple rule.

Perfect lines from audio alone are not realistic. The edit-lyrics step
(phase 13) is the real fix.

### Precise word times: a forced aligner

Whisper's word times are a by-product of how it reads, not a measurement. On
singing it makes **every word start the instant the previous one ended**, so
the pause before a word, and often a held note, is swallowed into the next
word's start. A chord landing in that pause gets pinned to the wrong word.
This was the main source of misplaced chords.

The fix is the tool professional karaoke and lyric-sync services use: a
**forced aligner**. It does one job. Given the audio and the words already
known to be in it, it finds exactly where each word is. Ours is **MMS**
(Meta's Massively Multilingual Speech, 1,100+ languages). It ships with
torchaudio, so nothing extra was installed; the weights (1.26 GB) download
once to `data/models/mms/`.

**How it works.** The model hears the audio as a stream of *letter*
probabilities, one set every 20 ms: "this moment sounds like *a*, the next
like *a*, then *y*…". Given the words in order (in plain a–z, which is why
the Roman lyrics matter), it finds the path through those probabilities that
spells them out (the same "best path" idea as the chord decoder). Each word's
span is where its letters were heard.

**Line by line.** Each line is aligned only within its own window (Whisper's
span plus a second either side), so a badly misheard line cannot drag the
rest of the song off with it. A line that fails keeps Whisper's times.

**Measured, not assumed.** A sung word starts with a burst of vocal energy,
an *onset*, which librosa can detect in the vocal stem independently of both
models. Comparing each word's start with the nearest onset, over both songs:

| | Whisper's word starts | Aligner's word starts |
| --- | --- | --- |
| Typical distance from the real vocal onset | 0.13–0.14 s | **0.03–0.04 s** |
| Within 0.15 s of an onset (Ae Dil Hai Mushkil) | 55% | **92%** |

The aligner was better even on the words it was least confident about, so it
is used for every word. It takes 10–20 seconds a song; older songs are
re-timed the first time they are opened, without re-running Whisper.

### When does a line really stop ringing?

After a line's last word there can be more singing the words do not cover: a
long "aaa" on the final syllable, a fade. Chords played under it belong to
that line. So from the last word's end, the vocal's loudness is followed
until it has dropped 15 dB below the line's own level and stays there for
0.3 s, so a breath does not count. It never goes past the next line's start.
That time is saved as the line's `held`. On "Besabriyaan", the last line's
words end at 52.1 s and the voice carries on to 57.0 s.

**An earlier version stretched the last word itself** to that point, back when
Whisper's rough ends were all there was. With measured ends, that went wrong:
a D landing on the dying end of "jahaan", just before "Besabriyaan", looked
mid-word and stayed on "jahaan". Now the word keeps its measured end, and
`held` is used only for chords *after* the last word.

### Pinning chords to words

Both files are lists of times, so this is bookkeeping, not guesswork. It runs
in the browser (`lib/sheet.ts`), keeping `chords.json` and `lyrics.json`
independent: re-transcribing never touches the chords.

For each chord, the first rule that fits wins:

1. **A word is being sung:** the chord goes on that word. Exception: the
   chord is *anticipating* the next word. That means either the next word
   starts under 0.15 s later, or the chord hits the **last quarter** of this
   word with the next word **within a beat**. Players change chord just before
   the singer, and a chart writes it over the coming word.
2. **Within one beat before a word:** a lead-in. It goes on that word. ("A
   beat" allows 0.15 s extra for detection's coarseness.)
3. **Under the line's held note or fade, or within a bar after it:** the line
   is still ringing, so the chord stays **at the end of that line**, written
   after the last word.
4. **Within one bar before the next line:** the run-up into it. It goes on the
   next line's first word.
5. **Anything deeper into a long gap:** its own Intro / Instrumental / Outro
   line. **"No chord" (N)** gets no symbol.

**The first version got this wrong.** It sent *every* chord in a pause of up
to two bars to the next word, assuming a chord in a pause is a lead-in.
Usually it is the opposite: it is still part of the line just sung. Combined
with Whisper's early word ends, the G played under a held "Besabriyaan" jumped
down to the next line, and the last line's trailing chords fell into the
instrumental. Now:

```
           Bm   A               G
Kyon suchna hai jaana kaha                ← G under the held "kahaa…"
             Bm  A G
Jaaye vahi  le  jaaye jahaan              ← A G under the held "jaaye…"
D A G                       D
Besabriyaan                               ← the D moved off "jahaan", onto here
D                           A G Bm A
Besabriya                                 ← chords under the long final fade
[Instrumental]  G  Bm  A  Em  F#m  G  D
```

The song's repeating **D A G** now lines up with each "Besabriyaan".

Finally, **every line states the chord it opens on**, dimmed, if that chord
started earlier. Any line can then be read on its own, which is what you need
after jumping into the middle of a song.

### Drawing it so chords cannot drift

Each word is a tiny two-row stack, chord on top and word underneath:

```
┌─────┐┌───────┐┌────┐┌───────┐
│ G   ││       ││    ││       │
│Kaise││bataaun││main││tumhein│
└─────┘└───────┘└────┘└───────┘
```

Chord and word share one box, so however a line wraps on a narrow screen, the
chord stays over its word. A chord name wider than its word ("Cmaj7" over
"main") widens the box rather than overlapping the next word. The boxes are
invisible; what you see is an ordinary chord sheet.

### Following the song

The same rule as everywhere else: an animation frame, binary searches, and DOM
writes only when something changes.

Like simple karaoke, and deliberately nothing more:

- **The current line sits in a soft band** with an accent bar on its left.
  It is chosen 0.3 s early, so your eyes arrive before the voice does.
- **Coming lines stay clearly readable**, with their chords, so you can see
  the next change. **Lines already sung fade.** The top and bottom edges of the
  sheet fade too, a hint that there is more.
- **Only whole lines change.** An earlier version lit each word as it was sung
  and flashed the current chord. While playing, that was something to chase
  rather than read, so it went. The eye needs somewhere still to rest.
- **Scrolling:** the current line glides to a quarter of the way down, leaving
  a line of context above and the next few below. Scroll yourself and it waits
  four seconds before taking over again.
- **Click any word** to jump the song there.

### What to expect

- **Clear studio vocals:** most words right.
- **Phone recordings, heavy reverb, harmonies, fast rap:** noticeably worse.
- **Spelling of romanised Hindi:** consistent, but sometimes not the spelling
  you would choose.
- **First open of a song:** about a minute (the first run ever also downloads
  1.5 GB of model weights). After that it is saved, like everything else.

---

## 15. Code structure

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
├── lib/
│   ├── format.ts          times and titles for display
│   ├── bars.ts            where each bar starts
│   ├── chords.ts          names, transposing, capo, colours, bars
│   ├── sheet.ts           pins each chord to the word it lands on
│   ├── tidy.ts            All / Normal / Minimal: drops chord blips
│   └── prefs.ts           remembered choices, safe if storage is blocked
├── hooks/
│   ├── usePlayer.ts       one engine, its state mirrored into React
│   └── useKeyboard.ts     space, arrows, 1-6, esc, f
├── components/
│   ├── Waveform.tsx       canvas, bar lines, drag-to-loop
│   ├── ChordLane.tsx      the song's chords as a strip under the waveform
│   ├── ChordPanel.tsx     the options, and the sheet or bar list below them
│   ├── LyricSheet.tsx     lyrics with chords above, following the song
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
│       ├── analysis.py  beats and chords; key later
│       └── jobs.py      progress streams
│
├── audio/               the slow half — knows nothing about HTTP
│   ├── separation.py    song -> six stems
│   ├── encoding.py      ffmpeg: Opus copies, audio out of video
│   ├── mixing.py        stems + levels -> one file
│   └── analysis/
│       ├── source.py    which stems an analyser hears, summed to mono
│       ├── beats.py     tempo, beats and bar starts (Beat This!)
│       ├── chords.py    one chord per beat -> chords.json
│       ├── lyrics.py    Whisper on the vocals -> lyrics.json, word by word
│       ├── roman.py     Devanagari -> casual Roman letters
│       └── btc/         the BTC network, copied in with its MIT licence
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

## 16. What comes next

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
| 10 | Where the bars start (beats + downbeats) | ✅ |
| 11 | Chords, one decision per beat, shown in the player | ✅ built, being checked |
| 12 | Lyrics from the vocals, as a scrolling chord sheet | Built, being checked |
| 13 | Edit lyrics; key detection and per-song spelling | |

**Phase 13 — polishing the sheet.** An *edit lyrics* mode to correct misheard
words (each word keeps its timing, so chords stay put). Key detection, so a
song in E spells D# where a song in Bb spells Eb. Optionally, LRCLIB's
published lyrics as a correctness check for released songs. It is opt-in,
because it is the only feature that would send anything (a song title) off the
machine.

**Phase 8 — more instruments.** Already partly done by using the six-stem model.
Going further means chaining models, and the largest open model needs far more
graphics memory than this machine has.

**Phase 9 — shipping.** A local desktop app (costs nothing, no uploads, minimal
legal exposure, but no phone support) or a cloud service (works everywhere, but
you pay for GPU time and take on responsibility for other people's music).

---

## 17. Glossary

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
| **Downbeat** | The first beat of a bar — "the one" |
| **Meter** | How many beats make a bar. 4 for most pop, 3 for a waltz |
| **Pickup** | Notes before the first downbeat of a song |
| **Onset** | The moment a note or hit starts; a sudden rise in energy |
| **Chroma** | A song's energy folded into 12 bins, one per note name, ignoring octave |
| **CQT (constant-Q transform)** | A spectrogram whose bins are spaced like piano keys rather than evenly in Hz |
| **Attention** | A layer that lets each frame weigh every other frame when deciding what it is |
| **Dropout** | Randomly blanking parts of a network during training; switched off by `model.eval()` |
| **Normalisation** | Scaling inputs by the training data's mean and spread, so the model sees familiar numbers |
| **Speech recognition (ASR)** | Turning spoken or sung audio into written words |
| **Whisper** | OpenAI's open-source speech recognition model; runs locally |
| **Half precision (fp16)** | Storing numbers in 16 bits instead of 32: half the memory, same answers for inference |
| **Memory-mapping** | Letting the OS read a file from disk as parts are needed, instead of loading it all into RAM |
| **Schwa deletion** | Dropping the built-in "a" of Hindi consonants where speech drops it: दिल is *dil*, not *dila* |
| **Transliteration** | Writing the same words in a different script (Devanagari → Roman); not translation |
| **Circle of fifths** | The 12 notes ordered a fifth apart (C G D A E B…); neighbours share most of their notes |
| **Capo** | A clamp across a guitar's neck that raises every string; you play the same shapes, and they sound higher |
| **Harte notation** | The research format for chords: `E:min7`, `C`, `N` for no chord |
| **Weights / state dict** | The trained numbers of a model, stored by layer name |
