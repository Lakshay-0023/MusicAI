# Section 8: AI lyric correction

[← Section 7, The chord sheet](07-chord-sheet.md) · [Index](README.md) · Next: [Section 9, Engineering under constraints →](09-engineering.md)

An opt-in "Fix lyrics with AI" button: Gemini listens to the vocal track,
reads Whisper's lyrics and (optionally) lyrics you paste, corrects misheard
words and adds lines Whisper missed, and then **the audio itself checks every
change** before it is kept.

---

## 8.1 What an LLM is (and isn't) good for here

A language model reads **text**; on its own it cannot hear. So it gets exactly
the jobs that are about **language**:

| Job | LLM? | Why |
| --- | --- | --- |
| Fix misheard words ("tard hi sahi" → "dard hi sahi") | **Yes** | It knows Hindi and context. The LyricWhiz research (Whisper as the "ear", GPT-4 as the "brain") showed large error reductions this way |
| Natural, consistent Roman spelling ("guzaara", one "alvida" not three) | **Yes** | Better than any rule list |
| Merge with lyrics you paste | **Yes** | Matching two texts is a language task |
| Label sections (verse, chorus) | **Yes** | Repetition and rhyme are visible in text |
| Find chords | **No** | Audio task; Section 5 |
| Timing | **No** | The forced aligner measures it; Section 6 |
| An "agent" | **No** | The steps are the same every time; an agent would only add unpredictability |

Gemini *can* also take audio as input, which turned out to matter (8.3).

## 8.2 The first version, and why it failed

The first version sent **text only** to a small model
(`gemini-3.5-flash-lite`), with one rule: one corrected line for every heard
line. On a live recording of "Channa Mereya", with pasted lyrics, it made
things **worse**:

```
HEARD: Achchha chalta hun tu aaune aad rakhna  →  Aaccha chalta hoon duaaon mein yaad rakhna  ✓
HEARD: Jada   (six one-second fragments)        →  "Channa mereya mereya" × 6                  ✗
HEARD: Mere aav liya                            →  Kitni dafaa, subha ko meri                 ✗
```

Three design faults:

1. **It was forced to answer every line**, so it crammed the chorus onto
   fragments it couldn't place.
2. **Its only safety check compared word counts**, never whether the new words
   sound like what was heard.
3. **It could not add lines at all**, and missing lines were the real problem
   (Whisper drops passages it is unsure of).

## 8.3 The design now: the LLM proposes, the audio decides

```
① gather   the vocal stem (sent as a small MP3), Whisper's lines with timings,
           the "gaps" (singing heard, nothing transcribed), any pasted lyrics
② Gemini   listens and reads; for EVERY heard line: keep / correct / not lyrics,
           plus an INSERT, with its time, for every sung line Whisper missed
③ check    every change against the audio with the forced aligner
④ retry    rejected suggestions go back to Gemini once, with the reason
⑤ re-time  only the changed lines; untouched lines keep their exact times
```

**Model and settings** ([ai/gemini.py](../../backend/woodshed/ai/gemini.py)):

- **`gemini-3.8-flash`**, Google's strongest stable Flash model. The task is
  judgment (listening, matching, deciding what is really sung), and the
  smaller model lacked it.
- **Temperature left at its default:** Google warns that lowering it on
  Gemini 3 models can cause looping and worse answers.
- **Thinking at "high".**
- **Structured output:** Gemini must answer in a fixed JSON shape (a Pydantic
  model: action, heard line number, times, text, section, pasted line number),
  parsed and validated by code. Nothing is picked out of prose.
- **Data first, instructions last**, as Google advises for large inputs.
- **Provider isolated in one file:** switching to Claude or another model
  touches only `ai/gemini.py`.

**The prompt** ([ai/polish.py `SYSTEM`, `INSTRUCTIONS`](../../backend/woodshed/ai/polish.py))
is written around the rules a good human transcriber follows:

- Every heard line gets a decision; **"keep" and "not lyrics" are valid**, so it
  is never forced to pick a line.
- **What is sung, not what is written:** pasted lyrics supply wording and
  spelling; the recording supplies repeats, order and omissions.
- **Line boundaries:** never pull in words from a neighbouring line; never
  "complete" a fragment.
