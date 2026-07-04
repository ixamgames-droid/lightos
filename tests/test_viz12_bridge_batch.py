"""VIZ-12 Schritt 2: dmxBatch-Signal an VisualizerBridge + JS-Batch-Handler.

Deckt zwei Dinge ab (siehe docs/VIZ12_SERVICE_DESIGN.md Abschnitt (d)):
  1. Emit-Roundtrip: ``VisualizerBridge.dmxBatch`` existiert als echtes Qt-
     Signal(str), laesst sich verbinden und liefert den emittierten JSON-String
     unveraendert an den Slot (Signal-Spy per connect()). Das alte
     ``dmxUpdated``-Einzelsignal wurde in VIZ-13 3c-4 ENTFERNT (der Service pusht
     ausschliesslich als Batch ueber ``dmxBatch``) — die Tests hier belegen jetzt
     auch, dass es weg ist (Signal + JS-Handler).
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
# VIZ-13 3a-4: der tryChannel()/dmxBatch-Handler-Block wanderte aus dem
# ehemaligen EINEN <script>-Block in stage_scene.html nach
# scene_src/bridge/bridge.js (siehe docs/VIZ13_JS_NEUAUFBAU_DESIGN.md
# Abschnitt (a)). JsBatchHandlerBraceBalanceTest prueft deshalb seit 3a-4
# BEIDE Dateien statt nur stage_scene.html - die Pruefabsicht (additiver
# Handler ist da, syntaktisch balanciert, ruft updateFixture byte-identisch
# auf) bleibt unveraendert, nur die Fundstelle folgt dem Modul-Split.
_BRIDGE_JS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "ui", "visualizer", "scene_src", "bridge", "bridge.js",
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

    def test_dmx_updated_signal_removed(self):
        """VIZ-13 3c-4: das Legacy-Einzelsignal dmxUpdated wurde ENTFERNT — der
        Service pusht ausschliesslich als Batch (dmxBatch)."""
        self.assertFalse(hasattr(VW.VisualizerBridge, "dmxUpdated"),
                         "dmxUpdated muss entfernt sein (nur dmxBatch bleibt)")

    def test_dmx_batch_emit_roundtrip(self):
        received = []
        self.bridge.dmxBatch.connect(lambda payload: received.append(payload))

        json_str = '[{"fid": 1, "r": 255, "g": 0, "b": 0, "intensity": 255, "pan": 128, "tilt": 128}]'
        self.bridge.dmxBatch.emit(json_str)

        self.assertEqual(len(received), 1, "genau ein Slot-Aufruf pro emit()")
        self.assertEqual(received[0], json_str, "Payload muss unveraendert ankommen")

    def test_dmx_batch_multiple_emits_roundtrip_in_order(self):
        received = []
        self.bridge.dmxBatch.connect(lambda payload: received.append(payload))

        self.bridge.dmxBatch.emit('[{"fid": 1, "r": 1}]')
        self.bridge.dmxBatch.emit('[{"fid": 2, "r": 2}]')

        self.assertEqual(len(received), 2)
        self.assertIn('"fid": 1', received[0])
        self.assertIn('"fid": 2', received[1])


class JsBatchHandlerBraceBalanceTest(unittest.TestCase):
    """Statische Klammer-/Parens-Balance-Pruefung ueber stage_scene.html +
    scene_src/bridge/bridge.js (seit VIZ-13 3a-4, siehe Kommentar bei
    _BRIDGE_JS_PATH oben) -- kein echtes QWebEngine noetig, faengt kaputte
    additive JS-Snippets frueh."""

    def setUp(self):
        with open(_HTML_PATH, encoding="utf-8") as f:
            self.content = f.read()
        with open(_BRIDGE_JS_PATH, encoding="utf-8") as f:
            self.bridge_js_content = f.read()

    def test_dmx_batch_handler_present_and_legacy_removed(self):
        self.assertIn("bridge.dmxBatch", self.bridge_js_content,
                       "JS muss bridge.dmxBatch verbinden")
        # VIZ-13 3c-4: der Legacy-Einzel-Handler bridge.dmxUpdated wurde entfernt.
        self.assertNotIn("bridge.dmxUpdated.connect", self.bridge_js_content,
                          "Legacy dmxUpdated-Handler muss entfernt sein")

    def test_dmx_batch_handler_calls_unmodified_update_fixture(self):
        match = re.search(
            r"bridge\.dmxBatch\.connect\(j => \{(.*?)\}\);",
            self.bridge_js_content, re.DOTALL,
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
        # stage_scene.html: seit 3a-4 nur noch klassische Loader-Scripts +
        # das eine type=module-Script (kein Inline-Code mehr, siehe
        # docs/VIZ13_JS_NEUAUFBAU_DESIGN.md Abschnitt (a)) - dennoch
        # weiterhin geprueft (leere/kurze Bloecke sind trivial balanciert).
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", self.content, re.DOTALL)
        self.assertTrue(scripts, "keine <script>-Bloecke gefunden")
        for i, block in enumerate(scripts):
            with self.subTest(html_block=i):
                self.assertEqual(block.count("{"), block.count("}"),
                                  f"geschweifte Klammern unbalanciert in HTML-Block {i}")
                self.assertEqual(block.count("("), block.count(")"),
                                  f"runde Klammern unbalanciert in HTML-Block {i}")
        # scene_src/bridge/bridge.js: der eigentliche dmxBatch-Handler-Code.
        with self.subTest(block="bridge.js"):
            self.assertEqual(
                self.bridge_js_content.count("{"), self.bridge_js_content.count("}"),
                "geschweifte Klammern unbalanciert in bridge.js")
            self.assertEqual(
                self.bridge_js_content.count("("), self.bridge_js_content.count(")"),
                "runde Klammern unbalanciert in bridge.js")


if __name__ == "__main__":
    unittest.main()
