"""FM-22: die zwei Dialoge, die das Build-Skript in der UI ersetzen.

``PanelGridDialog``  — „Raster aus Gerät": ein Mehrzonen-Gerät wird direkt zum
Matrix-Raster. Bisher fuehrte der einzige Weg ueber eine Fixture-Gruppe
(Gruppen-Tab, Raster vergroessern, Geraet finden, aufteilen, zurueck) — fuer ein
48-Zonen-Panel hiess das im schlechtesten Fall 48 Zieh-Vorgaenge.

``PatternWizardDialog`` — der Muster-Assistent: Richtung, Balkenbreite, Farbe und
Tempo ergeben einen fertigen Chaser mit harten Kanten. Die Matrix-Algorithmen
koennen das nicht: sie laufen mit eigenem Tempo ueber die Flaeche und zeigen
einen Verlauf, keine klare Kante.

Beide Dialoge rechnen NICHTS selbst — die Geometrie kommt aus
``src.core.matrix_pattern`` und ist dort headless geprueft. Hier steht nur die
Bedienung.
"""
from __future__ import annotations

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout,
                               QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit,
                               QLabel, QPushButton, QWidget, QDialogButtonBox)
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPainter, QColor

from src.core.matrix_pattern import (PATTERN_DIRECTIONS, DEFAULT_DIRECTION,
                                     band_count, panel_grid, pattern_frames,
                                     suggested_block_cols)
from src.core.pixel_order import (PIXEL_ORDER_LABELS, normalize_pixel_order,
                                  normalize_element_rotation)


class PanelCandidate:
    """Ein Geraet, das als Panel-Raster taugt — alles, was der Dialog braucht.

    Bewusst ein schlichtes Wertobjekt statt der DB-Zeile: der Dialog soll ohne
    Datenbank pruefbar sein, und die Kopf-Zahl steht in der DB ohnehin nicht
    (sie wird aus den ``color_r``-Kanaelen gezaehlt).
    """

    def __init__(self, fid: int, label: str, head_count: int, *,
                 order: str = "rowwise", rotation: int = 0, flip: bool = False):
        self.fid = int(fid)
        self.label = str(label)
        self.head_count = int(head_count)
        self.order = normalize_pixel_order(order)
        self.rotation = normalize_element_rotation(rotation)
        self.flip = bool(flip)


def panel_candidates(fixtures) -> list:
    """Aus gepatchten Geraeten die mit MEHREREN faerbbaren Zonen heraussuchen.

    Ein Ein-Zonen-Geraet ergaebe ein 1x1-Raster — darauf liefe jeder
    Flaecheneffekt als eine einzige Farbe. Es hier anzubieten waere also eine
    Einladung in einen Zustand, der garantiert nicht gemeint ist.
    """
    from src.core.app_state import color_head_count
    out = []
    for fx in fixtures or []:
        fid = getattr(fx, "fid", None)
        if fid is None:
            continue
        try:
            n = int(color_head_count(fx))
        except Exception:
            continue
        if n < 2:
            continue
        label = (getattr(fx, "label", "") or "") or f"Gerät {fid}"
        out.append(PanelCandidate(
            fid, label, n,
            order=getattr(fx, "pixel_order", "rowwise"),
            rotation=getattr(fx, "element_rotation", 0),
            flip=bool(getattr(fx, "element_flip", False))))
    return out


