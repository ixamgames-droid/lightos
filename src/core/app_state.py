"""Globaler App-State — hält Show-Daten und Engine-Referenzen zusammen."""
from __future__ import annotations
import os
import threading
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from .database.models import PatchedFixture, create_all_idempotent
from .database.fixture_db import get_channels
from .dmx.universe import Universe
from .dmx.output_manager import OutputManager
from .debug_log import debug_swallow
from .attr_groups import ATTR_GROUPS

# Show-Datenbank. Per LIGHTOS_SHOW_DB umlenkbar — so können Tests (conftest setzt
# eine Temp-DB) laufen, ohne die echte Show-DB der laufenden App anzufassen.
SHOW_DB_PATH = os.environ.get("LIGHTOS_SHOW_DB", "data/current_show.db")

# Echte Dimmer-/Intensitaets-Kanaele. Dieser Sentinel ist mehrfach load-bearing:
#   (a) Grand-Master + EE-02 skalieren NUR diese Kanaele (kein Doppel-Dimmen; sonst
#       die Farbkanaele); Pan/Tilt/Gobo bleiben unberuehrt.
#   (b) er entscheidet, ob ein Fixture als "Programmer-Dimmer gesetzt" gilt und damit
#       die implizite Grundhelligkeit (4a²) ueberspringt.
#   (c) ob ein Cue den Dimmer besitzt (exec_dimmer_fids).
# BEWUSST OHNE shutter/strobe, obwohl attr_groups diese dem "Intensity"-Tab zuordnet:
# der Grand Master darf einen Strobe nicht herunterdimmen, und 4a² soll nur am
# ECHTEN Dimmer entfallen (Shutter/Strobe oeffnen ist kein Helligkeitswert).
# Aus der kanonischen attr_groups-"Intensity"-Gruppe ABGELEITET (eine Quelle, kein
# Drift mehr): genau diese Gruppe MINUS shutter/strobe. Die Beziehung lockt
# tests/test_dim_intensity_sentinel.py -> aendert jemand attr_groups, schlaegt er an.
_DIM_INTENSITY_ATTRS = frozenset(ATTR_GROUPS["Intensity"]) - frozenset({"shutter", "strobe"})
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
        # Schuetzt jeden Lese-/Schreibzugriff auf self.programmer. Der MIDI-/OSC-/
        # Web-Thread mutiert den Programmer (set_programmer_value), waehrend der
        # Output-Thread im _render_frame einen Snapshot zieht — ohne Lock drohte
        # "dict changed size during iteration". RLock, damit re-entrante Aufrufe
        # (z. B. ueber Undo) nicht selbst-blockieren.
        self._prog_lock = threading.RLock()
        # Marshalling von Event-Callbacks in den Qt-UI-Thread (vom MainWindow per
        # set_ui_marshaller gesetzt). Ohne dieses Marshalling wuerden Worker-
        # Threads (MIDI/OSC/Audio) ueber _emit direkt Qt-Widgets anfassen → Crash.
        self._ui_marshaller = None
        self._ui_thread_id: int | None = None
        # BUG-01: Solange True, unterdrückt _emit() alle State-Events. Wird beim
        # Bulk-Patch-Ersatz (_replace_patch_from_data in show_file) gesetzt, damit
        # add_fixture() nicht 1×/Fixture re-entrant patch_changed feuert; der
        # Aufrufer macht danach EINEN gebündelten Refresh.
        self._suppress_emits: bool = False
        # Gemeinsame Programmer-Geraeteauswahl (Reihenfolge = Auswahl-Reihenfolge).
        # Wird vom ProgrammerView gesetzt; alle Kategorien (RGB Matrix, Effekte,
        # Paletten …) lesen sie. Nicht persistiert. Siehe docs/PROGRAMMER_REBUILD.md
        # (REVISION, Phase R1).
        self.selected_fids: list[int] = []
        # Aktive Gruppen-ID im Programmer (None = lose Einzel-/Mehrfachauswahl).
        # Wird VOR set_selected_fids gesetzt, damit die Matrix beim SELECTION_CHANGED
        # bereits die korrekte Gruppen-ID vorfindet.
        self.selected_group_id: int | None = None
        # ENG-02: Aktiver Programmer-Tab ("Intensity"/"Color"/"Matrix"/…). Entscheidet
        # bei Dimmer-Konflikten, WER den Dimmer einer SELEKTIERTEN Lampe besitzt: auf
        # dem Intensity-Tab gewinnt die manuelle Programmer-Intensitaet, sonst die
        # Funktion (Dimmer-Matrix/EFX). Von der ProgrammerView (_main_tabs) gesetzt;
        # None = kein Fokus -> Funktion besitzt einen direkt getriebenen Dimmer
        # (Default). Wird nur lesend im Output-Thread benutzt -> einfaches Attribut.
        self.programmer_focus: str | None = None
        # Visualizer-Persistenz — gehen mit in die .lshow (siehe show_file.py).
        # positions: {fid: (x, y, z)} ; active_stage_name: preset-key oder User-Stage-Name
        self.visualizer_positions: dict[int, tuple[float, float, float]] = {}
        # Multi-Achsen-Ausrichtung (rx, ry, rz) in GRAD je Fixture im 3D-Visualizer:
        # rx = Kippen (Pitch, Boden->Decke), ry = Drehen um die Hochachse (Yaw),
        # rz = Roll. Getrennt von positions. Abwaertskompatibel zu Alt-Shows, die
        # nur einen Y-Float gespeichert haben (siehe coords.normalize_rotation +
        # show_file.load_show). Erlaubt spaeter MH-Auto-Aim (volle Montage-Lage).
        self.visualizer_rotations: dict[int, tuple[float, float, float]] = {}
        # Andock-Beziehungen: {fid: stage_element_id} — Strahler haengt an/auf
        # diesem Buehnen-Element (Trasse/Plattform/Boden). Bewegt sich das
        # Element, wandert der Strahler mit. Geht mit in die .lshow.
        self.visualizer_docks: dict[int, str] = {}
        self.active_stage_name: str = "simple"
        # Live-View-Positionen (2D, {fid: (x, y)}) — eigene Persistenz, entkoppelt
        # vom 3D-Visualizer. Migration aus visualizer_positions beim Laden, falls leer.
        self.live_view_positions: dict[int, tuple[float, float]] = {}
        # P4: Show-spezifische Live-View-Einstellungen (zoom, grid_size, snap,
        # grid_visible, world_w/h) — von der Live View gepflegt, wandert mit
        # save_show/load_show. Leer = ui_prefs-Defaults (alte Shows).
        self.live_view_meta: dict = {}
        self._patch_cache: list[PatchedFixture] = []
        # Basis-Level pro Fixture: {fid: {attr: 0-255}}. Wird in den Default-Frame
        # gelegt (siehe _rebuild_render_plan) und mit der Show gespeichert. Typisch:
        # PAR-Grundhelligkeit, damit eine reine Farbe sofort sichtbar ist.
        self.base_levels: dict[int, dict[str, int]] = {}
        # Implizite Grundhelligkeit (4a²): True = eine aktive Farbe ohne getriebenen
        # Dimmer wird auf voll gesetzt ("Farbe heisst sichtbar"). False = strikte
        # Trennung Farbe ↔ Dimmer (reine Farbe bleibt dunkel; Helligkeit kommt NUR
        # aus Dimmer-Effekten/Mastern/-Snaps). Mit der Show gespeichert und per
        # Menue-Schalter umschaltbar. Default seit 2026-06-24: False (strikte
        # Trennung) — ein Farb-Snap soll den Dimmer NICHT mehr selbst hochziehen.
        # Alt-Shows ohne den Schluessel laden weiter mit True (Look bleibt erhalten).
        self.implicit_brightness: bool = False
        # Vorberechneter Render-Plan (bei Patch-Aenderung erneuert) fuer den
        # zentralen Per-Frame-Renderer _render_frame().
        self._fix_index: dict[int, tuple] = {}          # fid -> (fixture, channels)
        self._default_frame: dict[int, bytes] = {}      # univ -> 512B Default-Frame
        self._commit_spans: dict[int, list[tuple[int, int]]] = {}  # univ -> [(start,len)]
        self._patched_set: dict[int, frozenset] = {}    # univ -> {gepatchte Adressen}
        # Nicht-gepatchte Adressen, die Funktionen (z. B. ScriptFunction setdmx)
        # im letzten Frame geschrieben haben — fuer korrektes Freigeben.
        self._engine_extra_prev: dict[int, set] = {}
        # Simple Desk = manuelle Roh-Override-Ebene (ISO-03). {universe: {ch: val}},
        # nur explizit gesetzte Kanaele. Wird im _render_frame als OBERSTE Schicht
        # angewandt (deterministisch jeden Frame) — frueher schrieb der Fader direkt
        # ins Live-Universe am Renderer vorbei (Flackern auf gepatchten Kanaelen +
        # unsichtbarer Zombie auf freien). Sicht- (ISO-01) und loeschbar (ISO-02).
        self.simple_desk: dict[int, dict[int, int]] = {}
        self._sd_lock = threading.RLock()
        # F-20: Art-Net/sACN-EINGANG als eigene Render-Schicht. Die Empfaenger
        # (artnet_input/sacn_input) schreiben ihre gemergten Werte NICHT mehr direkt
        # ins Live-Universe (das ueberschrieb der Per-Frame-Renderer auf gepatchten
        # Kanaelen), sondern in diesen Puffer; _render_frame mischt ihn deterministisch
        # je Universe mit dem konfigurierten Modus. Leer = kein Eingang = kein Effekt.
        #   input_layer:       {out_universe: {channel(1..512): value}}
        #   input_merge_modes: {out_universe: "HTP"|"LTP"|"REPLACE"}
        self.input_layer: dict[int, dict[int, int]] = {}
        self.input_merge_modes: dict[int, str] = {}
        self._input_lock = threading.RLock()
        # Simple Desk ist standardmaessig reine ANZEIGE (Monitor). Erst mit aktivem
        # 'Manueller Override' wirkt die Ebene auf die Ausgabe (Schicht 4c, absolute
        # Oberhand). Default False = nichts faellt ungewollt in die Live-Ausgabe.
        self.simple_desk_override: bool = False
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
        # Musik-Playlist (In-App-Player): Liste von {path,title,genre,bpm}.
        # SSOT für die .lshow; der MediaPlayer (core/audio/media_player.py) wird
        # daraus gefüllt, und die Virtuelle Konsole (VCSongInfo) liest „aktuelles/
        # nächstes Lied".
        self.playlist: list[dict] = []
        # Auto-Show an Musik koppeln: startet beim Play im In-App-Player automatisch
        # die angegebenen Funktionen (BPM-synchrone Lichtshow), stoppt beim Pause/Stop.
        #   enabled       — Kopplung aktiv?
        #   function_ids  — Funktionen, die der MusicShowDirector startet/stoppt
        #   bank          — empfohlene VC-Bank der Auto-Show (Info/optionales Umschalten)
        #   slots         — {function_id: live_edit_slot} damit Bank-Pads desselben
        #                   Slots die director-gestartete Funktion sauber ablösen
        #                   (layer-getrennt, ohne globales stop_all)
        # Getrieben von core/audio/music_show.py (MusicShowDirector).
        self.music_autoshow: dict = {"enabled": False, "function_ids": [], "bank": 0, "slots": {}}
        # QLC+ Function Manager
        from .engine.function_manager import get_function_manager
        self.function_manager = get_function_manager()
        # Central MIDI mapping engine (singleton, bidirectional in/out).
        from .midi.midi_mapper import get_midi_mapper
        self.midi_mapper = get_midi_mapper(self)
        try:
            self.midi_mapper and self.midi_mapper.load("data/midi_mappings.json")
        except Exception as e:
            debug_swallow("app_state.midi_load", e)
        # Zentraler StateSync Event-Bus
        from .sync import get_sync
        self.sync = get_sync()

    # ── Show-Datenbank ────────────────────────────────────────────────────────

    def open_show(self, path: str = SHOW_DB_PATH):
        import os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._show_engine = create_engine(f"sqlite:///{path}", echo=False)
        create_all_idempotent(self._show_engine)   # QA-06: TOCTOU-toleranter create_all
        # FLD-01b: fehlende Spalten in bestehenden Show-DBs nachziehen.
        try:
            from .database.models import migrate_show_db
            migrate_show_db(self._show_engine)
        except Exception as e:
            print(f"[AppState] migrate_show_db failed: {e}")
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
        # FLD-FID: gegen Cache/DB-Desync absichern. Kollidiert die fid mit einer
        # bereits persistierten Zeile (z.B. verwaiste current_show.db-Eintraege),
        # auf die naechste freie fid ausweichen statt mit IntegrityError die App
        # einzufrieren.
        try:
            existing = {f.fid for f in self._patch_cache}
            if self._show_engine is not None:
                from sqlalchemy import select
                with self._session() as s:
                    existing |= set(
                        s.execute(select(PatchedFixture.fid)).scalars()
                    )
            if fixture.fid in existing:
                fixture.fid = self.next_fid()
        except Exception as e:
            debug_swallow("app_state.add_fixture.fid_guard", e)
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

    def clear_patch(self):
        """Loescht ALLE gepatchten Fixtures hart aus der Show-DB — auch Zeilen,
        die (durch Cache/DB-Desync) nicht im Cache stehen. Verhindert verwaiste
        fid-Kollisionen beim Neuaufbau des Patches (FLD-FID). Wird beim Laden
        einer Show genutzt, um die Patch-Tabelle verlustfrei zu ersetzen."""
        if self._show_engine is None:
            self._patch_cache = []
            return
        from sqlalchemy import delete
        with self._session() as s:
            s.execute(delete(PatchedFixture))
            s.commit()
        self._reload_patch_cache()
        self._emit("patch_changed")

    def update_fixture(self, fid: int, undoable: bool = True, **changes) -> bool:
        allowed = {
            "label", "fixture_profile_id", "mode_name", "universe",
            "address", "channel_count", "manufacturer_name",
            "fixture_name", "fixture_type", "invert_pan",
            "invert_tilt", "swap_pan_tilt", "dimmer_curve",
            "spider_mirrored", "spider_dual_tilt",
            "pan_range_deg", "tilt_range_deg", "pan_zero_dmx", "tilt_zero_dmx",
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
        for key in ("fixture_profile_id", "universe", "address", "channel_count",
                    "pan_range_deg", "tilt_range_deg", "pan_zero_dmx", "tilt_zero_dmx"):
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
            "spider_mirrored": getattr(f, "spider_mirrored", True),
            "spider_dual_tilt": getattr(f, "spider_dual_tilt", False),
            "pan_range_deg": getattr(f, "pan_range_deg", 540),
            "tilt_range_deg": getattr(f, "tilt_range_deg", 270),
            "pan_zero_dmx": getattr(f, "pan_zero_dmx", 128),
            "tilt_zero_dmx": getattr(f, "tilt_zero_dmx", 128),
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
            spider_mirrored=d.get("spider_mirrored", True),
            spider_dual_tilt=d.get("spider_dual_tilt", False),
            pan_range_deg=d.get("pan_range_deg", 540),
            tilt_range_deg=d.get("tilt_range_deg", 270),
            pan_zero_dmx=d.get("pan_zero_dmx", 128),
            tilt_zero_dmx=d.get("tilt_zero_dmx", 128),
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
        # Grand-Master-Adressmaske: nur Intensitaets-/Farbadressen je Universum,
        # damit der GM nur dimmt und nicht Pan/Tilt/Gobo verstellt (Audit B4).
        gm_mask: dict[int, set] = {}
        for fid, (fx, chans) in fix_index.items():
            for addr in self._fixture_intensity_addrs(fx, chans):
                gm_mask.setdefault(fx.universe, set()).add(addr)
        try:
            self.output_manager.set_gm_address_mask(
                {u: frozenset(s) for u, s in gm_mask.items()})
        except Exception as e:
            print(f"[AppState] set gm mask error: {e}")

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

    def auto_patch_fixtures(self, undoable: bool = True):
        """Weist allen Fixtures aufeinander folgende Adressen zu (undobar)."""
        # Snapshot der aktuellen Adressierung fuer Undo (vor der Aenderung).
        before = [
            {"fid": f.fid, "universe": f.universe, "address": f.address}
            for f in self._patch_cache
        ]
        addr = 1
        univ = 1
        after = []
        for f in sorted(self._patch_cache, key=lambda x: x.fid):
            if addr + f.channel_count - 1 > 512:
                univ += 1
                addr = 1
            after.append({"fid": f.fid, "universe": univ, "address": addr})
            addr += f.channel_count
        self._apply_patch_addresses(after)
        if undoable:
            self._push_undo(
                label="Auto-Patch",
                do=lambda: None,
                undo=lambda b=before: self._apply_patch_addresses(b),
                redo=lambda a=after: self._apply_patch_addresses(a),
            )

    def _apply_patch_addresses(self, rows: list[dict]):
        """Setzt universe/address fuer eine Liste {fid, universe, address} und
        baut Cache/Render-Plan neu auf (gemeinsame Basis fuer Auto-Patch+Undo)."""
        from sqlalchemy import update
        from .database.models import PatchedFixture as PF
        with self._session() as s:
            for r in rows:
                s.execute(
                    update(PF).where(PF.fid == r["fid"]).values(
                        universe=r["universe"], address=r["address"]
                    )
                )
            s.commit()
        self._reload_patch_cache()
        self._emit("patch_changed")

    def next_fid(self) -> int:
        """Naechste freie Fixture-ID. Robust gegen Cache/DB-Desync (FLD-FID):
        nimmt das Maximum aus der persistenten patched_fixtures-Tabelle UND dem
        In-Memory-Cache. Sonst kann add_fixture auf eine bereits in der DB
        belegte fid INSERTen -> IntegrityError (UNIQUE constraint failed:
        patched_fixtures.fid), der bis zum globalen Fehlerdialog durchschlaegt
        und das Hauptfenster einfriert."""
        cache_max = max((f.fid for f in self._patch_cache), default=0)
        db_max = 0
        if self._show_engine is not None:
            try:
                from sqlalchemy import select, func
                with self._session() as s:
                    db_max = s.execute(
                        select(func.max(PatchedFixture.fid))
                    ).scalar() or 0
            except Exception as e:
                debug_swallow("app_state.next_fid.db_max", e)
        return max(cache_max, db_max) + 1

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

    def suggest_address(self, universe: int, channel_count: int,
                        exclude_fid: int = -1) -> int | None:
        """Schlaegt die naechste freie Startadresse fuer ein Fixture mit
        channel_count Kanaelen im Universum vor (P1, zentral wiederverwendbar).

        Strategie: belegte Bereiche sortieren und die ERSTE Luecke nehmen, in
        die das Fixture passt (auch Luecken zwischen Fixtures) — sonst direkt
        hinter dem letzten belegten Kanal. Passt es nirgends mehr (Ende > 512),
        wird None geliefert; die UI zeigt dann eine Warnung.
        """
        try:
            channel_count = max(1, int(channel_count))
        except (TypeError, ValueError):
            return None
        spans = sorted(
            (f.address, f.address + f.channel_count - 1)
            for f in self._patch_cache
            if f.universe == universe and f.fid != exclude_fid
        )
        cursor = 1  # naechster Kandidat fuer eine Startadresse
        for start, end in spans:
            if start - cursor >= channel_count:
                return cursor  # Luecke vor diesem Fixture reicht aus
            cursor = max(cursor, end + 1)
        if cursor + channel_count - 1 <= 512:
            return cursor
        return None

    # ── Programmer ────────────────────────────────────────────────────────────

    def set_programmer_value(self, fid: int, attribute: str, value: int,
                             undoable: bool = False, head: int = 0):
        # Mehrkopf (X-6): head>0 adressiert das N-te Vorkommen eines Attributs
        # (z. B. die 2. Farb-/Tilt-Bank eines Spiders) ueber den Schluessel
        # "attr#N". head=0 = "attr" -> byte-genau wie bisher.
        key = attribute if not head else f"{attribute}#{int(head)}"
        with self._prog_lock:
            old = self.programmer.get(fid, {}).get(key, None)
            if fid not in self.programmer:
                self.programmer[fid] = {}
            self.programmer[fid][key] = max(0, min(255, value))
            new_val = self.programmer[fid][key]
        self._flush_programmer_to_dmx(fid)
        self._emit("programmer_changed", fid)
        if undoable and old != new_val:
            self._push_undo(
                label=f"Programmer FID{fid}.{key}={new_val}",
                do=lambda: None,
                undo=lambda f=fid, a=attribute, v=old, h=head: (
                    self.set_programmer_value(f, a, v, undoable=False, head=h)
                    if v is not None
                    else self._clear_programmer_attr(f, key)),
                redo=lambda f=fid, a=attribute, v=new_val, h=head:
                    self.set_programmer_value(f, a, v, undoable=False, head=h),
            )

    def _clear_programmer_attr(self, fid: int, attribute: str):
        with self._prog_lock:
            if fid not in self.programmer:
                return
            self.programmer[fid].pop(attribute, None)
            if not self.programmer[fid]:
                self.programmer.pop(fid, None)
        self._flush_programmer_to_dmx(fid)
        self._emit("programmer_changed", fid)

    def clear_programmer(self, fid: int | None = None):
        with self._prog_lock:
            if fid is None:
                self.programmer.clear()
            else:
                self.programmer.pop(fid, None)
        self._flush_all_to_dmx()
        self._emit("programmer_changed", None)

    def get_programmer_value(self, fid: int, attribute: str, head: int = 0) -> int | None:
        key = attribute if not head else f"{attribute}#{int(head)}"
        return self.programmer.get(fid, {}).get(key)

    def clear_programmer_value(self, fid: int, attribute: str):
        """Entfernt einen einzelnen Programmer-Wert (z. B. fuer Toggle-/Flash-
        Ruecknahme einer Farb-/Snap-Taste in der Virtual Console)."""
        self._clear_programmer_attr(int(fid), attribute)

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

    def set_programmer_focus(self, key: str | None):
        """ENG-02: Merkt den aktiven Programmer-Tab (z. B. "Intensity", "Matrix").
        Auf "Intensity" gewinnt fuer SELEKTIERTE Lampen die manuelle Intensitaet ueber
        einen laufenden Dimmer-Effekt; sonst besitzt der Effekt den direkt getriebenen
        Dimmer. Wird von der ProgrammerView bei Tab-Wechsel gesetzt."""
        self.programmer_focus = str(key) if key else None

    def active_scope_fids(self) -> list[int]:
        """Geraete im aktiven Speicher-Scope = die gemeinsame Auswahl.

        Beim Gruppenwechsel setzt der Programmer die Auswahl auf die Geraete der
        Gruppe (set_selected_fids), daher ist die aktuelle Auswahl der korrekte
        Scope: Speichern beruecksichtigt nur diese Geraete und NICHT liegen-
        gebliebene Programmer-Werte zuvor gewaehlter Gruppen. Leere Liste = kein
        Scope -> alles speichern (Alt-Verhalten, z. B. wenn nichts gewaehlt ist)."""
        return list(self.selected_fids)

    # ── Gruppen-Auflösung (zentral; von VC SELECT_GROUP / GROUP_DIMMER genutzt) ──
    def _group_lookup(self, name_or_ref):
        """(gid, fids in Raster-Reihenfolge) einer Fixture-Gruppe.

        ENG-05: Akzeptiert einen Namen (str) ODER einen ``(gid, name)``-Ref aus
        dem Preset-Browser. Bei vorhandener gid wird EINDEUTIG per ID aufgeloest
        (gleichnamige Gruppen → kein faelschliches „Gruppe ohne Geraete"). Sonst
        per Name: ``scalar_one_or_none`` bleibt der Normalpfad; nur wenn es
        WIRKLICH mehrere gleichnamige Gruppen gibt (``MultipleResultsFound``), wird
        die erste genommen statt zu crashen. (None, []) wenn nicht da.
        """
        import json
        from sqlalchemy.exc import MultipleResultsFound
        gid_hint, name = (name_or_ref if isinstance(name_or_ref, tuple)
                          else (None, name_or_ref))
        try:
            from sqlalchemy import select
            from .database.models import FixtureGroup
            with self._session() as s:
                if gid_hint is not None:
                    g = s.get(FixtureGroup, gid_hint)
                else:
                    stmt = select(FixtureGroup).where(FixtureGroup.name == name)
                    try:
                        g = s.execute(stmt).scalar_one_or_none()
                    except MultipleResultsFound:
                        g = s.execute(stmt).scalars().first()
            if g is None:
                return None, []
            items = []
            for key, fid in (json.loads(g.positions_json or "{}") or {}).items():
                try:
                    c, r = str(key).split(",")
                    items.append((int(r), int(c), int(fid)))
                except Exception:
                    continue
            items.sort()
            return g.id, [fid for _, _, fid in items]
        except Exception:
            return None, []

    def group_fids_by_name(self, name: str) -> list[int]:
        """Fids einer Gruppe (Name) in Raster-Reihenfolge; [] wenn unbekannt."""
        return self._group_lookup(name)[1]

    def select_group_by_name(self, name_or_ref) -> bool:
        """Wählt die Fixtures einer Gruppe in den Programmer (F-24). True bei Erfolg.

        ENG-05: ``name_or_ref`` ist ein Gruppenname (str, z. B. von VCButton) ODER
        ein ``(gid, name)``-Ref aus dem Preset-Browser (eindeutige Aufloesung bei
        gleichnamigen Gruppen).
        """
        gid, fids = self._group_lookup(name_or_ref)
        if gid is None or not fids:
            return False
        self.set_selected_group_id(gid)
        self.set_selected_fids(fids)
        return True

    def list_fixture_groups(self) -> list[dict]:
        """[{name, folder, fids}] aller Fixture-Gruppen (UI-01 Preset-Browser).
        fids in Raster-Reihenfolge (col,row), Duplikate entfernt. Leere Liste bei
        Fehler/fehlender Show-DB."""
        import json
        out: list[dict] = []
        try:
            from sqlalchemy import select
            from .database.models import FixtureGroup
            with self._session() as s:
                groups = list(s.execute(select(FixtureGroup)).scalars())
                for g in groups:
                    items = []
                    try:
                        for key, fid in (json.loads(g.positions_json or "{}") or {}).items():
                            c, r = str(key).split(",")
                            items.append((int(r), int(c), int(fid)))
                    except Exception:
                        items = []
                    items.sort()
                    fids: list[int] = []
                    for _r, _c, fid in items:
                        if fid not in fids:
                            fids.append(fid)
                    out.append({"id": g.id,
                                "name": g.name or "",
                                "folder": getattr(g, "folder", "") or "",
                                "fids": fids})
        except Exception:
            return []
        return out

    def _flush_programmer_to_dmx(self, fid: int):
        fixture = next((f for f in self._patch_cache if f.fid == fid), None)
        if not fixture or fixture.universe not in self.universes:
            return
        universe = self.universes[fixture.universe]
        prog = apply_pan_tilt_orientation(fixture, self.programmer.get(fid, {}))
        channels = get_channels_for_patched(fixture)
        seen: dict[str, int] = {}
        for ch in channels:
            a = ch.attribute
            head = seen.get(a, 0)
            seen[a] = head + 1
            # Mehrkopf (X-6): Kopf N liest "attr#N", faellt auf Kopf 0 ("attr")
            # zurueck, sonst Default -> Einzelkopf byte-genau wie bisher.
            key = a if head == 0 else f"{a}#{head}"
            if key in prog:
                val = prog[key]
            elif a in prog:
                val = prog[a]
            else:
                val = ch.default_value
            dmx_addr = fixture.address + ch.channel_number - 1
            if 1 <= dmx_addr <= 512:
                universe.set_channel(dmx_addr, val)

    def _flush_all_to_dmx(self):
        for f in self._patch_cache:
            self._flush_programmer_to_dmx(f.fid)

    # ── Simple Desk (manuelle Roh-Override-Ebene, ISO-03) ──────────────────────

    def _emit_dmx_changed(self, universe=None):
        try:
            from .sync import SyncEvent
            self.sync.emit(SyncEvent.DMX_CHANGED, universe)
        except Exception as e:
            print(f"[app_state] dmx emit error: {e}")

    def set_simple_desk_channel(self, universe: int, channel: int, value: int):
        """Setzt einen manuellen Simple-Desk-Override (Kanal 1..512, Wert 0..255).
        Wird im _render_frame als oberste Schicht angewandt (kein Roh-Bypass mehr)."""
        try:
            universe = int(universe)
            channel = int(channel)
            value = max(0, min(255, int(value)))
        except (TypeError, ValueError):
            return
        if not (1 <= channel <= 512):
            return
        with self._sd_lock:
            self.simple_desk.setdefault(universe, {})[channel] = value
        self._emit_dmx_changed(universe)

    def set_simple_desk_all(self, universe: int, value: int):
        """Setzt ALLE 512 Kanaele eines Universums als Simple-Desk-Override
        (Buttons 'Alles auf 0' / 'Alles auf 255')."""
        try:
            universe = int(universe)
            value = max(0, min(255, int(value)))
        except (TypeError, ValueError):
            return
        with self._sd_lock:
            self.simple_desk[universe] = {ch: value for ch in range(1, 513)}
        self._emit_dmx_changed(universe)

    def get_simple_desk_channel(self, universe: int, channel: int) -> int | None:
        with self._sd_lock:
            return self.simple_desk.get(int(universe), {}).get(int(channel))

    def clear_simple_desk(self, universe: int | None = None):
        """Entfernt Simple-Desk-Overrides (ein Universum oder alle). Die Kanaele
        fallen im naechsten Frame auf die gerenderte Ausgabe/Default zurueck —
        kein haengender Roh-Wert mehr (ISO-02)."""
        with self._sd_lock:
            if universe is None:
                self.simple_desk.clear()
            else:
                self.simple_desk.pop(int(universe), None)
        self._emit_dmx_changed(universe)

    def set_simple_desk_override(self, enabled: bool):
        """Schaltet den manuellen Override (Schicht 4c) an/aus. Nur wenn aktiv,
        wirkt die Simple-Desk-Ebene auf die Ausgabe (absolute Oberhand). Beim
        Ausschalten werden die Override-Werte verworfen (Kanaele werden frei)."""
        self.simple_desk_override = bool(enabled)
        if not self.simple_desk_override:
            with self._sd_lock:
                self.simple_desk.clear()
        self._emit_dmx_changed(None)

    # ── Aktive Fremdwerte: Anzeige (ISO-01) + zentrales Clear (ISO-02) ─────────

    def programmer_active(self) -> int:
        """Anzahl aktiver Programmer-Attribute (0 = leer). Fuer die ISO-01-Anzeige
        'Programmer aktiv (n)'."""
        with self._prog_lock:
            return sum(len(a) for a in self.programmer.values())

    def simple_desk_active(self) -> int:
        """Anzahl wirksamer Simple-Desk-Override-Kanaele (0 wenn der manuelle
        Override aus ist — dann ist Simple Desk reine Anzeige)."""
        if not getattr(self, "simple_desk_override", False):
            return 0
        with self._sd_lock:
            return sum(len(c) for c in self.simple_desk.values())

    def clear_all_non_vc(self):
        """ISO-02: setzt ALLE manuellen Stoerwerte zurueck (Programmer + Simple
        Desk). Laufende Funktionen/Effekte/Cues, gespeicherte Effekte, Shows,
        Patches und Fixtures bleiben UNANGETASTET."""
        self.clear_programmer()
        self.clear_simple_desk()

    # ── Events ────────────────────────────────────────────────────────────────

    def subscribe(self, callback):
        self._callbacks.append(callback)

    def unsubscribe(self, callback):
        """Gegenstueck zu subscribe: meldet einen Callback wieder ab.

        Defensiv — entfernt nur, wenn vorhanden (kein Fehler sonst), und ist
        damit idempotent (doppeltes/unsubscribe-ohne-subscribe ist ein No-Op).
        Ohne dies leakt jeder Subscriber, der sich nicht abmeldet (z. B. eine
        geschlossene VisualizerBridge): der gebundene Callback bliebe in
        ``_callbacks`` und liefe bei jedem Event auf einem toten Objekt weiter.
        ``_emit_impl`` iteriert ueber eine Kopie, daher ist Abmelden auch
        waehrend eines Emits sicher."""
        try:
            self._callbacks.remove(callback)
        except ValueError:
            pass

    # ── Playback ──────────────────────────────────────────────────────────────

    def start_playback(self):
        from .engine.executor import PlaybackEngine
        self.playback_engine = PlaybackEngine(self)
        self.playback_engine.start()
        # EIN zentraler Renderer im 44-Hz-Output-Loop (ersetzt den frueheren
        # zweiten PlaybackEngine-Thread) — behebt Tearing + haengende Werte.
        self.output_manager.add_tick_callback(self._render_frame)

    # ── Zentraler Per-Frame-Renderer ──────────────────────────────────────────

    def apply_input_merge(self, out_univ: int, data, mode: str = "HTP"):
        """F-20: Empfangene DMX-Werte (Art-Net/sACN) in die Eingangs-Schicht legen.
        Thread-safe; wird vom RX-Thread aufgerufen, ``_render_frame`` mischt sie pro
        Frame deterministisch. ``data`` = bytes/bytearray (Kanal 1 == Index 0)."""
        if mode not in ("HTP", "LTP", "REPLACE"):
            mode = "HTP"
        out_univ = int(out_univ)
        with self._input_lock:
            layer = self.input_layer.get(out_univ)
            if layer is None:
                layer = {}
                self.input_layer[out_univ] = layer
            self.input_merge_modes[out_univ] = mode
            for i in range(min(len(data), 512)):
                layer[i + 1] = data[i] & 0xFF

    def clear_input_merge(self, out_univ: int | None = None):
        """F-20: Eingangs-Schicht leeren (eine Universe oder alle). Damit ein
        weggefallener externer Sender keine eingefrorenen Werte hinterlaesst."""
        with self._input_lock:
            if out_univ is None:
                self.input_layer.clear()
                self.input_merge_modes.clear()
            else:
                self.input_layer.pop(int(out_univ), None)
                self.input_merge_modes.pop(int(out_univ), None)

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
        with self._prog_lock:
            programmer = {fid: dict(attrs)
                          for fid, attrs in self.programmer.items()}
        # 1. Scratch-Universen mit Default-Frame vorbelegen (= Per-Frame-Clear).
        scratch: dict[int, Universe] = {}
        for univ, _live in live_universes:
            su = Universe(univ)
            base = self._default_frame.get(univ)
            if base:
                su.set_range(1, base)
            scratch[univ] = su
        # 2. Funktionen rendern in die Scratch-Universen. Dabei protokollieren,
        #    welche Adressen der Funktions-Layer schreibt (WERT-unabhaengig) —
        #    so erkennt 4a² einen Dimmer-Effekt auch dann als „treibt die
        #    Intensitaet", wenn er gerade 0 ausgibt (Strobe-Nulldurchgang,
        #    dunkles Matrix-Pixel) und darf ihn dann nicht aufhellen.
        # WP-Tempo: Tempo-Buses EINMAL pro Frame fortschreiben, BEVOR die Funktionen
        # rendern — so liest jeder beat-synchrone Effekt im selben Frame dieselbe,
        # eingefrorene Bus-Position (phasenkohärent, da nur dieser Render-Thread
        # advance_frame aufruft). Rein additiv: schreibt KEINE Universen.
        try:
            from src.core.engine.tempo_bus import get_tempo_bus_manager
            get_tempo_bus_manager().advance_frame(dt)
        except Exception as exc:
            print(f"[AppState] tempo advance error: {exc}")
        for su in scratch.values():
            su.begin_write_log()
        try:
            self.function_manager.tick(scratch, self._patch_cache, dt)
        except Exception as exc:
            print(f"[AppState] render functions error: {exc}")
        func_touched: dict[int, set[int]] = {}
        for univ, su in scratch.items():
            func_touched[univ] = su.end_write_log()
        # 2a. WP-6 (Abschnitt 8): Adressen erfassen, die der FUNKTIONS-Layer
        #     (Matrix/EFX/…) in DIESEM Frame treibt (Scratch != Default). Der
        #     Programmer-LTP ueberschreibt diese Nicht-Intensitaets-Kanaele dann
        #     NICHT mehr (Funktionen "besitzen" sie) — eine laufende Matrix-Farbe
        #     wird also nicht vom normalen Color-Tab ueberschrieben. Intensitaet
        #     wird weiterhin multipliziert statt ersetzt (EE-02, s. u.). Nur
        #     gepatchte Adressen werden geprueft (schnell).
        func_driven: dict[int, set[int]] = {}
        for univ, su in scratch.items():
            base = self._default_frame.get(univ)
            patched = self._patched_set.get(univ, frozenset())
            if not patched:
                continue
            cur = su.get_all()
            if base:
                fd = {a for a in patched if cur[a - 1] != base[a - 1]}
            else:
                fd = {a for a in patched if cur[a - 1] != 0}
            if fd:
                func_driven[univ] = fd
        # 2b. Welche Fixtures treibt der EFFEKT-Layer (Funktionen) auf ihren
        #     Intensitaets-Kanaelen? Basis fuer Programmer-Multiply (EE-02).
        #     Bewusst VOR den Executoren erfasst: Cues behalten LTP-Ersatz durch
        #     den Programmer, nur laufende Effekte werden multipliziert.
        inten_addrs: dict[int, list[int]] = {}
        # Getrennt erfasst fuer die implizite Grundhelligkeit (4a²): NUR echte
        # Dimmer-/Intensitaets-Kanaele bzw. NUR Farb-Kanaele eines Fixtures.
        dim_addrs: dict[int, list[int]] = {}
        color_addrs: dict[int, list[int]] = {}
        effect_present: dict[int, bool] = {}
        for fidi, entry in self._fix_index.items():
            fx, chans = entry
            addrs = self._fixture_intensity_addrs(fx, chans)
            inten_addrs[fidi] = addrs
            dims: list[int] = []
            cols: list[int] = []
            for ch in chans:
                a_l = (getattr(ch, "attribute", "") or "").lower()
                ad = fx.address + ch.channel_number - 1
                if not (1 <= ad <= 512):
                    continue
                if a_l in _DIM_INTENSITY_ATTRS:
                    dims.append(ad)
                elif a_l in _DIM_COLOR_ATTRS:
                    cols.append(ad)
            dim_addrs[fidi] = dims
            color_addrs[fidi] = cols
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
        exec_dimmer_fids: set[int] = set()
        if self.playback_engine is not None:
            try:
                merged = self.playback_engine.compute_merged()
                self._apply_fixture_map(scratch, merged)
                # Fixtures, deren Intensitaet ein Cue setzt (auch 0) → 4a² laesst
                # sie in Ruhe (der Cue „besitzt" den Dimmer).
                for fid_m, attrs_m in merged.items():
                    try:
                        if any(k in attrs_m for k in _DIM_INTENSITY_ATTRS):
                            exec_dimmer_fids.add(int(fid_m))
                    except (TypeError, ValueError):
                        continue
            except Exception as exc:
                print(f"[AppState] render executors error: {exc}")

        # 4. Programmer (LTP, hoechste Prioritaet).
        #
        # ENG-02 „Aktiver Tab gewinnt": Treibt eine FUNKTION (Dimmer-Matrix/EFX) den
        # Intensitaets-/Dimmer-Kanal eines Fixtures DIREKT (Write-Log, WERT-unabhaengig
        # — auch im Nulldurchgang/bei dunklem Pixel!), gehoert ihr der Kanal. Der
        # per-Fixture Programmer-Intensity-Wert darf ihn dann NICHT antasten — weder
        # ersetzen (LTP) noch EE-02-multiplizieren. Sonst killt ein (oft beim Auswaehlen
        # auto-gesetztes) intensity=0 die Dimmer-Matrix, bzw. ein hochgezogener Wert
        # invertiert den Effekt (gerade dunkle Pixel bekaemen den Programmer-Wert).
        # AUSNAHME: ist der Intensity-Tab aktiv UND das Fixture selektiert, will der
        # Nutzer manuell dimmen -> die Programmer-Intensitaet gewinnt absolut (ersetzt
        # den Effekt-Dimmer). Globaler Submaster/Grand-Master/Fixture-Dimmer (4b) bleiben
        # in BEIDEN Faellen als echte Master erhalten. Farb-Effekte fassen den Intensity-
        # Kanal nicht an -> nicht betroffen, der EE-02-Multiply bleibt dort erhalten.
        func_inten_fids: set[int] = set()
        for fidi, dims in dim_addrs.items():
            if not dims:
                continue
            entry = self._fix_index.get(fidi)
            if not entry:
                continue
            touched = func_touched.get(entry[0].universe, ())
            if any(a in touched for a in dims):
                func_inten_fids.add(fidi)
        # Intensity-Tab aktiv + Fixture selektiert -> manuelle Intensitaet gewinnt.
        intensity_wins: set[int] = set()
        if getattr(self, "programmer_focus", None) == "Intensity" and func_inten_fids:
            sel = set(getattr(self, "selected_fids", None) or ())
            intensity_wins = func_inten_fids & sel
        owned_by_func = func_inten_fids - intensity_wins   # hier wirkt Programmer NICHT

        prog_factor: dict[int, float] = {}
        for fid, attrs in programmer.items():
            try:
                fidi = int(fid)
            except (TypeError, ValueError):
                continue
            # Funktions-getriebener Dimmer: KEIN EE-02-Multiply. (intensity_wins wird
            # weiter unten absolut geschrieben statt multipliziert.)
            if fidi in func_inten_fids:
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
        # owned_by_func: Intensitaet weder ersetzen noch multiplizieren (skip).
        # intensity_wins: Intensitaet ABSOLUT schreiben -> NICHT skippen UND die
        # Intensity-Adresse aus dem func-driven Schutz nehmen (sonst blockt protect den
        # Programmer-Ersatz). Farb-Kanaele des Effekts bleiben weiter geschuetzt.
        protect = func_driven
        if intensity_wins:
            protect = {u: set(a) for u, a in func_driven.items()}
            for fidi in intensity_wins:
                entry = self._fix_index.get(fidi)
                if not entry:
                    continue
                univ = entry[0].universe
                if univ in protect:
                    for a in dim_addrs.get(fidi, ()):
                        protect[univ].discard(a)
        self._apply_fixture_map(scratch, programmer,
                                skip_intensity_for=set(prog_factor) | owned_by_func,
                                protect_addrs=protect)

        # 4a². Implizite Grundhelligkeit — „Farbe heisst sichtbar". Ein Fixture mit
        #      eigenem Dimmer-/Intensitaets-Kanal, dessen Farbe aktiv ist (durch
        #      Programmer ODER einen laufenden Farb-Effekt/Matrix), dessen Dimmer
        #      aber von NICHTS getrieben wird, wird hier auf voll gesetzt — damit
        #      die Farbe leuchtet, OHNE dass der Master-/Programmer-Dimmer manuell
        #      hochgezogen werden muss (frueher blieb so eine reine Farb-Matrix auf
        #      Geraeten mit Dimmer-Kanal dunkel). Ein echter Dimmer gewinnt weiter:
        #        • Funktion schreibt den Dimmer  → func_touched (auch Wert 0!) →
        #          uebersprungen. Deckt „Dimmer-Effekt/Matrix zieht auf 0“ robust ab
        #          (Strobe-Nulldurchgang/dunkles Pixel bleibt dunkel, kein Flackern).
        #        • Cue setzt den Dimmer            → exec_dimmer_fids → uebersprungen
        #        • Programmer-Dimmer gesetzt        → uebersprungen (absolut/Multiply)
        #        • Base-Level / bereits getrieben   → Dimmer ≠ 0 → uebersprungen
        #      Die nachfolgende 4b-Skalierung (Submaster/Fixture-Dimmer/Blackout)
        #      regelt dieses implizite Voll ganz normal wieder herunter.
        prog_dimmer_fids: set[int] = set()
        for fid, attrs in programmer.items():
            try:
                if any(k in attrs for k in _DIM_INTENSITY_ATTRS):
                    prog_dimmer_fids.add(int(fid))
            except (TypeError, ValueError):
                continue
        # implicit_brightness=False -> strikte Trennung Farbe/Dimmer: kein implizites Voll
        # (reine Farbe bleibt dunkel, Helligkeit nur aus Dimmer-Effekten/Mastern).
        _dim_items = dim_addrs.items() if getattr(self, "implicit_brightness", True) else ()
        for fidi, dims in _dim_items:
            if not dims or fidi in exec_dimmer_fids or fidi in prog_dimmer_fids:
                continue
            entry = self._fix_index.get(fidi)
            if not entry:
                continue
            univ = entry[0].universe
            touched = func_touched.get(univ, ())
            if any(a in touched for a in dims):
                continue   # eine Funktion treibt den Dimmer (auch auf 0)
            su = scratch.get(univ)
            if su is None:
                continue
            if any(su.get_channel(a) for a in dims):
                continue   # Dimmer schon getrieben (Base-Level o. Ae.)
            # „Farbe aktiv" = ein Farbkanal wird UEBER seinen Ruhewert (Default-
            # Frame) getrieben. Ein blosser Geraete-Default (z. B. color_b=5) zaehlt
            # also nicht — nur eine echt gesetzte/effekt­getriebene Farbe lichtet.
            base = self._default_frame.get(univ)
            cols = color_addrs.get(fidi) or []
            active = False
            for a in cols:
                dv = base[a - 1] if (base and a - 1 < len(base)) else 0
                if su.get_channel(a) > dv:
                    active = True
                    break
            if not active:
                continue   # keine (zusaetzliche) Farbe aktiv → dunkel lassen
            for a in dims:
                su.set_channel(a, 255)

        # 4b. Multiplikativer Dimmer-Master: (globaler Submaster * je-Fixture
        #     zugewiesener Submaster) * Gruppen-/Fixture-Dimmer * Programmer-Dimmer
        #     (nur wo Effekt aktiv). Skaliert pro Fixture die Intensitaets- bzw.
        #     (ersatzweise) Farbkanaele.
        submaster = 1.0
        om = getattr(self, "output_manager", None)
        if om is not None and hasattr(om, "effective_submaster"):
            try:
                submaster = om.effective_submaster()
            except Exception:
                submaster = 1.0
        # Zugewiesene (gezielte) Submaster wirken nur auf ihre Fixture-fids — pro
        # Fixture abgefragt. hasattr einmal aufloesen (Hot Path).
        sub_for = getattr(om, "submaster_factor_for", None) if om is not None else None
        fixture_dimmers = getattr(self, "fixture_dimmers", {}) or {}
        global_sub = max(0.0, min(1.0, float(getattr(self, "submaster_level", 1.0)))) * submaster
        for fidi, addrs in inten_addrs.items():
            sub_t = 1.0
            if sub_for is not None:
                try:
                    sub_t = sub_for(fidi)
                except Exception:
                    sub_t = 1.0
            factor = global_sub * sub_t * float(fixture_dimmers.get(fidi, 1.0)) * prog_factor.get(fidi, 1.0)
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

        # 4b-Input. F-20: Art-Net/sACN-EINGANG als Schicht. Extern empfangene DMX-
        #     Werte (Puffer input_layer, vom RX-Thread gefuellt) je Universe mit dem
        #     konfigurierten Modus einmischen: HTP (Hoechstwert), LTP/REPLACE (ersetzt).
        #     RAW (nach dem Dimmer-Master, vor Simple Desk) — externer Eingang wird
        #     NICHT vom eigenen Submaster skaliert; manueller Simple-Desk-Override (4c)
        #     gewinnt weiterhin oben drauf. Leer = kein Eingang = kein Effekt.
        in_state = getattr(self, "input_layer", None)
        if in_state:
            in_lock = getattr(self, "_input_lock", None)
            if in_lock is not None:
                with in_lock:
                    in_layer = {u: dict(ch) for u, ch in in_state.items()}
                    in_modes = dict(self.input_merge_modes)
            else:
                in_layer = {u: dict(ch) for u, ch in in_state.items()}
                in_modes = dict(self.input_merge_modes)
            for univ, chans in in_layer.items():
                su = scratch.get(univ)
                if su is None:
                    continue
                htp = in_modes.get(univ, "HTP") == "HTP"
                for ch, val in chans.items():
                    if not (1 <= ch <= 512):
                        continue
                    v = max(0, min(255, int(val)))
                    if htp:
                        if v > su.get_channel(ch):
                            su.set_channel(ch, v)
                    else:
                        su.set_channel(ch, v)

        # 4c. Simple Desk (ISO-03): manuelle Override-Ebene als OBERSTE Schicht —
        #     NUR wenn 'Manueller Override' aktiv ist (sonst ist Simple Desk reine
        #     Anzeige und wirkt gar nicht). Patched-Kanaele committen ueber
        #     _commit_spans (Schritt 5), freie ueber den Engine-Extra-Pfad inkl.
        #     korrekter Freigabe bei Clear/Override-Aus. Frueher schrieb der Fader
        #     direkt ins Live-Universe (am Renderer vorbei) -> Flackern auf
        #     gepatchten + Zombie auf freien Kanaelen. Jetzt sicht- (ISO-01) und
        #     loeschbar (ISO-02).
        sd_state = getattr(self, "simple_desk", None)
        if sd_state and getattr(self, "simple_desk_override", False):
            sd_lock = getattr(self, "_sd_lock", None)
            if sd_lock is not None:
                with sd_lock:
                    sd_layer = {u: dict(ch) for u, ch in sd_state.items()}
            else:
                sd_layer = {u: dict(ch) for u, ch in sd_state.items()}
            for univ, chans in sd_layer.items():
                su = scratch.get(univ)
                if su is None:
                    continue
                for ch, val in chans.items():
                    if 1 <= ch <= 512:
                        su.set_channel(ch, max(0, min(255, int(val))))

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
                           skip_intensity_for: set | None = None,
                           protect_addrs: dict | None = None):
        """Malt eine {fid: {attr: val}}-Schicht in die Scratch-Universen (LTP:
        nur vorhandene Attribute ueberschreiben, Rest bleibt aus tieferer Schicht).

        skip_intensity_for: fids, fuer die Intensitaets-Attribute NICHT absolut
        geschrieben werden (sie werden stattdessen multiplikativ angewandt, EE-02).
        protect_addrs: {universe: set(addr)} — Nicht-Intensitaets-Kanaele, die der
        Funktions-Layer (Matrix/EFX) treibt und die dieser Layer NICHT ueberschreiben
        darf (WP-6/Abschnitt 8). Intensitaet bleibt unberuehrt von protect (sie wird
        ueber skip_intensity_for multipliziert).

        Mehrkopf (X-6): wiederholt sich ein Attribut in den Kanaelen (z. B. zwei
        Farb-/Tilt-Baenke eines Spiders), liest das N-te Vorkommen den Schluessel
        "attr#N"; fehlt der, spiegelt es "attr" (Kopf 0). Einzelkopf-Geraete und
        nicht separat gesetzte Koepfe verhalten sich damit byte-genau wie bisher."""
        skip = skip_intensity_for or ()
        protect = protect_addrs or {}
        for fid, attrs in fixmap.items():
            try:
                fidi = int(fid)
            except (TypeError, ValueError):
                continue
            entry = self._fix_index.get(fidi)
            if not entry:
                continue
            fx, chans = entry
            # M0.2: Pan/Tilt-Invert/Swap des Geraets anwenden, bevor geschrieben
            # wird (wirkt damit auf Programmer + Cues gleichermassen).
            attrs = apply_pan_tilt_orientation(fx, attrs)
            su = scratch.get(fx.universe)
            if su is None:
                continue
            skip_inten = fidi in skip
            prot = protect.get(fx.universe, ())
            seen_attr: dict[str, int] = {}
            for ch in chans:
                a = ch.attribute
                head = seen_attr.get(a, 0)
                seen_attr[a] = head + 1
                if head == 0:
                    if a not in attrs:
                        continue
                    key = a
                else:
                    key = f"{a}#{head}"
                    if key not in attrs:
                        if a in attrs:
                            key = a   # Kopf>0 spiegelt Kopf 0, falls nicht separat gesetzt
                        else:
                            continue
                attr_l = (a or "").lower()
                is_inten = attr_l in _DIM_INTENSITY_ATTRS
                if skip_inten and is_inten:
                    continue
                addr = fx.address + ch.channel_number - 1
                if not (1 <= addr <= 512):
                    continue
                # WP-6: laufende Funktion besitzt diesen (Nicht-Intensitaets-)Kanal
                # -> Programmer schreibt nicht drueber (kein Blind-Overwrite).
                if (not is_inten) and addr in prot:
                    continue
                v = attrs[key]
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

    def _resolve_cue_stack(self, idx):
        """F-16: Index → Geschwister-Cueliste (oder None). Liest die Liste LIVE, ist
        also auch nach Show-Reloads gültig. Wird als ``CueStack._resolve_sub`` injiziert."""
        if isinstance(idx, int) and 0 <= idx < len(self.cue_stacks):
            return self.cue_stacks[idx]
        return None

    def wire_cue_stack_resolvers(self):
        """F-16: Allen Cuelisten den Sub-Cuelisten-Resolver geben (idempotent).
        Nach jedem Erzeugen/Entfernen/Laden aufrufen."""
        for st in self.cue_stacks:
            st.set_sub_stack_resolver(self._resolve_cue_stack)

    def new_cue_stack(self, name: str = "Neue Cueliste"):
        from .engine.cue_stack import CueStack
        stack = CueStack(name)
        stack.set_sub_stack_resolver(self._resolve_cue_stack)   # F-16
        self.cue_stacks.append(stack)
        # Legacy-Callbacks (stacks_changed) UND zentraler Bus (cue_stack_changed).
        self._emit("stacks_changed", None)
        self._emit("cue_stack_changed", None)
        return stack

    def remove_cue_stack(self, stack):
        self.cue_stacks.remove(stack)
        self._emit("stacks_changed", None)
        self._emit("cue_stack_changed", None)

    def record_cue(self, stack, number: float, label: str = "",
                   fade_in: float = 2.0, fade_out: float = 0.0):
        """Speichert aktuellen Programmer-Inhalt als neue Cue."""
        from .engine.cue import Cue
        values = {fid: dict(attrs) for fid, attrs in self.programmer.items()}
        cue = Cue(number=number, label=label, fade_in=fade_in,
                  fade_out=fade_out, values=values)
        stack.add_cue(cue)
        self._emit("cue_recorded", (stack, cue))
        self._emit("cue_stack_changed", None)
        return cue

    def notify_groups_changed(self, data=None):
        """Zentrale Benachrichtigung bei Fixture-Gruppen-Aenderungen (erstellt/
        geaendert/geloescht). Alle gruppen-konsumierenden Views (Programmer,
        Live View, Matrix, Patcher) lauschen auf GROUP_CHANGED und aktualisieren
        ihre Gruppenlisten ohne manuelles Neuladen (Abschnitt 1)."""
        self._emit("group_changed", data)

    def _emit(self, event: str, data=None):
        """Emit auf Legacy-Callbacks UND auf neuen StateSync routen.

        Wird der Emit aus einem Worker-Thread (MIDI/OSC/Web/Audio) ausgeloest und
        ist ein UI-Marshaller registriert, wird die komplette Zustellung in den
        Qt-UI-Thread verlagert. Damit fassen die Listener (Views) Qt-Widgets nie
        aus einem Fremd-Thread an (sporadische Crashes). Auf dem UI-Thread selbst
        und vor Registrierung laeuft der Emit unveraendert synchron.
        """
        # BUG-01: Während eines Bulk-Vorgangs (Patch-Ersatz beim Laden/Reset)
        # alle Emits unterdrücken. Sonst feuert jedes clear_patch()/add_fixture()
        # synchron patch_changed → die Views refreshen re-entrant mitten im noch
        # inkonsistenten Zustand (programmer_view._refresh_effects_list →
        # QListWidget.clear() → AccessViolation). Der Aufrufer macht nach dem
        # vollständigen Aufbau EINEN gebündelten Refresh.
        if getattr(self, "_suppress_emits", False):
            return
        marshaller = self._ui_marshaller
        if marshaller is not None and threading.get_ident() != self._ui_thread_id:
            try:
                marshaller(lambda e=event, d=data: self._emit_impl(e, d))
                return
            except Exception as e:
                debug_swallow("app_state.marshaller", e)  # Fallback: synchron
        self._emit_impl(event, data)

    def _emit_impl(self, event: str, data=None):
        # Legacy callbacks — ueber eine Kopie iterieren, damit ein Callback, der
        # sich (un)subscribed, die Iteration nicht sprengt.
        for cb in list(self._callbacks):
            try:
                cb(event, data)
            except Exception as exc:
                print(f"[AppState] emit callback error ({event}): {exc}")
        # Neue zentrale Sync-Routing
        try:
            from .sync import SyncEvent
            try:
                ev = SyncEvent(event)
            except ValueError:
                return  # Unbekanntes Event -> ignorieren (kein Crash)
            self.sync.emit(ev, data)
        except Exception as e:
            debug_swallow("app_state.emit", e)

    def set_ui_marshaller(self, fn):
        """Registriert eine Funktion fn(callable)->None, die ihr Argument im
        Qt-UI-Thread ausfuehrt (vom MainWindow gesetzt). Speichert zugleich die
        ID des aufrufenden Threads als 'UI-Thread'."""
        self._ui_marshaller = fn
        self._ui_thread_id = threading.get_ident()


