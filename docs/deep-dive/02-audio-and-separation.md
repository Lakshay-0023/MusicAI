# Section 2: Audio basics and source separation

[← Section 1, Upload and processing](01-upload-and-processing.md) · [Index](README.md) · Next: [Section 3, The browser player →](03-browser-player.md)

Two halves:

- **2A, what audio actually is:** the foundation. No AI, just numbers.
- **2B, how the AI splits a song into instruments:** Demucs.

All numbers below were measured on a 10-second slice (1:00–1:10) of "Alvida"
(track `9a4ee4f115cd64c6`).

---

## 2A: What audio actually is

### Sound is a speaker cone moving

A speaker makes sound by pushing a cone out and pulling it back, very fast.
Your eardrum copies that movement, and your brain hears it as sound. So **a
recording is just instructions for where the speaker cone should be, moment by
moment.**

### A computer stores that as numbers ("samples")

The computer writes down the cone's position **44,100 times per second**:

- `0.0` = at rest (silence)
- `+1.0` = pushed fully out
- `−1.0` = pulled fully in

Each number is a **sample**. From "Alvida"'s vocal stem:

```
Vocals.wav: 44100 samples per second, 2 channels, PCM_16, 5.7 min
this 10 s slice has shape (441000, 2) = 441,000 moments x 2 (left, right)
first 6 samples (left): -0.0227, -0.0277, -0.0343, -0.0409, -0.0451, -0.0460
loudest value in the slice: 0.724 (the limit is 1.0)
```

**A WAV file is basically that list of numbers** written to disk, with a small
header saying "44,100 per second, 2 channels, 16-bit".

### Three terms you'll be asked about

| Term | Our value | Meaning |
| --- | --- | --- |
| **Sample rate** | 44,100 Hz | Samples per second. Why 44,100: to capture a frequency you must sample at **more than twice** it (the **Nyquist limit**). Human hearing tops out around 20,000 Hz, so ×2 plus a little headroom gives 44,100, the CD standard |
| **Channels** | 2 | Stereo: one list for the left speaker, one for the right |
| **Bit depth** | 16-bit (`PCM_16`) | How precisely each number is stored: 65,536 possible positions between −1 and +1. CD quality. Python converts them to decimals so maths is easy |

**Size maths** (useful in interviews): 44,100 samples × 2 channels × 2 bytes =
**176 KB per second**, about **10 MB per minute**. That is why the 5.7-minute
vocal stem WAV is **60 MB**.

### Mixing is addition

When two instruments play in a room, their pressure waves **physically add**
before reaching your ear. Digital audio copies that exactly. "Alvida" at
1:05.0, left channel:

```
Vocals  +0.1481
Drums   +0.0321
Bass    +0.1392
Guitar  +0.0176
Piano   +0.0004
Other   +0.0154
SUM     +0.3527   ← where the speaker cone actually goes
```

### Volume is multiplication

A volume slider is just a number every sample is **multiplied** by:

```
"drums 10%, vocals muted":  Drums × 0.1,  Vocals × 0.0,  others × 1.0  →  then add
same instant: +0.3527 becomes +0.1757
```

- **Mute is perfect:** × 0 gives exactly zero, mathematically silent, not
  "very quiet".
- **The whole product is one line**, in
  [mixing.py](../../backend/woodshed/audio/mixing.py):
  ```python
  mixed = sum(stems[name] * gains.get(name, 1.0) for name in stems)
  ```
  The browser player (Section 3) does exactly this, live, 44,100 times a
  second.

### Why "30%" doesn't sound like 30%: decibels

Ears judge loudness by **ratio**, not difference. One person joining a quiet
room is a big change; one person joining a crowd of 100 is unnoticeable. So
hearing is **logarithmic**, and **decibels (dB)** are the unit built to match
it:

| Gain | dB | How it sounds |
| --- | --- | --- |
| 1.0 | 0 dB | unchanged |
| 0.5 | −6 dB | slightly quieter |
| 0.3 | −10 dB | about half as loud |
| 0.1 | −20 dB | about a quarter as loud |
| 0.0 | −∞ | silent |

Rules of thumb: every **−6 dB halves the sample values**; every **−3 dB halves
the power (energy)**; around **−10 dB halves the *perceived* loudness**.

### Clipping, and why sliders stop at 100%

- Since mixing *adds*, a sum could exceed 1.0, and the cone can't go further.
  Those samples get **flattened ("clipped")**, which sounds like harsh
  crackling.
- **Measured, not assumed:** peaks on a test song across realistic settings
  were 0.72–0.92, never 1.0, because records are mastered with headroom and our
  sliders only *reduce*. `np.clip(-1, 1)` stays only as a safety net.
- **Why there's no boost above 100%:**
  1. Boosting a separated stem **also boosts its flaws** (bleed, artifacts).
  2. 100% has a real meaning: "exactly as loud as on the record".
  3. Turning *others down* achieves the same thing with no risk. Moises, the
     leading app, makes the same choice.

### The residual check: proving the stems are trustworthy

