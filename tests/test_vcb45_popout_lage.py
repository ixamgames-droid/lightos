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


def test_unendlich_in_der_datei_zaehlt_als_nichts_gemerkt():
    # json liest ``Infinity`` als float('inf'); das darf die Rechnung nicht
    # werfen lassen — sonst bliebe das Merken bis zum Loeschen der Datei tot.
    muell = {"fenster": [0, 1080, float("inf"), 5], "bildschirm": "DP-2"}
    assert PL.ziel_lage([OBEN], muell, 0).rechteck is None
    assert PL.ziel_lage([OBEN, UNTEN], muell, 0).zustand == PL.MAXIMIERT


def test_bildschirm_ohne_flaeche_gibt_nichts_vor():
    # Platzhalter-Bildschirm des Systems: kein Fenster mit 0x0 vorgeben.
    leer = Bildschirm("", Rechteck(0, 0, 0, 0))
    g = _gemerkt(UNTEN, (200, 1180, 1400, 700))
    assert PL.ziel_lage([leer], g, 0).rechteck is None
    assert PL.ziel_lage([OBEN, leer], None, 0).rechteck is None


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


def test_maximiert_ohne_normal_lage_merkt_nicht_das_maximierte_rechteck(
        prefs, zwei_bildschirme, monkeypatch):
    """Codex-Review #1083 (CDX-59): erster Start auf einem Bildschirm (keine
    Vorgabe, also keine Normal-Lage) und gleich maximiert. Gemerkt wurde das
    MAXIMIERTE Rechteck als Normal-Lage — „Wiederherstellen“ blieb dann
    bildschirmfuellend. Jetzt: Normal-Lage von Qt, sonst Standardgroesse mittig."""
    zwei_bildschirme(OBEN)
    w, merker = _fenster(PL.ziel_lage([OBEN], None, 0))
    assert merker._normal is None, "Vorbedingung: keine Normal-Lage bekannt"
    maximiert = (0, 0, 1920, 1040, PL.MAXIMIERT)
    monkeypatch.setattr(merker, "_ist", lambda: maximiert)
    # (a) Qt kennt keine brauchbare Normal-Lage -> Standardgroesse mittig.
    monkeypatch.setattr(merker, "_normal_lage_von_qt", lambda ist: None)
    merker.sichern()
    g = prefs()[PL.PREF_SCHLUESSEL]
    assert g["zustand"] == "maximized"
    assert g["fenster"] == [320, 120, 1280, 800]
    # (b) Qt kennt sie -> die gilt.
    monkeypatch.setattr(merker, "_normal_lage_von_qt",
                        lambda ist: Rechteck(100, 80, 900, 600))
    merker.sichern()
    assert prefs()[PL.PREF_SCHLUESSEL]["fenster"] == [100, 80, 900, 600]


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


def test_schliessen_mit_laufendem_zeitgeber_stuerzt_nicht_ab(prefs, zwei_bildschirme):
    """Verschieben und sofort schliessen: der entprellte Zeitgeber und der
    500-ms-Zeitgeber der Ersatz-Lage duerfen nach dem Abbau nicht mehr feuern."""
    from PySide6.QtTest import QTest
    PL.speichere_gemerkt(_gemerkt(UNTEN, (150, 1200, 1000, 640)))
    zwei_bildschirme(OBEN)                   # Ersatz-Lage -> 500-ms-Zeitgeber
    v = _konsole()
    for runde in range(3):
        v._popout_canvas()
        win = v._popout_window
        merker = win._lage_merker
        win.move(60 + runde, 80)
        assert merker._timer.isActive()
        win.close()
        del win
        QTest.qWait(650)                     # laenger als beide Zeitgeber
        assert v._popout_window is None and v._canvas_alive()
        with pytest.raises(RuntimeError):    # mit dem Fenster abgebaut
            merker._timer.isActive()
    # Unangefasste Ersatz-Lage hat den Platz auf dem Touch-Bildschirm behalten.
    assert prefs()[PL.PREF_SCHLUESSEL]["bildschirm"] == "DP-2"


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


