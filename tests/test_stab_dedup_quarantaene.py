"""STAB-DEDUP-OPT: verwaiste Patch-Zeilen finden, ohne benutzte zu erwischen.

★ **Die Asymmetrie ist die ganze Aussage.** Ein Gerät fälschlich zu verschieben
ist Datenverlust in Davids Show; ein echtes Waisen-Gerät fälschlich zu behalten
ist ein Schönheitsfehler. Der weitaus wichtigste Test ist deshalb nicht „findet
es die Waise", sondern **„legt JEDE einzelne Referenzstelle ein Veto ein"** —
eine vergessene Stelle wäre ein stiller Datenverlust.

Der Test geht die Stellen darum einzeln durch, statt eine „alles belegt"-Show
zu bauen: nur so fällt auf, wenn genau eine davon nicht mehr geprüft wird.

Weiter abgesichert:

* **Adress-Überlappung ist kein Grund.** Zwei Geräte auf derselben Adresse
  können beide gewollt sein (Ersatzgerät, Parallelbetrieb).
* **Unerreichbarer Scan-Ort bricht ab**, statt „keine Referenzen" zu melden.
  Genau so entstehen Datenverluste, die hinterher niemand zuordnen kann.
* **Verschieben ist verlustfrei umkehrbar** — auch nach einem Schema-Zuwachs.
* **Vor dem Verschieben wird erneut geprüft**: zwischen Anzeige und Bestätigung
  kann das Gerät längst wieder benutzt werden.
"""
from __future__ import annotations

import json
import os
import tempfile
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import create_engine, select                          # noqa: E402
from sqlalchemy.orm import Session                                    # noqa: E402

from src.core.database.models import (                                # noqa: E402
    Base, FixtureGroup, PatchedFixture, QuarantinedFixture,
)
from src.core.show import patch_dedup                                 # noqa: E402


class _Fx:
    def __init__(self, fid, universe=1, address=1, channel_count=4, label=""):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.channel_count = channel_count
        self.label = label or f"Gerät {fid}"


class _LeererFM:
    def all(self):
        return []

    def affected_fids(self, fid):
        return set()


class _LeereSnapBib:
    def snaps(self):
        return []


def _state(patch=None, **kw):
    """Minimaler State: alle Referenz-Orte leer, sofern nicht überschrieben."""
    st = types.SimpleNamespace()
    st._patch_cache = list(patch or [])
    st.programmer = {}
    st.base_levels = {}
    st.selected_fids = []
    st.function_manager = _LeererFM()
    st.cue_stacks = []
    st.list_fixture_groups = lambda: []
    st.visualizer_positions = {}
    st.visualizer_rotations = {}
    st.live_view_positions = {}
    st._vc_layout = {}
    st.stage_objects = []
    st._show_engine = None
    for k, v in kw.items():
        setattr(st, k, v)
    return st


class _SnapBibPatch:
    """Die Snap-Bibliothek ist ein Modul-Singleton — hier gezielt ersetzt."""

    def __init__(self, bib):
        self._bib = bib

    def __enter__(self):
        import src.core.engine.snap_library as sl
        self._orig = sl.get_snap_library
        sl.get_snap_library = lambda: self._bib
        return self

    def __exit__(self, *a):
        import src.core.engine.snap_library as sl
        sl.get_snap_library = self._orig
        return False


