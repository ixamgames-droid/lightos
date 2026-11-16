"""VIZ-56 Teil 2: „MVR-Datei exportieren …“ — Dateidialog und Meldung.

Gerechnet wird in ``src.core.mvr.schreiben``; hier stehen nur Dateiwahl,
Wartecursor und die Meldung danach (Anzahl Geraete, welche ohne Position am
Ursprung stehen, welche ohne Bibliotheksprofil exportiert wurden).
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from src.core.mvr.schreiben import ExportErgebnis, schreibe_mvr
from src.core.mvr.sicher import MvrFehler

TITEL = "MVR-Datei exportieren"
DATEI_FILTER = "My Virtual Rig (*.mvr);;Alle Dateien (*)"
#: So viele Namen nennt die Meldung, danach „und n weitere“.
NAMEN_MAX = 8


def _namen(namen: list[str]) -> str:
    teile = ", ".join(f"„{n}“" for n in namen[:NAMEN_MAX])
    if len(namen) > NAMEN_MAX:
        teile += f" und {len(namen) - NAMEN_MAX} weitere"
    return teile


def meldung_nach_export(e: ExportErgebnis) -> str:
    n = e.geraete
    zeilen = [("1 Gerät" if n == 1 else f"{n} Geräte")
              + f" nach „{os.path.basename(e.pfad)}“ exportiert"
              + (f" (mit {len(e.gdtf)} Gerätetyp{'en' if len(e.gdtf) != 1 else ''} als GDTF)."
                 if e.gdtf else ".")]
    if e.ohne_position:
        zeilen.append("Ohne Position im 3D, deshalb am Ursprung (0, 0, 0): "
                      + _namen(e.ohne_position) + ".")
    if e.ohne_profil:
        zeilen.append("Ohne Bibliotheksprofil, nur mit Kanalzahl exportiert: "
                      + _namen(e.ohne_profil) + ".")
    return "\n\n".join(zeilen)


def exportieren_starten(parent, state, pfad: str | None = None) -> ExportErgebnis | None:
    """Datei waehlen -> schreiben -> Meldung. ``None`` bei Abbruch/Fehler."""
    if not state.get_patched_fixtures():
        QMessageBox.information(parent, TITEL, "Im Patch steht kein Gerät — "
                                "es gibt nichts zu exportieren.")
        return None
    if pfad is None:
        pfad, _ = QFileDialog.getSaveFileName(parent, TITEL, "rig.mvr", DATEI_FILTER)
        if not pfad:
            return None
        if not os.path.splitext(pfad)[1]:
            pfad += ".mvr"
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        ergebnis, fehler = schreibe_mvr(state, pfad), ""
    except MvrFehler as e:
        ergebnis, fehler = None, str(e)
    finally:
        QApplication.restoreOverrideCursor()
    if ergebnis is None:
        QMessageBox.warning(parent, TITEL, f"Die Datei „{os.path.basename(pfad)}“ "
                            f"wurde nicht geschrieben.\n\n{fehler}")
        return None
    QMessageBox.information(parent, TITEL, meldung_nach_export(ergebnis))
    return ergebnis