# ── Bildschirm faellt weg und kommt wieder (Popout bleibt offen) ────────────
#
# Die Bildschirm-Ereignisse werden nachgestellt: ``zwei_bildschirme(...)``
# aendert die Liste, die der Kleber sieht, ``bildschirm_weg`` / ``bildschirm_dazu``
# stehen fuer ``screenRemoved`` / ``screenAdded``. Die Zeitgeber werden von Hand
# ausgeloest — kein Test wartet auf die Uhr.

PLATZ = (150, 1200, 1000, 640)
FREMD = Bildschirm("HDMI-3", Rechteck(1920, 0, 1280, 720))


def _geometrie(w):
    return (w.x(), w.y(), w.width(), w.height())


def _normal_lage_passt(w):
    """Die Lage, auf die ein maximiertes/Vollbild-Fenster zurueckgeht. Die
    Testplattform rechnet dabei ein paar Pixel Rahmen ein."""
    n = w.normalGeometry()
    return (abs(n.x() - PLATZ[0]) <= 4 and abs(n.y() - PLATZ[1]) <= 4
            and (n.width(), n.height()) == PLATZ[2:])


def _ruhe_vorbei(merker):
    """Die Beruhigungszeit ablaufen lassen (auch die zweite nach einem
    Sichtbar-Holen)."""
    for _ in range(3):
        if not merker._ruhe.isActive():
            break
        merker._ruhe.stop()
        merker._ruhe.timeout.emit()


def _offen_auf_touch(prefs, zustand=PL.NORMAL):
    g = _gemerkt(UNTEN, PLATZ, zustand)
    PL.speichere_gemerkt(g)
    w, merker = _fenster(PL.ziel_lage([OBEN, UNTEN], PL.lade_gemerkt(), 0))
    if zustand == PL.NORMAL:
        _ruhe_vorbei(merker)
    else:
        # Die Testplattform maximiert auf ihrem einzigen echten Bildschirm
        # bei (0, 0); das Merken kurz nach dem Oeffnen saehe das Fenster
        # deshalb oben statt auf dem nachgestellten Touch.
        merker._ruhe.stop()
        merker._erst = False
    assert prefs()[PL.PREF_SCHLUESSEL] == g
    return w, merker, g


def _touch_faellt_weg(zwei_bildschirme, w, merker, system_schiebt=(60, 80)):
    zwei_bildschirme(OBEN)
    merker.bildschirm_weg(UNTEN)
    if system_schiebt is not None:           # das System raeumt das Fenster um
        w.showNormal()
        w.move(*system_schiebt)
        _app.processEvents()
        merker.angestossen()
        merker._timer.timeout.emit()
    _ruhe_vorbei(merker)


def _touch_kommt_wieder(zwei_bildschirme, merker, meldungen=1):
    zwei_bildschirme(OBEN, UNTEN)
    for _ in range(meldungen):
        merker.bildschirm_dazu(UNTEN)
    if merker._rueck.isActive():
        merker._rueck.stop()
        merker._rueck.timeout.emit()
    _app.processEvents()


@pytest.fixture
def spruenge(monkeypatch):
    """Zaehlt, wie oft das Fenster versetzt wird."""
    gezaehlt = []
    echt = PL.versetze
    monkeypatch.setattr(PL, "versetze",
                        lambda f, lage, qs=None: (gezaehlt.append(lage),
                                                  echt(f, lage, qs)))
    return gezaehlt


def test_rueckkehr_lage_nur_wenn_der_gemerkte_bildschirm_da_ist():
    g = _gemerkt(UNTEN, PLATZ, PL.MAXIMIERT)
    assert PL.rueckkehr_lage([OBEN], g, 0) is None
    assert PL.rueckkehr_lage([OBEN, FREMD], g, 0) is None
    assert PL.rueckkehr_lage([OBEN, UNTEN], None, 0) is None
    lage = PL.rueckkehr_lage([OBEN, FREMD, UNTEN], g, 0)
    assert (lage.rechteck, lage.zustand, lage.bildschirm) == (
        Rechteck(*PLATZ), PL.MAXIMIERT, 2)
    # Unter anderem Namen wiedergekommen (Windows/Wayland): Geometrie zaehlt.
    anders = Bildschirm("DISPLAY7", UNTEN.flaeche)
    assert PL.rueckkehr_lage([OBEN, anders], g, 0).bildschirm == 1


