"""FM-9-Rest — die Kommandozeile hielt sich nicht an den Auswahl-Vertrag.

Sie war der letzte Schreiber, der ``state.selected_fids`` **roh als Attribut**
setzte, also an ``set_selected_fids`` vorbei. Genau die Fehlerklasse, die FM-9
beseitigen sollte („zweites Feld, das ein Schreiber vergisst"):
``set_selected_fids`` DELEGIERT an ``set_selected_cells`` und pflegt damit die
feine Kopf-Auswahl mit — eine rohe Zuweisung tut das nicht.

Gemessen an einem echten ``AppState`` mit drei Hydrabeams war nach ``1 thru 3``::

    selected_fids  = [1, 2, 3]      # richtig
    selected_cells = ['2:1']        # die ALTE Kopf-Auswahl, unveraendert
    SELECTION_CHANGED-Events = 0

Zwei Folgen, beide still: kein Konsument (Programmer, EFX, Matrix, Live-View,
Laser, Visualizer) erfaehrt von der neuen Auswahl, und eine spaetere Aktion
(Faecher, Snap, EFX, XY-Pad) blieb auf „Kopf 2 von Geraet 2" eingeschraenkt,
obwohl der Nutzer gerade drei ganze Geraete gewaehlt hatte.

``EchterAppStateTests`` faehrt genau diese Messung gegen den ECHTEN AppState —
ein Fake haette den Bug nicht zeigen koennen, weil er die Delegation gar nicht
hat.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.cmdline.parser import parse  # noqa: E402


class _MinimalState:
    """Ein State OHNE ``set_selected_fids`` — so werden Werkzeuge/Tests gegen die
    Kommandozeile gefahren. Der Fallback auf die rohe Zuweisung muss also
    bestehen bleiben, sonst verschwindet eine AttributeError im ``except``."""

    def __init__(self, fids):
        self._fids = list(fids)
        self.selected_fids = []
        self.writes = []
        self.cleared = False

    def get_patched_fixtures(self):
        return [type("F", (), {"fid": f})() for f in self._fids]

    def set_programmer_value(self, fid, attribute, value, undoable=False, head=0):
        key = attribute if not head else f"{attribute}#{int(head)}"
        self.writes.append((fid, key, value))

    def clear_programmer(self):
        self.cleared = True


class MinimalStateTests(unittest.TestCase):
    def test_ohne_vertrag_faellt_es_auf_die_rohe_zuweisung_zurueck(self):
        st = _MinimalState([1, 2, 3])
        res = parse("1 thru 3").execute(st)
        self.assertTrue(res.ok)
        self.assertEqual(st.selected_fids, [1, 2, 3])

    def test_clear_leert_die_auswahl_auch_ohne_vertrag(self):
        st = _MinimalState([1, 2])
        st.selected_fids = [1, 2]
        parse("clear").execute(st)
        self.assertTrue(st.cleared)
        self.assertEqual(st.selected_fids, [])

    def test_wert_ohne_selektion_nutzt_die_gespeicherte(self):
        st = _MinimalState([1, 2, 3])
        st.selected_fids = [2]
        res = parse("@ 50").execute(st)
        self.assertTrue(res.ok, res.message)
        self.assertEqual([f for f, _k, _v in st.writes], [2])


class EchterAppStateTests(unittest.TestCase):
    """★ Gegen den ECHTEN AppState — ein Fake haette den Bug nicht zeigen koennen,
    weil er die Delegation ``set_selected_fids`` -> ``set_selected_cells`` gar
    nicht hat."""

    def setUp(self):
        from src.core.app_state import get_state
        from src.core.database import fixture_db
        from src.core.database.models import PatchedFixture
        self.st = get_state()
        prof = next(iter(fixture_db.search_fixtures("HYDRABEAM 4000 RGBW")))
        mode = next(m for m in fixture_db.get_modes(prof.id)
                    if m.name.startswith("19-Kanal"))
        for fid in (1, 2, 3):
            self.st.add_fixture(
                PatchedFixture(fid=fid, label=f"HB{fid}",
                               fixture_profile_id=prof.id, mode_name=mode.name,
                               universe=1, address=1 + (fid - 1) * 19,
                               channel_count=19),
                undoable=False)

    def _events(self):
        from src.core.sync import SyncEvent
        seen = []
        self.st.sync.subscribe(SyncEvent.SELECTION_CHANGED,
                               lambda *a: seen.append(a))
        return seen

    def test_selektion_raeumt_die_alte_kopf_auswahl_ab(self):
        self.st.set_selected_cells(["2:1"])
        parse("1 thru 3").execute(self.st)
        self.assertEqual(self.st.get_selected_fids(), [1, 2, 3])
        self.assertEqual(
            self.st.get_selected_cells(), ["1", "2", "3"],
            "die alte Kopf-Zelle '2:1' haette sonst ueberlebt und jede spaetere "
            "Aktion still auf Kopf 2 von Geraet 2 eingeschraenkt")

    def test_selektion_feuert_selection_changed(self):
        self.st.set_selected_cells(["2:1"])
        seen = self._events()
        parse("1 thru 3").execute(self.st)
        self.assertTrue(seen, "ohne SELECTION_CHANGED merkt kein Konsument "
                              "(Programmer/EFX/Matrix/Visualizer) etwas davon")

    def test_clear_raeumt_zellen_und_meldet_es(self):
        self.st.set_selected_cells(["2:1"])
        seen = self._events()
        parse("clear").execute(self.st)
        self.assertEqual(self.st.get_selected_fids(), [])
        self.assertEqual(self.st.get_selected_cells(), [])
        self.assertTrue(seen)

    def test_wert_ohne_selektion_respektiert_die_kopf_auswahl(self):
        """`2:1` gewaehlt, dann nur `@ 50` — das muss auf Kopf 2 landen.

        ★ Bis 2026-07-31 stand hier ``["intensity#1"]`` — der Test sicherte also
        das GEGENTEIL seines eigenen Docstrings zu. Bei dieser Hydrabeam liegt
        vor den vier Kopf-Dimmern der gemeinsame ``CH1 Master dimmer``;
        ``intensity#1`` ist damit CH9 = der Dimmer von Kopf **1**. Kopf 2 ist
        ``intensity#2`` = CH12 (FM-17). Dass die Zusicherung falsch war und die
        Absicht daneben stand, ist der Grund, warum der Versatz so lange lebte.
        """
        self.st.set_selected_cells(["2:1"])
        self.st.programmer[2] = {}
        parse("@ 50").execute(self.st)
        prog = self.st.programmer.get(2, {})
        wert = int(round(50 * 255 / 100))
        self.assertEqual(prog.get("intensity#2"), wert,
                         "Kopf 2 ist das dritte intensity-Vorkommen (CH12)")
        self.assertEqual(prog.get("intensity"), wert,
                         "der geteilte Master muss mitkommen, sonst bleibt der "
                         "richtig adressierte Kopf dunkel")
        self.assertEqual(
            [prog.get("intensity#1"), prog.get("intensity#3"),
             prog.get("intensity#4")], [0, 0, 0],
            "die anderen Koepfe werden auf ihrem Ausgabewert verankert, damit "
            "der mitgezogene Master sie nicht ueber den Flush-Fallback mithochzieht")

    def test_genannte_selektion_hebt_die_kopf_einschraenkung_auf(self):
        """Wer `2 @ 50` tippt, meint das ganze Geraet — nicht den zuletzt
        gewaehlten Kopf."""
        self.st.set_selected_cells(["2:1"])
        self.st.programmer[2] = {}
        parse("2 @ 50").execute(self.st)
        self.assertEqual(sorted(self.st.programmer.get(2, {})), ["intensity"])

    def test_kopfzahl_folgt_dem_attribut(self):
        """Dasselbe Geraet, dieselbe Kopf-Auswahl: Pan hat 4 Koepfe, Farbe nur
        einen -> `color_r#1` waere ein Schluessel ohne Kanal (FM-9/A6)."""
        self.st.set_selected_cells(["2:1"])
        self.st.programmer[2] = {}
        self.assertTrue(parse("pan 128").execute(self.st).ok)
        self.assertTrue(parse("red 200").execute(self.st).ok)
        keys = sorted(self.st.programmer.get(2, {}))
        self.assertIn("pan#1", keys, "4 Pan-Kanaele -> Kopf 2 gibt es")
        self.assertIn("color_r", keys, "nur EINE Farbbank -> geraeteweit")
        self.assertNotIn("color_r#1", keys,
                         "'color_r#1' waere ein Schluessel ohne Kanal")


class VertragsWaechterTests(unittest.TestCase):
    """★ Der eigentliche Schutz gegen ein Wiederauftreten.

    Die Regel „NIE ``selected_fids`` direkt schreiben, immer ueber
    ``set_selected_fids``" stand seit FM-9 im Second Brain — und wurde von der
    Kommandozeile trotzdem gebrochen, gefunden erst per Zufall beim Lesen. Eine
    Regel ohne Waechter ist eine Bitte. Dieser Test macht daraus eine Zusage.
    """

    #: Der EINE erlaubte Ort ausserhalb von ``app_state`` — der bewusste Fallback
    #: in ``cmdline/parser._set_selection`` fuer Minimal-States ohne den Vertrag.
    ERLAUBT = {("src/core/cmdline/parser.py", "_set_selection")}

    def test_niemand_schreibt_selected_fids_roh(self):
        import ast
        import pathlib

        repo = pathlib.Path(__file__).resolve().parent.parent
        treffer = []
        for py in sorted((repo / "src").rglob("*.py")):
            rel = py.relative_to(repo).as_posix()
            if rel.endswith("core/app_state.py"):
                continue                     # die Heimat des Feldes
            try:
                baum = ast.parse(py.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for knoten in ast.walk(baum):
                if not isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for n in ast.walk(knoten):
                    if not isinstance(n, ast.Assign):
                        continue
                    for ziel in n.targets:
                        if (isinstance(ziel, ast.Attribute)
                                and ziel.attr == "selected_fids"
                                and (rel, knoten.name) not in self.ERLAUBT):
                            treffer.append(f"{rel}:{n.lineno} in {knoten.name}()")

        self.assertEqual(
            treffer, [],
            "Rohe Zuweisung an selected_fids gefunden. set_selected_fids() "
            "DELEGIERT an set_selected_cells und pflegt die Kopf-Auswahl mit; "
            "eine rohe Zuweisung laesst selected_cells veralten und feuert kein "
            "SELECTION_CHANGED — beides still. Entweder set_selected_fids() "
            "benutzen oder, mit Begruendung, in ERLAUBT aufnehmen.")


if __name__ == "__main__":
    unittest.main()
