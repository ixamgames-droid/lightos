"""VIZ-56 Teil 3: ein LightOS-Bibliotheksprofil als ``.gdtf`` schreiben.

Robins Vorgabe: die selbst angelegten Profile bleiben, und sie sollen nach
GDTF konvertierbar sein, damit sie im MVR-Export mitreisen. Geschrieben wird
eine MINIMALE, wohlgeformte GDTF (DataVersion 1.1): ein ZIP mit
``description.xml``, ohne 3D-Modelle, Raeder, Physik.

**Attribute** (:data:`GDTF_ATTRIBUT`): jedes LightOS-Attribut bekommt einen
GDTF-Namen. Wo die GDTF-Attributliste ein Gegenstueck hat, wird es genommen
(``intensity`` -> ``Dimmer``, ``color_r`` -> ``ColorAdd_R`` …) — so liest ein
fremdes Programm die Kanaele richtig. Was keins hat (Laser, ``gobo_fx``,
``raw``, ein einzelner Feinkanal ohne Grobkanal), wird ein EIGENES Attribut
``LightOS_<attribut>``. Jedes verwendete Attribut steht in
``AttributeDefinitions`` — damit ist die Datei auch mit eigenen Namen gueltig.
Die Tabelle ist umkehrbar: :func:`.gdtf_profil.lightos_attribut` ergibt beim
Import wieder dasselbe LightOS-Attribut. Einzige Ausnahme sind die Aliase
``dimmer``/``master``: sie sind laut Bibliotheksformat gleichwertig zu
``intensity`` und kommen als ``intensity`` zurueck.

**16 bit:** ``pan_fine``/``tilt_fine`` werden mit dem n-ten ``pan``/``tilt``
desselben Modus zu EINEM GDTF-Kanal mit zwei Offsets (``Offset="1,2"``) — so
beschreibt GDTF Feinkanaele, und der Import macht daraus wieder
``pan``/``pan_fine`` auf denselben Adressen.

**Mehrkopf:** LightOS speichert keine Koepfe, nur die Kanalliste. Kommt ein
Attribut in einem Modus mehrmals vor, liegt das n-te Vorkommen auf der
Geometrie ``Element n`` (ein Kind von ``Base``) — GDTF verlangt eindeutige
Kanalnamen ``Geometrie_Attribut`` je Modus, und genau so beschreiben
Pixel-Bars ihre Koepfe. Weiter (Achsen Yoke/Head, Strahlgeometrie,
GeometryReference) wird nicht modelliert: dafuer fehlen LightOS die Angaben,
und erfundene Physik waere schlimmer als keine. Deshalb bleibt die Geometrie
sonst flach.

**Luecken** (eine Adresse im Modus ohne Kanal) werden als ``LightOS_raw``
gefuellt, damit die Kanalzahl beim Lesen stimmt.

Die Ausgabe ist deterministisch: gleiches Profil -> byte-gleiche Datei
(FixtureTypeID ist eine UUID5 aus Hersteller und Modell, ZIP-Zeitstempel
fest).
"""
from __future__ import annotations

import io
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from xml.sax.saxutils import quoteattr


#: Namensraum fuer alle deterministischen UUIDs des Exports (fest, nie aendern).
NAMENSRAUM = uuid.UUID("6f1c2d6e-5a8b-4e43-9d2a-56c0a7e1b356")
#: Fester Zeitstempel aller ZIP-Eintraege (fruehester, den ZIP kennt).
ZIP_ZEIT = (1980, 1, 1, 0, 0, 0)

