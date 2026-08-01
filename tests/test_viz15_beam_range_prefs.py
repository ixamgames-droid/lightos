"""VIZ-15: globale Max-Strahllaenge — Python-Haelfte (Prefs + Stub-Sicherheit).

Der Regler deckelt AUSSCHLIESSLICH die Darstellung; an der DMX-Ausgabe aendert
sich nichts. Gemerkt wird er geraete-gebunden in ui_prefs (Key
``viz_max_beam_range``), dieselbe Ablage wie die Qualitaetsstufe und aus
verwandtem Grund: der sinnvolle Wert haengt am RAUM, nicht an der Show, die
zwischen Raeumen wandert.
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.ui.visualizer.visualizer_window as VW


class MaxBeamRangePrefTest(unittest.TestCase):
    def _mit_prefs(self, prefs):
        return patch("src.ui.views.programmer_view._load_prefs",
                     return_value=prefs)

    def test_ohne_eintrag_ist_der_deckel_aus(self):
        with self._mit_prefs({}):
            self.assertEqual(VW.max_beam_range_pref(), 0.0)

    def test_wert_wird_gelesen(self):
        with self._mit_prefs({"viz_max_beam_range": 6}):
            self.assertEqual(VW.max_beam_range_pref(), 6.0)

    def test_obergrenze_wird_gekappt(self):
        """Ein Wert jenseits der Reglerspanne darf nicht durchrutschen — sonst
        stuende im Regler etwas anderes als in der Szene."""
        with self._mit_prefs({"viz_max_beam_range": 999}):
            self.assertEqual(VW.max_beam_range_pref(), float(VW.MAX_BEAM_RANGE_MAX))

    def test_unsinn_faellt_auf_aus_zurueck(self):
        for wert in ("abc", None, -3, float("nan"), float("inf"), ""):
            with self._mit_prefs({"viz_max_beam_range": wert}):
                self.assertEqual(VW.max_beam_range_pref(), 0.0,
                                 f"{wert!r} muss als 'aus' gelten")

    def test_kaputte_prefs_werfen_nicht(self):
        with patch("src.ui.views.programmer_view._load_prefs",
                   side_effect=OSError("kaputt")):
            self.assertEqual(VW.max_beam_range_pref(), 0.0)


class BeamRangeStubSicherheitTest(unittest.TestCase):
    """Die Falle, die in diesem Projekt dreimal an einem Tag zugeschlagen hat:
    Bestandstests fahren Handler ungebunden auf ``SimpleNamespace``-Stubs. Ein
    neues Pflichtfeld auf ``self`` wirft dort ``AttributeError`` — und der
    verschwindet im ``except`` des Aufrufers, das Feature scheitert lautlos.
    Deshalb ist der Reglerwert eine MODUL-Funktion, kein Methoden-Helfer --
    beim ersten Anlauf hat die Falle hier prompt wieder zugeschlagen und wurde
    von genau diesen Tests gefangen.
    """

    def test_ohne_regler_liefert_null_statt_zu_werfen(self):
        stub = SimpleNamespace()
        self.assertEqual(VW.beam_range_value(stub), 0.0)

    def test_kaputter_regler_liefert_null_statt_zu_werfen(self):
        stub = SimpleNamespace(_sld_beam_range=SimpleNamespace(
            value=lambda: (_ for _ in ()).throw(RuntimeError("weg"))))
        self.assertEqual(VW.beam_range_value(stub), 0.0)

    def test_reglerwert_kommt_durch(self):
        stub = SimpleNamespace(_sld_beam_range=SimpleNamespace(value=lambda: 7))
        self.assertEqual(VW.beam_range_value(stub), 7.0)

    def test_beschriftung_sagt_aus_bei_null(self):
        texte = []
        stub = SimpleNamespace(
            _sld_beam_range=SimpleNamespace(value=lambda: 0),
            _lbl_beam_range=SimpleNamespace(setText=texte.append))
        VW.VisualizerWindow._update_beam_range_label(stub)
        self.assertEqual(texte, ["aus"])

    def test_beschriftung_zeigt_meter(self):
        texte = []
        stub = SimpleNamespace(
            _sld_beam_range=SimpleNamespace(value=lambda: 12),
            _lbl_beam_range=SimpleNamespace(setText=texte.append))
        VW.VisualizerWindow._update_beam_range_label(stub)
        self.assertEqual(texte, ["12 m"])

    def test_ohne_beschriftung_passiert_nichts(self):
        VW.VisualizerWindow._update_beam_range_label(SimpleNamespace())


class BeideZieleZeigenDasselbeTest(unittest.TestCase):
    """Vollfenster und eingebettete Live-View-3D muessen denselben Deckel
    verwenden — sonst zeigte dieselbe Szene in den beiden Ansichten
    unterschiedlich lange Kegel, und der Regler waere in einer davon
    wirkungslos."""

    def test_eingebettete_view_liest_denselben_pref(self):
        import src.ui.visualizer.visualizer_view as VV
        self.assertIs(VV.max_beam_range_pref, VW.max_beam_range_pref,
                      "die View muss DIESELBE Quelle lesen, nicht eine eigene")

    def test_eingebettete_view_reicht_den_wert_durch(self):
        import src.ui.visualizer.visualizer_view as VV
        stub = SimpleNamespace(_sld_brightness=SimpleNamespace(value=lambda: 40),
                               _state=SimpleNamespace(show_fixture_labels=True))
        with patch("src.ui.views.programmer_view._load_prefs",
                   return_value={"viz_max_beam_range": 9}):
            s = VV.Visualizer3DView._collect_settings(stub)
        self.assertEqual(s.get("maxBeamRange"), 9.0)


if __name__ == "__main__":
    unittest.main()
