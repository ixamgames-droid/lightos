"""WEB-09: Datenmodell der Handy-Konsole — die „Handy-Seiten".

Die Handy-Konsole (WEB-07, Konzept A) zeigt keine eigenen Bedienelemente,
sondern VERKNUEPFUNGEN auf Widgets der grossen Konsole. Dieses Modul beschreibt,
welche Widgets aufs Handy duerfen und wo sie dort liegen:

    {"version": 1,
     "seiten": [
        {"name": "Seite 1", "spalten": 4, "zeilen": 10,
         "eintraege": [
            {"widget": "w1a2b3c4d5e6", "spalte": 0, "zeile": 0,
             "breite": 4, "hoehe": 3},
            ...]},
        ...]}

Der Abschnitt liegt im VC-Layout unter :data:`SCHLUESSEL` — neben ``widgets``.
Damit nehmen ihn Show-Datei, „Canvas exportieren/importieren" und das
Rueckgaengig der Konsole ohne eigenes Zutun mit (alle drei arbeiten auf
``VCCanvas.to_dict()``/``from_dict()``). Ohne Seiten wird der Schluessel gar
nicht geschrieben: eine Show von frueher bleibt beim Laden und erneuten
Speichern unveraendert.

Reines Python ohne Qt — der Web-Server, die Tests und spaeter die
Editor-Seitenleiste (WEB-10) benutzen dieselben Funktionen. Jede Funktion gibt
einen NEUEN Abschnitt zurueck und laesst ihre Eingabe unberuehrt; so bleibt der
Vorher-Stand fuer das Rueckgaengig gueltig.

Die Seiten sind zugleich die FREIGABE: die Web-Schnittstelle liefert und
bedient nur Widgets, die auf einer Handy-Seite liegen
(:func:`freigegebene_kennungen`).
"""
from __future__ import annotations

import copy
import re

VERSION = 1
SCHLUESSEL = "handy_seiten"

SPALTEN = 4
ZEILEN = 10
MAX_SEITEN = 12
MAX_NAME = 24

# Dieselbe Form wie ``vc_widget.kennung_gueltig`` — hier wiederholt, damit das
# Modell ohne Qt-Import auskommt (ein Test haelt beide Muster gleich).
_KENNUNG_MUSTER = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{3,63}$")

# Standardgroessen in Zellen (Breite, Hoehe) fuer „Automatisch fuellen".
GROESSE_TASTE = (1, 1)
GROESSE_TASTE_BREIT = (2, 1)
GROESSE_FADER = (1, 3)
GROESSE_CUELISTE = (4, 3)
GROESSE_BLACKOUT = (SPALTEN, 1)

# Ab dieser Beschriftungslaenge bekommt eine Taste zwei Zellen Breite — in
# einer Zelle (rund 85 px am Handy) waere der Text nicht mehr lesbar.
_BREIT_AB_ZEICHEN = 10
# Tasten, die man im Ernstfall blind treffen muss, sind immer breit.
_IMMER_BREIT = ("LaserEstop", "StopAll")


def leer() -> dict:
    """Ein Abschnitt ohne Seiten."""
    return {"version": VERSION, "seiten": []}


def ist_leer(abschnitt) -> bool:
    return not (isinstance(abschnitt, dict) and abschnitt.get("seiten"))


def _ganzzahl(wert, standard=None):
    # ``bool`` ist in Python ein ``int`` — ein ``true`` in der Datei ist aber
    # keine Zellennummer.
    if isinstance(wert, bool):
        return standard
    if isinstance(wert, int):
        return wert
    if isinstance(wert, float) and wert == int(wert):
        return int(wert)
    return standard


def _name(roh, nummer: int) -> str:
    text = str(roh).strip() if isinstance(roh, str) else ""
    text = " ".join(text.split())
    return text[:MAX_NAME] if text else f"Seite {nummer}"


def _zellen(e: dict):
    for z in range(e["zeile"], e["zeile"] + e["hoehe"]):
        for s in range(e["spalte"], e["spalte"] + e["breite"]):
            yield (s, z)


