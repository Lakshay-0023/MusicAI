import type { BeatData } from '../api/types'

/**
 * The time every bar starts, in seconds.
 *
 * Detected downbeats when the server found them. Older analyses only have
 * beats, so there the bars are assumed to start every `beatsPerBar` beats
 * counting from the first - right for most songs, off for any that open on a
 * pickup.
 */
export function barStarts(beats: BeatData | null): number[] {
  if (!beats) return []
  if (beats.downbeats?.length) return beats.downbeats

  const perBar = beats.beatsPerBar || 4
  return beats.beats.filter((_, i) => i % perBar === 0)
}