def test_ueberwiegend_sichtbar():
    assert PL.ueberwiegend_sichtbar([OBEN], Rechteck(100, 100, 800, 600))
    assert not PL.ueberwiegend_sichtbar([OBEN], Rechteck(*PLATZ))
    assert PL.ueberwiegend_sichtbar([OBEN, UNTEN], Rechteck(100, 800, 800, 560))


def test_wegfall_behaelt_den_gemerkten_platz(prefs, zwei_bildschirme):
    w, merker, g = _offen_auf_touch(prefs)
    _touch_faellt_weg(zwei_bildschirme, w, merker)
    assert merker.im_ersatz()
    assert _geometrie(w)[:2] == (60, 80)     # wo das System es hingelegt hat
    merker.sichern()                         # auch beim Schliessen
    assert prefs()[PL.PREF_SCHLUESSEL] == g


def test_wegfall_holt_ein_liegengebliebenes_fenster_sichtbar_zum_hauptfenster(
        prefs, zwei_bildschirme, spruenge):
    w, merker, g = _offen_auf_touch(prefs)
    _touch_faellt_weg(zwei_bildschirme, w, merker, system_schiebt=None)
    x, y, b, h = _geometrie(w)
    assert PL.ueberwiegend_sichtbar([OBEN], Rechteck(x, y, b, h))
    assert (b, h) == PLATZ[2:]
    assert len(spruenge) == 1
    assert merker.im_ersatz() and merker._ausgang is not None
    merker.sichern()
    assert prefs()[PL.PREF_SCHLUESSEL] == g  # das eigene Holen zaehlt nicht


def test_wegfall_ohne_signal_merkt_den_ersatzplatz_nicht(prefs, zwei_bildschirme):
    """Der Fenstermanager verschiebt, bevor Qt den Wegfall meldet."""
    w, merker, g = _offen_auf_touch(prefs)
    zwei_bildschirme(OBEN)
    w.move(60, 80)
    _app.processEvents()
    merker.angestossen()
    merker._timer.timeout.emit()
    assert merker.im_ersatz()
    assert prefs()[PL.PREF_SCHLUESSEL] == g
    merker.bildschirm_weg(UNTEN)             # das Signal kommt nach
    _ruhe_vorbei(merker)
    merker.sichern()
    assert prefs()[PL.PREF_SCHLUESSEL] == g


@pytest.mark.parametrize("zustand", [PL.NORMAL, PL.MAXIMIERT, PL.VOLLBILD])
def test_rueckkehr_springt_an_den_gemerkten_platz(prefs, zwei_bildschirme,
                                                  spruenge, zustand):
    w, merker, g = _offen_auf_touch(prefs, zustand)
    _touch_faellt_weg(zwei_bildschirme, w, merker)
    assert spruenge == []
    _touch_kommt_wieder(zwei_bildschirme, merker, meldungen=3)

    assert len(spruenge) == 1                # drei Meldungen, ein Sprung
    assert PL._zustand_von(w) == zustand
    merker.sichern()                         # waehrend des Sprungs: nichts
    assert prefs()[PL.PREF_SCHLUESSEL] == g
    if zustand != PL.NORMAL:
        # Ob das Fenster angekommen ist, laesst sich hier nur im
        # Normalzustand pruefen (siehe ``_offen_auf_touch``).
        assert _normal_lage_passt(w)
        return
    assert _geometrie(w) == PLATZ
    _ruhe_vorbei(merker)
    assert not merker.im_ersatz()
    merker.sichern()
    assert prefs()[PL.PREF_SCHLUESSEL] == g
    # Weitere Meldungen loesen nichts mehr aus.
    merker.bildschirm_dazu(UNTEN)
    assert not merker._rueck.isActive() and len(spruenge) == 1


