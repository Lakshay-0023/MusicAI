"""
Phase 1: split one song into stems, then listen hard.

What happens here:
  A pretrained neural network (htdemucs_ft) looks at the song's waveform and
  guesses, sample by sample, which parts belong to vocals / drums / bass /
  "other". It writes each guess out as its own audio file into stems/.

  The first run also downloads the model itself (a few hundred MB) into a
  local cache — that only happens once.
"""

from audio_separator.separator import Separator

SONG = "Ae Dil Hai Mushkil Title Track Full Video - Ranbir, Anushka, Aishwarya  Arijit Singh Pritam.mp3"

# output_dir is where the separated stems get written
separator = Separator(output_dir="stems")

# load_model downloads (first time only) and prepares the trained weights
#
# Using htdemucs_6s: splits into 6 stems instead of 4 - vocals, drums, bass,
# guitar, piano, other. Guitar/piano separation is rougher than the core
# vocals/drums/bass split (trained on less data for those two), but it's
# worth it for practicing a specific instrument. Runs fine on the GPU.
separator.load_model(model_filename="htdemucs_6s.yaml")

# separate() runs the model on the song and returns the list of files it wrote
output_files = separator.separate(SONG)

print("\nDone. Files written:")
for f in output_files:
    print(" -", f)
