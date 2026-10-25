"""OSC-06: freie OSC-Adressen — Muster, {n}, Argumente, Learn, Rueckmeldung,
Speichern/Laden. Ohne Netz und ohne Qt (End-to-End: test_osc06_end_to_end.py)."""
from __future__ import annotations

import json
import os

import pytest

from src.core.osc import osc_zuordnung as oz
from src.core.osc.osc_zuordnung import (
    BEREICH_1, BEREICH_100, BEREICH_255, Konfig, OscRueckmeldung, OscZuordnung,
    RueckmeldeKonfig, Zuordnung,
)


# ── Nachbauten ───────────────────────────────────────────────────────────

class _Stack:
    def __init__(self, idx=-1):
        self.current_index = idx


class _Ex:
    def __init__(self, slot):
        self.slot = slot
        self.fader_value = 1.0
        self.fader_function = "volume"
        self.stack = None
        self.gedrueckt: list = []

    def press_btn(self, b):
        self.gedrueckt.append(b)


class _PE:
    def __init__(self):
        self.executors = [_Ex(i + 1) for i in range(20)]

    def get_executor(self, slot):
        return self.executors[slot - 1]


class _OM:
    def __init__(self):
        self.grand_master = 1.0
        self.blackout = False

    def set_grand_master(self, v):
        self.grand_master = v

    def set_blackout(self, v):
        self.blackout = bool(v)


class _F:
    def __init__(self, fid, name):
        self.id = fid
        self.name = name


class _FM:
    def __init__(self):
        self.fs = {3: _F(3, "Lauflicht"), 7: _F(7, "Strobe")}
        self.laeuft: set = set()
        self.log: list = []

    def get(self, fid):
        return self.fs.get(fid)

    def all(self):
        return list(self.fs.values())

    def start(self, fid):
        self.laeuft.add(fid)
        self.log.append(("start", fid))

    def stop(self, fid):
        self.laeuft.discard(fid)
        self.log.append(("stop", fid))

    def is_running(self, fid):
        return fid in self.laeuft


class _State:
    def __init__(self):
        self.playback_engine = _PE()
        self.output_manager = _OM()
        self.function_manager = _FM()


def _zu(*zuordnungen) -> tuple[OscZuordnung, _State]:
    zu = OscZuordnung()
    zu.konfigurieren(Konfig(aktiv=True, zuordnungen=list(zuordnungen)))
    state = _State()
    # Wecker statt Direktanwendung: die Tests wenden selbst an (GUI-Thread-Pfad)
    zu.set_wecker(lambda: None)
    return zu, state


def _senden(zu, state, adresse, *args) -> int:
    zu.empfange(adresse, args)
    return zu.abarbeiten(state)


# ── Muster ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("muster,passt,passt_nicht", [
    ("/Page1/Fader{n}", ["/Page1/Fader201", "/Page1/Fader1"],
     ["/Page1/Fader", "/Page1/FaderX", "/Page2/Fader1", "/Page1/Fader1/x"]),
    ("/exec/{n}/go", ["/exec/3/go"], ["/exec/a/go", "/exec/3/gox", "/exec//go"]),
    ("/a/*/b", ["/a/x/b", "/a//b", "/a/xyz/b"], ["/a/x/y/b", "/a/x/c"]),
    ("/q/?", ["/q/1", "/q/z"], ["/q/", "/q/12", "/q//"]),
    ("/k/[abc]", ["/k/a", "/k/c"], ["/k/d", "/k/ab"]),
    ("/k/[a-c]", ["/k/b"], ["/k/d"]),
    ("/k/[!0-9]", ["/k/x"], ["/k/5"]),
    ("/y/{go,start}", ["/y/go", "/y/start"], ["/y/stop", "/y/gostart"]),
    ("/eos/out/event/cue/*/*/fire", ["/eos/out/event/cue/1/25/fire"],
     ["/eos/out/event/cue/1/fire"]),
    ("/p.x+(y)", ["/p.x+(y)"], ["/pAx+(y)", "/p.xx(y)"]),   # Sonderzeichen woertlich
])
def test_muster_passt_und_passt_nicht(muster, passt, passt_nicht):
    rx = oz.muster_zu_regex(muster)
    assert rx is not None
    for a in passt:
        assert rx.match(a), a
    for a in passt_nicht:
        assert not rx.match(a), a


