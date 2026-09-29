import { STEMS, type Loop, type PlayerState, type StemName } from './types'

/**
 * Everything that makes sound. Deliberately free of React.
 *
 * React re-renders constantly; an audio graph is long-lived and
 * timing-sensitive. Rebuilding it on render would destroy the sample-accurate
 * sync between stems. So React owns the screen, this class owns the sound, and
 * a hook passes messages between them.
 */

/** The pitch shifter, as much of it as this code uses. */
interface StretchNode extends AudioNode {
  start(): void
  schedule(change: { semitones?: number; rate?: number }): void
}

type Listener = (state: PlayerState) => void

const RAMP = 0.015 // seconds; long enough to avoid a click, short enough to feel instant
const LEAD_IN = 0.1 // seconds of headroom to schedule all six before any begins

export class AudioEngine {
  private ctx: AudioContext | null = null
  private master: GainNode | null = null
  private stretch: StretchNode | null = null

  private gains = {} as Record<StemName, GainNode>
  private buffers = {} as Record<StemName, AudioBuffer>
  private sources: Partial<Record<StemName, AudioBufferSourceNode>> = {}

  private levels = Object.fromEntries(STEMS.map((s) => [s, 1])) as Record<StemName, number>
  private muted = new Set<StemName>()
  private soloed = new Set<StemName>()

  private listeners = new Set<Listener>()

  private _loaded = false
  private _playing = false
  private _duration = 0
  private startedAt = 0 // audio-clock time when playback began
  private offset = 0 // position in the song at that moment
  private _speed = 1
  private _semitones = 0
  private _masterVolume = 1
  private _loop: Loop | null = null

  // ---------------------------------------------------------------- state --

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  get state(): PlayerState {
    return {
      loaded: this._loaded,
      playing: this._playing,
      duration: this._duration,
      levels: { ...this.levels },
      muted: [...this.muted],
      soloed: [...this.soloed],
      speed: this._speed,
      semitones: this._semitones,
      masterVolume: this._masterVolume,
      loop: this._loop,
    }
  }

  private emit(): void {
    const snapshot = this.state
    this.listeners.forEach((listener) => listener(snapshot))
  }

  /**
   * Where we are in the song, right now.
   *
   * Read directly rather than pushed through React: it changes continuously,
   * and re-rendering sixty times a second to move a playhead would be absurd.
   */
  get position(): number {
    if (!this._playing || !this.ctx) return this.offset

    // At 70% speed, a second of real time covers 0.7 seconds of the song.
    let pos = this.offset + (this.ctx.currentTime - this.startedAt) * this._speed

    // The sources loop themselves, so elapsed time keeps growing past the loop
    // end. Fold it back to find where inside the loop we actually are.
    if (this._loop) {
      const span = this._loop.end - this._loop.start
      if (span > 0 && pos > this._loop.end) {
        pos = this._loop.start + ((pos - this._loop.start) % span)
      }
    }
    return Math.min(pos, this._duration)
  }

  // --------------------------------------------------------------- loading --

  /** Built on first use: browsers refuse to start audio before a user gesture. */
  private async init(): Promise<void> {
    if (this.ctx) return

    this.ctx = new AudioContext()
    this.master = this.ctx.createGain()
    this.master.gain.value = this._masterVolume

    // Exactly one stretcher, after the stems are summed. Six would cost six
    // times the CPU and could drift apart, undoing the sync work.
    // Loaded at runtime from public/, not bundled: it is a prebuilt module
    // that carries its own compiled WebAssembly. The path is held in a
    // variable so TypeScript treats it as a runtime value rather than trying
    // to resolve a file that only exists once the server is running.
    const modulePath = '/vendor/SignalsmithStretch.mjs'
    const { default: createStretch } = await import(/* @vite-ignore */ modulePath)
    this.stretch = (await createStretch(this.ctx)) as StretchNode

    this.master.connect(this.stretch)
    this.stretch.connect(this.ctx.destination)
    this.stretch.start()
    this.applyPitch()

    for (const stem of STEMS) {
      const gain = this.ctx.createGain()
      gain.gain.value = this.gainFor(stem)
      gain.connect(this.master)
      this.gains[stem] = gain
    }
  }

  async load(trackId: string, onProgress?: (done: number, total: number) => void): Promise<void> {
    if (this._playing) this.stopSources()
    await this.init()
    const ctx = this.ctx!

    let done = 0
    const loaded = {} as Record<StemName, AudioBuffer>

    // All six are fetched and decoded before anything starts. That is not
    // incidental - starting while files are still arriving would let the
    // quick ones begin early, which is exactly the drift being avoided.
    await Promise.all(
      STEMS.map(async (stem) => {
        const response = await fetch(`/stems/${trackId}/${stem}`)
        if (!response.ok) throw new Error(`${stem}: ${response.status} ${response.statusText}`)
        loaded[stem] = await ctx.decodeAudioData(await response.arrayBuffer())
        onProgress?.(++done, STEMS.length)
      }),
    )

    this.buffers = loaded
    this._duration = Math.max(...STEMS.map((stem) => loaded[stem].duration))
    this.offset = 0
    this._loop = null
    this._loaded = true
    this.emit()
  }

  // ------------------------------------------------------------- transport --

