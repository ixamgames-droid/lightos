"""FM-75: Live-Test im Fixture Generator — bei einem Laser erst fragen.

**Der Befund (Sitzung A, 12.10.2026).** „Test starten“ schrieb sofort die
Default-Werte aller Kanaele an das echte Geraet — auch bei einem Laser, ohne
Rueckfrage. Beim Nachlesen kamen drei Dinge dazu, die an derselben Stelle
haengen:

* „Blackout“ im Test setzte alles auf 0. Bei Lasern, deren Betriebsart bei 0
  „Auto run“ heisst, ist das AN.
* Der Laser-NOT-AUS wirkt nur auf gepatchte Laser. Der Test schreibt am
  Renderer vorbei; ein Profil, das gerade erst entsteht, ist meist nicht
  gepatcht — der NOT-AUS liess den Test weiterlaufen.
* „Test stoppen“ schrieb die Vorwerte zurueck, meist 0 — siehe oben.

Es wird an kein Geraet gesendet: die Universen sind echte ``Universe``-Objekte
ohne Ausgang, die Rueckfrage ist ersetzt.
"""
from __future__ import annotations

import os
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox          # noqa: E402

from src.core.dmx.universe import Universe                       # noqa: E402
from src.ui.widgets import fixture_generator as fg               # noqa: E402
from src.ui.widgets.fixture_generator import (                   # noqa: E402
    GenChannel, GenMode, GenRange, GeneratorModel, LiveTester,
    live_test_aus_werte, live_test_laser_hinweis)

_AUS_BEI_NULL = [(0, 49, "Laser aus", "closed"), (50, 149, "Auto", ""),
                 (150, 255, "Statisch", "open")]
#: Ein Laser, bei dem 0 NICHT aus ist (0–49 „Auto run“, aus erst ab 50).
_AUS_BEI_50 = [(0, 49, "Auto run", ""), (50, 99, "Laser off", "closed"),
               (100, 255, "DMX", "open")]


def _modell(kanaele, typ="laser"):
    chs = [GenChannel(name=name, attribute=attr, default_value=default,
                      highlight_value=0, ranges=[GenRange(*b) for b in bereiche])
           for name, attr, default, bereiche in kanaele]
    return GeneratorModel(manufacturer="Test", model="Laser 1", short_name="L1",
                          fixture_type=typ,
                          modes=[GenMode(name="3-Kanal", channels=chs)])


def _laser(default=0, bereiche=_AUS_BEI_NULL):
    return _modell([("Betriebsart", "shutter", default, bereiche),
                    ("Muster", "gobo_wheel", 10, []),
                    ("Rot", "color_r", 255, [])])


def _par():
    return _modell([("Dimmer", "intensity", 0, []), ("Rot", "color_r", 0, [])],
                   typ="par")


# ══════════════════════════════════════════════════════════════════════════════
# A) Der Text der Rueckfrage
# ══════════════════════════════════════════════════════════════════════════════

def test_kein_laser_keine_rueckfrage():
    m = _par()
    assert live_test_laser_hinweis(m, m.modes[0], 1, 1) == ""
    assert live_test_laser_hinweis(m, None, 1, 1) == ""
    assert live_test_aus_werte(m, m.modes[0]) == {}


def test_laser_hinweis_nennt_universum_adressen_und_kanalzahl():
    m = _laser()
    text = live_test_laser_hinweis(m, m.modes[0], 2, 100)
    assert "Dieses Profil ist ein Laser" in text
    assert "Universe 2, Adresse 100–102" in text
    assert "Default-Werte der 3 Kanäle" in text
    assert "Niemand steht im Strahlbereich" in text


def test_default_aus_sagt_dass_er_erst_mit_dem_fader_strahlt():
    m = _laser(default=0)
    text = live_test_laser_hinweis(m, m.modes[0], 1, 1)
    assert "bleibt er aus (Kanal 1 „Betriebsart“ = 0)" in text
    assert "SOFORT" not in text
    assert "„Blackout“ im Test stellt Kanal 1 auf 0 (aus)" in text