def test_nach_der_rueckkehr_wird_wieder_normal_gemerkt(prefs, zwei_bildschirme):
    w, merker, g = _offen_auf_touch(prefs)
    _touch_faellt_weg(zwei_bildschirme, w, merker)
    _touch_kommt_wieder(zwei_bildschirme, merker)
    _ruhe_vorbei(merker)
    w.move(200, 1300)
    _app.processEvents()
    merker.sichern()
    assert prefs()[PL.PREF_SCHLUESSEL]["fenster"] == [200, 1300, 1000, 640]
    assert prefs()[PL.PREF_SCHLUESSEL]["bildschirm"] == "DP-2"


def test_bediener_verschiebt_am_ersatzplatz_gilt_als_neue_wahl(
        prefs, zwei_bildschirme, spruenge):
    w, merker, g = _offen_auf_touch(prefs)
    _touch_faellt_weg(zwei_bildschirme, w, merker)
    w.move(300, 200)                         # der Bediener
    _app.processEvents()
    merker.angestossen()
    merker._timer.timeout.emit()
    neu = prefs()[PL.PREF_SCHLUESSEL]
    assert neu["bildschirm"] == "HDMI-1" and neu["fenster"][:2] == [300, 200]
    assert not merker.im_ersatz()

    _touch_kommt_wieder(zwei_bildschirme, merker, meldungen=2)
    assert spruenge == []
    assert _geometrie(w)[:2] == (300, 200)
    assert prefs()[PL.PREF_SCHLUESSEL] == neu


def test_bediener_aendert_die_groesse_am_ersatzplatz_gilt_als_neue_wahl(
        prefs, zwei_bildschirme, spruenge):
    w, merker, g = _offen_auf_touch(prefs)
    _touch_faellt_weg(zwei_bildschirme, w, merker)
    w.resize(700, 500)
    _app.processEvents()
    # Der Bildschirm kommt wieder, bevor das entprellte Schreiben dran war.
    _touch_kommt_wieder(zwei_bildschirme, merker)
    assert spruenge == []
    assert prefs()[PL.PREF_SCHLUESSEL]["fenster"] == [60, 80, 700, 500]
    assert prefs()[PL.PREF_SCHLUESSEL]["bildschirm"] == "HDMI-1"


def test_fremder_neuer_bildschirm_loest_nichts_aus(prefs, zwei_bildschirme, spruenge):
    w, merker, g = _offen_auf_touch(prefs)
    _touch_faellt_weg(zwei_bildschirme, w, merker)
    zwei_bildschirme(OBEN, FREMD)
    merker.bildschirm_dazu(FREMD)
    merker._rueck.stop()
    merker._rueck.timeout.emit()
    _ruhe_vorbei(merker)
    assert spruenge == []
    assert _geometrie(w)[:2] == (60, 80)
    assert merker.im_ersatz()
    merker.sichern()
    assert prefs()[PL.PREF_SCHLUESSEL] == g
    # Der richtige kommt spaeter doch noch.
    zwei_bildschirme(OBEN, FREMD, UNTEN)
    merker.bildschirm_dazu(UNTEN)
    merker._rueck.stop()
    merker._rueck.timeout.emit()
    assert len(spruenge) == 1 and _geometrie(w) == PLATZ


def test_fremder_bildschirm_faellt_weg_aendert_nichts(prefs, zwei_bildschirme):
    zwei_bildschirme(OBEN, UNTEN, FREMD)
    w, merker, g = _offen_auf_touch(prefs)
    zwei_bildschirme(OBEN, UNTEN)
    merker.bildschirm_weg(FREMD)
    assert not merker.im_ersatz()
    w.move(200, 1300)
    _app.processEvents()
    merker.sichern()
    assert prefs()[PL.PREF_SCHLUESSEL]["fenster"][:2] == [200, 1300]


