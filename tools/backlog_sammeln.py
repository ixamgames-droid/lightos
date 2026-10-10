#!/usr/bin/env python3
"""BACKLOG-Fragmente sammeln — und direkte BACKLOG-Aenderungen melden (PROC-20).

Warum es das gibt
-----------------
Jeder Feature-PR aenderte bisher ``BACKLOG.md``: eine neue Zeile oder der
Status ``review (Zweig …)``. Zwei Folgen, beide taeglich zu sehen:

* **Nach JEDEM Merge kollidieren die naechsten PRs** in ``BACKLOG.md`` — und
  GitHub startet fuer einen PR mit Konflikt nicht einmal die CI.
* **Gemergte Items bleiben auf ``review`` stehen.** Der Status wurde VOR dem
  Merge geschrieben; nach dem Merge fasst ihn niemand mehr an, und das
  Dashboard zaehlt das Item nicht als erledigt.

Die Antwort ist dasselbe Muster wie beim CHANGELOG (PROC-09,
``tools/changelog_sammeln.py``): **je Item eine eigene Datei** unter
``backlog.d/``. Zwei PRs legen zwei verschiedene Dateien an und koennen nicht
kollidieren. Erst ein Sammel-Lauf (EINE Sitzung, kleiner eigener PR) schreibt
sie in ``BACKLOG.md`` — und weil er NACH dem Merge laeuft, kennt er die
PR-Nummer und macht aus ``review`` gleich ``done``.

Fragment-Format
---------------
Dateiname ``<ID>.md`` (z. B. ``backlog.d/PROC-20.md``). Oben Kopfzeilen
``Name: Wert``, dann eine Leerzeile, dann Freitext::

    ID: PROC-20
    Prioritaet: P2
    Status: review
    Titel: Backlog-Konflikte abschaffen

    Was fehlt, woran man es merkt, wann es erledigt ist.

=================  ==========================================================
``ID``             Pflicht, gleich dem Dateinamen
``Status``         Pflicht: ``todo`` · ``review`` · ``done`` · ``teils`` ·
                   ``blocked``
``Prioritaet``     ``P1``/``P2``/``P3`` — Pflicht fuer ein NEUES Item
``Titel``          Pflicht fuer ein NEUES Item
``Status-Notiz``   optional, eine Zeile, landet hinter dem Status
``Nach``           optional: ID der Zeile, hinter der ein neues Item stehen
                   soll (sonst: hinter der hoechsten Nummer derselben Gruppe)
Freitext           die Details-Spalte eines NEUEN Items (mehrere Zeilen
                   werden zu einer)
=================  ==========================================================

Ein senkrechter Strich ist im Fragment nicht erlaubt — er wuerde die
Tabellenzeile zerschneiden.

Was der Sammel-Lauf tut
-----------------------
* **ID steht noch nicht in BACKLOG.md** -> neue Tabellenzeile, mit so vielen
  Spalten wie die Tabelle an der Einfuegestelle hat.
* **ID steht schon dort** -> NUR die Statusspalte wird ersetzt. Titel,
  Prioritaet und Details der Zeile bleiben, wie sie sind. Freitext im Fragment
  wird dann NICHT uebernommen; der Lauf meldet das als Hinweis.
* **``review``** wird zu ``done (<Datum>, [PR #N](…))``. Die Nummer kommt aus
  dem Betreff des letzten Commits, der das Fragment angefasst hat
  (Squash-Merge: ``… (#N)``), oder aus ``--pr N``. **Ohne Nummer bleibt das
  Fragment liegen** — dann ist der PR noch nicht gemergt, und ein Item, das
  als ``review`` in BACKLOG.md einrastet, ist genau der Schaden von oben.
* Uebernommene Fragmente werden geloescht. Ein zweiter Lauf aendert nichts.

Aufruf::

    ./venv/bin/python tools/backlog_sammeln.py --pruefen   # nur Form pruefen
    ./venv/bin/python tools/backlog_sammeln.py --dry-run   # zeigen, nichts schreiben
    ./venv/bin/python tools/backlog_sammeln.py             # eintragen + loeschen
    ./venv/bin/python tools/backlog_sammeln.py --waechter  # BACKLOG.md direkt geaendert?

Windows entsprechend mit ``venv/Scripts/python``.

Der Waechter WARNT nur
----------------------
``--waechter`` (und ``tests/test_backlog_fragmente.py``) meldet, wenn der
Zweig ``BACKLOG.md`` seit der Abzweigung von ``origin/main`` geaendert hat —
mit Exit 0. Offene PRs alter Art, die ihre Zeile noch direkt eintragen,
bleiben gueltig, und der Sammel-PR aendert die Datei absichtlich (Betreff
``backlog: …`` bzw. eingesammelte Fragmente — dann schweigt der Waechter).
Ohne ``origin/main`` (CI-Checkout) oder ausserhalb von Git: still.
"""
from __future__ import annotations

