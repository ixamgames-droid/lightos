"""OSC-06: Dialog „OSC-Zuordnungen & Rückmeldung“ (Menü Ausgabe).

Zwei Reiter: freie Eingangs-Zuordnungen mit OSC-Learn und die Rückmeldung
an ein Ziel (IP:Port). Logik, Datenformat und Thread-Übergabe stehen in
:mod:`src.core.osc.osc_zuordnung`.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QPushButton, QSpinBox, QTableWidget,
    QTabWidget, QVBoxLayout, QWidget,
)

from src.core.osc import osc_zuordnung as oz
from src.core.osc.osc_zuordnung import (
    BEREICH_1, BEREICH_100, BEREICH_255, EXECUTOR_MAX, Konfig, RueckmeldeKonfig,
    Zuordnung,
)

ZIELE_TEXT = [
    (oz.ZIEL_FADER, "Executor-Fader"),
    (oz.ZIEL_GO, "GO Executor"),
    (oz.ZIEL_BACK, "Zurück Executor"),
    (oz.ZIEL_STOP, "Stop Executor"),
    (oz.ZIEL_GM, "Grand Master"),
    (oz.ZIEL_BLACKOUT, "Blackout"),
    (oz.ZIEL_FKT_START, "Funktion starten"),
    (oz.ZIEL_FKT_STOP, "Funktion stoppen"),
    (oz.ZIEL_FKT_UMSCHALTEN, "Funktion umschalten"),
    (oz.ZIEL_TAP, "Tap-Tempo"),
]
BEREICHE_TEXT = [(BEREICH_1, "0–1"), (BEREICH_100, "0–100"), (BEREICH_255, "0–255")]
SPALTEN = ["Adresse", "Ziel", "Nummer", "Versatz", "Nr. aus Arg.", "Funktion", "Bereich"]
SP_ADR, SP_ZIEL, SP_NR, SP_VERSATZ, SP_ARG, SP_FKT, SP_BEREICH = range(7)

RM_TEXT = [
    (oz.RM_FADER, "Fader ({n}):"),
    (oz.RM_AKTIV, "Aktiv ({n}):"),
    (oz.RM_CUE, "Cue-Nr. ({n}):"),
    (oz.RM_GM, "Grand Master:"),
    (oz.RM_BLACKOUT, "Blackout:"),
]


def _versatz_vorschlag(n: int | None) -> int:
    """Learn: grandMA3-artige Nummern (201, 105 …) auf Executor 1.. abbilden."""
    if n is None or n <= EXECUTOR_MAX:
        return 0
    rest = n % 100
    if 1 <= rest <= EXECUTOR_MAX:
        return -(n - rest)
    return 0


class OscEinstellungenDialog(QDialog):
    #: aus dem OSC-Thread gefeuert (Queued), Slot läuft im GUI-Thread
    gelernt = Signal(str, object, object)

    def __init__(self, parent=None, pfad: str | None = None,
                 server_laeuft: bool | None = None):
        super().__init__(parent)
        self.setWindowTitle("OSC-Zuordnungen & Rückmeldung")
        self._pfad = pfad
        self._server_laeuft = server_laeuft
        self.gelernt.connect(self._gelernt, Qt.ConnectionType.QueuedConnection)
        self._lern_zeile = -1

        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)
        self.tabs.addTab(self._baue_eingang(), "Eingang")
        self.tabs.addTab(self._baue_rueckmeldung(), "Rückmeldung")

        unten = QHBoxLayout()
        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        unten.addWidget(self.lbl_status, 1)
        self.btn_uebernehmen = QPushButton("Übernehmen")
        self.btn_uebernehmen.clicked.connect(self.uebernehmen)
        btn_zu = QPushButton("Schließen")
        btn_zu.clicked.connect(self.reject)
        unten.addWidget(self.btn_uebernehmen)
        unten.addWidget(btn_zu)
        lay.addLayout(unten)
        self.resize(940, 520)
        self.laden()

    # ── Reiter Eingang ────────────────────────────────────────────────────

    def _baue_eingang(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        hinweis = QLabel(
            "Beliebige OSC-Adressen → LightOS. Muster: * ? [..] {a,b}; "
            "{n} liefert die Zielnummer (Zielnummer = n + Versatz). "
            "Die festen /lightos/…-Adressen gelten weiter.")
        hinweis.setWordWrap(True)
        lay.addWidget(hinweis)
        self.check_aktiv = QCheckBox("Zuordnungen aktiv")
        lay.addWidget(self.check_aktiv)

        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        kopf = self.tabelle.horizontalHeader()
        kopf.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        kopf.setSectionResizeMode(SP_ADR, QHeaderView.ResizeMode.Stretch)
        self.tabelle.setMinimumHeight(180)
        lay.addWidget(self.tabelle, 1)

        knoepfe = QHBoxLayout()
        self.btn_neu = QPushButton("+ Zuordnung")
        self.btn_neu.clicked.connect(lambda: self.zeile_hinzu(Zuordnung()))
        self.btn_weg = QPushButton("Entfernen")
        self.btn_weg.clicked.connect(self._zeile_entfernen)
        self.btn_lernen = QPushButton("Lernen")
        self.btn_lernen.setCheckable(True)
        self.btn_lernen.setToolTip(
            "Nächste eingehende OSC-Adresse in die gewählte Zeile übernehmen "
            "(ohne Auswahl: neue Zeile). Die letzte Zahl wird zu {n}.")
        self.btn_lernen.toggled.connect(self._lernen_umschalten)
        knoepfe.addWidget(self.btn_neu)
        knoepfe.addWidget(self.btn_weg)
        knoepfe.addWidget(self.btn_lernen)
        knoepfe.addStretch(1)
        lay.addLayout(knoepfe)
        return w

    def zeile_hinzu(self, z: Zuordnung) -> int:
        r = self.tabelle.rowCount()
        self.tabelle.insertRow(r)
        adr = QLineEdit(z.adresse)
        adr.setPlaceholderText("/Page1/Fader{n}")
        ziel = QComboBox()
        for key, text in ZIELE_TEXT:
            ziel.addItem(text, key)
        ziel.setCurrentIndex(max(0, ziel.findData(z.ziel)))
        nr = QSpinBox()
        nr.setRange(1, 9999)
        nr.setValue(int(z.nummer))
        versatz = QSpinBox()
        versatz.setRange(-9999, 9999)
        versatz.setValue(int(z.versatz))
        arg = QCheckBox()
        arg.setChecked(bool(z.nummer_aus_argument))
        arg.setToolTip("Erstes Argument = Zielnummer, zweites = Wert")
        fkt = QLineEdit(z.funktion)
        fkt.setPlaceholderText("Name oder Id")
        bereich = QComboBox()
        for key, text in BEREICHE_TEXT:
            bereich.addItem(text, key)
        bereich.setCurrentIndex(max(0, bereich.findData(z.bereich)))
        for sp, w in ((SP_ADR, adr), (SP_ZIEL, ziel), (SP_NR, nr),
                      (SP_VERSATZ, versatz), (SP_ARG, arg), (SP_FKT, fkt),
                      (SP_BEREICH, bereich)):
            self.tabelle.setCellWidget(r, sp, w)
        ziel.currentIndexChanged.connect(lambda _i, w=ziel: self._ziel_geaendert(w))
        self._felder_schalten(r)
        return r

    def _zeile_von(self, widget, spalte) -> int:
        for r in range(self.tabelle.rowCount()):
            if self.tabelle.cellWidget(r, spalte) is widget:
                return r
        return -1

    def _ziel_geaendert(self, combo):
        r = self._zeile_von(combo, SP_ZIEL)
        if r >= 0:
            self._felder_schalten(r)

    def _felder_schalten(self, r: int):
        ziel = self.tabelle.cellWidget(r, SP_ZIEL).currentData()
        self.tabelle.cellWidget(r, SP_FKT).setEnabled(ziel in oz.FUNKTIONS_ZIELE)
        ohne_nr = ziel in (oz.ZIEL_GM, oz.ZIEL_BLACKOUT, oz.ZIEL_TAP)
        for sp in (SP_NR, SP_VERSATZ, SP_ARG):
            self.tabelle.cellWidget(r, sp).setEnabled(not ohne_nr)

    def _zeile_entfernen(self):
        r = self.tabelle.currentRow()
        if r < 0:
            r = self.tabelle.rowCount() - 1
        if r >= 0:
            self.tabelle.removeRow(r)

    # ── OSC-Learn ─────────────────────────────────────────────────────────

    def _lernen_umschalten(self, an: bool):
        zu = oz.get_osc_zuordnung()
        if not an:
            zu.lerne(None)
            self.btn_lernen.setText("Lernen")
            return
        self._lern_zeile = self.tabelle.currentRow()
        zu.lerne(self.gelernt.emit)
        self.btn_lernen.setText("Warte … (abbrechen)")
        laeuft = self._server_laeuft
        if laeuft is None:
            try:
                from src.core.osc.osc_server import get_osc_server
                laeuft = get_osc_server().is_running()
            except Exception:
                laeuft = False
        if laeuft:
            self.lbl_status.setText("Warte auf die nächste OSC-Nachricht …")
        else:
            self.lbl_status.setText(
                "Warte auf die nächste OSC-Nachricht — der OSC-Server ist aus: "
                "Menü Ausgabe → OSC-Server einschalten.")

    def _gelernt(self, adresse: str, args, absender):
        muster, n = oz.vorschlag_muster(adresse)
        r = self._lern_zeile
        if not (0 <= r < self.tabelle.rowCount()):
            r = self.zeile_hinzu(Zuordnung(adresse=muster))
        w = self.tabelle.cellWidget
        w(r, SP_ADR).setText(muster)
        ziel = oz.vorschlag_ziel(adresse, tuple(args or ()))
        combo = w(r, SP_ZIEL)
        combo.setCurrentIndex(max(0, combo.findData(ziel)))
        if n is not None:
            w(r, SP_VERSATZ).setValue(_versatz_vorschlag(n))
        if args and not isinstance(args[0], bool) and isinstance(args[0], (int, float)):
            wert = float(args[0])
            bereich = BEREICH_1 if wert <= 1.0 else (
                BEREICH_100 if wert <= 100.0 else BEREICH_255)
            b = w(r, SP_BEREICH)
            b.setCurrentIndex(max(0, b.findData(bereich)))
        self.tabelle.selectRow(r)
        self.btn_lernen.blockSignals(True)
        self.btn_lernen.setChecked(False)
        self.btn_lernen.setText("Lernen")
        self.btn_lernen.blockSignals(False)
        teil = f" (n = {n})" if n is not None else ""
        von = f" von {absender}" if absender else ""
        self.lbl_status.setText(f"Gelernt: {adresse}{teil}{von} — prüfen, dann Übernehmen.")

    def done(self, ergebnis):
        # Ein offenes Lernen darf das geschlossene Fenster nicht mehr erreichen.
        if self.btn_lernen.isChecked():
            oz.get_osc_zuordnung().lerne(None)
        super().done(ergebnis)

    # ── Reiter Rückmeldung ────────────────────────────────────────────────

    def _baue_rueckmeldung(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        hinweis = QLabel(
            "Sendet Zustände an ein OSC-Ziel — nur bei Änderung, höchstens so oft "
            "wie unter „Rate“ eingestellt. Leere Adresse = nicht senden.")
        hinweis.setWordWrap(True)
        lay.addWidget(hinweis)
        self.check_rm = QCheckBox("Rückmeldung senden")
        lay.addWidget(self.check_rm)
        form = QFormLayout()
        ziel = QHBoxLayout()
        self.edit_ip = QLineEdit()
        self.edit_ip.setPlaceholderText("192.0.2.20")
        self.spin_port = QSpinBox()
        self.spin_port.setRange(1, 65535)
        ziel.addWidget(self.edit_ip, 1)
        ziel.addWidget(QLabel("Port:"))
        ziel.addWidget(self.spin_port)
        form.addRow("Ziel-IP:", ziel)
        self.combo_vorlage = QComboBox()
        for name, v in oz.VORLAGEN.items():
            self.combo_vorlage.addItem(v.titel + ("" if v.geprueft else " — ungeprüft"), name)
        self.combo_vorlage.activated.connect(self._vorlage_gewaehlt)
        form.addRow("Vorlage:", self.combo_vorlage)
        self.lbl_vorlage = QLabel("")
        self.lbl_vorlage.setWordWrap(True)
        form.addRow("", self.lbl_vorlage)
        zeile = QHBoxLayout()
        self.edit_exec = QLineEdit()
        self.edit_exec.setPlaceholderText("1-10")
        self.spin_rm_versatz = QSpinBox()
        self.spin_rm_versatz.setRange(-9999, 9999)
        self.spin_rm_versatz.setToolTip("Gesendete Nummer = Executor + Versatz")
        self.combo_rm_bereich = QComboBox()
        for key, text in BEREICHE_TEXT:
            self.combo_rm_bereich.addItem(text, key)
        self.spin_rate = QSpinBox()
        self.spin_rate.setRange(1, oz.RATE_MAX)
        self.spin_rate.setSuffix(" /s")
        for text, feld in (("Versatz:", self.spin_rm_versatz),
                           ("Bereich:", self.combo_rm_bereich),
                           ("Rate:", self.spin_rate)):
            zeile.addWidget(QLabel(text))
            zeile.addWidget(feld)
        zeile.insertWidget(0, self.edit_exec, 1)
        form.addRow("Executoren:", zeile)
        self.edit_rm: dict[str, QLineEdit] = {}
        for art, text in RM_TEXT:
            e = QLineEdit()
            self.edit_rm[art] = e
            form.addRow(text, e)
        lay.addLayout(form)
        knopf = QHBoxLayout()
        self.btn_neu_senden = QPushButton("Alles neu senden")
        self.btn_neu_senden.clicked.connect(lambda: oz.get_osc_rueckmeldung().alles_neu())
        knopf.addStretch(1)
        knopf.addWidget(self.btn_neu_senden)
        lay.addLayout(knopf)
        lay.addStretch(1)
        return w

    def _vorlage_gewaehlt(self, _i=None):
        rm = self._rm_aus_feldern()
        rm.vorlage_anwenden(self.combo_vorlage.currentData())
        self._rm_in_felder(rm)

    def _rm_in_felder(self, rm: RueckmeldeKonfig):
        self.check_rm.setChecked(rm.aktiv)
        self.edit_ip.setText(rm.ziel_ip)
        self.spin_port.setValue(int(rm.ziel_port))
        self.combo_vorlage.setCurrentIndex(max(0, self.combo_vorlage.findData(rm.vorlage)))
        v = oz.VORLAGEN.get(rm.vorlage)
        self.lbl_vorlage.setText(v.hinweis if v else "")
        self.edit_exec.setText(rm.executoren)
        self.spin_rm_versatz.setValue(int(rm.versatz))
        self.combo_rm_bereich.setCurrentIndex(
            max(0, self.combo_rm_bereich.findData(rm.bereich)))
        self.spin_rate.setValue(int(rm.rate_hz))
        for art, e in self.edit_rm.items():
            e.setText(rm.adressen.get(art, ""))

    def _rm_aus_feldern(self) -> RueckmeldeKonfig:
        return RueckmeldeKonfig.aus_dict({
            "aktiv": self.check_rm.isChecked(),
            "ziel_ip": self.edit_ip.text(),
            "ziel_port": self.spin_port.value(),
            "vorlage": self.combo_vorlage.currentData(),
            "executoren": self.edit_exec.text(),
            "versatz": self.spin_rm_versatz.value(),
            "bereich": self.combo_rm_bereich.currentData(),
            "rate_hz": self.spin_rate.value(),
            "adressen": {art: e.text() for art, e in self.edit_rm.items()},
        })

    # ── Konfig <-> Dialog ─────────────────────────────────────────────────

    def konfig(self) -> tuple[Konfig, int]:
        """(Konfig, Zahl verworfener Zeilen mit ungültigem Muster)."""
        zs = []
        kaputt = 0
        w = self.tabelle.cellWidget
        for r in range(self.tabelle.rowCount()):
            z = Zuordnung.aus_dict({
                "adresse": w(r, SP_ADR).text(),
                "ziel": w(r, SP_ZIEL).currentData(),
                "nummer": w(r, SP_NR).value(),
                "versatz": w(r, SP_VERSATZ).value(),
                "nummer_aus_argument": w(r, SP_ARG).isChecked(),
                "funktion": w(r, SP_FKT).text(),
                "bereich": w(r, SP_BEREICH).currentData(),
            })
            if z is None:
                kaputt += 1
            else:
                zs.append(z)
        return Konfig(aktiv=self.check_aktiv.isChecked(), zuordnungen=zs,
                      rueckmeldung=self._rm_aus_feldern()), kaputt

    def laden(self):
        konfig = oz.lade_konfig(self._pfad)
        self.tabelle.setRowCount(0)
        for z in konfig.zuordnungen:
            self.zeile_hinzu(z)
        self.check_aktiv.setChecked(konfig.aktiv)
        self._rm_in_felder(konfig.rueckmeldung)
        self.lbl_status.setText(f"{len(konfig.zuordnungen)} Zuordnung(en) gespeichert")

    def uebernehmen(self) -> bool:
        konfig, kaputt = self.konfig()
        rm_ip_ok = oz._ip_gueltig(self.edit_ip.text())
        try:
            oz.installiere_qt_bruecke()
        except Exception as e:
            from src.core.diagnose_log import melde_still
            melde_still("osc.zuordnung", e, text="Qt-Brücke")
        oz.anwenden(konfig)
        gespeichert = oz.speichere_konfig(konfig, self._pfad)
        teile = [f"{len(konfig.zuordnungen)} Zuordnung(en)"]
        if kaputt:
            teile.append(f"{kaputt} Zeile(n) mit ungültiger Adresse NICHT übernommen")
        if konfig.rueckmeldung.aktiv:
            if not rm_ip_ok:
                teile.append("Ziel-IP ungültig → 127.0.0.1")
            teile.append(f"Rückmeldung an {konfig.rueckmeldung.ziel_ip}:"
                         f"{konfig.rueckmeldung.ziel_port}")
        teile.append("gespeichert" if gespeichert else "NICHT gespeichert!")
        self.lbl_status.setText(" · ".join(teile))
        return gespeichert
