"""DEMO-04 — Bus-gekoppelte Matrix friert nicht mehr DUNKEL ein, wenn der Bus
zwar eine BPM>0 hat, seine Position aber nicht vorrueckt (keine laufende
``advance_frame``-Schleife: Vorschau-/Probe-/Validierungs-Render, pausierte Uhr).

Vorher: ``_advance_step`` nahm bei ``bpm>0`` bedingungslos den Bus-Sync-Pfad und
fror ``_step`` auf der (statischen) Bus-Position ein → bei Dimmer-Style = Intensitaet 0
= Fixtures dunkel. Jetzt erkennt es den stehenden Bus am Positions-Delta und faellt auf
Free-Run zurueck; bei Bus-Wiederanlauf snappt es zurueck auf Bus-Sync. Live
(Render-Thread tickt jeden Frame) ist die Position immer in Bewegung → byte-identisch.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.rgb_matrix import RgbMatrixInstance, MatrixStyle
from src.core.engine.tempo_bus import get_tempo_bus_manager, reset_tempo_bus_manager


def _mk(bus_id, style=MatrixStyle.DIMMER):
    m = RgbMatrixInstance("T")
    m.style = style
    m.matrix_speed = 2.0
    m.tempo_bus_id = bus_id
    m._running = True
    m.cols, m.rows = 4, 1
    m.fixture_grid = [1, 2, 3, 4]
    m._on_start()
    return m


class Demo04BusFreerunTest(unittest.TestCase):
    def setUp(self):
        reset_tempo_bus_manager()
        self.tbm = get_tempo_bus_manager()

    def tearDown(self):
        reset_tempo_bus_manager()

    def test_stalled_bus_freeruns_not_frozen(self):
        """bpm>0, Position steht (kein advance_frame) → _step rueckt vor (frueher: alle 0)."""
        self.tbm.resolve("A").set_bpm(120)
        m = _mk("A")
        steps = []
        for _ in range(6):
            m._advance_step(0.05)
            steps.append(round(m._step, 4))
        self.assertGreater(steps[-1], 0.0, f"eingefroren statt Free-Run: {steps}")
        self.assertGreater(len(set(steps)), 1, f"keine Animation: {steps}")

    def test_stalled_bus_not_blacked_out(self):
        """Render variiert ueber die Stall-Frames → kein statischer Black-out."""
        self.tbm.resolve("A").set_bpm(120)
        m = _mk("A")
        grids = set()
        for _ in range(8):
            m._advance_step(0.05)
            grids.add(tuple(m._render(m._step)))
        self.assertGreater(len(grids), 1, "Render statisch (eingefroren)")

    def test_live_bus_still_syncs(self):
        """bpm>0 MIT advance_frame jeden Frame → weiterhin echte Bus-Synchronitaet."""
        self.tbm.resolve("A").set_bpm(120)
        m = _mk("A")
        steps = []
        for _ in range(6):
            self.tbm.advance_frame(0.05)
            m._advance_step(0.05)
            steps.append(round(m._step, 6))
        self.assertEqual(steps, sorted(steps))
        self.assertGreater(steps[-1], steps[0])
        # _step folgt exakt der Bus-Position (mult=1, off=0).
        self.assertAlmostEqual(m._step, m._last_bus_pos - m._beat_anchor, places=6)

    def test_bpm_zero_still_freeruns(self):
        """bpm 0 (Bus nie gestartet) → Free-Run wie bisher."""
        self.tbm.resolve("A")  # bpm bleibt 0
        m = _mk("A")
        steps = []
        for _ in range(5):
            m._advance_step(0.05)
            steps.append(round(m._step, 4))
        self.assertGreater(steps[-1], 0.0)

    def test_resume_snaps_back_to_bus_sync(self):
        """Stall (Free-Run), dann Bus laeuft an → naechster Frame = Bus-Sync."""
        self.tbm.resolve("A").set_bpm(120)
        m = _mk("A")
        for _ in range(3):
            m._advance_step(0.05)               # Stall → Free-Run
        for _ in range(3):
            self.tbm.advance_frame(0.05)        # Bus laeuft
            m._advance_step(0.05)
        # Nach Wiederanlauf folgt _step wieder exakt der Bus-Position.
        self.assertAlmostEqual(m._step, m._last_bus_pos - m._beat_anchor, places=6)

    def test_global_freeze_holds_even_on_stall(self):
        """Globaler Freeze (F5) haelt die Position auch im Stall bewusst an."""
        self.tbm.resolve("A").set_bpm(120)
        m = _mk("A")
        m._advance_step(0.05)                   # 1. Frame (Bus-Sync)
        before = round(m._step, 6)
        self.tbm.toggle_freeze()                # global einfrieren
        try:
            for _ in range(4):
                m._advance_step(0.05)
            self.assertEqual(round(m._step, 6), before)
        finally:
            self.tbm.toggle_freeze()            # wieder auftauen


if __name__ == "__main__":
    unittest.main()