import argparse
import datetime
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FRAGMENT_ORDNER = "backlog.d"
BACKLOG = "BACKLOG.md"
MARKER = "backlog:"
PR_URL = "https://github.com/ixamgames-droid/lightos/pull/{nr}"

STATUS = ("todo", "review", "done", "teils", "blocked")
PRIOS = ("P1", "P2", "P3")
KOPFZEILEN = ("ID", "Prioritaet", "Status", "Titel", "Status-Notiz", "Nach")

# Deckungsgleich mit ROW in tests/test_backlog_lint.py und tools/backlog_compact.py.
ID_MUSTER = r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+[a-z]?"
FRAGMENT_NAME = re.compile(rf"^({ID_MUSTER})\.md$")
_KOPF = re.compile(r"^([A-Za-z][A-Za-z-]*):\s*(.*)$")
_TRENNZEILE = re.compile(r"^\|[\s:|-]+\|?\s*$")
_ZAEHLER = re.compile(r"^(.*?)-(\d+)[a-z]*$")
_PR_IM_BETREFF = (re.compile(r"\(#(\d+)\)\s*$"),
                  re.compile(r"^Merge pull request #(\d+)\b"))


class Fragment:
    """Ein gelesenes Fragment. Bewusst keine ``dataclass``: die Tests laden die
    Werkzeuge per ``exec_module`` ohne Eintrag in ``sys.modules``, und daran
    scheitert ``dataclasses`` mit ``from __future__ import annotations``."""

    def __init__(self, id: str, status: str, prio: str = "", titel: str = "",
                 notiz: str = "", nach: str = "", details: str = "",
                 datei: str = ""):
        self.id, self.status, self.prio, self.titel = id, status, prio, titel
        self.notiz, self.nach, self.details, self.datei = notiz, nach, details, datei


# --------------------------------------------------------------------------- git

