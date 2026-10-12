"""STAB-34: Nach dem Laden einer Show fragt LightOS weiter „Show speichern?".

Der Befund (Windows-Teil von QA-96, echte App): drei Bibliotheksmodule setzten
beim Import ``os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")`` —
``capability/reflect.py``, ``capability/manifest.py`` und
``show/showbuilder/builder.py``. Fuer Werkzeuge ist das richtig: sie bauen ihre
Qt-Anwendung erst danach und sollen kein Fenster brauchen. Seit TOOL-25 laedt
aber auch die Lade-Pruefung der App (``sync.validate_and_repair``) bei jeder
Show mit VC-Widgets ``capability.validate`` und damit ``reflect``. Die laufende
App — Qt laengst auf „windows“, Fenster sichtbar — hatte danach die Variable
auf „offscreen“ stehen, und ``main_window._exit_prompt_suppressed()`` las
daraus „niemand sitzt davor“: Beenden, Neue Show, Show laden und „Ältere
Version öffnen“ verwarfen ungespeicherte Aenderungen ohne Rueckfrage, das
Beenden auch ohne Sicherung.

Zwei Dinge werden festgehalten:

* **Ursache:** kein Modul unter ``src/`` schreibt die Variable einer laufenden
  Anwendung unter. Werkzeuge bekommen die Vorgabe weiter.
* **Zweites Netz:** ob jemand vor dem Bildschirm sitzt, sagt die Plattform, die
  Qt WIRKLICH benutzt — nicht eine Umgebungsvariable, die jeder Import aendern
  kann.

Die Unterprozesse starten ihre Qt-Anwendung mit ``-platform offscreen`` auf der
Kommandozeile und OHNE die Variable: so laeuft der Test auch ohne Bildschirm,
und die Variable ist — wie beim Nutzer — anfangs leer.
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import textwrap
from unittest import mock

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SHOW = os.path.join(_REPO, "shows", "Demo_ZQ_Buehne.lshow")     # 11 VC-Widgets

#: Die Module, die die Vorgabe fuer Werkzeuge setzen — und der Weg, auf dem die
#: App das erste von ihnen laedt (``sync.validate_and_repair`` -> ``validate``).
MODULE = ("src.core.capability.reflect", "src.core.capability.manifest",
          "src.core.capability.validate", "src.core.show.showbuilder.builder")

_SCHREIBT = re.compile(
    r"""os\.environ\s*(?:\.setdefault\(\s*|\[\s*)["']QT_QPA_PLATFORM["']""")
#: Der eine Ort, der die Variable anfassen darf.
_ERLAUBT = os.path.join("src", "core", "qt_plattform.py")


def _sandbox(tmp_path) -> dict:
    """Umgebung, in der jeder Schreibort der App im Wegwerf-Ordner liegt —
    dieselbe Liste wie ``tools/app_messung.py`` (eine Quelle, kein Nachbau)."""
    spec = importlib.util.spec_from_file_location(
        "app_messung_stab34", os.path.join(_REPO, "tools", "app_messung.py"))
    am = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(am)
    env = dict(os.environ)
    env.update(am.sandbox_umgebung(str(tmp_path / "sandbox")))
    env.pop("QT_QPA_PLATFORM", None)            # wie beim Nutzer: nicht gesetzt
    env["LIGHTOS_NO_OUTPUT_THREAD"] = "1"
    env["PYTHONPATH"] = _REPO
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _lauf(code: str, tmp_path, *args, timeout=240) -> dict:
    """Unterprozess starten; liefert seine ``NAME=wert``-Zeilen als Dict."""
    r = subprocess.run([sys.executable, "-c", textwrap.dedent(code), *args],
                       capture_output=True, text=True, timeout=timeout, cwd=_REPO,
                       env=_sandbox(tmp_path), encoding="utf-8", errors="replace")
    assert r.returncode == 0, f"Unterprozess endet mit {r.returncode}:\n{r.stderr[-3000:]}"
    aus = {}
    for zeile in r.stdout.splitlines():
        if "=" in zeile and zeile.split("=", 1)[0].isupper():
            name, wert = zeile.split("=", 1)
            aus[name] = wert
    return aus


_KOPF = """
    import importlib, os, sys
    assert "QT_QPA_PLATFORM" not in os.environ
    def ende():
        sys.stdout.flush()
        os._exit(0)                 # kein nativer Qt-Abbau im Testprozess
"""

_MIT_ANWENDUNG = _KOPF + """
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication
    app = QApplication(["lightos-test", "-platform", "offscreen"])
    print("PLATTFORM=" + QGuiApplication.platformName())
"""


# ── Ursache: die Variable gehoert der laufenden Anwendung ───────────────────

def test_nur_ein_ort_in_src_schreibt_die_plattform_variable():
    """Jede weitere Stelle waere derselbe Fehler noch einmal — auch in einem
    Modul, das heute noch kein App-Weg laedt."""
    treffer = []
    for ordner, _unter, dateien in os.walk(os.path.join(_REPO, "src")):
        for name in dateien:
            if not name.endswith(".py"):
                continue
            pfad = os.path.join(ordner, name)
            rel = os.path.relpath(pfad, _REPO)
            if rel == _ERLAUBT:
                continue
            with open(pfad, encoding="utf-8") as f:
                for nr, zeile in enumerate(f, 1):
                    if _SCHREIBT.search(zeile) and not zeile.lstrip().startswith("#"):
                        treffer.append(f"{rel}:{nr}")
    assert not treffer, (
        "QT_QPA_PLATFORM wird ausserhalb von src/core/qt_plattform.py gesetzt: "
        + ", ".join(treffer) + " — dort offscreen_fuer_werkzeuge() benutzen.")


@pytest.mark.parametrize("modul", MODULE)
def test_import_in_laufender_anwendung_laesst_die_variable_leer(modul, tmp_path):
    aus = _lauf(_MIT_ANWENDUNG + """
    importlib.import_module(sys.argv[1])
    print("VARIABLE=" + repr(os.environ.get("QT_QPA_PLATFORM")))
    ende()
    """, tmp_path, modul)
    assert aus["PLATTFORM"] == "offscreen"
    assert aus["VARIABLE"] == "None", (
        f"{modul} hat der laufenden Anwendung QT_QPA_PLATFORM={aus['VARIABLE']} "
        "untergeschoben")


@pytest.mark.parametrize("modul", MODULE)
def test_werkzeuge_bekommen_die_vorgabe_weiter(modul, tmp_path):
    """Ohne laufende Anwendung (Werkzeug, Skript): unveraendert offscreen — ein
    Generatorlauf darf kein Fenster brauchen."""
    aus = _lauf(_KOPF + """
    importlib.import_module(sys.argv[1])
    print("VARIABLE=" + repr(os.environ.get("QT_QPA_PLATFORM")))
    ende()
    """, tmp_path, modul)
    assert aus["VARIABLE"] == "'offscreen'"


def test_vorgabe_ueberschreibt_keine_ausdrueckliche_wahl(tmp_path):
    aus = _lauf("""
    import os, sys
    os.environ["QT_QPA_PLATFORM"] = "minimal"
    from src.core.qt_plattform import offscreen_fuer_werkzeuge
    offscreen_fuer_werkzeuge()
    print("VARIABLE=" + repr(os.environ.get("QT_QPA_PLATFORM")))
    sys.stdout.flush()
    os._exit(0)
    """, tmp_path)
    assert aus["VARIABLE"] == "'minimal'"


def test_show_laden_und_pruefen_laesst_die_variable_leer(tmp_path):
    """Der Weg der App: Show mit VC-Widgets laden, dann die Lade-Pruefung
    (dieselbe, die das Hauptfenster nach jedem Laden fuer sein Banner ruft)."""
    aus = _lauf(_MIT_ANWENDUNG + """
    from src.core.app_state import get_state
    from src.core.show.show_file import load_show
    ok, meldung = load_show(sys.argv[1])
    assert ok, meldung
    st = get_state()
    print("WIDGETS=" + str(len((st._vc_layout or {}).get("widgets", []))))
    from src.core.sync import validate_and_repair
    validate_and_repair(st, fix=False)
    print("GELADEN=" + str("src.core.capability.reflect" in sys.modules))
    print("VARIABLE=" + repr(os.environ.get("QT_QPA_PLATFORM")))
    ende()
    """, tmp_path, _SHOW)
    assert int(aus["WIDGETS"]) > 0, "die Demo-Show hat keine VC-Widgets mehr"
    assert aus["GELADEN"] == "True", (
        "die Lade-Pruefung laedt capability.reflect nicht mehr — dieser Test "
        "prueft dann nichts; den neuen Weg hier nachziehen")
    assert aus["VARIABLE"] == "None"


# ── Zweites Netz: die Frage haengt an der Plattform, die Qt benutzt ─────────

def _plattform(name):
    """``QGuiApplication.platformName`` so stellen, als liefe Qt auf ``name``."""
    from PySide6.QtGui import QGuiApplication
    return mock.patch.object(QGuiApplication, "platformName",
                             staticmethod(lambda: name))


@pytest.fixture
def qt():
    """Eine Qt-Anwendung (im Testlauf ohne Bildschirm)."""
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class TestFrageHaengtAnDerEchtenPlattform:
    def test_sichtbare_app_fragt_auch_mit_untergeschobener_variable(self, qt, monkeypatch):
        """Der Fall aus dem Befund: Qt auf „windows“, Variable auf „offscreen“."""
        from src.ui import main_window as MW
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
        monkeypatch.delenv("LIGHTOS_NO_RECOVERY_PROMPT", raising=False)
        with _plattform("windows"):
            assert MW._exit_prompt_suppressed() is False
            assert MW._recovery_prompt_suppressed() is False

    @pytest.mark.parametrize("name", ["xcb", "wayland", "cocoa", "windows"])
    def test_jede_bildschirm_plattform_fragt(self, qt, monkeypatch, name):
        from src.ui import main_window as MW
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
        with _plattform(name):
            assert MW._exit_prompt_suppressed() is False

    def test_ohne_bildschirm_bleibt_die_frage_aus(self, qt, monkeypatch):
        """Testlauf und Werkzeuge haengen weiter nie in einem modalen Dialog —
        auch wenn die Plattform ueber die Kommandozeile gewaehlt wurde."""
        from src.ui import main_window as MW
        monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
        monkeypatch.delenv("LIGHTOS_NO_RECOVERY_PROMPT", raising=False)
        with _plattform("offscreen"):
            assert MW._exit_prompt_suppressed() is True
            assert MW._recovery_prompt_suppressed() is True

    def test_schalter_fuer_die_wiederherstellung_gilt_weiter(self, qt, monkeypatch):
        from src.ui import main_window as MW
        monkeypatch.setenv("LIGHTOS_NO_RECOVERY_PROMPT", "1")
        with _plattform("windows"):
            assert MW._recovery_prompt_suppressed() is True
            assert MW._exit_prompt_suppressed() is False     # eigener Schutz (UI-69)

    def test_ohne_qt_anwendung_entscheidet_die_variable(self, monkeypatch):
        """Vor dem Start der Anwendung gibt es keine Plattform zu fragen."""
        from src.core import qt_plattform
        with mock.patch.object(qt_plattform, "_laufende_plattform", lambda: ""):
            monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen:size=1x1")
            assert qt_plattform.ohne_bildschirm() is True
            monkeypatch.setenv("QT_QPA_PLATFORM", "xcb")
            assert qt_plattform.ohne_bildschirm() is False
            monkeypatch.delenv("QT_QPA_PLATFORM")
            assert qt_plattform.ohne_bildschirm() is False

    def test_diagnosepaket_meldet_in_der_sichtbaren_app_wohin(self, qt, monkeypatch, tmp_path):
        """Dieselbe Variable liess nach dem Laden einer Show auch die Meldung
        „Gespeichert unter …“ des Diagnosepakets weg."""
        from PySide6.QtWidgets import QMessageBox
        from src.ui.main_window import MainWindow
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
        ziel = tmp_path / "paket.zip"
        gezeigt = []
        with _plattform("windows"), \
                mock.patch.object(QMessageBox, "information",
                                  lambda *a, **k: gezeigt.append(a[2])
                                  or QMessageBox.StandardButton.Ok):
            pfad = MainWindow._diagnosepaket_speichern(None, str(ziel))
        assert pfad == str(ziel) and ziel.is_file()
        assert gezeigt and str(ziel) in gezeigt[0]


def test_die_drei_fragen_lesen_die_variable_nicht_mehr_selbst():
    """Im Hauptfenster entscheidet nur noch ``qt_plattform.ohne_bildschirm``."""
    with open(os.path.join(_REPO, "src", "ui", "main_window.py"), encoding="utf-8") as f:
        quelle = f.read()
    assert not re.search(r"""environ\.get\(\s*["']QT_QPA_PLATFORM["']""", quelle)
    assert quelle.count("ohne_bildschirm()") >= 3
