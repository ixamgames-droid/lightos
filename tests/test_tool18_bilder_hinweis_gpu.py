"""TOOL-18: uebersprungene Szenen melden, wenn ihr Bild im Repo fehlt.

Befund (Codex-Review #936): ``tools/anleitungsbilder`` nimmt 3D-Szenen
(``braucht_gpu``) nur mit ``--bildschirm`` auf. Im gewoehnlichen Lauf stand dort
„UEBERSPRUNGEN — braucht eine GPU" und sonst nichts: ob das Bild und sein
Eintrag in ``bilder.json`` im Repo ueberhaupt existieren, sah niemand nach. Eine
neue 3D-Szene, die nie am Bildschirm aufgenommen wurde, blieb so unbemerkt ohne
Bild — die Anleitung zeigte dann einen toten Bildverweis.

Jetzt nennt die Meldung, was fehlt, und den Aufruf, der es nachholt; am Ende
des Laufs steht eine Sammelzeile. Dasselbe umgekehrt fuer ``--bildschirm``-Laeufe.

Geprueft werden die reinen Funktionen (ohne Qt) gegen einen Wegwerf-Ordner und
dass der Lauf sie an beiden Sprungstellen benutzt.
"""
import ast
import json
import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

ZIEL = "docs/anleitung_x/img"


class _Basis(unittest.TestCase):

    def setUp(self):
        from anleitungsbilder import runner
        self.runner = runner
        self._tmp = tempfile.TemporaryDirectory(prefix="lightos_tool18_")
        self.addCleanup(self._tmp.cleanup)
        self.repo = self._tmp.name
        self.ordner = os.path.join(self.repo, *ZIEL.split("/"))
        os.makedirs(self.ordner)

    def _bild(self, datei="05_buehne.png"):
        with open(os.path.join(self.ordner, datei), "wb") as f:
            f.write(b"\x89PNG")

    def _manifest(self, *dateien, roh=None):
        with open(os.path.join(self.ordner, "bilder.json"), "w", encoding="utf-8") as f:
            f.write(roh if roh is not None
                    else json.dumps({"bilder": [{"datei": d} for d in dateien]}))

    def _szene(self, gpu):
        return self.runner.Szene("05_buehne", braucht_gpu=gpu)


class FehlstandTest(_Basis):

    def _fehlt(self, datei="05_buehne.png"):
        return self.runner.fehlstand_im_repo(ZIEL, datei, self.repo)

    def test_bild_und_eintrag_fehlen(self):
        self.assertEqual(self._fehlt(), ["das Bild", "der Eintrag in bilder.json"])

    def test_nur_der_eintrag_fehlt(self):
        self._bild()
        self._manifest("01_anderes.png")
        self.assertEqual(self._fehlt(), ["der Eintrag in bilder.json"])

    def test_nur_das_bild_fehlt(self):
        self._manifest("05_buehne.png")
        self.assertEqual(self._fehlt(), ["das Bild"])

    def test_beides_da(self):
        self._bild()
        self._manifest("05_buehne.png")
        self.assertEqual(self._fehlt(), [])

    def test_kaputtes_manifest_zaehlt_als_fehlender_eintrag(self):
        self._bild()
        for roh in ("{kaputt", "[]", '{"bilder": "nein"}', ""):
            with self.subTest(roh=roh):
                self._manifest(roh=roh)
                self.assertEqual(self._fehlt(), ["der Eintrag in bilder.json"])

    def test_gefragt_wird_das_repo_nicht_der_zielordner_des_laufs(self):
        """Bei ``--pruefen`` ist der Zielordner ein leerer Temp-Ordner — die
        Auskunft muss trotzdem den Bestand im Repo betreffen."""
        self._bild()
        self._manifest("05_buehne.png")
        with tempfile.TemporaryDirectory() as leer:
            self.assertEqual(self.runner.fehlstand_im_repo(ZIEL, "05_buehne.png", self.repo), [])
            self.assertEqual(self.runner.fehlstand_im_repo(ZIEL, "05_buehne.png", leer),
                             ["das Bild", "der Eintrag in bilder.json"])


