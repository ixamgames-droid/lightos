"""WEB-10: Seitenleiste „Handy-Konsole" des VC-Editors.

Hier baut man die Handy-Konsole selbst: die Leiste zeigt das Handy im
Hochformat als Raster 4 x 10 (wie ``src/web/templates/konsole.html`` es am
Handy darstellt), darunter fest Master + Blackout. Elemente der grossen Konsole
werden als VERKNUEPFUNG abgelegt — per Ziehen in die Leiste oder per Rechtsklick
„Auf Handy-Konsole legen" —, im Raster verschoben, in der Groesse geaendert und
wieder heruntergenommen. Das Original bleibt immer, wo es ist.

Die Leiste selbst entscheidet nichts: jede Aenderung geht ueber die
``handy_*``-Methoden von :class:`VCCanvas` (ein Rueckgaengig-Schritt je
Aenderung) und kommt ueber ``handy_seiten_changed`` zurueck. Was die Konsole
nicht ablegt, liegt auf keiner Seite — und ist am Handy nicht erreichbar.

Bedienbar ist das Raster nur im Bearbeiten-Modus; sonst ist es eine Vorschau.
Der Verbindungsblock oben (Schalter, Zustand, „Verbinden…") geht immer: die
Handy-Konsole auszuschalten soll auch waehrend der Show ein Griff sein.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (QHBoxLayout, QInputDialog, QLabel, QMenu, QMessageBox,
                               QPushButton, QScrollArea, QSizePolicy, QTabBar,
                               QVBoxLayout, QWidget)

from src.core import handy_seiten as hs

#: Kleinste Trefferflaeche fuer Finger (Knoepfe, Reiter, Kacheln).
TREFFER = 36

# ``min-height`` steht hier ausdruecklich: das App-Theme setzt fuer jeden Knopf
# ``min-height: 22px`` und hebt damit ein ``setFixedHeight`` wieder auf.
_KNOPF_CSS = """
    QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                  border-radius:6px; font-size:11px; font-weight:bold; padding:0 8px;
                  min-height:34px; max-height:34px; }
    QPushButton:hover:!disabled { background:#30363d; }
    QPushButton:disabled { color:#484f58; border-color:#21262d; }
"""


def handy_farbe(hex_farbe):
    """Die Farbe einer Taste, wie das Handy sie zeigt (``farbe()`` in
    ``konsole.html``): sehr dunkle Widget-Farben werden aufgehellt, damit „an"
    leuchtet. Rueckgabe (Farbe, Textfarbe) oder None."""
    c = QColor(hex_farbe) if isinstance(hex_farbe, str) else QColor()
    if not c.isValid():
        return None
    r, g, b = c.red(), c.green(), c.blue()
    hell = max(r, g, b)
    if hell < 180:
        if hell < 8:
            r, g, b = 88, 166, 255
        else:
            f = 180.0 / hell
            r, g, b = round(r * f), round(g * f), round(b * f)
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    return QColor(r, g, b), QColor("#10141a" if lum > 0.6 else "#ffffff")


def _schrift(px: int, fett: bool = True) -> QFont:
    f = QFont()
    f.setPixelSize(max(7, int(px)))
    f.setBold(fett)
    return f


class _Reiter(QTabBar):
    """Reiter der Handy-Seiten. Eine per Ziehen geaenderte Reihenfolge wird
    erst beim LOSLASSEN gemeldet: waehrend des Ziehens tauscht Qt Nachbarn
    einzeln — jeder Tausch waere sonst ein eigener Rueckgaengig-Schritt, und ein
    Neuaufbau der Reiter mitten im Ziehen risse den Griff ab."""

    reihenfolge_geaendert = Signal(list)    # neue Reihenfolge der alten Nummern

    def __init__(self, parent=None):
        super().__init__(parent)
        self._maus_unten = False
        self._baut = False
        self.tabMoved.connect(self._verschoben)

    def reihenfolge(self) -> list:
        return [self.tabData(i) for i in range(self.count())]

    def umgestellt(self) -> bool:
        """Stehen die Reiter gerade anders als die Seiten der Konsole (eine
        Reihenfolge ist gezogen, aber noch nicht uebernommen)?"""
        folge = self.reihenfolge()
        return folge != sorted(folge)

    def _verschoben(self, _von, _nach):
        if not self._maus_unten and not self._baut:
            self._melden()

    def _melden(self):
        if self.umgestellt():
            self.reihenfolge_geaendert.emit(self.reihenfolge())

    def mousePressEvent(self, event):
        self._maus_unten = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self._maus_unten = False
        self._melden()

    def tabSizeHint(self, index):
        return QSize(super().tabSizeHint(index).width(), TREFFER)

    def minimumTabSizeHint(self, index):
        return self.tabSizeHint(index)


class HandyRaster(QWidget):
    """Das Handy als Raster — Anzeige und (im Bearbeiten-Modus) Bedienung."""

    ABSTAND = 3             # zwischen den Zellen
    RAND = 8                # Rahmen des Handys
    KOPF = 14               # Kopfzeile (Seitenname)
    FUSS = 32               # feste Leiste unten: Master + Blackout
    GRIFF = 22              # Kantenlaenge der Greifzone unten rechts

    def __init__(self, leiste):
        super().__init__(leiste)
        self._leiste = leiste
        self._auswahl: str | None = None
        self._zieh: dict | None = None      # laufendes Verschieben/Groesse aendern
        self._fremd: dict | None = None     # Vorschau beim Ziehen aus der grossen Konsole
        self.setObjectName("handy_raster")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # 10 Zeilen zu mindestens 36 px: jede Kachel bleibt mit dem Finger treffbar.
        self.setMinimumSize(
            4 * TREFFER + 3 * self.ABSTAND + 2 * self.RAND,
            hs.ZEILEN * TREFFER + (hs.ZEILEN - 1) * self.ABSTAND
            + 2 * self.RAND + self.KOPF + self.FUSS + 2 * self.ABSTAND)

    # ── Geometrie ────────────────────────────────────────────────────────────

    def _handy(self) -> QRectF:
        """Der Rahmen des Handys: volle Breite, hoechstens gut doppelt so hoch."""
        w = float(self.width())
        h = min(float(self.height()), max(float(self.minimumHeight()), w * 2.1))
        return QRectF(0.5, 0.5, w - 1.0, h - 1.0)

    def _feld(self) -> QRectF:
        """Die Flaeche des Rasters innerhalb des Handys."""
        r = self._handy()
        oben = r.top() + self.RAND + self.KOPF + self.ABSTAND
        unten = r.bottom() - self.RAND - self.FUSS - self.ABSTAND
        return QRectF(r.left() + self.RAND, oben,
                      r.width() - 2 * self.RAND, max(10.0, unten - oben))

    def _zelle(self) -> tuple:
        f = self._feld()
        return ((f.width() - (hs.SPALTEN - 1) * self.ABSTAND) / hs.SPALTEN,
                (f.height() - (hs.ZEILEN - 1) * self.ABSTAND) / hs.ZEILEN)

    def feld_rect(self, spalte, zeile, breite=1, hoehe=1) -> QRectF:
        f = self._feld()
        zw, zh = self._zelle()
        return QRectF(f.left() + spalte * (zw + self.ABSTAND),
                      f.top() + zeile * (zh + self.ABSTAND),
                      breite * zw + (breite - 1) * self.ABSTAND,
                      hoehe * zh + (hoehe - 1) * self.ABSTAND)

    def zelle_mitte(self, spalte, zeile) -> QPoint:
        return self.feld_rect(spalte, zeile).center().toPoint()

    def zelle_bei(self, pos) -> tuple:
        """Zelle unter ``pos`` — ausserhalb des Rasters die naechstgelegene."""
        f = self._feld()
        zw, zh = self._zelle()
        s = int((pos.x() - f.left()) // (zw + self.ABSTAND))
        z = int((pos.y() - f.top()) // (zh + self.ABSTAND))
        return (max(0, min(hs.SPALTEN - 1, s)), max(0, min(hs.ZEILEN - 1, z)))

    def kachel_rect(self, kennung) -> QRect | None:
        e = self._eintrag(kennung)
        if e is None:
            return None
        return self.feld_rect(e["spalte"], e["zeile"], e["breite"], e["hoehe"]).toRect()

    def griff_punkt(self, kennung) -> QPoint | None:
        """Ein Punkt im Groessen-Griff (unten rechts) der Kachel."""
        r = self.kachel_rect(kennung)
        if r is None:
            return None
        return QPoint(r.right() - 3, r.bottom() - 3)

    # ── Daten ────────────────────────────────────────────────────────────────

    def _canvas(self):
        return self._leiste.canvas()

    def _seite(self) -> dict | None:
        c = self._canvas()
        if c is None:
            return None
        seiten = c.handy_seiten()["seiten"]
        return seiten[c.handy_seite_nr()] if seiten else None

    def _eintrag(self, kennung) -> dict | None:
        seite = self._seite()
        for e in (seite["eintraege"] if seite else []):
            if e["widget"] == kennung:
                return e
        return None

    def _eintrag_bei(self, pos) -> dict | None:
        seite = self._seite()
        for e in (seite["eintraege"] if seite else []):
            if self.feld_rect(e["spalte"], e["zeile"], e["breite"], e["hoehe"]).contains(
                    QPointF(pos)):
                return e
        return None

    def _im_griff(self, e, pos) -> bool:
        r = self.feld_rect(e["spalte"], e["zeile"], e["breite"], e["hoehe"])
        g = min(float(self.GRIFF), r.width() / 2.0, r.height() / 2.0)
        return pos.x() >= r.right() - g and pos.y() >= r.bottom() - g

    def auswahl(self) -> str | None:
        return self._auswahl if self._eintrag(self._auswahl) is not None else None

    def waehle(self, kennung) -> None:
        self._auswahl = kennung
        self.update()

    def bedienbar(self) -> bool:
        return self._leiste.bearbeiten() and self._canvas() is not None

    # ── Vorschau beim Ziehen aus der grossen Konsole ─────────────────────────

    def zeige_fremd(self, ziel) -> None:
        """``ziel`` = (spalte, zeile, breite, hoehe, passt) oder None (keine)."""
        neu = None if ziel is None else dict(zip(
            ("spalte", "zeile", "breite", "hoehe", "ok"), ziel))
        if neu != self._fremd:
            self._fremd = neu
            self.update()

    # ── Maus ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if not self.bedienbar():
            event.accept()
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        pos = event.position().toPoint()
        e = self._eintrag_bei(pos)
        self._auswahl = e["widget"] if e else None
        self._zieh = None
        if e is not None and event.button() == Qt.MouseButton.LeftButton:
            s, z = self.zelle_bei(pos)
            self._zieh = {
                "kennung": e["widget"],
                "art": "groesse" if self._im_griff(e, pos) else "verschieben",
                "start": dict(e),
                "griff": (s - e["spalte"], z - e["zeile"]),
                "ziel": (e["spalte"], e["zeile"], e["breite"], e["hoehe"]),
                "ok": True,
            }
        self.update()
        event.accept()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if self._zieh is None:
            if self.bedienbar():
                e = self._eintrag_bei(pos)
                if e is not None and self._im_griff(e, pos):
                    self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                elif e is not None:
                    self.setCursor(Qt.CursorShape.OpenHandCursor)
                else:
                    self.unsetCursor()
            return
        d = self._zieh
        alt = d["start"]
        s, z = self.zelle_bei(pos)
        c = self._canvas()
        if d["art"] == "verschieben":
            ns = max(0, min(hs.SPALTEN - alt["breite"], s - d["griff"][0]))
            nz = max(0, min(hs.ZEILEN - alt["hoehe"], z - d["griff"][1]))
            ziel = (ns, nz, alt["breite"], alt["hoehe"])
        else:
            auskunft = c.handy_auskunft(c.widget_mit_kennung(d["kennung"])) if c else None
            if auskunft is None:
                ziel = d["ziel"]
            else:
                b, h = hs.groesse_begrenzen(
                    auskunft["typ"], s - alt["spalte"] + 1, z - alt["zeile"] + 1)
                ziel = (alt["spalte"], alt["zeile"], b, h)
        d["ziel"] = ziel
        d["ok"] = bool(c is not None and hs.passt(
            c.handy_seiten(), c.handy_seite_nr(), *ziel, ausser=d["kennung"]))
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        d, self._zieh = self._zieh, None
        if d is not None and self.bedienbar():
            alt = d["start"]
            ziel = d["ziel"]
            if ziel != (alt["spalte"], alt["zeile"], alt["breite"], alt["hoehe"]):
                c = self._canvas()
                if not d["ok"]:
                    self._leiste.melde("Dort ist kein Platz — das Feld ist belegt.")
                elif not c.handy_eintrag_aendern(c.handy_seite_nr(), d["kennung"], *ziel):
                    self._leiste.melde("Das ließ sich nicht ändern.")
        self.update()
        event.accept()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.bedienbar():
            if self.entferne_auswahl():
                event.accept()
                return
        super().keyPressEvent(event)

    def entferne_auswahl(self) -> bool:
        """Die gewaehlte Verknuepfung von der Seite nehmen (Original bleibt)."""
        kennung = self.auswahl()
        c = self._canvas()
        if kennung is None or c is None or not self.bedienbar():
            return False
        ok = c.handy_eintrag_entfernen(c.handy_seite_nr(), kennung)
        if ok:
            self._auswahl = None
        return ok

    def baue_kontextmenue(self, pos) -> QMenu | None:
        """Rechtsklick-Menue der Kachel unter ``pos`` (None auf freier Flaeche
        oder ausserhalb des Bearbeiten-Modus)."""
        if not self.bedienbar():
            return None
        e = self._eintrag_bei(pos)
        if e is None:
            return None
        self.waehle(e["widget"])
        menu = QMenu(self)
        akt = menu.addAction("Von der Handy-Konsole nehmen")
        akt.setObjectName("handy_nehmen")
        akt.setToolTip("Entfernt nur die Verknüpfung — das Element in der "
                       "Konsole bleibt unverändert.")
        akt.triggered.connect(self.entferne_auswahl)
        menu.setToolTipsVisible(True)
        return menu

    def contextMenuEvent(self, event):
        menu = self.baue_kontextmenue(event.pos())
        if menu is not None:
            menu.exec(event.globalPos())
            menu.deleteLater()
        event.accept()

    # ── Zeichnen ─────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        handy = self._handy()
        p.setPen(QPen(QColor("#3a424d"), 1.5))
        p.setBrush(QColor("#0d1117"))
        p.drawRoundedRect(handy, 14, 14)

        c = self._canvas()
        seite = self._seite()
        feld = self._feld()

        # Kopfzeile wie am Handy: Logo + Seitenname
        kopf = QRectF(feld.left(), handy.top() + self.RAND - 2, feld.width(), self.KOPF)
        p.setFont(_schrift(10))
        p.setPen(QColor("#58a6ff"))
        p.drawText(kopf, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "LightOS")
        p.setFont(_schrift(9, False))
        p.setPen(QColor("#8b949e"))
        name = seite["name"] if seite else "Handy-Konsole"
        p.drawText(kopf.adjusted(52, 0, 0, 0),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(p.font()).elidedText(
                       name, Qt.TextElideMode.ElideRight, int(kopf.width() - 56)))

        # leere Zellen
        bearbeiten = self.bedienbar()
        p.setBrush(QColor(22, 27, 34, 90))
        p.setPen(QPen(QColor("#2d3440" if bearbeiten else "#1c222b"), 1,
                      Qt.PenStyle.DashLine))
        for z in range(hs.ZEILEN):
            for s in range(hs.SPALTEN):
                p.drawRoundedRect(self.feld_rect(s, z), 5, 5)

        if seite is None:
            p.setPen(QColor("#8b949e"))
            p.setFont(_schrift(11))
            text = ("Noch keine Handy-Seite.\n\nElement aus der Konsole hierher "
                    "ziehen\noder „Automatisch füllen“."
                    if bearbeiten else
                    "Noch keine Handy-Seite.\n\n„Bearbeiten“ einschalten,\num sie zu bauen.")
            kasten = QRectF(feld.left() + 6, feld.center().y() - 52, feld.width() - 12, 104)
            p.save()
            p.setPen(QPen(QColor("#30363d"), 1))
            p.setBrush(QColor("#161b22"))
            p.drawRoundedRect(kasten, 8, 8)
            p.restore()
            p.drawText(kasten, Qt.AlignmentFlag.AlignCenter, text)
        else:
            zieh = self._zieh
            # Einmal nachschlagen statt je Kachel die ganze Konsole abzusuchen.
            nach_kennung = {getattr(w, "widget_id", None): w for w in c.alle_widgets()}
            for e in seite["eintraege"]:
                kennung = e["widget"]
                rect = self.feld_rect(e["spalte"], e["zeile"], e["breite"], e["hoehe"])
                auskunft = c.handy_auskunft(nach_kennung.get(kennung))
                blass = zieh is not None and zieh["kennung"] == kennung
                p.setOpacity(0.35 if blass else 1.0)
                self._male_kachel(p, rect, auskunft)
                p.setOpacity(1.0)
                if bearbeiten and kennung == self._auswahl and not blass:
                    self._male_auswahl(p, rect)
            if zieh is not None:
                self._male_ziel(p, self.feld_rect(*zieh["ziel"]), zieh["ok"])
        if self._fremd is not None:
            f = self._fremd
            self._male_ziel(p, self.feld_rect(f["spalte"], f["zeile"], f["breite"],
                                              f["hoehe"]), f["ok"])

        self._male_fuss(p, handy, feld)
        p.end()

    def _male_ziel(self, p, rect, ok: bool):
        farbe = QColor("#3fb950" if ok else "#f85149")
        fuell = QColor(farbe)
        fuell.setAlpha(60)
        p.setBrush(fuell)
        p.setPen(QPen(farbe, 2, Qt.PenStyle.DashLine))
        p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 6, 6)

    def _male_auswahl(self, p, rect):
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("#58d68d"), 2))
        p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 6, 6)
        g = min(12.0, rect.width() / 3.0, rect.height() / 3.0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#58d68d"))
        p.drawRoundedRect(QRectF(rect.right() - g, rect.bottom() - g, g, g), 2, 2)

    def _male_kachel(self, p, rect, auskunft):
        if auskunft is None:
            # verwaist oder nicht (mehr) fernbedienbar: am Handy ein leeres Feld
            p.setBrush(QColor(22, 27, 34, 140))
            p.setPen(QPen(QColor("#6e4b1c"), 1, Qt.PenStyle.DashLine))
            p.drawRoundedRect(rect, 6, 6)
            p.setPen(QColor("#d29922"))
            p.setFont(_schrift(8, False))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "leer")
            return
        typ = auskunft.get("typ")
        if typ == "fader":
            self._male_fader(p, rect, auskunft)
        elif typ == "cueliste":
            self._male_cueliste(p, rect, auskunft)
        else:
            self._male_taste(p, rect, auskunft)

    def _text(self, p, rect, text, px, farbe, fett=True, zeilen=1):
        p.setFont(_schrift(px, fett))
        p.setPen(QColor(farbe))
        fm = QFontMetrics(p.font())
        text = str(text or "")
        if zeilen > 1 and fm.horizontalAdvance(text) > rect.width() \
                and rect.height() >= 2 * fm.height():
            p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap),
                       text)
            return
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                   fm.elidedText(text, Qt.TextElideMode.ElideRight, int(rect.width())))

    def _male_taste(self, p, rect, a):
        funktion = a.get("funktion")
        aktiv = bool(a.get("aktiv"))
        farbe = handy_farbe(a.get("farbe"))
        text_farbe = "#e6edf3"
        if funktion == "Blackout":
            p.setBrush(QColor("#da3633" if aktiv else "#050607"))
            p.setPen(QPen(QColor("#da3633"), 1.6))
            text_farbe = "#ffffff" if aktiv else "#ff5b55"
        elif funktion == "LaserEstop":
            g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            g.setColorAt(0, QColor("#b3312e"))
            g.setColorAt(1, QColor("#8e2421"))
            p.setBrush(g)
            p.setPen(QPen(QColor("#f0625d"), 1))
            text_farbe = "#ffffff"
        elif aktiv and farbe is not None:
            p.setBrush(farbe[0])
            p.setPen(QPen(farbe[0].lighter(140), 1))
            text_farbe = farbe[1].name()
        else:
            g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            g.setColorAt(0, QColor("#2b323c"))
            g.setColorAt(1, QColor("#1f252d"))
            p.setBrush(g)
            p.setPen(QPen(QColor("#3a424d"), 1))
        p.drawRoundedRect(rect, 6, 6)
        innen = rect.adjusted(3, 2, -3, -2)
        halten = a.get("bedienung") == "halten"
        streifen = funktion not in ("Blackout", "LaserEstop") and rect.height() >= 30
        if streifen:
            sf = QColor(text_farbe) if aktiv else (farbe[0] if farbe else QColor("#58a6ff"))
            p.setPen(QPen(QColor(0, 0, 0, 130), 1))
            p.setBrush(sf)
            p.drawRoundedRect(QRectF(rect.center().x() - 8, rect.top() + 4, 16, 4), 2, 2)
            innen.setTop(rect.top() + 9)
        if halten and innen.height() >= 22:
            unten = QRectF(innen.left(), innen.bottom() - 9, innen.width(), 9)
            self._text(p, unten, "halten", 7,
                       text_farbe if aktiv or funktion == "Blackout" else "#9aa4af", False)
            innen.setBottom(unten.top())
        gross = funktion == "Blackout" and rect.width() > 120
        self._text(p, innen, (a.get("beschriftung") or "").upper() if gross
                   else a.get("beschriftung"), 11 if gross else 9, text_farbe, True, 2)

    def _male_fader(self, p, rect, a):
        gm = "grand" in str(a.get("modus") or "").lower()
        akzent = QColor("#f2cc60" if gm else "#58a6ff")
        p.setBrush(QColor("#1a160b" if gm else "#11161c"))
        p.setPen(QPen(QColor("#d29922" if gm else "#30363d"), 1))
        p.drawRoundedRect(rect, 6, 6)
        try:
            anteil = max(0.0, min(1.0, float(a.get("wert", 0)) / 255.0))
        except (TypeError, ValueError):
            anteil = 0.0
        prozent = f"{round(anteil * 100)}%"
        name = a.get("beschriftung") or ""
        if rect.width() > rect.height():                 # quer
            innen = rect.adjusted(6, 0, -6, 0)
            nb = min(innen.width() * 0.34, 70.0)
            self._text(p, QRectF(innen.left(), innen.top(), nb, innen.height()),
                       name, 8, "#f2cc60" if gm else "#c3ccd5")
            self._text(p, QRectF(innen.right() - 30, innen.top(), 30, innen.height()),
                       prozent, 8, akzent.name())
            bahn = QRectF(innen.left() + nb + 6, rect.center().y() - 3,
                          max(8.0, innen.width() - nb - 44), 6)
            p.setPen(QPen(QColor("#2a3038"), 1))
            p.setBrush(QColor("#05070a"))
            p.drawRoundedRect(bahn, 3, 3)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(akzent)
            p.drawRoundedRect(QRectF(bahn.left(), bahn.top(), bahn.width() * anteil,
                                     bahn.height()), 3, 3)
            gx = bahn.left() + bahn.width() * anteil
            p.setBrush(QColor("#c9d1d9"))
            p.setPen(QPen(QColor("#ffffff"), 1))
            p.drawRoundedRect(QRectF(gx - 4, rect.center().y() - 9, 8, 18), 2, 2)
            return
        self._text(p, QRectF(rect.left(), rect.top() + 2, rect.width(), 12),
                   prozent, 8, akzent.name())
        self._text(p, QRectF(rect.left() + 2, rect.bottom() - 13, rect.width() - 4, 12),
                   name, 8, "#f2cc60" if gm else "#c3ccd5")
        bahn = QRectF(rect.center().x() - 3, rect.top() + 20, 6,
                      max(6.0, rect.height() - 40))
        p.setPen(QPen(QColor("#2a3038"), 1))
        p.setBrush(QColor("#05070a"))
        p.drawRoundedRect(bahn, 3, 3)
        hoch = bahn.height() * anteil
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(akzent)
        p.drawRoundedRect(QRectF(bahn.left(), bahn.bottom() - hoch, bahn.width(), hoch), 3, 3)
        gy = bahn.bottom() - hoch
        p.setBrush(QColor("#c9d1d9"))
        p.setPen(QPen(QColor("#ffffff"), 1))
        p.drawRoundedRect(QRectF(rect.center().x() - 11, gy - 4, 22, 8), 2, 2)

    def _male_cueliste(self, p, rect, a):
        p.setBrush(QColor("#111820"))
        p.setPen(QPen(QColor("#2b5d9e"), 1))
        p.drawRoundedRect(rect, 6, 6)
        innen = rect.adjusted(5, 4, -5, -5)
        kn_h = max(18.0, min(innen.height() * 0.5, 44.0))
        oben = QRectF(innen.left(), innen.top(), innen.width(), innen.height() - kn_h - 4)
        liste = a.get("liste")
        try:
            cue_nr = int(a.get("cue_index", -1))
        except (TypeError, ValueError):
            cue_nr = -1
        laeuft = cue_nr >= 0
        if oben.height() >= 12:
            zeile1 = QRectF(oben.left(), oben.top(), oben.width(), min(11.0, oben.height()))
            kopf = (liste or a.get("beschriftung") or "Cueliste")
            kopf += (" · läuft" if laeuft else " · bereit") if liste else " · keine Liste"
            p.setFont(_schrift(7, False))
            p.setPen(QColor("#8b949e"))
            p.drawText(zeile1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(p.font()).elidedText(
                           kopf.upper(), Qt.TextElideMode.ElideRight, int(zeile1.width() - 40)))
            if a.get("anzahl"):
                p.drawText(zeile1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                           f"{max(0, cue_nr + 1)} / {a.get('anzahl')}")
            if oben.height() >= 26:
                cue = a.get("cue")
                jetzt = a.get("beschriftung") or "Cueliste"
                if isinstance(cue, dict):
                    jetzt = f"{cue.get('nummer', 0):g}  {cue.get('name') or 'Cue'}"
                p.setFont(_schrift(11))
                p.setPen(QColor("#ffffff"))
                zeile2 = QRectF(oben.left(), zeile1.bottom() + 1, oben.width(), 14)
                p.drawText(zeile2, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                           QFontMetrics(p.font()).elidedText(
                               jetzt, Qt.TextElideMode.ElideRight, int(zeile2.width())))
                danach = a.get("naechste")
                if isinstance(danach, dict) and oben.height() >= 40:
                    p.setFont(_schrift(8, False))
                    p.setPen(QColor("#9aa4af"))
                    zeile3 = QRectF(oben.left(), zeile2.bottom() + 1, oben.width(), 11)
                    p.drawText(
                        zeile3, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                        QFontMetrics(p.font()).elidedText(
                            f"danach: {danach.get('nummer', 0):g} · "
                            f"{danach.get('name') or 'Cue'}",
                            Qt.TextElideMode.ElideRight, int(zeile3.width())))
        # GO (doppelt breit) / BACK / STOP
        y = innen.bottom() - kn_h
        teil = (innen.width() - 8) / 4.0
        knoepfe = [("GO", innen.left(), 2 * teil, "#2f81f7", "#1a5fd0", "#79b8ff"),
                   ("BACK", innen.left() + 2 * teil + 4, teil, "#2b323c", "#1f252d", "#3a424d"),
                   ("STOP", innen.left() + 3 * teil + 8, teil, "#b3312e", "#8e2421", "#f0625d")]
        for text, x, b, f1, f2, rand in knoepfe:
            r = QRectF(x, y, b, kn_h)
            g = QLinearGradient(r.topLeft(), r.bottomLeft())
            g.setColorAt(0, QColor(f1))
            g.setColorAt(1, QColor(f2))
            p.setBrush(g)
            p.setPen(QPen(QColor(rand), 1))
            p.drawRoundedRect(r, 5, 5)
            self._text(p, r, text, 12 if text == "GO" else 8, "#ffffff")

    def _male_fuss(self, p, handy, feld):
        """Master + Blackout — am Handy fest unten. Hier nur angedeutet."""
        y = handy.bottom() - self.RAND - self.FUSS + 2
        p.setPen(QPen(QColor("#30363d"), 1))
        p.drawLine(QPointF(handy.left() + 6, y - 3), QPointF(handy.right() - 6, y - 3))
        hoch = self.FUSS - 4
        breit_gm = (feld.width() - 6) * 0.6
        gm = QRectF(feld.left(), y, breit_gm, hoch)
        bo = QRectF(gm.right() + 6, y, feld.width() - breit_gm - 6, hoch)
        p.setOpacity(0.75)
        p.setBrush(QColor("#1a160b"))
        p.setPen(QPen(QColor("#d29922"), 1))
        p.drawRoundedRect(gm, 6, 6)
        self._text(p, QRectF(gm.left() + 6, gm.top(), 40, gm.height()), "Master", 8, "#f2cc60")
        bahn = QRectF(gm.left() + 52, gm.center().y() - 3, max(8.0, gm.width() - 62), 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#d29922"))
        p.drawRoundedRect(bahn, 3, 3)
        p.setBrush(QColor("#050607"))
        p.setPen(QPen(QColor("#da3633"), 1.6))
        p.drawRoundedRect(bo, 6, 6)
        self._text(p, bo, "BLACKOUT", 9, "#ff5b55")
        p.setOpacity(1.0)


class HandyKonsolenLeiste(QWidget):
    """Die Seitenleiste: Verbindungsblock, Reiter der Seiten, Raster, Knoepfe."""

    verbinden_angefragt = Signal()

    BREITE = 320

    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self._canvas_ref = canvas
        self._bearbeiten = False
        self._baut = False
        self._signatur = None
        self._meldung_bis = 0
        self.setObjectName("handy_konsolen_leiste")
        self.setMinimumWidth(300)
        self.setMaximumWidth(340)

        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        rolle = QScrollArea()
        rolle.setWidgetResizable(True)
        rolle.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rolle.setStyleSheet("QScrollArea { border:none; background:#0d1117; }")
        aussen.addWidget(rolle)
        inhalt = QWidget()
        inhalt.setStyleSheet("background:#0d1117; border:none;")
        rolle.setWidget(inhalt)
        lay = QVBoxLayout(inhalt)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(4)

        # ── Verbindung ───────────────────────────────────────────────────────
        zeile = QHBoxLayout()
        zeile.setSpacing(6)
        self._schalter = QPushButton("Handy-Konsole: aus")
        self._schalter.setObjectName("handy_schalter")
        self._schalter.setCheckable(True)
        self._schalter.setFixedHeight(TREFFER)
        self._schalter.setToolTip(
            "Schaltet die Handy-Konsole ein oder aus — dieselbe Einstellung wie "
            "im Dialog „Web-Remote: Verbindung & Token“.\n"
            "Aus: verbundene Handys werden gesperrt, gehaltene Tasten losgelassen.")
        self._schalter.setStyleSheet("""
            QPushButton { background:#21262d; color:#8b949e; border:1px solid #30363d;
                          border-radius:6px; font-size:11px; font-weight:bold; padding:0 8px;
                          min-height:34px; max-height:34px; }
            QPushButton:checked { background:#12351d; color:#7ee787; border-color:#2ea043; }
            QPushButton:hover { border-color:#58a6ff; }
        """)
        self._schalter.toggled.connect(self._schalter_umgelegt)
        zeile.addWidget(self._schalter, 1)
        self._btn_verbinden = QPushButton("Verbinden…")
        self._btn_verbinden.setObjectName("handy_verbinden")
        self._btn_verbinden.setFixedHeight(TREFFER)
        self._btn_verbinden.setToolTip(
            "Öffnet „Web-Remote: Verbindung & Token“ mit dem Link und dem "
            "Schlüssel fürs Handy.")
        self._btn_verbinden.setStyleSheet(_KNOPF_CSS)
        self._btn_verbinden.clicked.connect(self.verbinden_angefragt.emit)
        zeile.addWidget(self._btn_verbinden)
        lay.addLayout(zeile)
        # Platz fuer den QR-Code des Handy-Links (eigener Folgebaustein): er
        # kommt in diesen Behaelter, zwischen Schalter und Zustand.
        self._qr_platz = QWidget()
        self._qr_platz.setObjectName("handy_qr_platz")
        self._qr_platz.setVisible(False)
        lay.addWidget(self._qr_platz)
        self._lbl_zustand = QLabel("aus")
        self._lbl_zustand.setObjectName("handy_zustand")
        self._lbl_zustand.setStyleSheet("color:#8b949e; font-size:10px;")
        lay.addWidget(self._lbl_zustand)

        # ── Seiten ───────────────────────────────────────────────────────────
        zeile = QHBoxLayout()
        zeile.setSpacing(4)
        self._reiter = _Reiter()
        self._reiter.setObjectName("handy_reiter")
        self._reiter.setExpanding(False)
        self._reiter.setDrawBase(False)
        self._reiter.setUsesScrollButtons(True)
        self._reiter.setElideMode(Qt.TextElideMode.ElideNone)
        self._reiter.setStyleSheet("""
            QTabBar::tab { background:#161b22; color:#8b949e; border:1px solid #30363d;
                           border-bottom:3px solid transparent; border-radius:5px;
                           padding:0 10px; margin-right:3px; min-width:40px;
                           font-size:11px; font-weight:bold; }
            QTabBar::tab:selected { color:#58a6ff; border-bottom:3px solid #58a6ff;
                                    background:#1b2330; }
            QTabBar QToolButton { background:#21262d; border:1px solid #30363d; }
        """)
        self._reiter.setToolTip("Seiten der Handy-Konsole.\nIm Bearbeiten-Modus: "
                                "Doppelklick benennt um, Ziehen ändert die Reihenfolge.")
        self._reiter.currentChanged.connect(self._reiter_gewaehlt)
        self._reiter.tabBarDoubleClicked.connect(self._reiter_doppelklick)
        self._reiter.reihenfolge_geaendert.connect(self.seiten_ordnen)
        self._reiter.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._reiter.customContextMenuRequested.connect(self._reiter_menue)
        zeile.addWidget(self._reiter, 1)
        self._btn_seite_neu = QPushButton("+")
        self._btn_seite_neu.setObjectName("handy_seite_neu")
        self._btn_seite_neu.setFixedSize(TREFFER, TREFFER)
        self._btn_seite_neu.setStyleSheet(_KNOPF_CSS + "QPushButton { font-size:16px; padding:0; }")
        self._btn_seite_neu.clicked.connect(self.seite_hinzufuegen)
        zeile.addWidget(self._btn_seite_neu)
        self._btn_seite_weg = QPushButton("−")
        self._btn_seite_weg.setObjectName("handy_seite_weg")
        self._btn_seite_weg.setFixedSize(TREFFER, TREFFER)
        self._btn_seite_weg.setStyleSheet(
            _KNOPF_CSS + "QPushButton { font-size:16px; padding:0; color:#f85149; }")
        self._btn_seite_weg.clicked.connect(self._seite_loeschen_geklickt)
        zeile.addWidget(self._btn_seite_weg)
        lay.addLayout(zeile)

        # ── Raster ───────────────────────────────────────────────────────────
        self.raster = HandyRaster(self)
        lay.addWidget(self.raster, 1)

        # ── Knoepfe ──────────────────────────────────────────────────────────
        zeile = QHBoxLayout()
        zeile.setSpacing(6)
        self._btn_fuellen = QPushButton("Automatisch füllen")
        self._btn_fuellen.setObjectName("handy_fuellen")
        self._btn_fuellen.setFixedHeight(TREFFER)
        self._btn_fuellen.setToolTip(
            "Legt alle fernbedienbaren Elemente (Tasten, Fader, Cuelisten) "
            "automatisch auf die Handy-Seiten.\nErsetzt die bisherigen Seiten "
            "(nach Rückfrage). Rückgängig mit Strg+Z.")
        self._btn_fuellen.setStyleSheet(
            _KNOPF_CSS + "QPushButton { color:#7ee787; }")
        self._btn_fuellen.clicked.connect(self.automatisch_fuellen)
        zeile.addWidget(self._btn_fuellen, 1)
        self._btn_leeren = QPushButton("Alles leeren")
        self._btn_leeren.setObjectName("handy_leeren")
        self._btn_leeren.setFixedHeight(TREFFER)
        self._btn_leeren.setToolTip("Entfernt alle Handy-Seiten (nach Rückfrage). "
                                    "Die Elemente der Konsole bleiben.")
        self._btn_leeren.setStyleSheet(_KNOPF_CSS + "QPushButton { color:#f85149; }")
        self._btn_leeren.clicked.connect(self.alles_leeren)
        zeile.addWidget(self._btn_leeren)
        lay.addLayout(zeile)

        self._lbl_hinweis = QLabel()
        self._lbl_hinweis.setObjectName("handy_hinweis")
        self._lbl_hinweis.setWordWrap(True)
        self._lbl_hinweis.setMinimumHeight(26)
        self._lbl_hinweis.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self._lbl_hinweis)

        self._takt = QTimer(self)
        self._takt.setInterval(500)
        self._takt.timeout.connect(self._takt_schlag)

        canvas.handy_seiten_changed.connect(self.aktualisiere)
        canvas.handy_seite_gewaehlt.connect(self._seite_von_aussen)
        canvas.handy_ablageziel_setzen(self)
        self.aktualisiere()
        self._verbindung_zeigen()

    # ── Grundlagen ───────────────────────────────────────────────────────────

    def canvas(self):
        c = self._canvas_ref
        if c is None:
            return None
        try:
            import shiboken6
            if not shiboken6.isValid(c):
                return None
        except Exception:
            pass
        return c

    def bearbeiten(self) -> bool:
        return self._bearbeiten

    def set_edit_mode(self, an: bool) -> None:
        """Nur im Bearbeiten-Modus bedienbar — sonst Vorschau."""
        self._bearbeiten = bool(an)
        self._reiter.setMovable(self._bearbeiten)
        for knopf in (self._btn_seite_neu, self._btn_seite_weg,
                      self._btn_fuellen, self._btn_leeren):
            knopf.setEnabled(self._bearbeiten)
        if not self._bearbeiten:
            self.raster.waehle(None)
            self.raster.zeige_fremd(None)
        self.aktualisiere()

    def showEvent(self, event):
        super().showEvent(event)
        self._takt.start()
        self.aktualisiere()
        self._verbindung_zeigen()

    def hideEvent(self, event):
        self._takt.stop()
        self.raster.zeige_fremd(None)
        super().hideEvent(event)

    def _takt_schlag(self):
        """Abgefragt statt verdrahtet (wie die Rueckmeldung ans Handy): eine
        umbenannte Taste, eine neue Farbe, ein bewegter Fader oder ein im
        Dialog umgelegter Schalter erscheinen so ohne eigene Haken."""
        try:
            self._verbindung_zeigen()
            sig = self._signatur_jetzt()
            if sig != self._signatur:
                self.aktualisiere()
            if self._meldung_bis:
                self._meldung_bis -= 1
                if self._meldung_bis <= 0:
                    self._hinweis_zeigen()
        except Exception as e:
            print(f"[vc_handy_leiste] ERROR: Takt: {e}")

    def _signatur_jetzt(self):
        c = self.canvas()
        if c is None:
            return None
        abschnitt = c.handy_seiten()
        seiten = abschnitt["seiten"]
        zustand = []
        if seiten:
            for e in seiten[c.handy_seite_nr()]["eintraege"]:
                a = c.handy_auskunft(c.widget_mit_kennung(e["widget"]))
                zustand.append(None if a is None else (
                    a.get("typ"), a.get("beschriftung"), a.get("farbe"), a.get("aktiv"),
                    a.get("wert"), a.get("funktion"), a.get("bedienung"),
                    a.get("liste"), a.get("cue_index"), a.get("anzahl")))
        return (repr(abschnitt), c.handy_seite_nr(), tuple(zustand))

    # ── Anzeige ──────────────────────────────────────────────────────────────

    def aktualisiere(self) -> None:
        """Reiter, Raster und Hinweis aus dem Stand der Konsole neu aufbauen."""
        c = self.canvas()
        if c is None:
            return
        seiten = c.handy_seiten()["seiten"]
        nr = c.handy_seite_nr()
        r = self._reiter
        namen = [s["name"] for s in seiten]
        if r._maus_unten and r.umgestellt():
            # Mitten im Ziehen eines Reiters: nicht neu aufbauen (das risse den
            # Griff ab). Beim Loslassen kommt die Reihenfolge und danach der Aufbau.
            self.raster.update()
            return
        if [r.tabText(i) for i in range(r.count())] == namen:
            # Namen und Reihenfolge stimmen (z. B. gerade per Ziehen umgestellt):
            # nur neu durchzaehlen — kein Abbau unter einer laufenden Bewegung.
            for i in range(r.count()):
                r.setTabData(i, i)
        else:
            self._baut = r._baut = True
            try:
                while r.count():
                    r.removeTab(0)
                for i, name in enumerate(namen):
                    r.addTab(name)
                    r.setTabData(i, i)
            finally:
                self._baut = r._baut = False
        if seiten and r.currentIndex() != nr:
            self._baut = True
            try:
                r.setCurrentIndex(nr)
            finally:
                self._baut = False
        self._btn_seite_neu.setEnabled(self._bearbeiten and len(seiten) < hs.MAX_SEITEN)
        self._btn_seite_neu.setToolTip(
            "Neue Handy-Seite hinzufügen" if len(seiten) < hs.MAX_SEITEN
            else f"Mehr als {hs.MAX_SEITEN} Seiten gibt es nicht.")
        self._btn_seite_weg.setEnabled(self._bearbeiten and bool(seiten))
        self._btn_seite_weg.setToolTip("Diese Handy-Seite löschen (die Elemente der "
                                       "Konsole bleiben)")
        self._btn_leeren.setEnabled(self._bearbeiten and bool(seiten))
        self._signatur = self._signatur_jetzt()
        if not self._meldung_bis:
            self._hinweis_zeigen()
        self.raster.update()

    def _hinweis_zeigen(self) -> None:
        self._meldung_bis = 0
        c = self.canvas()
        if c is None:
            return
        abschnitt = c.handy_seiten()
        seiten = abschnitt["seiten"]
        if seiten:
            nr = c.handy_seite_nr()
            n = len(seiten[nr]["eintraege"])
            frei = hs.freie_zellen(abschnitt, nr)
            kopf = (f"Raster {hs.SPALTEN} × {hs.ZEILEN} · {n} "
                    f"{'Verknüpfung' if n == 1 else 'Verknüpfungen'} · "
                    f"{frei} {'Feld' if frei == 1 else 'Felder'} frei")
        else:
            kopf = f"Raster {hs.SPALTEN} × {hs.ZEILEN} · noch keine Seite"
        if self._bearbeiten:
            text = kopf + "<br>Ziehen oder Rechtsklick → „Auf Handy-Konsole legen“"
        else:
            text = kopf + "<br>Vorschau — zum Ändern „Bearbeiten“ einschalten."
        self._lbl_hinweis.setStyleSheet("color:#8b949e; font-size:10px;")
        self._lbl_hinweis.setText(text)

    def melde(self, text: str) -> None:
        """Kurze Rueckmeldung (z. B. warum ein Ablegen nicht ging)."""
        self._lbl_hinweis.setStyleSheet("color:#ffa198; font-size:10px; font-weight:bold;")
        self._lbl_hinweis.setText(text)
        self._meldung_bis = 8           # Takte zu 500 ms

    def letzte_meldung(self) -> str:
        return self._lbl_hinweis.text() if self._meldung_bis else ""

    # ── Verbindung ───────────────────────────────────────────────────────────

    def _verbindung_lesen(self) -> tuple:
        """(eingeschaltet, Server laeuft, Zahl der verbundenen Handys)."""
        an, laeuft, anzahl = False, False, 0
        try:
            from src.web import remote_settings
            an = bool(remote_settings.is_vc_remote_enabled())
        except Exception as e:
            print(f"[vc_handy_leiste] ERROR: Einstellung nicht lesbar: {e}")
        try:
            from src.web import vc_remote
            anzahl = int(vc_remote.zuschauer())
        except Exception:
            anzahl = 0
        try:
            from src.web import app as web_app
            laeuft = bool(web_app.is_running())
        except Exception:
            laeuft = False
        return an, laeuft, anzahl

    @staticmethod
    def zustand_text(an: bool, laeuft: bool, anzahl: int) -> str:
        if not an:
            return "aus"
        if not laeuft:
            return "an · Web-Interface läuft nicht (Ausgabe → Web-Interface)"
        if anzahl == 1:
            return "an · 1 Handy verbunden"
        return f"an · {anzahl} Handys verbunden"

    def _verbindung_zeigen(self) -> None:
        an, laeuft, anzahl = self._verbindung_lesen()
        if self._schalter.isChecked() != an:
            self._schalter.blockSignals(True)
            self._schalter.setChecked(an)
            self._schalter.blockSignals(False)
        self._schalter.setText("Handy-Konsole: an" if an else "Handy-Konsole: aus")
        self._lbl_zustand.setText(self.zustand_text(an, laeuft, anzahl))
        farbe = "#8b949e"
        if an:
            farbe = "#7ee787" if (laeuft and anzahl) else ("#d29922" if not laeuft else "#c3ccd5")
        self._lbl_zustand.setStyleSheet(f"color:{farbe}; font-size:10px;")

    def _schalter_umgelegt(self, an: bool) -> None:
        # Wirkt sofort am laufenden Server (er liest die Einstellung bei jedem
        # Aufruf). Beim Ausschalten: gehaltene Tasten loslassen, Handys sperren.
        try:
            from src.web import remote_settings, vc_remote
            remote_settings.set_vc_remote_enabled(bool(an))
            vc_remote.einstellung_geaendert()
        except Exception as e:
            print(f"[vc_handy_leiste] ERROR: Handy-Konsole umschalten: {e}")
            self.melde(f"Umschalten fehlgeschlagen: {e}")
        self._verbindung_zeigen()

    # ── Seiten ───────────────────────────────────────────────────────────────

    def _reiter_gewaehlt(self, nr: int) -> None:
        if self._baut or nr < 0 or self._reiter.umgestellt():
            return      # umgestellt: die gezeigte Seite wandert beim Uebernehmen mit
        c = self.canvas()
        if c is not None:
            c.setze_handy_seite_nr(nr)
            self.raster.waehle(None)
            self.aktualisiere()

    def _seite_von_aussen(self, _nr: int) -> None:
        self.aktualisiere()

    def seite_hinzufuegen(self) -> int | None:
        c = self.canvas()
        if c is None or not self._bearbeiten:
            return None
        nr = c.handy_seite_hinzufuegen()
        if nr is None:
            self.melde(f"Mehr als {hs.MAX_SEITEN} Seiten gibt es nicht.")
        return nr

    def _reiter_doppelklick(self, nr: int) -> None:
        if nr >= 0:
            self.seite_umbenennen(nr)

    def seite_umbenennen(self, nr: int, name=None) -> bool:
        """Seite umbenennen; ohne ``name`` wird gefragt."""
        c = self.canvas()
        if c is None or not self._bearbeiten:
            return False
        seiten = c.handy_seiten()["seiten"]
        if not 0 <= nr < len(seiten):
            return False
        if name is None:
            name, ok = QInputDialog.getText(
                self, "Handy-Seite umbenennen",
                f"Name der Seite (höchstens {hs.MAX_NAME} Zeichen):",
                text=seiten[nr]["name"])
            if not ok:
                return False
        return c.handy_seite_umbenennen(nr, name)

    def _seite_loeschen_geklickt(self) -> None:
        c = self.canvas()
        if c is not None:
            self.seite_loeschen(c.handy_seite_nr())

    def seite_loeschen(self, nr: int) -> bool:
        """Seite loeschen — mit Rueckfrage, wenn etwas darauf liegt."""
        c = self.canvas()
        if c is None or not self._bearbeiten:
            return False
        seiten = c.handy_seiten()["seiten"]
        if not 0 <= nr < len(seiten):
            return False
        n = len(seiten[nr]["eintraege"])
        if n and QMessageBox.question(
                self, "Handy-Seite löschen",
                f"„{seiten[nr]['name']}“ mit {n} "
                f"{'Verknüpfung' if n == 1 else 'Verknüpfungen'} löschen?\n\n"
                "Die Elemente in der Konsole bleiben. (Rückgängig mit Strg+Z)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return False
        return c.handy_seite_loeschen(nr)

    def seiten_ordnen(self, reihenfolge) -> bool:
        """Neue Reihenfolge der Seiten: ``reihenfolge[i]`` = bisherige Nummer
        der Seite, die danach an Stelle i steht."""
        c = self.canvas()
        if c is None or not self._bearbeiten:
            self.aktualisiere()         # Reiter zurueck auf den Stand der Konsole
            return False
        ok = c.handy_seiten_ordnen(list(reihenfolge))
        self.aktualisiere()
        return ok

    def _reiter_menue(self, pos) -> None:
        nr = self._reiter.tabAt(pos)
        if nr < 0 or not self._bearbeiten:
            return
        menu = QMenu(self)
        menu.addAction("Umbenennen…").triggered.connect(lambda: self.seite_umbenennen(nr))
        menu.addAction("Seite löschen").triggered.connect(lambda: self.seite_loeschen(nr))
        menu.exec(self._reiter.mapToGlobal(pos))
        menu.deleteLater()

    # ── Knoepfe ──────────────────────────────────────────────────────────────

    def automatisch_fuellen(self) -> None:
        """Alle fernbedienbaren Elemente automatisch anordnen — ersetzt die
        bisherigen Seiten (nach Rueckfrage). Ein Rueckgaengig-Schritt."""
        c = self.canvas()
        if c is None or not self._bearbeiten:
            return
        try:
            if c.handy_seiten()["seiten"] and QMessageBox.question(
                    self, "Handy-Konsole automatisch füllen",
                    "Die bisherigen Handy-Seiten werden durch eine neue, "
                    "automatische Anordnung ersetzt.\n\nFortfahren? "
                    "(Rückgängig mit Strg+Z)",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            anzahl, seiten = c.handy_konsole_automatisch_fuellen()
        except Exception as e:
            print(f"[vc_handy_leiste] ERROR: Handy-Konsole füllen: {e}")
            QMessageBox.warning(self, "Handy-Konsole", str(e))
            return
        if anzahl == 0:
            QMessageBox.information(
                self, "Handy-Konsole",
                "Keine fernbedienbaren Elemente gefunden.\n"
                "Fernbedienbar sind Tasten, Fader und Cuelisten.")
            return
        c.setze_handy_seite_nr(0)
        self.melde(f"{anzahl} {'Element' if anzahl == 1 else 'Elemente'} auf "
                   f"{seiten} {'Seite' if seiten == 1 else 'Seiten'} gelegt.")
        self._lbl_hinweis.setStyleSheet("color:#7ee787; font-size:10px; font-weight:bold;")

    def alles_leeren(self) -> bool:
        c = self.canvas()
        if c is None or not self._bearbeiten:
            return False
        abschnitt = c.handy_seiten()
        if not abschnitt["seiten"]:
            return False
        n = hs.anzahl_eintraege(abschnitt)
        if QMessageBox.question(
                self, "Handy-Konsole leeren",
                f"Alle {len(abschnitt['seiten'])} Handy-Seite(n) mit {n} "
                f"Verknüpfung(en) entfernen?\n\nDie Elemente in der Konsole "
                "bleiben. (Rückgängig mit Strg+Z)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return False
        return c.handy_alles_leeren()

    # ── Ablageziel beim Ziehen aus der grossen Konsole ───────────────────────

    def _raster_pos(self, global_pos):
        """Position im Raster — oder None, wenn der Zeiger nicht darueber ist."""
        if not self._bearbeiten or not self.isVisible() or not self.raster.isVisible():
            return None
        pos = self.raster.mapFromGlobal(global_pos)
        return pos if self.raster.rect().contains(pos) else None

    def zieh_vorschau(self, widget, global_pos) -> bool:
        c = self.canvas()
        pos = self._raster_pos(global_pos)
        if c is None or pos is None:
            self.raster.zeige_fremd(None)
            return False
        s, z = self.raster.zelle_bei(pos)
        ok, grund = c.handy_ablegbar(widget)
        if not ok:
            self.raster.zeige_fremd((s, z, 1, 1, False))
            self.melde(grund)
            return True
        seiten = c.handy_seiten()["seiten"]
        if not seiten:
            b, h = hs.standard_groesse(c.handy_auskunft(widget))
            self.raster.zeige_fremd((max(0, min(hs.SPALTEN - b, s)),
                                     max(0, min(hs.ZEILEN - h, z)), b, h, True))
            return True
        self.raster.zeige_fremd(c.handy_zielfeld(widget, c.handy_seite_nr(), s, z))
        return True

    def zieh_ablegen(self, widget, global_pos) -> bool:
        c = self.canvas()
        pos = self._raster_pos(global_pos)
        if c is None or pos is None:
            return False
        s, z = self.raster.zelle_bei(pos)
        ok, text = c.handy_ablegen(widget, c.handy_seite_nr(), s, z)
        if ok:
            self.raster.waehle(widget.widget_id)
            self._hinweis_zeigen()
        else:
            self.melde(text)
        return True

    def zieh_ende(self) -> None:
        self.raster.zeige_fremd(None)
