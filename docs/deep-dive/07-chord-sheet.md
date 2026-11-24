# Section 7: The chord sheet: combining chords and lyrics

[← Section 6, Lyrics](06-lyrics.md) · [Index](README.md) · Next: [Section 8, AI lyric correction →](08-ai-lyrics.md)

How two independent lists of times, chords and words, become a chord sheet
with each chord above the right word, scrolling with the song like simple
karaoke.

---

## 7.1 The idea

After analysis there are two files, both just lists of times:

```
chords.json                 lyrics.json
12.48  Em                   12.40-12.71  kaise
14.95  C                    12.71-13.30  bataaun
17.40  G                    13.30-13.62  main
                            13.62-14.20  tumhein
                            ··· pause ···
                            15.10-15.38  mere
```

Combining them is **bookkeeping, not guesswork**: for each chord, find the word
being sung when it starts. It runs in the browser
([lib/sheet.ts `buildSheet`](../../frontend/src/lib/sheet.ts)), which keeps the
two server files independent (re-transcribing lyrics never touches the chords)
and lets display choices apply instantly.

**It can only be as right as the times it is given.** Most misplaced chords
were really timing errors, which is why the forced aligner (Section 6) was the
fix.

## 7.2 The placement rules

For each chord (`t` = when it starts), the first rule that fits wins:

| # | Where the chord falls | Where it goes | Why |
| --- | --- | --- | --- |
| 1 | **During a word** | That word | The chord sounds while that syllable is sung |
| 1′ | …but the next word starts within 0.15 s, **or** the chord hits the **last quarter** of the word with the next word **within a beat** | The **next** word | It is *anticipating* the next word, as players do (a D on the dying end of "jahaan", just before "Besabriyaan", belongs to "Besabriyaan") |
| 2 | **Within one beat before** a word | That word | A lead-in |
| 3 | **Under the line's held note or fade, or within a bar after it** | The **end of that line**, after the last word | The line is still ringing |
| 4 | **Within a bar before** the next line | The next line's first word | The run-up into it |
| 5 | **Deeper into a long gap** | Its own **Intro / Instrumental / Outro** line | A passage with no singing |

Also:
- **"No chord" (N)** gets no symbol.
- **Every line states the chord it opens on**, dimmed, if that chord started
  earlier, so any line can be read on its own, which you need after jumping into
  the middle of a song.
- "A beat" allows 0.15 s extra for detection's coarseness; beat and bar lengths
  come from `beats.json`.

**The rules evolved from real mistakes:**
- The first version sent *every* chord in a pause of up to two bars to the
  *next* word, assuming a chord in a pause is a lead-in. Usually it's the
  opposite: it still belongs to the line just sung. Combined with Whisper's
  early word ends, the G under a held "Besabriyaan" jumped down a line.
- Fixed by rule 3 plus the measured `held` times, and later by the aligner's
  precise word ends and rule 1′. Now the song's repeating **D A G** lines up with
  each "Besabriyaan":

```
           Bm   A               G
Kyon suchna hai jaana kaha                ← G under the held "kahaa…"
             Bm  A G
Jaaye vahi  le  jaaye jahaan              ← A G under the held "jaaye…"
D A G                       D
Besabriyaan
D                           A G Bm A
Besabriya                                 ← chords under the long final fade
[Instrumental]  G  Bm  A  Em  F#m  G  D
```

## 7.3 Drawing it so chords cannot drift

Each word is a tiny two-row stack, chord on top and word underneath
([LyricSheet.tsx](../../frontend/src/components/LyricSheet.tsx)):

```
┌─────┐┌───────┐┌────┐┌───────┐
│ G   ││       ││    ││       │
│Kaise││bataaun││main││tumhein│
└─────┘└───────┘└────┘└───────┘
```

- Chord and word share one box (CSS `inline-flex`, column), so however a line
  wraps on a narrow screen, the chord stays over its word.
- A chord name wider than its word ("Cmaj7" over "main") widens the box instead
  of overlapping the next word.
- Chords after the last word ("tail" chords, rule 3) are a chord row with no
  word under it.
- Section headings ("CHORUS", "VERSE") and dimmed "talk" lines appear once an AI
  correction has labelled them (Section 8).

## 7.4 Following the song: simple karaoke

