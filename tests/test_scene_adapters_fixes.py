"""VIZ-11 Review-Runde: gezielte Regressionstests fuer die 4 Adapter-/Graph-
Funde aus der adversarialen Review (siehe docs/VIZ11_SCENEGRAPH_DESIGN.md):

  1. O(n^2)-Resync bei Ganz-Dict-Zuweisung (Bulk-Perf-Smoke).
  2. Phantom-Fixture bei Rotation-only (Facetten-Flag pos_set).
  3. state._scene-Ersetzung desynct lebende Views (AppState.set_scene()).
  4. Geister-Platzhalter-Nodes (_DockView-Platzhalter werden aufgeraeumt).
"""
import contextlib
import os
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.show.show_file import load_show, reset_show, save_show
from src.core.stage.scene_graph import NodeKind, SceneGraph, SceneNode
from src.core.stage.stage_definition import StageDefinition


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class ResyncZaehlungTest(unittest.TestCase):
    """★★★ QA-71b: dieselbe Zusicherung wie die Perf-Messung — ohne Uhr.

    Die Buendelung ist eine ZAEHLBARE Eigenschaft, keine Geschwindigkeit: eine
    Ganz-Zuweisung darf genau EIN ``view._resync()`` ausloesen, unabhaengig von
    der Groesse. Gemessen: 1 bei 200 Fixtures, 1 bei 1000. Ohne die Buendelung
    sind es 201 bzw. 1001.

    Damit haengt die Aussage an keiner Maschine und an keiner Last — genau die
    Lehre, die QA-71 begonnen und die CI vom 2026-09-06 zu Ende erzwungen hat:
    eine Wanduhr im Gate ist auf fremder Hardware ein Wuerfelwurf, und ein
    Verhaeltnis aus zwei Zeitmessungen ist immer noch eine Uhr.
    """

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()

    def tearDown(self):
        reset_show()

    class _Zaehler:
        """Eine View, die nur mitzaehlt, wie oft sie neu abgeglichen wird."""

        def __init__(self):
            self.aufrufe = 0

        def _resync(self):
            self.aufrufe += 1

    def _zaehle(self, n, *, aushebeln=False):
        registry = self.state._view_registry
        v = self._Zaehler()
        try:
            registry._views.add(v)
        except AttributeError:
            registry._views.append(v)
        try:
            @contextlib.contextmanager
            def ohne_wirkung(*_a, **_k):
                yield registry

            ctx = (mock.patch.object(type(registry), "suspend", ohne_wirkung)
                   if aushebeln else contextlib.nullcontext())
            with ctx:
                self.state.visualizer_positions = {
                    i: (float(i), 6.0, 0.0) for i in range(n)}
        finally:
            try:
                registry._views.discard(v)
            except AttributeError:
                registry._views.remove(v)
        return v.aufrufe

    def test_eine_ganz_zuweisung_loest_genau_EIN_resync_aus(self):
        """Und zwar unabhaengig von der Groesse — das IST die Aussage."""
        for n in (200, 1000):
            with self.subTest(fixtures=n):
                self.assertEqual(self._zaehle(n), 1)

    def test_ohne_buendelung_waeren_es_n_plus_eins(self):
        """★★ Die Gegenprobe, ebenfalls ohne Uhr: wird der ``suspend()``-Block
        ausgehebelt, laeuft wieder ein Abgleich PRO EINTRAG. Ohne diesen Test
        waere „ein Resync" auch dadurch zu erreichen, dass gar nichts mehr
        abgeglichen wird."""
        for n in (200, 1000):
            with self.subTest(fixtures=n):
                self.assertGreaterEqual(
                    self._zaehle(n, aushebeln=True), n,
                    "Der ausgehebelte suspend()-Block faellt nicht mehr auf — "
                    "dann prueft der Test oben nichts mehr")

    def test_die_zaehlung_haengt_an_keiner_zeit(self):
        """Selbstkontrolle: in dieser Klasse darf keine Uhr vorkommen — sonst
        schleicht sich die Wanduhr durch die Hintertuer zurueck.

        ★★ Zwei Vorkehrungen, und beide sind noetig, weil die erste Fassung
        dieses Tests **sich selbst gefunden** hat: die verbotenen Woerter
        standen als Zeichenketten in seiner eigenen Liste, und er meldete
        prompt vier Verstoesse gegen sich.

        1. Die Begriffe werden aus TEILEN zusammengesetzt, stehen also nirgends
           wortwoertlich im Quelltext. (Eine Ausnahmeliste waere der falsche
           Weg — sie macht den Waechter fuer echte Faelle blind.)
        2. Gesucht wird nur im CODE: Kommentare und Docstrings werden vorher
           geleert. Ein Text ueber eine Uhr ist keine Uhr.

        Beides ist dieselbe Lehre wie QA-76 und QA-74 — ein Textsucher liest
        den Text, den man ueber ihn schreibt.
        """
        import ast
        import inspect
        import tokenize
        import io as _io

        quelle = inspect.getsource(type(self))
        zeilen = quelle.splitlines(keepends=True)
        _doc = set()
        try:
            for knoten in ast.walk(ast.parse(quelle)):
                koerper = getattr(knoten, "body", None)
                if isinstance(koerper, list) and koerper:
                    erst = koerper[0]
                    if (isinstance(erst, ast.Expr)
                            and isinstance(erst.value, ast.Constant)
                            and isinstance(erst.value.value, str)):
                        _doc.add((erst.value.lineno, erst.value.col_offset))
        except (SyntaxError, IndentationError):
            _doc = set()
        try:
            for m in tokenize.generate_tokens(_io.StringIO(quelle).readline):
                if m.type == tokenize.COMMENT or (
                        m.type == tokenize.STRING and m.start in _doc):
                    for z in range(m.start[0], m.end[0] + 1):
                        if z - 1 < len(zeilen):
                            zeilen[z - 1] = " " * len(zeilen[z - 1].rstrip("\n")) + "\n"
        except (tokenize.TokenError, IndentationError, SyntaxError):
            pass
        code = "".join(zeilen)

        # Zusammengesetzt, damit dieser Test nicht sich selbst findet.
        verboten = ("perf_" + "counter", "time" + ".time",
                    "mono" + "tonic", "sle" + "ep")
        for begriff in verboten:
            with self.subTest(begriff=begriff):
                self.assertNotIn(begriff, code)


