"""Audio Editor — Editor fuer AudioFunction."""
from __future__ import annotations
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QPushButton, QLabel, QFileDialog, QSlider, QCheckBox, QDoubleSpinBox,
    QGroupBox, QScrollArea, QDialog,
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
        # --- top-level layout on self ---
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addStretch(1)
        self._btn_editor_popout = QPushButton("⤢ Großes Fenster")
        self._btn_editor_popout.setFixedHeight(24)
        self._btn_editor_popout.setToolTip(
            "Den ganzen Editor in einem großen, scrollbaren Fenster bearbeiten")
        self._btn_editor_popout.setStyleSheet(
            "QPushButton{background:#21262d;color:#e6edf3;border:1px solid #30363d;"
            "border-radius:3px;font-size:10px;padding:1px 8px;} "
            "QPushButton:hover{background:#30363d;}")
        self._btn_editor_popout.clicked.connect(self._toggle_editor_popout)
        header.addWidget(self._btn_editor_popout)
        outer.addLayout(header)

        # --- editor body: ALL existing content goes here ---
        self._editor_body = QWidget()
        root = QVBoxLayout(self._editor_body)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(6)

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
        cfg_form.addRow("Lautstärke:", vol_row)

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

        # --- outer scroll area holds the editor body ---
        self._editor_window = None
        self._editor_window_scroll = None
        self._editor_scroll = QScrollArea()
        self._editor_scroll.setWidgetResizable(True)
        self._editor_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._editor_scroll.setWidget(self._editor_body)
        self._editor_scroll.setStyleSheet("QScrollArea{border:none;}")
        outer.addWidget(self._editor_scroll, 1)

        self._editor_placeholder = QLabel(
            "⤢ Der Editor ist in einem eigenen großen Fenster geöffnet.\n\n"
            "Zum Andocken das Fenster schließen oder erneut auf »Großes Fenster« tippen.")
        self._editor_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._editor_placeholder.setWordWrap(True)
        self._editor_placeholder.setStyleSheet("color:#8b949e; font-size:11px; padding:24px;")
        self._editor_placeholder.setVisible(False)
        outer.addWidget(self._editor_placeholder, 1)

    def _toggle_editor_popout(self):
        """Koppelt den GANZEN Audio-Editor in ein grosses, scrollbares Fenster
        aus / dockt ihn zurueck."""
        if self._editor_window is not None:
            self._editor_window.close()      # → finished → _redock_editor
            return
        body = self._editor_scroll.takeWidget()
        if body is None:
            return
        win = QDialog(self)
        win.setWindowTitle("Audio-Editor")
        win.setModal(False)
        wl = QVBoxLayout(win)
        wl.setContentsMargins(6, 6, 6, 6)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QScrollArea.Shape.NoFrame)
        sc.setWidget(body)
        sc.setStyleSheet("QScrollArea{border:none;}")
        wl.addWidget(sc)
        win.resize(760, 980)
        win.finished.connect(lambda *_: self._redock_editor())
        self._editor_window = win
        self._editor_window_scroll = sc
        self._btn_editor_popout.setText("⤡ Andocken")
        self._editor_scroll.setVisible(False)
        self._editor_placeholder.setVisible(True)
        win.show()

    def _redock_editor(self):
        """Holt den Editor-Koerper aus dem Fenster zurueck in die Inline-Ansicht."""
        if self._editor_window is None:
            return
        try:
            body = self._editor_window_scroll.takeWidget()
            if body is not None:
                self._editor_scroll.setWidget(body)
            self._editor_scroll.setVisible(True)
            self._editor_placeholder.setVisible(False)
            self._btn_editor_popout.setText("⤢ Großes Fenster")
        except RuntimeError:
            pass  # Widgets beim Layout-Wechsel zerstoert
        self._editor_window = None

    def _refresh(self):
        if self._audio.file_path and os.path.exists(self._audio.file_path):
            size = os.path.getsize(self._audio.file_path) // 1024
            self._lbl_status.setText(f"OK ({size} KB)")
            self._lbl_status.setStyleSheet("color: #9DFF52; font-size: 10px;")
        elif self._audio.file_path:
            self._lbl_status.setText(f"Datei nicht gefunden: {self._audio.file_path}")
            self._lbl_status.setStyleSheet("color: #ff4444; font-size: 10px;")
        else:
            self._lbl_status.setText("Keine Datei ausgewählt")
            self._lbl_status.setStyleSheet("color: #888888; font-size: 10px;")
        if not self._audio._available:
            self._lbl_status.setText(self._lbl_status.text() +
                                     " (PySide6.QtMultimedia fehlt - Audio deaktiviert)")

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Audio-Datei auswählen", "",
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
