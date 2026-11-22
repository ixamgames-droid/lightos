"""XPLAT-62: .deb-Paket fuer Mint/Ubuntu/Debian — Aufbau aus einem kuenstlichen
Programmordner.

Der echte Bau (PyInstaller + Paket + Installation im frischen Container) laeuft
im Workflow ``.github/workflows/linux-paket.yml``. Hier wird geprueft, was
``packaging/linux/baue_deb.py`` aus einem nachgebauten PyInstaller-Ordner
macht: control-Felder, Pfade, Starter, desktop-Datei, Symbol, udev-Regel,
Rechte der Maintainer-Skripte, Lizenztexte — und dass kein privater Pfad im
Paket landet.
"""
from __future__ import annotations

import configparser
import importlib.util
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LINUX = os.path.join(_REPO, "packaging", "linux")
_WORKFLOW = os.path.join(_REPO, ".github", "workflows", "linux-paket.yml")


def _lade_baue_deb():
    spec = importlib.util.spec_from_file_location(
        "xplat62_baue_deb", os.path.join(_LINUX, "baue_deb.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(*args, **kw):
    return subprocess.run(list(args), check=True, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", **kw)


@unittest.skipUnless(shutil.which("dpkg-deb"), "dpkg-deb fehlt")
class DebAusKuenstlichemOrdner(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.bd = _lade_baue_deb()
        cls.tmp = tempfile.mkdtemp(prefix="xplat62-")
        prog = os.path.join(cls.tmp, "dist", "LightOS")
        os.makedirs(os.path.join(prog, "_internal", "licenses", "pakete"))
        with open(os.path.join(prog, "LightOS"), "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\necho kuenstlich\n")
        os.chmod(os.path.join(prog, "LightOS"), 0o700)
        lib = os.path.join(prog, "_internal", "libbeispiel.so")
        with open(lib, "wb") as f:
            f.write(b"\x7fELF")
        os.chmod(lib, 0o775)          # gruppenschreibbar -> muss 0755 werden
        with open(os.path.join(prog, "_internal", "licenses",
                               "BUNDLE-KOMPONENTEN.txt"), "w",
                  encoding="utf-8") as f:
            f.write("Liste\n")
        cls.deb = cls.bd.baue(prog, os.path.join(cls.tmp, "aus"), "1.2.3")
        cls.baum = os.path.join(cls.tmp, "baum")
        _run("dpkg-deb", "-x", cls.deb, cls.baum)
        cls.ctrl = os.path.join(cls.tmp, "ctrl")
        _run("dpkg-deb", "-e", cls.deb, cls.ctrl)
        cls.inhalt = _run("dpkg-deb", "--contents", cls.deb).stdout

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _feld(self, name):
        return _run("dpkg-deb", "-f", self.deb, name).stdout.strip()

    def test_dateiname_und_control(self):
        self.assertEqual(os.path.basename(self.deb), "lightos_1.2.3_amd64.deb")
        self.assertEqual(self._feld("Package"), "lightos")
        self.assertEqual(self._feld("Version"), "1.2.3")
        self.assertEqual(self._feld("Architecture"), "amd64")
        self.assertTrue(self._feld("Installed-Size").isdigit())
        dep = self._feld("Depends")
        for d in ("libc6", "libxcb-cursor0", "libnss3", "libusb-1.0-0",
                  "libwayland-server0"):
            self.assertIn(d, dep)
        # Python und Qt bringt PyInstaller mit — nie als Systemabhaengigkeit.
        self.assertNotRegex(dep, r"python3|libqt6|pyside")
        self.assertIn("Vorabversion", self._feld("Description"))

    def test_pfade(self):
        for p in ("./opt/lightos/LightOS", "./usr/bin/lightos",
                  "./usr/share/applications/lightos.desktop",
                  "./usr/share/icons/hicolor/256x256/apps/lightos.png",
                  "./usr/lib/udev/rules.d/60-lightos-udmx.rules",
                  "./usr/share/doc/lightos/copyright",
                  "./usr/share/doc/lightos/licenses/BUNDLE-KOMPONENTEN.txt",
                  "./opt/lightos/_internal/licenses/BUNDLE-KOMPONENTEN.txt"):
            self.assertIn(p, self.inhalt)
        self.assertIn("LICENSE", self.bd.DOKU_DATEIEN)
        self.assertEqual(len(self.bd.DOKU_DATEIEN), 2)
        for name in self.bd.DOKU_DATEIEN:
            self.assertIn(f"./usr/share/doc/lightos/{name}", self.inhalt)
        # Dateien gehoeren root (gebaut ohne root, --root-owner-group).
        for zeile in self.inhalt.splitlines():
            self.assertIn("root/root", zeile)

    def test_starter_und_rechte(self):
        starter = os.path.join(self.baum, "usr", "bin", "lightos")
        with open(starter, encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("#!/bin/sh"))
        self.assertIn('exec /opt/lightos/LightOS "$@"', text)
        self.assertEqual(stat.S_IMODE(os.stat(starter).st_mode), 0o755)
        prog = os.path.join(self.baum, "opt", "lightos", "LightOS")
        self.assertEqual(stat.S_IMODE(os.stat(prog).st_mode), 0o755)
        lib = os.path.join(self.baum, "opt", "lightos", "_internal", "libbeispiel.so")
        self.assertEqual(stat.S_IMODE(os.stat(lib).st_mode), 0o755)
        regel = os.path.join(self.baum, "usr", "lib", "udev", "rules.d",
                             "60-lightos-udmx.rules")
        self.assertEqual(stat.S_IMODE(os.stat(regel).st_mode), 0o644)
        for ordner, _u, dateien in os.walk(self.baum):
            for n in dateien:
                m = os.stat(os.path.join(ordner, n)).st_mode
                self.assertFalse(m & (stat.S_IWGRP | stat.S_IWOTH), n)

    def test_desktop_datei_gueltig(self):
        pfad = os.path.join(self.baum, "usr", "share", "applications",
                            "lightos.desktop")
        cp = configparser.ConfigParser(interpolation=None)
        cp.optionxform = str
        cp.read(pfad, encoding="utf-8")
        e = cp["Desktop Entry"]
        self.assertEqual(e["Type"], "Application")
        self.assertEqual(e["Name"], "LightOS")
        self.assertEqual(e["Exec"].split()[0], "lightos")
        # main.py kennt keine Positionsargumente: kein %F/%f/%U im Exec.
        self.assertNotIn("%", e["Exec"])
        self.assertEqual(e["Icon"], "lightos")
        self.assertEqual(e["Terminal"], "false")
        self.assertTrue(e["Categories"].endswith(";"))
        if shutil.which("desktop-file-validate"):
            r = subprocess.run(["desktop-file-validate", pfad], capture_output=True,
                               text=True, encoding="utf-8", errors="replace")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_udev_regel_unveraendert(self):
        with open(os.path.join(_LINUX, "60-lightos-udmx.rules"), "rb") as f:
            quelle = f.read()
        with open(os.path.join(self.baum, "usr", "lib", "udev", "rules.d",
                               "60-lightos-udmx.rules"), "rb") as f:
            self.assertEqual(f.read(), quelle)

    def test_maintainer_skripte(self):
        for name in ("postinst", "postrm"):
            p = os.path.join(self.ctrl, name)
            self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o755, name)
            with open(p, encoding="utf-8") as f:
                text = f.read()
            self.assertTrue(text.startswith("#!/bin/sh"), name)
            self.assertIn("udevadm control --reload-rules", text)
            _run("sh", "-n", p)
            # Benutzerkonten und Benutzerdaten fasst das Paket nie an.
            for verboten in ("usermod -", "adduser", "gpasswd", "rm -", ".local/share"):
                code = "\n".join(z for z in text.splitlines()
                                 if not z.lstrip().startswith(("#", "echo")))
                self.assertNotIn(verboten, code, f"{name}: {verboten}")
        with open(os.path.join(self.ctrl, "postinst"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("dialout", text)

    def test_kein_privater_pfad(self):
        muster = re.compile(r"/home/|/Users/|C:\\\\Users", re.I)
        for wurzel in (self.baum, self.ctrl):
            for ordner, _u, dateien in os.walk(wurzel):
                for n in dateien:
                    p = os.path.join(ordner, n)
                    if n.endswith(".png") or n.endswith(".so"):
                        continue
                    with open(p, encoding="utf-8", errors="replace") as f:
                        self.assertIsNone(muster.search(f.read()), p)


class OhneProgrammordner(unittest.TestCase):

    def test_fehlender_ordner_bricht_ab(self):
        bd = _lade_baue_deb()
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(bd.main(["--programm", os.path.join(tmp, "fehlt"),
                                      "--ausgabe", tmp, "--version", "1.0.0"]), 1)
            self.assertEqual(os.listdir(tmp), [])

    def test_version(self):
        bd = _lade_baue_deb()
        self.assertRegex(bd.app_version(), r"^\d")
        self.assertEqual(bd.pruefe_version("v1.0.0"), "1.0.0")
        with self.assertRaises(ValueError):
            bd.pruefe_version("eins")


class Workflow(unittest.TestCase):

    def setUp(self):
        with open(_WORKFLOW, encoding="utf-8") as f:
            self.text = f.read()

    def test_gueltiges_yaml(self):
        try:
            import yaml
        except ImportError:
            yaml = None
        if yaml is not None:
            daten = yaml.safe_load(self.text)
            self.assertIn("deb", daten["jobs"])
        self.assertNotIn("\t", self.text)

    def test_eckpunkte(self):
        self.assertIn("workflow_dispatch", self.text)
        self.assertRegex(self.text, r'tags:\s*\["v\*"\]')
        self.assertIn("packaging/linux/LightOS.spec", self.text)
        self.assertIn("packaging/linux/baue_deb.py", self.text)
        self.assertIn("actions/upload-artifact", self.text)
        self.assertIn("--selbsttest", self.text)
        self.assertIn("ubuntu:24.04", self.text)
        # Nur Artefakt, kein Release (wie windows-setup.yml).
        self.assertNotRegex(self.text, r"(?i)softprops|action-gh-release|gh release")
        self.assertIn("contents: read", self.text)

    def test_spec_teilt_bundle_inhalt(self):
        with open(os.path.join(_LINUX, "LightOS.spec"), encoding="utf-8") as f:
            spec = f.read()
        self.assertIn("import bundle_inhalt", spec)
        self.assertIn("fremdkomponenten", spec)
        self.assertIn('name="LightOS"', spec)
        self.assertIn("COLLECT(", spec)   # onedir


if __name__ == "__main__":
    unittest.main()


def test_linux_paket_bringt_pyusb_mit():
    """Erster CI-Lauf: ``usb.core`` fehlte im Paket (pyusb steht in
    requirements.txt nur fuer Windows) — uDMX ginge im .deb nicht."""
    with open(os.path.join(_REPO, ".github", "workflows", "linux-paket.yml"),
              encoding="utf-8") as f:
        assert "pyusb" in f.read()
