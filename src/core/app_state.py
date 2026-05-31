"""Globaler App-State — hält Show-Daten und Engine-Referenzen zusammen."""
from __future__ import annotations
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from .database.models import Base, PatchedFixture
from .database.fixture_db import get_channels
from .dmx.universe import Universe
from .dmx.output_manager import OutputManager

SHOW_DB_PATH = "data/current_show.db"


class AppState:
    def __init__(self):
        self._show_engine = None
        self.output_manager = OutputManager()
        self.universes: dict[int, Universe] = {}
        self.programmer: dict[int, dict[str, int]] = {}
        # Visualizer-Persistenz — gehen mit in die .lshow (siehe show_file.py).
        # positions: {fid: (x, y, z)} ; active_stage_name: preset-key oder User-Stage-Name
        self.visualizer_positions: dict[int, tuple[float, float, float]] = {}
        self.active_stage_name: str = "simple"
        self._patch_cache: list[PatchedFixture] = []
        # Vorberechneter Render-Plan (bei Patch-Aenderung erneuert) fuer den
        # zentralen Per-Frame-Renderer _render_frame().
        self._fix_index: dict[int, tuple] = {}          # fid -> (fixture, channels)
        self._default_frame: dict[int, bytes] = {}      # univ -> 512B Default-Frame
        self._commit_spans: dict[int, list[tuple[int, int]]] = {}  # univ -> [(start,len)]
        self._patched_set: dict[int, frozenset] = {}    # univ -> {gepatchte Adressen}
        # Nicht-gepatchte Adressen, die Funktionen (z. B. ScriptFunction setdmx)
        # im letzten Frame geschrieben haben — fuer korrektes Freigeben.
        self._engine_extra_prev: dict[int, set] = {}
        self._callbacks: list = []
        self.mock_mode: bool = False
        # Cuelisten und Playback
        from .engine.cue_stack import CueStack
        self.cue_stacks: list[CueStack] = []
        self.playback_engine = None  # wird in start_playback() gesetzt
        # QLC+ Function Manager
        from .engine.function_manager import get_function_manager
        self.function_manager = get_function_manager()
        # Central MIDI mapping engine (singleton, bidirectional in/out).
        from .midi.midi_mapper import get_midi_mapper
        self.midi_mapper = get_midi_mapper(self)
        try:
            self.midi_mapper and self.midi_mapper.load("data/midi_mappings.json")
        except Exception:
            pass
        # Zentraler StateSync Event-Bus
        from .sync import get_sync
        self.sync = get_sync()

    # ── Show-Datenbank ────────────────────────────────────────────────────────

    def open_show(self, path: str = SHOW_DB_PATH):
        import os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._show_engine = create_engine(f"sqlite:///{path}", echo=False)
        Base.metadata.create_all(self._show_engine)
        self._reload_patch_cache()
        # Validierung + Auto-Repair beim Show-Laden
        try:
            from .sync import validate_and_repair, SyncEvent
            issues = validate_and_repair(self, fix=True)
            for issue in issues:
                print(f"[Validation] {issue}")
            self.sync.emit(SyncEvent.SHOW_LOADED, {"path": path, "issues": issues})
        except Exception as e:
            print(f"[AppState] validation on open_show failed: {e}")

    def _session(self) -> Session:
        return Session(self._show_engine)

    # ── Patch ─────────────────────────────────────────────────────────────────

    def get_patched_fixtures(self) -> list[PatchedFixture]:
        return list(self._patch_cache)

    def add_fixture(self, fixture: PatchedFixture, undoable: bool = True):
        # Save snapshot for undo BEFORE modifying
        snapshot = self._fixture_to_dict(fixture)
        with self._session() as s:
            s.add(fixture)
            s.commit()
        self._reload_patch_cache()
        self._emit("patch_changed")
        if undoable:
            self._push_undo(
                label=f"Fixture +{snapshot.get('label', '')}",
                do=lambda: None,   # already executed
                undo=lambda s=snapshot: self.remove_fixture(s["fid"], undoable=False),
                redo=lambda s=snapshot: self._restore_fixture_dict(s),
            )

    def remove_fixture(self, fid: int, undoable: bool = True):
        # Snapshot before delete
        snap = None
        for f in self._patch_cache:
            if f.fid == fid:
                snap = self._fixture_to_dict(f)
                break
        with self._session() as s:
            from sqlalchemy import select, delete
            s.execute(delete(PatchedFixture).where(PatchedFixture.fid == fid))
            s.commit()
        self.programmer.pop(fid, None)
        self._reload_patch_cache()
        self._emit("patch_changed")
        if undoable and snap is not None:
            self._push_undo(
                label=f"Fixture -{snap.get('label', '')}",
                do=lambda: None,
                undo=lambda s=snap: self._restore_fixture_dict(s),
                redo=lambda fid=fid: self.remove_fixture(fid, undoable=False),
            )

    def update_fixture(self, fid: int, undoable: bool = True, **changes) -> bool:
        allowed = {
            "label", "fixture_profile_id", "mode_name", "universe",
            "address", "channel_count", "manufacturer_name",
            "fixture_name", "fixture_type", "invert_pan",
            "invert_tilt", "swap_pan_tilt", "dimmer_curve",
        }
        values = {k: v for k, v in changes.items() if k in allowed}
        if not values:
            return False

        before = None
        for f in self._patch_cache:
            if f.fid == fid:
                before = self._fixture_to_dict(f)
                break
        if before is None:
            return False

        # Normalize common numeric fields to stable types for DB + compare.
        for key in ("fixture_profile_id", "universe", "address", "channel_count"):
            if key in values:
                values[key] = int(values[key])

        changed = any(before.get(k) != values.get(k) for k in values.keys())
        if not changed:
            return False

        from sqlalchemy import update
        with self._session() as s:
            s.execute(
                update(PatchedFixture)
                .where(PatchedFixture.fid == fid)
                .values(**values)
            )
            s.commit()
        self._reload_patch_cache()
        self._emit("patch_changed")

        if undoable:
            after = dict(before)
            after.update(values)
            self._push_undo(
                label=f"Fixture ~{before.get('label', '')}",
                do=lambda: None,
                undo=lambda b=before: self.update_fixture(fid, undoable=False, **b),
                redo=lambda a=after: self.update_fixture(fid, undoable=False, **a),
            )
        return True

    def _fixture_to_dict(self, f: PatchedFixture) -> dict:
        return {
            "fid": f.fid,
            "label": f.label,
            "fixture_profile_id": f.fixture_profile_id,
            "mode_name": f.mode_name,
            "universe": f.universe,
            "address": f.address,
            "channel_count": f.channel_count,
            "invert_pan": f.invert_pan,
            "invert_tilt": f.invert_tilt,
            "swap_pan_tilt": f.swap_pan_tilt,
            "dimmer_curve": f.dimmer_curve,
            "manufacturer_name": f.manufacturer_name,
            "fixture_name": f.fixture_name,
            "fixture_type": f.fixture_type,
        }

    def _restore_fixture_dict(self, d: dict):
        f = PatchedFixture(
            fid=d["fid"], label=d.get("label", ""),
            fixture_profile_id=d.get("fixture_profile_id", 0),
            mode_name=d.get("mode_name", ""),
            universe=d.get("universe", 1),
            address=d.get("address", 1),
            channel_count=d.get("channel_count", 1),
            invert_pan=d.get("invert_pan", False),
            invert_tilt=d.get("invert_tilt", False),
            swap_pan_tilt=d.get("swap_pan_tilt", False),
            dimmer_curve=d.get("dimmer_curve", "linear"),
            manufacturer_name=d.get("manufacturer_name", ""),
            fixture_name=d.get("fixture_name", ""),
            fixture_type=d.get("fixture_type", "other"),
        )
        self.add_fixture(f, undoable=False)

    def _push_undo(self, label, do, undo, redo=None):
        try:
            from .undo import get_undo_stack, Command
            get_undo_stack().push(
                Command(label=label, do=do, undo=undo, redo=redo),
                execute=False,
            )
        except Exception as e:
            print(f"[AppState] undo push error: {e}")

    def _reload_patch_cache(self):
        if not self._show_engine:
            return
        from sqlalchemy import select
        with self._session() as s:
            self._patch_cache = list(
                s.execute(select(PatchedFixture).order_by(PatchedFixture.fid)).scalars()
            )
        self._rebuild_universes()
        clear_channel_cache()
        self._rebuild_render_plan()

    def _rebuild_render_plan(self):
        """Berechnet aus dem Patch die Strukturen fuer den Per-Frame-Renderer:
        Default-Frame (gepatchte Kanaele auf Default), fid->Kanal-Index und die
        zusammenhaengenden Adress-Spans, die pro Frame committed werden."""
        fix_index: dict[int, tuple] = {}
        defaults: dict[int, bytearray] = {}
        addrs: dict[int, set] = {}
        for fx in self._patch_cache:
            chans = get_channels_for_patched(fx)
            fix_index[fx.fid] = (fx, chans)
            for ch in chans:
                addr = fx.address + ch.channel_number - 1
                if not (1 <= addr <= 512):
                    continue
                dv = ch.default_value
                try:
                    dv = int(dv) if dv is not None else 0
                except (TypeError, ValueError):
                    dv = 0
                defaults.setdefault(fx.universe, bytearray(512))[addr - 1] = max(0, min(255, dv))
                addrs.setdefault(fx.universe, set()).add(addr)
        # Adressen pro Universe zu zusammenhaengenden Spans zusammenfassen
        spans: dict[int, list[tuple[int, int]]] = {}
        for univ, aset in addrs.items():
            ordered = sorted(aset)
            runs: list[tuple[int, int]] = []
            start = prev = ordered[0]
            for a in ordered[1:]:
                if a == prev + 1:
                    prev = a
                else:
                    runs.append((start, prev - start + 1))
                    start = prev = a
            runs.append((start, prev - start + 1))
            spans[univ] = runs
        self._fix_index = fix_index
        self._default_frame = {u: bytes(b) for u, b in defaults.items()}
        self._commit_spans = spans
        self._patched_set = {u: frozenset(s) for u, s in addrs.items()}
        self._engine_extra_prev = {}

    def _rebuild_universes(self):
        needed = {f.universe for f in self._patch_cache} or {1}
        for u in needed:
            if u not in self.universes:
                self.universes[u] = self.output_manager.add_universe(u)

    def auto_patch_fixtures(self):
        """Weist allen Fixtures aufeinander folgende Adressen zu."""
        from sqlalchemy import update
        from .database.models import PatchedFixture as PF
        addr = 1
        univ = 1
        with self._session() as s:
            for f in sorted(self._patch_cache, key=lambda x: x.fid):
                if addr + f.channel_count - 1 > 512:
                    univ += 1
                    addr = 1
                s.execute(
                    update(PF).where(PF.fid == f.fid).values(
                        universe=univ, address=addr
                    )
                )
                addr += f.channel_count
            s.commit()
        self._reload_patch_cache()
        self._emit("patch_changed")

    def next_fid(self) -> int:
        if not self._patch_cache:
            return 1
        return max(f.fid for f in self._patch_cache) + 1

    def check_address_conflict(self, universe: int, address: int, channel_count: int,
                               exclude_fid: int = -1) -> list[int]:
        conflicts = []
        for f in self._patch_cache:
            if f.fid == exclude_fid or f.universe != universe:
                continue
            my_end = address + channel_count - 1
            their_end = f.address + f.channel_count - 1
            if address <= their_end and my_end >= f.address:
                conflicts.append(f.fid)
        return conflicts

    # ── Programmer ────────────────────────────────────────────────────────────

    def set_programmer_value(self, fid: int, attribute: str, value: int,
                             undoable: bool = False):
        old = self.programmer.get(fid, {}).get(attribute, None)
        if fid not in self.programmer:
            self.programmer[fid] = {}
        self.programmer[fid][attribute] = max(0, min(255, value))
        self._flush_programmer_to_dmx(fid)
        self._emit("programmer_changed", fid)
        if undoable and old != self.programmer[fid][attribute]:
            new_val = self.programmer[fid][attribute]
            self._push_undo(
                label=f"Programmer FID{fid}.{attribute}={new_val}",
                do=lambda: None,
                undo=lambda f=fid, a=attribute, v=old: (
                    self.set_programmer_value(f, a, v, undoable=False)
                    if v is not None
                    else self._clear_programmer_attr(f, a)),
                redo=lambda f=fid, a=attribute, v=new_val:
                    self.set_programmer_value(f, a, v, undoable=False),
            )

    def _clear_programmer_attr(self, fid: int, attribute: str):
        if fid in self.programmer:
            self.programmer[fid].pop(attribute, None)
            if not self.programmer[fid]:
                self.programmer.pop(fid, None)
            self._flush_programmer_to_dmx(fid)
            self._emit("programmer_changed", fid)

    def clear_programmer(self, fid: int | None = None):
        if fid is None:
            self.programmer.clear()
        else:
            self.programmer.pop(fid, None)
        self._flush_all_to_dmx()
        self._emit("programmer_changed", None)

    def get_programmer_value(self, fid: int, attribute: str) -> int | None:
        return self.programmer.get(fid, {}).get(attribute)

    def _flush_programmer_to_dmx(self, fid: int):
        fixture = next((f for f in self._patch_cache if f.fid == fid), None)
        if not fixture or fixture.universe not in self.universes:
            return
        universe = self.universes[fixture.universe]
        prog = self.programmer.get(fid, {})
        channels = get_channels_for_patched(fixture)
        for ch in channels:
            val = prog.get(ch.attribute, ch.default_value)
            dmx_addr = fixture.address + ch.channel_number - 1
            if 1 <= dmx_addr <= 512:
                universe.set_channel(dmx_addr, val)

    def _flush_all_to_dmx(self):
        for f in self._patch_cache:
            self._flush_programmer_to_dmx(f.fid)

    # ── Events ────────────────────────────────────────────────────────────────

    def subscribe(self, callback):
        self._callbacks.append(callback)

    # ── Playback ──────────────────────────────────────────────────────────────

    def start_playback(self):
        from .engine.executor import PlaybackEngine
        self.playback_engine = PlaybackEngine(self)
        self.playback_engine.start()
        # EIN zentraler Renderer im 44-Hz-Output-Loop (ersetzt den frueheren
        # zweiten PlaybackEngine-Thread) — behebt Tearing + haengende Werte.
        self.output_manager.add_tick_callback(self._render_frame)

    # ── Zentraler Per-Frame-Renderer ──────────────────────────────────────────

    def _render_frame(self, dt: float):
        """Berechnet jeden Output-Frame komplett neu (ein Thread):
        Default → Funktionen → Executoren → Programmer, dann atomarer Commit
        der gepatchten Kanaele ins Live-Universe. Nicht gepatchte Kanaele
        (SimpleDesk/OSC-Roh/Input-Merge) bleiben unberuehrt."""
        # Snapshots: dieser Renderer laeuft im Output-Thread, waehrend UI-/MIDI-/
        # RX-Threads programmer/universes mutieren (set_programmer_value,
        # Input-Merge legt Universen an). Iteration ueber Live-Dicts wuerde sonst
        # "dict changed size during iteration" werfen.
        live_universes = list(self.universes.items())
        programmer = {fid: dict(attrs)
                      for fid, attrs in list(self.programmer.items())}
        # 1. Scratch-Universen mit Default-Frame vorbelegen (= Per-Frame-Clear).
        scratch: dict[int, Universe] = {}
        for univ, _live in live_universes:
            su = Universe(univ)
            base = self._default_frame.get(univ)
            if base:
                su.set_range(1, base)
            scratch[univ] = su
        # 2. Funktionen rendern in die Scratch-Universen.
        try:
            self.function_manager.tick(scratch, self._patch_cache, dt)
        except Exception as exc:
            print(f"[AppState] render functions error: {exc}")
        # 3. Executoren (Cue-Playback) darueber.
        if self.playback_engine is not None:
            try:
                self._apply_fixture_map(scratch, self.playback_engine.compute_merged())
            except Exception as exc:
                print(f"[AppState] render executors error: {exc}")
        # 4. Programmer hat hoechste Prioritaet (LTP).
        self._apply_fixture_map(scratch, programmer)
        # 5. Atomarer Commit der gepatchten Spans ins Live-Universe.
        for univ, live in live_universes:
            su = scratch.get(univ)
            if su is None:
                continue
            data = su.get_all()
            for start, length in self._commit_spans.get(univ, ()):
                live.set_range(start, data[start - 1:start - 1 + length])
            # Roh-Kanaele, die Funktionen (z. B. ScriptFunction setdmx) auf NICHT
            # gepatchte Adressen geschrieben haben, ebenfalls committen — und
            # zuvor geschriebene, jetzt nicht mehr aktive, wieder freigeben (0).
            patched = self._patched_set.get(univ, frozenset())
            cur = {a for a in range(1, 513) if a not in patched and data[a - 1] != 0}
            prev = self._engine_extra_prev.get(univ)
            if cur or prev:
                for a in cur:
                    live.set_channel(a, data[a - 1])
                if prev:
                    for a in prev - cur:
                        live.set_channel(a, 0)
                self._engine_extra_prev[univ] = cur

    def _apply_fixture_map(self, scratch: dict, fixmap: dict):
        """Malt eine {fid: {attr: val}}-Schicht in die Scratch-Universen (LTP:
        nur vorhandene Attribute ueberschreiben, Rest bleibt aus tieferer Schicht)."""
        for fid, attrs in fixmap.items():
            try:
                entry = self._fix_index.get(int(fid))
            except (TypeError, ValueError):
                continue
            if not entry:
                continue
            fx, chans = entry
            su = scratch.get(fx.universe)
            if su is None:
                continue
            for ch in chans:
                if ch.attribute not in attrs:
                    continue
                addr = fx.address + ch.channel_number - 1
                if not (1 <= addr <= 512):
                    continue
                v = attrs[ch.attribute]
                try:
                    v = int(v)
                except (TypeError, ValueError):
                    v = 0
                su.set_channel(addr, max(0, min(255, v)))

    def new_cue_stack(self, name: str = "Neue Cueliste"):
        from .engine.cue_stack import CueStack
        stack = CueStack(name)
        self.cue_stacks.append(stack)
        self._emit("stacks_changed", None)
        return stack

    def remove_cue_stack(self, stack):
        self.cue_stacks.remove(stack)
        self._emit("stacks_changed", None)

    def record_cue(self, stack, number: float, label: str = "",
                   fade_in: float = 2.0, fade_out: float = 0.0):
        """Speichert aktuellen Programmer-Inhalt als neue Cue."""
        from .engine.cue import Cue
        values = {fid: dict(attrs) for fid, attrs in self.programmer.items()}
        cue = Cue(number=number, label=label, fade_in=fade_in,
                  fade_out=fade_out, values=values)
        stack.add_cue(cue)
        self._emit("cue_recorded", (stack, cue))
        return cue

    def _emit(self, event: str, data=None):
        """Emit auf Legacy-Callbacks UND auf neuen StateSync routen."""
        # Legacy callbacks
        for cb in self._callbacks:
            try:
                cb(event, data)
            except Exception:
                pass
        # Neue zentrale Sync-Routing
        try:
            from .sync import SyncEvent
            try:
                ev = SyncEvent(event)
            except ValueError:
                return  # Unbekanntes Event -> ignorieren (kein Crash)
            self.sync.emit(ev, data)
        except Exception:
            pass


