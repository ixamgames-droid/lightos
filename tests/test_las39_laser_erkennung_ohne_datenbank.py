"""LAS-39: Laser-Erkennung, wenn die Geraete-Datenbank beim Patchen fehlt.

Offen geblieben aus LAS-38: die Auskunft „hat dieses Profil in irgendeinem
Modus einen Laserkanal?“ kommt aus der Geraete-Datenbank. War sie beim
Patchen nicht erreichbar, galt die fehlende Auskunft als „nein“ — ein
Kombigeraet im Kurz-Modus ohne eigenen Laserkanal lief bei einem DANACH
ausgeloesten LASER NOT-AUS weiter, und der Zaehler am Knopf nannte es nicht.

Jetzt gilt (Sicherheit vor Bequemlichkeit):

* fehlt die Auskunft, gilt das Geraet VORERST als Laser — der NOT-AUS
  schaltet es dunkel, ein Wert daran loest den NOT-AUS nicht;
* der Betreiber sieht es (Statuszeile, NOT-AUS-Knopf):
  „Laser-Erkennung unvollständig: Geräte-Datenbank nicht erreichbar“;
* die Auskunft wird nachgeholt — beim naechsten Plan-Neubau und beim naechsten
  Ausloesen des NOT-AUS (erst NACH dem Verriegeln); danach ist eine normale
  Lampe wieder frei und der Hinweis zurueckgenommen.

Die Geraete-Datenbank wird hier durch eine Attrappe ersetzt
(``_profile_mit_laserkanal``), es wird nichts gesendet.
"""
from __future__ import annotations

import os
import threading
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.app_state import AppState
from src.core.dmx.universe import Universe
from src.core.laser import erkennung

_KOMBI_PROFIL = 939001       # Kombigeraet: Kurz-Modus ohne Laserkanal
_LAMPE_PROFIL = 939002       # PAR: kein Laser in keinem Modus


@pytest.fixture(autouse=True)
def _frische_auskunft():
    alt = getattr(erkennung, "_profil_quelle", None)
    erkennung.vergiss_profile()
    yield
    erkennung.setze_profil_quelle(alt)
    erkennung.vergiss_profile()


class _Bereich:
    range_from, range_to, name, kind = 0, 255, "", ""


class _Kanal:
    def __init__(self, nr, attribut, name, default):
        self.channel_number = nr
        self.attribute = attribut
        self.name = name
        self.default_value = default
        self.ranges = []


class _Gepatcht:
    protocol = ""
    dimmer_curve = "linear"
    spider_dual_tilt = False
    manufacturer_name = "Testwerk"

    def __init__(self, fid, adresse, profil_id, typ, name, modus, kanaele):
        self.fid, self.universe, self.address = fid, 1, adresse
        self.fixture_profile_id = profil_id
        self.fixture_type, self.fixture_name = typ, name
        self.label = f"Geraet {fid}"
        self.mode_name, self.channel_count = modus, len(kanaele)
        self.kanaele = kanaele


def _kombi():
    return _Gepatcht(1, 1, _KOMBI_PROFIL, "other", "Kombi Bar", "3-channel", [
        _Kanal(1, "raw", "LED-Betrieb", 120),
        _Kanal(2, "raw", "Show-Auswahl", 120),
        _Kanal(3, "raw", "Auto-Geschwindigkeit", 120)])


def _lampe():
    return _Gepatcht(2, 10, _LAMPE_PROFIL, "par", "LED PAR", "4ch", [
        _Kanal(1, "intensity", "Dimmer", 200),
        _Kanal(2, "color_r", "Rot", 0),
        _Kanal(3, "color_g", "Gruen", 0),
        _Kanal(4, "color_b", "Blau", 0)])


class _FM:
    def tick(self, universes, patch_cache, dt):
        pass


class _Datenbank:
    """Attrappe der Geraete-Datenbank: ``da`` = erreichbar; ``fragen`` zaehlt
    die Abfragen (und haelt fest, ob der NOT-AUS da schon verriegelt war)."""

    def __init__(self, st_ref):
        self.da = False
        self.fragen = []
        self._st = st_ref

    def __call__(self, ids):
        st = self._st.get("st")
        self.fragen.append((sorted(i for i in ids if i is not None),
                            bool(getattr(st, "laser_estop_active", False))))
        if not self.da:
            raise RuntimeError("Geraete-Datenbank nicht erreichbar")
        return {i: i == _KOMBI_PROFIL for i in ids if i is not None}


