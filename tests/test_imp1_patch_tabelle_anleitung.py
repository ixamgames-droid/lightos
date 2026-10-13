"""IMP-1: die Patch-Anleitung nennt, was die App wirklich zeigt.

Knöpfe, Menüeinträge, Statuswörter und die Beispiel-Tabelle der Anleitung
kommen aus dem Code. Benennt jemand im Dialog etwas um oder ändert die
Vorlage, wird dieser Test rot — nicht erst ein Leser stutzig.
"""
from __future__ import annotations

import pathlib

from src.core import patch_tabelle as T

ROOT = pathlib.Path(__file__).resolve().parents[1]
ANLEITUNG = ROOT / "docs" / "anleitung_patch_gruppen" / "ANLEITUNG_PATCH_GRUPPEN.md"
DIALOG = ROOT / "src" / "ui" / "widgets" / "patch_import_dialog.py"
PATCH = ROOT / "src" / "ui" / "views" / "patch_view.py"


def _abschnitt() -> str:
    text = ANLEITUNG.read_text(encoding="utf-8")
    start = text.index("### Geräteliste aus einer Tabelle übernehmen")
    return text[start:text.index("\n### ", start + 10)]


def test_knoepfe_und_eintraege_wie_in_der_app():
    text = _abschnitt()
    dialog = DIALOG.read_text(encoding="utf-8")
    patch = PATCH.read_text(encoding="utf-8")
    for wort, quelle in (("Tabellen-Import", patch),
                         ("Aus Tabelle importieren …", patch),
                         ("Vorlage speichern …", patch),
                         ("Anwenden", dialog),
                         ("Profil / Modus", dialog),
                         ("Status", dialog)):
        assert f'"{wort}"' in quelle, f"{wort!r} steht nicht mehr im Code"
        assert f"**{wort}**" in text, wort
    from src.ui.widgets import patch_import_dialog as D
    assert f"*{D.TITEL}*" in text
    assert f"„{D.KEIN_VORSCHLAG}“" in text


def test_statuswoerter_wie_in_der_vorschau():
    text = _abschnitt()
    assert f"**{T.STATUS_TEXT[T.ANLEGBAR]}**" in text
    assert f"**{T.STATUS_TEXT[T.OFFEN]}**" in text
    assert f"**{T.STATUS_TEXT[T.FEHLER]}**" in text
    assert T.STATUS_TEXT[T.UEBERSCHNEIDUNG].startswith(T.STATUS_TEXT[T.FEHLER])


def test_beispiel_tabelle_ist_die_vorlage():
    """Die Tabelle in der Anleitung ist Zeile für Zeile die Vorlage."""
    text = _abschnitt()
    for zeile in T.vorlage_text().splitlines():
        assert zeile in text, zeile


def test_spalten_der_anleitung_sind_die_des_lesers():
    text = _abschnitt()
    for spalte in T.SPALTEN_TEXT.values():
        assert f"| **{spalte}** |" in text, spalte
    # die „heißt auch“-Namen der Anleitung versteht der Leser wirklich
    for name, spalte in (("Modell", T.PROFIL), ("Gerät", T.PROFIL), ("Fixture", T.PROFIL),
                         ("Typ", T.PROFIL), ("Model", T.PROFIL), ("DMX", T.ADRESSE),
                         ("DMX-Adresse", T.ADRESSE), ("Address", T.ADRESSE),
                         ("Label", T.NAME), ("Bezeichnung", T.NAME),
                         ("Manufacturer", T.HERSTELLER), ("Marke", T.HERSTELLER),
                         ("Mode", T.MODUS), ("Universe", T.UNIVERSUM), ("Univ.", T.UNIVERSUM),
                         ("Count", T.ANZAHL), ("Menge", T.ANZAHL), ("Channels", T.KANAELE)):
        assert T._kopf_deuten([name]) == {spalte: 0}, name
        assert name in text, name


def test_grenzen_stehen_in_der_anleitung():
    text = _abschnitt()
    assert f"{T.UNIVERSUM_MIN} bis {T.UNIVERSUM_MAX}" in text
    for stichwort in ("rät nicht", "nie verändert oder", "in einem Schritt zurück",
                      ".xlsx", "nur der Patch"):
        assert stichwort in text, stichwort
