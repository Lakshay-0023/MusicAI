# Section 3: The browser player

[← Section 2, Audio and separation](02-audio-and-separation.md) · [Index](README.md) · Next: [Section 4, Beats and looping →](04-beats-and-looping.md)

How six separate audio files play as one song, perfectly in sync, with live
mixing, looping, and speed changed without changing the pitch. All of it runs
in the browser, in [audio/AudioEngine.ts](../../frontend/src/audio/AudioEngine.ts).

---

## 3.1 Why the mixing happens in the browser

Imagine the opposite: every slider nudge sends a request, the server renders a
new mix, sends it back, and playback restarts. Every adjustment would cost
seconds and stutter. Doing the multiply-and-add ([Section 2](02-audio-and-separation.md))
on the listener's own machine makes it **instant, free, and able to work
offline**. The server only ships the stems once.

## 3.2 The Web Audio API and the "audio graph"

Browsers contain a professional audio engine, the **Web Audio API**. You build
a **graph**: sources of sound, connected through processing nodes, ending at
the speakers. Ours:

```
Vocals buffer ─► source ─► GainNode (Vocals level) ─┐
Drums  buffer ─► source ─► GainNode (Drums level)  ─┤
Bass   buffer ─► source ─► GainNode (Bass level)   ─┤
Guitar buffer ─► source ─► GainNode (Guitar level) ─┼─► Master GainNode ─► Stretcher ─► speakers
Piano  buffer ─► source ─► GainNode (Piano level)  ─┤        (volume)       (pitch)
Other  buffer ─► source ─► GainNode (Other level)  ─┘
```

| Piece | What it is |
| --- | --- |
| **`AudioContext`** | The engine itself, with its own clock (`ctx.currentTime`) |
| **`AudioBuffer`** | One stem, fully decoded into raw samples in memory |
| **`AudioBufferSourceNode`** | A "play head" that plays a buffer. Single-use: once stopped, it can never start again |
| **`GainNode`** | Multiplies every sample passing through by a number: volume. **This is the mixing from Section 2, done by the browser** |
| **Master `GainNode`** | One volume for everything |
| **Stretcher** | Signalsmith Stretch, a third-party pitch shifter (3.6) |

Wherever several nodes connect into one, the browser **adds** them: mixing is
addition, done for us.

## 3.3 Loading: everything first, then play

[`load()`](../../frontend/src/audio/AudioEngine.ts):

1. Fetch all six stems at once (`/stems/<id>/<name>`, the Opus files).
2. `ctx.decodeAudioData` turns each compressed file into raw samples (an
   `AudioBuffer`).
3. **Only when all six are decoded** is the song ready.

**Why wait for all six:** if playback began while files were still arriving,
the quick ones would start early: exactly the drift the whole design avoids.

**Why the first click both loads and plays:** browsers refuse to let a page
make sound before the user interacts with it (otherwise every page could blare
at you). So the `AudioContext` is created on the first click (`init()`).

## 3.4 Keeping six tracks in sync, the core problem

Six separate sources must start **at exactly the same sample**. If one starts
even a few milliseconds late, the instruments drift apart, which sounds like a
flam or an echo.

The naive approach fails:

```js
for (const stem of STEMS) source.start()      // ✗ each start happens a tiny bit later
```

JavaScript runs one line after another, so each `start()` happens slightly
after the previous one, and the page can pause at any moment (rendering,
garbage collection).

**The fix: schedule all six against the audio clock**, in
[`play()`](../../frontend/src/audio/AudioEngine.ts):

```ts
const startAt = this.ctx.currentTime + LEAD_IN      // computed ONCE: 0.1 s in the future
for (const stem of STEMS) this.sources[stem]!.start(startAt, from)
```

- **The audio clock** (`ctx.currentTime`) is the sound card's own clock, not
  JavaScript's. Telling every source "start at clock time X" makes the *audio
  thread* start them all on the same sample, however busy the page is.
- **`LEAD_IN` (0.1 s):** enough headroom to schedule all six before the moment
  arrives.
- **Computed once, before the loop:** reading the clock inside the loop would
  give each stem a slightly different time.

## 3.5 Pause, seek and position

**Sources are single-use**, so pausing or seeking means throwing the six
sources away and building six new ones (`stopSources()` then `play(from)`). The
decoded audio in the buffers is untouched, which is why it feels instant.

**Where are we in the song?** Two numbers are recorded when playback starts:
`offset` (where in the song it began) and `startedAt` (the audio clock at that
moment). Then:

```
position = offset + (clock now − startedAt) × speed
```

Example: started at 42 s when the clock read 5.1; at clock 8.1 the position is
`42 + (8.1 − 5.1)` = **45 s**. Derived from the audio clock, it never drifts.

**Position never goes through React.** The waveform's playhead and the clock
run their own animation loop (`requestAnimationFrame`, about 60 times a second)
and read `engine.position` directly. Re-rendering React components 60 times a
second just to move a playhead would be pure waste.

## 3.6 Speed and pitch, independently

Practising means slowing a song down, **without** it dropping in key. The
physics: playing audio faster or slower changes **speed and pitch together**,
like a record player. At 70% speed, everything is 6.18 semitones lower.

The design, and why it is not the obvious one:

1. **Speed comes from `playbackRate`** on the six sources: simple resampling,
   which keeps them perfectly in sync (the same rate on all six). It also drags
   the pitch down.
2. **One pitch shifter after the mix** pushes the pitch back up by exactly the
   amount the speed change lowered it:

