"""Globaler App-State — hält Show-Daten und Engine-Referenzen zusammen."""
from __future__ import annotations
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from .database.models import Base, PatchedFixture
from .database.fixture_db import get_channels
from .dmx.universe import Universe
from .dmx.output_manager import OutputManager

SHOW_DB_PATH = "data/current_show.db"

# Attribut-Klassen fuer den multiplikativen Dimmer-Layer (EE-02). Wird ein
# dedizierter Dimmer/Intensitaets-Kanal gefunden, skaliert der Dimmer-Master nur
# diesen (kein Doppel-Dimmen); sonst die Farbkanaele. Pan/Tilt/Gobo bleiben unberuehrt.
_DIM_INTENSITY_ATTRS = frozenset({"intensity", "dimmer", "master"})
_DIM_COLOR_ATTRS = frozenset({
    "color_r", "color_g", "color_b", "color_w", "color_a", "color_uv",
    "red", "green", "blue", "white", "amber", "uv",
    "cyan", "magenta", "yellow",
})


class AppState:
    def __init__(self):
        self._show_engine = None
        self.output_manager = OutputManager()
        self.universes: dict[int, Universe] = {}
        self.programmer: dict[int, dict[str, int]] = {}
        # Gemeinsame Programmer-Geraeteauswahl (Reihenfolge = Auswahl-Reihenfolge).
        # Wird vom ProgrammerView gesetzt; alle Kategorien (RGB Matrix, Effekte,
        # Paletten …) lesen sie. Nicht persistiert. Siehe docs/PROGRAMMER_REBUILD.md
        # (REVISION, Phase R1).
        self.selected_fids: list[int] = []
        # Aktive Gruppen-ID im Programmer (None = lose Einzel-/Mehrfachauswahl).
        # Wird VOR set_selected_fids gesetzt, damit die Matrix beim SELECTION_CHANGED
        # bereits die korrekte Gruppen-ID vorfindet.
        self.selected_group_id: int | None = None
        # Visualizer-Persistenz — gehen mit in die .lshow (siehe show_file.py).
        # positions: {fid: (x, y, z)} ; active_stage_name: preset-key oder User-Stage-Name
        self.visualizer_positions: dict[int, tuple[float, float, float]] = {}
        self.active_stage_name: str = "simple"
        # Live-View-Positionen (2D, {fid: (x, y)}) — eigene Persistenz, entkoppelt
        # vom 3D-Visualizer. Migration aus visualizer_positions beim Laden, falls leer.
        self.live_view_positions: dict[int, tuple[float, float]] = {}
        self._patch_cache: list[PatchedFixture] = []
        # Basis-Level pro Fixture: {fid: {attr: 0-255}}. Wird in den Default-Frame
        # gelegt (siehe _rebuild_render_plan) und mit der Show gespeichert. Typisch:
        # PAR-Grundhelligkeit, damit eine reine Farbe sofort sichtbar ist.
        self.base_levels: dict[int, dict[str, int]] = {}
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
        # Multiplikative Dimmer-Master (EE-02), wirken NACH dem Effekt-Layer:
        #   submaster_level — globaler Faktor (VC-Submaster-Fader)
        #   fixture_dimmers — pro Fixture (Gruppen-Dimmer löst auf fids auf)
        # Programmer-Dimmer multipliziert Effekte zusätzlich, statt sie per LTP
        # zu ersetzen (siehe _render_frame).
        self.submaster_level: float = 1.0
        self.fixture_dimmers: dict[int, float] = {}
        # EFX-/RGB-Matrix-Effekt-Instanzen — Single Source of Truth.
        # EfxView und RgbMatrixView lesen/schreiben direkt diese Listen
        # (gemeinsame Referenz), show/show_file.py persistiert sie in der .lshow.
        # Beim Show-Laden werden sie IN-PLACE ersetzt (Slice-Assignment), damit
        # die in den Views gehaltenen Referenzen gueltig bleiben.
        self._efx_instances: list = []
        self._rgb_matrix_instances: list = []
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
        # Basis-Level (z. B. PAR-Grundhelligkeit) in den Default-Frame legen:
        # Damit sind Fixtures "scharf" — eine reine Farbe (color-only) ist sofort
        # sichtbar, und ein Dimmer-Effekt UEBERSCHREIBT die Basis (kann bis 0
        # dunkeln). Ohne Basis muesste jede Farbe zusaetzlich Intensitaet setzen,
        # was mit Dimmer-Effekten kollidiert (s. docs/PROGRAMMER_REBUILD.md).
        for fid_raw, attrs in (getattr(self, "base_levels", None) or {}).items():
            try:
                fid = int(fid_raw)
            except (TypeError, ValueError):
                continue
            entry = fix_index.get(fid)
            if not entry or not isinstance(attrs, dict):
                continue
            fx, chans = entry
            buf = defaults.setdefault(fx.universe, bytearray(512))
            for ch in chans:
                aname = getattr(ch, "attribute", "") or ""
                if aname in attrs:
                    addr = fx.address + ch.channel_number - 1
                    if 1 <= addr <= 512:
                        try:
                            buf[addr - 1] = max(0, min(255, int(attrs[aname])))
                        except (TypeError, ValueError):
                            pass
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

    def apply_output_config(self, path: str = "data/universes.json"):
        """Liest die im Universe-Manager gespeicherte Output-Konfiguration und
        richtet beim Start die passenden Backends (Enttec/ArtNet/sACN) ein.

        Format pro Zeile: {"num", "name", "output", "patch"}.
        - Enttec: ``patch`` = COM-Port
        - ArtNet: ``patch`` = Ziel-IP/Broadcast (leer = Default-Broadcast)
        - sACN:   ``patch`` = Unicast-IP (leer = Multicast)
        Fehler pro Universe werden geloggt, brechen den Start aber nicht ab.
        """
        import json
        import os
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                rows = json.load(f)
        except Exception as e:
            print(f"[app_state] apply_output_config: konnte {path} nicht lesen: {e}")
            return
        for r in rows or []:
            try:
                num = int(r.get("num", 1))
            except (TypeError, ValueError):
                continue
            output = (r.get("output") or "Disabled").strip()
            patch = (r.get("patch") or "").strip()
            if num not in self.universes:
                self.universes[num] = self.output_manager.add_universe(num)
            try:
                if output == "Enttec" and patch:
                    self.output_manager.add_enttec(num, patch)
                elif output == "ArtNet":
                    self.output_manager.add_artnet(num, patch or "255.255.255.255")
                elif output == "sACN":
                    self.output_manager.add_sacn(num, patch or None)
            except Exception as e:
                print(f"[app_state] apply_output_config: Universe {num} "
                      f"({output}) fehlgeschlagen: {e}")

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

    # ── Gemeinsame Geraeteauswahl (R1) ─────────────────────────────────────────

    def set_selected_fids(self, fids: list[int]):
        """Setzt die gemeinsame Programmer-Auswahl und benachrichtigt alle
        Kategorien (RGB Matrix, Effekte, Paletten …) via SELECTION_CHANGED.
        Reihenfolge bleibt erhalten (wichtig fuer Fan/Chase)."""
        new = [int(f) for f in fids]
        if new == self.selected_fids:
            return
        self.selected_fids = new
        try:
            from .sync import SyncEvent
            self.sync.emit(SyncEvent.SELECTION_CHANGED, list(new))
        except Exception as e:
            print(f"[app_state] selection emit error: {e}")

    def get_selected_fids(self) -> list[int]:
        return list(self.selected_fids)

    def set_selected_group_id(self, gid: int | None):
        """Merkt die aktuell im Programmer gewaehlte Gruppe (oder None bei loser
        Auswahl). Die Matrix nutzt das, um das echte 2D-Grid inkl. Luecken zu uebernehmen."""
        self.selected_group_id = int(gid) if gid is not None else None

    def get_selected_group_id(self):
        return getattr(self, "selected_group_id", None)

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
        # 2b. Welche Fixtures treibt der EFFEKT-Layer (Funktionen) auf ihren
        #     Intensitaets-Kanaelen? Basis fuer Programmer-Multiply (EE-02).
        #     Bewusst VOR den Executoren erfasst: Cues behalten LTP-Ersatz durch
        #     den Programmer, nur laufende Effekte werden multipliziert.
        inten_addrs: dict[int, list[int]] = {}
        effect_present: dict[int, bool] = {}
        for fidi, entry in self._fix_index.items():
            fx, chans = entry
            addrs = self._fixture_intensity_addrs(fx, chans)
            inten_addrs[fidi] = addrs
            su = scratch.get(fx.universe)
            if su is None:
                effect_present[fidi] = False
                continue
            base = self._default_frame.get(fx.universe)
            present = False
            for a in addrs:
                dv = base[a - 1] if (base and a - 1 < len(base)) else 0
                if su.get_channel(a) != dv:
                    present = True
                    break
            effect_present[fidi] = present
        # 3. Executoren (Cue-Playback) darueber.
        if self.playback_engine is not None:
            try:
                self._apply_fixture_map(scratch, self.playback_engine.compute_merged())
            except Exception as exc:
                print(f"[AppState] render executors error: {exc}")

        # 4. Programmer (LTP, hoechste Prioritaet) — ABER Intensitaets-Attribute
        #    multiplizieren einen laufenden EFFEKT, statt ihn zu ersetzen
        #    (EE-02 "Programmer-Dimmer multipliziert"). Ohne Effekt: LTP-Ersatz.
        prog_factor: dict[int, float] = {}
        for fid, attrs in programmer.items():
            try:
                fidi = int(fid)
            except (TypeError, ValueError):
                continue
            if not effect_present.get(fidi):
                continue
            for ikey in _DIM_INTENSITY_ATTRS:
                if ikey in attrs:
                    try:
                        f = max(0.0, min(1.0, int(attrs[ikey]) / 255.0))
                    except (TypeError, ValueError):
                        continue
                    prog_factor[fidi] = min(prog_factor.get(fidi, 1.0), f)
        self._apply_fixture_map(scratch, programmer, skip_intensity_for=set(prog_factor))

        # 4b. Multiplikativer Dimmer-Master: submaster * Gruppen-/Fixture-Dimmer *
        #     Programmer-Dimmer (nur wo Effekt aktiv). Skaliert pro Fixture die
        #     Intensitaets- bzw. (ersatzweise) Farbkanaele.
        submaster = 1.0
        om = getattr(self, "output_manager", None)
        if om is not None and hasattr(om, "effective_submaster"):
            try:
                submaster = om.effective_submaster()
            except Exception:
                submaster = 1.0
        fixture_dimmers = getattr(self, "fixture_dimmers", {}) or {}
        global_sub = max(0.0, min(1.0, float(getattr(self, "submaster_level", 1.0)))) * submaster
        for fidi, addrs in inten_addrs.items():
            factor = global_sub * float(fixture_dimmers.get(fidi, 1.0)) * prog_factor.get(fidi, 1.0)
            if factor >= 0.999 or not addrs:
                continue
            entry = self._fix_index.get(fidi)
            if not entry:
                continue
            su = scratch.get(entry[0].universe)
            if su is None:
                continue
            for a in addrs:
                su.set_channel(a, int(su.get_channel(a) * factor))

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

    def _apply_fixture_map(self, scratch: dict, fixmap: dict,
                           skip_intensity_for: set | None = None):
        """Malt eine {fid: {attr: val}}-Schicht in die Scratch-Universen (LTP:
        nur vorhandene Attribute ueberschreiben, Rest bleibt aus tieferer Schicht).

        skip_intensity_for: fids, fuer die Intensitaets-Attribute NICHT absolut
        geschrieben werden (sie werden stattdessen multiplikativ angewandt, EE-02)."""
        skip = skip_intensity_for or ()
        for fid, attrs in fixmap.items():
            try:
                fidi = int(fid)
            except (TypeError, ValueError):
                continue
            entry = self._fix_index.get(fidi)
            if not entry:
                continue
            fx, chans = entry
            su = scratch.get(fx.universe)
            if su is None:
                continue
            skip_inten = fidi in skip
            for ch in chans:
                if ch.attribute not in attrs:
                    continue
                if skip_inten and (ch.attribute or "").lower() in _DIM_INTENSITY_ATTRS:
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

    # ── Dimmer-Master API (EE-02) ──────────────────────────────────────────────

    def set_fixture_dimmer(self, fid: int, factor: float):
        """Setzt den multiplikativen Dimmer-Faktor (0.0–1.0) eines Fixtures.
        1.0 = voll (Eintrag wird entfernt, damit kein unnoetiges Skalieren)."""
        try:
            fid = int(fid)
            factor = max(0.0, min(1.0, float(factor)))
        except (TypeError, ValueError):
            return
        if factor >= 0.999:
            self.fixture_dimmers.pop(fid, None)
        else:
            self.fixture_dimmers[fid] = factor

    def set_group_dimmer(self, fids, factor: float):
        """Setzt denselben Dimmer-Faktor fuer mehrere Fixtures (Gruppen-Dimmer)."""
        for fid in fids or ():
            self.set_fixture_dimmer(fid, factor)

    def _fixture_intensity_addrs(self, fx, chans) -> list[int]:
        """Adressen, die der Dimmer-Master fuer dieses Fixture skaliert: der
        Dimmer/Intensitaets-Kanal falls vorhanden (virtueller Dimmer), sonst die
        Farbkanaele. Pan/Tilt/Gobo etc. werden nie skaliert."""
        inten: list[int] = []
        color: list[int] = []
        for ch in chans:
            attr = (getattr(ch, "attribute", "") or "").lower()
            addr = fx.address + ch.channel_number - 1
            if not (1 <= addr <= 512):
                continue
            if attr in _DIM_INTENSITY_ATTRS:
                inten.append(addr)
            elif attr in _DIM_COLOR_ATTRS:
                color.append(addr)
        return inten if inten else color

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
        _state.apply_output_config()
        _state.output_manager.start()
        _state.start_playback()
    return _state
