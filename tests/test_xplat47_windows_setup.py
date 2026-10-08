"""XPLAT-47: Windows-Setup (PyInstaller onedir + Inno Setup) — was davon auf
Linux pruefbar ist.

Der eigentliche Build laeuft nur auf Windows (``.github/workflows/
windows-setup.yml``). Hier festgehalten, was ohne Windows kaputtgehen kann:

* ``main.py`` ruft ``multiprocessing.freeze_support()`` als ALLERERSTES — sonst
  startet der DMX-Worker (``spawn``) in der gepackten exe die ganze App erneut;
* mitgelieferte Dateien werden ueber ``paths.programm_dir()`` gefunden, auch
  gefroren (``sys.frozen``/``sys._MEIPASS`` simuliert, Ende zu Ende in einem
  Kindprozess gegen ein nachgebautes Bundle);
* das Bundle (``packaging/windows/bundle_inhalt.py``) enthaelt alles, was der
  Selbsttest als Pflicht fuehrt — und nur Git-bekannte Dateien (keine privaten
  Laufzeitdaten aus ``data/``/``shows/``);
* der Builtin-Fingerabdruck (``fixture_db._code_stand``) und die Versionsangabe
  des Audio-Mitschnitts funktionieren ohne Quelltextdateien;
* ``--selbsttest`` beendet sich ohne Fenster mit 0;
* Spec, Inno-Skript und Workflow tragen die vereinbarten Eckpunkte (onedir,
  Programme-Ordner, Verknuepfungen, Lizenzen, Version aus dem Repo, nur
  Artefakt — kein Release).
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from src.core import paths

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PACK = os.path.join(_REPO, "packaging", "windows")


def _lies(*teile: str) -> str:
    with open(os.path.join(_REPO, *teile), encoding="utf-8") as f:
        return f.read()


def _bundle_inhalt():
    spec = importlib.util.spec_from_file_location(
        "bundle_inhalt_xplat47", os.path.join(_PACK, "bundle_inhalt.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _baue_bundle(ziel: str) -> None:
    """Legt die ``datas`` der Spec so unter ``ziel`` ab, wie PyInstaller es in
    ``_MEIPASS`` tut (Quelle -> Zielordner, Dateiname bleibt)."""
    for quelle, ordner in _bundle_inhalt().datas(_REPO):
        z = os.path.join(ziel, ordner)
        os.makedirs(z, exist_ok=True)
        shutil.copy2(quelle, os.path.join(z, os.path.basename(quelle)))


# ── 1. freeze_support ────────────────────────────────────────────────────────

class FreezeSupportTest(unittest.TestCase):
    def test_freeze_support_ist_die_erste_anweisung(self):
        baum = ast.parse(_lies("main.py"))
        koerper = list(baum.body)
        if (koerper and isinstance(koerper[0], ast.Expr)
                and isinstance(getattr(koerper[0], "value", None), ast.Constant)):
            koerper = koerper[1:]                       # Modul-Docstring
        aufruf_index = None
        for i, knoten in enumerate(koerper):
            if (isinstance(knoten, ast.Expr) and isinstance(knoten.value, ast.Call)
                    and ast.unparse(knoten.value.func)
                    == "multiprocessing.freeze_support"):
                aufruf_index = i
                break
        self.assertIsNotNone(aufruf_index,
                             "main.py ruft multiprocessing.freeze_support() nicht "
                             "auf Modulebene auf")
        davor = koerper[:aufruf_index]
        # Davor darf nur ``import multiprocessing`` stehen — kein anderer Import,
        # keine stdout-Umleitung, nichts, was im Kindprozess Wirkung haette.
        self.assertEqual([ast.unparse(k) for k in davor], ["import multiprocessing"])

    def test_serial_worker_nutzt_spawn(self):
        """Die Begruendung oben haengt an ``spawn`` — aendert sich das, muss
        man hier neu nachdenken (bei ``fork`` gaebe es keinen exe-Neustart)."""
        self.assertIn('get_context("spawn")', _lies("src", "core", "dmx", "serial_process.py"))


# ── 2. Pfadaufloesung gefroren ───────────────────────────────────────────────

class ProgrammDirTest(unittest.TestCase):
    def test_quellbetrieb_ist_das_repo(self):
        with mock.patch.object(sys, "frozen", False, create=True):
            self.assertEqual(os.path.normcase(paths.programm_dir()),
                             os.path.normcase(_REPO))

    def test_gefroren_mit_meipass(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "_MEIPASS", d, create=True):
            self.assertTrue(paths.ist_gefroren())
            self.assertEqual(paths.programm_dir(), os.path.abspath(d))
            self.assertEqual(paths.programm_datei("assets", "x"),
                             os.path.join(os.path.abspath(d), "assets", "x"))

    def test_gefroren_ohne_meipass_ist_der_exe_ordner(self):
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, "LightOS.exe")
            with mock.patch.object(sys, "frozen", True, create=True), \
                    mock.patch.object(sys, "executable", exe), \
                    mock.patch.dict(sys.__dict__):
                sys.__dict__.pop("_MEIPASS", None)
                self.assertEqual(paths.programm_dir(), os.path.abspath(d))

    def test_app_datenordner_haengt_nicht_am_programmordner(self):
        """Programme ist schreibgeschuetzt: der Datenordner darf sich durch das
        Einfrieren nicht verschieben."""
        vorher = paths.app_data_dir()
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "_MEIPASS", d, create=True):
            self.assertEqual(paths.app_data_dir(), vorher)
            self.assertFalse(paths.app_data_dir().startswith(os.path.abspath(d)))


_PROBE_GEFROREN = r"""
import json, sys
sys.frozen = True
sys._MEIPASS = sys.argv[1]
sys.path.insert(0, sys.argv[2])
from src.core import paths, selbsttest, datenumzug
from src.core.controllers import controller_library as cl
from src.core.database import bibliothek_format as bf
from src.core.show import vc_gallery as vg
print(json.dumps({
    "programm_dir": paths.programm_dir(),
    "controller": cl._BUILTIN_DIR,
    "bibliothek": bf.BIBLIOTHEK_DIR,
    "galerie": vg.gallery_dir(),
    "datenumzug": datenumzug._REPO_ROOT,
    "galerie_eintraege": len(vg._manifest().get("items", [])),
    "fehlend": selbsttest.pruefe_ressourcen(),
}))
"""


class GefrorenEndeZuEndeTest(unittest.TestCase):
    """Kindprozess mit ``sys.frozen``/``sys._MEIPASS`` VOR dem ersten Import —
    so wie die gepackte exe die Module laedt. Das Bundle ist aus den ``datas``
    der Spec nachgebaut; das Repo dient nur noch als Code-Quelle."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.bundle = os.path.join(cls._tmp.name, "_internal")
        _baue_bundle(cls.bundle)
        env = dict(os.environ)
        env.pop("LIGHTOS_BIBLIOTHEK_DIR", None)
        r = subprocess.run([sys.executable, "-c", _PROBE_GEFROREN, cls.bundle, _REPO],
                           cwd=cls._tmp.name, env=env, capture_output=True,
                           text=True, timeout=120)
        if r.returncode != 0:
            raise AssertionError(f"Probe gescheitert:\n{r.stdout}\n{r.stderr}")
        cls.erg = json.loads(r.stdout.strip().splitlines()[-1])

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _unter_bundle(self, schluessel: str, *rel: str):
        self.assertEqual(os.path.normpath(self.erg[schluessel]),
                         os.path.normpath(os.path.join(self.bundle, *rel)), schluessel)

    def test_programmordner_ist_meipass(self):
        self._unter_bundle("programm_dir")

    def test_ressourcen_kommen_aus_dem_bundle(self):
        self._unter_bundle("controller", "data", "controller_library")
        self._unter_bundle("bibliothek", "fixtures", "bibliothek")
        self._unter_bundle("galerie", "assets", "vc_gallery")
        self._unter_bundle("datenumzug")

    def test_bundle_ist_vollstaendig(self):
        self.assertEqual(self.erg["fehlend"], [])
        self.assertGreater(self.erg["galerie_eintraege"], 0)


