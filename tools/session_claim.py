#!/usr/bin/env python3
"""session_claim.py — Belegzettel fuer parallel arbeitende Claude-Sitzungen.

Seit dem 2026-08-06 arbeiten mehrere Claude-Instanzen gleichzeitig an LightOS.
Sie sehen einander **nur ueber dieses Repo**. Die Regel, aus der alles folgt:

    Was nicht gepusht ist, existiert fuer die andere Sitzung nicht.

Dieses Werkzeug pflegt die Tafel ``SESSIONS.md`` und macht daraus einen
belastbaren Beleg statt einer Absichtserklaerung.

★ **Wo die Tafel liegt (PROC-25, seit 2026-10-25):** in einem eigenen,
PRIVATEN Repo ``ixamgames-droid/lightos-intern`` (Branch ``main``), nicht mehr
auf dem Branch ``sessions`` des oeffentlichen Repos. Das Werkzeug arbeitet auf
einem lokalen Klon davon:

* ``LIGHTOS_TAFEL_REPO=<pfad>`` (oder ``--tafel <pfad>``) — sonst die Vorgabe
  ``<Projektordner>/lightos-intern``, also neben ``repo/`` bzw. den Worktrees.
* Fehlt der Klon, bricht jeder Befehl mit Exit 3 und dem Einrichtungsbefehl
  ``gh repo clone ixamgames-droid/lightos-intern <pfad>`` ab — es gibt
  bewusst KEINEN stillen Rueckfall auf ``origin/sessions``.
* ``LIGHTOS_TAFEL=alt`` nimmt fuer den Uebergangstag noch einmal den alten
  Branch ``sessions`` (mit Warnung). Nach ``umzug`` schreibt er dort nichts mehr.
* Vor JEDEM Schreiben auf die Tafel sperrt :func:`pruefe_zugangsdaten`
  Token-, Kennwort- und Schluessel-Muster. Klarnamen sind im privaten Repo
  erlaubt; :func:`pruefe_oeffentlich` gilt nur noch fuer Texte, die ins
  oeffentliche Repo gehen (``LIGHTOS_TAFEL=alt``, Hinweis-Commit von ``umzug``).

★ **Der Kern ist nicht die Datei, sondern der Push.** Zwei Sitzungen, die im
selben Moment dasselbe Item nehmen wollen, lesen beide „frei" — die Pruefung
allein entscheidet also gar nichts. Entschieden wird es erst dadurch, dass
genau **ein** Push als Fast-Forward durchgeht; der zweite wird von Git
abgelehnt, das Werkzeug liest neu und meldet dann ehrlich „belegt". Deshalb
wird hier mit Git-Plumbing (``hash-object`` / ``mktree`` / ``commit-tree``)
gearbeitet und der Commit gegen genau den Stand gesetzt, den wir gelesen
haben: waere der Push ein ``--force`` oder wuerde er automatisch rebasen,
gaebe es kein Rennen zu verlieren — und damit auch keine Erkennung.

Der Arbeitsbaum wird dabei **nicht angefasst**: kein Checkout, kein Wechsel des
Branches, kein Eingriff in einen laufenden Worktree der anderen Sitzung.

Aufrufe::

    python tools/session_claim.py list
    python tools/session_claim.py claim OUT-51 --session B \\
        --branch fix/out51-sendefehler --files src/core/dmx/output_manager.py
    python tools/session_claim.py claim QA-50 --session B --strikt \\
        --files src/core/dmx/            # Ordner: alles darunter (PROC-16)
    python tools/session_claim.py refresh OUT-51 --session B
    python tools/session_claim.py release OUT-51 --session B --status done
    python tools/session_claim.py blocker "Rig haengt am Enttec — nicht neu starten" \\
        --session A
    python tools/session_claim.py blocker --session A --datei - <<'EOF'
    AN B: bitte `app_state.py` erst nach meinem Merge anfassen
    EOF
    python tools/session_claim.py list --fuer B   # Briefe an B (PROC-17)
    python tools/session_claim.py entscheidung add "Rig umbauen?" --session A
    python tools/session_claim.py entscheidung list
    python tools/session_claim.py entscheidung done E-3 --session A --notiz "ja"
    python tools/session_claim.py umzug --session A --trocken   # PROC-25, einmalig

Windows PowerShell 5.1: ``… | python … --datei -`` kodiert die Pipe nach
``$OutputEncoding`` (Vorgabe US-ASCII) — Umlaute kommen still als ``?`` an.
Dort den Dateiweg nehmen (``--datei brief.txt``, Datei als UTF-8 speichern)
oder vorher ``$OutputEncoding = [Text.UTF8Encoding]::new()`` setzen.

Regeln stehen in ``COORDINATION.md``.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

#: PROC-25: Branch der Tafel im privaten Tafel-Repo.
BRANCH = "main"
#: Bis PROC-25: Branch der Tafel im OEFFENTLICHEN Code-Repo (nur noch
#: ``LIGHTOS_TAFEL=alt`` und ``umzug`` lesen ihn).
BRANCH_ALT = "sessions"
DATEI = "SESSIONS.md"
DATEI_ENTSCHEIDUNGEN = "ENTSCHEIDUNGEN.md"
#: Ordnername des Klons neben ``repo/`` und das Repo auf GitHub (privat).
TAFEL_ORDNER = "lightos-intern"
TAFEL_GITHUB = "ixamgames-droid/lightos-intern"
#: Steht im Hinweis, den ``umzug`` auf ``origin/sessions`` hinterlaesst — daran
#: erkennt ein zweiter Lauf (und ``LIGHTOS_TAFEL=alt``) den erledigten Umzug.
UMZUG_MARKE = "umgezogen nach lightos-intern (privat)"

# Ein Claim verfaellt, wenn die Sitzung ihn nicht auffrischt. Vier Stunden sind
# lang genug fuer ein grosses Item samt vollem Gate (~15 min) und kurz genug,
# dass eine abgestuerzte Sitzung das Item nicht ueber Nacht blockiert.
VERFALL = timedelta(hours=4)

_KOPF = """# SESSIONS.md — wer arbeitet gerade woran

<!-- Gepflegt von tools/session_claim.py. Privates Tafel-Repo lightos-intern,
     Branch main (bis PROC-25: Branch `sessions` des oeffentlichen Repos).
     Von Hand editieren ist moeglich, verliert aber die Konflikt-
     erkennung: erst der abgelehnte Push macht sichtbar, dass jemand schneller
     war. Spielregeln: COORDINATION.md. Zugangsdaten NIE hierher.
     PROC-08: Blocker verfallen beim naechsten Schreiben nach 7 Tagen — nicht
     aber ungelesene Briefe und der letzte Eintrag jeder Sitzung. Volltext
     aelterer Eintraege: git log -p origin/main -- SESSIONS.md (im Klon
     lightos-intern; vor dem Umzug: git log -p origin/sessions -- SESSIONS.md) -->
