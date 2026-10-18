"""DOC-16 (Rest) — Schrift der Anleitungsbilder, ``--demo-show`` und die neu
bebilderten Anleitungen (Virtual Console, Gruppen und Matrizen, Musik-Sync).

* **Schrift:** ``tools/anleitungsbilder/schrift/RobotoCondensed-wght.ttf`` liegt
  bei, die Bytes passen zur SHA-256 in ``THIRD_PARTY_NOTICES.md``, der
  OFL-Lizenztext liegt unter ``licenses/``, und das Werkzeug wuenscht genau die
  Familie, die das Theme verlangt. Ob sie im Lauf wirklich gerendert wird,
  prueft ``test_anleitungsbilder.MiniLaufTest`` am Manifest.
* **--demo-show:** ein echter Lauf schreibt eine ladbare ``.lshow`` (Zip mit
  ``show.json``) mit den Geraeten der Doku-Demo, ohne Pfade des Baurechners;
  der echte Datenordner bleibt unberuehrt; eine vorhandene Datei wird nicht
  ueberschrieben; zusammen mit einer Anleitung wird der Schalter abgelehnt.
* **Bilder:** jede Szene der drei Anleitungen hat ihr Bild im Repo, jedes Bild
  im Ordner ist von der Anleitung verlinkt und im Manifest eingetragen.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from anleitungsbilder import runner, sandbox  # noqa: E402

SCHRIFT = os.path.join(TOOLS, "anleitungsbilder", "schrift", "RobotoCondensed-wght.ttf")
LIZENZ = os.path.join(REPO, "licenses", "OFL-1.1-RobotoCondensed.txt")


class SchriftTest(unittest.TestCase):

    def test_datei_und_lizenz_liegen_bei(self):
        self.assertTrue(os.path.isfile(SCHRIFT))
        self.assertEqual(os.path.abspath(runner.SCHRIFT_DATEI), os.path.abspath(SCHRIFT))
        with open(LIZENZ, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("SIL OPEN FONT LICENSE Version 1.1", text)
        self.assertIn("The Roboto Project Authors", text)

    def test_bytes_passen_zur_angabe_in_den_notices(self):
        with open(os.path.join(REPO, "THIRD_PARTY_NOTICES.md"), encoding="utf-8") as f:
            text = f.read()
        abschnitt = text.split("## Roboto Condensed", 1)[1].split("\n## ", 1)[0]
        m = re.search(r"SHA-256:\*\*\s*`([0-9a-f]{64})`", abschnitt)
        self.assertIsNotNone(m, "SHA-256 fehlt im Abschnitt Roboto Condensed")
        with open(SCHRIFT, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), m.group(1))

    def test_familie_ist_die_des_themes(self):
        with open(os.path.join(REPO, "assets", "themes", "dark.qss"), encoding="utf-8") as f:
            qss = f.read()
        m = re.search(r'font-family:\s*"([^"]+)"', qss)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), runner.SCHRIFT_FAMILIE)


def _echte_orte():
    home = sandbox.echter_home()
    return [os.path.join(home, ".local", "share", "LightOS"),
            os.path.join(home, ".config", "LightOS"),
            os.path.join(REPO, "data"), os.path.join(REPO, "shows")]


def _lauf(*argumente):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, os.path.join(TOOLS, "anleitungsbilder.py"), *argumente],
        cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=180)


class DemoShowExportTest(unittest.TestCase):
    """Ein echter ``--demo-show``-Lauf (eigener Prozess, eigene Sandbox)."""

    @classmethod
    def setUpClass(cls):
        cls.ordner = tempfile.mkdtemp(prefix="lightos_demoshow_")
        cls.ziel = os.path.join(cls.ordner, "Doku_Demo")      # Endung ergaenzt das Werkzeug
        cls.orte = _echte_orte()
        cls.vorher = sandbox.schnappschuss(cls.orte)
        cls.lauf = _lauf("--demo-show", cls.ziel)
        cls.nachher = sandbox.schnappschuss(cls.orte)
        cls.app_laeuft = sandbox.laufende_instanz()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.ordner, ignore_errors=True)

    def _log(self):
        return self.lauf.stdout[-3000:] + "\n--- stderr ---\n" + self.lauf.stderr[-3000:]

    def test_schreibt_eine_show_mit_den_geraeten_der_doku_demo(self):
        self.assertEqual(self.lauf.returncode, 0, self._log())
        pfad = self.ziel + ".lshow"
        self.assertTrue(os.path.isfile(pfad), self._log())
        with zipfile.ZipFile(pfad) as z:
            show = json.loads(z.read("show.json").decode("utf-8"))
            text = z.read("show.json").decode("utf-8")
        self.assertIn("PAR 1", text)
        self.assertIn("LED-Leiste", text)
        self.assertIn("Doku-Cues", text)
        self.assertTrue(show)

    def test_keine_pfade_des_baurechners(self):
        with zipfile.ZipFile(self.ziel + ".lshow") as z:
            for name in z.namelist():
                text = z.read(name).decode("utf-8", "replace")
                with self.subTest(datei=name):
                    self.assertNotIn(sandbox.echter_home(), text)
                    self.assertNotIn(REPO, text)
                    self.assertNotIn("lightos_doku_", text)

    def test_echter_datenordner_unveraendert(self):
        self.assertEqual(sandbox.vergleiche(self.vorher, self.nachher,
                                            app_laeuft=self.app_laeuft), [])

    def test_vorhandene_datei_wird_nicht_ueberschrieben(self):
        pfad = self.ziel + ".lshow"
        vorher = os.stat(pfad).st_mtime_ns
        r = _lauf("--demo-show", pfad)
        self.assertEqual(r.returncode, 2, r.stdout[-2000:])
        self.assertIn("gibt es schon", r.stdout)
        self.assertEqual(os.stat(pfad).st_mtime_ns, vorher)

    def test_nicht_zusammen_mit_einer_anleitung(self):
        r = _lauf("vc", "--demo-show", os.path.join(self.ordner, "anders.lshow"))
        self.assertEqual(r.returncode, 2)
        self.assertFalse(os.path.exists(os.path.join(self.ordner, "anders.lshow")))


class SpurenTest(unittest.TestCase):
    """Die Spurensuche selbst: ein Heimatpfad in der Show wird gefunden."""

    def test_findet_einen_pfad_und_meldet_saubere_dateien_nicht(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_ab_werkzeug", os.path.join(TOOLS, "anleitungsbilder.py"))
        werkzeug = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(werkzeug)
        with tempfile.TemporaryDirectory() as tmp:
            heim = os.path.join(tmp, "heim", "konto")
            schmutzig = os.path.join(tmp, "a.lshow")
            with zipfile.ZipFile(schmutzig, "w") as z:
                z.writestr("show.json", json.dumps({"pfad": heim + "/Musik/x.mp3"}))
            sauber = os.path.join(tmp, "b.lshow")
            with zipfile.ZipFile(sauber, "w") as z:
                z.writestr("show.json", json.dumps({"pfad": "Musik/x.mp3"}))
            self.assertEqual(werkzeug._demo_show_spuren(schmutzig, [heim]), heim)
            self.assertEqual(werkzeug._demo_show_spuren(sauber, [heim]), "")


class NeueBilderTest(unittest.TestCase):
    """Szenen, Bilder, Manifest und Verweise der drei neu bebilderten Anleitungen."""

    ANLEITUNGEN = {
        "vc": "docs/anleitung_vc/ANLEITUNG_VC.md",
        "gruppen_matrizen": "docs/anleitung_gruppen_matrizen/ANLEITUNG_GRUPPEN_MATRIZEN.md",
        "musik_sync": "docs/anleitung_musik_sync/ANLEITUNG_MUSIK_SYNC.md",
    }

    def test_jede_szene_hat_ihr_bild_und_jedes_bild_einen_verweis(self):
        for name, md in self.ANLEITUNGEN.items():
            szenen, ziel = runner.lade_szenen(name)
            ordner = os.path.join(REPO, ziel)
            with open(os.path.join(REPO, md), encoding="utf-8") as f:
                text = f.read()
            with open(os.path.join(ordner, "bilder.json"), encoding="utf-8") as f:
                manifest = json.load(f)
            im_manifest = {b["datei"] for b in manifest["bilder"]}
            erwartet = {s.name + (".gif" if s.frames else ".png") for s in szenen}
            vorhanden = {f for f in os.listdir(ordner) if f.endswith((".png", ".gif"))}
            with self.subTest(anleitung=name):
                self.assertEqual(vorhanden, erwartet)
                self.assertEqual(im_manifest, erwartet)
                self.assertEqual(manifest["schrift"], runner.SCHRIFT_FAMILIE)
                for datei in erwartet:
                    self.assertIn(f"(img/{datei})", text, f"{md} verlinkt {datei} nicht")

    def test_alte_bilder_der_privaten_show_sind_weg(self):
        self.assertFalse(os.path.exists(os.path.join(REPO, "docs", "anleitung_vc", "gif")))
        for alt in ("01_vc_leer.png", "10_bank1_performance.png", "19_bank5_mh_spider.png"):
            self.assertFalse(os.path.exists(
                os.path.join(REPO, "docs", "anleitung_vc", "img", alt)))
        for alt in ("01_now_playing.png", "02_autoshow_laeuft.png"):
            self.assertFalse(os.path.exists(
                os.path.join(REPO, "docs", "anleitung_musik_sync", "img", alt)))


if __name__ == "__main__":
    unittest.main()
