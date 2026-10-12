"""LAS-32 (Slice S1): Bedienung und Anzeige der Sperrzonen — NUR ANZEIGE.

* :class:`SperrzonenHinweis` — die Meldung je Laser („kann Zone X erreichen" /
  „erreicht keine Zone" / „Randwinkel fehlen — nicht prüfbar"), gelb
  beschriftet, dass nichts abgeschaltet wird.
* Bearbeitet wird im Planer (``sperrzonen_planer.py``, LAS-35): Zonen ziehen,
  Laser-Felder, Einmess-Assistent. Der fruehere Zahlenfeld-Dialog ist darin
  aufgegangen; von ihm bleibt hier der Datenblatt-Schnellweg
  (:class:`_GesamtwinkelDialog`).
* :class:`SperrzonenKopfzeile` — die kleine gelbe Zeile im Hauptfenster
  „Laser gepatcht — keine Sperrzonen angelegt".

Nichts hier fasst die DMX-Ausgabe an. Jede Aenderung landet in
``state.sperrzonen`` und meldet ``sperrzonen_changed``; der 3D-Visualizer
zeichnet daraufhin neu, die Rechnung liegt in ``core/laser/sperrzonen.py``.
"""
from __future__ import annotations

import html

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout,
)

from src.core.laser import sperrzonen as S
from src.core.laser import sperrzonen_merker as M
from src.ui.widgets.decimal_spinbox import LocaleTolerantDoubleSpinBox

GELB = "#ffcc00"
GRENZEN_TEXT = ("Kein Laserschutz: ersetzt weder Blende/Abschattung am Gerät "
                "noch Abstände und Mindesthöhen noch den Laserschutzbeauftragten.")
NICHT_ANGEGEBEN = "nicht angegeben"

# LAS-35: gemeinsames Aussehen von Planer und Einmess-Assistent (dunkel,
# Bedienflaechen mindestens 36 px hoch).
BLAU = "#1a82ff"
BEDIEN_HOEHE = 36
PLANER_QSS = f"""
QDialog#sperrzonenPlaner, QWidget#einmessAssistent {{ background:#2b2b2b; color:#e4e4e4; }}
QWidget#sperrzonenPlaner QLabel, QWidget#einmessAssistent QLabel {{ color:#e4e4e4; }}
QFrame[rolle="tafel"] {{ background:#232323; border:1px solid #3a3a3a; border-radius:3px; }}
QFrame[rolle="karte"] {{ background:#1c1c1c; border:1px solid #3a3a3a; border-radius:4px; }}
QLabel[rolle="kopf"] {{ color:#9aa4b0; font-size:11px; font-weight:700; }}
QLabel[rolle="blass"] {{ color:#8b949e; font-size:11px; }}
QPushButton {{ min-height:{BEDIEN_HOEHE - 2}px; padding:0 12px; background:#3a3a3a;
  border:1px solid #505050; border-radius:3px; color:#e6e6e6; }}
QPushButton:disabled {{ color:#777; background:#303030; border-color:#3c3c3c; }}
QPushButton:checked, QPushButton[rolle="blau"] {{ background:{BLAU};
  border-color:#4a9cff; color:#fff; font-weight:600; }}
QPushButton[rolle="blau"]:disabled {{ background:#28466e; color:#9ab; border-color:#345; }}
QPushButton[rolle="gelb"] {{ background:#3a3000; border-color:#f0c000; color:#f0c000;
  font-weight:600; }}
QPushButton[rolle="gelb"]:disabled {{ background:#2c2a20; border-color:#6b5d1c; color:#8c7f45; }}
QPushButton[rolle="stopp"] {{ background:#8b0000; border:2px solid #e02020; color:#fff;
  font-weight:700; font-size:15px; min-height:52px; }}
QPushButton[rolle="rot"] {{ color:#ff8080; }}
QDoubleSpinBox, QLineEdit {{ min-height:{BEDIEN_HOEHE - 2}px; background:#3a3a3a;
  border:1px solid #555; border-radius:3px; color:#fff; padding:0 6px; }}
QDoubleSpinBox:disabled, QLineEdit:disabled {{ color:#777; background:#303030; }}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width:26px; }}
QCheckBox {{ color:#e4e4e4; spacing:8px; min-height:{BEDIEN_HOEHE - 6}px; }}
QCheckBox::indicator {{ width:22px; height:22px; }}
QListWidget {{ background:#1c1c1c; border:1px solid #3a3a3a; border-radius:3px; outline:0; }}
QScrollArea {{ border:0; background:transparent; }}
"""