"""

_H_AKTIV = "## Aktive Claims"
_H_BLOCKER = "## Blocker & Fallen"
_H_VERLAUF = "## Verlauf"

_TABELLENKOPF = ("| Item | Sitzung | Branch | seit (UTC) | Dateien |\n"
                 "|---|---|---|---|---|\n")

_VERLAUF_MAX = 30


# ─────────────────────────────────────────────────────────────────────────────
# Reine Logik — ohne Git, damit sie pruefbar ist
# ─────────────────────────────────────────────────────────────────────────────

def jetzt() -> datetime:
    return datetime.now(timezone.utc)


def stempel(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%MZ")


def lies_stempel(text: str) -> datetime | None:
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%dT%H:%MZ").replace(
            tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


def parse(inhalt: str) -> dict:
    """``SESSIONS.md`` -> ``{"claims": [...], "blocker": [...], "verlauf": [...]}``.

    Bewusst nachsichtig: eine kaputte Zeile darf die Tafel nicht unlesbar
    machen — sonst waere ein Tippfehler von Hand ein Totalausfall der
    Koordination fuer alle Sitzungen.
    """
    claims, blocker, verlauf = [], [], []
    abschnitt = None
    for zeile in inhalt.splitlines():
        if zeile.startswith("## "):
            abschnitt = zeile.strip()
            continue
        if abschnitt == _H_AKTIV and zeile.startswith("|"):
            spalten = [s.strip() for s in zeile.strip().strip("|").split("|")]
            if len(spalten) < 4 or spalten[0].lower() in ("item", ""):
                continue
            if set(spalten[0]) <= {"-", ":"}:            # Trennzeile
                continue
            # Die Platzhalterzeile der leeren Tafel (`_(frei)_`) ist Darstellung,
            # kein Claim. Ohne diese Zeile las sich eine leere Tafel als „ein
            # Item namens _(frei)_ ist belegt" — vom Test gefangen.
            if spalten[0].startswith("_"):
                continue
            claims.append({
                "item": spalten[0],
                "sitzung": spalten[1],
                "branch": spalten[2],
                "seit": spalten[3],
                "dateien": spalten[4] if len(spalten) > 4 else "",
            })
        elif abschnitt == _H_BLOCKER and zeile.startswith("- "):
            blocker.append(zeile[2:].rstrip())
        elif abschnitt == _H_VERLAUF and zeile.startswith("- "):
            verlauf.append(zeile[2:].rstrip())
    return {"claims": claims, "blocker": blocker, "verlauf": verlauf}


def rendere(tafel: dict) -> str:
    teile = [_KOPF, "\n", _H_AKTIV, "\n\n", _TABELLENKOPF]
    for c in tafel["claims"]:
        teile.append("| {item} | {sitzung} | {branch} | {seit} | {dateien} |\n"
                     .format(**c))
    if not tafel["claims"]:
        teile.append("| _(frei)_ |  |  |  |  |\n")
    teile.append("\n" + _H_BLOCKER + "\n\n")
    if tafel["blocker"]:
        teile += [f"- {b}\n" for b in tafel["blocker"]]
    else:
        teile.append("_(nichts gemeldet)_\n")
    teile.append("\n" + _H_VERLAUF + "\n\n")
    for v in tafel["verlauf"][-_VERLAUF_MAX:]:
        teile.append(f"- {v}\n")
    return "".join(teile)


# ─── PROC-16: Dateiueberschneidung beim Claim ────────────────────────────────
# Bis 2026-10-01 hat `claim` die Liste aus `--files` nur GESPEICHERT. Verglichen
# wurde nichts — COORDINATION.md fuehrte Fall 4 („beide aendern dieselbe Datei
# aus verschiedenen Items") deshalb ehrlich als „nur sichtbar gemacht". Sichtbar
# hiess: die andere Sitzung haette die Tafel lesen UND die Spalte selbst gegen
# die eigene Liste halten muessen. Das tut niemand zuverlaessig, also tut es
# jetzt das Werkzeug — vor dem Schreiben, gegen den frisch geholten Stand.

def normalisiere_pfad(pfad: str) -> str:
    """Repo-Pfad vergleichbar machen: Trenner, ``./``, Endschraegstrich, Gross-
    und Kleinschreibung.

    ``\\`` und ``/`` gelten als gleich — eine Windows-Sitzung schreibt
    ``src\\core\\x.py``, die Linux-Sitzung ``src/core/x.py``, gemeint ist
    dieselbe Datei. Gross/klein wird bewusst ignoriert: auf Windows (und macOS)
    IST es dieselbe Datei, und eine Warnung zu viel kostet weniger als eine
    verschwiegene Ueberschneidung.
    """
    p = pfad.strip().replace("\\", "/")
    while "//" in p:
        p = p.replace("//", "/")
    teile = [t for t in p.split("/") if t not in ("", ".")]
    return "/".join(teile).casefold()


def _dateien_der_tafel(spalte: str) -> list[str]:
    """Die Dateien-Spalte (``a · b`` oder ``-``) zurueck in eine Liste."""
    return [d.strip() for d in (spalte or "").split("·")
            if d.strip() and d.strip() != "-"]


def pfade_ueberlappen(a: str, b: str) -> bool:
    """Gleiche Datei, oder einer ist ein Ordner, in dem der andere liegt.

    Verglichen wird nach ganzen Pfadteilen: ``src/core`` umfasst
    ``src/core/x.py``, aber NICHT ``src/core_alt.py``. Ein leerer Pfad
    (``.`` oder ``./``) steht fuer das ganze Repo und ueberlappt mit allem.
    """
    na, nb = normalisiere_pfad(a), normalisiere_pfad(b)
    if not na or not nb:
        return True
    return na == nb or nb.startswith(na + "/") or na.startswith(nb + "/")


def ueberschneidungen(tafel: dict, sitzung: str, item: str,
                      dateien: list[str], t: datetime) -> list[tuple[dict, list[str]]]:
    """Nicht verfallene Claims ANDERER Items, die eine der ``dateien`` beruehren.

    Rueckgabe: ``[(claim, [beruehrte Pfade des anderen Claims]), ...]``.
    Ausgenommen ist nur das identische Item (ein Claim ueberschneidet sich
    nicht mit sich selbst) und verfallene Claims — ein Claim, den niemand mehr
    auffrischt, darf keine Warnung mehr erzeugen, sonst lernt man, sie zu
    uebergehen.

    ★ Claims anderer Items DERSELBEN Sitzung zaehlen mit. Bis 2026-10-01 stand
    hier „eigene Claims nicht mitzaehlen, dieselbe Sitzung arbeitet ohnehin
    nacheinander" — das stimmt nicht: die leitende Sitzung laesst mehrere
    Worktree-Agenten parallel unter DERSELBEN Kennung arbeiten. Genau dort
    entsteht der haeufigste reale Konflikt, und er blieb stumm. Ob ein Treffer
    fremd oder eigen ist, entscheidet erst die Meldung (``c["sitzung"]``).
    """
    eigene = [d for d in dateien if d.strip() and d.strip() != "-"]
    if not eigene:
        return []
    treffer = []
    for c in tafel["claims"]:
        if c.get("item", "").upper() == item.upper():
            continue
        if ist_verfallen(c, t):
            continue
        beruehrt = [f for f in _dateien_der_tafel(c.get("dateien", ""))
                    if any(pfade_ueberlappen(f, e) for e in eigene)]
        if beruehrt:
            treffer.append((c, beruehrt))
    return treffer


# ─── PROC-17: Briefe auf der Tafel ──────────────────────────────────────────
# Die Blockerliste ist auch der Briefkasten zwischen den Sitzungen („AN B: …").
# Bei 228 KB Tafel wurden solche Fragen schlicht ueberlesen: `list` zeigt
# bewusst nur die juengsten fuenf (PROC-07), und alles davor ist fuer die
# angesprochene Sitzung verloren, wenn sie es nicht gezielt sucht.

# Ein Blocker-Eintrag beginnt mit Stempel und Sitzung: ``2026-10-01T08:00Z (B) …``
_BLOCKER_KOPF = re.compile(r"^\S+\s+\(([^)]+)\)\s")
# Anrede: ``AN B``, ``AN A UND B``, ``AN A, B UND C``, ``AN ALLE``. Bewusst nur
# GROSS geschrieben — „an" ist im Fliesstext ein gewoehnliches Wort.
_ANREDE = re.compile(r"\bAN\s+(ALLE\b|[A-Z]\b(?:\s*(?:,|UND)\s*[A-Z]\b)*)")

#: Ab dieser Laenge wird ein Blocker-Text angemahnt (nicht abgelehnt).
BLOCKER_LANG = 300


def blocker_sitzung(eintrag: str) -> str | None:
    """Die Sitzung, die den Eintrag geschrieben hat (``None`` = unlesbar)."""
    m = _BLOCKER_KOPF.match(eintrag)
    return m.group(1).strip() if m else None


def ist_an(eintrag: str, sitzung: str) -> bool:
    """Spricht der Eintrag ``sitzung`` an (``AN X`` / ``AN … UND X`` / ``AN ALLE``)?"""
    ziel = sitzung.strip().upper()
    for m in _ANREDE.finditer(eintrag):
        gruppe = m.group(1)
        if gruppe == "ALLE":
            return True
        if ziel in re.findall(r"\b[A-Z]\b", gruppe):
            return True
    return False


def blocker_fuer(blocker: list[str], sitzung: str) -> list[str]:
    """Alle Eintraege an ``sitzung`` NACH ihrem letzten eigenen Eintrag.

    Ohne Altersgrenze: eine Frage von vor drei Tagen ist genau dann noch
    offen, wenn die Sitzung seitdem nichts geschrieben hat. Hat sie noch nie
    etwas geschrieben, zaehlt die ganze Liste.
    """
    ziel = sitzung.strip().upper()
    start = 0
    for i, b in enumerate(blocker):
        if (blocker_sitzung(b) or "").upper() == ziel:
            start = i + 1
    return [b for b in blocker[start:] if ist_an(b, ziel)]


# ─── PROC-08: Blocker verfallen ──────────────────────────────────────────────
# PROC-07 hat die LESE-Seite gekuerzt (`list --blocker N`), geschrieben wurde
# aber unbegrenzt: am 2026-10-01 stand die Tafel bei 144 Blockern / 253 kB,
# allein an diesem Tag kamen 30 dazu. Jeder `claim` holt und schreibt die ganze
# Datei. Der Verlauf daneben hat mit `_VERLAUF_MAX` laengst eine Grenze.
#
# Bewusst ein Alter statt einer festen Anzahl: an einem vollen Tag fielen sonst
# die Uebergaben vom Vortag heraus. Und drei Ausnahmen, damit nichts verloren
# geht, was noch jemand braucht:
#   * ein Brief, den ein Adressat noch NICHT gelesen hat (`blocker_offen`),
#   * der letzte Eintrag jeder Sitzung — er ist die Lesemarke von
#     `blocker_fuer`; faellt er weg, tauchen schon gelesene Briefe wieder auf,
#   * ein Eintrag ohne lesbaren Zeitstempel (von Hand geschrieben) — was man
#     nicht datieren kann, wird nicht weggeworfen.
# Verfallene Eintraege stehen weiter in der Git-Historie der Tafel.

#: Ab diesem Alter faellt ein Blocker beim naechsten Schreiben von der Tafel.
BLOCKER_VERFALL = timedelta(days=7)


def blocker_offen(blocker: list[str], i: int, sitzungen=()) -> bool:
    """Ist Eintrag ``i`` ein Brief, den ein Adressat noch nicht gelesen hat?

    „Gelesen" heisst wie bei :func:`blocker_fuer`: der Adressat hat NACH dem
    Brief selbst einen Blocker geschrieben. ``AN ALLE`` ist offen, solange
    irgendeine andere bekannte Sitzung seitdem schweigt — bekannt aus den
    Blockern UND aus ``sitzungen`` (Claims, Verlauf): eine Sitzung, die nur
    belegt und freigibt, aber nie einen Blocker schreibt, liest ``list --fuer``
    genauso (Review-Fund zu PROC-08).
    """
    eintrag = blocker[i]
    autor = (blocker_sitzung(eintrag) or "").upper()
    spaeter = {(blocker_sitzung(b) or "").upper() for b in blocker[i + 1:]}
    adressaten: set[str] = set()
    for m in _ANREDE.finditer(eintrag):
        gruppe = m.group(1)
        if gruppe == "ALLE":
            adressaten |= {(blocker_sitzung(b) or "").upper() for b in blocker}
            adressaten |= {str(s).strip().upper() for s in sitzungen}
        else:
            adressaten |= set(re.findall(r"\b[A-Z]\b", gruppe))
    adressaten -= {autor, ""}
    return any(a not in spaeter for a in adressaten)


def tafel_sitzungen(tafel: dict) -> set[str]:
    """Alle Sitzungen, die auf der Tafel vorkommen: Claims und Verlauf
    (``<stempel> <SITZUNG> claim …``) — Empfaenger eines ``AN ALLE``."""
    out = {str(c.get("sitzung", "")).strip().upper() for c in tafel.get("claims", ())}
    for v in tafel.get("verlauf", ()):
        m = re.match(r"^\S+\s+([A-Z])\b", v or "")
        if m:
            out.add(m.group(1))
    out.discard("")
    return out


def blocker_behalten(blocker: list[str], t: datetime, sitzungen=()) -> list[str]:
    """Die Blocker, die beim Schreiben zum Zeitpunkt ``t`` stehen bleiben.

    Reihenfolge bleibt erhalten. Verfallen ist ein Eintrag nur, wenn er
    datierbar, aelter als :data:`BLOCKER_VERFALL`, kein offener Brief und
    nicht der letzte Eintrag seiner Sitzung ist. ``sitzungen`` ergaenzt die
    Empfaenger eines ``AN ALLE`` um Sitzungen ohne eigenen Blocker
    (:func:`tafel_sitzungen`).
    """
    letzter: dict[str, int] = {}
    for i, b in enumerate(blocker):
        sitzung = (blocker_sitzung(b) or "").upper()
        if sitzung:
            letzter[sitzung] = i
    behalten = []
    for i, b in enumerate(blocker):
        st = lies_stempel(b.split(" ", 1)[0]) if b.strip() else None
        if (st is None or t - st <= BLOCKER_VERFALL
                or letzter.get((blocker_sitzung(b) or "").upper()) == i
                or blocker_offen(blocker, i, sitzungen)):
            behalten.append(b)
    return behalten


def blocker_text(roh: bytes) -> str:
    """Rohbytes (stdin oder Datei) -> EINE Blocker-Zeile.

    UTF-8 (mit oder ohne BOM) und UTF-16 mit BOM — das Letzte schreibt
    Windows PowerShell 5 mit ``Out-File``/``>`` als Vorgabe. Zeilenenden
    ``\r\n``/``\r``/``\n`` sind gleich; Zeilen werden zu einer verbunden,
    denn auf der Tafel ist ein Blocker genau ein Listenpunkt — eine zweite
    Zeile ohne ``- `` davor wuerde beim naechsten Lesen still verschwinden.
    Wirft ``UnicodeDecodeError`` bei allem anderen (lieber laut als ein
    Ersatzzeichen auf der geteilten Tafel).
    """
    if roh.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = roh.decode("utf-16")
    else:
        text = roh.decode("utf-8-sig")
    zeilen = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return " ".join(z.strip() for z in zeilen if z.strip())


# Ein ``?`` direkt zwischen zwei Buchstaben (``f?r``, ``Gr??e``) ist das
# typische Muster eines verlorenen Umlauts: Windows PowerShell 5.1 kodiert eine
# Pipe an ein natives Programm nach ``$OutputEncoding`` — Vorgabe US-ASCII —
# und ersetzt alles ausserhalb davon STILL durch ``?``. Bei uns kommt dann
# gueltiges UTF-8 an, die Dekodierung kann den Verlust nicht bemerken.
_UMLAUT_VERLOREN = re.compile(r"[^\W\d_]\?+[^\W\d_]")


def verdacht_verlorene_umlaute(text: str) -> list[str]:
    """Stellen, an denen vermutlich ein Umlaut zu ``?`` geworden ist."""
    return [m.group(0) for m in _UMLAUT_VERLOREN.finditer(text)]


def ist_verfallen(claim: dict, t: datetime) -> bool:
    seit = lies_stempel(claim.get("seit", ""))
    if seit is None:
        # Unlesbarer Zeitstempel: NICHT als verfallen behandeln. Ein Claim, den
        # man nicht datieren kann, im Zweifel zu uebernehmen waere die
        # gefaehrlichere Richtung — dann arbeiten zwei am selben Item.
        return False
    return t - seit > VERFALL


def finde(tafel: dict, item: str) -> dict | None:
    for c in tafel["claims"]:
        if c["item"].upper() == item.upper():
            return c
    return None


def klarnamen_datei() -> str:
    """PRIV-05: LOKALE Liste echter Namen, die nie auf die Tafel duerfen.

    Liegt bewusst AUSSERHALB des Repos — die Liste selbst waere sonst genau das
    Leck, das sie verhindern soll. Zusaetzlich wird ``<git-common-dir>/klarnamen.txt``
    gelesen (im Projektordner, aber nie versioniert). ``LIGHTOS_KLARNAMEN`` ueberschreibt den Ort
    (Tests). Linux/macOS: ``~/.config/lightos/klarnamen.txt``; Windows:
    ``%APPDATA%\\lightos\\klarnamen.txt``. Ein Name je Zeile, ``#`` = Kommentar.
    """
    ort = os.environ.get("LIGHTOS_KLARNAMEN")
    if ort:
        return ort
    if os.name == "nt" and os.environ.get("APPDATA"):
        return os.path.join(os.environ["APPDATA"], "lightos", "klarnamen.txt")
    basis = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(basis, "lightos", "klarnamen.txt")


def _git_klarnamen_datei() -> str | None:
    """Zweiter Ort: ``<git-common-dir>/klarnamen.txt`` — liegt im Projektordner,
    wird aber nie versioniert oder gepusht (``.git`` ist kein Arbeitsbaum).
    Fuer Rechner, auf denen ausserhalb des Projektordners nichts angelegt werden
    darf (Windows-Sitzung B, 01.10.2026)."""
    if os.environ.get("LIGHTOS_KLARNAMEN"):
        return None                              # Tests: nur die ausdrueckliche Datei
    try:
        r = subprocess.run(["git", "rev-parse", "--git-common-dir"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           cwd=os.path.dirname(os.path.abspath(__file__)),
                           timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    common = r.stdout.strip()
    if r.returncode != 0 or not common:
        return None
    if not os.path.isabs(common):
        common = os.path.join(os.path.dirname(os.path.abspath(__file__)), common)
    return os.path.join(common, "klarnamen.txt")


def _klarnamen() -> list[str]:
    """Namen aus :func:`klarnamen_datei` und ``<git-common-dir>/klarnamen.txt``;
    fehlen beide, ist die Liste leer (dann prueft der Waechter nur
    Pfade/Links/Adressen wie bisher)."""
    namen: list[str] = []
    for ort in (klarnamen_datei(), _git_klarnamen_datei()):
        if not ort:
            continue
        try:
            with open(ort, encoding="utf-8-sig") as f:
                namen += [z.strip() for z in f]
        except OSError:
            continue
    return [z for z in dict.fromkeys(namen) if len(z) >= 2 and not z.startswith("#")]


def pruefe_oeffentlich(text: str) -> list[str]:
    """PRIV-01/02: was in ein oeffentliches Repo nicht hineingehoert.

    Bis PROC-25 lag die Tafel im oeffentlichen Repo; ein Blocker-Text ist
    Freitext und war damit die Stelle, an der versehentlich Privates landen
    konnte. Seit dem Umzug ins private ``lightos-intern`` gilt diese Pruefung
    nur noch fuer Texte, die ins OEFFENTLICHE Repo gehen: ``LIGHTOS_TAFEL=alt``
    und den Hinweis-Commit von ``umzug``. Zugangsdaten sperrt ueberall
    :func:`pruefe_zugangsdaten`.
    """
    funde = []
    if re.search(r"/home/(?!user\b|runner\b)[a-z][a-z0-9_-]+/", text):
        funde.append("Home-Pfad mit Kontonamen (nutze /home/user/…)")
    # PRIV-05: beide Trenner — "C:/Users/<konto>/" stand so schon auf der Tafel.
    if re.search(r"[A-Za-z]:[\\/]+Users[\\/]+(?![Xx]\b|user\b|Public\b)[A-Za-z]", text):
        funde.append("Windows-Nutzerpfad (nutze C:\\Users\\X\\…)")
    for name in _klarnamen():
        if re.search(r"(?<![\w])" + re.escape(name) + r"s?(?![\w])", text, re.IGNORECASE):
            funde.append(f"Klarname aus der lokalen Namensliste (im Repo heisst der "
                         f"Betreiber „Robin“): {name[:1]}…")
    if "claude.ai/code/session" in text:
        funde.append("Sitzungs-Link")
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text):
        funde.append("E-Mail-Adresse")
    return funde


# ─── PROC-25: Zugangsdaten nie auf die Tafel ─────────────────────────────────
# Im privaten Tafel-Repo duerfen Klarnamen stehen — Zugangsdaten nie: ein
# privates Repo ist kein Tresor (jeder Klon, jede Sicherung, jeder spaeter
# hinzugefuegte Mitleser traegt sie mit). Die Pruefung laeuft deshalb nicht nur
# auf dem neuen Freitext, sondern in `_schreibe_dateien` auf JEDEM Inhalt, der
# gepusht wird. Gemeldet wird die ART des Fundes, nie der Wert.

_ZUGANGSMUSTER = (
    ("GitHub-Token (ghp_/gho_/ghu_/ghs_/ghr_…)",
     re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{20,}")),
    ("GitHub-Token (github_pat_…)",
     re.compile(r"(?<![A-Za-z0-9])github_pat_[A-Za-z0-9_]{20,}")),
    ("AWS-Zugangsschluessel (AKIA…/ASIA…)",
     re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Z0-9])")),
    ("Schluessel-Block (-----BEGIN … KEY-----)",
     re.compile(r"-----BEGIN [A-Z0-9 ]*KEY(?: BLOCK)?-----")),
    ("API-Schluessel (sk-…)",
     re.compile(r"(?<![A-Za-z0-9])sk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}")),
    ("GitLab-Token (glpat-…)",
     re.compile(r"(?<![A-Za-z0-9])glpat-[A-Za-z0-9_-]{20,}")),
    ("Slack-Token (xox…-)",
     re.compile(r"(?<![A-Za-z0-9])xox[abprs]-[A-Za-z0-9-]{10,}")),
    ("Bearer-Token",
     re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{20,}")),
    ("Kennwort/Geheimnis mit Wert (password=, Kennwort: …)",
     re.compile(r"(?i)(?<![\w-])(?:password|passwort|passwd|kennwort|"
                r"secret|api[_-]?key|access[_-]?key)\s*[=:]\s*[^\s,;]")),
)


def pruefe_zugangsdaten(text: str) -> list[str]:
    """PROC-25: Token-/Kennwort-/Schluessel-Muster im Text (Art, nie Wert)."""
    return [art for art, muster in _ZUGANGSMUSTER if muster.search(text or "")]


class ZugangsdatenGesperrt(RuntimeError):
    """Ein Inhalt, der auf die Tafel sollte, traegt ein Zugangsdaten-Muster."""

    def __init__(self, funde: list[str], datei: str = DATEI):
        self.funde = funde
        super().__init__(
            f"Abgelehnt — Zugangsdaten-Muster in {datei}: {', '.join(funde)}. "
            "Nichts geschrieben. Zugangsdaten gehoeren nie auf die Tafel "
            "(auch nicht ins private Repo).")


# ─── PROC-25: wo die Tafel liegt ─────────────────────────────────────────────

class TafelOrt(NamedTuple):
    """Git-Repo, in dem die Tafel gelesen/geschrieben wird, und ihr Branch.

    ``alt`` = Uebergangsweg ``LIGHTOS_TAFEL=alt`` (Branch ``sessions`` im
    OEFFENTLICHEN Code-Repo) — dort gilt zusaetzlich :func:`pruefe_oeffentlich`.
    """
    repo: str
    branch: str = BRANCH
    alt: bool = False


class TafelFehlt(RuntimeError):
    """Kein Klon des Tafel-Repos am erwarteten Ort — Meldung mit Klon-Befehl."""

    def __init__(self, pfad: str, grund: str = "kein Git-Klon"):
        self.pfad = pfad
        super().__init__(
            f"Tafel-Klon fehlt ({grund}): {pfad}\n"
            f"Die Sitzungs-Tafel liegt seit PROC-25 im privaten Repo {TAFEL_GITHUB}.\n"
            f"Einmal einrichten:\n"
            f"    gh repo clone {TAFEL_GITHUB} {pfad}\n"
            f"Anderer Ort: Umgebungsvariable LIGHTOS_TAFEL_REPO=<pfad>.")


def code_repo_wurzel() -> str:
    """Das Code-Repo (bzw. der Worktree), in dem dieses Werkzeug liegt."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tafel_vorgabe(code_repo: str | None = None) -> str:
    """``<Projektordner>/lightos-intern`` — Geschwister von ``repo/`` und den
    Worktrees ``wt-*``, damit alle Worktrees denselben Klon finden."""
    wurzel = os.path.abspath(code_repo or code_repo_wurzel())
    return os.path.join(os.path.dirname(wurzel), TAFEL_ORDNER)


