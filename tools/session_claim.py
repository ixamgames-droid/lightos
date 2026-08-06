#!/usr/bin/env python3
"""session_claim.py — Belegzettel fuer parallel arbeitende Claude-Sitzungen.

Seit dem 2026-08-06 arbeiten mehrere Claude-Instanzen gleichzeitig an LightOS.
Sie sehen einander **nur ueber dieses Repo**. Die Regel, aus der alles folgt:

    Was nicht gepusht ist, existiert fuer die andere Sitzung nicht.

Dieses Werkzeug pflegt die Tafel ``SESSIONS.md`` auf dem Branch ``sessions``
und macht daraus einen belastbaren Beleg statt einer Absichtserklaerung.

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
    python tools/session_claim.py refresh OUT-51 --session B
    python tools/session_claim.py release OUT-51 --session B --status done
    python tools/session_claim.py blocker "Rig haengt am Enttec — nicht neu starten" \\
        --session A

Regeln stehen in ``COORDINATION.md``.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

BRANCH = "sessions"
DATEI = "SESSIONS.md"

# Ein Claim verfaellt, wenn die Sitzung ihn nicht auffrischt. Vier Stunden sind
# lang genug fuer ein grosses Item samt vollem Gate (~15 min) und kurz genug,
# dass eine abgestuerzte Sitzung das Item nicht ueber Nacht blockiert.
VERFALL = timedelta(hours=4)

_KOPF = """# SESSIONS.md — wer arbeitet gerade woran

<!-- Gepflegt von tools/session_claim.py. Branch `sessions`, wird NIE nach main
     gemergt. Von Hand editieren ist moeglich, verliert aber die Konflikt-
     erkennung: erst der abgelehnte Push macht sichtbar, dass jemand schneller
     war. Spielregeln: COORDINATION.md -->
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


def pruefe_oeffentlich(text: str) -> list[str]:
    """PRIV-01/02: was in ein oeffentliches Repo nicht hineingehoert.

    Die Tafel liegt auf GitHub. Ein Blocker-Text ist Freitext und damit die
    einzige Stelle dieses Werkzeugs, an der versehentlich Privates landen kann
    — deshalb wird genau hier geprueft und nicht am Ende von irgendetwas.
    """
    funde = []
    if re.search(r"/home/(?!user\b|runner\b)[a-z][a-z0-9_-]+/", text):
        funde.append("Home-Pfad mit Kontonamen (nutze /home/user/…)")
    if re.search(r"[A-Za-z]:\\Users\\(?!X\b)[A-Za-z]", text):
        funde.append("Windows-Nutzerpfad (nutze C:\\Users\\X\\…)")
    if "claude.ai/code/session" in text:
        funde.append("Sitzungs-Link")
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text):
        funde.append("E-Mail-Adresse")
    return funde


# ─────────────────────────────────────────────────────────────────────────────
# Git-Schicht
# ─────────────────────────────────────────────────────────────────────────────

def _git(*args: str, eingabe: str | None = None, repo: str | None = None,
         pruefen: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=repo, input=eingabe,
                       capture_output=True, text=True)
    if pruefen and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def lade_tafel(repo: str) -> tuple[dict, str | None]:
    """Tafel + Spitzen-Commit von ``origin/sessions`` (nicht aus dem Arbeitsbaum).

    Der zweite Rueckgabewert ist der Eltern-Commit fuer den naechsten Schreib-
    vorgang. Er ist die halbe Konflikterkennung: schreiben wir spaeter gegen
    genau diesen Stand und ist der Remote inzwischen weiter, ist der Push kein
    Fast-Forward mehr und wird abgelehnt.
    """
    _git("fetch", "--quiet", "origin",
         f"+refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}",
         repo=repo, pruefen=False)
    spitze = _git("rev-parse", "--verify", "--quiet", f"origin/{BRANCH}",
                  repo=repo, pruefen=False)
    if not spitze:
        return parse(""), None
    inhalt = _git("show", f"{spitze}:{DATEI}", repo=repo, pruefen=False)
    return parse(inhalt), spitze


def schreibe_tafel(repo: str, tafel: dict, eltern: str | None,
                   nachricht: str) -> bool:
    """Tafel committen und pushen. ``False`` = jemand war schneller.

    Ueber Plumbing statt Checkout: der Arbeitsbaum der Sitzung (und der einer
    parallel laufenden!) bleibt unberuehrt.
    """
    blob = _git("hash-object", "-w", "--stdin", eingabe=rendere(tafel), repo=repo)
    baum = _git("mktree", eingabe=f"100644 blob {blob}\t{DATEI}\n", repo=repo)
    args = ["commit-tree", baum, "-m", nachricht]
    if eltern:
        args += ["-p", eltern]
    commit = _git(*args, repo=repo)
    r = subprocess.run(["git", "push", "origin", f"{commit}:refs/heads/{BRANCH}"],
                       cwd=repo, capture_output=True, text=True)
    return r.returncode == 0


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
    if tafel["blocker"]:
        print("\nBlocker:")
        for b in tafel["blocker"]:
            print(f"  - {b}")
    return 0


def cmd_claim(args, repo: str) -> int:
    def aendern(tafel):
        t = jetzt()
        vorhanden = finde(tafel, args.item)
        if vorhanden and vorhanden["sitzung"] == args.session:
            vorhanden["seit"] = stempel(t)
            return True, f"{args.item}: Claim aufgefrischt"
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
    print(meldung)
    return 0 if ok else 1


def cmd_refresh(args, repo: str) -> int:
    args.branch, args.files = None, None
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


def cmd_blocker(args, repo: str) -> int:
    funde = pruefe_oeffentlich(args.text)
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


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--repo", default=os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("list", help="Wer arbeitet gerade woran?")
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("claim", help="Item belegen")
    s.add_argument("item")
    s.add_argument("--session", required=True)
    s.add_argument("--branch")
    s.add_argument("--files", nargs="*")
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
    s.add_argument("text")
    s.add_argument("--session", required=True)
    s.add_argument("--remove", action="store_true")
    s.set_defaults(fn=cmd_blocker)

    args = p.parse_args(argv)
    return args.fn(args, args.repo)


if __name__ == "__main__":
    raise SystemExit(main())
