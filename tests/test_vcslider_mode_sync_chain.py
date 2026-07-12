"""VCSlider._post_dialog_mode_sync: Cleanup + Apply sind unabhaengige Phasen.

Regression (Bug-Jagd Runde 2, 2026-07-12): die elif-Kette liess bei
GROUP_DIMMER->SUBMASTER die alte Gruppe als Geister-Dimmer stehen (der
SUBMASTER-Apply-Zweig beendete die Kette vor dem VCB-19-Cleanup) und wandte bei
SUBMASTER->GROUP_DIMMER den neuen Modus nicht sofort an (der Clear-Zweig endete
vor dem Apply). Jetzt: Phase 1 = Alt-Modus aufraeumen, Phase 2 = Neu-Modus anwenden.
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.ui.virtualconsole.vc_slider as VS
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode


def _fake(mode, group=""):
    calls = {"reset_group": [], "apply": 0}
    fake = SimpleNamespace(
        mode=mode,
        programmer_group=group,
        _reset_group_dimmer=lambda g: calls["reset_group"].append(g),
        _apply=lambda: calls.__setitem__("apply", calls["apply"] + 1),
    )
    return fake, calls


class ModeSyncChainTest(unittest.TestCase):
    def test_group_dimmer_to_submaster_cleans_AND_applies(self):
        """Frueher: nur Apply, alte Gruppe blieb als Geister-Dimmer gedimmt."""
        fake, calls = _fake(SliderMode.SUBMASTER)
        VCSlider._post_dialog_mode_sync(fake, SliderMode.GROUP_DIMMER, "MHs")
        self.assertEqual(calls["reset_group"], ["MHs"], "alte Gruppe muss resetten")
        self.assertEqual(calls["apply"], 1, "neuer Submaster muss sofort anwenden")

    def test_submaster_to_group_dimmer_clears_AND_applies(self):
        """Frueher: nur Slot-Clear, der neue Gruppen-Dimmer wirkte erst beim
        naechsten Ziehen."""
        fake, calls = _fake(SliderMode.GROUP_DIMMER, group="PARs")
        cleared = []
        with patch.object(VS, "_clear_submaster_slot", side_effect=cleared.append):
            VCSlider._post_dialog_mode_sync(fake, SliderMode.SUBMASTER, "")
        self.assertEqual(len(cleared), 1, "alter Submaster-Slot muss geraeumt werden")
        self.assertEqual(calls["apply"], 1, "neuer Gruppen-Dimmer muss sofort anwenden")

    def test_group_retarget_still_resets_old_group(self):
        """VCB-34 unveraendert: Gruppe A -> Gruppe B resettet A und wendet B an."""
        fake, calls = _fake(SliderMode.GROUP_DIMMER, group="B")
        VCSlider._post_dialog_mode_sync(fake, SliderMode.GROUP_DIMMER, "A")
        self.assertEqual(calls["reset_group"], ["A"])
        self.assertEqual(calls["apply"], 1)

    def test_same_group_no_spurious_reset(self):
        fake, calls = _fake(SliderMode.GROUP_DIMMER, group="A")
        VCSlider._post_dialog_mode_sync(fake, SliderMode.GROUP_DIMMER, "A")
        self.assertEqual(calls["reset_group"], [])
        self.assertEqual(calls["apply"], 1)

    def test_feature_dimmer_to_submaster_clears_feature_slot(self):
        fake, calls = _fake(SliderMode.SUBMASTER)
        cleared = []
        with patch.object(VS, "_clear_feature_dimmer_slot", side_effect=cleared.append):
            VCSlider._post_dialog_mode_sync(fake, SliderMode.FEATURE_DIMMER, "")
        self.assertEqual(len(cleared), 1)
        self.assertEqual(calls["apply"], 1)

    def test_plain_level_mode_untouched(self):
        fake, calls = _fake(SliderMode.LEVEL)
        VCSlider._post_dialog_mode_sync(fake, SliderMode.LEVEL, "")
        self.assertEqual(calls["apply"], 0)
        self.assertEqual(calls["reset_group"], [])


if __name__ == "__main__":
    unittest.main()
