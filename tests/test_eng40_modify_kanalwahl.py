"""ENG-40: Kanalwahl eines Farb-Modify („Wirkt auf").

Regel (src/core/engine/modify.py, RgbMatrixInstance._modify_kanalwahl):

* ``modify_channels`` leer = Vorgabe: die Modify-FARBE bestimmt die Kanaele —
  genau das ENG-38-Verhalten, byte-gleich.
* Sind Kanaele angekreuzt (Rot, Gruen, Blau, Weiss, Amber, UV), veraendert der
  Modify-Effekt NUR diese Kanaele, je Kanal um die HELLIGKEIT des Effekts an
  der Lampe mal Staerke, in der eingestellten Betriebsart.
* Ein Geraet ohne den Kanal bleibt unberuehrt — es wird nichts umgerechnet
  (Weiss nicht auf Rot/Gruen/Blau).
* Der Dimmer wird nie angefasst; „nur Dimmer" ist der Stil Dimmer (ENG-37),
  dort wirkt die Kanalwahl nicht.

Gemessen werden DMX-Werte nach dem echten ``FunctionManager.tick`` ueber einem
vorbelegten Bild.
"""
from __future__ import annotations

import itertools
import os
from types import SimpleNamespace as N

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                    # noqa: E402

import src.core.app_state as AS                                  # noqa: E402
from src.core.dmx.universe import Universe                       # noqa: E402
from src.core.engine.function_manager import FunctionManager    # noqa: E402
from src.core.engine.modify import (                             # noqa: E402
    MODIFY_KANAELE, MODIFY_KANAL_ATTR, MODIFY_KANAL_LABELS, MODIFY_MODES,
    modify_posten, modify_wert, normalize_channels)
from src.core.engine.rgb_matrix import (                         # noqa: E402
    MatrixStyle, RgbAlgorithm, RgbMatrixInstance)

FARBSTILE = [MatrixStyle.RGB, MatrixStyle.RGBW]

# Bild darunter je Attribut — bewusst lauter verschiedene Werte, damit ein
# vertauschter Kanal auffaellt.
DARUNTER = {"intensity": 77, "color_r": 30, "color_g": 60, "color_b": 250,
            "color_w": 180, "color_a": 90, "color_uv": 120,
            "color_wheel": 40, "shutter": 200}

RGBW = ("intensity", "color_r", "color_g", "color_b", "color_w")
RGB = ("intensity", "color_r", "color_g", "color_b")
RGB_OHNE_DIMMER = ("color_r", "color_g", "color_b")
RGBWAUV = ("intensity", "color_r", "color_g", "color_b", "color_w",
           "color_a", "color_uv")
RAD = ("intensity", "color_wheel")


def _ch(attr, nr):
    return N(attribute=attr, channel_number=nr, default_value=0,
             highlight_value=255, ranges=[], name=attr)


def _kanaele(attrs):
    return [_ch(a, i + 1) for i, a in enumerate(attrs)]


def _fx(kanaele, fid=1, address=1):
    return N(fid=fid, universe=1, address=address, fixture_type="par",
             fixture_profile_id=1, mode_name="m", channel_count=len(kanaele))


def _matrix(wahl, mode="add", staerke=100, farbe=(255, 255, 255),
            stil=MatrixStyle.RGB, **felder):
    m = RgbMatrixInstance("ENG40", cols=1, rows=1, fixture_grid=[1],
                          algorithm=RgbAlgorithm.PLAIN, color1=farbe)
    m.style = stil
    m.tempo_bus_id = ""
    m.modify, m.modify_mode, m.modify_strength = True, mode, staerke
    m.modify_channels = tuple(wahl)
    for k, v in felder.items():
        setattr(m, k, v)
    return m


