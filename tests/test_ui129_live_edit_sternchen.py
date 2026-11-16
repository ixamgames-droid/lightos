"""UI-129: Sternchen an VC-Tasten und -Fadern, deren Effekt live bearbeitet ist.

Wunsch des Projektinhabers (15.11.2026): Wurde ein Effekt live veraendert, zeigt
jede Taste und jeder Fader, der genau fuer diesen Effekt zustaendig ist, ein
kleines Sternchen in einer oberen Ecke. Weg ist es bei „Reset Live", bei der
Uebernahme als neuer Stand/Preset und beim Laden einer Show. Reine
Bearbeitungs-Widgets (Edit-Slot ohne eigene Funktion) zeigen nichts; gespeichert
wird nichts.
"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QRect                     # noqa: E402
from PySide6.QtGui import QColor                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget                  # noqa: E402

from src.core.engine import effect_live                              # noqa: E402
from src.core.engine.function_manager import get_function_manager    # noqa: E402
from src.ui.virtualconsole.vc_button import ButtonAction, VCButton   # noqa: E402
from src.ui.virtualconsole.vc_encoder import VCEncoder               # noqa: E402
from src.ui.virtualconsole.vc_slider import SliderMode, VCSlider     # noqa: E402
from src.ui.widgets import live_stern                                # noqa: E402

_app = QApplication.instance() or QApplication([])

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402


@pytest.fixture
def fm():
    m = get_function_manager()
    m.stop_all()
    vorher = {f.id for f in m.all()}
    effect_live.clear_live_overrides()
    effect_live.clear_edit_targets()
    yield m
    effect_live.clear_live_overrides()
    effect_live.clear_edit_targets()
    destroy_all_top_level_widgets(_app)
    m.stop_all()
    for f in list(m.all()):
        if f.id not in vorher:
            m.remove(f.id)


def _matrix(fm, name="Mtx"):
    m = fm.new_rgb_matrix(name)
    m.snapshot_preset()            # wie nach dem Laden: Basis fuer „Reset Live"
    return m


def _taste(fid, action=ButtonAction.FUNCTION_TOGGLE, caption="Pad", **kw):
    b = VCButton(caption)
    b.action = action
    b.function_id = fid
    for k, v in kw.items():
        setattr(b, k, v)
    b.resize(72, 72)
    return b


def _fader(fid, mode=SliderMode.EFFECT_SPEED, **kw):
    s = VCSlider("Fader")
    s.mode = mode
    s.function_id = fid
    for k, v in kw.items():
        setattr(s, k, v)
    s.resize(60, 200)
    return s


def _ist_gelb(c: QColor) -> bool:
    return c.red() > 200 and c.green() > 170 and c.blue() < 90


def _gelbe_pixel(w, rect: QRect | None = None) -> int:
    img = w.grab().toImage()
    r = rect or QRect(0, 0, img.width(), img.height())
    n = 0
    for x in range(max(0, r.left()), min(img.width(), r.right() + 1)):
        for y in range(max(0, r.top()), min(img.height(), r.bottom() + 1)):
            if _ist_gelb(img.pixelColor(x, y)):
                n += 1
    return n


# ── Erkennung (effect_live) ─────────────────────────────────────────────────

def test_erkennung_alle_typen(fm):
    """RGB-Matrix, EFX, Chaser, Sequence: Live-Aenderung -> erkannt; Werte von
    Hand zurueckgedreht -> nicht mehr."""
    m = _matrix(fm)
    e = fm.new_efx("Efx")
    c = fm.new_chaser("Ch")
    s = fm.new_sequence("Seq")
    for f in (m, e, c, s):
        assert not effect_live.ist_live_editiert(f.id)
    for f in (m, e, c, s):
        alt = effect_live.get_param("speed", f.id)
        assert effect_live.set_param("speed", float(alt) * 0.5 + 0.1, f.id)
        assert effect_live.ist_live_editiert(f.id), type(f).__name__
        assert f.id in effect_live.live_editiert_ids()
        effect_live.set_param("speed", alt, f.id)
        assert not effect_live.ist_live_editiert(f.id), type(f).__name__
    assert effect_live.live_editiert_ids() == frozenset()


def test_nur_angepinnt_zaehlt_nicht(fm):
    """begin_live_edit (Live-Edit-Panel beim Drop) ohne Aenderung -> kein Stern."""
    m = _matrix(fm)
    effect_live.begin_live_edit(m.id)
    assert not effect_live.ist_live_editiert(m.id)
    assert not effect_live.ist_live_editiert(None)


def test_laufender_effekt_ohne_aenderung_bleibt_ohne_stern(fm):
    """Laufzeitfelder (Phase, Schritt) zaehlen nicht als Live-Aenderung."""
    from src.core.dmx.universe import Universe
    m = _matrix(fm)
    e = fm.new_efx("Efx")
    for f in (m, e):
        effect_live.begin_live_edit(f.id)
        fm.start(f.id)
    for _ in range(30):
        fm.tick({1: Universe(1)}, [], 0.05)
    assert effect_live.live_editiert_ids() == frozenset()


# ── Tasten / Fader ──────────────────────────────────────────────────────────

def test_taste_und_fader_zeigen_stern(fm):
    m = _matrix(fm)
    andere = _matrix(fm, "Andere")
    t = _taste(m.id)
    f = _fader(m.id)
    enc = VCEncoder("Enc")
    enc.function_id = m.id
    t_andere = _taste(andere.id)
    for w in (t, f, enc, t_andere):
        assert not w.live_stern_sichtbar()
    effect_live.set_param("speed", 7.5, m.id)
    assert t.live_stern_sichtbar()
    assert f.live_stern_sichtbar()
    assert enc.live_stern_sichtbar()
    assert not t_andere.live_stern_sichtbar()


def test_mehrere_widgets_auf_derselben_funktion(fm):
    m = _matrix(fm)
    tasten = [_taste(m.id, caption=f"P{i}") for i in range(3)]
    tasten.append(_taste(m.id, action=ButtonAction.FUNCTION_FLASH))
    tasten.append(_taste(m.id, action=ButtonAction.EFFECT_ACTION,
                         effect_action_key="next_color"))
    fader = [_fader(m.id, mode=md) for md in (SliderMode.EFFECT_SPEED,
                                               SliderMode.EFFECT_INTENSITY,
                                               SliderMode.EFFECT_PARAM)]
    effect_live.do_action("next_algorithm", m.id)
    for w in tasten + fader:
        assert w.live_stern_sichtbar(), w.caption


def test_edit_slot_widgets_ohne_eigene_funktion_zeigen_nichts(fm):
    """Aktionstaste/Fader ueber Edit-Slot wirken auf „das aktuelle Ziel" —
    kein Stern, auch wenn genau dieses Ziel live bearbeitet ist."""
    m = _matrix(fm)
    effect_live.set_edit_target("MX", m.id)
    aktion = _taste(None, action=ButtonAction.EFFECT_ACTION,
                    effect_action_key="next_color", edit_slot="MX")
    fader = _fader(None, edit_slot="MX")
    effect_live.set_param("speed", 9.0, m.id)
    assert effect_live.ist_live_editiert(m.id)
    assert aktion.live_stern_fid() is None
    assert not aktion.live_stern_sichtbar()
    assert not fader.live_stern_sichtbar()


def test_gruppen_und_fremde_aktionen_zeigen_nichts(fm):
    m = _matrix(fm)
    n = _matrix(fm, "N")
    gruppe = _taste(m.id, function_ids=[n.id])
    blackout = _taste(m.id, action=ButtonAction.BLACKOUT)
    executor = _taste(m.id, action=ButtonAction.TOGGLE)
    pegel = _fader(m.id, mode=SliderMode.LEVEL)
    effect_live.set_param("speed", 9.0, m.id)
    effect_live.set_param("speed", 9.0, n.id)
    for w in (gruppe, blackout, executor, pegel):
        assert not w.live_stern_sichtbar()


def test_reset_live_und_commit_nehmen_stern_weg(fm):
    m = _matrix(fm)
    t = _taste(m.id)
    reset = _taste(m.id, action=ButtonAction.EFFECT_ACTION,
                   effect_action_key="clear_live_override")
    effect_live.set_param("speed", 7.5, m.id)
    assert t.live_stern_sichtbar()
    reset._trigger(True)
    reset._trigger(False)
    assert not effect_live.ist_live_editiert(m.id)
    assert not t.live_stern_sichtbar()
    # Commit: neuer Stand/Preset
    effect_live.set_param("speed", 3.3, m.id)
    assert t.live_stern_sichtbar()
    effect_live.do_action("commit_live", m.id)
    assert not t.live_stern_sichtbar()
    assert abs(m.matrix_speed - 3.3) < 1e-6        # Wert bleibt, nur gilt er jetzt


def test_commit_live_override_direkt(fm):
    e = fm.new_efx("Efx")
    t = _taste(e.id)
    effect_live.set_param("speed", 4.0, e.id)
    assert t.live_stern_sichtbar()
    effect_live.commit_live_override(e.id)
    assert not t.live_stern_sichtbar()


def test_pixelprobe_stern_gemalt(fm):
    """Offscreen gemalt: gelbe Pixel in der Stern-Ecke nur mit Live-Aenderung,
    auf dunkler UND heller Taste."""
    m = _matrix(fm)
    for bg in ("#202020", "#f0f0f0"):
        t = _taste(m.id, caption="")
        t._bg_color = QColor(bg)
        f = _fader(m.id)
        ecke_t = QRect(0, 0, 24, 24)
        ecke_f = QRect(0, 0, 18, 18)
        assert _gelbe_pixel(t, ecke_t) == 0
        assert _gelbe_pixel(f, ecke_f) == 0
        effect_live.set_param("speed", 7.5, m.id)
        assert _gelbe_pixel(t, ecke_t) > 15, bg
        assert t._live_stern_rect is not None and ecke_t.contains(t._live_stern_rect)
        # dunkle Kontur am Stern (auch auf heller Taste sichtbar)
        img = t.grab().toImage()
        r = t._live_stern_rect
        dunkel = sum(1 for x in range(r.left(), r.right() + 1)
                     for y in range(r.top(), r.bottom() + 1)
                     if img.pixelColor(x, y).lightness() < 70)
        assert dunkel > 3, bg
        assert _gelbe_pixel(f, ecke_f) > 10
        effect_live.clear_live_overrides()
        m.clear_live_override()
        assert _gelbe_pixel(t, ecke_t) == 0


def test_stern_weicht_badges_aus(fm):
    """Tasten-Kuerzel/„+n" oben links: Stern rutscht darunter; Leitplanke am
    Fader oben links: Stern nach oben rechts."""
    m = _matrix(fm)
    t = _taste(m.id, caption="", key_binding="Q",
               actions=[{"type": "blackout", "mode": "toggle"}])
    f = _fader(m.id, invert=True)
    effect_live.set_param("speed", 7.5, m.id)
    t.grab()
    f.grab()
    assert t._live_stern_rect.top() >= 11
    assert not t._live_stern_rect.intersects(QRect(0, 0, 14, 10))
    assert not f._live_stern_rect.intersects(QRect(2, 0, 12, 12))
    assert f._live_stern_rect.top() < 20


def test_stern_meidet_beschriftung():
    """Reicht die Beschriftung in die obere Ecke, waehlt die Eckenwahl die
    naechste freie Flaeche."""
    a, b = QRect(2, 2, 12, 12), QRect(50, 50, 12, 12)
    assert live_stern.waehle_stern_rect([a, b], [QRect(0, 0, 72, 20)]) == b
    assert live_stern.waehle_stern_rect([a, b], [None]) == a
    assert live_stern.waehle_stern_rect([a, b], [QRect(0, 0, 72, 72)]) == a


def test_tooltip_zusatz(fm):
    m = _matrix(fm)
    t = _taste(m.id)
    t.setToolTip("Mein Pad")
    effect_live.set_param("speed", 7.5, m.id)
    assert "live bearbeitet" in live_stern.tooltip_mit_stern(t.toolTip())
    assert live_stern.tooltip_mit_stern(t.toolTip()).startswith("Mein Pad")
    from PySide6.QtGui import QHelpEvent
    ev = QHelpEvent(QEvent.Type.ToolTip, QPoint(30, 30), t.mapToGlobal(QPoint(30, 30)))
    assert live_stern.zeige_live_stern_tooltip(t, ev)
    effect_live.clear_live_overrides()
    assert not live_stern.zeige_live_stern_tooltip(t, ev)


# ── Aktualisierung im vorhandenen Statustakt ────────────────────────────────

def test_konsole_zeichnet_nur_bei_aenderung_neu(fm):
    from src.ui.views.virtual_console_view import VirtualConsoleView
    m = _matrix(fm)
    canvas = QWidget()
    t = _taste(m.id)
    t.setParent(canvas)
    f = _fader(m.id)
    f.setParent(canvas)
    zaehler = []
    t.update = lambda *a: zaehler.append("t")
    f.update = lambda *a: zaehler.append("f")
    stub = SimpleNamespace(
        _canvas=canvas, _sidebar=None,
        _canvas_alive=lambda: True,
        _function_catalog_signature=lambda funcs: 0,
        _zeige_aktiven_effekt=lambda *a: None,
        _TEXT_KEIN_EFFEKT="", _STIL_ZEILE_LEER="", _STIL_ZEILE_AKTIV="")
    VirtualConsoleView._update_active_fx(stub)
    zaehler.clear()
    VirtualConsoleView._update_active_fx(stub)
    assert zaehler == []                           # nichts geaendert -> still
    effect_live.set_param("speed", 7.5, m.id)
    VirtualConsoleView._update_active_fx(stub)
    assert "t" in zaehler and "f" in zaehler
    zaehler.clear()
    VirtualConsoleView._update_active_fx(stub)
    assert zaehler == []
    m.clear_live_override()
    VirtualConsoleView._update_active_fx(stub)
    assert "t" in zaehler
    canvas.deleteLater()


def test_zwischenstand_wird_bei_aenderung_verworfen(fm):
    """Der Zwischenstand fuer Malen/Handy darf nie eine Aenderung verschlucken."""
    m = _matrix(fm)
    assert effect_live.live_editiert_ids(max_alter=60) == frozenset()
    effect_live.set_param("speed", 7.5, m.id)
    assert m.id in effect_live.live_editiert_ids(max_alter=60)
    m.clear_live_override()
    assert m.id not in effect_live.live_editiert_ids(max_alter=60)


# ── Handy-Konsole ───────────────────────────────────────────────────────────

def test_handy_beschreibung_live_editiert(fm):
    from src.ui.virtualconsole.vc_fernbedienung import beschreibe
    m = _matrix(fm)
    t = _taste(m.id)
    f = _fader(m.id)
    andere = _taste(None, action=ButtonAction.BLACKOUT)
    assert beschreibe(t)["live_editiert"] is False
    effect_live.set_param("speed", 7.5, m.id)
    assert beschreibe(t)["live_editiert"] is True
    assert beschreibe(f)["live_editiert"] is True
    assert beschreibe(andere)["live_editiert"] is False
    json.dumps(beschreibe(t))


def test_handy_seite_zeigt_sternchen():
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / "src" / "web" / "templates"
            / "konsole.html").read_text(encoding="utf-8")
    assert "live_editiert" in html and ".zelle .stern" in html


# ── Show laden / speichern ──────────────────────────────────────────────────

def test_show_laden_nimmt_stern_weg_und_speichert_nichts(fm, tmp_path):
    from src.core.app_state import get_state
    from src.core.show import show_file
    state = get_state()
    show_file.reset_show()
    fm = state.function_manager
    m = fm.new_rgb_matrix("Mtx")
    m.snapshot_preset()
    alt_speed = m.matrix_speed
    t = _taste(m.id)
    vor = t.to_dict()
    effect_live.set_param("speed", 7.5, m.id)
    assert t.live_stern_sichtbar()
    assert t.to_dict() == vor                       # nichts Neues am Widget
    pfad = os.path.join(str(tmp_path), "ui129.lshow")
    show_file.save_show(pfad)
    roh = open(pfad, "rb").read()
    assert b"live_editiert" not in roh
    ok, msg = show_file.load_show(pfad)
    assert ok, msg
    assert effect_live.live_editiert_ids() == frozenset()
    assert not t.live_stern_sichtbar()
    geladen = state.function_manager.get(m.id)
    assert geladen is not None and abs(geladen.matrix_speed - alt_speed) < 1e-6
    show_file.reset_show()


def test_alte_show_laedt_ohne_stern(fm):
    """Eine im Test gebaute Alt-Taste/-Fader (Show-Stand ohne UI-129) laedt
    unveraendert, speichert keinen neuen Schluessel und zeigt den Stern trotzdem,
    sobald ihr Effekt live bearbeitet wird."""
    m = _matrix(fm, "Alt")
    alt_t = {"type": "VCButton", "caption": "Alt", "x": 0, "y": 0, "w": 72, "h": 72,
             "action": "FunctionToggle", "function_id": m.id}
    alt_f = {"type": "VCSlider", "caption": "AltF", "x": 0, "y": 0, "w": 60, "h": 200,
             "mode": SliderMode.EFFECT_SPEED, "function_id": m.id}
    t = VCButton("x")
    t.apply_dict(json.loads(json.dumps(alt_t)))
    f = VCSlider("y")
    f.apply_dict(json.loads(json.dumps(alt_f)))
    assert t.function_id == m.id and f.function_id == m.id
    vor_t, vor_f = t.to_dict(), f.to_dict()
    assert not t.live_stern_sichtbar() and not f.live_stern_sichtbar()
    effect_live.set_param("speed", 7.5, m.id)
    assert t.live_stern_sichtbar() and f.live_stern_sichtbar()
    assert t.to_dict() == vor_t and f.to_dict() == vor_f
    for d in (t.to_dict(), f.to_dict()):
        assert not any("live" in k and "edit" in k for k in d)
