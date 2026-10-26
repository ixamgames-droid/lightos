"""LIZ-1: Abfrage der Testlizenz beim Programmstart.

Erscheint NUR beim echten GUI-Start (``main.main()``), und nur, wenn keine
gueltige Lizenzdatei gefunden wurde. Einen Weg „weiter ohne Lizenz“ gibt es
nicht: der Dialog endet mit einer gueltigen, in den Datenordner uebernommenen
Lizenz — oder mit „Beenden“.

Waehrend der Sitzung wird nie wieder geprueft; siehe ``src/core/lizenz.py``.

Absturzfest gebaut: kein Knopf loescht ein Widget aus seinem eigenen Signal,
die Unterdialoge sind modale Kinder dieses Dialogs und leben bis zu dessen Ende.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout,
    QWidget,
)

from src.core import lizenz

TITEL = "LightOS — Testlizenz erforderlich"
MIN_BREITE = 540
# Platz fuer Fensterrahmen/Titelleiste, den der Dialog am Bildschirm freilaesst.
RAND_BILDSCHIRM = 48


def grund_text(status: lizenz.Lizenzstatus) -> str:
    """Warum gefragt wird — ein Satz."""
    if status.zustand == lizenz.FEHLT:
        return "Auf diesem Rechner wurde keine Lizenzdatei gefunden."
    if status.zustand == lizenz.ABGELAUFEN:
        bis = status.gueltig_bis.strftime("%d.%m.%Y") if status.gueltig_bis else "?"
        return f"Die Testlizenz für {status.name} ist am {bis} abgelaufen."
    if status.zustand == lizenz.UNGUELTIG:
        return ("Die Lizenzdatei ist ungültig"
                + (f": {status.grund}." if status.grund else "."))
    return ""


def erklaerung_html() -> str:
    return (
        "LightOS ist in der Testphase. Die Nutzung ist nur mit Erlaubnis des "
        f"Urhebers <b>{lizenz.URHEBER}</b> gestattet. Einen Testzugang gibt es "
        f"auf Anfrage über GitHub: <a href='{lizenz.QUELLE}'>{lizenz.QUELLE}</a>")


class LizenztextDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LightOS — Lizenztext")
        self.resize(720, 560)
        lay = QVBoxLayout(self)
        self.text = QPlainTextEdit(self)
        self.text.setReadOnly(True)
        self.text.setPlainText(lizenz.lizenztext())
        lay.addWidget(self.text)
        knoepfe = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        knoepfe.rejected.connect(self.reject)
        knoepfe.accepted.connect(self.accept)
        lay.addWidget(knoepfe)


class LizenzDialog(QDialog):
    """Fragt nach einer Lizenzdatei. ``exec()`` -> Accepted nur mit gueltiger,
    uebernommener Lizenz (dann steht sie in :attr:`status`)."""

    def __init__(self, status: lizenz.Lizenzstatus, parent=None):
        super().__init__(parent)
        self.status = status
        self._lizenztext: LizenztextDialog | None = None
        self.setWindowTitle(TITEL)
        self.setModal(True)
        self.setMinimumWidth(MIN_BREITE)
        self._passt_an = False

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        self.kopf = QLabel(f"<b>{TITEL}</b>", self)
        lay.addWidget(self.kopf)

        # Die Texte stehen in einem rahmenlosen Rollbereich: seine Hoehe folgt
        # dem umbrochenen Inhalt (siehe _passe_hoehe_an). Gerollt wird nur, wenn
        # der Inhalt hoeher waere als der Bildschirm — sonst ist nichts davon
        # zu sehen. Ohne das schnitt der Dialog die zweite Zeile der Erklaerung
        # und die Pfadzeile ab (Hoehe aus dem EINzeiligen sizeHint berechnet).
        self.bereich = QScrollArea(self)
        self.bereich.setFrameShape(QFrame.Shape.NoFrame)
        self.bereich.setWidgetResizable(True)
        self.bereich.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.bereich.setStyleSheet(
            "QScrollArea { background: transparent; }")
        self.inhalt = QWidget(self.bereich)
        self.inhalt.setObjectName("lizenz_inhalt")
        self.inhalt.setStyleSheet(
            "QWidget#lizenz_inhalt { background: transparent; }")
        inh = QVBoxLayout(self.inhalt)
        inh.setContentsMargins(0, 0, 0, 0)
        inh.setSpacing(12)
        self.bereich.setWidget(self.inhalt)
        self.bereich.viewport().setAutoFillBackground(False)
        lay.addWidget(self.bereich, 1)

        self.erklaerung = QLabel(erklaerung_html(), self.inhalt)
        self.erklaerung.setWordWrap(True)
        self.erklaerung.setTextFormat(Qt.TextFormat.RichText)
        self.erklaerung.setOpenExternalLinks(False)
        self.erklaerung.linkActivated.connect(self._oeffne_link)
        self.erklaerung.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction)
        inh.addWidget(self.erklaerung)

        self.grund = QLabel(grund_text(status), self.inhalt)
        self.grund.setWordWrap(True)
        # Reiner Text: hier stehen Dateiname und Befund einer NICHT geprueften
        # Datei — die darf kein HTML in den Dialog bringen.
        self.grund.setTextFormat(Qt.TextFormat.PlainText)
        self.grund.setObjectName("lizenz_grund")
        inh.addWidget(self.grund)

        self.ort = QLabel(
            "Die Lizenzdatei wird nach der Prüfung in den LightOS-Datenordner "
            "kopiert:", self.inhalt)
        self.ort.setWordWrap(True)
        inh.addWidget(self.ort)

        # Der Pfad hat keine Leerzeichen und bricht deshalb nicht um: er wird
        # in der Mitte gekuerzt, der volle Pfad steht im Tooltip.
        self._pfad_voll = str(lizenz.standard_pfad())
        self.ort_pfad = QLabel(self._pfad_voll, self.inhalt)
        self.ort_pfad.setObjectName("lizenz_pfad")
        self.ort_pfad.setTextFormat(Qt.TextFormat.PlainText)
        self.ort_pfad.setToolTip(self._pfad_voll)
        self.ort_pfad.setMinimumWidth(0)
        self.ort_pfad.setSizePolicy(QSizePolicy.Policy.Ignored,
                                    QSizePolicy.Policy.Fixed)
        self.ort_pfad.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        inh.addWidget(self.ort_pfad)
        inh.addStretch(1)

        zeile = QHBoxLayout()
        self.btn_auswaehlen = QPushButton("Lizenzdatei auswählen…", self)
        self.btn_lizenztext = QPushButton("Lizenztext anzeigen", self)
        self.btn_beenden = QPushButton("Beenden", self)
        self.btn_auswaehlen.setDefault(True)
        self.btn_beenden.setAutoDefault(False)
        self.btn_lizenztext.setAutoDefault(False)
        zeile.addWidget(self.btn_auswaehlen)
        zeile.addWidget(self.btn_lizenztext)
        zeile.addStretch(1)
        zeile.addWidget(self.btn_beenden)
        lay.addLayout(zeile)

        self.btn_auswaehlen.clicked.connect(self._auswaehlen)
        self.btn_lizenztext.clicked.connect(self._zeige_lizenztext)
        self.btn_beenden.clicked.connect(self.reject)
        # Startbreite = Mindestbreite (sonst gaelte Qts Vorgabe 640x480).
        self.resize(MIN_BREITE, self.height())
        self._passe_hoehe_an()

    # ── Groesse folgt dem Inhalt ─────────────────────────────────────────────

    def _verfuegbar(self) -> QSize:
        """Nutzbare Bildschirmflaeche — eigene Methode, damit Tests sie
        ersetzen koennen."""
        schirm = self.screen() or QGuiApplication.primaryScreen()
        if schirm is None:
            return QSize(1280, 720)
        return schirm.availableGeometry().size()

    def _passe_hoehe_an(self) -> None:
        """Macht den Dialog so hoch, wie der umbrochene Text bei der aktuellen
        Breite braucht — aber nie groesser als der Bildschirm."""
        if self._passt_an:
            return
        self._passt_an = True
        try:
            frei = self._verfuegbar()
            max_b = max(200, frei.width() - RAND_BILDSCHIRM)
            max_h = max(200, frei.height() - RAND_BILDSCHIRM)
            self.setMinimumWidth(min(MIN_BREITE, max_b))
            self.setMaximumSize(max_b, max_h)
            breite = min(max(self.width(), self.minimumWidth()), max_b)

            lay = self.layout()
            m = lay.contentsMargins()
            innen = max(50, breite - m.left() - m.right())

            def hoehe_inhalt(b: int) -> int:
                self.ort_pfad.setText(self.ort_pfad.fontMetrics().elidedText(
                    self._pfad_voll, Qt.TextElideMode.ElideMiddle,
                    max(20, b - 4)))
                h = self.inhalt.layout().totalHeightForWidth(b)
                return h if h > 0 else self.inhalt.sizeHint().height()

            knopf_h = max(self.btn_auswaehlen.sizeHint().height(),
                          self.btn_lizenztext.sizeHint().height(),
                          self.btn_beenden.sizeHint().height())
            rest = (m.top() + m.bottom() + 2 * lay.spacing()
                    + self.kopf.sizeHint().height() + knopf_h)
            brauch = hoehe_inhalt(innen)
            if brauch > max_h - rest:
                # Es wird gerollt: die Rollleiste nimmt dem Text Breite weg.
                leiste = self.bereich.verticalScrollBar().sizeHint().width()
                brauch = hoehe_inhalt(max(50, innen - leiste))
            sichtbar = max(20, min(brauch, max_h - rest))
            self.bereich.setMinimumHeight(sichtbar)
            self.resize(breite, min(max_h, rest + sichtbar))
        finally:
            self._passt_an = False

    def resizeEvent(self, event) -> None:           # noqa: N802
        super().resizeEvent(event)
        if event.size().width() != event.oldSize().width():
            self._passe_hoehe_an()

    def showEvent(self, event) -> None:             # noqa: N802
        # Erst jetzt stehen Schrift und Stil endgueltig fest.
        self._passe_hoehe_an()
        super().showEvent(event)

    # ── Aktionen ─────────────────────────────────────────────────────────────

    def _oeffne_link(self, url: str) -> None:
        try:
            from PySide6.QtCore import QUrl
            from src.ui import hilfe
            hilfe.oeffne(QUrl(url))
        except Exception as e:                      # noqa: BLE001
            print(f"[lizenz] Link nicht geoeffnet: {e}")

    def _frage_datei(self) -> str:
        """Dateiauswahl — eigene Methode, damit Tests sie ersetzen koennen."""
        pfad, _ = QFileDialog.getOpenFileName(
            self, "Lizenzdatei auswählen", os.path.expanduser("~"),
            "LightOS-Lizenz (*.lic);;Alle Dateien (*)")
        return pfad or ""

    def _auswaehlen(self) -> None:
        try:
            pfad = self._frage_datei()
        except Exception as e:                      # noqa: BLE001
            print(f"[lizenz] Dateiauswahl fehlgeschlagen: {e}")
            pfad = ""
        if pfad:
            self.uebernimm(pfad)

    def uebernimm(self, pfad: str) -> bool:
        """Prueft ``pfad`` und uebernimmt die Datei. True = Dialog angenommen."""
        status, fehler = lizenz.installiere(pfad)
        if status.ist_gueltig and not fehler:
            self.status = status
            self.accept()
            return True
        if status.ist_gueltig:           # gueltig, aber nicht kopierbar
            self.grund.setText(fehler)
        else:
            # Ein Dateiname ohne Leerzeichen bricht nicht um: lange Namen in
            # der Mitte kuerzen, sonst druecken sie den Dialog breit.
            name = os.path.basename(pfad)
            if len(name) > 48:
                name = name[:30] + "…" + name[-17:]
            self.grund.setText(
                f"„{name}“ wurde nicht übernommen. "
                + grund_text(status))
        self._passe_hoehe_an()
        return False

    def _zeige_lizenztext(self) -> None:
        if self._lizenztext is None:
            self._lizenztext = LizenztextDialog(self)
        self._lizenztext.exec()


def frage_nach_lizenz(status: lizenz.Lizenzstatus, parent=None
                      ) -> lizenz.Lizenzstatus | None:
    """Zeigt den Dialog. Rueckgabe: der gueltige Status — oder ``None``, wenn
    der Nutzer beendet (dann darf das Programm nicht starten)."""
    dlg = LizenzDialog(status, parent)
    angenommen = dlg.exec() == QDialog.DialogCode.Accepted
    ergebnis = dlg.status if angenommen and dlg.status.ist_gueltig else None
    dlg.deleteLater()
    return ergebnis
