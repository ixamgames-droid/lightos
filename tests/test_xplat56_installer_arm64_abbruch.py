"""XPLAT-56: install.py bricht bei nativem ARM64-Python ab (Entscheidung E-2).

Bis XPLAT-51 warnte der Installer nur ("laeuft trotzdem weiter"), obwohl
LightOS mit einem ARM64-venv in 6 von 12 Starts mit Access Violation abstuerzte.
Entscheidung E-2 vom 25.10.2026 im Auftrag des Projektinhabers: Abbruch mit
Exit-Code != 0 und der Anleitung "x64-Python installieren" (winget-Befehl,
Aufruf mit ``--neu-venv``). ``--arm64-trotzdem`` umgeht das, nur fuer Tests
und Entwicklung. start.bat/start.ps1 warnen weiter nur (XPLAT-51-Waechter).

Massgeblich ist das ZIEL - das Python, mit dem LightOS danach laeuft
(XPLAT-52), nicht das, das install.py ausfuehrt:

=====================  ==========================  ===========================
install.py-Python      venv                        Ergebnis
=====================  ==========================  ===========================
ARM64                  keins / --neu-venv          Abbruch vor dem ersten Schritt
ARM64                  vorhanden, x64              laeuft durch, venv bleibt
                                                   (keine Rueckfrage, kein Neubau)
ARM64                  vorhanden, ARM64            Abbruch
ARM64                  vorhanden, nicht startbar   Abbruch (Arch nicht belegbar)
ARM64                  --no-venv                   Abbruch
x64                    keins / x64 / --no-venv     laeuft durch
x64                    vorhanden, ARM64, "j"       neu gebaut, laeuft durch
x64                    vorhanden, ARM64, "N"       Abbruch nach der Rueckfrage
=====================  ==========================  ===========================

Nichts wird echt installiert: ``main()`` laeuft mit gepatchten Schritten,
VENV_DIR/MANIFEST_PATH liegen in tmp_path, ``subprocess.run`` wird nur
protokolliert. Die venv-Architektur folgt einem Zustand, den ein
protokollierter ``-m venv``-Aufruf auf die Architektur des ausfuehrenden
Python setzt - so sieht die Nachpruefung das venv, das wirklich entstuende.
"""
from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: os.name des Rechners, auf dem die Tests laufen - vor jedem Monkeypatch.
ECHTES_OS_NAME = __import__("os").name

_KERN = re.compile(r"nicht unterst(?:ue|ü)tzt \(instabil, kein 3D\) [-—] x64-Python nehmen")