def test_sprung_der_nicht_ankommt_bleibt_im_ersatz_ohne_schleife(
        prefs, zwei_bildschirme, monkeypatch):
    """Das System versetzt das Fenster nicht (etwa Wayland): kein zweiter
    Versuch, der gemerkte Platz bleibt."""
    w, merker, g = _offen_auf_touch(prefs)
    _touch_faellt_weg(zwei_bildschirme, w, merker)
    versuche = []
    monkeypatch.setattr(PL, "versetze", lambda *a, **k: versuche.append(a))
    _touch_kommt_wieder(zwei_bildschirme, merker)
    _ruhe_vorbei(merker)
    assert len(versuche) == 1
    assert merker.im_ersatz() and not merker._rueck.isActive()
    merker.sichern()
    assert prefs()[PL.PREF_SCHLUESSEL] == g


def test_geschlossenes_popout_reagiert_nicht_und_oeffnet_am_gemerkten_platz(
        prefs, zwei_bildschirme, spruenge):
    w, merker, g = _offen_auf_touch(prefs)
    _touch_faellt_weg(zwei_bildschirme, w, merker)
    merker.sichern()                         # wie closeEvent
    w.hide()
    _touch_kommt_wieder(zwei_bildschirme, merker)
    assert spruenge == [] and not merker._rueck.isActive()
    assert prefs()[PL.PREF_SCHLUESSEL] == g

    # Bildschirm fehlt noch: Ersatzplatz, Gemerktes bleibt.
    zwei_bildschirme(OBEN)
    ersatz = PL.ziel_lage([OBEN], PL.lade_gemerkt(), 0)
    assert ersatz.rueckfall and ersatz.bildschirm == 0
    w2, m2 = _fenster(ersatz)
    _ruhe_vorbei(m2)
    m2.sichern()
    w2.hide()
    assert prefs()[PL.PREF_SCHLUESSEL] == g
    # Bildschirm wieder da: am gemerkten Platz.
    lage = PL.ziel_lage([OBEN, UNTEN], PL.lade_gemerkt(), 0)
    assert (lage.rechteck, lage.bildschirm, lage.rueckfall) == (
        Rechteck(*PLATZ), 1, False)


def test_am_ersatzplatz_geoeffnet_springt_zurueck_wenn_der_bildschirm_kommt(
        prefs, zwei_bildschirme):
    g = _gemerkt(UNTEN, PLATZ, PL.MAXIMIERT)
    PL.speichere_gemerkt(g)
    zwei_bildschirme(OBEN)
    w, merker = _fenster(PL.ziel_lage([OBEN], PL.lade_gemerkt(), 0))
    _ruhe_vorbei(merker)
    assert merker.im_ersatz() and not w.isMaximized()
    _touch_kommt_wieder(zwei_bildschirme, merker)
    assert w.isMaximized() and _normal_lage_passt(w)
    merker.sichern()
    assert prefs()[PL.PREF_SCHLUESSEL] == g


def test_nie_angefasstes_popout_hat_trotzdem_einen_gemerkten_platz(
        prefs, zwei_bildschirme):
    """Erstes Oeffnen (maximiert auf dem Touch), nie angefasst: der Platz
    wird kurz nach dem Oeffnen gemerkt. Faellt der Touch danach weg, gibt es
    etwas, wohin das Fenster zurueckspringen kann."""
    w, merker = _fenster(PL.ziel_lage([OBEN, UNTEN], None, 0))
    assert PL.PREF_SCHLUESSEL not in prefs()
    _ruhe_vorbei(merker)
    g = prefs()[PL.PREF_SCHLUESSEL]
    assert g["zustand"] == "maximized"
    assert g["fenster"][1] >= 1080           # unten, auf dem Touch
    merker.sichern()                         # unveraendert -> bleibt so
    assert prefs()[PL.PREF_SCHLUESSEL] == g


