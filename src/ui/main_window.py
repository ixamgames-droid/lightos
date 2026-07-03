"""LightOS Hauptfenster."""
from __future__ import annotations
import os
import json
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QButtonGroup, QStackedWidget, QStatusBar,
    QMessageBox, QFileDialog, QTabWidget, QSizePolicy, QFrame,
    QMenu, QSlider, QInputDialog,
)
from PySide6.QtCore import Qt, QSize, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QIcon, QPixmap, QColor, QPainter
from src.core.app_state import get_state
from src.core.dmx.enttec_pro import find_enttec_port
from src.ui.views.patch_view import PatchView
from src.ui.views.programmer_view import ProgrammerView
from src.ui.views.playback_view import PlaybackView
from src.ui.views.curve_library_view import CurveLibraryView
from src.ui.views.output_view import OutputView
from src.ui.views.midi_view import MidiView
from src.ui.views.virtual_console_view import VirtualConsoleView
from src.ui.views.simple_desk import SimpleDeskView
from src.ui.views.efx_view import EfxView
from src.ui.views.rgb_matrix_view import RgbMatrixView
from src.ui.views.palette_view import PaletteView
from src.ui.views.function_manager_view import FunctionManagerView
from src.ui.views.show_manager_view import ShowManagerView
from src.ui.views.dmx_monitor_view import DmxMonitorView
from src.ui.views.fixture_group_view import FixtureGroupView
from src.ui.views.channel_groups_view import ChannelGroupsView
from src.ui.views.live_view import LiveView
from src.ui.weak_slots import weak_slot


# Recent files storage
def _recent_files_path() -> str:
    base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "LightOS")
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        pass
    return os.path.join(base, "recent.json")


def _load_recent_files() -> list[str]:
    path = _recent_files_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [str(x) for x in data][:10]
    except Exception:
        pass
    return []


