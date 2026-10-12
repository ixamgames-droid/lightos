"""OUT-76, Stufe 1: das Windows-Setup bringt pyusb und libusb mit.

**Entscheidung des Projektinhabers (12.10.2026):** pyusb und libusb-package
gehoeren ins Windows-Setup — es sind Bibliotheken, keine Treiber. Vorher lief
uDMX im installierten LightOS nie: ``requirements.txt`` fuehrte pyusb nur als
Kommentar, und die Setup-Pipeline installiert genau diese Datei.

Dieser Test haelt fest, was dafuer zusammenpassen muss: die Abhaengigkeiten,
das Setup-Manifest, die Lizenzhinweise (LGPL: dynamisch gebunden, austauschbar,
Quelle genannt) und der Selbsttest der gepackten exe, an dem der Rauchtest der
Setup-Pipeline haengt. Und dass weiterhin KEIN Treiber im Repo liegt.

Gebaut wird hier nichts; pyusb muss fuer diesen Test nicht installiert sein.
"""
from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import types

import pytest

from src.core import selbsttest
from src.core.dmx import udmx

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "packaging", "windows"))
import bundle_inhalt                                             # noqa: E402


def _lies(*teile) -> str:
    with io.open(os.path.join(_REPO, *teile), encoding="utf-8") as f:
        return f.read()


def _anforderung(name: str) -> str:
    zeilen = [z.strip() for z in _lies("requirements.txt").splitlines()
              if z.strip().lower().startswith(name)]
    assert len(zeilen) == 1, f"{name}: {zeilen}"
    return zeilen[0]


# ── Abhaengigkeiten ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("paket", ["pyusb", "libusb-package"])
def test_requirements_nennen_das_paket_fuer_windows_x64(paket):
    zeile = _anforderung(paket)
    assert not zeile.startswith("#")
    assert 'sys_platform == "win32"' in zeile
    # libusb-package hat kein fertiges Paket fuer Windows-ARM64 (und kein
    # Quellpaket): ohne die Ausnahme braeche dort die ganze Installation.
    assert 'platform_machine != "ARM64"' in zeile


def test_die_setup_pipeline_installiert_genau_diese_datei():
    """Sonst kaeme die Zeile oben nie im Setup an."""
    ablauf = _lies(".github", "workflows", "windows-setup.yml")
    assert "pip install -r requirements.txt" in ablauf
    assert "architecture: x64" in ablauf
    assert "--selbsttest" in ablauf, "der Rauchtest prueft das gepackte Ergebnis"


# ── Setup-Manifest ───────────────────────────────────────────────────────────

def test_manifest_nennt_die_module():
    for modul in ("usb.core", "usb.util", "usb.backend.libusb1", "libusb_package"):
        assert modul in bundle_inhalt.HIDDEN_IMPORTS, modul
    for nie in ("usb", "libusb_package"):
        assert nie not in bundle_inhalt.EXCLUDES


def test_manifest_nimmt_die_dll_als_eigene_datei_mit():
    assert "libusb_package" in bundle_inhalt.DYNAMISCHE_BIBLIOTHEKEN
    spec = _lies("packaging", "windows", "LightOS.spec")
    assert "collect_dynamic_libs" in spec
    assert "bundle_inhalt.DYNAMISCHE_BIBLIOTHEKEN" in spec
    assert "binaries=binaries," in spec
    # ONEDIR: die DLL bleibt eine Datei im Programmordner (LGPL: austauschbar).
    assert "exclude_binaries=True" in spec


# ── die mitgelieferte DLL finden ─────────────────────────────────────────────

def test_dll_wird_im_paketordner_und_im_programmordner_gefunden(tmp_path):
    assert udmx.bundle_dll_pfad("") == ""                      # nicht gepackt
    assert udmx.bundle_dll_pfad(str(tmp_path)) == ""           # gepackt, aber fehlt
    (tmp_path / "libusb-1.0.dll").write_bytes(b"x")
    assert udmx.bundle_dll_pfad(str(tmp_path)) == str(tmp_path / "libusb-1.0.dll")
    paket = tmp_path / "libusb_package"
    paket.mkdir()
    (paket / "libusb-1.0.dll").write_bytes(b"x")
    assert udmx.bundle_dll_pfad(str(tmp_path)) == str(paket / "libusb-1.0.dll"), \
        "der Paketordner hat Vorrang"


def test_backend_aus_dem_bundle_nimmt_genau_diese_datei(tmp_path, monkeypatch):
    (tmp_path / "libusb-1.0.dll").write_bytes(b"x")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    gefragt = []

    def get_backend(find_library=None):
        gefragt.append(find_library("usb-1.0"))
        return "backend"

    libusb1 = types.SimpleNamespace(get_backend=get_backend)
    backend_paket = types.SimpleNamespace(libusb1=libusb1)
    monkeypatch.setitem(sys.modules, "usb", types.SimpleNamespace(backend=backend_paket))
    monkeypatch.setitem(sys.modules, "usb.backend", backend_paket)
    monkeypatch.setitem(sys.modules, "usb.backend.libusb1", libusb1)
    assert udmx._backend_aus_bundle() == "backend"
    assert gefragt == [str(tmp_path / "libusb-1.0.dll")]


