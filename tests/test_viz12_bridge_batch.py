"""VIZ-12 Schritt 2: dmxBatch-Signal an VisualizerBridge + JS-Batch-Handler.

Deckt zwei Dinge ab (siehe docs/VIZ12_SERVICE_DESIGN.md Abschnitt (d)):
  1. Emit-Roundtrip: ``VisualizerBridge.dmxBatch`` existiert als echtes Qt-
     Signal(str), laesst sich verbinden und liefert den emittierten JSON-String
     unveraendert an den Slot (Signal-Spy per connect()). Das alte
     ``dmxUpdated``-Einzelsignal bleibt unveraendert bestehen (Kompat/Test-API,
     Orchestrator-Entscheidung 3) -- dieser Schritt baut KEINEN Live-Pfad um,
     der noch am alten Signal haengt.
  2. JS-Klammer-Balance: der neu eingefuegte ``dmxBatch``-Handler-Block in
     stage_scene.html ist syntaktisch balanciert (Klammern/Parens ueber den
     gesamten <script>-Block), damit ein kaputtes additives Snippet nicht erst
     zur Laufzeit im echten QWebEngine auffaellt.
"""
import os
import re
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.ui.visualizer.visualizer_window as VW
from src.core.app_state import get_state
from src.core.show.show_file import reset_show
from src.core.undo import get_undo_stack

_app = QApplication.instance() or QApplication([])

_HTML_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "ui", "visualizer", "stage_scene.html",
)


class DmxBatchSignalExistsTest(unittest.TestCase):
    def setUp(self):
        reset_show()
        self.state = get_state()
        get_undo_stack().clear()
        self.bridge = VW.VisualizerBridge(self.state)

    def tearDown(self):
        self.bridge.dispose()

    def test_dmx_batch_signal_present_on_bridge_class(self):
        self.assertTrue(hasattr(VW.VisualizerBridge, "dmxBatch"),
                         "VisualizerBridge muss ein dmxBatch-Signal exponieren")

    def test_dmx_updated_signal_still_present(self):
        """Kompat: Einzelsignal bleibt bestehen (Orchestrator-Entscheidung 3)."""
        self.assertTrue(hasattr(VW.VisualizerBridge, "dmxUpdated"))

    def test_dmx_batch_emit_roundtrip(self):
        received = []
        self.bridge.dmxBatch.connect(lambda payload: received.append(payload))

        json_str = '[{"fid": 1, "r": 255, "g": 0, "b": 0, "intensity": 255, "pan": 128, "tilt": 128}]'
        self.bridge.dmxBatch.emit(json_str)

        self.assertEqual(len(received), 1, "genau ein Slot-Aufruf pro emit()")
        self.assertEqual(received[0], json_str, "Payload muss unveraendert ankommen")

    def test_dmx_batch_emit_does_not_fire_dmx_updated(self):
        """dmxBatch und dmxUpdated sind unabhaengige Signale -- ein Batch-Emit
        darf keinen dmxUpdated-Slot ausloesen (kein versehentliches Aliasing)."""
        legacy_received = []
        self.bridge.dmxUpdated.connect(lambda payload: legacy_received.append(payload))

        self.bridge.dmxBatch.emit('[{"fid": 1}]')

        self.assertEqual(len(legacy_received), 0)

    def test_dmx_batch_multiple_emits_roundtrip_in_order(self):
        received = []
        self.bridge.dmxBatch.connect(lambda payload: received.append(payload))

        self.bridge.dmxBatch.emit('[{"fid": 1, "r": 1}]')
        self.bridge.dmxBatch.emit('[{"fid": 2, "r": 2}]')

        self.assertEqual(len(received), 2)
        self.assertIn('"fid": 1', received[0])
        self.assertIn('"fid": 2', received[1])


class JsBatchHandlerBraceBalanceTest(unittest.TestCase):
    """Statische Klammer-/Parens-Balance-Pruefung ueber stage_scene.html --
    kein echtes QWebEngine noetig, faengt kaputte additive JS-Snippets frueh."""

    def setUp(self):
        with open(_HTML_PATH, encoding="utf-8") as f:
            self.content = f.read()

    def test_dmx_batch_handler_present_and_additive(self):
        self.assertIn("bridge.dmxBatch", self.content,
                       "JS muss bridge.dmxBatch verbinden")
        self.assertIn("bridge.dmxUpdated", self.content,
                       "altes dmxUpdated-Handler-Snippet muss erhalten bleiben")

    def test_dmx_batch_handler_calls_unmodified_update_fixture(self):
        match = re.search(
            r"bridge\.dmxBatch\.connect\(j => \{(.*?)\}\);",
            self.content, re.DOTALL,
        )
        self.assertIsNotNone(match, "dmxBatch-Handler-Block nicht gefunden")
        body = match.group(1)
        self.assertIn("JSON.parse(j)", body)
        self.assertIn("for (const d of arr)", body)
        self.assertIn(
            "updateFixture(d.fid, d.r, d.g, d.b, d.intensity, d.pan||128, "
            "d.tilt||128, d.heads||null)",
            body,
            "updateFixture-Aufruf muss byte-identisch zum dmxUpdated-Handler sein",
        )

    def test_all_script_blocks_are_brace_and_paren_balanced(self):
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", self.content, re.DOTALL)
        self.assertTrue(scripts, "keine <script>-Bloecke gefunden")
        for i, block in enumerate(scripts):
            with self.subTest(block=i):
                self.assertEqual(block.count("{"), block.count("}"),
                                  f"geschweifte Klammern unbalanciert in Block {i}")
                self.assertEqual(block.count("("), block.count(")"),
                                  f"runde Klammern unbalanciert in Block {i}")


if __name__ == "__main__":
    unittest.main()