class BulkAssignmentPerfTest(unittest.TestCase):
    """Fund 1: Ganz-Dict-Zuweisung darf NICHT mehr O(n^2) sein (ein
    resync_all() pro Eintrag statt EINEM gebuendelten am Ende)."""

    #: Zwei Groessen im Verhaeltnis 1:5. Linear ergibt ~5, quadratisch ~25 —
    #: gemessen 5,1 bzw. 24,5 (siehe unten). Die Schwelle liegt bewusst
    #: dazwischen und nicht knapp an einem der beiden Werte.
    KLEIN, GROSS = 200, 1000

    #: ★★★ QA-71b: Die Zusicherung haengt NICHT mehr an dieser Zahl.
    #:
    #: QA-71 hatte die Wanduhr durch ein SKALIERUNGS-Verhaeltnis ersetzt — ein
    #: echter Fortschritt, aber immer noch eine Messung. In der CI vom
    #: 2026-09-06 wurde die Gegenprobe rot: sie fordert ein Verhaeltnis UEBER
    #: 12,0 und kam auf **11,94**. Nichts war kaputt, der Laeufer war langsam.
    #:
    #: Nachgemessen unter kuenstlicher Last (6 Rechenprozesse parallel) zeigt
    #: sich, warum kein Schwellenwert das retten kann — die beiden Faelle
    #: konvergieren von BEIDEN Seiten:
    #:
    #:               ohne Last      unter Last
    #:   gebuendelt      5,0            11,5      <- naehert sich der Schwelle
    #:   ausgehebelt    24,5            18,8      <- entfernt sich von ihr
    #:   Faktor          5,0             1,6
    #:
    #: Der gesunde Fall stand unter Last bei 11,5 — also selbst einen Hauch vor
    #: Rot. Eine Zeitmessung mit zwei Groessen ist auf einem geteilten Laeufer
    #: kein tauglicher Traeger fuer eine Zusicherung.
    #:
    #: ★ Die Eigenschaft laesst sich ZAEHLEN, und zwar exakt: gebuendelt loest
    #: eine Ganz-Zuweisung **genau EIN** ``view._resync()`` aus, unabhaengig von
    #: der Groesse; ausgehebelt sind es n+1. Gemessen 1 gegen 201 (n=200) und
    #: 1 gegen 1001 (n=1000). Das traegt die Zusicherung jetzt
    #: (``ResyncZaehlungTest``), und die Zeitmessung hier ist nur noch ein
    #: grober Rauchmelder mit weitem Abstand zum Rauschen.
    SCHWELLE = 18.0

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()

    def tearDown(self):
        reset_show()

    def _dauer(self, n, wiederholungen=3):
        """KLEINSTE gemessene Zeit fuer ``n`` Fixtures.

        Das Minimum, nicht der Mittelwert: Stoerungen durch Nachbarprozesse
        koennen eine Messung nur VERLAENGERN, nie verkuerzen. Der kleinste Wert
        ist damit der beste verfuegbare Schaetzer fuer die reine Rechenzeit —
        und genau darum geht es hier.
        """
        beste = None
        for _ in range(wiederholungen):
            reset_show()
            zustand = get_state()
            positionen = {fid: (float(fid), 6.0, 0.0) for fid in range(n)}
            start = time.perf_counter()
            zustand.visualizer_positions = positionen
            gemessen = time.perf_counter() - start
            beste = gemessen if beste is None else min(beste, gemessen)
        return beste

    def _verhaeltnis(self):
        klein = self._dauer(self.KLEIN)
        gross = self._dauer(self.GROSS)
        self.assertGreater(klein, 0.0, "Zeitmessung liefert 0 — nicht auswertbar")
        return gross / klein, klein, gross

    def test_bulk_position_assignment_skaliert_nicht_quadratisch(self):
        """★ Gemessen wird die SKALIERUNG, nicht die Uhrzeit.

        Die erste Fassung verlangte ``elapsed < 0.05`` fuer 500 Fixtures. Das
        war ein Wanduhr-Budget fuer eine Aussage ueber die Skalierung — und es
        hat am 2026-09-03 an einem Abend DREIMAL fremde PRs rot gefaerbt, die
        ``src/`` gar nicht anfassten (0,05137 s / 0,05078 s gegen 0,05 s), jedes
        Mal war der Neulauf gruen (QA-71).

        Der Grund ist keine Schlamperei bei der Zahl, sondern die Bauart: das
        Gate faehrt seine Segmente **absichtlich parallel**, und CI-Hardware ist
        geteilt. Gemessen: dieselbe Zuweisung braucht hier 1,4–1,9 ms und auf CI
        51 ms — ein Faktor 27. Ein absolutes Budget muesste entweder so gross
        sein, dass es nichts mehr faengt, oder es faellt unter Last.

        Ein VERHAELTNIS ist davon unabhaengig: ist die Maschine dreifach
        belastet, werden beide Messungen dreifach langsamer und der Quotient
        bleibt. Gemessen am 2026-09-03: linear 5,1 — quadratisch 24,5.
        """
        verhaeltnis, klein, gross = self._verhaeltnis()
        self.assertLess(
            verhaeltnis, self.SCHWELLE,
            "Die Zuweisung skaliert quadratisch statt linear: %dx so viele "
            "Fixtures kosteten %.1fx so viel Zeit (%.4fs -> %.4fs). Erwartet "
            "ist ~%.0fx (ein gebuendeltes resync_all() am Ende); ~%.0fx heisst "
            "ein resync_all() pro Eintrag."
            % (self.GROSS // self.KLEIN, verhaeltnis, klein, gross,
               self.GROSS / self.KLEIN, (self.GROSS / self.KLEIN) ** 2))
        # Funktional weiterhin korrekt (keine Perf-Optimierung auf Kosten der
        # Korrektheit).
        self.assertEqual(len(self.state.visualizer_positions), self.GROSS)
        self.assertEqual(self.state.visualizer_positions[42], (42.0, 6.0, 0.0))

    def test_ohne_gebuendeltes_resync_wuerde_der_test_anschlagen(self):
        """★★ Die Gegenprobe — ohne sie waere „nicht mehr flaky\" auch dadurch
        zu erreichen, dass der Test gar nichts mehr prueft.

        Der Rueckfall wird nicht nachgebaut, sondern am ECHTEN Codeweg
        hergestellt: die Buendelung haengt an genau einem ``suspend()``-Block im
        Setter. Wird der ausgehebelt, laeuft wieder ein ``resync_all()`` pro
        Eintrag — also exakt der Fund, gegen den dieser Test steht.

        Gemessen am 2026-09-03: Verhaeltnis 24,5 statt 5,1, und bei 1000
        Fixtures 133x mehr Zeit.

        ★ QA-71b: Diese Gegenprobe bleibt, aber sie ist nicht mehr der Beweis —
        den fuehrt ``ResyncZaehlungTest`` ohne Uhr. Hier steht nur noch, dass
        die Zeitmessung im Prinzip einen Unterschied SIEHT.
        """
        registry = self.state._view_registry

        @contextlib.contextmanager
        def ohne_wirkung():
            yield

        with mock.patch.object(registry, "suspend", ohne_wirkung):
            verhaeltnis, klein, gross = self._verhaeltnis()
        self.assertGreater(
            verhaeltnis, self.SCHWELLE,
            "Der ausgehebelte suspend()-Block faellt nicht mehr auf "
            "(Verhaeltnis %.1f, %.4fs -> %.4fs). Dann wuerde der Test oben "
            "einen echten O(n^2)-Rueckfall ebenfalls durchlassen — er prueft "
            "nichts mehr." % (verhaeltnis, klein, gross))

    def test_bulk_assignment_resyncs_existing_views_exactly_once(self):
        """Eine VOR der Ganz-Zuweisung gehaltene View-Referenz muss NACH der
        Zuweisung den vollen neuen Inhalt sehen (Bulk-Pfad darf den finalen
        Resync nicht versehentlich unterdruecken)."""
        view = self.state.visualizer_positions
        self.assertEqual(len(view), 0)
        self.state.visualizer_positions = {1: (1.0, 2.0, 3.0), 2: (4.0, 5.0, 6.0)}
        self.assertEqual(dict(view), {1: (1.0, 2.0, 3.0), 2: (4.0, 5.0, 6.0)})

    def test_bulk_rotation_assignment_is_fast(self):
        n = 500
        # Positionen zuerst (Legacy-Reihenfolge), dann Rotationen.
        self.state.visualizer_positions = {fid: (0.0, 6.0, 0.0) for fid in range(n)}
        rotations = {fid: (0.0, float(fid % 360), 0.0) for fid in range(n)}
        start = time.perf_counter()
        self.state.visualizer_rotations = rotations
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 0.05, f"Rotations-Ganz-Zuweisung von {n} Fixtures dauerte {elapsed:.3f}s")