class ReferenzVetoTest(unittest.TestCase):
    """Jede einzelne Stelle muss die Quarantäne verhindern."""

    def setUp(self):
        self._snap = _SnapBibPatch(_LeereSnapBib())
        self._snap.__enter__()

    def tearDown(self):
        self._snap.__exit__()

    def _ohne_referenz(self):
        st = _state([_Fx(7)])
        self.assertEqual(patch_dedup.referenzen(st, 7), [],
                         "Grundfall stimmt nicht — der Rest des Tests wäre wertlos")
        return st

    def test_grundfall_ohne_referenz_ist_kandidat(self):
        st = self._ohne_referenz()
        self.assertEqual([b.fid for b in patch_dedup.finde_kandidaten(st)], [7])

    def test_programmer_verhindert(self):
        st = self._ohne_referenz()
        st.programmer = {7: {"intensity": 255}}
        self.assertIn("programmer", patch_dedup.referenzen(st, 7))

    def test_base_levels_verhindert(self):
        st = self._ohne_referenz()
        st.base_levels = {7: {"intensity": 100}}
        self.assertIn("base_levels", patch_dedup.referenzen(st, 7))

    def test_auswahl_verhindert(self):
        st = self._ohne_referenz()
        st.selected_fids = [7]
        self.assertIn("auswahl", patch_dedup.referenzen(st, 7))

    def test_funktion_verhindert(self):
        """Deckt EFX/Matrix/Scene/Chaser mit ab — die Auflösung leistet der
        FunctionManager, deshalb genügt hier sein Vertrag."""
        st = self._ohne_referenz()

        class _FM:
            def all(self):
                return [types.SimpleNamespace(id=100)]

            def affected_fids(self, fid):
                return {7} if fid == 100 else set()

        st.function_manager = _FM()
        self.assertIn("funktionen", patch_dedup.referenzen(st, 7))

    def test_cueliste_verhindert(self):
        st = self._ohne_referenz()
        cue = types.SimpleNamespace(values={7: {"intensity": 200}})
        st.cue_stacks = [types.SimpleNamespace(cues=[cue])]
        self.assertIn("cuelisten", patch_dedup.referenzen(st, 7))

    def test_geraetegruppe_verhindert(self):
        """positions_json ist ein JSON-STRING mit String-Schlüsseln — genau die
        Form, an der eine naive `fid in dict`-Prüfung scheitern würde."""
        st = self._ohne_referenz()
        # Die ECHTE Rueckgabeform von AppState.list_fixture_groups.
        # Die erste Fassung dieses Tests stellte {"positions_json": ...} — eine
        # Form, die es nie gab. Er war gruen, waehrend der Scan-Ort im Betrieb
        # nie ansprang (STAB-22).
        st.list_fixture_groups = lambda: [
            {"id": 1, "name": "G", "folder": "", "fids": [7]}]
        self.assertIn("geraetegruppen", patch_dedup.referenzen(st, 7))

    def test_snap_verhindert(self):
        st = self._ohne_referenz()

        class _Bib:
            def snaps(self):
                return [types.SimpleNamespace(values={7: {"pan": 128}})]

        with _SnapBibPatch(_Bib()):
            self.assertIn("snap-bibliothek", patch_dedup.referenzen(st, 7))

    def test_visualizer_positionen_verhindern(self):
        st = self._ohne_referenz()
        st.visualizer_positions = {7: (0.0, 1.0, 2.0)}
        self.assertIn("visualizer-positionen", patch_dedup.referenzen(st, 7))

    def test_visualizer_drehungen_verhindern(self):
        st = self._ohne_referenz()
        st.visualizer_rotations = {7: 90.0}
        self.assertIn("visualizer-drehungen", patch_dedup.referenzen(st, 7))

    def test_2d_positionen_verhindern(self):
        st = self._ohne_referenz()
        st.live_view_positions = {7: (10.0, 20.0)}
        self.assertIn("2d-positionen", patch_dedup.referenzen(st, 7))

    def test_vc_layout_verhindert_auch_tief_verschachtelt(self):
        """★ Die Über-Approximation: das VC-Layout wird NICHT gedeutet, nur
        durchsucht. Ein Taster, der ein Gerät auf eine Weise anspricht, die
        dieses Modul nicht kennt, muss trotzdem schützen."""
        st = self._ohne_referenz()
        st._vc_layout = {"seiten": [{"widgets": [
            {"typ": "irgendwas_neues", "ziele": {"geraete": ["7"]}}]}]}
        self.assertIn("virtuelle-konsole", patch_dedup.referenzen(st, 7))

    def test_buehnenobjekte_verhindern(self):
        st = self._ohne_referenz()
        st.stage_objects = [{"typ": "truss", "gedockt": [7]}]
        self.assertIn("buehnen-objekte", patch_dedup.referenzen(st, 7))

    def test_alle_dokumentierten_orte_koennen_wirklich_greifen(self):
        """Wächter gegen einen stillschweigend entfernten Scan-Ort: jeder Name
        in SCAN_ORTE muss von mindestens einem Veto-Test oben erzeugbar sein."""
        st = self._ohne_referenz()
        st.programmer = {7: {}}
        st.base_levels = {7: {}}
        st.selected_fids = [7]
        st.cue_stacks = [types.SimpleNamespace(
            cues=[types.SimpleNamespace(values={7: {}})])]
        st.list_fixture_groups = lambda: [{"id": 1, "name": "G", "folder": "", "fids": [7]}]
        st.visualizer_positions = {7: (0, 0, 0)}
        st.visualizer_rotations = {7: 0}
        st.live_view_positions = {7: (0, 0)}
        st._vc_layout = {"x": 7}
        st.stage_objects = [7]

        class _FM:
            def all(self):
                return [types.SimpleNamespace(id=1)]

            def affected_fids(self, fid):
                return {7}

        st.function_manager = _FM()

        class _Bib:
            def snaps(self):
                return [types.SimpleNamespace(values={7: {}})]

        with _SnapBibPatch(_Bib()):
            gefunden = patch_dedup.referenzen(st, 7)
        self.assertEqual(sorted(gefunden), sorted(patch_dedup.SCAN_ORTE),
                         "SCAN_ORTE und die tatsächlich geprüften Orte driften "
                         "auseinander — ein nicht mehr geprüfter Ort ist ein "
                         "stiller Datenverlust")


