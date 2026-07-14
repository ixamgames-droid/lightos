"""Virtual Console tab — toolbar + canvas + Bibliothek-Sidebar."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QPushButton,
    QLabel, QSizePolicy, QSplitter,
)
from PySide6.QtCore import Qt, QPoint, QSize, QTimer

from src.ui.virtualconsole.vc_canvas import VCCanvas
from src.ui.virtualconsole.vc_inspector_panel import VCInspectorPanel
from src.ui.widgets.flow_layout import FlowLayout
from src.ui.weak_slots import weak_slot


# ─────────────────────────────────────────────────────────────────────────────
#  Bibliothek-Sidebar (Show-Bibliothek → VC-Tasten)
# ─────────────────────────────────────────────────────────────────────────────

class SnapshotSidebar(QWidget):
    """Rechte Seitenleiste: die Show-Bibliothek (Farben/Snaps + Effekte/Funktionen
    in einer gemeinsamen Ordnerstruktur). Eintraege lassen sich per Ziehen auf das
    Canvas oder per Rechtsklick -> „Auf VC-Taste legen" direkt auf eine Taste legen
    (VC-Patching). Programmierte Snapshots (Vollbilder) bleiben ueber den
    Button-Dialog unter „Snapshot" erreichbar.
    """

    def __init__(self, canvas: VCCanvas, parent=None):
        super().__init__(parent)
        self._canvas = canvas
        self._setup_ui()
        self.setMinimumWidth(200)
        self.setMaximumWidth(340)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        hdr = QLabel("Bibliothek")
        hdr.setStyleSheet(
            "color:#ffd700; font-weight:bold; font-size:12px; padding:2px 0;")
        hdr.setToolTip("Farben/Snaps (gelb) und Effekte/Funktionen (farbig) dieser Show")
        layout.addWidget(hdr)

        hint = QLabel("Eintrag auf eine Taste ziehen –\noder Rechtsklick → „Auf VC-Taste legen\".")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8b949e; font-size:10px; padding-bottom:2px;")
        layout.addWidget(hint)

        # Gemeinsame Bibliothek (snap_file_panel) im Drag-auf-Canvas-Modus
        # wiederverwenden — eine Quelle fuer Programmer UND Virtual Console.
        from src.ui.views.snap_file_panel import SnapFilePanel
        # show_header=False: die Sidebar liefert oben bereits den "Bibliothek"-
        # Header + Hinweis -> den panel-eigenen Header unterdruecken (kein Doppel).
        self._panel = SnapFilePanel(drag_to_canvas=True, canvas=self._canvas,
                                    show_header=False)
        layout.addWidget(self._panel, 1)

    # ── Kompatible API (von VirtualConsoleView aufgerufen) ────────────────────

    def refresh(self):
        try:
            self._panel._refresh_tree()
        except (RuntimeError, AttributeError):
            pass

    def refresh_functions(self):
        self.refresh()


# ─────────────────────────────────────────────────────────────────────────────
#  VirtualConsoleView
# ─────────────────────────────────────────────────────────────────────────────

class VirtualConsoleView(QWidget):
    """Full Virtual Console tab: Toolbar + Canvas + Snapshot-Sidebar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._edit_mode = False
        self._midi_learn_active = False
        self._popout_window = None
        self._pop_scroll = None
        self._apc_feedback = None
        self._inspector = None
        # UXT-06: laufende Nummer für das Staffeln (Kaskade) neuer Toolbar-Widgets,
        # damit ein zweiter Klick nicht deckungsgleich auf dem ersten landet.
        self._add_cascade = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setStyleSheet("background:#161b22; border-bottom:1px solid #30363d;")
        # Umbrechende Toolbar: bei 200 %-Display-Skalierung / schmalem Fenster
        # passen im Bearbeiten-Modus nicht alle Buttons in eine Zeile. Das
        # FlowLayout bricht dann in die nächste Zeile um, statt die Buttons (und
        # damit ihren Text) unter die Wunschbreite zusammenzuquetschen. Passt
        # alles in eine Zeile (Live-Modus), bleibt es einzeilig.
        toolbar.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        _tb_sp = toolbar.sizePolicy()
        _tb_sp.setHeightForWidth(True)
        toolbar.setSizePolicy(_tb_sp)
        tb_layout = FlowLayout(toolbar, margin=0, h_spacing=6, v_spacing=4)
        tb_layout.setContentsMargins(8, 3, 8, 3)

        self._btn_edit = QPushButton("Bearbeiten")
        self._btn_edit.setCheckable(True)
        self._btn_edit.setChecked(False)
        self._btn_edit.setFixedSize(90, 28)
        self._btn_edit.setStyleSheet("""
            QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                          border-radius:3px; font-size:11px; }
            QPushButton:checked { background:#0d4f8b; color:#58d68d; border-color:#1f6feb; }
            QPushButton:hover { background:#30363d; }
        """)
        self._btn_edit.toggled.connect(self._toggle_edit)
        tb_layout.addWidget(self._btn_edit)

        self._btn_snap = QPushButton("⊞ Raster")
        self._btn_snap.setCheckable(True)
        self._btn_snap.setChecked(False)
        self._btn_snap.setFixedHeight(26)
        self._btn_snap.setToolTip(
            "Snap auf Grid — Widgets rasten beim Verschieben und Skalieren\n"
            "am Raster ein (Grid-Größe: 8 px)"
        )
        self._btn_snap.setStyleSheet("""
            QPushButton { background:#21262d; color:#8b949e; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:checked { background:#0d4f8b; color:#58d68d; border-color:#1f6feb; }
            QPushButton:hover:!disabled { background:#30363d; color:#e6edf3; }
            QPushButton:disabled { color:#484f58; border-color:#21262d; }
        """)
        self._btn_snap.setProperty("edit_only", True)
        self._btn_snap.setVisible(False)
        self._btn_snap.toggled.connect(self._toggle_snap)
        tb_layout.addWidget(self._btn_snap)

        # Widget quick-add buttons
        widget_buttons = [
            ("Button",    "VCButton"),
            ("Fader",     "VCSlider"),
            ("XY Pad",    "VCXYPad"),
            ("Cueliste",  "VCCueList"),
            ("SpeedDial", "VCSpeedDial"),
            ("Encoder",   "VCEncoder"),
            ("Farbe",     "VCColor"),
            ("Chase-Liste", "VCColorList"),
            ("Effekt-Farben", "VCEffectColors"),
            ("Label",     "VCLabel"),
            ("Frame",     "VCFrame"),
            ("Musik",     "VCSongInfo"),
            ("BPM",       "VCBpmDisplay"),
            ("Tempo-Bus", "VCBusSelector"),
            ("Tempo-Controller", "VCTempoBusController"),
            ("Live-Edit", "VCMultiLiveEditor"),
        ]
        for label, wtype in widget_buttons:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.setStyleSheet("""
                QPushButton { background:#21262d; color:#8b949e; border:1px solid #30363d;
                              border-radius:3px; font-size:10px; padding:0 8px; }
                QPushButton:hover { background:#30363d; color:#e6edf3; }
                QPushButton:disabled { color:#484f58; }
            """)
            btn.clicked.connect(weak_slot(self._add_widget, wtype))
            btn.setProperty("add_btn", True)
            btn.setProperty("edit_only", True)
            btn.setVisible(False)
            tb_layout.addWidget(btn)

        # Undo/Redo (Bearbeitungsverlauf): zwei Pfeile, edit-only. Strg+Z / Strg+Y.
        for _glyph, _tip, _slot in [("↶", "Rückgängig (Strg+Z)", self._vc_undo),
                                    ("↷", "Wiederholen (Strg+Y)", self._vc_redo)]:
            ub = QPushButton(_glyph)
            ub.setFixedHeight(26)
            ub.setToolTip(_tip)
            ub.setStyleSheet("""
                QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                              border-radius:3px; font-size:14px; padding:0 8px; }
                QPushButton:hover { background:#30363d; }
            """)
            ub.clicked.connect(weak_slot(_slot))
            ub.setProperty("edit_only", True)
            ub.setVisible(False)
            tb_layout.addWidget(ub)
        from PySide6.QtGui import QShortcut, QKeySequence
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._vc_undo)
        QShortcut(QKeySequence("Ctrl+Y"), self, activated=self._vc_redo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self._vc_redo)

        # MIDI-Learn-Button
        self._btn_midi_learn = QPushButton("MIDI Lernen")
        self._btn_midi_learn.setCheckable(True)
        self._btn_midi_learn.setFixedHeight(26)
        self._btn_midi_learn.setToolTip(
            "MIDI-Patch-Modus: Zuerst einen VC-Button anklicken,\n"
            "dann die gewünschte MIDI-Taste drücken."
        )
        self._btn_midi_learn.setStyleSheet("""
            QPushButton { background:#21262d; color:#ff8800; border:1px solid #ff8800;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:checked { background:#ff8800; color:#000; font-weight:bold; }
            QPushButton:hover { background:#30363d; }
        """)
        self._btn_midi_learn.toggled.connect(self._toggle_midi_learn)
        tb_layout.addWidget(self._btn_midi_learn)

        # APC LEDs Toggle
        self._btn_apc_leds = QPushButton("APC LEDs")
        self._btn_apc_leds.setCheckable(True)
        self._btn_apc_leds.setFixedHeight(26)
        self._btn_apc_leds.setToolTip(
            "APC Mini LED-Feedback aktivieren/deaktivieren\n"
            "Grün = aktiv, Grün blinkend = gestoppt, Rot = Flash, Gelb = aktuelle Page"
        )
        self._btn_apc_leds.setStyleSheet("""
            QPushButton { background:#21262d; color:#00cc66; border:1px solid #00cc66;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:checked { background:#00cc66; color:#000; font-weight:bold; }
            QPushButton:hover { background:#30363d; }
        """)
        self._btn_apc_leds.toggled.connect(self._toggle_apc_leds)
        tb_layout.addWidget(self._btn_apc_leds)

        # Touch-Lock (Display-only): nur Anzeige, keine Steuerung per Touchscreen
        self._btn_touch_lock = QPushButton("🔒 Touch-Lock")
        self._btn_touch_lock.setCheckable(True)
        self._btn_touch_lock.setFixedHeight(26)
        self._btn_touch_lock.setToolTip(
            "Display-only: Touchscreen/Maus steuert nicht mehr (nur Anzeige).\n"
            "APC mini / MIDI steuern weiterhin. Schützt vor versehentlichem Antippen."
        )
        self._btn_touch_lock.setStyleSheet("""
            QPushButton { background:#21262d; color:#ffb000; border:1px solid #ffb000;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:checked { background:#ffb000; color:#000; font-weight:bold; }
            QPushButton:hover { background:#30363d; }
        """)
        self._btn_touch_lock.toggled.connect(self._toggle_touch_lock)
        tb_layout.addWidget(self._btn_touch_lock)

        # Soft-Takeover / „Pickup": für nicht-motorisierte Controller (APC mini & Co.).
        # Nach einem Seiten-/Bankwechsel übernimmt ein Fader erst, wenn der physische
        # Fader den aktuellen VC-Wert einmal durchfahren hat → keine Wertsprünge.
        self._btn_pickup = QPushButton("🎚 Pickup")
        self._btn_pickup.setCheckable(True)
        self._btn_pickup.setFixedHeight(26)
        self._btn_pickup.setToolTip(
            "Soft-Takeover für nicht-motorisierte Fader (APC mini …):\n"
            "Nach einem Seitenwechsel springt der Wert nicht — der Fader übernimmt\n"
            "erst, wenn er den aktuellen VC-Wert einmal durchfahren hat.\n"
            "Ein gelber Pfeil zeigt, wohin der Fader bewegt werden muss."
        )
        self._btn_pickup.setStyleSheet("""
            QPushButton { background:#21262d; color:#ffb000; border:1px solid #ffb000;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:checked { background:#ffb000; color:#000; font-weight:bold; }
            QPushButton:hover { background:#30363d; }
        """)
        self._btn_pickup.toggled.connect(self._toggle_soft_takeover)
        tb_layout.addWidget(self._btn_pickup)

        # Bank-Umschaltung (= Executor-Page): bestimmt, welche Widgets/Pads aktiv
        # sind. APC-Page-Buttons schalten dieselbe Bank. Immer sichtbar.
        _bank_btn_css = """
            QPushButton { background:#21262d; color:#58a6ff; border:1px solid #30363d;
                          border-radius:3px; font-size:12px; font-weight:bold; }
            QPushButton:hover { background:#30363d; color:#e6edf3; }
        """
        self._btn_bank_prev = QPushButton("◀")
        self._btn_bank_prev.setFixedSize(26, 26)
        self._btn_bank_prev.setToolTip("Vorherige Bank (Pad-/Widget-Seite)")
        self._btn_bank_prev.setStyleSheet(_bank_btn_css)
        self._btn_bank_prev.clicked.connect(weak_slot(self._step_bank, -1))
        tb_layout.addWidget(self._btn_bank_prev)

        self._lbl_bank = QLabel("Bank 1")
        self._lbl_bank.setFixedWidth(54)
        self._lbl_bank.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_bank.setStyleSheet(
            "color:#58a6ff; font-size:11px; font-weight:bold;"
        )
        tb_layout.addWidget(self._lbl_bank)

        self._btn_bank_next = QPushButton("▶")
        self._btn_bank_next.setFixedSize(26, 26)
        self._btn_bank_next.setToolTip("Nächste Bank (Pad-/Widget-Seite)")
        self._btn_bank_next.setStyleSheet(_bank_btn_css)
        self._btn_bank_next.clicked.connect(weak_slot(self._step_bank, 1))
        tb_layout.addWidget(self._btn_bank_next)

        # Popout Button
        self._btn_popout = QPushButton("⧉ Popout")
        self._btn_popout.setFixedHeight(26)
        self._btn_popout.setToolTip("Virtual Console in eigenem Fenster öffnen")
        self._btn_popout.setStyleSheet("""
            QPushButton { background:#21262d; color:#8b949e; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:hover { background:#30363d; color:#e6edf3; }
        """)
        self._btn_popout.clicked.connect(self._popout_canvas)
        tb_layout.addWidget(self._btn_popout)

        btn_clear = QPushButton("Alle löschen")
        btn_clear.setFixedHeight(26)
        btn_clear.setStyleSheet("""
            QPushButton { background:#21262d; color:#f85149; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:hover { background:#30363d; }
        """)
        btn_clear.clicked.connect(self._clear_all)
        btn_clear.setProperty("edit_only", True)
        btn_clear.setVisible(False)
        tb_layout.addWidget(btn_clear)

        btn_save = QPushButton("Canvas exportieren…")
        btn_save.setFixedHeight(26)
        btn_save.setToolTip("Nur dieses VC-Layout als separate JSON-Datei exportieren "
                            "(unabhängig vom Show-Speichern unter Datei → Speichern).")
        btn_save.setStyleSheet("""
            QPushButton { background:#21262d; color:#3fb950; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:hover { background:#30363d; }
        """)
        btn_save.clicked.connect(self._save)
        tb_layout.addWidget(btn_save)

        btn_load = QPushButton("Canvas importieren…")
        btn_load.setFixedHeight(26)
        btn_load.setToolTip("Ein zuvor exportiertes VC-Layout (JSON) in dieses Canvas laden.")
        btn_load.setStyleSheet("""
            QPushButton { background:#21262d; color:#58a6ff; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:hover { background:#30363d; }
        """)
        btn_load.clicked.connect(self._load)
        tb_layout.addWidget(btn_load)

        # Sidebar-Toggle
        self._btn_sidebar = QPushButton("◀ Bibliothek")
        self._btn_sidebar.setCheckable(True)
        self._btn_sidebar.setChecked(True)
        self._btn_sidebar.setFixedHeight(26)
        self._btn_sidebar.setStyleSheet("""
            QPushButton { background:#21262d; color:#ffd700; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:checked { background:#2a3344; color:#ffd700; }
            QPushButton:hover { background:#30363d; }
        """)
        self._btn_sidebar.toggled.connect(self._toggle_sidebar)
        tb_layout.addWidget(self._btn_sidebar)

        # Inspector-Panel ein-/ausblenden (nur im Bearbeiten-Modus sichtbar).
        self._btn_inspector = QPushButton("⚙ Inspector ✓")
        self._btn_inspector.setCheckable(True)
        self._btn_inspector.setChecked(True)
        self._btn_inspector.setFixedHeight(26)
        self._btn_inspector.setProperty("edit_only", True)
        self._btn_inspector.setVisible(False)
        self._btn_inspector.setStyleSheet("""
            QPushButton { background:#21262d; color:#58d68d; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:checked { background:#0d4f8b; color:#58d68d; border-color:#1f6feb; }
            QPushButton:hover { background:#30363d; }
        """)
        self._btn_inspector.toggled.connect(self._toggle_inspector)
        tb_layout.addWidget(self._btn_inspector)

        layout.addWidget(toolbar)
        self._toolbar_widget = toolbar

        # ── Status-Zeile: aktiver Effekt ──────────────────────────────────────
        self._lbl_active_fx = QLabel("Aktiver Effekt: —")
        # Feste, schmale Hoehe: sonst dehnt sich das Label vertikal auf und
        # verdeckt die halbe Canvas-Flaeche.
        self._lbl_active_fx.setFixedHeight(22)
        self._lbl_active_fx.setStyleSheet(
            "background:#0d1117; color:#9DFF52; border-bottom:1px solid #21262d;"
            " padding:2px 10px; font-size:11px;")
        layout.addWidget(self._lbl_active_fx)
        self._active_fx_timer = QTimer(self)
        self._active_fx_timer.setInterval(400)
        self._active_fx_timer.timeout.connect(self._update_active_fx)
        self._active_fx_timer.start()

        # ── Splitter: Canvas links, Sidebar rechts ────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background:#30363d; width:2px; }")

        self._main_scroll = QScrollArea()
        self._main_scroll.setWidgetResizable(False)
        self._main_scroll.setStyleSheet("QScrollArea { border:none; background:#0d1117; }")

        self._canvas = VCCanvas()
        self._canvas.midi_learn_done.connect(self._on_midi_learn_done)
        self._canvas.bank_changed.connect(self._on_bank_changed)
        self._canvas.widget_selected.connect(self._on_canvas_widget_selected)
        self._on_bank_changed(self._canvas.active_bank)
        self._main_scroll.setWidget(self._canvas)
        splitter.addWidget(self._main_scroll)

        # Inspector-Panel (Eigenschaften des gewaehlten Widgets, nur im Edit-Modus).
        self._inspector = VCInspectorPanel()
        self._inspector.setStyleSheet(
            "QWidget { background:#0d1117; border-left:1px solid #21262d; }"
        )
        self._inspector.setVisible(False)
        splitter.addWidget(self._inspector)

        # Sidebar
        self._sidebar = SnapshotSidebar(self._canvas)
        self._sidebar.setStyleSheet(
            "QWidget { background:#0d1117; border-left:1px solid #21262d; }"
        )
        splitter.addWidget(self._sidebar)

        # Größenverhältnis: Canvas viel breiter als Inspector/Sidebar
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 0)
        splitter.setStretchFactor(2, 1)
        splitter.setCollapsible(1, True)
        self._splitter = splitter

        # Stretch=1: der Canvas-/Sidebar-Splitter bekommt den gesamten
        # verbleibenden vertikalen Platz (Toolbar + Statuszeile sind fix).
        layout.addWidget(splitter, 1)

    # ── Status: aktiver Effekt ───────────────────────────────────────────────

    def _update_active_fx(self):
        """Zeigt den zuletzt gestarteten, noch laufenden Effekt + Anzahl laufender."""
        try:
            from src.core.engine.function_manager import get_function_manager
            fm = get_function_manager()
            # Funktionsliste der Sidebar nachziehen, wenn sich die Anzahl geaendert
            # hat (z. B. Show geladen) — ohne bei jedem Tick die Auswahl zu stoeren.
            try:
                cnt = len(fm.all())
                if cnt != getattr(self, "_last_fn_count", -1):
                    self._last_fn_count = cnt
                    if getattr(self, "_sidebar", None) is not None:
                        self._sidebar.refresh_functions()
            except Exception:
                pass
            active = fm.active_function()
            # Thread-sicherer Snapshot statt Direktzugriff auf _running_ids.
            running_ids = frozenset(fm.running_ids())
            running = len(running_ids)
            # Bei JEDEM Wechsel des Laufzustands die funktionsgebundenen VC-Widgets
            # neu zeichnen — sonst bleibt ein Toggle-Pad „aus", obwohl sein Effekt
            # noch laeuft (oder „an", obwohl er sich selbst/per StopAll beendet hat).
            if running_ids != getattr(self, "_last_running_ids", None):
                self._last_running_ids = running_ids
                if self._canvas_alive():
                    from src.ui.virtualconsole.vc_button import VCButton
                    from src.ui.virtualconsole.vc_slider import VCSlider
                    for cls in (VCButton, VCSlider):
                        for w in self._canvas.findChildren(cls):
                            try:
                                w.update()
                            except Exception:
                                pass
            if active is not None:
                extra = f"  (+{running - 1} weitere)" if running > 1 else ""
                self._lbl_active_fx.setText(
                    f"Aktiver Effekt: {active.function_type.value} · {active.name}{extra}")
                self._lbl_active_fx.setStyleSheet(
                    "background:#0d1117; color:#9DFF52; border-bottom:1px solid #21262d;"
                    " padding:2px 10px; font-size:11px;")
                self._lbl_active_fx.setVisible(True)   # UIC-04: nur bei laufendem Effekt sichtbar
            else:
                self._lbl_active_fx.setVisible(False)
                self._lbl_active_fx.setText("Aktiver Effekt: —")
                self._lbl_active_fx.setStyleSheet(
                    "background:#0d1117; color:#666; border-bottom:1px solid #21262d;"
                    " padding:2px 10px; font-size:11px;")
        except Exception:
            pass
        # To-Do #9: Farb-Kacheln (Programmer/Alle) ausgrauen, sobald eine RGB-/
        # RGBW-Matrix läuft (die besitzt dann die Farbe). Nur bei Zustandswechsel
        # neu zeichnen, damit der 400-ms-Tick nicht ständig repaintet.
        try:
            from src.core.engine import effect_live
            from src.ui.virtualconsole.vc_color import VCColor
            driven = effect_live.color_is_effect_driven()
            if driven != getattr(self, "_last_color_driven", None):
                self._last_color_driven = driven
                if self._canvas_alive():
                    for w in self._canvas.findChildren(VCColor):
                        w.update()
        except Exception:
            pass

    # ── Edit mode ────────────────────────────────────────────────────────────

    def _canvas_alive(self) -> bool:
        """True, wenn das C++-Objekt des Canvas noch existiert (gegen
        'already deleted'-Abstürze, falls der Canvas anderweitig zerstört wurde)."""
        try:
            import shiboken6
            return shiboken6.isValid(self._canvas)
        except Exception:
            return self._canvas is not None

    def _toggle_edit(self, enabled: bool):
        self._edit_mode = enabled
        self._btn_edit.setText("Bearbeiten ✓" if enabled else "Bearbeiten")
        self._add_cascade = 0      # UXT-06: Kaskade je Bearbeiten-Sitzung neu
        if not self._canvas_alive():
            return
        self._canvas.set_edit_mode(enabled)
        # Bearbeiten-only-Buttons (Widgets hinzufügen, Snap, Alle löschen) nur
        # im Bearbeiten-Modus zeigen -> aufgeraeumtes Fenster im Live-Betrieb.
        for btn in self._toolbar_widget.findChildren(QPushButton):
            if btn.property("edit_only"):
                btn.setVisible(enabled)
        # Inspector-Panel folgt dem Edit-Modus; beim Verlassen Auswahl loesen.
        if self._inspector is not None:
            if enabled:
                self._inspector.setVisible(self._btn_inspector.isChecked())
            else:
                self._inspector.clear()
                self._inspector.setVisible(False)

    def _toggle_snap(self, checked: bool):
        self._canvas.set_snap_to_grid(checked)

    # ── MIDI-Learn ───────────────────────────────────────────────────────────

    def _toggle_midi_learn(self, checked: bool):
        self._midi_learn_active = checked
        if checked:
            self._canvas.start_midi_learn()
        else:
            self._canvas.cancel_midi_learn()

    def _on_midi_learn_done(self):
        self._midi_learn_active = False
        self._btn_midi_learn.setChecked(False)

    # ── APC LEDs ─────────────────────────────────────────────────────────────

    def _toggle_touch_lock(self, checked: bool):
        """Display-only: Touch/Maus im Run-Modus sperren (APC/MIDI bleibt aktiv)."""
        try:
            from src.ui.virtualconsole.vc_widget import VCWidget
            VCWidget.input_locked = bool(checked)
            self._btn_touch_lock.setText("🔒 Gesperrt" if checked else "🔒 Touch-Lock")
        except Exception as e:
            print(f"[VC] touch lock error: {e}")

    def _toggle_soft_takeover(self, checked: bool):
        """Soft-Takeover (Pickup) global ein-/ausschalten und die Fader der aktuellen
        Seite sofort (neu) armieren."""
        try:
            from src.ui.virtualconsole.vc_slider import VCSlider
            VCSlider.soft_takeover = bool(checked)
            self._btn_pickup.setText("🎚 Pickup AN" if checked else "🎚 Pickup")
            if checked and hasattr(self._canvas, "_rearm_slider_pickup"):
                self._canvas._rearm_slider_pickup()
            else:
                # beim Ausschalten alle Fader sofort wieder „frei" schalten
                from src.ui.virtualconsole.vc_slider import VCSlider as _S
                for w in self._canvas.findChildren(_S):
                    w._pickup_armed = False
                    w.update()
        except Exception as e:
            print(f"[VC] soft-takeover error: {e}")

    def _toggle_apc_leds(self, checked: bool):
        if checked:
            try:
                from src.core.app_state import get_state
                from src.core.midi.midi_manager import get_midi_manager
                outs = get_midi_manager().list_outputs()
                is_mk2 = any("mk2" in p.lower() for p in outs)
                if is_mk2:
                    # mk2 nutzt RGB + spiegelt die VC-Button-Zustaende
                    from src.core.midi.apc_mk2_feedback import ApcMk2Feedback
                    self._apc_feedback = ApcMk2Feedback(self._canvas)
                else:
                    from src.core.midi.apc_mini_feedback import APCMiniFeedback
                    self._apc_feedback = APCMiniFeedback()
                if self._apc_feedback.is_connected:
                    self._apc_feedback.attach(get_state())
                else:
                    self._btn_apc_leds.setChecked(False)
                    self._apc_feedback = None
            except Exception as e:
                print(f"[VC] APC LEDs Fehler: {e}")
                self._btn_apc_leds.setChecked(False)
        else:
            if self._apc_feedback:
                self._apc_feedback.close()
                self._apc_feedback = None

    # ── Bank/Page ──────────────────────────────────────────────────────────────

    def _step_bank(self, delta: int):
        target = max(0, min(9, self._canvas.active_bank + int(delta)))
        pe = None
        try:
            from src.core.app_state import get_state
            pe = get_state().playback_engine
        except Exception:
            pe = None
        if pe is not None:
            pe.set_page(target)        # -> Canvas via Page-Callback -> bank_changed
        else:
            self._canvas.set_active_bank(target)

    def _on_bank_changed(self, b: int):
        self._lbl_bank.setText(f"Bank {int(b) + 1}")

    # ── Popout ────────────────────────────────────────────────────────────────

    def _popout_canvas(self):
        if self._popout_window is not None:
            self._popout_window.show()
            self._popout_window.raise_()
            return

        view = self

        class _PopoutWindow(QWidget):
            def closeEvent(self, event):
                # Beim Schließen des Popout-Fensters den Canvas zurück in die
                # Haupt-Ansicht holen — sonst bleibt er im (versteckten) Fenster
                # hängen und die Virtual Console verschwindet aus LightOS.
                # WICHTIG: takeWidget() löst die Eigentümerschaft, ohne den Canvas
                # zu löschen. Würde man ihn im Popout-Scroll lassen, zerstört das
                # schließende Fenster das C++-Objekt (-> "VCCanvas already deleted"
                # beim nächsten Bearbeiten-/Hinzufügen-Klick).
                if view._pop_scroll is not None:
                    view._pop_scroll.takeWidget()
                    view._pop_scroll = None
                view._main_scroll.setWidget(view._canvas)
                view._popout_window = None
                event.accept()

        win = _PopoutWindow(None, Qt.WindowType.Window)
        win.setWindowTitle("Virtual Console — Popout")
        win.resize(1280, 800)
        pop_l = QVBoxLayout(win)
        pop_l.setContentsMargins(0, 0, 0, 0)

        pop_scroll = QScrollArea()
        pop_scroll.setWidgetResizable(False)
        pop_scroll.setStyleSheet("QScrollArea { border:none; background:#0d1117; }")
        # Canvas zuerst aus dem Haupt-Scroll lösen (ohne Löschen), dann übergeben.
        self._main_scroll.takeWidget()
        pop_scroll.setWidget(self._canvas)
        pop_l.addWidget(pop_scroll)

        self._pop_scroll = pop_scroll
        self._popout_window = win
        win.show()

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _toggle_sidebar(self, checked: bool):
        self._sidebar.setVisible(checked)
        self._btn_sidebar.setText("◀ Bibliothek" if checked else "▶ Bibliothek")
        if checked:
            self._sidebar.refresh()

    def _toggle_inspector(self, checked: bool):
        self._btn_inspector.setText("⚙ Inspector ✓" if checked else "⚙ Inspector")
        if self._inspector is not None:
            self._inspector.setVisible(checked and self._edit_mode)

    def _on_canvas_widget_selected(self, w):
        """Auswahl auf der Canvas -> Inspector binden (nur im Bearbeiten-Modus,
        wenn das Panel sichtbar ist; sonst nur intern merken)."""
        if self._inspector is None:
            return
        if self._edit_mode and self._btn_inspector.isChecked():
            self._inspector.bind(w)
        elif w is None:
            self._inspector.clear()

    # ── Widget actions ────────────────────────────────────────────────────────

    def _add_widget(self, wtype: str):
        if not self._edit_mode or not self._canvas_alive():
            return
        # UXT-06: Toolbar-Klicks platzierten JEDES neue Widget exakt in der Mitte
        # → der zweite lag deckungsgleich auf dem ersten (wirkte wie „nichts
        # passiert"). Jetzt staffeln wir sie diagonal (Kaskade) um die Mitte und
        # wählen das neue Widget aus, damit der Inspector sofort darauf zeigt.
        step = self._canvas.GRID * 3        # sichtbarer Versatz je Klick
        span = 8                            # nach 8 Stufen wieder von vorn
        i = self._add_cascade % span
        base_x = self._canvas.width() // 2 - (span * step) // 2
        base_y = self._canvas.height() // 2 - (span * step) // 2
        pos = QPoint(max(0, base_x + i * step), max(0, base_y + i * step))
        self._add_cascade += 1
        w = self._canvas._add_widget(wtype, pos)
        # Neues Widget auswählen → Inspector bindet, sichtbare Bestätigung.
        if w is not None:
            self._canvas._on_widget_selected(w)

    def _vc_undo(self):
        """Letzte VC-Bearbeitung rueckgaengig (Strg+Z / ↶-Knopf)."""
        if self._canvas_alive():
            self._canvas.undo()

    def _vc_redo(self):
        """Rueckgaengig gemachte VC-Bearbeitung wiederholen (Strg+Y / ↷-Knopf)."""
        if self._canvas_alive():
            self._canvas.redo()

    def _clear_all(self):
        if self._edit_mode:
            self._canvas._clear()

    def _save(self):
        self._canvas._save()

    def _load(self):
        self._canvas._load()

    # ── Public serialization ──────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return self._canvas.to_dict()

    def from_dict(self, d: dict):
        # Auswahl loesen, bevor die alten Widgets beim Laden zerstoert werden.
        if self._inspector is not None:
            self._inspector.clear()
        self._canvas.from_dict(d)