# Cache: (profile_id, mode_name, channel_count) -> list[FixtureChannel] (detached).
# Ohne Cache macht get_channels_for_patched pro Fixture pro Frame (44 Hz) eine
# neue DB-Session — viel zu teuer fuer den zentralen Per-Frame-Renderer.
_channel_cache: dict = {}


def clear_channel_cache():
    """Invalidiert den Channel-Cache (bei jeder Patch-Aenderung aufrufen)."""
    _channel_cache.clear()


class _AttrOverrideChannel:
    """Leichter Proxy um ein ``FixtureChannel`` mit ueberschriebenem
    ``attribute`` (Spider-Dual-Tilt: Pan-Motor als zweiter Tilt). Alle anderen
    Felder/Methoden (channel_number, name, ranges, default_value, …) werden ans
    Original delegiert; das gecachte ORM-Objekt selbst bleibt UNVERAENDERT, damit
    ungeflaggte Geraete desselben Profils nicht mitgezogen werden."""
    __slots__ = ("_ch", "attribute")

    def __init__(self, ch, attribute):
        object.__setattr__(self, "_ch", ch)
        object.__setattr__(self, "attribute", attribute)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_ch"), name)


# Pan-Motoren eines Dual-Tilt-Spiders werden als zusaetzliche Tilt-Koepfe gedeutet.
_DUAL_TILT_REMAP = {"pan": "tilt", "pan_fine": "tilt_fine"}


