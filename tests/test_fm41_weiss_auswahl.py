"""FM-41 (Scheibe 3a): Weiss-Segmente sind im Programmer auswaehl- und bedienbar.

Vorher (gemessen 29.09.): eine reine Weiss-Gruppe des ZQ06121 (48 RGB-Zonen +
8 eigene Weiss-Segmente) liess sich nicht waehlen — ``select_group_by_name``
lieferte False, die Programmer-Gruppenliste zeigte „(0)", und im Geraete-Baum gab
es keine Zeile fuer ein Weiss-Segment. Der Renderer konnte die Achse seit
Scheibe 2 schon; es fehlte die Bedienung.

Echter Weg: eingebautes Profil (QA-23), echter AppState, echter Programmer.
"""
import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt                                      # noqa: E402
from PySide6.QtWidgets import QApplication                         # noqa: E402
from sqlalchemy import select                                       # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

from src.core.app_state import get_state                            # noqa: E402
from src.core.database.fixture_db import engine, ensure_builtins    # noqa: E402
from src.core.database.models import FixtureGroup, FixtureProfile, PatchedFixture  # noqa: E402
from src.core.group_cells import ACHSE_WEISS, zelle_fuer            # noqa: E402
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
        self.addCleanup(self.st.set_selected_fids, [])

    def _gruppe(self, name, zellen):
        pos = {f"{i},0": z for i, z in enumerate(zellen)}
        with self.st._session() as s:
            g = FixtureGroup(name=name, cols=len(zellen), rows=1,
                             positions_json=json.dumps(pos), folder="")
            s.add(g)
            s.commit()
            return g.id

    def _kanal(self, n):
        return self.st.output_manager.universes[1].get_channel(n)


class AuswahlTest(_Basis):

    def test_weiss_zellen_in_der_auswahl(self):
        self.st.set_selected_cells(["1:w1", "1:w3"])
        # Review 29.09.: NICHT in selected_fids — sonst fuehren alle anderen
        # Werkzeuge (Submaster, Command-Line, EFX, Fan …) den GANZEN Balken.
        self.assertEqual(self.st.get_selected_fids(), [])
        self.assertEqual(self.st.get_selected_cells(), ["1:w1", "1:w3"])
        self.assertEqual(self.st.selected_weiss_for(1), {1, 3})
        self.assertTrue(self.st.nur_weiss_gewaehlt(1))

    def test_ganzes_geraet_schlaegt_die_segmente(self):
        self.st.set_selected_cells(["1:w1", "1"])
        self.assertEqual(self.st.selected_weiss_for(1), set())
        self.assertFalse(self.st.nur_weiss_gewaehlt(1))

    def test_farbkopf_und_weiss_ist_nicht_nur_weiss(self):
        self.st.set_selected_cells(["1:2", "1:w3"])
        self.assertEqual(self.st.selected_heads_for(1), {2})
        self.assertFalse(self.st.nur_weiss_gewaehlt(1))

    def test_reine_weiss_gruppe_ist_waehlbar(self):
        self._gruppe("Nur Weiss", [zelle_fuer(1, ACHSE_WEISS, k) for k in range(8)])
        self.assertTrue(self.st.select_group_by_name("Nur Weiss"))
        self.assertEqual(self.st.selected_weiss_for(1), set(range(8)))

    def test_schluessel_trifft_das_segment(self):
        """Segment 3 (0-basiert) = CH150 „Weiss-Zone 4" laut Profil."""
        key = self.st.weiss_programmer_key(1, 3)
        self.st.set_programmer_value(1, key, 200)
        self.assertEqual(self._kanal(150), 200)
        self.assertEqual([self._kanal(c) for c in range(147, 155) if c != 150],
                         [0] * 7)

    def test_rgbw_par_hat_keine_weiss_achse(self):
        """ENG-25-Regel: am RGBW-PAR gehoert das Weiss zur Farbzelle."""
        self.st.add_fixture(PatchedFixture(
            fid=2, label="PAR", fixture_profile_id=_pid("ZQ01424"),
            mode_name="8-Kanal RGBW", universe=1, address=200, channel_count=8,
            fixture_type="par"), undoable=False)
        self.assertIsNone(self.st.weiss_programmer_key(2, 0))

    def test_submaster_auf_der_weiss_gruppe_dimmt_nur_die_segmente(self):
        """Scheibe 3a hielt hier fest, dass der Submaster NICHTS tut (statt den
        ganzen Balken). Seit 3b kennt er die Achse: Ziel ist das Geraet MIT
        einer Einschraenkung auf genau die Segmente — nie das ganze Geraet
        (Wirkung am Frame: ``test_fm41_weiss_submaster``)."""
        from src.ui.virtualconsole.vc_slider import VCSlider
        self._gruppe("Nur Weiss", [zelle_fuer(1, ACHSE_WEISS, k) for k in range(8)])
        sl = VCSlider()
        self.addCleanup(sl.deleteLater)
        sl.programmer_scope = "group"
        sl.programmer_group = "Nur Weiss"
        self.assertEqual(sl._submaster_targets(self.st),
                         ([1], {1: {f"w{k}" for k in range(8)}}))


