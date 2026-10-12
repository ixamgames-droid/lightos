"""LAS-35: Einmess-Assistent „Feld einmessen" — Verfahren Wand und Zollstock.

Vier Schritte: Aufstellung · Größtes Feld zeigen · Ablesen · Übernehmen.
Die Rechnung liegt in ``core/laser/feld_einmessen.py``; gerechnet wird mit dem,
was der Nutzer an der Wand abliest — nie mit DMX-Werten.

**Licht:** Dieser Assistent ist die einzige Stelle der Sperrzonen-Oberflaeche,
die einen Laser einschalten kann. Das geschieht nur

* nach dem Haken bei der ausdruecklichen Bestaetigung UND dem Druck auf den
  Knopf (der Haken faellt nach jedem Einschalten wieder heraus),
* ueber den normalen Programmer-Weg (LASER NOT-AUS, Blackout und Grand Master
  wirken unveraendert; ein gedrueckter NOT-AUS wird nicht geloest),
* und nur, wenn das Geraeteprofil sagt, welche Werte das groesste Feld ergeben.

Jedes Ende — Uebernehmen, Abbrechen, Schliessen des Planers, STOPP — setzt die
Betriebsart wieder auf „Aus", falls der Assistent eingeschaltet hat. Der Weg
„Ich stelle den Laser selbst ein" sendet nichts.
"""
from __future__ import annotations

import html

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from src.core.laser import feld_einmessen as E
from src.core.laser import sperrzonen as S
from src.ui.visualizer import sperrzonen_ui as UI
from src.ui.visualizer.sperrzonen_ui import UmbruchText, _spin

SCHRITTE = ("Aufstellung", "Größtes Feld", "Ablesen", "Übernehmen")
NOTAUS_HINWEIS = "Der LASER NOT-AUS oben rechts im Hauptfenster gilt jederzeit."