def tafel_pfad(code_repo: str | None = None, pfad: str | None = None) -> str:
    """Ausdruecklicher Pfad > ``LIGHTOS_TAFEL_REPO`` > :func:`tafel_vorgabe`."""
    gewaehlt = pfad or os.environ.get("LIGHTOS_TAFEL_REPO", "").strip()
    return os.path.abspath(os.path.expanduser(gewaehlt)) if gewaehlt \
        else tafel_vorgabe(code_repo)


def tafel_alt_gewuenscht() -> bool:
    return os.environ.get("LIGHTOS_TAFEL", "").strip().lower() == "alt"


def _ist_eigener_klon(pfad: str) -> str | None:
    """``None`` = brauchbarer Klon; sonst der Grund, warum nicht.

    ★ Nicht nur „``git rev-parse`` geht": ein leerer Ordner INNERHALB eines
    anderen Repos (etwa ``repo/lightos-intern``) waere fuer Git ein Teil des
    Code-Repos — dann landete die Tafel still im falschen, oeffentlichen Repo.
    """
    if not os.path.isdir(pfad):
        return "Ordner fehlt"
    r = subprocess.run(["git", "rev-parse", "--absolute-git-dir"], cwd=pfad,
                       capture_output=True)
    if r.returncode != 0:
        return "kein Git-Klon"
    gitdir = os.path.realpath(r.stdout.decode("utf-8", "replace").strip())
    echt = os.path.realpath(pfad)
    if gitdir not in (echt, os.path.join(echt, ".git")):
        return "Ordner liegt in einem anderen Repo, ist kein eigener Klon"
    r = subprocess.run(["git", "remote", "get-url", "origin"], cwd=pfad,
                       capture_output=True)
    if r.returncode != 0:
        return "Klon ohne Remote 'origin'"
    return None


