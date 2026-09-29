export function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds)) return '0:00'
  const minutes = Math.floor(seconds / 60)
  const rest = Math.floor(seconds % 60)
  return `${minutes}:${String(rest).padStart(2, '0')}`
}

/** Drop the file extension, so "Besabriyaan.mp3" reads as "Besabriyaan". */
export function songTitle(filename: string): string {
  return filename.replace(/\.[^.]+$/, '')
}