class UeberlappungTest(unittest.TestCase):
    def setUp(self):
        self._snap = _SnapBibPatch(_LeereSnapBib())
        self._snap.__enter__()

    def tearDown(self):
        self._snap.__exit__()

    def test_ueberlappung_allein_macht_keinen_kandidaten(self):
        """★ Zwei Geräte auf derselben Adresse können beide gewollt sein."""
        st = _state([_Fx(1, address=10), _Fx(2, address=10)],
                    programmer={1: {}, 2: {}})
        self.assertEqual(patch_dedup.finde_kandidaten(st), [])

    def test_ueberlappung_wird_aber_ausgewiesen(self):
        st = _state([_Fx(1, address=10), _Fx(2, address=12)], programmer={1: {}, 2: {}})
        nach_fid = {b.fid: b for b in patch_dedup.analysiere(st)}
        self.assertEqual(nach_fid[1].ueberlappt_mit, [2])
        self.assertEqual(nach_fid[2].ueberlappt_mit, [1])

    def test_getrennte_universen_ueberlappen_nicht(self):
        st = _state([_Fx(1, universe=1, address=10), _Fx(2, universe=2, address=10)],
                    programmer={1: {}, 2: {}})
        self.assertEqual([b.ueberlappt_mit for b in patch_dedup.analysiere(st)],
                         [[], []])


class ScanUnvollstaendigTest(unittest.TestCase):
    def test_unerreichbarer_ort_bricht_ab_statt_zu_raten(self):
        """★ Ein nicht ladbarer Snap-Speicher darf NICHT als „keine Referenzen"
        durchgehen — sonst verschiebt der Befehl benutzte Geräte."""
        st = _state([_Fx(7)])

        class _KaputteBib:
            def snaps(self):
                raise OSError("Snap-Datei nicht lesbar")

        with _SnapBibPatch(_KaputteBib()):
            with self.assertRaises(patch_dedup.ScanUnvollstaendig) as ctx:
                patch_dedup.referenzen(st, 7)
        self.assertIn("snap-bibliothek", str(ctx.exception))

    def test_kaputter_function_manager_bricht_ebenfalls_ab(self):
        st = _state([_Fx(7)])

        class _FM:
            def all(self):
                raise RuntimeError("Engine nicht bereit")

        st.function_manager = _FM()
        with _SnapBibPatch(_LeereSnapBib()):
            with self.assertRaises(patch_dedup.ScanUnvollstaendig):
                patch_dedup.referenzen(st, 7)