class _SchrittLeiste(QWidget):
    """Vier Kreise: erledigt (gruen), aktuell (blau), offen (grau)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.aktuell = 0
        self.setFixedHeight(54)

    def paintEvent(self, _ev):  # noqa: N802 (Qt-API)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        breite = self.width() / len(SCHRITTE)
        for i, name in enumerate(SCHRITTE):
            m = QPointF(breite * (i + 0.5), 15)
            farbe = "#2ea043" if i < self.aktuell else (
                UI.BLAU if i == self.aktuell else "#3a3a3a")
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(farbe))
            p.drawEllipse(m, 14, 14)
            f = QFont(self.font())
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("#ffffff"))
            p.drawText(QRectF(m.x() - 14, 1, 28, 28), Qt.AlignmentFlag.AlignCenter,
                       "✓" if i < self.aktuell else str(i + 1))
            f = QFont(self.font())
            f.setPixelSize(11)
            p.setFont(f)
            p.setPen(QColor("#ffffff" if i <= self.aktuell else "#8b949e"))
            p.drawText(QRectF(breite * i, 32, breite, 18),
                       Qt.AlignmentFlag.AlignCenter, name)
        p.end()


class _Skizze(QWidget):
    """Zeigt, was gemeint ist. ``art="aufstellung"``: Laser und Wand von oben
    mit dem Abstand. ``art="wand"``: die Wand von vorn mit der Mitte
    (Geraeteachse) und den vier Wegen."""

    def __init__(self, art: str, parent=None):
        super().__init__(parent)
        self.art = art
        self.abstand_m = 4.0
        self.wege = {r: 0.0 for r in S.RAENDER}      # Zentimeter
        self.setFixedHeight(150 if art == "aufstellung" else 156)
        self.setObjectName(f"einmessSkizze_{art}")

    def setze(self, abstand_m: float, wege=None) -> None:
        self.abstand_m = float(abstand_m)
        if wege is not None:
            self.wege = dict(wege)
        self.update()

    def _text(self, p, x, y, text, farbe="#ffffff", fett=False, mitte=False):
        f = QFont(self.font())
        f.setPixelSize(11)
        f.setBold(fett)
        p.setFont(f)
        p.setPen(QColor(farbe))
        if mitte:
            w = p.fontMetrics().horizontalAdvance(text)
            x -= w / 2
        x = max(3.0, min(self.width() - p.fontMetrics().horizontalAdvance(text) - 3.0, x))
        p.drawText(QPointF(x, y), text)

    def paintEvent(self, _ev):  # noqa: N802 (Qt-API)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#101216"))
        if self.art == "aufstellung":
            self._male_aufstellung(p)
        else:
            self._male_wand(p)
        p.end()

    def _male_aufstellung(self, p) -> None:
        w, h = self.width(), self.height()
        mx = w / 2
        p.fillRect(QRectF(8, 22, w - 16, 9), QColor("#4a4f59"))
        self._text(p, 10, 16, "Wand", "#9aa4b0")
        self._text(p, mx + 8, 16, "Mitte (Geräteachse)")
        spitze = QPointF(mx, h - 24)
        halb = min(w / 2 - 30, 105)
        p.setPen(QPen(QColor("#30ff50"), 1.2))
        p.setBrush(QColor(48, 255, 80, 26))
        p.drawPolygon(QPolygonF([spitze, QPointF(mx - halb, 31), QPointF(mx + halb, 31)]))
        p.setPen(QPen(QColor("#ffffff"), 1.2, Qt.PenStyle.DashLine))
        p.drawLine(spitze, QPointF(mx, 31))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QPointF(mx, 31), 4, 4)
        self._text(p, mx + 8, (h + 10) / 2, f"Abstand {E.de(self.abstand_m)} m", fett=True)
        p.setPen(QPen(QColor("#c8ccd4"), 1.5))
        p.setBrush(QColor("#20242b"))
        p.drawRoundedRect(QRectF(mx - 12, h - 26, 24, 16), 2, 2)
        self._text(p, mx + 18, h - 13, "Laser, gerade auf die Wand", "#9aa4b0")

    def _male_wand(self, p) -> None:
        w, h = self.width(), self.height()
        m = QPointF(w / 2, h / 2 + 6)
        self._text(p, 10, 15, "Wand von vorn — Blick in Strahlrichtung", "#9aa4b0")
        groesste = max(max(self.wege.values()), 1.0)
        halb_x, halb_y = w / 2 - 104, h / 2 - 42
        px = {r: max(14.0, self.wege[r] / groesste * (halb_x if r in ("links", "rechts")
                                                      else halb_y))
              for r in S.RAENDER}
        feld = QRectF(m.x() - px["links"], m.y() - px["oben"],
                      px["links"] + px["rechts"], px["oben"] + px["unten"])
        p.setPen(QPen(QColor("#30ff50"), 1.2))
        p.setBrush(QColor(48, 255, 80, 26))
        p.drawRect(feld)
        farben = {"links": "#6ab0ff", "rechts": "#f0c000",
                  "oben": "#ff9df0", "unten": "#7ee08f"}
        enden = {"links": QPointF(feld.left(), m.y()), "rechts": QPointF(feld.right(), m.y()),
                 "oben": QPointF(m.x(), feld.top()), "unten": QPointF(m.x(), feld.bottom())}
        for rand in S.RAENDER:
            p.setPen(QPen(QColor(farben[rand]), 3))
            p.drawLine(m, enden[rand])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(m, 4.5, 4.5)
        self._text(p, m.x() + 8, m.y() - 7, "Mitte")

        def _cm(rand):
            return f"{rand} {E.de(self.wege[rand], 0)} cm"

        self._text(p, feld.left() - 6 - p.fontMetrics().horizontalAdvance(_cm("links")) - 8,
                   m.y() + 4, _cm("links"), farben["links"], fett=True)
        self._text(p, feld.right() + 8, m.y() + 4, _cm("rechts"), farben["rechts"], fett=True)
        self._text(p, m.x(), feld.top() - 7, _cm("oben"), farben["oben"], fett=True, mitte=True)
        self._text(p, m.x(), feld.bottom() + 15, _cm("unten"), farben["unten"], fett=True,
                   mitte=True)


class _Seiten(QWidget):
    """Eine Seite zur Zeit. Anders als ein ``QStackedWidget`` ist dieser Stapel
    nur so hoch wie die GEZEIGTE Seite — sonst rollt eine kurze Seite, weil
    eine andere lang ist."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._seiten: list = []
        self._nr = 0

    def addWidget(self, w) -> None:  # noqa: N802 (wie QStackedWidget)
        self._lay.addWidget(w)          # erst einhaengen, dann zeigen
        w.setVisible(not self._seiten)
        self._seiten.append(w)

    def count(self) -> int:
        return len(self._seiten)

    def currentIndex(self) -> int:  # noqa: N802
        return self._nr

    def setCurrentIndex(self, nr: int) -> None:  # noqa: N802
        self._nr = nr
        for i, w in enumerate(self._seiten):
            w.setVisible(i == nr)


