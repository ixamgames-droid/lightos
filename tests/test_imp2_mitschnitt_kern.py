"""IMP-2: DMX-Mitschnitt — der Kern ohne Oberfläche.

Bytes je Universum + Patch -> Werte je Gerät (16 Bit, Mehrkopf), die
Auswahlregeln, die Laser-Vorgabe, die Ruhe-Erkennung mit vorgespielter Zeit
und der Rundlauf Abbild -> Szene -> ``Scene.write`` -> dieselben Bytes.
"""
from __future__ import annotations

import socket
import struct
import threading
from types import SimpleNamespace

import pytest

from src.core import mitschnitt as M
from src.core.dmx.universe import Universe
from src.core.engine.function_manager import FunctionManager
from src.core.undo import get_undo_stack


# ── Attrappen ────────────────────────────────────────────────────────────────

def _ch(nr, attribut, name=""):
    return SimpleNamespace(channel_number=nr, attribute=attribut, name=name or attribut)


def _fx(fid, universum, adresse, kanaele, label="", typ="par", protokoll="dmx"):
    return SimpleNamespace(fid=fid, universe=universum, address=adresse,
                           channel_count=len(kanaele), label=label or f"Gerät {fid}",
                           fixture_type=typ, fixture_name="", manufacturer_name="",
                           protocol=protokoll, _kanaele=kanaele)


def _kanaele(fx):
    return fx._kanaele


PAR = [_ch(1, "intensity"), _ch(2, "color_r"), _ch(3, "color_g"), _ch(4, "color_b")]
KOPF = [_ch(1, "pan"), _ch(2, "pan_fine"), _ch(3, "tilt"), _ch(4, "tilt_fine"),
        _ch(5, "intensity")]
# Zwei Köpfe: Pan/Pan fein/Farbe je Kopf, ein gemeinsamer Dimmer davor.
ZWEIKOPF = [_ch(1, "intensity"),
            _ch(2, "pan"), _ch(3, "pan_fine"), _ch(4, "color_r"),
            _ch(5, "pan"), _ch(6, "pan_fine"), _ch(7, "color_r")]
LASER = [_ch(1, "laser_mode"), _ch(2, "laser_pattern"), _ch(3, "intensity")]


def _bild(**werte):
    """512 Nullen, dazu ``a10=200`` -> Adresse 10 = 200."""
    b = bytearray(512)
    for k, v in werte.items():
        b[int(k[1:]) - 1] = v
    return bytes(b)


def _lies(abbild, patch, **kw):
    return M.lies_abbild(abbild, patch, kanaele_fuer=_kanaele, **kw)


# ── Abbildung Bytes -> Attribute ─────────────────────────────────────────────

def test_werte_je_geraet_und_attribut_nur_an_gepatchten_adressen():
    patch = [_fx(1, 1, 10, PAR, "PAR links"), _fx(2, 1, 20, PAR, "PAR rechts")]
    # Adresse 50 ist nicht gepatcht — der Wert dort fällt weg.
    m = _lies({1: _bild(a10=255, a11=200, a22=7, a50=99)}, patch)
    assert [g.fid for g in m.geraete] == [1, 2]
    assert m.geraete[0].attribute == {"intensity": 255, "color_r": 200,
                                      "color_g": 0, "color_b": 0}
    assert m.geraete[1].attribute == {"intensity": 0, "color_r": 0,
                                      "color_g": 7, "color_b": 0}
    assert [k.adresse for k in m.geraete[1].kanaele] == [20, 21, 22, 23]
    assert m.kanalzahl == 8
    assert (m.geraete_mit_wert, m.geraete_gesehen) == (2, 2)
    assert (1, 1, 255) in m.szenenwerte() and (2, 3, 7) in m.szenenwerte()
    assert all(w != 99 for _f, _k, w in m.szenenwerte())


def test_16_bit_paar_wird_zusammengesetzt():
    m = _lies({1: _bild(a1=0x12, a2=0x34, a3=0xFF, a4=0x01, a5=9)},
              [_fx(1, 1, 1, KOPF)])
    g = m.geraete[0]
    assert g.attribute["pan"] == 0x12 and g.attribute["pan_fine"] == 0x34
    assert g.werte16 == {"pan": 0x1234, "tilt": 0xFF01}
    assert g.paare == [("pan", "pan_fine"), ("tilt", "tilt_fine")]