def test_popout_der_konsole_haengt_an_den_bildschirm_meldungen(prefs, zwei_bildschirme):
    """Das echte Popout: Wegfall und Rueckkehr ueber die Signale der Anwendung."""
    PL.speichere_gemerkt(_gemerkt(UNTEN, PLATZ))
    v = _konsole()
    v._popout_canvas()
    _app.processEvents()
    win = v._popout_window
    merker = win._lage_merker
    _ruhe_vorbei(merker)
    assert _geometrie(win) == PLATZ

    zwei_bildschirme(OBEN)
    _app.screenRemoved.emit(_app.primaryScreen())
    assert merker.im_ersatz()
    _ruhe_vorbei(merker)
    assert PL.ueberwiegend_sichtbar([OBEN], Rechteck(*_geometrie(win)))

    zwei_bildschirme(OBEN, UNTEN)
    _app.screenAdded.emit(_app.primaryScreen())
    assert merker._rueck.isActive()
    merker._rueck.stop()
    merker._rueck.timeout.emit()
    assert _geometrie(win) == PLATZ
    win.close()
    _app.processEvents()
    assert prefs()[PL.PREF_SCHLUESSEL]["fenster"] == list(PLATZ)
    assert v._canvas_alive()


# ── Gegenpruefung: Wackelkontakt, gespiegelte Bildschirme, vorlaeufige Lage ──

def test_bildschirm_wackelt_waehrend_des_ruecksprungs_springt_am_ende_doch(
        prefs, zwei_bildschirme, spruenge):
    """Der Touch meldet sich beim Einschalten an, kurz ab und wieder an. Der
    zweite Wegfall trifft den laufenden Ruecksprung — das Popout darf danach
    nicht am Ersatzplatz haengen bleiben."""
    w, merker, g = _offen_auf_touch(prefs)
    _touch_faellt_weg(zwei_bildschirme, w, merker)
    _touch_kommt_wieder(zwei_bildschirme, merker)
    assert len(spruenge) == 1 and _geometrie(w) == PLATZ
    # Noch in der Beruhigungszeit des Sprungs: wieder weg, System raeumt um.
    zwei_bildschirme(OBEN)
    merker.bildschirm_weg(UNTEN)
    w.move(60, 80)
    _app.processEvents()
    assert merker.im_ersatz()
    # ... und gleich wieder da, bevor die Beruhigungszeit abgelaufen ist.
    _touch_kommt_wieder(zwei_bildschirme, merker)
    assert len(spruenge) == 2 and _geometrie(w) == PLATZ
    _ruhe_vorbei(merker)
    assert not merker.im_ersatz()
    merker.sichern()
    assert prefs()[PL.PREF_SCHLUESSEL] == g


def test_wegfall_waehrend_des_ruecksprungs_holt_das_fenster_sichtbar(
        prefs, zwei_bildschirme):
    """Faellt der Touch mitten im Ruecksprung wieder weg und laesst das System
    das Fenster liegen, wird es wie beim ersten Wegfall sichtbar geholt."""
    w, merker, g = _offen_auf_touch(prefs)
    _touch_faellt_weg(zwei_bildschirme, w, merker)
    _touch_kommt_wieder(zwei_bildschirme, merker)
    assert _geometrie(w) == PLATZ
    zwei_bildschirme(OBEN)
    merker.bildschirm_weg(UNTEN)
    _ruhe_vorbei(merker)
    assert merker.im_ersatz()
    assert PL.ueberwiegend_sichtbar([OBEN], Rechteck(*_geometrie(w)))
    merker.sichern()
    assert prefs()[PL.PREF_SCHLUESSEL] == g


def test_fremder_bildschirm_faellt_im_ruecksprung_weg_sprung_gilt_trotzdem(
        prefs, zwei_bildschirme, spruenge):
    zwei_bildschirme(OBEN, UNTEN, FREMD)
    w, merker, g = _offen_auf_touch(prefs)
    zwei_bildschirme(OBEN, FREMD)
    merker.bildschirm_weg(UNTEN)
    w.move(60, 80)
    _app.processEvents()
    _ruhe_vorbei(merker)
    zwei_bildschirme(OBEN, UNTEN, FREMD)
    merker.bildschirm_dazu(UNTEN)
    merker._rueck.stop()
    merker._rueck.timeout.emit()
    zwei_bildschirme(OBEN, UNTEN)
    merker.bildschirm_weg(FREMD)             # hat mit dem Popout nichts zu tun
    _ruhe_vorbei(merker)
    assert not merker.im_ersatz()
    assert len(spruenge) == 1 and _geometrie(w) == PLATZ


