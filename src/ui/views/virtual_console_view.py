"""Virtual Console tab — toolbar + canvas + Bibliothek-Sidebar."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QPushButton,
    QLabel, QSizePolicy, QSplitter, QMessageBox,
)
from PySide6.QtCore import Qt, QEvent, QObject, QPoint, QSize, QTimer

from src.ui.virtualconsole.vc_canvas import VCCanvas
from src.ui.virtualconsole.vc_inspector_panel import VCInspectorPanel
from src.ui.widgets.flow_layout import FlowLayout
from src.ui.weak_slots import weak_slot
from src.ui.virtualconsole.vc_style import touch_aktiv, tz
from src.ui import dialog_hilfe
from src.ui.abbau import abbau_still


# UI-138 (Klick-Test Fund 4): die Leistenknoepfe hatten per eigenem Stylesheet
# 10 px Schrift — auch im Touch-Modus, wo sie 44 px hoch sind. Dort winzig und
# grau. Touch: 12 px, Maus unveraendert 10 px (11 px bleibt 11 px). 13 px
# (Vorschlag des Klick-Tests) schob die Spielbetrieb-Leiste bei 1280 px in eine
# zweite Zeile — und eine Bedienleiste, die live umbricht, verschiebt die Konsole.
TB_SCHRIFT_MAUS = 10
TB_SCHRIFT_TOUCH = 12
# Seitenrand im Touch-Modus: 6 statt 8 px, damit die groessere Schrift die
# Spielbetrieb-Leiste bei 1280 px nicht in eine zweite Zeile schiebt.
TB_RAND_TOUCH = 6


def _tb_schrift() -> int:
    """Schriftgroesse (px) der VC-Werkzeugleiste: Touch 12, Maus 10."""
    return TB_SCHRIFT_TOUCH if touch_aktiv() else TB_SCHRIFT_MAUS


def _tb_css(css: str) -> str:
    """Stylesheet eines Leistenknopfs mit der Leistenschrift (nur im Touch-
    Modus geaendert — mit der Maus bleibt der Text Zeichen fuer Zeichen gleich)."""
    if not touch_aktiv():
        return css
    px = _tb_schrift()
    return (css.replace("font-size:10px", f"font-size:{px}px")
               .replace("font-size:11px", f"font-size:{px}px")
               .replace("padding:0 8px", f"padding:0 {TB_RAND_TOUCH}px"))


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


def _apc_mk2_port(outs) -> str | None:
    """MIDI-19: erster Ausgang eines APC mini mk2 (``None`` = keiner)."""
    for p in outs or ():
        if "apc mini mk2" in str(p).lower():
            return str(p)
    return None


def _apc_auto_erlaubt() -> bool:
    """MIDI-19: Auto-Start der APC-LEDs nur in der echten App (STAB-39) —
    bewusst nicht ``echte_ausgabe_erlaubt``: die Testsuite gibt die Ausgabe
    frei (Schein-Ausgaenge), soll aber nie von selbst ein angestecktes Pult
    ansprechen. Der Knopf bleibt davon unberuehrt.

    Nachbesserung MIDI-19: Eine aus einer Agent-Shell gestartete App (STAB-39:
    ``CLAUDECODE=1`` -> keine echte App) mit bewusst freigegebener Ausgabe
    (``LIGHTOS_ECHTE_AUSGABE=1`` je Befehl, z. B. fuer Robins Gegenprobe am
    Geraet) soll sich wie die echte App verhalten — sonst bliebe genau bei der
    Gegenprobe der Auto-Start aus. Unter pytest gilt die Freigabe nicht
    (conftest setzt sie fuer die Schein-Ausgaenge); Muster lizenz.testlauf."""
    try:
        import os
        import sys
        from src.core.paths import ist_echte_app, echte_ausgabe_erlaubt
        if ist_echte_app():
            return True
        unter_pytest = ("pytest" in sys.modules
                        or "PYTEST_CURRENT_TEST" in os.environ)
        return bool(echte_ausgabe_erlaubt()) and not unter_pytest
    except Exception:
        return False


class _FesteHoehe(QObject):
    """QA-120: haelt die feste Hoehe von Knoepfen gegen ein Fenster-Stylesheet.

    Qt setzt beim Polieren das Minimum aus ``min-height`` + Polsterung + Rand
    des Stylesheets und vergisst dabei ``setFixedHeight``. Poliert wird beim
    ersten Zeigen und bei jedem neuen Stylesheet eines Vorfahren; danach kommt
    ``Show`` bzw. ``StyleChange`` - dort wird die Hoehe neu gesetzt (das
    ``Polish``-Ereignis selbst laeuft VOR dem Polieren)."""

    _EREIGNISSE = (QEvent.Type.Show, QEvent.Type.StyleChange)

    def halten(self, knopf, hoehe: int) -> None:
        knopf.setProperty("_qa120_hoehe", int(hoehe))
        knopf.installEventFilter(self)

    def eventFilter(self, obj, event):  # noqa: N802 (Qt-API)
        if event.type() in self._EREIGNISSE:
            h = obj.property("_qa120_hoehe")
            if h and (obj.minimumHeight() != h or obj.maximumHeight() != h):
                obj.setFixedHeight(h)
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  VirtualConsoleView
# ─────────────────────────────────────────────────────────────────────────────

def _alle_loeschen_box(parent, anzahl: int) -> QMessageBox:
    """UI-137: Rueckfrage vor „Alle löschen“ — Vorgabe und Escape „Abbrechen“,
    im Touch-Modus Knoepfe >= 44 px hoch. Nicht ausgefuehrt (fuer Tests)."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Alle löschen")
    box.setText(f"Alle {anzahl} Elemente der Virtuellen Konsole löschen?")
    box.setInformativeText("Mit Strg+Z lässt sich das rückgängig machen.")
    loeschen = box.addButton("Löschen", QMessageBox.ButtonRole.DestructiveRole)
    abbrechen = box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
    if touch_aktiv():
        for k in (loeschen, abbrechen):
            k.setMinimumHeight(44)
    box.setDefaultButton(abbrechen)
    box.setEscapeButton(abbrechen)
    box._ui137_loeschen = loeschen
    return box


