"""ENG-34: Untergrund fuer Dimmer-Effekte — fester Wert und Atmen.

Beim Lauflicht gingen die Lampen ohne Laeufer bisher auf 0. Der Untergrund
legt fest, was sie stattdessen tun. Er ist eine Eigenschaft des DIMMER-Effekts,
wirkt nur auf den Dimmer (die Farbe bleibt getrennt) und setzt an der Stelle
an, an der seit jeher ``intensity_min`` gerechnet wird.

Geprueft wird:

* Engine: je Art stehen die Zellen ohne Laeufer auf dem Untergrund, der Laeufer
  bleibt, der Schweif blendet auf den Untergrund aus, Atmen laeuft mit der Uhr
  des Effekts, die Helligkeit des Effekts dimmt mit, Stopp ist aus.
* Altbestand: ``intensity_min`` ueber 0 verhaelt sich wie bisher, wird als
  „Fester Wert" gezeigt, und eine alte Show speichert byte-gleich.
* „Dimmer pro Runde wechseln": der feste Wert wirkt jetzt auch dort — aber nur,
  wenn die Art ausdruecklich gesetzt ist.
* Vorschau und Ausgabe zeigen dasselbe.
* Der Regler „Dimmer min" der virtuellen Konsole meint denselben Wert.
* Mehrkopf-Geraet mit geteiltem Dimmer: es gilt der hoechste Wert der Zellen.
* Editor: feste Felder, nur ein- und ausgeblendet; zwanzigmal Umschalten der
  Art im Kindprozess ohne Absturz.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.dmx.universe import Universe
from src.core.engine.rgb_matrix import (
    UNTERGRUND_ATMEN, UNTERGRUND_AUS, UNTERGRUND_FEST, MatrixStyle,
    RgbAlgorithm, RgbMatrixInstance)

REPO = Path(__file__).resolve().parents[1]
_ROLLE = os.environ.get("ENG34_ARBEITER", "")
_MARKE = "ENG34-UEBERLEBT"
_ZELLEN = 6


# ── Hilfen ───────────────────────────────────────────────────────────────────


class _Ch:
    def __init__(self, attribute, channel_number):
        self.attribute = attribute
        self.channel_number = channel_number
        self.default_value = 0
        self.name = f"{attribute}{channel_number}"


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    fixture_type = "par"

    def __init__(self, fid, address, kanaele):
        self.fid = fid
        self.universe = 1
        self.address = address
        self.kanaele = kanaele
        self.channel_count = len(kanaele)


@pytest.fixture
def kanaele(monkeypatch):
    """Die Kanaele kommen aus dem Test-Geraet statt aus der Bibliothek."""
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: fx.kanaele)


def _dimmer_reihe():
    """Sechs Geraete mit je EINEM Dimmer-Kanal auf Adresse 1..6."""
    return [_Fx(i + 1, i + 1, [_Ch("intensity", 1)]) for i in range(_ZELLEN)]


def _lauflicht(**params) -> RgbMatrixInstance:
    m = RgbMatrixInstance(name="Lauf", cols=_ZELLEN, rows=1,
                          fixture_grid=list(range(1, _ZELLEN + 1)),
                          algorithm=RgbAlgorithm.CHASE)
    m.style = MatrixStyle.DIMMER
    m.tempo_bus_id = ""              # Freilauf: die Uhr ist allein ``_step``
    m.params = {"axis": "H", "movement": "normal", "runner_count": 1,
                "runner_width": 1, "after_fade": 0.0}
    m.params.update(params)
    m.start()
    return m


def _ausgabe(m, schritt: float, patch=None) -> list[int]:
    """Was bei Schritt ``schritt`` wirklich auf den Dimmer-Adressen steht."""
    m._step = float(schritt)
    u = Universe(1)
    m.write({1: u}, patch or _dimmer_reihe(), 0.0)
    return [u.get_channel(a) for a in range(1, _ZELLEN + 1)]


# ── Engine: Aus und fester Wert ──────────────────────────────────────────────


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
class TestFesterWert:

    def test_vorgabe_ist_aus_und_die_anderen_stehen_auf_null(self, kanaele):
        m = _lauflicht()
        assert m.untergrund_art() == UNTERGRUND_AUS
        assert "untergrund_art" not in m.params
        assert _ausgabe(m, 0) == [255, 0, 0, 0, 0, 0]
        assert _ausgabe(m, 3) == [0, 0, 0, 255, 0, 0]

    def test_fester_wert_hebt_die_anderen_und_laesst_den_laeufer(self, kanaele):
        m = _lauflicht(untergrund_art=UNTERGRUND_FEST)
        m.intensity_min = 51                      # 20 %
        assert m.untergrund_art() == UNTERGRUND_FEST
        assert _ausgabe(m, 0) == [255, 51, 51, 51, 51, 51]
        assert _ausgabe(m, 4) == [51, 51, 51, 51, 255, 51]

    def test_laeufer_helligkeit_bleibt_dimmer_max(self, kanaele):
        m = _lauflicht(untergrund_art=UNTERGRUND_FEST)
        m.intensity_min, m.intensity_max = 51, 200
        assert _ausgabe(m, 2) == [51, 51, 200, 51, 51, 51]

    def test_schweif_blendet_auf_den_untergrund_aus_nicht_auf_null(self, kanaele):
        m = _lauflicht(untergrund_art=UNTERGRUND_FEST, after_fade=50.0)
        m.intensity_min = 51
        werte = _ausgabe(m, 4)                    # Kopf auf Zelle 4, Schweif dahinter
        assert werte[4] == 255
        # Der Schweif faellt Zelle fuer Zelle und bleibt ueber dem Untergrund.
        assert werte[3] >= werte[2] > werte[1] > 51, werte
        assert werte[2] < 255
        # Dieselbe Kurve wie ohne Untergrund, nur von 51 statt von 0 aus gemessen.
        m.intensity_min = 0
        ohne = _ausgabe(m, 4)
        assert werte == [int(round(51 + (255 - 51) * (o / 255.0))) for o in ohne]
        m.intensity_min = 51
        assert min(werte) == 51, "keine Zelle faellt unter den Untergrund"
        assert werte[5] == 51, "vor dem Laeufer liegt nur Untergrund"

    def test_invertieren_der_laeufer_ist_die_dunkle_stelle(self, kanaele):
        m = _lauflicht(untergrund_art=UNTERGRUND_FEST, invert=True)
        m.intensity_min = 51
        assert _ausgabe(m, 1) == [255, 51, 255, 255, 255, 255]

    def test_gilt_fuer_andere_dimmer_algorithmen(self, kanaele):
        """Der Untergrund sitzt an der gemeinsamen Rechenstelle — kein
        Algorithmus kommt darunter."""
        for algo in (RgbAlgorithm.WIPE, RgbAlgorithm.WAVE, RgbAlgorithm.STROBE,
                     RgbAlgorithm.FILL, RgbAlgorithm.RANDOM):
            m = _lauflicht(untergrund_art=UNTERGRUND_FEST)
            m.algorithm = algo
            m.params = {"untergrund_art": UNTERGRUND_FEST}
            m.intensity_min = 77
            for schritt in (0.0, 0.5, 1.0, 2.5, 7.0):
                werte = _ausgabe(m, schritt)
                assert min(werte) >= 77, (algo, schritt, werte)

    def test_helligkeit_des_effekts_dimmt_den_untergrund_mit(self, kanaele):
        from src.core.engine.function_manager import FunctionManager
        fm = FunctionManager()
        m = _lauflicht(untergrund_art=UNTERGRUND_FEST)
        m.intensity_min = 100
        m.stop()
        fm.add(m)
        fm.start(m.id)
        m._step = 0.0
        m.intensity = 0.5
        u = Universe(1)
        fm.tick({1: u}, _dimmer_reihe(), 0.0)
        assert [u.get_channel(a) for a in range(1, 7)] == [127, 50, 50, 50, 50, 50]

    def test_stopp_ist_aus(self, kanaele):
        from src.core.engine.function_manager import FunctionManager
        fm = FunctionManager()
        m = _lauflicht(untergrund_art=UNTERGRUND_FEST)
        m.intensity_min = 100
        m.stop()
        fm.add(m)
        fm.start(m.id)
        u = Universe(1)
        fm.tick({1: u}, _dimmer_reihe(), 0.0)
        assert u.get_channel(2) == 100
        fm.stop(m.id)
        # Der Renderer baut jedes Bild aus dem Grundzustand neu auf.
        u = Universe(1)
        fm.tick({1: u}, _dimmer_reihe(), 0.0)
        assert [u.get_channel(a) for a in range(1, 7)] == [0] * 6

    def test_farbe_bleibt_unberuehrt(self, monkeypatch):
        """Der Untergrund schreibt nur den Dimmer — nie einen Farbkanal."""
        rgb = [_Ch("intensity", 1), _Ch("color_r", 2), _Ch("color_g", 3),
               _Ch("color_b", 4)]
        monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: fx.kanaele)
        patch = [_Fx(i + 1, 1 + i * 4, rgb) for i in range(_ZELLEN)]
        m = _lauflicht(untergrund_art=UNTERGRUND_ATMEN)
        m.intensity_min = 128
        for schritt in (0.0, 1.0, 2.0, 3.3):
            m._step = schritt
            u = Universe(1)
            u.begin_write_log()
            m.write({1: u}, patch, 0.0)
            geschrieben = set(u.end_write_log())
            assert geschrieben == {1 + i * 4 for i in range(_ZELLEN)}, geschrieben


# ── Engine: Atmen ────────────────────────────────────────────────────────────


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
class TestAtmen:

    def _m(self, **params):
        m = _lauflicht(untergrund_art=UNTERGRUND_ATMEN, **params)
        m.intensity_min = 128                     # „Helligkeit" 50 %
        return m

    def test_atmet_zwischen_tiefpunkt_und_helligkeit(self, kanaele):
        m = self._m()
        # Ein Atemzug je vier Schritte: unten, halb, oben, halb, unten.
        # Zelle 5 traegt bei diesen Schritten nie den Laeufer (der steht auf 0..4).
        assert [_ausgabe(m, s)[5] for s in (0, 1, 2, 3, 4)] == [0, 64, 128, 64, 0]

    def test_laeufer_bleibt_voll_waehrend_der_untergrund_atmet(self, kanaele):
        m = self._m()
        for s in (0, 1, 2, 3, 4, 5):
            werte = _ausgabe(m, s)
            assert werte[s % _ZELLEN] == 255, (s, werte)
            andere = {w for i, w in enumerate(werte) if i != s % _ZELLEN}
            assert len(andere) == 1, "alle anderen atmen gemeinsam"

    def test_tiefpunkt_hebt_das_tal(self, kanaele):
        m = self._m(untergrund_tief=20)           # 20 % = 51
        tal_bis_gipfel = [_ausgabe(m, s / 10.0)[5] for s in range(0, 41)]
        assert min(tal_bis_gipfel) == 51
        assert max(tal_bis_gipfel) == 128
        assert tal_bis_gipfel[0] == 51 and tal_bis_gipfel[20] == 128

    def test_tiefpunkt_ueber_der_helligkeit_wird_gekappt(self, kanaele):
        m = self._m(untergrund_tief=90)
        assert {_ausgabe(m, s / 4.0)[5] for s in range(0, 17)} == {128}

    def test_tempo_faktor_ist_relativ_zur_uhr_des_effekts(self, kanaele):
        schnell = self._m(untergrund_tempo=2.0)
        assert [_ausgabe(schnell, s)[5] for s in (0, 1, 2)] == [0, 128, 0]
        langsam = self._m(untergrund_tempo=0.5)
        assert [_ausgabe(langsam, s)[5] for s in (0, 2, 4)] == [0, 64, 128]

    def test_laeuft_mit_der_uhr_des_effekts(self, kanaele):
        """Die Uhr ist ``_step`` — dieselbe, die das Lauflicht treibt. Wer das
        Tempo des Effekts verdoppelt, verdoppelt damit auch das Atmen."""
        m = self._m()
        m.matrix_speed = 1.0
        m._step = 0.0
        u = Universe(1)
        m.write({1: u}, _dimmer_reihe(), 2.0)     # zwei Sekunden bei 1 Schritt/s
        assert m._step == pytest.approx(2.0)
        assert u.get_channel(6) == 128
        m.matrix_speed = 2.0
        u = Universe(1)
        m.write({1: u}, _dimmer_reihe(), 1.0)     # eine Sekunde bei 2 Schritten/s
        assert m._step == pytest.approx(4.0)
        assert u.get_channel(6) == 0

    def test_am_tempo_bus_atmet_es_im_takt(self, kanaele):
        """Am Bus zaehlt ``_step`` in Beats: bei 120 BPM ist nach einer Sekunde
        (zwei Beats) der Gipfel erreicht, nach zwei Sekunden wieder das Tal."""
        from src.core.engine.tempo_bus import get_tempo_bus_manager
        bus = get_tempo_bus_manager().bus_for_effect("D")
        assert bus is not None
        alt = bus.bpm
        try:
            bus.set_bpm(120)
            m = self._m()
            m.tempo_bus_id = "D"
            m.tempo_multiplier = 1.0
            m.phase_offset = 0.0
            m._beat_anchor = bus.position()
            m._last_bus_pos = None
            bus.advance_frame(1.0)
            u = Universe(1)
            m.write({1: u}, _dimmer_reihe(), 1.0)
            assert m._step == pytest.approx(2.0, abs=1e-6)
            assert u.get_channel(1) == 128
            bus.advance_frame(1.0)
            u = Universe(1)
            m.write({1: u}, _dimmer_reihe(), 1.0)
            assert m._step == pytest.approx(4.0, abs=1e-6)
            assert u.get_channel(1) == 0
            # Tempo × 2 des Effekts: ab jetzt zwei Schritte je Beat (der Wechsel
            # setzt stetig an der erreichten Stelle fort) — das Atmen zieht mit.
            m.tempo_multiplier = 2.0
            bus.advance_frame(0.25)
            u = Universe(1)
            m.write({1: u}, _dimmer_reihe(), 0.25)
            assert m._step == pytest.approx(5.0, abs=1e-6)
            assert u.get_channel(1) == 64
        finally:
            bus.set_bpm(alt)

    def test_regler_fuer_tempo_und_tiefpunkt_nur_beim_atmen(self):
        m = self._m()
        keys = [s.key for s in m.list_params()]
        assert "untergrund_tempo" in keys and "untergrund_tief" in keys
        m.params["untergrund_art"] = UNTERGRUND_FEST
        keys = [s.key for s in m.list_params()]
        assert "untergrund_tempo" not in keys and "untergrund_tief" not in keys
        m.set_param("untergrund_tempo", 99)
        assert m.get_param("untergrund_tempo") == 4.0
        m.set_param("untergrund_tief", -5)
        assert m.get_param("untergrund_tief") == 0


# ── „Dimmer pro Runde wechseln" ──────────────────────────────────────────────


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
class TestDimmerProRunde:

    def _m(self, **params):
        from src.core.engine.rgb_matrix import DimmerSequence
        m = _lauflicht(dimmer_cycle=True, **params)
        m.dimmer_levels = DimmerSequence([200, 100])
        return m

    def test_altbestand_ignoriert_min_weiterhin(self, kanaele):
        """Eine alte Show mit vergessenem Min-Wert bekommt kein neues Licht."""
        m = self._m()
        m.intensity_min = 51
        assert m.untergrund_art() == UNTERGRUND_AUS
        assert _ausgabe(m, 0) == [200, 0, 0, 0, 0, 0]
        assert _ausgabe(m, 7) == [0, 100, 0, 0, 0, 0]      # zweite Runde, Stufe 100

    def test_fester_wert_wirkt_jetzt_auch_hier(self, kanaele):
        m = self._m(untergrund_art=UNTERGRUND_FEST)
        m.intensity_min = 51
        assert _ausgabe(m, 0) == [200, 51, 51, 51, 51, 51]
        assert _ausgabe(m, 7) == [51, 100, 51, 51, 51, 51]

    def test_schweif_blendet_von_der_stufe_auf_den_untergrund(self, kanaele):
        m = self._m(untergrund_art=UNTERGRUND_FEST, after_fade=50.0)
        m.intensity_min = 51
        werte = _ausgabe(m, 4)
        assert werte[4] == 200
        assert 51 < werte[1] < werte[2] <= werte[3] <= 200, werte
        assert min(werte) == 51

    def test_ohne_untergrund_bleiben_die_stufen_wie_sie_waren(self, kanaele):
        m = self._m(after_fade=50.0)
        for schritt in (0, 1.5, 4, 9):
            m._step = float(schritt)
            roh = m._render(m._step)
            assert _ausgabe(m, schritt) == [max(p) for p in roh]


# ── Altbestand und Show-Format ───────────────────────────────────────────────


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
class TestAltbestand:

    def _alte_show(self) -> dict:
        """Eine Dimmer-Matrix, wie sie vor ENG-34 in einer Show stand."""
        m = RgbMatrixInstance(name="Alt", cols=_ZELLEN, rows=1,
                              fixture_grid=list(range(1, _ZELLEN + 1)),
                              algorithm=RgbAlgorithm.CHASE)
        m.style = MatrixStyle.DIMMER
        m.intensity_min, m.intensity_max = 50, 240
        m.params = {"axis": "H", "movement": "normal", "runner_count": 1,
                    "runner_width": 1, "after_fade": 40.0}
        return json.loads(json.dumps(m.to_dict()))

    def test_min_ueber_null_rechnet_wie_bisher(self, kanaele):
        """Die alte Regel, ausgeschrieben: Helligkeit linear zwischen Min und Max."""
        m = RgbMatrixInstance.from_dict(self._alte_show())
        m.tempo_bus_id = ""
        m.start()
        for schritt in (0, 0.5, 1, 2.25, 3, 5.75, 11):
            m._step = float(schritt)
            roh = m._render(m._step)
            soll = [max(0, min(255, int(round(50 + (240 - 50) * (max(p) / 255.0)))))
                    for p in roh]
            assert _ausgabe(m, schritt) == soll

    def test_wird_als_fester_wert_gezeigt(self):
        m = RgbMatrixInstance.from_dict(self._alte_show())
        assert m.untergrund_art() == UNTERGRUND_FEST
        ohne = self._alte_show()
        ohne["intensity_min"] = 0
        assert RgbMatrixInstance.from_dict(ohne).untergrund_art() == UNTERGRUND_AUS

    def test_laden_und_speichern_ist_byte_gleich(self):
        alt = self._alte_show()
        vorher = json.dumps(alt, ensure_ascii=False)
        assert "untergrund" not in vorher
        nachher = json.dumps(RgbMatrixInstance.from_dict(alt).to_dict(),
                             ensure_ascii=False)
        assert nachher == vorher

    def test_show_format_hat_keine_neuen_pflichtfelder(self):
        """Der Untergrund lebt in ``params`` — ohne ihn kommt kein Schluessel dazu."""
        m = RgbMatrixInstance(name="Neu")
        m.style = MatrixStyle.DIMMER
        d = m.to_dict()
        assert not [k for k in d if "untergrund" in k]
        assert not [k for k in d["params"] if "untergrund" in k]

    def test_spaetere_art_bleibt_beim_speichern_erhalten(self, kanaele):
        """Eine Art, die dieser Stand nicht kennt (z. B. aus einer neueren
        Version), wird nicht umgeschrieben und rechnet als fester Wert."""
        alt = self._alte_show()
        alt["params"]["untergrund_art"] = "funkeln"
        m = RgbMatrixInstance.from_dict(alt)
        assert m.to_dict()["params"]["untergrund_art"] == "funkeln"
        assert m.untergrund_art() == UNTERGRUND_FEST
        m.tempo_bus_id = ""
        m.params["after_fade"] = 0.0
        m.start()
        assert _ausgabe(m, 0) == [240, 50, 50, 50, 50, 50]


# ── Vorschau = Ausgabe ───────────────────────────────────────────────────────


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
@pytest.mark.parametrize("params,pegel", [
    ({}, 0),
    ({}, 51),
    ({"untergrund_art": UNTERGRUND_FEST}, 51),
    ({"untergrund_art": UNTERGRUND_ATMEN}, 128),
    ({"untergrund_art": UNTERGRUND_ATMEN, "untergrund_tief": 10,
      "untergrund_tempo": 2.0}, 200),
    ({"untergrund_art": UNTERGRUND_FEST, "dimmer_cycle": True}, 51),
    ({"dimmer_cycle": True}, 51),
])
def test_vorschau_zeigt_dasselbe_wie_die_ausgabe(kanaele, params, pegel):
    m = _lauflicht(after_fade=40.0, **params)
    m.intensity_min = pegel
    for schritt in (0, 0.3, 1, 1.7, 2, 3.5, 6, 13.25):
        echt = _ausgabe(m, schritt)
        vorschau = [p[0] for p in m.preview_pixels()]
        assert vorschau == echt, (params, pegel, schritt)


# ── Virtuelle Konsole: Regler „Dimmer min" ───────────────────────────────────


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
class TestKonsoleRegler:

    def test_dimmer_min_ist_noch_da_und_meint_den_untergrund(self):
        m = _lauflicht()
        spec = {s.key: s for s in m.list_params()}["intensity_min"]
        assert spec.label == "Dimmer min"
        assert (spec.min, spec.max, spec.kind) == (0, 255, "int")

    def test_regler_auf_zwanzig_prozent_ist_zwanzig_prozent_untergrund(self, kanaele):
        """Der Regler laeuft 0..255 und zeigt Prozent; ``effect_live`` legt das
        linear auf 0..255 — dieselbe Skala wie „Helligkeit" im Editor."""
        from src.core.engine import effect_live
        from src.core.engine.function_manager import get_function_manager
        fm = get_function_manager()
        m = _lauflicht()
        fm.add(m)
        try:
            regler = int(round(0.20 * 255))                  # Regler auf 20 %
            assert effect_live.set_param_normalized(
                "intensity_min", regler / 255.0, m.id)
            assert m.intensity_min == 51
            assert m.untergrund_art() == UNTERGRUND_FEST
            assert _ausgabe(m, 0) == [255, 51, 51, 51, 51, 51]
            # Editor-Anzeige dazu: 51 von 255 sind 20 %.
            assert int(round(m.intensity_min * 100.0 / 255.0)) == 20
        finally:
            m.stop()
            fm.remove(m.id)

    def test_regler_stellt_beim_atmen_die_helligkeit(self, kanaele):
        from src.core.engine import effect_live
        from src.core.engine.function_manager import get_function_manager
        fm = get_function_manager()
        m = _lauflicht(untergrund_art=UNTERGRUND_ATMEN)
        fm.add(m)
        try:
            effect_live.set_param_normalized("intensity_min", 1.0, m.id)
            assert _ausgabe(m, 2)[5] == 255                  # Gipfel des Atemzugs
            assert _ausgabe(m, 0)[5] == 0
            assert effect_live.set_param_normalized("untergrund_tempo", 1.0, m.id)
            assert m.params["untergrund_tempo"] == 4.0
        finally:
            m.stop()
            fm.remove(m.id)


