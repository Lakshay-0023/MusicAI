# Section 4: Waveform, beats and looping

[← Section 3, The browser player](03-browser-player.md) · [Index](README.md) · Next: [Section 5, Chords →](05-chords.md)

Seeing the song, knowing where every beat and bar is, and looping a section
so it restarts exactly on the "1".

---

## 4.1 The waveform: drawing millions of samples in a few hundred pixels

A song is millions of samples; the screen is a few hundred pixels wide. So in
[`peaks()`](../../frontend/src/audio/AudioEngine.ts) **each pixel stands for a
chunk of the song**, drawn at the height of the **loudest moment** in that
chunk:

```
song:   ~12,500 samples per pixel  →  1 number per pixel  →  one vertical bar
```

- It reads only about 150 samples per chunk (stepping through it), which looks
  identical and is several times faster.
- It sums all six stems (the full mix) and scales so the loudest pixel fills
  the height.
- **Drawn on a `<canvas>`** ([Waveform.tsx](../../frontend/src/components/Waveform.tsx)),
  repainted in its own animation loop: the played part in the accent colour,
  the rest grey, plus bar lines and the loop region. No server involvement; it
  uses audio already decoded for playback.

## 4.2 Words first: beat, downbeat, meter, pickup

```
beat:      1   2   3   4 | 1   2   3   4 | 1   2   3   4
           ↑               ↑               ↑
        downbeats ("the one"), where each bar starts

meter = beats per bar: 4 for most pop and rock, 3 for a waltz
```

A **pickup** is a few notes *before* the first downbeat ("Happy Birthday"
starts on one). **Tempo** is beats per minute (BPM).

**Why the app needs them:**
- A loop that restarts a fraction of a beat late is useless: you feel the
  stumble every time it wraps. Loops must start on a bar line.
- Chords change on beats, nearly always on beat 1 (Section 5).

## 4.3 Version 1: a hand-written rule (librosa)

The first beat finder, still kept as a fallback, is `librosa.beat.beat_track`,
a rule someone wrote by hand:

1. **Onset strength:** for each ~23 ms slice, how much louder did it just get?
   Drum hits give tall spikes.
2. **Tempo:** which gap between spikes repeats most often? That gap is one beat.
3. **Dynamic programming:** choose the beat times that sit on strong spikes
   *and* stay evenly spaced; every combination is scored and the best kept.

It ran on the **drum stem**: to this rule a loud guitar chord looks like a drum
hit, and isolated drums are almost nothing but hits. Free accuracy, since the
stem already exists.

**Its weaknesses:** it finds beats but **no downbeats** (bars were *assumed* to
start every 4th beat from the first one, wrong for waltzes and pickups); it
needs clear hits; and it assumes one steady tempo.

## 4.4 Version 2: a trained model (Beat This!)

Now the app uses **Beat This!** (Johannes Kepler University, 2024), a neural
network trained on thousands of songs that people had tapped along to by hand.
Nobody wrote down what a beat is; the model learned it. For every 20 ms of
audio it outputs two probabilities:

```
audio ─► spectrogram ─► network ─► P(beat here)     ▁▁█▁▁▁█▁▁▁█▁▁▁█▁
                                  P(downbeat here)  ▁▁█▁▁▁▁▁▁▁▁▁▁▁█▁
                                       peaks = the beats and the bar starts
```

- **Finds downbeats**, so bar lines land on the real "1", including after a
  pickup.
- **Needs no drums**: it hears bar starts in the harmony and phrasing too.
- **Follows tempo drift.** The same idea Chordify uses; theirs is private, this
  one is open source and small enough for a 4 GB GPU.

**Why it hears the whole song now:** the rule wanted drums alone; the model was
trained on **full mixes**. The upload isn't kept, but the stems add back up to
the song (Section 2), so [`load_mono`](../../backend/woodshed/audio/analysis/source.py)
sums all six at 22.05 kHz mono, the rate the model was trained at.

**Memory discipline:** the model is loaded, used, deleted, and GPU memory is
released (`torch.cuda.empty_cache()`), so it never holds VRAM that Demucs
needs. **Install detail:** `beat-this` is installed with `--no-deps` so it
cannot replace the CUDA build of PyTorch.

## 4.5 What `beats.py` adds on top of the model

[audio/analysis/beats.py](../../backend/woodshed/audio/analysis/beats.py):