@pytest.mark.parametrize("muster", [
    "", "ohne/strich", "/a b", "/a/{n}/{n}", "/a[", "/a{b", "/a]", "/a}", "/a/[]",
    None, 5,
])
def test_ungueltige_muster(muster):
    assert oz.muster_zu_regex(muster) is None


def test_n_liefert_zielnummer_mit_versatz():
    zu, st = _zu(Zuordnung("/Page1/Fader{n}", oz.ZIEL_FADER, versatz=-200,
                           bereich=BEREICH_100))
    assert _senden(zu, st, "/Page1/Fader203", 50) == 1
    assert st.playback_engine.get_executor(3).fader_value == pytest.approx(0.5)
    # Gegenprobe: andere Executoren unberuehrt
    assert st.playback_engine.get_executor(1).fader_value == 1.0


def test_n_ausserhalb_executorbereich_tut_nichts():
    zu, st = _zu(Zuordnung("/exec/{n}/go", oz.ZIEL_GO))
    for a in ("/exec/0/go", "/exec/21/go", "/exec/99999999999999/go"):
        assert _senden(zu, st, a, 1.0) == 0
    assert all(not ex.gedrueckt for ex in st.playback_engine.executors)
    # 0 und 21: verworfen; mehr als 6 Ziffern passen gar nicht auf {n}
    assert zu.verworfen == 2


# ── Argumente ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("arg,bereich,erwartet", [
    (0.5, BEREICH_1, 0.5), (1, BEREICH_1, 1.0), (2.0, BEREICH_1, 1.0),
    (-1, BEREICH_1, 0.0), (127, BEREICH_255, 127 / 255), (255, BEREICH_255, 1.0),
    (50, BEREICH_100, 0.5), (True, BEREICH_255, 1.0), (False, BEREICH_1, 0.0),
    ("0.25", BEREICH_1, 0.25), (" 128 ", BEREICH_255, 128 / 255),
    ("on", BEREICH_1, 1.0), ("off", BEREICH_1, 0.0), ("AUS", BEREICH_1, 0.0),
    (0.5, "unbekannt", 0.5),
])
def test_wert_aus_argument(arg, bereich, erwartet):
    assert oz.wert_aus_argument(arg, bereich) == pytest.approx(erwartet)


@pytest.mark.parametrize("arg", [None, float("nan"), float("inf"), b"\x00\x01",
                                 "abc", "", [1], {"a": 1}, object()])
def test_kaputte_argumente_sind_none(arg):
    assert oz.wert_aus_argument(arg) is None


def test_fader_fehlende_oder_kaputte_argumente_aendern_nichts():
    zu, st = _zu(Zuordnung("/f/{n}", oz.ZIEL_FADER))
    ex = st.playback_engine.get_executor(2)
    ex.fader_value = 0.3
    for args in ((), (None,), ("kaputt",), (float("nan"),), (b"blob",)):
        assert _senden(zu, st, "/f/2", *args) == 0, args
        assert ex.fader_value == 0.3
    assert _senden(zu, st, "/f/2", 0.8) == 1
    assert ex.fader_value == pytest.approx(0.8)


def test_fader_bereich_0_255_und_int():
    zu, st = _zu(Zuordnung("/dmx/{n}", oz.ZIEL_FADER, bereich=BEREICH_255))
    _senden(zu, st, "/dmx/1", 51)
    assert st.playback_engine.get_executor(1).fader_value == pytest.approx(0.2)


def test_taste_nur_beim_druck_bang_ohne_argument():
    zu, st = _zu(Zuordnung("/exec/{n}/go", oz.ZIEL_GO))
    ex = st.playback_engine.get_executor(4)
    _senden(zu, st, "/exec/4/go", 1.0)
    _senden(zu, st, "/exec/4/go", 0.0)        # Loslassen
    _senden(zu, st, "/exec/4/go")             # Bang
    _senden(zu, st, "/exec/4/go", None)       # OSC-Nil als Bang
    _senden(zu, st, "/exec/4/go", "kaputt")   # kaputt: nichts
    assert ex.gedrueckt == ["go", "go", "go"]
    assert zu.verworfen == 1                  # Loslassen zaehlt nicht als kaputt


