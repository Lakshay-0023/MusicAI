// Phase 4: six stems, played in sync, one volume slider each.
//
// The whole idea: load every stem fully into memory first, then start them all
// at ONE shared timestamp taken from the audio clock. Starting them one by one
// makes them drift apart by milliseconds, which sounds like a sloppy band.

import SignalsmithStretch from "./vendor/SignalsmithStretch.mjs";

const STEMS = ["Vocals", "Drums", "Bass", "Guitar", "Piano", "Other"];

const dropEl = document.getElementById("drop");
const fileEl = document.getElementById("file");
const browseBtn = document.getElementById("browse");
const jobEl = document.getElementById("job");
const jobName = document.getElementById("jobName");
const jobStatus = document.getElementById("jobStatus");
const picker = document.querySelector(".picker");
const trackSel = document.getElementById("track");
const statusEl = document.getElementById("status");
const transport = document.querySelector(".transport");
const mixerEl = document.getElementById("mixer");
const masterEl = document.querySelector(".master");
const playBtn = document.getElementById("playBtn");
const seekEl = document.getElementById("seek");
const nowEl = document.getElementById("now");
const totalEl = document.getElementById("total");
const masterVol = document.getElementById("masterVol");
const masterVal = document.getElementById("masterVal");
const speedEl = document.getElementById("speed");
const speedVal = document.getElementById("speedVal");
const pitchUp = document.getElementById("pitchUp");
const pitchDown = document.getElementById("pitchDown");
const pitchVal = document.getElementById("pitchVal");
const resetBtn = document.getElementById("resetSpeedPitch");
const waveEl = document.getElementById("wave");
const loopBar = document.getElementById("loopBar");
const loopText = document.getElementById("loopText");
const loopClear = document.getElementById("loopClear");

let ctx;                  // the audio engine
let master;               // one gain node everything flows through
const gains = {};         // one volume knob per stem, created once and kept
let buffers = {};         // decoded audio of the CURRENT song
let sources = {};         // recreated on every play - see play()

let stretch;              // pitch shifter sitting on the master bus
let duration = 0;
let playing = false;
let startedAt = 0;        // audio-clock time when playback began
let offset = 0;           // position in the song when it began
let rendering = false;

const muted = new Set();  // stems switched off, level remembered
const soloed = new Set(); // if anything is soloed, everything else is silent
let peaks = null;         // one loudness value per pixel of the waveform
let beats = null;         // { tempo, beatsPerBar, beats: [seconds] }
let loop = null;          // { start, end } in seconds, snapped to bar lines
let dragging = null;      // an in-progress selection, before it is committed

let speed = 1;            // 0.7 = 70% - applied by resampling the sources
let semitones = 0;        // what the user asked for, before speed correction

// What a stem should actually be playing at: its slider level, unless it is
// muted, or something else is soloed.
function effectiveGain(name) {
  if (muted.has(name)) return 0;
  if (soloed.size && !soloed.has(name)) return 0;
  return document.getElementById(`vol-${name}`).value / 100;
}

function applyGains() {
  if (!ctx) return;
  for (const name of STEMS) {
    // Ramping over ~15ms instead of jumping avoids an audible click.
    gains[name].gain.setTargetAtTime(effectiveGain(name), ctx.currentTime, 0.015);
  }
}

// Resampling a source changes speed and pitch together, exactly like a record
// player. Slowing to 70% drops everything by 12*log2(0.7) = 6.18 semitones, so
// the stretcher on the master bus pushes it back up by the same amount. The
// user's own transpose is simply added on top.
function applyPitch() {
  if (!stretch) return;
  stretch.schedule({ semitones: semitones - 12 * Math.log2(speed) });
}

