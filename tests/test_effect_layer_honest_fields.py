"""BH-PHASEOFF — der Layer-Editor bietet nichts mehr an, das nichts tut.

Zwei Befunde, dieselbe Klasse: ein Bedienelement behauptet Wirkung, wo keine ist.

1. **``PHASE_OFFSET`` war ein No-Op.** ``process`` gibt den Eingang unveraendert
   zurueck (`return prev  # Phasen werden in folgenden Layern angewandt`) — die
   folgenden Layer wissen davon aber nichts. Was der Typ verspricht, kann das
   Feld ``fixture_phase_step`` auf JEDEM schwingenden Layer laengst: es geht
   direkt in ``phase_rad`` ein. Ihn „richtig" zu bauen haette einen ZWEITEN Weg
   zum selben Ziel geschaffen und die Signatur der ganzen Pipeline geaendert.
   Er wird deshalb nicht mehr **angeboten** — bleibt aber ladbar, damit
   Bestands-Shows unveraendert oeffnen.

2. **Das Eigenschaften-Formular zeigte alle acht Felder fuer jeden Typ.** Ein
   Clamp bot Amplitude und Frequenz an, die es nie liest.

Der wichtigste Test hier ist der letzte: er haelt die Feld-Karte gegen das echte
Verhalten von ``process``, statt gegen meine Behauptung darueber. Eine Karte, die
nur mit sich selbst uebereinstimmt, beweist nichts.
"""
from __future__ import annotations

import math
import os
import random
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.effect_layers import (EffectLayer, LayerType,   # noqa: E402
                                           offered_types, used_fields)

_ALLE_FELDER = ("amplitude", "frequency", "phase", "offset", "value",
                "min_val", "max_val", "fixture_phase_step")


class AngeboteneTypenTest(unittest.TestCase):

    def test_phase_offset_wird_nicht_mehr_angeboten(self):
        self.assertNotIn(LayerType.PHASE_OFFSET, offered_types())

    def test_alle_anderen_typen_bleiben_waehlbar(self):
        self.assertEqual(set(offered_types()),
                         set(LayerType) - {LayerType.PHASE_OFFSET})

    def test_bestands_shows_laden_ihn_weiter(self):
        """Nicht mehr anbieten heisst nicht wegnehmen: eine gespeicherte Show
        mit einem PHASE_OFFSET-Layer muss unveraendert oeffnen."""
        l = EffectLayer.from_dict({"type": "PhaseOffset", "amplitude": 2.0})
        self.assertEqual(l.type, LayerType.PHASE_OFFSET)
        self.assertEqual(l.process(0.42, t=1.0, fixture_index=3), 0.42,
                         "er tat vorher nichts und tut weiterhin nichts — das "
                         "Verhalten von Bestands-Shows aendert sich NICHT")


