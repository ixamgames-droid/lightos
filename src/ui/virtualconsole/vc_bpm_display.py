"""VCBpmDisplay — zeigt in der Virtuellen Konsole das aktuelle globale Tempo an.

WP-8 (Virtual-Console-Integration): reine Anzeige der Live-BPM (gross) plus einer
kurzen Quelle/Modus-Zeile (z. B. „AUTO", „MANUAL", „OS2L", „Tap"). Gesteuert wird
das Tempo ueber VCButtons (ButtonAction.TAP / BPM_NUDGE_* / BPM_MODE_TOGGLE) bzw.
den BPM-Fader (SliderMode.BPM) und den BPM-Manager-Tab — dieses Widget ist
nicht-interaktiv.

Struktur analog VCSongInfo (reines Anzeige-Widget mit Backend-Anbindung), aber:
Der BPMManager ruft seine Callbacks aus einem Worker-Thread (Timer-/Audio-Thread)
auf. Qt-Widgets duerfen nur aus dem GUI-Thread angefasst werden, deshalb
marshallen wir die Updates ueber ein Qt-Signal (`_bpm_changed_sig` /
`_state_changed_sig`) in den GUI-Thread. Beim Zerstoeren melden wir uns
zuverlaessig wieder ab (keine Geister-Callbacks auf ein geloeschtes Widget).
"""
from __future__ import annotations
from PySide6.QtWidgets import QDialog, QFormLayout, QSpinBox, QDialogButtonBox, QComboBox
from PySide6.QtCore import Qt, QRect, Signal, QTimer
from PySide6.QtGui import QPainter, QColor, QFont
from .vc_widget import VCWidget


# Kurze, kompakte Quelle/Modus-Labels fuer die schmale VC-Anzeige (vgl. die
# ausfuehrlicheren _SRC_LABELS im BPM-Manager-Tab).
_SRC_SHORT = {
    "audio": "AUTO",
    "file":  "AUTO",
    "os2l":  "OS2L",
    "tap":   "Tap",
    "nudge": "Nudge",
    "manual": "MANUAL",
    "off":   "—",
}


