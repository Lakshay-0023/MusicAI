import type { AudioEngine } from '../audio/AudioEngine'
import type { PlayerState } from '../audio/types'

/** Speed, pitch and output level - the controls used while playing along. */
export function PracticePanel({ engine, state }: { engine: AudioEngine; state: PlayerState }) {
  const speedPercent = Math.round(state.speed * 100)
  const semitones = state.semitones

  return (
    <section className="panel">
      <h2 className="panel-title">Practice</h2>

      <div className="control">
        <div className="row">
          <span>Speed</span>
          <span className="value">{speedPercent}%</span>
        </div>
        <input
          type="range"
          min={50}
          max={150}
          value={speedPercent}
          onChange={(event) => engine.setSpeed(Number(event.target.value) / 100)}
        />
      </div>

      <div className="control">
        <div className="row">
          <span>Pitch</span>
          <span className="value">semitones</span>
        </div>
        <div className="stepper">
          <button
            type="button"
            onClick={() => engine.setSemitones(semitones - 1)}
            disabled={semitones <= -12}
            aria-label="down one semitone"
          >
            −
          </button>
          <span className="reading">{semitones > 0 ? `+${semitones}` : semitones}</span>
          <button
            type="button"
            onClick={() => engine.setSemitones(semitones + 1)}
            disabled={semitones >= 12}
            aria-label="up one semitone"
          >
            +
          </button>
        </div>
      </div>

      <div className="control">
        <div className="row">
          <span>Master</span>
          <span className="value">{Math.round(state.masterVolume * 100)}%</span>
        </div>
        <input
          type="range"
          min={0}
          max={100}
          value={Math.round(state.masterVolume * 100)}
          onChange={(event) => engine.setMasterVolume(Number(event.target.value) / 100)}
        />
      </div>

      <button
        type="button"
        className="linkish"
        onClick={() => {
          engine.setSpeed(1)
          engine.setSemitones(0)
        }}
      >
        reset speed &amp; pitch
      </button>
    </section>
  )
}
