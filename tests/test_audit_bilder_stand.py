"""Waechter fuer `tools/audit_bilder_stand.py` — die Zeitrechnung des Werkzeugs.

Das Werkzeug beantwortet eine einzige Frage: *wurde dieses Bild nach dem Audit
angefasst?* Und genau daran ist es beim ersten Anlauf gescheitert — es verglich
**tagesgenau**, waehrend die Nacharbeit **drei Stunden** nach dem Audit lief.
Ergebnis: vier laengst erneuerte Bilder standen als „offen", und beim
Nachaufnehmen waere ein besseres Bild durch ein schlechteres ersetzt worden.

Deshalb testet diese Datei nicht die Ausgabeformatierung, sondern die
Entscheidung: `ist_neuer()`.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "tools"))

import audit_bilder_stand as abs_tool  # noqa: E402


# --- Der Fall, der es kaputt gemacht hat -----------------------------------
# Audit-Commit 62fe358d am 2026-07-20 19:18:49, Bilder-Commit ac1c76c6 am
# selben Tag um 22:39:34. Tagesgenau sind beide „2026-07-20".
_AUDIT = "2026-07-20T19:18:49+02:00"
_NACHARBEIT = "2026-07-20T22:39:34+02:00"


def test_nacharbeit_am_selben_tag_zaehlt_als_erneuert():
    """Der konkrete Fehlschlag vom 2026-08-03, als Test festgenagelt."""
    assert abs_tool.ist_neuer(_NACHARBEIT, _AUDIT) is True


def test_aelter_als_das_audit_bleibt_offen():
    assert abs_tool.ist_neuer("2026-06-21T10:00:00+02:00", _AUDIT) is False


def test_gleicher_zeitpunkt_ist_nicht_neuer():
    """Ein Bild, das im Audit-Commit selbst liegt, ist nicht die Nacharbeit."""
    assert abs_tool.ist_neuer(_AUDIT, _AUDIT) is False


def test_eine_sekunde_spaeter_reicht():
    assert abs_tool.ist_neuer("2026-07-20T19:18:50+02:00", _AUDIT) is True


# --- Zeitzonen: der Grund, warum String-Vergleich nicht genuegt ------------
def test_sommerzeit_wechsel_wird_nicht_alphabetisch_verglichen():
    """`+01:00` vs `+02:00` — alphabetisch faellt die Antwort falsch aus.

    `2026-10-25T02:00:00+01:00` ist 01:00 UTC und damit SPAETER als
    `2026-10-25T02:30:00+02:00` (00:30 UTC), obwohl die Zeichenkette kleiner
    ist. Ein `>` auf Strings wuerde hier „nicht neuer" sagen.
    """
    frueher = "2026-10-25T02:30:00+02:00"   # 00:30 UTC
    spaeter = "2026-10-25T02:00:00+01:00"   # 01:00 UTC
    assert spaeter < frueher                 # ... alphabetisch verdreht
    assert abs_tool.ist_neuer(spaeter, frueher) is True
    assert abs_tool.ist_neuer(frueher, spaeter) is False


# --- Unbekanntes darf nicht als erledigt durchrutschen ---------------------
@pytest.mark.parametrize("bild,stich", [
    ("", _AUDIT),            # Bild ohne Git-Historie
    (_NACHARBEIT, ""),       # Audit ohne Anlage-Commit
    ("", ""),
    ("kein Datum", _AUDIT),  # Format geaendert
    (_NACHARBEIT, "17.07.2026"),
    # Ohne Zeitzone — wirft TypeError, nicht ValueError. Waere die Ausnahme
    # nicht mitgefangen, riss das Werkzeug hier ab, statt den Punkt offen
    # zu lassen.
    ("2026-07-20T22:39:34", _AUDIT),
    (_NACHARBEIT, "2026-07-20T19:18:49"),
])
def test_unbekannte_zeit_laesst_den_punkt_offen(bild, stich):
    """Im Zweifel offen — ein Punkt darf nicht stillschweigend verschwinden."""
    assert abs_tool.ist_neuer(bild, stich) is False


# --- Der Stichzeitpunkt kommt aus git, nicht aus dem Dateinamen -----------
def test_stichzeit_stammt_aus_dem_anlage_commit():
    """Nicht aus dem Datum im Dateinamen — sonst fehlt die Uhrzeit."""
    audit = os.path.join(_REPO, "docs", "BILDER_AUDIT_2026-07-20.md")
    if not os.path.exists(audit):
        pytest.skip("Audit-Datei nicht vorhanden")
    zeit = abs_tool._audit_zeitpunkt(audit)
    assert zeit.startswith("2026-07-20T"), zeit
    # Eine Uhrzeit, die nicht Mitternacht ist — genau das fehlte vorher.
    assert zeit[11:19] != "00:00:00", "Stichzeit ohne Uhrzeit ist der alte Bug"


def test_werkzeug_laeuft_durch_und_meldet_null_offen():
    """Ende-zu-Ende: das Audit vom 20.07. ist abgearbeitet.

    Bewusst als Gesamtaussage geprueft, nicht je Bild — die Datei ist der
    Beleg, dass die Nacharbeit vollstaendig war. Wird spaeter ein Bild
    zurueckgedreht, faellt es hier auf.
    """
    audit = os.path.join(_REPO, "docs", "BILDER_AUDIT_2026-07-20.md")
    if not os.path.exists(audit):
        pytest.skip("Audit-Datei nicht vorhanden")
    r = subprocess.run(
        [sys.executable, os.path.join(_REPO, "tools", "audit_bilder_stand.py"),
         audit], cwd=_REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "OFFEN: 0" in r.stdout, r.stdout
