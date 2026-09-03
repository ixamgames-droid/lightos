"""OUT-55 — `invert_pan`/`invert_tilt`/`swap_pan_tilt` gelten fuer ALLE Koepfe.

`apply_pan_tilt_orientation` behandelte ausschliesslich die **blanken**
Schluessel `pan`, `tilt`, `pan_fine`, `tilt_fine`. Die Mehrkopf-Schluessel
`pan#1`, `tilt#1` … liefen unveraendert durch.

**Gemessen (Fund 2026-08-30, bestaetigt 2026-09-03):** mit `invert_pan=True` und
`{'pan': 10, 'pan#1': 10}` kam `{'pan': 245, 'pan#1': 10}` heraus. An einem
Spider oder einer Mover-Bar mit gesetztem Invert fuhr **Kopf 0 richtig herum und
jeder weitere spiegelverkehrt** — im Programmer-Flush wie im Render-Pfad.

`efx.py` faellt nicht darauf herein: es schickt jeden Kopf **einzeln** mit
blanken Schluesseln durch dieselbe Funktion — genau deshalb fiel es dort nie auf.

★★ **Warum beide Richtungen zusammen nachgezogen werden mussten.** Es gibt eine
Zwillingsfunktion `unapply_pan_tilt_orientation`: der 3D-Visualizer speist sich
aus dem GESENDETEN Frame und nimmt die Drehung der Ausgabestufe zurueck, damit
das Bild die Richtung des physischen Geraets zeigt (VIZ-55). Sie hatte dieselbe
Luecke. Waere nur die Vorwaertsrichtung gefixt worden, staende der Draht fuer die
Koepfe ab 1 richtig, **das Bild aber spiegelverkehrt** — die Klasse „zwei
gekoppelte Fehler heben sich auf", die VIZ-55 Slice 1 schon einmal gekostet hat.
Der Rundlauf-Test unten ist der Waechter dagegen.
"""
from __future__ import annotations
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import (apply_pan_tilt_orientation,
                                unapply_pan_tilt_orientation)


def _fx(**flags):
    basis = {"invert_pan": False, "invert_tilt": False, "swap_pan_tilt": False}
    basis.update(flags)
    return SimpleNamespace(**basis)


class JederKopfDrehtMitTest(unittest.TestCase):

    def test_zwei_koepfe__der_gemessene_fall(self):
        """Vorher: `{'pan': 245, 'pan#1': 10}` — Kopf 1 blieb stehen."""
        aus = apply_pan_tilt_orientation(_fx(invert_pan=True),
                                         {"pan": 10, "pan#1": 10})
        self.assertEqual(aus, {"pan": 245, "pan#1": 245})

    def test_vier_koepfe__mover_bar(self):
        ein = {f"pan#{i}": 10 for i in range(1, 4)} | {"pan": 10}
        aus = apply_pan_tilt_orientation(_fx(invert_pan=True), ein)
        self.assertEqual(set(aus.values()), {245},
                         f"nicht alle Koepfe gedreht: {aus}")

    def test_tilt_getrennt_von_pan(self):
        """Nur `invert_tilt`: Pan darf sich auf KEINEM Kopf aendern."""
        aus = apply_pan_tilt_orientation(
            _fx(invert_tilt=True),
            {"pan": 10, "pan#1": 10, "tilt": 10, "tilt#1": 10})
        self.assertEqual(aus, {"pan": 10, "pan#1": 10,
                               "tilt": 245, "tilt#1": 245})

    def test_feinkanal_je_kopf_als_16bit_paar(self):
        """Ein Kopf mit Feinkanal wird als 16-Bit-Wert gedreht, nicht byteweise —
        sonst springt der Kopf um bis zu einem groben Schritt daneben."""
        aus = apply_pan_tilt_orientation(
            _fx(invert_pan=True),
            {"pan": 10, "pan_fine": 0, "pan#1": 10, "pan_fine#1": 0})
        self.assertEqual(aus, {"pan": 245, "pan_fine": 255,
                               "pan#1": 245, "pan_fine#1": 255})

    def test_swap_je_kopf(self):
        aus = apply_pan_tilt_orientation(
            _fx(swap_pan_tilt=True),
            {"pan": 1, "tilt": 2, "pan#1": 3, "tilt#1": 4})
        self.assertEqual(aus, {"pan": 2, "tilt": 1, "pan#1": 4, "tilt#1": 3})


