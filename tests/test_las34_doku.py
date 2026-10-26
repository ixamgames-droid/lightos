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


def test_anleitung_nennt_blackout_gm_und_klickbares_abzeichen():
    """LAS-44 (QA96-22/23/46): Wortlaut wie in der Sicherheitsleiste."""
    text = (Path(__file__).resolve().parent.parent / "docs" / "anleitung_laser"
            / "ANLEITUNG_LASER.md").read_text(encoding="utf-8")
    flach = " ".join(text.split())
    anfang = flach.index("Ganz oben steht die **Sicherheitsleiste**")
    absatz = flach[anfang:flach.index("Was darunter steht", anfang)]
    assert "„Laser AN · durch BLACKOUT dunkel gehalten“" in absatz
    assert "„Laser AN · durch Grand Master 0 % dunkel gehalten“" in absatz
    assert "Grand Master 0 % schaltet ihn nicht ab" in absatz
    assert "ein Klick darauf öffnet den Planer" in absatz
    assert "mindestens 36 px hoch, im Touch-Modus (`--touch`) 46 px" in absatz
    quelle = (Path(__file__).resolve().parent.parent / "src" / "ui" / "views"
              / "laser_view.py").read_text(encoding="utf-8")
    for teil in ('f"durch {grund} dunkel gehalten"', '"BLACKOUT"',
                 '"Grand Master 0 %"', 'f"{grund} schaltet ihn nicht ab"'):
        assert teil in quelle, teil
