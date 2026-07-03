"""VCDropPanel — Checkbox-Mehrfachauswahl beim Reinziehen eines Effekts (eigenes
Fenster, ersetzt die fruehere 3-stufige Modal-Kette des SmartDropDialog).

Ablauf: Effekt aufs leere Canvas ziehen -> diese Karte. Eine Zeile je steuerbarem
Aspekt (aus ``vc_effect_meta.control_options`` — intelligent pro Effekttyp), als
ANKREUZBARE Checkbox. „An/Aus" ist vorangekreuzt (Standardfall = ein Klick auf
„Erstellen" liefert einen An/Aus-Button). Mehrere Haekchen = mehrere fertig
verdrahtete Widgets in EINEM Undo (``VCCanvas.build_from_smart_results``). Pro
Aspekt mit mehreren passenden Widget-Typen gibt es „Widget waehlen" -> grafische
``VCWidgetGallery``. Selten gebrauchte Parameter/Aktionen liegen aufgeklappt unter
„Mehr Parameter".

Die Karte hat KEINE Faehigkeits-/Mapping-Logik: Optionen kommen aus
``control_options``, der Default-Widget-Typ aus ``recommended_widget``, die
Option->Result-Abbildung aus ``SmartDropDialog._result_for`` (eine Quelle).
"""
from __future__ import annotations

import weakref

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QGridLayout, QLabel,
                               QCheckBox, QPushButton, QWidget, QDialogButtonBox,
                               QScrollArea)

from .vc_effect_meta import (function_capabilities, control_options,
                             widget_choices, recommended_widget, ControlKind,
                             WIDGET_TYPE_LABELS)

# Aspekte, die direkt (oben) erscheinen; der Rest wandert unter „Mehr Parameter".
_PRIMARY_KINDS = (ControlKind.TOGGLE, ControlKind.FLASH, ControlKind.TEMPO,
                  ControlKind.INTENSITY, ControlKind.COLORS, ControlKind.MOVEMENT,
                  ControlKind.TEMPO_BUS, ControlKind.TEMPO_MULT)


class _AspectRow:
    """Eine Aspekt-Zeile: Checkbox + (optional) Widget-Wahl ueber die Galerie."""

    def __init__(self, option, grid: QGridLayout, row: int, parent: QWidget):
        self.option = option
        self.choices = widget_choices(option)
        self.widget_type = recommended_widget(option)
        # SCHWACH: parent ist der Dialog, der diese Zeile in _rows hält — eine
        # starke Ref wäre ein Referenz-Zyklus (Dialog stirbt dann nur über die
        # zyklische GC statt per Refcount; Crash-Klasse STAB-09).
        self._parent_ref = weakref.ref(parent)

        self.check = QCheckBox(option.label)
        if option.kind == ControlKind.TOGGLE:
            self.check.setChecked(True)        # Standardfall vorangekreuzt
        grid.addWidget(self.check, row, 0)

        self.btn = QPushButton()
        if len(self.choices) > 1:
            self.btn.clicked.connect(self._pick)
        else:
            self.btn.setEnabled(False)
        self._refresh_btn()
        grid.addWidget(self.btn, row, 1)

    def _label_for(self, wt: str) -> str:
        return WIDGET_TYPE_LABELS.get(wt, wt)

    def _refresh_btn(self):
        if len(self.choices) > 1:
            self.btn.setText(f"Widget: {self._label_for(self.widget_type)}  ▸ ändern")
        elif self.widget_type and self.widget_type != "BULK":
            self.btn.setText(self._label_for(self.widget_type))
        else:
            self.btn.setText("—")

    def _pick(self):
        from .vc_widget_gallery import VCWidgetGallery
        chosen = VCWidgetGallery(self.choices, current=self.widget_type,
                                 parent=self._parent_ref()).run()
        if chosen:
            self.widget_type = chosen
            self._refresh_btn()

    def result(self, function_id, name):
        """SmartDropResult fuer diese Zeile (nur wenn angekreuzt) — sonst None."""
        if not self.check.isChecked():
            return None
        from .smart_drop_dialog import SmartDropDialog
        return SmartDropDialog(function_id)._result_for(
            self.option, self.widget_type, name)