class RotationOnlyPhantomTest(unittest.TestCase):
    """Fund 2: eine reine Rotations-Zuweisung darf KEIN Phantom-Fixture mit
    (0,0,0)-Position in visualizer_positions erzeugen."""

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()

    def tearDown(self):
        reset_show()

    def test_rotation_only_assignment_does_not_appear_in_positions(self):
        self.state.visualizer_rotations[5] = (10.0, 20.0, 30.0)
        self.assertNotIn(5, self.state.visualizer_positions)
        self.assertEqual(self.state.visualizer_rotations.get(5), (10.0, 20.0, 30.0))

    def test_rotation_only_node_not_persisted_as_position(self):
        self.state.visualizer_rotations[9] = (0.0, 45.0, 0.0)
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "rot_only.lshow")
            save_show(path)
            import json
            import zipfile
            with zipfile.ZipFile(path) as zf:
                data = json.loads(zf.read("show.json"))
            self.assertNotIn("9", data["visualizer"]["positions"])
            # scene_graph-Block: Node existiert (Rotation gespeichert), aber
            # ohne pos_set -> kein irrefuehrender (0,0,0)-Positions-Eintrag.
            node_entries = {n["id"]: n for n in data["scene_graph"]["nodes"]}
            self.assertIn("fix_9", node_entries)
            self.assertFalse(node_entries["fix_9"].get("pos_set", True))

    def test_pop_on_rotation_only_position_raises_keyerror(self):
        """Konsistenz-Check: 'fid in positions' ist False -> pop(fid) ohne
        Default muss KeyError werfen (kein stilles Verschwinden-Lassen eines
        Phantom-Node ueber positions.pop())."""
        self.state.visualizer_rotations[3] = (1.0, 2.0, 3.0)
        with self.assertRaises(KeyError):
            self.state.visualizer_positions.pop(3)

    def test_real_position_write_still_appears(self):
        """Gegenprobe: eine ECHTE Positions-Zuweisung bleibt unveraendert
        sichtbar (kein Overshoot des Fixes)."""
        self.state.visualizer_positions[11] = (1.0, 2.0, 3.0)
        self.assertIn(11, self.state.visualizer_positions)
        self.assertEqual(self.state.visualizer_positions[11], (1.0, 2.0, 3.0))

    def test_undo_style_rotation_after_node_loss_no_phantom(self):
        """Simuliert den in der Review benannten Undo-Verdacht: eine reine
        Rotations-Zuweisung NACH Verlust des urspruenglichen Node (z.B. nach
        Remove) darf keinen Phantom-Positions-Eintrag erzeugen."""
        self.state.visualizer_positions[4] = (1.0, 1.0, 1.0)
        self.state.visualizer_positions.pop(4, None)  # Node komplett weg
        self.assertNotIn(4, self.state.visualizer_positions)
        # "Undo" einer Rotation greift denselben Adapter-Pfad wie scene_commands
        # push_rotate_fixtures._apply (state.visualizer_rotations[fid] = rot).
        self.state.visualizer_rotations[4] = (5.0, 6.0, 7.0)
        self.assertNotIn(4, self.state.visualizer_positions)


