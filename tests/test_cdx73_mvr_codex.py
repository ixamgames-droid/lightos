"""CDX-73: Codex-Ernte zu PR #1292 (MVR-Import/-Export).

1. Die Suche nach einer freien Adresse bleibt in den Universen 1..32, auch
   wenn das Geraet in der Datei auf Universum 100 steht.
2. Der GDTF-Export behaelt die Art (kind) der Wertebereiche: ein Shutter mit
   zu/Strobe/offen kommt nicht als dreimal „offen“ zurueck.
3. Der GDTF-Import behaelt das Fein-Byte des Standardwerts mehrbytiger Kanaele.

Reine Kern-Tests: es wird kein Profil in einer Bibliothek angelegt.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.mvr import gdtf_profil as GP                           # noqa: E402
from src.core.mvr import gdtf_schreiben as GS                        # noqa: E402
from src.core.mvr import importieren as I                            # noqa: E402
from src.core.mvr import lesen as L                                  # noqa: E402


# ── 1. Freie Adresse ─────────────────────────────────────────────────────────

def _voll(ausser=()):
    b = I._Belegung([])
    for u in range(1, I.UNIVERSUM_MAX + 1):
        if u not in ausser:
            b.dazu(u, 1, I.UNIVERSUM_GROESSE, f"voll {u}")
    return b


def test_freie_adresse_nie_ueber_universum_max():
    b = _voll()
    assert b.frei(100, 1) is None
    assert b.frei(I.UNIVERSUM_MAX + 1, 1) is None
    assert b.frei(1, 1) is None


def test_freie_adresse_ab_hohem_universum_findet_luecke_im_bereich():
    b = _voll(ausser=(5,))
    assert b.frei(100, 1) == (5, 1)
    # leere Belegung: nie ein Universum > 32
    u, _a = I._Belegung([]).frei(100, 4)
    assert 1 <= u <= I.UNIVERSUM_MAX


def test_geraet_auf_universum_100_mit_freier_adresse_bei_vollem_patch():
    g = L.MvrGeraet(name="Spot", universum=100, adresse=1, adresse_text="100.1")
    e = I.Eintrag(index=0, geraet=g, kanaele=1, name="Spot")
    I._adressieren(e, _voll(), I.FREIE_ADRESSE)
    assert e.status == I.UEBERSPRUNGEN
    assert e.universum is None or e.universum <= I.UNIVERSUM_MAX


# ── 2. Art der Wertebereiche im GDTF-Export ─────────────────────────────────

def _profil(kanaele):
    m = GS.ProfilModus(name="M", kanalzahl=max(k.nummer for k in kanaele),
                       kanaele=tuple(kanaele))
    return GS.ProfilDaten(hersteller="Test", name="Typ", modi=(m,))


def _rund(p):
    typ = L.lies_gdtf_xml(ET.fromstring(GS.beschreibung_xml(p)), "t.gdtf")
    return GP.modus_payload(typ.modus("M"))


def test_shutter_arten_reisen_mit():
    shutter = GS.ProfilKanal(nummer=1, name="Shutter", attribut="shutter", default=255,
                             bereiche=((0, 9, "zu", "closed"),
                                       (10, 249, "Strobe", "strobe"),
                                       (250, 255, "offen", "open")))
    kanal = _rund(_profil([shutter]))["channels"][0]
    assert [r["kind"] for r in kanal["ranges"]] == ["closed", "strobe", "open"]
    assert [(r["range_from"], r["range_to"]) for r in kanal["ranges"]] == \
        [(0, 9), (10, 249), (250, 255)]


def test_bereich_ohne_art_bleibt_ohne_art():
    k = GS.ProfilKanal(nummer=1, name="Shutter", attribut="shutter",
                       bereiche=((0, 99, "a", ""), (100, 255, "b", "strobe")))
    kinds = [r["kind"] for r in _rund(_profil([k]))["channels"][0]["ranges"]]
    assert kinds == ["", "strobe"]


def test_fremde_gdtf_ohne_marke_nutzt_weiter_das_attribut():
    xml = ("<GDTF><FixtureType Name='X'><DMXModes><DMXMode Name='M'><DMXChannels>"
           "<DMXChannel Offset='1'><LogicalChannel Attribute='Shutter1'>"
           "<ChannelFunction Name='a' Attribute='Shutter1' DMXFrom='0/1'/>"
           "<ChannelFunction Name='b' Attribute='Shutter1Strobe' DMXFrom='10/1'/>"
           "</LogicalChannel></DMXChannel></DMXChannels></DMXMode></DMXModes>"
           "</FixtureType></GDTF>")
    typ = L.lies_gdtf_xml(ET.fromstring(xml), "f.gdtf")
    kinds = [r["kind"] for r in GP.modus_payload(typ.modus("M"))["channels"][0]["ranges"]]
    assert kinds == ["open", "strobe"]


# ── 3. Fein-Byte des Standardwerts ──────────────────────────────────────────

def _gdtf_pan(offset, default):
    return ("<GDTF><FixtureType Name='X'><DMXModes><DMXMode Name='M'><DMXChannels>"
            f"<DMXChannel Offset='{offset}' Default='{default}'>"
            "<LogicalChannel Attribute='Pan'>"
            "<ChannelFunction Name='Pan' Attribute='Pan' DMXFrom='0/1'/>"
            "</LogicalChannel></DMXChannel></DMXChannels></DMXMode></DMXModes>"
            "</FixtureType></GDTF>")


def _defaults(xml):
    typ = L.lies_gdtf_xml(ET.fromstring(xml), "p.gdtf")
    return [c["default_value"] for c in GP.modus_payload(typ.modus("M"))["channels"]]


def test_fein_default_16_bit():
    assert _defaults(_gdtf_pan("1,2", "32895/2")) == [128, 127]


def test_fein_default_bytezahl_weicht_ab():
    # 8-bit-Angabe auf 16-bit-Kanal: fein 0; 24-bit-Angabe auf 16 bit: abgeschnitten
    assert _defaults(_gdtf_pan("1,2", "128/1")) == [128, 0]
    assert _defaults(_gdtf_pan("1,2", f"{(128 << 16) | (127 << 8) | 5}/3")) == [128, 127]
    assert _defaults(_gdtf_pan("1,2,3", f"{(1 << 16) | (2 << 8) | 3}/3")) == [1, 2, 3]
    # zu gross: auf den Hoechstwert begrenzt wie bisher das grobe Byte
    assert _defaults(_gdtf_pan("1,2", "999999/2")) == [255, 255]


def test_fein_default_rundreise_export_import():
    pan = GS.ProfilKanal(nummer=1, name="Pan", attribut="pan", default=128)
    fein = GS.ProfilKanal(nummer=2, name="Pan fein", attribut="pan_fine", default=127)
    chs = _rund(_profil([pan, fein]))["channels"]
    assert [(c["attribute"], c["default_value"]) for c in chs] == \
        [("pan", 128), ("pan_fine", 127)]


def test_grobes_byte_bleibt_bei_mehr_als_vier_bytes():
    # Pruefung CDX-73: mehr als 4 Bytes duerfen das grobe Byte nicht anders
    # liefern als bisher (_dmx_wert); 2**32 auf 5 Bytes ist grob 1, nicht 255.
    for text in ("4294967296/5", f"{(7 << 32) | 0x12345678}/5", "32895/2", "300/1"):
        alt = L._dmx_wert(text)
        assert _defaults(_gdtf_pan("1", text))[0] == alt, text
    assert _defaults(_gdtf_pan("1,2", f"{(7 << 32) | (9 << 24)}/5")) == [7, 9]