def test_default_an_warnt_dass_er_sofort_strahlt():
    m = _laser(default=200)
    text = live_test_laser_hinweis(m, m.modes[0], 1, 1)
    assert "strahlt er SOFORT" in text
    assert "startet auf 200, „aus“ wäre 0" in text


def test_ohne_aus_wert_sagt_lightos_dass_es_nichts_weiss():
    m = _modell([("Programm", "macro", 0, []), ("Rot", "color_r", 0, [])])
    text = live_test_laser_hinweis(m, m.modes[0], 1, 1)
    assert "kein Aus-Wert hinterlegt" in text
    assert "auch das kann bei einem Laser „an“ heißen" in text
    assert live_test_aus_werte(m, m.modes[0]) == {}


def test_laser_wird_auch_ueber_ein_laser_attribut_erkannt():
    m = _modell([("Dimmer", "intensity", 0, []),
                 ("Muster", "laser_pattern", 0, [])], typ="other")
    assert live_test_laser_hinweis(m, m.modes[0], 1, 1) != ""


def test_ein_kanal_ohne_bis():
    m = _modell([("Betriebsart", "shutter", 0, _AUS_BEI_NULL)])
    assert "Universe 1, Adresse 7:" in live_test_laser_hinweis(m, m.modes[0], 1, 7)


def test_aus_werte_je_kanal_offset():
    m = _laser(bereiche=_AUS_BEI_50)
    assert live_test_aus_werte(m, m.modes[0]) == {0: 50}
    assert live_test_aus_werte(m, None) == {}


# ══════════════════════════════════════════════════════════════════════════════
# B) LiveTester: Blackout und Stoppen mit Aus-Wert
# ══════════════════════════════════════════════════════════════════════════════

def test_blackout_setzt_den_aus_wert_statt_null():
    u = Universe(1)
    t = LiveTester(u, base_address=10)
    for off, wert in enumerate((200, 30, 255)):
        t.write_channel(off, wert)
    t.blackout({0: 50})
    assert [u.get_channel(a) for a in (10, 11, 12)] == [50, 0, 0]
    t.restore()


def test_blackout_ohne_angabe_wie_bisher():
    u = Universe(1)
    t = LiveTester(u, base_address=1)
    t.write_channel(0, 255)
    t.blackout()
    assert u.get_channel(1) == 0


def test_blackout_fasst_nur_an_was_der_test_schon_angefasst_hat():
    u = Universe(1)
    u.set_channel(20, 123)                       # fremder Kanal einer laufenden Show
    t = LiveTester(u, base_address=10)
    t.write_channel(1, 99)
    t.blackout({0: 50, 10: 77})                  # Offset 0 und 10 nie angefasst
    assert u.get_channel(10) == 0 and u.get_channel(20) == 123
    t.restore()


def test_stoppen_laesst_den_aus_wert_stehen_wenn_vorher_null_stand():
    """0 an der Betriebsart heisst bei manchen Lasern „Auto run“ — „Test
    stoppen“ schaltete den Laser sonst ein."""
    u = Universe(1)
    t = LiveTester(u, base_address=10)
    t.write_channel(0, 200)
    t.write_channel(1, 30)
    t.restore({0: 50})
    assert u.get_channel(10) == 50
    assert u.get_channel(11) == 0


def test_stoppen_gibt_einer_laufenden_show_ihren_wert_zurueck():
    u = Universe(1)
    u.set_channel(10, 180)                       # die Show steuert den Laser
    t = LiveTester(u, base_address=10)
    t.write_channel(0, 200)
    t.restore({0: 50})
    assert u.get_channel(10) == 180


def test_halten_schreibt_nichts_zurueck_und_sperrt():
    u = Universe(1)
    u.set_channel(10, 7)
    t = LiveTester(u, base_address=10)
    t.write_channel(0, 200)
    t.blackout({0: 50})
    t.halten()
    assert u.get_channel(10) == 50
    t.write_channel(0, 255)                      # nach dem Ende wirkungslos
    t.restore()
    assert u.get_channel(10) == 50


