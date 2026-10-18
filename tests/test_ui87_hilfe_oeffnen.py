"""UI-87: Hilfe-Eintraege oeffnen verlaesslich — auch ueber Bedienhilfen und auf
einem Windows ohne Programm fuer ``.md``; ``systeminfo.txt`` nennt kein
Sitzungs-Log, das es nicht gibt.

Drei Befunde vom Windows-Testrechner (Sitzung D, 2026-10-10):

1. Ueber UI-Automation ausgeloest („Invoke“ am Menue-Eintrag — so arbeiten
   Screenreader und Sprachsteuerung) oeffnete „Datenordner öffnen“ KEINEN
   Explorer; im ``crash.log`` stand ``0x8001010d``. Der Klick lief in einem
   eingabe-synchronen Fensteraufruf, aus dem Windows nichts nach aussen starten
   laesst. Jetzt reicht ``hilfe.oeffne`` den Aufruf ueber die Ereignisschleife.
2. „Erste Schritte“/„Anleitungen öffnen“ zeigen im Quellbetrieb auf die lokale
   ``.md``. Ein frisches Windows hat dafuer kein Programm: es erschien der
   Dialog „Öffnen mit“, und ``openUrl`` meldete Erfolg. Jetzt die lokale Datei
   nur, wenn eine Zuordnung besteht — sonst der Link auf die Projektseite.
3. ``systeminfo.txt`` nannte den Pfad des Sitzungs-Logs auch, wenn es die Datei
   nicht gab.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                          # noqa: E402
from PySide6.QtCore import QUrl                        # noqa: E402
from PySide6.QtWidgets import QApplication             # noqa: E402

from src.core import diagnose_log as dl                # noqa: E402
from src.ui import hilfe                               # noqa: E402

_app = QApplication.instance() or QApplication([])


# ── 1. oeffnen ueber die Ereignisschleife ────────────────────────────────────

def test_oeffne_ruft_openurl_nicht_im_aufruf_selbst():
    url = QUrl("https://example.invalid/ui87")
    with mock.patch.object(hilfe.QDesktopServices, "openUrl", return_value=True) as offen:
        assert hilfe.oeffne(url) is True
        assert offen.call_count == 0, (
            "openUrl lief noch im Klick — aus einem eingabe-synchronen Aufruf "
            "(Bedienhilfen) startet Windows dann nichts")
        QApplication.processEvents()
        assert offen.call_count == 1
        assert offen.call_args[0][0] == url


def test_oeffne_ordner_legt_an_und_oeffnet_danach(tmp_path):
    ziel = tmp_path / "shows"
    with mock.patch.object(hilfe.QDesktopServices, "openUrl", return_value=True) as offen:
        assert hilfe.oeffne_ordner(str(ziel)) is True
        assert ziel.is_dir(), "der Ordner muss schon da sein, bevor geoeffnet wird"
        QApplication.processEvents()
        assert os.path.normpath(offen.call_args[0][0].toLocalFile()) == str(ziel)


def test_fehlschlag_beim_oeffnen_reisst_nichts_ab(capsys):
    with mock.patch.object(hilfe.QDesktopServices, "openUrl", side_effect=RuntimeError("kaputt")):
        hilfe.oeffne(QUrl("https://example.invalid/x"))
        QApplication.processEvents()
    with mock.patch.object(hilfe.QDesktopServices, "openUrl", return_value=False):
        hilfe.oeffne(QUrl("https://example.invalid/y"))
        QApplication.processEvents()
    aus = capsys.readouterr().out
    assert "openUrl fehlgeschlagen" in aus and "liess sich nicht oeffnen" in aus


# ── 2. lokale .md nur mit zugeordnetem Programm ──────────────────────────────

def test_ohne_zuordnung_geht_die_doku_zur_projektseite():
    with mock.patch.object(hilfe, "hat_zugeordnetes_programm", return_value=False):
        url = hilfe.doku_ziel(hilfe.ERSTE_SCHRITTE)
    assert not url.isLocalFile()
    assert url.toString() == hilfe.GITHUB_DOCS + hilfe.ERSTE_SCHRITTE


def test_mit_zuordnung_bleibt_es_bei_der_lokalen_datei():
    with mock.patch.object(hilfe, "hat_zugeordnetes_programm", return_value=True):
        url = hilfe.doku_ziel(hilfe.ANLEITUNGEN)
    assert url.isLocalFile()
    assert os.path.normpath(url.toLocalFile()) == str(ROOT / "docs" / "ANLEITUNGEN.md")


@pytest.mark.parametrize("antwort, erwartet", [
    (True, True),        # Programm zugeordnet
    (False, False),      # „App auswaehlen“
    (None, True),        # Frage ging nicht -> im Zweifel wie bisher lokal
])
def test_zuordnungsfrage_entscheidet(antwort, erwartet):
    gefragt = []
    assert hilfe.hat_zugeordnetes_programm(
        r"C:\x\ANLEITUNG.md", frage=lambda e: gefragt.append(e) or antwort) is erwartet
    assert gefragt == [".md"]


def test_ohne_endung_wird_nicht_gefragt():
    """Ordner oeffnet der Dateimanager — keine Zuordnungsfrage."""
    assert hilfe.hat_zugeordnetes_programm(
        r"C:\x\shows", frage=lambda e: pytest.fail("gefragt")) is True


def test_ausserhalb_von_windows_bleibt_alles_wie_bisher(monkeypatch):
    monkeypatch.setattr(hilfe.sys, "platform", "linux")
    monkeypatch.setattr(hilfe, "_windows_zuordnung",
                        lambda e: pytest.fail("unter Linux gefragt"))
    assert hilfe.hat_zugeordnetes_programm("/x/ANLEITUNG.md") is True


@pytest.mark.skipif(sys.platform != "win32", reason="fragt die Windows-Zuordnungen")
def test_windows_kennt_txt_aber_keine_erfundene_endung():
    """Am echten Windows: ohne das Flag „unbekannte ignorieren“ antwortete die
    Abfrage fuer JEDE Endung mit OpenWith.exe — also immer „ja“."""
    assert hilfe._windows_zuordnung(".txt") is True
    assert hilfe._windows_zuordnung(".ui87gibtesnicht") is False


# ── 3. systeminfo nennt kein Sitzungs-Log, das es nicht gibt ─────────────────

def _zeile(text: str) -> str:
    return next(z for z in text.splitlines() if z.strip().startswith("Sitzungs-Log:"))


def test_systeminfo_ohne_logdatei_nennt_keinen_pfad(tmp_path, monkeypatch):
    monkeypatch.setenv("LIGHTOS_LOG_DIR", str(tmp_path / "logs"))
    zeile = _zeile(dl.systeminfo_text("9.9.9"))
    assert dl.KEIN_SITZUNGS_LOG in zeile
    assert "lightos.log" not in zeile


def test_systeminfo_mit_logdatei_nennt_den_pfad(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / dl.LOG_NAME).write_text("x", encoding="utf-8")
    monkeypatch.setenv("LIGHTOS_LOG_DIR", str(logs))
    zeile = _zeile(dl.systeminfo_text("9.9.9"))
    assert dl.LOG_NAME in zeile and dl.KEIN_SITZUNGS_LOG not in zeile


def test_der_kopf_des_logs_nennt_seinen_pfad_immer(tmp_path, monkeypatch):
    """Der Kopfblock entsteht, BEVOR die Datei geoeffnet wird — dort waere
    „keins“ falsch."""
    monkeypatch.setenv("LIGHTOS_LOG_DIR", str(tmp_path / "noch_nicht_da"))
    zeile = _zeile(dl.kopfblock("9.9.9"))
    assert dl.LOG_NAME in zeile and dl.KEIN_SITZUNGS_LOG not in zeile
