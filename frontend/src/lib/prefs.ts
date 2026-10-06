/**
 * Small choices worth remembering between visits - capo, simplified chords.
 *
 * Browser storage can be missing or blocked (private windows, strict
 * settings), so every read falls back to the default and every write may
 * quietly fail. Nothing here is important enough to break the app over.
 */
export function readPref<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(`woodshed.${key}`)
    return raw === null ? fallback : (JSON.parse(raw) as T)
  } catch {
    return fallback
  }
}

export function writePref(key: string, value: unknown): void {
  try {
    localStorage.setItem(`woodshed.${key}`, JSON.stringify(value))
  } catch {
    // Storage unavailable: the choice lasts until the page is closed.
  }
}
