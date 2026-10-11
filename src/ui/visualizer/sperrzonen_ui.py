"""LAS-32 (Slice S1): Bedienung und Anzeige der Sperrzonen — NUR ANZEIGE.

* :class:`SperrzonenHinweis` — die Meldung je Laser („kann Zone X erreichen" /
  „erreicht keine Zone" / „Randwinkel fehlen — nicht prüfbar"), gelb
  beschriftet, dass nichts abgeschaltet wird.
* :class:`SperrzonenDialog` — Zonen anlegen, verschieben, in der Groesse
  aendern, benennen, loeschen; je Laser die vier Randwinkel und den Zuschlag.

Nichts hier fasst die DMX-Ausgabe an. Jede Aenderung landet in
``state.sperrzonen`` und meldet ``sperrzonen_changed``; der 3D-Visualizer
zeichnet daraufhin neu, die Rechnung liegt in ``core/laser/sperrzonen.py``.
"""
from __future__ import annotations

import html

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from src.core.laser import sperrzonen as S
from src.core.laser.sperrzonen import LaserFeld, Sperrzone
from src.ui.widgets.decimal_spinbox import LocaleTolerantDoubleSpinBox

GELB = "#ffcc00"
GRENZEN_TEXT = ("Kein Laserschutz: ersetzt weder Blende/Abschattung am Gerät "
                "noch Abstände und Mindesthöhen noch den Laserschutzbeauftragten.")
_NICHT_ANGEGEBEN = "nicht angegeben"


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
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        self._label = QLabel("")
        self._label.setObjectName("sperrzonenHinweisText")
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setWordWrap(True)
        lay.addWidget(self._label)
        self._timer = QTimer(self)
        self._timer.setInterval(self.INTERVALL_MS)
        self._timer.timeout.connect(self._takt)
        self._timer.start()
        self.aktualisieren()

    def text(self) -> str:
        return self._label.text()

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


def _spin(lo, hi, wert, schritt=0.1, suffix=" m", stellen=2):
    sp = LocaleTolerantDoubleSpinBox()
    sp.setDecimals(stellen)
    sp.setRange(lo, hi)
    sp.setSingleStep(schritt)
    sp.setSuffix(suffix)
    sp.setValue(wert)
    return sp


