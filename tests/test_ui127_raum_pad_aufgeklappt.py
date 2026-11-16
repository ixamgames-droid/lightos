"""UI-127 (Teil B): Raum-Pad, Ansicht „Aufgeklappt" (Boden + Waende als Ziele).

Abnahme laut Auftrag:

* Raumpunkt je Flaeche exakt (alle 5 Flaechen, Ecken, ausserhalb begrenzt).
* Stetigkeit an den Klappkanten (Boden <-> Wand: gleicher Raumpunkt, kein
  Sprung) — rechnerisch und beim Ziehen im Widget.
* Werte = ``aim_pan_tilt`` fuer Wandpunkte.
* Zielhoehe wirkt nur fuer den Boden, bei Wandziel ausgegraut.
* Kopf, der das Ziel nicht erreicht, wird markiert statt still begrenzt.
* Ansicht speichern/laden (auch ueber eine echte .lshow), Alt-Pad laedt als
  Draufsicht.
* Abgewaehlte Wand ist nicht antippbar.

Teilt die Wegwerf-Show (Fixture ``st``) mit ``test_ui127_raum_pad.py``.
"""
from __future__ import annotations

import json
import math
import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QPointF                   # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox                # noqa: E402

import src.core.app_state as A                                       # noqa: E402
from src.core.database.models import PatchedFixture                  # noqa: E402
from src.core.stage import raum_pad as RP                            # noqa: E402
from src.core.stage.aim import (aim_erreichbar, aim_pan_tilt,        # noqa: E402
                                aim_pan_tilt_16)
from src.core.stage.einmessen import aim_kw                          # noqa: E402
from src.ui import touch_keyboard                                    # noqa: E402
from src.ui.virtualconsole.vc_raumpad import (AUFGEKLAPPT,           # noqa: E402
                                              DRAUFSICHT, VCRaumPad)

# Fixture und Helfer aus Teil A (nur Nicht-Test-Namen importieren, sonst
# sammelt pytest die Tests von dort ein zweites Mal ein).
from test_ui127_raum_pad import (KANAELE, POS, ROT, _ch, _klick,     # noqa: E402,F401
                                 _maus, _pad, st)

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()

RAUM = RP.RaumMasse(-6.0, 6.0, -5.0, 7.0, 5.0)     # 12 x 12 m, 5 m hoch


def _auf(waende=RP.WAENDE):
    return RP.Aufklappung(RAUM, tuple(waende))


def _nah(p, q, tol=1e-9):
    return all(abs(a - b) <= tol for a, b in zip(p, q))


# ── Rechenteil ──────────────────────────────────────────────────────────────

def test_abwicklung_massstabsgetreu():
    auf = _auf()
    assert auf.groesse == (5 + 12 + 5, 5 + 12 + 5)
    r = auf.rechtecke()
    assert r[RP.BODEN] == (5, 5, 17, 17)
    assert r[RP.RUECKWAND] == (5, 0, 17, 5)
    assert r[RP.VORN] == (5, 17, 17, 22)
    assert r[RP.LINKS] == (0, 5, 5, 17)
    assert r[RP.RECHTS] == (17, 5, 22, 17)
    # ohne Rueckwand/links rutscht der Boden an den Rand
    klein = _auf((RP.RECHTS,))
    assert klein.groesse == (12 + 5, 12)
    assert klein.rechtecke()[RP.BODEN] == (0, 0, 12, 12)
    assert set(klein.rechtecke()) == {RP.BODEN, RP.RECHTS}


