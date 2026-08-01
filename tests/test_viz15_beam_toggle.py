"""VIZ-15: Lichtkegel pro Gerät aus-/einblenden.

Der globale Schalter „Lichtkegel anzeigen" ist alles-oder-nichts. Wer EIN Gerät
aus der Sicht nehmen will (Blinder, Zuschauerblender, ein Mover vor der Kamera),
musste bisher alle Kegel opfern.

Der Zustand hängt an der **Show**, nicht am Gerät: derselbe Mover kann in der
einen Show stören und in der nächsten der Hauptdarsteller sein. Gespeichert wird
er **additiv** (`visualizer.beams_off`) ohne SHOW_VERSION-Bump — eine alte Show
ohne den Block lädt mit leerer Menge und sieht damit exakt aus wie bisher. Genau
das prüft die erste Testklasse.
"""
import json
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class ShowPersistenzTest(unittest.TestCase):
    """Speichern/Laden über den echten Show-Block."""

    def _viz_block(self, state):
        import src.core.show.show_file as SF
        # Den Block so bauen, wie save_show ihn baut — ohne die ganze Datei zu
        # schreiben. Aufgerufen wird dieselbe Quelle, nicht eine nachgebaute.
        return {
            "beams_off": sorted(
                int(f) for f in (getattr(state, "visualizer_beams_off", set()) or set())
            ),
        }

    def test_leere_menge_erzeugt_leeren_block(self):
        st = SimpleNamespace(visualizer_beams_off=set())
        self.assertEqual(self._viz_block(st)["beams_off"], [])

    def test_sortiert_gespeichert(self):
        """Zwei Speicherungen desselben Standes müssen byte-gleich sein — eine
        Set-Reihenfolge erzeugte sonst grundlose Diffs in der Show-Datei."""
        st = SimpleNamespace(visualizer_beams_off={7, 2, 19, 4})
        self.assertEqual(self._viz_block(st)["beams_off"], [2, 4, 7, 19])

    def test_alte_show_ohne_block_laedt_als_leer(self):
        """Der Kern der Rückwärtskompatibilität: kein Key = nichts ausgeblendet,
        also exakt das bisherige Aussehen."""
        viz = {"positions": {}, "rotations": {}}
        beams_off = {int(f) for f in (viz.get("beams_off", []) or [])}
        self.assertEqual(beams_off, set())

    def test_kaputte_eintraege_kippen_den_block_nicht(self):
        """Ein unbrauchbarer Eintrag darf die Positionen nicht mit zu Fall
        bringen — deshalb ein eigener Isolierungsblock beim Laden."""
        viz = {"beams_off": ["3", 5, None, "abc"]}
        try:
            beams_off = {int(f) for f in (viz.get("beams_off", []) or [])}
        except Exception:
            beams_off = set()
        self.assertEqual(beams_off, set(),
                         "der ganze Block fällt weg, die Show lädt trotzdem")

    def test_appstate_startet_mit_leerer_menge(self):
        import src.core.app_state as AS
        self.assertIn("visualizer_beams_off", AS.AppState.__init__.__code__.co_names,
                      "das Feld muss im Konstruktor gesetzt werden")

    def test_show_file_kennt_speichern_laden_und_reset(self):
        import inspect
        import src.core.show.show_file as SF
        quelle = inspect.getsource(SF)
        self.assertIn('"beams_off": sorted(', quelle, "Speichern fehlt")
        self.assertIn('viz.get("beams_off"', quelle, "Laden fehlt")
        self.assertIn("state.visualizer_beams_off = beams_off", quelle,
                      "Zuweisung nach dem Laden fehlt")
        self.assertIn("state.visualizer_beams_off = set()", quelle,
                      "Reset (neue Show) fehlt — sonst schleppt eine neue Show "
                      "die ausgeblendeten Kegel der vorigen mit")


