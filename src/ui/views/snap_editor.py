"""Snap-Editor — Bearbeiten eines Bibliotheks-Snaps (programmierte Kanalwerte).

Snaps haben keinen Programmer-Editor wie Szenen/Matrix (sie speichern fertige
Werte). Dieser Overlay zeigt die tatsaechlich programmierten Geraete/Attribute —
**nach Geraetetyp gruppiert** (eine Karte je Modell) — mit aufgeloestem
Kanalnamen + DMX-Adresse und laesst die Werte direkt aendern, Eintraege
entfernen sowie **nachtraeglich Geraete und Kanaele hinzufuegen** (David-Wunsch
2026-06-22):

  * **Gerät hinzufügen** — listet nur **kompatible** gepatchte Geraete (die alle
    im Snap angesteuerten Attribut-Gruppen koennen; ein PAR ohne Pan/Tilt taucht
    bei einem Bewegungs-Snap also NICHT auf). Neue Geraete uebernehmen die Werte
    eines bereits im Snap vorhandenen Geraets gleichen Typs (Fallback 0).
  * **Kanal hinzufügen** (pro Typ-Karte) — fuellt einen vergessenen Kanal (z. B.
    Shutter/„Schalter" oder den Rot-Kanal) bei allen Geraeten des Typs nach, die
    ihn noch nicht haben, mit einem gemeinsam gewaehlten Wert.

Mutationen laufen ueber die SnapLibrary-API (set_snap_value/remove_snap_attr);
weil der Snap das Live-Objekt der Singleton-Bibliothek ist, wird die Aenderung
mit der Show gespeichert (kein extra Save-Hook noetig).
"""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QSpinBox, QHeaderView, QAbstractItemView,
    QScrollArea, QFrame, QDialog, QTreeWidget, QTreeWidgetItem,
    QDialogButtonBox, QCheckBox, QComboBox, QMessageBox,
)
from PySide6.QtCore import Qt

from src.core.app_state import get_state, get_channels_for_patched
from src.core.engine.snap_library import get_snap_library
from src.core.attr_groups import (  # kanonisch, kein Zyklus
    classify_attr as _classify_attr,
    attr_label as _attr_label,
)
from src.ui.weak_slots import weak_slot, weak_slot_fwd


_COLS = ["Gerät", "Kanal", "Gruppe", "DMX", "Wert", ""]


# ── Reine Logik (ohne Qt/DB testbar) ──────────────────────────────────────────

def base_attr(attr: str) -> str:
    """Basis-Attribut ohne Mehrkopf-Suffix: ``"color_r#1"`` -> ``"color_r"``."""
    return (attr or "").split("#", 1)[0].lower()


def fixture_caps(channels) -> set[str]:
    """Menge der vom Geraet unterstuetzten Basis-Attribut-Namen (aus seinen
    Kanaelen). ``raw``/leere Attribute werden ignoriert. Mehrfach-Koepfe
    (z. B. Spider mit 2x ``color_r``) zaehlen als EIN Basis-Attribut — fuer die
    Gruppen-Kompatibilitaet ([[is_compatible]]) reicht das."""
    out: set[str] = set()
    for ch in channels:
        a = (getattr(ch, "attribute", "") or "").lower()
        if a and a != "raw":
            out.add(a)
    return out


def fixture_channel_keys(channels) -> list[str]:
    """Pro-Kopf-Schluessel des Geraets in Snap-Konvention: das erste Vorkommen
    eines Attributs ist der Basis-Name, jedes weitere bekommt ``#N`` (Kopf-Index).

    Spiegelt ``AppState.set_programmer_value`` (head>0 -> ``"attr#head"``): ein
    Spider mit zwei ``color_r``-Kanaelen liefert ``["color_r", "color_r#1", …]``.
    So lassen sich beim „Kanal hinzufuegen" auch zweite Koepfe nachtragen.

    Gleiche Vorkommens-Logik wie ``app_state.channel_occurrence_keys`` (die kanonische
    Quelle); hier zusaetzlich ``.lower()`` + ``"raw"``/leer-Filter fuer die Editor-
    Anzeige — daher eine eigene, bewusst defensive Schleife statt direktem Aufruf."""
    seen: dict[str, int] = {}
    keys: list[str] = []
    for ch in channels:
        a = (getattr(ch, "attribute", "") or "").lower()
        if not a or a == "raw":
            continue
        n = seen.get(a, 0)
        keys.append(a if n == 0 else f"{a}#{n}")
        seen[a] = n + 1
    return keys