def test_ohne_bundle_kein_backend(monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert udmx._backend_aus_bundle() is None


# ── Selbsttest der gepackten exe ─────────────────────────────────────────────

def _fehlt():
    raise udmx.UdmxFehler(udmx.G_PYUSB_FEHLT)


def test_selbsttest_gepackt_ohne_pyusb_ist_ein_fehler():
    fehler = selbsttest.pruefe_udmx_bibliothek(
        gefroren=True, plattform="win32", maschine="AMD64", laden=_fehlt)
    assert len(fehler) == 1 and "pyusb fehlt im Setup" in fehler[0]


def test_selbsttest_gepackt_ohne_dll_ist_ein_fehler():
    fehler = selbsttest.pruefe_udmx_bibliothek(
        gefroren=True, plattform="win32", maschine="AMD64",
        laden=lambda: ("core", "util", None))
    assert len(fehler) == 1 and "libusb-1.0.dll fehlt im Setup" in fehler[0]


def test_selbsttest_gepackt_mit_beidem_ist_ruhig():
    assert selbsttest.pruefe_udmx_bibliothek(
        gefroren=True, plattform="win32", maschine="AMD64",
        laden=lambda: ("core", "util", object())) == []


@pytest.mark.parametrize("gefroren,plattform,maschine", [
    (False, "win32", "AMD64"),      # Quellbetrieb: optional wie bisher
    (True, "linux", "x86_64"),      # kein Windows-Setup
    (True, "win32", "ARM64"),       # dort gibt es libusb-package nicht
])
def test_selbsttest_verlangt_es_nur_im_windows_setup_x64(gefroren, plattform, maschine):
    assert selbsttest.pruefe_udmx_bibliothek(
        gefroren=gefroren, plattform=plattform, maschine=maschine, laden=_fehlt) == []


def test_der_bericht_fuehrt_die_pruefung_mit():
    import inspect
    assert "pruefe_udmx_bibliothek()" in inspect.getsource(selbsttest.bericht)
    code, zeilen = selbsttest.bericht()                         # Quellbetrieb
    assert not any("uDMX:" in z and z.startswith("FEHLER") for z in zeilen)


# ── Lizenzhinweise ───────────────────────────────────────────────────────────

def _abschnitt(titel_beginn: str) -> str:
    text = _lies("THIRD_PARTY_NOTICES.md")
    treffer = [a for a in re.split(r"(?m)^## ", text) if a.startswith(titel_beginn)]
    assert len(treffer) == 1, titel_beginn
    return " ".join(treffer[0].split())


def test_pyusb_steht_mit_lizenz_und_urheber_in_den_hinweisen():
    a = _abschnitt("pyusb")
    assert "licenses/BSD-3-Clause-pyusb.txt" in a and "Copyright ©" in a
    assert "https://github.com/pyusb/pyusb" in a
    lizenz = _lies("licenses", "BSD-3-Clause-pyusb.txt")
    assert "Wander Lairson Costa" in lizenz
    assert "Redistributions in binary form must reproduce" in lizenz


def test_libusb_steht_mit_den_lgpl_pflichten_in_den_hinweisen():
    a = _abschnitt("libusb —")
    assert "licenses/LGPL-2.1-libusb.txt" in a
    assert "https://github.com/libusb/libusb" in a, "Hinweis auf die Quelle"
    assert "Dynamisch gebunden" in a and "libusb-1.0.dll" in a
    assert "Austauschbar" in a and "ersetzen" in a
    assert "kein Treiber" in a
    lizenz = _lies("licenses", "LGPL-2.1-libusb.txt")
    assert "GNU LESSER GENERAL PUBLIC LICENSE" in lizenz and "Version 2.1" in lizenz
    assert len(lizenz) > 20000, "der ganze Text, nicht nur ein Verweis"


def test_libusb_package_steht_in_den_hinweisen():
    a = _abschnitt("libusb-package")
    assert "licenses/Apache-2.0.txt" in a and "Copyright ©" in a
    assert "https://github.com/pyocd/libusb-package" in a


def test_das_setup_installiert_hinweise_und_lizenztexte():
    iss = _lies("packaging", "windows", "LightOS.iss")
    assert "THIRD_PARTY_NOTICES.md" in iss and "\\licenses\\*" in iss
    assert "licenses" in bundle_inhalt.DATENORDNER


# ── weiterhin: kein Treiber ──────────────────────────────────────────────────

def test_im_repo_liegt_kein_treiber():
    """Stufe 1 liefert Bibliotheken. Treiberpakete (INF/CAT/SYS), Zadig oder
    ein Treiber-Installer kommen erst nach einer eigenen Entscheidung dazu —
    dieser Test wird dann bewusst geaendert, nicht still gruen gehalten."""
    try:
        aus = subprocess.run(["git", "ls-files"], cwd=_REPO, capture_output=True,
                             text=True, check=True).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("kein Git")
    verdaechtig = [d for d in aus
                   if d.lower().endswith((".inf", ".cat", ".sys"))
                   or re.search(r"(zadig|libwdi|wdi-simple|dpinst|cdm.*setup)", d.lower())]
    assert verdaechtig == []


def test_das_setup_fuehrt_kein_fremdes_installationsprogramm_aus():
    iss = _lies("packaging", "windows", "LightOS.iss").lower()
    for wort in ("zadig", "pnputil", "dpinst", ".inf", "devcon", "winusb"):
        assert wort not in iss, wort
