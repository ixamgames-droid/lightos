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
        # ENG-14: Wiedereintritts-Sperren gegen Zyklen (A->B->A oder A->A).
        # Eine Collection kann Collections enthalten; enthaelt eine davon wieder
        # die erste, ruft sich `write`/`_on_stop` endlos selbst auf. Gemessen:
        # RecursionError in JEDEM Frame, und `stop()` kam nicht mehr durch —
        # also blieb STOP ALL wirkungslos, waehrend Chaser und Cues weiterliefen.
        #
        # Bewusst eine Sperre und KEINE Tiefenbegrenzung wie in
        # `function_coverage`: dort wird einmalig ausgewertet, hier laeuft es
        # 44-mal je Sekunde. Eine Tiefengrenze wuerde den Zyklus jeden Frame
        # bis zur Grenze abarbeiten; die Sperre haelt beim ersten Wiedereintritt.
        self._in_write = False
        self._in_stop = False
        self._zyklus_gemeldet = False

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
        #
        # ENG-14: `Function.stop()` ist NICHT idempotent — es ruft `_on_stop()`
        # auch dann, wenn schon gestoppt wurde. Bei einem Zyklus stoppt A also B,
        # B stoppt A, A stoppt B ... bis der Stack reisst. Die Sperre hier statt
        # in `Function.stop()`: die Basis darf ein `stop()` auf einer bereits
        # gestoppten Funktion weiterhin zum Zuruecksetzen benutzen.
        if self._in_stop:
            return
        self._in_stop = True
        try:
            reg = self._registry
            if reg:
                for fid in self.function_ids:
                    child = reg.get(fid)
                    if child is not None:
                        child.stop()
            self._started = set()
        finally:
            self._in_stop = False

    # ── write ─────────────────────────────────────────────────────────────────

    def write(self, universes: dict[int, "Universe"],
              patch_cache: list["PatchedFixture"],
              dt: float,
              function_registry: dict[int, Function] | None = None):
        if not self._running:
            return

        # ENG-14: Wiedereintritt heisst Zyklus — hier aussteigen, sonst
        # RecursionError in jedem einzelnen Frame.
        if self._in_write:
            if not self._zyklus_gemeldet:
                self._zyklus_gemeldet = True
                print(f"[collection] ERROR: Sammlung '{self.name}' (id {self.id}) "
                      f"enthaelt sich selbst — der Kreis wird hier abgebrochen. "
                      f"Betroffene Mitglieder: {self.function_ids}")
            return
        self._in_write = True
        try:
            self._elapsed += dt

            if function_registry is None:
                return
            self._registry = function_registry

            for fid in self.function_ids:
                child = function_registry.get(fid)
                if child is None:
                    continue
                # Beim ersten Frame sauber starten (Fade-In/Step-Reset). Danach
                # nur write() aufrufen — das Child zaehlt _elapsed selbst hoch
                # (kein doppeltes dt mehr).
                if fid not in self._started:
                    child.start()
                    self._started.add(fid)
                child.write(universes, patch_cache, dt, function_registry)
        finally:
            self._in_write = False

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