def test_mehrkopf_bekommt_schluessel_je_kopf_und_eigene_16_bit_paare():
    m = _lies({1: _bild(a100=50, a101=1, a102=2, a103=30, a104=4, a105=5, a106=60)},
              [_fx(7, 1, 100, ZWEIKOPF)])
    g = m.geraete[0]
    assert g.attribute == {"intensity": 50, "pan": 1, "pan_fine": 2, "color_r": 30,
                           "pan#1": 4, "pan_fine#1": 5, "color_r#1": 60}
    assert g.werte16 == {"pan": 1 * 256 + 2, "pan#1": 4 * 256 + 5}


def test_geraet_ohne_bekanntes_profil_behaelt_seine_kanaele():
    fx = _fx(3, 1, 5, [])
    fx.channel_count = 3
    m = _lies({1: _bild(a5=1, a6=2, a7=3, a8=4)}, [fx])
    assert m.geraete[0].attribute == {"kanal_1": 1, "kanal_2": 2, "kanal_3": 3}


def test_kurzes_bild_und_ende_des_universums():
    patch = [_fx(1, 1, 510, PAR)]             # Kanal 4 läge auf Adresse 513
    m = _lies({1: bytes([9] * 511)}, patch)   # nur 511 Bytes empfangen
    assert [(k.kanal, k.adresse, k.wert) for k in m.geraete[0].kanaele] == [
        (1, 510, 9), (2, 511, 9), (3, 512, 0)]


def test_geraet_in_nicht_empfangenem_universum_bekommt_keine_erfundenen_nullen():
    patch = [_fx(1, 1, 1, PAR, "Im Bild"), _fx(2, 2, 1, PAR, "Ohne Bild")]
    m = _lies({1: _bild(a1=255)}, patch)
    assert [g.fid for g in m.geraete] == [1]
    assert m.ohne_bild == ["Ohne Bild"]
    assert m.geraete_gesehen == 1


# ── Auswahlregeln ────────────────────────────────────────────────────────────

def test_vorgabe_ist_alle_gepatchten_kanaele():
    assert M.AUSWAHL_VORGABE == M.AUSWAHL_ALLE
    m = _lies({1: _bild()}, [_fx(1, 1, 1, PAR)])
    assert m.kanalzahl == 4 and m.geraete_mit_wert == 0
    assert {w for _f, _k, w in m.szenenwerte()} == {0}


def test_nur_ungleich_null_laesst_dunkle_kanaele_und_geraete_weg():
    patch = [_fx(1, 1, 1, PAR), _fx(2, 1, 10, PAR)]
    m = _lies({1: _bild(a1=255, a3=10)}, patch, auswahl=M.AUSWAHL_UNGLEICH_NULL)
    assert m.szenenwerte() == [(1, 1, 255), (1, 3, 10)]
    assert (m.geraete_mit_wert, m.geraete_gesehen) == (1, 2)


def test_nur_geaendert_vergleicht_mit_dem_bezugsbild():
    patch = [_fx(1, 1, 1, PAR), _fx(2, 1, 10, PAR)]
    bezug = {1: _bild(a1=255, a2=100, a10=40)}
    jetzt = {1: _bild(a1=255, a2=0, a10=40, a11=8)}
    m = _lies(jetzt, patch, auswahl=M.AUSWAHL_GEAENDERT, bezug=bezug)
    # a2 fiel auf 0 (geändert, obwohl 0), a11 kam dazu. Die Dimmer a1/a10
    # blieben gleich, gehen bei einem aufgenommenen Gerät aber immer mit.
    assert m.szenenwerte() == [(1, 1, 255), (1, 2, 0), (2, 1, 40), (2, 2, 8)]
    # Ohne Bezugsbild wirkt die Regel wie „ungleich 0“.
    ohne = _lies(jetzt, patch, auswahl=M.AUSWAHL_GEAENDERT)
    assert ohne.szenenwerte() == [(1, 1, 255), (2, 1, 40), (2, 2, 8)]


