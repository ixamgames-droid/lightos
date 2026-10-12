"""LAS-33: die Laser-Seiten des Fixture Generators (offscreen).

* die Seiten gibt es nur bei einem Laser (Typ „laser“ oder ein Laser-Kanal);
* Musterliste: Zeilen anlegen und aendern, „Bereiche gleichmäßig aufteilen“,
  Schemabild je Zeile und Vorschau, eigene Form zeichnen;
* Farbtabelle mit Farbfeld; Richtungs-Haken mit sprechenden Enden und
  Mittelbereich; Betriebsart aus den Wertebereichen;
* ueberlappende/lueckenhafte Bereiche sind ein Hinweis, keine Sperre;
* speichern und wieder oeffnen erhaelt alles;
* der Platz reicht auf einem 1080er-Bildschirm (FM-70).
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from src.core.laser import profilangaben as PA

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EL400 = os.path.join(_REPO, "fixtures", "bibliothek", "laserworld",
                     "el-400rgb-mk2.json")


def _app():
    return QApplication.instance() or QApplication([])


def _el400() -> dict:
    with open(EL400, encoding="utf-8") as f:
        return json.load(f)


def _modell(typ="laser", mit_laserkanal=False):
    from src.ui.widgets.fixture_generator import (GenChannel, GenMode,
                                                  GeneratorModel, GenRange)
    kanaele = [
        GenChannel("Betriebsart", "shutter", 0, 200, ranges=[
            GenRange(0, 49, "Laser aus", "closed"),
            GenRange(50, 99, "Musik-Modus", "sound"),
            GenRange(100, 149, "Auto-Modus", ""),
            GenRange(150, 199, "Statische Muster (DMX)", "open"),
            GenRange(200, 255, "Dynamische Muster (DMX)", "open")]),
        GenChannel("Musterauswahl", "gobo_wheel", 0, 0),
        GenChannel("Position X", "laser_x" if mit_laserkanal or typ == "laser"
                   else "raw", 0, 0),
        GenChannel("Zoom", "zoom", 128, 128),
        GenChannel("Farbe", "laser_color" if typ == "laser" else "raw", 0, 0),
    ]
    return GeneratorModel(manufacturer="Testwerk", model="Generatorlaser",
                          fixture_type=typ, modes=[GenMode("5-Kanal", kanaele)])


@pytest.fixture
def dialog():
    _app()
    from src.ui.widgets.fixture_generator import FixtureGeneratorDialog
    offen = []

    def bauen(model=None, hoehe=1000):
        dlg = FixtureGeneratorDialog(None, model=model or _modell())
        dlg.resize(1200, hoehe)
        dlg.show()
        _app().processEvents()
        offen.append(dlg)
        return dlg

    yield bauen
    for dlg in offen:
        dlg._live.shutdown()
        dlg.close()
        dlg.deleteLater()
    _app().processEvents()


def _tab(dlg):
    return dlg._tabs.currentWidget()


# ── Sichtbarkeit ─────────────────────────────────────────────────────────────

def test_laser_seiten_nur_bei_einem_laser(dialog):
    par = _tab(dialog(_modell("par")))
    assert not par.laser_seiten_sichtbar()
    assert not par._seiten.tabBar().isVisible(), "Nicht-Laser: Dialog wie vorher"

    laser = _tab(dialog(_modell("laser")))
    assert laser.laser_seiten_sichtbar() and laser._seiten.tabBar().isVisible()
    assert [laser._seiten.tabText(i) for i in range(laser._seiten.count())] == [
        "Kanäle && Bereiche", "Laser: Muster", "Laser: Farben",
        "Laser: Richtungen"]

    # Typ „other“, aber ein Laser-Kanal: die Seiten sind da.
    assert _tab(dialog(_modell("other", mit_laserkanal=True))).laser_seiten_sichtbar()


def test_typwechsel_und_attribut_blenden_die_seiten_ein(dialog):
    dlg = dialog(_modell("par"))
    tab = _tab(dlg)
    assert not tab.laser_seiten_sichtbar()
    dlg._cb_type.setCurrentText("laser")
    _app().processEvents()
    assert tab.laser_seiten_sichtbar()
    tab.zeige_seite(1)
    dlg._cb_type.setCurrentText("par")
    _app().processEvents()
    assert not tab.laser_seiten_sichtbar()
    assert tab._seiten.currentIndex() == 0, "zurueck auf die Kanaltabelle"
    tab._set_attr(2, "laser_y")
    assert tab.laser_seiten_sichtbar()


# ── Muster ───────────────────────────────────────────────────────────────────

def test_musterliste_zeilen_anlegen_und_aendern(dialog):
    dlg = dialog()
    tab = _tab(dlg)
    tab.zeige_seite(1)
    seite = tab.laser_muster
    assert seite.kanal() is tab.mode.channels[1], "Vorauswahl: der Gobo-Kanal"
    assert seite.tbl.rowCount() == 0

    QTest.mouseClick(seite.btn_neu, Qt.MouseButton.LeftButton)
    QTest.mouseClick(seite.btn_neu, Qt.MouseButton.LeftButton)
    assert seite.tbl.rowCount() == 2
    kanal = tab.mode.channels[1]
    assert [(m["von"], m["bis"]) for m in kanal.laser["muster"]] == [(0, 0), (1, 1)]

    seite.zellen_widget(0, seite.C_BIS).setValue(31)
    seite.zellen_widget(1, seite.C_VON).setValue(32)
    seite.zellen_widget(1, seite.C_BIS).setValue(63)
    seite.tbl.item(0, seite.C_NAME).setText("Tunnel")
    form = seite.zellen_widget(1, seite.C_FORM)
    form.setCurrentIndex(form.findData("stern"))
    seite.zellen_widget(1, seite.C_ANZAHL).setValue(7)
    stil = seite.zellen_widget(1, seite.C_STIL)
    stil.setCurrentIndex(stil.findData("gepunktet"))
    seite.zellen_widget(1, seite.C_BEWEGT).setChecked(True)
    assert kanal.laser["muster"] == [
        {"von": 0, "bis": 31, "name": "Tunnel", "form": "kreis"},
        {"von": 32, "bis": 63, "name": "Muster 2", "form": "stern", "anzahl": 7,
         "stil": "gepunktet", "bewegt": True}]
    # Kreis hat keine Anzahl, Stern schon.
    assert not seite.zellen_widget(0, seite.C_ANZAHL).isEnabled()
    assert seite.zellen_widget(1, seite.C_ANZAHL).isEnabled()

    seite.tbl.setCurrentCell(0, seite.C_NAME)
    QTest.mouseClick(seite.btn_weg, Qt.MouseButton.LeftButton)
    assert len(kanal.laser["muster"]) == 1 and seite.tbl.rowCount() == 1
    assert dlg._model.to_payload()["modes"][0]["channels"][1]["laser"] == {
        "version": 1,
        "muster": [{"von": 32, "bis": 63, "name": "Muster 2", "form": "stern",
                    "anzahl": 7, "stil": "gepunktet", "bewegt": True}]}


def test_bereiche_gleichmaessig_aufteilen(dialog):
    tab = _tab(dialog())
    tab.zeige_seite(1)
    seite = tab.laser_muster
    seite.zeile_dazu({"von": 3, "bis": 9, "name": "Kreis", "form": "kreis"})
    seite.zeile_dazu({"von": 9, "bis": 12, "name": "Stern", "form": "stern"})
    assert any("überlappen" in h for h in seite.hinweise())
    assert seite.lbl_hinweis.isVisible() and "überlappen" in seite.lbl_hinweis.text()

    seite.aufteilen(16)
    muster = tab.mode.channels[1].laser["muster"]
    assert len(muster) == 16 and seite.tbl.rowCount() == 16
    assert [(m["von"], m["bis"]) for m in muster] == PA.gleichmaessig_aufteilen(16)
    assert (muster[0]["name"], muster[1]["form"]) == ("Kreis", "stern"), \
        "vorhandene Zeilen behalten Name und Form"
    assert muster[15]["name"] == "Muster 16"
    assert seite.hinweise() == [] and not seite.lbl_hinweis.isVisible()
    assert seite.zellen_widget(15, seite.C_VON).value() == 240

    seite.aufteilen(4)
    assert [(m["von"], m["bis"]) for m in muster] == [
        (0, 63), (64, 127), (128, 191), (192, 255)]


def test_schemabild_je_zeile_und_vorschau(dialog):
    tab = _tab(dialog())
    tab.zeige_seite(1)
    seite = tab.laser_muster
    seite.zeile_dazu({"von": 0, "bis": 9, "name": "Kreis", "form": "kreis"})
    seite.zeile_dazu({"von": 10, "bis": 19, "name": "Stern", "form": "stern"})
    _app().processEvents()

    def gruen(bild):
        img = bild.toImage()
        return sum(1 for x in range(img.width()) for y in range(img.height())
                   if img.pixelColor(x, y).green() > 150
                   and img.pixelColor(x, y).red() < 120)

    kreis = seite.zellen_widget(0, seite.C_BILD).pixmap()
    stern = seite.zellen_widget(1, seite.C_BILD).pixmap()
    assert gruen(kreis) > 20 and gruen(stern) > 20
    assert kreis.toImage() != stern.toImage()

    # Die Vorschau zeigt die GEWAEHLTE Zeile und folgt jeder Aenderung.
    seite.tbl.setCurrentCell(1, seite.C_NAME)
    assert seite.bild.muster()["name"] == "Stern"
    assert "Stern" in seite.lbl_bild.text() and "10–19" in seite.lbl_bild.text()
    vorher = seite.bild.grab().toImage()
    form = seite.zellen_widget(1, seite.C_FORM)
    form.setCurrentIndex(form.findData("welle"))
    _app().processEvents()
    assert seite.bild.muster()["form"] == "welle"
    assert seite.bild.grab().toImage() != vorher
    assert seite.zellen_widget(1, seite.C_BILD).pixmap().toImage() != stern.toImage()
    seite.tbl.setCurrentCell(0, seite.C_NAME)
    assert seite.bild.muster()["name"] == "Kreis"


def test_jede_form_laesst_sich_malen_und_bewegt_sieht_anders_aus():
    _app()
    from src.ui.widgets.laser_musterbild import muster_pixmap
    bilder = {}
    for form in PA.FORMEN:
        m = {"form": form}
        if form == PA.EIGENE_FORM:
            m["linien"] = [{"punkte": [[-0.6, -0.6], [0.6, -0.6], [0, 0.7]],
                            "geschlossen": True}]
        img = muster_pixmap(m, 64).toImage()
        farbig = sum(1 for x in range(64) for y in range(64)
                     if img.pixelColor(x, y).green() > 150)
        assert farbig > 8, f"{form}: nichts gezeichnet"
        bilder[form] = img
    assert len({i.cacheKey() for i in bilder.values()}) == len(bilder)
    assert bilder["kreis"] != bilder["quadrat"]
    ruhig = muster_pixmap({"form": "kreis"}, 64).toImage()
    bewegt = muster_pixmap({"form": "kreis", "bewegt": True}, 64).toImage()
    assert ruhig != bewegt
    rot = muster_pixmap({"form": "kreis"}, 64, QColor("#ff0000")).toImage()
    assert rot != ruhig
    # Unbekannte Form: kein Absturz, ein Fragezeichen-Feld.
    assert not muster_pixmap({"form": "herz"}, 64).isNull()
    assert not muster_pixmap(None, 64).isNull()


def test_eigene_form_zeichnen(dialog):
    _app()
    from src.ui.widgets.laser_musterbild import FormZeichnenDialog
    dlg = FormZeichnenDialog(None, None, "Haus")
    dlg.resize(460, 560)
    dlg.show()
    _app().processEvents()
    z = dlg.zeichner
    try:
        # Drei Klicks -> ein Linienzug mit drei Punkten.
        for x, y in ((-0.5, -0.5), (0.5, -0.5), (0.0, 0.5)):
            QTest.mouseClick(z, Qt.MouseButton.LeftButton,
                             pos=z.zu_bild(x, y).toPoint())
        (linie,) = z.linien()
        assert len(linie["punkte"]) == 3 and "geschlossen" not in linie
        for (x, y), (sx, sy) in zip(linie["punkte"],
                                    ((-0.5, -0.5), (0.5, -0.5), (0.0, 0.5))):
            assert abs(x - sx) < 0.03 and abs(y - sy) < 0.03
        # Schließen.
        QTest.mouseClick(dlg.btn_schliessen, Qt.MouseButton.LeftButton)
        assert dlg.linien()[0].get("geschlossen") is True
        # Neuer Linienzug: zwei Punkte, offen beendet.
        QTest.mouseClick(z, Qt.MouseButton.LeftButton, pos=z.zu_bild(-0.8, 0.8).toPoint())
        QTest.mouseClick(z, Qt.MouseButton.LeftButton, pos=z.zu_bild(0.8, 0.8).toPoint())
        QTest.mouseClick(dlg.btn_neu, Qt.MouseButton.LeftButton)
        QTest.mouseClick(z, Qt.MouseButton.LeftButton, pos=z.zu_bild(0.0, 0.0).toPoint())
        linien = dlg.linien()
        assert [len(l["punkte"]) for l in linien] == [3, 2, 1]
        # Das Ergebnis ist ein gueltiges Muster.
        muster = {"von": 0, "bis": 9, "name": "Haus", "form": "eigene",
                  "linien": linien}
        assert PA.pruefe({"version": 1, "muster": [muster]}) == []
        # Letzten Punkt entfernen, zu wenige Punkte schliessen nicht.
        QTest.mouseClick(dlg.btn_zurueck, Qt.MouseButton.LeftButton)
        assert [len(l["punkte"]) for l in dlg.linien()] == [3, 2]
        assert z.schliessen() is False, "zwei Punkte ergeben keine Flaeche"
        # Alles löschen.
        QTest.mouseClick(dlg.btn_loeschen, Qt.MouseButton.LeftButton)
        assert dlg.linien() == []
        # Klick ausserhalb wird auf den Rand geklemmt.
        QTest.mouseClick(z, Qt.MouseButton.LeftButton, pos=QPoint(1, 1))
        (p,) = dlg.linien()[0]["punkte"]
        assert -1.0 <= p[0] <= 1.0 and -1.0 <= p[1] <= 1.0
    finally:
        dlg.close()
        dlg.deleteLater()

    # In der Musterliste: die Zeichnung macht die Zeile zur eigenen Form.
    tab = _tab(dialog())
    tab.zeige_seite(1)
    seite = tab.laser_muster
    seite.zeile_dazu()
    form = seite.zellen_widget(0, seite.C_FORM)
    form.setCurrentIndex(form.findData("eigene"))
    assert any("eigene Form ohne Zeichnung" in h for h in seite.hinweise())
    seite.eigene_form_setzen(0, [{"punkte": [[-0.5, -0.5], [0.5, -0.5], [0, 0.5]],
                                  "geschlossen": True}])
    m = tab.mode.channels[1].laser["muster"][0]
    assert m["form"] == "eigene" and len(m["linien"][0]["punkte"]) == 3
    assert not any("eigene Form" in h for h in seite.hinweise())
    assert seite.zellen_widget(0, seite.C_FORM).currentData() == "eigene"


# ── Farben ───────────────────────────────────────────────────────────────────

def test_farbtabelle_mit_farbfeld(dialog):
    tab = _tab(dialog())
    tab.zeige_seite(2)
    seite = tab.laser_farben
    assert seite.kanal() is tab.mode.channels[4], "Vorauswahl: laser_color"
    QTest.mouseClick(seite.btn_neu, Qt.MouseButton.LeftButton)
    QTest.mouseClick(seite.btn_neu, Qt.MouseButton.LeftButton)
    farben = tab.mode.channels[4].laser["farben"]
    assert [(f["name"], f["farbe"]) for f in farben] == [
        ("Rot", PA.FARBEN["rot"][1]), ("Grün", PA.FARBEN["gruen"][1])]

    def feldfarbe(zeile):
        img = seite.zellen_widget(zeile, seite.C_FELD).pixmap().toImage()
        return img.pixelColor(img.width() // 2, img.height() // 2)

    assert feldfarbe(0).red() > 200 and feldfarbe(0).green() < 100
    assert feldfarbe(1).green() > 200 and feldfarbe(1).red() < 100

    cb = seite.zellen_widget(1, seite.C_FARBE)
    cb.setCurrentIndex(cb.findData(PA.FARBEN["blau"][1]))
    assert farben[1] == {"von": 1, "bis": 1, "name": "Blau",
                         "farbe": PA.FARBEN["blau"][1]}
    assert feldfarbe(1).blue() > 200
    # Ein selbst vergebener Name bleibt beim Farbwechsel stehen.
    seite.tbl.item(0, seite.C_NAME).setText("Feuer")
    seite.farbe_setzen(0, PA.MEHRFARBIG)
    assert farben[0]["name"] == "Feuer" and farben[0]["farbe"] == "mehrfarbig"
    # Eigener Farbwert (wie aus dem Farbdialog).
    seite.farbe_setzen(1, "#123456")
    assert seite.zellen_widget(1, seite.C_FARBE).currentData() == "#123456"

    seite.aufteilen(8)
    assert len(farben) == 8 and farben[-1]["bis"] == 255
    assert [(f["von"], f["bis"]) for f in farben] == PA.gleichmaessig_aufteilen(8)
    assert seite.hinweise() == []
    seite.zellen_widget(0, seite.C_BIS).setValue(40)
    assert any("überlappen" in h for h in seite.hinweise())
    assert PA.pruefe({"version": 1, "farben": farben}) == []


# ── Richtungen und Betriebsart ───────────────────────────────────────────────

def test_richtungs_haken_mit_sprechenden_enden(dialog):
    tab = _tab(dialog())
    tab.zeige_seite(3)
    seite = tab.laser_richtung
    assert seite.tbl.rowCount() == 5
    zoom, x = tab.mode.channels[3], tab.mode.channels[2]
    assert "richtung" not in zoom.laser

    cb, haken, m_von, m_bis = seite.richtung_widgets(3)
    cb.setCurrentIndex(1)                       # klein … groß
    assert zoom.laser["richtung"] == {"umgekehrt": False, "ende_niedrig": "klein",
                                      "ende_hoch": "gross"}
    haken.setChecked(True)
    assert zoom.laser["richtung"] == {"umgekehrt": True, "ende_niedrig": "gross",
                                      "ende_hoch": "klein"}
    assert "niedrig = groß" in seite.tbl.item(3, seite.C_TEXT).text()

    cb, haken, m_von, m_bis = seite.richtung_widgets(2)
    cb.setCurrentIndex(3)                       # links … rechts
    haken.setChecked(True)
    m_von.setValue(0)
    assert seite.lbl_hinweis.isVisible(), "Mitte nur halb angegeben"
    m_bis.setValue(10)
    assert not seite.lbl_hinweis.isVisible()
    assert x.laser["richtung"] == {"umgekehrt": True, "ende_niedrig": "rechts",
                                   "ende_hoch": "links",
                                   "mitte": {"von": 0, "bis": 10}}
    assert PA.pruefe({"version": 1, "richtung": x.laser["richtung"]}) == []
    r = PA.kanal_angaben(x.laser).richtung
    assert r.enden == ("links", "rechts") and r.regelweg == (11, 255)

    # Alles zurueck -> keine Angabe mehr.
    cb.setCurrentIndex(0)
    haken.setChecked(False)
    m_von.setValue(-1)
    m_bis.setValue(-1)
    assert "richtung" not in x.laser


def test_betriebsart_aus_den_wertebereichen(dialog):
    tab = _tab(dialog())
    tab.zeige_seite(3)
    seite = tab.laser_richtung
    assert seite.betriebsart_kanal() is tab.mode.channels[0]
    assert seite.tbl_b.rowCount() == 0
    QTest.mouseClick(seite.btn_b_aus, Qt.MouseButton.LeftButton)
    soll = _el400()["modi"][0]["kanaele"][0]["laser"]["betriebsart"]
    assert tab.mode.channels[0].laser["betriebsart"] == soll, \
        "der Vorschlag ergibt genau die Angaben des Bibliotheksprofils"
    assert seite.tbl_b.rowCount() == 5
    von, bis, art, steuert = seite.betriebsart_widgets(1)
    assert (von.value(), bis.value(), art.currentData(), steuert.isChecked()) == \
        (50, 99, "musik", False)
    steuert.setChecked(True)
    art.setCurrentIndex(art.findData("auto"))
    assert tab.mode.channels[0].laser["betriebsart"][1] == {
        "von": 50, "bis": 99, "art": "auto", "steuert": True}
    seite.betriebsart_weg(1)
    assert len(tab.mode.channels[0].laser["betriebsart"]) == 4
    seite.betriebsart_dazu()
    assert seite.tbl_b.rowCount() == 5
    # „offen“ ist nicht „off“.
    assert PA.betriebsart_aus_bereichen([(0, 9, "Shutter offen", "open")]) == []


# ── Hinweise, speichern, wieder oeffnen ──────────────────────────────────────

def test_ueberlappung_ist_hinweis_und_sperrt_das_speichern_nicht(dialog, monkeypatch):
    from src.ui.widgets import fixture_generator as FG
    dlg = dialog()
    tab = _tab(dlg)
    tab.zeige_seite(1)
    seite = tab.laser_muster
    seite.zeile_dazu({"von": 0, "bis": 20, "name": "A", "form": "kreis"})
    seite.zeile_dazu({"von": 10, "bis": 30, "name": "B", "form": "stern"})
    seite.zeile_dazu({"von": 40, "bis": 50, "name": "", "form": "welle"})
    hinweise = FG.validate_model(dlg._model)
    texte = [t for _s, t in hinweise]
    assert any("überlappen" in t and "Musterauswahl" in t for t in texte)
    assert any("ohne Eintrag" in t for t in texte)
    assert any("unvollständig" in t for t in texte), "Muster ohne Namen"
    assert not [t for s, t in hinweise if s == "error"], "nie eine Sperre"
    assert "überlappen" in dlg._issues.toPlainText()

    gespeichert = []
    monkeypatch.setattr(FG, "save_generated_profile",
                        lambda payload, **kw: gespeichert.append(payload) or 4711)
    fragen = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: fragen.append(a) or QMessageBox.StandardButton.No)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    dlg._save()
    assert dlg.saved_id == 4711 and not fragen
    muster = gespeichert[0]["modes"][0]["channels"][1]["laser"]["muster"]
    assert [m["name"] for m in muster] == ["A", "B"]


def test_speichern_und_wieder_oeffnen(dialog, monkeypatch, tmp_path):
    from sqlalchemy import create_engine
    from src.core.database import fixture_db as fdb
    from src.core.database.models import (create_all_idempotent,
                                          migrate_fixtures_db)
    from src.ui.widgets import fixture_generator as FG
    eng = create_engine(f"sqlite:///{tmp_path / 'fixtures.db'}")
    create_all_idempotent(eng)
    migrate_fixtures_db(eng)
    monkeypatch.setattr(FG, "save_generated_profile",
                        lambda payload, **kw: fdb.create_user_profile(payload,
                                                                      engine=eng))
    for name in ("information", "warning"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: None)

    dlg = dialog()
    tab = _tab(dlg)
    tab.zeige_seite(1)
    tab.laser_muster.aufteilen(4)
    form = tab.laser_muster.zellen_widget(2, tab.laser_muster.C_FORM)
    form.setCurrentIndex(form.findData("mehrere_kreise"))
    tab.laser_muster.zellen_widget(3, tab.laser_muster.C_BEWEGT).setChecked(True)
    tab.laser_muster.eigene_form_setzen(
        1, [{"punkte": [[-0.5, 0.0], [0.5, 0.0]]}])
    tab.zeige_seite(2)
    tab.laser_farben.aufteilen(3)
    tab.zeige_seite(3)
    cb, haken, _v, _b = tab.laser_richtung.richtung_widgets(3)
    cb.setCurrentIndex(1)
    haken.setChecked(True)
    tab.laser_richtung.betriebsart_aus_bereichen()
    vorher = [c["laser"] for c in dlg._model.to_payload()["modes"][0]["channels"]]
    assert vorher[1]["muster"][1]["form"] == "eigene"
    assert vorher[2] is None, "Kanal ohne Angaben traegt keine"
    dlg._save()
    assert dlg.saved_id

    # Wieder oeffnen: dasselbe Profil aus der DB in einem NEUEN Dialog.
    modell = FG.model_from_profile(dlg.saved_id, engine=eng)
    assert [c.laser or None for c in modell.modes[0].channels] == vorher
    neu = dialog(modell)
    tab2 = _tab(neu)
    assert tab2.laser_seiten_sichtbar()
    tab2.zeige_seite(1)
    assert tab2.laser_muster.tbl.rowCount() == 4
    assert tab2.laser_muster.zellen_widget(2, tab2.laser_muster.C_FORM) \
        .currentData() == "mehrere_kreise"
    assert tab2.laser_muster.zellen_widget(3, tab2.laser_muster.C_BEWEGT).isChecked()
    tab2.zeige_seite(2)
    assert tab2.laser_farben.tbl.rowCount() == 3
    tab2.zeige_seite(3)
    assert tab2.laser_richtung.richtung_widgets(3)[1].isChecked()
    assert tab2.laser_richtung.tbl_b.rowCount() == 5
    assert [c["laser"] for c in
            neu._model.to_payload()["modes"][0]["channels"]] == vorher
    # Die Lese-Schicht sieht dasselbe.
    a = PA.laser_profilangaben(modell, "5-Kanal")
    assert a.muster_kanal.muster_fuer(200).bewegt
    assert a.richtung("zoom").enden == ("klein", "gross")
    eng.dispose()


def test_bibliotheksprofil_im_generator_oeffnen(dialog):
    """Das mitgelieferte EL-400-Profil laesst sich als Vorlage oeffnen; das
    Payload traegt danach genau die Angaben der Datei."""
    from src.ui.widgets import fixture_generator as FG
    daten = _el400()
    dlg = dialog(FG.model_from_daten(daten))
    tab = _tab(dlg)
    tab.zeige_seite(1)
    assert tab.laser_muster.kanal().name == "Musterauswahl"
    assert tab.laser_muster.tbl.rowCount() == 8
    tab.zeige_seite(2)
    assert tab.laser_farben.kanal().name == "Farbe"
    tab.zeige_seite(3)
    assert tab.laser_richtung.betriebsart_kanal().name == "Betriebsart"
    kanaele = dlg._model.to_payload()["modes"][0]["channels"]
    for k, soll in zip(kanaele, daten["modi"][0]["kanaele"]):
        assert k["laser"] == soll.get("laser"), k["name"]
    # set_model (Import-Knopf) behaelt Leistung und Notizen des neuen Modells.
    anderes = _modell()
    anderes.power_w, anderes.notes = 77, "aus der Vorlage"
    dlg.set_model(anderes)
    assert (dlg._model.power_w, dlg._model.notes) == (77, "aus der Vorlage")
    assert dlg._tabs.tabText(0) == "5-Kanal"


def test_kanalreihenfolge_aendern_nimmt_die_angaben_mit(dialog):
    tab = _tab(dialog())
    tab.zeige_seite(1)
    tab.laser_muster.aufteilen(2)
    kanal = tab.mode.channels[1]
    tab.zeige_seite(0)
    tab._tbl.selectRow(1)
    tab._move(1)
    assert tab.mode.channels[2] is kanal and len(kanal.laser["muster"]) == 2
    tab.zeige_seite(1)
    assert tab.laser_muster.kanal() is kanal
    assert tab.laser_muster.cb_kanal.currentText() == "3: Musterauswahl"


# ── Platz (FM-70: 1080er-Bildschirm) ─────────────────────────────────────────

def test_platz_auf_einem_1080er_bildschirm(dialog):
    from src.ui.widgets import fixture_generator as FG
    dlg = dialog(FG.model_from_daten(_el400()), hoehe=1000)
    tab = _tab(dlg)
    # Die Kanaltabelle behaelt ihre fuenf Zeilen trotz Reiterleiste.
    tbl = tab._tbl
    assert tbl.viewport().height() // max(1, tbl.rowHeight(0)) >= 5
    tab.zeige_seite(1)
    _app().processEvents()
    seite = tab.laser_muster
    assert seite.tbl.viewport().height() // seite.tbl.rowHeight(0) >= 5
    # Vorschau, Unterschrift und Knopfzeile ueberdecken sich nicht.
    bild, text = seite.bild.geometry(), seite.lbl_bild.geometry()
    assert bild.bottom() < text.top()
    assert seite.bild.mapTo(seite, QPoint(0, seite.bild.height())).y() <= \
        seite.btn_neu.mapTo(seite, QPoint(0, 0)).y()
    assert seite.tbl.horizontalScrollBar().maximum() == 0, "keine Querleiste"
    tab.zeige_seite(3)
    _app().processEvents()
    r = tab.laser_richtung
    assert r.tbl.viewport().height() // r.tbl.rowHeight(0) >= 5
    assert r.tbl_b.viewport().height() // r.tbl_b.rowHeight(0) >= 5, \
        "alle fuenf Betriebsarten des EL-400 ohne Rollen"
    assert r.tbl_b.horizontalScrollBar().maximum() == 0
    assert dlg.height() <= 1000


# ── Der einfache Fixture-Editor traegt die Angaben mit ───────────────────────

def test_fixture_editor_speichern_erhaelt_die_laser_angaben(monkeypatch, tmp_path):
    """Der Editor zeigt die Laser-Angaben nicht, sein ``_save`` loescht aber
    alle Modi und baut sie neu — ohne Mittragen waeren sie nach dem ersten
    Bearbeiten weg."""
    _app()
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from src.core.database import bibliothek_format as BF
    from src.core.database.models import (FixtureChannel, create_all_idempotent,
                                          migrate_fixtures_db)
    from src.ui.widgets import fixture_editor as FE
    eng = create_engine(f"sqlite:///{tmp_path / 'fixtures.db'}")
    create_all_idempotent(eng)
    migrate_fixtures_db(eng)
    daten = _el400()
    daten["hersteller"], daten["modell"] = "Testwerk", "Editorlaser"
    pid = BF.importiere(daten, engine=eng)
    monkeypatch.setattr(FE, "engine", lambda: eng)
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)

    def angaben():
        with Session(eng) as s:
            return {c.channel_number: c.laser_angaben for c in s.execute(
                select(FixtureChannel)).scalars()}

    vorher = angaben()
    assert PA.aus_text(vorher[2])["muster"][6]["name"] == "Stern"
    dlg = FE.FixtureEditorDialog(None, fixture_id=pid)
    try:
        dlg._spin_power.setValue(31)
        dlg._save()
        assert dlg.saved_id == pid
    finally:
        dlg.close()
        dlg.deleteLater()
    assert angaben() == vorher
    # … und der Export aus dem Editor-Stand traegt sie ebenfalls.
    assert BF.exportiere(pid, engine=eng)["modi"][0]["kanaele"][7]["laser"] == \
        daten["modi"][0]["kanaele"][7]["laser"]
    eng.dispose()