class PanelGridDialog(QDialog):
    """Geraet + Spaltenzahl -> fertiges Matrix-Raster."""

    def __init__(self, candidates, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Raster aus Gerät")
        self._cands = list(candidates or [])

        lay = QVBoxLayout(self)
        form = QFormLayout()
        self._fix_combo = QComboBox()
        for c in self._cands:
            self._fix_combo.addItem(f"{c.label} · {c.head_count} Zonen", c.fid)
        form.addRow("Gerät:", self._fix_combo)

        self._cols_spin = QSpinBox()
        self._cols_spin.setRange(1, 512)
        form.addRow("Spalten:", self._cols_spin)
        lay.addLayout(form)

        self._info = QLabel("")
        self._info.setWordWrap(True)
        lay.addWidget(self._info)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)

        self._fix_combo.currentIndexChanged.connect(self._on_fixture_changed)
        self._cols_spin.valueChanged.connect(self._update_info)
        self._on_fixture_changed()

    # ── Zustand ──────────────────────────────────────────────────────────────

    def candidate(self):
        i = self._fix_combo.currentIndex()
        return self._cands[i] if 0 <= i < len(self._cands) else None

    def _on_fixture_changed(self, *_):
        """Spaltenvorschlag NEU setzen, wenn das Geraet wechselt.

        Ohne das bliebe die Zahl des vorherigen Geraets stehen — bei 48 -> 16
        Zonen waeren das 6 Spalten auf 16 Koepfe, also eine angebrochene Zeile,
        die niemand angefordert hat.
        """
        c = self.candidate()
        self._cols_spin.blockSignals(True)
        if c is not None:
            self._cols_spin.setRange(1, max(1, c.head_count))
            self._cols_spin.setValue(suggested_block_cols(c.head_count))
        self._cols_spin.blockSignals(False)
        self._update_info()

    def _update_info(self, *_):
        c = self.candidate()
        if c is None:
            self._info.setText("Kein Gerät mit mehreren Zonen im Patch.")
            if self._ok_button is not None:
                self._ok_button.setEnabled(False)
            return
        cols, rows, cells = panel_grid(
            c.head_count, self._cols_spin.value(),
            order=c.order, rotation=c.rotation, flip=c.flip)
        luecken = sum(1 for x in cells if x is None)
        text = (f"{c.head_count} Zonen → {rows} Reihen × {cols} Spalten"
                f" · Nummerierung: {PIXEL_ORDER_LABELS.get(c.order, c.order)}"
                f" · Montage: {c.rotation}°"
                + (" · gespiegelt" if c.flip else ""))
        if luecken:
            text += f" · {luecken} Lücken (letzte Zeile angebrochen)"
        self._info.setText(text)
        if self._ok_button is not None:
            self._ok_button.setEnabled(bool(cells))

    def result_grid(self) -> tuple:
        """``(cols, rows, fixture_grid, head_grid)`` — direkt in eine
        ``RgbMatrixInstance`` uebernehmbar.

        Luecken tragen ``None`` im ``fixture_grid``: die Zelle ist raeumlich da,
        steuert aber kein Geraet an. Wuerde dort die fid stehen, faerbte der
        Effekt einen Kopf mit, den es nicht gibt.
        """
        c = self.candidate()
        if c is None:
            return 0, 0, [], []
        cols, rows, cells = panel_grid(
            c.head_count, self._cols_spin.value(),
            order=c.order, rotation=c.rotation, flip=c.flip)
        fixture_grid = [None if h is None else c.fid for h in cells]
        return cols, rows, fixture_grid, list(cells)