Add the 6 stems back together and subtract the original song. Whatever is left
over is the model's error:

```
original loudness            −14.2 dB
leftover (original − sum)    −32.6 dB   → 18 dB quieter than the music itself
```

**Why this matters:** if the stems sum back to roughly the song, then
"everything at 100%" really is the record, and every slider behaves the way a
listener expects. The same check later proved that the chunk joins were
seamless ([Section 1](01-upload-and-processing.md)).

### Soloing one instrument: does it get quieter?

Yes, the overall sound gets quieter, by however much of the song that
instrument was. Measured on the same slice:

| What's playing | Loudness | vs the full song |
| --- | --- | --- |
| Everything (the record) | −14.8 dB | — |
| **Only Vocals** | −19.5 dB | **−4.8 dB**, noticeably quieter but not by much |
| Only Guitar | −21.3 dB | −6.6 dB |
| Only Bass | −21.9 dB | −7.1 dB |
| Only Drums | −23.2 dB | −8.4 dB |
| Only Other | −36.2 dB | −21.4 dB, very quiet |
| Only Piano | −50.4 dB | −35.6 dB, practically silent: this song has almost no piano |
| Everything **except** Vocals | −16.8 dB | −2.0 dB |

**Why vocals alone is only a bit quieter, not "1/6 as loud":** the six stems
don't share the loudness equally. The vocal is the biggest part of this song:
by itself it carries about **one third of the song's total energy** (−4.8 dB is
about 0.33× the power). Piano carries almost none. So "how much quieter" really
means **"how much of the song was that instrument?"**

**The important part: the vocal itself is not quieter.** When you solo the
vocals, the vocal samples are **exactly the same numbers** as when everything
plays (× 1.0): the singer is exactly as loud as on the record. What changes is
that everything else is gone, so the *total* is lower. It often even **sounds
clearer**, because no other instrument is covering it up. That covering-up is
called **masking**: a loud sound hides quieter sounds near the same
frequencies.

