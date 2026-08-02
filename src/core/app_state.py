"""Globaler App-State — hält Show-Daten und Engine-Referenzen zusammen."""
from __future__ import annotations
import contextlib
import os
import sys
import threading
import time
from dataclasses import dataclass
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from .database.models import PatchedFixture, create_all_idempotent
from .database.fixture_db import get_channels
from .dmx.universe import Universe
from .dmx.output_manager import OutputManager
from .dmx.enttec_pro import diagnose_port as diagnose_enttec_port
from .debug_log import debug_swallow
from .attr_groups import ATTR_GROUPS, classify_attr
from .stage.scene_graph import SceneGraph
from .stage.scene_adapters import _DockView, _LiveViewDict, _SceneBackedDict, _ViewRegistry

# Show-Datenbank. Per LIGHTOS_SHOW_DB umlenkbar — so können Tests (conftest setzt
# eine Temp-DB) laufen, ohne die echte Show-DB der laufenden App anzufassen.
SHOW_DB_PATH = os.environ.get("LIGHTOS_SHOW_DB", "data/current_show.db")


# STAB-CURSHOW: Bekannte Cloud-Sync-Ordner-Marker. Liegt die Show-DB in einem
# solchen Ordner, ist WAL unsicher — der Sync-Client fasst die -wal/-shm-mmap-
# Sidecar-Dateien mitten in einem Schreibvorgang an und kann die geteilte DB
# korrumpieren. Dann bleibt es beim DELETE-Journal (busy_timeout traegt den Fix
# ohnehin allein). Marker in Kleinschreibung; gematcht als Teilstring im Pfad.
_CLOUD_SYNC_MARKERS = (
    "onedrive", "dropbox", "google drive", "googledrive", "\\google\\drive",
    "icloud", "\\box\\", "\\box sync", "nextcloud", "creative cloud files",
    "pcloud", "mega", "sync.com",
)


# STAB-WAL-NET: Dateisystem-Typen, auf denen WAL sicher ist. ERLAUBNISLISTE —
# was hier nicht steht, bekommt kein WAL. Aufgenommen sind lokale
# Platten-Dateisysteme; NICHT drin sind alle Netz-/Verteil-Dateisysteme (nfs,
# cifs, smb3, 9p, ceph, glusterfs, afs, fuse.sshfs, fuse.rclone, davfs), auf
# denen SQLite den mmap-Shared-Memory der -shm-Datei nicht zuverlaessig
# bekommt, sowie alles Unbekannte.
#
# overlay steht bewusst NICHT drin: in einem Container ueberlagert es haeufig
# ein Netz-Volume, und von aussen ist der darunterliegende Speicher nicht zu
# sehen. tmpfs dagegen ist lokal und fuer WAL unproblematisch — dass es
# fluechtig ist, ist eine andere Frage als die nach Korruption.
_WAL_SICHERE_FSTYPES = frozenset({
    "ext2", "ext3", "ext4", "btrfs", "xfs", "f2fs", "jfs", "reiserfs",
    "zfs", "bcachefs", "tmpfs", "vfat", "exfat", "ntfs3", "fuseblk",
})


def _linux_fstype(pfad: str, quelle: str = "/proc/self/mountinfo") -> str:
    """Dateisystem-Typ des Mounts, der ``pfad`` traegt ("" = unbekannt).

    Gelesen aus ``/proc/self/mountinfo``, weil das ohne Zusatzpakete und ohne
    Aufruf eines externen Programms geht. Gewinnt der LAENGSTE passende
    Mount-Punkt: bei verschachtelten Mounts (``/`` und ``/home``) traegt den
    Pfad der speziellere.

    Zeilenformat: Feld 5 ist der Mount-Punkt, nach dem Trenner ``-`` folgt der
    Dateisystem-Typ. Die Zahl optionaler Felder VOR dem Trenner ist variabel —
    deshalb wird am ``-`` gesplittet statt ein festes Feld gezaehlt.

    ``quelle`` ist nur fuer Tests da: so laesst sich eine gestellte
    mountinfo-Tabelle einspeisen (NFS, verschachtelte Mounts, kaputte Zeilen),
    ohne den Rechner umzubauen.
    """
    try:
        with open(quelle, "r", encoding="utf-8") as fh:
            zeilen = fh.readlines()
    except OSError:
        return ""
    treffer, beste_laenge = "", -1
    for zeile in zeilen:
        links, _, rechts = zeile.partition(" - ")
        felder = links.split()
        rest = rechts.split()
        if len(felder) < 5 or not rest:
            continue
        punkt = felder[4].replace("\\040", " ")
        typ = rest[0]
        if pfad == punkt or pfad.startswith(punkt.rstrip("/") + "/"):
            if len(punkt) > beste_laenge:
                treffer, beste_laenge = typ, len(punkt)
    return treffer


def _is_local_writable_path(path: str) -> bool:
    """WAL-Guard (STAB-CURSHOW): ``True`` nur, wenn ``path`` auf einem lokalen
    Fixed-Laufwerk liegt UND nicht in einem bekannten Cloud-Sync-Ordner.

    WAL nutzt mmap-Shared-Memory (``-wal``/``-shm``) und wird auf SMB-/Netz-
    laufwerken NICHT zuverlaessig unterstuetzt; Cloud-Sync-Clients korrumpieren
    die Sidecars. Im Zweifel ``False`` -> ``journal_mode`` bleibt ``DELETE``
    (kein Nachteil ggue. heute, nur der WAL-Reader-Snapshot-Bonus entfaellt)."""
    try:
        ap = os.path.abspath(path)
        low = ap.replace("/", "\\").lower()
        # UNC / Netzpfad (\\server\share, \\?\UNC\...).
        #
        # ★ Gegen den ROHEN Pfad geprueft, nicht nur gegen abspath(): auf Linux
        # ist ein UNC-Pfad NICHT absolut, also stellt abspath() das
        # Arbeitsverzeichnis davor und der \\-Praefix verschwindet. Solange der
        # Linux-Zweig pauschal False lieferte, fiel das nicht auf — mit dem
        # fstype-Check (STAB-WAL-NET) waere daraus WAL auf einem Netzpfad
        # geworden, also genau die gefaehrliche Richtung. Der Bestandstest
        # test_wal_guard_rejects_unc_and_sync_folders hat es sofort gemeldet.
        roh = (path or "").replace("/", "\\").lower()
        if (low.startswith("\\\\") or low.startswith("\\\\?\\unc")
                or roh.startswith("\\\\") or roh.startswith("\\\\?\\unc")):
            return False
        # Bekannte Cloud-Sync-Ordner — auch auf Fixed-Disk unsicher.
        if any(m in low or m in roh for m in _CLOUD_SYNC_MARKERS):
            return False
        # Windows: nur DRIVE_FIXED zulassen (kein Wechsel-/Netz-/RAM-Laufwerk).
        if sys.platform == "win32":
            import ctypes
            drive = os.path.splitdrive(ap)[0]
            if not drive:
                return False
            if not drive.endswith("\\"):
                drive += "\\"
            DRIVE_FIXED = 3
            t = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(drive))
            if int(t) != DRIVE_FIXED:
                return False
            return True
        # Linux (STAB-WAL-NET): Bis 2026-08-01 stand hier ein hartes ``False``,
        # weil es "keinen portablen lokaler-vs-Netz-Check" gebe. Das stimmt fuer
        # POSIX allgemein — auf LINUX aber nicht: /proc/self/mountinfo nennt den
        # Dateisystem-TYP des tragenden Mounts, und genau daran haengt die Frage.
        #
        # Der Preis des harten False war real: Davids Show-DB liegt auf lokalem
        # ext4 und lief trotzdem im DELETE-Journal — der WAL-Reader-Snapshot
        # entfiel auf der Maschine, fuer die er gedacht war.
        #
        # Weiterhin eine ERLAUBNISLISTE, keine Verbotsliste: ein unbekannter
        # Dateisystem-Typ bleibt ohne WAL. Eine Verbotsliste muesste jedes
        # kuenftige Netz-Dateisystem kennen und waere beim ersten unbekannten
        # fail-open — also genau in der gefaehrlichen Richtung.
        if sys.platform.startswith("linux"):
            return _linux_fstype(ap) in _WAL_SICHERE_FSTYPES
        # Andere POSIX-Systeme (macOS/BSD): unveraendert konservativ.
        return False
    except Exception:
        # Jede Unsicherheit -> konservativ kein WAL.
        return False


def _set_sqlite_pragmas(dbapi_conn, wal_ok: bool) -> None:
    """SQLAlchemy ``connect``-Callback (STAB-CURSHOW): setzt pro physischer
    Show-DB-Connection die Concurrency-PRAGMAs.

    * ``busy_timeout=5000`` IMMER (pro Connection, risikofrei, auch auf
      Netzlaufwerk): macht aus sofortigem ``SQLITE_BUSY`` ein kurzes Warten, so
      dass zwei echte App-Prozesse ihre (jetzt atomaren) Patch-Replaces
      serialisieren statt sich zu korrumpieren.
    * ``journal_mode=WAL`` + ``synchronous=NORMAL`` NUR wenn ``wal_ok`` (lokaler
      Fixed-Pfad) — best-effort, Rueckgabewert verifiziert, nie crashend."""
    try:
        cur = dbapi_conn.cursor()
        try:
            cur.execute("PRAGMA busy_timeout=5000")
            if wal_ok:
                cur.execute("PRAGMA journal_mode=WAL")
                row = cur.fetchone()
                mode = (row[0] if row else "") or ""
                if str(mode).lower() == "wal":
                    # synchronous=NORMAL ist mit WAL crash-sicher und schneller.
                    cur.execute("PRAGMA synchronous=NORMAL")
                # Bleibt der Modus nicht 'wal' haengen (z. B. Netz-/Sync-Ordner
                # trotz Guard) -> nichts weiter tun, DELETE-Journal bleibt.
            else:
                # `journal_mode` ist eine PERSISTENTE Datei-Eigenschaft: war die DB
                # je (an einem sicheren Ort) auf WAL, bliebe sie es ueber Neustarts
                # hinweg — auch nachdem der Guard den Pfad jetzt als unsicher (Netz-/
                # Cloud-Sync-Ordner) einstuft. Reines "WAL nicht einschalten" reicht
                # daher nicht; eine geerbte WAL-Datei aktiv auf DELETE zurueckschalten
                # (best-effort; checkpointet + entfernt die -wal/-shm-Sidecars).
                cur.execute("PRAGMA journal_mode")
                row = cur.fetchone()
                mode = (row[0] if row else "") or ""
                if str(mode).lower() == "wal":
                    cur.execute("PRAGMA journal_mode=DELETE")
        finally:
            cur.close()
    except Exception as e:
        # PRAGMAs duerfen das Oeffnen der Show nie brechen.
        debug_swallow("app_state._set_sqlite_pragmas", e)

# NET-05: Art-Net/sACN-Eingangs-Timeout. Eine externe Quelle, die laenger als dies
# nichts mehr gesendet hat, gilt als weg und wird aus input_layer verworfen — sonst
# frieren ihre letzten Werte die Kanaele dauerhaft ein (Blackout skaliert den Input
# nicht). E1.31-2018 nennt ~2,5 s Network Data Loss; Art-Net analog.
INPUT_SOURCE_TIMEOUT_S = 2.5

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
    # cmy_c/m/y = real emittierte CMY-Namen (QXF-Import/Fixture-Editor); ohne sie
    # kennt die Farb-Feature-Dimmung / GM-Farbmaske CMY-Mover nicht als Farbe.
    "cmy_c", "cmy_m", "cmy_y",
    "cyan", "magenta", "yellow",
})

# A3D-37: SUBTRAKTIVE Farbkanaele (CMY). Sie bleiben in _DIM_COLOR_ATTRS (die
# GM-Farbmaske / Farb-Feature-Dimmung braucht CMY-Mover als Farbe), duerfen aber
# NICHT als Intensity-/Dimm-Fallback dienen: der Dimmer-Master/GM/Blackout skaliert
# die Fallback-Adressen MULTIPLIKATIV Richtung 0 — bei ADDITIVEM RGB(W) = dunkler
# (korrekt), bei SUBTRAKTIVEM CMY aber = Farbe OEFFNEN = heller/weiss (invertiert).
# Ein CMY-only-Mover ohne echten Dimmer wuerde so beim Blackout AUFHELLEN statt
# dunkeln. Deshalb in _fixture_intensity_addrs ausgenommen.
_SUBTRACTIVE_COLOR_ATTRS = frozenset({
    "cmy_c", "cmy_m", "cmy_y", "cyan", "magenta", "yellow",
})

# A3D-02: Nur diese Laser-Attribute sind "output-/emissions-relevant" und heben den
# DMX-Laser-NOT-AUS-Latch wieder auf ("wieder an" = bewusstes Einschalten): die
# Betriebsart/Musterbank (laser_bank), die Muster-/Gobo-Auswahl (gobo_wheel), der
# Shutter und die Effekt-/Programm-Auswahl (macro — treibt bei macro-basierten
# Party-Lasern wie dem PARTYLASER-Builtin ohne laser_bank/gobo_wheel die Emission).
# Ein harmloses Attribut (Position laser_x/laser_y, Zoom, Punktfarbe, Twist, Raster,
# …) darf den NOT-AUS NICHT lösen — sonst öffnet ein Positions-/Farb-Nudge den Laser
# trotz gedrücktem Not-Aus wieder. Annahme wie bei UXT-12: Betriebsart/Shutter/Macro
# 0 = Laser aus; die genannten Attribute sind die Betriebsart-/Emissions-Gates.
# CDX-13 (David-Entscheidung 2026-07-20, SAFETY vor Usability): `intensity` bleibt
# BEWUSST DRAUSSEN. Ein FB4-/Streaming-Laser exponiert seine Helligkeit als
# `intensity`, könnte also per Helligkeitsregler nicht wieder scharfgeschaltet
# werden — das ist gewollt: `intensity` ist zu breit, ein Szenen-/Snapshot-/
# Palette-Apply mit Laser-`intensity>0` (über set_programmer_value) würde den
# NOT-AUS sonst UNGEWOLLT lösen. Bewusstes Wieder-Scharfschalten läuft über den
# FB4-„Cue"-Kanal (= `gobo_wheel`, bereits whitelisted). Regressionstest:
# tests/test_laser_dmx_estop.py::test_intensity_on_laser_keeps_latch.
_LASER_REARM_ATTRS = frozenset({"shutter", "laser_bank", "gobo_wheel", "macro"})

# LAS-04: Netzwerk-Protokolle ohne DMX-Adressraum (PatchedFixture.protocol).
LASER_NETWORK_PROTOCOLS = ("etherdream", "idn")


def fixture_uses_dmx(fx) -> bool:
    """True, wenn das Geraet ueber den DMX-Adressraum ausgegeben wird.
    Netzwerk-Laser (protocol in LASER_NETWORK_PROTOCOLS) haben universe/address
    nur als bedeutungslose Platzhalter — JEDE Stelle, die
    ``fx.address + ch.channel_number`` rechnet, MUSS vorher hier fragen, sonst
    schreibt der Platzhalter in die Spans echter Geraete. Fehlendes/leeres
    Feld (Alt-Objekte, Mocks) zaehlt als DMX."""
    proto = (getattr(fx, "protocol", "") or "dmx").lower()
    return proto not in LASER_NETWORK_PROTOCOLS

# Feature-Dimmer-Master (F-26): ein per-Slot multiplikativer Master, der die
# Helligkeit (bzw. gewaehlte Feature-Kanaele) einer Fixture-Menge skaliert —
# effekt-UNABHAENGIG, weil er am fertig gerenderten Output ansetzt (Render-Schritt
# 4b²), NACH allen Effekten/Programmer. Default-Feature = "Intensity" (Helligkeit).
# Anders als fixture_dimmers (flach, fid->float, "last writer wins") hat jeder Slot
# eine eigene Identitaet -> mehrere unabhaengige Submaster koexistieren und stapeln
# multiplikativ (Produkt). Wird pro Frame vom VC-Slider gesetzt (Gruppen-/Auswahl-
# fids LIVE aufgeloest), NICHT in der Show persistiert (der Slider persistiert).
_DEFAULT_FEATURE_SET = frozenset({"Intensity"})


@dataclass
class FeatureDimmer:
    fids: frozenset = frozenset()
    features: frozenset = frozenset()   # leer = {"Intensity"} (Helligkeit)
    level: float = 1.0


