"""LAS-26: Laser-Bedienung fuer DMX-Laser (EL-400RGB MK2, SH-LASER3W).

Befunde der Sichtpruefung, die hier festgenagelt werden:

1. **Kein NOT-AUS fuer DMX-Laser auf der Laser-Seite.** Der Knopf sass nur in
   der Box „Laser-Ausgabe (Netzwerk)“, die ausschliesslich bei Ether-Dream-/
   IDN-Lasern sichtbar ist. Jetzt hat jede Auswahl mit DMX-Laser eine Box
   „Laser-Sicherheit“ mit NOT-AUS und Zustandsanzeige.
2. **Fixture Generator sagte nichts zur Laser-Sicherheit.** Ein Laser-Profil
   ohne Aus-Wert (oder mit einem Grundwert, der den Laser beim Patchen
   einschaltet) ging ohne Hinweis durch. Jetzt warnt die Pruefung, und bei
   einem guten Profil steht dort, ueber welchen Kanal/Wert LightOS ihn dunkel
   schaltet — dieselbe Erkennung wie im Sende-Pfad (``_laser_aus_wert``).
3. Mustergeschwindigkeit (``effect_speed``) fehlte auf der Laser-Seite —
   abgedeckt in ``test_laserworld_el400_profile.py``.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


class _Rng:
    def __init__(self, lo, hi, name, kind=""):
        self.range_from, self.range_to, self.name, self.kind = lo, hi, name, kind


class _Ch:
    def __init__(self, attr, num, ranges=None, name=""):
        self.attribute = attr
        self.channel_number = num
        self.ranges = ranges or []
        self.name = name or attr


class _FX:
    def __init__(self, fid, chans, protocol="dmx"):
        self.fid = fid
        self.label = self.fixture_name = self.name = "EL-400RGB MK2"
        self.fixture_type = "laser"
        self.universe = 1
        self.address = 1
        self.protocol = protocol
        self.net_host = "10.0.0.9" if protocol != "dmx" else ""
        self._chans = chans


def _el400():
    return [
        _Ch("shutter", 1, [_Rng(0, 49, "Laser aus", "closed"),
                           _Rng(50, 99, "Musik-Modus", "sound"),
                           _Rng(100, 149, "Auto-Modus"),
                           _Rng(150, 199, "Statische Muster (DMX)", "open"),
                           _Rng(200, 255, "Dynamische Muster (DMX)", "open")],
            "Betriebsart"),
        _Ch("gobo_wheel", 2, name="Musterauswahl"),
        _Ch("laser_x", 3), _Ch("laser_y", 4),
        _Ch("effect_speed", 6, name="Geschwindigkeit dynamische Muster"),
    ]


class _LO:
    def __init__(self, state):
        self.state = state
        self.armed = False

    def estop_all(self):
        self.state.laser_estop_active = True

    def set_armed(self, v):
        self.armed = bool(v)

    def clear_estop_all(self):
        pass        # loest NUR die Netzwerk-Verriegelung, nicht den DMX-Latch

    def set_figure(self, fid, figure):
        pass

    def clear_figures(self):
        pass


class _State:
    def __init__(self, fixtures):
        self._fixtures = list(fixtures)
        self.programmer: dict = {}
        self.laser_estop_active = False
        self.lo = _LO(self)

    def get_patched_fixtures(self):
        return list(self._fixtures)

    def get_selected_fids(self):
        return [f.fid for f in self._fixtures]

    def set_programmer_value(self, fid, attr, value, undoable=False, head=0):
        self.programmer.setdefault(fid, {})[attr] = int(value)
        if attr in ("shutter", "gobo_wheel"):       # A3D-02: „wieder an“
            self.laser_estop_active = False

    def get_programmer_value(self, fid, attr, head=0):
        return self.programmer.get(fid, {}).get(attr)

    def ensure_laser_output(self):
        return self.lo


def _view(monkeypatch, fixtures):
    _app()
    import src.ui.views.laser_view as lv
    import src.core.app_state as A
    st = _State(fixtures)
    monkeypatch.setattr(lv, "get_state", lambda: st)
    monkeypatch.setattr(lv, "get_channels_for_patched", lambda f: f._chans)
    monkeypatch.setattr(A, "get_channels_for_patched", lambda f: f._chans,
                        raising=False)
    v = lv.LaserView(follow_selection=False)
    v.refresh_from_selection()
    return v, st


# ── 1: NOT-AUS fuer DMX-Laser ───────────────────────────────────────────────

def test_dmx_laser_hat_not_aus(monkeypatch):
    v, _st = _view(monkeypatch, [_FX(1, _el400())])
    assert not v._safety_box.isVisibleTo(v)          # keine Netzwerk-Box
    assert v._dmx_safety_box.isVisibleTo(v)
    assert "NOT-AUS" in v._btn_dmx_estop.text()


def test_not_aus_schaltet_und_zeigt_zustand(monkeypatch):
    v, st = _view(monkeypatch, [_FX(1, _el400())])
    assert "aktiv" not in v._lbl_dmx_estop.text()
    v._btn_dmx_estop.click()
    assert st.laser_estop_active is True
    assert st.lo.armed is False
    assert "NOT-AUS aktiv" in v._lbl_dmx_estop.text()
    # Betriebsart neu waehlen (Modus-Kachel) = bewusstes Wieder-Einschalten.
    v._on_mode_tile_clicked(175)
    assert st.laser_estop_active is False
    assert "NOT-AUS aktiv" not in v._lbl_dmx_estop.text()


def test_nur_netzwerk_laser_ohne_dmx_box(monkeypatch):
    v, _st = _view(monkeypatch, [_FX(1, _el400(), protocol="etherdream")])
    assert v._safety_box.isVisibleTo(v)
    assert not v._dmx_safety_box.isVisibleTo(v)


def test_modus_kachel_tooltip_nennt_den_kanal(monkeypatch):
    v, _st = _view(monkeypatch, [_FX(1, _el400())])
    from src.ui.widgets.preset_tile import PresetTile
    tips = [t.toolTip() for t in v._mode_box.findChildren(PresetTile)]
    assert tips and all(t.startswith("Betriebsart") for t in tips), tips


def test_mustergeschwindigkeit_hat_einen_regler(monkeypatch):
    v, _st = _view(monkeypatch, [_FX(1, _el400())])
    assert "effect_speed" in v._rows


# ── 2: Fixture Generator ────────────────────────────────────────────────────

def _modell(kanaele, typ="laser"):
    from src.ui.widgets.fixture_generator import (GenChannel, GenMode,
                                                  GenRange, GeneratorModel)
    chs = []
    for name, attr, default, bereiche in kanaele:
        chs.append(GenChannel(name=name, attribute=attr, default_value=default,
                              highlight_value=0,
                              ranges=[GenRange(*b) for b in bereiche]))
    return GeneratorModel(manufacturer="Laserworld", model="EL-400RGB MK2",
                          short_name="EL400", fixture_type=typ,
                          modes=[GenMode(name="9-Kanal", channels=chs)])


_BETRIEBSART = [(0, 49, "Laser aus", "closed"), (50, 99, "Musik", "sound"),
                (100, 149, "Auto", ""), (150, 199, "Statisch", "open"),
                (200, 255, "Dynamisch", "open")]


def _laser_hinweise(model):
    from src.ui.widgets.fixture_generator import validate_model
    return [t for _s, t in validate_model(model) if "Laser" in t]


def test_generator_gutes_laserprofil_ohne_warnung_mit_bestaetigung():
    from src.ui.widgets.fixture_generator import laser_sicherheit_text
    m = _modell([("Betriebsart", "shutter", 0, _BETRIEBSART),
                 ("Muster", "gobo_wheel", 0, [])])
    assert _laser_hinweise(m) == []
    text = laser_sicherheit_text(m)
    assert "Kanal 1 ('Betriebsart') = 0" in text


def test_generator_warnt_ohne_aus_wert():
    m = _modell([("Betriebsart", "macro", 0, [(0, 99, "Auto", "")]),
                 ("X", "laser_x", 0, [])])
    hinweise = _laser_hinweise(m)
    assert len(hinweise) == 1 and "ohne Aus-Wert" in hinweise[0]


def test_generator_warnt_wenn_grundwert_den_laser_einschaltet():
    m = _modell([("Betriebsart", "shutter", 175, _BETRIEBSART)])
    hinweise = _laser_hinweise(m)
    assert len(hinweise) == 1
    assert "Default 175" in hinweise[0] and "Default auf 0" in hinweise[0]


def test_generator_laser_mit_dimmer_braucht_keinen_aus_wert():
    m = _modell([("Dimmer", "intensity", 0, []), ("X", "laser_x", 0, [])])
    assert _laser_hinweise(m) == []


def test_generator_par_bleibt_still():
    m = _modell([("Strobe", "shutter", 200, [(0, 9, "Zu", "closed"),
                                              (10, 255, "Offen", "open")])],
                typ="par")
    from src.ui.widgets.fixture_generator import laser_sicherheit_text
    assert _laser_hinweise(m) == []
    assert laser_sicherheit_text(m) == ""


def test_generator_dialog_zeigt_die_bestaetigung():
    _app()
    from src.ui.widgets.fixture_generator import FixtureGeneratorDialog
    m = _modell([("Betriebsart", "shutter", 0, _BETRIEBSART)])
    dlg = FixtureGeneratorDialog(None, model=m)
    try:
        assert "Laser-Sicherheit" in dlg._issues.toPlainText()
    finally:
        dlg._live.shutdown()
        dlg.deleteLater()


# ── 4: Regler vor Paletten, Beschriftung aus dem Profil ────────────────────

def test_regler_stehen_vor_paletten_und_werksmustern(monkeypatch):
    # Vorher lagen Muster-Paletten und Werksmuster FEST ueber dem Regler-
    # Scrollbereich; bei 900 px Fensterhoehe blieb fuer die Regler gut eine
    # Zeile. Jetzt: alles in einem Scrollbereich, Regler zuerst.
    v, _st = _view(monkeypatch, [_FX(1, _el400())])
    lay = v._scroll.widget().layout()
    reihe = [lay.itemAt(i).widget() for i in range(lay.count())]
    assert reihe.index(v._rows_host) < reihe.index(v._pal_box)
    assert reihe.index(v._pal_box) < reihe.index(v._pattern_box)


def test_zeilen_tragen_den_kanalnamen(monkeypatch):
    from PySide6.QtWidgets import QLabel
    v, _st = _view(monkeypatch, [_FX(1, _el400())])
    texte = {r.findChildren(QLabel)[0].text() for r in v._rows.values()}
    assert "Musterauswahl" in texte          # nicht „Gobo-Rad“
    assert "Geschwindigkeit dynamische Muster" in texte


def test_zeilen_beschriftung_ohne_gruppen_praefix_und_rueckfall():
    from src.ui.views.laser_view import row_label
    assert row_label(_Ch("gobo_wheel", 3, name="A: Musterauswahl")) == "Musterauswahl"
    assert row_label(_Ch("laser_x", 4, name="laser_x")) == "X-Bewegung"
    assert row_label(_Ch("laser_x", 4, name="")) == "X-Bewegung"
