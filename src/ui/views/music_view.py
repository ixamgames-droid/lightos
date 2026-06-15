"""Music View — In-App-Musik-Player (Tab „Musik").

Spielt die Lieder der Show-Playlist ab (MP3/MP4/…) und zeigt aktuelles/nächstes Lied.
Steuert den globalen MediaPlayer (src/core/audio/media_player.py).

BPM: Die genaue Taktung kommt im Betrieb von VirtualDJ → OS2L (Menü Ausgabe →
OS2L-Server). „BPM koppeln" setzt nur eine grobe Nominal-BPM pro Lied als Fallback.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QSlider, QCheckBox, QFileDialog,
    QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt

from src.core.audio.media_player import get_media_player


def _fmt_time(ms: int) -> str:
    s = max(0, int(ms // 1000))
    return f"{s // 60}:{s % 60:02d}"


class MusicView(QWidget):
    """Playlist + Transport für den In-App-Player."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mp = get_media_player()
        self._setup_ui()
        self._connect()
        self._rebuild_table()
        self._refresh_now_playing()

    # ── UI ────────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)

        # Kopf / Hinweis
        hint = QLabel(
            "🎵 In-App-Player — spielt die Playlist der Show. Doppelklick auf ein Lied = abspielen.\n"
            "Für taktgenaue Lichteffekte: VirtualDJ starten und OS2L senden lassen "
            "(Menü „Ausgabe → OS2L-Server starten“)."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#9aa4ad;")
        root.addWidget(hint)

        # Playlist-Tabelle
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["", "Titel", "Genre", "BPM"])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setColumnWidth(0, 28)
        self._table.doubleClicked.connect(self._on_double_click)
        root.addWidget(self._table, 1)

        # Now Playing
        self._lbl_now = QLabel("—")
        self._lbl_now.setStyleSheet("font-size:14px; font-weight:bold; color:#e8e8e8;")
        self._lbl_next = QLabel("Als Nächstes: —")
        self._lbl_next.setStyleSheet("color:#9aa4ad;")
        np_box = QGroupBox("Now Playing")
        np_lay = QVBoxLayout(np_box)
        np_lay.addWidget(self._lbl_now)
        np_lay.addWidget(self._lbl_next)
        root.addWidget(np_box)

        # Positions-Slider + Zeit
        pos_row = QHBoxLayout()
        self._lbl_pos = QLabel("0:00")
        self._pos = QSlider(Qt.Orientation.Horizontal)
        self._pos.setRange(0, 1000)
        self._pos.sliderMoved.connect(self._on_seek)
        self._lbl_dur = QLabel("0:00")
        pos_row.addWidget(self._lbl_pos)
        pos_row.addWidget(self._pos, 1)
        pos_row.addWidget(self._lbl_dur)
        root.addLayout(pos_row)

        # Transport
        tr = QHBoxLayout()
        self._btn_prev = QPushButton("⏮")
        self._btn_play = QPushButton("▶")
        self._btn_next = QPushButton("⏭")
        self._btn_stop = QPushButton("⏹")
        for b in (self._btn_prev, self._btn_play, self._btn_next, self._btn_stop):
            b.setMinimumHeight(36)
            b.setStyleSheet("font-size:16px;")
        self._btn_prev.clicked.connect(self._mp.prev)
        self._btn_play.clicked.connect(self._mp.toggle)
        self._btn_next.clicked.connect(self._mp.next)
        self._btn_stop.clicked.connect(self._mp.stop)
        tr.addWidget(self._btn_prev)
        tr.addWidget(self._btn_play)
        tr.addWidget(self._btn_next)
        tr.addWidget(self._btn_stop)
        tr.addSpacing(20)
        tr.addWidget(QLabel("🔊"))
        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setRange(0, 100)
        self._vol.setValue(self._mp.volume())
        self._vol.setMaximumWidth(160)
        self._vol.valueChanged.connect(self._mp.set_volume)
        tr.addWidget(self._vol)
        tr.addStretch(1)
        root.addLayout(tr)

        # Auto-Lichtshow an die Musik koppeln
        self._chk_autoshow = QCheckBox(
            "🎬 Lichtshow automatisch zur Musik starten "
            "(startet beim ▶ die Auto-Show der Show, taktet zur BPM)"
        )
        self._chk_autoshow.setChecked(self._autoshow_enabled())
        self._chk_autoshow.toggled.connect(self._on_autoshow)
        root.addWidget(self._chk_autoshow)

        # Optionen
        opt = QHBoxLayout()
        self._chk_couple = QCheckBox("BPM koppeln (grobe Nominal-BPM als Fallback)")
        self._chk_couple.setChecked(self._mp.couple_bpm)
        self._chk_couple.toggled.connect(self._on_couple)
        opt.addWidget(self._chk_couple)
        opt.addStretch(1)
        btn_folder = QPushButton("Ordner laden…")
        btn_folder.clicked.connect(self._on_load_folder)
        opt.addWidget(btn_folder)
        root.addLayout(opt)

    # ── Signale ───────────────────────────────────────────────────────────────────

    def _connect(self):
        self._mp.trackChanged.connect(self._on_track_changed)
        self._mp.playlistChanged.connect(self._rebuild_table)
        self._mp.playingChanged.connect(self._on_playing_changed)
        self._mp.positionChanged.connect(self._on_position)

    def _on_couple(self, on: bool):
        self._mp.couple_bpm = bool(on)

    # ── Auto-Lichtshow-Kopplung ──────────────────────────────────────────────────
    @staticmethod
    def _autoshow_cfg() -> dict | None:
        try:
            from src.core.app_state import get_state
            st = get_state()
            cfg = getattr(st, "music_autoshow", None)
            if not isinstance(cfg, dict):
                cfg = {"enabled": False, "function_ids": [], "bank": 0}
                st.music_autoshow = cfg
            return cfg
        except Exception:
            return None

    def _autoshow_enabled(self) -> bool:
        cfg = self._autoshow_cfg()
        return bool(cfg.get("enabled", False)) if cfg else False

    def _on_autoshow(self, on: bool):
        cfg = self._autoshow_cfg()
        if cfg is not None:
            cfg["enabled"] = bool(on)

    def _on_double_click(self, index):
        self._mp.play_index(index.row())

    def _on_seek(self, value: int):
        # Slider 0..1000 -> ms (relativ zur Dauer)
        dur = self._dur_ms
        if dur > 0:
            self._mp.seek(int(value / 1000.0 * dur))

    def _on_load_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Musik-Ordner laden")
        if folder:
            self._mp.load_folder(folder)
            try:
                from src.core.app_state import get_state
                get_state().playlist = self._mp.to_dicts()
            except Exception:
                pass

    # ── Anzeige-Updates ─────────────────────────────────────────────────────────────

    def _rebuild_table(self):
        self._table.setRowCount(0)
        for t in self._mp.tracks:
            r = self._table.rowCount()
            self._table.insertRow(r)
            self._table.setItem(r, 0, QTableWidgetItem(""))
            self._table.setItem(r, 1, QTableWidgetItem(t.title))
            self._table.setItem(r, 2, QTableWidgetItem(t.genre))
            bpm = f"{t.bpm:.0f}" if t.bpm else "—"
            self._table.setItem(r, 3, QTableWidgetItem(bpm))
        self._mark_current_row()
        self._refresh_now_playing()
        # Auto-Show-Schalter an die (ggf. frisch geladene) Show angleichen.
        if hasattr(self, "_chk_autoshow"):
            self._chk_autoshow.blockSignals(True)
            self._chk_autoshow.setChecked(self._autoshow_enabled())
            self._chk_autoshow.blockSignals(False)

    def _mark_current_row(self):
        idx = self._mp.index
        for r in range(self._table.rowCount()):
            item = self._table.item(r, 0)
            if item is not None:
                item.setText("▶" if r == idx else "")

    def _on_track_changed(self, _idx: int):
        self._mark_current_row()
        self._refresh_now_playing()

    def _on_playing_changed(self, playing: bool):
        self._btn_play.setText("⏸" if playing else "▶")
        self._refresh_now_playing()

    def _refresh_now_playing(self):
        cur = self._mp.current_track
        nxt = self._mp.next_track
        if cur is not None:
            bpm = f"  ·  {cur.bpm:.0f} BPM" if cur.bpm else ""
            icon = "▶" if self._mp.is_playing else "⏸"
            self._lbl_now.setText(f"{icon} {cur.title}{bpm}")
        else:
            self._lbl_now.setText("— (keine Playlist geladen)")
        self._lbl_next.setText(f"Als Nächstes: {nxt.title}" if nxt is not None else "Als Nächstes: —")

    _dur_ms = 0

    def _on_position(self, pos: int, dur: int):
        self._dur_ms = dur
        self._lbl_pos.setText(_fmt_time(pos))
        self._lbl_dur.setText(_fmt_time(dur))
        if dur > 0 and not self._pos.isSliderDown():
            self._pos.setValue(int(pos / dur * 1000))