- **Minimal change:** "when unsure between keep and correct, choose keep".
- **Spelling conventions**, with examples.
- **Six worked examples**, including the exact failure above ("a fragment is
  NOT a place to put a whole lyric line").

**What is given per line:** our Roman text, Whisper's original Devanagari, and
the words Whisper was least sure of (confidence `p` below 0.5): where to look
hardest.

## 8.4 The audio as fact-checker

The forced aligner (Section 6) can also say **how well the audio supports some
words being sung in a given place** ([`Aligner.fit`](../../backend/woodshed/audio/analysis/lyrics.py)).
Text that isn't sung there cannot score well, however plausible it reads.

| Check | Rule | Measured basis |
| --- | --- | --- |
| **A correction** | Fits ≥ 0.35, and not more than 0.20 worse than the heard text in the same place | Good corrections fitted 0.39–0.81; the chorus forced onto fragments 0.07–0.24 |
| **An inserted line** | Must not overlap any heard line | If something was heard there, the right move is to *correct* that line |
| | Must beat **its own letters scrambled** by ≥ 0.17, and fit ≥ 0.30 | True lines beat their scramble by +0.18 to +0.49; fakes by at most +0.15 |

**Why the scramble:** at first an insert only needed a fixed score, and a
made-up line placed during the judges' talking *passed*. In dense speech **any**
text fits 0.43–0.52, because there are speech sounds everywhere to latch onto.
So each insert is compared with a **nonsense control**: the same letters,
reversed, in the same place. Busy audio raises both scores; only words really
sung pull ahead. The margin is narrow (0.15 vs 0.18), worth watching on more
songs. A single very long held word can't be scored, so an insert like that is
rejected: the safe side.

**The retry** sends rejections back once, in plain words: *"H26 correct →
'Channa mereya mereya': not supported by the audio (fit 0.07; the heard text
fits 0.14)"* or *"insert at 6:16: heard line H52 is already at that time —
correct H52 instead"*. What still fails is dropped; the line stays as heard.

**Tested end to end** with a stand-in for Gemini, so the right outcome is known:

| Case | Result |
| --- | --- |
| A real line hidden from the heard lines, inserted at its true time | **accepted**, restored at 69.6 s |
| Good corrections | accepted |
| The chorus forced onto "Mere ya mere ya" and "Jada" | rejected |
| A made-up line during the talking | rejected (overlaps heard lines) |
| A wrong lyric inserted into a real singing gap | rejected (no better than its scramble) |

## 8.5 Pasting your own lyrics, and the wrong-song check

Pasting the song's lyrics is optional. With them, the wording comes from your
text while the structure (repeats, order, what is actually sung) comes from the
recording.

**Wrong song? Checked first, for free, offline,** before anything is sent:
compare **word pairs** ("dil hai", "tere bina") heard against pasted. Single
words weren't enough: songs share "hai", "mera", "dil", and a *different* song
still scored 30%. With pairs: the same song scored **69–100%** (even with half
the lines pasted, or spelt differently), a different song **2–3%**. Under 25%,
the app asks before going on. Gemini gives its own verdict too.

## 8.6 Safety rails and privacy

- **Nothing can get worse than Whisper:** every change must pass the audio
  check; failures keep what was heard.
- **Untouched lines are never re-timed:** re-aligning an already-timed line is
  unstable on long held words (one moved from 35.3 s to 38.8 s), so only changed
  lines are re-timed. Measured: 66 untouched lines, 0 words moved.
- **Undo:** Whisper's version is kept as `heardLines`: "As heard" to compare,
  "undo" to restore. "Redo" always starts again from what Whisper heard.
- **What leaves the machine:** the vocal stem as a small mono MP3 (about
  0.5 MB a minute) and lyrics text, only when the button is pressed. The key is
  read from the `GEMINI_API_KEY` environment variable, never stored in code.
- **Failures are graceful:** no key, offline, or a refusal → the lyrics simply
  stay as heard (the API returns 503 with the reason).

## 8.7 Measuring it, not trusting it

`woodshed score "song.mp3" --truth correct.txt` reports two numbers, for
Whisper alone and for the AI version:

- **Word error rate (WER):** the fewest word insertions, deletions and
  substitutions that turn our lyrics into the correct ones, divided by the
  number of correct words. The standard speech-recognition measure. Spelling
  variants count as right.
- **Lines missing:** the share of the correct lyrics' lines that appear nowhere
  (the failure WER blurs).

## Code map

| File | Role |
| --- | --- |
| [ai/gemini.py](../../backend/woodshed/ai/gemini.py) | The only file that talks to the model: audio + prompt in, validated object out |
| [ai/polish.py](../../backend/woodshed/ai/polish.py) | Prompt, answer shape, the audio checks, retry, re-timing, wrong-song check, WER and missing-line measures |
| [audio/analysis/lyrics.py](../../backend/woodshed/audio/analysis/lyrics.py) | `Aligner.fit` / `place`, `find_gaps` |
| [api/routes/analysis.py](../../backend/woodshed/api/routes/analysis.py) | `POST …/lyrics/polish` (409 = wrong song, 503 = AI unavailable), `POST …/lyrics/restore` |
| [components/LyricsTools.tsx](../../frontend/src/components/LyricsTools.tsx) | The bar: paste box, "Fix lyrics with AI", Corrected / As heard, undo |
| [cli.py](../../backend/woodshed/cli.py) | `woodshed polish`, `woodshed score` |

## Likely interview questions

1. **"How do you use an LLM without letting it hallucinate lyrics?"** It only
   proposes. Every change is checked against the audio with a forced aligner:
   corrections must fit at least as well as what was heard, and inserted lines
   must beat a scrambled-letter control. Rejections go back once with reasons;
   anything still unsupported is dropped.
2. **"Why not let the LLM do everything?"** It can't measure timing or hear
   chords; specialised models do those better. The LLM handles language
   (wording, spelling, merging, sections).
3. **"How did you detect a pasted lyric from the wrong song?"** Word-pair
   overlap, which separated same-song (69–100%) from different-song (2–3%)
   cleanly, where single words did not.
4. **"What went wrong with the first version?"** Forced one-to-one answers, a
   word-count-only safety check, and no way to add lines. It replaced fragments
   with the chorus. The redesign added "keep / not lyrics", inserts, and audio
   verification.
5. **"How do you know it helps?"** Word error rate and missing-line rate against
   hand-typed correct lyrics, for both versions.
