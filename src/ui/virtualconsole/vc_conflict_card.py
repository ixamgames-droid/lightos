"""VCConflictCard — kleine Erklaer-Karte beim Drop auf einen schon belegten Regler.

Loest den frueher STUMMEN Fall ab, in dem ein zweiter Effekt einfach ans selbe
Speed-Widget gekoppelt wurde. Die Karte erklaert kurz, was der Regler schon
steuert, und bietet drei klare Wege:
  * „Ersetzen"      -> Regler steuert nur noch den neuen Effekt  (resolution="replace")
  * „Dazu koppeln"  -> beide Effekte am selben Regler (Gruppe)   (resolution="couple")
  * „Neues Widget"  -> eigenes Bedien-Element daneben anlegen     (resolution="new")
Abbrechen = None.

Reine Praesentation; die eigentliche Bindungs-Logik bleibt in
``VCCanvas._resolve_coupling_conflict``.
"""
from __future__ import annotations

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPushButton,
                               QDialogButtonBox)
from PySide6.QtCore import Qt


_CHOICES = (
    ("replace", "Ersetzen",
     "Der Regler steuert dann NUR noch den neuen Effekt."),
    ("couple", "Dazu koppeln",
     "Beide Effekte hängen am selben Regler (eine Gruppe, ein Tempo)."),
    ("new", "Neues Widget daneben",
     "Lässt den Regler in Ruhe und legt ein eigenes Bedien-Element an."),
)


class VCConflictCard(QDialog):
    """Fragt, was beim Drop auf einen bereits gebundenen Regler passieren soll."""

    def __init__(self, effect_name: str, owners=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Regler ist schon belegt")
        self.setMinimumWidth(320)
        self._resolution: "str | None" = None

        who = ", ".join([o for o in (owners or []) if o]) or "einen anderen Effekt"
        v = QVBoxLayout(self)
        head = QLabel(f"Dieser Regler steuert schon <b>{who}</b>.<br>"
                      f"Was soll mit „{effect_name}“ passieren?")
        head.setTextFormat(Qt.TextFormat.RichText)
        head.setWordWrap(True)
        v.addWidget(head)

        for key, label, tip in _CHOICES:
            b = QPushButton(label)
            b.setToolTip(tip)
            b.setMinimumHeight(34)
            b.clicked.connect(lambda _checked=False, k=key: self._choose(k))
            v.addWidget(b)
            sub = QLabel(tip)
            sub.setWordWrap(True)
            sub.setStyleSheet("color:#8b949e; font-size:11px; margin:0 0 6px 4px;")
            v.addWidget(sub)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        box.rejected.connect(self.reject)
        v.addWidget(box)

    def _choose(self, key: str):
        self._resolution = key
        self.accept()

    def resolution(self) -> "str | None":
        return self._resolution

    def run(self) -> "str | None":
        if self.exec() == QDialog.DialogCode.Accepted:
            return self._resolution
        return None
