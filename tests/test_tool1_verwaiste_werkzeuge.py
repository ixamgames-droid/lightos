"""TOOL-1: sieben verwaiste Werkzeuge liegen jetzt in ``tools/_archiv/``.

Befund aus dem Werkzeug-Durchgang PROC-07 (2026-09-01), am 2026-10-02
nachgeprueft: keines der sieben wird von einer Anleitung, einem Test, einem
Skill oder einem anderen Werkzeug aufgerufen — die einzigen Nennungen waren
der generierte Index ``tools/README.md`` und ein Beispiel im Docstring von
``tools/_gen_env.py``. Verschoben, nicht geloescht: die Historie ist die
einzige Doku dieser Shows.

Zwei Lehren daraus sind als Waechter festgehalten:

* **Zwei lebende Generatoren mit derselben Zieldatei.** ``build_demo_show.py``
  und ``build_full_show.py`` schrieben beide ``shows/APC_Demo_Show.lshow`` —
  wer den falschen startet, ueberschreibt die mitgelieferte Show mit einem
  aelteren Stand, ohne dass es auffaellt.
* **Kein ``__main__``-Guard:** ``check_demo_show_full.py`` und
  ``verify_color_dimmer_separation.py`` starteten schon beim blossen Import den
  vollen Pruef- und Renderlauf. Im Archiv ruft sie niemand mehr auf.
"""
import ast
import os
import unittest
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
ARCHIV = os.path.join(TOOLS, "_archiv")

VERWAIST = (
    "build_komplette_animierte_show.py",
    "build_uxtest3_full.py",
    "build_validated_demo.py",
    "check_demo_show_full.py",
    "vc_click_targets.py",
    "verify_color_dimmer_separation.py",
    "build_demo_show.py",
)


def _show_ziele(ordner):
    """``{show-dateiname: [skript, ...]}`` aus den ``*OUT*``-Zuweisungen auf
    Modulebene — so legen die Generatoren ihre Zieldatei fest."""
    ziele = defaultdict(list)
    for name in sorted(os.listdir(ordner)):
        pfad = os.path.join(ordner, name)
        if not name.endswith(".py") or not os.path.isfile(pfad):
            continue
        with open(pfad, encoding="utf-8", errors="replace") as f:
            try:
                baum = ast.parse(f.read(), filename=pfad)
            except SyntaxError:
                continue
        for knoten in baum.body:
            if not isinstance(knoten, ast.Assign):
                continue
            if not any(isinstance(t, ast.Name) and "OUT" in t.id.upper()
                       for t in knoten.targets):
                continue
            for c in ast.walk(knoten.value):
                if (isinstance(c, ast.Constant) and isinstance(c.value, str)
                        and c.value.endswith(".lshow")):
                    ziele[os.path.basename(c.value)].append(name)
    return ziele


class VerwaisteWerkzeugeSindArchiviert(unittest.TestCase):

    def test_die_sieben_liegen_im_archiv(self):
        for name in VERWAIST:
            with self.subTest(werkzeug=name):
                self.assertFalse(os.path.exists(os.path.join(TOOLS, name)),
                                 f"{name} liegt noch in tools/")
                self.assertTrue(os.path.isfile(os.path.join(ARCHIV, name)),
                                f"{name} fehlt in tools/_archiv/ (verschieben, nicht loeschen)")

    def test_archiv_readme_begruendet_jedes(self):
        with open(os.path.join(ARCHIV, "README.md"), encoding="utf-8") as f:
            text = f.read()
        fehlend = [n for n in VERWAIST if f"`{n}`" not in text]
        self.assertEqual(fehlend, [], "ohne Begruendung archiviert")


class ArchivierteNennenIhrenNeuenPfad(unittest.TestCase):
    """Review-Fund (Codex zu #837): Aufrufbeispiele und Hilfemeldungen nannten
    nach dem Verschieben weiter ``tools/<name>.py`` — wer sie kopierte, bekam
    „No such file"."""

    def test_kein_aufruf_ueber_den_alten_pfad(self):
        import re
        treffer = []
        for name in VERWAIST:
            with open(os.path.join(ARCHIV, name), encoding="utf-8") as f:
                text = f.read()
            alt = re.compile(r"tools[/\\]" + re.escape(name))
            for nr, zeile in enumerate(text.splitlines(), 1):
                if alt.search(zeile):
                    treffer.append(f"{name}:{nr}  {zeile.strip()}")
        self.assertEqual(treffer, [], "alter Pfad im archivierten Skript:\n  "
                         + "\n  ".join(treffer))


class KeineZweiGeneratorenMitDerselbenShow(unittest.TestCase):

    def test_jede_zielshow_hat_genau_einen_lebenden_generator(self):
        ziele = _show_ziele(TOOLS)
        doppelt = {show: skripte for show, skripte in ziele.items() if len(skripte) > 1}
        self.assertEqual(doppelt, {}, (
            "Mehrere Werkzeuge in tools/ schreiben dieselbe Show — wer das "
            f"falsche startet, ueberschreibt sie mit einem anderen Stand: {doppelt}"))

    def test_der_scanner_sieht_die_generatoren(self):
        """Ohne diese Vorbedingung waere der Waechter oben leer gruen."""
        ziele = _show_ziele(TOOLS)
        self.assertGreaterEqual(len(ziele), 20, f"nur {len(ziele)} Zielshows erkannt")
        self.assertEqual(ziele.get("APC_Demo_Show.lshow"), ["build_full_show.py"],
                         "build_full_show.py ist der verbliebene Generator der APC-Demo")


if __name__ == "__main__":
    unittest.main()
