"""LAS-38: die Laser-Erkennung sieht auf ALLE Modi des Profils.

Offen geblieben aus LAS-37: die Regel sah nur die Kanaele des gepatchten Modus.
Ein Kombigeraet in einem Kurz-Modus ohne eigenen Laserkanal — Chauvet GigBAR 2
„3-channel“, Cameo Multi FX Bar „2 Channel“, der Laser laeuft dort ueber
Automatikprogramme — galt nicht als Laser: LASER NOT-AUS gedrueckt, das Geraet
lief weiter.

Geprueft wird

* ueber die ganze mitgelieferte Bibliothek: alle Modi eines Profils geben
  dieselbe Antwort, und neu dazu kommen genau die zwei bekannten Kurz-Modi;
* an diesen beiden Geraeten: Render-Plan/NOT-AUS, Zaehler, Blackout, „Alles
  Weiss“ — und dass ein Wert an so einem Geraet den NOT-AUS nicht loest;
* der Weg ueber die Geraete-Datenbank: je Profil EINMAL bestimmt (beim
  Patchen/Laden, eine Abfrage fuer alle Profile zusammen), der Render-Plan
  fragt danach nicht mehr; verworfen zusammen mit dem Kanal-Cache.

Es wird nichts gesendet.
"""
from __future__ import annotations

import glob
import json
import os
import threading
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core import all_white
from src.core.app_state import AppState
from src.core.dmx.universe import Universe
from src.core.laser import erkennung

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BIB = os.path.join(_REPO, "fixtures", "bibliothek")

#: Was durch die Profil-Regel NEU als Laser gilt — und sonst nichts. Aendert
#: sich die Bibliothek, zeigt der Test die neue Liste; sie gehoert dann hier
#: eingetragen UND angesehen (Fehlalarm?).
NEU_UEBER_ANDEREN_MODUS = {
    ("cameo/multi-fx-bar.json", "2 Channel"),
    ("chauvet/gigbar-2.json", "3-channel"),
}


@pytest.fixture(autouse=True)
def _frische_auskunft():
    """Jeder Fall beginnt und endet ohne gemerkte Profile; die Quelle
    (``app_state`` meldet sich beim Import an) bleibt, wie sie war."""
    # ``getattr``: auf einem Stand ohne LAS-38 soll jeder Fall an seiner eigenen
    # Aussage scheitern, nicht schon hier.
    vergiss = getattr(erkennung, "vergiss_profile", lambda: None)
    alt = getattr(erkennung, "_profil_quelle", None)
    vergiss()
    yield
    getattr(erkennung, "setze_profil_quelle", lambda q: None)(alt)
    vergiss()


# ── Attrappen aus den Profil-Dateien ────────────────────────────────────────

class _Bereich:
    def __init__(self, d):
        self.range_from = d.get("von", 0)
        self.range_to = d.get("bis", 255)
        self.name = d.get("name") or ""
        self.kind = d.get("art") or ""


class _Kanal:
    def __init__(self, nr, d):
        self.channel_number = nr
        self.attribute = d.get("attribut") or "raw"
        self.name = d.get("name") or ""
        self.default_value = d.get("default", 0)
        self.ranges = [_Bereich(b) for b in (d.get("bereiche") or [])]


class _Geraet:
    protocol = ""
    dimmer_curve = "linear"

    def __init__(self, fid, universum, adresse, profil, profil_id, modus, kanaele, datei):
        self.fid = fid
        self.universe = universum
        self.address = adresse
        self.fixture_profile_id = profil_id
        self.fixture_type = profil.get("typ") or "other"
        self.fixture_name = profil.get("modell") or ""
        self.manufacturer_name = profil.get("hersteller") or ""
        self.label = f"Geraet {fid}"
        self.mode_name = modus
        self.channel_count = len(kanaele)
        self.datei = datei


