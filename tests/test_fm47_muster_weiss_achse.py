"""FM-47: der Muster-Chaser faehrt die Weiss-Achse — und verkuerzt nicht still.

Der Renderer fuehrt die zweite Achse seit FM-41. Der MUSTER-Weg ist ein eigener,
zweiter Pfad und war noch nicht nachgezogen: ``matrix_pattern._cell_values`` las
nur ``grid``/``heads``. Eine Weiss-Zelle ist dort per Konstruktion eine LUECKE
(sonst faerbte ein Verbraucher ohne Achsenkenntnis die falsche Zone) — und ein
Schritt ohne Geraet wird ganz weggelassen.

★ **Gemessen vor dem Fix** (das Item trug „Sondenbefund, nicht nachgemessen"),
mit Positivkontrolle:

* zwei FARB-Zellen → 2 Frames, **2 Schritte** (die Probe loest aus),
* zwei WEISS-Zellen → 2 Frames, **0 Schritte**, kein Chaser,
* **gemischt** → 2 Frames, **1 Schritt**.

★★ Der gemischte Fall ist der heimtueckische: man bekommt einen Chaser, der
laeuft — nur mit einem Schritt weniger, und nichts sagt es. „Kein Schritt" faellt
auf, „ein Schritt zu wenig" nicht.

⚠️ **Was hier NICHT passiert, und die Unterscheidung ist wichtig:** Weiss laeuft
weiterhin nicht bei FARB-Effekten mit — ``cell_channel_values`` bedient
``color_w`` bewusst nicht (Robins Entscheidung vom 2026-08-05). Hier geht es um
Zellen, die SELBST Weiss-Zellen sind, vom Nutzer ueber die Weiss-Achse
ausdruecklich ins Raster gesetzt. Zwei Fragen, die gleich aussehen: „faerbt ein
Farbeffekt auch das Weiss?" (nein) und „faehrt ein Muster eine Weiss-Zelle?"
(ja). Der letzte Test unten haelt die erste Haelfte fest.
"""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core import app_state as AS
from src.core.engine.function_manager import FunctionManager
from src.core.matrix_pattern import build_pattern_chaser, pattern_frames


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num
        self.default_value = 0


def _panel():
    """Geteilter Master @1, RGB @2-4, ZWEI eigene Weiss-Segmente @5-6."""
    return [_Ch("intensity", 1), _Ch("color_r", 2), _Ch("color_g", 3),
            _Ch("color_b", 4), _Ch("color_w", 5), _Ch("color_w", 6)]


def _rgbw_par():
    """4-Kanal-RGBW-PAR: das Weiss gehoert zur FARBZELLE, ist keine eigene Achse."""
    return [_Ch("color_r", 1), _Ch("color_g", 2), _Ch("color_b", 3),
            _Ch("color_w", 4)]


class _Basis(unittest.TestCase):
    kanaele = staticmethod(_panel)

    def setUp(self):
        alt = AS.get_channels_for_patched
        AS.get_channels_for_patched = lambda fx: list(self.kanaele())
        self.addCleanup(setattr, AS, "get_channels_for_patched", alt)
        self.fx = SimpleNamespace(fid=1, universe=1, address=1,
                                  fixture_type="matrix", channel_count=6)

    def _bau(self, grid, weiss, **kw):
        n = max(len(grid), len(weiss))
        mx = SimpleNamespace(fixture_grid=list(grid), head_grid=[None] * n,
                             weiss_grid=list(weiss), cols=n, rows=1)
        ch, szenen = build_pattern_chaser(
            FunctionManager(), mx, pattern_frames(n, 1, "lr"),
            name="Probe", patch_cache=[self.fx], **kw)
        werte = [{v.channel: v.value for v in s._values} for s in szenen]
        return ch, werte


class HarnischTest(_Basis):
    """★ Zuerst der Nachweis, dass die Probe ueberhaupt Schritte erzeugt."""

    def test_zwei_farbzellen_ergeben_zwei_schritte(self):
        ch, werte = self._bau([1, 1], [None, None])
        self.assertIsNotNone(ch)
        self.assertEqual(2, len(werte), "die Probe erzeugt keine Schritte")
        self.assertEqual({1: 255, 2: 255, 3: 255, 4: 255}, werte[0])


