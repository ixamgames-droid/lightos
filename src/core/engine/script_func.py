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

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _on_start(self):
        self._line_idx = 0
        self._wait_until = 0.0
        self._lines = [l.rstrip() for l in self.script.splitlines()]

    def _on_stop(self):
        self._lines = []
        self._line_idx = 0
        self._wait_until = 0.0

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
            # Best-effort: zero out all universes
            if len(parts) >= 2 and parts[1].lower() in ("on", "1", "true"):
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