def _bibliothek():
    """``([(Geraet, [Kanaele])], {profil_id: hat_laserkanal})`` — jedes Profil in
    jedem Modus einmal gepatcht; die Profil-Auskunft so, wie die Datei sie gibt
    (irgendein Modus mit Laserkanal, oder Typ ``laser``)."""
    paare, profile = [], {}
    fid, universum, adresse = 1, 1, 1
    dateien = sorted(glob.glob(os.path.join(_BIB, "**", "*.json"), recursive=True))
    for nummer, pfad in enumerate(dateien):
        with open(pfad, encoding="utf-8") as f:
            profil = json.load(f)
        datei = os.path.relpath(pfad, _BIB).replace("\\", "/")
        profil_id = 500000 + nummer
        modi = [(m.get("name") or "",
                 [_Kanal(i, k) for i, k in enumerate(m.get("kanaele") or [], 1)])
                for m in (profil.get("modi") or [])]
        profile[profil_id] = (
            str(profil.get("typ") or "").strip().lower() == "laser"
            or any(erkennung.kanaele_tragen_laser(k) for _n, k in modi))
        for name, kanaele in modi:
            if not kanaele:
                continue
            if adresse + len(kanaele) - 1 > 512:
                universum, adresse = universum + 1, 1
            paare.append((_Geraet(fid, universum, adresse, profil, profil_id, name,
                                  kanaele, datei), kanaele))
            fid += 1
            adresse += len(kanaele)
    return paare, profile


class _FM:
    def tick(self, universes, patch_cache, dt):
        pass


def _zustand(geraete):
    """Ein AppState ohne Show-Datenbank und ohne Ausgabe (``_patch_cache``
    gesetzt, Plan noch nicht gebaut)."""
    st = AppState.__new__(AppState)
    st.universes = {u: Universe(u) for u in sorted({g.universe for g in geraete})}
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
    st._suppress_emits = True
    return st


@pytest.fixture
def bib(monkeypatch):
    paare, profile = _bibliothek()
    assert len(paare) > 400, "die Bibliothek ist unerwartet klein — Pfad pruefen"
    kanaele = {g.fid: k for g, k in paare}
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: kanaele[fx.fid])
    # Die Auskunft kommt hier aus den Dateien, nicht aus der Geraete-Datenbank.
    erkennung.setze_profil_quelle(lambda profil_id: profile.get(profil_id))
    st = _zustand([g for g, _ in paare])
    st._rebuild_render_plan()
    return types.SimpleNamespace(paare=paare, st=st, profile=profile)


def _adressen(g, kanaele):
    return {g.address + k.channel_number - 1 for k in kanaele}


# ══════════════════════════════════════════════════════════════════════════════
# A) Die Regel
# ══════════════════════════════════════════════════════════════════════════════

class _K:
    def __init__(self, attribute="raw", name=""):
        self.attribute, self.name = attribute, name


class _G:
    def __init__(self, profil_id=None, typ="other", fixture_name="", label=""):
        self.fixture_profile_id = profil_id
        self.fixture_type, self.fixture_name = typ, fixture_name
        self.label, self.manufacturer_name = label, ""


def test_anderer_modus_des_profils_macht_das_geraet_zum_laser():
    erkennung.merke_profil(7, True)
    kurz = [_K("raw", "Auto Program"), _K("raw", "Speed")]
    g = _G(7, fixture_name="Multi FX Bar")
    assert erkennung.laser_grund(g, kurz) == erkennung.GRUND_ANDERER_MODUS
    assert erkennung.ist_laser(g, kurz) is True


def test_profil_ohne_laser_bleibt_eine_lampe():
    erkennung.merke_profil(8, False)
    g = _G(8, "par", "LED PAR 64")
    assert erkennung.laser_grund(g, [_K("intensity", "Dimmer")]) == ""


def test_schon_erkannte_geraete_behalten_ihren_grund():
    """Typ, ``laser_*``-Kanal, Kanalname und Geraetename gehen vor — fuer sie
    wird das Profil gar nicht erst gefragt."""
    gefragt = []
    erkennung.setze_profil_quelle(lambda pid: gefragt.append(pid) or True)
    assert erkennung.laser_grund(_G(1, "laser"), []) == "typ"
    assert erkennung.laser_grund(_G(1), [_K("laser_x")]) == "kanal"
    assert erkennung.laser_grund(_G(1), [_K("raw", "Laser: Red")]) == "kanalname"
    assert erkennung.laser_grund(_G(1, fixture_name="Laser Bar"), []) == "name"
    assert gefragt == []


