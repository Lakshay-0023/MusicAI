# Section 5: Chords

[← Section 4, Beats and looping](04-beats-and-looping.md) · [Index](README.md) · Next: [Section 6, Lyrics →](06-lyrics.md)

How the app works out which chord is playing on every beat, and turns that
into something a player wants to read.

---

## 5.1 Where chords on websites come from

| Kind of site | How it gets chords |
| --- | --- |
| **Ultimate Guitar, e-chords** | **People.** Users work the chords out by ear and type them in; others vote and correct. Popular songs get good versions; obscure ones get bad versions or none |
| **Chordify, Moises, Yamaha Chord Tracker** | **Models.** The audio becomes a spectrogram, a neural network trained on hand-labelled songs predicts the chords, and a beat tracker aligns them to beats |

Woodshed is the second kind: a small Chordify.

**No language model is involved.** Finding chords is a music-analysis task
called **automatic chord estimation (ACE)**. It needs a network that reads
*sound*; an LLM reads text and cannot hear that bar 12 is E minor.

## 5.2 The pipeline

```
Bass + Guitar + Piano + Other stems  (drums and vocals left out)
        │
        ▼
① CQT spectrogram: which notes are sounding, every ~93 ms
        │
        ▼
② BTC model: for every frame, a probability for each of 170 chords
        │
        ▼
③ averaged within each beat (using beats.json)
        │
        ▼
④ Viterbi smoothing: the best chord path, where changing chord costs a penalty
        │
        ▼
chords.json: three versions, All / Normal / Minimal
```

### Which audio it hears

By default **Bass + Guitar + Piano + Other**: the harmony, without drums (pure
noise to a chord model) or vocals (a sung melody note looks like a chord note:
sing a D over a C chord and the model hears something closer to Cadd9). The
setting is `chord_stems` in [config.py](../../backend/woodshed/config.py), and
`woodshed chords song.mp3 --full-mix` lets it hear everything, to compare.

### ① The constant-Q transform (CQT)

A normal spectrogram spaces its frequency bins evenly (0 Hz, 10 Hz, 20 Hz…).
Music doesn't work evenly: each octave **doubles** the frequency, so the 12
notes from A2 to A3 span 110 Hz while A5 to A6 spans 880 Hz. Even bins waste
their detail on high notes and blur low ones together.

The **CQT** spaces its bins **like piano keys**: here **two bins per semitone,
over six octaves = 144 bins**. A note is then always the same number of bins
above the same note an octave lower, which is what makes chord shapes
recognisable.

```
          C    C#   D    D#   E    F    F#   G  ...
octave 3  ░░   ░░   ░░   ░░   ██   ░░   ░░   ██      E and G sounding
octave 4  ██   ░░   ░░   ░░   ░░   ░░   ░░   ░░      C sounding
                                                → C major (C, E, G)
```

- **Chroma** is the CQT folded into 12 bins (one per note name, octaves added
  together). BTC uses the full 144 bins instead, because *which octave* matters:
  the lowest note is usually the root, which separates Am (A in the bass) from
  C6 (C in the bass), although both contain the same four note names.
- The values are **logged** (`log(|CQT| + 1e-6)`): loudness is judged by
  ratios, and without the log one loud bass note would drown every other
  number.
- **10-second windows of 108 frames** (one frame ≈ 93 ms), exactly as BTC was
  trained; the song is padded with silence to a whole number of windows.

### ② BTC, the chord model

**BTC (Bi-directional Transformer for Chord recognition)**, Park et al., 2019,
MIT-licensed. It knows **170 chords**:

```
12 roots × 14 types   maj  min  7  maj7  min7  6  min6  dim  aug  dim7  m7b5  m(maj7)  sus2  sus4
+ N (no chord)  + X (a chord it can hear but not name)
```

- **"Transformer":** every frame in a window can look at every other frame
  (*attention*). **"Bi-directional":** once looking forwards in time, once
  backwards. So the guess for a frame is informed by what comes before *and*
  after, the way you know a passing note isn't a chord change because you heard
  what followed.