@pytest.fixture
def rig(monkeypatch):
    geraete = [_kombi(), _lampe()]
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: fx.kanaele)
    ref = {}
    db = _Datenbank(ref)
    # Die angemeldete Quelle (``_profil_hat_laserkanal``) und das Bestimmen
    # beim Patchen fragen beide ueber diese Funktion.
    monkeypatch.setattr(A, "_profile_mit_laserkanal", db)
    erkennung.setze_profil_quelle(A._profil_hat_laserkanal)
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = _FM()
    st._patch_cache = list(geraete)
    st._prog_lock = threading.RLock()
    st.output_manager = types.SimpleNamespace(set_gm_address_mask=lambda m: None)
    st.laser_estop_active = False
    st._laser_estop_addrs = {}
    st._laser_fids = frozenset()
    st.base_levels = {}
    st._engine_extra_prev = {}
    st._suppress_emits = False
    st._ui_marshaller = None
    st._callbacks = []
    hinweise = []
    st._callbacks.append(lambda ev, d: hinweise.append(d) if ev == "hinweis" else None)
    ref["st"] = st
    return types.SimpleNamespace(st=st, db=db, hinweise=hinweise)


def _patchen(st):
    """Wie ``_reload_patch_cache``: erst bestimmen, dann den Plan bauen."""
    st._laser_profile_bestimmen()
    st._rebuild_render_plan()


def _werte(st):
    st._render_frame(0.02)
    live = st.universes[1]
    return ([live.get_channel(a) for a in (1, 2, 3)],
            [live.get_channel(a) for a in (10, 11, 12, 13)])


# ══════════════════════════════════════════════════════════════════════════════
# A) Der Befund: Datenbank faellt beim Patchen aus, NOT-AUS danach
# ══════════════════════════════════════════════════════════════════════════════

def test_kombigeraet_geht_beim_spaeteren_notaus_dunkel(rig):
    """Ohne LAS-39 rot: das Kombigeraet lief mit 120/120/120 weiter."""
    st = rig.st
    _patchen(st)
    kombi, _lampe_w = _werte(st)
    assert kombi == [120, 120, 120]
    st.set_laser_estop(True)
    kombi, _lampe_w = _werte(st)
    assert kombi == [0, 0, 0], "fehlende Auskunft darf kein „kein Laser“ sein"


def test_zaehler_nennt_das_geraet(rig):
    st = rig.st
    _patchen(st)
    assert 1 in st._laser_fids
    assert st.laser_anzahl() >= 1


def test_ein_wert_am_unsicheren_geraet_loest_den_notaus_nicht(rig):
    st = rig.st
    _patchen(st)
    assert st._laser_fids == frozenset({1, 2})
    assert not (st._laser_rearm_menge() & {1, 2})


def test_nichts_wird_als_nein_gemerkt(rig):
    _patchen(rig.st)
    assert not erkennung.profil_bekannt(_KOMBI_PROFIL)
    assert not erkennung.profil_bekannt(_LAMPE_PROFIL)
    assert erkennung.offene_profile() == {_KOMBI_PROFIL, _LAMPE_PROFIL}


# ══════════════════════════════════════════════════════════════════════════════
# B) Sichtbar fuer den Betreiber
# ══════════════════════════════════════════════════════════════════════════════

def test_hinweis_beim_patchen_und_am_knopf(rig):
    st = rig.st
    _patchen(st)
    assert any(erkennung.UNVOLLSTAENDIG in h for h in rig.hinweise)
    knopf = st.laser_erkennung_hinweis()
    assert erkennung.UNVOLLSTAENDIG in knopf
    assert "2 Geräte" in knopf


def test_hinweis_nur_beim_wechsel_nicht_bei_jedem_plan(rig):
    st = rig.st
    _patchen(st)
    _patchen(st)
    st._rebuild_render_plan()
    assert sum(erkennung.UNVOLLSTAENDIG in h for h in rig.hinweise) == 1


def test_frischer_notaus_zeigt_den_hinweis_erneut(rig):
    st = rig.st
    _patchen(st)
    rig.hinweise.clear()
    st.set_laser_estop(True)
    assert any(erkennung.UNVOLLSTAENDIG in h for h in rig.hinweise)


def test_patch_hinweis_des_geraets_nennt_die_fehlende_auskunft():
    erkennung.setze_profil_quelle(lambda pid: None)      # weiss es nicht
    text = erkennung.hinweis_text(_kombi(), _kombi().kanaele)
    assert "gilt vorerst als Laser" in text
    assert erkennung.UNVOLLSTAENDIG in text


# ══════════════════════════════════════════════════════════════════════════════
# C) Nachholen, sobald die Datenbank wieder antwortet
# ══════════════════════════════════════════════════════════════════════════════

