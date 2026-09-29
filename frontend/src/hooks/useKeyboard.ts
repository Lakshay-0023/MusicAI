import { useEffect, useRef } from 'react'

interface Handlers {
  toggle: () => void
  seekBy: (seconds: number) => void
  muteSlot: (slot: number) => void
  clearLoop: () => void
}

/**
 * Keyboard control for the player.
 *
 * Not a nicety: you are holding an instrument. Reaching for the mouse breaks
 * practice in a way a keystroke does not.
 *
 * The handlers are kept in a ref so the listener is attached once, rather than
 * being torn down and rebuilt on every render.
 */
export function useKeyboard(handlers: Handlers): void {
  const ref = useRef(handlers)
  ref.current = handlers

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      // Let keys through when a control has focus, so space still works a button.
      const tag = (event.target as HTMLElement).tagName
      if (['INPUT', 'SELECT', 'BUTTON', 'TEXTAREA'].includes(tag)) return

      if (event.code === 'Space') {
        event.preventDefault()
        ref.current.toggle()
      } else if (event.code === 'ArrowLeft') {
        event.preventDefault()
        ref.current.seekBy(-5)
      } else if (event.code === 'ArrowRight') {
        event.preventDefault()
        ref.current.seekBy(5)
      } else if (event.code === 'Escape') {
        ref.current.clearLoop()
      } else {
        const slot = Number(event.key)
        if (slot >= 1 && slot <= 6) ref.current.muteSlot(slot - 1)
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])
}
