"""FM-46 (Etappe 2): ohne Zuordnung fahren die freien Dimmer eines
Weiss-Segments GEMEINSAM — und der Mensch erfaehrt es.

Entscheidung des Projektinhabers: die Matrix soll moeglichst immer leuchten;
ein Hinweis ist besser als ein stumm dunkles Segment. Etappe 1 liess ein
Weiss-Segment ohne gespeicherte Zuordnung hinter seinem Dimmer liegen — stand
der auf 0, blieb das Segment dunkel.

Jetzt (``app_state.weiss_rueckfall_dimmer``): bei ``drive_intensity`` oeffnet
die Matrix die Vorkommen des mehrfachen Dimmers, die nicht nachweislich
jemand anderem gehoeren — einem anderen Weiss-Segment (gespeicherte
Zuordnung), einem Farbkopf (Kopf-Karte, FM-17) oder einem FARBABSCHNITT.

★ Review (02.10.): die Kopf-Karte greift bei keinem echten Modus, weil der
Dimmer dort VOR oder NACH seinem Farbblock steht. Die Geraete unten sind
deshalb echten Bibliotheks-Layouts nachgebaut (Fusion Orbit MKII 16ch,
Ginamp 36ch, Robin Tetra) statt synthetisch. Leitsatz: lieber ein Segment zu
wenig oeffnen als einen fremden Teil aufleuchten lassen.

Geprueft:

* die Regel selbst (frei / anderes Segment / Farbabschnitt / gemischter
  Abschnitt / Phantom-Segment);
* Renderer und Muster-Pfad (``weiss_cell_values``) geben dieselbe Antwort,
  der Renderer gemessen nach dem ECHTEN Merge (kein doppeltes Dimmen);
* ``drive_intensity=False`` bleibt unveraendert (Dimmer gehoeren dem Nutzer);
* der Hinweis im RGB-Matrix-Editor und der ``lint_show``-Befund.
"""
import os
import unittest
from types import SimpleNamespace as N

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as AS                                  # noqa: E402
from src.core.dmx.universe import Universe                       # noqa: E402
from src.core.engine.function_manager import FunctionManager    # noqa: E402
from src.core.engine.rgb_matrix import MatrixStyle, RgbMatrixInstance  # noqa: E402


def _ch(attr, nr, segment=None):
    return N(attribute=attr, channel_number=nr, default_value=0,
             highlight_value=255, ranges=[], name=attr, segment=segment)


def _geraet(attrs, segmente=None):
    """Kanaele in Reihenfolge; ``segmente`` = Zuordnung je Dimmer-Vorkommen."""
    seg = iter(segmente or ())
    out = []
    for i, a in enumerate(attrs):
        s = next(seg, None) if a == "intensity" else None
        out.append(_ch(a, i + 1, s))
    return out


def _zwei_dimmer(segmente=(None, None)):
    """Zwei Dimmer (CH1, CH2) VOR vier RGB-Koepfen, zwei eigene Weiss-Segmente
    — das synthetische Geraet aus ``test_fm46_dimmer_segment`` (fuer Hinweis
    und Lint)."""
    kanaele = [_ch("intensity", i + 1, s) for i, s in enumerate(segmente)]
    nr = len(kanaele) + 1
    for _ in range(4):
        for a in ("color_r", "color_g", "color_b"):
            kanaele.append(_ch(a, nr))
            nr += 1
    kanaele += [_ch("color_w", nr), _ch("color_w", nr + 1)]
    return kanaele


def _orbit():
    """Nachbau Fusion Orbit MKII „16 Channel" (Review-Befund): CH4 Master
    (Beam), CH6-9 RGBW Beam, CH10 Master (Ring), CH12-14 RGB Ring."""
    return _geraet(["pan", "tilt", "speed", "intensity", "shutter",
                    "color_r", "color_g", "color_b", "color_w",
                    "intensity", "shutter", "color_r", "color_g", "color_b",
                    "macro", "reset"])


def _pixelsektion():
    """Nachbau Ginamp „36 Channel": 8 RGB-Pixel, CH25 „Dimmer (RGB)" HINTER
    den Pixeln, zwei Weiss (CH30/31), CH32 „Dimmer (W)"."""
    attrs = ["color_r", "color_g", "color_b"] * 8 + ["intensity"]
    attrs += ["macro"] * 4 + ["color_w", "color_w", "intensity"]
    return _geraet(attrs)


def _gemeinsam(segmente=None):
    """Zwei Dimmer neben reinen Weiss-Abschnitten (CH1, CH3) und ein Dimmer
    vor einem Farbblock (CH5)."""
    return _geraet(["intensity", "color_w", "intensity", "color_w",
                    "intensity", "color_r", "color_g", "color_b"], segmente)


