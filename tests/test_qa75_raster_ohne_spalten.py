"""QA-75 — Raster OHNE Spalte: die Zellsuche muss von sich aus terminieren.

**Der Fehler.** ``FixtureGridWidget.first_free_cells`` sucht mit
``while len(out) < count`` und einer inneren ``for c in range(self.cols)``.
Hat das Raster keine Spalte, findet die innere Schleife nie eine Zelle, die
Abbruchbedingung wird nie wahr und ``r`` zaehlt endlos weiter — kein Absturz,
keine Meldung, der UI-Faden steht. Dieselbe Form ein Stockwerk hoeher in
``GroupEditDialog.result_positions``: ``while cols * rows < len(fids) + ...``
waechst bei ``cols == 0`` nie ueber 0 hinaus (und bei ``cols < 0`` faellt das
Produkt sogar). Beide Stellen verliessen sich allein auf eine Klemmung des
Aufrufers (``set_grid``: ``max(1, cols)``, Dialog-Konstruktor: ``max(1, ...)``).

**Gemessen am laufenden Code, vor dem Fix** (Sonde: echter Aufruf am echten
Widget, Vorbedingung per assert gesichert, Zeitlimit von aussen):

===========================  ==================  ================
Weg                          cols/_cols = 8      cols/_cols < 1
===========================  ==================  ================
``first_free_cells(13)``     0,005 ms            > 8 s, Abbruch
``result_positions()``       0,017 ms            > 8 s, Abbruch
``_add_all_fixtures()``      0,305 ms            > 20 s, Abbruch
===========================  ==================  ================

Und mit gehaertetem Raster, aber ohne den dritten Teil des Fixes, tauschte der
Aufrufer den Haenger gegen einen Absturz: ``max()`` auf dem leeren Raster warf
``ValueError: max() iterable argument is empty``.

**Warum die Haenger-Tests in Unterprozessen laufen.** Ein Test, der ohne Fix
ewig laeuft, haengt die ganze Suite auf, statt rot zu werden — der Haenger wird
deshalb mit einem Zeitlimit gemessen (``subprocess`` + ``timeout``). Ein
Rueckfall meldet sich damit als Fehlschlag in Sekunden, nicht als stehender
Testlauf. Alles, was nicht haengen KANN (die Gegenproben, der Aufrufer mit
gestubster leerer Rueckgabe), laeuft direkt im Prozess.

Alles headless (QT_QPA_PLATFORM=offscreen via conftest).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

import src.ui.views.fixture_group_view as fgv
import src.ui.widgets.group_edit_dialog as ged
from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.show.show_file import reset_show
from src.ui.views.fixture_group_view import FixtureGridWidget, FixtureGroupView
from src.ui.widgets.group_edit_dialog import GroupEditDialog, raster_ohne_spalten

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Zeitlimit fuer die Haenger-Sonden. Weit ueber jedem gemessenen Gutfall
# (0,7 s bis 1,2 s inklusive Qt-Start), aber endlich — der Sinn der Uebung.
_GRENZE_S = 20.0


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


# XPLAT-15: uebrig gebliebene Top-Level-Widgets nach JEDEM Test wirklich
# abbauen (Begruendung: tests/_qt_lifecycle.py).
import pytest as _pytest_xplat15                          # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets    # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


# ── Sonde: ein Szenario je Unterprozess, mit Zeitlimit ────────────────────────

class _Lauf:
    """Ergebnis eines Sonden-Unterprozesses. ``rc is None`` = Zeitlimit gerissen."""

    def __init__(self, rc, dauer, text):
        self.rc, self.dauer, self.text = rc, dauer, text

    def bericht(self, was: str) -> str:
        if self.rc is None:
            return (f"{was}: KEINE Rueckkehr innerhalb {_GRENZE_S:.0f} s — das ist "
                    f"der Haenger aus QA-75 (der Gutfall braucht rund 1 s).")
        return f"{was}: rc={self.rc} nach {self.dauer:.2f} s\n{self.text}"


def _sonde(rumpf: str, zusatz_env: dict | None = None) -> _Lauf:
    """Fuehrt ``rumpf`` in einem frischen Python aus und schneidet bei
    ``_GRENZE_S`` ab. Der Unterprozess erbt den Test-Sandkasten der conftest
    (Show-/Fixture-DB, APPDATA, XDG) — genau dafuer ist er dort gebaut."""
    umgebung = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    umgebung.update(zusatz_env or {})
    t0 = time.perf_counter()
    try:
        p = subprocess.run([sys.executable, "-c", rumpf], cwd=_REPO,
                           capture_output=True, text=True, timeout=_GRENZE_S,
                           env=umgebung)
    except subprocess.TimeoutExpired:
        return _Lauf(None, time.perf_counter() - t0, "")
    return _Lauf(p.returncode, time.perf_counter() - t0,
                 (p.stdout or "") + (p.stderr or ""))


_RUMPF_RASTER = """
import sys
sys.path.insert(0, __REPO__)
from PySide6.QtWidgets import QApplication
from src.ui.views.fixture_group_view import FixtureGridWidget
app = QApplication.instance() or QApplication([])
w = FixtureGridWidget()
w.set_grid(8, 8)
w.cols = __COLS__                    # DIREKT gesetzt, an set_grid vorbei
assert w.cols == __COLS__, "Vorbedingung verfehlt: cols=%r" % (w.cols,)
assert w.rows >= 1, "Vorbedingung verfehlt: rows=%r" % (w.rows,)
erg = w.first_free_cells(13)
print("QA75-OK", repr(erg))
"""

_RUMPF_DIALOG = """
import sys, json
sys.path.insert(0, __REPO__)
from PySide6.QtWidgets import QApplication
from src.ui.widgets.group_edit_dialog import GroupEditDialog
app = QApplication.instance() or QApplication([])
raster = json.dumps({"0,0": 1, "3,1": "7:2"})
d = GroupEditDialog("G", raster, 8, 2, {1: "A", 2: "B", 3: "C"})
d._add_member_item(2)
d._add_member_item(3)
d._cols = __COLS__                   # DIREKT gesetzt, an der Klemmung vorbei
assert d._cols == __COLS__, "Vorbedingung verfehlt: _cols=%r" % (d._cols,)
assert len(d.member_fids()) == 3, "Vorbedingung verfehlt: %r" % (d.member_fids(),)
assert d._head_cells, "Vorbedingung verfehlt: keine Kopf-Zelle im Ausgangsraster"
pos, cols, rows = d.result_positions()
print("QA75-OK", json.dumps([json.loads(pos), cols, rows]))
"""

# ★★★ Zwei Rumpfvarianten, die der Skeptiker erzwungen hat.
#
# Alle Sonden oben starten auf einem LEEREN Raster bzw. auf einem Dialog MIT
# Kopf-Zelle. Damit ueberlebten zwei Mutationen, die den Wachposten auf genau
# diese Sonderfaelle verengen —
#     `if raster_ohne_spalten(self.cols) and not self.positions:`
#     `if not raster_ohne_spalten(cols) or not self._head_cells:`
# — und in beiden Faellen ist der Haenger vollstaendig zurueck, waehrend alle 13
# Tests gruen bleiben. Belegt mit eigener Sonde: 10 s ohne Rueckkehr.
#
# Der GEWOEHNLICHE Fall ist ein Raster, in dem schon etwas liegt, und ein Dialog
# OHNE Kopf-Zellen. Genau der war unbeobachtet. *Eine Sonde, die nur den
# leeren Sonderfall kennt, nagelt den Wachposten nur fuer den Sonderfall fest.*

_RUMPF_RASTER_BELEGT = """
import sys
sys.path.insert(0, __REPO__)
from PySide6.QtWidgets import QApplication
from src.ui.views.fixture_group_view import FixtureGridWidget
app = QApplication.instance() or QApplication([])
w = FixtureGridWidget()
w.set_grid(8, 8)
w.positions = {(0, 0): 1, (1, 0): 2}      # das Raster ist NICHT leer
w.cols = __COLS__
assert w.cols == __COLS__, "Vorbedingung verfehlt: cols=%r" % (w.cols,)
assert w.positions, "Vorbedingung verfehlt: Raster muss belegt sein"
erg = w.first_free_cells(13)
print("QA75-OK", repr(erg))
"""

_RUMPF_DIALOG_OHNE_KOPFZELLEN = """
import sys, json
sys.path.insert(0, __REPO__)
from PySide6.QtWidgets import QApplication
from src.ui.widgets.group_edit_dialog import GroupEditDialog
app = QApplication.instance() or QApplication([])
raster = json.dumps({"0,0": 1})           # NUR ganze Geraete, keine Kopf-Zelle
d = GroupEditDialog("G", raster, 8, 2, {1: "A", 2: "B", 3: "C"})
d._add_member_item(2)
d._add_member_item(3)
d._cols = __COLS__
assert d._cols == __COLS__, "Vorbedingung verfehlt: _cols=%r" % (d._cols,)
assert len(d.member_fids()) == 3, "Vorbedingung verfehlt: %r" % (d.member_fids(),)
assert not d._head_cells, "Vorbedingung verfehlt: es gibt doch Kopf-Zellen"
pos, cols, rows = d.result_positions()
print("QA75-OK", json.dumps([json.loads(pos), cols, rows]))
"""

_RUMPF_ADD_ALL = """
import sys
sys.path.insert(0, __REPO__)
from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.show.show_file import reset_show
from src.ui.views.fixture_group_view import FixtureGroupView
app = QApplication.instance() or QApplication([])
ensure_builtins()
reset_show()
state = get_state()
with Session(fdb_engine()) as s:
    pid = int(s.execute(select(FixtureProfile.id).where(
        FixtureProfile.short_name == "ZQ01424")).scalar_one())
