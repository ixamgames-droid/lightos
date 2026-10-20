"""XPLAT-51: natives ARM64-Python heisst ueberall "nicht unterstuetzt".

Befund am Windows-ARM-PC (10.10.2026): mit einem venv aus nativem ARM64-Python
stuerzte LightOS in 6 von 12 Starts mit Access Violation ab, an wechselnden
Stellen im Hauptthread; mit x64-Python und derselben PySide6-Version nie. Dazu
fehlt unter ARM64 QtWebEngine (XPLAT-45). Installer, Plattform-Hinweis,
Startskripte und Doku sagten trotzdem "laeuft ohne 3D-Visualizer".

Neuer Wortlaut je Stelle: "nicht unterstuetzt (instabil, kein 3D) - x64-Python
nehmen". Ob der Installer dann abbricht, hat der Projektinhaber nicht
entschieden - er warnt deutlich und laeuft weiter; auch das ist hier
festgehalten.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: Kern des Wortlauts (ASCII-Schreibweise und mit Umlaut).
_KERN = re.compile(r"nicht unterst(?:ue|ü)tzt \(instabil, kein 3D\) [-—] x64-Python nehmen")
#: Alter Wortlaut, den es nirgends mehr geben darf.
_ALT = ("laeuft ohne 3D-Visualizer", "LightOS laeuft, aber OHNE 3D-Visualizer",
        "geht auch, aber ohne 3D-Visualizer", "startet\nLightOS, aber ohne 3D-Ansicht",
        "geht nur ohne 3D-Visualizer", "x64-Python empfohlen")


def _text(rel: str) -> str:
    return (ROOT / rel).read_bytes().decode("utf-8")


@pytest.fixture
def installer(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(ROOT))
    import install
    # Nie das echte venv/ des Checkouts fragen und nichts starten.
    monkeypatch.setattr(install, "VENV_DIR", tmp_path / "venv")
    monkeypatch.setattr(install, "finde_x64_python", lambda: None)
    monkeypatch.setattr(install.os, "name", "nt")
    monkeypatch.setattr(install, "detect_native_os_arch", lambda: "arm64")
    return install


class TestInstaller:
    def test_konstante_traegt_den_wortlaut(self, installer):
        assert _KERN.search(installer.ARM64_NICHT_UNTERSTUETZT)

    def test_arm_warnung_sagt_nicht_unterstuetzt_und_nennt_x64_weg(
            self, installer, monkeypatch, capsys):
        monkeypatch.setattr(installer, "detect_arch", lambda: "arm64")
        installer.check_arm_runtime()
        out = capsys.readouterr().out
        warn = "\n".join(z for z in out.splitlines() if "WARN" in z)
        assert _KERN.search(warn)
        assert "6 von 12" in warn            # instabil - mit Zahl, nicht vage
        assert "QtWebEngine" in warn         # kein 3D - mit Grund
        assert "--architecture x64" in warn and "--neu-venv" in warn
        for alt in _ALT:
            assert alt not in out

    def test_installer_bricht_nicht_ab(self, installer, monkeypatch, capsys):
        # Abbrechen hat der Projektinhaber nicht entschieden: deutlich warnen,
        # aber weiterlaufen - und das auch sagen.
        monkeypatch.setattr(installer, "detect_arch", lambda: "arm64")
        assert installer.check_arm_runtime() is None
        out = capsys.readouterr().out
        assert "laeuft trotzdem weiter" in out
        quelle = inspect.getsource(installer.check_arm_runtime)
        assert "sys.exit" not in quelle and "raise" not in quelle

    def test_x64_auf_arm_bekommt_keine_warnung(self, installer, monkeypatch, capsys):
        monkeypatch.setattr(installer, "detect_arch", lambda: "x64")
        installer.check_arm_runtime()
        out = capsys.readouterr().out
        assert "WARN" not in out and "nicht unterstuetzt" not in out

    def test_zusammenfassung_sagt_nicht_unterstuetzt(self, installer, monkeypatch, capsys):
        monkeypatch.setattr(installer, "detect_arch", lambda: "arm64")
        monkeypatch.setattr(installer, "venv_arch", lambda: "arm64")
        installer.show_summary()
        out = capsys.readouterr().out
        warn = "\n".join(z for z in out.splitlines() if "WARN" in z)
        assert _KERN.search(warn) and "--architecture x64" in warn

    def test_kopf_des_installers(self):
        kopf = _text("install.py").split('"""', 2)[1]
        assert _KERN.search(" ".join(kopf.split()))
        assert "ohne\n3D-Visualizer" not in kopf


