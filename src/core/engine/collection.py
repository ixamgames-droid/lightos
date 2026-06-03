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
        self._registry: dict[int, Function] | None = None
        self._started: set[int] = set()

    # ── Management ────────────────────────────────────────────────────────────

    def add_function(self, function_id: int):
        if function_id not in self.function_ids:
            self.function_ids.append(function_id)

    def remove_function(self, function_id: int):
        self.function_ids = [fid for fid in self.function_ids if fid != function_id]

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _on_start(self):
        # Kinder werden beim ersten write() sauber gestartet (start() setzt
        # _running=True, _elapsed=0 und ruft _on_start) — hier nur Tracking leeren.
        self._started = set()

    def _on_stop(self):
        # Kinder ebenfalls stoppen, sonst laufen sie nach dem Collection-Stop
        # weiter (Audit-Befund: child._running nie zurueckgesetzt).
        reg = self._registry
        if reg:
            for fid in self.function_ids:
                child = reg.get(fid)
                if child is not None:
                    child.stop()
        self._started = set()

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
        self._registry = function_registry

        for fid in self.function_ids:
            child = function_registry.get(fid)
            if child is None:
                continue
            # Beim ersten Frame sauber starten (Fade-In/Step-Reset). Danach nur
            # write() aufrufen — das Child zaehlt _elapsed selbst hoch (kein
            # doppeltes dt mehr).
            if fid not in self._started:
                child.start()
                self._started.add(fid)
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
