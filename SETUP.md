# Setting up Woodshed

Step-by-step instructions to get Woodshed running on a new machine, from a
fresh clone to separating your first song.

**Read the whole of step 3 before starting it.** The order of the Python
installs matters: doing them in a different order silently leaves you with a
slow, CPU-only setup (step 3 explains why).

Commands are given for **Windows (PowerShell)**, where the project is
developed and tested, with **Linux/macOS** equivalents where they differ.

---

## 1. What you need

### Hardware

| | Minimum | Notes |
| --- | --- | --- |
| **GPU** | NVIDIA, 4 GB of video memory | Strongly recommended. Tested on an RTX 3050 Laptop (4 GB). Without an NVIDIA GPU it still runs, on the CPU, but separation and lyrics take many times longer (see [No NVIDIA GPU?](#no-nvidia-gpu)) |
| **RAM** | 8 GB | Tested with 8 GB. Close the browser and other heavy apps while a song is being processed |
| **Disk** | ~15 GB free | ~5 GB for the Python environment (the GPU build of PyTorch is large), ~3 GB of AI models (downloaded on first use), plus ~400 MB per processed song |

### Software

| Tool | Version | Check with | Install |
| --- | --- | --- | --- |
| **Git** | any recent | `git --version` | [git-scm.com](https://git-scm.com) |
| **Python** | 3.11 or 3.12 (tested 3.12.3) | `python --version` | [python.org](https://www.python.org/downloads/); on Windows, tick "Add python.exe to PATH" |
| **Node.js** | 22 LTS, at least 22.12 (or 20.19+); tested 22.19 | `node --version` | [nodejs.org](https://nodejs.org) |
| **ffmpeg** | any recent (tested 9.0) | `ffmpeg -version` | Windows: `winget install ffmpeg` · macOS: `brew install ffmpeg` · Linux: `sudo apt install ffmpeg` |
| **NVIDIA driver** | supporting CUDA 12.1 or newer | `nvidia-smi` (top right shows "CUDA Version: 12.x") | [nvidia.com/drivers](https://www.nvidia.com/drivers) |

After installing ffmpeg or Python, **open a new terminal** so the updated PATH
takes effect.

---

## 2. Get the code

```powershell
git clone <repository-url> MusicTeacher
cd MusicTeacher
```

All the commands below are run from this `MusicTeacher` folder unless a step
says otherwise.

> **Windows: keep the folder path short.** Some of the Python packages
> (PyTorch, numpy, ONNX Runtime) contain very deeply nested files, and Windows
> by default refuses paths longer than 260 characters. Cloned into a long
> folder, step 3.2 fails with
> `OSError: [WinError 206] The filename or extension is too long`. Either:
>
> - clone into a short path, such as `C:\dev\MusicTeacher` (anything under
>   about 60 characters is safe), **or**
> - enable long paths once, in PowerShell **run as Administrator**, then
>   restart the computer:
>   ```powershell
>   New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
>   ```

---

## 3. Backend (Python)

### 3.1 Create a virtual environment

A virtual environment keeps this project's Python packages separate from
everything else on your machine.

```powershell
python -m venv .venv
```

Activate it (do this in **every** new terminal you use for the backend):

```powershell
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```
```bash
# Linux / macOS
source .venv/bin/activate
```

> **Windows: "running scripts is disabled on this system"?** Run this once,
> then activate again:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
>
> Or skip activation entirely and call Python by its path in every command:
> `.venv\Scripts\python.exe -m pip ...`, `.venv\Scripts\python.exe -m woodshed ...`

Your prompt should now start with `(.venv)`. Upgrade pip:

```powershell
python -m pip install --upgrade pip
```

### 3.2 Install the project and its dependencies

```powershell
python -m pip install -e backend
```

This installs the `woodshed` package in *editable* mode (your code changes
take effect without reinstalling) and everything listed in
`backend/pyproject.toml`. It also pulls in PyTorch, but **the CPU-only
version**. The next steps fix that.

### 3.3 Make sure only the plain ONNX Runtime is installed

```powershell
python -m pip uninstall -y onnxruntime-gpu onnxruntime
python -m pip install onnxruntime
```

The GPU and plain builds of ONNX Runtime install into the same folder and
break each other. The separation model runs on PyTorch, not ONNX, so the plain
build is all that is needed.

### 3.4 Install the GPU (CUDA) build of PyTorch, **after** everything else

```powershell
python -m pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121 --force-reinstall --no-deps
```

**Why last, and why `--no-deps`:** several packages (`audio-separator`,
`beat-this`, `openai-whisper`) declare that they need PyTorch. When pip
installs them, it fetches PyTorch from the default index, which is the
**CPU-only** build. Nothing errors: the GPU is simply never used, and
separation becomes 10–20× slower. Installing the CUDA build last, with
`--no-deps` so pip does not touch anything else, guarantees it is the one that
stays.

`torch` and `torchaudio` must come from the **same index** with **matching
versions** (both 2.5.1, both `+cu121`), or importing them fails.

### 3.5 Install the beat, lyrics and alignment models' packages

```powershell
python -m pip install beat-this rotary-embedding-torch openai-whisper --no-deps
```

These three also ask for PyTorch, hence `--no-deps` again. Their other
requirements (`einops`, `soxr`, `tqdm`, `tiktoken`, `more-itertools`) were
already installed in step 3.2.

### 3.6 Check the backend

```powershell
python -c "import torch, torchaudio, whisper, beat_this, woodshed; print('GPU available:', torch.cuda.is_available(), '|', torch.__version__, '|', torchaudio.__version__)"
```

Expected output:

```
GPU available: True | 2.5.1+cu121 | 2.5.1+cu121
```

If it says `False`, see [Troubleshooting](#troubleshooting).

> **Rule for the future:** after *any* `pip install` in this project, run this
> check again. If a new package pulled the CPU build of PyTorch back in, repeat
> step 3.4.

---

## 4. Frontend (React)

```powershell
cd frontend
npm ci
cd ..
```

`npm ci` installs exactly the versions recorded in `package-lock.json`, so
everyone gets the same frontend. Use `npm install` only when you intend to add
or update a package.

---

## 5. Optional: AI lyric correction (Gemini)

The "Fix lyrics with AI" feature uses Google's Gemini. Everything else works
without it.

1. Create an API key at [Google AI Studio](https://aistudio.google.com/apikey).
2. Save it as an environment variable:
   ```powershell
   # Windows
   setx GEMINI_API_KEY "your-key-here"
   ```
   ```bash
   # Linux / macOS: add this line to ~/.bashrc or ~/.zshrc
   export GEMINI_API_KEY="your-key-here"
   ```
3. **Open a new terminal.** Programs only read environment variables when they
   start. On Windows, if you use VS Code's built-in terminal, **close and reopen
   VS Code completely**: its terminals inherit VS Code's own environment from
   when it started.
4. Check (prints whether the key is visible, never the key itself):
   ```powershell
   python -c "import os; print('key found' if os.environ.get('GEMINI_API_KEY') else 'key NOT found')"
   ```

Never put the key in the code or commit it.

---

## 6. Run it

### Development (two terminals)

**Terminal 1, the backend (API on port 8000):**

```powershell
.venv\Scripts\Activate.ps1
woodshed serve
```

**Terminal 2, the frontend (app on port 5173):**

```powershell
cd frontend
npm run dev
```

Open **http://localhost:5173**. Use `localhost`, not `127.0.0.1`: the Vite
dev server listens on `localhost` only.

The frontend dev server forwards `/tracks`, `/stems` and `/jobs` to the
backend (see `frontend/vite.config.ts`), so both terminals must be running.
Frontend changes appear instantly; after changing Python code, stop the backend
(Ctrl+C) and start it again.

### Single server (production-style)

```powershell
cd frontend
npm run build
cd ..
woodshed serve
```

Open **http://127.0.0.1:8000**. The backend serves the built app from
`frontend/dist` itself.

---

## 7. First run: what to expect

**Upload a song** by dropping an audio or video file on the page. The first
time each model is needed, it downloads automatically (internet required):

| Model | Used for | Size | Saved to |
| --- | --- | --- | --- |
| Demucs `htdemucs_6s` | separating instruments | ~0.3 GB | `/tmp/audio-separator-models/` (on Windows, `C:\tmp\audio-separator-models\`) |
| Beat This! `final0` | beats and bars | ~80 MB | PyTorch's cache in your user folder |
| BTC | chords | 12 MB | `data/models/` |
| Whisper `turbo` | lyrics | 1.5 GB | `data/models/whisper/` |
| MMS aligner | word timing | 1.26 GB | `data/models/mms/` |

So the **first song takes a while** (downloads, then processing). After that,
a song typically takes 2–4 minutes on a 4 GB GPU, and opening a song that was
already processed is instant (results are cached in `data/cache/`).

**Command-line alternative** (with the virtual environment active):

```powershell
woodshed split "path\to\song.mp3"       # separate, then beats, chords, lyrics
woodshed list                           # everything processed so far
woodshed chords "path\to\song.mp3"      # print the chords, bar by bar
woodshed lyrics "path\to\song.mp3"      # transcribe the vocals again
woodshed polish "path\to\song.mp3"      # AI lyric correction (needs step 5)
woodshed --help                         # every command
```

---

## No NVIDIA GPU?

Everything falls back to the CPU automatically. It works, but separation and
lyrics are many times slower and use much more RAM. Replace step 3.4 with the
CPU build:

```powershell
python -m pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu --force-reinstall --no-deps
```

The check in step 3.6 will then print `GPU available: False`, which is
expected. Apple Silicon Macs also run on the CPU: the code does not use Apple's
GPU (MPS).

---

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `OSError: [WinError 206] The filename or extension is too long` during `pip install` | The project folder's path is too long for Windows' 260-character limit | Move the project to a short path (e.g. `C:\dev\MusicTeacher`), delete `.venv`, and start step 3 again; or enable long paths (see step 2) |
| Step 3.6 prints `GPU available: False` (on an NVIDIA machine), and `torch.__version__` has no `+cu121` | A later install replaced the CUDA build with the CPU one | Repeat step 3.4 |
| `GPU available: False` but the version **is** `+cu121`, and `nvidia-smi` works | The GPU is stuck, typically after the laptop slept many times | **Restart** Windows (a full Restart, not Shut down) |
| `RuntimeError: CUDA error: unknown error` while the server is running | Same as above, or two GPU-heavy jobs at once | Stop and restart `woodshed serve`. If it repeats, restart Windows. Let one song finish before starting another heavy task |
| `Unable to allocate … MiB`, or the server dies with no error | Out of RAM | Close the browser and other heavy apps, then retry. Lower `separation_chunk_seconds` in `backend/woodshed/config.py` if it keeps happening |
| `[vite] http proxy error … ECONNRESET` | The backend stopped (usually the cause above) | Restart `woodshed serve` |
| "Could not reach the server" in the app | The backend is not running | Start Terminal 1 (step 6) |
| `ffmpeg` not found | ffmpeg not installed, or not on PATH yet | Install it (step 1), then open a new terminal |
| `woodshed` is not recognised | The virtual environment is not active | Activate it (step 3.1), or use `python -m woodshed ...` |
| "no Gemini API key" | Key not set, or the server was started before it was set | Step 5, including restarting the terminal or VS Code |
| `npm ci` or `npm run dev` fails | Node.js too old | Install Node.js 22 LTS |

---

## Tested versions

The setup above was last verified with:

| Package | Version |
| --- | --- |
| Python | 3.12.3 |
| torch / torchaudio | 2.5.1+cu121 |
| audio-separator | 0.47.0 |
| onnxruntime | 1.30.0 |
| beat-this | 1.1.0 |
| openai-whisper | 20250625 |
| rotary-embedding-torch | 0.6.5 |
| librosa | 1.0.0 |
| numpy | 2.5.3 |
| fastapi | 0.141.1 |
| google-genai | 2.29.0 |
| Node.js / npm | 22.19.0 / 10.9.3 |
| ffmpeg | 9.0.1 |
| NVIDIA driver | 555.99 |

If something breaks with newer versions, install these exact ones, e.g.
`python -m pip install audio-separator==0.47.0`.

---

## Before you commit

- **Never commit `data/`** (songs, stems, models: gigabytes) or audio/video
  files. `.gitignore` already excludes them.
- **Never commit API keys.**
- Check the frontend still builds: `cd frontend` then `npm run build`.

## Where to read next

- [README.md](README.md): what the app does.
- [docs/README.md](docs/README.md): how everything works and why, phase by phase.
- [docs/deep-dive/](docs/deep-dive/README.md): the system explained section by section.
- [docs/CONTEXT.md](docs/CONTEXT.md): current state and settled decisions.
