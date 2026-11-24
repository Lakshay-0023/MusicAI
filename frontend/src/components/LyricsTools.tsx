import { useState } from 'react'

import { api, ApiError } from '../api/client'
import type { LyricsData } from '../api/types'

interface Props {
  trackId: string
  data: LyricsData
  showHeard: boolean
  onShowHeard: (heard: boolean) => void
  onUpdated: (data: LyricsData) => void
}

type Phase =
  | { kind: 'idle' }
  | { kind: 'editing' }
  | { kind: 'working' }
  | { kind: 'mismatch'; message: string }
  | { kind: 'failed'; message: string }

/**
 * Completing and correcting the lyrics with AI - opt-in, per song, one small bar.
 *
 * Gemini hears the vocal track; pasted lyrics, if given, supply the wording.
 * It fixes misheard words and adds lines the transcription missed - and the
 * audio checks every change before it is kept. The version as heard stays
 * one click away.
 */
export function LyricsTools({ trackId, data, showHeard, onShowHeard, onUpdated }: Props) {
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })
  const [pasted, setPasted] = useState('')
  const corrected = !!data.polish

  async function run(force = false) {
    setPhase({ kind: 'working' })
    try {
      const updated = await api.polishLyrics(trackId, pasted.trim() || null, force)
      onUpdated(updated)
      onShowHeard(false)
      setPhase({ kind: 'idle' })
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setPhase({ kind: 'mismatch', message: error.message })
      } else {
        setPhase({ kind: 'failed', message: (error as Error).message })
      }
    }
  }

  async function undo() {
    setPhase({ kind: 'working' })
    try {
      onUpdated(await api.restoreLyrics(trackId))
      onShowHeard(false)
      setPhase({ kind: 'idle' })
    } catch (error) {
      setPhase({ kind: 'failed', message: (error as Error).message })
    }
  }

  return (
    <div className="lyrics-tools">
      <div className="lyrics-bar">
        {corrected ? (
          <>
            <span className="lyrics-state">
              AI-checked{data.polish!.pasted ? ' with your lyrics' : ''} ·{' '}
              {data.polish!.corrected} corrected
              {data.polish!.inserted ? ` · ${data.polish!.inserted} missing line${data.polish!.inserted === 1 ? '' : 's'} added` : ''}
            </span>
            <div className="segmented" role="group" aria-label="Which lyrics to show">
              <button type="button" className={showHeard ? '' : 'on'} onClick={() => onShowHeard(false)}>
                Corrected
              </button>
              <button type="button" className={showHeard ? 'on' : ''} onClick={() => onShowHeard(true)}>
                As heard
              </button>
            </div>
            <button type="button" className="linkish" onClick={() => setPhase({ kind: 'editing' })}>
              redo
            </button>
            <button type="button" className="linkish" onClick={() => void undo()}>
              undo
            </button>
          </>
        ) : (
          phase.kind === 'idle' && (
            <button type="button" className="toggle" onClick={() => setPhase({ kind: 'editing' })}>
              Fix lyrics with AI
            </button>
          )
        )}
      </div>

      {phase.kind === 'editing' && (
        <div className="lyrics-form">
          <textarea
            value={pasted}
            onChange={(event) => setPasted(event.target.value)}
            rows={6}
            placeholder={'Optional: paste the song’s lyrics here (Hindi or Roman letters).\n' +
              'The AI will use their wording, following what is actually sung.\n' +
              'Leave empty to just fix what was misheard.'}
          />
          <p className="hint">
            Gemini listens to the vocal track and reads the lyrics. Every change it suggests is then
            checked against the audio, and anything the audio doesn’t support is dropped.
          </p>
          <div className="lyrics-actions">
            <button type="button" className="toggle on" onClick={() => void run()}>
              {pasted.trim() ? 'Fix using my lyrics' : 'Fix lyrics'}
            </button>
            <button type="button" className="linkish" onClick={() => setPhase({ kind: 'idle' })}>
              cancel
            </button>
          </div>
        </div>
      )}

      {phase.kind === 'working' && (
        <div className="chords-wait">
          <span className="pulse" />
          Gemini is listening and checking the lyrics, then every change is verified against the
          audio… about a minute.
        </div>
      )}

      {phase.kind === 'mismatch' && (
        <div className="chords-wait failed">
          {phase.message}.{' '}
          <button type="button" className="linkish" onClick={() => void run(true)}>
            use them anyway
          </button>{' '}
          <button type="button" className="linkish" onClick={() => setPhase({ kind: 'editing' })}>
            edit
          </button>
        </div>
      )}

      {phase.kind === 'failed' && (
        <div className="chords-wait failed">
          {phase.message}{' '}
          <button type="button" className="linkish" onClick={() => setPhase({ kind: 'idle' })}>
            ok
          </button>
        </div>
      )}
    </div>
  )
}