def _as_dual_tilt_channels(channels):
    """Deutet die Pan-Bewegungskanaele als Tilt um (pan->tilt, pan_fine->tilt_fine),
    damit die GESAMTE Dual-Tilt-Maschinerie greift: is_dual_tilt_fixture/
    tilt_head_count (Erkennung), das SpiderPositionTool + der EFX-Spider-Modus
    (UI), der per-Kopf-Schluessel tilt/tilt#1 (channel_occurrence_keys) und die
    Auto-Scheren-Spiegelung in efx.write(). Reihenfolge bleibt = Kanalreihenfolge,
    der erste (ehemalige Pan-)Motor wird so Kopf 0. Nicht-Bewegungskanaele
    bleiben unangetastet."""
    out = []
    for ch in channels:
        a = (getattr(ch, "attribute", "") or "")
        new_a = _DUAL_TILT_REMAP.get(a)
        out.append(_AttrOverrideChannel(ch, new_a) if new_a else ch)
    return out


def get_channels_for_patched(fixture: PatchedFixture):
    """Laedt die Channel-Objekte fuer ein gepatchtes Geraet (gecached).
    Fallback: Wenn der exakte Mode-Name nicht existiert, wird der erste Mode
    des Profils mit passender Kanalanzahl verwendet (oder einfach der erste).

    Spider-Dual-Tilt: Bei explizitem ``fixture.spider_dual_tilt`` ODER einem
    sicher erkannten, fehlgemappten QLC+-Spider wird der Pan-Motor als zweiter
    Tilt-Kopf ausgegeben (siehe ``_as_dual_tilt_channels``). Die automatische
    Erkennung ist profilbezogen und wird nach dem Laden der Rohkanaele bestimmt."""
    spider_dual = bool(getattr(fixture, "spider_dual_tilt", False))
    key = (getattr(fixture, "fixture_profile_id", None),
           getattr(fixture, "mode_name", None),
           getattr(fixture, "channel_count", None),
           spider_dual)
    cached = _channel_cache.get(key)
    if cached is not None:
        return cached
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from .database.fixture_db import engine, should_auto_mark_dual_tilt
    from .database.models import FixtureProfile, FixtureMode, FixtureChannel
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
            # Ranges eager laden, damit sie auf den detachten (gecachten)
            # Objekten verfuegbar sind — open_value_for()/Quick-Select greifen
            # sonst per Lazy-Load zu und crashen im Per-Frame-Renderer.
            .options(selectinload(FixtureChannel.ranges))
        ).scalars().all()
        profile = s.get(FixtureProfile, fixture.fixture_profile_id)
        auto_dual = should_auto_mark_dual_tilt(profile, result)
        s.expunge_all()
        if spider_dual or auto_dual:
            result = _as_dual_tilt_channels(result)
        _channel_cache[key] = result
        return result


