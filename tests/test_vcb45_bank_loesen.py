"""VCB-45 Schritt 2/3: eine Bank der Virtual Console als eigenes Fenster.

Was eine Bank ist: ``VCWidget.bank`` (0..9, -1 = alle/geerbt); die Flaeche
zeigt ``active_bank`` = Executor-Seite der Wiedergabe (die Seitentasten des
APC schalten sie). Geprueft wird:

* Loesen zieht genau die obersten Widgets der Bank in ein eigenes Fenster;
  oben weiterblaettern laesst das Fenster stehen (Widgets bleiben sichtbar).
* Speichern sieht alle Widgets weiter; Andocken stellt den Stand exakt her.
* Fenster schliessen = andocken; Bearbeiten dockt vorlaeufig an.
* Jede Bank merkt ihre eigene Lage (``vc_bank_lagen``), getrennt vom Popout.
* Laden einer (Alt-)Show bei geloester Bank; die Show traegt nichts davon.
* MIDI bleibt an die oben gewaehlte Seite gebunden.
* Finger: Andocken-Knopf >= 44 px und per Tipp bedienbar.
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QPoint                                    # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication                           # noqa: E402

import src.ui.views.programmer_view as PV                            # noqa: E402
import src.ui.virtualconsole.popout_lage as PL                       # noqa: E402
from src.ui import touch_keyboard                                    # noqa: E402
from src.ui.virtualconsole.popout_lage import Bildschirm, Rechteck   # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ANLEITUNG = os.path.join(_ROOT, "docs", "anleitung_vc", "ANLEITUNG_VC.md")

OBEN = Bildschirm("HDMI-1", Rechteck(0, 0, 1920, 1080), Rechteck(0, 0, 1920, 1040))
UNTEN = Bildschirm("DP-2", Rechteck(0, 1080, 1920, 1080), Rechteck(0, 1080, 1920, 1080))


@pytest.fixture(autouse=True)
def _aufraeumen():
    alt_touch = touch_keyboard.is_touch_mode()
    yield
    touch_keyboard.setze_touch_modus(alt_touch)
    try:                                   # Seite der Wiedergabe zuruecksetzen
        from src.core.app_state import get_state
        pe = getattr(get_state(), "playback_engine", None)
        if pe is not None:
            pe.set_page(0)
    except Exception:
        pass
    destroy_all_top_level_widgets(QApplication.instance())


@pytest.fixture
def prefs(tmp_path, monkeypatch):
    pfad = tmp_path / "ui_prefs.json"
    monkeypatch.setattr(PV, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(PV, "_PREFS_PATH", str(pfad))

    def lesen():
        return json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else {}
    return lesen


@pytest.fixture
def zwei_bildschirme(monkeypatch):
    monkeypatch.setattr(PL, "lies_bildschirme",
                        lambda: [(b, None) for b in (OBEN, UNTEN)])
    monkeypatch.setattr(PL, "haupt_index", lambda paare, widget: 0)


def _konsole():
    """Bank 0: Taste A; Bank 1: Taste B + Fader + Kasten mit Taste;
    alle Baenke: Etikett."""
    from src.ui.views.virtual_console_view import VirtualConsoleView
    v = VirtualConsoleView()
    cv = v._canvas
    v._btn_edit.setChecked(True)
    v._set_bank(0)
    a = cv._add_widget("VCButton", QPoint(20, 20))
    a.caption, a.bank = "A", 0
    v._set_bank(1)
    b = cv._add_widget("VCButton", QPoint(140, 20))
    b.caption, b.bank = "B", 1
    s = cv._add_widget("VCSlider", QPoint(260, 20))
    s.bank = 1
    f = cv._add_widget("VCFrame", QPoint(400, 20))
    f.bank = 1
    k = f._add_child_widget("VCButton") if hasattr(f, "_add_child_widget") else None
    lab = cv._add_widget("VCLabel", QPoint(20, 300))
    lab.bank = -1
    v._btn_edit.setChecked(False)
    v._set_bank(1)
    assert cv.active_bank == 1
    v.show()
    _app.processEvents()
    return v, {"A": a, "B": b, "S": s, "F": f, "K": k, "L": lab}


def _dump(v) -> str:
    return json.dumps(v.to_dict(), sort_keys=True)


def _menge(v) -> list:
    return sorted(json.dumps(w, sort_keys=True) for w in v.to_dict()["widgets"])


def test_loesen_zieht_genau_die_bank_ins_fenster(prefs, zwei_bildschirme):
    v, w = _konsole()
    cv = v._canvas
    vorher = _menge(v)
    pos_b = w["B"].pos()
    fenster = cv.bank_loesen(1, haupt=v)
    _app.processEvents()
    assert fenster is not None and fenster.isVisible() and fenster.isWindow()
    assert cv.geloeste_baenke() == [1]
    drin = fenster.widgets()
    assert w["B"] in drin and w["S"] in drin and w["F"] in drin
    assert w["A"].parent() is cv and w["L"].parent() is cv
    # Speichern sieht dieselben Widgets (nur die Reihenfolge darf abweichen).
    assert _menge(v) == vorher
    # Koordinaten bleiben gleich (beim Andocken liegen sie wieder da).
    assert w["B"].pos() == pos_b


def test_oben_weiterblaettern_laesst_das_fenster_stehen(prefs, zwei_bildschirme):
    v, w = _konsole()
    cv = v._canvas
    fenster = cv.bank_loesen(1, haupt=v)
    for bank in (0, 2, 5, 1, 0):
        v._set_bank(bank)
        _app.processEvents()
        assert cv.active_bank == bank
        assert w["B"].isVisible() and w["S"].isVisible() and w["F"].isVisible()
        assert fenster.isVisible()
    # Oben gilt die Bank-Regel wie bisher.
    v._set_bank(0)
    assert w["A"].isVisible() and w["L"].isVisible()
    v._set_bank(3)
    assert not w["A"].isVisible() and w["L"].isVisible()
    # Das Kind im Kasten haengt an der Bank des Kastens -> sichtbar.
    if w["K"] is not None:
        assert w["K"].isVisible()


def test_midi_bleibt_an_der_oben_gewaehlten_seite(prefs, zwei_bildschirme):
    """Das Pult bedient die Seite, die oben gewaehlt ist — auch wenn die
    Widgets dieser Seite gerade im eigenen Fenster liegen."""
    v, w = _konsole()
    cv = v._canvas
    cv.bank_loesen(1, haupt=v)
    v._set_bank(0)
    assert cv.on_active_bank(w["A"]) and not cv.on_active_bank(w["B"])
    v._set_bank(1)
    assert cv.on_active_bank(w["B"]) and not cv.on_active_bank(w["A"])


def test_apc_folgt_der_seitentaste_auch_fuer_die_geloeste_bank(
        prefs, zwei_bildschirme):
    """Schritt 4: Seitentaste (= Executor-Seite) waehlt, welche Bank das
    Pult bedient — auch die gerade geloeste. Gespielt wird ueber den echten
    MIDI-Weg der Flaeche."""
    from types import SimpleNamespace
    v, w = _konsole()
    cv = v._canvas
    cv.bank_loesen(1, haupt=v)
    rufe = {"A": 0, "B": 0}
    for name in ("A", "B"):
        w[name].handle_midi = (lambda n: lambda msg: rufe.__setitem__(n, rufe[n] + 1)
                               or True)(name)
    note = SimpleNamespace(msg_type="note_on", channel=0, data1=60, data2=127)
    v._set_bank(1)                       # Seitentaste 2
    cv._handle_midi(note)
    assert rufe == {"A": 0, "B": 1}
    v._set_bank(0)                       # Seitentaste 1
    cv._handle_midi(note)
    assert rufe == {"A": 1, "B": 1}


def test_andocken_stellt_den_stand_exakt_her(prefs, zwei_bildschirme):
    v, w = _konsole()
    cv = v._canvas
    vorher = _dump(v)
    from src.ui.virtualconsole.vc_widget import VCWidget
    reihe = [x for x in cv.findChildren(VCWidget) if x.parent() is cv]
    cv.bank_loesen(1, haupt=v)
    v._set_bank(4)
    assert cv.bank_andocken(1) is True
    _app.processEvents()
    assert cv.geloeste_baenke() == []
    assert w["B"].parent() is cv and w["F"].parent() is cv
    assert [x for x in cv.findChildren(VCWidget)
            if x.parent() is cv] == reihe          # Stapel-Reihenfolge
    assert _dump(v) == vorher
    v._set_bank(1)
    assert w["B"].isVisible()
    v._set_bank(0)
    assert not w["B"].isVisible()


def test_fenster_schliessen_dockt_an(prefs, zwei_bildschirme):
    v, w = _konsole()
    cv = v._canvas
    vorher = _dump(v)
    fenster = cv.bank_loesen(1, haupt=v)
    fenster.close()
    _app.processEvents()
    assert cv.geloeste_baenke() == []
    assert w["B"].parent() is cv
    assert _dump(v) == vorher


def _menue_aktion(v):
    v._bank_menue()
    menue = v._bank_menue_offen
    akt = v._bank_loesen_aktion
    menue.close()
    return akt


def test_bank_menue_loest_und_dockt_an(prefs, zwei_bildschirme):
    """Loesen/Andocken liegt im Bank-Menue (Etikett antippen) — die
    Spielbetrieb-Leiste bekommt keinen weiteren Knopf (UI-138)."""
    v, w = _konsole()
    cv = v._canvas
    v._set_bank(1)
    akt = _menue_aktion(v)
    assert akt.text() == "⇲ Bank 2 lösen (eigenes Fenster)" and akt.isEnabled()
    akt.trigger()
    _app.processEvents()
    assert cv.geloeste_baenke() == [1]
    assert "gelöst" in v._lbl_bank.toolTip()
    assert _menue_aktion(v).text() == "⇱ Bank 2 andocken"
    v._set_bank(2)
    assert _menue_aktion(v).text() == "⇲ Bank 3 lösen (eigenes Fenster)"
    assert "gelöst" not in v._lbl_bank.toolTip()
    v._set_bank(1)
    _menue_aktion(v).trigger()
    assert cv.geloeste_baenke() == []
    # Schliessen des Fensters frischt die Anzeige ebenfalls auf.
    _menue_aktion(v).trigger()
    assert "gelöst" in v._lbl_bank.toolTip()
    cv.bank_fenster(1).close()
    _app.processEvents()
    assert "gelöst" not in v._lbl_bank.toolTip()


def test_bearbeiten_dockt_vorlaeufig_an_und_loest_danach_wieder(
        prefs, zwei_bildschirme):
    v, w = _konsole()
    cv = v._canvas
    cv.bank_loesen(1, haupt=v)
    v._btn_edit.setChecked(True)
    _app.processEvents()
    assert cv.geloeste_baenke() == []
    assert w["B"].parent() is cv
    assert not _menue_aktion(v).isEnabled()
    assert cv.bank_loesen(2) is None           # beim Bearbeiten nicht
    v._btn_edit.setChecked(False)
    _app.processEvents()
    assert cv.geloeste_baenke() == [1]
    assert w["B"] in cv.bank_fenster(1).widgets()
    assert _menue_aktion(v).isEnabled()


def test_jede_bank_merkt_ihre_eigene_lage(prefs, zwei_bildschirme):
    v, w = _konsole()
    cv = v._canvas
    f1 = cv.bank_loesen(1, haupt=v)
    _app.processEvents()
    # Ohne Gemerktes: maximiert auf dem anderen (unteren) Bildschirm.
    assert f1.isMaximized()
    assert f1.normalGeometry().y() >= 1080
    f1.showNormal()
    _app.processEvents()
    f1.move(100, 1200)
    f1.resize(800, 500)
    _app.processEvents()
    cv.bank_andocken(1)
    f0 = cv.bank_loesen(0, haupt=v)
    f0.showNormal()
    _app.processEvents()
    f0.move(900, 1300)
    f0.resize(700, 400)
    _app.processEvents()
    f0.close()
    _app.processEvents()
    lagen = prefs()[PL.BANK_PREF_SCHLUESSEL]
    assert lagen["1"]["fenster"] == [100, 1200, 800, 500]
    assert lagen["0"]["fenster"] == [900, 1300, 700, 400]
    assert PL.PREF_SCHLUESSEL not in prefs()     # das Popout bleibt unberuehrt

    f1 = cv.bank_loesen(1, haupt=v)
    _app.processEvents()
    assert not f1.isMaximized()
    assert (f1.x(), f1.y(), f1.width(), f1.height()) == (100, 1200, 800, 500)


def test_popout_lage_unveraendert_neben_geloester_bank(prefs, zwei_bildschirme):
    """Schritt 1 bleibt: das Popout merkt weiter unter ``vc_popout_lage``,
    und Popout auf/zu bei geloester Bank aendert den Inhalt nicht."""
    v, w = _konsole()
    cv = v._canvas
    vorher = _menge(v)
    fenster = cv.bank_loesen(1, haupt=v)
    v._popout_canvas()
    _app.processEvents()
    assert v._pop_scroll.widget() is cv
    assert fenster.isVisible() and w["B"] in fenster.widgets()
    v._popout_window.close()
    _app.processEvents()
    assert v._main_scroll.widget() is cv
    assert PL.PREF_SCHLUESSEL in prefs()
    assert _menge(v) == vorher
    assert cv.bank_andocken(1)


def test_show_laden_bei_geloester_bank_und_alt_show(prefs, zwei_bildschirme):
    v, w = _konsole()
    cv = v._canvas
    gespeichert = v.to_dict()
    cv.bank_loesen(1, haupt=v)
    # Die Show traegt nichts vom Loesen (Arbeitsplatz-Einstellung).
    assert "geloest" not in json.dumps(v.to_dict())
    assert set(v.to_dict()) == set(gespeichert)
    # Alt-Show (ohne jede neue Angabe), im Test erzeugt: Bank-1-Taste.
    alt = {"widgets": [
        {"type": "VCButton", "x": 30, "y": 40, "w": 72, "h": 72,
         "caption": "Alt1", "bank": 1},
        {"type": "VCButton", "x": 130, "y": 40, "w": 72, "h": 72,
         "caption": "Alt0", "bank": 0},
    ]}
    v.from_dict(alt)
    _app.processEvents()
    drin = cv.bank_fenster(1).widgets()
    assert [x.caption for x in drin] == ["Alt1"]
    assert sorted(d["caption"] for d in v.to_dict()["widgets"]) == ["Alt0", "Alt1"]
    # Undo-Weg (from_dict mit _restoring) verdoppelt nichts.
    cv._restoring = True
    try:
        v.from_dict(v.to_dict())
    finally:
        cv._restoring = False
    assert len(v.to_dict()["widgets"]) == 2
    assert len(cv.bank_fenster(1).widgets()) == 1


def test_andocken_knopf_am_finger(prefs, zwei_bildschirme):
    touch_keyboard.setze_touch_modus(True)
    v, w = _konsole()
    cv = v._canvas
    fenster = cv.bank_loesen(1, haupt=v)
    _app.processEvents()
    k = fenster.knopf_andocken
    assert k.height() >= 44 and k.width() >= 44
    mitte = k.rect().center()
    QTest.touchEvent(k, _DEV).press(0, mitte, k).commit()
    _app.processEvents()
    QTest.touchEvent(k, _DEV).release(0, mitte, k).commit()
    _app.processEvents()
    assert cv.geloeste_baenke() == []
    assert w["B"].parent() is cv


def test_anleitung_nennt_bank_loesen():
    text = open(_ANLEITUNG, encoding="utf-8").read()
    assert "lösen (eigenes Fenster)" in text
    assert "andocken" in text.lower()
