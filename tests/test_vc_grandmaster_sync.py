"""GDS-1: Der VC-GRANDMASTER-Fader spiegelt den EINEN globalen grand_master.

Bug (Demo-Show-Audit 2026-07-17, live beobachtet): ein GRANDMASTER-VCSlider wurde
ohne value-Attr gebaut -> serialisiert value=0. Beim Laden rief apply_dict() _apply()
nur fuer GROUP/SUB/FEATURE_DIMMER, GRANDMASTER war ausgenommen -> die geladene 0 wurde
nie gepusht, live blieb grand_master=1.0. Folge: Fader zeigt 0 %, Rig steht auf voll;
die ERSTE Maus-/Wheel-Beruehrung schreibt die 0-Position -> Blackout-Sprung. Ausserdem
folgte der Fader keiner externen GM-Aenderung (kein subscribe_grand_master).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode

_app = QApplication.instance() or QApplication([])


def _grandmaster_dict(value=0):
    """Serialisierter GRANDMASTER-Fader (wie vom Builder/aus der Show), value=0."""
    src = VCSlider("Master")
    src.mode = SliderMode.GRANDMASTER
    src._value = value
    return src.to_dict()


class GrandmasterSyncTest(unittest.TestCase):
    def setUp(self):
        self.om = get_state().output_manager
        self.om.set_grand_master(1.0)          # Rig live auf voll

    def test_load_mirrors_live_gm_not_stored_zero(self):
        s = VCSlider("Master")
        s.apply_dict(_grandmaster_dict(value=0))
        # Fader zeigt den LIVE-Wert (voll), NICHT die gespeicherte 0.
        self.assertEqual(s.value, 255)
        # Und das Laden hat den GM NICHT auf 0 gezogen (kein Blackout beim Show-Load).
        self.assertEqual(self.om.grand_master, 1.0)

    def test_follows_external_change(self):
        s = VCSlider("Master")
        s.apply_dict(_grandmaster_dict(value=0))
        self.om.set_grand_master(0.5)          # z. B. Header-Fader / MIDI
        self.assertIn(s.value, (127, 128))     # Anzeige folgt dem Push

    def test_drag_sets_gm_without_runaway(self):
        s = VCSlider("Master")
        s.apply_dict(_grandmaster_dict(value=0))
        s.value = 128                          # Nutzer zieht auf ~50 %
        self.assertAlmostEqual(self.om.grand_master, 128 / 255, places=3)
        # Der eigene Push-Callback hat den Wert nicht oszillieren lassen.
        self.assertEqual(s.value, 128)

    def test_teardown_stops_updates(self):
        s = VCSlider("Master")
        s.apply_dict(_grandmaster_dict(value=0))
        s._teardown_grandmaster_sync()         # Modus verlassen / Widget-Abbau
        self.om.set_grand_master(0.25)
        # Nach dem Abmelden folgt die Anzeige nicht mehr (bleibt beim letzten Wert).
        self.assertEqual(s.value, 255)

    def test_inverted_drag_keeps_raw_handle_no_snap(self):
        """Review-Fund: ein GRANDMASTER-Fader mit invert=True darf beim Ziehen NICHT
        durch seinen eigenen Push den rohen Griff-Wert mit dem effektiven ersetzen
        (sonst schnappt der Griff weg / Blackout beim Hochziehen)."""
        s = VCSlider("Master")
        s.apply_dict(_grandmaster_dict(value=0))
        s.invert = True
        s.value = 255                          # ganz nach oben ziehen
        self.assertEqual(s.value, 255)         # Griff bleibt oben (kein Snap)
        # invert: oben = GM 0 (gewollt) — aber eben KEIN unbeabsichtigter Sprung.
        self.assertAlmostEqual(self.om.grand_master, 0.0, places=3)

    def test_external_change_positions_inverted_handle(self):
        """Externe GM-Aenderung positioniert den Griff eines invertierten Faders
        korrekt (Inverse-Mapping), nicht am rohen gm*255."""
        s = VCSlider("Master")
        s.apply_dict(_grandmaster_dict(value=0))
        s.invert = True
        self.om.set_grand_master(0.0)          # extern -> invertiert = Griff oben
        self.assertEqual(s.value, 255)
        self.om.set_grand_master(1.0)          # extern -> invertiert = Griff unten
        self.assertEqual(s.value, 0)


if __name__ == "__main__":
    unittest.main()