def channel_occurrence_keys(channels):
    """Pro Kanal sein vorkommens-bewusster Programmer-Schluessel als ``(channel,
    key)``-Paare: das erste Vorkommen eines Attributs ist der Basis-Name, jedes
    weitere bekommt ``"attr#N"`` (N = Kopf-Index, X-6/Spider).

    EINE Quelle der Mehrkopf-Vorkommens-Logik (frueher in ``resolve_attr_channels``,
    ``efx.write`` und ``snap_editor.fixture_channel_keys`` je separat ausprogrammiert).
    Spiegelt ``set_programmer_value`` (head>0 -> ``"attr#head"``)."""
    seen: dict[str, int] = {}
    out: list[tuple] = []
    for ch in channels:
        a = ch.attribute
        head = seen.get(a, 0)
        seen[a] = head + 1
        out.append((ch, a if head == 0 else f"{a}#{head}"))
    return out


def resolve_attr_channels(channels, values: dict) -> list[tuple[int, str, int]]:
    """Loest einen attribut-gekeyten Wert-Dict gegen die Kanal-Liste eines
    Fixtures auf — mit DERSELBEN Mehrkopf-Vorkommens-Logik wie
    ``_flush_programmer_to_dmx`` und ``efx.py`` (gemeinsame Quelle:
    ``channel_occurrence_keys``).

    Hintergrund (X-6 / Spider): wiederholte Attribute (z. B. ``color_r`` zweimal
    bei zwei RGBW-Baenken) werden im Programmer/Snap pro Kopf als ``"attr#N"``
    gespeichert (Kopf 0 = ``"attr"``, Kopf 1 = ``"attr#1"`` …). Ein simples
    ``{attr: channel}``-Dict KOLLIDIERT dann (nur das letzte Vorkommen ueberlebt)
    und ein ``ch.attribute in values``-Match findet die ``#N``-Schluessel nie.

    Diese Funktion fuehrt beim Iterieren ueber ``channels`` einen per-Attribut
    ``seen``-Zaehler, bildet ``key = a if head==0 else f"{a}#{head}"`` und schlaegt
    den per-Kopf-Schluessel nach — mit Fallback auf den schlichten Attributnamen
    (Kopf>0 spiegelt Kopf 0, falls nicht separat gesetzt). Kanaele ohne passenden
    Schluessel werden uebersprungen (kein Default geschrieben).

    Rueckgabe: Liste ``(channel_number, matched_key, value)`` in Kanal-Reihenfolge.
    ``matched_key`` ist der tatsaechlich getroffene Dict-Schluessel (``"color_r"``
    oder ``"color_r#1"``) — Aufrufer mit Crossfade (Sequence) brauchen ihn, um den
    Vorwert mit DEMSELBEN Schluessel nachzuschlagen.
    """
    out: list[tuple[int, str, int]] = []
    if not isinstance(values, dict):
        return out
    for ch, key in channel_occurrence_keys(channels):
        if key in values:
            out.append((ch.channel_number, key, values[key]))
        elif ch.attribute in values:
            out.append((ch.channel_number, ch.attribute, values[ch.attribute]))
    return out


