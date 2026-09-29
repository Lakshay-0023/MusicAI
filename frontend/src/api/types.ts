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
