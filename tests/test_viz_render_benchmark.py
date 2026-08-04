"""Das Messwerkzeug selbst absichern (Codex-Befund zu PR #566).

`tools/viz_render_benchmark.py` hat zweimal ueberzeugend das Falsche gemessen:
einmal eine dunkle Szene (falsches `dmxBatch`-Format), einmal mehrere Frames in
EINEM JS-Task (nicht der Betriebsmodus, und der Treiber stuerzte ab). Beide Male
sahen die Zahlen tadellos aus. Ein Werkzeug mit dieser Vorgeschichte braucht
eigene Tests — sonst sichert es Entscheidungen ab, die niemand mehr nachprueft.

**Warum ohne Qt und ohne GPU.** Die Fehler lagen nie im Messen selbst, sondern
in der Form: welches Nutzlast-Format an die Bruecke geht, wie viele Frames je
Task gezeichnet werden, ob ein ungueltiger Lauf als gueltiges Ergebnis
durchrutscht. Das sind Aussagen ueber den Quelltext — pruefbar in Millisekunden
und, anders als eine GPU-Messung, auch in CI.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WERKZEUG = os.path.join(_REPO, "tools", "viz_render_benchmark.py")
_BRIDGE_JS = os.path.join(_REPO, "src", "ui", "visualizer", "scene_src",
                          "bridge", "bridge.js")


def _quelle() -> str:
    return open(_WERKZEUG, encoding="utf-8").read()


class BenchmarkNutzlastTest(unittest.TestCase):
    """Die Nutzlast muss zu dem passen, was die Bruecke wirklich liest."""

    def test_dmxbatch_ist_eine_liste_von_objekten(self):
        """Der Handler macht `for (const d of arr)` — ein Objekt ist nicht
        iterierbar, der Aufruf laeuft ins Leere und die Szene bleibt dunkel.

        Genau so entstand die zurueckgezogene Baseline vom 2026-08-03.
        """
        quelle = _quelle()
        stelle = quelle.index("dmxBatch.emit")
        umgebung = quelle[stelle:stelle + 400]
        self.assertIn("json.dumps([", umgebung,
                      "dmxBatch bekommt keine LISTE — der Handler iteriert aber")

    def test_dmxbatch_nutzt_die_feldnamen_der_bruecke(self):
        """`d.fid`, `d.r/g/b`, `d.intensity` — nicht `red`/`green`/`blue`."""
        handler = open(_BRIDGE_JS, encoding="utf-8").read()
        stelle = handler.index("dmxBatch")
        felder = re.findall(r"d\.([a-zA-Z]+)", handler[stelle:stelle + 400])
        self.assertIn("fid", felder, "Testannahme kaputt: Bruecke liest kein d.fid")

        quelle = _quelle()
        block = quelle[quelle.index("dmxBatch.emit"):][:400]
        for feld in ("fid", "r", "g", "b", "intensity"):
            self.assertIn(f'"{feld}"', block,
                          f"die Nutzlast nennt kein {feld!r} — die Bruecke liest es")
        for falsch in ("red", "green", "blue"):
            self.assertNotIn(f'"{falsch}"', block,
                             f"{falsch!r} liest die Bruecke nicht (alter Fehler)")


class BenchmarkMessartTest(unittest.TestCase):
    """Ein Frame je Aufruf — mehrere je Task sind weder Betrieb noch stabil."""

    def test_messung_zeichnet_genau_einen_frame(self):
        quelle = _quelle()
        js = quelle[quelle.index("_MESSUNG_JS"):quelle.index('"""', quelle.index(
            "_MESSUNG_JS") + 20)]
        self.assertNotIn("for (", js,
                         "die Messung rendert wieder in einer JS-Schleife — das "
                         "ist nicht der Betriebsmodus und bringt den Treiber um")
        self.assertEqual(js.count("__renderTick()"), 1,
                         "genau ein Renderdurchlauf je Aufruf")

    def test_gl_finish_bleibt(self):
        """Ohne `gl.finish()` misst man nur das Absetzen der Draw-Calls."""
        self.assertIn("gl.finish()", _quelle())


