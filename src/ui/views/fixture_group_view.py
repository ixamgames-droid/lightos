"""Fixture Group View - 2D grid where fixtures are placed (drag&drop)."""
from __future__ import annotations
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QComboBox, QSpinBox, QInputDialog, QMessageBox, QGroupBox,
    QFormLayout,
)
from PySide6.QtCore import Qt, QMimeData, QSize, QPoint
from PySide6.QtGui import (
    QPainter, QColor, QPen, QDrag, QFont, QBrush,
)
from src.core.app_state import get_state
from src.core.database.models import FixtureGroup
from sqlalchemy.orm import Session
from sqlalchemy import select, delete


class FixtureGridWidget(QWidget):
    """Custom widget that paints the 2D grid with placed fixtures.

    Accepts drops from the fixture list (Mime type: application/x-fid).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cols = 8
        self.rows = 8
        self.positions: dict[tuple[int, int], int] = {}  # (col, row) -> fid
        self.setMinimumSize(320, 320)
        self.setAcceptDrops(True)
        self._labels: dict[int, str] = {}

    def update_fixture_labels(self, labels: dict[int, str]):
        self._labels = labels
        self.update()

    def set_grid(self, cols: int, rows: int):
        self.cols = max(1, cols)
        self.rows = max(1, rows)
        # Drop out-of-bounds positions
        self.positions = {(c, r): fid for (c, r), fid in self.positions.items()
                          if c < self.cols and r < self.rows}
        self.update()

    def cell_size(self):
        if self.cols == 0 or self.rows == 0:
            return 32, 32
        cw = self.width() / self.cols
        ch = self.height() / self.rows
        return cw, ch

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#181820"))
        cw, ch = self.cell_size()
        # Grid lines
        p.setPen(QPen(QColor("#333333"), 1))
        for c in range(self.cols + 1):
            x = int(c * cw)
            p.drawLine(x, 0, x, self.height())
        for r in range(self.rows + 1):
            y = int(r * ch)
            p.drawLine(0, y, self.width(), y)
        # Placed fixtures
        font = QFont("Segoe UI", 9)
        font.setBold(True)
        p.setFont(font)
        for (c, r), fid in self.positions.items():
            x = c * cw
            y = r * ch
            rect = (int(x) + 2, int(y) + 2, int(cw) - 4, int(ch) - 4)
            p.fillRect(rect[0], rect[1], rect[2], rect[3], QBrush(QColor("#0978FF")))
            p.setPen(QColor("#ffffff"))
            label = self._labels.get(fid, str(fid))
            p.drawText(rect[0], rect[1], rect[2], rect[3],
                       Qt.AlignmentFlag.AlignCenter, f"{fid}")
            small = QFont("Segoe UI", 7)
            p.setFont(small)
            p.drawText(rect[0], rect[1] + 14, rect[2], rect[3] - 14,
                       Qt.AlignmentFlag.AlignCenter, label[:8])
            p.setFont(font)
        p.end()

    # ── Drag & Drop ───────────────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-fid"):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-fid"):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat("application/x-fid"):
            return
        try:
            fid = int(bytes(event.mimeData().data("application/x-fid")).decode())
        except Exception:
            return
        cw, ch = self.cell_size()
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        col = int(pos.x() // cw)
        row = int(pos.y() // ch)
        if 0 <= col < self.cols and 0 <= row < self.rows:
            # Remove any previous placement of this fid
            self.positions = {k: v for k, v in self.positions.items() if v != fid}
            self.positions[(col, row)] = fid
            self.update()
            event.acceptProposedAction()

    def mousePressEvent(self, event):
        # Allow right-click to remove
        if event.button() == Qt.MouseButton.RightButton:
            cw, ch = self.cell_size()
            col = int(event.position().x() // cw)
            row = int(event.position().y() // ch)
            if (col, row) in self.positions:
                del self.positions[(col, row)]
                self.update()


class FixtureListWithDrag(QListWidget):
    """QListWidget that supports starting a drag with the fixture id."""

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item:
            return
        fid = item.data(Qt.ItemDataRole.UserRole)
        if fid is None:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-fid", str(fid).encode())
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)


class FixtureGroupView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = get_state()
        self._current_group: FixtureGroup | None = None
        self._setup_ui()
        self._reload_group_list()

        # Zentraler StateSync
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            sync.subscribe(SyncEvent.REFRESH_ALL, lambda *_: self._sync_refresh())
            sync.subscribe(SyncEvent.PATCH_CHANGED, lambda *_: self._sync_refresh())
        except Exception as e:
            print(f"[fixture_group_view] sync subscribe error: {e}")

    def _sync_refresh(self):
        try:
            self._reload_group_list()
            self._refresh_fixtures()
        except Exception as e:
            print(f"[fixture_group_view] sync_refresh error: {e}")

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)

        # ── Left: group selector + fixtures ───────────────────────────────
        left = QVBoxLayout()

        grp_row = QHBoxLayout()
        grp_row.addWidget(QLabel("Gruppe:"))
        self._combo_group = QComboBox()
        self._combo_group.currentIndexChanged.connect(self._on_group_selected)
        grp_row.addWidget(self._combo_group, 1)
        left.addLayout(grp_row)

        btns = QHBoxLayout()
        b_new = QPushButton("+ Neu")
        b_new.clicked.connect(self._new_group)
        btns.addWidget(b_new)
        b_del = QPushButton("Loeschen")
        b_del.setObjectName("btn_danger")
        b_del.clicked.connect(self._delete_group)
        btns.addWidget(b_del)
        b_save = QPushButton("Speichern")
        b_save.clicked.connect(self._save_group)
        btns.addWidget(b_save)
        left.addLayout(btns)

        # Grid size config
        size_box = QGroupBox("Rastergroesse")
        size_form = QFormLayout(size_box)
        self._spin_cols = QSpinBox(); self._spin_cols.setRange(1, 64); self._spin_cols.setValue(8)
        self._spin_rows = QSpinBox(); self._spin_rows.setRange(1, 64); self._spin_rows.setValue(8)
        self._spin_cols.valueChanged.connect(self._apply_grid_size)
        self._spin_rows.valueChanged.connect(self._apply_grid_size)
        size_form.addRow("Spalten:", self._spin_cols)
        size_form.addRow("Zeilen:", self._spin_rows)
        left.addWidget(size_box)

        # Fixtures list
        left.addWidget(QLabel("Fixtures (drag auf Raster):"))
        self._fixture_list = FixtureListWithDrag()
        self._fixture_list.setDragEnabled(True)
        left.addWidget(self._fixture_list, 1)

        btn_refresh = QPushButton("Fixtures neu laden")
        btn_refresh.clicked.connect(self._refresh_fixtures)
        left.addWidget(btn_refresh)

        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(260)
        root.addWidget(left_w)

        # ── Right: grid ──────────────────────────────────────────────────
        right = QVBoxLayout()
        right.addWidget(QLabel("Raster (Drag&Drop fuer Platzierung, Rechtsklick zum Entfernen):"))
        self._grid_widget = FixtureGridWidget()
        right.addWidget(self._grid_widget, 1)
        right_w = QWidget()
        right_w.setLayout(right)
        root.addWidget(right_w, 1)

        self._refresh_fixtures()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _session(self) -> Session | None:
        eng = getattr(self._state, "_show_engine", None)
        if eng is None:
            return None
        return Session(eng)

    def _refresh_fixtures(self):
        labels = {}
        self._fixture_list.clear()
        for f in self._state.get_patched_fixtures():
            item = QListWidgetItem(f"[{f.fid:03d}] {f.label}")
            item.setData(Qt.ItemDataRole.UserRole, f.fid)
            self._fixture_list.addItem(item)
            labels[f.fid] = f.label
        self._grid_widget.update_fixture_labels(labels)

    def _reload_group_list(self):
        self._combo_group.blockSignals(True)
        self._combo_group.clear()
        s = self._session()
        if s is None:
            self._combo_group.blockSignals(False)
            return
        try:
            with s:
                groups = list(s.execute(select(FixtureGroup).order_by(FixtureGroup.id)).scalars())
                for g in groups:
                    self._combo_group.addItem(g.name, g.id)
                if groups:
                    self._current_group = groups[0]
                else:
                    self._current_group = None
        except Exception as e:
            print(f"[FixtureGroupView] reload error: {e}")
            self._current_group = None
        self._combo_group.blockSignals(False)
        if self._current_group is not None:
            self._load_group(self._current_group)

    def _on_group_selected(self, idx: int):
        gid = self._combo_group.itemData(idx)
        if gid is None:
            return
        s = self._session()
        if s is None:
            return
        try:
            with s:
                g = s.get(FixtureGroup, gid)
                if g:
                    self._current_group = g
                    self._load_group(g)
        except Exception as e:
            print(f"[FixtureGroupView] select error: {e}")

    def _load_group(self, g: FixtureGroup):
        self._spin_cols.blockSignals(True)
        self._spin_rows.blockSignals(True)
        self._spin_cols.setValue(g.cols)
        self._spin_rows.setValue(g.rows)
        self._spin_cols.blockSignals(False)
        self._spin_rows.blockSignals(False)
        try:
            pos_dict = json.loads(g.positions_json or "{}")
        except Exception:
            pos_dict = {}
        positions = {}
        for k, v in pos_dict.items():
            try:
                c, r = k.split(",")
                positions[(int(c), int(r))] = int(v)
            except Exception:
                continue
        self._grid_widget.set_grid(g.cols, g.rows)
        self._grid_widget.positions = positions
        self._grid_widget.update()

    def _new_group(self):
        name, ok = QInputDialog.getText(self, "Neue Gruppe", "Name:")
        if not ok or not name.strip():
            return
        s = self._session()
        if s is None:
            QMessageBox.warning(self, "Fehler", "Keine Show geoeffnet.")
            return
        try:
            with s:
                g = FixtureGroup(name=name.strip(), cols=8, rows=8, positions_json="{}")
                s.add(g)
                s.commit()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))
            return
        self._reload_group_list()

    def _delete_group(self):
        if self._current_group is None:
            return
        reply = QMessageBox.question(self, "Loeschen",
                                     f'Gruppe "{self._current_group.name}" loeschen?',
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        s = self._session()
        if s is None:
            return
        try:
            with s:
                s.execute(delete(FixtureGroup).where(FixtureGroup.id == self._current_group.id))
                s.commit()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))
            return
        self._current_group = None
        self._reload_group_list()

    def _save_group(self):
        if self._current_group is None:
            QMessageBox.information(self, "Speichern", "Erst eine Gruppe anlegen.")
            return
        s = self._session()
        if s is None:
            return
        positions = self._grid_widget.positions
        pos_json = json.dumps({f"{c},{r}": fid for (c, r), fid in positions.items()})
        try:
            with s:
                g = s.get(FixtureGroup, self._current_group.id)
                if g is None:
                    return
                g.cols = self._spin_cols.value()
                g.rows = self._spin_rows.value()
                g.positions_json = pos_json
                s.commit()
            QMessageBox.information(self, "Gespeichert", f'Gruppe "{self._current_group.name}" gespeichert.')
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))

    def _apply_grid_size(self, *_):
        c = self._spin_cols.value()
        r = self._spin_rows.value()
        self._grid_widget.set_grid(c, r)