def test_gespiegelter_bildschirm_faellt_weg_der_gemerkte_ist_noch_da(
        prefs, zwei_bildschirme):
    """Zwei Bildschirme zeigen dasselbe Bild (gleiche Flaeche, anderer
    Anschluss). Faellt der andere weg, ist der gemerkte nicht weg."""
    spiegel = Bildschirm("HDMI-3", UNTEN.flaeche)
    zwei_bildschirme(OBEN, UNTEN, spiegel)
    w, merker, g = _offen_auf_touch(prefs)
    zwei_bildschirme(OBEN, UNTEN)
    merker.bildschirm_weg(spiegel)
    assert not merker.im_ersatz()
    w.move(200, 1300)
    _app.processEvents()
    merker.sichern()
    assert prefs()[PL.PREF_SCHLUESSEL]["fenster"][:2] == [200, 1300]


def test_system_legt_das_fenster_vor_der_meldung_zurueck(prefs, zwei_bildschirme,
                                                         spruenge):
    """Manche Systeme legen das Fenster selbst zurueck auf den wieder
    angeschlossenen Bildschirm, bevor dieser gemeldet ist. Das Fenster liegt
    dann kurz auf keinem bekannten Bildschirm — das ist keine Wahl des
    Bedieners und darf nicht unter dem Namen des Hauptbildschirms landen."""
    w, merker, g = _offen_auf_touch(prefs)
    _touch_faellt_weg(zwei_bildschirme, w, merker)
    w.move(*PLATZ[:2])                       # das System, Liste noch alt
    _app.processEvents()
    merker.angestossen()
    merker._timer.timeout.emit()
    assert prefs()[PL.PREF_SCHLUESSEL] == g
    assert merker.im_ersatz()
    _touch_kommt_wieder(zwei_bildschirme, merker)
    _ruhe_vorbei(merker)
    assert _geometrie(w) == PLATZ and not merker.im_ersatz()
    assert prefs()[PL.PREF_SCHLUESSEL] == g


def test_bildschirm_kommt_erst_an_vorlaeufiger_stelle_wieder(
        prefs, zwei_bildschirme, spruenge):
    """Der Touch wird erst rechts neben dem Hauptbildschirm gemeldet und
    rueckt dann an seinen Platz darunter. Das Popout folgt mit einem zweiten
    Sprung, statt daneben liegen zu bleiben."""
    w, merker, g = _offen_auf_touch(prefs)
    _touch_faellt_weg(zwei_bildschirme, w, merker)
    vorlaeufig = Bildschirm("DP-2", Rechteck(1920, 0, 1920, 1080))
    zwei_bildschirme(OBEN, vorlaeufig)
    merker.bildschirm_dazu(vorlaeufig)
    merker._rueck.stop()
    merker._rueck.timeout.emit()
    assert _geometrie(w) == (150 + 1920, 120, 1000, 640)
    zwei_bildschirme(OBEN, UNTEN)            # endgueltige Anordnung
    _ruhe_vorbei(merker)
    assert merker._rueck.isActive()
    merker._rueck.stop()
    merker._rueck.timeout.emit()
    assert len(spruenge) == 2 and _geometrie(w) == PLATZ
    _ruhe_vorbei(merker)
    assert not merker.im_ersatz() and not merker._rueck.isActive()
    merker.sichern()
    assert prefs()[PL.PREF_SCHLUESSEL] == g


def test_anleitung_nennt_wegfall_und_rueckkehr_des_bildschirms():
    text = open(_ANLEITUNG, encoding="utf-8").read()
    assert "springt" in text and "wieder angeschlossen" in text
    assert "neue Wahl" in text
