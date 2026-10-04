"""UI-74: Ein gespeichertes Geraeteprofil wieder oeffnen.

Bis UI-74 kannte das Menue „Datenbank“ nur „Neues Fixture-Profil...“ — der
Fixture-Editor konnte ein vorhandenes Profil laden (``fixture_id``), aber kein
Weg fuehrte dorthin. Ein eigenes Profil mit einem Tippfehler war damit nur
noch neu anzulegen.

Regel, welches Profil wie geoeffnet wird (``oeffnen_als``):

* **eigene Profile** (``source='user'``) und **QLC+-Importe** (``qlcplus``)
  -> bearbeiten. Der QLC+-Download ueberspringt ein Profil, das es unter
  Hersteller + Modell schon gibt — eine Aenderung bleibt also stehen;
* **mitgelieferte** (``builtin``, ``lightos``) -> nur ansehen oder als eigenes
  Profil kopieren. Die naechste Bibliotheks-Aktualisierung bzw.
  ``ensure_builtins`` schriebe eine Aenderung an Ort und Stelle wieder
  zurueck — still, und mit ihr waere die Arbeit weg.

Wird ein mitgeliefertes Profil aus dem Patch heraus kopiert, bietet
:func:`geraete_auf_kopie_umhaengen` an, die gepatchten Geraete auf die Kopie
umzuhaengen (ein Undo-Schritt).
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


#: ``source``-Werte, die an Ort und Stelle bearbeitet werden (s. Modul).
BEARBEITBARE_QUELLEN = ("user", "qlcplus")


def profil_bearbeitbar(source: str | None) -> bool:
    """Eigene Profile und QLC+-Importe werden an Ort und Stelle bearbeitet,
    mitgelieferte (builtin/lightos) nicht (s. Modul)."""
    return (source or "").lower() in BEARBEITBARE_QUELLEN


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


def _modi_von(s, profil_id: int) -> dict[str, list[int]]:
    from src.core.database.models import FixtureMode
    modi: dict[str, list[int]] = {}
    for name, n in s.execute(select(FixtureMode.name, FixtureMode.channel_count)
                             .where(FixtureMode.fixture_id == profil_id)):
        modi.setdefault(name, []).append(int(n or 0))
    return modi


def umhaengbare_geraete(alt_id: int, neu_id: int, gepatchte,
                        eng=None) -> tuple[list, list]:
    """``(passend, unpassend)`` — die gepatchten Geraete am Profil ``alt_id``,
    aufgeteilt danach, ob die Kopie ``neu_id`` ihren Modus (gleicher Name,
    genau einmal, gleiche Kanalzahl) hat. Nur ``passend`` darf umgehaengt
    werden: sonst fiele das Geraet still auf einen anderen Modus zurueck."""
    eng = eng if eng is not None else engine()
    with Session(eng) as s:
        modi = _modi_von(s, neu_id)
    passend, unpassend = [], []
    for f in gepatchte or ():
        if getattr(f, "fixture_profile_id", None) != alt_id:
            continue
        zahlen = modi.get(getattr(f, "mode_name", "") or "", [])
        if zahlen == [int(getattr(f, "channel_count", 0) or 0)]:
            passend.append(f)
        else:
            unpassend.append(f)
    return passend, unpassend


def _get_state():
    from src.core.app_state import get_state
    return get_state()


def geraete_auf_kopie_umhaengen(parent, alt_id: int, neu_id: int,
                                state=None) -> int:
    """UI-74 (Review): nach „Als eigenes Profil kopieren“ aus dem Patch die
    Geraete am Original auf die Kopie umhaengen — mit Rueckfrage und als EIN
    Undo-Schritt. Ohne das bearbeitete man die Kopie, und die Show liefe
    weiter mit dem Original. Liefert die Zahl umgehaengter Geraete."""
    try:
        state = state if state is not None else _get_state()
        gepatchte = list(state.get_patched_fixtures())
    except Exception:
        return 0
    passend, unpassend = umhaengbare_geraete(alt_id, neu_id, gepatchte)
    if not passend and not unpassend:
        return 0
    if not passend:
        QMessageBox.information(
            parent, "Profil kopiert",
            f"{len(unpassend)} gepatchte(s) Gerät(e) nutzen weiter das Original — "
            "in der Kopie fehlt ihr Modus mit gleicher Kanalzahl. Zum Umstellen "
            "im Patch neu zuweisen.")
        return 0
    with Session(engine()) as s:
        kopie = s.get(FixtureProfile, neu_id)
        if kopie is None:
            return 0
        neu_namen = {"fixture_name": kopie.name,
                     "manufacturer_name": kopie.manufacturer.name if kopie.manufacturer else ""}
    text = (f"{len(passend)} gepatchte(s) Gerät(e) nutzen das Original:\n\n• "
            + "\n• ".join(getattr(f, "label", "") or f"Gerät {f.fid}" for f in passend[:12])
            + (f"\n… und {len(passend) - 12} weitere" if len(passend) > 12 else "")
            + "\n\nAuf die Kopie umhängen? (Rückgängig mit Strg+Z)")
    if unpassend:
        text += (f"\n\n{len(unpassend)} weitere(s) Gerät(e) bleiben beim Original — "
                 "in der Kopie fehlt ihr Modus mit gleicher Kanalzahl.")
    antwort = QMessageBox.question(
        parent, "Geräte umhängen?", text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes)
    if antwort != QMessageBox.StandardButton.Yes:
        return 0
    vorher = {f.fid: {"fixture_profile_id": f.fixture_profile_id,
                      "fixture_name": f.fixture_name,
                      "manufacturer_name": f.manufacturer_name} for f in passend}
    nachher = {fid: dict(neu_namen, fixture_profile_id=neu_id) for fid in vorher}

    def _setzen(werte):
        for fid, w in werte.items():
            state.update_fixture(fid, undoable=False, **w)

    _setzen(nachher)
    try:
        from src.core.undo import Command, get_undo_stack
        get_undo_stack().push(Command(
            label=f"Geräte auf Profil „{neu_namen['fixture_name']}“ umhängen",
            do=lambda: _setzen(nachher), undo=lambda: _setzen(vorher),
            redo=lambda: _setzen(nachher)), execute=False)
    except Exception as e:
        print(f"[UI-74] Undo-Schritt fehlt: {e}")
    return len(passend)


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
        neu = profil_oeffnen(parent, fixture_id, KOPIEREN)
        if neu is not None:
            geraete_auf_kopie_umhaengen(parent, fixture_id, neu)
        return neu
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
            self._hinweis.setText("Eigenes oder importiertes Profil — kann "
                                  "bearbeitet werden.")
        else:
            self._hinweis.setText(
                "Mitgelieferte Profile werden nicht überschrieben (die nächste "
                "Bibliotheks-Aktualisierung stellte sie wieder her). Zum Ändern "
                "als eigenes Profil kopieren.")

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