def test_taste_bereich_100_schwelle():
    zu, st = _zu(Zuordnung("/k{n}", oz.ZIEL_BACK, bereich=BEREICH_100))
    ex = st.playback_engine.get_executor(1)
    _senden(zu, st, "/k1", 40)
    assert ex.gedrueckt == []
    _senden(zu, st, "/k1", 60)
    assert ex.gedrueckt == ["back"]


def test_feste_nummer_und_stop():
    zu, st = _zu(Zuordnung("/stopp", oz.ZIEL_STOP, nummer=5))
    _senden(zu, st, "/stopp", 1)
    assert st.playback_engine.get_executor(5).gedrueckt == ["stop"]


def test_nummer_aus_argument():
    zu, st = _zu(Zuordnung("/hog/playback/go/0", oz.ZIEL_GO, nummer_aus_argument=True),
                 Zuordnung("/lvl", oz.ZIEL_FADER, nummer_aus_argument=True))
    _senden(zu, st, "/hog/playback/go/0", 3)
    _senden(zu, st, "/hog/playback/go/0", "6")
    _senden(zu, st, "/hog/playback/go/0", 2.0)
    assert st.playback_engine.get_executor(3).gedrueckt == ["go"]
    assert st.playback_engine.get_executor(6).gedrueckt == ["go"]
    assert st.playback_engine.get_executor(2).gedrueckt == ["go"]
    # zweites Argument ist der Wert
    _senden(zu, st, "/lvl", 7, 0.25)
    assert st.playback_engine.get_executor(7).fader_value == pytest.approx(0.25)
    # Gegenproben: ohne Argument, bool, Bruch, Text -> nichts
    vorher = zu.verworfen
    for args in ((), (True,), (2.5,), ("x",), (7,)):   # (7,) ohne Wert beim Fader
        _senden(zu, st, "/lvl", *args)
    assert zu.verworfen == vorher + 5
    assert st.playback_engine.get_executor(7).fader_value == pytest.approx(0.25)


def test_grand_master_und_master_executoren():
    zu, st = _zu(Zuordnung("/gm", oz.ZIEL_GM, bereich=BEREICH_255))
    st.playback_engine.get_executor(9).fader_function = "master"
    _senden(zu, st, "/gm", 0)
    assert st.output_manager.grand_master == 0.0
    assert st.playback_engine.get_executor(9).fader_value == 0.0
    assert st.playback_engine.get_executor(1).fader_value == 1.0


def test_blackout_setzen_ohne_wert_nichts():
    zu, st = _zu(Zuordnung("/bo", oz.ZIEL_BLACKOUT))
    assert _senden(zu, st, "/bo") == 0
    assert st.output_manager.blackout is False
    _senden(zu, st, "/bo", 1)
    assert st.output_manager.blackout is True
    _senden(zu, st, "/bo", "off")
    assert st.output_manager.blackout is False


def test_funktionen_per_name_id_und_n():
    zu, st = _zu(Zuordnung("/szene/an", oz.ZIEL_FKT_START, funktion="lauflicht"),
                 Zuordnung("/szene/aus", oz.ZIEL_FKT_STOP, funktion="3"),
                 Zuordnung("/fkt/{n}", oz.ZIEL_FKT_UMSCHALTEN),
                 Zuordnung("/fkt/weg", oz.ZIEL_FKT_START, funktion="Gibtsnicht"))
    fm = st.function_manager
    _senden(zu, st, "/szene/an")
    assert fm.log == [("start", 3)]
    _senden(zu, st, "/szene/aus", 1)
    assert fm.log[-1] == ("stop", 3)
    _senden(zu, st, "/fkt/7", 1)
    _senden(zu, st, "/fkt/7", 0)      # Loslassen schaltet nicht zurueck
    assert fm.is_running(7)
    _senden(zu, st, "/fkt/7", 1)
    assert not fm.is_running(7)
    n = len(fm.log)
    assert _senden(zu, st, "/fkt/weg") == 0
    assert _senden(zu, st, "/fkt/99") == 0
    assert len(fm.log) == n


def test_tap_tempo(monkeypatch):
    aufrufe = []

    class _B:
        def tap(self):
            aufrufe.append(1)
            return 120.0

    import src.core.engine.bpm_manager as bm
    monkeypatch.setattr(bm, "get_bpm_manager", lambda: _B())
    zu, st = _zu(Zuordnung("/tap", oz.ZIEL_TAP))
    _senden(zu, st, "/tap", 1.0)
    _senden(zu, st, "/tap", 0.0)
    assert aufrufe == [1]