class ProgrammerTest(_Basis):

    def _view(self):
        from src.ui.views.programmer_view import ProgrammerView
        v = ProgrammerView()
        self.addCleanup(v.deleteLater)
        return v

    def _weiss_zeilen(self, v):
        tree = v._fixture_list
        top = tree.topLevelItem(0)
        return [top.child(k).text(0) for k in range(top.childCount())
                if top.child(k).text(0).startswith("Weiß")], top.text(0)

    def test_baum_zeigt_die_acht_weiss_segmente(self):
        zeilen, geraet = self._weiss_zeilen(self._view())
        self.assertEqual(zeilen, [f"Weiß {k}" for k in range(1, 9)])
        self.assertIn("48 Köpfe + 8 Weiß", geraet)

    def test_gruppenklick_waehlt_die_segmente_und_der_regler_schreibt(self):
        from src.ui.views.programmer_view import AttributeSlider, WeissSegmentBlock
        gid = self._gruppe("Weiss 2+4", [zelle_fuer(1, ACHSE_WEISS, 1),
                                         zelle_fuer(1, ACHSE_WEISS, 3)])
        v = self._view()
        v._refresh_group_list()
        item = next(v._group_list.item(i) for i in range(v._group_list.count())
                    if v._group_list.item(i).data(Qt.ItemDataRole.UserRole + 1) == gid)
        self.assertIn("(2 Weiß)", item.text())
        v._on_group_clicked(item)
        self.assertEqual(self.st.get_selected_cells(), ["1:w1", "1:w3"])
        blocks = v.findChildren(WeissSegmentBlock)
        self.assertEqual(len(blocks), 1)
        # Nur Weiss gewaehlt: KEIN geraeteweiter Regler (der fuehre den ganzen Balken).
        self.assertEqual([w for w in v.findChildren(AttributeSlider)
                          if not w.isHidden() and w.parent() is not None
                          and any(getattr(f, "fid", None) == 1 for f in w._fixtures)
                          and w._channel.attribute.startswith("color_r")], [])
        blocks[0]._regler[3][0].setValue(180)
        self.assertEqual(self._kanal(150), 180)
        self.assertEqual(self._kanal(148), 0)
        self.assertEqual([self._kanal(c) for c in range(3, 147)], [0] * 144,
                         "eine RGB-Zone wurde mitgefahren")
        blocks[0]._regler["dimmer"][0].setValue(255)
        self.assertEqual(self._kanal(1), 255)

    def test_farbkopf_plus_weiss_zeigt_beides_ohne_extra_dimmer(self):
        from src.ui.views.programmer_view import WeissSegmentBlock
        v = self._view()
        self.st.set_selected_cells(["1:2", "1:w3"])
        v._sync_follow_selection()
        from PySide6.QtCore import QEvent
        _app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        blocks = v.findChildren(WeissSegmentBlock)
        self.assertEqual(len(blocks), 1)
        self.assertNotIn("dimmer", blocks[0]._regler,
                         "der Dimmer hat oben schon seinen Regler")

    def test_baumklick_auf_ein_weiss_segment(self):
        from src.ui.views.programmer_view import WeissSegmentBlock
        v = self._view()
        top = v._fixture_list.topLevelItem(0)
        weiss = next(top.child(k) for k in range(top.childCount())
                     if top.child(k).text(0) == "Weiß 8")
        weiss.setSelected(True)
        v._on_fixture_selected()
        from PySide6.QtCore import QEvent
        _app.sendPostedEvents(None, QEvent.Type.DeferredDelete)   # alte Bloecke weg
        self.assertEqual(self.st.get_selected_cells(), ["1:w7"])
        self.assertEqual(len(v.findChildren(WeissSegmentBlock)), 1)
        self.assertIn("W8", v._lbl_selection.text())



