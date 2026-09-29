import type { AudioEngine } from '../audio/AudioEngine'
import { STEMS, type PlayerState } from '../audio/types'

/**
 * One row per stem: mute, solo, level.
 *
 * Mute and solo are separate from the slider deliberately. Watching what
 * practice involves: muting an instrument to play its part is constant,
 * soloing one to learn it is frequent, setting something to 37% almost never
 * happens. A slider alone makes the rare action easy and the constant one
 * fiddly - solo would mean dragging five sliders to zero and back.
 */
export function Mixer({ engine, state }: { engine: AudioEngine; state: PlayerState }) {
  const anySolo = state.soloed.length > 0

  return (
    <section className="panel">
      <h2 className="panel-title">Mixer</h2>

      {STEMS.map((stem) => {
        const muted = state.muted.includes(stem)
        const soloed = state.soloed.includes(stem)
        const silent = muted || (anySolo && !soloed)
        const level = Math.round(state.levels[stem] * 100)

        return (
          <div className={`stem${silent ? ' silent' : ''}`} data-stem={stem} key={stem}>
            <label htmlFor={`level-${stem}`}>{stem}</label>

            <div className="toggles">
              <button
                type="button"
                className={`mute${muted ? ' on' : ''}`}
                title={`Mute ${stem}`}
                onClick={() => engine.toggleMute(stem)}
              >
                M
              </button>
              <button
                type="button"
                className={`solo${soloed ? ' on' : ''}`}
                title={`Solo ${stem}`}
                onClick={() => engine.toggleSolo(stem)}
              >
                S
              </button>
            </div>

            {/* The slider never moves when muting: that level has to survive
                unmuting, so the row dims instead. */}
            <input
              type="range"
              id={`level-${stem}`}
              min={0}
              max={100}
              value={level}
              onChange={(event) => engine.setLevel(stem, Number(event.target.value) / 100)}
            />

            <span className="value">{level}%</span>
          </div>
        )
      })}
    </section>
  )
}