def is_spider_fixture(fixture) -> bool:
    """True fuer Doppel-Bar-/Multi-Emitter-Spider. Definierendes Merkmal ist
    **>=2 RGBW-Banks** (zwei `color_r` = zwei unabhaengig gefaerbte Emitter) —
    NICHT die Tilt-Anzahl. Damit greift es sowohl beim klassischen Doppelbar
    (2 Tilt + 2 Banks) als auch beim Einzelkopf-Spider wie 'Speider 14ch'
    (nur 1 Pan + 1 Tilt, ABER zwei Farb-Banken), der sonst als normaler Moving
    Head durchgeht. Steuert den 3D-'spider'-Render (zwei getrennt gefaerbte
    Bars), das 2D-Spider-Symbol/-Icon und die Patch-Spiegel-Option. KONSISTENT
    mit dem Multi-Head-DMX-Pfad (`push_dmx_update`), dessen `heads`-Array auf
    `color_r#1` reagiert.
    Hinweis: ein reiner Tilt-only-Bar OHNE zweite Farb-Bank (Mini-Spider/
    Twinscan) ist BEWUSST kein `is_spider_fixture` — dafuer ist
    `is_dual_tilt_fixture` (Bewegung/Steuerung, >=2 Tilt + kein Pan) zustaendig."""
    try:
        chans = get_channels_for_patched(fixture)
        banks = sum(1 for c in chans if (getattr(c, "attribute", "") or "") == "color_r")
        return banks >= 2
    except Exception:
        return False