class BenchmarkGueltigkeitTest(unittest.TestCase):
    """Ein ungueltiger Lauf darf NICHT als Zahl herauskommen."""

    def test_dunkle_szene_bricht_ab_statt_zu_warnen(self):
        """Eine Warnung auf stderr rettet `--json` nicht: dort landete die
        ungueltige Stufe als ganz normales Ergebnis in der Ausgabe."""
        quelle = _quelle()
        stelle = quelle.index('if not aktiv.get("kegel")')
        block = quelle[stelle:stelle + 1400]
        self.assertIn("ungueltig", block,
                      "die Stufe wird nicht als ungueltig markiert")
        self.assertIn("break", block,
                      "nach einer dunklen Szene wird weitergemessen")

    def test_zaehler_unterscheidet_schweigen_von_null(self):
        """`ev()` liefert bei Zeitueberschreitung `None`; ohne Sentinel wird
        daraus `{}` und damit ein Messwert von 0 — so entstand das
        Schein-Raetsel 'bei 48 Fixtures leuchtet nichts'."""
        quelle = _quelle()
        self.assertIn("antwort", quelle[quelle.index("_ZAEHLEN"):][:900],
                      "die Zaehl-Sonde hat kein Antwort-Sentinel")
        self.assertIn('if not aktiv.get("antwort")', quelle,
                      "das Sentinel wird nirgends geprueft")

    def test_zerlegung_stellt_auch_die_schatten_wieder_her(self):
        """`applySettings()` ruft kein `syncSpotShadowBudget()`. Wer nur
        `spot.visible` zuruecksetzt, misst alle Folgestufen schattenlos — und
        vergleicht am Ende gegen einen unvollstaendigen 'Vollzustand'."""
        quelle = _quelle()
        stelle = quelle.index("_ALLES_AN")
        block = quelle[stelle:stelle + 900]
        self.assertIn("castShadow", block,
                      "der Rueckbau stellt die Schatten nicht wieder her")


class BenchmarkZerlegungTest(unittest.TestCase):
    """Der `--aus`-Modus misst EINE Variante in einem eigenen Prozess."""

    def test_aus_modus_existiert_mit_allen_vier_teilen(self):
        quelle = _quelle()
        self.assertIn('"--aus"', quelle)
        stelle = quelle.index("_ABSCHALTER = {")
        block = quelle[stelle:stelle + 700]
        for teil in ("kegel", "boden", "schatten", "spots"):
            self.assertIn(f'"{teil}"', block, f"--aus {teil} fehlt")

    def test_aus_modus_bricht_ab_wenn_der_schalter_nichts_bewirkt(self):
        """Ein Schalter ohne Wirkung sieht in der Messung aus wie ein
        Bestandteil ohne Kosten — der Fehler, den die Wirkungs-Kontrolle
        ueberhaupt erst sichtbar gemacht hat."""
        quelle = _quelle()
        stelle = quelle.index("_ABSCHALTER[aus]()")
        block = quelle[stelle:stelle + 800]
        self.assertIn("hat NICHTS bewirkt", block)
        self.assertIn("SystemExit", block,
                      "ohne Wirkung wird trotzdem gemessen")

    def test_das_gescheiterte_verfahren_bleibt_dokumentiert(self):
        """Die Zerlegung im selben Prozess ist zweimal an ihrer eigenen
        Kontrollmessung gescheitert. Wer das nicht weiss, baut sie nach."""
        quelle = _quelle()
        self.assertIn("Lauf gestoert", quelle,
                      "die gescheiterte Methode ist nicht mehr dokumentiert")


# ── Die Messung darf keine Vorgeschichte haben (CDX, Codex zu PR #569) ───────