function fmt(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

// Where we are in the song right now.
function position() {
  if (!playing) return offset;
  // At 70% speed, one second of real time covers 0.7 seconds of the song.
  let pos = offset + (ctx.currentTime - startedAt) * speed;

  // The sources loop themselves, so elapsed time keeps growing past the loop
  // end. Fold it back round to work out where in the loop we actually are.
  if (loop) {
    const span = loop.end - loop.start;
    if (span > 0 && pos > loop.end) pos = loop.start + ((pos - loop.start) % span);
  }
  return Math.min(pos, duration);
}

// Built once, on the first user click. A browser will not let audio start
// until the user interacts with the page.
async function initAudio() {
  if (ctx) return;
  ctx = new AudioContext();

  master = ctx.createGain();
  master.gain.value = masterVol.value / 100;

  // Exactly ONE stretcher, after the stems are summed. Six of them would cost
  // six times the CPU and could drift apart, undoing the sync work.
  //
  //   six sources -> six gains -> master -> stretch -> speakers
  stretch = await SignalsmithStretch(ctx);
  master.connect(stretch);
  stretch.connect(ctx.destination);
  stretch.start();
  applyPitch();

  for (const name of STEMS) {
    const gain = ctx.createGain();
    // Pick up whatever the controls are already set to, in case they were
    // touched before the first Play click created the audio engine.
    gain.gain.value = effectiveGain(name);
    gain.connect(master);
    gains[name] = gain;
  }
}

async function loadTrack(hash) {
  if (playing) stop();
  await initAudio();

  transport.hidden = mixerEl.hidden = masterEl.hidden = true;
  statusEl.hidden = false;
  statusEl.className = "";

  const loaded = {};
  let done = 0;
  await Promise.all(STEMS.map(async (name) => {
    const res = await fetch(`/stems/${hash}/${name}`);
    if (!res.ok) throw new Error(`${name} — ${res.status} ${res.statusText}`);

    // Decoding turns encoded bytes into raw samples in memory. It is
    // asynchronous because it is slow and must not freeze the page.
    loaded[name] = await ctx.decodeAudioData(await res.arrayBuffer());
    statusEl.textContent = `Loading stems… ${++done}/${STEMS.length}`;
  }));

  buffers = loaded;
  setLoop(null);
  duration = Math.max(...STEMS.map((n) => loaded[n].duration));
  offset = 0;
  totalEl.textContent = fmt(duration);
  seekEl.value = 0;

  statusEl.hidden = true;
  transport.hidden = mixerEl.hidden = masterEl.hidden = false;
  waveEl.hidden = false;

  sizeWave();
  peaks = computePeaks(Math.round(waveEl.width / (window.devicePixelRatio || 1)));

  // Not awaited: a song split before beat tracking existed gets analysed on
  // demand, which takes a few seconds. Bar lines appear when they appear.
  beats = null;
  fetch(`/tracks/${hash}/beats`)
    .then((res) => (res.ok ? res.json() : null))
    .then((data) => { beats = data; })
    .catch(() => { beats = null; });

  if (!rendering) { rendering = true; render(); }
}

function buildMixer() {
  for (const name of STEMS) {
    const row = document.createElement("div");
    row.className = "stem track";
    row.dataset.stem = name;
    row.innerHTML = `
      <label for="vol-${name}">${name}</label>
      <div class="stem-btns">
        <button type="button" class="mute" title="mute ${name}">M</button>
        <button type="button" class="solo" title="solo ${name}">S</button>
      </div>
      <input type="range" id="vol-${name}" min="0" max="100" value="100">
      <span class="val" id="val-${name}">100%</span>`;
    mixerEl.appendChild(row);

    const slider = row.querySelector("input");
    const readout = row.querySelector(".val");
    const muteBtn = row.querySelector(".mute");
    const soloBtn = row.querySelector(".solo");

    slider.addEventListener("input", () => {
      readout.textContent = `${slider.value}%`;
      applyGains();
    });

    // Mute and solo are separate from the slider on purpose: they are
    // instant, reversible, and they leave your level setting intact.
    muteBtn.addEventListener("click", () => toggle(muted, name));
    soloBtn.addEventListener("click", () => toggle(soloed, name));
  }
  refreshButtons();
}

function toggle(set, name) {
  set.has(name) ? set.delete(name) : set.add(name);
  refreshButtons();
  applyGains();
}

function refreshButtons() {
  for (const row of mixerEl.children) {
    const name = row.dataset.stem;
    row.querySelector(".mute").classList.toggle("on", muted.has(name));
    row.querySelector(".solo").classList.toggle("on", soloed.has(name));
    // Dim rather than move the slider: the level has to survive unmuting.
    row.classList.toggle("silent", effectiveGain(name) === 0);
  }
}

function play(from = position()) {
  if (from >= duration) from = 0;
  // Starting outside the loop would play until the end of it and only then
  // begin repeating, which is not what selecting a section implies.
  if (loop) from = Math.min(Math.max(from, loop.start), loop.end - 0.01);

  sources = {};
  for (const name of STEMS) {
    const src = ctx.createBufferSource();
    src.buffer = buffers[name];
    // Resampling: the same rate on all six keeps them locked together.
    src.playbackRate.value = speed;

    // Looping is done by the audio thread itself, not by JavaScript watching
    // the clock and jumping. That is what makes the wrap sample-accurate.
    if (loop) {
      src.loop = true;
      src.loopStart = loop.start;
      src.loopEnd = loop.end;
    }
    src.connect(gains[name]);
    sources[name] = src;
  }

  // The one line that matters: a single shared start time, slightly ahead of
  // now, so all six are scheduled before any of them begins. ctx.currentTime
  // is the audio clock - far more precise than the browser's normal clock.
  const startAt = ctx.currentTime + 0.1;
  for (const name of STEMS) sources[name].start(startAt, from);

  sources[STEMS[0]].onended = () => { if (playing) stopAt(duration); };

  offset = from;
  startedAt = startAt;
  playing = true;
  playBtn.textContent = "Pause";
}

function stop() {
  // A buffer source is single-use: once stopped it cannot be restarted, so
  // pausing and seeking both mean throwing these away and making new ones.
  for (const name of STEMS) {
    if (!sources[name]) continue;
    sources[name].onended = null;
    sources[name].stop();
  }
  sources = {};
  playing = false;
  playBtn.textContent = "Play";
}

function stopAt(pos) {
  stop();
  offset = pos;
}

// The song is ~10 million numbers; the canvas is a few hundred pixels wide.
// So each pixel stands for a chunk of the song, drawn at the height of the
// loudest moment inside that chunk. Stepping through the chunk rather than
// reading every sample is far faster and looks identical.
function computePeaks(width) {
  const channels = STEMS.map((n) => buffers[n].getChannelData(0));
  const length = Math.max(...channels.map((c) => c.length));
  const perPixel = Math.ceil(length / width);
  const step = Math.max(1, Math.floor(perPixel / 150));

  const out = new Float32Array(width);
  let loudest = 0.0001;

  for (let x = 0; x < width; x++) {
    const start = x * perPixel;
    const end = Math.min(length, start + perPixel);
    let peak = 0;
    for (let i = start; i < end; i += step) {
      let sum = 0;
      for (const c of channels) sum += i < c.length ? c[i] : 0;
      const value = Math.abs(sum);
      if (value > peak) peak = value;
    }
    out[x] = peak;
    if (peak > loudest) loudest = peak;
  }

  for (let x = 0; x < width; x++) out[x] /= loudest;   // scale to fit the box
  return out;
}

function drawWave() {
  if (!peaks) return;
  const dpr = window.devicePixelRatio || 1;
  const w = waveEl.width / dpr;
  const h = waveEl.height / dpr;
  const g = waveEl.getContext("2d");

  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);

  const played = duration ? (position() / duration) * w : 0;
  const style = getComputedStyle(document.documentElement);
  const behind = style.getPropertyValue("--accent").trim() || "#7c82ff";
  const ahead = style.getPropertyValue("--line").trim() || "#343b3f";

  for (let x = 0; x < peaks.length; x++) {
    const bar = Math.max(1, peaks[x] * (h - 8));
    g.fillStyle = x <= played ? behind : ahead;
    g.fillRect(x, (h - bar) / 2, 1, bar);
  }

  drawBarLines(g, w, h);

  const region = dragging || loop;
  if (region && duration) {
    const from = (Math.min(region.start, region.end) / duration) * w;
    const to = (Math.max(region.start, region.end) / duration) * w;
    g.fillStyle = dragging ? "rgba(124,130,255,.14)" : "rgba(124,130,255,.20)";
    g.fillRect(from, 0, Math.max(1, to - from), h);
    g.fillStyle = "rgba(124,130,255,.65)";
    g.fillRect(from, 0, 1, h);
    g.fillRect(to - 1, 0, 1, h);
  }
}

