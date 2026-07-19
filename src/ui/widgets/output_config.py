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

# A3D-33: gueltiger interner Universe-Bereich — identisch zu den 1..32-Spinboxen der
# Tabs und der 32-Zeilen-Grenze in _univ_add. Die freie '#'-Spalte des Universe-Tables
# hatte KEINEN Range-Guard -> -1/70000 landeten in universes.json und liessen
# apply_output_config Art-Net werfen bzw. sACN still auf ein falsches Universum wrappen.
_UNIVERSE_MIN, _UNIVERSE_MAX = 1, 32


def _coerce_universe_num(text, fallback: int) -> tuple[int, bool]:
    """Universe-Nummer aus einem freien Tabellenfeld robust in den gueltigen
    Bereich [``_UNIVERSE_MIN``..``_UNIVERSE_MAX``] zwingen.

    Rueckgabe ``(nummer, angepasst?)``:
    - Nicht parsebar (leer/Muell) -> ``(fallback, False)``: unveraendertes Verhalten,
      der Aufrufer setzt still den Zeilen-Default (Zeilenindex+1).
    - Parsebar aber ausserhalb -> auf die naechste Grenze geklemmt, ``angepasst=True``.
    - Innerhalb -> ``(nummer, False)``.
    """
    try:
        n = int(str(text).strip())
    except (ValueError, TypeError, AttributeError):
        return fallback, False
    clamped = max(_UNIVERSE_MIN, min(_UNIVERSE_MAX, n))
    return clamped, clamped != n


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


_UNSET = object()   # A3D-15: "Argument nicht uebergeben" vs. explizit None unterscheiden.


def _persist_output(num: int, output: str, patch: str, out_universe=_UNSET) -> None:
    """Schreibt/aktualisiert eine Zeile in universes.json, damit eine zur
    Laufzeit hergestellte Ausgabe-Verbindung beim naechsten Start automatisch
    wieder eingerichtet wird (apply_output_config). Ohne das war jede Verbindung
    nach einem Neustart weg -> 'es kommt kein Output'.

    A3D-15: ``out_universe`` = externe Art-Net-/sACN-Universe-Nummer.
    - ``_UNSET`` (Default) = das Feld NICHT anfassen. Wichtig: Enttec-/sACN-
      „Übernehmen" rufen ohne Wert und duerfen eine per Universe-Tabelle (OUT-03)
      gesetzte externe Universe NICHT loeschen (Review-Fund: sonst stiller
      Datenverlust + falscher Output ueber Neustarts).
    - ``None`` = explizit entfernen (Art-Net-Default univ-1, leer = Default wie die
      Tabellen-Spalte).
    - Wert = setzen. So ueberlebt die im Art-Net-Tab gewaehlte externe Universe
      einen Neustart (apply_output_config liest sie)."""
    rows = _load_universe_config()
    found = False
    for r in rows:
        if int(r.get("num", -1)) == int(num):
            r["output"] = output
            r["patch"] = patch
            if out_universe is None:
                r.pop("out_universe", None)
            elif out_universe is not _UNSET:
                r["out_universe"] = int(out_universe)
            found = True
            break
    if not found:
        entry = {"num": int(num), "name": f"Universe {num}",
                 "output": output, "patch": patch}
        if out_universe is not None and out_universe is not _UNSET:
            entry["out_universe"] = int(out_universe)
        rows.append(entry)
    _save_universe_config(rows)


class OutputConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ausgabe konfigurieren")
        self.setMinimumWidth(500)
        # MU-02 (Review): das je Tab TATSAECHLICH belegte Universum merken, damit
        # das Abwaehlen genau dieses raeumt und nicht den aktuellen Spin-Wert (der
        # inzwischen auf ein fremdes Universum zeigen kann).
        self._artnet_active_univ: int | None = None
        self._sacn_active_univ: int | None = None
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
        self._spin_enttec_univ.setRange(1, 32)
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

        # OUT-04: Ziel-Universum, auf das „Übernehmen" wirkt (analog Enttec) — nicht
        # mehr pauschal ALLE Universen. (Das separate „Startuniversum"-Feld unten ist
        # die EXTERNE Universe-Nummer und gehört zu OUT-03.)
        self._spin_artnet_univ = QSpinBox()
        self._spin_artnet_univ.setRange(1, 32)
        af.addRow("Universe:", self._spin_artnet_univ)

        self._edit_artnet_ip = QLineEdit("255.255.255.255")
        af.addRow("Ziel-IP / Broadcast:", self._edit_artnet_ip)

        self._spin_artnet_start_univ = QSpinBox()
        self._spin_artnet_start_univ.setRange(0, 32767)
        self._spin_artnet_start_univ.setToolTip(
            'Externe Art-Net-Universe-Nummer für "Übernehmen". Default = '
            'internes Universum − 1 (abwärtskompatibel).')
        af.addRow("Art-Net Startuniversum:", self._spin_artnet_start_univ)
        # A3D-15: die externe Universe folgt standardmaessig dem internen Universum
        # (univ-1 = Alt-Verhalten) bzw. einer bereits gespeicherten Wahl — so setzt
        # ein unbeabsichtigtes „Übernehmen" nicht still auf Universe 0/eine falsche
        # Nummer und eine gespeicherte externe Universe wird beim Neuwahl gezeigt.
        self._spin_artnet_univ.valueChanged.connect(self._sync_artnet_start_univ_default)
        self._sync_artnet_start_univ_default()

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

        # OUT-04: Ziel-Universum, auf das „Übernehmen" wirkt (nicht mehr alle).
        self._spin_sacn_univ = QSpinBox()
        self._spin_sacn_univ.setRange(1, 32)
        sf.addRow("Universe:", self._spin_sacn_univ)

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
            "Empfängt DMX-Daten via Art-Net (Port 6454) oder sACN (Port 5568)\n"
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

        ain_btn = QPushButton("Übernehmen")
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

        sin_btn = QPushButton("Übernehmen")
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
            "Pro Universe: Name, Output-Typ (Disabled / Enttec / sACN / ArtNet), "
            "Patch-Adresse, optionale externe Universe-Nummer."
        ))
        self._univ_table = QTableWidget(0, 5)
        self._univ_table.setHorizontalHeaderLabels(
            ["#", "Name", "Output", "Patch (Port/IP)", "Ext-Universe"]
        )
        # OUT-03: "Ext-Universe" = optionale externe Art-Net/sACN-Universe-Nummer.
        # Leer = Default (Art-Net num-1, sACN num).
        self._univ_table.horizontalHeaderItem(4).setToolTip(
            "Optionale externe Art-Net/sACN-Universe-Nummer. "
            "Leer = Standard (Art-Net #-1, sACN #)."
        )
        self._univ_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._univ_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._univ_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._univ_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._univ_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._univ_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        uf.addWidget(self._univ_table, 1)

        uf_btns = QHBoxLayout()
        b_add = QPushButton("+ Universe hinzufügen")
        b_add.clicked.connect(self._univ_add)
        b_del = QPushButton("Löschen")
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
            self._lbl_enttec_status.setText("Kein Port gewählt")
            return
        univ = self._spin_enttec_univ.value()
        state = get_state()
        om = state.output_manager

        # Sicherstellen dass das Universe existiert
        if univ not in state.universes:
            state.universes[univ] = om.add_universe(univ)

        # add_enttec() ist thread-sicher: es schliesst eine evtl. offene
        # Verbindung auf demselben Port/Universe selbst (unter dem Output-Lock),
        # bevor es die neue oeffnet. KEIN direkter Zugriff auf om._enttec_outputs
        # aus dem UI-Thread mehr -> verhindert den Deadlock mit dem Output-Thread.
        try:
            # MU-01: erst ALLE Alt-Adapter dieses Universums entfernen/schliessen
            # (auch ArtNet/sACN), sonst bleibt bei einem Cross-Typ-Wechsel der alte
            # Adapter aktiv -> Doppel-Output/Leak. Analog apply_output_config (OUT-05).
            om.remove_output(univ)
            om.add_enttec(univ, port)
            _persist_output(univ, "Enttec", port)
            self._lbl_enttec_status.setText(f"Verbunden: {port} -> Universe {univ} (gespeichert)")
        except Exception as e:
            self._lbl_enttec_status.setText(f"Fehler: {e}")

    def _sync_artnet_start_univ_default(self):
        """A3D-15: die Startuniversum-Spinbox auf einen sinnvollen Wert fuer das
        aktuell gewaehlte interne Universum stellen — eine bereits gespeicherte
        externe Art-Net-Universe, sonst den abwaertskompatiblen Default (univ-1).
        Verhindert, dass ein „Übernehmen" ohne bewusste Eingabe auf Universe 0
        (Spinbox-Minimum) setzt, und zeigt eine gespeicherte Wahl nach Reload/
        Universumswechsel wieder an."""
        univ = self._spin_artnet_univ.value()
        persisted = None
        try:
            for r in _load_universe_config():
                if int(r.get("num", -1)) == univ and (r.get("output") or "") == "ArtNet":
                    v = r.get("out_universe")
                    if v is not None and str(v).strip() != "":
                        persisted = int(v)
                    break
        except (ValueError, TypeError):
            persisted = None
        target = persisted if persisted is not None else max(0, univ - 1)
        self._spin_artnet_start_univ.blockSignals(True)
        self._spin_artnet_start_univ.setValue(target)
        self._spin_artnet_start_univ.blockSignals(False)

    def _apply_artnet(self):
        univ = self._spin_artnet_univ.value()
        state = get_state()
        if not self._check_artnet.isChecked():
            # MU-02 (+Review): Abwaehlen raeumt das beim Apply belegte Universum
            # (nicht den aktuellen Spin-Wert — der koennte inzwischen auf ein fremdes
            # Universum zeigen und dessen Adapter faelschlich killen).
            if self._artnet_active_univ is not None:
                state.output_manager.remove_output(self._artnet_active_univ)
                self._artnet_active_univ = None
            self._lbl_artnet_status.setText("Inaktiv")
            return
        ip = self._edit_artnet_ip.text().strip() or "255.255.255.255"
        # OUT-04: NUR das gewählte Universum belegen. Die frühere Schleife über ALLE
        # Universen überschrieb jede andere Adapter-Zuweisung — live UND in
        # universes.json (`_persist_output` je Universum) → Mixed-Setups zerstört.
        # `_persist_output` aktualisiert jetzt nur diese eine Zeile, andere bleiben.
        if univ not in state.universes:
            state.universes[univ] = state.output_manager.add_universe(univ)
        # MU-01: erst ALLE Alt-Adapter dieses Universums entfernen/schliessen, sonst
        # bleibt bei einem Cross-Typ-Wechsel (z. B. Enttec->ArtNet) der alte Adapter
        # aktiv -> Doppel-Output/Leak. Analog apply_output_config (OUT-05).
        state.output_manager.remove_output(univ)
        # A3D-15: externe Art-Net-Universe aus der (bisher toten) Startuniversum-
        # Spinbox durchreichen. Weicht sie NICHT vom Default (univ-1) ab -> None,
        # damit der Send-Pfad den abwaertskompatiblen Default (univ_num-1) nutzt und
        # universes.json sauber bleibt (Konvention "leer = Default", wie die Tabelle).
        start = self._spin_artnet_start_univ.value()
        out_u = start if start != univ - 1 else None
        state.output_manager.add_artnet(univ, ip, out_universe=out_u)
        self._artnet_active_univ = univ   # MU-02: fuer korrektes Abwaehlen merken
        _persist_output(univ, "ArtNet", ip, out_universe=out_u)
        # A3D-15 (Review-Fund #2): die Universe-Tabelle wurde nur beim Setup gefuellt
        # und kennt die eben persistierte externe Universe nicht -> ein spaeteres
        # „Speichern" im Universen-Tab wuerde sie aus der (stalen, leeren) Ext-Zelle
        # ueberschreiben. Tabelle neu laden, damit die Ext-Zelle den aktuellen Stand
        # zeigt und Tab und Datei konsistent bleiben.
        try:
            self._univ_load_table()
        except Exception:
            pass
        _ext_txt = f" → Art-Net-Universe {start}" if out_u is not None else ""
        self._lbl_artnet_status.setText(
            f"Aktiv → {ip} · Universe {univ}{_ext_txt} (gespeichert)")

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
            # OUT-03: externe Universe-Nummer (leer = Default). None/fehlt -> "".
            ext = r.get("out_universe")
            ext_item = QTableWidgetItem("" if ext is None else str(ext))
            ext_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._univ_table.setItem(i, 4, ext_item)

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
        self._univ_table.setItem(row, 4, QTableWidgetItem(""))

    def _univ_delete(self):
        rows = sorted({i.row() for i in self._univ_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self._univ_table.removeRow(r)

    def _univ_save(self):
        rows = []
        adjusted: list[tuple[int, int]] = []   # A3D-33: (Zeilennr, geklemmte Nummer)
        for r in range(self._univ_table.rowCount()):
            num_item = self._univ_table.item(r, 0)
            name_item = self._univ_table.item(r, 1)
            patch_item = self._univ_table.item(r, 3)
            ext_item = self._univ_table.item(r, 4)
            combo = self._univ_table.cellWidget(r, 2)
            # A3D-33: die freie '#'-Spalte auf [1..32] klemmen, BEVOR sie persistiert
            # und via apply_output_config als Universe-Key/Adapter angewandt wird
            # (sonst Art-Net-Wurf bzw. stiller sACN-Wrap auf ein falsches Universum).
            num, was_adjusted = _coerce_universe_num(
                num_item.text() if num_item else "", r + 1)
            if was_adjusted:
                adjusted.append((r + 1, num))
                if num_item is not None:
                    num_item.setText(str(num))   # UI spiegelt den gespeicherten Wert
            entry = {
                "num": num,
                "name": name_item.text() if name_item else f"Universe {num}",
                "output": combo.currentText() if combo else "Disabled",
                "patch": patch_item.text() if patch_item else "",
            }
            # OUT-03: externe Universe-Nummer nur speichern, wenn gesetzt & gueltig
            # (leer/ungueltig -> Feld weglassen = abwaertskompatibler Default).
            ext_text = ext_item.text().strip() if ext_item else ""
            if ext_text:
                try:
                    entry["out_universe"] = int(ext_text)
                except ValueError:
                    pass
            rows.append(entry)
        if adjusted:
            _lst = ", ".join(f"Zeile {r}: → {n}" for r, n in adjusted)
            QMessageBox.warning(
                self, "Universe-Nummer angepasst",
                f"Universe-Nummern müssen zwischen {_UNIVERSE_MIN} und "
                f"{_UNIVERSE_MAX} liegen. Angepasst: {_lst}.")
        _save_universe_config(rows)
        # Sofort anwenden, damit Änderungen ohne Neustart greifen.
        try:
            get_state().apply_output_config()
        except Exception as e:
            print(f"[output_config] apply after save error: {e}")
        QMessageBox.information(self, "Gespeichert", _UNIV_CONFIG_PATH)

    def _apply_sacn(self):
        univ = self._spin_sacn_univ.value()
        state = get_state()
        if not self._check_sacn.isChecked():
            # MU-02 (+Review): das beim Apply belegte Universum raeumen, nicht den
            # aktuellen Spin-Wert (koennte auf ein fremdes Universum zeigen).
            if self._sacn_active_univ is not None:
                state.output_manager.remove_output(self._sacn_active_univ)
                self._sacn_active_univ = None
            self._lbl_sacn_status.setText("Inaktiv")
            return
        ip_text = self._edit_sacn_ip.text().strip()
        target_ip = None if (self._check_sacn_multicast.isChecked() or not ip_text) else ip_text
        try:
            # OUT-04: NUR das gewählte Universum belegen (nicht mehr alle über eine
            # Schleife überschreiben); andere universes.json-Zeilen bleiben erhalten.
            if univ not in state.universes:
                state.universes[univ] = state.output_manager.add_universe(univ)
            # MU-01: erst ALLE Alt-Adapter dieses Universums entfernen/schliessen, sonst
            # bleibt bei einem Cross-Typ-Wechsel der alte Adapter aktiv -> Doppel-Output/
            # Leak. Analog apply_output_config (OUT-05).
            state.output_manager.remove_output(univ)
            state.output_manager.add_sacn(univ, target_ip)
            self._sacn_active_univ = univ   # MU-02: fuer korrektes Abwaehlen merken
            _persist_output(univ, "sACN", target_ip or "")
            mode = "Multicast (239.255.0.x)" if target_ip is None else f"Unicast → {target_ip}"
            self._lbl_sacn_status.setText(f"Aktiv · {mode} · Universe {univ} (gespeichert)")
        except Exception as e:
            self._lbl_sacn_status.setText(f"Fehler: {e}")

    # ── DMX Input ────────────────────────────────────────────────────────────

    @staticmethod
    def _clear_stale_input_merges(rx, new_in_u: int, new_out_u: int):
        """NET-08: Vor dem Einrichten einer neuen Input-Merge-Konfiguration die
        zuvor gesetzte(n) raeumen. Sonst mischt eine auf ein anderes eingehendes
        Universe umgestellte Quelle (z. B. U5 -> U7) ueber die alte Merge-Config +
        den weiterhin aktiven Empfangs-Handler in dasselbe out-Universe weiter.
        Nutzt die vorhandenen ``remove_merge``/``clear_input_merge``-Lifecycles
        (NET-05/NET-07)."""
        merges = getattr(rx, "_merges", None)
        if not merges:
            return
        new_in = int(new_in_u)
        new_out = int(new_out_u)
        stale = [in_u for in_u in list(merges.keys()) if int(in_u) != new_in]
        # Alte out-Universen merken, um eingefrorene Eingangs-Schichten zu leeren.
        stale_outs = {int(merges[in_u][0]) for in_u in stale}
        # NET-08b (Review): Bleibt das EINGANGS-Universum gleich, wechselt aber nur das
        # AUSGANGS-Universum, so bleibt der Merge-Eintrag (in==new_in) erhalten und
        # set_merge remappt ihn — die ALTE out-Schicht würde sonst nie geleert und hinge
        # bis zum NET-05-Timeout (~2,5s) als eingefrorener DMX. Sein altes out mitnehmen.
        for k in list(merges.keys()):
            if int(k) == new_in:
                stale_outs.add(int(merges[k][0]))
                break
        # Nichts zu räumen: keine anderen in_u UND kein abweichendes altes out
        # (Erst-Konfiguration oder unveränderte in/out).
        if not stale and stale_outs <= {new_out}:
            return
        for in_u in stale:
            rx.remove_merge(in_u)
        try:
            st = get_state()
            for out_u in stale_outs:
                if out_u != new_out:
                    st.clear_input_merge(out_u)
        except Exception:
            pass

    def _input_status_text(self, in_u, out_u, mode):
        """NET-07/CDX-02: Baut das Eingangs-Status-Label. Ist out_u NICHT als Output
        gepatcht, verwirft ``_render_frame`` die gemergten Kanaele -> statt "Aktiv"
        "wirkungslos" melden.

        CDX-02b (Review): Maszgeblich ist der AKTUELLE Patch-Stand ``state.universes``
        (genau was ``_render_frame`` zum Verwerfen prueft, app_state.py) — NICHT der
        ``input_unconfigured``-Zaehler. Der Zaehler wird erst vom RX-Thread NACH dem
        ersten empfangenen+gerenderten Frame hochgezaehlt: beim Klick auf "Uebernehmen"
        stuende er sonst noch auf 0 (Warnung verpasst, obwohl gerade der zu warnende
        Fall) bzw. bliebe nach nachtraeglichem Patchen stehen (falsche Warnung). Der
        direkte ``universes``-Check stimmt sofort beim Klick und verschwindet nach dem
        Patchen ohne Frame-Abhaengigkeit."""
        base = f"Aktiv: U{in_u} -> U{out_u} ({mode})"
        try:
            universes = getattr(get_state(), "universes", None)
            if universes is not None and int(out_u) not in universes:
                return (
                    f"Aktiv, aber wirkungslos (U{out_u} nicht als Output "
                    f"gepatcht): U{in_u} -> U{out_u} ({mode})"
                )
        except Exception:
            pass
        return base

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
            self._clear_stale_input_merges(rx, in_u, out_u)
            rx.set_merge(in_u, out_u, mode)
            self._lbl_artnet_in_status.setText(
                self._input_status_text(in_u, out_u, mode)
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
            self._clear_stale_input_merges(rx, in_u, out_u)
            rx.set_merge(in_u, out_u, mode)
            self._lbl_sacn_in_status.setText(
                self._input_status_text(in_u, out_u, mode)
            )
        except Exception as e:
            self._lbl_sacn_in_status.setText(f"Fehler: {e}")
