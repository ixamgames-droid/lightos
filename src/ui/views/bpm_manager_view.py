"""Sub-Tab „Erkennung" (Sektion BPM) — die Live-Erkennung auf einen Blick (BPM-09, S4).

Klassenname bleibt ``BpmManagerView`` (Smoke-Inventar tests/test_ui_smoke_enumerated.py).

**Standardansicht = genau 6 Bedienelemente** (plan.md 1.2):
(1) Quelle-Combo (PC-Audio Standard / PC-Audio je Ausgabegeraet / Eingang je
Geraet / OS2L / Lied-Analyse / Aus),
(2) grosser TAP-Knopf (Doppelrolle, ``bpm_tap_helper``), (3) Zweizustand
Auto | Manuell, (4) ×½, (5) ×2, (6) Aufklapper „Erweitert".
Anzeigen: grosse BPM-Zahl mit Pegelmeter direkt darunter (S5, ``cap.snapshot()``
im 50-ms-Timer; Anzeige, kein Bedienelement), Beat-Punkt + Taktzellen, Zustandswort
(KEIN SIGNAL / SUCHT / EINGERASTET / PAUSE · haelt N / MANUELL), Quelle-Text,
Konfidenzbalken.

**„Erweitert" = 11 Bedienelemente** (eingeklappt, Zustand nur je Sitzung):
Tempo-Bereich von/bis, „Vorlage ▾" (Genre-Bereiche), Beats/Takt, Beat-Latenz ms,
„Tempo einfrieren", Nudge −5/−1/+1/+5, „Taktgenau". Anzeigen: Diagnosezeile aus
dem Detektor-Snapshot, Spektrum.

Entfallen ersatzlos (S4): Empfindlichkeit, Glaettung, Genre-Preset + Anwenden,
Analyse-Song + ↻ (Quelle „Lied-Analyse" nimmt den aktuellen Player-Track),
Presets 4/8/16, Unterteilung, Nudge ±10, unsichtbare AUTO/MANUAL-Radios,
🔒-Knopf (jetzt „Tempo einfrieren" in Erweitert).

Datenfluss (Briefing 7c): Ereignisse des Managers (BPM/Beat/Zustand) kommen aus
Audio-/Timer-Threads und werden ueber Qt-Signale in den UI-Thread marshalled;
kontinuierliche Werte (Zustandswort, Konfidenz, Diagnose) liest ein 50-ms-Timer
aus dem unveraenderlichen ``det.snapshot()`` — NUR bei Sichtbarkeit
(showEvent/hideEvent). Kein get_bpm-Aufruf in dieser View (Grep-Test):
die Zahl kommt aus ``mgr.bpm``, alles andere aus dem Snapshot.

Quellenwechsel laufen ausschliesslich ueber ``bpm_source_controller`` (eine
Stelle, idempotent); TAP ueber ``bpm_tap_helper`` (derselbe Helfer wie der
Topbar-TAP). Manager/Detektor/Capture werden nur AUFGERUFEN.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QToolButton, QButtonGroup, QComboBox, QSpinBox, QMenu, QProgressBar,
    QScrollArea, QFrame, QCheckBox, QSizePolicy,
)

from src.core.engine.bpm_manager import get_bpm_manager, BpmMode
from src.core.audio import bpm_settings
from src.ui.bpm_source_controller import get_source_controller, AUDIO_KINDS
from src.ui.bpm_tap_helper import get_tap_helper
from src.ui.weak_slots import weak_slot
from src.ui.widgets.collapsible_section import CollapsibleSection
from src.ui.widgets.level_meter_widget import LevelMeterWidget

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
    "audio": "Audio",
    "os2l": "OS2L (extern)",
    "tap": "Tap",
    "nudge": "Nudge",
    "manual": "Eingabe",
    "file": "Datei/Player",
    "timeline": "Lied-Analyse",
    "off": "—",
}
_COL_GOLD, _COL_GREEN, _COL_GREY, _COL_AMBER = "#FFD700", "#9DFF52", "#888888", "#f0b429"
_BPM_STYLE = "font-size:56px; font-weight:bold; color:{col};"
_STATE_STYLE = "font-size:13px; font-weight:bold; color:{col};"
_SEG_STYLE = (
    "QToolButton { padding:6px 18px; font-weight:bold; border:1px solid #3d444d;"
    " border-radius:4px; background:#1b2028; color:#c9d1d9; }"
    "QToolButton:checked { background:#2f6f3a; color:#ffffff; border-color:#3fb950; }"
    "QToolButton:hover { background:#22272e; }")
_TAP_STYLE = (
    "QPushButton { font-size:18px; font-weight:bold; border:1px solid #3d444d;"
    " border-radius:6px; background:#1b2028; color:#FFD700; }"
    "QPushButton:pressed { background:#3b3200; }")
POLL_MS = 50


def state_word(mode_manual: bool, kind: str | None, snap, os2l_waiting: bool = False) -> tuple[str, str]:
    """Zustandswort + Farbe aus Manager-Modus, Quelle und Detektor-Snapshot
    (ui_diagnose 3.1). Reine Funktion — testbar ohne Qt."""
    if mode_manual:
        return "MANUELL", _COL_GREEN
    if kind in AUDIO_KINDS:
        if snap is None:
            return "KEIN SIGNAL", _COL_GREY
        st = getattr(snap, "state", "no_signal")
        if st == "locked":
            if int(getattr(snap, "hold_stage", 0)) in (1, 2):
                return f"PAUSE · hält {float(getattr(snap, 'bpm', 0.0)):.0f}", "#5fae4a"
            return "EINGERASTET", _COL_GREEN
        if st == "searching":
            return "SUCHT", _COL_AMBER
        return "KEIN SIGNAL", _COL_GREY
    if kind == "os2l":
        return ("OS2L · wartet auf DJ-Software" if os2l_waiting else "OS2L"), _COL_AMBER if os2l_waiting else _COL_GREEN
    if kind == "song":
        return "LIED-ANALYSE", _COL_GREEN
    return "AUS", _COL_GREY


def diag_line(snap) -> str:
    """Diagnosezeile aus dem Snapshot (was der Snapshot hergibt)."""
    if snap is None:
        return "kein Detektor"
    g = lambda n, d=0.0: getattr(snap, n, d)  # noqa: E731
    hint = g("tempo_hint", None)
    return (f"roh {float(g('bpm_raw')):.1f} · alt {float(g('alt_bpm')):.1f} "
            f"({float(g('alt_score')):.2f}) · Fenster {float(g('window_filled_s')):.1f}/"
            f"{float(g('window_s')):.0f} s · Pegel {float(g('level_rms_dbfs', -100.0)):.0f} dBFS · "
            f"Rauschteppich {float(g('noise_floor_dbfs', -100.0)):.0f} dBFS · "
            f"Brumm {int(g('hum_hz', 0))} Hz {float(g('hum_ratio')) * 100:.0f} % · "
            f"DC {float(g('dc_offset')):.3f} · Jitter {float(g('jitter_ms')):.0f} ms · "
            f"Rückstand {float(g('backlog_ms')):.0f} ms · Kontrast {float(g('onset_contrast')):.1f}"
            + (f" · Hinweis {float(hint):.0f}" if hint else ""))


class _SourceCombo(QComboBox):
    """Quelle-Combo: liest die Geraeteliste beim Oeffnen neu (ersetzt „Geraete neu lesen")."""

    def __init__(self, on_popup=None, parent=None):
        super().__init__(parent)
        self._on_popup = on_popup

    def showPopup(self):
        if self._on_popup is not None:
            try:
                self._on_popup()
            except Exception as e:
                print(f"[BpmManagerView] Quellenliste: {e}")
        super().showPopup()


class BpmManagerView(QWidget):
    """Sub-Tab „Erkennung": 6 Bedienelemente + Erweitert."""

    _bpm_sig = Signal(float)
    _beat_sig = Signal(int)
    _state_sig = Signal()

    def __init__(self, parent=None, source_controller=None, tap_helper=None):
        super().__init__(parent)
        self._mgr = get_bpm_manager()
        self._det = get_beat_detector() if get_beat_detector else None
        self._src = source_controller if source_controller is not None else get_source_controller()
        self._tap = tap_helper if tap_helper is not None else get_tap_helper()
        self._loading = True            # unterdrueckt Save/Backend waehrend Init
        self._beat_phase = 0
        # Entprellung (BPM-07): gesammelt wird EIN Schreibvorgang 400 ms nach dem
        # letzten Tick; hideEvent/closeEvent schreiben Ausstehendes sofort.
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._write_settings)
        self._source_pref = bpm_settings.DEFAULTS["source"]
        self._device_pref: str | None = None

        self._build_ui()
        self._load_into_controls()
        self._wire_backend()
        self._loading = False

        # Snapshot-Poll (Zustandswort/Konfidenz/Diagnose) — nur bei Sichtbarkeit.
        self._poll = QTimer(self)
        self._poll.setInterval(POLL_MS)
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
        root.setSpacing(10)

        root.addLayout(self._build_head())
        root.addLayout(self._build_buttons())
        self._lbl_status = QLabel("")
        self._lbl_status.setStyleSheet("color:#f0883e;")
        self._lbl_status.setWordWrap(True)
        root.addWidget(self._lbl_status)
        root.addWidget(self._build_advanced())
        root.addStretch(1)

    def _build_head(self) -> QHBoxLayout:
        """Grosse BPM-Zahl links; rechts Quelle, Beat-Punkt + Takt + Zustandswort, Konfidenz."""
        top = QHBoxLayout()
        top.setSpacing(16)
        self._lbl_bpm = QLabel("--")
        self._lbl_bpm.setStyleSheet(_BPM_STYLE.format(col=_COL_GREY))
        self._lbl_bpm.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_bpm.setMinimumWidth(170)
        self._lbl_bpm.setToolTip("Aktuelles Tempo des BPM-Managers (gelb = Auto, grün = Manuell, grau = kein Tempo).")
        bpm_col = QVBoxLayout()
        bpm_col.addWidget(self._lbl_bpm)
        unit = QLabel("BPM")
        unit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        unit.setStyleSheet("color:#8b949e; font-weight:bold;")
        bpm_col.addWidget(unit)
        # Pegelmeter direkt unter der BPM-Zahl (BPM-10): reine Anzeige aus cap.snapshot()
        self._level = LevelMeterWidget()
        bpm_col.addWidget(self._level)
        top.addLayout(bpm_col)

        col = QVBoxLayout()
        col.setSpacing(6)
        # (1) Quelle
        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("Quelle"))
        self._cmb_source = _SourceCombo(on_popup=self._populate_sources)
        self._cmb_source.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._cmb_source.setToolTip(
            "Woher das Tempo kommt: PC-Audio (mithören, was der Rechner abspielt), "
            "Eingang (Mikrofon/Line-In je Gerät), OS2L (DJ-Software wie VirtualDJ), "
            "Lied-Analyse (analysierter Titel im Player) oder Aus. Die Liste wird beim Öffnen neu gelesen.")
        self._cmb_source.currentIndexChanged.connect(self._on_source_changed)
        # ``activated`` auch fuer den SELBEN Eintrag: „erneut verbinden" nach
        # einem Capture-Fehler; der Controller ist idempotent, ein Wechsel
        # loest ueber beide Signale also nur EINEN Schaltvorgang aus.
        self._cmb_source.activated.connect(self._on_source_changed)
        src_row.addWidget(self._cmb_source, 1)
        col.addLayout(src_row)

        # Beat-Punkt + Taktzellen + Zustandswort + Quelle-Text
        beat_row = QHBoxLayout()
        self._dot = QLabel(" ")
        self._dot.setFixedSize(26, 26)
        self._dot.setStyleSheet(_DOT_IDLE)
        self._dot.setToolTip("Blinkt auf jedem Beat (gold = Takt 1).")
        beat_row.addWidget(self._dot)
        self._dot_timer = QTimer(self)
        self._dot_timer.setInterval(110)
        self._dot_timer.setSingleShot(True)
        self._dot_timer.timeout.connect(self._on_dot_idle)
        self._phase_cells_host = QWidget()
        self._phase_row = QHBoxLayout(self._phase_cells_host)
        self._phase_row.setContentsMargins(0, 0, 0, 0)
        self._phase_row.setSpacing(4)
        beat_row.addWidget(self._phase_cells_host)
        self._phase_pos = QLabel("")
        self._phase_pos.setStyleSheet("color:#888;")
        beat_row.addWidget(self._phase_pos)
        beat_row.addSpacing(10)
        self._lbl_state = QLabel("KEIN SIGNAL")
        self._lbl_state.setStyleSheet(_STATE_STYLE.format(col=_COL_GREY))
        self._lbl_state.setToolTip(
            "Zustand der Erkennung: KEIN SIGNAL (nichts zu hören), SUCHT (Fenster füllt sich), "
            "EINGERASTET (Beats laufen), PAUSE · hält N (Stille, Tempo wird gehalten), MANUELL.")
        beat_row.addWidget(self._lbl_state)
        self._lbl_source = QLabel("· —")
        self._lbl_source.setStyleSheet("color:#8b949e;")
        beat_row.addWidget(self._lbl_source)
        beat_row.addStretch(1)
        col.addLayout(beat_row)
        self._phase_lbls: list[QLabel] = []
        self._rebuild_phase_cells()

        # Konfidenz
        conf = QHBoxLayout()
        conf.addWidget(QLabel("Konfidenz"))
        self._conf = QProgressBar()
        self._conf.setRange(0, 100)
        self._conf.setValue(0)
        self._conf.setTextVisible(True)
        self._conf.setFixedHeight(16)
        self._conf.setToolTip("Wie sicher die Erkennung ist (Periodizität × Beat-Kontrast, 0–100 %).")
        # sichtbare Kontur auch bei 0 % (UI-24c)
        self._conf.setStyleSheet(
            "QProgressBar { border: 1px solid #3d444d; border-radius: 3px; "
            "background: #161b22; text-align: center; color: #e6edf3; } "
            "QProgressBar::chunk { background: #3fb950; border-radius: 2px; }")
        conf.addWidget(self._conf, 1)
        col.addLayout(conf)
        top.addLayout(col, 1)
        return top

    def _build_buttons(self) -> QHBoxLayout:
        """(2) TAP · (3) Auto | Manuell · (4) ×½ · (5) ×2."""
        row = QHBoxLayout()
        row.setSpacing(14)
        self._btn_tap = QPushButton("TAP")
        self._btn_tap.setFixedSize(120, 48)
        self._btn_tap.setStyleSheet(_TAP_STYLE)
        self._btn_tap.setToolTip(
            "Einmal tippen = Beat-Punkt auf „jetzt“ setzen (Tempo bleibt). "
            "Viermal im Takt tippen = Tempo setzen; ab dem dritten Tipp sucht die Erkennung um dieses Tempo.")
        self._btn_tap.clicked.connect(self._on_tap)
        row.addWidget(self._btn_tap)

        seg = QHBoxLayout()
        seg.setSpacing(0)
        self._btn_auto = QToolButton()
        self._btn_auto.setText("Auto")
        self._btn_manual = QToolButton()
        self._btn_manual.setText("Manuell")
        for b in (self._btn_auto, self._btn_manual):
            b.setCheckable(True)
            b.setStyleSheet(_SEG_STYLE)
            b.setFixedHeight(36)
            b.setMinimumWidth(90)
        self._btn_auto.setToolTip("Auto: das Tempo folgt der gewählten Quelle (Audio, OS2L, Lied-Analyse).")
        self._btn_manual.setToolTip("Manuell: das Tempo bleibt, wie du es per TAP oder Nudge setzt — die Quelle ändert es nicht.")
        self._mode_grp = QButtonGroup(self)
        self._mode_grp.setExclusive(True)
        self._mode_grp.addButton(self._btn_auto)
        self._mode_grp.addButton(self._btn_manual)
        self._btn_auto.toggled.connect(self._on_auto_toggled)
        seg.addWidget(self._btn_auto)
        seg.addWidget(self._btn_manual)
        row.addLayout(seg)

        self._btn_half = QToolButton()
        self._btn_half.setText("×½")
        self._btn_double = QToolButton()
        self._btn_double.setText("×2")
        for b in (self._btn_half, self._btn_double):
            b.setStyleSheet(_SEG_STYLE)
            b.setFixedSize(56, 36)
        self._btn_half.setToolTip(
            "Halbes Tempo: läuft das Licht doppelt so schnell wie die Musik, einmal klicken. "
            "In Auto zwingt das die Erkennung auf die halbe Oktave, in Manuell halbiert es dein Tempo.")
        self._btn_double.setToolTip(
            "Doppeltes Tempo: läuft das Licht halb so schnell wie die Musik, einmal klicken. "
            "In Auto zwingt das die Erkennung auf die doppelte Oktave, in Manuell verdoppelt es dein Tempo. "
            "Tipp: ein enger Tempo-Bereich (Erweitert) verhindert den Fehler dauerhaft.")
        self._btn_half.clicked.connect(self._on_half)
        self._btn_double.clicked.connect(self._on_double)
        row.addWidget(self._btn_half)
        row.addWidget(self._btn_double)
        row.addStretch(1)
        return row

    def _build_advanced(self) -> CollapsibleSection:
        """(6) Aufklapper „Erweitert" mit 11 Bedienelementen + Diagnose/Spektrum."""
        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(8, 6, 8, 6)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        r = 0

        # Tempo-Bereich von/bis + Vorlage + Beats/Takt
        grid.addWidget(QLabel("Tempo-Bereich"), r, 0)
        rng = QHBoxLayout()
        rng.addWidget(QLabel("von"))
        self._sp_min = QSpinBox()
        self._sp_min.setRange(20, 400)
        self._sp_min.setToolTip("Untergrenze der Erkennung in BPM. Eng gesetzt (z. B. 120–180) verhindert Halb-/Doppeltempo-Fehler.")
        self._sp_min.valueChanged.connect(self._on_bounds_changed)
        rng.addWidget(self._sp_min)
        rng.addWidget(QLabel("bis"))
        self._sp_max = QSpinBox()
        self._sp_max.setRange(20, 400)
        self._sp_max.setToolTip("Obergrenze der Erkennung in BPM.")
        self._sp_max.valueChanged.connect(self._on_bounds_changed)
        rng.addWidget(self._sp_max)
        rng.addWidget(QLabel("BPM"))
        rng.addSpacing(8)
        self._btn_preset = QToolButton()
        self._btn_preset.setText("Vorlage ▾")
        self._btn_preset.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._btn_preset.setToolTip("Tempo-Bereich und Beats/Takt nach Musikstil vorbelegen (House, Techno, Hardstyle …). Setzt nur diese beiden Werte.")
        self._preset_menu = QMenu(self._btn_preset)
        try:
            from src.core.audio import genre_presets as _gp
            for _k in _gp.ORDER:
                p = _gp.get(_k)
                act = QAction(f"{_gp.label(_k)}  ({p['min_bpm']}–{p['max_bpm']})", self._preset_menu)
                act.setData(_k)
                act.triggered.connect(weak_slot(self._on_preset, _k))
                self._preset_menu.addAction(act)
        except Exception as e:
            print(f"[BpmManagerView] Vorlagen: {e}")
        self._btn_preset.setMenu(self._preset_menu)
        rng.addWidget(self._btn_preset)
        rng.addSpacing(16)
        rng.addWidget(QLabel("Beats/Takt"))
        self._sp_bpb = QSpinBox()
        self._sp_bpb.setRange(1, 32)
        self._sp_bpb.setToolTip("Schläge pro Takt — Takt-1-Akzent alle N Beats (4 = Viertakt, 16 = Sechzehntakt). Ändert nicht die Beat-Rate.")
        self._sp_bpb.valueChanged.connect(self._on_meter_changed)
        rng.addWidget(self._sp_bpb)
        rng.addStretch(1)
        grid.addLayout(rng, r, 1)
        r += 1

        # Beat-Latenz
        grid.addWidget(QLabel("Beat-Latenz"), r, 0)
        lat = QHBoxLayout()
        self._sp_latency = QSpinBox()
        self._sp_latency.setRange(-300, 300)
        self._sp_latency.setSingleStep(5)
        self._sp_latency.setSuffix(" ms")
        self._sp_latency.setToolTip("Beats früher (+) oder später (−) melden, in Millisekunden — gleicht Laufzeit von Audio-Weg und Lichtausgabe aus.")
        self._sp_latency.valueChanged.connect(self._on_latency_changed)
        lat.addWidget(self._sp_latency)
        hint = QLabel("+ = Licht früher, − = später")
        hint.setStyleSheet("color:#8b949e;")
        lat.addWidget(hint)
        lat.addStretch(1)
        grid.addLayout(lat, r, 1)
        r += 1

        # Tempo einfrieren
        grid.addWidget(QLabel("Tempo halten"), r, 0)
        lock_row = QHBoxLayout()
        self._btn_lock = QPushButton("🔒 Tempo einfrieren")
        self._btn_lock.setCheckable(True)
        self._btn_lock.setToolTip("Friert das Tempo ein: keine Quelle ändert es, bis du es wieder löst. Beats laufen weiter.")
        self._btn_lock.toggled.connect(self._on_lock_toggled)
        lock_row.addWidget(self._btn_lock)
        lock_row.addStretch(1)
        grid.addLayout(lock_row, r, 1)
        r += 1

        # Nudge
        grid.addWidget(QLabel("Nudge"), r, 0)
        nudge = QHBoxLayout()
        self._btn_nudge: dict[int, QPushButton] = {}
        for delta in (-5, -1, +1, +5):
            b = QPushButton(f"{delta:+d}")
            b.setFixedWidth(48)
            b.setToolTip(f"Tempo um {abs(delta)} BPM {'senken' if delta < 0 else 'anheben'} (schaltet auf Manuell).")
            b.clicked.connect(weak_slot(self._mgr.nudge, delta))
            nudge.addWidget(b)
            self._btn_nudge[delta] = b
        nudge.addStretch(1)
        grid.addLayout(nudge, r, 1)
        r += 1

        # Taktgenau (Lied-Analyse)
        grid.addWidget(QLabel("Lied-Analyse"), r, 0)
        ph = QHBoxLayout()
        self._chk_phase = QCheckBox("Taktgenau")
        self._chk_phase.setChecked(True)
        self._chk_phase.setToolTip("Beats treffen exakt das Beatgrid des analysierten Lieds (statt nur den BPM-Wert). Wirkt nur bei Quelle „Lied-Analyse“.")
        self._chk_phase.toggled.connect(self._on_phase_toggled)
        ph.addWidget(self._chk_phase)
        ph.addStretch(1)
        grid.addLayout(ph, r, 1)
        r += 1

        # Diagnosezeile (Anzeige)
        grid.addWidget(QLabel("Diagnose"), r, 0)
        self._lbl_diag = QLabel("")
        self._lbl_diag.setStyleSheet("color:#8b949e; font-size:11px;")
        self._lbl_diag.setWordWrap(True)
        self._lbl_diag.setToolTip("Rohwerte des Detektors: Roh-Tempo, Alternativ-Oktave, Fensterfüllung, Pegel, Rauschteppich, Brumm, Jitter, Rückstand.")
        grid.addWidget(self._lbl_diag, r, 1)
        r += 1

        # Spektrum (Anzeige)
        if SpectrumBars is not None:
            grid.addWidget(QLabel("Spektrum"), r, 0)
            self._spectrum = SpectrumBars()
            grid.addWidget(self._spectrum, r, 1)
        else:
            self._spectrum = None
        grid.setColumnStretch(1, 1)

        self._advanced = CollapsibleSection("Erweitert", content, collapsed=True)
        btn = getattr(self._advanced, "_btn", None)
        if btn is not None:
            btn.setToolTip("Tempo-Bereich, Vorlage, Beats/Takt, Beat-Latenz, Tempo einfrieren, Nudge, Taktgenau, Diagnose.")
        return self._advanced

    def _on_dot_idle(self):
        # Bound-Method-Slot statt Lambda (STAB-09).
        self._dot.setStyleSheet(_DOT_IDLE)

    @staticmethod
    def _phase_style(active: bool, accent: bool) -> str:
        if active:
            col = _COL_GOLD if accent else _COL_GREEN
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
            pl.setFixedSize(22, 20)
            pl.setStyleSheet(self._phase_style(False, i == 0))
            self._phase_row.addWidget(pl)
            self._phase_lbls.append(pl)

    # ── Quelle-Combo ──────────────────────────────────────────────────────────

    @staticmethod
    def _list_inputs() -> list[str]:
        try:
            from src.core.audio.capture import get_audio_capture
            return list(type(get_audio_capture()).list_input_devices() or [])
        except Exception:
            return []

    @staticmethod
    def _list_sinks() -> list[tuple[str, str]]:
        try:
            from src.core.audio.capture import get_audio_capture
            return [(str(i), str(n)) for i, n in (type(get_audio_capture()).list_loopback_sinks() or [])]
        except Exception:
            return []

    def _populate_sources(self, keep: str | None = None):
        """Eintraege: PC-Audio (Standard-Ausgabegeraet), PC-Audio je Ausgabegeraet
        (Daten ``loopback:<sink_id>``, S5), Eingang je Geraet, OS2L, Lied-Analyse,
        Aus. Ein gespeichertes, nicht vorhandenes Geraet bleibt als
        „(nicht gefunden)" waehlbar."""
        cur = keep if keep is not None else (self._cmb_source.currentData() or "")
        was_loading = self._loading
        self._loading = True
        self._cmb_source.blockSignals(True)
        try:
            self._cmb_source.clear()
            self._cmb_source.addItem("PC-Audio", "loopback")
            sinks = self._list_sinks()
            for sid, name in sinks:
                self._cmb_source.addItem(f"PC-Audio: {name}", f"loopback:{sid}")
            if cur.startswith("loopback:") and cur[9:] not in {sid for sid, _ in sinks}:
                self._cmb_source.addItem(f"PC-Audio: {cur[9:]} (nicht gefunden)", cur)
            devs = self._list_inputs()
            for d in devs:
                self._cmb_source.addItem(f"Eingang: {d}", f"input:{d}")
            if cur.startswith("input:") and cur[6:] not in devs:
                self._cmb_source.addItem(f"Eingang: {cur[6:]} (nicht gefunden)", cur)
            self._cmb_source.addItem("OS2L (DJ-Software)", "os2l")
            self._cmb_source.addItem("Lied-Analyse (Player)", "song")
            self._cmb_source.addItem("Aus", "off")
            idx = self._cmb_source.findData(cur) if cur else -1
            self._cmb_source.setCurrentIndex(idx if idx >= 0 else 0)
        finally:
            self._cmb_source.blockSignals(False)
            self._loading = was_loading

    @staticmethod
    def _parse_source(data) -> tuple[str, str | None]:
        s = str(data or "loopback")
        if s.startswith("input:"):
            return "input", (s[6:] or None)
        if s.startswith("loopback:"):
            return "loopback", (s[9:] or None)
        return s, None

    def _on_source_changed(self, *_):
        if self._loading:
            return
        kind, dev = self._parse_source(self._cmb_source.currentData())
        self._src.apply(kind, dev)
        self._source_pref, self._device_pref = kind, dev
        self._reflect_state()
        self._save()

    # ── Init-Werte ────────────────────────────────────────────────────────────

    def _load_into_controls(self):
        """Regler aus dem BACKEND-Zustand fuellen (Manager/Detektor/Director);
        ``bpm_settings.boot()`` hat die Datei beim Start bereits angewandt. Nur
        Quelle und Geraet kommen aus den Prefs (Capture kann gestoppt/``off`` sein)."""
        D = bpm_settings.DEFAULTS
        mgr = self._mgr
        self._sp_min.setValue(int(mgr.min_bpm))
        self._sp_max.setValue(int(mgr.max_bpm))
        self._sp_bpb.setValue(int(mgr.beats_per_bar))
        self._sp_latency.setValue(int(getattr(self._det, "beat_latency_ms", D["beat_latency_ms"]) or 0))
        try:
            from src.core.audio.music_show import get_music_director
            pa = bool(get_music_director().is_phase_accurate())
        except Exception:
            pa = D["phase_accurate_beats"]
        self._chk_phase.setChecked(pa)

        s = bpm_settings.load_settings()
        self._source_pref = s["source"]
        self._device_pref = s["device"] if s["source"] in AUDIO_KINDS else None
        key = (f"{self._source_pref}:{self._device_pref}"
               if (self._source_pref in AUDIO_KINDS and self._device_pref) else self._source_pref)
        self._populate_sources(keep=key)
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

    def _bpm_color(self, bpm: float) -> str:
        if not bpm or bpm <= 0:
            return _COL_GREY
        return _COL_GREEN if self._mgr.mode == BpmMode.MANUAL else _COL_GOLD

    def _on_bpm(self, bpm: float):
        self._lbl_bpm.setText(f"{bpm:.1f}" if bpm and bpm > 0 else "--")
        self._lbl_bpm.setStyleSheet(_BPM_STYLE.format(col=self._bpm_color(bpm)))

    def _on_beat(self, idx: int):
        bpb = max(1, int(self._mgr.beats_per_bar))
        self._beat_phase = idx % bpb
        accent = (self._beat_phase == 0)
        col = _COL_GOLD if accent else _COL_GREEN
        self._dot.setStyleSheet(
            f"background:{col}; border:1px solid {col}; border-radius:13px;")
        self._dot_timer.start()
        for i, pl in enumerate(self._phase_lbls):
            pl.setStyleSheet(self._phase_style(i == self._beat_phase, i == 0))
        if bpb > len(self._phase_lbls):
            self._phase_pos.setText(f"{self._beat_phase + 1} / {bpb}")
        else:
            self._phase_pos.setText("")

    def _reflect_state(self):
        """Modus/Quelle/Lock aus dem Manager in die UI spiegeln (ohne Rueckschreiben)."""
        was = self._loading
        self._loading = True
        try:
            is_auto = (self._mgr.mode == BpmMode.AUTO)
            self._btn_auto.setChecked(is_auto)
            self._btn_manual.setChecked(not is_auto)
            self._btn_lock.setChecked(self._mgr.is_locked)
            src = self._mgr.current_source
            lock = " · 🔒" if self._mgr.is_locked else ""
            self._lbl_source.setText(f"· {_SRC_LABELS.get(src, src)}{lock}")
            self._on_bpm(self._mgr.bpm)
        finally:
            self._loading = was

    def _snapshot(self):
        if self._det is None:
            return None
        try:
            return self._det.snapshot()
        except Exception:
            return None

    def _refresh_monitor(self):
        """50-ms-Poll: Zustandswort, Konfidenz, Diagnose, Capture-Fehler."""
        snap = self._snapshot()
        kind = self._src.kind or self._source_pref
        waiting = False
        if kind == "os2l":
            try:
                from src.core.audio.os2l import get_os2l_server
                srv = get_os2l_server()
                waiting = bool(srv.is_running()) and float(srv.last_bpm() or 0) <= 0
            except Exception:
                waiting = False
        word, col = state_word(self._mgr.mode == BpmMode.MANUAL, kind, snap, waiting)
        if self._lbl_state.text() != word:
            self._lbl_state.setText(word)
            self._lbl_state.setStyleSheet(_STATE_STYLE.format(col=col))
        c = int(round(float(getattr(snap, "confidence", 0.0) or 0.0) * 100)) if snap is not None else 0
        self._conf.setValue(max(0, min(100, c)))
        if self._advanced.is_expanded():
            self._lbl_diag.setText(diag_line(snap))
        try:
            from src.core.audio.capture import get_audio_capture
            cap = get_audio_capture()
            err = cap.last_error()
            self._lbl_status.setText(f"⚠ {err}" if err and kind in AUDIO_KINDS else "")
            self._level.set_snapshot(cap.snapshot() if kind in AUDIO_KINDS else None)
        except Exception:
            self._lbl_status.setText("")
            self._level.set_snapshot(None)

    # ── Bedien-Handler ────────────────────────────────────────────────────────

    def _on_tap(self):
        self._tap.tap()

    def _on_auto_toggled(self, checked: bool):
        if self._loading:
            return
        self._src.set_auto(bool(checked))
        self._reflect_state()
        self._save()

    def _on_half(self):
        self._src.octave(-1)

    def _on_double(self):
        self._src.octave(+1)

    def _on_lock_toggled(self, checked: bool):
        if self._loading:
            return
        self._mgr.set_locked(bool(checked))

    def _on_bounds_changed(self, _v=0):
        if self._loading:
            return
        self._mgr.set_bounds(self._sp_min.value(), self._sp_max.value())   # spiegelt in den Detektor
        self._save()

    def _on_meter_changed(self, *_):
        if self._loading:
            return
        self._mgr.set_beats_per_bar(self._sp_bpb.value())
        self._rebuild_phase_cells()
        self._save()

    def _on_latency_changed(self, v: int):
        if self._loading:
            return
        if self._det is not None:
            try:
                self._det.set_beat_latency_ms(int(v))
            except Exception as e:
                print(f"[BpmManagerView] set_beat_latency_ms: {e}")
        self._save()

    def _on_preset(self, key: str):
        """„Vorlage ▾": setzt NUR Tempo-Bereich + Beats/Takt (genre_presets.apply_to_live)."""
        try:
            from src.core.audio import genre_presets as gp
            p = gp.apply_to_live(key)
        except Exception as e:
            self._lbl_status.setText(f"Vorlage-Fehler: {e}")
            return
        self._loading = True
        try:
            self._sp_min.setValue(int(p["min_bpm"]))
            self._sp_max.setValue(int(p["max_bpm"]))
            self._sp_bpb.setValue(int(p["beats_per_bar"]))
        finally:
            self._loading = False
        self._rebuild_phase_cells()
        self._save()

    def _on_phase_toggled(self, on: bool):
        if self._loading:
            return
        try:
            from src.core.audio.music_show import get_music_director
            get_music_director().set_phase_accurate(bool(on))
        except Exception as e:
            print(f"[BpmManagerView] phase toggle error: {e}")
        self._save()

    # ── Persistenz (v3) ───────────────────────────────────────────────────────

    def _save(self):
        """Entprellt speichern: (Neu-)Start des 400-ms-Single-Shots (BPM-07)."""
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
        """Der eigentliche Schreibvorgang (v3-Keys). ``device`` = Eingangsname bzw.
        bei PC-Audio die ``sink_id`` eines Ausgabegeraets (None = Standard)."""
        bpm_settings.save_settings({
            "source": self._source_pref,
            "device": self._device_pref if self._source_pref in AUDIO_KINDS else None,
            "mode": "auto" if self._btn_auto.isChecked() else "manual",
            "min_bpm": self._sp_min.value(),
            "max_bpm": self._sp_max.value(),
            "beats_per_bar": self._sp_bpb.value(),
            "phase_accurate_beats": self._chk_phase.isChecked(),
            "beat_latency_ms": self._sp_latency.value(),
        })

    # ── Sichtbarkeit: Poll-Timer nur im Vordergrund ───────────────────────────

    def showEvent(self, e):
        self._poll.start()
        self._reflect_state()
        self._refresh_monitor()
        super().showEvent(e)

    def hideEvent(self, e):
        self.flush_pending_save()
        self._poll.stop()
        super().hideEvent(e)

    def closeEvent(self, e):
        self.flush_pending_save()
        super().closeEvent(e)