def test_ein_wert_an_so_einem_geraet_ist_kein_laser_wieder_an():
    """Wie bei den nur ueber einen Namen erkannten Geraeten (LAS-37): gedeckt
    vom NOT-AUS, aber ein Wert auf „Auto Program“ darf ihn nicht loesen."""
    erkennung.merke_profil(7, True)
    assert erkennung.nur_ueber_namen(_G(7), [_K("raw", "Auto Program")]) is True
    assert erkennung.GRUND_ANDERER_MODUS in erkennung.NUR_NAME


def test_hinweis_beim_patchen_nennt_den_anderen_modus():
    erkennung.merke_profil(7, True)
    text = erkennung.hinweis_text(_G(7, label="Bar links"), [_K("raw", "Auto Program")])
    assert "Bar links" in text
    assert "anderen Modus" in text
    assert "NOT-AUS" in text and "Blackout" in text


def test_geraet_ohne_profilnummer_wird_nicht_nachgeschlagen():
    gefragt = []
    erkennung.setze_profil_quelle(lambda pid: gefragt.append(pid) or True)
    assert erkennung.profil_traegt_laser(types.SimpleNamespace()) is False
    assert erkennung.profil_traegt_laser(_G(None)) is False
    assert gefragt == []


def test_die_quelle_wird_je_profil_nur_einmal_gefragt():
    gefragt = []
    erkennung.setze_profil_quelle(lambda pid: gefragt.append(pid) or (pid == 7))
    for _ in range(5):
        assert erkennung.profil_traegt_laser(_G(7)) is True
        assert erkennung.profil_traegt_laser(_G(8)) is False
    assert gefragt == [7, 8]


def test_fehler_und_weiss_nicht_werden_nicht_gemerkt():
    """Eine gescheiterte Abfrage darf die Antwort nicht auf „nein“ festnageln."""
    antworten = [RuntimeError("Datenbank gesperrt"), None, True]

    def quelle(_pid):
        a = antworten.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    erkennung.setze_profil_quelle(quelle)
    g = _G(7)
    assert erkennung.profil_traegt_laser(g) is False     # Fehler
    assert erkennung.profil_bekannt(7) is False
    assert erkennung.profil_traegt_laser(g) is False     # weiss nicht
    assert erkennung.profil_bekannt(7) is False
    assert erkennung.profil_traegt_laser(g) is True      # jetzt beantwortet
    assert erkennung.profil_bekannt(7) is True


def test_ohne_quelle_bleibt_es_bei_der_regel_je_modus():
    erkennung.setze_profil_quelle(None)
    assert erkennung.laser_grund(_G(7), [_K("raw", "Auto Program")]) == ""


# ══════════════════════════════════════════════════════════════════════════════
# B) Ueber die ganze Bibliothek
# ══════════════════════════════════════════════════════════════════════════════

def test_alle_modi_eines_profils_geben_dieselbe_antwort(bib):
    """Die Luecke aus LAS-37: ein Modus Laser, ein anderer desselben Geraets
    nicht. Es darf keine mehr geben."""
    je = {}
    for g, kanaele in bib.paare:
        je.setdefault(g.datei, []).append((g.mode_name, erkennung.ist_laser(g, kanaele)))
    luecken = {(d, modus) for d, modi in je.items()
               if any(ja for _m, ja in modi) for modus, ja in modi if not ja}
    assert luecken == set()


def test_neu_dazu_kommen_genau_die_bekannten_kurzmodi(bib):
    neu = {(g.datei, g.mode_name) for g, kanaele in bib.paare
           if erkennung.laser_grund(g, kanaele) == erkennung.GRUND_ANDERER_MODUS}
    assert neu == NEU_UEBER_ANDEREN_MODUS


def _kurzmodi(bib):
    treffer = [(g, k) for g, k in bib.paare
               if (g.datei, g.mode_name) in NEU_UEBER_ANDEREN_MODUS]
    assert len(treffer) == len(NEU_UEBER_ANDEREN_MODUS)
    return treffer


def test_notaus_deckt_die_kurzmodi_ganz(bib):
    st = bib.st
    for g, kanaele in _kurzmodi(bib):
        assert g.fid in st._laser_fids, g.datei
        assert _adressen(g, kanaele) <= set(st._laser_estop_addrs.get(g.universe, ())), g.datei


