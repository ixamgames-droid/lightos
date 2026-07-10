"""QA-11: Das GitHub-CI-Gate enthält die lokalen Show-/View-Schutztests."""
from pathlib import Path


def test_ci_installs_qt_and_runs_show_lint_and_view_smoke():
    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8")
    assert "PySide6" in workflow
    for target in ("tests/test_show_file.py", "tests/test_show_lint.py",
                   "tests/test_core_engine.py", "tests/test_views.py"):
        assert target in workflow