def test_16_bit_paar_bleibt_bei_jeder_regel_zusammen():
    patch = [_fx(1, 1, 1, KOPF)]
    # Pan grob 0, fein 5: „ungleich 0“ träfe nur den Fein-Kanal.
    m = _lies({1: _bild(a2=5)}, patch, auswahl=M.AUSWAHL_UNGLEICH_NULL)
    assert m.szenenwerte() == [(1, 1, 0), (1, 2, 5), (1, 5, 0)]
    # Nur der Fein-Kanal ändert sich: der Grob-Kanal kommt trotzdem mit.
    m = _lies({1: _bild(a3=10, a4=7)}, patch, auswahl=M.AUSWAHL_GEAENDERT,
              bezug={1: _bild(a3=10, a4=6)})
    assert m.szenenwerte() == [(1, 3, 10), (1, 4, 7), (1, 5, 0)]


def test_unbekannte_auswahl_wird_abgelehnt():
    with pytest.raises(ValueError):
        _lies({1: _bild()}, [], auswahl="irgendwas")


# ── Laser ────────────────────────────────────────────────────────────────────

def test_laser_werden_ausgelassen_und_genannt():
    patch = [_fx(1, 1, 1, PAR), _fx(2, 1, 10, LASER, "Laser Mitte", typ="laser")]
    m = _lies({1: _bild(a1=255, a10=200, a12=255)}, patch)
    assert [g.fid for g in m.geraete] == [1]
    assert m.laser_ausgelassen == ["Laser Mitte"]
    assert all(f != 2 for f, _k, _w in m.szenenwerte())
    assert (m.geraete_mit_wert, m.geraete_gesehen) == (1, 1)


def test_laser_wird_auch_ueber_kanal_und_namen_erkannt():
    ueber_kanal = _fx(2, 1, 10, LASER, "Effekt 1")                # Typ „par“
    ueber_name = _fx(3, 1, 20, PAR, "Showlaser hinten")
    m = _lies({1: _bild(a10=1, a20=1)}, [ueber_kanal, ueber_name])
    assert m.geraete == []
    assert m.laser_ausgelassen == ["Effekt 1", "Showlaser hinten"]


def test_laser_kommt_nur_mit_ausdruecklicher_freigabe_mit():
    patch = [_fx(2, 1, 10, LASER, "Laser Mitte", typ="laser")]
    m = _lies({1: _bild(a10=200)}, patch, laser_mitnehmen=True)
    assert m.szenenwerte() == [(2, 1, 200), (2, 2, 0), (2, 3, 0)]
    assert m.laser_ausgelassen == []


def test_netzwerk_laser_wird_nie_gelesen_seine_adresse_ist_ein_platzhalter():
    netz = _fx(2, 1, 1, LASER, "Netz-Laser", typ="laser", protokoll="etherdream")
    par = _fx(1, 1, 1, PAR)
    m = _lies({1: _bild(a1=255)}, [netz, par], laser_mitnehmen=True)
    assert [g.fid for g in m.geraete] == [1]
    assert m.laser_ausgelassen == ["Netz-Laser"]


# ── Rundlauf: Abbild -> Szene -> Scene.write -> dieselben Bytes ──────────────

@pytest.fixture
def fm():
    stack = get_undo_stack()
    stack.clear()
    yield FunctionManager()
    stack.clear()


def _spiele(szene, patch, universen=(1, 2)):
    unis = {u: Universe(u) for u in universen}
    szene.start()
    szene.write(unis, patch, 0.03)
    return unis


def test_rundlauf_gibt_an_den_gepatchten_adressen_dieselben_bytes_aus(fm):
    patch = [_fx(1, 1, 1, PAR), _fx(2, 1, 10, KOPF), _fx(3, 2, 100, ZWEIKOPF),
             _fx(4, 1, 509, PAR)]
    import random
    rng = random.Random(20261013)
    abbild = {1: bytes(rng.randrange(256) for _ in range(512)),
              2: bytes(rng.randrange(256) for _ in range(512))}
    szene = M.baue_szene(fm, "Rundlauf", _lies(abbild, patch))
    assert (szene.fade_in, szene.fade_out, szene.hold) == (0.0, 0.0, 0.0)
    unis = _spiele(szene, patch)
    gepatcht = {(fx.universe, fx.address + i) for fx in patch
                for i in range(fx.channel_count)}
    for u in (1, 2):
        aus = unis[u].get_all()
        for adresse in range(1, 513):
            if (u, adresse) in gepatcht:
                assert aus[adresse - 1] == abbild[u][adresse - 1], (u, adresse)
            else:
                assert aus[adresse - 1] == 0, (u, adresse)   # nichts daneben


