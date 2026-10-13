"""ENG-35: Doku-Waechter fuer „Wer gewinnt? Prioritäten für Effekte“.

Die Anleitung nennt die Stufen mit denselben Namen und Zahlen wie der Code,
steht im Verzeichnis der Anleitungen, und der veraltete Merge-Vertrag verweist
deutlich auf sie.
"""
from pathlib import Path

from src.core.engine import stufen

REPO = Path(__file__).resolve().parent.parent
ANLEITUNG = REPO / "docs" / "anleitung_prioritaeten" / "ANLEITUNG.md"


def _text(pfad: Path) -> str:
    return pfad.read_text(encoding="utf-8")


def test_anleitung_nennt_alle_stufen_und_ihre_zahlen():
    text = _text(ANLEITUNG)
    for s in stufen.STUFEN:
        assert f"**{s.name}**" in text, s.name
    zahlen = [str(s.zahl).replace("-", "−") for s in stufen.STUFEN]
    assert "−20, 0, 20, 40 und 60" in text
    assert zahlen == ["−20", "0", "20", "40", "60"]


def test_anleitung_nennt_die_bedienelemente_wie_im_code():
    text = _text(ANLEITUNG)
    ansicht = _text(REPO / "src/ui/views/prioritaeten_view.py")
    for wort in ("▲ Stufe höher", "▼ Stufe tiefer", "Auswahl in Stufe",
                 "● läuft", "Fasst an"):
        assert wort in text, wort
        assert wort in ansicht, f"„{wort}“ steht nicht mehr in der Ansicht"
    assert stufen.SNAP_ZEILE in text
    assert "eigene Zahl (10)" in text and "eigene Zahl (n)" in text
    haupt = _text(REPO / "src/ui/main_window.py")
    assert '"Prioritäten"' in haupt and "Reiter **Prioritäten**" in text


def test_anleitung_sagt_was_die_stufen_nicht_regeln():
    text = _text(ANLEITUNG)
    assert "Sammlung, Chaser, Show" in text
    assert "zuletzt gestartet" in text
    assert "getrennte Kanäle" in text, "Farbe und Dimmer bleiben getrennt"
    assert "Kein „Untergrund“" in text


def test_anleitung_hat_die_liste_der_fehlenden_bilder():
    text = _text(ANLEITUNG)
    assert "## Bilder, die noch aufzunehmen sind" in text
    assert "![" not in text, "noch keine Bilder — sonst die Liste kuerzen"


def test_anleitung_steht_im_verzeichnis():
    index = _text(REPO / "docs" / "ANLEITUNGEN.md")
    assert "anleitung_prioritaeten/ANLEITUNG.md" in index


def test_merge_vertrag_verweist_deutlich_auf_die_anleitung():
    vertrag = _text(REPO / "docs" / "OUTPUT_MERGE_CONTRACT.md")
    kopf = vertrag[:vertrag.index("## Ein Renderer, ein Thread")]
    assert "nicht mehr vollständig" in kopf
    assert "anleitung_prioritaeten/ANLEITUNG.md" in kopf
    assert "Function.priority" in vertrag, "Zeile 2 nennt die Prioritaet"


def test_editor_anleitungen_nennen_das_feld_stufe():
    for datei in ("docs/anleitung_dimmermatrix/ANLEITUNG_DIMMERMATRIX.md",
                  "docs/anleitung_efx/ANLEITUNG_EFX.md",
                  "docs/anleitung_vc_widgets/19_matrix_editor.md",
                  "docs/anleitung_vc_widgets/19_matrix_editor.en.md"):
        text = _text(REPO / datei)
        assert "**Stufe**" in text, datei
        assert "**Layer-Priorität**" not in text, datei


# ── VCB-46: Haken „übersteuert laufende Dimmer-Effekte“ ─────────────────────

def test_anleitung_beschreibt_den_haken_mit_dem_wortlaut_der_taste():
    text = _text(ANLEITUNG)
    taste = _text(REPO / "src/ui/virtualconsole/vc_button.py")
    for wort in ("übersteuert laufende Dimmer-Effekte", "Dimmer (Snap)",
                 "Tasten-Modus (Snap)", "Ziel und Verhalten"):
        assert wort in text, wort
        assert wort in taste, f"„{wort}“ steht nicht mehr an der Taste"
    assert "## 6. Blinder und Strobe als Snap-Taste" in text
    assert "(#6-blinder-und-strobe-als-snap-taste)" in text
    assert "Die Farbe bleibt getrennt" in text
    assert "eigenem Dimmer-Kanal" in text
    assert "Blackout und Laser-NOT-AUS" in text


def test_button_anleitung_nennt_den_haken():
    for datei in ("docs/anleitung_vc_widgets/01_button.md",
                  "docs/anleitung_vc_widgets/01_button.en.md"):
        text = _text(REPO / datei)
        assert "| Dimmer (Snap) |" in text, datei
        assert "übersteuert laufende Dimmer-Effekte" in text, datei


def test_merge_vertrag_nennt_die_snap_ausnahme():
    vertrag = _text(REPO / "docs" / "OUTPUT_MERGE_CONTRACT.md")
    assert "VCB-46" in vertrag and "snap_dimmer_override" in vertrag