class _Lauf:
    """Gepatchter Installer-Lauf: Architekturen, venv-Zustand, Protokoll."""

    def __init__(self, install, monkeypatch, tmp_path):
        self.install = install
        self.mp = monkeypatch
        self.aufrufe: list[list[str]] = []
        self.fragen: list[str] = []
        self.antwort = False
        self.py_arch = "x64"
        self.venv: str | None = None          # None = kein venv/
        self.schritte: list[str] = []
        monkeypatch.setattr(install, "VENV_DIR", tmp_path / "venv")
        monkeypatch.setattr(install, "MANIFEST_PATH", tmp_path / "install_manifest.json")
        monkeypatch.setattr(install, "finde_x64_python", lambda: None)
        monkeypatch.setattr(install, "detect_arch", lambda: self.py_arch)
        monkeypatch.setattr(install, "venv_arch", self._venv_arch)
        monkeypatch.setattr(install.subprocess, "run", self._run)
        monkeypatch.setattr(install, "_frage_ja", self._frage)
        for name in ("check_python", "install_requirements", "create_shortcut",
                     "write_manifest", "show_summary"):
            monkeypatch.setattr(install, name,
                                lambda *a, _n=name, **k: self.schritte.append(_n))
        monkeypatch.setattr(install, "create_directories",
                            lambda: self.schritte.append("create_directories") or [])

    # -- Plattform ---------------------------------------------------------
    def windows_arm(self):
        self.mp.setattr(self.install.os, "name", "nt")
        self.mp.setattr(self.install, "detect_native_os_arch", lambda: "arm64")

    def windows_x64(self):
        self.mp.setattr(self.install.os, "name", "nt")
        self.mp.setattr(self.install, "detect_native_os_arch", lambda: "x64")

    # -- Zustand -----------------------------------------------------------
    def vorhandenes_venv(self, arch: str):
        """Legt venv/ an; ``arch='unknown'`` = vorhanden, aber nicht startbar."""
        self.install.VENV_DIR.mkdir()
        (self.install.VENV_DIR / "alt.txt").write_text(arch, encoding="utf-8")
        self.venv = arch

    def _venv_arch(self) -> str:
        if self.venv is None or not self.install.VENV_DIR.exists():
            return "unknown"
        return self.venv

    def _run(self, cmd, *a, **k):
        cmd = [str(c) for c in cmd]
        self.aufrufe.append(cmd)
        if cmd[1:3] == ["-m", "venv"]:
            Path(cmd[3]).mkdir(parents=True, exist_ok=True)
            self.venv = self.py_arch

    def _frage(self, frage: str) -> bool:
        self.fragen.append(frage)
        return self.antwort

    # -- Ergebnis ----------------------------------------------------------
    @property
    def venv_gebaut(self) -> bool:
        return any(c[1:3] == ["-m", "venv"] for c in self.aufrufe)

    @property
    def alt_venv_noch_da(self) -> bool:
        return (self.install.VENV_DIR / "alt.txt").exists()

    def main(self, *argv: str):
        """Laeuft main(); liefert den Exit-Code (None = durchgelaufen)."""
        self.mp.setattr(sys, "argv", ["install.py", "--no-shortcut", *argv])
        try:
            self.install.main()
        except SystemExit as e:
            return e.code
        return None


@pytest.fixture
def lauf(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(ROOT))
    import install
    return _Lauf(install, monkeypatch, tmp_path)


def _abbruch_text(out: str) -> str:
    return "\n".join(z for z in out.splitlines() if "ERROR" in z)


# ── ARM64-Python fuehrt install.py aus ─────────────────────────────────────
class TestArm64Installer:
    @pytest.fixture(autouse=True)
    def _arm(self, lauf):
        lauf.windows_arm()
        lauf.py_arch = "arm64"

    def test_ohne_venv_bricht_vor_dem_ersten_schritt_ab(self, lauf, capsys):
        code = lauf.main()
        assert code == lauf.install.ARM64_EXIT_CODE and code != 0
        assert not lauf.venv_gebaut and not lauf.install.VENV_DIR.exists()
        assert lauf.schritte == ["check_python"]       # nichts installiert
        fehler = _abbruch_text(capsys.readouterr().out)
        assert _KERN.search(fehler)
        assert "winget install Python.Python.3.12 --architecture x64" in fehler
        assert "install.py --neu-venv" in fehler
        assert "Exit-Code 3" in fehler

    def test_neu_venv_bricht_ab_und_loescht_das_x64_venv_nicht(self, lauf):
        lauf.vorhandenes_venv("x64")
        assert lauf.main("--neu-venv") == 3
        assert lauf.alt_venv_noch_da and not lauf.venv_gebaut

    def test_no_venv_bricht_ab(self, lauf, capsys):
        assert lauf.main("--no-venv") == 3
        assert "install_requirements" not in lauf.schritte
        assert "--no-venv" in _abbruch_text(capsys.readouterr().out)

    def test_vorhandenes_x64_venv_bleibt_und_laeuft_durch(self, lauf, capsys):
        # Mischfall XPLAT-52: pip und LightOS nutzen das x64-Python des venv -
        # das ARM64-Python richtet nur ein. Kein Abbruch, keine Rueckfrage
        # (ein "j" machte daraus ein ARM64-venv), kein Neubau.
        lauf.vorhandenes_venv("x64")
        assert lauf.main() is None
        assert lauf.fragen == [] and not lauf.venv_gebaut and lauf.alt_venv_noch_da
        assert "install_requirements" in lauf.schritte and "show_summary" in lauf.schritte
        out = capsys.readouterr().out
        assert "ERROR" not in out
        assert "vorhandene venv ist x64-Python und bleibt" in out

    def test_vorhandenes_arm64_venv_bricht_ab(self, lauf):
        lauf.vorhandenes_venv("arm64")
        assert lauf.main() == 3
        assert lauf.alt_venv_noch_da and "install_requirements" not in lauf.schritte

    def test_nicht_startbares_venv_bricht_ab(self, lauf):
        # Architektur nicht belegbar - es zaehlt das ausfuehrende ARM64-Python.
        lauf.vorhandenes_venv("unknown")
        assert lauf.main() == 3
        assert lauf.alt_venv_noch_da

    def test_warnblock_sagt_bricht_ab(self, lauf, capsys):
        lauf.main()
        warn = "\n".join(z for z in capsys.readouterr().out.splitlines() if "WARN" in z)
        assert "bricht deshalb ab" in warn
        assert "laeuft trotzdem weiter" not in warn