#: LightOS-Attribut -> (GDTF-Attribut, FeatureGroup, Feature).
GDTF_ATTRIBUT: dict[str, tuple[str, str, str]] = {
    "intensity": ("Dimmer", "Dimmer", "Dimmer"),
    "dimmer": ("Dimmer", "Dimmer", "Dimmer"),
    "master": ("Dimmer", "Dimmer", "Dimmer"),
    "shutter": ("Shutter1", "Beam", "Beam"),
    "strobe": ("Shutter1Strobe", "Beam", "Beam"),
    "duration": ("StrobeDuration", "Beam", "Beam"),
    "color_r": ("ColorAdd_R", "Color", "RGB"),
    "color_g": ("ColorAdd_G", "Color", "RGB"),
    "color_b": ("ColorAdd_B", "Color", "RGB"),
    "color_w": ("ColorAdd_W", "Color", "RGB"),
    "color_a": ("ColorAdd_A", "Color", "RGB"),
    "color_uv": ("ColorAdd_UV", "Color", "RGB"),
    "cmy_c": ("ColorSub_C", "Color", "RGB"),
    "cmy_m": ("ColorSub_M", "Color", "RGB"),
    "cmy_y": ("ColorSub_Y", "Color", "RGB"),
    "color_wheel": ("Color1", "Color", "Color"),
    "pan": ("Pan", "Position", "PanTilt"),
    "tilt": ("Tilt", "Position", "PanTilt"),
    "zoom": ("Zoom", "Focus", "Focus"),
    "focus": ("Focus1", "Focus", "Focus"),
    "frost": ("Frost1", "Beam", "Beam"),
    "iris": ("Iris", "Beam", "Beam"),
    "prism": ("Prism1", "Beam", "Beam"),
    "prism_rotation": ("Prism1Pos", "Beam", "Beam"),
    "gobo_wheel": ("Gobo1", "Gobo", "Gobo"),
    "gobo_wheel2": ("Gobo2", "Gobo", "Gobo"),
    "gobo_rotation": ("Gobo1Pos", "Gobo", "Gobo"),
    "animation": ("AnimationWheel1", "Gobo", "Gobo"),
    "speed": ("PanTiltSpeed", "Control", "Control"),
    "effect_speed": ("Effects1Rate", "Control", "Control"),
    "effect": ("Effects1", "Control", "Control"),
    "macro": ("Control1", "Control", "Control"),
    "fan": ("Fan", "Control", "Control"),
    "reset": ("DeviceReset", "Control", "Control"),
    "lamp": ("LampControl", "Control", "Control"),
}

#: Aliase, die beim Import als ``intensity`` zurueckkommen (gleichwertig).
ALIASE = {"dimmer": "intensity", "master": "intensity"}


def gdtf_attribut(lightos_attribut: str) -> tuple[str, str, str]:
    """``"color_r"`` -> ``("ColorAdd_R", "Color", "RGB")``; ohne Gegenstueck
    ``("LightOS_<attribut>", "Control", "Control")``."""
    a = (lightos_attribut or "raw").strip().lower() or "raw"
    if a in GDTF_ATTRIBUT:
        return GDTF_ATTRIBUT[a]
    sauber = re.sub(r"[^a-z0-9_]", "_", a)
    # "LightOS_" == EIGENES_PRAEFIX ohne Gross/Klein (der Import vergleicht so).
    return ("LightOS_" + sauber, "Control", "Control")



# ── Profil als reine Daten ───────────────────────────────────────────────────

@dataclass(frozen=True)
class ProfilKanal:
    nummer: int
    name: str
    attribut: str
    default: int = 0
    #: ``(von, bis, name, art)`` je Wertebereich, DMX 0..255.
    bereiche: tuple[tuple[int, int, str, str], ...] = ()


@dataclass(frozen=True)
class ProfilModus:
    name: str
    kanalzahl: int
    kanaele: tuple[ProfilKanal, ...] = ()


@dataclass(frozen=True)
class ProfilDaten:
    hersteller: str
    name: str
    kurzname: str = ""
    typ: str = "other"
    modi: tuple[ProfilModus, ...] = field(default_factory=tuple)
    id: int | None = None


