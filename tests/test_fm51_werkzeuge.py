"""FM-51 (Gruppe „werkzeuge"): reine Weiss-Auswahl ist NICHT „nichts gewaehlt".

Ein Geraet, das nur ueber Weiss-Zellen (``"1:w3"``) gewaehlt ist, steht bewusst
nicht in ``selected_fids``. Positions-, Spider-, Farb- und Faecher-Werkzeug
deuteten die dann leere fid-Liste als „nichts gewaehlt" und fielen auf die
Programmer-Geraete (bzw. das ganze Rig) zurueck: pan/tilt auf dem Balken und
auf fremden Geraeten, RGB auf allen 48 Zonen plus color_w=0 auf dem Balken.

Soll: diese Werkzeuge bedienen die Weiss-Achse nicht und tun bei reiner
Weiss-Auswahl NICHTS. Der alte Rueckfall gilt nur noch bei wirklich leerer
Auswahl (``AppState.auswahl_ziel_fids``). Je Werkzeug eine Positivkontrolle.

Echter Weg: eingebaute Profile, echter AppState, echter Programmer.
"""
import copy
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor                                    # noqa: E402
from PySide6.QtWidgets import QApplication                         # noqa: E402
from sqlalchemy import select                                       # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

from src.core.app_state import get_state                            # noqa: E402
from src.core.database.fixture_db import engine, ensure_builtins    # noqa: E402
from src.core.database.models import FixtureProfile, PatchedFixture  # noqa: E402
from src.core.show.show_file import reset_show                      # noqa: E402

_app = QApplication.instance() or QApplication([])
BALKEN_MODUS = "154-Kanal 48 Zonen RGB + 8x Weiss"


def _pid(short):
    with Session(engine()) as s:
        return s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first()