# ── Mehrkopf-Geraet mit geteiltem Dimmer ─────────────────────────────────────


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
class TestGeteilterDimmer:
    """Zwei Geraete mit je drei Farbkoepfen und EINEM gemeinsamen Dimmer.
    Jeder Kopf ist eine Zelle — drei Zellen schreiben denselben Kanal."""

    def _aufbau(self, **params):
        def koepfe():
            k = [_Ch("intensity", 1)]
            for h in range(3):
                k += [_Ch("color_r", 2 + h * 3), _Ch("color_g", 3 + h * 3),
                      _Ch("color_b", 4 + h * 3)]
            return k
        patch = [_Fx(10, 1, koepfe()), _Fx(11, 21, koepfe())]
        m = _lauflicht(**params)
        m.fixture_grid = [10, 10, 10, 11, 11, 11]
        m.head_grid = [0, 1, 2, 0, 1, 2]
        return m, patch

    def _dimmer(self, m, patch, schritt):
        m._step = float(schritt)
        u = Universe(1)
        m.write({1: u}, patch, 0.0)
        return u.get_channel(1), u.get_channel(21)

    def test_hoechster_wert_der_zellen_gewinnt(self, kanaele):
        m, patch = self._aufbau(untergrund_art=UNTERGRUND_FEST)
        m.intensity_min = 51
        # Laeufer auf Kopf 0, 1, 2 des ersten Geraets: dessen Dimmer ist voll,
        # egal welche Zelle zuletzt geschrieben hat; das zweite steht auf Untergrund.
        for schritt in (0, 1, 2):
            assert self._dimmer(m, patch, schritt) == (255, 51), schritt
        for schritt in (3, 4, 5):
            assert self._dimmer(m, patch, schritt) == (51, 255), schritt

    def test_ohne_untergrund_gilt_dieselbe_regel(self, kanaele):
        m, patch = self._aufbau()
        assert self._dimmer(m, patch, 0) == (255, 0)
        assert self._dimmer(m, patch, 4) == (0, 255)

    def test_atmen_auf_dem_geteilten_dimmer(self, kanaele):
        m, patch = self._aufbau(untergrund_art=UNTERGRUND_ATMEN)
        m.intensity_min = 128
        assert self._dimmer(m, patch, 2) == (255, 128)
        assert self._dimmer(m, patch, 4) == (0, 255)

    def test_ganze_geraete_schreiben_wie_bisher(self, kanaele):
        """Ohne Kopf-Angabe bleibt es beim alten Weg (letzte Zelle schreibt)."""
        m, patch = self._aufbau()
        m.head_grid = []
        assert self._dimmer(m, patch, 0) == (0, 0)      # Zelle 2 ueberschreibt Zelle 0
        assert self._dimmer(m, patch, 2) == (255, 0)


