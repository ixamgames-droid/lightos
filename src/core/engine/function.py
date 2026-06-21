"""Base Function class and enums for QLC+ v5 function types."""
from __future__ import annotations
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.dmx.universe import Universe
    from src.core.database.models import PatchedFixture

from .fade_curve import eval_named   # ARC-04/FW-4: Form der Hüllkurve (Leaf-Modul)


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
        # F-17: Layer-Prioritaet beim Engine-Merge. Hoehere Prioritaet gewinnt bei
        # Kanal-/Attribut-Ueberschneidung (tickt zuletzt -> LTP). Gleiche Prioritaet
        # faellt auf die Start-Reihenfolge zurueck (Verhalten wie bisher, Default 0).
        self.priority: int = 0
        # ARC-04: zeitbasierte Ein-/Ausblend-Huellkurve (Sekunden, 0 = aus). Wirkt als
        # Output-Multiplikator ueber ALLE Kanaele der Funktion (nicht nur Dimmer),
        # angewandt im FunctionManager.tick. Eigene Namen (env_*), um Scene.fade_in
        # (kurvenbasierte Wert-Interpolation, andere Semantik) NICHT zu kollidieren.
        self.env_fade_in: float = 0.0
        self.env_fade_out: float = 0.0
        self._env_elapsed: float = 0.0     # laeuft seit (Re-)Start -> Fade-In
        self._releasing: bool = False      # True = Fade-Out laeuft (nach release())
        self._release_elapsed: float = 0.0
        # FW-4: Form der Hüllkurve (kurzer Name aus fade_curve.CURVE_NAMES;
        # "linear" = unveränderter, gerader Verlauf).
        self.env_curve: str = "linear"
        # WP-Tempo: Anbindung an einen Tempo-Bus (core/engine/tempo_bus.py +
        # docs/TEMPO_SYNC_PLAN.md). "" = Free-Run wie bisher (Subtyp liest KEINEN Bus).
        # Sonst leitet ein zeitbasierter Subtyp seine Phase aus der Bus-Position ab:
        #   effect_pos = (bus.position - _beat_anchor) * tempo_multiplier + phase_offset
        # tempo_multiplier = harmonisches Verhältnis (×¼…×4), phase_offset in Beats,
        # sync_group bündelt Effekte, die per "Sync" gemeinsam re-ankern.
        self.tempo_bus_id: str = ""
        self.tempo_multiplier: float = 1.0
        self.phase_offset: float = 0.0
        self.sync_group: str = ""
        self._beat_anchor: float = 0.0     # Bus-Position beim letzten Sync/Start (privat, nicht serialisiert)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        """Called when function is started."""
        self._running = True
        self._elapsed = 0.0
        self._env_elapsed = 0.0
        self._releasing = False
        self._release_elapsed = 0.0
        self._on_start()

    def stop(self):
        """Called when function is stopped."""
        self._running = False
        self._elapsed = 0.0
        self._releasing = False
        self._release_elapsed = 0.0
        self._on_stop()

    def _on_start(self):
        pass

    def _on_stop(self):
        pass

    @property
    def is_running(self) -> bool:
        return self._running

    # ── ARC-04: Ein-/Ausblend-Huellkurve ───────────────────────────────────────

    def release(self):
        """Fade-Out einleiten — die Funktion bleibt laufend und blendet ueber
        env_fade_out Sekunden aus (vom FunctionManager getickt), statt sofort zu
        stoppen. Ohne env_fade_out wirkungslos (der Caller stoppt dann hart)."""
        if not self._releasing:
            self._releasing = True
            self._release_elapsed = 0.0

    def env_factor(self, dt: float) -> float:
        """Output-Multiplikator 0..1 fuer diesen Frame; treibt die Huellkurven-Uhr
        um dt weiter. MUSS pro Frame genau einmal aufgerufen werden. Fade-In rampt
        nach (Re-)Start ueber env_fade_in hoch; Fade-Out rampt nach release() ueber
        env_fade_out auf 0."""
        if self._releasing:
            if self.env_fade_out <= 0.0:
                return 0.0
            self._release_elapsed += dt
            remaining = max(0.0, 1.0 - self._release_elapsed / self.env_fade_out)
            return eval_named(self.env_curve, remaining)   # FW-4: Form anwenden
        self._env_elapsed += dt
        if self.env_fade_in <= 0.0:
            return 1.0
        prog = max(0.0, min(1.0, self._env_elapsed / self.env_fade_in))
        return eval_named(self.env_curve, prog)            # FW-4: Form anwenden

    def env_release_done(self) -> bool:
        """True, wenn der Fade-Out fertig ist (Funktion darf entfernt werden)."""
        return self._releasing and (self.env_fade_out <= 0.0
                                    or self._release_elapsed >= self.env_fade_out)

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
            "priority": self.priority,
            "env_fade_in": self.env_fade_in,
            "env_fade_out": self.env_fade_out,
            "env_curve": self.env_curve,
            "tempo_bus_id": self.tempo_bus_id,
            "tempo_multiplier": self.tempo_multiplier,
            "phase_offset": self.phase_offset,
            "sync_group": self.sync_group,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Function":
        raise NotImplementedError