def tilt_head_count(fixture) -> int:
    """Anzahl separater Tilt-Motoren/Koepfe (Kanaele mit attribute == 'tilt').
    Fine-Kanaele heissen 'tilt_fine' und zaehlen NICHT mit — ein 16-bit-Single-
    Head bleibt 1, ein Doppelbar-Spider ergibt 2."""
    try:
        return sum(1 for c in get_channels_for_patched(fixture)
                   if (getattr(c, "attribute", "") or "") == "tilt")
    except Exception:
        return 0


def is_dual_tilt_fixture(fixture) -> bool:
    """True fuer ALLE spider-/doppeltilter-artigen Geraete: >=2 separate Tilt-
    Kanaele UND KEIN Pan. Solche Geraete bewegen sich ausschliesslich ueber Tilt
    — das normale XY-Pan/Tilt-Pad ist fuer sie unbrauchbar, daher schalten
    Position- und FX-Tab auf die Spider-Bedienung um (mehrere Tilt-Regler +
    Bewegungsmuster). Breiter als `is_spider_fixture`: greift auch bei Spidern
    mit nur EINER Farbreihe, Farbrad oder ganz ohne Farbe (z. B. Mini-Spider,
    Twinscan, Butterfly) und bei >2 Tilt-Koepfen."""
    try:
        chans = get_channels_for_patched(fixture)
        tilts = sum(1 for c in chans if (getattr(c, "attribute", "") or "") == "tilt")
        pans = sum(1 for c in chans if (getattr(c, "attribute", "") or "") == "pan")
        return tilts >= 2 and pans == 0
    except Exception:
        return False