def test_mehrere_fader_werte_fallen_zusammen_tasten_nicht():
    zu, st = _zu(Zuordnung("/f/{n}", oz.ZIEL_FADER), Zuordnung("/g/{n}", oz.ZIEL_GO))
    for v in (0.1, 0.2, 0.3):
        zu.empfange("/f/1", (v,))
    zu.empfange("/g/1", ())
    zu.empfange("/g/1", ())
    assert zu.abarbeiten(st) == 3          # 1 Fader + 2 Tasten
    assert st.playback_engine.get_executor(1).fader_value == pytest.approx(0.3)
    assert st.playback_engine.get_executor(1).gedrueckt == ["go", "go"]


def test_inaktiv_und_neu_konfigurieren_verwirft_wartendes():
    zu, st = _zu(Zuordnung("/f/{n}", oz.ZIEL_FADER))
    zu.empfange("/f/1", (0.1,))
    zu.konfigurieren(Konfig(aktiv=False, zuordnungen=[Zuordnung("/f/{n}")]))
    assert zu.abarbeiten(st) == 0
    assert zu.empfange("/f/1", (0.1,)) == 0
    assert st.playback_engine.get_executor(1).fader_value == 1.0


def test_ohne_wecker_wird_direkt_angewandt(monkeypatch):
    st = _State()
    import src.core.app_state as app_state
    monkeypatch.setattr(app_state, "get_state", lambda: st)
    zu = OscZuordnung()
    zu.konfigurieren(Konfig(zuordnungen=[Zuordnung("/f/{n}", oz.ZIEL_FADER)]))
    zu.empfange("/f/2", (0.4,))
    assert st.playback_engine.get_executor(2).fader_value == pytest.approx(0.4)


def test_fehler_beim_anwenden_bricht_den_rest_nicht_ab():
    zu, st = _zu(Zuordnung("/f/{n}", oz.ZIEL_FADER), Zuordnung("/gm", oz.ZIEL_GM))

    def kaputt(_v):
        raise RuntimeError("weg")
    st.output_manager.set_grand_master = kaputt
    zu.empfange("/gm", (0.5,))
    zu.empfange("/f/1", (0.5,))
    assert zu.abarbeiten(st) == 1
    assert st.playback_engine.get_executor(1).fader_value == pytest.approx(0.5)


# ── Learn ────────────────────────────────────────────────────────────────

def test_learn_meldet_naechste_nachricht_einmal_und_wendet_nicht_an():
    zu, st = _zu(Zuordnung("/f/{n}", oz.ZIEL_FADER))
    gelernt = []
    zu.lerne(lambda a, args, von: gelernt.append((a, args, von)))
    assert zu.lernt
    assert zu.empfange("/f/1", (0.2,), "192.0.2.7") == 0
    zu.abarbeiten(st)
    assert st.playback_engine.get_executor(1).fader_value == 1.0
    assert gelernt == [("/f/1", (0.2,), "192.0.2.7")]
    assert not zu.lernt
    zu.empfange("/f/1", (0.2,))
    zu.abarbeiten(st)
    assert len(gelernt) == 1
    assert st.playback_engine.get_executor(1).fader_value == pytest.approx(0.2)


