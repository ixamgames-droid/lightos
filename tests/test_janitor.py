"""Tests fuer die pure Klassifikationslogik von tools/janitor.py.

Kein git, kein Dateisystem-Aufraeumen — nur die Entscheidungslogik, die
bestimmt, was der Janitor anfassen DARF. Die Guards (eigener Worktree,
pytest-Lock-Halter, dirty, ungemergt) sind sicherheitskritisch fuer den Loop.
"""
import os
import sys
import time
import unittest
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

import janitor  # noqa: E402

OUTER = r"C:\x\proj"
WT_A = os.path.join(OUTER, "wt-a")        # registriert, gemergt, clean -> removable
WT_B = os.path.join(OUTER, "wt-b")        # registriert, NICHT gemergt -> keep
WT_C = os.path.join(OUTER, "wt-c")        # nicht registriert -> orphan
WT_D = os.path.join(OUTER, "wt-d")        # registriert, gemergt, aber dirty -> keep
WT_E = os.path.join(OUTER, "wt-e")        # haelt pytest-Lock -> keep
WT_OWN = os.path.join(OUTER, "wt-own")    # eigener Worktree -> keep
WT_MAIN = os.path.join(OUTER, "wt-m")     # Branch main -> keep

REGISTERED = {
    WT_A: {"branch": "fix/a", "dirty": False},
    WT_B: {"branch": "feature/b", "dirty": False},
    WT_D: {"branch": "fix/d", "dirty": True},
    WT_E: {"branch": "fix/e", "dirty": False},
    WT_OWN: {"branch": "chore/own", "dirty": False},
    WT_MAIN: {"branch": "main", "dirty": False},
}
MERGED = {"fix/a", "fix/d", "fix/e", "chore/own", "main"}
DISK = [WT_A, WT_B, WT_C, WT_D, WT_E, WT_OWN, WT_MAIN]


def _verdicts(lock_cwd=None, own=WT_OWN):
    vs = janitor.classify_worktrees(DISK, REGISTERED, MERGED, lock_cwd, own)
    return {v.path: v for v in vs}


class WorktreeClassifyTest(unittest.TestCase):
    def test_merged_clean_is_removable(self):
        self.assertEqual(_verdicts()[WT_A].verdict, "removable")

    def test_unmerged_is_kept(self):
        self.assertEqual(_verdicts()[WT_B].verdict, "keep")

    def test_unregistered_is_orphan(self):
        self.assertEqual(_verdicts()[WT_C].verdict, "orphan")

    def test_dirty_is_kept_even_if_merged(self):
        self.assertEqual(_verdicts()[WT_D].verdict, "keep")

    def test_lock_holder_is_kept(self):
        v = _verdicts(lock_cwd=WT_E)[WT_E]
        self.assertEqual(v.verdict, "keep")
        self.assertIn("Sperre", v.reason)

    def test_lock_cwd_inside_worktree_also_protects(self):
        v = _verdicts(lock_cwd=os.path.join(WT_E, "tests"))[WT_E]
        self.assertEqual(v.verdict, "keep")

    def test_own_worktree_is_kept_even_if_merged(self):
        self.assertEqual(_verdicts()[WT_OWN].verdict, "keep")

    def test_main_branch_worktree_is_protected(self):
        v = _verdicts()[WT_MAIN]
        self.assertEqual(v.verdict, "keep")
        self.assertIn("geschuetzt", v.reason)

    def test_case_insensitive_paths_on_windows_semantics(self):
        vs = janitor.classify_worktrees([WT_A.upper()], REGISTERED, MERGED, None, WT_OWN)
        self.assertEqual(vs[0].verdict, "removable",
                         "Pfadvergleich muss normcase-normalisiert sein")

    def test_unregistered_without_git_marker_is_never_orphan(self):
        # Review 2026-07-19: Davids manuell angelegter 'wt-backup'-Ordner (nie
        # ein Worktree) darf NICHT als verwaist eingestuft und angefasst werden.
        vs = janitor.classify_worktrees([WT_C], REGISTERED, MERGED, None, WT_OWN,
                                        git_marked=set())
        self.assertEqual(vs[0].verdict, "keep")
        self.assertIn(".git-Marker", vs[0].reason)

    def test_unregistered_with_git_marker_is_orphan(self):
        vs = janitor.classify_worktrees([WT_C], REGISTERED, MERGED, None, WT_OWN,
                                        git_marked={WT_C.upper()})
        self.assertEqual(vs[0].verdict, "orphan",
                         "git_marked muss normcase-normalisiert verglichen werden")

    def test_unique_dest_never_overwrites(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "err.txt").write_text("alt")
            cand = janitor._unique_dest(d, "err.txt")
            self.assertNotEqual(cand.name, "err.txt")
            self.assertFalse(cand.exists())

    def test_pid_alive_for_own_and_bogus_pid(self):
        self.assertTrue(janitor._pid_alive(os.getpid()),
                        "eigener Prozess muss als lebendig erkannt werden")
        self.assertFalse(janitor._pid_alive(0))
        self.assertFalse(janitor._pid_alive(-5))


class PorcelainParseTest(unittest.TestCase):
    def test_branch_prefix_with_slash_survives(self):
        text = (
            "worktree C:/x/proj/wt-tools\n"
            "HEAD abc123\n"
            "branch refs/heads/chore/tools-audit-round\n"
            "\n"
            "worktree C:/x/proj/wt-det\n"
            "HEAD def456\n"
            "detached\n"
        )
        reg = janitor.parse_worktree_porcelain(text)
        self.assertEqual(reg["C:/x/proj/wt-tools"]["branch"], "chore/tools-audit-round",
                         "Branch-Namen mit '/' duerfen nicht verstuemmelt werden")
        self.assertEqual(reg["C:/x/proj/wt-det"]["branch"], "(detached)")


class BranchClassifyTest(unittest.TestCase):
    def test_only_merged_inactive_branches_are_deletable(self):
        out = dict(janitor.classify_branches(
            ["main", "fix/a", "feature/b", "chore/own"],
            merged_branches={"main", "fix/a", "chore/own"},
            active_branches={"chore/own"}))
        self.assertEqual(out["fix/a"], "deletable")
        self.assertTrue(out["main"].startswith("keep"))
        self.assertTrue(out["feature/b"].startswith("keep"))
        self.assertTrue(out["chore/own"].startswith("keep"))


class ArtifactAgeTest(unittest.TestCase):
    def test_stale_by_mtime(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "artifacts_x.png"
            p.write_bytes(b"x")
            now = time.time()
            self.assertFalse(janitor.artifact_is_stale(p, now, days=7))
            old = now - 8 * 86400
            os.utime(p, (old, old))
            self.assertTrue(janitor.artifact_is_stale(p, now, days=7))

    def test_missing_file_is_not_stale(self):
        self.assertFalse(janitor.artifact_is_stale(Path("Z:/gibt/es/nicht.png"),
                                                   time.time(), 7))


class GuardrailSmokeTest(unittest.TestCase):
    def test_report_mode_default_paths_resolve(self):
        # Pfad-Konstanten muessen auf den aeusseren Projektordner zeigen
        # (Guard gegen versehentliches Umhaengen der Verzeichnis-Basis).
        self.assertEqual(janitor._OUTER, janitor._REPO.parent)
        self.assertEqual(janitor._TRASH.parent, janitor._OUTER)
        self.assertTrue(str(janitor._MAIN).endswith("lightos-main"))


if __name__ == "__main__":
    unittest.main()