def test_der_plan_stimmt_ueberall_mit_der_regel_ueberein(bib):
    st = bib.st
    erwartet_fids, erwartet = set(), {}
    for g, kanaele in bib.paare:
        if erkennung.ist_laser(g, kanaele):
            erwartet_fids.add(g.fid)
            erwartet.setdefault(g.universe, set()).update(_adressen(g, kanaele))
    assert set(st._laser_fids) == erwartet_fids
    assert {u: set(s) for u, s in st._laser_estop_addrs.items()} == erwartet
    assert st.laser_anzahl() == len(erwartet_fids)


def test_blackout_und_alles_weiss_sehen_die_kurzmodi(bib):
    for g, kanaele in _kurzmodi(bib):
        erhalten, aus = AppState._blackout_aufteilung(g, kanaele)
        assert not erhalten and aus == _adressen(g, kanaele), g.datei
        assert all_white.ist_geraet_ohne_licht(g, kanaele), g.datei


def test_die_kurzmodi_loesen_den_notaus_nicht(bib):
    st = bib.st
    for g, _kanaele in _kurzmodi(bib):
        assert g.fid not in st._laser_rearm_menge(), g.datei


def test_alles_weiss_laesst_lampen_weiter_zu(bib):
    lampen = [g for g, k in bib.paare if not all_white.ist_geraet_ohne_licht(g, k)]
    assert len(lampen) > 0.8 * len(bib.paare)


def test_gigbar_im_kurzmodus_geht_beim_notaus_dunkel(bib):
    """Das Geraet aus dem Befund, gerendert: „Show-Auswahl“ steht auf einem
    Automatikprogramm — NOT-AUS zieht alle drei Kanaele auf 0."""
    g, kanaele = next((g, k) for g, k in bib.paare
                      if (g.datei, g.mode_name) == ("chauvet/gigbar-2.json", "3-channel"))
    for k in kanaele:
        k.default_value = 120
    g.universe, g.address = 1, 1
    A.get_channels_for_patched = lambda fx: kanaele      # monkeypatch von bib raeumt auf
    st = _zustand([g])
    st._rebuild_render_plan()
    live = st.universes[1]
    st._render_frame(0.02)
    assert [live.get_channel(a) for a in (1, 2, 3)] == [120, 120, 120]
    st.set_laser_estop(True)
    st._render_frame(0.02)
    assert [live.get_channel(a) for a in (1, 2, 3)] == [0, 0, 0]


# ══════════════════════════════════════════════════════════════════════════════
# C) Der Weg ueber die Geraete-Datenbank
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def profile_in_der_db():
    """Drei Profile in der (Test-)Geraete-Datenbank: ein Kombigeraet mit
    Kurz-Modus, eine Lampe, ein Geraet vom Typ ``laser`` ohne Laserkanal."""
    from sqlalchemy import delete, select
    from sqlalchemy.orm import Session
    from src.core.database.fixture_db import engine
    from src.core.database.models import (
        FixtureChannel, FixtureMode, FixtureProfile, Manufacturer)

    def profil(s, hersteller, name, typ, modi):
        p = FixtureProfile(manufacturer=hersteller, name=name, short_name=name[:20],
                           fixture_type=typ, source="user")
        s.add(p)
        s.flush()
        for modus, kanaele in modi:
            m = FixtureMode(fixture_id=p.id, name=modus, channel_count=len(kanaele))
            s.add(m)
            s.flush()
            for nr, (attribut, kanalname) in enumerate(kanaele, 1):
                s.add(FixtureChannel(mode_id=m.id, channel_number=nr,
                                     name=kanalname, attribute=attribut))
        return p.id

    with Session(engine()) as s:
        h = Manufacturer(name="LAS38 Testwerk", short_name="L38")
        s.add(h)
        s.flush()
        kombi = profil(s, h, "LAS38 Kombi Bar", "other", [
            ("3-channel", [("raw", "LED-Betrieb"), ("raw", "Show-Auswahl"),
                           ("raw", "Auto-Geschwindigkeit")]),
            ("11-channel", [("intensity", "Dimmer"), ("color_r", "Rot"),
                            ("raw", "Laser Strobe")]),
        ])
        lampe = profil(s, h, "LAS38 PAR", "par", [
            ("3ch", [("color_r", "Rot"), ("color_g", "Gruen"), ("color_b", "Blau")]),
            ("4ch", [("intensity", "Dimmer"), ("color_r", "Rot"),
                     ("color_g", "Gruen"), ("color_b", "Blau")]),
        ])
        typlaser = profil(s, h, "LAS38 Scanner", "laser", [
            ("2ch", [("raw", "Modus"), ("raw", "Muster")]),
        ])
        hersteller_id = h.id
        s.commit()
    A.clear_channel_cache()
    try:
        yield types.SimpleNamespace(kombi=kombi, lampe=lampe, typlaser=typlaser)
    finally:
        with Session(engine()) as s:
            ids = [kombi, lampe, typlaser]
            modi = [m for (m,) in s.execute(
                select(FixtureMode.id).where(FixtureMode.fixture_id.in_(ids))).all()]
            if modi:
                s.execute(delete(FixtureChannel).where(FixtureChannel.mode_id.in_(modi)))
            s.execute(delete(FixtureMode).where(FixtureMode.fixture_id.in_(ids)))
            s.execute(delete(FixtureProfile).where(FixtureProfile.id.in_(ids)))
            s.execute(delete(Manufacturer).where(Manufacturer.id == hersteller_id))
            s.commit()
        A.clear_channel_cache()


