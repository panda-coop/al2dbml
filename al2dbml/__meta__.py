"""Project metadata constants.

A standalone module so other modules (``diagram.py``, the CLI, etc.) can read
``__version__`` without importing from the package root, which would create a
circular import. The package's ``__init__`` re-exports the constants from here.
"""

from __future__ import annotations

__version__ = "0.10.0"
