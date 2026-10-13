"""VIZ-105 — Rueckgaengig nach dem Loeschen einer Traverse haengt die Geraete wieder an.

**Der Fehler (Bedientest QA-96, 11.10.2026):** eine Traverse mit angedockten
Geraeten loeschen, Strg+Z. Die Traverse kam zurueck, die Geraete hingen nicht
mehr daran: sie blieben auf ihrer Hoehe stehen und zogen beim naechsten
Verschieben der Traverse nicht mehr mit.

**Ursache:** ``SceneGraph.remove`` haengt die Kinder eines geloeschten Knotens
an die Wurzel (richtig, sie sollen nicht mit verschwinden). Der
RemoveNode-Command merkte sich aber nur das Element, nicht WER daran hing —
sein Undo legte die Traverse wieder an und liess die Andockungen weg.

**Zweiter Weg:** das Loeschen aus dem 3D-Bild (Entf-Taste, Loeschen-Knopf dort)
lief ueber ``_on_stage_object_deleted_from_js`` und legte gar keinen
Undo-Schritt an. Strg+Z nahm danach die Aktion DAVOR zurueck.

Geprueft wird am echten ``AppState`` (die Adapter-Views aus
``scene_adapters.py`` muessen wirklich greifen) und an den ungebundenen
Fenster-Methoden auf einem leichten Stellvertreter — das volle Fenster zoege
die Web-Ansicht hoch, um die es hier nicht geht.
"""
import os
import types
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.show.show_file import reset_show
from src.core.stage import scene_commands as scmd
from src.core.stage.stage_definition import StageDefinition
from src.core.undo import get_undo_stack


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _fenster(state, stage, *, ausgewaehlt=None):
    """Stellvertreter, auf dem die ECHTEN Fenster-Methoden laufen. Der
    Szenengraph wird ueber die echten Sync-Methoden nachgezogen — genau dort
    gingen die Andockungen verloren."""
    from src.ui.visualizer.visualizer_window import VisualizerWindow as W
    w = types.SimpleNamespace()
    w._state = state
    w._current_stage = stage
    w._bridge = MagicMock()
    # Kein Reload im Gang, nichts in der Warteschlange.
    w._bridge._reloading_stage = False
    w._bridge._poll_events = []
    w._pending_stage_ids = None
    w._selected_stage_id = ""
    w._stage_dirty = False
    w._refresh_stage_tree = lambda: None
    w._update_status_counts = lambda: None
    w._selected_stage_element = lambda: ausgewaehlt
    for name in ("_sync_stage_node_to_scene", "_remove_stage_node_from_scene"):
        setattr(w, name, types.MethodType(getattr(W, name), w))
    w.loeschen_knopf = lambda: W._delete_selected_stage_element(w)
    w.loeschen_aus_3d = lambda sid: W._on_stage_object_deleted_from_js(w, sid)
    return w


class _Basis(unittest.TestCase):
    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()
        self.undo = get_undo_stack()
        self.undo.clear()
        self.stage = StageDefinition(name="T")
        self.truss = self.stage.add("truss_h", x=0.0, y=6.0, z=0.0,
                                    w=8.0, h=0.3, d=0.3, name="Traverse")
        self.boden = self.stage.add("platform", x=0.0, y=0.2, z=3.0,
                                    w=6.0, h=0.4, d=4.0, name="Podest")

    def tearDown(self):
        self.undo.clear()
        reset_show()

    def _bestuecken(self, fenster):
        """Zwei Geraete an der Traverse, eins auf dem Podest, eins frei."""
        for el in (self.truss, self.boden):
            fenster._sync_stage_node_to_scene(el)
        for fid, x in ((1, -2.0), (2, 2.0)):
            self.state.visualizer_positions[fid] = (x, 5.75, 0.0)
            self.state.visualizer_docks[fid] = self.truss.id
        self.state.visualizer_positions[3] = (0.0, 0.7, 3.0)
        self.state.visualizer_docks[3] = self.boden.id
        self.state.visualizer_positions[4] = (5.0, 0.6, 5.0)


