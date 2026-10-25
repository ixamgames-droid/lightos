"""Hilfe ``tests/backlog_eintrag.py``: Fragment, Tabelle, Archiv, fehlt."""
from __future__ import annotations

import pathlib

import pytest

from backlog_eintrag import eintrag, fundort, status

ROOT = pathlib.Path(__file__).resolve().parents[1]
_KOPF = "| ID | Prio | Status | Titel | Details |\n|---|---|---|---|---|\n"


def _repo(tmp_path, *, fragment=None, backlog="", archiv=""):
    (tmp_path / "backlog.d").mkdir()
    (tmp_path / "BACKLOG.md").write_text(_KOPF + backlog, encoding="utf-8")
    (tmp_path / "BACKLOG_ARCHIVE.md").write_text(
        "| ID | Prio | Status | Titel / Notiz |\n|---|---|---|---|\n" + archiv,
        encoding="utf-8")
    if fragment:
        item, text = fragment
        (tmp_path / "backlog.d" / (item + ".md")).write_text(text, encoding="utf-8")
    return tmp_path


def test_fragment_geht_vor(tmp_path):
    repo = _repo(tmp_path, fragment=("XY-7", "ID: XY-7\nStatus: review\n\nText\n"),
                 backlog="| XY-7 | P2 | todo | **alt** | x |\n")
    assert eintrag(repo, "XY-7").startswith("ID: XY-7\n")
    assert status(repo, "XY-7") == "review"
    assert fundort(repo, "XY-7")[0] == "backlog.d/" + "XY-7.md"


def test_tabellenzeile(tmp_path):
    repo = _repo(tmp_path, backlog=(
        "| XY-70 | P2 | todo | **falsch** | x |\n"
        "| XY-7 | P3 | done (2026-10-14, [PR #5](u)) | **Titel** | Details |\n"))
    zeile = eintrag(repo, "XY-7")
    assert zeile.startswith("| XY-7 |") and "Titel" in zeile
    assert status(repo, "XY-7") == "done (2026-10-14, [PR #5](u))"
    assert fundort(repo, "XY-7")[0] == "BACKLOG.md"


def test_archiv(tmp_path):
    repo = _repo(tmp_path, archiv="| XY-7 | P2 | ✅ done | **Alt** |\n")
    assert "Alt" in eintrag(repo, "XY-7")
    assert status(repo, "XY-7") == "✅ done"
    assert fundort(repo, "XY-7")[0] == "BACKLOG_ARCHIVE.md"


def test_fehlt(tmp_path):
    repo = _repo(tmp_path, backlog="| XY-70 | P2 | todo | **t** | x |\n")
    with pytest.raises(AssertionError, match=r"XY-7 nicht gefunden"):
        eintrag(repo, "XY-7")
    with pytest.raises(AssertionError, match=r"XY-7 nicht gefunden"):
        status(repo, "XY-7")


def test_fragment_ohne_status(tmp_path):
    repo = _repo(tmp_path, fragment=("XY-7", "ID: XY-7\n\nText\n"))
    with pytest.raises(AssertionError, match="Status"):
        status(repo, "XY-7")


def test_echtes_repo():
    # Ein gesammelter, gemergter Eintrag ist im echten Repo auffindbar.
    assert status(ROOT, "ENG-39").startswith("done")