def normalisiere(roh, vorhandene_kennungen=None) -> dict:
    """Macht aus beliebigem Inhalt einen gueltigen Abschnitt. Wirft nicht.

    Verworfen wird, was nicht passt: Eintraege ohne gueltige Kennung, ausserhalb
    des Rasters, ueberlappend (der erste gewinnt), ein Widget zum zweiten Mal
    auf derselben Seite — und, wenn ``vorhandene_kennungen`` angegeben ist,
    VERWAISTE Verknuepfungen (das Widget gibt es nicht mehr).

    Das Raster ist in Version 1 fest 4 x 10; andere Werte in der Datei werden
    auf dieses Raster gelesen.
    """
    if not isinstance(roh, dict):
        return leer()
    vorhanden = None if vorhandene_kennungen is None else set(vorhandene_kennungen)
    seiten = []
    roh_seiten = roh.get("seiten")
    for sd in (roh_seiten if isinstance(roh_seiten, list) else []):
        if len(seiten) >= MAX_SEITEN:
            break
        if not isinstance(sd, dict):
            continue
        belegt: set = set()
        gesehen: set = set()
        eintraege = []
        roh_eintraege = sd.get("eintraege")
        for ed in (roh_eintraege if isinstance(roh_eintraege, list) else []):
            if not isinstance(ed, dict):
                continue
            kennung = ed.get("widget")
            if not (isinstance(kennung, str) and _KENNUNG_MUSTER.match(kennung)):
                continue
            if kennung in gesehen:
                continue
            if vorhanden is not None and kennung not in vorhanden:
                continue
            e = {"widget": kennung,
                 "spalte": _ganzzahl(ed.get("spalte")),
                 "zeile": _ganzzahl(ed.get("zeile")),
                 "breite": _ganzzahl(ed.get("breite"), 1),
                 "hoehe": _ganzzahl(ed.get("hoehe"), 1)}
            if e["spalte"] is None or e["zeile"] is None:
                continue
            if e["breite"] < 1 or e["hoehe"] < 1 or e["spalte"] < 0 or e["zeile"] < 0:
                continue
            if e["spalte"] + e["breite"] > SPALTEN or e["zeile"] + e["hoehe"] > ZEILEN:
                continue
            zellen = set(_zellen(e))
            if zellen & belegt:
                continue
            belegt |= zellen
            gesehen.add(kennung)
            eintraege.append(e)
        seiten.append({"name": _name(sd.get("name"), len(seiten) + 1),
                       "spalten": SPALTEN, "zeilen": ZEILEN,
                       "eintraege": eintraege})
    return {"version": VERSION, "seiten": seiten}


def freigegebene_kennungen(abschnitt) -> set:
    """Kennungen aller Widgets, die auf irgendeiner Handy-Seite liegen."""
    out: set = set()
    if not isinstance(abschnitt, dict):
        return out
    for seite in abschnitt.get("seiten") or []:
        for e in (seite.get("eintraege") or []) if isinstance(seite, dict) else []:
            k = e.get("widget") if isinstance(e, dict) else None
            if isinstance(k, str):
                out.add(k)
    return out


def anzahl_eintraege(abschnitt) -> int:
    if not isinstance(abschnitt, dict):
        return 0
    return sum(len(s.get("eintraege") or []) for s in abschnitt.get("seiten") or []
               if isinstance(s, dict))


# ── Bearbeiten (fuer den Editor, WEB-10) ─────────────────────────────────────
#
# Alle Funktionen liefern einen neuen Abschnitt — oder None, wenn die Aenderung
# nicht moeglich ist (Seite fehlt, Platz belegt, ausserhalb des Rasters).

def _kopie(abschnitt) -> dict:
    return copy.deepcopy(normalisiere(abschnitt))


def seite_hinzufuegen(abschnitt, name=None) -> dict | None:
    neu = _kopie(abschnitt)
    if len(neu["seiten"]) >= MAX_SEITEN:
        return None
    neu["seiten"].append({"name": _name(name, len(neu["seiten"]) + 1),
                          "spalten": SPALTEN, "zeilen": ZEILEN, "eintraege": []})
    return neu


def seite_entfernen(abschnitt, seite: int) -> dict | None:
    neu = _kopie(abschnitt)
    if not (isinstance(seite, int) and 0 <= seite < len(neu["seiten"])):
        return None
    del neu["seiten"][seite]
    return neu


def seite_umbenennen(abschnitt, seite: int, name) -> dict | None:
    neu = _kopie(abschnitt)
    if not (isinstance(seite, int) and 0 <= seite < len(neu["seiten"])):
        return None
    neu["seiten"][seite]["name"] = _name(name, seite + 1)
    return neu


