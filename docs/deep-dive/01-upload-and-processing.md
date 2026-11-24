# Section 1: Upload and the processing pipeline

[← Section 0, The big picture](00-big-picture.md) · [Index](README.md) · Next: [Section 2, Audio and separation →](02-audio-and-separation.md)

Everything from dropping a file on the page to "song ready".

## What the user sees

Drop an MP3 (or a video) on the page. A status line shows *"decoding…
separating 3/12… encoding… finding beats… finding chords… writing down the
lyrics… ready"*. Then the song appears in the picker.

## The whole journey

```
BROWSER                                   SERVER (Python)
───────                                   ───────────────
① Dropzone.tsx: you drop a file
② App.tsx upload() → api.upload()
   POST /tracks  (the file)  ───────────► ③ routes/tracks.py upload()
                                             - save to data/uploads/<name>
                                             - jobs.create() → ticket "3ad81ead3965"
   ◄────────────── { job_id } ─────────────  - schedule _process() in background
④ api.watchJob(job_id)                       - return IMMEDIATELY
   GET /jobs/<id>/events  ───────────────► ⑤ routes/jobs.py: keeps the connection open,
   ◄── data: {"step":"decoding"} ─────────     pushes each status change (SSE)
   ◄── data: {"step":"separating 3/12"} ─
                                          ⑥ meanwhile, in a worker thread:
                                             separation.separate(path):
                                               hash → decode → separate (chunks)
                                               → Opus copies → beats → chords
                                               → lyrics → meta.json (= "ready")
   ◄── data: {"status":"done", track_id} ─
⑦ refresh() → GET /tracks → song appears, gets selected
```

## ① Picking the file: [Dropzone.tsx](../../frontend/src/components/Dropzone.tsx)

- A `<div>` handles the drag-and-drop events (`onDragEnter`, `onDragOver`,
  `onDrop`). `event.preventDefault()` stops the browser from simply *opening*
  the dropped file.
- There is also a hidden `<input type="file" accept="audio/*,video/*">`,
  clicked through the "choose a file" link.
- Either way it calls `onFile(file)`, passed in from `App.tsx`. The component
  only *collects* a file; it knows nothing about servers.
- **Compact mode:** once there are songs, it shrinks to one line, because the
  player matters more than the upload box.

## ② Sending it: [App.tsx `upload`](../../frontend/src/App.tsx) → [client.ts `upload`](../../frontend/src/api/client.ts)

```ts
const body = new FormData()
body.append('file', file)
await fetch('/tracks', { method: 'POST', body })   // → returns { job_id }
```

- **FormData / multipart upload** is the standard way to send a file over HTTP:
  the request body is split into parts, one of which is the file's bytes.
- **Why a plain path like `/tracks` works:** in development the React app runs
  on port 5173 and Python on port 8000.
  [vite.config.ts](../../frontend/vite.config.ts) *proxies* `/tracks`, `/stems`
  and `/jobs` to port 8000, so the browser only ever talks to one address
  (**same origin**) and there are no CORS problems. In production, Python serves
  the built React files itself, so the same paths still work.
- **CORS** (Cross-Origin Resource Sharing) is a browser security rule: a page
  may not call a *different* origin (domain or port) unless that server
  explicitly allows it.

## ③ Receiving it: [routes/tracks.py `upload`](../../backend/woodshed/api/routes/tracks.py)

```python
name = Path(file.filename or "upload.mp3").name       # security: bare name only
destination = settings.uploads_dir / name
shutil.copyfileobj(file.file, out)                     # stream to disk
job = jobs.create(name)
background.add_task(_process, job.id, destination)     # runs AFTER the response
return {"job_id": job.id}
```

- **`UploadFile`** is FastAPI's file object. It spools large uploads to a temp
  file instead of holding them in RAM, and `copyfileobj` copies in pieces.
- **Security, path traversal:** `Path(...).name` keeps only the filename. A
  malicious name like `../../windows/x.dll` becomes just `x.dll`, so an upload
  can never choose where on disk it lands.
- **Why return immediately (the "ticket" pattern):** separation takes minutes.
  If the request waited, (a) browsers and proxies would **time out** and report
  failure for work that actually succeeded, and (b) it would tie up the server.
  So it returns a **job ID** at once, and the work happens afterwards.
- **`BackgroundTasks`:** FastAPI runs `_process` *after* sending the response.
  Because `_process` is an ordinary (non-`async`) function, it runs in a
  **worker thread**, so the server keeps answering other requests.

