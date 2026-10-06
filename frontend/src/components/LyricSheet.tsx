import { useEffect, useRef } from 'react'

import type { AudioEngine } from '../audio/AudioEngine'
import { chordColour, upToTime, type ChordView } from '../lib/chords'
import type { SheetLine } from '../lib/sheet'

interface Props {
  engine: AudioEngine
  sheet: SheetLine[]
  views: ChordView[]
}

/** How long a manual scroll stops the sheet following the song. */
const HANDS_OFF_MS = 4000
/** Move to a line this early, so the eye arrives before the voice does. */
const LEAD = 0.3

/**
 * The chord sheet: lyrics with each chord written above the word it lands on.
 *
 * Read like karaoke while you play: the line being sung is lit, the lines
 * coming up stay clearly readable with their chords, and lines already sung
 * fade. Nothing smaller than a line moves - no word-by-word lighting, no
 * flashing chords - because while playing, the eye needs a place to rest, not
 * something to chase.
 *
 * Each word is a small stack - chord on top, word below - so a chord can never
 * drift away from its word, however the line wraps. The highlight is written
 * straight to the page from an animation frame; React draws the sheet once.
 */
export function LyricSheet({ engine, sheet, views }: Props) {
  const sheetRef = useRef<HTMLDivElement>(null)
  const handsOffUntil = useRef(0)

  useEffect(() => {
    const container = sheetRef.current
    if (!container || !sheet.length) return

    const lineElements = Array.from(container.children) as HTMLElement[]
    const lineStarts = sheet.map((line) => line.start)
    let shown = -2
    let frame = 0

    function tick() {
      frame = requestAnimationFrame(tick)
      const line = upToTime(lineStarts, engine.position + LEAD)
      if (line === shown) return

      lineElements.forEach((element, i) => {
        element.classList.toggle('current', i === line)
        element.classList.toggle('past', i < line)
      })
      shown = line

      const element = lineElements[line]
      if (element && Date.now() > handsOffUntil.current) {
        // A quarter of the way down: a line of context above, and the next
        // few lines - with their chords - in view below.
        container!.scrollTo({
          top: element.offsetTop - container!.clientHeight / 4,
          behavior: 'smooth',
        })
      }
    }

    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [engine, sheet, views])

  const handsOff = () => (handsOffUntil.current = Date.now() + HANDS_OFF_MS)

  return (
    <div className="sheet" ref={sheetRef} onWheel={handsOff} onTouchMove={handsOff}>
      {sheet.map((line) =>
        line.kind === 'lyric' ? (
          <p key={`l${line.start}`} className="line">
            {line.words.map((word) => (
              <span
                key={word.start}
                className="w"
                onClick={() => engine.seek(word.start)}
                title="Jump here"
              >
                <span className="c">
                  {word.chords.length
                    ? word.chords.map((index) => (
                        <ChordSymbol key={index} view={views[index]} />
                      ))
                    : word.carried !== null && (
                        <ChordSymbol view={views[word.carried]} carried />
                      )}
                </span>
                <span className="t">{word.text}</span>
              </span>
            ))}
            {line.tail.length > 0 && (
              // Chords after the last word: a chord row with no word under it.
              <span className="w tail">
                <span className="c">
                  {line.tail.map((index) => (
                    <ChordSymbol key={index} view={views[index]} />
                  ))}
                </span>
                <span className="t">{' '}</span>
              </span>
            )}
          </p>
        ) : (
          <p
            key={`i${line.start}`}
            className="line inst"
            onClick={() => engine.seek(line.start)}
            title="Jump here"
          >
            <span className="tag">{line.label}</span>
            {line.chords.map((index) => (
              <ChordSymbol key={index} view={views[index]} />
            ))}
          </p>
        ),
      )}
    </div>
  )
}

function ChordSymbol({ view, carried = false }: { view: ChordView; carried?: boolean }) {
  return (
    <span
      className={`sym${carried ? ' carried' : ''}`}
      style={{ color: chordColour(view.root) }}
    >
      {view.name}
    </span>
  )
}
