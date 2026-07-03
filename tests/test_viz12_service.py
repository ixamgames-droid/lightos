"""Tests fuer VIZ-12 Schritt 1: VisualizerService-Kern (page-frei).

Wie ``test_visualizer_state_leaks.py``: reine Datenlogik ueber Fake-State
(``SimpleNamespace``) + Emit-Stub-Targets, KEIN echtes QWebEngine, KEIN
``state._scene`` (dict-only-Invariante). Der Timer wird ueber echte
``QTimer``-Instanzen geprueft (billig, braucht keine QApplication-Event-Loop
fuer isActive()/start()/stop()).
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.visualizer.visualizer_service import (
    VisualizerService, VisualizerTarget, get_visualizer_service,
)

# QTimer.start()/isActive() brauchen eine QCoreApplication-Instanz (sonst bleibt
# isActive() immer False, egal ob start() gerufen wurde) — wie in
# test_viz10_stability.py: einmal pro Testprozess erzeugen.
_app = QApplication.instance() or QApplication([])


def _universe(values: dict[int, int]):
    class _U:
        def get_channel(self, addr):
            return values.get(addr, 0)
    return _U()


def _channel(attr, number):
    return SimpleNamespace(attribute=attr, channel_number=number)


def _fixture(fid, universe, address, channels):
    return SimpleNamespace(fid=fid, universe=universe, address=address,
                            _channels=channels)


def _make_state(fixtures, universes, positions=None):
    positions = {} if positions is None else positions
    state = SimpleNamespace(
        universes=universes,
        visualizer_positions=positions,
        visualizer_docks={},
        visualizer_rotations={},
        live_view_positions={},
        get_patched_fixtures=lambda: fixtures,
        _callbacks=[],
    )
    state.subscribe = lambda cb: state._callbacks.append(cb)

    def _unsub(cb):
        try:
            state._callbacks.remove(cb)
        except ValueError:
            pass
    state.unsubscribe = _unsub
    return state


def _patch_get_channels_for_patched(monkeypatch_target, fixture_channels_map):
    """Monkeypatcht ``get_channels_for_patched`` im app_state-Modul (so wie es
    der Service importiert) fuer die Dauer eines Tests."""
    import src.core.app_state as app_state_mod
    original = app_state_mod.get_channels_for_patched

    def _fake(fixture):
        return fixture_channels_map[fixture.fid]
    app_state_mod.get_channels_for_patched = _fake
    return original, app_state_mod


class _ServiceTestCase(unittest.TestCase):
    def setUp(self):
        self._patched = []

    def tearDown(self):
        for mod, orig in self._patched:
            mod.get_channels_for_patched = orig

    def _install_channels(self, fixture_channels_map):
        orig, mod = _patch_get_channels_for_patched(None, fixture_channels_map)
        self._patched.append((mod, orig))

    def _make_target(self):
        sink: list = []
        target = VisualizerTarget("t", lambda json_str: sink.append(json_str))
        return target, sink


class DirtyDiffTest(_ServiceTestCase):
    def test_static_scene_no_emit_after_initial_full_push(self):
        fx = _fixture(1, universe=0, address=1, channels=None)
        universes = {0: _universe({1: 200, 2: 150, 3: 100, 4: 0, 5: 255,
                                    6: 128, 7: 128})}
        self._install_channels({1: [
            _channel("color_r", 1), _channel("color_g", 2),
            _channel("color_b", 3), _channel("color_w", 4),
            _channel("intensity", 5), _channel("pan", 6), _channel("tilt", 7),
        ]})
        state = _make_state([fx], universes, positions={1: (0, 0, 0)})
        svc = VisualizerService(state)
        target, sink = self._make_target()
        svc.attach_target(target)
        svc.set_target_active(target, True)

        svc._tick()  # erster Tick nach attach: voller Push (needs_full)
        self.assertEqual(len(sink), 1)
        first_batch = sink[0]

        svc._tick()  # unveraenderte Szene -> kein weiterer Push
        self.assertEqual(len(sink), 1, "statische Szene darf kein zweites Batch erzeugen")
        self.assertEqual(sink[0], first_batch)

    def test_only_changed_fixture_in_batch(self):
        fx1 = _fixture(1, universe=0, address=1, channels=None)
        fx2 = _fixture(2, universe=0, address=10, channels=None)
        chans = [
            _channel("color_r", 1), _channel("color_g", 2),
            _channel("color_b", 3), _channel("color_w", 4),
            _channel("intensity", 5), _channel("pan", 6), _channel("tilt", 7),
        ]
        self._install_channels({1: chans, 2: chans})
        values = {1: 10, 2: 10, 3: 10, 4: 0, 5: 255, 6: 128, 7: 128,
                  10: 50, 11: 50, 12: 50, 13: 0, 14: 255, 15: 128, 16: 128}
        universes = {0: _universe(values)}
        state = _make_state([fx1, fx2], universes,
                             positions={1: (0, 0, 0), 2: (1, 0, 0)})
        svc = VisualizerService(state)
        target, sink = self._make_target()
        svc.attach_target(target)
        svc.set_target_active(target, True)
        svc._tick()  # initial full
        sink.clear()

        # fid 1 aendert seine Farbe, fid 2 bleibt gleich.
        values[1] = 99
        svc._tick()
        self.assertEqual(len(sink), 1, "genau ein Batch-Emit fuer den geaenderten Tick")
        import json
        arr = json.loads(sink[0])
        self.assertEqual(len(arr), 1, "nur das geaenderte Fixture im Array")
        self.assertEqual(arr[0]["fid"], 1)
        self.assertEqual(arr[0]["r"], 99)


class BatchPayloadReferenceTest(_ServiceTestCase):
    """Vergleicht den Service-Payload Feld-fuer-Feld mit der alten
    ``VisualizerBridge.push_dmx_update``-Logik (Referenzvergleich)."""

    def test_payload_matches_legacy_push_dmx_update(self):
        from src.ui.visualizer.visualizer_window import VisualizerBridge
        from src.ui.visualizer.visualizer_service import _build_fixture_payload
        import json as _json

        legacy_sink: list = []

        class _LegacySelf(SimpleNamespace):
            pass

        legacy_self = _LegacySelf(dmxUpdated=SimpleNamespace(
            emit=lambda s: legacy_sink.append(_json.loads(s))))

        attrs = {
            "color_r": 200, "color_g": 150, "color_b": 100, "color_w": 10,
            "intensity": 255, "pan": 130, "tilt": 90,
        }
        VisualizerBridge.push_dmx_update(legacy_self, 42, attrs)
        legacy_payload = legacy_sink[0]

        fixture = _fixture(42, universe=0, address=1, channels=None)
        new_payload = _build_fixture_payload(fixture, attrs)

        self.assertEqual(new_payload, legacy_payload)

    def test_payload_matches_legacy_for_spider_heads(self):
        from src.ui.visualizer.visualizer_window import VisualizerBridge
        from src.ui.visualizer.visualizer_service import _build_fixture_payload
        import json as _json

        legacy_sink: list = []
        legacy_self = SimpleNamespace(dmxUpdated=SimpleNamespace(
            emit=lambda s: legacy_sink.append(_json.loads(s))))

        attrs = {
            "color_r": 200, "color_g": 0, "color_b": 0, "color_w": 0,
            "color_r#1": 0, "color_g#1": 0, "color_b#1": 255, "color_w#1": 0,
            "intensity": 255, "pan": 60, "tilt": 90, "tilt#1": 120,
        }
        VisualizerBridge.push_dmx_update(legacy_self, 7, attrs)
        legacy_payload = legacy_sink[0]

        fixture = _fixture(7, universe=0, address=1, channels=None)
        new_payload = _build_fixture_payload(fixture, attrs)

        self.assertEqual(new_payload, legacy_payload)
        self.assertIn("heads", new_payload)
        self.assertEqual(len(new_payload["heads"]), 2)


class ForceFullResyncTest(_ServiceTestCase):
    def test_force_full_resync_pushes_everything_next_tick(self):
        fx = _fixture(1, universe=0, address=1, channels=None)
        chans = [
            _channel("color_r", 1), _channel("color_g", 2),
            _channel("color_b", 3), _channel("color_w", 4),
            _channel("intensity", 5), _channel("pan", 6), _channel("tilt", 7),
        ]
        self._install_channels({1: chans})
        universes = {0: _universe({1: 10, 2: 10, 3: 10, 4: 0, 5: 255,
                                    6: 128, 7: 128})}
        state = _make_state([fx], universes, positions={1: (0, 0, 0)})
        svc = VisualizerService(state)
        target, sink = self._make_target()
        svc.attach_target(target)
        svc.set_target_active(target, True)
        svc._tick()
        sink.clear()

        svc._tick()  # unveraendert -> kein Push
        self.assertEqual(len(sink), 0)

        svc.force_full_resync()
        svc._tick()
        self.assertEqual(len(sink), 1, "nach force_full_resync muss der naechste Tick pushen")
        import json
        arr = json.loads(sink[0])
        self.assertEqual(len(arr), 1)
        self.assertEqual(arr[0]["fid"], 1)


class TimerGatingTest(_ServiceTestCase):
    def test_timer_starts_only_with_active_target(self):
        state = _make_state([], {})
        svc = VisualizerService(state)
        target = VisualizerTarget("t", lambda s: None)

        svc.attach_target(target)
        self.assertFalse(svc.timer_running, "attach allein (inaktiv) darf Timer nicht starten")

        svc.set_target_active(target, True)
        self.assertTrue(svc.timer_running)

        svc.set_target_active(target, False)
        self.assertFalse(svc.timer_running, "0 aktive Targets -> Timer haelt hart an")

    def test_timer_stops_on_detach_of_last_active_target(self):
        state = _make_state([], {})
        svc = VisualizerService(state)
        target = VisualizerTarget("t", lambda s: None)
        svc.attach_target(target)
        svc.set_target_active(target, True)
        self.assertTrue(svc.timer_running)

        svc.detach_target(target)
        self.assertFalse(svc.timer_running)

    def test_two_targets_one_active_keeps_timer_running(self):
        state = _make_state([], {})
        svc = VisualizerService(state)
        t1 = VisualizerTarget("t1", lambda s: None)
        t2 = VisualizerTarget("t2", lambda s: None)
        svc.attach_target(t1)
        svc.attach_target(t2)
        svc.set_target_active(t1, True)
        self.assertTrue(svc.timer_running)
        svc.set_target_active(t2, False)
        self.assertTrue(svc.timer_running, "t1 ist noch aktiv")
        svc.set_target_active(t1, False)
        self.assertFalse(svc.timer_running)


class MultiTargetActiveOnlyTest(_ServiceTestCase):
    def test_only_active_targets_receive_batch(self):
        fx = _fixture(1, universe=0, address=1, channels=None)
        chans = [
            _channel("color_r", 1), _channel("color_g", 2),
            _channel("color_b", 3), _channel("color_w", 4),
            _channel("intensity", 5), _channel("pan", 6), _channel("tilt", 7),
        ]
        self._install_channels({1: chans})
        universes = {0: _universe({1: 10, 2: 10, 3: 10, 4: 0, 5: 255,
                                    6: 128, 7: 128})}
        state = _make_state([fx], universes, positions={1: (0, 0, 0)})
        svc = VisualizerService(state)
        active_target, active_sink = self._make_target()
        inactive_target, inactive_sink = self._make_target()
        svc.attach_target(active_target)
        svc.attach_target(inactive_target)
        svc.set_target_active(active_target, True)
        # inactive_target bleibt inaktiv (nie set_target_active(True))

        svc._tick()
        self.assertEqual(len(active_sink), 1)
        self.assertEqual(len(inactive_sink), 0, "inaktives Target bekommt keinen Push")


class SpiderHeadsInBatchTest(_ServiceTestCase):
    def test_spider_heads_survive_batch_roundtrip(self):
        fx = _fixture(9, universe=0, address=1, channels=None)
        chans = [
            _channel("color_r", 1), _channel("color_g", 2),
            _channel("color_b", 3), _channel("color_w", 4),
            _channel("color_r", 5), _channel("color_g", 6),  # 2. Vorkommen -> #1
            _channel("color_b", 7), _channel("color_w", 8),
            _channel("intensity", 9), _channel("pan", 10),
            _channel("tilt", 11), _channel("tilt", 12),  # 2. Vorkommen -> tilt#1
        ]
        self._install_channels({9: chans})
        universes = {0: _universe({
            1: 255, 2: 0, 3: 0, 4: 0,      # Bar0 rot
            5: 0, 6: 0, 7: 255, 8: 0,      # Bar1 blau
            9: 255, 10: 60, 11: 90, 12: 120,
        })}
        state = _make_state([fx], universes, positions={9: (0, 0, 0)})
        svc = VisualizerService(state)
        target, sink = self._make_target()
        svc.attach_target(target)
        svc.set_target_active(target, True)

        svc._tick()
        self.assertEqual(len(sink), 1)
        import json
        arr = json.loads(sink[0])
        self.assertEqual(len(arr), 1)
        payload = arr[0]
        self.assertIn("heads", payload)
        self.assertEqual(len(payload["heads"]), 2)
        self.assertEqual(payload["heads"][0]["b"], 0)
        self.assertEqual(payload["heads"][1]["b"], 255)


class NeedsFullOnAttachTest(_ServiceTestCase):
    def test_freshly_attached_target_gets_full_snapshot_on_static_scene(self):
        """Design-Risiko: ein frisch geoeffnetes Target darf bei bereits
        statischer (unveraenderter) Szene nicht leer bleiben."""
        fx = _fixture(1, universe=0, address=1, channels=None)
        chans = [
            _channel("color_r", 1), _channel("color_g", 2),
            _channel("color_b", 3), _channel("color_w", 4),
            _channel("intensity", 5), _channel("pan", 6), _channel("tilt", 7),
        ]
        self._install_channels({1: chans})
        universes = {0: _universe({1: 10, 2: 10, 3: 10, 4: 0, 5: 255,
                                    6: 128, 7: 128})}
        state = _make_state([fx], universes, positions={1: (0, 0, 0)})
        svc = VisualizerService(state)

        first_target, first_sink = self._make_target()
        svc.attach_target(first_target)
        svc.set_target_active(first_target, True)
        svc._tick()
        self.assertEqual(len(first_sink), 1)

        # Szene bleibt danach unveraendert -> zweiter Tick ohne neues Target: still.
        svc._tick()
        self.assertEqual(len(first_sink), 1)

        # Jetzt dockt ein zweites Target an (Szene weiterhin unveraendert).
        second_target, second_sink = self._make_target()
        svc.attach_target(second_target)
        svc.set_target_active(second_target, True)
        svc._tick()
        self.assertEqual(len(second_sink), 1,
                          "frisch angedocktes Target muss trotz statischer Szene den vollen Bestand bekommen")
        import json
        arr = json.loads(second_sink[0])
        self.assertEqual(len(arr), 1)
        self.assertEqual(arr[0]["fid"], 1)


class SingletonTest(_ServiceTestCase):
    def test_get_visualizer_service_is_lazy_singleton_per_state(self):
        state_a = SimpleNamespace()
        state_b = SimpleNamespace()
        svc_a1 = get_visualizer_service(state_a)
        svc_a2 = get_visualizer_service(state_a)
        svc_b = get_visualizer_service(state_b)
        self.assertIs(svc_a1, svc_a2)
        self.assertIsNot(svc_a1, svc_b)


class PatchChangedPruneTest(_ServiceTestCase):
    def test_on_state_prunes_stale_fid_from_all_dicts(self):
        state = _make_state(
            [SimpleNamespace(fid=2)],  # fid 1 ist stale
            {},
            positions={1: (0, 0, 0), 2: (1, 1, 1)},
        )
        state.visualizer_docks = {1: "t1", 2: "t2"}
        state.visualizer_rotations = {1: 90.0, 2: 45.0}
        state.live_view_positions = {1: (10, 10), 2: (20, 20)}
        svc = VisualizerService(state)
        svc._last_payload = {1: {"fid": 1}, 2: {"fid": 2}}

        svc._on_state("patch_changed", None)

        self.assertNotIn(1, state.visualizer_positions)
        self.assertNotIn(1, state.visualizer_docks)
        self.assertNotIn(1, state.visualizer_rotations)
        self.assertNotIn(1, state.live_view_positions)
        self.assertNotIn(1, svc._last_payload)
        self.assertIn(2, state.visualizer_positions)
        self.assertIn(2, svc._last_payload)


class WindowAsServiceTargetTest(_ServiceTestCase):
    """VIZ-12 Schritt 3: ``VisualizerWindow`` dockt als EIN Service-Target an,
    statt einen eigenen Timer + eigenes DMX-Push-State-Subscribe zu bauen.
    Getestet per Fake-Self (wie ``WindowReleaseStateTest`` in
    ``test_visualizer_leak.py``) — kein echtes QWebEngine-Fenster noetig, nur
    die reine Andock-/Abdock-Buchhaltung."""

    def setUp(self):
        super().setUp()
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])

    def _fake_window(self, state):
        from types import SimpleNamespace as _NS
        from src.ui.visualizer.visualizer_window import VisualizerBridge, VisualizerWindow

        bridge = VisualizerBridge(state)
        fake = _NS(
            _state=state,
            _bridge=bridge,
            _on_state=lambda event, data: None,
            _view=None,
        )
        # Schritt 5: on_reset_interaction/on_reload sind echte gebundene
        # Methoden von VisualizerWindow (nicht neu nachgebaut), damit der
        # Test dieselbe Implementierung wie die Produktion durchlaeuft.
        fake._reset_own_interaction_state = lambda: VisualizerWindow._reset_own_interaction_state(fake)
        fake._reload_own_page = lambda: VisualizerWindow._reload_own_page(fake)
        return fake, bridge

    def test_attach_window_target_yields_single_service_subscriber(self):
        from src.ui.visualizer.visualizer_window import VisualizerWindow

        state = _make_state([], {})
        fake, bridge = self._fake_window(state)
        try:
            VisualizerWindow._setup_service_target(fake)
            svc = get_visualizer_service(state)
            self.assertEqual(len(state._callbacks), 3,
                              "Bridge-_on_state + Service-Subscriber (Prune) + Fenster-_on_state (UI-Refresh)")
            self.assertIn(fake._target, svc._targets)
            self.assertFalse(fake._target.active, "Target startet inaktiv (erst showEvent aktiviert)")
        finally:
            VisualizerWindow._release_state(fake)
            bridge.dispose()

    def test_show_hide_toggles_target_active_without_detach(self):
        """showEvent/hideEvent rufen am Ende ``super().showEvent/hideEvent`` —
        das braucht ein ECHTES QMainWindow-Objekt vom Typ ``VisualizerWindow``
        (wie ``_MinimalVisualizerWindow`` in ``test_viz10_stability.py``:
        ueberspringt das schwere ``__init__`` mit QWebEngineView/Toolbars)."""
        from src.ui.visualizer.visualizer_window import VisualizerWindow
        from PySide6.QtWidgets import QMainWindow
        from PySide6.QtGui import QShowEvent, QHideEvent

        class _MinimalWindow(VisualizerWindow):
            def __init__(self):
                QMainWindow.__init__(self)

        state = _make_state([], {})
        win = _MinimalWindow()
        win._state = state
        win._bridge = SimpleNamespace(dmxBatch=SimpleNamespace(emit=lambda s: None))
        try:
            VisualizerWindow._setup_service_target(win)
            svc = win._service

            VisualizerWindow.showEvent(win, QShowEvent())
            self.assertTrue(win._target.active)
            self.assertTrue(svc.timer_running)
            self.assertIn(win._target, svc._targets, "hideEvent darf NICHT detachen")

            VisualizerWindow.hideEvent(win, QHideEvent())
            self.assertFalse(win._target.active)
            self.assertFalse(svc.timer_running, "kein aktives Target mehr -> Timer stoppt hart")
            self.assertIn(win._target, svc._targets, "Target bleibt angedockt (nur inaktiv)")
        finally:
            svc = getattr(win, "_service", None)
            target = getattr(win, "_target", None)
            if svc is not None and target is not None:
                svc.detach_target(target)
            state.unsubscribe(win._on_state)

    def test_close_event_hides_and_keeps_target_attached(self):
        """VIZ-12 Schritt 4 (Dauerfenster): confirmed closeEvent versteckt nur
        (hide() -> hideEvent -> Target inaktiv), detacht aber NICHT. Fenster
        bleibt ohne Neubau wiederoeffenbar."""
        from src.ui.visualizer.visualizer_window import VisualizerWindow
        from PySide6.QtWidgets import QMainWindow
        from PySide6.QtGui import QCloseEvent

        class _MinimalWindow(VisualizerWindow):
            def __init__(self):
                QMainWindow.__init__(self)

        state = _make_state([], {})
        win = _MinimalWindow()
        win._state = state
        win._bridge = SimpleNamespace(dmxBatch=SimpleNamespace(emit=lambda s: None))
        win._confirm_close_with_unsaved_stage = lambda: True
        try:
            VisualizerWindow._setup_service_target(win)
            svc = win._service
            # Echtes show() (nicht nur ein synthetisches QShowEvent) noetig,
            # damit Qt beim spaeteren hide() auch wirklich ein echtes
            # hideEvent feuert (sonst: kein sichtbarer->unsichtbar-Uebergang).
            win.show()
            self.assertTrue(win._target.active)

            event = QCloseEvent()
            VisualizerWindow.closeEvent(win, event)

            self.assertFalse(event.isAccepted(), "hide() statt destruktivem close()")
            self.assertFalse(win.isVisible(), "Fenster ist versteckt")
            self.assertFalse(win._target.active, "hideEvent lief -> Target inaktiv")
            self.assertIn(win._target, svc._targets, "KEIN detach beim Schliessen (Dauerfenster)")
            self.assertIn(win._on_state, state._callbacks, "KEIN Unsubscribe beim Schliessen")
        finally:
            svc = getattr(win, "_service", None)
            target = getattr(win, "_target", None)
            if svc is not None and target is not None:
                svc.detach_target(target)
            state.unsubscribe(win._on_state)

    def test_release_state_detaches_target_from_service(self):
        from src.ui.visualizer.visualizer_window import VisualizerWindow

        state = _make_state([], {})
        fake, bridge = self._fake_window(state)
        VisualizerWindow._setup_service_target(fake)
        svc = fake._service
        target = fake._target

        VisualizerWindow._release_state(fake)

        self.assertNotIn(target, svc._targets, "_release_state muss das Fenster-Target abdocken")
        self.assertNotIn(fake._on_state, state._callbacks)
        bridge.dispose()

    def test_repeated_open_close_does_not_accumulate_service_subscriber(self):
        """Kern-Regression analog test_visualizer_leak: mehrfaches
        Setup/Release darf keinen Service-Subscriber akkumulieren. Der EINE
        Service-Subscriber selbst bleibt nach dem ersten attach dauerhaft
        bestehen (Orchestrator-Entscheidung: nur ``service.shutdown()`` meldet
        ihn ab, nicht ``detach_target`` — Hintergrund-Updates fuer andere
        Targets sollen moeglich bleiben) -> Baseline hier ist "Service-
        Subscriber + 0 Fenster-Subscriber", nicht die urspruengliche Baseline."""
        from src.ui.visualizer.visualizer_window import VisualizerWindow

        state = _make_state([], {})
        baseline = len(state._callbacks)
        service_baseline = None
        for _ in range(5):
            fake, bridge = self._fake_window(state)
            VisualizerWindow._setup_service_target(fake)
            self.assertEqual(len(state._callbacks), baseline + 3)
            VisualizerWindow._release_state(fake)
            bridge.dispose()
            if service_baseline is None:
                service_baseline = len(state._callbacks)
            self.assertEqual(len(state._callbacks), service_baseline,
                              "nach dem ersten Zyklus nur noch der eine Service-Subscriber uebrig")


