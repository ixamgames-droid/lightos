"""VCMultiLiveEditor — frei schwebendes Live-Edit-Fenster fuer mehrere Effekte.

Davids Wunsch: ein grosses, frei skalierbares Fenster, in das man mehrere Effekte
(Matrix, Chaser, EFX …) per Drag&Drop hineinzieht. Oben blaettert man mit Dropdown
und -/+ durch die zugewiesenen Effekte; der Body zeigt einen Live-Editor fuer den
gerade gewaehlten Effekt.

NICHT-PERSISTENZ (Kern): Das Fenster ist KEIN ``VCWidget`` und steht NICHT im
``WIDGET_REGISTRY`` — es hat kein ``to_dict`` und landet damit nie in der Show.
Die Effekt-Parameter werden live ueber ``effect_live`` gesetzt; dessen
Sitzungs-Baseline-Mechanismus (``begin_live_edit`` / ``serialization_dict``) sorgt
dafuer, dass ein Show-Save den urspruenglichen Preset-Zustand schreibt, NICHT die
Live-Werte. Es wird daher bewusst NIE ``commit_live_override`` /
``discard_live_override_tracking`` aufgerufen — beide wuerden die Live-Werte
speicherbar machen. Die Baseline wird beim Drop EINMAL gepinnt (``begin_live_edit``);
Edits laufen ueber ``effect_live.set_param`` (Branch 4).

Grenze: ``_live_baselines`` ist global pro Effektobjekt (nicht fenster-eigen).
Ruft eine ANDERE Oberflaeche bewusst ``Commit``/``Reset Live`` auf demselben Effekt
auf (z. B. ein dafuer gebundener VC-Button), wird die geteilte Baseline nach Absicht
uebernommen/verworfen — gewolltes App-weites Verhalten, keine Garantie dieses
Fensters dagegen.

Branch 3 (dieses File): nur das Grundgeruest — Drag-In, Navigation, Baseline-Naht.
Parameter-Editor (mit Checkbox-Auswahl), Vorschau pro Typ und Tempo-Modus folgen
in spaeteren Branches.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

# Muss exakt dem Funktions-MIME der VC entsprechen (vc_canvas.VCCanvas._MIME_FUNCTION).
_MIME_FUNCTION = "application/x-lightos-function"


class VCMultiLiveEditor(QWidget):
    """Nicht-persistentes Multi-Effekt-Live-Edit-Fenster (Grundgeruest)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Eigenes Top-Level-Fenster trotz parent (Lebensdauer/Stacking am View).
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowTitle("Live-Edit")
        self.setAcceptDrops(True)
        self.setMinimumSize(420, 320)
        self.resize(560, 460)

        self._fids: list[int] = []   # zugewiesene Effekt-IDs (Reihenfolge = Drop)
        self._current: int = -1      # Index des gerade gezeigten Effekts

        self._build()
        self._refresh_nav()

    # ── Aufbau ────────────────────────────────────────────────────────────────
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        nav = QHBoxLayout()
        nav.setSpacing(6)
        self._prev = QPushButton("–")
        self._prev.setFixedWidth(34)
        self._prev.setToolTip("Vorheriger Effekt")
        self._prev.clicked.connect(lambda: self._step(-1))
        self._combo = QComboBox()
        self._combo.setToolTip("Zugewiesene Effekte")
        self._combo.currentIndexChanged.connect(self._on_combo)
        self._next = QPushButton("+")
        self._next.setFixedWidth(34)
        self._next.setToolTip("Naechster Effekt")
        self._next.clicked.connect(lambda: self._step(1))
        nav.addWidget(self._prev)
        nav.addWidget(self._combo, 1)
        nav.addWidget(self._next)
        root.addLayout(nav)

        # Body-Platzhalter (Parameter/Vorschau/Tempo folgen in Branch 4/5).
        self._body = QLabel()
        self._body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body.setWordWrap(True)
        self._body.setObjectName("mle_body")
        root.addWidget(self._body, 1)

        self.setStyleSheet("""
            QWidget { background:#0d1117; color:#e6edf3; }
            QLabel#mle_body { color:#8b949e; font-size:12px;
                              border:1px dashed #30363d; border-radius:6px; padding:24px; }
            QComboBox { background:#161b22; border:1px solid #30363d; border-radius:3px;
                        padding:3px 6px; min-height:24px; }
            QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                          border-radius:3px; font-size:13px; min-height:24px; }
            QPushButton:hover:enabled { background:#30363d; }
            QPushButton:disabled { color:#484f58; }
        """)

    # ── Drag & Drop ────────────────────────────────────────────────────────────
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(_MIME_FUNCTION):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(_MIME_FUNCTION):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        md = event.mimeData()
        if not md.hasFormat(_MIME_FUNCTION):
            event.ignore()
            return
        try:
            fid = int(md.data(_MIME_FUNCTION).data().decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            event.ignore()
            return
        self.add_effect(fid)
        event.acceptProposedAction()

    # ── Effekt-Liste / Navigation ───────────────────────────────────────────────
    def add_effect(self, function_id) -> None:
        """Effekt aufnehmen (oder, falls schon drin, dorthin blaettern).

        Nur real existierende Funktionen werden aufgenommen — ein veralteter Drop
        (Funktion inzwischen geloescht) erzeugt keinen Geister-Eintrag."""
        try:
            fid = int(function_id)
        except (TypeError, ValueError):
            return
        if fid in self._fids:
            self._current = self._fids.index(fid)
            self._refresh_nav()
            return
        from src.core.engine import effect_live
        if effect_live.resolve_target(fid) is None:
            return
        self._fids.append(fid)
        self._current = len(self._fids) - 1
        # Baseline EINMAL pinnen -> Live-Edits bleiben fluechtig (Save schreibt das
        # Preset). Bewusst kein commit/discard hier oder beim Schliessen.
        effect_live.begin_live_edit(fid)
        self._refresh_nav()

    def _step(self, delta: int) -> None:
        if not self._fids:
            return
        self._current = (self._current + delta) % len(self._fids)
        self._refresh_nav()

    def _on_combo(self, idx: int) -> None:
        if 0 <= idx < len(self._fids):
            self._current = idx
            self._refresh_body()

    def _refresh_nav(self) -> None:
        from .vc_effect_meta import effect_name
        self._combo.blockSignals(True)
        self._combo.clear()
        for i, fid in enumerate(self._fids):
            self._combo.addItem(f"{i + 1}.  {effect_name(fid)}")
        if self._fids:
            self._current = max(0, min(self._current, len(self._fids) - 1))
            self._combo.setCurrentIndex(self._current)
        self._combo.blockSignals(False)

        multi = len(self._fids) > 1
        self._prev.setEnabled(multi)
        self._next.setEnabled(multi)
        self._combo.setEnabled(bool(self._fids))
        self._refresh_body()

    def _refresh_body(self) -> None:
        if not self._fids:
            self._body.setText(
                "Zieh einen oder mehrere Effekte hierher.\n\n"
                "Oben blaetterst du mit Dropdown oder –  / +  durch die zugewiesenen "
                "Effekte. Parameter-Editor, Vorschau und Tempo-Modus folgen.")
            return
        from .vc_effect_meta import effect_name
        fid = self._fids[self._current]
        self._body.setText(
            f"„{effect_name(fid)}“ geladen  "
            f"({self._current + 1}/{len(self._fids)}).\n\n"
            "Parameter-Editor, Vorschau und Tempo-Modus folgen in den naechsten Schritten.")