class VCDropPanel(QDialog):
    """Checkbox-Karte: waehle, was der gedroppte Effekt koennen soll."""

    def __init__(self, function_id, parent=None, for_box: bool = False):
        super().__init__(parent)
        self._fid = int(function_id)
        self._for_box = bool(for_box)
        self.box_mode = False
        caps = function_capabilities(self._fid)
        self._name = caps.name or f"#{self._fid}"
        # Aus einer bestehenden Effekt-Box heraus (⚙) ist die Box-Gruppierung schon
        # gegeben -> Titel + ausgeblendete Gruppieren-Checkbox.
        self.setWindowTitle("Bedienelemente wählen" if self._for_box else "Effekt einrichten")
        self.setMinimumWidth(360)

        # BULK (Sammel-Option) passt nicht ins Aspekt-Ankreuz-Modell -> raus.
        opts = [o for o in control_options(caps) if o.kind != ControlKind.BULK]
        primary = [o for o in opts if o.kind in _PRIMARY_KINDS]
        advanced = [o for o in opts if o.kind not in _PRIMARY_KINDS]

        v = QVBoxLayout(self)
        intro = (f'„{self._name}" direkt verknüpfen — es wird kein neuer Effekt '
                 "erzeugt. Welche Bedienelemente brauchst du?")
        if caps.channel_scope:
            intro += f"\nKanalbereich: {caps.channel_scope}."
        label = QLabel(intro)
        label.setWordWrap(True)
        v.addWidget(label)

        self._rows: list[_AspectRow] = []

        prim_grid = QGridLayout()
        prim_grid.setColumnStretch(0, 1)
        for i, opt in enumerate(primary):
            self._rows.append(_AspectRow(opt, prim_grid, i, self))
        prim_host = QWidget()
        prim_host.setLayout(prim_grid)
        v.addWidget(prim_host)

        if advanced:
            adv_grid = QGridLayout()
            adv_grid.setColumnStretch(0, 1)
            for i, opt in enumerate(advanced):
                self._rows.append(_AspectRow(opt, adv_grid, i, self))
            adv_host = QWidget()
            adv_host.setLayout(adv_grid)
            # In einen flachen Scrollbereich, falls es viele Parameter sind.
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(adv_host)
            scroll.setMaximumHeight(220)
            from src.ui.widgets.collapsible_section import CollapsibleSection
            v.addWidget(CollapsibleSection(
                f"Mehr Parameter ({len(advanced)})", scroll, collapsed=True,
                prefs_key="vc_drop_panel_more"))

        # Welle 4 (N): Wahl Box vs. einzelne Regler. Angekreuzt -> alle erzeugten
        # Widgets landen in einem beweglichen Effekt-Editor-Container mit Live-Vorschau.
        # Aus einer bestehenden Box heraus (for_box) entfaellt die Wahl.
        self._box_cb = None
        if not self._for_box:
            from PySide6.QtWidgets import QCheckBox
            self._box_cb = QCheckBox("Als Effekt-Box gruppieren (verschiebbar, mit Live-Vorschau)")
            self._box_cb.setToolTip("Alle gewählten Bedien-Elemente in EINEN beweglichen "
                                    "Container mit Live-Vorschau legen — statt einzeln aufs Canvas.")
            v.addWidget(self._box_cb)

        btns = QDialogButtonBox()
        ok = btns.addButton("Erstellen", QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setDefault(True)
        btns.addButton(QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

    # ── Ergebnis ──────────────────────────────────────────────────────────────

    def results(self) -> list:
        """Liste der SmartDropResults aus den angekreuzten Aspekten (testbar
        ohne exec — Checkboxen direkt setzen, dann aufrufen)."""
        out = []
        for row in self._rows:
            res = row.result(self._fid, self._name)
            if res is not None:
                out.append(res)
        return out

    def run(self) -> "list | None":
        if self.exec() == QDialog.DialogCode.Accepted:
            self.box_mode = bool(self._box_cb is not None and self._box_cb.isChecked())
            return self.results()
        return None
