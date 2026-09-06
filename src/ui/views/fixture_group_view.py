"""Fixture Group View - 2D grid where fixtures are placed (drag&drop)."""
from __future__ import annotations
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QPushButton, QComboBox, QSpinBox, QInputDialog, QMessageBox, QGroupBox,
    QFormLayout, QFrame, QSizePolicy, QGridLayout,
    QDialog, QListWidget, QListWidgetItem, QAbstractItemView, QDialogButtonBox,
    QMenu,
)
from PySide6.QtCore import Qt, QMimeData, QSize, QPoint, Signal
from PySide6.QtGui import (
    QPainter, QColor, QPen, QDrag, QFont, QBrush,
)
from src.core.app_state import get_state
from src.core.database.models import FixtureGroup
from src.core.group_cells import (base_fids_in_grid_order,
                                  referenzierte_fids_in_grid_order)
from src.ui.widgets import mini_icons as _mini
from sqlalchemy.orm import Session
from sqlalchemy import select, delete


from src.core.group_cells import (          # noqa: E402  (nach den Qt-Importen)
    ACHSE_FARBE, ACHSE_WEISS, parse_zelle, zelle_fuer, zelle_gehoert_zu,
)


def _split_cell(v):
    """FM-16e: Rasterzellwert -> (fid, head). ``v`` ist ENTWEDER ein ganzer fid
    (int/str) ODER eine Kopf-Zelle ``"fid:head"`` (Str, aus create_head_matrix_group
    / Merge). head=None fuer ganze Fixtures; (None, None) wenn unparsbar.

    Delegiert an die kanonische ``group_cells.parse_group_cell`` (EINE Parse-Quelle
    fuer Paint, Member-Highlight, Persistenz UND alle Gruppen-fid-Resolver,
    FM16E-HEADCOUNT)."""
    from src.core.group_cells import parse_group_cell
    return parse_group_cell(v)


# ── Floating Panel (Rastergröße) ──────────────────────────────────────────────

# FM-HEADLAYOUT Slice 4: Pro-Fixture-Farben fuer die Rasterzellen. Vorher waren
# ALLE Zellen gleich blau — in einer zusammengelegten Kopf-Matrix (z. B. 2x
# Hydrabeam = 8 Kopf-Zellen) war nicht zu sehen, welche Zelle zu welchem Geraet
# gehoert. Davids Anforderung: "eine schoene UI, die klar anzeigt, welche Zellen
# zu welchem Fixture/Kopf gehoeren".
#
# Palette + Farbfunktion liegen seit dem Matrix-Nachzug in src/ui/head_cell_colors
# (EINE Quelle fuer Gruppen-Editor UND Matrix-Vorschau — zwei Paletten waeren die
# klassische Drift-Stelle). Hier nur re-exportiert, damit der eingefuehrte Name
# (und die Slice-4-Tests) unveraendert bleiben.
from src.ui.head_cell_colors import (           # noqa: E402  (bewusst nach den Qt-Importen)
    FIXTURE_CELL_COLORS as _FIXTURE_CELL_COLORS,
    fixture_cell_color,
    head_count_suffix,
    head_counts,
)