def _zwei_rgbw_teile():
    """Nachbau Robin-Tetra-Struktur: RGBW-Teil A, CH5 Dimmer, RGBW-Teil B,
    CH10 Dimmer, CH12 Dimmer vor einer RGB-Pixelsektion."""
    return _geraet(["color_r", "color_g", "color_b", "color_w", "intensity",
                    "color_r", "color_g", "color_b", "color_w", "intensity",
                    "macro", "intensity", "color_r", "color_g", "color_b"])


def _mit_kopf_dimmern():
    """Master CH1 + zwei RGB-Koepfe mit EIGENEM Dimmer (CH5, CH9, laut
    Kopf-Karte) + drei Weiss-Segmente."""
    return _geraet(["intensity", "color_r", "color_g", "color_b", "intensity",
                    "color_r", "color_g", "color_b", "intensity",
                    "color_w", "color_w", "color_w"])


def _nrn(chans):
    return [c.channel_number for c in chans]


class RegelTest(unittest.TestCase):

    def test_review_befund_orbit_nur_der_beam_dimmer(self):
        """Segment 0 oeffnet nur CH4 — NICHT CH10, den Dimmer des RGB-Rings
        (vorher: [4, 10], der Ring leuchtete in fremder Farbe mit)."""
        self.assertEqual(_nrn(AS.weiss_rueckfall_dimmer(_orbit(), 0)), [4])

    def test_dimmer_hinter_der_pixelsektion_bleibt_zu(self):
        k = _pixelsektion()
        for s in (0, 1):
            with self.subTest(segment=s):
                self.assertEqual(_nrn(AS.weiss_rueckfall_dimmer(k, s)), [32])

    def test_ohne_zuordnung_alle_freien_gemeinsam(self):
        k = _gemeinsam()
        self.assertEqual(_nrn(AS.weiss_rueckfall_dimmer(k, 0)), [1, 3])
        self.assertEqual(_nrn(AS.weiss_rueckfall_dimmer(k, 1)), [1, 3])

    def test_gemischter_abschnitt_nur_angrenzende(self):
        """Weiss in einem RGBW-Teil: nur die Dimmer an DIESEM Teil."""
        k = _zwei_rgbw_teile()
        self.assertEqual(_nrn(AS.weiss_rueckfall_dimmer(k, 0)), [5])
        self.assertEqual(_nrn(AS.weiss_rueckfall_dimmer(k, 1)), [5, 10])

    def test_mit_vollstaendiger_zuordnung_kein_rueckfall(self):
        k = _gemeinsam((0, 1, None))
        self.assertEqual(AS.weiss_rueckfall_dimmer(k, 0), [])
        self.assertEqual(AS.weiss_rueckfall_dimmer(k, 1), [])

    def test_teilzuordnung_nur_die_freien(self):
        """CH1 gehoert Segment 1 — Segment 2 oeffnet nur den freien CH3."""
        k = _gemeinsam((0, None, None))
        self.assertEqual(AS.weiss_rueckfall_dimmer(k, 0), [])
        self.assertEqual(_nrn(AS.weiss_rueckfall_dimmer(k, 1)), [3])

    def test_widerspruch(self):
        """Beide tragen Segment 1: dort fahren beide (keine Auswahl noetig),
        Segment 2 bekommt keinen — beide gehoeren laut Eintrag Segment 1."""
        k = _gemeinsam((0, 0, None))
        self.assertEqual(_nrn(AS.weiss_rueckfall_dimmer(k, 0)), [1, 3])
        self.assertEqual(AS.weiss_rueckfall_dimmer(k, 1), [])

    def test_segment_das_es_nicht_gibt_gilt_als_frei(self):
        k = _gemeinsam((0, 5, None))
        self.assertEqual(_nrn(AS.weiss_rueckfall_dimmer(k, 1)), [3])

    def test_kein_phantom_segment(self):
        k = _gemeinsam()
        for idx in (2, 9, -1, None, "x"):
            with self.subTest(idx=idx):
                self.assertEqual(AS.weiss_rueckfall_dimmer(k, idx), [])

    def test_dimmer_an_farbkoepfen_bleiben_zu(self):
        """Kopf-Dimmer (Kopf-Karte) UND ein Master vor einem reinen Farbblock
        fahren nicht — lieber zu wenig als ein fremder Teil."""
        k = _mit_kopf_dimmern()
        self.assertEqual(AS.head_channel_map(k).get("intensity"), [4, 8],
                         "Vorbedingung: die Kopf-Karte kennt CH5/CH9")
        self.assertEqual(AS.weiss_rueckfall_dimmer(k, 0), [])

    def test_einzelner_dimmer_braucht_keinen_rueckfall(self):
        k = _geraet(["intensity", "color_r", "color_g", "color_b", "color_r",
                     "color_g", "color_b", "color_w"])
        self.assertEqual(AS.weiss_rueckfall_dimmer(k, 0), [])


