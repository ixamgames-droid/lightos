"""Collection function — runs multiple functions simultaneously."""
from __future__ import annotations
from typing import TYPE_CHECKING
from .function import Function, FunctionType

if TYPE_CHECKING:
    from src.core.dmx.universe import Universe
    from src.core.database.models import PatchedFixture


class Collection(Function):
    """
    QLC+ Collection: runs a list of functions simultaneously.
    All child functions receive the same write() call each frame.
    """

    function_type = FunctionType.Collection

    def __init__(self, name: str = "Neue Collection", fid: int | None = None):
        super().__init__(name, fid)
        self.function_ids: list[int] = []

    # ── Management ────────────────────────────────────────────────────────────

    def add_function(self, function_id: int):
        if function_id not in self.function_ids:
            self.function_ids.append(function_id)

    def remove_function(self, function_id: int):
        self.function_ids = [fid for fid in self.function_ids if fid != function_id]

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _on_start(self):
        pass

    def _on_stop(self):
        pass

    # ── write ─────────────────────────────────────────────────────────────────

    def write(self, universes: dict[int, "Universe"],
              patch_cache: list["PatchedFixture"],
              dt: float,
              function_registry: dict[int, Function] | None = None):
        if not self._running:
            return

        self._elapsed += dt

        if function_registry is None:
            return

        for fid in self.function_ids:
            child = function_registry.get(fid)
            if child is not None:
                child._running = True
                child._elapsed += dt
                child.write(universes, patch_cache, dt, function_registry)

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["function_ids"] = list(self.function_ids)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Collection":
        c = cls(name=d.get("name", "Collection"), fid=d.get("id"))
        c.function_ids = list(d.get("function_ids", []))
        return c