## ④–⑤ Following progress: [jobs/registry.py](../../backend/woodshed/jobs/registry.py) + [routes/jobs.py](../../backend/woodshed/api/routes/jobs.py)

- A **`Job`** is a small record: `id`, `source`, `status`
  (`queued → running → done / error`), `step` (the current message),
  `track_id`, `error`.
- **`JobRegistry`** keeps jobs in a plain Python dict, **in memory**, on
  purpose. If the server restarts you lose only the *tickets*; finished songs are
  already on disk. A database or Redis would only be needed with several
  servers. A deliberate "simplest thing that works" decision.
- `_process` updates the job: `jobs.start`, then `jobs.step(...)` for each
  stage, then `jobs.finish(track_id)` or `jobs.fail(error)`.
- **Server-Sent Events (SSE):** `GET /jobs/<id>/events` returns a response that
  **never finishes**. Every 0.4 s, `watch()` checks the job and, *only if it
  changed*, writes a line:
  ```
  data: {"status": "running", "step": "separating 3/12", ...}
  ```
  The browser reads it with `EventSource` (`watchJob` in
  [client.ts](../../frontend/src/api/client.ts)), which closes the stream once
  `finished` is true.

**Choices you may be asked about:**

| Option | Why not |
| --- | --- |
| **Polling** (ask "done yet?" every second) | Works, but wasteful and laggy; SSE pushes the moment something changes |
| **WebSockets** | Two-way: more machinery than needed, since nothing travels *back* from the browser |
| **SSE** ✅ | One-way, plain HTTP, and the browser **reconnects automatically** |

**Why named steps, not a percentage:** the model doesn't report usable
progress, and a fake percentage that jumps or stalls is worse than an honest
"separating 3/12".

## ⑥ The actual work: [audio/separation.py `separate`](../../backend/woodshed/audio/separation.py)

### a) Identify the song by its content: [tracks.py `track_id`](../../backend/woodshed/tracks.py)

The track's ID is a **hash** of the uploaded file. [Hashing in depth](#hashing-in-depth)
below explains it fully; the short version:

- **Same file, same ID, always.** Different files practically never share an
  ID.
- **Free caching:** if `is_ready(tid)` is already true, `separate` returns at
  once ("cached"). Separation, the slowest step, is never paid for twice.

### b) Decode: [encoding.py `decode`](../../backend/woodshed/audio/encoding.py)

```
ffmpeg -i <upload> -vn -ac 2 -ar 44100 source.wav
```

- `-vn` drops any video (phone recordings work), `-ac 2` makes it stereo, and
  `-ar 44100` sets the CD sample rate.
- **Why always decode to WAV:** every input then looks identical to the model,
  and a WAV can be **read a piece at a time** from disk, which is what makes
  chunking possible.

### c) Separate, in chunks: [`_separate_in_chunks`](../../backend/woodshed/audio/separation.py)

- The model is **Demucs `htdemucs_6s`** ([Section 2](02-audio-and-separation.md)
  goes deep on it). It outputs 6 stems: Vocals, Drums, Bass, Guitar, Piano,
  Other.
- **Why chunks:** a real bug. A 5.7-minute song failed with *"Unable to
  allocate 687 MiB"*, because Demucs builds all 6 stems for the whole song in
  RAM at once. Now the song goes through in **30-second chunks with 4-second
  overlaps**:
  ```
  |----- chunk 1 -----|
                  |XXXX----- chunk 2 -----|      XXXX = overlap, crossfaded
  ```
  Each chunk is separated and **appended** to the 6 stem files, so memory no
  longer grows with song length.
- **Why overlap and crossfade:** the model sees less context at a chunk's edge,
  so its output there differs slightly, and hard cuts would click. In the
  overlap, the old chunk fades out (`1 − fade_in`) while the new one fades in
  (`fade_in`), so the seam is inaudible. **Verified:** adding all 6 stems back
  together rebuilds the original equally well at the seams as mid-chunk.
- Other settings, in [config.py](../../backend/woodshed/config.py):
  `shifts: 1` (the default of 2 runs the model twice and averages, which needs
  twice the memory and crashed this laptop), plus `overlap: 0.25` and
  `segments_enabled`, which are Demucs's own internal chunking.

### d) Compressed copies: `write_opus_copies`

- Each stem also gets an **Opus** copy, about 15× smaller. The browser
  downloads Opus.
