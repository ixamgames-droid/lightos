"""VIZ-71: Lichtdaten schneller und schlanker zum Viewer (Python-Seite).

Bis VIZ-70 holte sich die Seite die DMX-Werte alle 130 ms per ``pollControl``
ab — im Mittel rund 100 ms Verzoegerung, schlimmstenfalls ueber 200 ms, und
jede Poll-Antwort schleppte die volle Geraeteliste mit (rund 18 KB, achtmal je
Sekunde). Jetzt schiebt der Service die Werte im Takt der Qualitaetsstufe per
``runJavaScript`` an die Seite, und der Poll liefert nur noch Geaendertes.

Alles hier laeuft ohne WebEngine: die Seite ist eine Attrappe, die die
``runJavaScript``-Aufrufe aufzeichnet und die Rueckrufe von Hand ausloest. Die
JS-Haelfte steht in ``test_viz71_apply_dmx_scene.py``.
"""
import json
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.visualizer.visualizer_service import (
    VisualizerService, VisualizerTarget, _build_fixture_payload,
)

_app = QApplication.instance() or QApplication([])


# ── Attrappen ────────────────────────────────────────────────────────────────
class _Universe:
    def __init__(self, werte=None):
        self.puffer = bytearray(512)
        for adr, v in (werte or {}).items():
            self.puffer[adr - 1] = v

    def get_channel(self, adr):
        return self.puffer[adr - 1]

    def get_all(self):
        return bytes(self.puffer)

    def set_channel(self, adr, v):
        self.puffer[adr - 1] = v


class _OutputManager:
    """Liefert den GESENDETEN Frame (nach Blackout/NOT-AUS-Masken)."""

    def __init__(self):
        self.frames = {}

    def get_display_frame(self, u):
        return self.frames.get(u)


_KANAELE = [("color_r", 1), ("color_g", 2), ("color_b", 3),
            ("intensity", 4), ("pan", 5), ("tilt", 6)]


def _kanaele():
    return [SimpleNamespace(attribute=a, channel_number=n, ranges=[])
            for a, n in _KANAELE]


def _fixture(fid, adresse):
    return SimpleNamespace(fid=fid, universe=1, address=adresse,
                           invert_pan=False, invert_tilt=False, swap_pan_tilt=False)


def _state(n=2, positions=True):
    fixtures = [_fixture(i + 1, 1 + i * 10) for i in range(n)]
    st = SimpleNamespace(
        universes={1: _Universe()},
        visualizer_positions={f.fid: (0.0, 6.0, 0.0) for f in fixtures} if positions else {},
        visualizer_docks={}, visualizer_rotations={}, live_view_positions={},
        output_manager=_OutputManager(),
        get_patched_fixtures=lambda: fixtures,
        _callbacks=[],
    )
    st.subscribe = st._callbacks.append
    st.unsubscribe = lambda cb: st._callbacks.remove(cb) if cb in st._callbacks else None
    st._fixtures = fixtures
    return st


class _KanalPatch:
    """``get_channels_for_patched`` fuer die Attrappen-Geraete umlenken."""

    def __enter__(self):
        import src.core.app_state as m
        self._m, self._orig = m, m.get_channels_for_patched
        m.get_channels_for_patched = lambda f: _kanaele()
        return self

    def __exit__(self, *a):
        self._m.get_channels_for_patched = self._orig


class _TestBasis(unittest.TestCase):
    def setUp(self):
        self._patch = _KanalPatch().__enter__()

    def tearDown(self):
        self._patch.__exit__()


# ── S1: der Service liefert strukturiert ─────────────────────────────────────
class ServiceStrukturiertTest(_TestBasis):
    def _ziel(self, svc, **kw):
        empfangen = []
        t = VisualizerTarget("t", lambda s: empfangen.append(("json", s)),
                             emit_payloads=lambda arr, full, seq:
                             empfangen.append((arr, full, seq)), **kw)
        svc.attach_target(t)
        svc.set_target_active(t, True)
        return t, empfangen

    def test_emit_payloads_bekommt_liste_full_und_seq(self):
        st = _state()
        svc = VisualizerService(st)
        _t, emp = self._ziel(svc)
        svc._tick()
        self.assertEqual(len(emp), 1)
        arr, full, seq = emp[0]
        self.assertIsInstance(arr, list)
        self.assertTrue(full, "erster Tick nach dem Andocken ist ein Vollbatch")
        self.assertEqual(sorted(p["fid"] for p in arr), [1, 2])
        st.universes[1].set_channel(1, 200)
        svc._tick()
        arr2, full2, seq2 = emp[1]
        self.assertFalse(full2)
        self.assertEqual([p["fid"] for p in arr2], [1], "nur das geaenderte Geraet")
        self.assertGreater(seq2, seq, "jeder gebaute Tick bekommt eine neue Nummer")

    def test_alter_weg_ohne_emit_payloads_bleibt(self):
        st = _state()
        svc = VisualizerService(st)
        empfangen = []
        t = VisualizerTarget("alt", empfangen.append)
        svc.attach_target(t)
        svc.set_target_active(t, True)
        svc._tick()
        self.assertEqual(len(empfangen), 1)
        self.assertEqual(len(json.loads(empfangen[0])), 2)

    def test_fehler_in_einem_ziel_bremst_das_andere_nicht(self):
        st = _state()
        svc = VisualizerService(st)

        def kaputt(arr, full, seq):
            raise RuntimeError("Seite weg")
        a = VisualizerTarget("a", lambda s: None, emit_payloads=kaputt)
        svc.attach_target(a)
        svc.set_target_active(a, True)
        _b, emp = self._ziel(svc)
        svc._tick()
        self.assertEqual(len(emp), 1, "Ziel b bekam seinen Batch trotz Fehler in a")
        self.assertTrue(a.needs_full, "das gestoerte Ziel wird beim naechsten Tick voll beliefert")

    def test_timer_folgt_dem_schnellsten_aktiven_ziel(self):
        st = _state()
        svc = VisualizerService(st)
        langsam, _ = self._ziel(svc, tick_ms=66)
        self.assertEqual(svc._timer.interval(), 66)
        schnell, _ = self._ziel(svc, tick_ms=22)
        self.assertEqual(svc._timer.interval(), 22)
        svc.set_target_active(schnell, False)
        self.assertEqual(svc._timer.interval(), 66, "inaktive Ziele zaehlen nicht")
        svc.set_target_tick_ms(langsam, 33)
        self.assertEqual(svc._timer.interval(), 33)
        svc.shutdown()


if __name__ == "__main__":
    unittest.main()
