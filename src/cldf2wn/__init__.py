"""Convert CLDF wordlists into WN-LMF wordnets via Concepticon and the ILI."""

from .convert import Doculect, LexiconStats, read_dataset
from .ili import Concept, build_mapping, load_mapping, write_mapping
from .lmf import Metadata, write_dataset

__version__ = "0.1.0"
__all__ = [
    "Concept", "Doculect", "LexiconStats", "Metadata",
    "build_mapping", "load_mapping", "read_dataset", "write_dataset", "write_mapping",
]
