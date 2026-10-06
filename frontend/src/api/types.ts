export interface Track {
  id: string
  source: string
  model: string
  stems: string[]
}

export interface BeatData {
  tempo: number
  beatsPerBar: number
  beats: number[]
  /** Where each bar starts. Missing from analyses made before it existed. */
  downbeats?: number[]
  /** 'beat_this' (the neural model) or 'librosa' (the fallback rule). */
  method?: string
}

export interface Chord {
  start: number
  end: number
  /** Research notation: "E:min7", "C", "N" for no chord. */
  label: string
  /** As a chart writes it: "Em7". */
  name: string
}

export interface ChordData {
  /** The "normal" level. */
  chords: Chord[]
  /** The same song at three levels of detail, decoded on the server. */
  levels?: Record<'all' | 'normal' | 'minimal', Chord[]>
  /** Which stems the model listened to. */
  stems: string[]
  method: string
}

export interface LyricWord {
  text: string
  start: number
  end: number
}

export interface LyricLine {
  start: number
  end: number
  words: LyricWord[]
}

export interface LyricsData {
  /** Language Whisper heard, e.g. "hi" (shown romanised) or "en". */
  language: string
  lines: LyricLine[]
  method: string
}

export interface Job {
  id: string
  source: string
  status: 'queued' | 'running' | 'done' | 'error'
  step: string
  track_id: string | null
  error: string | null
  finished: boolean
}
