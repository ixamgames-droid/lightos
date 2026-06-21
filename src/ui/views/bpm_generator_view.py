"""BPM-Generator-Tab — ganzes Lied analysieren → BPM-Kurve + echtes Beatgrid.

Workflow: Datei wählen → Genre + Analyse-Engine wählen → „Analysieren" dekodiert
das Lied (``QAudioDecoder``) und schätzt BPM-Verlauf **und** ein phasen-genaues
Beatgrid. Die Kurve + Beats werden geplottet und sind im **Editor** korrigierbar
(½×/2×, nudgen, Downbeat per Klick) — wie bei VirtualDJ/Serato. Per „als BPM-Quelle
nutzen" treibt die Analyse beim Abspielen die BPM über die Zeit.

Engines: Eingebaut (numpy), librosa (DP-Beat), Beat This! (SOTA) — auswählbar,
nicht installierte degradieren sauber auf die eingebaute Engine.
"""
from __future__ import annotations
import os
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QLineEdit, QDoubleSpinBox, QGroupBox, QFileDialog, QSizePolicy, QComboBox,
)

from src.core.audio import offline_timeline as OT
from src.core.audio import analysis_engines as AE
from src.core.audio import genre_presets as GP


# ── BPM-Kurven- + Beatgrid-Plot ───────────────────────────────────────────────

