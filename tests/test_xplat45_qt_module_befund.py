"""XPLAT-45 — Befund-Werkzeug ``tools/qt_module_befund.py``.

Die Windows-ARM64-Leg der CI ruft es zweimal auf: im nativen ARM64-venv als
reinen Befund (Exit 0, auch ohne QtWebEngine) und im x64-venv der Suite mit
``--erwarte-webengine`` (Exit 1 ohne QtWebEngine). Hier mit einem gefaelschten
Importer, damit der Test auf jeder Plattform dasselbe prueft.
"""
import io
import os
import sys
import types
import unittest
from contextlib import redirect_stdout
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import qt_module_befund as qb  # noqa: E402


def _importer(fehlend=()):
    def imp(name):
        kurz = name.rsplit(".", 1)[-1]
        if kurz in fehlend:
            raise ImportError(f"cannot import name '{kurz}' from 'PySide6'")
        return types.SimpleNamespace(__version__="6.11.2")
    return imp


def _lauf(argv, importer, plattform="win-arm64"):
    out = io.StringIO()
    with mock.patch.object(qb.sysconfig, "get_platform", return_value=plattform), \
            redirect_stdout(out):
        rc = qb.main(argv, importer=importer)
    return rc, out.getvalue()


class QtModulBefundTest(unittest.TestCase):

    def test_natives_arm64_ohne_webengine_ist_nur_befund(self):
        rc, log = _lauf([], _importer({"QtWebEngineCore", "QtWebEngineWidgets"}))
        self.assertEqual(rc, 0, log)
        self.assertIn("FEHLT QtWebEngineWidgets", log)
        self.assertIn("ok    QtWidgets", log)
        self.assertIn("kein QtWebEngine", log)

    def test_erwartete_webengine_fehlt_ist_rot(self):
        rc, log = _lauf(["--erwarte-webengine"], _importer({"QtWebEngineWidgets"}),
                        plattform="win-amd64")
        self.assertEqual(rc, 1, log)

    def test_x64_mit_webengine_ist_gruen(self):
        rc, log = _lauf(["--erwarte-webengine"], _importer(), plattform="win-amd64")
        self.assertEqual(rc, 0, log)
        self.assertNotIn("FEHLT", log)

    def test_webengine_im_arm64_wheel_wird_als_neu_gemeldet(self):
        rc, log = _lauf([], _importer())
        self.assertEqual(rc, 0, log)
        self.assertIn("NEU", log)

    def test_interpreter_arch_auch_unter_emulation(self):
        # platform.machine() sagt unter Emulation 'ARM64' — entscheidend ist
        # der Interpreter-Build.
        with mock.patch.object(qb.sysconfig, "get_platform", return_value="win-amd64"), \
                mock.patch.object(qb.platform, "machine", return_value="ARM64"):
            self.assertEqual(qb.interpreter_arch(), "x64")
        with mock.patch.object(qb.sysconfig, "get_platform", return_value="win-arm64"):
            self.assertEqual(qb.interpreter_arch(), "arm64")

    def test_echtes_pyside6_laesst_sich_befunden(self):
        # Ohne Faelschung: das Werkzeug laeuft im Suite-venv durch.
        out = io.StringIO()
        with redirect_stdout(out):
            rc = qb.main([])
        self.assertEqual(rc, 0, out.getvalue())
        self.assertIn("ok    QtCore", out.getvalue())


if __name__ == "__main__":
    unittest.main()