# ══════════════════════════════════════════════════════════════════════════════
# C) Das Feld im Dialog
# ══════════════════════════════════════════════════════════════════════════════

class _OM:
    _running = True

    def add_universe(self, n):
        return Universe(n)

    def start(self):
        self._running = True


@pytest.fixture
def aufbau(monkeypatch):
    QApplication.instance() or QApplication([])
    state = types.SimpleNamespace(output_manager=_OM(), universes={1: Universe(1)},
                                  laser_estop_active=False)
    fragen: list[str] = []
    meldungen: list[str] = []
    antwort = {"wert": False}

    def frage(_parent, text):
        fragen.append(text)
        return antwort["wert"]

    def warnung(_parent, _titel, text, *a, **k):
        meldungen.append(text)
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(fg, "_laser_test_fragen", frage)
    monkeypatch.setattr(fg.QMessageBox, "warning", staticmethod(warnung))
    dialoge = []

    def bauen(model):
        dlg = fg.FixtureGeneratorDialog(None, model=model)
        monkeypatch.setattr(dlg, "get_state", lambda: state)
        dialoge.append(dlg)
        return dlg

    yield types.SimpleNamespace(state=state, fragen=fragen, antwort=antwort,
                                meldungen=meldungen, bauen=bauen,
                                universum=state.universes[1])
    for dlg in dialoge:
        dlg._live.shutdown()
        dlg.deleteLater()


def _werte(u, n=3, ab=1):
    return [u.get_channel(a) for a in range(ab, ab + n)]


def test_laser_ohne_ja_wird_nichts_gesendet(aufbau):
    live = aufbau.bauen(_laser(default=200))._live
    live._btn_start.setChecked(True)
    assert len(aufbau.fragen) == 1
    assert "strahlt er SOFORT" in aufbau.fragen[0]
    assert live._tester is None
    assert _werte(aufbau.universum) == [0, 0, 0], "es wurde trotzdem gesendet"
    assert not live._btn_start.isChecked()
    assert "Nicht gestartet" in live._info.text()


def test_die_frage_hat_feste_knoepfe_und_die_vorgabe_abbrechen(monkeypatch):
    """Die echte Rueckfrage, ohne sie zu zeigen: ``exec`` ist ersetzt."""
    QApplication.instance() or QApplication([])
    gesehen = {}

    def exec_(box):
        gesehen["titel"] = box.windowTitle()
        gesehen["text"] = box.text()
        gesehen["knoepfe"] = [b.text() for b in box.buttons()]
        gesehen["vorgabe"] = box.defaultButton().text()
        gesehen["escape"] = box.escapeButton().text()
        return 0

    monkeypatch.setattr(fg.QMessageBox, "exec", exec_)
    assert fg._laser_test_fragen(None, "Hinweis") is False      # nichts geklickt
    assert gesehen["titel"] == "Live-Test mit einem Laser starten?"
    assert gesehen["text"] == "Hinweis"
    assert sorted(gesehen["knoepfe"]) == ["Abbrechen", "Test starten"]
    assert gesehen["vorgabe"] == "Abbrechen" and gesehen["escape"] == "Abbrechen"


def test_laser_mit_ja_startet_wie_bisher(aufbau):
    aufbau.antwort["wert"] = True
    live = aufbau.bauen(_laser(default=0))._live
    live._btn_start.setChecked(True)
    assert live._tester is not None
    assert _werte(aufbau.universum) == [0, 10, 255]
    assert live._notaus_timer.isActive()
    live._btn_start.setChecked(False)
    assert not live._notaus_timer.isActive()


def test_kein_laser_startet_ohne_frage(aufbau):
    live = aufbau.bauen(_par())._live
    live._btn_start.setChecked(True)
    assert aufbau.fragen == []
    assert live._tester is not None
    assert not live._notaus_timer.isActive()


def test_der_typ_aus_dem_kopf_zaehlt_auch_wenn_er_gerade_erst_gewaehlt_wurde(aufbau):
    dlg = aufbau.bauen(_par())
    dlg._cb_type.setCurrentText("laser")
    dlg._live._btn_start.setChecked(True)
    assert len(aufbau.fragen) == 1