def _lauf(monkeypatch, attrs, matrix, darunter=None):
    """Ein Frame des Modify-Effekts ueber dem vorbelegten Bild ->
    ``{attribut: wert}`` (bei mehrfachen Attributen eine Liste)."""
    kanaele = _kanaele(attrs)
    monkeypatch.setattr(AS, "get_channels_for_patched", lambda fx: kanaele)
    unten = dict(DARUNTER)
    unten.update(darunter or {})
    fm = FunctionManager()
    fm.add(matrix)
    fm.start(matrix.id)
    uni = Universe(1)
    for c in kanaele:
        uni.set_channel(c.channel_number, unten[c.attribute])
    fm.tick({1: uni}, [_fx(kanaele)], 0.02)
    roh = uni.get_all()
    aus: dict = {}
    for c in kanaele:
        aus.setdefault(c.attribute, []).append(roh[c.channel_number - 1])
    return {a: (v[0] if len(v) == 1 else v) for a, v in aus.items()}


def _unveraendert(attrs, ausser=()):
    return {a: DARUNTER[a] for a in attrs if a not in ausser}


# ── Die Faelle aus dem Wunsch des Betreibers ─────────────────────────────────

@pytest.mark.parametrize("stil", FARBSTILE)
@pytest.mark.parametrize("farbe", [(255, 255, 255), (255, 0, 0), (0, 0, 255)])
def test_rgbw_abziehen_nur_weiss_senkt_nur_weiss(monkeypatch, stil, farbe):
    """„Du bist ein Modifier nur fuer den Weiss-Kanal": nur W sinkt — egal,
    in welchem Farb-Stil und mit welchem Farbton der Effekt laeuft."""
    bild = _lauf(monkeypatch, RGBW,
                 _matrix(["w"], "sub", 50, farbe=farbe, stil=stil))
    erwartet = _unveraendert(RGBW)
    erwartet["color_w"] = modify_wert("sub", 180, 255, 0.5)
    assert erwartet["color_w"] == 52
    assert bild == erwartet


@pytest.mark.parametrize("stil", FARBSTILE)
def test_nur_rot_addieren_auf_blauer_grundfarbe(monkeypatch, stil):
    """Blau darunter, Modify „Addieren" nur Rot: Rot kommt dazu; Blau, Gruen,
    Weiss und der Dimmer bleiben exakt stehen."""
    blau = {"color_r": 0, "color_g": 0, "color_b": 255, "color_w": 0}
    bild = _lauf(monkeypatch, RGBW, _matrix(["r"], "add", 100, stil=stil),
                 darunter=blau)
    assert bild == {"intensity": 77, "color_r": 255, "color_g": 0,
                    "color_b": 255, "color_w": 0}
    halb = _lauf(monkeypatch, RGBW, _matrix(["r"], "add", 40, stil=stil),
                 darunter=blau)
    assert halb == {"intensity": 77, "color_r": 102, "color_g": 0,
                    "color_b": 255, "color_w": 0}


@pytest.mark.parametrize("stil", FARBSTILE)
@pytest.mark.parametrize("mode", MODIFY_MODES)
@pytest.mark.parametrize("attrs", [RGB, RGB_OHNE_DIMMER, RAD])
def test_geraet_ohne_weiss_bleibt_bei_nur_weiss_unberuehrt(monkeypatch, stil,
                                                           mode, attrs):
    """RGB-Strahler ohne Weiss-Kanal und „nur Weiss": es passiert nichts —
    kein Umrechnen auf Rot/Gruen/Blau, kein Posten."""
    m = _matrix(["w"], mode, 100, stil=stil)
    assert _lauf(monkeypatch, attrs, m) == _unveraendert(attrs)
    kanaele = _kanaele(attrs)
    monkeypatch.setattr(AS, "get_channels_for_patched", lambda fx: kanaele)
    m2 = _matrix(["w"], mode, 100, stil=stil)
    m2._running = True
    assert modify_posten(m2, {1: Universe(1)}, [_fx(kanaele)], 0.02) is None


# ── Jede Auswahl: genau diese Kanaele, sonst nichts ──────────────────────────

_ALLE_WAHLEN = [w for n in range(1, len(MODIFY_KANAELE) + 1)
                for w in itertools.combinations(MODIFY_KANAELE, n)]


@pytest.mark.parametrize("wahl", _ALLE_WAHLEN,
                         ids=["+".join(w) for w in _ALLE_WAHLEN])
