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


# ── zweite Sicherung zu LIZ-1: Inhalt einer Lizenzdatei ──────────────────────
#
# Alle Werte hier sind ERFUNDEN (ein Muster aus Buchstaben, kein Schluessel,
# keine echte Lizenz, kein echter Name). In Tests steht nie eine echte Datei.

_ERFUNDENE_SIGNATUR = "QUJD" * 21 + "QUI="            # 88 Zeichen Base64-Form
_ERFUNDENE_LIZENZ = ('{"format": 1, "kennung": "AAAA2222BBBB", "name": "Erika Beispiel", '
                     '"gueltig_bis": null, "ausgestellt_am": "2026-01-01", "hinweis": "", '
                     f'"signatur": "{_ERFUNDENE_SIGNATUR}"' + "}")


def test_ganze_lizenzdatei_in_einer_fehlermeldung_verschwindet():
    text = anonymisiere(f"[lizenz] unlesbar: {_ERFUNDENE_LIZENZ} — bitte neu waehlen")
    assert _ERFUNDENE_SIGNATUR not in text
    assert "Erika Beispiel" not in text, "mit der Signatur geht auch der Name"
    assert "AAAA2222BBBB" not in text
    assert text == "[lizenz] unlesbar: {Lizenzdatei: Inhalt entfernt} — bitte neu waehlen"


def test_mehrzeilige_lizenzdatei_verschwindet():
    mehrzeilig = _ERFUNDENE_LIZENZ.replace(", ", ",\n  ")
    text = anonymisiere("Inhalt:\n" + mehrzeilig + "\nEnde")
    assert _ERFUNDENE_SIGNATUR not in text and "Erika Beispiel" not in text
    assert text == "Inhalt:\n{Lizenzdatei: Inhalt entfernt}\nEnde"


@pytest.mark.parametrize("zeile", [
    f'"signatur": "{_ERFUNDENE_SIGNATUR}"',
    f"signatur={_ERFUNDENE_SIGNATUR}",
    f"Signatur: {_ERFUNDENE_SIGNATUR}",
])
def test_einzelnes_signaturfeld_verliert_seinen_wert(zeile):
    text = anonymisiere(f"vorher {zeile} nachher")
    assert _ERFUNDENE_SIGNATUR not in text
    assert "(entfernt)" in text and text.startswith("vorher ") and text.endswith(" nachher")


def test_das_wort_signatur_allein_bleibt():
    """„Signatur“ steht in Logs auch sonst — die Absturz-Signatur ``Typ@datei``,
    die Signatur-Migration der Geraeteprofile. Nur lange Base64-Werte zaehlen."""
    for text in ("Signatur: ZeroDivisionError@app_state.py:1234",
                 "Signatur-Migration: 3 Profile umbenannt",
                 'signatur = "kurz"',
                 "Lizenz: gueltig (unbefristet, Kennung AAAA…)"):
        assert anonymisiere(text) == text, text


def test_entfernen_ist_wiederholbar():
    einmal = anonymisiere(f"x {_ERFUNDENE_LIZENZ} y signatur={_ERFUNDENE_SIGNATUR}")
    assert anonymisiere(einmal) == einmal


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


# ── Codex-Review #1065 (CDX-59): Trennzeichen IN der Seriennummer ───────────

@pytest.fixture
def gesehen(monkeypatch):
    """Die Liste der gesehenen Nummern gehoert dem Prozess — im Test frisch."""
    monkeypatch.setattr(udmx, "GESEHENE_SERIEN", set())
    return udmx.GESEHENE_SERIEN


def test_doppelpunkt_in_der_nummer_wird_ganz_gekuerzt(gesehen):
    """Ohne dass LightOS die Nummer kennt: ein Doppelpunkt MITTEN in der
    Nummer gehoert dazu, ein abschliessender nicht."""
    text = anonymisiere("U3 uDMX → 16c0:05dc#ABC:DEF123: sendet")
    assert "ABC" not in text and "DEF1" not in text
    assert "16c0:05dc#…F123: sendet" in text
    text = anonymisiere("Anyma uDMX · Seriennr. QQ:RR:SS77 · Bus 1")
    assert "QQ" not in text and "RR" not in text
    assert "Seriennr. …SS77 · Bus 1" in text


def test_leerzeichen_in_einer_gesehenen_nummer(gesehen):
    """Eine Nummer mit Leerzeichen erkennt kein Textmuster — wohl aber die
    Liste der Nummern, die der uDMX-Pfad gelesen hat (Geraet oder Schluessel)."""
    vid, pid, serie, _ = udmx.schluessel_lesen("16c0:05dc#LAB 4711X")
    assert serie == "LAB 4711X" and serie in gesehen
    text = anonymisiere(f"U3 uDMX → 16c0:05dc#{serie}: sendet; "
                        f"Anyma uDMX · Seriennr. {serie} · Bus 1")
    assert "LAB" not in text and "4711" not in text, text
    assert "16c0:05dc#…711X: sendet" in text


def test_vom_geraet_gelesene_nummer_wird_gemerkt(gesehen):
    dev = types.SimpleNamespace(
        idVendor=0x16C0, idProduct=0x05DC, iManufacturer=1, iProduct=1,
        iSerialNumber=1, manufacturer="www.anyma.ch", product="uDMX",
        serial_number=" SN 12:34 ", bus=1, address=2, port_numbers=(1,))
    zeile = udmx._tabellen_zeile(0x16C0, 0x05DC)
    udmx._beschreibe(dev, zeile)
    assert "SN 12:34" in gesehen
    assert "SN 12:34" not in anonymisiere("Seriennr. SN 12:34 · Bus 1")


def test_kurze_oder_harmlose_nummern_werden_nicht_woertlich_ersetzt(gesehen):
    gesehen.update({"A:1", "ABCDEF"})
    # „A:1“ ist zu kurz, „ABCDEF“ hat kein Trennzeichen (das Muster reicht).
    assert anonymisiere("Zeit A:1 und ABCDEF im Text") == "Zeit A:1 und ABCDEF im Text"
