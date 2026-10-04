"""OUT-60 — ein Live-Show-Load sendet keinen Null-Frame mehr (CDX-22-Rest).

Befund (Sitzung B, echter Enttec auf COM3, 03.10.2026): beim Neu-Laden von
„Event Demo 2026“ fiel in 3 von 8 Laeufen fuer genau einen Frame (~23 ms) jeder
PAR-Dimmer von 255 auf 0 — der 44-Hz-Renderer hatte mitten im reset-first
gerechnet. Am Rig ein sichtbarer Blitz.

Hier deterministisch statt per Zufall: der Test laesst den Sende-Thread genau im
ungluecklichsten Moment laufen — direkt nach dem reset-first — und misst am
GESENDETEN Frame (``_display_frame``), nicht am Universum.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import get_state                     # noqa: E402
from src.core.show import show_file                          # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOW = os.path.join(REPO, "shows", "Demo_Show_Full.lshow")


class LadeSperreTest(unittest.TestCase):
    """Die Sperre selbst, am OutputManager."""

    def setUp(self):
        self.om = get_state().output_manager
        self.u = self.om.universes[1]

    def tearDown(self):
        self.om.set_blackout(False)

    def test_haelt_den_stand_und_gibt_danach_frei(self):
        self.u.set_channel(5, 200)
        self.om._send_all()
        with self.om.lade_sperre():
            self.u.set_channel(5, 0)
            self.om._send_all()
            self.assertEqual(self.om._display_frame[1][4], 200, "Ladesperre haelt nicht")
        self.om._send_all()
        self.assertEqual(self.om._display_frame[1][4], 0, "nach dem Laden wieder live")

    def test_blackout_greift_auch_waehrend_des_ladens(self):
        self.u.set_channel(5, 200)
        with self.om.lade_sperre():
            self.om.set_blackout(True)
            self.om._send_all()
            self.assertEqual(self.om._display_frame[1][4], 0)

    def test_verschachtelt_gibt_erst_das_aeusserste_ende_frei(self):
        self.u.set_channel(5, 120)
        with self.om.lade_sperre():
            with self.om.lade_sperre():
                pass
            self.u.set_channel(5, 0)
            self.om._send_all()
            self.assertEqual(self.om._display_frame[1][4], 120)
        self.assertIsNone(self.om._lade_frames)

    def test_bediener_freeze_bleibt_unberuehrt(self):
        self.u.set_channel(5, 90)
        self.om.set_freeze(True)
        try:
            with self.om.lade_sperre():
                pass
            self.assertIsNotNone(self.om._freeze_frames)
        finally:
            self.om.set_freeze(False)


class MaskenImLadeFensterTest(unittest.TestCase):
    """OUT-60-Folge (Review A): der reset-first baut GM-, Blackout-Erhalten- und
    Ziel-Masken fuer den LEEREN Patch neu. Im Lade-Fenster muessen die Masken
    vom Start der Sperre gelten — sonst skaliert ein GM < 100 % auch Pan/Tilt
    (Ruck), und ein aktiver Blackout zieht Pan/Tilt auf 0."""

    PAN, DIM = 10, 12

    def setUp(self):
        self.om = get_state().output_manager
        self.u = self.om.universes[1]
        self._alt = (self.om._gm_address_mask, self.om._blackout_keep_mask,
                     getattr(self.om, "_ziel_blackout_union", None), self.om.grand_master)
        self.u.set_channel(self.PAN, 200)
        self.u.set_channel(self.DIM, 200)
        self.om._gm_address_mask = {1: frozenset({self.DIM})}
        self.om._blackout_keep_mask = {1: frozenset({self.PAN})}

    def tearDown(self):
        (self.om._gm_address_mask, self.om._blackout_keep_mask,
         self.om._ziel_blackout_union, gm) = self._alt
        self.om.grand_master = gm
        self.om.set_blackout(False)

    def _leerer_patch(self):
        # wie _rebuild_render_plan fuer den leeren Patch: Masken leer ersetzt
        self.om._gm_address_mask = {}
        self.om._blackout_keep_mask = {}
        self.om._ziel_blackout_union = {}

    def test_gm_unter_100_ruckt_pan_nicht(self):
        self.om.grand_master = 0.5
        with self.om.lade_sperre():
            self._leerer_patch()
            self.om._send_all()
            f = self.om._display_frame[1]
            self.assertEqual(f[self.PAN - 1], 200, "Pan vom GM skaliert (Ruck)")
            self.assertEqual(f[self.DIM - 1], 100, "GM wirkt weiter auf den Dimmer")

    def test_blackout_haelt_pan_im_lade_fenster(self):
        self.om.set_blackout(True)
        with self.om.lade_sperre():
            self._leerer_patch()
            self.om._send_all()
            f = self.om._display_frame[1]
            self.assertEqual(f[self.PAN - 1], 200, "Pan im Blackout auf 0 gefallen")
            self.assertEqual(f[self.DIM - 1], 0)

    def test_gezielter_blackout_bleibt_im_lade_fenster(self):
        self.om._ziel_blackout_union = {1: frozenset({self.DIM})}
        with self.om.lade_sperre():
            self._leerer_patch()
            self.om._send_all()
            self.assertEqual(self.om._display_frame[1][self.DIM - 1], 0,
                             "gezielter Blackout im Lade-Fenster verloren")

    def test_nach_dem_laden_gelten_die_neuen_masken(self):
        self.om.grand_master = 0.5
        with self.om.lade_sperre():
            self._leerer_patch()
        self.assertIsNone(self.om._lade_masken)
        self.om._send_all()
        # ohne GM-Maske skaliert der GM wieder alles (bisheriges Verhalten)
        self.assertEqual(self.om._display_frame[1][self.PAN - 1], 100)


class LiveLoadTest(unittest.TestCase):
    """Ende zu Ende: dieselbe Show live neu laden."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="out60_")
        self.show = os.path.join(self.tmp, "show.lshow")
        shutil.copy(SHOW, self.show)
        self.state = get_state()
        ok, msg = show_file.load_show(self.show)
        self.assertTrue(ok, msg)
        for _ in range(5):
            self.state._render_frame(0.023)
        self.om = self.state.output_manager
        self.om._send_all()
        self.vorher = bytes(self.om._display_frame[1])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_kein_null_frame_mitten_im_reset_first(self):
        mitten = []

        def danach_senden(echt):
            def f(*a, **k):
                r = echt(*a, **k)
                # Der Sende-Thread rendert + sendet genau hier — nach dem
                # reset-first bzw. nach dem neuen Patch, aber bevor die
                # Wiedergabe der Show wiederhergestellt ist.
                self.state._render_frame(0.023)
                self.om._send_all()
                mitten.append(bytes(self.om._display_frame[1]))
                return r
            return f

        with mock.patch.object(show_file, "_reset_state",
                               danach_senden(show_file._reset_state)),                 mock.patch.object(show_file, "_replace_patch_from_data",
                                  danach_senden(show_file._replace_patch_from_data)):
            ok, msg = show_file.load_show(self.show)
        self.assertTrue(ok, msg)
        for _ in range(5):
            self.state._render_frame(0.023)
        self.om._send_all()
        nachher = bytes(self.om._display_frame[1])
        beide = [c for c in range(512) if self.vorher[c] > 0 and nachher[c] > 0]
        self.assertTrue(beide, "Show liefert kein Licht — Test waere wertlos")
        self.assertTrue(mitten, "reset-first lief nicht")
        einbrueche = sorted({c + 1 for f in mitten for c in beide if f[c] == 0})
        self.assertEqual(einbrueche, [], f"Null-Frame mitten im Load auf Kanal {einbrueche}")


if __name__ == "__main__":
    unittest.main()
