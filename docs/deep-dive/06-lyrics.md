# Section 6: Lyrics

[← Section 5, Chords](05-chords.md) · [Index](README.md) · Next: [Section 7, The chord sheet →](07-chord-sheet.md)

How the app writes down what is sung, in Roman letters, and works out
exactly when each word is sung.

---

## 6.1 Why the lyrics come from the audio

Lyric sites and apps get their text from licensed databases (Musixmatch,
LyricFind) or volunteers. They only know **released** songs, and a recording of
your own band is in none of them. So Woodshed writes the lyrics down **from the
audio itself**: speech recognition. It works on any recording with singing in
it, and nothing leaves the machine. (An optional AI pass can merge in lyrics
you paste: [Section 8](08-ai-lyrics.md).)

## 6.2 The pipeline

```
Vocals stem
   │
   ▼
① Whisper "turbo", told "this is Hindi"          → words, in Devanagari
   │
   ▼
② roman.py                                        → "कैसे" becomes "kaise"
   │
   ▼
③ words grouped into lines                        → Whisper's phrases, long ones split at a breath
   │
   ▼
④ MMS forced aligner                              → exactly when each word is sung
   │
   ▼
⑤ held-note check                                 → when the voice really stops after each line
   │
   ▼
lyrics.json
```

## 6.3 ① Whisper, on the vocals stem

