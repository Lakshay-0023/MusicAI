import { useEffect, useRef, useState } from 'react'

import type { AudioEngine } from '../audio/AudioEngine'
import type { Loop, PlayerState } from '../audio/types'
import type { BeatData } from '../api/types'

interface Props {
  engine: AudioEngine
  state: PlayerState
  beats: BeatData | null
}

/**
 * The song, drawn — and the surface you select a loop on.
 *
 * This component deliberately does not re-render as playback advances. It runs
 * its own animation frame, reads engine.position directly, and repaints the
 * canvas. Pushing a moving playhead through React sixty times a second would
 * be pure waste.
 */
export function Waveform({ engine, state, beats }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const peaksRef = useRef<Float32Array | null>(null)
  const [dragging, setDragging] = useState<Loop | null>(null)

  // Peaks are expensive to work out, so only when the song or the width changes.
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !state.loaded) return

    function measure() {
      const ratio = window.devicePixelRatio || 1
      canvas!.width = Math.round(canvas!.clientWidth * ratio)
      canvas!.height = Math.round(canvas!.clientHeight * ratio)
      peaksRef.current = engine.peaks(Math.round(canvas!.width / ratio))
    }

    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [engine, state.loaded, state.duration])

  // The drawing loop. Runs for as long as the component is mounted.
  useEffect(() => {
    let frame = 0

    function draw() {
      frame = requestAnimationFrame(draw)
      const canvas = canvasRef.current
      const peaks = peaksRef.current
      if (!canvas || !peaks) return

      const ratio = window.devicePixelRatio || 1
      const width = canvas.width / ratio
      const height = canvas.height / ratio
      const context = canvas.getContext('2d')
      if (!context) return

      context.setTransform(ratio, 0, 0, ratio, 0, 0)
      context.clearRect(0, 0, width, height)

      const played = state.duration ? (engine.position / state.duration) * width : 0
      const styles = getComputedStyle(document.documentElement)
      const behind = styles.getPropertyValue('--accent').trim() || '#7c82ff'
      const ahead = styles.getPropertyValue('--line').trim() || '#2e3639'

      for (let x = 0; x < peaks.length; x++) {
        const bar = Math.max(1, peaks[x] * (height - 10))
        context.fillStyle = x <= played ? behind : ahead
        context.fillRect(x, (height - bar) / 2, 1, bar)
      }

      drawBarLines(context, width, height)
      drawRegion(context, width, height)
    }

    function drawBarLines(context: CanvasRenderingContext2D, width: number, height: number) {
      if (!beats?.beats.length || !state.duration) return
      const perBar = beats.beatsPerBar || 4

      context.font = '10px system-ui, sans-serif'
      context.textBaseline = 'top'

      for (let i = 0; i < beats.beats.length; i += perBar) {
        const x = (beats.beats[i] / state.duration) * width
        const barNumber = i / perBar + 1
        const labelled = barNumber % 4 === 1

        context.fillStyle = labelled ? 'rgba(255,255,255,.24)' : 'rgba(255,255,255,.08)'
        context.fillRect(x, 0, 1, height)

        if (labelled) {
          context.fillStyle = 'rgba(255,255,255,.38)'
          context.fillText(String(barNumber), x + 3, 3)
        }
      }
    }

    function drawRegion(context: CanvasRenderingContext2D, width: number, height: number) {
      const region = dragging ?? state.loop
      if (!region || !state.duration) return

      const from = (Math.min(region.start, region.end) / state.duration) * width
      const to = (Math.max(region.start, region.end) / state.duration) * width

      context.fillStyle = dragging ? 'rgba(124,130,255,.14)' : 'rgba(124,130,255,.20)'
      context.fillRect(from, 0, Math.max(1, to - from), height)
      context.fillStyle = 'rgba(124,130,255,.65)'
      context.fillRect(from, 0, 1, height)
      context.fillRect(to - 1, 0, 1, height)
    }

    frame = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(frame)
  }, [engine, state.duration, state.loop, beats, dragging])

  // ---- selecting ----------------------------------------------------------

  function timeAt(event: React.PointerEvent<HTMLCanvasElement>): number {
    const box = event.currentTarget.getBoundingClientRect()
    const fraction = (event.clientX - box.left) / box.width
    return Math.max(0, Math.min(1, fraction)) * state.duration
  }

  /** The nearest bar line, so a rough drag still makes a musical loop. */
  function snapToBar(time: number): number {
    if (!beats?.beats.length) return time
    const perBar = beats.beatsPerBar || 4
    let best = beats.beats[0]
    for (let i = 0; i < beats.beats.length; i += perBar) {
      if (Math.abs(beats.beats[i] - time) < Math.abs(best - time)) best = beats.beats[i]
    }
    return best
  }

  return (
    <canvas
      ref={canvasRef}
      className="waveform"
      hidden={!state.loaded}
      onPointerDown={(event) => {
        if (!state.duration) return
        event.currentTarget.setPointerCapture(event.pointerId)
        const at = timeAt(event)
        setDragging({ start: at, end: at })
      }}
      onPointerMove={(event) => {
        if (dragging) setDragging({ ...dragging, end: timeAt(event) })
      }}
      onPointerUp={() => {
        if (!dragging) return
        const from = Math.min(dragging.start, dragging.end)
        const to = Math.max(dragging.start, dragging.end)
        setDragging(null)

        // A drag under a second is almost certainly a click meaning "go here".
        if (to - from < 1) {
          engine.seek(from)
          return
        }

        const start = snapToBar(from)
        const end = snapToBar(to)
        engine.setLoop(end > start ? { start, end } : null)
      }}
    />
  )
}
