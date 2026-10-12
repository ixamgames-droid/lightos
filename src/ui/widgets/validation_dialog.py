"""Validation Report Dialog - zeigt alle Probleme beim Show-Laden."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget, QPushButton,
    QDialogButtonBox, QListWidgetItem,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush


class ValidationDialog(QDialog):
    """Modal-Dialog zur Anzeige der ValidationIssue-Liste."""

    def __init__(self, issues: list, parent=None, reparieren=None):
        """``reparieren`` (VCB-44): eine Funktion, die die Reparatur ausfuehrt
        und die neue Befundliste liefert. Gibt es sie und ist etwas reparierbar,
        bietet der Dialog „Reparieren“ an — bis dahin ist nichts veraendert."""
        super().__init__(parent)
        self.setWindowTitle("Show-Validierung")
        self.setMinimumSize(600, 400)
        self._reparieren = reparieren
        self.repariert = False
        self._setup_ui(issues or [])

    def _setup_ui(self, issues: list):
        self._fuelle(QVBoxLayout(self), issues)

    def _fuelle(self, layout, issues: list):
        if not issues:
            lbl = QLabel("Show ist sauber - keine Probleme gefunden.")
            lbl.setStyleSheet("color: #9DFF52; font-weight: bold; padding: 12px;")
            layout.addWidget(lbl)
        else:
            errors = [i for i in issues if getattr(i, "severity", "") == 'error']
            warns = [i for i in issues if getattr(i, "severity", "") == 'warn']
            fixed = [i for i in issues if getattr(i, "auto_fixed", False)]
            # CDX-58: Hinweise (Schwere 'info', nicht behoben) mitzaehlen —
            # sonst stuende ueber einer Liste mit einem Eintrag „0 · 0 · 0".
            hints = [i for i in issues if getattr(i, "severity", "") == 'info'
                     and not getattr(i, "auto_fixed", False)]

            summary = QLabel(
                f"<b>{len(errors)} Fehler</b> &middot; "
                f"<b>{len(warns)} Warnungen</b> &middot; "
                f"<b>{len(hints)} Hinweise</b> &middot; "
                f"<b>{len(fixed)} automatisch behoben</b>"
            )
            summary.setStyleSheet("padding: 6px; font-size: 13px;")
            layout.addWidget(summary)

            self._list = QListWidget()
            for issue in issues:
                item = QListWidgetItem(str(issue))
                sev = getattr(issue, "severity", "")
                auto_fixed = getattr(issue, "auto_fixed", False)
                if sev == 'error':
                    item.setForeground(QBrush(QColor("#ff4444")))
                elif sev == 'warn':
                    item.setForeground(QBrush(QColor("#ffaa00")))
                elif auto_fixed:
                    item.setForeground(QBrush(QColor("#88ff88")))
                self._list.addItem(item)
            layout.addWidget(self._list)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        # VCB-44: erst zeigen, dann — auf Wunsch — reparieren. Bis hierhin
        # reparierte „Show prüfen“ ohne Rückfrage, noch bevor der Dialog
        # erschien (entfernte also Werte aus Cues und Szenen ungefragt).
        offen = [i for i in issues if getattr(i, "reparierbar", False)]
        self._btn_reparieren = None
        if offen and callable(self._reparieren):
            hinweis = QLabel(
                f"{len(offen)} davon lassen sich automatisch beheben. "
                "Es ist noch nichts verändert.")
            hinweis.setWordWrap(True)
            hinweis.setStyleSheet("color: #b0b6c0; padding: 4px 6px;")
            layout.addWidget(hinweis)
            self._btn_reparieren = btns.addButton(
                f"Reparieren ({len(offen)})", QDialogButtonBox.ButtonRole.ActionRole)
            self._btn_reparieren.clicked.connect(self._reparieren_geklickt)
        layout.addWidget(btns)

    def _reparieren_geklickt(self):
        """Reparatur ausfuehren und das Ergebnis im selben Dialog zeigen."""
        try:
            neu = self._reparieren()
        except Exception as e:                           # noqa: BLE001
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Reparatur", f"Fehler: {e}")
            return
        self.repariert = True
        self._reparieren = None
        alt = self.layout()
        while alt.count():
            item = alt.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        # Das alte Layout bleibt das Layout des Dialogs — neu befuellen.
        self._fuelle(alt, list(neu or []))
