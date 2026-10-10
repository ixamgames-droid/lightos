"""UI-85: Hilfe in der App — Doku-Ziele, Ordner oeffnen, Tastenkuerzel-Liste.

Drei Dinge, die das Hilfe-Menue des Hauptfensters braucht und die bewusst NICHT
in ``main_window.py`` stehen (dort waechst sonst alles zusammen):

* **Doku-Ziel** (``doku_ziel``): im Quellbetrieb die lokale Datei unter
  ``docs/``; im Setup-Build liegt ``docs/`` NICHT im Bundle
  (``packaging/windows/bundle_inhalt.py``) — dann der oeffentliche GitHub-Link.
  Entschieden wird am Dateisystem, nicht an ``sys.frozen``: kommt die Doku eines
  Tages ins Bundle, greift der lokale Zweig von selbst.
* **Ordner** (``datenordner`` / ``show_ordner``): legen den Ordner an, falls er
  noch fehlt — ein Dateimanager kann nur oeffnen, was existiert.
* **Tastenkuerzel** (``sammle_tastenkuerzel``): gesammelt aus den vorhandenen
  ``QAction``- und ``QShortcut``-Objekten. Keine handgepflegte Liste — ein neues
  Kuerzel steht ohne weiteres Zutun im Dialog.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QLabel, QLineEdit,
    QMenu, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from src.core.paths import app_data_dir, ist_gefroren, programm_dir

#: Oeffentliche Projektseite — Rueckfall, wenn die Doku nicht mitgeliefert ist.
GITHUB_DOCS = "https://github.com/ixamgames-droid/lightos/blob/main/docs/"
ANLEITUNGEN = "ANLEITUNGEN.md"
ERSTE_SCHRITTE = "anleitung_erste_schritte/ANLEITUNG.md"
DOKU_URL = GITHUB_DOCS + ANLEITUNGEN


# ── Doku ─────────────────────────────────────────────────────────────────────

def doku_ziel(rel: str) -> QUrl:
    """Ziel fuer eine Doku-Datei (``rel`` relativ zu ``docs/``, mit ``/``)."""
    lokal = os.path.join(programm_dir(), "docs", *rel.split("/"))
    if os.path.isfile(lokal):
        return QUrl.fromLocalFile(lokal)
    return QUrl(GITHUB_DOCS + rel)


def oeffne(url: QUrl) -> bool:
    """Reicht ``url`` an das Betriebssystem (Browser, Dateimanager, Editor)."""
    try:
        return bool(QDesktopServices.openUrl(url))
    except Exception as e:
        print(f"[hilfe] openUrl fehlgeschlagen ({url.toString()}): {e}")
        return False


def oeffne_doku(rel: str) -> bool:
    return oeffne(doku_ziel(rel))


# ── Ordner ───────────────────────────────────────────────────────────────────

def datenordner() -> str:
    return app_data_dir()


def show_ordner() -> str:
    """Standard-Show-Ordner — derselbe, in dem die Show-Dialoge starten."""
    return os.path.join(app_data_dir(), "shows")


def oeffne_ordner(pfad: str) -> bool:
    try:
        os.makedirs(pfad, exist_ok=True)
    except OSError as e:
        print(f"[hilfe] Ordner nicht anlegbar ({e})")
        return False
    return oeffne(QUrl.fromLocalFile(pfad))


# ── Ueber LightOS ────────────────────────────────────────────────────────────

def app_version() -> str:
    """Die echte Version (``APP_VERSION`` aus ``main.py``)."""
    try:
        from PySide6.QtWidgets import QApplication
        v = QApplication.applicationVersion()
        if v:
            return v
    except Exception:
        pass
    try:
        # liest main.py bzw. im Build das laufende ``__main__`` (XPLAT-47)
        from src.core.audio.audio_recorder import _lightos_version
        return _lightos_version() or "?"
    except Exception:
        return "?"


def build_art() -> str:
    return "Setup-Build" if ist_gefroren() else "Quellbetrieb (kein Setup-Build)"


def ueber_text() -> str:
    """HTML fuer „Über LightOS“."""
    from html import escape
    daten = datenordner()
    return (
        f"<b>LightOS {escape(app_version())}</b><br>"
        "Professionelle DMX-Lichtsteuerung<br><br>"
        "<table cellspacing='4'>"
        f"<tr><td>Version:</td><td>{escape(app_version())}</td></tr>"
        f"<tr><td>Build:</td><td>{escape(build_art())}</td></tr>"
        f"<tr><td>Datenordner:</td><td>{escape(daten)}</td></tr>"
        f"<tr><td>Anleitungen:</td><td><a href='{DOKU_URL}'>{DOKU_URL}</a></td></tr>"
        "</table><br>"
        "Enttec Pro USB &middot; Art-Net 4 &middot; sACN &middot; MIDI"
    )


# ── Tastenkuerzel ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Kuerzel:
    tasten: str     # „Strg+S“
    aktion: str     # „Show speichern“
    bereich: str    # Menue bzw. Fenster/Ansicht


#: Bereich der fensterweiten Kuerzel (steht in der Liste oben).
ALLGEMEIN = "Allgemein"

#: Portable Qt-Namen -> deutsche Tastenbeschriftung.
_TASTEN_DE = {
    "Ctrl": "Strg", "Shift": "Umschalt", "Space": "Leertaste",
    "Escape": "Esc", "Del": "Entf", "Ins": "Einfg", "Return": "Eingabe",
    "Enter": "Eingabe (Ziffernblock)", "PgUp": "Bild auf", "PgDown": "Bild ab",
    "Home": "Pos1", "End": "Ende", "Backspace": "Rücktaste",
    "Left": "Links", "Right": "Rechts", "Up": "Hoch", "Down": "Runter",
}

#: Beschriftung fuer QShortcuts ohne eigenen Text (``setWhatsThis``/Objektname).
_STANDARD_AKTION = {
    "Ctrl+Z": "Rückgängig", "Ctrl+Y": "Wiederholen",
    "Ctrl+Shift+Z": "Wiederholen", "Del": "Löschen",
}

#: Aktionstexte, die fuer sich allein zu knapp sind.
_AKTION_KLARTEXT = {
    ("Datei", "Speichern"): "Show speichern",
    ("Datei", "Öffnen"): "Show öffnen",
}


def tasten_text(seq: QKeySequence) -> str:
    """``Ctrl+Shift+S`` -> ``Strg+Umschalt+S`` (auch mehrteilige Folgen)."""
    roh = seq.toString(QKeySequence.SequenceFormat.PortableText)
    if not roh:
        return ""
    teile_aus = []
    for akkord in roh.split(", "):
        if akkord.endswith("++"):               # „Ctrl++“ = Strg und Plus
            tasten = akkord[:-2].split("+") + ["+"]
        elif akkord == "+":
            tasten = ["+"]
        else:
            tasten = akkord.split("+")
        teile_aus.append("+".join(_TASTEN_DE.get(t, t) for t in tasten))
    return ", ".join(teile_aus)


def _sauber(text: str) -> str:
    """Menuetext ohne Mnemonic-``&`` und ohne Auslassungspunkte."""
    t = (text or "").replace("&&", "\0").replace("&", "").replace("\0", "&")
    return t.rstrip(".… ").strip()


def _fenster_bereich(obj, bereiche=None) -> str:
    """Bereich eines Kuerzels ohne Menue: der naechste Vorfahr mit einem Namen
    in ``bereiche`` (Widget -> Name), sonst der Titel seines Fensters."""
    erster = None
    w = obj
    while w is not None:
        if isinstance(w, QWidget):
            erster = erster or w
            if bereiche and w in bereiche:
                return bereiche[w]
            if w.isWindow():
                return _sauber(w.windowTitle()) or type(w).__name__
        w = w.parent()
    return type(erster).__name__ if erster is not None else ALLGEMEIN


def _aktion_bereich(act: QAction, bereiche=None) -> str:
    for o in act.associatedObjects():
        if isinstance(o, QMenu) and o.title():
            return _sauber(o.title())
    return _fenster_bereich(act.parent(), bereiche)


def sammle_tastenkuerzel(wurzeln, bereiche=None) -> list[Kuerzel]:
    """Alle Kuerzel unter ``wurzeln`` (Widgets), sortiert nach Bereich/Aktion.

    ``bereiche`` (optional) ordnet Widgets einen Bereichsnamen zu — das
    Hauptfenster reicht sich selbst („Allgemein“) und seine Sektionsseiten
    herein; ohne Eintrag gilt der Fenstertitel.

    Quelle sind die lebenden ``QAction``- und ``QShortcut``-Objekte; Aktionen
    ohne Kuerzel und unsichtbare Aktionen bleiben draussen.
    """
    gesehen: set[tuple[str, str, str]] = set()
    aus: list[Kuerzel] = []

    def _dazu(tasten: str, aktion: str, bereich: str):
        if not tasten:
            return
        k = (tasten, aktion, bereich)
        if k not in gesehen:
            gesehen.add(k)
            aus.append(Kuerzel(tasten, aktion, bereich))

    for wurzel in wurzeln:
        if wurzel is None:
            continue
        aktionen = list(wurzel.findChildren(QAction))
        aktionen += [a for a in wurzel.actions() if a not in aktionen]
        for act in aktionen:
            if not act.isVisible():
                continue
            bereich = _aktion_bereich(act, bereiche)
            aktion = _sauber(act.text())
            aktion = _AKTION_KLARTEXT.get((bereich, aktion), aktion)
            for seq in act.shortcuts():
                _dazu(tasten_text(seq), aktion, bereich)
        for sc in wurzel.findChildren(QShortcut):
            portabel = sc.key().toString(QKeySequence.SequenceFormat.PortableText)
            aktion = (sc.whatsThis() or sc.objectName()
                      or _STANDARD_AKTION.get(portabel, "(ohne Beschreibung)"))
            _dazu(tasten_text(sc.key()), _sauber(aktion),
                  _fenster_bereich(sc.parent(), bereiche))

    aus.sort(key=lambda e: (e.bereich != ALLGEMEIN, e.bereich.lower(),
                            e.aktion.lower(), e.tasten))
    return aus


class TastenkuerzelDialog(QDialog):
    """Tabelle Taste · Aktion · Bereich mit Filterzeile."""

    def __init__(self, eintraege: list[Kuerzel], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tastenkürzel")
        self.resize(620, 560)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "Alle Tastenkürzel, die LightOS gerade kennt. Kürzel aus einem "
            "Bereich wirken, wenn dieser Bereich bzw. dieses Fenster aktiv ist."))
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filtern … (Taste, Aktion oder Bereich)")
        self.filter.setClearButtonEnabled(True)
        lay.addWidget(self.filter)

        self.tabelle = QTableWidget(len(eintraege), 3)
        self.tabelle.setHorizontalHeaderLabels(["Taste", "Aktion", "Bereich"])
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabelle.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        for r, e in enumerate(eintraege):
            for c, text in enumerate((e.tasten, e.aktion, e.bereich)):
                it = QTableWidgetItem(text)
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tabelle.setItem(r, c, it)
        kopf = self.tabelle.horizontalHeader()
        kopf.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        kopf.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        kopf.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.tabelle, 1)

        knoepfe = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        knoepfe.rejected.connect(self.reject)
        knoepfe.accepted.connect(self.accept)
        lay.addWidget(knoepfe)
        self.filter.textChanged.connect(self._filtern)

    def _filtern(self, text: str):
        nadel = text.strip().lower()
        for r in range(self.tabelle.rowCount()):
            zeile = " ".join(self.tabelle.item(r, c).text().lower()
                             for c in range(self.tabelle.columnCount()))
            self.tabelle.setRowHidden(r, bool(nadel) and nadel not in zeile)
