"""Tempo-Buses-Tab (BPM-08) — Tempo-Speeds, Grand-Master und „Effekte je Bus".

Eigener Sub-Tab der Sektion BPM (Erkennung | Tempo-Buses | Generator). Die beiden
Gruppen „Tempo-Speeds && Grand-Master" (Phase D2) und „Effekte je Bus —
taktgleich" (Stufe 2) lagen bis BPM-08 im BPM-Manager-Tab und sind unveraendert
hierher gezogen: Attribut-, Methoden- und Beschriftungsnamen sind dieselben
(``_bus_table``, ``_gm_bpm``, ``_gm_arm``, ``_fx_tree``, ``_chk_auto_sync`` …),
damit Werkzeuge, Anleitungen und Tests weiter greifen. Einzige Aenderung: der
zweite Knopf „Aktualisieren" unter der Bus-Tabelle entfaellt (der 150-ms-Poll
und „⟳ Aktualisieren" im Effekte-Panel decken das ab).

Alle Widgets lesen/schreiben NUR ueber ``get_tempo_bus_manager()`` /
``get_function_manager()`` — kein eigener Tempo-Zustand. Die Bus-Tabelle hat
keine Subscribe-API und wird per 150-ms-Poll (nur bei Sichtbarkeit) nachgezogen;
das Effekte-Panel haengt am Sync-Ereignis ``FUNCTION_CHANGED`` — das Abo ist
ueber ``subscribe_widget`` an die Lebenszeit dieses Widgets gebunden.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QGroupBox, QScrollArea, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QDoubleSpinBox,
    QCheckBox, QTreeWidget, QTreeWidgetItem,
)

from src.ui.weak_slots import weak_slot, weak_slot_fwd


class TempoBusView(QWidget):
    """Sub-Tab „Tempo-Buses": Tempo-Speeds && Grand-Master + Effekte je Bus."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

        # Poll-Timer — nur bei Sichtbarkeit aktiv. Frischt die BPM-Spalte der
        # Bus-Tabelle auf (TempoBus hat keine Subscribe-API → live nur per Poll),
        # damit Sound-BPM-Änderungen und ihr folgende Buses in der Übersicht
        # nicht stehenbleiben.
        self._poll = QTimer(self)
        self._poll.setInterval(150)
        self._poll.timeout.connect(self._refresh_bus_bpm_live)

    # ── Aufbau ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        host = QWidget()
        scroll.setWidget(host)
        root = QVBoxLayout(host)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(12)

        root.addWidget(self._build_speeds())
        root.addWidget(self._build_effects_panel())
        root.addStretch(1)
        self._refresh_speeds()
        self._refresh_effects_panel()
        # Live-Refresh, wenn Funktionen erstellt/gestartet/gestoppt werden.
        # Genau EIN Abo je View-Instanz (BPM-08: verschoben, nicht kopiert —
        # BpmManagerView abonniert FUNCTION_CHANGED nicht mehr).
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().subscribe_widget(
                SyncEvent.FUNCTION_CHANGED, self,
                lambda *_a: self._refresh_effects_panel())
        except Exception:
            pass

    # ── Effekte je Bus (taktgleich-Panel) ───────────────────────────────────────
    # Feste Bus-Buckets in Anzeige-Reihenfolge: Haupt-BPM, A-D, Free-Run.
    # Schluessel = kanonische bus_id (Default-Bus ist "default"; die Aliase
    # ""/"Global" loesen dorthin auf — list_effects_by_bus gruppiert nach bus_id).
    _BUS_BUCKETS = [
        ("default", "Haupt-BPM (Global)"),
        ("A", "Bus A"),
        ("B", "Bus B"),
        ("C", "Bus C"),
        ("D", "Bus D"),
        ("", "Frei (kein Bus)"),
    ]
    _TYPE_LABELS = {
        "RGBMatrix": "Matrix", "EFX": "Bewegung/EFX", "Chaser": "Chaser",
        "Sequence": "Sequence", "Scene": "Szene", "Collection": "Sammlung",
        "Audio": "Audio", "Script": "Skript", "Show": "Show",
    }

    def _build_effects_panel(self) -> QGroupBox:
        box = QGroupBox("Effekte je Bus — taktgleich")
        lay = QVBoxLayout(box)
        info = QLabel(
            "Welche Effekte folgen welchem Tempo-Bus. Haken = startet taktgleich auf "
            "dem gemeinsamen Beat-Raster. Per Dropdown den Bus wechseln, „Tempo ×\" als "
            "Verhältnis (½ / 2 …). „Sync jetzt\" rastet alle Effekte eines Bus gemeinsam "
            "auf die Eins.")
        info.setWordWrap(True)
        info.setStyleSheet("color:#999;")
        lay.addWidget(info)

        bar = QHBoxLayout()
        btn_refresh = QPushButton("⟳ Aktualisieren")
        btn_refresh.clicked.connect(self._refresh_effects_panel)
        bar.addWidget(btn_refresh)
        bar.addStretch(1)
        lay.addLayout(bar)

        self._fx_tree = QTreeWidget()
        self._fx_tree.setColumnCount(5)
        self._fx_tree.setHeaderLabels(
            ["Effekt", "Typ", "Bus", "Tempo ×", "Taktgleich"])
        self._fx_tree.setAlternatingRowColors(True)
        self._fx_tree.setMinimumHeight(220)
        hdr = self._fx_tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3, 4):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self._fx_tree)
        self._fx_empty = QLabel("Noch keine zeitbasierten Effekte angelegt.")
        self._fx_empty.setStyleSheet("color:#777; font-style:italic;")
        lay.addWidget(self._fx_empty)
        return box

    def _type_label(self, f) -> str:
        try:
            v = f.function_type.value
        except Exception:
            v = ""
        return self._TYPE_LABELS.get(v, v or "?")

    def _refresh_effects_panel(self):
        tree = getattr(self, "_fx_tree", None)
        if tree is None:
            return
        try:
            from src.core.engine.tempo_bus import get_tempo_bus_manager
            groups = get_tempo_bus_manager().list_effects_by_bus()
        except Exception:
            groups = {}
        tree.clear()
        total = 0
        for bus_id, label in self._BUS_BUCKETS:
            effects = groups.get(bus_id, [])
            top = QTreeWidgetItem(tree)
            top.setText(0, f"{label}  ({len(effects)})")
            f0 = top.font(0); f0.setBold(True); top.setFont(0, f0)
            if bus_id != "":   # Free-Run hat keinen gemeinsamen Sync
                btn = QPushButton("Sync jetzt")
                btn.setToolTip("Alle Effekte dieses Bus gemeinsam auf die Eins re-ankern.")
                btn.clicked.connect(weak_slot(self._on_bus_sync_now, bus_id))
                tree.setItemWidget(top, 4, btn)
            for f in effects:
                total += 1
                self._add_effect_row(top, f, bus_id)
            top.setExpanded(True)
        self._fx_empty.setVisible(total == 0)
        tree.setVisible(total > 0)

    def _add_effect_row(self, top, f, bus_id):
        tree = self._fx_tree
        fid = int(getattr(f, "id", 0))
        row = QTreeWidgetItem(top)
        row.setData(0, Qt.ItemDataRole.UserRole, fid)
        row.setText(0, getattr(f, "name", f"#{fid}"))
        row.setText(1, self._type_label(f))

        combo = QComboBox()
        for bid, lbl in self._BUS_BUCKETS:
            combo.addItem(lbl, bid)
        i = combo.findData(bus_id)
        if i >= 0:
            combo.setCurrentIndex(i)
        combo.setProperty("fid", fid)
        combo.currentIndexChanged.connect(self._on_row_bus_combo_changed)
        tree.setItemWidget(row, 2, combo)

        spin = QDoubleSpinBox()
        spin.setRange(0.0625, 16.0)
        spin.setSingleStep(0.25)
        spin.setDecimals(4)
        spin.setValue(float(getattr(f, "tempo_multiplier", 1.0) or 1.0))
        spin.valueChanged.connect(weak_slot_fwd(self._on_row_mult_changed, fid))
        tree.setItemWidget(row, 3, spin)

        chk = QCheckBox()
        chk.setChecked(bool(getattr(f, "align_on_start", True)))
        chk.setEnabled(bus_id != "")   # Free-Run kann nicht taktgleich sein
        chk.setToolTip(
            "Startet dieser Effekt taktgleich auf dem gemeinsamen Beat-Raster seines Bus?")
        chk.toggled.connect(weak_slot_fwd(self._on_taktgleich_toggled, fid))
        wrap = QWidget(); wl = QHBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addStretch(1); wl.addWidget(chk); wl.addStretch(1)
        tree.setItemWidget(row, 4, wrap)

    def _on_row_bus_combo_changed(self, _i):
        # sender()-Adapter statt Lambda (STAB-09): fid haengt als Property am Combo.
        c = self.sender()
        if c is not None:
            self._on_row_bus_changed(c.property("fid"), c.currentData())

    # ── Handler ──────────────────────────────────────────────────────────────
    def _fn(self, fid):
        try:
            from src.core.engine.function_manager import get_function_manager
            return get_function_manager().get(int(fid))
        except Exception:
            return None

    def _on_taktgleich_toggled(self, fid, checked):
        f = self._fn(fid)
        if f is None:
            return
        f.align_on_start = bool(checked)
        try:   # laeuft der Effekt, sofort sauber neu ankern -> Haken wirkt sofort
            if getattr(f, "is_running", False) and hasattr(f, "sync_phase"):
                f.sync_phase()
        except Exception:
            pass

    def _on_row_mult_changed(self, fid, value):
        f = self._fn(fid)
        if f is None:
            return
        try:
            if hasattr(f, "set_param"):
                f.set_param("tempo_multiplier", float(value))
            else:
                f.tempo_multiplier = float(value)
        except Exception:
            pass

    def _on_row_bus_changed(self, fid, new_bus):
        try:
            from src.core.engine.tempo_bus import get_tempo_bus_manager
            get_tempo_bus_manager().assign_effects_to_bus([int(fid)], new_bus or "")
        except Exception:
            pass
        # Tree erst NACH dem Signal neu bauen (loescht das ausloesende Combo) — sonst
        # wird das gerade feuernde Widget synchron zerstoert (Crash-Gefahr).
        QTimer.singleShot(0, self._refresh_effects_panel)

    def _on_bus_sync_now(self, bus_id):
        try:
            from src.core.engine.tempo_bus import get_tempo_bus_manager
            bus = get_tempo_bus_manager().bus_for_effect(bus_id)
            if bus is not None:
                bus.sync(reset_downbeat=True)
        except Exception:
            pass

    # ── Tempo-Speeds & Grand-Master (Phase D2) ─────────────────────────────────

    def _tbm(self):
        from src.core.engine.tempo_bus import get_tempo_bus_manager
        return get_tempo_bus_manager()

    @staticmethod
    def _fmt_mult(f: float) -> str:
        table = {0.25: "¼", 0.5: "½", 0.75: "¾", 1.0: "1×", 2.0: "2×", 4.0: "4×",
                 8.0: "8×", 0.125: "⅛"}
        if f in table:
            return table[f]
        return f"{int(f)}×" if float(f).is_integer() else f"{f:g}×"

    def _build_speeds(self) -> QGroupBox:
        box = QGroupBox("Tempo-Speeds && Grand-Master")
        lay = QVBoxLayout(box)

        # Grand-Master-Zeile (uebertrumpft alle Master, wenn scharf).
        gm = QHBoxLayout()
        self._gm_arm = QCheckBox("Grand-Master scharf")
        self._gm_arm.setToolTip("Wenn aktiv: ALLE Master laufen auf dem Grand-Master-Takt "
                                "(Subs bleiben relativ).")
        self._gm_arm.toggled.connect(self._on_gm_arm)
        gm.addWidget(self._gm_arm)
        gm.addWidget(QLabel("BPM:"))
        self._gm_bpm = QDoubleSpinBox()
        self._gm_bpm.setRange(0, 999)
        self._gm_bpm.setDecimals(0)
        self._gm_bpm.setToolTip("Grand-Master-Takt (0 = aus).")
        self._gm_bpm.valueChanged.connect(self._on_gm_bpm)
        gm.addWidget(self._gm_bpm)
        b_tap = QPushButton("Tap")
        b_tap.clicked.connect(self._on_gm_tap)
        gm.addWidget(b_tap)
        self._gm_status = QLabel("aus")
        self._gm_status.setStyleSheet("color:#8b949e;")
        gm.addWidget(self._gm_status)
        gm.addStretch(1)
        lay.addLayout(gm)

        # Auto-Sync + Einmal-Sync — Effekte unterschiedlicher Geschwindigkeit
        # starten taktgleich (gemeinsamer Beat-Raster-Ursprung). Spiegelt die
        # VC-Aktionen „Auto-Sync" / „Sync (Bus)", aber als fester, auffindbarer
        # Schalter (ohne dass ein VC-Button gelegt sein muss).
        sy = QHBoxLayout()
        self._chk_auto_sync = QCheckBox("Auto-Sync")
        self._chk_auto_sync.setToolTip(
            "An: neu (oder erneut) gestartete bus-gekoppelte Effekte übernehmen "
            "denselben Beat-Raster-Ursprung → sie starten taktgleich, egal wann "
            "ausgelöst (z. B. Dimmer ×½ und Farbe ×1 bleiben phasengleich). "
            "Aus = jeder Effekt startet bei seiner eigenen Null.")
        self._chk_auto_sync.toggled.connect(self._on_auto_sync_toggled)
        sy.addWidget(self._chk_auto_sync)
        b_sync_now = QPushButton("Jetzt synchronisieren")
        b_sync_now.setToolTip(
            "Re-ankert alle laufenden Effekte auf den aktuellen Downbeat (die Eins): "
            "sie beginnen ihren Zyklus gemeinsam auf demselben Schlag, auch bei "
            "unterschiedlichem Multiplikator.")
        b_sync_now.clicked.connect(self._on_sync_now)
        sy.addWidget(b_sync_now)
        sy.addStretch(1)
        lay.addLayout(sy)

        # Bus-Tabelle (Anzeige).
        self._bus_table = QTableWidget(0, 5)
        self._bus_table.setHorizontalHeaderLabels(["Bus", "Rolle", "Folgt", "Faktor", "BPM"])
        self._bus_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._bus_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._bus_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._bus_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._bus_table.itemSelectionChanged.connect(self._on_bus_selected)
        self._bus_table.setMinimumHeight(120)
        lay.addWidget(self._bus_table)

        # Anlegen / Loeschen (Aktualisieren: 150-ms-Poll + Knopf im Effekte-Panel).
        cr = QHBoxLayout()
        self._new_master_name = QLineEdit()
        self._new_master_name.setPlaceholderText("Neuer Master-Name (z.B. Bass, Drums)")
        cr.addWidget(self._new_master_name)
        b_add = QPushButton("Master anlegen")
        b_add.clicked.connect(self._on_add_master)
        cr.addWidget(b_add)
        b_del = QPushButton("Löschen")
        b_del.clicked.connect(self._on_delete_bus)
        cr.addWidget(b_del)
        lay.addLayout(cr)

        # Editor fuer den gewaehlten Bus: Rolle / Folgt / Faktor.
        er = QHBoxLayout()
        er.addWidget(QLabel("Gewählt:"))
        self._edit_busid = QLabel("—")
        self._edit_busid.setMinimumWidth(60)
        er.addWidget(self._edit_busid)
        er.addWidget(QLabel("Rolle:"))
        self._edit_role = QComboBox()
        self._edit_role.addItem("Master", "master")
        self._edit_role.addItem("Sub", "sub")
        er.addWidget(self._edit_role)
        er.addWidget(QLabel("Folgt:"))
        self._edit_parent = QComboBox()
        er.addWidget(self._edit_parent)
        er.addWidget(QLabel("Faktor:"))
        self._edit_factor = QComboBox()
        for _f in (0.25, 0.5, 1.0, 2.0, 4.0):
            self._edit_factor.addItem(self._fmt_mult(_f), _f)
        er.addWidget(self._edit_factor)
        b_apply = QPushButton("Übernehmen")
        b_apply.clicked.connect(self._on_apply_bus_edit)
        er.addWidget(b_apply)
        er.addStretch(1)
        lay.addLayout(er)
        return box

    def _refresh_speeds(self):
        mgr = self._tbm()
        # Grand-Master-Controls (ohne Signal-Echo).
        self._gm_arm.blockSignals(True)
        self._gm_bpm.blockSignals(True)
        self._gm_arm.setChecked(bool(mgr.grandmaster_armed))
        self._gm_bpm.setValue(float(mgr.grandmaster_bpm))
        self._gm_arm.blockSignals(False)
        self._gm_bpm.blockSignals(False)
        active = mgr.grandmaster_armed and mgr.grandmaster_bpm > 0
        self._gm_status.setText("scharf" if active else "aus")
        self._gm_status.setStyleSheet("color:#3fb950;" if active else "color:#8b949e;")

        # Auto-Sync-Toggle spiegeln (ohne Signal-Echo).
        self._chk_auto_sync.blockSignals(True)
        self._chk_auto_sync.setChecked(bool(mgr.auto_sync))
        self._chk_auto_sync.blockSignals(False)

        # Parent-Auswahl = Default + benannte Master.
        self._edit_parent.blockSignals(True)
        self._edit_parent.clear()
        self._edit_parent.addItem("(Sound-BPM/Default)", "")
        for b in mgr.master_buses():
            self._edit_parent.addItem(b.bus_id, b.bus_id)
        self._edit_parent.blockSignals(False)

        # Tabelle: Default zuerst, dann benannte Buses alphabetisch.
        buses = sorted(mgr.all_buses(),
                       key=lambda b: (b.bus_id != mgr.DEFAULT_BUS, b.bus_id))
        self._bus_table.blockSignals(True)
        self._bus_table.setRowCount(len(buses))
        for r, b in enumerate(buses):
            role = getattr(b, "role", "master")
            is_sub = role == "sub"
            label = "Default (Sound-BPM)" if b.bus_id == mgr.DEFAULT_BUS else b.bus_id
            vals = [
                label,
                "Sub" if is_sub else "Master",
                (getattr(b, "parent_id", "") or "Sound-BPM") if is_sub else "—",
                self._fmt_mult(b.bus_multiplier) if is_sub else "—",
                f"{b.bpm:.0f}" if b.bpm > 0 else "—",
            ]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._bus_table.setItem(r, c, it)
        self._bus_table.blockSignals(False)

    def _refresh_bus_bpm_live(self):
        """Zieht nur die BPM-Spalte der bestehenden Bus-Zeilen live nach — billig,
        ohne Tabellen-Rebuild (Auswahl/Combos/Editor bleiben erhalten). Hängt am
        150-ms-Poll, weil ein TempoBus keine Subscribe-API hat (gleicher Ansatz
        wie ``vc_bpm_display``): Default/Sound-BPM und Subs, die ihr folgen,
        ändern ihren Wert live im Render-Thread, ohne ein UI-Event auszulösen.
        Bei geänderter Bus-Anzahl einmal voll neu aufbauen (Struktur-Änderung)."""
        table = getattr(self, "_bus_table", None)
        if table is None:
            return
        mgr = self._tbm()
        buses = sorted(mgr.all_buses(),
                       key=lambda b: (b.bus_id != mgr.DEFAULT_BUS, b.bus_id))
        if table.rowCount() != len(buses):
            self._refresh_speeds()   # Buses dazu/entfernt → voller Rebuild
            return
        for r, b in enumerate(buses):
            text = f"{b.bpm:.0f}" if b.bpm > 0 else "—"
            it = table.item(r, 4)
            if it is None:
                it = QTableWidgetItem(text)
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(r, 4, it)
            elif it.text() != text:
                it.setText(text)

    def _selected_bus_id(self) -> str:
        items = self._bus_table.selectedItems()
        if not items:
            return ""
        it = self._bus_table.item(items[0].row(), 0)
        if it is None:
            return ""
        text = it.text()
        # Default-Zeile traegt das Label "Default (Sound-BPM)".
        return self._tbm().DEFAULT_BUS if text.startswith("Default") else text

    def _on_gm_arm(self, checked: bool):
        self._tbm().set_grandmaster_armed(bool(checked))
        self._refresh_speeds()

    def _on_gm_bpm(self, val: float):
        mgr = self._tbm()
        mgr.set_grandmaster_bpm(float(val))
        active = mgr.grandmaster_armed and mgr.grandmaster_bpm > 0
        self._gm_status.setText("scharf" if active else "aus")
        self._gm_status.setStyleSheet("color:#3fb950;" if active else "color:#8b949e;")

    def _on_gm_tap(self):
        self._tbm().tap_grandmaster()
        self._refresh_speeds()

    def _on_add_master(self):
        name = (self._new_master_name.text() or "").strip()
        if not name:
            return
        mgr = self._tbm()
        # ENG-26: auch die ALIASE des Default-Busses abweisen, nicht nur seinen
        # woertlichen Namen. Seit `ensure_bus` den Alias aufloest, kaeme bei
        # einem getippten „Global" sonst der Default-Bus zurueck — der Nutzer
        # saehe keinen neuen Eintrag und wuesste nicht warum. Vorher entstand
        # hier ein Phantom-Bus, den kein Effekt liest; beides ist stumm, aber
        # nur eines davon laesst sich hier abfangen.
        if mgr.kanonische_bus_id(name) == mgr.DEFAULT_BUS:
            return
        bus = mgr.ensure_bus(name)
        bus.set_role("master")
        self._new_master_name.clear()
        self._refresh_speeds()

    def _on_delete_bus(self):
        bid = self._selected_bus_id()
        if not bid or bid == self._tbm().DEFAULT_BUS:
            return
        self._tbm().remove_bus(bid)
        self._refresh_speeds()

    def _on_bus_selected(self):
        bid = self._selected_bus_id()
        self._edit_busid.setText(bid or "—")
        if not bid:
            return
        bus = self._tbm().get(bid)
        if bus is None:
            return
        role = getattr(bus, "role", "master")
        self._edit_role.setCurrentIndex(1 if role == "sub" else 0)
        pidx = self._edit_parent.findData(getattr(bus, "parent_id", "") or "")
        if pidx >= 0:
            self._edit_parent.setCurrentIndex(pidx)
        fidx = self._edit_factor.findData(bus.bus_multiplier)
        if fidx >= 0:
            self._edit_factor.setCurrentIndex(fidx)

    def _on_apply_bus_edit(self):
        bid = self._selected_bus_id()
        mgr = self._tbm()
        if not bid or bid == mgr.DEFAULT_BUS:
            return
        bus = mgr.get(bid)
        if bus is None:
            return
        role = self._edit_role.currentData() or "master"
        bus.set_role(role)
        if role == "sub":
            bus.set_parent(self._edit_parent.currentData() or "")
            try:
                bus.set_bus_multiplier(float(self._edit_factor.currentData() or 1.0))
            except (TypeError, ValueError):
                pass
        self._refresh_speeds()

    def _on_auto_sync_toggled(self, checked: bool):
        """Auto-Sync an/aus (global, alle Tempo-Buses) — spiegelt die VC-Aktion."""
        self._tbm().set_auto_sync(bool(checked))

    def _on_sync_now(self):
        """Einmal-Sync wie der VC-'Sync'-Knopf, aber für ALLE Buses: jeder Bus
        setzt seinen Downbeat neu und re-ankert seine Effekte auf 'jetzt' — sie
        beginnen ihren Zyklus gemeinsam auf demselben Schlag."""
        mgr = self._tbm()
        try:
            for b in mgr.all_buses():
                try:
                    b.sync(reset_downbeat=True)
                except Exception as e:
                    print(f"[TempoBusView] sync bus {getattr(b, 'bus_id', '?')}: {e}")
        except Exception as e:
            print(f"[TempoBusView] sync-now error: {e}")

    # ── Sichtbarkeit: Poll-Timer nur im Vordergrund ───────────────────────────

    def showEvent(self, e):
        self._poll.start()
        self._refresh_speeds()
        self._refresh_effects_panel()
        super().showEvent(e)

    def hideEvent(self, e):
        self._poll.stop()
        super().hideEvent(e)