| Function | What it does | Why |
| --- | --- | --- |
| `extend_to_start` | Continues the grid backwards to 0:00 at the same spacing | Nothing is detected before the music starts, so a quiet intro had no bar lines to snap a loop to. Produced music holds a steady tempo, so the spacing projects back reliably |
| `tempo_of` | 60 ÷ the **median** gap between beats | Median, so one missed or doubled beat can't drag the answer |
| `meter_of` | Counts beats between each pair of downbeats; takes the usual answer | 4 for most songs, 3 for a waltz, measured rather than assumed |
| `load` | Returns `None` for an old file without downbeats | Old songs re-analyse themselves once, with no migration script |

The result, `beats.json`:

```json
{ "tempo": 83.33, "beatsPerBar": 4, "beats": [...], "downbeats": [...], "method": "beat_this" }
```

**A known quirk:** beat trackers often lock onto **double tempo** on slow
ballads. "Ae Dil Hai Mushkil" came out at 125 bpm but feels like about 62.
Harmless for looping (bar lines still fall on real beats), but it is why the
chord cleanup in Section 5 measures in seconds as well as beats.

## 4.6 Looping that lands on the beat

**Selecting:** drag across the waveform. On release, both ends **snap to the
nearest bar start** ([Waveform.tsx `snapToBar`](../../frontend/src/components/Waveform.tsx)),
so a rough drag still makes a musical loop. A drag under one second counts as
a click: "go here".

**Bar starts come from one helper**, [lib/bars.ts](../../frontend/src/lib/bars.ts):
the detected downbeats, or for old data every `beatsPerBar`-th beat. The bar
lines, the snapping and the "bars 13–17" label all ask it, instead of each
repeating the guess.

**The looping itself is done by the audio thread**, in
[`play()`](../../frontend/src/audio/AudioEngine.ts):

```ts
source.loop = true
source.loopStart = loop.start
source.loopEnd = loop.end
```

The obvious approach (watch the clock in JavaScript and jump back when
playback passes the end) is wrong: the main thread pauses regularly for
rendering and memory clean-up, so the jump lands late by however busy the page
was. Tens of milliseconds, audible, and different every time round. The audio
engine wraps the loop itself, **sample-accurately**, whatever the page is
doing.

**Position while looping:** elapsed time keeps growing past the loop end, so
the playhead is folded back into the loop with a modulo:

```js
if (pos > loop.end) pos = loop.start + ((pos - loop.start) % (loop.end - loop.start))
```

Divide by the loop length and keep the remainder.

## Code map

| File | Role |
| --- | --- |
| [audio/analysis/beats.py](../../backend/woodshed/audio/analysis/beats.py) | Beat This! (+ librosa fallback), grid extension, tempo, meter, `beats.json` |
| [audio/analysis/source.py](../../backend/woodshed/audio/analysis/source.py) | Loads chosen stems summed into one mono signal |
| [api/routes/analysis.py](../../backend/woodshed/api/routes/analysis.py) | `GET /tracks/<id>/beats`: cached file, or analyse on first request |
| [audio/AudioEngine.ts](../../frontend/src/audio/AudioEngine.ts) | `peaks()`, `setLoop()`, looping in `play()`, folded `position` |
| [components/Waveform.tsx](../../frontend/src/components/Waveform.tsx) | Canvas drawing, bar lines, drag-to-loop, snapping |
| [lib/bars.ts](../../frontend/src/lib/bars.ts) | `barStarts()`: where each bar starts |
| [components/Transport.tsx](../../frontend/src/components/Transport.tsx) | The "bars 13–17" loop label |

## Likely interview questions

1. **"How do you detect beats?"** A neural beat tracker, Beat This!, on the
   full mix (the stems summed back), which outputs beat and downbeat
   probabilities; the peaks are the beats and bar starts. A rule-based librosa
   tracker on the drum stem is the fallback.
2. **"Why did you replace the librosa tracker?"** It couldn't find downbeats, so
   bars were guessed and wrong after pickups or in 3/4; it needed drums; and it
   assumed a steady tempo.
3. **"How do your loops stay tight?"** The audio thread loops the buffers itself
   (`loop`, `loopStart`, `loopEnd`), sample-accurately. A JavaScript timer would
   jump late whenever the page was busy.
4. **"How do loops snap to bars?"** On release, each end moves to the nearest
   detected downbeat.
5. **"What's a limitation?"** Tempo can lock at double speed on slow songs; the
   grid is extended backwards assuming a steady tempo.
