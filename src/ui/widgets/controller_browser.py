"""Controller-Browser — UI für die Controller-Bibliothek (Feature 6).

Zeigt Controller-Profile (Builtins + Nutzer-Importe), Details inkl.
MIDI-Belegung/LED-Feedback/Quelle, und bietet:

Standard ist ``midi_only=True`` (Aufruf aus der MIDI-Konsole): dann werden
nur echte MIDI-Eingabegeräte gelistet — DMX-Interfaces (Enttec), Netzwerk-
Nodes, Pulte und Makro-Tastaturen bleiben in der Bibliothek, werden hier aber
ausgeblendet. ``midi_only=False`` zeigt die komplette Bibliothek.

- „QLC+ .qxi importieren…" — konvertiert QLC+-Inputprofile in unsere
  Bibliothek (Kern: src/core/controllers/qxi_import.py, Apache-2.0-Quelle
  bleibt im Profil vermerkt)
- „MIDI-Mapping-Profil erzeugen" — legt für Profile mit Mapping-Vorlage
  (z. B. APC mini) ein fertiges Input-Profil unter
  %APPDATA%/LightOS/input_profiles/ an (MIDI-Konsole → Profile)

Aufgerufen aus der MIDI-Konsole („Controller-Profile…").
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox,
                               QPushButton, QTextBrowser, QVBoxLayout)

from src.core.controllers.controller_library import (ControllerProfile,
                                                     get_controller_library)

_TYPE_LABELS = {
    "midi_grid_controller": "MIDI-Grid-Controller",
    "midi_fader_controller": "MIDI-Fader/Encoder-Controller",
    "midi_keyboard": "MIDI-Keyboard",
    "dmx_interface": "DMX-Interface",
    "network_node": "Netzwerk-Node (Art-Net/sACN)",
    "console": "Lichtpult",
    "keyboard_macro": "Tastatur/Makro-Board",
    "other": "Sonstiges",
}

# Geräte-Typen, die echte MIDI-Eingabegeräte sind. Im MIDI-Kontext
# (Aufruf aus der MIDI-Konsole) zeigt der Browser NUR diese — DMX-Interfaces
# (Enttec), Netzwerk-Nodes, Pulte und Makro-Tastaturen gehören nicht hierher.
MIDI_DEVICE_TYPES = (
    "midi_grid_controller",
    "midi_fader_controller",
    "midi_keyboard",
)

# Gruppen-Reihenfolge für die "schön sortierte" MIDI-Liste:
# Grid-Controller → Fader/Encoder → Keyboards (innerhalb je alphabetisch).
_MIDI_TYPE_ORDER = {t: i for i, t in enumerate(MIDI_DEVICE_TYPES)}


def _sorted_midi_profiles(profiles, midi_only: bool = True):
    """Filtert (optional) auf MIDI-Controller und sortiert für die Anzeige.

    ``midi_only=True`` (Default, MIDI-Konsole): nur MIDI-Eingabegeräte,
    gruppiert nach Typ (Grid → Fader/Encoder → Keyboard), darin alphabetisch
    nach Anzeigename. ``midi_only=False``: alle Profile, wie bisher nach
    (device_type, label) sortiert.
    """
    if midi_only:
        midi = [p for p in profiles if p.device_type in MIDI_DEVICE_TYPES]
        return sorted(midi, key=lambda p: (_MIDI_TYPE_ORDER.get(p.device_type, 99),
                                           p.label.lower()))
    return sorted(profiles, key=lambda p: (p.device_type, p.label.lower()))

_BTN_STYLE = """
    QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                  border-radius:4px; font-size:11px; padding:6px 12px; }
    QPushButton:hover { background:#30363d; }
    QPushButton:disabled { color:#555d68; }
"""


class ControllerBrowserDialog(QDialog):
    def __init__(self, parent=None, midi_only: bool = True):
        super().__init__(parent)
        self._midi_only = midi_only
        self.setWindowTitle("MIDI-Controller-Profile" if midi_only
                            else "Controller-Bibliothek")
        self.setModal(True)
        self.setStyleSheet("QDialog { background:#161b22; } "
                           "QLabel { color:#8b949e; font-size:11px; }")
        self._lib = get_controller_library()

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        cols = QHBoxLayout()
        cols.setSpacing(10)

        # Links: Liste
        left = QVBoxLayout()
        left.addWidget(QLabel("MIDI-Controller (Builtins + Importe):"
                              if midi_only else "Profile (Builtins + Importe):"))
        self._list = QListWidget()
        self._list.setMinimumSize(260, 360)
        self._list.setStyleSheet(
            "QListWidget { background:#0d1117; color:#e6edf3; border:1px solid #30363d;"
            " border-radius:4px; font-size:11px; }"
            "QListWidget::item { min-height:30px; }"
            "QListWidget::item:selected { background:#1f6feb; }")
        self._list.currentItemChanged.connect(lambda *_: self._show_details())
        left.addWidget(self._list, stretch=1)
        cols.addLayout(left, stretch=1)

        # Rechts: Details
        right = QVBoxLayout()
        right.addWidget(QLabel("Details:"))
        self._details = QTextBrowser()
        self._details.setMinimumSize(380, 360)
        self._details.setStyleSheet(
            "QTextBrowser { background:#0d1117; color:#c9d1d9; border:1px solid #30363d;"
            " border-radius:4px; font-size:11px; }")
        right.addWidget(self._details, stretch=1)
        cols.addLayout(right, stretch=2)
        root.addLayout(cols, stretch=1)

        btns = QHBoxLayout()
        self._btn_import = QPushButton("QLC+ .qxi importieren…")
        self._btn_mapping = QPushButton("MIDI-Mapping-Profil erzeugen")
        btn_close = QPushButton("Schließen")
        for b in (self._btn_import, self._btn_mapping, btn_close):
            b.setMinimumHeight(36)
            b.setStyleSheet(_BTN_STYLE)
        self._btn_import.clicked.connect(self._import_qxi)
        self._btn_mapping.clicked.connect(self._create_mapping_profile)
        btn_close.clicked.connect(self.accept)
        btns.addWidget(self._btn_import)
        btns.addWidget(self._btn_mapping)
        btns.addStretch(1)
        btns.addWidget(btn_close)
        root.addLayout(btns)

        self.resize(820, 540)
        self._reload_list()

    # ── Liste & Details ───────────────────────────────────────────────────────

    def _reload_list(self, select_id: str | None = None):
        self._list.clear()
        profiles = _sorted_midi_profiles(self._lib.all(), self._midi_only)
        for p in profiles:
            it = QListWidgetItem(
                f"{p.label}\n   {_TYPE_LABELS.get(p.device_type, p.device_type)}")
            it.setData(Qt.ItemDataRole.UserRole, p.id)
            self._list.addItem(it)
            if select_id and p.id == select_id:
                self._list.setCurrentItem(it)
        if self._list.currentRow() < 0 and self._list.count():
            self._list.setCurrentRow(0)

    def _current(self) -> ControllerProfile | None:
        it = self._list.currentItem()
        if it is None:
            return None
        return self._lib.find(it.data(Qt.ItemDataRole.UserRole))

    def _show_details(self):
        p = self._current()
        if p is None:
            self._details.setHtml("")
            self._btn_mapping.setEnabled(False)
            return
        self._btn_mapping.setEnabled(bool(p.mapping_template))

        def esc(s):
            return (str(s).replace("&", "&amp;").replace("<", "&lt;")
                    .replace(">", "&gt;"))

        rows = []
        rows.append(f"<h3 style='color:#e6edf3'>{esc(p.label)}</h3>")
        rows.append(f"<b>Typ:</b> {esc(_TYPE_LABELS.get(p.device_type, p.device_type))}<br>")
        if p.connections:
            rows.append(f"<b>Anschluss:</b> {esc(', '.join(p.connections))}<br>")
        rows.append(f"<b>Tasten:</b> {p.buttons} &nbsp; <b>Fader:</b> {p.faders}"
                    f" &nbsp; <b>Encoder:</b> {p.encoders}")
        if p.pad_matrix:
            rows.append(f" &nbsp; <b>Pad-Matrix:</b> {p.pad_matrix[0]}×{p.pad_matrix[1]}")
        rows.append("<br>")
        if p.banks:
            rows.append(f"<b>Banks/Seiten:</b> {esc(p.banks)}<br>")
        if p.controls:
            rows.append("<br><b>MIDI-Belegung:</b><table border='0' cellspacing='0' "
                        "cellpadding='3' style='font-size:10px'>")
            rows.append("<tr style='color:#79c0ff'><td>Element</td><td>Typ</td>"
                        "<td>Kanal</td><td>Nummern</td><td>Layout</td></tr>")
            for c in p.controls[:40]:
                rng = (f"{c.range[0]}–{c.range[1]}" if c.range[0] != c.range[1]
                       else str(c.range[0]))
                ch = "alle" if c.channel < 0 else str(c.channel + 1)
                rows.append(f"<tr><td>{esc(c.name)}</td><td>{esc(c.type)}</td>"
                            f"<td>{ch}</td><td>{rng}</td><td>{esc(c.layout)}</td></tr>")
            if len(p.controls) > 40:
                rows.append(f"<tr><td colspan='5'>… {len(p.controls) - 40} weitere</td></tr>")
            rows.append("</table>")
        if p.led_feedback:
            rows.append(f"<br><b>LED-Feedback:</b> {esc(p.led_feedback.get('notes', p.led_feedback))}<br>")
        if p.features:
            rows.append("<br><b>Besonderheiten:</b><ul>")
            for f in p.features:
                rows.append(f"<li>{esc(f)}</li>")
            rows.append("</ul>")
        if p.vc_template:
            rows.append("<p style='color:#3fb950'>✔ VC-Vorlage verfügbar — in der "
                        "Virtual Console über „Controller-Vorlage einfügen“ nutzbar.</p>")
        rows.append("<hr>")
        rows.append(f"<p style='color:#8b949e; font-size:10px'><b>Quelle:</b> {esc(p.source)}<br>"
                    f"<b>Lizenz:</b> {esc(p.license)}<br>"
                    f"<b>Importiert:</b> {esc(p.imported_at)}</p>")
        self._details.setHtml("".join(rows))

    # ── Aktionen ──────────────────────────────────────────────────────────────

    def _import_qxi(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "QLC+-Inputprofile wählen", "",
            "QLC+ Inputprofile (*.qxi);;Alle Dateien (*)")
        if not paths:
            return
        from src.core.controllers.qxi_import import convert_qxi
        ok, errs = [], []
        last_id = None
        for path in paths:
            try:
                profile = convert_qxi(path)
                self._lib.add_user_profile(profile)
                ok.append(profile.label)
                last_id = profile.id
            except Exception as e:
                errs.append(f"{path}: {e}")
        self._reload_list(select_id=last_id)
        msg = ""
        if ok:
            msg += "Importiert:\n  " + "\n  ".join(ok)
        if errs:
            msg += "\n\nFehler:\n  " + "\n  ".join(errs)
        QMessageBox.information(self, "QXI-Import", msg or "Nichts importiert.")

    def _create_mapping_profile(self):
        p = self._current()
        if p is None or not p.mapping_template:
            return
        if p.mapping_template == "apc_mini_default":
            try:
                from src.core.input.profile import create_default_apc_mini_profile
                prof = create_default_apc_mini_profile()
                path = prof.save()
                QMessageBox.information(
                    self, "Mapping-Profil",
                    f"Profil „{prof.name}“ gespeichert:\n{path}\n\n"
                    "Laden über MIDI-Konsole → Profile.")
            except Exception as e:
                QMessageBox.warning(self, "Mapping-Profil", str(e))
        else:
            QMessageBox.information(
                self, "Mapping-Profil",
                f"Für die Vorlage „{p.mapping_template}“ ist noch kein "
                "Generator hinterlegt.")
