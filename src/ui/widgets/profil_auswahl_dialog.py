"""UI-74: Ein gespeichertes Geraeteprofil wieder oeffnen.

Bis UI-74 kannte das Menue „Datenbank“ nur „Neues Fixture-Profil...“ — der
Fixture-Editor konnte ein vorhandenes Profil laden (``fixture_id``), aber kein
Weg fuehrte dorthin. Ein eigenes Profil mit einem Tippfehler war damit nur
noch neu anzulegen.

Regel, welches Profil wie geoeffnet wird (``oeffnen_als``):

* **eigene Profile** (``source='user'``) -> bearbeiten;
* **mitgelieferte** (``builtin``, ``lightos``) und **QLC+-Importe**
  (``qlcplus``) -> nur ansehen oder als eigenes Profil kopieren. Die naechste
  Bibliotheks-Aktualisierung bzw. ``ensure_builtins`` schriebe eine Aenderung
  an Ort und Stelle wieder zurueck — still, und mit ihr waere die Arbeit weg.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.database.fixture_db import engine
from src.core.database.models import FixtureProfile, Manufacturer

#: Anzeige der ``source``-Werte in der Liste.
QUELLE_ANZEIGE = {
    "user": "eigenes Profil",
    "lightos": "LightOS-Bibliothek",
    "builtin": "eingebaut",
    "qlcplus": "QLC+-Import",
}

BEARBEITEN = "bearbeiten"
ANSEHEN = "ansehen"
KOPIEREN = "kopieren"


def profil_bearbeitbar(source: str | None) -> bool:
    """Nur eigene Profile werden an Ort und Stelle bearbeitet (s. Modul)."""
    return (source or "").lower() == "user"


def profile_suchen(text: str = "", eng=None) -> list[tuple[int, str, str, str]]:
    """``[(id, hersteller, modell, source), ...]`` — alle Woerter von ``text``
    muessen in „Hersteller Modell“ vorkommen (Gross/klein egal)."""
    eng = eng if eng is not None else engine()
    with Session(eng) as s:
        zeilen = s.execute(
            select(FixtureProfile.id, Manufacturer.name, FixtureProfile.name,
                   FixtureProfile.source)
            .join(Manufacturer, FixtureProfile.manufacturer_id == Manufacturer.id)
            .order_by(Manufacturer.name, FixtureProfile.name)).all()
    woerter = [w for w in (text or "").lower().split() if w]
    out = []
    for pid, hersteller, modell, source in zeilen:
        heu = f"{hersteller} {modell}".lower()
        if all(w in heu for w in woerter):
            out.append((int(pid), hersteller or "", modell or "", source or ""))
    return out


def profil_oeffnen(parent, fixture_id: int, wie: str) -> int | None:
    """Oeffnet den Fixture-Editor fuer ``fixture_id``. ``wie``: BEARBEITEN /
    ANSEHEN / KOPIEREN. Gibt die gespeicherte Profil-ID zurueck (oder None)."""
    from src.ui.widgets.fixture_editor import FixtureEditorDialog
    dlg = FixtureEditorDialog(parent, fixture_id=fixture_id,
                              nur_ansehen=(wie == ANSEHEN),
                              als_kopie=(wie == KOPIEREN))
    dlg.exec()
    return dlg.saved_id


def _source_von(fixture_id: int, eng=None) -> str | None:
    eng = eng if eng is not None else engine()
    with Session(eng) as s:
        return s.execute(select(FixtureProfile.source)
                         .where(FixtureProfile.id == fixture_id)).scalar_one_or_none()


def profil_bearbeiten_fuer(parent, fixture_id: int) -> int | None:
    """Einstieg „Profil bearbeiten“ von einem gepatchten Geraet aus: eigenes
    Profil -> Editor; sonst Rueckfrage Ansehen / als eigenes Profil kopieren."""
    source = _source_von(fixture_id)
    if source is None:
        QMessageBox.warning(parent, "Profil bearbeiten",
                            "Das Profil steht nicht in der Geräte-Bibliothek.")
        return None
    if profil_bearbeitbar(source):
        return profil_oeffnen(parent, fixture_id, BEARBEITEN)
    box = QMessageBox(parent)
    box.setWindowTitle("Profil bearbeiten")
    box.setText(f"Dieses Profil ist {QUELLE_ANZEIGE.get(source, source)} und wird "
                f"nicht überschrieben. Ansehen oder als eigenes Profil kopieren?")
    b_kopie = box.addButton("Als eigenes Profil kopieren…",
                            QMessageBox.ButtonRole.AcceptRole)
    b_ansehen = box.addButton("Ansehen…", QMessageBox.ButtonRole.ActionRole)
    box.addButton(QMessageBox.StandardButton.Cancel)
    box.exec()
    if box.clickedButton() is b_kopie:
        return profil_oeffnen(parent, fixture_id, KOPIEREN)
    if box.clickedButton() is b_ansehen:
        return profil_oeffnen(parent, fixture_id, ANSEHEN)
    return None


class ProfilAuswahlDialog(QDialog):
    """Menue Datenbank -> „Fixture-Profil bearbeiten...“: Profil suchen und
    bearbeiten, ansehen oder als eigenes Profil kopieren."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fixture-Profil bearbeiten")
        self.setMinimumSize(620, 480)
        lay = QVBoxLayout(self)

        zeile = QHBoxLayout()
        zeile.addWidget(QLabel("Suche:"))
        self._suche = QLineEdit()
        self._suche.setPlaceholderText("Hersteller oder Modell…")
        self._suche.textChanged.connect(lambda t: self._laden(t))
        zeile.addWidget(self._suche)
        lay.addLayout(zeile)

        self._liste = QTreeWidget()
        self._liste.setHeaderLabels(["Hersteller", "Modell", "Herkunft"])
        self._liste.setRootIsDecorated(False)
        self._liste.setColumnWidth(0, 160)
        self._liste.setColumnWidth(1, 260)
        self._liste.currentItemChanged.connect(lambda *_: self._knoepfe())
        self._liste.itemDoubleClicked.connect(lambda *_: self._standard())
        lay.addWidget(self._liste, 1)

        self._hinweis = QLabel("")
        self._hinweis.setWordWrap(True)
        self._hinweis.setStyleSheet("color: #8b949e; font-size: 11px;")
        lay.addWidget(self._hinweis)

        knoepfe = QHBoxLayout()
        self.btn_bearbeiten = QPushButton("Bearbeiten…")
        self.btn_bearbeiten.clicked.connect(lambda: self._oeffnen(BEARBEITEN))
        self.btn_ansehen = QPushButton("Ansehen…")
        self.btn_ansehen.clicked.connect(lambda: self._oeffnen(ANSEHEN))
        self.btn_kopieren = QPushButton("Als eigenes Profil kopieren…")
        self.btn_kopieren.clicked.connect(lambda: self._oeffnen(KOPIEREN))
        schliessen = QPushButton("Schließen")
        schliessen.clicked.connect(self.reject)
        for b in (self.btn_bearbeiten, self.btn_ansehen, self.btn_kopieren):
            b.setAutoDefault(False)
            knoepfe.addWidget(b)
        knoepfe.addStretch(1)
        knoepfe.addWidget(schliessen)
        lay.addLayout(knoepfe)

        self._laden("")

    def _laden(self, text: str) -> None:
        self._liste.clear()
        for pid, hersteller, modell, source in profile_suchen(text):
            it = QTreeWidgetItem([hersteller, modell,
                                  QUELLE_ANZEIGE.get(source, source)])
            it.setData(0, Qt.ItemDataRole.UserRole, (pid, source))
            self._liste.addTopLevelItem(it)
        if self._liste.topLevelItemCount():
            self._liste.setCurrentItem(self._liste.topLevelItem(0))
        self._knoepfe()

    def gewaehlt(self) -> tuple[int, str] | None:
        it = self._liste.currentItem()
        return it.data(0, Qt.ItemDataRole.UserRole) if it is not None else None

    def _knoepfe(self) -> None:
        wahl = self.gewaehlt()
        eigen = bool(wahl) and profil_bearbeitbar(wahl[1])
        self.btn_bearbeiten.setEnabled(eigen)
        self.btn_ansehen.setEnabled(bool(wahl) and not eigen)
        self.btn_kopieren.setEnabled(bool(wahl))
        if not wahl:
            self._hinweis.setText("Kein Profil gefunden.")
        elif eigen:
            self._hinweis.setText("Eigenes Profil — kann bearbeitet werden.")
        else:
            self._hinweis.setText(
                "Mitgelieferte und importierte Profile werden nicht überschrieben "
                "(die nächste Bibliotheks-Aktualisierung stellte sie wieder her). "
                "Zum Ändern als eigenes Profil kopieren.")

    def _standard(self) -> None:
        wahl = self.gewaehlt()
        if wahl:
            self._oeffnen(BEARBEITEN if profil_bearbeitbar(wahl[1]) else ANSEHEN)

    def _oeffnen(self, wie: str) -> None:
        wahl = self.gewaehlt()
        if not wahl:
            return
        if wie == BEARBEITEN and not profil_bearbeitbar(wahl[1]):
            return
        if profil_oeffnen(self, wahl[0], wie) is not None:
            self._laden(self._suche.text())
