"""UI-143: Raum-Pad aufgeklappt ohne ueberlappende Texte; Handy-Gruppen-Dialog
mit kurzem Kennzeichen und vollem Sperrgrund unter der Liste.

Befunde B2/B3 der Sichtprobe von Sitzung D (Windows x64, 100/125/150 %,
16.11.2026) — bei allen Skalierungen gleich, also Layout.

* B2: 10 Moving Heads in einer Reihe (1,6 m Abstand, gleiche Hoehe) bei
  260x240, 320x300 und 460x420 — kein Paar gesetzter Text-Rechtecke
  ueberlappt, kein Text ragt aus seiner Flaeche, keine Kopf-Kreise
  ueberlappen, die gemeinsame Hoehe steht einmal („10× 4,5 m"), die Hoehen
  stehen im Tooltip. Die Zielrechnung ist unveraendert.
* B3: Zeilen passen bei der Vorgabebreite samt Kennzeichen, Antippen (Finger
  und Maus) einer gesperrten Zeile zeigt den vollen Grund, gesperrte Zeilen
  bleiben nicht waehlbar (WEB-14: BLACKOUT & Co. nie in einer Gruppe).
"""
from __future__ import annotations

import itertools
import math
import os
import tempfile
from types import SimpleNamespace as NS

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QPoint, Qt                                # noqa: E402
from PySide6.QtGui import QFontMetrics                               # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget                  # noqa: E402

import src.core.app_state as A                                       # noqa: E402
from src.core.database.models import PatchedFixture                  # noqa: E402
from src.ui import touch_keyboard                                    # noqa: E402
from src.ui import ziehen_scrollen as zs                             # noqa: E402
from src.ui.virtualconsole import vc_fernbedienung                   # noqa: E402
from src.ui.virtualconsole.vc_handy_leiste import HandyGruppeDialog  # noqa: E402
from src.ui.virtualconsole.vc_raumpad import (AUFGEKLAPPT,           # noqa: E402
                                              DRAUFSICHT, VCRaumPad)
from src.ui.virtualconsole.vc_widget import VCWidget                 # noqa: E402

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()

N = 10
HOEHE = 4.5


def _ch(attr, num, default=0):
    return NS(attribute=attr, channel_number=num, default_value=default,
              highlight_value=255, ranges=[])


KANAELE = [_ch("pan", 1, 128), _ch("tilt", 2, 128), _ch("dimmer", 3)]


@pytest.fixture
def reihe(monkeypatch):
    """Wegwerf-Show: 10 Moving Heads in einer Reihe, 1,6 m Abstand, 4,5 m hoch."""
    zs.einrichten(_app).aktiv = True
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: list(KANAELE))
    state = A.AppState()
    fd, pfad = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    state.open_show(pfad)
    for i in range(N):
        fid = i + 1
        state.add_fixture(PatchedFixture(
            fid=fid, label=f"MH {fid}", fixture_profile_id=1, mode_name="Std",
            universe=1, address=1 + 3 * i, channel_count=3,
            fixture_type="moving_head"), undoable=False)
        state.visualizer_positions[fid] = (-7.2 + 1.6 * i, HOEHE, -2.0)
        state.visualizer_rotations[fid] = (0.0, 0.0, 0.0)
    monkeypatch.setattr(A, "get_state", lambda: state)
    alt_lock = VCWidget.input_locked
    alt_touch = touch_keyboard.is_touch_mode()
    yield state
    VCWidget.input_locked = alt_lock
    touch_keyboard.setze_touch_modus(alt_touch)
    destroy_all_top_level_widgets(_app)
    try:
        os.remove(pfad)
    except OSError:
        pass


def _pad(w, h, ansicht=AUFGEKLAPPT):
    p = VCRaumPad("Raum-Pad")
    p._fixture_ids = list(range(1, N + 1))
    p.set_ansicht(ansicht)
    p.resize(w, h)
    eltern = QWidget()
    eltern.resize(w + 40, h + 40)
    p.setParent(eltern)
    p.move(20, 20)
    eltern.show()
    p._traeger = eltern
    QApplication.processEvents()
    return p