class _Gepatcht:
    """Ein gepatchtes Geraet, wie die Show-Datenbank es liefert (nur die Felder,
    die Plan und Erkennung lesen)."""
    protocol = ""
    dimmer_curve = "linear"
    fixture_type = "other"
    fixture_name = "Kombi Bar"
    manufacturer_name = "Testwerk"
    spider_dual_tilt = False

    def __init__(self, fid, adresse, profil_id, modus, kanalzahl):
        self.fid, self.universe, self.address = fid, 1, adresse
        self.fixture_profile_id = profil_id
        self.mode_name, self.channel_count = modus, kanalzahl
        self.label = f"Geraet {fid}"


def test_die_abfrage_beantwortet_alle_profile_auf_einmal(profile_in_der_db):
    p = profile_in_der_db
    antwort = A._profile_mit_laserkanal([p.kombi, p.lampe, p.typlaser, 987654321, None])
    assert antwort == {p.kombi: True, p.lampe: False, p.typlaser: True,
                       987654321: False}


def test_die_angemeldete_quelle_ist_die_der_geraete_datenbank(profile_in_der_db):
    p = profile_in_der_db
    assert erkennung._profil_quelle is A._profil_hat_laserkanal
    assert erkennung.profil_traegt_laser(_Gepatcht(1, 1, p.kombi, "3-channel", 3)) is True
    assert erkennung.profil_traegt_laser(_Gepatcht(2, 9, p.lampe, "3ch", 3)) is False


def test_kurzmodus_aus_der_datenbank_ist_im_notaus(profile_in_der_db):
    """Der ganze Weg mit den echten Kanaelen aus der Geraete-Datenbank."""
    p = profile_in_der_db
    kombi = _Gepatcht(1, 1, p.kombi, "3-channel", 3)
    lampe = _Gepatcht(2, 10, p.lampe, "3ch", 3)
    st = _zustand([kombi, lampe])
    st._laser_profile_bestimmen()
    st._rebuild_render_plan()
    assert set(st._laser_fids) == {1}
    assert set(st._laser_estop_addrs.get(1, ())) == {1, 2, 3}
    assert st.laser_anzahl() == 1
    assert 1 not in st._laser_rearm_menge()


def test_einmal_je_laden_und_der_plan_fragt_nicht_mehr(profile_in_der_db, monkeypatch):
    """„Beim Patchen/Laden einmal bestimmen“: EINE Abfrage fuer alle Profile
    zusammen, danach liest der Render-Plan nur noch."""
    p = profile_in_der_db
    geraete = ([_Gepatcht(i, 1 + 3 * (i - 1), p.kombi, "3-channel", 3) for i in range(1, 6)]
               + [_Gepatcht(i, 1 + 3 * (i - 1), p.lampe, "3ch", 3) for i in range(6, 11)])
    aufrufe = []
    echt = A._profile_mit_laserkanal

    def gezaehlt(ids):
        aufrufe.append(sorted(ids))
        return echt(ids)

    monkeypatch.setattr(A, "_profile_mit_laserkanal", gezaehlt)
    st = _zustand(geraete)
    st._laser_profile_bestimmen()
    assert aufrufe == [sorted([p.kombi, p.lampe])]
    st._rebuild_render_plan()
    st._rebuild_render_plan()
    st._laser_profile_bestimmen()
    assert len(aufrufe) == 1, "der Plan darf die Geraete-Datenbank nicht mehr fragen"
    assert set(st._laser_fids) == {1, 2, 3, 4, 5}


