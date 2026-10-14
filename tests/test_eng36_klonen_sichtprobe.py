"""ENG-36: zwei Befunde der Sichtprobe am Dialog „Klonen" — Darstellung.

(a) Die Zählerzeile war bei gleichem Gerätetyp abgeschnitten („… · 26 bleibt,").
(b) Zwei Häkchen hießen „Matrix _Bewegungs-Effekte" und „Snaps _Szenen" — Qt
    hat das „&" als Tastenkürzel verschluckt.

Geprüft wird ohne Bildschirm: Größen und Texte der Widgets, kein echtes Bild.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (QAbstractButton, QApplication,       # noqa: E402
                               QGroupBox, QLabel, QStyleOptionButton)

from _eng36_show import RGB, RGBW, show_fixture                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets             # noqa: E402
from src.core.engine import palette as palette_mod                   # noqa: E402
from src.core.engine import snap_library as snap_mod                 # noqa: E402
from src.core.show import klonen as K                                # noqa: E402
from src.core.show import show_file                                  # noqa: E402
from src.ui.widgets import klonen_dialog as D                        # noqa: E402

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _keine_fenster_uebrig():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


@pytest.fixture
def show(tmp_path, monkeypatch):
    for sh in show_fixture(tmp_path, monkeypatch):
        # Der Show-Fingerabdruck liest Snaps und Paletten über die
        # Verwalter der App — hier sind es die der Test-Show.
        monkeypatch.setattr(snap_mod, "get_snap_library", lambda: sh.snaps)
        monkeypatch.setattr(palette_mod, "get_palette_manager",
                            lambda: sh.paletten)
        monkeypatch.setattr(show_file, "_gemerkter_stand", None)
        yield sh


class _Umgebung(D.Umgebung):
    def __init__(self, state):
        super().__init__(None, state)
        self.gesichert = 0

    def sichern(self):
        self.gesichert += 1
        return "sicherung.lshow"


def _dialog(show, quellen, ziele):
    umgebung = _Umgebung(show.state)
    dlg = D.KlonenDialog(show.state, quellen, ziele, umgebung=umgebung,
                         snap_library=show.snaps,
                         palette_manager=show.paletten)
    return dlg, umgebung


def _zeige(dlg):
    """In der Mindestgröße zeigen — so klein, wie der Dialog werden kann."""
    dlg.resize(dlg.minimumSize())
    dlg.show()
    _app.processEvents()
    _app.processEvents()


def _gleiche_show(show, mit_ziel=True):
    """Zwei gleiche Geräte, die an vielen Stellen schon dasselbe tun."""
    show.patch(1, RGB, "EVENTPARIP65 1")
    show.patch(2, RGB, "EVENTPARIP65 2")
    rot = {"intensity": 200, "color_r": 255, "color_g": 0, "color_b": 0}
    for i in range(3):
        show.snaps.add_snap(f"Snap {i}", "", {
            1: dict(rot), **({2: dict(rot)} if mit_ziel else {})})
    for name in ("Hintergrund", "Party", "Alle Strobe"):
        show.gruppe(name, {"0,0": 1, **({"1,0": 2} if mit_ziel else {})})
    show.state.base_levels = {1: {"intensity": 255},
                              **({2: {"intensity": 255}} if mit_ziel else {})}
    return rot


def _pruefe_nichts_abgeschnitten(dlg):
    """Kein Text des Dialogs ist abgeschnitten: umbrechende Labels sind hoch
    genug für ihren Text bei der tatsächlichen Breite, alles andere ist
    mindestens so breit und hoch wie sein ``sizeHint``."""
    geprueft = 0
    for w in dlg.findChildren(QLabel) + dlg.findChildren(QAbstractButton):
        if not w.isVisible() or w.window() is not dlg:
            continue
        text = w.text()
        if not text:
            continue
        geprueft += 1
        if isinstance(w, QLabel) and w.wordWrap():
            brauch = w.heightForWidth(w.width())
            assert w.height() >= brauch, (text[:50], w.height(), brauch)
            assert w.width() >= w.minimumSizeHint().width(), text[:50]
        else:
            hint = w.sizeHint()
            assert w.width() >= hint.width(), (text[:50], w.width(), hint.width())
            assert w.height() >= hint.height(), (text[:50], w.height(), hint.height())
        oben_links = w.mapTo(dlg, w.rect().topLeft())
        unten_rechts = w.mapTo(dlg, w.rect().bottomRight())
        assert dlg.rect().contains(oben_links), text[:50]
        assert dlg.rect().contains(unten_rechts), text[:50]
    assert geprueft >= 15


# ── (a) nichts abgeschnitten ────────────────────────────────────────────────

@pytest.mark.parametrize("wie", ["hinzufuegen", "ersetzen", None])
def test_gleicher_typ_kein_text_abgeschnitten(show, wie):
    _gleiche_show(show)
    dlg, _u = _dialog(show, [1], [2])
    if wie == "hinzufuegen":
        dlg._hinzufuegen.setChecked(True)
    elif wie == "ersetzen":
        dlg._ersetzen.setChecked(True)
    _zeige(dlg)
    if wie:
        # Genau die Zeile der Sichtprobe: sie endet mit „bleibt, wie es ist".
        assert dlg._zaehler.text().endswith("bleibt, wie es ist")
    assert dlg._zaehler.wordWrap()
    _pruefe_nichts_abgeschnitten(dlg)


def test_zaehlerzeile_passt_auch_mit_grossen_zahlen(show):
    """Vierstellige Zähler machen die Zeile länger als die rechte Spalte —
    dann bricht sie um, statt abgeschnitten zu werden."""
    _gleiche_show(show)
    dlg, _u = _dialog(show, [1], [2])
    dlg._hinzufuegen.setChecked(True)
    _zeige(dlg)
    dlg._zaehler.setText(dlg._zaehler.text().replace(" unverändert", "888888 unverändert")
                         .replace(" übersetzt", "888888 übersetzt")
                         .replace(" fällt", "888888 fällt")
                         .replace(" bleibt", "888888 bleibt"))
    _app.processEvents()
    _app.processEvents()
    lab = dlg._zaehler
    assert lab.heightForWidth(lab.width()) > lab.fontMetrics().lineSpacing() * 2 - 2
    _pruefe_nichts_abgeschnitten(dlg)


def test_verschiedene_typen_kein_text_abgeschnitten(show):
    show.patch(1, RGB, "PAR links")
    show.patch(2, RGBW, "PAR neu mit einem ziemlich langen Namen")
    show.snaps.add_snap("Rot", "", {1: {"color_r": 255, "color_g": 0,
                                        "color_b": 0, "intensity": 200},
                                    2: {"dimmer": 7}})
    show.gruppe("Front", {"0,0": 1})
    for knopf in ("_hinzufuegen", "_ersetzen"):
        dlg, _u = _dialog(show, [1], [2])
        getattr(dlg, knopf).setChecked(True)
        _zeige(dlg)
        assert not dlg._typ_hinweis.isHidden()
        _pruefe_nichts_abgeschnitten(dlg)
        dlg.close()


# ── (b) Beschriftungen ──────────────────────────────────────────────────────

def _sichtbarer_text(knopf) -> str:
    """Was Qt wirklich zeichnet: Tastenkürzel-Zeichen herausgerechnet."""
    opt = QStyleOptionButton()
    knopf.initStyleOption(opt)
    roh = opt.text
    out, i = [], 0
    while i < len(roh):
        if roh[i] == "&":
            i += 1
            if i < len(roh):
                out.append(roh[i])      # „&&" → „&", „&x" → „x" (unterstrichen)
        else:
            out.append(roh[i])
        i += 1
    return "".join(out)


def test_haekchen_zeigen_das_und_zeichen(show):
    _gleiche_show(show)
    dlg, _u = _dialog(show, [1], [2])
    _zeige(dlg)
    sichtbar = {b: _sichtbarer_text(cb) for b, cb in dlg._haekchen.items()}
    assert sichtbar[K.BEREICH_EFFEKTE] == "Matrix & Bewegungs-Effekte"
    assert sichtbar[K.BEREICH_SNAPS] == "Snaps & Szenen"
    # Jedes Häkchen zeigt genau den Namen seines Bereichs …
    assert sichtbar == {b: K.BEREICH_TEXT[b] for b in K.BEREICHE}
    for cb in dlg._haekchen.values():
        # … und keines hat ein (versehentliches) Tastenkürzel.
        assert cb.shortcut().isEmpty(), cb.text()


def test_kein_knopf_des_dialogs_verschluckt_ein_und_zeichen(show):
    """Alle Knöpfe, Häkchen und Wahlknöpfe beider Dialoge: kein einzelnes „&",
    das Qt als Tastenkürzel deuten würde."""
    _gleiche_show(show)
    dlg, _u = _dialog(show, [1], [2])
    dlg._ersetzen.setChecked(True)
    auswahl = D.ZielAuswahlDialog(show.state, [1])
    for fenster in (dlg, auswahl):
        knoepfe = fenster.findChildren(QAbstractButton)
        assert knoepfe
        for k in knoepfe:
            assert "&" not in k.text().replace("&&", ""), k.text()
    for kasten in dlg.findChildren(QGroupBox):
        assert "&" not in kasten.title().replace("&&", ""), kasten.title()


def test_geraetename_mit_sonderzeichen_steht_woertlich_im_kopf(show):
    show.patch(1, RGB, "Bar & <b>Theke</b>")
    show.patch(2, RGB, "Ziel")
    dlg, _u = _dialog(show, [1], [2])
    assert "Bar &amp; &lt;b&gt;Theke&lt;/b&gt;" in dlg._kopf.text()
