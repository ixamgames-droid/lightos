"""VIZ-56: eine ``.mvr`` lesen — Geraete, Lagen, Adressen, eingebettete GDTF.

Eine ``.mvr`` ist ein ZIP mit ``GeneralSceneDescription.xml`` (welches Geraet
steht WO) und den Geraetetypen als ``.gdtf`` (wieder ein ZIP, darin
``description.xml``). Gelesen wird ueber :mod:`.sicher` — nichts wird
entpackt, DTD/Entities werden abgelehnt.

Was nicht verstanden wird, wird uebersprungen (MVR kennt viel mehr als
LightOS braucht: Klassen, Video, Projektoren, Hilfsdaten). Kaputtes macht nie
den ganzen Import kaputt, wenn es sich auf ein Geraet beschraenkt: ein
unlesbares GDTF heisst „Geraet ohne Typ“, eine unlesbare Adresse heisst
„ohne Adresse“ — beides steht als Hinweis am Geraet. Nur eine Datei, die
gar nicht lesbar ist, ergibt :class:`~.sicher.MvrFehler`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import sicher as S
from .achsen import EINHEIT, MvrMatrix, lies_matrix, verkette
from .sicher import MvrFehler

SZENE = "GeneralSceneDescription.xml"
GDTF_BESCHREIBUNG = "description.xml"
UNIVERSUM_GROESSE = 512


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GdtfFunktion:
    """Ein Bereich eines Kanals (GDTF ``ChannelFunction``), DMX 0..255."""
    von: int
    name: str
    attribut: str


@dataclass(frozen=True)
class GdtfKanal:
    #: DMX-Offsets in diesem Modus (1-basiert), grob zuerst: ``(1, 2)`` =
    #: 16 bit auf Kanal 1 und 2.
    offsets: tuple[int, ...]
    #: GDTF-Attribut des ersten logischen Kanals (``Dimmer``, ``Pan``, …).
    attribut: str
    geometrie: str = ""
    name: str = ""
    default: int = 0
    funktionen: tuple[GdtfFunktion, ...] = ()


@dataclass(frozen=True)
class GdtfModus:
    name: str
    kanaele: tuple[GdtfKanal, ...] = ()

    @property
    def kanalzahl(self) -> int:
        return max((o for k in self.kanaele for o in k.offsets), default=0)


@dataclass(frozen=True)
class GdtfTyp:
    datei: str
    hersteller: str = ""
    name: str = ""
    langname: str = ""
    modi: tuple[GdtfModus, ...] = ()

    @property
    def anzeige(self) -> str:
        return f"{self.hersteller} {self.name}".strip() or self.datei

    def modus(self, name: str) -> GdtfModus | None:
        """Modus ``name`` — exakt, sonst ohne Gross/Klein/Leerzeichen; ohne
        Angabe nur, wenn es genau einen gibt."""
        if not name:
            return self.modi[0] if len(self.modi) == 1 else None
        for m in self.modi:
            if m.name == name:
                return m
        lose = [m for m in self.modi if _vergleich(m.name) == _vergleich(name)]
        return lose[0] if len(lose) == 1 else None


@dataclass(frozen=True)
class MvrGeraet:
    name: str
    uuid: str = ""
    #: Weltlage (alle Layer/Gruppen darueber eingerechnet).
    matrix: MvrMatrix = EINHEIT
    gdtf_datei: str = ""
    gdtf_modus: str = ""
    universum: int | None = None
    adresse: int | None = None
    #: Wie die Adresse in der Datei stand (fuer Vorschau und Meldungen).
    adresse_text: str = ""
    fixture_id: str = ""
    unit_number: str = ""
    #: Namen der Layer/Gruppen von aussen nach innen.
    pfad: tuple[str, ...] = ()
    hinweise: tuple[str, ...] = ()

    @property
    def hat_adresse(self) -> bool:
        return self.universum is not None and self.adresse is not None


@dataclass
class MvrDatei:
    geraete: list[MvrGeraet] = field(default_factory=list)
    #: GDTF-Dateiname (wie im Archiv) -> Typ; fehlt der Name, war die Datei
    #: nicht lesbar (Grund in :attr:`gdtf_fehler`).
    typen: dict[str, GdtfTyp] = field(default_factory=dict)
    gdtf_fehler: dict[str, str] = field(default_factory=dict)
    traversen: int = 0
    fokuspunkte: int = 0
    andere_objekte: int = 0
    hinweise: list[str] = field(default_factory=list)

    def typ_fuer(self, g: MvrGeraet) -> GdtfTyp | None:
        return self.typen.get(g.gdtf_datei) if g.gdtf_datei else None


# ── Hilfen ───────────────────────────────────────────────────────────────────

def _vergleich(text: str) -> str:
    return "".join((text or "").split()).casefold()


def _tag(el) -> str:
    t = el.tag if isinstance(el.tag, str) else ""
    return t.rsplit("}", 1)[-1]


def _kind(el, tag: str):
    for k in el:
        if _tag(k) == tag:
            return k
    return None


def _kind_text(el, tag: str) -> str:
    k = _kind(el, tag)
    return (k.text or "").strip() if k is not None else ""


def lies_adresse(text: str) -> tuple[int, int] | None:
    """``"2.17"`` (Universum.Adresse) oder ``"529"`` (absolut, 1-basiert)
    -> ``(universum, adresse)``. ``None`` bei unlesbarem Text."""
    t = (text or "").strip()
    try:
        if "." in t:
            u_text, a_text = t.split(".", 1)
            u, a = int(u_text), int(a_text)
        else:
            absolut = int(t)
            if absolut < 1:
                return None
            u, a = (absolut - 1) // UNIVERSUM_GROESSE + 1, (absolut - 1) % UNIVERSUM_GROESSE + 1
    except ValueError:
        return None
    if u < 1 or not 1 <= a <= UNIVERSUM_GROESSE:
        return None
    return u, a


def _dmx_wert(text: str, standard: int = 0) -> int:
    """GDTF-DMX-Wert ``"128/1"`` bzw. ``"32768/2"`` -> 0..255 (grob)."""
    t = (text or "").strip()
    if not t or t.lower() == "none":
        return standard
    try:
        if "/" in t:
            w, n = t.split("/", 1)
            wert, bytes_ = int(w), max(1, int(n))
            wert >>= 8 * (bytes_ - 1)
        else:
            wert = int(t)
    except ValueError:
        return standard
    return max(0, min(255, wert))


# ── GDTF ─────────────────────────────────────────────────────────────────────

def lies_gdtf_xml(wurzel, datei: str) -> GdtfTyp:
    ft = wurzel if _tag(wurzel) == "FixtureType" else _kind(wurzel, "FixtureType")
    if ft is None:
        raise MvrFehler(f"„{datei}“ enthält keinen Gerätetyp (FixtureType).")
    modi = []
    dm = _kind(ft, "DMXModes")
    for mode in (list(dm) if dm is not None else []):
        if _tag(mode) != "DMXMode":
            continue
        kanaele = []
        dc = _kind(mode, "DMXChannels")
        for ch in (list(dc) if dc is not None else []):
            if _tag(ch) != "DMXChannel":
                continue
            k = _lies_kanal(ch)
            if k is not None:
                kanaele.append(k)
        kanaele.sort(key=lambda k: k.offsets[0])
        modi.append(GdtfModus(name=(mode.get("Name") or "").strip() or "Modus",
                              kanaele=tuple(kanaele)))
    return GdtfTyp(datei=datei,
                   hersteller=(ft.get("Manufacturer") or "").strip(),
                   name=(ft.get("Name") or "").strip(),
                   langname=(ft.get("LongName") or "").strip(),
                   modi=tuple(modi))


def _lies_kanal(ch) -> GdtfKanal | None:
    offset_text = (ch.get("Offset") or "").strip()
    if not offset_text or offset_text.lower() == "none":
        return None          # virtueller Kanal ohne DMX
    bruch = (ch.get("DMXBreak") or "1").strip()
    if bruch not in ("1", ""):
        return None          # zweiter DMX-Anschluss: gehoert nicht zum Fussabdruck
    try:
        offsets = tuple(int(x) for x in offset_text.replace(" ", "").split(",") if x)
    except ValueError:
        return None
    if not offsets or any(o < 1 or o > UNIVERSUM_GROESSE for o in offsets):
        return None
    attribut, funktionen = "", []
    for lc in ch:
        if _tag(lc) != "LogicalChannel":
            continue
        attribut = attribut or (lc.get("Attribute") or "").strip()
        for cf in lc:
            if _tag(cf) != "ChannelFunction":
                continue
            funktionen.append(GdtfFunktion(
                von=_dmx_wert(cf.get("DMXFrom") or "0/1"),
                name=(cf.get("Name") or cf.get("Attribute") or "").strip(),
                attribut=(cf.get("Attribute") or "").strip()))
    default = _dmx_wert(ch.get("Default") or "")
    if not ch.get("Default") and funktionen:
        # GDTF 1.1+: der Standardwert steht an der ChannelFunction.
        for lc in ch:
            for cf in lc:
                if _tag(cf) == "ChannelFunction" and cf.get("Default"):
                    default = _dmx_wert(cf.get("Default"))
                    break
            else:
                continue
            break
    return GdtfKanal(offsets=offsets, attribut=attribut,
                     geometrie=(ch.get("Geometry") or "").strip(),
                     name=(ch.get("Name") or "").strip(),
                     default=default, funktionen=tuple(funktionen))


def lies_gdtf(archiv: S.Archiv, datei: str) -> GdtfTyp:
    """Eine ``.gdtf`` aus dem MVR-Archiv. :class:`MvrFehler` bei Problemen."""
    was = f"Die GDTF-Datei „{datei}“"
    unter = archiv.unterarchiv(datei, was)
    try:
        name = unter.finde(GDTF_BESCHREIBUNG)
        if name is None:
            raise MvrFehler(f"{was} enthält keine description.xml.")
        return lies_gdtf_xml(S.parse_xml(unter.lies_eintrag(name),
                                         f"description.xml in „{datei}“"), datei)
    finally:
        unter.schliessen()


# ── MVR ──────────────────────────────────────────────────────────────────────

#: Container, deren Kinder direkt weiterverfolgt werden.
_BEHAELTER = {"Layers", "ChildList"}
#: Objekte mit eigener Lage, unter denen Kinder haengen koennen.
_OBJEKTE = {"Layer", "GroupObject", "Fixture", "Truss", "SceneObject", "Support",
            "VideoScreen", "Projector", "FocusPoint"}


class _Leser:
    def __init__(self, datei: MvrDatei):
        self.datei = datei

    def lauf(self, el, matrix: MvrMatrix, pfad: tuple[str, ...], tiefe: int = 0):
        if tiefe > 64:
            self.datei.hinweise.append("Die Ebenen sind tiefer als 64 Stufen "
                                       "verschachtelt — darunter wird nicht gelesen.")
            return
        for kind in el:
            tag = _tag(kind)
            if tag in _BEHAELTER:
                self.lauf(kind, matrix, pfad, tiefe + 1)
                continue
            if tag not in _OBJEKTE:
                continue      # AUXData, UserData, Klassen … — fuer LightOS ohne Belang
            eigen = lies_matrix(_kind_text(kind, "Matrix")) if _kind(kind, "Matrix") is not None else None
            welt = verkette(matrix, eigen) if eigen is not None else matrix
            name = (kind.get("name") or "").strip()
            if tag == "Fixture":
                self._geraet(kind, welt, pfad, eigen is None and _kind(kind, "Matrix") is not None)
            elif tag == "Truss":
                self.datei.traversen += 1
            elif tag == "FocusPoint":
                self.datei.fokuspunkte += 1
            elif tag not in ("Layer", "GroupObject"):
                self.datei.andere_objekte += 1
            unter = pfad + ((name,) if tag in ("Layer", "GroupObject") and name else ())
            self.lauf(kind, welt, unter, tiefe + 1)

    def _geraet(self, el, welt: MvrMatrix, pfad, matrix_kaputt: bool):
        hinweise = []
        if matrix_kaputt:
            hinweise.append("Die Lage (Matrix) ist unlesbar — das Gerät steht "
                            "am Ursprung seiner Ebene.")
        universum = adresse = None
        adresse_text = ""
        adr = _kind(el, "Addresses")
        if adr is not None:
            eintraege = [a for a in adr if _tag(a) == "Address"]

            def bruch(a):
                try:
                    return int(a.get("break") or 0)
                except ValueError:
                    return 0
            eintraege.sort(key=bruch)
            if eintraege:
                adresse_text = (eintraege[0].text or "").strip()
                gelesen = lies_adresse(adresse_text)
                if gelesen is None:
                    hinweise.append(f"Die Adresse „{adresse_text}“ ist unlesbar.")
                else:
                    universum, adresse = gelesen
        name = (el.get("name") or "").strip()
        nr = _kind_text(el, "FixtureID")
        self.datei.geraete.append(MvrGeraet(
            name=name or (f"Gerät {nr}" if nr else f"Gerät {len(self.datei.geraete) + 1}"),
            uuid=(el.get("uuid") or "").strip(),
            matrix=welt,
            gdtf_datei=_kind_text(el, "GDTFSpec"),
            gdtf_modus=_kind_text(el, "GDTFMode"),
            universum=universum, adresse=adresse, adresse_text=adresse_text,
            fixture_id=nr, unit_number=_kind_text(el, "UnitNumber"),
            pfad=tuple(pfad), hinweise=tuple(hinweise)))


def lies_daten(archiv: S.Archiv) -> MvrDatei:
    name = archiv.finde(SZENE)
    if name is None:
        raise MvrFehler(f"{archiv.was} enthält keine {SZENE} — das ist keine "
                        "MVR-Datei.")
    wurzel = S.parse_xml(archiv.lies_eintrag(name), SZENE)
    if _tag(wurzel) != "GeneralSceneDescription":
        raise MvrFehler(f"{SZENE} hat nicht den erwarteten Aufbau "
                        "(GeneralSceneDescription fehlt).")
    datei = MvrDatei()
    szene = _kind(wurzel, "Scene")
    if szene is None:
        datei.hinweise.append("Die Datei enthält keine Szene.")
        return datei
    _Leser(datei).lauf(szene, EINHEIT, ())
    # GDTF je Typ EINMAL lesen.
    for g in datei.geraete:
        spec = g.gdtf_datei
        if not spec or spec in datei.typen or spec in datei.gdtf_fehler:
            continue
        eintrag = archiv.finde(spec) or archiv.finde(spec + ".gdtf")
        if eintrag is None:
            datei.gdtf_fehler[spec] = (f"Die GDTF-Datei „{spec}“ fehlt in der "
                                       "MVR-Datei.")
            continue
        try:
            datei.typen[spec] = lies_gdtf(archiv, eintrag)
        except MvrFehler as e:
            datei.gdtf_fehler[spec] = str(e)
    return datei


def lies_mvr(pfad: str) -> MvrDatei:
    """Eine ``.mvr``-Datei lesen. Wirft nur :class:`MvrFehler` (deutscher
    Satz), nie etwas anderes."""
    try:
        groesse = os.path.getsize(pfad)
    except OSError as e:
        raise MvrFehler(f"Die Datei lässt sich nicht öffnen: {e.strerror or e}.") from None
    if groesse > S.DATEI_MAX:
        raise MvrFehler(f"Die Datei ist {groesse // (1024 * 1024)} MB groß — "
                        f"mehr als {S.DATEI_MAX // (1024 * 1024)} MB werden "
                        "nicht gelesen.")
    try:
        with open(pfad, "rb") as f:
            archiv = S.Archiv(f, "Die MVR-Datei")
            try:
                return lies_daten(archiv)
            finally:
                archiv.schliessen()
    except MvrFehler:
        raise
    except OSError as e:
        raise MvrFehler(f"Die Datei lässt sich nicht lesen: {e.strerror or e}.") from None
    except Exception as e:      # letzte Sicherung: nie ein Absturz
        raise MvrFehler(f"Die MVR-Datei ist beschädigt oder unbekannt aufgebaut "
                        f"({type(e).__name__}: {S._kurz(e)}).") from None
