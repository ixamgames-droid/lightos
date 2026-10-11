"""LAS-33: Laser-Angaben im Geraeteprofil — Muster, Farben, Richtungen, Betriebsart.

Ein DMX-Laser sagt in seinem Profil bisher nur, WELCHER Kanal was ist. Was die
Werte bedeuten (Wert 192 = Stern, Wert 12 = rot, Groesse laeuft umgekehrt,
0-10 = Mitte), stand hoechstens als Fliesstext in den Notizen. Dieses Modul
beschreibt die Angaben als Daten — je KANAL ein optionales Objekt ``laser``::

    {"version": 1,
     "muster":      [{"von", "bis", "name", "form", "anzahl"?, "stil"?,
                      "bewegt"?, "linien"?}],
     "farben":      [{"von", "bis", "name", "farbe"}],
     "richtung":    {"umgekehrt"?, "ende_niedrig"?, "ende_hoch"?,
                     "mitte"?: {"von", "bis"}},
     "betriebsart": [{"von", "bis", "art", "steuert"}]}

Dasselbe Objekt steht in der Bibliotheksdatei (``kanaele[].laser``), in der
Fixture-DB (``channels.laser_angaben``, als JSON-Text) und im Payload des
Fixture Generators (``channels[].laser``). Fehlt es, ist der Kanal ein Kanal
wie bisher — Alt-Profile bleiben gueltig.

Drei Schichten, alle ohne Qt und ohne Datenbank:

* :func:`pruefe` — streng, fuer die Bibliothek (jeder Befund ein Satz);
  :func:`bereinige` — nachsichtig, fuer alles, was aus der DB oder einem
  Dialog kommt (Kaputtes faellt weg, statt zu stoeren);
* :func:`als_text` / :func:`aus_text` — die DB-Schreibweise;
* :func:`laser_profilangaben` — die LESE-Schicht fuer die Bedienung: Muster
  und Farbe zu einem DMX-Wert, der DMX-Wert zu einem gewaehlten Muster/einer
  Farbe, Regler richtig herum. Ohne Angaben liefert sie ``None`` — die
  Bedienung bleibt dann beim Regler.

Die Zeichnung einer Form (Form -> Polylinien) steht in
:mod:`src.core.laser.musterformen`.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

#: Version des ``laser``-Objekts. Eine hoehere Zahl kennt diese Fassung nicht —
#: sie liest solche Angaben nicht (Rueckfall auf Regler), statt sie falsch zu
#: deuten.
VERSION = 1

#: Baukasten der Formen: Kennung -> Anzeigename. ``eigene`` = Polylinien im
#: Feld ``linien`` (normierte Koordinaten -1..1, x nach rechts, y nach oben).
FORMEN: dict[str, str] = {
    "kreis": "Kreis",
    "linie_waagerecht": "Linie waagerecht",
    "linie_senkrecht": "Linie senkrecht",
    "dreieck": "Dreieck",
    "quadrat": "Quadrat",
    "stern": "Stern",
    "punkte_kreis": "Punkte im Kreis",
    "punkte_linie": "Punkte in einer Linie",
    "welle": "Welle",
    "kreuz": "Kreuz",
    "spirale": "Spirale",
    "mehrere_kreise": "Mehrere Kreise",
    "eigene": "Eigene Form",
}
EIGENE_FORM = "eigene"

#: Wofuer ``anzahl`` bei einer Form steht (fehlt die Form hier, hat die Zahl
#: keine Wirkung) und welcher Wert ohne Angabe gilt.
ANZAHL_BEDEUTUNG: dict[str, tuple[str, int]] = {
    "linie_waagerecht": ("Linien", 1),
    "linie_senkrecht": ("Linien", 1),
    "stern": ("Zacken", 5),
    "punkte_kreis": ("Punkte", 8),
    "punkte_linie": ("Punkte", 5),
    "welle": ("Wellen", 2),
    "spirale": ("Windungen", 3),
    "mehrere_kreise": ("Kreise", 4),
}
ANZAHL_MAX = 64

#: Zeichenstil: Kennung -> Anzeigename.
STILE: dict[str, str] = {"linie": "Linie", "gepunktet": "gepunktet",
                         "gefuellt": "gefüllt"}

#: Benannte Farben fuer die Auswahl im Generator: Kennung -> (Anzeigename, RGB).
#: Gespeichert wird immer der Farbwert ``#rrggbb`` bzw. ``mehrfarbig``.
FARBEN: dict[str, tuple[str, str]] = {
    "rot": ("Rot", "#ff2a2a"),
    "gruen": ("Grün", "#2aff4a"),
    "blau": ("Blau", "#3a6aff"),
    "gelb": ("Gelb", "#ffe32a"),
    "cyan": ("Cyan", "#2ae6ff"),
    "magenta": ("Magenta", "#ff3ad8"),
    "weiss": ("Weiß", "#ffffff"),
}
MEHRFARBIG = "mehrfarbig"

#: Sprechende Enden eines Reglers. Die Paare stehen in der NATUERLICHEN
#: Reihenfolge (niedriger Wert -> hoher Wert); ein Kanal, der sie andersherum
#: traegt, laeuft umgekehrt.
ENDEN_PAARE: tuple[tuple[str, str], ...] = (
    ("klein", "gross"), ("langsam", "schnell"), ("links", "rechts"),
    ("unten", "oben"))
ENDEN: dict[str, str] = {
    "klein": "klein", "gross": "groß", "langsam": "langsam",
    "schnell": "schnell", "links": "links", "rechts": "rechts",
    "unten": "unten", "oben": "oben"}

#: Bedeutung eines Betriebsart-Bereichs: Kennung -> Anzeigename.
BETRIEBSARTEN: dict[str, str] = {
    "aus": "Aus", "musik": "Musik", "auto": "Auto",
    "statisch": "Statisch", "dynamisch": "Dynamisch"}

LINIEN_MAX = 32
PUNKTE_MAX = 256

_FELDER = ("version", "muster", "farben", "richtung", "betriebsart")
_MUSTER_FELDER = ("von", "bis", "name", "form", "anzahl", "stil", "bewegt",
                  "linien")
_FARB_FELDER = ("von", "bis", "name", "farbe")
_RICHTUNG_FELDER = ("umgekehrt", "ende_niedrig", "ende_hoch", "mitte")
_BETRIEBSART_FELDER = ("von", "bis", "art", "steuert")
_LINIEN_FELDER = ("punkte", "geschlossen")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


# ── Pruefen ──────────────────────────────────────────────────────────────────

def _ist_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _ist_zahl(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _unbekannt(d: dict, erlaubt, wo: str, out: list[str]) -> None:
    for k in sorted(set(d) - set(erlaubt)):
        out.append(f"{wo}.{k}: unbekanntes Feld (erlaubt: {', '.join(erlaubt)})")


def _bereich(d: dict, wo: str, out: list[str]) -> None:
    von, bis = d.get("von"), d.get("bis")
    if not (_ist_int(von) and _ist_int(bis) and 0 <= von <= bis <= 255):
        out.append(f"{wo}: von/bis ganze Zahlen mit 0 <= von <= bis <= 255 "
                   f"(ist {von!r}..{bis!r})")


def _name(d: dict, wo: str, out: list[str]) -> None:
    n = d.get("name")
    if not isinstance(n, str) or not n.strip():
        out.append(f"{wo}.name: Pflichtfeld (Text)")
    elif len(n) > 80:
        out.append(f"{wo}.name: hoechstens 80 Zeichen")


def _pruefe_linien(linien, wo: str, out: list[str]) -> None:
    if not isinstance(linien, list) or not 1 <= len(linien) <= LINIEN_MAX:
        out.append(f"{wo}.linien: Liste mit 1..{LINIEN_MAX} Linienzuegen erwartet")
        return
    for li, linie in enumerate(linien):
        wl = f"{wo}.linien[{li}]"
        if not isinstance(linie, dict):
            out.append(f"{wl}: Objekt {{\"punkte\": [[x, y], …]}} erwartet")
            continue
        _unbekannt(linie, _LINIEN_FELDER, wl, out)
        punkte = linie.get("punkte")
        if not isinstance(punkte, list) or not 1 <= len(punkte) <= PUNKTE_MAX:
            out.append(f"{wl}.punkte: Liste mit 1..{PUNKTE_MAX} Punkten erwartet")
            continue
        for pi, p in enumerate(punkte):
            if not (isinstance(p, list) and len(p) == 2
                    and all(_ist_zahl(v) and -1 <= v <= 1 for v in p)):
                out.append(f"{wl}.punkte[{pi}]: [x, y] mit Zahlen von -1 bis 1 "
                           f"erwartet (ist {p!r})")
                break
        if "geschlossen" in linie and not isinstance(linie["geschlossen"], bool):
            out.append(f"{wl}.geschlossen: true/false erwartet")


def _pruefe_muster(m, wo: str) -> list[str]:
    out: list[str] = []
    if not isinstance(m, dict):
        return [f"{wo}: Objekt erwartet"]
    _unbekannt(m, _MUSTER_FELDER, wo, out)
    _bereich(m, wo, out)
    _name(m, wo, out)
    form = m.get("form")
    if not (isinstance(form, str) and form in FORMEN):
        out.append(f"{wo}.form: unbekannt {form!r} (erlaubt: {', '.join(FORMEN)})")
    if "anzahl" in m and not (_ist_int(m["anzahl"])
                              and 1 <= m["anzahl"] <= ANZAHL_MAX):
        out.append(f"{wo}.anzahl: ganze Zahl 1..{ANZAHL_MAX} erwartet")
    if "stil" in m and not (isinstance(m["stil"], str) and m["stil"] in STILE):
        out.append(f"{wo}.stil: {' / '.join(STILE)} erwartet")
    if "bewegt" in m and not isinstance(m["bewegt"], bool):
        out.append(f"{wo}.bewegt: true/false erwartet")
    if form == EIGENE_FORM:
        _pruefe_linien(m.get("linien"), wo, out)
    elif "linien" in m:
        out.append(f"{wo}.linien: nur bei form \"{EIGENE_FORM}\" erlaubt")
    return out


def _pruefe_farbe(f, wo: str) -> list[str]:
    out: list[str] = []
    if not isinstance(f, dict):
        return [f"{wo}: Objekt erwartet"]
    _unbekannt(f, _FARB_FELDER, wo, out)
    _bereich(f, wo, out)
    _name(f, wo, out)
    farbe = f.get("farbe")
    if not (isinstance(farbe, str)
            and (farbe == MEHRFARBIG or _HEX.match(farbe))):
        out.append(f"{wo}.farbe: \"#rrggbb\" oder \"{MEHRFARBIG}\" erwartet "
                   f"(ist {farbe!r})")
    return out


def _pruefe_betriebsart(b, wo: str) -> list[str]:
    out: list[str] = []
    if not isinstance(b, dict):
        return [f"{wo}: Objekt erwartet"]
    _unbekannt(b, _BETRIEBSART_FELDER, wo, out)
    _bereich(b, wo, out)
    art = b.get("art")
    if not (isinstance(art, str) and art in BETRIEBSARTEN):
        out.append(f"{wo}.art: unbekannt {art!r} "
                   f"(erlaubt: {', '.join(BETRIEBSARTEN)})")
    if not isinstance(b.get("steuert"), bool):
        out.append(f"{wo}.steuert: true/false erwartet (steuert LightOS in "
                   f"diesem Bereich Muster und Lage?)")
    return out


def umgekehrt_aus_enden(ende_niedrig: str, ende_hoch: str) -> bool | None:
    """Was die beiden Enden ueber die Laufrichtung sagen: ``False`` =
    natuerlich (klein -> gross), ``True`` = umgekehrt, ``None`` = die Enden
    bilden kein bekanntes Paar."""
    for a, b in ENDEN_PAARE:
        if (ende_niedrig, ende_hoch) == (a, b):
            return False
        if (ende_niedrig, ende_hoch) == (b, a):
            return True
    return None


def _pruefe_richtung(r, wo: str) -> list[str]:
    out: list[str] = []
    if not isinstance(r, dict) or not r:
        return [f"{wo}: Objekt mit mindestens einer Angabe erwartet"]
    _unbekannt(r, _RICHTUNG_FELDER, wo, out)
    if "umgekehrt" in r and not isinstance(r["umgekehrt"], bool):
        out.append(f"{wo}.umgekehrt: true/false erwartet")
    for k in ("ende_niedrig", "ende_hoch"):
        if k in r and not (isinstance(r[k], str) and r[k] in ENDEN):
            out.append(f"{wo}.{k}: unbekannt {r[k]!r} (erlaubt: {', '.join(ENDEN)})")
    if ("ende_niedrig" in r) != ("ende_hoch" in r):
        out.append(f"{wo}: ende_niedrig und ende_hoch gehoeren zusammen")
    elif not out and "ende_niedrig" in r:
        aus_enden = umgekehrt_aus_enden(r["ende_niedrig"], r["ende_hoch"])
        if aus_enden is None:
            out.append(f"{wo}: die Enden {r['ende_niedrig']!r}/{r['ende_hoch']!r} "
                       f"sind kein Paar")
        elif "umgekehrt" in r and r["umgekehrt"] != aus_enden:
            out.append(f"{wo}.umgekehrt: widerspricht den Enden "
                       f"({r['ende_niedrig']} -> {r['ende_hoch']})")
    if "mitte" in r:
        m = r["mitte"]
        if not isinstance(m, dict):
            out.append(f"{wo}.mitte: Objekt {{\"von\": n, \"bis\": n}} erwartet")
        else:
            _unbekannt(m, ("von", "bis"), f"{wo}.mitte", out)
            _bereich(m, f"{wo}.mitte", out)
    return out


_LISTEN = (("muster", _pruefe_muster), ("farben", _pruefe_farbe),
           ("betriebsart", _pruefe_betriebsart))


def pruefe(laser, wo: str = "laser") -> list[str]:
    """Alle Befunde eines ``laser``-Objekts als Saetze; leer = gueltig.

    Ueberlappende oder lueckenhafte Bereiche sind KEIN Befund — ein Laser, bei
    dem erst acht Muster am Geraet gemessen sind, hat Luecken, und das ist die
    ehrliche Angabe. Dafuer gibt es :func:`bereichs_hinweise`."""
    if not isinstance(laser, dict):
        return [f"{wo}: Objekt erwartet"]
    out: list[str] = []
    _unbekannt(laser, _FELDER, wo, out)
    if laser.get("version") != VERSION or not _ist_int(laser.get("version")):
        out.append(f"{wo}.version: {VERSION} erwartet (ist {laser.get('version')!r})")
    for feld, pruefer in _LISTEN:
        if feld not in laser:
            continue
        liste = laser[feld]
        if not isinstance(liste, list) or not liste:
            out.append(f"{wo}.{feld}: Liste mit mindestens einem Eintrag erwartet")
            continue
        for i, e in enumerate(liste):
            out += pruefer(e, f"{wo}.{feld}[{i}]")
    if "richtung" in laser:
        out += _pruefe_richtung(laser["richtung"], f"{wo}.richtung")
    if not any(k in laser for k in _FELDER[1:]):
        out.append(f"{wo}: keine Angabe (muster / farben / richtung / betriebsart)")
    return out


# ── Bereinigen / Schreibweise ────────────────────────────────────────────────

def _geordnet(d: dict, felder) -> dict:
    return {k: d[k] for k in felder if k in d}


def bereinige(laser) -> dict | None:
    """Ein ``laser``-Objekt aus unsicherer Hand (DB-Text, Dialog, von Hand
    gebautes Payload) auf das, was gueltig ist — in fester Feldreihenfolge und
    mit gesetzter ``version``. Ungueltige Eintraege fallen einzeln weg; bleibt
    nichts uebrig (oder ist die Version neuer als diese Fassung), ``None``.

    Eine fehlende ``version`` gilt als 1: der Generator traegt sie nicht im
    Modell, sie wird hier beim Schreiben gesetzt."""
    if not isinstance(laser, dict):
        return None
    version = laser.get("version", VERSION)
    if not _ist_int(version) or version != VERSION:
        return None
    out: dict = {"version": VERSION}
    felder = {"muster": _MUSTER_FELDER, "farben": _FARB_FELDER,
              "betriebsart": _BETRIEBSART_FELDER}
    for feld, pruefer in _LISTEN:
        liste = laser.get(feld)
        if not isinstance(liste, list):
            continue
        gut = []
        for e in liste:
            if isinstance(e, dict):
                e = _geordnet(e, felder[feld])
                if feld == "muster":
                    if e.get("form") != EIGENE_FORM:
                        e.pop("linien", None)
                    else:
                        e["linien"] = _linien_bereinigt(e.get("linien"))
            if not pruefer(e, feld):
                gut.append(e)
        if gut:
            out[feld] = sorted(gut, key=lambda e: (e["von"], e["bis"]))
    r = laser.get("richtung")
    if isinstance(r, dict):
        r = _geordnet(r, _RICHTUNG_FELDER)
        if isinstance(r.get("mitte"), dict):
            r["mitte"] = _geordnet(r["mitte"], ("von", "bis"))
        if r and not _pruefe_richtung(r, "richtung"):
            out["richtung"] = r
    return out if len(out) > 1 else None


def _linien_bereinigt(linien):
    """Koordinaten einer eigenen Form auf drei Nachkommastellen — eine mit der
    Maus gesetzte Linie braucht keine 17 Stellen in der Datei."""
    if not isinstance(linien, list):
        return linien
    out = []
    for linie in linien:
        if not (isinstance(linie, dict) and isinstance(linie.get("punkte"), list)):
            out.append(linie)
            continue
        neu: dict = {"punkte": [
            [round(float(v), 3) for v in p]
            if isinstance(p, (list, tuple)) and len(p) == 2
            and all(_ist_zahl(v) for v in p) else p
            for p in linie["punkte"]]}
        if linie.get("geschlossen") is True:
            neu["geschlossen"] = True
        out.append(neu)
    return out


def als_text(laser) -> str:
    """Die DB-Schreibweise (``channels.laser_angaben``): kanonisches JSON, oder
    ``""`` fuer „keine Angaben“."""
    sauber = bereinige(laser)
    if sauber is None:
        return ""
    return json.dumps(sauber, ensure_ascii=False, separators=(",", ":"))


def aus_text(text) -> dict | None:
    """Gegenstueck zu :func:`als_text`. Leer, kein JSON, kein Objekt oder eine
    unbekannte Version -> ``None`` (keine Angaben)."""
    if not text or not isinstance(text, str):
        return None
    try:
        return bereinige(json.loads(text))
    except (ValueError, TypeError):
        return None


# ── Hilfen fuer den Generator ────────────────────────────────────────────────

def gleichmaessig_aufteilen(anzahl: int, von: int = 0,
                            bis: int = 255) -> list[tuple[int, int]]:
    """``anzahl`` lueckenlose Bereiche ueber ``von..bis``, so gleich gross wie
    moeglich (16 ueber 0-255 -> 0-15, 16-31, …, 240-255). Mehr Bereiche als
    Werte gibt es nicht: die Zahl wird auf die Breite gekappt."""
    von, bis = max(0, min(255, int(von))), max(0, min(255, int(bis)))
    if bis < von:
        von, bis = bis, von
    breite = bis - von + 1
    n = max(1, min(int(anzahl), breite))
    grenzen = [von + (i * breite) // n for i in range(n + 1)]
    return [(grenzen[i], grenzen[i + 1] - 1) for i in range(n)]


# Ganze Woerter bzw. Wortanfaenge — „off“ darf nicht in „offen“ treffen.
_BETRIEBSART_WORTE = (
    ("aus", re.compile(r"\b(aus|off|blackout)\b")),
    ("musik", re.compile(r"\b(musik|sound|music|audio)")),
    ("auto", re.compile(r"\bauto")),
    ("statisch", re.compile(r"\b(statisch|static)")),
    ("dynamisch", re.compile(r"\b(dynamisch|dynamic)")),
)


def betriebsart_aus_bereichen(bereiche) -> list[dict]:
    """VORSCHLAG fuer die Betriebsart-Liste aus den Wertebereichen eines
    Kanals — ``bereiche`` = ``[(von, bis, name, art)]``. Die Bedeutung kommt
    aus der Art (``closed`` = aus, ``sound`` = Musik) bzw. aus dem Namen;
    Bereiche, die sich nicht deuten lassen, bleiben weg. ``steuert`` ist bei
    statischen und dynamischen Mustern gesetzt. Ein Vorschlag zum Pruefen,
    keine Wahrheit."""
    out = []
    for von, bis, name, kind in bereiche or ():
        text = str(name or "").casefold()
        art = {"closed": "aus", "sound": "musik"}.get(str(kind or ""))
        if art is None:
            art = next((a for a, muster in _BETRIEBSART_WORTE
                        if muster.search(text)), None)
        if art is None:
            continue
        eintrag = {"von": int(von), "bis": int(bis), "art": art,
                   "steuert": art in ("statisch", "dynamisch")}
        if not _pruefe_betriebsart(eintrag, "betriebsart"):
            out.append(eintrag)
    return sorted(out, key=lambda e: (e["von"], e["bis"]))


def bereichs_hinweise(eintraege, was: str = "Bereiche") -> list[str]:
    """Plausibilitaet einer Bereichsliste (Muster, Farben, Betriebsart) als
    HINWEISE — nie als Sperre: verdrehte, ueberlappende und lueckenhafte
    Bereiche. Die Luecken stehen in EINEM Satz, damit eine Liste aus acht
    gemessenen Einzelwerten nicht acht Zeilen fuellt."""
    out: list[str] = []
    gut = []
    for e in eintraege or ():
        try:
            von, bis = int(e["von"]), int(e["bis"])
        except (KeyError, TypeError, ValueError):
            continue
        name = str(e.get("name") or e.get("art") or f"{von}–{bis}")
        if von > bis:
            out.append(f"{was}: „{name}“ ist verdreht (von {von} > bis {bis}).")
            continue
        gut.append((von, bis, name))
    gut.sort()
    luecken: list[str] = []
    ende = -1
    letzter = ""
    for von, bis, name in gut:
        if von <= ende:
            out.append(f"{was}: „{letzter}“ und „{name}“ überlappen "
                       f"(bei {von}–{min(ende, bis)}).")
        elif von > ende + 1:
            luecken.append(f"{ende + 1}–{von - 1}" if von - 1 > ende + 1
                           else f"{von - 1}")
        if bis > ende:
            ende, letzter = bis, name
    if gut and ende < 255:
        luecken.append(f"{ende + 1}–255" if ende + 1 < 255 else "255")
    if luecken:
        gezeigt = ", ".join(luecken[:4]) + (" …" if len(luecken) > 4 else "")
        out.append(f"{was}: ohne Eintrag bleiben die Werte {gezeigt} — dort "
                   f"zeigt die Bedienung den Regler.")
    return out


# ── Lese-Schicht ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Bereich:
    """Ein DMX-Bereich mit Namen."""
    von: int
    bis: int
    name: str = ""

    @property
    def mitte(self) -> int:
        """Der Wert, den die Bedienung sendet, um diesen Bereich zu waehlen."""
        return (self.von + self.bis) // 2

    def enthaelt(self, dmx: int) -> bool:
        return self.von <= int(dmx) <= self.bis


@dataclass(frozen=True)
class Muster(Bereich):
    form: str = "kreis"
    anzahl: int | None = None
    stil: str = "linie"
    bewegt: bool = False
    #: nur bei ``form == "eigene"``: ``({"punkte": [[x, y], …], "geschlossen"?}, …)``
    linien: tuple = ()

    def als_dict(self) -> dict:
        d: dict = {"von": self.von, "bis": self.bis, "name": self.name,
                   "form": self.form}
        if self.anzahl is not None:
            d["anzahl"] = self.anzahl
        if self.stil != "linie":
            d["stil"] = self.stil
        if self.bewegt:
            d["bewegt"] = True
        if self.linien:
            d["linien"] = [dict(l) for l in self.linien]
        return d


@dataclass(frozen=True)
class Farbe(Bereich):
    farbe: str = "#ffffff"

    @property
    def mehrfarbig(self) -> bool:
        return self.farbe == MEHRFARBIG

    @property
    def rgb(self) -> tuple[int, int, int] | None:
        """``(r, g, b)`` — oder ``None`` bei ``mehrfarbig``."""
        if self.mehrfarbig:
            return None
        h = self.farbe.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


@dataclass(frozen=True)
class Betriebsart(Bereich):
    art: str = "aus"
    #: Steuert LightOS in diesem Bereich Muster und Lage? (In Musik/Auto laeuft
    #: das Geraet selbst — die Regler wirken dann nicht.)
    steuert: bool = False


@dataclass(frozen=True)
class Richtung:
    """Wie ein Regler zu diesem Kanal richtig herum laeuft.

    Der REGLER der Bedienung geht immer von 0.0 (klein / langsam / links /
    unten) bis 1.0 (gross / schnell / rechts / oben). Laeuft der Kanal
    umgekehrt, dreht :meth:`regler_zu_dmx` den Wert; ein Mittelbereich (z. B.
    0-10 = Mitte) gehoert nicht zum Regelweg."""
    umgekehrt: bool = False
    ende_niedrig: str = ""      # was bei NIEDRIGEM DMX-Wert passiert
    ende_hoch: str = ""         # was bei HOHEM DMX-Wert passiert
    mitte: tuple[int, int] | None = None

    @property
    def enden(self) -> tuple[str, str]:
        """``(links, rechts)`` — die Beschriftung des richtig herum laufenden
        Reglers (Kennungen aus :data:`ENDEN`, leer = keine Angabe)."""
        return ((self.ende_hoch, self.ende_niedrig) if self.umgekehrt
                else (self.ende_niedrig, self.ende_hoch))

    @property
    def regelweg(self) -> tuple[int, int]:
        """DMX-Bereich, ueber den der Regler laeuft (ohne den Mittelbereich,
        wenn der an einem Rand liegt)."""
        if self.mitte is not None:
            von, bis = self.mitte
            if von <= 0 and bis < 255:
                return bis + 1, 255
            if bis >= 255 and von > 0:
                return 0, von - 1
        return 0, 255

    @property
    def mitte_dmx(self) -> int | None:
        """Der Wert fuer „Mitte“ — oder ``None`` ohne Mittelbereich."""
        if self.mitte is None:
            return None
        return (self.mitte[0] + self.mitte[1]) // 2

    def ist_mitte(self, dmx: int) -> bool:
        return self.mitte is not None and self.mitte[0] <= int(dmx) <= self.mitte[1]

    def regler_zu_dmx(self, anteil: float) -> int:
        """Reglerstellung 0.0..1.0 (richtig herum) -> DMX-Wert."""
        a = max(0.0, min(1.0, float(anteil)))
        if self.umgekehrt:
            a = 1.0 - a
        lo, hi = self.regelweg
        return int(round(lo + a * (hi - lo)))

    def dmx_zu_regler(self, dmx: int) -> float | None:
        """DMX-Wert -> Reglerstellung 0.0..1.0; ``None`` im Mittelbereich."""
        if self.ist_mitte(dmx):
            return None
        lo, hi = self.regelweg
        a = 0.0 if hi == lo else (max(lo, min(hi, int(dmx))) - lo) / (hi - lo)
        return 1.0 - a if self.umgekehrt else a


def _treffer(bereiche, dmx):
    """Der Bereich, in dem ``dmx`` liegt; bei Ueberlappung der schmalste."""
    passend = [b for b in bereiche if b.enthaelt(dmx)]
    return min(passend, key=lambda b: (b.bis - b.von, b.von)) if passend else None


def _gewaehlt(bereiche, wahl, nahe):
    """Bereich zu einer Wahl: Index, Objekt oder Name (ohne Gross/klein). Bei
    mehreren gleichnamigen der, dessen Mitte ``nahe`` am naechsten liegt."""
    if isinstance(wahl, Bereich):
        return wahl
    if isinstance(wahl, int) and not isinstance(wahl, bool):
        return bereiche[wahl] if 0 <= wahl < len(bereiche) else None
    name = str(wahl or "").strip().casefold()
    passend = [b for b in bereiche if b.name.strip().casefold() == name]
    if not passend:
        return None
    if nahe is None:
        return passend[0]
    return min(passend, key=lambda b: (abs(b.mitte - int(nahe)), b.von))


@dataclass(frozen=True)
class KanalAngaben:
    """Die Laser-Angaben EINES Kanals, aufbereitet."""
    nummer: int                 # 1-basiert, Reihenfolge im Modus
    name: str
    attribut: str
    muster: tuple[Muster, ...] = ()
    farben: tuple[Farbe, ...] = ()
    richtung: Richtung | None = None
    betriebsart: tuple[Betriebsart, ...] = ()

    def muster_fuer(self, dmx: int) -> Muster | None:
        """Das Muster, das bei diesem DMX-Wert laeuft (``None`` = unbekannt)."""
        return _treffer(self.muster, dmx)

    def farbe_fuer(self, dmx: int) -> Farbe | None:
        return _treffer(self.farben, dmx)

    def betriebsart_fuer(self, dmx: int) -> Betriebsart | None:
        return _treffer(self.betriebsart, dmx)

    def dmx_fuer_muster(self, wahl, nahe: int | None = None) -> int | None:
        """DMX-Wert (Bereichsmitte) fuer ein gewaehltes Muster — ``wahl`` ist
        der Index in :attr:`muster`, das Muster selbst oder sein Name."""
        b = _gewaehlt(self.muster, wahl, nahe)
        return None if b is None else b.mitte

    def dmx_fuer_farbe(self, wahl, nahe: int | None = None) -> int | None:
        """DMX-Wert (Bereichsmitte) fuer eine gewaehlte Farbe. Kommt sie
        mehrfach vor, gewinnt der Bereich am naechsten an ``nahe`` (dem
        aktuellen Wert) — der Laser springt dann am wenigsten."""
        b = _gewaehlt(self.farben, wahl, nahe)
        return None if b is None else b.mitte

    def dmx_fuer_betriebsart(self, art: str) -> int | None:
        b = next((b for b in self.betriebsart if b.art == art), None)
        return None if b is None else b.mitte

    def steuert(self, dmx: int) -> bool | None:
        """Steuert LightOS bei diesem Betriebsart-Wert Muster und Lage?
        ``None`` = das Profil sagt es fuer diesen Wert nicht."""
        b = self.betriebsart_fuer(dmx)
        return None if b is None else b.steuert


@dataclass(frozen=True)
class LaserAngaben:
    """Alle Laser-Angaben eines Modus. Nur Kanaele MIT Angaben stehen drin."""
    kanaele: tuple[KanalAngaben, ...] = ()

    def kanal(self, nummer: int) -> KanalAngaben | None:
        return next((k for k in self.kanaele if k.nummer == nummer), None)

    def fuer_attribut(self, attribut: str) -> KanalAngaben | None:
        """Der erste Kanal mit diesem Attribut (z. B. ``"zoom"``)."""
        return next((k for k in self.kanaele if k.attribut == attribut), None)

    @property
    def muster_kanal(self) -> KanalAngaben | None:
        return next((k for k in self.kanaele if k.muster), None)

    @property
    def farb_kanal(self) -> KanalAngaben | None:
        return next((k for k in self.kanaele if k.farben), None)

    @property
    def betriebsart_kanal(self) -> KanalAngaben | None:
        return next((k for k in self.kanaele if k.betriebsart), None)

    def richtung(self, kanal) -> Richtung | None:
        """Richtung eines Kanals — ``kanal`` ist Nummer oder Attribut."""
        k = (self.kanal(kanal) if isinstance(kanal, int)
             else self.fuer_attribut(str(kanal)))
        return None if k is None else k.richtung


def kanal_angaben(laser, nummer: int = 1, name: str = "",
                  attribut: str = "raw") -> KanalAngaben | None:
    """Ein ``laser``-Objekt als :class:`KanalAngaben` (``None`` = keine)."""
    d = bereinige(laser)
    if d is None:
        return None
    muster = tuple(
        Muster(m["von"], m["bis"], m["name"], m["form"], m.get("anzahl"),
               m.get("stil", "linie"), bool(m.get("bewegt", False)),
               tuple(m.get("linien", ())))
        for m in d.get("muster", ()))
    farben = tuple(Farbe(f["von"], f["bis"], f["name"], f["farbe"].lower())
                   for f in d.get("farben", ()))
    betriebsart = tuple(Betriebsart(b["von"], b["bis"],
                                    BETRIEBSARTEN[b["art"]], b["art"], b["steuert"])
                        for b in d.get("betriebsart", ()))
    richtung = None
    r = d.get("richtung")
    if r:
        tief, hoch = r.get("ende_niedrig", ""), r.get("ende_hoch", "")
        umgekehrt = r.get("umgekehrt")
        if umgekehrt is None:
            umgekehrt = bool(umgekehrt_aus_enden(tief, hoch))
        m = r.get("mitte")
        richtung = Richtung(bool(umgekehrt), tief, hoch,
                            (m["von"], m["bis"]) if m else None)
    return KanalAngaben(int(nummer), str(name or ""), str(attribut or "raw"),
                        muster, farben, richtung, betriebsart)


def _kanal_teile(kanal, index: int):
    """``(nummer, name, attribut, laser)`` aus einem Kanal beliebiger Herkunft:
    Bibliotheksdatei (``attribut``/``laser``), Generator-Payload und -Modell
    (``attribute``/``laser``), DB-Zeile (``attribute``/``laser_angaben``)."""
    if isinstance(kanal, dict):
        laser = kanal.get("laser")
        if laser is None and kanal.get("laser_angaben"):
            laser = aus_text(kanal["laser_angaben"])
        return (kanal.get("channel_number", index + 1), kanal.get("name", ""),
                kanal.get("attribut") or kanal.get("attribute") or "raw", laser)
    laser = getattr(kanal, "laser", None)
    if not isinstance(laser, dict):
        laser = aus_text(getattr(kanal, "laser_angaben", None))
    return (getattr(kanal, "channel_number", None) or index + 1,
            getattr(kanal, "name", ""), getattr(kanal, "attribute", "raw"), laser)


def _kanaele_aus(quelle, modus):
    """Die Kanalliste zu ``quelle`` (siehe :func:`laser_profilangaben`)."""
    if quelle is None:
        return ()
    if isinstance(quelle, (list, tuple)):
        return quelle
    if isinstance(quelle, dict):
        if "modi" in quelle or "modes" in quelle:
            modi = quelle.get("modi") or quelle.get("modes") or ()
            m = next((m for m in modi if modus is None or m.get("name") == modus),
                     None)
            return _kanaele_aus(m, None)
        return quelle.get("kanaele") or quelle.get("channels") or ()
    if hasattr(quelle, "fixture_profile_id"):       # gepatchtes Geraet
        from src.core.app_state import get_channels_for_patched
        return get_channels_for_patched(quelle)
    modi = getattr(quelle, "modes", None)
    if modi is not None:                            # Profil (DB oder Generator)
        m = next((m for m in modi if modus is None or m.name == modus), None)
        return _kanaele_aus(m, None)
    kanaele = getattr(quelle, "channels", None)     # Modus
    if kanaele is None:
        return ()
    if all(getattr(c, "channel_number", None) for c in kanaele):
        return sorted(kanaele, key=lambda c: c.channel_number)
    return kanaele


def laser_profilangaben(quelle, modus: str | None = None) -> LaserAngaben | None:
    """Die Laser-Angaben eines Geraets, aufbereitet fuer die Bedienung.

    ``quelle`` ist, was der Aufrufer gerade in der Hand hat: ein gepatchtes
    Geraet, ein Profil (DB-Objekt, Bibliotheksdatei als ``dict`` oder
    Generator-Modell) samt Modusname ``modus`` (``None`` = erster Modus), ein
    einzelner Modus oder direkt eine Kanalliste.

    Liefert ``None``, wenn KEIN Kanal Angaben traegt — „keine“: die Bedienung
    faellt dann auf die Regler zurueck. Wirft nie wegen kaputter Angaben; was
    ungueltig ist, zaehlt als nicht vorhanden."""
    kanaele = []
    for i, kanal in enumerate(_kanaele_aus(quelle, modus)):
        nummer, name, attribut, laser = _kanal_teile(kanal, i)
        k = kanal_angaben(laser, nummer, name, attribut) if laser else None
        if k is not None:
            kanaele.append(k)
    return LaserAngaben(tuple(kanaele)) if kanaele else None