def test_naechster_plan_neubau_holt_nach_und_gibt_die_lampe_frei(rig):
    st = rig.st
    _patchen(st)
    rig.db.da = True
    rig.hinweise.clear()
    _patchen(st)
    assert st._laser_fids == frozenset({1})
    assert erkennung.offene_profile() == frozenset()
    assert st.laser_erkennung_hinweis() == ""
    assert rig.hinweise == [erkennung.hinweis_vollstaendig()]
    st.set_laser_estop(True)
    kombi, lampe = _werte(st)
    assert kombi == [0, 0, 0]
    assert lampe[0] == 200, "die Lampe darf nicht dauerhaft dunkel bleiben"


def test_naechster_notaus_holt_nach_erst_nach_dem_verriegeln(rig):
    st = rig.st
    _patchen(st)
    rig.db.da = True
    rig.db.fragen.clear()
    rig.hinweise.clear()
    st.set_laser_estop(True)
    assert st.laser_estop_active is True
    assert rig.db.fragen, "der NOT-AUS muss die fehlende Auskunft nachholen"
    assert all(verriegelt for _ids, verriegelt in rig.db.fragen), \
        "der NOT-AUS darf nie auf die Datenbank warten"
    assert st._laser_fids == frozenset({1})
    assert rig.hinweise[-1] == erkennung.hinweis_vollstaendig()
    # Dieser NOT-AUS haelt das Kombigeraet dunkel; nach dem Loesen gibt der
    # naechste die Lampe frei.
    assert _werte(st)[0] == [0, 0, 0]
    st.set_laser_estop(False)
    st.set_laser_estop(True)
    kombi, lampe = _werte(st)
    assert kombi == [0, 0, 0]
    assert lampe[0] == 200


def test_notaus_bei_weiter_fehlender_datenbank_bleibt_dunkel(rig):
    st = rig.st
    _patchen(st)
    st.set_laser_estop(True)            # Nachholen scheitert erneut
    assert st.laser_estop_active is True
    kombi, lampe = _werte(st)
    assert kombi == [0, 0, 0]
    assert lampe == [0, 0, 0, 0]
    assert erkennung.offene_profile() == {_KOMBI_PROFIL, _LAMPE_PROFIL}


def test_ohne_offene_profile_fragt_der_notaus_nicht(rig):
    st = rig.st
    rig.db.da = True
    _patchen(st)
    rig.db.fragen.clear()
    st.set_laser_estop(True)
    assert rig.db.fragen == []


# ══════════════════════════════════════════════════════════════════════════════
# D) Die Regel selbst
# ══════════════════════════════════════════════════════════════════════════════

def test_fehlende_auskunft_ist_grund_profil_unbekannt():
    def kaputt(_pid):
        raise RuntimeError("gesperrt")

    erkennung.setze_profil_quelle(kaputt)
    g = _kombi()
    assert erkennung.profil_auskunft(g) is None
    assert erkennung.laser_grund(g, g.kanaele) == erkennung.GRUND_PROFIL_UNBEKANNT
    assert erkennung.nur_ueber_namen(g, g.kanaele) is True
    assert erkennung.profil_traegt_laser(g) is False
    assert _KOMBI_PROFIL in erkennung.offene_profile()


def test_antwort_nimmt_das_profil_aus_der_offenen_liste():
    antworten = [None, False]
    erkennung.setze_profil_quelle(lambda _pid: antworten.pop(0))
    g = _lampe()
    assert erkennung.laser_grund(g, g.kanaele) == erkennung.GRUND_PROFIL_UNBEKANNT
    assert erkennung.laser_grund(g, g.kanaele) == ""
    assert erkennung.offene_profile() == frozenset()


def test_verwerfen_leert_auch_die_offene_liste():
    erkennung.setze_profil_quelle(lambda _pid: None)
    erkennung.profil_auskunft(_kombi())
    assert erkennung.offene_profile()
    erkennung.vergiss_profile()
    assert erkennung.offene_profile() == frozenset()


def test_ohne_quelle_bleibt_es_bei_der_regel_je_modus():
    erkennung.setze_profil_quelle(None)
    assert erkennung.laser_grund(_kombi(), _kombi().kanaele) == ""
    assert erkennung.offene_profile() == frozenset()


def test_knopf_zeigt_die_unvollstaendige_erkennung():
    """Der NOT-AUS-Knopf in der Kopfleiste fragt den Hinweis ab."""
    pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "src", "ui", "main_window.py")
    with open(pfad, encoding="utf-8") as f:
        text = f.read()
    rumpf = text.split("def _sync_notaus_button", 1)[1].split("\n    def ", 1)[0]
    assert "laser_erkennung_hinweis()" in rumpf


def test_anleitung_nennt_die_grenze():
    pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "docs", "anleitung_laser", "ANLEITUNG_LASER.md")
    with open(pfad, encoding="utf-8") as f:
        text = f.read()
    assert erkennung.UNVOLLSTAENDIG in text
