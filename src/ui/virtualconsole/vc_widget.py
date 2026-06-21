"""VCWidget — Basisklasse aller Virtual-Console-Widgets."""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QMenu, QSizePolicy
from PySide6.QtCore import Qt, QPoint, QRect, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QCursor, QAction


def midi_binding_matches(msg, midi_type: str, midi_ch: int, midi_data1: int) -> bool:
    """Gemeinsame MIDI-Bindungs-Prüfung (T-6: war byte-gleich in VCButton/VCColor).

    note_on bindet auch note_off (für Press/Release); Kanal 0 = alle Kanäle."""
    if midi_data1 is None or midi_data1 < 0:
        return False
    if midi_type == "note_on":
        if msg.msg_type not in ("note_on", "note_off"):
            return False
    elif midi_type != msg.msg_type:
        return False
    if midi_ch != 0 and midi_ch != msg.channel:
        return False
    return midi_data1 == msg.data1


class VCWidget(QFrame):
    """Basisklasse — abstrakt, nicht direkt instanziieren."""

    HANDLE_SIZE = 8
    MIN_SIZE = (40, 30)

    # Globaler Touch-/Maus-Lock im Run-Modus: True = nur Anzeige, keine Steuerung
    # ueber den Touchscreen (APC/MIDI steuert weiter). Vom VC-Toolbar gesetzt.
    input_locked = False

    def _run_input_blocked(self) -> bool:
        """True, wenn im Run-Modus Touch/Maus gesperrt ist (Display-only)."""
        return (not self._edit_mode) and VCWidget.input_locked

    moved = Signal(int, int)       # x, y
    resized = Signal(int, int)     # w, h
    delete_requested = Signal()

    def __init__(self, caption: str = "", parent=None):
        super().__init__(parent)
        self.caption = caption
        # Bank/Page-Zugehoerigkeit: -1 = auf allen Banks sichtbar (Default,
        # rueckwaertskompatibel), 0..9 = nur auf dieser Bank (= Executor-Page).
        self.bank = -1
        self._edit_mode = False
        self._dragging = False
        self._resizing = False
        self._selected = False
        self._effect_highlight = False   # Glow: „gehoert zum selben Effekt"
        self._snap_grid = 0      # 0 = kein Snap, sonst Grid-Größe in Pixel
        self._drag_start = QPoint()
        self._orig_rect = QRect()
        self._pre_edit_snapshot = None   # Canvas-Stand vor Move/Resize (fuer Undo)
        self._bg_color = QColor("#2a2a2a")
        self._fg_color = QColor("#ffffff")
        self.setFrameShape(QFrame.Shape.Box)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    # ── Edit Mode ─────────────────────────────────────────────────────────────

    def set_edit_mode(self, enabled: bool):
        self._edit_mode = enabled
        if not enabled:
            self._selected = False
            self.set_effect_highlight(False)   # keine Hervorhebung im Betrieb
        self.setCursor(Qt.CursorShape.SizeAllCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.update()
        for child in self.findChildren(VCWidget):
            child.set_edit_mode(enabled)

    def set_snap_grid(self, grid: int):
        """Setzt die Snap-Grid-Größe (0 = kein Snap)."""
        self._snap_grid = grid
        for child in self.findChildren(VCWidget):
            child.set_snap_grid(grid)

    # ── Farben ────────────────────────────────────────────────────────────────

    def set_background_color(self, color: QColor):
        self._bg_color = color
        self.update()

    def set_foreground_color(self, color: QColor):
        self._fg_color = color
        self.update()

    # ── Maus-Events (Drag + Resize) ───────────────────────────────────────────

    def mousePressEvent(self, event):
        if not self._edit_mode:
            super().mousePressEvent(event)
            return
        if event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._deselect_siblings()
            self._selected = True
            self.update()
            self._notify_effect_highlight()    # Gruppe „beeinflusst denselben Effekt"
            pos = event.position().toPoint()
            if self._is_resize_handle(pos):
                self._resizing = True
            else:
                self._dragging = True
            self._drag_start = event.globalPosition().toPoint()
            self._orig_rect = self.geometry()
            # Vorher-Stand fuer Undo erfassen (erst bei echter Geometrie-Aenderung
            # auf Release tatsaechlich auf den Undo-Stapel gelegt).
            self._pre_edit_snapshot = None
            _canvas = self._find_canvas()
            if _canvas is not None and hasattr(_canvas, "to_dict"):
                try:
                    self._pre_edit_snapshot = _canvas.to_dict()
                except Exception:
                    self._pre_edit_snapshot = None
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._edit_mode:
            return
        delta = event.globalPosition().toPoint() - self._drag_start
        if self._dragging and self.parent():
            nx = max(0, self._orig_rect.x() + delta.x())
            ny = max(0, self._orig_rect.y() + delta.y())
            if self._snap_grid > 0:
                nx = round(nx / self._snap_grid) * self._snap_grid
                ny = round(ny / self._snap_grid) * self._snap_grid
            self.move(nx, ny)
            self.moved.emit(nx, ny)
        elif self._resizing:
            nw = max(self.MIN_SIZE[0], self._orig_rect.width() + delta.x())
            nh = max(self.MIN_SIZE[1], self._orig_rect.height() + delta.y())
            if self._snap_grid > 0:
                nw = round(nw / self._snap_grid) * self._snap_grid
                nh = round(nh / self._snap_grid) * self._snap_grid
            self.resize(nw, nh)
            self.resized.emit(nw, nh)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if self._edit_mode and event.button() == Qt.MouseButton.LeftButton:
            self._edit_properties()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event):
        was_dragging = self._dragging
        was_resizing = self._resizing
        self._dragging = False
        self._resizing = False
        # Verschieben/Groesse ist ein Undo-Punkt — aber nur bei wirklicher
        # Geometrie-Aenderung (reiner Auswahl-Klick erzeugt keinen).
        if (was_dragging or was_resizing) and self._edit_mode \
                and self.geometry() != self._orig_rect:
            _snap = getattr(self, "_pre_edit_snapshot", None)
            _canvas = self._find_canvas()
            if _canvas is not None and _snap is not None \
                    and hasattr(_canvas, "push_undo_snapshot"):
                _canvas.push_undo_snapshot(_snap)
        self._pre_edit_snapshot = None
        # FRM-01: nach einem Drag pruefen, ob das Widget in einen Frame hinein
        # oder aus einem Frame heraus gezogen wurde (Reparenting per Hit-Test).
        if was_dragging and self._edit_mode:
            canvas = self._find_canvas()
            if canvas is not None and hasattr(canvas, "handle_drag_drop"):
                try:
                    canvas.handle_drag_drop(self)
                except Exception as e:
                    print(f"[VCWidget] drag-drop reparent error: {e}")
        event.accept()

    def _deselect_siblings(self):
        """Deselektiert alle anderen VCWidgets im selben Parent."""
        if self.parent() is not None:
            for sibling in self.parent().findChildren(VCWidget):
                if sibling is not self and sibling._selected:
                    sibling._selected = False
                    sibling.update()

    def _is_resize_handle(self, pos: QPoint) -> bool:
        r = self.rect()
        hs = self.HANDLE_SIZE
        return (r.right() - hs <= pos.x() <= r.right() and
                r.bottom() - hs <= pos.y() <= r.bottom())

    def _show_context_menu(self, global_pos: QPoint):
        menu = QMenu(self)
        menu.addAction("Einstellungen...").triggered.connect(self._edit_properties)
        # Grafische Widget-Galerie: nur wenn fuer den aktuellen Aspekt mehrere
        # Bedien-Element-Typen passen (z. B. Tempo -> Speed-Rad ODER Fader).
        _canvas = self._find_canvas()
        if _canvas is not None and hasattr(_canvas, "replace_widget_type"):
            try:
                _aspect = _canvas._widget_aspect(self)
            except Exception:
                _aspect = None
            if _aspect:
                from .vc_effect_meta import widget_choices, ControlOption
                _choices = widget_choices(ControlOption(_aspect, ""))
                if len(_choices) > 1:
                    menu.addAction("↔ Widget ändern…").triggered.connect(
                        lambda checked=False, a=_aspect, c=list(_choices):
                        self._change_widget_type(a, c))
        # MLV-01: ist das Widget an einen Effekt mit Live-Parametern gebunden,
        # bietet das Menue einen Live-Editor (Parameter/Aktionen -> erzeugt
        # automatisch VC-Bedienelemente, MLV-02).
        if self.is_effect_bound():
            _fid = self.live_effect_function_id()
            try:
                from src.core.engine import effect_live
                _has_live = bool(effect_live.list_params(_fid))
            except Exception:
                _has_live = False
            if _has_live:
                menu.addAction("⚡ Live-Parameter…").triggered.connect(
                    lambda checked=False, f=_fid: self._open_live_editor(f))
        if self.supports_midi_teach():
            menu.addAction("🎹 MIDI Teach...").triggered.connect(self._teach_midi)
        if self.supports_key_teach():
            menu.addAction("⌨ Taste zuweisen...").triggered.connect(self._teach_key)
        # Bank-Zuweisung (einheitlich fuer alle Widget-Typen)
        bank_menu = menu.addMenu("Bank")
        act_all = bank_menu.addAction("Alle Banks")
        act_all.setCheckable(True)
        act_all.setChecked(self.bank < 0)
        act_all.triggered.connect(lambda: self._set_bank(-1))
        bank_menu.addSeparator()
        for i in range(10):
            a = bank_menu.addAction(f"Bank {i + 1}")
            a.setCheckable(True)
            a.setChecked(self.bank == i)
            a.triggered.connect(lambda checked=False, b=i: self._set_bank(b))
        menu.addAction("Löschen").triggered.connect(self.delete_requested.emit)
        menu.addAction("Vordergrund-Farbe").triggered.connect(self._pick_fg)
        menu.addAction("Hintergrund-Farbe").triggered.connect(self._pick_bg)
        menu.exec(global_pos)

    def _set_bank(self, b: int):
        """Weist das Widget einer Bank zu (-1 = alle) und aktualisiert die
        Sichtbarkeit ueber die Canvas."""
        self.bank = int(b)
        p = self.parent()
        while p is not None:
            if hasattr(p, "_apply_bank_visibility"):
                p._apply_bank_visibility()
                break
            p = p.parent()
        self.update()

    def handle_midi(self, msg) -> bool:
        """Verarbeitet eine MIDI-Message. Gibt True zurück wenn konsumiert."""
        return False

    # ── MIDI Teach (Rechtsklick → Teach mit APC-mini-Abbild) ───────────────────

    def supports_midi_teach(self) -> bool:
        """True, wenn dieses Widget eine MIDI-Bindung unterstützt."""
        return False

    def current_midi_binding(self):
        """Aktuelle Bindung als (msg_type, channel, data1) oder None."""
        return None

    def apply_midi_binding(self, msg_type, channel, data1):
        """Setzt die MIDI-Bindung. data1 < 0 / None = 'entfernen'.
        Subklassen überschreiben dies."""
        pass

    def _midi_teach_kinds(self):
        """Welche APC-Element-Typen darf dieses Widget binden (note/cc)."""
        return ("note", "cc")

    def _teach_midi(self):
        from PySide6.QtWidgets import QDialog
        from src.ui.widgets.midi_teach_dialog import MidiTeachDialog
        dlg = MidiTeachDialog(self, current=self.current_midi_binding(),
                              accept_kinds=self._midi_teach_kinds(),
                              title=f"MIDI Teach — {self.caption}")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            b = dlg.result_binding
            if b is None:
                self.apply_midi_binding(None, 0, -1)
            else:
                self.apply_midi_binding(b[0], b[1], b[2])
            self.update()

    # ── Keyboard-Teach (Rechtsklick → Taste zuweisen) ──────────────────────────
    #
    # Spiegelbild des MIDI-Teach: ein app-weiter Hotkey-Filter
    # (core/input/keyboard_hotkeys.py) verteilt Tastendrücke an die Canvas,
    # diese ruft handle_key() der Widgets der aktiven Bank auf.

    def supports_key_teach(self) -> bool:
        """True, wenn dieses Widget eine Tastatur-Bindung unterstützt."""
        return False

    def current_key_binding(self) -> str:
        """Aktuelle Bindung als Sequenz-String ("Ctrl+F5") oder ""."""
        return ""

    def apply_key_binding(self, seq: str):
        """Setzt die Tastatur-Bindung ("" = entfernen). Subklassen überschreiben."""
        pass

    def handle_key(self, seq: str, pressed: bool) -> bool:
        """Verarbeitet einen Hotkey. True = konsumiert (Bindung passt)."""
        return False

    def _teach_key(self):
        from PySide6.QtWidgets import QDialog
        from src.ui.widgets.key_teach_dialog import KeyTeachDialog
        canvas = self._find_canvas()
        conflict_check = None
        if canvas is not None and hasattr(canvas, "key_binding_owners"):
            conflict_check = lambda seq: canvas.key_binding_owners(seq, exclude=self)
        dlg = KeyTeachDialog(self, current=self.current_key_binding(),
                             conflict_check=conflict_check,
                             title=f"Taste zuweisen — {self.caption}")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.apply_key_binding(dlg.result_sequence or "")
            self.update()

    def _open_properties(self):
        pass  # override in subclasses

    def _edit_properties(self):
        """Eigenschafts-Dialog MIT Undo-Punkt: erfasst den Vorher-Stand und legt ihn
        nur dann auf den Undo-Stapel, wenn der Dialog wirklich etwas geaendert hat.
        Ueber Doppelklick + Kontextmenue aufgerufen (statt _open_properties direkt)."""
        _canvas = self._find_canvas()
        _before = None
        if _canvas is not None and hasattr(_canvas, "to_dict"):
            try:
                _before = _canvas.to_dict()
            except Exception:
                _before = None
        self._open_properties()
        if _canvas is not None and _before is not None \
                and hasattr(_canvas, "push_undo_snapshot"):
            try:
                if _canvas.to_dict() != _before:
                    _canvas.push_undo_snapshot(_before)
            except Exception:
                pass

    def _change_widget_type(self, aspect, choices):
        """Oeffnet die grafische Widget-Galerie und tauscht den Typ dieses Widgets
        bindungserhaltend (VCCanvas.replace_widget_type) — ein Undo-Schritt."""
        canvas = self._find_canvas()
        if canvas is None or not hasattr(canvas, "replace_widget_type"):
            return
        from .vc_widget_gallery import VCWidgetGallery
        chosen = VCWidgetGallery(choices, current=self.__class__.__name__,
                                 parent=self).run()
        if chosen and chosen != self.__class__.__name__:
            canvas.replace_widget_type(self, chosen, aspect)

    # ── Effekt-Gruppen-Hervorhebung ───────────────────────────────────────────

    def set_effect_highlight(self, on: bool):
        """Hebt dieses Widget als „gehoert zum selben Effekt" hervor (oranger
        Glow-Halo). Wird vom Canvas gesetzt, wenn ein Widget/Effekt ausgewaehlt
        ist (effect_binding-Gruppe). Universell ohne paintEvent-Eingriff via
        QGraphicsDropShadowEffect."""
        on = bool(on)
        if on == getattr(self, "_effect_highlight", False):
            return
        self._effect_highlight = on
        try:
            if on:
                from PySide6.QtWidgets import QGraphicsDropShadowEffect
                from PySide6.QtGui import QColor
                eff = QGraphicsDropShadowEffect(self)
                eff.setColor(QColor("#ff9500"))   # Amber/Orange
                eff.setBlurRadius(30)
                eff.setOffset(0, 0)
                self.setGraphicsEffect(eff)
            else:
                self.setGraphicsEffect(None)
        except Exception:
            pass
        self.update()

    def _notify_effect_highlight(self):
        """Bittet den Canvas, alle Widgets hervorzuheben, die denselben Effekt
        steuern wie dieses (Selektion -> Gruppe sichtbar). Ohne Effekt-Bindung
        wird eine bestehende Hervorhebung aufgehoben."""
        canvas = self._find_canvas()
        if canvas is None or not hasattr(canvas, "highlight_effects"):
            return
        try:
            ids = canvas._effect_ids_of(self)
        except Exception:
            ids = set()
        canvas.highlight_effects(ids, exclude=self)

    # ── MLV: Matrix-/Effekt-Live-Editor (Phase 2) ──────────────────────────────

    def is_effect_bound(self) -> bool:
        """True, wenn dieses Widget an einen Effekt gebunden ist (Subklassen
        ueberschreiben: Button mit Funktions-/Effekt-Aktion, Slider im EFFECT_*-Modus)."""
        return False

    def live_effect_function_id(self) -> "int | None":
        """function_id des gebundenen Effekts (oder None = aktiver Effekt)."""
        return None

    def _find_canvas(self):
        """Naechster Vorfahr, der Live-Bedienelemente erzeugen kann (VCCanvas)."""
        p = self.parent()
        while p is not None:
            if hasattr(p, "add_live_controls"):
                return p
            p = p.parent()
        return None

    def _open_live_editor(self, function_id):
        """Oeffnet den Matrix-Live-Editor-Dialog und laesst die ausgewaehlten
        Parameter/Aktionen als VC-Bedienelemente erzeugen (MLV-01/02)."""
        from PySide6.QtWidgets import QDialog
        from src.ui.widgets.matrix_live_dialog import MatrixLiveDialog
        dlg = MatrixLiveDialog(function_id, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        canvas = self._find_canvas()
        if canvas is None:
            return
        canvas.add_live_controls(function_id, dlg.selected_param_keys(),
                                 dlg.selected_action_keys(), origin=self)

    def _pick_fg(self):
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(self._fg_color, self, "Vordergrundfarbe")
        if c.isValid():
            self.set_foreground_color(c)

    def _pick_bg(self):
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(self._bg_color, self, "Hintergrundfarbe")
        if c.isValid():
            self.set_background_color(c)

    # ── Painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg_color)
        if self._edit_mode:
            hs = self.HANDLE_SIZE
            r = self.rect()
            p.fillRect(r.right() - hs, r.bottom() - hs, hs, hs, QColor("#0088ff"))
            if self._selected:
                p.setPen(QPen(QColor("#58d68d"), 2, Qt.PenStyle.SolidLine))
            else:
                p.setPen(QPen(QColor("#0088ff"), 1, Qt.PenStyle.DashLine))
            p.drawRect(r.adjusted(0, 0, -1, -1))
        p.end()

    # ── Serialisierung ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        g = self.geometry()
        return {
            "type": self.__class__.__name__,
            "caption": self.caption,
            "bank": self.bank,
            "x": g.x(), "y": g.y(),
            "w": g.width(), "h": g.height(),
            "bg": self._bg_color.name(),
            "fg": self._fg_color.name(),
        }

    def apply_dict(self, d: dict):
        self.caption = d.get("caption", self.caption)
        try:
            self.bank = int(d.get("bank", -1))
        except (TypeError, ValueError):
            self.bank = -1
        self.setGeometry(d.get("x", 0), d.get("y", 0),
                         d.get("w", 120), d.get("h", 60))
        if "bg" in d:
            self._bg_color = QColor(d["bg"])
        if "fg" in d:
            self._fg_color = QColor(d["fg"])
