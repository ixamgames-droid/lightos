"""FM-64 (Teil 2): 3D-Vorschau im Fixture-Editor und -Generator.

Geprueft ohne Szene (die misst ``test_fm64_vorschau_scene.py``):

* Payload: Abstrahlwinkel, Zoom-Laufrichtung, Zoomwert, Gobo und Farbe kommen
  so an der Seite an, wie der Visualizer sie im Betrieb bekommt.
* Lazy: das Oeffnen von Editor und Generator baut KEINE WebEngine-Ansicht.
* Abbau: Aufklappen baut eine echte Ansicht, Schliessen des Dialogs baut sie
  wieder ab — ohne Absturz, auch mehrfach.
* Ohne WebGL / ohne QtWebEngine: ein Hinweis statt leerer Flaeche.
"""
import json
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import shiboken6
from PySide6.QtWidgets import QApplication

from _qt_lifecycle import (destroy_all_top_level_widgets, destroy_widget,
                           flush_deferred_deletes)

_app = QApplication.instance() or QApplication([])

from src.ui.widgets import fixture_vorschau_3d as V   # noqa: E402


@pytest.fixture(autouse=True)
def _keine_uebrigen_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _pump(s=0.2):
    ende = time.monotonic() + s
    while time.monotonic() < ende:
        _app.processEvents()
        time.sleep(0.02)


def _webengine_views(widget):
    from PySide6.QtWebEngineWidgets import QWebEngineView
    return widget.findChildren(QWebEngineView)


class _Mitschnitt:
    """Ersetzt ``_js`` der Vorschau: was ginge per runJavaScript an die Seite?"""

    def __init__(self, vorschau):
        self.skripte = []
        vorschau._js = self.skripte.append
        vorschau._bereit = True      # so tun, als laufe die Szene

    def letztes_geraet(self):
        for s in reversed(self.skripte):
            if "vorschauGeraet(" in s:
                roh = s.split("vorschauGeraet(", 1)[1].rsplit("):-1", 1)[0]
                return json.loads(roh)
        return None

    def letztes_licht(self):
        for s in reversed(self.skripte):
            if "applyDmx(" in s:
                roh = s.split("L.applyDmx(", 1)[1]
                arr, _rest = roh.split(",null", 1)
                return json.loads(arr)[0]
        return None


_GOBO_KANAL = {
    "name": "Gobo", "attribute": "gobo_wheel", "default": 0, "highlight": 0,
    "invert": False, "resolution": "8bit", "segment": None, "laser": {},
    "ranges": [
        {"range_from": 0, "range_to": 9, "name": "Offen", "kind": "open"},
        {"range_from": 10, "range_to": 19, "name": "Punkte", "kind": "gobo"},
        {"range_from": 20, "range_to": 29, "name": "Spirale", "kind": "gobo"},
    ],
}


# ── reine Payload-Funktionen ─────────────────────────────────────────────

def test_geraet_payload_traegt_winkel_und_zoomrichtung():
    d = V.VorschauDaten(typ="moving_head", abstrahlwinkel=(40, 10),
                        zoom_umgekehrt=True)
    p = V.geraet_payload(d)
    assert (p["beamAngleMin"], p["beamAngleMax"]) == (10.0, 40.0)   # getauscht
    assert p["zoomInverted"] is True
    assert p["model"] == "moving_head"
    assert p["fid"] == V.VORSCHAU_FID
    assert (p["x"], p["z"]) == (0.0, 0.0) and p["y"] == V.VORSCHAU_HOEHE


def test_geraet_payload_hat_die_felder_des_visualizers():
    """Dieselben Schluessel wie ``VisualizerBridge._fixture_to_dict`` — sonst
    baute ``addFixture`` die Vorschau anders als die Buehne."""
    import re
    from src.ui.visualizer import visualizer_window as VW
    import inspect
    quelle = inspect.getsource(VW.VisualizerBridge._fixture_to_dict)
    rumpf = quelle.split("return {", 1)[1]
    erwartet = set(re.findall(r'"(\w+)":', rumpf))
    assert erwartet, "Schluessel nicht gefunden — Quelltext umgebaut?"
    fehlt = erwartet - set(V.geraet_payload(V.VorschauDaten()))
    assert not fehlt, f"Vorschau-Payload ohne {sorted(fehlt)}"


def test_override_und_automatik_fuer_das_3d_modell():
    assert V.render_modell(V.VorschauDaten(typ="par", viz_model="spider")) == "spider"
    bar = V.VorschauDaten(typ="led_bar",
                          attribute=["color_r", "color_g", "color_b"] * 4)
    assert V.render_modell(bar) == "par_bar"
    assert V.geraet_payload(bar)["nHeads"] == 4


