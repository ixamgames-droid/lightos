"""„Gruppe bearbeiten"-Dialog für die Patch-Gruppenansicht.

Bearbeitet eine bestehende FixtureGroup komplett ohne Drag&Drop — bewusst
touch-tauglich (große Buttons, Antippen statt Ziehen):

- Name ändern (mit Duplikat-Rückfrage wie beim Umbenennen)
- Mitglieder entfernen / verfügbare Fixtures hinzufügen (Doppeltipp oder Button)
- Reihenfolge ändern (▲/▼) — relevant für Fan/Spread/Chase, denn die
  Mitglieder-Reihenfolge ist der zeilenweise Raster-Scan (siehe
  programmer_view._group_fids)

Speichern-Semantik fürs Raster (positions_json):
- Nur hinzufügen/entfernen: vorhandene Zellen bleiben erhalten, neue Mitglieder
  landen auf der ersten freien Zelle (zeilenweise).
- Wurde umsortiert (▲/▼ benutzt), wird das Raster zeilenweise neu geschrieben —
  ein eventuelles 2D-Layout (Matrix) geht dabei bewusst verloren; der Dialog
  weist darauf hin.

Der Dialog schreibt selbst NICHT in die Datenbank — der Aufrufer liest
``result()`` und persistiert (gleiche Session-Disziplin wie der Rest der View).
"""
from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QVBoxLayout)


_BTN_STYLE = """
    QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                  border-radius:4px; font-size:11px; padding:4px 10px; }
    QPushButton:hover { background:#30363d; }
    QPushButton:disabled { color:#555d68; }
"""
_LIST_STYLE = """
    QListWidget { background:#1a1a26; color:#cccccc; border:1px solid #333;
                  border-radius:4px; font-size:11px; }
    QListWidget::item { min-height:32px; }
    QListWidget::item:hover { background:#2a2a3a; }
    QListWidget::item:selected { background:#0978FF; color:#fff; }
"""


def group_member_fids(positions_json: str) -> list[int]:
    """Fids in Raster-Reihenfolge (Zeile, dann Spalte) — gleiche Logik wie
    programmer_view._group_fids, hier für den Dialog wiederverwendet."""
    try:
        pos = json.loads(positions_json or "{}")
    except Exception:
        return []
    items = []
    for key, v in pos.items():
        # FM-16e: Kopf-Zellen "fid:head" sind KEINE ganzen Mitglieder -> ueberspringen
        # (sie bleiben beim Speichern verbatim erhalten, s. GroupEditDialog._head_cells).
        if isinstance(v, str) and ":" in v:
            continue
        try:
            c, r = key.split(",")
            items.append((int(r), int(c), int(v)))
        except Exception:
            continue
    items.sort()
    return [fid for _, _, fid in items]


