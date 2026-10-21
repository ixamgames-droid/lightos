"""Umbrechendes Flow-Layout.

Widgets fließen von links nach rechts und brechen bei Platzmangel in die
nächste Zeile um — statt (wie bei einem ``QHBoxLayout``) unter ihre
Wunschbreite zusammengequetscht zu werden, was den Text abschneidet.

Genutzt z. B. für die Virtual-Console-Toolbar: bei 200 %-Display-Skalierung
oder schmalem Fenster passen im Bearbeiten-Modus nicht alle Buttons in eine
Zeile. Das FlowLayout bricht dann sauber um; passt alles in eine Zeile, bleibt
es einzeilig. Versteckte Widgets (``isHidden()``) werden übersprungen, damit im
Live-Modus keine Lücken entstehen, wo nur im Bearbeiten-Modus sichtbare Buttons
liegen.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QWidget


class FlowLayout(QLayout):
    def __init__(
        self,
        parent: QWidget | None = None,
        margin: int = 0,
        h_spacing: int = 6,
        v_spacing: int = 4,
        zeilen_zentrieren: bool = False,
    ) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._h_space = h_spacing
        self._v_space = v_spacing
        # UI-98: Elemente unterschiedlicher Höhe innerhalb ihrer Zeile
        # senkrecht mittig ausrichten (sonst oben bündig).
        self._zentrieren = zeilen_zentrieren
        # UI-104: zuletzt gemeldete Höhe für die aktuelle Breite (s. minimumSize).
        self._hfw_gemeldet = -1
        self.setContentsMargins(margin, margin, margin, margin)

    # ── Pflicht-Overrides ────────────────────────────────────────────────────
    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802
        return Qt.Orientation(0)

    def horizontalSpacing(self) -> int:  # noqa: N802
        return self._h_space

    def verticalSpacing(self) -> int:  # noqa: N802
        return self._v_space

    # ── Height-for-width ─────────────────────────────────────────────────────
    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        hoehe = self._do_layout(rect, test_only=False)
        if hoehe != self._hfw_gemeldet:
            # UI-104: Zeilenzahl hat sich mit der Breite geändert -> die
            # Mindesthöhe (minimumSize) auch; Eltern-Layouts neu fragen lassen.
            # Die Breite hängt nicht von der Höhe ab, das konvergiert.
            self._hfw_gemeldet = hoehe
            self.invalidate()

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            w = item.widget()
            if w is not None and w.isHidden():
                continue
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(
            margins.left() + margins.right(),
            margins.top() + margins.bottom(),
        )
        # UI-104: Bei bekannter Breite die umbrochene Höhe als Mindesthöhe
        # melden. Nur der größte Einzelknopf reichte nicht: jenseits eines
        # QSplitter fragt niemand heightForWidth, das Eltern-Layout stauchte
        # die Leiste bei Platzmangel unter ihre Zeilenhöhe (Touch-Modus,
        # schmale Bibliothek: „↻“ als Strich, „Löschen“ im Baum).
        breite = self.geometry().width()
        if breite > 0:
            size.setHeight(max(size.height(), self.heightForWidth(breite)))
        return size

    # ── Layout-Kern ──────────────────────────────────────────────────────────
    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(
            margins.left(), margins.top(), -margins.right(), -margins.bottom()
        )
        x = effective.x()
        y = effective.y()
        line_height = 0
        zeile: list[tuple[QLayoutItem, QPoint, QSize]] = []

        def _zeile_setzen() -> None:
            for it, pos, hint in zeile:
                dy = (line_height - hint.height()) // 2 if self._zentrieren else 0
                it.setGeometry(QRect(pos + QPoint(0, dy), hint))
            zeile.clear()

        for item in self._items:
            w = item.widget()
            if w is not None and w.isHidden():
                continue
            hint = item.sizeHint()
            next_x = x + hint.width() + self._h_space
            if next_x - self._h_space > effective.right() and line_height > 0:
                # In die nächste Zeile umbrechen.
                if not test_only:
                    _zeile_setzen()
                x = effective.x()
                y = y + line_height + self._v_space
                next_x = x + hint.width() + self._h_space
                line_height = 0
            if not test_only:
                zeile.append((item, QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())

        if not test_only:
            _zeile_setzen()
        return y + line_height - rect.y() + margins.bottom()
