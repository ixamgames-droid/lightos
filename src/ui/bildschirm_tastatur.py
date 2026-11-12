"""UI-112: app-eigene Bildschirmtastatur und Ziffernblock fuer den Touch-Modus.

Befund Touch-Audit 11.11.2026 (C-01/C-02): Unter Linux gibt es keine
System-Bildschirmtastatur, die von selbst erscheint (ibus; onboard waere zwar
installierbar, ist aber aus und gehoert nicht zur App). Rund 50 Eingabe-
dialoge, Suchfelder und Adressen waren am Finger nicht bedienbar, und grosse
Werte in Zahlenfeldern (Adresse 300, Wert 255) nur ueber winzige Pfeile.

Dieses Modul bringt beides selbst mit — reine Qt-Widgets, nichts zu
installieren:

* ``Ziffernblock``: erscheint beim Fingertipp in ein ``QSpinBox``/
  ``QDoubleSpinBox`` (auf allen Systemen). Eigene Anzeige, Ziffern, Komma,
  Vorzeichen (nur wenn das Feld negative Werte kann), Loeschen, „Min“/„Max“,
  „Abbruch“ und „OK“. OK setzt den Wert, auf den Bereich des Felds begrenzt.
* ``Bildschirmtastatur``: erscheint beim Fingertipp in ein ``QLineEdit``
  (auch das Textfeld einer editierbaren Klappliste) — unter Linux/macOS.
  Unter Windows bleibt die System-Tastatur (TabTip, ``touch_keyboard``).
  QWERTZ mit Umlauten, Umschalt, Zeichen-Ebene, Leertaste, Cursor, Loeschen.
  Getippt wird live ins Feld (Suchfilter laufen mit); „Abbruch“ stellt den
  alten Text wieder her, „Fertig“ schliesst, „↵“ schliesst und schickt die
  Eingabetaste ans Feld (wie die echte Tastatur).

Beide sind ``Qt.Popup``-Fenster mit dem Eingabefeld als Eltern: sie bekommen
auch in modalen Dialogen Eingaben, ein Tipp daneben schliesst sie (wie
Abbruch), und das Feld verliert dabei nicht seinen Zustand (Qt meldet beim
Popup des eigenen Felds kein ``editingFinished``).

Ausgeloest wird nur von ``touch_keyboard.OskEventFilter``: im Touch-Modus,
bei einem Tipp mit dem Finger (Maus, die Qt aus Touch erzeugt; Bewegung
unter der Touch-Schwelle von ``ziehen_scrollen``). Maus und echte Tastatur
oeffnen nie etwas. Abschalten je Feld: Qt-Eigenschaft
``bildschirm_tastatur = False``.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QGuiApplication, QKeyEvent
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)

try:
    from shiboken6 import isValid as _gueltig
except Exception:                       # pragma: no cover
    def _gueltig(_obj) -> bool:
        return True

#: Qt-Eigenschaft: False = an diesem Feld nie Tastatur/Ziffernblock.
EIN_AUS = "bildschirm_tastatur"
#: Mindestmass einer Taste (px) — Richtwert Touch-Audit: >= 44 px.
TASTE_MIN = 52
#: Unter Windows zeigt die System-Tastatur (TabTip) Text an; dort keine eigene.
APP_TEXT_TASTATUR = sys.platform != "win32"

_STIL = """
QFrame#bildschirmTastatur {
    background: #1d1f27; border: 1px solid #0978FF; border-radius: 6px;
}
QFrame#bildschirmTastatur QLabel { color: #ffffff; background: transparent; }
QFrame#bildschirmTastatur QLabel#anzeige {
    background: #11131a; border: 1px solid #3a3d4a; border-radius: 4px;
    padding: 4px 10px; font-size: 22px; min-height: 40px;
}
QFrame#bildschirmTastatur QLabel#bereich { color: #9aa0b0; font-size: 12px; }
QFrame#bildschirmTastatur QPushButton {
    background: #3a3d4a; color: #ffffff; border: 1px solid #161616;
    border-radius: 5px; font-size: 18px; padding: 0 6px;
    min-height: 52px; max-height: 52px; min-width: 44px;
}
QFrame#bildschirmTastatur QPushButton:pressed { background: #0978FF; }
QFrame#bildschirmTastatur QPushButton:checked { background: #2a5ea8; }
QFrame#bildschirmTastatur QPushButton[rolle="ok"] { background: #1f6f3a; }
QFrame#bildschirmTastatur QPushButton[rolle="ab"] { background: #5a2a2a; }
"""


# ── Ausloesen ────────────────────────────────────────────────────────────────

def _offenes_popup(w: QWidget | None):
    return getattr(w, "_bildschirm_popup", None) if w is not None else None


def ziel_fuer(w) -> tuple[str, QWidget] | None:
    """Welche Eingabehilfe passt zu einem Tipp auf ``w``?

    ``("zahl", spinbox)`` fuer das Textfeld eines QSpinBox/QDoubleSpinBox,
    ``("text", lineedit)`` fuer ein freies QLineEdit, sonst None (auch fuer
    die Pfeil-/±-Knoepfe eines Zahlenfelds: die zaehlen weiter)."""
    if not isinstance(w, QLineEdit) or not _gueltig(w):
        return None
    eltern = w.parentWidget()
    if isinstance(eltern, (QSpinBox, QDoubleSpinBox)):
        if (not eltern.isEnabled() or eltern.isReadOnly()
                or eltern.property(EIN_AUS) is False or w.property(EIN_AUS) is False):
            return None
        return ("zahl", eltern)
    if isinstance(eltern, QAbstractSpinBox):
        return None                     # Datum/Uhrzeit: eigenes Format, kein Block
    if not w.isEnabled() or w.isReadOnly() or w.property(EIN_AUS) is False:
        return None
    if not APP_TEXT_TASTATUR:
        return None
    return ("text", w)


def oeffnen(w) -> QFrame | None:
    """Oeffnet Ziffernblock oder Tastatur fuer ``w`` (wenn passend)."""
    ziel = ziel_fuer(w)
    if ziel is None:
        return None
    art, feld = ziel
    anker = feld.lineEdit() if art == "zahl" else feld
    alt = _offenes_popup(anker)
    if alt is not None and _gueltig(alt) and alt.isVisible():
        return alt
    popup = Ziffernblock(feld) if art == "zahl" else Bildschirmtastatur(feld)
    popup.zeigen()
    return popup


# ── Gemeinsame Teile ─────────────────────────────────────────────────────────

class _Taste(QPushButton):
    """Taste ohne Fokus: der Fokus bleibt beim Popup bzw. beim Feld."""

    def __init__(self, text: str, parent=None, breite: float = 1.0, rolle: str = ""):
        super().__init__(text, parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAutoDefault(False)
        self.setMinimumSize(int(TASTE_MIN * breite), TASTE_MIN)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if rolle:
            self.setProperty("rolle", rolle)
        # Ein Wisch ueber die Tasten soll nichts scrollen/ziehen (ziehen_scrollen).
        self.setProperty("ziehen_scrollen", False)
        self.setProperty("lang_druck_menue", False)


class _PopupBasis(QFrame):
    def __init__(self, anker: QWidget):
        super().__init__(anker, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("bildschirmTastatur")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        # Ein Tipp daneben schliesst nur (wie Abbruch) — Qt soll den Druck
        # nicht an das Widget dahinter weiterreichen (GO, BLACKOUT, STOP ALL
        # liegen oft genau neben dem Feld).
        self.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay, True)
        self.setStyleSheet(_STIL)
        self._anker = anker
        self._erledigt = False
        anker._bildschirm_popup = self      # type: ignore[attr-defined]

    def zeigen(self) -> None:
        self.adjustSize()
        self.move(self._lage())
        self.show()
        self.raise_()

    def _lage(self) -> QPoint:
        """Unter dem Feld, sonst darueber; immer ganz auf dem Bildschirm."""
        a = self._anker
        oben_links = a.mapToGlobal(QPoint(0, 0))
        feld = QRect(oben_links, a.size())
        bildschirm = a.screen() or QGuiApplication.primaryScreen()
        frei = bildschirm.availableGeometry() if bildschirm else QRect(0, 0, 1920, 1080)
        g = self.sizeHint().expandedTo(self.minimumSizeHint())
        x = min(max(feld.left(), frei.left()), frei.right() - g.width() + 1)
        y = feld.bottom() + 4
        if y + g.height() > frei.bottom() + 1:
            y = feld.top() - g.height() - 4
        y = max(frei.top(), min(y, frei.bottom() - g.height() + 1))
        return QPoint(max(frei.left(), x), y)

    def _abbrechen_intern(self) -> None:     # in Unterklassen
        pass

    def abbrechen(self) -> None:
        if not self._erledigt:
            self._erledigt = True
            self._abbrechen_intern()
        self.close()

    def hideEvent(self, ev):                 # noqa: N802 (Qt) — Tipp daneben
        if not self._erledigt:
            self._erledigt = True
            self._abbrechen_intern()
        if _gueltig(self._anker) and getattr(self._anker, "_bildschirm_popup", None) is self:
            self._anker._bildschirm_popup = None   # type: ignore[attr-defined]
        super().hideEvent(ev)


# ── Ziffernblock ─────────────────────────────────────────────────────────────

class Ziffernblock(_PopupBasis):
    """Zahl eintippen, OK setzt sie (im Bereich des Felds) ins Zahlenfeld."""

    def __init__(self, spin: QSpinBox | QDoubleSpinBox):
        super().__init__(spin.lineEdit())
        self._spin = spin
        self._doppelt = isinstance(spin, QDoubleSpinBox)
        self._komma = spin.locale().decimalPoint() if self._doppelt else ""
        if self._doppelt and not self._komma:
            self._komma = ","
        self._text = self._zahl_text(spin.value())
        self._frisch = True            # erste Ziffer ersetzt den alten Wert

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        self.anzeige = QLabel()
        self.anzeige.setObjectName("anzeige")
        self.anzeige.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self.anzeige)
        self.bereich = QLabel(f"Bereich {self._zahl_text(spin.minimum())} … "
                              f"{self._zahl_text(spin.maximum())}")
        self.bereich.setObjectName("bereich")
        lay.addWidget(self.bereich)

        grid = QGridLayout()
        grid.setSpacing(8)
        self.tasten: dict[str, _Taste] = {}
        for i, z in enumerate("789456123"):
            self._taste(grid, z, i // 3, i % 3, lambda _=False, z=z: self.tippe(z))
        if spin.minimum() < 0:
            self._taste(grid, "±", 3, 0, lambda: self.vorzeichen())
        self._taste(grid, "0", 3, 1, lambda: self.tippe("0"))
        if self._doppelt and spin.decimals() > 0:
            self._taste(grid, self._komma, 3, 2, lambda: self.tippe(self._komma))
        self._taste(grid, "⌫", 0, 3, lambda: self.loeschen())
        self._taste(grid, "C", 1, 3, lambda: self.leeren())
        self._taste(grid, "Min", 2, 3, lambda: self.setze(spin.minimum()))
        self._taste(grid, "Max", 3, 3, lambda: self.setze(spin.maximum()))
        lay.addLayout(grid)

        unten = QHBoxLayout()
        unten.setSpacing(12)
        self.btn_abbruch = _Taste("Abbruch", self, 2, rolle="ab")
        self.btn_abbruch.clicked.connect(self.abbrechen)
        self.btn_ok = _Taste("OK", self, 2, rolle="ok")
        self.btn_ok.clicked.connect(self.uebernehmen)
        unten.addWidget(self.btn_abbruch)
        unten.addWidget(self.btn_ok)
        lay.addLayout(unten)
        self._zeige()

    def _taste(self, grid, text, r, c, fn) -> None:
        t = _Taste(text, self)
        t.clicked.connect(fn)
        grid.addWidget(t, r, c)
        self.tasten[text] = t

    def _zahl_text(self, wert) -> str:
        if not self._doppelt:
            return str(int(wert))
        return f"{float(wert):.{self._spin.decimals()}f}".replace(".", self._komma)

    def _zeige(self) -> None:
        self.anzeige.setText(self._text or "0")

    # Eingabe
    def tippe(self, zeichen: str) -> None:
        if self._frisch:
            self._text = ""
            self._frisch = False
        if zeichen == self._komma:
            if self._komma in self._text:
                return
            if self._text in ("", "-"):
                self._text += "0"
        elif self._komma and self._komma in self._text:
            nachkomma = len(self._text.split(self._komma, 1)[1])
            if nachkomma >= self._spin.decimals():
                return
        if self._text in ("0", "-0") and zeichen != self._komma:
            self._text = self._text[:-1]
        if len(self._text.replace("-", "")) >= 15:
            return
        self._text += zeichen
        self._zeige()

    def vorzeichen(self) -> None:
        self._frisch = False
        self._text = self._text[1:] if self._text.startswith("-") else "-" + self._text
        self._zeige()

    def loeschen(self) -> None:
        self._frisch = False
        self._text = self._text[:-1]
        if self._text == "-":
            self._text = ""
        self._zeige()

    def leeren(self) -> None:
        self._frisch = False
        self._text = ""
        self._zeige()

    def setze(self, wert) -> None:
        self._text = self._zahl_text(wert)
        self._frisch = True
        self._zeige()

    def wert(self):
        """Eingetippter Wert, auf den Bereich des Felds begrenzt (None = leer)."""
        t = self._text.replace(self._komma, ".") if self._komma else self._text
        if t in ("", "-", ".", "-."):
            return None
        try:
            w = float(t)
        except ValueError:
            return None
        w = max(self._spin.minimum(), min(self._spin.maximum(), w))
        if not self._doppelt:
            return int(round(w))
        return round(w, self._spin.decimals())

    def uebernehmen(self) -> None:
        w = self.wert()
        self._erledigt = True
        if w is not None and _gueltig(self._spin):
            self._spin.setValue(w)
            self._spin.editingFinished.emit()   # wie Tippen + Eingabetaste
        self.close()

    def keyPressEvent(self, ev):             # noqa: N802 (Qt) — echte Tastatur geht auch
        k, t = ev.key(), ev.text()
        if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.uebernehmen()
        elif k == Qt.Key.Key_Escape:
            self.abbrechen()
        elif k == Qt.Key.Key_Backspace:
            self.loeschen()
        elif t and t.isdigit():
            self.tippe(t)
        elif t in (",", ".") and self._komma in self.tasten:
            self.tippe(self._komma)
        elif t == "-" and "±" in self.tasten:
            self.vorzeichen()
        else:
            super().keyPressEvent(ev)


# ── Bildschirmtastatur (Text) ────────────────────────────────────────────────

_REIHEN = ("1234567890ß", "qwertzuiopü", "asdfghjklöä", "yxcvbnm,.-")
_ZEICHEN = ("!\"§$%&/()=?", "@#+*~'^°<>|", "_:;[]{}\\€µ²", "´`³¿¡¬¦,.-")


class Bildschirmtastatur(_PopupBasis):
    """QWERTZ-Tastatur, tippt live ins Feld; Abbruch stellt den alten Text her."""

    def __init__(self, feld: QLineEdit):
        super().__init__(feld)
        self._feld = feld
        self._alt = feld.text()
        self._gross = False
        self._zeichen = False
        bildschirm = feld.screen() or QGuiApplication.primaryScreen()
        breite = bildschirm.availableGeometry().width() if bildschirm else 1280
        # 12 Tasten je Reihe sollen auf den Bildschirm passen, aber nicht riesig werden.
        self._taste_b = max(40, min(66, (breite - 40) // 12 - 6))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)
        self.anzeige = QLabel()
        self.anzeige.setObjectName("anzeige")
        self.anzeige.setTextFormat(Qt.TextFormat.PlainText)
        lay.addWidget(self.anzeige)

        self._buchstaben: list[_Taste] = []
        for i, reihe in enumerate(_REIHEN):
            zeile = QHBoxLayout()
            zeile.setSpacing(6)
            if i == 3:
                self.btn_umschalt = self._sonder(zeile, "⇧", 1.5, self.umschalten)
                self.btn_umschalt.setCheckable(True)
            for j, z in enumerate(reihe):
                t = _Taste(z, self)
                t.setMinimumSize(self._taste_b, TASTE_MIN)
                t.setProperty("klein", z)
                t.setProperty("zeichen", _ZEICHEN[i][j] if j < len(_ZEICHEN[i]) else z)
                t.clicked.connect(lambda _=False, t=t: self.tippe(t.text()))
                zeile.addWidget(t)
                self._buchstaben.append(t)
            if i == 0:
                self._sonder(zeile, "⌫", 1.5, self.loeschen)
            lay.addLayout(zeile)

        zeile = QHBoxLayout()
        zeile.setSpacing(6)
        self.btn_zeichen = self._sonder(zeile, "?123", 1.5, self.zeichen_umschalten)
        self.btn_zeichen.setCheckable(True)
        self._sonder(zeile, "◀", 1, lambda: self._feld.cursorBackward(False))
        leer = self._sonder(zeile, "Leerzeichen", 5, lambda: self.tippe(" "))
        leer.setObjectName("leertaste")
        self._sonder(zeile, "▶", 1, lambda: self._feld.cursorForward(False))
        self._sonder(zeile, "Leeren", 1.5, self.leeren)
        lay.addLayout(zeile)

        unten = QHBoxLayout()
        unten.setSpacing(12)
        self.btn_abbruch = self._sonder(unten, "Abbruch", 2, self.abbrechen, "ab")
        unten.addStretch(1)
        self.btn_fertig = self._sonder(unten, "Fertig", 2, self.fertig, "ok")
        self.btn_eingabe = self._sonder(unten, "↵", 1.5, self.eingabe, "ok")
        lay.addLayout(unten)

        feld.textChanged.connect(self._zeige)
        self._zeige()

    def _sonder(self, zeile, text, breite, fn, rolle="") -> _Taste:
        t = _Taste(text, self, rolle=rolle)
        t.setMinimumSize(int(self._taste_b * breite), TASTE_MIN)
        t.clicked.connect(fn)
        zeile.addWidget(t, max(1, int(breite * 2)))
        return t

    def _zeige(self, *_):
        if not _gueltig(self._feld) or not _gueltig(self.anzeige):
            return
        text = self._feld.displayText()
        self.anzeige.setText(text if text else " ")

    def _beschriften(self) -> None:
        for t in self._buchstaben:
            z = t.property("zeichen") if self._zeichen else t.property("klein")
            t.setText(z.upper() if (self._gross and not self._zeichen) else z)

    # Eingabe
    def tippe(self, text: str) -> None:
        if not _gueltig(self._feld):
            return
        self._feld.insert(text)
        if self._gross and not self._zeichen and text.strip():
            self._setze_gross(False)        # Umschalt gilt fuer EIN Zeichen

    def umschalten(self, *_) -> None:
        self._setze_gross(not self._gross)

    def _setze_gross(self, an: bool) -> None:
        self._gross = bool(an)
        self.btn_umschalt.setChecked(self._gross)
        self._beschriften()

    def zeichen_umschalten(self) -> None:
        self._zeichen = not self._zeichen
        self.btn_zeichen.setChecked(self._zeichen)
        self.btn_zeichen.setText("abc" if self._zeichen else "?123")
        self._beschriften()

    def loeschen(self) -> None:
        if _gueltig(self._feld):
            self._feld.backspace()

    def leeren(self) -> None:
        if _gueltig(self._feld):
            self._feld.selectAll()
            self._feld.del_()

    def _abbrechen_intern(self) -> None:
        if _gueltig(self._feld) and self._feld.text() != self._alt:
            self._feld.setText(self._alt)

    def fertig(self) -> None:
        self._erledigt = True
        self.close()

    def eingabe(self) -> None:
        """Schliessen und die Eingabetaste ans Feld schicken (Suche, Dialog-OK)."""
        self._erledigt = True
        feld = self._feld
        self.close()
        if _gueltig(feld):
            for typ in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
                QApplication.sendEvent(feld, QKeyEvent(typ, Qt.Key.Key_Return,
                                                       Qt.KeyboardModifier.NoModifier, "\r"))

    def keyPressEvent(self, ev):             # noqa: N802 (Qt) — echte Tastatur geht auch
        if ev.key() == Qt.Key.Key_Escape:
            self.abbrechen()
        elif ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.eingabe()
        elif _gueltig(self._feld):
            QApplication.sendEvent(self._feld, QKeyEvent(ev.type(), ev.key(), ev.modifiers(),
                                                         ev.text(), ev.isAutoRepeat(), ev.count()))
