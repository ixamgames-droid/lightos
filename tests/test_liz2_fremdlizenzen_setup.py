"""LIZ-2: Fremdlizenzen im Windows-Setup — vollstaendig und im Gleichschritt.

**Befund (12.10.2026, echtes Bundle aus ``LightOS.spec``):** Das Setup lieferte
Python, Qt/PySide6 (mit QtWebEngine/Chromium und FFmpeg) und 35 Python-Pakete
mit, ``THIRD_PARTY_NOTICES.md`` nannte davon drei. Die LGPL- und GPL-Texte
fehlten. Und im Bundle lagen sieben Qt-Module, die es nur unter der GPLv3 gibt
(Qt Charts, Qt Data Visualization, Qt Graphs, Qt Quick 3D, Qt Quick 3D Physics,
Qt Quick Timeline, Qt Virtual Keyboard) — PyInstaller sammelt den ganzen
QML-Ordner von Qt ein, obwohl LightOS kein QML benutzt.

Was dieser Test zusammenhaelt:

* ``qt_umfang.auswahl`` — von Qt bleibt nur, was LightOS oder ein
  mitgeliefertes Plugin laedt; die Nur-GPL-Module fallen heraus.
* ``fremdkomponenten`` — die Tabelle der erlaubten Komponenten und die Pruefung
  eines Bundles dagegen (Paket ohne Eintrag, geaenderte Lizenzangabe, fehlender
  Text, Datei unbekannter Herkunft, Nur-GPL- oder unbekanntes Qt-Modul).
* Tabelle <-> ``THIRD_PARTY_NOTICES.md`` <-> ``requirements.txt`` <-> ``licenses/``.
* Spec, Setup-Skript und Selbsttest der gepackten exe haengen daran.
* Die Controller-Bibliothek (CC0) enthaelt kein eingelesenes QLC+-Profil.

Gebaut wird hier nichts. Die Liste der Komponenten stammt aus einem echten Bau;
ob sie zum naechsten Bundle passt, prueft ``LightOS.spec`` beim Bauen selbst —
dort bricht der Bau ab, hier haelt der Test die Regeln fest, nach denen er das
tut.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

import pytest

from src.core import selbsttest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "packaging", "windows"))
import bundle_inhalt                                             # noqa: E402
import fremdkomponenten as fk                                    # noqa: E402
import qt_umfang                                                 # noqa: E402


def _lies(*teile) -> str:
    with io.open(os.path.join(_REPO, *teile), encoding="utf-8") as f:
        return f.read()


def _glatt(text: str) -> str:
    """Zeilenumbrueche und Einrueckung zaehlen nicht — der Wortlaut zaehlt."""
    return re.sub(r"\s+", " ", text)


def _abschnitt(titel_anfang: str) -> str:
    text = _lies("THIRD_PARTY_NOTICES.md")
    teile = re.split(r"(?m)^## ", text)
    treffer = [t for t in teile if t.startswith(titel_anfang)]
    assert len(treffer) == 1, f"Abschnitt „{titel_anfang}“: {len(treffer)} Treffer"
    return treffer[0]


# ── Qt-Umfang: was der Filter aus einem Bundle macht ─────────────────────────
#
# Ein kleines Bundle in der Form, in der PyInstaller es liefert: (ziel, quelle,
# typ). ``_IMPORTE`` ersetzt das Lesen der DLL-Importe — Schluessel ist die
# Quelle.

def _b(ziel: str) -> tuple[str, str, str]:
    return (ziel.replace("/", "\\"), "Q:\\" + ziel.replace("/", "\\"), "BINARY")


def _d(ziel: str) -> tuple[str, str, str]:
    return (ziel.replace("/", "\\"), "Q:\\" + ziel.replace("/", "\\"), "DATA")


_BINAER = [
    "PySide6/QtCore.pyd", "PySide6/QtWidgets.pyd", "PySide6/QtWebEngineWidgets.pyd",
    "PySide6/QtMultimedia.pyd", "PySide6/QtWebChannel.pyd",
    "PySide6/Qt6Core.dll", "PySide6/Qt6Gui.dll", "PySide6/Qt6Widgets.dll",
    "PySide6/Qt6Network.dll", "PySide6/Qt6Qml.dll", "PySide6/Qt6Quick.dll",
    "PySide6/Qt6Multimedia.dll", "PySide6/Qt6WebChannel.dll",
    "PySide6/Qt6WebEngineCore.dll", "PySide6/Qt6WebEngineWidgets.dll",
    "PySide6/Qt6Svg.dll",
    # nur ueber den QML-Ordner bzw. ein entfallendes Plugin erreichbar:
    "PySide6/Qt6Charts.dll", "PySide6/Qt6Quick3D.dll", "PySide6/Qt6Quick3DUtils.dll",
    "PySide6/Qt6QuickTimeline.dll", "PySide6/Qt6VirtualKeyboard.dll",
    "PySide6/Qt6QuickControls2.dll",
    "PySide6/qml/QtCharts/qtchartsqml2plugin.dll",
    "PySide6/qml/QtQuick3D/qquick3dplugin.dll",
    "PySide6/qml/QtQuick/Timeline/qtquicktimelineplugin.dll",
    "PySide6/qml/QtQuick/Controls/qtquickcontrols2plugin.dll",
    "PySide6/plugins/qmltooling/qmldbg_quick3dprofiler.dll",
    "PySide6/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll",
    "PySide6/plugins/platforms/qwindows.dll",
    "PySide6/plugins/iconengines/qsvgicon.dll",
    "PySide6/plugins/tls/qopensslbackend.dll",
    "PySide6/plugins/tls/qschannelbackend.dll",
    "PySide6/QtWebEngineProcess.exe",
    "PySide6/opengl32sw.dll",
    "libcrypto-3-x64.dll", "libssl-3-x64.dll",       # OpenSSL vom Bau-Rechner
    "libcrypto-3.dll", "libssl-3.dll", "_ssl.pyd",   # OpenSSL von Python
    "python312.dll", "VCRUNTIME140.dll",
    "ucrtbase.dll", "api-ms-win-crt-runtime-l1-1-0.dll",   # gehoert zu Windows
]
_IMPORTE = {
    "PySide6/QtCore.pyd": {"qt6core.dll", "python3.dll"},
    "PySide6/QtWidgets.pyd": {"qt6widgets.dll", "qt6gui.dll", "qt6core.dll"},
    "PySide6/QtWebEngineWidgets.pyd": {"qt6webenginewidgets.dll"},
    "PySide6/QtMultimedia.pyd": {"qt6multimedia.dll"},
    "PySide6/QtWebChannel.pyd": {"qt6webchannel.dll"},
    "PySide6/Qt6Gui.dll": {"qt6core.dll"},
    "PySide6/Qt6Widgets.dll": {"qt6gui.dll", "qt6core.dll"},
    "PySide6/Qt6Qml.dll": {"qt6network.dll", "qt6core.dll"},
    "PySide6/Qt6Quick.dll": {"qt6qml.dll", "qt6gui.dll"},
    "PySide6/Qt6WebEngineCore.dll": {"qt6quick.dll", "qt6webchannel.dll", "qt6network.dll"},
    "PySide6/Qt6WebEngineWidgets.dll": {"qt6webenginecore.dll", "qt6widgets.dll"},
    "PySide6/Qt6Charts.dll": {"qt6widgets.dll"},
    "PySide6/Qt6Quick3D.dll": {"qt6quick3dutils.dll", "qt6quick.dll"},
    "PySide6/Qt6QuickTimeline.dll": {"qt6quick.dll"},
    "PySide6/Qt6VirtualKeyboard.dll": {"qt6quick.dll"},
    "PySide6/Qt6QuickControls2.dll": {"qt6quick.dll"},
    "PySide6/qml/QtCharts/qtchartsqml2plugin.dll": {"qt6charts.dll"},
    "PySide6/qml/QtQuick3D/qquick3dplugin.dll": {"qt6quick3d.dll"},
    "PySide6/qml/QtQuick/Timeline/qtquicktimelineplugin.dll": {"qt6quicktimeline.dll"},
    "PySide6/qml/QtQuick/Controls/qtquickcontrols2plugin.dll": {"qt6quickcontrols2.dll"},
    "PySide6/plugins/qmltooling/qmldbg_quick3dprofiler.dll": {"qt6quick3d.dll"},
    "PySide6/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll":
        {"qt6virtualkeyboard.dll"},
    "PySide6/plugins/platforms/qwindows.dll": {"qt6gui.dll"},
    "PySide6/plugins/iconengines/qsvgicon.dll": {"qt6svg.dll"},
    "PySide6/plugins/tls/qopensslbackend.dll": {"qt6network.dll", "libssl-3-x64.dll",
                                                "libcrypto-3-x64.dll"},
    "PySide6/plugins/tls/qschannelbackend.dll": {"qt6network.dll"},
    "PySide6/QtWebEngineProcess.exe": {"qt6webenginecore.dll"},
    "libssl-3-x64.dll": {"libcrypto-3-x64.dll"},
    "libssl-3.dll": {"libcrypto-3.dll"},
    "_ssl.pyd": {"libssl-3.dll", "libcrypto-3.dll"},
}
_DATEN = [
    "PySide6/qml/QtCharts/qmldir", "PySide6/qml/QtQuick3D/Helpers/AxisHelper.qml",
    "PySide6/translations/qtbase_de.qm", "PySide6/translations/qtlocation_de.qm",
    "PySide6/resources/qtwebengine_resources.pak",
    "licenses/LGPL-3.0.txt",
]


def _importe(quelle: str) -> set[str]:
    return _IMPORTE.get(quelle[3:].replace("\\", "/"), set())


def _auswahl(binaer=None, daten=None, importe=_importe):
    b, d, bericht = qt_umfang.auswahl(
        [_b(z) for z in (_BINAER if binaer is None else binaer)],
        [_d(z) for z in (_DATEN if daten is None else daten)], importe=importe)
    ziele = {e[0].replace("\\", "/") for e in b + d}
    return ziele, bericht


def test_filter_laesst_nur_die_gebrauchten_qt_bibliotheken():
    ziele, bericht = _auswahl()
    assert bericht["fehler"] == []
    assert bericht["qt_bleibt"] == [
        "Qt6Core.dll", "Qt6Gui.dll", "Qt6Multimedia.dll", "Qt6Network.dll", "Qt6Qml.dll",
        "Qt6Quick.dll", "Qt6Svg.dll", "Qt6WebChannel.dll", "Qt6WebEngineCore.dll",
        "Qt6WebEngineWidgets.dll", "Qt6Widgets.dll"]


@pytest.mark.parametrize("datei", [
    "PySide6/Qt6Charts.dll", "PySide6/Qt6Quick3D.dll", "PySide6/Qt6Quick3DUtils.dll",
    "PySide6/Qt6QuickTimeline.dll", "PySide6/Qt6VirtualKeyboard.dll",
    "PySide6/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll",
    "PySide6/qml/QtCharts/qtchartsqml2plugin.dll", "PySide6/qml/QtCharts/qmldir",
    "PySide6/qml/QtQuick3D/Helpers/AxisHelper.qml",
    "PySide6/qml/QtQuick/Timeline/qtquicktimelineplugin.dll",
])
def test_nur_gpl_module_fallen_aus_dem_bundle(datei):
    """Der eigentliche Befund: keine Datei dieser Module darf uebrig bleiben —
    die Bibliothek nicht, ihr QML-Plugin nicht, ihre QML-Dateien nicht."""
    ziele, bericht = _auswahl()
    assert datei not in ziele
    assert datei in bericht["entfernt"]


def test_unbenutzter_ballast_faellt_mit():
    """Qt Quick Controls ist LGPL, wird aber nur ueber den QML-Ordner geladen —
    ohne QML braucht es niemand."""
    ziele, _ = _auswahl()
    assert "PySide6/Qt6QuickControls2.dll" not in ziele
    assert not [z for z in ziele if z.startswith("PySide6/qml/")]
    assert not [z for z in ziele if z.startswith("PySide6/plugins/qmltooling/")]
    assert "PySide6/translations/qtlocation_de.qm" not in ziele


def test_was_lightos_braucht_bleibt():
    ziele, _ = _auswahl()
    for datei in ("PySide6/QtWebEngineProcess.exe", "PySide6/plugins/platforms/qwindows.dll",
                  "PySide6/plugins/iconengines/qsvgicon.dll", "PySide6/opengl32sw.dll",
                  "PySide6/translations/qtbase_de.qm",
                  "PySide6/resources/qtwebengine_resources.pak",
                  "PySide6/QtCore.pyd", "python312.dll", "licenses/LGPL-3.0.txt"):
        assert datei in ziele, datei


def test_openssl_vom_bau_rechner_faellt_die_von_python_bleibt():
    """Qts OpenSSL-Plugin zieht die erste OpenSSL im PATH des Bau-Rechners an.
    Ohne das Plugin braucht sie niemand mehr — libssl haelt libcrypto nicht
    fest, wenn es selbst faellt. Pythons eigene OpenSSL bleibt."""
    ziele, _ = _auswahl()
    assert "PySide6/plugins/tls/qopensslbackend.dll" not in ziele
    assert "libssl-3-x64.dll" not in ziele
    assert "libcrypto-3-x64.dll" not in ziele
    assert "PySide6/plugins/tls/qschannelbackend.dll" in ziele
    assert {"libssl-3.dll", "libcrypto-3.dll", "_ssl.pyd"} <= ziele


def test_universal_c_runtime_faellt_die_vc_laufzeit_bleibt():
    """Entscheidung von Sitzung A (12.10.): was Windows 10/11 selbst mitbringt,
    kommt nicht ins Setup — PyInstaller holte es aus dem PATH des Bau-Rechners."""
    ziele, bericht = _auswahl()
    assert "ucrtbase.dll" not in ziele
    assert "api-ms-win-crt-runtime-l1-1-0.dll" not in ziele
    assert "ucrtbase.dll" in bericht["entfernt"]
    assert "VCRUNTIME140.dll" in ziele and "python312.dll" in ziele


def test_openssl_bleibt_wenn_jemand_anderes_sie_braucht():
    """Kein blindes Loeschen nach Namen: importiert sie etwas Verbleibendes,
    bleibt sie (und ``fremdkomponenten`` meldet dann ihre unbekannte Herkunft)."""
    importe = dict(_IMPORTE)
    importe["PySide6/Qt6Network.dll"] = {"libcrypto-3-x64.dll"}
    ziele, _ = _auswahl(importe=lambda q: importe.get(q[3:].replace("\\", "/"), set()))
    assert "libcrypto-3-x64.dll" in ziele
    assert "libssl-3-x64.dll" not in ziele


def test_fehlt_eine_pflicht_bibliothek_ist_das_ein_fehler():
    """Stimmt der Filter einmal nicht (Qt benennt um, ein Import wird nicht
    gelesen), darf kein Bundle ohne Qt6WebEngineCore entstehen."""
    importe = dict(_IMPORTE)
    importe["PySide6/Qt6WebEngineWidgets.dll"] = {"qt6widgets.dll"}
    importe["PySide6/QtWebEngineProcess.exe"] = set()
    _, bericht = _auswahl(importe=lambda q: importe.get(q[3:].replace("\\", "/"), set()))
    assert any("Qt6WebEngineCore.dll" in f for f in bericht["fehler"]), bericht["fehler"]


def test_unlesbare_binaerdatei_wird_gemeldet_nicht_geraten():
    def kaputt(quelle):
        if quelle.endswith("qwindows.dll"):
            raise ValueError("kein PE")
        return _importe(quelle)
    _, bericht = _auswahl(importe=kaputt)
    assert any("qwindows.dll" in f and "nicht lesbar" in f for f in bericht["fehler"])


def test_bundle_ohne_qt_bleibt_wie_es_ist():
    ziele, bericht = _auswahl(binaer=["python312.dll", "_ssl.pyd"], daten=["main.py"])
    assert ziele == {"python312.dll", "_ssl.pyd", "main.py"}
    assert bericht == {"entfernt": [], "qt_bleibt": [], "fehler": []}


# ── Fremd-Komponenten: Bundle gegen Tabelle ──────────────────────────────────

_BASIS = os.path.join("P:" + os.sep, "Python312")
_SITE = os.path.join("V:" + os.sep, "venv", "site-packages")
_EIGEN = os.path.join("R:" + os.sep, "repo")


def _karte(*eintraege):
    """``{Quellpfad: Paketname}`` wie ``besitzer_karte`` — hier von Hand."""
    return {os.path.normcase(os.path.abspath(os.path.join(_SITE, rel))): paket
            for rel, paket in eintraege}


def _info(name, version="1.0", angabe="MIT", lizenzdateien=(("x.dist-info/LICENSE", "L"),)):
    return {fk.normal(name): {"name": name, "version": version, "angabe": angabe,
                              "lizenzdateien": list(lizenzdateien)}}


def _bundle():
    eintraege = [
        ("flask.app", os.path.join(_SITE, "flask", "app.py"), "PYMODULE"),
        ("serial", os.path.join(_SITE, "serial", "__init__.py"), "PYMODULE"),
        ("PySide6\\Qt6Core.dll", os.path.join(_SITE, "PySide6", "Qt6Core.dll"), "BINARY"),
        ("PySide6\\avcodec-63.dll", os.path.join(_SITE, "PySide6", "avcodec-63.dll"), "BINARY"),
        ("json", os.path.join(_BASIS, "Lib", "json", "__init__.py"), "PYMODULE"),
        ("libcrypto-3.dll", os.path.join(_BASIS, "DLLs", "libcrypto-3.dll"), "BINARY"),
        ("VCRUNTIME140.dll", os.path.join(_BASIS, "vcruntime140.dll"), "BINARY"),
        ("src.core.app_state", os.path.join(_EIGEN, "src", "core", "app_state.py"), "PYMODULE"),
        ("licenses\\LGPL-3.0.txt", os.path.join(_EIGEN, "licenses", "LGPL-3.0.txt"), "DATA"),
        ("winrt", "-", "PYMODULE"),                    # Namensraum-Paket ohne Datei
        ("v", None, "OPTION"),
    ]
    karte = _karte(("flask/app.py", "Flask"), ("serial/__init__.py", "pyserial"),
                   ("PySide6/Qt6Core.dll", "PySide6_Essentials"),
                   ("PySide6/avcodec-63.dll", "PySide6_Addons"))
    return eintraege, karte


def _erfasst(eintraege=None, karte=None):
    e, k = _bundle()
    return fk.erfasse(eintraege or e, karte or k, python_basis=_BASIS, eigene=(_EIGEN,))


def _gute_info():
    info = {}
    info.update(_info("Flask", angabe="BSD-3-Clause"))
    info.update(_info("pyserial", angabe="BSD License", lizenzdateien=()))
    info.update(_info("PySide6_Essentials", angabe=fk._QT_ANGABE[0]))
    info.update(_info("PySide6_Addons", angabe=fk._QT_ANGABE[0]))
    return info


_TEXTE = {"LGPL-3.0.txt", "GPL-3.0.txt", "BSD-3-Clause-pyserial.txt"}


def test_jede_datei_bekommt_ihre_herkunft():
    erfasst = _erfasst()
    assert sorted(erfasst["pakete"]) == ["flask", "pyserial", "pyside6-addons",
                                         "pyside6-essentials"]
    assert sorted(erfasst["python"]) == ["VCRUNTIME140.dll", "json", "libcrypto-3.dll"]
    assert erfasst["eingebettet"] == {
        "FFmpeg": ["PySide6/avcodec-63.dll"],
        "OpenSSL (in Python)": ["libcrypto-3.dll"],
        "Microsoft Visual C++ Laufzeit": ["VCRUNTIME140.dll"],
    }
    assert erfasst["ohne"] == [], "eigene Dateien und Namensraum-Pakete zaehlen nicht"


def test_ein_stimmiges_bundle_hat_keinen_befund(tmp_path):
    lizenz = tmp_path / "LICENSE.txt"
    lizenz.write_text("PSF", encoding="utf-8")
    assert fk.befunde(_erfasst(), _gute_info(), _TEXTE, str(lizenz)) == []


def test_paket_ohne_eintrag_bricht_den_bau(tmp_path):
    """Der Kernfall: eine neue (auch mittelbare) Abhaengigkeit kommt ins Bundle,
    ohne dass jemand ihre Lizenz angesehen hat."""
    eintraege, karte = _bundle()
    eintraege.append(("neu.mod", os.path.join(_SITE, "neu", "mod.py"), "PYMODULE"))
    karte.update(_karte(("neu/mod.py", "Ganz-Neu")))
    info = _gute_info()
    info.update(_info("Ganz-Neu", version="2.3", angabe="GPL-3.0-only"))
    lizenz = tmp_path / "LICENSE.txt"
    lizenz.write_text("PSF", encoding="utf-8")
    b = fk.befunde(_erfasst(eintraege, karte), info, _TEXTE, str(lizenz))
    assert len(b) == 1, b
    assert "Ganz-Neu 2.3" in b[0] and "steht aber nicht in fremdkomponenten.PAKETE" in b[0]


def test_geaenderte_lizenzangabe_bricht_den_bau(tmp_path):
    info = _gute_info()
    info["flask"]["angabe"] = "AGPL-3.0-only"
    lizenz = tmp_path / "LICENSE.txt"
    lizenz.write_text("PSF", encoding="utf-8")
    b = fk.befunde(_erfasst(), info, _TEXTE, str(lizenz))
    assert len(b) == 1, b
    assert "Flask" in b[0] and "AGPL-3.0-only" in b[0] and "BSD-3-Clause" in b[0]


def test_fehlender_lizenztext_bricht_den_bau(tmp_path):
    lizenz = tmp_path / "LICENSE.txt"
    lizenz.write_text("PSF", encoding="utf-8")
    # pyserial bringt keinen Text mit; der aus dem Repo kommt nicht ins Bundle.
    b = fk.befunde(_erfasst(), _gute_info(), _TEXTE - {"BSD-3-Clause-pyserial.txt"},
                   str(lizenz))
    assert len(b) == 1 and "BSD-3-Clause-pyserial.txt" in b[0], b
    # Qt ohne LGPL-Text.
    b = fk.befunde(_erfasst(), _gute_info(), _TEXTE - {"LGPL-3.0.txt"}, str(lizenz))
    assert len(b) == 2 and all("LGPL-3.0.txt" in x for x in b), b
    # Ein Paket, das weder selbst einen Text mitbringt noch einen im Repo hat.
    info = _gute_info()
    info["flask"]["lizenzdateien"] = []
    b = fk.befunde(_erfasst(), info, _TEXTE, str(lizenz))
    assert len(b) == 1 and "Flask" in b[0] and "keinen Lizenztext" in b[0], b


def test_python_ohne_lizenzdatei_bricht_den_bau(tmp_path):
    b = fk.befunde(_erfasst(), _gute_info(), _TEXTE, str(tmp_path / "gibt-es-nicht.txt"))
    assert len(b) == 1 and b[0].startswith("Python:"), b


def test_datei_unbekannter_herkunft_bricht_den_bau(tmp_path):
    """Bei mir zog Qts TLS-Plugin die OpenSSL aus dem Git-Ordner des
    Bau-Rechners an — gehoert zu keinem Paket, nicht zu Python, nicht zum Repo."""
    eintraege, karte = _bundle()
    fremd = os.path.join("C:" + os.sep, "Program Files", "Git", "libcrypto-3-x64.dll")
    eintraege.append(("libcrypto-3-x64.dll", fremd, "BINARY"))
    lizenz = tmp_path / "LICENSE.txt"
    lizenz.write_text("PSF", encoding="utf-8")
    b = fk.befunde(_erfasst(eintraege, karte), _gute_info(), _TEXTE, str(lizenz))
    assert len(b) == 1, b
    assert "libcrypto-3-x64.dll" in b[0] and "Herkunft unbekannt" in b[0]


def test_bekannter_name_aus_fremdem_ordner_bricht_den_bau(tmp_path):
    """Nichts Zufaelliges vom Bau-Rechner: eine VC-Laufzeit, die nicht aus
    Python oder einem Paket stammt, ist unbekannter Herkunft — auch wenn sie
    heisst wie die richtige."""
    eintraege, karte = _bundle()
    fremd = os.path.join("C:" + os.sep, "Windows", "System32", "MSVCP140.dll")
    eintraege.append(("MSVCP140.dll", fremd, "BINARY"))
    lizenz = tmp_path / "LICENSE.txt"
    lizenz.write_text("PSF", encoding="utf-8")
    b = fk.befunde(_erfasst(eintraege, karte), _gute_info(), _TEXTE, str(lizenz))
    assert len(b) == 1 and "MSVCP140.dll" in b[0] and "Herkunft unbekannt" in b[0], b
    assert "nichts Zufaelliges vom Bau-Rechner" in b[0]


def test_universal_c_runtime_im_bundle_bricht_den_bau():
    b = fk.windows_eigene(["ucrtbase.dll", "api-ms-win-core-file-l1-1-0.dll",
                           "VCRUNTIME140.dll", "PySide6\\Qt6Core.dll"])
    assert len(b) == 2, b
    assert all("gehoert zu Windows" in x for x in b)
    ziele, _ = _auswahl()
    assert fk.windows_eigene(ziele) == []


@pytest.mark.parametrize("datei, wort", [
    ("PySide6/Qt6Charts.dll", "Qt Charts"),
    ("PySide6/Qt6ChartsQml.dll", "Qt Charts"),
    ("PySide6/Qt6DataVisualization.dll", "Qt Data Visualization"),
    ("PySide6/Qt6Graphs.dll", "Qt Graphs"),
    ("PySide6/Qt6Quick3D.dll", "Qt Quick 3D"),
    ("PySide6/Qt6Quick3DPhysics.dll", "Qt Quick 3D"),
    ("PySide6/Qt6QuickTimeline.dll", "Qt Quick Timeline"),
    ("PySide6/Qt6VirtualKeyboard.dll", "Qt Virtual Keyboard"),
    ("PySide6/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll",
     "Qt Virtual Keyboard"),
])
def test_nur_gpl_modul_im_bundle_bricht_den_bau(datei, wort):
    b = fk.qt_befunde([datei.replace("/", "\\")])
    assert len(b) == 1, b
    assert wort in b[0] and "GPLv3" in b[0]


def test_qt_quick_ist_kein_nur_gpl_modul():
    """Der Namensanfang allein genuegt nicht: ``Qt6Quick.dll`` (LGPL) faengt an
    wie ``Qt6Quick3D.dll`` und ``Qt6QuickTimeline.dll`` (nur GPL)."""
    assert fk.nur_gpl_modul("Quick") is None
    assert fk.nur_gpl_modul("QuickWidgets") is None
    assert fk.nur_gpl_modul("Qml") is None
    assert fk.nur_gpl_modul("Quick3DRuntimeRender") == "Qt Quick 3D"
    assert fk.qt_befunde(["PySide6/Qt6Quick.dll", "PySide6/Qt6QuickWidgets.dll"]) == []


@pytest.mark.parametrize("datei, wort", [
    ("PySide6/Qt6Bluetooth.dll", "ohne Eintrag"),           # LGPL, aber nicht geprueft
    ("PySide6/qml/QtQuick/Controls/qmldir", "QML-Modul"),
    ("PySide6/plugins/sqldrivers/qsqlite.dll", "Plugin-Ordner"),
    ("PySide6/d3dcompiler_47.dll", "unbekannter Herkunft"),
])
def test_unbekanntes_von_qt_bricht_den_bau(datei, wort):
    b = fk.qt_befunde([datei])
    assert len(b) == 1 and wort in b[0], b


def test_das_gefilterte_bundle_ist_fuer_qt_in_ordnung():
    ziele, _ = _auswahl()
    assert fk.qt_befunde(ziele) == []
    # … und ohne den Filter gerade nicht.
    assert len(fk.qt_befunde(_BINAER + _DATEN)) >= 10


def test_was_der_echte_bau_uebrig_liess_steht_in_der_tabelle():
    """Stand des echten Bundles vom 12.10.2026 (PySide6 6.12.0): diese 21
    Bibliotheken blieben nach dem Filter. Aendert sich das, sagt es der Bau."""
    assert sorted(fk.QT_BIBLIOTHEKEN) == [
        "Core", "Gui", "Multimedia", "MultimediaWidgets", "Network", "OpenGL", "Pdf",
        "Positioning", "PrintSupport", "Qml", "QmlMeta", "QmlModels", "QmlWorkerScript",
        "Quick", "QuickWidgets", "SerialPort", "Svg", "WebChannel", "WebEngineCore",
        "WebEngineWidgets", "Widgets"]
    for stamm in fk.QT_BIBLIOTHEKEN:
        assert fk.nur_gpl_modul(stamm) is None, stamm
    for name in qt_umfang.PFLICHT_QT:
        assert name[3:-4] in fk.QT_BIBLIOTHEKEN, name


# ── Lizenzangaben der Pakete lesen ───────────────────────────────────────────

class _Meta(dict):
    def get_all(self, name):
        wert = self.get(name)
        return list(wert) if isinstance(wert, (list, tuple)) else ([wert] if wert else None)


@pytest.mark.parametrize("meta, erwartet", [
    ({"License-Expression": "MPL-2.0", "License": "egal"}, "MPL-2.0"),
    ({"Classifier": ["License :: OSI Approved :: MIT License", "Topic :: X"],
      "License": "MIT"}, "MIT License"),
    ({"Classifier": ["License :: OSI Approved :: Apache Software License",
                     "License :: OSI Approved :: GNU General Public License v2 (GPLv2)"]},
     "Apache Software License / GNU General Public License v2 (GPLv2)"),
    ({"License": "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only\nzweite Zeile"},
     "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only"),
    ({}, ""),
])
def test_lizenzangabe_aus_den_metadaten(meta, erwartet):
    assert fk.lizenzangabe(_Meta(meta)) == erwartet


def test_angabe_passt_zur_tabelle():
    assert fk.angabe_passt("MIT", fk.PAKETE["sqlalchemy"])
    assert fk.angabe_passt("mit license", fk.PAKETE["blinker"])
    assert fk.angabe_passt(fk._QT_ANGABE[0], fk.PAKETE["shiboken6"])
    assert not fk.angabe_passt("GPL-3.0-only", fk.PAKETE["sqlalchemy"])
    assert not fk.angabe_passt("", fk.PAKETE["sqlalchemy"]), "keine Angabe ist keine Zusage"


@pytest.mark.parametrize("rel, ja", [
    ("bidict-0.24.1.dist-info/licenses/LICENSE", True),
    ("numpy-2.5.4.dist-info/licenses/numpy/_core/src/multiarray/dragon4_LICENSE.txt", True),
    ("mido-1.3.3.dist-info/LICENSE", True),
    ("pyusb-1.3.1.dist-info/AUTHORS", True),
    ("setuptools/_vendor/jaraco.text-4.0.0.dist-info/LICENSE", True),
    ("bidict-0.24.1.dist-info/METADATA", False),
    ("bidict-0.24.1.dist-info/RECORD", False),
    ("flask/license_helper.py", False),
])
def test_was_als_lizenzdatei_eines_pakets_gilt(rel, ja):
    assert fk.ist_lizenzdatei(rel) is ja


# ── Schreiben: Lizenzdateien und die Liste dieses Builds ─────────────────────

def test_lizenzdateien_und_liste_werden_geschrieben(tmp_path):
    quelle = tmp_path / "quelle"
    quelle.mkdir()
    for name in ("flask_LICENSE", "vendor_LICENSE", "python_LICENSE"):
        (quelle / name).write_text(name, encoding="utf-8")
    info = _gute_info()
    for eintrag in info.values():
        eintrag["lizenzdateien"] = []
    info["flask"]["version"] = "3.1.3"
    info["flask"]["lizenzdateien"] = [
        ("flask-3.1.3.dist-info/licenses/LICENSE.txt", str(quelle / "flask_LICENSE")),
        ("flask/_vendor/klein-1.0.dist-info/LICENSE", str(quelle / "vendor_LICENSE"))]
    info["pyside6-essentials"]["version"] = "6.12.0"
    ziel = tmp_path / "arbeit"
    datas = fk.schreibe_lizenzen(str(ziel), _erfasst(), info, str(quelle / "python_LICENSE"),
                                 "3.12.10", qt_dateien=["PySide6\\Qt6Core.dll"])
    wohin = {os.path.relpath(q, str(ziel)).replace(os.sep, "/"): z for q, z in datas}
    assert wohin["licenses/pakete/Flask-3.1.3/LICENSE.txt"] == "licenses/pakete/Flask-3.1.3"
    assert "licenses/pakete/Flask-3.1.3/klein-1.0.dist-info/LICENSE" in wohin
    assert wohin["licenses/Python-LICENSE.txt"] == "licenses"
    assert wohin[fk.LISTE] == "licenses"
    assert (ziel / "licenses" / "Python-LICENSE.txt").read_text(encoding="utf-8") == \
        "python_LICENSE"
    liste = (ziel / "licenses" / "BUNDLE-KOMPONENTEN.txt").read_text(encoding="utf-8")
    assert "Python 3.12.10 | PSF-2.0 |" in liste
    assert "Flask 3.1.3 | BSD-3-Clause | https://github.com/pallets/flask" in liste
    assert "https://pypi.org/project/Flask/3.1.3/" in liste
    assert "pyserial 1.0 | BSD-3-Clause |" in liste
    assert "Lizenztext: BSD-3-Clause-pyserial.txt" in liste, "Text aus dem Repo"
    assert "PySide6_Essentials 6.12.0 | LGPL-3.0-only |" in liste
    assert "LGPL-3.0.txt, GPL-3.0.txt" in liste
    assert "\nQt6Core.dll | Qt Core\n" in liste
    assert "FFmpeg | LGPL-2.1-or-later |" in liste
    assert "Microsoft Visual C++ Laufzeit | Microsoft (nicht Open Source) |" in liste
    assert "Universal C Runtime" not in liste, "wird nicht mehr mitgeliefert"


def test_schreiben_raeumt_den_alten_stand_weg(tmp_path):
    """Sonst reiste die Lizenzdatei eines Pakets mit, das laengst nicht mehr im
    Bundle liegt."""
    ziel = tmp_path / "arbeit"
    alt = ziel / "licenses" / "pakete" / "Weg-1.0"
    alt.mkdir(parents=True)
    (alt / "LICENSE").write_text("alt", encoding="utf-8")
    info = _gute_info()
    for eintrag in info.values():
        eintrag["lizenzdateien"] = []
    fk.schreibe_lizenzen(str(ziel), _erfasst(), info, None, "3.12.10")
    assert not alt.exists()


# ── Tabelle <-> Hinweise <-> requirements <-> licenses/ ──────────────────────

def _tabelle_in_den_hinweisen() -> dict[str, tuple[str, str]]:
    aus = {}
    for zeile in _abschnitt("Windows-Installationspaket").splitlines():
        m = re.match(r"^\| ([^|]+) \| ([^|]+) \| <([^>]+)> \|$", zeile)
        if m:
            aus[m.group(1).strip()] = (m.group(2).strip(), m.group(3).strip())
    return aus


def test_die_hinweise_nennen_genau_die_pakete_der_tabelle():
    in_hinweisen = _tabelle_in_den_hinweisen()
    in_tabelle = {n: (e["lizenz"], e["quelle"]) for n, e in fk.PAKETE.items()}
    assert in_hinweisen == in_tabelle, (
        "THIRD_PARTY_NOTICES.md und fremdkomponenten.PAKETE laufen auseinander — "
        "Tabelle neu erzeugen: python packaging/windows/fremdkomponenten.py")
    assert len(in_tabelle) >= 30


def test_die_tabelle_ist_sauber():
    for name, e in fk.PAKETE.items():
        assert name == fk.normal(name), name
        assert e["lizenz"] and e["quelle"].startswith("https://"), name
        assert "|" not in e["lizenz"] + e["quelle"], name
    assert not set(fk.PAKETE) & set(fk.NICHT_IM_BUNDLE)
    muster = [m for _n, _l, _q, m in fk.EINGEBETTET]
    for m in muster:
        re.compile(m)


def _anforderungen() -> list[str]:
    aus = []
    for zeile in _lies("requirements.txt").splitlines():
        zeile = zeile.split("#", 1)[0].strip()
        if zeile:
            aus.append(fk.normal(re.split(r"[\s<>=!~;\[]", zeile, maxsplit=1)[0]))
    return aus


def test_jede_anforderung_ist_eingeordnet():
    """requirements.txt ist NICHT die Liste des Bundles (die zieht der Bau aus
    dem Bundle selbst). Aber wer dort etwas eintraegt, muss sagen, was daraus
    im Setup wird: Eintrag in ``PAKETE`` oder, mit Grund, in ``NICHT_IM_BUNDLE``."""
    namen = _anforderungen()
    assert "flask" in namen and "pyside6" in namen, "Gegenprobe: Datei wird gelesen"
    offen = [n for n in namen if n not in fk.PAKETE and n not in fk.NICHT_IM_BUNDLE]
    assert offen == [], (f"{offen}: in packaging/windows/fremdkomponenten.py "
                         "einordnen (PAKETE mit Lizenz und Quelle oder NICHT_IM_BUNDLE)")
    for name, grund in fk.NICHT_IM_BUNDLE.items():
        assert name in namen, f"{name}: steht nicht mehr in requirements.txt"
        assert len(grund) > 20, name


def test_was_nicht_ins_bundle_kommt_wird_wirklich_nicht_importiert():
    """„Liegt nicht im Bundle“ gilt nur, solange das Programm das Paket nicht
    importiert — sonst packt PyInstaller es ein, und der Bau verlangt einen
    Eintrag."""
    muster = re.compile(r"(?m)^\s*(?:import|from)\s+(mido|winrt)\b")
    treffer = []
    for wurzel, dirs, dateien in os.walk(os.path.join(_REPO, "src")):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for d in dateien:
            if d.endswith(".py"):
                pfad = os.path.join(wurzel, d)
                with io.open(pfad, encoding="utf-8") as f:
                    if muster.search(f.read()):
                        treffer.append(os.path.relpath(pfad, _REPO))
    assert treffer == [], treffer


def test_lizenztexte_der_tabelle_liegen_im_repo_und_kommen_mit():
    im_bundle = set(bundle_inhalt.dateien(_REPO))
    for name, e in fk.PAKETE.items():
        for t in e.get("texte", ()):
            assert os.path.isfile(os.path.join(_REPO, "licenses", t)), (name, t)
            assert f"licenses/{t}" in im_bundle, (
                f"licenses/{t}: Git kennt die Datei nicht — bundle_inhalt packt "
                "nur, was eingecheckt ist")


@pytest.mark.parametrize("datei, anfang, muss", [
    ("LGPL-3.0.txt", "GNU LESSER GENERAL PUBLIC LICENSE", "Version 3, 29 June 2007"),
    ("GPL-3.0.txt", "GNU GENERAL PUBLIC LICENSE", "Version 3, 29 June 2007"),
    ("BSD-3-Clause-pyserial.txt", "Copyright (c) 2001-2020 Chris Liechti",
     "Redistributions in binary form must reproduce"),
    ("Unlicense-python-osc.txt", "This is free and unencumbered software",
     "unlicense.org"),
])
def test_die_neuen_lizenztexte_sind_die_richtigen(datei, anfang, muss):
    text = _lies("licenses", datei)
    assert text.lstrip().startswith(anfang)
    assert muss in text
    assert len(text) > 1000


def test_qt_abschnitt_nennt_lizenz_module_und_die_lgpl_pflichten():
    a = _abschnitt("Qt und PySide6")
    assert "(licenses/LGPL-3.0.txt)" in a and "(licenses/GPL-3.0.txt)" in a
    assert "Copyright © The Qt Company Ltd." in a
    glatt = _glatt(a)
    for modul in set(fk.QT_BIBLIOTHEKEN.values()):
        assert modul in glatt, f"eingebautes Modul fehlt: {modul}"
    for stamm in fk.QT_BIBLIOTHEKEN:
        assert f"`Qt6{stamm}.dll`" in glatt, stamm
    for modul in set(fk.QT_NUR_GPL.values()):
        assert modul in glatt, f"Nur-GPL-Modul nicht genannt: {modul}"
    assert "nur unter der GPLv3" in glatt
    for pflicht in ("*Hinweis:*", "*Lizenztexte:*", "*Dynamisch gebunden:*",
                    "*Austauschbar:*", "*Unverändert:*", "*Quelltext:*"):
        assert pflicht in a, pflicht
    assert "download.qt.io/official_releases/qt/" in a
    assert "download.qt.io/official_releases/QtForPython/pyside6/" in a


def test_eingebettete_bibliotheken_stehen_in_den_hinweisen():
    text = _glatt(_lies("THIRD_PARTY_NOTICES.md"))
    for wort in ("FFmpeg", "Chromium", "OpenBLAS", "Mesa llvmpipe", "OpenSSL", "libffi",
                 "SQLite", "Microsoft Visual C++ Laufzeit", "Universal C Runtime",
                 "Bootloader Exception", "Python Software Foundation License"):
        assert wort in text, wort
    # Microsoft-Dateien sind nicht Open Source — das steht da, nicht geraten.
    assert "**nicht** Open Source" in text


def test_ffmpeg_variante_und_bidict_hinweis_stehen_da():
    a = _glatt(_abschnitt("FFmpeg"))
    assert "LGPL version 2.1 or later" in a
    assert "`--enable-gpl`" in a and "`--enable-nonfree`" in a
    w = _glatt(_abschnitt("Windows-Installationspaket"))
    assert "**bidict** steht unter der Mozilla Public License 2.0" in w
    assert "unverändert" in w


def test_universal_c_runtime_steht_als_nicht_eingebaut_in_den_hinweisen():
    a = _glatt(_abschnitt("Weitere enthaltene Bibliotheken"))
    assert "Nicht eingebaut – Universal C Runtime" in a
    assert "gehört zu Windows 10 und 11" in a
    iss = _lies("packaging", "windows", "LightOS.iss")
    assert "MinVersion=10.0" in iss, "darauf beruht das Weglassen"


def test_offene_punkte_sind_als_offen_gekennzeichnet():
    """Was rechtlich nicht geklaert ist, stand als offen da. Chromium und Mesa
    sind seit LIZ-2 (Rest) erledigt: dort steht jetzt die Sammeldatei
    (tests/test_liz2_rest_sammeldateien.py) und kein „Offen“ mehr."""
    assert "**Offen:**" not in _abschnitt("Chromium")
    assert "licenses/QtWebEngine-THIRD-PARTY.txt" in _abschnitt("Chromium")
    assert "**Offen:**" not in _abschnitt("Weitere enthaltene Bibliotheken")
    # Mesa hat einen eigenen Abschnitt mit Herkunft/Urheber/Lizenz (PROC-18-Waechter).
    assert "**Offen:**" not in _abschnitt("Mesa llvmpipe")
    assert "licenses/Mesa-opengl32sw.txt" in _abschnitt("Mesa llvmpipe")


# ── Spec, Setup-Skript, Selbsttest ───────────────────────────────────────────

def test_die_spec_filtert_und_prueft_vor_dem_packen():
    spec = _lies("packaging", "windows", "LightOS.spec")
    filtern = spec.index("qt_umfang.auswahl(a.binaries, a.datas)")
    pruefen = spec.index("fremdkomponenten.pruefe_und_schreibe(")
    packen = spec.index("pyz = PYZ(a.pure)")
    assert spec.index("a = Analysis(") < filtern < pruefen < packen
    # Befunde brechen den Bau ab — sie werden nicht nur gedruckt.
    assert spec.count("raise SystemExit(") >= 2
    assert 'if _befunde:' in spec and 'if _qt["fehler"]:' in spec
    # Geprueft wird ALLES, was ins Bundle kommt.
    for teil in ("a.pure", "a.binaries", "a.datas", "a.scripts"):
        assert f"list({teil})" in spec, teil


def test_pyside_python_teile_liegen_offen_im_programmordner():
    """LGPL: auch die wenigen Python-Dateien von PySide6/shiboken6 sollen
    austauschbar sein — nicht im Archiv von LightOS.exe stecken."""
    assert dict(bundle_inhalt.OFFEN_MITLIEFERN) == {"PySide6": "py", "shiboken6": "py"}
    spec = _lies("packaging", "windows", "LightOS.spec")
    assert "module_collection_mode=dict(bundle_inhalt.OFFEN_MITLIEFERN)" in spec
    assert "upx=False" in spec and "exclude_binaries=True" in spec, \
        "onedir, DLLs unveraendert und als eigene Dateien"


def test_das_setup_nimmt_die_lizenzen_aus_dem_bundle():
    """Neben die exe gehoert derselbe Ordner wie ins Bundle — mit der Liste und
    den Texten der Pakete, die es nur dort gibt."""
    iss = _lies("packaging", "windows", "LightOS.iss")
    zeilen = [z for z in iss.splitlines() if 'DestDir: "{app}\\licenses"' in z]
    assert len(zeilen) == 1, zeilen
    assert '{#DistDir}\\_internal\\licenses\\*' in zeilen[0]
    assert "recursesubdirs" in zeilen[0]


def _programmordner(tmp_path, qt=("Qt6Core.dll", "Qt6Gui.dll"), liste=True, qml=False):
    w = tmp_path / "_internal"
    (w / "licenses" / "pakete" / "Flask-3.1.3").mkdir(parents=True)
    (w / "licenses" / "pakete" / "Flask-3.1.3" / "LICENSE.txt").write_text("x", "utf-8")
    for name in ("Python-LICENSE.txt", "LGPL-3.0.txt", "GPL-3.0.txt"):
        (w / "licenses" / name).write_text("x", encoding="utf-8")
    if liste:
        (w / "licenses" / "BUNDLE-KOMPONENTEN.txt").write_text(
            "Qt-Bibliotheken\nQt6Core.dll | Qt Core\nQt6Gui.dll | Qt GUI\n", encoding="utf-8")
    (w / "PySide6").mkdir()
    for name in qt:
        (w / "PySide6" / name).write_bytes(b"")
    if qml:
        (w / "PySide6" / "qml").mkdir()
    return str(w)


def test_selbsttest_gepackt_mit_allem_ist_ruhig(tmp_path):
    assert selbsttest.pruefe_fremdlizenzen(_programmordner(tmp_path), gefroren=True) == []


def test_selbsttest_gepackt_ohne_liste_ist_ein_fehler(tmp_path):
    f = selbsttest.pruefe_fremdlizenzen(_programmordner(tmp_path, liste=False), gefroren=True)
    assert f == ["Lizenzen: fehlt licenses/BUNDLE-KOMPONENTEN.txt"]


def test_selbsttest_findet_eine_qt_bibliothek_ausserhalb_der_liste(tmp_path):
    """Unabhaengig vom Bauwerkzeug: liegt im FERTIGEN Paket eine Qt-Bibliothek,
    die seine eigene Liste nicht nennt, ist sie am Filter vorbei hineingeraten."""
    w = _programmordner(tmp_path, qt=("Qt6Core.dll", "Qt6Gui.dll", "Qt6Charts.dll"))
    f = selbsttest.pruefe_fremdlizenzen(w, gefroren=True)
    assert len(f) == 1 and "Qt6Charts.dll" in f[0], f


def test_selbsttest_findet_die_universal_c_runtime(tmp_path):
    w = _programmordner(tmp_path)
    for name in ("ucrtbase.dll", "api-ms-win-crt-heap-l1-1-0.dll"):
        with open(os.path.join(w, name), "wb"):
            pass
    f = selbsttest.pruefe_fremdlizenzen(w, gefroren=True)
    assert len(f) == 1 and "Universal C Runtime" in f[0] and "2 Datei(en)" in f[0], f


def test_selbsttest_findet_den_qml_ordner(tmp_path):
    f = selbsttest.pruefe_fremdlizenzen(_programmordner(tmp_path, qml=True), gefroren=True)
    assert len(f) == 1 and "QML-Ordner" in f[0], f


def test_selbsttest_im_quellbetrieb_verlangt_nichts(tmp_path):
    assert selbsttest.pruefe_fremdlizenzen(str(tmp_path), gefroren=False) == []


def test_der_bericht_fuehrt_die_pruefung_mit(monkeypatch):
    monkeypatch.setattr(selbsttest, "pruefe_fremdlizenzen",
                        lambda *a, **k: ["Lizenzen: Probe"])
    code, zeilen = selbsttest.bericht()
    assert code == 1 and "FEHLER Lizenzen: Probe" in zeilen


def test_die_setup_pipeline_laesst_den_selbsttest_entscheiden():
    ablauf = _lies(".github", "workflows", "windows-setup.yml")
    assert "--selbsttest" in ablauf
    assert "packaging/**" in ablauf, "ein Push an der Paketierung baut das Setup"


# ── Controller-Bibliothek: eigene Arbeit unter CC0, kein QLC+-Import ─────────

def _profile() -> list[tuple[str, dict]]:
    ordner = os.path.join(_REPO, "data", "controller_library")
    aus = []
    for name in sorted(os.listdir(ordner)):
        if name.endswith(".json"):
            with io.open(os.path.join(ordner, name), encoding="utf-8") as f:
                aus.append((name, json.load(f)))
    return aus


def test_jedes_mitgelieferte_controller_profil_ist_cc0_mit_quelle():
    profile = _profile()
    assert len(profile) >= 20
    for name, p in profile:
        assert "CC0" in str(p.get("license", "")), name
        assert len(str(p.get("source", ""))) > 20, f"{name}: ohne Quelle"


def test_kein_mitgeliefertes_controller_profil_stammt_aus_qlc():
    """Gegenprobe zu QLC+ (Apache-2.0): der Einleser (``qxi_import``) vergibt
    die Kennung ``qlc_…``, die Quelle „QLC+-Inputprofil“ und die Lizenz
    „Apache-2.0 (QLC+ …)“. So ein Profil gehoert in den Datenordner des
    Nutzers — im mitgelieferten Ordner stuende es unter falscher Lizenz."""
    einleser = _lies("src", "core", "controllers", "qxi_import.py")
    assert '"qlc_"' in einleser and "Apache-2.0 (QLC+" in einleser and \
        "QLC+-Inputprofil" in einleser, "Gegenprobe: so markiert der Einleser"
    for name, p in _profile():
        roh = json.dumps(p, ensure_ascii=False).lower()
        assert not str(p.get("id", "")).startswith("qlc_"), name
        assert "apache" not in roh and "qlc" not in roh, name


def test_die_hinweise_nennen_die_controller_bibliothek_als_cc0():
    a = _abschnitt("Controller-Bibliothek")
    assert "`data/controller_library/`" in a
    assert "CC0" in a and "eigene Arbeit" in a
    assert "Apache-2.0" in a and "qlc_" in a, "Abgrenzung zu eingelesenen QLC+-Profilen"
    assert "CC0" in _lies("data", "controller_library", "README.md")
