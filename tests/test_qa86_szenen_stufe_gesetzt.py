"""QA-86: Szenen-Tests setzen die Render-Qualitaetsstufe ausdruecklich.

Wer ``stage_scene.html`` direkt per ``QUrl`` laedt und keine ``gputier``-Query
mitgibt, testet die Stufe, die die JS-Probe (``renderer.js#probeGpuTier``) auf
dem Testrechner waehlt — und die haengt an der Grafikkarte: Windows rendert
WebGL ueber ANGLE/Direct3D 11, und ANGLE meldet dort immer
``MAX_TEXTURE_IMAGE_UNITS = 16``, also ``'low'``; eine Linux-Desktop-GPU meldet
mehr und bekommt ``'high'``.

Gemessen 2026-10-08 (Sitzung D, Windows 11, Radeon RX 580): unter ``'low'``
deckelt das Prisma auf 3 Facetten (``PRISMA_MAX_LOWSPEC``), und damit waren
``test_viz80_optik_gobo_scene`` (4 Tests, ``prismN 2 != 5``) und
``test_viz13c_updatedmx_registry`` (Golden ``prismN 3 != 2``) rot, waehrend sie
auf Linux gruen sind — derselbe Stand, zwei Ergebnisse, je nach GPU. Dieselbe
Falle stand schon einmal in ``test_viz_prisma_3d_scene`` (Windows-ARM/Adreno);
dort wurde sie einzeln behoben, die anderen Szenen-Tests blieben offen.

Dieser Waechter macht daraus eine Regel: jede Testdatei, die die Szene per
``setQuery`` laedt, nennt eine Stufe. Welche, entscheidet der Test selbst —
die Szenen-Tests nehmen ``high`` (die Stufe, unter der die Erwartungswerte
entstanden sind); wer eine Stufe gezielt prueft, setzt genau diese.

Geprueft wird je DATEI, nicht je Aufruf: ``test_viz13_scene_modules_smoke``
baut die Query in einer Variablen zusammen; eine Suche nach dem Muster im
``setQuery``-Aufruf selbst wuerde dort falsch anschlagen.
"""
import os
import unittest

_TESTS = os.path.dirname(os.path.abspath(__file__))

# Dateien, die die Szene laden duerfen, OHNE eine Stufe zu nennen — je mit Grund.
_AUSNAHMEN = {
    # Wird im Zweig perf/viz72-grosse-rigs (VIZ-72) gerade umgebaut; die Stufe
    # wird dort gesetzt, sobald der Zweig gelandet ist — hier nicht vorgreifen,
    # sonst konfliktet derselbe Block in zwei Zweigen.
    "test_viz69_render_ruckler.py": "VIZ-72 in Arbeit",
}


def _szenen_tests():
    """(Dateiname, Text) jeder Testdatei, die stage_scene.html per setQuery laedt."""
    gefunden = []
    for name in sorted(os.listdir(_TESTS)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        if name == os.path.basename(__file__):
            continue
        with open(os.path.join(_TESTS, name), encoding="utf-8") as f:
            text = f.read()
        if "stage_scene.html" in text and "setQuery(" in text:
            gefunden.append((name, text))
    return gefunden


class SzenenTestsSetzenStufeTest(unittest.TestCase):

    def test_die_suche_findet_die_szenen_tests(self):
        # Gegenprobe: findet die Suche (etwa nach einer Umbenennung) nichts
        # mehr, waere der Waechter unten stumm und trotzdem gruen.
        namen = [n for n, _t in _szenen_tests()]
        self.assertGreaterEqual(len(namen), 20, namen)
        self.assertIn("test_viz80_optik_gobo_scene.py", namen)
        self.assertIn("test_viz13c_updatedmx_registry.py", namen)

    def test_jeder_szenen_test_nennt_eine_stufe(self):
        ohne = [n for n, t in _szenen_tests()
                if "gputier=" not in t and n not in _AUSNAHMEN]
        self.assertEqual(
            ohne, [],
            "Diese Szenen-Tests laden stage_scene.html ohne ?gputier=… — dann "
            "entscheidet die GPU des Testrechners ueber die Stufe (Windows/ANGLE: "
            "immer 'low'), und das Ergebnis haengt an der Grafikkarte. "
            "Stufe setzen, z. B. url.setQuery(f\"v=…&gputier=high\") (QA-86).")

    def test_ausnahmen_haben_einen_grund(self):
        for name, grund in _AUSNAHMEN.items():
            self.assertTrue(name.startswith("test_") and name.endswith(".py"), name)
            self.assertTrue(grund.strip(), f"Ausnahme ohne Grund: {name}")


if __name__ == "__main__":
    unittest.main()
