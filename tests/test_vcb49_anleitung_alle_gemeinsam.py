"""VCB-49: Die Anleitung zum Live-Edit-Panel beschreibt „Alle gemeinsam"
(DE + EN), inkl. „gemischt", Infozeile und Speichern."""
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent / "docs" / "anleitung_vc_widgets"


def test_anleitung_de_beschreibt_alle_gemeinsam():
    text = (_DIR / "23_live_edit.md").read_text(encoding="utf-8")
    for marke in ("Alle gemeinsam", "gemischt", "gilt für", "joint_checked", "Tempo ×"):
        assert marke in text, marke


def test_anleitung_en_beschreibt_alle_gemeinsam():
    text = (_DIR / "23_live_edit.en.md").read_text(encoding="utf-8")
    for marke in ("Alle gemeinsam", "gemischt", "gilt für", "joint_checked", "Tempo ×"):
        assert marke in text, marke