# Cache: (profile_id, mode_name, channel_count) -> list[FixtureChannel] (detached).
# Ohne Cache macht get_channels_for_patched pro Fixture pro Frame (44 Hz) eine
# neue DB-Session — viel zu teuer fuer den zentralen Per-Frame-Renderer.
_channel_cache: dict = {}


def clear_channel_cache():
    """Invalidiert den Channel-Cache (bei jeder Patch-Aenderung aufrufen)."""
    _channel_cache.clear()


def get_channels_for_patched(fixture: PatchedFixture):
    """Laedt die Channel-Objekte fuer ein gepatchtes Geraet (gecached).
    Fallback: Wenn der exakte Mode-Name nicht existiert, wird der erste Mode
    des Profils mit passender Kanalanzahl verwendet (oder einfach der erste).
    """
    key = (getattr(fixture, "fixture_profile_id", None),
           getattr(fixture, "mode_name", None),
           getattr(fixture, "channel_count", None))
    cached = _channel_cache.get(key)
    if cached is not None:
        return cached
    from sqlalchemy import select
    from .database.fixture_db import engine
    from .database.models import FixtureMode, FixtureChannel
    with Session(engine()) as s:
        # 1. Versuch: exakter Match
        mode = s.execute(
            select(FixtureMode)
            .where(FixtureMode.fixture_id == fixture.fixture_profile_id)
            .where(FixtureMode.name == fixture.mode_name)
        ).scalar_one_or_none()

        # 2. Fallback: Mode mit passender Kanalanzahl
        if not mode:
            mode = s.execute(
                select(FixtureMode)
                .where(FixtureMode.fixture_id == fixture.fixture_profile_id)
                .where(FixtureMode.channel_count == fixture.channel_count)
            ).scalar_one_or_none()

        # 3. Fallback: irgendein Mode des Profils
        if not mode:
            mode = s.execute(
                select(FixtureMode)
                .where(FixtureMode.fixture_id == fixture.fixture_profile_id)
                .order_by(FixtureMode.id)
            ).scalars().first()

        if not mode:
            _channel_cache[key] = []
            return []

        result = s.execute(
            select(FixtureChannel)
            .where(FixtureChannel.mode_id == mode.id)
            .order_by(FixtureChannel.channel_number)
        ).scalars().all()
        s.expunge_all()
        _channel_cache[key] = result
        return result


# Singleton
_state: AppState | None = None


def get_state() -> AppState:
    global _state
    if _state is None:
        _state = AppState()
        _state.open_show()
        _state.output_manager.start()
        _state.start_playback()
    return _state
