"""ENG-39: Doku-Waechter fuer den Abschnitt „Hinweis bei Überschneidungen“.

Die Anleitung zitiert die Saetze so, wie der Code sie baut, und nennt die
Bedienelemente mit dem Wortlaut der Oberflaeche.
"""
from pathlib import Path
from types import SimpleNamespace

from backlog_eintrag import eintrag
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
        bausteine=("D",), geraete=frozenset({1, 2}),
        geraete_text=U.geraete_text([1, 2], [("Hintergrund", [1, 2])]),
        verhaeltnis=verhaeltnis, stufen_abstand=abstand)


def test_anleitung_zitiert_die_saetze_wie_der_code_sie_baut():
    text = _flach(_text(ANLEITUNG))
    assert _treffer("Lauflicht HG", U.GLEICH, 0).satz() in text
    assert _treffer("Blinder", U.DIESE_TIEFER, 1).satz() in text
    assert U.MAX_AUSGESCHRIEBEN == 3 and "Höchstens drei Treffer" in text
    # Die Restzeile der Anleitung ist genau die, die der Code baut.
    rest = ([_treffer("A", U.GLEICH, 0)]
            + [_treffer(n, U.DIESE_HOEHER, 1) for n in ("B", "C")])
    assert f"**{U._rest_zeile(rest, 'Taste')}**" in text
    assert "gegen die diese Taste **verliert**" in text
    assert "**vollständige Liste**" in text and "Tooltip" in text


def test_anleitung_hat_den_abschnitt_und_die_nummern_stimmen():
    text = _text(ANLEITUNG)
    assert "## 7. Hinweis bei Überschneidungen" in text
    assert "## 8. Was die Stufen nicht regeln" in text
    assert text.index("## 6. ") < text.index("## 7. ") < text.index("## 8. ")
    assert "nur eine Auskunft" in text
    # DOC-73: Bild 9 (Eigenschaften einer Taste mit dem gelben Hinweis) ist da.
    assert "(img/09_ueberschneidung.png)" in text
    assert (ANLEITUNG.parent / "img" / "09_ueberschneidung.png").is_file()


def test_anleitung_nennt_die_bedienelemente_wie_im_code():
    text = _text(ANLEITUNG)
    taste = _text(REPO / "src/ui/virtualconsole/vc_button.py")
    fader = _text(REPO / "src/ui/virtualconsole/vc_slider.py")
    # Der Hinweis steht gleich unter „Aktion“, ueber die ganze Breite — im
    # Dialog wie im Inspector, ausserhalb der Klappbereiche.
    assert '("Beschriftung:", cap), ("Aktion:", act)' in taste
    assert 'form.addRow(S["ueberschneidungs_hinweis"])' in taste
    assert 'v.addWidget(S["ueberschneidungs_hinweis"])' in taste
    assert '("Hinweis:", ueberschn_hinweis)' not in taste
    assert "gleich unter **Aktion** ein gelber **Hinweis**" in text
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
        assert "… und n weitere Überschneidungen: …" in text, datei
        assert "**Aktion**" in text, datei


def test_fragmente_liegen_vor():
    # Fragment oder (nach dem Einsammeln) Zeile in BACKLOG.md — beides gilt.
    assert "ENG-39" in eintrag(REPO, "ENG-39")
    assert list((REPO / "changelog.d").glob("*-ENG-39.md"))


# ── Nachtrag: Fader zaehlen immer mit, Solo-Frame als Exklusiv-Gruppe ────────

def test_anleitung_zitiert_die_saetze_zum_fader_bei_null():
    flach = _flach(_text(ANLEITUNG).replace("> ", ""))
    assert U.HALTE_SATZ_FADER in flach
    assert U._halte_satz("„Wash HG“") in flach
    assert U._halte_satz("„Wash HG“", "Ein anderer Fader") in flach, (
        "stoppt der Fader selbst, haelt den Effekt ein ANDERER Fader")
    assert "**Fader zählen immer mit.**" in _text(ANLEITUNG)
    assert "ohne den Haken regelt er bloß und zählt nicht" not in _text(ANLEITUNG), (
        "die alte Regel „ohne den Haken zaehlt der Fader nicht“ ist abgeloest")


def test_anleitung_nennt_die_grenzen_der_exklusiv_gruppe():
    text = _text(ANLEITUNG)
    rahmen = _text(REPO / "src/ui/virtualconsole/vc_frame.py")
    haken = "Solo-Frame (nur 1 Button gleichzeitig aktiv)"
    assert f"**{haken}**" in _flach(text) and haken in rahmen
    for wort in ("**Unter-Rahmen**", "**Fader** im Solo-Rahmen",
                 "**verschiedene** Solo-Rahmen", "**außerhalb**",
                 "**Sammlung**"):
        assert wort in text, wort


def test_fader_anleitung_nennt_die_hinweiszeile():
    fader = _text(REPO / "src/ui/virtualconsole/vc_slider.py")
    assert 'subjekt="Fader"' in fader
    assert "form.insertRow(form.getWidgetPosition(target_editor)[0] + 1" in fader
    for datei in ("docs/anleitung_vc_widgets/02_fader.md",
                  "docs/anleitung_vc_widgets/02_fader.en.md"):
        text = _text(REPO / datei)
        assert "| **Hinweis**" in text, datei
        assert "**Steuert**" in text, datei
        assert U.HALTE_SATZ_FADER in text, datei
        assert "Ein anderer Fader hält „…“ auch bei 0 am Laufen" in text, datei
        assert "anleitung_prioritaeten/ANLEITUNG.md#7-hinweis-bei-überschneidungen" in text, datei
    for datei in ("docs/anleitung_vc_widgets/01_button.md",
                  "docs/anleitung_vc_widgets/01_button.en.md"):
        text = _text(REPO / datei)
        assert "auch bei 0 am Laufen" in text, datei
        assert "Solo-Frame" in text or "solo frame" in text, datei