  play(from: number = this.position): void {
    if (!this.ctx || !this._loaded) return
    if (this._playing) this.stopSources()

    if (from >= this._duration) from = 0
    // Starting outside the loop would play to its end before repeating, which
    // is not what selecting a section implies.
    if (this._loop) {
      from = Math.min(Math.max(from, this._loop.start), this._loop.end - 0.01)
    }

    for (const stem of STEMS) {
      const source = this.ctx.createBufferSource()
      source.buffer = this.buffers[stem]
      // The same rate on all six keeps them locked together.
      source.playbackRate.value = this._speed

      if (this._loop) {
        // The audio thread handles the wrap itself. Watching the clock in
        // JavaScript and jumping would land late whenever the page is busy -
        // audible every time round, and fatal for practising.
        source.loop = true
        source.loopStart = this._loop.start
        source.loopEnd = this._loop.end
      }

      source.connect(this.gains[stem])
      this.sources[stem] = source
    }

    // One shared start time, slightly ahead, computed ONCE before the loop.
    // Reading the clock inside it would give each stem a different value.
    const startAt = this.ctx.currentTime + LEAD_IN
    for (const stem of STEMS) this.sources[stem]!.start(startAt, from)

    this.sources[STEMS[0]]!.onended = () => {
      if (this._playing) this.pause(this._duration)
    }

    this.offset = from
    this.startedAt = startAt
    this._playing = true
    this.emit()
  }

  pause(at: number = this.position): void {
    this.stopSources()
    this.offset = at
    this.emit()
  }

  async toggle(): Promise<void> {
    if (this.ctx?.state === 'suspended') await this.ctx.resume()
    this._playing ? this.pause() : this.play()
  }

  seek(seconds: number): void {
    const target = Math.max(0, Math.min(this._duration, seconds))
    if (this._playing) this.play(target)
    else {
      this.offset = target
      this.emit()
    }
  }

  /** A source is single-use: once stopped it can never restart, so pausing and
   *  seeking both mean discarding these and building new ones. The decoded
   *  audio is untouched, which is why both feel instant. */
  private stopSources(): void {
    for (const stem of STEMS) {
      const source = this.sources[stem]
      if (!source) continue
      source.onended = null
      source.stop()
    }
    this.sources = {}
    this._playing = false
  }

  // ---------------------------------------------------------------- mixing --

  /** What a stem should actually play at: its level, unless it is muted or
   *  something else is soloed. */
  private gainFor(stem: StemName): number {
    if (this.muted.has(stem)) return 0
    if (this.soloed.size && !this.soloed.has(stem)) return 0
    return this.levels[stem]
  }

  private applyGains(): void {
    if (!this.ctx) return
    for (const stem of STEMS) {
      this.gains[stem].gain.setTargetAtTime(this.gainFor(stem), this.ctx.currentTime, RAMP)
    }
  }

  setLevel(stem: StemName, level: number): void {
    this.levels[stem] = level
    this.applyGains()
    this.emit()
  }

  toggleMute(stem: StemName): void {
    this.muted.has(stem) ? this.muted.delete(stem) : this.muted.add(stem)
    this.applyGains()
    this.emit()
  }

  toggleSolo(stem: StemName): void {
    this.soloed.has(stem) ? this.soloed.delete(stem) : this.soloed.add(stem)
    this.applyGains()
    this.emit()
  }

  /** Whether a stem is currently silent, for whatever reason. */
  isSilent(stem: StemName): boolean {
    return this.gainFor(stem) === 0
  }

  setMasterVolume(value: number): void {
    this._masterVolume = value
    this.master?.gain.setTargetAtTime(value, this.ctx!.currentTime, RAMP)
    this.emit()
  }

  // ------------------------------------------------------- speed and pitch --

  /**
   * Resampling changes speed and pitch together, exactly like a record player.
   * Slowing to 70% drops everything by 12*log2(0.7) = 6.18 semitones, so the
   * stretcher pushes it back up by the same amount. The listener's own
   * transpose is simply added on top.
   */
  private applyPitch(): void {
    this.stretch?.schedule({ semitones: this._semitones - 12 * Math.log2(this._speed) })
  }

  setSpeed(speed: number): void {
    if (this.ctx && this._playing) {
      // Everything played so far happened at the old speed: bank that position
      // and start measuring afresh, or the playhead corrupts.
      this.offset = this.position
      this.startedAt = this.ctx.currentTime
    }
    this._speed = speed

    for (const stem of STEMS) {
      const source = this.sources[stem]
      if (source) source.playbackRate.value = speed
    }
    this.applyPitch()
    this.emit()
  }

  setSemitones(semitones: number): void {
    this._semitones = Math.max(-12, Math.min(12, semitones))
    this.applyPitch()
    this.emit()
  }

  // ---------------------------------------------------------------- looping --

  setLoop(loop: Loop | null): void {
    this._loop = loop
    // Rebuild the sources so they pick up the new loop points.
    if (this._playing) this.play(loop ? loop.start : this.position)
    else this.emit()
  }

  // --------------------------------------------------------------- drawing --

  /**
   * One loudness value per pixel, for the waveform.
   *
   * The song is millions of numbers and the canvas a few hundred pixels wide,
   * so each pixel stands for a chunk, drawn at the height of the loudest
   * moment inside it. Stepping through a chunk rather than reading every
   * sample is far quicker and looks identical.
   */
  peaks(width: number): Float32Array {
    const out = new Float32Array(Math.max(0, width))
    if (!this._loaded || width <= 0) return out

    const channels = STEMS.map((stem) => this.buffers[stem].getChannelData(0))
    const length = Math.max(...channels.map((channel) => channel.length))
    const perPixel = Math.ceil(length / width)
    const step = Math.max(1, Math.floor(perPixel / 150))

    let loudest = 0.0001
    for (let x = 0; x < width; x++) {
      const start = x * perPixel
      const end = Math.min(length, start + perPixel)
      let peak = 0
      for (let i = start; i < end; i += step) {
        let sum = 0
        for (const channel of channels) sum += i < channel.length ? channel[i] : 0
        const value = Math.abs(sum)
        if (value > peak) peak = value
      }
      out[x] = peak
      if (peak > loudest) loudest = peak
    }

    for (let x = 0; x < width; x++) out[x] /= loudest
    return out
  }
}
