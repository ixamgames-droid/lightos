"""VIZ-PERF: das Shadow-Budget hat ein absolutes Dach, nicht nur eine Reserve.

**Was kaputt war.** `shadowSpotBudget()` rechnete `maxTextures − 6`. Auf einer
GPU mit vielen Texture-Units (Intel UHD 630, `maxTextures = 32`) sind das **26**
schattenwerfende SpotLights — und genau dort **stuerzt der Grafiktreiber ab**,
sobald die Szene mehr als einen Frame zeichnet. Nicht Kontextverlust, sondern
ein Uebersetzungsfehler:

    Failed to compile fragment shader:
    SIMD8 FS compile failed: no register to spill

Jede Shadow-Map kostet den Fragment-Shader nicht nur eine Texture-Unit, sondern
auch Register. Ab einer gewissen Zahl findet der Compiler nichts mehr zum
Auslagern, bricht ab, und der Prozess endet mit SIGSEGV.

**Gemessen** (leuchtende Moving Heads, rAF-Betrieb, 20 s): 20/22/24 Schatten
laufen (438/305/148 Frames), **26 stuerzt ab**, 32 Fixtures mit gedeckeltem
Budget von 22 bzw. 18 laufen wieder. Mit dem Dach auf 16: 32 Fixtures → 401
Frames, 48 Fixtures → 312 Frames, beide stabil. Bei 48 leuchtete die Szene
vorher **gar nicht** — auch das war dieser Shader, der nicht uebersetzte.

**Warum dieser Test ohne Qt auskommt.** Die Aussage ist eine ueber die REGEL,
nicht ueber die GPU: aus (maxTextures, Reserve, Dach) muss ein Budget folgen,
das auf keiner Karte ueber das Dach geht. Das laesst sich am Quelltext pruefen —
und nur so laeuft es auch in CI, wo es gar keine GPU gibt. Der Beleg, dass das
Dach den Absturz WIRKLICH behebt, ist die Messung oben; sie steht im
Modulkommentar von `fixtures.js` und ist mit `tools/viz_render_benchmark.py`
wiederholbar.
"""
from __future__ import annotations

import os
import re
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FIXTURES_JS = os.path.join(
    _REPO, "src", "ui", "visualizer", "scene_src", "fixtures", "fixtures.js")


def _quelltext() -> str:
    return open(_FIXTURES_JS, encoding="utf-8").read()


def _konstante(name: str) -> int:
    treffer = re.search(rf"^const {name} = (\d+);", _quelltext(), re.M)
    assert treffer, f"{name} steht nicht mehr in fixtures.js"
    return int(treffer.group(1))


class ShadowBudgetCapTest(unittest.TestCase):

    def test_es_gibt_ein_absolutes_dach(self):
        self.assertEqual(_konstante("SHADOW_SPOT_HARD_CAP"), 16)

    def test_budget_wendet_das_dach_an(self):
        """Die Rechnung muss `Math.min` gegen das Dach enthalten.

        Ohne diesen Schritt ist das Dach eine Konstante, die niemand liest —
        genau die Sorte Fehler, die VIZ-SHIM aufgedeckt hat.
        """
        quelle = _quelltext()
        koerper = quelle.split("function shadowSpotBudget()", 1)[1].split("}", 2)[0]
        self.assertIn("SHADOW_SPOT_HARD_CAP", koerper,
                      "shadowSpotBudget() benutzt das Dach nicht")
        self.assertIn("Math.min", koerper,
                      "das Dach wird nicht als Obergrenze angewandt")

    def test_dach_liegt_unter_der_gemessenen_kippgrenze(self):
        """24 Schatten liefen, 26 stuerzten ab — das Dach muss darunter liegen.

        Mit Abstand: die Kippgrenze wurde auf EINER GPU ermittelt, und ein Dach,
        das erst kurz davor greift, ist keins.
        """
        self.assertLess(_konstante("SHADOW_SPOT_HARD_CAP"), 26,
                        "das Dach liegt auf oder ueber der Absturzgrenze")
        self.assertLessEqual(_konstante("SHADOW_SPOT_HARD_CAP"), 20,
                             "zu wenig Abstand zur gemessenen Kippgrenze (26)")

    def test_reserve_bleibt_fuer_schwache_gpus_wirksam(self):
        """Auf Davids Surface (maxTextures=16) entscheidet weiter die Reserve.

        16 − 6 = 10 liegt unter dem Dach; dort darf sich nichts geaendert haben,
        sonst haette der Fix auf der schwaecheren Karte Schatten weggenommen,
        die dort nie ein Problem waren.
        """
        reserve = _konstante("SHADOW_TEXTURE_RESERVE")
        dach = _konstante("SHADOW_SPOT_HARD_CAP")
        surface_budget = min(dach, max(2, 16 - reserve))
        self.assertEqual(surface_budget, 16 - reserve,
                         "auf einer 16-Unit-GPU greift jetzt faelschlich das Dach")

    def test_die_messung_steht_im_code(self):
        """Die Zahlen, die das Dach begruenden, muessen auffindbar bleiben.

        Ein Grenzwert ohne die Messung daneben wird beim naechsten Aufraeumen
        hochgesetzt, weil niemand mehr weiss, warum er so niedrig ist.
        """
        quelle = _quelltext()
        for spur in ("no register to spill", "ABSTURZ", "viz_render_benchmark"):
            self.assertIn(spur, quelle,
                          f"die Begruendung des Dachs nennt {spur!r} nicht mehr")


if __name__ == "__main__":
    unittest.main()