class _Lauf(unittest.TestCase):

    def setUp(self):
        alt = AS.get_channels_for_patched
        self.addCleanup(setattr, AS, "get_channels_for_patched", alt)

    def _lauf(self, kanaele, segmente, drive, *, inten=0.5):
        AS.get_channels_for_patched = lambda fx, k=kanaele: k
        fx = N(fid=1, universe=1, address=1, fixture_type="led_bar",
               fixture_profile_id=1, mode_name="m", channel_count=len(kanaele))
        mx = RgbMatrixInstance(name="FM46b")
        mx.style = MatrixStyle.RGB
        mx.cols, mx.rows = len(segmente), 1
        mx.fixture_grid = [None] * len(segmente)
        mx.head_grid = [None] * len(segmente)
        mx.weiss_grid = [(1, s) for s in segmente]
        mx.drive_intensity = drive
        mx.intensity = inten
        mx._render = lambda phase: [(255, 255, 255)] * len(segmente)
        fm = FunctionManager()
        fm.add(mx)
        fm.start(mx.id)
        uni = Universe(1)
        fm.tick({1: uni}, [fx], 0.02)
        return {c.channel_number: uni.get_channel(c.channel_number)
                for c in kanaele}


class RendererTest(_Lauf):

    def test_orbit_ring_bleibt_zu(self):
        """Review-Befund am Renderer: CH4 auf (vom Merge halbiert), CH10 (Ring)
        bleibt 0, das Weiss voll — kein doppeltes Dimmen."""
        werte = self._lauf(_orbit(), [0], drive=True)
        self.assertEqual(werte[4], 127)
        self.assertEqual(werte[10], 0)
        self.assertEqual(werte[9], 255)

    def test_pixelsektion(self):
        werte = self._lauf(_pixelsektion(), [0, 1], drive=True)
        self.assertEqual((werte[25], werte[32]), (0, 127))
        self.assertEqual((werte[30], werte[31]), (255, 255))

    def test_voller_master_alle_freien(self):
        werte = self._lauf(_gemeinsam(), [0, 1], drive=True, inten=1.0)
        self.assertEqual((werte[1], werte[3], werte[5]), (255, 255, 0))

    def test_ohne_drive_intensity_unveraendert(self):
        werte = self._lauf(_orbit(), [0], drive=False)
        self.assertEqual((werte[4], werte[10]), (0, 0))
        self.assertEqual(werte[9], 127, "die Matrix dimmt das Weiss selbst (FM-54)")

    def test_ohne_freien_dimmer_dimmt_die_matrix_selbst(self):
        """Kein Dimmer faehrt -> FM-54: das Weiss wird in der Matrix gedimmt."""
        werte = self._lauf(_mit_kopf_dimmern(), [0, 1, 2], drive=True)
        self.assertEqual((werte[1], werte[5], werte[9]), (0, 0, 0))
        self.assertEqual([werte[10], werte[11], werte[12]], [127, 127, 127])


class MusterPfadTest(unittest.TestCase):
    """``weiss_cell_values`` — dieselbe Antwort wie der Renderer."""

    def setUp(self):
        alt = AS.get_channels_for_patched
        self.addCleanup(setattr, AS, "get_channels_for_patched", alt)
        self.fx = N(fid=1, universe=1, address=1, fixture_type="led_bar",
                    fixture_profile_id=1, mode_name="m", head_mode="auto",
                    channel_count=36)

    def _werte(self, kanaele, segment, **kw):
        from src.core.matrix_pattern import weiss_cell_values
        AS.get_channels_for_patched = lambda fx, k=kanaele: k
        return weiss_cell_values(self.fx, segment, (255, 255, 255), **kw)

    def test_orbit(self):
        werte = self._werte(_orbit(), 0)
        self.assertEqual(werte.get(4), 255)
        self.assertNotIn(10, werte)

    def test_pixelsektion(self):
        werte = self._werte(_pixelsektion(), 1)
        self.assertEqual(werte.get(32), 255)
        self.assertNotIn(25, werte)

    def test_teilzuordnung(self):
        werte = self._werte(_gemeinsam((0, None, None)), 1)
        self.assertEqual(werte.get(3), 255)
        self.assertNotIn(1, werte, "CH1 gehoert Segment 1")

    def test_ohne_drive_intensity(self):
        werte = self._werte(_orbit(), 0, drive_intensity=False)
        self.assertNotIn(4, werte)
        self.assertNotIn(10, werte)


