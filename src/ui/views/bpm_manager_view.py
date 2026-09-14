"""BPM-Manager-Tab — der „Leader"-zentrierte Tab.

Oben ein **Monitor** (grosse Live-BPM, Takt 1·2·3·4, Beat-Flash, Confidence,
Spektrum, aktive Quelle), unten die **Einstellungen** (AUTO/MANUAL, Quellenwahl,
Min/Max-Grenzen „Hoehen und Tiefen", Sensitivity, Glaettung, Tap/Nudge/Lock).
Tempo-Buses, Grand-Master und „Effekte je Bus" liegen seit BPM-08 im eigenen
Sub-Tab ``tempo_bus_view.TempoBusView``.

Alle Widgets lesen/schreiben NUR ueber die Singletons ``get_bpm_manager()`` /
``get_beat_detector()`` / ``get_audio_capture()`` — kein eigener BPM-Zustand.
Manager-Callbacks kommen aus Audio-/Timer-Threads → ausschliesslich ueber
Qt-Signale in den UI-Thread marshallen (sonst cross-thread Widget-Zugriff = Crash).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QRadioButton, QButtonGroup, QComboBox, QSpinBox, QSlider, QGroupBox,
    QProgressBar, QScrollArea, QFrame, QCheckBox,
)

from src.core.engine.bpm_manager import get_bpm_manager, BpmMode
from src.core.audio import bpm_settings
from src.ui.weak_slots import weak_slot

try:
    from src.core.audio.beat_detector import get_beat_detector
except Exception:  # pragma: no cover - numpy fehlt o.ae.
    get_beat_detector = None  # type: ignore[assignment]

try:
    from src.ui.views.spectrum_bars import SpectrumBars
except Exception:  # pragma: no cover
    SpectrumBars = None  # type: ignore[assignment]


_DOT_IDLE = "background:#1c1c1c; border:1px solid #333; border-radius:13px;"
_SRC_LABELS = {
    "audio": "AUTO · Audio",
    "os2l": "OS2L (extern)",
    "tap": "MANUAL · Tap",
    "nudge": "MANUAL · Nudge",
    "manual": "MANUAL · Eingabe",
    "file": "AUTO · Datei/Player",
    "timeline": "AUTO · Lied-Analyse",
    "off": "—",
}


class BpmManagerView(QWidget):
    """Eigenstaendiger BPM-Manager-Tab."""

    _bpm_sig = Signal(float)
    _beat_sig = Signal(int)
    _state_sig = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mgr = get_bpm_manager()
        self._det = get_beat_detector() if get_beat_detector else None
        self._loading = True            # unterdrueckt Save/Backend waehrend Init
        self._beat_phase = 0
        # Entprellung (BPM-07): ein Sliderzug loest hunderte valueChanged aus —
        # gesammelt wird EIN Schreibvorgang 400 ms nach dem letzten Tick.
        # hideEvent/closeEvent schreiben Ausstehendes sofort (flush_pending_save).
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._write_settings)
        self._source_pref = bpm_settings.DEFAULTS["source"]

        self._build_ui()
        self._load_into_controls()
        self._wire_backend()
        self._loading = False

        # Monitor-Poll-Timer (Confidence/Status) — nur bei Sichtbarkeit aktiv.
        # (Der Bus-Tabellen-Poll liegt seit BPM-08 in tempo_bus_view.py.)
        self._poll = QTimer(self)
        self._poll.setInterval(150)
        self._poll.timeout.connect(self._refresh_monitor)

    # ── Aufbau ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        host = QWidget()
        scroll.setWidget(host)
        root = QVBoxLayout(host)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(12)

        root.addWidget(self._build_monitor())
        root.addWidget(self._build_settings())
        root.addStretch(1)

    def _build_monitor(self) -> QGroupBox:
        box = QGroupBox("Monitor")
        lay = QVBoxLayout(box)

        top = QHBoxLayout()
        self._lbl_bpm = QLabel("-- BPM")
        self._lbl_bpm.setStyleSheet(
            "color:#FFD700; font-size:44px; font-weight:bold;")
        top.addWidget(self._lbl_bpm)
        top.addSpacing(16)

        col = QVBoxLayout()
        self._lbl_source = QLabel("Quelle: —")
        self._lbl_source.setStyleSheet("color:#bbbbbb;")
        col.addWidget(self._lbl_source)
        self._lbl_status = QLabel("")
        self._lbl_status.setStyleSheet("color:#f0883e;")
        col.addWidget(self._lbl_status)
        top.addLayout(col)
        top.addStretch(1)

        self._dot = QLabel(" ")
        self._dot.setFixedSize(26, 26)
        self._dot.setStyleSheet(_DOT_IDLE)
        top.addWidget(self._dot)
        self._dot_timer = QTimer(self)
        self._dot_timer.setInterval(110)
        self._dot_timer.setSingleShot(True)
        self._dot_timer.timeout.connect(self._on_dot_idle)
        lay.addLayout(top)

        # Takt-Anzeige (dynamisch nach beats_per_bar; max. 16 Zellen sichtbar)
        phase = QHBoxLayout()
        phase.addWidget(QLabel("Takt:"))
        self._phase_cells_host = QWidget()
        self._phase_row = QHBoxLayout(self._phase_cells_host)
        self._phase_row.setContentsMargins(0, 0, 0, 0)
        self._phase_row.setSpacing(4)
        phase.addWidget(self._phase_cells_host)
        self._phase_pos = QLabel("")
        self._phase_pos.setStyleSheet("color:#888;")
        phase.addWidget(self._phase_pos)
        phase.addStretch(1)
        lay.addLayout(phase)
        self._phase_lbls: list[QLabel] = []
        self._rebuild_phase_cells()

        # Confidence
        conf = QHBoxLayout()
        conf.addWidget(QLabel("Erkennungs-Qualität:"))
        self._conf = QProgressBar()
        self._conf.setRange(0, 100)
        self._conf.setValue(0)
        self._conf.setTextVisible(True)
        # UI-24c: sichtbare Kontur auch bei 0 % — sonst wirkt der leere Balken
        # (ohne Chunk) wie ein fehlendes/kaputtes Element.
        self._conf.setStyleSheet(
            "QProgressBar { border: 1px solid #3d444d; border-radius: 3px; "
            "background: #161b22; text-align: center; color: #e6edf3; } "
            "QProgressBar::chunk { background: #3fb950; border-radius: 2px; }")
        conf.addWidget(self._conf, 1)
        lay.addLayout(conf)

        # Spektrum
        if SpectrumBars is not None:
            self._spectrum = SpectrumBars()
            lay.addWidget(self._spectrum)
        else:
            self._spectrum = None
        return box

    def _on_dot_idle(self):
        # Bound-Method-Slot statt Lambda (STAB-09): Qt-Builtin-Methoden haben
        # kein __func__ und sind daher kein gueltiger weak_slot-Receiver.
        self._dot.setStyleSheet(_DOT_IDLE)

    def _build_settings(self) -> QGroupBox:
        box = QGroupBox("Einstellungen")
        grid = QGridLayout(box)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        r = 0

        # ── BPM-Quelle (primärer, einfacher Umschalter) ──
        grid.addWidget(QLabel("BPM-Quelle:"), r, 0)
        kind_row = QHBoxLayout()
        self._rb_kind_live = QRadioButton("Live-Audio")
        self._rb_kind_song = QRadioButton("Lied-Analyse")
        self._rb_kind_manual = QRadioButton("Manuell / Tap")
        self._rb_kind_live.setToolTip("BPM live aus dem Audio-Eingang erkennen (Standard).")
        self._rb_kind_song.setToolTip("BPM folgt der Offline-Analyse eines geladenen Songs "
                                      "(aus dem Generator-Tab).")
        self._rb_kind_manual.setToolTip("BPM manuell per Tap/Eingabe festlegen.")
        self._kind_grp = QButtonGroup(self)
        for _rb in (self._rb_kind_live, self._rb_kind_song, self._rb_kind_manual):
            self._kind_grp.addButton(_rb)
            _rb.toggled.connect(self._on_kind_changed)
            kind_row.addWidget(_rb)
        kind_row.addStretch(1)
        grid.addLayout(kind_row, r, 1)
        r += 1

        # Lied-Analyse: welcher analysierte Song treibt die BPM?
        grid.addWidget(QLabel("Analyse-Song:"), r, 0)
        song_row = QHBoxLayout()
        self._cmb_song = QComboBox()
        self._cmb_song.setMinimumWidth(260)
        self._cmb_song.setEnabled(False)
        self._cmb_song.currentIndexChanged.connect(self._on_song_changed)
        btn_song_refresh = QPushButton("↻")
        btn_song_refresh.setFixedWidth(30)
        btn_song_refresh.setToolTip("Liste der analysierten Songs aktualisieren.")
        btn_song_refresh.clicked.connect(self._populate_songs)
        self._chk_phase = QCheckBox("Taktgenau")
        self._chk_phase.setChecked(True)
        self._chk_phase.setToolTip("Beats treffen exakt das Lied-Beatgrid (statt nur "
                                   "den BPM-Wert). Aus = nur BPM-Wert folgen.")
        self._chk_phase.toggled.connect(self._on_phase_toggled)
        self._lbl_song_info = QLabel("")
        self._lbl_song_info.setStyleSheet("color:#8b949e;")
        song_row.addWidget(self._cmb_song)
        song_row.addWidget(btn_song_refresh)
        song_row.addWidget(self._chk_phase)
        song_row.addWidget(self._lbl_song_info)
        song_row.addStretch(1)
        grid.addLayout(song_row, r, 1)
        r += 1

        # Genre-Preset (stellt Grenzen + Empfindlichkeit/Glättung + Takt passend ein)
        grid.addWidget(QLabel("Genre-Preset:"), r, 0)
        genre_row = QHBoxLayout()
        self._cmb_genre = QComboBox()
        try:
            from src.core.audio import genre_presets as _gp
            for _k in _gp.ORDER:
                self._cmb_genre.addItem(_gp.label(_k), _k)
        except Exception:
            pass
        self._cmb_genre.setToolTip("Stellt Tempo-Grenzen, Empfindlichkeit, Glättung "
                                   "und Takt passend zum Musikstil ein.")
        btn_genre = QPushButton("Anwenden")
        btn_genre.setToolTip("Übernimmt das gewählte Genre-Preset in die Erkennung.")
        btn_genre.clicked.connect(self._on_genre_preset)
        genre_row.addWidget(self._cmb_genre)
        genre_row.addWidget(btn_genre)
        genre_row.addStretch(1)
        grid.addLayout(genre_row, r, 1)
        r += 1

        # Modus-Spiegel (AUTO/MANUAL) — von der BPM-Quelle gesteuert, daher
        # unsichtbar; bleibt als funktionaler Backend-/Test-Schalter erhalten.
        self._rb_auto = QRadioButton("AUTO (Audio)", box)
        self._rb_manual = QRadioButton("MANUAL", box)
        self._rb_auto.setVisible(False)
        self._rb_manual.setVisible(False)
        self._mode_grp = QButtonGroup(self)
        self._mode_grp.addButton(self._rb_auto)
        self._mode_grp.addButton(self._rb_manual)
        self._rb_auto.toggled.connect(self._on_mode_changed)

        # Lock (sichtbar)
        grid.addWidget(QLabel("Lock:"), r, 0)
        lock_row = QHBoxLayout()
        self._btn_lock = QPushButton("🔒 BPM einfrieren")
        self._btn_lock.setCheckable(True)
        self._btn_lock.setToolTip("Friert die BPM ein (Quellen ändern sie nicht).")
        self._btn_lock.toggled.connect(self._on_lock_toggled)
        lock_row.addWidget(self._btn_lock)
        lock_row.addStretch(1)
        grid.addLayout(lock_row, r, 1)
        r += 1

        # Audio-Eingang (Detail für „Live-Audio")
        grid.addWidget(QLabel("Audio-Eingang:"), r, 0)
        src_row = QHBoxLayout()
        self._rb_loop = QRadioButton("PC-Audio (Player/Spotify)")
        self._rb_input = QRadioButton("Externer Eingang")
        self._rb_os2l = QRadioButton("OS2L (VirtualDJ)")
        self._src_grp = QButtonGroup(self)
        for rb in (self._rb_loop, self._rb_input, self._rb_os2l):
            self._src_grp.addButton(rb)
        self._cmb_device = QComboBox()
        self._cmb_device.setMinimumWidth(180)
        self._cmb_device.setEnabled(False)
        self._rb_loop.toggled.connect(self._on_source_changed)
        self._rb_input.toggled.connect(self._on_source_changed)
        self._rb_os2l.toggled.connect(self._on_source_changed)
        self._cmb_device.currentIndexChanged.connect(self._on_source_changed)
        src_row.addWidget(self._rb_loop)
        src_row.addWidget(self._rb_input)
        src_row.addWidget(self._cmb_device)
        src_row.addWidget(self._rb_os2l)
        src_row.addStretch(1)
        grid.addLayout(src_row, r, 1)
        r += 1

        # Grenzen Min/Max
        grid.addWidget(QLabel("Grenzen (BPM):"), r, 0)
        bound_row = QHBoxLayout()
        bound_row.addWidget(QLabel("Tiefen"))
        self._sp_min = QSpinBox()
        self._sp_min.setRange(20, 400)
        self._sp_min.valueChanged.connect(self._on_bounds_changed)
        bound_row.addWidget(self._sp_min)
        bound_row.addSpacing(10)
        bound_row.addWidget(QLabel("Höhen"))
        self._sp_max = QSpinBox()
        self._sp_max.setRange(20, 400)
        self._sp_max.valueChanged.connect(self._on_bounds_changed)
        bound_row.addWidget(self._sp_max)
        bound_row.addStretch(1)
        grid.addLayout(bound_row, r, 1)
        r += 1

        # Sensitivity
        grid.addWidget(QLabel("Empfindlichkeit:"), r, 0)
        sens_row = QHBoxLayout()
        self._sl_sens = QSlider(Qt.Orientation.Horizontal)
        self._sl_sens.setRange(50, 300)   # 0.50 .. 3.00
        self._sl_sens.valueChanged.connect(self._on_sens_changed)
        self._lbl_sens = QLabel("1.30")
        sens_row.addWidget(self._sl_sens, 1)
        sens_row.addWidget(self._lbl_sens)
        grid.addLayout(sens_row, r, 1)
        r += 1

        # Smoothing
        grid.addWidget(QLabel("Glättung:"), r, 0)
        sm_row = QHBoxLayout()
        self._sl_smooth = QSlider(Qt.Orientation.Horizontal)
        self._sl_smooth.setRange(0, 100)
        self._sl_smooth.valueChanged.connect(self._on_smooth_changed)
        self._lbl_smooth = QLabel("0.30")
        sm_row.addWidget(self._sl_smooth, 1)
        sm_row.addWidget(self._lbl_smooth)
        grid.addLayout(sm_row, r, 1)
        r += 1

        # Takt-Raster (Bar-Laenge + Unterteilung)
        grid.addWidget(QLabel("Takt-Raster:"), r, 0)
        meter_row = QHBoxLayout()
        meter_row.addWidget(QLabel("Beats/Takt"))
        self._sp_bpb = QSpinBox()
        self._sp_bpb.setRange(1, 32)
        self._sp_bpb.setToolTip(
            "Schläge pro Takt — Downbeat/Bar-Event alle N Beats "
            "(4 = Viertakt, 16 = Sechzehntakt). Ändert nicht die Beat-Rate.")
        self._sp_bpb.valueChanged.connect(self._on_meter_changed)
        meter_row.addWidget(self._sp_bpb)
        for _n in (4, 8, 16):
            b = QPushButton(str(_n))
            b.setFixedWidth(34)
            b.clicked.connect(weak_slot(self._on_bpb_preset, _n))
            meter_row.addWidget(b)
        meter_row.addSpacing(12)
        meter_row.addWidget(QLabel("Unterteilung"))
        self._cmb_subdiv = QComboBox()
        for _sub in (1, 2, 3, 4, 6, 8, 16):
            self._cmb_subdiv.addItem("aus" if _sub == 1 else f"1/{_sub}", _sub)
        self._cmb_subdiv.setToolTip(
            "Zusätzliche Sub-Ticks pro Beat für schnellere Effekte "
            "(Timer/Tap/Datei-Modus; bei Live-Audio nur Beat-Rate).")
        self._cmb_subdiv.currentIndexChanged.connect(self._on_meter_changed)
        meter_row.addWidget(self._cmb_subdiv)
        meter_row.addStretch(1)
        grid.addLayout(meter_row, r, 1)
        r += 1

        # Tap / Nudge
        grid.addWidget(QLabel("Manuell:"), r, 0)
        tap_row = QHBoxLayout()
        btn_tap = QPushButton("TAP")
        btn_tap.setFixedWidth(60)
        btn_tap.clicked.connect(weak_slot(self._mgr.tap))
        tap_row.addWidget(btn_tap)
        tap_row.addSpacing(10)
        for delta in (-10, -5, -1, +1, +5, +10):
            b = QPushButton(f"{delta:+d}")
            b.setFixedWidth(44)
            b.clicked.connect(weak_slot(self._mgr.nudge, delta))
            tap_row.addWidget(b)
        tap_row.addStretch(1)
        grid.addLayout(tap_row, r, 1)
        return box

    @staticmethod
    def _phase_style(active: bool, accent: bool) -> str:
        if active:
            col = "#FFD700" if accent else "#9DFF52"
            return (f"background:{col}; color:#111; font-weight:bold;"
                    f" border-radius:4px;")
        return "background:#1c1c1c; color:#777; border:1px solid #333; border-radius:4px;"

    def _rebuild_phase_cells(self):
        """Baut die Takt-Zellen passend zu ``beats_per_bar`` (max. 16 sichtbar)."""
        while self._phase_row.count():
            it = self._phase_row.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        self._phase_lbls = []
        n = max(1, int(self._mgr.beats_per_bar))
        for i in range(min(n, 16)):
            pl = QLabel(str(i + 1))
            pl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pl.setFixedSize(24, 22)
            pl.setStyleSheet(self._phase_style(False, i == 0))
            self._phase_row.addWidget(pl)
            self._phase_lbls.append(pl)

    # ── Init-Werte ────────────────────────────────────────────────────────────

    def _load_into_controls(self):
        """Regler aus dem BACKEND-Zustand fuellen (Manager/Detektor/Director).
        ``bpm_settings.boot()`` hat die Datei beim App-Start bereits angewandt —
        eine Default-Quelle (``bpm_settings.DEFAULTS``), kein zweites Anwenden
        hier. Nur Audio-Quelle und Geraet kommen aus den Prefs: dafuer gibt es
        keinen Backend-Stand (Capture kann gestoppt oder ``off`` sein)."""
        D = bpm_settings.DEFAULTS
        mgr = self._mgr
        self._sp_min.setValue(int(mgr.min_bpm))
        self._sp_max.setValue(int(mgr.max_bpm))
        sens = float(getattr(self._det, "sensitivity", 1.3))
        self._sl_sens.setValue(int(round(sens * 100)))
        self._lbl_sens.setText(f"{sens:.2f}")
        sm = float(getattr(self._det, "smoothing", 0.3))
        self._sl_smooth.setValue(int(round(sm * 100)))
        self._lbl_smooth.setText(f"{sm:.2f}")

        # Takt-Raster (Spinbox klemmt selbst auf ihren Bereich)
        self._sp_bpb.setValue(int(mgr.beats_per_bar))
        si = self._cmb_subdiv.findData(int(mgr.subdivision))
        self._cmb_subdiv.setCurrentIndex(si if si >= 0 else 0)

        # Taktgenaue Wiedergabe (Lied-Analyse)
        try:
            from src.core.audio.music_show import get_music_director
            pa = bool(get_music_director().is_phase_accurate())
        except Exception:
            pa = D["phase_accurate_beats"]
        self._chk_phase.setChecked(pa)

        # Geraeteliste fuellen
        try:
            from src.core.audio.capture import get_audio_capture
            devs = type(get_audio_capture()).list_input_devices()
        except Exception:
            devs = []
        self._cmb_device.clear()
        self._cmb_device.addItems(devs or ["(kein Eingang gefunden)"])

        # Quelle + Geraet aus den Prefs (v2: source/device)
        s = bpm_settings.load_settings()
        dev = s["device"]
        if dev and dev in devs:
            self._cmb_device.setCurrentText(dev)
        self._source_pref = s["source"]
        if self._source_pref == "input":
            self._rb_input.setChecked(True)
            self._cmb_device.setEnabled(True)
        elif self._source_pref == "os2l":
            self._rb_os2l.setChecked(True)
            self._cmb_device.setEnabled(False)
        else:
            # loopback — und bis S4 ohne eigenen Schalter auch song/off; der
            # gespeicherte Wert bleibt in _source_pref, bis der Nutzer die
            # Quelle selbst umschaltet (_on_source_changed).
            self._rb_loop.setChecked(True)

        # Modus aus dem Manager (Live-Zustand gewinnt)
        self._populate_songs()
        self._reflect_state()
        self._rebuild_phase_cells()

    # ── Backend-Verdrahtung (marshalling) ─────────────────────────────────────

    def _wire_backend(self):
        self._bpm_sig.connect(self._on_bpm)
        self._beat_sig.connect(self._on_beat)
        self._state_sig.connect(self._reflect_state)
        self._cb_bpm = lambda b: self._bpm_sig.emit(float(b))
        self._cb_beat = lambda idx: self._beat_sig.emit(int(idx))
        self._cb_state = lambda: self._state_sig.emit()
        self._mgr.subscribe_bpm_change(self._cb_bpm)
        self._mgr.subscribe_beat(self._cb_beat)
        self._mgr.subscribe_state_change(self._cb_state)
        # Beim Zerstoeren abmelden (Geister-Callbacks vermeiden). Closure ohne
        # self -> sicher auch nach Python-Teardown.
        mgr = self._mgr
        cbb, cbt, cbs = self._cb_bpm, self._cb_beat, self._cb_state

        def _unsub(*_):
            for fn, cb in ((mgr.unsubscribe_bpm_change, cbb),
                           (mgr.unsubscribe_beat, cbt),
                           (mgr.unsubscribe_state_change, cbs)):
                try:
                    fn(cb)
                except Exception:
                    pass
        self.destroyed.connect(_unsub)
        self._on_bpm(self._mgr.bpm)

    # ── Slots (UI-Thread) ─────────────────────────────────────────────────────

    def _on_bpm(self, bpm: float):
        if bpm and bpm > 0:
            self._lbl_bpm.setText(f"{bpm:.1f} BPM")
            self._lbl_bpm.setStyleSheet("color:#FFD700; font-size:44px; font-weight:bold;")
        else:
            self._lbl_bpm.setText("-- BPM")
            self._lbl_bpm.setStyleSheet("color:#888; font-size:44px; font-weight:bold;")

    def _on_beat(self, idx: int):
        bpb = max(1, int(self._mgr.beats_per_bar))
        self._beat_phase = idx % bpb
        accent = (self._beat_phase == 0)
        col = "#FFD700" if accent else "#9DFF52"
        self._dot.setStyleSheet(
            f"background:{col}; border:1px solid {col}; border-radius:13px;")
        self._dot_timer.start()
        for i, pl in enumerate(self._phase_lbls):
            pl.setStyleSheet(self._phase_style(i == self._beat_phase, i == 0))
        # Bei >16 Schlaegen pro Takt zeigen die Zellen nur die ersten 16 — der
        # Text rechts haelt die exakte Position fest.
        if bpb > len(self._phase_lbls):
            self._phase_pos.setText(f"{self._beat_phase + 1} / {bpb}")
        else:
            self._phase_pos.setText("")

    def _reflect_state(self):
        """Modus/Quelle/Lock aus dem Manager in die UI spiegeln (ohne Rueckschreiben)."""
        self._loading = True
        try:
            is_auto = (self._mgr.mode == BpmMode.AUTO)
            self._rb_auto.setChecked(is_auto)
            self._rb_manual.setChecked(not is_auto)
            self._btn_lock.setChecked(self._mgr.is_locked)
            src = self._mgr.current_source
            self._lbl_source.setText(f"Quelle: {_SRC_LABELS.get(src, src)}")
            # Primären Quellen-Umschalter spiegeln (folgt der aktiven Quelle)
            if src == "timeline":
                self._rb_kind_song.setChecked(True)
            elif self._mgr.mode == BpmMode.MANUAL:
                self._rb_kind_manual.setChecked(True)
            else:
                self._rb_kind_live.setChecked(True)
            self._cmb_song.setEnabled(self._rb_kind_song.isChecked())
        finally:
            self._loading = False

    def _refresh_monitor(self):
        if self._det is not None:
            try:
                c = int(round(self._det.get_confidence() * 100))
                self._conf.setValue(max(0, min(100, c)))
            except Exception:
                pass
        # Capture-Status / Fehler
        try:
            from src.core.audio.capture import get_audio_capture
            cap = get_audio_capture()
            err = cap.last_error()
            if err:
                self._lbl_status.setText(f"⚠ {err}")
            elif cap.is_running():
                self._lbl_status.setText("Audio läuft")
            else:
                self._lbl_status.setText("Audio gestoppt")
        except Exception:
            self._lbl_status.setText("")

    # ── Einstellungs-Handler ──────────────────────────────────────────────────

    def _on_mode_changed(self, _checked=False):
        if self._loading:
            return
        self._mgr.set_mode("auto" if self._rb_auto.isChecked() else "manual")
        self._save()

    def _on_lock_toggled(self, checked: bool):
        if self._loading:
            return
        self._mgr.set_locked(bool(checked))

    def _on_source_changed(self, *_):
        if self._loading:
            return
        self._cmb_device.setEnabled(self._rb_input.isChecked())
        try:
            from src.core.audio.capture import get_audio_capture
            cap = get_audio_capture()
            if self._rb_os2l.isChecked():
                # OS2L als externe Quelle: Audio-Capture als Treiber abschalten.
                self._mgr.use_audio_source(False)
                try:
                    from src.core.audio.os2l import get_os2l_server
                    get_os2l_server().start()
                except Exception as e:
                    print(f"[BpmManagerView] os2l start: {e}")
            else:
                # Wechsel auf eine Audio-Quelle: OS2L-Server (falls aktiv) stoppen,
                # damit nicht zwei AUTO-Quellen um die BPM konkurrieren.
                try:
                    from src.core.audio.os2l import get_os2l_server
                    srv = get_os2l_server()
                    if srv.is_running():
                        srv.stop()
                except Exception as e:
                    print(f"[BpmManagerView] os2l stop: {e}")
                # Neue Quelle -> alten Detektor-Zustand verwerfen (Smoothing/Beats).
                if self._det is not None:
                    self._det.reset()
                if self._rb_input.isChecked():
                    dev = self._cmb_device.currentText() or None
                    if dev and dev.startswith("("):
                        dev = None
                    cap.set_source_mode("input", dev)
                else:
                    cap.set_source_mode("loopback")
                self._mgr.use_audio_source(True)
        except Exception as e:
            print(f"[BpmManagerView] source change: {e}")
        self._source_pref = self._source_from_radios()
        self._save()

    def _on_bounds_changed(self, _v=0):
        if self._loading:
            return
        lo, hi = self._sp_min.value(), self._sp_max.value()
        self._mgr.set_bounds(lo, hi)   # spiegelt in den Detektor
        self._save()

    def _on_sens_changed(self, v: int):
        val = v / 100.0
        self._lbl_sens.setText(f"{val:.2f}")
        if self._loading:
            return
        if self._det is not None:
            self._det.set_sensitivity(val)
        self._save()

    def _on_smooth_changed(self, v: int):
        val = v / 100.0
        self._lbl_smooth.setText(f"{val:.2f}")
        if self._loading:
            return
        if self._det is not None:
            self._det.set_smoothing(val)
        self._save()

    def _on_meter_changed(self, *_):
        if self._loading:
            return
        self._mgr.set_beats_per_bar(self._sp_bpb.value())
        self._mgr.set_subdivision(int(self._cmb_subdiv.currentData() or 1))
        self._rebuild_phase_cells()
        self._save()

    def _on_bpb_preset(self, v: int):
        # Adapter statt Lambda (STAB-09); setValue selbst ist Qt-Builtin ohne __func__.
        self._sp_bpb.setValue(v)

    def _on_genre_preset(self):
        """Wendet das gewählte Genre-Preset auf die Erkennung an + zieht die UI nach."""
        key = self._cmb_genre.currentData()
        if not key:
            return
        try:
            from src.core.audio import genre_presets as gp
            p = gp.apply_to_live(key)
        except Exception as e:
            self._lbl_status.setText(f"Preset-Fehler: {e}")
            return
        # Regler ohne Save-Schleife auf die Preset-Werte nachziehen.
        self._loading = True
        try:
            self._sp_min.setValue(int(p["min_bpm"]))
            self._sp_max.setValue(int(p["max_bpm"]))
            self._sl_sens.setValue(int(round(float(p["sensitivity"]) * 100)))
            self._sl_smooth.setValue(int(round(float(p["smoothing"]) * 100)))
            self._sp_bpb.setValue(int(p["beats_per_bar"]))
        finally:
            self._loading = False
        self._rebuild_phase_cells()
        self._save()
        self._lbl_status.setText(f"Genre-Preset aktiv: {p.get('label', key)}")

    # ── BPM-Quelle (Live / Lied-Analyse / Manuell) ─────────────────────────────

    def _current_kind(self) -> str:
        if self._rb_kind_song.isChecked():
            return "song"
        if self._rb_kind_manual.isChecked():
            return "manual"
        return "live"

    def _on_kind_changed(self, *_):
        if self._loading:
            return
        self._apply_source_kind(self._current_kind())

    def _apply_source_kind(self, kind: str):
        """Schaltet die globale BPM-Quelle um (user-friendly Primär-Steuerung)."""
        self._cmb_song.setEnabled(kind == "song")
        try:
            if kind == "live":
                self._mgr.set_mode("auto")
                self._on_source_changed()          # startet Capture passend zum Eingang
            elif kind == "manual":
                self._mgr.use_audio_source(False)
                self._mgr.set_mode("manual")
                self._lbl_status.setText("Manuell — BPM per Tap/Eingabe festlegen.")
            elif kind == "song":
                self._mgr.use_audio_source(False)  # Live-Audio aus → Timeline führt
                self._mgr.set_mode("auto")
                self._populate_songs()
                self._apply_selected_song()
        except Exception as e:
            print(f"[BpmManagerView] source kind error: {e}")

    def _populate_songs(self):
        """Füllt die Auswahl mit analysierten Songs (Tracks mit bpm_timeline)."""
        self._cmb_song.blockSignals(True)
        self._cmb_song.clear()
        found = 0
        try:
            from src.core.audio.media_player import get_media_player
            for i, t in enumerate(get_media_player().tracks):
                if getattr(t, "bpm_timeline", None):
                    self._cmb_song.addItem(t.title or t.path, i)
                    found += 1
        except Exception:
            pass
        if not found:
            self._cmb_song.addItem("(kein analysierter Song — im Generator erstellen)", -1)
        self._cmb_song.blockSignals(False)

    def _on_song_changed(self, *_):
        if self._loading:
            return
        self._apply_selected_song()

    def _apply_selected_song(self):
        """Wählt den analysierten Song als aktiven Track + setzt eine statische
        Start-BPM aus der Analyse (die genaue BPM folgt beim Abspielen der Timeline)."""
        idx = self._cmb_song.currentData()
        if idx is None or idx < 0:
            self._lbl_song_info.setText("kein analysierter Song")
            return
        try:
            from src.core.audio.media_player import get_media_player
            from src.core.audio.offline_timeline import BpmTimeline
            mp = get_media_player()
            if not (0 <= idx < len(mp.tracks)):
                return
            t = mp.tracks[idx]
            mp.index = idx
            mp.trackChanged.emit(idx)
            s = BpmTimeline.from_dict(t.bpm_timeline or {}).summary()
            med = s.get("median", 0)
            self._lbl_song_info.setText(
                f"Ø {s.get('avg', 0):.0f} · Median {med:.0f} BPM · {s.get('beats', 0)} Beats "
                f"— im Musik-Tab abspielen, dann folgt die BPM dem Lied")
            if med > 0:
                self._mgr.request_bpm(float(med), "timeline")
        except Exception as e:
            print(f"[BpmManagerView] song apply error: {e}")

    def _on_phase_toggled(self, on: bool):
        if self._loading:
            return
        try:
            from src.core.audio.music_show import get_music_director
            get_music_director().set_phase_accurate(bool(on))
        except Exception as e:
            print(f"[BpmManagerView] phase toggle error: {e}")
        self._save()

    def _source_from_radios(self) -> str:
        if self._rb_input.isChecked():
            return "input"
        if self._rb_os2l.isChecked():
            return "os2l"
        return "loopback"

    def _save(self):
        """Entprellt speichern: (Neu-)Start des 400-ms-Single-Shots — aus 250
        Slider-Ticks wird EIN Schreibvorgang (BPM-07)."""
        if self._loading:
            return
        self._save_timer.start()

    def flush_pending_save(self) -> bool:
        """Schreibt eine ausstehende Aenderung SOFORT (hideEvent/closeEvent/Tests).
        True, wenn tatsaechlich geschrieben wurde."""
        if not self._save_timer.isActive():
            return False
        self._save_timer.stop()
        self._write_settings()
        return True

    def _write_settings(self):
        """Der eigentliche Schreibvorgang (v2-Keys: source/device/mode/…).
        ``device`` nur fuer den Eingang: die Combo listet ausschliesslich
        Eingaenge (``list_input_devices``), und ein Mikrofonname unter
        ``loopback`` liesse PC-Audio nach dem Neustart das Mikrofon aufnehmen
        (Live-Wechsel ruft ``set_source_mode("loopback")`` ohne Geraet)."""
        dev = self._cmb_device.currentText() or None
        if dev and dev.startswith("("):
            dev = None
        bpm_settings.save_settings({
            "source": self._source_pref,
            "device": dev if self._source_pref == "input" else None,
            "mode": "auto" if self._rb_auto.isChecked() else "manual",
            "min_bpm": self._sp_min.value(),
            "max_bpm": self._sp_max.value(),
            "beats_per_bar": self._sp_bpb.value(),
            "phase_accurate_beats": self._chk_phase.isChecked(),
        })

    # ── Sichtbarkeit: Poll-Timer nur im Vordergrund ───────────────────────────

    def showEvent(self, e):
        self._poll.start()
        self._reflect_state()
        super().showEvent(e)

    def hideEvent(self, e):
        self.flush_pending_save()
        self._poll.stop()
        super().hideEvent(e)

    def closeEvent(self, e):
        self.flush_pending_save()
        super().closeEvent(e)