class UebersprungenTest(_Basis):

    def test_wann_eine_szene_uebersprungen_wird(self):
        r = self.runner.uebersprungen
        self.assertEqual(r(self._szene(True), bildschirm=False, offscreen=True), "gpu")
        self.assertIsNone(r(self._szene(True), bildschirm=True, offscreen=False))
        self.assertEqual(r(self._szene(False), bildschirm=True, offscreen=False), "offscreen")
        self.assertIsNone(r(self._szene(False), bildschirm=False, offscreen=True))
        # 3D-Szene ohne --bildschirm, aber auch nicht offscreen: wird aufgenommen.
        self.assertIsNone(r(self._szene(True), bildschirm=False, offscreen=False))

    def _text(self, grund):
        return self.runner.uebersprungen_text(grund, "x", "05_buehne.png", ZIEL, self.repo)

    def test_gpu_szene_ohne_bild_wird_gemeldet(self):
        text, fehlt = self._text("gpu")
        self.assertTrue(fehlt, "eine 3D-Szene ohne Bild im Repo bleibt unbemerkt")
        self.assertIn("UEBERSPRUNGEN", text)
        self.assertIn("das Bild und der Eintrag in bilder.json fehlt", text)
        self.assertIn(ZIEL, text)
        self.assertIn("tools/anleitungsbilder.py x --bildschirm", text)

    def test_gpu_szene_mit_bild_ohne_eintrag_wird_gemeldet(self):
        self._bild()
        text, fehlt = self._text("gpu")
        self.assertTrue(fehlt)
        self.assertIn("der Eintrag in bilder.json fehlt", text)
        self.assertNotIn("das Bild", text)

    def test_vollstaendige_gpu_szene_bleibt_bei_der_kurzen_zeile(self):
        self._bild()
        self._manifest("05_buehne.png")
        text, fehlt = self._text("gpu")
        self.assertFalse(fehlt)
        self.assertIn("UEBERSPRUNGEN", text)
        self.assertNotIn("ACHTUNG", text)

    def test_bildschirm_lauf_meldet_nur_luecken(self):
        text, fehlt = self._text("offscreen")
        self.assertTrue(fehlt)
        self.assertIn("ACHTUNG", text)
        self.assertIn("tools/anleitungsbilder.py x", text)
        self.assertNotIn("--bildschirm\n", text)
        self.assertFalse(text.rstrip().endswith("--bildschirm"),
                         "der Nachhol-Aufruf fuer eine Offscreen-Szene ist der OHNE --bildschirm")
        self._bild()
        self._manifest("05_buehne.png")
        self.assertEqual(self._text("offscreen"), (None, False))


class LaufBenutztDieHelferTest(unittest.TestCase):
    """Die Helfer nuetzen nichts, wenn der Lauf sie nicht ruft."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(TOOLS, "anleitungsbilder", "runner.py"), encoding="utf-8") as f:
            cls.quelle = f.read()
        baum = ast.parse(cls.quelle)
        cls.lauf = next(n for n in ast.walk(baum)
                        if isinstance(n, ast.FunctionDef) and n.name == "lauf")

    def _rufe(self):
        return {n.func.id for n in ast.walk(self.lauf)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}

    def test_lauf_fragt_beide_helfer(self):
        rufe = self._rufe()
        self.assertIn("uebersprungen", rufe)
        self.assertIn("uebersprungen_text", rufe)

    def test_die_alte_stumme_sprungstelle_ist_weg(self):
        text = ast.get_source_segment(self.quelle, self.lauf)
        self.assertNotIn("if bildschirm and not szene.braucht_gpu:\n                continue",
                         text)
        self.assertEqual(text.count("UEBERSPRUNGEN"), 0,
                         "die Meldung kommt aus uebersprungen_text, nicht aus lauf")

    def test_am_ende_steht_die_sammelzeile(self):
        text = ast.get_source_segment(self.quelle, self.lauf)
        self.assertIn("luecken.append(", text)
        self.assertIn("HINWEIS:", text)

    def test_der_echte_bestand_hat_keine_luecke(self):
        """Jede 3D-Szene, die das Werkzeug kennt, hat im Repo Bild und Eintrag —
        sonst zeigt eine Anleitung einen toten Bildverweis."""
        from anleitungsbilder import runner
        luecken, gesehen = [], 0
        for anleitung in runner.anleitungen():
            szenen, ziel_rel = runner.lade_szenen(anleitung)
            for s in szenen:
                if s.braucht_gpu:
                    gesehen += 1
                    fehlt = runner.fehlstand_im_repo(ziel_rel, s.datei)
                    if fehlt:
                        luecken.append(f"{ziel_rel}/{s.datei}: {' und '.join(fehlt)}")
        self.assertGreater(gesehen, 10, "Gegenprobe: es gibt 3D-Szenen, und sie werden gesehen")
        self.assertEqual(luecken, [])


if __name__ == "__main__":
    unittest.main()
