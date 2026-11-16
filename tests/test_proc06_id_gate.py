"""PROC-06 — das Gate gegen doppelt vergebene Backlog-IDs in ``pr_bereit.py``.

Fertig laut Item, wenn ein Zweig, der eine auf einem anderen offenen PR
bereits vergebene NEUE Nummer benutzt, laut auffaellt — **und ein Zweig, der
eine von ``main`` geerbte Nummer nur umformuliert, nicht** (Positivkontrolle).

Geprueft an einem Wegwerf-Git-Repo in ``tmp_path`` (Zweige als
``refs/remotes/origin/*``, wie nach ``git fetch``). ``gh`` wird nie gerufen:
die PR-Liste und ``gh pr view``/``gh api`` sind Attrappen.
"""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import backlog_ids as B  # noqa: E402
import pr_bereit as P  # noqa: E402

KOPF = ("| ID | Prio | Status | Titel | Beschreibung |\n"
        "|---|---|---|---|---|\n")


def _git(repo, *args):
    p = subprocess.run(
        ("git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
         "-c", "commit.gpgsign=false") + args,
        cwd=repo, capture_output=True, text=True, encoding="utf-8",
        errors="replace")
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def _schreibe(repo, dateien: dict):
    for name, text in dateien.items():
        pfad = repo / name
        if text is None:
            pfad.unlink()
            continue
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text(text, encoding="utf-8")


def _commit(repo, dateien, nachricht="x"):
    _schreibe(repo, dateien)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", nachricht)
    return _git(repo, "rev-parse", "HEAD")


def _zweig(repo, name, basis, dateien):
    _git(repo, "checkout", "-q", "-B", name, basis)
    sha = _commit(repo, dateien, name)
    _git(repo, "update-ref", f"refs/remotes/origin/{name}", sha)
    return sha


def _fragment_neu(item_id, titel):
    return (f"ID: {item_id}\nPrioritaet: P2\nStatus: review\nTitel: {titel}\n\n"
            "Freitext.\n")


def _fragment_status(item_id):
    return f"ID: {item_id}\nStatus: review\nStatus-Notiz: erledigt\n"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    backlog = (KOPF
               + "| FM-1 | P2 | todo | **Altes Item eins** | x |\n"
               + "| FM-2 | P2 | todo | **Altes Item zwei** | x |\n")
    sha = _commit(r, {"BACKLOG.md": backlog, "backlog.d/README.md": "Vorlage\n"})
    _git(r, "update-ref", "refs/remotes/origin/main", sha)
    monkeypatch.chdir(r)
    return r


def test_echter_konflikt_auf_zwei_offenen_zweigen_ist_rot(repo):
    _zweig(repo, "a", "main", {"backlog.d/FM-3.md": _fragment_neu("FM-3", "Return speichern")})
    _zweig(repo, "b", "main", {"backlog.d/FM-3.md": _fragment_neu("FM-3", "Matrizen zusammenlegen")})
    treffer, hinweise = B.id_gate("origin/a", {"origin/b": "origin/b"})
    assert [(t[0], t[2]) for t in treffer] == [("FM-3", "origin/b")]
    assert hinweise == []
    # in beide Richtungen
    treffer, _ = B.id_gate("origin/b", {"origin/a": "origin/a"})
    assert [t[0] for t in treffer] == ["FM-3"]


def test_neue_backlog_zeile_gegen_neues_fragment_ist_rot(repo):
    backlog = (repo / "BACKLOG.md").read_text(encoding="utf-8")
    _zweig(repo, "a", "main", {"BACKLOG.md": backlog
                               + "| FM-3 | P2 | todo | **Return speichern** | x |\n"})
    _zweig(repo, "b", "main", {"backlog.d/FM-3.md": _fragment_neu("FM-3", "Unerkannte Kanaele")})
    treffer, _ = B.id_gate("origin/a", {"origin/b": "origin/b"})
    assert [t[0] for t in treffer] == ["FM-3"]


def test_geerbte_umformulierte_id_bleibt_still(repo):
    """Positivkontrolle: beide Zweige formulieren FM-1 von main verschieden um."""
    backlog = (repo / "BACKLOG.md").read_text(encoding="utf-8")
    _zweig(repo, "a", "main", {"BACKLOG.md": backlog.replace(
        "Altes Item eins", "Altes Item eins, geschaerft")})
    _zweig(repo, "b", "main", {"BACKLOG.md": backlog.replace(
        "Altes Item eins", "Ganz anders formuliert")})
    assert B.id_gate("origin/a", {"origin/b": "origin/b"}) == ([], [])


def test_status_fragmente_fuer_vorhandenes_item_sind_kein_konflikt(repo):
    _zweig(repo, "a", "main", {"backlog.d/FM-1.md": _fragment_status("FM-1")})
    _zweig(repo, "b", "main", {"backlog.d/FM-1.md": _fragment_status("FM-1")
                               + "\nAnderer Freitext.\n"})
    assert B.id_gate("origin/a", {"origin/b": "origin/b"}) == ([], [])


def test_gleicher_titel_ist_derselbe_eintrag(repo):
    """Gestapelter Zweig: b baut auf a auf und traegt FM-3 unveraendert mit."""
    _zweig(repo, "a", "main", {"backlog.d/FM-3.md": _fragment_neu("FM-3", "Return speichern")})
    _zweig(repo, "b", "a", {"x.txt": "y\n"})
    assert B.id_gate("origin/a", {"origin/b": "origin/b"}) == ([], [])