def test_szene_ohne_werte_wird_nicht_angelegt(fm):
    with pytest.raises(ValueError):
        M.baue_szene(fm, "Leer", _lies({1: _bild()}, []))
    assert fm.all() == []
    assert not get_undo_stack().can_undo()


# ── Rückgängig, Chaser, Namen ────────────────────────────────────────────────

def test_szene_ist_ein_rueckgaengig_schritt_und_kommt_mit_derselben_id_wieder(fm):
    stack = get_undo_stack()
    szene = M.baue_szene(fm, "Mitschnitt 1", _lies({1: _bild(a1=9)}, [_fx(1, 1, 1, PAR)]))
    assert fm.get(szene.id) is szene
    assert stack.undo() and fm.get(szene.id) is None
    assert stack.redo() and fm.get(szene.id) is szene
    assert szene.get_value(1, 1) == 9


def test_chaser_haelt_reihenfolge_und_schrittzeit_und_ist_ein_eigener_schritt(fm):
    stack = get_undo_stack()
    patch = [_fx(1, 1, 1, PAR)]
    ids = [M.baue_szene(fm, f"Mitschnitt {i}", _lies({1: _bild(a1=i)}, patch)).id
           for i in (1, 2, 3)]
    chaser = M.baue_chaser(fm, "Mitschnitt Chaser 1", ids, 2.5)
    assert [s.function_id for s in chaser.steps] == ids
    assert {(s.fade_in, s.hold, s.fade_out) for s in chaser.steps} == {(0.0, 2.5, 0.0)}
    assert chaser.tempo_bus_id == ""           # läuft nach Zeit, nicht im Takt
    assert stack.undo()                        # nur der Chaser geht
    assert fm.get(chaser.id) is None
    assert all(fm.get(i) is not None for i in ids)
    with pytest.raises(ValueError):
        M.baue_chaser(fm, "Leer", [])


def test_freier_name_zaehlt_hoch_und_ueberspringt_vergebene(fm):
    assert M.freier_name(fm) == ("Mitschnitt 1", 1)
    fm.new_scene("Mitschnitt 1")
    fm.new_scene("Mitschnitt 2")
    assert M.freier_name(fm) == ("Mitschnitt 3", 3)
    assert M.freier_name(fm, ab=5) == ("Mitschnitt 5", 5)


# ── Eingangspuffer: Signal und Ruhe mit vorgespielter Zeit ───────────────────

class _Uhr:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def vor(self, sekunden):
        self.t += sekunden


def _ziel_1_zu_1(_protokoll, universum):
    return universum


def test_ruhig_erst_nach_der_ruhezeit_ohne_aenderung():
    uhr = _Uhr()
    p = M.Eingangspuffer(uhr=uhr)
    p.melde(M.ARTNET, 1, _bild(a1=10))
    assert not M.eingangsbild(p, _ziel_1_zu_1).ist_ruhig(0.5)   # erstes Bild = Änderung
    for _ in range(4):                       # 0,4 s dasselbe Bild
        uhr.vor(0.1)
        p.melde(M.ARTNET, 1, _bild(a1=10))
    assert not M.eingangsbild(p, _ziel_1_zu_1).ist_ruhig(0.5)
    uhr.vor(0.1)
    p.melde(M.ARTNET, 1, _bild(a1=10))
    bild = M.eingangsbild(p, _ziel_1_zu_1)
    assert bild.ist_ruhig(0.5) and bild.ruhig_seit == pytest.approx(0.5)
    assert not bild.ist_ruhig(2.0)           # einstellbar
    # Eine laufende Überblendung hält das Bild unruhig.
    uhr.vor(0.1)
    p.melde(M.ARTNET, 1, _bild(a1=11))
    assert not M.eingangsbild(p, _ziel_1_zu_1).ist_ruhig(0.5)


