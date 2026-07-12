"""Fixture Generator — grafisches Anlegen von Geraete-Profilen (F-23 / X-4).

An QLC+ 5 orientiert: Kopf (Hersteller/Modell/Typ/…), mehrere Modi, ein
gefuehrter Kanal-Editor (Attribut-Combo + Freitext, Default/Highlight, Invert,
8/16-bit mit Fine-Kanal-Kopplung), ein Bereichs-Editor je Kanal (range_from/to,
Name, kind) und ein **echter Live-Test**, der Werte direkt in ein Universe des
globalen OutputManagers schreibt — so identifiziert der Nutzer am echten
Strahler, welcher Kanal was tut.

Die **Kernlogik** (Modell-Bau, Validierung, Live-Write, Markdown-Export) ist
bewusst von der reinen Anzeige getrennt und ohne sichtbares Fenster testbar:

- :func:`build_profile_payload` — Generator-Modell → serialisierbares Payload.
- :func:`save_generated_profile` — schreibt das Payload in die Fixture-DB.
- :func:`validate_model` — nicht-blockierende Plausibilitaets-Hinweise.
- :class:`LiveTester` — schreibt/restauriert Kanalwerte in einem Universe.
- :func:`model_to_markdown` — Kanal-Layout als Markdown (wie MOVING_HEADS.md).

Verhindert strukturell Fehler wie den vertauschten ZQ02001 Dimmer/Strobe-Kanal.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QSpinBox,
    QComboBox, QPushButton, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox, QInputDialog, QGroupBox,
    QDialogButtonBox, QTabWidget, QWidget, QCheckBox, QSlider,
    QSplitter, QTextEdit, QFileDialog,
)
from PySide6.QtCore import Qt, QTimer

# Wiederverwendung der bereits gepflegten Listen aus dem einfachen Editor.
from src.ui.widgets.fixture_editor import FIXTURE_TYPES, CHANNEL_ATTRS


# Attribute, die fuer eine 16-bit-Aufloesung (coarse + Fine-Kanal) sinnvoll
# sind. Nur fuer diese wird die Fine-Kanal-Kopplung im Editor angeboten.
FINE_CAPABLE_ATTRS = {
    "pan", "tilt", "intensity", "dimmer", "color_wheel", "gobo_rotation",
    "zoom", "focus", "prism_rotation",
}

# kinds eines Bereichs (ChannelRange.kind). "" = unbekannt/neutral.
RANGE_KINDS = ["", "open", "closed", "strobe", "color", "gobo", "rotate",
               "shake", "sound", "reset"]

# FM-12: waehlbare 3D-Visualizer-Modelle. Wert "" = Automatik (Kanal-Heuristik
# suggest_viz_model bzw. fixture_type); alles andere ist ein harter Override,
# der als FixtureProfile.viz_model gespeichert wird und 3D, 2D-Live-View und
# Listen-Icons gemeinsam umschaltet (viz_model_for, FM-7).
VIZ_MODEL_CHOICES = [
    ("Automatisch (Vorschlag)", ""),
    ("PAR-Dose", "par"),
    ("Moving Head", "moving_head"),
    ("Scanner (Spiegel)", "scanner"),
    ("LED-Bar (Pixel)", "led_bar"),
    ("PAR-Bar (N Köpfe)", "par_bar"),
    ("Mover-Bar (N bewegliche Köpfe)", "mover_bar"),
    ("Spider (Doppel-Bar)", "spider"),
    ("Strobe", "strobe"),
    ("Dimmer-Pack", "dimmer"),
    ("Laser", "laser"),
    ("Nebelmaschine", "smoke"),
    ("Hazer", "hazer"),
    ("Neutrales Gerät", "other"),
]
VIZ_MODEL_LABELS = {value: label for label, value in VIZ_MODEL_CHOICES if value}


# ── Datenmodell (UI-unabhaengig, serialisierbar) ─────────────────────────────

@dataclass
class GenRange:
    """Ein benannter DMX-Bereich eines Kanals."""
    range_from: int = 0
    range_to: int = 255
    name: str = ""
    kind: str = ""

    def to_dict(self) -> dict:
        return {"range_from": int(self.range_from), "range_to": int(self.range_to),
                "name": self.name, "kind": self.kind}


@dataclass
class GenChannel:
    """Ein Kanal eines Modus (Reihenfolge ergibt die Kanalnummer)."""
    name: str = "Kanal"
    attribute: str = "raw"
    default_value: int = 0
    highlight_value: int = 255
    invert: bool = False
    resolution: str = "8bit"        # "8bit" | "16bit"
    fine_channel: str = ""          # Name des gekoppelten Fine-Kanals (16bit)
    ranges: list[GenRange] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name, "attribute": self.attribute,
            "default_value": int(self.default_value),
            "highlight_value": int(self.highlight_value),
            "invert": bool(self.invert), "resolution": self.resolution,
            "fine_channel": self.fine_channel,
            "ranges": [r.to_dict() for r in self.ranges],
        }


@dataclass
class GenMode:
    """Ein Modus (z. B. "9-Kanal") mit geordneter Kanalliste."""
    name: str = "Modus"
    channels: list[GenChannel] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name,
                "channels": [c.to_dict() for c in self.channels]}


@dataclass
class GeneratorModel:
    """Vollstaendiges Generator-Modell (Kopf + Modi)."""
    manufacturer: str = "Generic"
    short_mfr: str = ""
    model: str = "Neues Fixture"
    short_name: str = ""
    fixture_type: str = "par"
    power_w: int = 0
    notes: str = ""
    # FM-12: expliziter 3D-Modell-Override ("" = Automatik/Vorschlag).
    viz_model: str = ""
    modes: list[GenMode] = field(default_factory=list)

    def to_payload(self) -> dict:
        return build_profile_payload(self)


# ── Modell-Bau (Generator-Modell → DB-Payload) ───────────────────────────────

def build_profile_payload(model: GeneratorModel) -> dict:
    """Baut aus einem :class:`GeneratorModel` ein serialisierbares Payload, das
    sich 1:1 als FixtureProfile/FixtureMode/FixtureChannel/ChannelRange
    speichern laesst. Reine Funktion (keine DB, keine UI) — Kern der Tests.

    Die Kanalnummer ergibt sich aus der Reihenfolge je Modus.
    """
    modes_out: list[dict] = []
    for mode in model.modes:
        chans_out: list[dict] = []
        for i, ch in enumerate(mode.channels, 1):
            chans_out.append({
                "channel_number": i,
                "name": (ch.name or f"Kanal {i}").strip(),
                "attribute": (ch.attribute or "raw").strip() or "raw",
                "default_value": _clamp(ch.default_value),
                "highlight_value": _clamp(ch.highlight_value),
                "invert": bool(ch.invert),
                "resolution": "16bit" if ch.resolution == "16bit" else "8bit",
                "ranges": [
                    {"range_from": _clamp(r.range_from),
                     "range_to": _clamp(r.range_to),
                     "name": (r.name or "").strip(),
                     "kind": (r.kind or "").strip()}
                    for r in ch.ranges
                ],
            })
        modes_out.append({
            "name": (mode.name or "Modus").strip(),
            "channel_count": len(mode.channels),
            "channels": chans_out,
        })
    short = (model.short_name or model.model[:8]).strip().upper()[:40]
    short_mfr = (model.short_mfr or model.manufacturer[:8]).strip().upper()[:20]
    return {
        "manufacturer": (model.manufacturer or "Generic").strip(),
        "short_mfr": short_mfr,
        "name": (model.model or "Neues Fixture").strip(),
        "short_name": short or "FIXTURE",
        "fixture_type": (model.fixture_type or "other").strip(),
        "power_w": int(model.power_w or 0),
        "notes": model.notes or "",
        "source": "user",
        "viz_model": (model.viz_model or "").strip(),
        "modes": modes_out,
    }


def _clamp(v) -> int:
    try:
        v = int(v)
    except (TypeError, ValueError):
        return 0
    return 0 if v < 0 else 255 if v > 255 else v


# ── Speichern in die Fixture-DB ──────────────────────────────────────────────

def save_generated_profile(payload: dict, *, engine=None) -> int:
    """Speichert ein von :func:`build_profile_payload` erzeugtes Payload als
    neues FixtureProfile (source="user") in der Fixture-DB. Gibt die neue
    Profil-ID zurueck. ``engine`` erlaubt eine Test-DB (Default: globale DB).
    """
    from src.core.database import fixture_db as fdb
    return fdb.create_user_profile(payload, engine=engine)


# ── Validierung (nicht-blockierende Hinweise) ────────────────────────────────

def validate_model(model: GeneratorModel) -> list[tuple[str, str]]:
    """Prueft das Generator-Modell und liefert Hinweise als (severity, text).

    severity ist "warn" oder "error" — beides ist **nicht-blockierend**; der
    Nutzer kann trotzdem speichern (die Realitaet kennt Geraete mit Luecken).

    Geprueft wird:
    - leere Modi / fehlende Kanaele,
    - Bereiche ausserhalb 0–255 und range_from > range_to,
    - ueberlappende Bereiche innerhalb eines Kanals,
    - Luecken zwischen Bereichen (nur wenn ueberhaupt Bereiche existieren),
    - doppelte (gleiche) Attribute je Modus — bewusst nur Hinweis, der Nutzer
      hat reale Geraete mit zwei Pan/zwei Tilt,
    - Dimmer↔Strobe-Plausibilitaet (Heuristik: Strobe-Kanal mit Default 255 /
      Dimmer-Kanal mit Bereichen — sieht nach Verwechslung aus),
    - fehlender open-Bereich an einem shutter/strobe-Kanal mit Bereichen,
    - 16-bit-Kanaele ohne gekoppelten Fine-Kanal,
    - Modus-Vergleich: gleiche Attribut-Mengen, aber andere Kanalnummern.
    """
    issues: list[tuple[str, str]] = []
    if not model.modes:
        issues.append(("error", "Kein Modus angelegt."))
        return issues

    for mode in model.modes:
        loc = f"Modus '{mode.name}'"
        if not mode.channels:
            issues.append(("error", f"{loc}: keine Kanäle."))
            continue

        # Doppelte (echte) Attribute — nur Hinweis (zwei Pan/Tilt erlaubt).
        seen: dict[str, int] = {}
        for ch in mode.channels:
            a = (ch.attribute or "raw")
            if a not in ("raw", ""):
                seen[a] = seen.get(a, 0) + 1
        for a, n in seen.items():
            if n > 1:
                issues.append((
                    "warn",
                    f"{loc}: Attribut '{a}' {n}× vergeben "
                    f"(ok, falls beabsichtigt — z. B. zwei Tilt)."))

        for i, ch in enumerate(mode.channels, 1):
            chloc = f"{loc}, Kanal {i} ('{ch.name}')"
            issues.extend(_validate_channel(ch, chloc))

        # Dimmer↔Strobe-Plausibilitaet (Heuristik).
        issues.extend(_check_dimmer_strobe(mode, loc))

    # Modus-Vergleich (gleiche Funktionen, andere Reihenfolge).
    issues.extend(_compare_modes(model.modes))
    return issues


def _validate_channel(ch: GenChannel, loc: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if not (0 <= int(ch.default_value) <= 255):
        out.append(("error", f"{loc}: Default {ch.default_value} außerhalb 0–255."))
    if not (0 <= int(ch.highlight_value) <= 255):
        out.append(("error", f"{loc}: Highlight {ch.highlight_value} außerhalb 0–255."))

    if ch.resolution == "16bit" and not (ch.fine_channel or "").strip():
        out.append(("warn", f"{loc}: 16-bit ohne gekoppelten Fine-Kanal."))

    ranges = sorted(ch.ranges, key=lambda r: int(r.range_from))
    for r in ranges:
        if not (0 <= int(r.range_from) <= 255) or not (0 <= int(r.range_to) <= 255):
            out.append(("error",
                        f"{loc}: Bereich '{r.name}' außerhalb 0–255 "
                        f"({r.range_from}–{r.range_to})."))
        if int(r.range_from) > int(r.range_to):
            out.append(("error",
                        f"{loc}: Bereich '{r.name}' verdreht "
                        f"(von {r.range_from} > bis {r.range_to})."))

    # Ueberlappung + Luecken (nur unter sich plausiblen Bereichen).
    valid = [r for r in ranges if int(r.range_from) <= int(r.range_to)]
    for a, b in zip(valid, valid[1:]):
        if int(a.range_to) >= int(b.range_from):
            out.append(("warn",
                        f"{loc}: Bereiche '{a.name}' und '{b.name}' überlappen "
                        f"(…{a.range_to} / {b.range_from}…)."))
        elif int(b.range_from) - int(a.range_to) > 1:
            out.append(("warn",
                        f"{loc}: Lücke zwischen '{a.name}' ({a.range_to}) und "
                        f"'{b.name}' ({b.range_from})."))

    # Fehlender open-Bereich an shutter/strobe mit Bereichen.
    if (ch.attribute in ("shutter", "strobe")) and valid:
        if not any((r.kind or "") == "open" for r in valid):
            out.append(("warn",
                        f"{loc}: Shutter/Strobe ohne 'open'-Bereich — die "
                        f"Schnellwahl kann 'Auf' nicht erkennen."))
    return out


def _check_dimmer_strobe(mode: GenMode, loc: str) -> list[tuple[str, str]]:
    """Heuristik fuer vertauschten Dimmer/Strobe (realer ZQ02001-Fehler).

    Verdacht, wenn EIN Kanal als 'intensity' deklariert ist, aber mehrere
    Bereiche mit strobe-/open-kind traegt, waehrend ein anderer als
    'shutter'/'strobe' deklarierter Kanal gar keine Bereiche und Highlight 255
    hat — das sieht nach Vertauschung der beiden aus.
    """
    inten = [c for c in mode.channels if c.attribute in ("intensity", "dimmer")]
    strobe = [c for c in mode.channels if c.attribute in ("shutter", "strobe")]
    out: list[tuple[str, str]] = []
    for c in inten:
        kinds = {(r.kind or "") for r in c.ranges}
        if {"strobe", "open"} & kinds and len(c.ranges) >= 2:
            out.append(("warn",
                        f"{loc}: Kanal '{c.name}' ist als Dimmer deklariert, hat "
                        f"aber Strobe-/Open-Bereiche — Dimmer/Strobe vertauscht?"))
    for c in strobe:
        if not c.ranges and int(c.highlight_value) >= 255:
            out.append(("warn",
                        f"{loc}: Kanal '{c.name}' ist als Strobe deklariert, "
                        f"verhält sich aber wie ein Dimmer (Highlight 255, keine "
                        f"Bereiche) — Dimmer/Strobe vertauscht?"))
    return out


def _compare_modes(modes: list[GenMode]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for i in range(len(modes)):
        for j in range(i + 1, len(modes)):
            a, b = modes[i], modes[j]
            a_attrs = {c.attribute for c in a.channels if c.attribute != "raw"}
            b_attrs = {c.attribute for c in b.channels if c.attribute != "raw"}
            common = a_attrs & b_attrs
            for attr in sorted(common):
                ai = next((k for k, c in enumerate(a.channels, 1)
                           if c.attribute == attr), None)
                bi = next((k for k, c in enumerate(b.channels, 1)
                           if c.attribute == attr), None)
                if ai is not None and bi is not None and ai != bi:
                    out.append((
                        "warn",
                        f"Attribut '{attr}' liegt in '{a.name}' auf Kanal {ai}, "
                        f"in '{b.name}' auf Kanal {bi} (unterschiedliche Position)."))
    return out


# ── Live-Test (echte DMX-Ausgabe, mit sauberem Restore) ───────────────────────

class LiveTester:
    """Schreibt Kanalwerte direkt in ein Universe des OutputManagers und stellt
    beim Stop die zuvor gemerkten Werte wieder her.

    UI-unabhaengig (kein QWidget) und damit headless testbar: ein Test kann
    einen :class:`~src.core.dmx.universe.Universe` (oder ein Fake mit
    ``get_channel``/``set_channel``) uebergeben und das Schreib-/Restore-
    Verhalten pruefen.

    Der Live-Test darf eine laufende Show NICHT dauerhaft veraendern: beim Stop
    werden alle waehrend des Tests gesetzten Kanaele auf ihren vorherigen Wert
    zurueckgeschrieben (Blackout = vorherige Werte, in der Praxis meist 0).
    """

    def __init__(self, universe, base_address: int):
        self._u = universe
        self._base = int(base_address)
        self._saved: dict[int, int] = {}   # 1-basierte Adresse → Vorwert
        self._active = True

    @property
    def base_address(self) -> int:
        return self._base

    def set_base_address(self, addr: int):
        self._base = int(addr)

    def write_channel(self, ch_offset: int, value: int):
        """Schreibt Kanal ``base + ch_offset`` (0-basierter Offset) auf ``value``.
        Merkt sich beim ersten Schreiben den Vorwert fuer das spaetere Restore.
        """
        if not self._active or self._u is None:
            return
        addr = self._base + int(ch_offset)
        if not (1 <= addr <= 512):
            return
        if addr not in self._saved:
            try:
                self._saved[addr] = int(self._u.get_channel(addr))
            except Exception:
                self._saved[addr] = 0
        self._u.set_channel(addr, _clamp(value))

    def blackout(self):
        """Setzt alle bisher angefassten Kanaele auf 0 (Test-Blackout), ohne den
        gemerkten Restore-Stand zu verwerfen."""
        if self._u is None:
            return
        for addr in list(self._saved.keys()):
            try:
                self._u.set_channel(addr, 0)
            except Exception:
                pass

    def restore(self):
        """Stellt alle waehrend des Tests gesetzten Kanaele auf ihren Vorwert
        zurueck und beendet den Test (idempotent)."""
        if self._u is not None:
            for addr, val in self._saved.items():
                try:
                    self._u.set_channel(addr, val)
                except Exception:
                    pass
        self._saved.clear()
        self._active = False


# ── Markdown-Export (optional) ───────────────────────────────────────────────

def model_to_markdown(model: GeneratorModel) -> str:
    """Kanal-Layout des Modells als Markdown (Tabellen je Modus, wie
    docs/MOVING_HEADS.md). Reine Funktion, gut testbar."""
    lines: list[str] = []
    lines.append(f"# {model.manufacturer} {model.model}")
    lines.append("")
    meta = [f"Typ: {model.fixture_type}"]
    if model.power_w:
        meta.append(f"Leistung: {model.power_w} W")
    lines.append(" · ".join(meta))
    if model.notes:
        lines.append("")
        lines.append(model.notes)
    for mode in model.modes:
        lines.append("")
        lines.append(f"## {mode.name} ({len(mode.channels)} Kanäle)")
        lines.append("")
        lines.append("| # | Name | Attribut | Default | Highlight | Auflösung | Bereiche |")
        lines.append("|---|------|----------|---------|-----------|------------|----------|")
        for i, ch in enumerate(mode.channels, 1):
            rngs = "; ".join(
                f"{r.range_from}–{r.range_to} {r.name}"
                + (f" [{r.kind}]" if r.kind else "")
                for r in ch.ranges) or "—"
            lines.append(
                f"| {i} | {ch.name} | {ch.attribute} | {ch.default_value} | "
                f"{ch.highlight_value} | {ch.resolution} | {rngs} |")
    lines.append("")
    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════════
# UI
# ═════════════════════════════════════════════════════════════════════════════

CHANNEL_COLS = ["#", "Name", "Attribut", "Default", "Highlight", "Invert", "Aufl."]
RANGE_COLS = ["Von", "Bis", "Name", "Art"]


class _RangeEditor(QWidget):
    """Bereichs-Tabelle eines Kanals + kompakte Schnellwahl-Vorschau."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ranges: list[GenRange] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._title = QLabel("Bereiche (Kanal wählen)")
        self._title.setStyleSheet("color:#9aa4af;")
        lay.addWidget(self._title)

        self._tbl = QTableWidget(0, len(RANGE_COLS))
        self._tbl.setHorizontalHeaderLabels(RANGE_COLS)
        self._tbl.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked |
                                  QAbstractItemView.EditTrigger.SelectedClicked)
        lay.addWidget(self._tbl)

        row = QHBoxLayout()
        b_add = QPushButton("+ Bereich")
        b_add.clicked.connect(self._add)
        b_del = QPushButton("- Bereich")
        b_del.clicked.connect(self._del)
        b_auto = QPushButton("Art aus Namen")
        b_auto.setToolTip("Leitet die Art (kind) aus den Bereichsnamen ab.")
        b_auto.clicked.connect(self._infer_kinds)
        for b in (b_add, b_del, b_auto):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)

        self._preview = QLabel("")
        self._preview.setWordWrap(True)
        self._preview.setStyleSheet("color:#7d8590; font-size:11px;")
        lay.addWidget(self._preview)

    def set_ranges(self, ranges: list[GenRange], title: str):
        self.sync_from_table()
        self.ranges = ranges
        self._title.setText(f"Bereiche — {title}")
        self._refresh()

    def _add(self):
        self.sync_from_table()
        self.ranges.append(GenRange(0, 255, "Bereich", ""))
        self._refresh()

    def _del(self):
        self.sync_from_table()
        rows = sorted({i.row() for i in self._tbl.selectedIndexes()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self.ranges):
                del self.ranges[r]
        self._refresh()

    def _infer_kinds(self):
        self.sync_from_table()
        from src.core.database.fixture_db import _infer_range_kind
        for r in self.ranges:
            r.kind = _infer_range_kind(r.name)
        self._refresh()

    def _refresh(self):
        self._tbl.blockSignals(True)
        self._tbl.setRowCount(len(self.ranges))
        for i, r in enumerate(self.ranges):
            self._tbl.setItem(i, 0, QTableWidgetItem(str(r.range_from)))
            self._tbl.setItem(i, 1, QTableWidgetItem(str(r.range_to)))
            self._tbl.setItem(i, 2, QTableWidgetItem(r.name))
            cb = QComboBox()
            cb.addItems(RANGE_KINDS)
            cb.setCurrentText(r.kind or "")
            cb.currentTextChanged.connect(
                lambda txt, row=i: self._set_kind(row, txt))
            self._tbl.setCellWidget(i, 3, cb)
        self._tbl.blockSignals(False)
        self._update_preview()

    def _set_kind(self, row: int, value: str):
        if 0 <= row < len(self.ranges):
            self.ranges[row].kind = value
            self._update_preview()

    def sync_from_table(self):
        for i in range(min(self._tbl.rowCount(), len(self.ranges))):
            r = self.ranges[i]
            r.range_from = _clamp(self._cell(i, 0, r.range_from))
            r.range_to = _clamp(self._cell(i, 1, r.range_to))
            name_item = self._tbl.item(i, 2)
            if name_item is not None:
                r.name = name_item.text()

    def _cell(self, row, col, fallback):
        it = self._tbl.item(row, col)
        if it is None:
            return fallback
        try:
            return int(it.text())
        except (ValueError, TypeError):
            return fallback

    def _update_preview(self):
        """Kompakte Vorschau der erzeugten Schnellwahl (robust gehalten)."""
        if not self.ranges:
            self._preview.setText("Keine Bereiche — der Kanal bleibt ein Fader.")
            return
        try:
            from src.ui.widgets.preset_tile import slot_colors_for_name
        except Exception:
            slot_colors_for_name = lambda *_: []
        parts: list[str] = []
        for r in self.ranges:
            tag = ""
            kind = (r.kind or "")
            if kind in ("color", "open"):
                cols = slot_colors_for_name(r.name)
                if cols:
                    tag = " ●" * len(cols)
            elif kind == "gobo":
                tag = " ◈"
            elif kind in ("strobe", "shake", "rotate"):
                tag = " ⚡"
            elif kind == "reset":
                tag = " ⟳"
            parts.append(f"{r.range_from}–{r.range_to} {r.name}{tag}")
        self._preview.setText("Vorschau: " + "  ·  ".join(parts))


class _ModeTab(QWidget):
    """Kanal-Editor eines Modus + rechts der Bereichs-Editor des aktiven Kanals."""

    def __init__(self, mode: GenMode, parent=None):
        super().__init__(parent)
        self.mode = mode
        lay = QVBoxLayout(self)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Modus-Name:"))
        self._edit_name = QLineEdit(mode.name)
        self._edit_name.editingFinished.connect(self._on_name_changed)
        name_row.addWidget(self._edit_name, 1)
        lay.addLayout(name_row)

        split = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self._tbl = QTableWidget(0, len(CHANNEL_COLS))
        self._tbl.setHorizontalHeaderLabels(CHANNEL_COLS)
        self._tbl.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked |
                                  QAbstractItemView.EditTrigger.SelectedClicked)
        self._tbl.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._tbl.currentCellChanged.connect(self._on_row_changed)
        ll.addWidget(self._tbl)

        row = QHBoxLayout()
        for label, slot in (("+ Kanal", self._add), ("- Kanal", self._del),
                            ("Hoch", lambda: self._move(-1)),
                            ("Runter", lambda: self._move(1))):
            b = QPushButton(label)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        ll.addLayout(row)

        # 16-bit Fine-Kanal-Kopplung des aktiven Kanals.
        fine_row = QHBoxLayout()
        fine_row.addWidget(QLabel("16-bit Fine-Kanal:"))
        self._cb_fine = QComboBox()
        self._cb_fine.setEnabled(False)
        self._cb_fine.currentTextChanged.connect(self._on_fine_changed)
        fine_row.addWidget(self._cb_fine, 1)
        ll.addLayout(fine_row)
        split.addWidget(left)

        self._range_editor = _RangeEditor()
        split.addWidget(self._range_editor)
        split.setSizes([420, 320])
        lay.addWidget(split, 1)

        self._refresh()

    # ── Daten ────────────────────────────────────────────────────────────
    def _on_name_changed(self):
        self.mode.name = self._edit_name.text().strip() or "Modus"

    def _add(self):
        self.sync_from_widgets()
        n = len(self.mode.channels) + 1
        self.mode.channels.append(GenChannel(name=f"Kanal {n}"))
        self._refresh()
        self._tbl.selectRow(n - 1)

    def _del(self):
        self.sync_from_widgets()
        rows = sorted({i.row() for i in self._tbl.selectedIndexes()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self.mode.channels):
                del self.mode.channels[r]
        self._refresh()

    def _move(self, direction: int):
        self.sync_from_widgets()
        rows = sorted({i.row() for i in self._tbl.selectedIndexes()})
        if not rows:
            return
        r = rows[0]
        nr = r + direction
        if 0 <= nr < len(self.mode.channels):
            ch = self.mode.channels
            ch[r], ch[nr] = ch[nr], ch[r]
            self._refresh()
            self._tbl.selectRow(nr)

    def _refresh(self):
        self._tbl.blockSignals(True)
        self._tbl.setRowCount(len(self.mode.channels))
        for i, ch in enumerate(self.mode.channels):
            it_num = QTableWidgetItem(str(i + 1))
            it_num.setFlags(it_num.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._tbl.setItem(i, 0, it_num)
            self._tbl.setItem(i, 1, QTableWidgetItem(ch.name))

            cb_attr = QComboBox()
            cb_attr.setEditable(True)   # Freitext fuer Sonderfaelle erlaubt
            cb_attr.addItems(CHANNEL_ATTRS)
            cb_attr.setCurrentText(ch.attribute)
            cb_attr.currentTextChanged.connect(
                lambda txt, row=i: self._set_attr(row, txt))
            self._tbl.setCellWidget(i, 2, cb_attr)

            self._tbl.setItem(i, 3, QTableWidgetItem(str(ch.default_value)))
            self._tbl.setItem(i, 4, QTableWidgetItem(str(ch.highlight_value)))

            chk = QCheckBox()
            chk.setChecked(ch.invert)
            chk.toggled.connect(lambda v, row=i: self._set_invert(row, v))
            self._tbl.setCellWidget(i, 5, _center(chk))

            cb_res = QComboBox()
            cb_res.addItems(["8bit", "16bit"])
            cb_res.setCurrentText(ch.resolution)
            cb_res.currentTextChanged.connect(
                lambda txt, row=i: self._set_res(row, txt))
            self._tbl.setCellWidget(i, 6, cb_res)
        self._tbl.blockSignals(False)
        if self.mode.channels:
            self._tbl.selectRow(min(self._active_row(), len(self.mode.channels) - 1))
        self._sync_fine_combo()

    def _active_row(self) -> int:
        r = self._tbl.currentRow()
        return r if r >= 0 else 0

    def _set_attr(self, row: int, value: str):
        if 0 <= row < len(self.mode.channels):
            self.mode.channels[row].attribute = value.strip() or "raw"
            self._sync_fine_combo()

    def _set_invert(self, row: int, value: bool):
        if 0 <= row < len(self.mode.channels):
            self.mode.channels[row].invert = bool(value)

    def _set_res(self, row: int, value: str):
        if 0 <= row < len(self.mode.channels):
            self.mode.channels[row].resolution = value
            self._sync_fine_combo()

    def _on_row_changed(self, cur_row, _c, _pr, _pc):
        self.sync_from_widgets()
        if 0 <= cur_row < len(self.mode.channels):
            ch = self.mode.channels[cur_row]
            self._range_editor.set_ranges(ch.ranges, f"Kanal {cur_row + 1}: {ch.name}")
        self._sync_fine_combo()

    def _on_fine_changed(self, value: str):
        r = self._active_row()
        if 0 <= r < len(self.mode.channels):
            self.mode.channels[r].fine_channel = value

    def _sync_fine_combo(self):
        r = self._active_row()
        if not (0 <= r < len(self.mode.channels)):
            self._cb_fine.setEnabled(False)
            return
        ch = self.mode.channels[r]
        enabled = ch.resolution == "16bit" and ch.attribute in FINE_CAPABLE_ATTRS
        self._cb_fine.blockSignals(True)
        self._cb_fine.clear()
        self._cb_fine.addItem("")
        for c in self.mode.channels:
            if c is not ch:
                self._cb_fine.addItem(c.name)
        self._cb_fine.setCurrentText(ch.fine_channel or "")
        self._cb_fine.setEnabled(enabled)
        self._cb_fine.blockSignals(False)

    def sync_from_widgets(self):
        """Liest Texteingaben (Name/Default/Highlight) aus der Tabelle zurueck."""
        self._range_editor.sync_from_table()
        for i in range(min(self._tbl.rowCount(), len(self.mode.channels))):
            ch = self.mode.channels[i]
            name_item = self._tbl.item(i, 1)
            if name_item is not None:
                ch.name = name_item.text() or ch.name
            ch.default_value = _clamp(self._num(i, 3, ch.default_value))
            ch.highlight_value = _clamp(self._num(i, 4, ch.highlight_value))

    def _num(self, row, col, fallback):
        it = self._tbl.item(row, col)
        if it is None:
            return fallback
        try:
            return int(it.text())
        except (ValueError, TypeError):
            return fallback


def _center(widget: QWidget) -> QWidget:
    w = QWidget()
    l = QHBoxLayout(w)
    l.setContentsMargins(0, 0, 0, 0)
    l.addStretch(1)
    l.addWidget(widget)
    l.addStretch(1)
    return w


class _LiveTestPanel(QGroupBox):
    """Echter Live-Test: Universe + Startadresse + ein Fader pro Kanal, der
    direkt ins Universe schreibt. 'Wackeln' rampt einen Kanal hin/her.
    Sauberes Restore beim Schliessen."""

    def __init__(self, dialog: "FixtureGeneratorDialog", parent=None):
        super().__init__("Live-Test (echte DMX-Ausgabe)", parent)
        self._dialog = dialog
        self._tester: LiveTester | None = None
        self._faders: list[QSlider] = []
        self._wiggle_timer = QTimer(self)
        self._wiggle_timer.timeout.connect(self._wiggle_tick)
        self._wiggle_offset = 0
        self._wiggle_dir = 1
        self._wiggle_val = 0

        lay = QVBoxLayout(self)
        head = QHBoxLayout()
        head.addWidget(QLabel("Universe:"))
        self._spin_univ = QSpinBox()
        self._spin_univ.setRange(1, 32)
        head.addWidget(self._spin_univ)
        head.addWidget(QLabel("Startadresse:"))
        self._spin_addr = QSpinBox()
        self._spin_addr.setRange(1, 512)
        head.addWidget(self._spin_addr)
        self._btn_start = QPushButton("Test starten")
        self._btn_start.setCheckable(True)
        self._btn_start.toggled.connect(self._on_toggle)
        head.addWidget(self._btn_start)
        self._btn_black = QPushButton("Blackout")
        self._btn_black.clicked.connect(self._on_blackout)
        head.addWidget(self._btn_black)
        head.addStretch(1)
        lay.addLayout(head)

        self._info = QLabel("Test inaktiv. Universe/Adresse wählen und starten.")
        self._info.setStyleSheet("color:#9aa4af;")
        lay.addWidget(self._info)

        self._fader_box = QWidget()
        self._fader_layout = QHBoxLayout(self._fader_box)
        self._fader_layout.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._fader_box)

        wig = QHBoxLayout()
        wig.addWidget(QLabel("Wackeln-Kanal:"))
        self._cb_wiggle = QComboBox()
        wig.addWidget(self._cb_wiggle, 1)
        self._btn_wiggle = QPushButton("Wackeln")
        self._btn_wiggle.setCheckable(True)
        self._btn_wiggle.setToolTip("Rampt den gewählten Kanal hin/her — gut "
                                    "zum Identifizieren von Pan/Tilt.")
        self._btn_wiggle.toggled.connect(self._on_wiggle_toggle)
        wig.addWidget(self._btn_wiggle)
        lay.addLayout(wig)

    def current_mode(self) -> GenMode | None:
        return self._dialog.current_mode()

    def _on_toggle(self, on: bool):
        if on:
            self._start()
        else:
            self._stop()

    def _start(self):
        mode = self.current_mode()
        if not mode or not mode.channels:
            self._info.setText("Kein Modus/Kanäle zum Testen.")
            self._btn_start.setChecked(False)
            return
        try:
            state = self._dialog.get_state()
            om = state.output_manager
            univ_num = self._spin_univ.value()
            if univ_num not in state.universes:
                state.universes[univ_num] = om.add_universe(univ_num)
            universe = state.universes[univ_num]
            # Ausgabe defensiv aktivieren (falls Output nicht laeuft).
            if not getattr(om, "_running", False):
                om.start()
        except Exception as e:
            QMessageBox.warning(self, "Live-Test",
                                f"Ausgabe konnte nicht aktiviert werden:\n{e}")
            self._btn_start.setChecked(False)
            return

        self._tester = LiveTester(universe, self._spin_addr.value())
        self._build_faders(mode)
        self._spin_univ.setEnabled(False)
        self._spin_addr.setEnabled(False)
        self._btn_start.setText("Test stoppen")
        self._info.setText(
            f"AKTIV — Universe {univ_num}, Adresse {self._spin_addr.value()}. "
            f"Fader schreiben direkt aufs Gerät.")

    def _stop(self):
        self._btn_wiggle.setChecked(False)
        self._wiggle_timer.stop()
        if self._tester is not None:
            self._tester.restore()
            self._tester = None
        self._clear_faders()
        self._spin_univ.setEnabled(True)
        self._spin_addr.setEnabled(True)
        self._btn_start.setChecked(False)
        self._btn_start.setText("Test starten")
        self._info.setText("Test gestoppt — Kanäle zurückgesetzt.")

    def _on_blackout(self):
        if self._tester is not None:
            self._tester.blackout()
            for f in self._faders:
                f.blockSignals(True)
                f.setValue(0)
                f.blockSignals(False)

    def _build_faders(self, mode: GenMode):
        self._clear_faders()
        self._cb_wiggle.clear()
        for i, ch in enumerate(mode.channels):
            col = QVBoxLayout()
            sl = QSlider(Qt.Orientation.Vertical)
            sl.setRange(0, 255)
            sl.setValue(int(ch.default_value))
            sl.valueChanged.connect(lambda v, off=i: self._on_fader(off, v))
            self._faders.append(sl)
            lbl = QLabel(f"{i + 1}\n{ch.name[:8]}")
            lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lbl.setStyleSheet("font-size:10px;")
            col.addWidget(sl, 1, Qt.AlignmentFlag.AlignHCenter)
            col.addWidget(lbl)
            w = QWidget()
            w.setLayout(col)
            self._fader_layout.addWidget(w)
            self._cb_wiggle.addItem(f"{i + 1}: {ch.name}", i)
            # Startwert direkt senden, damit das Geraet sofort reagiert.
            if self._tester is not None:
                self._tester.write_channel(i, int(ch.default_value))

    def _clear_faders(self):
        while self._fader_layout.count():
            item = self._fader_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._faders = []

    def _on_fader(self, ch_offset: int, value: int):
        if self._tester is not None:
            self._tester.write_channel(ch_offset, value)

    # ── Wackeln ──────────────────────────────────────────────────────────
    def _on_wiggle_toggle(self, on: bool):
        if on and self._tester is not None:
            self._wiggle_offset = self._cb_wiggle.currentData() or 0
            self._wiggle_val = 0
            self._wiggle_dir = 1
            self._wiggle_timer.start(40)
        else:
            self._wiggle_timer.stop()

    def _wiggle_tick(self):
        if self._tester is None:
            return
        self._wiggle_val += self._wiggle_dir * 12
        if self._wiggle_val >= 255:
            self._wiggle_val = 255
            self._wiggle_dir = -1
        elif self._wiggle_val <= 0:
            self._wiggle_val = 0
            self._wiggle_dir = 1
        off = self._wiggle_offset
        self._tester.write_channel(off, self._wiggle_val)
        if 0 <= off < len(self._faders):
            self._faders[off].blockSignals(True)
            self._faders[off].setValue(self._wiggle_val)
            self._faders[off].blockSignals(False)

    def shutdown(self):
        """Sauberes Restore/Blackout — vom Dialog bei close/reject aufgerufen."""
        self._wiggle_timer.stop()
        if self._tester is not None:
            self._tester.restore()
            self._tester = None


class FixtureGeneratorDialog(QDialog):
    """Grafischer Fixture-Generator (F-23). Erfasst Kopf, Modi, Kanaele,
    Bereiche; validiert live; testet echt am Geraet; speichert als
    source="user" in die Fixture-DB."""

    def __init__(self, parent=None, model: GeneratorModel | None = None):
        super().__init__(parent)
        self.setWindowTitle("Fixture Generator")
        self.setMinimumSize(900, 680)
        self.saved_id: int | None = None
        self._model = model or _default_model()
        self._setup_ui()
        self._reload_modes()
        self._revalidate()

    # ── Hilfen fuer das Live-Panel ───────────────────────────────────────
    def get_state(self):
        from src.core.app_state import get_state
        return get_state()

    def current_mode(self) -> GenMode | None:
        idx = self._tabs.currentIndex()
        if 0 <= idx < len(self._model.modes):
            self._sync_all()
            return self._model.modes[idx]
        return None

    # ── UI-Aufbau ────────────────────────────────────────────────────────
    def _setup_ui(self):
        root = QVBoxLayout(self)

        # Kopf
        head = QGroupBox("Gerät")
        form = QFormLayout(head)
        self._edit_mfr = QLineEdit(self._model.manufacturer)
        form.addRow("Hersteller:", self._edit_mfr)
        self._edit_model = QLineEdit(self._model.model)
        form.addRow("Modell:", self._edit_model)
        self._edit_short = QLineEdit(self._model.short_name)
        self._edit_short.setMaxLength(40)
        form.addRow("Kurzname:", self._edit_short)
        self._cb_type = QComboBox()
        self._cb_type.addItems(FIXTURE_TYPES)
        self._cb_type.setCurrentText(self._model.fixture_type)
        self._cb_type.currentTextChanged.connect(lambda *_: self._revalidate())
        form.addRow("Typ:", self._cb_type)
        # FM-12: 3D-Modell-Wahl mit Live-Vorschlag der Automatik.
        self._cb_vizmodel = QComboBox()
        for label, value in VIZ_MODEL_CHOICES:
            self._cb_vizmodel.addItem(label, value)
        self._cb_vizmodel.setToolTip(
            "Welches 3D-Modell der Visualizer (und die 2D-Symbole) fuer dieses "
            "Geraet verwenden. 'Automatisch' folgt der Kanal-Heuristik — der "
            "aktuelle Vorschlag steht in Klammern.")
        idx = self._cb_vizmodel.findData(self._model.viz_model or "")
        self._cb_vizmodel.setCurrentIndex(idx if idx >= 0 else 0)
        form.addRow("3D-Modell:", self._cb_vizmodel)
        self._spin_power = QSpinBox()
        self._spin_power.setRange(0, 5000)
        self._spin_power.setSuffix(" W")
        self._spin_power.setValue(self._model.power_w)
        form.addRow("Leistung:", self._spin_power)
        self._edit_notes = QLineEdit(self._model.notes)
        form.addRow("Notizen:", self._edit_notes)

        import_row = QHBoxLayout()
        b_import = QPushButton("QLC+ (.qxf) importieren…")
        b_import.setToolTip("Vorhandene QLC+-Definition als Startpunkt laden.")
        b_import.clicked.connect(self._import_qxf)
        import_row.addWidget(b_import)
        import_row.addStretch(1)
        form.addRow("", _wrap(import_row))
        root.addWidget(head)

        # Modi
        modes_box = QGroupBox("Modi && Kanäle")
        mbl = QVBoxLayout(modes_box)
        self._tabs = QTabWidget()
        self._tabs.currentChanged.connect(lambda *_: self._revalidate())
        mbl.addWidget(self._tabs)
        mrow = QHBoxLayout()
        for label, slot in (("+ Modus", self._add_mode),
                            ("Modus umbenennen", self._rename_mode),
                            ("- Modus", self._del_mode)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            mrow.addWidget(b)
        mrow.addStretch(1)
        b_val = QPushButton("Prüfen")
        b_val.clicked.connect(self._revalidate)
        mrow.addWidget(b_val)
        mbl.addLayout(mrow)
        root.addWidget(modes_box, 1)

        # Validierungs-Hinweise
        self._issues = QTextEdit()
        self._issues.setReadOnly(True)
        self._issues.setMaximumHeight(96)
        root.addWidget(self._issues)

        # Live-Test
        self._live = _LiveTestPanel(self)
        root.addWidget(self._live)

        # Buttons
        btns = QHBoxLayout()
        b_md = QPushButton("Markdown exportieren…")
        b_md.clicked.connect(self._export_markdown)
        btns.addWidget(b_md)
        btns.addStretch(1)
        self._btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel)
        self._btn_box.accepted.connect(self._save)
        self._btn_box.rejected.connect(self.reject)
        btns.addWidget(self._btn_box)
        root.addLayout(btns)

    def _reload_modes(self):
        while self._tabs.count():
            self._tabs.removeTab(0)
        for mode in self._model.modes:
            tab = _ModeTab(mode)
            self._tabs.addTab(tab, mode.name)
        if self._tabs.count() == 0:
            self._model.modes.append(GenMode("Default", [GenChannel("Dimmer", "intensity", 0, 255)]))
            self._tabs.addTab(_ModeTab(self._model.modes[0]), "Default")

    # ── Modus-Verwaltung ─────────────────────────────────────────────────
    def _add_mode(self):
        self._sync_all()
        existing = {m.name for m in self._model.modes}
        i = 1
        while f"Modus {i}" in existing:
            i += 1
        mode = GenMode(f"Modus {i}", [GenChannel("Kanal 1")])
        self._model.modes.append(mode)
        tab = _ModeTab(mode)
        self._tabs.addTab(tab, mode.name)
        self._tabs.setCurrentWidget(tab)
        self._revalidate()

    def _rename_mode(self):
        idx = self._tabs.currentIndex()
        if idx < 0:
            return
        mode = self._model.modes[idx]
        name, ok = QInputDialog.getText(self, "Modus umbenennen", "Neuer Name:",
                                        text=mode.name)
        if ok and name.strip():
            mode.name = name.strip()
            self._tabs.widget(idx)._edit_name.setText(mode.name)
            self._tabs.setTabText(idx, mode.name)

    def _del_mode(self):
        idx = self._tabs.currentIndex()
        if idx < 0 or self._tabs.count() <= 1:
            QMessageBox.information(self, "Modus löschen",
                                    "Mindestens ein Modus muss bleiben.")
            return
        self._tabs.removeTab(idx)
        del self._model.modes[idx]
        self._revalidate()

    # ── Sync Kopf/Modi → Modell ──────────────────────────────────────────
    def _sync_all(self):
        self._model.manufacturer = self._edit_mfr.text().strip() or "Generic"
        self._model.model = self._edit_model.text().strip() or "Neues Fixture"
        self._model.short_name = self._edit_short.text().strip()
        self._model.fixture_type = self._cb_type.currentText()
        self._model.viz_model = self._cb_vizmodel.currentData() or ""
        self._model.power_w = self._spin_power.value()
        self._model.notes = self._edit_notes.text()
        for i in range(self._tabs.count()):
            self._tabs.widget(i).sync_from_widgets()

    # ── Validierung ──────────────────────────────────────────────────────
    def _viz_suggestion(self) -> str:
        """Modell, das die Automatik fuer den aktuell bearbeiteten Modus
        waehlen wuerde (FM-12) — identische Heuristik wie der Visualizer."""
        from src.core.app_state import suggest_viz_model
        idx = self._tabs.currentIndex() if hasattr(self, "_tabs") else -1
        mode = None
        if 0 <= idx < len(self._model.modes):
            mode = self._model.modes[idx]
        elif self._model.modes:
            mode = self._model.modes[0]
        attrs = [ch.attribute for ch in mode.channels] if mode else []
        return (suggest_viz_model(self._model.fixture_type, attrs)
                or (self._model.fixture_type or "other"))

    def _update_viz_suggestion(self):
        sug = self._viz_suggestion()
        label = VIZ_MODEL_LABELS.get(sug, sug)
        self._cb_vizmodel.setItemText(0, f"Automatisch (Vorschlag: {label})")

    def _revalidate(self):
        self._sync_all()
        self._update_viz_suggestion()
        issues = validate_model(self._model)
        if not issues:
            self._issues.setHtml(
                "<span style='color:#3fb950;'>Keine Hinweise — Profil sieht "
                "konsistent aus.</span>")
            return
        rows = []
        for sev, text in issues:
            color = "#f85149" if sev == "error" else "#d29922"
            tag = "FEHLER" if sev == "error" else "Hinweis"
            rows.append(f"<span style='color:{color};'>[{tag}]</span> {text}")
        self._issues.setHtml("<br>".join(rows))

    # ── Import / Export ──────────────────────────────────────────────────
    def _import_qxf(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "QLC+ Fixture (.qxf) wählen", "", "QLC+ Fixture (*.qxf)")
        if not path:
            return
        try:
            model = model_from_qxf(path)
        except Exception as e:
            QMessageBox.warning(self, "Import", f"Import fehlgeschlagen:\n{e}")
            return
        self._model = model
        self._edit_mfr.setText(model.manufacturer)
        self._edit_model.setText(model.model)
        self._edit_short.setText(model.short_name)
        self._cb_type.setCurrentText(model.fixture_type)
        vidx = self._cb_vizmodel.findData(model.viz_model or "")
        self._cb_vizmodel.setCurrentIndex(vidx if vidx >= 0 else 0)
        self._spin_power.setValue(model.power_w)
        self._edit_notes.setText(model.notes)
        self._reload_modes()
        self._revalidate()

    def _export_markdown(self):
        self._sync_all()
        path, _ = QFileDialog.getSaveFileName(
            self, "Markdown speichern", f"{self._model.model}.md",
            "Markdown (*.md)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(model_to_markdown(self._model))
        except Exception as e:
            QMessageBox.warning(self, "Export", f"Speichern fehlgeschlagen:\n{e}")
            return
        QMessageBox.information(self, "Export", f"Markdown gespeichert:\n{path}")

    # ── Speichern ────────────────────────────────────────────────────────
    def _save(self):
        self._sync_all()
        if not self._model.modes or not any(m.channels for m in self._model.modes):
            QMessageBox.warning(self, "Speichern",
                                "Mindestens ein Modus mit Kanälen nötig.")
            return
        # Live-Test sauber beenden, bevor wir speichern.
        self._live.shutdown()

        errors = [t for s, t in validate_model(self._model) if s == "error"]
        if errors:
            ans = QMessageBox.question(
                self, "Fehler im Profil",
                "Es gibt Fehler:\n\n- " + "\n- ".join(errors[:8]) +
                "\n\nTrotzdem speichern?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if ans != QMessageBox.StandardButton.Yes:
                return
        try:
            self.saved_id = save_generated_profile(self._model.to_payload())
        except Exception as e:
            QMessageBox.warning(self, "Speichern", f"Fehlgeschlagen:\n{e}")
            return
        try:
            # FM-12: gecachte viz_model-Overrides/Channels des Profils verwerfen.
            from src.core.app_state import clear_channel_cache
            clear_channel_cache()
        except Exception:
            pass
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.REFRESH_ALL, None)
        except Exception:
            pass
        QMessageBox.information(
            self, "Gespeichert",
            f"Fixture-Profil '{self._model.manufacturer} {self._model.model}' "
            f"gespeichert.")
        self.accept()

    # ── Aufraeumen ───────────────────────────────────────────────────────
    def reject(self):
        self._live.shutdown()
        super().reject()

    def closeEvent(self, e):
        self._live.shutdown()
        super().closeEvent(e)


# ── Hilfsfunktionen / Konvertierung ──────────────────────────────────────────

def _wrap(layout) -> QWidget:
    w = QWidget()
    w.setLayout(layout)
    return w


def _default_model() -> GeneratorModel:
    return GeneratorModel(
        modes=[GenMode("Default", [
            GenChannel("Dimmer", "intensity", 0, 255),
            GenChannel("Rot", "color_r", 0, 255),
            GenChannel("Grün", "color_g", 0, 255),
            GenChannel("Blau", "color_b", 0, 255),
        ])])


def model_from_qxf(path: str) -> GeneratorModel:
    """Liest eine QLC+ .qxf-Datei in ein :class:`GeneratorModel` (Startpunkt zum
    Weiterbearbeiten — KEIN direkter DB-Schreibvorgang). Nutzt dieselbe
    Attribut-/Typ-Aufloesung wie der vorhandene qxf_import."""
    import xml.etree.ElementTree as ET
    from src.core.database.qxf_import import (
        QXF_NS, TYPE_MAP, _resolve_attribute, _tag)

    tree = ET.parse(path)
    root = tree.getroot()

    def _txt(tag, default=""):
        el = root.find(_tag(tag))
        return el.text.strip() if el is not None and el.text else default

    mfr = _txt("Manufacturer", "Unknown")
    model_name = _txt("Model", "Unknown")
    type_str = _txt("Type", "Other")

    channel_defs: dict[str, ET.Element] = {}
    for ch_el in root.findall(_tag("Channel")):
        nm = ch_el.get("Name", "")
        if nm:
            channel_defs[nm] = ch_el

    def _build_channel(ch_el, name) -> GenChannel:
        attr = _resolve_attribute(ch_el)
        ranges: list[GenRange] = []
        for cap in ch_el.findall(_tag("Capability")):
            try:
                rf = int(cap.get("Min", "0"))
                rt = int(cap.get("Max", "255"))
            except ValueError:
                continue
            rname = cap.text.strip() if cap.text else ""
            if rname:
                from src.core.database.fixture_db import _infer_range_kind
                ranges.append(GenRange(rf, rt, rname[:80], _infer_range_kind(rname)))
        highlight = 255 if attr in ("intensity", "dimmer") else 0
        # 16-bit, wenn das QLC+-Preset einen Fine-Kanal andeutet.
        res = "16bit" if "fine" in (ch_el.get("Name", "").lower()) else "8bit"
        return GenChannel(name=name, attribute=attr, default_value=0,
                          highlight_value=highlight, resolution=res, ranges=ranges)

    modes_out: list[GenMode] = []
    mode_els = root.findall(_tag("Mode"))
    if not mode_els:
        chans = [_build_channel(el, nm) for nm, el in channel_defs.items()]
        if chans:
            modes_out.append(GenMode("Standard", chans))
    else:
        for mode_el in mode_els:
            mname = mode_el.get("Name", "Standard")
            chans: list[GenChannel] = []
            for ref in mode_el.findall(_tag("Channel")):
                nm = ref.text.strip() if ref.text else ""
                el = channel_defs.get(nm)
                if el is None:
                    chans.append(GenChannel(name=nm or "Kanal", attribute="raw"))
                else:
                    chans.append(_build_channel(el, nm))
            modes_out.append(GenMode(mname, chans))

    return GeneratorModel(
        manufacturer=mfr, model=model_name,
        short_name=model_name[:40], fixture_type=TYPE_MAP.get(type_str, "other"),
        notes=f"Importiert aus QLC+ ({type_str}).", modes=modes_out)
