# Section 9: Engineering under constraints

[← Section 8, AI lyric correction](08-ai-lyrics.md) · [Index](README.md) · Next: [Section 10, Interview prep →](10-interview-prep.md)

The cross-cutting engineering: how the project fits five AI models onto a
laptop, how it is structured, how decisions were tested, and how it would
scale.

---

## 9.1 The constraint: a 4 GB GPU and about 6 GB of RAM

The project runs on an RTX 3050 Laptop GPU (**4 GB of VRAM**) with 8 GB of RAM,
of which only **about 5.9 GB** is visible to programs (the rest is reserved for
the built-in graphics), and often less than 1 GB is free with a browser and
editor open.

The models it runs:

| Model | Job | Memory approach |
| --- | --- | --- |
| Demucs `htdemucs_6s` | separation | `shifts=1`; songs in 30 s chunks |
| Beat This! | beats | loaded per call, then released |
| BTC | chords | tiny; loaded per call, then released |
| Whisper turbo (809M) | lyrics | 16-bit weights; built without ever sitting in RAM |
| MMS aligner | word timing | loaded per call, then released |

**The rule for every model:** load, use, delete, and call
`torch.cuda.empty_cache()` to give the GPU memory back. No model stays
resident, because the next job may need the whole card.

## 9.2 Real incidents, and what each taught

| What happened | Cause | Fix | Lesson |
| --- | --- | --- | --- |
| Separation crashed with an access violation | `shifts=2` held two full-length results in RAM | `shifts=1`: half the memory, twice as fast, small quality cost | Defaults assume big machines |
| "Unable to allocate 687 MiB" on a 5.7-min song | Demucs assembles all 6 stems for the whole song in RAM | Separate in 30 s chunks with 4 s crossfaded overlaps; verified seamless with the residual check | Make memory independent of input size |
| A test process died loading Whisper | Its loader holds the file *and* a 32-bit copy (~5 GB) | Memory-mapped file + model built on the meta device + 16-bit weights: almost no RAM | Never build big models in RAM |
| `CUDA error: unknown error` | The GPU driver stuck after many sleep/wake cycles | Restart the server; if it repeats, restart Windows | Not every error is in your code; check the hardware state (`nvidia-smi`) first |
| Separation silently ~15× slower | Installing a package replaced CUDA PyTorch with the CPU build | Install CUDA PyTorch last, `--force-reinstall --no-deps`; `--no-deps` for later model packages; always re-check `torch.cuda.is_available()` | Silent failures need explicit checks |
| `[vite] http proxy error … ECONNRESET` | The backend process crashed mid-request (low RAM) | Restart; close heavy apps | Read the error at the right layer |
| A fresh install failed with `WinError 206` | Windows' 260-character path limit vs deeply nested package files | Short project path, or enable long paths (documented in SETUP.md) | Test the setup guide on a clean machine, not just your own |

**A working rule that came out of this:** fixes made *because* the machine is
low on memory are proposed and agreed first, not slipped in, because free
memory depends on what else is open, and the code shouldn't be reshaped around
one bad moment.

## 9.3 Architecture: layers with one job each

```
api/        HTTP only: validate, call, shape the response. No logic.
audio/      All the real work. Knows nothing about HTTP.
ai/         The LLM, behind one provider file.
storage/    The only code that touches file paths (an interface + a disk implementation).
jobs/       Tickets for long-running work.
config.py   Every tunable value.
cli.py      Turns typed commands into calls, nothing more.
```

**Why it pays off:**
- The **CLI and the web app share every line underneath**, so anything can be
  tested from the terminal.
- **Adding an analyser is mechanical:** a module with `detect(track_id)` and
  `load(track_id)` that writes a JSON file next to the stems, plus one route.
  Beats, chords and lyrics all follow it.
- **Swappable pieces:** storage (disk → S3), jobs (memory → Redis), the LLM
  (Gemini → another provider): each is one class or file.

On the frontend, the same idea: **the audio engine is a plain class with no
React**, pure logic lives in `lib/` (chords, sheet, bars, tidy), and components
only render and wire.

## 9.4 Caching, idempotence and self-upgrading data

- **Content-addressed IDs:** a track's ID is a SHA-256 hash of the upload, so
  the same file is never processed twice (Section 1).
- **A completeness marker:** `meta.json` is written last, so a crash can never
  leave a half-finished track that looks complete.
- **Every analysis is cached as a file** (`beats.json`, `chords.json`,
  `lyrics.json`) and computed on first request if missing.