@pytest.mark.parametrize("ab, erwartet", [
    # Boden: x/z aus der Lage, Hoehe = Zielhoehe
    ((8.0, 9.0), (RP.BODEN, (-3.0, 1.2, -1.0))),
    # Rueckwand: x aus der Waagerechten, Hoehe = Abstand zur Klappkante (b=5)
    ((8.0, 3.0), (RP.RUECKWAND, (-3.0, 2.0, -5.0))),
    # Wand vorn (Publikum): Klappkante b=17
    ((10.0, 18.5), (RP.VORN, (-1.0, 1.5, 7.0))),
    # Wand links: Klappkante a=5, z laeuft mit
    ((2.5, 11.0), (RP.LINKS, (-6.0, 2.5, 1.0))),
    # Wand rechts: Klappkante a=17
    ((21.0, 5.0), (RP.RECHTS, (6.0, 4.0, -5.0))),
    # Ecken des Bodens = Fusspunkte der Raumecken (Boden hat Vorrang)
    ((5.0, 5.0), (RP.BODEN, (-6.0, 1.2, -5.0))),
    ((17.0, 17.0), (RP.BODEN, (6.0, 1.2, 7.0))),
    # obere Ecken der Waende = obere Raumecken
    ((5.0, 0.0), (RP.RUECKWAND, (-6.0, 5.0, -5.0))),
    ((17.0, 22.0), (RP.VORN, (6.0, 5.0, 7.0))),
    ((0.0, 17.0), (RP.LINKS, (-6.0, 5.0, 7.0))),
    ((22.0, 5.0), (RP.RECHTS, (6.0, 5.0, -5.0))),
    # ausserhalb: auf die naechste Flaeche begrenzt
    ((100.0, 8.0), (RP.RECHTS, (6.0, 5.0, -2.0))),
    ((8.0, -40.0), (RP.RUECKWAND, (-3.0, 5.0, -5.0))),
    # leeres Eck-Viertel: gleich weit von Rueckwand und links -> Rueckwand,
    # der Punkt ist aber ohnehin derselbe (obere hintere linke Raumecke)
    ((0.0, 0.0), (RP.RUECKWAND, (-6.0, 5.0, -5.0))),
    ((1.0, 4.0), (RP.LINKS, (-6.0, 4.0, -5.0))),
    ((4.0, 1.0), (RP.RUECKWAND, (-6.0, 4.0, -5.0))),
])
def test_raumpunkt_je_flaeche_exakt(ab, erwartet):
    name, punkt = _auf().raumpunkt(*ab, zielhoehe=1.2)
    assert name == erwartet[0]
    assert _nah(punkt, erwartet[1]), punkt


def test_abwicklung_ist_umkehrung():
    auf = _auf()
    for ab in [(8.0, 9.0), (8.0, 3.0), (10.0, 18.5), (2.5, 11.0), (21.0, 7.0)]:
        name, punkt = auf.raumpunkt(*ab)
        assert _nah(auf.abwicklung(name, punkt), ab)


@pytest.mark.parametrize("innen, aussen", [
    ((9.0, 5.0 + 1e-6), (9.0, 5.0 - 1e-6)),     # Boden | Rueckwand
    ((9.0, 17.0 - 1e-6), (9.0, 17.0 + 1e-6)),   # Boden | vorn
    ((5.0 + 1e-6, 9.0), (5.0 - 1e-6, 9.0)),     # Boden | links
    ((17.0 - 1e-6, 9.0), (17.0 + 1e-6, 9.0)),   # Boden | rechts
])
def test_stetig_an_den_klappkanten(innen, aussen):
    auf = _auf()
    n1, p1 = auf.raumpunkt(*innen)
    n2, p2 = auf.raumpunkt(*aussen)
    assert n1 == RP.BODEN and n2 != RP.BODEN
    assert math.dist(p1, p2) < 1e-5, (p1, p2)


def test_abgewaehlte_wand_ist_keine_flaeche():
    auf = _auf((RP.LINKS, RP.RECHTS, RP.VORN))
    # oberhalb des Bodens (wo die Rueckwand waere) -> auf den Boden begrenzt
    name, punkt = auf.raumpunkt(8.0, -3.0)
    assert name == RP.BODEN and punkt[2] == pytest.approx(RAUM.z0)
    assert RP.waende_normal(["vorn", "quatsch", "links"]) == (RP.LINKS, RP.VORN)


def test_aim_erreichbar_wie_aim_pan_tilt():
    kopf = (0.0, 5.0, 0.0)                    # haengend, Ruhelage nach unten
    unten, oben = (2.0, 0.0, -3.0), (2.0, 8.0, -3.0)
    assert aim_erreichbar(kopf, unten, tilt_range_deg=180)
    assert not aim_erreichbar(kopf, oben, tilt_range_deg=180)
    assert aim_erreichbar(kopf, oben, tilt_range_deg=270)
    # aim_pan_tilt begrenzt still auf den Anschlag — genau das soll die
    # Abfrage aufdecken
    assert aim_pan_tilt(kopf, oben, tilt_range_deg=180)[1] in (0, 255)


# ── Widget ──────────────────────────────────────────────────────────────────

def _auf_pad(**kw):
    p = _pad(**kw)
    p.set_ansicht(AUFGEKLAPPT)
    QApplication.processEvents()
    return p


def _px_ab(p, a, b):
    rahmen, s = p._abw_abbildung()
    q = p._ab_zu_px(a, b, rahmen, s)
    return QPoint(round(q.x()), round(q.y()))


def _px_wand(p, flaeche, x, y, z):
    auf = p.aufklappung()
    return _px_ab(p, *auf.abwicklung(flaeche, (x, y, z)))


