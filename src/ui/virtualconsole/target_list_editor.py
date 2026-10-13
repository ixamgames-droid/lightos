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

from src.ui.weak_slots import weak_slot


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


def _all_snaps() -> list[tuple[int, str]]:
    """(id, Anzeigename) aller Show-Bibliothek-Snaps, nach Ordner/Name sortiert."""
    out: list[tuple[int, str]] = []
    try:
        from src.core.engine.snap_library import get_snap_library
        for s in get_snap_library().snaps_sorted():
            name = getattr(s, "name", None) or f"#{s.id}"
            folder = getattr(s, "folder", "") or ""
            label = f"{folder}/{name}  [Snap #{s.id}]" if folder else f"{name}  [Snap #{s.id}]"
            out.append((int(s.id), label))
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
        add.clicked.connect(self._on_add_clicked)
        self._rows_lay.addWidget(add)

        self._refresh_title()

    def _on_add_clicked(self):
        # STAB-09: gehobener Lambda-Body — Connection soll self nicht pinnen.
        self._add_row(None, "")
        self._refresh_title()
        self.changed.emit()

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

    def set_title(self, title: str):
        """Aendert die sichtbare Kopfzeile, ohne die aktuelle Auswahl anzufassen."""
        self._title = title or self._title
        self._refresh_title()

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
        if fid is not None and not any(_id == self._key(fid) for _id, _ in self._func_choices):
            func.addItem(self._fehlt_label(fid), self._key(fid))
        if fid is not None:
            idx = next((i for i in range(func.count()) if func.itemData(i) == self._key(fid)), -1)
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
        func.currentIndexChanged.connect(weak_slot(self._on_func_changed, row))
        dele.clicked.connect(weak_slot(self._remove_row, row))
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

    def _row_fid(self, row):
        data = row["func"].currentData()
        if data is None or data == -1:
            return None
        key = self._key(data)
        return key if not isinstance(key, int) or key >= 0 else None

    # VCB-11: Schluessel-Typ der Zeilen. Basis = Funktions-/Snap-ID (int);
    # Unterklassen mit anderen Zielen (Geraete/Gruppen) ueberschreiben beides.
    @staticmethod
    def _key(value):
        return int(value)

    def _fehlt_label(self, value) -> str:
        return f"#{int(value)} (nicht gefunden)"

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
                fid_i = self._key(fid)
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


class SnapListEditor(TargetListEditor):
    """Aufklappbare Liste fuer Show-Bibliothek-Snaps.

    Gleiche kleine API wie ``TargetListEditor`` (`set_targets`, `ids`), aber die
    Dropdowns zeigen Snap-Namen statt Funktionen. So kann ein Button mehrere
    Looks/Snaps als eine gemeinsame Schaltgruppe behandeln.
    """

    def __init__(self, title: str = "Schaltet Snaps", parent=None):
        super().__init__(with_params=False, title=title, parent=parent)
        self._func_choices = _all_snaps()
        try:
            self.findChild(QPushButton).setText("+ Snap hinzufuegen")
        except Exception:
            pass


def _blackout_gruppen() -> list[tuple[int, str, str]]:
    """VCB-36: ``(id, Name, Ordner)`` aller Fixture-Gruppen; ``[]`` ohne Show-DB."""
    try:
        from sqlalchemy import select
        from src.core.database.models import FixtureGroup
        from src.core.app_state import get_state
        with get_state()._session() as s:
            return [(int(g.id), g.name or "", g.folder or "")
                    for g in s.execute(select(FixtureGroup)).scalars().all()]
    except Exception:
        return []


