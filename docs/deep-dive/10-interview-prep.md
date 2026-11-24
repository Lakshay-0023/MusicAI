# Section 10: Interview prep

[← Section 9, Engineering](09-engineering.md) · [Index](README.md)

Everything from Sections 0–9, condensed into what to say. Practise these out
loud.

---

## 10.1 The pitch

**30 seconds:**

> "Woodshed is a music-practice app. You give it any song, and it uses AI to
> separate the instruments, find the beats, the chords and the lyrics. Then a
> browser player lets you mute or solo instruments, slow the song down without
> changing its key, loop bars, and follow a karaoke-style chord sheet. The AI
> runs once per song on a laptop GPU; the player mixes everything live in the
> browser."

**2 minutes**, adding the how:

> "The backend is Python with FastAPI. An upload returns a job ID straight away,
> and progress streams back over server-sent events while a worker separates the
> song into six stems with Demucs, in crossfaded chunks so long songs fit in
> memory. Then it detects beats and downbeats with a neural beat tracker, chords
> with a transformer model plus Viterbi smoothing, and lyrics with Whisper on the
> vocal stem, re-timed by a forced aligner that I measured as about four times
> closer to the real vocal onsets.
>
> The frontend is React and TypeScript. The audio engine is a plain class on the
> Web Audio API: it schedules all six stems against the audio clock so they stay
> sample-locked, and a single WebAssembly pitch shifter after the mix lets you
> change speed without changing key. Chords are pinned to lyric words by timing
> rules and drawn as a scrolling sheet.
>
> There's an optional AI step where Gemini listens to the vocals and fixes
> misheard or missing lyrics, but every change it suggests is verified against
> the audio by the forced aligner, so it can't invent lyrics. All of it runs on a
> 4 GB laptop GPU, which drove most of the engineering."

## 10.2 Numbers worth remembering

| What | Number |
| --- | --- |
| Stems | 6: Vocals, Drums, Bass, Guitar, Piano, Other |
| Sample rate / bit depth | 44,100 Hz / 16-bit; ~10 MB per minute of WAV |
| WAV → Opus | ~15× smaller (60 MB → 4 MB) |
| Residual check | leftover ~18 dB below the music |
| Separation chunks | 30 s, 4 s crossfade |
| Chord model | BTC, 170 chord types, ~93 ms frames, 10 s windows |
| Chord levels (Ae Dil Hai Mushkil) | 156 → 103 (Normal) → 89 (Minimal) changes |
| Whisper turbo | 809M parameters; 1.6 GB in 16-bit; ~100 s per 5-min song |
| Word timing (median distance to vocal onset) | Whisper 0.13 s → aligner 0.03 s; 55% → 92% within 0.15 s |
| Wrong-song check (word pairs) | same song 69–100%, different 2–3% |
| AI insert check | true lines beat their scramble by ≥ 0.18; fakes ≤ 0.15 |
| Hardware | RTX 3050 4 GB VRAM, ~5.9 GB usable RAM |

## 10.3 Questions by topic, with short answers

### System and architecture
- **Why split backend and frontend like that?** Slow GPU work once per song;
  millisecond-level interaction in the browser.
- **Why FastAPI?** Async, built-in validation, background tasks and streaming
  responses, minimal boilerplate.
- **How is the backend organised?** Thin routes; an audio layer with no HTTP; a
  storage interface; one config; the CLI and API share all logic.
- **How do you avoid reprocessing?** SHA-256 of the upload as the track ID, plus
  a `meta.json` completeness marker written last.
- **Why server-sent events?** One-way progress over plain HTTP with automatic
  reconnection; WebSockets would be unused complexity.
- **How would you scale it?** Job queue, GPU workers, object storage behind the
  existing interface, auth, limits, audio fingerprinting.

### Audio fundamentals
- **What is a sample?** The speaker cone's position at one instant; 44,100 per
  second per channel.
- **Why 44.1 kHz?** More than twice the ~20 kHz hearing limit (Nyquist), plus
  filter headroom.
- **How does mixing work?** Addition (waves superpose); volume is
  multiplication.
- **Why are sliders capped at 100%?** Boosting amplifies separation artifacts;
  100% means "as on the record"; lowering others is equivalent and safe.
- **What are decibels?** A logarithmic loudness unit that matches hearing; −6 dB
  halves the sample values.

### Separation
- **How does Demucs work?** A supervised hybrid model (waveform + spectrogram
  branches with a transformer), trained on mixes paired with true stems, that
  outputs each instrument's waveform.
- **Why `htdemucs_6s`?** Guitar and piano as separate stems, which a practice app
  needs; bigger models don't fit 4 GB.
- **Why isn't separation perfect?** Bleed and artifacts; cymbals and reverb
  overlap everything.

### Player
- **How are six stems kept in sync?** Scheduled against the audio clock with one
  shared start time computed once, 0.1 s ahead.
- **How does slowing down keep the key?** Resample all stems (speed and pitch
  drop together), then one pitch shifter after the mix raises pitch by
  `−12·log2(speed)` semitones.
