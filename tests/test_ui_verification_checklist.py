from pathlib import Path


def test_checklist_links_to_the_enumerating_smoke_gate():
    text = (Path(__file__).parents[1] / "docs" / "UI_VERIFICATION_CHECKLIST.md").read_text(encoding="utf-8")
    assert "test_ui_smoke_enumerated.py" in text
    assert "WIDGET_REGISTRY" in text