def test_bei_stehendem_notaus_startet_kein_laser_test(aufbau):
    aufbau.state.laser_estop_active = True
    aufbau.antwort["wert"] = True
    live = aufbau.bauen(_laser(default=200))._live
    live._btn_start.setChecked(True)
    assert live._tester is None
    assert _werte(aufbau.universum) == [0, 0, 0]
    assert aufbau.fragen == [], "bei stehendem NOT-AUS wird gar nicht erst gefragt"
    assert len(aufbau.meldungen) == 1 and "Laser-NOT-AUS ist aktiv" in aufbau.meldungen[0]
    assert "NOT-AUS" in live._info.text()


def test_ohne_kanaele_steht_der_grund_da_und_nicht_gestoppt(aufbau):
    """Bestand, an derselben Stelle: der Text wurde vom Loesen des Knopfs
    mit „Test gestoppt“ ueberschrieben."""
    m = _par()
    m.modes[0].channels.clear()
    live = aufbau.bauen(m)._live
    live._btn_start.setChecked(True)
    assert live._info.text() == "Kein Modus/Kanäle zum Testen."


def test_stehender_notaus_haelt_einen_par_test_nicht_auf(aufbau):
    aufbau.state.laser_estop_active = True
    live = aufbau.bauen(_par())._live
    live._btn_start.setChecked(True)
    assert live._tester is not None and aufbau.fragen == []


def test_notaus_waehrend_des_tests_beendet_ihn_dunkel(aufbau):
    aufbau.antwort["wert"] = True
    live = aufbau.bauen(_laser(default=200, bereiche=_AUS_BEI_50))._live
    live._btn_start.setChecked(True)
    assert _werte(aufbau.universum) == [200, 10, 255]
    live._notaus_pruefen()                                  # NOT-AUS steht nicht
    assert live._tester is not None
    aufbau.state.laser_estop_active = True
    live._notaus_pruefen()
    assert live._tester is None
    assert _werte(aufbau.universum) == [50, 0, 0], "aus-Wert, nicht 0 und nicht die Vorwerte"
    assert not live._btn_start.isChecked()
    assert "Laser-NOT-AUS — Test beendet" in live._info.text()
    assert not live._notaus_timer.isActive()


def test_blackout_knopf_setzt_den_aus_wert_und_zeigt_ihn(aufbau):
    aufbau.antwort["wert"] = True
    live = aufbau.bauen(_laser(default=200, bereiche=_AUS_BEI_50))._live
    live._btn_start.setChecked(True)
    live._on_blackout()
    assert _werte(aufbau.universum) == [50, 0, 0]
    assert [f.value() for f in live._faders] == [50, 0, 0]


def test_stoppen_laesst_den_laser_aus(aufbau):
    aufbau.antwort["wert"] = True
    live = aufbau.bauen(_laser(default=200, bereiche=_AUS_BEI_50))._live
    live._btn_start.setChecked(True)
    live._btn_start.setChecked(False)
    assert _werte(aufbau.universum) == [50, 0, 0]
    assert "Kanal 1 steht auf 50 (Laser aus)" in live._info.text()


def test_dialog_schliessen_laesst_den_laser_aus(aufbau):
    aufbau.antwort["wert"] = True
    live = aufbau.bauen(_laser(default=200, bereiche=_AUS_BEI_50))._live
    live._btn_start.setChecked(True)
    live.shutdown()
    assert _werte(aufbau.universum) == [50, 0, 0]


def test_par_stoppen_schreibt_die_vorwerte_zurueck_wie_bisher(aufbau):
    aufbau.universum.set_channel(1, 44)
    live = aufbau.bauen(_par())._live
    live._btn_start.setChecked(True)
    live._on_fader(0, 255)
    assert aufbau.universum.get_channel(1) == 255
    live._btn_start.setChecked(False)
    assert _werte(aufbau.universum, 2) == [44, 0]
    assert live._info.text() == "Test gestoppt — Kanäle zurückgesetzt."
