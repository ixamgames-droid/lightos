"""LIZ-1: Der Lizenzdialog schneidet keinen Text ab.

Befund der Sichtprobe: bei 540 px Breite war die zweite Zeile der Erklaerung
angeschnitten, der Link nur halb zu sehen und die Pfadzeile abgeschnitten. Die
Hoehe muss dem umbrochenen Inhalt folgen — fuer jeden Grund und auch bei einem
sehr langen Datenordner-Pfad — und der Dialog darf nie groesser werden als der
Bildschirm.
"""
from __future__ import annotations

import datetime as dt

import pytest
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from src.core import lizenz
from src.ui.lizenz_dialog import MIN_BREITE, LizenzDialog

LANGER_ORDNER = "/" + "/".join(
    f"ein_sehr_langer_ordnername_{i:02d}" for i in range(14)) + "/LightOS"

LANGER_GRUND = ("unbekanntes Lizenzformat "
                + "9" * 23 + "… — diese Programmversion kennt Format 1. "
                + "Bitte eine neue Lizenzdatei beim Urheber anfordern. " * 4)

GRUENDE = {
    "fehlt": lizenz.Lizenzstatus(lizenz.FEHLT),
    "abgelaufen": lizenz.Lizenzstatus(
        lizenz.ABGELAUFEN, name="Eine Testerin mit einem recht langen Namen",
        kennung="abc", gueltig_bis=dt.date(2026, 1, 31)),
    "ungueltig": lizenz.Lizenzstatus(lizenz.UNGUELTIG,
                                     grund="Signatur passt nicht"),
    "unbekanntes_format": lizenz.Lizenzstatus(lizenz.UNGUELTIG,
                                              grund=LANGER_GRUND),
}


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _umgebung(monkeypatch, tmp_path):
    monkeypatch.delenv(lizenz.ENV_PFAD, raising=False)
    monkeypatch.setattr(lizenz, "app_data_dir",
                        lambda: str(tmp_path / "daten" / "LightOS"))


def _zeige(app, status, breite=None):
    dlg = LizenzDialog(status)
    if breite is not None:
        dlg.resize(breite, dlg.height())
    dlg.show()
    app.processEvents()
    app.processEvents()
    return dlg


def _pruefe_nichts_abgeschnitten(dlg):
    """Jedes Label ist mindestens so gross, wie sein Text bei der tatsaechlichen
    Breite braucht, und liegt ganz im sichtbaren Bereich; alle Knoepfe sind
    ganz im Dialog."""
    sicht = dlg.bereich.viewport()
    for lab in (dlg.erklaerung, dlg.grund, dlg.ort, dlg.ort_pfad):
        assert lab.isVisible()
        brauch = lab.heightForWidth(lab.width())
        if brauch < 0:
            brauch = lab.sizeHint().height()
        assert lab.height() >= brauch, (lab.text()[:40], lab.height(), brauch)
        if lab is not dlg.ort_pfad:
            assert lab.width() >= lab.minimumSizeHint().width()
        # Nichts liegt unterhalb des sichtbaren Bereichs (kein Rollen noetig).
        unten = lab.mapTo(sicht, lab.rect().bottomLeft()).y()
        assert unten <= sicht.height(), (lab.text()[:40], unten, sicht.height())
    # Der gekuerzte Pfad passt in seine Zeile.
    fm = dlg.ort_pfad.fontMetrics()
    assert fm.horizontalAdvance(dlg.ort_pfad.text()) <= dlg.ort_pfad.width()
    assert dlg.kopf.height() >= dlg.kopf.sizeHint().height()
    assert not dlg.bereich.verticalScrollBar().isVisible()
    for knopf in dlg.findChildren(QPushButton):
        assert knopf.isVisible()
        assert knopf.height() >= knopf.sizeHint().height()
        assert knopf.width() >= knopf.sizeHint().width()
        assert dlg.rect().contains(knopf.geometry()), knopf.text()


