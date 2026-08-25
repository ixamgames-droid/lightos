#!/usr/bin/env python3
"""Naechste freie Backlog-ID — ueber ALLE Zweige, nicht nur den eigenen.

Warum es dieses Werkzeug gibt
-----------------------------
Zweimal in vier Tagen haben parallel arbeitende Sitzungen dieselbe ID vergeben:

* **22.08.2026:** zwei Agenten legten gleichzeitig ein ``FM-26`` an.
* **25.08.2026:** **drei** Zweige gleichzeitig ein ``FM-30`` — jeder mit anderem
  Inhalt (Return-Speichern / Matrizen zusammenlegen / unerkannte Kanaele).

Die Mechanik ist beide Male dieselbe und hat nichts mit Unachtsamkeit zu tun:
**jeder nimmt die naechste freie Nummer aus dem ``BACKLOG.md``, das ER sieht** —
und das ist der Stand seines Zweiges. Die Zweige der anderen sieht niemand.

``test_ids_are_unique`` (QA-18c) faengt die Kollision zuverlaessig — aber erst,
wenn **zwei** davon gelandet sind. Dann steht sie schon auf ``main``, und das
Aufloesen kostet eine Umbenennung quer durch BACKLOG, CHANGELOG, Tests und
Code-Kommentare. Dieses Werkzeug fragt vorher.

Zwei Fragen
-----------
1. **Welche ID ist frei?** Ueber alle Zweige gerechnet, nicht nur den eigenen.
2. **Gibt es schon eine Kollision?** Dieselbe ID auf zwei Zweigen mit
   VERSCHIEDENEM Titel. Gleicher Titel ist keine Kollision, sondern derselbe
   Eintrag auf zwei Staenden — der haeufige Normalfall.

★ **Der Zuschnitt ist das Entscheidende, und er ist gemessen.** Die erste
Fassung las **alle** 148 Remote-Zweige und beanstandete **316 von rund 500 IDs**
— unbrauchbar. Der Grund ist harmlos: Titel werden ueber Monate umformuliert,
also unterscheidet sich fast jede ID irgendwo. Gezaehlt wird deshalb nur, wo
eine Kollision auch wirklich landen kann: ``main`` plus die Zweige der OFFENEN
PRs. Ein Waechter, der zwei Drittel des Bestands beanstandet, wird abgeschaltet
— dieselbe Lehre wie bei ``backlog_status_drift.py`` (60 Zeilen -> 1).

Aufruf::

    ./venv/bin/python tools/backlog_ids.py                # Kollisionen + Uebersicht
    ./venv/bin/python tools/backlog_ids.py --gruppe FM    # naechste freie FM-Nummer
    ./venv/bin/python tools/backlog_ids.py --strict       # Exit 1 bei Kollision

Braucht die Remote-Refs (``git fetch``) — deshalb ein Werkzeug und kein
CI-Test: ``actions/checkout@v4`` holt **einen** Commit ohne weitere Refs. Ein
Test, der dort still ueberspringt, waere die Sorte Absicherung, die dieses Repo
in PROC-02b und PROC-04 schon zweimal teuer bezahlt hat. Die LOGIK ist trotzdem
festgenagelt (``tests/test_backlog_ids.py``).
"""
from __future__ import annotations

import argparse
import collections
import re
import subprocess
import sys

# | FM-30 | P2 | todo | **Titel** | …
ZEILE = re.compile(r"^\|\s*([A-Za-z][A-Za-z0-9-]*)\s*\|\s*(P[0-9])\s*\|([^|]*)\|([^|]*)\|")
# FM-30 -> ("FM", 30); PROC-02c -> ("PROC", 2); LAS-HW-VERIFY -> kein Zaehler
GETEILT = re.compile(r"^([A-Za-z][A-Za-z0-9]*(?:-[A-Za-z]+)*?)-(\d+)([a-z]*)$")


def zerlege(item_id: str):
    """``("FM", 30, "")`` — oder ``None``, wenn die ID keinen Zaehler hat.

    ``PROC-02c`` -> ``("PROC", 2, "c")``: der Buchstabe hinten ist eine
    Verfeinerung desselben Items, keine eigene Nummer. ``LAS-HW-VERIFY`` hat
    gar keinen Zaehler und faellt heraus — solche IDs gibt es, und sie duerfen
    die Zaehlung nicht durcheinanderbringen.
    """
    m = GETEILT.match(item_id)
    if not m:
        return None
    return m.group(1), int(m.group(2)), m.group(3)


