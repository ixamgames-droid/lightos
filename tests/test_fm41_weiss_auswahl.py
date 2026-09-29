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
        self.assertEqual(self.st.get_selected_fids(), [1])
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

    def test_submaster_bleibt_auf_der_weiss_gruppe_wirkungslos(self):
        """Absicht dieser Scheibe: der VC-Submaster kennt die Achse noch nicht.
        Er darf dann NICHTS tun — nicht den ganzen Balken dimmen (Backlog:
        „halb nachgeruestet ist schlechter als gar nicht")."""
        from src.ui.virtualconsole.vc_slider import VCSlider
        self._gruppe("Nur Weiss", [zelle_fuer(1, ACHSE_WEISS, k) for k in range(8)])
        sl = VCSlider()
        self.addCleanup(sl.deleteLater)
        sl.programmer_scope = "group"
        sl.programmer_group = "Nur Weiss"
        self.assertEqual(sl._submaster_targets(self.st), ([], {}))


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


if __name__ == "__main__":
    unittest.main()
