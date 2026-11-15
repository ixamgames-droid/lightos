"""UI-136 (4): Hinweis auf aktive System-Gesten — nur lesen, nie aendern.

Der ``gsettings``-Aufruf ist im Test immer eine Attrappe (kein echter Aufruf);
Einstellungen nur in ``tmp_path``.
"""
from __future__ import annotations

import os
import subprocess
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                           # noqa: E402

from src.ui import system_gesten as sg                               # noqa: E402

_app = QApplication.instance() or QApplication([])


def _attrappe(werte: dict, aufrufe: list | None = None):
    """Wie ``subprocess.run`` fuer ``gsettings get <schema> <key>``."""
    def lauf(args, **kw):
        if aufrufe is not None:
            aufrufe.append((list(args), kw))
        assert args[:2] == ["gsettings", "get"], "nur lesen"
        key = args[3]
        if key not in werte:
            return SimpleNamespace(returncode=1, stdout="", stderr="No such key")
        return SimpleNamespace(returncode=0, stdout=werte[key] + "\n", stderr="")
    return lauf


_CINNAMON = {"enabled": "true", "swipe-left-2": "'TILE_LEFT'",
             "swipe-right-2": "'TILE_RIGHT'", "tap-3": "'MEDIA_PLAY_PAUSE'"}


def test_linux_cinnamon_gesten_erkannt_nur_lesend():
    aufrufe = []
    g = sg.pruefen("linux", _attrappe(_CINNAMON, aufrufe))
    assert len(g) == 3 and "TILE_LEFT" in g[0] and "MEDIA_PLAY_PAUSE" in g[2]
    for args, kw in aufrufe:
        assert args[1] == "get" and args[2] == sg.SCHEMA
        assert kw["timeout"] == 2.0 and kw["text"] is True
        assert kw["encoding"] == "utf-8" and kw["errors"] == "replace"
    text = sg.hinweis_text(g, "linux")
    assert "System-Gesten sind aktiv" in text and "Systemeinstellungen → Gesten" in text


def test_linux_abgeschaltet_oder_leer_belegt():
    assert sg.pruefen("linux", _attrappe(dict(_CINNAMON, enabled="false"))) == []
    leer = {"enabled": "true", "swipe-left-2": "''", "swipe-right-2": "''", "tap-3": "''"}
    assert sg.pruefen("linux", _attrappe(leer)) == []


def test_linux_ohne_gsettings_oder_schema_still():
    def fehlt(*_a, **_k):
        raise FileNotFoundError("gsettings")

    def zeit(*_a, **_k):
        raise subprocess.TimeoutExpired("gsettings", 2)
    assert sg.pruefen("linux", fehlt) == []
    assert sg.pruefen("linux", zeit) == []
    assert sg.pruefen("linux", _attrappe({})) == []     # Schema fehlt
    assert sg.hinweis_text([], "linux") == ""


def test_windows_fester_text_ohne_aufruf():
    def nie(*_a, **_k):
        raise AssertionError("unter Windows kein Aufruf")
    g = sg.pruefen("win32", nie)
    assert g == [sg.WINDOWS_TEXT]
    assert "Drei- und Vier-Finger" in sg.hinweis_text(g, "win32")


def test_offscreen_ohne_attrappe_kein_echter_aufruf(monkeypatch):
    def nie(*_a, **_k):
        raise AssertionError("kein echter Aufruf")
    monkeypatch.setattr(subprocess, "run", nie)
    assert sg.pruefen("linux") == []
    assert sg.dialog_zeile("linux") == ""


class _Fenster:
    def __init__(self):
        self.meldungen = []

    def statusBar(self):                                  # noqa: N802
        return SimpleNamespace(showMessage=lambda t, ms=0: self.meldungen.append(t))


def test_start_dialog_einmal_und_nicht_mehr_zeigen(tmp_path):
    pfad = str(tmp_path / "ui_prefs.json")
    gezeigt = []
    lauf = _attrappe(_CINNAMON)
    r = sg.beim_start(_Fenster(), False, pfad, "linux", lauf,
                      dialog=lambda f, t: gezeigt.append(t) or False)
    assert r == "dialog" and len(gezeigt) == 1
    # OK (ohne „Nicht mehr zeigen"): beim naechsten Start wieder
    r = sg.beim_start(_Fenster(), False, pfad, "linux", lauf,
                      dialog=lambda f, t: gezeigt.append(t) or True)
    assert r == "dialog" and sg.abgeschaltet(pfad)
    r = sg.beim_start(_Fenster(), False, pfad, "linux", lauf,
                      dialog=lambda f, t: gezeigt.append(t) or False)
    assert r == "aus" and len(gezeigt) == 2


def test_nicht_mehr_zeigen_laesst_andere_prefs_stehen(tmp_path):
    pfad = tmp_path / "ui_prefs.json"
    pfad.write_text('{"gesten": {"halten_antippen": false}}', encoding="utf-8")
    assert sg.abschalten(str(pfad))
    import json
    d = json.loads(pfad.read_text(encoding="utf-8"))
    assert d["gesten"] == {"halten_antippen": False} and d[sg.PREF] is True
    kaputt = tmp_path / "kaputt.json"
    kaputt.write_text("{", encoding="utf-8")
    assert not sg.abschalten(str(kaputt))
    assert kaputt.read_text(encoding="utf-8") == "{"


def test_kiosk_nur_statuszeile(tmp_path):
    f = _Fenster()
    r = sg.beim_start(f, True, str(tmp_path / "p.json"), "linux", _attrappe(_CINNAMON),
                      dialog=lambda *_: (_ for _ in ()).throw(AssertionError("kein Dialog")))
    assert r == "status" and "System-Gesten" in f.meldungen[0]


def test_nichts_aktiv_kein_hinweis(tmp_path):
    r = sg.beim_start(_Fenster(), False, str(tmp_path / "p.json"), "linux",
                      _attrappe({"enabled": "false"}),
                      dialog=lambda *_: (_ for _ in ()).throw(AssertionError("kein Dialog")))
    assert r == "nichts"


def test_gesten_dialog_zeigt_hinweiszeile(tmp_path):
    from src.ui.widgets.gesten_dialog import GestenDialog
    d = GestenDialog(pfad=str(tmp_path / "p.json"),
                     system_zeile=sg.hinweis_text(["drei Finger tippen"], "linux"))
    assert d.system_hinweis is not None and "System-Gesten" in d.system_hinweis.text()
    d.deleteLater()
    d2 = GestenDialog(pfad=str(tmp_path / "p.json"))       # offscreen: nichts
    assert d2.system_hinweis is None
    d2.deleteLater()


def test_dialog_knoepfe_touchgross(monkeypatch):
    """Der echte Hinweis-Dialog: zwei Knoepfe, mind. 44 px hoch."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QMessageBox
    gesehen = {}

    def zu():
        box = QApplication.activeModalWidget()
        if not isinstance(box, QMessageBox):
            QTimer.singleShot(20, zu)
            return
        gesehen["texte"] = [b.text() for b in box.buttons()]
        gesehen["hoehe"] = min(b.minimumHeight() for b in box.buttons())
        nie = [b for b in box.buttons() if b.text() == "Nicht mehr zeigen"][0]
        nie.click()
    QTimer.singleShot(20, zu)
    assert sg._dialog_zeigen(None, "System-Gesten sind aktiv …") is True
    assert set(gesehen["texte"]) == {"OK", "Nicht mehr zeigen"}
    assert gesehen["hoehe"] >= 44
