import { useCallback, useEffect, useMemo, useState } from 'react'

import { api } from './api/client'
import type { BeatData, ChordData, Job, LyricLine, Track } from './api/types'
import { STEMS } from './audio/types'
import { ChordLane } from './components/ChordLane'
import { ChordPanel, type LoadStatus } from './components/ChordPanel'
import { Dropzone } from './components/Dropzone'
import { Mixer } from './components/Mixer'
import { PracticePanel } from './components/PracticePanel'
import { Transport } from './components/Transport'
import { Waveform } from './components/Waveform'
import { useKeyboard } from './hooks/useKeyboard'
import { usePlayer } from './hooks/usePlayer'
import type { Display } from './lib/chords'
import { songTitle } from './lib/format'
import { readPref, writePref } from './lib/prefs'
import { chordsAt, type ChordDetail } from './lib/tidy'

export default function App() {
  const { engine, state, load } = usePlayer()

  const [tracks, setTracks] = useState<Track[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [beats, setBeats] = useState<BeatData | null>(null)
  const [chords, setChords] = useState<ChordData | null>(null)
  const [chordStatus, setChordStatus] = useState<LoadStatus>('idle')
  const [lyrics, setLyrics] = useState<LyricLine[] | null>(null)
  const [lyricsStatus, setLyricsStatus] = useState<LoadStatus>('idle')
  const [job, setJob] = useState<Job | null>(null)
  const [notice, setNotice] = useState('Loading…')

  // ---- how chords are shown -----------------------------------------------

  const [capo, setCapo] = useState(() => readPref('capo', 0))
  const [simplify, setSimplify] = useState(() => readPref('simplify', false))
  const [detail, setDetail] = useState<ChordDetail>(() => readPref('chordDetail', 'normal'))
  const [focus, setFocus] = useState(false)

  useEffect(() => writePref('capo', capo), [capo])
  useEffect(() => writePref('simplify', simplify), [simplify])
  useEffect(() => writePref('chordDetail', detail), [detail])

  // Pitch comes from the engine, so chord names follow what is actually heard.
  const display = useMemo<Display>(
    () => ({ semitones: state.semitones, capo, simplify }),
    [state.semitones, capo, simplify],
  )

  // The chords every view shows, tidied as much as the player chose. Worked
  // out once here so the lane and the sheet can never disagree.
  const shownChords = useMemo(
    () => (chords ? chordsAt(chords, detail, display) : null),
    [chords, display, detail],
  )

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
    setChords(null)
    setChordStatus('loading')
    setLyrics(null)
    setLyricsStatus('loading')
    setNotice('Loading stems…')

    load(selected, (done, total) => {
      if (!cancelled) setNotice(`Loading stems… ${done}/${total}`)
    })
      .then(() => !cancelled && setNotice(''))
      .catch((error: Error) => !cancelled && setNotice(`Could not load: ${error.message}`))

    // Not awaited: a song processed before these analyses existed is analysed
    // on demand - seconds for beats and chords, about a minute for lyrics -
    // and each part of the screen appears as its answer arrives.
    //
    // One after another, never at once: chords need the beats, and each step
    // runs a model on a 4GB GPU. Asked together, the server would work out
    // the beats twice and could have three models loaded side by side.
    async function analyse(id: string) {
      try {
        const found = await api.beats(id)
        if (!cancelled) setBeats(found)
      } catch {
        // No bar lines; everything else still works.
      }
      if (cancelled) return

      try {
        const found = await api.chords(id)
        if (cancelled) return
        setChords(found)
        setChordStatus('ready')
      } catch {
        if (!cancelled) setChordStatus('error')
      }
      if (cancelled) return

      try {
        const found = await api.lyrics(id)
        if (cancelled) return
        setLyrics(found.lines)
        setLyricsStatus('ready')
      } catch {
        if (!cancelled) setLyricsStatus('error')
      }
    }
    void analyse(selected)

    return () => {
      cancelled = true
    }
  }, [selected, load])

  const retryChords = useCallback(() => {
    if (!selected) return
    setChordStatus('loading')
    api
      .chords(selected)
      .then((data) => {
        setChords(data)
        setChordStatus('ready')
      })
      .catch(() => setChordStatus('error'))
  }, [selected])

  const retryLyrics = useCallback(() => {
    if (!selected) return
    setLyricsStatus('loading')
    api
      .lyrics(selected)
      .then((data) => {
        setLyrics(data.lines)
        setLyricsStatus('ready')
      })
      .catch(() => setLyricsStatus('error'))
  }, [selected])

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
    toggleFocus: () => setFocus((on) => !on),
  })

  // ---- render -------------------------------------------------------------

  // Focus mode keeps only what you read while playing: the song's shape, the
  // transport and the chords. Everything for setting up is a keypress away.
  const setup = !focus

  return (
    <div className={`app${focus ? ' focus' : ''}`}>
      <header className="masthead">
        <h1>Woodshed</h1>
        <span className="tagline">
          {focus && selected
            ? songTitle(tracks.find((track) => track.id === selected)?.source ?? '')
            : 'Take a song apart, then practise inside it.'}
        </span>
      </header>

      {setup && <Dropzone onFile={upload} compact={tracks.length > 0} />}

      {setup && job && (
        <div className={`job${job.status === 'error' ? ' failed' : ''}`}>
          <span>{songTitle(job.source)}</span>
          <span className="status">
            {job.status === 'error' ? job.error : job.finished ? 'ready' : `${job.step}…`}
          </span>
        </div>
      )}

      {setup && tracks.length > 0 && (
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

      <div className="timeline">
        <Waveform engine={engine} state={state} beats={beats} />
        <ChordLane engine={engine} state={state} chords={shownChords} display={display} />
      </div>
      <Transport engine={engine} state={state} beats={beats} />

      <ChordPanel
        engine={engine}
        state={state}
        beats={beats}
        chords={shownChords}
        chordStatus={chordStatus}
        onRetryChords={retryChords}
        lyrics={lyrics}
        lyricsStatus={lyricsStatus}
        onRetryLyrics={retryLyrics}
        display={display}
        onCapo={setCapo}
        onSimplify={setSimplify}
        detail={detail}
        onDetail={setDetail}
        focus={focus}
        onFocus={() => setFocus((on) => !on)}
      />

      {setup && state.loaded && (
        <div className="console">
          <Mixer engine={engine} state={state} />
          <PracticePanel engine={engine} state={state} />
        </div>
      )}

      {setup && state.loaded && (
        <p className="shortcuts">
          <kbd>space</kbd> play · <kbd>←</kbd> <kbd>→</kbd> skip 5s ·{' '}
          <kbd>1</kbd>–<kbd>6</kbd> mute · <kbd>esc</kbd> clear loop · <kbd>f</kbd> focus
          <br />
          Drag across the waveform to loop a section — it snaps to bar lines.
          Click any word in the lyrics to jump to it.
          <br />
          0% is true silence. Levels stop at 100%, which is exactly as loud as
          the instrument was on the record.
        </p>
      )}
    </div>
  )
}
