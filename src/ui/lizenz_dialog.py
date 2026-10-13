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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QVBoxLayout,
)

from src.core import lizenz

TITEL = "LightOS — Testlizenz erforderlich"


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
        self.setMinimumWidth(540)

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        kopf = QLabel(f"<b>{TITEL}</b>", self)
        lay.addWidget(kopf)

        self.erklaerung = QLabel(erklaerung_html(), self)
        self.erklaerung.setWordWrap(True)
        self.erklaerung.setTextFormat(Qt.TextFormat.RichText)
        self.erklaerung.setOpenExternalLinks(False)
        self.erklaerung.linkActivated.connect(self._oeffne_link)
        self.erklaerung.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction)
        lay.addWidget(self.erklaerung)

        self.grund = QLabel(grund_text(status), self)
        self.grund.setWordWrap(True)
        # Reiner Text: hier stehen Dateiname und Befund einer NICHT geprueften
        # Datei — die darf kein HTML in den Dialog bringen.
        self.grund.setTextFormat(Qt.TextFormat.PlainText)
        self.grund.setObjectName("lizenz_grund")
        lay.addWidget(self.grund)

        self.ort = QLabel(
            "Die Lizenzdatei wird nach der Prüfung in den LightOS-Datenordner "
            f"kopiert:\n{lizenz.standard_pfad()}", self)
        self.ort.setWordWrap(True)
        self.ort.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.ort)

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
            self.grund.setText(
                f"„{os.path.basename(pfad)}“ wurde nicht übernommen. "
                + grund_text(status))
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