def test_plan_ohne_vorheriges_bestimmen_fragt_je_profil_einmal_nach(profile_in_der_db,
                                                                   monkeypatch):
    """Wer den Plan baut, ohne dass vorher bestimmt wurde (Testhelfer, ein
    vergessener Weg), bekommt trotzdem die richtige Antwort."""
    p = profile_in_der_db
    aufrufe = []
    echt = A._profile_mit_laserkanal
    monkeypatch.setattr(A, "_profile_mit_laserkanal",
                        lambda ids: aufrufe.append(list(ids)) or echt(ids))
    st = _zustand([_Gepatcht(i, 1 + 3 * (i - 1), p.kombi, "3-channel", 3)
                   for i in range(1, 4)])
    st._rebuild_render_plan()
    assert set(st._laser_fids) == {1, 2, 3}
    assert aufrufe == [[p.kombi]]


def test_kanal_cache_verwerfen_verwirft_auch_die_profil_antwort(profile_in_der_db):
    p = profile_in_der_db
    assert erkennung.profil_traegt_laser(_Gepatcht(1, 1, p.kombi, "3-channel", 3)) is True
    assert erkennung.profil_bekannt(p.kombi)
    A.clear_channel_cache()
    assert not erkennung.profil_bekannt(p.kombi)


def test_im_editor_ergaenzter_laserkanal_gilt_nach_dem_verwerfen(profile_in_der_db):
    """Ein Profil bekommt nachtraeglich einen Laserkanal in einem anderen Modus
    — nach ``clear_channel_cache`` (das ruft der Editor) zaehlt auch der
    Kurz-Modus als Laser."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from src.core.database.fixture_db import engine
    from src.core.database.models import FixtureChannel, FixtureMode
    p = profile_in_der_db
    g = _Gepatcht(2, 9, p.lampe, "3ch", 3)
    assert erkennung.ist_laser(g, []) is False
    with Session(engine()) as s:
        modus = s.execute(select(FixtureMode).where(
            FixtureMode.fixture_id == p.lampe, FixtureMode.name == "4ch")).scalar_one()
        s.add(FixtureChannel(mode_id=modus.id, channel_number=5,
                             name="Laser Helligkeit", attribute="raw"))
        s.commit()
    assert erkennung.ist_laser(g, []) is False, "die gemerkte Antwort gilt noch"
    A.clear_channel_cache()
    assert erkennung.ist_laser(g, []) is True


def test_gescheiterte_abfrage_laesst_den_patch_nicht_scheitern(profile_in_der_db,
                                                              monkeypatch):
    p = profile_in_der_db

    def kaputt(_ids):
        raise RuntimeError("Datenbank gesperrt")

    monkeypatch.setattr(A, "_profile_mit_laserkanal", kaputt)
    st = _zustand([_Gepatcht(1, 1, p.kombi, "3-channel", 3)])
    st._laser_profile_bestimmen()          # darf nicht werfen
    st._rebuild_render_plan()              # darf nicht werfen
    assert not erkennung.profil_bekannt(p.kombi), "ein Fehler ist keine Antwort"


def test_beide_ladewege_bestimmen_vor_dem_plan():
    """``_reload_patch_cache`` und ``replace_patch`` ohne Show-Datenbank: das
    Bestimmen steht VOR dem Aufbau des Render-Plans."""
    import inspect
    for methode in (AppState._reload_patch_cache, AppState.replace_patch):
        quelle = inspect.getsource(methode)
        assert "_laser_profile_bestimmen()" in quelle, methode.__name__
        assert (quelle.index("_laser_profile_bestimmen()")
                < quelle.index("self._rebuild_render_plan()")), methode.__name__
