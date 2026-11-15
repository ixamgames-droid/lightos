"""LAS-47 — SH-LASER3W: Effekt-Ziele, Kanal-Kopplungen und VC-Bindungen alter
Shows auf die LAS-28-Flips nachziehen (Rest aus CDX-65).

Vor LAS-28 trugen alle vier Flip-Kanaele ``laser_twist``; ein Effekt, eine
Kanal-Kopplung oder ein VC-Fader auf ``laser_twist`` trafen alle vier. Seit
LAS-28 heissen die vertikalen ``laser_twist_y``. Die Lade-Migration erhaelt das
gespielte Verhalten: Zusatzziel ``laser_twist_y`` (Effekt/Fader) bzw. eine
Regel-Kopie (Kanal-Kopplung). ``laser_twist#N``-Bindungen werden wie die Werte
in CDX-65 umbenannt. Alle Alt-Shows entstehen hier als JSON im Test.
"""
import json
import os
import tempfile
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from _fixture_quelle import frische_library
from src.core.app_state import clear_channel_cache, get_state
from src.core.database import bibliothek_format as BF
from src.core.database.models import FixtureMode, FixtureProfile
from src.core.engine.effect_func import LayeredEffect
from src.core.engine.effect_layers import EffectLayer, LayerType
from src.core.engine.function import FunctionType
from src.core.engine.mapped_channel import MappedChannelChange, MappedRule
from src.core.engine.palette import (Palette, PaletteManager, PaletteType,
                                     get_palette_manager)
from src.core.show import show_file as SF
from src.core.show.las28_ziele import (funktionen_nachziehen, vc_nachziehen,
                                       ziel_befund)

KANAL = {"Pattern A Horizontal Flip": 5, "Pattern A Vertical Flip": 6,
         "Pattern B Horizontal Flip": 17, "Pattern B Vertical Flip": 18}
VOR = (2026, 10, 20, 18, 30, 0)       # vor LAS-28 gestempelt
NACH = (2026, 11, 5, 12, 0, 0)        # nach dem Stichtag gestempelt
ALT = {"laser_twist": 10, "laser_twist#1": 20, "laser_twist#2": 30,
       "laser_twist#3": 40}


def _laden(show: dict, zeit=VOR) -> None:
    path = os.path.join(tempfile.mkdtemp(), "las47.lshow")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        info = zipfile.ZipInfo("show.json", date_time=zeit)
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, json.dumps(show))
    ok, msg = SF.load_show(path)
    assert ok, f"load_show fehlgeschlagen: {msg}"


def _effekt(fid=7, ziel="laser_twist", fixtures=(1,)):
    e = LayeredEffect("Twist-Welle", fid=fid)
    e.fixture_ids = list(fixtures)
    e.target_attribute = ziel
    lay = EffectLayer()
    lay.type = LayerType.CONSTANT
    lay.value = 100 / 255
    e.layers = [lay]
    return e.to_dict()


def _mapping(fid=8, ziel="laser_twist", fids=(1,), per_head=False):
    m = MappedChannelChange("Kopplung", fid=fid)
    m.fids = list(fids)
    m.rules = [MappedRule(source="tilt", target=ziel, per_head=per_head)]
    return m.to_dict()


def _fader(attr, mode="Programmer", **extra):
    d = {"type": "slider", "caption": "Flip", "mode": mode,
         "programmer_attr": attr, "programmer_scope": "all"}
    d.update(extra)
    return d