def _save_recent_files(paths: list[str]) -> None:
    try:
        with open(_recent_files_path(), "w", encoding="utf-8") as f:
            json.dump(paths[:10], f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[main_window] save recent error: {e}")


def _add_recent_file(path: str) -> list[str]:
    recents = _load_recent_files()
    # Move to front, dedup
    recents = [p for p in recents if p != path]
    recents.insert(0, path)
    recents = recents[:10]
    _save_recent_files(recents)
    return recents


def _colored_icon(color: str, size: int = 16) -> QIcon:
    """Kleines farbiges Quadrat als Fallback-Icon."""
    px = QPixmap(size, size)
    px.fill(QColor(color))
    return QIcon(px)


class SectionButton(QPushButton):
    """
    Sektions-Toolbar-Button:
    Transparenter Hintergrund, gelbe Unterstreichung wenn aktiv.
    """
    # Kleiner Klick-Floor, damit der Button nie auf Null-Breite schrumpft
    # (nur Sicherheitsnetz fuer Touch/Maus-Trefferflaeche, siehe Review-Fix
    # unten - KEIN Text-Mindestbedarf mehr, siehe resizeEvent).
    _CLICK_FLOOR_PX = 56

    def __init__(self, text: str, icon_color: str = "#6F6F6F"):
        super().__init__(text)
        # UI-15/Review-Fix (2026-07-02): voller Titel wird fuer sizeHint/Tooltip
        # und als Elide-Quelle in resizeEvent gebraucht - der aktuell angezeigte
        # Text() darf dafuer NICHT herangezogen werden, sonst entsteht eine
        # Schrumpf-Spirale (elidierter Text -> kleinere sizeHint -> noch mehr
        # Elide, ...).
        self._full_text = text
        self.setObjectName("sectionBtn")
        self.setCheckable(True)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIcon(_colored_icon(icon_color, 14))
        self.setIconSize(QSize(14, 14))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setToolTip(text)
        self.setMinimumWidth(self._CLICK_FLOOR_PX)

    def _full_text_size_hint(self) -> QSize:
        # Nutzt Qts EIGENE sizeHint()-Berechnung (beruecksichtigt QSS-Padding,
        # Icon-Abstand, Checkable/Flat-Extras exakt so wie Qt sie tatsaechlich
        # anwendet) - dafuer den aktuell GESETZTEN Text() kurz gegen den vollen
        # Titel tauschen. Robuster als eine eigene, von QSS-Werten abgeleitete
        # Naeherungsrechnung (die bei 1440px zu 1-6px Diskrepanz gegenueber der
        # tatsaechlichen Layout-Zuteilung fuehrte -> unnoetiges Elide trotz
        # eigentlich ausreichend Platz).
        current = self.text()
        if current == self._full_text:
            return super().sizeHint()
        QPushButton.setText(self, self._full_text)
        try:
            return super().sizeHint()
        finally:
            QPushButton.setText(self, current)

    def sizeHint(self):  # noqa: N802
        # Breite aus dem VOLLEN Titel, nicht aus dem aktuell ggf. bereits
        # elidierten self.text() - sonst wuerde die sizeHint mit jedem
        # Elide-Zyklus weiter schrumpfen (Feedback-Schleife).
        return self._full_text_size_hint()

    def minimumSizeHint(self):  # noqa: N802
        # QPushButtons Basis-minimumSizeHint() haengt am aktuell GESETZTEN
        # Text() (nicht an unserem sizeHint()-Override) - QHBoxLayout kann sich
        # bei der Groessenzuteilung an minimumSizeHint() statt sizeHint()
        # orientieren, was sonst zu einem Rundungsfehler ggue. sizeHint()
        # fuehrt (bei 1440px beobachtet: Buttons zu schmal -> letztes Zeichen
        # elidiert, obwohl eigentlich ausreichend Platz vorhanden war). Fix:
        # identisch zu sizeHint().
        return self.sizeHint()

    # Review-Fix (2026-07-02, Befund 1/HIGH): die vorherige harte
    # setMinimumWidth(sizeHint) in showEvent() erzwang bei 900-1439px (Fenster
    # erlaubt setMinimumSize(900,600)) eine Summe an Mindestbreiten, die groesser
    # war als die verfuegbare Bar-Breite -> QHBoxLayout konnte die Buttons NICHT
    # mehr auf ihre Mindestbreite bringen und positionierte sie enger als deren
    # Summe -> sichtbare Ueberlappung (gemessen 1024x900: bis 47px, GM-Gruppe
    # ueberdeckte den letzten Button). Fix: KEIN harter Text-Mindestbreiten-Floor
    # mehr - stattdessen elidiert der Button seinen Text graceful auf die vom
    # Layout tatsaechlich zugewiesene Breite (nie Ueberlappung, nur "..."-Kuerzung
    # unterhalb ~1440px). Tooltip zeigt weiterhin immer den vollen Titel.
    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # "Chrome"-Breite (QSS-Padding, Icon+Abstand, Checkable/Flat-Extras) =
        # Differenz zwischen Qts eigener sizeHint() fuer den vollen Titel und
        # der reinen Textbreite - so bleibt das Elide-Budget konsistent mit
        # sizeHint()/minimumSizeHint() oben (kein zweiter, potenziell
        # abweichender Naeherungswert).
        full_text_w = self.fontMetrics().horizontalAdvance(self._full_text)
        chrome = max(self._full_text_size_hint().width() - full_text_w, 0)
        avail = self.width() - chrome
        shown = self.fontMetrics().elidedText(
            self._full_text, Qt.TextElideMode.ElideRight, max(avail, 0))
        if shown != self.text():
            self.setText(shown)


class MainWindow(QMainWindow):
    # BPM-Aenderung kann aus Fremd-Threads (Audio) kommen -> Signal marshallt in UI.
    _bpm_changed_sig = Signal(float)
    # Modus/Quelle/Lock-Aenderung des BPM-Leaders -> Badge in der Top-Bar.
    _bpm_state_sig = Signal()
    # Page-Wechsel meldet die PlaybackEngine ggf. aus dem MIDI-Thread -> Signal
    # marshallt die Label-Aktualisierung in den UI-Thread (crash.log 2026-06-14:
    # MIDI-Thread fasste Widgets direkt an -> Access Violation).
    _page_changed_sig = Signal(int)
    # Marshallt beliebige State-Event-Zustellungen aus Worker-Threads (MIDI/OSC/
    # Web/Audio) in den UI-Thread. AutoConnection => Cross-Thread-Emits werden
    # gequeued, Emits aus dem UI-Thread laufen direkt.
    _emit_marshal_sig = Signal(object)

    def __init__(self, kiosk: bool = False, touch: bool = False):
        super().__init__()
        self._state = get_state()
        # UI-Marshaller registrieren, BEVOR irgendein Worker-Thread Events feuert:
        # _emit aus Fremd-Threads ruft danach _run_in_ui (Qt-Queued) statt direkt
        # Widget-Code im Fremd-Thread (Crash-Quelle, Audit B1/C8).
        self._emit_marshal_sig.connect(self._run_in_ui)
        self._state.set_ui_marshaller(self._emit_marshal_sig.emit)
        self._state.subscribe(self._on_state_event)
        self._visualizer_window = None
        self._current_show_path: str | None = None
        self._kiosk_mode = kiosk
        self._touch_mode = touch

        self.setWindowTitle("LightOS")
        self.resize(1400, 900)
        self.setMinimumSize(900, 600)

        self._apply_theme()
        self._setup_menubar()
        self._build_ui()
        self._setup_statusbar()
        self._check_hardware()

        # Kiosk-Modus: Menubar + Statusbar ausblenden, direkt zur Virtual Console
        if kiosk:
            self.menuBar().hide()
            self.statusBar().hide()
            # Section-Bar verstecken (nur VC sichtbar lassen)
            if hasattr(self, "_section_bar"):
                self._section_bar.hide()
            if hasattr(self, "_command_line") and self._command_line:
                self._command_line.hide()
            # Wechsel zu Virtual Console Section
            try:
                vc_idx = next((i for i, b in enumerate(self._section_btns)
                              if "Virtual" in b.text()), 3)
                self._stack.setCurrentIndex(vc_idx)
            except Exception:
                pass

        # Subscribe an zentralen Sync-Event-Bus
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            sync.subscribe(SyncEvent.REFRESH_ALL, self._on_refresh_all)
            sync.subscribe(SyncEvent.SHOW_LOADED, self._on_show_loaded)
            # Validation-Banner bei relevanten Aenderungen aktualisieren
            sync.subscribe(SyncEvent.PATCH_CHANGED, lambda *_: self._refresh_validation_banner())
            sync.subscribe(SyncEvent.SHOW_LOADED, lambda *_: self._refresh_validation_banner())
            sync.subscribe(SyncEvent.REFRESH_ALL, lambda *_: self._refresh_validation_banner())
            # ISO-01: Fremdwert-Badges bei Simple-Desk-(DMX) und Programmer-Aenderung
            # sowie bei Show-Wechsel/Refresh aktualisieren.
            sync.subscribe(SyncEvent.DMX_CHANGED, lambda *_: self._refresh_foreign_badges())
            sync.subscribe(SyncEvent.PROGRAMMER_CHANGED, lambda *_: self._refresh_foreign_badges())
            sync.subscribe(SyncEvent.SHOW_LOADED, lambda *_: self._refresh_foreign_badges())
            sync.subscribe(SyncEvent.REFRESH_ALL, lambda *_: self._refresh_foreign_badges())
        except Exception as e:
            print(f"[main_window] sync subscribe error: {e}")

        # Auto-Save: alle 5 Minuten Show als auto_save.lshow speichern
        self._setup_autosave()
        # Initial: Validation-Banner einmal pruefen
        QTimer.singleShot(1000, self._refresh_validation_banner)
        # Initial: Fremdwert-Badges (ISO-01) einmal aktualisieren
        QTimer.singleShot(800, self._refresh_foreign_badges)
        # Beim Start: pruefen ob Wiederherstellung noetig
        QTimer.singleShot(500, self._check_autosave_recovery)
        # MIDI-Eingaenge automatisch verbinden (APC mini etc.) — beim Start und
        # periodisch, damit auch nachtraeglich eingestecktes Geraet erkannt wird.
        QTimer.singleShot(800, self._auto_connect_midi)
        self._midi_autoconnect_timer = QTimer(self)
        self._midi_autoconnect_timer.timeout.connect(self._auto_connect_midi)
        self._midi_autoconnect_timer.start(4000)

    # ── MIDI Auto-Connect ───────────────────────────────────────────────────────

    def _auto_connect_midi(self):
        """Öffnet automatisch alle verfügbaren MIDI-Eingänge, damit Controller
        (z.B. APC mini) ohne manuelles 'Input öffnen' in der MIDI-Ansicht
        reagieren — Voraussetzung für MIDI-Teach und Live-Feedback der VC."""
        try:
            from src.core.midi.midi_manager import get_midi_manager
            mm = get_midi_manager()
            before = set(getattr(mm, "_inputs", {}).keys())
            mm.open_all_inputs()
            new = set(getattr(mm, "_inputs", {}).keys()) - before
            if new:
                print(f"[main_window] MIDI auto-connect: {sorted(new)}")
        except Exception as e:
            print(f"[main_window] MIDI auto-connect error: {e}")

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _apply_theme(self):
        theme_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "assets", "themes", "dark.qss")
        )
        qss = ""
        if os.path.exists(theme_path):
            with open(theme_path, "r", encoding="utf-8") as f:
                qss = f.read()
        # Touch-Mode: Buttons + Slider + Items vergroessern via Override
        if getattr(self, "_touch_mode", False):
            qss += "\n/* Touch-Mode Override */\n"
            qss += (
                "QPushButton { min-height: 38px; padding: 6px 14px; font-size: 14px; }\n"
                "QSlider::handle:horizontal, QSlider::handle:vertical { "
                "width: 26px; height: 26px; }\n"
                "QListWidget::item, QTreeWidget::item, QTableWidget::item { "
                "min-height: 36px; padding: 6px; }\n"
                "QComboBox { min-height: 38px; font-size: 14px; }\n"
                "QTabBar::tab { min-height: 40px; padding: 8px 16px; font-size: 13px; }\n"
                "QSpinBox, QDoubleSpinBox, QLineEdit { min-height: 32px; font-size: 13px; }\n"
            )
        self.setStyleSheet(qss)

    # ── Menu bar ──────────────────────────────────────────────────────────────

    def _setup_menubar(self):
        mb = self.menuBar()

        # Datei
        fm = mb.addMenu("&Datei")
        a = fm.addAction("Neue Show")
        a.setShortcut(QKeySequence.StandardKey.New)
        a.triggered.connect(self._new_show)

        a = fm.addAction("Öffnen...")
        a.setShortcut(QKeySequence.StandardKey.Open)
        a.triggered.connect(self._open_show)

        a = fm.addAction("Speichern")
        a.setShortcut(QKeySequence.StandardKey.Save)
        a.triggered.connect(self._save_show)

        a = fm.addAction("Speichern unter...")
        a.triggered.connect(self._save_show_as)

        # Recent files submenu
        fm.addSeparator()
        self._recent_menu = QMenu("Zuletzt verwendet", self)
        fm.addMenu(self._recent_menu)
        self._rebuild_recent_menu()

        # XML-Workspace Import
        fm.addSeparator()
        a = fm.addAction("XML-Workspace importieren...")
        a.triggered.connect(self._import_qxw)

        # Show pruefen & reparieren
        fm.addSeparator()
        a = fm.addAction("Show prüfen && reparieren...")
        a.setShortcut("Ctrl+Shift+R")
        a.triggered.connect(self._validate_show)

        # F-10: Auto-Save-Intervall konfigurierbar
        a = fm.addAction("Auto-Save-Intervall...")
        a.triggered.connect(self._configure_autosave_interval)

        fm.addSeparator()
        fm.addAction("Beenden").triggered.connect(self.close)

        # Bearbeiten (Undo/Redo)
        em = mb.addMenu("&Bearbeiten")
        self._act_undo = em.addAction("Rückgängig")
        self._act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self._act_undo.triggered.connect(self._do_undo)
        self._act_redo = em.addAction("Wiederherstellen")
        self._act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self._act_redo.triggered.connect(self._do_redo)
        em.addSeparator()
        a = em.addAction("Verlauf löschen")
        a.triggered.connect(self._clear_undo_history)
        try:
            from src.core.undo import get_undo_stack
            self._undo_stack = get_undo_stack()
            self._undo_stack.subscribe(self._refresh_undo_labels)
            self._refresh_undo_labels()
        except Exception as e:
            print(f"[main_window] undo init: {e}")
            self._undo_stack = None

        # Ansicht
        am = mb.addMenu("&Ansicht")
        a = am.addAction("Alle Views aktualisieren")
        a.setShortcut("F5")
        a.triggered.connect(self._refresh_all_views)
        am.addAction("Musik-Fenster (Now Playing)").triggered.connect(self._open_music_window)

        # Show
        sm = mb.addMenu("&Show")
        a = sm.addAction("Cue aufnehmen")
        a.setShortcut("R")
        a.triggered.connect(self._quick_record_cue)

        # Page-Wechsel (T0.1 Multi-Page)
        a = sm.addAction("Nächste Page")
        a.setShortcut("Ctrl+PgDown")
        a.triggered.connect(self._page_next)
        a = sm.addAction("Vorherige Page")
        a.setShortcut("Ctrl+PgUp")
        a.triggered.connect(self._page_prev)

        # Programmer-Hotkeys (T0.2)
        pm = mb.addMenu("&Programmer")
        a = pm.addAction("Highlight (selektierte Fixtures voll an)")
        a.setShortcut("H")
        a.triggered.connect(self._global_highlight)
        a = pm.addAction("Lowlight (nicht-selektierte dimmen)")
        a.setShortcut("Shift+H")
        a.triggered.connect(self._global_lowlight)
        a = pm.addAction("Programmer leeren")
        a.setShortcut("Escape")
        a.triggered.connect(self._global_clear_programmer)
        pm.addSeparator()
        a = pm.addAction("Selektion kopieren")
        a.setShortcut("Ctrl+C")
        a.triggered.connect(self._global_copy_programmer)
        a = pm.addAction("Selektion einfügen")
        a.setShortcut("Ctrl+V")
        a.triggered.connect(self._global_paste_programmer)
        pm.addSeparator()
        a = pm.addAction("Snapshot aufnehmen")
        a.setShortcut("Ctrl+Shift+S")
        a.triggered.connect(self._quick_snapshot)
        pm.addSeparator()
        # Strikte Trennung Farbe/Dimmer: ist der Schalter AUS, macht eine reine Farbe
        # den Dimmer NICHT automatisch auf (Helligkeit kommt nur aus Dimmer-Snaps/
        # -Effekten/Mastern). AN = altes Verhalten "Farbe heisst sichtbar" (4a²).
        self._act_implicit = pm.addAction("Farbe macht automatisch hell")
        self._act_implicit.setCheckable(True)
        self._act_implicit.setToolTip(
            "AN: eine gesetzte Farbe ohne eigenen Dimmer wird automatisch sichtbar "
            "(Dimmer auf voll).\nAUS (Standard): strikte Trennung — Farbe setzt nur "
            "Farbe, Helligkeit kommt aus Dimmer-Snaps/-Effekten/Master.")
        self._act_implicit.setChecked(bool(getattr(self._state, "implicit_brightness", False)))
        self._act_implicit.toggled.connect(self._on_toggle_implicit_brightness)

        # Datenbank
        dbm = mb.addMenu("&Datenbank")
        dbm.addAction("Fixtures importieren (XML)...").triggered.connect(self._open_qxf_import)
        dbm.addSeparator()
        dbm.addAction("Neues Fixture-Profil...").triggered.connect(self._open_fixture_editor)

        # Ausgabe
        om = mb.addMenu("&Ausgabe")
        om.addAction("Konfigurieren...").triggered.connect(self._open_output_config)
        om.addAction("Channel-Modifier...").triggered.connect(self._open_channel_modifiers)
        om.addSeparator()
        self._act_mock = om.addAction("Mock Mode AN/AUS")
        self._act_mock.setCheckable(True)
        self._act_mock.triggered.connect(self._toggle_mock)
        om.addSeparator()
        self._act_web = om.addAction("Web-Interface (Port 5000)")
        self._act_web.setCheckable(True)
        self._act_web.triggered.connect(self._toggle_web_server)
        self._act_osc = om.addAction("OSC-Server (Port 7770)")
        self._act_osc.setCheckable(True)
        self._act_osc.triggered.connect(self._toggle_osc_server)
        self._act_os2l = om.addAction("OS2L-Server (Port 1234)")
        self._act_os2l.setCheckable(True)
        self._act_os2l.triggered.connect(self._toggle_os2l_server)
        om.addSeparator()
        om.addAction("Input-Profile verwalten...").triggered.connect(self._open_input_profile_editor)

        # Visualizer
        vm = mb.addMenu("&Visualizer")
        vm.addAction("3D Visualizer öffnen").triggered.connect(self._open_visualizer)
        vm.addAction("Visualizer schließen").triggered.connect(self._close_visualizer)

        # Command-Line (T1.1)
        cm = mb.addMenu("&Command")
        a = cm.addAction("Command-Line fokussieren")
        a.setShortcut(":")
        a.triggered.connect(self._focus_command_line)
        a2 = cm.addAction("Command-Line fokussieren (F12)")
        a2.setShortcut("F12")
        a2.triggered.connect(self._focus_command_line)

        # Hilfe
        hm = mb.addMenu("&Hilfe")
        hm.addAction("Über LightOS").triggered.connect(self._about)

    # ── UI aufbauen ───────────────────────────────────────────────────────────

    def _build_ui(self):
        """
        Layout:
          [  section toolbar  ]   <- gradient #222->#111, checkable buttons + yellow underline
          [                   ]
          [   stacked views   ]   <- Hauptinhalt
          [                   ]
        """
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sektions-Toolbar (Haupt-Navigation) ───────────────────────────────
        self._section_bar = QWidget()
        self._section_bar.setObjectName("sectionBar")
        self._section_bar.setFixedHeight(34)
        bar_layout = QHBoxLayout(self._section_bar)
        bar_layout.setContentsMargins(4, 0, 4, 0)
        bar_layout.setSpacing(0)

        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)

        # Sektions-Definitionen: (Label, Icon-Farbe, Index)
        # UI-15: "Bühnen-Layout"/"Eingabe / Ausgabe" gekuerzt ("Bühne"/"E/A") -
        # das sind bei 1440px die beiden breitesten Labels, die den Bar-Platz
        # sprengen; alle anderen bleiben unveraendert (Kuerzung nur wo noetig).
        sections = [
            ("Bühne",                "#FFD700"),
            ("Patchen",              "#0978FF"),
            ("Programmer",           "#FFD700"),
            ("Virtual Console",      "#9DFF52"),
            ("Simple Desk",          "#8F8F8F"),
            ("Playback",             "#FF6B35"),
            ("E/A",                  "#6F6F6F"),
            ("BPM",                  "#FF3CAC"),
        ]

        # Volle Bezeichnung fuer Tooltip der gekuerzten Buttons (UI-15).
        _section_full_names = {"Bühne": "Bühnen-Layout", "E/A": "Eingabe / Ausgabe"}

        self._section_btns: list[SectionButton] = []
        for i, (label, color) in enumerate(sections):
            btn = SectionButton(label, color)
            if label in _section_full_names:
                btn.setToolTip(_section_full_names[label])
            self._btn_group.addButton(btn, i)
            bar_layout.addWidget(btn)
            self._section_btns.append(btn)

        # Spacer rechts
        bar_layout.addStretch(1)

        # Grand Master Slider (rechts neben Stretch, vor BPM)
        # UI-16 (Visual-Audit 2026-07-02): GM-Label/Slider standen direkt als
        # Einzel-Items in `bar_layout`. Bei knappem Bar-Platz (viele
        # Section-Buttons + GM + TAP + Validation/Clear-Widgets) komprimiert
        # QHBoxLayout gestauchte Items nicht nur in der Breite, sondern kann sie
        # auch VOR das Ende ihres direkten Vorgaengers positionieren (Qt-
        # Startvations-Artefakt) -> Slider-Griff ueberlappte die erste Ziffer
        # ("00%"). Fix: GM-Gruppe (Label "GM" + Slider + Prozent-Label) in einen
        # EIGENEN Container mit eigenem Layout kapseln - dessen interne Geometrie
        # ist von der Bar-Starvation isoliert (der Container selbst kann als Ganzes
        # schrumpfen, aber Slider und Prozent-Label bleiben zueinander korrekt
        # positioniert, da ihr Mini-Layout nur sich selbst versorgen muss).
        gm_group = QWidget()
        gm_layout = QHBoxLayout(gm_group)
        gm_layout.setContentsMargins(0, 0, 0, 0)
        gm_layout.setSpacing(4)
        lbl_gm = QLabel("GM")
        lbl_gm.setStyleSheet("color: #cccccc; padding: 0 4px; font-weight: bold;")
        gm_layout.addWidget(lbl_gm)
        self._slider_gm = QSlider(Qt.Orientation.Horizontal)
        self._slider_gm.setRange(0, 100)
        self._slider_gm.setValue(100)
        self._slider_gm.setFixedWidth(110)
        self._slider_gm.setToolTip("Grand Master (0–100 %)")
        self._slider_gm.valueChanged.connect(self._on_grand_master_changed)
        gm_layout.addWidget(self._slider_gm)
        self._lbl_gm_val = QLabel("100%")
        self._lbl_gm_val.setStyleSheet("color: #aaaaaa; padding: 0 4px;")
        # Fixe "min-width:36px" im Stylesheet war zu schmal fuer "100%" in
        # Fettschrift-Nachbarschaft -> harte Mindestbreite aus fontMetrics
        # ("100%") + Puffer, als setMinimumWidth (Layout-Floor, siehe SectionButton).
        gm_val_min_w = self._lbl_gm_val.fontMetrics().horizontalAdvance("100%") + 8
        self._lbl_gm_val.setMinimumWidth(gm_val_min_w)
        gm_layout.addWidget(self._lbl_gm_val)
        gm_group.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        # Container selbst braucht ebenfalls einen Layout-Floor (sonst wandert das
        # Starvations-Problem nur eine Ebene nach aussen, siehe SectionButton).
        gm_group.setMinimumWidth(gm_group.sizeHint().width())
        bar_layout.addWidget(gm_group)

        # Tap-Tempo + BPM (klickbares Label)
        self._btn_tap = QPushButton("TAP")
        self._btn_tap.setFixedHeight(26)
        self._btn_tap.setFixedWidth(48)
        self._btn_tap.setToolTip("Tap-Tempo (4x klicken)")
        self._btn_tap.clicked.connect(self._on_tap_tempo)
        bar_layout.addWidget(self._btn_tap)

        # Validation-Banner (zeigt Anzahl Issues, klickbar)
        self._lbl_validation = QLabel("")
        self._lbl_validation.setFixedHeight(22)
        self._lbl_validation.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lbl_validation.setToolTip("Klick: Validierung anzeigen")
        self._lbl_validation.mousePressEvent = lambda _ev: self._show_validation_dialog()
        self._lbl_validation.hide()  # Versteckt wenn keine Issues
        bar_layout.addWidget(self._lbl_validation)

        # UIC-01: Quick-Snap-Button aus der Section-Bar entfernt (redundant zu
        # Menue "Programmer -> Snapshot aufnehmen" / Strg+Shift+S, SnapshotsView
        # und VC-Sidebar). _quick_snapshot() bleibt fuer Menue/Shortcut erhalten.

        # ISO-01: Anzeige aktiver Fremdwerte (Programmer / Simple Desk). Nur
        # sichtbar wenn etwas aktiv ist; Klick oeffnet das Clear-Menue (ISO-02).
        self._lbl_foreign = QLabel("")
        self._lbl_foreign.setFixedHeight(22)
        self._lbl_foreign.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lbl_foreign.setToolTip("Aktive Programmer-/Simple-Desk-Werte — Klick: leeren")
        self._lbl_foreign.setStyleSheet(
            "QLabel { background:#3a2a00; color:#ffb000; font-weight:bold;"
            " border:1px solid #6b5000; border-radius:3px; padding:0 8px; }"
        )
        self._lbl_foreign.mousePressEvent = lambda _ev: self._open_clear_menu()
        self._lbl_foreign.hide()
        bar_layout.addWidget(self._lbl_foreign)

        # ISO-02: Zentrales Clear-Menue (immer erreichbar: Programmer / Simple Desk
        # / Alle Nicht-VC-Werte). Loescht nur aktive Werte, nie gespeicherte Daten.
        self._btn_clear_nonvc = QPushButton("✖ Clear ▾")
        self._btn_clear_nonvc.setFixedHeight(22)
        self._btn_clear_nonvc.setToolTip("Aktive Werte zurücksetzen (Programmer / Simple Desk / Alle Nicht-VC)")
        self._btn_clear_nonvc.setStyleSheet(
            "QPushButton { background:#21262d; color:#f85149; border:1px solid #30363d;"
            " border-radius:3px; padding:0 8px; }"
            "QPushButton:hover { background:#30363d; }"
        )
        self._btn_clear_nonvc.clicked.connect(self._open_clear_menu)
        bar_layout.addWidget(self._btn_clear_nonvc)

        # Page-Anzeige + Pfeile (T0.1 Multi-Page)
        page_prev = QPushButton("<")
        page_prev.setFixedSize(22, 22)
        page_prev.setToolTip("Vorherige Page (Ctrl+Page Up)")
        page_prev.clicked.connect(self._page_prev)
        bar_layout.addWidget(page_prev)

        self._lbl_page = QLabel("Page 1")
        self._lbl_page.setStyleSheet("color:#ffd700; font-weight:bold; padding:0 6px; min-width:60px;")
        self._lbl_page.setToolTip("Klick für Page-Auswahl")
        self._lbl_page.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lbl_page.mousePressEvent = lambda _ev: self._select_page_dialog()
        bar_layout.addWidget(self._lbl_page)

        page_next = QPushButton(">")
        page_next.setFixedSize(22, 22)
        page_next.setToolTip("Nächste Page (Ctrl+Page Down)")
        page_next.clicked.connect(self._page_next)
        bar_layout.addWidget(page_next)

        # Subscribe an PlaybackEngine fuer Page-Wechsel via MIDI etc. Die Engine
        # ruft die Subscriber ggf. aus dem MIDI-Thread auf -> ueber das Signal in
        # den UI-Thread marshallen (sonst cross-thread Widget-Zugriff -> Crash).
        self._page_changed_sig.connect(self._on_page_changed)
        pe = self._state.playback_engine
        if pe:
            pe.subscribe_page(lambda idx: self._page_changed_sig.emit(int(idx)))

        self._lbl_bpm = QLabel("BPM: --")
        self._lbl_bpm.setStyleSheet("color: #888888; padding: 0 8px;")
        self._lbl_bpm.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lbl_bpm.setToolTip("BPM einstellen (klicken)")
        self._lbl_bpm.mousePressEvent = lambda _ev: self._set_bpm_manually()
        bar_layout.addWidget(self._lbl_bpm)

        # AUTO/MANUAL/Lock-Badge — zeigt, welcher Modus/welche Quelle den Leader
        # treibt. Klick togglet AUTO/MANUAL.
        self._lbl_bpm_mode = QLabel("AUTO")
        self._lbl_bpm_mode.setFixedHeight(22)
        self._lbl_bpm_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lbl_bpm_mode.setToolTip("BPM-Modus (Klick: AUTO/MANUAL umschalten)")
        self._lbl_bpm_mode.mousePressEvent = lambda _ev: self._toggle_bpm_mode()
        bar_layout.addWidget(self._lbl_bpm_mode)

        # BPM-Pulse Indikator — groesserer runder Beat-Punkt (deutlich sichtbar)
        self._BPM_DOT_IDLE = ("background:#1c1c1c; border:1px solid #333;"
                              " border-radius:13px; margin:2px 4px;")
        self._bpm_indicator = QLabel(" ")
        self._bpm_indicator.setFixedSize(26, 26)
        self._bpm_indicator.setToolTip("Beat-Indikator (Takt 1 gelb, sonst grün)")
        self._bpm_indicator.setStyleSheet(self._BPM_DOT_IDLE)
        bar_layout.addWidget(self._bpm_indicator)
        self._bpm_indicator_timer = QTimer(self)
        self._bpm_indicator_timer.setInterval(110)
        self._bpm_indicator_timer.setSingleShot(True)
        self._bpm_indicator_timer.timeout.connect(self._on_bpm_indicator_idle)

        # BPM-Manager Subscribe
        try:
            from src.core.engine.bpm_manager import get_bpm_manager
            self._bpm_mgr = get_bpm_manager()
            self._bpm_mgr.subscribe_beat(self._on_beat)
            # BPM-Aenderung (Tap/APC/Audio) -> Label sofort aktualisieren.
            self._bpm_changed_sig.connect(self._update_bpm_label)
            self._bpm_mgr.subscribe_bpm_change(lambda b: self._bpm_changed_sig.emit(b))
            # Modus/Quelle/Lock -> Badge marshallen (Audio-Thread fasst kein Widget an).
            self._bpm_state_sig.connect(self._update_bpm_mode_badge)
            self._bpm_mgr.subscribe_state_change(lambda: self._bpm_state_sig.emit())
        except Exception as e:
            print(f"[main_window] bpm subscribe error: {e}")
            self._bpm_mgr = None

        # AUTO standardmaessig an: Einstellungen laden/anwenden und (sofern nicht
        # via LIGHTOS_NO_AUDIO_AUTOSTART unterdrueckt) den Audio-Capture starten.
        try:
            from src.core.audio import bpm_settings
            bpm_settings.boot()
        except Exception as e:
            print(f"[main_window] bpm boot error: {e}")
        self._update_bpm_mode_badge()

        btn_stop = QPushButton("STOP ALL")
        btn_stop.setObjectName("blackoutBtn")
        btn_stop.setFixedHeight(26)
        # Keine feste Breite: der Button passt sich an seinen Text an, sonst
        # wird „STOP ALL" bei großer Schrift/Skalierung beidseitig abgeschnitten.
        btn_stop.setMinimumWidth(78)
        btn_stop.clicked.connect(self._stop_all)
        bar_layout.addWidget(btn_stop)

        btn_blackout = QPushButton("BLACKOUT")
        btn_blackout.setObjectName("blackoutBtn")
        btn_blackout.setCheckable(True)
        btn_blackout.setFixedHeight(26)
        # Keine feste Breite (s. STOP ALL): „BLACKOUT" sonst rechts abgeschnitten.
        btn_blackout.setMinimumWidth(88)
        btn_blackout.clicked.connect(self._toggle_blackout)
        self._btn_blackout = btn_blackout
        bar_layout.addWidget(btn_blackout)

        root.addWidget(self._section_bar)

        # ── Stacked Widget ─────────────────────────────────────────────────────
        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        # ── Command-Line (T1.1, MA-/Avolites-Style) ───────────────────────────
        try:
            from src.ui.widgets.command_line import CommandLine
            self._command_line = CommandLine()
            root.addWidget(self._command_line)
        except Exception as e:
            print(f"[main_window] CommandLine init error: {e}")
            self._command_line = None

        # Sektion 0: Live View (2D Top-Down)
        try:
            self._live_view = LiveView()
        except Exception as e:
            print(f"[main_window] LiveView init error: {e}")
            self._live_view = QWidget()
        self._stack.addWidget(self._live_view)
        # Sektion 1: Patchen (Patch | Gruppen)
        self._stack.addWidget(self._build_section_fixtures())
        # Sektion 2: Programmer (Programmer | Funktionen | EFX | RGB Matrix | Paletten | Snapshots)
        self._stack.addWidget(self._build_section_programmer())
        # Sektion 3: Virtual Console
        self._vc_view = VirtualConsoleView()
        self._stack.addWidget(self._vc_view)
        # Sektion 4: Simple Desk + Channel Groups
        sd_tabs = _SubTabs()
        self._simple_desk = SimpleDeskView()
        try:
            self._channel_groups_view = ChannelGroupsView()
        except Exception as e:
            print(f"[main_window] ChannelGroupsView init error: {e}")
            self._channel_groups_view = QWidget()
        sd_tabs.addTab(self._simple_desk, "Simple Desk")
        sd_tabs.addTab(self._channel_groups_view, "Submaster/Kanal-Gruppen")
        self._stack.addWidget(sd_tabs)
        # Sektion 5: Playback
        self._stack.addWidget(self._build_section_playback())
        # Sektion 6: Eingabe / Ausgabe
        self._stack.addWidget(self._build_section_io())
        # Sektion 7: BPM (Manager | Generator)
        bpm_tabs = _SubTabs()
        try:
            from src.ui.views.bpm_manager_view import BpmManagerView
            self._bpm_manager_view = BpmManagerView()
        except Exception as e:
            print(f"[main_window] BpmManagerView init error: {e}")
            self._bpm_manager_view = QWidget()
        bpm_tabs.addTab(self._bpm_manager_view, "Manager")
        try:
            from src.ui.views.bpm_generator_view import BpmGeneratorView
            self._bpm_generator_view = BpmGeneratorView()
        except Exception as e:
            print(f"[main_window] BpmGeneratorView init error: {e}")
            self._bpm_generator_view = QWidget()
        bpm_tabs.addTab(self._bpm_generator_view, "Generator")
        self._stack.addWidget(bpm_tabs)

        # Verbindung Buttons <-> Stack
        self._btn_group.idClicked.connect(self._stack.setCurrentIndex)

        # Startseite: Live View
        self._section_btns[0].setChecked(True)
        self._stack.setCurrentIndex(0)

        # Keyboard-Shortcuts fuer Sektionswechsel (Ctrl+1..6)
        for i, btn in enumerate(self._section_btns):
            act = QAction(f"Sektion {i+1}", self)
            act.setShortcut(f"Ctrl+{i+1}")
            act.triggered.connect(weak_slot(self._switch_section, i))
            self.addAction(act)

        # Globale Shortcuts
        act_go = QAction("GO", self)
        act_go.setShortcut("Space")
        act_go.triggered.connect(self._global_go)
        self.addAction(act_go)

        act_back = QAction("BACK", self)
        act_back.setShortcut("Shift+Space")
        act_back.triggered.connect(self._global_back)
        self.addAction(act_back)

        act_clear = QAction("Clear Programmer", self)
        act_clear.setShortcut("Escape")
        act_clear.triggered.connect(weak_slot(self._state.clear_programmer))
        self.addAction(act_clear)

    def _switch_section(self, idx: int):
        self._section_btns[idx].setChecked(True)
        self._stack.setCurrentIndex(idx)

    # ── Sektions-Seiten ───────────────────────────────────────────────────────

    def _build_section_fixtures(self) -> QWidget:
        """Sektion 1 (Patchen): Patch + Gruppen.

        EFX / RGB Matrix / Funktionen sind nach P-01 in den Programmer
        umgezogen (gehoeren logisch zum Programmieren, nicht zum Patchen).
        """
        tabs = _SubTabs()
        self._patch_view = PatchView()
        try:
            self._fixture_group_view = FixtureGroupView()
        except Exception as e:
            print(f"[main_window] FixtureGroupView init error: {e}")
            self._fixture_group_view = QWidget()
        tabs.addTab(self._patch_view,             "Patch")
        tabs.addTab(self._fixture_group_view,     "Fixture-Gruppen")
        return tabs

    def _build_section_programmer(self) -> QWidget:
        """Sektion 2 (Programmer): EIN Programmer + Snapshots-Schnellzugriff.

        Vereinheitlichung (REVISION/R4, siehe docs/PROGRAMMER_REBUILD.md):
        Funktionen / EFX / RGB Matrix / Paletten sind keine eigenen Sub-Tabs mehr,
        sondern Kategorien im Programmer (`programmer_view._make_mitte`) und arbeiten
        auf der gemeinsamen Auswahl (`AppState.selected_fids`). Die rechte Bibliothek
        verwaltet Snaps + Funktionen. Der Snapshots-Tab bleibt als Schnellzugriff.
        """
        tabs = _SubTabs()
        self._programmer_view = ProgrammerView()
        tabs.addTab(self._programmer_view, "Attribute")
        try:
            from src.ui.views.snapshots_view import SnapshotsView
            self._snapshots_view = SnapshotsView()
            tabs.addTab(self._snapshots_view, "Snapshots")
        except Exception as e:
            print(f"[main_window] SnapshotsView init error: {e}")
        try:
            from src.ui.views.preset_browser_view import PresetBrowserView
            self._preset_browser_view = PresetBrowserView()
            tabs.addTab(self._preset_browser_view, "Preset-Browser")
        except Exception as e:
            print(f"[main_window] PresetBrowserView init error: {e}")
        return tabs

    def _build_section_playback(self) -> QWidget:
        """Sektion 4: Playback + Show Manager."""
        tabs = _SubTabs()
        self._playback_view = PlaybackView()
        self._show_manager_view = ShowManagerView()
        tabs.addTab(self._playback_view,      "Playback")
        tabs.addTab(self._show_manager_view,  "Show Manager")
        self._curve_library_view = CurveLibraryView()
        tabs.addTab(self._curve_library_view, "Kurven")
        return tabs

    def _build_section_io(self) -> QWidget:
        """Sektion 5: Output-Monitor + DMX-Monitor + MIDI + Audio Input."""
        tabs = _SubTabs()
        self._output_view = OutputView()
        try:
            self._dmx_monitor_view = DmxMonitorView()
        except Exception as e:
            print(f"[main_window] DmxMonitorView init error: {e}")
            self._dmx_monitor_view = QWidget()
        self._midi_view = MidiView()
        try:
            from src.ui.views.audio_input_view import AudioInputView
            self._audio_input_view = AudioInputView()
        except Exception as e:
            print(f"[main_window] AudioInputView init error: {e}")
            self._audio_input_view = QWidget()
        try:
            from src.ui.views.music_view import MusicView
            self._music_view = MusicView()
        except Exception as e:
            print(f"[main_window] MusicView init error: {e}")
            self._music_view = QWidget()
        # Auto-Lichtshow an den Musik-Player koppeln (startet beim Play die in
        # state.music_autoshow konfigurierten Funktionen). Idempotent.
        try:
            from src.core.audio.music_show import get_music_director
            get_music_director().attach()
        except Exception as e:
            print(f"[main_window] MusicShowDirector attach error: {e}")
        tabs.addTab(self._output_view,      "Output")
        tabs.addTab(self._dmx_monitor_view, "DMX Monitor")
        tabs.addTab(self._midi_view,        "MIDI")
        tabs.addTab(self._audio_input_view, "Audio Input")
        tabs.addTab(self._music_view,       "Musik")
        return tabs

    # ── Statusbar ─────────────────────────────────────────────────────────────

    def _setup_statusbar(self):
        sb = self.statusBar()
        self._lbl_enttec   = QLabel("Enttec: --")
        self._lbl_web      = QLabel("Web: aus")
        self._lbl_fixtures = QLabel("0 Geräte")
        self._lbl_mock     = QLabel("")
        self._lbl_universe = QLabel("Universe 1")

        for w in [self._lbl_enttec, _sep(), self._lbl_web,
                  _sep(), self._lbl_fixtures, _sep(), self._lbl_mock]:
            sb.addWidget(w)
        sb.addPermanentWidget(self._lbl_universe)

    def _check_hardware(self):
        port = find_enttec_port()
        if port:
            self._lbl_enttec.setText(f"Enttec: {port} OK")
            self._lbl_enttec.setStyleSheet("color: #9DFF52;")
        else:
            self._lbl_enttec.setText("Enttec: nicht gefunden")
            self._lbl_enttec.setStyleSheet("color: #ff4444;")

    # ── Transport / Playback ──────────────────────────────────────────────────

    def _global_go(self):
        pe = self._state.playback_engine
        if pe:
            for ex in pe.executors:
                if ex.stack:
                    ex.stack.go()
                    return
        if self._state.cue_stacks:
            self._state.cue_stacks[0].go()

    def _global_back(self):
        if self._state.cue_stacks:
            self._state.cue_stacks[0].back()

    def _stop_all(self):
        pe = self._state.playback_engine
        if pe:
            for ex in pe.executors:
                if ex.stack:
                    ex.stack.stop()

    # ── Undo/Redo ─────────────────────────────────────────────────────────────

    def _do_undo(self):
        if self._undo_stack:
            ok = self._undo_stack.undo()
            if ok:
                self.statusBar().showMessage("Rückgängig", 1500)

    def _do_redo(self):
        if self._undo_stack:
            ok = self._undo_stack.redo()
            if ok:
                self.statusBar().showMessage("Wiederhergestellt", 1500)

    def _clear_undo_history(self):
        if self._undo_stack:
            self._undo_stack.clear()
            self.statusBar().showMessage("Rückgängig-Verlauf geleert", 1500)

    def _refresh_undo_labels(self):
        if not getattr(self, "_undo_stack", None):
            return
        u = self._undo_stack.undo_label()
        r = self._undo_stack.redo_label()
        self._act_undo.setText(f"Rückgängig: {u}" if u else "Rückgängig")
        self._act_undo.setEnabled(self._undo_stack.can_undo())
        self._act_redo.setText(f"Wiederherstellen: {r}" if r else "Wiederherstellen")
        self._act_redo.setEnabled(self._undo_stack.can_redo())

    # ── Grand Master / BPM ────────────────────────────────────────────────────

    def _on_grand_master_changed(self, val: int):
        gm = val / 100.0
        try:
            self._state.output_manager.set_grand_master(gm)
        except Exception as e:
            print(f"[main_window] grand_master error: {e}")
        self._lbl_gm_val.setText(f"{val}%")

    def _on_tap_tempo(self):
        if not self._bpm_mgr:
            return
        bpm = self._bpm_mgr.tap()
        if bpm > 0:
            self._lbl_bpm.setText(f"BPM: {bpm:.1f}")
            self._lbl_bpm.setStyleSheet("color: #FFD700; padding: 0 8px;")

    def _on_beat(self, idx: int):
        """Wird vom BPM-Manager im Background-Thread aufgerufen → in UI dispatchen."""
        try:
            QTimer.singleShot(0, lambda i=idx: self._flash_bpm_indicator(i))
        except Exception:
            pass

    def _update_bpm_label(self, bpm: float):
        """Aktualisiert die BPM-Anzeige sofort bei jeder Tempo-Aenderung (UI-Thread)."""
        try:
            if bpm and bpm > 0:
                self._lbl_bpm.setText(f"BPM: {bpm:.1f}")
                self._lbl_bpm.setStyleSheet("color: #FFD700; padding: 0 8px;")
            else:
                self._lbl_bpm.setText("BPM: --")
                self._lbl_bpm.setStyleSheet("color: #888888; padding: 0 8px;")
        except Exception:
            pass

    def _on_bpm_indicator_idle(self):
        self._bpm_indicator.setStyleSheet(self._BPM_DOT_IDLE)

    def _flash_bpm_indicator(self, idx: int = 0):
        # Akzent auf Beat 1 (alle 4) — Index kommt direkt vom Beat-Callback,
        # kein Re-Read des privaten Zaehlers (war off-by-one).
        col = "#FFD700" if (idx % 4 == 0) else "#9DFF52"
        self._bpm_indicator.setStyleSheet(
            f"background:{col}; border:1px solid {col}; border-radius:13px; margin:2px 4px;")
        self._bpm_indicator_timer.start()
        # BPM-Label synchron halten — auch wenn das Tempo extern (APC-TAP / Audio)
        # geaendert wurde und nicht ueber den Tap-Button im Hauptfenster.
        if self._bpm_mgr and self._bpm_mgr.bpm > 0:
            self._lbl_bpm.setText(f"BPM: {self._bpm_mgr.bpm:.1f}")
            self._lbl_bpm.setStyleSheet("color: #FFD700; padding: 0 8px;")

    def _set_bpm_manually(self):
        if not self._bpm_mgr:
            return
        current = self._bpm_mgr.bpm if self._bpm_mgr.bpm > 0 else 120.0
        val, ok = QInputDialog.getDouble(
            self, "BPM einstellen", "BPM (0 = aus, 20–999):",
            current, 0.0, 999.0, 1
        )
        if ok:
            if val > 0:
                self._bpm_mgr.set_manual_bpm(val)
            else:
                self._bpm_mgr.reset()
            if val > 0:
                self._lbl_bpm.setText(f"BPM: {val:.1f}")
                self._lbl_bpm.setStyleSheet("color: #FFD700; padding: 0 8px;")
            else:
                self._lbl_bpm.setText("BPM: --")
                self._lbl_bpm.setStyleSheet("color: #888888; padding: 0 8px;")

    def _toggle_bpm_mode(self):
        if not self._bpm_mgr:
            return
        try:
            from src.core.engine.bpm_manager import BpmMode
            new = BpmMode.MANUAL if self._bpm_mgr.mode == BpmMode.AUTO else BpmMode.AUTO
            self._bpm_mgr.set_mode(new)
        except Exception as e:
            print(f"[main_window] toggle bpm mode error: {e}")

    def _update_bpm_mode_badge(self):
        """Aktualisiert das AUTO/MANUAL/Lock-Badge in der Top-Bar (UI-Thread)."""
        if not getattr(self, "_lbl_bpm_mode", None) or not self._bpm_mgr:
            return
        try:
            from src.core.engine.bpm_manager import BpmMode
            mgr = self._bpm_mgr
            if mgr.is_locked:
                txt, bg, fg = "🔒 LOCK", "#3a2a00", "#ffb000"
            elif mgr.mode == BpmMode.AUTO:
                txt, bg, fg = "AUTO", "#10331a", "#9DFF52"
            else:
                txt, bg, fg = "MAN", "#33210f", "#f0883e"
            self._lbl_bpm_mode.setText(txt)
            self._lbl_bpm_mode.setStyleSheet(
                f"QLabel {{ background:{bg}; color:{fg}; font-weight:bold;"
                f" border-radius:3px; padding:0 6px; }}")
        except Exception:
            pass

    def _toggle_blackout(self, checked: bool):
        self._state.output_manager.set_blackout(checked)
        if checked:
            self._btn_blackout.setStyleSheet(
                "background:#cc0000; color:#ffffff; font-weight:bold;"
                "border:2px solid #ff0000;"
            )
        else:
            self._btn_blackout.setStyleSheet("")

    def _quick_record_cue(self):
        stacks = self._state.cue_stacks
        if not stacks:
            QMessageBox.information(self, "Cue aufnehmen",
                                    "Zuerst eine Cueliste im Playback-Tab anlegen.")
            return
        stack = stacks[0]
        existing = [c.number for c in stack.cues]
        n = (max(existing) + 1.0) if existing else 1.0
        self._state.record_cue(stack, n, f"Cue {n:.0f}")

    # ── Multi-Page-Playback (T0.1) ─────────────────────────────────────────────

    def _page_prev(self):
        pe = self._state.playback_engine
        if pe:
            pe.set_page(pe.current_page - 1)

    def _page_next(self):
        pe = self._state.playback_engine
        if pe:
            pe.set_page(pe.current_page + 1)

    def _select_page_dialog(self):
        pe = self._state.playback_engine
        if not pe:
            return
        items = [f"Page {i+1}" for i in range(pe.MAX_PAGES)]
        item, ok = QInputDialog.getItem(
            self, "Page wählen", "Page:", items, pe.current_page, False
        )
        if ok and item:
            pe.set_page(items.index(item))

    def _on_page_changed(self, idx: int):
        """Engine meldet Page-Wechsel."""
        if hasattr(self, "_lbl_page"):
            self._lbl_page.setText(f"Page {idx + 1}")

    # ── Programmer-Hotkeys (T0.2) ─────────────────────────────────────────────

    def _programmer_view(self):
        """Holt den ProgrammerView falls instanziert."""
        return getattr(self, "_programmer_view_ref", None)

    def _global_highlight(self):
        pv = getattr(self, "_programmer_view", None)
        if pv and hasattr(pv, "_highlight"):
            pv._highlight()
        else:
            # Fallback: alle gepatchten Fixtures voll an
            for f in self._state.get_patched_fixtures():
                self._state.set_programmer_value(f.fid, "intensity", 255)
                self._state.set_programmer_value(f.fid, "color_r", 255)
                self._state.set_programmer_value(f.fid, "color_g", 255)
                self._state.set_programmer_value(f.fid, "color_b", 255)

    def _global_lowlight(self):
        pv = getattr(self, "_programmer_view", None)
        if pv and hasattr(pv, "_lowlight"):
            pv._lowlight()
        else:
            for f in self._state.get_patched_fixtures():
                self._state.set_programmer_value(f.fid, "intensity", 76)

    def _global_clear_programmer(self):
        self._state.clear_programmer()

    def _global_copy_programmer(self):
        pv = getattr(self, "_programmer_view", None)
        if pv and hasattr(pv, "_copy_to_clipboard"):
            pv._copy_to_clipboard()

    def _global_paste_programmer(self):
        pv = getattr(self, "_programmer_view", None)
        if pv and hasattr(pv, "_paste_from_clipboard"):
            pv._paste_from_clipboard()

    def _on_toggle_implicit_brightness(self, checked: bool):
        """Schaltet die implizite Grundhelligkeit (4a²) um. AUS = strikte Trennung
        Farbe/Dimmer: eine reine Farbe macht den Dimmer NICHT automatisch auf. Der
        Renderer liest das Flag live pro Frame, die Aenderung greift also sofort."""
        self._state.implicit_brightness = bool(checked)
        msg = ("Farbe macht automatisch hell: AN"
               if checked else
               "Strikte Trennung Farbe/Dimmer: AN (Farbe macht NICHT automatisch hell)")
        try:
            self.statusBar().showMessage(msg, 4000)
        except Exception:
            pass

    def _sync_render_toggles(self):
        """Spiegelt zustands-abhaengige Menue-Schalter nach Laden/Neue-Show wider
        (ohne erneut das toggled-Signal auszuloesen)."""
        act = getattr(self, "_act_implicit", None)
        if act is not None:
            act.blockSignals(True)
            act.setChecked(bool(getattr(self._state, "implicit_brightness", False)))
            act.blockSignals(False)

    # ── Validation-Banner (Section-Bar) ───────────────────────────────────────

    def _refresh_validation_banner(self):
        """Laeuft Validation (ohne Fix) und aktualisiert Banner-Text."""
        try:
            from src.core.sync import validate_and_repair
            issues = validate_and_repair(self._state, fix=False)
            errors = [i for i in issues if i.severity == "error"]
            warns = [i for i in issues if i.severity == "warn"]
            count = len(errors) + len(warns)
            if count == 0:
                self._lbl_validation.hide()
                return
            if errors:
                color = "#ff4444"
                icon = "!"
            else:
                color = "#ffaa00"
                icon = "*"
            self._lbl_validation.setText(f" {icon} {count} Issues ")
            self._lbl_validation.setStyleSheet(
                f"background:{color}; color:#000; font-weight:bold;"
                f" border-radius:3px; padding:2px 8px;"
            )
            self._lbl_validation.show()
            self._lbl_validation._cached_issues = issues
        except Exception as e:
            print(f"[main_window] validation refresh error: {e}")
            self._lbl_validation.hide()

    def _show_validation_dialog(self):
        """Oeffnet Validation-Dialog auf Klick aufs Banner."""
        try:
            from src.ui.widgets.validation_dialog import ValidationDialog
            issues = getattr(self._lbl_validation, "_cached_issues", None)
            if issues is None:
                from src.core.sync import validate_and_repair
                issues = validate_and_repair(self._state, fix=False)
            ValidationDialog(issues, self).exec()
            # Nach Dialog ggf. neu pruefen (User koennte Auto-Repair gestartet haben)
            self._refresh_validation_banner()
        except Exception as e:
            print(f"[main_window] validation dialog error: {e}")

    # ── Quick-Snapshot (Section-Bar Button) ───────────────────────────────────

    def _quick_snapshot(self):
        """Speichert aktuellen Programmer in den naechsten leeren Snapshot-Slot."""
        try:
            sv = getattr(self, "_snapshots_view", None)
            if sv is None:
                QMessageBox.information(self, "Snapshot", "Snapshots-View nicht initialisiert.")
                return
            # Naechsten leeren Slot finden
            free_idx = None
            for i in range(len(sv._snapshots)):
                if sv._snapshots[i].is_empty():
                    free_idx = i
                    break
            if free_idx is None:
                QMessageBox.warning(self, "Snapshot",
                    "Alle 48 Slots belegt. Bitte einen leeren oder den Snapshots-Tab öffnen.")
                return
            # Programmer pruefen
            if not self._state.programmer:
                QMessageBox.information(self, "Snapshot",
                    "Programmer ist leer - nichts zu speichern.")
                return
            # Name abfragen + capture
            name, ok = QInputDialog.getText(
                self, "Snapshot speichern",
                f"Name für Snapshot Slot {free_idx + 1}:",
                text=f"Snap {free_idx + 1}"
            )
            if not ok or not name.strip():
                return
            # Kanal-Auswahl wie im Snapshots-Tab / in der Snap-Bibliothek: NICHT
            # den ganzen Programmer (inkl. eines evtl. mit-scharfen Dimmers) blind
            # speichern, sondern fragen, WELCHE Attribut-Gruppen (Farbe / Dimmer /
            # …) in den Snapshot wandern. So kommt ein Dimmer nur mit, wenn man ihn
            # bewusst angehakt laesst (loest Davids "Color speichert Dimmer mit").
            import copy
            from src.ui.views.snap_file_panel import ChannelSelectDialog
            from PySide6.QtWidgets import QDialog
            vals = copy.deepcopy(self._state.programmer)
            scope = (self._state.active_scope_fids()
                     if hasattr(self._state, "active_scope_fids") else None)
            dlg = ChannelSelectDialog(vals, self, scope_fids=scope)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            vals = dlg.filter_programmer(vals)
            if not vals:
                QMessageBox.information(self, "Snapshot",
                    "Keine Kanäle ausgewählt - Snapshot nicht gespeichert.")
                return
            sv._snapshots[free_idx].name = name.strip()
            sv._snapshots[free_idx].values = vals
            sv._buttons[free_idx].refresh()
            sv._save_to_disk()
            self.statusBar().showMessage(
                f"Snapshot '{name}' in Slot {free_idx + 1} gespeichert", 3000
            )
        except Exception as e:
            print(f"[main_window] quick_snapshot error: {e}")
            QMessageBox.warning(self, "Snapshot Fehler", str(e))

    # ── Mock / Visualizer ─────────────────────────────────────────────────────

    def _toggle_mock(self, checked: bool):
        self._state.mock_mode = checked
        if checked:
            self._lbl_mock.setText("MOCK")
            self._lbl_mock.setStyleSheet("color: #FFD700; font-weight: bold;")
            self._open_visualizer()
        else:
            self._lbl_mock.setText("")
            self._lbl_mock.setStyleSheet("")

    def _open_music_window(self):
        """Öffnet die Musik-View als kleines eigenes Fenster (Now Playing)."""
        try:
            from PySide6.QtWidgets import QMainWindow
            from src.ui.views.music_view import MusicView
            win = getattr(self, "_music_window", None)
            if win is not None:
                try:
                    win.close()
                    win.deleteLater()
                except Exception:
                    pass
            self._music_window = QMainWindow(self)
            self._music_window.setWindowTitle("LightOS — Musik")
            self._music_window.setCentralWidget(MusicView())
            self._music_window.resize(520, 560)
            self._music_window.show()
        except Exception as e:
            print(f"[main_window] music window error: {e}")

    def _open_visualizer(self):
        # IMMER neu instanziieren -> HTML/JS wird frisch geladen (kein Stale-Cache).
        # Altes Fenster sauber schliessen falls noch offen.
        try:
            if self._visualizer_window is not None:
                try:
                    # close() kann seit VIZ-10 ueber den "Buehne speichern?"-Dialog
                    # abgebrochen werden (event.ignore() -> False): dann das bestehende
                    # Fenster BEHALTEN (kein deleteLater — sonst Leak + Datenverlust
                    # trotz "Abbrechen") und nur nach vorn holen.
                    if not self._visualizer_window.close():
                        self._visualizer_window.raise_()
                        self._visualizer_window.activateWindow()
                        return
                    self._visualizer_window.deleteLater()
                except Exception as e:
                    print(f"[MainWindow] _open_visualizer cleanup error: {e}")
                self._visualizer_window = None
        except Exception:
            self._visualizer_window = None
        try:
            from src.ui.visualizer.visualizer_window import VisualizerWindow
            self._visualizer_window = VisualizerWindow(self)
            self._visualizer_window.show()
            self._visualizer_window.raise_()
            self._visualizer_window.activateWindow()
        except Exception as e:
            self._visualizer_window = None
            print(f"[MainWindow] Visualizer start error: {e}")
            QMessageBox.warning(
                self,
                "Visualizer nicht verfügbar",
                "Der 3D-Visualizer konnte nicht gestartet werden.\n\n"
                "Bitte prüfe, ob PySide6 + PySide6-Addons korrekt installiert sind."
            )

    def _close_visualizer(self):
        if self._visualizer_window:
            self._visualizer_window.close()

    # ── Output-Konfiguration ──────────────────────────────────────────────────

    def _open_output_config(self):
        from src.ui.widgets.output_config import OutputConfigDialog
        dlg = OutputConfigDialog(self)
        dlg.exec()
        self._check_hardware()

    def _open_channel_modifiers(self):
        try:
            from src.ui.widgets.channel_modifier_dialog import ChannelModifierDialog
            ChannelModifierDialog(self).exec()
        except Exception as e:
            print(f"[main_window] channel_modifier open error: {e}")

    # ── Show-Datei ────────────────────────────────────────────────────────────

    def _new_show(self):
        reply = QMessageBox.question(self, "Neue Show",
            "Aktuelle Show komplett verwerfen und leer neu beginnen?\n\n"
            "Gepatchte Fixtures, Virtual Console, Funktionen, Paletten und "
            "Bibliothek werden geleert.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            from src.core.show.show_file import reset_show
            reset_show()
            self._current_show_path = None
            self.setWindowTitle("LightOS")
            self._sync_render_toggles()

    def _open_show(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Show öffnen", "", "LightOS Show (*.lshow);;Alle Dateien (*)"
        )
        if not path:
            return
        self._open_show_path(path)

    def _open_show_path(self, path: str):
        from src.core.show.show_file import load_show
        ok, msg = load_show(path)
        if ok:
            self._current_show_path = path
            self.setWindowTitle(f"LightOS  -  {msg}")
            self.statusBar().showMessage(msg, 4000)
            _add_recent_file(path)
            self._rebuild_recent_menu()
            self._sync_render_toggles()
        else:
            QMessageBox.warning(self, "Fehler", msg)

    def _rebuild_recent_menu(self):
        if not hasattr(self, "_recent_menu") or self._recent_menu is None:
            return
        self._recent_menu.clear()
        recents = _load_recent_files()
        if not recents:
            empty = self._recent_menu.addAction("(leer)")
            empty.setEnabled(False)
            return
        for path in recents:
            short = os.path.basename(path) or path
            act = self._recent_menu.addAction(short)
            act.setToolTip(path)
            act.triggered.connect(weak_slot(self._open_show_path, path))
        self._recent_menu.addSeparator()
        clear_act = self._recent_menu.addAction("Liste leeren")
        clear_act.triggered.connect(self._clear_recent_files)

    def _clear_recent_files(self):
        _save_recent_files([])
        self._rebuild_recent_menu()

    def _import_qxw(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "XML-Workspace importieren", "", "XML Workspace (*.qxw);;Alle Dateien (*)"
        )
        if not path:
            return
        try:
            from src.core.show.qxw_importer import import_qxw
            result = import_qxw(path)
        except Exception as e:
            QMessageBox.warning(self, "Import-Fehler", str(e))
            return
        if not result.get("ok"):
            QMessageBox.warning(self, "Import-Fehler", result.get("message", "Unbekannter Fehler"))
            return
        QMessageBox.information(
            self, "QLC+ Import",
            result.get("message", "") +
            "\n\nHinweis: Funktionen / VC-Widgets werden geparst, "
            "aber das vollständige Mapping in LightOS-Strukturen "
            "ist nicht automatisch (Profil-IDs unterscheiden sich)."
        )

    def _save_show(self):
        if not self._current_show_path:
            self._save_show_as()
            return
        self._do_save(self._current_show_path)

    def _save_show_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Show speichern", "", "LightOS Show (*.lshow)"
        )
        if path:
            if not path.endswith(".lshow"):
                path += ".lshow"
            self._current_show_path = path
            self._do_save(path)

    def _do_save(self, path: str):
        from src.core.show.show_file import save_show
        try:
            # VC-Layout (Buttons/Fader) aus dem aktuellen Canvas uebernehmen
            try:
                self._state._vc_layout = self._vc_view.to_dict()
            except Exception as e:
                print(f"[main_window] collect vc layout error: {e}")
            # Snapshots (pro Show) aus der View uebernehmen
            try:
                sv = getattr(self, "_snapshots_view", None)
                if sv is not None:
                    self._state._snapshots_data = sv.to_dict()
            except Exception as e:
                print(f"[main_window] collect snapshots error: {e}")
            # Kanal-Gruppen (pro Show, SDK-02) aus der View uebernehmen
            try:
                cg = getattr(self, "_channel_groups_view", None)
                if cg is not None and hasattr(cg, "to_dict"):
                    self._state._channel_groups_data = cg.to_dict()
            except Exception as e:
                print(f"[main_window] collect channel groups error: {e}")
            # T1.6 Layout-Persistenz: Layout dazupacken
            layout = None
            try:
                from src.core.layout_state import collect_layout
                layout = collect_layout(self)
            except Exception as e:
                print(f"[main_window] collect_layout error: {e}")
            save_show(path, layout=layout)
            self.setWindowTitle(f"LightOS  -  {path}")
            self.statusBar().showMessage(f"Gespeichert: {path}", 3000)
            _add_recent_file(path)
            self._rebuild_recent_menu()
        except Exception as e:
            QMessageBox.warning(self, "Speicherfehler", str(e))

    # ── Web / OSC ─────────────────────────────────────────────────────────────

    def _toggle_web_server(self, checked: bool):
        if checked:
            try:
                from src.web.app import start_server
                start_server(5000)
                self._lbl_web.setText("Web: :5000 OK")
                self._lbl_web.setStyleSheet("color: #9DFF52;")
                QMessageBox.information(self, "Web-Interface",
                    "Web-Interface läuft auf http://localhost:5000")
            except Exception as e:
                self._act_web.setChecked(False)
                QMessageBox.warning(self, "Web-Interface Fehler", str(e))
        else:
            try:
                from src.web.app import stop_server
                stop_server()
            except Exception:
                pass
            self._lbl_web.setText("Web: aus")
            self._lbl_web.setStyleSheet("")

    def _toggle_osc_server(self, checked: bool):
        if checked:
            try:
                from src.core.osc.osc_server import get_osc_server
                get_osc_server().start()
                self.statusBar().showMessage("OSC-Server: UDP :7770", 4000)
            except Exception as e:
                self._act_osc.setChecked(False)
                QMessageBox.warning(self, "OSC-Server Fehler", str(e))
        else:
            try:
                from src.core.osc.osc_server import get_osc_server
                get_osc_server().stop()
            except Exception:
                pass

    def _toggle_os2l_server(self, checked: bool):
        if checked:
            try:
                from src.core.audio.os2l import get_os2l_server
                get_os2l_server().start()
                self.statusBar().showMessage("OS2L-Server: TCP :1234", 4000)
            except Exception as e:
                self._act_os2l.setChecked(False)
                QMessageBox.warning(self, "OS2L-Server Fehler", str(e))
        else:
            try:
                from src.core.audio.os2l import get_os2l_server
                get_os2l_server().stop()
            except Exception:
                pass

    # ── QXF Import ────────────────────────────────────────────────────────────

    def _open_qxf_import(self):
        from src.ui.widgets.qxf_import_dialog import QxfImportDialog
        QxfImportDialog(self).exec()

    def _open_fixture_editor(self):
        try:
            from src.ui.widgets.fixture_editor import FixtureEditorDialog
            dlg = FixtureEditorDialog(self)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, "Fixture Editor", str(e))

    # ── Command-Line (T1.1) ──────────────────────────────────────────────────

    def _focus_command_line(self):
        cl = getattr(self, "_command_line", None)
        if cl is not None:
            try:
                cl.focus_input()
            except Exception as e:
                print(f"[main_window] focus_command_line error: {e}")

    # ── About ─────────────────────────────────────────────────────────────────

    def _about(self):
        QMessageBox.about(
            self, "Über LightOS",
            "<b>LightOS v1.0</b><br>"
            "Professionelle DMX-Lichtsteuerung<br><br>"
            "Windows x64 &amp; ARM64<br>"
            "Enttec Pro USB &middot; Art-Net 4 &middot; MIDI<br><br>"
            "UI: QLC+ v5 Design System"
        )

    # ── State-Events ─────────────────────────────────────────────────────────

    def _run_in_ui(self, fn):
        """Slot im UI-Thread: fuehrt die vom AppState-Marshaller uebergebene
        Zustellung aus. Wird via _emit_marshal_sig (Qt-Queued) aus Worker-Threads
        aufgerufen, sodass Widget-Code garantiert im UI-Thread laeuft."""
        try:
            fn()
        except Exception as exc:
            print(f"[MainWindow] marshalled emit error: {exc}")

    def _on_state_event(self, event: str, _data):
        if event == "patch_changed":
            count = len(self._state.get_patched_fixtures())
            self._lbl_fixtures.setText(f"{count} Gerät(e)")
        elif event == "programmer_changed":
            self._refresh_foreign_badges()

    # ── ISO-01/02: aktive Fremdwerte anzeigen + zentral leeren ─────────────────

    def _refresh_foreign_badges(self):
        """Aktualisiert die Anzeige aktiver Programmer-/Simple-Desk-Werte (ISO-01)."""
        if not hasattr(self, "_lbl_foreign"):
            return
        try:
            p = self._state.programmer_active()
            s = self._state.simple_desk_active()
        except Exception:
            p, s = 0, 0
        parts = []
        if p:
            parts.append(f"Programmer {p}")
        if s:
            parts.append(f"Simple Desk {s}")
        if parts:
            self._lbl_foreign.setText("● " + " · ".join(parts))
            self._lbl_foreign.show()
        else:
            self._lbl_foreign.hide()

    def _open_clear_menu(self, *_):
        """ISO-02: Menue zum Zuruecksetzen aktiver Werte. Loescht NUR aktive
        Programmer-/Simple-Desk-Werte — keine Funktionen/Effekte/Shows/Patches."""
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        p = 0
        s = 0
        try:
            p = self._state.programmer_active()
            s = self._state.simple_desk_active()
        except Exception:
            pass
        a_prog = m.addAction(f"Programmer leeren ({p})")
        a_prog.setEnabled(p > 0)
        a_prog.triggered.connect(lambda: self._do_clear("programmer"))
        a_sd = m.addAction(f"Simple Desk leeren ({s})")
        a_sd.setEnabled(s > 0)
        a_sd.triggered.connect(lambda: self._do_clear("simple_desk"))
        m.addSeparator()
        a_all = m.addAction(f"Alle Nicht-VC-Werte leeren ({p + s})")
        a_all.setEnabled((p + s) > 0)
        a_all.triggered.connect(lambda: self._do_clear("all"))
        anchor = self._btn_clear_nonvc
        m.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _do_clear(self, what: str):
        try:
            if what == "programmer":
                self._state.clear_programmer()
            elif what == "simple_desk":
                self._state.clear_simple_desk()
            else:
                self._state.clear_all_non_vc()
        except Exception as e:
            print(f"[main_window] clear '{what}' error: {e}")
        self._refresh_foreign_badges()

    def _on_refresh_all(self, _ev, _data):
        """Globaler REFRESH_ALL Handler - re-checked Hardware + Status."""
        try:
            self._check_hardware()
            count = len(self._state.get_patched_fixtures())
            self._lbl_fixtures.setText(f"{count} Gerät(e)")
        except Exception as e:
            print(f"[main_window] refresh_all error: {e}")

    def _on_show_loaded(self, _ev, data):
        """Wenn Show geladen wurde und Issues gefunden wurden, zeige Dialog."""
        try:
            issues = (data or {}).get("issues", []) if isinstance(data, dict) else []
            # Nur Dialog wenn wirklich was zu berichten ist
            relevant = [i for i in issues if getattr(i, "severity", "") in ('warn', 'error')
                        or getattr(i, "auto_fixed", False)]
            if relevant:
                from src.ui.widgets.validation_dialog import ValidationDialog
                ValidationDialog(issues, self).exec()
        except Exception as e:
            print(f"[main_window] show_loaded handler error: {e}")
        # T1.6 Layout aus Show anwenden
        try:
            layout = getattr(self._state, "_last_loaded_layout", None)
            if layout:
                from src.core.layout_state import apply_layout
                apply_layout(self, layout)
        except Exception as e:
            print(f"[main_window] apply_layout error: {e}")
        # VC-Layout (Buttons/Fader) in den Canvas laden. WICHTIG (VCL-04): auch ein
        # LEERES Layout-Dict muss durch from_dict() (raeumt intern via _clear() den
        # alten Canvas) — sonst ueberleben die VC-Widgets der VORIGEN Show ein
        # "Neue Show" bzw. das Laden einer Show ohne VC-Widgets. Nur ein fehlendes/
        # kaputtes _vc_layout (kein dict) laesst den Canvas unangetastet.
        try:
            vc = getattr(self._state, "_vc_layout", None)
            if isinstance(vc, dict):
                self._vc_view.from_dict(vc)
        except Exception as e:
            print(f"[main_window] vc layout restore error: {e}")
        # Snapshots (pro Show) in die View laden
        try:
            sv = getattr(self, "_snapshots_view", None)
            if sv is not None:
                sv.load_data(getattr(self._state, "_snapshots_data", []) or [])
        except Exception as e:
            print(f"[main_window] snapshots restore error: {e}")
        # Kanal-Gruppen (pro Show, SDK-02) in die View laden
        try:
            cg = getattr(self, "_channel_groups_view", None)
            if cg is not None and hasattr(cg, "load_data"):
                cg.load_data(getattr(self._state, "_channel_groups_data", []) or [])
        except Exception as e:
            print(f"[main_window] channel groups restore error: {e}")

    def _open_input_profile_editor(self):
        """T1.4 Input-Profile-Editor (MIDI/OSC/Keyboard)."""
        try:
            from src.ui.widgets.input_profile_editor import InputProfileEditor
            InputProfileEditor(self).exec()
        except Exception as e:
            QMessageBox.warning(self, "Input-Profile", str(e))

    # ── Validation / Refresh ─────────────────────────────────────────────────

    def _validate_show(self):
        """Menue 'Show pruefen & reparieren...' - laeuft Validator + zeigt Dialog."""
        try:
            from src.core.sync import validate_and_repair
            from src.ui.widgets.validation_dialog import ValidationDialog
            issues = validate_and_repair(self._state, fix=True)
            dlg = ValidationDialog(issues, self)
            dlg.exec()
            # Trigger Refresh-All danach
            try:
                self._state.sync.refresh_all()
            except Exception:
                pass
        except Exception as e:
            QMessageBox.warning(self, "Validierung", f"Fehler: {e}")

    def _refresh_all_views(self):
        """Menue 'Alle Views aktualisieren' (F5)."""
        try:
            self._state.sync.refresh_all()
        except Exception as e:
            print(f"[main_window] refresh_all_views error: {e}")
        # Legacy-Pfad fuer aeltere Subscriber
        try:
            self._state._emit("patch_changed")
        except Exception:
            pass

    # ── Auto-Save ────────────────────────────────────────────────────────────

    def _autosave_path(self) -> str:
        base = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")), "LightOS"
        )
        try:
            os.makedirs(base, exist_ok=True)
        except Exception:
            pass
        return os.path.join(base, "auto_save.lshow")

    def _autosave_minutes(self) -> int:
        """F-10: konfiguriertes Auto-Save-Intervall in Minuten (1–60, Default 5).
        Persistiert in ui_prefs.json."""
        try:
            from src.ui.views.programmer_view import _load_prefs
            val = int(_load_prefs().get("autosave_minutes", 5))
        except Exception:
            val = 5
        return max(1, min(60, val))

    def _setup_autosave(self):
        try:
            mins = self._autosave_minutes()
            self._autosave_timer = QTimer(self)
            self._autosave_timer.setInterval(mins * 60 * 1000)
            self._autosave_timer.timeout.connect(self._do_autosave)
            self._autosave_timer.start()
            # P4: Dirty-Flag — Auto-Save schreibt nur noch, wenn sich seit dem
            # letzten Lauf tatsaechlich etwas geaendert hat (sonst alle 5 min
            # ein unnoetiger Disk-Write). Gespeist aus den zentralen
            # SyncEvents inkl. neuem LIVE_VIEW_CHANGED (Fixture verschoben,
            # Zoom/Grid geaendert).
            self._autosave_dirty = True   # erster Lauf sichert immer
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            for ev in (SyncEvent.PATCH_CHANGED, SyncEvent.PROGRAMMER_CHANGED,
                       SyncEvent.FUNCTION_CHANGED, SyncEvent.GROUP_CHANGED,
                       SyncEvent.CUE_STACK_CHANGED, SyncEvent.PALETTE_CHANGED,
                       SyncEvent.OUTPUT_CONFIG_CHANGED,
                       SyncEvent.LIVE_VIEW_CHANGED):
                sync.subscribe(ev, self._mark_autosave_dirty)
            print(f"[autosave] aktiv ({mins} min, dirty-basiert) -> {self._autosave_path()}")
        except Exception as e:
            print(f"[autosave] setup error: {e}")

    def _configure_autosave_interval(self):
        """F-10: Auto-Save-Intervall (1–60 min) per Dialog setzen + sofort anwenden."""
        cur = self._autosave_minutes()
        mins, ok = QInputDialog.getInt(
            self, "Auto-Save-Intervall",
            "Show automatisch sichern alle (Minuten):",
            cur, 1, 60, 1
        )
        if not ok:
            return
        try:
            from src.ui.views.programmer_view import _save_prefs
            _save_prefs({"autosave_minutes": int(mins)})
        except Exception as e:
            print(f"[autosave] save interval error: {e}")
        # Live anwenden, ohne Neustart
        if getattr(self, "_autosave_timer", None) is not None:
            self._autosave_timer.setInterval(int(mins) * 60 * 1000)
        self.statusBar().showMessage(f"Auto-Save-Intervall: {mins} min", 3000)

    def _mark_autosave_dirty(self, *_args):
        self._autosave_dirty = True

    def _do_autosave(self):
        if not getattr(self, "_autosave_dirty", True):
            return  # nichts geaendert seit dem letzten Auto-Save
        try:
            from src.core.show.show_file import save_show
            path = self._autosave_path()
            save_show(path)
            self._autosave_dirty = False
            self.statusBar().showMessage(f"Auto-Save: {path}", 2500)
        except Exception as e:
            print(f"[autosave] save error: {e}")

    def _check_autosave_recovery(self):
        """Wenn auto_save existiert und neuer als andere Show ist - Recovery anbieten."""
        try:
            auto = self._autosave_path()
            if not os.path.exists(auto):
                return
            auto_mtime = os.path.getmtime(auto)
            # Vergleiche mit der letzten geoeffneten / gespeicherten Show
            recents = _load_recent_files()
            for r in recents:
                if os.path.exists(r) and os.path.getmtime(r) >= auto_mtime:
                    return
            # Frage nach Wiederherstellung
            reply = QMessageBox.question(
                self, "Auto-Save Wiederherstellung",
                "Eine Auto-Save Datei existiert (neuer als die zuletzt gespeicherte Show).\n"
                "Wiederherstellen?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._open_show_path(auto)
        except Exception as e:
            print(f"[autosave] recovery check error: {e}")

    # ── Close ─────────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        # Visualizer ZUERST schliessen: sein "Buehne speichern?"-Dialog (VIZ-10) kann
        # abbrechen (close() -> False) — dann muss der App-Exit stoppen, BEVOR
        # Output/Playback/MIDI heruntergefahren werden.
        if self._visualizer_window:
            try:
                if not self._visualizer_window.close():
                    event.ignore()
                    return
            except Exception:
                pass
        # Warnung wenn Show ungespeicherte Aenderungen hat
        if self._has_unsaved_changes():
            reply = QMessageBox.question(
                self, "Show speichern?",
                "Es gibt möglicherweise ungespeicherte Änderungen "
                "(Cuelisten, VC-Layout, Snapshots).\n\n"
                "Vor dem Beenden speichern?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save
            )
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.StandardButton.Save:
                self._save_show()

        self._state.output_manager.stop()
        if self._state.playback_engine:
            self._state.playback_engine.stop()
        from src.core.midi.midi_manager import get_midi_manager
        get_midi_manager().close_all()
        try:
            if getattr(self._state, "midi_mapper", None):
                self._state.midi_mapper.close()
        except Exception:
            pass
        super().closeEvent(event)

    def _has_unsaved_changes(self) -> bool:
        """Heuristik: Show hat Cuelisten oder Funktionen aber wurde nie gespeichert."""
        try:
            # Nie gespeichert + es gibt Inhalt?
            if self._current_show_path is None:
                has_content = (
                    len(self._state.cue_stacks) > 0
                    or len(self._state.function_manager.all()) > 0
                    or bool(self._state.programmer)
                )
                return has_content
            return False  # Bei gespeicherter Show wuerde ein "dirty"-Flag noetig sein
        except Exception:
            return False


# ── Hilfklassen ───────────────────────────────────────────────────────────────

class _SubTabs(QTabWidget):
    """Innere Sub-Tab-Leiste im QLC+ v5 Stil (gelber Unterstrich)."""
    def __init__(self):
        super().__init__()
        self.setTabPosition(QTabWidget.TabPosition.North)
        self.setDocumentMode(True)


def _placeholder(text: str) -> QWidget:
    w = QWidget()
    layout = QVBoxLayout(w)
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet("color: #555555; font-size: 15px;")
    layout.addWidget(lbl)
    return w


def _sep() -> QLabel:
    s = QLabel("|")
    s.setStyleSheet("color: #444444; padding: 0 4px;")
    return s