- **Normalising the input:** the weights file stores the *mean* and *spread* of
  the training data, and our features are scaled by exactly those numbers
  (`(x − mean) / std`). Skip that and every value is off by a constant, and the
  answers are nonsense. The most common mistake when reusing someone else's
  model.
- **`model.eval()`** switches off *dropout* (random blanking of parts of the
  network, a training trick) so answers are stable.
- **Output:** for every frame, a probability for each of the 170 chords.

**Why the code is copied in, not installed:** BTC is a GitHub repository, not
a pip package, and its code uses `np.float`, which numpy removed years ago. So
the network (about 200 lines) lives in
[audio/analysis/btc/](../../backend/woodshed/audio/analysis/btc/) with its MIT
licence, fixed for modern numpy. **Every class and attribute name is kept
unchanged**: the weights file stores each number under a name like
`self_attn_layers.self_attn_layers.0.attn_block.multi_head_attention.query_linear.weight`,
and renaming anything makes loading fail. The weights (12 MB) **download on
first use** to `data/models/`, under a temporary name renamed at the end, so an
interrupted download is never mistaken for a finished one.

**Tested:** synthetic C, Am, F and G7 chords (tones with known answers) came
back exactly right, including the 7th.

### ③ One decision per beat

```
frames (~93 ms):  Em Em Em G  Em Em | C  C  C  C  Am C |
                           ↑ passing note        ↑ stray frame
per beat:             Em            |        C         |
```

For each beat, the probabilities of every frame inside it are **averaged**.
Averaging rather than voting means a beat that is steadily 60% sure of Em
outweighs one stray frame that is 90% sure of G. This is why the beat grid
(Section 4) was built first.

### ④ Viterbi smoothing: making a change cost something

Even per beat, a passing bass note or a moment of doubt between two similar
chords (Em and G share two of their three notes) becomes a chord change lasting
under a second. On "Ae Dil Hai Mushkil" that meant **156 chord changes**, with
lines like `[B F# B]Aajmaati [F#]hai [Ebm Abm7]teri [B Bbm7]kami`.

Professional chord decoders (Chordino, madmom, ChordFormer) don't take each
beat's likeliest chord on its own. They find the best **path** through the song
where **every change has a price**. A real change easily pays it; a one-beat
blip cannot.

This is the **Viterbi algorithm** ([`_decode`](../../backend/woodshed/audio/analysis/chords.py)),
the standard way to find the best path through a sequence of guesses. Beat by
beat, it keeps for every chord the best score of any path ending on it:

```
stay on chord k:     best[k]                + evidence for k on this beat
switch to chord k:   best overall − penalty  + evidence for k on this beat
```

then traces back the choices behind the winning score. Scores are
log-probabilities, so a penalty of 3 means a change must be about e³ ≈ 20 times
better supported than staying put.

**One penalty per level**, all decoded on the server and saved side by side,
so the switch in the app is instant:

| Level | Penalty | Ae Dil Hai Mushkil | Besabriyaan |
| --- | --- | --- | --- |
| **All** | 0 (every beat for itself) | 156 changes | 101 |
| **Normal** (default) | 3 | 103 | 92 |
| **Minimal** | 6 | 89 | 73 |
| *(too far)* | 12 | 52 | 23: real changes vanish |

**What it replaced:** a first version tidied the chords afterwards with
hand-made rules (drop chords under half a bar or 1.5 s; at most two per bar).
It was **too sparse**: a rule about *length* can't tell a short real chord from
a short mistake. A cost weighed against the *evidence* can.

### The output, `chords.json`

```json
{ "start": 12.48, "end": 15.31, "label": "E:min", "name": "Em" }
```

`label` is research notation (Harte: `root:quality`); `name` is how a chord
sheet writes it. The file holds `levels: {all, normal, minimal}`, the stems
used, and the method.

## 5.3 Showing chords: choices that change the *names*, not the chords

