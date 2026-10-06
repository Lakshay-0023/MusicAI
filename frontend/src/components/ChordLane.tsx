import { useEffect, useMemo, useRef } from 'react'

import type { AudioEngine } from '../audio/AudioEngine'
import type { PlayerState } from '../audio/types'
import type { Chord } from '../api/types'
import { chordColour, chordIndexAt, present, type Display } from '../lib/chords'

interface Props {
  engine: AudioEngine
  state: PlayerState
  chords: Chord[] | null
  display: Display
}

/**
 * The whole song's chords as one strip, lined up with the waveform above it.
 *
 * It is the map rather than the music stand: a glance shows where the chorus
 * comes back (same colours again) and a click jumps there. Like the waveform,
 * it never re-renders as the song plays - its own animation frame moves the
 * playhead and lights the current block.
 */
export function ChordLane({ engine, state, chords, display }: Props) {
  const laneRef = useRef<HTMLDivElement>(null)
  const headRef = useRef<HTMLDivElement>(null)

  const blocks = useMemo(
    () => (chords ?? []).map((chord) => ({ chord, view: present(chord.label, display) })),
    [chords, display],
  )

  useEffect(() => {
    if (!chords?.length || !state.duration) return
    let frame = 0
    let lit = -1

    function tick() {
      frame = requestAnimationFrame(tick)
      const position = engine.position
      if (headRef.current) headRef.current.style.left = `${(position / state.duration) * 100}%`

      const now = chordIndexAt(chords!, position)
      if (now !== lit && laneRef.current) {
        laneRef.current.children[lit]?.classList.remove('now')
        laneRef.current.children[now]?.classList.add('now')
        lit = now
      }
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [engine, chords, state.duration, blocks])

  if (!state.loaded || !chords?.length || !state.duration) return null

  return (
    <div className="chord-lane" aria-label="Chords across the song">
      <div className="blocks" ref={laneRef}>
        {blocks.map(({ chord, view }) => (
          <button
            key={chord.start}
            type="button"
            className="block"
            title={`${view.name} — ${chord.start.toFixed(1)}s`}
            style={{
              left: `${(chord.start / state.duration) * 100}%`,
              width: `${((chord.end - chord.start) / state.duration) * 100}%`,
              background: chordColour(view.root, 0.22),
              borderTopColor: chordColour(view.root),
            }}
            onClick={() => engine.seek(chord.start)}
          >
            {view.name}
          </button>
        ))}
      </div>
      <div className="playhead" ref={headRef} />
    </div>
  )
}