class WeissAchseTest(_Basis):
    """Das Abnahmekriterium: Schrittzahl == Zellzahl."""

    def test_eine_reine_weiss_gruppe_faehrt(self):
        ch, werte = self._bau([None, None], [(1, 0), (1, 1)])
        self.assertIsNotNone(ch, "kein Chaser — die Weiss-Zellen sind Luecken")
        self.assertEqual(2, len(werte))

    def test_jeder_schritt_faehrt_SEIN_segment(self):
        """★★ Sonst waere es kein Lauflicht, sondern zweimal dasselbe.

        Ein Fix, der stur das erste Segment nimmt, erzeugt die richtige
        SCHRITTZAHL und faellt der Zusicherung oben nicht auf.
        """
        _, werte = self._bau([None, None], [(1, 0), (1, 1)])
        self.assertEqual(255, werte[0].get(5), "Schritt 1 faehrt Segment 1 (CH5)")
        self.assertNotIn(6, werte[0], "Schritt 1 faehrt auch Segment 2 mit")
        self.assertEqual(255, werte[1].get(6), "Schritt 2 faehrt Segment 2 (CH6)")
        self.assertNotIn(5, werte[1])

    def test_gemischt_verliert_keinen_schritt(self):
        """★★★ Der heimtueckische Fall: der Chaser LAEUFT, nur kuerzer."""
        ch, werte = self._bau([1, None], [None, (1, 1)])
        self.assertIsNotNone(ch)
        self.assertEqual(2, len(werte),
                         "der Weiss-Schritt faellt still weg — ein Chaser mit "
                         "einem Schritt zu wenig faellt niemandem auf")
        self.assertIn(2, werte[0], "Schritt 1 ist die Farbzelle")
        self.assertEqual(255, werte[1].get(6), "Schritt 2 ist die Weiss-Zelle")

    def test_ein_raster_ganz_ohne_farbachse_faehrt_auch(self):
        """Leeres ``fixture_grid`` — die fruehe Wache prueft jetzt beide Achsen."""
        ch, werte = self._bau([], [(1, 0), (1, 1)])
        self.assertIsNotNone(ch)
        self.assertEqual(2, len(werte))


class GrenzenTest(_Basis):
    """Die Riegel, die aus FM-41/ENG-25 und FM-45 mitkommen."""

    def test_der_geteilte_master_kommt_nur_mit_drive_intensity(self):
        _, mit = self._bau([None, None], [(1, 0), (1, 1)], drive_intensity=True)
        _, ohne = self._bau([None, None], [(1, 0), (1, 1)], drive_intensity=False)
        self.assertEqual(255, mit[0].get(1), "ohne Master bleibt das Panel dunkel")
        self.assertNotIn(1, ohne[0],
                         "der geteilte Master gehoert sonst dem Nutzer bzw. "
                         "dem Merge — mehrere Weiss-Zellen wuerden sich darum "
                         "streiten")

    def test_ein_segment_das_es_nicht_gibt_faehrt_nichts(self):
        """FM-45-Grenze: kein Phantom-Emitter, und vor allem NICHT ersatzweise
        die geteilten Kanaele allein — sonst zoege eine Zelle jenseits der
        Segmentzahl den Master des ganzen Geraets hoch."""
        ch, werte = self._bau([None, None], [(1, 0), (1, 9)])
        self.assertEqual(1, len(werte), "das Phantom-Segment erzeugt einen Schritt")
        self.assertEqual(255, werte[0].get(5))

    def test_missgeformte_eintraege_erzeugen_keine_phantom_geraete(self):
        ch, werte = self._bau([1, None, None], ["5abc", None, [1]])
        self.assertEqual(1, len(werte), "nur die Farbzelle traegt einen Schritt")


class WeissGehoertZurFarbzelleTest(_Basis):
    """⚠️ Der Torwaechter aus FM-41/ENG-25, hier gegengeprueft.

    Bei einem 4-Kanal-RGBW-PAR gehoert das Weiss zur FARBZELLE — beide Zellen
    adressieren denselben Kanal. Eine Weiss-Zelle darf dort nichts fahren, sonst
    ueberschriebe sie die Farbe (gemessen in FM-41: die Weiss-Zelle gewann
    IMMER, weil ihre Schleife baulich spaeter laeuft).
    """
    kanaele = staticmethod(_rgbw_par)

    def test_dort_faehrt_die_weiss_zelle_nichts(self):
        ch, werte = self._bau([None, None], [(1, 0), (1, 1)])
        self.assertIsNone(ch, "die Weiss-Zelle faehrt ein Geraet, dessen Weiss "
                              "zur Farbzelle gehoert")
        self.assertEqual([], werte)


class FarbeFaerbtKeinWeissTest(_Basis):
    """★★★ Robins Entscheidung vom 2026-08-05 bleibt gueltig.

    „Weiss soll bei Farbeffekten nicht mitlaufen." Diese Datei aendert das
    NICHT — sie faehrt nur Zellen, die der Nutzer ausdruecklich als
    Weiss-Segmente ins Raster gesetzt hat. Faellt dieser Test, ist aus der
    zweiten Achse ein Mitlaufen geworden.
    """

    def test_eine_farbzelle_schreibt_keinen_weiss_kanal(self):
        _, werte = self._bau([1, 1], [None, None])
        for i, w in enumerate(werte):
            with self.subTest(schritt=i):
                self.assertNotIn(5, w, "die Farbzelle faerbt ein Weiss-Segment")
                self.assertNotIn(6, w)


if __name__ == "__main__":
    unittest.main()