def test_signal_seit_kein_signal_und_neubeginn_nach_einer_pause():
    uhr = _Uhr()
    p = M.Eingangspuffer(uhr=uhr, signal_timeout=5.0)
    assert not M.eingangsbild(p, _ziel_1_zu_1).hat_signal
    p.melde(M.SACN, 3, _bild(a1=1))
    uhr.vor(4.0)
    p.melde(M.SACN, 3, _bild(a1=1))
    (st,) = p.stand()
    assert (st.protokoll, st.universum, st.hat_signal) == (M.SACN, 3, True)
    assert st.signal_seit == pytest.approx(4.0) and st.kanaele == 512
    uhr.vor(5.5)                              # Sender schweigt
    (st,) = p.stand()
    assert not st.hat_signal and st.letztes_paket_vor == pytest.approx(5.5)
    assert p.bild(M.SACN, 3) is None
    bild = M.eingangsbild(p, _ziel_1_zu_1)
    assert not bild.hat_signal and not bild.ist_ruhig(0.5)
    p.melde(M.SACN, 3, _bild(a1=1))           # wieder da: Zählung beginnt neu
    (st,) = p.stand()
    assert st.hat_signal and st.signal_seit == 0.0 and st.ruhig_seit == 0.0


def test_nicht_zugeordnete_quelle_wird_genannt_aber_nicht_mitgeschnitten():
    uhr = _Uhr()
    p = M.Eingangspuffer(uhr=uhr)
    p.melde(M.ARTNET, 1, _bild(a1=1))
    p.melde(M.ARTNET, 2, _bild(a1=2))
    bild = M.eingangsbild(p, lambda _p, u: 4 if u == 1 else None)
    assert bild.abbild == {4: _bild(a1=1)}
    assert bild.quellen == [(M.ARTNET, 1, 4)]
    assert bild.nicht_zugeordnet == [(M.ARTNET, 2)]


def test_zwei_quellen_auf_dasselbe_universum_die_juengste_gilt():
    uhr = _Uhr()
    p = M.Eingangspuffer(uhr=uhr)
    p.melde(M.ARTNET, 1, _bild(a1=1))
    uhr.vor(1.0)
    p.melde(M.SACN, 1, _bild(a1=2))
    bild = M.eingangsbild(p, lambda _p, _u: 1)
    assert bild.abbild == {1: _bild(a1=2)} and bild.doppelt == [1]


# ── Anbindung: der Leser hört nur zu ─────────────────────────────────────────

class _Rx:
    def __init__(self, zuordnung=None, laeuft=True):
        self.cbs = []
        self.zuordnung = dict(zuordnung or {})
        self.laeuft = laeuft
        self.aufrufe = []

    def subscribe(self, cb):
        self.cbs.append(cb)

    def unsubscribe(self, cb):
        self.cbs.remove(cb)

    def is_running(self):
        return self.laeuft

    def merges(self):
        return {k: (v, "HTP") for k, v in self.zuordnung.items()}

    def __getattr__(self, name):               # start/stop/set_merge … wären Eingriffe
        if name.startswith("_"):
            raise AttributeError(name)
        self.aufrufe.append(name)
        return lambda *a, **k: None


def test_leser_meldet_sich_nur_als_zuhoerer_an_und_wieder_ab():
    art, sacn = _Rx({1: 2}), _Rx({}, laeuft=False)
    leser = M.EingangsLeser(M.Eingangspuffer(uhr=_Uhr()),
                            {M.ARTNET: art, M.SACN: sacn})
    leser.verbinden()
    leser.verbinden()                          # doppelt schadet nicht
    assert len(art.cbs) == 1 and len(sacn.cbs) == 1
    art.cbs[0](1, _bild(a7=70))
    assert leser.bild().abbild == {2: _bild(a7=70)}
    assert leser.laeuft(M.ARTNET) and not leser.laeuft(M.SACN)
    assert leser.ziel(M.ARTNET, 1) == 2 and leser.ziel(M.ARTNET, 9) is None
    leser.trennen()
    assert art.cbs == [] and sacn.cbs == []
    assert art.aufrufe == [] and sacn.aufrufe == []   # kein start/stop/set_merge