class LoeschenUeberDenKnopfTests(_Basis):
    def test_undo_haengt_die_geraete_wieder_an(self):
        """★ Der gemeldete Fall."""
        w = _fenster(self.state, self.stage, ausgewaehlt=self.truss)
        self._bestuecken(w)
        vorher = dict(self.state.visualizer_positions)

        w.loeschen_knopf()
        self.assertIsNone(self.stage.get(self.truss.id))
        self.assertEqual(dict(self.state.visualizer_docks), {3: self.boden.id},
                         "ohne Traverse haengt dort nichts mehr")

        self.assertTrue(self.undo.undo())
        self.assertIsNotNone(self.stage.get(self.truss.id))
        self.assertEqual(
            dict(self.state.visualizer_docks),
            {1: self.truss.id, 2: self.truss.id, 3: self.boden.id})
        self.assertEqual(dict(self.state.visualizer_positions), vorher,
                         "die Geraete duerfen dabei nicht springen")

    def test_geraete_ziehen_nach_dem_undo_wieder_mit(self):
        """Woran man den Fehler am Rig merkte: Traverse verschieben, die
        Geraete bleiben stehen. Im Graphen ist das die Eltern-Kette."""
        w = _fenster(self.state, self.stage, ausgewaehlt=self.truss)
        self._bestuecken(w)
        w.loeschen_knopf()
        self.undo.undo()

        self.truss.x = 3.0
        w._sync_stage_node_to_scene(self.truss)
        pos = self.state.visualizer_positions
        self.assertAlmostEqual(pos[1][0], 1.0)
        self.assertAlmostEqual(pos[2][0], 5.0)
        self.assertAlmostEqual(pos[4][0], 5.0, msg="freies Geraet bleibt stehen")

    def test_undo_meldet_die_andockung_an_das_3d_bild(self):
        """Der AppState allein reicht nicht: das 3D-Bild fuehrt ``dockedTo``
        selbst und erfaehrt es nur ueber die Transform-Nachricht."""
        w = _fenster(self.state, self.stage, ausgewaehlt=self.truss)
        self._bestuecken(w)
        w.loeschen_knopf()
        w._bridge.push_apply_fixture_transform.reset_mock()

        self.undo.undo()
        gemeldet = {c.args[0]: c.kwargs.get("dock")
                    for c in w._bridge.push_apply_fixture_transform.call_args_list}
        self.assertEqual(gemeldet, {1: self.truss.id, 2: self.truss.id})

    def test_redo_loest_sie_wieder_und_ein_zweites_undo_haengt_sie_wieder_an(self):
        w = _fenster(self.state, self.stage, ausgewaehlt=self.truss)
        self._bestuecken(w)
        w.loeschen_knopf()
        self.undo.undo()

        self.assertTrue(self.undo.redo())
        self.assertIsNone(self.stage.get(self.truss.id))
        self.assertEqual(dict(self.state.visualizer_docks), {3: self.boden.id})

        self.assertTrue(self.undo.undo())
        self.assertEqual(
            dict(self.state.visualizer_docks),
            {1: self.truss.id, 2: self.truss.id, 3: self.boden.id})

    def test_ein_loeschen_bleibt_ein_undo_schritt(self):
        w = _fenster(self.state, self.stage, ausgewaehlt=self.truss)
        self._bestuecken(w)
        w.loeschen_knopf()
        self.assertTrue(self.undo.undo())
        self.assertFalse(self.undo.can_undo(),
                         "das Wiederanhaengen ist Teil desselben Schritts")


class LoeschenAusDem3dBildTests(_Basis):
    def test_legt_einen_undo_schritt_an(self):
        """Vorher: keiner. Strg+Z nahm die Aktion DAVOR zurueck."""
        w = _fenster(self.state, self.stage)
        self._bestuecken(w)
        self.assertFalse(self.undo.can_undo())

        w.loeschen_aus_3d(self.truss.id)
        self.assertIsNone(self.stage.get(self.truss.id))
        self.assertTrue(self.undo.can_undo())
        self.assertIn("Traverse", self.undo.undo_label())

    def test_undo_holt_traverse_und_andockungen_zurueck(self):
        w = _fenster(self.state, self.stage)
        self._bestuecken(w)
        w.loeschen_aus_3d(self.truss.id)

        self.assertTrue(self.undo.undo())
        self.assertIsNotNone(self.stage.get(self.truss.id))
        self.assertEqual(
            dict(self.state.visualizer_docks),
            {1: self.truss.id, 2: self.truss.id, 3: self.boden.id})
        # Das 3D-Bild hat das Element selbst entfernt — es muss es zurueckbekommen.
        w._bridge.push_add_stage_object_data.assert_called_once_with(self.truss)

    def test_verworfenes_echo_legt_keinen_schritt_an(self):
        """Ein Loesch-Echo waehrend eines Reloads ist keine Nutzergeste."""
        w = _fenster(self.state, self.stage)
        self._bestuecken(w)
        w._bridge._reloading_stage = True
        w.loeschen_aus_3d(self.truss.id)
        self.assertIsNotNone(self.stage.get(self.truss.id))
        self.assertFalse(self.undo.can_undo())