class SetSceneResyncTest(unittest.TestCase):
    """Fund 3: eine VOR load_show/reset_show gehaltene View-Referenz muss
    NACH der Graph-Ersetzung wieder den aktuellen Graphen sehen (uber
    AppState.set_scene(), nicht mehr eine blosse state._scene=...-Zuweisung)."""

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()

    def tearDown(self):
        reset_show()

    def test_set_scene_updates_live_view_reference(self):
        view = self.state.visualizer_positions
        old_scene = self.state._scene
        new_scene = SceneGraph()
        new_scene.add(SceneNode(id="fix_7", kind=NodeKind.FIXTURE, fixture_id=7))
        new_scene.get("fix_7").transform.pos_m = (9.0, 9.0, 9.0)
        new_scene.get("fix_7").pos_set = True

        self.state.set_scene(new_scene)

        self.assertIsNot(self.state._scene, old_scene)
        self.assertIs(view._scene, new_scene)
        # Ein Schreibzugriff auf die ALTE View-Referenz landet jetzt im
        # AKTIVEN Graphen (nicht mehr spurlos im verwaisten alten Graphen).
        view[7] = (1.0, 2.0, 3.0)
        self.assertEqual(new_scene.world_pos("fix_7"), (1.0, 2.0, 3.0))
        self.assertEqual(self.state.visualizer_positions.get(7), (1.0, 2.0, 3.0))

    def test_load_show_resyncs_live_view_reference(self):
        """End-to-End ueber den echten load_show-Pfad (nicht nur set_scene()
        direkt): eine vor dem Laden gehaltene View muss danach den neu
        geladenen Graphen sehen."""
        self.state.visualizer_positions = {1: (1.0, 1.0, 1.0)}
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "resync.lshow")
            save_show(path)

            view = self.state.visualizer_positions
            self.assertEqual(dict(view), {1: (1.0, 1.0, 1.0)})

            # Neuen Inhalt speichern + erneut laden -> view (ALTE Referenz)
            # muss den NEUEN Inhalt zeigen, nicht den alten von der Bindung.
            self.state.visualizer_positions = {2: (2.0, 2.0, 2.0)}
            path2 = os.path.join(td, "resync2.lshow")
            save_show(path2)

            ok, msg = load_show(path2)
            self.assertTrue(ok, msg)
            self.assertEqual(dict(view), {2: (2.0, 2.0, 2.0)})

    def test_reset_show_resyncs_live_view_reference(self):
        self.state.visualizer_positions = {1: (1.0, 1.0, 1.0)}
        view = self.state.visualizer_positions
        reset_show()
        self.assertEqual(dict(view), {})
        view[3] = (3.0, 3.0, 3.0)
        self.assertEqual(self.state.visualizer_positions.get(3), (3.0, 3.0, 3.0))