- **Self-upgrading files:** when an analysis improved, its `load()` recognises
  the old format and re-runs just that step, once:
  - beats without `downbeats` are re-analysed;
  - chords without `levels` are re-decoded;
  - lyrics without `aligned` are re-timed (without re-running Whisper).

  No migration scripts, and old songs keep working.

## 9.5 Decisions made by measuring, not guessing

A habit through the whole project: when a choice could be tested, it was.

| Question | Measurement |
| --- | --- |
| Do the stems really add back up to the song? | Residual check: leftover ~18 dB below the music |
| Will mixing ever clip? | Peaks across realistic settings: 0.72–0.92, never 1.0 |
| Are chunk joins audible? | Residual at each join equals mid-chunk |
| Which word timings are better? | Distance to independently detected vocal onsets: 0.13 s (Whisper) vs 0.03 s (aligner) |
| Can the aligner verify AI suggestions? | Fit scores of true vs fake text; then the scramble control after a fake slipped through |
| How strong should chord smoothing be? | Chord-change counts per penalty on two songs |
| Does the wrong-song check separate songs? | Word-pair overlap: 69–100% same song vs 2–3% different |
| Does the AI correction help? | WER and missing-line rate against hand-typed truth |
| Does SETUP.md work? | Followed it command by command in a clean copy, which found the long-path problem |

## 9.6 How things were tested safely

- **Never on the user's data:** experiments ran on copies in a scratch folder,
  or with file writes captured by the test instead of reaching `data/`.
- **Stand-ins for external services:** the Gemini flow was tested end to end
  with a fake model returning known decisions, including deliberately wrong
  ones, so the right outcome was known.
- **Known answers:** synthetic chords (C, Am, F, G7) for the chord model; a real
  line deliberately hidden to test missing-line recovery.
- **Type checks and production builds** after every frontend change.

## 9.7 Privacy and cost

- **Local-first:** separation and analysis run on your own machine. Nothing is
  uploaded anywhere by default.
- **Opt-in AI:** only when the button is pressed, sending the vocal MP3 and
  lyrics text; the key lives in an environment variable.
- **Cost:** local models are free to run; the AI call is a fraction of a cent to
  a few cents per song (and Gemini has a free tier).

## 9.8 How it would scale

| Today | To serve many users |
| --- | --- |
| Jobs in an in-memory dict | A queue (Redis + RQ/Celery) |
| GPU on the same machine | GPU workers (serverless, e.g. Modal/RunPod), one job per GPU |
| Files on local disk | Object storage (S3/R2) behind the existing storage interface |
| No accounts | Authentication; per-user libraries |
| No limits | Upload size limits, rate limits |
| Same file → same ID | Audio fingerprinting to share results for the same song across users |

The layering means most of this is swapping implementations, not rewriting
logic.

## 9.9 What's next on the product side

- **Edit lyrics** (click a word, fix it, it keeps its timing), which also
  collects corrections that could later fine-tune the chord model on this kind
  of music.
- **Section detection** (intro, verse, chorus) from a structure model, fixing
  the verse-ending chord issue properly.
- **Key detection**, for correct spellings (Bb vs A#) and smarter smoothing.
- **Bass-root check:** use the separated bass to settle Em-vs-G style
  confusions.
- **ChordFormer vs BTC** side by side; **lyrics lookup** for released songs
  (opt-in).

## Likely interview questions

1. **"What was the hardest constraint?"** Memory: five models on a 4 GB GPU with
   about 6 GB of RAM. Solved by loading per call and releasing, 16-bit weights,
   meta-device loading, and chunked processing.
2. **"Tell me about a bug you solved."** The 687 MiB allocation failure:
   diagnosed as Demucs assembling a whole song in RAM, fixed with crossfaded
   chunking, and verified with the residual check that the joins are inaudible.
3. **"How is the code structured, and why?"** Layered: thin routes, an audio
   layer that doesn't know about HTTP, a storage interface, one config. The CLI
   and API share all the logic, and storage, jobs and the LLM provider are each
   swappable.
4. **"How do you handle old data when the analysis improves?"** Each `load()`
   detects the old format and re-runs just that step once; no migrations.
5. **"How would you scale this?"** A job queue, GPU workers, object storage
   behind the existing interface, auth and limits, and audio fingerprinting to
   share results.
6. **"How do you decide between options?"** Measure where possible: residual
   checks, onset distance, fit scores, chord counts, WER.
