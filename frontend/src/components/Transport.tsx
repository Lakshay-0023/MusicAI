import { useEffect, useRef } from 'react'

import type { AudioEngine } from '../audio/AudioEngine'
import type { PlayerState } from '../audio/types'
import type { BeatData } from '../api/types'
import { barStarts } from '../lib/bars'
import { formatTime } from '../lib/format'

interface Props {
  engine: AudioEngine
  state: PlayerState
  beats: BeatData | null
}

export function Transport({ engine, state, beats }: Props) {
  const timeRef = useRef<HTMLSpanElement>(null)
  const seekRef = useRef<HTMLInputElement>(null)
  const scrubbing = useRef(false)

  // The clock and the seek bar move continuously, so they are written to
  // directly rather than driven through React state.
  useEffect(() => {
    let frame = 0
    function tick() {
      frame = requestAnimationFrame(tick)
      const position = engine.position
      if (timeRef.current) timeRef.current.textContent = formatTime(position)
      if (seekRef.current && !scrubbing.current && state.duration) {
        seekRef.current.value = String(Math.round((position / state.duration) * 1000))
      }
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [engine, state.duration])

  const loopLabel = state.loop ? describeLoop(state.loop.start, state.loop.end, beats) : null

  return (
    <div className="transport" hidden={!state.loaded}>
      <button className="play" onClick={() => void engine.toggle()}>
        {state.playing ? 'Pause' : 'Play'}
      </button>

      <input
        ref={seekRef}
        className="seek"
        type="range"
        min={0}
        max={1000}
        defaultValue={0}
        onPointerDown={() => (scrubbing.current = true)}
        onPointerUp={() => (scrubbing.current = false)}
        onChange={(event) => engine.seek((Number(event.target.value) / 1000) * state.duration)}
      />

      <span className="time">
        <span ref={timeRef}>0:00</span> / {formatTime(state.duration)}
      </span>

      {state.loop && (
        <span className="loop-chip">
          <strong>{loopLabel}</strong>
          <button className="linkish" onClick={() => engine.setLoop(null)}>
            clear
          </button>
        </span>
      )}
    </div>
  )
}

/** "bars 13–17" where beats are known, otherwise a plain time range. */
function describeLoop(start: number, end: number, beats: BeatData | null): string {
  const bars = barStarts(beats)
  if (!bars.length) return `${formatTime(start)} – ${formatTime(end)}`

  const barAt = (time: number) => {
    let index = 0
    for (let i = 0; i < bars.length; i++) {
      if (bars[i] <= time + 0.001) index = i
    }
    return index + 1
  }
  return `bars ${barAt(start)}–${barAt(end)}`
}
