import type { Chord, ChordData } from '../api/types'
import { present, type Display } from './chords'

/**
 * How many chord changes to show: "all" | "normal" | "minimal".
 *
 * The server decodes the chords three times, with a rising cost on changing
 * chord (see chords.py), so a one-beat blip only survives at "all". This
 * picks a level; it does not do the smoothing itself.
 */
export type ChordDetail = 'all' | 'normal' | 'minimal'

/** The chords at the chosen level, with repeats merged as displayed. */
export function chordsAt(data: ChordData, detail: ChordDetail, display: Display): Chord[] {
  return mergeAsShown(data.levels?.[detail] ?? data.chords, display)
}

/**
 * Consecutive chords that are written the same become one.
 *
 * The server only merges identical chords. Once the player's choices are
 * applied, different ones can look the same - with Simple on, G -> G7 -> G
 * is "G G G" - and should read as a single G.
 */
function mergeAsShown(chords: Chord[], display: Display): Chord[] {
  const out: (Chord & { shown: string })[] = []
  for (const chord of chords) {
    const shown = present(chord.label, display).name
    const last = out[out.length - 1]
    if (last && last.shown === shown) last.end = chord.end
    else out.push({ ...chord, shown })
  }
  return out.map(({ shown: _shown, ...chord }) => chord)
}