class QuarantaeneTest(unittest.TestCase):
    def setUp(self):
        self._snap = _SnapBibPatch(_LeereSnapBib())
        self._snap.__enter__()
        self._tmp = tempfile.TemporaryDirectory()
        pfad = os.path.join(self._tmp.name, "show.db")
        self.engine = create_engine(f"sqlite:///{pfad}")
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()
        self._tmp.cleanup()
        self._snap.__exit__()

    def _zeile_anlegen(self, fid=7):
        with Session(self.engine) as s:
            s.add(PatchedFixture(fid=fid, label="Alt-Gerät", fixture_profile_id=1,
                                 mode_name="m", universe=1, address=33,
                                 channel_count=9))
            s.commit()

    def test_verschieben_loescht_nicht_sondern_legt_ab(self):
        self._zeile_anlegen()
        st = _state([_Fx(7, address=33, channel_count=9)], _show_engine=self.engine)
        self.assertEqual(patch_dedup.in_quarantaene(st, [7], grund="test"), [7])
        with Session(self.engine) as s:
            self.assertIsNone(s.scalar(select(PatchedFixture)
                                       .where(PatchedFixture.fid == 7)))
            q = s.scalar(select(QuarantinedFixture).where(QuarantinedFixture.fid == 7))
            self.assertIsNotNone(q, "Zeile ist weg, aber nicht in der Quarantäne — "
                                    "das wäre gelöscht statt verschoben")
            self.assertEqual(q.grund, "test")
            self.assertTrue(q.verschoben_am, "kein Zeitstempel protokolliert")
            self.assertEqual(json.loads(q.daten_json)["address"], 33)

    def test_zurueckholen_ist_verlustfrei(self):
        self._zeile_anlegen()
        st = _state([_Fx(7, address=33, channel_count=9)], _show_engine=self.engine)
        patch_dedup.in_quarantaene(st, [7])
        self.assertTrue(patch_dedup.zurueckholen(st, 7))
        with Session(self.engine) as s:
            zurueck = s.scalar(select(PatchedFixture).where(PatchedFixture.fid == 7))
            self.assertIsNotNone(zurueck)
            self.assertEqual((zurueck.label, zurueck.universe, zurueck.address,
                              zurueck.channel_count, zurueck.mode_name),
                             ("Alt-Gerät", 1, 33, 9, "m"))
            self.assertIsNone(s.scalar(select(QuarantinedFixture)
                                       .where(QuarantinedFixture.fid == 7)))

    def test_zurueckholen_ueberlebt_einen_schema_zuwachs(self):
        """★ Der Grund für das JSON-Feld statt gespiegelter Spalten: bekommt die
        Quarantäne-Zeile ein Feld, das `patched_fixtures` (noch) nicht kennt,
        darf das Zurückholen nicht mit TypeError sterben."""
        self._zeile_anlegen()
        st = _state([_Fx(7)], _show_engine=self.engine)
        patch_dedup.in_quarantaene(st, [7])
        with Session(self.engine) as s:
            q = s.scalar(select(QuarantinedFixture).where(QuarantinedFixture.fid == 7))
            daten = json.loads(q.daten_json)
            daten["ein_feld_aus_der_zukunft"] = 42
            q.daten_json = json.dumps(daten)
            s.commit()
        self.assertTrue(patch_dedup.zurueckholen(st, 7))

    def test_inzwischen_wieder_benutzt_bleibt_stehen(self):
        """★ Zwischen Anzeige und Bestätigung kann der Nutzer das Gerät längst
        wieder benutzen — dann darf es sich nicht bewegen."""
        self._zeile_anlegen()
        st = _state([_Fx(7)], _show_engine=self.engine, programmer={7: {"intensity": 5}})
        self.assertEqual(patch_dedup.in_quarantaene(st, [7]), [])
        with Session(self.engine) as s:
            self.assertIsNotNone(s.scalar(select(PatchedFixture)
                                          .where(PatchedFixture.fid == 7)))

    def test_liste_zeigt_den_inhalt(self):
        self._zeile_anlegen()
        st = _state([_Fx(7, address=33)], _show_engine=self.engine)
        patch_dedup.in_quarantaene(st, [7], grund="aufräumen")
        eintraege = patch_dedup.liste_quarantaene(st)
        self.assertEqual(len(eintraege), 1)
        self.assertEqual(eintraege[0]["fid"], 7)
        self.assertEqual(eintraege[0]["grund"], "aufräumen")


