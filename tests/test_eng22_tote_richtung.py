"""ENG-22: „Richtung" war bei Bewegung `bounce` ein exakter No-Op.

Ein wirkungsloses Bedienelement ist schlimmer als keines: man dreht daran,
nichts passiert, und man sucht den Fehler woanders.

★★ **Der No-Op ist beweisbar, nicht messgluecksabhaengig.** ``_render`` wendet
die Richtung ausschliesslich als ``p = -phase`` an (`rgb_matrix.py`), und beide
Bounce-Bahnformeln sind **gerade Funktionen** — sie liefern fuer ``p`` und
``-p`` denselben Wert:

* CHASE ``head = span - abs((int(p) % (2*span)) - span)``
* WIPE  ``tt = (p % (2*length)) / length; t = tt if tt <= 1 else 2 - tt``

**Gemessen:** CHASE/bounce 0 von 500 Frames verschieden. Gegenprobe
CHASE/normal 500 von 500.

⚠️ **Korrektur an meiner eigenen Verifikationsnotiz.** Ich hatte notiert, die
Rest-Unterschiede haetten mit ``edge_fade`` zu tun und laegen bei 1 LSB. Beim
Nachmessen vor dem Bauen war es umgekehrt und schlimmer: WIPE/bounce **ohne**
``edge_fade`` ergibt 8 von 500 Frames mit **voller Kanaldifferenz 255** — ein
ganzer Pixel kippt die Farbe. Nachgerechnet ist es dennoch kein Effekt, sondern
**Fliesskomma-Rauschen**: ``(-p) % 2L`` und ``2L - (p % 2L)`` unterscheiden sich
um ~1e-16, und der harte Vergleich ``frac < t`` verstaerkt das auf einen ganzen
Pixel. Mit ``edge_fade`` ist der Uebergang weich, dort bleiben 1 LSB (18/500).
*Der Regler steuert nicht — er wuerfelt.*

⚠️ **Und die zweite Haelfte des urspruenglichen Kriteriums („oder die
Einstellung verschwindet") stand auf falscher Praemisse.** Gemessen wirkt die
Richtung sehr wohl:

    Chase  bounce      —                  0/500
    Chase  bounce      color_cycle      360/500
    Chase  center_out  —                341/500
    Chase  outside_in  —                429/500
    Wipe   center_out  —                398/500

Der Rundenzaehler ``int(p) // (...)`` ist eine Floor-Division und damit **nicht**
gerade. Wer den Regler pauschal loeschte, kippte bestehende
Bounce-plus-Farbwechsel-Shows.

**Deshalb: ausblenden statt loeschen, und nur dort, wo es nachweislich folgenlos
ist.** ``direction`` liegt nicht in ``self.params``, ``visible_specs`` filtert
nur params-Keys, und ``to_dict`` schreibt den Wert unveraendert weiter — eine
ausgeblendete Richtung bleibt erhalten und wirkt sofort wieder, sobald die
Bewegung wechselt.

★ Das Haus fuehrt dieses Muster bereits: ``runner_count`` wird bei bounce per
``when`` ausgeblendet, „statt tote Regler zu zeigen". Die Richtung wurde dort
schlicht vergessen.
"""
from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.engine.rgb_matrix import (  # noqa: E402
    MatrixStyle, RgbAlgorithm, RgbMatrixInstance)
from src.core.engine.rgb_matrix_meta import ALGO_META, richtung_wirkt  # noqa: E402

FRAMES = 500
SCHRITT = 0.05


def _matrix(algo, params, style=MatrixStyle.RGB, cols=6, rows=1):
    m = RgbMatrixInstance(name="X")
    m.algorithm = algo
    m.style = style
    m.cols, m.rows = cols, rows
    m.params = dict(params)
    return m


def _verschiedene_frames(algo, params, **kw):
    """(Anzahl unterschiedlicher Frames, groesste Kanaldifferenz)."""
    def lauf(richtung):
        m = _matrix(algo, params, **kw)
        m.direction = richtung
        return [m._render(i * SCHRITT) for i in range(FRAMES)]
    a, b = lauf("forward"), lauf("reverse")
    anders = [(x, y) for x, y in zip(a, b) if x != y]
    if not anders:
        return 0, 0
    gross = max(abs(u - v) for fa, fb in anders
                for pa, pb in zip(fa, fb) for u, v in zip(pa, pb))
    return len(anders), gross