class _TimelinePlot(QWidget):
    """Zeichnet BPM-Kurve + Beatgrid; Klick liefert die Zeit (für Downbeat-Setzen)."""

    clicked_ms = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tl = None
        self._wave = []           # Peak-Huellkurve (0..1) hinter dem Grid
        self._playhead = -1       # Wiedergabe-Position (ms) beim Vorhören
        self._geom = (44, 1, 1)   # (x0, pw, dur_ms) — für Klick-Mapping
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_timeline(self, tl):
        self._tl = tl
        self.update()

    def set_waveform(self, peaks):
        self._wave = peaks or []
        self.update()

    def set_playhead(self, ms):
        self._playhead = int(ms)
        self.update()

    def mousePressEvent(self, e):
        x0, pw, dur = self._geom
        x = e.position().x() if hasattr(e, "position") else e.x()
        ms = int(max(0, min(dur, (x - x0) / max(1, pw) * dur)))
        self.clicked_ms.emit(ms)
        super().mousePressEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor("#141414"))
        ml, mb, mt, mr = 44, 22, 12, 10
        x0, y0 = ml, mt
        pw, ph = max(1, w - ml - mr), max(1, h - mt - mb)

        tl = self._tl
        segs = getattr(tl, "segments", None) or []
        beats = getattr(tl, "beats_ms", None) or []
        downs = set(getattr(tl, "downbeats_ms", None) or [])
        dur = max(1, getattr(tl, "duration_ms", 0) or (beats[-1] if beats else (segs[-1].t_ms if segs else 1)))
        self._geom = (x0, pw, dur)

        if not segs and not beats:
            p.setPen(QColor("#666"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Noch keine Analyse — Datei wählen und analysieren.")
            p.end()
            return

        bpms = [s.bpm for s in segs if s.bpm > 0]
        lo = max(0.0, (min(bpms) - 6) if bpms else 60)
        hi = (max(bpms) + 6) if bpms else 200
        if hi - lo < 8:
            hi = lo + 8

        def px(t_ms):
            return x0 + pw * (t_ms / dur)

        def py(bpm):
            return y0 + ph * (1.0 - (bpm - lo) / (hi - lo))

        # Wellenform (dim, hinter Gitter/Kurve) — zeigt, ob Beats auf Transienten sitzen
        if self._wave:
            n = len(self._wave)
            cy = y0 + ph * 0.5
            amp = ph * 0.46
            p.setPen(QPen(QColor(90, 115, 140, 130), 1))
            for i, pk in enumerate(self._wave):
                x = int(x0 + pw * (i / max(1, n - 1)))
                a = amp * pk
                p.drawLine(x, int(cy - a), x, int(cy + a))

        # BPM-Gitter
        p.setPen(QPen(QColor("#2a2a2a"), 1))
        for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
            y = y0 + ph * frac
            p.drawLine(x0, int(y), x0 + pw, int(y))
            p.setPen(QColor("#888"))
            p.drawText(2, int(y) + 4, f"{hi - (hi - lo) * frac:5.0f}")
            p.setPen(QPen(QColor("#2a2a2a"), 1))

        # Beatgrid (untere 22 px): Beats dünn, Downbeats hell+höher
        if beats:
            gy = y0 + ph
            for b in beats:
                x = int(px(b))
                if b in downs:
                    p.setPen(QPen(QColor("#FF6AD5"), 2))
                    p.drawLine(x, gy - 20, x, gy)
                else:
                    p.setPen(QPen(QColor("#3a6ea5"), 1))
                    p.drawLine(x, gy - 9, x, gy)

        # BPM-Kurve
        if segs:
            path = QPainterPath()
            path.moveTo(px(segs[0].t_ms), py(segs[0].bpm))
            for s in segs[1:]:
                if s.bpm > 0:
                    path.lineTo(px(s.t_ms), py(s.bpm))
            p.setPen(QPen(QColor("#FFD700"), 2))
            p.drawPath(path)

        # Songstruktur-Marker (Phrasen: Intro/Build/Drop/Breakdown/…)
        sections = getattr(tl, "sections", None) or []
        for sec in sections:
            try:
                t_ms, label = int(sec[0]), str(sec[1])
            except (TypeError, ValueError, IndexError):
                continue
            x = int(px(t_ms))
            if label in ("Drop", "Hook", "Start"):
                col = QColor("#FF8C42")
            elif label in ("Breakdown", "Ruhig", "Intro", "Outro"):
                col = QColor("#5AC8FA")
            else:
                col = QColor("#9b8cff")
            p.setPen(QPen(col, 1, Qt.PenStyle.DashLine))
            p.drawLine(x, y0, x, y0 + ph)
            p.setPen(col)
            p.drawText(x + 2, y0 + 11, label)

        # Zeitachse
        p.setPen(QColor("#888"))
        for frac in (0.0, 0.5, 1.0):
            t = int(dur * frac)
            label = f"{t // 60000}:{(t // 1000) % 60:02d}"
            tx = x0 + pw * frac
            align = (Qt.AlignmentFlag.AlignLeft if frac == 0 else
                     Qt.AlignmentFlag.AlignRight if frac == 1 else Qt.AlignmentFlag.AlignHCenter)
            p.drawText(int(tx) - 24, h - mb + 4, 48, 16, align, label)

        # Wiedergabe-Cursor (Vorhören)
        if self._playhead >= 0:
            xph = int(px(min(self._playhead, dur)))
            p.setPen(QPen(QColor("#FFFFFF"), 1))
            p.drawLine(xph, y0, xph, y0 + ph)
        p.end()


# ── Generator-View ────────────────────────────────────────────────────────────

class BpmGeneratorView(QWidget):
    _analyzed = Signal(object)
    _status_sig = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path = ""
        self._timeline = None
        self._busy = False
        self._db_offset = 0
        self._wave_peaks = []
        # Vorhören (eigener Player + Metronom-Klicks, isoliert vom Playlist-Player)
        self._preview_on = False
        self._preview_player = None
        self._preview_out = None
        self._preview_timer = None
        self._click_beat = None
        self._click_down = None
        self._preview_i = 0
        self._preview_downbeats = set()
        self._sugg_genre = "general"   # Auto-Erkennung: Vorschlag Genre + Taktart
        self._sugg_meter = 4
        # Ordner-Stapelanalyse
        self._batch_on = False
        self._batch_files = []
        self._batch_i = 0
        self._batch_timer = None
        self._build_ui()
        self._analyzed.connect(self._on_analyzed)
        self._status_sig.connect(self._set_status)

    # ── Aufbau ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(12)

        intro = QLabel(
            "Lade ein komplettes Lied und erzeuge daraus BPM-Kurve + Beatgrid. "
            "Genre und Analyse-Engine wählbar; das Grid lässt sich im Editor "
            "korrigieren und als BPM-Quelle nutzen, die dem Lied über die Zeit folgt.")
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#bbb;")
        root.addWidget(intro)

        box = QGroupBox("Quelle, Genre & Engine")
        grid = QGridLayout(box)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        grid.addWidget(QLabel("Datei:"), 0, 0)
        self._le_path = QLineEdit()
        self._le_path.setReadOnly(True)
        self._le_path.setPlaceholderText("Keine Datei gewählt")
        grid.addWidget(self._le_path, 0, 1, 1, 2)
        btn_pick = QPushButton("Datei wählen…")
        btn_pick.clicked.connect(self._pick_file)
        grid.addWidget(btn_pick, 0, 3)

        grid.addWidget(QLabel("Genre:"), 1, 0)
        self._cmb_genre = QComboBox()
        for key in GP.ORDER:
            self._cmb_genre.addItem(GP.label(key), key)
        self._cmb_genre.currentIndexChanged.connect(self._on_genre_changed)
        grid.addWidget(self._cmb_genre, 1, 1)
        self._lbl_range = QLabel("")
        self._lbl_range.setStyleSheet("color:#8b949e;")
        grid.addWidget(self._lbl_range, 1, 2, 1, 2)

        grid.addWidget(QLabel("Engine:"), 2, 0)
        self._cmb_engine = QComboBox()
        for e in AE.list_engines():
            text = e["label"] + ("" if e["available"] else "  — " + e["note"])
            self._cmb_engine.addItem(text, e["key"])
        self._cmb_engine.currentIndexChanged.connect(self._on_engine_changed)
        grid.addWidget(self._cmb_engine, 2, 1)

        prow = QHBoxLayout()
        prow.addWidget(QLabel("Fenster (s)"))
        self._sp_window = QDoubleSpinBox()
        self._sp_window.setRange(2.0, 30.0)
        self._sp_window.setValue(8.0)
        prow.addWidget(self._sp_window)
        prow.addWidget(QLabel("Schritt (s)"))
        self._sp_step = QDoubleSpinBox()
        self._sp_step.setRange(0.5, 10.0)
        self._sp_step.setSingleStep(0.5)
        self._sp_step.setValue(2.0)
        prow.addWidget(self._sp_step)
        prow.addSpacing(10)
        prow.addWidget(QLabel("Takt"))
        self._cmb_takt = QComboBox()
        for _lbl, _bpb in (("4/4", 4), ("3/4", 3), ("6/8", 6), ("2/4", 2)):
            self._cmb_takt.addItem(_lbl, _bpb)
        self._cmb_takt.setToolTip("Schläge pro Takt fürs Beatgrid (die Auto-Erkennung "
                                  "schlägt nach der Analyse einen Wert vor).")
        prow.addWidget(self._cmb_takt)
        prow.addStretch(1)
        grid.addLayout(prow, 2, 2, 1, 2)

        self._btn_analyze = QPushButton("Analysieren")
        self._btn_analyze.setStyleSheet(
            "QPushButton{background:#2d6cdf; color:white; font-weight:bold; padding:6px 14px;}")
        self._btn_analyze.clicked.connect(self._analyze)
        self._btn_analyze.setEnabled(False)
        grid.addWidget(self._btn_analyze, 3, 1)
        self._btn_batch = QPushButton("Ordner analysieren…")
        self._btn_batch.setToolTip("Alle Songs eines Ordners analysieren und im Cache "
                                   "ablegen (Stapelanalyse) — danach laden sie sofort.")
        self._btn_batch.clicked.connect(self._batch_folder)
        grid.addWidget(self._btn_batch, 3, 3)
        root.addWidget(box)

        res = QGroupBox("BPM-Verlauf & Beatgrid")
        rlay = QVBoxLayout(res)
        self._summary = QLabel("—")
        self._summary.setStyleSheet("color:#FFD700; font-size:15px;")
        rlay.addWidget(self._summary)
        # Auto-Erkennung: Vorschlag Genre + Taktart
        sug = QHBoxLayout()
        self._lbl_suggest = QLabel("")
        self._lbl_suggest.setStyleSheet("color:#9DFF52;")
        sug.addWidget(self._lbl_suggest)
        self._btn_suggest = QPushButton("Vorschlag übernehmen")
        self._btn_suggest.setToolTip("Setzt Genre + Taktart auf die Auto-Erkennung und "
                                     "analysiert neu (genauer).")
        self._btn_suggest.clicked.connect(self._apply_suggestion)
        self._btn_suggest.setVisible(False)
        sug.addWidget(self._btn_suggest)
        sug.addStretch(1)
        rlay.addLayout(sug)
        self._plot = _TimelinePlot()
        self._plot.clicked_ms.connect(self._on_plot_clicked)
        rlay.addWidget(self._plot)

        # Beatgrid-Editor
        ed = QHBoxLayout()
        ed.addWidget(QLabel("Beatgrid:"))
        for label, fn in (("½×", self._halve), ("2×", self._double),
                          ("◀ nudge", lambda: self._nudge(-8)),
                          ("nudge ▶", lambda: self._nudge(+8)),
                          ("Downbeat ◀", lambda: self._shift_downbeat(-1)),
                          ("Downbeat ▶", lambda: self._shift_downbeat(+1))):
            b = QPushButton(label)
            b.clicked.connect(fn)
            ed.addWidget(b)
        ed.addWidget(QLabel("· Klick im Plot = Downbeat setzen"))
        ed.addSpacing(14)
        self._btn_preview = QPushButton("▶ Vorhören")
        self._btn_preview.setToolTip("Song abspielen mit Metronom-Klick auf jedem Beat "
                                     "(Downbeat betont) — hörbar prüfen, ob das Grid sitzt.")
        self._btn_preview.setEnabled(False)
        self._btn_preview.clicked.connect(self._toggle_preview)
        ed.addWidget(self._btn_preview)
        ed.addStretch(1)
        self._editor_widgets = ed
        rlay.addLayout(ed)

        act = QHBoxLayout()
        self._btn_use = QPushButton("Im Player laden & als BPM-Quelle nutzen")
        self._btn_use.clicked.connect(self._use_as_source)
        self._btn_use.setEnabled(False)
        act.addWidget(self._btn_use)
        self._btn_export = QPushButton("Als .json exportieren")
        self._btn_export.clicked.connect(self._export_json)
        self._btn_export.setEnabled(False)
        act.addWidget(self._btn_export)
        act.addStretch(1)
        rlay.addLayout(act)
        root.addWidget(res, 1)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8b949e;")
        root.addWidget(self._status)

        self._on_genre_changed()
        if not OT.HAS_NUMPY:
            self._set_status("⚠ numpy fehlt — Analyse nicht verfügbar.")
            btn_pick.setEnabled(False)

    # ── Genre / Engine ────────────────────────────────────────────────────────
    def _genre(self) -> str:
        return self._cmb_genre.currentData() or GP.DEFAULT

    def _engine(self) -> str:
        return self._cmb_engine.currentData() or "builtin"

    def _on_genre_changed(self, *_):
        p = GP.get(self._genre())
        self._lbl_range.setText(
            f"{p['min_bpm']}–{p['max_bpm']} BPM · Prior {p['prior']}")

    def _on_engine_changed(self, *_):
        key = self._engine()
        if not AE.available(key):
            name = AE.ENGINE_LABELS.get(key, key)
            self._set_status(
                f"Engine {name} nicht installiert ({AE.install_hint(key)}) — "
                f"es wird die eingebaute Engine genutzt.")
        else:
            self._set_status("")

    # ── Datei + Analyse ───────────────────────────────────────────────────────
    def _pick_file(self):
        exts = " ".join(f"*{e}" for e in OT.AUDIO_EXTS)
        fn, _ = QFileDialog.getOpenFileName(
            self, "Lied wählen", "", f"Audio ({exts});;Alle Dateien (*.*)")
        if not fn:
            return
        self._path = fn
        self._le_path.setText(fn)
        self._btn_analyze.setEnabled(True)
        self._set_status("")

    def _analyze(self):
        if self._busy or not self._path:
            return
        self._preview_stop()
        engine = self._engine()
        genre = self._genre()
        bpb = self._taktart_bpb()
        # Cache-Treffer? → sofort laden (kein Dekodieren/Analysieren nötig)
        try:
            from src.core.audio import bpm_cache
            hit = bpm_cache.get(self._path, engine, genre, bpb)
        except Exception:
            hit = None
        if hit:
            from src.core.audio.offline_timeline import BpmTimeline
            self._wave_peaks = list(hit.get("peaks") or [])
            self._on_analyzed(BpmTimeline.from_dict(hit["timeline"]))
            self._set_status("✓ Sofort aus Cache geladen (bereits analysiert).")
            return
        self._busy = True
        self._btn_analyze.setEnabled(False)
        self._btn_use.setEnabled(False)
        self._btn_export.setEnabled(False)
        self._set_status("Dekodiere Lied…")
        try:
            samples, sr = OT.decode_audio_mono(self._path)
        except Exception as e:
            samples, sr = None, 0
            print(f"[BpmGenerator] decode error: {e}")
        if samples is None or sr <= 0:
            self._busy = False
            self._btn_analyze.setEnabled(True)
            ext = os.path.splitext(self._path)[1].lower()
            name = os.path.basename(self._path)
            self._set_status(
                f"⚠ Konnte {name} nicht dekodieren ({ext}). Fehlt evtl. der "
                f"System-Codec — als .wav konvertieren und erneut versuchen.")
            return
        self._set_status("Analysiere BPM-Verlauf & Beatgrid…")
        p = GP.get(genre)
        win = float(self._sp_window.value())
        step = float(self._sp_step.value())

        def _work():
            try:
                tl = AE.analyze(engine, samples, sr, window_s=win, step_s=step,
                                min_bpm=float(p["min_bpm"]), max_bpm=float(p["max_bpm"]),
                                prior=float(p["prior"]), beats_per_bar=bpb)
            except Exception as e:
                print(f"[BpmGenerator] analyze error: {e}")
                tl = None
            try:
                self._wave_peaks = (OT.waveform_peaks(samples)
                                    if (tl is not None and not tl.is_empty()) else [])
            except Exception:
                self._wave_peaks = []
            try:
                if tl is not None and not tl.is_empty():
                    tl.sections = OT.detect_sections(tl.beats_ms, tl.downbeats_ms,
                                                     self._wave_peaks, tl.duration_ms)
                    from src.core.audio import bpm_cache
                    bpm_cache.put(self._path, engine, genre, bpb,
                                  tl.to_dict(), self._wave_peaks)
            except Exception:
                pass
            self._analyzed.emit(tl)

        threading.Thread(target=_work, daemon=True, name="BpmAnalyze").start()

    def _on_analyzed(self, tl):
        self._busy = False
        self._btn_analyze.setEnabled(True)
        self._timeline = tl
        self._preview_stop()
        if tl is None or tl.is_empty():
            self._plot.set_waveform([])
            self._plot.set_timeline(None)
            self._summary.setText("—")
            self._lbl_suggest.setText("")
            self._btn_suggest.setVisible(False)
            self._btn_preview.setEnabled(False)
            self._set_status("⚠ Keine verwertbare BPM gefunden (zu wenig Beat/zu kurz).")
            return
        self._plot.set_waveform(self._wave_peaks)
        self._btn_preview.setEnabled(tl.has_grid())
        # Downbeat-Versatz aus dem Ergebnis ableiten
        self._db_offset = 0
        if tl.beats_ms and tl.downbeats_ms:
            try:
                self._db_offset = tl.beats_ms.index(tl.downbeats_ms[0]) % max(1, tl.beats_per_bar)
            except ValueError:
                self._db_offset = 0
        self._refresh()
        self._btn_use.setEnabled(True)
        self._btn_export.setEnabled(True)
        self._set_status(f"✓ Analyse fertig (Engine: {tl.engine}).")
        self._update_suggestion(tl)

    # ── Auto-Erkennung: Genre + Taktart vorschlagen ───────────────────────────
    def _update_suggestion(self, tl):
        try:
            med = tl.summary().get("median", 0)
            meter = OT.detect_meter(tl.beats_ms, tl.downbeats_ms) if tl.has_grid() else 4
            self._sugg_genre = GP.suggest(med, self._path)
            self._sugg_meter = meter
            meter_lbl = {4: "4/4", 3: "3/4", 6: "6/8", 2: "2/4"}.get(meter, f"{meter}/4")
            note = "" if tl.engine == "beatthis" else " (Taktart genau mit Beat This!)"
            self._lbl_suggest.setText(
                f"Erkannt: ~{med:.0f} BPM · {meter_lbl} · Empfohlenes Genre: "
                f"{GP.label(self._sugg_genre)}{note}")
            differs = (self._sugg_genre != self._genre()) or (meter != self._taktart_bpb())
            self._btn_suggest.setVisible(differs)
        except Exception:
            self._lbl_suggest.setText("")
            self._btn_suggest.setVisible(False)

    def _taktart_bpb(self) -> int:
        try:
            return int(self._cmb_takt.currentData() or 4)
        except Exception:
            return 4

    def _apply_suggestion(self):
        """Übernimmt Genre + Taktart aus der Auto-Erkennung und analysiert neu."""
        try:
            gi = self._cmb_genre.findData(self._sugg_genre)
            if gi >= 0:
                self._cmb_genre.setCurrentIndex(gi)
            ti = self._cmb_takt.findData(self._sugg_meter)
            if ti >= 0:
                self._cmb_takt.setCurrentIndex(ti)
        except Exception:
            pass
        self._btn_suggest.setVisible(False)
        self._analyze()

    # ── Ordner-Stapelanalyse ──────────────────────────────────────────────────
    def _batch_folder(self):
        if self._batch_on:                       # läuft → abbrechen
            self._batch_finish(cancelled=True)
            return
        folder = QFileDialog.getExistingDirectory(self, "Ordner mit Songs wählen")
        if not folder:
            return
        files = []
        for root, _dirs, names in os.walk(folder):
            for fn in names:
                if os.path.splitext(fn)[1].lower() in OT.AUDIO_EXTS:
                    files.append(os.path.join(root, fn))
        if not files:
            self._set_status("Keine Audiodateien im Ordner gefunden.")
            return
        self._batch_files = files
        self._batch_i = 0
        self._batch_on = True
        self._btn_batch.setText("⏹ Stapel abbrechen")
        from PySide6.QtCore import QTimer
        if self._batch_timer is None:
            self._batch_timer = QTimer(self)
            self._batch_timer.setInterval(40)
            self._batch_timer.timeout.connect(self._batch_step)
        self._batch_timer.start()

    def _batch_step(self):
        if not self._batch_on or self._batch_i >= len(self._batch_files):
            self._batch_finish()
            return
        path = self._batch_files[self._batch_i]
        self._batch_i += 1
        self._set_status(f"Stapelanalyse {self._batch_i}/{len(self._batch_files)}: "
                         f"{os.path.basename(path)}")
        engine, genre, bpb = self._engine(), self._genre(), self._taktart_bpb()
        try:
            from src.core.audio import bpm_cache
            if bpm_cache.get(path, engine, genre, bpb):
                return                            # schon im Cache → nächster Tick
            samples, sr = OT.decode_audio_mono(path)
            if samples is None or sr <= 0:
                return
            p = GP.get(genre)
            tl = AE.analyze(engine, samples, sr, min_bpm=float(p["min_bpm"]),
                            max_bpm=float(p["max_bpm"]), prior=float(p["prior"]),
                            beats_per_bar=bpb)
            if tl is not None and not tl.is_empty():
                peaks = OT.waveform_peaks(samples)
                tl.sections = OT.detect_sections(tl.beats_ms, tl.downbeats_ms,
                                                 peaks, tl.duration_ms)
                bpm_cache.put(path, engine, genre, bpb, tl.to_dict(), peaks)
        except Exception as e:
            print(f"[BpmGenerator] batch error: {e}")

    def _batch_finish(self, cancelled: bool = False):
        was = self._batch_i
        self._batch_on = False
        if self._batch_timer is not None:
            self._batch_timer.stop()
        self._btn_batch.setText("Ordner analysieren…")
        if cancelled:
            self._set_status(f"Stapelanalyse abgebrochen ({was} verarbeitet).")
        else:
            self._set_status(f"✓ Stapelanalyse fertig — {was} Dateien im Cache.")

    # ── Beatgrid-Editor ───────────────────────────────────────────────────────
    def _refresh(self):
        tl = self._timeline
        self._plot.set_timeline(tl)
        self._preview_resync()
        if tl is None:
            return
        s = tl.summary()
        dur = s.get("duration_ms", 0)
        stab = "stabil" if s.get("stable") else "wechselnd"
        self._summary.setText(
            f"Ø {s['avg']:.0f} · Median {s['median']:.0f} BPM · "
            f"{s['min']:.0f}–{s['max']:.0f} ({stab}) · {s.get('beats', 0)} Beats · "
            f"{dur // 60000}:{(dur // 1000) % 60:02d} · Engine {s.get('engine', '?')}")

    def _recompute_downbeats(self):
        tl = self._timeline
        if not tl or not tl.beats_ms:
            return
        bpb = max(1, tl.beats_per_bar)
        tl.downbeats_ms = tl.beats_ms[self._db_offset % bpb::bpb]

    def _after_grid_edit(self):
        tl = self._timeline
        if tl and tl.beats_ms:
            tl.segments = OT.segments_from_beats(tl.beats_ms, max(0.5, self._sp_step.value()))
        self._recompute_downbeats()
        self._refresh()

    def _nudge(self, delta_ms: int):
        tl = self._timeline
        if not tl or not tl.beats_ms:
            return
        tl.beats_ms = [max(0, b + delta_ms) for b in tl.beats_ms]
        self._recompute_downbeats()
        self._refresh()

    def _halve(self):
        tl = self._timeline
        if not tl or len(tl.beats_ms) < 2:
            return
        tl.beats_ms = tl.beats_ms[::2]
        self._after_grid_edit()

    def _double(self):
        tl = self._timeline
        if not tl or len(tl.beats_ms) < 2:
            return
        b = tl.beats_ms
        nb = []
        for i in range(len(b) - 1):
            nb.append(b[i])
            nb.append((b[i] + b[i + 1]) // 2)
        nb.append(b[-1])
        tl.beats_ms = nb
        self._after_grid_edit()

    def _shift_downbeat(self, d: int):
        tl = self._timeline
        if not tl or not tl.beats_ms:
            return
        self._db_offset = (self._db_offset + d) % max(1, tl.beats_per_bar)
        self._recompute_downbeats()
        self._refresh()

    def _on_plot_clicked(self, ms: int):
        tl = self._timeline
        if not tl or not tl.beats_ms:
            return
        i, _t = tl.nearest_beat(ms)
        if i is None:
            return
        self._db_offset = i % max(1, tl.beats_per_bar)
        self._recompute_downbeats()
        self._refresh()
        self._set_status("Downbeat gesetzt.")

    # ── Nutzen / Export ───────────────────────────────────────────────────────
    def _use_as_source(self):
        if self._timeline is None or self._timeline.is_empty() or not self._path:
            return
        try:
            from src.core.audio.media_player import get_media_player, Track
            mp = get_media_player()
            tld = self._timeline.to_dict()
            s = self._timeline.summary()
            track = next((t for t in mp.tracks if t.path == self._path), None)
            if track is None:
                track = Track(path=self._path)
                mp.set_tracks(list(mp.tracks) + [track])
            track.bpm_timeline = tld
            track.bpm_source = "analysis"
            if s.get("median", 0) > 0:
                track.bpm = float(s["median"])
            for i, t in enumerate(mp.tracks):
                if t.path == self._path:
                    mp.index = i
                    mp.trackChanged.emit(i)
                    break
            try:
                from src.core.app_state import get_state
                get_state().playlist = mp.to_dicts()
            except Exception:
                pass
            try:
                from src.core.engine.bpm_manager import get_bpm_manager
                get_bpm_manager().use_audio_source(False)
            except Exception:
                pass
            self._set_status(
                "✓ Im Player geladen — die Lied-Analyse ist jetzt die BPM-Quelle. "
                "Im Musik-Tab abspielen; die BPM folgt dem Lied über die Zeit.")
        except Exception as e:
            self._set_status(f"Fehler beim Laden in den Player: {e}")

    def _export_json(self):
        if self._timeline is None or self._timeline.is_empty():
            return
        import json
        default = (os.path.splitext(self._path)[0] + ".bpmtimeline.json"
                   if self._path else "timeline.json")
        fn, _ = QFileDialog.getSaveFileName(
            self, "Timeline speichern", default, "JSON (*.json)")
        if not fn:
            return
        try:
            with open(fn, "w", encoding="utf-8") as f:
                json.dump(self._timeline.to_dict(), f, indent=2)
            self._set_status(f"✓ Gespeichert: {fn}")
        except Exception as e:
            self._set_status(f"Speichern fehlgeschlagen: {e}")

    def _set_status(self, text: str):
        self._status.setText(text)

    # ── Vorhören mit Metronom (Editor-Kontrolle) ──────────────────────────────
    def _ensure_clicks(self) -> bool:
        if self._click_beat is not None:
            return True
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import QSoundEffect
            beat_p = _make_click_wav(1000.0, 0.6)
            down_p = _make_click_wav(1600.0, 0.9)
            if not beat_p or not down_p:
                return False
            self._click_beat = QSoundEffect(self)
            self._click_beat.setSource(QUrl.fromLocalFile(beat_p))
            self._click_beat.setVolume(0.45)
            self._click_down = QSoundEffect(self)
            self._click_down.setSource(QUrl.fromLocalFile(down_p))
            self._click_down.setVolume(0.7)
            return True
        except Exception as e:
            print(f"[BpmGenerator] click setup error: {e}")
            return False

    def _toggle_preview(self):
        if self._preview_on:
            self._preview_stop()
        else:
            self._preview_start()

    def _preview_start(self):
        if self._timeline is None or not self._timeline.has_grid() or not self._path:
            return
        if not self._ensure_clicks():
            self._set_status("Metronom-Klicks nicht verfügbar — Vorhören ohne Klick.")
        try:
            from PySide6.QtCore import QUrl, QTimer
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            if self._preview_player is None:
                self._preview_out = QAudioOutput()
                self._preview_player = QMediaPlayer()
                self._preview_player.setAudioOutput(self._preview_out)
            if self._preview_timer is None:
                self._preview_timer = QTimer(self)
                self._preview_timer.setInterval(15)
                self._preview_timer.timeout.connect(self._preview_tick)
            self._preview_downbeats = set(self._timeline.downbeats_ms or [])
            self._preview_i = 0
            self._preview_player.setSource(QUrl.fromLocalFile(self._path))
            self._preview_player.play()
            self._preview_timer.start()
            self._preview_on = True
            self._btn_preview.setText("⏹ Vorhören stoppen")
            self._set_status("Vorhören läuft — Klick auf jedem Beat (Downbeat betont). "
                             "Grid-Buttons korrigieren live.")
        except Exception as e:
            self._set_status(f"Vorhören fehlgeschlagen: {e}")

    def _preview_stop(self):
        if not self._preview_on:
            return
        self._preview_on = False
        try:
            if self._preview_timer is not None:
                self._preview_timer.stop()
            if self._preview_player is not None:
                self._preview_player.stop()
        except Exception:
            pass
        self._plot.set_playhead(-1)
        if hasattr(self, "_btn_preview"):
            self._btn_preview.setText("▶ Vorhören")

    def _preview_resync(self):
        """Nach Grid-Edits den Klick-Index wieder auf die Wiedergabe-Position setzen."""
        if not self._preview_on or self._preview_player is None or self._timeline is None:
            return
        import bisect
        self._preview_downbeats = set(self._timeline.downbeats_ms or [])
        self._preview_i = bisect.bisect_right(self._timeline.beats_ms or [],
                                              int(self._preview_player.position()))

    def _preview_tick(self):
        if not self._preview_on or self._preview_player is None or self._timeline is None:
            return
        try:
            import bisect
            pos = int(self._preview_player.position())
            beats = self._timeline.beats_ms or []
            self._plot.set_playhead(pos)
            if self._preview_i > len(beats):
                self._preview_i = len(beats)
            # Rückwärts-Seek → Index neu setzen
            if (0 < self._preview_i <= len(beats)
                    and pos < beats[self._preview_i - 1] - 150):
                self._preview_i = bisect.bisect_right(beats, pos)
            fired = 0
            while self._preview_i < len(beats) and beats[self._preview_i] <= pos and fired < 8:
                is_db = beats[self._preview_i] in self._preview_downbeats
                eff = self._click_down if is_db else self._click_beat
                if eff is not None:
                    eff.play()
                self._preview_i += 1
                fired += 1
        except Exception:
            pass

    def hideEvent(self, e):
        self._preview_stop()
        if self._batch_on:
            self._batch_finish(cancelled=True)
        super().hideEvent(e)


# ── Metronom-Klick (kurze WAV im Temp, einmalig erzeugt) ──────────────────────

def _make_click_wav(freq: float, gain: float = 0.7) -> str:
    """Erzeugt eine kurze Klick-WAV (Sinus-Burst mit schnellem Abfall). Gibt den
    Pfad zurueck (gecacht im Temp) oder '' bei Fehler."""
    import os
    import tempfile
    import wave
    import struct
    import math
    try:
        sr = 44100
        ln = int(sr * 0.045)
        path = os.path.join(tempfile.gettempdir(), f"lightos_click_{int(freq)}.wav")
        if os.path.exists(path):
            return path
        frames = bytearray()
        for i in range(ln):
            env = math.exp(-i / (sr * 0.008))
            s = math.sin(2.0 * math.pi * freq * i / sr) * env * gain
            frames += struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767))
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(bytes(frames))
        return path
    except Exception:
        return ""
