"""FunctionManager singleton — owns all Functions and drives their tick loop."""
from __future__ import annotations
import threading
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
from .efx import EfxInstance
from .rgb_matrix import RgbMatrixInstance

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
        # Schuetzt _running_ids/_start_order. start()/stop() laufen aus dem MIDI-/
        # OSC-Thread, tick() aus dem Output-Thread — ohne Lock drohte beim Bilden
        # der Tick-Reihenfolge "set/list changed size during iteration". RLock,
        # weil stop_all() ueber stop() reentrant ist.
        self._lock = threading.RLock()
        # Start-Reihenfolge laufender Funktionen (zuletzt gestartete am Ende) —
        # fuer active_function() / Aktiv-Effekt-Master (Block B).
        self._start_order: list[int] = []
        # Cache der Dim-Adressen je Universum fuer die Per-Effekt-Intensitaet.
        # An die Identitaet des patch_cache gebunden (Re-Patch => Neuaufbau).
        self._dim_map_cache: dict[int, frozenset[int]] | None = None
        self._dim_map_key: int = -1

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add(self, f: Function) -> Function:
        self._functions[f.id] = f
        # Zentrale Benachrichtigung: jede neu erstellte Funktion (Scene, Chaser,
        # Matrix, EFX, …) erscheint sofort in allen Listen/Auswahlfeldern
        # (Abschnitt 1). from_dict() umgeht add() bewusst (Bulk-Load → SHOW_LOADED),
        # daher kein Event-Spam beim Show-Laden.
        self._notify_functions_changed({"id": f.id})
        return f

    def remove(self, fid: int):
        self.stop(fid)
        self._functions.pop(fid, None)
        self._notify_functions_changed({"id": fid, "removed": True})

    @staticmethod
    def _notify_functions_changed(data=None):
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.FUNCTION_CHANGED, data)
        except Exception:
            pass

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

    def new_efx(self, name: str = "Neue Bewegung") -> EfxInstance:
        f = EfxInstance(name)
        return self.add(f)

    def new_rgb_matrix(self, name: str = "Neue Matrix") -> RgbMatrixInstance:
        f = RgbMatrixInstance(name)
        return self.add(f)

    # ── Playback ──────────────────────────────────────────────────────────────

    def start(self, fid: int):
        f = self._functions.get(fid)
        if f is None:
            return
        f.start()
        with self._lock:
            self._running_ids.add(fid)
            # Start-Reihenfolge pflegen: ans Ende (= zuletzt gestartet) verschieben.
            try:
                self._start_order.remove(fid)
            except ValueError:
                pass
            self._start_order.append(fid)

    def stop(self, fid: int):
        f = self._functions.get(fid)
        if f is not None:
            f.stop()
        with self._lock:
            self._running_ids.discard(fid)
            try:
                self._start_order.remove(fid)
            except ValueError:
                pass

    def active_function(self) -> Function | None:
        """Die zuletzt gestartete, noch laufende Funktion (Aktiv-Effekt-Master).
        Aufraeumen stiller Eintraege (z. B. selbst-stoppende SingleShot-Chaser)."""
        while self._start_order:
            fid = self._start_order[-1]
            f = self._functions.get(fid)
            if f is not None and f.is_running:
                return f
            self._start_order.pop()
        return None

    def stop_all(self):
        for fid in list(self._running_ids):
            self.stop(fid)

    def is_running(self, fid: int) -> bool:
        f = self._functions.get(fid)
        return f is not None and f.is_running

    # ── Frame tick ────────────────────────────────────────────────────────────

    # Attribut-Klassen fuer die Per-Effekt-Intensitaet (Block B).
    _INTENSITY_ATTRS = frozenset({"intensity", "dimmer", "master"})
    _COLOR_ATTRS = frozenset({
        "color_r", "color_g", "color_b", "color_w", "color_a", "color_uv",
        "red", "green", "blue", "white", "amber", "uv",
        "cyan", "magenta", "yellow",
    })

    def _dim_addr_map(self, patch_cache: list["PatchedFixture"]
                      ) -> dict[int, frozenset[int]]:
        """{universe: frozenset(addr)} — Adressen, die die Per-Effekt-Intensitaet
        skaliert. Pro Fixture: gibt es einen Dimmer/Intensitaets-Kanal, werden nur
        dessen Adressen skaliert (virtueller Dimmer, kein Doppel-Dimmen). Sonst
        Fallback auf die Farbkanaele. Pan/Tilt/Gobo etc. werden nie skaliert.
        Ergebnis an die patch_cache-Identitaet gebunden gecached."""
        key = id(patch_cache)
        if self._dim_map_cache is not None and self._dim_map_key == key:
            return self._dim_map_cache
        try:
            from src.core.app_state import get_channels_for_patched
        except Exception:
            return {}
        acc: dict[int, set[int]] = {}
        for fx in patch_cache or ():
            try:
                channels = get_channels_for_patched(fx)
            except Exception:
                continue
            inten_addrs: set[int] = set()
            color_addrs: set[int] = set()
            for ch in channels:
                attr = (getattr(ch, "attribute", "") or "").lower()
                addr = fx.address + ch.channel_number - 1
                if not (1 <= addr <= 512):
                    continue
                if attr in self._INTENSITY_ATTRS:
                    inten_addrs.add(addr)
                elif attr in self._COLOR_ATTRS:
                    color_addrs.add(addr)
            scal = inten_addrs if inten_addrs else color_addrs
            if scal:
                acc.setdefault(fx.universe, set()).update(scal)
        result = {u: frozenset(a) for u, a in acc.items()}
        self._dim_map_cache = result
        self._dim_map_key = key
        return result

    def tick(self, universes: dict[int, "Universe"],
             patch_cache: list["PatchedFixture"],
             dt: float):
        """Called every frame (44 Hz). Drives all running functions.

        Per-Effekt-Intensitaet (Block B): Funktionen mit intensity < 1.0 werden
        in ein privates Universum gerendert und ihre geaenderten Kanaele skaliert
        ins gemeinsame Scratch gemerged (Dim-/Farbadressen * intensity). Bei
        intensity == 1.0 wird direkt geschrieben (Fast-Path, kein Kopieraufwand)."""
        from src.core.dmx.universe import Universe
        dim_map = None  # lazy — nur bei Bedarf aufbauen
        finished = set()
        # LTP-Reihenfolge: in Start-Reihenfolge ticken — die zuletzt gestartete
        # Funktion schreibt zuletzt und gewinnt damit bei Kanal-Ueberschneidung
        # (z. B. zwei Effekte auf denselben Dimmer-/Farbkanal). Frueher wurde
        # ueber das ungeordnete _running_ids-Set iteriert -> nicht-deterministisches
        # Ueberschreiben. IDs, die (defensiv) nur im Set stehen, hinten anhaengen.
        # Tick-Reihenfolge unter Lock als Snapshot bilden: start()/stop() koennen
        # _start_order/_running_ids aus anderen Threads mutieren. Der Lock wird
        # NICHT waehrend der (potenziell langsamen) f.write()-Schleife gehalten.
        with self._lock:
            running = set(self._running_ids)
            ordered = [fid for fid in self._start_order if fid in running]
            if len(ordered) != len(running):
                ordered += [fid for fid in running
                            if fid not in self._start_order]
        for fid in ordered:
            f = self._functions.get(fid)
            if f is None or not f.is_running:
                finished.add(fid)
                continue
            try:
                inten = f.intensity
                try:
                    inten = max(0.0, min(1.0, float(inten)))
                except (TypeError, ValueError):
                    inten = 1.0
                if inten >= 0.999:
                    f.write(universes, patch_cache, dt, self._functions)
                else:
                    if dim_map is None:
                        dim_map = self._dim_addr_map(patch_cache)
                    # privates Universum je Universum = Kopie des aktuellen Scratch
                    priv: dict[int, Universe] = {}
                    before: dict[int, bytes] = {}
                    for u, su in universes.items():
                        cur = su.get_all()
                        pu = Universe(u)
                        pu.set_range(1, cur)
                        priv[u] = pu
                        before[u] = bytes(cur)
                    f.write(priv, patch_cache, dt, self._functions)
                    for u, pu in priv.items():
                        shared = universes.get(u)
                        if shared is None:
                            continue
                        after = pu.get_all()
                        b = before[u]
                        dims = dim_map.get(u, frozenset())
                        for i in range(512):
                            av = after[i]
                            if av == b[i]:
                                continue
                            if (i + 1) in dims:
                                av = int(av * inten)
                            shared.set_channel(i + 1, av if av < 255 else 255)
            except Exception as exc:
                print(f"[FunctionManager] tick error in function {fid}: {exc}")
            if not f.is_running:
                finished.add(fid)
        if finished:
            with self._lock:
                self._running_ids -= finished
                # _start_order mit _running_ids synchron halten: selbst-beendete
                # Funktionen (die nicht ueber stop() liefen) hier entfernen, damit
                # die Liste nicht mit stale-IDs volllaeuft.
                self._start_order = [fid for fid in self._start_order
                                     if fid in self._running_ids]

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
                    # EFX-Tag wird von EfxInstance (Pan/Tilt-Bewegung), LayeredEffect
                    # und Carousel geteilt. Unterscheidung anhand der Keys.
                    if fd.get("motion") or "speed_hz" in fd:
                        f = EfxInstance.from_dict(fd)
                    elif "layers" in fd:
                        f = LayeredEffect.from_dict(fd)
                    elif "pattern" in fd:
                        f = Carousel.from_dict(fd)
                    else:
                        continue
                elif ftype == FunctionType.RGBMatrix.value:
                    f = RgbMatrixInstance.from_dict(fd)
                else:
                    continue
            except Exception as exc:
                print(f"[FunctionManager] from_dict skip {ftype}: {exc}")
                continue
            # Per-Effekt-Master generisch laden (Block B) — eine Stelle statt in
            # jeder Subtyp-from_dict. Chaser/Sequence setzen speed schon selbst,
            # das ueberschreibt der gespeicherte Wert hier konsistent.
            try:
                f.intensity = max(0.0, min(1.0, float(fd.get("intensity", 1.0))))
            except (TypeError, ValueError):
                f.intensity = 1.0
            try:
                f.speed = max(0.1, min(4.0, float(fd.get("speed", f.speed))))
            except (TypeError, ValueError):
                pass
            # Bibliotheks-Ordner generisch laden (Phase 1). Fehlt = Wurzel.
            try:
                f.folder = str(fd.get("folder", "") or "")
            except (TypeError, ValueError):
                f.folder = ""
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
