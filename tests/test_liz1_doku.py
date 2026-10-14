"""LIZ-1: Lizenztext und Doku stimmen mit dem Programm ueberein."""
from __future__ import annotations

import os
import re

from src.core import lizenz

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _lies(*teile) -> str:
    with open(os.path.join(ROOT, *teile), encoding="utf-8") as fh:
        return fh.read()


def test_license_nennt_urheber_und_die_kernpunkte():
    text = _lies("LICENSE")
    assert "Copyright (c) 2026 ixamgames-droid" in text
    assert lizenz.QUELLE in text
    for stelle in ("Alle Rechte vorbehalten", "Ansehen ist erlaubt",
                   "schriftliche Erlaubnis", "nicht übertragbar",
                   "THIRD_PARTY_NOTICES.md", "licenses/", "GitHub",
                   "Keine Gewähr", "keine Rechtsberatung",
                   "English version", "All rights reserved",
                   "Viewing is permitted", "not legal advice"):
        assert stelle in text, stelle
    # deutsch zuerst, englisch darunter
    assert text.index("Deutsche Fassung") < text.index("English version")
    assert "§" not in text


def test_license_schraenkt_fremde_lizenzen_nicht_ein():
    text = _lies("LICENSE")
    assert "schränkt keine Rechte ein" in text
    assert "does not restrict any rights" in text


def test_readme_hat_den_abschnitt_und_nicht_mehr_ohne_lizenz():
    text = _lies("README.md")
    assert "### Lizenz und Urheber" in text
    assert "ohne Lizenz" not in text
    assert "ixamgames-droid" in text
    assert "(LICENSE)" in text and "(docs/LIZENZ_UND_TESTZUGANG.md)" in text


def test_install_verweist_auf_die_seite():
    text = _lies("INSTALL.md")
    assert "docs/LIZENZ_UND_TESTZUGANG.md" in text
    assert lizenz.DATEINAME in text


def test_doku_nennt_was_das_programm_tut():
    text = _lies("docs", "LIZENZ_UND_TESTZUGANG.md")
    assert lizenz.DATEINAME in text
    assert lizenz.ENV_PFAD in text
    assert lizenz.QUELLE in text
    assert f"{lizenz.VORWARN_TAGE} Tagen" in text
    for stelle in ("nur beim Programmstart", "nie unterbrochen",
                   "nie ins Internet", "Lizenzdatei auswählen…",
                   "LightOS — Testlizenz erforderlich",
                   r"%APPDATA%\LightOS", "~/.local/share/LightOS"):
        assert stelle in text, stelle


def test_doku_dialogtexte_gibt_es_im_programm():
    """Was die Seite an Knoepfen und Fenstertiteln nennt, steht so im Dialog."""
    quelle = _lies("src", "ui", "lizenz_dialog.py")
    for stelle in ("LightOS — Testlizenz erforderlich", "Lizenzdatei auswählen…",
                   "Lizenztext anzeigen", "Beenden"):
        assert stelle in quelle, stelle


def test_datenordner_in_der_doku_passt_zur_pfadschicht():
    """Windows liegt unter APPDATA (Roaming), nicht LOCALAPPDATA."""
    pfade = _lies("src", "core", "paths.py")
    assert 'os.environ.get("APPDATA")' in pfade
    for datei in (("docs", "LIZENZ_UND_TESTZUGANG.md"), ("INSTALL.md",)):
        assert "LOCALAPPDATA" not in "".join(
            z for z in _lies(*datei).splitlines() if "lizenz" in z.lower())


def test_fragmente_nennen_die_id():
    assert re.search(r"^ID: LIZ-1$", _lies("backlog.d", "LIZ-1.md"), re.M)
    assert "(LIZ-1)" in _lies("changelog.d", "2026-10-12-LIZ-1.md").splitlines()[0]
