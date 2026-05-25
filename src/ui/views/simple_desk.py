"""Simple Desk — 512 direct DMX faders per universe."""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
                                QLabel, QSpinBox, QComboBox, QPushButton,
                                QSizePolicy, QGridLayout, QSlider)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QFont


class ChannelFader(QWidget):
    """Single vertical fader for one DMX channel."""
    def __init__(self, channel: int, parent=None):
        super().__init__(parent)
        self.channel = channel
        self._value = 0
        self.setFixedSize(36, 110)
        self.setToolTip(f"CH {channel}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(1)

        self._val_lbl = QLabel("0")
        self._val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._val_lbl.setStyleSheet("color:#8b949e; font-size:8px;")
        layout.addWidget(self._val_lbl)

        self._slider = QSlider(Qt.Orientation.Vertical)
        self._slider.setRange(0, 255)
        self._slider.setValue(0)
        self._slider.setStyleSheet("""
            QSlider::groove:vertical { background:#21262d; width:8px; border-radius:4px; }
            QSlider::handle:vertical { background:#58a6ff; height:12px; width:12px;
                                       margin:-2px -2px; border-radius:6px; }
            QSlider::sub-page:vertical { background:#1f6feb; border-radius:4px; }
        """)
        self._slider.valueChanged.connect(self._on_change)
        layout.addWidget(self._slider)

        self._ch_lbl = QLabel(str(channel))
        self._ch_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ch_lbl.setStyleSheet("color:#484f58; font-size:7px;")
        layout.addWidget(self._ch_lbl)

    def _on_change(self, val: int):
        self._value = val
        self._val_lbl.setText(str(val))
        self.value_changed(val)

    def value_changed(self, val: int):
        pass  # to be monkey-patched by parent

    def set_value_silent(self, val: int):
        self._slider.blockSignals(True)
        self._slider.setValue(val)
        self._value = val
        self._val_lbl.setText(str(val))
        self._slider.blockSignals(False)


class SimpleDeskView(QWidget):
    """Direct 1:1 DMX channel faders (512 per universe)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._universe = 1   # 1-based DMX universe number
        self._faders: list[ChannelFader] = []
        self._user_active_until: dict[int, float] = {}  # {channel: timestamp}
        self._setup_ui()

        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self._sync_from_output)
        self._sync_timer.start(200)

        # Zentraler StateSync
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            sync.subscribe(SyncEvent.REFRESH_ALL, lambda *_: self._sync_from_output())
            sync.subscribe(SyncEvent.PATCH_CHANGED, lambda *_: self._sync_from_output())
            sync.subscribe(SyncEvent.DMX_CHANGED, lambda *_: self._sync_from_output())
        except Exception as e:
            print(f"[simple_desk] sync subscribe error: {e}")

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header
        header = QHBoxLayout()
        header.addWidget(QLabel("Universe:"))
        self._uni_combo = QComboBox()
        self._uni_combo.addItems(["Universe 1", "Universe 2", "Universe 3", "Universe 4"])
        self._uni_combo.currentIndexChanged.connect(self._universe_changed)
        self._uni_combo.setFixedWidth(120)
        header.addWidget(self._uni_combo)
        header.addSpacing(20)

        btn_all_zero = QPushButton("Alles auf 0")
        btn_all_zero.setFixedHeight(24)
        btn_all_zero.clicked.connect(self._zero_all)
        btn_all_zero.setStyleSheet("""
            QPushButton { background:#21262d; color:#f85149; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:hover { background:#30363d; }
        """)
        header.addWidget(btn_all_zero)

        btn_full = QPushButton("Alles auf 255")
        btn_full.setFixedHeight(24)
        btn_full.clicked.connect(lambda: self._set_all(255))
        btn_full.setStyleSheet(btn_all_zero.styleSheet().replace("#f85149", "#3fb950"))
        header.addWidget(btn_full)

        header.addStretch()
        layout.addLayout(header)

        # Fader grid in scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border:none; background:#0d1117; }")

        fader_widget = QWidget()
        fader_widget.setStyleSheet("background:#0d1117;")
        grid = QHBoxLayout(fader_widget)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setSpacing(2)
        grid.setAlignment(Qt.AlignmentFlag.AlignLeft)

        for ch in range(1, 513):
            f = ChannelFader(ch)
            f.value_changed = lambda val, c=ch: self._on_fader_change(c, val)
            grid.addWidget(f)
            self._faders.append(f)

        scroll.setWidget(fader_widget)
        layout.addWidget(scroll)

    def _on_fader_change(self, channel: int, value: int):
        import time
        # User aktiv -> 800ms lang nicht vom Sync ueberschreiben
        self._user_active_until[channel] = time.monotonic() + 0.8
        try:
            from src.core.app_state import get_state
            state = get_state()
            # Sicherstellen dass das Universe existiert
            if self._universe not in state.universes:
                state.universes[self._universe] = state.output_manager.add_universe(self._universe)
            state.universes[self._universe].set_channel(channel, value)
        except Exception as e:
            print(f"[SimpleDesk] fader change error: {e}")

    def _universe_changed(self, idx: int):
        # Combobox-Index (0-based) -> Universe-Nummer (1-based)
        self._universe = idx + 1
        self._user_active_until.clear()
        self._sync_from_output()

    def _zero_all(self):
        self._set_all(0)

    def _set_all(self, val: int):
        import time
        try:
            from src.core.app_state import get_state
            state = get_state()
            if self._universe not in state.universes:
                state.universes[self._universe] = state.output_manager.add_universe(self._universe)
            u = state.universes[self._universe]
            now = time.monotonic() + 0.8
            for ch in range(1, 513):
                u.set_channel(ch, val)
                self._user_active_until[ch] = now
        except Exception as e:
            print(f"[SimpleDesk] set_all error: {e}")
        for f in self._faders:
            f.set_value_silent(val)

    def _sync_from_output(self):
        import time
        try:
            from src.core.app_state import get_state
            state = get_state()
            u = state.universes.get(self._universe)
            if u is None:
                return
            data = u.get_all()
            now = time.monotonic()
            for i, f in enumerate(self._faders):
                if i >= len(data):
                    continue
                ch = i + 1
                # User-Bewegung kuerzlich -> nicht ueberschreiben
                if self._user_active_until.get(ch, 0) > now:
                    continue
                f.set_value_silent(data[i])
        except Exception as e:
            print(f"[SimpleDesk] sync error: {e}")