def _f(state, fid):
    return next(f for f in state.get_patched_fixtures() if f.fid == fid)


def test_tipp_auf_rueckwand_zielt_auf_die_wand(st):
    p = _auf_pad(w=360, h=360)
    raum = p._raum()
    p.hoehe_setzen(1.5)                         # gilt nur fuer den Boden
    _klick(p, _px_wand(p, RP.RUECKWAND, 0.5, 2.0, raum.z0))
    assert p.flaeche == RP.RUECKWAND and p.aktiv
    ziel = p.ziel_3d()
    assert ziel[2] == pytest.approx(raum.z0)
    assert ziel[1] == pytest.approx(2.0, abs=0.15), "Hoehe aus dem Abstand zur Kante"
    assert ziel[0] == pytest.approx(0.5, abs=0.15)
    f1, f2 = _f(st, 1), _f(st, 2)
    a16 = aim_pan_tilt_16(POS[1], ziel, ROT[1], **aim_kw(f1))
    assert (st.get_programmer_value(1, "pan"), st.get_programmer_value(1, "pan_fine")) == \
        (a16[0] >> 8, a16[0] & 0xFF)
    assert (st.get_programmer_value(1, "tilt"), st.get_programmer_value(1, "tilt_fine")) == \
        (a16[1] >> 8, a16[1] & 0xFF)
    assert (st.get_programmer_value(2, "pan"), st.get_programmer_value(2, "tilt")) == \
        aim_pan_tilt(POS[2], ziel, ROT[2], **aim_kw(f2))
    assert "Rückwand" in p.koordinaten_text()


@pytest.mark.parametrize("flaeche", [RP.LINKS, RP.RECHTS, RP.VORN])
def test_jede_wand_liefert_aim_werte(st, flaeche):
    p = _auf_pad(w=360, h=360)
    raum = p._raum()
    punkt = {RP.LINKS: (raum.x0, 1.0, 0.0), RP.RECHTS: (raum.x1, 3.0, 1.0),
             RP.VORN: (1.0, 2.5, raum.z1)}[flaeche]
    _klick(p, _px_wand(p, flaeche, *punkt))
    assert p.flaeche == flaeche
    ziel = p.ziel_3d()
    assert math.dist(ziel, punkt) < 0.25
    assert (st.get_programmer_value(2, "pan"), st.get_programmer_value(2, "tilt")) == \
        aim_pan_tilt(POS[2], ziel, ROT[2], **aim_kw(_f(st, 2)))


def test_boden_wie_draufsicht(st):
    p = _auf_pad(w=360, h=360)
    p.hoehe_setzen(1.0)
    auf = p.aufklappung()
    _klick(p, _px_ab(p, *auf.abwicklung(RP.BODEN, (1.0, 0.0, 2.0))))
    assert p.flaeche == RP.BODEN
    ziel = p.ziel_3d()
    assert ziel[1] == 1.0
    assert (ziel[0], ziel[2]) == pytest.approx((1.0, 2.0), abs=0.15)
    assert (st.get_programmer_value(2, "pan"), st.get_programmer_value(2, "tilt")) == \
        aim_pan_tilt(POS[2], ziel, ROT[2], **aim_kw(_f(st, 2)))


def test_ziehen_ueber_die_klappkante_ohne_sprung(st):
    p = _auf_pad(w=400, h=400)
    raum = p._raum()
    auf = p.aufklappung()
    start = _px_ab(p, *auf.abwicklung(RP.BODEN, (0.0, 0.0, raum.z0 + 1.0)))
    ende = _px_wand(p, RP.RUECKWAND, 0.0, 1.0, raum.z0)
    _maus(p, QEvent.Type.MouseButtonPress, start)
    punkte, flaechen = [p.ziel_3d()], [p.flaeche]
    schritte = 40
    for i in range(1, schritte + 1):
        _maus(p, QEvent.Type.MouseMove, start + (ende - start) * (i / schritte))
        punkte.append(p.ziel_3d())
        flaechen.append(p.flaeche)
    _maus(p, QEvent.Type.MouseButtonRelease, ende)
    assert flaechen[0] == RP.BODEN and flaechen[-1] == RP.RUECKWAND
    _rahmen, s = p._abw_abbildung()
    schritt_m = (abs(ende.y() - start.y()) / schritte) / s
    for a, b in zip(punkte, punkte[1:]):
        # nie mehr als ein Zugschritt (plus Pixel-/Rundungsrest) — kein Sprung
        assert math.dist(a, b) <= schritt_m + 2.0 / s + 0.02, (a, b)