class DieRichtungIstBeiBounceWirkungslosTest(unittest.TestCase):

    def test_chase_bounce_ist_ein_exakter_no_op(self):
        """★★★ Der Kern, und er ist exakt: nicht „fast gleich", sondern gleich."""
        anders, _ = _verschiedene_frames(RgbAlgorithm.CHASE, {"movement": "bounce"})
        self.assertEqual(anders, 0, "die Richtung wirkt doch — Annahme pruefen")

    def test_auch_auf_einer_flaeche(self):
        """Nicht nur in einer Reihe — sonst haenge die Aussage an der Geometrie."""
        anders, _ = _verschiedene_frames(RgbAlgorithm.CHASE, {"movement": "bounce"},
                                         cols=8, rows=4)
        self.assertEqual(anders, 0)

    def test_wipe_bounce_unterscheidet_sich_nur_durch_rundung(self):
        """★★ Hier ist die Messung allein irrefuehrend: 8 von 500 Frames mit
        voller Kanaldifferenz 255 sehen nach Wirkung aus. Nachgerechnet sind es
        Fliesskomma-Reste, die ein harter Schwellenvergleich verstaerkt."""
        L = 5.0        # length bei cols=6

        def t_bounce(p):
            tt = (p % (2 * L)) / L
            return tt if tt <= 1.0 else (2.0 - tt)

        groesster = max(abs(t_bounce(i * SCHRITT) - t_bounce(-i * SCHRITT))
                        for i in range(FRAMES))
        self.assertLess(groesster, 1e-9,
                        "die Bahnkurve unterscheidet sich WIRKLICH — dann ist "
                        "die Richtung kein No-Op und dieser Fix ist falsch")

    def test_die_bahnformeln_sind_gerade_funktionen(self):
        """★ Der Beweis statt der Stichprobe — fuer beide Formeln, ueber einen
        Bereich, der mehrere Umkehrpunkte enthaelt."""
        span, L = 5, 5.0
        for i in range(-400, 400):
            p = i * 0.37                      # krumm, damit keine Kanten getroffen werden
            with self.subTest(p=round(p, 2)):
                chase = lambda x: span - abs((int(x) % (2 * span)) - span)  # noqa: E731
                self.assertEqual(chase(p), chase(-p))


