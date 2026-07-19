"""Worktree-, Branch- und Artefakt-Hygiene fuer den LightOS-Loop (report-first).

Der autonome Loop hinterlaesst mit der Zeit Leichen: wt-*-Worktree-Ordner im
aeusseren Projektordner (Windows-Dateilocks verhindern oft das sofortige
Aufraeumen, siehe lightos-loop-Skill), laengst gemergte lokale Branches und
Screenshot-/Log-Artefakte im Haupt-Checkout. Dieses Werkzeug ERKENNT all das
und raeumt NUR auf explizites --apply wirklich auf.

Aufruf (aus Repo-Root oder Worktree):
  venv/Scripts/python.exe tools/janitor.py                  # alles, nur Report
  venv/Scripts/python.exe tools/janitor.py worktrees --apply
  venv/Scripts/python.exe tools/janitor.py branches  --apply
  venv/Scripts/python.exe tools/janitor.py artifacts --apply [--days 7]

Harte Guardrails:
  * Default = reiner Report; ohne --apply wird NICHTS veraendert.
  * Nie angefasst: main, der eigene Worktree, dirty Worktrees, der Halter der
    pytest-Sperre (.pytest_lock.json), data/, shows/, fixtures/.
  * Artefakte werden NICHT geloescht, sondern nach <outer>/_trash/<datum>/
    verschoben (Wiederherstellung moeglich; _trash leert David selbst).
  * `git worktree remove` ohne --force: ein dirty/gesperrter Tree schlaegt fehl
    und wird als "manuell pruefen" gemeldet (Windows-Lock -> nach App-/Session-
    Neustart erneut versuchen).

Reines Stdlib-Werkzeug (subprocess+git); die Klassifikationslogik ist als pure
Funktionen testbar (tests/test_janitor.py).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]      # Checkout, aus dem wir laufen
_OUTER = _REPO.parent                            # aeusserer Projektordner
_MAIN = _OUTER / "lightos-main"                  # Haupt-Checkout (venv, Artefakte)
_TRASH = _OUTER / "_trash"
_LOCK = _OUTER / ".pytest_lock.json"

ARTIFACT_PATTERNS = ("artifacts_*.png", "app_stderr.txt", "err.txt")
PROTECTED_BRANCHES = {"main", "HEAD"}


def _git(*args: str, cwd: Path | None = None) -> str:
    res = subprocess.run(["git", "-C", str(cwd or _REPO), *args],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} -> rc={res.returncode}: {res.stderr.strip()}")
    return res.stdout


# ── pure Klassifikationslogik (testbar ohne git) ─────────────────────────────

@dataclass
class WtVerdict:
    path: str
    verdict: str      # 'orphan' | 'removable' | 'keep'
    reason: str
    branch: str = ""


def classify_worktrees(disk_dirs: list[str], registered: dict[str, dict],
                       merged_branches: set[str], lock_cwd: str | None,
                       own_path: str) -> list[WtVerdict]:
    """Klassifiziert Worktree-Kandidaten.

    disk_dirs:  wt-*-Ordner auf der Platte (absolute Pfade, normalisiert)
    registered: pfad -> {'branch': str, 'dirty': bool} aus `git worktree list`
    merged_branches: Branch-Namen, die vollstaendig in origin/main enthalten sind
    lock_cwd:   cwd aus einer LEBENDEN pytest-Sperre (oder None)
    own_path:   der Worktree, aus dem wir selbst laufen (nie anfassen)
    """
    def norm(p: str) -> str:
        return os.path.normcase(os.path.normpath(p))

    reg = {norm(k): v for k, v in registered.items()}
    lock_n = norm(lock_cwd) if lock_cwd else None
    own_n = norm(own_path)
    out: list[WtVerdict] = []
    for d in disk_dirs:
        dn = norm(d)
        info = reg.get(dn)
        if dn == own_n:
            out.append(WtVerdict(d, "keep", "eigener Worktree dieser Session"))
            continue
        if lock_n and (dn == lock_n or lock_n.startswith(dn + os.sep)):
            out.append(WtVerdict(d, "keep", "haelt die pytest-Sperre (Tests laufen)"))
            continue
        if info is None:
            out.append(WtVerdict(d, "orphan", "auf Platte, aber nicht (mehr) als Worktree registriert"))
            continue
        branch = info.get("branch", "")
        if branch in PROTECTED_BRANCHES:
            out.append(WtVerdict(d, "keep", f"Branch '{branch}' ist geschuetzt", branch))
        elif info.get("dirty"):
            out.append(WtVerdict(d, "keep", "uncommittete Aenderungen", branch))
        elif branch in merged_branches:
            out.append(WtVerdict(d, "removable", "Branch vollstaendig in origin/main gemergt", branch))
        else:
            out.append(WtVerdict(d, "keep", "Branch (noch) nicht in origin/main gemergt", branch))
    return out


def classify_branches(local_branches: list[str], merged_branches: set[str],
                      active_branches: set[str]) -> list[tuple[str, str]]:
    """Liefert (branch, verdict) — 'deletable' nur fuer gemergte, inaktive Branches."""
    out: list[tuple[str, str]] = []
    for b in local_branches:
        if b in PROTECTED_BRANCHES:
            out.append((b, "keep: geschuetzt"))
        elif b in active_branches:
            out.append((b, "keep: in einem Worktree ausgecheckt"))
        elif b in merged_branches:
            out.append((b, "deletable"))
        else:
            out.append((b, "keep: nicht in origin/main gemergt"))
    return out


def artifact_is_stale(path: Path, now: float, days: int) -> bool:
    try:
        return (now - path.stat().st_mtime) >= days * 86400
    except OSError:
        return False


# ── git-/Dateisystem-Anbindung ───────────────────────────────────────────────

def parse_worktree_porcelain(text: str) -> dict[str, dict]:
    """`git worktree list --porcelain` -> {pfad: {'branch': voller Name, 'dirty': False}}."""
    reg: dict[str, dict] = {}
    cur: str | None = None
    for line in text.splitlines():
        if line.startswith("worktree "):
            cur = line[len("worktree "):].strip()
            reg[cur] = {"branch": "", "dirty": False}
        elif line.startswith("branch ") and cur:
            # 'branch refs/heads/chore/foo-bar' -> 'chore/foo-bar' (NUR das
            # refs/heads/-Praefix strippen — Branch-Namen enthalten selbst '/').
            ref = line[len("branch "):].strip()
            reg[cur]["branch"] = ref.removeprefix("refs/heads/")
        elif line.strip() == "detached" and cur:
            reg[cur]["branch"] = "(detached)"
    return reg


def _registered_worktrees() -> dict[str, dict]:
    reg = parse_worktree_porcelain(_git("worktree", "list", "--porcelain"))
    for path, info in reg.items():
        try:
            info["dirty"] = bool(_git("status", "--porcelain", cwd=Path(path)).strip())
        except RuntimeError:
            info["dirty"] = True   # im Zweifel nicht anfassen
    return reg


def _merged_branches() -> set[str]:
    out = _git("branch", "--merged", "origin/main", "--format=%(refname:short)")
    return {b.strip() for b in out.splitlines() if b.strip()}


def _local_branches() -> list[str]:
    out = _git("branch", "--format=%(refname:short)")
    return [b.strip() for b in out.splitlines() if b.strip()]


def _alive_lock_cwd() -> str | None:
    """cwd der pytest-Sperre, falls der Halter-Prozess noch lebt."""
    try:
        info = json.loads(_LOCK.read_text(encoding="utf-8-sig"))
        pid = int(info.get("pid", 0))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if pid <= 0:
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    return str(info.get("cwd") or "") or None


def _disk_worktree_dirs() -> list[str]:
    dirs = [str(p) for p in _OUTER.glob("wt-*") if p.is_dir()]
    # Auch .claude/worktrees des Haupt-Checkouts einsammeln (EnterWorktree-Reste).
    claude_wt = _MAIN / ".claude" / "worktrees"
    if claude_wt.is_dir():
        dirs += [str(p) for p in claude_wt.iterdir() if p.is_dir()]
    return dirs


def cmd_worktrees(apply: bool) -> int:
    verdicts = classify_worktrees(
        _disk_worktree_dirs(), _registered_worktrees(), _merged_branches(),
        _alive_lock_cwd(), str(_REPO))
    orphans = [v for v in verdicts if v.verdict == "orphan"]
    removable = [v for v in verdicts if v.verdict == "removable"]
    print(f"Worktrees: {len(verdicts)} Kandidaten — {len(orphans)} verwaist, "
          f"{len(removable)} entfernbar, {len(verdicts)-len(orphans)-len(removable)} bleiben.")
    for v in verdicts:
        tag = {"orphan": "VERWAIST ", "removable": "ENTFERNBAR", "keep": "bleibt    "}[v.verdict]
        print(f"  {tag} {v.path}  [{v.branch or '-'}]  {v.reason}")
    if not apply:
        if orphans or removable:
            print("-> Aufraeumen mit: tools/janitor.py worktrees --apply")
        return 0
    for v in removable:
        try:
            _git("worktree", "remove", v.path)
            print(f"  entfernt: {v.path}")
        except RuntimeError as e:
            print(f"  MANUELL PRUEFEN (Windows-Lock? spaeter erneut): {v.path} — {e}")
    for v in orphans:
        try:
            shutil.rmtree(v.path)
            print(f"  geloescht (verwaister Ordner): {v.path}")
        except OSError as e:
            print(f"  MANUELL PRUEFEN (Datei-Lock, nach App-Neustart erneut): {v.path} — {e}")
    try:
        _git("worktree", "prune")
        print("  git worktree prune: ok")
    except RuntimeError as e:
        print(f"  git worktree prune: {e}")
    return 0


def cmd_branches(apply: bool) -> int:
    reg = _registered_worktrees()
    active = {i["branch"] for i in reg.values() if i.get("branch")}
    verdicts = classify_branches(_local_branches(), _merged_branches(), active)
    deletable = [b for b, v in verdicts if v == "deletable"]
    keep = [(b, v) for b, v in verdicts if v != "deletable"]
    print(f"Branches: {len(verdicts)} lokal — {len(deletable)} geloescht werden koennen "
          f"(gemergt + inaktiv), {len(keep)} bleiben.")
    for b in deletable:
        print(f"  DELETABLE {b}")
    if not apply:
        if deletable:
            print("-> Loeschen mit: tools/janitor.py branches --apply")
        return 0
    for b in deletable:
        try:
            _git("branch", "-d", b)   # -d: doppelte Sicherheit, nur gemergte
            print(f"  geloescht: {b}")
        except RuntimeError as e:
            print(f"  uebersprungen: {b} — {e}")
    return 0


def cmd_artifacts(apply: bool, days: int) -> int:
    now = time.time()
    stale: list[Path] = []
    for pattern in ARTIFACT_PATTERNS:
        for p in sorted(_MAIN.glob(pattern)):
            if p.is_file() and artifact_is_stale(p, now, days):
                stale.append(p)
    total = sum(p.stat().st_size for p in stale)
    print(f"Artefakte im Haupt-Checkout ({_MAIN.name}/): {len(stale)} Dateien aelter "
          f"als {days} Tage ({total/1024/1024:.1f} MB) — Muster: {', '.join(ARTIFACT_PATTERNS)}")
    for p in stale[:15]:
        print(f"  {p.name}")
    if len(stale) > 15:
        print(f"  … und {len(stale)-15} weitere")
    if not apply:
        if stale:
            print("-> Verschieben nach _trash mit: tools/janitor.py artifacts --apply")
        return 0
    if not stale:
        return 0
    dest = _TRASH / _dt.date.today().isoformat()
    dest.mkdir(parents=True, exist_ok=True)
    moved = 0
    for p in stale:
        try:
            shutil.move(str(p), str(dest / p.name))
            moved += 1
        except OSError as e:
            print(f"  uebersprungen (in Benutzung?): {p.name} — {e}")
    print(f"  {moved}/{len(stale)} verschoben nach {dest}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Worktree-/Branch-/Artefakt-Hygiene, report-first (--apply zum Aufraeumen).")
    ap.add_argument("scope", nargs="?", default="all",
                    choices=["all", "worktrees", "branches", "artifacts"])
    ap.add_argument("--apply", action="store_true", help="wirklich aufraeumen (Default: nur Report)")
    ap.add_argument("--days", type=int, default=7,
                    help="Artefakte erst ab diesem Alter in Tagen anfassen (Default 7)")
    args = ap.parse_args(argv)

    rc = 0
    if args.scope in ("all", "worktrees"):
        rc |= cmd_worktrees(args.apply)
    if args.scope in ("all", "branches"):
        rc |= cmd_branches(args.apply)
    if args.scope in ("all", "artifacts"):
        rc |= cmd_artifacts(args.apply, args.days)
    return rc


if __name__ == "__main__":
    sys.exit(main())
