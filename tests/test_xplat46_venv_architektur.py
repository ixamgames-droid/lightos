"""XPLAT-46 / Codex-Review #967: der Rat "x64-Python, dann install.py erneut"
muss auch wirken.

Zwei Luecken:
* ``create_venv()`` kehrte bei vorhandenem ``venv/`` sofort zurueck — das mit
  ARM64-Python gebaute venv blieb, und damit weiter kein QtWebEngine/3D.
  Jetzt erkennt der Installer ein venv mit fremder Architektur und fragt nach;
  ``--neu-venv`` baut es ohne Rueckfrage neu.
* ``py -3.12-64`` heisst seit Python 3.11 nur "nicht 32-bit" und kann bei
  parallel installiertem ARM64-Python dieses treffen. Die Hinweise nennen
  jetzt den Pfad des x64-Interpreters (aus ``py -0p`` oder den Standardort).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def installer(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(ROOT))
    import install
    venv = tmp_path / "venv"
    venv.mkdir()
    (venv / "alt.txt").write_text("arm64", encoding="utf-8")
    monkeypatch.setattr(install, "VENV_DIR", venv)
    aufrufe = []
    monkeypatch.setattr(install.subprocess, "run",
                        lambda cmd, *a, **k: aufrufe.append(list(cmd)))
    install._test_aufrufe = aufrufe
    return install


def _neu_gebaut(installer) -> bool:
    venv_aufrufe = [c for c in installer._test_aufrufe if "-m" in c and "venv" in c]
    return bool(venv_aufrufe) and not (installer.VENV_DIR / "alt.txt").exists()


class TestVenvArchitektur:
    def test_fremde_architektur_mit_ja_baut_neu(self, installer, monkeypatch):
        monkeypatch.setattr(installer, "venv_arch", lambda: "arm64")
        monkeypatch.setattr(installer, "detect_arch", lambda: "x64")
        monkeypatch.setattr(installer, "_frage_ja", lambda frage: True)
        installer.create_venv()
        assert _neu_gebaut(installer)

    def test_fremde_architektur_ohne_terminal_bleibt_und_nennt_schalter(
            self, installer, monkeypatch, capsys):
        monkeypatch.setattr(installer, "venv_arch", lambda: "arm64")
        monkeypatch.setattr(installer, "detect_arch", lambda: "x64")
        monkeypatch.setattr(installer.sys, "stdin", None)
        installer.create_venv()
        assert not _neu_gebaut(installer)
        out = capsys.readouterr().out
        assert "arm64" in out and "--neu-venv" in out

    def test_gleiche_architektur_bleibt_ohne_frage(self, installer, monkeypatch):
        monkeypatch.setattr(installer, "venv_arch", lambda: "x64")
        monkeypatch.setattr(installer, "detect_arch", lambda: "x64")

        def _nie(frage):
            raise AssertionError("keine Rueckfrage erwartet")
        monkeypatch.setattr(installer, "_frage_ja", _nie)
        installer.create_venv()
        assert not _neu_gebaut(installer)

    def test_schalter_neu_venv_baut_immer_neu(self, installer, monkeypatch):
        monkeypatch.setattr(installer, "venv_arch", lambda: "x64")
        monkeypatch.setattr(installer, "detect_arch", lambda: "x64")
        installer.create_venv(neu=True)
        assert _neu_gebaut(installer)

    def test_main_reicht_den_schalter_durch(self, installer, monkeypatch):
        gesehen = []
        for name in ("check_python", "check_arm_runtime", "install_requirements",
                     "create_directories", "create_shortcut", "write_manifest",
                     "show_summary"):
            monkeypatch.setattr(installer, name, lambda *a, **k: [])
        monkeypatch.setattr(installer, "create_venv", lambda neu=False: gesehen.append(neu))
        monkeypatch.setattr(sys, "argv", ["install.py", "--neu-venv", "--no-shortcut"])
        installer.main()
        monkeypatch.setattr(sys, "argv", ["install.py", "--no-shortcut"])
        installer.main()
        assert gesehen == [True, False]


class TestX64Auswahl:
    LISTE_NEU = (
        " -V:3.12-arm64 *    C:\\Py\\Python312-arm64\\python.exe\n"
        " -V:3.12           C:\\Py\\Python312\\python.exe\n"
        " -V:3.11-32        C:\\Py\\Python311-32\\python.exe\n"
    )
    LISTE_ALT = (
        " -3.12-arm64 *      C:\\Py\\Python312-arm64\\python.exe\n"
        " -3.12-64           C:\\Py\\Python312\\python.exe\n"
    )

    def test_liste_waehlt_x64_nicht_arm64(self, installer):
        assert installer.x64_python_aus_liste(self.LISTE_NEU) == "C:\\Py\\Python312\\python.exe"
        assert installer.x64_python_aus_liste(self.LISTE_ALT) == "C:\\Py\\Python312\\python.exe"

    def test_install_manager_tag_mit_klammern(self, installer):
        # "py -0p" des Python-Install-Managers (ab 3.14), so am Windows-ARM-PC
        # gemessen: der optionale Zusatz steht in eckigen Klammern.
        liste = (" -V:3.14-arm64     C:\\Py\\pythoncore-3.14-arm64\\python.exe\n"
                 " -V:3.14[-64] *   C:\\Py\\pythoncore-3.14-64\\python.exe\n")
        assert (installer.x64_python_aus_liste(liste)
                == "C:\\Py\\pythoncore-3.14-64\\python.exe")
        nur_arm = " -V:3.14[-arm64] *   C:\\Py\\pythoncore-3.14-arm64\\python.exe\n"
        assert installer.x64_python_aus_liste(nur_arm) is None

    def test_nur_arm64_und_32bit_ergibt_nichts(self, installer):
        liste = (" -V:3.12-arm64 *  C:\\Py\\Python312-arm64\\python.exe\n"
                 " -V:3.11-32       C:\\Py\\Python311-32\\python.exe\n")
        assert installer.x64_python_aus_liste(liste) is None

    def test_arm_warnung_nennt_eindeutigen_aufruf(self, installer, monkeypatch, capsys):
        monkeypatch.setattr(installer, "detect_arch", lambda: "arm64")
        monkeypatch.setattr(installer, "detect_native_os_arch", lambda: "arm64")
        monkeypatch.setattr(installer.os, "name", "nt")
        monkeypatch.setattr(installer, "finde_x64_python",
                            lambda: "C:\\Py\\Python312\\python.exe")
        installer.check_arm_runtime()
        out = capsys.readouterr().out
        assert '"C:\\Py\\Python312\\python.exe" install.py --neu-venv' in out
        assert "py -3.12-64" not in out

    def test_arm_warnung_ohne_fund_nennt_standardpfad(self, installer, monkeypatch, capsys):
        monkeypatch.setattr(installer, "detect_arch", lambda: "arm64")
        monkeypatch.setattr(installer, "detect_native_os_arch", lambda: "arm64")
        monkeypatch.setattr(installer.os, "name", "nt")
        monkeypatch.setattr(installer, "finde_x64_python", lambda: None)
        installer.check_arm_runtime()
        out = capsys.readouterr().out
        assert "Python312\\python.exe" in out and "--neu-venv" in out


class TestHinweisUndDoku:
    def test_visualizer_hinweis_nennt_neu_venv(self):
        from src.core.plattform_hinweis import visualizer_startfehler_text
        text = visualizer_startfehler_text(ImportError("x"), system="nt", py_arch="arm64")
        assert "--neu-venv" in text
        assert "py -3.12-64" not in text
        assert "-arm64" in text

    def test_install_md_nennt_neu_venv_statt_mehrdeutigem_selektor(self):
        text = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        assert "install.py --neu-venv" in text
        assert "`py -3.12-64 install.py`" not in text
