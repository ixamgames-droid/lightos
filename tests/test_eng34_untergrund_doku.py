"""ENG-34: die Dimmer-Matrix-Anleitung beschreibt den Untergrund — mit den
Namen, die der Editor wirklich zeigt, und ohne erfundene Bilder."""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ANLEITUNG = REPO / "docs" / "anleitung_dimmermatrix" / "ANLEITUNG_DIMMERMATRIX.md"
EDITOR = REPO / "src" / "ui" / "views" / "rgb_matrix_view.py"
ENGINE = REPO / "src" / "core" / "engine" / "rgb_matrix.py"


def _abschnitt() -> str:
    text = ANLEITUNG.read_text(encoding="utf-8")
    treffer = re.search(r"^## \d+\. Untergrund[^\n]*\n(.*?)(?=^## )", text,
                        flags=re.M | re.S)
    assert treffer, "Abschnitt „Untergrund“ fehlt in der Dimmer-Matrix-Anleitung"
    return treffer.group(1)


def test_abschnitt_nennt_die_felder_des_editors():
    abschnitt = _abschnitt()
    editor = EDITOR.read_text(encoding="utf-8")
    # (Name in der Anleitung, Beschriftung im Editor)
    for name, im_editor in (("Untergrund", 'QGroupBox("Untergrund")'),
                            ("Aus", '"Aus"'),
                            ("Fester Wert", '"Fester Wert"'),
                            ("Atmen", '"Atmen"'),
                            ("Art:", 'QLabel("Art:")'),
                            ("Helligkeit", 'QLabel("Helligkeit:")'),
                            ("Tiefpunkt", 'QLabel("Tiefpunkt:")'),
                            ("Tempo ×", 'QLabel("Tempo ×:")')):
        assert im_editor in editor, f"Editor zeigt {im_editor} nicht mehr"
        assert f"**{name}**" in abschnitt, f"Anleitung nennt „{name}“ nicht"


def test_abschnitt_nennt_die_regler_der_konsole():
    abschnitt = _abschnitt()
    engine = ENGINE.read_text(encoding="utf-8")
    for name in ("Dimmer min", "Untergrund Tempo ×", "Untergrund Tiefpunkt"):
        assert f'"{name}"' in engine, f"Parameter „{name}“ heisst im Code anders"
        assert name in abschnitt, f"Anleitung nennt den Regler „{name}“ nicht"


def test_abschnitt_sagt_was_getrennt_bleibt_und_was_mit_alten_shows_ist():
    abschnitt = _abschnitt()
    assert "nur auf den Dimmer" in abschnitt
    assert "Alte Shows" in abschnitt and "Fester Wert" in abschnitt


def test_bilder_sind_als_offen_benannt_und_nicht_erfunden():
    abschnitt = _abschnitt()
    assert "Bilder folgen" in abschnitt and "noch aufzunehmen" in abschnitt
    assert not re.search(r"!\[[^\]]*\]\(", abschnitt), (
        "im Abschnitt „Untergrund“ steht ein Bild — aufgenommen ist noch keins")


def test_min_feld_wird_nicht_mehr_bei_den_farben_versprochen():
    text = ANLEITUNG.read_text(encoding="utf-8")
    assert "Spinboxen **Min** / **Max**" not in text
    assert "(Min/Max)" not in text