def test_learn_abbrechen_und_fehler_im_rueckruf():
    zu, _st = _zu()
    zu.lerne(lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    assert zu.empfange("/a", ()) == 0      # Fehler wird geschluckt
    zu.lerne(lambda *a: pytest.fail("abgebrochen"))
    zu.lerne(None)
    zu.empfange("/a", ())


@pytest.mark.parametrize("adresse,muster,n", [
    ("/Page1/Fader201", "/Page1/Fader{n}", 201),
    ("/exec/3/go", "/exec/{n}/go", 3),
    ("/1/fader4", "/1/fader{n}", 4),
    ("/blackout", "/blackout", None),
])
def test_vorschlag_muster(adresse, muster, n):
    assert oz.vorschlag_muster(adresse) == (muster, n)
    rx = oz.muster_zu_regex(muster)
    assert rx is not None and rx.match(adresse)


@pytest.mark.parametrize("adresse,args,ziel", [
    ("/Page1/Fader201", (50,), oz.ZIEL_FADER),
    ("/exec/3/go", (), oz.ZIEL_GO),
    ("/exec/3/back", (1,), oz.ZIEL_BACK),
    ("/1/push2", (1.0,), oz.ZIEL_GO),
    ("/lightos/blackout", (1,), oz.ZIEL_BLACKOUT),
    ("/tap", (), oz.ZIEL_TAP),
    ("/x/y", (0.4,), oz.ZIEL_FADER),
    ("/x/y", (), oz.ZIEL_GO),
])
def test_vorschlag_ziel(adresse, args, ziel):
    assert oz.vorschlag_ziel(adresse, args) == ziel


# ── Rueckmeldung ─────────────────────────────────────────────────────────

class _Sender:
    def __init__(self, ip, port):
        self.ziel = (ip, port)
        self.gesendet: list = []
        self.fehler = False
        self.zu = False

    def send(self, adresse, wert):
        if self.fehler:
            return False
        self.gesendet.append((adresse, wert))
        return True

    def close(self):
        self.zu = True


def _rm(**kw) -> tuple[OscRueckmeldung, list]:
    sender: list = []

    def fabrik(ip, port):
        s = _Sender(ip, port)
        sender.append(s)
        return s
    rm = OscRueckmeldung(sender_fabrik=fabrik, uhr=lambda: 0.0)
    k = RueckmeldeKonfig(aktiv=True, executoren="1-2", **kw)
    rm.konfigurieren(k)
    return rm, sender


def test_rueckmeldung_sendet_nur_bei_aenderung():
    rm, sender = _rm()
    st = _State()
    st.playback_engine.get_executor(1).stack = _Stack(2)
    assert rm.tick(st, jetzt=1.0) == 8      # 2x3 je Executor + GM + Blackout
    s = sender[0]
    d = dict(s.gesendet)
    assert d["/lightos/exec/1/fader"] == 1.0
    assert d["/lightos/exec/1/aktiv"] == 1
    assert d["/lightos/exec/1/cue"] == 3
    assert d["/lightos/exec/2/aktiv"] == 0
    assert d["/lightos/grandmaster"] == 1.0
    assert d["/lightos/blackout"] == 0
    assert rm.tick(st, jetzt=2.0) == 0      # nichts geaendert -> nichts
    st.playback_engine.get_executor(2).fader_value = 0.5
    st.output_manager.blackout = True
    assert rm.tick(st, jetzt=3.0) == 2
    assert set(s.gesendet[-2:]) == {("/lightos/blackout", 1),
                                    ("/lightos/exec/2/fader", 0.5)}


def test_rueckmeldung_drossel():
    rm, sender = _rm(rate_hz=10)
    st = _State()
    ex = st.playback_engine.get_executor(1)
    assert rm.tick(st, jetzt=0.0) > 0
    ex.fader_value = 0.2
    assert rm.tick(st, jetzt=0.05) == 0     # < 1/10 s
    assert rm.tick(st, jetzt=0.11) == 1
    # 1000 Aenderungen in einer Sekunde -> hoechstens 10 Durchgaenge
    n = 0
    for i in range(1000):
        ex.fader_value = (i % 100) / 100
        n += rm.tick(st, jetzt=1.0 + i / 1000)
    assert n <= 10


def test_rueckmeldung_erst_senden_dann_merken():
    rm, sender = _rm()
    st = _State()
    sender[0].fehler = True
    assert rm.tick(st, jetzt=1.0) == 0
    sender[0].fehler = False
    assert rm.tick(st, jetzt=2.0) == 8      # Aussetzer wird nachgeholt


def test_rueckmeldung_versatz_bereich_und_leere_adressen():
    rm, sender = _rm()
    k = RueckmeldeKonfig(aktiv=True, executoren="1")
    k.vorlage_anwenden("grandma3")
    rm.konfigurieren(k)
    st = _State()
    st.playback_engine.get_executor(1).fader_value = 0.5
    rm.tick(st, jetzt=1.0)
    assert sender[-1].gesendet == [("/Page1/Fader201", 50.0)]
    assert sender[0].zu                       # alter Sender geschlossen
    k2 = RueckmeldeKonfig(aktiv=True, executoren="1", bereich=BEREICH_255,
                          adressen={oz.RM_FADER: "/f{n}"})
    rm.konfigurieren(k2)
    rm.tick(st, jetzt=2.0)
    assert sender[-1].gesendet == [("/f1", 128)]


def test_rueckmeldung_alles_neu_und_inaktiv():
    rm, sender = _rm()
    st = _State()
    rm.tick(st, jetzt=1.0)
    rm.alles_neu()
    assert rm.tick(st, jetzt=2.0) == 8
    rm.konfigurieren(RueckmeldeKonfig(aktiv=False))
    assert not rm.aktiv
    assert rm.tick(st, jetzt=3.0) == 0


def test_rueckmeldung_max_je_tick():
    rm, sender = _rm()
    rm.konfigurieren(RueckmeldeKonfig(aktiv=True, executoren="1-20"))
    rm.MAX_JE_TICK = 10
    st = _State()
    assert rm.tick(st, jetzt=1.0) == 10
    assert rm.tick(st, jetzt=2.0) == 10     # Rest folgt


def test_executoren_aus_text():
    assert oz.executoren_aus_text("1-3, 8;5") == [1, 2, 3, 8, 5]
    assert oz.executoren_aus_text("4-2") == [2, 3, 4]
    assert oz.executoren_aus_text("0, 21, x, 1-a, 20") == [20]
    assert oz.executoren_aus_text("") == []


def test_vorlagen_vollstaendig_und_ehrlich_markiert():
    for name, v in oz.VORLAGEN.items():
        assert set(v.adressen) == set(oz.RM_ARTEN), name
        for a in v.adressen.values():
            assert a == "" or a.startswith("/")
        if name != "lightos":
            assert not v.geprueft, f"{name} wurde nie mit Geraet geprueft"
    assert oz.VORLAGEN["grandma3"].versatz == 200


# ── Speichern / Laden ────────────────────────────────────────────────────

def test_speichern_laden_rundreise(tmp_path):
    p = str(tmp_path / "osc.json")
    k = Konfig(aktiv=True, zuordnungen=[
        Zuordnung("/Page1/Fader{n}", oz.ZIEL_FADER, versatz=-200, bereich=BEREICH_100),
        Zuordnung("/szene", oz.ZIEL_FKT_START, funktion="Lauflicht"),
    ])
    k.rueckmeldung = RueckmeldeKonfig(aktiv=True, ziel_ip="192.0.2.20", ziel_port=8000)
    assert oz.speichere_konfig(k, p)
    assert not os.path.exists(p + ".tmp")
    k2 = oz.lade_konfig(p)
    assert k2.als_dict() == k.als_dict()
    roh = json.load(open(p, encoding="utf-8"))
    assert roh["version"] == oz.FORMAT_VERSION


def test_fehlende_und_kaputte_datei(tmp_path):
    assert oz.lade_konfig(str(tmp_path / "fehlt.json")).zuordnungen == []
    for inhalt in ("{kaputt", "[]", "null", '"text"', "1"):
        p = tmp_path / "k.json"
        p.write_text(inhalt, encoding="utf-8")
        k = oz.lade_konfig(str(p))
        assert k.zuordnungen == [] and not k.rueckmeldung.aktiv, inhalt


def test_kaputte_zeilen_kosten_nur_sich(tmp_path):
    p = tmp_path / "k.json"
    p.write_text(json.dumps({
        "aktiv": True,
        "zuordnungen": [
            {"adresse": "/ok/{n}", "ziel": "executor_fader"},
            {"adresse": "kein-strich", "ziel": "executor_fader"},
            {"adresse": "/x", "ziel": "unbekannt"},
            "keine-zeile",
            {"adresse": "/y", "ziel": "executor_go", "nummer": "abc",
             "versatz": None, "bereich": "0-9"},
        ],
        "rueckmeldung": {"aktiv": True, "ziel_ip": "kein.host", "ziel_port": 99999,
                         "rate_hz": 1000, "vorlage": "gibtsnicht",
                         "adressen": {"fader": "ohne strich", "blackout": "/bo"}},
    }), encoding="utf-8")
    k = oz.lade_konfig(str(p))
    assert [z.adresse for z in k.zuordnungen] == ["/ok/{n}", "/y"]
    y = k.zuordnungen[1]
    assert (y.nummer, y.versatz, y.bereich) == (1, 0, BEREICH_1)
    rm = k.rueckmeldung
    assert rm.ziel_ip == "127.0.0.1"          # Hostnamen werden nicht aufgeloest
    assert rm.ziel_port == 65535 and rm.rate_hz == oz.RATE_MAX
    assert rm.vorlage == "lightos"
    assert rm.adressen[oz.RM_FADER] == "" and rm.adressen[oz.RM_BLACKOUT] == "/bo"


def test_alte_datei_ohne_rueckmeldung_laedt(tmp_path):
    p = tmp_path / "k.json"
    p.write_text(json.dumps({"zuordnungen": [{"adresse": "/a", "ziel": "blackout"}]}),
                 encoding="utf-8")
    k = oz.lade_konfig(str(p))
    assert k.aktiv and len(k.zuordnungen) == 1 and not k.rueckmeldung.aktiv


def test_pfad_ist_in_der_testumgebung_umgelenkt():
    from src.core.paths import osc_zuordnungen_path
    assert osc_zuordnungen_path() == os.environ["LIGHTOS_OSC_ZUORDNUNGEN"]
    assert oz.konfig_pfad() == os.environ["LIGHTOS_OSC_ZUORDNUNGEN"]
    assert "lightos_test_osc_zuordnungen_" in os.path.basename(oz.konfig_pfad())


# ── Gegenpruefung (Haertung) ─────────────────────────────────────────────

def test_viele_sterne_und_lange_adresse_blockieren_nicht():
    """ReDoS: Muster mit Sternen ueber mehrere Adressteile duerfen bei einer
    boesartigen Adresse nicht exponentiell zurueckverfolgen; ueberlange
    Adressen werden gar nicht verglichen."""
    import time as _t
    zu, st = _zu(Zuordnung("/*a*b/*a*b/*a*b/*a*b/*a*b/*a*b", oz.ZIEL_GO))
    teil = "a" * 24 + "b"
    # fuenf Teile passen, der letzte nie (kein b) -> vorher Sekunden lang
    boese = "/" + "/".join([teil] * 5 + ["a" * 24])
    assert len(boese) < oz.ADRESSE_MAX
    t0 = _t.perf_counter()
    assert zu.empfange(boese, ()) == 0
    assert zu.empfange("/" + "a" * 5000, ()) == 0
    assert _t.perf_counter() - t0 < 0.5
    lang, _st = _zu(Zuordnung("/*", oz.ZIEL_GO))
    assert lang.empfange("/" + "a" * oz.ADRESSE_MAX, ()) == 0
    assert lang.empfange("/" + "a" * (oz.ADRESSE_MAX - 1), ()) == 1
    # passende kurze Adresse wirkt weiterhin
    assert _senden(zu, st, "/xab/ab/ab/ab/ab/aXb") == 1


def test_drei_sterne_je_adressteil_ungueltig_zwei_gueltig():
    assert oz.muster_zu_regex("/*a*a*b") is None
    assert oz.muster_zu_regex("/x/*a*") is not None
    assert oz.muster_zu_regex("/***a") is not None      # Folge = ein Stern
    assert oz.muster_zu_regex("/k/[a/b]") is None       # / in Klammern
    rx = oz.muster_zu_regex("/y/{a,ab}/z")
    assert rx.match("/y/ab/z") and rx.match("/y/a/z")


def test_n_mit_riesenzahl_und_kaputte_nummer_brechen_nichts_ab(monkeypatch):
    gerufen = []
    zu = OscZuordnung()
    zu.konfigurieren(Konfig(zuordnungen=[
        Zuordnung("/a/{n}", oz.ZIEL_GO),
        Zuordnung("/a/*", oz.ZIEL_STOP, nummer=2),
        Zuordnung("/h", oz.ZIEL_GO, nummer_aus_argument=True),
    ]))
    zu.set_wecker(lambda: gerufen.append(1))
    assert zu.empfange("/a/" + "1" * 200, ()) == 1    # nur der Stern-Treffer
    assert gerufen == [1]
    for arg in ("--5", "²", "٣", "1" * 5000):
        assert zu.empfange("/h", (arg,)) == 0
    assert zu.verworfen == 4
    assert oz.vorschlag_muster("/a/" + "1" * 5000)[1] is None
    # Ein Fehler in einem Treffer kostet nur diesen: der naechste wird noch
    # eingereiht und der Wecker laeuft.
    echt = OscZuordnung._aktion

    def kaputt(m, z, args):
        if z.ziel == oz.ZIEL_GO:
            raise ValueError("kaputt")
        return echt(m, z, args)
    monkeypatch.setattr(OscZuordnung, "_aktion", staticmethod(kaputt))
    assert zu.empfange("/a/3", ()) == 1
    assert gerufen == [1, 1]


@pytest.mark.parametrize("bereich,wert", [(BEREICH_1, 0.5), (BEREICH_100, 50)])
def test_tastenschwelle_genau_halbe_skala_loest_aus(bereich, wert):
    zu, st = _zu(Zuordnung("/k{n}", oz.ZIEL_GO, bereich=bereich))
    _senden(zu, st, "/k1", wert)
    assert st.playback_engine.get_executor(1).gedrueckt == ["go"]


class _Uhr:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def _echo_aufbau():
    uhr = _Uhr()
    sender: list = []

    def fabrik(ip, port):
        s = _Sender(ip, port)
        sender.append(s)
        return s
    rm = OscRueckmeldung(sender_fabrik=fabrik, uhr=uhr)
    rm.konfigurieren(RueckmeldeKonfig(aktiv=True, executoren="1"))
    zu, st = _zu(Zuordnung("/lightos/exec/{n}/fader", oz.ZIEL_FADER))
    zu.set_rueckmeldung(rm)
    return uhr, rm, zu, st, sender[0]


def test_echo_der_rueckmeldung_ueberschreibt_lokale_bewegung_nicht():
    uhr, rm, zu, st, s = _echo_aufbau()
    ex = st.playback_engine.get_executor(1)
    adresse = "/lightos/exec/1/fader"
    offen = None
    for v in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7):
        uhr.t += 0.034
        ex.fader_value = v                      # Nutzer zieht lokal
        if offen is not None:                   # Echo des letzten Werts
            zu.empfange(adresse, (offen,))
            zu.abarbeiten(st)
        rm.tick(st, jetzt=uhr.t)
        offen = dict(s.gesendet).get(adresse)
    for _ in range(3):
        uhr.t += 0.034
        zu.empfange(adresse, (offen,))
        zu.abarbeiten(st)
        rm.tick(st, jetzt=uhr.t)
    assert ex.fader_value == pytest.approx(0.7)
    assert [w for a, w in s.gesendet if a == adresse][-1] == pytest.approx(0.7)