def items_aus_backlog(text: str) -> dict:
    """``{ID: Titel}`` fuer jede Item-Zeile.

    Die zweite Spalte MUSS eine Prioritaet sein — sonst zaehlt die Kopfzeile
    ``| ID | Prio | Status | …`` als Item namens „ID" (derselbe Fehler wie in
    ``backlog_status_drift.py``, dort vom eigenen Test gefunden).
    """
    gefunden = {}
    for z in text.splitlines():
        m = ZEILE.match(z)
        if m:
            gefunden[m.group(1)] = m.group(4).strip()
    return gefunden


def kollisionen(je_zweig: dict, auf_main: set) -> list:
    """``[(ID, {Zweig: Titel})]`` fuer jede NEUE ID mit verschiedenen Titeln.

    Zwei Filter, und beide sind noetig:

    1. **Gleicher Titel ist keine Kollision** — das ist derselbe Eintrag auf
       zwei Staenden, der haeufige Normalfall.
    2. **★ Die ID darf auf ``main`` noch NICHT existieren.** Steht sie dort,
       haben beide Zweige sie geerbt, und ein Titelunterschied ist eine
       Umformulierung, keine doppelte Vergabe. Ohne diesen Filter meldet das
       Werkzeug jedes Item, dessen Titel jemand auf seinem Zweig geschaerft hat
       — gemessen an ``UI-52``, wo aus „Die Gruppen-Legende zaehlt …" auf dem
       eigenen Zweig „Die Legende zaehlt …" wurde. Eine echte Kollision ist per
       Definition NEU: zwei Zweige greifen nach derselben freien Nummer.
    """
    titel_je_id = collections.defaultdict(dict)
    for zweig, items in je_zweig.items():
        for item_id, titel in items.items():
            if item_id not in auf_main:
                titel_je_id[item_id][zweig] = titel
    treffer = []
    for item_id, nach_zweig in sorted(titel_je_id.items()):
        if len(set(nach_zweig.values())) > 1:
            treffer.append((item_id, nach_zweig))
    return treffer


def naechste_freie(je_zweig: dict, gruppe: str) -> int:
    """Eins ueber der HOECHSTEN Nummer der Gruppe — ueber alle Zweige gerechnet.

    ★ Bewusst nicht „die kleinste freie Nummer". Luecken entstehen hier durch
    archivierte oder zurueckgezogene Items, und deren Nummern stehen weiter in
    Commit-Nachrichten, im CHANGELOG und in Code-Kommentaren. Eine Nummer neu zu
    vergeben, die dort schon eine andere Bedeutung hat, waere eine zweite
    Kollision — nur eine, die kein Gate mehr findet, weil beide Eintraege nie
    gleichzeitig im BACKLOG stehen.

    (Der erste Entwurf fuellte Luecken. Der eigene Test hat es gefangen: bei
    ``{FM-29, FM-30}`` lieferte er ``FM-1``.)
    """
    hoechste = 0
    for items in je_zweig.values():
        for item_id in items:
            t = zerlege(item_id)
            if t and t[0] == gruppe:
                hoechste = max(hoechste, t[1])
    return hoechste + 1


# ── Alles ab hier redet mit git ──────────────────────────────────────────────

def _git(*args: str) -> tuple[int, str]:
    p = subprocess.run(("git",) + args, capture_output=True, text=True)
    return p.returncode, p.stdout


# `gh pr list --limit` ist ein HARTES Abschneiden, kein Seitenwechsel. Bei mehr
# offenen PRs als hier faellt der Rest still weg — und ein Werkzeug, das „alle
# offenen PRs" verspricht, darf nicht stillschweigend weniger liefern (CDX-57).
_PR_LIMIT = 200


def offene_pr_zweige() -> tuple:
    """``(Zweignamen, Warnung|None)`` der offenen PRs.

    **Nie stillschweigend weniger liefern:** wer die Liste nicht vollstaendig
    bekommt, bekommt hier einen Grund statt einer kuerzeren Liste.
    """
    p = subprocess.run(
        ("gh", "pr", "list", "--state", "open", "--limit", str(_PR_LIMIT),
         "--json", "headRefName,isCrossRepository,number",
         "-q", ".[] | [.number, .headRefName, (.isCrossRepository|tostring)] | @tsv"),
        capture_output=True, text=True)
    if p.returncode != 0:
        return [], f"`gh pr list` fehlgeschlagen: {p.stderr.strip()[:160]}"
    zeilen = [z.split("\t") for z in p.stdout.splitlines() if z.strip()]
    if len(zeilen) >= _PR_LIMIT:
        return [], (f"mehr als {_PR_LIMIT} offene PRs — `gh pr list --limit` "
                    "schneidet ab, die Liste waere unvollstaendig")
    # ★ Fork-PRs haben keinen `origin/<headRefName>`; sie stumm zu ueberspringen
    # hiesse, Abdeckung zu behaupten, die es nicht gibt.
    fremd = [f"#{n}" for n, _b, cross in zeilen if cross == "true"]
    zweige = [b for _n, b, cross in zeilen if cross != "true"]
    if fremd:
        return zweige, f"aus einem Fork und darum nicht lesbar: {', '.join(fremd)}"
    return zweige, None


