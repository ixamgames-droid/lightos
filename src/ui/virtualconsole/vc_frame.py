"""VCFrame — Container widget with optional multi-page support."""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QCheckBox,
                                QSpinBox, QDialogButtonBox, QMenu, QSizePolicy)
from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from .vc_widget import VCWidget


class VCFrame(VCWidget):
    """Container that holds child VCWidgets. Supports multiple pages."""

    def __init__(self, caption: str = "Frame", parent=None):
        super().__init__(caption, parent)
        self._page_count: int = 1
        self._current_page: int = 0
        self._show_header: bool = True
        self._solo: bool = False
        self._bg_color = QColor("#161b22")
        self._fg_color = QColor("#8b949e")
        self._tab_height = 22
        self.resize(300, 200)
        self.setAcceptDrops(True)

    # ── Solo-Frame Logik ─────────────────────────────────────────────────────

    def is_solo(self) -> bool:
        return self._solo

    def set_solo(self, on: bool):
        self._solo = bool(on)
        self.update()

    def on_child_activated(self, child: VCWidget):
        if not self._solo:
            return
        for c in self.findChildren(VCWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
            if c is child:
                continue
            deactivate = getattr(c, "deactivate_for_solo", None)
            if callable(deactivate):
                try:
                    deactivate()
                except Exception:
                    pass

    # ── Page management ───────────────────────────────────────────────────────

    def _content_rect(self) -> QRect:
        top = self._tab_height if self._show_header else 0
        return self.rect().adjusted(2, top + 2, -2, -2)

    def _tab_for_page(self, page: int) -> QRect:
        w = max(40, self.width() // self._page_count)
        return QRect(page * w, 0, w, self._tab_height)

    def _canvas(self):
        """Umschliessende VCCanvas finden (erkannt an ``on_active_bank``) — oder
        None, solange der Frame noch nicht in einer Canvas haengt."""
        p = self.parent()
        while p is not None:
            if hasattr(p, "on_active_bank"):
                return p
            p = p.parent()
        return None

    def _child_visible(self, child) -> bool:
        """Kind ist sichtbar, wenn es auf der aktuellen Seite liegt UND die
        Bank-Regel erfuellt. Die Bank-Entscheidung delegieren wir an
        ``VCCanvas.on_active_bank`` — DIE getestete Autoritaet, die die
        VCB-04-Vererbung (``bank=-1`` erbt vom naechsten Vorfahr mit fester Bank,
        heisst NICHT „alle Banks") ueber die ganze Parent-Kette inkl.
        verschachtelter Frames aufloest. Frueher rechnete der Frame das selbst mit
        abweichender Semantik nach. Ohne Canvas (z.B. im Aufbau) nur Seiten-Regel.
        Behebt: Bank-Pins von Widgets IN einem Frame blieben bei der Sichtbarkeit
        unbeachtet (Canvas._apply_bank_visibility iteriert nur direkte Kinder)."""
        on_page = (child.property("vc_page") or 0) == self._current_page
        cv = self._canvas()
        on_bank = cv.on_active_bank(child) if cv is not None else True
        return on_page and on_bank

    def _apply_bank_visibility(self):
        """Kombinierte Seiten+Bank-Sichtbarkeit der Kinder neu anwenden — vom
        Canvas propagiert und vom VCWidget-Bank-Parent-Walk gerufen. Rekursiv in
        verschachtelte Frames, damit auch deren Kinder neu bewertet werden."""
        for child in self.findChildren(
                VCWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
            child.setVisible(self._child_visible(child))
            if child is not self and hasattr(child, "_apply_bank_visibility"):
                child._apply_bank_visibility()

    def switch_page(self, page: int):
        self._current_page = max(0, min(self._page_count - 1, page))
        # VCB-01: nur DIREKTE Kinder umschalten — sonst versteckt der Seitenwechsel
        # eines aeusseren Frames auch die Kinder verschachtelter innerer Frames
        # (deren vc_page auf den INNEREN Frame bezogen ist). Konsistent mit
        # to_dict/on_child_activated/paintEvent.
        for child in self.findChildren(
                VCWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
            child.setVisible(self._child_visible(child))
        self.update()

    def add_child_to_page(self, widget: VCWidget, page: int = 0):
        widget.setParent(self)
        widget.setProperty("vc_page", page)
        widget.setVisible(self._child_visible(widget))
        if self._edit_mode:
            widget.set_edit_mode(True)
        # FRM-01: Delete-Ownership an die Box uebergeben. Die Methode verdrahtete
        # `delete_requested` frueher NICHT — ein per Snap-in/Drop hineingelegtes
        # Widget blieb an der Canvas (semantisch falsch) bzw. liess sich gar nicht
        # loeschen. Etwaige Alt-Verdrahtung loesen (kein Doppel-Delete), dann an das
        # (undobare) `_remove_child` der Box haengen.
        try:
            widget.delete_requested.disconnect()
        except (TypeError, RuntimeError):
            pass
        widget.delete_requested.connect(self._on_child_delete_requested)
        # VCB-02: KEIN bedingungsloses widget.show() — das ueberschrieb das
        # setVisible(page == _current_page) oben und liess das Widget auf der
        # falschen Seite erscheinen. Die Sichtbarkeit ist bereits korrekt gesetzt.

    # ── Child widget management ───────────────────────────────────────────────

    def _find_canvas(self):
        """Naechster Vorfahre mit Canvas-Undo-API (duck-typed, kein Import-Zyklus)."""
        obj = self.parent()
        while obj is not None:
            if hasattr(obj, "push_undo_snapshot") and hasattr(obj, "to_dict"):
                return obj
            obj = obj.parent() if hasattr(obj, "parent") else None
        return None

    def _add_child_widget(self, wtype: str, pos: QPoint | None = None):
        from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY
        cls = WIDGET_REGISTRY.get(wtype)
        if cls is None:
            return
        child = cls(parent=self)
        child.set_edit_mode(self._edit_mode)
        child.set_snap_grid(self._snap_grid)   # Snap des Frames an neues Kind weitergeben
        cr = self._content_rect()
        if pos is not None:
            child.move(pos)
        else:
            cx = cr.x() + max(0, (cr.width() - child.width()) // 2)
            cy = cr.y() + max(0, (cr.height() - child.height()) // 2)
            child.move(cx, cy)
        child.setProperty("vc_page", self._current_page)
        child.setVisible(True)
        child.delete_requested.connect(self._on_child_delete_requested)
        child.show()
        return child

    def _remove_child(self, widget: VCWidget):
        # Undo-Punkt VOR dem Entfernen (Canvas-Gesamt-Snapshot, wie beim Loeschen
        # eines Top-Level-Widgets) -> Strg+Z holt das in der Box geloeschte Widget
        # zurueck. Waehrend einer laufenden Wiederherstellung NICHT snapshotten.
        canvas = self._find_canvas()
        if canvas is not None and not getattr(canvas, "_restoring", False):
            try:
                canvas.push_undo_snapshot(canvas.to_dict())
            except Exception:
                pass
        widget.hide()
        widget.setParent(None)
        widget.deleteLater()

    def _on_child_delete_requested(self):
        # STAB-09: sender()-Adapter statt Lambda — die C++-Connection wuerde ein
        # self-fangendes Lambda stark und GC-unsichtbar pinnen.
        w = self.sender()
        if w is not None:
            self._remove_child(w)

    # ── Context menu ─────────────────────────────────────────────────────────

    def _show_context_menu(self, global_pos: QPoint):
        from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY
        menu = QMenu(self)

        add_menu = menu.addMenu("Widget hinzufügen")
        for wtype in WIDGET_REGISTRY:
            if wtype == "VCFrame":
                continue
            act = add_menu.addAction(wtype.replace("VC", ""))
            act.setData(wtype)

        menu.addSeparator()
        menu.addAction("Einstellungen...").triggered.connect(self._open_properties)
        # Bank-Zuweisung — wie bei normalen Widgets (VCWidget._set_bank). Erlaubt,
        # einen bestehenden Frame nachtraeglich auf eine andere Bank zu legen; der
        # Frame folgt als EINHEIT der Bank-Sichtbarkeit (Kinder blenden mit aus/ein).
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
        menu.addSeparator()
        menu.addAction("Vordergrund-Farbe").triggered.connect(self._pick_fg)
        menu.addAction("Hintergrund-Farbe").triggered.connect(self._pick_bg)

        chosen = menu.exec(global_pos)
        if chosen and chosen.data():
            self._add_child_widget(chosen.data())

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        # Tab-Klick wechselt die Seite — auch im Edit-Modus, damit man die Widgets
        # JEDER Seite bearbeiten kann (sonst bliebe im Edit-Modus nur Seite 1 sichtbar).
        if self._show_header and self._page_count > 1 and pos.y() < self._tab_height:
            w = max(40, self.width() // self._page_count)
            page = int(pos.x() // w)
            if 0 <= page < self._page_count:
                self.switch_page(page)
                event.accept()
                return
        if self._edit_mode:
            super().mousePressEvent(event)
            return
        super().mousePressEvent(event)

    # ── Effekt-Gruppen-Highlight (Box als Einheit) ─────────────────────────────

    def set_effect_highlight(self, on: bool):
        """Container-Variante: Glow als GEZEICHNETER Amber-Rahmen statt
        ``QGraphicsDropShadowEffect``. Ein Graphics-Effect auf einem Widget mit
        Kind-Widgets (= die Box + ihre Live-Regler) verursacht Render-Quirks der
        Kinder -> hier bewusst per paintEvent. So leuchtet die Box als EINHEIT,
        wenn man ein zugehoeriges Widget antippt oder den Effekt waehlt."""
        on = bool(on)
        if on == getattr(self, "_effect_highlight", False):
            return
        self._effect_highlight = on
        self.update()

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg_color)
        if self._solo:
            p.setPen(QPen(QColor("#e63946"), 2))
        else:
            p.setPen(QPen(QColor("#30363d"), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        if getattr(self, "_effect_highlight", False):
            p.setPen(QPen(QColor("#ff9500"), 3))         # Box-als-Einheit: Amber-Rahmen
            p.drawRect(self.rect().adjusted(1, 1, -2, -2))

        if self._show_header:
            header = QRect(0, 0, self.width(), self._tab_height)
            p.fillRect(header, QColor("#21262d"))
            if self._page_count <= 1:
                p.setPen(self._fg_color)
                p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                p.drawText(header, Qt.AlignmentFlag.AlignCenter, self.caption)
            else:
                w = max(40, self.width() // self._page_count)
                for i in range(self._page_count):
                    tab = self._tab_for_page(i)
                    if i == self._current_page:
                        p.fillRect(tab, QColor("#0d4f8b"))
                    p.setPen(QColor("#e6edf3") if i == self._current_page else self._fg_color)
                    p.setFont(QFont("Segoe UI", 8))
                    p.drawText(tab, Qt.AlignmentFlag.AlignCenter, f"P{i+1}")

        # Snap-Grid in der Content-Flaeche zeichnen (Edit-Modus) — gespiegelt vom
        # Canvas (gleiche 32-px-Teilung GRID*4, gleiche Farbe), auf die Content-
        # Flaeche geclippt, damit Header/Rahmen frei bleiben. Dasselbe Raster, an
        # dem die Kinder per Snap einrasten (set_snap_grid).
        if self._edit_mode:
            cr = self._content_rect()
            if cr.width() > 0 and cr.height() > 0:
                p.save()
                p.setClipRect(cr)
                p.setPen(QColor("#1f2937"))
                g = 32
                gx = cr.left()
                while gx <= cr.right():
                    p.drawLine(gx, cr.top(), gx, cr.bottom())
                    gx += g
                gy = cr.top()
                while gy <= cr.bottom():
                    p.drawLine(cr.left(), gy, cr.right(), gy)
                    gy += g
                p.restore()

        # Hinweis wenn Frame leer und im Edit-Modus
        if self._edit_mode:
            children = self.findChildren(VCWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)
            if not children:
                p.setPen(QColor("#30363d"))
                p.setFont(QFont("Segoe UI", 8))
                cr = self._content_rect()
                p.drawText(cr, Qt.AlignmentFlag.AlignCenter,
                           "Rechtsklick → Widget hinzufügen")
        p.end()

    # ── Properties ───────────────────────────────────────────────────────────

    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Frame Einstellungen")
        form = QFormLayout(dlg)
        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)
        pages = QSpinBox()
        pages.setRange(1, 10)
        pages.setValue(self._page_count)
        form.addRow("Seitenanzahl:", pages)
        header = QCheckBox()
        header.setChecked(self._show_header)
        form.addRow("Header anzeigen:", header)
        solo = QCheckBox("Solo-Frame (nur 1 Button gleichzeitig aktiv)")
        solo.setChecked(self._solo)
        form.addRow("Modus:", solo)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            self._page_count = pages.value()
            self._show_header = header.isChecked()
            self._solo = solo.isChecked()
            # VCB-03: die Seitenanzahl koennte reduziert worden sein -> _current_page
            # ueber den neuen Bereich hinaus. switch_page klemmt selbst und wendet die
            # Sichtbarkeit neu an (statt nur update(), das den alten Index liesse).
            self.switch_page(self._current_page)

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["page_count"] = self._page_count
        d["show_header"] = self._show_header
        d["solo"] = self._solo
        children = []
        for child in self.findChildren(VCWidget,
                                       options=Qt.FindChildOption.FindDirectChildrenOnly):
            cd = child.to_dict()
            cd["vc_page"] = child.property("vc_page") or 0
            children.append(cd)
        d["children"] = children
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self._page_count = max(1, int(d.get("page_count", 1)))
        self._show_header = d.get("show_header", True)
        self._solo = d.get("solo", False)
        # Kinder wiederherstellen
        from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY
        for cd in d.get("children", []):
            wtype = cd.get("type", "")
            cls = WIDGET_REGISTRY.get(wtype)
            if cls is None:
                continue
            child = cls(parent=self)
            child.apply_dict(cd)
            page = cd.get("vc_page", 0)
            child.setProperty("vc_page", page)
            # Edit-Mode/Snap des Frames an die wiederhergestellten Kinder
            # weiterreichen — beim set_edit_mode/_snap_grid des Frames (in
            # VCCanvas._add_widget) existierten sie noch nicht.
            child.set_edit_mode(self._edit_mode)
            child.set_snap_grid(self._snap_grid)
            child.delete_requested.connect(self._on_child_delete_requested)
        # Seiten-Sichtbarkeit konsistent setzen. Früher überschrieb ein
        # bedingungsloses child.show() die Seiten-Logik → alle Seiten überlappten
        # nach dem Laden. switch_page() blendet nur die aktuelle Seite ein.
        self._current_page = max(0, min(self._page_count - 1, self._current_page))
        self.switch_page(self._current_page)