- **Why is the engine not React state?** Long-lived, timing-critical graph; React
  re-renders constantly. Position is read directly in an animation loop.
- **Why don't loops stumble?** The audio thread loops the buffers itself; a
  JavaScript timer would land late.

### Beats and chords
- **How are beats found?** A neural beat and downbeat tracker (Beat This!) on the
  full mix; librosa's rule-based tracker on the drum stem as fallback.
- **How are chords found?** Harmony stems → constant-Q spectrogram → BTC
  transformer → per-beat averaging → Viterbi with a change penalty.
- **Why a CQT?** Bins spaced like musical notes, so chord shapes look alike in
  every octave.
- **Why Viterbi?** Changing chord gets a cost, so blips disappear and real
  changes survive; three penalties give three detail levels.
- **Why not an LLM for chords?** It can't hear.

### Lyrics and combining
- **How are lyrics found?** Whisper on the vocal stem with the language forced
  to Hindi, converted to Roman letters by rule, timed by the MMS forced aligner.
- **Why force the language?** Auto-detection called a Hindi song English and
  translated it.
- **How do chords get onto words?** Timing rules: during a word, lead-ins, held
  notes, instrumental gaps; scaled to the song's beat and bar length.
- **How did you make AI corrections safe?** The audio decides: corrections and
  inserts must pass forced-alignment fit checks, including a scrambled-text
  control; rejections are retried once, then dropped.

## 10.4 Stories (situation → action → result)

Interviewers often ask for "a hard problem you solved". Each of these is real.

**1. The out-of-memory crash on long songs.**
A 5.7-minute song failed with "Unable to allocate 687 MiB". I traced it to
Demucs building all six stems for the whole song in RAM. I changed separation to
30-second chunks with 4-second overlaps, crossfaded so the model's edge effects
don't click, and appended each chunk to the stem files. I verified it by adding
the stems back together: the error at each join matched the middle of a chunk.
Memory no longer grows with song length.

**2. Whisper writing English sentences for a Hindi song.**
The first lyrics came back as fluent English: "Ae dil hai mushkil" became "This
soul is also my soul". I checked the language-detection scores: English 35%,
with Hindi not in the top five. Forcing the language to Hindi made the
transcription nearly word-perfect, so the language became a setting.

**3. Chords landing on the wrong word.**
Users saw chords shifted to the next line around held notes. Measuring showed
Whisper's word times were off by ~0.13 s on average and swallowed pauses. I added
a forced aligner and measured both against independently detected vocal onsets:
0.13 s → 0.03 s, 55% → 92% within 0.15 s. I also detected held notes from vocal
loudness and rewrote the placement rules. Re-timing also turned out to be
unstable on held words, so after AI corrections only changed lines are re-timed.

**4. Making an LLM safe to use.**
The first AI correction replaced short fragments with the chorus and couldn't
add missing lines. I redesigned it: Gemini listens to the vocals and proposes
keep / correct / not-lyrics / insert, and the forced aligner fact-checks every
change. A made-up line placed during talking still passed a fixed threshold,
because dense speech fits any text, so I added a control: each insert must beat
its own letters scrambled. Tested with a stand-in model, every fake was rejected
and a hidden real line was restored.

**5. The setup guide that didn't work.**
Before publishing SETUP.md, I followed it command by command in a clean copy.
The install failed with WinError 206: Windows' 260-character path limit against
deeply nested package files. My own setup never hit it because its path was
short. I documented keeping the project path short or enabling long paths, and
pinned matching torch and torchaudio builds, which the old instructions had
missed.

## 10.5 What I'd do differently, or next

- **Measure earlier:** several fixes came from users noticing problems that a
  quick measurement would have caught (word timing, the wrong-song check).
- **A small regression set:** a few songs with hand-checked lyrics and chords, so
  every change is scored automatically (WER, missing lines, chord accuracy).
- **Section detection and key detection**, for verse-aware chord placement and
  correct spellings.
- **Edit and learn:** let users correct lyrics and chords, and use those
  corrections as training data to fine-tune the chord model on this music.

## 10.6 Vocabulary to use precisely

| Term | One-line meaning |
| --- | --- |
| Stem | One instrument's audio, separated from a mix |
| Source separation | Producing stems from a mixed recording |
| Sample rate / Nyquist | Samples per second / must exceed twice the highest frequency |
| CQT | A spectrogram with note-spaced frequency bins |
| Transformer / attention | Layers that let each moment weigh every other moment |
| Viterbi | Dynamic programming for the best path through a sequence of guesses |
| Forced alignment | Finding exactly when known words occur in audio |
| Transliteration | Same words, different script (Devanagari → Roman) |
| Schwa deletion | Dropping Hindi's inherent "a" where speech drops it |
| WER | Word error rate: edits needed ÷ correct word count |
| Structured output | Forcing an LLM to answer in a fixed JSON shape |
| SSE | Server-sent events: a one-way, never-ending HTTP response |
| Content addressing | Naming data by a hash of its content |
| Half precision (fp16) | 16-bit numbers: half the memory |
| Meta device | PyTorch's shapes-only, no-memory model "outline" |