def is_mover_fixture(fixture) -> bool:
    """True, wenn ``fixture`` ein bewegliches Geraet ist, das eine EFX-Bewegung
    ansteuern kann: klassischer Moving Head (Pan UND Tilt) ODER Dual-Tilt-Spider
    (>=2 Tilt, kein Pan). EINE Quelle fuer alle Mover-Erkennungen (EFX-Editor +
    VC-Auto-Assign), damit beide nicht auseinanderdriften."""
    try:
        attrs = {ch.attribute for ch in get_channels_for_patched(fixture)}
    except Exception:
        return False
    return ("pan" in attrs and "tilt" in attrs) or is_dual_tilt_fixture(fixture)


def mover_fids(restrict_fids=None) -> list[int]:
    """fids aller beweglichen Geraete (siehe ``is_mover_fixture``).
    ``restrict_fids`` (z. B. die aktuelle Auswahl) grenzt ein und BEWAHRT deren
    Reihenfolge (wichtig fuer Fan/Spread); sonst alle gepatchten in
    Patch-Reihenfolge. Bei Fehlern defensiv leer."""
    try:
        patched = {f.fid: f for f in get_state().get_patched_fixtures()}
    except Exception:
        return []
    if restrict_fids is not None:
        seq = [patched[int(f)] for f in restrict_fids if int(f) in patched]
    else:
        seq = list(patched.values())
    return [fx.fid for fx in seq if is_mover_fixture(fx)]


