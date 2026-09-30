"""FM-51 (Gruppe cmdline_vc): Command-Line und VC-Farbkachel deuten eine reine
Weiss-Auswahl nicht mehr als „nichts gewaehlt -> alle".

Aufbau: fid 1 = ZQ06121 (48 RGB-Zonen + 8 Weiss-Segmente), fid 2 und 3 =
RGBW-PAR ZQ01424. Ein Geraet, das nur ueber ``"1:wN"`` gewaehlt ist, steht
bewusst NICHT in ``selected_fids``.

* ``hi``: bei reiner Weiss-Auswahl nur die gewaehlten Segmente + geteilter
  Dimmer; kein geraeteweites RGB/intensity, PARs unberuehrt.
* ``lowlight``: das nur-weiss gewaehlte Geraet ist ausgenommen.
* ``@ 50`` ohne getippte Selektion: eigene Meldung „Nur Weiß-Segmente gewählt".
* VC-Farbkachel „Programmer/Selektion": faerbt bei reiner Weiss-Auswahl nichts.
* VC-Slider/MIDI/XY-Pad: auf den zentralen Helfer umgestellt (verhaltensgleich).

Je Stelle eine Positivkontrolle: wirklich leere Auswahl bzw. ganze Geraete
verhalten sich wie vorher.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                         # noqa: E402
from sqlalchemy import select                                       # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

from src.core.app_state import get_state                            # noqa: E402
from src.core.cmdline.parser import execute                         # noqa: E402
from src.core.database.fixture_db import engine, ensure_builtins    # noqa: E402
from src.core.database.models import FixtureProfile, PatchedFixture  # noqa: E402
from src.core.show.show_file import reset_show                      # noqa: E402

_app = QApplication.instance() or QApplication([])


def _pid(short):
    with Session(engine()) as s:
        return s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first()


class _Rig(unittest.TestCase):

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
        for fid, adr in ((2, 300), (3, 310)):
            self.st.add_fixture(PatchedFixture(
                fid=fid, label=f"PAR {fid}", fixture_profile_id=_pid("ZQ01424"),
                mode_name="8-Kanal RGBW", universe=1, address=adr, channel_count=8,
                fixture_type="par"), undoable=False)
        self.addCleanup(self.st.set_selected_cells, [])
        self.addCleanup(self.st.clear_programmer)
        self.st.clear_programmer()

    def _prog(self, fid):
        return dict(self.st.programmer.get(fid, {}))


class HighlightTest(_Rig):

    def test_nur_weiss_macht_nur_das_segment_hell(self):
        self.st.set_selected_cells(["1:w3"])
        seg = self.st.weiss_programmer_key(1, 3)
        dk = self.st.weiss_dimmer_key(1, 3)
        self.assertTrue(seg and dk)
        res = execute("hi", self.st)
        self.assertTrue(res.ok, res.message)
        p1 = self._prog(1)
        self.assertEqual(p1.get(seg), 255)
        self.assertEqual(p1.get(dk), 255)
        # Keine geraeteweite Farbe am Balken, andere Segmente verankert (nicht 255).
        for k in ("color_r", "color_g", "color_b"):
            self.assertNotIn(k, p1, f"{k} geraeteweit am Balken gesetzt")
        for s in range(8):
            if s != 3:
                self.assertNotEqual(p1.get(self.st.weiss_programmer_key(1, s)), 255)
        self.assertEqual(self._prog(2), {}, "PAR 2 wurde mit hell gemacht")
        self.assertEqual(self._prog(3), {}, "PAR 3 wurde mit hell gemacht")

    def test_leer_heisst_weiter_alle(self):
        self.st.set_selected_cells([])
        execute("hi", self.st)
        for fid in (1, 2, 3):
            p = self._prog(fid)
            self.assertEqual(p.get("intensity"), 255)
            self.assertEqual(p.get("color_r"), 255)

    def test_ganzes_geraet_wie_bisher(self):
        self.st.set_selected_cells(["2"])
        execute("hi", self.st)
        self.assertEqual(self._prog(2).get("color_b"), 255)
        self.assertEqual(self._prog(1), {})
        self.assertEqual(self._prog(3), {})

    def test_gemischt_ganzes_geraet_plus_weiss(self):
        self.st.set_selected_cells(["2", "1:w0"])
        execute("hi", self.st)
        self.assertEqual(self._prog(2).get("intensity"), 255)
        self.assertEqual(self._prog(1).get(self.st.weiss_programmer_key(1, 0)), 255)
        self.assertNotIn("color_r", self._prog(1))
        self.assertEqual(self._prog(3), {})


class LowlightTest(_Rig):

    def test_nur_weiss_geraet_ist_ausgenommen(self):
        self.st.set_selected_cells(["1:w3"])
        execute("lowlight", self.st)
        self.assertNotIn("intensity", self._prog(1), "gewaehlter Balken abgedunkelt")
        self.assertEqual(self._prog(2).get("intensity"), 76)
        self.assertEqual(self._prog(3).get("intensity"), 76)

    def test_ganzes_geraet_wie_bisher(self):
        self.st.set_selected_cells(["2"])
        execute("lowlight", self.st)
        self.assertNotIn("intensity", self._prog(2))
        self.assertEqual(self._prog(1).get("intensity"), 76)
        self.assertEqual(self._prog(3).get("intensity"), 76)

    def test_leer_dunkelt_alle(self):
        self.st.set_selected_cells([])
        execute("lowlight", self.st)
        for fid in (1, 2, 3):
            self.assertEqual(self._prog(fid).get("intensity"), 76)


class SetValueMeldungTest(_Rig):

    def test_nur_weiss_meldung(self):
        self.st.set_selected_cells(["1:w3"])
        res = execute("@ 50", self.st)
        self.assertFalse(res.ok)
        self.assertEqual(res.message, "Nur Weiß-Segmente gewählt")
        for fid in (1, 2, 3):
            self.assertEqual(self._prog(fid), {})

    def test_leer_meldung_wie_bisher(self):
        self.st.set_selected_cells([])
        res = execute("@ 50", self.st)
        self.assertFalse(res.ok)
        self.assertEqual(res.message, "Keine Fixtures selektiert")


class VCColorTest(_Rig):

    def _kachel(self, target=None):
        from src.ui.virtualconsole.vc_color import ColorTarget, VCColor
        w = VCColor()
        self.addCleanup(w.deleteLater)
        w.target = target or ColorTarget.PROGRAMMER
        w.head = None
        w.color_r, w.color_g, w.color_b, w.color_w = 10, 20, 30, 0
        return w

    def test_nur_weiss_faerbt_nichts(self):
        # Wie nach dem Weiss-Regler: fid 1 steht schon im Programmer.
        self.st.set_selected_cells(["1:w3"])
        self.st.weiss_setzen(1, 3, 200)
        vorher = {f: self._prog(f) for f in (1, 2, 3)}
        w = self._kachel()
        self.assertEqual(w._target_fids(self.st), [])
        w._apply()
        for f in (1, 2, 3):
            self.assertEqual(self._prog(f), vorher[f], f"fid {f} gefaerbt")

    def test_leer_programmer_geraete_wie_bisher(self):
        self.st.set_selected_cells([])
        self.st.set_programmer_value(2, "intensity", 100)
        self.assertEqual(self._kachel()._target_fids(self.st), [2])

    def test_leer_ohne_programmer_alle(self):
        self.st.set_selected_cells([])
        self.assertEqual(sorted(self._kachel()._target_fids(self.st)), [1, 2, 3])

    def test_ganze_geraete_wie_bisher_programmer_geraete(self):
        # Review FM-51 A: nur die reine Weiss-Auswahl wird abgefangen; bei ganzen
        # Geraeten bleibt das alte Verhalten (Programmer-Geraete, nicht Auswahl).
        self.st.set_selected_cells(["3"])
        self.st.set_programmer_value(2, "intensity", 100)
        self.assertEqual(self._kachel()._target_fids(self.st), [2])

    def test_gemischt_wie_bisher(self):
        self.st.set_selected_cells(["3", "1:w3"])
        self.st.set_programmer_value(2, "intensity", 100)
        self.assertEqual(self._kachel()._target_fids(self.st), [2])

    def test_ziel_alle_bleibt_alle(self):
        from src.ui.virtualconsole.vc_color import ColorTarget
        self.st.set_selected_cells(["1:w3"])
        self.assertEqual(sorted(self._kachel(ColorTarget.ALL)._target_fids(self.st)),
                         [1, 2, 3])


class ZentralerHelferTest(_Rig):
    """VC-Slider / MIDI-Fader / XY-Pad: verhaltensgleich ueber auswahl_ziel_fids."""

    def test_xypad(self):
        from src.ui.virtualconsole.vc_xypad import VCXYPad
        pad = VCXYPad()
        self.addCleanup(pad.deleteLater)
        self.st.set_selected_cells(["1:w2"])
        self.assertEqual(pad._resolve_fids(self.st), [])
        self.st.set_selected_cells(["2"])
        self.assertEqual(pad._resolve_fids(self.st), [2])
        self.st.set_selected_cells([])
        self.assertEqual(sorted(pad._resolve_fids(self.st)), [1, 2, 3])

    def test_midi(self):
        from src.core.midi.midi_mapper import MidiMapper
        m = MidiMapper.__new__(MidiMapper)
        m._state = self.st
        self.st.set_selected_cells(["1:w2"])
        self.assertEqual(m._programmer_targets("intensity"), ([], {}))
        self.st.set_selected_cells(["3"])
        self.assertEqual(m._programmer_targets("intensity")[0], [3])
        self.st.set_selected_cells([])
        self.assertEqual(sorted(m._programmer_targets("intensity")[0]), [1, 2, 3])

    def test_slider(self):
        from src.ui.virtualconsole.vc_slider import SliderMode, VCSlider
        sl = VCSlider()
        self.addCleanup(sl.deleteLater)
        sl.mode = SliderMode.PROGRAMMER
        sl.programmer_scope = "selected"
        sl.programmer_attr = "intensity"
        self.st.set_selected_cells(["1:w2"])
        sl._value = 10
        sl._apply()
        for f in (1, 2, 3):
            self.assertNotIn("intensity", self._prog(f))
        self.st.set_selected_cells([])
        sl._value = 128
        sl._apply()
        for f in (1, 2, 3):
            self.assertIn("intensity", self._prog(f))


if __name__ == "__main__":
    unittest.main()