class GhostPlaceholderCleanupTest(unittest.TestCase):
    """Fund 4: _DockView-Platzhalter (Dock auf unbekannte Stage-Element-ID)
    werden beim Laden UND beim Speichern aufgeraeumt, statt sich unbegrenzt
    anzusammeln."""

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()

    def tearDown(self):
        reset_show()

    def test_dock_on_unknown_id_creates_placeholder_pruned_on_save(self):
        self.state.visualizer_positions = {7: (1.0, 6.0, -2.0)}
        self.state.visualizer_docks[7] = "el_doesnotexist123"
        # Platzhalter existiert direkt nach dem Setzen (Design-Absicht:
        # reparent()/to_legacy_docks() duerfen den Eintrag nicht verwerfen).
        self.assertIsNotNone(self.state._scene.get("el_doesnotexist123"))

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "ghost.lshow")
            save_show(path)
            # Save raeumt den Platzhalter im LEBENDEN Graphen auf, WEIL das
            # Dock beim Laden ohnehin als stale verworfen wird (Element
            # existiert auf keiner aufloesbaren Buehne) -> kein Kind mehr am
            # Platzhalter haengt danach nicht zwangslaeufig sofort, aber der
            # persistierte Block darf keinen dauerhaften Geister-Node ohne
            # Referenz akkumulieren:
            import json
            import zipfile
            with zipfile.ZipFile(path) as zf:
                data = json.loads(zf.read("show.json"))
            node_ids = {n["id"] for n in data["scene_graph"]["nodes"]}
            # fid 7 ist per keep_world weiterhin (an el_doesnotexist123
            # geparented, da _resolve_stage_element_ids fuer "simple" das
            # Element nicht kennt) -- das Dock selbst wird erst beim naechsten
            # LADEN stale-gefiltert. Nach dem Laden darf der Platzhalter dann
            # nicht mehr vorhanden sein.
            ok, msg = load_show(path)
            self.assertTrue(ok, msg)
            self.assertIsNone(self.state._scene.get("el_doesnotexist123"))
            self.assertNotIn(7, self.state.visualizer_docks)

    def test_ghost_placeholder_without_children_removed_by_prune_helper(self):
        from src.core.show.show_file import _prune_ghost_placeholder_nodes

        scene = SceneGraph()
        scene.add(SceneNode(id="ghost1", kind=NodeKind.PLATFORM))
        scene.add(SceneNode(id="real_truss", kind=NodeKind.TRUSS_H, size_m=(1.0, 1.0, 1.0), name="T"))
        scene.add(SceneNode(id="fix_1", kind=NodeKind.FIXTURE, fixture_id=1, parent_id="real_truss"))

        _prune_ghost_placeholder_nodes(scene)

        self.assertIsNone(scene.get("ghost1"))
        self.assertIsNotNone(scene.get("real_truss"))
        self.assertIsNotNone(scene.get("fix_1"))

    def test_ghost_placeholder_with_live_child_is_not_removed(self):
        """Ein Platzhalter, an dem noch ein Fixture haengt (Kind), ist KEIN
        reiner Geister-Node -- das Aufraeumen darf ein noch gedocktes Fixture
        nicht kaputt reparenten."""
        from src.core.show.show_file import _prune_ghost_placeholder_nodes

        scene = SceneGraph()
        scene.add(SceneNode(id="ghost_with_child", kind=NodeKind.PLATFORM))
        scene.add(SceneNode(id="fix_2", kind=NodeKind.FIXTURE, fixture_id=2, parent_id="ghost_with_child"))

        _prune_ghost_placeholder_nodes(scene)

        self.assertIsNotNone(scene.get("ghost_with_child"))
        self.assertIsNotNone(scene.get("fix_2"))


if __name__ == "__main__":
    unittest.main()