class VCBpmDisplay(VCWidget):
    """Live-Tempo-Anzeige: grosse BPM-Zahl + kurze Quelle/Modus-Zeile."""

    # Marshalling in den GUI-Thread: der BPMManager ruft die Callbacks aus
    # Worker-Threads auf, das Signal stellt sie im GUI-Thread zu.
    _bpm_changed_sig = Signal(float)
    _state_changed_sig = Signal()

    def __init__(self, caption: str = "BPM", parent=None):
        super().__init__(caption, parent)
        self._font_size = 11
        self._bg_color = QColor("#101820")
        self._fg_color = QColor("#e8e8e8")
        self.resize(180, 96)

        # Aktueller Anzeigezustand (wird nur im GUI-Thread aus den Signalen heraus
        # aktualisiert — die Callbacks selbst beruehren keine Widgets/Felder).
        self._bpm = 0.0
        self._source = "off"
        self._mode = "auto"
        # "" = globaler BPM-Leader (Default). Sonst zeigt das Widget die BPM eines
        # benannten Tempo-Bus (A/B/C/D) an — Tempo-Sync Phase 5.
        self.tempo_bus_id = ""

        self._bpm_changed_sig.connect(self._on_bpm_changed)
        self._state_changed_sig.connect(self._on_state_changed)
        self._connect_manager()
        # Bus-Modus: TempoBus hat keine subscribe-API -> per GUI-Timer (~10 Hz) pollen.
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(100)
        self._poll_timer.timeout.connect(self._poll_bus)
        self._update_bus_mode()
        # Zuverlaessige Abmeldung beim Zerstoeren (sonst Callback-Leak / Crash, wenn
        # der Manager auf ein bereits geloeschtes Widget feuert).
        self.destroyed.connect(lambda *_: self._teardown())

    # ── BPM-Manager-Anbindung ───────────────────────────────────────────────────

    def _manager(self):
        try:
            from src.core.engine.bpm_manager import get_bpm_manager
            return get_bpm_manager()
        except Exception:
            return None

    def _connect_manager(self):
        """Abonniert BPM- und Zustandsaenderungen (KEIN use_audio_source!)."""
        try:
            mgr = self._manager()
            if mgr is None:
                return
            mgr.subscribe_bpm_change(self._on_bpm_cb)
            mgr.subscribe_state_change(self._on_state_cb)
            # Initialen Stand uebernehmen (Widget kann nachtraeglich angelegt werden).
            self._bpm = float(mgr.bpm)
            self._source = str(mgr.current_source)
            self._mode = mgr.mode.value if hasattr(mgr.mode, "value") else str(mgr.mode)
        except Exception as e:
            print(f"[VCBpmDisplay] connect error: {e}")

    def _teardown(self):
        """Callbacks beim Manager wieder abmelden (mirror VCCanvas-Teardown).
        Idempotent — kann aus destroyed UND closeEvent kommen."""
        if getattr(self, "_torn_down", False):
            return
        self._torn_down = True
        try:
            self._poll_timer.stop()
        except Exception:
            pass
        mgr = self._manager()
        if mgr is None:
            return
        try:
            mgr.unsubscribe_bpm_change(self._on_bpm_cb)
        except Exception:
            pass
        try:
            mgr.unsubscribe_state_change(self._on_state_cb)
        except Exception:
            pass

    def closeEvent(self, event):
        self._teardown()
        super().closeEvent(event)

    # ── Backend-Callbacks (Worker-Thread!) → nur Signal emittieren ──────────────

    def _on_bpm_cb(self, bpm: float):
        # Achtung: laeuft evtl. im Timer/Audio-Thread — KEINE Widget-Zugriffe hier.
        try:
            self._bpm_changed_sig.emit(float(bpm))
        except RuntimeError:
            # Widget bereits zerstoert — Callback ignorieren.
            pass

    def _on_state_cb(self):
        try:
            self._state_changed_sig.emit()
        except RuntimeError:
            pass

    # ── GUI-Thread-Slots ────────────────────────────────────────────────────────

    def _on_bpm_changed(self, bpm: float):
        self._bpm = float(bpm)
        self.update()

    def _on_state_changed(self):
        mgr = self._manager()
        if mgr is not None:
            self._source = str(mgr.current_source)
            self._mode = mgr.mode.value if hasattr(mgr.mode, "value") else str(mgr.mode)
        self.update()

    # ── Bus-Modus (Tempo-Sync Phase 5) ─────────────────────────────────────────

    def _update_bus_mode(self):
        """Startet/stoppt den Poll-Timer je nach Bus-Bindung."""
        try:
            if self.tempo_bus_id:
                if not self._poll_timer.isActive():
                    self._poll_timer.start()
            else:
                self._poll_timer.stop()
        except Exception:
            pass

    def _poll_bus(self):
        """Liest die BPM des gebundenen Tempo-Bus (GUI-Thread, lock-sicher)."""
        try:
            from src.core.engine.tempo_bus import get_tempo_bus_manager
            bus = get_tempo_bus_manager().resolve(self.tempo_bus_id)
            self._bpm = float(bus.bpm) if bus is not None else 0.0
        except Exception:
            self._bpm = 0.0
        self.update()

    def _mode_label(self) -> str:
        """Kurzes Quelle/Modus-Label fuer die zweite Zeile."""
        lbl = _SRC_SHORT.get(self._source)
        if lbl:
            return lbl
        # Fallback ueber den Modus, falls die Quelle unbekannt ist.
        return "AUTO" if str(self._mode).lower() == "auto" else "MANUAL"

    # ── Painting ──────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg_color)

        pad = 8
        w = self.width() - 2 * pad
        y = pad

        # Kopfzeile
        p.setPen(QColor("#7fb0ff"))
        p.setFont(QFont("Segoe UI", max(7, self._font_size - 3), QFont.Weight.Bold))
        p.drawText(QRect(pad, y, w, 16), Qt.AlignmentFlag.AlignLeft, self.caption.upper())
        y += 18

        # Grosse BPM-Zahl
        active = self._bpm > 0
        p.setPen(QColor("#58d68d") if active else self._fg_color)
        big = max(16, self._font_size * 2 + 8)
        p.setFont(QFont("Segoe UI", big, QFont.Weight.Bold))
        txt = f"{self._bpm:.0f}" if active else "—"
        bpm_h = big + 8
        p.drawText(QRect(pad, y, w, bpm_h), Qt.AlignmentFlag.AlignLeft, txt)
        # „BPM"-Einheit dezent rechts
        p.setPen(QColor("#9aa4ad"))
        p.setFont(QFont("Segoe UI", max(7, self._font_size - 2)))
        p.drawText(QRect(pad, y, w, bpm_h), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom, "BPM")
        y += bpm_h

        # Quelle/Modus-Zeile
        p.setPen(QColor("#f0883e") if str(self._mode).lower() == "manual" else QColor("#7fb0ff"))
        p.setFont(QFont("Segoe UI", max(7, self._font_size - 2), QFont.Weight.Bold))
        _line2 = f"BUS {self.tempo_bus_id}" if self.tempo_bus_id else self._mode_label()
        p.drawText(QRect(pad, y, w, 18), Qt.AlignmentFlag.AlignLeft, _line2)

        p.end()

    # ── Properties ──────────────────────────────────────────────────────────────────

    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("BPM-Anzeige")
        form = QFormLayout(dlg)
        fs = QSpinBox()
        fs.setRange(7, 28)
        fs.setValue(self._font_size)
        form.addRow("Schriftgröße:", fs)
        bus_cb = QComboBox()
        for _bid, _blbl in (("", "Global (Leader)"), ("A", "Bus A"), ("B", "Bus B"),
                            ("C", "Bus C"), ("D", "Bus D")):
            bus_cb.addItem(_blbl, _bid)
        for i in range(bus_cb.count()):
            if bus_cb.itemData(i) == self.tempo_bus_id:
                bus_cb.setCurrentIndex(i)
                break
        bus_cb.setToolTip("Welche BPM angezeigt wird: der globale Leader oder ein Tempo-Bus.")
        form.addRow("Quelle:", bus_cb)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._font_size = fs.value()
            self.tempo_bus_id = bus_cb.currentData() or ""
            self._update_bus_mode()
            self.update()

    # ── Serialisierung ────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["font_size"] = self._font_size
        d["tempo_bus_id"] = self.tempo_bus_id
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self._font_size = int(d.get("font_size", 11))
        self.tempo_bus_id = d.get("tempo_bus_id", "") or ""
        self._update_bus_mode()