class PatternPreview(QWidget):
    """Zeigt die Schritte des Musters — die Vorschau, die im Skript fehlte.

    Sie laeuft in ECHTEN Schritten (Timer, ein Frame je Schritt), nicht als
    Standbild: ob die Kante hart ist und in welche Richtung sie laeuft, sieht
    man nur in Bewegung. Genau das ist der Unterschied zu den
    Matrix-Algorithmen, den der Assistent verkaufen soll.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(90)
        self._cols = 0
        self._rows = 0
        self._frames: list = []
        self._idx = 0
        self._color = (255, 255, 255)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.advance)

    def set_pattern(self, cols, rows, frames, color, interval_ms: int = 120):
        self._cols, self._rows = int(cols), int(rows)
        self._frames = list(frames or [])
        self._color = tuple(color)
        self._idx = 0
        if self._frames:
            self._timer.start(max(20, int(interval_ms)))
        else:
            self._timer.stop()
        self.update()

    @property
    def frames(self) -> list:
        return list(self._frames)

    @property
    def index(self) -> int:
        return self._idx

    def current_cells(self) -> list:
        if not self._frames:
            return []
        return list(self._frames[self._idx % len(self._frames)])

    def advance(self):
        if self._frames:
            self._idx = (self._idx + 1) % len(self._frames)
            self.update()

    def stop(self):
        self._timer.stop()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0d1117"))
        if self._cols < 1 or self._rows < 1:
            return
        lit = set(self.current_cells())
        cw = self.width() / self._cols
        chh = self.height() / self._rows
        on = QColor(*self._color)
        off = QColor("#21262d")
        for r in range(self._rows):
            for c in range(self._cols):
                idx = r * self._cols + c
                p.fillRect(int(c * cw) + 1, int(r * chh) + 1,
                           max(1, int(cw) - 2), max(1, int(chh) - 2),
                           on if idx in lit else off)


class PatternResult:
    """Was der Assistent liefert — genau die vier Angaben aus dem Wunsch
    (Richtung, Breite des Balkens, Farbe, Tempo) plus der Name."""

    def __init__(self, name, direction, width, color, hold):
        self.name = name
        self.direction = direction
        self.width = int(width)
        self.color = tuple(color)
        self.hold = float(hold)


class PatternWizardDialog(QDialog):
    """Muster-Assistent: Richtung, Breite, Farbe, Tempo -> fertiger Chaser."""

    def __init__(self, cols: int, rows: int, default_name: str = "Lauflicht",
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Muster-Assistent")
        self._cols = max(1, int(cols))
        self._rows = max(1, int(rows))
        self._color = (255, 255, 255)

        lay = QVBoxLayout(self)
        form = QFormLayout()

        self._name_edit = QLineEdit(default_name)
        form.addRow("Name:", self._name_edit)

        self._dir_combo = QComboBox()
        for key, label in PATTERN_DIRECTIONS:
            self._dir_combo.addItem(label, key)
        form.addRow("Richtung:", self._dir_combo)

        self._width_spin = QSpinBox()
        self._width_spin.setRange(1, 64)
        self._width_spin.setValue(1)
        self._width_spin.setToolTip(
            "Wie viele Spalten/Reihen gleichzeitig leuchten.")
        form.addRow("Balkenbreite:", self._width_spin)

        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(48, 24)
        self._color_btn.clicked.connect(self._pick_color)
        self._apply_color_style()
        form.addRow("Farbe:", self._color_btn)

        self._tempo_spin = QDoubleSpinBox()
        self._tempo_spin.setRange(0.2, 50.0)
        self._tempo_spin.setDecimals(1)
        self._tempo_spin.setSingleStep(0.5)
        self._tempo_spin.setValue(8.0)
        self._tempo_spin.setSuffix(" Schritte/s")
        form.addRow("Tempo:", self._tempo_spin)
        lay.addLayout(form)

        self._info = QLabel("")
        self._info.setWordWrap(True)
        lay.addWidget(self._info)

        self._preview = PatternPreview()
        lay.addWidget(self._preview)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        self._dir_combo.currentIndexChanged.connect(self._refresh)
        self._width_spin.valueChanged.connect(self._refresh)
        self._tempo_spin.valueChanged.connect(self._refresh)
        self._refresh()

    # ── Zustand ──────────────────────────────────────────────────────────────

    def direction(self) -> str:
        d = self._dir_combo.currentData()
        return d if d else DEFAULT_DIRECTION

    def _apply_color_style(self):
        r, g, b = self._color
        self._color_btn.setStyleSheet(
            f"background: rgb({r},{g},{b}); border:1px solid #30363d;"
            " border-radius:3px;")

    def _pick_color(self):
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(QColor(*self._color), self, "Farbe wählen")
        if c.isValid():
            self.set_color((c.red(), c.green(), c.blue()))

    def set_color(self, rgb):
        """Farbe setzen — auch der Weg, auf dem ein Test sie waehlt, ohne den
        modalen System-Farbdialog zu oeffnen."""
        self._color = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
        self._apply_color_style()
        self._refresh()

    def frames(self) -> list:
        return pattern_frames(self._cols, self._rows, self.direction(),
                              width=self._width_spin.value())

    def _refresh(self, *_):
        """Balkenbreite klemmen und Vorschau/Text nachziehen.

        ★ Die Obergrenze ist die Zahl der BAENDER dieser Richtung, nicht 64: ein
        Balken, der breiter als die Flaeche ist, laeuft umlaufend ueber jede
        Zelle und schaltet damit schlicht alles ein. Das waere kein Lauflicht
        mehr — und der Nutzer saehe nur ein Standbild, ohne zu verstehen warum.
        """
        n = band_count(self._cols, self._rows, self.direction())
        self._width_spin.blockSignals(True)
        self._width_spin.setRange(1, max(1, n))
        self._width_spin.blockSignals(False)
        frames = self.frames()
        hold = self.hold()
        self._info.setText(
            f"{len(frames)} Schritte · je {hold * 1000:.0f} ms"
            f" · Durchlauf {len(frames) * hold:.1f} s"
            f" · Raster {self._rows}×{self._cols}")
        self._preview.set_pattern(self._cols, self._rows, frames, self._color,
                                  interval_ms=int(hold * 1000))

    def hold(self) -> float:
        """Haltezeit je Schritt. Das Tempofeld steht in Schritten pro Sekunde —
        so denkt man an der Konsole; der Chaser rechnet in Sekunden je Schritt."""
        return 1.0 / max(0.2, float(self._tempo_spin.value()))

    def result(self) -> PatternResult:
        return PatternResult(self._name_edit.text().strip() or "Lauflicht",
                             self.direction(), self._width_spin.value(),
                             self._color, self.hold())

    def done(self, code):
        # Vorschau-Timer beim Schliessen stoppen — ein Timer auf einem
        # zerstoerten Widget ist auf Qt-Seite genau die Sorte Teardown-Race,
        # die hier schon einmal Testsegmente gekippt hat.
        self._preview.stop()
        super().done(code)