class AppState:
    def __init__(self):
        self._show_engine = None
        self.output_manager = OutputManager()
        self.universes: dict[int, Universe] = {}
        # HW-5b: je Enttec-Universe der Befund aus resolve_port() — None = alles
        # unauffaellig, sonst ein zeigbarer Satz ("Port COM_FAKE existiert hier
        # nicht — benutze /dev/ttyUSB0"). Der Statusbalken liest das, damit ein
        # falsch konfigurierter Adapter nicht laenger als gruen durchgeht.
        self.enttec_port_notes: dict[int, str | None] = {}
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
        # FM-HEADLAYOUT Slice 5: feine Auswahl auf Zell-Ebene ("fid" ODER
        # "fid:head"). selected_fids bleibt die dedup-Basisliste und damit der
        # unveraenderte Vertrag fuer alle SELECTION_CHANGED-Konsumenten; beide
        # werden AUSSCHLIESSLICH in set_selected_cells fortgeschrieben.
        self.selected_cells: list[str] = []
        self._selected_heads: dict[int, set] = {}
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
        # VIZ-11 (Schritt 3+4): kanonischer Store ist ab jetzt der SceneGraph
        # (state._scene); die 5 Legacy-Felder darunter sind schreibende
        # dict-Views/ein str-Attribut, die den Graphen durchreichen (siehe
        # docs/VIZ11_SCENEGRAPH_DESIGN.md (b) + src/core/stage/scene_adapters.py).
        # _view_registry haelt eine schwache Referenzliste aller lebenden
        # dict-Views, damit eine direkte Graph-Mutation (nicht ueber die View)
        # per _notify_scene_changed() alle Views frisch resyncen kann.
        self._scene: SceneGraph = SceneGraph()
        self._view_registry: _ViewRegistry = _ViewRegistry()
        self._active_stage_name: str = "simple"
        # Transientes Backing-dict fuer schema-fremde live_view_positions-Werte
        # (Test-Sentinel, s. scene_adapters._LiveViewDict) -- lebt in AppState,
        # damit es zwischen zwei Property-Zugriffen ueberlebt (der Getter
        # erzeugt bei jedem Aufruf eine frische View-Instanz).
        self._live_view_transient: dict = {}
        # positions: {fid: (x, y, z)} ; active_stage_name: preset-key oder User-Stage-Name
        # (Property weiter unten; Backing-Store ist state._scene.)
        # Multi-Achsen-Ausrichtung (rx, ry, rz) in GRAD je Fixture im 3D-Visualizer:
        # rx = Kippen (Pitch, Boden->Decke), ry = Drehen um die Hochachse (Yaw),
        # rz = Roll. Getrennt von positions. Abwaertskompatibel zu Alt-Shows, die
        # nur einen Y-Float gespeichert haben (siehe coords.normalize_rotation +
        # show_file.load_show). Erlaubt spaeter MH-Auto-Aim (volle Montage-Lage).
        # (Property weiter unten; Backing-Store ist state._scene.)
        # Andock-Beziehungen: {fid: stage_element_id} — Strahler haengt an/auf
        # diesem Buehnen-Element (Trasse/Plattform/Boden). Bewegt sich das
        # Element, wandert der Strahler mit. Geht mit in die .lshow.
        # (Property weiter unten; Backing-Store ist state._scene.)
        # Live-View-Positionen (2D, {fid: (x, y)}) — eigene Persistenz, entkoppelt
        # vom 3D-Visualizer. Migration aus visualizer_positions beim Laden, falls leer.
        # (Property weiter unten; Backing-Store ist state._scene.)
        # P4: Show-spezifische Live-View-Einstellungen (zoom, grid_size, snap,
        # grid_visible, world_w/h) — von der Live View gepflegt, wandert mit
        # save_show/load_show. Leer = ui_prefs-Defaults (alte Shows).
        self.live_view_meta: dict = {}
        # VIZ-13 Schritt 3b-K-2: benannte Kamerapositionen des 3D-Visualizers
        # (View-State, NICHT Szenegraph -- siehe docs/VIZ13_JS_NEUAUFBAU_DESIGN.md
        # Abschnitt (c) "Persistenz-Schnitt"). Liste von
        # {name, mode, theta, phi, radius, target:[x,y,z], orthoSize, orthoPan:[x,z]}.
        # Additiver Show-Block (visualizer.named_cameras), KEIN SHOW_VERSION-
        # Bump -- alte Shows ohne den Block laden mit leerer Liste (siehe
        # show_file.py). Einfaches plain-list-Attribut wie live_view_meta,
        # kein SceneGraph-Backing (keine Fixture-Topologie).
        self.visualizer_named_cameras: list = []
        # VIZ-15: fids, deren Lichtkegel im 3D AUSGEBLENDET ist. Der globale
        # "Lichtkegel anzeigen"-Schalter ist alles-oder-nichts; wer ein einzelnes
        # Geraet aus der Sicht nehmen will (Blinder, Zuschauerblender, ein Mover,
        # der die Kamera zustellt), musste bisher alle Kegel opfern.
        #
        # Wie named_cameras ein einfaches plain-Attribut: KEIN SceneGraph-Backing
        # (das traegt Topologie/Transformationen, nicht Darstellungswuensche) und
        # ein ADDITIVER Show-Block (visualizer.beams_off) ohne SHOW_VERSION-Bump —
        # alte Shows ohne den Block laden mit leerer Menge, also unveraendert.
        # Set statt Liste: die Frage ist immer "ist DIESE fid drin".
        self.visualizer_beams_off: set = set()
        # VIZ-LABELS: globaler Schalter, ob die Fixture-Namens-Labels ("#<fid>
        # <Name>"-Sprites) im 3D-Visualizer sichtbar sind. EINE Quelle fuer alle
        # 3D-Ansichten (eingebettete Live-View-3D, Pop-out-Fenster, volles
        # VisualizerWindow) — jede liest den Wert in ihrem _collect_settings() und
        # schreibt ihn bei ihrem Toggle, damit die UIs nicht auseinanderlaufen.
        # Reine View-Praeferenz: bewusst NICHT in der .lshow persistiert (wie
        # brightness/showCones — transient, Default beim Start). Default AN
        # (heutiges Verhalten: Labels innerhalb 28 m sichtbar).
        self.show_fixture_labels: bool = True
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
        # UXT-12: Laser-NOT-AUS für DMX-Muster-Laser (L2600 & Co.). Der Netzwerk-
        # Streamer wird separat über estop_all/armed verriegelt; DMX-Laser geben
        # über normale Kanäle aus und würden nach NOT-AUS weiterlaufen. Aktiv =
        # der Renderer zwingt alle Laser-Kanäle als OBERSTE Ebene auf 0.
        self.laser_estop_active: bool = False
        self._laser_estop_addrs: dict[int, frozenset] = {}   # univ -> Laser-Adressen
        self._laser_fids: frozenset = frozenset()            # fids aller DMX-Laser
        # STAB-15: Der 44-Hz-Renderer (_render_frame) liest den Render-Plan
        # (_fix_index/_default_frame/_commit_spans/_patched_set/_laser_estop_addrs),
        # waehrend _rebuild_render_plan ihn beim Umpatchen feldweise austauscht.
        # Ohne Schutz koennte der Renderer einen HALB getauschten Plan sehen (neue
        # fix_index + alte spans -> 1-Frame-Glitch/Crash). Dieses Lock haelt beide
        # nur KURZ: der Rebuild baut den Plan lokal fertig und tauscht die Felder
        # gebuendelt darunter; _render_frame zieht darunter EINEN konsistenten
        # Snapshot in Locals und rechnet dann daraus (wie prog/simple_desk/input).
        self._plan_lock = threading.RLock()
        # Nicht-gepatchte Adressen, die Funktionen (z. B. ScriptFunction setdmx)
        # im letzten Frame geschrieben haben — fuer korrektes Freigeben.
        self._engine_extra_prev: dict[int, set] = {}
        # A3D-18: Adressen, die ein Rebuild als "war gepatcht, jetzt frei" markiert
        # hat und die der Render-Thread im naechsten Frame-Commit (Schritt 5, NACH
        # dem Span-Commit) final nullt — race-fest gegen einen nachlaufenden
        # Alt-Plan-Commit. {universe: set[addr]}.
        self._pending_release: dict[int, set] = {}
        # CDX-22: Deferral-Fenster fuer die A3D-18-Freigabe (s.
        # deferred_unpatched_release). > 0 = laufender MEHRSTUFIGER Patch-Tausch
        # (Show-Load: leerer Patch -> neuer Patch); entpatchte Adressen werden
        # dann nur in _deferred_release gemerkt und erst beim Verlassen EINMAL
        # gegen den dann gueltigen _patched_set freigegeben.
        self._defer_release_depth: int = 0
        self._deferred_release: dict[int, set] = {}
        # CDX-22b: dasselbe Fenster fuer die STAB-14-Freigabe script-getriebener
        # ROH-Adressen. Ohne das nullte _release_engine_extra sie mitten im
        # Ladefenster sofort — dieselbe Puls-Klasse wie CDX-22, nur eine Ebene
        # tiefer. {universe: set[addr]}.
        self._deferred_engine_extra: dict[int, set] = {}
        # Simple Desk = manuelle Roh-Override-Ebene (ISO-03). {universe: {ch: val}},
        # nur explizit gesetzte Kanaele. Wird im _render_frame als OBERSTE Schicht
        # angewandt (deterministisch jeden Frame) — frueher schrieb der Fader direkt
        # ins Live-Universe am Renderer vorbei (Flackern auf gepatchten Kanaelen +
        # unsichtbarer Zombie auf freien). Sicht- (ISO-01) und loeschbar (ISO-02).
        self.simple_desk: dict[int, dict[int, int]] = {}
        self._sd_lock = threading.RLock()
        # QA-LIVE: Szenen-Vorschau ist ein EINMALIGER Render-Layer statt eines
        # direkten Universe-Write aus dem UI. Dadurch durchlaeuft sie Master,
        # Blackout und den Laser-NOT-AUS wie jeder andere Output.
        self._scene_preview: dict[int, dict[int, int]] = {}
        self._scene_preview_lock = threading.RLock()
        # F-20: Art-Net/sACN-EINGANG als eigene Render-Schicht. Die Empfaenger
        # (artnet_input/sacn_input) schreiben ihre gemergten Werte NICHT mehr direkt
        # ins Live-Universe (das ueberschrieb der Per-Frame-Renderer auf gepatchten
        # Kanaelen), sondern in diesen Puffer; _render_frame mischt ihn deterministisch
        # je Universe mit dem konfigurierten Modus. Leer = kein Eingang = kein Effekt.
        #   input_layer:       {out_universe: {channel(1..512): value}}
        #   input_merge_modes: {out_universe: "HTP"|"LTP"|"REPLACE"}
        self.input_layer: dict[int, dict[int, int]] = {}
        self.input_merge_modes: dict[int, str] = {}
        # WEB-01: Kanaele, die vom Web-/OSC-Remote ueber set_input_channel gesetzt
        # wurden ({out_univ: set(channel)}). Sie liegen mit in input_layer, sind
        # aber DISKRETE Einzelbefehle (kein Stream) -> der Renderer nimmt sie vom
        # NET-05-Source-Timeout aus (nie verworfen) und wendet sie als REPLACE an,
        # unabhaengig vom Per-Universe-Merge-Mode der Art-Net/sACN-Quelle. Freigabe
        # nur ueber clear_remote_input()/clear_programmer (Release-Pfad).
        self._remote_input_channels: dict[int, set[int]] = {}
        # NET-05: letzter Empfangszeitpunkt je out_univ (time.monotonic) fuer den
        # Source-Timeout — der Renderer verwirft still gewordene Quellen.
        self.input_last_seen: dict[int, float] = {}
        # NET-07: Merge-Ziele, die NICHT als Output konfiguriert/gepatcht sind (nicht
        # in self.universes). scratch wird nur aus self.universes gebaut, also verwirft
        # _render_frame solche empfangenen Kanaele STILL (scratch.get(univ) is None ->
        # continue) — die UI zeigt trotzdem "Aktiv". Dieser Zaehler je out_univ macht
        # das erkennbar (dropped-because-unconfigured); die Status-Abfrage kann ihn
        # lesen. apply_input_merge pflegt ihn und warnt EINMAL pro out_univ (kein
        # Per-Frame-Spam). Wird das Ziel spaeter gepatcht, faellt der Eintrag weg.
        self.input_unconfigured: dict[int, int] = {}
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
        # BUG-FBW Slice 2: Moment-Override „Alles Weiß" (Render-Schritt 4a³).
        # None = aus. Gebaut von set_all_white(), nicht pro Frame gerechnet.
        self._all_white_map: dict[int, dict[str, int]] | None = None
        # F-26: Feature-Dimmer-Master pro Slot (stabile Slider-ID -> FeatureDimmer).
        # Effekt-unabhaengiger Helligkeits-/Feature-Master, s. Render-Schritt 4b².
        # STAB-13: _fd_lock schuetzt feature_dimmers gegen den lock-freien Renderer
        # (Schritt 4b² snapshottet unter diesem Lock) — sonst wirft eine GROESSEN-
        # Aenderung aus dem UI-Thread (Slot anlegen/pop/clear) "dict changed size
        # during iteration" und verwirft den ganzen Frame.
        self.feature_dimmers: dict = {}
        self._fd_lock = threading.RLock()
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
        # LAS-07b: gezeichnete Laser-Muster (Show-persistent, Bibliothek für
        # den Zeichen-Editor + die Figur-Auswahl der Laser-Steuerseite).
        self.laser_figures: list = []
        # LAS-18b: gemerkte WERKSMUSTER-Slots für DMX-Muster-Laser (Bank/Wert
        # + optionales Nutzer-Foto) — Kachel-Picker der Laser-Steuerseite.
        self.laser_patterns: list = []
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

    # ── VIZ-11: SceneGraph-Adapter (Schritt 3+4) ────────────────────────────────
    # Die 5 Legacy-Felder sind Properties ueber state._scene. Getter liefern
    # eine frische View-Instanz (dict-Subklasse, siehe scene_adapters.py);
    # Setter fangen Ganz-Dict-/Ganz-Wert-Zuweisung ab und speisen sie in den
    # Graphen ein. isinstance(x, dict) bleibt fuer alle 4 dict-Felder True.

    def _notify_scene_changed(self) -> None:
        """Muss aufgerufen werden, wenn state._scene DIREKT (nicht ueber eine
        der 4 dict-Views) mutiert wurde, damit lebende Views wieder synchron
        sind (siehe Design (b), Konsistenzregel)."""
        self._view_registry.resync_all()

    def set_scene(self, scene: SceneGraph) -> None:
        """Review-Fix (state._scene-Ersetzung desynct lebende Views): einzige
        erlaubte Stelle, um ``state._scene`` komplett durch ein NEUES
        SceneGraph-Objekt zu ersetzen (load_show/reset_show). Ein blosses
        ``state._scene = neuer_graph`` liesse alle bereits konstruierten
        ``_SceneBackedDict``/``_DockView``/``_LiveViewDict``-Instanzen (die
        ihre ``self._scene``-Referenz im Konstruktor binden) permanent am
        ALTEN, verwaisten Graphen haengen. ``set_scene`` haengt daher zuerst
        die Registry-Views auf den neuen Graphen um (jede lebende View bindet
        ``_scene`` neu) und resynct danach EINMAL gebuendelt."""
        self._scene = scene
        with self._view_registry.suspend():
            for view in list(self._view_registry._views):
                view._scene = scene
            self._view_registry.resync_all()

    @property
    def visualizer_positions(self) -> dict:
        return _SceneBackedDict(self._scene, "pos", self._view_registry)

    @visualizer_positions.setter
    def visualizer_positions(self, value: dict) -> None:
        # Ganz-Dict-Zuweisung = vollstaendige Ersetzung: Fixtures, die im neuen
        # Dict fehlen, verlieren ihre Node komplett (pos+rot+dock in EINEM,
        # wie ein einzelnes pop). ANNAHME (von allen realen Call-Sites erfuellt,
        # siehe show_file.load_show/reset_show + Tests): visualizer_positions
        # wird vor visualizer_rotations/visualizer_docks zugewiesen, sonst
        # wuerden hier bereits gesetzte Rotationen/Docks mit verloren gehen.
        # Review-Fix (O(n^2)-Resync): die gesamte Bulk-Schreibschleife laeuft
        # unter EINEM suspend()-Block -> genau EIN resync_all() am Ende statt
        # einem pro Eintrag.
        view = _SceneBackedDict(self._scene, "pos", self._view_registry)
        with self._view_registry.suspend():
            view.clear()
            for fid, pos in dict(value or {}).items():
                view[fid] = pos

    @property
    def visualizer_rotations(self) -> dict:
        return _SceneBackedDict(self._scene, "rot", self._view_registry)

    @visualizer_rotations.setter
    def visualizer_rotations(self, value: dict) -> None:
        view = _SceneBackedDict(self._scene, "rot", self._view_registry)
        with self._view_registry.suspend():
            for fid, rot in dict(value or {}).items():
                view[fid] = rot
            # Fixtures, die im neuen Dict fehlen, auf (0,0,0) zuruecksetzen (Ganz-
            # Dict-Zuweisung ist eine vollstaendige Ersetzung, kein Merge).
            stale = [n.fixture_id for n in self._scene.fixtures()
                     if n.fixture_id not in dict(value or {})]
            for fid in stale:
                view[fid] = (0.0, 0.0, 0.0)

    @property
    def visualizer_docks(self) -> dict:
        return _DockView(self._scene, self._view_registry)

    @visualizer_docks.setter
    def visualizer_docks(self, value: dict) -> None:
        view = _DockView(self._scene, self._view_registry)
        with self._view_registry.suspend():
            view.clear()
            for fid, sid in dict(value or {}).items():
                view[fid] = sid

    @property
    def live_view_positions(self) -> dict:
        return _LiveViewDict(self._scene, self._view_registry, self._live_view_transient)

    @live_view_positions.setter
    def live_view_positions(self, value: dict) -> None:
        self._warn_live_view_overwrites_3d(value)
        view = _LiveViewDict(self._scene, self._view_registry, self._live_view_transient)
        with self._view_registry.suspend():
            view.clear()
            for fid, pos in dict(value or {}).items():
                view[fid] = pos

    def _warn_live_view_overwrites_3d(self, value: dict) -> None:
        """VIZ-LIVEVIEW-FOOTGUN: warnen, wenn eine 2D-Zuweisung ausdrueckliche
        3D-Positionen verschiebt.

        2D und 3D sind zwei Projektionen DESSELBEN SceneGraph-Knotens: ein
        2D-Pixelpaar leitet ueber ``live_to_world3d`` die 3D-x/z ab (die Hoehe
        bleibt). Das ist im interaktiven Betrieb genau richtig — man zieht ein
        Symbol im Grundriss und das Geraet wandert. In einem **Build-Skript**
        ist es eine Falle: wer erst die Truss-Koordinaten setzt und danach ein
        2D-Raster, ueberschreibt die eben gesetzten x/z still (Mover landeten in
        der Mega-Arena-Show bei z=20 m). Nur Fixtures OHNE 2D-Eintrag blieben
        korrekt — der Fehler sah also aus wie "manche Geraete stehen falsch".

        Gewarnt wird NUR bei der Ganz-Dict-Zuweisung: das ist der Weg der
        Build-Skripte. Interaktives Ziehen schreibt einzelne Eintraege in das
        Dict und laeuft hier nicht durch. Verhalten bleibt unveraendert — wer
        das 2D-Raster bewusst setzt, bekommt es; er erfaehrt nur, was es kostet.
        """
        try:
            from .stage.coords import live_to_world3d
            neu = dict(value or {})
            if not neu:
                return
            betroffen = []
            for node in self._scene.fixtures():
                fid = node.fixture_id
                if fid not in neu:
                    continue
                # ``pos_set`` ist die vorhandene Quelle fuer "hat wirklich eine
                # Position bekommen" — ein Knoten, der nur wegen einer Rotation
                # existiert, steht auf (0,0,0) und zaehlt hier bewusst nicht.
                if not getattr(node, "pos_set", False):
                    continue
                alt = tuple(node.transform.pos_m)
                px, py = neu[fid][0], neu[fid][1]
                x3, z3 = live_to_world3d(px, py)
                if abs(x3 - alt[0]) > 1e-6 or abs(z3 - alt[2]) > 1e-6:
                    betroffen.append((fid, (round(alt[0], 2), round(alt[2], 2)),
                                      (round(x3, 2), round(z3, 2))))
            if betroffen:
                print(f"[app_state] WARNUNG: live_view_positions verschiebt "
                      f"{len(betroffen)} ausdrueckliche 3D-Position(en) "
                      f"(x/z werden aus dem 2D-Raster abgeleitet): "
                      + ", ".join(f"fid {f}: {a} -> {b}" for f, a, b in betroffen[:5])
                      + (" …" if len(betroffen) > 5 else "")
                      + ". Entweder das 2D-Raster weglassen oder es aus den "
                        "3D-Positionen ableiten (stage.coords.world3d_to_live).")
        except Exception as e:
            print(f"[app_state] live_view-Guard uebersprungen: {e}")

    @property
    def active_stage_name(self) -> str:
        return self._active_stage_name

    @active_stage_name.setter
    def active_stage_name(self, value: str) -> None:
        self._active_stage_name = value or "simple"
        self._scene.stage_snapshot["name"] = self._active_stage_name

    # ── Show-Datenbank ────────────────────────────────────────────────────────

    def open_show(self, path: str = SHOW_DB_PATH):
        import os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # STAB-CURSHOW: eine evtl. schon offene Show-Engine (samt ihrem
        # connect-Listener-Closure) vor dem Ueberschreiben freigeben — sonst
        # leakt bei wiederholtem open_show (Tests / kuenftiges "Show wechseln
        # ohne Neustart") der alte Connection-Pool + Listener.
        _old_engine = getattr(self, "_show_engine", None)
        if _old_engine is not None:
            try:
                _old_engine.dispose()
            except Exception as e:
                debug_swallow("app_state.open_show.dispose_old", e)
        self._show_engine = create_engine(f"sqlite:///{path}", echo=False)
        # STAB-CURSHOW: Concurrency-PRAGMAs pro Connection setzen. busy_timeout ist
        # Pflicht (serialisiert zwei echte App-Prozesse statt sofort SQLITE_BUSY);
        # WAL nur auf lokalem Fixed-Pfad (Guard gegen Netz-/Cloud-Sync-Ordner).
        # Der 'connect'-Listener feuert fuer jede neue physische Pool-Connection.
        _wal_ok = _is_local_writable_path(path)
        event.listen(
            self._show_engine, "connect",
            lambda dbapi_conn, _rec: _set_sqlite_pragmas(dbapi_conn, _wal_ok),
        )
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
        # FM-16: Multi-Head-Fixture (Spider/Mover-/Beam-Bar) -> automatisch eine
        # Pro-Kopf-Matrix-Gruppe anlegen, damit die Einzelkoepfe sofort als Matrix
        # im Matrix-Programmer (und beim Zusammenlegen) ansprechbar sind. Best-effort:
        # ein Fehler hier darf den Patch NIE brechen; idempotent (kein Duplikat).
        # NUR bei INTERAKTIVEM Einzel-Patch: waehrend eines Bulk-Load/Reset ist
        # _suppress_emits gesetzt -> die Auto-Gruppe waere sinnlos (der Loader macht
        # gleich delete-all + _restore_fixture_groups) und ihr group_changed-Emit
        # wuerde re-entrante View-Rebuilds mitten im halb aufgebauten Patch ausloesen
        # (BUG-01-Klasse). Guard hier + notify_groups_changed() (statt direktem
        # get_sync-Emit) in create_head_matrix_group respektiert die Suppression.
        # WICHTIG: NICHT das uebergebene `fixture` verwenden — nach s.commit()
        # ist es (expire_on_commit) EXPIRED und nach dem with-Exit DETACHED, d.h.
        # jeder Zugriff auf eine Spalte (fixture_profile_id/mode_name/channel_count
        # …) in color_head_count -> get_channels_for_patched wirft
        # DetachedInstanceError. create_head_matrix_group verschluckt das still
        # (except -> None) -> es entsteht KEINE Kopf-Gruppe (FM-16 (d) tot). Statt
        # dessen das frisch aus _reload_patch_cache() GEBUNDENE Cache-Objekt
        # (Spalten geladen, nicht expired) an create_head_matrix_group geben.
        if not getattr(self, "_suppress_emits", False):
            bound = next(
                (f for f in self._patch_cache if f.fid == snapshot["fid"]), None
            )
            # FM-HEADLAYOUT: head_mode == "single" ("als EINE Lampe") unterdrueckt
            # die automatische Kopf-Matrix-Gruppe. "auto" (Default, Alt-Shows) und
            # "heads" legen sie wie bisher an.
            _hmode = str(getattr(bound, "head_mode", "auto") or "auto")
            if bound is not None and _hmode != "single":
                try:
                    self.create_head_matrix_group(bound)
                except Exception as e:
                    debug_swallow("app_state.add_fixture.head_matrix_group", e)
        if undoable:
            self._push_undo(
                label=f"Fixture +{snapshot.get('label', '')}",
                do=lambda: None,   # already executed
                undo=lambda s=snapshot: self.remove_fixture(s["fid"], undoable=False),
                redo=lambda s=snapshot: self._restore_fixture_dict(s),
            )

    def _scan_head_matrix_group(self, fid_i: int, dedicated: bool) -> int | None:
        """Interner Scan — WIRFT bei DB-Fehlern (damit ``create_head_matrix_group``
        einen fehlgeschlagenen Scan NICHT als „nicht vorhanden" missdeutet und ein
        Duplikat anlegt, Review-Fund LOW)."""
        import json as _json
        from sqlalchemy import select as _select
        from src.core.database.models import FixtureGroup as _FG
        from .group_cells import parse_group_cell
        with self._session() as s:
            stmt = _select(_FG)
            if dedicated:
                stmt = stmt.where(_FG.folder == "Multi-Head")
            for g in s.execute(stmt).scalars().all():
                try:
                    pos = _json.loads(g.positions_json or "{}")
                except Exception:
                    continue
                cells = [parse_group_cell(v) for v in (pos or {}).values()]
                if dedicated:
                    # Die DEDIZIERTE Auto-Gruppe: AUSSCHLIESSLICH Koepfe DIESES
                    # fid (identisch zum Cleanup in remove_fixture). Eine vom
                    # Nutzer zusammengelegte Matrix (mehrere fids) zaehlt NICHT.
                    if cells and all(h is not None and cf == fid_i
                                     for cf, h in cells):
                        return g.id
                else:
                    if any(h is not None and cf == fid_i for cf, h in cells):
                        return g.id
        return None

    def find_head_matrix_group(self, fid, *, dedicated: bool = False) -> int | None:
        """FM-HEADLAYOUT: id der Pro-Kopf-Matrix-Gruppe zu ``fid`` — sonst ``None``.
        Read-only, fehlertolerant.

        ``dedicated=False`` (breit): IRGENDEINE Gruppe adressiert ``fid`` kopfweise
        (Zellen ``"fid:head"``) — das ist der Idempotenz-Begriff von
        ``create_head_matrix_group`` (kein zweites Kopf-Adressierungs-Raster).
        ``dedicated=True`` (eng): die beim Patchen erzeugte AUTO-Gruppe (Ordner
        „Multi-Head", ausschliesslich Koepfe dieses fid) — dafuer, dass die Status-
        Anzeige im Patch-Dialog nicht „vorhanden" meldet, obwohl nur eine
        zusammengelegte Fremd-Matrix die Koepfe abdeckt (Review-Fund MEDIUM).
        Nutzt den kanonischen Zell-Parser (``group_cells``)."""
        eng = getattr(self, "_show_engine", None)
        if eng is None or fid is None:
            return None
        try:
            fid_i = int(fid)
        except (TypeError, ValueError):
            return None
        try:
            return self._scan_head_matrix_group(fid_i, dedicated)
        except Exception as e:
            debug_swallow("app_state.find_head_matrix_group", e)
            return None

    def create_head_matrix_group(self, fixture, *, emit: bool = True) -> int | None:
        """FM-16: Legt fuer ein MULTI-HEAD-Fixture (>=2 color_r-Baenke, z. B. Spider/
        Mover-Bar/Hydrabeam) automatisch eine 1×N-``FixtureGroup`` an, deren N Zellen
        die EINZELKOEPFE sind (``positions`` = ``{"i,0": "fid:i"}``). Damit sind die
        Koepfe sofort als Pro-Kopf-Matrix im Matrix-Programmer ansprechbar und
        koennen mit anderen Kopf-Matrizen zu groesseren Matrizen zusammengelegt
        werden (FM-16 Vision). Idempotent: existiert bereits eine Gruppe, die diesen
        ``fid`` pro-Kopf adressiert, wird deren id zurueckgegeben (kein Duplikat bei
        Re-Patch). Rueckgabe: neue/bestehende Gruppen-id, oder ``None`` wenn kein
        Multi-Head oder keine Show-DB."""
        eng = getattr(self, "_show_engine", None)
        if eng is None:
            return None
        try:
            n = color_head_count(fixture)
        except Exception as e:
            # Frueher voellig stumm -> ein detached/expired Fixture (BUG-Klasse
            # von FM-16 (d)) blieb unsichtbar. Jetzt wenigstens im Debug-Log.
            debug_swallow("app_state.create_head_matrix_group.head_count", e)
            return None
        if n < 2:
            return None
        fid = getattr(fixture, "fid", None)
        if fid is None:
            return None
        import json as _json
        from sqlalchemy import select as _select
        from src.core.database.models import FixtureGroup as _FG
        label = (getattr(fixture, "label", None)
                 or getattr(fixture, "fixture_name", None) or f"Fixture {fid}")
        positions = {f"{i},0": f"{fid}:{i}" for i in range(n)}
        try:
            # Idempotenz: adressiert schon IRGENDEINE Gruppe dieses fid kopfweise?
            # Der Scan liegt BEWUSST im try und wirft bei DB-Fehlern — sonst
            # wuerde ein fehlgeschlagener Scan als „nicht vorhanden" gelten und
            # ein Duplikat anlegen (Review-Fund). Gleiche Quelle wie die Status-
            # Anzeige im Patch-Dialog (dort eng, hier breit).
            existing = self._scan_head_matrix_group(int(fid), False)
            if existing is not None:
                return existing
            with self._session() as s:
                g = _FG(name=f"{label} · Köpfe", cols=n, rows=1,
                        positions_json=_json.dumps(positions), folder="Multi-Head")
                s.add(g)
                s.commit()
                gid = g.id
        except Exception as e:
            debug_swallow("app_state.create_head_matrix_group", e)
            return None
        if emit:
            # notify_groups_changed -> self._emit("group_changed") respektiert
            # _suppress_emits UND das UI-Thread-Marshalling (kein direkter get_sync-
            # Bus-Emit, der beide Schutzmechanismen umgeht).
            try:
                self.notify_groups_changed()
            except Exception:
                pass
        return gid

    @staticmethod
    def _stack_group_grids(grids: list[tuple[int, int, dict]]) -> tuple[int, int, dict]:
        """FM-16e: Stapelt mehrere ``(cols, rows, positions)``-Raster VERTIKAL zu
        EINEM groesseren. ``positions`` = ``{(col,row): value}`` (value = ganzer fid
        ODER Kopf-Zelle ``"fid:head"``). Raster k beginnt bei ``row = Summe der Hoehen
        davor``; Spalten auf die max. Breite. Zellwerte bleiben UNVERAENDERT (das
        ``fid:head``-Encoding ueberlebt) -> die Matrix-Engine (grids_from_positions)
        spricht die Koepfe weiter einzeln an. Rueckgabe ``(cols, rows, merged)``."""
        max_cols = 1
        total_rows = 0
        merged: dict = {}
        for cols, rows, positions in grids:
            max_cols = max(max_cols, int(cols or 1))
            for (c, r), val in positions.items():
                merged[(c, total_rows + r)] = val
            total_rows += max(1, int(rows or 1))
        return max_cols, max(1, total_rows), merged

    def merge_head_matrix_groups(self, gids, name=None, *, emit: bool = True):
        """FM-16e (Kopf-Matrizen ZUSAMMENLEGEN, David-Wunsch 2026-07-18): fasst
        mehrere (Kopf-)Matrix-Gruppen zu EINER groesseren Matrix zusammen — die N
        Raster werden in ``gids``-Reihenfolge untereinander gestapelt (Zeilen),
        Spalten auf die max. Breite; jede Zelle behaelt ihr ``fid``/``"fid:head"``-
        Encoding, sodass die zusammengelegte Matrix im Matrix-Programmer pro Kopf
        ansprechbar bleibt (z. B. 2× Hydrabeam 1×4 -> eine 4×2-Matrix). Die
        QUELL-Gruppen bleiben unangetastet (nicht-destruktiv). Neue Gruppe im Ordner
        "Matrizen" (nicht "Multi-Head" -> remove_fixture raeumt sie nicht mit weg).
        Rueckgabe: neue gid, oder None (<2 gueltige Gruppen / keine Show-DB)."""
        eng = getattr(self, "_show_engine", None)
        if eng is None:
            return None
        import json as _json
        from sqlalchemy import select as _select
        from src.core.database.models import FixtureGroup as _FG
        gids = [int(g) for g in (gids or [])]
        if len(gids) < 2:
            return None
        try:
            with self._session() as s:
                by_id = {g.id: g for g in s.execute(
                    _select(_FG).where(_FG.id.in_(gids))).scalars().all()}
                grids: list[tuple[int, int, dict]] = []
                names: list[str] = []
                for gid in gids:                      # Reihenfolge = Stapel-Reihenfolge
                    g = by_id.get(gid)
                    if g is None:
                        continue
                    try:
                        pos_raw = _json.loads(g.positions_json or "{}")
                    except Exception:
                        pos_raw = {}
                    positions: dict = {}
                    for k, v in pos_raw.items():
                        try:
                            c, r = k.split(",")
                            positions[(int(c), int(r))] = v
                        except Exception:
                            continue
                    grids.append((int(g.cols or 1), int(g.rows or 1), positions))
                    names.append(g.name or "")
                if len(grids) < 2:
                    return None
                cols, rows, merged = self._stack_group_grids(grids)
                merged_json = _json.dumps({f"{c},{r}": v for (c, r), v in merged.items()})
                label = name or (" + ".join(n for n in names if n)[:60] or "Matrix")
                ng = _FG(name=label, cols=cols, rows=rows,
                         positions_json=merged_json, folder="Matrizen")
                s.add(ng)
                s.commit()
                gid = ng.id
        except Exception as e:
            debug_swallow("app_state.merge_head_matrix_groups", e)
            return None
        if emit:
            try:
                self.notify_groups_changed()
            except Exception:
                pass
        return gid

    def remove_fixture(self, fid: int, undoable: bool = True):
        # Snapshot before delete
        snap = None
        for f in self._patch_cache:
            if f.fid == fid:
                snap = self._fixture_to_dict(f)
                break
        removed_group = False
        with self._session() as s:
            from sqlalchemy import select, delete
            s.execute(delete(PatchedFixture).where(PatchedFixture.fid == fid))
            # FM-16: die beim Patchen auto-erzeugte Kopf-Matrix-Gruppe (Ordner
            # "Multi-Head") dieses Fixtures mit entfernen -> keine verwaisten
            # "fid:head"-Gruppen bei Delete/Undo. NUR eine Gruppe anfassen, die
            # AUSSCHLIESSLICH die Koepfe DIESES fid adressiert (die dedizierte 1×N-
            # Auto-Gruppe) — vom Nutzer zusammengelegte Matrizen (mehrere fids)
            # bleiben unberuehrt.
            try:
                from src.core.database.models import FixtureGroup as _FG
                import json as _json
                for g in s.execute(
                        select(_FG).where(_FG.folder == "Multi-Head")).scalars().all():
                    try:
                        pos = _json.loads(g.positions_json or "{}")
                    except Exception:
                        continue
                    vals = [str(v) for v in pos.values()]
                    if vals and all(":" in v and v.split(":", 1)[0] == str(fid)
                                    for v in vals):
                        s.delete(g)
                        removed_group = True
            except Exception as e:
                debug_swallow("app_state.remove_fixture.head_group_cleanup", e)
            s.commit()
        self.programmer.pop(fid, None)
        self._reload_patch_cache()
        self._emit("patch_changed")
        if removed_group:
            try:
                self.notify_groups_changed()
            except Exception:
                pass
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

    def replace_patch(self, fixtures: list[PatchedFixture]):
        """STAB-CURSHOW: Ersetzt den GESAMTEN Patch ATOMAR in EINER Transaktion.

        Ersetzt das frühere ``clear_patch()`` + N×``add_fixture()`` (N+1 Commits)
        durch GENAU EINEN Commit: ``DELETE FROM patched_fixtures`` + Bulk-Insert
        aller Fixtures. Dadurch existiert nie ein persistierter Leer-/Halbzustand,
        den ein paralleler Prozess sieht oder in den er hinein-INSERTet — die
        Quelle der 22-35-Nichtdeterminismus + der Adress-Ueberlapp-Zeilen. Crash
        vor dem Commit -> Journal-Rollback -> alter Patch bleibt intakt.

        FALLEN (zwingend, siehe STAB-CURSHOW-Debatte):
        * ZWINGEND Core-``delete()`` (``s.execute(delete(...))``), NIEMALS ORM-
          ``session.delete``/objektweise: die Unit-of-Work ordnet objektweises
          Delete sonst NACH den ``add_all``-INSERTs derselben Tabelle -> UNIQUE-
          Constraint-Clash auf ``fid``. Core-delete emittiert das SQL sofort und
          leert die Tabelle im selben TX vor dem Flush (Vorbild: ``clear_patch``).
        * fid-Dedup REASSIGN (nie droppen): kollidiert eine fid innerhalb der
          eingehenden Liste (kaputte Show-Datei), weicht sie auf die naechste
          freie aus — sonst Intra-Load-Datenverlust. Kein DB-Read alter fids
          noetig, da die Tabelle im selben TX geleert wird.
        * KEIN ``add_fixture`` -> KEINE Auto-Kopf-Matrix-Gruppe (FM-16). Gruppen
          werden vom Loader separat via ``_restore_fixture_groups`` gesetzt.
        * ``expire_on_commit``: die uebergebenen ORM-Objekte sind nach dem Commit
          DETACHED. Downstream ausschliesslich den frisch via
          ``_reload_patch_cache`` gebundenen Cache nutzen, nie ``fixtures``.
        """
        # fid-Dedup mit REASSIGN gegen das Batch-Set.
        used: set[int] = set()
        for pf in fixtures:
            if pf.fid in used:
                pf.fid = max(used) + 1
            used.add(pf.fid)
        if self._show_engine is None:
            # Kein Show-Engine (Test-/Headless-Sonderfall): Cache setzen UND die
            # In-Memory-Ableitungen genauso vorwaermen wie der Engine-Zweig via
            # _reload_patch_cache (Universes/Channel-/Render-Plan), sonst emittiert
            # patch_changed auf einen inkonsistenten abgeleiteten Zustand.
            self._patch_cache = list(fixtures)
            self._rebuild_universes()
            clear_channel_cache()
            self._rebuild_render_plan()
            self._emit("patch_changed")
            return
        from sqlalchemy import delete
        with self._session() as s:
            # Core-delete zuerst (leert die Tabelle im selben TX), dann Bulk-Insert.
            s.execute(delete(PatchedFixture))
            s.add_all(fixtures)
            s.commit()   # GENAU EIN Commit -> kein persistierter Zwischenzustand.
        # `fixtures` ist jetzt detached (expire_on_commit) -> ab hier nur der Cache.
        self._reload_patch_cache()
        self._emit("patch_changed")

    def update_fixture(self, fid: int, undoable: bool = True, **changes) -> bool:
        allowed = {
            "label", "fixture_profile_id", "mode_name", "universe",
            "address", "channel_count", "manufacturer_name",
            "fixture_name", "fixture_type", "invert_pan",
            "invert_tilt", "swap_pan_tilt", "dimmer_curve",
            "spider_mirrored", "spider_dual_tilt",
            # FM-HEADLAYOUT: OHNE diesen Eintrag wird die Mehrkopf-Modus-Wahl aus
            # dem Patch-Dialog STILL verworfen (Review-Fund HIGH) -> Feature tot.
            "head_mode",
            "pan_range_deg", "tilt_range_deg", "pan_zero_dmx", "tilt_zero_dmx",
            "protocol", "net_host",
        }
        values = {k: v for k, v in changes.items() if k in allowed}
        if "head_mode" in values:
            # Garbage aus Skript-/Remote-Pfaden klemmen (kanonische Quelle:
            # Leaf-Modul core.head_mode — dieselbe wie die Show-Persistenz).
            from .head_mode import normalize_head_mode
            values["head_mode"] = normalize_head_mode(values["head_mode"])
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
            # Drop the 'fid' key: it is passed positionally to update_fixture,
            # so leaving it in the **kwargs dict would raise
            # "TypeError: got multiple values for argument 'fid'".
            before_kw = {k: v for k, v in before.items() if k != "fid"}
            after_kw = {k: v for k, v in after.items() if k != "fid"}
            self._push_undo(
                label=f"Fixture ~{before.get('label', '')}",
                do=lambda: None,
                undo=lambda b=before_kw: self.update_fixture(fid, undoable=False, **b),
                redo=lambda a=after_kw: self.update_fixture(fid, undoable=False, **a),
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
            # FM-HEADLAYOUT: OHNE dies verliert Loeschen+Undo den Modus UND legt
            # die per "single" unterdrueckte Kopf-Gruppe wieder an (Review-Fund).
            "head_mode": getattr(f, "head_mode", "auto") or "auto",
            "pan_range_deg": getattr(f, "pan_range_deg", 540),
            "tilt_range_deg": getattr(f, "tilt_range_deg", 270),
            "pan_zero_dmx": getattr(f, "pan_zero_dmx", 128),
            "tilt_zero_dmx": getattr(f, "tilt_zero_dmx", 128),
            "manufacturer_name": f.manufacturer_name,
            "fixture_name": f.fixture_name,
            "fixture_type": f.fixture_type,
            "protocol": getattr(f, "protocol", "dmx") or "dmx",
            "net_host": getattr(f, "net_host", "") or "",
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
            head_mode=d.get("head_mode", "auto") or "auto",   # FM-HEADLAYOUT
            pan_range_deg=d.get("pan_range_deg", 540),
            tilt_range_deg=d.get("tilt_range_deg", 270),
            pan_zero_dmx=d.get("pan_zero_dmx", 128),
            tilt_zero_dmx=d.get("tilt_zero_dmx", 128),
            manufacturer_name=d.get("manufacturer_name", ""),
            fixture_name=d.get("fixture_name", ""),
            fixture_type=d.get("fixture_type", "other"),
            protocol=d.get("protocol", "dmx") or "dmx",
            net_host=d.get("net_host", "") or "",
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

    def _get_plan_lock(self):
        """STAB-15: Liefert das Render-Plan-Lock; legt es defensiv an, falls das
        Objekt ohne __init__ gebaut wurde (Test-Helfer via AppState.__new__ —
        gleiches Muster wie _fd_lock/_sd_lock: getattr mit Fallback)."""
        lock = getattr(self, "_plan_lock", None)
        if lock is None:
            lock = self._plan_lock = threading.RLock()
        return lock

    def _rebuild_render_plan(self):
        """Berechnet aus dem Patch die Strukturen fuer den Per-Frame-Renderer:
        Default-Frame (gepatchte Kanaele auf Default), fid->Kanal-Index und die
        zusammenhaengenden Adress-Spans, die pro Frame committed werden."""
        fix_index: dict[int, tuple] = {}
        defaults: dict[int, bytearray] = {}
        addrs: dict[int, set] = {}
        laser_addrs: dict[int, set] = {}   # UXT-12: Adressen aller DMX-Laser
        laser_fids: set = set()
        for fx in self._patch_cache:
            chans = get_channels_for_patched(fx)
            # FM-12: Override-Cache hier mit vorwaermen (gleiche Stelle, an der
            # der Channel-Cache nach clear_channel_cache wieder befuellt wird) —
            # sonst zahlt der naechste 20-FPS-Paint-Tick der Live-View pro
            # distinktem Profil eine synchrone DB-Session auf dem GUI-Thread.
            viz_model_override_for(fx)
            fix_index[fx.fid] = (fx, chans)
            # LAS-04: Netzwerk-Laser bleiben im fix_index (Programmer/Effekte
            # adressieren sie per fid), bekommen aber KEINE Defaults/Spans —
            # ihre Platzhalter-Adresse darf nie ins Live-Universe committen.
            if not fixture_uses_dmx(fx):
                continue
            # UXT-12: DMX-Laser erkennen (fixture_type 'laser' ODER laser_*-Kanäle
            # — dieselbe Definition wie capability.is_laser_fixture, aber mit den
            # schon geladenen chans, ohne Zweit-Load).
            is_laser = ((getattr(fx, "fixture_type", "") or "").lower() == "laser"
                        or any((getattr(ch, "attribute", "") or "").startswith("laser_")
                               for ch in chans))
            if is_laser:
                laser_fids.add(fx.fid)
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
                if is_laser:
                    laser_addrs.setdefault(fx.universe, set()).add(addr)
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
        # STAB-15: Der Plan wurde oben KOMPLETT lokal aufgebaut; die Felder jetzt
        # gebuendelt unter _plan_lock tauschen, damit _render_frame nie eine halb
        # getauschte Kombination (neuer fix_index + alte spans/defaults) sieht.
        new_default_frame = {u: bytes(b) for u, b in defaults.items()}
        new_patched_set = {u: frozenset(s) for u, s in addrs.items()}
        new_laser_estop_addrs = {u: frozenset(s) for u, s in laser_addrs.items()}
        new_laser_fids = frozenset(laser_fids)
        # A3D-18: Snapshot der bisher gepatchten Adressen VOR dem Tausch — Adressen,
        # die jetzt NICHT mehr gepatcht sind (Fixture entfernt/umadressiert), muessen
        # danach im Live-Universe freigegeben werden (sonst Zombie-Kanal).
        old_patched = {u: set(s) for u, s in getattr(self, "_patched_set", {}).items()}
        # CDX-22 (Safety): Snapshot der bisherigen DMX-Laser-Adressen — sie sind von
        # der Deferral-Aufschiebung ausgenommen (Begruendung in
        # _release_unpatched_addrs). Eigener Snapshot, damit der CDX-12-Vergleich
        # unten (_old_le vs. frozenset-Werte) unangetastet bleibt.
        old_laser_addrs = {u: set(s) for u, s
                           in (getattr(self, "_laser_estop_addrs", {}) or {}).items()}
        # CDX-12 (Plan-Rebuild): Ist der Laser-NOT-AUS AKTIV und aendern sich die
        # Laser-Adressen (Fixture umadressiert/entfernt/dazu), die Ebene-2-OM-Maske
        # ZUERST auf die VEREINIGUNG aus alten und neuen Adressen erweitern — BEVOR
        # Ebene 1 (`_laser_estop_addrs`) unter `_plan_lock` auf die neuen umschaltet.
        # Sonst deckt die Maske im Fenster bis zum finalen Push (unten) nur die alten
        # Adressen, waehrend der Renderer schon die neuen nullt → ein Modifier auf
        # einer neu adressierten Laser-Adresse oeffnete den Laser fuer die Rebuild-
        # Frames (dieselbe Ebene-1-vor-Ebene-2-Fehlerklasse wie in set_laser_estop).
        # Extra-(alte)-Adressen dunkel zu halten ist safe; der Push unten verengt
        # danach auf die neuen. Deadlock-frei: KEIN verschachteltes _plan_lock —
        # dieser Push (nur _estop_lock) laeuft VOR dem _plan_lock-Block.
        if getattr(self, "laser_estop_active", False):
            _old_le = getattr(self, "_laser_estop_addrs", {}) or {}
            if _old_le != new_laser_estop_addrs:
                _union = {}
                for _m in (_old_le, new_laser_estop_addrs):
                    for _u, _s in _m.items():
                        _union[_u] = _union.get(_u, frozenset()) | frozenset(_s)
                self._push_laser_estop_mask(target_active=True, target_addrs=_union)
        with self._get_plan_lock():
            self._fix_index = fix_index
            self._default_frame = new_default_frame
            self._commit_spans = spans
            self._patched_set = new_patched_set
            self._laser_estop_addrs = new_laser_estop_addrs
            self._laser_fids = new_laser_fids
        # STAB-14: die zuletzt als Engine-Extra committeten Roh-Kanaele aktiv
        # freigeben, statt das Tracking nur zu leeren (sonst Zombie, s. Helfer).
        self._release_engine_extra()
        # A3D-18: zuvor gepatchte, jetzt ungepatchte Adressen (entferntes/umadressiertes
        # Fixture) im Live-Universe freigeben — der Commit (Schritt 5) beruehrt nur noch
        # die NEUEN Spans, _release_engine_extra nur ungepatchte Roh-Kanaele.
        self._release_unpatched_addrs(old_patched, new_patched_set,
                                     never_defer=old_laser_addrs)
        # Grand-Master-Adressmaske: nur Intensitaets-/Farbadressen je Universum,
        # damit der GM nur dimmt und nicht Pan/Tilt/Gobo verstellt (Audit B4).
        gm_mask = self._build_gm_mask(fix_index)
        try:
            self.output_manager.set_gm_address_mask(
                {u: frozenset(s) for u, s in gm_mask.items()})
        except Exception as e:
            print(f"[AppState] set gm mask error: {e}")
        # A3D-01: die Laser-Estop-Maske am OutputManager mitpflegen (Adressen
        # koennen sich geaendert haben, waehrend der NOT-AUS-Latch aktiv ist).
        self._push_laser_estop_mask()

    def _release_engine_extra(self):
        """STAB-14: gibt die zuletzt als Engine-Extra committeten Roh-Kanaele
        (``ScriptFunction.setdmx`` auf NICHT gepatchte Adressen, gemerkt in
        ``_engine_extra_prev``) im Live-Universe auf 0 frei und leert das Tracking.

        Wird beim Patch-Rebuild aufgerufen: Frueher wurde ``_engine_extra_prev``
        dort nur auf ``{}`` gesetzt, ohne die Live-Werte zu nullen — stoppte das
        Skript danach, blieb ``prev`` im naechsten Frame leer, die ``prev-cur``-
        Freigabe (Schritt 5) feuerte nie und der Roh-Kanal blieb dauerhaft an
        (Zombie; bei Strobe/Shutter/Beam sicht-/sicherheitsrelevant). Wird die
        Adresse jetzt gepatcht oder weiter roh beschrieben, setzt der naechste
        Frame sie ueber ihren Commit-Span bzw. erneut als Engine-Extra neu —
        hoechstens 1 Frame Dip waehrend des Umpatchens.

        ``list(...)``-Snapshot, da der Render-Thread ``_engine_extra_prev`` parallel
        neu bindet (Schritt 5). ``set_channel`` ist per Universe-Lock thread-safe.
        Defensiv (``getattr``): ``_rebuild_render_plan`` darf — wie die alte reine
        ``= {}``-Zuweisung — auch laufen, bevor ``_engine_extra_prev``/``universes``
        existieren (Bau-Reihenfolge/Test-Stubs); dann nur zuruecksetzen, nichts freigeben.

        CDX-22b: Laeuft ein ``deferred_unpatched_release``-Fenster, wird hier NICHT
        genullt, sondern nur gemerkt — sonst blitzen script-getriebene Roh-Adressen
        beim Live-Show-Load schwarz, genau wie die gepatchten vor CDX-22. Die
        Freigabe holt ``_flush_deferred_engine_extra`` am Fensterende nach.
        """
        if getattr(self, "_defer_release_depth", 0) > 0:
            store = getattr(self, "_deferred_engine_extra", None)
            if store is None:
                store = self._deferred_engine_extra = {}
            for u, addrs in list((getattr(self, "_engine_extra_prev", None) or {}).items()):
                store[u] = set(store.get(u, set())) | set(addrs)
            # Tracking trotzdem leeren: der Renderer soll im Fenster nicht gegen
            # einen Vor-Load-Stand diffen. Kein Zombie-Risiko — der Flush unten
            # laeuft in JEDEM Fall (``finally`` im Kontextmanager).
            self._engine_extra_prev = {}
            return
        prev = getattr(self, "_engine_extra_prev", None)
        universes = getattr(self, "universes", None)
        if prev and universes:
            for u, prev_addrs in list(prev.items()):
                uni = universes.get(u)
                if uni is None:
                    continue
                for a in prev_addrs:
                    uni.set_channel(a, 0)
        self._engine_extra_prev = {}

    def _release_unpatched_addrs(self, old_patched: dict, new_patched: dict,
                                 *, never_defer: dict | None = None):
        """A3D-18: Adressen, die vor dem Rebuild gepatcht waren, jetzt aber NICHT
        mehr (Fixture entfernt oder umadressiert), im Live-Universe auf 0 freigeben.

        Ohne das behaelt so eine Adresse fuer immer ihren zuletzt committeten Wert:
        _render_frame committet in Schritt 5 nur noch die NEUEN _commit_spans, und
        _release_engine_extra erfasst ausschliesslich ungepatchte Roh-Kanaele
        (ScriptFunction setdmx) — die alte Fixture-Adresse ist keins von beidem und
        bleibt als Zombie stehen (bei Dimmer/Shutter/Beam sicht-/sicherheitsrelevant).

        Eine Adresse, die weiterhin von einem ANDEREN Fixture gepatcht ist
        (Umadressierung auf denselben Kanal), steht in ``new_patched`` und wird NICHT
        genullt — sie committet der naechste Frame ueber ihren Span neu (max. 1 Frame
        Dip). Defensiv (getattr/None-Guards) wie _release_engine_extra: darf laufen,
        bevor ``universes`` existiert (Bau-Reihenfolge/Test-Stubs). ``set_channel`` ist
        per Universe-Lock thread-safe.

        Race-Absicherung (A3D-18-Review): das SOFORTIGE Nullen hier laeuft im
        UI-Thread; ein bereits gestarteter Render-Frame mit STALE altem Plan-Snapshot
        kann seine alte Span aber NACH diesem Nullen erneut committen -> die Adresse
        wuerde dauerhaft wieder auferstehen. Darum werden die Adressen zusaetzlich in
        ``_pending_release`` vorgemerkt; der Render-Thread nullt sie im naechsten
        Frame-Commit (Schritt 5) NACH dem Span-Commit deterministisch nach (Rendering
        ist single-threaded -> genau der folgende Frame konsumiert das Pending).

        CDX-22: Laeuft ein ``deferred_unpatched_release``-Fenster (mehrstufiger
        Patch-Tausch), wird hier NICHT genullt, sondern nur gemerkt — die Freigabe
        holt ``_flush_deferred_release`` am Ende des Fensters gegen den dann
        gueltigen Patch nach. ``never_defer`` ({universe: addrs}) nimmt Adressen
        davon AUS und gibt sie auch im Fenster sofort frei — der Rebuild uebergibt
        dort die Adressen der bisherigen DMX-Laser (Safety, s. u.)."""
        if getattr(self, "_defer_release_depth", 0) > 0:
            store = getattr(self, "_deferred_release", None)
            if store is None:
                store = self._deferred_release = {}
            # SAFETY: Laser-Adressen NIE aufschieben. Das Fenster laesst alte
            # Adressen absichtlich auf ihrem letzten Wert stehen (kein Blackout-
            # Puls) — waehrenddessen kennt der Plan die alten Laser-Adressen aber
            # nicht mehr, also greift weder die Renderer-Nullung (Ebene 1) noch die
            # OutputManager-Maske (Ebene 2) eines JETZT ausgeloesten NOT-AUS an sie.
            # Ein Laser darf im Ladefenster nicht unerreichbar weiterstrahlen; ein
            # kurzer Dunkel-Dip ist bei Lasern das sichere Verhalten (und war es
            # vor CDX-22 fuer alle Fixtures).
            urgent: dict[int, set] = {}
            for u, old_addrs in old_patched.items():
                addrs = set(old_addrs)
                laser = {int(a) for a in ((never_defer or {}).get(u) or ())}
                if laser:
                    hit = addrs & laser
                    if hit:
                        urgent[u] = hit
                    addrs -= laser
                stale = {a for a in (addrs - set(new_patched.get(u, frozenset())))
                         if 1 <= a <= 512}
                if stale:
                    store[u] = set(store.get(u, set())) | stale
            if urgent:
                self._release_now(urgent, new_patched)
            return
        self._release_now(old_patched, new_patched)

    def _release_now(self, old_patched: dict, new_patched: dict):
        """Sofort-Freigabe (Rumpf von ``_release_unpatched_addrs`` ohne Deferral):
        entpatchte Adressen im Live-Universe nullen UND dem Render-Thread
        vormerken. Getrennt, weil das CDX-22-Fenster denselben Pfad fuer die
        Laser-Ausnahme und fuer den Flush am Ende braucht."""
        universes = getattr(self, "universes", None)
        pending = getattr(self, "_pending_release", None)
        if pending is None:
            pending = self._pending_release = {}
        for u, old_addrs in old_patched.items():
            stale = {a for a in (set(old_addrs) - set(new_patched.get(u, frozenset())))
                     if 1 <= a <= 512}
            if not stale:
                continue
            # 1) sofort nullen (Anzeige/Monitor + Fall ohne laufenden Render-Thread).
            uni = universes.get(u) if universes else None
            if uni is not None:
                for a in stale:
                    uni.set_channel(a, 0)
            # 2) dem Render-Thread vormerken (race-fest gegen Alt-Plan-Commit).
            pending[u] = set(pending.get(u, set())) | stale

    @contextlib.contextmanager
    def deferred_unpatched_release(self):
        """CDX-22: Schiebt die A3D-18-Freigabe entpatchter Adressen bis zum ENDE
        eines MEHRSTUFIGEN Patch-Tauschs auf (Show-Load: leerer Patch -> neuer Patch).

        Warum: ``load_show`` setzt reset-first einen LEEREN Patch (``replace_patch([])``
        via ``_reset_state``). Dessen ``_rebuild_render_plan`` sah JEDE bisher
        gepatchte Adresse als "jetzt frei" und nullte sie SOFORT im Live-Universe —
        der 44-Hz-Output-Thread sendet diese Nullen, bis der neue Patch geladen und
        gerendert ist. Ergebnis: bei JEDEM Live-Show-Load blitzten die alten Adressen
        physisch schwarz. Genau das sollte ``blackout_output=False`` verhindern, doch
        dieser Guard ueberspringt nur den EXPLIZITEN ``universe.clear()``/
        ``_flush_all_to_dmx()``, nicht die Freigabe aus dem Plan-Rebuild.

        Im Fenster werden entpatchte Adressen nur in ``_deferred_release`` GEMERKT.
        Beim Verlassen laeuft die Freigabe EINMAL gegen den dann gueltigen
        ``_patched_set``:
        * Adressen, die der neue Patch weiter belegt, bleiben unberuehrt — ihr
          zuletzt committeter Wert steht, bis der naechste Render-Commit ihn
          ersetzt (kein Puls).
        * Genuin entpatchte Adressen (Fixture in der neuen Show weg/umadressiert)
          werden weiter deterministisch freigegeben — A3D-18/CDX-17 bleiben intakt,
          auch wenn der Patch-Tausch mitten drin wirft (``finally``).

        Re-entrant (Tiefen-Zaehler); nur die AEUSSERSTE Ebene gibt frei.
        """
        self._defer_release_depth = getattr(self, "_defer_release_depth", 0) + 1
        try:
            yield
        finally:
            depth = getattr(self, "_defer_release_depth", 1) - 1
            self._defer_release_depth = depth if depth > 0 else 0
            if self._defer_release_depth == 0:
                self._flush_deferred_release()

    def _flush_deferred_release(self):
        """CDX-22: gibt die im Deferral-Fenster gemerkten Adressen frei — aber NUR
        die, die auch nach dem Patch-Tausch nicht mehr gepatcht sind. Delegiert an
        ``_release_unpatched_addrs`` (Tiefe ist hier 0 -> echter Freigabe-Pfad mit
        Sofort-Nullung + ``_pending_release``-Vormerkung fuer den Render-Thread)."""
        deferred = getattr(self, "_deferred_release", None)
        self._deferred_release = {}
        if deferred:
            self._release_unpatched_addrs(
                deferred, getattr(self, "_patched_set", {}) or {})
        self._flush_deferred_engine_extra()

    def _flush_deferred_engine_extra(self):
        """CDX-22b: gibt die im Fenster gemerkten Roh-Adressen frei — aber nur die,
        die nach dem Tausch wirklich niemand mehr treibt.

        Zwei Ausnahmen, und beide sind der Grund, warum die Sofort-Freigabe im
        Fenster falsch war:

        * Die Adresse steht wieder in ``_engine_extra_prev`` — die NEUE Show treibt
          sie ebenfalls per Skript. Nullen hiesse: kurz aus und im naechsten Frame
          wieder an, also genau der Puls.
        * Die Adresse ist inzwischen GEPATCHT. Dann committet sie ihr Span; die
          Roh-Ebene hat dort nichts mehr zu suchen.

        Kein Zombie (STAB-14): treibt die Adresse weiterhin ein Skript, uebernimmt
        die normale ``prev``-``cur``-Freigabe im Frame-Commit, sobald es stoppt.
        """
        deferred = getattr(self, "_deferred_engine_extra", None)
        self._deferred_engine_extra = {}
        if not deferred:
            return
        universes = getattr(self, "universes", None) or {}
        cur = getattr(self, "_engine_extra_prev", None) or {}
        patched = getattr(self, "_patched_set", {}) or {}
        for u, addrs in deferred.items():
            uni = universes.get(u)
            if uni is None:
                continue
            behalten = set(cur.get(u, ()) or ()) | set(patched.get(u, ()) or ())
            for a in set(addrs) - behalten:
                uni.set_channel(a, 0)

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
            # OUT-03: optionale externe Universe-Nummer (Art-Net/sACN). Fehlt sie
            # oder ist leer/unparsbar -> None = abwaertskompatibler Default.
            out_u = r.get("out_universe")
            if out_u is not None and str(out_u).strip() != "":
                try:
                    out_u = int(out_u)
                except (TypeError, ValueError):
                    out_u = None
            else:
                out_u = None
            if num not in self.universes:
                self.universes[num] = self.output_manager.add_universe(num)
            try:
                # OUT-05: erst ALLE Alt-Adapter dieses Universums entfernen/schliessen,
                # damit pro Universe genau ein (oder bei "Disabled" kein) Adapter
                # existiert — sonst sendet nach einem Typ-Wechsel der alte Adapter
                # weiter mit (Doppel-Output) bzw. ein "Disabled"-Universe gibt weiter
                # Licht aus.
                self.output_manager.remove_output(num)
                if output == "Enttec" and patch:
                    # HW-5b: den Port BEGUTACHTEN, bevor wir ihn oeffnen. Ein Name
                    # von einer anderen Plattform ("COM_FAKE" aus der Windows-Zeit
                    # auf einem Linux-Rechner) liess add_enttec nur werfen, die
                    # Exception verschwand im except unten — und der Statusbalken
                    # meldete trotzdem gruen, weil er nur die VID/PID-Anwesenheit
                    # prueft. Gar kein DMX, ohne dass es irgendwo auffiel.
                    #
                    # Der Oeffnungsversuch bleibt ABSICHTLICH unveraendert: nur
                    # diagnostizieren, nicht umbiegen. Sonst haenge der Aufbau
                    # davon ab, was gerade eingesteckt ist (bis in die Tests).
                    #
                    # Der Befund wird per getattr/Lazy-Init abgelegt, NICHT ueber
                    # ein Pflichtfeld oder eine Hilfsmethode auf self: diese
                    # Funktion wird in Bestandstests auf einem SimpleNamespace-Stub
                    # aufgerufen, der laut eigener Doku nur `output_manager` und
                    # `universes` mitbringt. Beides haette dort mit AttributeError
                    # zugeschlagen — und waere im except unten verschwunden, also
                    # genau in der Fehlerklasse gelandet, die HW-5b behebt.
                    hinweis = diagnose_enttec_port(patch)
                    if hinweis:
                        print(f"[app_state] Universe {num} (Enttec): {hinweis}")
                    notes = getattr(self, "enttec_port_notes", None)
                    if notes is None:
                        notes = {}
                        self.enttec_port_notes = notes
                    notes[num] = hinweis
                    self.output_manager.add_enttec(num, patch)
                elif output == "ArtNet":
                    self.output_manager.add_artnet(num, patch or "255.255.255.255",
                                                   out_universe=out_u)
                elif output == "sACN":
                    self.output_manager.add_sacn(num, patch or None,
                                                 out_universe=out_u)
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

    def _get_estop_lock(self):
        """A3D-01: Lock, das den ``laser_estop_active``-Flag-Wechsel mit dem
        Mask-Push an den OutputManager koppelt. Defensiv angelegt (wie
        ``_get_plan_lock``), damit Test-Helfer via ``AppState.__new__`` es nicht
        vorab setzen müssen. Nötig, weil der Latch-Clear (MIDI/OSC-Thread) und ein
        gleichzeitiges ``set_laser_estop`` (UI-Thread) sonst einen stale Push
        hinterlassen könnten (Flag ``True``, Maske leer → Safety-Backstop aus)."""
        lock = getattr(self, "_estop_lock", None)
        if lock is None:
            lock = self._estop_lock = threading.RLock()
        return lock

    def _push_laser_estop_mask(self, target_active=None, target_addrs=None):
        """A3D-01: dem OutputManager die aktuell zu verriegelnden Laser-Adressen
        pushen — bei aktivem NOT-AUS die ``_laser_estop_addrs``, sonst leer.

        Läuft unter ``_get_estop_lock`` (self-lockend + re-entrant), damit der
        gepushte Mask-Zustand IMMER zum ``laser_estop_active``-Flag passt: die
        Aufrufer setzen Flag und Push unter demselben Lock, sonst könnte ein stale
        Push zwischen Flag-Write und Push eines anderen Threads landen.

        Der Renderer nullt die Laser-Adressen bereits im Puffer (Schritt 4d), der
        OutputManager erzwingt sie zusätzlich NACH dem Channel-Modifier-Pass final
        auf 0. Ohne das hebt ein auf einer Laser-Adresse konfigurierter Modifier
        (INVERSE → 255, Range-Lock → range_min) das erzwungene Dunkel wieder auf.
        Überall aufrufen, wo ``laser_estop_active`` oder die Laser-Adressen sich
        ändern (set_laser_estop / Latch-Clear / Plan-Rebuild).

        CDX-12: ``target_active`` erlaubt es, die Maske für einen EXPLIZITEN Ziel-
        Zustand zu pushen, statt ihn aus dem Flag abzuleiten. Nötig, damit
        ``set_laser_estop`` bei der AKTIVIERUNG die (nicht-leere) Maske installieren
        kann, BEVOR das Flag gesetzt wird — leitete der Helfer den Zustand hier aus
        dem noch-``False``-Flag ab, würde er eine LEERE Maske pushen (No-Op) und das
        Sub-Frame-Fenster bliebe offen. ``None`` = Zustand aus dem Flag lesen
        (Plan-Rebuild / Latch-Clear-Deaktivierung: passt weiter zum Flag).

        CDX-12 (Plan-Rebuild): ``target_addrs`` erlaubt es, EXPLIZITE Adressen (statt
        ``_laser_estop_addrs``) zu maskieren — genutzt, um im Plan-Rebuild die Maske
        VOR dem Adress-Swap auf die VEREINIGUNG aus alten und neuen Laser-Adressen zu
        erweitern (Ebene 1 schaltet unter ``_plan_lock`` auf die neuen Adressen um,
        Ebene 2 hier unter ``_estop_lock`` — ohne Union deckt die Maske im Rebuild-
        Fenster nur die alten, während der Renderer schon die neuen nullt). ``None``
        = aus ``_laser_estop_addrs`` lesen (alle Alt-Aufrufer)."""
        with self._get_estop_lock():
            try:
                om = getattr(self, "output_manager", None)
                if om is None or not hasattr(om, "set_laser_estop_mask"):
                    return
                active = (getattr(self, "laser_estop_active", False)
                          if target_active is None else bool(target_active))
                addrs = ((getattr(self, "_laser_estop_addrs", {}) or {})
                         if target_addrs is None else target_addrs)
                om.set_laser_estop_mask(
                    {u: frozenset(s) for u, s in addrs.items()} if active else {})
            except Exception as e:
                print(f"[AppState] set laser estop mask error: {e}")

    def set_laser_estop(self, active: bool):
        """UXT-12: DMX-Muster-Laser (L2600 & Co.) bei NOT-AUS hart dunkel halten.

        ``estop_all`` verriegelt nur den Netzwerk-Streamer (Ether Dream/IDN);
        Fixtures, die über normale DMX-Kanäle ein Muster ausgeben, erreicht das
        nicht. Ist dieser Latch aktiv, zwingt der Renderer alle Laser-Kanäle als
        oberste Ebene auf 0 (Betriebsart/Shutter 0 = Laser aus); zusätzlich erzwingt
        der OutputManager sie final nach dem Channel-Modifier-Pass (A3D-01). Der
        Latch wird bewusst durch das nächste Setzen eines Laser-Werts wieder gelöst
        (Muster-Abruf/Regler = „wieder an") — ein Show-Load lässt ihn absichtlich
        stehen (dunkel = sicher)."""
        # A3D-01: Flag-Wechsel und Mask-Push atomar koppeln (siehe _get_estop_lock).
        # CDX-12: Reihenfolge ist ASYMMETRISCH und failt in beide Richtungen sicher.
        # Der Sende-/Renderpfad liest ``laser_estop_active`` roh (ohne _get_estop_lock)
        # und die OutputManager-Maske (Ebene 2) wird separat angewandt.
        with self._get_estop_lock():
            if active:
                # AKTIVIEREN: Ebene 2 (OM-Maske) installieren, BEVOR das Flag sichtbar
                # wird. Setzte man erst das Flag, sähe ein Frame im Fenster Flag=True
                # (Renderer nullt den Puffer, Ebene 1), aber die OM-Maske noch leer —
                # ein INVERSE/Range-Lock-Modifier auf einer Laser-Adresse öffnete den
                # Laser für genau diesen einen Frame trotz NOT-AUS. Maske-vor-Flag
                # schließt das Fenster: an jedem Interleaving gilt Maske installiert
                # ODER Flag noch aus. ``target_active=True``, weil der Helfer sonst aus
                # dem noch-False-Flag eine leere Maske ableitete (No-Op).
                self._push_laser_estop_mask(target_active=True)
                self.laser_estop_active = True
            else:
                # DEAKTIVIEREN bleibt Flag-dann-leere-Maske → failt safe: im Fenster
                # sieht der Sendepfad Flag=False (Renderer nullt nicht mehr), aber die
                # OM-Maske ist noch die alte (nicht-leere) → der Laser bleibt einen
                # Frame extra dunkel. Nie ein offenes Fenster.
                self.laser_estop_active = False
                self._push_laser_estop_mask(target_active=False)

    def _channels_for_fid(self, fid: int):
        """Kanalliste des gepatchten Fixtures — oder ``None``, wenn es (noch)
        nicht im Patch steht. Nur fuer die Kopf-Aufloesung (FM-17)."""
        try:
            fixture = next((f for f in self._patch_cache
                            if int(getattr(f, "fid", -1)) == int(fid)), None)
            if fixture is None:
                return None
            return get_channels_for_patched(fixture)
        except Exception:
            return None

    def _head_key(self, fid: int, attribute: str, head) -> str:
        """Aus „Kopf N" wird hier der Programmer-Schluessel (FM-17).

        ``head=None`` = ganzes Geraet -> Basis-Schluessel, unveraendert. Sonst
        entscheidet :func:`programmer_key_for_head` gegen den LIVE-Patch. Ist das
        Fixture nicht (mehr) gepatcht, bleibt es beim alten Vorkommens-Schluessel
        — ein nicht aufloesbarer Kopf darf nichts anderes tun als frueher."""
        if head is None:
            return attribute
        channels = self._channels_for_fid(fid)
        if channels is None:
            base = (attribute or "").split("#", 1)[0]
            return base if not head else f"{base}#{int(head)}"
        return programmer_key_for_head(channels, attribute, head)

    def _shared_dimmer_key(self, fid: int, attribute: str, head_key: str):
        """Der GETEILTE Master-Dimmer, den ein Kopf-Schreiben sonst zusperrt.

        ★ FM-17, zweite Haelfte. „Kopf 2 auf 50 %" richtig auf CH12 zu schreiben
        macht am echten Geraet noch kein Licht: die Hydrabeam hat davor einen
        gemeinsamen ``CH1 Master dimmer`` mit ``default_value=0``. Gemessen (
        ``tests/test_fm17_head_dimmer_map.py``): CH12=128, CH1=0 — der Kopf ist
        korrekt adressiert und bleibt trotzdem dunkel.

        Deshalb zieht ein Kopf-Dimmer den geteilten Master mit. Liefert den
        Basis-Schluessel, wenn ALLE vier Bedingungen gelten: es ist ein
        Dimmer-Attribut, geschrieben wurde ein Pro-Kopf-Kanal, das erste
        Vorkommen gehoert KEINEM Kopf (= geteilt) und es gibt ueberhaupt eine
        Kopf-Karte. Sonst ``None``.

        Bewusst nur Dimmer: Strobe/Farbe/Makro teilen zwar auch, aber ihre
        Defaults sperren nichts zu (Shutter steht offen). Ein Riegel, der nichts
        verbietet, schlaegt einen, der Bestands-Shows umschreibt.

        Rueckgabe ``(basis_schluessel, [(kopf_schluessel, kanal), …])`` oder
        ``None``."""
        base = (attribute or "").split("#", 1)[0]
        a = base.lower()
        if a not in _DIM_INTENSITY_ATTRS or head_key == base:
            return None
        channels = self._channels_for_fid(fid)
        if channels is None:
            return None
        positions, hmap = _channel_index(channels)
        per_head = hmap.get(a)
        occurrences = list(positions.get(a, ()))
        if not per_head or not occurrences:
            return None
        if occurrences[0] in per_head:
            return None      # erstes Vorkommen IST ein Kopf -> kein geteilter Master
        heads = []
        for idx in per_head:
            occ = occurrences.index(idx)
            heads.append((base if occ == 0 else f"{base}#{occ}", channels[idx]))
        return base, heads

    def set_programmer_value(self, fid: int, attribute: str, value: int,
                             undoable: bool = False, head=None):
        # Mehrkopf (X-6/FM-17): head=None = ganzes Geraet -> "attr" (byte-genau
        # wie bisher). head=0..n-1 = ein echter Kopf; welchen Schluessel der
        # adressiert, entscheidet _head_key gegen die Kanalliste — bei einem
        # geteilten Master-Dimmer ist "Kopf 1" NICHT der Basis-Schluessel.
        key = self._head_key(fid, attribute, head)
        master = self._shared_dimmer_key(fid, attribute, key) if head is not None else None
        with self._prog_lock:
            old = self.programmer.get(fid, {}).get(key, None)
            if fid not in self.programmer:
                self.programmer[fid] = {}
            self.programmer[fid][key] = max(0, min(255, value))
            new_val = self.programmer[fid][key]
            master_key = master_old = None
            if master is not None:
                master_key, heads = master
                master_old = self.programmer[fid].get(master_key)
                # Die ANDEREN Koepfe verankern, BEVOR der Master steigt: der
                # DMX-Flush spiegelt einen gesetzten Basis-Wert auf jeden noch
                # nicht eigenstaendigen Kopf-Kanal. Ohne das Verankern zoege
                # „Kopf 2 auf 50 %" ueber den mitgezogenen Master alle vier
                # Koepfe auf 50 % — dieselbe Mechanik und dieselbe Antwort wie
                # beim Getrennt-Modus-Seeding (ProgrammerView._seed_separate_head).
                # Verankert wird der Wert, den der Kopf JETZT ausgibt; die Ausgabe
                # bleibt im Moment des Verankerns also byte-genau gleich.
                for k, ch in heads:
                    if k == key or k in self.programmer[fid]:
                        continue
                    self.programmer[fid][k] = (
                        master_old if master_old is not None
                        else int(getattr(ch, "default_value", 0) or 0))
                brightest = max((self.programmer[fid][k] for k, _ in heads
                                 if k in self.programmer[fid]), default=new_val)
                self.programmer[fid][master_key] = brightest
        self._flush_programmer_to_dmx(fid)
        # UXT-12 / A3D-02: bewusstes Setzen eines OUTPUT-relevanten Laser-Werts
        # (Betriebsart/Musterbank/Gobo/Shutter/Macro = Muster-Abruf/„wieder an") hebt
        # den Laser-NOT-AUS auf. Ein harmloses Attribut (Position/Zoom/Farbe/…) darf
        # ihn NICHT lösen — sonst öffnet ein Positions-Nudge den Laser trotz Not-Aus.
        # Auf den Basisnamen prüfen: Snap-/VC-Restore-Pfade reichen den Composite-Key
        # "attr#N" (Kopf>0) direkt als attribute durch -> vor dem Whitelist-Check das
        # "#N"-Suffix abspalten, sonst entriegelt ein Kopf>0-Gate den Not-Aus nicht.
        if (getattr(self, "laser_estop_active", False)
                and str(attribute).split("#", 1)[0] in _LASER_REARM_ATTRS
                and int(fid) in getattr(self, "_laser_fids", frozenset())):
            # A3D-01: Flag-Wechsel und Mask-Push atomar koppeln (siehe _get_estop_lock).
            with self._get_estop_lock():
                self.laser_estop_active = False
                self._push_laser_estop_mask()
        self._emit("programmer_changed", fid)
        if undoable and old != new_val:
            self._push_undo(
                label=f"Programmer FID{fid}.{key}={new_val}",
                do=lambda: None,
                undo=lambda f=fid, a=attribute, v=old, h=head, mk=master_key,
                mv=master_old: (
                    self.set_programmer_value(f, a, v, undoable=False, head=h)
                    if v is not None
                    else self._clear_programmer_attr(f, key),
                    # FM-17: der mitgezogene geteilte Master gehoert zum selben
                    # Schritt zurueck — sonst bliebe er nach dem Undo oben.
                    self._restore_shared_dimmer(f, mk, mv)),
                redo=lambda f=fid, a=attribute, v=new_val, h=head:
                    self.set_programmer_value(f, a, v, undoable=False, head=h),
            )

    def _restore_shared_dimmer(self, fid: int, master_key, master_old):
        """Setzt den von FM-17 mitgezogenen geteilten Master auf seinen Vorwert
        zurueck (bzw. entfernt ihn, wenn er vorher gar nicht gesetzt war)."""
        if not master_key:
            return
        with self._prog_lock:
            prog = self.programmer.get(int(fid))
            if prog is None:
                return
            if master_old is None:
                prog.pop(master_key, None)
            else:
                prog[master_key] = master_old
            if not prog:
                self.programmer.pop(int(fid), None)
        self._flush_programmer_to_dmx(int(fid))
        self._emit("programmer_changed", int(fid))

    def _clear_programmer_attr(self, fid: int, attribute: str):
        with self._prog_lock:
            if fid not in self.programmer:
                return
            self.programmer[fid].pop(attribute, None)
            if not self.programmer[fid]:
                self.programmer.pop(fid, None)
        self._flush_programmer_to_dmx(fid)
        self._emit("programmer_changed", fid)

    def clear_programmer(self, fid: int | None = None, *, flush: bool = True):
        """Leert den Programmer (global oder ein Fixture) und schreibt die
        betroffenen Kanaele per Default sofort neu ins Live-Universe.

        ``flush=False`` unterdrueckt NUR diesen DMX-Flush (CDX-22): Beim Show-Load
        leert ``_replace_patch_from_data`` den Programmer, WAEHREND der ALTE Patch
        noch geladen ist — der Flush schreibt dann jedes alte Fixture auf seine
        Kanal-Defaults (Dimmer 0), und der 44-Hz-Output-Thread sendet diesen
        Blackout-Frame physisch, bis der neue Patch geladen UND geflusht ist. Der
        Loader flusht ohnehin direkt nach dem Programmer-Block erneut — dann gegen
        den NEUEN Patch (jede weiter gepatchte Adresse bekommt ihren Wert bzw. ihren
        Default, entpatchte Adressen die A3D-18-Freigabe). Der In-Memory-Clear und
        der WEB-01-Release laufen unveraendert."""
        with self._prog_lock:
            if fid is None:
                self.programmer.clear()
            else:
                self.programmer.pop(fid, None)
        # WEB-01: Der globale Clear ist auch der Release-Pfad fuer die per Web/OSC
        # ueber set_input_channel gesetzten Roh-Kanaele. Ein Per-Fixture-Clear
        # (fid gesetzt) laesst die Roh-Overrides stehen (sie sind nicht fid-basiert).
        if fid is None:
            try:
                self.clear_remote_input()
            except Exception as e:
                print(f"[app_state] clear_remote_input error: {e}")
        if flush:
            self._flush_all_to_dmx()
        self._emit("programmer_changed", None)

    def get_programmer_value(self, fid: int, attribute: str, head=None) -> int | None:
        # FM-17: dieselbe Kopf-Aufloesung wie set_programmer_value — ein Regler
        # muss den Wert LESEN, den er schreibt. head=None = ganzes Geraet.
        return self.programmer.get(fid, {}).get(
            self._head_key(fid, attribute, head))

    def clear_programmer_value(self, fid: int, attribute: str):
        """Entfernt einen einzelnen Programmer-Wert (z. B. fuer Toggle-/Flash-
        Ruecknahme einer Farb-/Snap-Taste in der Virtual Console)."""
        self._clear_programmer_attr(int(fid), attribute)

    # ── Gemeinsame Geraeteauswahl (R1) ─────────────────────────────────────────

    def set_selected_fids(self, fids: list[int]):
        """Setzt die gemeinsame Programmer-Auswahl und benachrichtigt alle
        Kategorien (RGB Matrix, Effekte, Paletten …) via SELECTION_CHANGED.
        Reihenfolge bleibt erhalten (wichtig fuer Fan/Chase).

        FM-HEADLAYOUT Slice 5: delegiert an ``set_selected_cells`` — jedes fid wird
        als GANZES Geraet gewaehlt. Dadurch kann die feine Auswahl
        (``selected_cells``) nie veralten, egal welcher der vielen Bestandsaufrufer
        hier hereinkommt (die Fehlerklasse „zweites Feld, das ein Schreiber
        vergisst" ist genau die, die FM16E schon einmal geliefert hat)."""
        self.set_selected_cells([str(int(f)) for f in fids])

    def set_selected_cells(self, cells):
        """FM-HEADLAYOUT Slice 5: Auswahl auf **Zell-Ebene** setzen — ein Eintrag
        ist ENTWEDER ein ganzes Geraet (``"7"``/``7``) ODER ein einzelner Kopf
        (``"7:2"``), also dieselbe Syntax wie die Gruppen-Zellen
        (``core.group_cells.parse_group_cell`` ist die EINE Parse-Quelle).

        ``selected_fids`` bleibt die dedup-Basisliste in Auswahl-Reihenfolge und
        damit der unveraenderte Vertrag fuer ALLE bisherigen Konsumenten
        (SELECTION_CHANGED traegt weiterhin die fid-Liste). Wer Koepfe
        unterscheiden will, liest zusaetzlich ``get_selected_cells()`` bzw.
        ``selected_heads_for(fid)``.

        Ist ein Geraet sowohl als Ganzes als auch per Kopf gewaehlt, gewinnt das
        GANZE Geraet (die groebere Aussage ist die sichere: alle Koepfe)."""
        from .group_cells import parse_group_cell
        norm: list[str] = []
        whole: set[int] = set()
        heads: dict[int, list[int]] = {}
        for c in cells or []:
            fid, head = parse_group_cell(c)
            if fid is None:
                continue
            key = f"{fid}" if head is None else f"{fid}:{head}"
            if key in norm:
                continue
            norm.append(key)
            if head is None:
                whole.add(fid)
            else:
                heads.setdefault(fid, []).append(head)
        # Ganzes Geraet schlaegt seine Kopf-Eintraege (sonst waere unklar, ob
        # „alle Koepfe" oder „nur diese" gemeint ist).
        if whole:
            norm = [k for k in norm
                    if ":" not in k or int(k.split(":", 1)[0]) not in whole]
            for fid in list(heads):
                if fid in whole:
                    heads.pop(fid, None)
        base: list[int] = []
        for k in norm:
            fid = int(k.split(":", 1)[0])
            if fid not in base:
                base.append(fid)
        if norm == list(getattr(self, "selected_cells", [])) and base == self.selected_fids:
            return
        self.selected_cells = norm
        self._selected_heads = {f: set(hs) for f, hs in heads.items()}
        self.selected_fids = base
        try:
            from .sync import SyncEvent
            self.sync.emit(SyncEvent.SELECTION_CHANGED, list(base))
        except Exception as e:
            print(f"[app_state] selection emit error: {e}")

    def get_selected_cells(self) -> list[str]:
        """Feine Auswahl in Auswahl-Reihenfolge (``"fid"`` oder ``"fid:head"``)."""
        return list(getattr(self, "selected_cells", []))

    def selected_heads_for(self, fid) -> set | None:
        """Welche Koepfe von ``fid`` sind gewaehlt? ``None`` = das GANZE Geraet
        (alle Koepfe) — der Normalfall und das Bestandsverhalten. Ein Set heisst:
        NUR diese Koepfe. Leeres Ergebnis (Geraet gar nicht gewaehlt) -> ``set()``."""
        try:
            fid = int(fid)
        except (TypeError, ValueError):
            return None
        if fid not in self.selected_fids:
            return set()
        hs = (getattr(self, "_selected_heads", None) or {}).get(fid)
        return set(hs) if hs else None

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

    def active_scope_heads(self) -> dict:
        """FM-HEADLAYOUT A2: Kopf-Einschraenkung des aktiven Speicher-Scopes,
        ``{fid: {head, ...}}`` — NUR fuer Geraete, bei denen wirklich einzelne
        Koepfe gewaehlt sind. Ein ganz gewaehltes Geraet taucht NICHT auf (dort
        gelten alle Koepfe), leeres Dict = keine Einschraenkung.

        Gegenstueck zu ``active_scope_fids``: wer den Programmer beim Speichern auf
        die Auswahl reduziert, soll dieselbe Feinheit anwenden — sonst landen bei
        gewaehltem Kopf 2 auch die Werte der anderen Koepfe still im Snap."""
        return {fid: set(hs)
                for fid, hs in (getattr(self, "_selected_heads", None) or {}).items()
                if hs and fid in self.selected_fids}

    # ── Gruppen-Auflösung (zentral; von VC SELECT_GROUP / GROUP_DIMMER genutzt) ──
    def _group_positions(self, name_or_ref):
        """``(gid, positions_json-dict)`` einer Fixture-Gruppe; ``(None, {})`` wenn
        nicht da. EINE Abfrage-Quelle — ``_group_lookup`` (Basis-fids) und
        ``group_cells_by_name`` (feine Zellen inkl. Koepfe) teilen sie sich, damit
        beide Sichten garantiert dieselbe Gruppe meinen.

        ENG-05: Akzeptiert einen Namen (str) ODER einen ``(gid, name)``-Ref aus
        dem Preset-Browser. Bei vorhandener gid wird EINDEUTIG per ID aufgeloest
        (gleichnamige Gruppen → kein faelschliches „Gruppe ohne Geraete"). Sonst
        per Name: ``scalar_one_or_none`` bleibt der Normalpfad; nur wenn es
        WIRKLICH mehrere gleichnamige Gruppen gibt (``MultipleResultsFound``), wird
        die erste genommen statt zu crashen.
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
                    return None, {}
                # Attribute NOCH IN der Session lesen (nach dem Schliessen kann eine
                # expire_on_commit-Session sie nicht mehr nachladen).
                return g.id, (json.loads(g.positions_json or "{}") or {})
        except Exception:
            return None, {}

    def _group_lookup(self, name_or_ref):
        """(gid, fids in Raster-Reihenfolge) einer Fixture-Gruppe; (None, []) wenn
        nicht da."""
        gid, positions = self._group_positions(name_or_ref)
        if gid is None:
            return None, []
        # FM16E-HEADCOUNT: Kopf-Zellen "fid:head" tragen ihren Basis-fid bei
        # (EINE Parse-Quelle group_cells) — sonst faellt eine Kopf-Matrix-Gruppe
        # hier still auf [] (int("5:2") wirft), zeigte "(0)" + selektierte nichts.
        from .group_cells import base_fids_in_grid_order
        return gid, base_fids_in_grid_order(positions)

    def group_fids_by_name(self, name: str) -> list[int]:
        """Fids einer Gruppe (Name) in Raster-Reihenfolge; [] wenn unbekannt."""
        return self._group_lookup(name)[1]

    def group_cells_by_name(self, name_or_ref) -> list[str]:
        """FEINE Zellen einer Gruppe in Raster-Reihenfolge: ``"fid"`` (ganzes
        Geraet) bzw. ``"fid:head"`` (Kopf-Zelle aus Slice 3 „Koepfe einzeln →
        Raster"), dedupliziert; [] wenn die Gruppe unbekannt ist.

        Gegenstueck zu ``group_fids_by_name``, das die Kopf-Aufloesung bewusst
        wegwirft — fuer Konsumenten, die sie brauchen (VC-Submaster pro Kopf, A4)."""
        from .group_cells import cells_in_grid_order
        return cells_in_grid_order(self._group_positions(name_or_ref)[1])

    def validate_head_restrictions(self, heads, *, count_heads=None) -> dict:
        """FM-HEADLAYOUT A4: eine Kopf-Einschraenkung ``{fid: {head}}`` gegen den
        LIVE-Patch pruefen. Liefert nur die Eintraege, die WIRKLICH „einzelne
        Koepfe dieses Geraets" bedeuten; alles andere faellt raus und das Geraet
        landet damit wieder im geraeteweiten Bestandspfad
        (``submaster_factor_for``) statt in einer Kopf-Maske.

        ``count_heads`` waehlt die Zaehl-Quelle: ``(fixture, channels) -> int``.
        Default ist :func:`color_head_count_for_channels` — der Farb-/Submaster-
        Fall, byte-identisch zum Bestand. Wer die BEWEGUNGSachse einschraenkt
        (XY-Pad, FM-9/A5), muss :func:`move_head_count_for_channels` uebergeben:
        die beiden Zaehlungen gehen in **831 von 5116** Library-Modi auseinander,
        und zwar in beide Richtungen (Begruendung und Zahlen dort). Die vier
        Verwerfungsregeln unten gelten fuer beide Reichweiten unveraendert; nur
        die Frage „wie viele Koepfe hat dieses Geraet ueberhaupt" hat je nach
        Achse eine andere Antwort.

        Verworfen wird ein Geraet, wenn …

        * es **nicht (mehr) gepatcht** ist,
        * es **kein Mehrkopf-Geraet** ist (``color_head_count < 2``; auch Laser),
        * nach dem Klemmen **kein gueltiger Kopf** uebrig bleibt,
        * die Koepfe **ALLE** Koepfe des Geraets abdecken — „alle Koepfe" ist
          semantisch das ganze Geraet.

        ★ Die letzten beiden Regeln sind kein Feinschliff, sondern verhindern zwei
        bestaetigte Regressionen: (1) Die beim Patchen automatisch angelegte Gruppe
        „… · Koepfe" besteht aus lauter Kopf-Zellen. Ein BESTEHENDER Submaster-Fader
        mit Reichweite „Feste Gruppe" = dieser Gruppe haette ohne die Voll-Abdeckungs-
        Regel den geraeteweiten Faktor verloren — der von allen Koepfen geteilte
        Master-Dimmer waere nicht mehr gedimmt worden (**317 Modi der eingebauten
        Library** haben genau diese Form: ein Master-Dimmer + >=2 Farbbaenke), bei
        aktivem Farb-Makro sogar bis zur voelligen Wirkungslosigkeit des Faders.
        (2) Kopf-Zellen ueberleben einen Kanal-Modus-Wechsel (``update_fixture``
        raeumt die Auto-Gruppe nicht auf) — ohne Klemmen zeigte „Kopf 2" danach auf
        den Kopf 1 des neuen Modus."""
        if not heads:
            return {}
        try:
            by_fid = {}
            for fx in self.get_patched_fixtures():
                try:
                    by_fid[int(fx.fid)] = fx
                except (TypeError, ValueError):
                    continue
        except Exception:
            return {}
        out: dict = {}
        for fid, hs in dict(heads).items():
            try:
                fid = int(fid)
            except (TypeError, ValueError):
                continue
            fx = by_fid.get(fid)
            if fx is None:
                continue
            counter = count_heads or color_head_count_for_channels
            try:
                n = counter(fx, get_channels_for_patched(fx))
            except Exception:
                continue
            if n < 2:
                continue
            valid: set = set()
            for h in (hs or ()):
                try:
                    h = int(h)
                except (TypeError, ValueError):
                    continue
                if 0 <= h < n:
                    valid.add(h)
            if not valid or len(valid) >= n:
                continue
            out[fid] = valid
        return out

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
                from .group_cells import base_fids_in_grid_order
                for g in groups:
                    # FM16E-HEADCOUNT: Kopf-Zellen "fid:head" mitzaehlen (eine
                    # Parse-Quelle) — sonst leerer Preset-Browser-Eintrag.
                    try:
                        fids = base_fids_in_grid_order(
                            json.loads(g.positions_json or "{}") or {})
                    except Exception:
                        fids = []
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
        # LAS-04: Netzwerk-Laser haben keinen DMX-Adressraum — ihre Werte
        # bleiben im Programmer (liest spaeter der LaserOutputManager).
        if not fixture_uses_dmx(fixture):
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

    def queue_scene_preview(self, values) -> None:
        """Plant Szenenwerte fuer GENAU den naechsten vollstaendigen Render-Frame.

        Der Scene-Editor darf nicht direkt in ``Universe`` schreiben: das umgeht
        den Render-Vertrag und konnte einen DMX-Laser trotz NOT-AUS kurz ansteuern.
        Nicht-DMX-Netzwerk-Laser werden wie in allen anderen DMX-Pfaden ignoriert.
        """
        preview: dict[int, dict[int, int]] = {}
        for sv in list(values or ()):
            try:
                fid = int(sv.fixture_id)
                channel = int(sv.channel)
                value = max(0, min(255, int(sv.value)))
            except (AttributeError, TypeError, ValueError):
                continue
            entry = self._fix_index.get(fid)
            if not entry:
                continue
            fixture = entry[0]
            if not fixture_uses_dmx(fixture):
                continue
            dmx_addr = int(fixture.address) + channel - 1
            if 1 <= dmx_addr <= 512:
                preview.setdefault(int(fixture.universe), {})[dmx_addr] = value
        with self._scene_preview_lock:
            self._scene_preview = preview
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
        # LAS-05: Laser-Streaming-Thread (Netzwerk-Laser) teilt den Lifecycle
        # mit dem DMX-Output; gleiche Env-Bremse wie der Output-Thread, damit
        # Tests keine Hintergrund-Threads bekommen.
        if not os.environ.get("LIGHTOS_NO_OUTPUT_THREAD"):
            try:
                self.ensure_laser_output()
            except Exception as e:
                print(f"[AppState] laser output start error: {e}")

    def ensure_laser_output(self):
        """Liefert den Laser-Streaming-Manager (LAS-05), erzeugt ihn bei Bedarf.
        Der Sende-Thread startet NUR, wenn `LIGHTOS_NO_OUTPUT_THREAD` nicht
        gesetzt ist (gleiche Bremse wie der DMX-Output-Thread) — so kann die UI
        `set_armed`/`set_figure`/`estop_all` auch in Tests am Manager aufrufen,
        ohne einen echten Netzwerk-Thread (Cross-Thread-Qt-AV-Risiko) zu starten.
        Der Manager tickt leer, solange keine Netzwerk-Laser gepatcht sind."""
        lo = getattr(self, "_laser_output", None)
        if lo is None:
            from .laser.laser_output import LaserOutputManager
            lo = LaserOutputManager(self)
            self._laser_output = lo
        if not lo.running and not os.environ.get("LIGHTOS_NO_OUTPUT_THREAD"):
            lo.start()
        return lo

    def stop_laser_output(self):
        lo = getattr(self, "_laser_output", None)
        if lo is not None:
            lo.stop()

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
            # NET-05: Empfang stempeln (defensiv, falls Stub das Feld nicht init).
            ls = getattr(self, "input_last_seen", None)
            if ls is None:
                ls = self.input_last_seen = {}
            ls[out_univ] = time.monotonic()
            # NET-07: Ist out_univ NICHT als Output gepatcht, verwirft _render_frame
            # die Kanaele still (scratch kennt nur self.universes). Statt still zu
            # schlucken je out_univ zaehlen und EINMAL warnen — die Status-Abfrage
            # liest input_unconfigured und kann so "Aktiv, aber wirkungslos" zeigen.
            unconf = getattr(self, "input_unconfigured", None)
            if unconf is None:
                unconf = self.input_unconfigured = {}
            if out_univ not in getattr(self, "universes", {}):
                if out_univ not in unconf:
                    print(
                        f"[app_state] Art-Net/sACN-Eingang fuer Universe {out_univ} "
                        f"empfangen, aber {out_univ} ist nicht als Output gepatcht -> "
                        f"Kanaele bleiben wirkungslos (Status faelschlich 'Aktiv').")
                unconf[out_univ] = unconf.get(out_univ, 0) + 1
            else:
                # Ziel ist (wieder) konfiguriert -> Fehl-Flag zuruecknehmen.
                unconf.pop(out_univ, None)

    def clear_input_merge(self, out_univ: int | None = None):
        """F-20: Eingangs-Schicht leeren (eine Universe oder alle). Damit ein
        weggefallener externer Sender keine eingefrorenen Werte hinterlaesst."""
        with self._input_lock:
            ls = getattr(self, "input_last_seen", None)
            unconf = getattr(self, "input_unconfigured", None)
            if out_univ is None:
                self.input_layer.clear()
                self.input_merge_modes.clear()
                if ls is not None:
                    ls.clear()
                if unconf is not None:
                    unconf.clear()
            else:
                self.input_layer.pop(int(out_univ), None)
                self.input_merge_modes.pop(int(out_univ), None)
                if ls is not None:
                    ls.pop(int(out_univ), None)
                if unconf is not None:
                    unconf.pop(int(out_univ), None)

    def set_input_channel(self, universe: int, channel: int, value: int,
                          source: str = "remote"):
        """WEB-01: Web-/OSC-Remote setzt einen EINZELNEN DMX-Kanal ueber die
        Input-Override-Schicht — NICHT mehr direkt ins Live-Universe. Frueher rief
        der Web-/OSC-Handler ``universe.set_channel()`` direkt; der 44-Hz-Renderer
        ueberschrieb den Wert auf gepatchten Kanaelen aber jeden Frame wieder
        (Flackern, hielt nur ~1 Frame ~23 ms). Jetzt landet der Wert in
        ``input_layer`` und wird in ``_render_frame`` (Schritt 4b-Input)
        deterministisch als REPLACE eingemischt.

        Anders als ein Art-Net/sACN-Stream ist ein Web-POST ein DISKRETER
        Einzelbefehl: er darf NICHT vom NET-05-Stale-Timeout (~2,5 s) verworfen
        werden. Darum wird der Kanal zusaetzlich in ``_remote_input_channels``
        vermerkt — der Renderer nimmt diese Kanaele vom Source-Timeout aus und
        laesst sie stehen, bis sie per ``clear_remote_input``/``clear_programmer``
        (Release) ausdruecklich geraeumt werden. ``source`` ('web'/'osc') ist nur
        Diagnostik.

        Range-Guards wie im alten set_channel-Pfad: unbekannte Universe verwerfen
        (der Renderer koennte den Kanal ohnehin nur in ``self.universes`` committen),
        ``1<=channel<=512``, ``0<=value<=255``. Never-crash bei kaputtem Payload."""
        try:
            universe = int(universe)
            channel = int(channel)
            value = int(value)
        except (TypeError, ValueError):
            return
        if not (1 <= channel <= 512):
            return
        value = max(0, min(255, value))
        lock = getattr(self, "_input_lock", None)
        if lock is None:
            return
        with lock:
            if universe not in getattr(self, "universes", {}):
                return
            layer = self.input_layer.get(universe)
            if layer is None:
                layer = {}
                self.input_layer[universe] = layer
            layer[channel] = value
            remote = getattr(self, "_remote_input_channels", None)
            if remote is None:
                remote = self._remote_input_channels = {}
            remote.setdefault(universe, set()).add(channel)

    def set_all_white(self, active: bool, exclude_fids=()) -> int:
        """„Alles Weiß" ein-/ausschalten. Gibt die Zahl der gedeckten Geraete zurueck.

        BUG-FBW Slice 2: Der Knopf setzte bisher nichts selbst, sondern startete
        die an ihn gebundene Weiss-Szene — „die Szene weiss das, nicht der
        Button". Eine Szene aus einer Zeit mit weniger Geraeten liess die spaeter
        dazugepatchten dunkel, und ohne Bindung passierte gar nichts. Davids
        Entscheidung (2026-08-02): der Knopf soll **alle gepatchten Geraete**
        weiss setzen.

        ``exclude_fids`` — Geraete, die eine gebundene Funktion ohnehin schon
        bedient. Deren bewusst eingestellter Look (warmweisse PARs o. Ae.) bleibt
        damit erhalten; die Ueberdeckung fuellt nur die Luecke.

        Die Schicht wird EINMAL beim Druck gebaut (nicht pro Frame): sie haengt
        am Patch, und der aendert sich waehrend eines gehaltenen Tasters nicht.
        Geraete ohne DMX-Adressraum (Netzwerk-Laser) bleiben aussen vor —
        ``fixture_uses_dmx`` ist an JEDER Adress-Rechenstelle Pflicht (LAS-04).
        """
        if not active:
            self._all_white_map = None
            return 0
        try:
            from src.core.all_white import white_map
            fixtures = [f for f in self.get_patched_fixtures() if fixture_uses_dmx(f)]
            self._all_white_map = white_map(
                fixtures, get_channels_for_patched, open_value_of_channel,
                exclude_fids=exclude_fids)
        except Exception as e:
            print(f"[AppState] set_all_white error: {e}")
            self._all_white_map = None
            return 0
        return len(self._all_white_map)

    def clear_remote_input(self):
        """WEB-01: Die von Web/OSC ueber ``set_input_channel`` gesetzten Einzel-
        Kanaele wieder freigeben (Release-Pfad). Entfernt sie aus ``input_layer``
        und der Remote-Merkliste; leert eine Universe komplett, faellt ihr
        input_layer-/mode-/last_seen-Eintrag mit weg, damit kein Zombie-Wert
        eingefroren zurueckbleibt. Art-Net/sACN-Kanaele derselben Universe bleiben
        unberuehrt."""
        lock = getattr(self, "_input_lock", None)
        if lock is None:
            return
        with lock:
            remote = getattr(self, "_remote_input_channels", None)
            if not remote:
                return
            ls = getattr(self, "input_last_seen", None)
            for univ, chans in list(remote.items()):
                layer = self.input_layer.get(univ)
                if layer is not None:
                    for ch in list(chans):
                        layer.pop(ch, None)
                    if not layer:
                        self.input_layer.pop(univ, None)
                        self.input_merge_modes.pop(univ, None)
                        if ls is not None:
                            ls.pop(univ, None)
            remote.clear()

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
        # STAB-15: EINEN konsistenten Snapshot des Render-Plans unter _plan_lock
        # ziehen (kurz gehalten) und danach NUR aus diesen Locals rechnen — so
        # kann ein gleichzeitiges _rebuild_render_plan (Umpatchen) nie eine halb
        # getauschte Feld-Kombination in diesen Frame einschleusen.
        with self._get_plan_lock():
            fix_index = self._fix_index
            default_frame = self._default_frame
            commit_spans = self._commit_spans
            patched_set = self._patched_set
            # _laser_estop_addrs wie zuvor defensiv (Test-Stubs ohne das Feld).
            laser_estop_addrs = getattr(self, "_laser_estop_addrs", {})
        # 1. Scratch-Universen mit Default-Frame vorbelegen (= Per-Frame-Clear).
        scratch: dict[int, Universe] = {}
        for univ, _live in live_universes:
            su = Universe(univ)
            base = default_frame.get(univ)
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
            base = default_frame.get(univ)
            patched = patched_set.get(univ, frozenset())
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
        for fidi, entry in fix_index.items():
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
            base = default_frame.get(fx.universe)
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
                # Executor-Schreibungen protokollieren, um func_driven zu bereinigen.
                for _su in scratch.values():
                    _su.begin_write_log()
                self._apply_fixture_map(scratch, merged, fix_index=fix_index)
                # WP-6-Fix (Prioritaets-Inversion): func_driven wurde VOR den
                # Executoren erfasst und schuetzt Nicht-Intensitaets-Kanaele vor dem
                # Programmer-LTP ("Funktion besitzt sie"). Ueberschreibt aber ein Cue
                # so einen Kanal, gehoert er nicht mehr der Funktion — er dann trotzdem
                # im Schutz zu lassen liesse den (hoechstprioren) Programmer aussen vor
                # und den CUE-Wert gegen den Programmer gewinnen (untere Ebene schlaegt
                # obere). Darum jede vom Cue geschriebene Adresse aus func_driven
                # nehmen: rein funktions-getriebene (cue-unberuehrte) Kanaele bleiben
                # geschuetzt, cue-uebernommene faellt der Programmer korrekt wieder an.
                for _univ, _su in scratch.items():
                    _ex = _su.end_write_log()
                    if _ex and _univ in func_driven:
                        func_driven[_univ] = func_driven[_univ] - _ex
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
            entry = fix_index.get(fidi)
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
                entry = fix_index.get(fidi)
                if not entry:
                    continue
                univ = entry[0].universe
                if univ in protect:
                    for a in dim_addrs.get(fidi, ()):
                        protect[univ].discard(a)
        self._apply_fixture_map(scratch, programmer,
                                skip_intensity_for=set(prog_factor) | owned_by_func,
                                protect_addrs=protect, fix_index=fix_index)

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
            entry = fix_index.get(fidi)
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
            base = default_frame.get(univ)
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

        # 4a³. Szenen-Vorschau (QA-LIVE): einmalige UI-Vorschau als Render-Layer.
        # Liegt nach Funktionen/Programmer/impliziter Helligkeit, aber VOR allen
        # Mastern, Simple Desk und Laser-NOT-AUS. Sie kann daher keinen direkten
        # Roh-Write mehr erzeugen und wird im Folgeframe automatisch freigegeben.
        preview_state = getattr(self, "_scene_preview", None)
        if preview_state:
            preview_lock = getattr(self, "_scene_preview_lock", None)
            if preview_lock is not None:
                with preview_lock:
                    scene_preview = {u: dict(chans)
                                     for u, chans in self._scene_preview.items()}
                    self._scene_preview = {}
            else:
                scene_preview = {u: dict(chans) for u, chans in preview_state.items()}
                self._scene_preview = {}
            for univ, chans in scene_preview.items():
                su = scratch.get(univ)
                if su is None:
                    continue
                for ch, val in chans.items():
                    if 1 <= ch <= 512:
                        su.set_channel(ch, max(0, min(255, int(val))))

        # 4a³. „Alles Weiß" — Moment-Override (BUG-FBW Slice 2, Davids
        #      Entscheidung 2026-08-02: der Knopf soll wirklich ALLE gepatchten
        #      Geraete weiss setzen, nicht nur die einer gebundenen Szene).
        #      Absolut geschrieben, ohne ``protect_addrs``: ein Panik-Knopf muss
        #      auch gegen einen laufenden Farb-Effekt durchkommen — genau daran
        #      scheiterte die Szenen-Loesung, sobald eine Matrix die Farbkanaele
        #      besass. Bewusst HIER, also VOR 4b: Grand-Master und Blackout
        #      wirken weiterhin darueber, damit „alles weiss" den Notaus nicht
        #      aushebelt.
        weiss = getattr(self, "_all_white_map", None)
        if weiss:
            self._apply_fixture_map(scratch, weiss, fix_index=fix_index)

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
        # FM-HEADLAYOUT A4: kopf-genaue Submaster-Faktoren. EINMAL pro Frame fragen,
        # ob es ueberhaupt einen kopf-beschraenkten Slot gibt — sonst kostet der
        # Bestandsfall (der Normalfall) nicht einen einzigen Aufruf pro Fixture.
        head_fac_for = None
        if om is not None:
            try:
                if om.has_head_submasters():
                    head_fac_for = getattr(om, "submaster_head_factors_for", None)
            except Exception:
                head_fac_for = None
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
            head_fac = {}
            if head_fac_for is not None:
                try:
                    head_fac = head_fac_for(fidi) or {}
                except Exception:
                    head_fac = {}
            if not head_fac and (factor >= 0.999 or not addrs):
                continue
            entry = fix_index.get(fidi)
            if not entry:
                continue
            su = scratch.get(entry[0].universe)
            if su is None:
                continue
            if not head_fac:
                for a in addrs:
                    su.set_channel(a, int(su.get_channel(a) * factor))
                continue
            # Kopf-Fall: pro Adresse GENAU EINEN Faktor bilden und EINMAL anwenden.
            # Zwei getrennte int()-Durchgaenge (erst geraeteweit, dann pro Kopf)
            # wuerden zweimal abrunden und den Fader-Weg verfaelschen.
            # ``get(a, 1.0)``: eine kopf-exklusive Farbadresse steht NICHT in
            # ``inten_addrs``, wenn das Geraet einen geteilten Master-Dimmer hat
            # (dann ist der die Intensitaets-Quelle) — sie bekommt daher nur den
            # Kopf-Faktor, nicht zusaetzlich den geraeteweiten.
            addr_fac = {a: factor for a in addrs}
            head_map = None
            for head, hf in head_fac.items():
                if hf >= 0.999:
                    continue
                if head_map is None:      # EIN Kanal-Durchlauf fuer alle Koepfe
                    head_map = self._fixture_head_intensity_addr_map(entry[0], entry[1])
                for a in head_map.get(head, ()):
                    addr_fac[a] = addr_fac.get(a, 1.0) * hf
            for a, f in addr_fac.items():
                if f < 0.999:
                    su.set_channel(a, int(su.get_channel(a) * f))

        # 4b². Feature-Dimmer-Master (F-26): per-Slot multiplikativer Master ueber
        #      eine Fixture-Menge, effekt-UNABHAENGIG (greift am fertigen Output,
        #      nach allen Effekten/Programmer). "Intensity"-Feature trifft die
        #      Helligkeits-Adressen (inten_addrs = echter Dimmer, sonst Farb-
        #      Fallback) — wie der globale Submaster; andere Features (Color/Gobo/
        #      Beam/Position/Effect) ihre via classify_attr klassifizierten Kanaele.
        #      Jede Adresse wird GENAU EINMAL mit dem Produkt aller sie treffenden
        #      Slots skaliert (kein Doppel-Dimmen). Shutter/Strobe wird ueber
        #      'Intensity' NICHT mitgedimmt (nicht in inten_addrs — konsistent zum
        #      Grand Master). Nur aktiv, wenn ueberhaupt Slots existieren.
        # STAB-13: unter _fd_lock EINEN Snapshot der (unveraenderlichen) Slot-Objekte
        # ziehen — nicht die live .values()-View iterieren (UI-Thread kann die
        # dict-Groesse aendern -> "dict changed size during iteration" -> Frame weg).
        fd_lock = getattr(self, "_fd_lock", None)
        if fd_lock is not None:
            with fd_lock:
                fd_snapshot = list(getattr(self, "feature_dimmers", {}).values())
        else:
            fd_snapshot = list((getattr(self, "feature_dimmers", None) or {}).values())
        if fd_snapshot:
            active = [s for s in fd_snapshot
                      if getattr(s, "level", 1.0) < 0.999 and s.fids]
            target_fids: set[int] = set()
            for s in active:
                target_fids |= set(s.fids)
            for fidi in target_fids:
                entry = fix_index.get(fidi)
                if not entry:
                    continue
                fx, chans = entry
                su = scratch.get(fx.universe)
                if su is None:
                    continue
                hit = [s for s in active if fidi in s.fids]
                inten = set(inten_addrs.get(fidi, ()))
                for ch in chans:
                    attr = (getattr(ch, "attribute", "") or "").lower()
                    addr = fx.address + ch.channel_number - 1
                    if not (1 <= addr <= 512):
                        continue
                    grp = classify_attr(attr)
                    f = 1.0
                    for s in hit:
                        feats = s.features or _DEFAULT_FEATURE_SET
                        if "Intensity" in feats and addr in inten:
                            f *= s.level
                        elif grp != "Intensity" and grp in feats:
                            f *= s.level
                    if f < 0.999:
                        su.set_channel(addr, int(su.get_channel(addr) * f))

        # 4b-Input. F-20: Art-Net/sACN-EINGANG als Schicht. Extern empfangene DMX-
        #     Werte (Puffer input_layer, vom RX-Thread gefuellt) je Universe mit dem
        #     konfigurierten Modus einmischen: HTP (Hoechstwert), LTP/REPLACE (ersetzt).
        #     RAW (nach dem Dimmer-Master, vor Simple Desk) — externer Eingang wird
        #     NICHT vom eigenen Submaster skaliert; manueller Simple-Desk-Override (4c)
        #     gewinnt weiterhin oben drauf. Leer = kein Eingang = kein Effekt.
        in_state = getattr(self, "input_layer", None)
        if in_state:
            in_lock = getattr(self, "_input_lock", None)

            def _expire_and_snapshot():
                # NET-05: Quellen, die laenger als INPUT_SOURCE_TIMEOUT_S nichts mehr
                # gesendet haben (Konsole abgezogen/abgestuerzt), verwerfen — sonst
                # mischt der Renderer ihre letzten Werte fuer immer weiter und friert
                # die Kanaele ein (der Blackout/Submaster skaliert den Input NICHT).
                remote = getattr(self, "_remote_input_channels", None) or {}
                ls = getattr(self, "input_last_seen", None)
                if ls is not None:
                    now = time.monotonic()
                    stale = [u for u in list(in_state.keys())
                             if now - ls.get(u, now) > INPUT_SOURCE_TIMEOUT_S]
                    for u in stale:
                        rc = remote.get(u)
                        if rc:
                            # WEB-01: Web/OSC-Kanaele sind diskrete Befehle (kein
                            # Stream) -> NICHT vom Source-Timeout verwerfen. Nur die
                            # Stream-Kanaele (Art-Net/sACN) dieser Universe entfernen,
                            # die Remote-Kanaele stehen lassen.
                            layer = in_state.get(u)
                            if layer is not None:
                                for ch in [c for c in list(layer) if c not in rc]:
                                    layer.pop(ch, None)
                                if not layer:
                                    in_state.pop(u, None)
                                    self.input_merge_modes.pop(u, None)
                            ls.pop(u, None)
                        else:
                            in_state.pop(u, None)
                            self.input_merge_modes.pop(u, None)
                            ls.pop(u, None)
                return ({u: dict(ch) for u, ch in in_state.items()},
                        dict(self.input_merge_modes),
                        {u: set(chs) for u, chs in remote.items()})

            if in_lock is not None:
                with in_lock:
                    in_layer, in_modes, in_remote = _expire_and_snapshot()
            else:
                in_layer, in_modes, in_remote = _expire_and_snapshot()
            for univ, chans in in_layer.items():
                su = scratch.get(univ)
                if su is None:
                    continue
                htp = in_modes.get(univ, "HTP") == "HTP"
                rc = in_remote.get(univ, ())
                for ch, val in chans.items():
                    if not (1 <= ch <= 512):
                        continue
                    v = max(0, min(255, int(val)))
                    # WEB-01: von Web/OSC gesetzte Kanaele gelten IMMER als REPLACE
                    # (diskreter Befehl), unabhaengig vom Per-Universe-Merge-Mode.
                    if htp and ch not in rc:
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

        # 4d. UXT-12: Laser-NOT-AUS — DMX-Muster-Laser (L2600 & Co.) hart dunkel.
        #     OBERSTE Ebene (nach ALLEN Merges, unmittelbar vor dem Commit): alle
        #     Laser-Kanäle auf 0 zwingen, unabhängig von Programmer/Effekten. Der
        #     Netzwerk-Streamer wird separat über estop_all/armed verriegelt; ein
        #     L2600 gibt über DMX aus und würde sonst nach dem Not-Aus weiterlaufen.
        #     (Annahme: Betriebsart/Shutter 0 = Laser aus; gilt für den L2600.)
        if getattr(self, "laser_estop_active", False):
            for univ, laser_addrs in laser_estop_addrs.items():
                su = scratch.get(univ)
                if su is None:
                    continue
                for addr in laser_addrs:
                    su.set_channel(addr, 0)

        # 5. Atomarer Commit der gepatchten Spans ins Live-Universe.
        for univ, live in live_universes:
            su = scratch.get(univ)
            if su is None:
                continue
            data = su.get_all()
            for start, length in commit_spans.get(univ, ()):
                live.set_range(start, data[start - 1:start - 1 + length])
            # Roh-Kanaele, die Funktionen (z. B. ScriptFunction setdmx) auf NICHT
            # gepatchte Adressen geschrieben haben, ebenfalls committen — und
            # zuvor geschriebene, jetzt nicht mehr aktive, wieder freigeben (0).
            patched = patched_set.get(univ, frozenset())
            cur = {a for a in range(1, 513) if a not in patched and data[a - 1] != 0}
            prev = self._engine_extra_prev.get(univ)
            if cur or prev:
                for a in cur:
                    live.set_channel(a, data[a - 1])
                if prev:
                    for a in prev - cur:
                        live.set_channel(a, 0)
                self._engine_extra_prev[univ] = cur
            # A3D-18: vom Rebuild vorgemerkte, jetzt ungepatchte Adressen final auf 0
            # — als LETZTER Schritt fuer dieses Universe, NACH dem Span-Commit oben.
            # Ein nachlaufender Alt-Plan-Commit (stale Snapshot) haette die Adresse
            # sonst wieder gesetzt; hier ueberschreibt der Render-Thread sie determi-
            # nistisch mit 0. Einmalig konsumiert (pop) — Rendering ist single-threaded.
            pr = getattr(self, "_pending_release", None)
            if pr:
                rel = pr.pop(univ, None)   # unbedingt konsumieren (Race-Guard-pop)
                if rel:
                    # CDX-17: nur WIRKLICH-ungepatchte Adressen nullen. Wird eine
                    # Adresse entfernt und VOR diesem Render-Tick wieder gepatcht
                    # (Bulk-Show-Load, schnelles Undo/Redo), steht sie noch aus dem
                    # frueheren Rebuild in _pending_release, ist jetzt aber wieder in
                    # patched_set. Ohne Filter zwingt die Nullung das NEU-gepatchte
                    # Fixture fuer diesen einen Frame auf 0 (sichtbares Schwarz-
                    # Aufblitzen). Der pop bleibt unbedingt (konsumiert gegen nach-
                    # laufende Alt-Plan-Commits); nur die Schreib-Teilmenge wird auf
                    # ungepatchte Adressen (a not in patched) verengt — genuin
                    # entpatchte Adressen werden weiter deterministisch freigegeben.
                    for a in rel:
                        if 1 <= a <= 512 and a not in patched:
                            live.set_channel(a, 0)

    def _apply_fixture_map(self, scratch: dict, fixmap: dict,
                           skip_intensity_for: set | None = None,
                           protect_addrs: dict | None = None,
                           fix_index: dict | None = None):
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
        # STAB-15: den vom Aufrufer (_render_frame) unter _plan_lock gezogenen
        # Plan-Snapshot verwenden; nur ohne (Alt-Aufruf) auf das Live-Feld fallen.
        if fix_index is None:
            with self._get_plan_lock():
                fix_index = self._fix_index
        for fid, attrs in fixmap.items():
            try:
                fidi = int(fid)
            except (TypeError, ValueError):
                continue
            entry = fix_index.get(fidi)
            if not entry:
                continue
            fx, chans = entry
            # LAS-04: Netzwerk-Laser nie in die Scratch-Universen malen (ihre
            # Platzhalter-Adresse laege sonst in den Spans echter Geraete).
            if not fixture_uses_dmx(fx):
                continue
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

    def set_feature_dimmer(self, slot, fids, features=None, level: float = 1.0):
        """F-26: setzt/aktualisiert den Feature-Dimmer-Master eines Slots (stabile
        Slider-ID). ``fids`` = Ziel-Fixtures (Gruppe/Auswahl LIVE aufgeloest),
        ``features`` = Menge der Feature-Gruppen-Namen (leer/None = {'Intensity'} =
        Helligkeit), ``level`` 0.0-1.0 multiplikativ. ``level`` >= 0.999 ODER keine
        ``fids`` entfernt den Slot (kein unnoetiges Skalieren). Wirkt im Render-
        Schritt 4b² effekt-unabhaengig auf den fertigen Output."""
        try:
            level = max(0.0, min(1.0, float(level)))
        except (TypeError, ValueError):
            return
        fid_set: set[int] = set()
        for f in fids or ():
            try:
                fid_set.add(int(f))
            except (TypeError, ValueError):
                continue
        feat_set = frozenset(str(x) for x in (features or ()))
        # STAB-13: Groessen-Aenderung unter _fd_lock (Renderer snapshottet darunter).
        with self._fd_lock:
            if level >= 0.999 or not fid_set:
                self.feature_dimmers.pop(slot, None)
            else:
                self.feature_dimmers[slot] = FeatureDimmer(
                    frozenset(fid_set), feat_set, level)

    def clear_feature_dimmers(self):
        """Alle Feature-Dimmer-Slots leeren (z. B. bei neuer/geladener Show, damit
        keine Slots zerstoerter Slider stehen bleiben)."""
        with self._fd_lock:
            self.feature_dimmers.clear()

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
            elif attr in _DIM_COLOR_ATTRS and attr not in _SUBTRACTIVE_COLOR_ATTRS:
                # A3D-37: additive Farbe (RGB/W/A/UV) darf als virtueller Dimmer
                # dienen; subtraktives CMY NICHT (Skalieren Richtung 0 hellt auf).
                color.append(addr)
        return inten if inten else color

    def _fixture_head_intensity_addr_map(self, fx, chans) -> dict:
        """FM-HEADLAYOUT A4: ``{head: [addr]}`` — welche Adressen ein KOPF-genauer
        Dimm-Faktor (VC-Submaster pro Kopf) je Kopf skalieren darf.

        Pro Kopf gilt dieselbe Regel wie in ``_fixture_intensity_addrs`` (echter
        Dimmer falls vorhanden, sonst ADDITIVE Farbe als virtueller Dimmer; CMY nie),
        aber ausschliesslich auf **kopf-exklusiven** Kanaelen.

        ★ Kopf-exklusiv heisst: das Attribut kommt **GENAU SO OFT vor wie das Geraet
        Koepfe hat** (``color_head_count`` = Zahl der ``color_r``-Kanaele — dieselbe
        Quelle, aus der auch die Kopf-Zellen der Gruppe stammen). Die naheliegendere
        Regel „kommt mehr als einmal vor ⇒ pro Kopf" ist FALSCH und war ein
        bestaetigter Review-Fund: **107 Modi der eingebauten Library** haben
        ZONEN-Master, also ein wiederholtes ``intensity``, dessen Anzahl NICHT der
        Kopfzahl entspricht (z. B. `Frost FX Bar W` 14 Koepfe / 2 Zonen-Dimmer,
        `Spiider (4) Full RGBW` 21 / 2). Dort haette „Kopf 0" den Weiss-Master ueber
        ALLE Pixel erwischt und „Kopf 1" den Hintergrund-Master, waehrend Pixel 1
        und 2 ueber gar keinen Fader erreichbar gewesen waeren.

        Ein Attribut, das seltener/oefter vorkommt, gilt als GETEILT und bleibt
        unangetastet — sonst dimmte „Kopf 2" ueber den gemeinsamen Master-Dimmer das
        ganze Geraet. Genau deshalb reicht ``channels_for_head`` hier nicht: das
        reicht geteilte Attribute bewusst JEDEM Kopf durch (richtig fuer den
        Programmer-/Matrix-SCHREIBpfad, falsch fuer eine Dimm-Maske).

        Ein Kopf ohne eigenen Intensitaets-/Farbkanal bekommt ``[]`` — der Fader hat
        dort ehrlich keine Wirkung, statt ersatzweise das ganze Geraet zu dimmen.
        Single-Head-Geraete (und Laser) liefern ``{}``.

        EIN Durchlauf ueber die Kanaele fuer ALLE Koepfe: der Renderer ruft das pro
        Fixture und Frame: die frueher kopfweise Fassung war bei Pixel-Panels
        O(Koepfe x Kanaele) und sprengte bei 144 Pixeln das 22,7-ms-Frame-Budget."""
        n_heads = color_head_count_for_channels(fx, chans)
        if n_heads < 2:
            return {}
        counts: dict[str, int] = {}
        for ch in chans:
            a = (getattr(ch, "attribute", "") or "").lower()
            counts[a] = counts.get(a, 0) + 1
        inten: dict[int, list[int]] = {}
        color: dict[int, list[int]] = {}
        seen: dict[str, int] = {}
        for ch in chans:
            attr = (getattr(ch, "attribute", "") or "").lower()
            occ = seen.get(attr, 0)
            seen[attr] = occ + 1
            if counts.get(attr, 0) != n_heads:
                continue          # geteilter Master bzw. Zonen-Kanal -> kein Kopf-Kanal
            addr = fx.address + ch.channel_number - 1
            if not (1 <= addr <= 512):
                continue
            if attr in _DIM_INTENSITY_ATTRS:
                inten.setdefault(occ, []).append(addr)
            elif attr in _DIM_COLOR_ATTRS and attr not in _SUBTRACTIVE_COLOR_ATTRS:
                color.setdefault(occ, []).append(addr)
        return {h: (inten.get(h) or color.get(h) or []) for h in range(n_heads)}

    def _fixture_head_intensity_addrs(self, fx, chans, head) -> list[int]:
        """Kopf-Maske eines EINZELNEN Kopfes (Bequemlichkeits-Sicht auf
        ``_fixture_head_intensity_addr_map``; der Renderer nutzt die Map)."""
        return self._fixture_head_intensity_addr_map(fx, chans).get(int(head), [])

    def _build_gm_mask(self, fix_index) -> dict[int, set]:
        """Grand-Master-Adressmaske pro gepatchtem DMX-Universum: die zu dimmenden
        Intensitaets-/Farbadressen (Pan/Tilt/Gobo bleiben unangetastet, Audit B4).

        WICHTIG: JEDES gepatchte DMX-Universum bekommt einen (ggf. LEEREN) Eintrag.
        So kann der Sende-Pfad (``output_manager._send_all``) 'gepatcht, aber ohne
        Intensitaets-/Farbkanal' (leere Maske -> NICHTS skalieren) von 'ungepatchtes
        Roh-Universum' (KEIN Key -> global dimmen wie bisher) unterscheiden. Ohne die
        Leer-Saat fiel ein reines Pan/Tilt/Gobo-Universum (z. B. nur Farbrad-Spots
        ohne Dimmer/RGB) in den mask-is-None-Global-Dim-Zweig -> der GM fuhr Moving
        Heads bei GM<100 % auf falsche Pan/Tilt-Positionen."""
        gm_mask: dict[int, set] = {}
        for _fid, (fx, chans) in fix_index.items():
            if not fixture_uses_dmx(fx):
                continue
            addrs = gm_mask.setdefault(fx.universe, set())   # Universum registrieren
            for addr in self._fixture_intensity_addrs(fx, chans):
                addrs.add(addr)
        return gm_mask

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
        # Executor-Bindungen auf ALLEN Pages loesen: sonst behaelt ein Executor die
        # tote CueStack-Referenz, tickt/rendert sie weiter (Ghost-Playback) und GO/
        # BACK/Fader wirken auf eine Cueliste, die nirgends mehr sichtbar ist.
        pe = self.playback_engine
        if pe is not None:
            try:
                stack.stop()
            except Exception:
                pass
            for page in pe.pages:
                for ex in page:
                    if ex.stack is stack:
                        ex.stack = None
        self._emit("stacks_changed", None)
        self._emit("cue_stack_changed", None)

    def record_cue(self, stack, number: float, label: str = "",
                   fade_in: float = 2.0, fade_out: float = 0.0):
        """Speichert aktuellen Programmer-Inhalt als neue Cue."""
        from .engine.cue import Cue
        # STAB-21: Snapshot unter _prog_lock (wie _render_frame:1324) — sonst kann ein
        # paralleler MIDI-/OSC-/Web-RX-set_programmer_value ein NEUES fid einfuegen,
        # waehrend diese Comprehension self.programmer iteriert (das innere dict(attrs)
        # ist ein GIL-Yield-Punkt) -> "dictionary changed size during iteration"
        # (unabgefangen -> Record-Cue bricht ab, Cue nicht gespeichert).
        with self._prog_lock:
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
    """Invalidiert den Channel-Cache (bei jeder Patch-Aenderung aufrufen).
    Leert auch den viz_model-Override-Cache (FM-12) mit — Profil-Aenderungen
    aus Generator/Editor reisen ueber denselben Invalidierungs-Pfad."""
    _channel_cache.clear()
    _viz_model_override_cache.clear()
    # FM-17: die Kopf-Karte haengt an genau diesen Kanal-Listen — zusammen
    # invalidieren, sonst zeigt sie auf Kanaele eines alten Modus (der Schluessel
    # ist die Objekt-Identitaet der gecachten Liste, siehe head_channel_map).
    _head_map_cache.clear()
    _cached_channel_list_ids.clear()


# FM-12: Cache profile_id -> viz_model-Override ("" = Automatik). Wie der
# Channel-Cache noetig, weil viz_model_for pro Fixture pro Frame laufen kann.
_viz_model_override_cache: dict = {}


def viz_model_override_for(fixture) -> str:
    """Expliziter 3D-Modell-Override aus dem FixtureProfile (FM-12).

    Liefert ``FixtureProfile.viz_model`` des gepatchten Geraets oder ``""``
    (= Automatik). Gecached pro Profil-ID; ``clear_channel_cache`` leert mit."""
    pid = getattr(fixture, "fixture_profile_id", None)
    if pid is None:
        return ""
    cached = _viz_model_override_cache.get(pid)
    if cached is not None:
        return cached
    try:
        from .database.fixture_db import engine
        from .database.models import FixtureProfile
        with Session(engine()) as s:
            prof = s.get(FixtureProfile, pid)
            val = (getattr(prof, "viz_model", "") or "").strip() if prof else ""
    except Exception:
        # Transienter DB-Fehler (z.B. gesperrte fixtures.db mitten in einem
        # Generator-Save): NICHT cachen — sonst wird der Fehlerfall dauerhaft
        # als "kein Override" eingefroren. Naechster Aufruf versucht es neu.
        return ""
    _viz_model_override_cache[pid] = val
    return val


def suggest_viz_model(fixture_type: str, attributes) -> str | None:
    """Reine Multi-Emitter-Heuristik OHNE DB-Zugriff (FM-12).

    ``attributes`` = Liste der Kanal-Attribut-Strings eines Modus. Liefert
    'mover_bar' / 'par_bar' / 'spider' oder ``None`` (= Single-Head, Aufrufer
    nutzt den ``fixture_type``). Identische Regeln wie ``viz_model_for``
    (dort mit echten DB-Kanaelen); der Fixture-Generator nutzt sie fuer den
    Live-Vorschlag auf noch ungespeicherten Kanallisten."""
    if (fixture_type or "") in ("laser", "matrix"):
        # Laser = Punkt-Scanner (FLA-1); matrix = Pixel-Panel mit eigenem
        # Renderer (FM-13) — beide NIE ueber die Multi-Emitter-Heuristik routen.
        return None
    attrs = [(a or "") for a in attributes]
    banks = sum(1 for a in attrs if a == "color_r")
    if banks < 2:
        return None
    pan_count = sum(1 for a in attrs if a == "pan")
    tilt_count = sum(1 for a in attrs if a == "tilt")
    if pan_count >= 2:
        return "mover_bar"
    if pan_count == 0 and tilt_count == 0:
        return "par_bar"
    return "spider"


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
        # FM-17: nur DIESE Listen darf die Kopf-Karte per Objekt-Identitaet
        # cachen — der Channel-Cache haelt sie am Leben, ihre id kann also nicht
        # von einer anderen Liste wiederverwendet werden. Eine frei gebaute
        # Kanal-Liste (Tests, Ad-hoc-Aufrufer) wird jedes Mal frisch gerechnet.
        _cached_channel_list_ids.add(id(result))
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


# FM-16: Multi-Head-Fixtures als Pro-Kopf-Matrix. Kanonische Kopf-Sicht — EINE
# Quelle fuer den Matrix-Pro-Kopf-Write UND (spaeter) die EFX-Pro-Kopf-Ziele.


def color_head_count_for_channels(fixture, channels) -> int:
    """Wie ``color_head_count``, aber gegen eine BEREITS geladene Kanalliste —
    fuer Aufrufer, die die Kanaele ohnehin in der Hand haben (Renderer-Hot-Path:
    spart den Cache-Lookup pro Frame). EINE Zaehl-Regel fuer beide."""
    if (getattr(fixture, "fixture_type", "") or "") == "laser":
        return 1
    try:
        n = sum(1 for c in channels
                if (getattr(c, "attribute", "") or "").lower() == "color_r")
        return n if n >= 1 else 1
    except Exception:
        return 1


def move_head_count_for_channels(fixture, channels) -> int:
    """Wie :func:`pan_tilt_head_count`, aber gegen eine BEREITS geladene Kanalliste
    — das Gegenstueck zu :func:`color_head_count_for_channels` fuer die BEWEGUNGS-
    achse.

    ★ Warum es beide Zaehlungen braucht (FM-9/A5): Farb- und Bewegungskoepfe eines
    Geraets sind NICHT dieselbe Zahl. **Ueber die eingebaute Library ausgezaehlt
    (5116 Modi) gehen sie bei 831 Modi auseinander — in BEIDE Richtungen:**

    * **108 Modi** haben >=2 Bewegungs-, aber <2 Farbkoepfe: ``Event Bar LED/Pro/
      Q4``, ``HYDRABEAM 4000 RGBW`` in ``19-Kanal``/``32-Kanal``, ``Hydrabeam 400
      Series`` ``15-CH``/``28-CH``. Mit der Farb-Zahl validiert wird die
      Kopf-Einschraenkung **verworfen** -> „Kopf 2" gewaehlt, und trotzdem fahren
      alle vier Koepfe.
    * **723 Modi** haben >=2 Farb-, aber <2 Bewegungskoepfe: Pixel-Bars und die
      Spider (``Speider 14ch``, ``Mini Spider ZQ-B20 15ch``). Dort wird die
      Einschraenkung faelschlich **behalten** und erzeugt ``pan#1``.

    Was ``pan#1`` auf einem Ein-Pan-Geraet wirklich tut, ist gemessen:
    ``_flush_programmer_to_dmx`` laeuft ueber die KANAELE, der einzige Pan-Kanal
    fragt also nach ``"pan"`` — ``pan#1`` liest niemand. Der Kanal faellt auf
    seinen ``default_value`` zurueck, der Kopf springt also auf Default-Position
    und folgt dem Pad nicht mehr (gemessen: Default 128, geschrieben 200, Kanal
    blieb 128). Kein Fehler, keine Meldung.
    """
    try:
        pans = sum(1 for c in channels
                   if (getattr(c, "attribute", "") or "").lower() == "pan")
        tilts = sum(1 for c in channels
                    if (getattr(c, "attribute", "") or "").lower() == "tilt")
        return max(1, pans, tilts)
    except Exception:
        return 1


def attr_head_count_for_channels(fixture, channels, attribute: str) -> int:
    """Wie viele Koepfe hat dieses Geraet **fuer genau dieses Attribut**?

    ★ Die allgemeinste der drei Zaehlungen — und die einzige, die immer stimmt.
    ``color_head_count`` zaehlt ``color_r``, ``move_head_count`` zaehlt Pan/Tilt;
    beide sind Spezialfaelle davon. Dass sie noetig sind, zeigt der Blick in die
    Library: eine ``HYDRABEAM 4000 RGBW [19-Kanal]`` hat 4 Pan, 4 Tilt, **5**
    Intensity und **1** Farbbank. „Wie viele Koepfe hat das Geraet" hat dort also
    drei verschiedene richtige Antworten, je nachdem was man schreibt.

    Genau das spiegelt ``channel_occurrence_keys``: jedes Attribut wird fuer sich
    gezaehlt, das N-te Vorkommen von ``A`` heisst ``A#N``. Wer eine
    Kopf-Einschraenkung fuer einen Schreibvorgang auf ``A`` validiert, muss also
    die Vorkommen von ``A`` zaehlen — sonst entsteht ein ``A#N`` ohne Kanal
    (Kopf faellt auf seinen Default) oder die Einschraenkung faellt weg (alle
    Koepfe reagieren). Beide Fehlrichtungen sind stumm, s. FM-9/A5.
    """
    a = (attribute or "").split("#", 1)[0].lower()
    if not a:
        return 1
    try:
        n = sum(1 for c in channels
                if (getattr(c, "attribute", "") or "").lower() == a)
        return n if n >= 1 else 1
    except Exception:
        return 1


def head_counter_for_attr(attribute: str):
    """``(fixture, channels) -> int`` fuer ``validate_head_restrictions``, passend
    zu dem Attribut, das gleich geschrieben wird."""
    return lambda fx, chans: attr_head_count_for_channels(fx, chans, attribute)


def color_head_count(fixture) -> int:
    """Anzahl unabhaengig faerbbarer Koepfe/Emitter = Zahl der ``color_r``-Kanaele
    (jeder Kopf hat eine eigene RGB(W)-Bank). 1 = Single-Head/einfarbig, >=2 =
    Multi-Head (Spider/Mover-Bar/Beam-Bar wie Hydrabeam 56ch). Basis fuer die
    Pro-Kopf-Matrix (FM-16): jeder Kopf wird eine Grid-Zelle. Laser-Ausnahme wie
    is_spider_fixture: ein Punkt-Scanner ist kein Multi-Emitter."""
    if (getattr(fixture, "fixture_type", "") or "") == "laser":
        return 1
    try:
        return color_head_count_for_channels(
            fixture, get_channels_for_patched(fixture))
    except Exception:
        return 1


# FM-17: Kopf-Anker. Ein Kopf ist das, was sich EIGEN BEWEGT bzw. EIGEN FAERBT —
# an diesen Attributen haengt die Kopf-Zahl, nicht am Dimmer. Reihenfolge = Vorrang
# bei Gleichstand; genommen wird das am haeufigsten wiederholte.
_HEAD_ANCHOR_ATTRS = ("pan", "tilt", "color_r")

# FM-17: Kopf-Karte pro Kanal-Liste, gecached wie der Channel-Cache selbst.
# ★ Ohne das ist es die O(Koepfe x Kanaele)-Falle aus der Review-Checkliste:
# rgb_matrix.write ruft die Projektion PRO ZELLE PRO FRAME auf — bei einem
# 144-Pixel-Panel waeren das 144 volle Kanal-Durchlaeufe je 44-Hz-Frame (dieselbe
# Form, die 2026-07-28 mit 118,88 ms/Frame gemessen wurde; Budget sind 22,73 ms).
# Schluessel ist die Objekt-IDENTITAET der gecachten Liste: get_channels_for_patched
# gibt pro (Profil, Modus) DIESELBE Liste zurueck, und clear_channel_cache leert
# beide Caches gemeinsam — die ids koennen also nicht auf eine andere Liste
# weiterzeigen, solange der Eintrag lebt.
_head_map_cache: dict = {}
# ids der Listen, die WIRKLICH im Channel-Cache haengen (nur die duerfen per
# Identitaet gecached werden — sonst koennte eine kurzlebige Ad-hoc-Liste ihre
# Adresse an eine spaetere Liste vererben und deren Karte verfaelschen).
_cached_channel_list_ids: set = set()


def head_channel_map(channels) -> dict:
    """Welcher Kanal gehoert zu WELCHEM Kopf — ``{attr: [Index je Kopf]}``.

    ★ FM-17. Die alte Regel „Kopf N = N-tes Vorkommen des Attributs" zaehlt
    Vorkommen und nicht Koepfe. Das geht schief, sobald ein Attribut neben den
    Pro-Kopf-Kanaelen noch einen GETEILTEN Kanal hat — der klassische Fall ist der
    Master-Dimmer. Gemessen an der ``HYDRABEAM 4000 RGBW [19-Kanal]`` aus Davids
    Rig: ``CH1 Master dimmer`` + ``CH9/12/15/18 Kopf 1..4 Dimmer``. „Kopf 2"
    landete damit auf ``intensity#1`` = CH9 = **Kopf 1**, und „Kopf 1" auf dem
    gemeinsamen Master, dimmte also alles.

    Diese Funktion bestimmt die Zuordnung stattdessen ueber **Kopf-Segmente**:
    Anker sind die Vorkommen des am haeufigsten wiederholten Kopf-Attributs
    (``pan``/``tilt``/``color_r`` — was sich eigen bewegt bzw. eigen faerbt).
    Kopf N besitzt die Kanaele von seinem Anker bis zum naechsten Anker; pro
    Segment zaehlt das ERSTE Vorkommen eines Attributs. Alles vor dem ersten
    Anker und jedes zusaetzliche Vorkommen im Segment ist GETEILT.

    Das trifft den geteilten Master an jeder Position, und genau daran scheitert
    jede Offset-Regel: er steht vorn (Hydrabeam ``CH1``), hinten (Event Bar Pro
    ``CH21``) ODER mittendrin (Impression X4 Bar 10 ``CH12``, zwischen Set 1 und
    Set 2).

    **Rueckwaerts-sicher by design:** Ein Attribut kommt nur in die Karte, wenn
    sich fuer JEDEN Kopf genau ein Kanal findet. Sonst fehlt es — und der Aufrufer
    bleibt beim Vorkommens-Zaehlen. Ueber die eingebaute + importierte Library
    (5116 Modi) aendert das 128 Zuordnungen; die 27 Intensity-Faelle sind
    durchgaengig ``Master + Kopf 1..3`` -> ``Kopf 1..4``. Die Anker-Attribute
    selbst koennen sich nie aendern (ihre Vorkommen SIND die Segmentgrenzen) —
    Pan/Tilt pro Kopf, also EFX und XY-Pad, bleiben damit beweisbar unberuehrt.

    NICHT beruehrt wird ``channel_occurrence_keys``: welcher Kanal welchen
    Programmer-Schluessel traegt, bleibt exakt wie bisher. Verschoben wird nur,
    welchen Schluessel ein KOPF adressiert. Deshalb braucht FM-17 keine
    Show-Migration — gespeicherte ``attr#N`` treffen weiter denselben Kanal.
    """
    return _channel_index(channels)[1]


def _channel_index(channels):
    """``(positions, head_map)`` einer Kanal-Liste — EIN Durchlauf, gecached.

    ``positions`` = ``{attr: [Index jedes Vorkommens]}``, ``head_map`` = die
    Kopf-Karte aus :func:`head_channel_map`. Beides zusammen, weil jeder
    Kopf-Konsument beides braucht und der 44-Hz-Pfad sonst pro Zelle erneut
    ueber alle Kanaele laeuft (Review-Checkliste, O(Koepfe x Kanaele))."""
    ck = (id(channels), len(channels)) if id(channels) in _cached_channel_list_ids else None
    if ck is not None:
        hit = _head_map_cache.get(ck)
        if hit is not None:
            return hit
    try:
        attrs = [(getattr(c, "attribute", "") or "").lower() for c in channels]
    except Exception:
        return {}, {}
    positions: dict[str, list[int]] = {}
    for i, a in enumerate(attrs):
        positions.setdefault(a, []).append(i)
    anchors: list[int] = []
    for a in _HEAD_ANCHOR_ATTRS:
        if len(positions.get(a, ())) > len(anchors):
            anchors = positions[a]
    heads = len(anchors)
    out: dict = {}
    if heads >= 2:
        bounds = list(anchors) + [len(attrs)]
        for a, occurrences in positions.items():
            # BEWUSST nur Dimmer-Attribute. Die Segment-Regel wuerde ueber die
            # ganze Library 128 Zuordnungen verschieben, aber ein GEMESSENER
            # Fehler liegt nur bei den 27 Intensity-Faellen vor. Der Rest waere
            # Umbau auf Verdacht — mit zwei konkreten Risiken, die die
            # Gegenprobe gezeigt hat: (a) bei einigen Profilen wandern color_g/b,
            # nicht aber color_r (das ist der Anker) — Rot und Blau eines Kopfes
            # kaemen dann von verschiedenen Koepfen, also falsche Farben;
            # (b) 7 Laser-Modi bekommen eine Karte (macro/color_wheel/speed),
            # und ein verschobener Muster-/Betriebsart-Kanal ist genau die
            # Sorte Ueberraschung, die man an einem Laser nicht will.
            # Weiten (mit eigener Messung je Attributklasse) waere ein eigenes
            # Item, kein Nebeneffekt dieses Fixes.
            if a not in _DIM_INTENSITY_ATTRS:
                continue
            per_head: list[int] = []
            for k in range(heads):
                lo, hi = bounds[k], bounds[k + 1]
                inside = next((p for p in occurrences if lo <= p < hi), None)
                if inside is None:
                    per_head = []
                    break
                per_head.append(inside)
            if len(per_head) == heads:
                out[a] = per_head
    if ck is not None:
        # Auch das LEERE Ergebnis cachen: „dieses Geraet hat keine Kopf-Karte"
        # ist die haeufigste Antwort (Einzelkopf) und darf nicht pro Frame neu
        # ausgerechnet werden. Der Cache-Write steht bewusst im Erfolgspfad —
        # ein Ergebnis aus dem except-Zweig oben wird NIE gecached (Lehre FM-12).
        _head_map_cache[ck] = (positions, out)
    return positions, out


def programmer_key_for_head(channels, attribute: str, head) -> str:
    """Welchen Programmer-Schluessel adressiert „Kopf ``head``" fuer ``attribute``?

    ★ FM-17, und die EINE Stelle, an der aus einem Kopf ein Schluessel wird.
    ``head=None`` heisst **ganzes Geraet** (Basis-Schluessel, Bestandsverhalten);
    ``head=0..n-1`` meint einen echten Kopf. Diese Unterscheidung ist neu und
    noetig: vorher war „Kopf 1" und „ganzes Geraet" beides ``head=0``, was
    dieselbe Antwort gab — bei einem geteilten Master sind es aber zwei
    verschiedene Kanaele.

    Drei Faelle, in dieser Reihenfolge:

    1. Attribut steht in der :func:`head_channel_map` -> dessen Kanal fuer diesen
       Kopf (Hydrabeam 19ch: Kopf 0 -> ``intensity#1`` = CH9 „Kopf 1 Dimmer").
    2. Attribut kommt nur EINMAL vor -> geteilt, also der Basis-Schluessel. Das
       heilt einen zweiten stummen Fehler: bei **358 Modi** der Library (ein
       Master-Dimmer + mehrere Farb-/Bewegungskoepfe, z. B. ``MOVBAR4 22ch``)
       schrieb ein Kopf-Ziel bisher ``intensity#1`` — einen Schluessel, den kein
       Kanal traegt. Der Wert landete im Programmer-Dict und **nirgends** auf DMX.
       Dasselbe galt fuer die geteilte Farbe der Hydrabeam 19ch.
    3. Sonst -> unveraendert das ``head``-te Vorkommen (Bestandsverhalten).
    """
    if head is None:
        return attribute
    base = (attribute or "").split("#", 1)[0]
    a = base.lower()
    try:
        head = int(head)
    except (TypeError, ValueError):
        return attribute
    positions, hmap = _channel_index(channels)
    occurrences = positions.get(a, ())
    per_head = hmap.get(a)
    if per_head is not None and 0 <= head < len(per_head):
        occ = list(occurrences).index(per_head[head])
        return base if occ == 0 else f"{base}#{occ}"
    if len(occurrences) <= 1:
        return base
    return base if head == 0 else f"{base}#{head}"


def shared_master_channels(channels, attribute: str) -> list:
    """Kanaele dieses Attributs, die KEINEM Kopf gehoeren — die geteilten Master.

    ★ FM-17, Gegenstueck zu :func:`channels_for_head`. Wer nur den Kanal eines
    Kopfes bespielt, laesst den davorliegenden gemeinsamen Dimmer unberuehrt —
    und der steht per ``default_value`` auf 0 (Hydrabeam ``CH1``). Der Kopf ist
    dann richtig adressiert und trotzdem dunkel. Leer, wenn es fuer das Attribut
    gar keine Kopf-Karte gibt (dann ist der einzige Kanal ohnehin geteilt und
    wird auf dem normalen Weg geschrieben)."""
    a = (attribute or "").split("#", 1)[0].lower()
    positions, hmap = _channel_index(channels)
    per_head = hmap.get(a)
    if not per_head:
        return []
    owned = set(per_head)
    return [channels[i] for i in positions.get(a, ()) if i not in owned]


def channels_for_head(channels, head: int) -> dict:
    """Projiziert die Kanaele EINES Kopfes eines Multi-Head-Fixtures: liefert
    ``{basis_attr: channel}`` fuer den ``head``-ten Kopf.

    Regel: Zuerst die :func:`head_channel_map` (FM-17) — sie weiss, welcher Kanal
    welchem Kopf gehoert, auch wenn ein GETEILTER Kanal (Master-Dimmer) dasselbe
    Attribut traegt. Fehlt ein Attribut dort, gilt unveraendert: mehrfaches
    Vorkommen = pro Kopf (das ``head``-te), einmaliges Vorkommen = GETEILT und
    damit bei JEDEM Kopf dabei (gemeinsamer Master-Dimmer, Strobe, Farbrad,
    Makro …). So bekommt eine Matrix-Zelle „Kopf h" genau dessen Farbe und —
    bei Geraeten wie der Hydrabeam 56ch — dessen eigenen Dimmer/Strobe.
    ``head=0`` auf einem Single-Head-Fixture liefert schlicht alle Kanaele
    (byte-identisch zum Nicht-Kopf-Pfad).

    Laeuft ueber den gecachten Kanal-Index (:func:`_channel_index`), kostet also
    O(Attribute) statt O(Kanaele) — der Matrix-Pfad ruft diese Funktion PRO ZELLE
    PRO FRAME auf."""
    positions, hmap = _channel_index(channels)
    picked: list[tuple[int, str]] = []
    for a, occurrences in positions.items():
        per_head = hmap.get(a)
        if per_head is not None:
            # FM-17: die Karte entscheidet — geteilte Kanaele desselben
            # Attributs (Master-Dimmer) gehoeren KEINEM Kopf.
            if 0 <= head < len(per_head):
                picked.append((per_head[head], a))
        elif len(occurrences) > 1:
            # wiederholtes Attribut ohne Kopf-Karte -> das head-te Vorkommen.
            if 0 <= head < len(occurrences):
                picked.append((occurrences[head], a))
        else:
            # einmaliges Attribut -> geteilt (jeder Kopf).
            picked.append((occurrences[0], a))
    # In KANAL-Reihenfolge zurueckgeben (wie die fruehere Schleife ueber
    # ``channels``) — Aufrufer schreiben daraus DMX-Kanaele der Reihe nach.
    return {a: channels[i] for i, a in sorted(picked)}


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
    mit dem Multi-Head-DMX-Pfad (`visualizer_service._build_fixture_payload`),
    dessen `heads`-Array auf `color_r#1` reagiert.
    Hinweis: ein reiner Tilt-only-Bar OHNE zweite Farb-Bank (Mini-Spider/
    Twinscan) ist BEWUSST kein `is_spider_fixture` — dafuer ist
    `is_dual_tilt_fixture` (Bewegung/Steuerung, >=2 Tilt + kein Pan) zustaendig.
    Laser-Ausnahme: ein Geraet mit fixture_type=='laser' ist ein Punkt-Scanner,
    NIE ein Multi-Emitter-Spider — auch wenn es (wie das PARTYLASER-Builtin mit
    zwei roten Dioden auf getrennten `color_r`-Kanaelen) zufaellig >=2 Farb-Banken
    hat. Ohne dieses Gate liefert `_viz_model_for` fuer den Laser 'spider' statt
    'laser' -> falsches 3D-Modell, 2D-Spider-Symbol und sinnlose Patch-Spiegel-
    Option. Gilt genauso fuer importierte Laser mit doppelter Farb-Bank."""
    # Laser = Punkt-Scanner, nie ein Multi-Emitter-Spider (s. Docstring). Vor dem
    # Bank-Zaehlen greifen, damit auch >=2 color_r ein Laser bleibt.
    # FM-13: dito fuer 'matrix' (Pixel-Panel) — es hat rows*cols color_r-Banks,
    # ist aber KEIN Spider/par_bar: der Panel-Renderer nutzt den fixture_type
    # 'matrix' direkt (buildMatrixPanel). Ohne dieses Gate routet viz_model_for
    # das Panel faelschlich auf par_bar (>=2 Banks, keine Bewegung).
    if (getattr(fixture, "fixture_type", "") or "") in ("laser", "matrix"):
        return False
    try:
        chans = get_channels_for_patched(fixture)
        banks = sum(1 for c in chans if (getattr(c, "attribute", "") or "") == "color_r")
        return banks >= 2
    except Exception:
        return False


def viz_model_for(fixture):
    """Zentrales Render-Modell-Routing fuer Multi-Emitter-Geraete (FM-3..7).

    EINZIGE Quelle, damit 2D-Symbol (``live_view``/``mini_icons``), 3D-Modell
    (``VisualizerBridge._viz_model_for``) und die Patch-Spiegel-Option NICHT
    auseinanderdriften.

    FM-12: Ein expliziter Profil-Override (``FixtureProfile.viz_model``, im
    Fixture-Generator waehlbar) gewinnt IMMER — er darf auch Single-Head-
    Modelle ('par', 'laser', …) liefern; alle Aufrufer nutzen das Muster
    ``viz_model_for(f) or f.fixture_type`` und tragen ihn damit durch.

    Ohne Override rein aus dem Kanal-Layout:
      * kein ``is_spider_fixture`` (>=2 RGBW-Banks) -> ``None`` (Aufrufer nutzt
        den ``fixture_type``).
      * >=2 ``pan`` (Pro-Kopf-Pan)         -> ``'mover_bar'`` (FM-4: N Mini-MHs).
      * keine Bewegung (kein Pan, kein Tilt) -> ``'par_bar'`` (FM-3: N PARs).
      * sonst (Bewegung, aber kein Pro-Kopf-Pan) -> ``'spider'`` (Doppelbar).
    """
    override = viz_model_override_for(fixture)
    if override:
        return override
    if not is_spider_fixture(fixture):
        return None
    try:
        chans = get_channels_for_patched(fixture)
    except Exception:
        return "spider"
    # Gemeinsame Heuristik mit dem Generator-Vorschlag (suggest_viz_model);
    # nach bestandenem is_spider_fixture liefert sie immer ein Multi-Emitter-
    # Modell — "spider" nur als defensiver Fallback.
    return suggest_viz_model(
        getattr(fixture, "fixture_type", ""),
        [(getattr(c, "attribute", "") or "") for c in chans]) or "spider"


def tilt_head_count(fixture) -> int:
    """Anzahl separater Tilt-Motoren/Koepfe (Kanaele mit attribute == 'tilt').
    Fine-Kanaele heissen 'tilt_fine' und zaehlen NICHT mit — ein 16-bit-Single-
    Head bleibt 1, ein Doppelbar-Spider ergibt 2."""
    try:
        return sum(1 for c in get_channels_for_patched(fixture)
                   if (getattr(c, "attribute", "") or "") == "tilt")
    except Exception:
        return 0


def pan_tilt_head_count(fixture) -> int:
    """EFX-Kopfzahl eines beweglichen Geraets = Zahl der ANSTEUERBAREN Pan/Tilt-
    Koepfe = ``max(#pan, #tilt)`` Motoren (Fine-Kanaele ``pan_fine``/``tilt_fine``
    zaehlen NICHT mit). 1 = Single-Head-Mover, >=2 = Mehrkopf-Mover (MOVBAR4/
    Hydrabeam) bzw. Doppelbar-Spider (>=2 Tilt, 0 Pan).

    EINE Quelle fuer die pro-Kopf-Pan/Tilt-Welle im Render (``efx.write()`` gatet
    genau hierauf: ``head_count >= 2``) UND fuer die Pro-Kopf-Punkte der
    EFX-Vorschau (FM-16b). Immer >= 1 (nutzt denselben gecachten
    ``get_channels_for_patched``-Pfad wie ``tilt_head_count``)."""
    try:
        chans = get_channels_for_patched(fixture)
    except Exception:
        return 1
    pans = sum(1 for c in chans if (getattr(c, "attribute", "") or "") == "pan")
    tilts = sum(1 for c in chans if (getattr(c, "attribute", "") or "") == "tilt")
    return max(1, pans, tilts)


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


def open_value_of_channel(ch, fallback: int = 255) -> int:
    """Wie ``open_value_for``, aber auf einem bereits aufgeloesten Kanal.

    EINE Quelle fuer beide Wege (BUG-FBW Slice 2): „Alles Weiß" hat die Kanaele
    ohnehin schon in der Hand, ein zweiter Lookup ueber das Fixture waere nur
    eine weitere Gelegenheit zur Drift. Ein ``fallback``, den der Aufrufer
    erkennen kann (z. B. -1), heisst „das Profil sagt nichts" — genau darauf
    stuetzt sich die Shutter-Regel in ``core.all_white``.
    """
    if ch is None:
        return fallback
    for rng in (getattr(ch, "ranges", None) or ()):
        if (getattr(rng, "kind", "") or "").lower() == "open":
            return max(0, min(255, (int(rng.range_from) + int(rng.range_to)) // 2))
    hv = getattr(ch, "highlight_value", None)
    return int(hv) if hv is not None else fallback


def open_value_for(fixture, attribute: str, fallback: int = 255) -> int:
    """Sinnvoller "offener"/Highlight-Wert eines Kanals: bevorzugt eine
    ChannelRange mit ``kind == "open"`` (Mittelwert), sonst ``highlight_value``,
    sonst ``fallback``. Nutzt nur vorhandene Capability-Daten (kein Raten)."""
    return open_value_of_channel(find_channel(fixture, attribute), fallback)


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