# ── Ausnahme-Schalter ──────────────────────────────────────────────────────
class TestSchalter:
    @pytest.fixture(autouse=True)
    def _arm(self, lauf):
        lauf.windows_arm()
        lauf.py_arch = "arm64"

    @pytest.mark.parametrize("argv", [(), ("--no-venv",), ("--neu-venv",)])
    def test_trotzdem_laeuft_durch_und_warnt(self, lauf, capsys, argv):
        assert lauf.main("--arm64-trotzdem", *argv) is None
        assert "show_summary" in lauf.schritte
        out = capsys.readouterr().out
        assert "ERROR" not in out
        assert any("WARN" in z and "--arm64-trotzdem" in z and "Tests/Entwicklung" in z
                   for z in out.splitlines())
        if "--no-venv" not in argv:
            assert lauf.venv_gebaut and lauf.venv == "arm64"

    def test_trotzdem_fragt_beim_x64_venv_wie_frueher(self, lauf):
        lauf.vorhandenes_venv("x64")
        lauf.antwort = True
        assert lauf.main("--arm64-trotzdem") is None
        assert len(lauf.fragen) == 1 and lauf.venv_gebaut

    def test_hilfe_beschreibt_den_schalter_als_test_werkzeug(self, lauf, capsys):
        assert lauf.main("--help") == 0
        hilfe = " ".join(capsys.readouterr().out.split())
        assert "--arm64-trotzdem" in hilfe
        assert "NUR fuer Tests/Entwickler" in hilfe

    def test_abbruchmeldung_bewirbt_den_schalter_nicht(self, lauf, capsys):
        lauf.main()
        assert "--arm64-trotzdem" not in capsys.readouterr().out


# ── x64-Python fuehrt install.py aus ───────────────────────────────────────
class TestX64Installer:
    @pytest.fixture(autouse=True)
    def _arm(self, lauf):
        lauf.windows_arm()
        lauf.py_arch = "x64"

    @pytest.mark.parametrize("argv", [(), ("--no-venv",), ("--neu-venv",)])
    def test_kein_abbruch(self, lauf, capsys, argv):
        assert lauf.main(*argv) is None
        assert "ERROR" not in capsys.readouterr().out

    def test_vorhandenes_x64_venv_kein_abbruch(self, lauf):
        lauf.vorhandenes_venv("x64")
        assert lauf.main() is None and lauf.fragen == []

    def test_arm64_venv_mit_ja_wird_neu_gebaut(self, lauf):
        lauf.vorhandenes_venv("arm64")
        lauf.antwort = True
        assert lauf.main() is None
        assert lauf.venv_gebaut and lauf.venv == "x64" and not lauf.alt_venv_noch_da

    def test_arm64_venv_mit_nein_bricht_nach_der_rueckfrage_ab(self, lauf, capsys):
        # Ohne Neubau liefe LightOS mit dem ARM64-venv - also Abbruch, bevor
        # Pakete hineinkommen; der Weg nennt dieses (x64-)Python.
        lauf.vorhandenes_venv("arm64")
        lauf.antwort = False
        assert lauf.main() == 3
        assert len(lauf.fragen) == 1 and lauf.alt_venv_noch_da
        assert "install_requirements" not in lauf.schritte
        fehler = _abbruch_text(capsys.readouterr().out)
        assert f'"{sys.executable}" install.py --neu-venv' in fehler
        assert "winget" not in fehler          # x64-Python ist ja schon da

    def test_arm64_venv_mit_neu_venv_kein_abbruch(self, lauf):
        lauf.vorhandenes_venv("arm64")
        assert lauf.main("--neu-venv") is None
        assert lauf.venv == "x64" and lauf.fragen == []