// The times of every bar line - what a loop snaps to.
function barTimes() {
  if (!beats || !beats.beats.length) return [];
  const perBar = beats.beatsPerBar || 4;
  const out = [];
  for (let i = 0; i < beats.beats.length; i += perBar) out.push(beats.beats[i]);
  return out;
}

// Nearest bar line, so a rough drag still produces a musical loop.
function snapToBar(time) {
  const bars = barTimes();
  if (!bars.length) return time;
  return bars.reduce((best, bar) =>
    Math.abs(bar - time) < Math.abs(best - time) ? bar : best, bars[0]);
}

function barNumberAt(time) {
  const bars = barTimes();
  if (!bars.length) return null;
  let index = 0;
  for (let i = 0; i < bars.length; i++) if (bars[i] <= time + 0.001) index = i;
  return index + 1;
}

function setLoop(next) {
  loop = next;
  if (loop) {
    const from = barNumberAt(loop.start);
    const to = barNumberAt(loop.end);
    loopText.innerHTML = from && to
      ? `Looping <strong>bars ${from}\u2013${to}</strong>`
      : `Looping <strong>${fmt(loop.start)} \u2013 ${fmt(loop.end)}</strong>`;
  }
  loopBar.hidden = !loop;

  // Rebuild the sources so they pick up the new loop points.
  if (playing) { stop(); play(loop ? loop.start : position()); }
}