class GroupEditDialog(QDialog):
    """Mitglieder, Name und Reihenfolge einer Gruppe bearbeiten."""

    def __init__(self, group_name: str, positions_json: str, cols: int, rows: int,
                 patched_labels: dict[int, str], parent=None):
        """patched_labels: {fid: label} aller aktuell gepatchten Fixtures."""
        super().__init__(parent)
        self.setWindowTitle(f"Gruppe bearbeiten: {group_name}")
        self.setModal(True)
        self.setStyleSheet("QDialog { background:#161b22; } "
                           "QLabel { color:#8b949e; font-size:11px; } "
                           "QLineEdit { background:#0d1117; color:#e6edf3; "
                           "  border:1px solid #30363d; border-radius:4px; padding:6px; }")

        self._labels = dict(patched_labels)
        self._cols = max(1, int(cols))
        self._rows = max(1, int(rows))
        self._order_changed = False
        # Originale Zellen je fid merken (Erhalt des 2D-Layouts ohne Umsortierung).
        # FM-16e: ganze-Fixture-Zellen (fid) von Kopf-Zellen ("fid:head") trennen.
        # Kopf-Zellen editiert dieser Mitglieder-Dialog NICHT — sie bleiben beim
        # Speichern VERBATIM erhalten (frueher warf int("5:0") und loeschte das ganze
        # Raster einer Kopf-Matrix, inkl. der neuen "Matrizen"-Merge-Gruppen).
        self._orig_cells: dict[int, str] = {}    # fid -> cellkey (nur ganze Fixtures)
        self._head_cells: dict[str, str] = {}     # cellkey -> "fid:head" (unveraendert)
        try:
            for key, v in (json.loads(positions_json or "{}") or {}).items():
                if isinstance(v, str) and ":" in v:
                    self._head_cells[str(key)] = v
                else:
                    try:
                        self._orig_cells[int(v)] = str(key)
                    except (TypeError, ValueError):
                        continue
        except Exception:
            self._orig_cells = {}
            self._head_cells = {}

        members = [fid for fid in group_member_fids(positions_json)
                   if fid in self._labels]

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        root.addWidget(QLabel("Name der Gruppe:"))
        self._name_edit = QLineEdit(group_name)
        self._name_edit.setMinimumHeight(36)
        root.addWidget(self._name_edit)

        cols_row = QHBoxLayout()
        cols_row.setSpacing(10)

        # ── Links: Mitglieder (geordnet) ─────────────────────────────────────
        left = QVBoxLayout()
        left.addWidget(QLabel("In der Gruppe (Reihenfolge = Fan/Chase-Lauf):"))
        self._member_list = QListWidget()
        self._member_list.setStyleSheet(_LIST_STYLE)
        self._member_list.setMinimumSize(240, 280)
        for fid in members:
            self._add_member_item(fid)
        left.addWidget(self._member_list, stretch=1)

        mrow = QHBoxLayout()
        self._btn_up = QPushButton("▲")
        self._btn_down = QPushButton("▼")
        self._btn_remove = QPushButton("Entfernen →")
        for b in (self._btn_up, self._btn_down, self._btn_remove):
            b.setMinimumHeight(36)
            b.setStyleSheet(_BTN_STYLE)
        self._btn_up.setFixedWidth(44)
        self._btn_down.setFixedWidth(44)
        self._btn_up.clicked.connect(lambda: self._move_member(-1))
        self._btn_down.clicked.connect(lambda: self._move_member(+1))
        self._btn_remove.clicked.connect(self._remove_member)
        mrow.addWidget(self._btn_up)
        mrow.addWidget(self._btn_down)
        mrow.addWidget(self._btn_remove, stretch=1)
        left.addLayout(mrow)
        cols_row.addLayout(left, stretch=1)

        # ── Rechts: verfügbare Fixtures ──────────────────────────────────────
        right = QVBoxLayout()
        right.addWidget(QLabel("Verfügbare Fixtures (Doppeltipp = hinzufügen):"))
        self._avail_list = QListWidget()
        self._avail_list.setStyleSheet(_LIST_STYLE)
        self._avail_list.setMinimumSize(240, 280)
        in_group = set(members)
        for fid in sorted(self._labels):
            if fid not in in_group:
                self._add_avail_item(fid)
        self._avail_list.itemDoubleClicked.connect(lambda _i: self._add_member())
        right.addWidget(self._avail_list, stretch=1)

        self._btn_add = QPushButton("← Hinzufügen")
        self._btn_add.setMinimumHeight(36)
        self._btn_add.setStyleSheet(_BTN_STYLE)
        self._btn_add.clicked.connect(self._add_member)
        right.addWidget(self._btn_add)
        cols_row.addLayout(right, stretch=1)

        root.addLayout(cols_row, stretch=1)

        self._hint = QLabel("")
        self._hint.setStyleSheet("color:#d29922; font-size:10px;")
        self._hint.setWordWrap(True)
        root.addWidget(self._hint)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Save).setText("Speichern")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        for b in (bb.button(QDialogButtonBox.StandardButton.Save),
                  bb.button(QDialogButtonBox.StandardButton.Cancel)):
            b.setMinimumHeight(40)
            b.setStyleSheet(_BTN_STYLE)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

        self.resize(620, 520)

    # ── Listen-Helfer ─────────────────────────────────────────────────────────

    def _item_text(self, fid: int) -> str:
        return f"[{fid:03d}] {self._labels.get(fid, f'Fixture {fid}')}"

    def _add_member_item(self, fid: int):
        it = QListWidgetItem(self._item_text(fid))
        it.setData(Qt.ItemDataRole.UserRole, fid)
        self._member_list.addItem(it)

    def _add_avail_item(self, fid: int):
        it = QListWidgetItem(self._item_text(fid))
        it.setData(Qt.ItemDataRole.UserRole, fid)
        self._avail_list.addItem(it)

    # ── Aktionen ──────────────────────────────────────────────────────────────

    def _move_member(self, step: int):
        row = self._member_list.currentRow()
        new = row + step
        if row < 0 or not (0 <= new < self._member_list.count()):
            return
        it = self._member_list.takeItem(row)
        self._member_list.insertItem(new, it)
        self._member_list.setCurrentRow(new)
        self._order_changed = True
        self._hint.setText("Hinweis: Umsortieren schreibt das Gruppen-Raster "
                           "zeilenweise neu (ein eigenes 2D-Layout der Gruppe "
                           "geht dabei verloren).")

    def _remove_member(self):
        row = self._member_list.currentRow()
        if row < 0:
            return
        it = self._member_list.takeItem(row)
        fid = it.data(Qt.ItemDataRole.UserRole)
        # zurück in die verfügbare Liste (sortiert einfügen)
        self._add_avail_item(int(fid))
        self._avail_list.sortItems()

    def _add_member(self):
        row = self._avail_list.currentRow()
        if row < 0:
            return
        it = self._avail_list.takeItem(row)
        fid = it.data(Qt.ItemDataRole.UserRole)
        self._add_member_item(int(fid))
        self._member_list.setCurrentRow(self._member_list.count() - 1)

    # ── Ergebnis ──────────────────────────────────────────────────────────────

    def member_fids(self) -> list[int]:
        return [int(self._member_list.item(i).data(Qt.ItemDataRole.UserRole))
                for i in range(self._member_list.count())]

    def result_name(self) -> str:
        return self._name_edit.text().strip()

    def result_positions(self) -> tuple[str, int, int]:
        """(positions_json, cols, rows) für die gespeicherte Gruppe.

        Ohne Umsortierung behalten bestehende Mitglieder ihre Zellen; neue
        kommen auf die ersten freien Zellen. Mit Umsortierung wird zeilenweise
        neu geschrieben. Wächst die Mitgliederzahl über das Raster hinaus,
        werden Zeilen ergänzt."""
        fids = self.member_fids()
        cols, rows = self._cols, self._rows
        # FM-16e: Kopf-Zellen ("fid:head") IMMER verbatim erhalten — sie belegen ihre
        # Zellen; ganze Mitglieder landen NUR in den restlichen freien Zellen.
        positions: dict[str, object] = dict(self._head_cells)
        head_used: set[str] = set(self._head_cells.keys())
        while cols * rows < len(fids) + len(head_used):
            rows += 1

        if self._order_changed:
            free = (f"{c},{r}" for r in range(rows) for c in range(cols)
                    if f"{c},{r}" not in head_used)
            for fid, cell in zip(fids, free):
                positions[cell] = fid
        else:
            used: set[str] = set(head_used)
            pending: list[int] = []
            for fid in fids:
                cell = self._orig_cells.get(fid)
                if cell is not None and cell not in used:
                    try:
                        c, r = (int(v) for v in cell.split(","))
                    except Exception:
                        pending.append(fid)
                        continue
                    if 0 <= c < cols and 0 <= r < rows:
                        positions[cell] = fid
                        used.add(cell)
                        continue
                pending.append(fid)
            # neue/verschobene Mitglieder: erste freie Zellen (zeilenweise)
            free = (f"{c},{r}" for r in range(rows) for c in range(cols))
            for fid in pending:
                for cell in free:
                    if cell not in used:
                        positions[cell] = fid
                        used.add(cell)
                        break
        return json.dumps(positions), cols, rows
