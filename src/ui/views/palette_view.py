"""Palette View — Color, Position, Beam preset manager."""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
                                QScrollArea, QGridLayout, QPushButton, QLabel,
                                QLineEdit, QInputDialog, QMessageBox, QSizePolicy)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QPainter, QFont
from src.core.engine.palette import PaletteManager, Palette, PaletteType, get_palette_manager


class PaletteButton(QPushButton):
    """Button showing a palette swatch."""
    SIZE = 72

    def __init__(self, palette: Palette, parent=None):
        super().__init__(parent)
        self.palette = palette
        self.setFixedSize(self.SIZE, self.SIZE)
        self._update_style()
        self.setToolTip(palette.name)

    def _update_style(self):
        p = self.palette
        if p.type == PaletteType.COLOR:
            r = p.values.get("color_r", 200)
            g = p.values.get("color_g", 200)
            b = p.values.get("color_b", 200)
            bg = f"rgb({r},{g},{b})"
            text_color = "#000" if (r + g + b) > 380 else "#fff"
        elif p.type == PaletteType.POSITION:
            bg = "#1a3a5c"
            text_color = "#58a6ff"
        elif p.type == PaletteType.BEAM:
            bg = "#1a4a2a"
            text_color = "#3fb950"
        elif p.type == PaletteType.LASER:
            bg = "#2a0a3a"
            text_color = "#e879f9"
        else:
            bg = "#2a1a4a"
            text_color = "#bc8cff"

        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg}; color: {text_color};
                border: 1px solid #30363d; border-radius: 4px;
                font-size: 9px; font-weight: bold;
                padding: 4px;
            }}
            QPushButton:hover {{ border: 2px solid #58a6ff; }}
            QPushButton:pressed {{ border: 2px solid #1f6feb; background: #4d8dff; }}
        """)
        self.setText(p.name)

    def apply(self, fids: list[int] | None = None):
        self.palette.apply_to_programmer(fids)


class PalettePage(QWidget):
    """Scrollable grid of palette buttons for one type."""

    def __init__(self, ptype: PaletteType, manager: PaletteManager, parent=None):
        super().__init__(parent)
        self.ptype = ptype
        self.manager = manager
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Toolbar
        tbar = QHBoxLayout()
        btn_new = QPushButton("+ Neu aufzeichnen")
        btn_new.setFixedHeight(26)
        btn_new.setStyleSheet("""
            QPushButton { background:#21262d; color:#3fb950; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; }
            QPushButton:hover { background:#30363d; }
        """)
        btn_new.clicked.connect(self._record_new)
        tbar.addWidget(btn_new)
        tbar.addStretch()
        # F-1: Such-/Filterfeld (filtert nach Paletten-Name und Ordner).
        self._search = QLineEdit()
        self._search.setPlaceholderText("Suchen…")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedWidth(160)
        self._search.setStyleSheet(
            "QLineEdit { background:#0d1117; color:#e6edf3; border:1px solid #30363d;"
            " border-radius:3px; font-size:10px; padding:2px 6px; }")
        self._search.textChanged.connect(self._refresh)
        tbar.addWidget(self._search)
        layout.addLayout(tbar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border:none; background:#0d1117; }")
        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background:#0d1117;")
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setSpacing(6)
        scroll.setWidget(self._grid_widget)
        layout.addWidget(scroll)

        self._refresh()

    def _refresh(self, _=None):
        # Clear grid
        for i in reversed(range(self._grid.count())):
            item = self._grid.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()
        # FLD-01c: nach Ordner + Name sortieren und je Ordner eine Überschrift zeigen.
        palettes = list(self.manager.get_by_type(self.ptype))
        palettes.sort(key=lambda p: ((getattr(p, "folder", "") or "").lower(),
                                     (p.name or "").lower()))
        # F-1: Filter nach Suchtext (Name oder Ordner).
        q = self._search.text().strip().lower() if hasattr(self, "_search") else ""
        if q:
            palettes = [p for p in palettes
                        if q in (p.name or "").lower()
                        or q in (getattr(p, "folder", "") or "").lower()]
        col_count = 6
        row = 0
        col = 0
        cur_folder = None
        for pal in palettes:
            folder = getattr(pal, "folder", "") or ""
            if folder != cur_folder:
                if col != 0:
                    row += 1
                    col = 0
                cur_folder = folder
                hdr = QLabel(f"📁 {folder}" if folder else "● (kein Ordner)")
                hdr.setStyleSheet("color:#8b949e; font-size:10px; font-weight:bold; padding-top:4px;")
                self._grid.addWidget(hdr, row, 0, 1, col_count)
                row += 1
                col = 0
            btn = PaletteButton(pal)
            btn.clicked.connect(lambda checked=False, p=pal: self._apply(p))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, p=pal, b=btn: self._context(p, b)
            )
            self._grid.addWidget(btn, row, col)
            col += 1
            if col >= col_count:
                col = 0
                row += 1

    def _target_fids(self) -> list[int] | None:
        """Aktuelle Programmer-Auswahl; None = keine Auswahl.
        Anwenden (_apply) bricht bei None bewusst ab (sonst wuerde apply_to_programmer(None)
        die Palette auf das GANZE Rig schreiben); Aufzeichnen nimmt bei None den
        gesamten Programmer."""
        try:
            from src.core.app_state import get_state
            fids = get_state().get_selected_fids()
            return list(fids) if fids else None
        except Exception:
            return None

    def _apply(self, pal: Palette):
        fids = self._target_fids()
        if not fids:
            # Sicherheitsnetz: leere Auswahl wuerde sonst per apply_to_programmer(None)
            # die Palette auf ALLE gepatchten Geraete schreiben (ganzes Rig).
            QMessageBox.information(
                self, "Palette",
                "Keine Geräte ausgewählt — bitte zuerst die Fixtures auswählen, "
                "auf die die Palette wirken soll.")
            return
        pal.apply_to_programmer(fids)

    def _record_new(self):
        name, ok = QInputDialog.getText(self, "Palette aufzeichnen", "Name:")
        if not ok or not name:
            return
        pal = Palette(name=name, type=self.ptype)
        # aus der Auswahl aufzeichnen (None = gesamter Programmer, falls nichts gewaehlt)
        pal.record_from_programmer(self._target_fids())
        self.manager.add(pal)
        self._refresh()

    def _context(self, pal: Palette, btn: PaletteButton):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.addAction("Anwenden").triggered.connect(lambda: self._apply(pal))
        menu.addAction("Überschreiben (Programmer)").triggered.connect(
            lambda: (pal.record_from_programmer(self._target_fids()), self._refresh())
        )
        menu.addAction("In Ordner verschieben…").triggered.connect(
            lambda: self._set_folder(pal)
        )
        menu.addSeparator()
        menu.addAction("Löschen").triggered.connect(
            lambda: (self.manager.remove(pal), self._refresh())
        )
        menu.exec(btn.mapToGlobal(btn.rect().center()))

    def _set_folder(self, pal: Palette):
        """FLD-01c: Palette einem (verschachtelten) Ordner zuordnen (Pfad mit /)."""
        cur = getattr(pal, "folder", "") or ""
        path, ok = QInputDialog.getText(
            self, "Ordner setzen",
            "Ordnerpfad (verschachtelt mit /, leer = Wurzel):", text=cur)
        if not ok:
            return
        pal.folder = "/".join(p.strip() for p in path.split("/") if p.strip())
        self._refresh()
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.PALETTE_CHANGED, None)
        except Exception:
            pass


class PaletteView(QWidget):
    """Multi-tab palette manager: Color, Position, Beam, Effect."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._manager = get_palette_manager()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane { border:none; }
            QTabBar::tab { background:#161b22; color:#8b949e; padding:6px 14px;
                           border:1px solid #30363d; font-size:11px; }
            QTabBar::tab:selected { background:#1f6feb; color:#fff; }
        """)

        self._pages: list = []
        for ptype, label in [
            (PaletteType.COLOR,    "Farben"),
            (PaletteType.POSITION, "Position"),
            (PaletteType.BEAM,     "Beam"),
            (PaletteType.EFFECT,   "Effekte"),
            (PaletteType.LASER,    "Laser"),
        ]:
            page = PalettePage(ptype, self._manager)
            tabs.addTab(page, label)
            self._pages.append(page)

        layout.addWidget(tabs)

        # Zentraler StateSync: alle PalettePages refreshen
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            sync.subscribe_widget(SyncEvent.REFRESH_ALL, self, lambda *_: self._sync_refresh())
            sync.subscribe_widget(SyncEvent.PALETTE_CHANGED, self, lambda *_: self._sync_refresh())
            sync.subscribe_widget(SyncEvent.PATCH_CHANGED, self, lambda *_: self._sync_refresh())
        except Exception as e:
            print(f"[palette_view] sync subscribe error: {e}")

    def _sync_refresh(self):
        for page in getattr(self, "_pages", []):
            try:
                page._refresh()
            except Exception as e:
                print(f"[palette_view] page refresh error: {e}")
