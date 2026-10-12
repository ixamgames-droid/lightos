"""OUT-77: die Seriennummer eines uDMX-Adapters steht nicht im Klartext im
Diagnosepaket.

**Der Befund (Bedientest QA-96, Sitzung A).** Der Schluessel eines
uDMX-Adapters traegt seine Seriennummer (``16c0:05dc#Seriennummer``, OUT-68).
Das Diagnosepaket schrieb ihn unveraendert hinein: in die Zeilen „Ausgabe“ und
„uDMX (USB)“ der Systeminfo und mit jeder Log-Zeile des Senders. Eine
Seriennummer gehoert zu genau einem Geraet — das Paket ist dafuer gemacht,
weitergegeben zu werden.

Alle Texte des Pakets laufen durch ``diagnose_log.anonymisiere``; dort wird
gekuerzt. Die Nummern in diesem Test sind erfunden.
"""
from __future__ import annotations

import sys
import types
import zipfile

import pytest

from src.core import diagnose_log
from src.core.diagnose_log import anonymisiere, kuerze_seriennummer
from src.core.dmx import udmx

SERIE = "A6008isP"
SCHLUESSEL = f"16c0:05dc#{SERIE}"


# ── die Kuerzung ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("serie,gekuerzt", [
    ("A6008isP", "…8isP"),          # hoechstens die letzten vier
    ("0123456789ABCDEF", "…CDEF"),
    ("SN001", "…01"),               # nie mehr als die Haelfte
    ("AB12", "…12"),
    ("XY", "…Y"),
    ("7", "…"),
    ("", ""),
])
def test_kuerze_seriennummer(serie, gekuerzt):
    assert kuerze_seriennummer(serie) == gekuerzt


def test_schon_gekuerzt_bleibt():
    """Die Systeminfo laeuft zeilenweise UND als Ganzes durch die Kuerzung."""
    einmal = anonymisiere(f"Adapter {SCHLUESSEL}: kein Befund")
    assert anonymisiere(einmal) == einmal
    assert kuerze_seriennummer("…8isP") == "…8isP"


# ── im Text ──────────────────────────────────────────────────────────────────

def test_schluessel_mit_seriennummer_wird_gekuerzt():
    text = anonymisiere(f"U3 uDMX → {SCHLUESSEL}: sendet")
    assert SERIE not in text
    assert "16c0:05dc#…8isP" in text, "Kennung und Ende bleiben lesbar"


def test_auch_in_klammern_und_mehrfach():
    text = anonymisiere(
        f"U3 Adapter {SCHLUESSEL}: uDMX-Adapter ({SCHLUESSEL}) nicht gefunden — "
        f"eingesteckt? U4 Adapter 2008:1066#ZZ99887766: kein Befund")
    assert SERIE not in text and "ZZ99887766" not in text
    assert text.count("16c0:05dc#…8isP") == 2
    assert "(16c0:05dc#…8isP) nicht gefunden" in text
    assert "2008:1066#…7766: kein Befund" in text


def test_log_zeile_des_senders():
    zeile = (f"[Udmx] {SCHLUESSEL}: Ausgabe gestoppt — "
             f"{udmx.grund_text(udmx.G_NICHT_DA, SCHLUESSEL)} Neuer Versuch alle 2s.")
    text = anonymisiere(zeile)
    assert SERIE not in text
    assert text.startswith("[Udmx] 16c0:05dc#…8isP: Ausgabe gestoppt")


def test_beschriftung_der_adapter_liste():
    g = udmx.UdmxGeraet(vid=0x16C0, pid=0x05DC, name="Anyma uDMX", seriennummer=SERIE)
    text = anonymisiere(g.beschriftung())
    assert SERIE not in text
    assert "Seriennr. …8isP" in text


def test_was_keine_seriennummer_ist_bleibt():
    for text in ("U4 uDMX → 2008:1066@1-2: sendet",           # Schluessel mit Anschluss
                 "U4 uDMX → 2008:1066: sendet",               # nur die Kennung
                 "Enttec → COM3: sendet",
                 "Art-Net → 2.0.0.1: sendet",
                 "Zeit 12:34:56#3 und Farbe #ff8800",
                 "PR #1054 und Kanal 16c0"):
        assert anonymisiere(text) == text, text


def test_pfade_werden_weiter_anonymisiert():
    text = anonymisiere(r"D:\\Profile\\Testerin\\AppData und 16c0:05dc#A6008isP",
                        home=r"D:\\Profile\\Testerin", user="Testerin")
    assert "Testerin" not in text and SERIE not in text
    assert "~" in text and "#…8isP" in text


def test_das_paket_sagt_dass_gekuerzt_wird():
    """Der Dialog „Diagnosepaket erstellen“ und LIESMICH.txt zeigen diesen Text."""
    assert "Seriennummern von USB-Adaptern werden gekuerzt" in diagnose_log.PAKET_INHALT


# ── im Paket ─────────────────────────────────────────────────────────────────

@pytest.fixture
def zustand(monkeypatch):
    dev = types.SimpleNamespace(
        port=SCHLUESSEL,
        grund_text=lambda: udmx.grund_text(udmx.G_NICHT_DA, SCHLUESSEL))
    om = types.SimpleNamespace(
        _udmx_outputs={3: dev},
        ausgabe_status=lambda: [{"universum": 3, "weg": "uDMX", "ziel": SCHLUESSEL,
                                 "verbunden": False,
                                 "problem": udmx.grund_kurz(udmx.G_NICHT_DA)}])
    state = types.SimpleNamespace(output_manager=om)
    monkeypatch.setitem(sys.modules, "src.core.app_state",
                        types.SimpleNamespace(_state=state))
    return state


def test_die_quellen_nennen_die_nummer_noch(zustand):
    """Vorbedingung: ohne die Kuerzung stuende sie im Paket."""
    assert any(SERIE in z for z in diagnose_log.udmx_infos())
    assert any(SERIE in z for z in diagnose_log.dmx_infos())


def test_systeminfo_nennt_sie_nicht(zustand):
    text = diagnose_log.systeminfo_text("test", ".")
    assert SERIE not in text
    assert "16c0:05dc#…8isP" in text, "der Adapter bleibt im Paket erkennbar"


def test_das_gepackte_paket_nennt_sie_nirgends(zustand, tmp_path, monkeypatch):
    log = tmp_path / "lightos.log"
    log.write_text(f"[Udmx] {SCHLUESSEL}: Ausgabe gestoppt\n", encoding="utf-8")
    ziel = diagnose_log.erstelle_diagnosepaket(str(tmp_path / "paket.zip"),
                                               app_version="test", programm_dir=".")
    with zipfile.ZipFile(ziel) as zf:
        for name in zf.namelist():
            inhalt = zf.read(name).decode("utf-8", errors="replace")
            assert SERIE not in inhalt, name
