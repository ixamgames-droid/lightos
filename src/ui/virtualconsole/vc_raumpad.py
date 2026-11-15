"""VCRaumPad — den Raum antippen statt Pan/Tilt schieben (UI-127).

Draufsicht der Buehne aus den Raummassen des Visualizers (Raster 1 m, oben
Rueckwand, unten Publikum). Die zugeordneten Moving Heads stehen als
nummerierte Punkte an ihrem Standort. Tippen oder Ziehen setzt einen Zielpunkt
(x, z) in der Zielhoehe H; jeder Kopf bekommt Pan/Tilt (mit Feinkanal) aus
``aim_pan_tilt`` fuer SEINEN Standort und seine Montage — dieselbe Rechnung wie
das Werkzeug „Zielen" im 3D-Visualizer (``core/stage/raum_pad.py``).

Schalter am Widget:

* **AN/AUS** — AN schreibt die Zielwerte in den Programmer (derselbe Weg wie
  das XY-Pad). AUS gibt Pan/Tilt/Fein der eigenen Koepfe wieder frei: jeder
  Schluessel bekommt den Wert zurueck, den er vor dem ersten Schreiben hatte
  (fehlte er, wird er entfernt). Ein Wert, den inzwischen jemand anderes
  ueberschrieben hat, bleibt stehen — fremde Programmer-Werte fasst das Pad nie
  an. Die Ausgabe ist danach byte-gleich wie vorher.
* **Position Lock** (Vorgabe AN) — AN: das Ziel bleibt nach dem Loslassen
  stehen. AUS: das Ziel gilt nur, solange Finger oder Maus gedrueckt sind;
  beim Loslassen wird freigegeben wie bei AUS.
* **Zielhoehe** — Regler 0 m (Boden) bis Raumhoehe.

Zwei Ansichten (Eigenschaft ``ansicht``, im Inspector waehlbar, gespeichert):

* **Draufsicht** (Vorgabe, Teil A) — siehe oben.
* **Aufgeklappt** (Teil B) — der Raum als auseinandergefalteter Wuerfel ohne
  Decke: Boden in der Mitte, Rueckwand oben, Waende links/rechts seitlich,
  Wand vorn unten; massstabsgetreu aus Raumbreite/-tiefe/-hoehe. Ein Tipp auf
  den Boden zielt wie in der Draufsicht (Zielhoehe H), ein Tipp auf eine Wand
  zielt auf den Punkt AUF der Wand (Hoehe = Abstand zur Klappkante); der
  Zielhoehen-Regler ist dann ausgegraut und zeigt die Wandhoehe. Ziehen ueber
  eine Klappkante wechselt stetig auf die Nachbarflaeche; ausserhalb aller
  Flaechen wird auf die naechste begrenzt. Welche Waende gezeigt werden, ist
  abwaehlbar (der Boden bleibt immer). Rechnung in
  ``core/stage/raum_pad.Aufklappung``.

Koepfe, die das Ziel nicht erreichen koennen (``aim_pan_tilt`` wuerde still
auf den Anschlag begrenzen, z. B. ein Ziel ueber der Kopfhoehe bei kleinem
Tilt-Bereich), werden rot markiert und im Hinweis genannt.

Koepfe ohne Standort im Visualizer fahren NICHT mit; sie stehen gelb
gestrichelt am Rand mit Hinweis. Geraete ohne Pan/Tilt lassen sich nicht
zuordnen.

Der AN-Zustand wird bewusst nicht gespeichert: eine geladene Show schreibt
nichts von selbst in den Programmer.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout,
                               QWidget)

from .vc_style import touch_aktiv
from .vc_widget import VCWidget

_GELB = QColor("#e3b341")
_AN = QColor("#2ea043")
_AUS = QColor("#30363d")
_ZIEL = QColor("#ff5c8a")
_KOPF = QColor("#58a6ff")
_ROT = QColor("#f85149")

DRAUFSICHT = "Draufsicht"
AUFGEKLAPPT = "Aufgeklappt"
ANSICHTEN = (DRAUFSICHT, AUFGEKLAPPT)


def _state():
    from src.core.app_state import get_state
    return get_state()


def _kanaele(f):
    from src.core import app_state as A
    try:
        return list(A.get_channels_for_patched(f) or [])
    except Exception:
        return []


class VCRaumPad(VCWidget):
    """Draufsicht des Raums: Ziel antippen, alle zugeordneten Koepfe zielen."""

    MIN_SIZE = (180, 170)

    def __init__(self, caption: str = "Raum-Pad", parent=None):
        super().__init__(caption, parent)
        self._fixture_ids: list[int] = []
        self.gruppen: list[str] = []
        self.ziel: tuple[float, float] | None = None   # (x, z) in Metern
        self.hoehe: float = 0.0                          # Zielhoehe in Metern
        self.position_lock: bool = True
        # Teil B: Ansicht + gezeigte Waende; Zielflaeche + Hoehe auf der Wand
        from src.core.stage.raum_pad import BODEN, WAENDE
        self.ansicht: str = DRAUFSICHT
        self.waende: tuple[str, ...] = tuple(WAENDE)
        self.flaeche: str = BODEN
        self.wand_hoehe: float = 0.0
        self.aktiv: bool = False                          # nicht gespeichert
        # (fid, attr, kopf) -> [Wert vorher, zuletzt selbst geschriebener Wert]
        self._eigene: dict[tuple, list] = {}
        self._zug: str | None = None                      # "pad" / "hoehe" / "an" / "lock"
        self._bg_color = QColor("#0d1117")
        self._fg_color = QColor("#58a6ff")
        self.resize(260, 240)

    # ── Geometrie ──────────────────────────────────────────────────────────

    def _leiste(self) -> int:
        """Hoehe der Bedienleisten: im Touch-Modus >= 44 px."""
        return 44 if touch_aktiv() else 26

    def _zonen(self) -> dict[str, QRect]:
        r = self.rect().adjusted(4, 4, -4, -4)
        h = self._leiste()
        knopf_b = 64 if touch_aktiv() else 46
        lock_b = 96 if touch_aktiv() else 70
        oben = QRect(r.x(), r.y(), r.width(), h)
        unten = QRect(r.x(), r.bottom() - h + 1, r.width(), h)
        return {
            "an": QRect(oben.x(), oben.y(), knopf_b, h),
            "lock": QRect(oben.x() + knopf_b + 4, oben.y(), lock_b, h),
            "titel": QRect(oben.x() + knopf_b + lock_b + 8, oben.y(),
                           max(0, oben.width() - knopf_b - lock_b - 8), h),
            "hoehe": unten,
            "feld": QRect(r.x(), oben.bottom() + 4, r.width(),
                          max(1, unten.top() - oben.bottom() - 8)),
        }

    def _raum(self):
        from src.core.stage.raum_pad import raum_masse
        try:
            pos = dict(_state().visualizer_positions)
        except Exception:
            pos = {}
        return raum_masse(pos)

    def _abbildung(self, raum=None):
        """(Pad-Rechteck in px, Massstab px/m) — seitentreu im Feld zentriert."""
        raum = raum or self._raum()
        feld = self._zonen()["feld"]
        s = min(feld.width() / max(raum.breite, 1e-6),
                feld.height() / max(raum.tiefe, 1e-6))
        w, h = raum.breite * s, raum.tiefe * s
        pad = QRectF(feld.x() + (feld.width() - w) / 2.0,
                     feld.y() + (feld.height() - h) / 2.0, w, h)
        return pad, s

    def aufklappung(self, raum=None):
        from src.core.stage.raum_pad import Aufklappung
        return Aufklappung(raum or self._raum(), self.waende)

    def _abw_abbildung(self, auf=None):
        """Aufgeklappt: (Rechteck der ganzen Abwicklung in px, Massstab px/m)."""
        auf = auf or self.aufklappung()
        feld = self._zonen()["feld"]
        bw, bh = auf.groesse
        s = min(feld.width() / max(bw, 1e-6), feld.height() / max(bh, 1e-6))
        w, h = bw * s, bh * s
        return QRectF(feld.x() + (feld.width() - w) / 2.0,
                      feld.y() + (feld.height() - h) / 2.0, w, h), s

    def _ab_zu_px(self, a, b, rahmen, s) -> QPointF:
        return QPointF(rahmen.x() + a * s, rahmen.y() + b * s)

    def _px_zu_ab(self, p, auf=None):
        rahmen, s = self._abw_abbildung(auf)
        s = s or 1.0
        return (p.x() - rahmen.x()) / s, (p.y() - rahmen.y()) / s

    def flaeche_px(self, flaeche: str, auf=None) -> QRectF | None:
        """Pixel-Rechteck einer gezeigten Flaeche (Aufgeklappt), sonst None."""
        auf = auf or self.aufklappung()
        rr = auf.rechtecke().get(flaeche)
        if rr is None:
            return None
        rahmen, s = self._abw_abbildung(auf)
        return QRectF(self._ab_zu_px(rr[0], rr[1], rahmen, s),
                      self._ab_zu_px(rr[2], rr[3], rahmen, s))

    def _welt_zu_px(self, x, z, raum, pad, s) -> QPointF:
        return QPointF(pad.x() + (x - raum.x0) * s, pad.y() + (z - raum.z0) * s)

    def _px_zu_welt(self, p: QPoint, raum=None):
        raum = raum or self._raum()
        pad, s = self._abbildung(raum)
        s = s or 1.0
        x = raum.x0 + (p.x() - pad.x()) / s
        z = raum.z0 + (p.y() - pad.y()) / s
        return raum.klemme(x, z)

    def _hoehe_aus_px(self, p: QPoint, raum=None):
        raum = raum or self._raum()
        z = self._zonen()["hoehe"]
        bahn = z.adjusted(self._hoehe_text_b(), 0, -8, 0)
        frac = (p.x() - bahn.x()) / max(1, bahn.width())
        frac = max(0.0, min(1.0, frac))
        return round(frac * raum.hoehe, 1)

    def _hoehe_text_b(self) -> int:
        return 96 if touch_aktiv() else 74

    # ── Zuordnung ──────────────────────────────────────────────────────────

    def zugeordnete_fids(self, state=None) -> list[int]:
        """Feste Geraete + Gruppenmitglieder (Reihenfolge stabil, ohne Doppel)."""
        state = state or _state()
        out: list[int] = []
        for fid in self._fixture_ids:
            if int(fid) not in out:
                out.append(int(fid))
        for name in self.gruppen:
            try:
                fids = state.group_fids_by_name(name) or []
            except Exception:
                fids = []
            for fid in fids:
                if int(fid) not in out:
                    out.append(int(fid))
        return out

    def koepfe(self, state=None):
        """``(mit_position, ohne_position)``: Listen von ``(fid, f, kanaele, pos)``
        nur fuer Geraete mit Pan/Tilt (alles andere faehrt nie mit)."""
        from src.core.stage.raum_pad import bewegung
        state = state or _state()
        try:
            patch = {f.fid: f for f in state.get_patched_fixtures()}
        except Exception:
            patch = {}
        try:
            positionen = state.visualizer_positions
        except Exception:
            positionen = {}
        mit, ohne = [], []
        for fid in self.zugeordnete_fids(state):
            f = patch.get(fid)
            if f is None:
                continue
            kan = _kanaele(f)
            if bewegung(f, kan) < 1:
                continue
            pos = positionen.get(fid) if positionen is not None else None
            if pos:
                mit.append((fid, f, kan, tuple(float(v) for v in pos[:3])))
            else:
                ohne.append((fid, f, kan, None))
        return mit, ohne

    # ── Ausgabe ────────────────────────────────────────────────────────────

    def ziel_3d(self):
        if self.ziel is None:
            return None
        y = self.hoehe if self.auf_boden() else self.wand_hoehe
        return (float(self.ziel[0]), float(y), float(self.ziel[1]))

    def auf_boden(self) -> bool:
        from src.core.stage.raum_pad import BODEN
        return self.flaeche == BODEN

    def unerreichbar(self, state=None) -> list[int]:
        """Geraete-IDs der Koepfe, die das aktuelle Ziel nicht treffen koennen
        (``aim_pan_tilt`` wuerde still auf den Anschlag begrenzen)."""
        ziel = self.ziel_3d()
        if ziel is None:
            return []
        from src.core.stage.raum_pad import erreichbar
        state = state or _state()
        try:
            rots = state.visualizer_rotations
        except Exception:
            rots = {}
        mit, _ohne = self.koepfe(state)
        out = []
        for fid, f, _k, pos in mit:
            try:
                ok = erreichbar(f, pos, rots.get(fid), ziel)
            except Exception:
                ok = True
            if not ok:
                out.append(fid)
        return out

    def anwenden(self) -> int:
        """Zielwerte in den Programmer schreiben; Rueckgabe: Zahl der Koepfe."""
        ziel = self.ziel_3d()
        if ziel is None:
            return 0
        from src.core.stage.raum_pad import ziel_werte
        state = _state()
        mit, _ohne = self.koepfe(state)
        try:
            rots = state.visualizer_rotations
        except Exception:
            rots = {}
        schritt = getattr(state, "programmer_schritt", None)
        ctx = schritt("Raum-Pad") if callable(schritt) else None
        if ctx is not None:
            ctx.__enter__()
        try:
            for fid, f, kan, pos in mit:
                for attr, kopf, wert in ziel_werte(f, kan, pos, rots.get(fid), ziel):
                    k = (fid, attr, kopf)
                    if k not in self._eigene:
                        self._eigene[k] = [state.get_programmer_value(fid, attr, head=kopf), None]
                    state.set_programmer_value(fid, attr, wert, head=kopf)
                    self._eigene[k][1] = state.get_programmer_value(fid, attr, head=kopf)
        finally:
            if ctx is not None:
                ctx.__exit__(None, None, None)
        return len(mit)

    def freigeben(self) -> bool:
        """Eigene Pan/Tilt/Fein-Werte zuruecknehmen (s. Modulkopf)."""
        self.aktiv = False
        if not self._eigene:
            self.update()
            return False
        state = _state()
        eigene, self._eigene = self._eigene, {}
        schritt = getattr(state, "programmer_schritt", None)
        ctx = schritt("Raum-Pad frei") if callable(schritt) else None
        if ctx is not None:
            ctx.__enter__()
        try:
            for (fid, attr, kopf), (vorher, mein) in eigene.items():
                try:
                    jetzt = state.get_programmer_value(fid, attr, head=kopf)
                except Exception:
                    continue
                if jetzt != mein:
                    continue            # inzwischen fremd ueberschrieben
                if vorher is None:
                    key = attr if kopf is None else state._head_key(fid, attr, kopf)
                    state.clear_programmer_value(fid, key)
                else:
                    state.set_programmer_value(fid, attr, vorher, head=kopf)
        finally:
            if ctx is not None:
                ctx.__exit__(None, None, None)
        self.update()
        return True

    def einschalten(self):
        self.aktiv = True
        self.anwenden()
        self.update()

    def ziel_setzen(self, x: float, z: float):
        """Zielpunkt setzen (Meter) und — wie ein Tipp — einschalten."""
        from src.core.stage.raum_pad import BODEN
        self.ziel = (round(float(x), 2), round(float(z), 2))
        self.flaeche = BODEN
        self.einschalten()

    def _abw_ziel(self, a: float, b: float):
        """Aufgeklappt: Abwicklungspunkt (m) -> Ziel (Flaeche + Raumpunkt)."""
        flaeche, (x, y, z) = self.aufklappung().raumpunkt(a, b, self.hoehe)
        self.flaeche = flaeche
        self.ziel = (round(x, 2), round(z, 2))
        if not self.auf_boden():
            self.wand_hoehe = round(y, 2)

    def ziel_setzen_abwicklung(self, a: float, b: float):
        """Aufgeklappt: Tipp auf ``(a, b)`` (Meter in der Abwicklung) — wie ein
        Tipp einschalten."""
        self._abw_ziel(a, b)
        self.einschalten()

    def set_ansicht(self, ansicht: str):
        self.ansicht = ansicht if ansicht in ANSICHTEN else DRAUFSICHT
        self.update()

    def set_waende(self, waende):
        from src.core.stage.raum_pad import waende_normal
        self.waende = waende_normal(waende)
        self.update()

    def hoehe_setzen(self, h: float):
        """Zielhoehe fuer den Boden (bei einem Wandziel wirkungslos fuer die
        Ausgabe — der Wert wird trotzdem gemerkt)."""
        raum = self._raum()
        self.hoehe = max(0.0, min(float(raum.hoehe), float(h)))
        if self.aktiv:
            self.anwenden()
        self.update()

    def release_if_held(self) -> bool:
        """Bankwechsel: ein nur gehaltenes Ziel (Lock AUS) freigeben."""
        if self._zug is not None and not self.position_lock and self.aktiv:
            self._zug = None
            return self.freigeben()
        self._zug = None
        return False

    # ── Maus / Finger ──────────────────────────────────────────────────────

    def _zone_bei(self, p: QPoint) -> str | None:
        z = self._zonen()
        for name in ("an", "lock", "hoehe"):
            if z[name].contains(p):
                return name
        if self.ansicht == AUFGEKLAPPT:
            auf = self.aufklappung()
            for name in auf.flaechen:
                rr = self.flaeche_px(name, auf)
                if rr is not None and rr.adjusted(-0.5, -0.5, 0.5, 0.5).contains(QPointF(p)):
                    return "pad"
            return None
        pad, _s = self._abbildung()
        if pad.contains(QPointF(p)):
            return "pad"
        return None

    def _pad_ziel(self, p: QPoint, einschalten: bool):
        """Pad-Druck/-Zug an Pixel ``p`` in der aktuellen Ansicht."""
        if self.ansicht == AUFGEKLAPPT:
            self._abw_ziel(*self._px_zu_ab(p))
        else:
            from src.core.stage.raum_pad import BODEN
            x, z = self._px_zu_welt(p)
            self.ziel = (round(x, 2), round(z, 2))
            self.flaeche = BODEN
        if einschalten:
            self.einschalten()
        else:
            self.aktiv = True
            self.anwenden()
            self.update()

    def mousePressEvent(self, event):
        if self._edit_mode:
            super().mousePressEvent(event)
            return
        if self._run_input_blocked():
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            event.accept()
            return
        p = event.position().toPoint()
        zone = self._zone_bei(p)
        self._zug = zone
        if zone == "pad":
            self._pad_ziel(p, einschalten=True)
        elif zone == "hoehe":
            if self.auf_boden():
                self.hoehe_setzen(self._hoehe_aus_px(p))
            else:
                self._zug = None          # Wandziel: Regler ausgegraut
        elif zone == "an" and not self.position_lock and self.ziel is not None:
            self.einschalten()            # Lock AUS: nur solange gedrueckt
        event.accept()

    def mouseMoveEvent(self, event):
        if self._edit_mode:
            super().mouseMoveEvent(event)
            return
        if self._run_input_blocked() or self._zug is None:
            event.accept()
            return
        p = event.position().toPoint()
        if self._zug == "pad":
            self._pad_ziel(p, einschalten=False)
        elif self._zug == "hoehe":
            self.hoehe_setzen(self._hoehe_aus_px(p))
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._edit_mode:
            super().mouseReleaseEvent(event)
            return
        zug, self._zug = self._zug, None
        if self._run_input_blocked() or zug is None:
            event.accept()
            return
        p = event.position().toPoint()
        if zug in ("pad", "an") and not self.position_lock:
            self.freigeben()
        elif zug == "an" and self._zonen()["an"].contains(p):
            if self.aktiv:
                self.freigeben()
            elif self.ziel is not None:
                self.einschalten()
        elif zug == "lock" and self._zonen()["lock"].contains(p):
            self.position_lock = not self.position_lock
            self.update()
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if self._edit_mode:
            super().mouseDoubleClickEvent(event)
            return
        # Doppeltipp im Betrieb = zwei Tipps (kein Eigenschaften-Dialog).
        self.mousePressEvent(event)

    # ── Zeichnen ───────────────────────────────────────────────────────────

    def _male_raster(self, p, rr: QRectF, s: float, u0: float, v0: float):
        """1-m-Raster in ``rr``; ``u0``/``v0`` = Meterwert am linken/oberen Rand."""
        p.setPen(QPen(QColor("#1f2937"), 1))
        if s <= 0:
            return
        u = math.ceil(u0 - 1e-9)
        while u <= u0 + rr.width() / s + 1e-9:
            px = rr.x() + (u - u0) * s
            p.drawLine(QPointF(px, rr.top()), QPointF(px, rr.bottom()))
            u += 1
        v = math.ceil(v0 - 1e-9)
        while v <= v0 + rr.height() / s + 1e-9:
            py = rr.y() + (v - v0) * s
            p.drawLine(QPointF(rr.left(), py), QPointF(rr.right(), py))
            v += 1

    def _male_draufsicht(self, p, raum, klein):
        pad, s = self._abbildung(raum)
        p.fillRect(pad, QColor("#111827"))
        self._male_raster(p, pad, s, raum.x0, raum.z0)
        p.setPen(QPen(QColor("#374151"), 1))
        p.drawRect(pad)
        p.setFont(klein)
        p.setPen(QColor("#6e7681"))
        p.drawText(pad.adjusted(0, 2, 0, 0), Qt.AlignmentFlag.AlignTop
                   | Qt.AlignmentFlag.AlignHCenter, "Rückwand")
        p.drawText(pad.adjusted(0, 0, 0, -2), Qt.AlignmentFlag.AlignBottom
                   | Qt.AlignmentFlag.AlignHCenter, "Publikum")
        p.drawText(pad.adjusted(4, 0, 0, -2), Qt.AlignmentFlag.AlignBottom
                   | Qt.AlignmentFlag.AlignLeft,
                   f"{raum.breite:.0f}×{raum.tiefe:.0f} m".replace(".", ","))
        ziel_px = (self._welt_zu_px(self.ziel[0], self.ziel[1], raum, pad, s)
                   if self.ziel is not None else None)
        return pad, s, ziel_px, pad.adjusted(0, 0, -4, -16)

    def _male_aufgeklappt(self, p, raum, klein):
        from src.core.stage.raum_pad import BODEN, FLAECHEN_NAMEN
        auf = self.aufklappung(raum)
        rahmen, s = self._abw_abbildung(auf)
        p.setFont(klein)
        for name, (a0, b0, a1, b1) in auf.rechtecke().items():
            rr = QRectF(self._ab_zu_px(a0, b0, rahmen, s), self._ab_zu_px(a1, b1, rahmen, s))
            p.fillRect(rr, QColor("#111827") if name == BODEN else QColor("#161b22"))
            # Raster: Boden in x/z, Waende in ihren eigenen Metern ab der Kante
            self._male_raster(p, rr, s, a0, b0)
            p.setPen(QPen(QColor("#374151"), 1))
            p.drawRect(rr)
            p.setPen(QColor("#6e7681"))
            p.drawText(rr.adjusted(2, 2, -2, -2), Qt.AlignmentFlag.AlignCenter
                       if name != BODEN else Qt.AlignmentFlag.AlignTop
                       | Qt.AlignmentFlag.AlignHCenter, FLAECHEN_NAMEN[name])
            # Zielhoehe des Bodens als gestrichelte Linie auf der Wand
            if name != BODEN and self.hoehe > 0:
                q0 = auf.abwicklung(name, (raum.x0, self.hoehe, raum.z0))
                q1 = auf.abwicklung(name, (raum.x1, self.hoehe, raum.z1))
                p.setPen(QPen(QColor(88, 166, 255, 110), 1, Qt.PenStyle.DashLine))
                p.drawLine(self._ab_zu_px(*q0, rahmen, s), self._ab_zu_px(*q1, rahmen, s))
        # Klappkanten etwas heller
        boden = self.flaeche_px(BODEN, auf)
        p.setPen(QPen(QColor("#4b5563"), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(boden)
        p.setPen(QColor("#6e7681"))
        p.drawText(boden.adjusted(4, 0, 0, -2), Qt.AlignmentFlag.AlignBottom
                   | Qt.AlignmentFlag.AlignLeft,
                   f"{raum.breite:.0f}×{raum.tiefe:.0f}×{raum.hoehe:.0f} m".replace(".", ","))
        ziel_px = None
        ziel = self.ziel_3d()
        if ziel is not None and self.flaeche in auf.flaechen:
            ziel_px = self._ab_zu_px(*auf.abwicklung(self.flaeche, ziel), rahmen, s)
        return boden, s, ziel_px, rahmen.adjusted(0, 0, -4, -2)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect().adjusted(1, 1, -1, -1), self._bg_color)
        z = self._zonen()
        raum = self._raum()
        klein = QFont("Segoe UI", 8)
        mittel = QFont("Segoe UI", 10 if touch_aktiv() else 8)
        mittel.setBold(True)

        if self.ansicht == AUFGEKLAPPT:
            boden, s, ziel_px, text_rect = self._male_aufgeklappt(p, raum, klein)
        else:
            boden, s, ziel_px, text_rect = self._male_draufsicht(p, raum, klein)

        try:
            mit, ohne = self.koepfe()
        except Exception:
            mit, ohne = [], []
        try:
            weg = set(self.unerreichbar())
        except Exception:
            weg = set()
        # Linien Kopf -> Ziel
        if ziel_px is not None and self.aktiv:
            p.setPen(QPen(QColor(255, 92, 138, 140), 1))
            for _fid, _f, _k, pos in mit:
                p.drawLine(self._welt_zu_px(pos[0], pos[2], raum, boden, s), ziel_px)
        # Koepfe (auf dem Boden an ihrem Standort; haengende mit Hoehe)
        r_kopf = 9 if touch_aktiv() else 7
        p.setFont(klein)
        for fid, _f, _k, pos in mit:
            c = self._welt_zu_px(pos[0], pos[2], raum, boden, s)
            p.setPen(QPen(QColor("#0d1117"), 1))
            p.setBrush(_KOPF)
            p.drawEllipse(c, r_kopf, r_kopf)
            p.setPen(QColor("#0d1117"))
            p.drawText(QRectF(c.x() - r_kopf, c.y() - r_kopf, 2 * r_kopf, 2 * r_kopf),
                       Qt.AlignmentFlag.AlignCenter, str(fid))
            if fid in weg:
                # Ziel nicht erreichbar: roter Ring + „!" statt still begrenzt
                p.setPen(QPen(_ROT, 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(c, r_kopf + 3, r_kopf + 3)
                p.setPen(_ROT)
                p.drawText(QRectF(c.x() + r_kopf, c.y() - 2 * r_kopf, 2 * r_kopf, 2 * r_kopf),
                           Qt.AlignmentFlag.AlignCenter, "!")
            if self.ansicht == AUFGEKLAPPT and pos[1] > 0.3:
                p.setPen(QColor("#8b949e"))
                p.drawText(QRectF(c.x() - 30, c.y() + r_kopf, 60, 12),
                           Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                           f"{pos[1]:.1f} m".replace(".", ","))
        # Koepfe ohne Standort: gelb gestrichelt am linken oberen Rand
        for i, (fid, _f, _k, _pos) in enumerate(ohne):
            c = QPointF(boden.x() + 4 + r_kopf + i * (2 * r_kopf + 4), boden.y() + 16 + r_kopf)
            p.setPen(QPen(_GELB, 1.5, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, r_kopf, r_kopf)
            p.setPen(_GELB)
            p.drawText(QRectF(c.x() - r_kopf, c.y() - r_kopf, 2 * r_kopf, 2 * r_kopf),
                       Qt.AlignmentFlag.AlignCenter, str(fid))
        if ohne:
            p.setPen(_GELB)
            p.drawText(boden.adjusted(4, 16 + 2 * r_kopf + 4, -4, 0),
                       Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                       "ohne Position – fährt nicht mit")
        if not mit and not ohne:
            p.setPen(QColor("#6e7681"))
            p.drawText(boden, Qt.AlignmentFlag.AlignCenter,
                       "Keine Moving Heads zugeordnet\n(Bearbeiten → Doppelklick)")
        # Zielmarke + Koordinaten
        if ziel_px is not None:
            farbe = _ZIEL if self.aktiv else QColor("#6e7681")
            p.setPen(QPen(farbe, 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(ziel_px, 8, 8)
            p.drawLine(ziel_px + QPointF(-12, 0), ziel_px + QPointF(12, 0))
            p.drawLine(ziel_px + QPointF(0, -12), ziel_px + QPointF(0, 12))
        if self.ziel is not None:
            p.setPen(_ZIEL if self.aktiv else QColor("#6e7681"))
            p.setFont(klein)
            # eine Zeile ueber „Publikum"/Raumgroesse, damit nichts ueberlappt
            p.drawText(text_rect, Qt.AlignmentFlag.AlignBottom
                       | Qt.AlignmentFlag.AlignRight, self.koordinaten_text())

        # Schalter
        p.setFont(mittel)
        for name, an, text in (("an", self.aktiv, "AN" if self.aktiv else "AUS"),
                               ("lock", self.position_lock,
                                "Lock AN" if self.position_lock else "Lock AUS")):
            rr = z[name]
            p.setPen(QPen(QColor("#484f58"), 1))
            p.setBrush(_AN if an else _AUS)
            p.drawRoundedRect(rr.adjusted(0, 0, -1, -1), 4, 4)
            p.setPen(QColor("#ffffff"))
            p.drawText(rr, Qt.AlignmentFlag.AlignCenter, text)
        p.setPen(self._fg_color)
        p.setFont(klein)
        p.drawText(z["titel"], Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                   self.caption)

        # Zielhoehe — bei einem Wandziel ausgegraut, mit der Wandhoehe
        hz = z["hoehe"]
        boden_ziel = self.auf_boden()
        p.setPen(QColor("#c9d1d9") if boden_ziel else QColor("#6e7681"))
        p.setFont(mittel)
        text = (f"Höhe {self.hoehe:.1f} m" if boden_ziel
                else f"Wand {self.wand_hoehe:.1f} m").replace(".", ",")
        p.drawText(QRect(hz.x(), hz.y(), self._hoehe_text_b(), hz.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        bahn = hz.adjusted(self._hoehe_text_b(), 0, -8, 0)
        my = bahn.center().y()
        p.setPen(QPen(QColor("#30363d") if boden_ziel else QColor("#21262d"), 4))
        p.drawLine(bahn.left(), my, bahn.right(), my)
        wert = self.hoehe if boden_ziel else self.wand_hoehe
        frac = max(0.0, min(1.0, wert / raum.hoehe)) if raum.hoehe > 0 else 0.0
        gx = bahn.left() + frac * bahn.width()
        p.setPen(QPen(QColor("#0d1117"), 1))
        p.setBrush(QColor("#58a6ff") if boden_ziel else QColor("#484f58"))
        gr = 9 if touch_aktiv() else 6
        p.drawEllipse(QPointF(gx, my), gr, gr)
        p.end()
        self._tooltip_setzen(ohne, sorted(weg))

    def koordinaten_text(self) -> str:
        if self.ziel is None:
            return ""
        from src.core.stage.raum_pad import FLAECHEN_NAMEN
        if self.auf_boden():
            return (f"x {self.ziel[0]:.1f} m · z {self.ziel[1]:.1f} m · "
                    f"H {self.hoehe:.1f} m").replace(".", ",")
        return (f"{FLAECHEN_NAMEN.get(self.flaeche, self.flaeche)} · "
                f"x {self.ziel[0]:.1f} m · z {self.ziel[1]:.1f} m · "
                f"H {self.wand_hoehe:.1f} m").replace(".", ",")

    def _tooltip_setzen(self, ohne, weg=()):
        teile = ["Raum-Pad: Ziel antippen – alle zugeordneten Moving Heads zielen darauf."]
        if ohne:
            teile.append("Ohne Position im Visualizer (fahren NICHT mit): "
                         + ", ".join(str(f) for f, *_ in ohne)
                         + ". Im 3D-Visualizer platzieren bzw. einmessen.")
        if weg:
            teile.append("Ziel außerhalb des Bewegungsbereichs (zeigen daneben, rot "
                         "markiert): " + ", ".join(str(f) for f in weg) + ".")
        text = "\n".join(teile)
        if self.toolTip() != text:
            self.setToolTip(text)

    # ── Eigenschaften ──────────────────────────────────────────────────────

    def _open_properties(self):
        state = _state()
        from src.core.stage.raum_pad import bewegung
        dlg = QDialog(self)
        dlg.setWindowTitle("Raum-Pad Einstellungen")
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)
        ansicht_cb, wand_boxen = self._ansicht_bedienung(form, live=False)
        lay.addLayout(form)
        lay.addWidget(QLabel("Moving Heads (nur Geräte mit Pan/Tilt):"))
        liste = QListWidget()
        try:
            patch = list(state.get_patched_fixtures())
        except Exception:
            patch = []
        for f in patch:
            if bewegung(f, _kanaele(f)) < 1:
                continue
            it = QListWidgetItem(f"{f.fid}  {getattr(f, 'label', '') or ''}")
            it.setData(Qt.ItemDataRole.UserRole, int(f.fid))
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if f.fid in self._fixture_ids
                             else Qt.CheckState.Unchecked)
            liste.addItem(it)
        lay.addWidget(liste)
        uebernehmen = QPushButton("Aktuelle Auswahl übernehmen")

        def _auswahl():
            try:
                sel = set(int(x) for x in state.get_selected_fids())
            except Exception:
                sel = set()
            for i in range(liste.count()):
                it = liste.item(i)
                it.setCheckState(Qt.CheckState.Checked
                                 if it.data(Qt.ItemDataRole.UserRole) in sel
                                 else Qt.CheckState.Unchecked)
        uebernehmen.clicked.connect(_auswahl)
        lay.addWidget(uebernehmen)
        lay.addWidget(QLabel("Gruppen (es fahren nur deren Moving Heads):"))
        gliste = QListWidget()
        try:
            gruppen = [g.get("name") for g in state.list_fixture_groups() if g.get("name")]
        except Exception:
            gruppen = []
        for name in sorted(set(gruppen) | set(self.gruppen)):
            it = QListWidgetItem(name)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if name in self.gruppen
                             else Qt.CheckState.Unchecked)
            gliste.addItem(it)
        lay.addWidget(gliste)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            war_an = self.aktiv
            self.freigeben()
            self.caption = cap.text() or self.caption
            self._fixture_ids = [liste.item(i).data(Qt.ItemDataRole.UserRole)
                                 for i in range(liste.count())
                                 if liste.item(i).checkState() == Qt.CheckState.Checked]
            self.gruppen = [gliste.item(i).text() for i in range(gliste.count())
                            if gliste.item(i).checkState() == Qt.CheckState.Checked]
            self.set_ansicht(ansicht_cb.currentText())
            self.set_waende([w for w, cb in wand_boxen.items() if cb.isChecked()])
            if war_an and self.position_lock:
                self.einschalten()
            self.update()

    def _ansicht_bedienung(self, form, live: bool):
        """Ansicht-Auswahl + Wand-Haken in ``form``. ``live``: jede Aenderung
        wirkt sofort (Inspector)."""
        from src.core.stage.raum_pad import FLAECHEN_NAMEN, WAENDE
        cb = QComboBox()
        cb.setObjectName("raumpad_ansicht")
        cb.addItems(list(ANSICHTEN))
        cb.setCurrentText(self.ansicht if self.ansicht in ANSICHTEN else DRAUFSICHT)
        cb.setToolTip("Draufsicht: nur der Boden. Aufgeklappt: Boden und Wände als "
                      "auseinandergefalteter Raum – auch Wände sind Ziele.")
        form.addRow("Ansicht:", cb)
        boden = QCheckBox(FLAECHEN_NAMEN["boden"])
        boden.setChecked(True)
        boden.setEnabled(False)
        boden.setToolTip("Der Boden ist immer dabei.")
        form.addRow("Flächen:", boden)
        boxen = {}
        for w in WAENDE:
            k = QCheckBox(FLAECHEN_NAMEN[w])
            k.setObjectName(f"raumpad_wand_{w}")
            k.setChecked(w in self.waende)
            form.addRow("", k)
            boxen[w] = k

        def _waende_an(on: bool):
            for k in boxen.values():
                k.setEnabled(on)
        _waende_an(self.ansicht == AUFGEKLAPPT)
        cb.currentTextChanged.connect(lambda t: _waende_an(t == AUFGEKLAPPT))
        if live:
            cb.currentTextChanged.connect(self.set_ansicht)
            for k in boxen.values():
                k.toggled.connect(lambda _on: self.set_waende(
                    [w for w, x in boxen.items() if x.isChecked()]))
        return cb, boxen

    def build_inspector_body(self, host=None):
        """Inspector: Ansicht + Wände live, Zuordnung ueber den Dialog."""
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 6, 0, 0)
        form = QFormLayout()
        self._ansicht_bedienung(form, live=True)
        v.addLayout(form)
        knopf = QPushButton("Moving Heads zuordnen…")
        knopf.setObjectName("raumpad_zuordnen")
        knopf.clicked.connect(self._open_properties)
        v.addWidget(knopf)
        v.addStretch(1)
        self._inspector_apply = lambda: None
        return body

    # ── Serialisierung ─────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["fixture_ids"] = [int(f) for f in self._fixture_ids]
        d["gruppen"] = list(self.gruppen)
        d["ziel"] = list(self.ziel) if self.ziel is not None else None
        d["hoehe"] = float(self.hoehe)
        d["position_lock"] = bool(self.position_lock)
        d["ansicht"] = self.ansicht
        d["waende"] = list(self.waende)
        d["flaeche"] = self.flaeche
        d["wand_hoehe"] = float(self.wand_hoehe)
        return d

    def apply_dict(self, d: dict):
        if self._eigene:
            self.freigeben()
        super().apply_dict(d)
        try:
            self._fixture_ids = [int(f) for f in (d.get("fixture_ids") or [])]
        except (TypeError, ValueError):
            self._fixture_ids = []
        self.gruppen = [str(g) for g in (d.get("gruppen") or []) if g]
        z = d.get("ziel")
        try:
            self.ziel = (float(z[0]), float(z[1])) if z else None
        except (TypeError, ValueError, IndexError):
            self.ziel = None
        try:
            self.hoehe = max(0.0, float(d.get("hoehe", 0.0) or 0.0))
        except (TypeError, ValueError):
            self.hoehe = 0.0
        self.position_lock = d.get("position_lock", True) is not False
        # Teil B — alte Shows ohne diese Schluessel: Draufsicht, alle Waende,
        # Ziel auf dem Boden.
        from src.core.stage.raum_pad import BODEN, FLAECHEN, WAENDE, waende_normal
        a = d.get("ansicht", DRAUFSICHT)
        self.ansicht = a if a in ANSICHTEN else DRAUFSICHT
        self.waende = waende_normal(d["waende"]) if "waende" in d else tuple(WAENDE)
        fl = d.get("flaeche", BODEN)
        self.flaeche = fl if fl in FLAECHEN else BODEN
        try:
            self.wand_hoehe = max(0.0, float(d.get("wand_hoehe", 0.0) or 0.0))
        except (TypeError, ValueError):
            self.wand_hoehe = 0.0
        self.aktiv = False
        self.update()
