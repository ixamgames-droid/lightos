"""Virtual Console tab — toolbar + canvas + Bibliothek-Sidebar."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QPushButton,
    QLabel, QSizePolicy, QSplitter,
)
from PySide6.QtCore import Qt, QEvent, QPoint, QSize, QTimer

from src.ui.virtualconsole.vc_canvas import VCCanvas
from src.ui.virtualconsole.vc_inspector_panel import VCInspectorPanel
from src.ui.widgets.flow_layout import FlowLayout
from src.ui.weak_slots import weak_slot


class GrowingScrollArea(QScrollArea):
    """Scroll-Bereich, dessen Inhalt auf breiten Viewports MITWAECHST.

    Zweck (Linux-Audit 2026-07-23): auf einem 1920-px-Touchscreen blieb die
    VC-Arbeitsflaeche starr auf ihrer Mindestbreite (1200 px) stehen; rechts
    daneben entstand eine grosse, unbenutzbare schwarze Flaeche.

    Bewusst NICHT ueber ``setWidgetResizable(True)`` geloest: die VC reicht
    denselben ``VCCanvas`` per ``takeWidget()``/``setWidget()`` zwischen Haupt-
    und Popout-Fenster hin und her. Mit ``widgetResizable=True`` destabilisiert
    dieser Wechsel den nativen Qt-Widget-Abbau — auf Windows/Python 3.11/
    PySide6 6.11 in ~88 % der Testlaeufe als ``STATUS_HEAP_CORRUPTION``
    (0xc0000374) reproduzierbar (Messung 2026-07-26: main 1/8 rot,
    ``setWidgetResizable(True)`` 7/8 rot; Bisect auf Commit e28c261).

    Diese Klasse behaelt deshalb die alte, stabile Eigentumssemantik
    (``widgetResizable=False``) und setzt die Groesse des Inhalts stattdessen
    selbst auf ``max(Mindestgroesse, Viewport)``. Sichtbares Ergebnis auf
    breiten Bildschirmen ist identisch; unterhalb von 1200x800 bleibt der
    Bereich wie bisher scrollbar.
    """

    def setWidget(self, widget):  # noqa: N802 (Qt-API)
        super().setWidget(widget)
        self._grow_widget()

    def resizeEvent(self, event):  # noqa: N802 (Qt-API)
        super().resizeEvent(event)
        self._grow_widget()

    def _grow_widget(self) -> None:
        w = self.widget()
        if w is None:
            return
        try:
            vp = self.viewport().size()
            target = QSize(max(w.minimumWidth(), vp.width()),
                           max(w.minimumHeight(), vp.height()))
            if w.size() != target:
                w.resize(target)
        except RuntimeError:
            # Canvas wird gerade zerstoert (Popout-Wechsel) — nichts zu tun.
            pass


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

    # VCB-47: Statuszeile „Aktiver Effekt" — fester Platz, wechselnder Inhalt.
    _ZEILE_AKTIVER_EFFEKT_H = 22
    _TEXT_KEIN_EFFEKT = "Kein Effekt aktiv"
    _STIL_ZEILE_AKTIV = (
        "background:#0d1117; color:#9DFF52; border-bottom:1px solid #21262d;"
        " padding:2px 10px; font-size:11px;")
    _STIL_ZEILE_LEER = (
        "background:#0d1117; color:#666; border-bottom:1px solid #21262d;"
        " padding:2px 10px; font-size:11px;")

    def __init__(self, parent=None, *, kiosk: bool = False):
        super().__init__(parent)
        # UI-96: Im Kiosk-Modus (``--kiosk``: „nur Virtual Console, keine
        # Bearbeitung") gibt es weder die Bibliothek-Seitenleiste noch einen
        # anderen Weg, das Layout oder die Belegung der Tasten zu aendern:
        # kein Bearbeiten-Modus, kein MIDI-Lernen, kein Canvas-Import, kein
        # Undo/Redo. Die Sperren sitzen in den Handlern selbst, nicht nur im
        # Ausblenden der Knoepfe — ein Kuerzel oder ein direkter Aufruf holt
        # sie nicht zurueck.
        self._kiosk = bool(kiosk)
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
        if self._kiosk:
            self._btn_edit.setEnabled(False)
            self._btn_edit.setVisible(False)

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

        # Undo/Redo (Bearbeitungsverlauf): zwei Pfeile, edit-only.
        from src.ui import undo_kuerzel
        # UI-93: die Knoepfe tun dasselbe wie die Tasten, die ihr Tooltip
        # nennt — im Hauptfenster also den gemeinsamen Verlauf (Layout UND
        # Patch/Geraete in zeitlicher Reihenfolge), nicht nur das Layout.
        for _glyph, _tip, _slot in [
                ("↶", f"Rückgängig ({undo_kuerzel.undo_text()}): nimmt den "
                      "zuletzt gemachten Schritt zurück. Das ist derselbe "
                      "Verlauf wie Bearbeiten → Rückgängig – Layout der "
                      "Konsole und Änderungen an Patch und Geräten in der "
                      "Reihenfolge, in der du sie gemacht hast.",
                 self._knopf_rueckgaengig),
                ("↷", f"Wiederholen ({undo_kuerzel.redo_text()}): holt den "
                      "zuletzt zurückgenommenen Schritt wieder. Das ist "
                      "derselbe Verlauf wie Bearbeiten → Wiederholen.",
                 self._knopf_wiederholen)]:
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
        # UI-93: eigene Kuerzel nur fuer den Betrieb OHNE Hauptfenster. Im
        # Hauptfenster liegen dieselben Folgen schon auf Bearbeiten →
        # Rückgängig; doppelt belegt loest Qt keine von beiden aus. Dort
        # verteilt das Fenster (MainWindow.event) und showEvent schaltet
        # diese beiden ab.
        # UI-96: im Kiosk kein Bearbeitungsverlauf -> keine Kuerzel.
        self._undo_kuerzel = () if self._kiosk else undo_kuerzel.kuerzel_anlegen(
            self, self._vc_undo, self._vc_redo,
            "Letzte Änderung am Layout zurücknehmen",
            "Zurückgenommene Änderung am Layout wiederholen")

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
        self._breite_festhalten(self._btn_midi_learn, (self._btn_midi_learn.text(),))
        tb_layout.addWidget(self._btn_midi_learn)
        if self._kiosk:
            # UI-96: MIDI-Lernen aendert die Belegung einer Taste -> Bearbeitung.
            self._btn_midi_learn.setEnabled(False)
            self._btn_midi_learn.setVisible(False)

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
        self._breite_festhalten(self._btn_apc_leds, (self._btn_apc_leds.text(),))
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
        self._breite_festhalten(self._btn_touch_lock, ("🔒 Touch-Lock", "🔒 Gesperrt"))
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
        self._breite_festhalten(self._btn_pickup, ("🎚 Pickup", "🎚 Pickup AN"))
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
        if self._kiosk:
            # UI-96: Import ersetzt das ganze Layout -> Bearbeitung.
            btn_load.setEnabled(False)
            btn_load.setVisible(False)
        self._btn_load = btn_load

        # Sidebar-Toggle (UI-96: im Kiosk gibt es keine Bibliothek -> kein Knopf)
        self._btn_sidebar = None
        if not self._kiosk:
            self._sidebar_knopf_bauen(tb_layout)

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
        # VCB-47: Die Zeile hat einen FESTEN, immer reservierten Platz. Sie wurde
        # frueher (UIC-04) nur bei laufendem Effekt eingeblendet — dadurch rutschte
        # die ganze Konsole beim ersten Tastendruck um 22 px nach unten, und der
        # zweite Tipp an derselben Bildschirmstelle ging daneben. Bedienflaechen
        # einer Live-Konsole duerfen sich durch Statusanzeigen nie verschieben:
        # die Zeile wird NIE ein-/ausgeblendet, nur Text und Farbe wechseln.
        self._lbl_active_fx = QLabel(self._TEXT_KEIN_EFFEKT)
        # Feste, schmale Hoehe: sonst dehnt sich das Label vertikal auf und
        # verdeckt die halbe Canvas-Flaeche.
        self._lbl_active_fx.setFixedHeight(self._ZEILE_AKTIVER_EFFEKT_H)
        # Breite ignorieren: ein langer Effektname darf weder die Mindestbreite
        # der Ansicht hochtreiben noch irgendetwas zur Seite schieben.
        self._lbl_active_fx.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        # Ein Effektname ist kein Markup: „<h1>…" im Namen wuerde sonst als
        # Ueberschrift gesetzt. Umbrochen wird nie — die Zeile bleibt einzeilig.
        self._lbl_active_fx.setTextFormat(Qt.TextFormat.PlainText)
        self._lbl_active_fx.setWordWrap(False)
        self._lbl_active_fx.setToolTip(
            "Zeigt den zuletzt gestarteten, noch laufenden Effekt und wie viele "
            "weitere gerade laufen.")
        self._lbl_active_fx.setStyleSheet(self._STIL_ZEILE_LEER)
        layout.addWidget(self._lbl_active_fx)
        self._active_fx_timer = QTimer(self)
        self._active_fx_timer.setInterval(400)
        self._active_fx_timer.timeout.connect(self._update_active_fx)
        self._active_fx_timer.start()

        # ── Splitter: Canvas links, Sidebar rechts ────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background:#30363d; width:2px; }")

        # Die VC-Arbeitsflaeche soll mindestens 1200x800 gross bleiben, auf
        # breiten Touchscreens aber den GANZEN verfuegbaren Viewport nutzen.
        # Vorher blieb der Canvas starr bei 1200 px und rechts entstand trotz
        # ~1680 px Platz eine grosse schwarze, nicht nutzbare Flaeche.
        # GrowingScrollArea erledigt das ohne Qt-``widgetResizable`` (siehe dort).
        self._main_scroll = GrowingScrollArea()
        self._main_scroll.setStyleSheet("QScrollArea { border:none; background:#0d1117; }")

        self._canvas = VCCanvas()
        # UI-96: auch der Canvas kennt den Kiosk (Zuweisungs-/Lern-Modi, Drops).
        self._canvas.set_kiosk(self._kiosk)
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

        # Sidebar — UI-96: im Kiosk gar nicht erst gebaut (kein Ziehen, kein
        # „Auf VC-Taste legen", keine Bibliotheks-Knoepfe).
        self._sidebar = None
        if not self._kiosk:
            self._sidebar = SnapshotSidebar(self._canvas)
            self._sidebar.setStyleSheet(
                "QWidget { background:#0d1117; border-left:1px solid #21262d; }"
            )
            splitter.addWidget(self._sidebar)

        # Größenverhältnis: Canvas viel breiter als Inspector/Sidebar
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 0)
        if self._sidebar is not None:
            splitter.setStretchFactor(2, 1)
        splitter.setCollapsible(1, True)
        self._splitter = splitter

        # Stretch=1: der Canvas-/Sidebar-Splitter bekommt den gesamten
        # verbleibenden vertikalen Platz (Toolbar + Statuszeile sind fix).
        layout.addWidget(splitter, 1)

    def _sidebar_knopf_bauen(self, tb_layout) -> None:
        """Knopf „◀ Bibliothek" (ausserhalb des Kiosk-Modus)."""
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
        self._breite_festhalten(self._btn_sidebar, ("◀ Bibliothek", "▶ Bibliothek"))
        tb_layout.addWidget(self._btn_sidebar)

    @property
    def kiosk(self) -> bool:
        return self._kiosk

    def showEvent(self, event):
        """Beim Oeffnen der VC einen aktuellen Bibliotheksbaum zeigen.

        Deckt den typischen Ablauf ab: Effekt in einer anderen Ansicht
        erstellen, danach erst zur Virtual Console wechseln.

        WICHTIG: nur bei tatsaechlicher Aenderung neu aufbauen.
        ``SnapshotSidebar.refresh()`` ist ein Clear-and-Rebuild des ganzen
        Baums und wirft dabei Auswahl und Scrollposition weg. Ein
        bedingungsloser Refresh bei JEDEM Tabwechsel liess also die gerade
        markierte Funktion verschwinden, sobald man kurz woanders nachsah.
        """
        super().showEvent(event)
        # UI-93: verteilt das Fenster Rueckgaengig/Wiederholen selbst, ruhen
        # die eigenen Kuerzel (sonst waeren die Folgen doppelt belegt).
        try:
            from src.ui import undo_kuerzel
            zentral = bool(getattr(self.window(),
                                   undo_kuerzel.MERKMAL_ZENTRAL, False))
            for sc in getattr(self, "_undo_kuerzel", ()):
                sc.setEnabled(not zentral)
        except RuntimeError:
            pass
        # Statusticker laeuft, solange die Ansicht benutzt wird. closeEvent
        # stoppt ihn; ein erneutes Anzeigen weckt ihn wieder auf.
        try:
            self._active_fx_timer.start()
        except (RuntimeError, AttributeError):
            pass
        sidebar = getattr(self, "_sidebar", None)
        if sidebar is None:
            return
        try:
            from src.core.engine.function_manager import get_function_manager
            sig = self._function_catalog_signature(get_function_manager().all())
        except Exception:
            sig = None
        if sig is None or sig != getattr(self, "_last_function_catalog_signature", None):
            if sig is not None:
                self._last_function_catalog_signature = sig
            sidebar.refresh()

    def closeEvent(self, event):
        """Beim Schliessen den 400-ms-Statusticker stoppen.

        Der Timer haengt am View und lief bisher weiter, solange das Objekt
        lebte — also auch nach dem Schliessen. Er ruft ``_update_active_fx``,
        das den Funktionskatalog abfragt und die Sidebar neu baut; auf einer
        bereits geschlossenen Ansicht ist das reine Last und arbeitet im
        Qt-Abbau auf halb zerlegten Widgets weiter.
        """
        try:
            self._active_fx_timer.stop()
        except (RuntimeError, AttributeError):
            pass
        fb = getattr(self, "_apc_feedback", None)
        if fb is not None:
            try:
                fb.close()
            except Exception:
                pass
            self._apc_feedback = None
        super().closeEvent(event)

    # ── Status: aktiver Effekt ───────────────────────────────────────────────

    @staticmethod
    def _function_catalog_signature(functions) -> tuple:
        """Leichte Signatur der in der VC-Bibliothek sichtbaren Metadaten.

        Die reine Anzahl reicht nicht: Editor-Ablauf ist oft
        ``Funktion anlegen -> benennen -> in Ordner verschieben``. Nach dem
        ersten Schritt bleibt die Anzahl gleich; geht das spaetere Sync-Event
        verloren, zeigte die VC dauerhaft den alten Namen/Ordner. Die Signatur
        erkennt auch solche In-Place-Aenderungen, ohne den Baum alle 400 ms
        unnoetig neu aufzubauen.
        """
        rows = []
        for f in functions:
            ftype = getattr(f, "function_type", "")
            ftype = getattr(ftype, "value", ftype)
            rows.append((
                int(getattr(f, "id", 0) or 0),
                str(getattr(f, "name", "") or ""),
                str(getattr(f, "folder", "") or ""),
                str(ftype or ""),
                bool(getattr(f, "committed", True)),
            ))
        return tuple(sorted(rows))

    def _update_active_fx(self):
        """Zeigt den zuletzt gestarteten, noch laufenden Effekt + Anzahl laufender."""
        try:
            from src.core.engine.function_manager import get_function_manager
            fm = get_function_manager()
            # Funktionskatalog der Sidebar nachziehen, wenn sich Anzahl ODER
            # sichtbare Metadaten (Name/Ordner/Typ) geaendert haben. So erscheint
            # z. B. ein nachtraeglich nach Hintergrund/Dimmer verschobener
            # "Strobe" auch dann sofort, wenn sein einzelnes Sync-Event ausblieb.
            try:
                funcs = fm.all()
                sig = self._function_catalog_signature(funcs)
                if sig != getattr(self, "_last_function_catalog_signature", None):
                    self._last_function_catalog_signature = sig
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
            # ENG-37-B: ebenso, wenn ein Modify-Haken oder eine Betriebsart
            # umgestellt wurde — Taste/Fader zeigen das Zeichen der Betriebsart.
            try:
                from src.ui.widgets.modify_zeichen import modify_signatur
                modify_sig = modify_signatur(funcs)
            except Exception:
                modify_sig = None
            if (running_ids != getattr(self, "_last_running_ids", None)
                    or modify_sig != getattr(self, "_last_modify_sig", None)):
                self._last_running_ids = running_ids
                self._last_modify_sig = modify_sig
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
                # Zeilenumbrueche/Tabulatoren im Namen zu Leerzeichen: in der
                # 22 px hohen Zeile waere sonst nur die mittlere Textzeile zu sehen.
                name = " ".join(str(active.name).split())
                self._zeige_aktiven_effekt(
                    f"Aktiver Effekt: {active.function_type.value} · {name}{extra}",
                    self._STIL_ZEILE_AKTIV)
            else:
                self._zeige_aktiven_effekt(self._TEXT_KEIN_EFFEKT, self._STIL_ZEILE_LEER)
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

    def ausgabe_chip_platz(self):
        """VCB-47 (Nachtrag 2): wo der eingeklappte Hinweis „Ausgabe gestört“
        des Hauptfensters (``ausgabe_banner.AusgabeChip``) nichts verdeckt — das
        rechte Ende der Zeile „Aktiver Effekt“. Seit UI-103 liegt dort auch das
        aufgeklappte Banner (Probenmodus/Stoerung), statt ueber den
        Bank-Knoepfen und der Werkzeugleiste. Sie liegt zwischen Werkzeugleiste
        und Konsole, hat einen festen Platz und traegt keine Bedienung; der Chip
        beruehrt dort in keiner Fensterbreite einen Knopf oder eine Taste."""
        return self._lbl_active_fx

    def _zeige_aktiven_effekt(self, text: str, stil: str) -> None:
        """VCB-47: nur Text und Farbe der Statuszeile wechseln — nie ihre Sichtbarkeit
        oder Hoehe (sonst verschiebt sich die Konsole unter dem Finger). Unveraenderte
        Werte werden nicht neu gesetzt: der 400-ms-Takt soll nicht staendig neu stylen."""
        lbl = self._lbl_active_fx
        if lbl.text() != text:
            lbl.setText(text)
        if lbl.styleSheet() != stil:
            lbl.setStyleSheet(stil)

    @staticmethod
    def _breite_festhalten(btn: QPushButton, texte) -> None:
        """VCB-47: Mindestbreite eines Umschaltknopfs auf seinen breitesten Zustand
        legen (alle Texte, gedrueckt = fett). Sonst aendert der Knopf beim Umschalten
        seine Breite, die umbrechende Werkzeugleiste bricht in schmalen Fenstern
        anders um, wird eine Zeile hoeher oder niedriger — und die Konsole rutscht."""
        ruhetext, gedrueckt = btn.text(), btn.isChecked()
        alt = btn.blockSignals(True)
        try:
            breite = 0
            for zustand in (False, True):
                btn.setChecked(zustand)
                for text in texte:
                    btn.setText(text)
                    btn.ensurePolished()
                    breite = max(breite, btn.sizeHint().width())
            btn.setText(ruhetext)
            btn.setChecked(gedrueckt)
        finally:
            btn.blockSignals(alt)
        btn.setMinimumWidth(breite + 2)

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
        if self._kiosk and enabled:
            # UI-96: im Kiosk gibt es keinen Bearbeiten-Modus.
            blocker = self._btn_edit.blockSignals(True)
            self._btn_edit.setChecked(False)
            self._btn_edit.blockSignals(blocker)
            enabled = False
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
        if self._kiosk and checked:
            blocker = self._btn_midi_learn.blockSignals(True)
            self._btn_midi_learn.setChecked(False)
            self._btn_midi_learn.blockSignals(blocker)
            return
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
            # VCB-45: Lage/Groesse/Zustand merken. Die drei Ereignisse stossen
            # nur das entprellte Schreiben an; am Umhaengen des Canvas und an
            # der Reihenfolge beim Schliessen aendert das nichts.
            _lage_merker = None

            def _lage_anstossen(self):
                m = self._lage_merker
                if m is not None:
                    m.angestossen()

            def moveEvent(self, event):  # noqa: N802 (Qt-API)
                super().moveEvent(event)
                self._lage_anstossen()

            def resizeEvent(self, event):  # noqa: N802 (Qt-API)
                super().resizeEvent(event)
                self._lage_anstossen()

            def changeEvent(self, event):  # noqa: N802 (Qt-API)
                super().changeEvent(event)
                if event.type() == QEvent.Type.WindowStateChange:
                    self._lage_anstossen()

            def closeEvent(self, event):
                # VCB-45: letzten Stand festhalten, solange das Fenster noch
                # steht (liest nur Lage und Zustand).
                try:
                    if self._lage_merker is not None:
                        self._lage_merker.sichern()
                except Exception as e:
                    print(f"[VC] Popout-Lage nicht gemerkt: {e}")
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

        # Gleiches Verhalten wie im Hauptfenster: auf grosse Fenster mitwachsen,
        # bei kleineren Fenstern dank Canvas-Minimum weiterhin scrollbar.
        pop_scroll = GrowingScrollArea()
        pop_scroll.setStyleSheet("QScrollArea { border:none; background:#0d1117; }")
        # Canvas zuerst aus dem Haupt-Scroll lösen (ohne Löschen), dann übergeben.
        self._main_scroll.takeWidget()
        pop_scroll.setWidget(self._canvas)
        pop_l.addWidget(pop_scroll)

        self._pop_scroll = pop_scroll
        self._popout_window = win
        self._zeige_popout(win)

    def _zeige_popout(self, win):
        """VCB-45: Popout dort oeffnen, wo es zuletzt lag — sonst (mehrere
        Bildschirme, nichts gemerkt) maximiert auf dem anderen Bildschirm.
        Geht dabei etwas schief, oeffnet es wie frueher."""
        try:
            from src.ui.virtualconsole import popout_lage as pl
            paare = pl.lies_bildschirme()
            lage = pl.ziel_lage([b for b, _ in paare], pl.lade_gemerkt(),
                                pl.haupt_index(paare, self))
            win._lage_merker = pl.baue_merker(win, lage, self)
            qscreen = paare[lage.bildschirm][1] if paare else None
            pl.oeffne(win, lage, qscreen)
        except Exception as e:
            print(f"[VC] Popout-Lage nicht wiederhergestellt: {e}")
            win.show()

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _toggle_sidebar(self, checked: bool):
        if self._sidebar is None or self._btn_sidebar is None:
            return          # UI-96: Kiosk — keine Bibliothek
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

    def _verlauf_knopf(self, wiederholen: bool):
        """↶/↷ der Werkzeugleiste. Im Hauptfenster derselbe gemeinsame Verlauf
        wie Strg+Z und Bearbeiten → Rückgängig (UI-93) — ein Knopf, dessen
        Tooltip „Strg+Z“ nennt, darf nichts anderes tun als die Taste. Ohne
        Hauptfenster (eigenes Fenster, Tests) bleibt es der Layout-Verlauf."""
        from src.ui import undo_kuerzel
        try:
            fenster = self.window()
        except RuntimeError:
            fenster = None
        schritt = getattr(fenster, "verlauf_schritt", None)
        if (getattr(fenster, undo_kuerzel.MERKMAL_ZENTRAL, False)
                and callable(schritt)):
            schritt(wiederholen)
            return
        (self._vc_redo if wiederholen else self._vc_undo)()

    def _knopf_rueckgaengig(self):
        self._verlauf_knopf(False)

    def _knopf_wiederholen(self):
        self._verlauf_knopf(True)

    def _vc_undo(self):
        """Letzte VC-Bearbeitung rueckgaengig (Strg+Z / ↶-Knopf)."""
        if self._kiosk:
            return          # UI-96: kein Bearbeitungsverlauf im Kiosk
        if self._canvas_alive():
            self._canvas.undo()

    def _vc_redo(self):
        """Rueckgaengig gemachte VC-Bearbeitung wiederholen (Strg+Y / ↷-Knopf)."""
        if self._kiosk:
            return          # UI-96: kein Bearbeitungsverlauf im Kiosk
        if self._canvas_alive():
            self._canvas.redo()

    def _clear_all(self):
        if self._edit_mode:
            self._canvas._clear()

    def _save(self):
        self._canvas._save()

    def _load(self):
        if self._kiosk:
            return          # UI-96: kein Layout-Import im Kiosk
        self._canvas._load()

    # ── Public serialization ──────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return self._canvas.to_dict()

    def from_dict(self, d: dict):
        # Auswahl loesen, bevor die alten Widgets beim Laden zerstoert werden.
        if self._inspector is not None:
            self._inspector.clear()
        self._canvas.from_dict(d)
