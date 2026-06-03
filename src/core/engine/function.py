"""Base Function class and enums for QLC+ v5 function types."""
from __future__ import annotations
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.dmx.universe import Universe
    from src.core.database.models import PatchedFixture


class FunctionType(Enum):
    Scene = "Scene"
    Chaser = "Chaser"
    Sequence = "Sequence"
    Collection = "Collection"
    Show = "Show"
    EFX = "EFX"
    RGBMatrix = "RGBMatrix"
    Audio = "Audio"
    Script = "Script"


class RunOrder(Enum):
    Loop = "Loop"
    SingleShot = "SingleShot"
    PingPong = "PingPong"
    Random = "Random"


class Direction(Enum):
    Forward = "Forward"
    Backward = "Backward"


_next_id = 1


def _alloc_id() -> int:
    global _next_id
    fid = _next_id
    _next_id += 1
    return fid


def bump_next_id(used_ids) -> None:
    """Hebt den globalen ID-Zaehler an, damit kuenftige _alloc_id()-Aufrufe
    keine bereits vergebene (z. B. aus einer geladenen Show stammende) ID
    erneut liefern. Verhindert stilles Ueberschreiben geladener Funktionen."""
    global _next_id
    for fid in used_ids:
        try:
            if int(fid) >= _next_id:
                _next_id = int(fid) + 1
        except (TypeError, ValueError):
            continue


class Function:
    """Abstract base for all QLC+ function types."""

    function_type: FunctionType = FunctionType.Scene  # overridden by subclasses

    def __init__(self, name: str = "Neue Funktion", fid: int | None = None):
        self.id: int = fid if fid is not None else _alloc_id()
        self.name: str = name
        self._running: bool = False
        self._elapsed: float = 0.0
        # Per-Effekt-Master (Block B). intensity skaliert die Ausgabe (0..1,
        # angewandt im FunctionManager.tick), speed ist ein Zeit-Multiplikator
        # (0.1..4.0, von zeitbasierten Subtypen selbst angewandt). Chaser und
        # Sequence definieren self.speed bereits eigenstaendig (gleicher Name).
        self.intensity: float = 1.0
        self.speed: float = 1.0
        # Bibliotheks-Ordner (verschachtelbar, "/"-getrennt). "" = Wurzel.
        # Pro Show gespeichert; siehe docs/PROGRAMMER_REBUILD.md (Phase 1).
        self.folder: str = ""

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        """Called when function is started."""
        self._running = True
        self._elapsed = 0.0
        self._on_start()

    def stop(self):
        """Called when function is stopped."""
        self._running = False
        self._elapsed = 0.0
        self._on_stop()

    def _on_start(self):
        pass

    def _on_stop(self):
        pass

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Per-frame tick ────────────────────────────────────────────────────────

    def write(self, universes: dict[int, "Universe"],
              patch_cache: list["PatchedFixture"],
              dt: float,
              function_registry: dict[int, "Function"] | None = None):
        """
        Called every frame while running.
        Subclasses override this to produce DMX output.
        dt: delta time in seconds since last call.
        """
        raise NotImplementedError

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.function_type.value,
            "intensity": self.intensity,
            "speed": self.speed,
            "folder": self.folder,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Function":
        raise NotImplementedError
