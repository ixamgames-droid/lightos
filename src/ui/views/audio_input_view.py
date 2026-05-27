"""Audio Input View - WASAPI-Loopback Aufnahme + Beat-Detection Einstellungen.

Liefert eine UI um:
- Audio-Eingang (Speaker Loopback / Mikro) auszuwaehlen
- Start/Stop des Captures
- Sensitivity, Bass-Band und Cooldown einzustellen
- Pegel, Bass, Treble und BPM live zu sehen
- Den BPMManager mit den erkannten Beats zu fuettern
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QLabel, QComboBox, QPushButton, QDoubleSpinBox, QSpinBox,
    QCheckBox, QProgressBar, QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer

try:
    from src.core.audio.capture import (
        AudioCapture, get_audio_capture, HAS_SOUNDCARD,
    )
    from src.core.audio.beat_detector import get_beat_detector
    AUDIO_AVAILABLE = True
except Exception as _e:
    AUDIO_AVAILABLE = False
    print(f"[audio_input_view] audio import error: {_e}")

try:
    import numpy as np
    HAS_NUMPY = True
except Exception:
    HAS_NUMPY = False


class AudioInputView(QWidget):
    """Konfiguriert den Audio-Capture und zeigt Beats + BPM live an."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._capture = get_audio_capture() if AUDIO_AVAILABLE else None
        self._detector = get_beat_detector() if AUDIO_AVAILABLE else None
        self._level: float = 0.0
        self._bass: float = 0.0
        self._treble: float = 0.0
        self._beat_flash: int = 0   # countdown frames fuer Beat-Indikator
        self._setup_ui()

        if not AUDIO_AVAILABLE or not HAS_NUMPY or (
                AUDIO_AVAILABLE and not HAS_SOUNDCARD):
            self._disable_ui_with_message(
                "Audio nicht verfuegbar.\n"
                "Installiere 'soundcard' und 'numpy' (pip install soundcard numpy)."
            )
            return

        # Beat- und Level-Callback verkabeln
        self._capture.subscribe(self._on_audio_chunk)
        self._detector.subscribe(self._on_beat)

        # Geraete-Liste aufbauen
        self._populate_devices()

        # UI-Refresh-Timer (30 Hz)
        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(33)
        self._ui_timer.timeout.connect(self._refresh_ui)
        self._ui_timer.start()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # ── Geraete / Steuerung ───────────────────────────────────────────────
        dev_box = QGroupBox("Audio-Eingang")
        dev_layout = QFormLayout(dev_box)

        self._combo_device = QComboBox()
        self._combo_device.setMinimumWidth(280)
        self._combo_device.currentIndexChanged.connect(self._on_device_changed)
        dev_layout.addRow("Geraet:", self._combo_device)

        btn_row = QHBoxLayout()
        self._btn_start = QPushButton("Start")
        self._btn_start.clicked.connect(self._start_capture)
        btn_row.addWidget(self._btn_start)

        self._btn_stop = QPushButton("Stop")
        self._btn_stop.clicked.connect(self._stop_capture)
        btn_row.addWidget(self._btn_stop)

        self._btn_refresh = QPushButton("Geraete neu lesen")
        self._btn_refresh.clicked.connect(self._populate_devices)
        btn_row.addWidget(self._btn_refresh)
        btn_row.addStretch(1)
        dev_layout.addRow("", _row_widget(btn_row))

        self._chk_drive_bpm = QCheckBox("BPM-Manager mit erkannten Beats steuern")
        self._chk_drive_bpm.setToolTip(
            "Wenn aktiv, treibt der Beat-Detektor die globalen BPM/Beats")
        self._chk_drive_bpm.toggled.connect(self._on_drive_bpm_toggled)
        dev_layout.addRow("", self._chk_drive_bpm)

        root.addWidget(dev_box)

        # ── Detector-Parameter ────────────────────────────────────────────────
        det_box = QGroupBox("Beat-Detection Parameter")
        det_layout = QFormLayout(det_box)

        self._spin_sens = QDoubleSpinBox()
        self._spin_sens.setRange(0.5, 3.0)
        self._spin_sens.setSingleStep(0.05)
        self._spin_sens.setDecimals(2)
        self._spin_sens.setValue(1.3)
        self._spin_sens.valueChanged.connect(self._on_params_changed)
        det_layout.addRow("Sensitivity:", self._spin_sens)

        self._spin_low = QSpinBox()
        self._spin_low.setRange(20, 500)
        self._spin_low.setValue(40)
        self._spin_low.setSuffix(" Hz")
        self._spin_low.valueChanged.connect(self._on_params_changed)
        det_layout.addRow("Bass-Band (low):", self._spin_low)

        self._spin_high = QSpinBox()
        self._spin_high.setRange(40, 800)
        self._spin_high.setValue(180)
        self._spin_high.setSuffix(" Hz")
        self._spin_high.valueChanged.connect(self._on_params_changed)
        det_layout.addRow("Bass-Band (high):", self._spin_high)

        self._spin_cooldown = QSpinBox()
        self._spin_cooldown.setRange(50, 2000)
        self._spin_cooldown.setSingleStep(10)
        self._spin_cooldown.setValue(250)
        self._spin_cooldown.setSuffix(" ms")
        self._spin_cooldown.valueChanged.connect(self._on_params_changed)
        det_layout.addRow("Cooldown:", self._spin_cooldown)

        root.addWidget(det_box)

        # ── Live-Anzeige ──────────────────────────────────────────────────────
        live_box = QGroupBox("Live")
        live_layout = QFormLayout(live_box)

        self._bar_level = _meter("#3fa34d")
        live_layout.addRow("Pegel:", self._bar_level)

        self._bar_bass = _meter("#c0392b")
        live_layout.addRow("Bass:", self._bar_bass)

        self._bar_treble = _meter("#2980b9")
        live_layout.addRow("Hoehen:", self._bar_treble)

        bpm_row = QHBoxLayout()
        self._lbl_bpm = QLabel("BPM: --")
        f = self._lbl_bpm.font()
        f.setPointSize(20)
        f.setBold(True)
        self._lbl_bpm.setFont(f)
        bpm_row.addWidget(self._lbl_bpm)

        self._lbl_beat = QLabel("BEAT")
        self._lbl_beat.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_beat.setFixedSize(60, 32)
        self._lbl_beat.setStyleSheet(
            "background:#222222; color:#444444; border-radius:6px; "
            "font-weight:bold;")
        bpm_row.addWidget(self._lbl_beat)
        bpm_row.addStretch(1)
        live_layout.addRow("", _row_widget(bpm_row))

        self._lbl_status = QLabel("Status: gestoppt")
        self._lbl_status.setStyleSheet("color:#888888;")
        live_layout.addRow("", self._lbl_status)

        root.addWidget(live_box)
        root.addStretch(1)

    def _disable_ui_with_message(self, text: str):
        """Versteckt Controls und zeigt einen Hinweis."""
        # Alle Kinder deaktivieren ausser Hinweistext
        for w in self.findChildren(QWidget):
            w.setEnabled(False)
        msg = QLabel(text)
        msg.setStyleSheet("color:#cc8800; padding:8px;")
        msg.setWordWrap(True)
        self.layout().insertWidget(0, msg)

    # ── Geraete-Management ────────────────────────────────────────────────────

    def _populate_devices(self):
        if not AUDIO_AVAILABLE:
            return
        self._combo_device.blockSignals(True)
        self._combo_device.clear()
        try:
            speakers = AudioCapture.list_speakers()
            default = AudioCapture.default_speaker()
            for name in speakers:
                marker = "  (Standard)" if name == default else ""
                self._combo_device.addItem(
                    f"[Loopback] {name}{marker}", name)
        except Exception as e:
            print(f"[audio_input_view] list_speakers error: {e}")
        # Default auswaehlen
        if self._capture and self._capture._device_name:
            for i in range(self._combo_device.count()):
                if self._combo_device.itemData(i) == self._capture._device_name:
                    self._combo_device.setCurrentIndex(i)
                    break
        self._combo_device.blockSignals(False)

    def _on_device_changed(self, _idx: int):
        if not self._capture:
            return
        name = self._combo_device.currentData()
        if name:
            self._capture.set_device(name)

    # ── Start/Stop ────────────────────────────────────────────────────────────

    def _start_capture(self):
        if not self._capture:
            return
        name = self._combo_device.currentData()
        if name:
            self._capture.set_device(name)
        ok = self._capture.start()
        if ok:
            self._lbl_status.setText("Status: laeuft")
            self._lbl_status.setStyleSheet("color:#9DFF52;")
        else:
            self._lbl_status.setText("Status: Start fehlgeschlagen")
            self._lbl_status.setStyleSheet("color:#ff4444;")

    def _stop_capture(self):
        if not self._capture:
            return
        self._capture.stop()
        self._lbl_status.setText("Status: gestoppt")
        self._lbl_status.setStyleSheet("color:#888888;")

    # ── Parameter ─────────────────────────────────────────────────────────────

    def _on_params_changed(self, *_):
        if not self._detector:
            return
        self._detector.set_sensitivity(self._spin_sens.value())
        # Bass-Band sicher anwenden (low < high)
        low = self._spin_low.value()
        high = self._spin_high.value()
        if low >= high:
            high = low + 10
            self._spin_high.blockSignals(True)
            self._spin_high.setValue(high)
            self._spin_high.blockSignals(False)
        self._detector.band_low_hz = low
        self._detector.band_high_hz = high
        self._detector.min_beat_interval = self._spin_cooldown.value() / 1000.0

    # ── BPM Manager Anbindung ─────────────────────────────────────────────────

    def _on_drive_bpm_toggled(self, checked: bool):
        try:
            from src.core.engine.bpm_manager import get_bpm_manager
            mgr = get_bpm_manager()
            mgr.use_audio_source(bool(checked))
        except Exception as e:
            print(f"[audio_input_view] drive bpm error: {e}")

    # ── Audio-Callbacks ───────────────────────────────────────────────────────

    def _on_audio_chunk(self, samples):
        """Wird im Capture-Thread aufgerufen."""
        if not HAS_NUMPY:
            return
        try:
            # Detector verarbeiten lassen
            self._detector.process_chunk(samples)
            # Eigene Pegel/Spektrum berechnen fuer UI
            rms = float(np.sqrt(np.mean(samples * samples)))
            self._level = min(1.0, rms * 4.0)
            n = len(samples)
            if n >= 64:
                fft = np.abs(np.fft.rfft(samples * np.hanning(n)))
                freqs = np.fft.rfftfreq(n, 1.0 / 44100)
                bass_mask = (freqs >= 40) & (freqs <= 250)
                trbl_mask = (freqs >= 2000) & (freqs <= 8000)
                bass = float(np.sqrt(np.mean(fft[bass_mask] ** 2)))
                treble = float(np.sqrt(np.mean(fft[trbl_mask] ** 2)))
                self._bass = min(1.0, bass * 0.005)
                self._treble = min(1.0, treble * 0.01)
        except Exception as e:
            print(f"[audio_input_view] chunk error: {e}")

    def _on_beat(self):
        """Wird im Detector-Thread aufgerufen."""
        self._beat_flash = 4  # Frames lang leuchten

    # ── UI Refresh ────────────────────────────────────────────────────────────

    def _refresh_ui(self):
        if not self._detector:
            return
        # Bars
        self._bar_level.setValue(int(self._level * 100))
        self._bar_bass.setValue(int(self._bass * 100))
        self._bar_treble.setValue(int(self._treble * 100))

        # BPM
        bpm = self._detector.get_bpm()
        if bpm > 0:
            self._lbl_bpm.setText(f"BPM: {bpm:.1f}")
        else:
            self._lbl_bpm.setText("BPM: --")

        # Beat-Flash
        if self._beat_flash > 0:
            self._lbl_beat.setStyleSheet(
                "background:#FFD700; color:#000; border-radius:6px; "
                "font-weight:bold;")
            self._beat_flash -= 1
        else:
            self._lbl_beat.setStyleSheet(
                "background:#222222; color:#444444; border-radius:6px; "
                "font-weight:bold;")

        # Capture-Status checken (z.B. wenn Thread gestorben ist)
        if self._capture and not self._capture.is_running() and (
                self._lbl_status.text() == "Status: laeuft"):
            self._lbl_status.setText("Status: gestoppt")
            self._lbl_status.setStyleSheet("color:#888888;")


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _meter(color: str) -> QProgressBar:
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(0)
    bar.setTextVisible(False)
    bar.setFixedHeight(14)
    bar.setStyleSheet(
        "QProgressBar { background:#222222; border:1px solid #333333; "
        "border-radius:3px; } "
        f"QProgressBar::chunk {{ background:{color}; }}"
    )
    return bar


def _row_widget(layout: QHBoxLayout) -> QWidget:
    w = QWidget()
    w.setLayout(layout)
    return w