**Why the app doesn't "make up" the lost volume:** auto-boosting a soloed stem
would amplify its separation artifacts and lose the meaning of 100% ("as on the
record"). If it's too quiet, turn up the **Master** slider or the speakers. An
optional "match loudness when soloing" switch would be possible as a feature.

---

## 2B: Source separation, splitting a song into instruments

### The problem

A finished song is one mixed signal. The original studio tracks (the "stems")
are not public, so they have to be **reconstructed**. Why that is hard:
instruments **overlap in frequency**. A vocal, a guitar and a piano can all
play the same note at once, so there is no simple filter like "everything below
200 Hz is bass" that cleanly separates them.

### How the model learned it

**Demucs** (by Meta AI research) was trained on songs where **both** the final
mix **and** the true separate stems exist, mainly a research dataset called
**MUSDB18**. Shown thousands of these pairs, it learned the patterns: "when the
mix looks like *this*, the drum part looks like *that*". This is **supervised
learning**. The model does not understand music (no idea of key, rhythm or
chords). It is very good pattern matching, which is why it struggles with
sounds unlike its training data (sitar, tabla).

### The specific model: HTDemucs ("Hybrid Transformer Demucs")

It looks at the audio **two ways at once**, then combines them:

| View | What it is | Good at |
| --- | --- | --- |
| **Waveform** | the raw samples over time | sharp events: drum hits, plucks |
| **Spectrogram** | a picture of which frequencies sound at each moment | sustained notes: held vocals, chords ringing |

- **"Hybrid"** = both views processed in parallel. Older models were good at
  one and weak at the other.
- **"Transformer"** = a layer that lets every moment look at every other moment
  (the same "attention" idea as in ChatGPT, and in the chord model in
  Section 5), for long-range context.
- **Output:** one waveform per instrument, **6 stems: Vocals, Drums, Bass,
  Guitar, Piano, Other**.

### Why we chose `htdemucs_6s`

| Model | Stems | Cost | Why / why not |
| --- | --- | --- | --- |
| Spleeter (2019) | 2/4/5 | fast | Older; audibly worse quality |
| `htdemucs` | 4 | 1× | The solid default, but guitar and piano are buried inside "Other" |
| `htdemucs_ft` | 4 | ~4× | Cleaner, much slower, still no guitar or piano |
| **`htdemucs_6s`** ✅ | **6** | ~1.5× | **Adds Guitar and Piano.** The app is for practising *specific instruments*, so a guitarist needs a guitar fader |
| BS-RoFormer / 53-stem models | many | far more | Best quality today, but need ~16 GB of GPU memory. Impossible on a 4 GB card |

**The honest trade-off:** guitar and piano separation are rougher than vocals,
drums and bass (less training data). Acoustic guitar and piano sometimes get
confused, and "Other" is the leftovers bucket (strings, synths, sitar…).

### Why separation is never perfect

- **Bleed:** traces of a removed instrument remain in another stem (a ghost of
  cymbals after muting the drums).
- **Artifacts:** watery or smeared sound where an instrument was removed.
- **Hardest cases:** **cymbals** (energy spread across almost all frequencies,
  overlapping everything) and **reverb** (the sound smeared through the room,
  so it is part vocal and part everything else).

### The settings we chose, and why ([config.py](../../backend/woodshed/config.py))

| Setting | Value | Why |
| --- | --- | --- |
| `shifts` | **1** (default 2) | 2 runs the model twice at slightly shifted times and averages: slightly cleaner, but double the memory. It **crashed this laptop**, so 1: twice as fast, small quality cost |
| `overlap` | 0.25 | Demucs's *own* internal pieces overlap 25% and blend, so its seams don't click |
| `separation_chunk_seconds` | **30** + 4 s crossfade | *Our* outer chunking ([Section 1](01-upload-and-processing.md)), so long songs fit in RAM |

### GPU vs CPU, and VRAM vs RAM

- Neural networks are mostly giant **matrix multiplications**. A GPU has
  **thousands of small cores** that do them in parallel, about **10–20× faster**
  than a CPU here (seconds instead of minutes).
- **Two separate memory pools, and neither substitutes for the other:**
  - **VRAM (4 GB, on the graphics card)** holds the model and the piece being
    processed right now.
  - **RAM (about 5.9 GB usable)** holds the song and the assembled results.

  That is why a big GPU didn't save us from the RAM crash, and why chunking
  fixed it.

### A setup gotcha worth knowing

The `audio-separator` package depends on PyTorch, and installing it pulls the
**CPU-only** PyTorch from PyPI, silently replacing the GPU version. Nothing
errors; separation just becomes about 15× slower. The fix:

- **Always install CUDA PyTorch last**, with `--force-reinstall --no-deps`.
- Later packages (beat-this, Whisper) get **`--no-deps`** too.
- Check with `torch.cuda.is_available()`.

---

## 2C: Where this lives in the code

| File | What it does |
| --- | --- |
| [audio/separation.py](../../backend/woodshed/audio/separation.py) | `Separator(...)` from `audio-separator`, `load_model("htdemucs_6s.yaml")`, `separator.separate(chunk)` per chunk; crossfades and writes `Vocals.wav` … `Other.wav` |
| [audio/encoding.py](../../backend/woodshed/audio/encoding.py) | ffmpeg: `decode` (anything → 44.1 kHz stereo WAV), `write_opus_copies` (each WAV → Opus at 96 kbps) |
| [audio/mixing.py](../../backend/woodshed/audio/mixing.py) | The "multiply and add" mix, used by `woodshed mix` in the terminal to render a practice track |
| [api/routes/stems.py](../../backend/woodshed/api/routes/stems.py) | `GET /stems/<id>/<name>` sends the **Opus** copy if it exists (`audio/ogg`), otherwise the WAV |
| [config.py](../../backend/woodshed/config.py) | `STEM_NAMES`, `separation_model`, `demucs_params`, chunk sizes, `opus_bitrate` |

### WAV vs Opus: send small, keep lossless

```
Vocals  WAV 60.0 MB  →  Opus 4.1 MB  (15× smaller)
Drums   WAV 60.0 MB  →  Opus 3.8 MB  (16× smaller)
```

- **Opus** is a modern compressed format that sounds transparent at 96 kbps.
  It is what the browser downloads.
- **The WAVs are kept**, because compression throws information away
  permanently, and all analysis (beats, chords, lyrics) reads the lossless
  WAVs.
- **What compression doesn't fix:** the browser *decodes* Opus back into raw
  samples to play it, so 6 stems still take about 500 MB of browser memory
  while playing. Compression saves **download size and disk**, not **playback
  memory**.

---

## Likely interview questions

1. **"How does source separation work?"** A supervised model (HTDemucs),
   trained on mixes paired with their true stems, predicts each instrument's
   waveform. It is hybrid: it processes the waveform and the spectrogram in
   parallel, with a transformer for long-range context.
2. **"Why is mixing just addition?"** Sound waves physically superpose:
   pressures add. Digital samples copy that, so sum the stems for the mix and
   multiply for volume.
3. **"How do you know the separation is good enough?"** The residual check: the
   stems sum back to within about 18 dB of the original. Plus listening tests on
   the riskiest assumption *before* building anything (Phase 1).
4. **"Why can't you boost a stem above 100%?"** It amplifies separation
   artifacts; 100% means "as on the record"; and lowering the others gives the
   same balance safely.
5. **"Why does soloing the vocals make the song quieter?"**
   > "Soloing a stem drops the overall level by however much that instrument
   > contributed. Vocals alone were only about 5 dB down because they carry a
   > third of the energy. I keep levels true to the record rather than
   > auto-normalising, because boosting a separated stem also boosts its
   > artifacts."
6. **"Why Opus?"** About 15× smaller to send, perceptually transparent. Keep the
   WAVs for analysis, since compression is lossy.
7. **"What limited your model choice?"** A 4 GB GPU and about 6 GB of RAM: no
   RoFormer, `shifts=1`, and chunked processing.
