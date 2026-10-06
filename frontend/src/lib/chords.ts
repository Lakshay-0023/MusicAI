import type { BeatData, Chord } from '../api/types'
import { barStarts } from './bars'

/**
 * Everything the screen needs to know about a chord beyond its label.
 *
 * The server sends research notation ("E:min7"). Turning that into what a
 * player reads happens here, in the browser, because it depends on choices the
 * player makes while practising - pitch shift, capo, simplified chords - and
 * none of those should cost a trip to the server.
 */

// Flats where charts conventionally use them (Bb, Eb, Ab), sharps elsewhere.
// Key detection will later choose spelling per song; this is the safe default.
const NAMES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']

const PITCH: Record<string, number> = {
  C: 0, 'C#': 1, D: 2, 'D#': 3, E: 4, F: 5, 'F#': 6, G: 7, 'G#': 8, A: 9, 'A#': 10, B: 11,
}

/** Every quality BTC can name: how a chart writes it, which notes it holds
 *  (semitones above the root), and what it becomes when simplified. */
const QUALITIES: Record<string, { suffix: string; intervals: number[]; simple: string }> = {
  maj: { suffix: '', intervals: [0, 4, 7], simple: 'maj' },
  min: { suffix: 'm', intervals: [0, 3, 7], simple: 'min' },
  dim: { suffix: 'dim', intervals: [0, 3, 6], simple: 'dim' },
  aug: { suffix: 'aug', intervals: [0, 4, 8], simple: 'aug' },
  min6: { suffix: 'm6', intervals: [0, 3, 7, 9], simple: 'min' },
  maj6: { suffix: '6', intervals: [0, 4, 7, 9], simple: 'maj' },
  min7: { suffix: 'm7', intervals: [0, 3, 7, 10], simple: 'min' },
  minmaj7: { suffix: 'm(maj7)', intervals: [0, 3, 7, 11], simple: 'min' },
  maj7: { suffix: 'maj7', intervals: [0, 4, 7, 11], simple: 'maj' },
  '7': { suffix: '7', intervals: [0, 4, 7, 10], simple: 'maj' },
  dim7: { suffix: 'dim7', intervals: [0, 3, 6, 9], simple: 'dim' },
  hdim7: { suffix: 'm7b5', intervals: [0, 3, 6, 10], simple: 'dim' },
  sus2: { suffix: 'sus2', intervals: [0, 2, 7], simple: 'maj' },
  sus4: { suffix: 'sus4', intervals: [0, 5, 7], simple: 'maj' },
}

/** The player's choices that change how a chord is written. */
export interface Display {
  /** Pitch shift from the practice panel: chords follow what you hear. */
  semitones: number
  /** Capo fret: chords become the shapes you finger, not what sounds. */
  capo: number
  /** Drop 7ths, 6ths and sus: Cmaj7 -> C, Asus4 -> A. */
  simplify: boolean
}

export interface ChordView {
  name: string
  /** 0-11, or null for no chord. Drives the colour. */
  root: number | null
  notes: string[]
}

export function present(label: string, display: Display): ChordView {
  if (label === 'N') return { name: 'N.C.', root: null, notes: [] }
  if (label === 'X') return { name: '?', root: null, notes: [] }

  const [rootName, written = 'maj'] = label.split(':')
  const quality = QUALITIES[display.simplify ? QUALITIES[written].simple : written]

  // + 120 keeps the sum positive, so % 12 cannot return a negative number.
  const root = (PITCH[rootName] + display.semitones - display.capo + 120) % 12
  return {
    name: NAMES[root] + quality.suffix,
    root,
    notes: quality.intervals.map((step) => NAMES[(root + step) % 12]),
  }
}

/**
 * A colour per root, walking the circle of fifths.
 *
 * C, G, D, A... are each a fifth apart, and chords a fifth apart are the ones
 * that sit together in a key. Giving neighbours on the circle neighbouring
 * hues means a song's usual chords share a family of colours, and a repeated
 * section is visible before it is heard.
 */
export function chordColour(root: number | null, alpha = 1): string {
  if (root === null) return `hsla(200, 6%, 45%, ${alpha * 0.5})`
  const hue = ((root * 7) % 12) * 30
  return `hsla(${hue}, 55%, 64%, ${alpha})`
}

/**
 * In a list sorted by time, the index of the last item at or before `time`;
 * -1 if there is none. A binary search: halve the range until one is left,
 * so even a song's thousand beats take about ten steps, every frame.
 */
export function upTo<T>(items: T[], time: number, timeOf: (item: T) => number): number {
  let lo = 0
  let hi = items.length - 1
  let found = -1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (timeOf(items[mid]) <= time) {
      found = mid
      lo = mid + 1
    } else {
      hi = mid - 1
    }
  }
  return found
}

export const upToTime = (times: number[], time: number) => upTo(times, time, (t) => t)

/** Index of the chord playing at `time`. -1 before the first. */
export const chordIndexAt = (chords: Chord[], time: number) => upTo(chords, time, (c) => c.start)

export interface BeatCell {
  time: number
  chord: number
  /** True on the beat a chord arrives; false while it carries on. */
  arrives: boolean
}

export interface Bar {
  number: number
  start: number
  end: number
  beats: BeatCell[]
}

/**
 * The song as a chord chart: bars, each split into its beats, each beat
 * knowing its chord. This is the shape a musician reads, so the screen draws
 * it directly.
 */
export function buildBars(beats: BeatData, chords: Chord[]): Bar[] {
  const starts = barStarts(beats)
  const songEnd = chords.length ? chords[chords.length - 1].end : 0
  const bars: Bar[] = []
  let previous = -1
  let b = 0

  starts.forEach((start, i) => {
    const end = starts[i + 1] ?? songEnd
    if (start >= songEnd) return

    const times: number[] = []
    while (b < beats.beats.length && beats.beats[b] < start - 0.01) b++
    while (b < beats.beats.length && beats.beats[b] < end - 0.01) times.push(beats.beats[b++])
    if (!times.length) times.push(start)

    const cells = times.map((time) => {
      // A hair past the beat, so a chord that starts exactly on it counts.
      const chord = chordIndexAt(chords, time + 0.02)
      const cell = { time, chord, arrives: chord !== previous }
      previous = chord
      return cell
    })
    bars.push({ number: i + 1, start, end, beats: cells })
  })
  return bars
}