for i in range(3):
    state.add_fixture(PatchedFixture(
        fid=i + 1, label="PAR-%d" % (i + 1), fixture_profile_id=pid,
        mode_name="8-Kanal RGBW", universe=1, address=1 + i * 8, channel_count=8,
        manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
        fixture_type="par"), undoable=False)
v = FixtureGroupView()
v._refresh_fixtures()
gw = v._grid_widget
gw.set_grid(8, 8)
gw.positions = {}
gw.cols = __COLS__                   # DIREKT gesetzt, an set_grid vorbei
assert gw.cols == __COLS__, "Vorbedingung verfehlt: cols=%r" % (gw.cols,)
assert len(state.get_patched_fixtures()) == 3, "Vorbedingung verfehlt: kein Patch"
assert not gw.positions, "Vorbedingung verfehlt: Raster nicht leer"
v._add_all_fixtures()                # die echte UI-Aktion
print("QA75-OK", repr(dict(gw.positions)), gw.rows, gw.cols)
"""


def _rumpf(vorlage: str, cols: int) -> str:
    return vorlage.replace("__REPO__", repr(_REPO)).replace("__COLS__", str(cols))


# ── 1. Das Rasterwidget selbst ────────────────────────────────────────────────

class RasterOhneSpalteTest(unittest.TestCase):
    """``first_free_cells`` muss ohne Spalte zurueckkehren statt zu kreisen."""

    def _pruefe(self, cols: int):
        lauf = _sonde(_rumpf(_RUMPF_RASTER, cols))
        self.assertIsNotNone(lauf.rc, lauf.bericht(f"first_free_cells bei cols={cols}"))
        self.assertEqual(lauf.rc, 0, lauf.bericht(f"first_free_cells bei cols={cols}"))
        self.assertIn("QA75-OK []", lauf.text,
                      f"cols={cols} muss eine LEERE Liste liefern:\n{lauf.text}")

    def test_ohne_spalte_kehrt_zurueck(self):
        """cols = 0: gemessen der Haenger (> 8 s ohne Rueckkehr)."""
        self._pruefe(0)

    def test_negative_spaltenzahl_kehrt_zurueck(self):
        """cols = -1 haengt GENAUSO — der Wachposten muss auf ``< 1`` pruefen,
        nicht auf ``== 0``, sonst bleibt die negative Haelfte offen."""
        self._pruefe(-1)


# ── 2. Dieselbe Schleifenform im Mitglieder-Dialog ────────────────────────────

class DialogOhneSpalteTest(unittest.TestCase):
    """``result_positions`` teilt Form und Schwaeche mit ``first_free_cells``.
    Wer nur das Rasterwidget haertet, laesst diesen zweiten Weg offen."""

    def _pruefe(self, cols: int):
        lauf = _sonde(_rumpf(_RUMPF_DIALOG, cols))
        self.assertIsNotNone(lauf.rc, lauf.bericht(f"result_positions bei _cols={cols}"))
        self.assertEqual(lauf.rc, 0, lauf.bericht(f"result_positions bei _cols={cols}"))
        zeile = [z for z in lauf.text.splitlines() if z.startswith("QA75-OK ")]
        self.assertTrue(zeile, f"keine Ergebniszeile:\n{lauf.text}")
        positionen, zurueck_cols, zurueck_rows = json.loads(zeile[0][len("QA75-OK "):])
        self.assertEqual(positionen, {"3,1": "7:2"},
                         "ohne Spalte gibt es keine Zelle fuer ganze Mitglieder — "
                         "die Kopf-Zelle bleibt aber VERBATIM erhalten (FM-16e)")
        self.assertEqual([zurueck_cols, zurueck_rows], [cols, 2],
                         "ohne Spalte darf die Reihenzahl nicht wachsen")

    def test_ohne_spalte_kehrt_zurueck(self):
        self._pruefe(0)

    def test_negative_spaltenzahl_kehrt_zurueck(self):
        self._pruefe(-1)


# ── 3. Der Aufrufer muss die leere Rueckgabe ueberleben ───────────────────────

class AddAllFixturesLeeresRasterTest(unittest.TestCase):
    """Ein Fix, der den Haenger gegen einen Absturz tauscht, ist kein Fix."""

    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        with Session(fdb_engine()) as s:
            pid = int(s.execute(select(FixtureProfile.id).where(
                FixtureProfile.short_name == "ZQ01424")).scalar_one())
        for i in range(3):
            self.state.add_fixture(PatchedFixture(
                fid=i + 1, label=f"PAR-{i+1}", fixture_profile_id=pid,
                mode_name="8-Kanal RGBW", universe=1, address=1 + i * 8,
                channel_count=8, manufacturer_name="Generic",
                fixture_name="Stage Light ZQ01424", fixture_type="par"),
                undoable=False)
        self.view = FixtureGroupView()
        self.view._refresh_fixtures()

    def test_leere_rueckgabe_wirft_nicht(self):
        """Der gemessene ValueError: ``max()`` lief auf dem leeren Raster.

        Kein Haenger moeglich — ``first_free_cells`` ist hier durch eine leere
        Rueckgabe ersetzt; geprueft wird ALLEIN der Aufrufer."""
        gw = self.view._grid_widget
        gw.set_grid(8, 4)
        self.view._spin_rows.setValue(4)
        gw.positions = {}
        gw.first_free_cells = lambda count: []
        self.assertEqual(gw.first_free_cells(3), [],
                         "Vorbedingung verfehlt: Rueckgabe nicht leer")
        self.assertEqual(gw.positions, {}, "Vorbedingung verfehlt: Raster nicht leer")
        self.assertTrue(self.state.get_patched_fixtures(),
                        "Vorbedingung verfehlt: nichts zu platzieren")

        self.view._add_all_fixtures()      # darf NICHT werfen

        self.assertEqual(gw.positions, {}, "ohne freie Zelle wird nichts platziert")
        self.assertEqual(gw.rows, 4, "ohne Zelle waechst das Raster nicht")
        self.assertEqual(self.view._spin_rows.value(), 4, "Spinbox unangetastet")

    def test_echte_ui_aktion_kehrt_bei_rasterbreite_null_zurueck(self):
        """Der ganze Weg, nicht nur die Hilfsfunktion: gemessen stand
        ``_add_all_fixtures`` bei cols=0 ueber 20 s im UI-Faden."""
        lauf = _sonde(_rumpf(_RUMPF_ADD_ALL, 0))
        self.assertIsNotNone(lauf.rc, lauf.bericht("_add_all_fixtures bei cols=0"))
        self.assertEqual(lauf.rc, 0, lauf.bericht("_add_all_fixtures bei cols=0"))
        self.assertIn("QA75-OK {} 8 0", lauf.text,
                      f"Raster muss leer und unveraendert bleiben:\n{lauf.text}")


# ── 4. Gegenproben: was sich NICHT aendern darf ───────────────────────────────

class GegenprobeTest(unittest.TestCase):
    """Ein Wachposten, der zu frueh zuschlaegt, „behebt" den Haenger, indem er
    die Funktion abschaltet. Diese Tests nageln den Normalfall fest."""

    def _raster(self, cols=8, rows=1) -> FixtureGridWidget:
        _app()
        w = FixtureGridWidget()
        w.set_grid(cols, rows)
        return w

    def test_normales_raster_liefert_dieselben_zellen(self):
        w = self._raster(4, 2)
        w.positions = {(0, 0): 1, (1, 0): 2}
        self.assertEqual(w.first_free_cells(3), [(2, 0), (3, 0), (0, 1)],
                         "belegte Zellen weiterhin ueberspringen, Rest unveraendert")

    def test_reihen_wachsen_weiterhin_ueber_das_raster_hinaus(self):
        w = self._raster(8, 1)
        zellen = w.first_free_cells(13)
        self.assertEqual(len(zellen), 13)
        self.assertEqual(len(set(zellen)), 13, "keine Doppel")
        self.assertTrue(any(r >= 1 for (_c, r) in zellen),
                        "Reihen wachsen weiterhin virtuell nach unten")

    def test_eine_einzige_spalte_bleibt_ein_gueltiges_raster(self):
        """Nagelt ``< 1`` gegen ein zu breites ``< 2``: cols=1 ist gueltig."""
        w = self._raster(1, 1)
        self.assertEqual(w.first_free_cells(3), [(0, 0), (0, 1), (0, 2)])

    def test_set_grid_klemmt_weiterhin(self):
        """Die Klemmung eine Ebene hoeher bleibt — sie ist richtig, sie war nur
        nicht die einzige noetige Zusicherung."""
        w = self._raster(8, 4)
        w.set_grid(0, 4)
        self.assertEqual(w.cols, 1, "set_grid(0, r) klemmt auf 1")
        w.set_grid(-7, 4)
        self.assertEqual(w.cols, 1, "set_grid(-7, r) klemmt auf 1")
        w.set_grid(64, 4)
        self.assertEqual(w.cols, 64, "gueltige Werte bleiben unangetastet")

    def test_dialog_klemmt_weiterhin(self):
        _app()
        d = GroupEditDialog("G", "{}", 0, 1, {1: "A"})
        self.assertEqual(d._cols, 1, "Konstruktor klemmt weiterhin auf 1")

    def test_dialog_ergaenzt_weiterhin_reihen(self):
        """Die Wachstumsschleife muss im Normalfall unveraendert laufen."""
        _app()
        d = GroupEditDialog("G", json.dumps({"0,0": 1}), 2, 1,
                            {1: "A", 2: "B", 3: "C"})
        d._add_member_item(2)
        d._add_member_item(3)
        self.assertEqual(len(d.member_fids()), 3, "Vorbedingung: drei Mitglieder")
        pos, cols, rows = d.result_positions()
        self.assertEqual((cols, rows), (2, 2),
                         "3 Mitglieder in 2 Spalten -> Reihen wachsen auf 2")
        self.assertEqual(len(json.loads(pos)), 3, "alle drei bekommen eine Zelle")

    def test_beide_stellen_fragen_dieselbe_funktion(self):
        """EINE Frage, EINE Stelle: Rasterwidget und Dialog duerfen nicht mit
        zwei Kopien derselben Bedingung auseinanderlaufen."""
        self.assertIs(fgv.raster_ohne_spalten, ged.raster_ohne_spalten,
                      "beide Aufrufer muessen denselben Wachposten benutzen")
        for cols, erwartet in ((-7, True), (-1, True), (0, True),
                               (1, False), (2, False), (64, False)):
            self.assertIs(raster_ohne_spalten(cols), erwartet,
                          f"raster_ohne_spalten({cols}) falsch beantwortet")


if __name__ == "__main__":
    unittest.main()


class AuchImGEWOEHNLICHENFallTest(unittest.TestCase):
    """★★★ Vom Skeptiker erzwungen: der Wachposten muss auch dann greifen, wenn
    das Raster schon belegt ist bzw. der Dialog keine Kopf-Zellen hat.

    Zwei Mutationen, die genau darauf verengten, liessen alle 13 Tests gruen —
    und der Haenger war vollstaendig zurueck (10 s ohne Rueckkehr, gemessen).
    """

    def test_belegtes_raster_ohne_spalte_kehrt_zurueck(self):
        for cols in (0, -1):
            with self.subTest(cols=cols):
                lauf = _sonde(_rumpf(_RUMPF_RASTER_BELEGT, cols))
                self.assertEqual(0, lauf.rc,
                                 f"keine Rueckkehr bei cols={cols} auf einem "
                                 f"BELEGTEN Raster: {lauf.text[-300:]}")

    def test_dialog_ohne_kopfzellen_kehrt_zurueck(self):
        for cols in (0, -1):
            with self.subTest(cols=cols):
                lauf = _sonde(_rumpf(_RUMPF_DIALOG_OHNE_KOPFZELLEN, cols))
                self.assertEqual(0, lauf.rc,
                                 f"keine Rueckkehr bei _cols={cols} ohne "
                                 f"Kopf-Zellen: {lauf.text[-300:]}")

    def test_belegtes_raster_bleibt_im_normalfall_unveraendert(self):
        """Gegenprobe: die neue Sonde darf den Gutfall nicht mitbewegen."""
        lauf = _sonde(_rumpf(_RUMPF_RASTER_BELEGT, 8))
        self.assertEqual(0, lauf.rc, lauf.text[-300:])
        self.assertIn("QA75-OK", lauf.text)
