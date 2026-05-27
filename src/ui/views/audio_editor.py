"""Audio Editor — Editor fuer AudioFunction."""
from __future__ import annotations
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QPushButton, QLabel, QFileDialog, QSlider, QCheckBox, QDoubleSpinBox,
    QGroupBox,
)
from PySide6.QtCore import Qt
from src.core.engine.audio_func import AudioFunction


class AudioEditor(QWidget):
    """Audio Function Editor."""

    def __init__(self, audio: AudioFunction, parent=None):
        super().__init__(parent)
        self._audio = audio
        self._setup_ui()
        self._refresh()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        title = QLabel(f"Audio: {self._audio.name}")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #58a6ff;")
        root.addWidget(title)

        # File selection
        file_box = QGroupBox("Audio-Datei")
        file_layout = QVBoxLayout(file_box)
        row = QHBoxLayout()
        self._edit_path = QLineEdit(self._audio.file_path)
        self._edit_path.editingFinished.connect(self._on_path_changed)
        row.addWidget(self._edit_path, 1)
        btn_browse = QPushButton("Durchsuchen...")
        btn_browse.clicked.connect(self._browse)
        row.addWidget(btn_browse)
        file_layout.addLayout(row)
        self._lbl_status = QLabel()
        self._lbl_status.setStyleSheet("color: #888888; font-size: 10px;")
        file_layout.addWidget(self._lbl_status)
        root.addWidget(file_box)

        # Settings
        cfg_box = QGroupBox("Einstellungen")
        cfg_form = QFormLayout(cfg_box)

        # Name
        self._edit_name = QLineEdit(self._audio.name)
        self._edit_name.editingFinished.connect(self._on_name_changed)
        cfg_form.addRow("Name:", self._edit_name)

        # Volume
        vol_row = QHBoxLayout()
        self._slider_vol = QSlider(Qt.Orientation.Horizontal)
        self._slider_vol.setRange(0, 100)
        self._slider_vol.setValue(int(self._audio.volume * 100))
        self._slider_vol.valueChanged.connect(self._on_vol_changed)
        self._lbl_vol = QLabel(f"{int(self._audio.volume * 100)}%")
        self._lbl_vol.setMinimumWidth(40)
        vol_row.addWidget(self._slider_vol)
        vol_row.addWidget(self._lbl_vol)
        cfg_form.addRow("Lautstaerke:", vol_row)

        # Loop
        self._chk_loop = QCheckBox("Endlos wiederholen")
        self._chk_loop.setChecked(self._audio.loop)
        self._chk_loop.toggled.connect(self._on_loop_changed)
        cfg_form.addRow(self._chk_loop)

        # Fades
        self._spin_fadein = QDoubleSpinBox()
        self._spin_fadein.setRange(0.0, 60.0)
        self._spin_fadein.setSingleStep(0.1)
        self._spin_fadein.setSuffix(" s")
        self._spin_fadein.setValue(self._audio.fade_in)
        self._spin_fadein.valueChanged.connect(self._on_fadein_changed)
        cfg_form.addRow("Fade In:", self._spin_fadein)

        self._spin_fadeout = QDoubleSpinBox()
        self._spin_fadeout.setRange(0.0, 60.0)
        self._spin_fadeout.setSingleStep(0.1)
        self._spin_fadeout.setSuffix(" s")
        self._spin_fadeout.setValue(self._audio.fade_out)
        self._spin_fadeout.valueChanged.connect(self._on_fadeout_changed)
        cfg_form.addRow("Fade Out:", self._spin_fadeout)

        root.addWidget(cfg_box)

        # Transport
        btn_row = QHBoxLayout()
        btn_play = QPushButton("Play")
        btn_play.clicked.connect(self._play)
        btn_stop = QPushButton("Stop")
        btn_stop.clicked.connect(self._stop)
        btn_row.addWidget(btn_play)
        btn_row.addWidget(btn_stop)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        root.addStretch(1)

    def _refresh(self):
        if self._audio.file_path and os.path.exists(self._audio.file_path):
            size = os.path.getsize(self._audio.file_path) // 1024
            self._lbl_status.setText(f"OK ({size} KB)")
            self._lbl_status.setStyleSheet("color: #9DFF52; font-size: 10px;")
        elif self._audio.file_path:
            self._lbl_status.setText(f"Datei nicht gefunden: {self._audio.file_path}")
            self._lbl_status.setStyleSheet("color: #ff4444; font-size: 10px;")
        else:
            self._lbl_status.setText("Keine Datei ausgewaehlt")
            self._lbl_status.setStyleSheet("color: #888888; font-size: 10px;")
        if not self._audio._available:
            self._lbl_status.setText(self._lbl_status.text() +
                                     " (PySide6.QtMultimedia fehlt - Audio deaktiviert)")

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Audio-Datei auswaehlen", "",
            "Audio (*.mp3 *.wav *.ogg *.flac *.m4a *.aac);;Alle Dateien (*)"
        )
        if path:
            self._audio.file_path = path
            self._edit_path.setText(path)
            self._refresh()

    def _on_path_changed(self):
        self._audio.file_path = self._edit_path.text()
        self._refresh()

    def _on_name_changed(self):
        n = self._edit_name.text().strip()
        if n:
            self._audio.name = n
            try:
                from src.core.sync import get_sync, SyncEvent
                get_sync().emit(SyncEvent.FUNCTION_CHANGED, None)
            except Exception:
                pass

    def _on_vol_changed(self, v: int):
        self._audio.volume = v / 100.0
        self._lbl_vol.setText(f"{v}%")
        if self._audio._audio_out is not None:
            try:
                self._audio._audio_out.setVolume(self._audio.volume)
            except Exception:
                pass

    def _on_loop_changed(self, checked: bool):
        self._audio.loop = checked

    def _on_fadein_changed(self, v: float):
        self._audio.fade_in = v

    def _on_fadeout_changed(self, v: float):
        self._audio.fade_out = v

    def _play(self):
        try:
            from src.core.engine.function_manager import get_function_manager
            get_function_manager().start(self._audio.id)
        except Exception as e:
            print(f"[AudioEditor] play error: {e}")

    def _stop(self):
        try:
            from src.core.engine.function_manager import get_function_manager
            get_function_manager().stop(self._audio.id)
        except Exception as e:
            print(f"[AudioEditor] stop error: {e}")