def _frage_alle_loeschen(parent, anzahl: int) -> bool:
    """True nur, wenn ausdruecklich „Löschen“ gewaehlt wurde."""
    box = _alle_loeschen_box(parent, anzahl)
    with dialog_hilfe.offen(box):
        box.exec()
        return box.clickedButton() is box._ui137_loeschen


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
        # MIDI-19: Zustand des „APC LEDs"-Knopfs. ``_apc_nutzer_aus`` = Robin
        # hat die LEDs bewusst ausgeschaltet (dann kein Auto-Start mehr);
        # ``_apc_auto_wechsel`` = der Knopf wird gerade vom Programm gestellt
        # (Auto-Start/Geraet weg/Fehlschlag), nicht von einem Druck.
        self._apc_nutzer_aus = False
        self._apc_auto_wechsel = False
        self._apc_letzter_wechsel: float | None = None
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
        # UI-121 B-14: im Touch-Modus 8 px Abstand zwischen den Knoepfen
        # (vorher 6 px ≈ 1,6 mm), mit der Maus wie bisher.
        _abstand = 8 if touch_aktiv() else 6
        tb_layout = FlowLayout(toolbar, margin=0, h_spacing=_abstand, v_spacing=_abstand - 2)
        tb_layout.setContentsMargins(8, 3, 8, 3)

        self._btn_edit = QPushButton("Bearbeiten")
        self._btn_edit.setCheckable(True)
        self._btn_edit.setChecked(False)
        # UI-138: im Touch-Modus 96 statt tz(90)=117 px — der Platz geht an die
        # groessere Leistenschrift (die Leiste bleibt bei 1280 px einzeilig).
        self._btn_edit.setFixedSize(96 if touch_aktiv() else tz(90),
                                    max(28, self._tb_hoehe()))
        self._btn_edit.setStyleSheet(_tb_css("""
            QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                          border-radius:3px; font-size:11px; }
            QPushButton:checked { background:#0d4f8b; color:#58d68d; border-color:#1f6feb; }
            QPushButton:hover { background:#30363d; }
        """))
        self._btn_edit.toggled.connect(self._toggle_edit)
        tb_layout.addWidget(self._btn_edit)
        if self._kiosk:
            self._btn_edit.setEnabled(False)
            self._btn_edit.setVisible(False)

        self._btn_snap = QPushButton("⊞ Raster")
        self._btn_snap.setCheckable(True)
        self._btn_snap.setChecked(False)
        self._btn_snap.setFixedHeight(self._tb_hoehe())
        self._btn_snap.setToolTip(
            "Snap auf Grid — Widgets rasten beim Verschieben und Skalieren\n"
            "am Raster ein (Grid-Größe: 8 px)"
        )
        self._btn_snap.setStyleSheet(_tb_css("""
            QPushButton { background:#21262d; color:#8b949e; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:checked { background:#0d4f8b; color:#58d68d; border-color:#1f6feb; }
            QPushButton:hover:!disabled { background:#30363d; color:#e6edf3; }
            QPushButton:disabled { color:#484f58; border-color:#21262d; }
        """))
        self._btn_snap.setProperty("edit_only", True)
        self._btn_snap.setVisible(False)
        self._btn_snap.toggled.connect(self._toggle_snap)
        tb_layout.addWidget(self._btn_snap)

        # Widget quick-add buttons
        widget_buttons = [
            ("Button",    "VCButton"),
            ("Fader",     "VCSlider"),
            ("XY Pad",    "VCXYPad"),
            ("Raum-Pad",  "VCRaumPad"),    # UI-127
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
            btn.setFixedHeight(self._tb_hoehe())
            btn.setStyleSheet(_tb_css("""
                QPushButton { background:#21262d; color:#8b949e; border:1px solid #30363d;
                              border-radius:3px; font-size:10px; padding:0 8px; }
                QPushButton:hover { background:#30363d; color:#e6edf3; }
                QPushButton:disabled { color:#484f58; }
            """))
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
            ub.setFixedHeight(self._tb_hoehe())
            # UI-121 B-14: ↶/↷ waren 30 px schmal — jetzt ≥ 40 px (Touch 44).
            ub.setMinimumWidth(44 if touch_aktiv() else 40)
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
        # UI-126: Mehrfachauswahl. „Mehrfach" (nur im Touch-Modus sichtbar,
        # wie UI-116): jeder Tipp nimmt ein Widget dazu/heraus — die Maus hat
        # Strg/Umschalt-Klick und den Auswahlrahmen. „Ausrichten" wirkt auf
        # die Auswahl (ab zwei Elementen).
        _knopf_stil = _tb_css("""
            QPushButton { background:#21262d; color:#8b949e; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:checked { background:#0d4f8b; color:#58d68d; border-color:#1f6feb; }
            QPushButton:hover:!disabled { background:#30363d; color:#e6edf3; }
            QPushButton:disabled { color:#484f58; }
        """)
        self._btn_mehrfach = QPushButton("Mehrfach")
        self._btn_mehrfach.setObjectName("vc_mehrfach")
        self._btn_mehrfach.setCheckable(True)
        self._btn_mehrfach.setFixedHeight(max(44, self._tb_hoehe()) if touch_aktiv()
                                          else self._tb_hoehe())
        self._btn_mehrfach.setMinimumWidth(44)
        self._btn_mehrfach.setToolTip(
            "Mehrfachauswahl am Finger: eingeschaltet nimmt jeder Tipp ein "
            "Element dazu oder heraus. Gewählte zusammen ziehen verschiebt alle.")
        self._btn_mehrfach.setStyleSheet(_knopf_stil)
        self._btn_mehrfach.setProperty("edit_only", True)
        self._btn_mehrfach.setProperty("nur_touch", True)
        self._btn_mehrfach.setVisible(False)
        self._btn_mehrfach.toggled.connect(self._toggle_mehrfach)
        tb_layout.addWidget(self._btn_mehrfach)

        self._btn_ausrichten = QPushButton("Ausrichten ▾")
        self._btn_ausrichten.setObjectName("vc_ausrichten")
        self._btn_ausrichten.setFixedHeight(self._tb_hoehe())
        self._btn_ausrichten.setToolTip(
            "Gewählte Elemente ausrichten (links/rechts/oben/unten), mit gleichen "
            "Abständen verteilen oder gemeinsam löschen.\nMehrere wählen: "
            "Strg/Umschalt-Klick, Rahmen auf freier Fläche aufziehen oder am "
            "Finger „Mehrfach“.")
        self._btn_ausrichten.setStyleSheet(_knopf_stil)
        self._btn_ausrichten.setEnabled(False)
        self._btn_ausrichten.setProperty("edit_only", True)
        self._btn_ausrichten.setVisible(False)
        self._btn_ausrichten.clicked.connect(self._ausrichten_zeigen)
        # UI-138: der Zaehler „3 gewählt" steht HIER (feste Stelle, verdeckt
        # nichts) statt auf der Flaeche. Breite fuer den laengsten Text fest
        # vorhalten, sonst bricht die Leiste beim Waehlen anders um (VCB-47).
        self._breite_festhalten(self._btn_ausrichten,
                                ("Ausrichten ▾", self._ausrichten_text(88)))
        tb_layout.addWidget(self._btn_ausrichten)

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
        self._btn_midi_learn.setFixedHeight(self._tb_hoehe())
        self._btn_midi_learn.setToolTip(
            "MIDI-Patch-Modus: Zuerst einen VC-Button anklicken,\n"
            "dann die gewünschte MIDI-Taste drücken."
        )
        self._btn_midi_learn.setStyleSheet(_tb_css("""
            QPushButton { background:#21262d; color:#ff8800; border:1px solid #ff8800;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:checked { background:#ff8800; color:#000; font-weight:bold; }
            QPushButton:hover { background:#30363d; }
        """))
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
        self._btn_apc_leds.setFixedHeight(self._tb_hoehe())
        self._btn_apc_leds.setToolTip(
            "APC Mini LED-Feedback aktivieren/deaktivieren\n"
            "Grün = aktiv, Grün blinkend = gestoppt, Rot = Flash, Gelb = aktuelle Page\n"
            "APC mini mk2: startet von selbst, sobald es erkannt ist; die Seitentaste\n"
            "der aktiven Seite leuchtet"
        )
        self._btn_apc_leds.setStyleSheet(_tb_css("""
            QPushButton { background:#21262d; color:#00cc66; border:1px solid #00cc66;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:checked { background:#00cc66; color:#000; font-weight:bold; }
            QPushButton:hover { background:#30363d; }
        """))
        self._btn_apc_leds.toggled.connect(self._toggle_apc_leds)
        self._breite_festhalten(self._btn_apc_leds, (self._btn_apc_leds.text(),))
        tb_layout.addWidget(self._btn_apc_leds)

        # Touch-Lock (Display-only): nur Anzeige, keine Steuerung per Touchscreen
        self._btn_touch_lock = QPushButton("🔒 Touch-Lock")
        self._btn_touch_lock.setCheckable(True)
        self._btn_touch_lock.setFixedHeight(self._tb_hoehe())
        self._btn_touch_lock.setToolTip(
            "Display-only: Touchscreen/Maus steuert nicht mehr (nur Anzeige).\n"
            "APC mini / MIDI steuern weiterhin. Schützt vor versehentlichem Antippen."
        )
        self._btn_touch_lock.setStyleSheet(_tb_css("""
            QPushButton { background:#21262d; color:#ffb000; border:1px solid #ffb000;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:checked { background:#ffb000; color:#000; font-weight:bold; }
            QPushButton:hover { background:#30363d; }
        """))
        self._btn_touch_lock.toggled.connect(self._toggle_touch_lock)
        self._breite_festhalten(self._btn_touch_lock, ("🔒 Touch-Lock", "🔒 Gesperrt"))
        tb_layout.addWidget(self._btn_touch_lock)

        # Soft-Takeover / „Pickup": für nicht-motorisierte Controller (APC mini & Co.).
        # Nach einem Seiten-/Bankwechsel übernimmt ein Fader erst, wenn der physische
        # Fader den aktuellen VC-Wert einmal durchfahren hat → keine Wertsprünge.
        self._btn_pickup = QPushButton("🎚 Pickup")
        self._btn_pickup.setCheckable(True)
        self._btn_pickup.setFixedHeight(self._tb_hoehe())
        self._btn_pickup.setToolTip(
            "Soft-Takeover für nicht-motorisierte Fader (APC mini …):\n"
            "Nach einem Seitenwechsel springt der Wert nicht — der Fader übernimmt\n"
            "erst, wenn er den aktuellen VC-Wert einmal durchfahren hat.\n"
            "Ein gelber Pfeil zeigt, wohin der Fader bewegt werden muss."
        )
        self._btn_pickup.setStyleSheet(_tb_css("""
            QPushButton { background:#21262d; color:#ffb000; border:1px solid #ffb000;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:checked { background:#ffb000; color:#000; font-weight:bold; }
            QPushButton:hover { background:#30363d; }
        """))
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
        # UI-121 B-05: Bank-Knoepfe waren 26×26 px (6,9 mm breit) — der Bank-
        # wechsel ist live haeufig. Maus: 44 px breit (Hoehe der Leiste),
        # Touch: 56×56 px. Das Etikett dazwischen ist antippbar (Bank-Auswahl).
        _bank_w, _bank_h = (56, 56) if touch_aktiv() else (44, self._tb_hoehe())
        self._btn_bank_prev = QPushButton("◀")
        self._btn_bank_prev.setFixedSize(_bank_w, _bank_h)
        self._btn_bank_prev.setToolTip("Vorherige Bank (Pad-/Widget-Seite)")
        self._btn_bank_prev.setStyleSheet(_bank_btn_css)
        self._btn_bank_prev.clicked.connect(weak_slot(self._step_bank, -1))
        tb_layout.addWidget(self._btn_bank_prev)

        # UI-121 B-05: Etikett ist ein flacher Knopf — Antippen oeffnet die
        # Bank-Auswahl (direkt zu Bank 1–10 statt mehrfach ◀/▶).
        self._lbl_bank = QPushButton("Bank 1")
        self._lbl_bank.setFlat(True)
        self._lbl_bank.setFixedWidth(72 if touch_aktiv() else 54)
        self._lbl_bank.setFixedHeight(_bank_h)
        self._lbl_bank.setToolTip("Bank waehlen (Pad-/Widget-Seite)")
        self._lbl_bank.setStyleSheet(_tb_css(
            "QPushButton { color:#58a6ff; font-size:11px; font-weight:bold;"
            " background:transparent; border:none; padding:0; }"
            "QPushButton:hover { color:#e6edf3; }"
        ))
        self._lbl_bank.clicked.connect(weak_slot(self._bank_menue))
        tb_layout.addWidget(self._lbl_bank)

        self._btn_bank_next = QPushButton("▶")
        self._btn_bank_next.setFixedSize(_bank_w, _bank_h)
        self._btn_bank_next.setToolTip("Nächste Bank (Pad-/Widget-Seite)")
        self._btn_bank_next.setStyleSheet(_bank_btn_css)
        self._btn_bank_next.clicked.connect(weak_slot(self._step_bank, 1))
        tb_layout.addWidget(self._btn_bank_next)

        # Popout Button
        self._btn_popout = QPushButton("⧉ Popout")
        self._btn_popout.setFixedHeight(self._tb_hoehe())
        self._btn_popout.setToolTip("Virtual Console in eigenem Fenster öffnen")
        self._btn_popout.setStyleSheet(_tb_css("""
            QPushButton { background:#21262d; color:#8b949e; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:hover { background:#30363d; color:#e6edf3; }
        """))
        self._btn_popout.clicked.connect(self._popout_canvas)
        tb_layout.addWidget(self._btn_popout)

        btn_clear = QPushButton("Alle löschen")
        btn_clear.setFixedHeight(self._tb_hoehe())
        btn_clear.setStyleSheet(_tb_css("""
            QPushButton { background:#21262d; color:#f85149; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px;
                          margin:0 10px; }
            QPushButton:hover { background:#30363d; }
        """))
        # UI-137: „margin:0 10px“ setzt den Knopf von den Nachbarn ab (die
        # FlowLayout-Leiste kennt kein addSpacing); verschwindet mit ihm.
        btn_clear.clicked.connect(self._clear_all)
        btn_clear.setProperty("edit_only", True)
        btn_clear.setVisible(False)
        tb_layout.addWidget(btn_clear)

        btn_save = QPushButton("Canvas exportieren…")
        btn_save.setFixedHeight(self._tb_hoehe())
        btn_save.setToolTip("Nur dieses VC-Layout als separate JSON-Datei exportieren "
                            "(unabhängig vom Show-Speichern unter Datei → Speichern).")
        btn_save.setStyleSheet(_tb_css("""
            QPushButton { background:#21262d; color:#3fb950; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:hover { background:#30363d; }
        """))
        btn_save.clicked.connect(self._save)
        tb_layout.addWidget(btn_save)

        btn_load = QPushButton("Canvas importieren…")
        btn_load.setFixedHeight(self._tb_hoehe())
        btn_load.setToolTip("Ein zuvor exportiertes VC-Layout (JSON) in dieses Canvas laden.")
        btn_load.setStyleSheet(_tb_css("""
            QPushButton { background:#21262d; color:#58a6ff; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:hover { background:#30363d; }
        """))
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
        self._btn_inspector.setFixedHeight(self._tb_hoehe())
        self._btn_inspector.setProperty("edit_only", True)
        self._btn_inspector.setVisible(False)
        self._btn_inspector.setStyleSheet(_tb_css("""
            QPushButton { background:#21262d; color:#58d68d; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:checked { background:#0d4f8b; color:#58d68d; border-color:#1f6feb; }
            QPushButton:hover { background:#30363d; }
        """))
        self._btn_inspector.toggled.connect(self._toggle_inspector)
        tb_layout.addWidget(self._btn_inspector)

        # WEB-10: Seitenleiste „Handy-Konsole" ein-/ausblenden. Immer sichtbar:
        # im Betrieb ist die Leiste eine Vorschau (und der Schalter „an/aus"
        # bleibt ein Griff), gebaut wird im Bearbeiten-Modus. Ersetzt den
        # vorlaeufigen Knopf „Handy füllen" aus WEB-09 — „Automatisch füllen"
        # steht jetzt in der Leiste.
        self._btn_handy = QPushButton("📱 Handy-Konsole")
        self._btn_handy.setObjectName("vc_handy_konsole")
        self._btn_handy.setCheckable(True)
        self._btn_handy.setChecked(False)
        self._btn_handy.setFixedHeight(self._tb_hoehe())
        self._btn_handy.setToolTip(
            "Seitenleiste „Handy-Konsole“: hier baust du, was am Handy zu sehen "
            "ist.\nElemente im Bearbeiten-Modus hineinziehen oder per Rechtsklick "
            "→ „Auf Handy-Konsole legen“.")
        self._btn_handy.setStyleSheet(_tb_css("""
            QPushButton { background:#21262d; color:#7ee787; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:checked { background:#12351d; color:#7ee787; border-color:#2ea043; }
            QPushButton:hover { background:#30363d; }
        """))
        self._btn_handy.toggled.connect(self._toggle_handy_leiste)
        tb_layout.addWidget(self._btn_handy)
        if self._kiosk:
            # UI-96: im Kiosk keine Bearbeitungswege — die Leiste baut
            # Handy-Seiten und schaltet den Fernzugriff, beides gehoert nicht
            # an die reine Bedien-Konsole.
            self._btn_handy.setEnabled(False)
            self._btn_handy.setVisible(False)

        layout.addWidget(toolbar)
        self._toolbar_widget = toolbar
        self._leiste_touch_hoehe(toolbar)

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
        # VCB-50: im selben Statustakt die VC-Fader im Modus „Playback
        # (Executor)" auf einen Pegel von aussen ziehen — kein eigener Timer.
        self._active_fx_timer.timeout.connect(self._vc_pegel_nachziehen)
        self._active_fx_timer.start()

        # ── Splitter: Canvas links, Sidebar rechts ────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        # UI-119 (B-10): im Touch-Modus breiter Griff mit Marke (Touch-QSS);
        # mit der Maus bleibt der schmale 2-px-Strich.
        try:
            from src.ui.touch_keyboard import is_touch_mode, SPLITTER_GRIFF
            _griff = SPLITTER_GRIFF if is_touch_mode() else 2
        except Exception:
            _griff = 2
        splitter.setStyleSheet(
            "QSplitter::handle { background:#30363d; width:%dpx; }" % _griff)

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
        self._canvas.geloeste_baenke_geaendert.connect(
            weak_slot(self._bank_loesen_knopf_auffrischen))
        self._canvas.widget_selected.connect(self._on_canvas_widget_selected)
        self._canvas.auswahl_geaendert.connect(self._on_canvas_auswahl)   # UI-126
        self._on_bank_changed(self._canvas.active_bank)
        self._main_scroll.setWidget(self._canvas)
        # WEB-08: die Konsole fuer die Fernausloesung anmelden. Die Bruecke
        # haengt als Kind am Canvas (stirbt mit ihm) und reicht Aufrufe des
        # Web-Threads in den UI-Thread. Ob sie etwas ausfuehren darf,
        # entscheidet die Einstellung in ``src.web.vc_remote`` — Standard AUS.
        self._fernbedienung = None
        try:
            from src.ui.virtualconsole.vc_fernbedienung import VCFernbedienung
            from src.web import vc_remote
            self._fernbedienung = VCFernbedienung(self._canvas)
            # Kein ``destroyed``-Lambda zum Abmelden (STAB-09: so eine Connection
            # pinnt ihre Fangvariablen GC-unsichtbar). Eine Bruecke, deren
            # Konsole abgebaut ist, antwortet von selbst mit „keine Konsole".
            vc_remote.registriere(self._fernbedienung)
        except Exception as e:
            print(f"[virtual_console_view] ERROR: Fernbedienung nicht angemeldet: {e}")
        splitter.addWidget(self._main_scroll)

        # WEB-10: Seitenleiste „Handy-Konsole" — direkt neben der Konsole, damit
        # der Weg beim Hineinziehen kurz ist. UI-96: im Kiosk gar nicht erst
        # gebaut (sie baut Handy-Seiten und schaltet den Fernzugriff).
        self._handy_leiste = None
        if not self._kiosk:
            from src.ui.virtualconsole.vc_handy_leiste import HandyKonsolenLeiste
            self._handy_leiste = HandyKonsolenLeiste(self._canvas)
            self._handy_leiste.setVisible(False)
            self._handy_leiste.verbinden_angefragt.connect(self._handy_verbinden)
            # Rechtsklick „Auf Handy-Konsole legen" bei ausgeblendeter Leiste: sie
            # erscheint, damit man sieht, wo das Element gelandet ist.
            self._canvas.handy_abgelegt.connect(self._handy_abgelegt)
            splitter.addWidget(self._handy_leiste)

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
        # (Spalten ueber indexOf: im Kiosk fehlen Handy-Leiste und Sidebar, UI-96)
        splitter.setStretchFactor(0, 4)
        if self._handy_leiste is not None:  # Handy-Konsole: feste Breite
            i = splitter.indexOf(self._handy_leiste)
            splitter.setStretchFactor(i, 0)
            splitter.setCollapsible(i, False)
        i = splitter.indexOf(self._inspector)
        splitter.setStretchFactor(i, 0)
        splitter.setCollapsible(i, True)
        if self._sidebar is not None:
            splitter.setStretchFactor(splitter.indexOf(self._sidebar), 1)
        self._splitter = splitter

        # Stretch=1: der Canvas-/Sidebar-Splitter bekommt den gesamten
        # verbleibenden vertikalen Platz (Toolbar + Statuszeile sind fix).
        layout.addWidget(splitter, 1)

    def _sidebar_knopf_bauen(self, tb_layout) -> None:
        """Knopf „◀ Bibliothek" (ausserhalb des Kiosk-Modus)."""
        self._btn_sidebar = QPushButton("◀ Bibliothek")
        self._btn_sidebar.setCheckable(True)
        self._btn_sidebar.setChecked(True)
        self._btn_sidebar.setFixedHeight(self._tb_hoehe())
        self._btn_sidebar.setStyleSheet(_tb_css("""
            QPushButton { background:#21262d; color:#ffd700; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:checked { background:#2a3344; color:#ffd700; }
            QPushButton:hover { background:#30363d; }
        """))
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

    @abbau_still
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
            # UI-129: ebenso, wenn sich die Menge der live bearbeiteten Effekte
            # aendert (Sternchen an Taste/Fader/Encoder). Gerechnet wird hier im
            # vorhandenen Statustakt — kein eigener Timer, neu gezeichnet nur bei
            # Aenderung.
            try:
                from src.core.engine import effect_live
                live_ids = effect_live.live_editiert_ids()
            except Exception:
                live_ids = None
            if (running_ids != getattr(self, "_last_running_ids", None)
                    or modify_sig != getattr(self, "_last_modify_sig", None)
                    or live_ids != getattr(self, "_last_live_ids", None)):
                self._last_running_ids = running_ids
                self._last_modify_sig = modify_sig
                self._last_live_ids = live_ids
                if self._canvas_alive():
                    from src.ui.virtualconsole.vc_button import VCButton
                    from src.ui.virtualconsole.vc_slider import VCSlider
                    from src.ui.virtualconsole.vc_encoder import VCEncoder
                    for cls in (VCButton, VCSlider, VCEncoder):
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

    def _vc_pegel_nachziehen(self):
        """VCB-50: VC-Fader im Modus PLAYBACK zeigen einen Executor-Pegel, der
        von aussen kam (Web/OSC/MIDI/Executor-Leiste). Nur Anzeige, Details in
        ``VCSlider.pegel_nachziehen``; im Bearbeiten-Modus nichts."""
        if not self._canvas_alive():
            return
        canvas = self._canvas
        if getattr(canvas, "_edit_mode", False):
            return
        try:
            from src.ui.virtualconsole.vc_slider import SliderMode, VCSlider
            fader = canvas.findChildren(VCSlider)
        except RuntimeError:
            return
        for w in fader:
            try:
                if w.mode == SliderMode.PLAYBACK:
                    w.pegel_nachziehen()
            except Exception as e:
                print(f"[VC] Pegel nachziehen: {type(e).__name__}: {e}")

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
                # UI-126: „Mehrfach" nur im Touch-Modus (Maus: Strg/Umschalt)
                btn.setVisible(enabled and (not btn.property("nur_touch")
                                            or touch_aktiv()))
        if not enabled:
            self._btn_mehrfach.setChecked(False)
            self._btn_ausrichten.setEnabled(False)
            self._btn_ausrichten.setText(self._ausrichten_text(0))
        # Inspector-Panel folgt dem Edit-Modus; beim Verlassen Auswahl loesen.
        if self._inspector is not None:
            if enabled:
                self._inspector.setVisible(self._btn_inspector.isChecked())
            else:
                self._inspector.clear()
                self._inspector.setVisible(False)
        # WEB-10: die Handy-Seitenleiste ist nur im Bearbeiten-Modus bedienbar.
        if getattr(self, "_handy_leiste", None) is not None:
            self._handy_leiste.set_edit_mode(enabled)

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

    def _apc_knopf_setzen(self, an: bool) -> None:
        """Knopf vom Programm aus stellen — mit Signal (startet/stoppt), aber
        ohne Prell-Sperre und ohne als Robins Entscheidung zu zaehlen."""
        alt = self._apc_auto_wechsel
        self._apc_auto_wechsel = True
        try:
            self._btn_apc_leds.setChecked(bool(an))
        finally:
            self._apc_auto_wechsel = alt

    def _apc_knopf_still(self, an: bool) -> None:
        """Knopf-Anzeige korrigieren, ohne den Slot erneut auszuloesen."""
        alt = self._btn_apc_leds.blockSignals(True)
        try:
            self._btn_apc_leds.setChecked(bool(an))
        finally:
            self._btn_apc_leds.blockSignals(alt)

    def _toggle_apc_leds(self, checked: bool):
        if not self._apc_auto_wechsel:
            # MIDI-19 (2): ein Druck = genau ein Umschalten. Am Geraet kam auf
            # einen Druck an → aus → an (Log: gestartet, 0,12 s spaeter
            # geschlossen, 0,6 s spaeter wieder gestartet). Ein zweites
            # Umschalten innerhalb des Doppelklick-Fensters ist dasselbe
            # Antippen (Doppeltippen/Prellen am Finger kommt beim Knopf als
            # Doppelklick an, und QPushButton schaltet darauf ein zweites Mal
            # um) — es wird verworfen und der Knopf zurueckgestellt.
            import time
            from PySide6.QtWidgets import QApplication
            jetzt = time.monotonic()
            fenster = QApplication.styleHints().mouseDoubleClickInterval() / 1000.0
            letzter = self._apc_letzter_wechsel
            if letzter is not None and (jetzt - letzter) < fenster:
                self._apc_knopf_still(not checked)
                print("[VC] APC LEDs: zweites Umschalten im Doppelklick-Fenster ignoriert.")
                return
            self._apc_letzter_wechsel = jetzt
            self._apc_nutzer_aus = not checked
        if checked:
            if self._apc_feedback is not None:
                return          # laeuft schon — nicht ein zweites Mal oeffnen
            try:
                from src.core.app_state import get_state
                from src.core.midi.midi_manager import get_midi_manager
                outs = get_midi_manager().list_outputs()
                mk2 = _apc_mk2_port(outs)
                if mk2 is not None:
                    # mk2 nutzt RGB + spiegelt die VC-Button-Zustaende.
                    # MIDI-19: nur „APC mini mk2" zaehlt — „APC Key 25 mk2" oder
                    # „APC40 mkII" sind andere Geraete (frueher reichte „mk2").
                    from src.core.midi.apc_mk2_feedback import ApcMk2Feedback
                    self._apc_feedback = ApcMk2Feedback(self._canvas,
                                                        port_hint="APC mini mk2")
                else:
                    from src.core.midi.apc_mini_feedback import APCMiniFeedback
                    self._apc_feedback = APCMiniFeedback()
                if self._apc_feedback.is_connected:
                    self._apc_feedback.attach(get_state())
                else:
                    self._apc_feedback = None
                    self._apc_knopf_still(False)
            except Exception as e:
                print(f"[VC] APC LEDs Fehler: {e}")
                self._apc_feedback = None
                self._apc_knopf_still(False)
        else:
            if self._apc_feedback:
                self._apc_feedback.close()
                self._apc_feedback = None

    def apc_leds_automatisch(self) -> None:
        """MIDI-19 (1): LED-Rueckmeldung fuer ein erkanntes APC mini mk2 von
        selbst starten — beim Start und nach spaeterem Einstecken.

        Ruft das Hauptfenster aus seinem MIDI-Auto-Connect (800 ms nach dem
        Start, dann alle 4 s). Vorher oeffnete nur der Knopf „APC LEDs" den
        Ausgang; der Auto-Connect oeffnete allein die EINGAENGE — daher im Log
        „MIDI Ausgang: -" und dunkle LEDs, obwohl der APC verbunden war.

        Regeln: kein Auto-Start, wenn Robin die LEDs bewusst ausgeschaltet hat;
        verschwindet das Geraet, endet das Feedback (Knopf aus, nicht als
        Robins Entscheidung), damit es beim Wiedereinstecken neu anlaeuft.
        Nur in der echten App (STAB-39: Tests/Probelaeufe senden nichts).
        """
        if not _apc_auto_erlaubt():
            return
        try:
            from src.core.midi.midi_manager import get_midi_manager
            outs = get_midi_manager().list_outputs()
        except Exception as e:
            print(f"[VC] APC LEDs automatisch: {e}")
            return
        port = _apc_mk2_port(outs)
        fb = self._apc_feedback
        if fb is None:
            if port is not None and not self._apc_nutzer_aus:
                print(f"[VC] APC mini mk2 erkannt ({port}) — LED-Feedback startet.")
                self._apc_knopf_setzen(True)
            return
        try:
            from src.core.midi.apc_mk2_feedback import ApcMk2Feedback
        except Exception:
            return
        if port is None and isinstance(fb, ApcMk2Feedback):
            print("[VC] APC mini mk2 nicht mehr da — LED-Feedback beendet.")
            self._apc_knopf_setzen(False)

    # ── Bank/Page ──────────────────────────────────────────────────────────────

    def _tb_hoehe(self) -> int:
        """UI-121 B-14: Hoehe der Werkzeugleisten-Knoepfe — Touch 44 px,
        Maus wie bisher 26 px."""
        return 44 if touch_aktiv() else 26

    def _leiste_touch_hoehe(self, leiste) -> None:
        """QA-118 (e): im Hauptfenster behalten die Leistenknoepfe ihre Hoehe.

        Das Touch-Stylesheet des Hauptfensters setzt ``QPushButton
        { min-height: 38px; padding: 6px 14px }``. Beim Polieren ueberschreibt
        das das Minimum aus ``setFixedHeight`` — gemessen in der echten App
        (250 %): 38 px + 1 px Rand oben und unten = 40 statt 44. QA-120: eine
        eigene ``min-height`` im Knopf-Stil half nur ohne Polsterung (Bank ◀/▶
        blieben 52 statt 56, das Bank-Etikett 38, „Bearbeiten“ wurde 56 statt
        44). Deshalb setzt ``_FesteHoehe`` die Hoehe nach jedem Polieren neu."""
        if not touch_aktiv():
            return
        halter = _FesteHoehe(leiste)
        for b in leiste.findChildren(QPushButton):
            if b.minimumHeight() == b.maximumHeight():
                halter.halten(b, b.maximumHeight())

    def _bank_menue(self):
        """UI-121 B-05: Bank-Etikett angetippt — Bank direkt waehlen."""
        from PySide6.QtWidgets import QMenu
        menue = QMenu(self)
        aktiv = self._canvas.active_bank
        for b in range(10):
            act = menue.addAction(f"Bank {b + 1}")
            act.setCheckable(True)
            act.setChecked(b == aktiv)
            act.triggered.connect(weak_slot(self._set_bank, b))
        # VCB-45 Schritt 3: die gezeigte Bank als eigenes Fenster loesen bzw.
        # wieder andocken. Bewusst im Bank-Menue statt als eigener Knopf: die
        # Spielbetrieb-Leiste bleibt bei 1280 px einzeilig (UI-138).
        menue.addSeparator()
        self._bank_loesen_aktion = menue.addAction(self._bank_loesen_text())
        self._bank_loesen_aktion.setEnabled(not self._edit_mode)
        self._bank_loesen_aktion.triggered.connect(
            weak_slot(self._bank_loesen_umschalten))
        self._bank_menue_offen = menue          # fuer Tests greifbar
        menue.popup(self._lbl_bank.mapToGlobal(self._lbl_bank.rect().bottomLeft()))

    def _step_bank(self, delta: int):
        self._set_bank(self._canvas.active_bank + int(delta))

    def _set_bank(self, target: int, *_):
        target = max(0, min(9, int(target)))
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
        self._bank_loesen_knopf_auffrischen()   # VCB-45: Marke „geloest"

    # ── VCB-45: Bank loesen / andocken ────────────────────────────────────────

    def _bank_loesen_text(self) -> str:
        if not self._canvas_alive():
            return ""
        b = self._canvas.active_bank
        if self._canvas.bank_fenster(b) is not None:
            return f"⇱ Bank {b + 1} andocken"
        return f"⇲ Bank {b + 1} lösen (eigenes Fenster)"

    def _bank_loesen_knopf_auffrischen(self, *_):
        """Tooltip des Bank-Etiketts nennt, ob die gezeigte Bank geloest ist
        (der Text bleibt — das Etikett hat eine feste Breite)."""
        if not self._canvas_alive():
            return
        b = self._canvas.active_bank
        if self._canvas.bank_fenster(b) is not None:
            self._lbl_bank.setToolTip(
                f"Bank {b + 1} ist gelöst (eigenes Fenster). Antippen: Bank "
                "wählen oder andocken")
        else:
            self._lbl_bank.setToolTip(
                "Bank waehlen (Pad-/Widget-Seite) oder als eigenes Fenster lösen")

    def _bank_loesen_umschalten(self, *_):
        if not self._canvas_alive():
            return
        cv = self._canvas
        b = cv.active_bank
        if cv.bank_fenster(b) is not None:
            cv.bank_andocken(b)
        else:
            cv.bank_loesen(b, haupt=self)
        self._bank_loesen_knopf_auffrischen()

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

    # ── UI-126: Mehrfachauswahl ──────────────────────────────────────────────

    def _toggle_mehrfach(self, an: bool):
        self._btn_mehrfach.setText("Mehrfach ✓" if an else "Mehrfach")
        if self._canvas_alive():
            self._canvas.set_mehrfach_modus(an)

    def _on_canvas_auswahl(self, widgets):
        """Auswahl der Canvas geaendert: „Ausrichten" ab zwei Elementen;
        der Inspector zeigt mehrere als Mehrfachauswahl."""
        n = len(widgets)
        self._btn_ausrichten.setEnabled(self._edit_mode and n > 1)
        self._btn_ausrichten.setText(self._ausrichten_text(n))
        if (n > 1 and self._inspector is not None and self._edit_mode
                and self._btn_inspector.isChecked()):
            self._inspector.bind_mehrfach(widgets, self._canvas)

    @staticmethod
    def _ausrichten_text(n: int) -> str:
        """UI-138: Beschriftung von „Ausrichten" mit dem Auswahl-Zaehler."""
        return f"Ausrichten · {n} gewählt ▾" if n > 1 else "Ausrichten ▾"

    def ausrichten_menue(self):
        """Das Menue des Knopfs „Ausrichten" (gebaut, nicht gezeigt)."""
        from PySide6.QtWidgets import QMenu
        menue = QMenu(self._btn_ausrichten)
        self._canvas.auswahl_menue_fuellen(menue)
        return menue

    def _ausrichten_zeigen(self):
        if not self._edit_mode or not self._canvas_alive():
            return
        menue = self.ausrichten_menue()
        menue.exec(self._btn_ausrichten.mapToGlobal(
            QPoint(0, self._btn_ausrichten.height())))
        menue.deleteLater()

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
        """„Alle löschen“ (Bearbeiten-Leiste). UI-137: erst Rueckfrage, dann
        ein Rueckgaengig-Stand (Strg+Z holt alles zurueck). ``_clear`` selbst
        bleibt ohne Undo — es wird auch vom Laden/Undo benutzt."""
        if not self._edit_mode:
            return
        from src.ui.virtualconsole.vc_widget import VCWidget
        canvas = self._canvas
        anzahl = len(canvas.findChildren(
            VCWidget, options=Qt.FindChildOption.FindDirectChildrenOnly))
        if anzahl == 0:
            return
        if not _frage_alle_loeschen(self if isinstance(self, QWidget) else None,
                                    anzahl):
            return
        canvas._push_undo()
        canvas._clear()

    # ── WEB-10: Handy-Konsole ────────────────────────────────────────────────

    def _toggle_handy_leiste(self, checked: bool):
        self._btn_handy.setText("📱 Handy-Konsole ✓" if checked else "📱 Handy-Konsole")
        if self._handy_leiste is None:
            return          # UI-96: Kiosk ohne Handy-Leiste
        self._handy_leiste.setVisible(bool(checked))
        if checked:
            self._handy_leiste.set_edit_mode(self._edit_mode)

    def _handy_abgelegt(self, _kennung: str):
        if not self._btn_handy.isChecked():
            self._btn_handy.setChecked(True)

    def _handy_verbinden(self):
        """„📱 Handy verbinden" in der Seitenleiste: der Dialog „Web-Remote:
        Verbindung & Token", der gleich alles Noetige einschaltet (WEB-12)."""
        fenster = self.window()
        oeffnen = getattr(fenster, "_open_web_remote_dialog", None)
        if callable(oeffnen):
            try:
                oeffnen(verbinden=True)
            except Exception as e:
                print(f"[virtual_console_view] ERROR: Web-Remote-Dialog: {e}")
                QMessageBox.warning(self, "Handy-Konsole", str(e))
        else:
            QMessageBox.information(
                self, "Handy-Konsole",
                "Link und Schlüssel fürs Handy stehen unter\n"
                "Ausgabe → „Web-Remote: Verbindung & Token…“.")
        if self._handy_leiste is not None:
            self._handy_leiste._verbindung_zeigen()

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