class Las47Ziele(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        eng = frische_library(cls)
        cls.eng = eng
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
            for c in modus.channels:
                if c.name in KANAL:
                    assert c.channel_number == KANAL[c.name], c.name
            l2600 = s.execute(
                select(FixtureProfile)
                .options(selectinload(FixtureProfile.modes)
                         .selectinload(FixtureMode.channels))
                .where(FixtureProfile.short_name == "L2600LASER")).scalar_one()
            lm = max(l2600.modes, key=lambda m: len(m.channels))
            cls.l2600 = {"fid": 2, "label": "L2600",
                         "fixture_profile_id": l2600.id, "mode_name": lm.name,
                         "universe": 1, "address": 101,
                         "channel_count": len(lm.channels),
                         "fixture_name": l2600.name, "fixture_type": "laser"}
        clear_channel_cache()

    @classmethod
    def tearDownClass(cls):
        clear_channel_cache()

    def _patch(self, mit_l2600=False):
        p = [{"fid": 1, "label": "Laser", "fixture_profile_id": self.pid,
              "mode_name": self.modus, "universe": 1, "address": 1,
              "channel_count": self.cc, "fixture_name": "3000mW RGB Laser",
              "manufacturer_name": "Shehds", "fixture_type": "laser"}]
        return p + ([dict(self.l2600)] if mit_l2600 else [])

    def _show(self, funktionen=(), vc_widgets=(), mit_l2600=False, **extra):
        show = {"version": "1.2", "patch": self._patch(mit_l2600),
                "functions": {"functions": list(funktionen)},
                "virtual_console": {"pages": [{"widgets": list(vc_widgets)}]}}
        show.update(extra)
        return show

    def _fm(self):
        return get_state().function_manager

    def _flips(self):
        u = get_state().universes[1]
        return {n: u.get_channel(k) for n, k in KANAL.items()}

    # ── (1) Effekte ───────────────────────────────────────────────────────

    def test_alter_effekt_trifft_wieder_alle_vier_flips(self):
        _laden(self._show([_effekt()]))
        e = self._fm().get(7)
        self.assertEqual(e.target_attribute, "laser_twist")
        self.assertEqual(e.zusatz_ziele, ["laser_twist_y"])
        st = get_state()
        u = st.universes[1]
        for k in KANAL.values():
            u.set_channel(k, 0)
        e._running = True
        e.write(st.universes, list(st.get_patched_fixtures()), 0.02)
        self.assertEqual(set(self._flips().values()), {100}, self._flips())

    def test_effekt_bleibt_ohne_altstands_beleg(self):
        """Nach dem Stichtag gestempelt, kein Merkmal: mehrdeutig -> bleibt,
        und Robin bekommt einen sichtbaren Ladehinweis."""
        _laden(self._show([_effekt()]), zeit=NACH)
        self.assertEqual(self._fm().get(7).zusatz_ziele, [])
        self.assertTrue(any("SH-LASER3W" in h for h in SF.letzte_ladehinweise()))

    def test_effekt_mit_marker_bleibt(self):
        _laden(self._show([_effekt()], attribut_migrationen=["LAS-28"]))
        self.assertEqual(self._fm().get(7).zusatz_ziele, [])
        self.assertFalse(SF.letzte_ladehinweise())

    def test_effekt_auf_anderes_geraet_bleibt(self):
        _laden(self._show([_effekt(fixtures=(2,))], mit_l2600=True))
        self.assertEqual(self._fm().get(7).zusatz_ziele, [])

    def test_vc_merkmal_macht_die_show_eindeutig_alt(self):
        """Ein Fader auf ``laser_twist#3`` gibt es nur im Altstand — dann ist
        auch der Effekt nach dem Stichtag eindeutig (Rest 3)."""
        _laden(self._show([_effekt()], [_fader("laser_twist#3")]), zeit=NACH)
        self.assertEqual(self._fm().get(7).zusatz_ziele, ["laser_twist_y"])

    def test_neues_ziel_im_befund_widerlegt_den_zeitstempel(self):
        _laden(self._show([_effekt(), _effekt(fid=9, ziel="laser_twist_y")]))
        self.assertEqual(self._fm().get(7).zusatz_ziele, [])

    def test_speichern_und_neu_laden_ist_idempotent(self):
        _laden(self._show([_effekt()], [_fader("laser_twist")]))
        daten = SF._show_daten(get_state(), [])
        fd = next(f for f in daten["functions"]["functions"] if f["id"] == 7)
        self.assertEqual(fd["zusatz_ziele"], ["laser_twist_y"])
        self.assertIn("LAS-28", daten["attribut_migrationen"])
        # Ohne Marker erneut durch die Migration: nichts verdoppelt sich.
        daten.pop("attribut_migrationen")
        _laden(json.loads(json.dumps(daten, default=str)))
        self.assertEqual(self._fm().get(7).zusatz_ziele, ["laser_twist_y"])
        w = get_state()._vc_layout["pages"][0]["widgets"][0]
        self.assertEqual(w["programmer_attr_zusatz"], ["laser_twist_y"])

    def test_effekt_ohne_zusatz_bleibt_byte_gleich(self):
        d = _effekt(ziel="intensity")
        self.assertNotIn("zusatz_ziele", d)
        self.assertEqual(LayeredEffect.from_dict(d).to_dict(), d)

    # ── (1) Kanal-Kopplung ────────────────────────────────────────────────

    def test_kopplung_bekommt_eine_regel_fuer_die_vertikalen(self):
        _laden(self._show([_mapping()]))
        m = self._fm().get(8)
        self.assertEqual([r.target for r in m.rules],
                         ["laser_twist", "laser_twist_y"])
        self.assertEqual(m.rules[0].source, m.rules[1].source)
        # zweiter Lauf: unveraendert
        funktionen_nachziehen(self._fm(), {1}, True, set())
        self.assertEqual(len(m.rules), 2)

    def test_kopplung_kopf_ziele_werden_umbenannt(self):
        _laden(self._show([_mapping(ziel="laser_twist#3"),
                           _mapping(fid=9, ziel="laser_twist#2")]))
        self.assertEqual(self._fm().get(8).rules[0].target, "laser_twist_y#1")
        self.assertEqual(self._fm().get(9).rules[0].target, "laser_twist#1")

    def test_kopplung_mit_l2600_behaelt_kopf_2(self):
        """``#2`` -> ``#1`` hiesse am L2600 Gruppe B: bleibt, wird gemeldet."""
        _laden(self._show([_mapping(ziel="laser_twist#2", fids=(1, 2))],
                          mit_l2600=True))
        self.assertEqual(self._fm().get(8).rules[0].target, "laser_twist#2")
        self.assertTrue(SF.letzte_ladehinweise())

    # ── (2) VC-Bindungen ──────────────────────────────────────────────────

    def _widgets(self):
        return get_state()._vc_layout["pages"][0]["widgets"]

    def test_vc_fader_auf_kopf_n_werden_umbenannt(self):
        _laden(self._show(vc_widgets=[
            _fader("laser_twist#1"), _fader("laser_twist#2"),
            _fader("laser_twist#3"), _fader("intensity")]))
        self.assertEqual([w["programmer_attr"] for w in self._widgets()],
                         ["laser_twist_y", "laser_twist#1", "laser_twist_y#1",
                          "intensity"])

    def test_vc_fader_auf_laser_twist_bekommt_zusatzattribut(self):
        _laden(self._show(vc_widgets=[_fader("laser_twist")]))
        self.assertEqual(self._widgets()[0]["programmer_attr_zusatz"],
                         ["laser_twist_y"])

    def test_vc_kopf_1_nach_stichtag_bleibt(self):
        _laden(self._show(vc_widgets=[_fader("laser_twist#1")]), zeit=NACH)
        self.assertEqual(self._widgets()[0]["programmer_attr"], "laser_twist#1")

    def test_vc_mit_l2600_kopf_3_wird_umgesetzt_kopf_2_nicht(self):
        _laden(self._show(vc_widgets=[_fader("laser_twist#2"),
                                      _fader("laser_twist#3")], mit_l2600=True))
        self.assertEqual([w["programmer_attr"] for w in self._widgets()],
                         ["laser_twist#2", "laser_twist_y#1"])

    def test_vc_in_rahmen_verschachtelt(self):
        rahmen = {"type": "frame", "children": [_fader("laser_twist#3")]}
        _laden(self._show(vc_widgets=[rahmen]))
        self.assertEqual(self._widgets()[0]["children"][0]["programmer_attr"],
                         "laser_twist_y#1")

    def test_vc_slider_setzt_auch_das_zusatzattribut(self):
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from src.ui.virtualconsole.vc_slider import VCSlider
        _laden(self._show(vc_widgets=[_fader("laser_twist")]))
        s = VCSlider("Flip")
        try:
            s.apply_dict(self._widgets()[0])
            self.assertEqual(s.programmer_attr_zusatz, ["laser_twist_y"])
            self.assertEqual(s.to_dict()["programmer_attr_zusatz"],
                             ["laser_twist_y"])
            s.value = 200
            s._apply()
            p = get_state().programmer.get(1, {})
            self.assertEqual(p.get("laser_twist"), p.get("laser_twist_y"))
            self.assertIsNotNone(p.get("laser_twist_y"))
            # Ohne Zusatz bleibt der Fader in der Datei wie bisher.
            s2 = VCSlider("X")
            self.assertNotIn("programmer_attr_zusatz", s2.to_dict())
        finally:
            s.deleteLater()

    # ── (4) generische Palette nur mit #1 neben L2600 ─────────────────────

    def test_generische_kopf_1_palette_neben_l2600(self):
        pm = PaletteManager()
        pm._palettes = [Palette(name="Q", type=PaletteType.LASER,
                                values={"laser_twist": 8, "laser_twist#1": 9})]
        _laden(self._show(mit_l2600=True, palettes=pm.to_dict(),
                          programmer={"1": dict(ALT)}), zeit=NACH)
        pal = next(p for p in get_palette_manager().get_all() if p.name == "Q")
        laser = pal.get_values_for_fixture(1)
        self.assertEqual(laser.get("laser_twist_y"), 9)
        self.assertNotIn("laser_twist#1", laser)          # kein B horizontal
        self.assertEqual(pal.get_values_for_fixture(2)["laser_twist#1"], 9)
        self.assertEqual(pal.get_values_for_fixture(2)["laser_twist"], 8)

    # ── Pruefung: ``#2`` am L2600 ist kein Altstands-Merkmal ─────────────

    def test_l2600_fader_kopf_2_macht_die_show_nicht_alt(self):
        """Nach LAS-28 gespeichert (kein Marker, Stempel nach Stichtag): ein
        Fader auf ``laser_twist#2`` meint den L2600 und darf den
        SH-LASER3W-Wert ``laser_twist#1`` (B horizontal) nicht umsetzen."""
        _laden(self._show(vc_widgets=[_fader("laser_twist#2")],
                          mit_l2600=True,
                          programmer={"1": {"laser_twist#1": 50}}), zeit=NACH)
        p = get_state().programmer[1]
        self.assertEqual(p.get("laser_twist#1"), 50)
        self.assertNotIn("laser_twist_y", p)

    def test_l2600_kopplung_kopf_2_macht_die_show_nicht_alt(self):
        _laden(self._show(funktionen=[_mapping(ziel="laser_twist#2", fids=(2,))],
                          mit_l2600=True,
                          programmer={"1": {"laser_twist#1": 50}}), zeit=NACH)
        p = get_state().programmer[1]
        self.assertEqual(p.get("laser_twist#1"), 50)
        self.assertNotIn("laser_twist_y", p)

    def test_ziel_befund_filtert_l2600(self):
        show = self._show([_mapping(ziel="laser_twist#2", fids=(2,)),
                           _mapping(ziel="laser_twist#3", fids=(1,))],
                          [_fader("laser_twist#2")])
        self.assertEqual(ziel_befund(show, {1}, {2}), (1, 0))
        self.assertEqual(ziel_befund(show, {1}, set()), (2, 0))  # Fader + #3
        self.assertEqual(ziel_befund(show, {1}, None), (0, 0))

    # ── Befund ────────────────────────────────────────────────────────────

    def test_ziel_befund(self):
        show = self._show([_effekt(ziel="laser_twist_y")],
                          [_fader("laser_twist#2")])
        self.assertEqual(ziel_befund(show), (1, 1))
        self.assertEqual(ziel_befund({}), (0, 0))
        self.assertEqual(vc_nachziehen(None, True, False), (0, 0))


if __name__ == "__main__":
    unittest.main()