def passt(abschnitt, seite: int, spalte: int, zeile: int, breite: int = 1,
          hoehe: int = 1, ausser=None) -> bool:
    """Ist das Rechteck auf der Seite frei? ``ausser`` = Kennung eines Eintrags,
    der dabei nicht zaehlt (er wird gerade verschoben)."""
    a = normalisiere(abschnitt)
    if not (isinstance(seite, int) and 0 <= seite < len(a["seiten"])):
        return False
    werte = [_ganzzahl(v) for v in (spalte, zeile, breite, hoehe)]
    if any(v is None for v in werte):
        return False
    spalte, zeile, breite, hoehe = werte
    if breite < 1 or hoehe < 1 or spalte < 0 or zeile < 0:
        return False
    if spalte + breite > SPALTEN or zeile + hoehe > ZEILEN:
        return False
    ziel = set(_zellen({"spalte": spalte, "zeile": zeile,
                        "breite": breite, "hoehe": hoehe}))
    for e in a["seiten"][seite]["eintraege"]:
        if e["widget"] == ausser:
            continue
        if ziel & set(_zellen(e)):
            return False
    return True


def freie_stelle(abschnitt, seite: int, breite: int = 1, hoehe: int = 1,
                 gesperrte_zeilen=(), ab_zeile: int = 0) -> tuple | None:
    """Erste freie Stelle (spalte, zeile) fuer ein Rechteck, zeilenweise von
    oben links (ab ``ab_zeile``) gesucht — oder None."""
    a = normalisiere(abschnitt)
    if not (isinstance(seite, int) and 0 <= seite < len(a["seiten"])):
        return None
    belegt: set = set()
    for e in a["seiten"][seite]["eintraege"]:
        belegt |= set(_zellen(e))
    gesperrt = set(gesperrte_zeilen)
    for z in range(max(0, int(ab_zeile)), ZEILEN - hoehe + 1):
        if any((z + dz) in gesperrt for dz in range(hoehe)):
            continue
        for s in range(0, SPALTEN - breite + 1):
            ziel = {(s + ds, z + dz) for ds in range(breite) for dz in range(hoehe)}
            if not (ziel & belegt):
                return (s, z)
    return None


def eintrag_setzen(abschnitt, seite: int, kennung: str, spalte: int, zeile: int,
                   breite: int = 1, hoehe: int = 1) -> dict | None:
    """Legt ein Widget auf die Seite — oder verschiebt/vergroessert es, wenn es
    dort schon liegt. None, wenn der Platz nicht frei ist."""
    if not (isinstance(kennung, str) and _KENNUNG_MUSTER.match(kennung)):
        return None
    if not passt(abschnitt, seite, spalte, zeile, breite, hoehe, ausser=kennung):
        return None
    neu = _kopie(abschnitt)
    eintraege = [e for e in neu["seiten"][seite]["eintraege"]
                 if e["widget"] != kennung]
    eintraege.append({"widget": kennung, "spalte": int(spalte), "zeile": int(zeile),
                      "breite": int(breite), "hoehe": int(hoehe)})
    eintraege.sort(key=lambda e: (e["zeile"], e["spalte"]))
    neu["seiten"][seite]["eintraege"] = eintraege
    return neu


def eintrag_entfernen(abschnitt, seite: int, kennung: str) -> dict | None:
    neu = _kopie(abschnitt)
    if not (isinstance(seite, int) and 0 <= seite < len(neu["seiten"])):
        return None
    vorher = neu["seiten"][seite]["eintraege"]
    nachher = [e for e in vorher if e["widget"] != kennung]
    if len(nachher) == len(vorher):
        return None
    neu["seiten"][seite]["eintraege"] = nachher
    return neu


# ── Automatisch fuellen ──────────────────────────────────────────────────────

def standard_groesse(auskunft: dict) -> tuple:
    """(Breite, Hoehe) in Zellen fuer ein Widget — aus seiner Fernbedien-
    Auskunft (``vc_fernbedienung.beschreibe``)."""
    typ = auskunft.get("typ")
    if typ == "fader":
        return GROESSE_FADER
    if typ == "cueliste":
        return GROESSE_CUELISTE
    funktion = str(auskunft.get("funktion") or "")
    if funktion == "Blackout":
        return GROESSE_BLACKOUT
    if funktion in _IMMER_BREIT:
        return GROESSE_TASTE_BREIT
    if len(str(auskunft.get("beschriftung") or "").strip()) >= _BREIT_AB_ZEICHEN:
        return GROESSE_TASTE_BREIT
    return GROESSE_TASTE