def test_jede_auswahl_trifft_genau_ihre_kanaele(monkeypatch, wahl):
    """Alle 63 Kombinationen an einem Geraet mit Rot, Gruen, Blau, Weiss,
    Amber, UV: verrechnet werden genau die angekreuzten Kanaele."""
    for mode, stil in itertools.product(MODIFY_MODES, FARBSTILE):
        bild = _lauf(monkeypatch, RGBWAUV,
                     _matrix(wahl, mode, 50, farbe=(200, 10, 90), stil=stil))
        erwartet = _unveraendert(RGBWAUV)
        for k in wahl:
            a = MODIFY_KANAL_ATTR[k]
            # Betrag = Helligkeit der Zelle = groesster Farbanteil (200).
            erwartet[a] = modify_wert(mode, DARUNTER[a], 200, 0.5)
        assert bild == erwartet, (wahl, mode, stil)


@pytest.mark.parametrize("wahl", _ALLE_WAHLEN,
                         ids=["+".join(w) for w in _ALLE_WAHLEN])
def test_dimmer_und_fremde_kanaele_stehen_nie_im_posten(monkeypatch, wahl):
    """Der Posten nennt ausschliesslich Adressen angekreuzter Farbkanaele —
    auch bei „Dimmer mitziehen". Farbe und Dimmer bleiben getrennt."""
    attrs = RGBWAUV + ("shutter", "color_wheel")
    kanaele = _kanaele(attrs)
    monkeypatch.setattr(AS, "get_channels_for_patched", lambda fx: kanaele)
    erlaubt = {c.channel_number for c in kanaele
               if c.attribute in {MODIFY_KANAL_ATTR[k] for k in wahl}}
    for stil, drive in itertools.product(FARBSTILE, (False, True)):
        m = _matrix(wahl, stil=stil, drive_intensity=drive)
        m._running = True
        posten = modify_posten(m, {1: Universe(1)}, [_fx(kanaele)], 0.02)
        assert posten is not None
        adressen = {adr for adr, _betrag in posten[2][1]}
        assert adressen == erlaubt, (wahl, stil, drive)


def test_betrag_ist_die_helligkeit_des_effekts(monkeypatch):
    """Der Farbton zaehlt bei getroffener Auswahl nicht, die Helligkeit schon:
    halbe Helligkeit = halber Betrag, Schwarz = kein Betrag."""
    for farbe, betrag in (((255, 255, 255), 255), ((0, 255, 0), 255),
                          ((128, 0, 0), 128), ((10, 64, 20), 64),
                          ((0, 0, 0), 0)):
        bild = _lauf(monkeypatch, RGBW,
                     _matrix(["w"], "sub", 100, farbe=farbe))
        erwartet = _unveraendert(RGBW)
        erwartet["color_w"] = max(0, 180 - betrag)
        assert bild == erwartet, farbe


def test_effekt_helligkeit_wirkt_genau_einmal_auf_die_staerke(monkeypatch):
    for drive in (False, True):
        bild = _lauf(monkeypatch, RGBW,
                     _matrix(["r", "w"], "add", 100, intensity=0.5,
                             drive_intensity=drive))
        erwartet = _unveraendert(RGBW)
        erwartet["color_r"] = modify_wert("add", 30, 255, 0.5)
        erwartet["color_w"] = modify_wert("add", 180, 255, 0.5)
        assert bild == erwartet, drive


def test_schweif_wird_auch_mit_kanalwahl_mit_verrechnet(monkeypatch):
    """Lauflicht mit Schweif, nur Weiss: Kopf voll, Schweif anteilig, Rest 0."""
    attrs = ("color_r", "color_g", "color_b", "color_w")
    kanaele = _kanaele(attrs)
    monkeypatch.setattr(AS, "get_channels_for_patched", lambda fx: kanaele)
    m = RgbMatrixInstance("ENG40-L", cols=8, rows=1,
                          fixture_grid=list(range(1, 9)),
                          algorithm=RgbAlgorithm.CHASE, color1=(255, 0, 0))
    m.style = MatrixStyle.RGB
    m.tempo_bus_id = ""
    m.matrix_speed = 0.0
    m.params.update({"runner_count": 1, "runner_width": 1,
                     "movement": "normal", "after_fade": 60.0, "offset": 4.0})
    m.modify, m.modify_mode, m.modify_channels = True, "add", ("w",)
    fm = FunctionManager()
    fm.add(m)
    fm.start(m.id)
    uni = Universe(1)
    fm.tick({1: uni}, [_fx(kanaele, fid=i, address=1 + (i - 1) * 4)
                       for i in range(1, 9)], 0.02)
    roh = uni.get_all()
    weiss = [roh[i * 4 + 3] for i in range(8)]
    assert max(weiss) == 255 and any(0 < v < 255 for v in weiss), weiss
    assert all(roh[i * 4 + k] == 0 for i in range(8) for k in range(3)), (
        "Rot/Gruen/Blau wurden trotz „nur Weiss“ veraendert")