def _blackout_choices() -> list[tuple[str, str]]:
    """VCB-11: (Schluessel, Anzeigename) aller Fixture-Gruppen und gepatchten
    Geraete — ``"gi:<Gruppen-ID>"`` bzw. ``"f:<fid>"``. Gruppen zuerst (der
    Normalfall „diese Seite der Buehne aus"), danach die Geraete nach fid.

    VCB-36: JEDE Gruppe steht einzeln da, mit ihrer ID als Schluessel. Vorher
    war der Schluessel der Name — zwei Gruppen „PARs“ (Ordner „Front“ und
    „Back“) fielen zu einem Eintrag zusammen. Der Ordner steht im Anzeigenamen;
    heissen zwei Gruppen im selben Ordner gleich, unterscheidet sie die Nummer."""
    out: list[tuple[str, str]] = []
    gruppen = sorted(_blackout_gruppen(),
                     key=lambda g: (g[1].lower(), g[2].lower(), g[0]))
    anzahl: dict[tuple[str, str], int] = {}
    for _gid, name, ordner in gruppen:
        anzahl[(name, ordner)] = anzahl.get((name, ordner), 0) + 1
    for gid, name, ordner in gruppen:
        text = f"Gruppe: {name or '(ohne Namen)'}"
        if ordner:
            text += f"  ({ordner})"
        if not name or anzahl[(name, ordner)] > 1:
            text += f"  [#{gid}]"
        out.append((f"gi:{gid}", text))
    try:
        from src.core.app_state import get_state
        for fx in sorted(get_state().get_patched_fixtures(), key=lambda f: int(f.fid)):
            name = getattr(fx, "label", "") or f"#{fx.fid}"
            out.append((f"f:{int(fx.fid)}", f"Gerät: {name}  [#{int(fx.fid)}]"))
    except Exception:
        pass
    return out


def blackout_ziel_schluessel(fids, groups, group_ids=(), verloren=()) -> list[str]:
    """VCB-11: Ziel einer Taste -> Zeilen-Schluessel des BlackoutTargetEditor
    (Gruppen-IDs, dann Gruppennamen aus alten Layouts, dann Geraete).

    VCB-36: ein alter NAME wird zur ID, wenn genau eine Gruppe so heisst —
    gemeint war dann immer diese, und mit dem naechsten OK speichert die Taste
    die ID. Heissen mehrere so (oder keine), bleibt der Name stehen: welche
    gemeint war, kann nur der Bediener sagen.

    VCB-42: IDs in ``verloren`` bekommen den Schluessel ``gx:<id>`` statt
    ``gi:<id>``. Die Nummer kann inzwischen einer ANDEREN Gruppe gehoeren — mit
    ``gi:`` stuende diese fremde Gruppe als gewaehlt im Dialog, und OK baende
    die Taste an sie."""
    verloren = set(verloren or ())
    je_name: dict[str, list[int]] = {}
    for gid, name, _ordner in _blackout_gruppen():
        je_name.setdefault(name, []).append(gid)
    out: list[str] = []

    def dazu(key: str):
        if key not in out:
            out.append(key)

    for g in (group_ids or []):
        try:
            dazu(f"gx:{int(g)}" if int(g) in verloren else f"gi:{int(g)}")
        except (TypeError, ValueError):
            continue
    for name in (groups or []):
        if not name:
            continue
        treffer = je_name.get(str(name), [])
        dazu(f"gi:{treffer[0]}" if len(treffer) == 1 else f"g:{name}")
    for f in (fids or []):
        try:
            dazu(f"f:{int(f)}")
        except (TypeError, ValueError):
            continue
    return out


