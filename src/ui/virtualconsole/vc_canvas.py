"""VCCanvas — Free-form layout surface for all VC widgets."""
from __future__ import annotations
import json
from PySide6.QtWidgets import (QWidget, QScrollArea, QMenu, QFileDialog,
                                QMessageBox, QInputDialog, QSizePolicy, QRubberBand)
from PySide6.QtCore import Qt, QPoint, QRect, QSize, Signal
from PySide6.QtGui import QPainter, QColor, QAction, QPen

from .vc_widget import VCWidget


WIDGET_REGISTRY: dict[str, type] = {}

def _register():
    from .vc_button   import VCButton
    from .vc_slider   import VCSlider
    from .vc_xypad    import VCXYPad
    from .vc_label    import VCLabel
    from .vc_cuelist  import VCCueList
    from .vc_speedial import VCSpeedDial
    from .vc_frame    import VCFrame
    from .vc_color    import VCColor
    from .vc_encoder  import VCEncoder
    from .vc_color_list import VCColorList
    from .vc_chase_builder import VCChaseBuilder
    from .vc_song_info import VCSongInfo
    from .vc_bpm_display import VCBpmDisplay
    from .vc_bus_selector import VCBusSelector
    from .vc_tempo_bus_controller import VCTempoBusController
    from .vc_effect_colors import VCEffectColors
    from .vc_stepper import VCStepper
    from .vc_effect_editor import VCEffectEditor
    from .vc_effect_display import VCEffectDisplay
    WIDGET_REGISTRY.update({
        "VCButton":   VCButton,
        "VCSlider":   VCSlider,
        "VCXYPad":    VCXYPad,
        "VCLabel":    VCLabel,
        "VCCueList":  VCCueList,
        "VCSpeedDial":VCSpeedDial,
        "VCEncoder":  VCEncoder,
        "VCStepper":  VCStepper,
        "VCColor":    VCColor,
        "VCColorList":VCColorList,
        "VCChaseBuilder": VCChaseBuilder,
        "VCSongInfo": VCSongInfo,
        "VCBpmDisplay": VCBpmDisplay,
        "VCBusSelector": VCBusSelector,
        "VCTempoBusController": VCTempoBusController,
        "VCEffectColors": VCEffectColors,
        "VCFrame":    VCFrame,
        "VCEffectEditor": VCEffectEditor,
        "VCEffectDisplay": VCEffectDisplay,
    })

_register()


class _DragTargetOverlay(QWidget):
    """Transientes Overlay fuers Drag-Feedback: zeichnet einen farbigen Rahmen
    ueber dem Widget, ueber das gerade ein Effekt gezogen wird.
      gruen (#22c55e) = der Effekt bindet hier (gueltiges Ziel),
      rot  (#ef4444) = dieses Widget nimmt den Effekt nicht an.
    ``WA_TransparentForMouseEvents`` haelt es aus jedem Hit-Test heraus — weder
    ``childAt`` (Drop-Ziel-Suche) noch der Drop selbst sehen das Overlay, und es
    faengt keine Maus-/Drag-Events ab."""

    def __init__(self, parent):
        super().__init__(parent)
        self._valid = True
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide()

    def show_over(self, rect: QRect, valid: bool):
        self._valid = bool(valid)
        self.setGeometry(rect)
        self.raise_()
        self.show()
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        col = QColor("#22c55e") if self._valid else QColor("#ef4444")
        fill = QColor(col)
        fill.setAlpha(40)
        r = self.rect().adjusted(1, 1, -2, -2)
        p.setPen(QPen(col, 2))
        p.setBrush(fill)
        p.drawRoundedRect(r, 6, 6)