def tafel_ort(code_repo: str | None = None, pfad: str | None = None,
              warnen: bool = True) -> TafelOrt:
    """Wo gelesen und geschrieben wird — wirft :class:`TafelFehlt`.

    Es gibt bewusst KEINEN Rueckfall auf ``origin/sessions``: eine Sitzung ohne
    Klon, die still die alte Tafel nimmt, schriebe Claims dorthin, wo keine
    andere Sitzung mehr hinsieht — zwei Tafeln sind schlimmer als keine.
    """
    if tafel_alt_gewuenscht() and not pfad:
        if warnen:
            print("⚠ LIGHTOS_TAFEL=alt: Tafel vom Branch `sessions` des "
                  "OEFFENTLICHEN Repos — nur fuer den Uebergangstag (PROC-25).",
                  file=sys.stderr)
        return TafelOrt(os.path.abspath(code_repo or code_repo_wurzel()),
                        BRANCH_ALT, True)
    ziel = tafel_pfad(code_repo, pfad)
    grund = _ist_eigener_klon(ziel)
    if grund:
        raise TafelFehlt(ziel, grund)
    return TafelOrt(ziel, BRANCH, False)


def _ort(ort) -> TafelOrt:
    """Ein nackter Pfad (Tests, aeltere Aufrufer) ist ein Tafel-Klon auf main."""
    return ort if isinstance(ort, TafelOrt) else TafelOrt(ort, BRANCH, False)


# ─────────────────────────────────────────────────────────────────────────────
# Git-Schicht
# ─────────────────────────────────────────────────────────────────────────────

def _git(*args: str, eingabe: str | None = None, repo: str | None = None,
         pruefen: bool = True) -> str:
    """git aufrufen — ueber BYTES, nicht ueber ``text=True``.

    ★ XPLAT-20 (31.08.2026): hier stand ``text=True`` ohne ``encoding``. Das
    hat auf Windows ZWEI verschiedene Fehler gleichzeitig gemacht, und der
    zweite hat die geteilte Tafel tatsaechlich zerstoert:

    1. **Dekodierung.** ``text=True`` nimmt die LOCALE-Kodierung, auf Windows
       cp1252. ``BACKLOG.md`` enthaelt ★/⚠/⏳ — Bytes, die cp1252 nicht kennt.
       Der ``UnicodeDecodeError`` faellt im subprocess-Reader-Thread und wird
       verschluckt: ``stdout`` ist danach ``None`` bei ``returncode == 0``, das
       Werkzeug stirbt also an einem irrefuehrenden ``AttributeError`` statt an
       einer Kodierungsmeldung.
    2. **Zeilenenden.** ``text=True`` uebersetzt beim SCHREIBEN ``\\n`` in
       ``os.linesep``. Auf Windows bekam damit die mktree-Zeile
       ``"100644 blob <hash>\\tSESSIONS.md\\n"`` ein ``\\r`` angehaengt — die
       Tafel landete als Datei **"SESSIONS.md\\r"** im Git-Baum. Fuer die
       andere Sitzung war sie damit spurlos verschwunden
       (``git show origin/sessions:SESSIONS.md`` -> "does not exist").
       Genau das ist am 31.08.2026 beim ersten Windows-Claim passiert.

    ``encoding="utf-8"`` allein behebt nur Punkt 1 — Punkt 2 bleibt, weil die
    Newline-Uebersetzung an ``newline=None`` haengt und ``subprocess.run`` kein
    ``newline``-Argument kennt. Gemessen:

    ==============================  =========================
    Aufruf                          Blob-Inhalt
    ==============================  =========================
    ``text=True``                   ``b'a\\r\\nb\\r\\n'``
    ``text=True, encoding='utf-8'``  ``b'a\\r\\nb\\r\\n'``
    bytes (dieser Weg)              ``b'a\\nb\\n'``
    ==============================  =========================

    Deshalb: Eingabe explizit nach UTF-8 kodieren, Ausgabe explizit dekodieren.
    """
    roh = eingabe.encode("utf-8") if eingabe is not None else None
    r = subprocess.run(["git", *args], cwd=repo, input=roh,
                       capture_output=True)
    if pruefen and r.returncode != 0:
        fehler = r.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git {' '.join(args)}: {fehler}")
    # stdout OHNE ``errors=``: die Tafel ist Nutzdaten. Ein Ersatzzeichen waere
    # hier eine stille Verfaelschung, die genau so wieder zurueckgeschrieben
    # wuerde — dann lieber ein lauter UnicodeDecodeError.
    # ``\r\n`` beim LESEN normalisieren: ein alter, von einer fruehen
    # Windows-Sitzung geschriebener Stand soll die Tafel nicht unlesbar machen.
    return r.stdout.decode("utf-8").replace("\r\n", "\n").strip()


def _hole(repo: str, branch: str) -> str | None:
    """``origin/<branch>`` frisch holen; Spitze oder ``None`` (Branch fehlt)."""
    _git("fetch", "--quiet", "origin",
         f"+refs/heads/{branch}:refs/remotes/origin/{branch}",
         repo=repo, pruefen=False)
    return _git("rev-parse", "--verify", "--quiet", f"origin/{branch}",
                repo=repo, pruefen=False) or None