def melde_aenderung(state) -> None:
    """Nach jeder Aenderung an ``state.sperrzonen`` rufen."""
    try:
        state._emit("sperrzonen_changed", None)
    except Exception as e:                               # noqa: BLE001
        print(f"[sperrzonen] emit error: {e}")


def hinweis_html(state) -> str:
    """Der Meldungstext (RichText). Leer = nichts anzuzeigen (kein DMX-Laser)."""
    try:
        kopf, befunde = S.state_befunde(state)
    except Exception as e:                               # noqa: BLE001
        kopf, befunde = f"Sperrzonen: Anzeige nicht berechenbar ({e})", []
    if not kopf:
        return ""
    zeilen = [f'<b style="color:{GELB}">Sperrzonen (Vorschau) — '
              f'{html.escape(S.HINWEIS_NUR_ANZEIGE)}</b>']
    if not befunde:
        zeilen.append(f'<span style="color:{GELB}">{html.escape(kopf)}</span>')
    for b in befunde:
        if b.status == S.STATUS_ERREICHT:
            farbe = "#ff9040"
        elif b.status == S.STATUS_NICHT_PRUEFBAR:
            farbe = GELB
        else:
            farbe = "#c9d1d9"
        zeilen.append(f'<span style="color:{farbe}">{html.escape(b.text)}</span>')
    return "<br>".join(zeilen)


