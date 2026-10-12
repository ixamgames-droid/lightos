"""LAS-34: Die Laser-Anleitung beschreibt die Sicherheitsleiste des neuen
Laser-Tabs so, wie sie ist (Befund QA96-22: Knopf „Sperrzonen planen…“)."""
from pathlib import Path


def test_anleitung_nennt_knopf_und_meldung_in_der_sicherheitsleiste():
    """QA96-22: Die Anleitung beschreibt, was der Tab wirklich zeigt — und
    der Satz „nur Anzeige“ steht gleich bei der Sicherheitsleiste."""
    text = (Path(__file__).resolve().parent.parent / "docs" / "anleitung_laser"
            / "ANLEITUNG_LASER.md").read_text(encoding="utf-8")
    flach = " ".join(text.split())
    anfang = flach.index("Ganz oben steht die **Sicherheitsleiste**")
    absatz = flach[anfang:flach.index("Was darunter steht", anfang)]
    assert "**„Sperrzonen planen…“**" in absatz
    assert "**„Meldung ▾“**" in absatz
    assert "**nur Anzeige**" in absatz
    assert "schalten den Laser nicht ab" in absatz
    assert "ersetzen keinen Laserschutz" in absatz
