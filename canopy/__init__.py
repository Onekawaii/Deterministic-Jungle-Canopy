"""
The Deterministic Jungle Canopy 🦜🌿
A procedural image and video processing pipeline.
Same seed = same output. Always.
"""
__version__ = "0.1.0-alpha"
__author__ = "The Prophet"

from .core.renderer import CanopyRenderer
from .core.seeded_random import SeededRandom
from .core.grid import GridManipulator
from .archive.database import Archive
from .manifest import Manifest, ManifestBuilder
from .version import __version__, __schema_version__, RNG_ALGORITHM

__all__ = [
    "CanopyRenderer", 
    "SeededRandom", 
    "GridManipulator", 
    "Archive",
    "Manifest",
    "ManifestBuilder",
    "__version__",
    "__schema_version__",
    "RNG_ALGORITHM",
]