class UnbeladenRiegelTest(unittest.TestCase):
    """★ Das gefährlichste Loch, im Sandbox-Lauf entdeckt.

    Der PATCH kommt aus ``current_show.db``, die Referenzen aber größtenteils
    aus der SHOW-DATEI (Funktionen, Cuelisten, VC-Layout, Snaps). Ohne geladene
    Show ist der Patch voll und jede Referenzquelle leer — also gälte JEDES
    Gerät als Waise, und ein ``--anwenden`` hätte den kompletten Patch geräumt.
    """

    def setUp(self):
        self._snap = _SnapBibPatch(_LeereSnapBib())
        self._snap.__enter__()

    def tearDown(self):
        self._snap.__exit__()

    def test_voller_patch_ohne_jede_referenzquelle_gilt_als_unbeladen(self):
        st = _state([_Fx(1), _Fx(2)])
        self.assertTrue(patch_dedup.wirkt_unbeladen(st))

    def test_leerer_patch_ist_kein_problem(self):
        self.assertFalse(patch_dedup.wirkt_unbeladen(_state([])))

    def test_eine_einzige_funktion_genuegt_als_lebenszeichen(self):
        class _FM:
            def all(self):
                return [types.SimpleNamespace(id=1)]

            def affected_fids(self, fid):
                return set()

        st = _state([_Fx(1)], function_manager=_FM())
        self.assertFalse(patch_dedup.wirkt_unbeladen(st))

    def test_eine_cue_genuegt(self):
        st = _state([_Fx(1)], cue_stacks=[types.SimpleNamespace(
            cues=[types.SimpleNamespace(values={})])])
        self.assertFalse(patch_dedup.wirkt_unbeladen(st))

    def test_ein_vc_layout_genuegt(self):
        st = _state([_Fx(1)], _vc_layout={"seiten": []})
        self.assertFalse(patch_dedup.wirkt_unbeladen(st))

    def test_ein_snap_genuegt(self):
        class _Bib:
            def snaps(self):
                return [types.SimpleNamespace(values={})]

        with _SnapBibPatch(_Bib()):
            self.assertFalse(patch_dedup.wirkt_unbeladen(_state([_Fx(1)])))

    def test_unlesbare_snapbibliothek_blockiert_ebenfalls(self):
        """Im Zweifel blockieren: eine nicht lesbare Quelle darf nicht als
        „nichts da" gelten, sonst kippt der Riegel in die falsche Richtung."""
        class _Kaputt:
            def snaps(self):
                raise OSError("nicht lesbar")

        with _SnapBibPatch(_Kaputt()):
            self.assertFalse(patch_dedup.wirkt_unbeladen(_state([_Fx(1)])))


class WerkzeugTest(unittest.TestCase):
    def test_werkzeug_veraendert_ohne_anwenden_nichts(self):
        """Der Trockenlauf ist Vorgabe — geprüft an der Quelle, weil ein echter
        Lauf eine vollständige App-Umgebung bräuchte."""
        pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "tools", "patch_quarantaene.py")
        quelle = open(pfad, encoding="utf-8").read()
        self.assertIn("if not args.anwenden:", quelle)
        vor_anwenden = quelle.split("if not args.anwenden:")[0]
        self.assertNotIn("in_quarantaene(", vor_anwenden,
                         "das Werkzeug verschiebt, bevor --anwenden geprüft ist")

    def test_werkzeug_prueft_den_unbeladen_riegel_vor_der_analyse(self):
        """Der Riegel muss VOR analysiere() greifen — danach wäre die
        Kandidatenliste schon falsch berechnet."""
        pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "tools", "patch_quarantaene.py")
        quelle = open(pfad, encoding="utf-8").read()
        self.assertIn("wirkt_unbeladen(state)", quelle)
        self.assertLess(quelle.index("wirkt_unbeladen(state)"),
                        quelle.index("patch_dedup.analysiere(state)"),
                        "der Riegel steht hinter der Analyse")