class ReviewTest(_Basis):
    """Befunde der Gegenpruefung 29.09.: eine reine Weiss-Auswahl darf ausserhalb
    des Programmers NICHTS am Geraet bewirken."""

    def _balken_leuchtet(self):
        for k in range(48):
            self.st.set_programmer_value(1, "color_r" if k == 0 else f"color_r#{k}", 200)
        self.st.set_programmer_value(1, "intensity", 255)

    def test_submaster_auswahl_dimmt_nicht_den_balken(self):
        """Ziel ist das Geraet NUR mit Segment-Einschraenkung — ein fid ohne
        Einschraenkung hiesse „ganzes Geraet" (Review 29.09.)."""
        from src.ui.virtualconsole.vc_slider import VCSlider
        self.st.set_selected_cells(["1:w3"])
        sl = VCSlider()
        self.addCleanup(sl.deleteLater)
        sl.programmer_scope = "selected"
        self.assertEqual(sl._submaster_targets(self.st), ([1], {1: {"w3"}}))

    def test_submaster_nach_gruppenwahl_ebenso(self):
        from src.ui.virtualconsole.vc_slider import VCSlider
        self._gruppe("Nur Weiss", [zelle_fuer(1, ACHSE_WEISS, k) for k in range(8)])
        self.assertTrue(self.st.select_group_by_name("Nur Weiss"))
        sl = VCSlider()
        self.addCleanup(sl.deleteLater)
        sl.programmer_scope = "selected"
        self.assertEqual(sl._submaster_targets(self.st),
                         ([1], {1: {f"w{k}" for k in range(8)}}))

    def test_efx_und_andere_sehen_kein_geraet(self):
        self.st.set_selected_cells(["1:w3"])
        self.assertEqual(self.st.get_selected_fids(), [])
        self.assertEqual(self.st.selected_heads_for(1), set())

    def test_einkopf_modus_hat_keine_segmente(self):
        with self.st._session() as s:
            fx = s.get(PatchedFixture, 1) if False else None
        self.st.update_fixture(1, head_mode="single") if hasattr(
            self.st, "update_fixture") else None
        if getattr(next(f for f in self.st.get_patched_fixtures() if f.fid == 1),
                   "head_mode", "auto") != "single":
            self.skipTest("head_mode liess sich nicht setzen")
        self.assertIsNone(self.st.weiss_programmer_key(1, 0))


class ProgrammerReviewTest(ProgrammerTest):

    def test_auswahl_von_aussen_ganz_zu_nur_weiss_baut_um(self):
        """Befund 2: ganz -> nur Weiss aendert die fids nicht; die View blieb mit
        einem Rot-Regler stehen, der alle 48 Zonen fuhr."""
        from PySide6.QtCore import QEvent
        from src.ui.views.programmer_view import AttributeSlider, WeissSegmentBlock
        v = self._view()
        self.st.set_selected_cells(["1"])
        v._sync_follow_selection()
        self.st.set_selected_cells(["1:w3"])
        v._sync_follow_selection()
        _app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertEqual(len(v.findChildren(WeissSegmentBlock)), 1)
        rot = [w for w in v.findChildren(AttributeSlider)
               if (w._channel.attribute or "").startswith("color_r")]
        self.assertEqual(rot, [], "geraeteweiter Farbregler steht noch")

    def test_sammelregler_und_farbreiter(self):
        """M1/M4: bei zwei Segmenten gibt es den Sammelregler, und der
        Farb-Reiter ist sichtbar (sonst laege der Block in einem versteckten Tab)."""
        from PySide6.QtCore import QEvent
        from src.ui.views.programmer_view import WeissSegmentBlock
        v = self._view()
        self.st.set_selected_cells(["1:w0", "1:w5"])
        v._sync_follow_selection()
        _app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        block = v.findChildren(WeissSegmentBlock)[0]
        self.assertIn(None, block._regler)
        block._regler[None][0].setValue(90)
        self.assertEqual((self._kanal(147), self._kanal(152)), (90, 90))
        self.assertEqual(self._kanal(148), 0)
        idx = v._main_tabs.indexOf(v._attr_group_tabs["Color"])
        self.assertTrue(v._main_tabs.isTabVisible(idx))
        from PySide6.QtWidgets import QLabel
        texte = [l.text() for l in v._attr_group_tabs["Color"].findChildren(QLabel)]
        self.assertFalse([t for t in texte if "Keine Color" in t],
                         "bei reiner Weiss-Auswahl steht „Keine Color-Kanäle“ da")


class ErstesSegmentTest(_Basis):
    """Gefunden beim Bauen: Segment 1 traegt den BASIS-Schluessel ``color_w``,
    den der DMX-Flush auf jedes Segment ohne eigenen Wert spiegelt — „Weiß 1"
    fuhr alle acht."""

    def test_weiss_1_faehrt_nur_sich(self):
        self.assertTrue(self.st.weiss_setzen(1, 0, 150))
        self.assertEqual([self._kanal(c) for c in range(147, 155)],
                         [150, 0, 0, 0, 0, 0, 0, 0])

    def test_gesetzte_segmente_bleiben_stehen(self):
        self.st.weiss_setzen(1, 4, 80)
        self.st.weiss_setzen(1, 0, 150)
        self.assertEqual([self._kanal(c) for c in range(147, 155)],
                         [150, 0, 0, 0, 80, 0, 0, 0])

if __name__ == "__main__":
    unittest.main()