# ── Kein Windows-ARM ───────────────────────────────────────────────────────
class TestAndereSysteme:
    def test_windows_x64_kein_abbruch(self, lauf):
        lauf.windows_x64()
        lauf.py_arch = "x64"
        assert lauf.main() is None

    @pytest.mark.skipif(ECHTES_OS_NAME == "nt",
                        reason="os.name bleibt echt - unter Windows gibt es kein Linux")
    @pytest.mark.parametrize("arch", ["x64", "arm64"])
    def test_linux_kein_abbruch(self, lauf, capsys, arch):
        # os.name wird nicht umgestellt (XPLAT-52-Lehre: pathlib); Linux auf
        # aarch64 ist nicht der XPLAT-51-Fall.
        lauf.mp.setattr(lauf.install, "detect_native_os_arch", lambda: arch)
        lauf.py_arch = arch
        assert lauf.main() is None
        assert "ERROR" not in capsys.readouterr().out

    def test_pruefungen_verlangen_windows_arm(self, lauf):
        quelle = inspect.getsource(lauf.install.pruefe_arm64_vorab)
        assert "auf_windows_arm()" in quelle
        assert "auf_windows_arm()" in inspect.getsource(lauf.install.pruefe_arm64_ziel)


# ── Absicherung in create_venv ─────────────────────────────────────────────
def test_create_venv_baut_mit_arm64_python_nie_ein_venv(lauf):
    # Auch wer create_venv direkt aufruft (ohne die Vorabpruefung), bekommt
    # kein ARM64-venv - und ein vorhandenes x64-venv wird nicht geloescht.
    lauf.windows_arm()
    lauf.py_arch = "arm64"
    with pytest.raises(SystemExit) as e:
        lauf.install.create_venv()
    assert e.value.code == 3 and not lauf.venv_gebaut
    lauf.vorhandenes_venv("x64")
    with pytest.raises(SystemExit):
        lauf.install.create_venv(neu=True)
    assert lauf.alt_venv_noch_da and not lauf.venv_gebaut


# ── Wortlaut ───────────────────────────────────────────────────────────────
def _text(rel: str) -> str:
    return " ".join((ROOT / rel).read_bytes().decode("utf-8").replace("**", "").split())


class TestWortlaut:
    def test_installer_kopf(self):
        kopf = " ".join((ROOT / "install.py").read_text(encoding="utf-8")
                        .split('"""', 2)[1].split())
        assert "bricht dann ab" in kopf and "--arm64-trotzdem" in kopf
        assert "bricht aber nicht ab" not in kopf

    def test_install_md(self):
        text = _text("INSTALL.md")
        assert "Der Installer bricht in diesem Fall ab (Exit-Code 3" in text
        assert "brechen aber nicht ab" not in text
        assert "--arm64-trotzdem ist nur fuer Tests und Entwicklung" in text.replace("`", "")
        assert "die Startskripte warnen nur" in text

    @pytest.mark.parametrize("rel,satz", [
        ("README.md", "install.py bricht mit nativem ARM64-Python deshalb ab"),
        ("CONTRIBUTING.md", "install.py bricht damit ab (XPLAT-56)"),
    ])
    def test_readme_contributing(self, rel, satz):
        text = _text(rel).replace("`", "")
        assert satz in text
        assert "bricht nicht ab" not in text

    def test_backlog_eintrag_verweist_auf_xplat51(self):
        # Fragment oder (nach dem Einsammeln) Zeile in BACKLOG.md - beides gilt.
        from backlog_eintrag import eintrag
        text = eintrag(ROOT, "XPLAT-56")
        assert "XPLAT-51" in text and "E-2" in text