# ── Editor ───────────────────────────────────────────────────────────────────


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _ansicht(pegel: int = 0, **params):
    """Matrix-Ansicht mit einer eigenen Dimmer-Lauflicht-Matrix, so geladen,
    als kaeme sie aus einer Show."""
    from src.ui.views.rgb_matrix_view import RgbMatrixView
    ansicht = RgbMatrixView()
    ansicht._add()
    m = ansicht._saved
    assert m is not None
    m.algorithm = RgbAlgorithm.CHASE
    m.style = MatrixStyle.DIMMER
    m.intensity_min = pegel
    m.params = {"axis": "H", "movement": "normal", "runner_count": 1,
                "runner_width": 1, "after_fade": 30.0}
    m.params.update(params)
    ansicht._select(ansicht._list.currentRow())
    assert ansicht._current is not None
    return ansicht


def _felder(ansicht):
    return (ansicht._ug_art_combo, ansicht._ug_hell_spin, ansicht._ug_tief_spin,
            ansicht._ug_tempo_spin)


def _art_waehlen(ansicht, art):
    box = ansicht._ug_art_combo
    box.setCurrentIndex(box.findData(art))


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
class TestEditor:

    def test_gruppe_und_felder_sind_da(self):
        _app()
        ansicht = _ansicht()
        assert ansicht._grp_untergrund.title() == "Untergrund"
        box = ansicht._ug_art_combo
        assert [box.itemText(i) for i in range(box.count())] == [
            "Aus", "Fester Wert", "Atmen"]
        assert ansicht._ug_hell_spin.suffix() == " %"
        assert ansicht._ug_hell_spin.maximum() == 100
        assert not ansicht._grp_untergrund.isHidden()
        ansicht.deleteLater()

    def test_nur_beim_dimmer_stil(self):
        _app()
        ansicht = _ansicht()
        ansicht._style_combo.setCurrentText(MatrixStyle.RGB.value)
        assert ansicht._grp_untergrund.isHidden()
        ansicht._style_combo.setCurrentText(MatrixStyle.DIMMER.value)
        assert not ansicht._grp_untergrund.isHidden()
        ansicht.deleteLater()

    def test_art_blendet_felder_nur_ein_und_aus(self):
        import shiboken6
        _app()
        ansicht = _ansicht()
        vorher = _felder(ansicht)
        assert ansicht._ug_art_combo.currentData() == UNTERGRUND_AUS
        assert ansicht._ug_hell_spin.isHidden()
        assert ansicht._ug_tief_spin.isHidden() and ansicht._ug_tempo_spin.isHidden()

        _art_waehlen(ansicht, UNTERGRUND_FEST)
        assert not ansicht._ug_hell_spin.isHidden()
        assert ansicht._ug_tief_spin.isHidden() and ansicht._ug_tempo_spin.isHidden()

        _art_waehlen(ansicht, UNTERGRUND_ATMEN)
        assert not ansicht._ug_hell_spin.isHidden()
        assert not ansicht._ug_tief_spin.isHidden()
        assert not ansicht._ug_tempo_spin.isHidden()
        assert not ansicht._ug_tempo_label.isHidden()

        _art_waehlen(ansicht, UNTERGRUND_AUS)
        assert ansicht._ug_hell_spin.isHidden() and ansicht._ug_tempo_spin.isHidden()
        # Dieselben Widgets wie am Anfang — nichts wurde neu gebaut oder geloescht.
        assert _felder(ansicht) == vorher
        assert all(shiboken6.isValid(w) for w in vorher)
        ansicht.deleteLater()

    def test_fester_wert_schreibt_art_und_pegel_in_prozent(self):
        _app()
        ansicht = _ansicht()
        _art_waehlen(ansicht, UNTERGRUND_FEST)
        m = ansicht._current
        assert m.params["untergrund_art"] == UNTERGRUND_FEST
        assert m.intensity_min == 51, "Start bei 20 %, sonst saehe man nichts"
        assert ansicht._ug_hell_spin.value() == 20
        ansicht._ug_hell_spin.setValue(40)
        assert m.intensity_min == 102
        assert ansicht._btn_save.isEnabled()
        ansicht._save_edit()
        assert ansicht._saved.intensity_min == 102
        assert ansicht._saved.params["untergrund_art"] == UNTERGRUND_FEST
        ansicht.deleteLater()

    def test_atmen_schreibt_tempo_und_tiefpunkt(self):
        _app()
        ansicht = _ansicht()
        _art_waehlen(ansicht, UNTERGRUND_ATMEN)
        m = ansicht._current
        assert m.params["untergrund_art"] == UNTERGRUND_ATMEN
        assert "untergrund_tempo" not in m.params, "Vorgabe wird nicht mitgespeichert"
        ansicht._ug_tempo_spin.setValue(2.0)
        ansicht._ug_tief_spin.setValue(10)
        assert m.params["untergrund_tempo"] == 2.0
        assert m.params["untergrund_tief"] == 10
        ansicht.deleteLater()

    def test_aus_raeumt_wieder_auf(self):
        _app()
        ansicht = _ansicht()
        vorher = json.dumps(ansicht._editor_dict(ansicht._current), sort_keys=True)
        _art_waehlen(ansicht, UNTERGRUND_ATMEN)
        ansicht._ug_tempo_spin.setValue(2.0)
        _art_waehlen(ansicht, UNTERGRUND_AUS)
        m = ansicht._current
        assert not [k for k in m.params if "untergrund" in k]
        assert m.intensity_min == 0
        assert json.dumps(ansicht._editor_dict(m), sort_keys=True) == vorher
        assert not ansicht._btn_save.isEnabled(), "kein Aenderungs-Hinweis ohne Aenderung"
        ansicht.deleteLater()

    def test_alte_show_wird_als_fester_wert_gezeigt(self):
        _app()
        ansicht = _ansicht(pegel=50)
        assert ansicht._ug_art_combo.currentData() == UNTERGRUND_FEST
        assert ansicht._ug_hell_spin.value() == 20         # 50 von 255
        assert not ansicht._ug_hell_spin.isHidden()
        assert not ansicht._btn_save.isEnabled(), "Laden allein ist keine Aenderung"
        ansicht.deleteLater()

    def test_alte_show_bleibt_beim_bearbeiten_anderer_felder_byte_gleich(self):
        """Min 50 sind 19,6 % — die Anzeige rundet, der gespeicherte Wert nicht."""
        _app()
        ansicht = _ansicht(pegel=50)
        # Einmal durch den Editor speichern: er schreibt von sich aus die
        # Vorgaben der sichtbaren Felder (z. B. „Invertieren") aus — das tat er
        # schon immer und ist hier nicht das Thema.
        ansicht._param_change()
        ansicht._save_edit()
        vorher = json.dumps(ansicht._saved.to_dict(), ensure_ascii=False)
        assert "untergrund" not in vorher
        alt_tempo = ansicht._speed_spin.value()
        ansicht._speed_spin.setValue(alt_tempo + 1.0)
        ansicht._param_change()
        assert ansicht._current.intensity_min == 50
        assert not [k for k in ansicht._current.params if "untergrund" in k]
        ansicht._speed_spin.setValue(alt_tempo)
        ansicht._param_change()
        ansicht._save_edit()
        assert json.dumps(ansicht._saved.to_dict(), ensure_ascii=False) == vorher
        ansicht.deleteLater()

    def test_unter_dimmer_pro_runde_zeigt_der_altbestand_aus(self):
        """Dort war Min bisher wirkungslos — der Editor behauptet nichts anderes.
        Wer „Fester Wert" waehlt, schaltet ihn ausdruecklich ein."""
        _app()
        ansicht = _ansicht(pegel=50, dimmer_cycle=True)
        assert ansicht._ug_art_combo.currentData() == UNTERGRUND_AUS
        assert not ansicht._grp_untergrund.isHidden()
        _art_waehlen(ansicht, UNTERGRUND_FEST)
        assert ansicht._current.params["untergrund_art"] == UNTERGRUND_FEST
        assert ansicht._current.intensity_min == 50, "vorhandener Pegel bleibt"
        ansicht.deleteLater()

    def test_min_feld_steht_nicht_mehr_bei_den_farben(self):
        _app()
        ansicht = _ansicht()
        assert ansicht._imin_spin.isHidden()
        assert not ansicht._imax_spin.isHidden()
        _art_waehlen(ansicht, UNTERGRUND_FEST)
        assert ansicht._imin_spin.isHidden(), "der Wert-Traeger bleibt unsichtbar"
        ansicht.deleteLater()