def automatisch_fuellen(auskuenfte) -> dict:
    """Ordnet alle fernbedienbaren Widgets ins Raster. Ersetzt nichts
    Bestehendes — der Aufrufer entscheidet, ob er das Ergebnis uebernimmt.

    ``auskuenfte``: Liste der Fernbedien-Auskuenfte (``id``, ``typ``,
    ``funktion``, ``beschriftung``) in der Reihenfolge der Konsole.

    Anordnung je Seite, von oben nach unten: Cuelisten (4 x 3), Tasten (1 x 1,
    lange Beschriftung und Not-Tasten 2 x 1), Fader (1 x 3, senkrecht
    nebeneinander). Blackout-Tasten liegen ueber die volle Breite UNTEN auf der
    ersten Seite — dort, wo der Daumen sie blind findet. Was nicht mehr passt,
    wandert auf die naechste Seite (hoechstens :data:`MAX_SEITEN`); innerhalb
    jeder Gruppe bleibt die Reihenfolge der Konsole erhalten.
    """
    gesehen: set = set()
    cuelisten, tasten, fader, blackout = [], [], [], []
    for a in auskuenfte or []:
        if not isinstance(a, dict):
            continue
        kennung = a.get("id")
        if not (isinstance(kennung, str) and _KENNUNG_MUSTER.match(kennung)):
            continue
        if kennung in gesehen:
            continue
        typ = a.get("typ")
        if typ == "cueliste":
            cuelisten.append(a)
        elif typ == "fader":
            fader.append(a)
        elif typ == "taste":
            (blackout if str(a.get("funktion") or "") == "Blackout" else tasten).append(a)
        else:
            continue
        gesehen.add(kennung)

    abschnitt = leer()
    # Zeilen der ersten Seite, die fuer Blackout frei bleiben (von unten).
    reserviert = {0: set()}

    def _seite(nr: int) -> None:
        nonlocal abschnitt
        while len(abschnitt["seiten"]) <= nr:
            abschnitt = seite_hinzufuegen(abschnitt)

    def _erste_leere_zeile(nr: int) -> int:
        """Erste Zeile der Seite, unter der (bis auf Blackout) nichts liegt."""
        unten = 0
        for e in abschnitt["seiten"][nr]["eintraege"]:
            if e["zeile"] in reserviert.get(nr, ()):
                continue
            unten = max(unten, e["zeile"] + e["hoehe"])
        return unten

    def _lege(a: dict, band: dict | None = None) -> None:
        """Legt das Widget auf die erste Seite, auf der es Platz hat. Mit
        ``band`` (Seite -> Startzeile) beginnt die Gruppe je Seite in einer
        eigenen Zeile: Fader stehen so nebeneinander auf gleicher Hoehe statt
        versetzt in den Luecken der Tasten."""
        nonlocal abschnitt
        breite, hoehe = standard_groesse(a)
        for nr in range(MAX_SEITEN):
            _seite(nr)
            ab_zeile = 0
            if band is not None:
                if nr not in band:
                    band[nr] = _erste_leere_zeile(nr)
                ab_zeile = band[nr]
            stelle = freie_stelle(abschnitt, nr, breite, hoehe,
                                  gesperrte_zeilen=reserviert.get(nr, ()),
                                  ab_zeile=ab_zeile)
            if stelle is not None:
                abschnitt = eintrag_setzen(abschnitt, nr, a["id"], stelle[0],
                                           stelle[1], breite, hoehe)
                return

    if cuelisten or tasten or fader or blackout:
        _seite(0)
    # Blackout zuerst festlegen: von der untersten Zeile aufwaerts.
    for i, a in enumerate(blackout):
        zeile = ZEILEN - 1 - i
        if zeile < 0:
            break
        abschnitt = eintrag_setzen(abschnitt, 0, a["id"], 0, zeile, *GROESSE_BLACKOUT)
        reserviert[0].add(zeile)

    for a in cuelisten + tasten:
        _lege(a)
    fader_band: dict = {}
    for a in fader:
        _lege(a, fader_band)

    # Leere Seiten am Ende (durch die Suche angelegt) wieder entfernen.
    while abschnitt["seiten"] and not abschnitt["seiten"][-1]["eintraege"]:
        abschnitt = seite_entfernen(abschnitt, len(abschnitt["seiten"]) - 1)
    return abschnitt
