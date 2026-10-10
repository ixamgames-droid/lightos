"""VIZ-70: Haupt-Thread (Qt-UI/GIL) entlasten.

Gemessen (Windows-Rig, Extremfall): mit sichtbarer 2D-Buehne ~65 % des
Hauptthreads in ``StageCanvas.paintEvent``/``FixtureRenderer.draw`` — dort setzt
QtWebEngine auch das 3D-Bild zusammen (3,6 statt 57,7 FPS). Auf Linux baute
``VisualizerService._tick`` 31x/s den kompletten Snapshot neu, auch bei
stehendem DMX, und rechnete dabei je Geraet ``visualizer_positions`` neu
(O(n^2)). Das Simple Desk taktete ab dem Bau, auch nie gezeigt.

Abgesichert:
- Service: Frame-Gate (unveraendert -> kein Snapshot), Positionen einmal je Tick,
  Gate bleibt bei Attrappen ohne ``get_all`` aus, Event/DMX/needs_full/
  Sicherheitsnetz bauen wieder.
- StageCanvas: unsichtbar -> kein Neuzeichnen; statisch -> kein Neuzeichnen je
  Takt; Wertaenderung/Animation -> Neuzeichnen; Hintergrund-Pixmap aendert das
  Bild nicht (pixelgleich) und wird nur bei Zoom/Raster neu gebaut;
  Effekt-Vorabzuordnung == alte Schleifen.
- Simple Desk: nie gezeigt -> kein Takt, kein Fader-Abgleich.
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from _qt_lifecycle import destroy_all_top_level_widgets

from src.ui.visualizer.visualizer_service import VisualizerService, VisualizerTarget

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(_app)


# ════════════════════════════════════════════════════════════════════════════
# 1. VisualizerService: Frame-Gate + Positionen einmal je Tick
# ════════════════════════════════════════════════════════════════════════════

class _Uni:
    """Universe-Attrappe MIT ``get_all`` (wie das echte Universe)."""

    def __init__(self, values):
        self.values = values

    def get_channel(self, addr):
        return self.values.get(addr, 0)

    def get_all(self):
        return bytes(self.values.get(i, 0) for i in range(1, 513))


class _UniOhneGetAll:
    def __init__(self, values):
        self.values = values

    def get_channel(self, addr):
        return self.values.get(addr, 0)


class _State:
    """State-Attrappe; ``visualizer_positions`` ist wie am echten AppState eine
    Property (dort rechnet sie bei JEDEM Zugriff alle Weltpositionen neu)."""

    def __init__(self, fixtures, universes, positions):
        self._fixtures = fixtures
        self.universes = universes
        self._positions = positions
        self.pos_zugriffe = 0
        self.visualizer_docks = {}
        self.visualizer_rotations = {}
        self.live_view_positions = {}
        self._callbacks = []

    @property
    def visualizer_positions(self):
        self.pos_zugriffe += 1
        return dict(self._positions)

    def get_patched_fixtures(self):
        return self._fixtures

    def subscribe(self, cb):
        self._callbacks.append(cb)

    def unsubscribe(self, cb):
        if cb in self._callbacks:
            self._callbacks.remove(cb)

    def emit(self, event, data=None):
        for cb in list(self._callbacks):
            cb(event, data)


def _chans():
    return [SimpleNamespace(attribute=a, channel_number=n) for a, n in (
        ("color_r", 1), ("color_g", 2), ("color_b", 3), ("intensity", 4))]


class ServiceFrameGateTest(unittest.TestCase):
    def setUp(self):
        import src.core.app_state as app_state_mod
        self._mod = app_state_mod
        self._orig = app_state_mod.get_channels_for_patched
        app_state_mod.get_channels_for_patched = lambda fixture: _chans()

    def tearDown(self):
        self._mod.get_channels_for_patched = self._orig

    def _service(self, n=6, uni_cls=_Uni):
        self.values = {}
        fixtures = []
        for i in range(n):
            fid = i + 1
            fixtures.append(SimpleNamespace(fid=fid, universe=0, address=i * 4 + 1))
            self.values[i * 4 + 4] = 255
        self.state = _State(fixtures, {0: uni_cls(self.values)},
                            {f.fid: (0.0, 0.0, 0.0) for f in fixtures})
        svc = VisualizerService(self.state)
        self.builds = []
        echt = svc._build_snapshot

        def _zaehlend():
            self.builds.append(1)
            return echt()
        svc._build_snapshot = _zaehlend
        self.sink = []
        target = VisualizerTarget("t", self.sink.append)
        svc.attach_target(target)
        svc.set_target_active(target, True)
        return svc, target

    def test_unveraenderter_tick_baut_keinen_snapshot(self):
        svc, _t = self._service()
        svc._tick()                        # erster Tick: voller Bestand
        self.assertEqual(len(self.builds), 1)
        self.assertEqual(len(self.sink), 1)
        for _ in range(5):
            svc._tick()
        self.assertEqual(len(self.builds), 1,
                         "stehendes DMX darf keinen neuen Snapshot bauen")
        self.assertEqual(len(self.sink), 1)

    def test_dmx_aenderung_baut_und_sendet(self):
        svc, _t = self._service()
        svc._tick()
        self.values[1] = 99                # fid 1: Rot aendert sich
        svc._tick()
        self.assertEqual(len(self.builds), 2)
        self.assertEqual(len(self.sink), 2)
        self.assertIn('"fid": 1', self.sink[-1])
        self.assertNotIn('"fid": 2', self.sink[-1])

    def test_state_event_macht_gate_ungueltig(self):
        svc, _t = self._service()
        svc._tick()
        self.state.emit("programmer_changed")
        svc._tick()
        self.assertEqual(len(self.builds), 2,
                         "ein State-Event (z. B. Patch) muss neu bauen lassen")

    def test_needs_full_geht_immer_durch(self):
        svc, target = self._service()
        svc._tick()
        svc.force_full_resync(target)
        svc._tick()
        self.assertEqual(len(self.builds), 2)
        self.assertEqual(len(self.sink), 2, "voller Bestand trotz stehendem DMX")

    def test_sicherheitsnetz_baut_nach_max_skips(self):
        svc, _t = self._service()
        svc._tick()
        for _ in range(VisualizerService.GATE_MAX_SKIPS):
            svc._tick()
        self.assertEqual(len(self.builds), 1)
        svc._tick()
        self.assertEqual(len(self.builds), 2,
                         "spaetestens nach GATE_MAX_SKIPS Takten wird gebaut")

    def test_platzieren_aendert_signatur(self):
        svc, _t = self._service()
        svc._tick()
        del self.state._positions[3]
        svc._tick()
        self.assertEqual(len(self.builds), 2)

    def test_ohne_get_all_bleibt_gate_aus(self):
        """Attrappen ohne ``get_all`` (test_viz12_service) -> Verhalten wie vorher."""
        svc, _t = self._service(uni_cls=_UniOhneGetAll)
        svc._tick()
        svc._tick()
        self.assertEqual(len(self.builds), 2)
        self.assertEqual(len(self.sink), 1, "Diff bleibt leer, gesendet wird nichts")

    def test_positionen_einmal_je_tick(self):
        """Vorher je Geraet ein Zugriff (O(n^2)); jetzt hoechstens Signatur + Bau."""
        svc, _t = self._service(n=12)
        self.state.pos_zugriffe = 0
        svc._tick()
        self.assertLessEqual(self.state.pos_zugriffe, 2)


# ════════════════════════════════════════════════════════════════════════════
# 2. StageCanvas: nur sichtbar, nur bei Aenderung, Hintergrund-Cache
# ════════════════════════════════════════════════════════════════════════════

from src.core.app_state import get_state                 # noqa: E402
from src.ui.views import live_view                       # noqa: E402


def _fx(fid, address):
    return SimpleNamespace(fid=fid, universe=1, address=address,
                           label=f"PAR-{fid}", fixture_type="PAR")


class _CanvasCase(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        if 1 not in self.state.universes:
            self.state.universes[1] = self.state.output_manager.add_universe(1)
        self.fixtures = [_fx(1, 1), _fx(2, 11)]
        self.state.get_patched_fixtures = lambda: self.fixtures
        self.addCleanup(lambda: self.state.__dict__.pop("get_patched_fixtures", None))

    def _canvas(self, zoom=1.0):
        c = live_view.StageCanvas()
        c._update_timer.stop()             # Takt hier von Hand
        c.zoom = zoom
        c.world_w, c.world_h = 600, 400
        c.grid_visible, c.grid_size = True, 50
        c._fixture_size = 30.0
        c._apply_canvas_size()
        c._positions = {1: (150.0, 200.0), 2: (400.0, 200.0)}
        c._nn_gap = {1: 1e9, 2: 1e9}
        c._running_functions = lambda: []
        return c


class CanvasDrosselTest(_CanvasCase):
    def _gezaehlt(self, c):
        calls = []
        c.update = lambda *a: calls.append(1)
        return calls

    def test_unsichtbar_kein_neuzeichnen(self):
        c = self._canvas()
        calls = self._gezaehlt(c)
        for _ in range(3):
            c._on_render_tick()
        self.assertEqual(calls, [], "nie gezeigte Canvas darf nicht neu zeichnen")

    def test_statisch_zeichnet_nicht_je_takt(self):
        c = self._canvas()
        c.show()
        _app.processEvents()
        c.repaint()                        # ein echtes Bild: nichts animiert
        self.assertFalse(c._animiert)
        calls = self._gezaehlt(c)
        c._on_render_tick()                # erste Signatur -> zeichnen
        self.assertEqual(len(calls), 1)
        for _ in range(4):
            c._on_render_tick()
        self.assertEqual(len(calls), 1, "unveraenderte Werte -> kein Neuzeichnen")

        uni = self.state.universes[1]
        alt = uni.get_channel(1)
        self.addCleanup(uni.set_channel, 1, alt)
        uni.set_channel(1, (alt + 77) % 256)
        c._on_render_tick()
        self.assertEqual(len(calls), 2, "DMX-Aenderung muss neu zeichnen")

    def test_sicherheitsnetz(self):
        c = self._canvas()
        c.show()
        _app.processEvents()
        c.repaint()
        calls = self._gezaehlt(c)
        for _ in range(live_view.StageCanvas.MAX_TAKTE_OHNE_PAINT + 1):
            c._on_render_tick()
        self.assertEqual(len(calls), 2)

    def test_animiert_zeichnet_jeden_takt(self):
        c = self._canvas()
        c._running_functions = lambda: [SimpleNamespace(name="FX", fixture_ids=[1])]
        c.show()
        _app.processEvents()
        c.repaint()
        self.assertTrue(c._animiert, "Effekt-Ring pulsiert -> animiert")
        calls = self._gezaehlt(c)
        for _ in range(3):
            c._on_render_tick()
        self.assertEqual(len(calls), 3)


class CanvasHintergrundTest(_CanvasCase):
    def _bild(self, c):
        return c.grab().toImage()

    def test_hintergrund_pixmap_ist_pixelgleich(self):
        for zoom in (1.0, 1.37, 0.6):
            c = self._canvas(zoom)
            mit = self._bild(c)
            self.assertIsNotNone(c._bg_pixmap, "Hintergrund wurde nicht gecacht")
            c.BG_CACHE_MAX_PIXEL = 0       # Cache aus -> direkt wie vorher
            ohne = self._bild(c)
            self.assertIsNone(c._hintergrund_pixmap())
            self.assertEqual(mit, ohne, f"Bild mit Cache weicht ab (Zoom {zoom})")

    def test_cache_nur_bei_zoom_oder_raster_neu(self):
        c = self._canvas()
        pm1 = c._hintergrund_pixmap()
        self.assertIs(c._hintergrund_pixmap(), pm1)
        c.set_zoom(1.5)
        pm2 = c._hintergrund_pixmap()
        self.assertIsNot(pm2, pm1)
        c.grid_size = 25
        self.assertIsNot(c._hintergrund_pixmap(), pm2)


class EffektVorabTest(_CanvasCase):
    """Die je Bild vorberechnete Zuordnung liefert dasselbe wie die alten
    Schleifen je Geraet."""

    def test_gleiches_ergebnis_wie_alte_schleifen(self):
        from src.core.engine.effect_layers import LayerType
        sq = lambda f: SimpleNamespace(type=LayerType.SQUARE, frequency=f)  # noqa: E731
        other = SimpleNamespace(type=None, frequency=9.0)

        class _Szene:
            name = "Methode"

            def _values(self):            # Methode statt Liste -> kein Treffer
                return []
        running = [
            SimpleNamespace(name="Dim", fixture_ids=[1, 2], target_attribute="intensity",
                            layers=[other, sq(4.0)]),
            SimpleNamespace(name="EFX", fixtures=[SimpleNamespace(fid=2),
                                                  SimpleNamespace(fid=3)]),
            SimpleNamespace(name="MTX", fixture_grid=[3, None, [4], 4]),
            SimpleNamespace(name="Szene", _values=[SimpleNamespace(fixture_id=4)]),
            _Szene(),
            SimpleNamespace(name="Null", fixture_ids={5}, target_attribute="intensity",
                            layers=[sq(0.0)]),
            SimpleNamespace(name="Spaet", fixture_ids=(5, 6), target_attribute="intensity",
                            layers=[sq(2.5)]),
            SimpleNamespace(name="Nested", fixture_ids=[[1], 6]),
        ]
        c = self._canvas()
        vorab = c._effekt_vorab(running)
        for fid in range(1, 8):
            fx = SimpleNamespace(fid=fid, universe=99, address=1)
            alt = c._get_strobe_info(fid, fx, running)[0]
            neu = c._get_strobe_info(fid, fx, running, vorab)[0]
            self.assertEqual(alt, neu, f"Strobe fid {fid}")
            self.assertEqual(c._get_active_effects(fid, alt, running),
                             c._get_active_effects(fid, alt, running, vorab),
                             f"Effekte fid {fid}")


# ════════════════════════════════════════════════════════════════════════════
# 3. Simple Desk: nie gezeigt -> kein Takt, kein Abgleich
# ════════════════════════════════════════════════════════════════════════════

class SimpleDeskUnsichtbarTest(unittest.TestCase):
    def test_nie_gezeigt_kein_takt_und_kein_abgleich(self):
        from src.ui.views.simple_desk import SimpleDeskView
        st = get_state()
        if 1 not in st.universes:
            st.universes[1] = st.output_manager.add_universe(1)
        uni = st.universes[1]
        alt = uni.get_channel(5)
        self.addCleanup(uni.set_channel, 5, alt)
        neu = (alt + 77) % 256

        view = SimpleDeskView()
        view._universe = 1
        self.assertFalse(view._sync_timer.isActive())
        uni.set_channel(5, neu)
        view._sync_from_output()
        self.assertNotEqual(view._faders[4]._value, neu,
                            "unsichtbares Pult darf keine Fader nachziehen")

        view.show()                        # showEvent holt den Stand nach
        _app.processEvents()
        self.assertEqual(view._faders[4]._value, neu)
        self.assertTrue(view._sync_timer.isActive())
        view.hide()


if __name__ == "__main__":
    unittest.main()


# ════════════════════════════════════════════════════════════════════════════
# 4. Weitere Dauer-Takte: unsichtbar nichts tun, sichtbar wie vorher
# ════════════════════════════════════════════════════════════════════════════

class DauerTakteUnsichtbarTest(unittest.TestCase):
    def test_dmx_monitor(self):
        from src.ui.views.dmx_monitor_view import DmxMonitorView
        v = DmxMonitorView()
        v._timer.stop()
        calls = []
        v._grid.set_values = lambda data: calls.append(1)
        v._refresh()
        self.assertEqual(calls, [], "unsichtbarer Monitor darf nicht abgleichen")
        v.show()
        _app.processEvents()
        v._refresh()
        self.assertEqual(calls, [1])
        v.hide()

    def test_output_view(self):
        from src.core.dmx.universe import Universe
        from src.ui.views.output_view import OutputView
        st = get_state()
        st.universes.setdefault(1, Universe(1))
        v = OutputView()
        v._timer.stop()
        v._spin_univ.setValue(1)
        cells = v._cells.get(1) or []
        self.assertTrue(cells, "Universe 1 ohne Zellen")
        calls = []
        cells[0].set_value = lambda val: calls.append(val)
        v._refresh()
        self.assertEqual(calls, [])
        v.show()
        _app.processEvents()
        v._refresh()
        self.assertEqual(len(calls), 1)
        v.hide()

    def test_function_manager_laufstatus(self):
        from src.ui.views.function_manager_view import FunctionManagerView
        v = FunctionManagerView()
        v._timer.stop()
        calls = []
        echt = v._fm.is_running
        v._fm = SimpleNamespace(is_running=lambda fid: calls.append(fid) or echt(fid))
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QTreeWidgetItem
        item = QTreeWidgetItem(["Testfunktion"])
        item.setData(0, Qt.ItemDataRole.UserRole, 4711)
        v._tree.addTopLevelItem(item)
        v._refresh_running_state()
        self.assertEqual(calls, [])
        v.show()
        _app.processEvents()
        v._refresh_running_state()
        self.assertIn(4711, calls, "sichtbar wird der Laufstatus wie bisher gelesen")
        v.hide()

    def test_matrix_vorschau(self):
        from src.ui.views.rgb_matrix_view import MatrixPreview
        pv = MatrixPreview()
        pv._timer.stop()
        calls = []
        pv.set_matrix(SimpleNamespace(_step=0.0, matrix_speed=1.0,
                                      preview_pixels=lambda: calls.append(1) or []))
        pv._tick()
        self.assertEqual(calls, [], "unsichtbare Vorschau rechnet nicht")
        pv.show()
        _app.processEvents()
        pv._tick()
        self.assertEqual(calls, [1])
        pv.hide()


# ════════════════════════════════════════════════════════════════════════════
# 5. Review-Befunde: Patch-Aenderung bei gleicher fid, gebrochener DPR
# ════════════════════════════════════════════════════════════════════════════

class CanvasPatchAenderungTest(_CanvasCase):
    def _bereit(self):
        c = self._canvas()
        c.show()
        _app.processEvents()
        c.repaint()
        calls = []
        c.update = lambda *a: calls.append(1)
        c._on_render_tick()                # Signatur steht
        calls.clear()
        c._on_render_tick()
        self.assertEqual(calls, [])
        return c, calls

    def test_umadressieren_zeichnet_sofort(self):
        c, calls = self._bereit()
        self.fixtures[0].address = 101     # gleiche fid, neue Adresse
        c._on_render_tick()
        self.assertEqual(len(calls), 1, "Umadressieren muss sofort neu zeichnen")

    def test_bereich_und_invert_zeichnen_sofort(self):
        c, calls = self._bereit()
        self.fixtures[1].pan_range_deg = 360
        c._on_render_tick()
        self.fixtures[1].invert_pan = True
        c._on_render_tick()
        self.assertEqual(len(calls), 2)

    def test_patch_changed_event_zeichnet_sofort(self):
        c, calls = self._bereit()
        from src.core.sync import get_sync, SyncEvent
        get_sync().emit(SyncEvent.PATCH_CHANGED, None)   # z. B. Profil geaendert
        c._on_render_tick()
        self.assertEqual(len(calls), 1)


_DPR_SKRIPT = r"""
import os, sys
sys.path.insert(0, os.getcwd())
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication
app = QApplication([])
from src.core.app_state import get_state
from src.ui.views import live_view as lv
st = get_state()
st.get_patched_fixtures = lambda: [SimpleNamespace(fid=1, universe=1, address=1,
                                                   label="A", fixture_type="PAR")]