# ── 3. Bundle-Inhalt ─────────────────────────────────────────────────────────

class BundleInhaltTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bi = _bundle_inhalt()
        cls.dateien = cls.bi.dateien(_REPO)

    def test_selbsttest_pflicht_ist_abgedeckt(self):
        from src.core import selbsttest
        for rel in selbsttest.PFLICHT_RESSOURCEN:
            with self.subTest(rel=rel):
                self.assertTrue(any(d == rel or d.startswith(rel + "/")
                                    for d in self.dateien),
                                f"{rel} fehlt in bundle_inhalt")

    def test_nachgebautes_bundle_besteht_den_selbsttest(self):
        from src.core import selbsttest
        with tempfile.TemporaryDirectory() as d:
            _baue_bundle(d)
            self.assertEqual(selbsttest.pruefe_ressourcen(d), [])

    def test_visualizer_komplett(self):
        """Alles, was ``stage_scene.html`` per relativem Pfad nachlaedt."""
        for rel in ("src/ui/visualizer/stage_scene.html",
                    "src/ui/visualizer/three_local.js",
                    "src/ui/visualizer/scene_src/app.js",
                    "src/ui/visualizer/scene_src/bridge"):
            with self.subTest(rel=rel):
                self.assertTrue(any(d == rel or d.startswith(rel + "/")
                                    for d in self.dateien), rel)

    def test_keine_privaten_laufzeitdaten(self):
        for d in self.dateien:
            with self.subTest(d=d):
                self.assertFalse(d.startswith("shows/"), d)
                if d.startswith("data/"):
                    self.assertTrue(d.startswith("data/controller_library/"), d)
                self.assertFalse(d.endswith((".db", ".lshow", ".pyc")), d)

    def test_nur_git_bekannte_dateien(self):
        try:
            aus = subprocess.run(["git", "ls-files", "-z"], cwd=_REPO,
                                 capture_output=True, check=True)
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("kein Git")
        bekannt = set(aus.stdout.decode("utf-8").split("\0"))
        unbekannt = [d for d in self.dateien if d not in bekannt]
        self.assertEqual(unbekannt, [])

    def test_hidden_import_fuer_socketio_threading(self):
        """``SocketIO(async_mode="threading")`` laedt den Treiber per Name —
        ohne den Eintrag fehlt die Web-Remote in der exe."""
        self.assertIn('async_mode="threading"', _lies("src", "web", "app.py"))
        self.assertIn("engineio.async_drivers.threading", self.bi.HIDDEN_IMPORTS)