class SperrzonenHinweis(QFrame):
    """Gelb umrandete Meldung je Laser. Unsichtbar, solange kein DMX-Laser
    gepatcht ist. Frischt sich selbst auf, solange sie sichtbar sein koennte
    (die Rechnung kostet Mikrosekunden; ein Abo auf jede Positionsaenderung im
    3D waere die fehleranfaelligere Loesung)."""

    INTERVALL_MS = 1000

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self._state = state
        self.setObjectName("sperrzonenHinweis")
        self.setStyleSheet(
            f"#sperrzonenHinweis{{border:1px solid {GELB};border-radius:5px;"
            "background:#2a2400;}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        self._label = QLabel("")
        self._label.setObjectName("sperrzonenHinweisText")
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setWordWrap(True)
        lay.addWidget(self._label, stretch=1)
        # LAS-35: von der Meldung direkt in den Planer.
        self._btn_planer = QPushButton("Sperrzonen planen…")
        self._btn_planer.setObjectName("sperrzonenHinweisPlaner")
        self._btn_planer.setMinimumHeight(BEDIEN_HOEHE)
        self._btn_planer.setToolTip(
            "Öffnet den Planer: Zonen ziehen, Laser-Felder eintragen oder "
            "einmessen. " + S.GRENZEN_KOMPAKT)
        self._btn_planer.clicked.connect(self.planer_oeffnen)
        lay.addWidget(self._btn_planer, alignment=Qt.AlignmentFlag.AlignTop)
        self._timer = QTimer(self)
        self._timer.setInterval(self.INTERVALL_MS)
        self._timer.timeout.connect(self._takt)
        self._timer.start()
        self.aktualisieren()

    def text(self) -> str:
        return self._label.text()

    def planer_oeffnen(self):
        from src.ui.visualizer.sperrzonen_planer import planer_oeffnen
        return planer_oeffnen(self._state, self.window())

    def _takt(self) -> None:
        # Die Meldung blendet sich selbst aus, wenn es nichts zu sagen gibt —
        # der Takt darf deshalb nicht an ihrer eigenen Sichtbarkeit haengen,
        # sondern an der des Elters (Reiter/Dialog gerade zu sehen?).
        elter = self.parentWidget()
        if elter is not None and not elter.isVisible():
            return
        self.aktualisieren()

    def aktualisieren(self) -> None:
        inhalt = hinweis_html(self._state)
        if inhalt != self._label.text():
            self._label.setText(inhalt)
        self.setVisible(bool(inhalt))


class SperrzonenKopfzeile(QLabel):
    """Kleine gelbe Zeile fuer die Kopfleiste des Hauptfensters (G10):
    „Laser gepatcht — keine Sperrzonen angelegt". Nicht modal, kein Knopf.
    Wann sie erscheint, entscheidet allein
    :func:`src.core.laser.sperrzonen.kopfleisten_hinweis`.

    ``state_holen`` liefert den aktuellen State (das Hauptfenster kann ihn
    wechseln). Der Aufrufer ruft :meth:`aktualisieren` im eigenen Takt."""

    def __init__(self, state_holen, parent=None):
        super().__init__("", parent)
        self._state_holen = state_holen
        self.setObjectName("sperrzonenKopfzeile")
        self.setStyleSheet(
            f"#sperrzonenKopfzeile{{color:{GELB};font-size:11px;"
            "padding:0px 8px;background:transparent;}")
        self.setToolTip(
            "In dieser Show gibt es keine Sperrzonen. Anlegen: 3D-Fenster, "
            "Werkzeugleiste „Sperrzonen…“.\n" + S.HINWEIS_NUR_ANZEIGE + "\n" + GRENZEN_TEXT)
        self.setVisible(False)

    def soll_text(self) -> str:
        try:
            state = self._state_holen()
            daten = getattr(state, "sperrzonen", None)
            if daten is None:
                return ""
            # Billig zuerst — das laeuft im Takt des NOT-AUS-Knopfs: wer die
            # Funktion nie benutzt hat oder Zonen hat, kostet keinen Gang
            # durch den Patch.
            benutzt = M.war_benutzt()
            if not S.kopfleisten_hinweis(1, daten, benutzt):
                return ""
            return S.kopfleisten_hinweis(len(S.dmx_laser(state)), daten, benutzt)
        except Exception:                                # noqa: BLE001
            return ""       # eine Anzeige darf das Hauptfenster nie stoeren

    def aktualisieren(self) -> None:
        text = self.soll_text()
        if text != self.text():
            self.setText(text)
        if self.isHidden() == bool(text):
            self.setVisible(bool(text))


class _GesamtwinkelDialog(QDialog):
    """Datenblatt-Schnellweg: voller Abstrahlwinkel waagerecht/senkrecht."""

    def __init__(self, laser_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Winkel laut Datenblatt")
        lay = QVBoxLayout(self)
        text = QLabel(
            f"Für „{html.escape(laser_name)}“ nennt das Geräteprofil keinen "
            "Abstrahlwinkel. Trage den <b>vollen</b> Winkel aus dem Datenblatt "
            "ein (z. B. „Scanwinkel 40°“). Er wird je zur Hälfte auf "
            "links/rechts bzw. oben/unten verteilt.<br>"
            f'<span style="color:{GELB}">Ein Datenblatt-Wert ist keine Messung '
            "— die Ränder später am Gerät nachprüfen.</span>")
        text.setTextFormat(Qt.TextFormat.RichText)
        text.setWordWrap(True)
        lay.addWidget(text)
        form = QFormLayout()
        self.waagerecht = _spin(1.0, 2 * S.WINKEL_MAX, 40.0, schritt=1.0,
                                suffix=" °", stellen=1)
        self.senkrecht = _spin(1.0, 2 * S.WINKEL_MAX, 40.0, schritt=1.0,
                               suffix=" °", stellen=1)
        form.addRow("Gesamtwinkel waagerecht", self.waagerecht)
        form.addRow("Gesamtwinkel senkrecht", self.senkrecht)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class UmbruchText(QLabel):
    """RichText mit Zeilenumbruch, das seine Hoehe auch dort bekommt, wo Qt
    sie nicht durchreicht (Stapel, Rollbereich) — sonst wird Text abgeschnitten."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

    def _hoehe_nachziehen(self) -> None:
        if not self.isVisible():        # ungezeigt ist die Breite noch geraten
            return
        h = self.heightForWidth(self.width())
        if h > 0 and h != self.minimumHeight():
            self.setMinimumHeight(h)

    def showEvent(self, ev):  # noqa: N802 (Qt-API)
        super().showEvent(ev)
        self._hoehe_nachziehen()

    def resizeEvent(self, ev):  # noqa: N802 (Qt-API)
        super().resizeEvent(ev)
        self._hoehe_nachziehen()

    def setText(self, text):  # noqa: N802 (Qt-API)
        super().setText(text)
        self._hoehe_nachziehen()


def _spin(lo, hi, wert, schritt=0.1, suffix=" m", stellen=2):
    sp = LocaleTolerantDoubleSpinBox()
    sp.setDecimals(stellen)
    sp.setRange(lo, hi)
    sp.setSingleStep(schritt)
    sp.setSuffix(suffix)
    sp.setValue(wert)
    return sp
