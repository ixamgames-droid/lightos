"""Channel-Modifier Editor: pro Universe/Channel eine Curve zuweisen."""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QSpinBox, QComboBox, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox, QDialogButtonBox,
)
from PySide6.QtCore import Qt
from src.core.engine.channel_modifier import (
    get_modifier_manager, ChannelModifier, CurveType,
)


class ChannelModifierDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Channel-Modifier verwalten")
        self.setMinimumSize(700, 480)
        self._mgr = get_modifier_manager()
        self._setup_ui()
        self._refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        info = QLabel(
            "Pro DMX-Channel kann eine Curve zugewiesen werden, die beim Output "
            "angewandt wird. Z.B. Gamma 2.2 für LED-Wahrnehmungs-Helligkeit, "
            "Inverse für invertierte Dimmer."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Universe", "Adresse", "Curve", "Name"])
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self._table, 1)

        # Add-Row
        add_row = QHBoxLayout()
        add_row.addWidget(QLabel("Add:"))
        self._spin_univ = QSpinBox()
        self._spin_univ.setRange(1, 32)
        self._spin_univ.setValue(1)
        add_row.addWidget(QLabel("U:"))
        add_row.addWidget(self._spin_univ)
        self._spin_addr = QSpinBox()
        self._spin_addr.setRange(1, 512)
        self._spin_addr.setValue(1)
        add_row.addWidget(QLabel("Adr:"))
        add_row.addWidget(self._spin_addr)
        self._combo_curve = QComboBox()
        for c in CurveType:
            self._combo_curve.addItem(c.value, c)
        add_row.addWidget(QLabel("Curve:"))
        add_row.addWidget(self._combo_curve)
        btn_add = QPushButton("+ Hinzufügen")
        btn_add.clicked.connect(self._add_modifier)
        add_row.addWidget(btn_add)
        btn_del = QPushButton("Löschen")
        btn_del.setStyleSheet("background:#a02020;color:white;")
        btn_del.clicked.connect(self._delete_modifier)
        add_row.addWidget(btn_del)
        layout.addLayout(add_row)

        # Save/Close
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Close
        )
        btns.button(QDialogButtonBox.StandardButton.Save).clicked.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _refresh(self):
        mods = sorted(self._mgr.all(), key=lambda m: (m.universe, m.address))
        self._table.setRowCount(len(mods))
        for r, m in enumerate(mods):
            item_u = QTableWidgetItem(str(m.universe))
            item_u.setFlags(item_u.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(r, 0, item_u)
            item_a = QTableWidgetItem(str(m.address))
            item_a.setFlags(item_a.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(r, 1, item_a)
            combo = QComboBox()
            for c in CurveType:
                combo.addItem(c.value, c)
            combo.setCurrentText(m.curve.value)
            combo.currentIndexChanged.connect(
                lambda _, mod=m, cb=combo: self._change_curve(mod, cb)
            )
            self._table.setCellWidget(r, 2, combo)
            self._table.setItem(r, 3, QTableWidgetItem(m.name))

    def _add_modifier(self):
        u = self._spin_univ.value()
        a = self._spin_addr.value()
        c = self._combo_curve.currentData()
        mod = ChannelModifier(universe=u, address=a, curve=c, name=f"U{u}.{a}")
        self._mgr.add(mod)
        self._refresh()

    def _delete_modifier(self):
        rows = sorted({i.row() for i in self._table.selectedIndexes()}, reverse=True)
        for r in rows:
            try:
                univ = int(self._table.item(r, 0).text())
                addr = int(self._table.item(r, 1).text())
                self._mgr.remove(univ, addr)
            except Exception:
                continue
        self._refresh()

    def _change_curve(self, mod: ChannelModifier, combo: QComboBox):
        mod.curve = combo.currentData()

    def _save(self):
        import os
        os.makedirs("data", exist_ok=True)
        try:
            self._mgr.save("data/channel_modifiers.json")
            QMessageBox.information(self, "Gespeichert", "data/channel_modifiers.json")
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Speichern fehlgeschlagen: {e}")