class _FloatingGridPanel(QFrame):
    """Schwebendes, ein-/ausklappbares, verschiebbares Panel für Rastergröße.

    Lebt als Kind-Widget des rechten Container-Widgets über dem Raster.
    """

    # Höhe geändert (auf-/zugeklappt) — der Besitzer muss den oben reservierten
    # Platz nachziehen, sonst deckt das Panel wieder eine Rasterzelle zu.
    size_changed = Signal()

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("floatingGridPanel")
        self.setStyleSheet("""
            #floatingGridPanel {
                background: #23232e;
                border: 1px solid #444;
                border-radius: 6px;
            }
        """)
        self._collapsed = False
        self._drag_start: QPoint | None = None
        self._panel_start: QPoint | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        self._header = QWidget()
        self._header.setFixedHeight(24)
        self._header.setStyleSheet("background: #2d2d3a; border-radius: 6px;")
        self._header.setCursor(Qt.CursorShape.SizeAllCursor)
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(6, 0, 4, 0)
        header_layout.setSpacing(4)

        lbl = QLabel("Rastergröße")
        lbl.setStyleSheet("color: #cccccc; font-size: 11px; font-weight: bold; background: transparent;")
        header_layout.addWidget(lbl, 1)

        self._btn_toggle = QPushButton("▾")
        self._btn_toggle.setFixedSize(18, 18)
        self._btn_toggle.setStyleSheet("""
            QPushButton { background: transparent; color: #aaa; border: none; font-size: 11px; }
            QPushButton:hover { color: #fff; }
        """)
        self._btn_toggle.clicked.connect(self._toggle_body)
        header_layout.addWidget(self._btn_toggle)

        layout.addWidget(self._header)

        # Body mit Spinboxen
        self._body = QWidget()
        body_layout = QFormLayout(self._body)
        body_layout.setContentsMargins(8, 6, 8, 6)
        body_layout.setSpacing(4)

        self.spin_cols = QSpinBox()
        self.spin_cols.setRange(1, 64)
        self.spin_cols.setValue(8)
        self.spin_rows = QSpinBox()
        self.spin_rows.setRange(1, 64)
        self.spin_rows.setValue(8)

        for sp in (self.spin_cols, self.spin_rows):
            sp.setStyleSheet("""
                QSpinBox { background: #1a1a26; color: #ddd;
                           border: 1px solid #555; border-radius: 3px; padding: 1px 3px; }
            """)

        body_layout.addRow(QLabel("Spalten:"), self.spin_cols)
        body_layout.addRow(QLabel("Zeilen:"), self.spin_rows)
        for lbl_w in self._body.findChildren(QLabel):
            lbl_w.setStyleSheet("color: #bbb; font-size: 11px;")

        layout.addWidget(self._body)
        self.adjustSize()

    def _toggle_body(self):
        self._collapsed = not self._collapsed
        self._body.setVisible(not self._collapsed)
        self._btn_toggle.setText("▸" if self._collapsed else "▾")
        self.adjustSize()
        self.size_changed.emit()

    # ── Drag to move ─────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint()
            self._panel_start = self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._drag_start
            new_pos = self._panel_start + delta
            if self.parent():
                pw, ph = self.parent().width(), self.parent().height()
                new_x = max(0, min(new_pos.x(), pw - self.width()))
                new_y = max(0, min(new_pos.y(), ph - self.height()))
                self.move(new_x, new_y)
            else:
                self.move(new_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start = None
        self._panel_start = None
        super().mouseReleaseEvent(event)


# ── Grid Widget ───────────────────────────────────────────────────────────────

class FixtureGridWidget(QWidget):
    """Custom widget that paints the 2D grid with placed fixtures.

    Accepts drops from the fixture tree (Mime type: application/x-fid).
    Also supports intra-grid drag: left-press on a filled cell starts an
    internal move; release on empty cell = move, release on other cell = swap.
    """

    positions_changed = Signal()
    # FM-20: Rechtsklick auf eine Rasterzelle. Das Widget MELDET nur (Spalte,
    # Zeile, Bildschirmpunkt) — gebaut wird das Menue von der View, die als
    # einzige an Geraetedaten und Undo kommt. Gleiche Aufteilung wie in der
    # Live-View (`context_menu_requested`), damit es nur EIN Muster gibt.
    cell_context_menu = Signal(int, int, QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cols = 8
        self.rows = 8
        self.positions: dict[tuple[int, int], "int | str"] = {}  # (col,row) -> fid ODER "fid:head" (FM-16e)
        self.setMinimumSize(320, 320)
        self.setAcceptDrops(True)
        self._labels: dict[int, str] = {}

        # Internal drag state
        self._drag_from: tuple[int, int] | None = None
        # Zell-WERT der laufenden internen Verschiebung: ganzes Fixture (int) ODER
        # Kopf-Zelle ("fid:head", str) — Kopf-Zellen sind seit FM-16e einzeln
        # verschieb-/tauschbar, die Annotation hinkte hinterher.
        self._drag_fid: "int | str | None" = None
        self._drag_current: tuple[int, int] | None = None  # for visual feedback
        # External drag state (from fixture tree): live "so rastet es ein"-Ziel.
        self._drop_target: tuple[int, int] | None = None

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

    def _cell_at(self, point: QPoint) -> tuple[int, int]:
        cw, ch = self.cell_size()
        col = int(point.x() // cw)
        row = int(point.y() // ch)
        return col, row

    def _cell_at_clamped(self, point: QPoint) -> tuple[int, int]:
        """Wie _cell_at, aber auf gueltige Zellen geklemmt — ein Drop knapp
        ueber den Raster-Rand landet dann in der Randzelle statt ins Leere."""
        col, row = self._cell_at(point)
        col = max(0, min(col, self.cols - 1))
        row = max(0, min(row, self.rows - 1))
        return col, row

    def _is_free(self, cell: tuple[int, int], ignore_fid: int | None,
                 achse: str | None = None) -> bool:
        """Zelle frei? ``ignore_fid`` zaehlt die EIGENEN Zellen dieses Geraets als
        frei — ein Drop ist immer ein MOVE, das Geraet darf sich nicht selbst
        blockieren (FM-HEADLAYOUT Slice 3: sonst scheitert das Zurueckziehen eines
        Multi-Head-Geraets auf ein kleines Raster, das seine eigenen Kopf-Zellen
        komplett fuellen — z. B. die 1×N-Auto-Kopf-Matrix).

        ★ FM-41: „eigen" heisst jetzt „eigen AUF DIESER ACHSE". Die Frage ist
        wortwoertlich dieselbe wie beim Aufraeumen in ``_drop_fid_cells`` —
        *welche Zellen gibt dieser Wurf frei?* — und wird deshalb an genau
        einer Stelle beantwortet: ``group_cells.zelle_gehoert_zu``. Zwei
        Fassungen davon waeren Review-Checkliste 17, und dann laufen Highlight
        und echte Platzierung auseinander."""
        v = self.positions.get(cell)
        if v is None:
            return True
        return (ignore_fid is not None
                and zelle_gehoert_zu(v, ignore_fid, achse))

    def _nearest_free_cell(self, col: int, row: int,
                           ignore_fid: int | None = None,
                           achse: str | None = None) -> tuple[int, int] | None:
        """Naechste freie Zelle zu (col,row). (col,row) selbst, wenn frei; sonst
        die per Manhattan-Distanz naechste (Tie-Break row-major). None, wenn das
        Raster komplett voll ist. So wird beim Drop nie still ueberschrieben.
        ``ignore_fid`` s. ``_is_free``."""
        if (0 <= col < self.cols and 0 <= row < self.rows
                and self._is_free((col, row), ignore_fid, achse)):
            return (col, row)
        best_key = None
        best_cell = None
        for r in range(self.rows):
            for c in range(self.cols):
                if not self._is_free((c, r), ignore_fid, achse):
                    continue
                key = (abs(c - col) + abs(r - row), r, c)
                if best_key is None or key < best_key:
                    best_key, best_cell = key, (c, r)
        return best_cell

    def resolve_drop_cell(self, fid: int | None, col: int, row: int,
                          achse: str | None = None) -> tuple[int, int] | None:
        """Zielzelle fuer einen externen Drop bestimmen (identisch fuer Highlight
        und echten Drop). Liegt fid schon an (col,row) -> genau dort (No-Op);
        ist die Zelle von einem ANDEREN fid belegt -> naechste freie Zelle. Eigene
        Zellen (auch Kopf-Zellen) gelten als frei, weil der Drop sie ohnehin
        freigibt — Highlight und echte Platzierung bleiben so deckungsgleich."""
        col = max(0, min(col, self.cols - 1))
        row = max(0, min(row, self.rows - 1))
        if self.positions.get((col, row)) == fid and fid is not None:
            return (col, row)
        return self._nearest_free_cell(col, row, ignore_fid=fid, achse=achse)

    def place_fixture(self, fid: int, col: int, row: int) -> tuple[int, int] | None:
        """Platziert fid an/nahe (col,row) und gibt die tatsaechliche Zelle zurueck.
        Belegte Zielzelle -> naechste freie (kein stilles Ueberschreiben). Raster
        voll -> None (nichts wird zerstoert). Move-Semantik: eine evtl. vorherige
        Platzierung desselben fid wird freigegeben."""
        target = self.resolve_drop_cell(fid, col, row)
        if target is None:
            return None
        if self.positions.get(target) == fid:
            return target  # steht schon dort
        # alte Platzierung dieses fid entfernen (Move statt Duplikat). FM-16e:
        # per Basis-fid vergleichen -> ein extern gedroptetes ganzes Fixture räumt
        # auch etwaige Kopf-Zellen ("fid:head") desselben fid weg (kein Doppel).
        #
        # ★ FM-41: hier stand dieselbe Zeile wie in ``_drop_fid_cells`` noch
        # einmal ausgeschrieben. Jetzt der Aufruf — ein ganzes Geraet raeumt
        # BEIDE Achsen (``achse=None``), sonst bliebe ein Weiss-Segment als
        # Waise stehen und das Geraet staende doppelt im Raster.
        self._drop_fid_cells(fid)
        self.positions[target] = fid
        return target

    def _drop_fid_cells(self, fid: int, achse: str | None = None):
        """Zellen dieses Basis-fid entfernen. Gemeinsame Move-Semantik von
        ``place_fixture``/``place_fixture_heads``: ein Gerät steht nie doppelt
        im Raster.

        ``achse=None`` (Vorgabe) räumt **alles** — ganzes Fixture, Farb-Köpfe
        UND Weiß-Segmente. Das ist die Lesart des Menüpunkts „Alle Zellen von X
        entfernen"; gemessen ließ er vor FM-41 Weiß-Zellen als Waisen stehen,
        weil der verlustbehaftete ``parse_group_cell`` sie gar nicht als zu
        diesem Gerät gehörig erkennt.

        Mit einer Achse räumt er nur diese eine (plus die achsenlose
        Ganz-Geräte-Zelle) — die Voraussetzung dafür, dass RGB-Zonen und
        Weiß-Segmente **nebeneinander** im Raster liegen können."""
        self.positions = {k: v for k, v in self.positions.items()
                          if not zelle_gehoert_zu(v, fid, achse)}

    def place_fixture_heads(self, fid: int, count: int,
                            col: int | None = None, row: int | None = None,
                            *, vertical: bool = False) -> list[tuple[int, int]]:
        """Die Farb-Achse — der eingefuehrte Name, unveraendert im Verhalten.

        Seit FM-41 die duenne Fassung von :meth:`place_fixture_axis`. Alle
        Aufrufstellen und die Slice-3-Tests bleiben, wie sie sind; was frueher
        „die Koepfe" hiess, ist jetzt ausgesprochen „die Koepfe der Farb-Achse".
        """
        return self.place_fixture_axis(fid, ACHSE_FARBE, count, col, row,
                                       vertical=vertical)

    def place_fixture_axis(self, fid: int, achse: str, count: int,
                           col: int | None = None, row: int | None = None,
                           *, vertical: bool = False) -> list[tuple[int, int]]:
        """FM-HEADLAYOUT Slice 3: setzt die ``count`` Köpfe eines Multi-Head-
        Fixtures als EINZELNE Zellen (``"fid:head"``) ab — **waagerecht** (Zeile)
        oder **hochkant** (Spalte, ``vertical=True``). Davids Kernwunsch: die Köpfe
        einer Hydrabeam/Spider-Bar so anordnen, wie sie am Rig wirklich hängen.

        Regeln (bewusst dieselben wie beim externen Drop):
        * **Zusammenhängend, wenn möglich:** passt der Streifen ab (col,row) nicht
          mehr ins Raster, wird der START so weit zurückgeschoben, dass er
          hineinpasst (statt hinten abzuschneiden).
        * **Kein stilles Überschreiben:** eine von einem ANDEREN Gerät belegte
          Zelle wird nicht überschrieben — dieser Kopf weicht auf die nächste
          freie Zelle aus (``_nearest_free_cell``). Ist das Raster voll, bleiben
          die restlichen Köpfe ungesetzt (nichts wird zerstört).
        * **Move statt Duplikat:** vorherige Platzierungen desselben fid (ganzes
          Fixture ODER alte Kopf-Zellen) werden vorher freigegeben.

        ``col``/``row`` weggelassen = „such dir die erste freie Zelle" — und zwar
        NACH dem Freigeben der eigenen Zellen, sonst weicht ein Gerät, das schon
        kopfweise im Raster steht, unnötig hinter sich selbst aus. Das Raster wächst
        hier NICHT (Spalten/Reihen gehören der Gruppe, nicht dem Widget) — der
        Aufrufer vergrößert vorher, wenn der Streifen sonst nicht hineinpasst.

        Rückgabe: die tatsächlich belegten Zellen in Kopf-Reihenfolge (leer, wenn
        nichts platziert werden konnte).

        ★ FM-41: ``achse`` sagt, WELCHER Satz ausgelegt wird — die Farb-Zonen
        (``ACHSE_FARBE``, das bisherige Verhalten, Zellwerte byte-gleich) oder
        die eigenen Weiß-Segmente (``ACHSE_WEISS``). Beide Sätze dürfen
        gleichzeitig im Raster liegen; das Auslegen des einen räumt den anderen
        nicht weg. Genau das ist der Zweck von FM-41: eine Gruppe aus Weiß, aus
        RGB oder aus beidem."""
        try:
            count = int(count)
        except (TypeError, ValueError):
            return []
        if count < 1:
            return []
        # ★ FM-41: NUR die Farb-Achse. Wer die RGB-Zonen eines Geraets
        # neu auslegt, raeumt damit nicht dessen Weiss-Segmente weg — sie
        # sind der zweite, eigenstaendige Satz. Die achsenlose
        # Ganz-Geraet-Zelle geht mit, sonst staende es doppelt.
        self._drop_fid_cells(fid, achse)
        if col is None or row is None:
            _free = self.first_free_cells(1)
            want_c, want_r = _free[0] if _free else (0, 0)
        else:
            want_c, want_r = int(col), int(row)
        limit = self.rows if vertical else self.cols
        start_c = max(0, min(want_c, self.cols - 1))
        start_r = max(0, min(want_r, self.rows - 1))
        # Streifen zusammenhängend halten: Start zurückschieben, wenn er sonst
        # über den Rand läuft (nur soweit das Raster überhaupt lang genug ist).
        if count <= limit:
            if vertical:
                start_r = min(start_r, self.rows - count)
            else:
                start_c = min(start_c, self.cols - count)
        placed: list[tuple[int, int]] = []
        for h in range(count):
            c = start_c + (0 if vertical else h)
            r = start_r + (h if vertical else 0)
            if not (0 <= c < self.cols and 0 <= r < self.rows) or (c, r) in self.positions:
                cell = self._nearest_free_cell(c, r)
            else:
                cell = (c, r)
            if cell is None:
                break               # Raster voll -> Rest bleibt ungesetzt
            # ★ FM-41: ueber `zelle_fuer`, nicht per f-String. Hier stand die
            # zweite Stelle im Baum, an der ein Zellwert ENTSTEHT — genau die,
            # vor der `zelle_fuer` warnt. Fuer die Farb-Achse byte-gleich.
            self.positions[cell] = zelle_fuer(fid, achse, h)
            placed.append(cell)
        return placed

    def contextMenuEvent(self, event):
        """Rechtsklick auf eine Zelle -> die View baut das Menue (FM-20).

        Bewusst ueber ``contextMenuEvent`` und nicht im ``mousePressEvent``:
        so kommt das Menue auch ueber die Kontextmenue-Taste der Tastatur und
        auf Plattformen, die es anders ausloesen.
        """
        col, row = self._cell_at(event.pos())
        if not (0 <= col < self.cols and 0 <= row < self.rows):
            return
        self.cell_context_menu.emit(col, row, event.globalPos())
        event.accept()

    def remove_cell(self, col: int, row: int) -> bool:
        """Eine einzelne Zelle leeren. Rueckgabe: ob dort etwas war."""
        if (col, row) not in self.positions:
            return False
        del self.positions[(col, row)]
        return True

    def place_fixture_block(self, fid: int, count: int, block_cols: int,
                            col: int | None = None, row: int | None = None,
                            achse: str = ACHSE_FARBE,
                            *, order: str = "rowwise",
                            rotation: int = 0, flip: bool = False
                            ) -> list[tuple[int, int]]:
        """FM-20: setzt die ``count`` Köpfe als RECHTECK ab statt als Streifen.

        Der Streifen (``place_fixture_heads``) ist die richtige Form für eine
        Bar — für ein Panel ist er falsch. Davids ZQ06121 hat 48 Zonen in 4
        Reihen à 12; als 1×48-Streifen läuft darauf jeder Flächeneffekt als
        Linie, und von Hand sind es 48 Zieh-Vorgänge.

        ★ HIER wird ``pixel_order`` zum ersten Mal ausserhalb der 3D-Vorschau
        wirksam. `place_element` verrechnet beides in einem Schritt: wie das
        GERÄT nummeriert (Werkszustand/Schlangenlinie) und wie es HÄNGT
        (Montage-Drehung, FM-ORIENT). Ein Panel, das ab Werk in Schlangenlinien
        zählt und hochkant montiert ist, landet damit ohne Handarbeit richtig
        im Raster — genau die Verbindung, die in FM-21 als fehlend notiert ist.

        ``block_cols`` ist die Breite des Blocks VOR der Drehung. Bei 90°/270°
        tauschen Zeilen und Spalten die Rollen, der belegte Bereich ist dann
        entsprechend hoch statt breit; die tatsächlichen Maße kommen deshalb aus
        `place_element` selbst und werden nicht danebenher gerechnet (FM16E:
        genau daran laufen zwei Fassungen auseinander).

        Regeln bewusst identisch zu ``place_fixture_heads``: eigene Zellen
        zuerst freigeben (Move statt Duplikat), Block zusammenhängend halten
        indem der Start zurückgeschoben wird, kein stilles Überschreiben
        (Ausweichen auf die nächste freie Zelle), bei vollem Raster bleibt der
        Rest ungesetzt statt etwas zu zerstören.

        Rückgabe: die belegten Zellen in Kopf-Reihenfolge.
        """
        from src.core.pixel_order import place_element
        try:
            count = int(count)
            block_cols = int(block_cols)
        except (TypeError, ValueError):
            return []
        if count < 1 or block_cols < 1:
            return []
        block_rows = (count + block_cols - 1) // block_cols

        # Maße NACH der Drehung aus derselben Quelle holen, die auch die Zellen
        # rechnet — sonst driften Vorab-Klemmung und tatsächliche Belegung.
        _r0, _c0, eff_rows, eff_cols = place_element(
            0, block_cols, block_rows, order, rotation, flip)

        # ★ FM-41: NUR die Farb-Achse. Wer die RGB-Zonen eines Geraets
        # neu auslegt, raeumt damit nicht dessen Weiss-Segmente weg — sie
        # sind der zweite, eigenstaendige Satz. Die achsenlose
        # Ganz-Geraet-Zelle geht mit, sonst staende es doppelt.
        self._drop_fid_cells(fid, achse)
        if col is None or row is None:
            _free = self.first_free_cells(1)
            want_c, want_r = _free[0] if _free else (0, 0)
        else:
            want_c, want_r = int(col), int(row)
        start_c = max(0, min(want_c, self.cols - 1))
        start_r = max(0, min(want_r, self.rows - 1))
        if eff_cols <= self.cols:
            start_c = min(start_c, self.cols - eff_cols)
        if eff_rows <= self.rows:
            start_r = min(start_r, self.rows - eff_rows)

        placed: list[tuple[int, int]] = []
        for h in range(count):
            rr, cc, _nr, _nc = place_element(
                h, block_cols, block_rows, order, rotation, flip)
            c = start_c + cc
            r = start_r + rr
            if not (0 <= c < self.cols and 0 <= r < self.rows) or (c, r) in self.positions:
                cell = self._nearest_free_cell(c, r)
            else:
                cell = (c, r)
            if cell is None:
                break               # Raster voll -> Rest bleibt ungesetzt
            # ★ FM-41: ueber `zelle_fuer`, nicht per f-String. Hier stand die
            # zweite Stelle im Baum, an der ein Zellwert ENTSTEHT — genau die,
            # vor der `zelle_fuer` warnt. Fuer die Farb-Achse byte-gleich.
            self.positions[cell] = zelle_fuer(fid, achse, h)
            placed.append(cell)
        return placed

    def collapse_fixture_heads(self, fid: int) -> tuple[int, int] | None:
        """Gegenstück zu ``place_fixture_heads``: die Kopf-Zellen dieses fid durch
        EINE Ganz-Fixture-Zelle ersetzen (an der ersten bisherigen Kopf-Zelle in
        Raster-Reihenfolge). Rückgabe: die belegte Zelle, oder ``None``, wenn das
        fid gar nicht kopfweise im Raster steht (dann bleibt alles unverändert).

        ★ FM-41: „kopfweise" heisst auf JEDER Achse. Über ``_split_cell`` waren
        Weiß-Segmente unsichtbar — ein Gerät, das nur in Weiß-Segmenten im
        Raster stand, galt als „gar nicht kopfweise da" und ließ sich nicht
        zusammenfalten. Das Zusammenfalten selbst räumt danach beide Achsen
        (``achse=None``), denn eine Ganz-Zelle meint das ganze Gerät."""
        head_cells = []
        for (c, r), v in self.positions.items():
            base, achse, index = parse_zelle(v)
            if base == fid and achse is not None:
                head_cells.append((r, c))       # Raster-Reihenfolge: Zeile, Spalte
        head_cells.sort()
        if not head_cells:
            return None
        first = (head_cells[0][1], head_cells[0][0])   # (col,row)
        self._drop_fid_cells(fid)
        self.positions[first] = fid
        return first

    def first_free_cells(self, count: int) -> list[tuple[int, int]]:
        """Liefert `count` freie Zellen in row-major Reihenfolge; erweitert die
        Reihen bei Bedarf virtuell nach unten. Platziert selbst nichts."""
        out: list[tuple[int, int]] = []
        occupied = set(self.positions.keys())
        r = 0
        while len(out) < count:
            for c in range(self.cols):
                if (c, r) not in occupied:
                    out.append((c, r))
                    occupied.add((c, r))
                    if len(out) >= count:
                        break
            r += 1
        return out

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

        font = QFont("Segoe UI", 9)
        font.setBold(True)
        p.setFont(font)

        # FM-HEADLAYOUT Slice 4: Farbton je Geraet, Helligkeit je Kopf. Reihenfolge
        # EINMAL pro Paint bestimmen (nicht je Zelle) — dieselbe Quelle wie alle
        # anderen Gruppen-fid-Resolver (group_cells), damit die Farbzuordnung nicht
        # von der dict-Reihenfolge abhaengt.
        # ★ FM-41: fuer die ANZEIGE zaehlt „kommt vor", nicht „wird gefahren" —
        # ein Geraet, das nur mit Weiss-Zellen im Raster steht, muss man sehen
        # und benennen koennen. (Die Trennung der beiden Lesarten steht in
        # `group_cells.referenzierte_fids`.)
        fid_order = referenzierte_fids_in_grid_order(
            {f"{c},{r}": v for (c, r), v in self.positions.items()})
        for (c, r), v in self.positions.items():
            fid, achse, index = parse_zelle(v)
            head = index if achse == ACHSE_FARBE else None
            x = c * cw
            y = r * ch
            rect = (int(x) + 2, int(y) + 2, int(cw) - 4, int(ch) - 4)
            # Highlight the cell being dragged internally
            if self._drag_from and (c, r) == self._drag_from:
                fill_color = QColor("#ff8c00")
            else:
                fill_color = fixture_cell_color(
                    fid, index if achse else head, fid_order, achse)
            p.fillRect(rect[0], rect[1], rect[2], rect[3], QBrush(fill_color))
            p.setPen(QColor("#ffffff"))
            p.setFont(font)
            # FM-16e: Kopf-Zelle als "fid·K{head+1}" (1-basiert), ganzes Fixture
            # als fid. FM-41: Weiss-Segment als "fid·W{n+1}" — eigener Buchstabe,
            # damit Kopf 3 und Weiss-Segment 3 nicht gleich aussehen.
            if fid is None:
                big = str(v)
            elif achse == ACHSE_WEISS and index is not None:
                big = f"{fid}·W{index + 1}"
            elif head is not None:
                big = f"{fid}·K{head + 1}"
            else:
                big = f"{fid}"
            p.drawText(rect[0], rect[1], rect[2], rect[3],
                       Qt.AlignmentFlag.AlignCenter, big)
            label = self._labels.get(fid, str(fid if fid is not None else v))
            small = QFont("Segoe UI", 7)
            p.setFont(small)
            p.drawText(rect[0], rect[1] + 14, rect[2], rect[3] - 14,
                       Qt.AlignmentFlag.AlignCenter, label[:8])

        # Visual feedback: highlight drop target during internal drag
        if self._drag_from is not None and self._drag_current is not None:
            tc, tr = self._drag_current
            if (tc, tr) != self._drag_from and 0 <= tc < self.cols and 0 <= tr < self.rows:
                tx = int(tc * cw) + 2
                ty = int(tr * ch) + 2
                tw = int(cw) - 4
                th_ = int(ch) - 4
                p.fillRect(tx, ty, tw, th_, QBrush(QColor(255, 140, 0, 80)))
                p.setPen(QPen(QColor("#ff8c00"), 2))
                p.drawRect(tx, ty, tw, th_)

        # Visual feedback: highlight the cell an EXTERNAL drop will snap into
        # (gruen = frei, hier landet es wirklich). Macht das "Einrasten" sichtbar.
        if self._drop_target is not None:
            dc, dr = self._drop_target
            if 0 <= dc < self.cols and 0 <= dr < self.rows:
                dx = int(dc * cw) + 2
                dy = int(dr * ch) + 2
                dw = int(cw) - 4
                dh = int(ch) - 4
                p.fillRect(dx, dy, dw, dh, QBrush(QColor(34, 204, 102, 90)))
                p.setPen(QPen(QColor("#22cc66"), 3))
                p.drawRect(dx, dy, dw, dh)

        p.end()

    # ── External Drag & Drop (from fixture tree) ──────────────────────────────

    @staticmethod
    def _mime_fid(event) -> int | None:
        md = event.mimeData()
        if not md.hasFormat("application/x-fid"):
            return None
        try:
            return int(bytes(md.data("application/x-fid")).decode())
        except Exception:
            return None

    @staticmethod
    def _event_point(event) -> QPoint:
        return event.position().toPoint() if hasattr(event, "position") else event.pos()

    def _update_drop_target(self, event):
        """Ziel-Highlight live nachziehen (zeigt exakt, wohin der Drop einrastet)."""
        fid = self._mime_fid(event)
        col, row = self._cell_at(self._event_point(event))
        self._drop_target = self.resolve_drop_cell(fid, col, row)
        self.update()

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-fid"):
            self._update_drop_target(event)
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-fid"):
            self._update_drop_target(event)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._drop_target = None
        self.update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        fid = self._mime_fid(event)
        self._drop_target = None
        if fid is None:
            self.update()
            return
        col, row = self._cell_at(self._event_point(event))
        # place_fixture klemmt auf gueltige Zellen und weicht belegten Zellen auf
        # die naechste FREIE aus (kein stilles Ueberschreiben, Rand-Drop landet).
        target = self.place_fixture(fid, col, row)
        self.update()
        event.acceptProposedAction()
        if target is not None:
            self.positions_changed.emit()

    # ── Internal Drag (cell → cell: move or swap) ─────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            # FM-20: Rechtsklick loeschte die Zelle bis 2026-08-05 SOFORT und
            # ohne Nachfrage — die einzige Rechtsklick-Aktion im ganzen Raster.
            # Jetzt oeffnet er ein Menue (contextMenuEvent), „Zelle entfernen"
            # ist dort der erste Eintrag. Hier bleibt nur das Verschlucken des
            # Klicks, damit er nicht in den Links-Drag-Pfad darunter faellt.
            return

        if event.button() == Qt.MouseButton.LeftButton:
            col, row = self._cell_at(event.position().toPoint())
            if (col, row) in self.positions:
                # Start internal drag
                self._drag_from = (col, row)
                self._drag_fid = self.positions[(col, row)]
                self._drag_current = (col, row)
                self.update()

    def mouseMoveEvent(self, event):
        if self._drag_from is not None and event.buttons() & Qt.MouseButton.LeftButton:
            col, row = self._cell_at(event.position().toPoint())
            self._drag_current = (col, row)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_from is not None:
            col, row = self._cell_at(event.position().toPoint())
            src = self._drag_from
            fid = self._drag_fid

            changed = False
            if (col, row) != src and 0 <= col < self.cols and 0 <= row < self.rows:
                if (col, row) not in self.positions:
                    # Move to empty cell
                    del self.positions[src]
                    self.positions[(col, row)] = fid
                    changed = True
                else:
                    # Swap with existing fixture
                    other_fid = self.positions[(col, row)]
                    self.positions[src] = other_fid
                    self.positions[(col, row)] = fid
                    changed = True

            self._drag_from = None
            self._drag_fid = None
            self._drag_current = None
            self.update()
            if changed:
                self.positions_changed.emit()


# ── Fixture Tree with Drag ────────────────────────────────────────────────────

class FixtureTreeWithDrag(QTreeWidget):
    """QTreeWidget mit Universe-Ordnern als Top-Level-Items.

    Kind-Items (Fixtures) sind draggbar via Mime 'application/x-fid'.
    Top-Level-Universe-Items sind NICHT draggbar.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        # QOL-03: laenger Namen mittig kuerzen (statt rechts) — so bleibt der
        # unterscheidende Namens-Schwanz sichtbar (`[013] PAR …RGBW` statt
        # `[013] PAR T…`); der Vollname haengt zusaetzlich im Tooltip.
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.setDragEnabled(True)
        self.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.setStyleSheet("""
            QTreeWidget {
                background: #1a1a26;
                color: #cccccc;
                border: 1px solid #333;
                border-radius: 4px;
            }
            QTreeWidget::item:hover { background: #2a2a3a; }
            QTreeWidget::item:selected { background: #0978FF; color: #fff; }
        """)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item:
            return
        # Only child items (fixtures) are draggable — top-level = universe
        if item.parent() is None:
            return
        fid = item.data(0, Qt.ItemDataRole.UserRole)
        if fid is None:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-fid", str(fid).encode())
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)


# ── Group View ────────────────────────────────────────────────────────────────

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
            # Gruppe anderswo erstellt/geaendert (Live View, …) -> Liste auffrischen.
            sync.subscribe(SyncEvent.GROUP_CHANGED, lambda *_: self._reload_group_list())
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

        # ── Left: group selector + fixture tree ───────────────────────────
        left = QVBoxLayout()

        grp_row = QHBoxLayout()
        grp_row.addWidget(QLabel("Gruppe:"))
        self._combo_group = QComboBox()
        self._combo_group.currentIndexChanged.connect(self._on_group_selected)
        grp_row.addWidget(self._combo_group, 1)
        left.addLayout(grp_row)

        # B-07-Fix: 6 Buttons in ein 2-spaltiges Grid (3 Reihen) statt in EINE
        # HBox-Reihe. Im schmalen (260px), touch-grossen Panel wurde jeder Button
        # sonst nur ~43px breit -> die Labels wurden zu unleserlichen Fragmenten
        # beschnitten. 2 Spalten verdoppeln die Button-Breite -> Text lesbar.
        btns = QGridLayout()
        b_new = QPushButton("+ Neu")
        b_new.clicked.connect(self._new_group)
        btns.addWidget(b_new, 0, 0)
        b_rename = QPushButton("Umbenennen")
        b_rename.setToolTip("Name der ausgewählten Gruppe ändern")
        b_rename.clicked.connect(self._rename_group)
        btns.addWidget(b_rename, 0, 1)
        b_edit = QPushButton("Bearbeiten…")
        b_edit.setToolTip("Mitglieder, Name und Reihenfolge der Gruppe ändern "
                          "(touch-tauglich, ohne Drag&Drop)")
        b_edit.clicked.connect(self._edit_group)
        btns.addWidget(b_edit, 1, 0)
        b_del = QPushButton("Löschen")
        b_del.setObjectName("btn_danger")
        b_del.clicked.connect(self._delete_group)
        btns.addWidget(b_del, 1, 1)
        b_save = QPushButton("Speichern")
        b_save.clicked.connect(self._save_group)
        btns.addWidget(b_save, 2, 0)
        b_folder = QPushButton("Ordner…")
        b_folder.setToolTip("Gruppe einem (verschachtelten) Ordner zuordnen — z. B. Front/Wash")
        b_folder.clicked.connect(self._set_group_folder)
        btns.addWidget(b_folder, 2, 1)
        b_merge = QPushButton("⧉ Matrizen zusammenlegen…")
        b_merge.setToolTip("Mehrere (Kopf-)Matrix-Gruppen zu EINER größeren Matrix "
                           "stapeln — z. B. 2× Hydrabeam (je 1×4 Köpfe) → eine 4×2-"
                           "Matrix. Kopf-Zellen bleiben pro Kopf ansprechbar; die "
                           "Quell-Gruppen bleiben erhalten (FM-16).")
        b_merge.clicked.connect(self._merge_groups)
        btns.addWidget(b_merge, 3, 0, 1, 2)
        left.addLayout(btns)

        # Fixture tree (Universe-Ordner)
        left.addWidget(QLabel("Fixtures (drag auf Raster):"))
        self._fixture_list = FixtureTreeWithDrag()
        left.addWidget(self._fixture_list, 1)

        # FM-HEADLAYOUT Slice 3: Köpfe eines Multi-Head-Geräts als EINZELNE Zellen
        # ins Raster — mit Orientierung, damit das Raster dem realen Rig-Aufbau
        # folgen kann (Hydrabeam hochkant vs. Spider-Bar waagerecht).
        # ★★ FM-41: DASSELBE Menü zweimal — einmal für die Farb-Zonen, einmal
        # für die eigenen Weiß-Segmente. Robins Bild dazu: ein Gerät mit eigener
        # Weiß-Leiste hat zwei „Hauptfixtures", aus denen sich Gruppen bauen
        # lassen — nur RGB, nur Weiß, oder beides zusammen. Deshalb eine
        # FABRIK und keine Kopie: eine zweite, von Hand gepflegte Menü-Fassung
        # wäre wieder die Doppelstellen-Klasse (Checkliste 17), und die beiden
        # liefen beim nächsten Eintrag auseinander.
        self._acts_hinterlegt: dict[str, object] = {}
        self._btn_achse: dict[str, QPushButton] = {}
        for _achse, _titel, _hilfe in (
            (ACHSE_FARBE, "Köpfe einzeln → Raster ▾",
             "Setzt die Köpfe des im Baum gewählten Mehrkopf-Geräts als einzelne "
             "Zellen ins Raster (waagerecht oder hochkant) — so ansprechbar wie "
             "eine Pro-Kopf-Matrix.\n"
             "Die Köpfe lassen sich danach frei einzeln verschieben/tauschen "
             "(Drag) und einzeln entfernen (Rechtsklick).\n"
             "Unabhängig von der Auto-Anlage beim Patchen: hier bestimmst du die "
             "Anordnung von Hand."),
            (ACHSE_WEISS, "Weiß-Segmente einzeln → Raster ▾",
             "Setzt die EIGENEN Weiß-Segmente des gewählten Geräts als einzelne "
             "Zellen ins Raster — unabhängig von seinen Farb-Zonen.\n"
             "Beide Sätze dürfen gleichzeitig im Raster liegen: so entsteht eine "
             "Gruppe nur aus Weiß, nur aus RGB, oder aus beidem.\n"
             "Nur aktiv, wenn das Gerät eigene Weiß-Kanäle hat (color_w) — die "
             "Zahl steht im Fixture-Profil, sie wird nicht geraten."),
        ):
            _btn = QPushButton(_titel)
            _btn.setToolTip(_hilfe)
            _menu = QMenu(_btn)
            # FM-40: die im Gerät hinterlegte Form steht OBEN — sie ist die
            # einzige Anordnung, die nicht geraten ist, und damit fast immer die
            # gesuchte. Beschriftung/Verfügbarkeit werden beim Aufklappen
            # nachgezogen (`_heads_menu_aktualisieren`), weil sie am gewählten
            # Gerät hängen und nicht am Menü.
            _act_h = _menu.addAction("wie im Gerät hinterlegt")
            _act_h.triggered.connect(
                lambda _c=False, a=_achse: self._place_heads_hinterlegt(achse=a))
            self._acts_hinterlegt[_achse] = _act_h
            _menu.addSeparator()
            _menu.aboutToShow.connect(
                lambda a=_achse: self._heads_menu_aktualisieren(a))
            _act_row = _menu.addAction("als Zeile (waagerecht)")
            _act_row.triggered.connect(
                lambda _c=False, a=_achse: self._place_heads(vertical=False, achse=a))
            _act_col = _menu.addAction("als Spalte (hochkant)")
            _act_col.triggered.connect(
                lambda _c=False, a=_achse: self._place_heads(vertical=True, achse=a))
            _menu.addSeparator()
            # Zusammenfassen gilt fuer das GANZE Geraet (beide Achsen) und steht
            # deshalb nur einmal im Farb-Menue — zweimal derselbe Eintrag mit
            # derselben Wirkung waere irrefuehrend.
            if _achse == ACHSE_FARBE:
                _act_one = _menu.addAction("Köpfe zusammenfassen (eine Zelle)")
                _act_one.triggered.connect(self._collapse_heads)
            _btn.setMenu(_menu)
            left.addWidget(_btn)
            self._btn_achse[_achse] = _btn
        # Eingefuehrter Name der Farb-Fassung — Tests und aeltere Aufrufer
        # kennen ihn, und er meint weiterhin genau dasselbe Menue.
        self._btn_heads = self._btn_achse[ACHSE_FARBE]
        self._act_hinterlegt = self._acts_hinterlegt[ACHSE_FARBE]

        btn_all = QPushButton("Alle → Raster")
        btn_all.setToolTip("Alle gepatchten Fixtures ins Raster übernehmen "
                           "(freie Zellen zuerst, Reihen wachsen bei Bedarf; "
                           "bereits platzierte bleiben). Danach Speichern nicht vergessen.")
        btn_all.clicked.connect(self._add_all_fixtures)
        left.addWidget(btn_all)

        btn_refresh = QPushButton("Fixtures neu laden")
        btn_refresh.clicked.connect(self._refresh_fixtures)
        left.addWidget(btn_refresh)

        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(260)
        root.addWidget(left_w)

        # ── Right: container with grid + floating panel ───────────────────
        right_w = QWidget()
        right_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(right_w, 1)

        right_inner = QVBoxLayout(right_w)
        right_inner.setContentsMargins(0, 0, 0, 0)
        # FGRP-PANEL-OVERLAP: Das schwebende „Rastergröße"-Panel sitzt oben
        # rechts ÜBER diesem Container und verdeckte damit die oberste rechte
        # Rasterzelle samt Label. Statt das Panel zu verschieben (es soll dort
        # bleiben, wo man es sucht) reservieren wir seine Höhe hier oben — dann
        # beginnt das Raster darunter und keine Zelle liegt mehr dahinter.
        # Die Höhe zieht `_reposition_float_panel` nach, auch beim Zuklappen.
        self._panel_reserve = QWidget()
        self._panel_reserve.setFixedHeight(0)
        right_inner.addWidget(self._panel_reserve)
        right_inner.addWidget(
            QLabel("Raster (Drag&Drop für Platzierung, Rechtsklick zum Entfernen):"))

        self._grid_widget = FixtureGridWidget(right_w)
        self._grid_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right_inner.addWidget(self._grid_widget, 1)

        # FM-HEADLAYOUT Slice 4: Legende „Farbe -> Gerät" unter dem Raster. Die
        # Zellfarbe allein ist ein Hinweis, keine Zuordnung — erst die Legende macht
        # sie eindeutig (Davids „klar anzeigen, welche Zellen zu welchem Fixture/Kopf
        # gehören"). Leer = versteckt, damit sie in Ein-Geräte-Gruppen nicht stört.
        self._legend = QLabel("")
        self._legend.setWordWrap(True)
        self._legend.setTextFormat(Qt.TextFormat.RichText)
        self._legend.setToolTip(
            "Farbton = Gerät, Helligkeit = Kopf (K1 dunkel → höhere Köpfe heller).")
        self._legend.hide()
        right_inner.addWidget(self._legend)

        # Schwebende Rastergröße-Panel (Kind von right_w, schwebt über dem Grid)
        self._float_panel = _FloatingGridPanel(right_w)
        # Spinbox-Referenzen auf Attributnamen, die _apply_grid_size/_save_group/_load_group nutzen
        self._spin_cols = self._float_panel.spin_cols
        self._spin_rows = self._float_panel.spin_rows
        self._spin_cols.valueChanged.connect(self._apply_grid_size)
        self._spin_rows.valueChanged.connect(self._apply_grid_size)
        # Zuklappen gibt den reservierten Platz sofort wieder frei.
        self._float_panel.size_changed.connect(self._reposition_float_panel)

        # Signal: Raster-Änderungen → Hervorhebung aktualisieren
        self._grid_widget.positions_changed.connect(self._highlight_group_members)
        # FM-20: Rechtsklick auf eine Zelle → Kontextmenü (siehe _on_cell_menu)
        self._grid_widget.cell_context_menu.connect(self._on_cell_menu)

        self._refresh_fixtures()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_float_panel()

    def showEvent(self, event):
        super().showEvent(event)
        self._reposition_float_panel()

    _PANEL_TOP = 8       # Abstand des Panels zur Oberkante
    _PANEL_GAP = 6       # Luft zwischen Panel-Unterkante und Raster

    def _reposition_float_panel(self):
        """Floating Panel oben rechts im right_w positionieren — und oben genau
        so viel Platz reservieren, dass es keine Rasterzelle verdeckt."""
        panel = self._float_panel
        parent = panel.parent()
        if parent is None:
            return
        panel.adjustSize()
        pw = parent.width()
        x = max(0, pw - panel.width() - 8)
        panel.move(x, self._PANEL_TOP)
        panel.raise_()
        reserve = getattr(self, "_panel_reserve", None)
        if reserve is not None:
            need = self._PANEL_TOP + panel.height() + self._PANEL_GAP
            if reserve.height() != need:
                reserve.setFixedHeight(need)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _session(self) -> Session | None:
        eng = getattr(self._state, "_show_engine", None)
        if eng is None:
            return None
        return Session(eng)

    def _refresh_fixtures(self):
        """Baut den Universe-Baum neu auf und aktualisiert Grid-Labels."""
        labels: dict[int, str] = {}
        fixtures = self._state.get_patched_fixtures()

        # Gruppiere nach Universe
        by_universe: dict[int, list] = {}
        for f in fixtures:
            by_universe.setdefault(f.universe, []).append(f)
        for uni_list in by_universe.values():
            uni_list.sort(key=lambda fx: fx.address)

        self._fixture_list.clear()
        for uni_num in sorted(by_universe.keys()):
            uni_item = QTreeWidgetItem(self._fixture_list, [f"Universe {uni_num}"])
            uni_item.setFlags(uni_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            uni_item.setIcon(0, _mini.folder_icon())
            uni_item.setExpanded(True)
            for f in by_universe[uni_num]:
                # Konstruktor mit uni_item als Parent hängt das Kind bereits ein
                # (kein zusätzliches addChild → sonst qWarning "already owned").
                _txt = f"[{f.fid:03d}] {f.label}"
                child = QTreeWidgetItem(uni_item, [_txt])
                child.setToolTip(0, _txt)  # QOL-03: Vollname auch bei Kuerzung
                child.setData(0, Qt.ItemDataRole.UserRole, f.fid)
                child.setIcon(0, _mini.fixture_icon_for(f))
                labels[f.fid] = f.label

        self._grid_widget.update_fixture_labels(labels)
        self._highlight_group_members()

    def _refresh_legend(self):
        """FM-HEADLAYOUT Slice 4: „Farbe → Gerät"-Legende unter dem Raster.

        Zeigt je Gerät im Raster ein Farbfeld in genau der Zellfarbe (dieselbe
        Funktion wie der Renderer, also keine zweite Farbquelle) + Label + Kopfzahl.
        Bleibt versteckt, solange nur EIN Gerät im Raster liegt — dort ist nichts
        zu unterscheiden und die Zeile wäre nur Rauschen."""
        lg = getattr(self, "_legend", None)
        if lg is None:
            return
        order = self._group_fids()
        if len(order) < 2:
            lg.hide()
            lg.setText("")
            return
        # UI-52: die tatsaechlich belegten KOPF-ZELLEN zaehlen, NICHT aus dem
        # hoechsten Kopf-Index schliessen (`max(head)+1`). Die Regel liegt in
        # `head_cell_colors.head_counts` — dieselbe Quelle, aus der auch der
        # Matrix-Editor seine Legende speist; die Formel stand vorher zweimal im
        # Code und war zweimal falsch. Gezaehlt werden die Kopf-Zellen, NICHT die
        # eingefaerbten Zellen: eine Zelle des GANZEN Geraets traegt zwar den
        # Grundton des Geraets, ist aber kein Kopf (beides zugleich entsteht nur
        # ueber „Matrizen zusammenlegen", s. FM-32).
        heads = head_counts(_split_cell(v)
                            for v in self._grid_widget.positions.values())
        parts = []
        for fid in order:
            col = fixture_cell_color(fid, None, order).name()
            name = self._labels_by_fid().get(fid, f"Fixture {fid}")
            suffix = head_count_suffix(heads.get(fid))
            parts.append(
                f"<span style='background:{col}; color:#fff;'>&nbsp;&nbsp;&nbsp;</span>"
                f" {name}{suffix}")
        lg.setText("Farbe → Gerät: " + " &nbsp;·&nbsp; ".join(parts))
        lg.show()

    def _labels_by_fid(self) -> dict:
        """fid -> Label der gepatchten Fixtures (dieselbe Quelle wie die
        Rasterzellen-Beschriftung)."""
        return dict(getattr(self._grid_widget, "_labels", {}) or {})

    def _highlight_group_members(self):
        """Hebt Fixture-Items hervor, die im aktuellen Raster platziert sind."""
        # FM-16e: Basis-fids (Kopf-Zellen "fid:head" -> fid), sonst wird ein nur per
        # Kopf-Zelle platziertes Fixture nie hervorgehoben (str != int).
        active_fids = set(self._group_fids())

        accent_bg = QColor("#1f6feb")
        accent_fg = QColor("#ffffff")
        normal_bg = QColor(0, 0, 0, 0)  # transparent
        normal_fg = QColor("#cccccc")

        bold_font = QFont("Segoe UI", 9)
        bold_font.setBold(True)
        normal_font = QFont("Segoe UI", 9)

        root = self._fixture_list.invisibleRootItem()
        for i in range(root.childCount()):
            uni_item = root.child(i)
            for j in range(uni_item.childCount()):
                child = uni_item.child(j)
                fid = child.data(0, Qt.ItemDataRole.UserRole)
                if fid in active_fids:
                    child.setBackground(0, QBrush(accent_bg))
                    child.setForeground(0, QBrush(accent_fg))
                    child.setFont(0, bold_font)
                else:
                    child.setBackground(0, QBrush(normal_bg))
                    child.setForeground(0, QBrush(normal_fg))
                    child.setFont(0, normal_font)
        # Slice 4: Legende mitziehen — sie haengt an genau denselben Rasterdaten
        # und laeuft ueber dieselben Trigger (positions_changed + Gruppenwechsel).
        self._refresh_legend()

    def _reload_group_list(self, select_gid: int | None = None):
        """Gruppen-Combo neu aufbauen und die GEWAEHLTE Gruppe (per ID) erhalten.

        Frueher sprang die Auswahl bei jedem Neuaufbau hart auf die alphabetisch
        erste Gruppe (`groups[0]`) — d. h. nach `+ Neu` bzw. nach jedem `Speichern`
        (das ueber GROUP_CHANGED hier landet) wechselte die aktive Gruppe, und
        folgende Drags/Speichern trafen die FALSCHE Gruppe. Jetzt bleibt die
        aktuell selektierte Gruppe stabil; `select_gid` erzwingt gezielt eine
        (z. B. die frisch angelegte)."""
        if select_gid is None and self._current_group is not None:
            select_gid = self._current_group.id
        self._combo_group.blockSignals(True)
        self._combo_group.clear()
        s = self._session()
        if s is None:
            self._combo_group.blockSignals(False)
            self._current_group = None
            return
        try:
            with s:
                groups = list(s.execute(select(FixtureGroup)).scalars())
                # FLD-01b: nach Ordner + Name sortieren und mit Ordnerpfad anzeigen.
                groups.sort(key=lambda x: ((getattr(x, "folder", "") or "").lower(),
                                           (x.name or "").lower()))
                for g in groups:
                    folder = getattr(g, "folder", "") or ""
                    label = f"{folder}/{g.name}" if folder else g.name
                    self._combo_group.addItem(label, g.id)
                if groups:
                    # gewaehlte Gruppe per ID wiederfinden, sonst erste.
                    self._current_group = next(
                        (g for g in groups if g.id == select_gid), groups[0])
                else:
                    self._current_group = None
        except Exception as e:
            print(f"[FixtureGroupView] reload error: {e}")
            self._current_group = None
        # Combo-Anzeige auf die Zielgruppe stellen (Signale noch geblockt).
        if self._current_group is not None:
            idx = self._combo_group.findData(self._current_group.id)
            if idx >= 0:
                self._combo_group.setCurrentIndex(idx)
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
                cell = (int(c), int(r))
            except Exception:
                continue
            # FM-16e: Zellwert ist ENTWEDER ein ganzer fid (int) ODER eine
            # Kopf-Zelle "fid:head" (Str, aus create_head_matrix_group / Merge).
            # Frueher int(v) -> "5:0" warf und die Kopf-Zelle fiel STILL weg
            # (Kopf-Matrix-Gruppe erschien im Editor leer). Beide Formen erhalten.
            if isinstance(v, str) and ":" in v:
                positions[cell] = v
            else:
                try:
                    positions[cell] = int(v)
                except (TypeError, ValueError):
                    continue
        self._grid_widget.set_grid(g.cols, g.rows)
        self._grid_widget.positions = positions
        self._grid_widget.update()
        self._highlight_group_members()

    def _new_group(self):
        name, ok = QInputDialog.getText(self, "Neue Gruppe", "Name:")
        if not ok or not name.strip():
            return
        s = self._session()
        if s is None:
            QMessageBox.warning(self, "Fehler", "Keine Show geöffnet.")
            return
        new_id = None
        try:
            with s:
                g = FixtureGroup(name=name.strip(), cols=8, rows=8, positions_json="{}")
                s.add(g)
                s.commit()
                new_id = g.id
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))
            return
        # Die FRISCH angelegte Gruppe selektieren (nicht auf groups[0] zurueckspringen).
        self._reload_group_list(select_gid=new_id)
        self._notify_groups_changed()

    def _set_group_folder(self):
        """FLD-01b: weist die aktuelle Gruppe einem (verschachtelten) Ordner zu.
        Pfad mit '/' = Unterordner; leer = Wurzel. Verschieben = Pfad ändern."""
        if self._current_group is None:
            QMessageBox.information(self, "Ordner", "Erst eine Gruppe auswählen.")
            return
        cur = getattr(self._current_group, "folder", "") or ""
        path, ok = QInputDialog.getText(
            self, "Ordner setzen",
            "Ordnerpfad (verschachtelt mit /, leer = Wurzel):", text=cur)
        if not ok:
            return
        path = "/".join(p.strip() for p in path.split("/") if p.strip())
        s = self._session()
        if s is None:
            return
        try:
            with s:
                g = s.get(FixtureGroup, self._current_group.id)
                if g is None:
                    return
                g.folder = path
                s.commit()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))
            return
        self._reload_group_list()
        self._notify_groups_changed()

    def _rename_group(self):
        """P5: Gruppe nachtraeglich umbenennen (mit Leer-/Duplikat-Pruefung).
        Der neue Name erscheint ueberall (Programmer/Live View/Matrix) ueber
        GROUP_CHANGED."""
        if self._current_group is None:
            QMessageBox.information(self, "Umbenennen", "Erst eine Gruppe auswählen.")
            return
        name, ok = QInputDialog.getText(
            self, "Gruppe umbenennen", "Neuer Name:",
            text=self._current_group.name or "")
        if not ok:
            return
        name = name.strip()
        if not name:
            QMessageBox.warning(self, "Umbenennen", "Der Name darf nicht leer sein.")
            return
        s = self._session()
        if s is None:
            return
        try:
            with s:
                from sqlalchemy import select
                dup = s.execute(
                    select(FixtureGroup)
                    .where(FixtureGroup.name == name)
                    .where(FixtureGroup.id != self._current_group.id)
                ).scalars().first()
                if dup is not None:
                    if QMessageBox.question(
                        self, "Doppelter Name",
                        f'Eine Gruppe "{name}" existiert bereits. Trotzdem verwenden?',
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    ) != QMessageBox.StandardButton.Yes:
                        return
                g = s.get(FixtureGroup, self._current_group.id)
                if g is None:
                    return
                g.name = name
                s.commit()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))
            return
        self._reload_group_list()
        self._notify_groups_changed()

    def _edit_group(self):
        """Feature „Gruppe bearbeiten": Mitglieder hinzufügen/entfernen, Name
        ändern und Reihenfolge anpassen — über einen touch-tauglichen Dialog
        statt Drag&Drop. Persistiert in der Show-DB, GROUP_CHANGED informiert
        Programmer/Live View/EFX/Matrix."""
        if self._current_group is None:
            QMessageBox.information(self, "Bearbeiten", "Erst eine Gruppe auswählen.")
            return
        from src.ui.widgets.group_edit_dialog import GroupEditDialog
        labels = {f.fid: f.label for f in self._state.get_patched_fixtures()}
        dlg = GroupEditDialog(
            group_name=self._current_group.name or "",
            positions_json=self._current_group.positions_json or "{}",
            cols=self._current_group.cols,
            rows=self._current_group.rows,
            patched_labels=labels,
            parent=self,
        )
        if not dlg.exec():
            return
        name = dlg.result_name()
        if not name:
            QMessageBox.warning(self, "Bearbeiten", "Der Name darf nicht leer sein.")
            return
        pos_json, cols, rows = dlg.result_positions()
        s = self._session()
        if s is None:
            return
        try:
            with s:
                if name != (self._current_group.name or ""):
                    dup = s.execute(
                        select(FixtureGroup)
                        .where(FixtureGroup.name == name)
                        .where(FixtureGroup.id != self._current_group.id)
                    ).scalars().first()
                    if dup is not None:
                        if QMessageBox.question(
                            self, "Doppelter Name",
                            f'Eine Gruppe "{name}" existiert bereits. Trotzdem verwenden?',
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        ) != QMessageBox.StandardButton.Yes:
                            return
                g = s.get(FixtureGroup, self._current_group.id)
                if g is None:
                    return
                g.name = name
                g.positions_json = pos_json
                g.cols = cols
                g.rows = rows
                s.commit()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))
            return
        self._reload_group_list()
        self._notify_groups_changed()

    def _delete_group(self):
        if self._current_group is None:
            return
        reply = QMessageBox.question(self, "Löschen",
                                     f'Gruppe "{self._current_group.name}" löschen?',
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
        self._notify_groups_changed()

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
            self._notify_groups_changed()
            QMessageBox.information(self, "Gespeichert", f'Gruppe "{self._current_group.name}" gespeichert.')
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))

    def _group_fids(self) -> list[int]:
        """Fids der aktuell im Raster platzierten Fixtures der Gruppe. FM-16e:
        Kopf-Zellen ``"fid:head"`` -> Basis-fid (dedupliziert) fuer Member-Highlight."""
        # ★ FM-41: ueber `parse_zelle`, nicht ueber den verlustbehafteten
        # `_split_cell`. Sonst gilt ein Geraet, das NUR mit Weiss-Zellen im
        # Raster steht, hier als „nicht in der Gruppe" — es liesse sich weder
        # im Baum hervorheben noch als Ziel des Kontextmenues waehlen, obwohl
        # man seine Zellen sieht.
        out: list[int] = []
        for v in self._grid_widget.positions.values():
            fid, _achse, _index = parse_zelle(v)
            if fid is not None and fid not in out:
                out.append(fid)
        return out

    def _merge_groups(self):
        """FM-16e: >=2 Gruppen wählen -> zu EINER größeren Matrix stapeln (Raster
        untereinander, Reihenfolge = Listen-/Namensreihenfolge). Ruft
        AppState.merge_head_matrix_groups; die Quell-Gruppen bleiben erhalten."""
        s = self._session()
        if s is None:
            QMessageBox.warning(self, "Fehler", "Keine Show geöffnet.")
            return
        # FM-16e: Session SOFORT schließen (with) — sonst hält ein offener Read-Tx
        # während des modalen Dialogs auf einer non-WAL/Netz-Show den Writer auf
        # (busy_timeout). Nur (id, name) mitnehmen, keine ORM-Objekte/Session halten.
        with s:
            groups = [(int(g.id), g.name or f"Gruppe {g.id}") for g in s.execute(
                select(FixtureGroup).order_by(FixtureGroup.name)).scalars().all()]
        if len(groups) < 2:
            QMessageBox.information(self, "Zusammenlegen", "Mindestens zwei Gruppen nötig.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Matrizen zusammenlegen")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Gruppen wählen (von oben nach unten gestapelt):"))
        lst = QListWidget()
        lst.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        for gid, gname in groups:
            it = QListWidgetItem(gname)
            it.setData(Qt.ItemDataRole.UserRole, gid)
            lst.addItem(it)
        lay.addWidget(lst)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        # FM-16e: in VISUELLER Reihenfolge (Listen-Zeile) stapeln, nicht in Klick-/
        # Selektions-Reihenfolge — sonst passt „von oben nach unten" nicht zum Ergebnis.
        gids = [it.data(Qt.ItemDataRole.UserRole)
                for it in sorted(lst.selectedItems(), key=lst.row)]
        if len(gids) < 2:
            QMessageBox.information(self, "Zusammenlegen",
                                    "Mindestens zwei Gruppen wählen.")
            return
        new_gid = get_state().merge_head_matrix_groups(gids)
        if new_gid is None:
            QMessageBox.warning(self, "Zusammenlegen", "Zusammenlegen fehlgeschlagen.")
            return
        self._reload_group_list(select_gid=new_gid)

    def _notify_groups_changed(self):
        """Zentrale GROUP_CHANGED-Benachrichtigung: Programmer, Live View, Matrix
        und Patcher aktualisieren ihre Gruppenlisten automatisch (Abschnitt 1)."""
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.GROUP_CHANGED, None)
        except Exception as e:
            print(f"[fixture_group_view] group notify error: {e}")

    def _apply_grid_size(self, *_):
        c = self._spin_cols.value()
        r = self._spin_rows.value()
        self._grid_widget.set_grid(c, r)
        self._highlight_group_members()

    # ── FM-HEADLAYOUT Slice 3: Kopf-Zellen von Hand anordnen ──────────────────

    def _tree_fids(self) -> list[int]:
        """fids aller Fixture-Items im Baum (Universe-Ordner tragen kein fid)."""
        out: list[int] = []
        root = self._fixture_list.invisibleRootItem()
        for i in range(root.childCount()):
            uni = root.child(i)
            for j in range(uni.childCount()):
                fid = uni.child(j).data(0, Qt.ItemDataRole.UserRole)
                if fid is not None:
                    out.append(int(fid))
        return out

    def _target_fid(self) -> int | None:
        """Gerät, dessen Köpfe angeordnet werden sollen — in dieser Reihenfolge:

        1. das **angeklickte** Baum-Item (``currentItem``),
        2. genau EIN echt selektiertes Baum-Item,
        3. enthält die gerade bearbeitete Gruppe genau EIN Gerät, dann dieses
           (eindeutig, also kein Raten).

        Sonst ``None``. Punkt 3 ist wichtig, weil das blaue Hervorheben im Baum
        die **Gruppen-Mitglieder** markiert (Hintergrundfarbe, s.
        ``_highlight_group_members``) und NICHT die Auswahl: bei einer frisch
        gepatchten Kopf-Matrix-Gruppe sieht das Gerät „gewählt" aus, ohne
        ``currentItem`` zu sein — ohne diesen Fall verlangte die Aktion ein
        Anklicken von etwas, das schon markiert wirkt."""
        item = self._fixture_list.currentItem()
        fid = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
        if fid is not None:
            return int(fid)
        sel = [it.data(0, Qt.ItemDataRole.UserRole)
               for it in self._fixture_list.selectedItems()]
        sel = [int(f) for f in sel if f is not None]
        if len(sel) == 1:
            return sel[0]
        in_group = self._group_fids()
        if len(in_group) == 1:
            return int(in_group[0])
        return None

    # ── FM-20: Rechtsklick-Menü im Raster ────────────────────────────────────

    def _fixture_by_fid(self, fid: int):
        return next((f for f in self._state.get_patched_fixtures()
                     if f.fid == int(fid)), None)

    def _on_cell_menu(self, col: int, row: int, global_pos):
        """Rechtsklick-Menü bauen und anzeigen."""
        menu = self._build_cell_menu(col, row)
        if menu is None:
            return
        menu.exec(global_pos)

    def _build_cell_menu(self, col: int, row: int):
        """Menü für die ANGEKLICKTE Zelle — gebaut, aber NICHT gezeigt.

        ★ Bewusst getrennt vom Anzeigen. `QMenu.exec` blockiert, bis jemand
        klickt; ein Test, der den Inhalt prüfen will, müsste also entweder das
        Menü aufreissen (headless unmöglich) oder `exec` wegpatchen — was bei
        PySide6-Klassen nicht zuverlässig greift und den Lauf schlicht HÄNGEN
        liess statt zu scheitern. Getrennt ist der Menüinhalt eine ganz normale,
        prüfbare Rückgabe.

        ★ Der Punkt dabei ist nicht das Menü, sondern woher das Zielgerät kommt:
        aus der Zelle unter dem Mauszeiger. „Köpfe einzeln → Raster" und
        „zusammenfassen" gab es schon, aber nur als Knöpfe, die das Gerät aus
        der Baum-Auswahl LINKS nehmen — man musste also erst dort das richtige
        Gerät finden, obwohl man mit der Maus längst auf ihm stand. Genau das
        meinte David mit „intuitiv".
        """
        gw = self._grid_widget
        wert = gw.positions.get((col, row))
        # ★ FM-41: auch aus einer Weiss-Zelle. Ueber `_split_cell` verlor das
        # Menue auf einer Weiss-Zelle ALLE geraetebezogenen Eintraege
        # („zusammenfassen", „alle Zellen entfernen", Aufteilen) — sichtbar war
        # nur noch „Zelle entfernen". `head` bleibt bewusst None, wenn die Zelle
        # keine FARB-Kopfzelle ist: die kopfbezogenen Eintraege meinen Koepfe.
        _fid, _achse, _index = parse_zelle(wert) if wert is not None else (None, None, None)
        fid = _fid
        head = _index if _achse == ACHSE_FARBE else None
        fx = self._fixture_by_fid(fid) if fid is not None else None

        menu = QMenu(self)
        if wert is not None:
            act_del = menu.addAction("Zelle entfernen")
            act_del.triggered.connect(lambda: self._cell_menu_remove(col, row))

        if fx is not None:
            from src.core.app_state import color_head_count
            try:
                n = int(color_head_count(fx))
            except Exception:
                n = 0
            name = getattr(fx, "label", "") or f"Gerät {fid}"
            if head is None and n >= 2:
                # Ganze-Geräte-Zelle mit mehreren Köpfen -> aufteilen anbieten.
                menu.addSeparator()
                sub = menu.addMenu(f'„{name}“ aufteilen ({n} Elemente)')
                # FM-40: hinterlegte Form zuerst — hier wie am Knopf. Zwei Wege
                # mit unterschiedlichem Angebot waeren schlimmer als einer.
                _form = self._hinterlegte_form(fx, n)
                if _form is not None:
                    _z, _s = _form
                    sub.addAction(f"wie im Gerät hinterlegt ({_z}×{_s})"
                                  ).triggered.connect(
                        lambda: self._cell_menu_split(fx, n, "hinterlegt", col, row))
                    sub.addSeparator()
                sub.addAction("als Zeile").triggered.connect(
                    lambda: self._cell_menu_split(fx, n, "row", col, row))
                sub.addAction("als Spalte").triggered.connect(
                    lambda: self._cell_menu_split(fx, n, "col", col, row))
                sub.addAction("als Block…").triggered.connect(
                    lambda: self._cell_menu_split(fx, n, "block", col, row))
            elif head is not None:
                menu.addSeparator()
                menu.addAction(f'„{name}“ zu einer Zelle zusammenfassen'
                               ).triggered.connect(
                    lambda: self._cell_menu_collapse(fx))
            if fid is not None:
                menu.addSeparator()
                menu.addAction(f'Alle Zellen von „{name}“ entfernen'
                               ).triggered.connect(
                    lambda: self._cell_menu_drop_all(fid))

        return None if menu.isEmpty() else menu

    def _cell_menu_remove(self, col: int, row: int):
        gw = self._grid_widget
        if gw.remove_cell(col, row):
            gw.update()
            gw.positions_changed.emit()

    def _cell_menu_drop_all(self, fid: int):
        gw = self._grid_widget
        gw._drop_fid_cells(int(fid))
        gw.update()
        gw.positions_changed.emit()

    def _cell_menu_collapse(self, fx):
        gw = self._grid_widget
        if gw.collapse_fixture_heads(fx.fid) is None:
            return
        gw.update()
        gw.positions_changed.emit()

    def _block_platzieren(self, fx, n: int, spalten: int, titel: str,
                          col: int | None = None, row: int | None = None,
                          achse: str = ACHSE_FARBE) -> bool:
        """Die Köpfe von ``fx`` als Rechteck mit ``spalten`` Spalten ablegen.

        EINE Implementierung für beide Wege — das Kontextmenü („als Block…",
        mit Rückfrage) und den Knopf („wie im Gerät hinterlegt", ohne). Getrennt
        gepflegt wären es zwei Fassungen derselben Regeln (Raster vorher
        vergrößern, Pixel-Reihenfolge, Montage-Drehung/Flip), und genau daran
        laufen sie erfahrungsgemäß auseinander.

        Rückgabe: ob etwas platziert wurde."""
        gw = self._grid_widget
        drehung = int(getattr(fx, "element_rotation", 0) or 0)
        self._grow_grid_for_block(n, spalten, rotation=drehung)
        placed = gw.place_fixture_block(
            fx.fid, n, spalten, col, row, achse,
            order=getattr(fx, "pixel_order", "rowwise") or "rowwise",
            rotation=drehung,
            flip=bool(getattr(fx, "element_flip", False)))
        if not placed:
            QMessageBox.information(self, titel,
                                    "Im Raster ist keine Zelle frei — erst "
                                    "Spalten/Reihen erhöhen oder Platz machen.")
            return False
        if len(placed) < n:
            QMessageBox.information(
                self, titel,
                f"Nur {len(placed)} von {n} Elementen platziert — das Raster "
                "war voll. Rest nach dem Vergrößern erneut einfügen.")
        gw.update()
        gw.positions_changed.emit()
        return True

    def _cell_menu_split(self, fx, n: int, wie: str, col: int, row: int):
        """Aufteilen an der angeklickten Stelle — Zeile, Spalte oder Block."""
        gw = self._grid_widget
        titel = "Aufteilen"
        if wie in ("block", "hinterlegt"):
            if wie == "hinterlegt":
                form = self._hinterlegte_form(fx, n)
                if form is None:
                    return          # Menue bietet es dann gar nicht erst an
                spalten = form[1]
            else:
                spalten = self._ask_block_cols(n, fx)
                if spalten is None:
                    return
            self._block_platzieren(fx, n, spalten, titel, col, row)
            return
        else:
            vertical = (wie == "col")
            self._grow_grid_for_strip(n, vertical=vertical)
            placed = gw.place_fixture_heads(fx.fid, n, col, row,
                                            vertical=vertical)
        if not placed:
            QMessageBox.information(self, titel,
                                    "Im Raster ist keine Zelle frei — erst "
                                    "Spalten/Reihen erhöhen oder Platz machen.")
            return
        if len(placed) < n:
            QMessageBox.information(
                self, titel,
                f"Nur {len(placed)} von {n} Elementen platziert — das Raster "
                "war voll. Rest nach dem Vergrößern erneut einfügen.")
        gw.update()
        gw.positions_changed.emit()

    def _ask_block_cols(self, n: int, fx=None) -> int | None:
        """Spaltenzahl für den Block erfragen.

        **Vorbelegt aus dem Gerät, wenn es eine hinterlegte Form hat** (FM-40) —
        das ist die einzige Zahl, die nicht geraten ist. Sonst wie bisher ein
        TEILER von ``n`` nahe der Wurzel, damit der Block aufgeht.

        ★ Warum das mehr als Bequemlichkeit ist: der geratene Teiler liegt beim
        ZQ06121 (48 Zonen) bei 6 oder 8 — das Gerät hat aber **12** Spalten. Der
        Vorschlag war also nicht nur unbequem, er war zuverlässig falsch, und
        wer ihn bestätigt, bekommt ein Panel in der falschen Form."""
        form = self._hinterlegte_form(fx, n) if fx is not None else None
        if form is not None:
            zeilen, spalten = form
            vorschlag = spalten
            frage = (f"Spalten (bei {n} Elementen) — "
                     f"im Gerät hinterlegt: {zeilen}×{spalten}:")
        else:
            teiler = [t for t in range(2, n) if n % t == 0]
            vorschlag = min(teiler, key=lambda t: abs(t - (n ** 0.5)), default=n)
            frage = f"Spalten (bei {n} Elementen):"
        wert, ok = QInputDialog.getInt(
            self, "Als Block aufteilen", frage, vorschlag, 1, max(1, n), 1)
        return int(wert) if ok else None

    def _grow_grid_for_block(self, n: int, spalten: int, *,
                             rotation: int = 0):
        """Raster gross genug machen, sonst greift die Ausweich-Regel und die
        Blockform kippt — dieselbe Falle wie beim Streifen
        (`_grow_grid_for_strip`), nur in zwei Richtungen statt einer.

        ★ Bei 90°/270° tauschen Breite und Höhe die Rollen: ein 12×4-Panel
        braucht hochkant ein 4×12-Raster. Ohne diesen Tausch wäre das Raster in
        der falschen Richtung zu klein, die Köpfe wichen aus, und das Ergebnis
        sähe nach einem Fehler in der Drehung aus statt nach einem zu kleinen
        Raster.

        Verkleinert NIE, und zieht die Spinboxen mit ``blockSignals`` nach —
        sonst läuft ``_apply_grid_size`` re-entrant (gleiche Begründung wie in
        ``_grow_grid_for_strip`` und ``_add_all_fixtures``).
        """
        zeilen = (n + spalten - 1) // spalten
        if int(rotation) % 180 == 90:
            spalten, zeilen = zeilen, spalten
        gw = self._grid_widget
        cols, rows = gw.cols, gw.rows
        if cols < spalten:
            cols = spalten
            self._spin_cols.blockSignals(True)
            self._spin_cols.setValue(cols)
            self._spin_cols.blockSignals(False)
        if rows < zeilen:
            rows = zeilen
            self._spin_rows.blockSignals(True)
            self._spin_rows.setValue(rows)
            self._spin_rows.blockSignals(False)
        if (cols, rows) != (gw.cols, gw.rows):
            gw.set_grid(cols, rows)

    def _selected_tree_fixture(self, title: str):
        """Das Zielgerät (oder ``None`` + Hinweis-Dialog, der die blaue Markierung
        erklärt — sonst liest man sie als Auswahl und der Hinweis wirkt falsch)."""
        fid = self._target_fid()
        if fid is None:
            QMessageBox.information(
                self, title,
                "Klick links im Baum das Gerät an, dessen Köpfe du anordnen "
                "willst (ein Gerät, nicht den Universe-Ordner).\n\n"
                "Hinweis: Die blaue Markierung im Baum zeigt nur, welche Geräte "
                "schon in dieser Gruppe liegen — sie ist keine Auswahl.")
            return None
        fx = self._target_fixture_leise()
        if fx is None:
            QMessageBox.information(self, title,
                                    "Das gewählte Gerät ist nicht mehr gepatcht.")
        return fx

    def _target_fixture_leise(self):
        """Dasselbe Zielgerät wie ``_selected_tree_fixture``, aber OHNE Dialog —
        für Menü-Beschriftung und Tooltip, die beim Aufklappen laufen und dabei
        niemanden anreden dürfen. Bewusst dieselbe Quelle (``_target_fid``), damit
        die beiden Wege nicht auseinanderlaufen."""
        fid = self._target_fid()
        if fid is None:
            return None
        return next((f for f in self._state.get_patched_fixtures()
                     if f.fid == int(fid)), None)

    def _hinterlegte_form(self, fx, n: int | None = None,
                          achse: str = ACHSE_FARBE):
        """FM-40: die im Fixture-Profil hinterlegte physische Rasterform
        ``(zeilen, spalten)`` — oder ``None``.

        ★ Die Form liegt längst vor: VIZ-50a legt sie als
        ``FixtureMode.grid_rows``/``grid_cols`` ab und ``panel_grid_for`` liest
        sie. Gelesen hat sie bisher aber **nur der Visualizer** — im
        Gruppen-Editor landete jedes Panel als Streifen, und die Form musste
        jedes Mal von Hand nachgestellt werden. Es fehlte kein Datum, nur der
        Aufruf.

        ``None`` heißt „nicht anbieten" und hat zwei Gründe, die bewusst gleich
        behandelt werden: es ist **nichts hinterlegt** (dann wäre jede Zahl
        geraten), oder die Form **passt nicht zur Kopfzahl** (``zeilen*spalten
        != n``). Der zweite Fall ist der gefährlichere — ein Panel als falsches
        Rechteck abzulegen sieht richtig aus und ist es nicht. Lieber die
        bisherige Frage stellen als still danebenlegen.

        ★★ FM-41: die Weiß-Segmente haben eine EIGENE hinterlegte Form
        (``white_grid_for``, CDX-52) — nicht die des Farbrasters. Sie hier
        mitzulesen ist der Unterschied zwischen „die 8 Weiß-Segmente des
        ZQ06121 liegen als 1×8-Leiste" und „irgendwie als Rechteck". Und der
        Fall „nichts hinterlegt" heißt auf beiden Achsen dasselbe: **nicht
        anbieten**, statt eine Form zu raten."""
        try:
            from src.core.app_state import panel_grid_for, white_grid_for
            _quelle = white_grid_for if achse == ACHSE_WEISS else panel_grid_for
            zeilen, spalten = _quelle(fx)
            zeilen, spalten = int(zeilen or 0), int(spalten or 0)
        except Exception:
            return None
        if achse == ACHSE_WEISS and n:
            zeilen, spalten = self._weiss_form_ergaenzen(fx, zeilen, spalten, int(n))
        if zeilen < 1 or spalten < 1:
            return None
        if n is not None and zeilen * spalten != int(n):
            return None
        return (zeilen, spalten)

    @staticmethod
    def _weiss_form_ergaenzen(fx, zeilen: int, spalten: int, n: int):
        """Die halb hinterlegte Weiß-Form vervollständigen. Nur für Weiß.

        ★ Zwei Konventionen, die es im Baum SCHON GIBT — hier gelesen statt neu
        erfunden:

        1. **Eine 0 heißt „aus der Kanalzahl füllen".** Der ZQ06121 trägt
           bewusst ``(1, 0)``: „die Warmweiß-Leiste ist EINE Reihe, die
           Spaltenzahl steht als acht ``color_w``-Kanäle in diesem Modus, und
           ``panelGrid`` füllt sie daraus" (CDX-52, ``_ZQ06121_WEISS``). Wer
           hier auf ``spalten >= 1`` besteht, wirft eine hinterlegte Form weg
           und nennt sie „nicht vorhanden".
        2. **Gleich viele Weiß- wie Farbköpfe heißt: dieselbe Geometrie.** Das
           ist wortwörtlich die ENG-25-Regel („das Weiß gehört zur Zelle, wenn
           ``n_w == n_c``") — dort für den Renderer, hier für die Auslegung.
           Der Stairville Matrix Blinder 5×5 RGBWW hat 25 Weiß-Kanäle und
           ``white_grid = (0, 0)``, weil es keine eigene LEISTE gibt: die
           Weiß-LEDs sitzen IN den 25 Pixeln. Ihre Form ist also die des
           Panels, 5×5 — und die steht hinterlegt da.

        ``(0, 0)`` ohne passende Farbzahl bleibt ``None``: „keine eigene
        Weiß-Leiste hinterlegt" heißt nach CDX-52 **nein**, nicht *raten*."""
        if zeilen >= 1 and spalten < 1 and zeilen and n % zeilen == 0:
            return zeilen, n // zeilen
        if spalten >= 1 and zeilen < 1 and spalten and n % spalten == 0:
            return n // spalten, spalten
        if zeilen < 1 and spalten < 1:
            from src.core.app_state import color_head_count, panel_grid_for
            try:
                if int(color_head_count(fx)) == n:
                    pz, ps = panel_grid_for(fx)
                    return int(pz or 0), int(ps or 0)
            except Exception:
                return zeilen, spalten
        return zeilen, spalten

    def _grow_grid_for_strip(self, count: int, *, vertical: bool):
        """Raster so vergrößern, dass ein Kopf-Streifen der Länge ``count`` in der
        gewünschten Richtung überhaupt Platz hat (hochkant → Reihen, waagerecht →
        Spalten). Verkleinert NIE. Spinbox mit ``blockSignals`` mitziehen (wie
        ``_add_all_fixtures``), damit kein re-entranter ``_apply_grid_size`` läuft."""
        gw = self._grid_widget
        cols, rows = gw.cols, gw.rows
        if vertical and rows < count:
            rows = count
            self._spin_rows.blockSignals(True)
            self._spin_rows.setValue(rows)
            self._spin_rows.blockSignals(False)
        elif not vertical and cols < count:
            cols = count
            self._spin_cols.blockSignals(True)
            self._spin_cols.setValue(cols)
            self._spin_cols.blockSignals(False)
        if (cols, rows) != (gw.cols, gw.rows):
            gw.set_grid(cols, rows)

    # ★ FM-41: EINE Stelle, die sagt, was eine Achse ist — Zahl und Wortwahl.
    # Ohne sie stuende „wie viele?" und „wie heisst das?" gleich viermal im
    # View (zwei Menues x hinterlegt/Streifen), und beim naechsten Geraetetyp
    # ein fuenftes Mal. Das ist die Doppelstellen-Klasse aus Checkliste 17.
    _ACHSEN_WORT = {
        ACHSE_FARBE: ("Köpfe", "pro-Kopf färbbare Bänke"),
        ACHSE_WEISS: ("Weiß-Segmente", "eigenen Weiß-Segmente"),
    }

    def _achsen_zahl(self, fx, achse: str) -> int:
        """Wie viele ansprechbare Elemente hat ``fx`` auf dieser Achse?

        Farbe: dieselbe Quelle wie die Auto-Kopf-Matrix beim Patchen
        (``color_head_count``) — sonst driften Hand- und Auto-Anlage.
        Weiß: ``weiss_segment_count``, das bewusst **nicht** auf 1 aufrundet;
        ein erfundenes Segment wäre sofort eine Phantom-Zelle."""
        from src.core.app_state import (color_head_count, weiss_segment_count,
                                        weiss_ist_eigene_achse)
        try:
            if achse == ACHSE_WEISS:
                # ★★★ FM-41 (nachgemessen 05.09.): 0, wenn das Weiss zur
                # FARBZELLE gehoert. Bei einem gewoehnlichen RGBW-PAR (1:1) oder
                # dem Blinder 5x5 RGBWW (25:25) ist `color_w` derselbe physische
                # Emitter, den die Farbzelle ueber den RGBW-Split fuehrt — eine
                # Weiss-Zelle daneben adressiert nichts Zweites, sondern
                # ueberschreibt nur. Gemessen: 1564 von 5125 Modi bekamen die
                # Achse angeboten, obwohl es sie bei ihnen nicht gibt; wirklich
                # eigenstaendig ist sie in 71. Die Regel ist DIESELBE, die der
                # Renderer seit ENG-25 fuehrt.
                if not weiss_ist_eigene_achse(fx):
                    return 0
                return int(weiss_segment_count(fx))
            return int(color_head_count(fx))
        except Exception:
            return 0

    def _place_heads(self, *, vertical: bool, achse: str = ACHSE_FARBE):
        """Setzt die Köpfe des gewählten Geräts als Einzel-Zellen ins Raster.
        Kopfzahl kommt aus derselben Quelle wie die Auto-Kopf-Matrix beim Patchen
        (``app_state.color_head_count``) — sonst driften Hand- und Auto-Anlage."""
        _mehrzahl, _quelle = self._ACHSEN_WORT[achse]
        title = f"{_mehrzahl} einzeln → Raster"
        fx = self._selected_tree_fixture(title)
        if fx is None:
            return
        n = self._achsen_zahl(fx, achse)
        if n < 2:
            _name = getattr(fx, "label", "") or f"Fixture {fx.fid}"
            QMessageBox.information(
                self, title,
                f"{_name} hat keine {_quelle} — es gibt also nichts, was man "
                "einzeln im Raster verteilen könnte.")
            return
        gw = self._grid_widget
        # Raster erst gross genug machen, sonst KIPPT die gewuenschte Orientierung:
        # eine Auto-Kopf-Matrix ist 1×N, ein „hochkant"-Streifen passt dort nicht,
        # und die Ausweich-Regel (naechste freie Zelle) haette die Koepfe wieder
        # waagerecht verteilt — genau das Gegenteil der Anweisung.
        self._grow_grid_for_strip(n, vertical=vertical)
        placed = gw.place_fixture_axis(fx.fid, achse, n, vertical=vertical)
        if not placed:
            QMessageBox.information(self, title,
                                    "Im Raster ist keine Zelle frei — erst "
                                    "Spalten/Reihen erhöhen oder Platz machen.")
            return
        if len(placed) < n:
            QMessageBox.information(
                self, title,
                f"Nur {len(placed)} von {n} {_mehrzahl} platziert — das Raster "
                "war voll. Rest nach dem Vergrößern erneut einfügen.")
        gw.update()
        gw.positions_changed.emit()

    def _act_hinterlegt_fuer(self, achse: str):
        """Die „hinterlegt"-Aktion dieser Achse.

        Rückfall auf den eingeführten Einzelnamen ``_act_hinterlegt``: die
        Stub-Views der FM-40-Tests setzen genau den, und er meint die
        Farb-Achse. So bleibt der eingeführte Vertrag gültig, ohne dass eine
        zweite Menü-Fassung entsteht."""
        acts = getattr(self, "_acts_hinterlegt", None)
        if acts:
            return acts.get(achse)
        if achse == ACHSE_FARBE:
            return getattr(self, "_act_hinterlegt", None)
        return None

    def _heads_menu_aktualisieren(self, achse: str = ACHSE_FARBE):
        """Beschriftet die „hinterlegt"-Aktion mit der ECHTEN Form des gerade
        gewählten Geräts und schaltet sie ab, wenn es keine gibt.

        Der Name allein („wie im Gerät hinterlegt") sagt nicht, was passieren
        wird — „wie im Gerät hinterlegt (4×12)" schon. Und eine Aktion, die für
        das gewählte Gerät gar nichts tun kann, gehört ausgegraut statt in einen
        Dialog, der erklärt, warum sie nichts getan hat."""
        act = self._act_hinterlegt_fuer(achse)
        if act is None:
            return
        fx = self._target_fixture_leise()
        n = self._achsen_zahl(fx, achse) if fx is not None else 0
        form = (self._hinterlegte_form(fx, n, achse)
                if (fx is not None and n >= 2) else None)
        if form is None:
            act.setText("wie im Gerät hinterlegt")
            act.setEnabled(False)
            act.setToolTip("Für dieses Gerät ist keine Rasterform hinterlegt "
                           "(oder sie passt nicht zur Kopfzahl) — dann wäre "
                           "jede Anordnung geraten.")
            return
        zeilen, spalten = form
        act.setText(f"wie im Gerät hinterlegt ({zeilen}×{spalten})")
        act.setEnabled(True)
        _mehrzahl = self._ACHSEN_WORT[achse][0]
        act.setToolTip(f"Legt die {n} {_mehrzahl} als {zeilen}×{spalten} ab — die Form, "
                       "die im Fixture-Profil steht. Montage-Drehung und "
                       "Pixel-Reihenfolge des Geräts werden dabei verrechnet.")

    def _place_heads_hinterlegt(self, _checked: bool = False,
                                achse: str = ACHSE_FARBE):
        """FM-40: die Köpfe in der Form ablegen, die am Fixture hinterlegt ist."""
        _mehrzahl, _quelle = self._ACHSEN_WORT[achse]
        titel = f"{_mehrzahl} → hinterlegtes Raster"
        fx = self._selected_tree_fixture(titel)
        if fx is None:
            return
        n = self._achsen_zahl(fx, achse)
        if n < 2:
            _name = getattr(fx, "label", "") or f"Fixture {fx.fid}"
            QMessageBox.information(
                self, titel,
                f"{_name} hat keine {_quelle} — es gibt also nichts, was man "
                "einzeln im Raster verteilen könnte.")
            return
        form = self._hinterlegte_form(fx, n, achse)
        if form is None:
            _name = getattr(fx, "label", "") or f"Fixture {fx.fid}"
            QMessageBox.information(
                self, titel,
                f"Für {_name} ist keine Rasterform hinterlegt, oder sie passt "
                f"nicht zu den {n} Köpfen.\n\n"
                'Jede Anordnung wäre hier geraten — nimm „als Zeile“ oder '
                '„als Spalte“, oder trag die Form im Fixture-Generator '
                '(Feld „Raster“) ein, dann steht sie künftig hier.')
            return
        zeilen, spalten = form
        self._block_platzieren(fx, n, spalten, titel, achse=achse)

    def _place_heads_horizontal(self, _checked: bool = False):
        self._place_heads(vertical=False)

    def _place_heads_vertical(self, _checked: bool = False):
        self._place_heads(vertical=True)

    def _collapse_heads(self, _checked: bool = False):
        """Kopf-Zellen des gewählten Geräts wieder zu EINER Zelle zusammenfassen."""
        title = "Köpfe zusammenfassen"
        fx = self._selected_tree_fixture(title)
        if fx is None:
            return
        gw = self._grid_widget
        cell = gw.collapse_fixture_heads(fx.fid)
        if cell is None:
            QMessageBox.information(
                self, title,
                "Dieses Gerät steht nicht kopfweise im Raster — es gibt nichts "
                "zusammenzufassen.")
            return
        gw.update()
        gw.positions_changed.emit()

    def _add_all_fixtures(self):
        """Shortcut „alle auswählen → in Gruppe übernehmen": alle gepatchten
        Fixtures ins Raster legen (freie Zellen zuerst, in Patch-Reihenfolge;
        Reihen wachsen bei Bedarf). Bereits platzierte Fixtures bleiben. Wie ein
        Drag speichert das noch nicht — erst „Speichern" schreibt es in die Gruppe."""
        gw = self._grid_widget
        fixtures = self._state.get_patched_fixtures()
        # FM-16e: Basis-fids (Kopf-Zellen -> fid), sonst wird ein nur per Kopf-Zelle
        # platziertes Fixture erneut als ganze Zelle hinzugefügt (Duplikat).
        placed = set(self._group_fids())
        todo = [f.fid for f in sorted(fixtures, key=lambda x: (x.universe, x.address))
                if f.fid not in placed]
        if not todo:
            QMessageBox.information(
                self, "Alle → Raster",
                "Alle gepatchten Fixtures sind bereits im Raster." if fixtures
                else "Keine Fixtures gepatcht.")
            return
        cells = gw.first_free_cells(len(todo))
        for fid, cell in zip(todo, cells):
            gw.positions[cell] = fid
        # Reihenzahl an den tiefsten belegten Punkt anpassen (falls gewachsen).
        max_row = max(r for (_c, r) in gw.positions)
        if max_row + 1 > gw.rows:
            self._spin_rows.blockSignals(True)
            self._spin_rows.setValue(max_row + 1)
            self._spin_rows.blockSignals(False)
            gw.set_grid(gw.cols, max_row + 1)
        gw.update()
        gw.positions_changed.emit()
