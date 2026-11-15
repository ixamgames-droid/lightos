"""DOC-78: GitHub-Seite und Anleitungen — Stimmigkeit, Datenschutz, Schluessel.

Reiner Text-Test: liest README/INSTALL/CONTRIBUTING/Vorlagen und den Quelltext
als Text, importiert nichts aus ``src`` und startet nichts. Er haelt fest, dass
die neuen Abschnitte nur nennen, was der Code auch hergibt — Menuenamen,
Startschalter, Dateinamen im Datenordner, Knopftexte.
"""
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _lies(*teile: str) -> str:
    with open(os.path.join(REPO, *teile), encoding="utf-8") as f:
        return f.read()


def _abschnitt(text: str, ueberschrift: str) -> str:
    m = re.search(rf"^## {re.escape(ueberschrift)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert m, f"Abschnitt „## {ueberschrift}“ fehlt"
    return m.group(1)


def _slug(ueberschrift: str) -> str:
    """GitHub-Anker: klein, Satzzeichen weg, Leerzeichen -> Bindestrich."""
    return re.sub(r"[^\w\- ]", "", ueberschrift.strip().lower()).replace(" ", "-")


def test_datenschutz_abschnitt_nennt_die_privaten_dateien():
    teil = _abschnitt(_lies("README.md"), "Datenschutz: was privat bleibt")
    for name in ("current_show.db", "universes.json", "midi_mappings.json",
                 "ui_prefs.json", "lightos-lizenz.lic", "LightOS-Diagnose-",
                 "auto_save.lshow"):
        assert name in teil, name
    # Belegt im Code: dort heissen die Dateien wirklich so.
    pfade = _lies("src", "core", "paths.py")
    for name in ("current_show.db", "universes.json", "midi_mappings.json"):
        assert f'"{name}"' in pfade, name
    assert '"ui_prefs.json"' in _lies("src", "web", "remote_settings.py")
    assert 'DATEINAME = "lightos-lizenz.lic"' in _lies("src", "core", "lizenz.py")
    assert "LightOS-Diagnose-" in _lies("src", "core", "diagnose_log.py")
    assert "nie" in teil and "Issue" in teil


def test_diagnosepaket_inhalt_stimmt_mit_dem_code():
    teil = _abschnitt(_lies("README.md"), "Datenschutz: was privat bleibt")
    code = _lies("src", "core", "diagnose_log.py")
    m = re.search(r"PAKET_INHALT = \((.*?)\)\n", code, re.S)
    assert m
    inhalt = m.group(1)
    for stichwort in ("Sitzungs-Logs", "crash.log", "Systeminfo", "Einstellungen",
                      "Datei-NAMEN", "Show-Dateien", "Datenbanken", "%USERNAME%"):
        assert stichwort in inhalt, stichwort
    for stichwort in ("Sitzungs-Logs", "crash.log", "Systeminfo", "Einstellungen",
                      "Show-Dateien", "Datenbanken", "%USERNAME%"):
        assert stichwort in teil, stichwort
    # Der Weg „privat schicken" ist der, den der Dialog in der App nennt.
    assert "per E-Mail oder Messenger" in _lies("src", "ui", "main_window.py")
    assert "E-Mail oder Messenger" in teil


def test_schluessel_erneuern_heisst_wie_der_knopf():
    knopf = "Schlüssel erneuern (neues Token)"
    assert f'"{knopf}"' in _lies("src", "ui", "widgets", "web_remote_dialog.py")
    readme = _lies("README.md")
    assert readme.count(knopf) >= 2   # Datenschutz und Handy-Abschnitt


def test_touch_und_handy_abschnitt_stimmt_mit_dem_code():
    teil = _abschnitt(_lies("README.md"), "Touchscreen und Handy")
    assert "Ansicht → Touch-Gesten…" in teil
    fenster = _lies("src", "ui", "main_window.py")
    assert 'am.addAction("Touch-Gesten…")' in fenster
    assert 'mb.addMenu("&Ansicht")' in fenster
    assert "Web-Remote: Verbindung & Token…" in teil
    assert '"Web-Remote: Verbindung && Token…"' in fenster
    assert "📱 Handy verbinden" in teil
    assert "📱 Handy verbinden" in _lies("src", "ui", "widgets", "web_remote_dialog.py")
    assert "„Mehrfach“" in teil
    assert 'QPushButton("Mehrfach")' in _lies("src", "ui", "views",
                                               "virtual_console_view.py")
    # Keine Sicherheitsaktion auf einer Geste — so steht es im Code.
    gesten = _lies("src", "ui", "gesten_prefs.py")
    assert "blackout" not in gesten.split("DREI_FINGER_AKTIONEN = (")[1].split(")\n")[0].lower()
    assert "BLACKOUT, STOP ALL" in teil
    assert "](docs/anleitung_web_remote/LASER_VOM_HANDY.md)" in teil


def test_start_optionen_gibt_es_wirklich():
    readme = _lies("README.md")
    main = _lies("main.py")
    for schalter in ("--touch", "--kiosk", "--show", "--diagnose"):
        assert f'"{schalter}"' in main, schalter
        assert f"| `{schalter}" in readme, schalter


def test_inhaltszeile_zeigt_auf_vorhandene_ueberschriften():
    readme = _lies("README.md")
    zeile = readme.split("**Auf dieser Seite:**", 1)[1].split("\n\n", 1)[0]
    anker = re.findall(r"\]\(#([^)]+)\)", zeile)
    assert len(anker) >= 6
    vorhanden = {_slug(u) for u in re.findall(r"^## (.+)$", readme, re.M)}
    for a in anker:
        assert a in vorhanden, a


def test_issue_vorlage_will_keine_privaten_anhaenge():
    vorlage = _lies(".github", "ISSUE_TEMPLATE", "bug_report.md")
    assert "Diagnosepaket speichern…" in vorlage          # DOC-69 bleibt
    assert "NICHT hier anhängen" in vorlage
    assert "Diagnosepaket angehängt" not in vorlage
    for name in (".lshow", "universes.json", "ui_prefs.json"):
        assert name in vorlage, name
    # Die alte Bitte, Show-Dateien hochzuladen, ist weg.
    assert "Show-Dateien (.lshow) die das Problem reproduzieren" not in vorlage


def test_install_und_contributing_verweisen_auf_den_datenschutz():
    for datei in ("INSTALL.md", "CONTRIBUTING.md"):
        text = _lies(datei)
        assert "README.md#datenschutz-was-privat-bleibt" in text, datei
    install = _lies("INSTALL.md")
    assert "ui_prefs.json" in install and "lightos-lizenz.lic" in install
    assert "Nicht** an ein oeffentliches" in install


def test_anleitungs_uebersicht_nennt_touch_und_handy():
    text = _lies("docs", "ANLEITUNGEN.md")
    assert "../README.md#touchscreen-und-handy" in text
    assert "../README.md#datenschutz-was-privat-bleibt" in text


def test_relative_links_der_startseiten_zeigen_auf_dateien():
    """Jede relative Verlinkung in README/INSTALL/CONTRIBUTING und docs/*.md
    (ohne Unterordner) zeigt auf eine vorhandene Datei. HTML-Kommentare zaehlen
    nicht — dort steht bewusst ein Bild, das es noch nicht gibt."""
    import glob
    dateien = [os.path.join(REPO, n) for n in ("README.md", "INSTALL.md", "CONTRIBUTING.md")]
    dateien += sorted(glob.glob(os.path.join(REPO, "docs", "*.md")))
    link = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)|"
                      r"(?:href|src)=\"([^\"]+)\"")
    fehlt = []
    for pfad in dateien:
        text = _lies(pfad)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        text = re.sub(r"`[^`\n]*`", "", text)
        for m in link.finditer(text):
            ziel = (m.group(1) or m.group(2) or "").split("#", 1)[0]
            if not ziel or re.match(r"^[a-z]+:", ziel) or ziel.startswith("//"):
                continue
            from urllib.parse import unquote
            voll = os.path.normpath(os.path.join(os.path.dirname(pfad), unquote(ziel)))
            if not os.path.exists(voll):
                fehlt.append(f"{os.path.relpath(pfad, REPO)} -> {ziel}")
    assert fehlt == [], fehlt
