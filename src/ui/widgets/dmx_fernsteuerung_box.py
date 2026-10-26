"""NET-15: Zuordnungstabelle „Fernsteuerung" im Ausgabe-Dialog (Reiter DMX-Eingang).

Eigene Datei, damit ``output_config.py`` nur um zwei Zeilen waechst. Logik,
Datenformat und Thread-Uebergabe stehen in :mod:`src.core.dmx.fernsteuerung`.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QPushButton, QSpinBox, QTableWidget, QVBoxLayout,
)

from src.core.dmx import fernsteuerung as fs_mod
from src.core.dmx.fernsteuerung import (
    QUELLE_ARTNET, QUELLE_SACN, ZIEL_BACK, ZIEL_FADER, ZIEL_GM, ZIEL_GO,
    ZIEL_STOP, TASTEN_ZIELE, Konfig, Zuordnung,
)
from src.ui.widgets.tabellen_spalten import combo_breite, spalte_fest

QUELLEN_TEXT = [(QUELLE_ARTNET, "Art-Net"), (QUELLE_SACN, "sACN")]
ZIELE_TEXT = [
    (ZIEL_FADER, "Executor-Fader"),
    (ZIEL_GM, "Grand Master"),
    (ZIEL_GO, "GO (Weiter)"),
    (ZIEL_BACK, "Zurück"),
    (ZIEL_STOP, "Stop"),
]
SPALTEN = ["Quelle", "Universum", "Kanal", "Ziel", "Executor", "Schwelle %"]
SP_QUELLE, SP_UNIV, SP_KANAL, SP_ZIEL, SP_EXEC, SP_SCHWELLE = range(6)


class FernsteuerungBox(QGroupBox):
    """Tabelle eingehendes Universum + Kanal -> Ziel, mit Übernehmen."""

    def __init__(self, parent=None, pfad: str | None = None):
        super().__init__("Fernsteuerung (Pult steuert LightOS)", parent)
        self._pfad = pfad   # None = App-Datenordner (Tests geben einen Pfad)
        lay = QVBoxLayout(self)
        hinweis = QLabel(
            "Eingehende Kanäle bedienen Executor-Fader, Grand Master und "
            "GO / Zurück / Stop. Fader wirken erst, wenn sich der Kanal bewegt; "
            "GO löst beim Überschreiten der Schwelle genau einmal aus. "
            "Zugeordnete Kanäle werden nicht in die Ausgabe gemischt.")
        hinweis.setWordWrap(True)
        lay.addWidget(hinweis)

        self.check_aktiv = QCheckBox("Fernsteuerung aktiv")
        lay.addWidget(self.check_aktiv)

        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        kopf = self.tabelle.horizontalHeader()
        kopf.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # „GO (Weiter)" / „Executor-Fader" sollen lesbar bleiben, auch schmal.
        # ResizeToContents misst nur Kopftext und Items, nicht die per
        # setCellWidget gesetzten Auswahlfelder (Windows-Gegenprobe D: „Art-N",
        # „E:", „G"). Deshalb feste Breite aus dem sizeHint der Combo mit
        # allen Eintraegen; wird es zu eng, schrumpfen nur die Zahlenspalten,
        # danach rollt die Tabelle waagerecht statt abzuschneiden.
        for sp in (SP_QUELLE, SP_ZIEL):
            kopf.setSectionResizeMode(sp, QHeaderView.ResizeMode.Fixed)
        self.tabelle.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tabelle.setMinimumHeight(130)
        self._spalten_anpassen()
        lay.addWidget(self.tabelle)

        knoepfe = QHBoxLayout()
        self.btn_neu = QPushButton("+ Zuordnung")
        self.btn_neu.clicked.connect(lambda: self.zeile_hinzu(Zuordnung()))
        self.btn_weg = QPushButton("Entfernen")
        self.btn_weg.clicked.connect(self._zeile_entfernen)
        self.btn_uebernehmen = QPushButton("Übernehmen")
        self.btn_uebernehmen.clicked.connect(self.uebernehmen)
        knoepfe.addWidget(self.btn_neu)
        knoepfe.addWidget(self.btn_weg)
        knoepfe.addStretch(1)
        knoepfe.addWidget(self.btn_uebernehmen)
        lay.addLayout(knoepfe)
        self.lbl_status = QLabel("Inaktiv")
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)

        self.laden()

    # ── Tabelle ───────────────────────────────────────────────────────────

    def _combo_breite(self, texte) -> int:
        """sizeHint-Breite einer Combo mit diesen Eintraegen (gemeinsame Hilfe
        ``tabellen_spalten.combo_breite``, seit OSC-07 auch im OSC-Dialog)."""
        return combo_breite(self.tabelle, texte)

    def _spalten_anpassen(self):
        """Quelle/Ziel so breit wie Kopf und laengster Eintrag (mit Pfeil)."""
        for sp, texte in ((SP_QUELLE, QUELLEN_TEXT), (SP_ZIEL, ZIELE_TEXT)):
            spalte_fest(self.tabelle, sp, self._combo_breite(texte))

    def changeEvent(self, ev):
        super().changeEvent(ev)
        if (ev.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange)
                and getattr(self, "tabelle", None) is not None):
            self._spalten_anpassen()

    def zeile_hinzu(self, z: Zuordnung) -> int:
        r = self.tabelle.rowCount()
        self.tabelle.insertRow(r)
        quelle = QComboBox()
        for key, text in QUELLEN_TEXT:
            quelle.addItem(text, key)
        quelle.setCurrentIndex(max(0, quelle.findData(z.quelle)))
        univ = QSpinBox()
        univ.setRange(1, 63999)
        univ.setValue(int(z.universum))
        kanal = QSpinBox()
        kanal.setRange(1, 512)
        kanal.setValue(int(z.kanal))
        ziel = QComboBox()
        for key, text in ZIELE_TEXT:
            ziel.addItem(text, key)
        ziel.setCurrentIndex(max(0, ziel.findData(z.ziel)))
        exe = QSpinBox()
        exe.setRange(1, fs_mod.EXECUTOR_MAX)
        exe.setValue(int(z.executor))
        schwelle = QSpinBox()
        schwelle.setRange(1, 100)
        schwelle.setValue(int(z.schwelle))
        # Hysterese hat keine eigene Spalte; der gespeicherte Wert reist mit.
        schwelle.setProperty("hysterese", int(z.hysterese))
        for sp, w in ((SP_QUELLE, quelle), (SP_UNIV, univ), (SP_KANAL, kanal),
                      (SP_ZIEL, ziel), (SP_EXEC, exe), (SP_SCHWELLE, schwelle)):
            self.tabelle.setCellWidget(r, sp, w)
        ziel.currentIndexChanged.connect(lambda _i, w=ziel: self._ziel_geaendert(w))
        self._felder_schalten(r)
        self._spalten_anpassen()
        return r

    def _ziel_geaendert(self, combo):
        for r in range(self.tabelle.rowCount()):
            if self.tabelle.cellWidget(r, SP_ZIEL) is combo:
                self._felder_schalten(r)
                return

    def _felder_schalten(self, r: int):
        ziel = self.tabelle.cellWidget(r, SP_ZIEL).currentData()
        self.tabelle.cellWidget(r, SP_EXEC).setEnabled(ziel != ZIEL_GM)
        self.tabelle.cellWidget(r, SP_SCHWELLE).setEnabled(ziel in TASTEN_ZIELE)

    def _zeile_entfernen(self):
        r = self.tabelle.currentRow()
        if r < 0:
            r = self.tabelle.rowCount() - 1
        if r >= 0:
            self.tabelle.removeRow(r)

    # ── Konfig <-> Tabelle ────────────────────────────────────────────────

    def konfig(self) -> Konfig:
        zs = []
        for r in range(self.tabelle.rowCount()):
            w = self.tabelle.cellWidget
            schwelle = w(r, SP_SCHWELLE)
            hyst = schwelle.property("hysterese")
            z = Zuordnung.aus_dict({
                "quelle": w(r, SP_QUELLE).currentData(),
                "universum": w(r, SP_UNIV).value(),
                "kanal": w(r, SP_KANAL).value(),
                "ziel": w(r, SP_ZIEL).currentData(),
                "executor": w(r, SP_EXEC).value(),
                "schwelle": schwelle.value(),
                "hysterese": fs_mod.HYSTERESE_STANDARD if hyst is None else hyst,
            })
            if z is not None:
                zs.append(z)
        # OUT-79: die Empfangsadresse steht in derselben Datei, wird aber im
        # Kopf des Reiters gewaehlt — beim Speichern mitnehmen, nicht verlieren.
        adresse = fs_mod.lade_konfig(self._pfad).empfangsadresse
        return Konfig(aktiv=self.check_aktiv.isChecked(), zuordnungen=zs,
                      empfangsadresse=adresse)

    def laden(self):
        konfig = fs_mod.lade_konfig(self._pfad)
        self.tabelle.setRowCount(0)
        for z in konfig.zuordnungen:
            self.zeile_hinzu(z)
        self.check_aktiv.setChecked(konfig.aktiv)
        if konfig.zuordnungen:
            self.lbl_status.setText(
                ("Aktiv" if konfig.aktiv else "Aus")
                + f" · {len(konfig.zuordnungen)} Zuordnung(en) gespeichert")

    def uebernehmen(self) -> bool:
        konfig = self.konfig()
        fs = fs_mod.get_fernsteuerung()
        fs.konfigurieren(konfig)
        try:
            fs_mod.installiere_qt_wecker()
        except Exception as e:
            print(f"[fernsteuerung] Qt-Bruecke: {e}")
        gespeichert = fs_mod.speichere_konfig(konfig, self._pfad)
        teil = "(gespeichert)" if gespeichert else "(NICHT gespeichert!)"
        if not konfig.aktiv or not konfig.zuordnungen:
            self.lbl_status.setText(f"Aus {teil}")
            return gespeichert
        try:
            quellen = fs.empfaenger_starten()
        except Exception as e:
            self.lbl_status.setText(f"Fehler beim Empfang: {e}")
            return False
        namen = dict(QUELLEN_TEXT)
        self.lbl_status.setText(
            f"Aktiv · {len(konfig.zuordnungen)} Zuordnung(en) · Empfang: "
            + ", ".join(namen.get(q, q) for q in quellen) + f" {teil}")
        return gespeichert
