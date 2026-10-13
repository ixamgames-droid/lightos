"""ENG-39: Doku-Waechter fuer den Abschnitt „Hinweis bei Überschneidungen“.

Die Anleitung zitiert die Saetze so, wie der Code sie baut, und nennt die
Bedienelemente mit dem Wortlaut der Oberflaeche.
"""
from pathlib import Path
from types import SimpleNamespace

from src.core.engine import ueberschneidung as U

REPO = Path(__file__).resolve().parent.parent
ANLEITUNG = REPO / "docs" / "anleitung_prioritaeten" / "ANLEITUNG.md"


def _text(pfad: Path) -> str:
    return pfad.read_text(encoding="utf-8")


def _flach(text: str) -> str:
    """Zitatzeichen und Umbrueche der Anleitung glaetten."""
    return " ".join(text.replace("\n   > ", " ").replace(">", " ").split())


def _treffer(andere_name, verhaeltnis, abstand):
    return U.Treffer(
        eigene=SimpleNamespace(name="Puls", priority=0),
        andere=SimpleNamespace(name=andere_name, priority=0),
        bausteine=("D",), geraete=frozenset({1, 2}), geraete_text="Hintergrund",
        verhaeltnis=verhaeltnis, stufen_abstand=abstand)


def test_anleitung_zitiert_die_saetze_wie_der_code_sie_baut():
    text = _flach(_text(ANLEITUNG))
    assert _treffer("Lauflicht HG", U.GLEICH, 0).satz() in text
    assert _treffer("Blinder", U.DIESE_TIEFER, 1).satz() in text
    assert "**… und n weitere**" in text
    assert U.MAX_AUSGESCHRIEBEN == 3 and "Höchstens drei Treffer" in text


def test_anleitung_hat_den_abschnitt_und_die_nummern_stimmen():
    text = _text(ANLEITUNG)
    assert "## 7. Hinweis bei Überschneidungen" in text
    assert "## 8. Was die Stufen nicht regeln" in text
    assert text.index("## 6. ") < text.index("## 7. ") < text.index("## 8. ")
    assert "nur eine Auskunft" in text
    assert "9. Eigenschaften einer Taste mit dem gelben Hinweis" in text


def test_anleitung_nennt_die_bedienelemente_wie_im_code():
    text = _text(ANLEITUNG)
    taste = _text(REPO / "src/ui/virtualconsole/vc_button.py")
    fader = _text(REPO / "src/ui/virtualconsole/vc_slider.py")
    assert '("Hinweis:", ueberschn_hinweis)' in taste
    assert '("Ziele:", target_editor)' in taste
    assert "Zeile **Hinweis**" in text and "unter **Ziele**" in text
    for wort in ("Funktion an/aus", "Funktion (nur gehalten)"):
        assert f"**{wort}**" in text and f'"{wort}"' in taste, wort
    haken = "bei 0 wirklich stoppen (sonst nur runterregeln)"
    assert f"**{haken}**" in text and haken in fader


def test_anleitung_sagt_wann_kein_hinweis_kommt():
    text = _text(ANLEITUNG)
    for wort in ("**Farbe gegen Dimmer**", "**Geräteart**", "**keiner Taste**",
                 "**Solo-Rahmen**", "**Sonstiges**", "Stufe des Behälters"):
        assert wort in text, wort


def test_button_anleitung_nennt_die_hinweiszeile():
    for datei in ("docs/anleitung_vc_widgets/01_button.md",
                  "docs/anleitung_vc_widgets/01_button.en.md"):
        text = _text(REPO / datei)
        assert "| Hinweis" in text, datei
        assert "anleitung_prioritaeten/ANLEITUNG.md#7-hinweis-bei-überschneidungen" in text, datei
        assert "… und n weitere" in text, datei


def test_fragmente_liegen_vor():
    backlog = _text(REPO / "backlog.d" / "ENG-39.md")
    assert backlog.startswith("ID: ENG-39\n")
    assert list((REPO / "changelog.d").glob("*-ENG-39.md"))
