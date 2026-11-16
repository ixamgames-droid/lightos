"""VIZ-56: Dialog „MVR-Datei importieren“ — Vorschau, Zuordnung, Konflikte.

Der Dialog rechnet nichts selbst: Lesen macht ``src.core.mvr.lesen``,
Zuordnen/Pruefen/Anlegen ``src.core.mvr.importieren``. Hier steht nur, was man
sieht — je Geraet eine Zeile (Name, Ebene, Typ aus der Datei, Profil,
Adresse, Position, Konflikt, Status), eine Zusammenfassung und
„Importieren“/„Abbrechen“. UI-142: Status steht neben „Konflikt“ in der
letzten, mitwachsenden Spalte und bricht um; ueber der Tabelle fuehren
„Alle Konflikte: überspringen / auf freie Adresse“ und ein Hinweis aus einem
Adresskonflikt. Vorhandene Geraete werden nie veraendert (kein Ersetzen).

Qt-Fallen wie beim Tabellen-Import (``patch_import_dialog``): Auswahlfelder
werden EINMAL beim Aufbau erzeugt und nie ersetzt (STAB-38), eine Wahl
schreibt nur Texte in vorhandene Zellen, und das Mausrad verstellt kein
Auswahlfeld. Die Profilliste ist EIN Modell fuer alle Auswahlfelder — eine
grosse Bibliothek wird nicht je Zeile kopiert.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QCompleter, QDialog,
    QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from src.core import patch_tabelle as T
from src.core.mvr import importieren as I
from src.core.mvr.lesen import MvrDatei, lies_mvr
from src.core.mvr.sicher import MvrFehler

TITEL = "MVR-Datei importieren"
DATEI_FILTER = "MVR-Dateien (*.mvr);;Alle Dateien (*)"

SPALTEN = ["Name", "Ebene", "Typ (Datei)", "Profil", "Adresse", "Position (m)",
           "Konflikt", "Status"]
SPALTEN_TIPP = {
    0: "Name, unter dem das Gerät im Patch angelegt wird.",
    1: "Ebene (Layer) und Gruppe, in der das Gerät in der Datei steht.",
    2: "Gerätetyp (GDTF) und Modus, wie sie in der Datei stehen.",
    3: "Profil aus der Geräte-Bibliothek. „neu aus GDTF“: der Typ ist unbekannt "
       "und wird mit den Kanälen aus der Datei als eigenes Profil angelegt. "
       "Bei „nicht zugeordnet“ hier ein Profil wählen.",
    4: "Universum.Adresse, auf die das Gerät gepatcht wird.",
    5: "Position im 3D in Metern (x, Höhe, z), aus der Datei umgerechnet.",
    6: "Belegt die Adresse schon ein Gerät, oder fehlt sie, steht hier, was "
       "passieren soll: überspringen oder auf die nächste freie Adresse legen. "
       "Vorhandene Geräte werden nie verändert.",
    7: "Was mit dem Gerät passiert und warum.",
}
S_NAME, S_EBENE, S_TYP, S_PROFIL, S_ADRESSE, S_POS, S_KONFLIKT, S_STATUS = range(8)
#: Bis zu so vielen Zeilen passt die Tabelle die Zeilenhoehe an den
#: umgebrochenen Status an (sonst bleibt der volle Text im Tooltip).
ZEILEN_ANPASSEN_MAX = 400

NICHT_ANLEGEN = "— nicht zugeordnet —"
KEIN_KONFLIKT = "—"

_FARBE = {I.ANLEGBAR: "#3fb950", I.OFFEN: "#d29922", I.UEBERSPRUNGEN: "#f85149"}

TIPP_IMPORTIEREN = ("Legt alle Geräte an, bei denen „wird angelegt“ steht, und "
                    "setzt ihre Position und Drehung im 3D. Unbekannte Typen "
                    "werden als neue Profile in der Bibliothek angelegt. "
                    "Vorhandene Geräte bleiben unverändert; Rückgängig (Strg+Z) "
                    "nimmt den Import in einem Schritt zurück.")
TIPP_IMPORTIEREN_AUS = ("Noch kein Gerät lässt sich anlegen — bei „nicht "
                        "zugeordnet“ ein Profil wählen oder bei Konflikten "
                        "„auf freie Adresse“.")
HINWEIS_KONFLIKT = ("Kein Gerät wird angelegt: die Adressen aus der Datei sind im "
                    "Patch schon belegt. „Alle auf freie Adresse“ legt die Geräte "
                    "auf die nächsten freien Adressen, oder je Zeile unter "
                    "„Konflikt“ wählen. Vorhandene Geräte bleiben unverändert.")
TIPP_ALLE_UEBERSPRINGEN = ("Alle Geräte mit Adresskonflikt oder fehlender Adresse "
                           "werden nicht angelegt.")
TIPP_ALLE_FREI = ("Alle Geräte mit Adresskonflikt oder fehlender Adresse kommen "
                  "auf die nächste freie Adresse. Vorhandene Geräte werden nie "
                  "verändert oder überschrieben.")


class _AuswahlOhneRad(QComboBox):
    def wheelEvent(self, event):
        event.ignore()


def _profil_modell(bibliothek: T.Bibliothek) -> QStandardItemModel:
    modell = QStandardItemModel()
    leer = QStandardItem(NICHT_ANLEGEN)
    leer.setData(None, Qt.ItemDataRole.UserRole)
    modell.appendRow(leer)
    for p in sorted(bibliothek.profile, key=lambda p: p.anzeige.casefold()):
        for m in p.modi:
            if m.kanaele <= 0:
                continue
            it = QStandardItem(f"{p.anzeige} · {m.name} ({m.kanaele} Kanäle)")
            it.setData((p.id, m.name, m.kanaele), Qt.ItemDataRole.UserRole)
            modell.appendRow(it)
    return modell


def _html(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class MvrImportDialog(QDialog):
    """Vorschau einer gelesenen MVR-Datei. Nach ``exec()`` steht in
    ``ergebnis``, was angelegt wurde (``None`` = abgebrochen)."""

    def __init__(self, state, datei: MvrDatei, bibliothek: T.Bibliothek,
                 dateiname: str = "", parent=None):
        super().__init__(parent)
        self._state = state
        self._datei = datei
        self._bibliothek = bibliothek
        self.wahl: dict[int, tuple] = {}
        self.konflikt_wahl: dict[int, str] = {}
        self.plan: I.Plan = self._rechne()
        self.ergebnis: I.Ergebnis | None = None
        self._profil_auswahl: dict[int, QComboBox] = {}
        self._konflikt_auswahl: dict[int, QComboBox] = {}
        self._modell = None
        self.setWindowTitle(TITEL)
        self._aufbauen(dateiname)
        self._zeigen()
        self.resize(1200, 620)

    def _rechne(self) -> I.Plan:
        return I.baue_plan(self._datei, self._bibliothek,
                           T.belegung_aus_state(self._state),
                           self.wahl, self.konflikt_wahl)

    # ── Aufbau (einmal) ──────────────────────────────────────────────────────

    def _aufbauen(self, dateiname: str):
        layout = QVBoxLayout(self)
        d = self._datei
        teile = [f"{len(d.geraete)} Gerät{'e' if len(d.geraete) != 1 else ''}",
                 f"{len(d.typen)} Gerätetyp{'en' if len(d.typen) != 1 else ''} (GDTF)"]
        if d.traversen:
            teile.append(f"{d.traversen} Traverse{'n' if d.traversen > 1 else ''} "
                         "(werden noch nicht übernommen)")
        if d.fokuspunkte:
            teile.append(f"{d.fokuspunkte} Fokuspunkt{'e' if d.fokuspunkte > 1 else ''} "
                         "(werden noch nicht übernommen)")
        kopf = QLabel(f"<b>{_html(dateiname) or 'MVR-Datei'}</b> — " + ", ".join(teile))
        kopf.setWordWrap(True)
        layout.addWidget(kopf)
        if d.hinweise:
            h = QLabel(_html(" ".join(d.hinweise)))
            h.setWordWrap(True)
            layout.addWidget(h)

        # UI-142: Sammelwahl fuer alle Konflikte + Hinweis, wenn nichts angelegt wird
        self.hinweis_konflikt = QLabel(HINWEIS_KONFLIKT)
        self.hinweis_konflikt.setWordWrap(True)
        self.hinweis_konflikt.setStyleSheet("color:#d29922;")
        layout.addWidget(self.hinweis_konflikt)
        sammel = QHBoxLayout()
        sammel.addWidget(QLabel("Alle Konflikte:"))
        self.knopf_alle_ueberspringen = QPushButton("Alle überspringen")
        self.knopf_alle_ueberspringen.setToolTip(TIPP_ALLE_UEBERSPRINGEN)
        self.knopf_alle_ueberspringen.clicked.connect(
            lambda: self._alle_konflikte(I.UEBERSPRINGEN))
        self.knopf_alle_frei = QPushButton("Alle auf freie Adresse")
        self.knopf_alle_frei.setToolTip(TIPP_ALLE_FREI)
        self.knopf_alle_frei.clicked.connect(lambda: self._alle_konflikte(I.FREIE_ADRESSE))
        sammel.addWidget(self.knopf_alle_ueberspringen)
        sammel.addWidget(self.knopf_alle_frei)
        sammel.addStretch(1)
        layout.addLayout(sammel)

        self.tabelle = QTableWidget(len(self.plan.eintraege), len(SPALTEN))
        self.tabelle.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabelle.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tabelle.verticalHeader().setVisible(False)
        for s, text in enumerate(SPALTEN):
            item = QTableWidgetItem(text)
            item.setToolTip(SPALTEN_TIPP[s])
            self.tabelle.setHorizontalHeaderItem(s, item)
        kopfzeile = self.tabelle.horizontalHeader()
        for s in range(len(SPALTEN)):
            kopfzeile.setSectionResizeMode(s, QHeaderView.ResizeMode.Interactive)
        kopfzeile.setStretchLastSection(True)      # Status waechst mit
        self.tabelle.setWordWrap(True)
        # Zeilenhoehe folgt der Spaltenbreite (Fenster groesser/kleiner,
        # Spalte gezogen) — sonst stuende der Status in zu hohen oder zu
        # niedrigen Zeilen.
        kopfzeile.sectionResized.connect(lambda *_: self._zeilen_anpassen())
        for e in self.plan.eintraege:
            r = e.index
            if e.art in (I.NICHT_ZUGEORDNET, I.GEWAEHLT):
                self._profil_auswahl[r] = self._baue_profil_auswahl(r)
                self.tabelle.setCellWidget(r, S_PROFIL, self._profil_auswahl[r])
            # Fuer JEDE Zeile: ein Konflikt kann auch spaeter entstehen (eine
            # Profilwahl weiter oben belegt dieselbe Adresse). Ohne Konflikt
            # zeigt das Feld „—“ und ist gesperrt.
            self._konflikt_auswahl[r] = self._baue_konflikt_auswahl(r)
            self.tabelle.setCellWidget(r, S_KONFLIKT, self._konflikt_auswahl[r])
        for s, breite in ((S_NAME, 120), (S_EBENE, 90), (S_TYP, 160),
                          (S_PROFIL, 220), (S_ADRESSE, 64), (S_POS, 116),
                          (S_KONFLIKT, 150)):
            self.tabelle.setColumnWidth(s, breite)
        layout.addWidget(self.tabelle, 1)

        self.zusammenfassung = QLabel()
        self.zusammenfassung.setWordWrap(True)
        layout.addWidget(self.zusammenfassung)

        knoepfe = QHBoxLayout()
        knoepfe.addStretch(1)
        self.knopf_importieren = QPushButton("Importieren")
        self.knopf_importieren.setDefault(True)
        self.knopf_importieren.clicked.connect(self._importieren)
        self.knopf_abbrechen = QPushButton("Abbrechen")
        self.knopf_abbrechen.setToolTip("Dialog schließen, ohne etwas anzulegen.")
        self.knopf_abbrechen.clicked.connect(self.reject)
        knoepfe.addWidget(self.knopf_importieren)
        knoepfe.addWidget(self.knopf_abbrechen)
        layout.addLayout(knoepfe)

    def _baue_profil_auswahl(self, zeile: int) -> QComboBox:
        if self._modell is None:
            self._modell = _profil_modell(self._bibliothek)
        cb = _AuswahlOhneRad()
        cb.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        cb.setModel(self._modell)
        cb.setEditable(True)
        cb.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        completer = QCompleter(self._modell, cb)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        cb.setCompleter(completer)
        cb.setCurrentIndex(0)
        cb.setToolTip("Profil für dieses Gerät wählen — tippen sucht in der "
                      "Geräte-Bibliothek. „nicht zugeordnet“: das Gerät wird "
                      "nicht angelegt.")
        cb.currentIndexChanged.connect(lambda i, z=zeile, c=cb: self._profil_gewaehlt(z, c))
        return cb

    def _baue_konflikt_auswahl(self, zeile: int) -> QComboBox:
        cb = _AuswahlOhneRad()
        cb.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        cb.addItem(KEIN_KONFLIKT, None)
        for wert in (I.UEBERSPRINGEN, I.FREIE_ADRESSE):
            cb.addItem(I.AKTION_TEXT[wert], wert)
        cb.setToolTip(SPALTEN_TIPP[S_KONFLIKT])
        cb.currentIndexChanged.connect(lambda i, z=zeile, c=cb: self._konflikt_gewaehlt(z, c))
        return cb

    # ── Wahl ─────────────────────────────────────────────────────────────────

    def _profil_gewaehlt(self, zeile: int, cb: QComboBox):
        daten = cb.currentData(Qt.ItemDataRole.UserRole)
        if daten:
            self.wahl[zeile] = tuple(daten)
        else:
            self.wahl.pop(zeile, None)
        self.plan = self._rechne()
        self._zeigen()

    def _alle_konflikte(self, wert: str):
        """Sammelwahl: fuer JEDE Zeile — auch eine, deren Konflikt erst durch
        die Wahl weiter oben entsteht. Ohne Konflikt wird die Wahl nicht
        gelesen (``importieren._adressieren``)."""
        self.konflikt_wahl = {e.index: wert for e in self.plan.eintraege}
        self.plan = self._rechne()
        self._zeigen()

    def _konflikt_gewaehlt(self, zeile: int, cb: QComboBox):
        wert = cb.currentData()
        if wert:
            self.konflikt_wahl[zeile] = wert
        else:
            self.konflikt_wahl.pop(zeile, None)
        self.plan = self._rechne()
        self._zeigen()

    # ── Anzeige (nur Texte) ──────────────────────────────────────────────────

    def _setze(self, r: int, s: int, text: str, tipp: str = "", farbe: str = ""):
        item = self.tabelle.item(r, s)
        if item is None:
            item = QTableWidgetItem()
            self.tabelle.setItem(r, s, item)
        item.setText(text)
        item.setToolTip(tipp or text)
        if farbe:
            item.setForeground(QColor(farbe))

    def _zeigen(self):
        for e in self.plan.eintraege:
            r = e.index
            self._setze(r, S_NAME, e.name)
            self._setze(r, S_EBENE, " / ".join(e.geraet.pfad) or "—")
            self._setze(r, S_TYP, e.typ_text)
            if r not in self._profil_auswahl:
                self._setze(r, S_PROFIL, e.profil_text)
            adresse = e.adresse_text
            self._setze(r, S_ADRESSE, adresse,
                        f"In der Datei: {e.geraet.adresse_text or '—'}")
            cb = self._konflikt_auswahl[r]
            cb.blockSignals(True)
            cb.setCurrentIndex(cb.findData(e.aktion) if e.konflikt else 0)
            cb.blockSignals(False)
            cb.setEnabled(bool(e.konflikt))
            cb.setToolTip(e.konflikt or "Kein Konflikt.")
            x, y, z = e.position
            rx, ry, rz = e.rotation
            self._setze(r, S_POS, f"{x:.2f}, {y:.2f}, {z:.2f}",
                        f"Position x={x:.3f} m, Höhe={y:.3f} m, z={z:.3f} m\n"
                        f"Drehung {rx:.1f}° / {ry:.1f}° / {rz:.1f}°")
            self._setze(r, S_STATUS, e.status_text, farbe=_FARBE.get(e.status, ""))
        self.zusammenfassung.setText(self.plan.zaehlerzeile() + ".")
        geht = bool(self.plan.anlegbare())
        konflikte = [e for e in self.plan.eintraege if e.konflikt]
        self.knopf_alle_ueberspringen.setEnabled(bool(konflikte))
        self.knopf_alle_frei.setEnabled(bool(konflikte))
        self.hinweis_konflikt.setVisible(
            not geht and any(e.aktion == I.UEBERSPRINGEN for e in konflikte))
        self.knopf_importieren.setEnabled(geht)
        self.knopf_importieren.setToolTip(TIPP_IMPORTIEREN if geht else TIPP_IMPORTIEREN_AUS)
        self._zeilen_anpassen()

    def _zeilen_anpassen(self):
        if self.tabelle.rowCount() <= ZEILEN_ANPASSEN_MAX:
            self.tabelle.resizeRowsToContents()

    def showEvent(self, event):
        super().showEvent(event)
        # Die mitwachsende Status-Spalte hat ihre Breite erst nach dem Layout
        QTimer.singleShot(0, self._zeilen_anpassen)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._zeilen_anpassen)

    # ── Anwenden ─────────────────────────────────────────────────────────────

    def _importieren(self):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            ergebnis = I.wende_an(self._state, self.plan, self._bibliothek)
        except Exception as e:     # wende_an faengt selbst; letzte Sicherung
            ergebnis = I.Ergebnis(fehler=[f"Der Import schlug fehl: {e}"],
                                  zurueckgenommen=True)
        finally:
            QApplication.restoreOverrideCursor()
        self.ergebnis = ergebnis
        self.accept()


def meldung_nach_import(ergebnis: I.Ergebnis) -> str:
    if ergebnis.zurueckgenommen:
        return ("Es wurde nichts angelegt.\n\n" + "\n".join(ergebnis.fehler))
    n = ergebnis.geraete
    text = ("1 Gerät angelegt und im 3D platziert." if n == 1
            else f"{n} Geräte angelegt und im 3D platziert.")
    if ergebnis.neue_profile:
        text += ("\n\nNeu in der Geräte-Bibliothek (aus GDTF): "
                 + ", ".join(ergebnis.neue_profile) + ".")
    if ergebnis.ausgelassen:
        m = ergebnis.ausgelassen
        text += (f"\n\n{m} Gerät{'e' if m > 1 else ''} der Datei "
                 f"wurde{'n' if m > 1 else ''} nicht angelegt (nicht zugeordnet "
                 "oder übersprungen).")
    if ergebnis.fehler:
        text += "\n\n" + "\n".join(ergebnis.fehler)
    if n:
        text += "\n\nRückgängig (Strg+Z) nimmt den ganzen Import in einem Schritt zurück."
    return text


def importieren_starten(parent, state, pfad: str | None = None,
                        bibliothek: T.Bibliothek | None = None) -> I.Ergebnis | None:
    """Der ganze Weg: Datei waehlen -> lesen -> Vorschau -> Anwenden -> Meldung.
    Rueckgabe: das Ergebnis, ``None`` bei Abbruch oder unlesbarer Datei."""
    if pfad is None:
        pfad, _ = QFileDialog.getOpenFileName(parent, TITEL, "", DATEI_FILTER)
        if not pfad:
            return None
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        datei = lies_mvr(pfad)
        fehler = ""
    except MvrFehler as e:
        datei, fehler = None, str(e)
    finally:
        QApplication.restoreOverrideCursor()
    if datei is None:
        QMessageBox.warning(parent, TITEL,
                            f"Die Datei „{os.path.basename(pfad)}“ wurde nicht "
                            f"importiert.\n\n{fehler}")
        return None
    if not datei.geraete:
        QMessageBox.information(parent, TITEL,
                                "Die Datei enthält keine Geräte — es gibt "
                                "nichts zu importieren.")
        return None
    if bibliothek is None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            bibliothek = T.bibliothek_aus_db()
        finally:
            QApplication.restoreOverrideCursor()
    dlg = MvrImportDialog(state, datei, bibliothek, os.path.basename(pfad), parent)
    if not dlg.exec() or dlg.ergebnis is None:
        return None
    if dlg.ergebnis.zurueckgenommen:
        QMessageBox.warning(parent, TITEL, meldung_nach_import(dlg.ergebnis))
    else:
        QMessageBox.information(parent, TITEL, meldung_nach_import(dlg.ergebnis))
    return dlg.ergebnis