The server stores one thing, `E:min7`. How it is written depends on choices you
make while practising, so that translation happens in the browser,
[lib/chords.ts `present()`](../../frontend/src/lib/chords.ts), instantly:

| Choice | What it does | Why |
| --- | --- | --- |
| **Pitch** (practice panel) | Names follow it: +2 turns Em into F#m | Chords should name what you *hear* |
| **Capo** | Shows the shapes to play: capo 2 turns F#m into Em | Guitarists think in shapes |
| **Simple** | Drops 7ths, 6ths and sus: Cmaj7 → C | Learning a song before polishing it |
| **All / Normal / Minimal** | Picks one of the three decoded versions | How much detail you want |

- **Spelling:** flats where charts conventionally use them (Bb, Eb, Ab), sharps
  elsewhere (F#, C#). Key detection could later choose per song.
- **Look-alikes merge:** with Simple on, G → G7 → G displays as one G
  ([lib/tidy.ts](../../frontend/src/lib/tidy.ts)).
- **Colour follows the circle of fifths:** roots a fifth apart (C→G→D→A…) get
  neighbouring hues (`hue = (root × 7 mod 12) × 30°`; multiplying by 7 walks
  the circle, since 7 semitones is a fifth). Chords that live together in a key
  form a family of colours, so a repeated section *looks* repeated in the
  **chord lane** under the waveform ([ChordLane.tsx](../../frontend/src/components/ChordLane.tsx)).

## 5.4 What accuracy to expect

Published results for models like this on pop and rock: about **80%** of the
time correct on plain major/minor, about **65%** once 7ths, sus chords and
inversions count. Chordify is in the same range.

- **Mostly right:** the main chords of verses and choruses.
- **Sometimes wrong:** similar chords (Em/G, Am/C, Bm/D), maj vs maj7, sus4
  resolving to maj.
- **Never shown:** inversions (C/E is reported as C).
- **Weaker on Bollywood arrangements** (strings, pads, harmonium), which BTC saw
  little of in training.

## Code map

| File | Role |
| --- | --- |
| [audio/analysis/chords.py](../../backend/woodshed/audio/analysis/chords.py) | CQT features, BTC probabilities, per-beat averaging, Viterbi levels, `chords.json`, the bar-by-bar text chart |
| [audio/analysis/btc/model.py](../../backend/woodshed/audio/analysis/btc/model.py) | The BTC network (copied, MIT, names unchanged) |
| [config.py](../../backend/woodshed/config.py) | `chord_stems`, `chord_model_url` |
| [lib/chords.ts](../../frontend/src/lib/chords.ts) | `present()` (names, transpose, capo, simplify, notes), colours, `chordIndexAt` |
| [lib/tidy.ts](../../frontend/src/lib/tidy.ts) | Picks the level; merges chords that look identical once displayed |
| [components/ChordLane.tsx](../../frontend/src/components/ChordLane.tsx) | The coloured chord strip under the waveform |

## Likely interview questions

1. **"How does chord recognition work?"** Harmony stems → constant-Q
   spectrogram → a bi-directional transformer (BTC) giving chord probabilities
   every 93 ms → averaged per beat → Viterbi decoding with a chord-change
   penalty.
2. **"Why not an LLM?"** It can't hear. Chord estimation is an audio task for a
   model trained on spectrograms.
3. **"How did you stop the chords flickering?"** Per-beat averaging, then
   Viterbi decoding where each change has a cost, so only well-supported changes
   survive. Three penalty levels give All / Normal / Minimal.
4. **"Why CQT instead of a normal spectrogram?"** Its bins are spaced like
   musical notes, so chord shapes look the same in every octave.
5. **"How did you reuse a research model that wasn't packaged?"** Copied the
   network with its licence, fixed a numpy incompatibility, kept every layer
   name so the trained weights load, normalised inputs with the training mean
   and spread, and verified on synthetic chords with known answers.
6. **"What are its limits?"** Similar-chord confusion, no inversions, weaker on
   non-Western arrangements.