// One line per bar, numbered every fourth. These are what a loop will snap to.
function drawBarLines(g, w, h) {
  if (!beats || !beats.beats.length || !duration) return;

  const perBar = beats.beatsPerBar || 4;
  g.font = "10px system-ui, sans-serif";
  g.textBaseline = "top";

  for (let i = 0; i < beats.beats.length; i += perBar) {
    const x = (beats.beats[i] / duration) * w;
    const barNumber = i / perBar + 1;
    const labelled = barNumber % 4 === 1;

    g.fillStyle = labelled ? "rgba(255,255,255,.26)" : "rgba(255,255,255,.09)";
    g.fillRect(x, 0, 1, h);

    if (labelled) {
      g.fillStyle = "rgba(255,255,255,.4)";
      g.fillText(String(barNumber), x + 3, 3);
    }
  }
}

function sizeWave() {
  const dpr = window.devicePixelRatio || 1;
  waveEl.width = Math.round(waveEl.clientWidth * dpr);
  waveEl.height = Math.round(waveEl.clientHeight * dpr);
}

function render() {
  const pos = position();
  nowEl.textContent = fmt(pos);
  if (document.activeElement !== seekEl) {
    seekEl.value = Math.round((pos / duration) * 1000);
  }
  drawWave();
  requestAnimationFrame(render);
}

