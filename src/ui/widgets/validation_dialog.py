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

    def __init__(self, issues: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Show-Validierung")
        self.setMinimumSize(600, 400)
        self._setup_ui(issues or [])

    def _setup_ui(self, issues: list):
        layout = QVBoxLayout(self)

        if not issues:
            lbl = QLabel("Show ist sauber - keine Probleme gefunden.")
            lbl.setStyleSheet("color: #9DFF52; font-weight: bold; padding: 12px;")
            layout.addWidget(lbl)
        else:
            errors = [i for i in issues if getattr(i, "severity", "") == 'error']
            warns = [i for i in issues if getattr(i, "severity", "") == 'warn']
            fixed = [i for i in issues if getattr(i, "auto_fixed", False)]

            summary = QLabel(
                f"<b>{len(errors)} Fehler</b> &middot; "
                f"<b>{len(warns)} Warnungen</b> &middot; "
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
        layout.addWidget(btns)
