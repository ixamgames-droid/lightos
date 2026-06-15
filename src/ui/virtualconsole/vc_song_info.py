"""VCSongInfo — zeigt in der Virtuellen Konsole das aktuelle und nächste Lied an.

Liest aus dem In-App-MediaPlayer (src/core/audio/media_player.py) und aktualisiert
sich bei jedem Trackwechsel. Nicht-interaktiv (reine Anzeige) — gesteuert wird die
Wiedergabe über VCButtons mit ButtonAction.MEDIA_* bzw. den Musik-Tab.
"""
from __future__ import annotations
from PySide6.QtWidgets import QDialog, QFormLayout, QSpinBox, QDialogButtonBox
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QColor, QFont
from .vc_widget import VCWidget


class VCSongInfo(VCWidget):
    """Anzeige „▶ Jetzt: … / Als Nächstes: …" aus der Musik-Playlist."""

    def __init__(self, caption: str = "Musik", parent=None):
        super().__init__(caption, parent)
        self._font_size = 11
        self._bg_color = QColor("#101820")
        self._fg_color = QColor("#e8e8e8")
        self.resize(300, 96)
        self._connect_player()

    # ── MediaPlayer-Anbindung ─────────────────────────────────────────────────────

    def _connect_player(self):
        try:
            from src.core.audio.media_player import get_media_player
            mp = get_media_player()
            mp.trackChanged.connect(self._on_changed)
            mp.playlistChanged.connect(self._on_changed)
            mp.playingChanged.connect(self._on_changed)
        except Exception as e:
            print(f"[VCSongInfo] connect error: {e}")

    def _on_changed(self, *args):
        self.update()

    def _player(self):
        try:
            from src.core.audio.media_player import get_media_player
            return get_media_player()
        except Exception:
            return None

    # ── Painting ──────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg_color)

        mp = self._player()
        cur = mp.current_track if mp else None
        nxt = mp.next_track if mp else None
        playing = bool(mp.is_playing) if mp else False

        pad = 8
        w = self.width() - 2 * pad
        y = pad

        # Kopfzeile
        p.setPen(QColor("#7fb0ff"))
        p.setFont(QFont("Segoe UI", max(7, self._font_size - 3), QFont.Weight.Bold))
        p.drawText(QRect(pad, y, w, 16), Qt.AlignmentFlag.AlignLeft, self.caption.upper())
        y += 18

        # Aktuelles Lied
        icon = "▶" if playing else "⏸"
        p.setPen(QColor("#58d68d") if playing else self._fg_color)
        p.setFont(QFont("Segoe UI", self._font_size, QFont.Weight.Bold))
        if cur is not None:
            bpm = f"  ·  {cur.bpm:.0f} BPM" if cur.bpm else ""
            txt = f"{icon} {cur.title}{bpm}"
        else:
            txt = f"{icon} —  (keine Playlist)"
        p.drawText(QRect(pad, y, w, 22), Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, txt)
        y += 26

        # Nächstes Lied
        p.setPen(QColor("#9aa4ad"))
        p.setFont(QFont("Segoe UI", max(7, self._font_size - 2)))
        if nxt is not None and (cur is None or nxt is not cur):
            ntxt = f"Als Nächstes: {nxt.title}"
        else:
            ntxt = "Als Nächstes: —"
        p.drawText(QRect(pad, y, w, 20), Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, ntxt)

        p.end()

    # ── Properties ──────────────────────────────────────────────────────────────────

    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Song-Anzeige")
        form = QFormLayout(dlg)
        fs = QSpinBox()
        fs.setRange(7, 28)
        fs.setValue(self._font_size)
        form.addRow("Schriftgröße:", fs)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._font_size = fs.value()
            self.update()

    # ── Serialisierung ────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["font_size"] = self._font_size
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self._font_size = int(d.get("font_size", 11))