class WoDieRichtungSEHRWOHLWirktTest(unittest.TestCase):
    """★★★ Die Gegenproben — und der Grund, warum „Regler loeschen" falsch
    gewesen waere. Sie sind wichtiger als der Kern: ein zu breiter Fix nimmt
    bestehenden Shows eine Funktion weg."""

    def test_normal_wirkt(self):
        anders, _ = _verschiedene_frames(RgbAlgorithm.CHASE, {"movement": "normal"})
        self.assertEqual(anders, FRAMES)

    def test_center_out_und_outside_in_wirken(self):
        for mv in ("center_out", "outside_in"):
            with self.subTest(movement=mv):
                anders, gross = _verschiedene_frames(RgbAlgorithm.CHASE,
                                                     {"movement": mv})
                self.assertGreater(anders, FRAMES // 2)
                self.assertEqual(gross, 255)

    def test_bounce_MIT_rundenzaehler_wirkt(self):
        """★★ Der Rundenzaehler ist eine Floor-Division und damit nicht gerade:
        die Richtung dreht die Farbfolge um. Genau hier haette ein pauschales
        Loeschen bestehende Shows gekippt."""
        anders, gross = _verschiedene_frames(
            RgbAlgorithm.CHASE, {"movement": "bounce", "color_cycle": True})
        self.assertGreater(anders, FRAMES // 2)
        self.assertEqual(gross, 255)


class DieRegelStehtNurEinmalTest(unittest.TestCase):
    """Review-Checkliste 17: drei Stellen brauchen die Antwort, es gibt eine."""

    def _matrix_mit(self, params, style=MatrixStyle.RGB):
        return _matrix(RgbAlgorithm.CHASE, params, style=style)

    def test_die_regel_trifft_genau_bounce_ohne_rundenzaehler(self):
        faelle = [
            ({"movement": "normal"}, True),
            ({"movement": "center_out"}, True),
            ({"movement": "outside_in"}, True),
            ({"movement": "bounce"}, False),
            ({"movement": "bounce", "color_cycle": True}, True),
            ({"movement": "bounce", "dimmer_cycle": True}, True),
        ]
        for params, erwartet in faelle:
            with self.subTest(params=params):
                self.assertIs(richtung_wirkt(RgbAlgorithm.CHASE, params), erwartet)

    def test_alle_drei_anzeigen_antworten_GLEICH(self):
        """★★ Ohne das hier koennte der Editor das Feld verstecken, waehrend die
        VC den Knopf weiter anbietet — genau die Sorte Knopf, die stumm nichts
        tut (dieselbe Klasse wie ENG-23)."""
        for params in ({"movement": "normal"}, {"movement": "bounce"},
                       {"movement": "bounce", "color_cycle": True},
                       {"movement": "center_out"}):
            with self.subTest(params=params):
                m = self._matrix_mit(params)
                regel = richtung_wirkt(m.algorithm, m.params)
                in_params = any(s.key == "direction" for s in m.list_params())
                in_aktionen = any(k == "reverse_direction"
                                  for k, _ in m.list_actions())
                self.assertEqual((in_params, in_aktionen), (regel, regel))

    def test_ohne_movement_gilt_die_vorgabe_des_renderers(self):
        """★ Eine Anzeige, die andere Vorgaben annimmt als der Code, den sie
        beschreibt, beschreibt etwas anderes. Der Renderer liest
        ``params.get("movement", "normal")``."""
        self.assertTrue(richtung_wirkt(RgbAlgorithm.CHASE, {}))
        self.assertTrue(richtung_wirkt(RgbAlgorithm.CHASE, None))

    def test_algorithmen_ohne_richtung_bleiben_ohne(self):
        ohne = [a for a, meta in ALGO_META.items() if not meta.direction]
        self.assertTrue(ohne, "Vorbedingung: es gibt solche Algorithmen")
        for a in ohne:
            with self.subTest(algo=a.value):
                self.assertFalse(richtung_wirkt(a, {"movement": "normal"}))


class DerWertWirdNichtUEBERSCHRIEBENTest(unittest.TestCase):
    """★★★ Ausblenden ist harmlos, ueberschreiben waere es nicht. Ein Nutzer,
    der auf „reverse" gestellt hat und voruebergehend auf bounce wechselt, muss
    seine Einstellung zurueckbekommen."""

    def test_die_ausgeblendete_richtung_bleibt_gespeichert(self):
        m = _matrix(RgbAlgorithm.CHASE, {"movement": "bounce"})
        m.direction = "reverse"
        self.assertFalse(richtung_wirkt(m.algorithm, m.params))
        self.assertEqual(m.direction, "reverse")
        self.assertEqual(m.to_dict().get("direction"), "reverse")

    def test_das_ABFRAGEN_der_anzeigen_aendert_nichts(self):
        """★★★ Von der Mutationsprobe gefunden: der Test darueber prueft den
        WERT, betritt aber nie den Pfad, der ihn ueberschreiben koennte. Ein
        ``self.direction = "forward"`` in ``list_params`` blieb deshalb
        unbemerkt — und genau das waere der Schaden: die Einstellung des
        Nutzers ginge beim blossen OEFFNEN des Editors verloren.

        Wieder dieselbe Klasse wie bei ENG-23: eine Probe, die ihren Gegenstand
        nicht erreicht, meldet „alles gut"."""
        m = _matrix(RgbAlgorithm.CHASE, {"movement": "bounce"})
        m.direction = "reverse"
        for _ in range(3):
            m.list_params()
            m.list_actions()
            richtung_wirkt(m.algorithm, m.params)
        self.assertEqual(m.direction, "reverse",
                         "das blosse Anzeigen hat die Einstellung geaendert")
        self.assertEqual(m.to_dict().get("direction"), "reverse")

    def test_auch_bei_wirksamer_richtung_aendert_das_abfragen_nichts(self):
        """Die Gegenrichtung — kein Pfad darf den Wert anfassen."""
        m = _matrix(RgbAlgorithm.CHASE, {"movement": "normal"})
        m.direction = "reverse"
        m.list_params(); m.list_actions()
        self.assertEqual(m.direction, "reverse")

    def test_sie_wirkt_sofort_wieder_wenn_die_bewegung_wechselt(self):
        m = _matrix(RgbAlgorithm.CHASE, {"movement": "bounce"})
        m.direction = "reverse"
        m.params["movement"] = "normal"
        self.assertTrue(richtung_wirkt(m.algorithm, m.params))
        vorwaerts = _matrix(RgbAlgorithm.CHASE, {"movement": "normal"})
        vorwaerts.direction = "forward"
        self.assertNotEqual(m._render(1.3), vorwaerts._render(1.3),
                            "die zurueckgekehrte Richtung wirkt nicht")

    def test_das_speichern_ueberlebt_einen_ladevorgang(self):
        m = _matrix(RgbAlgorithm.CHASE, {"movement": "bounce"})
        m.direction = "reverse"
        geladen = RgbMatrixInstance.from_dict(m.to_dict())
        self.assertEqual(geladen.direction, "reverse")


if __name__ == "__main__":
    unittest.main()
