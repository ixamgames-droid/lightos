"""FunctionManager singleton — owns all Functions and drives their tick loop."""
from __future__ import annotations
from typing import TYPE_CHECKING
from .function import Function, FunctionType, _alloc_id, bump_next_id
from .scene import Scene
from .chaser import Chaser
from .collection import Collection
from .show_engine import Show
from .sequence import Sequence
from .audio_func import AudioFunction
from .effect_func import LayeredEffect
from .carousel import Carousel

if TYPE_CHECKING:
    from src.core.dmx.universe import Universe
    from src.core.database.models import PatchedFixture


class FunctionManager:
    """
    Singleton that holds all QLC+ Function objects.
    tick() is called every frame by the OutputManager callback.
    """

    def __init__(self):
        self._functions: dict[int, Function] = {}
        self._running_ids: set[int] = set()

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add(self, f: Function) -> Function:
        self._functions[f.id] = f
        return f

    def remove(self, fid: int):
        self.stop(fid)
        self._functions.pop(fid, None)

    def get(self, fid: int) -> Function | None:
        return self._functions.get(fid)

    def all(self) -> list[Function]:
        return list(self._functions.values())

    def by_type(self, ftype: FunctionType) -> list[Function]:
        return [f for f in self._functions.values() if f.function_type == ftype]

    # ── Factory helpers ───────────────────────────────────────────────────────

    def new_scene(self, name: str = "Neue Szene") -> Scene:
        f = Scene(name)
        return self.add(f)

    def new_chaser(self, name: str = "Neuer Chaser") -> Chaser:
        f = Chaser(name)
        return self.add(f)

    def new_collection(self, name: str = "Neue Collection") -> Collection:
        f = Collection(name)
        return self.add(f)

    def new_show(self, name: str = "Neue Show") -> Show:
        f = Show(name)
        return self.add(f)

    def new_sequence(self, name: str = "Neue Sequence") -> Sequence:
        f = Sequence(name)
        return self.add(f)

    def new_audio(self, name: str = "Neues Audio") -> AudioFunction:
        f = AudioFunction(name)
        return self.add(f)

    def new_layered_effect(self, name: str = "Neuer Effekt") -> LayeredEffect:
        f = LayeredEffect(name)
        return self.add(f)

    def new_carousel(self, name: str = "Neues Carousel") -> Carousel:
        f = Carousel(name)
        return self.add(f)

    # ── Playback ──────────────────────────────────────────────────────────────

    def start(self, fid: int):
        f = self._functions.get(fid)
        if f is None:
            return
        f.start()
        self._running_ids.add(fid)

    def stop(self, fid: int):
        f = self._functions.get(fid)
        if f is not None:
            f.stop()
        self._running_ids.discard(fid)

    def stop_all(self):
        for fid in list(self._running_ids):
            self.stop(fid)

    def is_running(self, fid: int) -> bool:
        f = self._functions.get(fid)
        return f is not None and f.is_running

    # ── Frame tick ────────────────────────────────────────────────────────────

    def tick(self, universes: dict[int, "Universe"],
             patch_cache: list["PatchedFixture"],
             dt: float):
        """Called every frame (44 Hz). Drives all running functions."""
        finished = set()
        for fid in list(self._running_ids):
            f = self._functions.get(fid)
            if f is None:
                finished.add(fid)
                continue
            if not f.is_running:
                finished.add(fid)
                continue
            try:
                f.write(universes, patch_cache, dt, self._functions)
            except Exception as exc:
                print(f"[FunctionManager] tick error in function {fid}: {exc}")
            # After write, check again
            if not f.is_running:
                finished.add(fid)
        self._running_ids -= finished

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "functions": [f.to_dict() for f in self._functions.values()]
        }

    def from_dict(self, d: dict):
        """Load functions from dict, clearing existing ones first."""
        self.stop_all()
        self._functions.clear()
        for fd in d.get("functions", []):
            ftype = fd.get("type", "Scene")
            try:
                if ftype == "Script" or ftype == FunctionType.Script.value:
                    from .script_func import ScriptFunction
                    f = ScriptFunction.from_dict(fd)
                elif ftype == FunctionType.Scene.value:
                    f = Scene.from_dict(fd)
                elif ftype == FunctionType.Chaser.value:
                    f = Chaser.from_dict(fd)
                elif ftype == FunctionType.Sequence.value:
                    f = Sequence.from_dict(fd)
                elif ftype == FunctionType.Collection.value:
                    f = Collection.from_dict(fd)
                elif ftype == FunctionType.Show.value:
                    f = Show.from_dict(fd)
                elif ftype == FunctionType.Audio.value:
                    f = AudioFunction.from_dict(fd)
                elif ftype == FunctionType.EFX.value:
                    # EFX-Tag wird von LayeredEffect und Carousel geteilt.
                    # Unterscheidung anhand der gespeicherten Keys.
                    if "layers" in fd:
                        f = LayeredEffect.from_dict(fd)
                    elif "pattern" in fd:
                        f = Carousel.from_dict(fd)
                    else:
                        continue
                else:
                    continue
            except Exception as exc:
                print(f"[FunctionManager] from_dict skip {ftype}: {exc}")
                continue
            self._functions[f.id] = f
        # ID-Zaehler hinter die hoechste geladene ID setzen, sonst kollidieren
        # neu erstellte Funktionen mit geladenen und ueberschreiben sie.
        bump_next_id(self._functions.keys())


# ── Singleton ─────────────────────────────────────────────────────────────────

_manager: FunctionManager | None = None


def get_function_manager() -> FunctionManager:
    global _manager
    if _manager is None:
        _manager = FunctionManager()
    return _manager
