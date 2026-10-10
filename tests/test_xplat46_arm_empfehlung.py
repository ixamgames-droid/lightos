"""XPLAT-46: auf Windows-ARM wird x64-Python empfohlen, ARM64 nur "ohne 3D".

Entscheidung des Projektinhabers vom 05.10.2026. Hintergrund (XPLAT-45): die
nativen win_arm64-Wheels von PySide6-Addons haben kein QtWebEngine, mit
ARM64-Python fehlt also der 3D-Visualizer. Vorher rieten Installer, INSTALL.md
und CONTRIBUTING.md genau zu diesem Python, und die Visualizer-Fehlermeldung
empfahl "PySide6-Addons neu installieren" - was dort nichts aendert.

Geprueft wird:
* der Installer warnt bei nativem ARM64-Python (nicht mehr bei x64) und nennt
  einen funktionierenden winget-Befehl fuer x64-Python,
* INSTALL.md und CONTRIBUTING.md geben dieselbe Empfehlung,
* die Meldung "Visualizer nicht verfuegbar" nennt auf nativem ARM64 x64-Python
  als Abhilfe, sonst den bisherigen Rat - auch im echten MainWindow-Pfad.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def installer(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    import install
    return install


def _installer_ausgabe(installer, monkeypatch, capsys, *, py_arch, os_arch):
    monkeypatch.setattr(installer, "detect_arch", lambda: py_arch)
    monkeypatch.setattr(installer, "detect_native_os_arch", lambda: os_arch)
    monkeypatch.setattr(installer.os, "name", "nt")
    installer.check_arm_runtime()
    return capsys.readouterr().out


class TestInstaller:
    def test_natives_arm64_warnt_ohne_3d_und_empfiehlt_x64(self, installer, monkeypatch, capsys):
        out = _installer_ausgabe(installer, monkeypatch, capsys,
                                 py_arch="arm64", os_arch="arm64")
        assert "WARN" in out
        assert "3D-Visualizer" in out
        assert "--architecture x64" in out
        assert "--arch arm64" not in out
        assert "Bitte ARM64-Python installieren" not in out

    def test_x64_auf_arm_ist_der_empfohlene_weg(self, installer, monkeypatch, capsys):
        out = _installer_ausgabe(installer, monkeypatch, capsys,
                                 py_arch="x64", os_arch="arm64")
        assert "WARN" not in out
        assert "empfohlen" in out.lower()

    def test_x64_auf_x64_bleibt_still(self, installer, monkeypatch, capsys):
        out = _installer_ausgabe(installer, monkeypatch, capsys,
                                 py_arch="x64", os_arch="x64")
        assert "WARN" not in out
        assert "ARM" not in out

    def test_zusammenfassung_warnt_nur_bei_nativem_arm64(self, installer, monkeypatch, capsys):
        monkeypatch.setattr(installer.os, "name", "nt")
        monkeypatch.setattr(installer, "detect_native_os_arch", lambda: "arm64")
        monkeypatch.setattr(installer, "detect_arch", lambda: "x64")
        installer.show_summary()
        assert "WARN" not in capsys.readouterr().out
        monkeypatch.setattr(installer, "detect_arch", lambda: "arm64")
        installer.show_summary()
        out = capsys.readouterr().out
        assert "WARN" in out and "3D-Visualizer" in out

    def test_winget_befehl_nutzt_die_echte_option(self, installer):
        # winget kennt "--architecture" (Kurzform "-a"), keine Option "--arch".
        assert re.search(r"--architecture x64\b", installer.X64_PYTHON_BEFEHL)


class TestDoku:
    def test_install_md_empfiehlt_x64_auf_arm(self):
        text = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        assert "--arch arm64" not in text
        assert "winget install Python.Python.3.12 --architecture x64" in text
        assert "ohne 3D-Visualizer" in text
        assert "| PySide6-Addons | OK (ARM64-Wheel) |" not in text
        assert "tools/qt_module_befund.py" in text

    def test_contributing_md_empfiehlt_x64_auf_arm(self):
        text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        assert "nicht x64-Emulation" not in text
        zeile = next(z for z in text.splitlines() if z.startswith("**Windows ARM64:**"))
        assert "x64-Python" in zeile and "ohne 3D-Visualizer" in zeile


class TestVisualizerMeldung:
    def test_natives_arm64_nennt_x64_als_abhilfe(self):
        from src.core.plattform_hinweis import visualizer_startfehler_text
        text = visualizer_startfehler_text(
            ImportError("No module named 'PySide6.QtWebEngineWidgets'"),
            system="nt", py_arch="arm64")
        assert "x64-Python" in text
        assert "--architecture x64" in text
        assert "PySide6-Addons korrekt installiert" not in text

    @pytest.mark.parametrize("system,py_arch,exc", [
        ("nt", "x64", ImportError("x")),
        ("posix", "arm64", ImportError("x")),
        ("nt", "arm64", RuntimeError("Fenster kaputt")),
    ])
    def test_sonst_bleibt_der_alte_rat(self, system, py_arch, exc):
        from src.core.plattform_hinweis import visualizer_startfehler_text
        text = visualizer_startfehler_text(exc, system=system, py_arch=py_arch)
        assert "PySide6-Addons korrekt installiert" in text
        assert "x64-Python" not in text

    def test_interpreter_arch_liest_den_prozess_nicht_den_host(self, monkeypatch):
        # platform.machine() meldet auf emuliertem x64-Python 'ARM64' (Host);
        # massgeblich ist sysconfig.get_platform() (Prozess).
        import src.core.plattform_hinweis as ph
        monkeypatch.setattr(ph.sysconfig, "get_platform", lambda: "win-amd64")
        monkeypatch.setattr(ph.platform, "machine", lambda: "ARM64")
        assert ph.interpreter_arch() == "x64"
        monkeypatch.setattr(ph.sysconfig, "get_platform", lambda: "win-arm64")
        assert ph.interpreter_arch() == "arm64"

    def test_mainwindow_zeigt_den_arm_hinweis(self, monkeypatch):
        """Der echte _open_visualizer-Pfad: Import scheitert wie auf ARM64."""
        import src.core.plattform_hinweis as ph
        import src.ui.main_window as mw

        monkeypatch.setattr(ph.os, "name", "nt")
        monkeypatch.setattr(ph, "interpreter_arch", lambda: "arm64")
        # None in sys.modules laesst "from ... import" mit ImportError scheitern.
        monkeypatch.setitem(sys.modules, "src.ui.visualizer.visualizer_window", None)
        gezeigt = []
        monkeypatch.setattr(mw.QMessageBox, "warning",
                            lambda *a, **k: gezeigt.append(a))

        class _Fenster:
            _visualizer_window = None

        fenster = _Fenster()
        mw.MainWindow._open_visualizer(fenster)
        assert fenster._visualizer_window is None
        assert len(gezeigt) == 1
        titel, text = gezeigt[0][1], gezeigt[0][2]
        assert titel == "Visualizer nicht verfügbar"
        assert "x64-Python" in text