class FeldKarteTest(unittest.TestCase):

    def test_oszillatoren_nutzen_die_wellen_felder(self):
        for lt in (LayerType.SIN, LayerType.COS, LayerType.TRIANGLE,
                   LayerType.SAW, LayerType.SQUARE):
            with self.subTest(lt=lt):
                self.assertEqual(
                    used_fields(lt),
                    {"amplitude", "frequency", "phase", "offset",
                     "fixture_phase_step"})

    def test_clamp_bietet_keine_amplitude_mehr_an(self):
        self.assertEqual(used_fields(LayerType.CLAMP), {"min_val", "max_val"})

    def test_phase_offset_hat_nichts_einzustellen(self):
        self.assertEqual(used_fields(LayerType.PHASE_OFFSET), set())

    def test_jeder_typ_ist_in_der_karte(self):
        """Sonst faellt ein neuer Layer-Typ still auf „keine Felder" zurueck und
        waere im Editor gar nicht einstellbar."""
        for lt in LayerType:
            with self.subTest(lt=lt):
                self.assertIn(lt, {t for t in LayerType if used_fields(t) is not None})

    # ── der eigentliche Beweis ───────────────────────────────────────────────

    def test_karte_stimmt_mit_dem_echten_verhalten_ueberein(self):
        """Feld fuer Feld gemessen: aendert sich die Ausgabe, wenn ich es
        verstelle? Genau dann gehoert es in die Karte.

        Das ist der Unterschied zwischen „die Karte sagt X" und „der Code tut X".
        """
        # Die Basis darf NICHT entartet sein — mein erster Versuch hatte
        # offset=value=0, womit MAPs Ausgangsbereich 0..0 ist und dort auch
        # min_val/max_val nichts bewirken KOENNEN. Ein Test, der so misst,
        # meldet einen Fehler in der Karte, wo der Fehler in der Messung liegt.
        basis = dict(amplitude=0.8, frequency=1.3, phase=0.17, offset=0.23,
                     value=0.71, min_val=0.11, max_val=0.89,
                     fixture_phase_step=0.29)
        # Viele Stuetzstellen ueber eine ganze Periode: SQUARE etwa zeigt eine
        # Frequenzaenderung nur, wenn eine davon die Flanke ueberquert. Und
        # ``prev`` muss AUSSERHALB der Clamp-Grenzen liegen koennen — lagen alle
        # Proben dazwischen, konnte max_val gar nichts bewirken und die Messung
        # meldete faelschlich „unbenutzt" (dieselbe Falle wie CDX-18: die Probe
        # muss den unterscheidenden Pfad ueberhaupt erreichen).
        proben = [(prev, t, idx)
                  for prev in (-0.4, 0.15, 0.62, 1.4)
                  for t in (0.0, 0.07, 0.19, 0.31, 0.44, 0.58, 0.73, 0.91)
                  for idx in (0, 3)]

        def _wert(layer, prev, t, idx):
            # RANDOM ist nur mit gleichem Startwert vergleichbar — sonst misst
            # man die Zufallsquelle statt das Feld.
            random.seed(1234)
            return layer.process(prev, t, idx)

        for lt in LayerType:
            for feld in _ALLE_FELDER:
                with self.subTest(lt=lt, feld=feld):
                    a = EffectLayer(type=lt, **basis)
                    b = EffectLayer(type=lt, **{**basis, feld: basis[feld] + 0.37})
                    wirkt = any(
                        not math.isclose(_wert(a, *p), _wert(b, *p),
                                         rel_tol=1e-9, abs_tol=1e-9)
                        for p in proben)
                    self.assertEqual(
                        wirkt, feld in used_fields(lt),
                        f"{lt.value}/{feld}: gemessene Wirkung={wirkt}, "
                        f"Karte sagt {feld in used_fields(lt)}")


class EditorTest(unittest.TestCase):
    """Kommt es auch am Formular an?"""

    def _editor(self):
        from PySide6.QtWidgets import QApplication
        from src.core.engine.effect_func import LayeredEffect
        from src.ui.views.effect_layer_editor import EffectLayerEditor
        QApplication.instance() or QApplication([])
        eff = LayeredEffect("Test")
        ed = EffectLayerEditor(eff)
        self.addCleanup(ed.deleteLater)
        return eff, ed

    def test_auswahlliste_bietet_phase_offset_nicht_an(self):
        _eff, ed = self._editor()
        angeboten = [ed._add_combo.itemText(i)
                     for i in range(ed._add_combo.count())]
        self.assertNotIn(LayerType.PHASE_OFFSET.value, angeboten)
        self.assertIn(LayerType.SIN.value, angeboten)

    def test_clamp_zeigt_nur_min_und_max(self):
        eff, ed = self._editor()
        eff.layers.append(EffectLayer(type=LayerType.CLAMP))
        ed._refresh()
        ed._list.setCurrentRow(0)

        sichtbar = {attr for attr, spin in ed._prop_rows.items()
                    if not spin.isHidden()}
        self.assertEqual(sichtbar, {"min_val", "max_val"})

    def test_sinus_zeigt_die_wellen_felder(self):
        eff, ed = self._editor()
        eff.layers.append(EffectLayer(type=LayerType.SIN))
        ed._refresh()
        ed._list.setCurrentRow(0)

        sichtbar = {attr for attr, spin in ed._prop_rows.items()
                    if not spin.isHidden()}
        self.assertEqual(sichtbar, {"amplitude", "frequency", "phase",
                                    "offset", "fixture_phase_step"})

    def test_wechsel_des_layers_zieht_die_felder_nach(self):
        """Sonst stuenden nach dem Klick auf einen anderen Layer noch die Felder
        des vorigen da — schlimmer als zu viele Felder, weil sie dann zum
        falschen Layer zu gehoeren scheinen."""
        eff, ed = self._editor()
        eff.layers.append(EffectLayer(type=LayerType.SIN))
        eff.layers.append(EffectLayer(type=LayerType.CLAMP))
        ed._refresh()

        ed._list.setCurrentRow(0)
        self.assertFalse(ed._prop_rows["amplitude"].isHidden())
        ed._list.setCurrentRow(1)
        self.assertTrue(ed._prop_rows["amplitude"].isHidden())


if __name__ == "__main__":
    unittest.main()
