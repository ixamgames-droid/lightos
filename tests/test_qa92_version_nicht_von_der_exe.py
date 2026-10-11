"""QA-92: „Über LightOS“ und das Diagnosepaket nennen die LightOS-Version —
nicht die der laufenden EXE.

Befund am Windows-Testrechner (Gate auf ``main``): ``test_ui85_hilfe_menue``
sah im Dialog „LightOS 3.12.10150.1013“. ``hilfe.app_version()`` fragte zuerst
``QApplication.applicationVersion()``. Hat dort niemand eine Version gesetzt,
liefert Qt unter Windows die Dateiversion der laufenden EXE — im Quellbetrieb
die von ``python.exe``. Unter Linux ist der Wert dann leer, der Rueckfall auf
``APP_VERSION`` griff, und der Fehler blieb unsichtbar.

Die echte App setzt die Version in ``main.py`` selbst; betroffen war jeder
andere Weg zu einem Hauptfenster (Tests, Werkzeuge). Damit der Fall auf JEDEM
Betriebssystem geprueft wird, setzt der Test die fremde Version ausdruecklich.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                          # noqa: E402
from PySide6.QtWidgets import QApplication             # noqa: E402

from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15

_app = QApplication.instance() or QApplication([])

#: So meldet Qt unter Windows die Version, wenn nur ``python.exe`` laeuft.
VERSION_DER_EXE = "3.12.10150.1013"


def _app_version() -> str:
    m = re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']',
                  (ROOT / "main.py").read_text(encoding="utf-8"), re.M)
    assert m, "APP_VERSION nicht in main.py gefunden"
    return m.group(1)


@pytest.fixture
def fremde_qt_version():
    """Qt-Anwendungsversion wie unter Windows ohne ``setApplicationVersion``."""
    vorher = QApplication.applicationVersion()
    QApplication.setApplicationVersion(VERSION_DER_EXE)
    yield VERSION_DER_EXE
    QApplication.setApplicationVersion(vorher)


def test_app_version_ist_die_von_lightos(fremde_qt_version):
    from src.ui import hilfe
    assert hilfe.app_version() == _app_version()
    text = hilfe.ueber_text()
    assert f"LightOS {_app_version()}" in text
    assert fremde_qt_version not in text


def test_qt_version_bleibt_der_rueckfall():
    """Ist ``APP_VERSION`` nicht ermittelbar, gilt weiter, was Qt weiss —
    und ohne beides „?“ statt eines leeren Feldes."""
    from src.ui import hilfe
    vorher = QApplication.applicationVersion()
    try:
        with mock.patch("src.core.audio.audio_recorder._lightos_version",
                        return_value=None):
            QApplication.setApplicationVersion("7.7.7")
            assert hilfe.app_version() == "7.7.7"
        with mock.patch("src.core.audio.audio_recorder._lightos_version",
                        side_effect=RuntimeError("kaputt")):
            assert hilfe.app_version() == "7.7.7"
    finally:
        QApplication.setApplicationVersion(vorher)


def test_diagnosepaket_bekommt_die_lightos_version(fremde_qt_version, tmp_path):
    """Derselbe Weg wie Hilfe → „Diagnosepaket speichern…“ (Ziel vorgegeben =
    ohne Dialoge). Die Version steht im Paket in der Zeile ``LightOS:``."""
    from src.core.show import show_file as SF
    from src.ui import main_window as mw
    SF.reset_show()
    win = mw.MainWindow()
    try:
        ziel = str(tmp_path / "paket.zip")
        with mock.patch("src.core.diagnose_log.erstelle_diagnosepaket",
                        return_value=ziel) as bau, \
             mock.patch("src.core.diagnose_log.melde_laufzeit_umgebung"):
            assert win._diagnosepaket_speichern(ziel) == ziel
        assert bau.call_count == 1
        assert bau.call_args[0] == (ziel, _app_version()), (
            f"Diagnosepaket mit Version {bau.call_args[0][1]!r} geschrieben")
    finally:
        win.deleteLater()
        destroy_all_top_level_widgets(QApplication.instance())
