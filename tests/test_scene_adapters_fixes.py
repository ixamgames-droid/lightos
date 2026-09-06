"""VIZ-11 Review-Runde: gezielte Regressionstests fuer die 4 Adapter-/Graph-
Funde aus der adversarialen Review (siehe docs/VIZ11_SCENEGRAPH_DESIGN.md):

  1. O(n^2)-Resync bei Ganz-Dict-Zuweisung (Bulk-Perf-Smoke).
  2. Phantom-Fixture bei Rotation-only (Facetten-Flag pos_set).
  3. state._scene-Ersetzung desynct lebende Views (AppState.set_scene()).
  4. Geister-Platzhalter-Nodes (_DockView-Platzhalter werden aufgeraeumt).
"""
import contextlib
import os
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

    def test_rotationen_buendeln_ebenso(self):
        """★ Dieselbe Zusicherung fuer die ROTATIONEN — vorher eine rohe
        Wanduhr-Schranke (`elapsed < 0.05`). Gemessen: gebuendelt 1 Aufruf,
        ausgehebelt n (1 gegen 200 und 1 gegen 500)."""
        for n in (200, 500):
            with self.subTest(fixtures=n):
                self.assertEqual(self._zaehle_rotationen(n), 1)
                self.assertGreaterEqual(
                    self._zaehle_rotationen(n, aushebeln=True), n,
                    "ohne Buendelung muesste je Eintrag abgeglichen werden")

    def _zaehle_rotationen(self, n, *, aushebeln=False):
        """Wie ``_zaehle``, aber fuer die Rotations-Zuweisung.

        Positionen zuerst (Legacy-Reihenfolge) — sie sind Vorbedingung und
        werden ausserhalb der Zaehlung gesetzt."""
        registry = self.state._view_registry
        self.state.visualizer_positions = {
            fid: (0.0, 6.0, 0.0) for fid in range(n)}
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
                self.state.visualizer_rotations = {
                    fid: (0.0, float(fid % 360), 0.0) for fid in range(n)}
        finally:
            try:
                registry._views.discard(v)
            except AttributeError:
                registry._views.remove(v)
        return v.aufrufe

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

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()

    def tearDown(self):
        reset_show()

    # ★★★ QA-71c: HIER STAND DIE ZEIT-MESSUNG, und auch sie ist weg.
    #
    # Nicht weil die Frage falsch waere — „skaliert die Ganz-Zuweisung linear?"
    # ist genau richtig —, sondern weil eine WANDUHR sie auf einem geteilten
    # Laeufer nicht beantworten kann. Gemessen unter kuenstlicher Last
    # (6 Rechenprozesse), drei Laeufe je Fall:
    #
    #     gesund  13,6 / 9,0 / 7,4      (ohne Last: ~5,0)
    #     kaputt  23,3 / 15,3 / 26,9    (ohne Last: ~24,5)
    #
    # Innerhalb EINES Laufs trennen sie sauber. Ueber Laeufe hinweg
    # UEBERLAPPEN die Bereiche: in der CI vom 06.09. erreichte der gesunde Fall
    # ueber 18, der kaputte fiel auf 15,7. Eine Schranke, die lastfest ist,
    # waere damit zu locker, um den Rueckfall noch zu fangen — die Messung kann
    # nicht beides.
    #
    # ★ Die Frage ist ZAEHLBAR und wird von `ResyncZaehlungTest` beantwortet:
    # eine Ganz-Zuweisung loest gebuendelt GENAU EIN `view._resync()` aus,
    # unabhaengig von der Groesse; ausgehebelt sind es n+1 (gemessen 1 gegen 201
    # und 1 gegen 1001). Das ist dieselbe Aussage, nur ohne Uhr — und mit
    # eigener Gegenprobe.
    #
    # ⚠️ Was dabei VERLOREN geht, ehrlich benannt: die Zaehlung faenge einen
    # Rueckfall NICHT, bei dem die Zahl der Resyncs gleich bleibt, ein
    # einzelner Resync aber selbst quadratisch wird. Dafuer braeuchte es eine
    # Messung auf ruhiger Hardware — im Gate eines geteilten Laeufers ist sie
    # nicht zu haben. Steht als Vermerk hier, statt als flackernder Test.

    # ★★★ QA-71c: HIER STAND EINE ZEIT-GEGENPROBE, und sie ist ersatzlos weg.
    #
    # Sie forderte ein Verhaeltnis UEBER `SCHWELLE`, waehrend der Test oben
    # DARUNTER bleiben muss — dieselbe Konstante, entgegengesetzte Richtungen.
    # Damit war jede Anpassung ein Nullsummenspiel: QA-71b hat die Schwelle von
    # 12,0 auf 18,0 angehoben, um dem Test oben Luft zu geben, und hat der
    # Gegenprobe damit genau so viel weggenommen. Sie fiel prompt in der
    # naechsten CI bei 15,7.
    #
    # Gemessen unter Last liegen die beiden Faelle zu dicht beieinander, als
    # dass IRGENDEIN Wert fuer beide sicher waere:
    #
    #     gesund  5,0 -> 11,5   (naehert sich der Schwelle von unten)
    #     kaputt 24,5 -> 15,7   (naehert sich ihr von oben)
    #
    # ★ Die Zusicherung, die sie tragen sollte, traegt seit QA-71b
    # `ResyncZaehlungTest` — OHNE Uhr, mit eigener Gegenprobe
    # (`test_ohne_buendelung_waeren_es_n_plus_eins`, gemessen 1 gegen n+1).
    # Eine zweite, flackernde Gegenprobe fuegt dem nichts hinzu; sie erzieht nur
    # dazu, Rot wegzuwinken.
    #
    # Was hier BLEIBT, ist der Test oben — als grober Rauchmelder fuer die
    # Laufzeit, nicht als Traeger einer Zusicherung.

    def test_bulk_assignment_resyncs_existing_views_exactly_once(self):
        """Eine VOR der Ganz-Zuweisung gehaltene View-Referenz muss NACH der
        Zuweisung den vollen neuen Inhalt sehen (Bulk-Pfad darf den finalen
        Resync nicht versehentlich unterdruecken)."""
        view = self.state.visualizer_positions
        self.assertEqual(len(view), 0)
        self.state.visualizer_positions = {1: (1.0, 2.0, 3.0), 2: (4.0, 5.0, 6.0)}
        self.assertEqual(dict(view), {1: (1.0, 2.0, 3.0), 2: (4.0, 5.0, 6.0)})

    # ★★ QA-71c: Hier stand `test_bulk_rotation_assignment_is_fast` mit einer
    # ROHEN Wanduhr-Schranke (`assertLess(elapsed, 0.05)`) — die reinste Form
    # derselben Krankheit wie oben, nur ohne das Verhaeltnis dazwischen. Auf
    # einem geteilten Laeufer ist das ein Wuerfelwurf.
    #
    # Auch DIESE Eigenschaft ist zaehlbar, und die Messung ist genauso deutlich:
    # eine Rotations-Ganz-Zuweisung loest gebuendelt GENAU EIN `view._resync()`
    # aus, ausgehebelt n. Gemessen 1 gegen 200 und 1 gegen 500.
    # Uebernommen von `ResyncZaehlungTest.test_rotationen_buendeln_ebenso`.


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
