"""LAS-37: EINE Laser-Erkennung fuer alle Sicherheits-Stellen.

Befund (Audit QA-96): auf „ist das ein Laser?“ gab es drei Antworten. NOT-AUS-
Adressen, Zaehler und Aus-Maske nahmen nur Typ ``laser`` oder einen
``laser_*``-Kanal; Blackout und „Alles Weiss“ erkannten zusaetzlich am
Geraetenamen; auf Kanalnamen sah niemand. Am Eurolite „LED KLS Laser Bar FX
Light Set“ der mitgelieferten Bibliothek (Typ ``other``, Kanaele „Laser: Red“
und „Laser: Green“ mit Attribut ``raw``) hiess das: LASER NOT-AUS gedrueckt,
der Laser der Bar leuchtet weiter.

Geprueft wird ueber ALLE Profile und Modi der mitgelieferten Bibliothek, dass
jede Stelle dieselbe Antwort gibt wie ``laser.erkennung.ist_laser``:

* der Render-Plan (NOT-AUS-Adressen ``_laser_estop_addrs``, ``_laser_fids``),
* der Zaehler ``laser_anzahl``,
* die Aus-Maske (``_build_gm_laser_aus_mask``),
* der Blackout (``_blackout_aufteilung``),
* „Alles Weiss“ (``ist_geraet_ohne_licht``).

Es wird nichts gesendet: die Geraete sind Attrappen aus den Profil-Dateien.
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

#: Was NUR ueber einen Namen als Laser gilt — also durch die weite Regel neu
#: dazukommt: fuenf Profile, neun Modi. Aendert sich die Bibliothek, zeigt
#: dieser Test die neue Liste; sie gehoert dann hier eingetragen UND angesehen
#: (Fehlalarm?).
NUR_UEBER_NAMEN = {
    ("cameo/multi-fx-bar.json", "29 Channel"): "kanalname",
    ("cameo/multi-fx-bar.json", "5 Channel"): "kanalname",
    ("cameo/storm.json", "10 Channel"): "kanalname",
    ("chauvet/gigbar-2.json", "11-channel"): "kanalname",
    ("eurolite/led-kls-laser-bar-fx-light-set.json", "3 Channels"): "name",
    ("eurolite/led-kls-laser-bar-fx-light-set.json", "5 Channels"): "name",
    ("eurolite/led-kls-laser-bar-fx-light-set.json", "9 Channels"): "kanalname",
    ("eurolite/led-kls-laser-bar-fx-light-set.json", "27 Channels"): "kanalname",
    ("u-king/mini-double-sided-moving-head.json", "15 Channel"): "kanalname",
}
#: Die Grenze der Regel (steht im Modulkopf von ``erkennung``): Kurz-Modi von
#: Kombigeraeten ohne eigenen Laserkanal. Bewusst festgehalten, nicht geloest.
KURZMODI_OHNE_LASERKANAL = {
    ("cameo/multi-fx-bar.json", "2 Channel"),
    ("chauvet/gigbar-2.json", "3-channel"),
}


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
    fixture_profile_id = 1
    protocol = ""                       # normaler DMX-Ausgang
    dimmer_curve = "linear"

    def __init__(self, fid, universum, adresse, profil, modus, kanaele, datei):
        self.fid = fid
        self.universe = universum
        self.address = adresse
        self.fixture_type = profil.get("typ") or "other"
        self.fixture_name = profil.get("modell") or ""
        self.manufacturer_name = profil.get("hersteller") or ""
        self.label = f"Geraet {fid}"            # neutral: sagt nichts ueber Laser
        self.mode_name = modus
        self.channel_count = len(kanaele)
        self.datei = datei


def _bibliothek():
    """``[(Geraet, [Kanaele])]`` — jedes Profil in jedem Modus einmal gepatcht,
    lueckenlos hintereinander auf so viele Universen wie noetig."""
    aus, fid, universum, adresse = [], 1, 1, 1
    for pfad in sorted(glob.glob(os.path.join(_BIB, "**", "*.json"), recursive=True)):
        with open(pfad, encoding="utf-8") as f:
            profil = json.load(f)
        datei = os.path.relpath(pfad, _BIB).replace("\\", "/")
        for modus in profil.get("modi") or []:
            kanaele = [_Kanal(i, k) for i, k in enumerate(modus.get("kanaele") or [], 1)]
            if not kanaele:
                continue
            if adresse + len(kanaele) - 1 > 512:
                universum, adresse = universum + 1, 1
            aus.append((_Geraet(fid, universum, adresse, profil, modus.get("name") or "",
                                kanaele, datei), kanaele))
            fid += 1
            adresse += len(kanaele)
    return aus


class _FM:
    def tick(self, universes, patch_cache, dt):
        pass


def _zustand(paare):
    """Ein AppState ohne Datenbank und ohne Ausgabe, gepatcht mit ``paare``."""
    st = AppState.__new__(AppState)
    st.universes = {u: Universe(u) for u in sorted({g.universe for g, _ in paare})}
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = _FM()
    st._patch_cache = [g for g, _ in paare]
    st._prog_lock = threading.RLock()
    st.output_manager = types.SimpleNamespace(set_gm_address_mask=lambda m: None)
    st.laser_estop_active = False
    st._laser_estop_addrs = {}
    st._laser_fids = frozenset()
    st.base_levels = {}
    st._engine_extra_prev = {}
    st._suppress_emits = True
    st._rebuild_render_plan()
    return st


@pytest.fixture(scope="module")
def bib():
    paare = _bibliothek()
    assert len(paare) > 400, "die Bibliothek ist unerwartet klein — Pfad pruefen"
    kanaele = {g.fid: k for g, k in paare}
    alt = A.get_channels_for_patched
    A.get_channels_for_patched = lambda fx: kanaele[fx.fid]
    try:
        st = _zustand(paare)        # der Plan haelt die Kanaele danach selbst
    finally:
        A.get_channels_for_patched = alt
    return types.SimpleNamespace(paare=paare, st=st, kanaele=kanaele)


def _adressen(g, kanaele):
    return {g.address + k.channel_number - 1 for k in kanaele}


# ── Die Regel selbst ────────────────────────────────────────────────────────

class _K:
    def __init__(self, attribute="raw", name=""):
        self.attribute, self.name = attribute, name


class _G:
    def __init__(self, typ="other", fixture_name="", label="", manufacturer_name=""):
        self.fixture_type, self.fixture_name = typ, fixture_name
        self.label, self.manufacturer_name = label, manufacturer_name


@pytest.mark.parametrize("geraet, kanaele, grund", [
    (_G("laser"), [], "typ"),
    (_G("LASER "), [], "typ"),
    (_G(), [_K("laser_x")], "kanal"),
    (_G(), [_K("raw", "Laser: Red")], "kanalname"),
    (_G("moving_head"), [_K("intensity", "Dimmer"), _K("raw", "Laser Helligkeit")], "kanalname"),
    (_G(fixture_name="LED KLS Laser Bar FX Light Set"), [], "name"),
    (_G(manufacturer_name="Laserworld"), [], "name"),
    (_G(label="Showlaser links"), [], "name"),
    (_G("par", "LED PAR 64"), [_K("intensity", "Dimmer"), _K("color_r", "Red")], ""),
    (_G("moving_head", "Blazer 200"), [_K("raw", "Phaser")], ""),
])
def test_die_regel(geraet, kanaele, grund):
    assert erkennung.laser_grund(geraet, kanaele) == grund
    assert erkennung.ist_laser(geraet, kanaele) is bool(grund)
    assert erkennung.nur_ueber_namen(geraet, kanaele) is (grund in ("kanalname", "name"))


def test_typ_und_kanal_gehen_vor_namen():
    """Wer Typ oder ``laser_*``-Kanal hat, ist kein „nur ueber Namen“-Fall."""
    g = _G("laser", fixture_name="Laser 3000")
    assert erkennung.laser_grund(g, [_K("raw", "Laser Mode")]) == "typ"
    assert erkennung.hinweis_text(g, []) == ""


def test_hinweis_nennt_das_geraet_und_die_folge():
    g = _G(fixture_name="LED KLS Laser Bar FX Light Set", label="Bar links")
    text = erkennung.hinweis_text(g, [_K("raw", "Laser: Red")])
    assert "Bar links" in text and "NOT-AUS" in text and "Blackout" in text


def test_bedienung_bleibt_die_enge_regel():
    """Ein Moving Head mit Laserdiode zaehlt fuer die Sicherheit als Laser —
    bekommt aber nicht den Laser-Tab."""
    from src.core.laser import capability
    kanaele = [_K("intensity", "Dimmer"), _K("raw", "Laser Helligkeit")]
    g = _G("moving_head", "Mini Double Sided Moving Head")
    alt = A.get_channels_for_patched
    A.get_channels_for_patched = lambda fx: kanaele
    try:
        assert erkennung.ist_laser(g, kanaele) is True
        assert capability.is_laser_fixture(g) is False
    finally:
        A.get_channels_for_patched = alt


# ── Ueber die ganze Bibliothek ──────────────────────────────────────────────

def test_weite_regel_bringt_genau_diese_modi_neu(bib):
    """Was durch Kanal- und Geraetenamen NEU als Laser gilt — und sonst nichts."""
    neu = {(g.datei, g.mode_name): erkennung.laser_grund(g, kanaele)
           for g, kanaele in bib.paare
           if erkennung.laser_grund(g, kanaele) in erkennung.NUR_NAME}
    assert neu == NUR_UEBER_NAMEN


def test_grenze_kurzmodi_ohne_laserkanal_ist_bekannt(bib):
    """Je Profil: gilt ein Modus als Laser und ein anderer nicht? Das sind die
    Kurz-Modi von Kombigeraeten (Laser nur ueber Automatikprogramme)."""
    je = {}
    for g, kanaele in bib.paare:
        je.setdefault(g.datei, []).append((g.mode_name, erkennung.ist_laser(g, kanaele)))
    luecken = {(d, modus) for d, modi in je.items()
               if any(ja for _m, ja in modi) for modus, ja in modi if not ja}
    assert luecken == KURZMODI_OHNE_LASERKANAL


def test_render_plan_notaus_adressen_und_zaehler(bib):
    """NOT-AUS deckt ALLE Adressen jedes erkannten Geraets — und keines sonst."""
    st = bib.st
    erwartet_fids, erwartet = set(), {}
    for g, kanaele in bib.paare:
        if erkennung.ist_laser(g, kanaele):
            erwartet_fids.add(g.fid)
            erwartet.setdefault(g.universe, set()).update(_adressen(g, kanaele))
    assert set(st._laser_fids) == erwartet_fids
    assert {u: set(s) for u, s in st._laser_estop_addrs.items()} == erwartet
    assert st.laser_anzahl() == len(erwartet_fids)


def test_blackout_und_alles_weiss_sehen_jeden_laser(bib):
    abweichung = []
    for g, kanaele in bib.paare:
        if not erkennung.ist_laser(g, kanaele):
            continue
        erhalten, aus = AppState._blackout_aufteilung(g, kanaele)
        if erhalten or aus != _adressen(g, kanaele):
            abweichung.append(f"Blackout erhaelt Adressen: {g.datei} [{g.mode_name}]")
        if not all_white.ist_geraet_ohne_licht(g, kanaele):
            abweichung.append(f"Alles Weiss fasst an: {g.datei} [{g.mode_name}]")
    assert not abweichung, "\n".join(abweichung)


def test_alles_weiss_laesst_lampen_weiter_zu(bib):
    """Die weite Regel darf „Alles Weiss“ nicht leerraeumen: was weder Laser
    noch Nebel & Co. ist, bleibt eine Lampe."""
    lampen = [g for g, k in bib.paare
              if not all_white.ist_geraet_ohne_licht(g, k)]
    assert len(lampen) > 0.8 * len(bib.paare)


def test_aus_maske_nimmt_dieselben_geraete(bib):
    """Die Aus-Maske (GM ~0, NOT-AUS-Aus-Werte) darf nur Adressen erkannter
    Laser tragen — und jeder Laserkanal mit Attribut ``raw`` steht mit 0 drin."""
    st = bib.st
    maske = st._build_gm_laser_aus_mask(st._fix_index)
    laser_adressen, raw_laser = {}, {}
    for g, kanaele in bib.paare:
        if not erkennung.ist_laser(g, kanaele):
            continue
        laser_adressen.setdefault(g.universe, set()).update(_adressen(g, kanaele))
        for k in kanaele:
            if k.attribute == "raw" and erkennung.ist_laserkanal(k):
                raw_laser.setdefault(g.universe, set()).add(g.address + k.channel_number - 1)
    for u, eintraege in maske.items():
        fremd = set(eintraege) - laser_adressen.get(u, set())
        assert not fremd, f"Aus-Maske U{u} traegt Adressen von Nicht-Lasern: {sorted(fremd)[:8]}"
    fehlt = {u: sorted(a - set(maske.get(u, {}))) for u, a in raw_laser.items()
             if a - set(maske.get(u, {}))}
    assert not fehlt, f"raw-Laserkanaele ohne Aus-Wert: {fehlt}"
    assert all(maske[u][a] == 0 for u, adr in raw_laser.items() for a in adr)


# ── Das Geraet aus dem Befund ───────────────────────────────────────────────

def test_kls_laser_bar_geht_beim_notaus_dunkel():
    """Eurolite LED KLS Laser Bar FX Light Set, groesster Modus: NOT-AUS zieht
    die Kanaele „Laser: Red“/„Laser: Green“ auf 0 — vorher blieben sie offen.
    Die Kanaele bekommen hier einen Ruhewert von 200, damit ohne NOT-AUS
    wirklich etwas anliegt."""
    paare = [(g, k) for g, k in _bibliothek()
             if g.datei == "eurolite/led-kls-laser-bar-fx-light-set.json"]
    g, kanaele = max(paare, key=lambda p: len(p[1]))
    g.universe, g.address = 1, 1
    laser = set()
    for k in kanaele:
        if "Laser:" in k.name:
            k.default_value = 200
            laser.add(g.address + k.channel_number - 1)
    assert len(laser) >= 2, [k.name for k in kanaele]
    alt = A.get_channels_for_patched
    A.get_channels_for_patched = lambda fx: kanaele
    try:
        st = _zustand([(g, kanaele)])
        live = st.universes[1]
        st._render_frame(0.02)
        assert all(live.get_channel(a) == 200 for a in laser)      # ohne NOT-AUS an
        assert g.fid in st._laser_fids
        assert laser <= set(st._laser_estop_addrs.get(1, ()))
        st.set_laser_estop(True)
        st._render_frame(0.02)
        assert all(live.get_channel(a) == 0 for a in laser)
    finally:
        A.get_channels_for_patched = alt


# ── NOT-AUS loesen: nur, was wie ein Laser bedient wird ─────────────────────

class _Mini:
    """Geraet fuer die Loese-Regel (Kanaele mit Attribut und Name)."""
    fixture_profile_id = 1
    protocol = ""
    mode_name = "m"

    def __init__(self, fid, adresse, typ, name, kanaele):
        self.fid, self.universe, self.address = fid, 1, adresse
        self.fixture_type, self.fixture_name = typ, name
        self.manufacturer_name, self.label = "", f"Geraet {fid}"
        self.channel_count = len(kanaele)


def _kanal(nr, attribut, name=""):
    k = _Kanal(nr, {"attribut": attribut, "name": name})
    return k


def test_gobo_am_moving_head_mit_laserdiode_loest_den_notaus_nicht():
    """Die weite Regel deckt mehr Geraete mit dem NOT-AUS — sie darf nicht
    zugleich mehr Wege schaffen, ihn zu loesen. Seit LAS-36 loest KEIN Wert den
    NOT-AUS mehr: weder Gobo/Shutter am Moving Head mit Laserdiode noch der
    Muster-Abruf am echten Laser — nur ``laser_notaus_loesen`` (Rueckfrage)."""
    mh_kan = [_kanal(1, "intensity", "Dimmer"), _kanal(2, "gobo_wheel", "Gobo"),
              _kanal(3, "shutter", "Shutter"), _kanal(4, "raw", "Laser Helligkeit")]
    la_kan = [_kanal(1, "laser_bank", "Muster"), _kanal(2, "shutter", "Betriebsart")]
    mh = _Mini(11, 1, "moving_head", "Mini Double Sided Moving Head", mh_kan)
    laser = _Mini(12, 20, "laser", "L2600", la_kan)
    kanaele = {11: mh_kan, 12: la_kan}
    alt = A.get_channels_for_patched
    A.get_channels_for_patched = lambda fx: kanaele[fx.fid]
    try:
        st = _zustand([(mh, mh_kan), (laser, la_kan)])
        assert st._laser_fids == frozenset({11, 12})           # beide gedeckt
        assert not hasattr(st, "_laser_rearm_fids")             # LAS-36: keine Loese-Menge mehr
        st.set_laser_estop(True)
        for attribut in ("gobo_wheel", "shutter", "intensity"):
            st.set_programmer_value(11, attribut, 120)
            assert st.laser_estop_active is True, f"{attribut} am Moving Head hat geloest"
        st._render_frame(0.02)
        assert st.universes[1].get_channel(4) == 0               # Laserdiode bleibt aus
        st.set_programmer_value(12, "laser_bank", 42)            # Muster-Abruf am echten Laser
        assert st.laser_estop_active is True                     # LAS-36: loest auch nicht
        st.laser_notaus_loesen()                                 # der eine Weg
        assert st.laser_estop_active is False
    finally:
        A.get_channels_for_patched = alt


def test_laser_universen_fuer_sperren_je_universum(bib):
    """Vorbereitet fuer die Testsignal-Sperre: dieselbe Erkennung, je Universum."""
    erwartet = {g.universe for g, k in bib.paare if erkennung.ist_laser(g, k)}
    assert bib.st.laser_universen() == frozenset(erwartet)
    assert erwartet and erwartet != {g.universe for g, _ in bib.paare}


# ── Hinweis beim Patchen ────────────────────────────────────────────────────

def test_patchen_meldet_ein_geraet_das_nur_ueber_namen_laser_ist(monkeypatch):
    """Echter Patch-Weg (Show-DB im Testordner): ein Geraet, dessen Kanal
    „Laser: Red“ heisst, loest beim Patchen den Hinweis aus; ein PAR nicht."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from src.core.app_state import get_state
    from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
    from src.core.database.models import FixtureProfile, PatchedFixture
    from src.core.show.show_file import reset_show

    ensure_builtins()
    reset_show()
    st = get_state()
    with Session(fdb_engine()) as s:
        pid = int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == "PARD")).scalars().first())
    echt = A.get_channels_for_patched
    laser_kanaele = [_kanal(1, "intensity", "Dimmer"), _kanal(2, "raw", "Laser: Red")]
    monkeypatch.setattr(
        A, "get_channels_for_patched",
        lambda fx: laser_kanaele if getattr(fx, "fid", None) == 902 else echt(fx))
    meldungen = []

    def hoeren(event, daten=None):
        if event == "hinweis":
            meldungen.append(str(daten))
    st.subscribe(hoeren)
    try:
        for fid, adresse in ((901, 1), (902, 20)):
            st.add_fixture(PatchedFixture(
                fid=fid, label=f"Bar {fid}", fixture_profile_id=pid, mode_name="",
                universe=1, address=adresse, channel_count=4, fixture_type="other"),
                undoable=False)
        assert len(meldungen) == 1, meldungen
        assert "Bar 902" in meldungen[0] and "NOT-AUS" in meldungen[0]
        assert 902 in st._laser_fids and 901 not in st._laser_fids
    finally:
        st.unsubscribe(hoeren)
        monkeypatch.undo()
        reset_show()


# ── Eine Quelle ─────────────────────────────────────────────────────────────

def test_die_sicherheits_stellen_fragen_alle_dieselbe_funktion():
    """Keine zweite, eigene Laser-Regel in den Sicherheits-Pfaden."""
    with open(os.path.join(_REPO, "src", "core", "app_state.py"), encoding="utf-8") as f:
        zustand = f.read()
    assert 'startswith("laser_")' not in zustand, (
        "app_state.py prueft wieder selbst auf laser_*-Kanaele — "
        "laser.erkennung.ist_laser benutzen")
    assert zustand.count("ist_laser(fx, chans)") >= 2        # Render-Plan + Aus-Maske
    with open(os.path.join(_REPO, "src", "core", "all_white.py"), encoding="utf-8") as f:
        weiss = f.read()
    assert "ist_laser(" in weiss and 'startswith("laser_")' not in weiss
