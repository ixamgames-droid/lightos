"""Backlog-Verdichter + Queue-View fuer BACKLOG.md (Loop-Werkzeug).

BACKLOG.md ist auf ~290 KB gewachsen — zu gross, um es in einer Loop-Runde am
Stueck zu laden. Dieses Werkzeug macht die Datei wieder loop-tauglich:

  --queue [N]    Die naechsten N offenen Items (todo zuerst, P1 < P2 < P3) als
                 kompakte Liste auf stdout — Ersatz fuer das Voll-Read in
                 /lightos-loop Schritt 1. wip/review-Items werden separat
                 gelistet (laufende Arbeit sichtbar, aber nicht doppelt nehmen).
  --stats        Zaehler je Status/Prio + Dateigroesse + Archivierungs-Potenzial.
  --archive      Verdichtet erledigte Tabellenzeilen gemaess der Konvention in
                 BACKLOG.md ("Ein done-Eintrag wird beim naechsten Beruehren in
                 den Kurz-Log verdichtet"): die VOLLE Zeile wandert nach
                 BACKLOG_ARCHIVE.md, im Original bleibt eine 1-Zeilen-Kurzform
                 (ID, Prio, "done -> Archiv", Bold-Titel + erster PR-Link).
                 Default ist DRY-RUN (nur Report); schreiben mit --apply.

Aufruf (Repo-Root):  venv/Scripts/python.exe tools/backlog_compact.py --queue 10
Reines Stdlib-/Text-Werkzeug — keine src-Imports, keine Show-DB.
Zeilen-Konvention identisch zum Linter tests/test_backlog_lint.py (QA-18).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import sys
from dataclasses import dataclass

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKLOG = os.path.join(_ROOT, "BACKLOG.md")
ARCHIVE = os.path.join(_ROOT, "BACKLOG_ARCHIVE.md")

# Identisch zur QA-18-Lint-Konvention (tests/test_backlog_lint.py).
ROW = re.compile(r"^\|\s*([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|")
PRIO_ORDER = {"P1": 0, "P2": 1, "P3": 2}
# Bold-Titel NUR am Zellenanfang: ein spaeterer '**Fix:**'-Span im Fliesstext
# darf nie zum Titel-Stub werden (Review-Fund 2026-07-19).
BOLD_TITLE = re.compile(r"^\s*\*\*(.+?)\*\*")
# Linktext beliebig ([#270], [PR #100], [Codex #334], [Codex-Review], ...) —
# die enge [#N]-Form verlor real 79 % der PR-Links (Review-Fund 2026-07-19).
PR_LINK = re.compile(r"\[[^\]]*\]\(https://github\.com/[\w.-]+/[\w.-]+/(?:pull|issues)/\d+[^)]*\)")

# Ein Status gilt als "nur noch Historie", wenn er 'done' enthaelt und KEIN
# aktives Keyword mehr — dekorierte Staten wie "wip (3/8 done)" bleiben aktiv.
_ACTIVE_KEYWORDS = ("todo", "wip", "review", "blocked", "decision", "teils", "teil")
# Markdown-Links VOR der Keyword-Erkennung strippen: ein Linktext wie
# "[Codex-Review](...)" in der Status-Zelle ist Dekoration, kein Status —
# sonst zaehlt eine done-Zeile faelschlich als 'review' (Review-Fund 2026-07-19).
_MD_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)")


def _status_text(status: str) -> str:
    return _MD_LINK.sub(" ", status).lower()


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", text) is not None


@dataclass
class Row:
    lineno: int          # 0-basiert (Index in der Zeilenliste)
    id: str
    prio: str
    status: str
    line: str            # komplette Original-Zeile (mit Zeilenende)

    @property
    def status_low(self) -> str:
        """Status-Zelle in Kleinschreibung, Markdown-Links entfernt."""
        return _status_text(self.status)

    @property
    def is_done(self) -> bool:
        low = self.status_low
        return _has_word(low, "done") and not any(_has_word(low, k) for k in _ACTIVE_KEYWORDS)

    @property
    def is_condensed(self) -> bool:
        """Schon frueher von --archive verdichtet -> nie erneut anfassen."""
        return "archiv" in self.status_low

    def active_kind(self) -> str | None:
        """'todo' | 'wip' | 'review' | 'blocked' | 'decision' | None."""
        low = self.status_low
        for kind in ("todo", "wip", "review", "blocked", "decision"):
            if _has_word(low, kind):
                return kind
        return None

    def short_title(self, maxlen: int = 110) -> str:
        # Titel-Zelle = 4. Spalte; Bold-Anfang bevorzugen, sonst Zellen-Anfang.
        cells = self.line.split("|")
        title_cell = cells[4].strip() if len(cells) > 4 else ""
        m = BOLD_TITLE.search(title_cell)
        text = m.group(1) if m else title_cell
        text = re.sub(r"\s+", " ", text).strip()
        return text[: maxlen - 1] + "…" if len(text) > maxlen else text

    def first_pr_link(self) -> str:
        m = PR_LINK.search(self.line)
        return m.group(0) if m else ""


def parse_rows(lines: list[str]) -> list[Row]:
    rows: list[Row] = []
    for i, line in enumerate(lines):
        m = ROW.match(line)
        if not m:
            continue
        prio = m.group(2).strip().strip("* ").strip()
        if set(m.group(2).strip()) <= set("-: "):   # Trennzeile |----|
            continue
        rows.append(Row(i, m.group(1), prio, m.group(3).strip(), line))
    return rows


def _read() -> list[str]:
    with open(BACKLOG, "r", encoding="utf-8") as f:
        return f.readlines()


def cmd_queue(lines: list[str], n: int) -> str:
    rows = parse_rows(lines)
    todo = [r for r in rows if r.active_kind() == "todo"]
    todo.sort(key=lambda r: (PRIO_ORDER.get(r.prio, 9), r.lineno))
    running = [r for r in rows if r.active_kind() in ("wip", "review")]
    out = [f"# Naechste ausfuehrbare Items (todo, P1<P2<P3) — {min(n, len(todo))}/{len(todo)}:"]
    for r in todo[:n]:
        out.append(f"  {r.id}  [{r.prio}]  {r.short_title()}")
    if running:
        out.append(f"# In Arbeit / Review ({len(running)}) — nicht doppelt nehmen:")
        for r in running:
            out.append(f"  {r.id}  [{r.prio}]  ({r.active_kind()})  {r.short_title(80)}")
    return "\n".join(out)


def cmd_stats(lines: list[str]) -> str:
    rows = parse_rows(lines)
    by_kind: dict[str, int] = {}
    for r in rows:
        kind = r.active_kind() or ("done" if _has_word(r.status_low, "done") else "sonstig")
        by_kind[kind] = by_kind.get(kind, 0) + 1
    size = os.path.getsize(BACKLOG)
    archivable = sum(1 for r in rows if r.is_done and not r.is_condensed)
    out = [
        f"BACKLOG.md: {size:,} Bytes, {len(lines)} Zeilen, {len(rows)} Tabellenzeilen",
        "Status: " + ", ".join(f"{k}={v}" for k, v in sorted(by_kind.items())),
        "Prio:   " + ", ".join(
            f"{p}={sum(1 for r in rows if r.prio == p)}" for p in ("P1", "P2", "P3")
        ),
        f"Archivierbar (reine done-Zeilen): {archivable}  -> tools/backlog_compact.py --archive [--apply]",
    ]
    return "\n".join(out)


def archive_split(lines: list[str]) -> tuple[list[str], list[Row]]:
    """Liefert (neue BACKLOG-Zeilen, archivierte Rows). Reine Funktion, schreibt nichts."""
    rows = parse_rows(lines)
    done = [r for r in rows if r.is_done and not r.is_condensed]
    done_idx = {r.lineno: r for r in done}
    new_lines: list[str] = []
    for i, line in enumerate(lines):
        r = done_idx.get(i)
        if r is None:
            new_lines.append(line)
            continue
        pr = r.first_pr_link()
        short = r.short_title(90)
        extra = f" {pr}" if pr else ""
        ending = "\r\n" if line.endswith("\r\n") else "\n"
        new_lines.append(
            f"| {r.id} | {r.prio} | done → Archiv | {short}{extra} "
            f"(Details: BACKLOG_ARCHIVE.md) |{ending}"
        )
    return new_lines, done


def cmd_archive(lines: list[str], apply: bool) -> str:
    new_lines, done = archive_split(lines)
    if not done:
        return "Nichts zu archivieren — keine reine done-Tabellenzeile gefunden."
    report = [f"{'ARCHIVIERE' if apply else 'DRY-RUN (mit --apply schreiben)'}: "
              f"{len(done)} done-Zeilen -> BACKLOG_ARCHIVE.md"]
    for r in done:
        report.append(f"  {r.id}  [{r.prio}]  {r.short_title(80)}")
    if apply:
        stamp = _dt.date.today().isoformat()
        header_needed = not os.path.exists(ARCHIVE)
        with open(ARCHIVE, "a", encoding="utf-8") as f:
            if header_needed:
                f.write("# LightOS — Backlog-Archiv (verdichtete done-Eintraege)\n\n"
                        "> Automatisch gepflegt von tools/backlog_compact.py --archive. "
                        "Volltext der erledigten Tabellenzeilen; Kurzform bleibt in BACKLOG.md.\n")
            f.write(f"\n## Verdichtet am {stamp}\n\n")
            f.write("| ID | Prio | Status | Titel / Notiz |\n|----|------|--------|---------------|\n")
            for r in done:
                f.write(r.line if r.line.endswith("\n") else r.line + "\n")
        with open(BACKLOG, "w", encoding="utf-8", newline="") as f:
            f.writelines(new_lines)
        report.append("Geschrieben: BACKLOG.md (verdichtet) + BACKLOG_ARCHIVE.md (Volltext).")
    return "\n".join(report)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Backlog-Verdichter + Queue-View fuer BACKLOG.md (Loop-Werkzeug).")
    ap.add_argument("--queue", type=int, nargs="?", const=10, default=None, metavar="N",
                    help="naechste N offene todo-Items kompakt listen (Default 10)")
    ap.add_argument("--stats", action="store_true", help="Zaehler je Status/Prio")
    ap.add_argument("--archive", action="store_true",
                    help="reine done-Zeilen nach BACKLOG_ARCHIVE.md verdichten (Dry-Run)")
    ap.add_argument("--apply", action="store_true", help="--archive wirklich schreiben")
    args = ap.parse_args(argv)

    if not (args.stats or args.archive or args.queue is not None):
        ap.print_help()
        return 2
    lines = _read()
    if args.stats:
        print(cmd_stats(lines))
    if args.queue is not None:
        print(cmd_queue(lines, args.queue))
    if args.archive:
        print(cmd_archive(lines, args.apply))
    return 0


if __name__ == "__main__":
    sys.exit(main())
