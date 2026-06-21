"""ShowBuilder-DSL: per-Skript Shows bauen, die NUR echte Bausteine nutzen
können (Validierung at call time). Siehe SecondBrain entry_show_validation.

    from src.core.show.showbuilder import ShowBuilder, BuildError
"""
from __future__ import annotations

from .builder import ShowBuilder, Handle
from .errors import BuildError, did_you_mean

__all__ = ["ShowBuilder", "Handle", "BuildError", "did_you_mean"]