**Whisper** is OpenAI's open-source speech-recognition model, trained on
680,000 hours of speech in about 100 languages, running locally on the GPU. The
model is **`turbo`**: large-v3 (Whisper's most accurate) with a slimmer
decoder, 809 million weights.

**Why the vocals stem:** Whisper learned from speech, and drums and guitars on
top of the voice confuse it badly. The separated vocal is as close to speech as
singing gets: the separation investment paying off a second time.

**Settings that keep it honest on music:**

| Setting | Why |
| --- | --- |
| `language="hi"` (told, not guessed) | Left to guess, Whisper called "Ae Dil Hai Mushkil" **English** (35%, with Hindi not in its top five) and wrote English *sentences* for Hindi singing: "Ae dil hai mushkil" came out as "This soul is also my soul". Told it was Hindi, the same song came back nearly word-perfect. `lyrics_language` in config; `--language en` for English songs |
| `word_timestamps=True` | A time for every word, not just every line |
| `condition_on_previous_text=False` | By default each 30 s piece is told what the last one said; on singing, one misheard line then repeats down the whole song |
| `hallucination_silence_threshold=2.0` | Over long silences (an instrumental break on the vocal stem), Whisper can *invent* words; this skips them |

**Hindi and Urdu are treated as one.** Spoken, they are the same language;
written, Hindi uses Devanagari and Urdu Arabic script. Both are transcribed as
Hindi, because Devanagari is what the next step can convert.

**Fitting it on the laptop** ([`_load_model`](../../backend/woodshed/audio/analysis/lyrics.py)):

- **GPU memory:** 809M weights × 4 bytes (32-bit) = 3.2 GB, too close to 4 GB.
  Kept in **16-bit (half precision)** they take 1.6 GB, at no audible cost.
  Whisper's *normalisation* layers insist on 32-bit, so they are left alone.
- **RAM:** Whisper's own loader holds the 1.6 GB file *and* a 3.2 GB model in RAM
  at once, and crashed with the browser open. The loader here
  **memory-maps** the file (weights stay on disk until touched), builds the
  model as an empty **outline** (PyTorch's "meta" device: shapes, no memory),
  attaches the weights from disk, and moves them straight to the GPU. Measured:
  almost no extra RAM, 1.6 GB of VRAM, 2.1 GB at peak.
- Loaded, used, deleted, and the GPU memory released.

A 5-minute song transcribes in about 100 seconds.

## 6.4 ② Devanagari → Roman letters

Whisper writes Hindi most accurately in Devanagari; asked for Roman letters
directly, it tends to *translate into English*. So it writes Devanagari, and
[roman.py](../../backend/woodshed/audio/analysis/roman.py) converts the result
into **casual Roman spelling**, the way lyrics are typed online ("kaise
bataaun", not the scholarly "kaise batāūṁ"). This is **transliteration**:
same words, different script, not translation.

Devanagari is a syllable script: each consonant carries a built-in "a" (क is
*ka*), changed by vowel marks (कि *ki*, की *kee*). Most of it is a table
lookup, except one rule that decides whether it sounds like Hindi:

**Schwa deletion**: spoken Hindi drops that built-in "a" in predictable
places:

```
end of a word:            दिल     di-la        → dil
between two vowels:       समझना   sa-ma-jha-na → samajhna
never stacking three
consonants:               ज़िंदगी   zin-da-gi    → zindagi   (not zindgi)
```

Plus casual conventions: long vowels doubled mid-word but not at the end
(जाना *jaana*, तेरी *teri*), में as *mein*, a nasal before p/b/m written m
(संभल *sambhal*), व after a joined consonant as w (ख़्वाब *khwaab*). Checked
against 29 common lyric words: **29 matched**. It is rules, not a model, so a
spelling may differ from the one you'd choose (the AI pass in Section 8 can
smooth that).

## 6.5 ③ Words into lines, at the singer's breaths

The plan was "a pause between words starts a new line". It never fired: on
sustained singing Whisper reports **no gaps at all**, each word running right
up to the next and swallowing the breath in between.

The breath is still in the audio, though, as a **dip in the vocal's loudness**
(not silence, because reverb fills it). So:

1. A line ends where Whisper ended a segment, or at a real pause (over 0.6 s).
2. A line still over **8 words** is split at its **deepest breath dip**,
   repeatedly, never leaving a single word alone.

```
Ye rooh bhi meri ye jism bhi mera
Utna mera nahin jitna hua tera
```

Tried and dropped: plain silence detection (the reverb meant the voice was
almost never silent), and choosing every break in the song together to fit an
ideal length (the dip signal was too noisy).

## 6.6 ④ Precise word times: the forced aligner

Whisper's word times are a by-product of how it reads, not a measurement. They
were the **main source of chords landing on the wrong word** (Section 7).

A **forced aligner** does one job: given the audio and the words known to be
in it, it finds exactly where each word is. Ours is **MMS** (Meta's Massively
Multilingual Speech, 1,100+ languages), included in torchaudio, so nothing extra
to install (weights 1.26 GB, downloaded once).

**How it works:** the model hears the audio as a stream of *letter*
probabilities every 20 ms ("this moment sounds like *a*, the next like *y*…").
Given the words in order, in plain a–z (which is why the Roman script matters),
it finds the path through those probabilities that spells them out. Each
word's span is where its letters were heard.

**Line by line:** each line is aligned only within its own window (its span
plus a second either side), so a badly misheard line cannot drag the rest of
the song with it; a line that fails keeps Whisper's times.

**Measured, not assumed:** a sung word starts with a burst of vocal energy, an
*onset*, which librosa detects in the vocal stem independently of both models.
Comparing each word's start with the nearest onset, over two songs:

| | Whisper's word starts | Aligner's word starts |
| --- | --- | --- |
| Typical distance from the real vocal onset | 0.13–0.14 s | **0.03–0.04 s** |
| Within 0.15 s of an onset (Ae Dil Hai Mushkil) | 55% | **92%** |

It takes 10–20 seconds a song. Older songs are re-timed the first time they are
opened, without re-running Whisper.

## 6.7 ⑤ When does a line really stop ringing?

After a line's last word there can be more singing the words don't cover: a
long "aaa" on the final syllable, a fade. Chords played under it belong to that
line. So from the last word's end, the vocal's loudness is followed until it
has dropped **15 dB below the line's own level** and stays there for **0.3 s**
(so a breath doesn't count), never past the next line's start. That time is
saved as the line's **`held`**. On "Besabriyaan", the last line's words end at
52.1 s and the voice carries on to 57.0 s.

An earlier version stretched the last *word* itself to that point. Once the
aligner measured real word ends, that went wrong (a chord on the dying end of
"jahaan", leading into the next line, looked mid-word), so the word keeps its
measured end and `held` is used only for chords *after* the last word.

## 6.8 Finding missing lines

Whisper sometimes drops a whole passage: its filters against invented text can
throw out a real line sung over heavy music.
[`find_gaps`](../../backend/woodshed/audio/analysis/lyrics.py) finds stretches
where the vocal is **as loud as the song's sung lines but no line covers it**.
Measured on five songs: 7–18 s of such stretches on studio recordings, 104 s on
a live TV clip (partly judges talking). These are hints for the AI pass
(Section 8), not lines in themselves.

## 6.9 What `lyrics.json` holds

```json
{
  "language": "hi", "method": "whisper-turbo", "aligned": true,
  "lines": [
    { "start": 42.36, "end": 43.76, "held": 44.04,
      "words": [ { "text": "Besabriyaan", "start": 42.36, "end": 43.76,
                   "heard": "बेसब्रियाँ", "p": 0.91 } ] }
  ]
}
```

`heard` (Whisper's own spelling) and `p` (its confidence in the word) are kept
for the AI correction pass; after a correction, `heardLines` keeps the original.

## Code map

| File | Role |
| --- | --- |
| [audio/analysis/lyrics.py](../../backend/woodshed/audio/analysis/lyrics.py) | Whisper (low-RAM loader, settings), lines and breath splits, the `Aligner` (place and fit), held ends, `find_gaps`, `lyrics.json` |
| [audio/analysis/roman.py](../../backend/woodshed/audio/analysis/roman.py) | Devanagari → casual Roman, with schwa deletion |
| [config.py](../../backend/woodshed/config.py) | `lyrics_model`, `lyrics_language` |
| [api/routes/analysis.py](../../backend/woodshed/api/routes/analysis.py) | `GET /tracks/<id>/lyrics` |
| [cli.py](../../backend/woodshed/cli.py) | `woodshed lyrics "song.mp3" [--language en]` |

## Likely interview questions

1. **"How do you get lyrics for any song?"** Whisper speech recognition on the
   separated vocal stem, then a forced aligner for precise word timing.
2. **"Why didn't you let Whisper detect the language?"** On singing it
   misdetected Hindi as English and translated; forcing the language made it
   nearly word-perfect.
3. **"How did you fit an 809M-parameter model on 4 GB?"** 16-bit weights (1.6 GB)
   and a loader that never builds the model in RAM: memory-mapped file, model
   built on PyTorch's meta device, weights attached and moved straight to the
   GPU.
4. **"Why a separate aligner when Whisper gives word times?"** Whisper's times
   are a by-product and run words together on singing. The aligner measures; it
   was about 4× closer to real vocal onsets (0.03 s vs 0.13 s), measured
   independently.
5. **"How do you write Hindi in Roman letters?"** Rule-based transliteration
   with schwa deletion (dropping the inherent "a" where speech drops it) and
   casual spelling conventions; 29 of 29 test words matched.
6. **"What are the limits?"** Misheard words on stretched or reverberant
   singing, occasional dropped passages, and line breaks that are a best guess
   from breaths.
