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
import time

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QWindow
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout,
                               QWidget)

from .vc_style import touch_aktiv
from .vc_widget import VCWidget
from src.ui.abbau import abbau_still

_GELB = QColor("#e3b341")
# UI-136: nach einer Freigabe steht so lange „freigegeben" an der Marke
FREI_HINWEIS_S = 2.5
_FREI = QColor("#8b949e")
_AN = QColor("#2ea043")
_AUS = QColor("#30363d")
_ZIEL = QColor("#ff5c8a")
_KOPF = QColor("#58a6ff")
_ROT = QColor("#f85149")

DRAUFSICHT = "Draufsicht"
AUFGEKLAPPT = "Aufgeklappt"
ANSICHTEN = (DRAUFSICHT, AUFGEKLAPPT)

#: UI-143: kurze Flaechennamen, wenn der volle Name nicht passt
_KURZNAMEN = {"rueckwand": "hinten", "links": "links", "rechts": "rechts", "vorn": "vorn"}


class _Text:
    """UI-143: eine Beschriftung des Pads. ``varianten``: Liste
    ``(rechteck, ausrichtung, text, schrift)`` in Wunschreihenfolge; gesetzt
    wird die erste, die in ``flaeche`` passt und nichts ueberdeckt."""
    __slots__ = ("art", "flaeche", "varianten", "farbe", "ueber_koepfe", "kreis")

    def __init__(self, art, flaeche, varianten, farbe, ueber_koepfe=False, kreis=None):
        self.art = art
        self.flaeche = QRectF(flaeche)
        self.varianten = [(QRectF(r), f, t, s) for r, f, t, s in varianten]
        self.farbe = farbe
        self.ueber_koepfe = ueber_koepfe
        #: ``(mitte, radius)``: die Schrift muss ganz im Kreis liegen (Kopfnummer
        #: in Kreisfarbe — was ueber den Kreis hinausragt, ist unsichtbar)
        self.kreis = kreis


def _ueberlappt(a: QRectF, b: QRectF) -> bool:
    r = a.intersected(b)
    return r.width() > 0.5 and r.height() > 0.5


def _innen(flaeche: QRectF, r: QRectF) -> bool:
    return flaeche.adjusted(-0.5, -0.5, 0.5, 0.5).contains(r)


def _tinte_im_kreis(p, br: QRectF, text: str, font: QFont, mitte: QPointF, r: float) -> bool:
    """Liegt die tatsaechlich gemalte Schrift (ohne Zeilenabstand) von
    ``text`` im Kasten ``br`` ganz im Kreis um ``mitte`` mit Radius ``r``?"""
    fm = QFontMetricsF(font, p.device())
    tinte = fm.tightBoundingRect(text)
    grund = br.top() + fm.ascent()                    # Grundlinie der Zeile
    x0 = br.left() + (br.width() - fm.horizontalAdvance(text)) / 2.0
    tr = QRectF(x0 + tinte.left(), grund + tinte.top(), tinte.width(), tinte.height())
    r2 = (r + 0.5) ** 2
    return all((q.x() - mitte.x()) ** 2 + (q.y() - mitte.y()) ** 2 <= r2
               for q in (tr.topLeft(), tr.topRight(), tr.bottomLeft(), tr.bottomRight()))


def _px_font(px: int) -> QFont:
    f = QFont("Segoe UI")
    f.setPixelSize(px)
    return f


def _state():
    from src.core.app_state import get_state
    return get_state()


def _kanaele(f):
    from src.core import app_state as A
    try:
        return list(A.get_channels_for_patched(f) or [])
    except Exception:
        return []