def test_echo_schutz_laesst_pultbewegungen_durch():
    uhr, rm, zu, st, s = _echo_aufbau()
    ex = st.playback_engine.get_executor(1)
    adresse = "/lightos/exec/1/fader"
    for v in (0.5, 0.3, 0.5, 0.3):              # Pult schnell hin und her
        uhr.t += 0.034
        _senden(zu, st, adresse, v)
        assert ex.fader_value == pytest.approx(v)
        rm.tick(st, jetzt=uhr.t)
    # nach dem Fenster gilt auch ein frueher gesendeter Wert wieder
    ex.fader_value = 0.9
    rm.tick(st, jetzt=uhr.t + 0.04)
    uhr.t += 0.04 + oz.ECHO_FENSTER + 0.01
    _senden(zu, st, adresse, 0.9)
    _senden(zu, st, adresse, 0.1)
    assert ex.fader_value == pytest.approx(0.1)


def test_lernen_ueberspringt_feste_adressen_und_echo():
    uhr, rm, zu, st, s = _echo_aufbau()
    k = RueckmeldeKonfig(aktiv=True, executoren="1")
    k.vorlage_anwenden("touchosc")              # Ausgang /1/fader{n}
    rm.konfigurieren(k)
    rm.tick(st, jetzt=uhr.t)                    # meldet Fader 1 = 1.0
    gelernt = []
    zu.lerne(lambda a, args, von: gelernt.append(a))
    zu.empfange("/lightos/exec/2/go", (1.0,))   # feste Adresse
    zu.empfange("/lightos/go", ())
    zu.empfange("/1/fader1", (1.0,))            # Echo der Rueckmeldung
    assert gelernt == [] and zu.lernt
    zu.empfange("/1/fader1", (0.3,))            # echte Bewegung: wird gelernt
    assert gelernt == ["/1/fader1"]
    zu.lerne(lambda a, args, von: gelernt.append(a))
    zu.empfange("/Page1/Fader201", (40.0,))
    assert gelernt == ["/1/fader1", "/Page1/Fader201"] and not zu.lernt
