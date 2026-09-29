import { useCallback, useEffect, useState } from 'react'

import { api } from './api/client'
import type { BeatData, Job, Track } from './api/types'
import { STEMS } from './audio/types'
import { Dropzone } from './components/Dropzone'
import { Mixer } from './components/Mixer'
import { PracticePanel } from './components/PracticePanel'
import { Transport } from './components/Transport'
import { Waveform } from './components/Waveform'
import { useKeyboard } from './hooks/useKeyboard'
import { usePlayer } from './hooks/usePlayer'
import { songTitle } from './lib/format'

export default function App() {
  const { engine, state, load } = usePlayer()

  const [tracks, setTracks] = useState<Track[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [beats, setBeats] = useState<BeatData | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [notice, setNotice] = useState('Loading…')

  // ---- the library --------------------------------------------------------

  const refresh = useCallback(async (pick?: string) => {
    const found = await api.tracks()
    setTracks(found)
    if (pick) setSelected(pick)
    else if (found.length) setSelected((current) => current ?? found[0].id)
    return found
  }, [])

  useEffect(() => {
    refresh()
      .then((found) => setNotice(found.length ? '' : 'No songs yet — drop one above to begin.'))
      .catch((error: Error) => setNotice(`Could not reach the server: ${error.message}`))
  }, [refresh])

  // ---- loading a song -----------------------------------------------------

  useEffect(() => {
    if (!selected) return
    let cancelled = false

    setBeats(null)
    setNotice('Loading stems…')

    load(selected, (done, total) => {
      if (!cancelled) setNotice(`Loading stems… ${done}/${total}`)
    })
      .then(() => !cancelled && setNotice(''))
      .catch((error: Error) => !cancelled && setNotice(`Could not load: ${error.message}`))

    // Not awaited: a song processed before beat detection existed is analysed
    // on demand, which takes a few seconds. Bar lines appear when they appear.
    api
      .beats(selected)
      .then((data) => !cancelled && setBeats(data))
      .catch(() => undefined)

    return () => {
      cancelled = true
    }
  }, [selected, load])

  // ---- uploading ----------------------------------------------------------

  const upload = useCallback(
    async (file: File) => {
      setJob({
        id: '', source: file.name, status: 'queued', step: 'uploading',
        track_id: null, error: null, finished: false,
      })
      try {
        const jobId = await api.upload(file)
        api.watchJob(jobId, async (update) => {
          setJob(update)
          if (update.status === 'done' && update.track_id) {
            await refresh(update.track_id)
            setTimeout(() => setJob(null), 2500)
          }
        })
      } catch (error) {
        setJob({
          id: '', source: file.name, status: 'error', step: '',
          track_id: null, error: (error as Error).message, finished: true,
        })
      }
    },
    [refresh],
  )

  // ---- keyboard -----------------------------------------------------------

  useKeyboard({
    toggle: () => void engine.toggle(),
    seekBy: (seconds) => engine.seek(engine.position + seconds),
    muteSlot: (slot) => engine.toggleMute(STEMS[slot]),
    clearLoop: () => engine.setLoop(null),
  })

  // ---- render -------------------------------------------------------------

  return (
    <div className="app">
      <header className="masthead">
        <h1>Woodshed</h1>
        <span className="tagline">Take a song apart, then practise inside it.</span>
      </header>

      <Dropzone onFile={upload} />

      {job && (
        <div className={`job${job.status === 'error' ? ' failed' : ''}`}>
          <span>{songTitle(job.source)}</span>
          <span className="status">
            {job.status === 'error' ? job.error : job.finished ? 'ready' : `${job.step}…`}
          </span>
        </div>
      )}

      {tracks.length > 0 && (
        <div className="picker">
          <label htmlFor="track">Song</label>
          <select
            id="track"
            value={selected ?? ''}
            onChange={(event) => setSelected(event.target.value)}
          >
            {tracks.map((track) => (
              <option key={track.id} value={track.id}>
                {songTitle(track.source)}
              </option>
            ))}
          </select>
        </div>
      )}

      {notice && <p className="notice">{notice}</p>}

      <Waveform engine={engine} state={state} beats={beats} />
      <Transport engine={engine} state={state} beats={beats} />

      {state.loaded && (
        <div className="console">
          <Mixer engine={engine} state={state} />
          <PracticePanel engine={engine} state={state} />
        </div>
      )}

      {state.loaded && (
        <p className="shortcuts">
          <kbd>space</kbd> play · <kbd>←</kbd> <kbd>→</kbd> skip 5s ·{' '}
          <kbd>1</kbd>–<kbd>6</kbd> mute · <kbd>esc</kbd> clear loop
          <br />
          Drag across the waveform to loop a section — it snaps to bar lines.
          <br />
          0% is true silence. Levels stop at 100%, which is exactly as loud as
          the instrument was on the record.
        </p>
      )}
    </div>
  )
}