# ── 4. Laufzeit ohne Quelltextdateien ────────────────────────────────────────

class OhneQuelltextTest(unittest.TestCase):
    def test_code_stand_ohne_quelldatei_nicht_leer(self):
        from src.core.database import fixture_db
        normal = fixture_db._code_stand()
        self.assertTrue(normal)
        with mock.patch.object(fixture_db, "__file__",
                               os.path.join(tempfile.gettempdir(), "gibtsnicht",
                                            "fixture_db.pyc")):
            gefroren = fixture_db._code_stand()
        self.assertTrue(gefroren, "ohne Quelltext waere der Stand leer — dann "
                                  "liefe der Builtin-Abgleich nach Updates nie")
        self.assertNotEqual(gefroren, normal)

    def test_code_stand_pyc_endung_liest_die_py_daneben(self):
        from src.core.database import fixture_db
        normal = fixture_db._code_stand()
        quelle = os.path.abspath(fixture_db.__file__)
        with mock.patch.object(fixture_db, "__file__", quelle + "c"):
            self.assertEqual(fixture_db._code_stand(), normal)

    def test_version_ohne_main_py(self):
        from src.core.audio import audio_recorder as ar
        haupt = mock.Mock(APP_VERSION="9.8.7")
        with mock.patch.object(paths, "programm_datei",
                               lambda *t: os.path.join(tempfile.gettempdir(),
                                                       "gibtsnicht", *t)), \
                mock.patch.dict(sys.modules, {"__main__": haupt}):
            self.assertEqual(ar._lightos_version(), "9.8.7")

    def test_version_normalweg(self):
        from src.core.audio import audio_recorder as ar
        m = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', _lies("main.py"), re.M)
        self.assertEqual(ar._lightos_version(), m.group(1))


