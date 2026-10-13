"""VCB-45 (Schritt 1): das Popout der Virtual Console merkt sich Bildschirm,
Lage, Groesse und Zustand.

Drei Ebenen:

* die Rechnung ``ziel_lage`` ohne jedes Fenster (ein/zwei Bildschirme
  uebereinander, gemerkter Bildschirm fehlt, Fenster ausserhalb, zu gross),
* Merken und Wiederherstellen ueber die Einstellungs-Ablage (umgelenkt),
* das echte Popout: auf/zu aendert den Inhalt der Konsole nicht.
"""
import json
import os

import pytest
from PySide6.QtWidgets import QApplication, QWidget

import src.ui.views.programmer_view as PV
import src.ui.virtualconsole.popout_lage as PL
from src.ui.virtualconsole.popout_lage import Bildschirm, Rechteck
from _qt_lifecycle import destroy_all_top_level_widgets

_app = QApplication.instance() or QApplication([])

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ANLEITUNG = os.path.join(_ROOT, "docs", "anleitung_vc", "ANLEITUNG_VC.md")

# Der Aufbau des Betreibers: oben der Hauptbildschirm, darunter der
# Touch-Bildschirm. Oben belegt eine Leiste 40 px.
OBEN = Bildschirm("HDMI-1", Rechteck(0, 0, 1920, 1080), Rechteck(0, 0, 1920, 1040))
UNTEN = Bildschirm("DP-2", Rechteck(0, 1080, 1920, 1080), Rechteck(0, 1080, 1920, 1080))


def _gemerkt(bildschirm, fenster, zustand=PL.NORMAL):
    return PL.als_gemerkt(bildschirm, Rechteck(*fenster), zustand)


def _sichtbar(lage, bildschirme):
    r = lage.rechteck
    b = bildschirme[lage.bildschirm].nutzbar
    return (b.x <= r.x and b.y <= r.y
            and r.x + r.w <= b.x + b.w and r.y + r.h <= b.y + b.h)


@pytest.fixture(autouse=True)
def _aufraeumen():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


