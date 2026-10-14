"""ENG-36: die Anleitung „Geräte klonen" nennt, was die App wirklich zeigt.

Die Wörter der Anleitung kommen aus dem Code: Bereichs-Häkchen, Kennzeichen,
Knöpfe und der Name der Sicherung. Benennt jemand im Dialog etwas um, wird
dieser Test rot — nicht erst ein Leser stutzig.
"""
from __future__ import annotations

import pathlib
import re

from src.core.show import klonen as K
from src.core.show import sicherungen as S

ROOT = pathlib.Path(__file__).resolve().parents[1]
ANLEITUNG = ROOT / "docs" / "anleitung_klonen" / "ANLEITUNG_KLONEN.md"
INDEX = ROOT / "docs" / "ANLEITUNGEN.md"
DIALOG = ROOT / "src" / "ui" / "widgets" / "klonen_dialog.py"
PATCH = ROOT / "src" / "ui" / "views" / "patch_view.py"


def _text() -> str:
    return ANLEITUNG.read_text(encoding="utf-8")


def test_anleitung_steht_im_index():
    assert "(anleitung_klonen/ANLEITUNG_KLONEN.md)" in INDEX.read_text(encoding="utf-8")


def test_bereiche_und_kennzeichen_wie_im_dialog():
    text = _text()
    for bereich in K.BEREICHE:
        assert K.BEREICH_TEXT[bereich] in text, bereich
    for kennzeichen in (K.UNVERAENDERT, K.UEBERSETZT, K.FAELLT_WEG, K.BLEIBT):
        assert K.KENNZEICHEN_TEXT[kennzeichen] in text, kennzeichen
    assert K.GRUND_SPAETER in text


def test_knoepfe_und_wahl_wie_in_der_app():
    text = _text()
    dialog = DIALOG.read_text(encoding="utf-8")
    patch = PATCH.read_text(encoding="utf-8")
    for wort, quelle in (("Klonen…", patch), ("Klonen auf …", patch),
                         ("Klonen auf …", dialog), ("Weiter", dialog),
                         ("Anwenden", dialog), ("Hinzufügen", dialog),
                         ("Ersetzen", dialog), ("ans Ende", dialog),
                         ("neben die Quelle", dialog),
                         ("Position in Gruppe, Raster und Fächer", dialog)):
        assert wort in quelle, f"{wort!r} steht nicht mehr im Code"
        assert f"**{wort}**" in text, wort


def test_sicherung_heisst_wie_in_der_liste_der_versionen():
    assert f"„{S.ANLASS_TEXT[S.ANLASS_VOR_KLONEN]}\"" in _text()


def test_grenzen_und_stand_sind_genannt():
    text = _text()
    for stichwort in ("Farbe und Dimmer bleiben getrennt", "Ersetzen löscht nichts",
                      "Kommandozeile", "Menü Bearbeiten", "ungefähr",
                      "Bilder, die noch fehlen"):
        assert stichwort in text, stichwort


def test_keine_erfundenen_bilder():
    """Die Anleitung hat noch keine Bilder — sie darf auch keine einbinden."""
    assert not re.search(r"!\[[^\]]*\]\(", _text())
    assert not (ANLEITUNG.parent / "img").exists()