def snap_controlled_attrs(values: dict) -> set[str]:
    """Alle vom Snap angesteuerten Basis-Attribute (ueber alle Geraete)."""
    return {base_attr(a) for attrs in values.values() for a in attrs}


def snap_controlled_groups(values: dict) -> set[str]:
    """Alle vom Snap angesteuerten Attribut-Gruppen (Intensity/Color/…)."""
    return {_classify_attr(a) for a in snap_controlled_attrs(values)}


def caps_support_group(caps: set[str], group: str) -> bool:
    """True, wenn das Geraet mindestens einen Kanal dieser Gruppe hat."""
    return any(_classify_attr(a) == group for a in caps)


def is_compatible(caps: set[str], controlled_groups: set[str]) -> bool:
    """Ein Geraet ist kompatibel, wenn es JEDE vom Snap angesteuerte
    Attribut-Gruppe bedienen kann (Gruppen-Ebene, nicht Einzelkanal — RGB/Weiß/
    Shutter haben fast alle, Bewegung nur Mover)."""
    return all(caps_support_group(caps, g) for g in controlled_groups)


def values_for_new_device(template_values: dict | None, caps: set[str],
                          controlled_attrs: set[str]) -> dict[str, int]:
    """Werte fuer ein neu in den Snap aufgenommenes Geraet.

    Bevorzugt werden die Werte eines bereits vorhandenen Geraets **gleichen Typs**
    (``template_values``) uebernommen — beschraenkt auf Kanaele, die das neue
    Geraet ueberhaupt hat. Gibt es kein Vorbild, bekommen die angesteuerten
    Kanaele den Wert 0 (manuell nachstellbar)."""
    if template_values:
        return {a: int(v) for a, v in template_values.items()
                if base_attr(a) in caps}
    return {a: 0 for a in sorted(controlled_attrs) if a in caps}


def addable_channels(type_caps: set[str], present_on_all: set[str]) -> list[str]:
    """Kanaele eines Typs, die noch nicht bei ALLEN Geraeten des Typs vorhanden
    sind — also nachtraeglich hinzufuegbar. Stabil sortiert fuer die UI."""
    return sorted(a for a in type_caps if a not in present_on_all)


def fixture_type_key(fx) -> tuple:
    """Identitaet eines Geraetetyps: gleiches Profil + Mode + Kanalzahl =
    identisches Kanal-Layout."""
    return (getattr(fx, "fixture_profile_id", None),
            getattr(fx, "mode_name", None),
            getattr(fx, "channel_count", None))


def fixture_type_label(fx) -> str:
    """Menschenlesbarer Typ-Name (Hersteller + Modell + Mode/Kanalzahl)."""
    man = (getattr(fx, "manufacturer_name", "") or "").strip()
    name = (getattr(fx, "fixture_name", "") or getattr(fx, "label", "")
            or "Gerät").strip()
    mode = (getattr(fx, "mode_name", "") or "").strip()
    head = f"{man} {name}".strip() if man else name
    if mode:
        return f"{head} · {mode}"
    cc = getattr(fx, "channel_count", None)
    return f"{head} · {cc}ch" if cc else head


# ── Dialog: Gerät hinzufügen ───────────────────────────────────────────────────

class _AddDeviceDialog(QDialog):
    """Listet kompatible, noch nicht im Snap enthaltene Geraete (nach Typ
    gruppiert) zum Ankreuzen."""

    def __init__(self, candidates_by_type: list[tuple[str, list[tuple]]], parent=None):
        # candidates_by_type: [(type_label, [(fid, device_label, dmx_hint), ...]), ...]
        super().__init__(parent)
        self.setWindowTitle("Gerät hinzufügen")
        self.setMinimumWidth(420)
        self.setMinimumHeight(360)
        self._fid_items: list[tuple[QTreeWidgetItem, int]] = []
        self._setup_ui(candidates_by_type)

    def _setup_ui(self, candidates_by_type):
        v = QVBoxLayout(self)
        info = QLabel("Kompatible Geräte (passen zu allen im Snap gesteuerten "
                      "Gruppen). Übernehmen die Werte eines gleichartigen Geräts "
                      "im Snap.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #8b949e; font-size: 11px;")
        v.addWidget(info)

        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        v.addWidget(tree, 1)

        if not candidates_by_type:
            tree.setEnabled(False)
            empty = QTreeWidgetItem(tree, ["Keine kompatiblen Geräte verfügbar."])
            empty.setForeground(0, Qt.GlobalColor.gray)
        for type_label, devices in candidates_by_type:
            parent = QTreeWidgetItem(tree, [f"{type_label}  ({len(devices)})"])
            parent.setFlags(parent.flags() | Qt.ItemFlag.ItemIsUserCheckable
                            | Qt.ItemFlag.ItemIsAutoTristate)
            parent.setCheckState(0, Qt.CheckState.Unchecked)
            parent.setExpanded(True)
            for fid, dev_label, dmx_hint in devices:
                child = QTreeWidgetItem(parent, [f"{dev_label}{dmx_hint}"])
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                child.setCheckState(0, Qt.CheckState.Unchecked)
                self._fid_items.append((child, int(fid)))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)

    def selected_fids(self) -> list[int]:
        return [fid for item, fid in self._fid_items
                if item.checkState(0) == Qt.CheckState.Checked]


