"""Preset-Browser (UI-01).

Ein Suchfeld über Paletten UND Fixture-Gruppen: tippen filtert live, Doppelklick
(oder Enter) wendet den Treffer an — Palette → in den Programmer (auf die aktuelle
Auswahl, sonst alle), Gruppe → deren Fixtures auswählen. Die Filterlogik selbst
liegt Qt-frei in ``preset_search`` (headless getestet); diese View baut nur die
Einträge und stellt sie dar.
"""
from __future__ import annotations

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLineEdit,
                                QListWidget, QListWidgetItem, QLabel)
from PySide6.QtCore import Qt

from src.core.engine.palette import get_palette_manager
from src.core.engine.preset_search import build_entries, filter_entries, PresetEntry


_KIND_PREFIX = {"palette": "🎨", "group": "👥"}


class PresetBrowserView(QWidget):
    """Durchsuchbarer Browser über Paletten + Fixture-Gruppen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[PresetEntry] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QLabel("Preset-Browser — Paletten & Gruppen")
        title.setStyleSheet("color:#e6edf3; font-size:12px; font-weight:bold;")
        layout.addWidget(title)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Suchen … (Name, Typ, Ordner, Tag)")
        self._search.setClearButtonEnabled(True)
        self._search.setStyleSheet(
            "QLineEdit { background:#0d1117; color:#e6edf3; border:1px solid #30363d;"
            " border-radius:4px; padding:5px 8px; font-size:12px; }"
            "QLineEdit:focus { border:1px solid #1f6feb; }")
        self._search.textChanged.connect(self._apply_filter)
        self._search.returnPressed.connect(self._apply_first)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget { background:#0d1117; color:#e6edf3; border:1px solid #30363d;"
            " border-radius:4px; font-size:12px; }"
            "QListWidget::item { padding:5px 6px; }"
            "QListWidget::item:selected { background:#1f6feb; color:#fff; }")
        self._list.itemActivated.connect(self._on_activated)
        self._list.itemDoubleClicked.connect(self._on_activated)
        layout.addWidget(self._list, 1)

        self._status = QLabel("")
        self._status.setStyleSheet("color:#8b949e; font-size:10px;")
        layout.addWidget(self._status)

        self._reload_entries()

        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            for ev in (SyncEvent.REFRESH_ALL, SyncEvent.PALETTE_CHANGED,
                       SyncEvent.PATCH_CHANGED, SyncEvent.GROUP_CHANGED):
                sync.subscribe_widget(ev, self, lambda *_: self._reload_entries())
        except Exception as e:
            print(f"[preset_browser] sync subscribe error: {e}")

    # ── Daten ──────────────────────────────────────────────────────────────────

    def _reload_entries(self):
        """Paletten + Gruppen frisch einlesen und die Liste neu filtern."""
        try:
            palettes = get_palette_manager().get_all()
        except Exception:
            palettes = []
        try:
            from src.core.app_state import get_state
            groups = get_state().list_fixture_groups()
        except Exception:
            groups = []
        self._entries = build_entries(palettes, groups)
        self._apply_filter()

    def _apply_filter(self):
        hits = filter_entries(self._search.text(), self._entries)
        self._list.clear()
        for e in hits:
            prefix = _KIND_PREFIX.get(e.kind, "•")
            label = f"{prefix}  {e.name}"
            if e.subtitle:
                label += f"   —   {e.subtitle}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, e)
            self._list.addItem(item)
        n_pal = sum(1 for e in hits if e.kind == "palette")
        n_grp = sum(1 for e in hits if e.kind == "group")
        self._status.setText(
            f"{len(hits)} Treffer ({n_pal} Paletten, {n_grp} Gruppen) · "
            "Doppelklick/Enter wendet an")

    # ── Anwenden ────────────────────────────────────────────────────────────────

    def _apply_first(self):
        if self._list.count() > 0:
            self._activate_item(self._list.item(0))

    def _on_activated(self, item: QListWidgetItem):
        self._activate_item(item)

    def _activate_item(self, item: QListWidgetItem | None):
        if item is None:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(entry, PresetEntry):
            return
        try:
            if entry.kind == "palette":
                entry.ref.apply_to_programmer(self._target_fids())
                self._status.setText(f"Palette angewendet: {entry.name}")
            elif entry.kind == "group":
                from src.core.app_state import get_state
                ok = get_state().select_group_by_name(entry.ref)
                self._status.setText(
                    f"Gruppe ausgewählt: {entry.name}" if ok
                    else f"Gruppe ohne Geräte: {entry.name}")
        except Exception as e:
            print(f"[preset_browser] apply error: {e}")

    @staticmethod
    def _target_fids() -> list[int] | None:
        """Aktuelle Programmer-Auswahl; None = alle Geräte (Fallback)."""
        try:
            from src.core.app_state import get_state
            fids = get_state().get_selected_fids()
            return list(fids) if fids else None
        except Exception:
            return None