```ts
stretch.schedule({ semitones: userSemitones - 12 * Math.log2(speed) })
//                 your transpose  +  the correction for the speed change
```

At 70%: `12 × log2(0.7) = −6.18`, so the shifter adds +6.18 semitones and the
song sounds in its original key. Your own transpose (± semitones) is added on
top.

**Why only one shifter, after the mix:** six shifters (one per stem) would cost
six times the CPU and could drift apart. One shifter on the master bus keeps
the volume sliders live, because mixing happens before it.

**Why Signalsmith Stretch:** time-stretching cannot be done with plain Web
Audio; it needs a dedicated algorithm. Signalsmith Stretch is **MIT-licensed**
(Rubber Band, the other good option, is GPL, which would force the whole app to
be open-sourced under GPL), sounds clean, and ships as **WebAssembly** running
inside an **AudioWorklet** (the browser's real-time audio thread). It is loaded
at runtime from `frontend/public/vendor/SignalsmithStretch.mjs`, by full URL.

**A subtle consequence:** when the speed changes *during* playback,
`setSpeed()` first "banks" the position (`offset = position; startedAt = now`),
because everything played so far happened at the old speed. Without that, the
playhead would jump.

## 3.7 Mute, solo and levels

[Mixer.tsx](../../frontend/src/components/Mixer.tsx) shows one row per stem:
**M** (mute), **S** (solo), and a level slider (0–100%).

```ts
gainFor(stem):  muted → 0;  something else soloed → 0;  otherwise → its level
```

- **Ramping, not jumping:** `setTargetAtTime(value, now, 0.015)` glides to the
  new volume over about 15 ms. An instant change makes the waveform take a
  vertical step, heard as a click.
- **Why M/S buttons as well as sliders:** in practice, muting an instrument to
  play its part is constant, soloing to learn it is frequent, and setting
  something to 37% is rare. Sliders alone would make solo mean "drag five
  sliders to zero and back".
- **The slider never moves when muting:** the row dims instead, so your level
  survives unmuting (muting to 0 on the slider would forget your 40%).

## 3.8 React and the engine: who owns what

```
AudioEngine (plain TypeScript class)   ← owns ALL sound; knows nothing of React
        ▲   ▼ subscribe(state)
usePlayer() hook                       ← creates the engine ONCE, mirrors its state into React
        ▲   ▼
Components (Mixer, Transport, ...)     ← call engine.setLevel(), engine.toggle()...
```

- [usePlayer.ts](../../frontend/src/hooks/usePlayer.ts) creates the engine
  **once**, held in a `useRef`, and subscribes to its state.
- **Why the engine isn't React state:** React re-renders constantly. If React
  owned the audio graph it would be rebuilt on render, and the sample-accurate
  sync would collapse.
- **Only discrete changes go through React:** playing or paused, levels, loop
  points. Never the moving position.

## 3.9 Keyboard shortcuts

[useKeyboard.ts](../../frontend/src/hooks/useKeyboard.ts): **space** play or
pause, **← →** skip 5 s, **1–6** mute a stem, **Esc** clear the loop, **F** focus
mode. You are holding an instrument; reaching for the mouse breaks practice in
a way a keystroke does not. Keys are ignored while a text box or slider has
focus.

## Code map

| File | Role |
| --- | --- |
| [audio/AudioEngine.ts](../../frontend/src/audio/AudioEngine.ts) | The whole audio graph: load, play, pause, seek, mix, speed and pitch, loops, waveform peaks |
| [audio/types.ts](../../frontend/src/audio/types.ts) | `STEMS`, `Loop`, `PlayerState` |
| [hooks/usePlayer.ts](../../frontend/src/hooks/usePlayer.ts) | One engine for the app's lifetime, state mirrored into React |
| [components/Transport.tsx](../../frontend/src/components/Transport.tsx) | Play button, seek bar, clock, loop label |
| [components/Mixer.tsx](../../frontend/src/components/Mixer.tsx) | Six rows: mute, solo, level |
| [components/PracticePanel.tsx](../../frontend/src/components/PracticePanel.tsx) | Speed, pitch, master volume |
| [public/vendor/SignalsmithStretch.mjs](../../frontend/public/vendor/SignalsmithStretch.mjs) | The pitch shifter (MIT, WebAssembly) |

## Honest limitations

- **Memory:** six decoded stems take about 500 MB of browser memory, whatever
  format they were downloaded in.
- **The pitch shifter adds a few tens of milliseconds of delay**, so the
  playhead and the sound are very slightly out of step at non-default settings.
- **Speed range:** quality is best between about 0.75× and 1.5×; the slider
  goes to 0.5×.

## Likely interview questions

1. **"How do you keep six audio files in sync?"** I schedule every source
   against the audio hardware clock, with one shared start time computed once,
   0.1 s ahead, so the audio thread starts them all on the same sample,
   independent of JavaScript timing.
2. **"How does slowing down without changing pitch work?"** Speed comes from
   resampling all six sources at the same rate, which lowers the pitch; one
   pitch shifter after the mix raises it back by `−12·log2(speed)` semitones.
   One shifter instead of six keeps it cheap and in sync.
3. **"Why isn't the audio engine React state?"** The audio graph is long-lived
   and timing-critical; React re-renders constantly. The engine is a plain class
   created once; only discrete changes flow into React, and the moving position
   is read directly in an animation loop.
4. **"Why do volume changes not click?"** Gains ramp over 15 ms with
   `setTargetAtTime` instead of jumping.
5. **"Why Signalsmith over Rubber Band?"** MIT versus GPL licensing, and it runs
   as WebAssembly in an AudioWorklet.