playBtn.addEventListener("click", async () => {
  // First click also creates the audio engine and loads the selected song -
  // browsers refuse to start audio before a user gesture.
  if (!ctx) {
    playBtn.disabled = true;
    try {
      await loadTrack(trackSel.value);
    } catch (err) {
      fail(err);
      return;
    } finally {
      playBtn.disabled = false;
    }
    play();
    return;
  }

  if (ctx.state === "suspended") await ctx.resume();
  playing ? stopAt(position()) : play();
});

seekEl.addEventListener("input", () => {
  const target = (seekEl.value / 1000) * duration;
  nowEl.textContent = fmt(target);
  if (playing) { stop(); play(target); } else { offset = target; }
});

speedEl.addEventListener("input", () => {
  const next = speedEl.value / 100;
  speedVal.textContent = `${speedEl.value}%`;
  if (!ctx) { speed = next; return; }

  // Re-anchor before changing rate: everything already played happened at the
  // old speed, so bank that position and start measuring afresh from here.
  offset = position();
  startedAt = ctx.currentTime;
  speed = next;

  for (const name of STEMS) {
    if (sources[name]) sources[name].playbackRate.value = speed;
  }
  applyPitch();
});

function setPitch(next) {
  semitones = Math.max(-12, Math.min(12, next));
  pitchVal.textContent = semitones > 0 ? `+${semitones}` : `${semitones}`;
  pitchUp.disabled = semitones >= 12;
  pitchDown.disabled = semitones <= -12;
  applyPitch();
}

pitchUp.addEventListener("click", () => setPitch(semitones + 1));
pitchDown.addEventListener("click", () => setPitch(semitones - 1));

resetBtn.addEventListener("click", () => {
  speedEl.value = 100;
  speedEl.dispatchEvent(new Event("input"));
  setPitch(0);
});

masterVol.addEventListener("input", () => {
  masterVal.textContent = `${masterVol.value}%`;
  master.gain.setTargetAtTime(masterVol.value / 100, ctx.currentTime, 0.015);
});

trackSel.addEventListener("change", () => {
  loadTrack(trackSel.value).catch(fail);
});

function timeAt(event) {
  const box = waveEl.getBoundingClientRect();
  const fraction = (event.clientX - box.left) / box.width;
  return Math.max(0, Math.min(1, fraction)) * duration;
}

waveEl.addEventListener("pointerdown", (event) => {
  if (!duration) return;
  waveEl.setPointerCapture(event.pointerId);
  dragging = { start: timeAt(event), end: timeAt(event) };
});

waveEl.addEventListener("pointermove", (event) => {
  if (dragging) dragging.end = timeAt(event);
});

waveEl.addEventListener("pointerup", (event) => {
  if (!dragging) return;
  const from = Math.min(dragging.start, dragging.end);
  const to = Math.max(dragging.start, dragging.end);
  dragging = null;

  // A drag shorter than a second is almost certainly a click meaning "go here".
  if (to - from < 1) {
    if (playing) { stop(); play(from); } else { offset = from; }
    return;
  }

  const start = snapToBar(from);
  const end = snapToBar(to);
  setLoop(end > start ? { start, end } : null);
});

window.addEventListener("resize", () => {
  if (!peaks) return;
  sizeWave();
  peaks = computePeaks(Math.round(waveEl.width / (window.devicePixelRatio || 1)));

  // Not awaited: a song split before beat tracking existed gets analysed on
  // demand, which takes a few seconds. Bar lines appear when they appear.
  beats = null;
  fetch(`/tracks/${hash}/beats`)
    .then((res) => (res.ok ? res.json() : null))
    .then((data) => { beats = data; })
    .catch(() => { beats = null; });
});

loopClear.addEventListener("click", () => setLoop(null));

function seekBy(seconds) {
  if (!ctx || !duration) return;
  const target = Math.max(0, Math.min(duration, position() + seconds));
  if (playing) { stop(); play(target); } else { offset = target; }
  nowEl.textContent = fmt(target);
  seekEl.value = Math.round((target / duration) * 1000);
}