class _Basis(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        ensure_builtins()

    def setUp(self):
        reset_show()
        self.st = get_state()
        self.st.add_fixture(PatchedFixture(
            fid=1, label="Balken", fixture_profile_id=_pid("ZQ06121"),
            mode_name=BALKEN_MODUS, universe=1, address=1, channel_count=154,
            fixture_type="matrix"), undoable=False)
        self.st.add_fixture(PatchedFixture(
            fid=2, label="PAR", fixture_profile_id=_pid("ZQ01424"),
            mode_name="8-Kanal RGBW", universe=1, address=200, channel_count=8,
            fixture_type="par"), undoable=False)
        self.addCleanup(self.st.set_selected_cells, [])
        self.addCleanup(self.st.clear_programmer)

    def _nur_weiss_mit_rest(self):
        """Auswahl ``["1:w3"]``, Segment gesetzt (fid 1 steht im Programmer),
        PAR-Rest in fid 2 — genau der Zustand aus der Bestandsaufnahme."""
        self.st.set_selected_cells(["1:w3"])
        self.assertEqual(self.st.get_selected_fids(), [])
        self.assertTrue(self.st.weiss_setzen(1, 3, 200))
        self.st.set_programmer_value(2, "intensity", 77)
        self.assertEqual(sorted(self.st.programmer.keys()), [1, 2])

    def _prog(self):
        return copy.deepcopy({k: dict(v) for k, v in self.st.programmer.items()})

    def _widget(self, cls, *a, **kw):
        w = cls(*a, **kw)
        self.addCleanup(w.deleteLater)
        return w


class PositionToolTest(_Basis):

    def _tool(self):
        from src.ui.widgets.position_tool import PositionTool
        pt = self._widget(PositionTool)
        pt._pan, pt._tilt, pt._pan_fine, pt._tilt_fine = 140, 90, 5, 6
        return pt

    def test_reine_weiss_auswahl_schreibt_kein_pan(self):
        self._nur_weiss_mit_rest()
        vorher = self._prog()
        self._tool()._apply_to_selection()
        self.assertEqual(self._prog(), vorher)
        for fid, werte in self.st.programmer.items():
            self.assertNotIn("pan", werte, f"pan auf fid {fid}")

    def test_reine_weiss_auswahl_leerer_programmer_nicht_das_ganze_rig(self):
        self.st.set_selected_cells(["1:w3"])
        self._tool()._apply_to_selection()
        self.assertEqual(dict(self.st.programmer), {})

    def test_leere_auswahl_faellt_wie_bisher_zurueck(self):
        """Positivkontrolle: wirklich leer + leerer Programmer -> alle Geraete."""
        self.st.set_selected_cells([])
        self._tool()._apply_to_selection()
        self.assertEqual(sorted(self.st.programmer.keys()), [1, 2])
        self.assertEqual(self.st.programmer[2].get("pan"), 140)

    def test_ganzes_geraet_wie_bisher(self):
        self.st.set_selected_cells(["2", "1:w3"])
        self._tool()._apply_to_selection()
        self.assertEqual(self.st.programmer[2].get("pan"), 140)
        self.assertNotIn("pan", self.st.programmer.get(1, {}))


class SpiderPositionToolTest(_Basis):
    """Unter den eingebauten Testprofilen gibt es keinen Doppeltilter; die
    Erkennung wird im Werkzeug-Modul fuer fid 2 umgebogen (nur die Erkennung,
    Schreibweg und Programmer bleiben echt)."""

    def setUp(self):
        super().setUp()
        import src.ui.widgets.spider_position_tool as spt
        alt_dual, alt_n = spt.is_dual_tilt_fixture, spt.tilt_head_count
        spt.is_dual_tilt_fixture = lambda fx: getattr(fx, "fid", None) == 2
        spt.tilt_head_count = lambda fx: 2
        self.addCleanup(setattr, spt, "is_dual_tilt_fixture", alt_dual)
        self.addCleanup(setattr, spt, "tilt_head_count", alt_n)

    def _tool(self):
        from src.ui.widgets.spider_position_tool import SpiderPositionTool
        t = self._widget(SpiderPositionTool, head_count=2)
        t._tilts = [200, 50]
        return t

    def _tilt2(self):
        return {k: v for k, v in self.st.programmer.get(2, {}).items()
                if k.startswith("tilt")}

    def test_reine_weiss_auswahl_bewegt_fremden_spider_nicht(self):
        self._nur_weiss_mit_rest()
        self.st.set_programmer_value(2, "tilt", 10)
        vorher = self._tilt2()
        self._tool()._apply_to_selection()
        self.assertEqual(self._tilt2(), vorher)

    def test_leere_auswahl_faellt_wie_bisher_zurueck(self):
        self.st.set_selected_cells([])
        self.st.set_programmer_value(2, "tilt", 10)
        self._tool()._apply_to_selection()
        self.assertNotEqual(self._tilt2(), {"tilt": 10})


class ColorPickerTest(_Basis):

    def _picker(self):
        from src.ui.widgets.color_picker import ColorPicker
        cp = self._widget(ColorPicker)
        cp._color = QColor(255, 0, 0)
        return cp

    def test_reine_weiss_auswahl_faerbt_nichts(self):
        self._nur_weiss_mit_rest()
        vorher = self._prog()
        self._picker()._apply_to_selection()
        self.assertEqual(self._prog(), vorher)
        for fid in (1, 2):
            self.assertNotIn("color_r", self.st.programmer.get(fid, {}))

    def test_leere_auswahl_faellt_auf_programmer_zurueck(self):
        """Positivkontrolle: wirklich leer -> Programmer-Geraete (nicht alle)."""
        self.st.set_selected_cells([])
        self.st.set_programmer_value(2, "intensity", 77)
        self._picker()._apply_to_selection()
        self.assertEqual(self.st.programmer[2].get("color_r"), 255)
        self.assertNotIn(1, self.st.programmer)

    def test_ganzes_geraet_wie_bisher(self):
        self.st.set_selected_cells(["2", "1:w3"])
        self._picker()._apply_to_selection()
        self.assertEqual(self.st.programmer[2].get("color_r"), 255)
        self.assertNotIn("color_r", self.st.programmer.get(1, {}))


class FanToolTest(_Basis):

    def _fan(self):
        from src.ui.widgets.fan_tool import FanTool
        ft = self._widget(FanTool)
        for i in range(ft._combo_attr.count()):
            if ft._combo_attr.itemData(i) == "intensity":
                ft._combo_attr.setCurrentIndex(i)
        return ft

    def test_weiss_zellen_sind_keine_ziele(self):
        self._nur_weiss_mit_rest()
        ft = self._fan()
        ft.set_cells(["1:w3"])
        self.assertEqual(ft._selected_fids, [])
        ft._refresh_table()
        self.assertEqual(ft._selected_fids, [])
        self.assertEqual(ft._table.rowCount(), 0)
        vorher = self._prog()
        ft._apply()
        self.assertEqual(self._prog(), vorher)

    def test_neu_laden_bei_reiner_weiss_auswahl_bleibt_leer(self):
        self._nur_weiss_mit_rest()
        ft = self._fan()
        self.assertEqual(ft._selected_fids, [])  # Konstruktor-Rueckfall
        ft._reload_from_programmer()
        self.assertEqual(ft._selected_fids, [])

    def test_gemischt_nur_ganze_geraete_und_koepfe(self):
        self.st.set_selected_cells(["1:w3", "2", "1:4"])
        ft = self._fan()
        ft.set_cells(self.st.get_selected_cells())
        self.assertEqual(ft._selected_fids, [2, 1])
        self.assertEqual(ft._selected_heads, [None, 4])

    def test_leere_auswahl_faellt_wie_bisher_zurueck(self):
        """Positivkontrolle: wirklich leer -> Programmer-Geraete als Ziele."""
        self.st.set_selected_cells([])
        self.st.set_programmer_value(2, "intensity", 77)
        ft = self._fan()
        ft.set_selection([])
        self.assertEqual(ft._selected_fids, [2])
        ft._reload_from_programmer()
        self.assertEqual(ft._selected_fids, [2])


if __name__ == "__main__":
    unittest.main()
