"""QA-77: die Dimmer-Dunkel-Pruefung kennt die Weiss-Achse — in beide Richtungen.

Eine Weiss-Zelle traegt ihren fid bewusst **nicht** in ``fixture_grid``: dort
muss eine Luecke stehen, sonst faerbt ein Verbraucher ohne Achsenkenntnis die
falsche Zone (FM-41). Wer wissen MUSS, welche Geraete eine Matrix bespielt,
liest deshalb beide Listen — genau wie ``function_manager.affected_fids``.

``dimmer_check._matrix_fids`` tat das nicht, und weil ``_treibt_dimmer``
dieselbe Funktion fragt, ging der Fehler in **zwei gegenlaeufige** Richtungen:

* **(a) eine Warnung bleibt aus:** ein Geraet, das nur ueber Weiss-Zellen
  gefaerbt wird, hat aus Sicht der Pruefung „keinen Faerber" und wird gar nicht
  geprueft.
* **(b) eine falsche Warnung kommt:** eine Matrix, die den Dimmer per
  ``drive_intensity`` sehr wohl hochzieht, aber nur ueber Weiss-Zellen faerbt,
  gilt als „treibt ihn nicht" — ``lint_show --strict`` meldet DIMMER-DUNKEL,
  obwohl die Show hell ist.

★ **Das Item trug ausdruecklich „nicht ende-zu-ende nachgemessen".** Beide
Richtungen sind vor dem Fix gemessen worden, mit Positivkontrolle. Das war
noetig: derselbe Sonden-Lauf lag bei ENG-15 daneben (falscher Mechanismus).

⚠️ **Und es waere um ein Haar falsch herum ausgegangen.** Aus den Testnamen der
FM-41-Suite (``test_kein_phantom_segment``: „zieht vor allem NICHT den geteilten
Master hoch") laesst sich schliessen, die Weiss-Achse fasse den Dimmer nie an —
dann waere (b) gar kein Fehlalarm, sondern richtig, und dieser Fix wuerde eine
WAHRE Warnung unterdruecken. Gemessen stimmt es nicht: die Aussage dort gilt
fuer die Weiss-Achse als Segment-Kanal, ``drive_intensity`` zieht den Master
davon unabhaengig hoch. Deshalb steht diese Praemisse unten als eigener Test am
RENDERER — faellt sie, ist der Fix hier falsch, und man soll es hier erfahren.
"""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core import app_state as AS
from src.core.capability.dimmer_check import statische_befunde


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num
        self.default_value = 0


#: Geteilter Master-Dimmer auf CH1, RGB dahinter, zwei Weiss-Segmente.
_KANAELE = [_Ch("intensity", 1), _Ch("color_r", 2), _Ch("color_g", 3),
            _Ch("color_b", 4), _Ch("color_w", 5), _Ch("color_w", 6)]

_PATCH = [{"fid": 1, "label": "Balken", "universe": 1, "address": 1,
           "channel_count": 6}]


def _matrix(fid_der_funktion, **extra) -> dict:
    d = {"type": "RGBMatrix", "id": fid_der_funktion,
         "name": f"M{fid_der_funktion}",
         "fixture_grid": [], "weiss_grid": [], "drive_intensity": False}
    d.update(extra)
    return d


class _Basis(unittest.TestCase):
    def setUp(self):
        alt = AS.get_channels_for_patched
        AS.get_channels_for_patched = lambda fx: list(_KANAELE)
        self.addCleanup(setattr, AS, "get_channels_for_patched", alt)

    def _befunde(self, *funktionen):
        return statische_befunde({"patch": _PATCH, "functions": list(funktionen)})


class HarnischTest(_Basis):
    """★ Zuerst der Nachweis, dass diese Probe ueberhaupt etwas ausloest.

    Ohne ihn ist jedes „0 Befunde" unten wertlos — eine Probe, die nie warnt,
    meldet Entwarnung ueber eine Frage, die nie gestellt wurde. Genau daran ist
    mein erster Messversuch gescheitert: ohne gestellte Kanaele fand
    ``dimmer_kanaele`` keinen Dimmer und ALLE vier Faelle waren still.
    """

    def test_eine_farbmatrix_ohne_drive_intensity_warnt(self):
        b = self._befunde(_matrix(10, fixture_grid=[1]))
        self.assertEqual(1, len(b), "die Probe loest die Warnung nicht aus")
        self.assertEqual("DIMMER-DUNKEL", b[0].code)

    def test_mit_drive_intensity_schweigt_sie(self):
        self.assertEqual(
            [], self._befunde(_matrix(10, fixture_grid=[1], drive_intensity=True)))


