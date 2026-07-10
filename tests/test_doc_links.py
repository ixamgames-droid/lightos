from pathlib import Path

from tools.check_doc_links import broken_links


def test_repository_markdown_links_resolve():
    assert broken_links() == []


def test_checker_reports_a_missing_relative_link(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("[missing](nope.md)", encoding="utf-8")
    assert broken_links(Path(tmp_path)) == ["docs/a.md -> nope.md"]
