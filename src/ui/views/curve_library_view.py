"""B2 / FW-4(a): Standalone-Ansicht der Fade-Kurven-Bibliothek.

Listet `get_curve_library().all()` (Presets + benutzerdefinierte Kurven) und
erlaubt Neu / Bearbeiten / Duplizieren / Umbenennen / Löschen. Presets sind
schreibgeschützt. Bisher war die Bibliothek nur über das Popup im Kurven-Editor
(CurveEditorDialog) erreichbar — diese View macht sie als eigene Verwaltung sichtbar.
"""
from __future__ import annotations
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                               QListWidgetItem, QPushButton, QLabel, QInputDialog,
                               QMessageBox)

from src.core.engine.curve_library import get_curve_library
from src.ui.widgets.curve_editor import CurveEditorDialog, CurveThumbnail


class CurveLibraryView(QWidget):
    """Verwaltung der show-weiten Fade-Kurven-Bibliothek."""

    curves_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(QLabel("Fade-Kurven-Bibliothek"))

        body = QHBoxLayout()
        self._list = QListWidget()
        self._list.currentItemChanged.connect(lambda *_: self._on_selection())
        body.addWidget(self._list, 1)
        self._preview = CurveThumbnail()
        self._preview.setMinimumSize(150, 120)
        body.addWidget(self._preview)
        lay.addLayout(body)

        row = QHBoxLayout()
        self._btn_new = QPushButton("Neu")
        self._btn_edit = QPushButton("Bearbeiten")
        self._btn_dup = QPushButton("Duplizieren")
        self._btn_ren = QPushButton("Umbenennen")
        self._btn_del = QPushButton("Löschen")
        self._btn_new.clicked.connect(self._on_new)
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_dup.clicked.connect(self._on_duplicate)
        self._btn_ren.clicked.connect(self._on_rename)
        self._btn_del.clicked.connect(self._on_delete)
        for b in (self._btn_new, self._btn_edit, self._btn_dup, self._btn_ren, self._btn_del):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)

        self._refresh()

    # ── Bibliothek <-> Liste ────────────────────────────────────────────────────

    def _refresh(self):
        lib = get_curve_library()
        self._list.blockSignals(True)
        self._list.clear()
        for c in lib.presets():
            it = QListWidgetItem(f"🔒 {c.name}")
            it.setData(Qt.ItemDataRole.UserRole, c.name)
            self._list.addItem(it)
        for c in lib.user_curves():
            it = QListWidgetItem(f"★ {c.name}")
            it.setData(Qt.ItemDataRole.UserRole, c.name)
            self._list.addItem(it)
        self._list.blockSignals(False)
        if self._list.count():
            self._list.setCurrentRow(0)
        self._on_selection()

    def _selected_name(self):
        it = self._list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _selected_curve(self):
        name = self._selected_name()
        return get_curve_library().find(name) if name else None

    def _is_preset(self, name) -> bool:
        return bool(name) and get_curve_library().is_preset(name)

    def _on_selection(self):
        c = self._selected_curve()
        if c is not None:
            self._preview.set_curve(c)
        name = self._selected_name()
        has = name is not None
        editable = has and not self._is_preset(name)
        self._btn_del.setEnabled(editable)
        self._btn_ren.setEnabled(editable)
        self._btn_edit.setEnabled(has)
        self._btn_dup.setEnabled(has)

    def _select(self, name):
        for i in range(self._list.count()):
            if self._list.item(i).data(Qt.ItemDataRole.UserRole) == name:
                self._list.setCurrentRow(i)
                return

    # ── Operationen (dialogfrei aufrufbar -> testbar) ───────────────────────────

    def _do_add(self, curve):
        saved = get_curve_library().add(curve)
        self._refresh()
        self._select(saved.name)
        self.curves_changed.emit()
        return saved

    def _do_duplicate(self, curve):
        c = curve.copy()
        c.name = get_curve_library()._unique_name(f"{curve.name} Kopie")
        return self._do_add(c)

    def _do_rename(self, curve, new_name):
        new_name = (new_name or "").strip()
        if (not new_name or new_name == curve.name
                or get_curve_library().is_preset(curve.name)):
            return None
        get_curve_library().remove(curve.name)
        c = curve.copy()
        c.name = new_name
        return self._do_add(c)

    def _do_delete(self, name):
        ok = get_curve_library().remove(name)
        if ok:
            self._refresh()
            self.curves_changed.emit()
        return ok

    # ── Button-Handler (mit Dialogen) ───────────────────────────────────────────

    def _on_new(self):
        dlg = CurveEditorDialog(None, "Neue Fade-Kurve", self)
        if dlg.exec() and dlg.result_curve is not None:
            cur = dlg.result_curve
            name, ok = QInputDialog.getText(self, "Kurve speichern", "Name:",
                                            text=cur.name or "Kurve")
            if ok and name.strip():
                cur.name = name.strip()
                self._do_add(cur)

    def _on_edit(self):
        c = self._selected_curve()
        if c is None:
            return
        dlg = CurveEditorDialog(c, f"Kurve: {c.name}", self)
        if dlg.exec() and dlg.result_curve is not None:
            res = dlg.result_curve
            # Preset bearbeiten -> als neue User-Kurve ablegen; User -> ersetzen.
            res.name = (get_curve_library()._unique_name(c.name)
                        if self._is_preset(c.name) else c.name)
            self._do_add(res)

    def _on_duplicate(self):
        c = self._selected_curve()
        if c is not None:
            self._do_duplicate(c)

    def _on_rename(self):
        c = self._selected_curve()
        if c is None or self._is_preset(c.name):
            return
        name, ok = QInputDialog.getText(self, "Umbenennen", "Neuer Name:", text=c.name)
        if ok:
            self._do_rename(c, name)

    def _on_delete(self):
        name = self._selected_name()
        if not name or self._is_preset(name):
            return
        if QMessageBox.question(self, "Löschen", f'Kurve "{name}" löschen?') == \
                QMessageBox.StandardButton.Yes:
            self._do_delete(name)
