/** The six sources the separation model produces, in a fixed order. */
export const STEMS = ['Vocals', 'Drums', 'Bass', 'Guitar', 'Piano', 'Other'] as const

export type StemName = (typeof STEMS)[number]

/** A section of the song set to repeat, in seconds. */
export interface Loop {
  start: number
  end: number
}

/** What the engine reports about itself. Position is deliberately absent:
 *  it changes continuously and is read directly, not pushed into React. */
export interface PlayerState {
  loaded: boolean
  playing: boolean
  duration: number
  levels: Record<StemName, number>
  muted: StemName[]
  soloed: StemName[]
  speed: number
  semitones: number
  masterVolume: number
  loop: Loop | null
}