@pytest.mark.parametrize("name", list(GRUENDE))
@pytest.mark.parametrize("langer_pfad", [False, True])
def test_kein_label_abgeschnitten(app, monkeypatch, name, langer_pfad):
    if langer_pfad:
        monkeypatch.setattr(lizenz, "app_data_dir", lambda: LANGER_ORDNER)
    dlg = _zeige(app, GRUENDE[name])
    try:
        assert dlg.width() >= MIN_BREITE
        _pruefe_nichts_abgeschnitten(dlg)
        if langer_pfad:
            assert dlg.ort_pfad.text() != dlg.ort_pfad.toolTip()
            assert "…" in dlg.ort_pfad.text()
        assert dlg.ort_pfad.toolTip() == str(lizenz.standard_pfad())
        frei = dlg._verfuegbar()
        assert dlg.width() <= frei.width() and dlg.height() <= frei.height()
    finally:
        dlg.close()
        dlg.deleteLater()


def test_erklaerung_hat_bei_540_px_platz_fuer_beide_zeilen(app):
    """Genau der Fall der Sichtprobe: 540 px breit, die Erklaerung umbricht."""
    dlg = _zeige(app, GRUENDE["fehlt"], breite=MIN_BREITE)
    try:
        assert dlg.width() == MIN_BREITE
        lab = dlg.erklaerung
        einzeilig = lab.fontMetrics().lineSpacing()
        assert lab.heightForWidth(lab.width()) > einzeilig     # umbricht wirklich
        assert lab.height() >= lab.heightForWidth(lab.width())
        _pruefe_nichts_abgeschnitten(dlg)
    finally:
        dlg.close()
        dlg.deleteLater()


def test_hoehe_folgt_neuem_text_und_neuer_breite(app):
    dlg = _zeige(app, GRUENDE["fehlt"])
    try:
        h0 = dlg.height()
        dlg.grund.setText(LANGER_GRUND)
        dlg._passe_hoehe_an()
        app.processEvents()
        assert dlg.height() > h0
        _pruefe_nichts_abgeschnitten(dlg)
        dlg.resize(700, dlg.height())
        app.processEvents()
        app.processEvents()
        _pruefe_nichts_abgeschnitten(dlg)
    finally:
        dlg.close()
        dlg.deleteLater()


def test_abgelehnte_datei_laesst_den_dialog_wachsen(app, tmp_path):
    datei = tmp_path / ("eine_datei_mit_sehr_langem_namen_" * 3 + ".lic")
    datei.write_text("das ist keine Lizenz", encoding="utf-8")
    dlg = _zeige(app, GRUENDE["fehlt"])
    try:
        assert dlg.uebernimm(str(datei)) is False
        app.processEvents()
        app.processEvents()
        assert dlg.width() == MIN_BREITE      # langer Name drueckt nicht breit
        assert ".lic" in dlg.grund.text()
        _pruefe_nichts_abgeschnitten(dlg)
    finally:
        dlg.close()
        dlg.deleteLater()


def test_nie_groesser_als_der_bildschirm(app, monkeypatch):
    """Kleiner Bildschirm + langer Text: der Dialog bleibt im Bildschirm, der
    Text wird rollbar, die Knoepfe bleiben sichtbar."""
    monkeypatch.setattr(LizenzDialog, "_verfuegbar",
                        lambda self: QSize(480, 260))
    monkeypatch.setattr(lizenz, "app_data_dir", lambda: LANGER_ORDNER)
    dlg = _zeige(app, GRUENDE["unbekanntes_format"])
    try:
        assert dlg.width() <= 480 and dlg.height() <= 260
        assert dlg.bereich.verticalScrollBar().maximum() > 0    # rollbar
        for knopf in dlg.findChildren(QPushButton):
            assert knopf.isVisible()
            assert dlg.rect().contains(knopf.geometry()), knopf.text()
        # In der Breite passt weiterhin alles (kein waagerechtes Abschneiden).
        for lab in dlg.inhalt.findChildren(QLabel):
            assert lab.width() <= dlg.bereich.viewport().width()
    finally:
        dlg.close()
        dlg.deleteLater()