class VCCanvas(QWidget):
    """The free-form canvas. Widgets are placed as direct children."""

    GRID = 8

    # Signale nach außen (für VirtualConsoleView)
    midi_learn_done = Signal()          # MIDI-Learn für Button abgeschlossen
    snapshot_assign_done = Signal()     # Snapshot-Assign abgeschlossen
    function_assign_done = Signal()     # Funktions-Assign abgeschlossen
    snap_assign_done = Signal()         # Bibliothek-Snap-Assign abgeschlossen
    bank_changed = Signal(int)          # aktive Bank (0-basiert) gewechselt
    area_selected = Signal(str, int, int, int, int)  # (tool, x, y, w, h) aufgezogener Bereich
    widget_selected = Signal(object)    # VC-Widget gewaehlt (None = Auswahl aufgehoben) -> Inspector-Panel
    # Intern: MIDI aus dem Dispatch-Thread thread-sicher in den UI-Thread holen
    _midi_received = Signal(object)
    # Intern: Page/Bank-Wechsel der Engine (kann aus MIDI-Thread kommen)
    _bank_change_sig = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._edit_mode = False
        self._snap_to_grid = False
        self._active_bank = 0
        # Undo/Redo: Snapshot-Verlauf der VC-Layouts (Hinzufuegen/Loeschen/…).
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []
        self._restoring = False
        self._UNDO_MAX = 50
        self.setMinimumSize(QSize(1200, 800))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self._bg = QColor("#0d1117")
        self.setAcceptDrops(True)

        # Drag-Feedback: Overlay, das beim Effekt-Drag das Ziel-Widget gruen
        # (bindet hier) bzw. rot (nimmt der Effekt nicht an) umrahmt. Lazy erzeugt.
        self._drag_overlay: _DragTargetOverlay | None = None
        self._drag_caps_fid: int | None = None   # gecachte Capabilities pro Drag
        self._drag_caps = None

        # MIDI-Learn-Modus
        self._midi_learn_btn = None       # VCButton das auf MIDI wartet

        # Snapshot-Assign-Modus
        self._assign_snapshot_index: int | None = None  # welcher Snap zugewiesen wird
        # Funktions-Assign-Modus (Effekt/Matrix/Scene auf VC-Button legen)
        self._assign_function_id: int | None = None
        # Bibliothek-Snap-Assign-Modus (Farbe/Look auf VC-Button legen)
        self._assign_snap_id: int | None = None
        self._awaiting_button_click_for: str | None = None
        # Canvas-Editor: Bereich aufziehen (Rubber-Band) fuer z. B. Color-Chase
        self._area_tool: str | None = None
        self._area_origin: QPoint | None = None
        self._rubber: QRubberBand | None = None

        # MIDI aus dem Dispatch-Thread sicher in den UI-Thread marshallen.
        # (Cross-Thread-Signal -> automatisch QueuedConnection -> _handle_midi laeuft im UI-Thread)
        self._midi_received.connect(self._handle_midi)
        self._bank_change_sig.connect(self.set_active_bank)
        self._setup_midi()
        self._setup_keyboard()
        self._setup_engine_page()

    # ── MIDI ─────────────────────────────────────────────────────────────────

    def _setup_midi(self):
        self._mm = None
        try:
            from src.core.midi.midi_manager import get_midi_manager
            self._mm = get_midi_manager()
            self._mm.subscribe(self._on_midi_raw)
            # Beim Zerstoeren der Canvas zuverlaessig abmelden (sonst Leak +
            # MIDI-Dispatch auf bereits geloeschte Widgets → Crash/Doppeltrigger).
            self.destroyed.connect(lambda *_: self._teardown_midi())
        except Exception as e:
            print(f"[VCCanvas] MIDI-Subscribe-Fehler: {e}")

    def _teardown_midi(self):
        mm = getattr(self, "_mm", None)
        if mm is not None:
            try:
                mm.unsubscribe(self._on_midi_raw)
            except Exception:
                pass
            self._mm = None

    def closeEvent(self, event):
        self._teardown_midi()
        self._teardown_keyboard()
        super().closeEvent(event)

    # ── Keyboard-Hotkeys (Feature: Tasten in der VC patchen) ──────────────────
    #
    # Gleiche Architektur wie MIDI: ein zentraler App-Filter
    # (core/input/keyboard_hotkeys.py) liefert (seq, pressed) — die Canvas
    # verteilt an die Widgets der aktiven Bank. Textfelder/Modal-Dialoge
    # blockt bereits der Filter.

    def _setup_keyboard(self):
        self._kb = None
        try:
            from src.core.input.keyboard_hotkeys import get_keyboard_hotkeys
            self._kb = get_keyboard_hotkeys()
            self._kb.subscribe(self._on_hotkey)
            self.destroyed.connect(lambda *_: self._teardown_keyboard())
        except Exception as e:
            print(f"[VCCanvas] Keyboard-Subscribe-Fehler: {e}")

    def _teardown_keyboard(self):
        kb = getattr(self, "_kb", None)
        if kb is not None:
            try:
                kb.unsubscribe(self._on_hotkey)
            except Exception:
                pass
            self._kb = None

    def _on_hotkey(self, seq: str, pressed: bool) -> bool:
        """Hotkey an die Widgets der aktiven Bank verteilen (wie _handle_midi)."""
        if not self.isVisible():
            return False
        try:
            widgets = self.findChildren(VCWidget)
        except RuntimeError:
            self._teardown_keyboard()
            return False
        consumed = False
        for widget in widgets:
            if not self.on_active_bank(widget):
                continue
            try:
                if widget.handle_key(seq, pressed):
                    consumed = True
            except Exception as e:
                print(f"[VCCanvas] handle_key error: {e}")
        return consumed

    def key_binding_owners(self, seq: str, exclude=None) -> list[str]:
        """Captions aller Widgets, die `seq` bereits gebunden haben
        (Konfliktprüfung für den Tasten-Lern-Dialog)."""
        owners: list[str] = []
        if not seq:
            return owners
        try:
            widgets = self.findChildren(VCWidget)
        except RuntimeError:
            return owners
        for w in widgets:
            if w is exclude:
                continue
            try:
                if w.current_key_binding() == seq:
                    owners.append(w.caption or w.__class__.__name__)
            except Exception:
                continue
        return owners

    # ── Bank/Page (= Executor-Page der Engine) ────────────────────────────────

    def _setup_engine_page(self):
        """Koppelt die VC-Bank an die Executor-Page der Engine: ein Page-Wechsel
        (z.B. via APC-Page-Button) blendet die passenden VC-Widgets ein."""
        self._pe = None
        try:
            from src.core.app_state import get_state
            pe = getattr(get_state(), "playback_engine", None)
            if pe is not None:
                self._pe = pe
                self._active_bank = pe.current_page
                pe.subscribe_page(self._on_engine_page)
                self.destroyed.connect(lambda *_: self._teardown_engine_page())
        except Exception as e:
            print(f"[VCCanvas] Page-Subscribe-Fehler: {e}")

    def _teardown_engine_page(self):
        pe = getattr(self, "_pe", None)
        if pe is not None:
            try:
                pe.unsubscribe_page(self._on_engine_page)
            except Exception:
                pass
            self._pe = None

    def _on_engine_page(self, page_idx: int):
        # Kann aus dem MIDI-Thread kommen -> thread-sicher in den UI-Thread.
        self._bank_change_sig.emit(int(page_idx))

    def set_active_bank(self, b: int):
        b = max(0, min(9, int(b)))
        self._active_bank = b
        self._apply_bank_visibility()
        self._rearm_slider_pickup()    # Soft-Takeover: Fader nach Seitenwechsel neu armieren
        self.update()
        self.bank_changed.emit(b)

    def _rearm_slider_pickup(self):
        """Soft-Takeover: nach einem Bank-/Seitenwechsel alle Fader neu armieren,
        damit ein nicht-motorisierter Controller keine Wertsprünge auslöst (der
        physische Fader steht ggf. woanders als der VC-Wert der neuen Seite).
        arm_pickup() prüft selbst, ob Soft-Takeover global aktiv ist."""
        from .vc_slider import VCSlider
        for w in self.findChildren(VCSlider):
            try:
                w.arm_pickup()
            except Exception:
                pass

    @property
    def active_bank(self) -> int:
        return self._active_bank

    def on_active_bank(self, w) -> bool:
        """True, wenn das Widget auf der aktuell aktiven Bank sichtbar/aktiv ist
        (Bank < 0 = auf allen Banks)."""
        bnk = getattr(w, "bank", -1)
        return bnk is None or bnk < 0 or bnk == self._active_bank

    def _apply_bank_visibility(self):
        for child in self.findChildren(
            VCWidget, options=Qt.FindChildOption.FindDirectChildrenOnly
        ):
            child.setVisible(self.on_active_bank(child))

    def _on_midi_raw(self, msg):
        # Laeuft im MidiDispatch-Thread (kein Qt-Event-Loop!). QTimer.singleShot
        # wuerde hier NIE feuern. Ein Qt-Signal marshallt thread-sicher in den UI-Thread.
        self._midi_received.emit(msg)

    def _handle_midi(self, msg):
        # MIDI-Learn: nächste Message wird dem bewaffneten Button zugewiesen
        if self._midi_learn_btn is not None:
            btn = self._midi_learn_btn
            self._midi_learn_btn = None
            btn.accept_midi(msg.channel, msg.data1, msg.msg_type)
            self.midi_learn_done.emit()
            return

        # Dispatch an alle VCWidgets (VCButton, VCSlider, …)
        try:
            widgets = self.findChildren(VCWidget)
        except RuntimeError:
            # Canvas wird gerade zerstoert — abmelden und aussteigen.
            self._teardown_midi()
            return
        for widget in widgets:
            # Nur Widgets der aktiven Bank reagieren (verdeckte Banks stumm).
            if not self.on_active_bank(widget):
                continue
            widget.handle_midi(msg)

    # ── MIDI-Learn-Modus ─────────────────────────────────────────────────────

    def start_midi_learn(self):
        """
        Aktiviert MIDI-Learn: der nächste Klick auf einen VCButton bewaffnet ihn,
        die darauf folgende MIDI-Message wird ihm zugewiesen.
        """
        self._midi_learn_btn = None
        # Signalisiere allen Buttons dass sie für MIDI-Learn klickbar sind
        self._awaiting_button_click_for = "midi_learn"
        self.setCursor(Qt.CursorShape.CrossCursor)

    def cancel_midi_learn(self):
        if self._midi_learn_btn is not None:
            try:
                self._midi_learn_btn._midi_armed = False
                self._midi_learn_btn.update()
            except Exception:
                pass
        self._midi_learn_btn = None
        self._awaiting_button_click_for = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    # ── Snapshot-Assign-Modus ─────────────────────────────────────────────────

    def start_snapshot_assign(self, snapshot_index: int):
        """
        Aktiviert Assign-Modus: nächster Klick auf einen VCButton weist ihm
        den angegebenen Snapshot zu.
        """
        self._assign_snapshot_index = snapshot_index
        self._awaiting_button_click_for = "snapshot"
        self.setCursor(Qt.CursorShape.CrossCursor)

    def cancel_snapshot_assign(self):
        self._assign_snapshot_index = None
        self._awaiting_button_click_for = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    # ── Funktions-Assign-Modus ────────────────────────────────────────────────

    def start_function_assign(self, function_id: int):
        """Aktiviert Assign-Modus: nächster Klick auf einen VCButton macht ihn
        zum Funktions-Toggle für die gewählte Funktion (Effekt/Matrix/Scene)."""
        self._assign_function_id = function_id
        self._awaiting_button_click_for = "function"
        self.setCursor(Qt.CursorShape.CrossCursor)

    def cancel_function_assign(self):
        self._assign_function_id = None
        self._awaiting_button_click_for = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    # ── Bibliothek-Snap-Assign-Modus ──────────────────────────────────────────

    def start_snap_assign(self, snap_id: int):
        """Aktiviert Assign-Modus: naechster Klick auf einen VCButton macht ihn
        zur Farb-/Snap-Taste fuer den gewaehlten Bibliothek-Snap."""
        self._assign_snap_id = snap_id
        self._awaiting_button_click_for = "library_snap"
        self.setCursor(Qt.CursorShape.CrossCursor)

    def cancel_snap_assign(self):
        self._assign_snap_id = None
        self._awaiting_button_click_for = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    # ── Mausereignisse für Learn/Assign ──────────────────────────────────────

    def mousePressEvent(self, event):
        # Canvas-Editor: Bereich aufziehen (nur wenn ein Area-Tool armiert ist).
        if self._area_tool and self._edit_mode and event.button() == Qt.MouseButton.LeftButton:
            self._area_origin = event.position().toPoint()
            if self._rubber is None:
                self._rubber = QRubberBand(QRubberBand.Shape.Rectangle, self)
            self._rubber.setGeometry(QRect(self._area_origin, QSize()))
            self._rubber.show()
            return
        mode = getattr(self, "_awaiting_button_click_for", None)
        if mode and event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            if child is not None:
                # VCButton-Elternteil suchen
                from .vc_button import VCButton
                btn = child if isinstance(child, VCButton) else None
                p = child.parent()
                while p is not None and not isinstance(p, VCCanvas):
                    if isinstance(p, VCButton):
                        btn = p
                        break
                    p = p.parent()

                if btn is not None:
                    if mode == "midi_learn":
                        self._midi_learn_btn = btn
                        btn.arm_midi_learn()
                        self._awaiting_button_click_for = None
                        self.setCursor(Qt.CursorShape.ArrowCursor)
                        return
                    elif mode == "snapshot":
                        from .vc_button import ButtonAction
                        btn.action = ButtonAction.SNAPSHOT
                        btn.snapshot_index = self._assign_snapshot_index
                        btn.update()
                        self._assign_snapshot_index = None
                        self._awaiting_button_click_for = None
                        self.setCursor(Qt.CursorShape.ArrowCursor)
                        self.snapshot_assign_done.emit()
                        return
                    elif mode == "function":
                        from .vc_button import ButtonAction
                        btn.action = ButtonAction.FUNCTION_TOGGLE
                        btn.function_id = self._assign_function_id
                        # Caption auf den Funktionsnamen setzen (falls auffindbar).
                        try:
                            from src.core.engine.function_manager import get_function_manager
                            fn = get_function_manager().get(self._assign_function_id)
                            if fn is not None and getattr(btn, "caption", None) in (None, "", "Button"):
                                btn.caption = fn.name
                        except Exception:
                            pass
                        btn.update()
                        self._assign_function_id = None
                        self._awaiting_button_click_for = None
                        self.setCursor(Qt.CursorShape.ArrowCursor)
                        self.function_assign_done.emit()
                        return
                    elif mode == "library_snap":
                        self._assign_snap_to_button(btn, self._assign_snap_id)
                        self._assign_snap_id = None
                        self._awaiting_button_click_for = None
                        self.setCursor(Qt.CursorShape.ArrowCursor)
                        self.snap_assign_done.emit()
                        return

            # Klick ins Leere bricht Modus ab
            self.cancel_midi_learn()
            self.cancel_snapshot_assign()
            self.cancel_function_assign()
            self.cancel_snap_assign()
            return

        # Klick ins Leere (kein Widget) -> Effekt-Gruppen-Hervorhebung + Inspector-
        # Auswahl aufheben.
        if self._edit_mode and event.button() == Qt.MouseButton.LeftButton:
            self.clear_effect_highlight()
            self._on_widget_selected(None)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._rubber is not None and self._area_origin is not None:
            self._rubber.setGeometry(QRect(self._area_origin,
                                           event.position().toPoint()).normalized())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._rubber is not None and self._area_origin is not None:
            rect = QRect(self._area_origin, event.position().toPoint()).normalized()
            tool = self._area_tool
            self._rubber.hide()
            self._area_origin = None
            self._area_tool = None          # Tool nach einem Zug wieder entwaffnen
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if rect.width() >= 60 and rect.height() >= 60:
                self.area_selected.emit(tool or "", rect.x(), rect.y(),
                                        rect.width(), rect.height())
            return
        super().mouseReleaseEvent(event)

    def arm_area_tool(self, name: str):
        """Aktiviert das Aufziehen eines Bereichs (z. B. 'color_chase'). Der naechste
        Maus-Zug auf der Canvas loest ``area_selected`` aus."""
        self._area_tool = name
        self.setCursor(Qt.CursorShape.CrossCursor)

    def cancel_area_tool(self):
        self._area_tool = None
        self._area_origin = None
        if self._rubber is not None:
            self._rubber.hide()
        self.setCursor(Qt.CursorShape.ArrowCursor)

    # ── Edit mode ────────────────────────────────────────────────────────────

    def set_edit_mode(self, enabled: bool):
        self._edit_mode = enabled
        for child in self.findChildren(VCWidget):
            child.set_edit_mode(enabled)
        if not enabled:
            self._on_widget_selected(None)   # Inspector leeren, wenn Edit-Modus aus
        self.update()

    def _on_widget_selected(self, w):
        """Von einem VCWidget beim Anklicken (oder vom Canvas bei Klick ins Leere mit
        ``None``) aufgerufen; reicht die Auswahl als Signal an den VC-Host
        (Inspector-Panel) weiter."""
        self.widget_selected.emit(w)

    def set_snap_to_grid(self, enabled: bool):
        self._snap_to_grid = enabled
        grid = self.GRID if enabled else 0
        for child in self.findChildren(VCWidget):
            child.set_snap_grid(grid)

    # ── Drag & Drop ──────────────────────────────────────────────────────────

    _MIME_FUNCTION = "application/x-lightos-function"
    _MIME_SNAPSHOT  = "application/x-lightos-snapshot"
    _MIME_SNAP      = "application/x-lightos-snap"   # Bibliothek-Snap (Farbe/Look)

    def _accepts(self, md) -> bool:
        return (md.hasFormat(self._MIME_FUNCTION)
                or md.hasFormat(self._MIME_SNAPSHOT)
                or md.hasFormat(self._MIME_SNAP))

    def dragEnterEvent(self, event):
        if self._accepts(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._accepts(event.mimeData()):
            event.acceptProposedAction()
            self._update_drag_highlight(event)
        else:
            event.ignore()
            self._clear_drag_highlight()

    def dragLeaveEvent(self, event):
        # Verlaesst der Drag die Canvas (oder wird er abgebrochen), das Ziel-
        # Highlight ausblenden.
        self._clear_drag_highlight()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        # Beim Loslassen das Drag-Highlight in jedem Fall ausblenden (auch wenn der
        # Drop gleich verworfen wird) — sonst bliebe der Rahmen stehen.
        self._clear_drag_highlight()
        if not self._edit_mode:
            event.ignore()
            return

        md = event.mimeData()
        pos = event.position().toPoint()

        # Ziel-Widget unter dem Mauszeiger suchen (wie in mousePressEvent).
        # Funktions-Drops akzeptieren jetzt auch Farbe/Encoder/XY/SpeedDial — die
        # konkrete Zuordnung passiert in apply_drop je nach Widget-Typ.
        target = None
        droppable = self._droppable_types()
        child = self.childAt(pos)
        if child is not None:
            if isinstance(child, droppable):
                target = child
            else:
                p = child.parent()
                while p is not None and not isinstance(p, VCCanvas):
                    if isinstance(p, droppable):
                        target = p
                        break
                    p = p.parent()

        if md.hasFormat(self._MIME_FUNCTION):
            try:
                fid = int(md.data(self._MIME_FUNCTION).data().decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                event.ignore()
                return
            self.apply_drop(function_id=fid, pos=pos, target=target, interactive=True)

        elif md.hasFormat(self._MIME_SNAPSHOT):
            try:
                idx = int(md.data(self._MIME_SNAPSHOT).data().decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                event.ignore()
                return
            self.apply_drop(snapshot_index=idx, pos=pos, target=target)

        elif md.hasFormat(self._MIME_SNAP):
            try:
                sid = int(md.data(self._MIME_SNAP).data().decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                event.ignore()
                return
            self.apply_drop(snap_id=sid, pos=pos, target=target)

        else:
            event.ignore()
            return

        event.acceptProposedAction()

    @staticmethod
    def _droppable_types():
        """Widget-Typen, die einen Funktions-Drop direkt annehmen."""
        from .vc_button import VCButton
        from .vc_slider import VCSlider
        from .vc_color import VCColor
        from .vc_encoder import VCEncoder
        from .vc_xypad import VCXYPad
        from .vc_speedial import VCSpeedDial
        from .vc_stepper import VCStepper
        from .vc_effect_display import VCEffectDisplay
        from .vc_effect_editor import VCEffectEditor
        from .vc_bus_selector import VCBusSelector
        from .vc_tempo_bus_controller import VCTempoBusController
        return (VCButton, VCSlider, VCColor, VCEncoder, VCXYPad, VCSpeedDial,
                VCStepper, VCEffectDisplay, VCEffectEditor, VCBusSelector,
                VCTempoBusController)

    # ── Drag-Feedback: Ziel-Widget gruen/rot umrahmen ─────────────────────────
    #
    # Beim Ziehen eines Effekts (Funktions-MIME) ueber die Canvas zeigt ein
    # transientes Overlay, ob der Drop auf dem Widget unterm Cursor sinnvoll
    # bindet (gruen) oder nicht (rot) — bevor man loslaesst.

    def _update_drag_highlight(self, event):
        """dragMove-Handler: Ziel unterm Cursor ermitteln und gruen/rot umrahmen.
        Nur fuer Effekt-(Funktions-)Drops im Bearbeiten-Modus — Snapshot/Snap und
        der Betriebs-Modus zeigen kein Feedback (dort gilt die alte, stumme Logik)."""
        md = event.mimeData()
        if not self._edit_mode or not md.hasFormat(self._MIME_FUNCTION):
            self._clear_drag_highlight()
            return
        try:
            fid = int(md.data(self._MIME_FUNCTION).data().decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._clear_drag_highlight()
            return
        target, valid = self._drag_highlight_info(event.position().toPoint(), fid)
        if target is None:
            self._clear_drag_highlight()      # leere Flaeche -> kein Rahmen
        else:
            self._show_drag_highlight(target, valid)

    def _drag_highlight_info(self, pos, fid):
        """``(ziel_widget, gueltig)`` fuers Drag-Feedback an Position ``pos``.
        ``ziel_widget`` ist das naechste VCWidget unterm Cursor (oder None ueber
        leerer Flaeche); ``gueltig`` = der Effekt ``fid`` bindet dort sinnvoll."""
        w = self._vc_widget_under(pos)
        if w is None:
            return None, False
        return w, self._drag_target_valid(w, fid)

    def _vc_widget_under(self, pos):
        """Naechstes VCWidget unter ``pos`` (Qt-Innenkinder wie QSlider hochlaufen)."""
        w = self.childAt(pos)
        while w is not None and not isinstance(w, VCWidget):
            w = w.parent()
        return w if isinstance(w, VCWidget) else None

    def _drag_target_valid(self, w, fid) -> bool:
        """Nimmt das Widget ``w`` den Effekt ``fid`` sinnvoll an? Erst die
        Typ-Huerde (``_droppable_types``), dann der Capability-Abgleich gegen die
        Live-Faehigkeiten des Effekts."""
        if not isinstance(w, self._droppable_types()):
            return False
        return self._effect_fits_widget(w, self._drag_caps_for(fid))

    def _drag_caps_for(self, fid):
        """Capabilities des gezogenen Effekts — pro Drag gecacht, weil dragMove
        sehr oft feuert. ``_clear_drag_highlight`` setzt den Cache zurueck."""
        if self._drag_caps_fid != fid or self._drag_caps is None:
            from .vc_effect_meta import function_capabilities
            self._drag_caps_fid = fid
            self._drag_caps = function_capabilities(fid)
        return self._drag_caps

    @staticmethod
    def _caps_have_numeric_param(caps) -> bool:
        """Hat der Effekt einen live-steuerbaren Zahl-Parameter (Speed/Helligkeit/
        beliebiger int/float)? -> Fader/Encoder/Stepper koennen sinnvoll binden."""
        if getattr(caps, "has_speed", False) or getattr(caps, "has_intensity", False):
            return True
        for s in getattr(caps, "param_specs", []):
            if (getattr(s, "kind", "") in ("int", "float")
                    and getattr(s, "live_editable", True)
                    and getattr(s, "mappable", True)):
                return True
        return False

    @staticmethod
    def _caps_have_step_param(caps) -> bool:
        """Hat der Effekt einen diskreten int/bool/select-Parameter?"""
        return any(
            getattr(spec, "kind", "") in ("int", "bool", "select")
            and getattr(spec, "live_editable", True)
            and getattr(spec, "mappable", True)
            for spec in getattr(caps, "param_specs", [])
        )

    def _effect_fits_widget(self, w, caps) -> bool:
        """Capability-Abgleich Effekt<->Widget-Typ (vgl. _apply_function_to_special):
        spiegelt, was der Drop tatsaechlich binden wuerde."""
        from .vc_button import VCButton
        from .vc_slider import VCSlider
        from .vc_color import VCColor
        from .vc_encoder import VCEncoder
        from .vc_xypad import VCXYPad
        from .vc_speedial import VCSpeedDial
        from .vc_stepper import VCStepper
        from .vc_effect_display import VCEffectDisplay
        from .vc_effect_editor import VCEffectEditor
        from .vc_bus_selector import VCBusSelector
        if isinstance(w, (VCButton, VCEffectDisplay)):
            return True                                  # togglen / anzeigen: jede Funktion
        if isinstance(w, VCEffectEditor):
            return bool(getattr(caps, "has_params", False))
        if isinstance(w, (VCSlider, VCEncoder)):
            return self._caps_have_numeric_param(caps)   # braucht steuerbaren Zahl-Param
        if isinstance(w, VCStepper):
            return self._caps_have_step_param(caps)
        if isinstance(w, VCSpeedDial):
            return bool(getattr(caps, "has_speed", False))
        if isinstance(w, VCBusSelector):
            return bool(getattr(caps, "is_tempo_syncable", False))
        from .vc_tempo_bus_controller import VCTempoBusController
        if isinstance(w, VCTempoBusController):
            return bool(getattr(caps, "is_tempo_syncable", False))
        if isinstance(w, VCColor):
            return bool(getattr(caps, "has_colors", False))
        if isinstance(w, VCXYPad):
            return bool(getattr(caps, "has_movement", False))
        return False

    def _show_drag_highlight(self, target, valid: bool):
        """Overlay ueber ``target`` (in Canvas-Koordinaten) positionieren + zeigen."""
        if self._drag_overlay is None:
            self._drag_overlay = _DragTargetOverlay(self)
        tl = target.mapTo(self, QPoint(0, 0))
        self._drag_overlay.show_over(QRect(tl, target.size()), valid)

    def _clear_drag_highlight(self):
        """Drag-Feedback ausblenden und den Capability-Cache zuruecksetzen."""
        self._drag_caps_fid = None
        self._drag_caps = None
        if self._drag_overlay is not None:
            self._drag_overlay.hide()

    # ── apply_drop (testbar ohne echten Drag) ────────────────────────────────

    def apply_drop(self, *, function_id=None, snapshot_index=None, snap_id=None,
                   pos=None, target=None, interactive: bool = False):
        """Fuehrt den Drop aus: Funktion, Snapshot oder Bibliothek-Snap (Farbe/Look)
        auf ein Ziel-Widget oder das leere Canvas anwenden.

        Args:
            function_id:    Funktions-ID eines Effekts/Matrix/Scene (oder None).
            snapshot_index: Snapshot-Index (oder None).
            snap_id:        Bibliothek-Snap-ID (Farbe/Look) (oder None).
            pos:            QPoint der Drop-Position (benoetigt wenn target None).
            target:         VCButton oder VCSlider unter dem Mauszeiger, oder None
                            fuer leeres Canvas.
        Reihenfolge der Prioritaet: function_id > snapshot_index > snap_id.
        """
        from .vc_button import VCButton, ButtonAction
        from .vc_slider import VCSlider, SliderMode

        if function_id is not None:
            # WS1: gefuehrter Smart-Drop auf leeres Canvas (statt fixem Toggle-Button).
            # Nur im interaktiven Pfad (echter Drag&Drop); Direktaufrufe/Tests bleiben
            # beim alten, stummen Verhalten (interactive=False).
            if interactive and target is None:
                # Drop aufs leere Canvas -> Checkbox-Karte (Mehrfachauswahl), je
                # angekreuztem Aspekt ein vorverdrahtetes Widget in EINEM Undo.
                from .vc_drop_panel import VCDropPanel
                panel = VCDropPanel(function_id, parent=self)
                results = panel.run()
                if not results:
                    return
                self.build_from_smart_results(results, pos=pos,
                                              box=getattr(panel, "box_mode", False))
                return
            # Funktionsnamen fuer Caption ermitteln
            fn_name: str | None = None
            try:
                from src.core.engine.function_manager import get_function_manager
                fn = get_function_manager().get(function_id)
                fn_name = fn.name if fn is not None else None
            except Exception:
                pass

            if isinstance(target, VCSlider):
                # Phase E: haelt der Fader schon einen Effekt, wird der neue
                # ANGEHAENGT (gekoppelt) statt ersetzt; sonst frisch binden.
                already_bound = (target.function_id is not None) or bool(target.function_ids)
                if already_bound:
                    # Doppelbelegungs-Schutz: statt stumm zu koppeln entscheidet der
                    # Resolver. Phase 2/nicht-interaktiv -> Default 'couple' (Verhalten
                    # unveraendert); Phase 3 reicht die Erklaer-Karten-Wahl ein.
                    if not self._resolve_coupling_conflict(
                            target, function_id, aspect=self._widget_aspect(target),
                            interactive=interactive):
                        return
                    if target.mode not in (SliderMode.EFFECT_INTENSITY,
                                           SliderMode.EFFECT_SPEED,
                                           SliderMode.EFFECT_PARAM):
                        target.mode = SliderMode.EFFECT_PARAM
                    target.update()
                else:
                    # Effekt-Parameter-Fader konfigurieren
                    target.mode = SliderMode.EFFECT_PARAM
                    target.function_id = function_id
                    try:
                        from src.core.engine import effect_live
                        default_key = effect_live.default_param_key(function_id)
                        if default_key:
                            target.param_key = default_key
                    except Exception:
                        pass
                    if fn_name and getattr(target, "caption", None) in (None, "", "Fader"):
                        target.caption = fn_name
                    target.update()

            elif isinstance(target, VCButton):
                # Funktions-Buttons koennen wie Slider mehrere Ziele koppeln:
                # ein weiterer Drop wird angehaengt statt die erste Bindung zu
                # ersetzen. Andere Button-Arten (Executor, Snapshot, …) werden
                # weiterhin bewusst in einen Funktions-Toggle umgewandelt.
                function_button = target.action in (
                    ButtonAction.FUNCTION_TOGGLE,
                    ButtonAction.FUNCTION_FLASH,
                )
                already_bound = function_button and (
                    target.function_id is not None or bool(target.function_ids)
                )
                if already_bound:
                    if not self._resolve_coupling_conflict(
                            target, function_id, aspect="toggle",
                            interactive=interactive):
                        return
                else:
                    target.action = ButtonAction.FUNCTION_TOGGLE
                    target.function_id = function_id
                    target.function_ids = []
                if fn_name and getattr(target, "caption", None) in (None, "", "Button"):
                    target.caption = fn_name
                target.update()

            elif self._apply_function_to_special(target, function_id, fn_name,
                                                 interactive=interactive):
                # Farbe / Encoder / XY-Pad / SpeedDial haben den Drop verarbeitet.
                pass

            else:
                # Leeres Canvas → neuen Button anlegen
                drop_pos = pos if pos is not None else QPoint(40, 40)
                w = self._add_widget("VCButton", drop_pos)
                if w is not None:
                    w.action = ButtonAction.FUNCTION_TOGGLE
                    w.function_id = function_id
                    if fn_name:
                        w.caption = fn_name
                    w.setVisible(self.on_active_bank(w))
                    w.show()

        elif snapshot_index is not None:
            if isinstance(target, VCButton):
                target.action = ButtonAction.SNAPSHOT
                target.snapshot_index = snapshot_index
                target.update()

            else:
                drop_pos = pos if pos is not None else QPoint(40, 40)
                w = self._add_widget("VCButton", drop_pos)
                if w is not None:
                    w.action = ButtonAction.SNAPSHOT
                    w.snapshot_index = snapshot_index
                    w.setVisible(self.on_active_bank(w))
                    w.show()

        elif snap_id is not None:
            if isinstance(target, VCButton):
                self._assign_snap_to_button(target, snap_id)
            else:
                drop_pos = pos if pos is not None else QPoint(40, 40)
                w = self._add_widget("VCButton", drop_pos)
                if w is not None:
                    self._assign_snap_to_button(w, snap_id)
                    w.setVisible(self.on_active_bank(w))
                    w.show()

    def _build_from_smart_result(self, res, pos):
        """WS1: erzeugt aus einem SmartDropResult ein vorverdrahtetes VC-Widget."""
        from .vc_button import VCButton, ButtonAction
        from .vc_slider import VCSlider, SliderMode
        drop_pos = pos if pos is not None else QPoint(40, 40)

        # Sammel-Option: alle Live-Regler des Effekts erzeugen (kein Einzel-Widget).
        if res.widget_type == "BULK":
            try:
                from src.core.engine import effect_live
                pkeys = [getattr(s, "key", "")
                          for s in effect_live.list_params(res.function_id)
                          if getattr(s, "kind", "") in ("int", "float", "bool", "select")
                          and getattr(s, "live_editable", True)
                          and getattr(s, "mappable", True)]
                akeys = [k for k, _l in effect_live.list_actions(res.function_id)]
                self.add_live_controls(res.function_id, pkeys, akeys,
                                       origin=None if pos is None else None)
            except Exception as e:
                print(f"[VCCanvas] smart-drop bulk error: {e}")
            return

        w = self._add_widget(res.widget_type, drop_pos)
        if w is None:
            return
        fid = res.function_id
        wt = res.widget_type
        if wt == "VCButton":
            w.action = res.action or ButtonAction.FUNCTION_TOGGLE
            w.function_id = fid
            if res.effect_action_key:
                w.effect_action_key = res.effect_action_key
        elif wt == "VCSlider":
            w.mode = res.slider_mode or SliderMode.EFFECT_INTENSITY
            w.function_id = fid
            if res.param_key:
                w.param_key = res.param_key
        elif wt == "VCEncoder":
            w.function_id = fid
            if res.param_key:
                w.param_key = res.param_key
        elif wt == "VCStepper":
            w.function_id = fid
            if res.param_key:
                w.param_key = res.param_key
        elif wt == "VCSpeedDial":
            from .vc_speedial import SpeedTarget
            w.target_mode = getattr(res, "speed_target", None) or SpeedTarget.FUNCTION
            w.function_id = fid
        elif wt == "VCEffectColors":
            w.function_id = fid
        elif wt == "VCXYPad":
            # Bewegungs-Aspekt (EFX): Feld-Modus steuert Zentrum/Groesse.
            w.mode = "area"
            w.efx_function_id = fid
        elif wt == "VCBusSelector":
            w.function_id = fid
        # Phase E: optionale Multi-Effekt-Kopplung aus dem SmartDropResult
        # uebernehmen (nur Widgets, die die Felder kennen).
        _extra_ids = [int(i) for i in getattr(res, "function_ids", []) if str(i).lstrip("-").isdigit()]
        if _extra_ids and hasattr(w, "function_ids"):
            _existing = list(getattr(w, "function_ids", []) or [])
            for _i in _extra_ids:
                if _i != fid and _i not in _existing:
                    _existing.append(_i)
            w.function_ids = _existing
        _pkpi = getattr(res, "param_keys_per_id", None)
        if _pkpi and hasattr(w, "param_keys_per_id"):
            _clean: dict[int, str] = {}
            for _k, _v in _pkpi.items():
                try:
                    _clean[int(_k)] = str(_v)
                except (TypeError, ValueError):
                    pass
            w.param_keys_per_id = _clean
        if res.caption:
            w.caption = res.caption
        w.setVisible(self.on_active_bank(w))
        w.show()
        return w

    def _apply_function_to_special(self, target, function_id, fn_name,
                                   interactive: bool = False) -> bool:
        """Funktions-Drop auf Farbe / Encoder / XY-Pad / SpeedDial anwenden.
        Gibt True zurück, wenn der Drop von einem dieser Typen verarbeitet wurde."""
        from .vc_color import VCColor, ColorTarget
        from .vc_encoder import VCEncoder
        from .vc_stepper import VCStepper
        from .vc_effect_display import VCEffectDisplay
        from .vc_effect_editor import VCEffectEditor
        from .vc_bus_selector import VCBusSelector
        from .vc_xypad import VCXYPad
        from .vc_speedial import VCSpeedDial, SpeedTarget

        if isinstance(target, VCEffectEditor):
            # Effekt auf die Editor-Box gezogen -> Box an den Effekt binden
            # (Header + Live-Vorschau).
            # Wird die Box auf einen ANDEREN Effekt umgebunden und hat schon
            # Bedien-Widgets (die den ALTEN Effekt steuern), diese erst entfernen
            # (ein Undo-Snapshot, _restoring-Guard) -> keine veralteten Regler,
            # die unsichtbar den falschen Effekt steuern.
            try:
                _old = target.effect_id
                _had = target._control_children()
            except Exception:
                _old, _had = None, []
            if _old is not None and _old != int(function_id) and _had:
                self.push_undo_snapshot(self.to_dict())
                _prev = self._restoring
                self._restoring = True
                try:
                    for _w in list(_had):
                        target._remove_child(_w)
                finally:
                    self._restoring = _prev
            # Beim interaktiven Drop oeffnet sich gleich das Auswahlmenue
            # (open_control_chooser baut nur, wenn die Box danach leer ist).
            target.set_effect(function_id, open_chooser=interactive)
            return True

        if isinstance(target, VCBusSelector):
            target.function_id = function_id
            if fn_name and getattr(target, "caption", None) in (None, "", "Tempo-Bus"):
                target.caption = f"{fn_name} Tempo-Bus"
            target.update()
            return True

        from .vc_tempo_bus_controller import VCTempoBusController
        if isinstance(target, VCTempoBusController):
            # Effekt auf den Controller ziehen -> taktgleich an dessen Bus koppeln
            # (mehrfach moeglich; couple_effect haengt an statt zu ersetzen).
            target.couple_effect(function_id)
            if fn_name and getattr(target, "caption", None) in (None, "", "Tempo-Bus"):
                target.caption = f"{fn_name} Tempo"
            target.update()
            return True

        if isinstance(target, VCColor):
            # Farb-Kachel färbt live die aktive Sequence-Farbe DIESES Effekts.
            target.target = ColorTarget.EFFECT
            target.function_id = function_id
            if fn_name and getattr(target, "caption", None) in (None, "", "Farbe"):
                target.caption = fn_name
            target.update()
            return True

        if isinstance(target, VCEncoder):
            # Encoder verstellt einen Parameter dieses Effekts relativ.
            target.function_id = function_id
            try:
                from src.core.engine import effect_live
                dk = effect_live.default_param_key(function_id)
                if dk:
                    target.param_key = dk
            except Exception:
                pass
            if fn_name and getattr(target, "caption", None) in (None, "", "Encoder"):
                target.caption = fn_name
            target.update()
            return True

        if isinstance(target, VCStepper):
            # Schrittwahl braucht einen diskreten int/bool/select-Parameter.
            target.function_id = function_id
            try:
                from src.core.engine import effect_live
                dk = next(
                    (
                        spec.key for spec in effect_live.list_params(function_id)
                        if spec.kind in ("int", "bool", "select")
                        and getattr(spec, "live_editable", True)
                        and getattr(spec, "mappable", True)
                    ),
                    None,
                )
                if dk:
                    target.param_key = dk
            except Exception:
                pass
            if fn_name and getattr(target, "caption", None) in (None, "", "Anzahl"):
                target.caption = fn_name
            target.update()
            return True

        if isinstance(target, VCEffectDisplay):
            # Live-Anzeige rendert genau diesen Effekt (keine Bedien-Aspekte).
            target.function_id = function_id
            if fn_name and getattr(target, "caption", None) in (None, "", "Effekt"):
                target.caption = fn_name
            target.update()
            return True

        if isinstance(target, VCXYPad):
            # XY-Pad im Feld-Modus steuert Zentrum/Größe dieses EFX.
            target.mode = "area"
            target.efx_function_id = function_id
            if fn_name and getattr(target, "caption", None) in (None, "", "XY Pad"):
                target.caption = fn_name
            target.update()
            return True

        if isinstance(target, VCSpeedDial):
            # Speed-Dial steuert das Tempo dieser Funktion/dieses Effekts.
            # Phase E: haelt der Dial schon einen Effekt, neuen ANHAENGEN statt
            # ersetzen (so koppelt man mehrere Effekte an EINEN Tempo-Regler).
            already_bound = (target.function_id is not None) or bool(target.function_ids)
            if already_bound:
                # Doppelbelegungs-Schutz wie beim Slider; Rueckgabewert wird jetzt
                # beachtet (frueher ignoriert -> latenter Bug).
                if not self._resolve_coupling_conflict(
                        target, function_id, aspect="tempo", interactive=interactive):
                    return True   # Drop verarbeitet (No-op/abgelehnt), kein neues Widget
                if target.target_mode not in (SpeedTarget.FUNCTION,
                                               SpeedTarget.TEMPO_BUS_MULT):
                    target.target_mode = SpeedTarget.FUNCTION
            else:
                target.target_mode = SpeedTarget.FUNCTION
                target.function_id = function_id
                if fn_name and getattr(target, "caption", None) in (None, "", "Speed"):
                    target.caption = fn_name
            target.update()
            return True

        return False

    def _couple_effect(self, target, function_id) -> bool:
        """Phase E: haengt einen weiteren Effekt an ein bereits gebundenes Multi-
        Effekt-Widget (z. B. VCButton/VCSlider/VCSpeedDial) an. Dedupliziert gegen die
        Primaer-ID und die bestehende Liste. Gibt False zurueck, wenn der Effekt
        schon gekoppelt ist (nichts zu tun)."""
        try:
            fid = int(function_id)
        except (TypeError, ValueError):
            return False
        ids = list(getattr(target, "function_ids", []) or [])
        primary = getattr(target, "function_id", None)
        if fid == primary or fid in ids:
            return False
        ids.append(fid)
        target.function_ids = ids
        return True

    # ── Doppelbelegungs-Schutz + Widget-Typ-Tausch (Phase 2) ──────────────────

    def _widget_aspect(self, w):
        """Welchen EFFEKT-Aspekt steuert ``w``? -> Vokabular wie ControlKind
        ('tempo'/'intensity'/'colors'/'movement'/'param'/'tempo_bus'/'toggle'/
        'action'); None = keine (relevante) Effekt-Bindung. Basis fuer
        Konflikt-Erkennung + bindungserhaltenden Typ-Tausch."""
        from .vc_slider import VCSlider, SliderMode
        from .vc_speedial import VCSpeedDial, SpeedTarget
        from .vc_encoder import VCEncoder
        from .vc_stepper import VCStepper
        from .vc_effect_colors import VCEffectColors
        from .vc_color import VCColor, ColorTarget
        from .vc_xypad import VCXYPad
        from .vc_bus_selector import VCBusSelector
        from .vc_button import VCButton, ButtonAction
        if isinstance(w, VCSlider):
            return {SliderMode.EFFECT_SPEED: "tempo",
                    SliderMode.EFFECT_INTENSITY: "intensity",
                    SliderMode.EFFECT_PARAM: "param",
                    SliderMode.TEMPO_BUS: "tempo_bus"}.get(getattr(w, "mode", None))
        if isinstance(w, VCSpeedDial):
            if getattr(w, "target_mode", None) == SpeedTarget.TEMPO_BUS_MULT:
                return "tempo_bus"
            return "tempo"
        if isinstance(w, VCEncoder):
            return "param"
        if isinstance(w, VCStepper):
            return "param"
        if isinstance(w, VCEffectColors):
            return "colors"
        if isinstance(w, VCColor):
            return "colors" if getattr(w, "target", None) == ColorTarget.EFFECT else None
        if isinstance(w, VCXYPad):
            return "movement" if getattr(w, "mode", None) == "area" else None
        if isinstance(w, VCBusSelector):
            return "tempo_bus"
        if isinstance(w, VCButton):
            a = getattr(w, "action", None)
            if a in (ButtonAction.FUNCTION_TOGGLE, ButtonAction.FUNCTION_FLASH):
                return "toggle"
            if a == ButtonAction.EFFECT_ACTION:
                return "action"
        return None

    def _effect_ids_of(self, w) -> set:
        """Alle Effekt-/Funktions-IDs, die ``w`` bindet (function_id +
        function_ids + efx_function_id)."""
        ids = set()
        # effect_id: die VCEffectEditor-Box bindet ihren Effekt hierueber (nicht
        # ueber function_id) -> aufnehmen, damit die Box als Einheit mit-leuchtet.
        for attr in ("function_id", "efx_function_id", "effect_id"):
            v = getattr(w, attr, None)
            if isinstance(v, int):
                ids.add(v)
        for v in (getattr(w, "function_ids", None) or []):
            if isinstance(v, int):
                ids.add(v)
        return ids

    def effect_binding_owners(self, function_id, aspect=None, exclude=None) -> list:
        """Captions aller Widgets, die ``function_id`` bereits steuern — optional
        nur fuer einen bestimmten ``aspect`` (siehe _widget_aspect). Vorbild:
        key_binding_owners. Basis fuer den Doppelbelegungs-Schutz (Phase-3-Karte:
        „Tempo -> liegt schon auf Fader 3")."""
        owners: list = []
        try:
            fid = int(function_id)
        except (TypeError, ValueError):
            return owners
        try:
            widgets = self.findChildren(VCWidget)
        except RuntimeError:
            return owners
        for w in widgets:
            if w is exclude:
                continue
            if fid not in self._effect_ids_of(w):
                continue
            if aspect is not None and self._widget_aspect(w) != aspect:
                continue
            owners.append(getattr(w, "caption", "") or w.__class__.__name__)
        return owners

    def highlight_effects(self, fids, exclude=None):
        """Hebt alle Widgets hervor (oranger Glow), die einen der Effekte aus
        ``fids`` steuern — macht die Gruppe „was beeinflusst diesen Effekt"
        sichtbar (Antippen eines Widgets ODER Auswahl eines Effekts in der
        Bibliothek). Leeres/None ``fids`` -> Hervorhebung komplett aufheben.
        Nur im Bearbeiten-Modus aktiv — im Betrieb stoert der Glow live laufende
        Widgets nicht."""
        want: set = set()
        if self._edit_mode:
            for f in (fids or []):
                try:
                    want.add(int(f))
                except (TypeError, ValueError):
                    pass
        try:
            widgets = self.findChildren(VCWidget)
        except RuntimeError:
            return
        for w in widgets:
            on = False if w is exclude else (bool(want) and bool(self._effect_ids_of(w) & want))
            try:
                w.set_effect_highlight(on)
            except Exception:
                pass

    def clear_effect_highlight(self):
        """Hebt jede Effekt-Gruppen-Hervorhebung auf."""
        self.highlight_effects(None)

    def _rebind_widget_to(self, target, function_id):
        """Konflikt-Aufloesung 'Ersetzen': biegt ein Multi-Effekt-Widget komplett
        auf EINEN Effekt um (leert function_ids + param_keys_per_id)."""
        try:
            fid = int(function_id)
        except (TypeError, ValueError):
            return
        if hasattr(target, "function_ids"):
            target.function_ids = []
        if hasattr(target, "param_keys_per_id"):
            target.param_keys_per_id = {}
        target.function_id = fid
        target.update()

    def _resolve_coupling_conflict(self, target, function_id, aspect=None, *,
                                   interactive: bool = False,
                                   resolution: "str | None" = None) -> bool:
        """Entscheidet, was beim Drop eines Effekts auf einen BEREITS gebundenen
        Multi-Ziel-Widget passiert — statt stumm zu koppeln:
          'couple'  -> bestehendes _couple_effect (heutiges Verhalten)
          'replace' -> Ziel auf den neuen Effekt umbiegen
          'new'     -> Ziel unangetastet (Aufrufer legt ein neues Widget an)
          'cancel'  -> nichts tun
        Nicht-interaktiv/programmatisch (Tests): ohne ``resolution`` -> Default
        'couple' (Verhalten unveraendert). Interaktiv: ohne ``resolution`` wird die
        Erklaer-Karte (VCConflictCard) gezeigt; „Neues Widget" legt einen
        gleichartigen Regler DANEBEN an (kein stummes Koppeln mehr). Rueckgabe:
        True, wenn am ZIEL etwas gebunden/geaendert wurde (sonst No-op)."""
        if resolution is None:
            if interactive:
                resolution = self._ask_coupling_resolution(target, function_id)
                if resolution == "new":
                    self._spawn_sibling_control(target, function_id)
                    return False        # Ziel unangetastet, neues Widget daneben
                if resolution is None:
                    return False        # Abbruch
            else:
                resolution = "couple"
        if resolution in ("cancel", "new"):
            return False                # explizites 'new' (Tests): reiner No-op
        if resolution == "replace":
            self._rebind_widget_to(target, function_id)
            return True
        return self._couple_effect(target, function_id)

    def _ask_coupling_resolution(self, target, function_id):
        """Zeigt die Erklaer-Karte und liefert 'replace'/'couple'/'new'/None
        (None = Abbruch). Bei UI-Fehlern defensiv 'couple' (nicht blockieren)."""
        try:
            from .vc_conflict_card import VCConflictCard
            from .vc_effect_meta import effect_name
            owners = [getattr(target, "caption", "") or target.__class__.__name__]
            return VCConflictCard(effect_name(function_id), owners, parent=self).run()
        except Exception:
            return "couple"

    def _spawn_sibling_control(self, target, function_id, aspect=None):
        """Konflikt-Aufloesung 'Neues Widget': legt einen GLEICHARTIGEN Regler
        (selber Typ + Aspekt) fuer den neuen Effekt direkt unter dem Ziel an.
        Ein Undo-Schritt."""
        new_type = target.__class__.__name__
        if WIDGET_REGISTRY.get(new_type) is None:
            return None
        if aspect is None:
            aspect = self._widget_aspect(target)
        pos = QPoint(target.x(), target.y() + target.height() + self.GRID)
        self.push_undo_snapshot(self.to_dict())
        _prev = self._restoring
        self._restoring = True
        try:
            w = self._add_widget(new_type, pos)
            if w is None:
                return None
            try:
                w.function_id = int(function_id)
            except (TypeError, ValueError):
                pass
            if hasattr(w, "param_key") and not getattr(w, "param_key", ""):
                try:
                    from src.core.engine import effect_live
                    dk = effect_live.default_param_key(function_id)
                    if dk:
                        w.param_key = dk
                except Exception:
                    pass
            self._prime_widget_for_aspect(w, aspect)
            if not getattr(w, "caption", ""):
                try:
                    from .vc_effect_meta import effect_name
                    w.caption = effect_name(function_id)
                except Exception:
                    pass
            w.setVisible(self.on_active_bank(w))
            w.show()
            w.update()
        finally:
            self._restoring = _prev
        return w

    def _prime_widget_for_aspect(self, w, aspect):
        """Belegt Modus/Ziel eines (frisch getauschten) Widgets so, dass die
        erhaltene Effekt-Bindung fuer ``aspect`` wirkt."""
        from .vc_slider import VCSlider, SliderMode
        from .vc_speedial import VCSpeedDial, SpeedTarget
        from .vc_xypad import VCXYPad
        from .vc_button import VCButton, ButtonAction
        if isinstance(w, VCSlider):
            w.mode = {"tempo": SliderMode.EFFECT_SPEED,
                      "intensity": SliderMode.EFFECT_INTENSITY,
                      "param": SliderMode.EFFECT_PARAM,
                      "tempo_bus": SliderMode.TEMPO_BUS}.get(aspect, SliderMode.EFFECT_PARAM)
        elif isinstance(w, VCSpeedDial):
            w.target_mode = SpeedTarget.FUNCTION
        elif isinstance(w, VCXYPad):
            w.mode = "area"
        elif isinstance(w, VCButton):
            w.action = (ButtonAction.EFFECT_ACTION if aspect == "action"
                        else ButtonAction.FUNCTION_TOGGLE)

    def replace_widget_type(self, widget, new_type, aspect=None):
        """Tauscht den Widget-TYP eines Bedienelements und ERHAELT die Effekt-
        Bindung (function_id(s), param_key(s), efx_function_id, Caption, Position,
        Bank). Fuer die grafische Widget-Galerie / „↔ Widget aendern". Ein
        Undo-Schritt. Gibt das neue Widget zurueck (oder None)."""
        if widget is None or WIDGET_REGISTRY.get(new_type) is None:
            return None
        if widget.__class__.__name__ == new_type:
            return widget
        if aspect is None:
            aspect = self._widget_aspect(widget)
        pos = widget.pos()
        carry = {}
        for attr in ("function_id", "function_ids", "param_keys_per_id",
                     "param_key", "efx_function_id", "caption", "bank"):
            if hasattr(widget, attr):
                carry[attr] = getattr(widget, attr)
        self.push_undo_snapshot(self.to_dict())
        _prev = self._restoring
        self._restoring = True
        try:
            new = self._add_widget(new_type, pos)
            if new is None:
                return None
            for attr, val in carry.items():
                if hasattr(new, attr):
                    try:
                        setattr(new, attr, val)
                    except Exception:
                        pass
            self._prime_widget_for_aspect(new, aspect)
            new.setVisible(self.on_active_bank(new))
            new.show()
            new.update()
            self._remove_widget(widget)
        finally:
            self._restoring = _prev
        return new

    def build_from_smart_results(self, results, pos=None, origin=None, box=False) -> list:
        """Phase 2: baut aus MEHREREN SmartDropResults je ein vorverdrahtetes
        Widget (ueber _build_from_smart_result) und legt sie in einer Reihe ab —
        alles als EIN Undo-Schritt (Muster add_live_controls). ``origin`` =
        Anker-Widget (Reihe darunter), sonst ``pos``. Gibt die erzeugten Widgets
        zurueck (BULK-Results erzeugen eigene Regler und liefern kein Einzel-W)."""
        results = [r for r in (results or []) if r is not None]
        if not results:
            return []
        if origin is not None:
            x0 = origin.x()
            y0 = origin.y() + origin.height() + self.GRID
        elif pos is not None:
            x0, y0 = pos.x(), pos.y()
        else:
            x0, y0 = 40, 40
        created: list = []
        self.push_undo_snapshot(self.to_dict())
        _prev = self._restoring
        self._restoring = True
        try:
            if box:
                created = self._build_box(results, x0, y0)
            else:
                x = x0
                for res in results:
                    w = self._build_from_smart_result(res, QPoint(x, y0))
                    if w is None:
                        continue
                    created.append(w)
                    x += w.width() + self.GRID
        finally:
            self._restoring = _prev
        return created

    def _build_box(self, results, x0, y0) -> list:
        """Welle 4 (L/N): erzeugt eine VCEffectEditor-Box, baut ALLE gewaehlten
        Widgets DARIN (auto-gelabelt via aspect_caption) und bettet eine Live-
        Vorschau ein. Snap-out + Teil-Entfernen erbt die Box von VCFrame.
        BULK (None) bleibt bewusst lose ausserhalb der Box."""
        frame = self._add_widget("VCEffectEditor", QPoint(x0, y0))
        if frame is None:
            return []
        prim = next((r.function_id for r in results
                     if getattr(r, "function_id", None) is not None), None)
        if prim is not None:
            frame.set_effect(int(prim))
        children: list = []
        for res in results:
            w = self._build_from_smart_result(res, QPoint(0, 0))
            if w is not None:               # BULK liefert None -> bleibt lose
                children.append(w)
        pad = self.GRID
        band = (frame._tab_height if frame._show_header else 0) + 2 + frame._preview_h
        total_w = sum(c.width() + pad for c in children) + pad
        max_h = max((c.height() for c in children), default=40)
        frame.resize(max(240, total_w), band + max_h + 2 * pad)
        cx, cy = pad, band + pad
        for w in children:
            frame.add_effect_child(w, frame._current_page)
            w.move(cx, cy)
            cx += w.width() + pad
        frame.setVisible(self.on_active_bank(frame))
        return [frame] + children

    def build_results_into_box(self, box, results) -> list:
        """Baut die gewaehlten SmartDropResults als Bedien-Widgets IN eine
        bestehende VCEffectEditor-Box (ein Undo-Schritt) und legt sie unter dem
        Vorschau-Band in einer Reihe aus. Wird vom ⚙-Auswahlmenue der Box genutzt.
        BULK (None) bleibt bewusst aussen vor."""
        results = [r for r in (results or []) if r is not None]
        if not results:
            return []
        self.push_undo_snapshot(self.to_dict())
        _prev = self._restoring
        self._restoring = True
        created: list = []
        try:
            for res in results:
                w = self._build_from_smart_result(res, QPoint(0, 0))
                if w is None:                 # BULK liefert None -> bleibt lose
                    continue
                box.add_effect_child(w, box._current_page)
                created.append(w)
            try:
                box._relayout_controls()
            except Exception as e:
                print(f"[VCCanvas] _relayout_controls failed: {e}")
        finally:
            self._restoring = _prev
        return created

    def _assign_snap_to_button(self, btn, snap_id):
        """Macht einen VCButton zur Bibliothek-Farb-/Snap-Taste (Standard: Umschalten).
        Setzt die Beschriftung auf den Snap-Namen, wenn noch generisch."""
        from .vc_button import ButtonAction
        if snap_id is None:
            return
        sid = int(snap_id)
        already_library_snap = getattr(btn, "action", None) == ButtonAction.LIBRARY_SNAP
        already_bound = already_library_snap and (
            getattr(btn, "snap_id", None) is not None or bool(getattr(btn, "snap_ids", []))
        )
        btn.action = ButtonAction.LIBRARY_SNAP
        if already_bound:
            primary = getattr(btn, "snap_id", None)
            try:
                primary = int(primary) if primary is not None else None
            except (TypeError, ValueError):
                primary = None
            ids = []
            for raw in (getattr(btn, "snap_ids", []) or []):
                try:
                    iv = int(raw)
                except (TypeError, ValueError):
                    continue
                if iv != primary and iv not in ids:
                    ids.append(iv)
            if sid != primary and sid not in ids:
                ids.append(sid)
            btn.snap_ids = ids
        else:
            btn.snap_id = sid
            btn.snap_ids = []
        btn._snap_active = False
        btn._snap_prev = {}
        try:
            from src.core.engine.snap_library import get_snap_library
            snap = get_snap_library().get(sid)
            if snap is not None and getattr(btn, "caption", None) in (None, "", "Button"):
                btn.caption = snap.name
        except Exception:
            pass
        btn.update()

    # ── Context menu ─────────────────────────────────────────────────────────

    def _context_menu(self, local_pos: QPoint):
        if not self._edit_mode:
            return
        menu = QMenu(self)
        menu.setTitle("Widget hinzufügen")

        add_menu = menu.addMenu("Hinzufügen")
        for wtype in WIDGET_REGISTRY:
            act = add_menu.addAction(wtype.replace("VC", ""))
            act.setData((wtype, local_pos))

        menu.addSeparator()
        act_clear = menu.addAction("Alle löschen")
        # UIC-05: Canvas-Export/Import nur noch über die Toolbar (keine Dopplung im
        # Kontextmenü). Das Menü dient dem Hinzufügen + schnellen Leeren.

        chosen = menu.exec(self.mapToGlobal(local_pos))
        if chosen is None:
            return
        if chosen == act_clear:
            self._clear()
        elif chosen.data():
            wtype, pos = chosen.data()
            self._add_widget(wtype, pos)

    def _add_widget(self, wtype: str, pos: QPoint, d: dict | None = None):
        cls = WIDGET_REGISTRY.get(wtype)
        if cls is None:
            return
        if d is None and not self._restoring:
            self._push_undo()      # Benutzer legt ein NEUES Widget an -> Undo-Punkt
        w = cls(parent=self)
        w.set_edit_mode(self._edit_mode)
        w.set_snap_grid(self.GRID if self._snap_to_grid else 0)
        if d:
            w.apply_dict(d)
        else:
            snapped = QPoint(
                round(pos.x() / self.GRID) * self.GRID,
                round(pos.y() / self.GRID) * self.GRID,
            )
            w.move(snapped)
            # Neu angelegte Widgets landen auf der aktuell sichtbaren Bank.
            w.bank = self._active_bank
        w.delete_requested.connect(lambda widget=w: self._remove_widget(widget))
        w.setVisible(self.on_active_bank(w))
        return w

    def add_live_controls(self, function_id, param_keys, action_keys, origin=None):
        """MLV-02: erzeugt passende Regler und Tasten, fest an function_id gebunden."""
        from .vc_button import VCButton, ButtonAction
        from .vc_slider import VCSlider, SliderMode

        labels = {}
        specs = {}
        try:
            from src.core.engine import effect_live
            for s in effect_live.list_params(function_id):
                labels[s.key] = getattr(s, "label", s.key)
                specs[s.key] = s
        except Exception:
            pass
        try:
            from src.ui.widgets.matrix_live_dialog import ACTION_LABELS
        except Exception:
            ACTION_LABELS = {}

        if origin is not None:
            x0, y0 = origin.x(), origin.y() + origin.height() + self.GRID
        else:
            x0, y0 = 40, 40
        gap = self.GRID
        created = []

        # Das ganze Kit soll EIN Undo-Schritt sein: einmal den Vorher-Stand sichern,
        # dann die Pro-Widget-Undo-Punkte waehrend des Aufbaus unterdruecken
        # (_restoring deaktiviert die _push_undo-Hooks in _add_widget).
        self.push_undo_snapshot(self.to_dict())
        _prev_restoring = self._restoring
        self._restoring = True
        try:
            x = x0
            for key in (param_keys or []):
                spec = specs.get(key)
                kind = getattr(spec, "kind", "float")
                try:
                    small_int = (kind == "int"
                                 and (float(spec.max) - float(spec.min)) <= 64)
                except (TypeError, ValueError, AttributeError):
                    small_int = False
                widget_type = ("VCStepper"
                               if kind in ("bool", "select") or small_int
                               else "VCSlider")
                w = self._add_widget(widget_type, QPoint(x, y0))
                if w is None:
                    continue
                if isinstance(w, VCSlider):
                    w.mode = SliderMode.EFFECT_PARAM
                w.function_id = function_id
                w.param_key = key
                w.caption = labels.get(key, key)
                w.update()
                w.show()
                created.append(w)
                x += w.width() + gap

            if action_keys:
                x = x0
                yb = y0 + 200 + gap     # Reihe unter den Fadern
                for akey in action_keys:
                    w = self._add_widget("VCButton", QPoint(x, yb))
                    if w is None:
                        continue
                    w.action = ButtonAction.EFFECT_ACTION
                    w.function_id = function_id
                    w.effect_action_key = akey
                    w.caption = ACTION_LABELS.get(akey, akey)
                    w.update()
                    w.show()
                    created.append(w)
                    x += w.width() + gap
        finally:
            self._restoring = _prev_restoring
        return created

    def handle_drag_drop(self, widget):
        """FRM-01: Reparenting nach einem Drag. Liegt der Widget-Mittelpunkt über
        einem Frame, wird das Widget dessen Kind (Position relativ zum Frame); wird
        es aus einem Frame heraus gezogen, kehrt es auf den Canvas zurück. Frames
        selbst werden nicht verschachtelt.

        FRM-02: Ein aktiver Effekt-Glow (``QGraphicsDropShadowEffect`` aus
        ``set_effect_highlight``) ueberlebt das ``setParent()`` — Qt rendert das
        Widget dann ueber ein Offscreen-Pixmap mit einem unter dem ALTEN Parent
        berechneten Clip-Rechteck, das nie neu berechnet wird → das Widget zeichnet
        nichts mehr und wirkt geloescht. Darum den Glow VOR dem Umhaengen loesen,
        danach ``raise_()`` (Z-Order) + Frame neu zeichnen und den Glow frisch
        setzen. Beim Drop wird die Position zusaetzlich aufs Grid gerundet."""
        from .vc_frame import VCFrame
        if isinstance(widget, VCFrame):
            return
        center_canvas = self.mapFromGlobal(widget.mapToGlobal(widget.rect().center()))
        # FRM-03: Ziel-Frame NUR unter den auf der aktiven Bank sichtbaren Frames
        # suchen. Frames anderer Baenke liegen (unsichtbar) an derselben Geometrie —
        # ohne diesen Filter gewann immer das zuerst erstellte (= Bank 1), egal auf
        # welcher Bank man wirklich ablegt. Bei Ueberlappung auf DERSELBEN Bank das
        # OBERSTE waehlen: kein `break`, der letzte Treffer in der Kind-/Stapel-
        # reihenfolge liegt zuoberst (raise_() haengt das Widget hinten an).
        target = None
        for f in self.findChildren(VCFrame, options=Qt.FindChildOption.FindDirectChildrenOnly):
            if f is widget or not self.on_active_bank(f):
                continue
            if f.geometry().contains(center_canvas):
                target = f
        parent = widget.parent()
        grid = self.GRID if self._snap_to_grid else 0

        if target is not None and parent is not target:
            # In den Frame hinein.
            local = target.mapFromGlobal(widget.mapToGlobal(QPoint(0, 0)))
            cr = target._content_rect()
            lx = min(max(local.x(), cr.x()), max(cr.x(), cr.right() - widget.width()))
            ly = min(max(local.y(), cr.y()), max(cr.y(), cr.bottom() - widget.height()))
            if grid > 0:
                lx = round(lx / grid) * grid
                ly = round(ly / grid) * grid
            had_hl = self._detach_highlight(widget)        # FRM-02: Glow loesen
            target.add_child_to_page(widget, target._current_page)
            widget.set_snap_grid(grid)
            widget.move(lx, ly)
            widget.raise_()                                # sonst unten im Stapel -> verdeckt
            self._reattach_highlight(widget, had_hl)       # frisches Effekt-Objekt
            widget.update()
            target.update()                                # Frame-Backing-Store auffrischen
        elif target is None and isinstance(parent, VCFrame):
            # Aus dem Frame heraus -> zurück auf den Canvas.
            canvas_tl = self.mapFromGlobal(widget.mapToGlobal(QPoint(0, 0)))
            nx, ny = max(0, canvas_tl.x()), max(0, canvas_tl.y())
            if grid > 0:
                nx = round(nx / grid) * grid
                ny = round(ny / grid) * grid
            had_hl = self._detach_highlight(widget)        # FRM-02: Glow loesen
            widget.setParent(self)
            widget.setProperty("vc_page", None)
            widget.set_edit_mode(self._edit_mode)
            widget.set_snap_grid(grid)
            widget.bank = self._active_bank
            widget.move(nx, ny)
            widget.raise_()
            widget.setVisible(self.on_active_bank(widget))
            self._reattach_highlight(widget, had_hl)
            widget.show()
            widget.update()

    @staticmethod
    def _detach_highlight(widget) -> bool:
        """Entfernt einen aktiven Effekt-Glow VOR einem Reparent (FRM-02) und meldet,
        ob er an war. Der ``QGraphicsDropShadowEffect`` wuerde ``setParent()`` sonst
        mit einem veralteten Offscreen-Clip ueberleben und das Widget verschwindet."""
        had = bool(getattr(widget, "_effect_highlight", False))
        if had:
            try:
                widget.set_effect_highlight(False)
            except Exception:
                pass
        return had

    @staticmethod
    def _reattach_highlight(widget, had: bool):
        """Setzt den Effekt-Glow nach dem Reparent neu — frisches Effekt-Objekt unter
        dem neuen Parent (korrektes Clip-Rechteck)."""
        if had:
            try:
                widget.set_effect_highlight(True)
            except Exception:
                pass

    def _remove_widget(self, widget: VCWidget):
        if not self._restoring:
            self._push_undo()      # Widget geloescht -> per Strg+Z wiederherstellbar
        widget.hide()
        widget.setParent(None)
        widget.deleteLater()

    def _clear(self):
        for child in self.findChildren(VCWidget,
                                       options=Qt.FindChildOption.FindDirectChildrenOnly):
            child.setParent(None)
            child.deleteLater()

    # ── Undo/Redo ───────────────────────────────────────────────────────────────
    def _push_undo(self):
        """Aktuellen VC-Stand vor einer Aenderung auf den Undo-Stapel legen."""
        self.push_undo_snapshot(self.to_dict())

    def push_undo_snapshot(self, snapshot: dict):
        """Einen (ggf. vor der Aenderung erfassten) Stand auf den Undo-Stapel legen.
        Fuer Move/Resize/Eigenschafts-Edits, die den Vorher-Stand selbst erfassen.
        No-op waehrend Restore/Laden; dedupliziert identische Folge-Stände; cappt + leert Redo."""
        if self._restoring or not isinstance(snapshot, dict):
            return
        if self._undo_stack and self._undo_stack[-1] == snapshot:
            return
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > self._UNDO_MAX:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def undo(self):
        """Letzte Aenderung rueckgaengig (Strg+Z)."""
        if not self._undo_stack:
            return
        self._redo_stack.append(self.to_dict())
        self._restore(self._undo_stack.pop())

    def redo(self):
        """Rueckgaengig gemachte Aenderung wiederholen (Strg+Y / Strg+Umschalt+Z)."""
        if not self._redo_stack:
            return
        self._undo_stack.append(self.to_dict())
        self._restore(self._redo_stack.pop())

    def _restore(self, layout: dict):
        self._restoring = True
        try:
            self.from_dict(layout)
        finally:
            self._restoring = False

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        widgets = []
        for child in self.findChildren(VCWidget,
                                       options=Qt.FindChildOption.FindDirectChildrenOnly):
            widgets.append(child.to_dict())
        return {"widgets": widgets}

    def from_dict(self, d: dict):
        if not self._restoring:
            # Echtes Laden einer Show -> Undo-Verlauf zuruecksetzen (nicht beim Restore).
            self._undo_stack.clear()
            self._redo_stack.clear()
        self._clear()
        for wd in d.get("widgets", []):
            wtype = wd.get("type", "")
            # Pro-Widget abgesichert: ein einzelnes defektes Widget (unbekannter Typ,
            # unbekannte Aktion/Feld aus einer anderen Version) darf NICHT das Laden der
            # restlichen VC abbrechen (sonst verschwindet fast die ganze Konsole).
            try:
                self._add_widget(wtype, QPoint(wd.get("x", 0), wd.get("y", 0)), wd)
            except Exception as e:
                print(f"[VCCanvas] Widget '{wtype}' uebersprungen: {e}")
        # Aktive Bank an die (ggf. aus der Show geladene) Engine-Page angleichen
        # und Sichtbarkeit setzen.
        if getattr(self, "_pe", None) is not None:
            self._active_bank = self._pe.current_page
        self._apply_bank_visibility()
        self.bank_changed.emit(self._active_bank)

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(self, "VC Layout speichern",
                                               "", "JSON (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)

    def _load(self):
        path, _ = QFileDialog.getOpenFileName(self, "VC Layout laden",
                                               "", "JSON (*.json)")
        if path:
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                self.from_dict(d)
            except Exception as e:
                QMessageBox.warning(self, "Fehler", str(e))

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg)
        if self._edit_mode:
            p.setPen(QColor("#1f2937"))
            g = self.GRID * 4
            for x in range(0, self.width(), g):
                p.drawLine(x, 0, x, self.height())
            for y in range(0, self.height(), g):
                p.drawLine(0, y, self.width(), y)

        # Hinweis wenn MIDI-Learn oder Snapshot-Assign aktiv
        mode = getattr(self, "_awaiting_button_click_for", None)
        if mode == "midi_learn":
            p.setPen(QColor("#ff8800"))
            p.drawText(self.rect().adjusted(8, 4, -8, 0),
                       Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                       "MIDI-Learn: Klicke einen Button an...")
        elif mode == "snapshot":
            p.setPen(QColor("#ffd700"))
            p.drawText(self.rect().adjusted(8, 4, -8, 0),
                       Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                       f"Snapshot zuweisen: Klicke einen Button an...")
        p.end()