def backlog_je_zweig(refs: list) -> dict:
    """``{Ref: {ID: Titel}}`` fuer die genannten Refs, soweit sie ein BACKLOG haben."""
    je_zweig = {}
    for ref in refs:
        rc, text = _git("show", f"{ref}:BACKLOG.md")
        if rc == 0 and text:
            je_zweig[ref] = items_aus_backlog(text)
    return je_zweig


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--gruppe", help="Praefix, z. B. FM oder PROC")
    ap.add_argument("--strict", action="store_true", help="Exit 1 bei Kollision")
    ap.add_argument("--alle-zweige", action="store_true",
                    help="auch gelandete Zweige lesen (viel Rauschen, s. Docstring)")
    ap.add_argument("--kein-fetch", action="store_true",
                    help="nicht vorher `git fetch` — dann gilt der zuletzt geholte Stand")
    args = ap.parse_args(argv)

    if not args.kein_fetch:
        rc, _ = _git("fetch", "--quiet", "--prune", "origin")
        if rc != 0:
            # ★ CDX-57: fail closed. Mit veralteten Refs koennte eine Nummer als
            # frei gemeldet werden, die auf einem neueren Zweig laengst vergeben
            # ist — genau der Schaden, den dieses Werkzeug verhindern soll.
            print("FEHLER: `git fetch` fehlgeschlagen — mit veralteten Refs waere "
                  "jede Auskunft hier wertlos. Netz/Zugang pruefen, oder bewusst "
                  "mit --kein-fetch fahren.")
            return 2

    if args.alle_zweige:
        rc, out = _git("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin")
        refs = [r for r in out.split() if r and not r.endswith("/HEAD")] if rc == 0 else []
        print("[ids] ACHTUNG: --alle-zweige liest auch laengst gelandete Zweige. "
              "Titel werden ueber Monate umformuliert, das meiste davon ist "
              "Rauschen (gemessen: 316 von ~500 IDs).")
    else:
        zweige, warnung = offene_pr_zweige()
        if warnung:
            print(f"[ids] ⚠ {warnung}")
        elif not zweige:
            print("[ids] HINWEIS: keine offenen PRs — geprueft wird nur "
                  "`origin/main`. Das ist WENIGER, als der Name verspricht.")
        refs = ["origin/main"] + [f"origin/{b}" for b in zweige]

    je_zweig = backlog_je_zweig(refs)
    # ★ CDX-57: ein Ref, das nicht lesbar ist, wurde bisher still uebersprungen —
    # das Werkzeug behauptete dann Abdeckung, die es nicht hatte.
    fehlend = [r for r in refs if r not in je_zweig]
    if fehlend:
        print(f"[ids] ⚠ nicht lesbar (uebersprungen): {', '.join(fehlend)}")
    if not je_zweig:
        print("FEHLER: kein Ref mit BACKLOG.md gefunden — sind die Remote-Refs da?")
        return 2

    # ★ Die Abdeckung MUSS mit. Ohne sie sieht „keine Kollision" bei einem
    # einzigen gelesenen Zweig aus wie ein sauberer Bestand.
    print(f"[ids] geprueft: {', '.join(sorted(je_zweig))}")

    auf_main = set(je_zweig.get("origin/main", {}))
    treffer = kollisionen(je_zweig, auf_main)
    if treffer:
        print(f"\n⚠ {len(treffer)} ID(s) doppelt vergeben — VERSCHIEDENE Titel:")
        for item_id, nach_zweig in treffer:
            # Nach TITEL gruppieren, nicht nach Zweig: sonst stehen bei einer
            # Kollision Dutzende identischer Zeilen und die eine abweichende
            # geht darin unter.
            nach_titel = collections.defaultdict(list)
            for zweig, titel in nach_zweig.items():
                nach_titel[titel].append(zweig)
            print(f"  {item_id}:")
            for titel, zweige_ in sorted(nach_titel.items()):
                erst = sorted(zweige_)[0].replace("origin/", "")
                mehr = f" (+{len(zweige_) - 1} weitere)" if len(zweige_) > 1 else ""
                print(f"      {erst}{mehr}:")
                print(f"          {titel[:110]}")
    else:
        print("✓ keine ID mit verschiedenen Titeln.")

    if args.gruppe:
        n = naechste_freie(je_zweig, args.gruppe)
        print(f"\n[ids] naechste freie Nummer der Gruppe {args.gruppe}: "
              f"{args.gruppe}-{n}")
    return 1 if (treffer and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