class TestPlattformHinweis:
    def test_konstante(self):
        from src.core.plattform_hinweis import ARM64_NICHT_UNTERSTUETZT
        assert _KERN.search(ARM64_NICHT_UNTERSTUETZT)

    def test_visualizer_meldung_auf_arm64(self):
        from src.core.plattform_hinweis import visualizer_startfehler_text
        text = visualizer_startfehler_text(ImportError("x"), system="nt", py_arch="arm64")
        assert _KERN.search(text)
        assert "--architecture x64" in text

    def test_modulkopf(self):
        kopf = _text("src/core/plattform_hinweis.py").split('"""', 2)[1]
        assert "nicht unterstuetzt (instabil, kein 3D)" in kopf
        assert 'nur als Hinweis "ohne 3D"' not in kopf


def _warnzeile(name: str) -> str:
    zeilen = [z for z in _text(name).splitlines()
              if "ARM64-Python" in z and ("echo" in z or "Write-Host" in z)]
    assert len(zeilen) == 1, zeilen
    return zeilen[0]


class TestStartskripte:
    def test_start_ps1(self):
        zeile = _warnzeile("start.ps1")
        assert "WARNUNG" in zeile and _KERN.search(zeile)
        assert "--architecture x64" in zeile

    def test_start_bat(self):
        # cmd: Klammern in echo-Zeilen sind heikel - hier ohne Klammern, aber
        # mit denselben Bestandteilen.
        zeile = _warnzeile("start.bat")
        assert "WARNUNG" in zeile
        for teil in ("nicht unterstuetzt", "instabil", "kein 3D", "x64-Python nehmen",
                     "--architecture x64"):
            assert teil in zeile, teil
        assert "(" not in zeile and ")" not in zeile

    @pytest.mark.parametrize("name", ("start.bat", "start.ps1"))
    def test_startet_trotzdem(self, name):
        text = _text(name)
        nach_hinweis = text[text.index("x64-Python nehmen"):text.rindex("main.py")]
        assert not re.search(r"(?im)^\s*(exit|goto :eof|return)\b", nach_hinweis)

    @pytest.mark.parametrize("name", ("start.bat", "start.ps1"))
    def test_kein_alter_wortlaut(self, name):
        text = _text(name)
        for alt in _ALT:
            assert alt not in text


class TestDoku:
    @pytest.mark.parametrize("rel", ("INSTALL.md", "README.md", "CONTRIBUTING.md",
                                     "docs/DMX_PROTOCOL.md"))
    def test_wortlaut(self, rel):
        text = " ".join(_text(rel).replace("**", "").split())
        assert _KERN.search(text), rel
        for alt in _ALT:
            assert " ".join(alt.split()) not in text, (rel, alt)

    def test_install_md_nennt_absturzrate_und_kein_abbruch(self):
        text = " ".join(_text("INSTALL.md").split())
        assert "6 von 12 Starts" in text
        assert "brechen aber nicht ab" in text

    def test_install_md_troubleshooting_kennt_den_absturz(self):
        zeilen = [z for z in _text("INSTALL.md").splitlines()
                  if z.startswith("|") and "Access Violation" in z]
        assert zeilen and "x64-Python nehmen" in zeilen[0]