def test_ausserhalb_wird_auf_naechste_flaeche_begrenzt(st):
    p = _auf_pad(w=360, h=360)
    raum = p._raum()
    auf = p.aufklappung()
    start = _px_ab(p, *auf.abwicklung(RP.BODEN, (0.0, 0.0, 0.0)))
    _maus(p, QEvent.Type.MouseButtonPress, start)
    _maus(p, QEvent.Type.MouseMove, QPoint(p.width() + 200, start.y()))
    _maus(p, QEvent.Type.MouseButtonRelease, QPoint(p.width() + 200, start.y()))
    assert p.flaeche == RP.RECHTS
    assert p.ziel_3d()[0] == pytest.approx(raum.x1)
    assert p.ziel_3d()[1] == pytest.approx(raum.hoehe)


def test_zielhoehe_bei_wandziel_ausgegraut(st):
    p = _auf_pad(w=360, h=360)
    raum = p._raum()
    p.hoehe_setzen(1.0)
    _klick(p, _px_wand(p, RP.RUECKWAND, 0.0, 3.0, raum.z0))
    vorher = p.ziel_3d()
    hz = p._zonen()["hoehe"]
    _klick(p, QPoint(hz.right() - 10, hz.center().y()))
    assert p.hoehe == 1.0, "Regler ist bei Wandziel gesperrt"
    assert p.ziel_3d() == vorher
    p.grab()                                    # malt „Wand x,x m"


def test_abgewaehlte_wand_nicht_antippbar(st):
    p = _auf_pad(w=360, h=360)
    auf_voll = p.aufklappung()
    wand_px = _px_wand(p, RP.RUECKWAND, 0.0, 2.5, p._raum().z0)
    p.set_waende([RP.LINKS, RP.RECHTS, RP.VORN])
    boden = p.flaeche_px(RP.BODEN)
    oben = QPoint(round(boden.center().x()), round(boden.top()) - 6)
    for pos in (oben, wand_px):
        if not boden.contains(QPointF(pos)):
            _klick(p, pos)
            assert p.flaeche != RP.RUECKWAND
    assert p.flaeche_px(RP.RUECKWAND) is None
    assert RP.RUECKWAND in auf_voll.flaechen
    assert st.get_programmer_value(2, "pan") is None, "kein Ziel gesetzt"


def test_unerreichbarer_kopf_wird_markiert(st):
    KANAELE[7] = [_ch("pan", 1, 128), _ch("tilt", 2, 128)]
    try:
        st.add_fixture(PatchedFixture(
            fid=7, label="Kopf 7", fixture_profile_id=1, mode_name="Std",
            universe=1, address=100, channel_count=2, fixture_type="moving_head",
            tilt_range_deg=180), undoable=False)
        st.visualizer_positions[7] = (0.0, 3.0, 0.0)
        st.visualizer_rotations[7] = (0.0, 0.0, 0.0)
        p = _auf_pad(fids=(2, 7), w=360, h=360)
        raum = p._raum()
        _klick(p, _px_wand(p, RP.RUECKWAND, 0.0, raum.hoehe - 0.5, raum.z0))
        f7 = _f(st, 7)
        assert not aim_erreichbar(POS.get(7, (0.0, 3.0, 0.0)), p.ziel_3d(),
                                  **aim_kw(f7))
        assert 7 in p.unerreichbar()
        assert 2 not in p.unerreichbar()
        p.grab()
        assert "7" in p.toolTip() and "Bewegungsbereich" in p.toolTip()
        # der Wert selbst bleibt der von aim_pan_tilt (dokumentiert begrenzt)
        assert (st.get_programmer_value(7, "pan"), st.get_programmer_value(7, "tilt")) == \
            aim_pan_tilt((0.0, 3.0, 0.0), p.ziel_3d(), (0, 0, 0), **aim_kw(f7))
    finally:
        KANAELE.pop(7, None)


def test_lock_und_an_aus_gelten_unveraendert(st):
    vorher = st.universes[1].get_all()
    p = _auf_pad(w=360, h=360)
    raum = p._raum()
    p.position_lock = False
    pos = _px_wand(p, RP.LINKS, raum.x0, 2.0, 0.0)
    _maus(p, QEvent.Type.MouseButtonPress, pos)
    assert p.aktiv and st.get_programmer_value(2, "pan") is not None
    _maus(p, QEvent.Type.MouseButtonRelease, pos)
    assert not p.aktiv and st.get_programmer_value(2, "pan") is None
    assert st.universes[1].get_all() == vorher


