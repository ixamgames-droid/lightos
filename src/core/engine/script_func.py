"""Script Function - text-based command interpreter.

Supported commands (one per line, # = comment):
  wait <seconds>                  - pause for N seconds
  setdmx <universe> <channel> <value>
  setfixture <fid> <attribute> <value>
  start function <fid>
  stop function <fid>
  blackout on|off

Anything else is ignored (logged via print).
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional
from .function import Function, FunctionType
from .function import gibt_ueber_dmx_aus as _gibt_ueber_dmx_aus

if TYPE_CHECKING:
    from src.core.dmx.universe import Universe
    from src.core.database.models import PatchedFixture


class ScriptFunction(Function):
    function_type = FunctionType.Scene  # reuse Scene type for storage compat; tagged below

    def __init__(self, name: str = "Neues Script", fid: int | None = None):
        super().__init__(name, fid)
        self.script: str = "# Befehle, eine pro Zeile\n# wait 1.0\n# setdmx 1 1 255\n"
        self._line_idx: int = 0
        self._wait_until: float = 0.0  # absolute elapsed time when current wait ends
        self._lines: list[str] = []
        # Mark this as a script subclass via attribute for editors
        self.is_script = True
        # OUT-57: Besitz am globalen Blackout. ``None`` = dieses Skript hat ihn
        # nicht gesetzt; sonst der ``blackout_epoch`` des OutputManagers direkt nach
        # dem eigenen „blackout on". Nur dann darf „blackout off" bzw. ein Stop des
        # Skripts ihn zuruecknehmen — einen Blackout des Operators (oder einen, den
        # der Operator seitdem selbst neu geschaltet hat) loest ein Skript nie.
        self._blackout_epoch: int | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _on_start(self):
        self._line_idx = 0
        self._wait_until = 0.0
        self._lines = [l.rstrip() for l in self.script.splitlines()]

    def _on_stop(self):
        self._lines = []
        self._line_idx = 0
        self._wait_until = 0.0
        # OUT-57: Stop/Abbruch nimmt einen vom Skript gesetzten Blackout zurueck —
        # sonst rastete „blackout on" dauerhaft ein, und nur der Operator-Knopf
        # kaeme wieder heraus. Laeuft das Skript dagegen regulaer zu Ende, bleibt
        # der Blackout bewusst stehen (ein Einzeiler „blackout on" soll wirken);
        # der Besitz bleibt gemerkt, ein spaeterer Stop nimmt ihn zurueck.
        self._blackout_freigeben()

    def _blackout_freigeben(self):
        """OUT-57: hebt den Blackout auf, wenn ER von diesem Skript stammt und
        seitdem niemand sonst ihn umgeschaltet hat; vergisst den Besitz immer."""
        epoch, self._blackout_epoch = self._blackout_epoch, None
        if epoch is None:
            return
        om = self._output_manager()
        if om is None:
            return
        if om.blackout and getattr(om, "blackout_epoch", None) == epoch:
            om.set_blackout(False)

    # ── write ─────────────────────────────────────────────────────────────────

    def write(self, universes: dict[int, "Universe"],
              patch_cache: list["PatchedFixture"],
              dt: float,
              function_registry: dict[int, Function] | None = None):
        if not self._running:
            return
        self._elapsed += dt

        # If we are in a wait period, skip until done
        if self._elapsed < self._wait_until:
            return

        # Execute as many lines as we can in this frame (until wait or end)
        max_lines_per_frame = 50
        for _ in range(max_lines_per_frame):
            if self._line_idx >= len(self._lines):
                self._running = False
                return
            line = self._lines[self._line_idx].strip()
            self._line_idx += 1
            if not line or line.startswith("#"):
                continue
            try:
                if self._execute_line(line, universes, patch_cache, function_registry):
                    # _execute_line returned True meaning "wait set" - break
                    return
            except Exception as exc:
                print(f"[ScriptFunction] Line {self._line_idx}: '{line}' error: {exc}")

    @staticmethod
    def _output_manager():
        """OUT-57: der OutputManager der laufenden App — oder None. Bewusst NICHT
        ``get_state()``: das wuerde ohne App eine komplette AppState samt Show und
        Output-Thread anlegen."""
        try:
            from src.core import app_state as _app_state
            st = getattr(_app_state, "_state", None)
            return getattr(st, "output_manager", None) if st is not None else None
        except Exception:
            return None

    def _execute_line(self, line: str, universes, patch_cache, registry) -> bool:
        """Returns True if execution should pause this frame (wait command)."""
        parts = line.split()
        if not parts:
            return False
        cmd = parts[0].lower()

        if cmd == "wait":
            if len(parts) >= 2:
                seconds = float(parts[1])
                self._wait_until = self._elapsed + seconds
                return True
        elif cmd == "setdmx":
            if len(parts) >= 4:
                u = int(parts[1]); ch = int(parts[2]); val = int(parts[3])
                universe = universes.get(u)
                if universe and 1 <= ch <= 512:
                    universe.set_channel(ch, max(0, min(255, val)))
        elif cmd == "setfixture":
            if len(parts) >= 4:
                fid = int(parts[1])
                attr = parts[2]
                val = int(parts[3])
                fixture = next((f for f in patch_cache if f.fid == fid), None)
                # QA-78: gemessen erreichbar (Laser schrieb auf Adresse 2).
                if fixture is not None and not _gibt_ueber_dmx_aus(fixture):
                    return True
                if fixture is None:
                    return False
                # Lookup channel offset by attribute
                from src.core.app_state import get_channels_for_patched
                for ch in get_channels_for_patched(fixture):
                    if ch.attribute == attr:
                        dmx_addr = fixture.address + ch.channel_number - 1
                        universe = universes.get(fixture.universe)
                        if universe and 1 <= dmx_addr <= 512:
                            universe.set_channel(dmx_addr, max(0, min(255, val)))
                        break
        elif cmd == "start" and len(parts) >= 3 and parts[1].lower() == "function":
            fid = int(parts[2])
            if registry:
                child = registry.get(fid)
                if child is not None:
                    child.start()
        elif cmd == "stop" and len(parts) >= 3 and parts[1].lower() == "function":
            fid = int(parts[2])
            if registry:
                child = registry.get(fid)
                if child is not None:
                    child.stop()
        elif cmd == "blackout":
            # OUT-57: derselbe Blackout wie Kopfzeilen-Knopf, VC, Web, OSC und
            # Kommandozeile — ueber den OutputManager (nullt nur Dimmer/Farbe,
            # Laser/Nebel komplett; Pan/Tilt bleiben). Frueher schrieb das Skript
            # alle 512 Kanaele direkt auf 0: das liess Moving Heads in die
            # Grundstellung fahren, der Kopfzeilen-Knopf bekam nichts mit und
            # „blackout off" tat gar nichts.
            an = len(parts) >= 2 and parts[1].lower() in ("on", "1", "true")
            om = self._output_manager()
            if om is not None:
                if an:
                    # Nur wer den Blackout wirklich EINschaltet, besitzt ihn — stand
                    # er schon (Operator), bleibt er dessen Sache.
                    if not om.blackout:
                        om.set_blackout(True)
                        self._blackout_epoch = getattr(om, "blackout_epoch", None)
                else:
                    # „blackout off" loest nur den eigenen Blackout, nie den des
                    # Operators (der Knopf oben rechts bleibt Herr ueber seinen).
                    self._blackout_freigeben()
            elif an:
                # Ohne laufende App (isolierter Aufruf) bleibt nur das alte
                # Best-effort-Nullen der uebergebenen Universen.
                for u in universes.values():
                    for c in range(1, 513):
                        u.set_channel(c, 0)
        return False

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["type"] = "Script"
        d["script"] = self.script
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ScriptFunction":
        s = cls(name=d.get("name", "Script"), fid=d.get("id"))
        s.script = d.get("script", "")
        return s