def find_channel(fixture, attribute: str):
    """Erstes FixtureChannel-Objekt eines Geraets mit diesem ``attribute``
    (oder None). Zentraler Ersatz fuer die ueberall duplizierte
    ``for ch ... if ch.attribute == attr``-Schleife (M0.3)."""
    for ch in get_channels_for_patched(fixture):
        if ch.attribute == attribute:
            return ch
    return None


def channel_addr(fixture, attribute: str):
    """DMX-Adresse (1..512) des Kanals mit ``attribute``, oder None wenn das
    Geraet diesen Kanal nicht hat bzw. die Adresse ausserhalb liegt (M0.3)."""
    ch = find_channel(fixture, attribute)
    if ch is None:
        return None
    addr = fixture.address + ch.channel_number - 1
    return addr if 1 <= addr <= 512 else None


def open_value_for(fixture, attribute: str, fallback: int = 255) -> int:
    """Sinnvoller "offener"/Highlight-Wert eines Kanals: bevorzugt eine
    ChannelRange mit ``kind == "open"`` (Mittelwert), sonst ``highlight_value``,
    sonst ``fallback``. Nutzt nur vorhandene Capability-Daten (kein Raten)."""
    ch = find_channel(fixture, attribute)
    if ch is None:
        return fallback
    for rng in (getattr(ch, "ranges", None) or ()):
        if (getattr(rng, "kind", "") or "").lower() == "open":
            return max(0, min(255, (int(rng.range_from) + int(rng.range_to)) // 2))
    hv = getattr(ch, "highlight_value", None)
    return int(hv) if hv is not None else fallback


def apply_pan_tilt_orientation(fx, attrs: dict) -> dict:
    """Wendet ``invert_pan`` / ``invert_tilt`` / ``swap_pan_tilt`` eines
    Geraets auf eine ``{attr: val}``-Schicht an (M0.2).

    Gibt das Original unveraendert zurueck, wenn keine Flag gesetzt ist oder
    die Schicht gar kein Pan/Tilt enthaelt (kein Overhead im heissen Render-
    Pfad). Andernfalls ein NEUES dict (Programmer-/Funktions-State bleibt roh).
    Reihenfolge: erst Swap (Achsen tauschen inkl. Fine), dann Invert je Kanal.
    Fine-Kanaele werden als 16-bit-Paar korrekt mit-invertiert.
    """
    inv_pan = bool(getattr(fx, "invert_pan", False))
    inv_tilt = bool(getattr(fx, "invert_tilt", False))
    swap = bool(getattr(fx, "swap_pan_tilt", False))
    if not (inv_pan or inv_tilt or swap):
        return attrs
    if not any(k in attrs for k in ("pan", "pan_fine", "tilt", "tilt_fine")):
        return attrs
    out = dict(attrs)

    if swap:
        for a, b in (("pan", "tilt"), ("pan_fine", "tilt_fine")):
            va, vb = out.get(a), out.get(b)
            if va is None and vb is None:
                continue
            if vb is not None:
                out[a] = vb
            else:
                out.pop(a, None)
            if va is not None:
                out[b] = va
            else:
                out.pop(b, None)

    def _invert(coarse: str, fine: str):
        if coarse not in out:
            return
        # P9: defensiv gegen kaputte Werte (None/Strings aus OSC/Web/MIDI) —
        # ein ungueltiger Pan/Tilt-Wert darf den Render-Thread nicht stoppen.
        try:
            c = max(0, min(255, int(out[coarse])))
        except (TypeError, ValueError):
            out.pop(coarse, None)
            out.pop(fine, None)
            return
        if fine in out:
            try:
                f = max(0, min(255, int(out[fine])))
            except (TypeError, ValueError):
                f = 0
            combined = 65535 - ((c << 8) | f)
            out[coarse] = (combined >> 8) & 0xFF
            out[fine] = combined & 0xFF
        else:
            out[coarse] = 255 - c

    if inv_pan:
        _invert("pan", "pan_fine")
    if inv_tilt:
        _invert("tilt", "tilt_fine")
    return out


# Singleton
_state: AppState | None = None


def get_state() -> AppState:
    global _state
    if _state is None:
        _state = AppState()
        _state.open_show()
        _state.apply_output_config()
        # Den 44-Hz-Output-Thread NICHT autostarten, wenn das ausdruecklich
        # deaktiviert ist (Tests setzen LIGHTOS_NO_OUTPUT_THREAD): der Thread
        # rendert in _render_frame und emittiert Sync-Events, die cross-thread in
        # Qt marshallt werden. Das racete mit dem pytest-Teardown (processEvents/
        # GC abgemeldeter Widgets) -> sporadische native Access Violation. Tests
        # rendern synchron (tick()/_render_frame()); echte Hardware-Ausgabe wird
        # dort ohnehin nicht geprueft.
        if not os.environ.get("LIGHTOS_NO_OUTPUT_THREAD"):
            _state.output_manager.start()
        _state.start_playback()
    return _state