def lade_datei(ort, datei: str) -> tuple[str, str | None]:
    """``(Inhalt, Spitze)`` einer Datei der Tafel — leer, wenn es sie noch nicht gibt."""
    repo, branch, _alt = _ort(ort)
    spitze = _hole(repo, branch)
    if not spitze:
        return "", None
    return _git("show", f"{spitze}:{datei}", repo=repo, pruefen=False), spitze


def lade_tafel(ort) -> tuple[dict, str | None]:
    """Tafel + Spitzen-Commit von ``origin/<branch>`` (nicht aus dem Arbeitsbaum).

    ``ort`` ist ein :class:`TafelOrt` oder der Pfad eines Tafel-Klons
    (Branch ``main``). Der zweite Rueckgabewert ist der Eltern-Commit fuer den
    naechsten Schreibvorgang. Er ist die halbe Konflikterkennung: schreiben
    wir spaeter gegen genau diesen Stand und ist der Remote inzwischen weiter,
    ist der Push kein Fast-Forward mehr und wird abgelehnt.
    """
    inhalt, spitze = lade_datei(ort, DATEI)
    return parse(inhalt), spitze


class TafelText(NamedTuple):
    """Ergebnis von :func:`lies_tafel_text` — fuer die LESER der Tafel."""
    text: str | None          # None = nicht gelesen
    fehler: str | None        # Lesefehler (Klon da, aber nicht lesbar)
    klon_fehlt: str | None    # Meldung mit Klon-Befehl, wenn der Klon fehlt
    quelle: str = ""          # z. B. "lightos-intern:origin/main:SESSIONS.md"


def lies_tafel_text(code_repo: str | None = None, holen: bool = False) -> TafelText:
    """PROC-25: die EINE Lesehilfe fuer Werkzeuge, die die Tafel nur lesen
    (``backlog_ids``, ``pr_bereit`` …) — statt eigener Kopien von Ort,
    Branch und Fehlerfall. Wirft nie.

    ``holen=False`` liest den zuletzt geholten Stand (``--kein-fetch``).
    """
    try:
        ort = tafel_ort(code_repo)
    except TafelFehlt as e:
        return TafelText(None, None, str(e), f"{TAFEL_ORDNER}:{DATEI}")
    quelle = (f"origin/{ort.branch}:{DATEI}" if ort.alt
              else f"{TAFEL_ORDNER}:origin/{ort.branch}:{DATEI}")
    try:
        if holen:
            _hole(ort.repo, ort.branch)
        r = subprocess.run(["git", "show", f"origin/{ort.branch}:{DATEI}"],
                           cwd=ort.repo, capture_output=True)
    except OSError as e:
        return TafelText(None, f"git nicht aufrufbar ({e})", None, quelle)
    if r.returncode != 0:
        return TafelText(None, r.stderr.decode("utf-8", "replace").strip()
                         or f"git show Exit {r.returncode}", None, quelle)
    return TafelText(r.stdout.decode("utf-8", "replace").replace("\r\n", "\n"),
                     None, None, quelle)


def _schreibe_dateien(ort, dateien: dict, eltern: str | None,
                      nachricht: str) -> bool:
    """Dateien als EIN Commit auf ``origin/<branch>`` — ``False`` = Rennen verloren.

    Ueber Plumbing statt Checkout: der Arbeitsbaum der Sitzung (und der einer
    parallel laufenden!) bleibt unberuehrt. Der Baum des Eltern-Commits wird
    uebernommen und nur ``dateien`` ersetzt — sonst loeschte jeder Claim die
    ``ENTSCHEIDUNGEN.md`` daneben.

    ★ PROC-25: JEDER Inhalt geht vorher durch :func:`pruefe_zugangsdaten`;
    ein Fund wirft :class:`ZugangsdatenGesperrt`, bevor irgendetwas
    geschrieben wird.
    """
    repo, branch, _alt = _ort(ort)
    for name, inhalt in dateien.items():
        funde = pruefe_zugangsdaten(inhalt)
        if funde:
            raise ZugangsdatenGesperrt(funde, name)
    eintraege: dict[str, str] = {}
    if eltern:
        for zeile in _git("ls-tree", "-z", eltern, repo=repo).split("\0"):
            if "\t" in zeile:
                meta, name = zeile.split("\t", 1)
                eintraege[name] = meta
    for name, inhalt in dateien.items():
        blob = _git("hash-object", "-w", "--stdin", eingabe=inhalt, repo=repo)
        eintraege[name] = f"100644 blob {blob}"
    baum = _git("mktree", "-z", eingabe="".join(
        f"{meta}\t{name}\0" for name, meta in sorted(eintraege.items())), repo=repo)
    args = ["commit-tree", baum, "-m", nachricht]
    if eltern:
        args += ["-p", eltern]
    commit = _git(*args, repo=repo)
    # XPLAT-20: wie ``_git`` ueber Bytes — hier wird zwar nichts geschrieben,
    # aber git meldet Fehler auf stderr mit UTF-8-Zeichen, und die duerfen den
    # Aufruf nicht an der cp1252-Dekodierung sterben lassen.
    r = subprocess.run(["git", "push", "origin", f"{commit}:refs/heads/{branch}"],
                       cwd=repo, capture_output=True)
    return r.returncode == 0


def schreibe_tafel(ort, tafel: dict, eltern: str | None,
                   nachricht: str) -> bool:
    """Tafel committen und pushen. ``False`` = jemand war schneller."""
    # PROC-08: die Schreib-Seite haelt die Blockerliste begrenzt — an genau
    # einer Stelle, damit claim/release/blocker es gleich halten.
    t = jetzt()
    bleibt = blocker_behalten(tafel["blocker"], t, tafel_sitzungen(tafel))
    weg = len(tafel["blocker"]) - len(bleibt)
    if weg:
        tafel = dict(tafel, blocker=bleibt, verlauf=list(tafel["verlauf"]) + [
            f"{stempel(t)} {weg} Blocker verfallen (aelter als "
            f"{BLOCKER_VERFALL.days} Tage, gelesen; Volltext in der Historie)"])
    return _schreibe_dateien(ort, {DATEI: rendere(tafel)}, eltern, nachricht)


# ─────────────────────────────────────────────────────────────────────────────
# Befehle
# ─────────────────────────────────────────────────────────────────────────────

def _mit_wiederholung(repo: str, aendern, nachricht: str, versuche: int = 5):
    """Lesen → aendern → pushen, bei verlorenem Rennen erneut.

    ``aendern(tafel)`` gibt ``(weiter?, meldung)`` zurueck. Gibt es ``False``
    zurueck, wird nichts geschrieben — dann hat die Pruefung entschieden, dass
    es nichts zu tun gibt (z. B. „schon belegt").
    """
    for versuch in range(versuche):
        tafel, eltern = lade_tafel(repo)
        if _ort(repo).alt and eltern and ist_umgezogen(repo, eltern):
            # PROC-25: nach dem Umzug steht auf `sessions` nur noch der
            # Hinweis. Wer dort weiterschreibt, fuehrt eine zweite Tafel, die
            # niemand mehr liest.
            return False, ("LIGHTOS_TAFEL=alt: die Tafel ist schon umgezogen "
                           f"({UMZUG_MARKE}) — nichts geschrieben. Klon "
                           f"einrichten: gh repo clone {TAFEL_GITHUB} "
                           f"{tafel_vorgabe(_ort(repo).repo)}")
        weiter, meldung = aendern(tafel)
        if not weiter:
            return False, meldung
        if schreibe_tafel(repo, tafel, eltern, nachricht):
            return True, meldung
        # Push abgelehnt: die andere Sitzung war schneller. Neu lesen — beim
        # naechsten Durchlauf sieht `aendern` ihren Claim und entscheidet neu.
        print(f"[claim] Rennen verloren (Versuch {versuch + 1}), lese neu …",
              file=sys.stderr)
    return False, "konnte nicht schreiben — zu viele gleichzeitige Aenderungen"


# PROC-07: Vorgabe fuer `list`. Fuenf statt drei, gemessen begruendet: die
# QA-66-Erklaerung ("nicht den eigenen Diff verdaechtigen") lag bei drei
# Blockern knapp ausserhalb, obwohl die juengsten sie zweimal erwaehnen —
# eine Kurzfassung, die eine Referenz aufreisst, macht die Runde teurer
# statt billiger.
_BLOCKER_VORGABE = 5


def cmd_list(args, repo: str) -> int:
    tafel, _ = lade_tafel(repo)
    t = jetzt()
    if not tafel["claims"]:
        print("Keine aktiven Claims.")
    for c in tafel["claims"]:
        marke = "  ⏳ VERFALLEN" if ist_verfallen(c, t) else ""
        print(f"{c['item']:<16} {c['sitzung']:<4} {c['branch']:<32} "
              f"seit {c['seit']}{marke}")
        if c["dateien"]:
            print(f"{'':<16} Dateien: {c['dateien']}")
    blocker = tafel["blocker"]
    fuer = getattr(args, "fuer", None)
    if fuer:
        # PROC-17: statt der juengsten fuenf genau die Briefe, die seit dem
        # letzten eigenen Eintrag an diese Sitzung gingen — ungekuerzt.
        an = blocker_fuer(blocker, fuer)
        if an:
            print(f"\nAn {fuer} seit dem letzten eigenen Eintrag ({len(an)}):")
            for b in an:
                print(f"  - {b}")
        else:
            print(f"\nNichts an {fuer} seit dem letzten eigenen Eintrag.")
        return 0
    if blocker:
        # PROC-07: die Blockerliste waechst unbegrenzt und macht 99 % der Ausgabe
        # aus (gemessen 2026-09-01: 11.516 von 11.637 Bytes). `list` steht als
        # Schritt 2 im Ablauf JEDES Items (AGENTS.md, COORDINATION.md) — wer sie
        # jedes Mal ganz liest, zahlt sie jedes Mal. Vorgabe deshalb: nur die
        # juengsten, aber UNGEKUERZT (ein angeschnittener Blocker ist wertlos —
        # gerade die letzte Zeile ist meist die Uebergabe der anderen Sitzung).
        # Die Gesamtzahl und der Weg zur Vollansicht stehen in der Kopfzeile,
        # damit niemand glaubt, er saehe alles.
        n = getattr(args, "blocker", _BLOCKER_VORGABE)
        if n == 0:
            print(f"\n({len(blocker)} Blocker ausgeblendet — `list --blocker -1` zeigt alle)")
            return 0
        zeigen = blocker if n < 0 else blocker[-n:]
        if len(zeigen) < len(blocker):
            print(f"\nBlocker (letzte {len(zeigen)} von {len(blocker)} — "
                  f"alle mit `--blocker -1`):")
        else:
            print("\nBlocker:")
        for b in zeigen:
            print(f"  - {b}")
    return 0


