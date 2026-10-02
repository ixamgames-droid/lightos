"""FM-54: Der Intensitaetsregler der Matrix wirkt auch auf die Weiss-Segmente
eines Geraets mit MEHREREN Dimmer-Kanaelen.

Gefunden beim Befund zu FM-46 (#846, Punkt 2). Die Weiss-Achse
(``RgbMatrixInstance._weiss_achse_schreiben``) dimmt ein Weiss-Segment nur
dann selbst, wenn der FunctionManager-Merge es nicht tut:
``_skalieren = _hat_dimmer and not self.drive_intensity and inten < 0.999``.
Dahinter steht die Annahme „treibt die Matrix den Dimmer, dimmt der Merge
ueber den Dimmer-Kanal". Bei einem Geraet mit zwei ``intensity``-Kanaelen
liefert ``channels_for_axis`` fuer ein Weiss-Segment aber KEINEN Dimmer
(welcher von beiden das Segment dimmt, steht nicht in der Kanalliste). Die
Matrix schreibt dann keinen Dimmer, der Merge skaliert bei Geraeten mit Dimmer
nur Dimmer-Adressen — und das Weiss-Segment blieb bei Master 0,5 auf 255.

Regel jetzt: das Segment wird in der Matrix gedimmt, sobald die Matrix an
diesem Geraet KEINEN Dimmer treibt — weder ueber die Weiss-Projektion noch
ueber eigene Farbzellen. Treibt sie die Dimmer ueber Farbzellen mit, bleibt es
wie bisher (sonst doppelt gedimmt, falls einer davon das Weiss dimmt; welcher,
ist die offene Frage von FM-46).

Gemessen wird das ENDERGEBNIS nach dem echten Merge (``FunctionManager.tick``),
nicht der Zwischenwert der Matrix.
"""
import os
import unittest
from types import SimpleNamespace as N

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as AS                                  # noqa: E402
from src.core.dmx.universe import Universe                       # noqa: E402
from src.core.engine.function_manager import FunctionManager    # noqa: E402
from src.core.engine.rgb_matrix import MatrixStyle, RgbMatrixInstance  # noqa: E402


def _ch(attr, nr):
    return N(attribute=attr, channel_number=nr, default_value=0,
             highlight_value=255, ranges=[], name=attr)


def _geraet(n_dimmer):
    """``n_dimmer`` Dimmer, vier RGB-Koepfe, zwei eigene Weiss-Segmente."""
    kanaele = [_ch("intensity", i + 1) for i in range(n_dimmer)]
    nr = n_dimmer + 1
    for _ in range(4):
        for a in ("color_r", "color_g", "color_b"):
            kanaele.append(_ch(a, nr))
            nr += 1
    kanaele += [_ch("color_w", nr), _ch("color_w", nr + 1)]
    return kanaele


class _Basis(unittest.TestCase):

    def setUp(self):
        alt = AS.get_channels_for_patched
        self.addCleanup(setattr, AS, "get_channels_for_patched", alt)

    def _lauf(self, n_dimmer, drive, *, inten=0.5, farbzellen=False):
        """Ein Vollweiss-Frame durch den echten Merge -> ``{adresse: wert}``
        und die Adressen von Dimmern und Weiss-Segmenten."""
        kanaele = _geraet(n_dimmer)
        AS.get_channels_for_patched = lambda fx, k=kanaele: k
        fx = N(fid=1, universe=1, address=1, fixture_type="led_bar",
               fixture_profile_id=1, mode_name="m", channel_count=len(kanaele))
        mx = RgbMatrixInstance(name="FM54")
        mx.style = MatrixStyle.RGB
        mx.cols, mx.rows = 2, 1
        mx.fixture_grid = [1, None] if farbzellen else [None, None]
        mx.head_grid = [None, None]
        mx.weiss_grid = [None, (1, 0)] if farbzellen else [(1, 0), (1, 1)]
        mx.drive_intensity = drive
        mx.intensity = inten
        mx._render = lambda phase: [(255, 255, 255)] * 2
        fm = FunctionManager()
        fm.add(mx)
        fm.start(mx.id)
        uni = Universe(1)
        fm.tick({1: uni}, [fx], 0.02)
        dimmer = [c.channel_number for c in kanaele if c.attribute == "intensity"]
        weiss = [c.channel_number for c in kanaele if c.attribute == "color_w"]
        return uni, dimmer, weiss


