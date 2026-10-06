import type { BeatData, Chord, LyricLine } from '../api/types'
import { chordIndexAt, upTo } from './chords'

/**
 * Lyrics and chords become one chord sheet: each chord pinned to the word
 * being sung when it starts, the way a printed sheet writes it.
 *
 * Both arrive as lists of times, so this is bookkeeping, not guesswork. It
 * runs in the browser so the server's two files stay simple and independent:
 * re-transcribing lyrics never touches the chords, or the other way round.
 */

export interface SheetWord {
  text: string
  start: number
  end: number
  /** Chords that arrive on this word, as indexes into the chord list. */
  chords: number[]
  /** On a line's first word: the chord already playing as the line starts,
   *  repeated so every line can be read on its own. */
  carried: number | null
}

export type SheetLine =
  | {
      kind: 'lyric'
      start: number
      words: SheetWord[]
      /** Chords played after the last word, before the line has really
       *  finished - written at the end of the line, as a chart would. */
      tail: number[]
    }
  | { kind: 'instrumental'; start: number; label: string; chords: number[] }

/** A chord arriving less than this before a word belongs to that word:
 *  players change a hair before the singer, and detection is ~0.1s coarse. */
const EARLY = 0.15

export function buildSheet(lines: LyricLine[], chords: Chord[], beats: BeatData | null): SheetLine[] {
  const beat = beats?.tempo ? 60 / beats.tempo : 0.5
  const bar = (beats?.beatsPerBar || 4) * beat

  const sheet = lines.map((line) => ({
    kind: 'lyric' as const,
    start: line.start,
    words: line.words.map((word): SheetWord => ({ ...word, chords: [], carried: null })),
    tail: [] as number[],
  }))
  // Every word in the song in order, knowing which line it is in.
  const words = sheet.flatMap((line) => line.words.map((word) => ({ word, line })))

  // Chords that fall in a long gap, grouped by the gap they fall in.
  const gaps = new Map<number, number[]>()

  chords.forEach((chord, index) => {
    if (chord.label === 'N') return // silence needs no symbol
    const t = chord.start
    const at = upTo(words, t, (w) => w.word.start)
    const before = words[at]
    const after = words[at + 1]
    const untilNext = after ? after.word.start - t : Infinity

    // 1. A word is being sung: it owns the chord - unless the next word starts
    //    a moment later, in which case the chord is anticipating that word.
    if (before && t < before.word.end && untilNext >= EARLY) {
      before.word.chords.push(index)
      return
    }

    // 2. Just before a word - within a beat: a lead-in. It goes on that word.
    if (after && untilNext <= beat) {
      after.word.chords.push(index)
      return
    }

    // 3. Within a bar after a line finished: the line is still ringing, so
    //    the chord belongs to it, written after its last word. (A gap in the
    //    middle of a line leads into the line's next word instead.)
    if (before && t - before.word.end <= bar) {
      const lastOfLine = before.word === before.line.words[before.line.words.length - 1]
      if (lastOfLine) before.line.tail.push(index)
      else after!.word.chords.push(index)
      return
    }

    // 4. Within a bar before the next line: the run-up into it.
    if (after && untilNext <= bar) {
      after.word.chords.push(index)
      return
    }

    // 5. Anything else is deep in a long gap: an instrumental passage of its
    //    own - intro, solo, outro - grouped by the word it follows.
    if (!gaps.has(at)) gaps.set(at, [])
    gaps.get(at)!.push(index)
  })

  // Every lyric line says which chord it opens on, even if it started earlier.
  for (const line of sheet) {
    if (!line.words.length || line.words[0].chords.length) continue
    const playing = chordIndexAt(chords, line.words[0].start + 0.02)
    if (playing >= 0 && chords[playing].label !== 'N') line.words[0].carried = playing
  }

  const result: SheetLine[] = [...sheet]
  gaps.forEach((indexes, after) => {
    const label = after < 0 ? 'Intro' : after === words.length - 1 ? 'Outro' : 'Instrumental'
    result.push({ kind: 'instrumental', start: chords[indexes[0]].start, label, chords: indexes })
  })
  return result.sort((a, b) => a.start - b.start)
}