class BlackoutTargetEditor(TargetListEditor):
    """VCB-11: Ziel-Liste einer VC-Blackout-Taste — einzelne Geraete und/oder
    Fixture-Gruppen. Leere Liste = globaler Blackout (Bestandsverhalten).

    Gleiche kleine API wie ``TargetListEditor``; die Zeilen-Schluessel sind
    Strings: ``"f:<fid>"``, ``"gi:<Gruppen-ID>"`` und — nur noch fuer Namen aus
    alten Layouts, die sich nicht eindeutig zuordnen lassen — ``"g:<Gruppe>"``.
    ``fids()``/``group_ids()``/``groups()`` liefern die getrennten Listen.

    VCB-42: ``"gx:<Gruppen-ID>"`` ist ein VERLORENES Gruppen-Ziel (die Gruppe
    gibt es nicht mehr, oder die Nummer gehoert jetzt einer anderen). Es steht
    nicht in der Auswahl, nur als Zeile einer Taste, die es noch traegt —
    ``set_verlorene`` liefert dazu, wie die Gruppe hiess."""

    def __init__(self, title: str = "Blackout-Ziel", parent=None):
        super().__init__(with_params=False, title=title, parent=parent)
        self._func_choices = _blackout_choices()
        self._verlorene: dict[int, tuple[str, str]] = {}
        try:
            self.findChild(QPushButton).setText("+ Gerät/Gruppe hinzufügen")
            self._empty_lbl.setText("(kein Ziel = globaler Blackout)")
        except Exception:
            pass

    @staticmethod
    def _key(value):
        v = str(value)
        for vorsatz in ("gi:", "gx:", "f:", "g:"):
            if v.startswith(vorsatz) and len(v) > len(vorsatz):
                return v
        raise ValueError(v)

    def set_verlorene(self, gruppen: dict):
        """VCB-42: ``{Gruppen-ID: (Name, Ordner)}`` der verlorenen Ziele — fuer
        die Beschriftung ihrer ``gx:``-Zeilen. VOR ``set_targets`` aufrufen."""
        self._verlorene = {int(g): (str(n or ""), str(o or ""))
                           for g, (n, o) in (gruppen or {}).items()}

    def _fehlt_label(self, value) -> str:
        v = str(value)
        if v.startswith("gx:"):
            # VCB-42: mit dem Namen, den die Gruppe HATTE — nicht mit dem der
            # Gruppe, die die Nummer jetzt traegt.
            try:
                name, ordner = self._verlorene.get(int(v[3:]), ("", ""))
            except ValueError:
                name, ordner = "", ""
            text = f"Gruppe: {name}" if name else f"Gruppe #{v[3:]}"
            if ordner:
                text += f"  ({ordner})"
            return (f"{text} — verloren (gelöscht oder aus einer anderen Show), "
                    f"bitte neu wählen")
        if v.startswith("gi:"):
            return f"Gruppe #{v[3:]} (nicht gefunden)"
        if v.startswith("g:"):
            # VCB-36: ein Name aus einem alten Layout. Eindeutige sind schon zur
            # ID geworden (``blackout_ziel_schluessel``) — hier steht, warum
            # dieser es nicht ist.
            name = v[2:]
            gleiche = sum(1 for _gid, n, _o in _blackout_gruppen() if n == name)
            if gleiche > 1:
                return (f"Gruppe: {name} (mehrdeutig — {gleiche} Gruppen heißen so, "
                        f"bitte neu wählen)")
            return f"Gruppe: {name}" if gleiche == 1 else f"Gruppe: {name} (nicht gefunden)"
        return f"Gerät: {v[2:]} (nicht gefunden)"

    def fids(self) -> list[int]:
        out: list[int] = []
        for k in self.ids():
            if k.startswith("f:"):
                try:
                    out.append(int(k[2:]))
                except ValueError:
                    continue
        return out

    def group_ids(self) -> list[int]:
        """VCB-36: die gewaehlten Gruppen, je ueber ihre ID."""
        out: list[int] = []
        for k in self.ids():
            if k.startswith("gi:"):
                try:
                    out.append(int(k[3:]))
                except ValueError:
                    continue
        return out

    def verlorene_ids(self) -> list[int]:
        """VCB-42: die verlorenen Gruppen-Ziele, die als Zeile stehen geblieben
        sind — die Taste behaelt sie (und bleibt damit ein Ziel-Blackout)."""
        out: list[int] = []
        for k in self.ids():
            if k.startswith("gx:"):
                try:
                    out.append(int(k[3:]))
                except ValueError:
                    continue
        return out

    def groups(self) -> list[str]:
        """Gruppen-NAMEN aus alten Layouts, die keine eindeutige ID bekamen."""
        return [k[2:] for k in self.ids() if k.startswith("g:")]
