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

let speed = 1;            // 0.7 = 70% - applied by resampling the sources
let semitones = 0;        // what the user asked for, before speed correction

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
  return Math.min(offset + (ctx.currentTime - startedAt) * speed, duration);
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
    // Pick up whatever the sliders are already set to, in case they were
    // moved before the first Play click created the audio engine.
    gain.gain.value = document.getElementById(`vol-${name}`).value / 100;
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
  duration = Math.max(...STEMS.map((n) => loaded[n].duration));
  offset = 0;
  totalEl.textContent = fmt(duration);
  seekEl.value = 0;

  statusEl.hidden = true;
  transport.hidden = mixerEl.hidden = masterEl.hidden = false;

  if (!rendering) { rendering = true; render(); }
}

function buildMixer() {
  for (const name of STEMS) {
    const row = document.createElement("div");
    row.className = "stem";
    row.dataset.stem = name;
    row.innerHTML = `
      <label for="vol-${name}">${name}</label>
      <input type="range" id="vol-${name}" min="0" max="100" value="100">
      <span class="val" id="val-${name}">100%</span>`;
    mixerEl.appendChild(row);

    const slider = row.querySelector("input");
    const readout = row.querySelector(".val");

    slider.addEventListener("input", () => {
      readout.textContent = `${slider.value}%`;
      if (!ctx) return;   // before the first Play click; initAudio() reads it then
      // Jumping the value instantly causes an audible click. Ramping over
      // ~15ms is inaudible as a delay but removes the click entirely.
      gains[name].gain.setTargetAtTime(slider.value / 100, ctx.currentTime, 0.015);
    });
  }
}

function play(from = position()) {
  if (from >= duration) from = 0;

  sources = {};
  for (const name of STEMS) {
    const src = ctx.createBufferSource();
    src.buffer = buffers[name];
    // Resampling: the same rate on all six keeps them locked together.
    src.playbackRate.value = speed;
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

function render() {
  const pos = position();
  nowEl.textContent = fmt(pos);
  if (document.activeElement !== seekEl) {
    seekEl.value = Math.round((pos / duration) * 1000);
  }
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
