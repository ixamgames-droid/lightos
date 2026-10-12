"""STAB-38: harter Absturz im Matrix-Editor, sobald beim Lauflicht (Chase) die
Bewegung auf „Ping-Pong“ gestellt wird.

Befund (Vorfuehrung, 12.10.2026): Effekt-Editor, Matrix, Lauflicht, Auswahlbox
„Bewegung“ auf „Ping-Pong“ — die App war weg. Kein Python-Traceback, im
Absturzprotokoll „Fatal Python error: Segmentation fault“ mit dem Hauptthread
in der Qt-Ereignisschleife.

Ursache: die Parameterfelder unter „Bewegung & Parameter“ werden je nach Wert
neu aufgebaut (bei „Ping-Pong“ entfallen „Laeufer-Anzahl“ und „Schweif“). Der
Neuaufbau lief IM Signal der Auswahlbox und raeumte die alten Zeilen mit
``QFormLayout.removeRow`` ab — das loescht die Widgets SOFORT, also auch die
Auswahlbox, deren Signal gerade laeuft. Qt arbeitet nach dem Signal auf der
geloeschten Box weiter (Aufklappliste schliessen, ``activated`` senden) und
greift in freigegebenen Speicher.

Geprueft wird dreifach:

1. die Ursache selbst, sofort und ohne Zufall: die sendende Auswahlbox lebt
   noch, wenn ihr Signal zurueckkehrt, und ist erst nach der naechsten Runde
   der Ereignisschleife weg;
2. ein Waechter gegen neue ``removeRow``-Aufrufe an Formular-Layouts der
   Oberflaeche;
3. die Reproduktion als Schleife in einem KINDPROZESS mit echter Ansicht und
   echter Bedienung (Aufklappliste oeffnen, Eintrag anklicken) — ein Absturz
   reisst so den Testlauf nicht mit.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parents[1]
_ROLLE = os.environ.get("STAB38_ARBEITER", "")
_MARKE = "STAB38-UEBERLEBT"


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _verzoegert_loeschen():
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()


def _ansicht_mit_lauflicht():
    """Matrix-Ansicht mit einer EIGENEN, frischen Matrix im Lauflicht."""
    from src.core.engine.rgb_matrix import RgbAlgorithm
    from src.ui.views.rgb_matrix_view import RgbMatrixView
    ansicht = RgbMatrixView()
    ansicht._add()
    assert ansicht._current is not None, "keine aktive Matrix nach dem Anlegen"
    ansicht._algo_combo.setCurrentText(RgbAlgorithm.CHASE.value)
    assert "movement" in ansicht._param_widgets, "Lauflicht ohne Feld „Bewegung“"
    return ansicht


# ── 1. Ursache: die sendende Auswahlbox ueberlebt ihr eigenes Signal ─────────


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
class TestSenderUeberlebtSeinSignal:

    def test_bewegung_auf_ping_pong_loescht_die_box_nicht_im_signal(self):
        import shiboken6
        _app()
        ansicht = _ansicht_mit_lauflicht()
        box = ansicht._param_widgets["movement"]
        vorher = list(ansicht._param_widgets)
        assert "runner_count" in vorher

        box.setCurrentIndex(box.findData("bounce"))

        # Der Wechsel hat die Felder wirklich neu aufgebaut …
        assert ansicht._current.params["movement"] == "bounce"
        assert "runner_count" not in ansicht._param_widgets
        neu = ansicht._param_widgets["movement"]
        assert neu is not box, "Felder wurden nicht neu aufgebaut — Test prueft nichts"
        assert neu.currentData() == "bounce"
        # … und die Box, deren Signal das ausgeloest hat, lebt noch: Qt arbeitet
        # nach dem Signal auf ihr weiter.
        assert shiboken6.isValid(box), (
            "die sendende Auswahlbox wurde in ihrem eigenen Signal geloescht — "
            "Qt greift danach in freigegebenen Speicher (STAB-38)")
        # … aber nicht mehr zu sehen: ihr alter Traeger ist versteckt.
        assert box.parentWidget().isHidden()
        assert box.parentWidget() is not ansicht._param_traeger

        # Mit der naechsten Runde der Ereignisschleife ist sie dann weg.
        _verzoegert_loeschen()
        assert not shiboken6.isValid(box)
        ansicht.deleteLater()

    def test_alte_zeilen_bleiben_nicht_sichtbar_liegen(self):
        """Verzoegertes Loeschen darf keine doppelten Zeilen zeigen: bis die
        alten Felder weg sind, sind sie versteckt und nicht mehr im Formular."""
        _app()
        ansicht = _ansicht_mit_lauflicht()
        box = ansicht._param_widgets["movement"]
        box.setCurrentIndex(box.findData("bounce"))
        formular = ansicht._param_form
        assert formular.rowCount() == len(ansicht._param_widgets)
        _verzoegert_loeschen()
        assert formular.rowCount() == len(ansicht._param_widgets)
        # und zurueck: die bedingten Felder kommen wieder
        box = ansicht._param_widgets["movement"]
        box.setCurrentIndex(box.findData("normal"))
        assert "runner_count" in ansicht._param_widgets
        assert ansicht._param_form.rowCount() == len(ansicht._param_widgets)
        _verzoegert_loeschen()
        ansicht.deleteLater()


# ── 2. Waechter: kein sofortiges Zeilen-Loeschen in der Oberflaeche ─────────


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
def test_kein_removerow_an_formular_layouts():
    """``QFormLayout.removeRow`` loescht die Widgets der Zeile SOFORT. Laeuft
    das im Signal eines dieser Widgets, stuerzt die App hart ab. Tabellen
    (``QTableWidget.removeRow``) sind nicht gemeint."""
    muster = re.compile(r"(form|_fl|layout)\w*\.removeRow\(", re.I)
    treffer = []
    for datei in sorted((REPO / "src" / "ui").rglob("*.py")):
        text = datei.read_text(encoding="utf-8", errors="replace")
        for nr, zeile in enumerate(text.splitlines(), 1):
            if muster.search(zeile) and not zeile.lstrip().startswith("#"):
                treffer.append(f"{datei.relative_to(REPO).as_posix()}:{nr}: {zeile.strip()}")
    assert not treffer, (
        "removeRow an einem Formular-Layout loescht sofort — stattdessen die "
        "Zeile herausnehmen und die Widgets verzoegert loeschen:\n"
        + "\n".join(treffer))


# ── 3. Reproduktion: Schleife im Kindprozess ────────────────────────────────


@pytest.mark.skipif(not _ROLLE, reason="laeuft nur als Kindprozess des Schleifen-Tests")
@pytest.mark.timeout(100)
def test_arbeiter():
    """Kindprozess: echte Matrix-Ansicht (offscreen), „Bewegung“ so umstellen
    wie am Bildschirm. Endet mit Exit 0 und der Marke — oder stirbt mit dem
    Absturz, den der Elternprozess dann meldet."""
    import faulthandler
    faulthandler.enable()
    from PySide6.QtCore import QCoreApplication, QPoint, Qt
    from PySide6.QtTest import QTest
    _app()
    ansicht = _ansicht_mit_lauflicht()
    ansicht.resize(1400, 900)
    ansicht.show()
    QTest.qWait(50)
    runden = int(os.environ.get("STAB38_RUNDEN", "6"))
    folge = ("bounce", "normal", "center_out", "normal")

    for nr in range(runden * len(folge)):
        wert = folge[nr % len(folge)]
        # jedes Mal frisch nachschlagen: ein Neuaufbau ersetzt die Box
        box = ansicht._param_widgets["movement"]
        zeile = box.findData(wert)
        assert zeile >= 0, wert
        print("STELLE", nr, wert, _ROLLE, flush=True)
        if _ROLLE == "liste":
            box.showPopup()
            QTest.qWait(30)
            liste = box.view()
            mitte = liste.visualRect(liste.model().index(zeile, 0)).center()
            QTest.mouseMove(liste.viewport(), mitte)
            QTest.mouseClick(liste.viewport(), Qt.MouseButton.LeftButton,
                             Qt.KeyboardModifier.NoModifier, mitte)
        elif _ROLLE == "rad":
            from PySide6.QtGui import QWheelEvent
            box.setFocus()
            schritte = box.currentIndex() - zeile
            richtung = 1 if schritte > 0 else -1
            for _ in range(abs(schritte)):
                box = ansicht._param_widgets["movement"]
                ort = box.rect().center()
                QCoreApplication.sendEvent(box, QWheelEvent(
                    ort, box.mapToGlobal(ort), QPoint(0, 0),
                    QPoint(0, 120 * richtung), Qt.MouseButton.NoButton,
                    Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase,
                    False))
        else:
            box.setCurrentIndex(zeile)
        QTest.qWait(30)
        assert ansicht._current.params["movement"] == wert

    print(_MARKE, flush=True)
    # Bewusst hart beenden: geprueft wird die Schleife, nicht der Abbau am
    # Prozessende (eigenes Thema, eigene Tests).
    sys.stdout.flush()
    os._exit(0)


def _kind_umgebung(tmp_path, rolle: str, runden: int) -> dict:
    """Eigener Sandkasten fuer das Kind (nie die Show-DB des Elternlaufs erben)."""
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["STAB38_ARBEITER"] = rolle
    env["STAB38_RUNDEN"] = str(runden)
    env["LIGHTOS_SHOW_DB"] = str(tmp_path / "show.db")
    env["LIGHTOS_CRASH_LOG"] = str(tmp_path / "crash.log")
    daten = tmp_path / "daten"
    daten.mkdir(exist_ok=True)
    env["XDG_DATA_HOME"] = str(daten)
    env["APPDATA"] = str(daten)
    # Freigegebenen Speicher sofort ueberschreiben (glibc; anderswo wirkungslos).
    # Ohne das bleibt der Zugriff auf die geloeschte Auswahlbox meist folgenlos,
    # weil der Speicher noch die alten Werte traegt — gemessen vor dem Fix:
    # ohne 0 von 3 Laeufen abgestuerzt, mit 16 von 16 (Liste) bzw. 8 von 8 (Rad),
    # jeweils bei den ersten Umstellungen. Die Gegenprobe „index“ (Wert per
    # Programm setzen, Qt fasst die Box danach nicht mehr an) ueberlebt unter
    # derselben Einstellung — sie allein bringt also nichts zum Absturz.
    env["GLIBC_TUNABLES"] = "glibc.malloc.tcache_count=0:glibc.malloc.perturb=165"
    env.pop("LIGHTOS_UNIVERSES_JSON", None)
    env.pop("LIGHTOS_SACN_CID", None)
    env.pop("PYTEST_CURRENT_TEST", None)
    return env


def _schleife_im_kind(tmp_path, rolle: str, laeufe: int, runden: int):
    for lauf in range(1, laeufe + 1):
        ordner = tmp_path / f"lauf{lauf}"
        ordner.mkdir()
        fertig = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-x", "-s",
             "-p", "no:cacheprovider", "-o", "addopts=",
             f"tests/{Path(__file__).name}::test_arbeiter"],
            cwd=str(REPO), env=_kind_umgebung(ordner, rolle, runden),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=105)
        aus = (fertig.stdout or "") + "\n" + (fertig.stderr or "")
        schritte = len(re.findall(r"^STELLE ", aus, flags=re.M))
        assert fertig.returncode == 0 and _MARKE in aus, (
            f"Lauf {lauf} von {laeufe} ({rolle}): Kindprozess endete mit "
            f"{fertig.returncode} nach {schritte} Umstellungen — nativer Absturz "
            f"oder Fehler:\n{aus[-3000:]}")


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
@pytest.mark.timeout(115)
def test_bewegung_ueber_die_aufklappliste_stuerzt_nicht_ab(tmp_path):
    """Wie am Bildschirm: Aufklappliste oeffnen, Eintrag anklicken."""
    _schleife_im_kind(tmp_path, "liste", laeufe=2, runden=6)


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
@pytest.mark.timeout(115)
def test_bewegung_ueber_das_mausrad_stuerzt_nicht_ab(tmp_path):
    """Mausrad ueber der geschlossenen Auswahlbox."""
    _schleife_im_kind(tmp_path, "rad", laeufe=2, runden=6)
