"""LAS-35: Sperrzonen planen — NUR ANZEIGE.

Ein Fenster statt des frueheren Zahlenfeld-Dialogs:

* **Draufsicht** (Buehne von oben) und **Seitenansicht** (Hoehe). Zonen werden
  mit grossen Griffen gezogen, aufgezogen, verschoben und gedreht; eine neue
  Zone entsteht durch Aufziehen in der Draufsicht oder aus einer Vorlage.
* Links die Zonenliste mit Ampel, unten die Massleiste (Zahlenfelder der
  gewaehlten Zone als Feineingabe), rechts je Laser eine Karte mit den
  Randwinkeln und ihrer Herkunft — oder der Einmess-Assistent.
* Der vom Laser erreichte Teil einer Zone ist in beiden Ansichten schraffiert.
  Ob schraffiert wird, entscheidet ``pruefe_laser`` aus
  ``core/laser/sperrzonen.py``; der Umriss kommt aus derselben Rechnung
  (``erreichter_teil``). Die Zeichnung zeigt nie „frei", wenn die Rechnung
  „erreicht" sagt.

Nichts hier fasst die DMX-Ausgabe an. Jede Aenderung landet in
``state.sperrzonen`` und meldet ``sperrzonen_changed`` (das 3D zeichnet mit).
Einschalten kann einen Laser allein der Einmess-Assistent, nach ausdruecklicher
Bestaetigung und ueber den Programmer (``core/laser/feld_einmessen.py``).
"""
from __future__ import annotations

import html
import math
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
)
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSizePolicy,
    QStackedWidget, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from src.core.laser import sperrzonen as S
from src.core.laser import sperrzonen_merker as M
from src.core.laser.sperrzonen import LaserFeld, Sperrzone
from src.ui.visualizer import sperrzonen_ui as UI
from src.ui.visualizer.sperrzonen_ui import _spin, melde_aenderung

#: Raster zum Einrasten (Meter) und beim Drehen (Grad).
RASTER_M = 0.25
RASTER_GRAD = 5.0
#: Trefferflaeche eines Griffs (Pixel, Durchmesser) — fingertauglich.
GRIFF_PX = 40
#: Abstand des Dreh-Griffs von der Zonenkante (Pixel).
DREH_ABSTAND_PX = 34
#: Kleinste Kante einer aufgezogenen Zone (Meter); darunter war es ein Tipp.
NEU_MIN_M = 0.25
#: Hoehe einer aufgezogenen Zone (Meter).
NEU_HOEHE_M = 3.0
UNDO_TIEFE = 100
#: Aenderungen mit demselben Schluessel innerhalb dieser Zeit sind EIN Schritt.
_UNDO_BUENDEL_S = 1.0

_ROLLE_ID = Qt.ItemDataRole.UserRole
_ROLLE_MASSE = Qt.ItemDataRole.UserRole + 1
_ROLLE_AMPEL = Qt.ItemDataRole.UserRole + 2
_ROLLE_STATUS = Qt.ItemDataRole.UserRole + 3

_AMPEL_FARBE = {S.STATUS_ERREICHT: "#f0c000", S.STATUS_FREI: "#7ee08f",
                S.STATUS_NICHT_PRUEFBAR: "#f0c000", S.STATUS_KEIN_LASER: "#8b949e"}

# (lx, lz) = Vorzeichen des Griffs in Zonen-Koordinaten; lz = -1 ist die Kante
# zur Buehne hin (bei ungedrehter Zone oben im Bild).
_GRIFFE_DRAUF = {
    "nw": (-1, -1), "n": (0, -1), "no": (1, -1), "w": (-1, 0), "o": (1, 0),
    "sw": (-1, 1), "s": (0, 1), "so": (1, 1),
}


def _m(zahl: float, stellen: int = 2) -> str:
    return f"{float(zahl):.{stellen}f}".replace(".", ",")


def _grad(zahl) -> str:
    return f"{float(zahl):g}".replace(".", ",") + "°"


def raste(wert: float, an: bool, raster: float = RASTER_M) -> float:
    return round(float(wert) / raster) * raster if an else float(wert)


def buehnen_umrisse(state) -> list:
    """Die Buehnenelemente der aktiven 3D-Buehne als Umrisse:
    ``[{"name", "typ", "drauf": [(x, z)…], "seite": [(z, y)…]}]``. Ohne
    Buehne (oder bei jedem Fehler) leer — der Planer zeichnet dann nur das
    Raster."""
    name = getattr(state, "active_stage_name", None)
    if name is None:
        return []
    try:
        from src.core.stage.stage_definition import resolve_active_stage
        buehne, _art, _n = resolve_active_stage(name)
        aus = []
        for el in buehne.elements:
            c, s = math.cos(-el.rotation), math.sin(-el.rotation)
            ecken = []
            for lx, lz in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                ax, az = lx * el.w / 2.0, lz * el.d / 2.0
                ecken.append((el.x + ax * c + az * s, el.z - ax * s + az * c))
            zs = [p[1] for p in ecken]
            y0, y1 = el.y - el.h / 2.0, el.y + el.h / 2.0
            aus.append({"name": el.name or "", "typ": el.type, "drauf": ecken,
                        "seite": [(min(zs), y0), (max(zs), y0),
                                  (max(zs), y1), (min(zs), y1)]})
        return aus
    except Exception as e:                               # noqa: BLE001
        print(f"[sperrzonen_planer] Bühne nicht lesbar: {e}")
        return []


def abstand_zum_umriss(x: float, z: float, umriss) -> float:
    """Waagerechter Abstand eines Punkts zum (konvexen) Umriss; 0 = darin."""
    n = len(umriss)
    if n == 0:
        return 0.0
    beste, seiten = float("inf"), set()
    for i in range(n):
        (ax, az), (bx, bz) = umriss[i], umriss[(i + 1) % n]
        dx, dz = bx - ax, bz - az
        laenge2 = dx * dx + dz * dz
        t = 0.0 if laenge2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / laenge2))
        beste = min(beste, math.hypot(x - (ax + t * dx), z - (az + t * dz)))
        kreuz = dx * (z - az) - dz * (x - ax)
        if abs(kreuz) > 1e-12:
            seiten.add(kreuz > 0)
    return 0.0 if (n >= 3 and len(seiten) <= 1) else beste


def _schraffur_pinsel() -> QBrush:
    pm = QPixmap(10, 10)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(255, 176, 0, 215), 2.6))
    for versatz in (-10, 0, 10):
        p.drawLine(QPointF(versatz, 10), QPointF(versatz + 10, 0))
    p.end()
    return QBrush(pm)


