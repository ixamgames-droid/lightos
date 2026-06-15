"""Fixture-Browser Dialog — Gerät aus DB wählen und patchen."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTreeWidget, QTreeWidgetItem, QComboBox,
    QSpinBox, QFormLayout, QGroupBox, QMessageBox, QSplitter
)
from PySide6.QtCore import Qt
from src.core.database import fixture_db as fdb
from src.core.database.models import FixtureProfile, PatchedFixture


class FixtureBrowserDialog(QDialog):
    def __init__(self, next_fid: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gerät hinzufügen")
        self.setMinimumSize(700, 500)
        self.result_fixture: PatchedFixture | None = None
        self._next_fid = next_fid
        self._selected_profile: FixtureProfile | None = None
        self._setup_ui()
        self._load_tree()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Suchleiste
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Suche:"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("Herstellername, Gerätename, Typ...")
        self._search.textChanged.connect(self._on_search)
        search_row.addWidget(self._search)
        layout.addLayout(search_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Geräte-Baum
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Gerät", "Typ", "Kanäle"])
        self._tree.setColumnWidth(0, 280)
        self._tree.setColumnWidth(1, 80)
        self._tree.currentItemChanged.connect(self._on_selection)
        splitter.addWidget(self._tree)

        # Rechte Seite: Optionen
        right = QGroupBox("Patch-Optionen")
        form = QFormLayout(right)

        self._lbl_manufacturer = QLabel("—")
        self._lbl_fixture = QLabel("—")
        form.addRow("Hersteller:", self._lbl_manufacturer)
        form.addRow("Gerät:", self._lbl_fixture)

        self._combo_mode = QComboBox()
        self._combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        form.addRow("Modus:", self._combo_mode)

        self._spin_count = QSpinBox()
        self._spin_count.setRange(1, 64)
        self._spin_count.setValue(1)
        form.addRow("Anzahl:", self._spin_count)

        self._edit_label = QLineEdit()
        form.addRow("Label:", self._edit_label)

        self._spin_universe = QSpinBox()
        self._spin_universe.setRange(1, 32)
        form.addRow("Universe:", self._spin_universe)

        self._spin_address = QSpinBox()
        self._spin_address.setRange(1, 512)
        form.addRow("DMX-Adresse:", self._spin_address)
        # P1: Hinweis unter dem Adressfeld — zeigt den automatischen Vorschlag
        # bzw. eine Warnung, wenn kein zusammenhaengender Bereich mehr frei ist.
        self._lbl_addr_hint = QLabel("")
        self._lbl_addr_hint.setWordWrap(True)
        self._lbl_addr_hint.setStyleSheet("color: #8b949e;")
        form.addRow("", self._lbl_addr_hint)
        self._spin_universe.valueChanged.connect(
            lambda _v: self._update_address_suggestion())

        self._spin_offset = QSpinBox()
        self._spin_offset.setRange(0, 64)
        self._spin_offset.setValue(0)
        self._spin_offset.setToolTip("Adress-Abstand zwischen mehreren Geräten (0 = dicht)")
        form.addRow("Adress-Offset:", self._spin_offset)

        splitter.addWidget(right)
        splitter.setSizes([400, 300])
        layout.addWidget(splitter)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Abbrechen")
        btn_cancel.clicked.connect(self.reject)
        self._btn_add = QPushButton("Hinzufügen")
        self._btn_add.setEnabled(False)
        self._btn_add.clicked.connect(self._on_add)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(self._btn_add)
        layout.addLayout(btn_row)

    def _load_tree(self, query: str = ""):
        self._tree.clear()
        if query:
            fixtures = fdb.search_fixtures(query)
            for f in fixtures:
                mfr_name = f.manufacturer.name if f.manufacturer else "Unbekannt"
                item = QTreeWidgetItem([
                    f"{mfr_name} — {f.name}", f.fixture_type,
                    str(f.modes[0].channel_count) if f.modes else "?"
                ])
                item.setData(0, Qt.ItemDataRole.UserRole, f.id)
                self._tree.addTopLevelItem(item)
        else:
            for mfr in fdb.get_all_manufacturers():
                mfr_item = QTreeWidgetItem([mfr.name, "", ""])
                mfr_item.setData(0, Qt.ItemDataRole.UserRole, None)
                fixtures = fdb.get_fixtures_by_manufacturer(mfr.id)
                for f in fixtures:
                    ch = str(f.modes[0].channel_count) if f.modes else "?"
                    child = QTreeWidgetItem([f.name, f.fixture_type, ch])
                    child.setData(0, Qt.ItemDataRole.UserRole, f.id)
                    mfr_item.addChild(child)
                if fixtures:
                    self._tree.addTopLevelItem(mfr_item)
            self._tree.expandAll()

    def _on_search(self, text: str):
        self._load_tree(text.strip())

    def _on_selection(self, current, _previous):
        if not current:
            return
        fid = current.data(0, Qt.ItemDataRole.UserRole)
        if fid is None:
            return
        profile = fdb.get_fixture(fid)
        if not profile:
            return
        self._selected_profile = profile
        self._lbl_manufacturer.setText(
            profile.manufacturer.name if profile.manufacturer else "—"
        )
        self._lbl_fixture.setText(profile.name)
        self._combo_mode.clear()
        modes = fdb.get_modes(profile.id)
        for m in modes:
            self._combo_mode.addItem(f"{m.name} ({m.channel_count}ch)", m.id)
        self._edit_label.setText(profile.short_name or profile.name)
        self._btn_add.setEnabled(True)

    def _on_mode_changed(self, _idx):
        self._update_address_suggestion()

    def _current_channel_count(self) -> int:
        mode_id = self._combo_mode.currentData()
        if not mode_id:
            return 0
        try:
            return len(fdb.get_channels(mode_id))
        except Exception:
            return 0

    def _update_address_suggestion(self):
        """P1: naechsten freien zusammenhaengenden Kanalbereich vorschlagen
        (zentrale Logik: AppState.suggest_address — lueckenbewusst, pro
        Universum). Kein Platz -> deutliche Warnung statt stillem Konflikt."""
        ch_count = self._current_channel_count()
        if ch_count <= 0:
            return
        try:
            from src.core.app_state import get_state
            suggestion = get_state().suggest_address(
                self._spin_universe.value(), ch_count)
        except Exception:
            return
        if suggestion is None:
            self._lbl_addr_hint.setText(
                f"⚠ Kein freier zusammenhängender Bereich für {ch_count} "
                f"Kanäle in Universe {self._spin_universe.value()} — bitte "
                f"anderes Universum wählen oder Patch aufräumen.")
            self._lbl_addr_hint.setStyleSheet("color: #f85149;")
        else:
            self._spin_address.setValue(suggestion)
            self._lbl_addr_hint.setText(
                f"Vorschlag: Adresse {suggestion} "
                f"(nächster freier Bereich für {ch_count} Kanäle)")
            self._lbl_addr_hint.setStyleSheet("color: #8b949e;")

    def _on_add(self):
        if not self._selected_profile:
            return
        mode_id = self._combo_mode.currentData()
        mode_name = self._combo_mode.currentText().split(" (")[0]
        channels = fdb.get_channels(mode_id) if mode_id else []
        ch_count = len(channels)
        count = self._spin_count.value()
        universe = self._spin_universe.value()
        address = self._spin_address.value()
        offset = self._spin_offset.value() or ch_count
        label_base = self._edit_label.text() or self._selected_profile.name
        fid = self._next_fid

        # Bei mehreren Geräten: erstes zurückgeben (weitere werden in patch_view hinzugefügt)
        self.result_fixture = PatchedFixture(
            fid=fid,
            label=label_base if count == 1 else f"{label_base} 1",
            fixture_profile_id=self._selected_profile.id,
            mode_name=mode_name,
            universe=universe,
            address=address,
            channel_count=ch_count,
            manufacturer_name=self._selected_profile.manufacturer.name if self._selected_profile.manufacturer else "",
            fixture_name=self._selected_profile.name,
            fixture_type=self._selected_profile.fixture_type,
        )
        # Zusatz-Geräte als Liste mitgeben. Laeuft die Adresse ueber 512, wird
        # ins naechste Universe gerollt (statt Geraete still zu verwerfen).
        # Erst wenn auch Universe 32 voll ist, brechen wir ab und melden, wie
        # viele Geraete nicht mehr gepatcht werden konnten (self.skipped_count).
        self.extra_fixtures = []
        self.skipped_count = 0
        cur_univ = universe
        cur_addr = address
        for i in range(1, count):
            cur_addr += offset
            if cur_addr + ch_count - 1 > 512:
                cur_univ += 1
                cur_addr = 1
                if cur_univ > 32:
                    self.skipped_count = count - i
                    break
            self.extra_fixtures.append(PatchedFixture(
                fid=fid + i,
                label=f"{label_base} {i + 1}",
                fixture_profile_id=self._selected_profile.id,
                mode_name=mode_name,
                universe=cur_univ,
                address=cur_addr,
                channel_count=ch_count,
                manufacturer_name=self._selected_profile.manufacturer.name if self._selected_profile.manufacturer else "",
                fixture_name=self._selected_profile.name,
                fixture_type=self._selected_profile.fixture_type,
            ))
        self.accept()
