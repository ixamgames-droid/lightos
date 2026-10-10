"""STAB-33: schreibt ``build_info.json`` — der Commit, aus dem ein Setup gebaut ist.

Im gepackten Build gibt es kein ``.git``; das Diagnosepaket meldete deshalb
``Commit: unbekannt``. Dieses Skript laeuft VOR PyInstaller (Workflow
``.github/workflows/windows-setup.yml`` bzw. von Hand), legt die Datei in die
Repo-Wurzel, ``bundle_inhalt.py`` nimmt sie von dort ins Bundle
(``GENERIERTE_DATEIEN``), ``src/core/diagnose_log.py`` liest sie im gefrorenen
Zustand und ``--selbsttest`` verlangt sie dort.

Quelle des Commits: ``GITHUB_SHA`` (Actions), sonst ``git rev-parse HEAD``.
Ohne beides bricht das Skript ab — lieber kein Setup als eines, dessen Stand
niemand benennen kann.

Aufruf: ``python packaging/windows/build_info.py [REPO]``. Die Datei ist
gitignored und wird nie eingecheckt. Bewusst ohne LightOS-Importe.
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys

NAME = "build_info.json"


def _git(repo: str, *args: str) -> str:
    try:
        aus = subprocess.run(["git", *args], cwd=repo, capture_output=True,
                             check=True)
    except (OSError, subprocess.CalledProcessError):
        return ""
    return aus.stdout.decode("utf-8", errors="replace").strip()


def sammle(repo: str, env=None, jetzt: str | None = None) -> dict:
    """Die Build-Info als dict. ``env``/``jetzt`` sind einspeisbar (Tests)."""
    env = os.environ if env is None else env
    commit = (env.get("GITHUB_SHA") or "").strip() or _git(repo, "rev-parse", "HEAD")
    if not commit:
        raise RuntimeError("Commit unbekannt: weder GITHUB_SHA noch ein "
                           "Git-Arbeitsverzeichnis")
    ref = (env.get("GITHUB_REF_NAME") or "").strip() or _git(
        repo, "rev-parse", "--abbrev-ref", "HEAD")
    if jetzt is None:
        jetzt = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
    info = {"commit": commit, "ref": ref, "datum": jetzt}
    if env.get("GITHUB_RUN_ID"):
        info["lauf"] = str(env["GITHUB_RUN_ID"])
    return info


def schreibe(repo: str, env=None, jetzt: str | None = None) -> str:
    """Schreibt ``<repo>/build_info.json`` und gibt den Pfad zurueck."""
    info = sammle(repo, env, jetzt)
    pfad = os.path.join(repo, NAME)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return pfad


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    repo = os.path.abspath(argv[0]) if argv else os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    try:
        pfad = schreibe(repo)
    except Exception as e:      # noqa: BLE001 — Meldung + Exit-Code fuer die CI
        print(f"build_info: FEHLER {e}", file=sys.stderr)
        return 1
    with open(pfad, encoding="utf-8") as f:
        print(f"build_info: {pfad}\n{f.read()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