| What | How | Why |
| --- | --- | --- |
| **Current line** | A soft band with an accent bar; chosen **0.3 s early** | Your eyes arrive before the voice does |
| **Lines ahead** | Clearly readable, with their chords | You see the next change coming |
| **Lines already sung** | Faded | Less to look at |
| **Scrolling** | The current line glides to a quarter of the way down; if you scroll yourself, it waits **4 s** before taking over again | Context above, the next few lines below; a page that fights you is the worst UX |
| **Click any word** | Jumps the song there | Drill a tricky line |

**Performance:** the sheet is drawn by React once. An animation loop (about 60
times a second) does a binary search over line start times and changes CSS
classes **only when the current line changes**. Position never goes through
React (the same rule as Section 3).

## 7.5 Designs that were tried and dropped

Each was built, used, and removed because it got in the way while playing an
instrument:

| Dropped | Why |
| --- | --- |
| **A beat-by-beat chart** (four bars a row, a tick lighting per beat) | Accurate but too detailed: a session musician's view; reading beats was more work than playing them |
| **A big "Now / Next" chord display** with a beat countdown | A second thing to watch; the sheet already shows the next line and its chords |
| **Word-by-word lighting** and a flashing current chord | Something to chase rather than read; the eye needs somewhere still to rest |

The principle that came out of it: **the calmest view by default; detail only
as an opt-in switch**.

## 7.6 The controls around the sheet

[ChordPanel.tsx](../../frontend/src/components/ChordPanel.tsx) header:
**Chords: All · Normal · Minimal** (Section 5), **Simple**, **Capo**, **Focus**
(or the **F** key: hides upload, picker, mixer and practice panel and enlarges
the sheet). Choices are remembered between visits in browser storage
([lib/prefs.ts](../../frontend/src/lib/prefs.ts), wrapped so blocked storage
never breaks the page).

**Songs with no singing** get a simpler bar-by-bar chord list instead of the
sheet.

**Loading order:** the browser asks for **beats, then chords, then lyrics**,
each after the last has answered ([App.tsx](../../frontend/src/App.tsx)). For a
song never analysed, each request triggers analysis on the server; chained, each
model runs once and alone on the 4 GB GPU.

## Code map

| File | Role |
| --- | --- |
| [lib/sheet.ts](../../frontend/src/lib/sheet.ts) | `buildSheet`: the placement rules, tails, instrumental lines, carried chords |
| [components/LyricSheet.tsx](../../frontend/src/components/LyricSheet.tsx) | Renders the sheet; follows the song; click to seek |
| [components/ChordPanel.tsx](../../frontend/src/components/ChordPanel.tsx) | The panel: controls, sheet or bar list, loading states |
| [components/ChordLane.tsx](../../frontend/src/components/ChordLane.tsx) | The chord strip under the waveform |
| [lib/chords.ts](../../frontend/src/lib/chords.ts), [lib/tidy.ts](../../frontend/src/lib/tidy.ts) | Chord names, colours, levels |
| [App.tsx](../../frontend/src/App.tsx) | Loads beats → chords → lyrics; holds the display choices |

## Honest limitations

- **Verse endings:** when a verse ends and an instrumental begins, rule 3's
  extra bar can pull the instrumental's first chords onto the verse's last line.
  A proposed fix (at a section break, keep only chords that start while the
  voice is still sounding, with no extra bar) has not been built yet.
- **Sections are inferred from gaps**, not detected: nothing in the system
  truly knows what a verse is. A music-structure model (e.g. All-In-One) would
  label intro, verse and chorus from the audio.
- **Thresholds** (one beat, one bar, 0.15 s, last quarter) were chosen on a
  handful of songs.

## Likely interview questions

1. **"How do you put chords above the right words?"** Both are timed lists; each
   chord goes on the word being sung when it starts, with rules for
   anticipation, lead-ins, held notes and instrumental gaps, all scaled to the
   song's own beat and bar length.
2. **"What caused chords to land on the wrong word, and how did you fix it?"**
   Mostly Whisper's rough word times. I added a forced aligner, measured as about
   4× closer to real vocal onsets, plus loudness-based detection of held notes.
3. **"How do you keep chords aligned when lines wrap?"** Each word and its chord
   share one flex box, so they wrap together.
4. **"How does the auto-scroll avoid fighting the user?"** It pauses for 4 s
   after any manual scroll, and moves only when the current line changes.
5. **"What did user feedback change?"** Three richer views were removed in
   favour of a calm, line-level karaoke sheet; detail became opt-in.
