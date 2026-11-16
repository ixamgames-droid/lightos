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

WEB-13: ein Eintrag darf zusaetzlich ``handy_farbe`` (``#rrggbb``) und
``handy_text`` tragen — eigenes Aussehen NUR am Handy. Das Original-Widget
bleibt unberuehrt. Fehlen beide (jede Show von frueher), steht auch nichts
davon in der Datei.

WEB-14: eigene Handy-Gruppen stehen unter ``gruppen`` neben den Seiten::

    "gruppen": [{"name": "Grundfarbe", "widgets": ["w1a2b3c4d5e6", ...]}, ...]

In einer Gruppe ist am Handy immer hoechstens EINE Taste aktiv (die
Fernbedienung schaltet die anderen ueber den Klick-Weg aus). Eine Kachel liegt
in hoechstens einer Gruppe; Mitglieder muessen auf einer Handy-Seite liegen.
Ohne Gruppen wird der Schluessel nicht geschrieben — alte Shows bleiben
unveraendert. Welche Tasten ueberhaupt in eine Gruppe duerfen (nie BLACKOUT,
Laser-NOT-AUS, STOP ALL, Laser scharf), entscheidet die Konsole
(``VCCanvas.handy_gruppe_erlaubt``) und die Fernbedienung bei jedem Druck neu.
"""
from __future__ import annotations

import copy
import math
import re

VERSION = 1
SCHLUESSEL = "handy_seiten"

SPALTEN = 4
ZEILEN = 10
MAX_SEITEN = 12
MAX_NAME = 24
#: WEB-13: Hoechstlaenge der eigenen Handy-Beschriftung einer Kachel.
MAX_HANDY_TEXT = 32
#: WEB-13: die beiden optionalen Felder fuer eigenes Aussehen am Handy.
AUSSEHEN_FELDER = ("handy_farbe", "handy_text")

#: WEB-14: Schluessel und Grenzen der eigenen Handy-Gruppen.
GRUPPEN = "gruppen"
MAX_GRUPPEN = 24
MAX_GRUPPE_MITGLIEDER = 40

_FARB_MUSTER = re.compile(r"^#[0-9a-fA-F]{6}$")

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
    # WEB-15: NaN/Infinity (Python-json liest sie) erst ausschliessen —
    # ``int(nan)`` wirft, und ``normalisiere`` verwarf dann ALLE Seiten.
    if isinstance(wert, float) and math.isfinite(wert) and wert.is_integer():
        return int(wert)
    return standard


def _name(roh, nummer: int) -> str:
    text = str(roh).strip() if isinstance(roh, str) else ""
    text = " ".join(text.split())
    return text[:MAX_NAME] if text else f"Seite {nummer}"


def handy_farbe_gueltig(roh) -> str | None:
    """WEB-13: ``#rrggbb`` (klein geschrieben) oder None."""
    if isinstance(roh, str) and _FARB_MUSTER.match(roh.strip()):
        return roh.strip().lower()
    return None


def handy_text_gueltig(roh) -> str | None:
    """WEB-13: bereinigte Handy-Beschriftung (Leerraum zusammengezogen,
    hoechstens :data:`MAX_HANDY_TEXT` Zeichen) oder None, wenn leer."""
    if not isinstance(roh, str):
        return None
    text = " ".join(roh.split())[:MAX_HANDY_TEXT].strip()
    return text or None


def _aussehen(ed: dict) -> dict:
    """Die gueltigen WEB-13-Felder eines Roh-Eintrags (nur vorhandene)."""
    raus = {}
    farbe = handy_farbe_gueltig(ed.get("handy_farbe"))
    if farbe is not None:
        raus["handy_farbe"] = farbe
    text = handy_text_gueltig(ed.get("handy_text"))
    if text is not None:
        raus["handy_text"] = text
    return raus


def hat_eigenes_aussehen(eintrag) -> bool:
    """WEB-13: traegt die Kachel eigene Handy-Farbe oder -Beschriftung?"""
    return isinstance(eintrag, dict) and any(eintrag.get(f) for f in AUSSEHEN_FELDER)


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
            e.update(_aussehen(ed))         # WEB-13: nur wenn vorhanden
            eintraege.append(e)
        seiten.append({"name": _name(sd.get("name"), len(seiten) + 1),
                       "spalten": SPALTEN, "zeilen": ZEILEN,
                       "eintraege": eintraege})
    raus = {"version": VERSION, "seiten": seiten}
    gruppen = _gruppen_normalisieren(roh.get(GRUPPEN), freigegebene_kennungen(raus))
    if gruppen:                         # WEB-14: nur schreiben, wenn es welche gibt
        raus[GRUPPEN] = gruppen
    return raus


def _gruppen_name(roh, nummer: int) -> str:
    text = " ".join(roh.split()) if isinstance(roh, str) else ""
    return text[:MAX_NAME] if text else f"Gruppe {nummer}"


def _gruppen_normalisieren(roh, frei: set) -> list:
    """WEB-14: gueltige Gruppen — Mitglieder nur mit gueltiger Kennung, auf
    einer Handy-Seite (``frei``) und in keiner frueheren Gruppe (die erste
    gewinnt). Gruppen ohne Mitglied fallen weg."""
    raus: list = []
    vergeben: set = set()
    for gd in (roh if isinstance(roh, list) else []):
        if len(raus) >= MAX_GRUPPEN:
            break
        if not isinstance(gd, dict):
            continue
        mitglieder = []
        roh_w = gd.get("widgets")
        for k in (roh_w if isinstance(roh_w, list) else []):
            if not (isinstance(k, str) and _KENNUNG_MUSTER.match(k)):
                continue
            if k in vergeben or k not in frei:
                continue
            if len(mitglieder) >= MAX_GRUPPE_MITGLIEDER:
                break
            vergeben.add(k)
            mitglieder.append(k)
        if mitglieder:
            raus.append({"name": _gruppen_name(gd.get("name"), len(raus) + 1),
                         "widgets": mitglieder})
    return raus


def gruppen(abschnitt) -> list:
    """WEB-14: die (bereinigten) Handy-Gruppen als Kopie."""
    return copy.deepcopy(normalisiere(abschnitt).get(GRUPPEN, []))


def gruppe_von(abschnitt, kennung) -> int | None:
    """WEB-14: Nummer der Handy-Gruppe, in der ``kennung`` liegt, oder None."""
    for nr, g in enumerate(gruppen(abschnitt)):
        if kennung in g["widgets"]:
            return nr
    return None


def _mit_gruppen(abschnitt: dict, liste: list) -> dict:
    neu = copy.deepcopy(abschnitt)
    neu.pop(GRUPPEN, None)
    if liste:
        neu[GRUPPEN] = liste
    return normalisiere(neu)


def gruppe_setzen(abschnitt, nr, name, kennungen) -> dict | None:
    """WEB-14: Handy-Gruppe ``nr`` neu fassen (``nr`` = None: neue Gruppe am
    Ende). Kennungen, die schon in einer ANDEREN Gruppe liegen, wandern in
    diese (eine Kachel ist nur in einer Gruppe). Ohne gueltiges Mitglied wird
    die Gruppe entfernt. None, wenn ``nr`` nicht passt oder schon
    :data:`MAX_GRUPPEN` Gruppen bestehen."""
    a = normalisiere(abschnitt)
    liste = copy.deepcopy(a.get(GRUPPEN, []))
    frei = freigegebene_kennungen(a)
    mitglieder = []
    for k in (kennungen if isinstance(kennungen, (list, tuple)) else []):
        if isinstance(k, str) and k in frei and k not in mitglieder:
            mitglieder.append(k)
    if nr is None:
        if len(liste) >= MAX_GRUPPEN:
            return None
        nummer = len(liste) + 1
    elif isinstance(nr, int) and not isinstance(nr, bool) and 0 <= nr < len(liste):
        nummer = nr + 1
    else:
        return None
    for i, g in enumerate(liste):
        if i != nr:
            g["widgets"] = [k for k in g["widgets"] if k not in mitglieder]
    gruppe = {"name": _gruppen_name(name, nummer), "widgets": mitglieder}
    if nr is None:
        liste.append(gruppe)
    else:
        liste[nr] = gruppe
    return _mit_gruppen(a, [g for g in liste if g["widgets"]])


def gruppe_entfernen(abschnitt, nr) -> dict | None:
    """WEB-14: Handy-Gruppe ``nr`` aufloesen (die Kacheln bleiben liegen)."""
    a = normalisiere(abschnitt)
    liste = copy.deepcopy(a.get(GRUPPEN, []))
    if not (isinstance(nr, int) and not isinstance(nr, bool) and 0 <= nr < len(liste)):
        return None
    del liste[nr]
    return _mit_gruppen(a, liste)


def aus_gruppe_nehmen(abschnitt, kennung) -> dict | None:
    """WEB-14: ``kennung`` aus ihrer Handy-Gruppe nehmen (None: in keiner)."""
    a = normalisiere(abschnitt)
    liste = copy.deepcopy(a.get(GRUPPEN, []))
    for g in liste:
        if kennung in g["widgets"]:
            g["widgets"].remove(kennung)
            return _mit_gruppen(a, [g for g in liste if g["widgets"]])
    return None


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
    alt = [e for e in neu["seiten"][seite]["eintraege"] if e["widget"] == kennung]
    eintraege = [e for e in neu["seiten"][seite]["eintraege"]
                 if e["widget"] != kennung]
    e = {"widget": kennung, "spalte": int(spalte), "zeile": int(zeile),
         "breite": int(breite), "hoehe": int(hoehe)}
    if alt:
        e.update(_aussehen(alt[0]))     # WEB-13: Verschieben behaelt das Aussehen
    eintraege.append(e)
    eintraege.sort(key=lambda e: (e["zeile"], e["spalte"]))
    neu["seiten"][seite]["eintraege"] = eintraege
    return neu


def eintrag_aussehen(abschnitt, seite: int, kennung, farbe=None,
                     text=None) -> dict | None:
    """WEB-13: eigene Handy-Farbe/-Beschriftung einer Kachel setzen.

    ``farbe``/``text`` = None (oder ungueltig/leer) heisst „wie Original“ —
    das Feld wird dann entfernt. Gesetzt werden immer BEIDE: wer nur eines
    aendern will, gibt das andere aus :func:`eintrag` mit. None, wenn die
    Kachel nicht auf der Seite liegt."""
    neu = _kopie(abschnitt)
    if not (isinstance(seite, int) and 0 <= seite < len(neu["seiten"])):
        return None
    for e in neu["seiten"][seite]["eintraege"]:
        if e["widget"] != kennung:
            continue
        for feld in AUSSEHEN_FELDER:
            e.pop(feld, None)
        e.update(_aussehen({"handy_farbe": farbe, "handy_text": text}))
        return neu
    return None


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


def seite_verschieben(abschnitt, von: int, nach: int) -> dict | None:
    """Reihenfolge der Seiten aendern: Seite ``von`` steht danach an Stelle
    ``nach``. Namen und Inhalt wandern mit."""
    neu = _kopie(abschnitt)
    n = len(neu["seiten"])
    if not (isinstance(von, int) and isinstance(nach, int)
            and 0 <= von < n and 0 <= nach < n):
        return None
    neu["seiten"].insert(nach, neu["seiten"].pop(von))
    return neu


def seiten_ordnen(abschnitt, reihenfolge) -> dict | None:
    """Seiten in neuer Reihenfolge: ``reihenfolge[i]`` ist die bisherige Nummer
    der Seite, die danach an Stelle i steht. None, wenn die Liste nicht jede
    Seite genau einmal nennt."""
    neu = _kopie(abschnitt)
    n = len(neu["seiten"])
    folge = list(reihenfolge) if isinstance(reihenfolge, (list, tuple)) else None
    if folge is None or any(isinstance(v, bool) or not isinstance(v, int) for v in folge) \
            or sorted(folge) != list(range(n)):
        return None
    neu["seiten"] = [neu["seiten"][i] for i in folge]
    return neu


def seiten_mit(abschnitt, kennung) -> list:
    """Nummern der Seiten, auf denen ``kennung`` liegt."""
    a = normalisiere(abschnitt)
    return [nr for nr, seite in enumerate(a["seiten"])
            if any(e["widget"] == kennung for e in seite["eintraege"])]


def eintrag(abschnitt, seite: int, kennung) -> dict | None:
    """Der Eintrag von ``kennung`` auf der Seite (Kopie) oder None."""
    a = normalisiere(abschnitt)
    if not (isinstance(seite, int) and 0 <= seite < len(a["seiten"])):
        return None
    for e in a["seiten"][seite]["eintraege"]:
        if e["widget"] == kennung:
            return dict(e)
    return None


def freie_zellen(abschnitt, seite: int) -> int:
    a = normalisiere(abschnitt)
    if not (isinstance(seite, int) and 0 <= seite < len(a["seiten"])):
        return 0
    belegt = sum(e["breite"] * e["hoehe"] for e in a["seiten"][seite]["eintraege"])
    return SPALTEN * ZEILEN - belegt


# ── Groessen je Art (WEB-10) ─────────────────────────────────────────────────
#
# Was die Handy-Ansicht (``konsole.html``) sinnvoll darstellen kann:
#   Taste     1 x 1 … 4 x 2
#   Fader     senkrecht 1 x 2 … 1 x 5  ODER  waagerecht 2 x 1 … 4 x 1
#             (die Ansicht legt einen Fader quer, sobald er breiter als hoch ist)
#   Cueliste  4 x 2 … 4 x 4 (immer volle Breite: Anzeige + GO/BACK/STOP)

def groesse_begrenzen(typ, breite, hoehe) -> tuple:
    """Die naechste erlaubte Groesse (Breite, Hoehe) fuer ein Element der Art
    ``typ`` ('taste' | 'fader' | 'cueliste')."""
    b = _ganzzahl(breite, 1)
    h = _ganzzahl(hoehe, 1)
    if typ == "fader":
        if b >= 2 and h <= 1:                       # quer
            return (max(2, min(SPALTEN, b)), 1)
        return (1, max(2, min(5, h)))               # senkrecht
    if typ == "cueliste":
        return (SPALTEN, max(2, min(4, h)))
    return (max(1, min(SPALTEN, b)), max(1, min(2, h)))


def groesse_erlaubt(typ, breite, hoehe) -> bool:
    return (breite, hoehe) == groesse_begrenzen(typ, breite, hoehe)


def naechster_platz(abschnitt, kennung, breite: int, hoehe: int,
                    ab_seite: int = 0):
    """Wohin ein neues Element kommt: der erste freie Platz der Seite
    ``ab_seite``, sonst der einer folgenden Seite, sonst eine neue Seite.

    Rueckgabe ``(abschnitt, seite, spalte, zeile)`` — der Abschnitt ist um
    eine Seite gewachsen, wenn eine neue noetig war — oder None, wenn nirgends
    Platz ist und es schon :data:`MAX_SEITEN` Seiten gibt. Seiten, auf denen
    das Element schon liegt, werden uebersprungen (je Seite hoechstens einmal).
    """
    a = normalisiere(abschnitt)
    start = max(0, _ganzzahl(ab_seite, 0) or 0)
    for nr in range(start, len(a["seiten"])):
        if any(e["widget"] == kennung for e in a["seiten"][nr]["eintraege"]):
            continue
        stelle = freie_stelle(a, nr, breite, hoehe)
        if stelle is not None:
            return (a, nr, stelle[0], stelle[1])
    gewachsen = seite_hinzufuegen(a)
    if gewachsen is None:
        return None
    nr = len(gewachsen["seiten"]) - 1
    stelle = freie_stelle(gewachsen, nr, breite, hoehe)
    if stelle is None:
        return None
    return (gewachsen, nr, stelle[0], stelle[1])


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
