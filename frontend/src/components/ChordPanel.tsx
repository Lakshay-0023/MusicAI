import { useEffect, useMemo, useRef } from 'react'

import type { AudioEngine } from '../audio/AudioEngine'
import type { PlayerState } from '../audio/types'
import type { BeatData, Chord, LyricLine } from '../api/types'
import {
  buildBars, chordColour, present, upToTime, type ChordView, type Display,
} from '../lib/chords'
import { buildSheet } from '../lib/sheet'
import type { ChordDetail } from '../lib/tidy'
import { LyricSheet } from './LyricSheet'

export type LoadStatus = 'idle' | 'loading' | 'ready' | 'error'

interface Props {
  engine: AudioEngine
  state: PlayerState
  beats: BeatData | null
  chords: Chord[] | null
  chordStatus: LoadStatus
  onRetryChords: () => void
  lyrics: LyricLine[] | null
  lyricsStatus: LoadStatus
  onRetryLyrics: () => void
  display: Display
  onCapo: (capo: number) => void
  onSimplify: (simplify: boolean) => void
  /** How much the chords have been tidied (see lib/tidy.ts). */
  detail: ChordDetail
  onDetail: (detail: ChordDetail) => void
  focus: boolean
  onFocus: () => void
}

/**
 * The music stand: the song's lyrics with chords written in, the way a chord
 * sheet is printed, scrolling with the song like simple karaoke. A song with
 * no singing gets its chords bar by bar instead.
 *
 * The chords arrive already tidied or not - the panel just shows what it gets.
 */
export function ChordPanel(props: Props) {
  const { engine, state, beats, chords, chordStatus, lyrics, lyricsStatus, display } = props

  const views = useMemo(
    () => (chords ?? []).map((chord) => present(chord.label, display)),
    [chords, display],
  )
  const sheet = useMemo(
    () => (lyrics?.length && chords?.length ? buildSheet(lyrics, chords, beats) : []),
    [lyrics, chords, beats],
  )

  if (!state.loaded) return null

  const ready = chordStatus === 'ready' && !!chords?.length

  return (
    <section className="panel chords" aria-label="Chords and lyrics">
      <header className="chords-head">
        <h2 className="panel-title">Chords</h2>
        <Options {...props} />
      </header>

      {chordStatus === 'loading' && (
        <Waiting>Listening for chords… the first time takes a few seconds.</Waiting>
      )}
      {chordStatus === 'error' && (
        <Failed onRetry={props.onRetryChords}>Could not work out the chords.</Failed>
      )}
      {chordStatus === 'ready' && !chords?.length && (
        <div className="chords-wait">No chords found in this song.</div>
      )}

      {ready && (
        <>
          {sheet.length > 0 ? (
            <LyricSheet engine={engine} sheet={sheet} views={views} />
          ) : (
            <>
              {lyricsStatus === 'loading' && (
                <Waiting>
                  Writing down the lyrics from the vocals… about a minute the first time.
                </Waiting>
              )}
              {lyricsStatus === 'error' && (
                <Failed onRetry={props.onRetryLyrics}>Could not transcribe the lyrics.</Failed>
              )}
              {lyricsStatus === 'ready' && (
                <div className="chords-wait">No singing found — chords bar by bar instead.</div>
              )}
              {lyricsStatus !== 'loading' && (
                <BarList engine={engine} beats={beats} chords={chords!} views={views} />
              )}
            </>
          )}
        </>
      )}
    </section>
  )
}

// ---- the header controls ------------------------------------------------------

const DETAILS: [ChordDetail, string, string][] = [
  ['all', 'All', 'Every chord the model heard, beat by beat, even ones lasting a moment'],
  ['normal', 'Normal', 'A chord change has to be clearly heard - passing blips are gone'],
  ['minimal', 'Minimal', 'Only strong, lasting changes - the backbone of the song'],
]