- **The WAVs are kept**, because they're lossless and all analysis reads them.
  The rule: *compress what you send, keep what you have.*

### e) Analysis

`beats.detect`, then `chords.detect`, then `lyrics.detect` (Sections 4–6).
Chords and lyrics are wrapped in `try/except`: if they fail, the song is
**still usable** ("chords skipped"). A bonus feature never loses you the stems.

### f) The "ready" marker: `meta.json`, written last on purpose

[`tracks.write`](../../backend/woodshed/tracks.py) creates `meta.json`, and
`is_ready()` just checks whether it exists. Since it is written **only after
everything else succeeded**, a crash halfway can never leave a half-finished
song that looks complete. That is a simple **atomic commit marker**, a common
reliability pattern.

## Where everything lives on disk: [storage/](../../backend/woodshed/storage/)

- [base.py](../../backend/woodshed/storage/base.py) defines a **Protocol**, the
  interface everyone relies on: `path`, `exists`, `ensure`, `read_json`,
  `write_json`, `track_ids`.
- [local.py](../../backend/woodshed/storage/local.py) implements it on disk, as
  `data/cache/<track-id>/<file>`.
- **Why the interface:** switching to cloud storage later means writing one new
  class, and nothing else changes.

```
data/cache/28d2c7721b9c3fc9/
├── Vocals.wav  Drums.wav  Bass.wav  Guitar.wav  Piano.wav  Other.wav   ← lossless stems
├── Vocals.opus … Other.opus                                           ← what the browser downloads
├── beats.json   chords.json   lyrics.json                             ← analysis results
└── meta.json                                                          ← "this track is complete"
```

## ⑦ After it's done

- The browser calls `refresh(track_id)` → `GET /tracks` →
  [`tracks.all_ready()`](../../backend/woodshed/tracks.py), which lists every
  folder that has a `meta.json`. The new song appears and is selected.
- **Validation on every later request:**
  [`deps.py require_track`](../../backend/woodshed/api/deps.py) checks that the
  ID is exactly 16 hex characters **and** is a finished track, *before touching
  disk*. Anything else gets a 404, which blocks path tricks through the URL.

---

## Hashing in depth

**In short:** the hash is a fingerprint of the uploaded file's raw bytes,
used as the song's ID so that re-uploading the same file is an instant cache
hit and two different files can never overwrite each other.

### What a hash is

A **hash function** takes any amount of data and produces a fixed-length
"fingerprint". We use **SHA-256**, a standard one used in passwords, Git,
downloads and Bitcoin. Measured:

```
1. Same input -> same hash, every time:
   'hello'      -> 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
   'hello'      -> 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824

2. Change ONE letter -> completely different hash:
   'hellp'      -> fdd7585e08c4e2afd71dcabdb4636c89d557a3f42db9e2040c8bbd1708aa4ce7

3. Any size in -> same size out (64 hex characters):
   ''            -> e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
   10 MB of 'a'  -> 01f4a87c04b40af59aadc0e812293509709c9a8763a60b7f9e19303322f8b03c
```

| Property | What the demo shows |
| --- | --- |
| **Same input, same output, always** | `hello` gave `2cf24dba…` both times |
| **A tiny change gives a totally different output** | one letter changed (`hellp`) gave `fdd7585e…`, nothing alike. This is the *avalanche effect* |
| **Any size in, same size out** | an empty input and 10 MB both give 64 characters |
| **One-way** | you cannot rebuild the file from its hash; it is a fingerprint, not a compressed copy |

### What exactly is hashed

The **raw bytes of the uploaded file itself** (the `.mp3` or video), exactly
as it arrived, **before any decoding**. Not the song title, not the processed
audio. Every file on disk is a long list of bytes (numbers 0–255); the "Alvida"
upload is 8.2 million of them:

```
Alvida ... .mp3  (8.2 MB of bytes)  ──SHA-256──►  9a4ee4f115cd64c650263fe3f84bdabbf65ead35c8f1c1b89b9f246789caf502
                                                  └──────────────┘
                                          first 16 characters = track id "9a4ee4f115cd64c6"
```

That track ID is the **folder name**: `data/cache/9a4ee4f115cd64c6/` holds
Alvida's stems, beats, chords and lyrics.

### Why hash at all

The app needs a **name for each song** to use as a folder name and in URLs
(`/stems/9a4ee4f115cd64c6/Vocals`). Three options:

