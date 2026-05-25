"""Output-Konfigurations-Dialog (Enttec / Art-Net / sACN / Universe-Manager)."""
from __future__ import annotations
import json
import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QGroupBox, QFormLayout, QCheckBox, QLineEdit,
    QSpinBox, QTabWidget, QWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox,
)
from PySide6.QtCore import Qt
import serial.tools.list_ports
from src.core.app_state import get_state
from src.core.dmx.enttec_pro import EnttecPro, ENTTEC_VID, ENTTEC_PID

_UNIV_CONFIG_PATH = os.path.join("data", "universes.json")


def _load_universe_config() -> list[dict]:
    if not os.path.exists(_UNIV_CONFIG_PATH):
        return []
    try:
        with open(_UNIV_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_universe_config(rows: list[dict]) -> None:
    try:
        os.makedirs(os.path.dirname(_UNIV_CONFIG_PATH), exist_ok=True)
        with open(_UNIV_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[output_config] save universes error: {e}")


class OutputConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ausgabe konfigurieren")
        self.setMinimumWidth(500)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        # ── Enttec Tab ────────────────────────────────────────────────────────
        enttec_tab = QWidget()
        ef = QFormLayout(enttec_tab)

        self._combo_port = QComboBox()
        self._refresh_ports()
        ef.addRow("COM-Port:", self._combo_port)

        refresh_btn = QPushButton("Ports aktualisieren")
        refresh_btn.clicked.connect(self._refresh_ports)
        ef.addRow("", refresh_btn)

        self._spin_enttec_univ = QSpinBox()
        self._spin_enttec_univ.setRange(1, 16)
        ef.addRow("Universe:", self._spin_enttec_univ)

        connect_btn = QPushButton("Verbinden")
        connect_btn.clicked.connect(self._connect_enttec)
        self._lbl_enttec_status = QLabel("Nicht verbunden")
        ef.addRow("", connect_btn)
        ef.addRow("Status:", self._lbl_enttec_status)

        tabs.addTab(enttec_tab, "Enttec Pro USB")

        # ── Art-Net Tab ───────────────────────────────────────────────────────
        artnet_tab = QWidget()
        af = QFormLayout(artnet_tab)

        self._check_artnet = QCheckBox("Art-Net aktivieren")
        af.addRow(self._check_artnet)

        self._edit_artnet_ip = QLineEdit("2.255.255.255")
        af.addRow("Ziel-IP / Broadcast:", self._edit_artnet_ip)

        self._spin_artnet_start_univ = QSpinBox()
        self._spin_artnet_start_univ.setRange(0, 32767)
        af.addRow("Art-Net Startuniversum:", self._spin_artnet_start_univ)

        apply_artnet_btn = QPushButton("Übernehmen")
        apply_artnet_btn.clicked.connect(self._apply_artnet)
        self._lbl_artnet_status = QLabel("Inaktiv")
        af.addRow("", apply_artnet_btn)
        af.addRow("Status:", self._lbl_artnet_status)

        tabs.addTab(artnet_tab, "Art-Net")

        # ── sACN Tab ──────────────────────────────────────────────────────────
        sacn_tab = QWidget()
        sf = QFormLayout(sacn_tab)

        self._check_sacn = QCheckBox("sACN (E1.31) aktivieren")
        sf.addRow(self._check_sacn)

        self._check_sacn_multicast = QCheckBox("Multicast (239.255.0.x)")
        self._check_sacn_multicast.setChecked(True)
        sf.addRow(self._check_sacn_multicast)

        self._edit_sacn_ip = QLineEdit("")
        self._edit_sacn_ip.setPlaceholderText("Leer = Multicast")
        sf.addRow("Unicast Ziel-IP:", self._edit_sacn_ip)

        apply_sacn_btn = QPushButton("Übernehmen")
        apply_sacn_btn.clicked.connect(self._apply_sacn)
        self._lbl_sacn_status = QLabel("Inaktiv")
        sf.addRow("", apply_sacn_btn)
        sf.addRow("Status:", self._lbl_sacn_status)

        tabs.addTab(sacn_tab, "sACN (E1.31)")

        # ── DMX Input Tab ──────────────────────────────────────────────────────
        input_tab = QWidget()
        if_l = QVBoxLayout(input_tab)
        if_l.addWidget(QLabel(
            "Empfaengt DMX-Daten via Art-Net (Port 6454) oder sACN (Port 5568)\n"
            "und mergt sie in lokale Universen (HTP / LTP / REPLACE)."
        ))

        # Art-Net Input
        ain_box = QGroupBox("Art-Net Input")
        ain_l = QFormLayout(ain_box)
        self._check_artnet_in = QCheckBox("Art-Net Input aktivieren")
        ain_l.addRow(self._check_artnet_in)

        self._spin_artnet_in_univ = QSpinBox()
        self._spin_artnet_in_univ.setRange(1, 32767)
        self._spin_artnet_in_univ.setValue(1)
        ain_l.addRow("Eingehendes Universe:", self._spin_artnet_in_univ)

        self._spin_artnet_in_out = QSpinBox()
        self._spin_artnet_in_out.setRange(1, 32)
        self._spin_artnet_in_out.setValue(1)
        ain_l.addRow("Merge in Universe:", self._spin_artnet_in_out)

        self._combo_artnet_in_mode = QComboBox()
        self._combo_artnet_in_mode.addItems(["HTP", "LTP", "REPLACE"])
        ain_l.addRow("Merge-Modus:", self._combo_artnet_in_mode)

        ain_btn = QPushButton("Uebernehmen")
        ain_btn.clicked.connect(self._apply_artnet_input)
        self._lbl_artnet_in_status = QLabel("Inaktiv")
        ain_l.addRow("", ain_btn)
        ain_l.addRow("Status:", self._lbl_artnet_in_status)
        if_l.addWidget(ain_box)

        # sACN Input
        sin_box = QGroupBox("sACN Input")
        sin_l = QFormLayout(sin_box)
        self._check_sacn_in = QCheckBox("sACN Input aktivieren")
        sin_l.addRow(self._check_sacn_in)

        self._spin_sacn_in_univ = QSpinBox()
        self._spin_sacn_in_univ.setRange(1, 63999)
        self._spin_sacn_in_univ.setValue(1)
        sin_l.addRow("Eingehendes Universe:", self._spin_sacn_in_univ)

        self._spin_sacn_in_out = QSpinBox()
        self._spin_sacn_in_out.setRange(1, 32)
        self._spin_sacn_in_out.setValue(1)
        sin_l.addRow("Merge in Universe:", self._spin_sacn_in_out)

        self._combo_sacn_in_mode = QComboBox()
        self._combo_sacn_in_mode.addItems(["HTP", "LTP", "REPLACE"])
        sin_l.addRow("Merge-Modus:", self._combo_sacn_in_mode)

        sin_btn = QPushButton("Uebernehmen")
        sin_btn.clicked.connect(self._apply_sacn_input)
        self._lbl_sacn_in_status = QLabel("Inaktiv")
        sin_l.addRow("", sin_btn)
        sin_l.addRow("Status:", self._lbl_sacn_in_status)
        if_l.addWidget(sin_box)

        if_l.addStretch(1)
        tabs.addTab(input_tab, "DMX Input")

        # ── Universe Manager Tab ───────────────────────────────────────────────
        univ_tab = QWidget()
        uf = QVBoxLayout(univ_tab)
        uf.addWidget(QLabel(
            "Universen verwalten - bis zu 32 Universen.\n"
            "Pro Universe: Name, Output-Typ (Disabled / Enttec / sACN / ArtNet), Patch-Adresse."
        ))
        self._univ_table = QTableWidget(0, 4)
        self._univ_table.setHorizontalHeaderLabels(
            ["#", "Name", "Output", "Patch (Port/IP)"]
        )
        self._univ_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._univ_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._univ_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._univ_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._univ_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        uf.addWidget(self._univ_table, 1)

        uf_btns = QHBoxLayout()
        b_add = QPushButton("+ Universe hinzufuegen")
        b_add.clicked.connect(self._univ_add)
        b_del = QPushButton("Loeschen")
        b_del.setObjectName("btn_danger")
        b_del.clicked.connect(self._univ_delete)
        b_save = QPushButton("Speichern")
        b_save.clicked.connect(self._univ_save)
        uf_btns.addWidget(b_add); uf_btns.addWidget(b_del); uf_btns.addWidget(b_save)
        uf_btns.addStretch(1)
        uf.addLayout(uf_btns)
        tabs.addTab(univ_tab, "Universen")
        self._univ_load_table()

        layout.addWidget(tabs)

        btn_close = QPushButton("Schließen")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def _refresh_ports(self):
        self._combo_port.clear()
        ports = list(serial.tools.list_ports.comports())
        enttec_found = False
        for p in ports:
            label = f"{p.device}"
            if p.description:
                label += f"  —  {p.description}"
            if p.vid == ENTTEC_VID and p.pid == ENTTEC_PID:
                label += "  [Enttec Pro]"
                enttec_found = True
            self._combo_port.addItem(label, p.device)
        if not ports:
            self._combo_port.addItem("Kein Port gefunden", "")

    def _connect_enttec(self):
        port = self._combo_port.currentData()
        if not port:
            self._lbl_enttec_status.setText("Kein Port gewaehlt")
            return
        univ = self._spin_enttec_univ.value()
        state = get_state()
        om = state.output_manager

        # Sicherstellen dass das Universe existiert
        if univ not in state.universes:
            state.universes[univ] = om.add_universe(univ)

        # Wenn auf diesem Universe bereits eine Enttec offen ist -> schliessen
        existing = om._enttec_outputs.get(univ)
        if existing is not None:
            try:
                existing.close()
            except Exception:
                pass
            om._enttec_outputs.pop(univ, None)

        # Pruefen ob der gleiche Port auf einem anderen Universe offen ist
        for u, dev in list(om._enttec_outputs.items()):
            try:
                if getattr(dev, "port", None) == port or getattr(dev, "_port_name", None) == port:
                    dev.close()
                    om._enttec_outputs.pop(u, None)
            except Exception:
                pass

        try:
            om.add_enttec(univ, port)
            self._lbl_enttec_status.setText(f"Verbunden: {port} -> Universe {univ}")
        except Exception as e:
            self._lbl_enttec_status.setText(f"Fehler: {e}")

    def _apply_artnet(self):
        if not self._check_artnet.isChecked():
            self._lbl_artnet_status.setText("Deaktiviert")
            return
        ip = self._edit_artnet_ip.text().strip() or "2.255.255.255"
        state = get_state()
        for univ_num in state.universes:
            state.output_manager.add_artnet(univ_num, ip)
        self._lbl_artnet_status.setText(f"Aktiv → {ip}")

    # ── Universe Manager ─────────────────────────────────────────────────────

    def _univ_load_table(self):
        rows = _load_universe_config()
        if not rows:
            # Provide an initial example row
            rows = [{"num": 1, "name": "Main", "output": "Disabled", "patch": ""}]
        self._univ_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            num_item = QTableWidgetItem(str(r.get("num", i + 1)))
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._univ_table.setItem(i, 0, num_item)
            self._univ_table.setItem(i, 1, QTableWidgetItem(r.get("name", "Universe")))
            combo = QComboBox()
            for opt in ("Disabled", "Enttec", "sACN", "ArtNet"):
                combo.addItem(opt)
            combo.setCurrentText(r.get("output", "Disabled"))
            self._univ_table.setCellWidget(i, 2, combo)
            self._univ_table.setItem(i, 3, QTableWidgetItem(r.get("patch", "")))

    def _univ_add(self):
        row = self._univ_table.rowCount()
        if row >= 32:
            QMessageBox.information(self, "Limit", "Maximal 32 Universen.")
            return
        self._univ_table.insertRow(row)
        self._univ_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self._univ_table.setItem(row, 1, QTableWidgetItem(f"Universe {row + 1}"))
        combo = QComboBox()
        for opt in ("Disabled", "Enttec", "sACN", "ArtNet"):
            combo.addItem(opt)
        self._univ_table.setCellWidget(row, 2, combo)
        self._univ_table.setItem(row, 3, QTableWidgetItem(""))

    def _univ_delete(self):
        rows = sorted({i.row() for i in self._univ_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self._univ_table.removeRow(r)

    def _univ_save(self):
        rows = []
        for r in range(self._univ_table.rowCount()):
            num_item = self._univ_table.item(r, 0)
            name_item = self._univ_table.item(r, 1)
            patch_item = self._univ_table.item(r, 3)
            combo = self._univ_table.cellWidget(r, 2)
            try:
                num = int(num_item.text()) if num_item else r + 1
            except ValueError:
                num = r + 1
            rows.append({
                "num": num,
                "name": name_item.text() if name_item else f"Universe {num}",
                "output": combo.currentText() if combo else "Disabled",
                "patch": patch_item.text() if patch_item else "",
            })
        _save_universe_config(rows)
        QMessageBox.information(self, "Gespeichert", _UNIV_CONFIG_PATH)

    def _apply_sacn(self):
        if not self._check_sacn.isChecked():
            self._lbl_sacn_status.setText("Deaktiviert")
            return
        ip_text = self._edit_sacn_ip.text().strip()
        target_ip = None if (self._check_sacn_multicast.isChecked() or not ip_text) else ip_text
        state = get_state()
        try:
            for univ_num in state.universes:
                state.output_manager.add_sacn(univ_num, target_ip)
            mode = f"Multicast (239.255.0.x)" if target_ip is None else f"Unicast → {target_ip}"
            self._lbl_sacn_status.setText(f"Aktiv · {mode}")
        except Exception as e:
            self._lbl_sacn_status.setText(f"Fehler: {e}")

    # ── DMX Input ────────────────────────────────────────────────────────────

    def _apply_artnet_input(self):
        try:
            from src.core.dmx.artnet_input import get_artnet_receiver
            rx = get_artnet_receiver()
            if not self._check_artnet_in.isChecked():
                rx.stop()
                self._lbl_artnet_in_status.setText("Gestoppt")
                return
            if not rx.is_running():
                rx.start()
            in_u = self._spin_artnet_in_univ.value()
            out_u = self._spin_artnet_in_out.value()
            mode = self._combo_artnet_in_mode.currentText()
            rx.set_merge(in_u, out_u, mode)
            self._lbl_artnet_in_status.setText(
                f"Aktiv: U{in_u} -> U{out_u} ({mode})"
            )
        except Exception as e:
            self._lbl_artnet_in_status.setText(f"Fehler: {e}")

    def _apply_sacn_input(self):
        try:
            from src.core.dmx.sacn_input import get_sacn_receiver
            rx = get_sacn_receiver()
            if not self._check_sacn_in.isChecked():
                rx.stop()
                self._lbl_sacn_in_status.setText("Gestoppt")
                return
            in_u = self._spin_sacn_in_univ.value()
            out_u = self._spin_sacn_in_out.value()
            mode = self._combo_sacn_in_mode.currentText()
            if not rx.is_running():
                rx.start(universes=[in_u])
            else:
                rx.join_universe(in_u)
            rx.set_merge(in_u, out_u, mode)
            self._lbl_sacn_in_status.setText(
                f"Aktiv: U{in_u} -> U{out_u} ({mode})"
            )
        except Exception as e:
            self._lbl_sacn_in_status.setText(f"Fehler: {e}")
