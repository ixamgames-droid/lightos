"""ENG-35: Prioritaeten-Stufen fuer Effekte — Namen ueber der Zahl ``priority``.

Der Engine-Merge kennt weiterhin nur die Zahl ``Function.priority`` (hoeher
schreibt spaeter und gewinnt; gleiche Zahl = zuletzt gestartet gewinnt, siehe
``FunctionManager.tick``). Dieses Modul legt fuenf feste, benannte Stufen
darueber. Es rechnet nichts um und fasst keine Show an: eine Zahl, die auf
keine Stufe passt, bleibt wie sie ist und heisst in der Bedienung
„eigene Zahl (n)“.

Warum die Abstaende 20 betragen (−20 / 0 / 20 / 40 / 60) und nicht 10:
die Kanal-Kopplung (``MappedChannelChange``) wird vom Editor seit jeher mit
der festen Zahl 10 angelegt — sie muss NACH den Bewegungs-Effekten der Stufe
„Effekte“ rechnen, weil sie deren Tilt-Ausgang liest. Laege „Akzente“ auf 10,
wuerde jede vorhandene Kanal-Kopplung als bewusst gewaehlter „Akzent“
erscheinen, und ein Akzent-Effekt haette mit ihr dieselbe Stufe. Mit 20er-
Schritten liegt die 10 ehrlich ZWISCHEN „Effekte“ und „Akzente“ und wird als
„eigene Zahl (10)“ gezeigt; alte Shows bleiben dabei unveraendert. Die Luecken
lassen ausserdem Platz, falls spaeter Zwischenstufen gewuenscht werden.

Leaf-Modul ohne Qt-/DB-Importe: Kern, Oberflaeche und Tests teilen es sich.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from src.core.attr_groups import classify_attr


@dataclass(frozen=True)
class Stufe:
    schluessel: str
    name: str
    zahl: int
    hinweis: str


# Von der SCHWAECHSTEN zur STAERKSTEN. Die Reihenfolge ist Teil der Bedeutung
# („Stufe hoeher“ = naechster Eintrag).
STUFEN: tuple[Stufe, ...] = (
    Stufe("grundlicht", "Grundlicht", -20,
          "Liegt unter allem anderen — jeder Effekt einer hoeheren Stufe "
          "gewinnt dagegen."),
    Stufe("effekte", "Effekte", 0,
          "Vorgabe. Alle Effekte aus aelteren Shows stehen hier."),
    Stufe("akzente", "Akzente", 20,
          "Gewinnt gegen Grundlicht und Effekte."),
    Stufe("strobe_blinder", "Strobe & Blinder", 40,
          "Gewinnt gegen Grundlicht, Effekte und Akzente."),
    Stufe("notfall", "Notfall", 60,
          "Staerkste Stufe fuer Effekte."),
)

STUFE_VORGABE: Stufe = STUFEN[1]          # „Effekte“ = 0

# Die feste Zeile ueber den Stufen: Snap-Tasten und Programmer sind keine
# Effekte und lassen sich nicht einsortieren (siehe docs: „Wer gewinnt?“).
SNAP_ZEILE = "Snaps / Programmer — liegt immer darüber"
MODIFY_HINWEIS = "Modify — rechnet auf das fertige Bild"

_NACH_ZAHL: dict[int, Stufe] = {s.zahl: s for s in STUFEN}
_NACH_SCHLUESSEL: dict[str, Stufe] = {s.schluessel: s for s in STUFEN}


def zahl_von(wert) -> int:
    """``priority`` robust als ganze Zahl (kaputte Werte -> 0 = „Effekte“)."""
    try:
        return int(wert)
    except (TypeError, ValueError):
        return 0


def stufe_fuer_zahl(zahl) -> Stufe | None:
    """Die Stufe mit genau dieser Zahl — ``None`` fuer eine „eigene Zahl“."""
    return _NACH_ZAHL.get(zahl_von(zahl))


def stufe_fuer_schluessel(schluessel: str) -> Stufe | None:
    return _NACH_SCHLUESSEL.get(str(schluessel or ""))


def stufe_von(funktion) -> Stufe | None:
    """Stufe einer Funktion (``None`` = eigene Zahl)."""
    return stufe_fuer_zahl(getattr(funktion, "priority", 0))


def stufen_name(zahl) -> str:
    """Anzeigename: Stufenname oder „eigene Zahl (n)“."""
    s = stufe_fuer_zahl(zahl)
    return s.name if s is not None else f"eigene Zahl ({zahl_von(zahl)})"


def naechste_stufe(zahl, richtung: int) -> Stufe | None:
    """Nachbarstufe von ``zahl`` aus: ``richtung`` > 0 = staerker, < 0 =
    schwaecher. Fuer eine eigene Zahl die naechste echte Stufe in der Richtung.
    ``None`` am Rand."""
    z = zahl_von(zahl)
    if richtung > 0:
        kandidaten = [s for s in STUFEN if s.zahl > z]
        return kandidaten[0] if kandidaten else None
    kandidaten = [s for s in STUFEN if s.zahl < z]
    return kandidaten[-1] if kandidaten else None


def ist_modify(funktion) -> bool:
    """ENG-37 (falls vorhanden): rechnet die Funktion als Modify-Effekt auf das
    fertige Bild? Ohne ENG-37 gibt es weder Feld noch Methode -> ``False``."""
    if not getattr(funktion, "modify", False):
        return False
    wirksam = getattr(funktion, "modify_wirksam", None)
    if callable(wirksam):
        try:
            return bool(wirksam())
        except Exception:
            return False
    return True


# ── Bausteine: was fasst ein Effekt an? ──────────────────────────────────────

DIMMER, FARBE, BEWEGUNG, GOBO, SONSTIGES = "D", "F", "B", "G", "S"
BAUSTEIN_NAMEN: dict[str, str] = {
    DIMMER: "Dimmer", FARBE: "Farbe", BEWEGUNG: "Bewegung", GOBO: "Gobo",
    SONSTIGES: "Sonstiges",
}
BAUSTEIN_REIHENFOLGE: tuple[str, ...] = (DIMMER, FARBE, BEWEGUNG, GOBO, SONSTIGES)

_GRUPPE_ZU_BAUSTEIN = {"Intensity": DIMMER, "Color": FARBE,
                       "Position": BEWEGUNG, "Gobo": GOBO}
# Shutter/Strobe stehen im Programmer auf dem Intensity-Reiter, sind fuer den
# Renderer aber KEIN Dimmer (app_state._DIM_INTENSITY_ATTRS nimmt sie aus).
_KEIN_DIMMER = frozenset({"shutter", "strobe"})

_MAX_TIEFE = 8


@dataclass(frozen=True)
class Bausteine:
    """Was eine Funktion schreibt. ``unbekannt`` = mindestens ein Teil liess
    sich nicht bestimmen (dann ist ``menge`` nur das sicher Erkannte)."""
    menge: frozenset = frozenset()
    unbekannt: bool = False

    def text(self) -> str:
        teile = [BAUSTEIN_NAMEN[b] for b in BAUSTEIN_REIHENFOLGE if b in self.menge]
        if self.unbekannt:
            teile.append("unbekannt")
        return " · ".join(teile) if teile else "—"

    def kuerzel(self) -> str:
        k = "".join(b for b in BAUSTEIN_REIHENFOLGE if b in self.menge)
        return (k + "?") if self.unbekannt else (k or "—")


def baustein_fuer_attribut(attr: str) -> str:
    a = (attr or "").lower().split("#", 1)[0]
    if a in _KEIN_DIMMER:
        return SONSTIGES
    return _GRUPPE_ZU_BAUSTEIN.get(classify_attr(a), SONSTIGES)


def _aus_attributen(attrs: Iterable[str]) -> Bausteine:
    return Bausteine(frozenset(baustein_fuer_attribut(a) for a in attrs if a))


def _vereinen(teile: Iterable[Bausteine]) -> Bausteine:
    menge: set = set()
    unbekannt = False
    for t in teile:
        menge |= t.menge
        unbekannt = unbekannt or t.unbekannt
    return Bausteine(frozenset(menge), unbekannt)


_UNBEKANNT = Bausteine(frozenset(), True)


def bausteine_von(funktion,
                  aufloesen: Callable[[int], object | None] | None = None,
                  kanal_attribut: Callable[[int, int], str | None] | None = None,
                  _tiefe: int = 0) -> Bausteine:
    """Welche Bausteine (Dimmer / Farbe / Bewegung / Gobo / Sonstiges) schreibt
    ``funktion``? Abgeleitet aus dem, was sie gespeichert hat — nicht geraten.

    ``aufloesen``: Funktions-ID -> Funktion (fuer Chaser, Sammlung, Show).
    ``kanal_attribut``: (Geraete-ID, Kanal-Nr. im Geraet) -> Attributname (fuer
    Szenen, die nur Kanalnummern speichern). Fehlt eine Auskunft, steht
    ``unbekannt`` im Ergebnis — Skripte sind grundsaetzlich nicht erkennbar.
    """
    f = funktion
    if f is None or _tiefe > _MAX_TIEFE:
        return _UNBEKANNT
    if getattr(f, "is_script", False):
        return _UNBEKANNT
    typ = getattr(getattr(f, "function_type", None), "value", "")

    if getattr(f, "is_layered_effect", False):
        return _aus_attributen([getattr(f, "target_attribute", "")])

    if getattr(f, "is_carousel", False):
        muster = getattr(getattr(f, "pattern", None), "value", "")
        menge = {DIMMER}
        if muster in ("Circle", "Sweep"):
            menge.add(BEWEGUNG)
        elif muster not in ("Pulse", "Wave", "Chase"):
            return Bausteine(frozenset(menge), True)
        if getattr(f, "paint_color", False):
            menge.add(FARBE)
        return Bausteine(frozenset(menge))

    if typ == "RGBMatrix":
        stil = getattr(getattr(f, "style", None), "value", getattr(f, "style", ""))
        if stil in ("RGB", "RGBW"):
            menge = {FARBE}
            if getattr(f, "drive_intensity", False):
                menge.add(DIMMER)
            return Bausteine(frozenset(menge))
        if stil == "Dimmer":
            return Bausteine(frozenset({DIMMER}))
        if stil == "Shutter":
            return Bausteine(frozenset({SONSTIGES}))
        return _UNBEKANNT

    if typ == "EFX":
        geraete = getattr(f, "fixtures", None)
        if not isinstance(geraete, (list, tuple)):
            return _UNBEKANNT
        attrs: list[str] = []
        for g in geraete:
            attrs.append(getattr(g, "pan_attr", "pan") or "pan")
            attrs.append(getattr(g, "tilt_attr", "tilt") or "tilt")
        return _aus_attributen(attrs)

    if typ == "MappedChannelChange":
        attrs = []
        for r in getattr(f, "rules", None) or ():
            if getattr(r, "mode", "") == "gradient":
                attrs.append("color_r")
            else:
                attrs.append(getattr(r, "target", ""))
        return _aus_attributen(attrs)

    if typ == "Sequence":
        attrs = []
        for schritt in getattr(f, "steps", None) or ():
            werte = getattr(schritt, "values", None)
            if not isinstance(werte, dict):
                return _UNBEKANNT
            for geraet in werte.values():
                if isinstance(geraet, dict):
                    attrs.extend(str(a) for a in geraet)
        return _aus_attributen(attrs)

    if typ == "Scene":
        werte = getattr(f, "values", None)
        if not isinstance(werte, list):
            return _UNBEKANNT
        menge: set = set()
        unbekannt = False
        for sv in werte:
            attr = None
            if kanal_attribut is not None:
                try:
                    attr = kanal_attribut(int(getattr(sv, "fixture_id")),
                                          int(getattr(sv, "channel")))
                except Exception:
                    attr = None
            if not attr:
                unbekannt = True
                continue
            menge.add(baustein_fuer_attribut(attr))
        return Bausteine(frozenset(menge), unbekannt)

    kinder: list[int] | None = None
    if typ == "Chaser":
        kinder = [getattr(s, "function_id", None)
                  for s in getattr(f, "steps", None) or ()]
    elif typ == "Collection":
        kinder = list(getattr(f, "function_ids", None) or ())
    elif typ == "Show":
        kinder = [getattr(sf, "function_id", None)
                  for spur in getattr(f, "tracks", None) or ()
                  for sf in getattr(spur, "show_functions", None) or ()]
    if kinder is not None:
        if aufloesen is None:
            return _UNBEKANNT if kinder else Bausteine()
        teile = []
        for kid in kinder:
            try:
                kind = aufloesen(int(kid))
            except (TypeError, ValueError):
                kind = None
            teile.append(bausteine_von(kind, aufloesen, kanal_attribut,
                                       _tiefe + 1))
        return _vereinen(teile)

    if typ == "Audio":
        return Bausteine()          # spielt Ton, schreibt kein DMX
    return _UNBEKANNT


# ── Art einer Funktion in Worten ─────────────────────────────────────────────

_ART = {"Scene": "Szene", "Chaser": "Chaser", "Sequence": "Sequenz",
        "Collection": "Sammlung", "Show": "Show", "EFX": "Bewegung (EFX)",
        "RGBMatrix": "Matrix", "Audio": "Audio",
        "MappedChannelChange": "Kanal-Kopplung"}


def art_von(funktion) -> str:
    if getattr(funktion, "is_script", False):
        return "Skript"
    if getattr(funktion, "is_layered_effect", False):
        return "Ebenen-Effekt"
    if getattr(funktion, "is_carousel", False):
        return "Carousel"
    typ = getattr(getattr(funktion, "function_type", None), "value", "")
    return _ART.get(typ, typ or "Funktion")
