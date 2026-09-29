import { useRef, useState } from 'react'

/** Where a song comes in. Accepts video too - phone recordings of a band
 *  arrive as .mov, and the server strips the audio before separating. */
export function Dropzone({ onFile }: { onFile: (file: File) => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)

  return (
    <div
      className={`dropzone${over ? ' over' : ''}`}
      onDragEnter={(event) => {
        event.preventDefault()
        setOver(true)
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        event.preventDefault()
        setOver(false)
        const file = event.dataTransfer.files[0]
        if (file) onFile(file)
      }}
    >
      <strong>Drop a song here</strong>
      <span>
        or{' '}
        <button type="button" className="linkish" onClick={() => inputRef.current?.click()}>
          choose a file
        </button>{' '}
        — audio or video
      </span>
      <input
        ref={inputRef}
        type="file"
        accept="audio/*,video/*"
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) onFile(file)
          event.target.value = ''
        }}
      />
    </div>
  )
}