class AusModusReihenfolgeTest(unittest.TestCase):
    """**Wann** gemessen wird, ist hier genauso wichtig wie **was**.

    Die erste Fassung rief am Anfang jeder Fixture-Stufe ein unbedingtes
    ``einmal_messen()`` und verwarf dessen Ergebnis im ``--aus``-Zweig wieder.
    Folge: der Voll-Lauf meldete sein ERSTES 40-Frame-Fenster, jeder
    ``--aus``-Lauf ein SPAETERES — verglichen wurden zwei verschiedene
    Abschnitte der Prozess-Lebenszeit. Das Werkzeug beziffert die Drift ueber
    einen Lauf selbst mit **2,5 bzw. 3,8 ms**, bei gesuchten Anteilen von
    **1–7 ms**: der Messfehler hatte die Groesse des Messergebnisses.

    Das ist bitter, weil ``--aus`` genau gegen diese Drift gebaut wurde — ein
    eigener Prozess je Variante. Der Gedanke war richtig und die Umsetzung gab
    dem einen Prozess trotzdem eine laengere Vorgeschichte als dem anderen.

    Geprueft wird deshalb die **Anweisungsfolge im AST**, nicht der Wortlaut:
    die Frage ist eine der Reihenfolge, und ein Textfund an anderer Stelle
    beantwortet sie nicht.
    """

    def _mess_schleife(self):
        """Der `for`-Koerper ueber die Fixture-Stufen in `messen()`."""
        baum = ast.parse(_quelle())
        fn = next(k for k in ast.walk(baum)
                  if isinstance(k, ast.FunctionDef) and k.name == "messen")
        for knoten in ast.walk(fn):
            if isinstance(knoten, ast.For):
                körper = "".join(ast.dump(s) for s in knoten.body)
                if "einmal_messen" in körper and "_ABSCHALTER" in körper:
                    return knoten
        self.fail("die Mess-Schleife ueber die Fixture-Stufen ist nicht auffindbar")

    def test_abschalten_kommt_vor_der_ersten_messung(self):
        """Im `--aus`-Zweig: erst der Zustand, dann die erste getaktete Messung."""
        schleife = self._mess_schleife()
        zweig = next((s for s in schleife.body
                      if isinstance(s, ast.If) and "_ABSCHALTER" in
                      "".join(ast.dump(k) for k in s.body)), None)
        self.assertIsNotNone(zweig, "der `if aus:`-Zweig ist nicht auffindbar")

        reihenfolge = []
        for knoten in ast.walk(zweig):
            if isinstance(knoten, ast.Call):
                if (isinstance(knoten.func, ast.Name)
                        and knoten.func.id == "einmal_messen"):
                    reihenfolge.append((knoten.lineno, "messen"))
                elif isinstance(knoten.func, ast.Subscript) and \
                        getattr(knoten.func.value, "id", "") == "_ABSCHALTER":
                    reihenfolge.append((knoten.lineno, "abschalten"))
        reihenfolge.sort()
        namen = [n for _, n in reihenfolge]
        self.assertIn("abschalten", namen, "der Abschalter wird gar nicht gerufen")
        self.assertIn("messen", namen, "es wird gar nicht gemessen")
        self.assertLess(
            namen.index("abschalten"), namen.index("messen"),
            "gemessen wird VOR dem Abschalten — die 40 Frames davor sind "
            "Vorgeschichte, die der Voll-Lauf nicht hat")

    def test_keine_unbedingte_messung_vor_dem_aus_zweig(self):
        """Und davor darf ueberhaupt nicht gemessen werden.

        Die Gegenprobe zum Test oben: haette man das alte
        `werte = einmal_messen()` stehen lassen und im Zweig nur ein zweites
        ergaenzt, waere die Reihenfolge INNERHALB des Zweigs richtig — und die
        verworfenen 40 Frames trotzdem wieder da.
        """
        schleife = self._mess_schleife()
        for stmt in schleife.body:
            if isinstance(stmt, ast.If) and "_ABSCHALTER" in \
                    "".join(ast.dump(k) for k in stmt.body):
                break
            gefunden = [k for k in ast.walk(stmt) if isinstance(k, ast.Call)
                        and isinstance(k.func, ast.Name)
                        and k.func.id == "einmal_messen"]
            self.assertEqual(
                gefunden, [],
                f"unbedingte Messung in Zeile {gefunden[0].lineno if gefunden else '?'} "
                f"— sie laeuft auch im `--aus`-Lauf und verschiebt dessen Fenster")