class _HaltWaechter(QObject):
    """Nur waehrend eines GEHALTENEN Ziels (Lock AUS) am QApplication: meldet
    ein abgebrochenes Halten — Touch-Abbruch durch das System, Fenster bzw.
    Programm verliert den Fokus. Dann kommt das Loslassen nie an, und ohne
    diesen Waechter bliebe das Ziel stehen (Nachpruefung UI-127)."""

    def __init__(self, pad):
        super().__init__()
        self._pad = pad

    def eventFilter(self, obj, ev):                      # noqa: N802 (Qt)
        t = ev.type()
        try:
            if t == QEvent.Type.TouchCancel and isinstance(obj, QWindow):
                self._pad._halten_abbrechen()
            elif t == QEvent.Type.ApplicationDeactivate:
                self._pad._halten_abbrechen()
            elif t == QEvent.Type.WindowDeactivate and obj is self._pad.window():
                self._pad._halten_abbrechen()
        except (RuntimeError, AttributeError):
            # Pad schon zerstoert (RuntimeError) oder mitten im Abbau — dann
            # fehlen ihm schon Attribute (AttributeError, einmal im Testlauf
            # zu UI-143 gesehen). Der Waechter haengt dann noch am Programm
            # und wuerde bei jedem Fokuswechsel wieder hineinlaufen: abhaengen.
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                app.removeEventFilter(self)
        return False


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
        self._waechter: _HaltWaechter | None = None       # nur waehrend Halten
        self._frei_seit: float | None = None              # UI-136: Zeitpunkt der Freigabe
        # UI-143: beim letzten Malen gesetzte Texte und Kopf-Kreise (abfragbar)
        self._gesetzte_texte: list = []
        self._kopf_kreise: dict = {}
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
            from src.core.stage.raum_pad import standort
            pos = standort(positionen.get(fid)) if positionen is not None else None
            if pos is not None:
                mit.append((fid, f, kan, pos))
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
                    jetzt = state.get_programmer_value(fid, attr, head=kopf)
                    if k not in self._eigene:
                        self._eigene[k] = [jetzt, None]
                    elif jetzt != self._eigene[k][1]:
                        # Inzwischen fremd ueberschrieben, jetzt zieht das Pad
                        # wieder drueber: beim Freigeben DIESEN Wert zurueck,
                        # nicht den von vor dem ersten Schreiben.
                        self._eigene[k][0] = jetzt
                    state.set_programmer_value(fid, attr, wert, head=kopf)
                    self._eigene[k][1] = state.get_programmer_value(fid, attr, head=kopf)
        finally:
            if ctx is not None:
                ctx.__exit__(None, None, None)
        return len(mit)

    def freigeben(self) -> bool:
        """Eigene Pan/Tilt/Fein-Werte zuruecknehmen (s. Modulkopf)."""
        if self.aktiv:
            self._frei_merken()
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

    def _frei_merken(self) -> None:
        """UI-136: die Marke zeigt kurz „freigegeben" — ein frei gegebenes Ziel
        blieb sonst sichtbar stehen und sah aus wie „klebt fest"."""
        self._frei_seit = time.monotonic()
        try:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(int(FREI_HINWEIS_S * 1000) + 50, self._frei_neu_malen)
        except Exception:
            pass

    def _frei_neu_malen(self) -> None:
        try:
            self.update()
        except RuntimeError:
            pass                        # Pad schon abgebaut

    def ziel_zustand(self) -> str | None:
        """UI-136: ``"aktiv"`` (Koepfe zielen), ``"frei"`` (Marke steht nur
        noch als Erinnerung, Ausgabe freigegeben) oder ``None`` (kein Ziel)."""
        if self.ziel is None:
            return None
        return "aktiv" if self.aktiv else "frei"

    def frei_hinweis(self) -> str:
        """„freigegeben" kurz nach einer Freigabe, sonst leer."""
        if self.aktiv or self._frei_seit is None:
            return ""
        if time.monotonic() - self._frei_seit > FREI_HINWEIS_S:
            return ""
        return "freigegeben"

    def einschalten(self):
        self._frei_seit = None
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

    def vor_entfernen(self) -> None:
        """CDX-72: Pad wird geloescht oder die Konsole neu geladen (``_clear``,
        Undo/Redo, Show laden): eigene Pan/Tilt-Werte freigeben, auch bei
        Lock AN. Fremd ueberschriebene Werte bleiben (s. ``freigeben``)."""
        self._zug = None
        self._waechter_aus()
        self.aktiv = False              # kein „freigegeben"-Hinweis mehr (Widget geht)
        if self._eigene:
            self.freigeben()

    def release_if_held(self) -> bool:
        """Bankwechsel: ein nur gehaltenes Ziel (Lock AUS) freigeben."""
        return self._halten_abbrechen()

    def _gehalten(self, zug) -> bool:
        """Haengt die Ausgabe an einem Druck (Lock AUS, Pad oder AN gedrueckt)?"""
        return zug in ("pad", "an") and not self.position_lock

    def _waechter_an(self):
        if self._waechter is None:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                self._waechter = _HaltWaechter(self)
                app.installEventFilter(self._waechter)

    def _waechter_aus(self):
        w, self._waechter = self._waechter, None
        if w is not None:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                app.removeEventFilter(w)
            w.deleteLater()

    def _halten_abbrechen(self) -> bool:
        """Ein Druck endet ohne Loslassen (Bankwechsel, Touch-Abbruch, Fokus
        weg, verdeckt): ein nur gehaltenes Ziel freigeben. Rueckgabe: True,
        wenn wirklich etwas freigegeben wurde."""
        try:
            zug, self._zug = self._zug, None
        except AttributeError:
            # Objekt im Abbau: Python hat seine Attribute schon geleert, Qt
            # schickt beim Zerstoeren aber noch ein hideEvent. Gesehen im
            # Testlauf zu UI-143 — die Ausnahme landete im gerade laufenden
            # paintEvent eines ANDEREN Pads (Maler blieb offen, danach
            # nativer Absturz beim Aufraeumen). Hier ist nichts mehr freizugeben.
            return False
        self._waechter_aus()
        if self._gehalten(zug) and self.aktiv:
            return self.freigeben()
        return False

    def set_position_lock(self, an: bool):
        """Lock umschalten. Lock AUS heisst „nur solange gedrueckt" — ein vorher
        eingerastetes Ziel wird deshalb sofort freigegeben."""
        self.position_lock = bool(an)
        if not self.position_lock and self.aktiv and self._zug is None:
            self.freigeben()
        self.update()

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
        if self._gehalten(zone):
            self._waechter_an()
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
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            # Das Loslassen ist verloren gegangen (z. B. Fenster dazwischen)
            self._halten_abbrechen()
            event.accept()
            return
        p = event.position().toPoint()
        if self._zug == "pad":
            self._pad_ziel(p, einschalten=False)
        elif self._zug == "hoehe":
            self.hoehe_setzen(self._hoehe_aus_px(p))
        event.accept()

    def mouseReleaseEvent(self, event):
        zug, self._zug = self._zug, None
        self._waechter_aus()
        # Ein gehaltenes Ziel endet mit dem Loslassen IMMER — auch wenn
        # waehrenddessen die Touch-Sperre oder der Bearbeiten-Modus anging.
        if self._gehalten(zug) and self.aktiv:
            self.freigeben()
            zug = None
        if self._edit_mode:
            super().mouseReleaseEvent(event)
            return
        if self._run_input_blocked() or zug is None:
            event.accept()
            return
        p = event.position().toPoint()
        if self._gehalten(zug):
            pass
        elif zug == "an" and self._zonen()["an"].contains(p):
            if self.aktiv:
                self.freigeben()
            elif self.ziel is not None:
                self.einschalten()
        elif zug == "lock" and self._zonen()["lock"].contains(p):
            self.set_position_lock(not self.position_lock)
        event.accept()

    @abbau_still
    def hideEvent(self, event):
        super().hideEvent(event)
        self._halten_abbrechen()      # verdeckt: das Loslassen kommt nie an

    @abbau_still
    def changeEvent(self, event):
        super().changeEvent(event)
        if (event.type() == QEvent.Type.ActivationChange
                and getattr(self, "_zug", None) is not None
                and not self.isActiveWindow()):
            self._halten_abbrechen()

    def mouseDoubleClickEvent(self, event):
        if self._edit_mode:
            super().mouseDoubleClickEvent(event)
            return
        # Doppeltipp im Betrieb = zwei Tipps (kein Eigenschaften-Dialog).
        self.mousePressEvent(event)

    # ── Zeichnen ───────────────────────────────────────────────────────────
    #
    # UI-143: Alle Texte des Pads laufen ueber ``_texte_setzen``. Jede
    # Beschriftung bringt ihre Flaeche (aus der sie nie herausragen darf) und
    # eine Liste von Varianten (kuerzer, kleiner, anderer Platz) mit; gesetzt
    # wird die erste Variante, die in die Flaeche passt und weder einen schon
    # gesetzten Text noch (ausser Nummern/Warnmarken) einen Kopf-Kreis
    # ueberdeckt. Passt keine, bleibt der Text weg — er steht dann im Tooltip.
    # Die gesetzten Rechtecke sind ueber ``gezeichnete_texte()`` abfragbar.
    # Nur das Zeichnen; Geometrie und Zielrechnung bleiben unberuehrt.

    def gezeichnete_texte(self) -> list[tuple[str, QRectF, QRectF, str]]:
        """``(art, text_rechteck, flaeche, text)`` aller beim letzten Malen
        gesetzten Texte."""
        return list(self._gesetzte_texte)

    def kopf_kreise(self) -> dict[int, tuple[QPointF, float]]:
        """``{fid: (mitte, radius)}`` der beim letzten Malen gezeichneten Koepfe
        mit Standort."""
        return dict(self._kopf_kreise)

    def _texte_setzen(self, p, texte, kreise) -> None:
        belegt: list[QRectF] = []
        gesetzt = []
        for t in texte:
            for rect, flags, text, font in t.varianten:
                if not text or rect.width() <= 0 or rect.height() <= 0:
                    continue
                p.setFont(font)
                br = p.boundingRect(rect, flags, text)
                if not _innen(t.flaeche, br):
                    continue
                if t.kreis is not None and not _tinte_im_kreis(p, br, text, font, *t.kreis):
                    continue
                if any(_ueberlappt(br, b) for b in belegt):
                    continue
                if not t.ueber_koepfe and any(_ueberlappt(br, k) for k in kreise):
                    continue
                p.setPen(t.farbe)
                p.drawText(rect, flags, text)
                belegt.append(br)
                gesetzt.append((t.art, br, QRectF(t.flaeche), text))
                break
        self._gesetzte_texte = gesetzt

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

    def _male_draufsicht(self, p, raum, klein, texte):
        pad, s = self._abbildung(raum)
        p.fillRect(pad, QColor("#111827"))
        self._male_raster(p, pad, s, raum.x0, raum.z0)
        p.setPen(QPen(QColor("#374151"), 1))
        p.drawRect(pad)
        grau = QColor("#6e7681")
        oben = Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter
        unten = Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter
        texte.append(_Text("flaeche", pad, [(pad.adjusted(0, 2, 0, 0), oben, "Rückwand", klein),
                                            (pad.adjusted(0, 2, 0, 0), oben, "hinten", klein)],
                           grau))
        texte.append(_Text("flaeche", pad, [(pad.adjusted(0, 0, 0, -2), unten, "Publikum", klein),
                                            (pad.adjusted(0, 0, 0, -2), unten, "vorn", klein)],
                           grau))
        texte.append(_Text("groesse", pad, [(
            pad.adjusted(4, 0, 0, -2), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
            f"{raum.breite:.0f}×{raum.tiefe:.0f} m".replace(".", ","), klein)], grau))
        ziel_px = (self._welt_zu_px(self.ziel[0], self.ziel[1], raum, pad, s)
                   if self.ziel is not None else None)
        return pad, s, ziel_px, pad.adjusted(0, 0, -4, -16)

    def _male_aufgeklappt(self, p, raum, klein, texte):
        from src.core.stage.raum_pad import BODEN, FLAECHEN_NAMEN
        auf = self.aufklappung(raum)
        rahmen, s = self._abw_abbildung(auf)
        grau = QColor("#6e7681")
        for name, (a0, b0, a1, b1) in auf.rechtecke().items():
            rr = QRectF(self._ab_zu_px(a0, b0, rahmen, s), self._ab_zu_px(a1, b1, rahmen, s))
            p.fillRect(rr, QColor("#111827") if name == BODEN else QColor("#161b22"))
            # Raster: Boden in x/z, Waende in ihren eigenen Metern ab der Kante
            self._male_raster(p, rr, s, a0, b0)
            p.setPen(QPen(QColor("#374151"), 1))
            p.drawRect(rr)
            # UI-143: Name der Flaeche, bei wenig Platz gekuerzt, sonst weg
            flags = (Qt.AlignmentFlag.AlignCenter if name != BODEN
                     else Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            innen = rr.adjusted(2, 2, -2, -2)
            namen = [FLAECHEN_NAMEN[name]]
            if _KURZNAMEN.get(name) and _KURZNAMEN[name] not in namen:
                namen.append(_KURZNAMEN[name])
            texte.append(_Text("flaeche", rr, [(innen, flags, n, klein) for n in namen], grau))
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
        texte.append(_Text("groesse", boden, [(
            boden.adjusted(4, 0, 0, -2), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
            f"{raum.breite:.0f}×{raum.tiefe:.0f}×{raum.hoehe:.0f} m".replace(".", ","), klein)],
            grau))
        ziel_px = None
        ziel = self.ziel_3d()
        if ziel is not None and self.flaeche in auf.flaechen:
            ziel_px = self._ab_zu_px(*auf.abwicklung(self.flaeche, ziel), rahmen, s)
        return boden, s, ziel_px, rahmen.adjusted(0, 0, -4, -2)

    @staticmethod
    def _kopf_radien(mitten, r_basis: float) -> list[float]:
        """UI-143: Radius je Kopf — so gross wie ``r_basis``, aber nie so gross,
        dass er den naechsten Nachbarn ueberdeckt (mindestens 3 px)."""
        radien = []
        for i, c in enumerate(mitten):
            nah = min((math.hypot(c.x() - d.x(), c.y() - d.y())
                       for j, d in enumerate(mitten) if j != i), default=math.inf)
            radien.append(max(3.0, min(float(r_basis), (nah - 1.0) / 2.0)))
        return radien

    @staticmethod
    def _hoehen_gruppen(eintraege, abstand) -> list[list[int]]:
        """UI-143: haengende Koepfe gleicher Hoehe, die im Bild naeher als
        ``abstand(hoehe_text)`` px beieinander haengen (auch ueber Nachbarn
        verkettet, z. B. eine Traverse), bekommen EINE gemeinsame Beschriftung.
        ``eintraege``: Liste ``(hoehe_text, mitte)``; Rueckgabe: Index-Gruppen."""
        eltern = list(range(len(eintraege)))

        def wurzel(i):
            while eltern[i] != i:
                eltern[i] = eltern[eltern[i]]
                i = eltern[i]
            return i

        for i, (hi, ci) in enumerate(eintraege):
            for j in range(i + 1, len(eintraege)):
                hj, cj = eintraege[j]
                if hi == hj and math.hypot(ci.x() - cj.x(), ci.y() - cj.y()) < abstand(hi):
                    eltern[wurzel(j)] = wurzel(i)
        gruppen: dict[int, list[int]] = {}
        for i in range(len(eintraege)):
            gruppen.setdefault(wurzel(i), []).append(i)
        return list(gruppen.values())

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
        # Texte nach Vorrang: zuerst gesetzt = gewinnt bei Platzmangel
        fest, warn, nummern, koord, hoehen, hinweise, flaechen = [], [], [], [], [], [], []

        if self.ansicht == AUFGEKLAPPT:
            boden, s, ziel_px, text_rect = self._male_aufgeklappt(p, raum, klein, flaechen)
        else:
            boden, s, ziel_px, text_rect = self._male_draufsicht(p, raum, klein, flaechen)

        try:
            mit, ohne = self.koepfe()
        except Exception:
            mit, ohne = [], []
        try:
            weg = set(self.unerreichbar())
        except Exception:
            weg = set()
        mitten = [self._welt_zu_px(pos[0], pos[2], raum, boden, s) for _f, _x, _k, pos in mit]
        # Linien Kopf -> Ziel
        if ziel_px is not None and self.aktiv:
            p.setPen(QPen(QColor(255, 92, 138, 140), 1))
            for c in mitten:
                p.drawLine(c, ziel_px)
        # Koepfe (auf dem Boden an ihrem Standort; haengende mit Hoehe)
        r_kopf = 9 if touch_aktiv() else 7
        radien = self._kopf_radien(mitten, r_kopf)
        self._kopf_kreise = {}
        kreise: list[QRectF] = []
        # kleiner als 9 px ist eine Nummer nicht mehr lesbar — dann lieber keine
        nr_fonts = [klein] + [_px_font(px) for px in (10, 9)]
        zentriert = Qt.AlignmentFlag.AlignCenter
        for (fid, _f, _k, pos), c, r in zip(mit, mitten, radien):
            p.setPen(QPen(QColor("#0d1117"), 1))
            p.setBrush(_KOPF)
            p.drawEllipse(c, r, r)
            self._kopf_kreise[fid] = (QPointF(c), r)
            quadrat = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
            kreise.append(quadrat)
            # Nummer nur, wenn sie in den Kreis passt (sonst im Tooltip)
            nummern.append(_Text("nummer", quadrat.adjusted(-1, -1, 1, 1),
                                 [(quadrat, zentriert, str(fid), f) for f in nr_fonts],
                                 QColor("#0d1117"), ueber_koepfe=True, kreis=(QPointF(c), r)))
            if fid in weg:
                # Ziel nicht erreichbar: roter Ring + „!" statt still begrenzt
                p.setPen(QPen(_ROT, 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(c, r + 3, r + 3)
                marke = QRectF(c.x() + r, c.y() - 2 * r_kopf, 2 * r_kopf, 2 * r_kopf)
                warn.append(_Text("warnung", QRectF(self.rect()), [(marke, zentriert, "!", klein)],
                                  _ROT, ueber_koepfe=True))
        # UI-143: Hoehen haengender Koepfe — gleiche Hoehe in einer Reihe nur
        # EINMAL („5× 4,5 m"), und nur, wo Platz ist
        if self.ansicht == AUFGEKLAPPT:
            fm = QFontMetricsF(klein)
            haengend = [(f"{pos[1]:.1f} m".replace(".", ","), c, r)
                        for (_fid, _f, _k, pos), c, r in zip(mit, mitten, radien) if pos[1] > 0.3]
            feld = QRectF(z["feld"])
            zeile_h = fm.height() + 2
            for gruppe in self._hoehen_gruppen([(h, c) for h, c, _r in haengend],
                                               lambda h: fm.horizontalAdvance(h) + 8):
                h = haengend[gruppe[0]][0]
                text = f"{len(gruppe)}× {h}" if len(gruppe) > 1 else h
                xs = [haengend[i][1].x() for i in gruppe]
                mx = (min(xs) + max(xs)) / 2.0
                b = max(fm.horizontalAdvance(text) + 8, max(xs) - min(xs))
                unter = max(haengend[i][1].y() + haengend[i][2] for i in gruppe) + 1
                ueber = min(haengend[i][1].y() - haengend[i][2] for i in gruppe) - 1
                hoehen.append(_Text("hoehe", feld, [
                    (QRectF(mx - b / 2, unter, b, zeile_h),
                     Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, text, klein),
                    (QRectF(mx - b / 2, ueber - zeile_h, b, zeile_h),
                     Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, text, klein)],
                    QColor("#8b949e")))
        # Koepfe ohne Standort: gelb gestrichelt am linken oberen Rand
        for i, (fid, _f, _k, _pos) in enumerate(ohne):
            c = QPointF(boden.x() + 4 + r_kopf + i * (2 * r_kopf + 4), boden.y() + 16 + r_kopf)
            p.setPen(QPen(_GELB, 1.5, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, r_kopf, r_kopf)
            quadrat = QRectF(c.x() - r_kopf, c.y() - r_kopf, 2 * r_kopf, 2 * r_kopf)
            kreise.append(quadrat)
            nummern.append(_Text("nummer", quadrat.adjusted(-1, -1, 1, 1),
                                 [(quadrat, zentriert, str(fid), f) for f in nr_fonts],
                                 _GELB, ueber_koepfe=True))
        oben_links = Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        if ohne:
            rr = boden.adjusted(4, 16 + 2 * r_kopf + 4, -4, 0)
            hinweise.append(_Text("hinweis", boden, [
                (rr, oben_links, "ohne Position – fährt nicht mit", klein),
                (rr, oben_links, "ohne Position", klein)], _GELB))
        if not mit and not ohne:
            hinweise.append(_Text("hinweis", boden, [
                (boden, zentriert, "Keine Moving Heads zugeordnet\n(Bearbeiten → Doppelklick)",
                 klein),
                (boden, zentriert, "Keine Moving Heads zugeordnet", klein),
                (boden, zentriert, "keine Köpfe", klein)], QColor("#6e7681")))
        # Zielmarke + Koordinaten. UI-136: frei gegeben ist die Marke nur noch
        # ein gestrichelter grauer Ring ohne Fadenkreuz (Linien zu den Koepfen
        # sind dann schon weg) — sonst sah ein freigegebenes Ziel aus, als
        # stuende es noch.
        if ziel_px is not None:
            # Beschriftungen weichen auch der Zielmarke aus
            kreise.append(QRectF(ziel_px.x() - 12, ziel_px.y() - 12, 24, 24))
            if self.aktiv:
                p.setPen(QPen(_ZIEL, 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(ziel_px, 8, 8)
                p.drawLine(ziel_px + QPointF(-12, 0), ziel_px + QPointF(12, 0))
                p.drawLine(ziel_px + QPointF(0, -12), ziel_px + QPointF(0, 12))
            else:
                p.setPen(QPen(_FREI, 1.5, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(ziel_px, 8, 8)
        if self.ziel is not None:
            frei = self.frei_hinweis()
            farbe = _ZIEL if self.aktiv else (QColor("#e6edf3") if frei else QColor("#6e7681"))
            # eine Zeile ueber „Publikum"/Raumgroesse, damit nichts ueberlappt
            k = self.koordinaten_text()
            kurz = k.replace(" m", "")
            varianten = ([f"freigegeben · {k}", f"freigegeben · {kurz}", "freigegeben"] if frei
                         else [k, kurz])
            unten_rechts = Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight
            koord.append(_Text("koordinaten", text_rect,
                               [(text_rect, unten_rechts, v, klein) for v in varianten], farbe))

        # Schalter
        for name, an, text in (("an", self.aktiv, "AN" if self.aktiv else "AUS"),
                               ("lock", self.position_lock,
                                "Lock AN" if self.position_lock else "Lock AUS")):
            rr = QRectF(z[name])
            p.setPen(QPen(QColor("#484f58"), 1))
            p.setBrush(_AN if an else _AUS)
            p.drawRoundedRect(rr.adjusted(0, 0, -1, -1), 4, 4)
            fest.append(_Text("schalter", rr, [(rr, zentriert, text, mittel)],
                              QColor("#ffffff"), ueber_koepfe=True))
        titel = QRectF(z["titel"])
        rechts_mitte = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        fest.append(_Text("titel", titel, [(titel, rechts_mitte, QFontMetricsF(klein).elidedText(
            self.caption, Qt.TextElideMode.ElideRight, max(0.0, titel.width() - 1)), klein)],
            self._fg_color, ueber_koepfe=True))

        # Zielhoehe — bei einem Wandziel ausgegraut, mit der Wandhoehe
        hz = z["hoehe"]
        boden_ziel = self.auf_boden()
        wert = self.hoehe if boden_ziel else self.wand_hoehe
        h_rect = QRectF(hz.x(), hz.y(), self._hoehe_text_b(), hz.height())
        links_mitte = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        fest.append(_Text("hoehe_leiste", h_rect, [
            (h_rect, links_mitte, t.replace(".", ","), mittel)
            for t in ((f"Höhe {wert:.1f} m" if boden_ziel else f"Wand {wert:.1f} m"),
                      f"{wert:.1f} m")],
            QColor("#c9d1d9") if boden_ziel else QColor("#6e7681"), ueber_koepfe=True))
        bahn = hz.adjusted(self._hoehe_text_b(), 0, -8, 0)
        my = bahn.center().y()
        p.setPen(QPen(QColor("#30363d") if boden_ziel else QColor("#21262d"), 4))
        p.drawLine(bahn.left(), my, bahn.right(), my)
        frac = max(0.0, min(1.0, wert / raum.hoehe)) if raum.hoehe > 0 else 0.0
        gx = bahn.left() + frac * bahn.width()
        p.setPen(QPen(QColor("#0d1117"), 1))
        p.setBrush(QColor("#58a6ff") if boden_ziel else QColor("#484f58"))
        gr = 9 if touch_aktiv() else 6
        p.drawEllipse(QPointF(gx, my), gr, gr)
        self._texte_setzen(p, fest + warn + nummern + koord + hoehen + hinweise + flaechen,
                           kreise)
        p.end()
        self._tooltip_setzen(ohne, sorted(weg), [(fid, pos[1]) for fid, _f, _k, pos in mit])

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

    def _tooltip_setzen(self, ohne, weg=(), hoehen=()):
        teile = ["Raum-Pad: Ziel antippen – alle zugeordneten Moving Heads zielen darauf."]
        # UI-143: Hoehen der haengenden Koepfe immer hier — im Bild stehen sie
        # nur, wo Platz ist (gleiche Hoehe einer Reihe nur einmal)
        nach_hoehe: dict[str, list] = {}
        for fid, h in hoehen:
            if h > 0.3:
                nach_hoehe.setdefault(f"{h:.1f} m".replace(".", ","), []).append(str(fid))
        if nach_hoehe:
            teile.append("Höhen: " + "; ".join(f"{h}: {', '.join(f)}"
                                               for h, f in nach_hoehe.items()))
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
