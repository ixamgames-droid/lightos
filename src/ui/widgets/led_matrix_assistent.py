"""FM-80: LED-Matrix-Assistent — eine eigene LED-Matrix als Geraet anlegen.

Fragt Pixel Breite x Hoehe, Flaeche in cm (-> Pixelabstand), Bauform,
Kanalformat je Pixel (optional Master-Dimmer/Strobe vorn), Verdrahtung und
Startecke sowie die Zeilen je Universum — und zeigt das Raster live mit
Nummerierung und Universums-Teilen. Ergebnis ist ein normales eigenes
Bibliotheks-Profil (``source='user'``); die Rechnung steht in
``src/core/led_matrix.py``, gespeichert wird ueber ``fixture_db``.

Einstiege: Patch -> „LED-Matrix…“ (dort auch gleich patchen), Menue
Datenbank -> „LED-Matrix-Assistent…“, „Fixture-Profil bearbeiten…“ ->
„Im Matrix-Assistenten…“ (nachtraeglich aendern).
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from src.core import led_matrix as LM

TITEL = "LED-Matrix-Assistent"
#: Bis zu dieser Pixelzahl zeichnet die Vorschau jede Zelle mit Nummer.
VORSCHAU_ZELLEN_MAX = 4096
TEIL_FARBEN = ("#2f6f9f", "#7a4f9f", "#2f8f6f", "#9f6f2f", "#8f2f4f", "#4f6f2f")


def _touch() -> bool:
    try:
        from src.ui.touch_keyboard import is_touch_mode
        return bool(is_touch_mode())
    except Exception:
        return False


def _ueberschreiben_fragen(parent, pid, name, folgen) -> bool:
    from src.ui.widgets.fixture_generator import ueberschreiben_fragen
    return ueberschreiben_fragen(parent, pid, name, folgen)


def ist_matrix_profil(profil_id, eng=None) -> bool:
    """True, wenn das Profil vom Assistenten stammt (Angaben gespeichert)."""
    from sqlalchemy.orm import Session
    from src.core.database import fixture_db as fdb
    from src.core.database.models import FixtureProfile
    try:
        with Session(eng if eng is not None else fdb.engine()) as s:
            p = s.get(FixtureProfile, int(profil_id))
            return p is not None and LM.angaben_von_profil(p) is not None
    except Exception:
        return False


class MatrixVorschau(QWidget):
    """Live-Vorschau: Raster in Anzeige-Lage, Zellen nach Universums-Teil
    gefaerbt, Pixelnummer (1-basiert, Verdrahtungsreihenfolge) in der Zelle,
    das erste Pixel markiert."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 220)
        self._angaben: LM.MatrixAngaben | None = None
        self._zellen: dict[tuple[int, int], tuple[int, int]] = {}

    def setze(self, a: LM.MatrixAngaben | None) -> None:
        self._angaben = a
        self._zellen = {}
        if a is not None and not a.fehler():
            n = int(a.breite_px) * int(a.hoehe_px)
            if n <= VORSCHAU_ZELLEN_MAX:
                b = int(a.breite_px)
                for t in LM.teile(a):
                    for lokal in range(t.zeilen * b):
                        p = t.erstes_pixel + lokal
                        self._zellen[LM.pixel_platz(a, p)] = (p, t.index)
        self.update()

    def zelle(self, zeile: int, spalte: int):
        """``(pixelnummer_0basiert, teil)`` an einer Anzeige-Zelle (Tests)."""
        return self._zellen.get((zeile, spalte))

    def paintEvent(self, _ev):
        a = self._angaben
        p = QPainter(self)
        try:
            p.fillRect(self.rect(), QColor("#11151a"))
            if a is None or a.fehler():
                p.setPen(QColor("#8b949e"))
                p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                           "Keine gültige Matrix")
                return
            b, h = int(a.breite_px), int(a.hoehe_px)
            # Seitenverhaeltnis aus der Flaeche, sonst quadratische Pixel.
            pb, ph = a.pixelabstand_mm()
            vb = (pb / ph) if pb > 0 and ph > 0 else 1.0
            breite, hoehe = self.width() - 8, self.height() - 8
            zh = min(hoehe / h, breite / (b * vb))
            zb = zh * vb
            x0 = (self.width() - zb * b) / 2
            y0 = (self.height() - zh * h) / 2
            if not self._zellen:
                # Grosse Matrix: nur die Teile als Baender.
                for t in LM.teile(a):
                    z = LM.teil_anzeige_zeile(a, t)
                    p.fillRect(QRectF(x0, y0 + z * zh, zb * b, zh * t.zeilen),
                               QColor(TEIL_FARBEN[t.index % len(TEIL_FARBEN)]))
                return
            schrift = QFont(self.font())
            schrift.setPixelSize(max(6, int(min(zb, zh) * 0.38)))
            p.setFont(schrift)
            mit_zahl = min(zb, zh) >= 14
            for (r, c), (nr, teil) in self._zellen.items():
                rect = QRectF(x0 + c * zb, y0 + r * zh, zb, zh)
                farbe = QColor(TEIL_FARBEN[teil % len(TEIL_FARBEN)])
                if nr == 0:
                    farbe = QColor("#d29922")
                p.fillRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), farbe)
                if mit_zahl:
                    p.setPen(QColor("#ffffff"))
                    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(nr + 1))
            p.setPen(QPen(QColor("#e6edf3"), 1))
            p.drawRect(QRectF(x0, y0, zb * b, zh * h))
        finally:
            p.end()