# ── Vorgabe: byte-gleich zum bisherigen Verhalten ────────────────────────────

@pytest.mark.parametrize("stil", FARBSTILE)
@pytest.mark.parametrize("mode", MODIFY_MODES)
def test_ohne_auswahl_gilt_die_modify_farbe_wie_bisher(monkeypatch, stil, mode):
    """Vorgabe: Rot 255, Gruen 128, Blau 128 teilt sich im Stil RGBW in Weiss
    128 und Rot 127 (ENG-38); im Stil RGB bleibt der Weiss-Kanal stehen."""
    bild = _lauf(monkeypatch, RGBW,
                 _matrix((), mode, 100, farbe=(255, 128, 128), stil=stil))
    if stil == MatrixStyle.RGBW:
        betrag = {"color_r": 127, "color_g": 0, "color_b": 0, "color_w": 128}
    else:
        betrag = {"color_r": 255, "color_g": 128, "color_b": 128, "color_w": 0}
    erwartet = {"intensity": 77}
    for a, w in betrag.items():
        erwartet[a] = modify_wert(mode, DARUNTER[a], w, 1.0)
    assert bild == erwartet


@pytest.mark.parametrize("leer", [(), [], None, "", ["x"], "dimmer", 7])
def test_leere_und_unlesbare_auswahl_ist_die_vorgabe(monkeypatch, leer):
    """Jede leere/unlesbare Kanalwahl verhaelt sich Byte fuer Byte wie eine
    Matrix, die das Feld gar nicht kennt (Alt-Show)."""
    for stil, mode, farbe in itertools.product(
            FARBSTILE, MODIFY_MODES, [(255, 255, 255), (200, 40, 90)]):
        alt = _matrix((), mode, 70, farbe=farbe, stil=stil)
        del alt.modify_channels          # Instanz aus der Zeit vor ENG-40
        assert "modify_channels" not in vars(alt)
        neu = _matrix((), mode, 70, farbe=farbe, stil=stil)
        neu.modify_channels = leer
        assert (_lauf(monkeypatch, RGBWAUV, neu)
                == _lauf(monkeypatch, RGBWAUV, alt)), (leer, stil, mode)


def test_weisse_modify_farbe_trifft_bei_rgbw_weiter_nur_den_weiss_kanal(
        monkeypatch):
    """Bestaetigt vom Betreiber: das bleibt die Vorgabe."""
    bild = _lauf(monkeypatch, RGBW,
                 _matrix((), "sub", 100, stil=MatrixStyle.RGBW))
    erwartet = _unveraendert(RGBW)
    erwartet["color_w"] = 0
    assert bild == erwartet


# ── Grenzen ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("mode", MODIFY_MODES)
def test_im_stil_dimmer_wirkt_die_kanalwahl_nicht(monkeypatch, mode):
    """„Nur Dimmer" ist der Stil Dimmer. Dort verrechnet der Modify-Effekt
    den Dimmer wie in ENG-37 — eine gemerkte Kanalwahl aendert nichts und
    zieht keine Farbe mit."""
    mit = _lauf(monkeypatch, RGBW,
                _matrix(["r", "w"], mode, 100, stil=MatrixStyle.DIMMER))
    ohne = _lauf(monkeypatch, RGBW,
                 _matrix((), mode, 100, stil=MatrixStyle.DIMMER))
    assert mit == ohne
    erwartet = _unveraendert(RGBW)
    erwartet["intensity"] = modify_wert(mode, 77, 255, 1.0)
    assert mit == erwartet
    assert _matrix(["w"], stil=MatrixStyle.DIMMER)._modify_kanalwahl() == frozenset()