class SperrzonenDialog(QDialog):
    """Sperrzonen und Laser-Felder der Show bearbeiten."""

    _ZONEN_FELDER = (
        ("x", "Mitte X (rechts/links)", -200.0, 200.0),
        ("y", "Unterkante (Höhe über Boden)", -20.0, 50.0),
        ("z", "Mitte Z (vorn/hinten)", -200.0, 200.0),
        ("breite", "Breite (X)", S.ZONE_MIN_M, 200.0),
        ("hoehe", "Höhe (Y)", S.ZONE_MIN_M, 50.0),
        ("tiefe", "Tiefe (Z)", S.ZONE_MIN_M, 200.0),
    )

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self._state = state
        self._laedt = False
        self.setWindowTitle("Sperrzonen (Vorschau) — nur Anzeige")
        self.setModal(False)
        self.resize(760, 640)
        root = QVBoxLayout(self)

        grenzen = QLabel(f"<b>{html.escape(S.HINWEIS_NUR_ANZEIGE)}</b><br>"
                         f"{html.escape(GRENZEN_TEXT)}")
        grenzen.setObjectName("sperrzonenGrenzen")
        grenzen.setTextFormat(Qt.TextFormat.RichText)
        grenzen.setWordWrap(True)
        grenzen.setStyleSheet(
            f"color:{GELB};border:1px solid {GELB};border-radius:5px;"
            "background:#2a2400;padding:6px;")
        root.addWidget(grenzen)

        # ── Zonen ─────────────────────────────────────────────────────────
        zbox = QGroupBox("Sperrzonen (Quader, im 3D rot)")
        zl = QHBoxLayout(zbox)
        links = QVBoxLayout()
        self._liste = QListWidget()
        self._liste.currentRowChanged.connect(self._zone_gewaehlt)
        links.addWidget(self._liste, stretch=1)
        knoepfe = QHBoxLayout()
        self._btn_neu = QPushButton("Neue Zone")
        self._btn_neu.clicked.connect(self._zone_neu)
        self._btn_loeschen = QPushButton("Löschen")
        self._btn_loeschen.clicked.connect(self._zone_loeschen)
        knoepfe.addWidget(self._btn_neu)
        knoepfe.addWidget(self._btn_loeschen)
        links.addLayout(knoepfe)
        zl.addLayout(links, stretch=1)

        self._form_host = QWidget()
        form = QFormLayout(self._form_host)
        self._name = QLineEdit()
        self._name.setMaxLength(40)
        self._name.textEdited.connect(self._zone_geaendert)
        form.addRow("Name", self._name)
        self._zspins = {}
        for attr, titel, lo, hi in self._ZONEN_FELDER:
            sp = _spin(lo, hi, 0.0 if lo < 0 else lo)
            sp.valueChanged.connect(self._zone_geaendert)
            self._zspins[attr] = sp
            form.addRow(titel, sp)
        self._dreh = _spin(-180.0, 180.0, 0.0, schritt=5.0, suffix=" °", stellen=1)
        self._dreh.valueChanged.connect(self._zone_geaendert)
        form.addRow("Drehung um die Hochachse", self._dreh)
        zl.addWidget(self._form_host, stretch=2)
        root.addWidget(zbox, stretch=2)

        # ── Laser-Felder ──────────────────────────────────────────────────
        lbox = QGroupBox("Maximalfeld je Laser — Randwinkel von der Geräteachse")
        ll = QVBoxLayout(lbox)
        erkl = QLabel(
            "Links/rechts/oben/unten aus Sicht des Geräts in Strahlrichtung, in "
            "Grad. Eintragen, was der Laser bei größtem Muster und voller "
            "Auslenkung höchstens erreicht (auch ungleich, z. B. hinter einer "
            f"Blende). „{_NICHT_ANGEGEBEN}“ = dieser Laser ist nicht prüfbar. "
            f"Zuschlag rundum: Vorgabe {S.ZUSCHLAG_STANDARD:g}°, mindestens "
            f"{S.ZUSCHLAG_MIN:g}°.")
        erkl.setWordWrap(True)
        erkl.setStyleSheet("color:#8b949e;")
        ll.addWidget(erkl)
        self._tabelle = QTableWidget(0, 6)
        self._tabelle.setHorizontalHeaderLabels(
            ["Laser", "Links", "Rechts", "Oben", "Unten", "Zuschlag"])
        self._tabelle.verticalHeader().setVisible(False)
        self._tabelle.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        ll.addWidget(self._tabelle)
        root.addWidget(lbox, stretch=2)

        self._hinweis = SperrzonenHinweis(state, self)
        root.addWidget(self._hinweis)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.close)
        root.addWidget(bb)

        self.neu_laden()

    # ── Bestand ───────────────────────────────────────────────────────────
    def _daten(self):
        return self._state.sperrzonen

    def neu_laden(self) -> None:
        """Dialog aus dem State fuellen (z. B. nach dem Laden einer Show)."""
        self._laedt = True
        try:
            fremd = self._daten().fremd is not None
            gewaehlt = self._gewaehlte_id()
            self._liste.clear()
            for z in self._daten().zonen:
                it = QListWidgetItem(z.name)
                it.setData(Qt.ItemDataRole.UserRole, z.id)
                self._liste.addItem(it)
            self._btn_neu.setEnabled(not fremd)
            self._fuelle_tabelle(fremd)
        finally:
            self._laedt = False
        zeile = 0
        for i in range(self._liste.count()):
            if self._liste.item(i).data(Qt.ItemDataRole.UserRole) == gewaehlt:
                zeile = i
        if self._liste.count():
            self._liste.setCurrentRow(zeile)
        self._zone_gewaehlt(self._liste.currentRow())
        self._hinweis.aktualisieren()

    def _gewaehlte_id(self):
        it = self._liste.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it is not None else None

    def _gewaehlte_zone(self):
        zid = self._gewaehlte_id()
        return self._daten().zone(zid) if zid else None

    def _zone_gewaehlt(self, _zeile=None) -> None:
        zone = self._gewaehlte_zone()
        self._form_host.setEnabled(zone is not None)
        self._btn_loeschen.setEnabled(zone is not None)
        if zone is None:
            return
        self._laedt = True
        try:
            self._name.setText(zone.name)
            for attr, sp in self._zspins.items():
                sp.setValue(float(getattr(zone, attr)))
            self._dreh.setValue(float(zone.dreh_y))
        finally:
            self._laedt = False

    def _zone_neu(self) -> None:
        daten = self._daten()
        if daten.fremd is not None:
            return
        vorhandene = {z.name for z in daten.zonen}
        name, n = "Publikum", 2
        while name in vorhandene:
            name, n = f"Zone {n}", n + 1
        zone = Sperrzone(name=name, x=0.0, y=0.0, z=6.0,
                         breite=8.0, hoehe=3.0, tiefe=6.0)
        daten.zonen.append(zone)
        melde_aenderung(self._state)
        self.neu_laden()
        self._liste.setCurrentRow(self._liste.count() - 1)

    def _zone_loeschen(self) -> None:
        zone = self._gewaehlte_zone()
        if zone is None:
            return
        self._daten().zonen.remove(zone)
        melde_aenderung(self._state)
        self.neu_laden()

    def _zone_geaendert(self, *_a) -> None:
        if self._laedt:
            return
        zone = self._gewaehlte_zone()
        if zone is None:
            return
        zone.name = self._name.text().strip() or "Sperrzone"
        for attr, sp in self._zspins.items():
            setattr(zone, attr, float(sp.value()))
        zone.dreh_y = float(self._dreh.value())
        it = self._liste.currentItem()
        if it is not None and it.text() != zone.name:
            it.setText(zone.name)
        melde_aenderung(self._state)
        self._hinweis.aktualisieren()

    # ── Laser-Felder ──────────────────────────────────────────────────────
    def _fuelle_tabelle(self, fremd: bool) -> None:
        laser = S.dmx_laser(self._state)
        self._tabelle.setRowCount(len(laser))
        self._feld_spins = {}
        for zeile, (fid, name) in enumerate(laser):
            feld = self._daten().feld(fid)
            titel = QTableWidgetItem(f"{fid}  {name}")
            titel.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._tabelle.setItem(zeile, 0, titel)
            spins = {}
            for spalte, rand in enumerate(S.RAENDER, start=1):
                # -1 steht fuer „nicht angegeben" (Qt zeigt dann den Sondertext).
                sp = _spin(-1.0, S.WINKEL_MAX, -1.0, schritt=1.0, suffix=" °", stellen=1)
                sp.setSpecialValueText(_NICHT_ANGEGEBEN)
                wert = getattr(feld, rand)
                sp.setValue(-1.0 if wert is None else float(wert))
                sp.setEnabled(not fremd)
                sp.valueChanged.connect(
                    lambda _v, f=fid: self._feld_geaendert(f))
                self._tabelle.setCellWidget(zeile, spalte, sp)
                spins[rand] = sp
            zs = _spin(S.ZUSCHLAG_MIN, S.ZUSCHLAG_MAX, feld.zuschlag,
                       schritt=0.5, suffix=" °", stellen=1)
            zs.setEnabled(not fremd)
            zs.valueChanged.connect(lambda _v, f=fid: self._feld_geaendert(f))
            self._tabelle.setCellWidget(zeile, 5, zs)
            spins["zuschlag"] = zs
            self._feld_spins[fid] = spins

    def _feld_geaendert(self, fid: int) -> None:
        if self._laedt:
            return
        spins = self._feld_spins.get(fid)
        if not spins:
            return
        werte = {}
        for rand in S.RAENDER:
            v = float(spins[rand].value())
            werte[rand] = None if v < 0.0 else v
        feld = LaserFeld(zuschlag=float(spins["zuschlag"].value()), **werte)
        self._daten().setze_feld(fid, feld)
        melde_aenderung(self._state)
        self._hinweis.aktualisieren()
