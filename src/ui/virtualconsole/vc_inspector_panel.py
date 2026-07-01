"""VCInspectorPanel — andockbares Eigenschaften-Panel der Virtuellen Konsole.

Ersetzt im Bearbeiten-Modus die modalen Eigenschafts-Dialoge: das aktuell gewaehlte
VC-Widget wird hier live bearbeitet (jede Aenderung wirkt sofort; beim Wechsel/Verlassen
wird ein Undo-Schritt fuer die gesamte Bearbeitungs-Sitzung gesetzt). Widgets mit
``build_inspector_body`` (Runde 1: VCButton) zeigen ihre vollen, in Sektionen
gegliederten Einstellungen inline; alle anderen Typen zeigen eine Kurzkarte mit
Button auf ihren bestehenden Dialog (Fallback, bis sie migriert sind).

Zentrale Naht: ``VCCanvas.widget_selected``-Signal -> ``bind(widget)``. Der Undo-
Stand wird beim Binden erfasst (``canvas.to_dict()``) und beim Verlassen der Sitzung
nur dann auf den Undo-Stapel gelegt, wenn sich wirklich etwas geaendert hat.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QPushButton,
)


def _is_valid(obj) -> bool:
    """True, wenn das zugrundeliegende C++-QObject noch lebt (kein dangling ptr)."""
    if obj is None:
        return False
    try:
        import shiboken6
        return shiboken6.isValid(obj)
    except Exception:
        return True


_TYPE_LABELS = {
    "VCButton": "Button", "VCSlider": "Fader", "VCSpeedDial": "Speed-Rad",
    "VCColor": "Farb-Kachel", "VCEncoder": "Encoder", "VCStepper": "Schrittzähler",
    "VCBusSelector": "Tempo-Bus", "VCXYPad": "XY-Feld", "VCFrame": "Rahmen",
    "VCEffectEditor": "Effekt-Box", "VCLabel": "Beschriftung",
    "VCEffectDisplay": "Effekt-Vorschau", "VCColorList": "Farbliste",
    "VCEffectColors": "Effekt-Farben", "VCCuelist": "Cue-Liste",
    "VCBpmDisplay": "BPM-Anzeige", "VCSongInfo": "Song-Info",
    "VCMultiLiveEditor": "Live-Edit",
}


class VCInspectorPanel(QWidget):
    """Eigenschaften-Panel; an ein VC-Widget gebunden oder leer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(260)
        self.setMaximumWidth(440)
        self.setStyleSheet(
            "QWidget { background:#0d1117; }"
            "QLabel { color:#c9d1d9; }"
        )
        self._widget = None
        self._before = None     # Canvas-Stand vor der Bearbeitung (fuer Undo)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(4)

        self._title = QLabel("Inspector")
        self._title.setStyleSheet("color:#e6edf3; font-weight:bold; font-size:13px;")
        root.addWidget(self._title)

        self._subtitle = QLabel("Kein Element gewählt")
        self._subtitle.setStyleSheet("color:#8b949e; font-size:11px;")
        self._subtitle.setWordWrap(True)
        root.addWidget(self._subtitle)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea { border:none; background:#0d1117; }")
        root.addWidget(self._scroll, 1)

        self._show_empty()

    # ── Oeffentliche API ───────────────────────────────────────────────────────

    def bind(self, widget):
        """Bindet das Panel an ein VC-Widget (``None`` = leeren). Schliesst zuvor die
        laufende Bearbeitungs-Sitzung sauber ab (letztes Apply + Undo-Punkt)."""
        if widget is self._widget:
            return
        self._end_session()
        if not _is_valid(widget):
            widget = None
        self._widget = widget
        if widget is None:
            self._show_empty()
            return
        self._before = self._capture_before()
        self._build_for(widget)

    def clear(self):
        """Auswahl loesen (z. B. beim Show-Laden oder Verlassen des Edit-Modus)."""
        self.bind(None)

    # ── Aufbau ─────────────────────────────────────────────────────────────────

    def _build_for(self, widget):
        type_label = _TYPE_LABELS.get(widget.__class__.__name__,
                                      widget.__class__.__name__)
        cap = getattr(widget, "caption", "") or "—"
        self._title.setText(type_label)
        self._subtitle.setText(f"„{cap}“")
        if hasattr(widget, "build_inspector_body"):
            try:
                body = widget.build_inspector_body(host=self)
            except Exception as e:
                body = self._message_body(f"Inspector-Fehler: {e}")
        else:
            body = self._fallback_body(widget)
        self._set_body(body)

    def _fallback_body(self, widget):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 6, 0, 0)
        info = QLabel("Für diesen Typ öffnet sich der ausführliche Dialog.")
        info.setWordWrap(True)
        info.setStyleSheet("color:#8b949e; font-size:11px;")
        lay.addWidget(info)
        btn = QPushButton("Einstellungen öffnen…")
        btn.clicked.connect(lambda: self._open_modal(widget))
        lay.addWidget(btn)
        lay.addStretch(1)
        return w

    def _message_body(self, text):
        w = QLabel(text)
        w.setWordWrap(True)
        w.setStyleSheet("color:#f85149; font-size:11px; padding:8px;")
        return w

    def _open_modal(self, widget):
        if _is_valid(widget) and hasattr(widget, "_edit_properties"):
            widget._edit_properties()

    def _set_body(self, body):
        # QScrollArea uebernimmt den Besitz des vorigen Widgets und loescht es.
        self._scroll.setWidget(body)

    def _show_empty(self):
        self._title.setText("Inspector")
        self._subtitle.setText("Kein Element gewählt")
        ph = QLabel("Wähle im Bearbeiten-Modus ein Element aus,\n"
                    "um es hier einzustellen.")
        ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph.setWordWrap(True)
        ph.setStyleSheet("color:#6e7681; font-size:11px; padding:24px 12px;")
        self._set_body(ph)

    # ── Undo-Sitzung ───────────────────────────────────────────────────────────

    def _capture_before(self):
        canvas = self._find_canvas()
        if canvas is None:
            return None
        try:
            return canvas.to_dict()
        except Exception:
            return None

    def _end_session(self):
        """Schliesst die laufende Bearbeitung ab: letztes Apply (faengt Aenderungen
        ohne Live-Signal, z. B. Ziel-Listen) + ein Undo-Punkt, wenn sich der Layout-
        Stand geaendert hat."""
        w, before = self._widget, self._before
        self._before = None
        if w is None or before is None:
            return
        canvas = self._find_canvas()
        if _is_valid(w):
            apply = getattr(w, "_inspector_apply", None)
            if callable(apply):
                try:
                    apply()
                except Exception:
                    pass
        if canvas is None:
            return
        try:
            if canvas.to_dict() != before:
                canvas.push_undo_snapshot(before)
        except Exception:
            pass

    def _find_canvas(self):
        w = self._widget
        if not _is_valid(w):
            return None
        p = w.parent()
        while p is not None:
            if hasattr(p, "push_undo_snapshot") and hasattr(p, "to_dict"):
                return p
            p = p.parent()
        return None