def test_ohne_haken_ist_die_kanalwahl_wirkungslos(monkeypatch):
    """Gemerkte Auswahl, Haken entfernt: der Effekt laeuft als ganz normaler
    Farb-Effekt und SETZT seine Farbe."""
    m = _matrix(["w"], farbe=(10, 20, 30), stil=MatrixStyle.RGB)
    m.modify = False
    m.drive_intensity = False
    bild = _lauf(monkeypatch, RGBW, m)
    assert (bild["color_r"], bild["color_g"], bild["color_b"]) == (10, 20, 30)
    assert bild["color_w"] == DARUNTER["color_w"]


def test_geraet_nur_mit_farbrad_bleibt_unberuehrt(monkeypatch):
    for wahl in (["r"], ["w"], list(MODIFY_KANAELE)):
        assert (_lauf(monkeypatch, RAD, _matrix(wahl))
                == _unveraendert(RAD)), wahl


@pytest.mark.parametrize("mode", MODIFY_MODES)
def test_kopf_zelle_trifft_nur_den_gewaehlten_kanal_ihres_kopfes(monkeypatch,
                                                                mode):
    """Vier RGBW-Koepfe, Zelle auf Kopf 2, nur Weiss: allein das Weiss von
    Kopf 2 wird verrechnet; alle anderen Kanaele und der Master bleiben."""
    attrs = ("intensity",) + ("color_r", "color_g", "color_b", "color_w") * 4
    m = _matrix(["w"], mode, 100, drive_intensity=True)
    m.cols, m.rows = 2, 1
    m.fixture_grid = [1, None]
    m.head_grid = [2, None]
    bild = _lauf(monkeypatch, attrs, m)
    neu = modify_wert(mode, 180, 255, 1.0)
    assert bild["intensity"] == 77
    assert bild["color_w"] == [180, 180, neu, 180]
    assert bild["color_r"] == [30] * 4
    assert bild["color_g"] == [60] * 4
    assert bild["color_b"] == [250] * 4


def _leiste():
    """Ein Dimmer, vier RGB-Koepfe, zwei EIGENE Weiss-Segmente (Weiss gehoert
    hier nicht zur Farbzelle — ENG-25/FM-41)."""
    return ("intensity",) + ("color_r", "color_g", "color_b") * 4 + (
        "color_w", "color_w")


def _leisten_matrix(wahl, mode):
    m = _matrix(wahl, mode, 100, drive_intensity=True)
    m.cols, m.rows = 2, 1
    m.fixture_grid = [1, None]
    m.head_grid = [None, None]
    m.weiss_grid = [None, (1, 0)]
    m._render = lambda phase: [(255, 255, 255)] * 2
    return m


@pytest.mark.parametrize("mode", MODIFY_MODES)
def test_eigene_weiss_leiste_nur_weiss_faehrt_die_weiss_zelle(monkeypatch, mode):
    """Nur Weiss an einem Geraet mit eigener Weiss-Leiste: verrechnet wird das
    Segment der Weiss-ZELLE. Die Farbzelle fasst das Weiss nicht an (dieselbe
    Regel wie ENG-25) und veraendert auch keine Farbe."""
    bild = _lauf(monkeypatch, _leiste(), _leisten_matrix(["w"], mode))
    assert bild["intensity"] == 77
    assert bild["color_w"] == [modify_wert(mode, 180, 255, 1.0), 180]
    assert (bild["color_r"], bild["color_g"], bild["color_b"]) == (
        [30] * 4, [60] * 4, [250] * 4)


@pytest.mark.parametrize("mode", MODIFY_MODES)
def test_eigene_weiss_leiste_bleibt_ohne_weiss_in_der_auswahl_stehen(
        monkeypatch, mode):
    """Nur Rot: die Weiss-Zelle schreibt nichts, Rot aller Koepfe wird
    verrechnet, Gruen und Blau bleiben."""
    bild = _lauf(monkeypatch, _leiste(), _leisten_matrix(["r"], mode))
    assert bild["intensity"] == 77
    assert bild["color_w"] == [180, 180]
    assert bild["color_r"] == [modify_wert(mode, 30, 255, 1.0)] * 4
    assert (bild["color_g"], bild["color_b"]) == ([60] * 4, [250] * 4)


