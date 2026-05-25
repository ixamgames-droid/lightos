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
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QAction, QKeySequence, QIcon, QPixmap, QColor, QPainter
from src.core.app_state import get_state
from src.core.dmx.enttec_pro import find_enttec_port
from src.ui.views.patch_view import PatchView
from src.ui.views.programmer_view import ProgrammerView
from src.ui.views.playback_view import PlaybackView
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
    def __init__(self, text: str, icon_color: str = "#6F6F6F"):
        super().__init__(text)
        self.setObjectName("sectionBtn")
        self.setCheckable(True)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIcon(_colored_icon(icon_color, 14))
        self.setIconSize(QSize(14, 14))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._state = get_state()
        self._state.subscribe(self._on_state_event)
        self._visualizer_window = None
        self._current_show_path: str | None = None

        self.setWindowTitle("LightOS")
        self.resize(1400, 900)
        self.setMinimumSize(900, 600)

        self._apply_theme()
        self._setup_menubar()
        self._build_ui()
        self._setup_statusbar()
        self._check_hardware()

        # Subscribe an zentralen Sync-Event-Bus
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            sync.subscribe(SyncEvent.REFRESH_ALL, self._on_refresh_all)
            sync.subscribe(SyncEvent.SHOW_LOADED, self._on_show_loaded)
        except Exception as e:
            print(f"[main_window] sync subscribe error: {e}")

        # Auto-Save: alle 5 Minuten Show als auto_save.lshow speichern
        self._setup_autosave()
        # Beim Start: pruefen ob Wiederherstellung noetig
        QTimer.singleShot(500, self._check_autosave_recovery)

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _apply_theme(self):
        theme_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "assets", "themes", "dark.qss")
        )
        if os.path.exists(theme_path):
            with open(theme_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    # ── Menu bar ──────────────────────────────────────────────────────────────

    def _setup_menubar(self):
        mb = self.menuBar()

        # Datei
        fm = mb.addMenu("&Datei")
        a = fm.addAction("Neue Show")
        a.setShortcut(QKeySequence.StandardKey.New)
        a.triggered.connect(self._new_show)

        a = fm.addAction("Oeffnen...")
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
        a = fm.addAction("Show pruefen && reparieren...")
        a.setShortcut("Ctrl+Shift+R")
        a.triggered.connect(self._validate_show)

        fm.addSeparator()
        fm.addAction("Beenden").triggered.connect(self.close)

        # Bearbeiten (Undo/Redo)
        em = mb.addMenu("&Bearbeiten")
        self._act_undo = em.addAction("Rueckgaengig")
        self._act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self._act_undo.triggered.connect(self._do_undo)
        self._act_redo = em.addAction("Wiederherstellen")
        self._act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self._act_redo.triggered.connect(self._do_redo)
        em.addSeparator()
        a = em.addAction("Verlauf loeschen")
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

        # Show
        sm = mb.addMenu("&Show")
        a = sm.addAction("Cue aufnehmen")
        a.setShortcut("R")
        a.triggered.connect(self._quick_record_cue)

        # Page-Wechsel (T0.1 Multi-Page)
        a = sm.addAction("Naechste Page")
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
        a = pm.addAction("Selektion einfuegen")
        a.setShortcut("Ctrl+V")
        a.triggered.connect(self._global_paste_programmer)

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
        vm.addAction("3D Visualizer oeffnen").triggered.connect(self._open_visualizer)
        vm.addAction("Visualizer schliessen").triggered.connect(self._close_visualizer)

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
        hm.addAction("Ueber LightOS").triggered.connect(self._about)

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
        sections = [
            ("Live View",            "#FFD700"),
            ("Geraete & Funktionen", "#0978FF"),
            ("Programmer",           "#FFD700"),
            ("Virtual Console",      "#9DFF52"),
            ("Simple Desk",          "#8F8F8F"),
            ("Playback",             "#FF6B35"),
            ("Eingabe / Ausgabe",    "#6F6F6F"),
        ]

        self._section_btns: list[SectionButton] = []
        for i, (label, color) in enumerate(sections):
            btn = SectionButton(label, color)
            self._btn_group.addButton(btn, i)
            bar_layout.addWidget(btn)
            self._section_btns.append(btn)

        # Spacer rechts
        bar_layout.addStretch(1)

        # Grand Master Slider (rechts neben Stretch, vor BPM)
        lbl_gm = QLabel("GM")
        lbl_gm.setStyleSheet("color: #cccccc; padding: 0 4px; font-weight: bold;")
        bar_layout.addWidget(lbl_gm)
        self._slider_gm = QSlider(Qt.Orientation.Horizontal)
        self._slider_gm.setRange(0, 100)
        self._slider_gm.setValue(100)
        self._slider_gm.setFixedWidth(110)
        self._slider_gm.setToolTip("Grand Master (0–100 %)")
        self._slider_gm.valueChanged.connect(self._on_grand_master_changed)
        bar_layout.addWidget(self._slider_gm)
        self._lbl_gm_val = QLabel("100%")
        self._lbl_gm_val.setStyleSheet("color: #aaaaaa; padding: 0 4px; min-width:36px;")
        bar_layout.addWidget(self._lbl_gm_val)

        # Tap-Tempo + BPM (klickbares Label)
        self._btn_tap = QPushButton("TAP")
        self._btn_tap.setFixedHeight(26)
        self._btn_tap.setFixedWidth(48)
        self._btn_tap.setToolTip("Tap-Tempo (4x klicken)")
        self._btn_tap.clicked.connect(self._on_tap_tempo)
        bar_layout.addWidget(self._btn_tap)

        # Page-Anzeige + Pfeile (T0.1 Multi-Page)
        page_prev = QPushButton("<")
        page_prev.setFixedSize(22, 22)
        page_prev.setToolTip("Vorherige Page (Ctrl+Page Up)")
        page_prev.clicked.connect(self._page_prev)
        bar_layout.addWidget(page_prev)

        self._lbl_page = QLabel("Page 1")
        self._lbl_page.setStyleSheet("color:#ffd700; font-weight:bold; padding:0 6px; min-width:60px;")
        self._lbl_page.setToolTip("Klick fuer Page-Auswahl")
        self._lbl_page.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lbl_page.mousePressEvent = lambda _ev: self._select_page_dialog()
        bar_layout.addWidget(self._lbl_page)

        page_next = QPushButton(">")
        page_next.setFixedSize(22, 22)
        page_next.setToolTip("Naechste Page (Ctrl+Page Down)")
        page_next.clicked.connect(self._page_next)
        bar_layout.addWidget(page_next)

        # Subscribe an PlaybackEngine fuer Page-Wechsel via MIDI etc.
        pe = self._state.playback_engine
        if pe:
            pe.subscribe_page(self._on_page_changed)

        self._lbl_bpm = QLabel("BPM: --")
        self._lbl_bpm.setStyleSheet("color: #888888; padding: 0 8px;")
        self._lbl_bpm.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lbl_bpm.setToolTip("BPM einstellen (klicken)")
        self._lbl_bpm.mousePressEvent = lambda _ev: self._set_bpm_manually()
        bar_layout.addWidget(self._lbl_bpm)

        # BPM-Pulse Indikator
        self._bpm_indicator = QLabel(" ")
        self._bpm_indicator.setFixedSize(12, 18)
        self._bpm_indicator.setStyleSheet("background:#222222; border-radius:3px; margin:4px 4px;")
        bar_layout.addWidget(self._bpm_indicator)
        self._bpm_indicator_timer = QTimer(self)
        self._bpm_indicator_timer.setInterval(80)
        self._bpm_indicator_timer.setSingleShot(True)
        self._bpm_indicator_timer.timeout.connect(
            lambda: self._bpm_indicator.setStyleSheet(
                "background:#222222; border-radius:3px; margin:4px 4px;"))

        # BPM-Manager Subscribe
        try:
            from src.core.engine.bpm_manager import get_bpm_manager
            self._bpm_mgr = get_bpm_manager()
            self._bpm_mgr.subscribe_beat(self._on_beat)
        except Exception as e:
            print(f"[main_window] bpm subscribe error: {e}")
            self._bpm_mgr = None

        btn_stop = QPushButton("STOP ALL")
        btn_stop.setObjectName("blackoutBtn")
        btn_stop.setFixedHeight(26)
        btn_stop.setFixedWidth(80)
        btn_stop.clicked.connect(self._stop_all)
        bar_layout.addWidget(btn_stop)

        btn_blackout = QPushButton("BLACKOUT")
        btn_blackout.setObjectName("blackoutBtn")
        btn_blackout.setCheckable(True)
        btn_blackout.setFixedHeight(26)
        btn_blackout.setFixedWidth(90)
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
        # Sektion 1: Geraete & Funktionen (Patch | EFX | RGB Matrix)
        self._stack.addWidget(self._build_section_fixtures())
        # Sektion 2: Programmer (Programmer | Paletten)
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
        sd_tabs.addTab(self._channel_groups_view, "Channel Groups")
        self._stack.addWidget(sd_tabs)
        # Sektion 5: Playback
        self._stack.addWidget(self._build_section_playback())
        # Sektion 6: Eingabe / Ausgabe
        self._stack.addWidget(self._build_section_io())

        # Verbindung Buttons <-> Stack
        self._btn_group.idClicked.connect(self._stack.setCurrentIndex)

        # Startseite: Live View
        self._section_btns[0].setChecked(True)
        self._stack.setCurrentIndex(0)

        # Keyboard-Shortcuts fuer Sektionswechsel (Ctrl+1..6)
        for i, btn in enumerate(self._section_btns):
            act = QAction(f"Sektion {i+1}", self)
            act.setShortcut(f"Ctrl+{i+1}")
            act.triggered.connect(lambda _, idx=i: self._switch_section(idx))
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
        act_clear.triggered.connect(lambda: self._state.clear_programmer())
        self.addAction(act_clear)

    def _switch_section(self, idx: int):
        self._section_btns[idx].setChecked(True)
        self._stack.setCurrentIndex(idx)

    # ── Sektions-Seiten ───────────────────────────────────────────────────────

    def _build_section_fixtures(self) -> QWidget:
        """Sektion 0: Patch, EFX, RGB Matrix, Funktionen, Gruppen."""
        tabs = _SubTabs()
        self._patch_view = PatchView()
        self._efx_view = EfxView()
        self._rgb_matrix_view = RgbMatrixView()
        self._function_manager_view = FunctionManagerView()
        try:
            self._fixture_group_view = FixtureGroupView()
        except Exception as e:
            print(f"[main_window] FixtureGroupView init error: {e}")
            self._fixture_group_view = QWidget()
        tabs.addTab(self._patch_view,             "Patch")
        tabs.addTab(self._efx_view,               "EFX")
        tabs.addTab(self._rgb_matrix_view,        "RGB Matrix")
        tabs.addTab(self._function_manager_view,  "Funktionen")
        tabs.addTab(self._fixture_group_view,     "Gruppen")
        return tabs

    def _build_section_programmer(self) -> QWidget:
        """Sektion 1: Programmer + Paletten + Snapshots."""
        tabs = _SubTabs()
        self._programmer_view = ProgrammerView()
        self._palette_view = PaletteView()
        tabs.addTab(self._programmer_view, "Programmer")
        tabs.addTab(self._palette_view,    "Paletten")
        try:
            from src.ui.views.snapshots_view import SnapshotsView
            self._snapshots_view = SnapshotsView()
            tabs.addTab(self._snapshots_view, "Snapshots")
        except Exception as e:
            print(f"[main_window] SnapshotsView init error: {e}")
        return tabs

    def _build_section_playback(self) -> QWidget:
        """Sektion 4: Playback + Show Manager."""
        tabs = _SubTabs()
        self._playback_view = PlaybackView()
        self._show_manager_view = ShowManagerView()
        tabs.addTab(self._playback_view,      "Playback")
        tabs.addTab(self._show_manager_view,  "Show Manager")
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
        tabs.addTab(self._output_view,      "Output")
        tabs.addTab(self._dmx_monitor_view, "DMX Monitor")
        tabs.addTab(self._midi_view,        "MIDI")
        tabs.addTab(self._audio_input_view, "Audio Input")
        return tabs

    # ── Statusbar ─────────────────────────────────────────────────────────────

    def _setup_statusbar(self):
        sb = self.statusBar()
        self._lbl_enttec   = QLabel("Enttec: --")
        self._lbl_web      = QLabel("Web: aus")
        self._lbl_fixtures = QLabel("0 Geraete")
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
                self.statusBar().showMessage("Rueckgaengig", 1500)

    def _do_redo(self):
        if self._undo_stack:
            ok = self._undo_stack.redo()
            if ok:
                self.statusBar().showMessage("Wiederhergestellt", 1500)

    def _clear_undo_history(self):
        if self._undo_stack:
            self._undo_stack.clear()
            self.statusBar().showMessage("Undo-Verlauf geleert", 1500)

    def _refresh_undo_labels(self):
        if not getattr(self, "_undo_stack", None):
            return
        u = self._undo_stack.undo_label()
        r = self._undo_stack.redo_label()
        self._act_undo.setText(f"Rueckgaengig: {u}" if u else "Rueckgaengig")
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
            QTimer.singleShot(0, self._flash_bpm_indicator)
        except Exception:
            pass

    def _flash_bpm_indicator(self):
        # Akzent auf Beat 1 (alle 4)
        col = "#FFD700" if (self._bpm_mgr and self._bpm_mgr._beat_index % 4 == 1) else "#9DFF52"
        self._bpm_indicator.setStyleSheet(
            f"background:{col}; border-radius:3px; margin:4px 4px;")
        self._bpm_indicator_timer.start()

    def _set_bpm_manually(self):
        if not self._bpm_mgr:
            return
        current = self._bpm_mgr.bpm if self._bpm_mgr.bpm > 0 else 120.0
        val, ok = QInputDialog.getDouble(
            self, "BPM einstellen", "BPM (0 = aus, 20–999):",
            current, 0.0, 999.0, 1
        )
        if ok:
            self._bpm_mgr.set_bpm(val)
            if val > 0:
                self._lbl_bpm.setText(f"BPM: {val:.1f}")
                self._lbl_bpm.setStyleSheet("color: #FFD700; padding: 0 8px;")
            else:
                self._lbl_bpm.setText("BPM: --")
                self._lbl_bpm.setStyleSheet("color: #888888; padding: 0 8px;")

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
            self, "Page waehlen", "Page:", items, pe.current_page, False
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

    def _open_visualizer(self):
        # IMMER neu instanziieren -> HTML/JS wird frisch geladen (kein Stale-Cache).
        # Altes Fenster sauber schliessen falls noch offen.
        try:
            if self._visualizer_window is not None:
                try:
                    self._visualizer_window.close()
                    self._visualizer_window.deleteLater()
                except Exception as e:
                    print(f"[MainWindow] _open_visualizer cleanup error: {e}")
                self._visualizer_window = None
        except Exception:
            self._visualizer_window = None
        from src.ui.visualizer.visualizer_window import VisualizerWindow
        self._visualizer_window = VisualizerWindow(self)
        self._visualizer_window.show()
        self._visualizer_window.raise_()
        self._visualizer_window.activateWindow()

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
            "Aktuelle Show verwerfen und neu beginnen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._state.clear_programmer()
            self._state.cue_stacks.clear()
            self._current_show_path = None
            self.setWindowTitle("LightOS")

    def _open_show(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Show oeffnen", "", "LightOS Show (*.lshow);;Alle Dateien (*)"
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
            act.triggered.connect(lambda _=False, p=path: self._open_show_path(p))
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
            "aber das vollstaendige Mapping in LightOS-Strukturen "
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
                    "Web-Interface laeuft auf http://localhost:5000")
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
            self, "Ueber LightOS",
            "<b>LightOS v1.0</b><br>"
            "Professionelle DMX-Lichtsteuerung<br><br>"
            "Windows x64 &amp; ARM64<br>"
            "Enttec Pro USB &middot; Art-Net 4 &middot; MIDI<br><br>"
            "UI: QLC+ v5 Design System"
        )

    # ── State-Events ─────────────────────────────────────────────────────────

    def _on_state_event(self, event: str, _data):
        if event == "patch_changed":
            count = len(self._state.get_patched_fixtures())
            self._lbl_fixtures.setText(f"{count} Geraet(e)")

    def _on_refresh_all(self, _ev, _data):
        """Globaler REFRESH_ALL Handler - re-checked Hardware + Status."""
        try:
            self._check_hardware()
            count = len(self._state.get_patched_fixtures())
            self._lbl_fixtures.setText(f"{count} Geraet(e)")
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

    def _setup_autosave(self):
        try:
            self._autosave_timer = QTimer(self)
            self._autosave_timer.setInterval(5 * 60 * 1000)  # 5 Minuten
            self._autosave_timer.timeout.connect(self._do_autosave)
            self._autosave_timer.start()
            print(f"[autosave] aktiv (5 min) -> {self._autosave_path()}")
        except Exception as e:
            print(f"[autosave] setup error: {e}")

    def _do_autosave(self):
        try:
            from src.core.show.show_file import save_show
            path = self._autosave_path()
            save_show(path)
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
        self._state.output_manager.stop()
        if self._state.playback_engine:
            self._state.playback_engine.stop()
        from src.core.midi.midi_manager import get_midi_manager
        get_midi_manager().close_all()
        if self._visualizer_window:
            self._visualizer_window.close()
        super().closeEvent(event)


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