def test_licht_payload_standard_weiss_ohne_zoom_und_gobo():
    p = V.licht_payload()
    assert (p["r"], p["g"], p["b"], p["intensity"]) == (255, 255, 255, 255)
    assert "zoom" not in p and "gobo" not in p


def test_gobo_liste_aus_dem_profil():
    kanaele = V.kanaele_aus_dicts([_GOBO_KANAL])
    assert V.gobo_auswahl(kanaele) == [("Punkte", "dots"), ("Spirale", "spiral")]
    assert V.gobo_auswahl([]) == []


# ── Editor ───────────────────────────────────────────────────────────────

def _editor():
    from src.ui.widgets.fixture_editor import FixtureEditorDialog
    return FixtureEditorDialog()


def test_editor_oeffnet_ohne_webengine():
    dlg = _editor()
    try:
        dlg.show()
        _pump(0.1)
        assert not dlg._vorschau.geladen
        assert _webengine_views(dlg) == []
        assert dlg._vorschau.btn.text() == V.KNOPF_ZEIGEN
    finally:
        destroy_widget(dlg, _app)


def test_editor_winkel_zoom_und_gobo_kommen_an():
    dlg = _editor()
    try:
        vs = dlg._vorschau
        vs.btn.blockSignals(True)       # aufgeklappt, aber ohne echte Seite
        vs.btn.setChecked(True)
        vs.btn.blockSignals(False)
        mit = _Mitschnitt(vs)
        dlg._abstrahlwinkel.setze(12, 36)
        p = mit.letztes_geraet()
        assert p is not None, "Winkelaenderung schickte kein Geraet"
        assert (p["beamAngleMin"], p["beamAngleMax"]) == (12.0, 36.0)
        assert not vs.sld_zoom.isHidden(), "Zoom-Spanne ohne Zoom-Regler"
        vs.sld_zoom.setValue(200)
        assert mit.letztes_licht()["zoom"] == 200
        # Gobo-Liste kommt aus dem gezeigten Modus
        dlg._tabs.currentWidget().channels.append(dict(_GOBO_KANAL))
        vs.aktualisieren()
        assert not vs.cb_gobo.isHidden()
        vs.cb_gobo.setCurrentIndex(vs.cb_gobo.findText("Spirale"))
        assert mit.letztes_licht()["gobo"] == "spiral"
        vs.cb_farbe.setCurrentIndex(vs.cb_farbe.findText("Rot"))
        licht = mit.letztes_licht()
        assert (licht["r"], licht["g"], licht["b"]) == (255, 0, 0)
        # fester Winkel: kein Zoom-Regler, kein zoom im Licht
        dlg._abstrahlwinkel.setze(20, 0)
        assert vs.sld_zoom.isHidden()
        assert "zoom" not in mit.letztes_licht()
        assert mit.letztes_geraet()["beamAngleMax"] == 20.0
    finally:
        destroy_widget(dlg, _app)


# ── Generator ────────────────────────────────────────────────────────────

def test_generator_oeffnet_ohne_webengine_und_schickt_den_winkel():
    from src.ui.widgets.fixture_generator import FixtureGeneratorDialog
    dlg = FixtureGeneratorDialog()
    try:
        dlg.show()
        _pump(0.1)
        assert not dlg._vorschau.geladen
        assert _webengine_views(dlg) == []
        vs = dlg._vorschau
        vs.btn.blockSignals(True)
        vs.btn.setChecked(True)
        vs.btn.blockSignals(False)
        mit = _Mitschnitt(vs)
        dlg._abstrahlwinkel.setze(8, 30)
        p = mit.letztes_geraet()
        assert (p["beamAngleMin"], p["beamAngleMax"]) == (8.0, 30.0)
        dlg._cb_type.setCurrentText("moving_head")
        dlg._revalidate()
        assert mit.letztes_geraet()["type"] == "moving_head"
    finally:
        destroy_widget(dlg, _app)


# ── Abbau / ohne WebGL ───────────────────────────────────────────────────

def test_aufklappen_baut_ansicht_schliessen_baut_sie_ab():
    dlg = _editor()
    try:
        dlg.show()
        vs = dlg._vorschau
        for _runde in range(2):
            vs.zeigen()
            _pump(0.3)
            assert vs.geladen
            view = vs.view
            assert shiboken6.isValid(view)
            vs.btn.setChecked(False)          # zuklappen = abbauen
            flush_deferred_deletes()
            assert not vs.geladen
            assert not shiboken6.isValid(view), "Ansicht ueberlebt das Zuklappen"
        vs.zeigen()
        _pump(0.3)
        view = vs.view
        dlg.reject()                          # Dialog schliessen
        flush_deferred_deletes()
        _pump(0.2)
        assert not vs.geladen
        assert not shiboken6.isValid(view), "Ansicht ueberlebt den Dialog"
        vs.abbauen()                          # zweimal ist harmlos
    finally:
        destroy_widget(dlg, _app)