# ── Editor: Umschalten der Art als Schleife im Kindprozess ───────────────────


@pytest.mark.skipif(not _ROLLE, reason="laeuft nur als Kindprozess des Schleifen-Tests")
@pytest.mark.timeout(100)
def test_arbeiter():
    """Kindprozess: echte Ansicht (offscreen), die Art so umstellen wie am
    Bildschirm — Aufklappliste oeffnen, Eintrag anklicken. Endet mit Exit 0
    und der Marke, oder stirbt mit dem Absturz, den der Elternprozess meldet."""
    import faulthandler
    faulthandler.enable()
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    _app()
    ansicht = _ansicht()
    ansicht.resize(1400, 900)
    ansicht.show()
    QTest.qWait(50)
    folge = (UNTERGRUND_FEST, UNTERGRUND_ATMEN, UNTERGRUND_AUS, UNTERGRUND_ATMEN,
             UNTERGRUND_FEST)
    for nr in range(int(os.environ.get("ENG34_UMSTELLUNGEN", "20"))):
        art = folge[nr % len(folge)]
        box = ansicht._ug_art_combo
        zeile = box.findData(art)
        print("STELLE", nr, art, flush=True)
        box.showPopup()
        QTest.qWait(30)
        liste = box.view()
        mitte = liste.visualRect(liste.model().index(zeile, 0)).center()
        QTest.mouseMove(liste.viewport(), mitte)
        QTest.mouseClick(liste.viewport(), Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, mitte)
        QTest.qWait(30)
        assert ansicht._current.untergrund_art() == art
        assert ansicht._ug_tempo_spin.isVisible() == (art == UNTERGRUND_ATMEN)
        assert ansicht._ug_hell_spin.isVisible() == (art != UNTERGRUND_AUS)
    print(_MARKE, flush=True)
    sys.stdout.flush()
    os._exit(0)     # geprueft wird die Schleife, nicht der Abbau am Prozessende


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
@pytest.mark.timeout(115)
def test_art_zwanzigmal_umschalten_stuerzt_nicht_ab(tmp_path):
    """Nach dem Muster von STAB-38: eigener Prozess, freigegebener Speicher wird
    sofort ueberschrieben — ein Zugriff auf ein geloeschtes Feld fiele auf."""
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["ENG34_ARBEITER"] = "liste"
    env["ENG34_UMSTELLUNGEN"] = "20"
    env["LIGHTOS_SHOW_DB"] = str(tmp_path / "show.db")
    env["LIGHTOS_CRASH_LOG"] = str(tmp_path / "crash.log")
    daten = tmp_path / "daten"
    daten.mkdir(exist_ok=True)
    env["XDG_DATA_HOME"] = str(daten)
    env["APPDATA"] = str(daten)
    env["GLIBC_TUNABLES"] = "glibc.malloc.tcache_count=0:glibc.malloc.perturb=165"
    for key in ("LIGHTOS_UNIVERSES_JSON", "LIGHTOS_SACN_CID", "PYTEST_CURRENT_TEST"):
        env.pop(key, None)
    fertig = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "-s",
         "-p", "no:cacheprovider", "-o", "addopts=",
         f"tests/{Path(__file__).name}::test_arbeiter"],
        cwd=str(REPO), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=105)
    aus = (fertig.stdout or "") + "\n" + (fertig.stderr or "")
    schritte = len(re.findall(r"^STELLE ", aus, flags=re.M))
    assert fertig.returncode == 0 and _MARKE in aus, (
        f"Kindprozess endete mit {fertig.returncode} nach {schritte} "
        f"Umstellungen — nativer Absturz oder Fehler:\n{aus[-3000:]}")
    assert schritte == 20