def test_inzwischen_auf_main_gelandet_mit_anderem_titel_ist_rot(repo):
    _zweig(repo, "a", "main", {"backlog.d/FM-3.md": _fragment_neu("FM-3", "Return speichern")})
    _git(repo, "checkout", "-q", "main")
    sha = _commit(repo, {"backlog.d/FM-3.md": _fragment_neu("FM-3", "Matrizen zusammenlegen")})
    _git(repo, "update-ref", "refs/remotes/origin/main", sha)
    treffer, _ = B.id_gate("origin/a", {})
    assert [(t[0], t[2]) for t in treffer] == [("FM-3", "main")]


def test_fehlender_ref_ist_hinweis_nicht_rot(repo):
    _zweig(repo, "a", "main", {"backlog.d/FM-3.md": _fragment_neu("FM-3", "Return speichern")})
    treffer, hinweise = B.id_gate("origin/a", {"origin/weg": "origin/weg"})
    assert treffer == []
    assert hinweise and "origin/weg" in hinweise[0]
    treffer, hinweise = B.id_gate("origin/gibtsnicht", {})
    assert treffer == [] and "nicht gelaufen" in hinweise[0]


# ── pr_bereit.main mit Attrappen fuer gh ─────────────────────────────────────

def _gh_attrappe(kopfe: dict):
    """``gh pr view``/``gh api`` fuer PRs ``{Nummer: (Zweig, sha)}``: alles gruen."""
    def gh_json(*args):
        if args[:2] == ("pr", "view"):
            zweig, sha = kopfe[int(args[2])]
            return {"headRefOid": sha, "headRefName": zweig, "title": "T",
                    "mergeable": "MERGEABLE", "isDraft": False}
        if args[0] == "api" and args[1].endswith("/check-runs"):
            return {"check_runs": [{"name": "test", "status": "completed",
                                    "conclusion": "success"}]}
        if args[0] == "api" and "/compare/" in args[1]:
            return {"behind_by": 0}
        if args[0] == "api":
            return {"commit": {"committer": {"date": "2026-01-01T00:00:00Z"}}}
        raise AssertionError(args)
    return gh_json


@pytest.fixture
def ohne_gh(monkeypatch):
    monkeypatch.setattr(P, "_lade_tafel", lambda: {"claims": []})

    def setze(kopfe, zweige=None, warnung=None):
        monkeypatch.setattr(P, "_gh_json", _gh_attrappe(kopfe))
        monkeypatch.setattr(B, "offene_pr_zweige", lambda: (
            list(zweige if zweige is not None else [z for z, _ in kopfe.values()]),
            warnung))
    return setze


def test_pr_bereit_meldet_konflikt_mit_exit_1(repo, ohne_gh, capsys):
    a = _zweig(repo, "a", "main", {"backlog.d/FM-3.md": _fragment_neu("FM-3", "Return speichern")})
    b = _zweig(repo, "b", "main", {"backlog.d/FM-3.md": _fragment_neu("FM-3", "Matrizen zusammenlegen")})
    ohne_gh({10: ("a", a), 11: ("b", b)})
    rc = P.main(["10", "--strict", "--ohne-claim", "Test"])
    aus = capsys.readouterr().out
    assert rc == 1
    assert P.ID_KONFLIKT in aus and "FM-3" in aus and "origin/b" in aus
    # auch ohne --strict: die Merge-Pruefung (PR-Nummern) ist eine Regel
    assert P.main(["10", "--ohne-claim", "Test"]) == 1


def test_pr_bereit_bleibt_bei_geerbter_id_gruen(repo, ohne_gh, capsys):
    backlog = (repo / "BACKLOG.md").read_text(encoding="utf-8")
    a = _zweig(repo, "a", "main", {"BACKLOG.md": backlog.replace(
        "Altes Item zwei", "Item zwei umformuliert"),
        "backlog.d/FM-1.md": _fragment_status("FM-1")})
    b = _zweig(repo, "b", "main", {"backlog.d/FM-1.md": _fragment_status("FM-1")})
    ohne_gh({10: ("a", a), 11: ("b", b)})
    assert P.main(["10", "--strict", "--ohne-claim", "Test"]) == 0
    aus = capsys.readouterr().out
    assert P.ID_KONFLIKT not in aus and "1 von 1 bereit" in aus


def test_pr_bereit_ohne_gh_liste_gibt_hinweis_kein_rot(repo, ohne_gh, capsys):
    a = _zweig(repo, "a", "main", {"backlog.d/FM-3.md": _fragment_neu("FM-3", "Return speichern")})
    ohne_gh({10: ("a", a)}, zweige=[], warnung="`gh pr list` nicht ausfuehrbar (FileNotFoundError)")
    assert P.main(["10", "--strict", "--ohne-claim", "Test"]) == 0
    aus = capsys.readouterr().out
    assert "Hinweis" in aus and "nur teilweise" in aus


def test_offene_pr_zweige_ohne_gh_stuerzt_nicht_ab(monkeypatch):
    def kein_gh(*a, **k):
        raise FileNotFoundError("gh")
    monkeypatch.setattr(B.subprocess, "run", kein_gh)
    zweige, warnung = B.offene_pr_zweige()
    assert zweige == [] and "nicht ausfuehrbar" in warnung


def test_mit_id_pruefung_behaelt_schlimmeres_urteil():
    k = [("FM-3", "a", "origin/b", "b")]
    u, grund, rot = P.mit_id_pruefung(P.ROT, "1 von 3 Checks nicht bestanden", k, [])
    assert u == P.ROT and rot and "ID-Konflikt" in grund
    u, _, rot = P.mit_id_pruefung(P.BEREIT, "ok", [], ["Hinweis x"])
    assert u == P.BEREIT and not rot