def test_ohne_webgl_steht_ein_hinweis_da():
    vs = V.FixtureVorschau3D(lambda: V.VorschauDaten())
    try:
        vs.show()
        vs.zeigen()
        _pump(0.2)
        vs._szene_startet_nicht()            # Szenen-Start-Waechter gibt auf
        flush_deferred_deletes()
        assert not vs.geladen
        assert not vs.lbl_hinweis.isHidden()
        assert vs.lbl_hinweis.text() == V.HINWEIS_KEIN_WEBGL
    finally:
        destroy_widget(vs, _app)


def test_ohne_qtwebengine_steht_ein_hinweis_da():
    vs = V.FixtureVorschau3D(lambda: V.VorschauDaten())

    def _kaputt():
        raise ImportError("kein QtWebEngine")
    vs._baue_view = _kaputt
    try:
        vs.zeigen()
        assert not vs.geladen
        assert vs.lbl_hinweis.text() == V.HINWEIS_KEINE_ENGINE
        assert not vs.lbl_hinweis.isHidden()
    finally:
        destroy_widget(vs, _app)


def test_editor_kanaltabelle_zieht_die_vorschau_nach():
    """Review: ein Kanal-Attribut in der Tabelle aendern (oder Kanaele
    hinzufuegen/loeschen) muss die Vorschau nachziehen — sonst stuende nach
    dem zweiten ``color_r`` weiter eine Einzel-PAR statt der Bar da, und ein
    neuer Gobo-Kanal fehlte in der Gobo-Liste."""
    dlg = _editor()
    try:
        vs = dlg._vorschau
        vs.btn.blockSignals(True)
        vs.btn.setChecked(True)
        vs.btn.blockSignals(False)
        mit = _Mitschnitt(vs)
        tab = dlg._tabs.currentWidget()
        for _ in range(2):
            tab._add_channel()
        assert mit.letztes_geraet() is not None, "Kanal hinzufuegen ohne Vorschau"
        for row in range(2):
            tab._tbl.cellWidget(row, 2).setCurrentText("color_r")
        assert mit.letztes_geraet()["model"] == "par_bar"
        assert mit.letztes_geraet()["nHeads"] == 2
        tab._tbl.selectRow(1)
        tab._del_channel()
        assert mit.letztes_geraet()["model"] == dlg._cb_type.currentText()
    finally:
        destroy_widget(dlg, _app)


def test_pixelkopf_traegt_den_ring_versatz_wie_der_visualizer():
    """Review: ``pixelBase`` kommt wie im Betrieb aus ``pixel_ring_base_banks``
    (CDX-55) — mit fester 0 zeigte die Vorschau die Grundfarbe als zusaetzliches
    Ring-Segment."""
    from src.core.app_state import pixel_ring_base_banks
    # Grundfarben-Lage mit eigenem Weiss/Shutter, dahinter 4 RGB-Pixel
    attrs = (["pan", "tilt", "dimmer", "color_r", "color_g", "color_b",
              "color_w", "shutter"]
             + ["color_r", "color_g", "color_b"] * 4)
    d = V.VorschauDaten(typ="moving_head", attribute=attrs)
    p = V.geraet_payload(d)
    assert p["model"] == "pixel_head"
    assert p["nHeads"] == 5
    assert p["pixelBase"] == pixel_ring_base_banks(attrs)
    assert p["pixelBase"] == 1


def test_unveraendertes_geraet_wird_nicht_neu_gebaut():
    """Review: der Generator ruft ``aktualisieren`` nach jeder Eingabe (auch im
    Namensfeld). Ohne Aenderung am Geraet kein Neubau — nur das Licht."""
    d = V.VorschauDaten(abstrahlwinkel=(20, 0))
    vs = V.FixtureVorschau3D(lambda: d)
    try:
        mit = _Mitschnitt(vs)
        vs.aktualisieren()
        vs.aktualisieren()
        bauten = [s for s in mit.skripte if "vorschauGeraet(" in s]
        assert len(bauten) == 1, f"{len(bauten)} Neubauten ohne Aenderung"
        d.abstrahlwinkel = (30, 0)
        vs.aktualisieren()
        assert mit.letztes_geraet()["beamAngleMin"] == 30.0
        vs._geraet_senden(erzwingen=True)       # neue Seite: immer bauen
        assert len([s for s in mit.skripte if "vorschauGeraet(" in s]) == 3
    finally:
        destroy_widget(vs, _app)