def _pruefe_texte(p):
    texte = p.gezeichnete_texte()
    assert texte, "nichts gemalt"
    for art, r, flaeche, text in texte:
        assert flaeche.adjusted(-0.5, -0.5, 0.5, 0.5).contains(r), (art, text, r, flaeche)
        assert QRectFInWidget(p, r), (art, text, r)
    for (a1, r1, _f1, t1), (a2, r2, _f2, t2) in itertools.combinations(texte, 2):
        x = r1.intersected(r2)
        assert not (x.width() > 0.5 and x.height() > 0.5), ((a1, t1, r1), (a2, t2, r2))
    return texte


def QRectFInWidget(p, r):                                            # noqa: N802
    return (r.left() >= -0.5 and r.top() >= -0.5 and r.right() <= p.width() + 0.5
            and r.bottom() <= p.height() + 0.5)


def _kreise_frei(p):
    kreise = list(p.kopf_kreise().values())
    assert len(kreise) == N
    for (c1, r1), (c2, r2) in itertools.combinations(kreise, 2):
        assert math.hypot(c1.x() - c2.x(), c1.y() - c2.y()) >= r1 + r2, (c1, r1, c2, r2)


@pytest.mark.parametrize("w, h", [(260, 240), (320, 300), (460, 420)])
def test_aufgeklappt_reihe_ohne_ueberlappung(reihe, w, h, tmp_path):
    p = _pad(w, h)
    p.ziel_setzen(0.0, 0.0)                    # mit Koordinaten-Zeile
    bild = p.grab()
    bild.save(str(tmp_path / f"raumpad_{w}x{h}.png"))
    if os.environ.get("UI143_BILDER"):
        bild.save(os.path.join(os.environ["UI143_BILDER"], f"raumpad_{w}x{h}.png"))
    texte = _pruefe_texte(p)
    _kreise_frei(p)
    hoehen = [t for a, _r, _f, t in texte if a == "hoehe"]
    # gleiche Hoehe einer Reihe: hoechstens einmal beschriftet
    assert len(hoehen) <= 1, hoehen
    if hoehen:
        assert hoehen[0] == f"{N}× 4,5 m"
    # die Hoehe ist immer erreichbar — im Tooltip
    assert "Höhen: 4,5 m: 1, 2, 3" in p.toolTip()
    # Wandnamen nie abgeschnitten: entweder ganz, gekuerzt oder weg
    erlaubt = {"Boden", "Rückwand", "hinten", "Wand links", "links", "Wand rechts", "rechts",
               "Wand vorn", "vorn"}
    for a, _r, _f, t in texte:
        if a == "flaeche":
            assert t in erlaubt, t
    if (w, h) == (460, 420):
        assert hoehen == [f"{N}× 4,5 m"]
        assert {t for a, _r, _f, t in texte if a == "nummer"} == {str(i) for i in range(1, N + 1)}


def test_wandnamen_klein_gekuerzt(reihe):
    p = _pad(260, 240)
    p.grab()
    namen = {t for a, _r, _f, t in p.gezeichnete_texte() if a == "flaeche"}
    assert "Wand links" not in namen and "Wand rechts" not in namen
    assert {"links", "rechts"} <= namen, namen


def test_touch_modus_und_draufsicht_sauber(reihe):
    touch_keyboard.setze_touch_modus(True)
    for ansicht in (AUFGEKLAPPT, DRAUFSICHT):
        p = _pad(320, 300, ansicht)
        p.grab()
        _pruefe_texte(p)
        _kreise_frei(p)
        assert p._zonen()["an"].height() >= 44


def test_zielrechnung_unveraendert(reihe):
    """Nur das Zeichnen ist neu: Pixel <-> Abwicklung wie vorher."""
    p = _pad(320, 300)
    rahmen, s = p._abw_abbildung()
    feld = p._zonen()["feld"]
    bw, bh = p.aufklappung().groesse
    assert s == pytest.approx(min(feld.width() / bw, feld.height() / bh))
    a, b = p._px_zu_ab(QPoint(int(rahmen.center().x()), int(rahmen.center().y())))
    assert a == pytest.approx(bw / 2, abs=1 / s) and b == pytest.approx(bh / 2, abs=1 / s)


# ── B3: Handy-Gruppen-Dialog ────────────────────────────────────────────────

class VCButton:                         # gruppe_erlaubt sieht nur auf den Klassennamen
    def __init__(self, aktion):
        self.action = NS(value=aktion)


