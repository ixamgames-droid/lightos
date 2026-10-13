"""FM-74: Fixture Generator und Fixture Editor oeffnen in einer Groesse, in der
nichts uebereinanderliegt.

Befund aus dem Bedientest: der Generator oeffnete kleiner als sein Inhalt
braucht — Tabellenkopf, „+ Kanal / - Kanal / Hoch / Runter“ und „16-bit
Fine-Kanal“ lagen uebereinander, von der Kanaltabelle war eine Zeile zu sehen.
Der Fixture Editor zeigte eine 40 px hohe Kanaltabelle.

FM-70 hatte den Platzbedarf des Generators gesenkt, aber nur mit einem von
Hand gesetzten ``resize(1200, 1000)`` geprueft — die STARTgroesse, mit der
der Dialog wirklich aufgeht, pruefte kein Test. Das holt diese Datei nach.

Der Bildschirm wird gestellt: die Tests ersetzen
``dialog_groesse.verfuegbare_flaeche`` (die einzige Stelle, an der die Dialoge
den Bildschirm fragen). Gerechnet wird in logischen Pixeln — ein 3840 x 2160-
Bildschirm mit Skalierung 2 meldet Qt als 1920 x 1080.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtWidgets import (QAbstractButton, QApplication, QComboBox,
                               QDialog, QLineEdit, QSpinBox, QStyle,
                               QTableWidget, QTextEdit, QVBoxLayout, QWidget)

#: Hoehe einer Systemleiste, die von der Bildschirmflaeche abgeht.
LEISTE = 40

#: (Name, Breite, Hoehe, Skalierung) in GERAETEpixeln.
BILDSCHIRME = [("full-hd", 1920, 1080, 1),
               ("laptop", 1366, 768, 1),
               ("4k-skaliert", 3840, 2160, 2)]


def _app():
    return QApplication.instance() or QApplication([])


def _flaeche(breite: int, hoehe: int, skalierung: int) -> QRect:
    """Verfuegbare Flaeche in logischen Pixeln, Leiste unten abgezogen."""
    return QRect(0, 0, breite // skalierung, hoehe // skalierung - LEISTE)


@pytest.fixture(params=BILDSCHIRME, ids=[b[0] for b in BILDSCHIRME])
def bildschirm(request, monkeypatch):
    _name, b, h, s = request.param
    flaeche = _flaeche(b, h, s)
    # raising=False: auf einem Stand ohne die Hilfsfunktion sollen die Tests an
    # der Groesse scheitern, nicht am Aufbau.
    import importlib
    try:
        mod = importlib.import_module("src.ui.widgets.dialog_groesse")
        monkeypatch.setattr(mod, "verfuegbare_flaeche", lambda _w=None: flaeche)
    except ImportError:
        pass
    return flaeche


def _zeigen(dlg):
    dlg.show()
    for _ in range(3):
        _app().processEvents()
    return dlg


def _zu(dlg):
    live = getattr(dlg, "_live", None)
    if live is not None:
        live.shutdown()
    dlg.close()
    dlg.deleteLater()
    _app().processEvents()


def _generator(typ="laser"):
    _app()
    from src.ui.widgets.fixture_generator import (FixtureGeneratorDialog,
                                                  GenChannel, GenMode,
                                                  GeneratorModel)
    m = GeneratorModel(manufacturer="Laserworld", model="EL-400RGB MK2",
                       fixture_type=typ,
                       modes=[GenMode("Default", [GenChannel(f"K{i}")
                                                  for i in range(9)])])
    return FixtureGeneratorDialog(None, model=m)


def _editor():
    _app()
    from src.ui.widgets.fixture_editor import FixtureEditorDialog
    return FixtureEditorDialog(None)


DIALOGE = {"generator": _generator, "editor": _editor}


@pytest.fixture(params=sorted(DIALOGE))
def dialog(request, bildschirm):
    dlg = _zeigen(DIALOGE[request.param]())
    yield dlg
    _zu(dlg)


# ── Messhilfen ──────────────────────────────────────────────────────────────

_BEDIENTEILE = (QTableWidget, QAbstractButton, QComboBox, QLineEdit, QSpinBox,
                QTextEdit)


def _bedienteile(dlg):
    """Sichtbare Bedienteile des Dialogs, ohne die Innenteile zusammengesetzter
    Widgets (Zellen und Rollbalken einer Tabelle, Eingabezeile einer Spinbox,
    Pfeile der Reiterleiste)."""
    out = []
    for w in dlg.findChildren(QWidget):
        if not isinstance(w, _BEDIENTEILE) or not w.isVisibleTo(dlg):
            continue
        p, innen = w.parentWidget(), False
        while p is not None and p is not dlg:
            if isinstance(p, _BEDIENTEILE) or p.inherits("QTabBar"):
                innen = True
                break
            p = p.parentWidget()
        if not innen:
            out.append(w)
    return out


def _rechteck(dlg, w) -> QRect:
    """Sichtbares Rechteck von ``w`` im Dialog — beschnitten auf alle Eltern
    (was im Rollbereich weggerollt ist, liegt nicht „ueber“ der Knopfzeile)."""
    r = QRect(w.mapTo(dlg, QPoint(0, 0)), w.size())
    p = w.parentWidget()
    while p is not None and p is not dlg:
        r = r.intersected(QRect(p.mapTo(dlg, QPoint(0, 0)), p.size()))
        p = p.parentWidget()
    return r


def _name(w) -> str:
    text = getattr(w, "text", None)
    text = text() if callable(text) else ""
    return f"{type(w).__name__}({text!r})" if text else type(w).__name__


def _ueberlappungen(dlg):
    teile = [(w, _rechteck(dlg, w)) for w in _bedienteile(dlg)]
    treffer = []
    for i, (a, ra) in enumerate(teile):
        for b, rb in teile[i + 1:]:
            if ra.intersects(rb):
                treffer.append(f"{_name(a)} {ra.getRect()} × "
                               f"{_name(b)} {rb.getRect()}")
    return treffer


def _kanaltabellen(dlg):
    tab = dlg._tabs.currentWidget()
    tabellen = [tab._tbl]
    bereiche = getattr(tab, "_range_editor", None)
    if bereiche is not None:
        tabellen.append(bereiche._tbl)
    return tabellen


def _sichtbare_zeilen(tbl) -> int:
    return tbl.viewport().height() // max(
        1, tbl.verticalHeader().defaultSectionSize())


def _titelleiste(dlg) -> int:
    return dlg.style().pixelMetric(QStyle.PixelMetric.PM_TitleBarHeight,
                                   None, dlg)


# ── Die eigentlichen Zusagen ────────────────────────────────────────────────

def test_dialog_passt_auf_den_bildschirm(dialog, bildschirm):
    assert dialog.width() <= bildschirm.width(), (
        f"{dialog.width()} px breit, Bildschirm {bildschirm.width()}")
    hoehe = dialog.height() + _titelleiste(dialog)
    assert hoehe <= bildschirm.height(), (
        f"{dialog.height()} px + Titelleiste, Bildschirm {bildschirm.height()}")
    # Das Mindestmass darf den Dialog nicht ueber den Bildschirm hinausdruecken.
    assert dialog.minimumWidth() <= bildschirm.width()
    assert dialog.minimumHeight() + _titelleiste(dialog) <= bildschirm.height()


def test_nichts_liegt_uebereinander(dialog, bildschirm):
    assert len(_bedienteile(dialog)) >= 10        # die Messung sieht etwas
    treffer = _ueberlappungen(dialog)
    assert not treffer, "Überlappung:\n" + "\n".join(treffer[:12])


def test_kanaltabelle_zeigt_mindestens_fuenf_zeilen(dialog, bildschirm):
    for tbl in _kanaltabellen(dialog):
        assert _sichtbare_zeilen(tbl) >= 5, (
            f"nur {_sichtbare_zeilen(tbl)} Zeilen "
            f"(Tabelle {tbl.width()} x {tbl.height()})")


def test_speichern_bleibt_ohne_rollen_erreichbar(dialog, bildschirm):
    """Speichern/Abbrechen liegen ausserhalb des Rollbereichs und im Fenster."""
    from PySide6.QtWidgets import QDialogButtonBox
    box = dialog.findChild(QDialogButtonBox)
    r = _rechteck(dialog, box)
    assert box.isVisibleTo(dialog)
    assert dialog.rect().contains(r), f"Knopfleiste {r.getRect()} ausserhalb"


def test_auf_grossem_bildschirm_ohne_rollbalken(monkeypatch):
    """1920 x 1080: der ganze Inhalt ist auf einmal zu sehen."""
    from src.ui.widgets import dialog_groesse as DG
    flaeche = _flaeche(1920, 1080, 1)
    monkeypatch.setattr(DG, "verfuegbare_flaeche", lambda _w=None: flaeche)
    for name in sorted(DIALOGE):
        dlg = _zeigen(DIALOGE[name]())
        try:
            rollen = dlg.findChild(DG.InhaltsRollbereich)
            assert rollen is not None, name
            assert rollen.verticalScrollBar().maximum() == 0, (
                f"{name}: Inhalt {rollen.widget().height()} px rollt in "
                f"{rollen.viewport().height()} px")
            assert rollen.horizontalScrollBar().maximum() == 0, name
        finally:
            _zu(dlg)


def test_auf_kleinem_bildschirm_rollt_der_inhalt_statt_zu_quetschen(monkeypatch):
    """1366 x 768: der Generator braucht mehr Hoehe, als da ist — der Inhalt
    behaelt seine Mindesthoehe und rollt."""
    from src.ui.widgets import dialog_groesse as DG
    flaeche = _flaeche(1366, 768, 1)
    monkeypatch.setattr(DG, "verfuegbare_flaeche", lambda _w=None: flaeche)
    dlg = _zeigen(_generator())
    try:
        rollen = dlg.findChild(DG.InhaltsRollbereich)
        inhalt = rollen.widget()
        assert inhalt.height() >= inhalt.minimumSizeHint().height()
        assert rollen.verticalScrollBar().maximum() > 0
        # Die Tabelle passt ganz in den sichtbaren Ausschnitt.
        for tbl in _kanaltabellen(dlg):
            assert tbl.height() <= rollen.viewport().height()
    finally:
        _zu(dlg)


def test_eigene_groesse_vor_dem_zeigen_bleibt(monkeypatch):
    """Wer vor ``show()`` selbst ``resize()`` ruft, behaelt seine Groesse."""
    from src.ui.widgets import dialog_groesse as DG
    monkeypatch.setattr(DG, "verfuegbare_flaeche",
                        lambda _w=None: _flaeche(1920, 1080, 1))
    dlg = _generator()
    dlg.resize(1210, 905)
    _zeigen(dlg)
    try:
        assert (dlg.width(), dlg.height()) == (1210, 905)
    finally:
        _zu(dlg)


# ── Die Hilfsfunktion fuer sich ─────────────────────────────────────────────

class _Probe(QDialog):
    def __init__(self, inhalt: QSize, mindest: QSize | None = None):
        super().__init__()
        from src.ui.widgets.dialog_groesse import InhaltsRollbereich
        w = QWidget()
        w.setMinimumSize(inhalt)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.rollen = InhaltsRollbereich(w)
        lay.addWidget(self.rollen)
        if mindest is not None:
            self.setMinimumSize(mindest)

    def showEvent(self, e):
        from src.ui.widgets.dialog_groesse import beim_ersten_zeigen_anpassen
        beim_ersten_zeigen_anpassen(self)
        super().showEvent(e)


def test_hilfsfunktion_rechnet_mit_dem_inhalt_nicht_mit_festen_zahlen(monkeypatch):
    """Waechst der Inhalt (z. B. um eine Reiterleiste), waechst der Dialog mit
    — bis an den Bildschirm, nie darueber."""
    _app()
    from src.ui.widgets import dialog_groesse as DG
    flaeche = _flaeche(1920, 1080, 1)
    monkeypatch.setattr(DG, "verfuegbare_flaeche", lambda _w=None: flaeche)
    groessen = []
    for hoehe in (600, 700, 5000):
        dlg = _zeigen(_Probe(QSize(1100, hoehe)))
        groessen.append((dlg.width(), dlg.height()))
        dlg.close()
        dlg.deleteLater()
    assert groessen[0] == (1100, 600)
    assert groessen[1] == (1100, 700)
    grenze = DG.groesste_fenstergroesse(None)
    assert groessen[2][1] == grenze.height() < flaeche.height()


def test_hilfsfunktion_zieht_zu_grosses_mindestmass_herunter(monkeypatch):
    _app()
    from src.ui.widgets import dialog_groesse as DG
    flaeche = _flaeche(1366, 768, 1)
    monkeypatch.setattr(DG, "verfuegbare_flaeche", lambda _w=None: flaeche)
    dlg = _zeigen(_Probe(QSize(400, 300), mindest=QSize(900, 2000)))
    try:
        assert dlg.height() <= flaeche.height()
        assert dlg.minimumHeight() <= flaeche.height()
        assert dlg.minimumWidth() == 900          # was passt, bleibt
    finally:
        dlg.close()
        dlg.deleteLater()


def test_verfuegbare_flaeche_nimmt_den_bildschirm_des_elternfensters():
    _app()
    from src.ui.widgets.dialog_groesse import verfuegbare_flaeche
    eltern = QWidget()
    kind = QDialog(eltern)
    try:
        erwartet = eltern.screen().availableGeometry()
        assert verfuegbare_flaeche(kind) == erwartet
        assert verfuegbare_flaeche(None).isValid()
    finally:
        kind.deleteLater()
        eltern.deleteLater()


def test_mindestzeilen_aus_kopf_und_zeilenhoehe():
    _app()
    from src.ui.widgets.dialog_groesse import mindestzeilen_setzen
    tbl = QTableWidget(0, 3)
    try:
        h = mindestzeilen_setzen(tbl, 5)
        zeile = tbl.verticalHeader().defaultSectionSize()
        assert h >= 5 * zeile + tbl.horizontalHeader().sizeHint().height()
        assert tbl.minimumHeight() == h
    finally:
        tbl.deleteLater()
