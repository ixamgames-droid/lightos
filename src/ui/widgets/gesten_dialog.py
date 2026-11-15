"""UI-83: Uebersicht der Touch-Gesten mit Schaltern (Ansicht → Touch-Gesten…).

Zeigt jede Finger-Geste mit kurzer Erklaerung und einem Schalter zum
Abschalten, dazu die Auswahl fuer das Drei-Finger-Tippen (Vorgabe: aus; die
Liste enthaelt nie eine Sicherheitsaktion). „Übernehmen" gilt sofort fuer den
Anwendungsfilter (``ziehen_scrollen``) und wird in ``ui_prefs.json``
gespeichert. Die Maus ist von keinem Schalter betroffen.
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from src.ui import gesten_prefs


def _ist_windows() -> bool:
    return sys.platform == "win32"


class GestenDialog(QDialog):
    def __init__(self, parent=None, pfad: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Touch-Gesten")
        self.setObjectName("gesten_dialog")
        self._pfad = pfad
        self._filter = getattr(QApplication.instance(), "_ui110_ziehen_scrollen", None)
        if self._filter is not None:
            stand = gesten_prefs.GestenSchalter.aus_dict(self._filter.gesten.als_dict())
        else:
            stand = gesten_prefs.laden(pfad)

        lay = QVBoxLayout(self)
        kopf = QLabel(
            "Gesten am Touchscreen. Jede lässt sich hier abschalten; die Maus "
            "bleibt davon unberührt.")
        kopf.setWordWrap(True)
        lay.addWidget(kopf)

        inhalt = QWidget()
        il = QVBoxLayout(inhalt)
        self.schalter: dict[str, QCheckBox] = {}
        for key, titel, text in gesten_prefs.UEBERSICHT:
            cb = QCheckBox(titel)
            cb.setObjectName(f"geste_{key}")
            cb.setChecked(bool(getattr(stand, key)))
            cb.setToolTip(text)
            il.addWidget(cb)
            erkl = QLabel(text)
            erkl.setWordWrap(True)
            erkl.setStyleSheet("color:#8b949e; margin-left:24px;")
            il.addWidget(erkl)
            self.schalter[key] = cb

        form = QFormLayout()
        self.drei = QComboBox()
        self.drei.setObjectName("geste_drei_finger")
        for wert, text in gesten_prefs.DREI_FINGER_AKTIONEN:
            self.drei.addItem(text, wert)
        i = self.drei.findData(stand.drei_finger)
        self.drei.setCurrentIndex(max(0, i))
        form.addRow("Drei Finger tippen:", self.drei)
        il.addLayout(form)
        hinweis = QLabel(
            "Drei Finger gleichzeitig kurz antippen (nicht auf Knöpfen, Fadern "
            "oder Feldern). Sicherheitsaktionen wie BLACKOUT oder STOP ALL "
            "lassen sich bewusst nicht auf eine Geste legen.")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet("color:#8b949e;")
        il.addWidget(hinweis)
        if _ist_windows():
            # UI-134: unter Windows 11 kommt das Drei-Finger-TIPPEN nie an
            # (Systemgeste), Ziehen mit drei Fingern schon (B, 15.11.2026).
            self.windows_hinweis = QLabel(
                "Windows: Das Tippen mit drei Fingern nutzt Windows selbst als "
                "Systemgeste – es kommt dann nicht bei LightOS an. Abhilfe: in den "
                "Windows-Einstellungen (Bluetooth und Geräte → Toucheingabe) die "
                "Drei- und Vier-Finger-Gesten ausschalten. LightOS ändert diese "
                "Einstellung nicht selbst.")
            self.windows_hinweis.setObjectName("gesten_windows_hinweis")
            self.windows_hinweis.setWordWrap(True)
            self.windows_hinweis.setStyleSheet("color:#d29922;")
            il.addWidget(self.windows_hinweis)
        il.addStretch(1)

        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(inhalt)
        lay.addWidget(sc, 1)

        knoepfe = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        knoepfe.button(QDialogButtonBox.StandardButton.Ok).setText("Übernehmen")
        knoepfe.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        knoepfe.accepted.connect(self.uebernehmen)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.resize(520, 560)

    def stand(self) -> gesten_prefs.GestenSchalter:
        s = gesten_prefs.GestenSchalter()
        for key, cb in self.schalter.items():
            setattr(s, key, cb.isChecked())
        wert = self.drei.currentData()
        s.drei_finger = wert if wert in gesten_prefs.DREI_FINGER_WERTE else "aus"
        return s

    def uebernehmen(self) -> None:
        s = self.stand()
        if self._filter is not None:
            self._filter.gesten = s
        gesten_prefs.speichern(s, self._pfad)
        self.accept()
