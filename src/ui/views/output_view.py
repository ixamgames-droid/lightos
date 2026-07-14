"""Output-Monitor — zeigt DMX-Kanalwerte in Echtzeit."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QGridLayout, QScrollArea, QPushButton
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QFont
from src.core.app_state import get_state


class DMXChannelCell(QWidget):
    """Einzelne Zelle für einen DMX-Kanal."""
    def __init__(self, channel: int, parent=None):
        super().__init__(parent)
        self.channel = channel
        self._value = 0
        self.setFixedSize(44, 44)
        self.setToolTip(f"Kanal {channel}")

    def set_value(self, value: int):
        if value != self._value:
            self._value = value
            self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        val = self._value
        # Helligkeit als Hintergrundfarbe
        brightness = int(val * 0.8)
        if val > 0:
            bg = QColor(brightness // 3, brightness // 3, brightness)
        else:
            bg = QColor(20, 20, 25)
        p.fillRect(0, 0, 44, 44, bg)

        # Kanalwert
        text_color = QColor("#ffffff") if val > 100 else QColor("#888")
        p.setPen(text_color)
        font = QFont("Courier New", 9)
        font.setBold(val > 0)
        p.setFont(font)
        p.drawText(0, 0, 44, 28, Qt.AlignmentFlag.AlignCenter, str(val))

        # Kanal-Nummer klein
        p.setPen(QColor("#555"))
        small = QFont("Segoe UI", 7)
        p.setFont(small)
        p.drawText(0, 28, 44, 16, Qt.AlignmentFlag.AlignCenter, str(self.channel))
        p.end()


class OutputView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = get_state()
        self._cells: dict[int, list[DMXChannelCell]] = {}
        self._setup_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(100)  # 10 Hz Anzeige-Update

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Controls
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Universe:"))
        self._spin_univ = QSpinBox()
        # Der Patch und die Output-Konfiguration unterstützen Universen 1–32.
        # Ein 1–16-Limit machte gepatchte Geräte auf U17–U32 im Monitor unsichtbar.
        self._spin_univ.setRange(1, 32)
        self._spin_univ.valueChanged.connect(self._rebuild_grid)
        ctrl.addWidget(self._spin_univ)
        ctrl.addStretch()
        lbl_info = QLabel("Kanal-Werte in Echtzeit (0–255)")
        lbl_info.setStyleSheet("color: #888;")
        ctrl.addWidget(lbl_info)
        layout.addLayout(ctrl)

        # Scrollbarer Kanal-Grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._grid_widget = QWidget()
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setSpacing(2)
        scroll.setWidget(self._grid_widget)
        layout.addWidget(scroll)

        self._rebuild_grid(1)

    def _rebuild_grid(self, universe: int):
        # Alte Cells entfernen
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._cells = {}
        cells = []
        for ch in range(1, 513):
            cell = DMXChannelCell(ch, self._grid_widget)
            row = (ch - 1) // 16
            col = (ch - 1) % 16
            self._grid_layout.addWidget(cell, row, col)
            cells.append(cell)
        self._cells[universe] = cells

    def _refresh(self):
        univ_num = self._spin_univ.value()
        if univ_num not in self._state.universes:
            return
        universe = self._state.universes[univ_num]
        # WYSIWYG: den GESENDETEN Output zeigen (POST Grand-Master/Blackout).
        # Fallback auf den Rohpuffer, solange noch kein Frame gesendet wurde.
        data = None
        om = getattr(self._state, "output_manager", None)
        if om is not None:
            data = om.get_display_frame(univ_num)
        if data is None:
            data = universe.get_all()
        cells = self._cells.get(univ_num, [])
        for i, cell in enumerate(cells):
            cell.set_value(data[i])