def _kasten(farbe: str, grund: str) -> QLabel:
    lab = UmbruchText("")
    lab.setStyleSheet(f"background:{grund};border:1px solid {farbe};border-radius:4px;"
                      "padding:7px 9px;")
    return lab


class EinmessAssistent(QWidget):
    """Der Assistent fuer EINEN Laser. Meldet ``beendet(feld)`` — das
    eingemessene :class:`LaserFeld` oder ``None`` (abgebrochen)."""

    beendet = Signal(object)

    def __init__(self, state, fid: int, name: str, bisher: S.LaserFeld | None = None,
                 parent=None, schalter=None, heute=None):
        super().__init__(parent)
        self.setObjectName("einmessAssistent")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(UI.PLANER_QSS)
        self.fid = int(fid)
        self._bisher = bisher or S.LaserFeld()
        self._heute = heute
        self.schalter = schalter or E.FeldSchalter(state, fid)
        self._fertig = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(7)
        kopfzeile = QHBoxLayout()
        kopf = QLabel("LASER-FELD EINMESSEN")
        kopf.setProperty("rolle", "kopf")
        kopf.setStyleSheet("color:#6ab0ff;")
        kopfzeile.addWidget(kopf)
        kopfzeile.addStretch(1)
        self._btn_abbrechen = QPushButton("✕ Abbrechen")
        self._btn_abbrechen.setObjectName("einmessAbbrechen")
        self._btn_abbrechen.setToolTip("Bricht das Einmessen ab. Hat der Assistent "
                                       "den Laser eingeschaltet, geht er aus.")
        self._btn_abbrechen.clicked.connect(self.abbrechen)
        kopfzeile.addWidget(self._btn_abbrechen)
        lay.addLayout(kopfzeile)
        titel = QLabel(f"<b>Laser {self.fid} · {html.escape(name)}</b>")
        titel.setTextFormat(Qt.TextFormat.RichText)
        titel.setStyleSheet("font-size:14px;color:#ffffff;")
        lay.addWidget(titel)
        self._leiste = _SchrittLeiste()
        lay.addWidget(self._leiste)
        self._seiten = _Seiten()
        for bau in (self._baue_aufstellung, self._baue_zeigen, self._baue_ablesen,
                    self._baue_uebernehmen):
            self._seiten.addWidget(bau())
        rollen = QScrollArea()                 # kleines Fenster: nichts abschneiden
        rollen.setWidgetResizable(True)
        rollen.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rollen.setWidget(self._seiten)
        rollen.viewport().setStyleSheet("background:transparent;")
        lay.addWidget(rollen, stretch=1)

        self._btn_stopp = QPushButton("STOPP — Laser aus")
        self._btn_stopp.setObjectName("einmessStopp")
        self._btn_stopp.setProperty("rolle", "stopp")
        self._btn_stopp.setToolTip("Setzt die Betriebsart dieses Lasers auf „Aus“. "
                                   + NOTAUS_HINWEIS)
        self._btn_stopp.clicked.connect(self.stopp)
        lay.addWidget(self._btn_stopp)
        self._lbl_notaus = QLabel(NOTAUS_HINWEIS)
        self._lbl_notaus.setProperty("rolle", "blass")
        self._lbl_notaus.setWordWrap(True)
        lay.addWidget(self._lbl_notaus)

        fuss = QHBoxLayout()
        self._btn_zurueck = QPushButton("◂ Zurück")
        self._btn_zurueck.clicked.connect(self.zurueck)
        self._btn_weiter = QPushButton("Weiter ▸")
        self._btn_weiter.setProperty("rolle", "blau")
        self._btn_weiter.clicked.connect(self.weiter)
        fuss.addWidget(self._btn_zurueck)
        fuss.addWidget(self._btn_weiter, stretch=1)
        lay.addLayout(fuss)
        self._zeige_schritt(0)

    # ── Seiten ───────────────────────────────────────────────────────────
    @staticmethod
    def _seite():
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(7)
        return w, lay

    @staticmethod
    def _satz(text: str, blass: bool = False) -> QLabel:
        lab = UmbruchText(text)
        if blass:
            lab.setProperty("rolle", "blass")
        return lab

    def _baue_aufstellung(self) -> QWidget:
        w, lay = self._seite()
        self._skizze_aufstellung = _Skizze("aufstellung")
        lay.addWidget(self._skizze_aufstellung)
        lay.addWidget(self._satz(
            "Richte den Laser <b>gerade auf eine freie Wand</b>. Miss den Abstand "
            "vom Austrittsfenster bis zur Wand."))
        t = QLabel("Abstand Laser → Wand")
        t.setProperty("rolle", "blass")
        lay.addWidget(t)
        self.sp_abstand = _spin(0.0, 100.0, 4.0, schritt=0.1, suffix=" m", stellen=2)
        self.sp_abstand.setObjectName("einmessAbstand")
        self.sp_abstand.valueChanged.connect(self._messung_geaendert)
        lay.addWidget(self.sp_abstand)
        warnung = _kasten("#f0c000", "#2e2600")
        warnung.setText(
            f'<b style="color:{UI.GELB}">Vor dem Messen:</b> Niemand im Strahl. '
            "Raum abgesperrt, Türen zu, keine spiegelnden Flächen im Feld. "
            "Laserschutzbeauftragter einverstanden.")
        lay.addWidget(warnung)
        lay.addStretch(1)
        return w

    def _baue_zeigen(self) -> QWidget:
        w, lay = self._seite()
        lay.addWidget(self._satz(
            "Der Laser muss jetzt sein <b>größtes Feld</b> zeigen: größtes Muster, "
            "volle Auslenkung. An der Wand markierst du gleich die vier äußersten "
            "Punkte."))
        rahmen = QFrame()
        rahmen.setProperty("rolle", "karte")
        rl = QVBoxLayout(rahmen)
        rl.setContentsMargins(9, 8, 9, 9)
        rl.setSpacing(6)
        rl.addWidget(self._satz("<b>LightOS stellt den Laser ein</b>"))
        self._lbl_plan = self._satz("", blass=True)
        rl.addWidget(self._lbl_plan)
        # Der Satz steht als umbrechender Text NEBEN dem Haken (ein Haken-
        # Text bricht nicht um und wuerde abgeschnitten); ``text()`` des
        # Hakens bleibt der Satz.
        self.chk_bestaetigt = QCheckBox("")
        self.chk_bestaetigt.setObjectName("einmessBestaetigung")
        self.chk_bestaetigt.setAccessibleName(E.BESTAETIGUNG)
        self.chk_bestaetigt.toggled.connect(self._zeigen_auffrischen)
        self.lbl_bestaetigt = self._satz(
            f'<b style="color:{UI.GELB}">{html.escape(E.BESTAETIGUNG)}</b>')
        self.lbl_bestaetigt.setObjectName("einmessBestaetigungText")
        self.lbl_bestaetigt.mousePressEvent = self._satz_getippt
        zeile = QHBoxLayout()
        zeile.setSpacing(8)
        zeile.addWidget(self.chk_bestaetigt, alignment=Qt.AlignmentFlag.AlignTop)
        zeile.addWidget(self.lbl_bestaetigt, stretch=1)
        rl.addLayout(zeile)
        self.btn_zeigen = QPushButton("Größtes Feld zeigen — schaltet den Laser ein")
        self.btn_zeigen.setObjectName("einmessZeigen")
        self.btn_zeigen.setProperty("rolle", "gelb")
        self.btn_zeigen.setMinimumHeight(42)
        self.btn_zeigen.clicked.connect(self.feld_zeigen)
        rl.addWidget(self.btn_zeigen)
        lay.addWidget(rahmen)
        self.btn_selbst = QPushButton("Ich stelle den Laser selbst ein")
        self.btn_selbst.setObjectName("einmessSelbst")
        self.btn_selbst.setToolTip("LightOS sendet nichts. Stelle im Laser-Tab oder "
                                   "am Gerät das größte Muster ein.")
        self.btn_selbst.clicked.connect(self.selbst_einstellen)
        lay.addWidget(self.btn_selbst)
        lay.addWidget(self._satz("LightOS sendet dabei nichts.", blass=True))
        self._lbl_zustand = _kasten("#555", "#2a2a2a")
        lay.addWidget(self._lbl_zustand)
        lay.addStretch(1)
        return w

    def _satz_getippt(self, _ev) -> None:
        """Tipp auf den Satz = Tipp auf den Haken (Fingerbedienung)."""
        if self.chk_bestaetigt.isEnabled():
            self.chk_bestaetigt.toggle()

    def _baue_ablesen(self) -> QWidget:
        w, lay = self._seite()
        self._skizze_wand = _Skizze("wand")
        lay.addWidget(self._skizze_wand)
        lay.addWidget(self._satz(
            "Miss von der <b>Mitte</b> (dort trifft die Geräteachse die Wand) bis "
            "zum äußersten Punkt des Felds, in Zentimetern."))
        gitter = QGridLayout()
        gitter.setHorizontalSpacing(8)
        gitter.setVerticalSpacing(2)
        self.sp_weg = {}
        for i, rand in enumerate(S.RAENDER):
            t = QLabel(f"Rand {rand}")
            t.setProperty("rolle", "blass")
            sp = _spin(0.0, 10000.0, 0.0, schritt=5.0, suffix=" cm", stellen=0)
            sp.setObjectName(f"einmessWeg_{rand}")
            sp.valueChanged.connect(self._messung_geaendert)
            gitter.addWidget(t, (i // 2) * 2, i % 2)
            gitter.addWidget(sp, (i // 2) * 2 + 1, i % 2)
            self.sp_weg[rand] = sp
        lay.addLayout(gitter)
        self._lbl_ergebnis = _kasten("#2ea043", "#12301a")
        self._lbl_ergebnis.setObjectName("einmessErgebnis")
        lay.addWidget(self._lbl_ergebnis)
        self._lbl_rueckfrage = _kasten("#f0c000", "#2e2600")
        self._lbl_rueckfrage.setObjectName("einmessRueckfrage")
        lay.addWidget(self._lbl_rueckfrage)
        self.chk_stimmt = QCheckBox("Ja, die Werte stimmen so")
        self.chk_stimmt.setObjectName("einmessStimmt")
        self.chk_stimmt.toggled.connect(self._weiter_auffrischen)
        lay.addWidget(self.chk_stimmt)
        lay.addStretch(1)
        return w

    def _baue_uebernehmen(self) -> QWidget:
        w, lay = self._seite()
        self._lbl_summe = _kasten("#2ea043", "#12301a")
        self._lbl_summe.setObjectName("einmessSumme")
        lay.addWidget(self._lbl_summe)
        t = QLabel(f"Zuschlag rundum (Vorgabe {S.ZUSCHLAG_STANDARD:g}°, "
                   f"mindestens {S.ZUSCHLAG_MIN:g}°)")
        t.setProperty("rolle", "blass")
        lay.addWidget(t)
        self.sp_zuschlag = _spin(S.ZUSCHLAG_MIN, S.ZUSCHLAG_MAX, S.ZUSCHLAG_STANDARD,
                                 schritt=0.5, suffix=" °", stellen=1)
        self.sp_zuschlag.setObjectName("einmessZuschlag")
        self.sp_zuschlag.valueChanged.connect(self._summe_auffrischen)
        lay.addWidget(self.sp_zuschlag)
        lay.addWidget(self._satz(
            "Der Zuschlag deckt Ablesefehler und eine nicht ganz gerade Montage "
            "ab. Die Winkel gelten für das Gerät — steht es später anders als im "
            "3D eingetragen, stimmt die Anzeige nicht mehr.", blass=True))
        self._lbl_ende = _kasten("#555", "#2a2a2a")
        lay.addWidget(self._lbl_ende)
        lay.addStretch(1)
        return w

    # ── Rechnung ─────────────────────────────────────────────────────────
    def messung(self) -> E.Messung:
        return E.Messung(float(self.sp_abstand.value()),
                         *(float(self.sp_weg[r].value()) for r in S.RAENDER))

    def rueckfragen(self) -> list:
        return E.rueckfragen(self.messung())

    def feld(self) -> S.LaserFeld | None:
        """Das Feld, das „Übernehmen" eintragen wuerde — oder ``None``."""
        try:
            return E.feld_aus_messung(self.messung(), self.sp_zuschlag.value(),
                                      datum=self._heute)
        except ValueError:
            return None

    def _messung_geaendert(self, *_a) -> None:
        m = self.messung()
        self._skizze_aufstellung.setze(m.abstand_m)
        self._skizze_wand.setze(m.abstand_m, {r: m.weg_cm(r) for r in S.RAENDER})
        self.chk_stimmt.setChecked(False)        # neue Zahlen, neue Antwort
        fragen = self.rueckfragen()
        gesperrt = [f for f in fragen if f.sperrt]
        if gesperrt:
            self._lbl_ergebnis.setText(
                '<span style="color:#8b949e">Noch kein Ergebnis.</span>')
        else:
            w = E.randwinkel(m)
            zeilen = ['<span style="color:#7ee08f">Ergibt</span>',
                      '<b style="font-size:14px">' + " · ".join(
                          f"{r} {E.de(w[r], 1)}°" for r in S.RAENDER) + "</b>"]
            zeilen.append('<span style="color:#8b949e;font-size:11px">Gegenprobe — '
                          + "<br>".join(
                              html.escape(E.gegenprobe(m.abstand_m, m.weg_cm(r), r))
                              for r in S.RAENDER) + "</span>")
            self._lbl_ergebnis.setText("<br>".join(zeilen))
        self._lbl_rueckfrage.setVisible(bool(fragen))
        self._lbl_rueckfrage.setText("<br>".join(
            f'<b style="color:{UI.GELB}">{"Bitte korrigieren" if f.sperrt else "Rückfrage"}:'
            f'</b> {html.escape(f.text)}' for f in fragen))
        self.chk_stimmt.setVisible(bool(fragen) and not gesperrt)
        self._weiter_auffrischen()

    def _summe_auffrischen(self, *_a) -> None:
        feld = self.feld()
        if feld is None:
            self._lbl_summe.setText("Die Messung ist noch nicht vollständig.")
            return
        tag = S.datum_deutsch(feld.quelle_datum)
        bisher = self._bisher
        alt = ("bisher nichts eingetragen" if not bisher.vollstaendig else
               "bisher " + " / ".join(f"{getattr(bisher, r):g}°" for r in S.RAENDER)
               + f" ({S.quelle_text(bisher)})")
        self._lbl_summe.setText(
            '<span style="color:#7ee08f">Wird eingetragen</span><br>'
            '<b style="font-size:14px">'
            + " · ".join(f"{r} {E.de(getattr(feld, r), 1)}°" for r in S.RAENDER)
            + f"</b><br>Zuschlag {E.de(feld.zuschlag, 1)}° · Quelle: eingemessen am {tag}"
            f'<br><span style="color:#8b949e">{html.escape(alt)}</span>')

    # ── Schritte ─────────────────────────────────────────────────────────
    def schritt(self) -> int:
        return self._seiten.currentIndex()

    def _zeige_schritt(self, nr: int) -> None:
        nr = max(0, min(len(SCHRITTE) - 1, int(nr)))
        self._seiten.setCurrentIndex(nr)
        self._leiste.aktuell = nr
        self._leiste.update()
        self._btn_zurueck.setEnabled(nr > 0)
        self._btn_weiter.setText(
            ("Übernehmen — Laser aus" if self.schalter.eingeschaltet else "Übernehmen")
            if nr == 3 else f"Weiter: {SCHRITTE[nr + 1]} ▸")
        self._btn_stopp.setVisible(nr > 0)
        self._lbl_notaus.setVisible(nr > 0)
        if nr == 1:
            self.chk_bestaetigt.setChecked(False)
            self._zeigen_auffrischen()
        self._messung_geaendert()
        self._summe_auffrischen()
        if nr == 3:
            self._lbl_ende.setText(
                "Beim Übernehmen setzt LightOS die Betriebsart wieder auf „Aus“."
                if self.schalter.eingeschaltet else
                "LightOS hat den Laser nicht eingeschaltet — schalte ihn selbst "
                "wieder aus.")

    def _weiter_erlaubt(self) -> bool:
        nr = self.schritt()
        fragen = self.rueckfragen()
        if nr == 0:
            return float(self.sp_abstand.value()) > 0.0
        if nr >= 2:
            if any(f.sperrt for f in fragen):
                return False
            if fragen and not self.chk_stimmt.isChecked():
                return False
        return True

    def _weiter_auffrischen(self, *_a) -> None:
        self._btn_weiter.setEnabled(self._weiter_erlaubt())

    def weiter(self) -> None:
        if not self._weiter_erlaubt():
            return
        if self.schritt() == 3:
            self.uebernehmen()
        else:
            self._zeige_schritt(self.schritt() + 1)

    def zurueck(self) -> None:
        self._zeige_schritt(self.schritt() - 1)

    # ── Licht ────────────────────────────────────────────────────────────
    def _zeigen_auffrischen(self, *_a) -> None:
        ok, grund = self.schalter.kann_einschalten()
        plan = self.schalter.plan() or []
        if plan:
            self._lbl_plan.setText(
                "Gesendet wird über den Programmer: "
                + ", ".join(html.escape(s.text) for s in plan)
                + ". Das größte Muster und die äußersten Lagen stellst du bei "
                "Bedarf im Laser-Tab nach.")
        else:
            self._lbl_plan.setText(html.escape(
                grund or "Das Geräteprofil sagt nicht, welche Werte das größte "
                         "Feld ergeben.") + " Nimm den Weg darunter.")
        if plan and not ok:
            self._lbl_plan.setText(self._lbl_plan.text() + "<br><b>"
                                   + html.escape(grund) + "</b>")
        self.chk_bestaetigt.setEnabled(ok)
        self.btn_zeigen.setEnabled(ok and self.chk_bestaetigt.isChecked())
        self._lbl_zustand.setText(
            f'<b style="color:{UI.GELB}">LightOS hat den Laser eingeschaltet.</b> '
            "STOPP setzt die Betriebsart auf „Aus“."
            if self.schalter.eingeschaltet else
            "LightOS sendet nichts an den Laser.")

    def feld_zeigen(self) -> bool:
        """Groesstes Feld zeigen — nur mit gesetztem Haken."""
        an = self.schalter.einschalten(self.chk_bestaetigt.isChecked() is True
                                       and self.chk_bestaetigt.isEnabled())
        # Der Haken gilt fuer EIN Einschalten.
        self.chk_bestaetigt.setChecked(False)
        self._zeigen_auffrischen()
        return an

    def selbst_einstellen(self) -> None:
        """Der Weg von Hand: LightOS sendet nichts."""
        self._zeige_schritt(2)

    def stopp(self) -> None:
        """STOPP: Betriebsart auf „Aus" — egal, wer eingeschaltet hat."""
        if self.schalter.eingeschaltet:
            ok = self.schalter.beenden() is not False
        else:
            ok = self.schalter.stopp()
        self.chk_bestaetigt.setChecked(False)
        self._zeigen_auffrischen()
        self._lbl_zustand.setText(
            "STOPP: Betriebsart steht auf „Aus“." if ok else
            f'<b style="color:{UI.GELB}">LightOS konnte die Betriebsart nicht auf '
            "„Aus“ setzen — LASER NOT-AUS oben rechts benutzen.</b>")
        if self.schritt() == 3:
            self._zeige_schritt(3)

    def ausschalten(self) -> None:
        """Aus, falls der Assistent eingeschaltet hat (jedes Ende ruft das)."""
        try:
            self.schalter.beenden()
        except Exception as e:                           # noqa: BLE001
            print(f"[einmess_assistent] ERROR: Ausschalten: {e}")

    def abbrechen(self) -> None:
        if self._fertig:
            return
        self._fertig = True
        self.ausschalten()
        self.beendet.emit(None)

    def uebernehmen(self) -> None:
        if self._fertig:
            return
        feld = self.feld()
        if feld is None or not self._weiter_erlaubt():
            return
        self._fertig = True
        self.ausschalten()             # Laser wieder aus, DANN eintragen
        self.beendet.emit(feld)
