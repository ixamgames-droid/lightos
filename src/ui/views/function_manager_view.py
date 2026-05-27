"""Function Manager View — QLC+ style function browser and editor."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget,
    QTreeWidgetItem, QStackedWidget, QPushButton, QLabel,
    QMenu, QInputDialog, QMessageBox, QToolBar, QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer, QMimeData
from PySide6.QtGui import QFont, QAction, QDrag
from src.core.engine.function import FunctionType
from src.core.engine.function_manager import get_function_manager
from src.core.engine.script_func import ScriptFunction


FUNCTION_MIME = "application/x-lightos-function"


class _FunctionTree(QTreeWidget):
    """QTreeWidget mit Drag-Support fuer ShowManager (mimetype application/x-lightos-function)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)

    def mimeTypes(self):
        return [FUNCTION_MIME, "text/plain"]

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if item is None:
            return
        fid = item.data(0, Qt.ItemDataRole.UserRole)
        if fid is None:
            return
        mime = QMimeData()
        mime.setData(FUNCTION_MIME, str(int(fid)).encode("utf-8"))
        mime.setText(item.text(0))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


# Pseudo type for Scripts (ScriptFunction reuses FunctionType.Scene at the engine level
# but we want to display them in their own group). We use a string tag for grouping.
SCRIPT_GROUP = "Script"
LAYERED_EFFECT_GROUP = "LayeredEffect"
CAROUSEL_GROUP = "Carousel"


# Mapping type -> display label
_TYPE_LABELS = {
    FunctionType.Scene:     "Szenen",
    FunctionType.Chaser:    "Chasers",
    FunctionType.Sequence:  "Sequences",
    FunctionType.Collection:"Collections",
    FunctionType.Show:      "Shows",
    FunctionType.EFX:       "EFX",
    FunctionType.RGBMatrix: "RGB-Matrix",
    FunctionType.Audio:     "Audio",
    SCRIPT_GROUP:           "Scripts",
    LAYERED_EFFECT_GROUP:   "Layered-Effekte",
    CAROUSEL_GROUP:         "Carousels",
}

_TYPE_ORDER = [
    FunctionType.Scene,
    FunctionType.Chaser,
    FunctionType.Sequence,
    FunctionType.Collection,
    FunctionType.Show,
    FunctionType.EFX,
    LAYERED_EFFECT_GROUP,
    CAROUSEL_GROUP,
    FunctionType.RGBMatrix,
    FunctionType.Audio,
    SCRIPT_GROUP,
]


