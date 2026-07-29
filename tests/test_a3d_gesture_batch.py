"""A3D-06/09/10/27: EIN Undo-Command pro Gestik, und Undo/Redo fuehrt Ansicht,
Dock und Autosave-Signal mit.

Vorher schleifte JS am Drag-Ende ueber ``view.selectedFids`` und rief
``fixtureGestureEnd`` EINMAL PRO FIXTURE — jeder Aufruf pushte ein eigenes
Command. Ein 10-Fixture-Multi-Drag brauchte also 10x Strg+Z; bei >100 Fixtures
sprengte er zusaetzlich den ``MAX_SIZE``-Deckel des UndoStacks und loeschte
damit die komplette Undo-Historie der Sitzung.

Ebenfalls abgedeckt:
  * **A3D-10** — ``fixtureGestureEnd`` pushte ohne ``apply_push``/Dock: ein Undo
    aenderte nur den AppState und schickte nichts an JS.
  * **A3D-06** — der Spinbox-Commit emittierte GAR KEIN ``LIVE_VIEW_CHANGED``,
    per Spinbox gesetzte Positionen machten die Show also nie „dirty".
    (Der im Item geforderte ``_write_back_to_live_view`` ist NICHT der Fix:
    ``visualizer_positions`` und ``live_view_positions`` sind seit VIZ-11 zwei
    Projektionen desselben SceneGraph — nachgemessen; ein Write-Back waere ein
    No-op und wuerde die Weltposition ueber den Koordinaten-Roundtrip sogar um
    1 ULP verfaelschen.)
  * **A3D-27** — der Buehnen-Element-Drag meldete jede mitgezogene Lampe
    einzeln.
"""
import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.ui.visualizer.visualizer_window as VW
from src.core.app_state import get_state
from src.core.show.show_file import reset_show
from src.core.stage import scene_commands as scmd
from src.core.sync import get_sync, SyncEvent
from src.core.undo import get_undo_stack


def _app():
    return QApplication.instance() or QApplication([])


def _item(fid, x, y=6.0, z=0.0, dock=None, rot=None):
    d = {"fid": fid, "x": x, "y": y, "z": z,
         "hasRotation": rot is not None,
         "hasDockChange": dock is not None,
         "dock": dock or ""}
    if rot is not None:
        d["rx"], d["ry"], d["rz"] = rot
    return d


class GestureBatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        reset_show()
        self.state = get_state()
        self.undo = get_undo_stack()
        self.undo.clear()
        # Echte Bridge (Adapter-Views greifen real); dispose() ist Pflicht,
        # sonst leakt ein State-Subscriber in die Folgetests.
        self.bridge = VW.VisualizerBridge(self.state)

    def tearDown(self):
        self.bridge.dispose()
        self.undo.clear()

    # ── A3D-09: EIN Command fuer die ganze Gestik ───────────────────────────

    def test_batch_of_ten_is_one_undo_command(self):
        for fid in range(1, 11):
            self.state.visualizer_positions[fid] = (0.0, 6.0, 0.0)
        self.undo.clear()

        self.bridge.fixturesTransformBatch(json.dumps({
            "label": "Fixture bearbeiten",
            "items": [_item(fid, x=float(fid)) for fid in range(1, 11)],
        }))

        self.assertEqual(len(self.undo._undo), 1,
                         "eine Gestik = ein Undo-Schritt, nicht einer pro Fixture")
        for fid in range(1, 11):
            self.assertAlmostEqual(self.state.visualizer_positions[fid][0], float(fid))

        self.assertTrue(self.undo.undo())
        for fid in range(1, 11):
            self.assertAlmostEqual(self.state.visualizer_positions[fid][0], 0.0,
                                   msg="ein Undo stellt ALLE Fixtures der Gestik her")
        self.assertFalse(self.undo.can_undo())

    def test_three_gestures_are_three_steps(self):
        for fid in (1, 2, 3):
            self.state.visualizer_positions[fid] = (0.0, 6.0, 0.0)
        self.undo.clear()
        for run in range(3):
            self.bridge.fixturesTransformBatch(json.dumps({
                "items": [_item(fid, x=float(run + 1)) for fid in (1, 2, 3)]}))
        self.assertEqual(len(self.undo._undo), 3)

    def test_undo_history_survives_a_huge_multi_drag(self):
        """UndoStack.MAX_SIZE = 100 mit hartem Abschneiden: ein Multi-Drag ueber
        >100 Fixtures pushte vorher >100 Commands und loeschte damit die
        komplette Undo-Historie der Sitzung."""
        for i in range(50):
            self.undo.push_simple(f"platzhalter {i}", lambda: None, lambda: None)
        before = len(self.undo._undo)

        for fid in range(1, 151):
            self.state.visualizer_positions[fid] = (0.0, 6.0, 0.0)
        self.bridge.fixturesTransformBatch(json.dumps({
            "items": [_item(fid, x=float(fid)) for fid in range(1, 151)]}))

        self.assertEqual(len(self.undo._undo), before + 1,
                         "150 Fixtures = EIN Schritt, die Historie bleibt stehen")

    # ── A3D-10: Undo/Redo fuehrt Ansicht + Dock mit ─────────────────────────

    def _transform_events(self):
        return [ev for ev in self.bridge._poll_events if ev.get("t") == "transform"]

    def test_undo_pushes_transforms_back_to_js(self):
        """Nicht ``applyFixtureTransform.emit`` mocken: Signale erreichen die
        Post-Load-Seite nicht: der Poll ist der echte Zustellweg."""
        for fid in (1, 2):
            self.state.visualizer_positions[fid] = (0.0, 6.0, 0.0)
        self.bridge.fixturesTransformBatch(json.dumps({
            "items": [_item(fid, x=5.0) for fid in (1, 2)]}))
        self.bridge._poll_events.clear()

        self.undo.undo()

        evs = self._transform_events()
        self.assertEqual(len(evs), 2, "Undo muss beide Fixtures an JS pushen")
        xs = {json.loads(ev["j"])["x"] for ev in evs}
        self.assertEqual(xs, {0.0}, "und zwar mit den ALTEN Koordinaten")

    def test_transform_payload_carries_the_dock(self):
        self.state.visualizer_positions[1] = (0.0, 6.0, 0.0)
        self.state.visualizer_docks[1] = "truss-alt"
        self.bridge.fixturesTransformBatch(json.dumps({
            "items": [_item(1, x=5.0, dock="")]}))     # Drag loest das Dock
        self.assertIsNone(self.state.visualizer_docks.get(1))
        self.bridge._poll_events.clear()

        self.undo.undo()

        evs = self._transform_events()
        self.assertTrue(evs, "Undo pusht einen Transform")
        self.assertEqual(json.loads(evs[0]["j"]).get("dock"), "truss-alt",
                         "das Undo stellt die Andockung auch in JS wieder her")
        self.assertEqual(self.state.visualizer_docks.get(1), "truss-alt")

    def test_old_payloads_without_dock_do_not_undock(self):
        """``dock`` ist optional — ein Aufrufer, der es nicht mitschickt, darf
        keine bestehende Andockung loeschen (deshalb ein Sentinel statt ``None``,
        denn ``None`` heisst gueltig 'kein Dock')."""
        self.bridge.push_apply_fixture_transform(1, 1.0, 2.0, 3.0)
        ev = self._transform_events()[-1]
        self.assertNotIn("dock", json.loads(ev["j"]))

    # ── A3D-06: genau EIN Dirty-Signal je Anwendung ─────────────────────────

    def _count_live_view_events(self, fn):
        seen = []
        cb = lambda *a: seen.append(1)
        get_sync().subscribe(SyncEvent.LIVE_VIEW_CHANGED, cb)
        try:
            fn()
        finally:
            try:
                get_sync().unsubscribe(SyncEvent.LIVE_VIEW_CHANGED, cb)
            except Exception:
                pass
        return len(seen)

    def test_one_live_view_signal_per_gesture_not_per_fixture(self):
        for fid in range(1, 11):
            self.state.visualizer_positions[fid] = (0.0, 6.0, 0.0)
        n = self._count_live_view_events(lambda: self.bridge.fixturesTransformBatch(
            json.dumps({"items": [_item(fid, x=float(fid)) for fid in range(1, 11)]})))
        self.assertEqual(n, 1, "ein Emit je Gestik, nicht zehn")

    def test_undo_and_redo_each_emit_the_dirty_signal(self):
        self.state.visualizer_positions[1] = (0.0, 6.0, 0.0)
        self.bridge.fixturesTransformBatch(json.dumps({"items": [_item(1, x=5.0)]}))
        self.assertEqual(self._count_live_view_events(self.undo.undo), 1)
        self.assertEqual(self._count_live_view_events(self.undo.redo), 1)

    # ── No-op-Schutz ────────────────────────────────────────────────────────

    def test_unchanged_fixtures_in_a_batch_keep_their_dock(self):
        """Anti-Clobber: in einer gemischten Gestik darf ein unveraendertes
        Fixture nicht mit-entdockt werden."""
        self.state.visualizer_positions[1] = (0.0, 6.0, 0.0)
        self.state.visualizer_positions[2] = (0.0, 6.0, 0.0)
        self.state.visualizer_docks[2] = "truss-b"
        self.undo.clear()

        self.bridge.fixturesTransformBatch(json.dumps({"items": [
            _item(1, x=5.0),                       # bewegt
            _item(2, x=0.0),                       # unveraendert, kein Dock-Wechsel
        ]}))

        self.assertEqual(self.state.visualizer_docks.get(2), "truss-b")
        self.undo.undo()
        self.assertEqual(self.state.visualizer_docks.get(2), "truss-b")

    def test_entry_without_dock_change_never_touches_the_dock(self):
        """Review-Fund: der Traversen-Pfad (A3D-27) meldet immer
        ``hasDockChange: false``. Wuerde der Command die Andockung trotzdem
        erzwingen, koennte ein Undo eine zwischenzeitlich anders gesetzte
        Andockung still zurueckdrehen — vorher fasste dieser Pfad ueber
        ``push_transform_fixtures`` ausschliesslich Positionen an."""
        self.state.visualizer_positions[1] = (0.0, 6.0, 0.0)
        self.undo.clear()
        self.bridge.fixturesTransformBatch(json.dumps({
            "items": [_item(1, x=5.0)]}))          # hasDockChange = False

        # Zwischendurch wird das Dock auf anderem Weg gesetzt (z.B. place_fixture_at).
        self.state.visualizer_docks[1] = "truss-neu"

        self.undo.undo()
        self.assertEqual(self.state.visualizer_docks.get(1), "truss-neu",
                         "ein Eintrag ohne Dock-Wechsel darf die Andockung nicht anfassen")

    def test_broken_entry_leaves_no_half_applied_state(self):
        """Review-Fund: erst die ganze Payload parsen, dann schreiben. Sonst
        haette ein defekter Eintrag die vorherigen Fixtures im State stehen
        lassen — ohne Undo-Command, ohne Meldung (der Slot-Guard schluckt).

        **A3D-41 hat die Erwartung praezisiert.** Die Garantie war und bleibt:
        kein nicht-ruecknehmbarer Teilzustand — was ankommt, kommt in EINEM
        Undo-Command an. Was NICHT mehr gilt, ist „ein defekter Eintrag
        verwirft die ganze Gestik": das kostete den Nutzer beim Multi-Drag alle
        mitgezogenen Lampen und hinterliess trotzdem eine Divergenz (JS hatte
        ja schon bewegt). Jetzt wird der defekte Eintrag einzeln verworfen und
        die uebrigen bilden weiterhin genau einen Undo-Schritt.
        """
        self.state.visualizer_positions[1] = (0.0, 6.0, 0.0)
        self.state.visualizer_positions[2] = (0.0, 6.0, 0.0)
        self.undo.clear()

        # zweiter Eintrag defekt: x = None (JSON.stringify macht das aus NaN)
        bad = _item(2, x=9.0)
        bad["x"] = None
        self.bridge.fixturesTransformBatch(json.dumps({
            "items": [_item(1, x=5.0), bad]}))

        self.assertAlmostEqual(self.state.visualizer_positions[1][0], 5.0,
                               msg="der gueltige Eintrag darf nicht mit "
                                   "verworfen werden")
        self.assertEqual(self.state.visualizer_positions[2], (0.0, 6.0, 0.0),
                         "der defekte Eintrag bleibt unangetastet")
        self.assertEqual(len(self.undo._undo), 1,
                         "die uebernommenen Eintraege sind EIN Undo-Schritt")
        self.assertTrue(self.undo.undo())
        self.assertEqual(self.state.visualizer_positions[1], (0.0, 6.0, 0.0))

    def test_no_broken_entry_ever_reaches_the_state(self):
        """A3D-41: keine der Spielarten eines kaputten Wertes darf durch.

        ``None`` ist der Fall aus dem Crash-Log (``JSON.stringify`` macht aus
        NaN ein ``null``), ``float('nan')``/``inf`` der Fall, wenn ein
        Nicht-JSON-Transport die Werte roh durchreicht, und der String der
        Fall eines fehlgeleiteten Payload-Feldes. Alle vier muessen den State
        unberuehrt lassen, statt ihn mit einem unbrauchbaren Wert zu
        vergiften — ein NaN in ``visualizer_positions`` ueberlebt sonst bis in
        die Show-Datei und macht das Geraet dauerhaft unsichtbar.
        """
        for bad_value in (None, float("nan"), float("inf"), "abc"):
            with self.subTest(bad=repr(bad_value)):
                self.state.visualizer_positions[7] = (1.0, 6.0, 2.0)
                self.undo.clear()
                bad = _item(7, x=9.0)
                bad["x"] = bad_value
                # allow_nan=True ist der Default und genau der Transportweg,
                # ueber den ein rohes NaN hier ankommen wuerde.
                self.bridge.fixturesTransformBatch(json.dumps({"items": [bad]}))

                self.assertEqual(self.state.visualizer_positions[7],
                                 (1.0, 6.0, 2.0))
                self.assertFalse(self.undo.can_undo(),
                                 "nichts uebernommen = kein Undo-Schritt")

    def test_dropped_entry_is_pushed_back_to_js(self):
        """A3D-41: Der verworfene Eintrag steht in JS auf NaN und ist DORT
        unsichtbar (three.js rastert eine NaN-Position nicht), waehrend Python
        die letzte gueltige Position kennt. Ihn nur zu ignorieren liesse ein
        unsichtbares Geraet in der Szene zurueck — Python schickt deshalb den
        autoritativen Stand zurueck."""
        self.state.visualizer_positions[3] = (2.0, 6.0, -1.0)
        self.bridge._poll_events.clear()

        bad = _item(3, x=9.0)
        bad["x"] = None
        self.bridge.fixturesTransformBatch(json.dumps({"items": [bad]}))

        evs = [json.loads(ev["j"]) for ev in self._transform_events()]
        healed = [p for p in evs if int(p.get("fid", -1)) == 3]
        self.assertTrue(healed, "Heil-Push fuer genau dieses Fixture fehlt")
        self.assertAlmostEqual(healed[-1]["x"], 2.0,
                               msg="und zwar mit der letzten GUELTIGEN Position")
        self.assertAlmostEqual(healed[-1]["z"], -1.0)

    def test_invalid_rotation_keeps_the_valid_position(self):
        """A3D-41: Nur die Drehung ist unbrauchbar — Verschieben und Andocken
        sind trotzdem echte Nutzerarbeit und werden uebernommen."""
        self.state.visualizer_positions[4] = (0.0, 6.0, 0.0)
        self.state.visualizer_rotations[4] = (0.0, 45.0, 0.0)
        self.undo.clear()

        bad = _item(4, x=7.0, rot=(0.0, 90.0, 0.0))
        bad["ry"] = None
        self.bridge.fixturesTransformBatch(json.dumps({"items": [bad]}))

        self.assertAlmostEqual(self.state.visualizer_positions[4][0], 7.0,
                               msg="die gueltige Position muss ankommen")
        self.assertEqual(self.state.visualizer_rotations[4], (0.0, 45.0, 0.0),
                         "die unbrauchbare Drehung darf nichts ueberschreiben")

    def test_empty_batch_pushes_nothing(self):
        self.undo.clear()
        self.bridge.fixturesTransformBatch(json.dumps({"items": []}))
        self.assertFalse(self.undo.can_undo())

    # ── Rueckwaertskompatibilitaet ──────────────────────────────────────────

    def test_singular_slot_still_works_and_equals_a_one_item_batch(self):
        self.state.visualizer_positions[1] = (0.0, 6.0, 0.0)
        self.undo.clear()
        self.bridge.fixtureGestureEnd(json.dumps(_item(1, x=5.0)))
        self.assertEqual(len(self.undo._undo), 1)
        self.assertAlmostEqual(self.state.visualizer_positions[1][0], 5.0)
        self.undo.undo()
        self.assertAlmostEqual(self.state.visualizer_positions[1][0], 0.0)

    def test_plural_command_helper_is_ui_free(self):
        """``scene_commands`` darf nichts ueber die UI wissen (Design-Invariante):
        der Plural-Command muss auch gegen einen nackten Fake-State laufen."""
        from types import SimpleNamespace
        st = SimpleNamespace(visualizer_positions={}, visualizer_rotations={},
                             visualizer_docks={})
        self.undo.clear()
        scmd.push_transform_and_dock_fixtures(st, [{
            "fid": 1, "old_pos": (0, 0, 0), "new_pos": (1, 0, 0),
            "old_rot": (0, 0, 0), "new_rot": (0, 0, 0),
            "old_dock": None, "new_dock": None}])
        self.undo.undo()
        self.undo.redo()
        self.assertEqual(st.visualizer_positions[1], (1, 0, 0))


if __name__ == "__main__":
    unittest.main()