class _Zeichenflaeche(QWidget):
    """Draufsicht (``art="drauf"``: x nach rechts, z nach unten = Publikum
    unten) oder Seitenansicht (``art="seite"``: z nach rechts, Hoehe nach
    oben)."""

    def __init__(self, planer, art: str):
        super().__init__(planer)
        self._p = planer
        self.art = art
        self.setObjectName("sperrzonenDraufsicht" if art == "drauf"
                           else "sperrzonenSeitenansicht")
        self.setMinimumSize(300 if art == "drauf" else 260,
                            300 if art == "drauf" else 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(False)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._mass = 30.0           # Pixel je Meter
        self._ox = self._oy = 0.0   # Pixel-Lage des Welt-Ursprungs
        self._zug = None            # laufende Mausbewegung
        self._gummi = None          # (welt_start, welt_jetzt) beim Aufziehen
        self._schraffur = None

    # ── Welt <-> Pixel ───────────────────────────────────────────────────
    def zu_px(self, a: float, b: float) -> QPointF:
        """Draufsicht: (x, z). Seitenansicht: (z, y)."""
        if self.art == "drauf":
            return QPointF(self._ox + a * self._mass, self._oy + b * self._mass)
        return QPointF(self._ox + a * self._mass, self._oy - b * self._mass)

    def zu_welt(self, pos) -> tuple:
        a = (pos.x() - self._ox) / self._mass
        b = (pos.y() - self._oy) / self._mass
        return (a, b) if self.art == "drauf" else (a, -b)

    def einpassen(self) -> None:
        """Ausschnitt so legen, dass Zonen, Laser und Buehne zu sehen sind."""
        punkte = list(self._p.inhalt_punkte(self.art))
        if self.art == "drauf":
            punkte += [(-6.0, -1.0), (6.0, 11.0)]
        else:
            punkte += [(-1.0, 0.0), (11.0, 5.5)]
        aa, bb = [p[0] for p in punkte], [p[1] for p in punkte]
        a0, a1, b0, b1 = min(aa), max(aa), min(bb), max(bb)
        rand = 34.0
        w = max(50.0, self.width() - 2 * rand)
        h = max(50.0, self.height() - 2 * rand)
        self._mass = max(4.0, min(w / max(1.0, a1 - a0), h / max(1.0, b1 - b0), 80.0))
        self._ox = rand + (w - (a1 - a0) * self._mass) / 2 - a0 * self._mass
        if self.art == "drauf":
            self._oy = rand + (h - (b1 - b0) * self._mass) / 2 - b0 * self._mass
        else:
            self._oy = self.height() - rand - (h - (b1 - b0) * self._mass) / 2 \
                + b0 * self._mass
        self.update()

    def resizeEvent(self, ev):  # noqa: N802 (Qt-API)
        super().resizeEvent(ev)
        self.einpassen()

    # ── Griffe ───────────────────────────────────────────────────────────
    def griffe(self) -> dict:
        """Name -> Pixel-Mitte der Griffe der gewaehlten Zone."""
        zone = self._p.gewaehlte_zone()
        if zone is None or not self._p.bearbeitbar():
            return {}
        if self.art == "seite":
            return {"oben": self.zu_px(zone.z, zone.y + zone.hoehe),
                    "unten": self.zu_px(zone.z, zone.y)}
        w = math.radians(zone.dreh_y)
        c, s = math.cos(w), math.sin(w)

        def _welt(lx, lz):
            return self.zu_px(zone.x + c * lx + s * lz, zone.z - s * lx + c * lz)

        aus = {name: _welt(vx * zone.breite / 2, vz * zone.tiefe / 2)
               for name, (vx, vz) in _GRIFFE_DRAUF.items()}
        aus["mitte"] = _welt(0.0, 0.0)
        kante = _welt(0.0, -zone.tiefe / 2)
        # Richtung „aus der Zone hinaus" der buehnenseitigen Kante, in Pixeln.
        aus["dreh"] = QPointF(kante.x() - s * DREH_ABSTAND_PX,
                              kante.y() - c * DREH_ABSTAND_PX)
        return aus

    def _griff_bei(self, pos):
        beste, abstand = None, GRIFF_PX / 2.0
        for name, mitte in self.griffe().items():
            d = math.hypot(pos.x() - mitte.x(), pos.y() - mitte.y())
            if d <= abstand:
                beste, abstand = name, d
        return beste

    def _zone_bei(self, pos):
        a, b = self.zu_welt(pos)
        zonen = list(self._p.daten().zonen)
        gewaehlt = self._p.gewaehlte_zone()
        if gewaehlt in zonen:               # die gewaehlte zuerst
            zonen.remove(gewaehlt)
            zonen.append(gewaehlt)
        for zone in reversed(zonen):
            if self.art == "drauf":
                drin = S.punkt_in_zone((a, zone.y + zone.hoehe / 2, b), zone, 0.0)
            else:
                umriss = S.zonen_umriss(zone)["seite"]
                zs, ys = [p[0] for p in umriss], [p[1] for p in umriss]
                drin = min(zs) <= a <= max(zs) and min(ys) <= b <= max(ys)
            if drin:
                return zone
        return None

    # ── Maus (Touch kommt bei Qt als Maus an) ────────────────────────────
    def mousePressEvent(self, ev):  # noqa: N802 (Qt-API)
        if ev.button() != Qt.MouseButton.LeftButton or not self._p.bearbeitbar():
            return
        pos = ev.position()
        welt = self.zu_welt(pos)
        griff = self._griff_bei(pos)
        zone = self._p.gewaehlte_zone()
        if griff is None:
            zone = self._zone_bei(pos)
            if zone is not None:
                self._p.waehle(zone.id)
                griff = "mitte" if self.art == "drauf" else None
        if griff is not None and zone is not None:
            self._zug = {"griff": griff, "zid": zone.id, "start": welt,
                         "alt": Sperrzone(**zone.to_dict()), "gemerkt": False}
        elif self.art == "drauf" and zone is None:
            self._zug = {"griff": "neu", "start": welt}
            self._gummi = (welt, welt)
        self.update()

    def mouseMoveEvent(self, ev):  # noqa: N802 (Qt-API)
        zug = self._zug
        if zug is None:
            return
        welt = self.zu_welt(ev.position())
        if zug["griff"] == "neu":
            self._gummi = (zug["start"], welt)
            self.update()
            return
        zone = self._p.daten().zone(zug["zid"])
        if zone is None:
            self._zug = None
            return
        werte = self._zug_werte(zug, welt)
        if not werte:
            return
        if not zug["gemerkt"]:              # EIN Rueckgaengig-Schritt je Zug
            self._p.merke_stand()
            zug["gemerkt"] = True
        self._p.zone_setzen(zone, werte)

    def mouseReleaseEvent(self, ev):  # noqa: N802 (Qt-API)
        zug, self._zug = self._zug, None
        gummi, self._gummi = self._gummi, None
        if zug is not None and zug["griff"] == "neu" and gummi is not None:
            an = self._p.einrasten()
            (x0, z0), (x1, z1) = gummi
            x0, x1 = sorted((raste(x0, an), raste(x1, an)))
            z0, z1 = sorted((raste(z0, an), raste(z1, an)))
            if x1 - x0 >= NEU_MIN_M and z1 - z0 >= NEU_MIN_M:
                self._p.zone_anlegen(Sperrzone(
                    name=S.freier_name(self._p.daten(), "Zone"),
                    x=(x0 + x1) / 2, y=0.0, z=(z0 + z1) / 2,
                    breite=x1 - x0, hoehe=NEU_HOEHE_M, tiefe=z1 - z0))
        self.update()

    def mouseDoubleClickEvent(self, ev):  # noqa: N802 (Qt-API)
        if self._zone_bei(ev.position()) is not None:
            self._p.masse_eintippen()

    def _zug_werte(self, zug, welt) -> dict:
        """Neue Zonenwerte fuer die Mausposition ``welt``."""
        alt, griff, an = zug["alt"], zug["griff"], self._p.einrasten()
        if self.art == "seite":
            hoehe_y = raste(welt[1], an)
            oben = alt.y + alt.hoehe
            if griff == "oben":
                return {"hoehe": max(S.ZONE_MIN_M, hoehe_y - alt.y)}
            if griff == "unten":
                y = min(hoehe_y, oben - (RASTER_M if an else S.ZONE_MIN_M))
                return {"y": y, "hoehe": oben - y}
            return {}
        if griff == "mitte":
            return {"x": raste(alt.x + welt[0] - zug["start"][0], an),
                    "z": raste(alt.z + welt[1] - zug["start"][1], an)}
        if griff == "dreh":
            w = math.degrees(math.atan2(-(welt[0] - alt.x), -(welt[1] - alt.z)))
            w = raste(w, an, RASTER_GRAD)
            return {"dreh_y": 180.0 if w == -180.0 else w}
        vx, vz = _GRIFFE_DRAUF[griff]
        gerade = abs(alt.dreh_y / 90.0 - round(alt.dreh_y / 90.0)) < 1e-9
        if an and gerade:                   # Kante landet auf dem Raster
            welt = (raste(welt[0], True), raste(welt[1], True))
        w = math.radians(alt.dreh_y)
        c, s = math.cos(w), math.sin(w)
        dx, dz = welt[0] - alt.x, welt[1] - alt.z
        lx, lz = c * dx - s * dz, s * dx + c * dz
        kleinste = RASTER_M if an else S.ZONE_MIN_M

        def _achse(v, zeiger, alt_mass):
            if v == 0:
                return alt_mass, 0.0
            fest = -v * alt_mass / 2
            mass = max(kleinste, (zeiger - fest) * v)
            if an and not gerade:
                mass = max(kleinste, raste(mass, True))
            return mass, fest + v * mass / 2

        breite, mx = _achse(vx, lx, alt.breite)
        tiefe, mz = _achse(vz, lz, alt.tiefe)
        return {"breite": breite, "tiefe": tiefe,
                "x": alt.x + c * mx + s * mz, "z": alt.z - s * mx + c * mz}

    # ── Zeichnen ─────────────────────────────────────────────────────────
    def _polygon(self, punkte) -> QPolygonF:
        return QPolygonF([self.zu_px(a, b) for a, b in punkte])

    def paintEvent(self, _ev):  # noqa: N802 (Qt-API)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#101216"))
        self._male_raster(p)
        self._male_buehne(p)
        self._male_felder(p)
        self._male_zonen(p)
        self._male_schraffur(p)
        self._male_laser(p)
        self._male_auswahl(p)
        if self._gummi is not None:
            (x0, z0), (x1, z1) = self._gummi
            p.setPen(QPen(QColor("#ffffff"), 1.5, Qt.PenStyle.DashLine))
            p.setBrush(QColor(208, 32, 32, 60))
            p.drawRect(QRectF(self.zu_px(x0, z0), self.zu_px(x1, z1)).normalized())
        p.setPen(QColor("#6f7780"))
        f = QFont(self.font())
        f.setPixelSize(11)
        p.setFont(f)
        fuss = ("Raster 1 m · Publikum unten" if self.art == "drauf"
                else "Raster 1 m · Bühne links")
        p.drawText(self.rect().adjusted(8, 0, -8, -6),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom, fuss)
        p.end()

    def _male_raster(self, p) -> None:
        schritt = 1 if self._mass >= 9 else 5
        a0, b0 = self.zu_welt(QPointF(0, 0))
        a1, b1 = self.zu_welt(QPointF(self.width(), self.height()))
        for i in range(math.floor(min(a0, a1)), math.ceil(max(a0, a1)) + 1):
            if i % schritt:
                continue
            x = self.zu_px(i, 0).x()
            p.setPen(QColor("#343a45" if i % 5 == 0 else "#23272e"))
            p.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        for i in range(math.floor(min(b0, b1)), math.ceil(max(b0, b1)) + 1):
            if i % schritt:
                continue
            y = self.zu_px(0, i).y()
            p.setPen(QColor("#343a45" if i % 5 == 0 else "#23272e"))
            p.drawLine(QPointF(0, y), QPointF(self.width(), y))
        if self.art == "seite":
            boden = self.zu_px(0, 0).y()
            p.setPen(QPen(QColor("#8a909c"), 2))
            p.drawLine(QPointF(0, boden), QPointF(self.width(), boden))
            f = QFont(self.font())
            f.setPixelSize(10)
            p.setFont(f)
            p.setPen(QColor("#6f7780"))
            for hoehe in (0, 3, 5):
                p.drawText(QPointF(self.width() - 30, self.zu_px(0, hoehe).y() - 3),
                           f"{hoehe} m")

    def _male_buehne(self, p) -> None:
        f = QFont(self.font())
        f.setPixelSize(11)
        p.setFont(f)
        for el in self._p.buehne():
            poly = self._polygon(el[self.art])
            p.setPen(QPen(QColor("#5a606c"), 1))
            p.setBrush(QColor(44, 48, 56, 200 if self.art == "drauf" else 110))
            p.drawPolygon(poly)
            if self.art == "drauf" and el["name"]:
                p.setPen(QColor("#9aa4b0"))
                r = poly.boundingRect()
                p.drawText(r.adjusted(6, 4, -4, -4),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                           el["name"])

    def _male_felder(self, p) -> None:
        for fa in self._p.faecher():
            for teil, stil in (("aussen", Qt.PenStyle.DashLine),
                               ("innen", Qt.PenStyle.SolidLine)):
                p.setPen(QPen(QColor("#f0c000"), 1.2, stil))
                p.setBrush(QColor(240, 192, 0, 26))
                p.drawPolygon(self._polygon(fa[teil][self.art]))

    def _male_zonen(self, p) -> None:
        f = QFont(self.font())
        f.setPixelSize(12)
        f.setBold(True)
        p.setFont(f)
        gewaehlt = self._p.gewaehlte_zone()
        for zone in self._p.daten().zonen:
            poly = self._polygon(S.zonen_umriss(zone)[self.art])
            p.setPen(QPen(QColor("#ffffff" if zone is gewaehlt else "#ff5a5a"),
                          2 if zone is gewaehlt else 1.2))
            p.setBrush(QColor(208, 32, 32, 72))
            p.drawPolygon(poly)
            p.setPen(QColor("#ffd0d0"))
            r = poly.boundingRect()
            # Seitenansicht: unten links — oben sitzt der Griff der Oberkante.
            oben = r.top() + 4 if self.art == "drauf" else max(r.top() + 2, r.bottom() - 21)
            p.drawText(QRectF(r.left() + 7, oben, max(10.0, r.width() - 9), 18),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       p.fontMetrics().elidedText(
                           zone.name, Qt.TextElideMode.ElideRight,
                           int(max(10.0, r.width() - 9))))

    def _male_schraffur(self, p) -> None:
        if self._schraffur is None:
            self._schraffur = _schraffur_pinsel()
        for eintrag in self._p.schraffuren():
            poly = self._polygon(eintrag[self.art])
            p.setPen(QPen(QColor("#ffb000"), 1.4))
            p.setBrush(self._schraffur)
            p.drawPolygon(poly)

    def _male_laser(self, p) -> None:
        f = QFont(self.font())
        f.setPixelSize(11)
        p.setFont(f)
        for la in self._p.laser_lagen():
            x, y, z = la["pos"]
            m = self.zu_px(x, z) if self.art == "drauf" else self.zu_px(z, y)
            p.setPen(QPen(QColor("#c8ccd4"), 1.5))
            p.setBrush(QColor("#20242b"))
            p.drawRoundedRect(QRectF(m.x() - 11, m.y() - 8, 22, 16), 2, 2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#30ff50" if la["pruefbar"] else "#f0c000"))
            p.drawEllipse(m, 3.5, 3.5)
            p.setPen(QColor("#f0c000"))
            if self.art == "drauf":
                p.drawText(QPointF(m.x() + 17, m.y() + 4), la["text"])
            else:
                p.drawText(QPointF(m.x() - 11, m.y() + 24), f"Laser {la['fid']}")
                p.drawText(QPointF(m.x() - 11, m.y() + 38), f"{_m(y)} m")

    def _schild(self, p, mitte: QPointF, text: str) -> None:
        f = QFont(self.font())
        f.setPixelSize(12)
        f.setBold(True)
        p.setFont(f)
        breite = p.fontMetrics().horizontalAdvance(text) + 16
        r = QRectF(mitte.x() - breite / 2, mitte.y() - 11, breite, 22)
        r.moveLeft(max(2.0, min(self.width() - breite - 2.0, r.left())))
        r.moveTop(max(2.0, min(self.height() - 24.0, r.top())))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(UI.BLAU))
        p.drawRoundedRect(r, 3, 3)
        p.setPen(QColor("#ffffff"))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)

    def _male_auswahl(self, p) -> None:
        zone = self._p.gewaehlte_zone()
        griffe = self.griffe()
        if zone is None or not griffe:
            return
        blau = QColor(UI.BLAU)
        if self.art == "seite":
            for name in ("oben", "unten"):
                m = griffe[name]
                p.setPen(QPen(QColor("#ffffff"), 2))
                p.setBrush(blau)
                p.drawEllipse(m, 16, 16)
                self._pfeil(p, m, senkrecht=True)
            r = self._polygon(S.zonen_umriss(zone)["seite"]).boundingRect()
            self._schild(p, QPointF(r.right() + 56, r.center().y()),
                         f"{_m(zone.hoehe)} m hoch")
            return
        dreh, kante = griffe["dreh"], griffe["n"]
        p.setPen(QPen(blau, 2))
        p.drawLine(kante, dreh)
        for name in _GRIFFE_DRAUF:
            m = griffe[name]
            p.setPen(QPen(blau, 2.5))
            p.setBrush(QColor("#ffffff"))
            p.drawRect(QRectF(m.x() - 9, m.y() - 9, 18, 18))
        for name, zeichen in (("mitte", "✥"), ("dreh", "⟳")):
            m = griffe[name]
            p.setPen(QPen(QColor("#ffffff"), 2))
            p.setBrush(blau)
            p.drawEllipse(m, 17, 17)
            f = QFont(self.font())
            f.setPixelSize(17)
            p.setFont(f)
            p.drawText(QRectF(m.x() - 17, m.y() - 17, 34, 34),
                       Qt.AlignmentFlag.AlignCenter, zeichen)
        s, o = griffe["s"], griffe["o"]
        mi = griffe["mitte"]

        def _aussen(punkt, weite):
            dx, dy = punkt.x() - mi.x(), punkt.y() - mi.y()
            n = math.hypot(dx, dy) or 1.0
            return QPointF(punkt.x() + dx / n * weite, punkt.y() + dy / n * weite)

        self._schild(p, _aussen(s, 24), f"{_m(zone.breite)} m breit")
        self._schild(p, _aussen(o, 58), f"{_m(zone.tiefe)} m tief")

    @staticmethod
    def _pfeil(p, m: QPointF, senkrecht: bool) -> None:
        p.setPen(QPen(QColor("#ffffff"), 2))
        a, b = QPointF(m.x(), m.y() - 8), QPointF(m.x(), m.y() + 8)
        p.drawLine(a, b)
        for spitze, r in ((a, 1), (b, -1)):
            p.drawLine(spitze, QPointF(spitze.x() - 4, spitze.y() + 4 * r))
            p.drawLine(spitze, QPointF(spitze.x() + 4, spitze.y() + 4 * r))