class ShutdownUnsubscribesTest(_ServiceTestCase):
    def test_shutdown_unsubscribes_the_one_service_subscriber(self):
        state = _make_state([], {})
        svc = VisualizerService(state)
        target = VisualizerTarget("t", lambda s: None)
        svc.attach_target(target)  # subscribes
        self.assertEqual(len(state._callbacks), 1)

        svc.shutdown()
        self.assertEqual(len(state._callbacks), 0)
        self.assertFalse(svc.timer_running)

    def test_attach_detach_multiple_times_single_subscriber(self):
        state = _make_state([], {})
        svc = VisualizerService(state)
        t1 = VisualizerTarget("t1", lambda s: None)
        t2 = VisualizerTarget("t2", lambda s: None)
        svc.attach_target(t1)
        svc.attach_target(t2)
        svc.detach_target(t1)
        svc.attach_target(t1)
        self.assertEqual(len(state._callbacks), 1, "genau ein Service-Subscriber, egal wie viele Targets")


class ResetInteractionStateTest(_ServiceTestCase):
    """VIZ-12 Schritt 5: ``reset_interaction_state()`` ruft den optionalen
    ``on_reset_interaction``-Callback jedes Targets auf, kennt aber die
    konkrete Bridge/den Reload-Token-Mechanismus selbst nicht (Invariante 2 —
    Pro-Target-Zustand bleibt im Target)."""

    def test_calls_on_reset_interaction_for_every_target(self):
        state = _make_state([], {})
        svc = VisualizerService(state)
        calls: list[str] = []
        t1 = VisualizerTarget("t1", lambda s: None,
                               on_reset_interaction=lambda: calls.append("t1"))
        t2 = VisualizerTarget("t2", lambda s: None,
                               on_reset_interaction=lambda: calls.append("t2"))
        svc.attach_target(t1)
        svc.attach_target(t2)

        svc.reset_interaction_state()

        self.assertEqual(sorted(calls), ["t1", "t2"])

    def test_target_without_callback_is_skipped_silently(self):
        state = _make_state([], {})
        svc = VisualizerService(state)
        target = VisualizerTarget("t", lambda s: None)  # kein on_reset_interaction
        svc.attach_target(target)

        svc.reset_interaction_state()  # darf nicht werfen

    def test_one_target_error_does_not_block_others(self):
        state = _make_state([], {})
        svc = VisualizerService(state)
        calls: list[str] = []

        def _boom():
            raise RuntimeError("kaputt")

        t1 = VisualizerTarget("t1", lambda s: None, on_reset_interaction=_boom)
        t2 = VisualizerTarget("t2", lambda s: None,
                               on_reset_interaction=lambda: calls.append("t2"))
        svc.attach_target(t1)
        svc.attach_target(t2)

        svc.reset_interaction_state()

        self.assertEqual(calls, ["t2"], "t2 muss trotz t1-Fehler aufgerufen werden")

    def test_window_reset_interaction_stops_trace_and_clears_reload_guard(self):
        """Reale Fenster-Implementierung (kein Fake-Callback): stop_trace()
        + Reload-Guard-Reset ueber die echte Bridge."""
        from src.ui.visualizer.visualizer_window import VisualizerBridge, VisualizerWindow

        state = _make_state([], {})
        bridge = VisualizerBridge(state)
        bridge._trace_state = {"seqs": {1: [(1, 2)]}, "i": 0, "n": 1}
        bridge._reloading_stage = True
        fake_window = SimpleNamespace(_bridge=bridge)
        try:
            VisualizerWindow._reset_own_interaction_state(fake_window)
            self.assertIsNone(bridge._trace_state, "stop_trace muss die Live-Trace beenden")
            self.assertFalse(bridge._reloading_stage, "Reload-Guard muss zurueckgesetzt werden")
        finally:
            bridge.dispose()