def profil_aus_db(profil_id: int, engine=None) -> ProfilDaten | None:
    """Ein Bibliotheksprofil samt Modi, Kanaelen und Bereichen lesen."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session, selectinload

    from src.core.database import fixture_db as fdb
    from src.core.database.models import FixtureChannel, FixtureMode, FixtureProfile

    eng = engine if engine is not None else fdb.engine()
    with Session(eng) as s:
        p = s.execute(
            select(FixtureProfile)
            .options(selectinload(FixtureProfile.manufacturer),
                     selectinload(FixtureProfile.modes)
                     .selectinload(FixtureMode.channels)
                     .selectinload(FixtureChannel.ranges))
            .where(FixtureProfile.id == profil_id)).scalar_one_or_none()
        if p is None:
            return None
        modi = []
        for m in sorted(p.modes, key=lambda m: m.id):
            kanaele = tuple(
                ProfilKanal(
                    nummer=int(c.channel_number), name=c.name or "",
                    attribut=(c.attribute or "raw"),
                    default=int(c.default_value or 0),
                    bereiche=tuple((int(r.range_from), int(r.range_to),
                                    r.name or "", r.kind or "")
                                   for r in sorted(c.ranges,
                                                   key=lambda r: (r.range_from, r.id))))
                for c in sorted(m.channels, key=lambda c: (c.channel_number, c.id)))
            modi.append(ProfilModus(name=m.name or "Modus",
                                    kanalzahl=int(m.channel_count or 0),
                                    kanaele=kanaele))
        return ProfilDaten(hersteller=(p.manufacturer.name if p.manufacturer else "") or "",
                           name=p.name or "", kurzname=p.short_name or "",
                           typ=p.fixture_type or "other", modi=tuple(modi), id=p.id)


def ersatz_profil(hersteller: str, name: str, modus: str, kanalzahl: int) -> ProfilDaten:
    """Profil, wenn das Bibliotheksprofil eines gepatchten Geraets fehlt:
    nur die Kanalzahl ist bekannt, alle Kanaele ``raw``."""
    return ProfilDaten(hersteller=hersteller or "Unbekannt", name=name or "Gerät",
                       modi=(ProfilModus(name=modus or "Modus",
                                         kanalzahl=max(1, int(kanalzahl or 1))),))


def fixture_type_id(p: ProfilDaten) -> str:
    """Deterministische FixtureTypeID (UUID5 aus Hersteller + Modell)."""
    return str(uuid.uuid5(NAMENSRAUM, f"profil:{p.hersteller}|{p.name}")).upper()


def dateiname(p: ProfilDaten) -> str:
    """``Hersteller@Modell.gdtf`` (die uebliche Schreibweise), nur sichere
    Zeichen."""
    def sauber(t):
        t = re.sub(r"[^\w .\-]", "_", t or "", flags=re.UNICODE).strip(" .")
        return t or "Unbekannt"
    return f"{sauber(p.hersteller)}@{sauber(p.name)}.gdtf"


# ── description.xml ──────────────────────────────────────────────────────────

@dataclass
class _GKanal:
    offsets: list[int]
    attribut: str          # LightOS
    gdtf: str
    geometrie: str
    quelle: ProfilKanal | None
    default16: int | None = None


def _gdtf_kanaele(m: ProfilModus) -> list[_GKanal]:
    """Die Kanaele eines Modus als GDTF-Kanaele (Feinkanaele zusammengelegt,
    Mehrfach-Vorkommen auf ``Element n``, Luecken aufgefuellt)."""
    kanalzahl = max([m.kanalzahl] + [k.nummer for k in m.kanaele if 1 <= k.nummer <= 512])
    kanalzahl = min(kanalzahl, 512)
    gesehen: set[int] = set()
    kanaele: list[ProfilKanal] = []
    for k in m.kanaele:
        if 1 <= k.nummer <= kanalzahl and k.nummer not in gesehen:
            gesehen.add(k.nummer)
            kanaele.append(k)
    for nr in range(1, kanalzahl + 1):
        if nr not in gesehen:
            kanaele.append(ProfilKanal(nummer=nr, name=f"Kanal {nr}", attribut="raw"))
    kanaele.sort(key=lambda k: k.nummer)

    def attr(k):
        return (k.attribut or "raw").strip().lower() or "raw"

    # Feinkanaele dem n-ten Grobkanal zuordnen.
    fein_zu: dict[int, ProfilKanal] = {}
    for grob, fein in (("pan", "pan_fine"), ("tilt", "tilt_fine")):
        grobe = [k for k in kanaele if attr(k) == grob]
        feine = [k for k in kanaele if attr(k) == fein]
        for g, f in zip(grobe, feine):
            fein_zu[g.nummer] = f
    verbraucht = {f.nummer for f in fein_zu.values()}

    zaehler: dict[str, int] = {}
    aus = []
    for k in kanaele:
        if k.nummer in verbraucht:
            continue
        a = attr(k)
        g = gdtf_attribut(a)[0]
        n = zaehler[g] = zaehler.get(g, 0) + 1
        geo = "Base" if n == 1 else f"Element {n}"
        gk = _GKanal(offsets=[k.nummer], attribut=a, gdtf=g, geometrie=geo, quelle=k)
        f = fein_zu.get(k.nummer)
        if f is not None:
            gk.offsets.append(f.nummer)
            gk.default16 = (max(0, min(255, k.default)) << 8) | max(0, min(255, f.default))
        aus.append(gk)
    return aus


def _wert(v: int) -> str:
    return f"{max(0, min(255, int(v)))}/1"


def _funktionen(gk: _GKanal) -> list[tuple[str, int, int, str]]:
    """``(Name, DMXFrom, Default, art)`` je ChannelFunction. Ohne Bereiche
    EINE Funktion ueber den ganzen Kanal."""
    k = gk.quelle
    default = k.default if k else 0
    name = (k.name if k else "") or gk.gdtf
    bereiche = sorted({(max(0, min(255, b[0])), b[2], b[3]) for b in (k.bereiche if k else ())},
                      key=lambda b: b[0])
    if len(bereiche) < 2:
        return [(name, 0, default, "")]
    aus = []
    if bereiche[0][0] > 0:
        aus.append((name, 0, default, ""))
    letzter = -1
    for von, bname, art in bereiche:
        if von == letzter:
            continue          # zwei Bereiche ab demselben Wert: der erste gilt
        letzter = von
        aus.append((bname or f"{name} {von}", von, default, art))
    # Funktionsnamen je Kanal eindeutig.
    namen: dict[str, int] = {}
    eindeutig = []
    for n, von, d, art in aus:
        z = namen[n] = namen.get(n, 0) + 1
        eindeutig.append((n if z == 1 else f"{n} ({z})", von, d, art))
    return eindeutig


def _a(name: str, wert) -> str:
    return f" {name}={quoteattr(str(wert))}"


def beschreibung_xml(p: ProfilDaten) -> bytes:
    """Die ``description.xml`` eines Profils (UTF-8, deterministisch)."""
    modi = [(m, _gdtf_kanaele(m)) for m in p.modi]
    # Benutzte Attribute (Reihenfolge des ersten Auftretens) und Geometrien.
    attribute: dict[str, tuple[str, str]] = {}
    elemente = 1
    for _m, kk in modi:
        for gk in kk:
            g, grp, feat = gdtf_attribut(gk.attribut)
            attribute.setdefault(g, (grp, feat))
            if gk.geometrie.startswith("Element "):
                elemente = max(elemente, int(gk.geometrie.split()[1]))
    gruppen: dict[str, list[str]] = {}
    for grp, feat in attribute.values():
        if feat not in gruppen.setdefault(grp, []):
            gruppen[grp].append(feat)

    z = ['<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
         '<GDTF DataVersion="1.1">',
         "<FixtureType" + _a("Name", p.name) + _a("ShortName", p.kurzname or p.name)
         + _a("LongName", p.name) + _a("Manufacturer", p.hersteller)
         + _a("Description", "Aus LightOS exportiert (VIZ-56).")
         + _a("FixtureTypeID", fixture_type_id(p)) + _a("Thumbnail", "")
         + _a("RefFT", "") + ">",
         "<AttributeDefinitions>", "<ActivationGroups/>", "<FeatureGroups>"]
    for grp, feats in gruppen.items():
        z.append("<FeatureGroup" + _a("Name", grp) + _a("Pretty", grp) + ">")
        z += ["<Feature" + _a("Name", f) + "/>" for f in feats]
        z.append("</FeatureGroup>")
    z += ["</FeatureGroups>", "<Attributes>"]
    for g, (grp, feat) in attribute.items():
        z.append("<Attribute" + _a("Name", g) + _a("Pretty", g)
                 + _a("Feature", f"{grp}.{feat}") + _a("PhysicalUnit", "None") + "/>")
    z += ["</Attributes>", "</AttributeDefinitions>",
          "<Wheels/>", "<PhysicalDescriptions/>", "<Models/>", "<Geometries>",
          '<Geometry Name="Base" Position="{1,0,0,0}{0,1,0,0}{0,0,1,0}{0,0,0,1}">']
    for n in range(2, elemente + 1):
        z.append("<Geometry" + _a("Name", f"Element {n}")
                 + ' Position="{1,0,0,0}{0,1,0,0}{0,0,1,0}{0,0,0,1}"/>')
    z += ["</Geometry>", "</Geometries>", "<DMXModes>"]
    for m, kk in modi:
        z.append("<DMXMode" + _a("Name", m.name) + _a("Geometry", "Base") + ">")
        z.append("<DMXChannels>")
        for gk in kk:
            funktionen = _funktionen(gk)
            kanalname = f"{gk.geometrie}_{gk.gdtf}"
            erste = f"{kanalname}.{gk.gdtf}.{funktionen[0][0]}"
            z.append("<DMXChannel" + _a("DMXBreak", 1)
                     + _a("Offset", ",".join(str(o) for o in gk.offsets))
                     + _a("InitialFunction", erste) + _a("Highlight", "None")
                     + _a("Geometry", gk.geometrie) + ">")
            z.append("<LogicalChannel" + _a("Attribute", gk.gdtf) + _a("Snap", "No")
                     + _a("Master", "None") + _a("MibFade", "0")
                     + _a("DMXChangeTimeLimit", "0") + ">")
            for i, (fname, von, default, _art) in enumerate(funktionen):
                if gk.default16 is not None:
                    dmx_von, dmx_def = f"{von << 8}/2", f"{gk.default16}/2"
                else:
                    dmx_von, dmx_def = _wert(von), _wert(default)
                z.append("<ChannelFunction" + _a("Name", fname) + _a("Attribute", gk.gdtf)
                         + _a("OriginalAttribute", "") + _a("DMXFrom", dmx_von)
                         + _a("Default", dmx_def) + _a("PhysicalFrom", "0")
                         + _a("PhysicalTo", "1") + _a("RealFade", "0") + "/>")
            z.append("</LogicalChannel>")
            z.append("</DMXChannel>")
        z += ["</DMXChannels>", "<Relations/>", "<FTMacros/>", "</DMXMode>"]
    z += ["</DMXModes>", "<Revisions>",
          '<Revision Text="Aus LightOS exportiert" Date="" UserID="0"/>',
          "</Revisions>", "<FTPresets/>", "<Protocols/>",
          "</FixtureType>", "</GDTF>"]
    return ("\n".join(z) + "\n").encode("utf-8")


# ── ZIP ──────────────────────────────────────────────────────────────────────

def zip_bytes(eintraege: list[tuple[str, bytes]]) -> bytes:
    """Ein ZIP mit festen Zeitstempeln und Rechten — gleiche Eingabe,
    gleiche Bytes."""
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        for name, daten in eintraege:
            info = zipfile.ZipInfo(name, date_time=ZIP_ZEIT)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 3
            z.writestr(info, daten)
    return puffer.getvalue()


def gdtf_bytes(p: ProfilDaten) -> bytes:
    """Die ``.gdtf``-Datei eines Profils als Bytes."""
    return zip_bytes([("description.xml", beschreibung_xml(p))])


def schreibe_gdtf(p: ProfilDaten, pfad: str) -> None:
    """Ein Profil als ``.gdtf`` auf die Platte (atomar ueber eine
    Zwischendatei)."""
    from .schreiben import atomar_schreiben
    atomar_schreiben(pfad, gdtf_bytes(p))