class _ZonenZeile(QStyledItemDelegate):
    """Zwei Zeilen je Zone: Name, darunter Masse und Ampel."""

    HOEHE = 50

    def sizeHint(self, _option, _index):  # noqa: N802 (Qt-API)
        return QSize(120, self.HOEHE)

    def paint(self, p, option, index):
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(option.rect).adjusted(3, 2, -3, -2)
        gewaehlt = bool(option.state & QStyle.StateFlag.State_Selected)
        p.setPen(QPen(QColor(UI.BLAU if gewaehlt else "#3a3a3a"), 2 if gewaehlt else 1))
        p.setBrush(QColor("#0d1a2c" if gewaehlt else "#1c1c1c"))
        p.drawRoundedRect(r, 4, 4)
        farbe = QColor(_AMPEL_FARBE.get(index.data(_ROLLE_STATUS), "#8b949e"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(farbe)
        p.drawEllipse(QPointF(r.left() + 13, r.top() + 14), 5.5, 5.5)
        f = QFont(option.font)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#ffffff"))
        p.drawText(QRectF(r.left() + 26, r.top() + 3, r.width() - 32, 20),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(str(index.data() or ""),
                                              Qt.TextElideMode.ElideRight,
                                              int(r.width() - 32)))
        f = QFont(option.font)
        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(farbe)
        p.drawText(QRectF(r.left() + 26, r.top() + 23, r.width() - 32, 18),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(str(index.data(_ROLLE_AMPEL) or ""),
                                              Qt.TextElideMode.ElideRight,
                                              int(r.width() - 32)))
        p.restore()


class _LaserKarte(QFrame):
    """Ein Laser: Name, Montage, Randwinkel + Zuschlag kompakt, Herkunft."""

    def __init__(self, planer, fid: int, name: str, kennung: str):
        super().__init__(planer)
        self._p = planer
        self.fid, self.name, self.kennung = int(fid), name, kennung
        self.setProperty("rolle", "karte")
        self.setObjectName(f"sperrzonenLaserKarte{fid}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)
        self.lbl_titel = QLabel(f"<b>Laser {fid}</b> · {html.escape(name)}")
        self.lbl_titel.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_montage = QLabel("")
        self.lbl_montage.setProperty("rolle", "blass")
        self.lbl_winkel = UI.UmbruchText("")
        self.lbl_quelle = QLabel("")
        self.lbl_quelle.setProperty("rolle", "blass")
        for w in (self.lbl_titel, self.lbl_montage, self.lbl_winkel, self.lbl_quelle):
            lay.addWidget(w)
        zeile = QHBoxLayout()
        self.btn_aendern = QPushButton("ändern")
        self.btn_aendern.setCheckable(True)
        self.btn_aendern.setToolTip("Randwinkel und Zuschlag von Hand eintragen.")
        self.btn_aendern.toggled.connect(self._editor_zeigen)
        self.btn_einmessen = QPushButton("Feld einmessen…")
        self.btn_einmessen.setToolTip(
            "Die vier Randwinkel an einer Wand ausmessen (Wand und Zollstock).")
        self.btn_einmessen.clicked.connect(lambda: planer.einmessen_starten(self.fid))
        zeile.addWidget(self.btn_aendern)
        zeile.addWidget(self.btn_einmessen, stretch=1)
        lay.addLayout(zeile)
        self.btn_datenblatt = QPushButton("Winkel aus Profil / Datenblatt")
        self.btn_datenblatt.setToolTip(
            "Füllt die vier Randwinkel: aus dem Geräteprofil, wenn es einen "
            "Abstrahlwinkel nennt — sonst fragt LightOS nach dem Gesamtwinkel "
            "aus dem Datenblatt.")
        self.btn_datenblatt.clicked.connect(lambda: planer.datenblatt_klick(self.fid))
        lay.addWidget(self.btn_datenblatt)

        self.editor = QWidget()
        gitter = QGridLayout(self.editor)
        gitter.setContentsMargins(0, 4, 0, 0)
        gitter.setHorizontalSpacing(8)
        self.spins = {}
        for i, rand in enumerate(S.RAENDER):
            # -1 steht fuer „nicht angegeben" (Qt zeigt dann den Sondertext).
            sp = _spin(-1.0, S.WINKEL_MAX, -1.0, schritt=1.0, suffix=" °", stellen=1)
            sp.setSpecialValueText(UI.NICHT_ANGEGEBEN)
            sp.valueChanged.connect(lambda _v: planer.feld_geaendert(self.fid))
            titel = QLabel(rand.capitalize())
            titel.setProperty("rolle", "blass")
            gitter.addWidget(titel, (i // 2) * 2, i % 2)
            gitter.addWidget(sp, (i // 2) * 2 + 1, i % 2)
            self.spins[rand] = sp
        zs = _spin(S.ZUSCHLAG_MIN, S.ZUSCHLAG_MAX, S.ZUSCHLAG_STANDARD,
                   schritt=0.5, suffix=" °", stellen=1)
        zs.valueChanged.connect(lambda _v: planer.feld_geaendert(self.fid, nur_zuschlag=True))
        titel = QLabel(f"Zuschlag rundum (Vorgabe {S.ZUSCHLAG_STANDARD:g}°, "
                       f"mindestens {S.ZUSCHLAG_MIN:g}°)")
        titel.setProperty("rolle", "blass")
        gitter.addWidget(titel, 4, 0, 1, 2)
        gitter.addWidget(zs, 5, 0)
        self.spins["zuschlag"] = zs
        self.editor.setVisible(False)
        lay.addWidget(self.editor)

    def _editor_zeigen(self, an: bool) -> None:
        self.editor.setVisible(bool(an))
        self.btn_aendern.setText("fertig" if an else "ändern")

    def fuelle(self, feld: LaserFeld, montage: str, bearbeitbar: bool) -> None:
        """Anzeige und Zahlenfelder aus dem Feld — ohne Aenderung zu melden."""
        self.lbl_montage.setText(montage)
        if feld.vollstaendig:
            self.lbl_winkel.setText(
                " · ".join(f"{r} {_grad(getattr(feld, r))}" for r in S.RAENDER)
                + f" · Zuschlag {_grad(feld.zuschlag)}")
            self.lbl_winkel.setStyleSheet("")
        else:
            self.lbl_winkel.setText("Randwinkel fehlen — nicht prüfbar")
            self.lbl_winkel.setStyleSheet(f"color:{UI.GELB};")
        self.lbl_quelle.setText(f"Quelle: {S.quelle_text(feld)}")
        for name, sp in self.spins.items():
            wert = getattr(feld, name)
            wert = -1.0 if wert is None else float(wert)
            if abs(sp.value() - wert) > 1e-9:       # beim Tippen nicht stoeren
                sp.blockSignals(True)
                sp.setValue(wert)
                sp.blockSignals(False)
            sp.setEnabled(bearbeitbar)
        for knopf in (self.btn_aendern, self.btn_einmessen, self.btn_datenblatt):
            knopf.setEnabled(bearbeitbar)


class _Hinweis(UI.UmbruchText):
    """Die Befunde je Laser, mit Ort — im Planer statt der gelben Meldung."""

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setObjectName("sperrzonenPlanerHinweis")
        self.setStyleSheet(
            "#sperrzonenPlanerHinweis{background:#2e2600;border:1px solid #f0c000;"
            "border-radius:4px;padding:7px 9px;font-size:12px;}")


class SperrzonenPlaner(QDialog):
    """Sperrzonen und Laser-Felder der Show planen. Nur Anzeige."""

    _ZONEN_FELDER = (
        ("breite", "Breite", S.ZONE_MIN_M, 200.0),
        ("tiefe", "Tiefe", S.ZONE_MIN_M, 200.0),
        ("hoehe", "Höhe", S.ZONE_MIN_M, 50.0),
        ("x", "Mitte links/rechts", -200.0, 200.0),
        ("z", "Mitte vorn/hinten", -200.0, 200.0),
        ("y", "Unterkante", -20.0, 50.0),
    )

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self._state = state
        self._laedt = False
        self._gewaehlt = None           # id der gewaehlten Zone
        self._undo: list = []
        self._redo: list = []
        self._undo_schluessel = None
        self._undo_zeit = 0.0
        self._abgeleitet = None         # Zwischenspeicher bis zur naechsten Aenderung
        self._assistent = None
        self._laser_karten: dict = {}
        self._feld_spins: dict = {}
        self._laser_zeilen: list = []
        self.setObjectName("sperrzonenPlaner")
        self.setWindowTitle("Sperrzonen planen")
        self.setModal(False)
        self.setStyleSheet(UI.PLANER_QSS)
        self.resize(1500, 850)
        self.setMinimumSize(1080, 660)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(8)
        root.addLayout(self._baue_kopf())
        mitte = QHBoxLayout()
        mitte.setSpacing(8)
        mitte.addWidget(self._baue_links())
        mitte.addWidget(self._baue_mitte(), stretch=1)
        mitte.addWidget(self._baue_rechts())
        root.addLayout(mitte, stretch=1)
        self.neu_laden()
        # Laser werden im 3D verschoben, Shows geladen, Geraete gepatcht,
        # waehrend der Planer offen ist — die Zeichnung zieht im Takt nach.
        self._takt_stand = self._signatur()
        self._timer = QTimer(self)
        self._timer.setInterval(self.TAKT_MS)
        self._timer.timeout.connect(self._takt)
        self._timer.start()

    # ── Aufbau ───────────────────────────────────────────────────────────
    def _baue_kopf(self) -> QHBoxLayout:
        kopf = QHBoxLayout()
        kopf.setSpacing(6)
        titel = QLabel("<b>Sperrzonen planen</b>")
        titel.setStyleSheet("font-size:14px;margin:0 8px 0 4px;")
        kopf.addWidget(titel)
        self._btn_modus_zonen = QPushButton("Zonen zeichnen")
        self._btn_modus_zonen.setCheckable(True)
        self._btn_modus_zonen.setChecked(True)
        self._btn_modus_zonen.clicked.connect(self._modus_zonen)
        self._btn_modus_messen = QPushButton("Laser-Feld einmessen")
        self._btn_modus_messen.setCheckable(True)
        self._btn_modus_messen.clicked.connect(lambda: self.einmessen_starten(None))
        self._btn_modus_zonen.setMinimumWidth(128)
        self._btn_modus_messen.setMinimumWidth(168)
        kopf.addWidget(self._btn_modus_zonen)
        kopf.addWidget(self._btn_modus_messen)
        # Die Grenzen: EINE Zeile, dauernd sichtbar.
        grenzen = QLabel(html.escape(S.GRENZEN_KOMPAKT))
        grenzen.setObjectName("sperrzonenGrenzen")
        grenzen.setStyleSheet(
            f"#sperrzonenGrenzen{{color:{UI.GELB};border:1px solid {UI.GELB};"
            "border-radius:15px;background:#2e2600;padding:5px 12px;"
            "font-size:12px;font-weight:600;margin-left:8px;}")
        grenzen.setToolTip(
            "Gerechnet wird nur, was hier eingetragen ist. Spiegelungen und "
            "Abschattungen fehlen. " + UI.GRENZEN_TEXT)
        grenzen.setWordWrap(True)
        grenzen.setMinimumWidth(330)
        kopf.addWidget(grenzen, stretch=1)
        self._btn_3d = QPushButton("Im 3D zeigen")
        self._btn_3d.setToolTip("Das 3D-Fenster nach vorn holen — es zeichnet "
                                "jede Änderung sofort mit.")
        self._btn_3d.clicked.connect(self._im_3d_zeigen)
        self._btn_undo = QPushButton("Rückgängig")
        self._btn_undo.setShortcut("Ctrl+Z")
        self._btn_undo.clicked.connect(self.rueckgaengig)
        self._btn_redo = QPushButton("Wiederholen")
        self._btn_redo.setShortcut("Ctrl+Y")
        self._btn_redo.clicked.connect(self.wiederholen)
        self._btn_fertig = QPushButton("Fertig")
        self._btn_fertig.setProperty("rolle", "blau")
        self._btn_fertig.setMinimumWidth(90)
        self._btn_fertig.clicked.connect(self.close)
        for b in (self._btn_3d, self._btn_undo, self._btn_redo, self._btn_fertig):
            kopf.addWidget(b)
        return kopf

    @staticmethod
    def _tafel(titel: str, hilfe: str = ""):
        tafel = QFrame()
        tafel.setProperty("rolle", "tafel")
        lay = QVBoxLayout(tafel)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)
        kopf = QHBoxLayout()
        t = QLabel(titel.upper())
        t.setProperty("rolle", "kopf")
        kopf.addWidget(t)
        kopf.addStretch(1)
        if hilfe:
            h = QLabel(hilfe)
            h.setProperty("rolle", "blass")
            kopf.addWidget(h)
        lay.addLayout(kopf)
        return tafel, lay, t

    def _baue_links(self) -> QWidget:
        tafel, lay, self._lbl_zonen = self._tafel("Zonen")
        tafel.setFixedWidth(284)
        self._liste = QListWidget()
        self._liste.setObjectName("sperrzonenListe")
        self._liste.setItemDelegate(_ZonenZeile(self._liste))
        self._liste.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self._liste.currentRowChanged.connect(self._zeile_gewaehlt)
        lay.addWidget(self._liste, stretch=1)
        t = QLabel("NEUE ZONE")
        t.setProperty("rolle", "kopf")
        lay.addWidget(t)
        self._btn_vorlagen = {}
        for kennung, knopf, _name, *_masse in S.VORLAGEN:
            b = QPushButton(knopf)
            b.setObjectName(f"sperrzonenVorlage_{kennung}")
            b.setToolTip("Legt eine Zone an dieser üblichen Stelle an — danach "
                         "in der Draufsicht zurechtziehen.")
            b.clicked.connect(lambda _c=False, k=kennung: self.vorlage_anlegen(k))
            lay.addWidget(b)
            self._btn_vorlagen[kennung] = b
        self._btn_neu = QPushButton("+ Freie Zone")
        self._btn_neu.setToolTip("Oder: in der Draufsicht auf freier Fläche aufziehen.")
        self._btn_neu.clicked.connect(self._zone_neu)
        lay.addWidget(self._btn_neu)
        legende = QLabel(
            '<span style="color:#d05050">■</span> Sperrzone &nbsp; '
            '<span style="color:#f0c000">—</span> größtes Feld &nbsp; '
            '<span style="color:#f0c000">- -</span> mit Zuschlag<br>'
            '<span style="color:#ffb000">▨</span> vom Laser erreichbar')
        legende.setTextFormat(Qt.TextFormat.RichText)
        legende.setProperty("rolle", "blass")
        lay.addWidget(legende)
        return tafel

    def _baue_mitte(self) -> QWidget:
        host = QWidget()
        gitter = QGridLayout(host)
        gitter.setContentsMargins(0, 0, 0, 0)
        gitter.setSpacing(8)
        tafel, lay, _t = self._tafel(
            "Draufsicht", "freie Fläche aufziehen = neue Zone")
        self._drauf = _Zeichenflaeche(self, "drauf")
        self._drauf.setToolTip(
            "Zone ziehen = verschieben · eckige Griffe = Größe · runder Griff "
            "außen = drehen · freie Fläche aufziehen = neue Zone · Doppeltipp = "
            "Maße eintippen")
        lay.addWidget(self._drauf, stretch=1)
        gitter.addWidget(tafel, 0, 0)

        rechts = QVBoxLayout()
        rechts.setSpacing(8)
        tafel, lay, _t = self._tafel("Seitenansicht", "Griffe = Ober-/Unterkante")
        self._seite = _Zeichenflaeche(self, "seite")
        lay.addWidget(self._seite, stretch=1)
        rechts.addWidget(tafel, stretch=1)
        self._hinweis = _Hinweis()
        rechts.addWidget(self._hinweis)
        gitter.addLayout(rechts, 0, 1)
        gitter.setColumnStretch(0, 5)
        gitter.setColumnStretch(1, 4)
        gitter.setRowStretch(0, 1)
        gitter.addWidget(self._baue_massleiste(), 1, 0, 1, 2)
        return host

    def _baue_massleiste(self) -> QWidget:
        tafel, lay, self._lbl_gewaehlt = self._tafel("Gewählt: —")
        self._form_host = QWidget()
        gitter = QGridLayout(self._form_host)
        gitter.setContentsMargins(0, 0, 0, 0)
        gitter.setHorizontalSpacing(8)
        gitter.setVerticalSpacing(2)
        platz = [0]

        def _spalte(titel, widget):
            reihe, spalte = divmod(platz[0], 5)
            platz[0] += 1
            t = QLabel(titel)
            t.setProperty("rolle", "blass")
            gitter.addWidget(t, reihe * 2, spalte)
            gitter.addWidget(widget, reihe * 2 + 1, spalte)

        self._name = QLineEdit()
        self._name.setMaxLength(40)
        self._name.textEdited.connect(self._zone_geaendert)
        _spalte("Name", self._name)
        self._zspins = {}
        self._dreh = _spin(-180.0, 180.0, 0.0, schritt=RASTER_GRAD, suffix=" °", stellen=1)
        self._dreh.valueChanged.connect(lambda _v: self._zone_geaendert("dreh_y"))
        self._btn_loeschen = QPushButton("Zone löschen")
        self._btn_loeschen.setProperty("rolle", "rot")
        self._btn_loeschen.clicked.connect(self._zone_loeschen)
        for attr, titel, lo, hi in self._ZONEN_FELDER:
            sp = _spin(lo, hi, 0.0 if lo < 0 else lo, schritt=RASTER_M)
            sp.valueChanged.connect(lambda _v, a=attr: self._zone_geaendert(a))
            self._zspins[attr] = sp
            _spalte(titel, sp)
            if attr == "hoehe":
                _spalte("Drehung", self._dreh)
        _spalte("", self._btn_loeschen)
        for spalte in range(5):
            gitter.setColumnStretch(spalte, 1)
        lay.addWidget(self._form_host)
        self._chk_einrasten = QCheckBox(f"Einrasten auf {_m(RASTER_M)} m (beim Ziehen)")
        self._chk_einrasten.setObjectName("sperrzonenEinrasten")
        self._chk_einrasten.setChecked(True)
        kopfzeile = tafel.layout().itemAt(0).layout()
        kopfzeile.addWidget(self._chk_einrasten)
        return tafel

    def _baue_rechts(self) -> QWidget:
        self._rechts = QStackedWidget()
        self._rechts.setFixedWidth(356)
        tafel, lay, _t = self._tafel("Laser-Felder", "Randwinkel von der Geräteachse")
        self._karten_host = QWidget()
        self._karten_lay = QVBoxLayout(self._karten_host)
        self._karten_lay.setContentsMargins(0, 0, 0, 0)
        self._karten_lay.setSpacing(6)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self._karten_host)
        scroll.viewport().setStyleSheet("background:transparent;")
        self._karten_host.setStyleSheet("background:transparent;")
        lay.addWidget(scroll, stretch=1)
        self._datenblatt_info = QLabel("")
        self._datenblatt_info.setObjectName("sperrzonenDatenblattInfo")
        self._datenblatt_info.setProperty("rolle", "blass")
        self._datenblatt_info.setWordWrap(True)
        lay.addWidget(self._datenblatt_info)
        erkl = QLabel(
            "Links/rechts/oben/unten aus Sicht des Geräts in Strahlrichtung: was "
            "der Laser bei größtem Muster und voller Auslenkung höchstens "
            f"erreicht. „{UI.NICHT_ANGEGEBEN}“ = dieser Laser ist nicht prüfbar.")
        erkl.setWordWrap(True)
        erkl.setProperty("rolle", "blass")
        lay.addWidget(erkl)
        self._chk_lasersicht = QCheckBox("Sicht des Lasers zeigen (Fenster im 3D)")
        self._chk_lasersicht.setObjectName("sperrzonenLasersicht")
        self._chk_lasersicht.setToolTip(
            "Blendet im 3D unten links ein Bild aus Sicht des Lasers ein: das "
            "Feld als Rechteck, die Sperrzonen darin. Erscheint nur, wenn es "
            "einen Laser mit Randwinkeln und mindestens eine Zone gibt. "
            "Nur Anzeige.")
        self._chk_lasersicht.setChecked(M.lasersicht_zeigen())
        self._chk_lasersicht.toggled.connect(self._lasersicht_geschaltet)
        lay.addWidget(self._chk_lasersicht)
        self._rechts.addWidget(tafel)
        self._assistent_host = QFrame()
        self._assistent_host.setProperty("rolle", "tafel")
        self._assistent_host.setStyleSheet(
            f'QFrame[rolle="tafel"]{{border-color:{UI.BLAU};}}')
        self._assistent_lay = QVBoxLayout(self._assistent_host)
        self._assistent_lay.setContentsMargins(2, 2, 2, 2)
        self._rechts.addWidget(self._assistent_host)
        return self._rechts

    # ── Bestand und Abgeleitetes ─────────────────────────────────────────
    def daten(self):
        return self._state.sperrzonen

    _daten = daten

    def bearbeitbar(self) -> bool:
        return self.daten().fremd is None

    def einrasten(self) -> bool:
        return self._chk_einrasten.isChecked()

    def gewaehlte_zone(self):
        return self.daten().zone(self._gewaehlt) if self._gewaehlt else None

    _gewaehlte_zone = gewaehlte_zone

    def _rechne(self) -> dict:
        """Alles, was die Zeichnung aus dem Bestand ableitet — einmal je
        Aenderung, nicht je Neuzeichnen."""
        if self._abgeleitet is not None:
            return self._abgeleitet
        daten = self.daten()
        st = self._state
        laser = S.dmx_laser_geraete(st) if daten.fremd is None else []
        pos = getattr(st, "visualizer_positions", {}) or {}
        rot = getattr(st, "visualizer_rotations", {}) or {}
        zonen = daten.zonen if daten.fremd is None else []
        schraffuren, faecher, lagen, befunde = [], [], [], []
        for fid, name, kennung in laser:
            feld = daten.feld(fid, kennung)
            p, r = pos.get(fid), rot.get(fid)
            befund = S.pruefe_laser(fid, name, p, r, feld, zonen)
            orte = {}
            for zone in zonen:
                # Die Entscheidung trifft pruefe_laser — der Umriss kommt aus
                # derselben Rechnung und ist dann nie leer.
                if S.pruefe_laser(fid, name, p, r, feld, [zone]).status \
                        != S.STATUS_ERREICHT:
                    continue
                try:
                    teil = S.erreichter_teil(p, r, feld, zone)
                except Exception:                        # noqa: BLE001
                    teil = None
                if teil is None:                         # nie „frei" zeichnen
                    teil = S.zonen_umriss(zone, S.ZONEN_RAND_M)
                schraffuren.append({"fid": fid, "zid": zone.id, **teil})
                orte[zone.name] = abstand_zum_umriss(p[0], p[2], teil["drauf"])
            befunde.append((befund, orte))
            if p is None:
                continue
            pruefbar = feld.vollstaendig
            text = f"Laser {fid}"
            if pruefbar:
                breit = max(feld.links, feld.rechts)
                text += f" · {_grad(breit)} + {_grad(feld.zuschlag)}"
                try:
                    faecher.append({
                        "fid": fid,
                        "innen": S.feld_umriss(p, r, feld, S.FELD_ANZEIGE_LAENGE_M, False),
                        "aussen": S.feld_umriss(p, r, feld, S.FELD_ANZEIGE_LAENGE_M, True)})
                except Exception as e:                   # noqa: BLE001
                    print(f"[sperrzonen_planer] Feld von Laser {fid}: {e}")
            else:
                text += " · Winkel fehlen"
            lagen.append({"fid": fid, "pos": tuple(float(v) for v in p),
                          "rot": r, "pruefbar": pruefbar, "text": text})
        self._abgeleitet = {
            "laser": laser, "schraffuren": schraffuren, "faecher": faecher,
            "lagen": lagen, "befunde": befunde,
            "ampel": S.zonen_ampel(laser, pos, rot, daten) if daten.fremd is None else {},
            "buehne": buehnen_umrisse(st)}
        return self._abgeleitet

    def schraffuren(self) -> list:
        return self._rechne()["schraffuren"]

    def faecher(self) -> list:
        return self._rechne()["faecher"]

    def laser_lagen(self) -> list:
        return self._rechne()["lagen"]

    def buehne(self) -> list:
        return self._rechne()["buehne"]

    def ampel(self) -> dict:
        return self._rechne()["ampel"]

    def inhalt_punkte(self, art: str):
        for zone in (self.daten().zonen if self.bearbeitbar() else []):
            yield from S.zonen_umriss(zone)[art]
        for la in self.laser_lagen():
            x, y, z = la["pos"]
            yield (x, z) if art == "drauf" else (z, y)
        for el in self.buehne():
            yield from el[art]

    def buehne_vorn_z(self) -> float:
        """Vorderkante der Buehne (Publikumsseite) fuer die Vorlagen."""
        kanten = [max(p[1] for p in el["drauf"]) for el in self.buehne()
                  if el["typ"] in ("platform", "dj_booth", "riser_stairs")]
        return max(kanten) if kanten else 2.0

    # ── Rueckgaengig / Wiederholen ───────────────────────────────────────
    def _stand(self) -> dict:
        daten = self.daten()
        return {"zonen": [z.to_dict() for z in daten.zonen],
                "felder": {fid: LaserFeld(**{**f.to_dict()})
                           for fid, f in daten.laser_felder.items()},
                "gewaehlt": self._gewaehlt}

    def merke_stand(self, schluessel=None) -> None:
        """Den Stand VOR einer Aenderung auf den Stapel legen. Gleicher
        ``schluessel`` kurz hintereinander (Pfeiltasten an einem Zahlenfeld)
        ist ein Schritt."""
        if not self.bearbeitbar():
            return
        jetzt = time.monotonic()
        if (schluessel is not None and schluessel == self._undo_schluessel
                and jetzt - self._undo_zeit < _UNDO_BUENDEL_S and self._undo):
            self._undo_zeit = jetzt
            return
        self._undo_schluessel, self._undo_zeit = schluessel, jetzt
        self._undo.append(self._stand())
        del self._undo[:-UNDO_TIEFE]
        self._redo.clear()
        self._knoepfe_auffrischen()

    def _stand_setzen(self, stand: dict) -> None:
        daten = self.daten()
        daten.zonen[:] = [Sperrzone.from_dict(d) for d in stand["zonen"]]
        daten.laser_felder.clear()
        daten.laser_felder.update(
            {fid: LaserFeld(**f.to_dict()) for fid, f in stand["felder"].items()})
        self._gewaehlt = stand.get("gewaehlt")
        self._undo_schluessel = None
        self._geaendert(liste=True)

    def rueckgaengig(self) -> None:
        if not self._undo or not self.bearbeitbar():
            return
        self._redo.append(self._stand())
        self._stand_setzen(self._undo.pop())

    def wiederholen(self) -> None:
        if not self._redo or not self.bearbeitbar():
            return
        self._undo.append(self._stand())
        self._stand_setzen(self._redo.pop())

    def _knoepfe_auffrischen(self) -> None:
        self._btn_undo.setEnabled(bool(self._undo) and self.bearbeitbar())
        self._btn_redo.setEnabled(bool(self._redo) and self.bearbeitbar())

    # ── Auffrischen ──────────────────────────────────────────────────────
    def _geaendert(self, liste: bool = False) -> None:
        """Nach JEDER Aenderung am Bestand: melden (das 3D zeichnet mit) und
        die eigene Anzeige nachziehen."""
        self._abgeleitet = None
        melde_aenderung(self._state)
        self._anzeige(liste)

    def _anzeige(self, liste: bool = False) -> None:
        self._abgeleitet = None
        if liste:
            self._fuelle_liste()
        else:
            self._liste_auffrischen()
        self._zone_in_felder()
        self._karten_auffrischen()
        self._hinweis_auffrischen()
        self._knoepfe_auffrischen()
        self._drauf.update()
        self._seite.update()

    def neu_laden(self) -> None:
        """Alles aus dem State fuellen (z. B. nach dem Laden einer Show)."""
        self._abgeleitet = None
        self.lasersicht_nachziehen()
        fremd = not self.bearbeitbar()
        if self.gewaehlte_zone() is None:
            zonen = self.daten().zonen if not fremd else []
            self._gewaehlt = zonen[0].id if zonen else None
        for b in (self._btn_neu, *self._btn_vorlagen.values(), self._chk_einrasten):
            b.setEnabled(not fremd)
        self._baue_karten()
        self._anzeige(liste=True)
        self._drauf.einpassen()
        self._seite.einpassen()

    def _fuelle_liste(self) -> None:
        self._laedt = True
        try:
            self._liste.clear()
            for z in (self.daten().zonen if self.bearbeitbar() else []):
                it = QListWidgetItem(z.name)
                it.setData(_ROLLE_ID, z.id)
                self._liste.addItem(it)
        finally:
            self._laedt = False
        self._liste_auffrischen()

    def _liste_auffrischen(self) -> None:
        ampel = self.ampel()
        zonen = self.daten().zonen if self.bearbeitbar() else []
        self._lbl_zonen.setText(f"ZONEN ({len(zonen)})")
        self._laedt = True
        try:
            for i in range(self._liste.count()):
                it = self._liste.item(i)
                zone = self.daten().zone(it.data(_ROLLE_ID))
                if zone is None:
                    continue
                eintrag = ampel.get(zone.id, {"status": S.STATUS_KEIN_LASER})
                if it.text() != zone.name:
                    it.setText(zone.name)
                it.setData(_ROLLE_STATUS, eintrag["status"])
                it.setData(_ROLLE_AMPEL,
                           f"{_m(zone.breite, 1)} × {_m(zone.tiefe, 1)} × "
                           f"{_m(zone.hoehe, 1)} m · {S.ampel_text(eintrag)}")
                it.setToolTip(S.ampel_text(eintrag))
                if zone.id == self._gewaehlt and self._liste.currentRow() != i:
                    self._liste.setCurrentRow(i)
            if self.gewaehlte_zone() is None:
                self._liste.setCurrentRow(-1)
        finally:
            self._laedt = False

    def ampel_texte(self) -> dict:
        """Zonenname -> Ampeltext, wie die Liste ihn zeigt."""
        return {z.name: S.ampel_text(self.ampel()[z.id]) for z in self.daten().zonen
                if z.id in self.ampel()}

    def _zone_in_felder(self) -> None:
        zone = self.gewaehlte_zone()
        an = zone is not None and self.bearbeitbar()
        self._form_host.setEnabled(an)
        self._btn_loeschen.setEnabled(an)
        self._lbl_gewaehlt.setText(
            f"GEWÄHLT: {zone.name.upper()}" if zone is not None else "GEWÄHLT: —")
        if zone is None:
            return
        self._laedt = True
        try:
            text = self._name.text().strip()
            if text != zone.name and not (self._name.hasFocus() and not text):
                self._name.setText(zone.name)
            for attr, sp in (*self._zspins.items(), ("dreh_y", self._dreh)):
                wert = float(getattr(zone, attr))
                if abs(sp.value() - wert) > 1e-9:   # beim Tippen nicht stoeren
                    sp.setValue(wert)
        finally:
            self._laedt = False

    def _hinweis_auffrischen(self) -> None:
        daten = self.daten()
        zeilen = []
        if daten.fremd is not None:
            zeilen.append(f'<b style="color:{UI.GELB}">'
                          f'{html.escape(S.kopfzeile(0, daten))}</b>')
        else:
            r = self._rechne()
            if not r["laser"]:
                zeilen.append('<span style="color:#c9d1d9">Kein DMX-Laser '
                              'gepatcht — es gibt nichts zu prüfen.</span>')
            elif not daten.zonen:
                zeilen.append(f'<span style="color:{UI.GELB}">Laser gepatcht, '
                              'keine Sperrzonen angelegt</span>')
            for befund, orte in (r["befunde"] if daten.zonen else []):
                if befund.status == S.STATUS_ERREICHT:
                    wo = "; ".join(
                        f"„{html.escape(n)}“ ab rund {_m(d, 1)} m" for n, d in orte.items())
                    zeilen.append(
                        f'<b style="color:{UI.GELB}">{html.escape(befund.text)}</b>'
                        f'<br><span style="color:#d8b84a">{wo} (waagerecht vom '
                        'Gerät gemessen). Begrenzt wird am Gerät: Blende, Höhe, '
                        'Neigung.</span>')
                elif befund.status == S.STATUS_NICHT_PRUEFBAR:
                    zeilen.append(f'<span style="color:{UI.GELB}">'
                                  f'{html.escape(befund.text)}</span>')
                else:
                    zeilen.append(f'<span style="color:#c9d1d9">'
                                  f'{html.escape(befund.text)}</span>')
        inhalt = "<br>".join(zeilen)
        if inhalt != self._hinweis.text():
            self._hinweis.setText(inhalt)

    # ── Zonen ────────────────────────────────────────────────────────────
    def waehle(self, zid) -> None:
        if zid == self._gewaehlt:
            return
        self._gewaehlt = zid
        self._undo_schluessel = None
        self._anzeige()

    def _zeile_gewaehlt(self, zeile: int) -> None:
        if self._laedt:
            return
        it = self._liste.item(zeile)
        self.waehle(it.data(_ROLLE_ID) if it is not None else None)

    def zone_anlegen(self, zone: Sperrzone) -> None:
        if not self.bearbeitbar():
            return
        self.merke_stand()
        self.daten().zonen.append(zone)
        self._gewaehlt = zone.id
        M.merke_benutzt()      # ab jetzt meldet das Hauptfenster Shows ohne Zonen
        self._geaendert(liste=True)

    def _zone_neu(self) -> None:
        if not self.bearbeitbar():
            return
        self.zone_anlegen(Sperrzone(
            name=S.freier_name(self.daten(), "Zone"), x=0.0, y=0.0,
            z=self.buehne_vorn_z() + 2.0, breite=4.0, hoehe=NEU_HOEHE_M, tiefe=2.0))

    def vorlage_anlegen(self, kennung: str) -> None:
        if not self.bearbeitbar():
            return
        self.zone_anlegen(S.vorlage_zone(kennung, self.daten(), self.buehne_vorn_z()))
        self._drauf.einpassen()
        self._seite.einpassen()

    def _zone_loeschen(self) -> None:
        zone = self.gewaehlte_zone()
        if zone is None or not self.bearbeitbar():
            return
        self.merke_stand()
        zonen = self.daten().zonen
        i = zonen.index(zone)
        zonen.remove(zone)
        self._gewaehlt = zonen[min(i, len(zonen) - 1)].id if zonen else None
        self._geaendert(liste=True)

    def zone_setzen(self, zone: Sperrzone, werte: dict) -> None:
        """Werte aus einem Zug uebernehmen (der Aufrufer hat den Stand schon
        gemerkt)."""
        for attr, wert in werte.items():
            if attr in ("breite", "hoehe", "tiefe"):
                wert = max(S.ZONE_MIN_M, float(wert))
            setattr(zone, attr, float(wert))
        self._geaendert()

    def _zone_geaendert(self, attr=None) -> None:
        """Feineingabe ueber die Massleiste."""
        if self._laedt:
            return
        zone = self.gewaehlte_zone()
        if zone is None or not self.bearbeitbar():
            return
        self.merke_stand(("feld", zone.id, attr if isinstance(attr, str) else "name"))
        # Nur das angefasste Feld schreiben: die anderen zeigen gerundet, was
        # ein Zug ohne Einrasten feiner abgelegt hat.
        if attr in self._zspins:
            setattr(zone, attr, float(self._zspins[attr].value()))
        elif attr == "dreh_y":
            zone.dreh_y = float(self._dreh.value())
        else:
            zone.name = self._name.text().strip() or "Sperrzone"
        self._geaendert()

    def masse_eintippen(self) -> None:
        sp = self._zspins["breite"]
        sp.setFocus()
        sp.selectAll()

    # ── Laser-Felder ─────────────────────────────────────────────────────
    def _montage_text(self, fid: int) -> str:
        pos = (getattr(self._state, "visualizer_positions", {}) or {}).get(fid)
        if pos is None:
            return "im 3D nicht platziert"
        rot = (getattr(self._state, "visualizer_rotations", {}) or {}).get(fid)
        vorn, _r, _o = S.geraete_achsen(rot)
        neigung = math.degrees(math.asin(max(-1.0, min(1.0, vorn[1]))))
        if abs(neigung) < 0.5:
            wort = "waagerecht"
        else:
            wort = f"{_grad(round(abs(neigung)))} nach {'oben' if neigung > 0 else 'unten'}"
        return f"Montage: {_m(pos[1])} m hoch · strahlt {wort}"

    def _baue_karten(self) -> None:
        while self._karten_lay.count():
            w = self._karten_lay.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        laser = S.dmx_laser_geraete(self._state)
        self._laser_zeilen = list(laser)
        self._laser_karten, self._feld_spins = {}, {}
        for fid, name, kennung in laser:
            karte = _LaserKarte(self, fid, name, kennung)
            self._karten_lay.addWidget(karte)
            self._laser_karten[fid] = karte
            self._feld_spins[fid] = karte.spins
        if not laser:
            leer = QLabel("Kein DMX-Laser gepatcht.")
            leer.setProperty("rolle", "blass")
            self._karten_lay.addWidget(leer)
        self._karten_lay.addStretch(1)
        self._btn_modus_messen.setEnabled(bool(laser) and self.bearbeitbar())

    def _karten_auffrischen(self) -> None:
        for fid, karte in self._laser_karten.items():
            karte.fuelle(self.daten().feld(fid, karte.kennung),
                         self._montage_text(fid), self.bearbeitbar())

    def _kennung(self, fid: int) -> str:
        karte = self._laser_karten.get(int(fid))
        return karte.kennung if karte is not None else ""

    def feld_geaendert(self, fid: int, nur_zuschlag: bool = False) -> None:
        """Zahlenfelder einer Laser-Karte. Von Hand geaenderte Winkel sind
        nicht mehr „eingemessen"; der Zuschlag allein aendert die Herkunft
        nicht."""
        if self._laedt or not self.bearbeitbar():
            return
        spins = self._feld_spins.get(fid)
        if not spins:
            return
        alt = self.daten().feld(fid, self._kennung(fid))
        werte = {}
        for rand in S.RAENDER:
            v = float(spins[rand].value())
            werte[rand] = None if v < 0.0 else v
        self.merke_stand(("laser", fid))
        self.daten().setze_feld(fid, LaserFeld(
            zuschlag=float(spins["zuschlag"].value()), geraet=self._kennung(fid),
            quelle=alt.quelle if nur_zuschlag else S.QUELLE_HAND,
            quelle_datum=alt.quelle_datum if nur_zuschlag else "", **werte))
        self._geaendert()

    def feld_setzen(self, fid: int, feld: LaserFeld) -> None:
        """Ein fertiges Feld (Profil, Datenblatt, Einmessen) eintragen."""
        if not self.bearbeitbar():
            return
        self.merke_stand()
        feld.geraet = self._kennung(fid)
        self.daten().setze_feld(fid, feld)
        self._geaendert()

    # ── Schnellweg: Winkel aus Profil / Datenblatt ───────────────────────
    def _profil_feld(self, fid: int):
        """Was die Geraete-Bibliothek fuer dieses Modell belegt — oder None."""
        for fx in self._state.get_patched_fixtures():
            if int(getattr(fx, "fid", -1)) == int(fid):
                return S.winkel_aus_bibliothek(
                    getattr(fx, "manufacturer_name", ""),
                    getattr(fx, "fixture_name", ""))
        return None

    def _frage_gesamtwinkel(self, name: str):
        """``(waagerecht, senkrecht)`` vom Nutzer — oder ``None`` (abgebrochen)."""
        dlg = UI._GesamtwinkelDialog(name, self)
        try:
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return None
            return float(dlg.waagerecht.value()), float(dlg.senkrecht.value())
        finally:
            dlg.deleteLater()

    def datenblatt_klick(self, fid: int) -> None:
        karte = self._laser_karten.get(fid)
        if karte is None or not self.bearbeitbar():
            return
        feld = self._profil_feld(fid)
        if feld is not None:
            feld.quelle = S.QUELLE_PROFIL
            quelle = "aus dem Geräteprofil übernommen"
        else:
            antwort = self._frage_gesamtwinkel(karte.name or f"Laser {fid}")
            if antwort is None:
                return
            feld = S.feld_aus_gesamtwinkel(*antwort)
            if feld is None:
                return
            feld.quelle = S.QUELLE_DATENBLATT
            quelle = (f"Datenblatt {antwort[0]:g}° × {antwort[1]:g}° — das "
                      "Geräteprofil nennt keinen Winkel")
        feld.zuschlag = self.daten().feld(fid, karte.kennung).zuschlag
        self.feld_setzen(fid, feld)
        self._datenblatt_info.setText(
            f"Laser {fid}: {quelle}. Kein Messwert — Ränder am Gerät nachprüfen "
            "(„Feld einmessen…“).")

    # ── Einmess-Assistent ────────────────────────────────────────────────
    def einmessen_starten(self, fid=None) -> None:
        self._assistent_schliessen(abbrechen=True)
        if fid is None:
            fid = next(iter(self._laser_karten), None)
        karte = self._laser_karten.get(fid)
        if karte is None or not self.bearbeitbar():
            self._modus_zonen()
            return
        from src.ui.visualizer.einmess_assistent import EinmessAssistent
        ass = EinmessAssistent(self._state, fid, karte.name,
                               self.daten().feld(fid, karte.kennung),
                               self._assistent_host)
        ass.beendet.connect(self._assistent_beendet)
        self._assistent_lay.addWidget(ass)
        self._assistent = ass
        self._rechts.setCurrentIndex(1)
        self._btn_modus_zonen.setChecked(False)
        self._btn_modus_messen.setChecked(True)

    def _assistent_beendet(self, feld) -> None:
        fid = self._assistent.fid if self._assistent is not None else None
        self._assistent_schliessen(abbrechen=False)
        if feld is not None and fid is not None:
            self.feld_setzen(fid, feld)
            self._datenblatt_info.setText(
                f"Laser {fid}: Feld {S.quelle_text(feld)}.")

    def _assistent_schliessen(self, abbrechen: bool) -> None:
        ass, self._assistent = self._assistent, None
        if ass is not None:
            if abbrechen:
                ass.ausschalten()      # Abbruch schaltet aus
            try:
                ass.beendet.disconnect(self._assistent_beendet)
            except (RuntimeError, TypeError):
                pass
            ass.setParent(None)
            ass.deleteLater()
        self._modus_zonen()

    def _modus_zonen(self) -> None:
        if self._assistent is not None:
            self._assistent_schliessen(abbrechen=True)
            return
        self._rechts.setCurrentIndex(0)
        self._btn_modus_zonen.setChecked(True)
        self._btn_modus_messen.setChecked(False)

    # ── Darstellung im 3D ────────────────────────────────────────────────
    def _im_3d_zeigen(self) -> None:
        elter = self.parentWidget()
        if elter is not None:
            elter.raise_()
            elter.activateWindow()

    def _lasersicht_geschaltet(self, an: bool) -> None:
        """Haken „Sicht des Lasers zeigen": merken, das 3D zieht nach."""
        M.merke_lasersicht(bool(an))
        try:
            self._state._emit("sperrzonen_anzeige_changed", bool(an))
        except Exception as e:                           # noqa: BLE001
            print(f"[sperrzonen] emit error: {e}")

    def lasersicht_nachziehen(self) -> None:
        """Das Fenster wurde im 3D selbst geschlossen/geoeffnet."""
        an = M.lasersicht_zeigen()
        if self._chk_lasersicht.isChecked() != an:
            self._chk_lasersicht.blockSignals(True)
            self._chk_lasersicht.setChecked(an)
            self._chk_lasersicht.blockSignals(False)

    TAKT_MS = 1000

    def _signatur(self):
        st = self._state
        daten = self.daten()
        try:
            laser = tuple(S.dmx_laser_geraete(st)) if daten.fremd is None else ()
        except Exception:                                # noqa: BLE001
            laser = ()
        fids = [l[0] for l in laser]
        pos = getattr(st, "visualizer_positions", {}) or {}
        rot = getattr(st, "visualizer_rotations", {}) or {}
        lage = tuple((f, tuple(pos.get(f) or ()), tuple(rot.get(f) or ())) for f in fids)
        return (id(daten), laser), (lage, repr(daten.to_dict()),
                                    getattr(st, "active_stage_name", None))

    def _takt(self) -> None:
        if not self.isVisible():
            return
        try:
            neu = self._signatur()
            alt, self._takt_stand = self._takt_stand, neu
            if neu[0] != alt[0]:
                self.patch_oder_show_geaendert()
                self._takt_stand = self._signatur()
            elif neu[1] != alt[1]:
                self._anzeige(liste=self._liste.count() != len(self.daten().zonen))
        except Exception as e:                           # noqa: BLE001
            print(f"[sperrzonen_planer] Takt: {e}")

    def patch_oder_show_geaendert(self) -> None:
        """Neue Show / anderer Patch: ein laufendes Einmessen endet (aus), der
        Rueckgaengig-Stapel gehoert zur alten Show."""
        self._assistent_schliessen(abbrechen=True)
        self._undo.clear()
        self._redo.clear()
        self._gewaehlt = None
        self.neu_laden()

    def einmessen_abbrechen(self) -> None:
        """Ein laufendes Einmessen beenden: Laser aus (falls der Assistent ihn
        eingeschaltet hat), nichts eintragen. Ohne Assistent passiert nichts."""
        if self._assistent is not None:
            self._assistent_schliessen(abbrechen=True)

    def closeEvent(self, ev):  # noqa: N802 (Qt-API)
        # Schliessen mitten im Einmessen = Abbruch = Laser aus.
        self._assistent_schliessen(abbrechen=True)
        super().closeEvent(ev)

    def hideEvent(self, ev):  # noqa: N802 (Qt-API)
        # Esc ruft ``reject()`` und versteckt den Dialog OHNE ``closeEvent``;
        # auch das ist ein Abbruch. Nur das Minimieren durch den Fenster-
        # Manager (spontan) laesst das Einmessen stehen.
        if not ev.spontaneous():
            self.einmessen_abbrechen()
        super().hideEvent(ev)


_offen = None        # der eine offene Planer (je Programm)


def planer_oeffnen(state, elter=None) -> SperrzonenPlaner:
    """Den Planer zeigen — vom Knopf „Sperrzonen…" im 3D-Fenster und von der
    Sperrzonen-Meldung aus. Es gibt nur einen; ein zweiter Aufruf holt ihn
    nach vorn und laedt ihn neu."""
    global _offen
    dlg = _offen
    try:
        from shiboken6 import isValid
        lebt = dlg is not None and isValid(dlg) and dlg._state is state
    except Exception:                                    # noqa: BLE001
        lebt = False
    if not lebt:
        dlg = SperrzonenPlaner(state, elter)
        _offen = dlg
    else:
        dlg.neu_laden()
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    return dlg