@pytest.fixture
def prefs(tmp_path, monkeypatch):
    """Einstellungs-Ablage in einen Wegwerf-Ordner umlenken."""
    pfad = tmp_path / "ui_prefs.json"
    monkeypatch.setattr(PV, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(PV, "_PREFS_PATH", str(pfad))

    def lesen():
        return json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else {}
    lesen.pfad = pfad
    return lesen


@pytest.fixture
def zwei_bildschirme(monkeypatch):
    """Dem Kleber zwei Bildschirme uebereinander vorspielen (ohne QScreen)."""
    def setze(*bildschirme, haupt=0):
        monkeypatch.setattr(PL, "lies_bildschirme",
                            lambda: [(b, None) for b in bildschirme])
        monkeypatch.setattr(PL, "haupt_index", lambda paare, widget: haupt)
    setze(OBEN, UNTEN)
    return setze


# ── Rechnung ohne Fenster ───────────────────────────────────────────────────

def test_ein_bildschirm_nichts_gemerkt_oeffnet_wie_bisher():
    lage = PL.ziel_lage([OBEN], None, 0)
    assert lage.rechteck is None
    assert lage.zustand == PL.NORMAL
    assert lage.rueckfall is False


def test_zwei_bildschirme_nichts_gemerkt_geht_maximiert_auf_den_anderen():
    lage = PL.ziel_lage([OBEN, UNTEN], None, 0)
    assert lage.bildschirm == 1
    assert lage.zustand == PL.MAXIMIERT
    assert _sichtbar(lage, [OBEN, UNTEN])
    assert lage.rechteck.y >= 1080
    assert (lage.rechteck.w, lage.rechteck.h) == PL.STANDARD_GROESSE

    # Liegt das Hauptfenster unten, ist „der andere" der obere.
    lage = PL.ziel_lage([OBEN, UNTEN], None, 1)
    assert lage.bildschirm == 0 and lage.zustand == PL.MAXIMIERT
    assert _sichtbar(lage, [OBEN, UNTEN])


def test_gemerkte_lage_wird_genau_wiederhergestellt():
    g = _gemerkt(UNTEN, (200, 1180, 1400, 700))
    lage = PL.ziel_lage([OBEN, UNTEN], g, 0)
    assert lage.rechteck == Rechteck(200, 1180, 1400, 700)
    assert (lage.bildschirm, lage.zustand, lage.rueckfall) == (1, PL.NORMAL, False)


@pytest.mark.parametrize("zustand", [PL.MAXIMIERT, PL.VOLLBILD])
def test_gemerkter_zustand_bleibt(zustand):
    g = _gemerkt(UNTEN, (320, 1220, 1280, 800), zustand)
    lage = PL.ziel_lage([OBEN, UNTEN], g, 0)
    assert lage.zustand == zustand
    assert lage.bildschirm == 1
    assert lage.rechteck == Rechteck(320, 1220, 1280, 800)


def test_gemerkter_bildschirm_fehlt_faellt_sichtbar_zum_hauptfenster():
    g = _gemerkt(UNTEN, (200, 1180, 1400, 700), PL.MAXIMIERT)
    lage = PL.ziel_lage([OBEN], g, 0)
    assert lage.bildschirm == 0
    assert lage.rueckfall is True
    assert lage.zustand == PL.NORMAL          # nicht ueber das Hauptfenster legen
    assert _sichtbar(lage, [OBEN])
    assert (lage.rechteck.w, lage.rechteck.h) == (1400, 700)


def test_fenster_ausserhalb_aller_bildschirme_faellt_zum_hauptfenster():
    # Bildschirm ist da, das Fenster laege aber weit daneben.
    g = _gemerkt(UNTEN, (5000, 6000, 1280, 800))
    lage = PL.ziel_lage([OBEN, UNTEN], g, 0)
    assert lage.bildschirm == 0 and lage.rueckfall is True
    assert _sichtbar(lage, [OBEN, UNTEN])


def test_teilweise_herausragendes_fenster_wird_hereingeholt():
    g = _gemerkt(UNTEN, (1500, 1900, 1280, 800))
    lage = PL.ziel_lage([OBEN, UNTEN], g, 0)
    assert lage.bildschirm == 1 and lage.rueckfall is False
    assert _sichtbar(lage, [OBEN, UNTEN])
    assert (lage.rechteck.w, lage.rechteck.h) == (1280, 800)


def test_zu_grosses_fenster_wird_auf_den_freien_bereich_begrenzt():
    g = _gemerkt(OBEN, (-50, -30, 4000, 3000))
    lage = PL.ziel_lage([OBEN, UNTEN], g, 1)
    assert lage.bildschirm == 0
    assert lage.rechteck == Rechteck(0, 0, 1920, 1040)   # ohne die Leiste

    # Rueckfall auf einen kleineren Bildschirm begrenzt ebenfalls.
    klein = Bildschirm("eDP-1", Rechteck(0, 0, 1366, 768), Rechteck(0, 0, 1366, 728))
    lage = PL.ziel_lage([klein], _gemerkt(UNTEN, (0, 1080, 1920, 1080)), 0)
    assert lage.rueckfall is True
    assert lage.rechteck == Rechteck(0, 0, 1366, 728)


def test_bildschirm_umbenannt_wird_ueber_die_geometrie_gefunden():
    g = _gemerkt(UNTEN, (200, 1180, 1400, 700))
    umbenannt = Bildschirm("DP-3", UNTEN.flaeche, UNTEN.frei)
    lage = PL.ziel_lage([OBEN, umbenannt], g, 0)
    assert lage.bildschirm == 1 and lage.rueckfall is False
    assert lage.rechteck == Rechteck(200, 1180, 1400, 700)


def test_bildschirm_umgestellt_fenster_wandert_mit():
    # Touch-Bildschirm steht jetzt rechts statt unten.
    g = _gemerkt(UNTEN, (200, 1180, 1400, 700))
    rechts = Bildschirm("DP-2", Rechteck(1920, 0, 1920, 1080))
    lage = PL.ziel_lage([OBEN, rechts], g, 0)
    assert lage.bildschirm == 1
    assert lage.rechteck == Rechteck(2120, 100, 1400, 700)


def test_gleichnamige_bildschirme_entscheidet_die_geometrie():
    a = Bildschirm("HDMI", Rechteck(0, 0, 1920, 1080))
    b = Bildschirm("HDMI", Rechteck(0, 1080, 1920, 1080))
    g = _gemerkt(b, (100, 1200, 800, 600))
    assert PL.ziel_lage([a, b], g, 0).bildschirm == 1


@pytest.mark.parametrize("muell", [
    "kaputt", 7, [], {}, {"fenster": [1, 2, 3]}, {"fenster": [0, 0, 0, 0]},
    {"fenster": ["a", 0, 10, 10]}, {"fenster": None, "bildschirm": "DP-2"},
])
def test_unbrauchbar_gemerktes_zaehlt_als_nichts_gemerkt(muell):
    assert PL.ziel_lage([OBEN], muell, 0).rechteck is None
    assert PL.ziel_lage([OBEN, UNTEN], muell, 0).zustand == PL.MAXIMIERT


def test_ohne_bildschirmliste_keine_vorgabe():
    assert PL.ziel_lage([], _gemerkt(UNTEN, (0, 0, 10, 10)), 0).rechteck is None


def test_gemerkt_wird_nur_name_und_geometrie():
    g = _gemerkt(UNTEN, (200, 1180, 1400, 700), PL.MAXIMIERT)
    assert g == {"bildschirm": "DP-2",
                 "bildschirm_flaeche": [0, 1080, 1920, 1080],
                 "fenster": [200, 1180, 1400, 700],
                 "zustand": "maximized"}


def test_qt_kleber_liest_keine_geraetekennungen():
    """Seriennummer, Hersteller und Modell des Bildschirms bleiben draussen."""
    quelle = open(PL.__file__, encoding="utf-8").read()
    for verboten in ("serialNumber", "manufacturer(", "model("):
        assert verboten not in quelle


# ── Merken / Wiederherstellen ueber die Ablage ──────────────────────────────

def _fenster(lage):
    w = QWidget()
    w.resize(1280, 800)
    merker = PL.baue_merker(w, lage)
    PL.oeffne(w, lage)
    _app.processEvents()
    return w, merker


def test_merken_und_wiederherstellen_ueber_die_ablage(prefs, zwei_bildschirme):
    lage = PL.ziel_lage([OBEN, UNTEN], PL.lade_gemerkt(), 0)
    w, merker = _fenster(lage)
    w.showNormal()
    _app.processEvents()
    w.move(150, 1200)
    w.resize(1000, 640)
    _app.processEvents()
    merker.sichern()

    g = prefs()[PL.PREF_SCHLUESSEL]
    assert g == {"bildschirm": "DP-2",
                 "bildschirm_flaeche": [0, 1080, 1920, 1080],
                 "fenster": [150, 1200, 1000, 640],
                 "zustand": "normal"}

    neu = PL.ziel_lage([OBEN, UNTEN], PL.lade_gemerkt(), 0)
    assert neu.rechteck == Rechteck(150, 1200, 1000, 640)
    assert (neu.bildschirm, neu.zustand) == (1, PL.NORMAL)


def test_fremde_einstellungen_bleiben_beim_merken_erhalten(prefs, zwei_bildschirme):
    prefs.pfad.write_text(json.dumps({"viz_quality": "hoch"}), encoding="utf-8")
    w, merker = _fenster(PL.ziel_lage([OBEN, UNTEN], None, 0))
    merker.sichern()
    daten = prefs()
    assert daten["viz_quality"] == "hoch"
    assert PL.PREF_SCHLUESSEL in daten


def test_maximiert_merkt_die_lage_vor_dem_maximieren(prefs, zwei_bildschirme):
    g = _gemerkt(UNTEN, (150, 1200, 1000, 640), PL.MAXIMIERT)
    w, merker = _fenster(PL.ziel_lage([OBEN, UNTEN], g, 0))
    assert w.isMaximized()
    merker.sichern()
    g2 = prefs()[PL.PREF_SCHLUESSEL]
    assert g2["zustand"] == "maximized"
    assert g2["fenster"] == [150, 1200, 1000, 640]


def test_bewegen_schreibt_entprellt(prefs, zwei_bildschirme, monkeypatch):
    geschrieben = []
    echt = PL.speichere_gemerkt
    monkeypatch.setattr(PL, "speichere_gemerkt",
                        lambda wert: (geschrieben.append(wert), echt(wert)))
    g = _gemerkt(UNTEN, (150, 1200, 1000, 640))
    w, merker = _fenster(PL.ziel_lage([OBEN, UNTEN], g, 0))
    for dx in range(10):
        w.move(150 + dx * 10, 1200)
        merker.angestossen()
    assert geschrieben == []                 # noch nichts: es wird gewartet
    assert merker._timer.isActive()
    merker._timer.timeout.emit()
    assert len(geschrieben) == 1
    assert geschrieben[0]["fenster"] == [240, 1200, 1000, 640]
    merker.sichern()                         # unveraendert -> kein zweites Mal
    assert len(geschrieben) == 1


def test_rueckfall_ueberschreibt_das_gemerkte_nicht_von_selbst(prefs, zwei_bildschirme):
    """Touch-Bildschirm einmal abgezogen: sein Platz bleibt gemerkt."""
    g = _gemerkt(UNTEN, (150, 1200, 1000, 640), PL.MAXIMIERT)
    PL.speichere_gemerkt(g)
    zwei_bildschirme(OBEN)                   # nur noch der Hauptbildschirm
    lage = PL.ziel_lage([OBEN], PL.lade_gemerkt(), 0)
    assert lage.rueckfall is True
    w, merker = _fenster(lage)
    merker.sichern()                         # schliessen ohne Anfassen
    assert prefs()[PL.PREF_SCHLUESSEL] == g

    # Der Bediener schiebt das Ersatz-Fenster zurecht -> das wird gemerkt.
    merker._scharf_stellen()
    w.move(40, 60)
    _app.processEvents()
    merker.sichern()
    assert prefs()[PL.PREF_SCHLUESSEL]["bildschirm"] == "HDMI-1"
    assert prefs()[PL.PREF_SCHLUESSEL]["fenster"][:2] == [40, 60]


# ── Das echte Popout ────────────────────────────────────────────────────────

def _konsole():
    from src.ui.views.virtual_console_view import VirtualConsoleView
    v = VirtualConsoleView()
    v._btn_edit.setChecked(True)
    v._add_widget("VCButton")
    v._add_widget("VCSlider")
    v._btn_edit.setChecked(False)
    return v


def test_popout_auf_zu_aendert_den_inhalt_der_konsole_nicht(prefs, zwei_bildschirme):
    v = _konsole()
    vorher = json.dumps(v.to_dict(), sort_keys=True)
    canvas = v._canvas
    assert len(v.to_dict()["widgets"]) == 2

    v._popout_canvas()
    _app.processEvents()
    win = v._popout_window
    assert win is not None and win.isVisible()
    assert v._pop_scroll.widget() is canvas
    assert json.dumps(v.to_dict(), sort_keys=True) == vorher

    win.close()                              # zurueckholen
    _app.processEvents()
    assert v._popout_window is None and v._pop_scroll is None
    assert v._main_scroll.widget() is canvas
    assert v._canvas_alive()
    assert json.dumps(v.to_dict(), sort_keys=True) == vorher


def test_popout_oeffnet_ohne_gemerktes_maximiert_auf_dem_anderen_bildschirm(
        prefs, zwei_bildschirme):
    v = _konsole()
    v._popout_canvas()
    _app.processEvents()
    win = v._popout_window
    assert win.isMaximized()
    # Ohne echten zweiten Bildschirm maximiert die Testplattform auf ihrem
    # einzigen; geprueft wird deshalb die Lage, mit der das Fenster vor dem
    # Maximieren auf den unteren Bildschirm gesetzt wurde.
    assert win.normalGeometry().y() >= 1080
    win.close()
    g = prefs()[PL.PREF_SCHLUESSEL]
    assert g["zustand"] == "maximized"
    assert g["fenster"][1] >= 1080           # unten, nicht beim Hauptfenster


def test_popout_oeffnet_wieder_dort_wo_es_geschlossen_wurde(prefs, zwei_bildschirme):
    v = _konsole()
    v._popout_canvas()
    _app.processEvents()
    win = v._popout_window
    win.showNormal()
    _app.processEvents()
    win.move(300, 1250)
    win.resize(900, 600)
    _app.processEvents()
    win.close()
    _app.processEvents()
    assert prefs()[PL.PREF_SCHLUESSEL]["fenster"] == [300, 1250, 900, 600]

    v._popout_canvas()
    _app.processEvents()
    win = v._popout_window
    assert not win.isMaximized()
    assert (win.x(), win.y(), win.width(), win.height()) == (300, 1250, 900, 600)
    win.close()
    assert v._canvas_alive()


def test_popout_bei_einem_bildschirm_wie_bisher(prefs, zwei_bildschirme):
    zwei_bildschirme(OBEN)
    v = _konsole()
    v._popout_canvas()
    _app.processEvents()
    win = v._popout_window
    assert not win.isMaximized() and not win.isFullScreen()
    assert (win.width(), win.height()) == (1280, 800)
    win.close()


def test_popout_oeffnet_auch_wenn_die_lage_rechnung_scheitert(
        prefs, zwei_bildschirme, monkeypatch):
    def kaputt():
        raise RuntimeError("keine Bildschirme")
    monkeypatch.setattr(PL, "lies_bildschirme", kaputt)
    v = _konsole()
    v._popout_canvas()
    _app.processEvents()
    assert v._popout_window.isVisible()
    v._popout_window.close()                 # Merken scheitert still
    assert v._popout_window is None and v._canvas_alive()


def test_echte_bildschirmliste_laesst_sich_lesen():
    paare = PL.lies_bildschirme()
    assert paare, "auch ohne Bildschirm meldet Qt mindestens einen"
    b, qs = paare[0]
    assert b.flaeche.w > 0 and b.flaeche.h > 0
    assert PL.haupt_index(paare, QWidget()) == 0


# ── Doku ────────────────────────────────────────────────────────────────────

def test_anleitung_nennt_das_gemerkte_popout():
    text = open(_ANLEITUNG, encoding="utf-8").read()
    assert "Popout" in text
    assert "merkt sich" in text
