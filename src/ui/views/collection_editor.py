"""Collection Editor — Editor fuer Collection-Funktion (parallele Ausfuehrung)."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QGroupBox, QDialog,
)
from PySide6.QtCore import Qt
from src.core.engine.collection import Collection
from src.core.engine.function_manager import get_function_manager


class CollectionEditor(QWidget):
    """Bearbeite eine Collection: Liste der parallel laufenden Funktionen."""

    def __init__(self, collection: Collection, parent=None):
        super().__init__(parent)
        self._coll = collection
        self._fm = get_function_manager()
        self._setup_ui()
        self._refresh()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        title = QLabel(f"Collection: {self._coll.name}")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #58a6ff;")
        root.addWidget(title)

        # Name
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self._edit_name = QLineEdit(self._coll.name)
        self._edit_name.editingFinished.connect(self._on_name_changed)
        name_row.addWidget(self._edit_name, 1)
        root.addLayout(name_row)

        # Member list
        list_box = QGroupBox("Enthaltene Funktionen (parallel)")
        list_layout = QVBoxLayout(list_box)
        self._lst = QListWidget()
        self._lst.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        list_layout.addWidget(self._lst)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ Funktion hinzufügen")
        btn_add.clicked.connect(self._add_function)
        btn_remove = QPushButton("- Entfernen")
        btn_remove.clicked.connect(self._remove_selected)
        btn_up = QPushButton("Hoch")
        btn_up.clicked.connect(lambda: self._move_selected(-1))
        btn_down = QPushButton("Runter")
        btn_down.clicked.connect(lambda: self._move_selected(1))
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_remove)
        btn_row.addWidget(btn_up)
        btn_row.addWidget(btn_down)
        btn_row.addStretch(1)
        list_layout.addLayout(btn_row)
        root.addWidget(list_box, 1)

        # Transport
        tr = QHBoxLayout()
        btn_play = QPushButton("Play All")
        btn_play.clicked.connect(self._play)
        btn_stop = QPushButton("Stop All")
        btn_stop.clicked.connect(self._stop)
        tr.addWidget(btn_play)
        tr.addWidget(btn_stop)
        tr.addStretch(1)
        root.addLayout(tr)

    def _refresh(self):
        self._lst.clear()
        for fid in self._coll.function_ids:
            fn = self._fm.get(fid)
            label = fn.name if fn else f"<gelöscht id={fid}>"
            ftype = fn.function_type.value if fn else "?"
            item = QListWidgetItem(f"[{ftype}] {label}  (id={fid})")
            item.setData(Qt.ItemDataRole.UserRole, fid)
            if not fn:
                item.setForeground(Qt.GlobalColor.red)
            self._lst.addItem(item)

    def _on_name_changed(self):
        n = self._edit_name.text().strip()
        if n:
            self._coll.name = n
            try:
                from src.core.sync import get_sync, SyncEvent
                get_sync().emit(SyncEvent.FUNCTION_CHANGED, None)
            except Exception:
                pass

    def _add_function(self):
        try:
            from src.ui.views.chaser_editor import FunctionSelectorDialog
        except Exception as e:
            print(f"[CollectionEditor] FunctionSelectorDialog import: {e}")
            return
        dlg = FunctionSelectorDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        fid = dlg.selected_id
        if fid is None or fid == self._coll.id:
            return
        self._coll.add_function(fid)
        self._refresh()

    def _remove_selected(self):
        for it in self._lst.selectedItems():
            fid = it.data(Qt.ItemDataRole.UserRole)
            self._coll.remove_function(fid)
        self._refresh()

    def _move_selected(self, dir: int):
        items = self._lst.selectedItems()
        if not items:
            return
        row = self._lst.row(items[0])
        new_row = row + dir
        if 0 <= new_row < len(self._coll.function_ids):
            self._coll.function_ids[row], self._coll.function_ids[new_row] = (
                self._coll.function_ids[new_row], self._coll.function_ids[row])
            self._refresh()
            self._lst.setCurrentRow(new_row)

    def _play(self):
        self._fm.start(self._coll.id)

    def _stop(self):
        self._fm.stop(self._coll.id)
        # Stop children too
        for fid in self._coll.function_ids:
            self._fm.stop(fid)
