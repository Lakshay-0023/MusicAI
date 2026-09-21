"""
Phase 2: what audio actually IS.

The whole point of this script: audio is not a mysterious blob. It's a long
list of numbers. Once you've seen that with your own eyes, the rest of this
project (volume sliders, muting, mixing) stops looking like magic - it's
arithmetic on arrays.

Run:  .venv\\Scripts\\python.exe explore_audio.py
"""

import glob
import numpy as np
import soundfile as sf

SONG = "Ae Dil Hai Mushkil Title Track Full Video - Ranbir, Anushka, Aishwarya  Arijit Singh Pritam.mp3"

# Rather than hardcoding those very long filenames, find them by pattern.
# Each stem file is named like: <song>_(Drums)_htdemucs_6s.wav
STEM_NAMES = ["Vocals", "Drums", "Bass", "Guitar", "Piano", "Other"]

stems = {}
sample_rate = None

print("=" * 70)
print("PART 1 - loading the stems and looking at what's inside them")
print("=" * 70)

for name in STEM_NAMES:
    matches = glob.glob(f"stems/*({name})*.wav")
    if not matches:
        print(f"  !! no file found for {name}")
        continue

    audio, sr = sf.read(matches[0])
    stems[name] = audio
    sample_rate = sr

    # audio.shape is the single most important line in this script.
    # (10584000, 2) means: 10,584,000 numbers per channel, 2 channels (stereo)
    samples, channels = audio.shape
    duration = samples / sr

    print(f"\n{name}")
    print(f"  shape        : {audio.shape}   <- (number of samples, channels)")
    print(f"  sample rate  : {sr} Hz        <- numbers per second, per channel")
    print(f"  duration     : {duration:.1f} seconds  ({samples} / {sr})")
    print(f"  data type    : {audio.dtype}")
    print(f"  value range  : {audio.min():+.3f} to {audio.max():+.3f}")

print("\n" + "-" * 70)
print("What one of those numbers actually means:")
print("-" * 70)
drums = stems["Drums"]
# Grab 8 consecutive samples from ~30 seconds in, left channel only.
start = 30 * sample_rate
print(f"\n8 raw samples of the drum stem at the 30-second mark (left channel):")
print(" ", np.round(drums[start:start + 8, 0], 5))
print("""
Each number is where the speaker cone should physically sit at that instant.
-1.0 = pushed fully out, +1.0 = pulled fully in, 0.0 = at rest.
Play 44,100 of those per second and your ear hears it as sound.

That is all audio is. Everything below is arithmetic on these numbers.
""")

print("=" * 70)
print("PART 2 - mixing is just adding, volume is just multiplying")
print("=" * 70)

# A "mix" is one gain (volume multiplier) per stem.
#   1.0 = untouched     0.5 = half volume     0.0 = muted entirely
gains = {
    "Vocals": 0.0,   # muted - this is your karaoke / sing-along track
    "Drums":  0.1,   # very faint - roughly a quarter as loud to the ear
    "Bass":   1.0,
    "Guitar": 1.0,
    "Piano":  1.0,
    "Other":  1.0,
}

print("\nGains being applied:")
for name, g in gains.items():
    label = "MUTED" if g == 0 else f"{int(g * 100)}%"
    print(f"  {name:<8} x {g:<5} ({label})")

# This next line IS the entire product. Multiply each stem by its volume,
# add them all together. Nothing else is happening.
mix = sum(stems[name] * gain for name, gain in gains.items())

# Clipping: if the numbers add up past +/-1.0, the speaker can't go further
# and you get harsh distortion. np.clip forces everything back into range.
over = np.sum(np.abs(mix) > 1.0)
print(f"\nSamples that went out of range before clipping: {over:,}")
mix = np.clip(mix, -1.0, 1.0)

sf.write("practice.wav", mix, sample_rate)
print("Wrote practice.wav  <- go listen to this")

print("\n" + "=" * 70)
print("PART 3 - do the stems actually add back up to the original?")
print("=" * 70)

original, orig_sr = sf.read(SONG)

# Every stem at 100%, nothing touched - this should sound like the record.
rebuilt = sum(stems.values())
sf.write("rebuilt.wav", np.clip(rebuilt, -1.0, 1.0), sample_rate)
print("\nWrote rebuilt.wav  <- all 6 stems at 100%, A/B this against the original mp3")

# The mp3 and the stems can differ by a few samples in length; compare the
# overlapping part only.
n = min(len(original), len(rebuilt))
residual = original[:n] - rebuilt[:n]

original_energy = float(np.abs(original[:n]).mean())
residual_energy = float(np.abs(residual).mean())

print(f"\n  average level of the original : {original_energy:.6f}")
print(f"  average level of what's left   : {residual_energy:.6f}")
print(f"  leftover as % of original      : {residual_energy / original_energy * 100:.2f}%")
print("""
Why this matters: if the 6 stems add back up to (almost) the original, then
setting every slider to 100% gives you the record back, and your volume
controls will behave the way a listener expects. A big leftover means the
model is losing or inventing energy, and "100%" would sound wrong.
""")
