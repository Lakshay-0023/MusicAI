import { useCallback, useEffect, useRef, useState } from 'react'

import { AudioEngine } from '../audio/AudioEngine'
import type { PlayerState } from '../audio/types'

/**
 * One engine for the lifetime of the app, and its state mirrored into React.
 *
 * Only discrete changes go through React - playing, levels, loop points.
 * Position is not among them: it moves continuously, and re-rendering to
 * advance a playhead would be wasteful. Components that need it read
 * engine.position inside their own animation frame.
 */
export function usePlayer() {
  const engineRef = useRef<AudioEngine | null>(null)
  if (engineRef.current === null) engineRef.current = new AudioEngine()
  const engine = engineRef.current

  const [state, setState] = useState<PlayerState>(engine.state)

  useEffect(() => engine.subscribe(setState), [engine])

  const load = useCallback(
    (trackId: string, onProgress?: (done: number, total: number) => void) =>
      engine.load(trackId, onProgress),
    [engine],
  )

  return { engine, state, load }
}
