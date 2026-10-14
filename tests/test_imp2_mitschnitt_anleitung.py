"""IMP-2: die Anleitung zum Mitschnitt nennt, was die App wirklich zeigt.

Knöpfe, Haken und Auswahltexte des Abschnitts kommen aus dem Dialog. Benennt
jemand dort etwas um, wird dieser Test rot — nicht erst ein Leser stutzig.
"""
from __future__ import annotations

import pathlib

from src.core import mitschnitt as M
from src.ui.widgets import mitschnitt_dialog as D

ROOT = pathlib.Path(__file__).resolve().parents[1]
ORDNER = ROOT / "docs" / "anleitung_szenen_cues"
TITEL = "Szenen aus einem anderen Programm übernehmen (Mitschnitt)"


def _abschnitt(datei="ANLEITUNG.md", kopf=f"## 11. {TITEL}") -> str:
    text = (ORDNER / datei).read_text(encoding="utf-8")
    start = text.index(kopf)
    return text[start:text.index("\n## ", start + 10)]


def test_knoepfe_und_haken_wie_im_dialog():
    text = " ".join(_abschnitt().split())
    for wort in (D.TITEL + "...", D.TEXT_FESTHALTEN, D.TEXT_FERTIG, D.TEXT_ENTFERNEN,
                 D.TEXT_CHASER, D.TEXT_LASER, D.TEXT_UNRUHIG, "Name:", "Schrittzeit:",
                 "Ruhig nach:", *D.AUSWAHL_TEXT.values()):
        assert f"**{wort}**" in text, wort
    dialog = (ROOT / "src" / "ui" / "widgets" / "mitschnitt_dialog.py").read_text(encoding="utf-8")
    for wort in ("Name:", "Schrittzeit:", "Ruhig nach:"):
        assert f'"{wort}"' in dialog, wort
    programmer = (ROOT / "src" / "ui" / "views" / "programmer_view.py").read_text(encoding="utf-8")
    assert f'QPushButton("{D.TITEL}...")' in programmer
    assert f"„{D.STAMM} 1“" in text


def test_weg_zum_eingang_wie_im_hilfetext_des_dialogs():
    text = " ".join(_abschnitt().split())
    for wort in ("Ausgabe → Konfigurieren...", "DMX Input", "Art-Net Input aktivieren",
                 "sACN Input aktivieren", "Eingehendes Universe", "Merge in Universe",
                 "Übernehmen"):
        assert f"**{wort}**" in text, wort
    for wort in ("DMX Input", "Art-Net Input aktivieren", "Merge in Universe"):
        assert wort in D.HILFE_EINGANG


def test_vorgaben_stehen_mit_ihren_zahlen_da():
    text = " ".join(_abschnitt().split())
    assert M.RUHEZEIT_VORGABE == 0.5 and "0,5 Sekunden" in text
    assert M.SIGNAL_TIMEOUT == 5.0 and "mehr als 5 Sekunden" in text
    assert M.AUSWAHL_VORGABE == M.AUSWAHL_ALLE
    assert f"Vorgabe ist **{D.AUSWAHL_TEXT[M.AUSWAHL_ALLE]}**" in text


def test_ehrliche_grenzen_stehen_in_der_anleitung():
    text = " ".join(_abschnitt().split())
    for satz in ("Nur Kanalwerte.", "Keine Effekte als Effekte.", "Keine Tasten.",
                 "Ein Universum je Protokoll.", "Zeiten musst du von Hand setzen.",
                 "Laser werden ausgelassen.", "Der Assistent liest nur."):
        assert f"**{satz}**" in text, satz


def test_englische_fassung_hat_den_abschnitt_mit_den_deutschen_knopfnamen():
    text = " ".join(_abschnitt("ANLEITUNG.en.md",
                               "## 11. Take over scenes from another program (capture)").split())
    for wort in (D.TITEL + "...", D.TEXT_FESTHALTEN, D.TEXT_CHASER, D.TEXT_FERTIG,
                 D.TEXT_LASER, D.AUSWAHL_TEXT[M.AUSWAHL_ALLE]):
        assert f"**{wort}**" in text, wort
    assert "one universe per protocol" in text and "channel values only" in text


def test_fragmente_liegen_bei():
    assert (ROOT / "backlog.d" / "IMP-2.md").read_text(encoding="utf-8").startswith("ID: IMP-2\n")
    assert list((ROOT / "changelog.d").glob("*-IMP-2.md"))


def test_anleitung_beschreibt_das_eigene_fenster_und_die_leertaste():
    """Der Assistent ist nicht modal. Was daraus folgt, steht in der Anleitung
    — und nirgends mehr, dass er die App sperrt."""
    text = " ".join(_abschnitt().split())
    assert f"**{D.TEXT_HILFE_ZEIGEN}**" in text
    for satz in ("ist ein eigenes Fenster über LightOS und sperrt nichts",
                 "holt das offene Fenster nach vorn",
                 "solange das Fenster des Assistenten das aktive ist",
                 "im Hauptfenster bleibt sie **GO**",
                 "Nach einem Show-Wechsel beginnt die Liste neu",
                 "Den Patch liest er bei jedem Festhalten neu",
                 "rollt nur der obere Teil"):
        assert satz in text, satz
    assert "modal" not in text.lower()
    englisch = " ".join(_abschnitt(
        "ANLEITUNG.en.md",
        "## 11. Take over scenes from another program (capture)").split())
    assert "non-modal window" in englisch and "space bar stays GO" in englisch
    programmer = (ROOT / "src" / "ui" / "views" / "programmer_view.py").read_text(encoding="utf-8")
    assert "zeige_assistent(self)" in programmer and "MitschnittDialog(self).exec()" not in programmer
