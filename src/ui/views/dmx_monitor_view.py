"""DMX Monitor View - displays all 512 DMX channels in a 32x16 grid."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QSpinBox, QCheckBox, QLineEdit, QToolTip,
)
from PySide6.QtCore import Qt, QTimer, QRect, QSize, QEvent
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from src.core.app_state import get_state
# U-4/SD-03: Kanal-Funktion (Kürzel + Farbe) — dieselben Helfer wie der Simple Desk.
from src.ui.views.simple_desk import channel_function_color, channel_function_abbrev


COLS = 32
ROWS = 16
CELL_W = 36
CELL_H = 30


class DmxGrid(QWidget):
    """Custom widget that paints all 512 channels as a colored grid."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._values = [0] * 512
        self._patched_addrs: set[int] = set()  # DMX addresses occupied by patched fixtures
        self._highlighted: set[int] = set()    # filter highlights
        # U-4/SD-03: addr -> (Geräte-Kürzel, Attribut, voller Tooltip-Text)
        self._cell_info: dict[int, tuple[str, str, str]] = {}
        self.setMinimumSize(COLS * CELL_W, ROWS * CELL_H)
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(),
                           self.sizePolicy().verticalPolicy())

    def set_values(self, values: list[int]):
        if len(values) >= 512:
            self._values = list(values[:512])
        else:
            self._values = list(values) + [0] * (512 - len(values))
        self.update()

    def set_patched_addrs(self, addrs):
        self._patched_addrs = set(addrs)
        self.update()

    def set_highlighted(self, addrs):
        self._highlighted = set(addrs)
        self.update()

    def set_cell_info(self, info: dict[int, tuple[str, str, str]]):
        """U-4/SD-03: Patch-Kontext je Adresse (Geräte-Kürzel, Attribut, Tooltip)."""
        self._cell_info = dict(info)
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(COLS * CELL_W, ROWS * CELL_H)

    def event(self, e):
        # U-4/SD-03: voller Kanalname (Gerät + Kanal) als Tooltip pro Zelle.
        if e.type() == QEvent.Type.ToolTip:
            cw = self.width() / COLS
            chh = self.height() / ROWS
            pos = e.pos()
            col = int(pos.x() // cw) if cw else -1
            row = int(pos.y() // chh) if chh else -1
            if 0 <= col < COLS and 0 <= row < ROWS:
                chan_no = row * COLS + col + 1
                val = self._values[chan_no - 1] if chan_no - 1 < len(self._values) else 0
                info = self._cell_info.get(chan_no)
                if info:
                    QToolTip.showText(e.globalPos(), f"CH {chan_no}: {info[2]}  =  {val}", self)
                else:
                    QToolTip.showText(e.globalPos(), f"CH {chan_no}  =  {val}", self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        cw = self.width() / COLS
        ch = self.height() / ROWS
        small_font = QFont("Segoe UI", 7)
        big_font = QFont("Courier New", 10)
        big_font.setBold(True)

        for ch_idx in range(512):
            row = ch_idx // COLS
            col = ch_idx % COLS
            x = col * cw
            y = row * ch
            val = self._values[ch_idx]
            chan_no = ch_idx + 1
            info = self._cell_info.get(chan_no)   # (Kürzel, Attribut, Tooltip) o. None
            # Background
            shade = int(val * 0.85)
            if val == 0:
                bg = QColor(22, 22, 28)
            elif val < 128:
                bg = QColor(shade // 3, shade // 3, shade)
            else:
                bg = QColor(shade, shade, shade)
            p.fillRect(int(x), int(y), int(cw) + 1, int(ch) + 1, bg)

            # U-4/SD-03: gepatchte Zelle dezent in der Kanal-Funktionsfarbe tönen.
            if info:
                tint = QColor(channel_function_color(info[1]))
                tint.setAlpha(40)
                p.fillRect(int(x), int(y), int(cw) + 1, int(ch) + 1, tint)

            # Border (patched/normal)
            if chan_no in self._highlighted:
                p.setPen(QPen(QColor("#FFD700"), 2))
            elif chan_no in self._patched_addrs:
                p.setPen(QPen(QColor("#0978FF"), 1))
            else:
                p.setPen(QPen(QColor(40, 40, 50), 1))
            p.drawRect(int(x), int(y), int(cw), int(ch))

            # Channel number (top, small)
            p.setFont(small_font)
            p.setPen(QColor("#888888") if val < 100 else QColor("#dddddd"))
            p.drawText(int(x) + 2, int(y) + 2, int(cw) - 4, 12,
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                       str(chan_no))

            # Value (center, big) — bei Patch-Kontext unten Platz für die Kürzel-Zeile.
            label_h = 11 if info else 0
            p.setFont(big_font)
            p.setPen(QColor("#ffffff") if val > 80 else QColor("#aaaaaa"))
            p.drawText(int(x), int(y), int(cw), int(ch) - label_h,
                       Qt.AlignmentFlag.AlignCenter, str(val))

            # U-4/SD-03: Geräte-Kürzel + Kanal-Funktion (z. B. 'PAR 1 R') unten,
            # in der Funktionsfarbe; voller Name steckt im Tooltip.
            if info:
                short, attr = info[0], info[1]
                abbrev = channel_function_abbrev(attr)
                text = f"{short} {abbrev}".strip()
                p.setFont(small_font)
                p.setPen(QColor(channel_function_color(attr)))
                p.drawText(int(x) + 1, int(y) + int(ch) - 11, int(cw) - 2, 10,
                           Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                           text)
        p.end()


class DmxMonitorView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = get_state()
        self._setup_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(33)  # ~30 Hz

        # Zentraler StateSync
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            sync.subscribe(SyncEvent.REFRESH_ALL, lambda *_: self._sync_refresh())
            sync.subscribe(SyncEvent.PATCH_CHANGED, lambda *_: self._sync_refresh())
        except Exception as e:
            print(f"[dmx_monitor_view] sync subscribe error: {e}")

    def _sync_refresh(self):
        try:
            self._refresh_patched()
            self._refresh()
        except Exception as e:
            print(f"[dmx_monitor_view] sync_refresh error: {e}")

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)

        # Top toolbar
        top = QHBoxLayout()
        top.addWidget(QLabel("Universe:"))
        self._combo_univ = QComboBox()
        for u in range(1, 17):
            self._combo_univ.addItem(f"Universe {u}", u)
        self._combo_univ.currentIndexChanged.connect(self._refresh_patched)
        top.addWidget(self._combo_univ)

        top.addSpacing(20)
        top.addWidget(QLabel("Hervorgehobene Kanäle:"))
        self._edit_filter = QLineEdit()
        self._edit_filter.setPlaceholderText("z.B. 1,5,10-20")
        self._edit_filter.setFixedWidth(160)
        self._edit_filter.textChanged.connect(self._on_filter_changed)
        top.addWidget(self._edit_filter)

        top.addStretch(1)
        self._lbl_legend = QLabel(
            'Blauer Rahmen = gepatcht  |  Gelber Rahmen = hervorgehoben  |  '
            'Farbige Kürzel = Kanalfunktion (z. B. Rot = Rot-Farbkanal, '
            'Gelb = Dimmer, Blau = Blau/Position)'
        )
        # UI-24a: kräftigeres Grau für besseren Kontrast auf dunklem Grund.
        self._lbl_legend.setStyleSheet("color: #b0b6c0; font-size: 11px;")
        top.addWidget(self._lbl_legend)
        root.addLayout(top)

        # Grid
        self._grid = DmxGrid()
        root.addWidget(self._grid, 1)

        self._refresh_patched()

    def _refresh_patched(self):
        univ = self._combo_univ.currentData() or 1
        addrs = set()
        info: dict[int, tuple[str, str, str]] = {}
        # Lazy-Import (analog Simple Desk), damit Tests get_channels_for_patched mocken können.
        from src.core.app_state import get_channels_for_patched
        try:
            for f in self._state.get_patched_fixtures():
                if f.universe != univ:
                    continue
                for off in range(getattr(f, "channel_count", 0) or 0):
                    a = f.address + off
                    if 1 <= a <= 512:
                        addrs.add(a)
                # U-4/SD-03: pro Kanal Kürzel + Attribut + voller Name (Tooltip).
                label = (getattr(f, "label", "") or "").strip() or f"Fixture {getattr(f, 'fid', '?')}"
                short = label[:6]
                try:
                    for cobj in get_channels_for_patched(f):
                        a = f.address + cobj.channel_number - 1
                        if not (1 <= a <= 512):
                            continue
                        attr = (getattr(cobj, "attribute", "") or "")
                        cname = cobj.name if (getattr(cobj, "name", None) and cobj.name.strip()) else attr
                        info[a] = (short, attr, f"{label} — {cname}")
                except Exception:
                    pass
        except Exception:
            pass
        self._grid.set_patched_addrs(addrs)
        self._grid.set_cell_info(info)

    def _on_filter_changed(self, txt: str):
        addrs = set()
        for part in txt.split(','):
            part = part.strip()
            if not part:
                continue
            try:
                if '-' in part:
                    a, b = part.split('-', 1)
                    a = int(a.strip())
                    b = int(b.strip())
                    if a > b: a, b = b, a
                    for v in range(a, b + 1):
                        if 1 <= v <= 512:
                            addrs.add(v)
                else:
                    v = int(part)
                    if 1 <= v <= 512:
                        addrs.add(v)
            except ValueError:
                continue
        self._grid.set_highlighted(addrs)

    def _refresh(self):
        univ = self._combo_univ.currentData() or 1
        if univ not in self._state.universes:
            return
        try:
            # WYSIWYG: den GESENDETEN Output zeigen (POST Grand-Master/Blackout).
            # Fallback auf den Rohpuffer, solange noch kein Frame gesendet wurde.
            data = None
            om = getattr(self._state, "output_manager", None)
            if om is not None:
                data = om.get_display_frame(univ)
            if data is None:
                data = self._state.universes[univ].get_all()
            self._grid.set_values(data)
        except Exception:
            pass