class LedMatrixAssistent(QDialog):
    """Der Dialog. ``profil_id`` = vorhandenes Assistenten-Profil bearbeiten;
    ``state`` = AppState, dann wird „gleich patchen“ angeboten."""

    def __init__(self, parent=None, *, profil_id: int | None = None, state=None):
        super().__init__(parent)
        self.setWindowTitle(TITEL)
        self.saved_id: int | None = None
        self.gepatchte_fids: list[int] = []
        self.gespeichert_meldung = ""
        self._profil_id = profil_id
        self._name_alt: tuple[str, str] | None = None
        self._state = state
        a = LM.MatrixAngaben()
        if profil_id is not None:
            geladen = self._laden(profil_id)
            if geladen is not None:
                a = geladen
                self._name_alt = (a.hersteller, a.modell)
            else:
                self._profil_id = None
        self._baue(a)
        self._aktualisieren()

    # ── Laden ───────────────────────────────────────────────────────────
    def _laden(self, profil_id):
        from sqlalchemy.orm import Session
        from src.core.database import fixture_db as fdb
        from src.core.database.models import FixtureProfile
        with Session(fdb.engine()) as s:
            p = s.get(FixtureProfile, int(profil_id))
            if p is None or (p.source or "").lower() != "user":
                return None
            return LM.angaben_von_profil(p)

    # ── Aufbau ──────────────────────────────────────────────────────────
    def _baue(self, a: LM.MatrixAngaben) -> None:
        touch = _touch()
        haupt = QHBoxLayout(self)
        links = QVBoxLayout()
        haupt.addLayout(links, 0)

        def spin(lo, hi, wert, suffix=""):
            w = QSpinBox()
            w.setRange(lo, hi)
            w.setValue(int(wert))
            if suffix:
                w.setSuffix(suffix)
            w.valueChanged.connect(lambda *_: self._aktualisieren())
            return w

        def dspin(wert):
            w = QDoubleSpinBox()
            w.setRange(0.0, LM.FLAECHE_MAX_CM)
            w.setDecimals(1)
            w.setSuffix(" cm")
            w.setValue(float(wert))
            w.valueChanged.connect(lambda *_: self._aktualisieren())
            return w

        def combo(werte: dict, aktuell):
            w = QComboBox()
            for k, text in werte.items():
                w.addItem(text, k)
            w.setCurrentIndex(max(0, w.findData(aktuell)))
            w.currentIndexChanged.connect(lambda *_: self._aktualisieren())
            return w

        g_name = QGroupBox("Gerät")
        f = QFormLayout(g_name)
        self.ed_hersteller = QLineEdit(a.hersteller)
        self.ed_modell = QLineEdit(a.modell)
        for e in (self.ed_hersteller, self.ed_modell):
            e.textChanged.connect(lambda *_: self._aktualisieren())
        f.addRow("Hersteller:", self.ed_hersteller)
        f.addRow("Modell:", self.ed_modell)
        self.cb_bauform = combo(LM.BAUFORM_TEXT, a.bauform)
        self.cb_bauform.setToolTip(
            "Bauform für das 3D-Bild (Panel, Vorhang, Leiste, Ring, Säule).")
        f.addRow("Bauform:", self.cb_bauform)
        links.addWidget(g_name)

        g_gr = QGroupBox("Größe")
        f = QFormLayout(g_gr)
        self.sp_breite = spin(1, LM.PIXEL_MAX, a.breite_px, " Pixel")
        self.sp_hoehe = spin(1, LM.PIXEL_MAX, a.hoehe_px, " Pixel")
        f.addRow("Breite:", self.sp_breite)
        f.addRow("Höhe:", self.sp_hoehe)
        self.sp_breite_cm = dspin(a.breite_cm)
        self.sp_hoehe_cm = dspin(a.hoehe_cm)
        f.addRow("Fläche breit:", self.sp_breite_cm)
        f.addRow("Fläche hoch:", self.sp_hoehe_cm)
        self.lbl_abstand = QLabel("")
        f.addRow("Pixelabstand:", self.lbl_abstand)
        links.addWidget(g_gr)

        g_k = QGroupBox("Kanäle und Verdrahtung")
        f = QFormLayout(g_k)
        self.cb_format = combo({k: k for k in LM.FORMATE}, a.format)
        self.cb_format.setToolTip("Reihenfolge der Farbkanäle je Pixel, "
                                  "wie der Controller sie erwartet.")
        f.addRow("Kanalformat je Pixel:", self.cb_format)
        self.chk_master = QCheckBox("Master-Dimmer vorn")
        self.chk_master.setChecked(bool(a.master))
        self.chk_strobe = QCheckBox("Strobe vorn")
        self.chk_strobe.setChecked(bool(a.strobe))
        for c in (self.chk_master, self.chk_strobe):
            c.setToolTip("Steht am Anfang jedes Universums-Teils.")
            c.toggled.connect(lambda *_: self._aktualisieren())
        f.addRow("", self.chk_master)
        f.addRow("", self.chk_strobe)
        self.cb_verdrahtung = combo(LM.VERDRAHTUNG_TEXT, a.verdrahtung)
        f.addRow("Verdrahtung:", self.cb_verdrahtung)
        self.cb_startecke = combo(LM.STARTECKE_TEXT, a.startecke)
        f.addRow("Erstes Pixel:", self.cb_startecke)
        self.sp_zeilen = spin(0, LM.PIXEL_MAX, a.zeilen_je_teil)
        self.sp_zeilen.setSpecialValueText("so viele wie passen")
        self.sp_zeilen.setToolTip(
            "Ganze Zeilen je Universum. Ein Pixel wird nie über eine "
            "Universumsgrenze geteilt; jeder Teil wird ein eigenes Gerät.")
        f.addRow("Zeilen je Universum:", self.sp_zeilen)
        links.addWidget(g_k)

        self.lbl_info = QLabel("")
        self.lbl_info.setWordWrap(True)
        links.addWidget(self.lbl_info)
        self.lbl_fehler = QLabel("")
        self.lbl_fehler.setWordWrap(True)
        self.lbl_fehler.setStyleSheet("color: #ff7b72;")
        links.addWidget(self.lbl_fehler)

        zeile = QHBoxLayout()
        self.chk_patchen = QCheckBox("Gleich patchen ab Universum")
        self.sp_universum = QSpinBox()
        self.sp_universum.setRange(1, 4096)
        self.sp_universum.setValue(self._freies_universum())
        self.chk_patchen.setChecked(self._state is not None and self._profil_id is None)
        self.chk_patchen.toggled.connect(lambda *_: self._aktualisieren())
        self.sp_universum.valueChanged.connect(lambda *_: self._aktualisieren())
        zeile.addWidget(self.chk_patchen)
        zeile.addWidget(self.sp_universum)
        zeile.addStretch(1)
        self.chk_patchen.setVisible(self._state is not None)
        self.sp_universum.setVisible(self._state is not None)
        links.addLayout(zeile)
        links.addStretch(1)

        knoepfe = QHBoxLayout()
        knoepfe.addStretch(1)
        self.btn_abbrechen = QPushButton("Abbrechen")
        self.btn_abbrechen.clicked.connect(self.reject)
        self.btn_speichern = QPushButton(
            "Profil aktualisieren" if self._profil_id is not None
            else "In Bibliothek speichern")
        self.btn_speichern.setDefault(True)
        self.btn_speichern.clicked.connect(self.speichern)
        for b in (self.btn_abbrechen, self.btn_speichern):
            if touch:
                b.setMinimumHeight(44)
            knoepfe.addWidget(b)
        links.addLayout(knoepfe)

        rechts = QVBoxLayout()
        rechts.addWidget(QLabel("Vorschau (Nummer = Reihenfolge am Controller, "
                                "Farbe = Universum):"))
        self.vorschau = MatrixVorschau()
        rechts.addWidget(self.vorschau, 1)
        haupt.addLayout(rechts, 1)
        if touch:
            for w in self.findChildren(QWidget):
                if isinstance(w, (QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit,
                                  QCheckBox)):
                    w.setMinimumHeight(44)
        self.resize(900, 640)

    def _freies_universum(self) -> int:
        try:
            belegt = {int(f.universe) for f in self._state.get_patched_fixtures()}
        except Exception:
            return 1
        return (max(belegt) + 1) if belegt else 1

    # ── Zustand ─────────────────────────────────────────────────────────
    def angaben(self) -> LM.MatrixAngaben:
        return LM.MatrixAngaben(
            hersteller=self.ed_hersteller.text().strip(),
            modell=self.ed_modell.text().strip(),
            breite_px=int(self.sp_breite.value()),
            hoehe_px=int(self.sp_hoehe.value()),
            breite_cm=float(self.sp_breite_cm.value()),
            hoehe_cm=float(self.sp_hoehe_cm.value()),
            bauform=self.cb_bauform.currentData(),
            format=self.cb_format.currentData(),
            master=self.chk_master.isChecked(),
            strobe=self.chk_strobe.isChecked(),
            verdrahtung=self.cb_verdrahtung.currentData(),
            startecke=self.cb_startecke.currentData(),
            zeilen_je_teil=int(self.sp_zeilen.value()),
        )

    def _aktualisieren(self) -> None:
        a = self.angaben()
        pb, ph = a.pixelabstand_mm()
        self.lbl_abstand.setText(f"{pb:g} × {ph:g} mm" if pb and ph else "—")
        fehler = a.fehler()
        self.lbl_fehler.setText("\n".join(fehler))
        self.btn_speichern.setEnabled(not fehler)
        if fehler:
            self.lbl_info.setText("")
        else:
            tl = LM.teile(a)
            kan = sum(t.kanaele for t in tl)
            text = (f"{a.breite_px * a.hoehe_px} Pixel, {kan} Kanäle, "
                    f"{len(tl)} Universum" + ("" if len(tl) == 1 else "/Universen")
                    + f" à {a.zeilen_teil()} Zeilen "
                    f"({a.zeilen_teil() * a.breite_px} Pixel je Universum — "
                    "so am Pixel-Controller einstellen).")
            if len(tl) > 1:
                text += (f" Jeder Teil wird ein eigenes Gerät; dazu eine "
                         f"Gruppe über die ganze Matrix.")
            if self._state is not None and self.chk_patchen.isChecked():
                u = int(self.sp_universum.value())
                text += (f" Patch: Universum {u}" +
                         (f"–{u + len(tl) - 1}" if len(tl) > 1 else "") + ", Adresse 1.")
            self.lbl_info.setText(text)
        self.vorschau.setze(a)

    # ── Speichern ───────────────────────────────────────────────────────
    def speichern(self) -> bool:
        from src.core.database import fixture_db as fdb
        a = self.angaben()
        try:
            payload = LM.profil_payload(a)
        except ValueError as e:
            QMessageBox.warning(self, TITEL, str(e))
            return False
        from src.core.kopfformular import kopf_beanstandung
        beanstandung = kopf_beanstandung(a.hersteller, a.modell)
        if beanstandung:
            QMessageBox.warning(self, TITEL, beanstandung)
            return False
        from src.ui.widgets.fixture_generator import profil_dubletten
        name_bleibt = (self._name_alt is not None and
                       fdb.profil_schluessel(*self._name_alt)
                       == fdb.profil_schluessel(a.hersteller, a.modell))
        try:
            andere = [] if name_bleibt else profil_dubletten(
                a.hersteller, a.modell, ohne=self._profil_id)
        except Exception as e:
            QMessageBox.warning(self, TITEL, f"Bibliothek nicht lesbar:\n{e}")
            return False
        if andere:
            QMessageBox.warning(
                self, TITEL,
                f"„{a.hersteller} / {a.modell}“ steht schon in der Bibliothek. "
                "Bitte einen anderen Modellnamen wählen.")
            return False
        try:
            if self._profil_id is not None:
                from src.ui.widgets.fixture_editor import (_gepatchte_geraete,
                                                            profil_patch_folgen)
                folgen = profil_patch_folgen(
                    self._profil_id, _gepatchte_geraete(),
                    [(m["name"], m["channel_count"]) for m in payload["modes"]],
                    name_alt=self._name_alt, name_neu=(a.hersteller, a.modell))
                if not _ueberschreiben_fragen(
                        self, self._profil_id, f"{a.hersteller} {a.modell}", folgen):
                    return False
                pid = fdb.update_user_profile(self._profil_id, payload)
                try:
                    from src.core.app_state import profil_geaendert
                    profil_geaendert(pid)
                except Exception:
                    pass
                self.gespeichert_meldung = f"LED-Matrix „{a.modell}“ aktualisiert."
            else:
                pid = fdb.create_user_profile(payload)
                self.gespeichert_meldung = f"LED-Matrix „{a.modell}“ gespeichert."
        except Exception as e:
            QMessageBox.warning(self, TITEL, f"Fehlgeschlagen:\n{e}")
            return False
        self.saved_id = int(pid)
        try:
            from src.core.app_state import clear_channel_cache
            clear_channel_cache()
        except Exception:
            pass
        if self._state is not None and self.chk_patchen.isChecked():
            try:
                self.gepatchte_fids = LM.matrix_patchen(
                    self._state, self.saved_id, int(self.sp_universum.value()))
                self.gespeichert_meldung += (
                    f" {len(self.gepatchte_fids)} Gerät(e) gepatcht.")
            except Exception as e:
                QMessageBox.warning(
                    self, TITEL,
                    f"Profil gespeichert, aber nicht gepatcht:\n{e}")
        try:
            from src.core.sync import SyncEvent, get_sync
            get_sync().emit(SyncEvent.REFRESH_ALL, None)
        except Exception:
            pass
        self.accept()
        return True