def test_finger_tipp_auf_wand(st):
    p = _auf_pad(w=360, h=360)
    pos = _px_wand(p, RP.VORN, 0.0, 2.0, p._raum().z1)
    QTest.touchEvent(p, _DEV).press(0, pos, p).commit()
    QApplication.processEvents()
    QTest.touchEvent(p, _DEV).release(0, pos, p).commit()
    QApplication.processEvents()
    assert p.aktiv and p.flaeche == RP.VORN


def test_touch_modus_44px_auch_aufgeklappt(st):
    touch_keyboard.setze_touch_modus(True)
    p = _auf_pad(w=360, h=360)
    z = p._zonen()
    for name in ("an", "lock", "hoehe"):
        assert z[name].height() >= 44 and z[name].width() >= 44, name
    p.grab()


def test_inspector_waehlt_ansicht_und_waende(st):
    p = _pad()
    body = p.build_inspector_body()
    cb = body.findChild(QComboBox, "raumpad_ansicht")
    assert cb.currentText() == DRAUFSICHT
    cb.setCurrentText(AUFGEKLAPPT)
    assert p.ansicht == AUFGEKLAPPT
    from PySide6.QtWidgets import QCheckBox
    links = body.findChild(QCheckBox, "raumpad_wand_links")
    assert links.isChecked() and links.isEnabled()
    links.setChecked(False)
    assert RP.LINKS not in p.waende and RP.RUECKWAND in p.waende
    body.deleteLater()


# ── Speichern / Laden ───────────────────────────────────────────────────────

def test_ansicht_rundweg_und_alt_pad(st):
    p = _auf_pad()
    p.set_waende([RP.RUECKWAND, RP.VORN])
    raum = p._raum()
    _klick(p, _px_wand(p, RP.RUECKWAND, 0.0, 2.0, raum.z0))
    d = json.loads(json.dumps(p.to_dict()))
    assert d["ansicht"] == AUFGEKLAPPT and d["waende"] == ["rueckwand", "vorn"]
    q = VCRaumPad()
    q.apply_dict(d)
    assert (q.ansicht, q.waende, q.flaeche) == (AUFGEKLAPPT, (RP.RUECKWAND, RP.VORN),
                                                RP.RUECKWAND)
    assert q.ziel_3d() == pytest.approx(p.ziel_3d())
    assert q.aktiv is False
    # Pad aus Teil A (ohne die neuen Schluessel) -> Draufsicht, alle Waende
    alt = {k: v for k, v in d.items()
           if k not in ("ansicht", "waende", "flaeche", "wand_hoehe")}
    r = VCRaumPad()
    r.apply_dict(alt)
    assert (r.ansicht, r.waende, r.flaeche) == (DRAUFSICHT, tuple(RP.WAENDE), RP.BODEN)
    # Unsinn faellt auf die Vorgabe zurueck
    r.apply_dict(dict(alt, ansicht="Seitlich", flaeche="decke"))
    assert (r.ansicht, r.flaeche) == (DRAUFSICHT, RP.BODEN)
    q.deleteLater(); r.deleteLater()


def test_ansicht_in_echter_show_datei(monkeypatch):
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: [])
    from src.core.show import show_file as SF
    from src.core.app_state import get_state
    SF.reset_show()
    with tempfile.TemporaryDirectory(prefix="lightos_ui127b_") as tmp:
        pad = VCRaumPad("Raum")
        pad.set_ansicht(AUFGEKLAPPT)
        pad.set_waende([RP.LINKS])
        pad.ziel, pad.flaeche, pad.wand_hoehe = (-3.0, 1.0), RP.LINKS, 2.25
        # Alt-Pad aus Teil A daneben, im Test erzeugt
        alt = {"type": "VCRaumPad", "caption": "Alt", "x": 10, "y": 300, "w": 260,
               "h": 240, "fixture_ids": [1], "gruppen": [], "ziel": [0.5, 1.0],
               "hoehe": 0.0, "position_lock": True}
        pfad = os.path.join(tmp, "b.lshow")
        get_state()._vc_layout = {"widgets": [pad.to_dict(), alt]}
        SF.save_show(pfad)
        ok, msg = SF.load_show(pfad)
        assert ok, msg
        geladen = get_state()._vc_layout["widgets"]
        q, r = VCRaumPad(), VCRaumPad()
        q.apply_dict(geladen[0])
        r.apply_dict(geladen[1])
        assert (q.ansicht, q.waende, q.flaeche, q.wand_hoehe) == \
            (AUFGEKLAPPT, (RP.LINKS,), RP.LINKS, 2.25)
        assert (r.ansicht, r.flaeche, r.ziel) == (DRAUFSICHT, RP.BODEN, (0.5, 1.0))
        q.deleteLater(); r.deleteLater(); pad.deleteLater()
    SF.reset_show()
