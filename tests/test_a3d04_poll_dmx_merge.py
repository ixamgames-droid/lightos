"""A3D-04: der Poll-Puffer MERGT differentielle dmxBatch-Frames pro fid.

Vorher speicherte ``_poll_set_dmx`` nur den LETZTEN Batch (``self._poll_dmx =
batch_json``). Der ``VisualizerService`` pusht aber DIFFERENTIELL (nur geaenderte
Fixtures) und setzt sein ``_last_payload`` unbedingt weiter — ein verworfener Batch
wird also nie nachgeliefert. Bei ~33 ms Service-Tick gegen ~130 ms JS-Poll fielen
damit ~3 von 4 Batches ersatzlos aus: ein Fixture, dessen einzige Aenderung in einem
verschluckten Batch lag, blieb im 3D dauerhaft auf dem alten Wert stehen.

Der Poll ist laut Modul-Kommentar der EINZIGE zuverlaessige Python->JS-DMX-Weg
(QtWebEngine stellt Signale an die eingebettete Post-Load-Seite nicht zu), also gibt
es keinen zweiten Kanal, der das heilt.
"""
import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.ui.visualizer.visualizer_window as VW


def _app():
    return QApplication.instance() or QApplication([])


def _payload(fid, r=0, g=0, b=0, intensity=0, heads=None):
    d = {"fid": fid, "r": r, "g": g, "b": b, "intensity": intensity,
         "pan": 128, "tilt": 128}
    if heads is not None:
        d["heads"] = heads
    return d


class PollDmxMergeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        # Nur den Poll-Puffer testen -> Bridge ohne __init__-Vollaufbau, aber mit
        # den echten Methoden (kein Nachbau der Logik im Test).
        self.b = VW.VisualizerBridge.__new__(VW.VisualizerBridge)
        self.b._poll_state = {}
        self.b._poll_events = []
        self.b._poll_dmx = {}
        self.b._poll_dmx_max = 2048

    def _poll(self):
        return json.loads(self.b.pollControl.__wrapped__(self.b)
                          if hasattr(self.b.pollControl, "__wrapped__")
                          else self.b.pollControl())

    def test_batches_between_two_polls_are_merged(self):
        """DER Regressionstest: zwei Batches mit VERSCHIEDENEN fids zwischen zwei
        Polls — vorher ueberlebte nur der zweite."""
        self.b._poll_set_dmx(json.dumps([_payload(1, r=255)]))
        self.b._poll_set_dmx(json.dumps([_payload(2, g=255)]))

        arr = json.loads(self._poll()["dmx"])
        fids = {d["fid"] for d in arr}
        self.assertEqual(fids, {1, 2},
                         "beide differentiellen Frames muessen den Poll erreichen")

    def test_same_fid_keeps_last_payload(self):
        self.b._poll_set_dmx(json.dumps([_payload(7, intensity=10)]))
        self.b._poll_set_dmx(json.dumps([_payload(7, intensity=200)]))

        arr = json.loads(self._poll()["dmx"])
        self.assertEqual(len(arr), 1)
        self.assertEqual(arr[0]["intensity"], 200)

    def test_dropped_heads_do_not_survive_as_stale_array(self):
        """Ganz-Payload-Ersatz statt dict.update: ``heads`` haengt nur bei
        head_count>=2 am Payload. Ein Key-Merge liesse das alte Array stehen, und
        JS cacht es dauerhaft (``if (heads) f.lastHeads = heads``) -> permanent
        falsche Pro-Kopf-Farben bei Spider/PAR-Bar/Mover-Bar."""
        self.b._poll_set_dmx(json.dumps([_payload(3, heads=[{"r": 255}])]))
        self.b._poll_set_dmx(json.dumps([_payload(3)]))          # ohne heads

        arr = json.loads(self._poll()["dmx"])
        self.assertNotIn("heads", arr[0],
                         "veraltetes heads-Array darf nicht ueberleben")

    def test_dmx_value_is_a_json_string(self):
        """Vertrag zur JS-Seite: dort laeuft ``JSON.parse(s.dmx)``. Legte man die
        Liste selbst in out['dmx'], wuerfe JSON.parse — der Wurf landete im
        aeusseren catch und ueberspraenge den DANACH folgenden events-Block,
        waehrend Python die Event-Queue schon geleert hat."""
        self.b._poll_set_dmx(json.dumps([_payload(1)]))
        self.assertIsInstance(self._poll()["dmx"], str)

    def test_buffer_is_drained_by_the_poll(self):
        self.b._poll_set_dmx(json.dumps([_payload(1)]))
        self.assertIn("dmx", self._poll())
        self.assertNotIn("dmx", self._poll(), "zweiter Poll ohne neue Daten")

    def test_broken_batch_neither_raises_nor_drops_the_buffer(self):
        """Der Slot haengt am dmxBatch-Emit des Service, der seine Targets in einer
        Schleife OHNE try/except bedient und keinen _bridge_slot_guard traegt — ein
        Wurf hier brachte das naechste Target (Live-View-Spiegel) um seinen Batch."""
        self.b._poll_set_dmx(json.dumps([_payload(1, r=255)]))
        self.b._poll_set_dmx("kein json")                  # defekt
        self.b._poll_set_dmx(json.dumps({"fid": 9}))       # Objekt statt Array
        self.b._poll_set_dmx(json.dumps([{"kein": "fid"}]))
        self.b._poll_set_dmx(json.dumps([_payload(2, g=255)]))

        arr = json.loads(self._poll()["dmx"])
        self.assertEqual({d["fid"] for d in arr}, {1, 2},
                         "gesunde Batches ueberleben einen defekten dazwischen")

    def test_buffer_has_a_backstop_cap(self):
        """Analog zum 512er-Deckel von _poll_events: pollt keine Seite (Fenster zu,
        Renderer nach CrashGuard-Give-up tot), darf der Puffer nicht unbegrenzt
        wachsen — ueber Repatch-Zyklen entstehen immer neue fids."""
        self.b._poll_dmx_max = 10
        for fid in range(50):
            self.b._poll_set_dmx(json.dumps([_payload(fid)]))

        self.assertLessEqual(len(self.b._poll_dmx), 10)
        arr = json.loads(self._poll()["dmx"])
        self.assertEqual({d["fid"] for d in arr}, set(range(40, 50)),
                         "die juengsten fids ueberleben, die aeltesten fallen")


if __name__ == "__main__":
    unittest.main()