| Option | Problem |
| --- | --- |
| The filename (`song.mp3`) | Two *different* songs can share a name and would overwrite each other. Renaming a file would make it look like a new song |
| A counter (song 1, song 2…) | Uploading the *same* file twice would create two copies and separate it twice |
| **Hash of the content** ✅ | Same file always gets the same ID; different files get different IDs. The name comes from *what the file is*, not what it is called |

This gives **free caching**, in
[separation.py](../../backend/woodshed/audio/separation.py):

```python
tid = tracks.track_id(source)                  # fingerprint the upload
if tracks.is_ready(tid) and not force:         # do we already have this exact file?
    return tid                                 # yes → skip ALL the slow work
```

Upload the same file again, even renamed, and it is ready instantly instead of
spending minutes on separation.

### How the code does it, line by line

[tracks.py `track_id`](../../backend/woodshed/tracks.py):

```python
digest = hashlib.sha256()                    # 1. start an empty SHA-256 calculator
with open(path, "rb") as handle:             # 2. open in Binary mode ("rb"): raw bytes, not text
    for chunk in iter(lambda: handle.read(CHUNK), b""):   # 3. read 1 MB at a time...
        digest.update(chunk)                 #    ...and feed each piece into the calculator
return digest.hexdigest()[:16]               # 4. the result as text, first 16 characters
```

- **Step 3 in plain words:** `iter(function, b"")` means "keep calling
  `handle.read(1 MB)` until it returns empty bytes", i.e. until the end of the
  file. "Alvida" was read as **8 pieces**, in **29 ms**.
- **Why in pieces:** SHA-256 can be fed bit by bit, and the final answer is
  **identical** to hashing the whole file at once. Reading 1 MB at a time means
  even a 2 GB video never has to fit in RAM.
- **`hexdigest()`:** the raw fingerprint is 32 bytes; "hex" writes it as 64
  readable characters (0–9, a–f), safe for folder names and URLs.
- **`[:16]`:** we keep the first 16 characters (64 bits) for shorter folder
  names. That is still about 18 quintillion possible IDs. You would need around
  **4 billion** different songs before two shared an ID by chance (the
  "birthday bound": √2⁶⁴ = 2³²), so it is safe for this app.

### One limit worth knowing

The hash identifies the **file**, not the **song**. The same song as a
different file (an MP3 at another quality, a YouTube rip versus a CD copy, a
trimmed version) has different bytes, so it gets a different hash and is
processed again.

Recognising *the song itself* regardless of file needs **audio
fingerprinting**, which is how Shazam and AcoustID work: they fingerprint the
*sound* (patterns of frequencies over time), not the bytes. We don't need that
for caching, but it is the right tool for something like "look up this song's
official lyrics".

---

## Honest limitations (interviewers love these)

- **One process, one machine:** jobs live in memory, so they are lost on
  restart (by design). Scaling out would need a queue (Redis + RQ or Celery) and
  shared storage (S3).
- **GPU jobs aren't queued:** two heavy GPU tasks at once (e.g. a separation
  while lyrics are being analysed) can exhaust the 4 GB card. Today the rule is
  "let one finish first".
- **Uploads keep their original filename** in `data/uploads/`, so two
  *different* files with the same name overwrite each other there. The cache is
  safe, because it is keyed by hash.
- **No authentication and no upload size limit.** Fine for a local app;
  required before going public.

## Likely interview questions

1. **"Why not process the upload inside the request?"** Timeouts, and it blocks
   the server. So I return a job ID and stream progress over SSE.
2. **"Why SSE over WebSockets?"** One-way updates only. SSE is plain HTTP and
   reconnects automatically; WebSockets would be unused complexity.
3. **"How do you avoid reprocessing the same song?"** Content hashing (SHA-256
   of the bytes) as the track ID, plus a `meta.json` completeness marker.
4. **"How did you handle long songs on a low-memory machine?"** Chunked
   separation with crossfaded overlaps, verified by checking that the stems
   still sum back to the original.
5. **"What would you change to deploy this?"** A job queue, cloud storage
   behind the existing storage interface, authentication, upload limits, and GPU
   serverless workers.
6. **"What is hashed, and why?"**
   > "Each upload is identified by a SHA-256 hash of its bytes, computed in
   > 1 MB chunks. It's a content-addressed ID, so re-uploading the same file is
   > an instant cache hit, and two different files can never overwrite each
   > other's results."