def _kandidaten():
    ok, grund = vc_fernbedienung.gruppe_erlaubt(VCButton("LaserEstop"))
    assert not ok and "gehören nie in eine Handy-Gruppe" in grund
    return [
        ("w1", "Rot  ·  Seite 1", ""),
        ("w2", "Laser NOT-AUS  ·  Seite 2", grund),
        ("w3", "Grün  ·  Seite 1", "schon in „Grundfarbe“"),
        ("w4", "Ein sehr langer Tastenname für die Bühne  ·  Seite 3 / Effekte", grund),
    ], grund


def _dialog():
    kand, grund = _kandidaten()
    dlg = HandyGruppeDialog("Gruppe 1", kand, ["w1"])
    dlg.show()                                   # Vorgabegroesse
    QApplication.processEvents()
    return dlg, grund


def test_zeilen_passen_mit_kennzeichen(reihe):
    dlg, grund = _dialog()
    try:
        fm = QFontMetrics(dlg.liste.font())
        texte = {}
        for i in range(dlg.liste.count()):
            it = dlg.liste.item(i)
            texte[it.data(Qt.ItemDataRole.UserRole)] = it.text()
            assert fm.horizontalAdvance(it.text()) <= dlg.textbreite(it), it.text()
        assert texte["w2"] == "Laser NOT-AUS  ·  Seite 2  — gesperrt"
        assert texte["w3"].endswith("— schon in „Grundfarbe“")
        assert texte["w4"].endswith("— gesperrt") and "…" in texte["w4"]
        assert grund not in "".join(texte.values())
        # Tooltip bleibt
        assert dlg.liste.item(1).toolTip() == grund
        # schmaler gezogen: Kennzeichen bleibt
        dlg.resize(260, dlg.height())
        QApplication.processEvents()
        for i in (1, 3):
            it = dlg.liste.item(i)
            assert it.text().endswith("— gesperrt"), it.text()
            assert fm.horizontalAdvance(it.text()) <= dlg.textbreite(it)
    finally:
        dlg.close()
        dlg.deleteLater()


def test_antippen_zeigt_vollen_grund(reihe):
    dlg, grund = _dialog()
    try:
        hinweis = dlg.grund_hinweis
        assert not hinweis.isVisible()
        vp = dlg.liste.viewport()
        it = dlg.liste.item(1)
        pos = dlg.liste.visualItemRect(it).center()
        QTest.touchEvent(vp, _DEV).press(0, pos, vp).commit()
        QTest.touchEvent(vp, _DEV).release(0, pos, vp).commit()
        QApplication.processEvents()
        assert hinweis.isVisible()
        assert grund in hinweis.text() and "Laser NOT-AUS" in hinweis.text()
        assert hinweis.wordWrap()
        dlg.layout().activate()                  # Hinweis sitzt UNTER der Liste
        assert hinweis.geometry().top() >= dlg.liste.geometry().bottom()
        # gesperrt bleibt nicht waehlbar
        assert not (it.flags() & Qt.ItemFlag.ItemIsUserCheckable)
        assert it.checkState() == Qt.CheckState.Unchecked
        # waehlbare Zeile mit der Maus: Hinweis weg, Haken geht
        it0 = dlg.liste.item(0)
        QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         dlg.liste.visualItemRect(it0).center())
        QApplication.processEvents()
        assert not hinweis.isVisible()
        # Maus auf gesperrte Zeile „schon in …"
        it2 = dlg.liste.item(2)
        QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         dlg.liste.visualItemRect(it2).center())
        QApplication.processEvents()
        assert hinweis.isVisible() and "schon in „Grundfarbe“" in hinweis.text()
        dlg.setze_auswahl(["w1", "w2", "w3", "w4"])
        assert dlg.ergebnis()[1] == ["w1"]
    finally:
        dlg.close()
        dlg.deleteLater()


def test_dialog_nicht_breiter(reihe):
    kand, _grund = _kandidaten()
    lang = [(k, t, g) for k, t, g in kand] + [
        ("w5", "X" * 40 + "  ·  Seite 9", "BLACKOUT, Laser-NOT-AUS, Alles stoppen und Laser "
         "scharf/unscharf gehören nie in eine Handy-Gruppe.")]
    dlg = HandyGruppeDialog("Gruppe 1", lang)
    try:
        dlg.show()
        QApplication.processEvents()
        dlg.grund_zeigen(dlg.liste.item(4))
        QApplication.processEvents()
        assert dlg.width() <= 640
        assert dlg.sizeHint().width() <= 640
    finally:
        dlg.close()
        dlg.deleteLater()
