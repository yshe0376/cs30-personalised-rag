"""Isolated v2 M1 contracts and corpus build boundary.

The package is deliberately separate from the v1 modules while v1 is still
being frozen.  It does not auto-upgrade or read v1 assets.
"""

from cs30.v2.catalog import REQUIRED_TEXTBOOK_IDS
from cs30.v2.evidence import CitationValidatorAdapter, EvidenceBundleAdapter

__all__ = [
    "CitationValidatorAdapter",
    "EvidenceBundleAdapter",
    "REQUIRED_TEXTBOOK_IDS",
]
