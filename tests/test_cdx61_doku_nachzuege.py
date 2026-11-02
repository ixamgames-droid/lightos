"""CDX-61 — Codex-Doku-Befunde zu #1166, #1173, #1192, #1193, #1197, #1205.

Codex bemaengelte an gemergten PRs, dass die Anleitungen die geaenderte
Bedienung nicht nennen. Jeder Test haelt eine kurze, eindeutige Textmarke
fest und prueft dieselbe Marke gegen den Quelltext, damit die Doku nicht
etwas festschreibt, das der Code nicht (mehr) zeigt. Rein textuell — es wird
nichts aus ``src`` importiert.
"""
from __future__ import annotations

import os
import re
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _lies(*teile: str) -> str:
    with open(os.path.join(_REPO, *teile), encoding="utf-8") as f:
        return f.read()


def _flach(text: str) -> str:
    return re.sub(r"\s+", " ", text)


class SpeedDialResetTest(unittest.TestCase):
    """#1166 (ENG-32) / #1173 (ENG-44): X und Faktor-Set-Wechsel landen auf der
    Gitterstufe naechst 1×; im Multiplier-Ziel zaehlt das Gitter, nicht das Feld."""

    SRC = ("src", "ui", "virtualconsole", "vc_speedial.py")

    def test_code_hat_das_verhalten(self):
        src = _lies(*self.SRC)
        self.assertIn("def _reset_target(self)", src)
        self.assertIn("self._active_factor = self._reset_target()", src)
        self.assertIn("self._mult = float(self._active_factor)", src)
        # CDX-62: Grundwert gemerkt (_FREE_RUN_BASIS), Verhaeltnis bleibt gleich
        self.assertIn("basis = old_speed / old_mult", src)
        self.assertIn('effect_live.set_param("speed", basis * new_mult, fid)', src)

    def test_speed_anleitung(self):
        doc = _flach(_lies("docs", "anleitung_speed", "ANLEITUNG_SPEED.md"))
        self.assertIn("springt `X` auf die Stufe, die `1×` am nächsten liegt", doc)

    def test_widget_anleitung_de(self):
        doc = _flach(_lies("docs", "anleitung_vc_widgets", "05_speed_dial.md"))
        self.assertIn("auf die Stufe, die `1×` am nächsten liegt", doc)
        self.assertIn("dort gilt beim OK der im Faktor-Gitter markierte Faktor", doc)
        self.assertIn("Steht der aktive Faktor nach dem OK nicht mehr im Set", doc)
        self.assertIn("ändert der Dial seine eigene Geschwindigkeit im selben Verhältnis", doc)

    def test_widget_anleitung_en(self):
        doc = _flach(_lies("docs", "anleitung_vc_widgets", "05_speed_dial.en.md"))
        self.assertIn("to the step closest to `1×`", doc)
        self.assertIn("on OK the factor marked in the factor grid applies", doc)
        self.assertIn("If the active factor is no longer in the set after OK", doc)
        self.assertIn("changes its own speed in the same ratio", doc)


class PanTiltMitteTest(unittest.TestCase):
    """#1192 (UI-77): Mitte mit Komma/Punkt, zwei Nachkommastellen, 0,5er-Schritt."""

    def test_code(self):
        src = _lies("src", "ui", "views", "patch_view.py")
        for marke in ('"Pan-Mitte (DMX):"', '"Tilt-Mitte (DMX):"',
                      "sp.setDecimals(2)", "sp.setSingleStep(0.5)",
                      'text.replace(".", self.locale().decimalPoint())'):
            self.assertIn(marke, src)

    def test_anleitung(self):
        doc = _flach(_lies("docs", "anleitung_einmessen", "ANLEITUNG_EINMESSEN.md"))
        self.assertIn("**Pan-Mitte (DMX)** / **Tilt-Mitte (DMX)**", doc)
        self.assertIn("bis zu zwei Nachkommastellen", doc)
        self.assertIn("mit Komma oder Punkt", doc)
        self.assertIn("0,5er-Schritten", doc)


class EfxLaserBeschriftungTest(unittest.TestCase):
    """#1193 (LAS-29): reine Laser-Ziele heissen X/Y, 16-bit ausgeblendet."""

    def test_code(self):
        src = _lies("src", "ui", "views", "efx_view.py")
        for marke in ('"Breite (X-Hub):"', '"Höhe (Y-Hub):"', '"Zentrum X:"',
                      '"Zentrum Y:"', '"um aktuelle X/Y-Position"',
                      '"Pan/Tilt über pan_fine/tilt_fine"', '"16-bit:"',
                      "self._bit16_chk.setVisible(not laser)"):
            self.assertIn(marke, src)

    def test_anleitung(self):
        doc = _flach(_lies("docs", "anleitung_efx", "ANLEITUNG_EFX.md"))
        for marke in ("**Breite (X-Hub)** / **Höhe (Y-Hub)**",
                      "**Zentrum X** / **Zentrum Y**",
                      "**um aktuelle X/Y-Position**",
                      "**Pan/Tilt über pan_fine/tilt_fine**",
                      "Bei gemischten Zielen"):
            self.assertIn(marke, doc)


class VizPositionOhneAuswahlTest(unittest.TestCase):
    """#1197 (VIZ-76): gesperrt ohne Auswahl, Platzierungswerte bei ungesetztem Geraet."""

    def test_code(self):
        src = _lies("src", "ui", "visualizer", "visualizer_window.py")
        self.assertIn('_POS_TITEL = "Position && Ausrichtung"', src)
        self.assertIn('" — kein Gerät gewählt"', src)
        self.assertIn('" — Platzierungswerte"', src)
        self.assertIn("box.setEnabled(gewaehlt)", src)

    def test_anleitung(self):
        doc = _flach(_lies("docs", "anleitung_3d_visualizer_2026", "ANLEITUNG_3D_BUEHNE.md"))
        self.assertIn("„Position & Ausrichtung — kein Gerät gewählt“", doc)
        self.assertIn("„Position & Ausrichtung — Platzierungswerte“", doc)
        self.assertIn("ist der Bereich gesperrt", doc)


class LaserEinzelneKanaeleTest(unittest.TestCase):
    """#1205 (LAS-43): je Kanal ein Regler statt A/B ohne echte zweite Mustergruppe."""

    def test_code(self):
        src = _lies("src", "ui", "views", "laser_view.py")
        for marke in ('QGroupBox("Einzelne Kanäle")', 'f"Kanal {nr} · {row_label(ch)}"',
                      'QGroupBox("Mustergruppe")', '("Gruppe A", "A")',
                      '("Gruppe B", "B")', '("A + B", "AB")',
                      "return len(doppelt) >= 2 and len(set(doppelt)) == 1"):
            self.assertIn(marke, src)

    def test_anleitung(self):
        doc = _flach(_lies("docs", "anleitung_laser", "ANLEITUNG_LASER.md"))
        for marke in ("**„Einzelne Kanäle“**", "„Kanal 1 · Mode“",
                      "keine Mustergruppen", "**„Mustergruppe“**",
                      "**Gruppe A**, **Gruppe B** und **A + B**",
                      "jedes gleich oft"):
            self.assertIn(marke, doc)


if __name__ == "__main__":
    unittest.main()
