"""LAS-33: die Laser-Seiten des Fixture Generators — Muster, Farben, Richtungen.

Drei Seiten je Modus, sichtbar nur bei einem Laser:

* :class:`MusterSeite` — Musterliste eines Kanals als Tabelle (von, bis, Name,
  Form aus dem Baukasten, Anzahl, Stil, bewegt) mit Schemabild je Zeile und
  grosser Vorschau; „Bereiche gleichmäßig aufteilen“ und „Eigene Form
  zeichnen“;
* :class:`FarbSeite` — Farbtabelle eines Kanals mit Farbfeld und einer Leiste,
  die zeigt, wo die Farben auf 0–255 liegen;
* :class:`RichtungSeite` — je Kanal: sprechende Enden, „läuft umgekehrt“,
  Mittelbereich; daneben die Bedeutung der Betriebsart-Bereiche.

Die Seiten schreiben direkt in ``kanal.laser`` (ein ``dict`` im Aufbau von
``src/core/laser/profilangaben.py``) — dasselbe Objekt, das der Generator
speichert. Ein Kanal ist hier alles mit ``name``, ``attribute``, ``laser`` und
``ranges`` (``GenChannel``).
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import (QBrush, QColor, QLinearGradient, QPainter, QPen,
                           QPixmap)
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QColorDialog,
                               QComboBox, QGroupBox, QHBoxLayout, QHeaderView,
                               QInputDialog, QLabel, QMessageBox, QPushButton,
                               QSpinBox, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from src.core.laser import profilangaben as PA
from src.core.laser.musterformen import anzahl_fuer
from src.ui.widgets.laser_musterbild import (FormZeichnenDialog, MusterBild,
                                             muster_pixmap)

ZEILENHOEHE = 30
VORSCHAU = 168         # Kantenlaenge der Mustervorschau
_HINWEIS_STIL = "color:#d29922;"
_LEISE_STIL = "color:#7d8590; font-size:11px;"

#: Attribute, an denen ein Kanal ueblicherweise die Muster bzw. Farben waehlt —
#: nur fuer die VORAUSWAHL des Kanals; waehlbar ist jeder.
MUSTER_ATTRIBUTE = ("gobo_wheel", "laser_bank", "gobo_wheel2", "effect", "macro")
FARB_ATTRIBUTE = ("laser_color", "color_wheel")
BETRIEBSART_ATTRIBUTE = ("shutter", "macro")


def _mitte(widget: QWidget) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(widget)
    return w


def _spin(wert: int, lo: int = 0, hi: int = 255) -> QSpinBox:
    sp = QSpinBox()
    sp.setRange(lo, hi)
    sp.setValue(int(wert))
    sp.setFrame(False)
    return sp


def _tabelle(spalten: list[str], dehnen: int) -> QTableWidget:
    tbl = QTableWidget(0, len(spalten))
    tbl.setHorizontalHeaderLabels(spalten)
    kopf = tbl.horizontalHeader()
    kopf.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    kopf.setSectionResizeMode(dehnen, QHeaderView.ResizeMode.Stretch)
    tbl.verticalHeader().setDefaultSectionSize(ZEILENHOEHE)
    tbl.verticalHeader().setVisible(False)
    tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    tbl.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked |
                        QAbstractItemView.EditTrigger.SelectedClicked)
    return tbl


def _feste_breite(tbl: QTableWidget, breiten: dict[int, int]) -> None:
    """Spalten mit Eingabefeldern auf feste Breite — „an den Inhalt anpassen“
    misst die Zell-Widgets grosszuegig und nimmt der Namensspalte den Platz."""
    kopf = tbl.horizontalHeader()
    for spalte, breite in breiten.items():
        kopf.setSectionResizeMode(spalte, QHeaderView.ResizeMode.Fixed)
        tbl.setColumnWidth(spalte, breite)


def farb_pixmap(farbe: str, breite: int = 44, hoehe: int = 22) -> QPixmap:
    """Farbfeld zu einem Farbwert (``#rrggbb`` oder ``mehrfarbig``)."""
    bild = QPixmap(breite, hoehe)
    bild.fill(Qt.GlobalColor.transparent)
    p = QPainter(bild)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    rect = QRectF(0.5, 0.5, breite - 1, hoehe - 1)
    p.setPen(QPen(QColor("#2a3340"), 1))
    p.setBrush(_farb_pinsel(farbe, rect))
    p.drawRoundedRect(rect, 4, 4)
    p.end()
    return bild


def _farb_pinsel(farbe: str, rect: QRectF) -> QBrush:
    if farbe == PA.MEHRFARBIG:
        verlauf = QLinearGradient(rect.left(), 0, rect.right(), 0)
        for i, (_name, wert) in enumerate(
                (PA.FARBEN[k] for k in ("rot", "gelb", "gruen", "cyan", "blau",
                                        "magenta"))):
            verlauf.setColorAt(i / 5.0, QColor(wert))
        return QBrush(verlauf)
    c = QColor(farbe)
    return QBrush(c if c.isValid() else QColor("#444"))


class _KanalSeite(QWidget):
    """Gemeinsames der drei Seiten: der Modus, die Kanalwahl, der Rueckruf."""

    def __init__(self, mode, geaendert=None, parent=None):
        super().__init__(parent)
        self.mode = mode
        self._geaendert = geaendert
        self._baut = False

    def _melden(self) -> None:
        if self._geaendert is not None and not self._baut:
            try:
                self._geaendert()
            except Exception as e:      # die Seite bleibt bedienbar
                print(f"[laser_profil_seiten] ERROR: {e}")

    def _kanaele(self) -> list:
        return list(self.mode.channels)

    @staticmethod
    def _laser(kanal) -> dict:
        if not isinstance(getattr(kanal, "laser", None), dict):
            kanal.laser = {}
        return kanal.laser

    def _combo_fuellen(self, cb: QComboBox, feld: str, attribute,
                       bisher=None) -> None:
        """Kanalwahl neu fuellen. Vorauswahl: der bisher gewaehlte Kanal,
        sonst der erste MIT Angaben, sonst der erste mit passendem Attribut."""
        kanaele = self._kanaele()
        cb.blockSignals(True)
        cb.clear()
        for i, ch in enumerate(kanaele):
            cb.addItem(f"{i + 1}: {ch.name}", i)
        wahl = next((i for i, ch in enumerate(kanaele) if ch is bisher), None)
        if wahl is None:
            wahl = next((i for i, ch in enumerate(kanaele)
                         if self._laser(ch).get(feld)), None)
        if wahl is None:
            wahl = next((i for i, ch in enumerate(kanaele)
                         if (ch.attribute or "") in attribute), None)
        cb.setCurrentIndex(wahl if wahl is not None else (0 if kanaele else -1))
        cb.blockSignals(False)


# ── Muster ───────────────────────────────────────────────────────────────────

class MusterSeite(_KanalSeite):
    SPALTEN = ["Bild", "Von", "Bis", "Name", "Form", "Anzahl", "Stil", "bewegt"]
    C_BILD, C_VON, C_BIS, C_NAME, C_FORM, C_ANZAHL, C_STIL, C_BEWEGT = range(8)

    def __init__(self, mode, geaendert=None, parent=None):
        super().__init__(mode, geaendert, parent)
        self._kanal = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 8, 6, 4)

        kopf = QHBoxLayout()
        kopf.addWidget(QLabel("Musterkanal:"))
        self.cb_kanal = QComboBox()
        self.cb_kanal.setMinimumWidth(240)
        self.cb_kanal.setToolTip("Der Kanal, dessen DMX-Wert das Muster wählt.")
        self.cb_kanal.currentIndexChanged.connect(self._kanal_gewechselt)
        kopf.addWidget(self.cb_kanal)
        kopf.addSpacing(12)
        info = QLabel("Welcher DMX-Bereich zeigt welches Muster? Die Bedienung "
                      "macht daraus Musterbilder zum Antippen.")
        info.setStyleSheet("color:#9aa4af;")
        kopf.addWidget(info, 1)
        lay.addLayout(kopf)

        mitte = QHBoxLayout()
        self.tbl = _tabelle(self.SPALTEN, self.C_NAME)
        _feste_breite(self.tbl, {self.C_BILD: 44, self.C_VON: 66, self.C_BIS: 66,
                                 self.C_FORM: 170, self.C_ANZAHL: 66,
                                 self.C_STIL: 108, self.C_BEWEGT: 70})
        self.tbl.currentCellChanged.connect(lambda *_: self._vorschau())
        self.tbl.itemChanged.connect(self._name_geaendert)
        mitte.addWidget(self.tbl, 1)

        # Vorschau der gewaehlten Zeile. Feste Groessen: die Seite hat auf einem
        # 1080er-Bildschirm rund 240 px Hoehe (FM-70) — Bild, Unterschrift und
        # Schema-Hinweis muessen zusammen hineinpassen.
        rechts = QVBoxLayout()
        rechts.setSpacing(4)
        self.bild = MusterBild(groesse=VORSCHAU)
        self.bild.setFixedSize(VORSCHAU, VORSCHAU)
        self.bild.setToolTip("Schemazeichnung — am Gerät kann es anders aussehen.")
        rechts.addWidget(self.bild)
        self.lbl_bild = QLabel("")
        self.lbl_bild.setFixedSize(VORSCHAU, 34)
        self.lbl_bild.setAlignment(Qt.AlignmentFlag.AlignHCenter |
                                   Qt.AlignmentFlag.AlignTop)
        rechts.addWidget(self.lbl_bild)
        schema = QLabel("Schemazeichnung")
        schema.setFixedWidth(VORSCHAU)
        schema.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        schema.setStyleSheet(_LEISE_STIL)
        rechts.addWidget(schema)
        rechts.addStretch(1)
        mitte.addLayout(rechts)
        lay.addLayout(mitte, 1)

        knoepfe = QHBoxLayout()
        self.btn_neu = QPushButton("+ Muster")
        self.btn_neu.clicked.connect(lambda: self.zeile_dazu())
        self.btn_weg = QPushButton("- Muster")
        self.btn_weg.clicked.connect(lambda: self.zeile_weg())
        self.btn_aufteilen = QPushButton("Bereiche gleichmäßig aufteilen…")
        self.btn_aufteilen.setToolTip(
            "Verteilt eine Anzahl Muster lückenlos über 0–255 (z. B. 16 Muster "
            "= je 16 Werte). Vorhandene Zeilen behalten Name und Form.")
        self.btn_aufteilen.clicked.connect(self._aufteilen_fragen)
        self.btn_zeichnen = QPushButton("Eigene Form zeichnen…")
        self.btn_zeichnen.setToolTip(
            "Für die gewählte Zeile: Punkte klicken, die zu einer Linie "
            "verbunden werden — für Muster, die der Baukasten nicht hat.")
        self.btn_zeichnen.clicked.connect(self._zeichnen)
        for b in (self.btn_neu, self.btn_weg, self.btn_aufteilen,
                  self.btn_zeichnen):
            b.setAutoDefault(False)
            knoepfe.addWidget(b)
        knoepfe.addStretch(1)
        lay.addLayout(knoepfe)

        self.lbl_hinweis = QLabel("")
        self.lbl_hinweis.setWordWrap(True)
        self.lbl_hinweis.setStyleSheet(_HINWEIS_STIL)
        lay.addWidget(self.lbl_hinweis)
        self.aktualisieren()

    # ── Daten ────────────────────────────────────────────────────────────
    def kanal(self):
        return self._kanal

    def eintraege(self) -> list[dict]:
        """Die Musterliste des gewaehlten Kanals (das Original, kein Abzug)."""
        if self._kanal is None:
            return []
        liste = self._laser(self._kanal).setdefault("muster", [])
        return liste

    def aktualisieren(self) -> None:
        """Kanalwahl und Tabelle aus dem Modus neu aufbauen."""
        self._combo_fuellen(self.cb_kanal, "muster", MUSTER_ATTRIBUTE, self._kanal)
        self._kanal_gewechselt()

    def _kanal_gewechselt(self, *_):
        kanaele = self._kanaele()
        i = self.cb_kanal.currentIndex()
        self._kanal = kanaele[i] if 0 <= i < len(kanaele) else None
        self._tabelle_fuellen()

    def kanal_waehlen(self, index: int) -> None:
        self.cb_kanal.setCurrentIndex(index)

    def zeile_dazu(self, eintrag: dict | None = None) -> dict | None:
        if self._kanal is None:
            return None
        liste = self.eintraege()
        if eintrag is None:
            start = min(255, max((int(e.get("bis", -1)) for e in liste),
                                 default=-1) + 1)
            eintrag = {"von": start, "bis": start, "name": f"Muster {len(liste) + 1}",
                       "form": "kreis"}
        liste.append(eintrag)
        self._tabelle_fuellen(len(liste) - 1)
        self._melden()
        return eintrag

    def zeile_weg(self, zeile: int | None = None) -> None:
        liste = self.eintraege()
        zeile = self.tbl.currentRow() if zeile is None else zeile
        if 0 <= zeile < len(liste):
            del liste[zeile]
            self._tabelle_fuellen(min(zeile, len(liste) - 1))
            self._melden()

    def aufteilen(self, anzahl: int) -> None:
        """``anzahl`` Muster lueckenlos ueber 0–255. Vorhandene Zeilen behalten
        Name und Form; fehlende kommen als Kreis dazu, ueberzaehlige fallen weg."""
        if self._kanal is None:
            return
        liste = self.eintraege()
        teile = PA.gleichmaessig_aufteilen(anzahl)
        del liste[len(teile):]
        while len(liste) < len(teile):
            liste.append({"name": f"Muster {len(liste) + 1}", "form": "kreis"})
        for e, (von, bis) in zip(liste, teile):
            e["von"], e["bis"] = von, bis
        self._tabelle_fuellen(0)
        self._melden()

    def _aufteilen_fragen(self):
        liste = self.eintraege()
        n, ok = QInputDialog.getInt(
            self, "Bereiche gleichmäßig aufteilen",
            "Wie viele Muster hat der Kanal (über 0–255)?",
            len(liste) or 16, 1, 256)
        if not ok:
            return
        if n < len(liste):
            antwort = QMessageBox.question(
                self, "Bereiche gleichmäßig aufteilen",
                f"Es stehen {len(liste)} Muster in der Liste. Bei {n} fallen "
                f"die letzten {len(liste) - n} weg. Fortfahren?")
            if antwort != QMessageBox.StandardButton.Yes:
                return
        self.aufteilen(n)

    def eigene_form_setzen(self, zeile: int, linien: list[dict]) -> None:
        liste = self.eintraege()
        if not (0 <= zeile < len(liste)) or not linien:
            return
        e = liste[zeile]
        e["form"] = PA.EIGENE_FORM
        e["linien"] = linien
        e.pop("anzahl", None)
        self._tabelle_fuellen(zeile)
        self._melden()

    def _zeichnen(self):
        zeile = self.tbl.currentRow()
        liste = self.eintraege()
        if not (0 <= zeile < len(liste)):
            QMessageBox.information(self, "Eigene Form zeichnen",
                                    "Bitte zuerst eine Zeile der Musterliste "
                                    "wählen (oder mit „+ Muster“ anlegen).")
            return
        dlg = FormZeichnenDialog(self, liste[zeile].get("linien"),
                                 str(liste[zeile].get("name", "")))
        if dlg.exec() and dlg.linien():
            self.eigene_form_setzen(zeile, dlg.linien())

    # ── Tabelle ──────────────────────────────────────────────────────────
    def _tabelle_fuellen(self, zeile: int | None = None) -> None:
        liste = self.eintraege()
        if zeile is None:
            zeile = self.tbl.currentRow()
        self._baut = True
        self.tbl.blockSignals(True)
        self.tbl.setRowCount(len(liste))
        for i, e in enumerate(liste):
            self._zeile_bauen(i, e)
        self.tbl.blockSignals(False)
        self._baut = False
        for b in (self.btn_neu, self.btn_aufteilen):
            b.setEnabled(self._kanal is not None)
        if liste:
            self.tbl.setCurrentCell(max(0, min(zeile, len(liste) - 1)), self.C_NAME)
        self._vorschau()
        self._hinweise()

    def _zeile_bauen(self, i: int, e: dict) -> None:
        bild = QLabel()
        bild.setPixmap(muster_pixmap(e, ZEILENHOEHE - 4))
        self.tbl.setCellWidget(i, self.C_BILD, _mitte(bild))
        for spalte, feld in ((self.C_VON, "von"), (self.C_BIS, "bis")):
            sp = _spin(e.get(feld, 0))
            sp.valueChanged.connect(
                lambda v, z=i, f=feld: self._setze(z, f, int(v)))
            self.tbl.setCellWidget(i, spalte, sp)
        self.tbl.setItem(i, self.C_NAME, QTableWidgetItem(str(e.get("name", ""))))
        cb_form = QComboBox()
        for kennung, anzeige in PA.FORMEN.items():
            cb_form.addItem(anzeige, kennung)
        cb_form.setCurrentIndex(max(0, cb_form.findData(e.get("form", "kreis"))))
        cb_form.currentIndexChanged.connect(
            lambda _i, z=i, cb=cb_form: self._form_geaendert(z, cb.currentData()))
        self.tbl.setCellWidget(i, self.C_FORM, cb_form)
        form = e.get("form", "kreis")
        bedeutung = PA.ANZAHL_BEDEUTUNG.get(form)
        if bedeutung is not None:
            sp_n = _spin(anzahl_fuer(form, e.get("anzahl")), 1, PA.ANZAHL_MAX)
        else:                       # Form ohne Anzahl: ein Strich statt „1“
            sp_n = _spin(0, 0, 0)
            sp_n.setSpecialValueText("–")
        sp_n.setEnabled(bedeutung is not None)
        sp_n.setToolTip(f"Anzahl {bedeutung[0]}" if bedeutung
                        else "Diese Form hat keine Anzahl.")
        sp_n.valueChanged.connect(lambda v, z=i: self._setze(z, "anzahl", int(v)))
        self.tbl.setCellWidget(i, self.C_ANZAHL, sp_n)
        cb_stil = QComboBox()
        for kennung, anzeige in PA.STILE.items():
            cb_stil.addItem(anzeige, kennung)
        cb_stil.setCurrentIndex(max(0, cb_stil.findData(e.get("stil", "linie"))))
        cb_stil.currentIndexChanged.connect(
            lambda _i, z=i, cb=cb_stil: self._stil_geaendert(z, cb.currentData()))
        self.tbl.setCellWidget(i, self.C_STIL, cb_stil)
        chk = QCheckBox()
        chk.setChecked(bool(e.get("bewegt", False)))
        chk.setToolTip("Pulsierendes oder animiertes Muster.")
        chk.toggled.connect(lambda v, z=i: self._bewegt_geaendert(z, bool(v)))
        self.tbl.setCellWidget(i, self.C_BEWEGT, _mitte(chk))

    def zellen_widget(self, zeile: int, spalte: int):
        """Das Eingabe-Widget einer Zelle (Spinbox, Combo, Haken)."""
        w = self.tbl.cellWidget(zeile, spalte)
        if spalte in (self.C_BEWEGT, self.C_BILD) and w is not None:
            return w.findChild(QCheckBox if spalte == self.C_BEWEGT else QLabel)
        return w

    def _eintrag(self, zeile: int) -> dict | None:
        liste = self.eintraege()
        return liste[zeile] if 0 <= zeile < len(liste) else None

    def _nach_aenderung(self, zeile: int, neu_bauen: bool = False) -> None:
        if self._baut:
            return
        e = self._eintrag(zeile)
        if e is None:
            return
        if neu_bauen:
            self._tabelle_fuellen(zeile)
        else:
            bild = self.zellen_widget(zeile, self.C_BILD)
            if bild is not None:
                bild.setPixmap(muster_pixmap(e, ZEILENHOEHE - 4))
            self._vorschau()
            self._hinweise()
        self._melden()

    def _setze(self, zeile: int, feld: str, wert) -> None:
        e = self._eintrag(zeile)
        if e is None or self._baut:
            return
        e[feld] = wert
        self._nach_aenderung(zeile)

    def _form_geaendert(self, zeile: int, form: str) -> None:
        e = self._eintrag(zeile)
        if e is None or self._baut:
            return
        e["form"] = form
        e.pop("anzahl", None)
        if form != PA.EIGENE_FORM:
            e.pop("linien", None)
        self._nach_aenderung(zeile, neu_bauen=True)

    def _stil_geaendert(self, zeile: int, stil: str) -> None:
        e = self._eintrag(zeile)
        if e is None or self._baut:
            return
        if stil == "linie":
            e.pop("stil", None)
        else:
            e["stil"] = stil
        self._nach_aenderung(zeile)

    def _bewegt_geaendert(self, zeile: int, wert: bool) -> None:
        e = self._eintrag(zeile)
        if e is None or self._baut:
            return
        if wert:
            e["bewegt"] = True
        else:
            e.pop("bewegt", None)
        self._nach_aenderung(zeile)

    def _name_geaendert(self, item: QTableWidgetItem) -> None:
        if self._baut or item.column() != self.C_NAME:
            return
        e = self._eintrag(item.row())
        if e is not None:
            e["name"] = item.text().strip()
            self._nach_aenderung(item.row())

    def _vorschau(self) -> None:
        e = self._eintrag(self.tbl.currentRow())
        self.bild.set_muster(e)
        self.btn_zeichnen.setEnabled(e is not None)
        self.btn_weg.setEnabled(e is not None)
        if e is None:
            self.lbl_bild.setText("Kein Muster gewählt.")
            return
        von, bis = e.get("von", 0), e.get("bis", 0)
        wert = f"DMX {von}" if von == bis else f"DMX {von}–{bis}"
        zusatz = " · bewegt" if e.get("bewegt") else ""
        self.lbl_bild.setText(f"<b>{e.get('name', '')}</b><br>{wert}{zusatz}")

    def hinweise(self) -> list[str]:
        liste = self.eintraege()
        out = PA.bereichs_hinweise(liste, "Muster")
        for e in liste:
            if e.get("form") == PA.EIGENE_FORM and not e.get("linien"):
                out.append(f"Muster „{e.get('name', '')}“: eigene Form ohne "
                           f"Zeichnung — bitte „Eigene Form zeichnen…“, sonst "
                           f"wird der Eintrag nicht gespeichert.")
            if not str(e.get("name", "")).strip():
                out.append(f"Muster bei {e.get('von')}–{e.get('bis')}: ohne "
                           f"Namen wird der Eintrag nicht gespeichert.")
        return out

    def _hinweise(self) -> None:
        texte = self.hinweise()
        self.lbl_hinweis.setText("Hinweis: " + " ".join(texte) if texte else "")
        self.lbl_hinweis.setVisible(bool(texte))