# ── Dialog: Kanal hinzufügen (pro Typ) ─────────────────────────────────────────

class _AddChannelDialog(QDialog):
    """Waehlt nachzutragende Kanaele eines Typs + einen gemeinsamen Wert."""

    def __init__(self, type_label: str, addable: list[str], n_devices: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kanal hinzufügen")
        self.setMinimumWidth(340)
        self._checks: dict[str, QCheckBox] = {}
        self._setup_ui(type_label, addable, n_devices)

    def _setup_ui(self, type_label: str, addable: list[str], n_devices: int):
        v = QVBoxLayout(self)
        head = QLabel(f"{type_label} — {n_devices} Gerät(e)")
        head.setStyleSheet("font-weight: bold;")
        v.addWidget(head)

        if not addable:
            v.addWidget(QLabel("Alle vom Typ unterstützten Kanäle sind bereits im Snap."))
        else:
            v.addWidget(QLabel("Welche Kanäle nachtragen?"))
            for attr in addable:
                grp = _classify_attr(attr)
                cb = QCheckBox(f"{_attr_label(attr)}  ·  {grp}")
                v.addWidget(cb)
                self._checks[attr] = cb

            row = QHBoxLayout()
            row.addWidget(QLabel("Wert (für alle):"))
            self._value = QSpinBox()
            self._value.setRange(0, 255)
            self._value.setValue(0)
            row.addWidget(self._value)
            row.addStretch(1)
            v.addLayout(row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)

    def selected_attrs(self) -> list[str]:
        return [attr for attr, cb in self._checks.items() if cb.isChecked()]

    def value(self) -> int:
        return int(self._value.value()) if hasattr(self, "_value") else 0


# ── Editor ─────────────────────────────────────────────────────────────────────

class SnapEditor(QWidget):
    """Nach Geraetetyp gruppierter Editor fuer die programmierten Werte EINES Snaps."""

    def __init__(self, snap, parent=None):
        super().__init__(parent)
        self._snap = snap
        self._building = False
        self._caps_cache: dict[int, set[str]] = {}
        self._setup_ui()
        self._load()

    def _lib(self):
        try:
            return get_snap_library()
        except Exception:
            return None

    # ── Aufbau ────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(6)

        hdr = QHBoxLayout()
        self._title = QLabel()
        self._title.setStyleSheet("font-weight: bold;")
        hdr.addWidget(self._title)
        hdr.addStretch(1)
        b_add = QPushButton("➕ Gerät hinzufügen")
        b_add.setFixedHeight(24)
        b_add.setToolTip("Ein kompatibles gepatchtes Gerät nachträglich in den Snap aufnehmen.")
        b_add.clicked.connect(self._add_device)
        hdr.addWidget(b_add)
        b_prev = QPushButton("Vorschau senden")
        b_prev.setFixedHeight(24)
        b_prev.setToolTip("Den Snap in den Programmer laden (auf der Bühne sichtbar machen).")
        b_prev.clicked.connect(self._preview)
        hdr.addWidget(b_prev)
        v.addLayout(hdr)

        # Scrollbereich mit je einer Karte pro Geraetetyp.
        self._tables: list[QTableWidget] = []   # je Typ-Karte eine Tabelle
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._cards_host = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_host)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(8)
        self._scroll.setWidget(self._cards_host)
        v.addWidget(self._scroll, 1)

        self._info = QLabel()
        self._info.setStyleSheet("color: #8b949e; font-size: 11px;")
        self._info.setWordWrap(True)
        v.addWidget(self._info)

    # ── Geraete-/Kanal-Aufloesung ──────────────────────────────────────────────

    def _fixtures(self) -> dict:
        try:
            return {f.fid: f for f in get_state().get_patched_fixtures()}
        except Exception:
            return {}

    def _channels(self, fx):
        try:
            return list(get_channels_for_patched(fx))
        except Exception:
            return []

    def _caps(self, fx) -> set[str]:
        fid = getattr(fx, "fid", None)
        if fid in self._caps_cache:
            return self._caps_cache[fid]
        caps = fixture_caps(self._channels(fx))
        if fid is not None:
            self._caps_cache[fid] = caps
        return caps

    def _resolve(self, fx, attr: str):
        """(Gerätelabel, Kanalname, DMX-Adresse|None) fuer ein fid+attr.

        Mehrkopf: ``attr#N`` loest auf den **N-ten** Kanal mit diesem Basis-
        Attribut auf (nicht stur den ersten) — sonst zeigte z. B. ``color_r#1``
        eines Spiders faelschlich Adresse/Name des ersten Banks."""
        if fx is None:
            return ("<nicht gepatcht>", attr, None)
        label = getattr(fx, "label", None) or f"FID {getattr(fx, 'fid', '?')}"
        chan_name, dmx = _attr_label(attr), None
        base, sep, head = attr.partition("#")
        base = base.lower()
        head_idx = int(head) if (sep and head.isdigit()) else 0
        try:
            seen = 0
            for ch in self._channels(fx):
                if (ch.attribute or "").lower() == base:
                    if seen == head_idx:
                        chan_name = ch.name or _attr_label(attr)
                        dmx = int(fx.address) + int(ch.channel_number) - 1
                        break
                    seen += 1
        except (TypeError, ValueError, AttributeError):
            pass
        return (label, chan_name, dmx)

    # ── Laden / Anzeige ─────────────────────────────────────────────────────────

    def total_rows(self) -> int:
        """Summe der programmierten Kanal-Zeilen über alle Typ-Karten."""
        return sum(t.rowCount() for t in self._tables)

    def _load(self):
        self._building = True
        self._title.setText(f"Snap: {self._snap.name}")
        fixtures = self._fixtures()
        self._tables = []

        # leeren
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        # Geraete des Snaps nach Typ gruppieren (gepatchte zuerst, dann nach Typ-Label).
        by_type: dict[tuple, list[int]] = {}
        type_label_of: dict[tuple, str] = {}
        ungepatcht: list[int] = []
        for fid in self._snap.values.keys():
            fx = fixtures.get(int(fid))
            if fx is None:
                ungepatcht.append(int(fid))
                continue
            tkey = fixture_type_key(fx)
            by_type.setdefault(tkey, []).append(int(fid))
            type_label_of.setdefault(tkey, fixture_type_label(fx))

        n_rows = 0
        for tkey in sorted(by_type, key=lambda k: type_label_of[k].lower()):
            fids = sorted(by_type[tkey])
            n_rows += self._add_type_card(type_label_of[tkey], tkey, fids, fixtures)

        if ungepatcht:
            n_rows += self._add_type_card("Nicht (mehr) gepatcht", None,
                                          sorted(ungepatcht), fixtures)

        if not self._snap.values:
            empty = QLabel("Dieser Snap enthält noch keine Werte. "
                           "Über „➕ Gerät hinzufügen“ Geräte aufnehmen.")
            empty.setStyleSheet("color: #8b949e;")
            self._cards_layout.addWidget(empty)

        self._cards_layout.addStretch(1)
        ndev = len(self._snap.values)
        self._info.setText(
            f"{n_rows} programmierte Kanäle auf {ndev} Gerät(en), "
            f"gruppiert nach Typ. DMX-Strich = Gerät nicht (mehr) gepatcht.")
        self._building = False

    def _add_type_card(self, type_label: str, tkey, fids: list[int], fixtures: dict) -> int:
        """Baut eine Typ-Karte (Kopf + Tabelle) und gibt die Zeilenzahl zurueck."""
        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        cv = QVBoxLayout(card)
        cv.setContentsMargins(8, 6, 8, 8)
        cv.setSpacing(4)

        head = QHBoxLayout()
        lbl = QLabel(f"{type_label}  ·  {len(fids)} Gerät(e)")
        lbl.setStyleSheet("font-weight: bold;")
        head.addWidget(lbl)
        head.addStretch(1)
        if tkey is not None:
            b_chan = QPushButton("➕ Kanal")
            b_chan.setFixedHeight(22)
            b_chan.setToolTip("Einen vergessenen Kanal (z. B. Shutter/Rot) bei allen "
                              "Geräten dieses Typs nachtragen.")
            b_chan.clicked.connect(weak_slot(self._add_channel, tkey, list(fids)))
            head.addWidget(b_chan)
        cv.addLayout(head)

        # Zeilen (fid, attr, val) dieses Typs einsammeln + nach Gerät/Gruppe sortieren.
        rows: list[tuple[int, str, int]] = []
        for fid in fids:
            for attr in self._snap.values.get(fid, {}):
                rows.append((fid, attr, self._snap.values[fid][attr]))
        rows.sort(key=lambda r: (r[0], _classify_attr(r[1]), _attr_label(r[1]).lower()))

        tbl = QTableWidget(len(rows), len(_COLS))
        tbl.setHorizontalHeaderLabels(_COLS)
        tbl.verticalHeader().setVisible(False)
        tbl.verticalHeader().setDefaultSectionSize(30)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        tbl.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        hh = tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        for r, (fid, attr, val) in enumerate(rows):
            label, chan_name, dmx = self._resolve(fixtures.get(fid), attr)
            tbl.setItem(r, 0, QTableWidgetItem(f"{label}  (FID {fid})"))
            tbl.setItem(r, 1, QTableWidgetItem(chan_name))
            tbl.setItem(r, 2, QTableWidgetItem(_classify_attr(attr)))
            dmx_item = QTableWidgetItem("—" if dmx is None else str(dmx))
            dmx_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            tbl.setItem(r, 3, dmx_item)
            sp = QSpinBox()
            sp.setRange(0, 255)
            sp.setValue(int(val))
            sp.valueChanged.connect(weak_slot_fwd(self._on_value, fid, attr))
            tbl.setCellWidget(r, 4, sp)
            btn = QPushButton("✕")
            btn.setFixedWidth(28)
            btn.setToolTip("Diesen Kanal aus dem Snap entfernen")
            btn.clicked.connect(weak_slot(self._remove, fid, attr))
            tbl.setCellWidget(r, 5, btn)

        # Tabelle auf Inhaltshoehe fixieren (kein verschachtelter Scroll).
        h = hh.height() + 4
        for r in range(tbl.rowCount()):
            h += tbl.rowHeight(r) or 30
        tbl.setFixedHeight(max(h, 60))
        cv.addWidget(tbl)
        self._tables.append(tbl)

        self._cards_layout.addWidget(card)
        return len(rows)

    # ── Mutationen (ueber die Library-API) ──────────────────────────────────────

    def _set_value(self, fid: int, attr: str, val: int):
        lib = self._lib()
        if lib is not None:
            lib.set_snap_value(self._snap.id, int(fid), attr, int(val))
        else:
            self._snap.values.setdefault(int(fid), {})[attr] = max(0, min(255, int(val)))

    def _on_value(self, fid: int, attr: str, val: int):
        if self._building:
            return
        self._set_value(fid, attr, val)

    def _remove(self, fid: int, attr: str):
        lib = self._lib()
        if lib is not None:
            lib.remove_snap_attr(self._snap.id, int(fid), attr)
        else:
            self._snap.values.get(int(fid), {}).pop(attr, None)
            if int(fid) in self._snap.values and not self._snap.values[int(fid)]:
                self._snap.values.pop(int(fid), None)
        self._load()

    # ── Gerät hinzufügen ────────────────────────────────────────────────────────

    def _add_device(self):
        fixtures = self._fixtures()
        if not fixtures:
            QMessageBox.information(self, "Gerät hinzufügen",
                                   "Keine gepatchten Geräte verfügbar.")
            return
        controlled_groups = snap_controlled_groups(self._snap.values)
        in_snap = {int(f) for f in self._snap.values.keys()}

        # Kompatible Kandidaten (noch nicht im Snap) nach Typ gruppieren.
        cand_by_type: dict[tuple, list[tuple]] = {}
        type_label_of: dict[tuple, str] = {}
        for fid, fx in fixtures.items():
            if int(fid) in in_snap:
                continue
            caps = self._caps(fx)
            if not is_compatible(caps, controlled_groups):
                continue
            tkey = fixture_type_key(fx)
            label = getattr(fx, "label", None) or f"FID {fid}"
            try:
                dmx_hint = f"  ·  DMX {int(fx.address)} (U{int(getattr(fx, 'universe', 1))})"
            except Exception:
                dmx_hint = ""
            cand_by_type.setdefault(tkey, []).append((int(fid), label, dmx_hint))
            type_label_of.setdefault(tkey, fixture_type_label(fx))

        ordered = [
            (type_label_of[k], sorted(cand_by_type[k], key=lambda d: d[1].lower()))
            for k in sorted(cand_by_type, key=lambda k: type_label_of[k].lower())
        ]
        if not ordered:
            QMessageBox.information(
                self, "Gerät hinzufügen",
                "Keine kompatiblen Geräte verfügbar — alle passenden Geräte sind "
                "bereits im Snap, oder kein gepatchtes Gerät kann alle gesteuerten "
                "Gruppen bedienen.")
            return

        dlg = _AddDeviceDialog(ordered, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        chosen = dlg.selected_fids()
        if not chosen:
            return

        controlled_attrs = snap_controlled_attrs(self._snap.values)
        # Vorbild je Typ (erstes Snap-Gerät desselben Typs) cachen.
        template_by_type: dict[tuple, dict] = {}
        for fid in in_snap:
            fx = fixtures.get(int(fid))
            if fx is None:
                continue
            tkey = fixture_type_key(fx)
            template_by_type.setdefault(tkey, dict(self._snap.values.get(int(fid), {})))

        added = 0
        skipped = 0
        for fid in chosen:
            fx = fixtures.get(int(fid))
            if fx is None:
                skipped += 1
                continue
            caps = self._caps(fx)
            template = template_by_type.get(fixture_type_key(fx))
            new_vals = values_for_new_device(template, caps, controlled_attrs)
            if not new_vals:
                skipped += 1   # kompatibel auf Gruppen-Ebene, aber kein exakt passender Kanal
                continue
            for attr, val in new_vals.items():
                self._set_value(int(fid), attr, val)
            added += 1

        if added == 0:
            QMessageBox.information(self, "Gerät hinzufügen",
                                   "Keine passenden Kanäle für die Auswahl gefunden.")
        elif skipped:
            QMessageBox.information(
                self, "Gerät hinzufügen",
                f"{added} Gerät(e) hinzugefügt, {skipped} übersprungen "
                f"(keine passenden Kanäle).")
        self._load()

    # ── Kanal hinzufügen (pro Typ) ───────────────────────────────────────────────

    def _add_channel(self, tkey, fids: list[int]):
        # tkey identifiziert die Karte (alle fids sind dieses Typs); die Logik
        # leitet alles aus den fids/Geraeten ab, daher hier nicht weiter genutzt.
        fixtures = self._fixtures()
        present = {f for f in fids if f in self._snap.values}
        if not present:
            self._load()
            return

        # Volle Pro-Kopf-Schluessel je Typ (inkl. attr#N) + die bei ALLEN Geraeten
        # bereits vorhandenen EXAKTEN Schluessel (NICHT basis-gestrippt) — sonst
        # liesse sich ein fehlender zweiter Kopf (z. B. color_r#1 am Spider) nie
        # nachtragen, weil der vorhandene Basis-Kopf ihn maskieren wuerde.
        type_keys: set[str] = set()
        present_sets: list[set[str]] = []
        for fid in present:
            fx = fixtures.get(int(fid))
            if fx is not None:
                type_keys |= set(fixture_channel_keys(self._channels(fx)))
            present_sets.append(set(self._snap.values.get(int(fid), {}).keys()))
        present_on_all = set.intersection(*present_sets) if present_sets else set()
        addable = addable_channels(type_keys, present_on_all)

        type_label = fixture_type_label(fixtures.get(next(iter(present)))) \
            if fixtures.get(next(iter(present))) is not None else "Typ"
        dlg = _AddChannelDialog(type_label, addable, len(present), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        attrs = dlg.selected_attrs()
        if not attrs:
            return
        value = dlg.value()

        for attr in attrs:
            for fid in present:
                # nur dort nachtragen, wo der Kanal fehlt (vorhandene Werte schonen)
                existing = self._snap.values.get(int(fid), {})
                if attr in existing:
                    continue
                self._set_value(int(fid), attr, value)
        self._load()

    # ── Vorschau ──────────────────────────────────────────────────────────────

    def _preview(self):
        try:
            st = get_state()
            for fid, attrs in self._snap.values.items():
                for attr, val in attrs.items():
                    st.set_programmer_value(int(fid), attr, int(val))
        except Exception:
            pass