class WeissAchseTest(_Basis):
    """Die beiden gegenlaeufigen Richtungen aus dem Item."""

    def test_a_nur_weiss_gefaerbt_wird_GEPRUEFT(self):
        """Vorher: kein Faerber gefunden, also gar keine Pruefung."""
        b = self._befunde(_matrix(10, weiss_grid=[[1, 0]]))
        self.assertEqual(1, len(b),
                         "ein nur ueber Weiss-Zellen gefaerbtes Geraet faellt "
                         "aus der Pruefung — die Warnung bleibt aus")

    def test_b_eine_weiss_matrix_die_den_dimmer_zieht_erzeugt_KEINE_warnung(self):
        """★★ Die teure Richtung: ein Fehlalarm in ``lint_show --strict``.

        Matrix 10 faerbt farbig ohne Dimmer, Matrix 11 zieht ihn per
        ``drive_intensity`` — faerbt aber nur ueber Weiss-Zellen. Vorher zaehlte
        sie nicht, und die Show wurde als dunkel gemeldet, obwohl sie hell ist.
        """
        self.assertEqual([], self._befunde(
            _matrix(10, fixture_grid=[1]),
            _matrix(11, weiss_grid=[[1, 0]], drive_intensity=True)))

    def test_die_gegenprobe_ueber_die_farbachse_verhaelt_sich_gleich(self):
        """★ Beide Achsen muessen dieselbe Antwort geben — sonst haette man den
        Fehler nur verschoben."""
        self.assertEqual([], self._befunde(
            _matrix(10, fixture_grid=[1]),
            _matrix(11, fixture_grid=[1], drive_intensity=True)))


class StrengeFormTest(_Basis):
    """``weiss_grid`` wird streng auf ``(fid, segment)`` gelesen.

    Wie in ``affected_fids``: ein Text wie ``"5abc"`` wuerde ueber ``sub[0]``
    sonst als Geraet 5 durchgehen und ein Phantom-Geraet in die Menge tragen.
    """

    def test_muell_erzeugt_keine_phantom_geraete(self):
        b = self._befunde(_matrix(10, fixture_grid=[1],
                                  weiss_grid=["5abc", None, [1], [1, 2, 3],
                                              {"fid": 9}]))
        self.assertEqual(1, len(b), "nur Geraet 1 ist gepatcht und gefaerbt")
        self.assertIn("Balken", b[0].where + b[0].message)

    def test_ein_gueltiger_eintrag_zwischen_muell_zaehlt_trotzdem(self):
        """★ Die Gegenprobe: die Strenge darf nicht alles wegwerfen."""
        self.assertEqual(1, len(self._befunde(
            _matrix(10, weiss_grid=["kaputt", [1, 0], None]))))


class PraemisseTest(unittest.TestCase):
    """★★★ Die Annahme, auf der (b) steht — am RENDERER festgenagelt.

    (b) ist nur dann ein Fehlalarm, wenn eine Weiss-Matrix mit
    ``drive_intensity=True`` den Master-Dimmer WIRKLICH hochzieht. Taete sie es
    nicht, waere die alte Warnung richtig und der Fix in ``_matrix_fids``
    wuerde eine wahre Warnung unterdruecken — die teuerste Sorte Fehler.

    Ich habe das beim Bauen zuerst FALSCH geschlossen, aus den Testnamen der
    FM-41-Suite. Deshalb steht es hier als Messung und nicht als Annahme: faellt
    dieser Test, gehoert der Fix in ``_matrix_fids`` ueberprueft.
    """

    def _frame(self, positions, cols, rows, drive):
        from src.core.engine.rgb_matrix import (RgbMatrixInstance, MatrixStyle,
                                                grids_from_positions,
                                                weiss_grid_from_positions)
        alt = AS.get_channels_for_patched
        AS.get_channels_for_patched = lambda fx: list(_KANAELE)
        self.addCleanup(setattr, AS, "get_channels_for_patched", alt)

        fg, hg = grids_from_positions(positions, cols, rows)
        mx = RgbMatrixInstance(name="T")
        mx.cols, mx.rows = cols, rows
        mx.style = MatrixStyle.RGBW
        mx.fixture_grid, mx.head_grid = fg, hg
        mx.weiss_grid = weiss_grid_from_positions(positions, cols, rows)
        mx.drive_intensity = drive
        mx._running = True
        mx._render = lambda phase, n=cols * rows: [(255, 255, 255)] * n

        class _U:
            def __init__(self):
                self.ch = {}

            def set_channel(self, a, v):
                self.ch[a] = v

        u = _U()
        mx.write({1: u}, [SimpleNamespace(fid=1, universe=1, address=1,
                                          fixture_type="matrix")], 0.02)
        return u.ch

    def test_eine_weiss_matrix_zieht_den_master_dimmer_hoch(self):
        raster = {"0,0": "1:w0", "1,0": "1:w1"}
        ohne = self._frame(raster, 2, 1, drive=False)
        mit = self._frame(raster, 2, 1, drive=True)

        self.assertEqual([5, 6], sorted(ohne),
                         "Vorbedingung: die Weiss-Segmente werden gefahren")
        self.assertNotIn(1, ohne,
                         "ohne drive_intensity bleibt der Master unberuehrt")
        self.assertEqual(255, mit.get(1),
                         "mit drive_intensity zieht auch eine WEISS-Matrix den "
                         "geteilten Master hoch — faellt das weg, ist der "
                         "QA-77-Fix in _matrix_fids falsch")

    def test_und_die_farbachse_verhaelt_sich_genauso(self):
        """★ Ohne diesen Arm koennte oben etwas Weiss-Spezifisches gemessen
        sein statt der Regel."""
        mit = self._frame({"0,0": "1:0"}, 1, 1, drive=True)
        self.assertEqual(255, mit.get(1))


if __name__ == "__main__":
    unittest.main()
