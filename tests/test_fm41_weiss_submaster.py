"""FM-41 (Scheibe 3b): Submaster und Projektion kennen die Weiss-Achse.

1. Ein VC-Submaster auf einer reinen Weiss-Gruppe dimmt GENAU deren
   Weiss-Segmente — nicht den ganzen Balken (Master, 48 RGB-Zonen) und nicht
   nichts. Gemessen am fertigen Frame (``_render_frame``) mit dem echten Profil.
2. Ein Farbkopf traegt an einem Geraet mit eigener Weiss-Achse kein Weiss mehr
   (Kopf 4 schaltete vorher CH150 „Weiss-Zone 4" mit).
3. „Leere Auswahl heisst alle" (VC-Slider im Programmer-Modus, MIDI-Fader,
   XY-Pad) gilt nur noch, wenn WIRKLICH nichts gewaehlt ist — eine reine
   Weiss-Auswahl hat leere fids und fuehr sonst das ganze Rig.
"""
import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                         # noqa: E402
from sqlalchemy import select                                       # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

from src.core.app_state import get_state                            # noqa: E402
from src.core.database.fixture_db import engine, ensure_builtins    # noqa: E402
from src.core.database.models import FixtureGroup, FixtureProfile, PatchedFixture  # noqa: E402
from src.core.group_cells import ACHSE_WEISS, zelle_fuer            # noqa: E402
from src.core.show.show_file import reset_show                      # noqa: E402

_app = QApplication.instance() or QApplication([])


def _pid(short):
    with Session(engine()) as s:
        return s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first()