class BestandsverhaltenTest(unittest.TestCase):
    """Was sich NICHT aendern darf — sonst repariert der Fix das eine und
    zerstoert das andere."""

    def test_ohne_flag_dasselbe_objekt(self):
        """Kein Overhead im heissen Render-Pfad: ohne Flag kommt das ORIGINAL
        zurueck, nicht eine Kopie."""
        ein = {"pan": 10, "pan#1": 10}
        self.assertIs(apply_pan_tilt_orientation(_fx(), ein), ein)

    def test_schicht_ohne_pan_tilt_unveraendert(self):
        ein = {"color_r": 255, "intensity": 200}
        self.assertIs(apply_pan_tilt_orientation(_fx(invert_pan=True), ein), ein)

    def test_efx_weg_bleibt_wie_er_war(self):
        """`efx.py` schickt jeden Kopf EINZELN mit blanken Schluesseln durch —
        deshalb fiel der Fehler dort nie auf, und deshalb muss dieser Weg
        byte-genau gleich bleiben."""
        aus = apply_pan_tilt_orientation(_fx(invert_pan=True), {"pan": 10})
        self.assertEqual(aus, {"pan": 245})

    def test_kaputter_wert_auf_einem_kopf_stoppt_nichts(self):
        """P9: ein ungueltiger Wert (OSC/Web/MIDI) darf den Render-Thread nicht
        anhalten — er faellt heraus, der Rest laeuft."""
        aus = apply_pan_tilt_orientation(_fx(invert_pan=True),
                                         {"pan": 10, "pan#1": None})
        self.assertEqual(aus.get("pan"), 245)
        self.assertNotIn("pan#1", aus)


class RundlaufTest(unittest.TestCase):
    """★★ Der Waechter gegen „zwei gekoppelte Fehler heben sich auf": was die
    Ausgabestufe dreht, muss der Visualizer exakt zurueckdrehen — fuer JEDEN
    Kopf."""

    FAELLE = [
        ("nur invert_pan", {"invert_pan": True}),
        ("nur invert_tilt", {"invert_tilt": True}),
        ("nur swap", {"swap_pan_tilt": True}),
        ("swap UND invert_pan", {"swap_pan_tilt": True, "invert_pan": True}),
        ("alles zusammen", {"swap_pan_tilt": True, "invert_pan": True,
                            "invert_tilt": True}),
    ]

    SCHICHT = {"pan": 10, "tilt": 200, "pan_fine": 7, "tilt_fine": 3,
               "pan#1": 40, "tilt#1": 90, "pan_fine#1": 128, "tilt_fine#1": 64,
               "pan#2": 250, "tilt#2": 5}

    def test_hin_und_zurueck_ist_die_identitaet(self):
        for name, flags in self.FAELLE:
            with self.subTest(fall=name):
                fx = _fx(**flags)
                draht = apply_pan_tilt_orientation(fx, self.SCHICHT)
                zurueck = unapply_pan_tilt_orientation(fx, draht)
                self.assertEqual(zurueck, self.SCHICHT,
                                 f"{name}: der Rueckweg trifft das Modell nicht")

    def test_der_draht_unterscheidet_sich_ueberhaupt(self):
        """Sonst waere der Rundlauf oben trivial gruen — die Identitaet ist nur
        eine Aussage, wenn dazwischen wirklich etwas passiert."""
        fx = _fx(invert_pan=True)
        self.assertNotEqual(apply_pan_tilt_orientation(fx, self.SCHICHT),
                            self.SCHICHT)


if __name__ == "__main__":
    unittest.main()