// You are holding an instrument. Reaching for the mouse breaks practice.
document.addEventListener("keydown", (event) => {
  // Let keys through when a control has focus, so space still works a button.
  if (["INPUT", "SELECT", "BUTTON", "TEXTAREA"].includes(event.target.tagName)) return;

  if (event.code === "Space") { event.preventDefault(); playBtn.click(); }
  if (event.code === "ArrowLeft") { event.preventDefault(); seekBy(-5); }
  if (event.code === "ArrowRight") { event.preventDefault(); seekBy(5); }
  if (event.code === "Escape" && loop) setLoop(null);

  // 1-6 mute the six stems, in the order they appear on screen.
  const slot = Number(event.key);
  if (slot >= 1 && slot <= STEMS.length) toggle(muted, STEMS[slot - 1]);
});

function fail(err) {
  statusEl.hidden = false;
  statusEl.className = "error";
  statusEl.textContent = `Could not load: ${err.message}`;
}

// ---- song list -------------------------------------------------------------

async function refreshTracks(selectHash) {
  const res = await fetch("/tracks");
  if (!res.ok) throw new Error("could not reach the server");
  const tracks = await res.json();

  trackSel.innerHTML = "";
  for (const t of tracks) {
    const opt = document.createElement("option");
    opt.value = t.hash;
    opt.textContent = t.source.replace(/\.[^.]+$/, "");
    trackSel.appendChild(opt);
  }
  picker.hidden = tracks.length === 0;

  if (selectHash) trackSel.value = selectHash;
  return tracks;
}

// ---- uploading -------------------------------------------------------------

async function upload(file) {
  jobEl.hidden = false;
  jobEl.className = "";
  jobName.textContent = file.name;
  jobStatus.textContent = "uploading…";

  const body = new FormData();
  body.append("file", file);

  const res = await fetch("/tracks", { method: "POST", body });
  if (!res.ok) { jobFailed(`upload failed (${res.status})`); return; }

  const { job_id } = await res.json();
  follow(job_id);
}

// The server pushes status down an open connection until the job settles.
// EventSource handles reconnection on its own; nothing travels back up.
function follow(jobId) {
  const events = new EventSource(`/jobs/${jobId}/events`);

  events.onmessage = async (msg) => {
    const job = JSON.parse(msg.data);

    if (job.status === "queued")      jobStatus.textContent = "queued…";
    if (job.status === "separating")  jobStatus.textContent = "separating — about 30 seconds…";

    if (job.status === "done") {
      events.close();
      jobStatus.textContent = "ready";
      await refreshTracks(job.hash);
      await loadTrack(job.hash).catch(fail);
      setTimeout(() => { jobEl.hidden = true; }, 2500);
    }

    if (job.status === "error") {
      events.close();
      jobFailed(job.error || "separation failed");
    }
  };

  events.onerror = () => { events.close(); jobFailed("lost connection to the server"); };
}

function jobFailed(message) {
  jobEl.className = "error";
  jobStatus.textContent = message;
}

browseBtn.addEventListener("click", () => fileEl.click());
fileEl.addEventListener("change", () => {
  if (fileEl.files[0]) upload(fileEl.files[0]);
  fileEl.value = "";
});

for (const evt of ["dragenter", "dragover"]) {
  dropEl.addEventListener(evt, (e) => { e.preventDefault(); dropEl.classList.add("over"); });
}
for (const evt of ["dragleave", "drop"]) {
  dropEl.addEventListener(evt, (e) => { e.preventDefault(); dropEl.classList.remove("over"); });
}
dropEl.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) upload(file);
});

// ---- start -----------------------------------------------------------------

refreshTracks()
  .then((tracks) => {
    buildMixer();
    if (tracks.length) {
      transport.hidden = false;
      mixerEl.hidden = false;
      masterEl.hidden = false;
      statusEl.hidden = true;
    } else {
      statusEl.textContent = "No songs yet — drop one above to get started.";
    }
  })
  .catch(fail);