class AusModusEineStufeTest(unittest.TestCase):
    """`--aus` misst genau EINE Fixture-Zahl — als echter Prozessaufruf geprueft.

    Der abgeschaltete Zustand wird nicht wieder eingeraeumt; er traegt sonst in
    die naechste Stufe hinueber. Ohne Zahl greift der Default ``[12, 32, 48]``,
    der Fall entsteht also schon beim bequemsten Aufruf.

    Bewusst als Subprozess statt als Quelltext-Scan: die Frage ist, was das
    Werkzeug TUT, wenn man es so aufruft. Der Abbruch liegt vor dem Aufbau der
    Szene, der Test kostet deshalb keinen Renderlauf.
    """

    def _lauf(self, *argv):
        umgebung = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        return subprocess.run([sys.executable, _WERKZEUG, *argv],
                              cwd=_REPO, capture_output=True, text=True,
                              env=umgebung, timeout=180)

    def test_mehrere_stufen_mit_aus_werden_abgelehnt(self):
        r = self._lauf("12", "32", "--aus", "kegel")
        self.assertNotEqual(r.returncode, 0, "mehrere Stufen wurden gemessen")
        self.assertIn("EINE Fixture-Zahl", r.stderr + r.stdout)

    def test_aus_ohne_zahl_faellt_nicht_in_den_default(self):
        """Der Default [12, 32, 48] ist der wahrscheinlichste Weg in die Falle."""
        r = self._lauf("--aus", "schatten")
        self.assertNotEqual(r.returncode, 0,
                            "der Default-Dreisatz lief mit --aus durch")
        self.assertIn("EINE Fixture-Zahl", r.stderr + r.stdout)


class BenchmarkFormTest(unittest.TestCase):
    """Das Werkzeug muss importierbar und syntaktisch heil sein."""

    def test_ist_gueltiges_python(self):
        ast.parse(_quelle())

    def test_budget_haengt_an_der_push_rate_des_visualizers(self):
        """33 ms ist keine Zierzahl — sie ist der Massstab jeder Aussage.

        **Und es ist bewusst NICHT die DMX-Rate.** Die erste Fassung rechnete
        gegen 44 Hz (`OutputManager.TARGET_HZ`) und meldete daraufhin "ab 32
        Geraeten ueberschreitet die Szene das Budget" — die falsche Zahl, denn
        die Szene wird vom `VisualizerService` gefuettert, und der tickt mit
        `TICK_MS = 33`. Dieser Test bindet beide Seiten aneinander, damit die
        Verwechslung nicht zurueckkommt.
        """
        quelle = _quelle()
        self.assertIn("VIZ_BUDGET_MS = 33.0", quelle)

        dienst = open(os.path.join(_REPO, "src", "ui", "visualizer",
                                   "visualizer_service.py"), encoding="utf-8").read()
        treffer = re.search(r"TICK_MS\s*=\s*(\d+)", dienst)
        self.assertTrue(treffer, "VisualizerService hat kein TICK_MS mehr")
        self.assertEqual(int(treffer.group(1)), 33,
                         "der Service tickt anders als das Budget im Benchmark")

    def test_ueberschreiten_staut_nichts_auf(self):
        """Das Dirty-Flag ist binaer — ueber dem Budget heisst "weniger Bilder",
        nicht "haengt hinterher". Steht so im Werkzeug und muss dort bleiben,
        sonst liest jemand die Zahlen wieder dramatischer als sie sind."""
        quelle = _quelle()
        self.assertIn("binaer", quelle)
        loop = open(os.path.join(_REPO, "src", "ui", "visualizer", "scene_src",
                                 "scene", "render_loop.js"), encoding="utf-8").read()
        self.assertIn("_dirty = false", loop,
                      "der Render-Loop puffert jetzt doch — Aussage pruefen")


if __name__ == "__main__":
    unittest.main()