class _Balken(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        ensure_builtins()

    def setUp(self):
        reset_show()
        self.st = get_state()
        self.st.add_fixture(PatchedFixture(
            fid=1, label="Balken", fixture_profile_id=_pid("ZQ06121"),
            mode_name="154-Kanal 48 Zonen RGB + 8x Weiss", universe=1, address=1,
            channel_count=154, fixture_type="matrix"), undoable=False)
        self.addCleanup(self.st.set_selected_fids, [])
        om = self.st.output_manager
        self.addCleanup(lambda: [om.clear_submaster(k) for k in list(om._submasters)])
        # Alles an: Master, alle RGB-Zonen rot, alle Weiss-Segmente.
        self.st.set_programmer_value(1, "intensity", 255)
        for k in range(48):
            self.st.set_programmer_value(1, "color_r" if k == 0 else f"color_r#{k}", 200)
        for k in range(8):
            self.st.weiss_setzen(1, k, 160)

    def _gruppe(self, name, zellen):
        pos = {f"{i},0": z for i, z in enumerate(zellen)}
        with self.st._session() as s:
            s.add(FixtureGroup(name=name, cols=len(zellen), rows=1,
                               positions_json=json.dumps(pos), folder=""))
            s.commit()

    def _frame(self):
        self.st._render_frame(0.02)
        u = self.st.universes[1]
        return {"master": u.get_channel(1),
                "rot": [u.get_channel(3 + 3 * k) for k in range(48)],
                "weiss": [u.get_channel(c) for c in range(147, 155)]}

    def _slider(self, **kw):
        from src.ui.virtualconsole.vc_slider import VCSlider
        sl = VCSlider()
        self.addCleanup(sl.deleteLater)
        for k, v in kw.items():
            setattr(sl, k, v)
        return sl


class SubmasterTest(_Balken):

    def test_vorbedingung_alles_leuchtet(self):
        f = self._frame()
        self.assertEqual(f["master"], 255)
        self.assertEqual(set(f["rot"]), {200})
        self.assertEqual(f["weiss"], [160] * 8)

    def test_weiss_gruppe_dimmt_nur_das_weiss(self):
        self._gruppe("Weiss 2+4", [zelle_fuer(1, ACHSE_WEISS, 1),
                                   zelle_fuer(1, ACHSE_WEISS, 3)])
        sl = self._slider(programmer_scope="group", programmer_group="Weiss 2+4")
        fids, heads = sl._submaster_targets(self.st)
        self.assertEqual((fids, heads), ([1], {1: {"w1", "w3"}}))
        self.st.output_manager.set_submaster("t", 0.0, fids, heads=heads)
        f = self._frame()
        self.assertEqual(f["weiss"], [160, 0, 160, 0, 160, 160, 160, 160])
        self.assertEqual(f["master"], 255, "der Master-Dimmer darf nicht mit")
        self.assertEqual(set(f["rot"]), {200}, "RGB-Zonen duerfen nicht mit")

    def test_halb(self):
        self._gruppe("Nur Weiss", [zelle_fuer(1, ACHSE_WEISS, k) for k in range(8)])
        sl = self._slider(programmer_scope="group", programmer_group="Nur Weiss")
        fids, heads = sl._submaster_targets(self.st)
        self.st.output_manager.set_submaster("t", 0.5, fids, heads=heads)
        f = self._frame()
        for v in f["weiss"]:
            self.assertAlmostEqual(v, 80, delta=1)
        self.assertEqual(f["master"], 255)

    def test_auswahl_reichweite(self):
        self.st.set_selected_cells(["1:w5"])
        sl = self._slider(programmer_scope="selected")
        self.assertEqual(sl._submaster_targets(self.st), ([1], {1: {"w5"}}))

    def test_ganzes_geraet_bleibt_bestand(self):
        """Positivkontrolle: ganze Geraete-Gruppe -> geraeteweiter Faktor."""
        self._gruppe("Ganz", ["1"])
        sl = self._slider(programmer_scope="group", programmer_group="Ganz")
        self.assertEqual(sl._submaster_targets(self.st), ([1], {}))


class ProjektionTest(_Balken):

    def test_farbkopf_4_schaltet_kein_weiss(self):
        self.st.set_programmer_value(1, "color_w", 0, head=3)
        f = self._frame()
        self.assertEqual(f["weiss"], [160] * 8)


class KopfReglerTest(_Balken):

    def test_farbkopf_hat_keinen_weiss_regler(self):
        from PySide6.QtCore import QEvent
        from src.ui.views.programmer_view import AttributeSlider, ProgrammerView
        v = ProgrammerView()
        self.addCleanup(v.deleteLater)
        self.st.set_selected_cells(["1:3"])
        v._sync_follow_selection()
        _app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        attrs = sorted({w._channel.attribute for w in v.findChildren(AttributeSlider)
                        if (w._channel.attribute or "").startswith("color")})
        self.assertEqual(attrs, ["color_b", "color_g", "color_r"])


class LeerHeisstAlleTest(_Balken):
    """Eine reine Weiss-Auswahl ist NICHT „nichts gewaehlt"."""

    def setUp(self):
        super().setUp()
        self.st.add_fixture(PatchedFixture(
            fid=2, label="PAR", fixture_profile_id=_pid("ZQ01424"),
            mode_name="8-Kanal RGBW", universe=1, address=300, channel_count=8,
            fixture_type="par"), undoable=False)

    def test_midi_fader(self):
        from src.core.midi.midi_mapper import MidiMapper
        m = MidiMapper.__new__(MidiMapper)
        m._state = self.st
        self.st.set_selected_cells(["1:w2"])
        self.assertEqual(m._programmer_targets("intensity"), ([], {}))
        self.st.set_selected_cells([])
        fids, _ = m._programmer_targets("intensity")
        self.assertEqual(sorted(fids), [1, 2], "wirklich leer -> weiter alle")

    def test_xypad(self):
        from src.ui.virtualconsole.vc_xypad import VCXYPad
        pad = VCXYPad()
        self.addCleanup(pad.deleteLater)
        self.st.set_selected_cells(["1:w2"])
        self.assertEqual(pad._resolve_fids(self.st), [])

    def test_programmer_slider_auswahl(self):
        from src.ui.virtualconsole.vc_slider import SliderMode
        self.st.set_selected_cells(["1:w2"])
        sl = self._slider(mode=SliderMode.PROGRAMMER, programmer_scope="selected",
                          programmer_attr="intensity")
        vorher = dict(self.st.programmer.get(2, {}))
        sl._value = 10
        sl._apply()
        self.assertEqual(self.st.programmer.get(2, {}), vorher,
                         "der PAR wurde ueber eine Weiss-Auswahl gefahren")


if __name__ == "__main__":
    unittest.main()
