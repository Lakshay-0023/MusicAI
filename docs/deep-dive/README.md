# Woodshed: the deep dive

A section-by-section study guide to the whole project: the concepts, what was
used and why, what was *not* used and why not, where each part lives in the
code, and the questions you are likely to be asked about it.

This folder complements the two main docs:

- [`../README.md`](../README.md) is the phase-by-phase history: how the
  project was built, in order, with every decision and measurement as it
  happened.
- [`../CONTEXT.md`](../CONTEXT.md) is the current state: what exists, what is
  proven, and the settled decisions.
- **This folder** goes through the *finished* system one part at a time, as
  you would explain it to someone else.

Each section ends with **likely interview questions** and short answers.

## Sections

| # | Section | Status |
| --- | --- | --- |
| 0 | [The big picture](00-big-picture.md): what it is, architecture, tech stack, folder map | ✅ |
| 1 | [Upload and the processing pipeline](01-upload-and-processing.md): from dropping a file to "song ready", including hashing in depth | ✅ |
| 2 | [Audio basics and source separation](02-audio-and-separation.md): samples, mixing, decibels, Demucs, WAV vs Opus | ✅ |
| 3 | [The browser player](03-browser-player.md): Web Audio, keeping six tracks in sync, speed and pitch | ✅ |
| 4 | [Waveform, beats and looping](04-beats-and-looping.md): Beat This!, downbeats, bar-snapped loops | ✅ |
| 5 | [Chords](05-chords.md): spectrograms, the BTC model, smoothing with a change penalty | ✅ |
| 6 | [Lyrics](06-lyrics.md): Whisper, Roman script, forced alignment, gaps | ✅ |
| 7 | [The chord sheet](07-chord-sheet.md): pinning chords to words, the karaoke UI | ✅ |
| 8 | [AI lyric correction](08-ai-lyrics.md): Gemini, and the audio as fact-checker | ✅ |
| 9 | [Engineering under constraints](09-engineering.md): memory and GPU limits, architecture, measuring, scaling | ✅ |
| 10 | [Interview prep](10-interview-prep.md): the pitch, key numbers, Q&A, real stories | ✅ |

## How to use it

- Read a section, then open the files it links to and find each piece it
  describes.
- Try answering its interview questions out loud before reading the answers.
- The numbers quoted (sizes, loudness, timings) were measured on the songs in
  `data/cache/`, so you can re-run the checks yourself.