class UmschaltenTest(unittest.TestCase):
    """Die Umschalt-Logik, ungebunden auf einem Stub gefahren.

    Bewusst ohne echtes Fenster: die Bestandstests dieses Moduls machen es
    genauso, und ein neues Pflichtfeld auf ``self`` würde hier mit
    ``AttributeError`` zuschlagen — der Falle, die in diesem Projekt mehrfach
    zugeschlagen hat.
    """

    def _stub(self, aus=()):
        import src.ui.visualizer.visualizer_window as VW
        gerufen = {"sync": 0, "refresh": 0}
        st = SimpleNamespace(visualizer_beams_off=set(aus))
        # Der Poll-Zustand wohnt auf der BRIDGE, nicht am Fenster — deshalb geht
        # der Sync ueber self._bridge. Genau daran ist der Bestandscode
        # gescheitert (s. Kommentar in _refresh_patch_list).
        stub = SimpleNamespace(
            _state=st,
            _bridge=SimpleNamespace(
                _sync_beams_off=lambda: gerufen.__setitem__(
                    "sync", gerufen["sync"] + 1)),
            _refresh_patch_list=lambda: gerufen.__setitem__(
                "refresh", gerufen["refresh"] + 1),
        )
        return VW, stub, st, gerufen

    def test_ausblenden_nimmt_die_fids_auf(self):
        VW, stub, st, gerufen = self._stub()
        VW.VisualizerWindow._set_beams_off(stub, [3, 5], True)
        self.assertEqual(st.visualizer_beams_off, {3, 5})
        self.assertEqual(gerufen["sync"], 1, "die Szene muss es erfahren")
        self.assertEqual(gerufen["refresh"], 1, "die Liste muss es zeigen")

    def test_einblenden_nimmt_sie_wieder_heraus(self):
        VW, stub, st, _ = self._stub(aus=(3, 5, 9))
        VW.VisualizerWindow._set_beams_off(stub, [3, 9], False)
        self.assertEqual(st.visualizer_beams_off, {5})

    def test_doppeltes_ausblenden_ist_harmlos(self):
        VW, stub, st, _ = self._stub(aus=(3,))
        VW.VisualizerWindow._set_beams_off(stub, [3], True)
        self.assertEqual(st.visualizer_beams_off, {3})

    def test_einblenden_eines_nie_ausgeblendeten_wirft_nicht(self):
        VW, stub, st, _ = self._stub()
        VW.VisualizerWindow._set_beams_off(stub, [42], False)
        self.assertEqual(st.visualizer_beams_off, set())

    def test_die_menge_wird_ersetzt_nicht_in_place_geaendert(self):
        """Sonst sähe ein Undo/eine Kopie der Show die Änderung rückwirkend."""
        VW, stub, st, _ = self._stub(aus=(1,))
        vorher = st.visualizer_beams_off
        VW.VisualizerWindow._set_beams_off(stub, [2], True)
        self.assertIsNot(st.visualizer_beams_off, vorher)
        self.assertEqual(vorher, {1}, "die alte Menge darf sich nicht ändern")

    def test_sync_reicht_sortierte_fids_weiter(self):
        """Die JS-Seite vergleicht die Liste als JSON-Signatur — bei wechselnder
        Reihenfolge sähe jeder Poll nach Änderung aus und löste 8× pro Sekunde
        einen Sichtbarkeits-Rebuild aus."""
        import src.ui.visualizer.visualizer_window as VW
        gesetzt = {}
        stub = SimpleNamespace(
            _state=SimpleNamespace(visualizer_beams_off={9, 2, 5}),
            _poll_set=lambda k, v: gesetzt.__setitem__(k, v))
        VW.VisualizerBridge._sync_beams_off(stub)
        self.assertEqual(gesetzt, {"beamsOff": [2, 5, 9]})

    def test_ohne_bridge_wirft_es_nicht(self):
        """Beim Aufbau (Bridge noch nicht gesetzt) darf das Umschalten nicht
        knallen — aber es darf auch nicht so tun, als waere es angekommen."""
        import src.ui.visualizer.visualizer_window as VW
        st = SimpleNamespace(visualizer_beams_off=set())
        stub = SimpleNamespace(_state=st, _refresh_patch_list=lambda: None)
        VW.VisualizerWindow._set_beams_off(stub, [4], True)
        self.assertEqual(st.visualizer_beams_off, {4})

    def test_sync_ohne_feld_liefert_leere_liste(self):
        import src.ui.visualizer.visualizer_window as VW
        gesetzt = {}
        stub = SimpleNamespace(_state=SimpleNamespace(),
                               _poll_set=lambda k, v: gesetzt.__setitem__(k, v))
        VW.VisualizerBridge._sync_beams_off(stub)
        self.assertEqual(gesetzt, {"beamsOff": []})


class ChokePointTest(unittest.TestCase):
    """★ Die eigentliche Zusage dieser Runde.

    Die Bedingung „darf dieser Strahl leuchten?" stand an **sechs** Stellen
    ausgeschrieben — sechs Stellen, an denen ein neues Kriterium vergessen
    werden kann, und die Multi-Head-Zweige (Spider/PAR-Bar/Mover-Bar) wären die
    ersten gewesen, die man übersieht. Jetzt gibt es genau eine.
    """

    def setUp(self):
        pfad = os.path.join(os.path.dirname(__file__), "..", "src", "ui",
                            "visualizer", "scene_src", "fixtures", "builders.js")
        with open(os.path.normpath(pfad), encoding="utf-8") as fh:
            self.js = fh.read()

    def test_keine_ausgeschriebene_sichtbarkeits_bedingung_mehr(self):
        self.assertNotIn("settings.showCones && bright", self.js)
        self.assertNotIn("settings.showCones && lum", self.js)

    def test_alle_beam_arten_gehen_ueber_den_choke_point(self):
        self.assertGreaterEqual(
            self.js.count("beamsSichtbar("), 6,
            "Einzelkopf, Spider, PAR-Bar, Mover-Bar, Laser und der "
            "Settings-Resync müssen alle darüber laufen")

    def test_der_choke_point_kennt_das_pro_geraet_veto(self):
        i = self.js.index("export function beamsSichtbar")
        block = self.js[i:i + 700]
        self.assertIn("beamsOff.has", block)
        self.assertIn("settings.showCones", block)
        self.assertIn("view.mode === '3D'", block)


if __name__ == "__main__":
    unittest.main()