# ── Farben ───────────────────────────────────────────────────────────────────

class Farbleiste(QWidget):
    """Wo liegen die Farben auf 0–255? Eine Leiste, je Eintrag ein Feld."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._eintraege: list[dict] = []
        self.setFixedHeight(46)

    def set_eintraege(self, eintraege) -> None:
        self._eintraege = list(eintraege or ())
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rand = 8.0
        b = self.width() - 2 * rand
        leiste = QRectF(rand, 4, b, 22)
        p.setPen(QPen(QColor("#2a3340"), 1))
        p.setBrush(QBrush(QColor("#0b0f14")))
        p.drawRoundedRect(leiste, 4, 4)
        for e in self._eintraege:
            try:
                von, bis = int(e["von"]), int(e["bis"])
            except (KeyError, TypeError, ValueError):
                continue
            if von > bis:
                continue
            x0 = rand + b * von / 256.0
            breite = max(3.0, b * (bis - von + 1) / 256.0)
            feld = QRectF(x0, 5, breite, 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_farb_pinsel(str(e.get("farbe", "")), feld))
            p.drawRect(feld)
        p.setPen(QPen(QColor("#7d8590")))
        schrift = p.font()
        schrift.setPixelSize(10)
        p.setFont(schrift)
        for wert in (0, 64, 128, 192, 255):
            x = rand + b * wert / 255.0
            p.drawText(QRectF(x - 20, 28, 40, 14),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                       str(wert))
        p.end()


class FarbSeite(_KanalSeite):
    SPALTEN = ["Farbfeld", "Von", "Bis", "Name", "Farbe"]
    C_FELD, C_VON, C_BIS, C_NAME, C_FARBE = range(5)
    _EIGENE = "eigene…"

    def __init__(self, mode, geaendert=None, parent=None):
        super().__init__(mode, geaendert, parent)
        self._kanal = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 8, 6, 4)
        kopf = QHBoxLayout()
        kopf.addWidget(QLabel("Farbkanal:"))
        self.cb_kanal = QComboBox()
        self.cb_kanal.setMinimumWidth(240)
        self.cb_kanal.setToolTip("Der Kanal, dessen DMX-Wert die Farbe wählt.")
        self.cb_kanal.currentIndexChanged.connect(self._kanal_gewechselt)
        kopf.addWidget(self.cb_kanal)
        kopf.addSpacing(12)
        info = QLabel("Welcher DMX-Bereich ergibt welche Farbe? Die Bedienung "
                      "macht daraus Farbfelder. Farbe ändert die Helligkeit nicht.")
        info.setStyleSheet("color:#9aa4af;")
        kopf.addWidget(info, 1)
        lay.addLayout(kopf)

        self.tbl = _tabelle(self.SPALTEN, self.C_NAME)
        _feste_breite(self.tbl, {self.C_FELD: 76, self.C_VON: 66, self.C_BIS: 66,
                                 self.C_FARBE: 180})
        self.tbl.itemChanged.connect(self._name_geaendert)
        lay.addWidget(self.tbl, 1)

        self.leiste = Farbleiste()
        lay.addWidget(self.leiste)

        knoepfe = QHBoxLayout()
        self.btn_neu = QPushButton("+ Farbe")
        self.btn_neu.clicked.connect(lambda: self.zeile_dazu())
        self.btn_weg = QPushButton("- Farbe")
        self.btn_weg.clicked.connect(lambda: self.zeile_weg())
        self.btn_aufteilen = QPushButton("Bereiche gleichmäßig aufteilen…")
        self.btn_aufteilen.clicked.connect(self._aufteilen_fragen)
        for b in (self.btn_neu, self.btn_weg, self.btn_aufteilen):
            b.setAutoDefault(False)
            knoepfe.addWidget(b)
        knoepfe.addStretch(1)
        lay.addLayout(knoepfe)
        self.lbl_hinweis = QLabel("")
        self.lbl_hinweis.setWordWrap(True)
        self.lbl_hinweis.setStyleSheet(_HINWEIS_STIL)
        lay.addWidget(self.lbl_hinweis)
        self.aktualisieren()

    def kanal(self):
        return self._kanal

    def eintraege(self) -> list[dict]:
        if self._kanal is None:
            return []
        return self._laser(self._kanal).setdefault("farben", [])

    def aktualisieren(self) -> None:
        self._combo_fuellen(self.cb_kanal, "farben", FARB_ATTRIBUTE, self._kanal)
        self._kanal_gewechselt()

    def _kanal_gewechselt(self, *_):
        kanaele = self._kanaele()
        i = self.cb_kanal.currentIndex()
        self._kanal = kanaele[i] if 0 <= i < len(kanaele) else None
        self._tabelle_fuellen()

    def kanal_waehlen(self, index: int) -> None:
        self.cb_kanal.setCurrentIndex(index)

    def _naechste_farbe(self, n: int) -> tuple[str, str]:
        kennungen = list(PA.FARBEN)
        if n < len(kennungen):
            return PA.FARBEN[kennungen[n]]
        return ("Bunt", PA.MEHRFARBIG) if n == len(kennungen) else PA.FARBEN["weiss"]

    def zeile_dazu(self, eintrag: dict | None = None) -> dict | None:
        if self._kanal is None:
            return None
        liste = self.eintraege()
        if eintrag is None:
            start = min(255, max((int(e.get("bis", -1)) for e in liste),
                                 default=-1) + 1)
            name, farbe = self._naechste_farbe(len(liste))
            eintrag = {"von": start, "bis": start, "name": name, "farbe": farbe}
        liste.append(eintrag)
        self._tabelle_fuellen(len(liste) - 1)
        self._melden()
        return eintrag

    def zeile_weg(self, zeile: int | None = None) -> None:
        liste = self.eintraege()
        zeile = self.tbl.currentRow() if zeile is None else zeile
        if 0 <= zeile < len(liste):
            del liste[zeile]
            self._tabelle_fuellen(min(zeile, len(liste) - 1))
            self._melden()

    def aufteilen(self, anzahl: int) -> None:
        if self._kanal is None:
            return
        liste = self.eintraege()
        teile = PA.gleichmaessig_aufteilen(anzahl)
        del liste[len(teile):]
        while len(liste) < len(teile):
            name, farbe = self._naechste_farbe(len(liste))
            liste.append({"name": name, "farbe": farbe})
        for e, (von, bis) in zip(liste, teile):
            e["von"], e["bis"] = von, bis
        self._tabelle_fuellen(0)
        self._melden()

    def _aufteilen_fragen(self):
        liste = self.eintraege()
        n, ok = QInputDialog.getInt(
            self, "Bereiche gleichmäßig aufteilen",
            "Wie viele Farben hat der Kanal (über 0–255)?",
            len(liste) or 8, 1, 256)
        if not ok:
            return
        if n < len(liste):
            antwort = QMessageBox.question(
                self, "Bereiche gleichmäßig aufteilen",
                f"Es stehen {len(liste)} Farben in der Liste. Bei {n} fallen "
                f"die letzten {len(liste) - n} weg. Fortfahren?")
            if antwort != QMessageBox.StandardButton.Yes:
                return
        self.aufteilen(n)

    def _tabelle_fuellen(self, zeile: int | None = None) -> None:
        liste = self.eintraege()
        if zeile is None:
            zeile = self.tbl.currentRow()
        self._baut = True
        self.tbl.blockSignals(True)
        self.tbl.setRowCount(len(liste))
        for i, e in enumerate(liste):
            feld = QLabel()
            feld.setPixmap(farb_pixmap(str(e.get("farbe", ""))))
            self.tbl.setCellWidget(i, self.C_FELD, _mitte(feld))
            for spalte, name in ((self.C_VON, "von"), (self.C_BIS, "bis")):
                sp = _spin(e.get(name, 0))
                sp.valueChanged.connect(
                    lambda v, z=i, f=name: self._setze(z, f, int(v)))
                self.tbl.setCellWidget(i, spalte, sp)
            self.tbl.setItem(i, self.C_NAME,
                             QTableWidgetItem(str(e.get("name", ""))))
            cb = QComboBox()
            for _k, (anzeige, wert) in PA.FARBEN.items():
                cb.addItem(anzeige, wert)
            cb.addItem("Mehrfarbig (bunt)", PA.MEHRFARBIG)
            farbe = str(e.get("farbe", "")).lower()
            if cb.findData(farbe) < 0 and farbe:
                cb.addItem(f"Eigene ({farbe})", farbe)
            cb.addItem("Eigene Farbe…", self._EIGENE)
            cb.setCurrentIndex(max(0, cb.findData(farbe)))
            cb.currentIndexChanged.connect(
                lambda _i, z=i, c=cb: self._farbe_gewaehlt(z, c))
            self.tbl.setCellWidget(i, self.C_FARBE, cb)
        self.tbl.blockSignals(False)
        self._baut = False
        self.btn_neu.setEnabled(self._kanal is not None)
        self.btn_aufteilen.setEnabled(self._kanal is not None)
        if liste:
            self.tbl.setCurrentCell(max(0, min(zeile, len(liste) - 1)), self.C_NAME)
        self.leiste.set_eintraege(liste)
        self._hinweise()

    def zellen_widget(self, zeile: int, spalte: int):
        w = self.tbl.cellWidget(zeile, spalte)
        if spalte == self.C_FELD and w is not None:
            return w.findChild(QLabel)
        return w

    def _eintrag(self, zeile: int) -> dict | None:
        liste = self.eintraege()
        return liste[zeile] if 0 <= zeile < len(liste) else None

    def _setze(self, zeile: int, feld: str, wert) -> None:
        e = self._eintrag(zeile)
        if e is None or self._baut:
            return
        e[feld] = wert
        self.leiste.set_eintraege(self.eintraege())
        self._hinweise()
        self._melden()

    def farbe_setzen(self, zeile: int, farbe: str) -> None:
        """Farbwert einer Zeile setzen. Traegt die Zeile noch den Namen der
        alten Farbe (oder keinen), zieht der Name mit."""
        e = self._eintrag(zeile)
        if e is None:
            return
        namen = {wert: anzeige for anzeige, wert in PA.FARBEN.values()}
        namen[PA.MEHRFARBIG] = "Bunt"
        alt = namen.get(str(e.get("farbe", "")).lower())
        if not str(e.get("name", "")).strip() or e.get("name") == alt:
            e["name"] = namen.get(farbe, e.get("name") or "Farbe")
        e["farbe"] = farbe
        self._tabelle_fuellen(zeile)
        self._melden()

    def _farbe_gewaehlt(self, zeile: int, cb: QComboBox) -> None:
        if self._baut:
            return
        wert = cb.currentData()
        if wert == self._EIGENE:
            e = self._eintrag(zeile) or {}
            start = QColor(str(e.get("farbe", "#ffffff")))
            c = QColorDialog.getColor(start if start.isValid() else QColor("#fff"),
                                      self, "Eigene Farbe")
            if not c.isValid():
                self._tabelle_fuellen(zeile)
                return
            wert = c.name()
        self.farbe_setzen(zeile, wert)

    def _name_geaendert(self, item: QTableWidgetItem) -> None:
        if self._baut or item.column() != self.C_NAME:
            return
        e = self._eintrag(item.row())
        if e is not None:
            e["name"] = item.text().strip()
            self._hinweise()
            self._melden()

    def hinweise(self) -> list[str]:
        liste = self.eintraege()
        out = PA.bereichs_hinweise(liste, "Farben")
        for e in liste:
            if not str(e.get("name", "")).strip():
                out.append(f"Farbe bei {e.get('von')}–{e.get('bis')}: ohne "
                           f"Namen wird der Eintrag nicht gespeichert.")
        return out

    def _hinweise(self) -> None:
        texte = self.hinweise()
        self.lbl_hinweis.setText("Hinweis: " + " ".join(texte) if texte else "")
        self.lbl_hinweis.setVisible(bool(texte))


# ── Richtungen und Betriebsart ───────────────────────────────────────────────

class RichtungSeite(_KanalSeite):
    SPALTEN = ["Kanal", "Enden des Reglers", "umgekehrt", "Mitte von",
               "Mitte bis", "Am Gerät"]
    C_KANAL, C_ENDEN, C_UMGEKEHRT, C_MVON, C_MBIS, C_TEXT = range(6)
    B_SPALTEN = ["Von", "Bis", "Bedeutung", "LightOS steuert"]
    BETRIEBSART_BREITE = 400

    def __init__(self, mode, geaendert=None, parent=None):
        super().__init__(mode, geaendert, parent)
        self._b_kanal = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 8, 6, 4)

        links = QVBoxLayout()
        info = QLabel("Je Kanal: Enden des Reglers, Laufrichtung und "
                      "Mittelbereich — die Bedienung dreht den Regler richtig "
                      "herum.")
        info.setToolTip(
            "„Läuft umgekehrt“: ein hoher DMX-Wert bedeutet klein / langsam / "
            "links / unten. „Mitte“: ein Wertebereich, der die Mittelstellung "
            "bedeutet (z. B. 0–10); „–“ = keiner.")
        info.setStyleSheet("color:#9aa4af;")
        links.addWidget(info)
        self.tbl = _tabelle(self.SPALTEN, self.C_KANAL)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tbl.setTextElideMode(Qt.TextElideMode.ElideRight)
        _feste_breite(self.tbl, {self.C_ENDEN: 136, self.C_UMGEKEHRT: 88,
                                 self.C_MVON: 74, self.C_MBIS: 74,
                                 self.C_TEXT: 172})
        self.tbl.horizontalHeaderItem(self.C_UMGEKEHRT).setToolTip(
            "Läuft umgekehrt: ein hoher DMX-Wert bedeutet klein / langsam / "
            "links / unten.")
        links.addWidget(self.tbl, 1)
        self.lbl_hinweis = QLabel("")
        self.lbl_hinweis.setWordWrap(True)
        self.lbl_hinweis.setStyleSheet(_HINWEIS_STIL)
        links.addWidget(self.lbl_hinweis)
        lay.addLayout(links, 1)

        box = QGroupBox("Betriebsart")
        bl = QVBoxLayout(box)
        zeile = QHBoxLayout()
        zeile.addWidget(QLabel("Kanal:"))
        self.cb_kanal = QComboBox()
        self.cb_kanal.currentIndexChanged.connect(self._b_kanal_gewechselt)
        zeile.addWidget(self.cb_kanal, 1)
        bl.addLayout(zeile)
        self.tbl_b = _tabelle(self.B_SPALTEN, 2)
        self.tbl_b.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        _feste_breite(self.tbl_b, {0: 66, 1: 66, 3: 112})
        bl.addWidget(self.tbl_b, 1)
        knoepfe = QHBoxLayout()
        self.btn_b_neu = QPushButton("+ Bereich")
        self.btn_b_neu.clicked.connect(lambda: self.betriebsart_dazu())
        self.btn_b_weg = QPushButton("- Bereich")
        self.btn_b_weg.clicked.connect(lambda: self.betriebsart_weg())
        self.btn_b_aus = QPushButton("Aus Wertebereichen übernehmen")
        self.btn_b_aus.setToolTip(
            "Übernimmt Von/Bis aus den Wertebereichen des Kanals und schlägt "
            "die Bedeutung aus deren Namen vor — bitte prüfen.")
        self.btn_b_aus.clicked.connect(lambda: self.betriebsart_aus_bereichen())
        for b in (self.btn_b_neu, self.btn_b_weg, self.btn_b_aus):
            b.setAutoDefault(False)
            knoepfe.addWidget(b)
        knoepfe.addStretch(1)
        bl.addLayout(knoepfe)
        self.tbl_b.horizontalHeaderItem(3).setToolTip(
            "Steuert LightOS in diesem Bereich Muster, Lage und Farbe? In "
            "Musik und Auto läuft das Gerät selbst — die Regler wirken dort "
            "nicht.")
        box.setFixedWidth(self.BETRIEBSART_BREITE)
        lay.addWidget(box)
        self.aktualisieren()

    # ── Richtungen ───────────────────────────────────────────────────────
    def aktualisieren(self) -> None:
        self._richtungen_fuellen()
        self._combo_fuellen(self.cb_kanal, "betriebsart", BETRIEBSART_ATTRIBUTE,
                            self._b_kanal)
        self._b_kanal_gewechselt()

    @staticmethod
    def _paar_von(richtung: dict) -> int:
        """Index des Enden-Paars (0 = keine Angabe)."""
        tief, hoch = richtung.get("ende_niedrig"), richtung.get("ende_hoch")
        for i, (a, b) in enumerate(PA.ENDEN_PAARE, 1):
            if {tief, hoch} == {a, b}:
                return i
        return 0

    def _richtungen_fuellen(self) -> None:
        kanaele = self._kanaele()
        self._baut = True
        self.tbl.setRowCount(len(kanaele))
        for i, ch in enumerate(kanaele):
            r = self._laser(ch).get("richtung") or {}
            it = QTableWidgetItem(f"{i + 1}: {ch.name}")
            it.setToolTip(f"{ch.name} ({ch.attribute or 'raw'})")
            self.tbl.setItem(i, self.C_KANAL, it)
            cb = QComboBox()
            cb.addItem("– keine Angabe –", 0)
            for n, (a, b) in enumerate(PA.ENDEN_PAARE, 1):
                cb.addItem(f"{PA.ENDEN[a]} … {PA.ENDEN[b]}", n)
            cb.setCurrentIndex(self._paar_von(r))
            cb.currentIndexChanged.connect(lambda _i, z=i: self._richtung_lesen(z))
            self.tbl.setCellWidget(i, self.C_ENDEN, cb)
            chk = QCheckBox()
            umgekehrt = r.get("umgekehrt")
            if umgekehrt is None:
                umgekehrt = bool(PA.umgekehrt_aus_enden(
                    r.get("ende_niedrig", ""), r.get("ende_hoch", "")))
            chk.setChecked(bool(umgekehrt))
            chk.toggled.connect(lambda _v, z=i: self._richtung_lesen(z))
            self.tbl.setCellWidget(i, self.C_UMGEKEHRT, _mitte(chk))
            m = r.get("mitte") or {}
            for spalte, feld in ((self.C_MVON, "von"), (self.C_MBIS, "bis")):
                sp = _spin(m.get(feld, -1), -1, 255)
                sp.setSpecialValueText("–")
                sp.setToolTip("„–“ = kein Mittelbereich.")
                sp.valueChanged.connect(lambda _v, z=i: self._richtung_lesen(z))
                self.tbl.setCellWidget(i, spalte, sp)
            self.tbl.setItem(i, self.C_TEXT, QTableWidgetItem(self._text(r)))
        self._baut = False
        self._richtung_hinweise()

    @staticmethod
    def _text(r: dict) -> str:
        teile = []
        if r.get("ende_niedrig") and r.get("ende_hoch"):
            teile.append(f"niedrig = {PA.ENDEN[r['ende_niedrig']]} · "
                         f"hoch = {PA.ENDEN[r['ende_hoch']]}")
        elif r.get("umgekehrt"):
            teile.append("läuft umgekehrt")
        return " · ".join(teile)

    def richtung_widgets(self, zeile: int):
        """``(enden_combo, umgekehrt_haken, mitte_von, mitte_bis)`` einer Zeile."""
        haken = self.tbl.cellWidget(zeile, self.C_UMGEKEHRT)
        return (self.tbl.cellWidget(zeile, self.C_ENDEN),
                haken.findChild(QCheckBox) if haken is not None else None,
                self.tbl.cellWidget(zeile, self.C_MVON),
                self.tbl.cellWidget(zeile, self.C_MBIS))

    def _richtung_lesen(self, zeile: int) -> None:
        """Zeile -> ``kanal.laser["richtung"]`` (leer = Schluessel entfernt)."""
        if self._baut:
            return
        kanaele = self._kanaele()
        if not (0 <= zeile < len(kanaele)):
            return
        cb, chk, sp_von, sp_bis = self.richtung_widgets(zeile)
        r: dict = {}
        paar = int(cb.currentData() or 0)
        umgekehrt = chk.isChecked()
        if umgekehrt or paar:
            r["umgekehrt"] = umgekehrt
        if paar:
            a, b = PA.ENDEN_PAARE[paar - 1]
            r["ende_niedrig"], r["ende_hoch"] = (b, a) if umgekehrt else (a, b)
        von, bis = sp_von.value(), sp_bis.value()
        if von >= 0 and bis >= 0 and von <= bis:
            r["mitte"] = {"von": von, "bis": bis}
        laser = self._laser(kanaele[zeile])
        if r:
            laser["richtung"] = r
        else:
            laser.pop("richtung", None)
        self.tbl.item(zeile, self.C_TEXT).setText(self._text(r))
        self._richtung_hinweise()
        self._melden()

    def _richtung_hinweise(self) -> None:
        texte = []
        for i in range(self.tbl.rowCount()):
            _cb, _chk, sp_von, sp_bis = self.richtung_widgets(i)
            if sp_von is None or sp_bis is None:
                continue
            von, bis = sp_von.value(), sp_bis.value()
            if (von >= 0) != (bis >= 0) or (von >= 0 and von > bis):
                texte.append(f"Kanal {i + 1}: Mitte braucht „von“ und „bis“ "
                             f"(von ≤ bis) — so wird sie nicht gespeichert.")
        self.lbl_hinweis.setText("Hinweis: " + " ".join(texte) if texte else "")
        self.lbl_hinweis.setVisible(bool(texte))

    # ── Betriebsart ──────────────────────────────────────────────────────
    def betriebsart_kanal(self):
        return self._b_kanal

    def betriebsart(self) -> list[dict]:
        if self._b_kanal is None:
            return []
        return self._laser(self._b_kanal).setdefault("betriebsart", [])

    def _b_kanal_gewechselt(self, *_):
        kanaele = self._kanaele()
        i = self.cb_kanal.currentIndex()
        self._b_kanal = kanaele[i] if 0 <= i < len(kanaele) else None
        self._b_fuellen()

    def betriebsart_kanal_waehlen(self, index: int) -> None:
        self.cb_kanal.setCurrentIndex(index)

    def betriebsart_dazu(self, eintrag: dict | None = None) -> dict | None:
        if self._b_kanal is None:
            return None
        liste = self.betriebsart()
        if eintrag is None:
            start = min(255, max((int(e.get("bis", -1)) for e in liste),
                                 default=-1) + 1)
            eintrag = {"von": start, "bis": 255, "art": "statisch", "steuert": True}
        liste.append(eintrag)
        self._b_fuellen()
        self._melden()
        return eintrag

    def betriebsart_weg(self, zeile: int | None = None) -> None:
        liste = self.betriebsart()
        zeile = self.tbl_b.currentRow() if zeile is None else zeile
        if 0 <= zeile < len(liste):
            del liste[zeile]
            self._b_fuellen()
            self._melden()

    def betriebsart_aus_bereichen(self) -> int:
        """Die Wertebereiche des Kanals als Betriebsart-Liste vorschlagen.
        Liefert die Zahl der uebernommenen Bereiche."""
        if self._b_kanal is None:
            return 0
        vorschlag = PA.betriebsart_aus_bereichen(
            [(r.range_from, r.range_to, r.name, r.kind)
             for r in getattr(self._b_kanal, "ranges", ())])
        if vorschlag:
            self._laser(self._b_kanal)["betriebsart"] = vorschlag
            self._b_fuellen()
            self._melden()
        return len(vorschlag)

    def _b_fuellen(self) -> None:
        liste = self.betriebsart()
        self._baut = True
        self.tbl_b.setRowCount(len(liste))
        for i, e in enumerate(liste):
            for spalte, feld in ((0, "von"), (1, "bis")):
                sp = _spin(e.get(feld, 0))
                sp.valueChanged.connect(
                    lambda v, z=i, f=feld: self._b_setze(z, f, int(v)))
                self.tbl_b.setCellWidget(i, spalte, sp)
            cb = QComboBox()
            for kennung, anzeige in PA.BETRIEBSARTEN.items():
                cb.addItem(anzeige, kennung)
            cb.setCurrentIndex(max(0, cb.findData(e.get("art", "aus"))))
            cb.currentIndexChanged.connect(
                lambda _i, z=i, c=cb: self._b_setze(z, "art", c.currentData()))
            self.tbl_b.setCellWidget(i, 2, cb)
            chk = QCheckBox()
            chk.setChecked(bool(e.get("steuert", False)))
            chk.setToolTip("LightOS steuert in diesem Bereich Muster und Lage.")
            chk.toggled.connect(lambda v, z=i: self._b_setze(z, "steuert", bool(v)))
            self.tbl_b.setCellWidget(i, 3, _mitte(chk))
        self._baut = False
        aktiv = self._b_kanal is not None
        self.btn_b_neu.setEnabled(aktiv)
        self.btn_b_aus.setEnabled(
            aktiv and bool(getattr(self._b_kanal, "ranges", ())))

    def betriebsart_widgets(self, zeile: int):
        """``(von, bis, art_combo, steuert_haken)`` einer Zeile."""
        haken = self.tbl_b.cellWidget(zeile, 3)
        return (self.tbl_b.cellWidget(zeile, 0), self.tbl_b.cellWidget(zeile, 1),
                self.tbl_b.cellWidget(zeile, 2),
                haken.findChild(QCheckBox) if haken is not None else None)

    def _b_setze(self, zeile: int, feld: str, wert) -> None:
        liste = self.betriebsart()
        if self._baut or not (0 <= zeile < len(liste)):
            return
        liste[zeile][feld] = wert
        self._melden()

    def sizeHint(self) -> QSize:
        return QSize(900, 300)