# ── 5. --selbsttest ──────────────────────────────────────────────────────────

class SelbsttestTest(unittest.TestCase):
    def test_main_selbsttest_beendet_ohne_fenster_mit_null(self):
        with tempfile.TemporaryDirectory() as d:
            bericht = os.path.join(d, "bericht.txt")
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
            r = subprocess.run([sys.executable, os.path.join(_REPO, "main.py"),
                                "--selbsttest", bericht],
                               cwd=d, env=env, capture_output=True, text=True,
                               timeout=180)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(bericht, encoding="utf-8") as f:
                text = f.read()
            self.assertIn("ERGEBNIS: ok", text)
            # Nichts im Arbeitsordner angelegt ausser dem Bericht.
            self.assertEqual(sorted(os.listdir(d)), ["bericht.txt"])

    def test_selbsttest_meldet_fehlendes(self):
        from src.core import selbsttest
        with tempfile.TemporaryDirectory() as d:
            fehler = selbsttest.pruefe_ressourcen(d)
        self.assertEqual(len(fehler), len(selbsttest.PFLICHT_RESSOURCEN))
        fehler = selbsttest.pruefe_module(("gibt_es_nicht_xplat47",))
        self.assertEqual(len(fehler), 1)
        self.assertIn("gibt_es_nicht_xplat47", fehler[0])

    def test_selbsttest_prueft_qtwebengine(self):
        from src.core import selbsttest
        self.assertIn("PySide6.QtWebEngineWidgets", selbsttest.PFLICHT_MODULE)
        self.assertIn("PySide6.QtWebEngineCore", selbsttest.PFLICHT_MODULE)

    def test_selbsttest_vor_der_einzelinstanz_sperre(self):
        quelle = _lies("main.py")
        self.assertLess(quelle.index("if args.selbsttest:"),
                        quelle.index("acquire_instance_lock("))


# ── 6. Spec, Inno-Skript, Workflow ───────────────────────────────────────────

class PackagingDateienTest(unittest.TestCase):
    def test_spec_onedir_mit_bundle_inhalt(self):
        s = _lies("packaging", "windows", "LightOS.spec")
        self.assertIn("bundle_inhalt.datas(REPO)", s)
        self.assertIn("exclude_binaries=True", s)       # onedir
        self.assertIn("COLLECT(", s)
        self.assertIn("console=False", s)
        self.assertIn("lightos.ico", s)
        self.assertIn("bundle_inhalt.HIDDEN_IMPORTS", s)

    def test_iss_eckpunkte(self):
        s = _lies("packaging", "windows", "LightOS.iss")
        for muss in ("DefaultDirName={autopf}\\LightOS",
                     "OutputBaseFilename=LightOS-Setup",
                     "AppVersion={#AppVersion}",
                     "#ifndef AppVersion",
                     "ArchitecturesAllowed=x64compatible",
                     "{autoprograms}\\LightOS",
                     "{autodesktop}\\LightOS",
                     'Name: "desktopicon"',
                     "THIRD_PARTY_NOTICES.md",
                     "\\licenses\\*",
                     "dist\\LightOS",
                     "LightOS.exe"):
            with self.subTest(muss=muss):
                self.assertIn(muss, s)

    def test_workflow_eckpunkte(self):
        s = _lies(".github", "workflows", "windows-setup.yml")
        for muss in ("runs-on: windows-latest", "workflow_dispatch:",
                     'tags: ["v*"]', "packaging/windows/LightOS.spec",
                     "--selbsttest", "/DAppVersion=", "actions/upload-artifact",
                     "LightOS-Setup.exe", "innosetup", "APP_VERSION"):
            with self.subTest(muss=muss):
                self.assertIn(muss, s)

    def test_workflow_veroeffentlicht_nichts(self):
        s = _lies(".github", "workflows", "windows-setup.yml")
        code = "\n".join(z for z in s.splitlines() if not z.lstrip().startswith("#"))
        for verboten in ("action-gh-release", "gh release", "create-release",
                         "upload-release-asset", "contents: write"):
            with self.subTest(verboten=verboten):
                self.assertNotIn(verboten, code)


if __name__ == "__main__":
    unittest.main()
