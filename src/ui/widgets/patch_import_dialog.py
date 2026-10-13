"""IMP-1: Dialog „Patch aus Tabelle importieren“ — Vorschau, Profilwahl, Anwenden.

Der Dialog rechnet nichts selbst: Lesen, Zuordnen, Pruefen und Anlegen macht
``src.core.patch_tabelle``. Hier steht nur, was man sieht — je Tabellenzeile
eine Zeile mit Auswahlfeld fuer Profil/Modus und dem Grund im Klartext, eine
Zaehlerzeile und „Anwenden“.

★ Qt-Fallen, die hier bewusst umgangen sind:

* Die Auswahlfelder werden EINMAL beim Aufbau erzeugt und nie ersetzt. Eine
  Wahl rechnet den Plan neu und schreibt nur TEXTE in vorhandene Zellen —
  kein Neuaufbau der Tabelle aus dem Signal eines ihrer eigenen Widgets
  (Absturzmuster STAB-38).
* Das Mausrad verstellt kein Auswahlfeld. Beim Scrollen durch eine lange
  Liste wuerde sonst still ein anderes Profil gewaehlt — genau das, was der
  Import nie tun darf.
* Die Spaltenbreiten rechnet ``_spalten_verteilen`` selbst aus der Breite der
  Tabelle. „Status“ ist die LETZTE Spalte und bekommt, was uebrig bleibt —
  mindestens :data:`STATUS_MIN`. Mit ``ResizeToContents`` fuer die uebrigen
  Spalten schob ein langer Name oder Profiltext den Grund aus dem Bild; er war
  dann nur ueber den waagerechten Rollbalken zu lesen.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QFileDialog,
    QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from src.core import patch_tabelle as T
from src.ui.widgets import dialog_groesse

TITEL = "Patch aus Tabelle importieren"
DATEI_FILTER = "Tabellen (*.csv *.txt *.tsv);;Alle Dateien (*)"

SPALTEN = ["Zeile", "Name", "Tabelle", "Profil / Modus", "Univ.",
           "Adresse", "Kanäle", "Status"]
#: IMP-3: Erklaerung je Spaltenkopf. Der Kopf „Tabelle“ hiess „In der
#: Tabelle“ und stand bei 900 px Dialogbreite als „n der Tabell“ da — jetzt
#: ist er kurz, die Erklaerung steht hier, und keine Spalte wird schmaler
#: als ihr Kopftext (``_kleinste_breite``).
SPALTEN_TIPP = {
    0: "Zeilennummer in der Datei.",
    1: "Name, unter dem das Gerät im Patch angelegt wird. Gab es den Namen "
       "schon, steht hier der neue Name mit Nummer.",
    2: "So steht das Gerät in der Tabelle: Hersteller, Profil und Modus, "
       "wie sie in der Datei geschrieben sind.",
    3: "Profil und Modus aus der Geräte-Bibliothek, mit denen die Zeile "
       "angelegt wird. Bei „offen“ hier das richtige Gerät wählen.",
    4: "Universum, in das das Gerät gepatcht wird.",
    5: "Startadresse des Geräts (bei mehreren Geräten: des ersten).",
    6: "Kanäle, die ein Gerät in diesem Modus belegt.",
    7: "Was mit der Zeile passiert und warum.",
}
S_ZEILE, S_NAME, S_TABELLE, S_PROFIL, S_UNIV, S_ADRESSE, S_KANAELE, S_STATUS = range(8)

#: Breite, die „Status“ (der Grund im Klartext) immer behaelt.
STATUS_MIN = 240
#: Breite, mit der „Status“ in die Startgroesse des Dialogs eingeht.
STATUS_WUNSCH = 420
#: Die schmalen Zahlenspalten: nach Inhalt, hoechstens so breit.
SCHMAL_MAX = 90
#: Textspalten, die sich den Platz teilen: (kleinste, groesste Breite). Reicht
#: der Platz nicht fuer den Inhalt, schrumpfen sie; der Text bricht um bzw.
#: steht ganz im Tooltip.
BIEGSAM = {1: (80, 220), 2: (80, 240), 3: (170, 460)}     # Name, Tabelle, Profil
#: Startgroesse: nie schmaler/breiter bzw. hoeher als das (der Bildschirm
#: begrenzt zusaetzlich).
START_BREITE = (900, 1500)
START_HOEHE = 620

BITTE_WAEHLEN = "— bitte wählen —"
MODUS_WAEHLEN = "— Modus wählen —"
KEIN_VORSCHLAG = "— kein passendes Profil —"

#: IMP-3: Farbe des Namens, wenn der Import ihn nummeriert hat.
FARBE_UMBENANNT = "#d29922"

_FARBE = {
    T.ANLEGBAR: "#3fb950",
    T.OFFEN: "#d29922",
    T.UEBERSCHNEIDUNG: "#f85149",
    T.FEHLER: "#f85149",
}

TIPP_ANWENDEN = ("Legt alle Zeilen an, bei denen „wird angelegt“ steht. Offene "
                 "und fehlerhafte Zeilen bleiben weg. Vorhandene Geräte werden "
                 "nicht verändert; Rückgängig (Strg+Z) nimmt den Import in "
                 "einem Schritt zurück.")
TIPP_ANWENDEN_AUS = ("Noch keine Zeile lässt sich anlegen — bei offenen Zeilen "
                     "ein Profil wählen oder die Tabelle berichtigen.")


class _AuswahlOhneRad(QComboBox):
    """Auswahlfeld, das auf das Mausrad nicht reagiert (s. Modulkopf)."""

    def wheelEvent(self, event):
        event.ignore()


def _eintrag_text(profil: T.Profil, modus: T.Modus) -> str:
    return f"{profil.anzeige} · {modus.name} ({modus.kanaele} Kanäle)"


class PatchImportDialog(QDialog):
    """Vorschau einer gelesenen Tabelle. Nach ``exec()`` steht in
    ``ergebnis``, was angelegt wurde (``None`` = abgebrochen)."""

    def __init__(self, state, tabelle: T.Tabelle, bibliothek: T.Bibliothek,
                 dateiname: str = "", parent=None):
        super().__init__(parent)
        self._state = state
        self._tabelle = tabelle
        self._bibliothek = bibliothek
        self.wahl: dict[int, tuple[int, str]] = {}
        self.plan: T.Plan = self._rechne()
        self.ergebnis: T.Ergebnis | None = None
        self._auswahl: list[QComboBox] = []
        self._wunsch: dict[int, int] = {}
        self.setWindowTitle(TITEL)
        self._aufbauen(dateiname)
        self._zeigen()
        # Mindestbreite: alle Spalten auf ihrer kleinsten Breite UND der Grund.
        # Keine feste Startgroesse — die setzt showEvent passend zu Inhalt und
        # Bildschirm (ein zu grosses Mindestmass zieht es dort mit herunter).
        self.setMinimumSize(self._breite_fuer(kleinste=True), 360)

    # ── Aufbau (einmal) ──────────────────────────────────────────────────────

    def _aufbauen(self, dateiname: str):
        layout = QVBoxLayout(self)
        tab = self._tabelle
        kopf = (f"<b>{_html(dateiname) or 'Tabelle'}</b> — {len(tab.zeilen)} "
                f"Zeile(n), Trennzeichen "
                f"{T.TRENNZEICHEN_TEXT.get(tab.trennzeichen, repr(tab.trennzeichen))}, "
                f"{tab.kodierung}")
        for hinweis in tab.hinweise:
            kopf += f"<br>{_html(hinweis)}"
        self._lbl_kopf = QLabel(kopf)
        self._lbl_kopf.setWordWrap(True)
        layout.addWidget(self._lbl_kopf)

        erklaerung = QLabel(
            "Angelegt wird nur, was sicher erkannt ist. Bei <b>offen</b> in der "
            "Spalte „Profil / Modus“ das richtige Gerät wählen — LightOS rät "
            "nicht.")
        erklaerung.setWordWrap(True)
        layout.addWidget(erklaerung)

        self._table = QTableWidget(len(self.plan.zeilen), len(SPALTEN))
        self._table.setHorizontalHeaderLabels(SPALTEN)
        for spalte, tipp in SPALTEN_TIPP.items():
            self._table.horizontalHeaderItem(spalte).setToolTip(tipp)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setWordWrap(True)
        self._table.verticalHeader().hide()
        hdr = self._table.horizontalHeader()
        # Breiten setzt _spalten_verteilen; „Status“ (letzte Spalte) nimmt den
        # Rest. Kein ResizeToContents — s. Modulkopf.
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setMinimumSectionSize(30)
        hdr.setStretchLastSection(True)
        for zeile, pz in enumerate(self.plan.zeilen):
            for spalte in range(len(SPALTEN)):
                if spalte != S_PROFIL:
                    self._table.setItem(zeile, spalte, QTableWidgetItem(""))
            auswahl = self._auswahl_bauen(pz)
            self._auswahl.append(auswahl)
            # In einem Rahmen mit Layout: sonst zieht die Tabelle das Feld
            # auf die volle Hoehe einer mehrzeiligen Status-Zelle.
            rahmen = QWidget()
            innen = QVBoxLayout(rahmen)
            innen.setContentsMargins(2, 2, 2, 2)
            innen.addWidget(auswahl, 0, Qt.AlignmentFlag.AlignVCenter)
            self._table.setCellWidget(zeile, S_PROFIL, rahmen)
        # Erst NACH dem Befuellen verbinden: das Vorbelegen ist keine Wahl.
        for zeile, auswahl in enumerate(self._auswahl):
            auswahl.currentIndexChanged.connect(
                lambda _i, z=zeile: self._gewaehlt(z))
        layout.addWidget(self._table, 1)
        self._table.installEventFilter(self)

        self._lbl_zaehler = QLabel("")
        self._lbl_zaehler.setObjectName("patch_import_zaehler")
        self._lbl_zaehler.setWordWrap(True)
        self._lbl_zaehler.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._lbl_zaehler)

        knoepfe = QHBoxLayout()
        self._btn_vorlage = QPushButton("Vorlage speichern …")
        self._btn_vorlage.setToolTip(
            "Schreibt eine Beispiel-Tabelle mit Kopfzeile und zwei Zeilen — "
            "zum Ausfüllen im Tabellenprogramm.")
        self._btn_vorlage.clicked.connect(lambda: vorlage_speichern(self))
        self._btn_anwenden = QPushButton("Anwenden")
        self._btn_anwenden.setDefault(True)
        self._btn_anwenden.clicked.connect(self._anwenden)
        self._btn_abbrechen = QPushButton("Abbrechen")
        self._btn_abbrechen.setToolTip("Schließt die Vorschau, ohne etwas anzulegen.")
        self._btn_abbrechen.clicked.connect(self.reject)
        knoepfe.addWidget(self._btn_vorlage)
        knoepfe.addStretch()
        knoepfe.addWidget(self._btn_anwenden)
        knoepfe.addWidget(self._btn_abbrechen)
        layout.addLayout(knoepfe)

    def _auswahl_bauen(self, pz: T.PlanZeile) -> QComboBox:
        """Auswahlfeld einer Zeile. Die Eintraege haengen nur an der Tabelle
        und der Bibliothek, nicht an der Wahl — darum einmal und fertig."""
        box = _AuswahlOhneRad()
        box.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        box.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        box.setMinimumContentsLength(18)
        if pz.profil is not None:
            # Profil erkannt: zur Wahl stehen seine Modi.
            if pz.modus is None:
                box.addItem(MODUS_WAEHLEN, None)
            for modus in pz.profil.modi:
                box.addItem(_eintrag_text(pz.profil, modus),
                            (pz.profil.id, modus.name))
            if pz.modus is not None:
                box.setCurrentIndex(box.findText(_eintrag_text(pz.profil, pz.modus)))
            box.setToolTip("Erkanntes Profil. Hier lässt sich der Modus "
                           "(Kanalbelegung) umstellen.")
        elif pz.vorschlaege:
            box.addItem(BITTE_WAEHLEN, None)
            for profil in pz.vorschlaege:
                for modus in profil.modi:
                    box.addItem(_eintrag_text(profil, modus), (profil.id, modus.name))
            box.setToolTip("Nicht sicher erkannt. Zur Wahl stehen die "
                           "ähnlichsten Profile der Geräte-Bibliothek, je Modus.")
        else:
            box.addItem(KEIN_VORSCHLAG, None)
            box.setEnabled(False)
            box.setToolTip("Die Geräte-Bibliothek hat kein ähnliches Profil. "
                           "Namen in der Tabelle berichtigen oder das Profil "
                           "zuerst anlegen (Patch → Gerät erstellen…).")
        box.setProperty("_hilfe", box.toolTip())
        # Die aufgeklappte Liste so breit wie ihr laengster Eintrag — sie darf
        # ueber das (schmalere) Feld hinausragen, statt Text abzuschneiden.
        liste = box.view()
        liste.setTextElideMode(Qt.TextElideMode.ElideNone)
        liste.setMinimumWidth(self._eintrag_breite(box)
                              + liste.verticalScrollBar().sizeHint().width())
        self._auswahl_tooltip(box)
        return box

    @staticmethod
    def _eintrag_breite(box: QComboBox) -> int:
        """Breite, die der laengste Eintrag von ``box`` samt Rand braucht."""
        fm = box.fontMetrics()
        text = max((fm.horizontalAdvance(box.itemText(i))
                    for i in range(box.count())), default=0)
        return text + 4 * fm.horizontalAdvance("x") + 2 * box.view().frameWidth()

    @staticmethod
    def _auswahl_tooltip(box: QComboBox):
        """Tooltip des Auswahlfelds: der GEWAEHLTE Eintrag in voller Laenge
        (im Feld kann er abgeschnitten sein), darunter die Erklaerung."""
        hilfe = box.property("_hilfe") or ""
        gewaehlt = box.currentText()
        box.setToolTip(f"{gewaehlt}\n\n{hilfe}" if gewaehlt else hilfe)

    # ── Rechnen und Anzeigen ─────────────────────────────────────────────────

    def _rechne(self) -> T.Plan:
        return T.baue_plan(self._tabelle, self._bibliothek,
                           T.belegung_aus_state(self._state), self.wahl)

    def _gewaehlt(self, zeile: int):
        daten = self._auswahl[zeile].currentData()
        if daten is None:
            self.wahl.pop(zeile, None)
        else:
            self.wahl[zeile] = (int(daten[0]), str(daten[1]))
        self._auswahl_tooltip(self._auswahl[zeile])
        self.plan = self._rechne()
        self._zeigen()

    def waehle(self, zeile: int, index: int):
        """Eintrag ``index`` im Auswahlfeld von ``zeile`` nehmen (wie ein Klick)."""
        self._auswahl[zeile].setCurrentIndex(index)

    def _zeigen(self):
        """Texte der vorhandenen Zellen aus ``self.plan`` setzen — ersetzt
        weder Zellen noch Auswahlfelder."""
        for zeile, pz in enumerate(self.plan.zeilen):
            z = pz.zeile
            # IMP-3: der Name, unter dem WIRKLICH angelegt wird.
            name = pz.anzeige_name + (f"  ×{z.anzahl}" if z.anzahl > 1 else "")
            texte = {
                S_ZEILE: str(z.nr),
                S_NAME: name,
                S_TABELLE: z.profil_text,
                S_UNIV: str(pz.universum),
                S_ADRESSE: "" if z.adresse is None else str(z.adresse),
                S_KANAELE: "" if pz.kanaele is None else str(pz.kanaele),
                S_STATUS: pz.status_text,
            }
            for spalte, text in texte.items():
                item = self._table.item(zeile, spalte)
                item.setText(text)
                item.setToolTip(text)
            status = self._table.item(zeile, S_STATUS)
            status.setForeground(QColor(_FARBE[pz.status]))
            # IMP-3: ein umbenanntes Geraet faellt in der Spalte „Name“ auf
            # (fett, Hinweisfarbe); der Tooltip nennt alten und neuen Namen.
            zelle = self._table.item(zeile, S_NAME)
            schrift = zelle.font()
            schrift.setBold(bool(pz.umbenannt))
            zelle.setFont(schrift)
            if pz.umbenannt:
                zelle.setForeground(QColor(FARBE_UMBENANNT))
                zelle.setToolTip("\n".join(
                    f"„{alt}“ gab es schon — heißt jetzt „{neu}“."
                    for alt, neu in pz.umbenannt))
            else:
                zelle.setData(Qt.ItemDataRole.ForegroundRole, None)
        self._wunsch = self._wunschbreiten()
        self._zeilenhoehen()
        self._lbl_zaehler.setText(self.plan.zaehlerzeile())
        anlegbar = bool(self.plan.anlegbare())
        self._btn_anwenden.setEnabled(anlegbar)
        self._btn_anwenden.setToolTip(TIPP_ANWENDEN if anlegbar else TIPP_ANWENDEN_AUS)

    # ── Spaltenbreiten ───────────────────────────────────────────────────────

    def _wunschbreiten(self) -> dict[int, int]:
        """Je Spalte (ohne „Status“) die Breite, die ihr Inhalt haben moechte,
        schon auf die Obergrenze gekappt."""
        kopf = self._table.horizontalHeader()
        fm = self._table.fontMetrics()
        rand = 3 * fm.horizontalAdvance("x")
        wunsch: dict[int, int] = {}
        for spalte in range(len(SPALTEN)):
            if spalte == S_STATUS:
                continue
            breite = kopf.sectionSizeHint(spalte)
            if spalte == S_PROFIL:
                for box in self._auswahl:
                    # Feld = laengster Eintrag + Pfeil + Rand der Zelle.
                    breite = max(breite, self._eintrag_breite(box) + 36)
            else:
                for zeile in range(self._table.rowCount()):
                    item = self._table.item(zeile, spalte)
                    if item is not None:
                        breite = max(breite,
                                     fm.horizontalAdvance(item.text()) + rand)
            if spalte in BIEGSAM:
                kleinste, groesste = BIEGSAM[spalte]
                breite = max(kleinste, min(breite, groesste))
            else:
                breite = min(breite, SCHMAL_MAX)
            wunsch[spalte] = breite
        return wunsch

    def _kleinste_breite(self, spalte: int) -> int:
        """IMP-3: kleinste Breite einer Textspalte — nie schmaler als ihr
        Kopftext („n der Tabell“ bei 900 px)."""
        return max(BIEGSAM[spalte][0],
                   self._table.horizontalHeader().sectionSizeHint(spalte))

    def _tabellen_rand(self) -> int:
        """Was von der Breite der Tabelle nicht den Spalten gehoert: Rahmen
        und der senkrechte Rollbalken (immer mitgerechnet, damit die Breiten
        nicht springen, wenn er erscheint)."""
        return (2 * self._table.frameWidth()
                + self._table.verticalScrollBar().sizeHint().width())

    def _breite_fuer(self, *, kleinste: bool = False) -> int:
        """Dialogbreite, bei der alle Spalten ihre Wunschbreite haben
        (``kleinste``: ihre kleinste Breite, „Status“ :data:`STATUS_MIN`)."""
        wunsch = self._wunsch or self._wunschbreiten()
        if kleinste:
            spalten = sum(self._kleinste_breite(s) if s in BIEGSAM else b
                          for s, b in wunsch.items()) + STATUS_MIN
        else:
            spalten = sum(wunsch.values()) + STATUS_WUNSCH
        raender = self.layout().contentsMargins()
        return (spalten + self._tabellen_rand()
                + raender.left() + raender.right())

    def _spalten_verteilen(self):
        """Breiten aller Spalten ausser „Status“ setzen; „Status“ nimmt den
        Rest. Reicht der Platz nicht fuer alle Wunschbreiten, geben die
        Textspalten nach — „Status“ behaelt :data:`STATUS_MIN`."""
        wunsch = self._wunsch
        if not wunsch:
            return
        platz = self._table.width() - self._tabellen_rand() - STATUS_MIN
        fest = sum(b for s, b in wunsch.items() if s not in BIEGSAM)
        klein = {s: min(self._kleinste_breite(s), wunsch[s]) for s in BIEGSAM}
        frei = platz - fest - sum(klein.values())
        breiten = {s: b for s, b in wunsch.items() if s not in BIEGSAM}
        # Zuerst das Auswahlfeld: sein Text bricht nicht um. Was dann noch
        # frei ist, teilen sich Name und „Tabelle“ (die umbrechen).
        for gruppe in ((S_PROFIL,), tuple(s for s in BIEGSAM if s != S_PROFIL)):
            luft = sum(wunsch[s] - klein[s] for s in gruppe)
            anteil = 1.0 if luft <= 0 else max(0.0, min(1.0, frei / luft))
            for spalte in gruppe:
                kleinste = klein[spalte]
                breiten[spalte] = kleinste + int((wunsch[spalte] - kleinste) * anteil)
                frei -= breiten[spalte] - kleinste
        for spalte, breite in breiten.items():
            if self._table.columnWidth(spalte) != breite:
                self._table.setColumnWidth(spalte, breite)

    def _zeilenhoehen(self):
        """Spalten verteilen und Zeilen so hoch, dass der Status-Satz ganz zu
        lesen ist. Haengt an der Breite — darum auch nach dem Zeigen und nach
        jedem Groessenwechsel des Fensters."""
        self._spalten_verteilen()
        self._table.resizeRowsToContents()

    def showEvent(self, event):
        # FM-74: Startgroesse aus Inhalt und Bildschirm, VOR super() — Qt
        # mittet den Dialog dann mit der endgueltigen Groesse ein.
        breite = max(START_BREITE[0], min(self._breite_fuer(), START_BREITE[1]))
        dialog_groesse.beim_ersten_zeigen_anpassen(
            self, wunsch=QSize(breite, START_HOEHE))
        super().showEvent(event)
        self._zeilenhoehen()

    def eventFilter(self, objekt, event):
        # Auf die Groesse der TABELLE hoeren, nicht auf die des Dialogs: erst
        # wenn das Layout sie gesetzt hat, stimmt die Breite, aus der gerechnet
        # wird.
        if objekt is self._table and event.type() == QEvent.Type.Resize:
            self._zeilenhoehen()
        return super().eventFilter(objekt, event)

    # ── Abfragen (auch fuer Tests) ───────────────────────────────────────────

    def zaehlerzeile(self) -> str:
        return self._lbl_zaehler.text()

    def status_text(self, zeile: int) -> str:
        return self._table.item(zeile, S_STATUS).text()

    def anwenden_moeglich(self) -> bool:
        return self._btn_anwenden.isEnabled()

    # ── Anwenden ─────────────────────────────────────────────────────────────

    def _anwenden(self):
        if not self.plan.anlegbare():
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.ergebnis = T.wende_an(self._state, self.plan, self._bibliothek)
        finally:
            QApplication.restoreOverrideCursor()
        self.accept()


def _html(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── Einstiege aus dem Patch ──────────────────────────────────────────────────

def vorlage_speichern(parent, pfad: str | None = None) -> str | None:
    """Beispiel-Tabelle schreiben. Ohne ``pfad`` fragt ein Dateidialog.
    Rueckgabe: der geschriebene Pfad oder ``None``."""
    if pfad is None:
        pfad, _ = QFileDialog.getSaveFileName(
            parent, "Vorlage speichern", "LightOS-Patch-Vorlage.csv",
            "CSV-Tabelle (*.csv)")
        if not pfad:
            return None
        if not os.path.splitext(pfad)[1]:
            pfad += ".csv"
    try:
        T.schreibe_vorlage(pfad)
    except OSError as e:
        QMessageBox.warning(parent, "Vorlage speichern",
                            f"Die Vorlage ließ sich nicht schreiben:\n{e.strerror or e}")
        return None
    QMessageBox.information(
        parent, "Vorlage speichern",
        f"Vorlage gespeichert:\n{pfad}\n\n"
        "Im Tabellenprogramm öffnen, die zwei Beispielzeilen durch die eigenen "
        "Geräte ersetzen, als CSV speichern und dann über „Aus Tabelle "
        "importieren …“ einlesen.")
    return pfad


def meldung_nach_import(ergebnis: T.Ergebnis) -> str:
    """Der Satz nach dem Anwenden."""
    n = ergebnis.geraete
    text = "1 Gerät angelegt." if n == 1 else f"{n} Geräte angelegt."
    if ergebnis.umbenannt:
        u = ergebnis.umbenannt
        text += (f"\n\n{u} Gerät{'e' if u > 1 else ''} "
                 f"{'haben' if u > 1 else 'hat'} eine Nummer am Namen bekommen, "
                 "weil es den Namen schon gab.")
    if ergebnis.ausgelassen:
        m = ergebnis.ausgelassen
        text += (f"\n\n{m} Zeile{'n' if m > 1 else ''} der Tabelle "
                 f"wurde{'n' if m > 1 else ''} nicht angelegt (offen, "
                 "Überschneidung oder Fehler).")
    if ergebnis.fehler:
        text += "\n\n" + "\n".join(ergebnis.fehler)
    text += ("\n\nRückgängig (Strg+Z) nimmt den ganzen Import in einem "
             "Schritt zurück.")
    return text


def importieren_starten(parent, state, pfad: str | None = None,
                        bibliothek: T.Bibliothek | None = None) -> T.Ergebnis | None:
    """Der ganze Weg: Datei waehlen -> Vorschau -> Anwenden -> Meldung.
    Rueckgabe: das Ergebnis, ``None`` bei Abbruch oder unlesbarer Tabelle."""
    if pfad is None:
        pfad, _ = QFileDialog.getOpenFileName(parent, TITEL, "", DATEI_FILTER)
        if not pfad:
            return None
    tabelle = T.lies_datei(pfad)
    if tabelle.fehler:
        QMessageBox.warning(
            parent, TITEL,
            f"{tabelle.fehler}\n\nEine Beispiel-Tabelle zum Ausfüllen gibt es "
            "über „Vorlage speichern …“.")
        return None
    if bibliothek is None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            bibliothek = T.bibliothek_aus_db()
        finally:
            QApplication.restoreOverrideCursor()
    dlg = PatchImportDialog(state, tabelle, bibliothek,
                            os.path.basename(pfad), parent)
    if not dlg.exec() or dlg.ergebnis is None:
        return None
    QMessageBox.information(parent, TITEL, meldung_nach_import(dlg.ergebnis))
    return dlg.ergebnis