def test_die_echten_empfaenger_geben_ihre_zuordnung_als_kopie_heraus():
    from src.core.dmx.artnet_input import ArtNetReceiver
    from src.core.dmx.sacn_input import SACNReceiver
    for rx in (ArtNetReceiver(), SACNReceiver()):
        rx.set_merge(3, 2, "LTP")
        kopie = rx.merges()
        assert kopie == {3: (2, "LTP")}
        kopie.clear()
        assert rx.merges() == {3: (2, "LTP")}
        assert not rx.is_running()             # nichts gestartet


# ── Ein echtes Art-Net-Paket über 127.0.0.1 ──────────────────────────────────

def _artdmx(universum_draht: int, daten: bytes) -> bytes:
    return (b"Art-Net\x00" + struct.pack("<H", 0x5000) + bytes([0, 14, 1, 0])
            + struct.pack("<H", universum_draht) + struct.pack(">H", len(daten)) + daten)


def test_echtes_artnet_paket_ueber_loopback_wird_zur_szene(monkeypatch, fm):
    from src.core.dmx import artnet_input

    class _NurLoopback(socket.socket):
        def bind(self, adresse):
            super().bind(("127.0.0.1", adresse[1]))

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    monkeypatch.setattr(artnet_input, "ARTNET_PORT", port)
    monkeypatch.setattr(artnet_input.socket, "socket", _NurLoopback)

    rx = artnet_input.ArtNetReceiver()
    # Zuordnung nur für den Leser sichtbar: so läuft der Merge-Weg des
    # Empfängers (der in die Ausgabe schriebe) in diesem Test gar nicht an.
    rx.merges = lambda: {1: (2, "HTP")}
    uhr = _Uhr()
    leser = M.EingangsLeser(M.Eingangspuffer(uhr=uhr), {M.ARTNET: rx})
    da = threading.Event()
    rx.start()
    try:
        if not rx.is_running():
            pytest.skip("UDP-Port auf 127.0.0.1 nicht bindbar")
        leser.verbinden()
        rx.subscribe(lambda _u, _d: da.set())   # nach dem Leser: erst er, dann das Zeichen
        daten = bytes((i * 7) % 256 for i in range(512))
        with _NurLoopback(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.sendto(_artdmx(0, daten), ("127.0.0.1", port))
            assert da.wait(3.0), "Paket kam nicht an"
        # Gelesen wird, solange der Eingang laeuft: ein abgeschalteter Eingang
        # liefert kein Bild mehr.
        uhr.vor(0.6)
        bild = leser.bild()
    finally:
        leser.trennen()
        rx.stop()

    assert not leser.bild().hat_signal
    assert bild.quellen == [(M.ARTNET, 1, 2)]   # Draht-Universum 0 = Universum 1
    assert bild.ist_ruhig(0.5)
    patch = [_fx(1, 2, 1, PAR), _fx(2, 2, 200, KOPF)]
    szene = M.baue_szene(fm, "Vom Draht", _lies(bild.abbild, patch))
    aus = _spiele(szene, patch)[2].get_all()
    assert aus[0:4] == daten[0:4] and aus[199:204] == daten[199:204]



def test_sparregeln_nehmen_den_dimmer_eines_aufgenommenen_geraets_immer_mit():
    """Farbe ohne Dimmer: der Dimmer muss mit 0 in der Szene stehen — sonst
    zieht die Grundhelligkeit aelterer Shows ihn beim Abspielen auf Voll."""
    patch = [_fx(1, 1, 1, PAR), _fx(2, 1, 10, PAR)]
    # Geraet 1: nur Rot (Adresse 2), Dimmer 0. Geraet 2: ganz dunkel.
    m = _lies({1: _bild(a2=200)}, patch, auswahl=M.AUSWAHL_UNGLEICH_NULL)
    assert m.szenenwerte() == [(1, 1, 0), (1, 2, 200)]
    # Dasselbe bei „nur geaendert“: Rot aendert sich, der Dimmer (0) geht mit.
    g = _lies({1: _bild(a2=200)}, patch, auswahl=M.AUSWAHL_GEAENDERT,
              bezug={1: _bild(a2=100)})
    assert g.szenenwerte() == [(1, 1, 0), (1, 2, 200)]