class ReloadAllTargetsTest(_ServiceTestCase):
    """VIZ-12 Schritt 5: ``reload_all_targets()`` stoesst pro Target den
    ``on_reload``-Callback an und leert danach den Dirty-Cache -> naechster
    Tick pusht wieder ALLES (Design (b) Punkt 3 + (d) force_full_resync)."""

    def test_reload_clears_dirty_cache_so_next_tick_pushes_full(self):
        fx = _fixture(1, universe=0, address=1, channels=None)
        chans = [
            _channel("color_r", 1), _channel("color_g", 2),
            _channel("color_b", 3), _channel("color_w", 4),
            _channel("intensity", 5), _channel("pan", 6), _channel("tilt", 7),
        ]
        self._install_channels({1: chans})
        universes = {0: _universe({1: 10, 2: 10, 3: 10, 4: 0, 5: 255,
                                    6: 128, 7: 128})}
        state = _make_state([fx], universes, positions={1: (0, 0, 0)})
        svc = VisualizerService(state)
        reload_calls: list[str] = []
        target = VisualizerTarget("t", lambda s: None,
                                   on_reload=lambda: reload_calls.append("reload"))
        sink: list = []
        target.emit_batch = lambda s: sink.append(s)
        svc.attach_target(target)
        svc.set_target_active(target, True)
        svc._tick()  # initial full
        sink.clear()

        svc._tick()  # unveraendert -> still
        self.assertEqual(len(sink), 0)

        svc.reload_all_targets()
        self.assertEqual(reload_calls, ["reload"], "on_reload muss pro Target aufgerufen werden")

        svc._tick()
        self.assertEqual(len(sink), 1, "nach reload_all_targets muss der naechste Tick wieder voll pushen")
        import json
        arr = json.loads(sink[0])
        self.assertEqual(len(arr), 1)
        self.assertEqual(arr[0]["fid"], 1)

    def test_reload_single_target_only_resyncs_that_target(self):
        state = _make_state([], {})
        svc = VisualizerService(state)
        reload_calls: list[str] = []
        t1 = VisualizerTarget("t1", lambda s: None,
                               on_reload=lambda: reload_calls.append("t1"))
        t2 = VisualizerTarget("t2", lambda s: None,
                               on_reload=lambda: reload_calls.append("t2"))
        svc.attach_target(t1)
        svc.attach_target(t2)
        t1.needs_full = False
        t2.needs_full = False

        svc.reload_all_targets(target=t1)

        self.assertEqual(reload_calls, ["t1"], "nur t1s on_reload wird aufgerufen")
        self.assertTrue(t1.needs_full, "t1 braucht nach seinem Reload den vollen Bestand")
        self.assertFalse(t2.needs_full, "t2 ist von einem gezielten Reload unberuehrt")

    def test_reload_target_without_callback_still_resyncs(self):
        state = _make_state([], {})
        svc = VisualizerService(state)
        target = VisualizerTarget("t", lambda s: None)  # kein on_reload
        svc.attach_target(target)
        target.needs_full = False

        svc.reload_all_targets()  # darf nicht werfen

        self.assertTrue(target.needs_full)

    def test_window_reload_own_page_calls_load_stage_html(self):
        """Reale Fenster-Implementierung: ``_reload_own_page`` ruft
        ``load_stage_html`` auf der eigenen View (kein Fake-Callback)."""
        import src.ui.visualizer.visualizer_window as VW

        calls: list = []
        original = VW.load_stage_html
        VW.load_stage_html = lambda view: calls.append(view)
        try:
            fake_view = object()
            fake_window = SimpleNamespace(_view=fake_view)
            VW.VisualizerWindow._reload_own_page(fake_window)
            self.assertEqual(calls, [fake_view])
        finally:
            VW.load_stage_html = original


if __name__ == "__main__":
    unittest.main()
