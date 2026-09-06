"""ENG-19: ein Attribut, das die Ziel-Cue nicht nennt, SPRANG am Fade-Ende.

Zwei Haelften desselben Uebergangs beantworteten dieselbe Frage verschieden —
Review-Checkliste 17, und zwar innerhalb EINER Methode:

* ``_blend`` (der ganze Fade): ein im Ziel fehlendes Attribut **haelt** seinen
  Wert (``tv = to_f.get(attr, fv)``).
* der Endzweig (``raw >= 1.0``): er gab nur ``to_vals`` zurueck — das Attribut
  fiel **weg**.

**Gemessen vor dem Fix**, Cue 1 ``{intensity: 255, color_r: 0}`` → Cue 2 nennt
nur ``{color_r: 255}``::

    0.000 -> {'color_r': 0,   'intensity': 255}
    0.500 -> {'color_r': 127, 'intensity': 255}
    0.999 -> {'color_r': 254, 'intensity': 255}
    1.000 -> {'color_r': 255}          <- schlagartig weg

★★★ **Warum HALTEN und nicht „auf den Default fahren"** — der Backlog-Eintrag
schlug Letzteres als Abnahmekriterium vor, und das waere ein Fehler gewesen:

1. LightOS fuehrt Cues nach **LTP** („Cues behalten LTP-Ersatz durch den
   Programmer", ``app_state.py:3082``). Eine Cue setzt, was sie NENNT.
2. Der spaeter gebaute Pfad ``_blend_per_attr`` (F-6) haelt bereits — gemessen
   liefert er nach Ablauf ``{'color_r': 255, 'intensity': 255}`` mit
   ``done=True``. Der Endzweig des Normalpfads war der Ausreisser, nicht die
   Regel.
3. **Auf der Buehne:** eine Cue, die nur die FARBE wechselt, wuerde die
   Intensitaet auf 0 ziehen. Ein Blackout mitten in der Show.
"""
from __future__ import annotations

import os
import sys
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.engine.cue_stack import FadeState  # noqa: E402


class FadeEndeSpringtNichtTest(unittest.TestCase):

    def _fade(self, frm, to, **kw):
        f = FadeState(frm, to, kw.pop("duration", 1.0), kw.pop("delay", 0.0), **kw)
        f.manual = True
        return f

    def _bei(self, f, pos):
        f.manual_pos = pos
        f.done = False
        return f.current_values()

    def test_ein_nicht_genanntes_attribut_ueberlebt_das_fade_ende(self):
        """★★ Der Kern: bei 0,999 war es da, bei 1,0 weg — das ist ein Sprung,
        kein Fade."""
        f = self._fade({1: {"intensity": 255, "color_r": 0}},
                       {1: {"color_r": 255}})
        kurz_davor = self._bei(f, 0.999)[1]
        am_ende = self._bei(f, 1.0)[1]
        self.assertEqual(kurz_davor.get("intensity"), 255)
        self.assertEqual(am_ende.get("intensity"), 255,
                         "das Attribut verschwindet am Fade-Ende schlagartig")

    def test_ein_reiner_farbwechsel_macht_keinen_blackout(self):
        """★★★ Die Buehnensicht — und der Grund, warum das vorgeschlagene
        Abnahmekriterium („auf den Default fahren") falsch gewesen waere: eine
        Cue, die nur die Farbe nennt, darf die Intensitaet nicht anfassen."""
        f = self._fade({1: {"intensity": 255, "color_r": 255, "color_g": 0}},
                       {1: {"color_r": 0, "color_g": 255}})
        for pos in (0.0, 0.5, 1.0):
            with self.subTest(fortschritt=pos):
                self.assertEqual(self._bei(f, pos)[1].get("intensity"), 255,
                                 "die Intensitaet darf nicht mitwandern")

    def test_genannte_attribute_erreichen_exakt_den_zielwert(self):
        """Die Gegenprobe zur Kurvenunabhaengigkeit: am Ende steht der Zielwert
        genau, nicht ein durch die Kurve gerundeter Nachbarwert."""
        f = self._fade({1: {"color_r": 0, "color_g": 13}},
                       {1: {"color_r": 255, "color_g": 200}})
        ende = self._bei(f, 1.0)[1]
        self.assertEqual(ende, {"color_r": 255, "color_g": 200})

    def test_ein_neues_attribut_der_ziel_cue_kommt_von_null(self):
        """Die andere Richtung: was die Quelle nicht kannte, faehrt von 0 hoch
        und steht am Ende auf dem Zielwert."""
        f = self._fade({1: {"color_r": 0}}, {1: {"color_r": 100, "gobo": 80}})
        self.assertEqual(self._bei(f, 0.0)[1].get("gobo"), 0)
        self.assertEqual(self._bei(f, 1.0)[1].get("gobo"), 80)

    def test_ein_geraet_nur_in_der_quelle_verschwindet_nicht(self):
        """Dasselbe eine Ebene hoeher: ein FIXTURE, das die Ziel-Cue nicht
        nennt, darf am Ende nicht wegfallen."""
        f = self._fade({1: {"intensity": 255}, 2: {"intensity": 200}},
                       {1: {"intensity": 100}})
        ende = self._bei(f, 1.0)
        self.assertIn(2, ende, "Geraet 2 faellt am Fade-Ende weg")
        self.assertEqual(ende[2].get("intensity"), 200)

    def test_done_wird_am_ende_gesetzt(self):
        f = self._fade({1: {"intensity": 0}}, {1: {"intensity": 255}})
        self._bei(f, 0.5)
        self.assertFalse(f.done)
        f.manual_pos = 1.0
        f.current_values()
        self.assertTrue(f.done)

    def test_die_gespeicherte_cue_bleibt_unberuehrt(self):
        """★ Die Aliasing-Falle, die der alte Endzweig ausdruecklich bewachte:
        ``to_vals`` IST die ``cue.values`` des Ziel-Cues (per Referenz). Gaebe
        der Endzweig sie direkt zurueck, mutierte ein spaeterer In-Place-Merge
        die persistente Cue und korrumpierte die Show dauerhaft. Der Fix darf
        diese Wache nicht aufgeben."""
        to = {1: {"color_r": 255}}
        f = self._fade({1: {"intensity": 255}}, to)
        ergebnis = self._bei(f, 1.0)
        ergebnis[1]["color_r"] = 7
        ergebnis[1]["intensity"] = 7
        self.assertEqual(to, {1: {"color_r": 255}},
                         "die gespeicherte Cue wurde mitmutiert")

    def test_beide_pfade_antworten_GLEICH(self):
        """★★ Der eigentliche Fund war eine Doppelstelle. Der spaeter gebaute
        Pfad ``_blend_per_attr`` (F-6) hielt schon immer richtig — der Endzweig
        des Normalpfads war der Ausreisser. Dieser Test haelt fest, dass sie
        sich nicht wieder auseinander entwickeln."""
        frm = {1: {"intensity": 255, "color_r": 0}}
        to = {1: {"color_r": 255}}

        normal = self._fade(dict(frm), dict(to))
        normal_ende = self._bei(normal, 1.0)[1]

        per_attr = FadeState({1: dict(frm[1])}, {1: dict(to[1])}, 0.02, 0.0,
                             attr_delays={1: {"color_r": 0.0}})
        time.sleep(0.12)
        per_attr_ende = per_attr.current_values()[1]

        self.assertEqual(normal_ende, per_attr_ende,
                         "Normalpfad und Pro-Attribut-Pfad enden verschieden")
        self.assertTrue(per_attr.done)


if __name__ == "__main__":
    unittest.main()
