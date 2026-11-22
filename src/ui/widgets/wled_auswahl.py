"""OUT-82: Oberflaeche fuer „WLED suchen“ und „Matrix verteilen…“.

Die Rechnung steht in :mod:`src.core.dmx.wled` (Suche, ``/json/info``,
``ddp_verteilung``). Hier nur:

* :func:`matrix_geraete` — welche gepatchten Geraete eine Matrix aus dem
  LED-Matrix-Assistenten (FM-80) sind, je Matrix EIN Eintrag (alle Teile
  zusammen, Start = Universum des ersten Teils).
* :class:`WledAuswahlDialog` — gefundene Geraete (Name, IP, LED-Zahl) zur
  Auswahl.
* :class:`MatrixVerteilenDialog` — Matrix und Ziel-IP waehlen, Vorschau der
  Offsets.

Beide Dialoge werden ueber :mod:`src.ui.dialog_hilfe` geoeffnet und
freigegeben (STAB-41). Im Touch-Modus sind Knoepfe und Listenzeilen
mindestens 44 px hoch. Beispiel-IPs nur 192.0.2.x.
"""
from __future__ import annotations

import re

from PySide6.QtCore import QSize
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QVBoxLayout,
)

TOUCH_MIN_PX = 44


def _touch() -> bool:
    try:
        from src.ui.touch_keyboard import is_touch_mode
        return bool(is_touch_mode())
    except Exception:
        return False


def touch_groesse(*widgets) -> None:
    """Im Touch-Modus mindestens 44 px hoch (Maus-Bedienung bleibt wie sie ist)."""
    if not _touch():
        return
    for w in widgets:
        if w is not None:
            w.setMinimumHeight(max(TOUCH_MIN_PX, w.minimumHeight()))


def geraet_text(g: dict) -> str:
    name = str(g.get("name") or "").strip() or "WLED"
    leds = int(g.get("leds") or 0)
    return f"{name} — {g.get('ip', '')} — {leds} LEDs"


_TEIL_ENDE = re.compile(r"\s+T\d+$")


def _standard_angaben(profil_id: int):
    """Angaben des Assistenten-Profils aus der Bibliothek (oder ``None``)."""
    from sqlalchemy.orm import Session
    from src.core import led_matrix
    from src.core.database import fixture_db as fdb
    from src.core.database.models import FixtureProfile
    with Session(fdb.engine()) as s:
        prof = s.get(FixtureProfile, int(profil_id))
        return led_matrix.angaben_von_profil(prof) if prof is not None else None


def matrix_geraete(state, angaben_holen=None) -> list[dict]:
    """``[{"name", "angaben", "start", "teile"}]`` — je Assistenten-Matrix im
    Patch ein Eintrag. Die Teile einer Matrix (``matrix_patchen``: gleiches
    Profil, Beschriftung „<Name> T<k>“) werden zusammengefasst; Start ist das
    kleinste Universum. Profile ohne Assistenten-Angaben fehlen."""
    holen = angaben_holen or _standard_angaben
    gruppen: dict = {}
    for fx in list(state.get_patched_fixtures() or []):
        pid = getattr(fx, "fixture_profile_id", None)
        if pid is None:
            continue
        basis = _TEIL_ENDE.sub("", str(getattr(fx, "label", "") or "").strip())
        gruppen.setdefault((int(pid), basis), []).append(fx)
    cache: dict = {}
    out = []
    for (pid, basis), fxs in gruppen.items():
        if pid not in cache:
            try:
                cache[pid] = holen(pid)
            except Exception:
                cache[pid] = None
        a = cache[pid]
        if a is None:
            continue
        start = min(int(getattr(f, "universe", 1) or 1) for f in fxs)
        out.append({"name": basis or f"Matrix (Profil {pid})", "angaben": a,
                    "start": start, "teile": len(fxs)})
    out.sort(key=lambda g: (g["start"], g["name"]))
    return out


class WledAuswahlDialog(QDialog):
    """Liste der gefundenen WLED-Geraete; „Übernehmen“ traegt die IP ein."""

    def __init__(self, geraete: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("WLED-Gerät wählen")
        self._geraete = list(geraete)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Gefundene WLED-Geräte (Name — IP — LED-Zahl):"))
        self._liste = QListWidget()
        for g in self._geraete:
            item = QListWidgetItem(geraet_text(g))
            if _touch():
                item.setSizeHint(QSize(0, TOUCH_MIN_PX))
            self._liste.addItem(item)
        if self._geraete:
            self._liste.setCurrentRow(0)
        self._liste.itemDoubleClicked.connect(lambda *_: self.accept())
        lay.addWidget(self._liste, 1)
        knoepfe = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        knoepfe.button(QDialogButtonBox.StandardButton.Ok).setText("IP übernehmen")
        knoepfe.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        touch_groesse(*knoepfe.buttons())
        lay.addWidget(knoepfe)

    def gewaehlt(self) -> dict | None:
        i = self._liste.currentRow()
        return self._geraete[i] if 0 <= i < len(self._geraete) else None


class MatrixVerteilenDialog(QDialog):
    """Matrix-Geraet und Ziel-IP waehlen; zeigt Universum/Offset je Teil."""

    def __init__(self, geraete: list[dict], ip: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Matrix auf DDP verteilen")
        self._geraete = list(geraete)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self._combo = QComboBox()
        for g in self._geraete:
            self._combo.addItem(
                f"{g['name']} — ab Universum {g['start']} ({g['teile']} Teil(e))")
        self._ip = QLineEdit(ip)
        self._ip.setPlaceholderText("z. B. 192.0.2.50")
        form.addRow("Matrix-Gerät:", self._combo)
        form.addRow("WLED-IP:", self._ip)
        lay.addLayout(form)
        self._vorschau = QLabel()
        self._vorschau.setWordWrap(True)
        lay.addWidget(self._vorschau, 1)
        self._knoepfe = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        self._knoepfe.button(QDialogButtonBox.StandardButton.Ok).setText("Eintragen")
        self._knoepfe.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        self._knoepfe.accepted.connect(self.accept)
        self._knoepfe.rejected.connect(self.reject)
        lay.addWidget(self._knoepfe)
        touch_groesse(self._combo, self._ip, *self._knoepfe.buttons())
        self._combo.currentIndexChanged.connect(self._nachziehen)
        self._ip.textChanged.connect(self._nachziehen)
        self._nachziehen()

    def ip(self) -> str:
        return self._ip.text().strip()

    def gewaehlt(self) -> dict | None:
        i = self._combo.currentIndex()
        return self._geraete[i] if 0 <= i < len(self._geraete) else None

    def _nachziehen(self, *_):
        from src.core.dmx import wled
        g = self.gewaehlt()
        ok = g is not None and bool(self.ip())
        self._knoepfe.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ok)
        if g is None:
            self._vorschau.setText("Keine Matrix aus dem LED-Matrix-Assistenten gepatcht.")
            return
        self._vorschau.setText(wled.ddp_hinweis(
            g["angaben"], g["start"], self.ip() or "…"))