def _melde_ueberschneidung(treffer, sitzung: str) -> None:
    # Zwei Kategorien, weil die Abhilfe verschieden ist: bei einer fremden
    # Sitzung hilft nur ein Blocker, bei der eigenen reicht es, die eigenen
    # parallelen Agenten (Worktrees) nicht auf dieselbe Datei loszulassen.
    fremd = [(c, b) for c, b in treffer if c.get("sitzung") != sitzung]
    eigen = [(c, b) for c, b in treffer if c.get("sitzung") == sitzung]
    if fremd:
        print("⚠ Dateiueberschneidung mit fremden Claims (PROC-16):",
              file=sys.stderr)
        for c, beruehrt in fremd:
            print(f"  - {c['item']} (Sitzung {c['sitzung']}, Branch "
                  f"{c['branch']}, seit {c['seit']}): {' · '.join(beruehrt)}",
                  file=sys.stderr)
        print("  Vorher absprechen (Blocker an die Sitzung) oder ein anderes "
              "Item nehmen.", file=sys.stderr)
    if eigen:
        print(f"⚠ Hinweis: Dateiueberschneidung mit eigenen Claims "
              f"(Sitzung {sitzung}, PROC-16):", file=sys.stderr)
        for c, beruehrt in eigen:
            print(f"  - eigenes Item {c['item']} (Branch {c['branch']}) "
                  f"beruehrt dieselbe Datei: {' · '.join(beruehrt)}",
                  file=sys.stderr)
        print("  Laufen beide Items parallel (eigene Worktree-Agenten), "
              "nacheinander mergen oder zusammenlegen.", file=sys.stderr)


def cmd_claim(args, repo: str) -> int:
    # PROC-16: `refresh` laeuft durch diese Funktion, ist aber ein reines
    # Auffrischen — es fragt weder nach Dateien noch vergleicht es welche.
    auffrischen = getattr(args, "auffrischen", False)
    strikt = getattr(args, "strikt", False)
    gefunden: list = []

    def aendern(tafel):
        t = jetzt()
        gefunden.clear()                   # jeder Versuch liest neu
        vorhanden = finde(tafel, args.item)
        if (vorhanden is None or vorhanden["sitzung"] == args.session
                or ist_verfallen(vorhanden, t)) and args.files:
            # Erst NACH der Belegt-Pruefung sinnvoll — ein belegtes Item
            # meldet „belegt", nicht eine Ueberschneidung mit sich selbst.
            gefunden.extend(ueberschneidungen(tafel, args.session, args.item,
                                              args.files, t))
            if gefunden and strikt:
                return False, (f"{args.item}: NICHT belegt — --strikt und "
                               f"{len(gefunden)} Dateiueberschneidung(en).")
        if vorhanden and vorhanden["sitzung"] == args.session:
            # ★★ PROC-12: Ein erneuter `claim` DERSELBEN Sitzung hat bis
            # 2026-09-05 nur den Zeitstempel angefasst und `--branch`/`--files`
            # STILL VERWORFEN — und dabei „Claim aufgefrischt" gemeldet, also
            # Erfolg. Gemessen ist genau das passiert: A hat FM-41 zweimal mit
            # neuem Zweig und neuer Dateiliste belegt, die Tafel zeigte
            # weiterhin den ersten Zweig und EINE Datei. B las daraus, A fasse
            # `app_state.py` nicht an — und nahm sich ein Item, das genau dort
            # arbeitet. Die Tafel meldete keinen Konflikt, wo einer war.
            #
            # Das ist die Fehlrichtung, die dieses Werkzeug am wenigsten haben
            # darf: es verschweigt eine Ueberschneidung, statt sie zu nennen.
            # `refresh` reicht bewusst None durch und bleibt damit ein reines
            # Auffrischen; angegebene Werte GEWINNEN jetzt.
            vorhanden["seit"] = stempel(t)
            geaendert = []
            if args.branch and args.branch != vorhanden.get("branch"):
                geaendert.append(f"Branch {vorhanden.get('branch')} -> {args.branch}")
                vorhanden["branch"] = args.branch
            if args.files is not None:
                neu_dateien = " · ".join(args.files) or "-"
                if neu_dateien != vorhanden.get("dateien"):
                    geaendert.append(f"Dateien {vorhanden.get('dateien')} -> {neu_dateien}")
                    vorhanden["dateien"] = neu_dateien
            if geaendert:
                tafel["verlauf"].append(
                    f"{stempel(t)} {args.session} aktualisiert {args.item}: "
                    + "; ".join(geaendert))
                return True, (f"{args.item}: Claim aufgefrischt UND geaendert — "
                              + "; ".join(geaendert))
            return True, f"{args.item}: Claim aufgefrischt (unveraendert)"
        if vorhanden and not ist_verfallen(vorhanden, t):
            return False, (f"{args.item} ist belegt von Sitzung "
                           f"{vorhanden['sitzung']} (Branch {vorhanden['branch']}, "
                           f"seit {vorhanden['seit']}). Nimm ein anderes Item.")
        if vorhanden:
            tafel["claims"].remove(vorhanden)
            tafel["verlauf"].append(
                f"{stempel(t)} {args.session} uebernimmt {args.item} von "
                f"{vorhanden['sitzung']} (Claim verfallen)")
        tafel["claims"].append({
            "item": args.item, "sitzung": args.session,
            "branch": args.branch or "-", "seit": stempel(t),
            "dateien": " · ".join(args.files or []) or "-",
        })
        tafel["verlauf"].append(f"{stempel(t)} {args.session} claim {args.item}")
        return True, f"{args.item} gehoert jetzt Sitzung {args.session}"

    ok, meldung = _mit_wiederholung(
        repo, aendern, f"claim {args.item} ({args.session})")
    if gefunden:
        _melde_ueberschneidung(gefunden, args.session)
    if (not auffrischen and ok and not [f for f in (args.files or [])
                                         if f.strip() and f.strip() != "-"]):
        # Ohne Dateiliste kann niemand — weder die andere Sitzung noch dieses
        # Werkzeug — eine Ueberschneidung erkennen. Kein Abbruch: manches
        # Item kennt seine Dateien erst nach dem Lesen; dann nachreichen.
        print(f"⚠ {args.item}: ohne --files ist keine Ueberschneidungspruefung "
              f"moeglich — nachreichen mit `claim {args.item} --session "
              f"{args.session} --files …`.", file=sys.stderr)
    print(meldung)
    if gefunden and strikt and not ok:
        return 2
    return 0 if ok else 1


def cmd_refresh(args, repo: str) -> int:
    args.branch, args.files = None, None
    args.auffrischen, args.strikt = True, False
    return cmd_claim(args, repo)


def cmd_release(args, repo: str) -> int:
    def aendern(tafel):
        t = jetzt()
        vorhanden = finde(tafel, args.item)
        if vorhanden is None:
            return False, f"{args.item} war gar nicht belegt."
        if vorhanden["sitzung"] != args.session and not args.force:
            return False, (f"{args.item} gehoert Sitzung {vorhanden['sitzung']}, "
                           f"nicht {args.session}. Mit --force trotzdem freigeben.")
        tafel["claims"].remove(vorhanden)
        tafel["verlauf"].append(
            f"{stempel(t)} {args.session} {args.status} {args.item}")
        return True, f"{args.item} freigegeben ({args.status})"

    ok, meldung = _mit_wiederholung(
        repo, aendern, f"release {args.item} ({args.status})")
    print(meldung)
    return 0 if ok else 1


def _blocker_quelle(args) -> str | None:
    """PROC-17: Text aus dem Argument, aus ``--datei <pfad>`` oder ``--datei -``.

    stdin bzw. Datei gibt es, weil Freitext als Shell-Argument zwei Fallen
    hat: Backticks fuehrt die Shell AUS (``"… `x` …"`` wird zu dessen
    Ausgabe), und lange Texte mit Anfuehrungszeichen brechen das Quoting.
    Mit ``<<'EOF' … EOF | … blocker --datei -`` kommt der Text unveraendert an.
    """
    datei = getattr(args, "datei", None)
    if datei is None:
        return args.text
    if datei == "-":
        if sys.stdin is None:              # pythonw.exe auf Windows: kein stdin
            raise OSError("kein stdin vorhanden")
        strom = getattr(sys.stdin, "buffer", None)
        roh = strom.read() if strom is not None else sys.stdin.read().encode("utf-8")
        text = blocker_text(roh)
        verdacht = verdacht_verlorene_umlaute(text)
        if verdacht:
            # Nur ein Hinweis, kein Abbruch: ``?`` zwischen Buchstaben kann
            # auch gewollt sein. Aber der Verlust selbst ist stumm.
            print(f"Hinweis: '?' zwischen Buchstaben ({', '.join(verdacht[:3])})"
                  f" — verlorene Umlaute? Unter Windows PowerShell 5.1 kodiert "
                  f"die Pipe nach $OutputEncoding (US-ASCII). Besser "
                  f"`--datei brief.txt` (Datei als UTF-8 speichern) oder "
                  f"`$OutputEncoding = [Text.UTF8Encoding]::new()`. "
                  f"Wird trotzdem geschrieben.", file=sys.stderr)
        return text
    with open(datei, "rb") as f:
        roh = f.read()
    return blocker_text(roh)