# ── Speichern, Laden, Kopieren ───────────────────────────────────────────────

def test_kurzzeichen_und_namen_sind_vollstaendig():
    assert MODIFY_KANAELE == ("r", "g", "b", "w", "a", "uv")
    assert set(MODIFY_KANAL_ATTR) == set(MODIFY_KANAL_LABELS) == set(MODIFY_KANAELE)
    assert MODIFY_KANAL_ATTR["w"] == "color_w"
    # Jedes Attribut ist der Engine als Farbkanal bekannt.
    assert set(MODIFY_KANAL_ATTR.values()) <= AS._DIM_COLOR_ATTRS


@pytest.mark.parametrize("roh,erwartet", [
    (None, ()), ("", ()), ([], ()), (["w"], ("w",)), (("uv", "r"), ("r", "uv")),
    (["W", " r "], ("r", "w")), ("w,r", ("r", "w")), (["r", "r", "x"], ("r",)),
    ({"b", "g"}, ("g", "b")), (5, ()), (["dimmer"], ()),
])
def test_normalize_channels(roh, erwartet):
    assert normalize_channels(roh) == erwartet


def test_speichern_schreibt_das_feld_nur_bei_getroffener_auswahl():
    ohne = _matrix(()).to_dict()
    assert "modify_channels" not in ohne
    mit = _matrix(["w", "r"]).to_dict()
    assert mit["modify_channels"] == ["r", "w"]      # feste Reihenfolge
    import json
    json.dumps(mit)                      # Show-Datei ist JSON


def test_laden_kopieren_und_alt_show():
    quelle = _matrix(["w", "r"], "sub", 35, stil=MatrixStyle.RGBW)
    d = quelle.to_dict()
    # Kopieren/Klonen und der Entwurf des Editors laufen ueber to_dict/from_dict.
    kopie = RgbMatrixInstance.from_dict(dict(d, id=None))
    assert kopie.modify_channels == ("r", "w")
    assert kopie._modify_kanalwahl() == frozenset({"color_r", "color_w"})
    assert kopie.to_dict()["modify_channels"] == ["r", "w"]
    # apply_dict OHNE den Schluessel heisst Vorgabe (im Editor abgewaehlt).
    d.pop("modify_channels")
    kopie.apply_dict(d)
    assert kopie.modify_channels == ()
    # Alt-Show (ENG-38) ohne das Feld.
    alt = RgbMatrixInstance.from_dict(d)
    assert alt.modify is True and alt.modify_channels == ()
    assert alt._modify_kanalwahl() == frozenset()
    # Unlesbares in der Datei faellt auf die Vorgabe zurueck.
    assert RgbMatrixInstance.from_dict(
        dict(d, modify_channels="kaputt")).modify_channels == ()


def test_show_roundtrip_ueber_den_function_manager(monkeypatch):
    fm = FunctionManager()
    a = _matrix(["w"], "sub", 50, stil=MatrixStyle.RGBW)
    b = _matrix(())
    fm.add(a)
    fm.add(b)
    daten = fm.to_dict()
    fm2 = FunctionManager()
    fm2.from_dict(daten)
    a2, b2 = fm2.get(a.id), fm2.get(b.id)
    assert a2.modify_channels == ("w",) and b2.modify_channels == ()
    assert fm2.to_dict() == daten
    fm2.start(a2.id)
    kanaele = _kanaele(RGBW)
    monkeypatch.setattr(AS, "get_channels_for_patched", lambda fx: kanaele)
    uni = Universe(1)
    for c in kanaele:
        uni.set_channel(c.channel_number, DARUNTER[c.attribute])
    fm2.tick({1: uni}, [_fx(kanaele)], 0.02)
    roh = uni.get_all()
    assert list(roh[:5]) == [77, 30, 60, 250, 52]
