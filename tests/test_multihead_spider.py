"""Mehrkopf-Spider (X-6): Profil = 2 Tilts, Farbe je Bar (VCColor head),
EFX schwenkt die zwei Bars gegenphasig.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import get_state, get_channels_for_patched
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.engine.function_manager import get_function_manager
from src.core.engine.efx import EfxFixture, EfxAlgorithm
from src.core.show.show_file import reset_show


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one())


class MultiHeadSpiderTest(unittest.TestCase):

    def setUp(self):
        _app()
        ensure_builtins()        # Profil-Migration auf 2 Tilts sicherstellen
        reset_show()
        self.state = get_state()
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.state.add_fixture(PatchedFixture(
            fid=1, label="Spider", fixture_profile_id=_pid("SPIDER14"), mode_name="14-Kanal",
            universe=1, address=1, channel_count=14, manufacturer_name="U King",
            fixture_name="Spider 14ch", fixture_type="moving_head"), undoable=False)
        self.state._rebuild_render_plan()
        u = self.state.universes.get(1)
        if u is None:
            u = self.state.output_manager.add_universe(1)
            self.state.universes[1] = u
        self.u = self.state.universes[1]

    def tearDown(self):
        self.fm.stop_all()

    def test_profile_has_two_tilts_no_pan(self):
        chans = get_channels_for_patched(
            next(f for f in self.state.get_patched_fixtures() if f.fid == 1))
        tilts = [c for c in chans if (c.attribute or "") == "tilt"]
        pans = [c for c in chans if (c.attribute or "") == "pan"]
        self.assertEqual(len(tilts), 2, "Spider sollte zwei Tilt-Kanaele haben")
        self.assertEqual(len(pans), 0, "Spider sollte keinen Pan-Kanal mehr haben")
        # color_r kommt zweimal vor (Bank 1 + Bank 2)
        self.assertEqual(sum(1 for c in chans if (c.attribute or "") == "color_r"), 2)

    def test_vccolor_head_colors_bank2_only(self):
        from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
        c = VCColor("Bar R rot")
        c.target = ColorTarget.ALL
        c.head = 1
        c.color_r, c.color_g, c.color_b, c.color_w = 200, 0, 0, 0
        c.with_intensity = False
        c._apply()
        # Bank 2 (CH10) rot, Bank 1 (CH6) bleibt 0
        self.assertEqual(self.u.get_channel(10), 200)
        self.assertEqual(self.u.get_channel(6), 0)

    def test_visualizer_sends_per_head_color_and_tilt(self):
        """3D-Visualizer: Spider wird als 'spider' erkannt und die DMX-Bruecke
        sendet pro Bar eigene Farbe + eigenen Tilt (heads-Array) — sonst zeigt
        der Visualizer beide Bars in EINER Farbe / EINEM Tilt.

        Wie test_visualizer_autopatch: KEIN echter VisualizerBridge (dessen
        __init__ subscribt am State-Singleton -> Leak ueber die Suite), sondern
        Aufruf der Methoden mit Fake-self.
        """
        import json
        from types import SimpleNamespace
        from src.ui.visualizer.visualizer_window import VisualizerBridge
        f = next(x for x in self.state.get_patched_fixtures() if x.fid == 1)
        self.assertEqual(VisualizerBridge._viz_model_for(SimpleNamespace(), f), "spider")
        # Bar L = rot + Tilt 200, Bar R = blau + Tilt 55 (CH1/2 Tilts, CH6 Rot1,
        # CH12 Blau2, CH4 Master-Dimmer)
        self.u.set_channel(1, 200)
        self.u.set_channel(2, 55)
        self.u.set_channel(4, 255)
        self.u.set_channel(6, 255)
        self.u.set_channel(12, 255)
        attrs, seen = {}, {}
        for ch in get_channels_for_patched(f):
            addr = f.address + ch.channel_number - 1
            if 1 <= addr <= 512:
                a = ch.attribute
                h = seen.get(a, 0)
                seen[a] = h + 1
                attrs[a if h == 0 else f"{a}#{h}"] = self.u.get_channel(addr)
        cap = {}
        fake = SimpleNamespace(
            dmxUpdated=SimpleNamespace(emit=lambda j: cap.update(json.loads(j))))
        VisualizerBridge.push_dmx_update(fake, 1, attrs)
        heads = cap.get("heads")
        assert heads is not None and len(heads) == 2, f"heads fehlt: {cap}"
        self.assertEqual((heads[0]["tilt"], heads[1]["tilt"]), (200, 55))
        # Summenfarbe (Icon/Kompat)
        self.assertEqual((heads[0]["r"], heads[0]["b"]), (255, 0))  # Bar L rot
        self.assertEqual((heads[1]["r"], heads[1]["b"]), (0, 255))  # Bar R blau
        # Roh-Einzelkanaele pro LED: Bar L nur rote LED (cr), Bar R nur blaue (cb)
        self.assertEqual(
            (heads[0]["cr"], heads[0]["cg"], heads[0]["cb"], heads[0]["cw"]),
            (255, 0, 0, 0))
        self.assertEqual(
            (heads[1]["cr"], heads[1]["cg"], heads[1]["cb"], heads[1]["cw"]),
            (0, 0, 255, 0))

    def test_visualizer_pan_tilt_spider_independent_bars(self):
        """QLC+-Importe (z. B. 'Speider', 'Mini Spider ZQ-B20') mappen die ZWEI
        Tilt-Motoren des Geraets als pan + tilt (nur EIN `tilt`-Kanal, KEIN
        `tilt#1`), weil die QXF die Motoren als PositionPan/PositionTilt bzw.
        PositionXAxis/PositionYAxis fuehrt. Der 3D-Spider muss Bar 0 dann aus
        `pan` und Bar 1 aus `tilt` speisen — sonst faellt Bar 1 auf denselben
        `tilt` zurueck und BEIDE Bars folgen nur "Tilt 2" (der gemeldete Bug).
        """
        import json
        from types import SimpleNamespace
        from src.ui.visualizer.visualizer_window import VisualizerBridge
        # Reales Speider/Mini-Layout: pan (Motor 1 / "Tilt 1") + tilt (Motor 2 /
        # "Tilt 2") + zwei Farb-Banks. pan=60, tilt=200 -> die zwei Bars MUESSEN
        # unterschiedlich kippen.
        attrs = {
            "pan": 60, "tilt": 200, "intensity": 255,
            "color_r": 255, "color_g": 0, "color_b": 0, "color_w": 0,         # Bank 1
            "color_r#1": 0, "color_g#1": 0, "color_b#1": 255, "color_w#1": 0,  # Bank 2
        }
        cap = {}
        fake = SimpleNamespace(
            dmxUpdated=SimpleNamespace(emit=lambda j: cap.update(json.loads(j))))
        VisualizerBridge.push_dmx_update(fake, 7, attrs)
        heads = cap.get("heads")
        assert heads is not None and len(heads) == 2, f"heads fehlt: {cap}"
        # Bar 0 <- pan (Motor 1), Bar 1 <- tilt (Motor 2): UNABHAENGIG.
        self.assertEqual((heads[0]["tilt"], heads[1]["tilt"]), (60, 200))
        self.assertNotEqual(heads[0]["tilt"], heads[1]["tilt"])
        # Farbe bleibt pro Bar getrennt (Bank 1 rot, Bank 2 blau).
        self.assertEqual((heads[0]["cr"], heads[1]["cb"]), (255, 255))

    def test_spider_mirror_option(self):
        """Spider-Anordnung (gespiegelt/parallel): Erkennung, update_fixture-
        Whitelist, Show-Serialisierung-Roundtrip und Visualizer-`mirror`-Flag."""
        from types import SimpleNamespace
        from src.core.app_state import is_spider_fixture
        from src.ui.visualizer.visualizer_window import VisualizerBridge
        from src.core.show.show_file import (
            _fixture_to_dict as pf_to_dict, _patched_fixture_from_data,
        )
        f = next(x for x in self.state.get_patched_fixtures() if x.fid == 1)
        # 1. Erkennung + Default = gespiegelt
        self.assertTrue(is_spider_fixture(f))
        self.assertTrue(bool(getattr(f, "spider_mirrored", True)))
        # 2. update_fixture-Whitelist
        self.state.update_fixture(1, spider_mirrored=False, undoable=False)
        f = next(x for x in self.state.get_patched_fixtures() if x.fid == 1)
        self.assertFalse(bool(f.spider_mirrored))
        # 3. Show-Serialisierung-Roundtrip (.lshow)
        d = pf_to_dict(f)
        self.assertEqual(d["spider_mirrored"], False)
        f2 = _patched_fixture_from_data(d, 99)
        self.assertFalse(bool(f2.spider_mirrored))
        # 4. Visualizer-Dict: mirror-Flag (Fake-self, kein echter Bridge)
        fake = SimpleNamespace(_state=self.state, _viz_model_for=lambda ff: "spider")
        vd = VisualizerBridge._fixture_to_dict(fake, f)
        self.assertEqual(vd["model"], "spider")
        self.assertEqual(vd["mirror"], False)

    def test_efx_swings_bars_counter(self):
        e = self.fm.new_efx("Spider Schwenk")
        e.algorithm = EfxAlgorithm.CIRCLE
        e.fixtures = [EfxFixture(fid=1)]
        e.open_beam = True
        e.speed_hz = 1.0
        e.width = e.height = 200.0
        # Gegenphase ("Schere") = expliziter head_spread=1.0 (180-Grad-Welle).
        # Seit der per-Kopf-Phasenwelle (2026-06-22) ist der Default head_spread=0.5
        # eine 90-Grad-Welle (Bars laufen versetzt, NICHT gegenphasig); die alte
        # starre tilt#1=255-tilt-Schere ist als head_spread=1.0 back-compat erhalten.
        e.head_spread = 1.0
        self.fm.start(e.id)
        # ein paar Frames rendern, dann Tilt-Kanaele lesen
        for _ in range(6):
            self.state._render_frame(1 / 44.0)
        t0 = self.u.get_channel(1)    # Tilt Bar L (Kopf 0)
        t1 = self.u.get_channel(2)    # Tilt Bar R (Kopf 1) — gegenphasig
        self.assertLessEqual(abs((t0 + t1) - 255), 2,
                             f"Bars sollten gegenphasig schwenken: {t0}+{t1}")


if __name__ == "__main__":
    unittest.main()
