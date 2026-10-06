"""BTC - the Bi-directional Transformer for Chord recognition.

Third-party code (Park et al., ISMIR 2019, MIT licence - see LICENSE),
copied from github.com/jayg996/BTC-ISMIR19 rather than installed: it is not a
pip package, and its original code no longer runs on current numpy. Only the
network itself is here; the training scripts and their dependencies are not.
"""

from .model import BTC_model, CONFIG, FRAMES_PER_WINDOW, WINDOW_SECONDS, label_of

__all__ = ["BTC_model", "CONFIG", "FRAMES_PER_WINDOW", "WINDOW_SECONDS", "label_of"]