class EditorHinweisTest(unittest.TestCase):
    """Die Hinweiszeile im RGB-Matrix-Editor (reine Text-Funktion)."""

    def _text(self, kanaele, *, drive, weiss_grid=((1, 0),),
              style=MatrixStyle.RGB):
        from src.ui.views.rgb_matrix_view import RgbMatrixView
        selbst = N(_fixture_label=RgbMatrixView._fixture_label)
        m = N(weiss_grid=list(weiss_grid), drive_intensity=drive, style=style)
        by_fid = {1: N(fid=1, name="Leiste A")}
        return RgbMatrixView.weiss_dimmer_hint_text(
            selbst, m, by_fid, chans_of=lambda fx: kanaele)

    def test_ohne_zuordnung_mit_treiben(self):
        t = self._text(_zwei_dimmer(), drive=True)
        self.assertIn("Für Leiste A sind die Dimmer keinem Weiß-Segment "
                      "zugeordnet — alle freien Dimmer (keinem anderen Segment "
                      "und keinem Farbteil zugeordnet) werden gemeinsam "
                      "gefahren.", t)
        self.assertIn("Spalte „Weiß-Segment“", t)

    def test_ohne_zuordnung_ohne_treiben(self):
        """Neue Matrizen: ``drive_intensity=False`` — der Text darf nicht
        behaupten, die Matrix fahre die Dimmer."""
        t = self._text(_zwei_dimmer(), drive=False)
        self.assertIn("Diese Matrix fährt keine Dimmer", t)
        self.assertNotIn("gemeinsam gefahren", t)

    def test_teilzuordnung(self):
        t = self._text(_zwei_dimmer((None, 0)), drive=True)
        self.assertIn("unvollständig oder widersprüchlich", t)

    def test_still_unter_dimmer_und_shutter_stil(self):
        """Review: unter Dimmer/Shutter faehrt die Matrix die Weiss-Achse
        gar nicht (``_weiss_achse_schreiben`` steigt aus) — kein Hinweis."""
        for stil in (MatrixStyle.DIMMER, MatrixStyle.SHUTTER):
            with self.subTest(stil=stil):
                self.assertEqual(self._text(_zwei_dimmer(), drive=True,
                                            style=stil), "")
        self.assertTrue(self._text(_zwei_dimmer(), drive=True,
                                   style=MatrixStyle.RGBW))

    def test_still_wenn_alles_passt(self):
        self.assertEqual(self._text(_zwei_dimmer((1, 0)), drive=True), "")
        self.assertEqual(self._text(_zwei_dimmer(), drive=True, weiss_grid=()), "")
        self.assertEqual(self._text(_zwei_dimmer(), drive=True,
                                    weiss_grid=((2, 0),)), "",
                         "Geraet nicht gepatcht -> nichts zu sagen")


class LintBefundTest(unittest.TestCase):

    def setUp(self):
        alt = AS.get_channels_for_patched
        self.addCleanup(setattr, AS, "get_channels_for_patched", alt)

    def _befunde(self, kanaele, weiss_grid, style="RGB"):
        from src.core.capability.dimmer_check import weiss_zuordnung_befunde
        AS.get_channels_for_patched = lambda fx, k=kanaele: list(k)
        show = {"patch": [{"fid": 1, "label": "Leiste", "address": 1,
                           "channel_count": len(kanaele)}],
                "functions": [{"type": "RGBMatrix", "name": "W", "style": style,
                               "weiss_grid": weiss_grid}]}
        return weiss_zuordnung_befunde(show)

    def test_fehlende_zuordnung_wird_gemeldet(self):
        b = self._befunde(_zwei_dimmer(), [[1, 0]])
        self.assertEqual([f.code for f in b], ["WEISS-DIMMER-ZUORDNUNG"])
        self.assertEqual(b[0].severity, "warning")

    def test_still_mit_zuordnung_oder_ohne_weiss_achse(self):
        self.assertEqual(self._befunde(_zwei_dimmer((1, 0)), [[1, 0]]), [])
        self.assertEqual(self._befunde(_zwei_dimmer(), []), [])


    def test_still_unter_dimmer_stil(self):
        self.assertEqual(self._befunde(_zwei_dimmer(), [[1, 0]], "Dimmer"), [])
        self.assertEqual(self._befunde(_zwei_dimmer(), [[1, 0]], "Shutter"), [])


if __name__ == "__main__":
    unittest.main()