class FunctionManagerView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._fm = get_function_manager()
        self._type_items: dict = {}
        self._setup_ui()
        self._populate_tree()

        # Refresh timer — every 500 ms update running state (bold = running)
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._refresh_running_state)
        self._timer.start()

        # Zentraler StateSync
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            sync.subscribe(SyncEvent.REFRESH_ALL, lambda *_: self._sync_refresh())
            sync.subscribe(SyncEvent.FUNCTION_CHANGED, lambda *_: self._sync_refresh())
            sync.subscribe(SyncEvent.PATCH_CHANGED, lambda *_: self._sync_refresh())
        except Exception as e:
            print(f"[function_manager_view] sync subscribe error: {e}")

    def _sync_refresh(self):
        try:
            self._refresh_tree()
        except Exception as e:
            print(f"[function_manager_view] refresh error: {e}")

    # ── UI setup ──────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 2, 4, 2)
        toolbar.setSpacing(4)

        for label, ftype in [
            ("+ Szene", FunctionType.Scene),
            ("+ Chaser", FunctionType.Chaser),
            ("+ Sequence", FunctionType.Sequence),
            ("+ Collection", FunctionType.Collection),
            ("+ Show", FunctionType.Show),
            ("+ Audio", FunctionType.Audio),
            ("+ Script", SCRIPT_GROUP),
            ("+ Layered Effekt", LAYERED_EFFECT_GROUP),
            ("+ Carousel", CAROUSEL_GROUP),
        ]:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda checked=False, t=ftype: self._new_function(t))
            toolbar.addWidget(btn)

        toolbar.addStretch(1)

        self._btn_run = QPushButton("Run")
        self._btn_run.setFixedHeight(26)
        self._btn_run.clicked.connect(self._run_selected)
        toolbar.addWidget(self._btn_run)

        self._btn_stop = QPushButton("Stop")
        self._btn_stop.setFixedHeight(26)
        self._btn_stop.clicked.connect(self._stop_selected)
        toolbar.addWidget(self._btn_stop)

        self._btn_del = QPushButton("Loeschen")
        self._btn_del.setFixedHeight(26)
        self._btn_del.clicked.connect(self._delete_selected)
        toolbar.addWidget(self._btn_del)

        toolbar_widget = QWidget()
        toolbar_widget.setLayout(toolbar)
        root.addWidget(toolbar_widget)

        # Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        # Left — tree
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._tree = _FunctionTree()
        self._tree.setHeaderLabel("Funktionen")
        self._tree.setMinimumWidth(200)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        self._tree.currentItemChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self._tree)
        splitter.addWidget(left)

        # Right — stacked editor
        self._stack = QStackedWidget()
        self._stack.addWidget(_placeholder("Funktion auswaehlen oder erstellen"))
        splitter.addWidget(self._stack)

        splitter.setSizes([250, 750])

    # ── Tree population ───────────────────────────────────────────────────────

    def _populate_tree(self):
        self._tree.clear()
        self._type_items.clear()

        for ftype in _TYPE_ORDER:
            top = QTreeWidgetItem(self._tree, [_TYPE_LABELS[ftype]])
            top.setData(0, Qt.ItemDataRole.UserRole, None)
            top.setExpanded(True)
            self._type_items[ftype] = top

        # Add existing functions
        for f in self._fm.all():
            self._add_tree_item(f)

    def _add_tree_item(self, f) -> QTreeWidgetItem:
        # Script / LayeredEffect / Carousel haben eigene Gruppen, obwohl sie
        # intern auf andere FunctionType-Werte mappen.
        if getattr(f, "is_script", False):
            parent = self._type_items.get(SCRIPT_GROUP)
        elif getattr(f, "is_layered_effect", False):
            parent = self._type_items.get(LAYERED_EFFECT_GROUP)
        elif getattr(f, "is_carousel", False):
            parent = self._type_items.get(CAROUSEL_GROUP)
        else:
            parent = self._type_items.get(f.function_type)
        if parent is None:
            return None
        item = QTreeWidgetItem(parent, [f.name])
        item.setData(0, Qt.ItemDataRole.UserRole, f.id)
        return item

    def _refresh_tree(self):
        """Rebuild tree preserving selection."""
        selected_id = self._selected_function_id()
        self._populate_tree()
        if selected_id is not None:
            self._select_by_id(selected_id)

    def _refresh_running_state(self):
        """Make bold the items whose function is currently running."""
        bold_font = QFont()
        bold_font.setBold(True)
        normal_font = QFont()

        def _walk(item: QTreeWidgetItem):
            fid = item.data(0, Qt.ItemDataRole.UserRole)
            if fid is not None:
                running = self._fm.is_running(fid)
                item.setFont(0, bold_font if running else normal_font)
            for i in range(item.childCount()):
                _walk(item.child(i))

        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            _walk(root.child(i))

    # ── Selection helpers ─────────────────────────────────────────────────────

    def _selected_function_id(self) -> int | None:
        item = self._tree.currentItem()
        if item is None:
            return None
        return item.data(0, Qt.ItemDataRole.UserRole)

    def _select_by_id(self, fid: int):
        root = self._tree.invisibleRootItem()

        def _walk(item: QTreeWidgetItem) -> bool:
            if item.data(0, Qt.ItemDataRole.UserRole) == fid:
                self._tree.setCurrentItem(item)
                return True
            for i in range(item.childCount()):
                if _walk(item.child(i)):
                    return True
            return False

        for i in range(root.childCount()):
            if _walk(root.child(i)):
                break

    # ── Actions ───────────────────────────────────────────────────────────────

    def _new_function(self, ftype):
        if ftype == FunctionType.Scene:
            f = self._fm.new_scene()
        elif ftype == FunctionType.Chaser:
            f = self._fm.new_chaser()
        elif ftype == FunctionType.Sequence:
            f = self._fm.new_sequence()
        elif ftype == FunctionType.Collection:
            f = self._fm.new_collection()
        elif ftype == FunctionType.Show:
            f = self._fm.new_show()
        elif ftype == FunctionType.Audio:
            f = self._fm.new_audio()
        elif ftype == SCRIPT_GROUP:
            sf = ScriptFunction()
            self._fm.add(sf)
            f = sf
        elif ftype == LAYERED_EFFECT_GROUP:
            try:
                f = self._fm.new_layered_effect()
            except Exception as e:
                print(f"[function_manager_view] new_layered_effect error: {e}")
                return
        elif ftype == CAROUSEL_GROUP:
            try:
                f = self._fm.new_carousel()
            except Exception as e:
                print(f"[function_manager_view] new_carousel error: {e}")
                return
        else:
            return

        self._add_tree_item(f)
        self._select_by_id(f.id)
        self._open_editor(f.id)

    def _delete_selected(self):
        fid = self._selected_function_id()
        if fid is None:
            return
        f = self._fm.get(fid)
        if f is None:
            return
        reply = QMessageBox.question(
            self, "Loeschen",
            f'Funktion "{f.name}" wirklich loeschen?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._fm.remove(fid)
            self._refresh_tree()
            # Reset editor
            while self._stack.count() > 1:
                w = self._stack.widget(1)
                self._stack.removeWidget(w)
                w.deleteLater()
            self._stack.setCurrentIndex(0)

    def _run_selected(self):
        fid = self._selected_function_id()
        if fid is not None:
            self._fm.start(fid)

    def _stop_selected(self):
        fid = self._selected_function_id()
        if fid is not None:
            self._fm.stop(fid)

    def _rename_selected(self):
        fid = self._selected_function_id()
        if fid is None:
            return
        f = self._fm.get(fid)
        if f is None:
            return
        text, ok = QInputDialog.getText(self, "Umbenennen", "Neuer Name:", text=f.name)
        if ok and text.strip():
            f.name = text.strip()
            self._refresh_tree()
            self._select_by_id(fid)

    # ── Editor ────────────────────────────────────────────────────────────────

    def _open_editor(self, fid: int):
        f = self._fm.get(fid)
        if f is None:
            return

        # Remove old editors (keep placeholder at index 0)
        while self._stack.count() > 1:
            w = self._stack.widget(1)
            self._stack.removeWidget(w)
            w.deleteLater()

        if getattr(f, "is_script", False):
            from src.ui.views.script_editor import ScriptEditor
            editor = ScriptEditor(f)
        elif getattr(f, "is_layered_effect", False):
            try:
                from src.ui.views.effect_layer_editor import EffectLayerEditor
                editor = EffectLayerEditor(f)
            except Exception as e:
                editor = _placeholder(f"Effect-Layer Editor Fehler: {e}")
        elif getattr(f, "is_carousel", False):
            try:
                from src.ui.views.carousel_editor import CarouselEditor
                editor = CarouselEditor(f)
            except Exception as e:
                editor = _placeholder(f"Carousel Editor Fehler: {e}")
        elif f.function_type == FunctionType.Scene:
            from src.ui.views.scene_editor import SceneEditor
            editor = SceneEditor(f)
        elif f.function_type == FunctionType.Chaser:
            from src.ui.views.chaser_editor import ChaserEditor
            editor = ChaserEditor(f)
        elif f.function_type == FunctionType.Sequence:
            try:
                from src.ui.views.sequence_editor import SequenceEditor
                editor = SequenceEditor(f)
            except Exception as e:
                editor = _placeholder(f"Sequence Editor Fehler: {e}")
        elif f.function_type == FunctionType.Audio:
            try:
                from src.ui.views.audio_editor import AudioEditor
                editor = AudioEditor(f)
            except Exception as e:
                editor = _placeholder(f"Audio Editor Fehler: {e}")
        elif f.function_type == FunctionType.Collection:
            try:
                from src.ui.views.collection_editor import CollectionEditor
                editor = CollectionEditor(f)
            except Exception as e:
                editor = _placeholder(f"Collection Editor Fehler: {e}")
        elif f.function_type == FunctionType.Show:
            editor = _placeholder(
                f"Show: {f.name}\n\nBearbeiten in 'Playback' → 'Show Manager'.")
        else:
            editor = _placeholder(f"{f.function_type.value}: {f.name}\n\nEditor kommt bald.")

        self._stack.addWidget(editor)
        self._stack.setCurrentWidget(editor)

    # ── Tree events ───────────────────────────────────────────────────────────

    def _on_double_click(self, item: QTreeWidgetItem, _col: int):
        fid = item.data(0, Qt.ItemDataRole.UserRole)
        if fid is not None:
            self._open_editor(fid)

    def _on_selection_changed(self, current: QTreeWidgetItem, _prev):
        if current is None:
            return
        fid = current.data(0, Qt.ItemDataRole.UserRole)
        if fid is not None:
            self._open_editor(fid)

    def _show_context_menu(self, pos):
        item = self._tree.itemAt(pos)
        menu = QMenu(self)

        if item is not None and item.data(0, Qt.ItemDataRole.UserRole) is None:
            # Top-level type item — only "new" actions
            ftype = None
            for t, ti in self._type_items.items():
                if ti is item:
                    ftype = t
                    break
            if ftype in (FunctionType.Scene, FunctionType.Chaser,
                         FunctionType.Collection, FunctionType.Show, SCRIPT_GROUP):
                menu.addAction(f"Neue {_TYPE_LABELS[ftype][:-1]}",
                               lambda t=ftype: self._new_function(t))
        else:
            menu.addAction("Neue Szene",      lambda: self._new_function(FunctionType.Scene))
            menu.addAction("Neuer Chaser",     lambda: self._new_function(FunctionType.Chaser))
            menu.addAction("Neue Collection",  lambda: self._new_function(FunctionType.Collection))
            menu.addAction("Neue Show",        lambda: self._new_function(FunctionType.Show))
            menu.addAction("Neues Script",     lambda: self._new_function(SCRIPT_GROUP))
            if item is not None and item.data(0, Qt.ItemDataRole.UserRole) is not None:
                menu.addSeparator()
                menu.addAction("Umbenennen", self._rename_selected)
                menu.addAction("Loeschen",   self._delete_selected)

        menu.exec(self._tree.viewport().mapToGlobal(pos))


# ── Helper ────────────────────────────────────────────────────────────────────

def _placeholder(text: str) -> QWidget:
    w = QWidget()
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet("color: #666666; font-size: 14px;")
    layout = QVBoxLayout(w)
    layout.addWidget(lbl)
    return w
