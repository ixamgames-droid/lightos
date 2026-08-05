"""PIXELORDER-CRASH: der Patch-Dialog liess sich bei Matrix-Panels nicht
speichern — und Mehrkopf-Geraete verloren ihre Kopf-Gruppe.

★ WARUM DAS NIEMAND GEFUNDEN HAT: **kein einziger der rund 2030 Tests baut
`PatchFixtureEditDialog` jemals.** `tests/test_head_mode_option.py` prueft den
Weg dahinter (`update_fixture`) und schreibt die Dialog-Nutzlast dafuer von Hand
ab — er testet also die ANNAHME ueber den Dialog, nicht den Dialog. Genau in
dieser Luecke sass der Fehler.

DER FEHLER: In PR #514 wurde der `pixel_order`-Block VOR die bestehenden Zeilen
gesetzt; `wants_head_group = (_hm == "heads")` rutschte dadurch in den neuen
`if`-Zweig. Zwei stille Folgen:

  (a) Ein Mehrkopf-Geraet ohne Pixel-Reihenfolge-Combo (Spider, Hydrabeam)
      erreichte die Zeile nie -> `wants_head_group` blieb False -> „Koepfe
      einzeln" legte die Kopf-Matrix GAR NICHT MEHR an. Das ist die
      Kernfunktion von FM-HEADLAYOUT, ein zweites Mal tot.
  (b) Ein Matrix-Panel mit nur EINEM `color_r` hat umgekehrt keine
      Kopf-Modus-Combo -> `_hm` war nie gesetzt -> **UnboundLocalError beim
      Speichern**, das Geraet war nicht editierbar. Betroffen sind vier reale
      Modi der eingebauten Library.

Dieser Test baut den Dialog wirklich — beide Geraetearten, beide Zweige.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


class _DialogBasis(unittest.TestCase):
    def setUp(self):
        _app()
        from src.core.database.fixture_db import ensure_builtins
        from src.core.show.show_file import reset_show
        from src.core.app_state import get_state
        ensure_builtins()
        reset_show()
        self.state = get_state()

    def _patchen(self, fid, ftype, kanaele, label="X", modus="m"):
        from src.core.database.models import PatchedFixture
        f = PatchedFixture(fid=fid, label=label, fixture_profile_id=1,
                           mode_name=modus, universe=1, address=1,
                           channel_count=kanaele, fixture_type=ftype)
        self.state.add_fixture(f)
        # ★ NICHT das eigene Objekt zurueckgeben: nach `add_fixture` ist es von
        # seiner Session geloest, und der Dialog laeuft beim ersten
        # Attributzugriff in einen DetachedInstanceError. Der State liefert die
        # gepflegte Fassung — dieselbe, die auch die echte PatchView benutzt.
        return next(x for x in self.state.get_patched_fixtures() if x.fid == fid)

    def _dialog(self, fixture, kopf_attribute):
        """Dialog mit kontrollierter Kanalliste bauen.

        `get_channels_for_patched` bestimmt, welche Combos ueberhaupt entstehen —
        genau daran haengen beide Fehlerzweige.
        """
        from types import SimpleNamespace as NS
        import src.core.app_state as A
        import src.ui.views.patch_view as PV
        orig = A.get_channels_for_patched
        kanaele = [NS(attribute=a, channel_number=i + 1, default_value=0,
                      highlight_value=255, ranges=[])
                   for i, a in enumerate(kopf_attribute)]
        A.get_channels_for_patched = lambda f: kanaele
        if hasattr(PV, "get_channels_for_patched"):
            orig_pv = PV.get_channels_for_patched
            PV.get_channels_for_patched = lambda f: kanaele
            self.addCleanup(setattr, PV, "get_channels_for_patched", orig_pv)
        self.addCleanup(setattr, A, "get_channels_for_patched", orig)
        return PV.PatchFixtureEditDialog(self.state, fixture)


class MatrixPanelLaesstSichSpeichernTest(_DialogBasis):
    """★ Der Absturz. Ein Matrix-Panel mit EINEM color_r hat keine
    Kopf-Modus-Combo — vor dem Fix starb `_on_accept` an einem unbelegten `_hm`."""

    def test_speichern_wirft_nicht(self):
        f = self._patchen(1, "matrix", 8, label="Panel", modus="8-Kanal")
        d = self._dialog(f, ["intensity", "shutter", "color_r", "color_g",
                             "color_b", "macro", "raw", "speed"])
        try:
            d._on_accept()          # genau der Pfad, der vorher UnboundLocalError warf
        except UnboundLocalError as e:
            self.fail(f"Speichern eines Matrix-Panels stuerzt ab: {e!r} — "
                      f"das Geraet ist damit gar nicht editierbar")
        finally:
            d.deleteLater()

    def test_pixel_reihenfolge_ist_in_der_nutzlast(self):
        f = self._patchen(2, "matrix", 8, label="Panel", modus="8-Kanal")
        d = self._dialog(f, ["color_r", "color_g", "color_b"])
        d._on_accept()
        self.assertIn("pixel_order", d.result_updates,
                      "der Dialog schickt die Pixel-Reihenfolge gar nicht mit")
        d.deleteLater()


class MehrkopfBehaeltDenKopfGruppenWunschTest(_DialogBasis):
    """★ Die andere Haelfte: ein Mehrkopf-Geraet, das KEIN Matrix-Panel ist,
    hat keine Pixel-Reihenfolge-Combo. Vor dem Fix wurde `wants_head_group`
    deshalb nie gesetzt — „Koepfe einzeln" legte die Kopf-Matrix nicht an."""

    def test_koepfe_einzeln_setzt_den_wunsch(self):
        f = self._patchen(3, "moving_head", 24, label="Spider", modus="24ch")
        d = self._dialog(f, ["color_r", "color_g", "color_b", "color_w"] * 4)
        if d._combo_head_mode is None:
            self.skipTest("kein Kopf-Modus-Auswahlfeld fuer diese Kanalliste")
        i = d._combo_head_mode.findData("heads")
        self.assertGreaterEqual(i, 0, "der Modus 'heads' fehlt im Auswahlfeld")
        d._combo_head_mode.setCurrentIndex(i)
        d._on_accept()
        self.assertTrue(
            getattr(d, "wants_head_group", False),
            "„Koepfe einzeln\" gewaehlt, aber der Wunsch kommt nicht an — die "
            "Kopf-Matrix wird damit nie angelegt (FM-HEADLAYOUT tot)")
        d.deleteLater()

    def test_als_eine_lampe_setzt_ihn_nicht(self):
        """Gegenrichtung — sonst bestuende der Test auch bei „immer True"."""
        f = self._patchen(4, "moving_head", 24, label="Spider", modus="24ch")
        d = self._dialog(f, ["color_r", "color_g", "color_b", "color_w"] * 4)
        if d._combo_head_mode is None:
            self.skipTest("kein Kopf-Modus-Auswahlfeld fuer diese Kanalliste")
        i = d._combo_head_mode.findData("single")
        if i >= 0:
            d._combo_head_mode.setCurrentIndex(i)
            d._on_accept()
            self.assertFalse(getattr(d, "wants_head_group", False))
        d.deleteLater()


if __name__ == "__main__":
    unittest.main()