class CommandTests(_Basis):
    """Der Command allein, ohne Fenster."""

    def _on_change(self, w):
        from src.ui.visualizer import visualizer_window as VW
        return VW._stage_loesch_on_change(w, self.truss)

    def test_inzwischen_entferntes_geraet_bleibt_weg(self):
        """Kein Phantom: ein Geraet, das es nicht mehr gibt, bekommt durch das
        Undo keinen Knoten zurueck."""
        w = _fenster(self.state, self.stage)
        self._bestuecken(w)
        scmd.push_remove_stage_element(
            self.state, self.stage, self.truss, on_change=self._on_change(w))
        self.stage.remove(self.truss.id)
        self._on_change(w)()
        self.state.visualizer_positions.pop(2, None)

        self.undo.undo()
        self.assertNotIn(2, self.state.visualizer_positions)
        self.assertEqual(
            dict(self.state.visualizer_docks),
            {1: self.truss.id, 3: self.boden.id})

    def test_inzwischen_woanders_angedocktes_geraet_bleibt_dort(self):
        w = _fenster(self.state, self.stage)
        self._bestuecken(w)
        scmd.push_remove_stage_element(
            self.state, self.stage, self.truss, on_change=self._on_change(w))
        self.stage.remove(self.truss.id)
        self._on_change(w)()
        self.state.visualizer_docks[2] = self.boden.id

        self.undo.undo()
        self.assertEqual(self.state.visualizer_docks.get(2), self.boden.id)

    def test_undo_nach_buehnenwechsel_haengt_nichts_an_ein_phantom(self):
        """Review: zwischen Loeschen und Rueckgaengig wurde die Buehne
        gewechselt. Das Undo trifft dann die ALTE Buehne — der Knoten der
        Traverse kommt nicht in den Graphen zurueck, und es gibt nichts, woran
        sich anhaengen liesse. Vorher legte die Dock-Sicht einen Platzhalter an
        und haengte die Geraete an ein Element, das es nicht gibt."""
        w = _fenster(self.state, self.stage, ausgewaehlt=self.truss)
        self._bestuecken(w)
        w.loeschen_knopf()
        w._current_stage = StageDefinition(name="Andere Bühne")   # Wechsel
        vorher = dict(self.state.visualizer_positions)

        self.undo.undo()
        self.assertIsNone(self.state._scene.get(self.truss.id),
                          "kein Platzhalter-Knoten fuer die alte Traverse")
        self.assertEqual(dict(self.state.visualizer_docks), {3: self.boden.id})
        self.assertEqual(dict(self.state.visualizer_positions), vorher)

    def test_callback_bekommt_nur_die_wirklich_angehaengten(self):
        w = _fenster(self.state, self.stage)
        self._bestuecken(w)
        gemeldet = []
        scmd.push_remove_stage_element(
            self.state, self.stage, self.truss, on_change=self._on_change(w),
            on_docks_restored=lambda fids: gemeldet.append(list(fids)))
        self.stage.remove(self.truss.id)
        self._on_change(w)()
        self.state.visualizer_positions.pop(2, None)

        self.undo.undo()
        self.assertEqual(gemeldet, [[1]])

    def test_element_ohne_geraete_ruft_den_callback_nicht(self):
        w = _fenster(self.state, self.stage)
        for el in (self.truss, self.boden):
            w._sync_stage_node_to_scene(el)
        gemeldet = []
        scmd.push_remove_stage_element(
            self.state, self.stage, self.truss, on_change=self._on_change(w),
            on_docks_restored=lambda fids: gemeldet.append(list(fids)))
        self.stage.remove(self.truss.id)
        self._on_change(w)()
        self.undo.undo()
        self.assertEqual(gemeldet, [])


if __name__ == "__main__":
    unittest.main()
