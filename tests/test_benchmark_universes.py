"""T-8: Smoke-Test fuer das Render-Benchmark-Tool — schuetzt vor API-Drift
(add_fixture / _render_frame / FunctionManager.start) und prueft die Kennzahlen."""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LIGHTOS_NO_OUTPUT_THREAD", "1")

from PySide6.QtWidgets import QApplication

import tools.benchmark_universes as B

_app = QApplication.instance() or QApplication([])


class BenchmarkSmokeTest(unittest.TestCase):
    # 44 Hz entsprechen 22,7 ms/Frame. 20 ms lässt messbaren Headroom und ist
    # zugleich locker genug für Windows-/CI-Jitter bei einem kleinen 1U-Rig.
    P95_BUDGET_MS = 20.0
    def test_pct_helper(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        self.assertEqual(B._pct(data, 0), 1.0)
        self.assertEqual(B._pct(data, 100), 5.0)
        self.assertEqual(B._pct([], 50), 0.0)

    def test_run_benchmark_smoke(self):
        rows = B.run_benchmark(universe_counts=(1,), pars_per_universe=2, frames=3)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["universes"], 1)
        self.assertEqual(r["frames"], 3)
        self.assertGreaterEqual(r["fixtures"], 1)   # PARs (+ MH) wurden gepatcht
        self.assertGreater(r["p50"], 0.0)
        self.assertGreater(r["fps"], 0.0)
        # Tabelle ist wohlgeformt.
        table = B._fmt_table(rows)
        self.assertIn("Universen", table)
        self.assertIn("| 1 |", table)

    def test_single_universe_p95_stays_below_44hz_budget(self):
        rows = B.run_benchmark(universe_counts=(1,), pars_per_universe=2, frames=30)
        self.assertLess(
            rows[0]["p95"], self.P95_BUDGET_MS,
            f"Render-p95 {rows[0]['p95']:.2f} ms überschreitet das {self.P95_BUDGET_MS} ms-Gate")

    def tearDown(self):
        # run_benchmark ruft am Ende _reset(); zur Sicherheit Singleton leeren.
        B._reset()


if __name__ == "__main__":
    unittest.main()
