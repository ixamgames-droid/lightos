"""CDX-75 (3): ein alter VC-Fader auf ``laser_twist#1`` (SH-LASER3W, Pattern A
vertikal) steuert nach der Lade-Migration NUR Pattern A vertikal.

Vor LAS-28 war ``laser_twist#1`` ein exakter Schluessel (nur A vertikal). Die
Migration (LAS-47) setzt den Fader auf ``laser_twist_y`` um — ein
Basis-Schluessel, den die Mehrkopf-Aufloesung auf ``laser_twist_y#1``
(Pattern B vertikal) spiegelt, solange dort kein eigener Wert steht. Ohne
Gegenmassnahme bewegte der migrierte Fader also beide vertikalen Flips.
Jetzt traegt er ``programmer_attr_nur_kopf0`` und verankert die anderen Koepfe
vor dem Schreiben (wie der Getrennt-Modus im Programmer, UI-06).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from _fixture_quelle import frische_library
from src.core.app_state import (clear_channel_cache, get_state,
                                resolve_attr_channels)
from src.core.database import bibliothek_format as BF
from src.core.database.models import FixtureMode, FixtureProfile
from src.core.show.las28_ziele import vc_nachziehen

from test_las47_laser_twist_ziele import KANAL, NACH, _fader, _laden


class Cdx75Kopf1Fader(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        eng = frische_library(cls)
        with Session(eng) as s:
            BF.einspielen_wenn_noetig(s)
            s.commit()
            prof = s.execute(
                select(FixtureProfile)
                .options(selectinload(FixtureProfile.modes)
                         .selectinload(FixtureMode.channels))
                .where(FixtureProfile.short_name == "SH-LASER3W")).scalar_one()
            modus = next(m for m in prof.modes if m.name == "25 Channel")
            cls.pid, cls.modus, cls.cc = prof.id, modus.name, len(modus.channels)
        clear_channel_cache()

    @classmethod
    def tearDownClass(cls):
        clear_channel_cache()

    def _show(self, vc_widgets=(), **extra):
        patch = [{"fid": 1, "label": "Laser", "fixture_profile_id": self.pid,
                  "mode_name": self.modus, "universe": 1, "address": 1,
                  "channel_count": self.cc, "fixture_name": "3000mW RGB Laser",
                  "manufacturer_name": "Shehds", "fixture_type": "laser"}]
        show = {"version": "1.2", "patch": patch,
                "functions": {"functions": []},
                "virtual_console": {"pages": [{"widgets": list(vc_widgets)}]}}
        show.update(extra)
        return show

    def _widgets(self):
        return get_state()._vc_layout["pages"][0]["widgets"]

    def _aufgeloest(self) -> dict:
        """Kanalnummer -> Wert, wie der Programmer-Flush ihn aufloest."""
        st = get_state()
        chans = st._channels_for_fid(1)
        werte = st.programmer.get(1, {})
        return {nr: v for nr, _k, v in resolve_attr_channels(chans, werte)}

    def _slider(self):
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from src.ui.virtualconsole.vc_slider import VCSlider
        s = VCSlider("Flip")
        s.apply_dict(self._widgets()[0])
        return s

    def test_migration_markiert_den_fader_als_nur_kopf_0(self):
        _laden(self._show(vc_widgets=[_fader("laser_twist#1"),
                                      _fader("laser_twist#3")]))
        w0, w1 = self._widgets()
        self.assertEqual(w0["programmer_attr"], "laser_twist_y")
        self.assertIs(w0.get("programmer_attr_nur_kopf0"), True)
        # #3 -> laser_twist_y#1 ist ein exakter Schluessel: keine Markierung
        self.assertNotIn("programmer_attr_nur_kopf0", w1)
        # zweiter Lauf: unveraendert (idempotent)
        vor = [dict(w) for w in self._widgets()]
        vc_nachziehen(get_state()._vc_layout, True, False)
        self.assertEqual([dict(w) for w in self._widgets()], vor)

    def test_migrierter_fader_bewegt_b_vertikal_nicht_mit(self):
        _laden(self._show(vc_widgets=[_fader("laser_twist#1")]))
        get_state().programmer.pop(1, None)
        s = self._slider()
        try:
            self.assertTrue(s.to_dict().get("programmer_attr_nur_kopf0"))
            s.value = 200
            s._apply()
            ch = self._aufgeloest()
            a_v, b_v = KANAL["Pattern A Vertical Flip"], KANAL["Pattern B Vertical Flip"]
            self.assertEqual(ch.get(a_v), 200)
            self.assertNotEqual(ch.get(b_v), 200,
                                "Fader auf A vertikal zieht B vertikal mit")
            # B vertikal steht verankert auf dem Kanal-Default
            b_wert = ch.get(b_v)
            s.value = 50
            s._apply()
            ch = self._aufgeloest()
            self.assertEqual(ch.get(a_v), 50)
            self.assertEqual(ch.get(b_v), b_wert)
        finally:
            s.deleteLater()

    def test_eigener_wert_auf_b_vertikal_bleibt(self):
        _laden(self._show(vc_widgets=[_fader("laser_twist#1")]))
        st = get_state()
        st.programmer.pop(1, None)
        st.set_programmer_value(1, "laser_twist_y#1", 77)
        s = self._slider()
        try:
            s.value = 120
            s._apply()
            self.assertEqual(st.programmer[1]["laser_twist_y#1"], 77)
            self.assertEqual(st.programmer[1]["laser_twist_y"], 120)
        finally:
            s.deleteLater()

    def test_neu_angelegter_fader_auf_laser_twist_y_bleibt_geraeteweit(self):
        """Ohne Markierung (neue Show, Fader von Hand auf laser_twist_y)
        bleibt der Basis-Schluessel geraeteweit — wie bisher."""
        _laden(self._show(vc_widgets=[_fader("laser_twist_y")]), zeit=NACH)
        get_state().programmer.pop(1, None)
        s = self._slider()
        try:
            self.assertNotIn("programmer_attr_nur_kopf0", s.to_dict())
            s.value = 90
            s._apply()
            ch = self._aufgeloest()
            self.assertEqual(ch.get(KANAL["Pattern A Vertical Flip"]), 90)
            self.assertEqual(ch.get(KANAL["Pattern B Vertical Flip"]), 90)
        finally:
            s.deleteLater()
