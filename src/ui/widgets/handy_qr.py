"""WEB-11: der QR-Code zum Verbinden des Handys mit der Handy-Konsole.

``qr_bild`` zeichnet die Matrix aus ``src/web/qr_code.py`` als ``QImage`` — mit
Ruhezone (vier Module hell ringsum, ohne die viele Kameras nicht lesen) und in
ganzzahligen Modulgroessen, also ohne Weichzeichnen.

``HandyQrFeld`` ist das Bedienelement fuer den Dialog „Web-Remote: Verbindung &
Token" (gross) und fuer die Seitenleiste der virtuellen Konsole (klein, Klick
vergroessert): QR-Code, bei mehreren Netzwerkkarten die Auswahl der Adresse,
die Warnzeile — oder, wenn es keinen Code geben kann, der noetige Schritt.

Der Inhalt des Codes ist ein Geheimnis (der Schluessel steht im Link). Er
landet deshalb in keinem Fenstertitel, keinem Tooltip, keinem
``accessibleName`` und in keiner Protokollzeile.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QRect, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QLayout,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from src.web import handy_verbindung as hv
from src.web import qr_code

RUHEZONE = 4            # Module; die Norm verlangt mindestens vier
KANTE_GROSS = 300       # Pixel, im Dialog und in der Vergroesserung
KANTE_KLEIN = 132       # Pixel, in der Seitenleiste
_NETZ_ALLE = 3.0        # Sekunden zwischen zwei Abfragen der Netzwerkkarten


def qr_bild(inhalt, modul_px: int = 6, ruhezone: int = RUHEZONE) -> QImage:
    """Der QR-Code fuer ``inhalt`` als Bild: dunkle Module schwarz auf weiss,
    ``ruhezone`` Module Rand, jedes Modul genau ``modul_px`` Pixel."""
    code = qr_code.erzeuge(inhalt)
    modul_px = max(1, int(modul_px))
    kante = (code.groesse + 2 * ruhezone) * modul_px
    bild = QImage(kante, kante, QImage.Format.Format_RGB32)
    bild.fill(QColor("#ffffff"))
    p = QPainter(bild)
    schwarz = QColor("#000000")
    for y, zeile in enumerate(code.matrix):
        for x, dunkel in enumerate(zeile):
            if dunkel:
                p.fillRect(QRect((x + ruhezone) * modul_px, (y + ruhezone) * modul_px,
                                 modul_px, modul_px), schwarz)
    p.end()
    return bild


def modul_groesse(inhalt, kante_px: int, ruhezone: int = RUHEZONE) -> int:
    """Die groesste ganze Modulgroesse, mit der der Code in ``kante_px`` passt."""
    module = qr_code.erzeuge(inhalt).groesse + 2 * ruhezone
    return max(1, int(kante_px) // module)


def qr_pixmap(inhalt, kante_px: int, dpr: float = 1.0) -> QPixmap:
    """Der Code als ``QPixmap``, hoechstens ``kante_px`` gross (logische Pixel).
    Auf hochaufloesenden Anzeigen werden die Module in echten Pixeln gerechnet
    — das Bild bleibt scharf statt hochskaliert."""
    dpr = max(1.0, float(dpr or 1.0))
    bild = qr_bild(inhalt, modul_groesse(inhalt, int(kante_px * dpr)))
    bild.setDevicePixelRatio(dpr)
    return QPixmap.fromImage(bild)


class _KlickBild(QLabel):
    geklickt = Signal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
                event.position().toPoint()):
            self.geklickt.emit()
        super().mouseReleaseEvent(event)


class HandyQrFeld(QWidget):
    """QR-Code oder der noetige Schritt. ``quelle`` liefert die ``Lage``
    (Standard: der echte Zustand des Programms) — Tests reichen eine eigene."""

    vergroessern = Signal()
    geaendert = Signal()

    def __init__(self, klein: bool = False, parent=None, quelle=None):
        super().__init__(parent)
        self._klein = bool(klein)
        self._quelle = quelle
        self._lage = hv.Lage(hv.SERVER_AUS)
        self._gezeigt = None
        self._netz = (0.0, [], "")
        self.setObjectName("handy_qr_feld")

        self._bild = _KlickBild()
        self._bild.setObjectName("handy_qr_bild")
        self._bild.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bild.geklickt.connect(self.vergroessern.emit)
        self._wahl = QComboBox()
        self._wahl.setObjectName("handy_qr_adresse")
        self._wahl.setToolTip(
            "Dieser PC hat mehrere Netzwerkkarten. Die wählen, die im selben "
            "Netz ist wie das Handy (meist das WLAN). Die Wahl wird gemerkt.")
        self._wahl.currentIndexChanged.connect(self._adresse_gewaehlt)
        self._lbl_wahl = QLabel("Netzwerkkarte:")
        self._lbl_wahl.setObjectName("handy_qr_adresse_titel")
        self._warnung = QLabel(hv.WARNUNG)
        self._warnung.setObjectName("handy_qr_warnung")
        self._warnung.setWordWrap(True)
        self._schritt = QLabel()
        self._schritt.setObjectName("handy_qr_schritt")
        self._schritt.setWordWrap(True)

        if self._klein:
            self._bild.setCursor(Qt.CursorShape.PointingHandCursor)
            self._bild.setToolTip("QR-Code fürs Handy — Klick vergrößert.")
            self._bild.setFixedSize(KANTE_KLEIN, KANTE_KLEIN)
            lay = QHBoxLayout(self)
            lay.setContentsMargins(0, 2, 0, 2)
            lay.setSpacing(8)
            lay.addWidget(self._bild, 0, Qt.AlignmentFlag.AlignTop)
            rechts = QVBoxLayout()
            rechts.setSpacing(4)
            self._titel = QLabel("Mit der Handy-Kamera scannen")
            self._titel.setObjectName("handy_qr_titel")
            self._titel.setWordWrap(True)
            self._titel.setStyleSheet("color:#e6edf3; font-size:11px; font-weight:bold;")
            rechts.addWidget(self._titel)
            self._warnung.setStyleSheet("color:#d29922; font-size:10px;")
            rechts.addWidget(self._warnung)
            self._lbl_wahl.setStyleSheet("color:#8b949e; font-size:10px;")
            rechts.addWidget(self._lbl_wahl)
            self._wahl.setStyleSheet(
                "QComboBox { background:#21262d; color:#e6edf3; border:1px solid #30363d;"
                " border-radius:4px; padding:2px 6px; font-size:10px; }")
            self._wahl.setMinimumContentsLength(8)
            self._wahl.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            rechts.addWidget(self._wahl)
            rechts.addStretch(1)
            lay.addLayout(rechts, 1)
            self._schritt.setStyleSheet("color:#d29922; font-size:10px;")
            lay.addWidget(self._schritt, 1)
        else:
            self._titel = QLabel("Handy verbinden: diesen Code mit der Kamera scannen")
            self._titel.setObjectName("handy_qr_titel")
            self._titel.setStyleSheet("font-weight:bold;")
            lay = QVBoxLayout(self)
            lay.setContentsMargins(0, 4, 0, 4)
            lay.setSpacing(6)
            lay.addWidget(self._titel)
            lay.addWidget(self._bild, 0, Qt.AlignmentFlag.AlignHCenter)
            zeile = QHBoxLayout()
            # Die Beschriftung behaelt ihre volle Breite — die Auswahl daneben
            # bekommt den Rest.
            self._lbl_wahl.setSizePolicy(QSizePolicy.Policy.Fixed,
                                         QSizePolicy.Policy.Preferred)
            zeile.addWidget(self._lbl_wahl, 0)
            zeile.addWidget(self._wahl, 1)
            lay.addLayout(zeile)
            self._warnung.setStyleSheet("color:#d29922;")
            lay.addWidget(self._warnung)
            self._schritt.setStyleSheet("color:#d29922;")
            lay.addWidget(self._schritt)
            # Im Dialog fragt das Feld selbst nach: ein erneuerter Schluessel
            # oder ein umgelegter Schalter erscheint ohne eigene Verdrahtung.
            self._takt = QTimer(self)
            self._takt.setInterval(1000)
            self._takt.timeout.connect(self.aktualisiere)
        self._zeige()

    # ── Abfragen ─────────────────────────────────────────────────────────────

    def lage(self) -> hv.Lage:
        return self._lage

    def url(self) -> str:
        """Der Link im Code — leer, solange es keinen Code gibt."""
        return self._lage.url if self._lage.bereit else ""

    def hat_code(self) -> bool:
        return self._lage.bereit

    def hat_inhalt(self) -> bool:
        """Zeigt das Feld etwas? In der Seitenleiste bleibt es weg, solange die
        Zustandszeile daneben die Lage schon erklaert (aus / Server laeuft
        nicht)."""
        if self._lage.bereit:
            return True
        if self._klein:
            return self._lage.zustand in (hv.NUR_LOKAL, hv.KEIN_NETZ, hv.NETZ_NEU)
        return True

    # ── Anzeige ──────────────────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        if not self._klein:
            self._takt.start()
        self.aktualisiere()

    def hideEvent(self, event):
        if not self._klein:
            self._takt.stop()
        super().hideEvent(event)

    def _lage_lesen(self) -> hv.Lage:
        if self._quelle is not None:
            return self._quelle()
        jetzt = time.monotonic()
        zeit, karten, bevorzugt = self._netz
        if not zeit or jetzt - zeit >= _NETZ_ALLE:
            karten, bevorzugt = hv.lese_schnittstellen(), hv.standard_adresse()
            self._netz = (jetzt, karten, bevorzugt)
        return hv.lage_jetzt(karten, bevorzugt)

    def aktualisiere(self, sofort: bool = False) -> None:
        """Lage neu lesen und nur bei einer Aenderung neu zeichnen. ``sofort``
        fragt auch die Netzwerkkarten neu ab."""
        if sofort:
            self._netz = (0.0, [], "")
        try:
            neu = self._lage_lesen()
        except Exception as e:
            # Nur die Art des Fehlers: eine Meldung koennte den Link enthalten.
            print(f"[handy_qr] ERROR: Lage nicht lesbar: {type(e).__name__}")
            neu = hv.Lage(hv.SERVER_AUS)
        stand = (neu.zustand, neu.url, neu.adressen)
        self._lage = neu
        if stand == self._gezeigt:
            return
        self._gezeigt = stand
        self._zeige()
        self.geaendert.emit()

    def _zeige(self) -> None:
        lage = self._lage
        bereit = lage.bereit
        if bereit:
            try:
                kante = KANTE_KLEIN if self._klein else KANTE_GROSS
                pix = qr_pixmap(lage.url, kante, self.devicePixelRatioF())
                self._bild.setPixmap(pix)
                if not self._klein:
                    self._bild.setFixedSize(pix.deviceIndependentSize().toSize())
            except Exception as e:
                print(f"[handy_qr] ERROR: QR-Code nicht erzeugt: {type(e).__name__}")
                bereit = False
        if not bereit:
            self._bild.clear()
        self._bild.setVisible(bereit)
        self._titel.setVisible(bereit)
        self._warnung.setVisible(bereit)
        mehrere = bereit and len(lage.adressen) > 1
        self._wahl.blockSignals(True)
        self._wahl.clear()
        if bereit:
            for a in lage.adressen:
                self._wahl.addItem(a.beschriftung, a.ip)
            if lage.gewaehlt is not None:
                self._wahl.setCurrentIndex(max(0, self._wahl.findData(lage.gewaehlt.ip)))
        self._wahl.blockSignals(False)
        self._wahl.setVisible(mehrere)
        self._lbl_wahl.setVisible(mehrere)
        self._schritt.setText("" if bereit else (lage.schritt or hv.SCHRITTE[hv.KEIN_NETZ]))
        self._schritt.setVisible(not bereit)

    def _adresse_gewaehlt(self, index: int) -> None:
        ip = self._wahl.itemData(index)
        if not ip:
            return
        try:
            from src.web import remote_settings
            remote_settings.set_handy_ip(str(ip))
        except Exception as e:
            print(f"[handy_qr] ERROR: Auswahl nicht gemerkt: {type(e).__name__}")
        self.aktualisiere()


class HandyQrDialog(QDialog):
    """Die Vergroesserung aus der Seitenleiste: derselbe Code, gross."""

    def __init__(self, parent=None, quelle=None):
        super().__init__(parent)
        self.setObjectName("handy_qr_gross")
        self.setWindowTitle("Handy verbinden")       # nie der Link im Titel
        lay = QVBoxLayout(self)
        # Das Fenster folgt seinem Inhalt: erscheint oder verschwindet der
        # Code, waechst bzw. schrumpft es mit, statt den Inhalt zu stauchen.
        lay.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        self.feld = HandyQrFeld(klein=False, parent=self, quelle=quelle)
        lay.addWidget(self.feld)
        hinweis = QLabel(
            "Handy und PC müssen im selben WLAN sein. Danach am Handy „Zum "
            "Startbildschirm hinzufügen“ — dann startet die Konsole wie eine App.")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet("color:#8b949e;")
        lay.addWidget(hinweis)
        zeile = QHBoxLayout()
        zeile.addStretch(1)
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.accept)
        zeile.addWidget(zu)
        lay.addLayout(zeile)
