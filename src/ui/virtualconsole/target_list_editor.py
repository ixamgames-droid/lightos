"""Aufklappbare „Steuert"-Liste fuer VC-Widget-Dialoge.

Statt nur roher Function-ID-/Slot-Textfelder zeigt diese Komponente eine lesbare,
aufklappbare Liste der Funktionen/Effekte, auf die ein Widget wirkt. Jede Zeile:
  [ Funktion/Effekt (Name-Combo) ]  [ Parameter (Combo, optional) ]  [ ✕ ]
plus „+ Hinzufuegen". So kann der Nutzer pro Eintrag auswaehlen, was gesteuert wird,
und Eintraege loeschen — wie es der BPM/Speed-Dial bereits per Effekt-Parameter hat.

Qt-Schicht; Funktions-/Parameter-Metadaten kommen aus vc_effect_meta + function_manager.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QToolButton, QPushButton, QLabel,
)
from PySide6.QtCore import Qt, Signal


def _all_functions() -> list[tuple[int, str]]:
    """(id, Anzeigename) aller Funktionen, nach Name sortiert. Qt-frei nutzbar."""
    out: list[tuple[int, str]] = []
    try:
        from src.core.app_state import get_state
        funcs = get_state().function_manager.all()
        for f in sorted(funcs, key=lambda x: (getattr(x, "name", "") or "").lower()):
            ftype = getattr(getattr(f, "function_type", None), "value", "")
            name = getattr(f, "name", None) or f"#{f.id}"
            label = f"{name}  [{ftype} #{f.id}]" if ftype else f"{name}  [#{f.id}]"
            out.append((int(f.id), label))
    except Exception:
        pass
    return out


class TargetListEditor(QWidget):
    """Aufklappbare Liste der gesteuerten Funktionen/Effekte (+ optional Parameter).

    - ``with_params=True`` blendet je Zeile eine Parameter-Combo ein (Fader/Dial-Ziele).
    - ``set_targets(ids, param_keys)`` befuellt die Liste.
    - ``ids()`` / ``param_keys()`` liefern die aktuelle Auswahl zurueck.
    """

    changed = Signal()

    def __init__(self, with_params: bool = False, title: str = "Steuert", parent=None):
        super().__init__(parent)
        self._with_params = with_params
        self._title = title
        self._func_choices = _all_functions()
        self._rows: list[dict] = []   # je Zeile: {"box","func","param","del"}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        # Aufklapp-Kopf
        self._toggle = QToolButton()
        self._toggle.setCheckable(True)
        self._toggle.setChecked(True)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow)
        self._toggle.setStyleSheet("QToolButton { border: none; font-weight: bold; }")
        self._toggle.toggled.connect(self._on_toggle)
        root.addWidget(self._toggle)

        # Zeilen-Container
        self._body = QWidget()
        self._rows_lay = QVBoxLayout(self._body)
        self._rows_lay.setContentsMargins(12, 0, 0, 0)
        self._rows_lay.setSpacing(2)
        root.addWidget(self._body)

        self._empty_lbl = QLabel("(noch nichts zugewiesen)")
        self._empty_lbl.setStyleSheet("color: gray; font-style: italic;")
        self._rows_lay.addWidget(self._empty_lbl)

        add = QPushButton("+ Funktion/Effekt hinzufügen")
        add.clicked.connect(lambda: (self._add_row(None, ""), self._refresh_title(),
                                     self.changed.emit()))
        self._rows_lay.addWidget(add)

        self._refresh_title()

    # ── Aufklappen ────────────────────────────────────────────────────────────
    def _on_toggle(self, checked: bool):
        self._body.setVisible(checked)
        self._toggle.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

    def _refresh_title(self):
        n = len([r for r in self._rows if self._row_fid(r) is not None])
        self._title_n = n
        self._toggle.setText(f"{self._title} ({n})")
        self._empty_lbl.setVisible(n == 0)

    # ── Zeilen ──────────────────────────────────────────────────────────────────
    def _add_row(self, fid, param_key: str):
        box = QWidget()
        hl = QHBoxLayout(box)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(4)

        func = QComboBox()
        func.addItem("(leer)", -1)
        for _id, _lbl in self._func_choices:
            func.addItem(_lbl, _id)
        # gespeicherte, aber nicht (mehr) gelistete ID dennoch zeigen
        if fid is not None and not any(_id == int(fid) for _id, _ in self._func_choices):
            func.addItem(f"#{int(fid)} (nicht gefunden)", int(fid))
        if fid is not None:
            idx = next((i for i in range(func.count()) if func.itemData(i) == int(fid)), -1)
            if idx >= 0:
                func.setCurrentIndex(idx)
        hl.addWidget(func, 2)

        param = None
        if self._with_params:
            param = QComboBox()
            param.setEditable(True)
            hl.addWidget(param, 2)

        dele = QToolButton()
        dele.setText("✕")
        dele.setToolTip("Diesen Eintrag entfernen")
        hl.addWidget(dele)

        row = {"box": box, "func": func, "param": param}
        self._rows.append(row)
        # vor dem „+"-Button einfuegen (Add-Button ist immer letztes Element)
        self._rows_lay.insertWidget(self._rows_lay.count() - 1, box)

        if param is not None:
            self._reload_params(row, param_key)
        func.currentIndexChanged.connect(lambda _i, r=row: self._on_func_changed(r))
        dele.clicked.connect(lambda _c=False, r=row: self._remove_row(r))
        return row

    def _on_func_changed(self, row):
        # Duplikate verhindern: ist der gewaehlte Effekt schon in einer ANDEREN Zeile,
        # diese Zeile auf „(leer)" zuruecksetzen (sonst gingen beim Speichern Parameter
        # still verloren, da ids()/param_keys() pro ID nur einmal zaehlen).
        fid = self._row_fid(row)
        if fid is not None:
            for other in self._rows:
                if other is not row and self._row_fid(other) == fid:
                    row["func"].blockSignals(True)
                    row["func"].setCurrentIndex(0)   # „(leer)"
                    row["func"].blockSignals(False)
                    break
        if row.get("param") is not None:
            self._reload_params(row, "")
        self._refresh_title()
        self.changed.emit()

    def _reload_params(self, row, current: str):
        param: QComboBox = row["param"]
        param.blockSignals(True)
        param.clear()
        param.addItem("(Standard)", "")
        fid = self._row_fid(row)
        keys: list[str] = []
        if fid is not None:
            try:
                from .vc_effect_meta import mappable_param_choices
                for k, lbl in mappable_param_choices(fid):
                    param.addItem(f"{lbl}  ({k})", k)
                    keys.append(k)
            except Exception:
                pass
        if current and current not in keys:
            param.addItem(current, current)
        idx = next((i for i in range(param.count()) if param.itemData(i) == current), -1)
        if idx >= 0:
            param.setCurrentIndex(idx)
        elif current:
            param.setCurrentText(current)
        else:
            param.setCurrentIndex(0)
        param.blockSignals(False)

    def _remove_row(self, row):
        try:
            self._rows.remove(row)
        except ValueError:
            return
        row["box"].setParent(None)
        row["box"].deleteLater()
        self._refresh_title()
        self.changed.emit()

    @staticmethod
    def _row_fid(row):
        data = row["func"].currentData()
        return int(data) if data is not None and int(data) >= 0 else None

    @staticmethod
    def _row_param(row) -> str:
        param = row.get("param")
        if param is None:
            return ""
        hit = param.findText(param.currentText().strip())
        val = param.itemData(hit) if hit >= 0 else None
        if val is None:
            val = param.currentText().strip()
        return str(val or "")

    # ── Public API ──────────────────────────────────────────────────────────────
    def set_targets(self, ids, param_keys: dict | None = None):
        """Liste neu aufbauen aus IDs (+ optional je-ID Parameter)."""
        for r in list(self._rows):
            self._remove_row(r)
        param_keys = param_keys or {}
        _seen: set[int] = set()
        for fid in (ids or []):
            try:
                fid_i = int(fid)
            except (TypeError, ValueError):
                continue
            if fid_i in _seen:        # Duplikate beim Befuellen ueberspringen
                continue
            _seen.add(fid_i)
            try:
                self._add_row(fid_i, str(param_keys.get(fid_i, param_keys.get(str(fid_i), ""))))
            except Exception:
                # eine defekte Zeile darf den restlichen Aufbau nicht abbrechen
                continue
        self._refresh_title()

    def ids(self) -> list[int]:
        """Gesteuerte Funktions-IDs in Zeilen-Reihenfolge (leere Zeilen entfallen)."""
        out: list[int] = []
        for r in self._rows:
            fid = self._row_fid(r)
            if fid is not None and fid not in out:
                out.append(fid)
        return out

    def param_keys(self) -> dict[int, str]:
        """Je gesteuerter ID der gewaehlte Parameter-Key ('' = Standard)."""
        out: dict[int, str] = {}
        for r in self._rows:
            fid = self._row_fid(r)
            if fid is None:
                continue
            key = self._row_param(r)
            if key:
                out[fid] = key
        return out