class EchterGruppenDienstTest(unittest.TestCase):
    """★ STAB-22 — der Test, den es damals gebraucht haette.

    Alle anderen Tests dieser Datei stellen ``list_fixture_groups`` als
    Attrappe. Sie waren gruen, waehrend der Scan-Ort im Betrieb **nie** ansprang:
    die Attrappe lieferte ``{"positions_json": ...}``, die echte Methode liefert
    ``{"id", "name", "folder", "fids"}``. Geprueft wurde damit die Form, die ich
    ENTWORFEN hatte — nicht die, die es gibt. Ein Geraet, das nur in einer
    Gruppe steckt, galt als Waise und war per ``--anwenden`` aus dem Patch zu
    entfernen.

    Hier laeuft deshalb die ECHTE ``AppState.list_fixture_groups`` gegen eine
    eigene Wegwerf-DB. Sie braucht nur ``_show_engine``, also genuegt eine nackte
    Instanz — kein App-Start, keine Show, und vor allem nicht Davids
    ``data/current_show.db``.
    """

    def setUp(self):
        self._snap = _SnapBibPatch(_LeereSnapBib())
        self._snap.__enter__()
        self._tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{self._tmp.name}/show.db")
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()
        self._tmp.cleanup()
        self._snap.__exit__()

    def _state_mit_gruppe(self, positions):
        from src.core.app_state import AppState
        with Session(self.engine) as s:
            s.add(PatchedFixture(fid=7, label="Nur in einer Gruppe",
                                 fixture_profile_id=1, mode_name="m",
                                 universe=1, address=100, channel_count=4))
            s.add(FixtureGroup(name="Front", cols=1, rows=1,
                               positions_json=json.dumps(positions)))
            s.commit()
        return self._binde_echte_methode(_state([_Fx(7, address=100)],
                                                 _show_engine=self.engine))

    @staticmethod
    def _binde_echte_methode(st):
        """Die ECHTE Methode an den Test-Zustand binden — samt Mitspieler.

        ``list_fixture_groups`` ruft ``self._session()``. Wird nur sie gebunden,
        wirft sie AttributeError, ihr eigenes ``except Exception: return []``
        schluckt ihn, und der Test misst wieder eine Attrappe statt der Sache.
        Genau diese Verwechslung ist STAB-22.
        """
        from src.core.app_state import AppState
        st._session = AppState._session.__get__(st, AppState)
        st.list_fixture_groups = AppState.list_fixture_groups.__get__(st, AppState)
        return st

    def test_geraet_nur_in_einer_gruppe_ist_KEINE_waise(self):
        st = self._state_mit_gruppe({"0,0": 7})
        self.assertIn("geraetegruppen", patch_dedup.referenzen(st, 7))
        self.assertEqual(patch_dedup.finde_kandidaten(st), [],
                         "Geraet steckt in einer Gruppe und gilt trotzdem als Waise")

    def test_auch_kopfzellen_schuetzen_das_geraet(self):
        """Kopf-Zellen stehen als ``"7:0"`` im Raster.

        Genau hier waere ein „sicherheitshalber" behaltener Rueckfall auf das
        rohe ``positions_json`` blind gewesen: ``_als_ints`` akzeptiert nur reine
        Ziffernfolgen. ``fids`` ist bereits durch ``base_fids_in_grid_order``
        aufgeloest — deshalb ist es die richtige Quelle, nicht nur die vorhandene.
        """
        st = self._state_mit_gruppe({"0,0": "7:0", "1,0": "7:1"})
        self.assertIn("geraetegruppen", patch_dedup.referenzen(st, 7))

    def test_die_zugesagte_form_wird_wirklich_geliefert(self):
        """Nagelt den Vertrag fest: wer ``fids`` umbenennt, wird hier rot —
        nicht erst dann, wenn ein Geraet verschwunden ist."""
        st = self._state_mit_gruppe({"0,0": 7})
        gruppen = st.list_fixture_groups()
        self.assertTrue(gruppen)
        self.assertIn("fids", gruppen[0],
                      "list_fixture_groups liefert kein 'fids' mehr — der "
                      "Scan-Ort in patch_dedup liest dann ins Leere")
        self.assertEqual(list(gruppen[0]["fids"]), [7])

    def test_verschluckter_lesefehler_bricht_ab_statt_waise_zu_melden(self):
        """★ Die zweite Haelfte von STAB-22.

        ``list_fixture_groups`` endet auf ``except Exception: return []``. Fuer
        den Preset-Browser ist das richtig; fuer ein Werkzeug, das daraufhin
        Geraete VERSCHIEBT, sieht ein unlesbarer Bestand exakt aus wie „keine
        Gruppen". Die Abbruch-Regel konnte an dieser Stelle prinzipiell nie
        greifen.
        """
        st = self._state_mit_gruppe({"0,0": 7})
        st.list_fixture_groups = lambda: []          # der verschluckte Fehler
        with self.assertRaises(patch_dedup.ScanUnvollstaendig) as ctx:
            patch_dedup.referenzen(st, 7)
        self.assertIn("verschluckt", str(ctx.exception))

    def test_leerer_bestand_ist_kein_verschluckter_fehler(self):
        """Gegenprobe, damit die Kreuzprobe nicht bei jeder Show ohne Gruppen
        Fehlalarm schlaegt — ein Waechter, der das tut, wird umgangen."""
        with Session(self.engine) as s:
            s.add(PatchedFixture(fid=7, label="Ohne Gruppe", fixture_profile_id=1,
                                 mode_name="m", universe=1, address=100,
                                 channel_count=4))
            s.commit()
        st = self._binde_echte_methode(
            _state([_Fx(7, address=100)], _show_engine=self.engine))
        self.assertEqual(patch_dedup.referenzen(st, 7), [])


if __name__ == "__main__":
    unittest.main()
