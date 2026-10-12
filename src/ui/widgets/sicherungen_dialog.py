"""STAB-32: Dialog „Ältere Version öffnen…" (Menü Datei).

Listet die versionierten Sicherungen der aktuellen Show (wahlweise aller
Shows) mit Datum/Uhrzeit, Anlass, Groesse und einer Kurzinfo (Geraete-/
Funktionszahl). Die Kurzinfo wird aus der Datei gelesen, ohne die Show zu
laden — und zeilenweise nachgereicht, damit eine lange Liste das Fenster nicht
aufhaelt. Der Dialog oeffnet selbst nichts: er liefert nur die Auswahl.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QHeaderView,
    QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from src.core.show import sicherungen as S

_SPALTEN = ("Datum / Uhrzeit", "Show", "Anlass", "Größe", "Inhalt")
_SP_ZEIT, _SP_SHOW, _SP_ANLASS, _SP_GROESSE, _SP_INFO = range(5)


def groesse_text(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB".replace(".", ",")
    return f"{max(1, round(n / 1024))} KB"


class SicherungenDialog(QDialog):
    """``auswahl()`` liefert nach ``exec()`` die gewaehlte :class:`Sicherung`."""

    def __init__(self, show_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ältere Version öffnen")
        self.resize(720, 420)
        self._show_name = show_name
        self._eintraege: list[S.Sicherung] = []
        self._offen: list[int] = []          # Zeilen, deren Kurzinfo noch fehlt

        lay = QVBoxLayout(self)
        self._kopf = QLabel()
        self._kopf.setWordWrap(True)
        lay.addWidget(self._kopf)

        self._tabelle = QTableWidget(0, len(_SPALTEN))
        self._tabelle.setHorizontalHeaderLabels(list(_SPALTEN))
        self._tabelle.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tabelle.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tabelle.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tabelle.verticalHeader().setVisible(False)
        kopf = self._tabelle.horizontalHeader()
        kopf.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        kopf.setSectionResizeMode(_SP_INFO, QHeaderView.ResizeMode.Stretch)
        self._tabelle.itemDoubleClicked.connect(lambda *_: self.accept())
        self._tabelle.itemSelectionChanged.connect(self._knopf_nachfuehren)
        lay.addWidget(self._tabelle, 1)

        self._alle = QCheckBox("Sicherungen aller Shows anzeigen")
        self._alle.toggled.connect(self._fuellen)
        lay.addWidget(self._alle)

        hinweis = QLabel(
            "Die Version öffnet sich als neue, ungespeicherte Show. Deine "
            "Show-Datei und die Sicherung bleiben unverändert.")
        hinweis.setWordWrap(True)
        lay.addWidget(hinweis)

        self._knoepfe = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Open |
            QDialogButtonBox.StandardButton.Cancel)
        self._knoepfe.button(QDialogButtonBox.StandardButton.Open).setText("Öffnen")
        self._knoepfe.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        self._knoepfe.accepted.connect(self.accept)
        self._knoepfe.rejected.connect(self.reject)
        lay.addWidget(self._knoepfe)

        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._naechste_kurzinfo)
        self._fuellen()

    # ── Inhalt ───────────────────────────────────────────────────────────────

    def eintraege(self) -> list[S.Sicherung]:
        return list(self._eintraege)

    def _fuellen(self, *_):
        alle = self._alle.isChecked()
        self._eintraege = S.liste_sicherungen(None if alle else self._show_name)
        t = self._tabelle
        t.setRowCount(len(self._eintraege))
        for zeile, e in enumerate(self._eintraege):
            werte = (e.zeit_text, e.show, e.anlass_text, groesse_text(e.groesse), "…")
            for spalte, text in enumerate(werte):
                item = QTableWidgetItem(text)
                if spalte == _SP_GROESSE:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight |
                                          Qt.AlignmentFlag.AlignVCenter)
                t.setItem(zeile, spalte, item)
        t.setColumnHidden(_SP_SHOW, not alle)
        if self._eintraege:
            t.selectRow(0)
            self._kopf.setText(
                f"{len(self._eintraege)} Sicherung(en)"
                + ("" if alle else f" von „{self._show_name}“") + " — neueste zuerst.")
        else:
            self._kopf.setText(
                "Noch keine Sicherungen" + ("." if alle else
                                            f" von „{self._show_name}“."))
        self._offen = list(range(len(self._eintraege)))
        self._knopf_nachfuehren()
        if self._offen:
            self._timer.start()
        else:
            self._timer.stop()

    def _naechste_kurzinfo(self):
        if not self._offen:
            self._timer.stop()
            return
        zeile = self._offen.pop(0)
        if zeile < len(self._eintraege):
            item = self._tabelle.item(zeile, _SP_INFO)
            if item is not None:
                item.setText(S.kurzinfo(self._eintraege[zeile].pfad))

    def kurzinfos_fertig_laden(self):
        """Alle ausstehenden Kurzinfos sofort lesen (Tests)."""
        while self._offen:
            self._naechste_kurzinfo()

    def zeilen_text(self) -> list[list[str]]:
        t = self._tabelle
        return [[t.item(z, s).text() for s in range(t.columnCount())]
                for z in range(t.rowCount())]

    def _knopf_nachfuehren(self):
        self._knoepfe.button(QDialogButtonBox.StandardButton.Open).setEnabled(
            self.auswahl() is not None)

    def waehle(self, zeile: int):
        self._tabelle.selectRow(zeile)

    def auswahl(self) -> S.Sicherung | None:
        zeile = self._tabelle.currentRow()
        if 0 <= zeile < len(self._eintraege) and self._tabelle.selectedItems():
            return self._eintraege[zeile]
        return None

    def done(self, ergebnis):
        self._timer.stop()
        super().done(ergebnis)