class DerReglerWirktAufDieWeissSegmente(_Basis):

    def test_zwei_dimmer_dimmer_mit_treiben(self):
        """Der Fund: Master 0,5, aber die Weiss-Segmente standen auf 255.

        ★ Seit FM-46 (Etappe 2) treibt die Matrix hier wieder einen Dimmer:
        ohne gespeicherte Zuordnung oeffnet sie die freien Vorkommen
        (``weiss_rueckfall_dimmer``). Bei diesem Geraet liegen RGB und Weiss
        in EINEM Abschnitt hinter CH2 — nach der Review-Regel faehrt nur der
        Dimmer, der an diesen Abschnitt grenzt (CH2); CH1 bleibt zu. Damit
        gilt derselbe Weg wie beim geteilten Master: der Merge halbiert den
        DIMMER, das Weiss bleibt im Wert voll. Die FM-54-Zusage (der Regler
        wirkt) bleibt — nur traegt sie jetzt der Dimmer. Vorher erwartete
        dieser Test ``[0, 0]`` fuer die Dimmer und ``[127, 127]`` fuer das
        Weiss: ein Segment hinter einem Dimmer auf 0 ist am Geraet dunkel."""
        uni, dimmer, weiss = self._lauf(2, drive=True)
        self.assertEqual([uni.get_channel(a) for a in dimmer], [0, 127],
                         "der angrenzende Dimmer, vom Merge halbiert")
        self.assertEqual([uni.get_channel(a) for a in weiss], [255, 255],
                         "nicht doppelt dimmen")

    def test_voller_master_unveraendert(self):
        uni, _dimmer, weiss = self._lauf(2, drive=True, inten=1.0)
        self.assertEqual([uni.get_channel(a) for a in weiss], [255, 255])


class BestandUnveraendert(_Basis):
    """Die Faelle, in denen der Merge schon dimmt — dort darf sich nichts
    aendern (sonst wird QUADRATISCH gedimmt, s. FM-41 ``test_weiss_wird_genauso
    _gedimmt_wie_die_farbzonen``)."""

    def test_ein_dimmer_dimmer_mit_treiben(self):
        """Der geteilte Dimmer kommt mit der Projektion: die Matrix zieht ihn
        auf, der Merge halbiert IHN — das Weiss bleibt im Wert voll."""
        uni, dimmer, weiss = self._lauf(1, drive=True)
        self.assertEqual([uni.get_channel(a) for a in dimmer], [127])
        self.assertEqual([uni.get_channel(a) for a in weiss], [255, 255])

    def test_ohne_dimmer_mit_treiben_dimmt_die_matrix(self):
        for n in (1, 2):
            with self.subTest(dimmer=n):
                uni, dimmer, weiss = self._lauf(n, drive=False)
                self.assertEqual([uni.get_channel(a) for a in weiss], [127, 127])
                self.assertEqual([uni.get_channel(a) for a in dimmer], [0] * n)

    def test_farbzellen_treiben_die_dimmer_mit(self):
        """Treibt die Matrix die Dimmer ueber eigene Farbzellen, dimmt der
        Merge sie — das Weiss NICHT zusaetzlich in der Matrix dimmen."""
        uni, dimmer, weiss = self._lauf(2, drive=True, farbzellen=True)
        self.assertEqual([uni.get_channel(a) for a in dimmer], [127, 127])
        self.assertEqual(uni.get_channel(weiss[0]), 255)


if __name__ == "__main__":
    unittest.main()