def _git(repo: Path, *args: str) -> tuple[int, str]:
    """Nur lesend; UTF-8 fest, sonst stirbt es auf Windows an ★/— (XPLAT-20)."""
    try:
        p = subprocess.run(("git", *args), cwd=str(repo), capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return 1, ""
    return p.returncode, p.stdout


def pr_aus_git(repo: Path, relpfad: str) -> tuple[int | None, str | None]:
    """``(PR-Nummer, Datum)`` des Merges, der das Fragment nach ``main`` brachte.

    Gelesen wird der Betreff des LETZTEN Commits, der die Datei angefasst hat.
    Nach einem Squash-Merge endet er auf ``(#N)``. Hat die Datei noch nicht
    committete Aenderungen oder traegt der Betreff keine Nummer, gibt es
    ``(None, None)`` — raten waere schlimmer als nichts."""
    rc, status = _git(repo, "status", "--porcelain", "--", relpfad)
    if rc != 0 or status.strip():
        return None, None
    rc, aus = _git(repo, "log", "-1", "--format=%cs%x09%s", "--", relpfad)
    if rc != 0 or "\t" not in aus:
        return None, None
    datum, betreff = aus.strip().split("\t", 1)
    for muster in _PR_IM_BETREFF:
        m = muster.search(betreff)
        if m:
            return int(m.group(1)), datum
    return None, None


# --------------------------------------------------------------------- Fragmente

def _lies_text(pfad: Path) -> str:
    # newline=None vereinheitlicht CRLF (Windows-Checkout) zu \n.
    with open(pfad, "r", encoding="utf-8", newline=None) as f:
        return f.read()


def lies_fragment(name: str, text: str) -> tuple[Fragment | None, list[str]]:
    """``(Fragment, Formfehler)`` — bei Fehlern ist das Fragment ``None``."""
    fehler: list[str] = []
    m_name = FRAGMENT_NAME.match(name)
    if not m_name:
        fehler.append(f"{name}: Dateiname ist keine Backlog-ID (<ID>.md, z. B. PROC-20.md)")
    if "|" in text:
        fehler.append(f"{name}: senkrechter Strich '|' zerschneidet die Tabellenzeile "
                      "— umschreiben (z. B. 'bzw.' oder '/')")
    zeilen = text.split("\n")
    kopf: dict[str, str] = {}
    i = 0
    while i < len(zeilen) and zeilen[i].strip():
        m = _KOPF.match(zeilen[i])
        if not m:
            fehler.append(f"{name}:{i + 1}: erwartet 'Name: Wert' (Kopfzeilen bis zur "
                          "ersten Leerzeile, Freitext erst danach)")
        elif m.group(1) not in KOPFZEILEN:
            fehler.append(f"{name}:{i + 1}: unbekannte Kopfzeile {m.group(1)!r} "
                          f"(erlaubt: {', '.join(KOPFZEILEN)})")
        elif m.group(1) in kopf:
            fehler.append(f"{name}:{i + 1}: Kopfzeile {m.group(1)!r} steht doppelt")
        else:
            kopf[m.group(1)] = m.group(2).strip()
        i += 1
    details = " ".join(z.strip() for z in zeilen[i:] if z.strip())
    if not text.strip():
        fehler.append(f"{name}: Fragment ist leer")
        return None, fehler
    if not kopf.get("ID"):
        fehler.append(f"{name}: Kopfzeile 'ID:' fehlt")
    elif m_name and kopf["ID"] != m_name.group(1):
        fehler.append(f"{name}: 'ID: {kopf['ID']}' passt nicht zum Dateinamen")
    if not kopf.get("Status"):
        fehler.append(f"{name}: Kopfzeile 'Status:' fehlt")
    elif kopf["Status"] not in STATUS:
        fehler.append(f"{name}: Status {kopf['Status']!r} unbekannt "
                      f"(erlaubt: {', '.join(STATUS)})")
    if kopf.get("Prioritaet") and kopf["Prioritaet"] not in PRIOS:
        fehler.append(f"{name}: Prioritaet {kopf['Prioritaet']!r} unbekannt "
                      f"(erlaubt: {', '.join(PRIOS)})")
    if kopf.get("Nach") and not re.fullmatch(ID_MUSTER, kopf["Nach"]):
        fehler.append(f"{name}: 'Nach: {kopf['Nach']}' ist keine Backlog-ID")
    if fehler:
        return None, fehler
    return Fragment(id=kopf["ID"], status=kopf["Status"],
                    prio=kopf.get("Prioritaet", ""),
                    titel=kopf.get("Titel", "").strip("* ").strip(),
                    notiz=kopf.get("Status-Notiz", ""), nach=kopf.get("Nach", ""),
                    details=details, datei=name), []


def fragmente(repo: Path = REPO) -> list[Path]:
    """Alle ``*.md`` in ``backlog.d/`` ausser der README, nach Namen sortiert."""
    ordner = repo / FRAGMENT_ORDNER
    if not ordner.is_dir():
        return []
    return sorted((p for p in ordner.iterdir()
                   if p.is_file() and p.suffix == ".md" and p.name != "README.md"),
                  key=lambda p: p.name)


def fremde_dateien(repo: Path = REPO) -> list[str]:
    """Dateien in ``backlog.d/``, die weder ``*.md`` noch Punktdatei sind — ein
    ``PROC-20.txt`` wuerde sonst still nie gesammelt."""
    ordner = repo / FRAGMENT_ORDNER
    if not ordner.is_dir():
        return []
    return sorted(p.name for p in ordner.iterdir()
                  if p.is_file() and p.suffix != ".md" and not p.name.startswith("."))


def lies_alle(repo: Path = REPO) -> tuple[list[Fragment], list[str]]:
    """Alle Fragmente samt Formfehlern; eine ID in zwei Dateien ist ein Fehler."""
    fehler = [f"{FRAGMENT_ORDNER}/{n}: kein Fragment (erwartet <ID>.md)"
              for n in fremde_dateien(repo)]
    gut: list[Fragment] = []
    je_id: dict[str, list[str]] = {}
    for p in fragmente(repo):
        text = _lies_text(p)
        f, fe = lies_fragment(p.name, text)
        fehler.extend(fe)
        if f:
            gut.append(f)
        # Auch ein sonst kaputtes Fragment zaehlt fuer die Doppel-Pruefung.
        m = re.search(r"^ID:\s*(\S+)", text, re.M)
        if m:
            je_id.setdefault(m.group(1), []).append(p.name)
    for id_, namen in sorted(je_id.items()):
        if len(namen) > 1:
            fehler.append(f"zwei Fragmente fuer {id_}: {', '.join(namen)} — "
                          "zu EINER Datei zusammenfuehren")
    return gut, fehler


def fragment_ids(repo: Path = REPO) -> set[str]:
    return {m.group(1) for p in fragmente(repo)
            if (m := FRAGMENT_NAME.match(p.name))}


def backlog_ids(repo: Path = REPO) -> set[str]:
    pfad = repo / BACKLOG
    if not pfad.is_file():
        return set()
    return {m.group(1) for z in _lies_text(pfad).split("\n")
            if (m := _ZEILE.match(z))}


def bekannte_ids(repo: Path = REPO) -> set[str]:
    """Jede ID, die als BACKLOG-Zeile ODER als Fragment vorliegt.

    Fuer Gates, die wissen wollen, ob es ein Item gibt: ein Fragment zaehlt
    gleichwertig, sonst waere der neue Ablauf (kein PR fasst BACKLOG.md an)
    mit keinem solchen Gate vereinbar."""
    return backlog_ids(repo) | fragment_ids(repo)


# ----------------------------------------------------------------------- Tabelle

_ZEILE = re.compile(rf"^\|\s*({ID_MUSTER})\s*\|([^|]*)\|([^|]*)\|")


def _gruppe(item_id: str) -> tuple[str, int]:
    """``FM-30`` -> ``("FM", 30)``; ohne Zaehler ``("LAS-HW", -1)``."""
    m = _ZAEHLER.match(item_id)
    if m:
        return m.group(1), int(m.group(2))
    return item_id.rsplit("-", 1)[0], -1


def _zeile_von(zeilen: list[str], item_id: str) -> int | None:
    for i, z in enumerate(zeilen):
        m = _ZEILE.match(z)
        if m and m.group(1) == item_id:
            return i
    return None


def _spalten(zeilen: list[str], i: int) -> int:
    """Spaltenzahl der Tabelle, in der Zeile ``i`` steht (aus der Trennzeile)."""
    while i >= 0 and zeilen[i].startswith("|"):
        if _TRENNZEILE.match(zeilen[i]):
            return zeilen[i].strip().strip("|").count("|") + 1
        i -= 1
    return 5


def _status_zelle(f: Fragment, pr: tuple[int | None, str | None]) -> str:
    nr, datum = pr
    if f.status in ("review", "done") and nr:
        kern = f"done ({datum}, [PR #{nr}]({PR_URL.format(nr=nr)}))"
    else:
        kern = f.status
    return f"{kern} — {f.notiz}" if f.notiz else kern


def baue_backlog(text: str, frags: list[Fragment],
                 pr_je_id: dict[str, tuple[int | None, str | None]]
                 ) -> tuple[str, list[str], list[Fragment], list[str]]:
    """``(neuer Text, Protokoll, uebernommene Fragmente, Fehler)``.

    Rein: kein Dateizugriff, kein Git. Bei Fehlern ist der Text unveraendert."""
    zeilen = text.split("\n")
    protokoll: list[str] = []
    fehler: list[str] = []
    fertig: list[Fragment] = []
    # Neue Items in Nummernfolge: FM-66 soll hinter der eben eingefuegten FM-65
    # landen, nicht davor.
    for f in sorted(frags, key=lambda f: (_gruppe(f.id), f.id)):
        pr = pr_je_id.get(f.id, (None, None))
        # ★ Erst pruefen, dann ueber "bleibt liegen" entscheiden: sonst faellt
        # ein unvollstaendiges 'review'-Fragment im PR durch --pruefen und
        # scheitert erst beim Sammeln auf main, wo es niemand mehr erwartet.
        wartet = f.status == "review" and not pr[0]
        zelle = _status_zelle(f, pr)
        i = _zeile_von(zeilen, f.id)
        anker = None
        if i is None:
            fehlt = [n for n, w in (("Prioritaet", f.prio), ("Titel", f.titel)) if not w]
            if fehlt:
                fehler.append(f"{f.datei}: {f.id} steht nicht in {BACKLOG} — fuer ein "
                              f"neues Item fehlt: {', '.join(fehlt)}")
                continue
            if f.nach:
                anker = _zeile_von(zeilen, f.nach)
                # Das Ziel darf auch ein Fragment desselben Laufs sein, das
                # noch auf seinen Merge wartet — dann klaert es sich spaeter.
                if anker is None and f.nach not in {g.id for g in frags}:
                    fehler.append(f"{f.datei}: 'Nach: {f.nach}' — diese Zeile gibt "
                                  f"es in {BACKLOG} nicht")
                    continue
            else:
                gruppe = _gruppe(f.id)[0]
                kandidaten = [(_gruppe(m.group(1))[1], n) for n, z in enumerate(zeilen)
                              if (m := _ZEILE.match(z)) and _gruppe(m.group(1))[0] == gruppe]
                if kandidaten:
                    anker = max(kandidaten)[1]
                elif not any(_gruppe(g.id)[0] == gruppe and g is not f for g in frags):
                    fehler.append(f"{f.datei}: Gruppe {gruppe!r} gibt es in {BACKLOG} "
                                  "noch nicht — mit 'Nach: <ID>' sagen, hinter welche Zeile")
                    continue
        if wartet or (i is None and anker is None):
            protokoll.append(
                f"bleibt liegen: {f.id} ist 'review' und hat keine PR-Nummer "
                "(noch nicht gemergt? sonst --pr N)" if wartet else
                f"bleibt liegen: {f.id} wartet auf die Zeile, hinter die es soll")
            continue
        if i is not None:
            m = _ZEILE.match(zeilen[i])
            neu = (zeilen[i][:m.start(3)] + f" {zelle} " + zeilen[i][m.end(3):])
            protokoll.append(f"Status {f.id}: {m.group(3).strip()[:60]} -> {zelle}"
                             if neu != zeilen[i] else f"unveraendert: {f.id}")
            if f.details:
                # Review-Fund: der Freitext faellt mit dem Fragment weg. Das
                # ist gewollt (nur die Statusspalte), darf aber nicht still
                # passieren — --dry-run zeigt es, bevor geloescht wird.
                protokoll.append(
                    f"Hinweis {f.id}: die Zeile gibt es schon — der Freitext des "
                    "Fragments wird NICHT uebernommen (nur der Status; Kurzes "
                    "gehoert in 'Status-Notiz')")
            zeilen[i] = neu
            fertig.append(f)
            continue
        if _spalten(zeilen, anker) <= 4:
            rumpf = f"**{f.titel}** {f.details}".rstrip()
        else:
            rumpf = f"**{f.titel}** | {f.details}".rstrip()
        zeile = f"| {f.id} | {f.prio} | {zelle} | {rumpf} |"
        zeilen.insert(anker + 1, zeile)
        protokoll.append(f"neu hinter {_ZEILE.match(zeilen[anker]).group(1)}: {zeile}")
        fertig.append(f)
    if fehler:
        return text, protokoll, [], fehler
    return "\n".join(zeilen), protokoll, fertig, []


def sammeln(repo: Path = REPO, *, pruefen: bool = False, dry_run: bool = False,
            pr: int | None = None, heute: str | None = None,
            ausgabe=print) -> int:
    """Exit-Code: 0 ok/nichts zu tun, 1 Fehler (dann wird NICHTS geschrieben)."""
    frags, fehler = lies_alle(repo)
    neu, protokoll, fertig = "", [], []
    pfad = repo / BACKLOG
    crlf = False
    if not fehler and frags:
        heute = heute or datetime.date.today().isoformat()
        pr_je_id = {}
        for f in frags:
            nr, datum = pr_aus_git(repo, f"{FRAGMENT_ORDNER}/{f.datei}")
            if pr:      # ausdruecklich genannt schlaegt geraten
                nr, datum = pr, heute
            pr_je_id[f.id] = (nr, datum)
        roh = pfad.read_bytes().decode("utf-8")
        crlf = "\r\n" in roh
        alt = roh.replace("\r\n", "\n")
        neu, protokoll, fertig, fehler = baue_backlog(alt, frags, pr_je_id)
    if fehler:
        for f in fehler:
            ausgabe(f"[backlog] FEHLER: {f}")
        return 1
    if not frags:
        ausgabe("[backlog] keine Fragmente — nichts zu sammeln.")
        return 0
    ausgabe(f"[backlog] {len(frags)} Fragment(e), {len(fertig)} uebernehmbar:")
    for z in protokoll:
        ausgabe(f"  {z}")
    if pruefen or dry_run:
        ausgabe(f"[backlog] {'--pruefen' if pruefen else '--dry-run'}: "
                "nichts geschrieben, nichts geloescht.")
        return 0
    if neu != alt:
        pfad.write_bytes((neu.replace("\n", "\r\n") if crlf else neu).encode("utf-8"))
    for f in fertig:
        (repo / FRAGMENT_ORDNER / f.datei).unlink()
    if fertig:
        ausgabe(f"[backlog] {BACKLOG} geschrieben, {len(fertig)} Fragment(e) entfernt. "
                f"Commit z. B. mit Betreff '{MARKER} sammeln'.")
    return 0


# ---------------------------------------------------------------------- Waechter

def direkte_aenderung(repo: Path = REPO, basis: str = "origin/main") -> str:
    """Hinweistext, wenn der Zweig ``BACKLOG.md`` selbst geaendert hat — sonst ``""``.

    ★ Nur ein HINWEIS, nie ein Fehler (Uebergang): offene PRs, die ihre Zeile
    noch direkt eintragen, bleiben gueltig. Leer auch ohne ``origin/main``,
    ohne Merge-Basis oder ausserhalb von Git — so laeuft die CI. Gerechnet wird
    ueber die Merge-Basis, damit ein Zweig hinter ``main`` die dort inzwischen
    gesammelten Zeilen nicht angelastet bekommt. Ein Sammel-Lauf (Fragmente der
    Abzweigung sind weg) und ein Commit mit Betreff ``backlog: …`` schweigen."""
    rc, _ = _git(repo, "rev-parse", "--verify", "-q", f"{basis}^{{commit}}")
    if rc != 0:
        return ""
    rc, mb = _git(repo, "merge-base", basis, "HEAD")
    mb = mb.strip()
    if rc != 0 or not mb:
        return ""
    rc, diff = _git(repo, "diff", "--numstat", mb, "--", BACKLOG)
    if rc != 0 or not diff.strip():
        return ""
    rc, betreffe = _git(repo, "log", "--format=%s", f"{mb}..HEAD", "--", BACKLOG)
    if rc == 0 and any(b.strip().lower().startswith(MARKER)
                       for b in betreffe.splitlines()):
        return ""
    rc, namen = _git(repo, "ls-tree", "-r", "--name-only", mb, "--",
                     f"{FRAGMENT_ORDNER}/")
    if rc == 0 and any(FRAGMENT_NAME.match(n.rsplit("/", 1)[-1])
                       and not (repo / n).exists() for n in namen.split()):
        return ""       # Sammel-Lauf
    plus, minus = (diff.split() + ["?", "?"])[:2]
    return (f"{BACKLOG} wurde auf diesem Zweig direkt geaendert (+{plus}/-{minus} "
            f"Zeilen). Das bleibt gueltig, kollidiert aber mit jedem anderen PR, der "
            f"dasselbe tut. Neuer Ablauf (PROC-20): je Item ein Fragment "
            f"{FRAGMENT_ORDNER}/<ID>.md anlegen, {BACKLOG} unberuehrt lassen — "
            f"siehe {FRAGMENT_ORDNER}/README.md.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pruefen", action="store_true",
                    help="nur pruefen: nichts schreiben, Exit 1 bei kaputtem Fragment")
    ap.add_argument("--dry-run", action="store_true",
                    help="zeigen, was eingetragen wuerde — nichts schreiben/loeschen")
    ap.add_argument("--pr", type=int, metavar="N",
                    help="PR-Nummer fuer 'done (…, PR #N)', falls sie nicht aus "
                         "der Historie hervorgeht (gilt fuer ALLE Fragmente des Laufs)")
    ap.add_argument("--waechter", action="store_true",
                    help="melden, wenn der Zweig BACKLOG.md direkt geaendert hat "
                         "(nur Hinweis, Exit immer 0)")
    ap.add_argument("--repo", type=Path, default=REPO, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.waechter:
        hinweis = direkte_aenderung(a.repo)
        print(f"[backlog] HINWEIS: {hinweis}" if hinweis
              else "[backlog] Waechter: BACKLOG.md auf diesem Zweig unberuehrt.")
        return 0
    return sammeln(a.repo, pruefen=a.pruefen, dry_run=a.dry_run, pr=a.pr)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass
    os.chdir(REPO)
    sys.exit(main())