def cmd_blocker(args, repo: str) -> int:
    if (getattr(args, "datei", None) is None) == (args.text is None):
        print("Blocker-Text ODER --datei <pfad|-> angeben (genau eins).",
              file=sys.stderr)
        return 2
    try:
        args.text = _blocker_quelle(args)
    except UnicodeDecodeError:
        print("Blocker-Text ist kein UTF-8 (Datei als UTF-8 speichern).",
              file=sys.stderr)
        return 2
    except OSError as e:
        print(f"Blocker-Datei nicht lesbar: {e}", file=sys.stderr)
        return 2
    if not args.text.strip():
        print("Blocker-Text ist leer.", file=sys.stderr)
        return 2
    if not args.remove and len(args.text) >= BLOCKER_LANG:
        # Nur ein Hinweis: manches braucht den Platz. Aber die Tafel wird
        # gelesen, nicht durchsucht — ein langer Brief wird eher ueberlesen.
        print(f"Hinweis: {len(args.text)} Zeichen (ab {BLOCKER_LANG} wird ein "
              f"Blocker leicht ueberlesen) — Details besser ins BACKLOG, hier "
              f"nur Kern + Verweis. Wird trotzdem geschrieben.", file=sys.stderr)
    # PROC-25: Zugangsdaten nie — egal wo die Tafel liegt. (`_schreibe_dateien`
    # prueft den ganzen Inhalt noch einmal; hier gibt es die fruehe Meldung.)
    funde = pruefe_zugangsdaten(args.text)
    if funde:
        print("Abgelehnt — Zugangsdaten-Muster im Blocker-Text (nie auf die "
              "Tafel, auch nicht ins private Repo):", file=sys.stderr)
        for f in funde:
            print(f"  - {f}", file=sys.stderr)
        return 2
    # Klarnamen & Co. nur, wenn die Tafel im OEFFENTLICHEN Repo liegt
    # (LIGHTOS_TAFEL=alt) — im privaten lightos-intern sind sie erlaubt.
    funde = pruefe_oeffentlich(args.text) if _ort(repo).alt else []
    if funde:
        print("Abgelehnt — die Tafel liegt in einem OEFFENTLICHEN Repo:",
              file=sys.stderr)
        for f in funde:
            print(f"  - {f}", file=sys.stderr)
        return 2

    def aendern(tafel):
        eintrag = f"{stempel(jetzt())} ({args.session}) {args.text}"
        if args.remove:
            passend = [b for b in tafel["blocker"] if args.text.lower() in b.lower()]
            if not passend:
                return False, "kein passender Blocker gefunden"
            for b in passend:
                tafel["blocker"].remove(b)
            return True, f"{len(passend)} Blocker entfernt"
        tafel["blocker"].append(eintrag)
        return True, "Blocker vermerkt"

    ok, meldung = _mit_wiederholung(repo, aendern, "blocker")
    print(meldung)
    return 0 if ok else 1


# ─── PROC-25: offene Entscheidungen (ENTSCHEIDUNGEN.md) ──────────────────────
# Neben der Tafel liegt im privaten Repo eine Liste offener Entscheidungen —
# Fragen, die nur der Projektinhaber beantworten kann und die sonst zwischen
# Blockern untergehen. Eine Zeile je Entscheidung, fortlaufend nummeriert.

_E_KOPF = """# ENTSCHEIDUNGEN.md — offene Entscheidungen

<!-- Gepflegt von tools/session_claim.py entscheidung add|list|done.
     Eine Zeile je Entscheidung: `- E-<n> · <stempel> (<Sitzung>) <Frage>`.
     Erledigte wandern nach unten (die juengsten 50 bleiben stehen, der Rest
     in der Git-Historie). Zugangsdaten NIE hierher.
     naechste-nummer: {naechste} -->
"""
_E_OFFEN = "## Offen"
_E_ERLEDIGT = "## Erledigt"
_E_ZEILE = re.compile(r"^- (E-(\d+)) · (.*)$")
_E_NAECHSTE = re.compile(r"naechste-nummer:\s*(\d+)")
_E_ERLEDIGT_MAX = 50


def parse_entscheidungen(inhalt: str) -> dict:
    """``{"offen": [(id, text)], "erledigt": [(id, text)], "naechste": n}``."""
    offen, erledigt, abschnitt, hoechste = [], [], None, 0
    for zeile in (inhalt or "").splitlines():
        if zeile.startswith("## "):
            abschnitt = zeile.strip()
            continue
        m = _E_ZEILE.match(zeile.rstrip())
        if not m:
            continue
        hoechste = max(hoechste, int(m.group(2)))
        ziel = offen if abschnitt == _E_OFFEN else erledigt if abschnitt == _E_ERLEDIGT else None
        if ziel is not None:
            ziel.append((m.group(1), m.group(3)))
    m = _E_NAECHSTE.search(inhalt or "")
    naechste = max(int(m.group(1)) if m else 1, hoechste + 1)
    return {"offen": offen, "erledigt": erledigt, "naechste": naechste}


def rendere_entscheidungen(e: dict) -> str:
    teile = [_E_KOPF.format(naechste=e["naechste"]), "\n", _E_OFFEN, "\n\n"]
    teile += [f"- {i} · {t}\n" for i, t in e["offen"]] or ["_(keine)_\n"]
    teile += ["\n", _E_ERLEDIGT, "\n\n"]
    teile += [f"- {i} · {t}\n" for i, t in e["erledigt"][-_E_ERLEDIGT_MAX:]] \
        or ["_(keine)_\n"]
    return "".join(teile)


def _nur_privat(ort, was: str) -> str | None:
    if _ort(ort).alt:
        return (f"{was} gibt es nur im privaten Tafel-Repo — nicht mit "
                "LIGHTOS_TAFEL=alt.")
    return None


def cmd_entscheidung(args, repo) -> int:
    fehler = _nur_privat(repo, "ENTSCHEIDUNGEN.md")
    if fehler:
        print(fehler, file=sys.stderr)
        return 2
    if args.aktion == "list":
        e = parse_entscheidungen(lade_datei(repo, DATEI_ENTSCHEIDUNGEN)[0])
        if not e["offen"]:
            print("Keine offenen Entscheidungen.")
        for i, t in e["offen"]:
            print(f"{i:<6} {t}")
        if getattr(args, "alle", False) and e["erledigt"]:
            print("\nErledigt:")
            for i, t in e["erledigt"]:
                print(f"{i:<6} {t}")
        return 0
    if not args.session:
        print("--session angeben.", file=sys.stderr)
        return 2
    if args.aktion == "add":
        text = " ".join(z.strip() for z in (args.text or "").splitlines() if z.strip())
        if not text:
            print("Text der Entscheidung fehlt.", file=sys.stderr)
            return 2
        funde = pruefe_zugangsdaten(text)
        if funde:
            print(f"Abgelehnt — Zugangsdaten-Muster: {', '.join(funde)}",
                  file=sys.stderr)
            return 2
    for _versuch in range(5):
        inhalt, eltern = lade_datei(repo, DATEI_ENTSCHEIDUNGEN)
        e = parse_entscheidungen(inhalt)
        t = stempel(jetzt())
        if args.aktion == "add":
            eid = f"E-{e['naechste']}"
            e["offen"].append((eid, f"{t} ({args.session}) {text}"))
            e["naechste"] += 1
            meldung = f"{eid} vermerkt"
        else:                                         # done
            eid = (args.text or "").strip().upper()
            treffer = [x for x in e["offen"] if x[0].upper() == eid]
            if not treffer:
                print(f"{eid}: keine offene Entscheidung mit dieser Nummer.",
                      file=sys.stderr)
                return 1
            e["offen"].remove(treffer[0])
            notiz = f": {args.notiz.strip()}" if args.notiz else ""
            e["erledigt"].append((treffer[0][0], f"{treffer[0][1]} — erledigt "
                                  f"{t} ({args.session}){notiz}"))
            meldung = f"{treffer[0][0]} erledigt"
        if _schreibe_dateien(repo, {DATEI_ENTSCHEIDUNGEN: rendere_entscheidungen(e)},
                             eltern, f"entscheidung {args.aktion} {eid} ({args.session})"):
            print(meldung)
            return 0
        print(f"[entscheidung] Rennen verloren, lese neu …", file=sys.stderr)
    print("konnte nicht schreiben — zu viele gleichzeitige Aenderungen")
    return 1


# ─── PROC-25: einmaliger Umzug der Tafel ins private Repo ────────────────────

def umzug_hinweis(datum: str) -> str:
    """Was auf ``origin/sessions`` stehen bleibt — geht ins OEFFENTLICHE Repo."""
    return (f"# SESSIONS.md — umgezogen\n\n"
            f"Die Sitzungs-Tafel ist {UMZUG_MARKE} am {datum}; Historie bleibt "
            f"hier:\n`git log -p origin/sessions -- SESSIONS.md`.\n\n"
            f"Einrichtung und Regeln: `COORDINATION.md` auf `main`. Dieser "
            f"Branch bleibt bestehen und wird nicht mehr beschrieben.\n")


def ist_umgezogen(ort, spitze: str | None) -> bool:
    if not spitze:
        return False
    repo = _ort(ort).repo
    return UMZUG_MARKE in _git("show", f"{spitze}:{DATEI}", repo=repo, pruefen=False)


def _zeilen_nur_in(a: str, b: str) -> list[str]:
    """Claim-, Blocker- und Verlaufszeilen, die in ``a`` stehen, in ``b`` nicht."""
    def wichtig(text):
        return [z for z in text.splitlines()
                if z.startswith("- ") or (z.startswith("| ") and not z.startswith("| Item")
                                          and not z.startswith("| _"))]
    rest = set(wichtig(b))
    return [z for z in wichtig(a) if z not in rest]