function Options({ state, display, onSimplify, onCapo, detail, onDetail, focus, onFocus }: Props) {
  return (
    <div className="chord-options">
      {state.semitones !== 0 && (
        <span className="chip" title="Chord names follow the pitch control">
          pitch {state.semitones > 0 ? `+${state.semitones}` : state.semitones}
        </span>
      )}
      <div className="segmented" role="group" aria-label="How many chord changes to show">
        <span className="stepper-label">Chords</span>
        {DETAILS.map(([value, label, hint]) => (
          <button
            key={value}
            type="button"
            className={detail === value ? 'on' : ''}
            aria-pressed={detail === value}
            title={hint}
            onClick={() => onDetail(value)}
          >
            {label}
          </button>
        ))}
      </div>
      <button
        type="button"
        className={`toggle${display.simplify ? ' on' : ''}`}
        aria-pressed={display.simplify}
        title="Drop 7ths and sus chords: Cmaj7 becomes C"
        onClick={() => onSimplify(!display.simplify)}
      >
        Simple
      </button>
      <div className="stepper small" title="Show the shapes to play with a capo">
        <span className="stepper-label">Capo</span>
        <button
          type="button"
          aria-label="capo down"
          disabled={display.capo <= 0}
          onClick={() => onCapo(display.capo - 1)}
        >
          −
        </button>
        <span className="reading">{display.capo || '–'}</span>
        <button
          type="button"
          aria-label="capo up"
          disabled={display.capo >= 9}
          onClick={() => onCapo(display.capo + 1)}
        >
          +
        </button>
      </div>
      <button
        type="button"
        className={`toggle${focus ? ' on' : ''}`}
        aria-pressed={focus}
        title="Hide everything but the chords and lyrics (F)"
        onClick={onFocus}
      >
        Focus
      </button>
    </div>
  )
}

// ---- bar by bar, for songs without singing -------------------------------------

interface ViewProps {
  engine: AudioEngine
  beats: BeatData | null
  chords: Chord[]
  views: ChordView[]
}

/** Chords bar by bar, four bars a row - just the names, no beat detail. */
function BarList({ engine, beats, chords, views }: ViewProps) {
  const listRef = useRef<HTMLDivElement>(null)
  const bars = useMemo(() => (beats ? buildBars(beats, chords) : []), [beats, chords])

  useEffect(() => {
    const list = listRef.current
    if (!list || !bars.length) return
    const starts = bars.map((bar) => bar.start)
    let lit = -1
    let rowTop = -1
    let frame = 0

    function tick() {
      frame = requestAnimationFrame(tick)
      const bar = upToTime(starts, engine.position)
      if (bar === lit) return
      list!.children[lit]?.classList.remove('current')
      const element = list!.children[bar] as HTMLElement | undefined
      element?.classList.add('current')
      lit = bar
      if (element && element.offsetTop !== rowTop) {
        rowTop = element.offsetTop
        list!.scrollTo({ top: rowTop - element.offsetHeight - 8, behavior: 'smooth' })
      }
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [engine, bars])

  if (!bars.length) return null

  return (
    <div className="bar-list" ref={listRef}>
      {bars.map((bar) => {
        // The chords that arrive in this bar; a bar that only continues the
        // last chord repeats it, dimmed, so every bar can be read on its own.
        const arriving = bar.beats.filter((cell, j) => cell.chord >= 0 && (cell.arrives || j === 0))
        return (
          <div key={bar.start} className="bar" onClick={() => engine.seek(bar.start)} title="Jump here">
            <span className="bar-no">{bar.number}</span>
            <span className="names">
              {arriving.map((cell) => (
                <span
                  key={cell.time}
                  className={cell.arrives ? '' : 'carried'}
                  style={{ color: chordColour(views[cell.chord].root) }}
                >
                  {views[cell.chord].name}
                </span>
              ))}
            </span>
          </div>
        )
      })}
    </div>
  )
}

// ---- small pieces ----------------------------------------------------------------

function Waiting({ children }: { children: React.ReactNode }) {
  return (
    <div className="chords-wait">
      <span className="pulse" />
      {children}
    </div>
  )
}

function Failed({ children, onRetry }: { children: React.ReactNode; onRetry: () => void }) {
  return (
    <div className="chords-wait failed">
      {children}{' '}
      <button type="button" className="linkish" onClick={onRetry}>
        try again
      </button>
    </div>
  )
}
