"""FM-51 (Gruppe „programmer"): Toolbar-Aktionen des Programmers bei reiner
Weiss-Auswahl.

Ein Geraet, das nur ueber Weiss-Zellen (``"1:w3"``) gewaehlt ist, steht bewusst
NICHT in ``AppState.selected_fids`` — die View-eigene Liste ``_selected_fids``
fuehrt es aber (sie kommt aus den Zellen). Highlight, Kopieren und Einfuegen
behandelten es deshalb als GANZES Geraet: Highlight setzte intensity/pan/tilt und
RGB=255 auf alle 48 Zonen, Kopieren nahm den kompletten Programmer-Eintrag mit,
Einfuegen eines PAR-Clips faerbte alle 48 Zonen.

Soll: fuer nur-weiss gewaehlte Geraete wirken diese Aktionen nur auf die
gewaehlten Segmente (``weiss_setzen``); ganze Geraete wie bisher. Je Stelle eine
Positivkontrolle.

Echter Weg: eingebaute Profile, echter AppState, echter Programmer.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                         # noqa: E402
from sqlalchemy import select                                       # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

from src.core.app_state import get_state                            # noqa: E402
from src.core.database.fixture_db import engine, ensure_builtins    # noqa: E402
from src.core.database.models import FixtureProfile, PatchedFixture  # noqa: E402
from src.core.show.show_file import reset_show                      # noqa: E402

_app = QApplication.instance() or QApplication([])
BALKEN_MODUS = "154-Kanal 48 Zonen RGB + 8x Weiss"
RGB_KANAELE = range(3, 147)          # die 48 RGB-Zonen des Balkens (Adresse 1)


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
        self.addCleanup(self.st.set_selected_fids, [])
        from src.ui.views.programmer_view import ProgrammerView
        self.v = ProgrammerView()
        self.addCleanup(self.v.deleteLater)

    def _waehle(self, zellen):
        self.st.set_selected_cells(list(zellen))
        self.v._sync_follow_selection()

    def _kanal(self, n):
        return self.st.output_manager.universes[1].get_channel(n)

    def _prog(self, fid):
        return dict(self.st.programmer.get(fid, {}))

    def _rgb_im_programmer(self, fid):
        return {k: v for k, v in self._prog(fid).items()
                if k.split("#", 1)[0] in ("color_r", "color_g", "color_b")}


class HighlightTest(_Basis):

    def test_nur_weiss_macht_nur_das_segment_hell(self):
        self._waehle(["1:w3"])
        self.assertIn(1, self.v._selected_fids)        # View fuehrt das Geraet
        self.v._highlight()
        p = self._prog(1)
        self.assertEqual(self._rgb_im_programmer(1), {}, "RGB-Zonen geschrieben")
        for attr in ("pan", "tilt"):
            self.assertNotIn(attr, p)
        self.assertEqual(p.get(self.st.weiss_programmer_key(1, 3)), 255)
        dk = self.st.weiss_dimmer_key(1, 3)
        self.assertTrue(dk)
        self.assertEqual(p.get(dk), 255)
        self.assertEqual(p.get(self.st.weiss_programmer_key(1, 1)), 0,
                         "uebrige Segmente muessen verankert (0) sein")
        self.assertEqual([self._kanal(c) for c in RGB_KANAELE], [0] * 144,
                         "eine RGB-Zone leuchtet mit")
        self.assertEqual(self._kanal(150), 255)
        self.assertEqual(self._kanal(148), 0)
        self.assertNotIn(2, self.st.programmer)

    def test_positiv_ganzes_geraet_wie_bisher(self):
        self._waehle(["2"])
        self.v._highlight()
        p = self._prog(2)
        for attr in ("intensity", "color_r", "color_g", "color_b"):
            self.assertEqual(p.get(attr), 255)
        self.assertNotIn(1, self.st.programmer)

    def test_positiv_leere_auswahl_tut_nichts(self):
        self._waehle([])
        self.v._highlight()
        self.assertEqual(dict(self.st.programmer), {})


class LowlightTest(_Basis):

    def test_nur_weiss_geraet_bleibt_ausgenommen(self):
        self._waehle(["1:w3"])
        self.v._lowlight()
        self.assertEqual(self._prog(2).get("intensity"), 76)
        self.assertNotIn("intensity", self._prog(1))

    def test_positiv_anderes_geraet_gewaehlt(self):
        self._waehle(["2"])
        self.v._lowlight()
        self.assertEqual(self._prog(1).get("intensity"), 76)
        self.assertNotIn("intensity", self._prog(2))


class KopierenTest(_Basis):

    def _balken_belegen(self):
        self.st.set_programmer_value(1, "color_r", 200)
        self.st.set_programmer_value(1, "intensity", 180)
        self.st.weiss_setzen(1, 1, 50)
        self.st.weiss_setzen(1, 3, 200)

    def test_nur_weiss_kopiert_nur_das_segment(self):
        self._balken_belegen()
        self._waehle(["1:w3"])
        self.v._copy_to_clipboard()
        self.assertEqual(self.v._clipboard,
                         {1: {self.st.weiss_programmer_key(1, 3): 200}})

    def test_positiv_ganzes_geraet_kopiert_alles(self):
        self._balken_belegen()
        self._waehle(["1"])
        self.v._copy_to_clipboard()
        self.assertEqual(self.v._clipboard, {1: self._prog(1)})
        self.assertIn("color_r", self.v._clipboard[1])


class EinfuegenTest(_Basis):

    def _par_clip(self, mit_weiss=True):
        self.st.set_programmer_value(2, "color_r", 255)
        self.st.set_programmer_value(2, "intensity", 255)
        if mit_weiss:
            self.st.set_programmer_value(2, "color_w", 100)
        self._waehle(["2"])
        self.v._copy_to_clipboard()

    def test_par_clip_auf_weiss_segment_faerbt_keine_zone(self):
        self._par_clip()
        self._waehle(["1:w4"])
        self.v._paste_from_clipboard()
        p = self._prog(1)
        self.assertEqual(self._rgb_im_programmer(1), {}, "RGB eingefuegt")
        self.assertNotIn("intensity", p)
        self.assertEqual(p.get(self.st.weiss_programmer_key(1, 4)), 100)
        self.assertEqual(p.get(self.st.weiss_programmer_key(1, 0)), 0,
                         "Basis-Schluessel nicht verankert -> alle Segmente fahren mit")
        self.assertEqual([self._kanal(c) for c in RGB_KANAELE], [0] * 144)
        self.assertEqual(self._kanal(151), 100)
        self.assertEqual(self._kanal(147), 0)

    def test_clip_ohne_weiss_schreibt_nichts(self):
        self._par_clip(mit_weiss=False)
        self._waehle(["1:w4"])
        self.v._paste_from_clipboard()
        self.assertEqual(self._prog(1), {})

    def test_balken_segment_auf_balken_segment(self):
        self.st.weiss_setzen(1, 3, 200)
        self.st.set_programmer_value(1, "color_r", 120)
        self._waehle(["1:w3"])
        self.v._copy_to_clipboard()
        self.st.clear_programmer()
        self._waehle(["1:w5"])
        self.v._paste_from_clipboard()
        p = self._prog(1)
        self.assertEqual(p.get(self.st.weiss_programmer_key(1, 5)), 200)
        self.assertNotIn("color_r", p)

    def test_positiv_ganzes_geraet_wie_bisher(self):
        self._par_clip()
        self._waehle(["1"])
        self.v._paste_from_clipboard()
        p = self._prog(1)
        self.assertEqual(p.get("color_r"), 255)
        self.assertEqual(p.get("intensity"), 255)


if __name__ == "__main__":
    unittest.main()