def cmd_umzug(args) -> int:
    """Tafel von ``origin/sessions`` ins Tafel-Repo — idempotent, ``--trocken``.

    Reihenfolge mit Absicht: erst das NEUE Repo beschreiben, dann den Hinweis
    auf ``sessions`` setzen. Bricht dazwischen etwas ab, ist nichts verloren —
    die alte Tafel steht noch, der zweite Lauf erkennt die neue und setzt nur
    noch den Hinweis.
    """
    code = os.path.abspath(args.repo)
    ziel = tafel_pfad(code, args.tafel)
    grund = _ist_eigener_klon(ziel)
    if grund:
        print(TafelFehlt(ziel, grund), file=sys.stderr)
        return 3
    neu = TafelOrt(ziel, BRANCH, False)
    alt = TafelOrt(code, BRANCH_ALT, True)
    datum = jetzt().strftime("%Y-%m-%d")
    wer = args.session or "A"

    alt_inhalt, alt_spitze = lade_datei(alt, DATEI)
    neu_inhalt, neu_spitze = lade_datei(neu, DATEI)
    alt_umgezogen = UMZUG_MARKE in alt_inhalt
    neu_da = bool(neu_inhalt.strip())
    if alt_umgezogen and neu_da:
        print(f"Umzug schon erledigt: origin/{BRANCH_ALT} traegt den Hinweis, "
              f"{TAFEL_ORDNER} hat die Tafel. Nichts zu tun.")
        return 0

    if alt_umgezogen:
        # Hinweis steht, neue Tafel fehlt (von Hand gesetzt?) — der Inhalt
        # ist der Stand direkt davor.
        quelle = _git("show", f"{alt_spitze}^:{DATEI}", repo=code, pruefen=False)
    else:
        quelle = alt_inhalt
    if not neu_da and not quelle.strip():
        print(f"Keine alte Tafel auf origin/{BRANCH_ALT} gefunden — nichts "
              "umzuziehen. Eine neue Tafel entsteht beim ersten `claim`.",
              file=sys.stderr)
        return 1
    funde = pruefe_zugangsdaten(quelle) if not neu_da else []
    if funde:
        print(f"Abgelehnt — die alte Tafel traegt Zugangsdaten-Muster "
              f"({', '.join(funde)}). Erst von Hand bereinigen, dann umzug.",
              file=sys.stderr)
        return 2
    hinweis = umzug_hinweis(datum)
    assert not pruefe_oeffentlich(hinweis), "Hinweistext ist nicht oeffentlich tauglich"

    nachtrag = []
    if neu_da and not alt_umgezogen:
        # Zweiter Lauf nach halbem Umzug: kam auf `sessions` seither etwas dazu?
        nachtrag = _zeilen_nur_in(alt_inhalt, neu_inhalt)
    e_da = bool(lade_datei(neu, DATEI_ENTSCHEIDUNGEN)[0].strip())
    t = parse(quelle)
    print(f"Umzug der Tafel nach {TAFEL_ORDNER} ({ziel}):")
    print(f"  1) {TAFEL_ORDNER} origin/{BRANCH}: "
          + ("uebersprungen — Tafel schon da" if neu_da else
             f"SESSIONS.md ({len(quelle.encode('utf-8'))} Bytes, "
             f"{len(t['claims'])} Claims, {len(t['blocker'])} Blocker)"
             + ("" if e_da else " + leere ENTSCHEIDUNGEN.md")))
    print(f"  2) origin/{BRANCH_ALT}: "
          + ("uebersprungen — Hinweis steht schon" if alt_umgezogen else
             f"letzter Commit, SESSIONS.md -> Hinweis „{UMZUG_MARKE} am "
             f"{datum}; Historie bleibt hier“ (Branch bleibt bestehen)"))
    if nachtrag:
        print(f"⚠ Auf origin/{BRANCH_ALT} stehen {len(nachtrag)} Zeile(n), die "
              f"in {TAFEL_ORDNER} fehlen — nach dem Umzug von Hand uebertragen:",
              file=sys.stderr)
        for z in nachtrag:
            print(f"    {z}", file=sys.stderr)
    if args.trocken:
        print("(--trocken: nichts geschrieben)")
        return 0

    if not neu_da:
        dateien = {DATEI: quelle if quelle.endswith("\n") else quelle + "\n"}
        if not e_da:
            dateien[DATEI_ENTSCHEIDUNGEN] = rendere_entscheidungen(
                parse_entscheidungen(""))
        if not _schreibe_dateien(neu, dateien, neu_spitze,
                                 f"umzug: Tafel aus origin/{BRANCH_ALT} ({wer}, {datum})"):
            print(f"{TAFEL_ORDNER}: Push abgelehnt — dort hat jemand gleichzeitig "
                  "geschrieben. Nichts verloren; umzug erneut ausfuehren.",
                  file=sys.stderr)
            return 1
        print(f"  ✓ {TAFEL_ORDNER}: Tafel geschrieben")
    if not alt_umgezogen:
        if not _schreibe_dateien(alt, {DATEI: hinweis}, alt_spitze,
                                 f"umzug: Tafel {UMZUG_MARKE} am {datum}"):
            print(f"origin/{BRANCH_ALT}: Push abgelehnt — dort hat jemand "
                  "waehrend des Umzugs geschrieben. Die neue Tafel steht; umzug "
                  "erneut ausfuehren, er zeigt die nachzutragenden Zeilen.",
                  file=sys.stderr)
            return 1
        print(f"  ✓ origin/{BRANCH_ALT}: Hinweis gesetzt (Branch bleibt, Historie bleibt)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--repo", default=code_repo_wurzel(),
                   help="Code-Repo (fuer LIGHTOS_TAFEL=alt und umzug; "
                        "Vorgabe: das Repo dieses Werkzeugs)")
    p.add_argument("--tafel", metavar="PFAD",
                   help="Klon des privaten Tafel-Repos (Vorgabe: "
                        "LIGHTOS_TAFEL_REPO, sonst <Projektordner>/lightos-intern)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("list", help="Wer arbeitet gerade woran?")
    s.add_argument("--blocker", type=int, default=_BLOCKER_VORGABE,
                   help=f"Wieviele der juengsten Blocker zeigen "
                        f"(Vorgabe {_BLOCKER_VORGABE}; 0 = keine, -1 = alle)")
    s.add_argument("--fuer", metavar="SITZUNG",
                   help="nur Blocker mit 'AN <SITZUNG>' (auch 'AN … UND <SITZUNG>', "
                        "'AN ALLE') nach deren letztem eigenen Eintrag")
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("claim", help="Item belegen")
    s.add_argument("item")
    s.add_argument("--session", required=True)
    s.add_argument("--branch")
    s.add_argument("--files", nargs="*",
                   help="Dateien/Ordner, die das Item aendert (Ordner = alles "
                        "darunter); wird gegen die Claims anderer Items geprueft")
    s.add_argument("--strikt", action="store_true",
                   help="bei Dateiueberschneidung NICHT belegen, Exit 2")
    s.set_defaults(fn=cmd_claim)

    s = sub.add_parser("refresh", help="Claim auffrischen (laenger als 4 h dran)")
    s.add_argument("item")
    s.add_argument("--session", required=True)
    s.set_defaults(fn=cmd_refresh)

    s = sub.add_parser("release", help="Item freigeben")
    s.add_argument("item")
    s.add_argument("--session", required=True)
    s.add_argument("--status", default="done",
                   choices=["done", "abgebrochen", "uebergeben"])
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_release)

    s = sub.add_parser("blocker", help="Falle/Blocker fuer die andere Sitzung")
    s.add_argument("text", nargs="?")
    s.add_argument("--datei", metavar="PFAD",
                   help="Text aus Datei (UTF-8) lesen, '-' = stdin; "
                        "vermeidet Backtick-/Quoting-Fallen der Shell. "
                        "Windows PowerShell 5.1: Pipe verliert Umlaute "
                        "($OutputEncoding = US-ASCII) — dort Dateiweg nehmen "
                        "(UTF-8) oder $OutputEncoding = "
                        "[Text.UTF8Encoding]::new()")
    s.add_argument("--session", required=True)
    s.add_argument("--remove", action="store_true")
    s.set_defaults(fn=cmd_blocker)

    s = sub.add_parser("entscheidung", help="offene Entscheidungen (ENTSCHEIDUNGEN.md)")
    s.add_argument("aktion", choices=["add", "list", "done"])
    s.add_argument("text", nargs="?", help="add: die Frage; done: die Nummer (E-3)")
    s.add_argument("--session")
    s.add_argument("--notiz", help="done: wie entschieden wurde")
    s.add_argument("--alle", action="store_true", help="list: auch erledigte")
    s.set_defaults(fn=cmd_entscheidung)

    s = sub.add_parser("umzug", help="PROC-25: Tafel einmalig von origin/sessions "
                                     "ins private Tafel-Repo ziehen")
    s.add_argument("--session", help="wer umzieht (nur fuer die Commit-Nachricht)")
    s.add_argument("--trocken", action="store_true", help="nur anzeigen")
    s.set_defaults(fn=None)

    args = p.parse_args(argv)
    try:
        if args.cmd == "umzug":
            return cmd_umzug(args)
        try:
            ort = tafel_ort(args.repo, args.tafel)
        except TafelFehlt as e:
            print(e, file=sys.stderr)
            return 3
        return args.fn(args, ort)
    except ZugangsdatenGesperrt as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    # XPLAT-20: Windows-Konsolen und -Pipes laufen ohne PYTHONUTF8 auf cp1252.
    # Die Statuszeichen dieses Werkzeugs (✓ ⚠ ★ ⏳) haben dort keine Abbildung,
    # der Bericht stirbt also mitten in der Ausgabe an einem UnicodeEncodeError.
    # Bewusst HIER und nicht auf Modulebene: beim Import (Tests laden die
    # Werkzeuge per exec_module) bleibt der Datenstrom des Aufrufers unberuehrt.
    for _strom in (sys.stdout, sys.stderr):
        if hasattr(_strom, "reconfigure"):
            _strom.reconfigure(encoding="utf-8")
    raise SystemExit(main())