c = lv.StageCanvas(); c._update_timer.stop(); c._running_functions = lambda: []
c.zoom = 1.0; c.world_w, c.world_h = 603, 403; c._fixture_size = 30.0
c._apply_canvas_size(); c._positions = {1: (150.0, 150.0)}; c._nn_gap = {1: 1e9}
mit = c.grab().toImage()
c.BG_CACHE_MAX_PIXEL = 0
ohne = c.grab().toImage()
W, H = mit.width(), mit.height()
innen = sum(1 for y in range(H - 1) for x in range(W - 1)
            if mit.pixel(x, y) != ohne.pixel(x, y))
rand = {mit.pixelColor(W - 1, y).name() for y in range(H)}
rand |= {mit.pixelColor(x, H - 1).name() for x in range(W)}
print("ERGEBNIS", c.devicePixelRatioF(), W, H, innen, "#000000" in rand)
"""


class HintergrundGebrochenerDprTest(unittest.TestCase):
    """DPR 1,5 und ungerade Breite: 603 x 1,5 = 904,5 — round() ergab 904
    Geraetepixel, das Widget hat 905 -> letzte Spalte/Zeile blieb schwarz."""

    def test_dpr_1_5_ungerade_breite(self):
        import subprocess
        import sys
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR="1.5",
                   QT_ENABLE_HIGHDPI_SCALING="1")
        env.pop("QT_SCREEN_SCALE_FACTORS", None)
        out = subprocess.run([sys.executable, "-c", _DPR_SKRIPT], cwd=repo, env=env,
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        zeile = [z for z in out.stdout.splitlines() if z.startswith("ERGEBNIS")]
        self.assertTrue(zeile, out.stdout[-2000:] + out.stderr[-2000:])
        _, dpr, w, h, innen, schwarz = zeile[0].split()
        self.assertEqual(float(dpr), 1.5, "Skalierung kam im Subprozess nicht an")
        self.assertEqual((int(w), int(h)), (905, 605))
        self.assertEqual(schwarz, "False", "schwarzer Rand: Cache-Bild zu schmal")
        # Innen pixelgleich zum direkten Zeichnen (die letzte Geraetepixel-
        # Spalte/Zeile deckt die Welt dort nur halb — direkt also halb geblendet,
        # aus dem Cache deckend in Hintergrundfarbe).
        self.assertEqual(int(innen), 0)
