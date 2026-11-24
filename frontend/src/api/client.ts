import type { BeatData, ChordData, Job, LyricsData, Track } from './types'

/**
 * Everything the browser knows how to ask the server.
 *
 * Paths are relative: in development Vite proxies them to the Python app, and
 * in production that same app serves these files, so nothing changes.
 */

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (!response.ok) throw new Error(`${path}: ${response.status} ${response.statusText}`)
  return response.json() as Promise<T>
}

/** A refusal from the server that carries a reason worth showing. */
export class ApiError extends Error {
  status: number
  detail: Record<string, unknown>

  constructor(status: number, detail: Record<string, unknown>) {
    super(String(detail.message ?? `request failed (${status})`))
    this.status = status
    this.detail = detail
  }
}

async function post<T>(path: string, body: unknown = {}): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { detail?: unknown }
    const detail = typeof payload.detail === 'object' && payload.detail
      ? (payload.detail as Record<string, unknown>)
      : { message: String(payload.detail ?? response.statusText) }
    throw new ApiError(response.status, detail)
  }
  return response.json() as Promise<T>
}

export const api = {
  tracks: () => get<Track[]>('/tracks'),

  track: (id: string) => get<Track>(`/tracks/${id}`),

  beats: (id: string) => get<BeatData>(`/tracks/${id}/beats`),

  chords: (id: string) => get<ChordData>(`/tracks/${id}/chords`),

  lyrics: (id: string) => get<LyricsData>(`/tracks/${id}/lyrics`),

  /**
   * Correct the lyrics with AI, optionally following lyrics the player pasted.
   * Sends lyrics text only. A 409 means the pasted lyrics look like another
   * song; `force` sends them anyway.
   */
  polishLyrics: (id: string, lyrics: string | null, force = false) =>
    post<LyricsData>(`/tracks/${id}/lyrics/polish`, { lyrics, force }),

  /** Undo an AI correction: back to exactly what was heard. */
  restoreLyrics: (id: string) => post<LyricsData>(`/tracks/${id}/lyrics/restore`),

  /**
   * Hand the server a song and get a ticket back, immediately.
   *
   * Separation takes far longer than a request may last, so the work happens
   * afterwards and progress is followed separately.
   */
  async upload(file: File): Promise<string> {
    const body = new FormData()
    body.append('file', file)

    const response = await fetch('/tracks', { method: 'POST', body })
    if (!response.ok) throw new Error(`Upload failed (${response.status})`)

    const { job_id } = (await response.json()) as { job_id: string }
    return job_id
  },

  /**
   * Follow a ticket until the work settles.
   *
   * Server-sent events rather than a websocket: nothing needs to travel back
   * up, and EventSource reconnects by itself if the connection drops.
   */
  watchJob(jobId: string, onUpdate: (job: Job) => void): () => void {
    const events = new EventSource(`/jobs/${jobId}/events`)

    events.onmessage = (message) => {
      const job = JSON.parse(message.data) as Job
      onUpdate(job)
      if (job.finished) events.close()
    }

    events.onerror = () => {
      events.close()
      onUpdate({
        id: jobId, source: '', status: 'error', step: '',
        track_id: null, error: 'lost connection to the server', finished: true,
      })
    }

    return () => events.close()
  },
}
