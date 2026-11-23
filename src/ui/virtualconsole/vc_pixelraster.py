"""VCPixelraster — auf eine LED-Matrix bzw. Kopf-Gruppe live malen (VCB-51).

Das Element zeigt das Raster einer Fixture-Gruppe (aufgeloest: Kopf-Zellen
``"fid:kopf"``, FM-20-Untergruppen-Bloecke) und laesst darauf mit Finger oder
Maus malen:

* **Pinsel** — Zelle(n) in der gewaehlten Farbe,
* **Radierer** — Zelle(n) wieder durchsichtig,
* **Füllen** — zusammenhaengende Flaeche gleicher Farbe umfaerben,
* **Löschen** — ganze Zeichnung weg (zweimal tippen: erst scharf, dann leer),
* **Auflösung** 1×1 / 2×2 / 4×4 — so viele Rasterzellen fasst ein Malpunkt
  zusammen (die Zeichnung selbst wird immer in voller Rasteraufloesung
  gehalten, Umschalten verliert nichts),
* **Merken / Abruf** — die aktuelle Zeichnung als Bild beim Element ablegen
  und gemerkte Bilder der Reihe nach wieder abrufen,
* **Pegel** — senkrechter Regler rechts: wie stark die Zeichnung ueber dem
  liegt, was sonst laeuft.

Ausgabe: ``src/core/engine/zeichen_ebene.py`` — eine eigene Ebene im Renderer
nach den Modify-Effekten und vor Mastern/Blackout. Sie schreibt nur
``color_r/g/b``, nie einen Dimmer (Farbe zieht den Dimmer nie mit).

Bedienen nur im Run-Modus und nicht bei Touch-Sperre; im Bearbeiten-Modus
verschiebt/skaliert die Maus das Element wie jedes andere. Die Bindung an eine
Gruppe (ueber ihre Kennung, Umbenennen loest sie nicht) oder direkt an ein
Matrix-Geraet kommt ueber Eigenschaften (nicht im Kiosk).
"""
from __future__ import annotations

import time

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QLabel, QLineEdit, QPushButton,
                               QToolTip, QVBoxLayout, QWidget)

from .vc_style import touch_aktiv
from .vc_widget import VCWidget

PINSEL = "pinsel"
RADIERER = "radierer"
FUELLEN = "fuellen"
WERKZEUGE = (PINSEL, RADIERER, FUELLEN)
AUFLOESUNGEN = (1, 2, 4)
MAX_BILDER = 12
LOESCHEN_SCHARF_S = 3.0

#: Knopfleiste in dieser Reihenfolge (Schluessel, Beschriftung)
KNOEPFE = (
    (PINSEL, "Pinsel"),
    (RADIERER, "Radierer"),
    (FUELLEN, "Füllen"),
    ("farbe", "Farbe"),
    ("aufloesung", "1×1"),
    ("loeschen", "Löschen"),
    ("merken", "Merken"),
    ("abruf", "Abruf"),
)

#: VCB-52: Erklaerung je Knopf (Tooltip; die Beschriftung kann gekuerzt sein)
KNOPF_HILFE = {
    PINSEL: "Pinsel: Zellen in der gewählten Farbe malen",
    RADIERER: "Radierer: Zellen wieder durchsichtig machen",
    FUELLEN: "Füllen: zusammenhängende Fläche gleicher Farbe umfärben",
    "farbe": "Farbe: Pinselfarbe wählen",
    "aufloesung": "Auflösung: wie viele Rasterzellen ein Malpunkt fasst",
    "loeschen": "Löschen: ganze Zeichnung weg (zweimal tippen, innerhalb 3 s)",
    "merken": "Merken: aktuelle Zeichnung als Bild ablegen",
    "abruf": "Abruf: gemerkte Bilder der Reihe nach abrufen",
}
#: Breitester Text, den ein Knopf zeigen kann (fuer die Spaltenzahl)
_BREITESTE = tuple(t for _k, t in KNOEPFE) + ("Sicher?", "Abruf 9/9")


def _state():
    from src.core.app_state import get_state
    return get_state()


def _ebenen():
    from src.core.engine.zeichen_ebene import EBENEN
    return EBENEN


def _schluessel(c: int, r: int) -> str:
    return f"{int(c)},{int(r)}"


def _farbe_text(c) -> str | None:
    q = QColor(c) if not isinstance(c, QColor) else c
    return q.name() if q.isValid() else None


class VCPixelraster(VCWidget):
    """Malflaeche ueber dem Raster einer Kopf-Gruppe."""

    MIN_SIZE = (200, 160)

    def __init__(self, caption: str = "Pixelraster", parent=None):
        super().__init__(caption, parent)
        self.gruppe: str = ""                       # Name der Gruppe (Anzeige/Altbestand)
        self.gruppe_uid: str = ""                   # Kennung der Gruppe (FM-20/VCB-42)
        self.geraet_fid: int | None = None          # Matrix-Geraet statt Gruppe
        self.pixel: dict[str, str] = {}             # "c,r" -> "#rrggbb"
        self.bilder: list[dict[str, str]] = []      # gemerkte Zeichnungen
        self.abruf_index: int = -1
        self.pegel: float = 1.0
        self.farbe: QColor = QColor("#ff0000")
        self.werkzeug: str = PINSEL
        self.aufloesung: int = 1
        self._raster: tuple[int, int, dict] | None = None   # (cols, rows, pos)
        self._zug: str | None = None                # "malen" / "pegel" / Knopf
        self._loeschen_scharf_bis = 0.0
        # VCB-52: nach Ablauf faellt 'Sicher?' sichtbar auf 'Löschen' zurueck
        # (vorher blieb die Anzeige stehen, der Tipp darauf loeschte nicht).
        self._loeschen_timer = QTimer(self)
        self._loeschen_timer.setSingleShot(True)
        self._loeschen_timer.timeout.connect(self._loeschen_entschaerfen)
        self._bg_color = QColor("#0d1117")
        self._fg_color = QColor("#e6edf3")
        self.resize(360, 260)

    # ── Bindung / Raster ──────────────────────────────────────────────────

    def gebunden(self) -> bool:
        return bool(self.gruppe or self.gruppe_uid or self.geraet_fid is not None)

    def _gruppe_ref(self, state):
        """``(gid, name)`` der gebundenen Gruppe oder ``None``.

        Kennung zuerst: sie bleibt beim Umbenennen (VCB-42), und eine
        geloeschte und gleichnamig neu angelegte Gruppe ist NICHT mehr die
        gemeinte (VCB-44) — dann gibt es kein Raster statt eines fremden.
        Ohne Kennung (Element aus der Zeit davor) per Name; die Kennung wird
        dabei nachgetragen (Migration beim Laden)."""
        steck = state.gruppen_steckbriefe()
        if steck is None:
            return None
        if self.gruppe_uid:
            for gid, (name, _ordner, uid) in sorted(steck.items()):
                if uid and uid == self.gruppe_uid:
                    self.gruppe = name
                    return gid, name
            return None
        for gid, (name, _ordner, uid) in sorted(steck.items()):
            if self.gruppe and name == self.gruppe:
                self.gruppe_uid = uid or ""
                return gid, name
        return None

    def _geraet_raster(self, state):
        """Raster eines einzelnen Matrix-Geraets: seine Kopf-Matrix (FM-21:
        ``grid_rows x grid_cols`` bzw. 1xN) — dieselbe Rechnung wie seine
        Auto-Kopf-Gruppe, aber ohne dass es die Gruppe geben muss."""
        from src.core.app_state import color_head_count, head_matrix_layout
        fx = next((f for f in state.get_patched_fixtures()
                   if int(f.fid) == int(self.geraet_fid)), None)
        if fx is None:
            return None
        n = int(color_head_count(fx) or 0)
        if n <= 1:
            return 1, 1, {"0,0": int(fx.fid)}
        cols, rows, plaetze, _ring = head_matrix_layout(fx, n)
        return int(cols), int(rows), {f"{c},{r}": f"{fx.fid}:{h}"
                                      for h, (c, r) in plaetze.items()}

    def _raster_lesen(self, state):
        if self.geraet_fid is not None:
            return self._geraet_raster(state)
        if not (self.gruppe or self.gruppe_uid):
            return None
        ref = self._gruppe_ref(state)
        return state.gruppen_raster(ref) if ref is not None else None

    def raster_neu_laden(self, state=None) -> None:
        """Raster der Bindung (Gruppe aufgeloest, FM-20, oder Matrix-Geraet)
        neu lesen und die Ebene neu melden — nach Bindung, Laden oder
        Aenderung der Gruppe."""
        self._raster = None
        if self.gebunden():
            try:
                self._raster = self._raster_lesen(state or _state())
            except Exception:
                self._raster = None
        self._ebene_melden()
        self.update()

    def raster(self) -> tuple[int, int, dict]:
        if self._raster is None and self.gebunden():
            try:
                self._raster = self._raster_lesen(_state())
            except Exception:
                self._raster = None
        return self._raster or (0, 0, {})

    def zellen_ziele(self) -> dict[str, tuple]:
        """``{"c,r": (fid, kopf|None)}`` aller belegten Rasterzellen."""
        from src.core.group_cells import parse_group_cell
        _c, _r, pos = self.raster()
        out: dict[str, tuple] = {}
        for key, wert in (pos or {}).items():
            fid, kopf = parse_group_cell(wert)
            if fid is not None:
                out[str(key).replace(" ", "")] = (fid, kopf)
        return out

    def ausgabe_pixel(self) -> dict[tuple, tuple]:
        """``{(fid, kopf): (r, g, b)}`` — was die Ebene ausgibt."""
        ziele = self.zellen_ziele()
        out: dict[tuple, tuple] = {}
        for key, farbe in self.pixel.items():
            ziel = ziele.get(key)
            q = QColor(farbe)
            if ziel is None or not q.isValid():
                continue
            out[ziel] = (q.red(), q.green(), q.blue())
        return out

    def _ebene_melden(self) -> None:
        try:
            _ebenen().setzen(self.widget_id, self.pegel, self.ausgabe_pixel())
        except Exception as e:
            print(f"[VCPixelraster] Ebene melden: {e}")

    def vor_entfernen(self) -> None:
        """Element wird geloescht oder die Konsole neu geladen: Ebene weg."""
        self._zug = None
        try:
            _ebenen().entfernen(self.widget_id)
        except Exception:
            pass

    # ── Malen (ohne Ereignisse, auch fuer Tests/Handy) ────────────────────

    def _block(self, c: int, r: int) -> list[tuple[int, int]]:
        n = max(1, int(self.aufloesung))
        c0, r0 = (c // n) * n, (r // n) * n
        cols, rows, _pos = self.raster()
        return [(cc, rr) for rr in range(r0, min(r0 + n, rows))
                for cc in range(c0, min(c0 + n, cols))]

    def malen(self, c: int, r: int, werkzeug: str | None = None) -> bool:
        """Werkzeug auf Rasterzelle ``(c, r)`` anwenden. True = geaendert."""
        cols, rows, _pos = self.raster()
        if not (0 <= c < cols and 0 <= r < rows):
            return False
        w = werkzeug or self.werkzeug
        if w == FUELLEN:
            geaendert = self._fuellen(c, r)
        else:
            farbe = self.farbe.name() if w == PINSEL else None
            geaendert = False
            for cc, rr in self._block(c, r):
                k = _schluessel(cc, rr)
                if farbe is None:
                    geaendert |= self.pixel.pop(k, None) is not None
                elif self.pixel.get(k) != farbe:
                    self.pixel[k] = farbe
                    geaendert = True
        if geaendert:
            self._ebene_melden()
            self.update()
        return geaendert

    def _fuellen(self, c: int, r: int) -> bool:
        """Flutfuellung auf Malpunkt-Ebene (Aufloesung beachtet): alle
        zusammenhaengenden Bloecke mit derselben Farbe wie der getroffene."""
        n = max(1, int(self.aufloesung))
        cols, rows, _pos = self.raster()
        bc_max, br_max = (cols + n - 1) // n, (rows + n - 1) // n
        neu = self.farbe.name()

        def farbe_von(bc, br):
            return self.pixel.get(_schluessel(bc * n, br * n))

        start = (c // n, r // n)
        alt = farbe_von(*start)
        if alt == neu:
            return False
        offen, gesehen = [start], {start}
        while offen:
            bc, br = offen.pop()
            for cc, rr in self._block(bc * n, br * n):
                self.pixel[_schluessel(cc, rr)] = neu
            for nb in ((bc + 1, br), (bc - 1, br), (bc, br + 1), (bc, br - 1)):
                if (0 <= nb[0] < bc_max and 0 <= nb[1] < br_max
                        and nb not in gesehen and farbe_von(*nb) == alt):
                    gesehen.add(nb)
                    offen.append(nb)
        return True

    def alles_loeschen(self) -> None:
        self.pixel = {}
        self._loeschen_scharf_bis = 0.0
        self._loeschen_timer.stop()
        self._ebene_melden()
        self.update()

    def set_pegel(self, wert: float) -> None:
        try:
            self.pegel = max(0.0, min(1.0, float(wert)))
        except (TypeError, ValueError):
            return
        self._ebene_melden()
        self.update()

    def set_farbe(self, farbe) -> None:
        q = QColor(farbe)
        if q.isValid():
            self.farbe = q
            self.update()

    def set_werkzeug(self, w: str) -> None:
        if w in WERKZEUGE:
            self.werkzeug = w
            self.update()

    def set_aufloesung(self, n: int) -> None:
        if int(n) in AUFLOESUNGEN:
            self.aufloesung = int(n)
            self.update()

    def aufloesung_weiter(self) -> None:
        i = AUFLOESUNGEN.index(self.aufloesung) if self.aufloesung in AUFLOESUNGEN else 0
        self.set_aufloesung(AUFLOESUNGEN[(i + 1) % len(AUFLOESUNGEN)])

    def merken(self) -> int:
        """Aktuelle Zeichnung als Bild ablegen (hoechstens ``MAX_BILDER``,
        das aelteste faellt heraus). Rueckgabe: Zahl der Bilder."""
        self.bilder.append(dict(self.pixel))
        del self.bilder[:-MAX_BILDER]
        self.abruf_index = len(self.bilder) - 1
        self.update()
        return len(self.bilder)

    def abrufen(self, index: int | None = None) -> bool:
        """Gemerktes Bild ``index`` (ohne: das naechste) als Zeichnung laden."""
        if not self.bilder:
            return False
        if index is None:
            index = (self.abruf_index + 1) % len(self.bilder)
        if not (0 <= index < len(self.bilder)):
            return False
        self.abruf_index = index
        self.pixel = dict(self.bilder[index])
        self._ebene_melden()
        self.update()
        return True

    # ── Geometrie ─────────────────────────────────────────────────────────

    def _knopf_min(self) -> int:
        return 44 if touch_aktiv() else 30

    def _rand(self) -> int:
        return 4

    def _pegel_breite(self) -> int:
        return 44 if touch_aktiv() else 26

    def _knopf_schrift(self) -> QFont:
        f = QFont(self.font())
        f.setPixelSize(12 if not touch_aktiv() else 14)
        return f

    def knopf_rechtecke(self) -> dict[str, QRect]:
        """Knopfleiste oben; bricht um, wenn die Breite nicht reicht. Jeder
        Knopf ist im Touch-Modus mindestens 44 × 44 px gross und (VCB-52)
        moeglichst so breit, dass seine Beschriftung ganz hineinpasst."""
        m = self._rand()
        breite = max(1, self.width() - 2 * m)
        mindest = self._knopf_min()
        fm = QFontMetrics(self._knopf_schrift())
        text_b = max(fm.horizontalAdvance(t) for t in _BREITESTE) + 8
        je_reihe = max(1, min(len(KNOEPFE), breite // (max(mindest, text_b) + 2)))
        hoehe = mindest
        kw = breite // je_reihe
        out: dict[str, QRect] = {}
        for i, (k, _t) in enumerate(KNOEPFE):
            zeile, spalte = divmod(i, je_reihe)
            out[k] = QRect(m + spalte * kw, m + zeile * (hoehe + 2), kw - 2, hoehe)
        return out

    def _leiste_unten(self) -> int:
        r = self.knopf_rechtecke()
        return max(q.bottom() for q in r.values()) + 1 + self._rand()

    def pegel_rechteck(self) -> QRect:
        m = self._rand()
        top = self._leiste_unten()
        b = self._pegel_breite()
        return QRect(self.width() - m - b, top, b, max(1, self.height() - top - m))

    def malflaeche(self) -> QRectF:
        """Rechteck des Rasters (Zellen quadratisch, zentriert)."""
        m = self._rand()
        top = self._leiste_unten()
        frei = QRectF(m, top, max(1, self.width() - 3 * m - self._pegel_breite()),
                      max(1, self.height() - top - m))
        cols, rows, _pos = self.raster()
        if cols <= 0 or rows <= 0:
            return frei
        s = min(frei.width() / cols, frei.height() / rows)
        w, h = s * cols, s * rows
        return QRectF(frei.x() + (frei.width() - w) / 2,
                      frei.y() + (frei.height() - h) / 2, w, h)

    def zelle_bei(self, p) -> tuple[int, int] | None:
        cols, rows, _pos = self.raster()
        fl = self.malflaeche()
        if cols <= 0 or rows <= 0 or not fl.contains(p.x() + 0.0, p.y() + 0.0):
            return None
        c = int((p.x() - fl.x()) / (fl.width() / cols))
        r = int((p.y() - fl.y()) / (fl.height() / rows))
        return min(c, cols - 1), min(r, rows - 1)

    def zelle_mitte(self, c: int, r: int) -> QPoint:
        """Bildschirmpunkt der Zellmitte (Tests, Handy)."""
        cols, rows, _pos = self.raster()
        fl = self.malflaeche()
        s = fl.width() / max(1, cols)
        return QPoint(int(fl.x() + (c + 0.5) * s), int(fl.y() + (r + 0.5) * s))

    def _knopf_bei(self, p: QPoint) -> str | None:
        for k, q in self.knopf_rechtecke().items():
            if q.contains(p):
                return k
        return None

    # ── Ereignisse ────────────────────────────────────────────────────────

    def _pegel_aus_px(self, p: QPoint) -> float:
        q = self.pegel_rechteck()
        return 1.0 - (p.y() - q.top()) / max(1, q.height())

    def mousePressEvent(self, event):
        if self._edit_mode:
            super().mousePressEvent(event)
            return
        if self._run_input_blocked() or event.button() != Qt.MouseButton.LeftButton:
            event.accept()
            return
        p = event.position().toPoint()
        knopf = self._knopf_bei(p)
        if knopf is not None:
            self._zug = knopf
        elif self.pegel_rechteck().contains(p):
            self._zug = "pegel"
            self.set_pegel(self._pegel_aus_px(p))
        else:
            zelle = self.zelle_bei(p)
            self._zug = "malen" if zelle is not None else None
            if zelle is not None:
                self.malen(*zelle)
        event.accept()

    def mouseMoveEvent(self, event):
        if self._edit_mode:
            super().mouseMoveEvent(event)
            return
        if self._run_input_blocked() or self._zug is None:
            event.accept()
            return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            self._zug = None
            event.accept()
            return
        p = event.position().toPoint()
        if self._zug == "pegel":
            self.set_pegel(self._pegel_aus_px(p))
        elif self._zug == "malen" and self.werkzeug != FUELLEN:
            zelle = self.zelle_bei(p)
            if zelle is not None:
                self.malen(*zelle)
        event.accept()

    def mouseReleaseEvent(self, event):
        zug, self._zug = self._zug, None
        if self._edit_mode:
            super().mouseReleaseEvent(event)
            return
        if self._run_input_blocked() or zug is None:
            event.accept()
            return
        p = event.position().toPoint()
        if zug in dict(KNOEPFE) and self._knopf_bei(p) == zug:
            self._knopf(zug)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if self._edit_mode:
            super().mouseDoubleClickEvent(event)
            return
        # Run-Modus: ein schneller zweiter Tipp ist ein weiterer Malpunkt
        # (kein Eigenschaften-Dialog mitten in der Show).
        # Ausnahme „Löschen“: ein Doppeltipp (auch ein prellender Finger) darf
        # die Rueckfrage nicht selbst bestaetigen — der zweite Tipp muss ein
        # eigener, bewusster Tipp sein (Pruefung VCB-51).
        if (not self._run_input_blocked()
                and event.button() == Qt.MouseButton.LeftButton
                and self._knopf_bei(event.position().toPoint()) == "loeschen"):
            self._zug = None
            event.accept()
            return
        self.mousePressEvent(event)

    def _knopf(self, k: str) -> None:
        if k in WERKZEUGE:
            self.set_werkzeug(k)
        elif k == "farbe":
            self._farbe_waehlen()
        elif k == "aufloesung":
            self.aufloesung_weiter()
        elif k == "loeschen":
            jetzt = time.monotonic()
            # VCB-52: was angezeigt wird, gilt — 'Sicher?' steht genau so lange,
            # wie der Zeitgeber laeuft, und nur dann loescht der Tipp.
            if self.loeschen_scharf():
                self.alles_loeschen()
            else:
                self._loeschen_scharf_bis = jetzt + LOESCHEN_SCHARF_S
                self._loeschen_timer.start(int(LOESCHEN_SCHARF_S * 1000))
                self.update()
        elif k == "merken":
            self.merken()
        elif k == "abruf":
            self.abrufen()

    def _farbe_waehlen(self) -> None:
        from PySide6.QtWidgets import QColorDialog
        from src.ui.dialog_hilfe import offen
        dlg = QColorDialog(self.farbe, self)
        dlg.setWindowTitle("Pinselfarbe")
        with offen(dlg):
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.set_farbe(dlg.selectedColor())
                self.set_werkzeug(PINSEL)

    def loeschen_scharf(self) -> bool:
        """Steht der Knopf auf 'Sicher?'? Massgeblich ist der Zeitgeber, der
        die Anzeige nach LOESCHEN_SCHARF_S zuruecksetzt (VCB-52)."""
        return self._loeschen_timer.isActive()

    def _loeschen_entschaerfen(self) -> None:
        """VCB-52: Ablauf der Scharf-Zeit — Anzeige und Zustand zuruecksetzen."""
        self._loeschen_scharf_bis = 0.0
        self.update()

    def event(self, e):
        # VCB-52: Tooltip je Knopf (volle Erklaerung, auch wenn gekuerzt)
        if e.type() == QEvent.Type.ToolTip:
            k = self._knopf_bei(e.pos())
            if k:
                QToolTip.showText(e.globalPos(), KNOPF_HILFE.get(k, k), self)
                return True
        return super().event(e)

    # ── Malen auf den Bildschirm ──────────────────────────────────────────

    def _knopf_text(self, k: str, t: str) -> str:
        if k == "aufloesung":
            return f"{self.aufloesung}×{self.aufloesung}"
        if k == "loeschen" and self.loeschen_scharf():
            return "Sicher?"
        if k == "abruf" and self.bilder:
            return f"Abruf {self.abruf_index + 1}/{len(self.bilder)}"
        return t

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            f = self._knopf_schrift()
            p.setFont(f)
            fm = QFontMetrics(f)
            for k, t in KNOEPFE:
                q = self.knopf_rechtecke()[k]
                aktiv = (k == self.werkzeug)
                grund = QColor("#1f6feb") if aktiv else QColor("#21262d")
                if k == "loeschen" and self.loeschen_scharf():
                    grund = QColor("#b62324")
                p.fillRect(q, grund)
                if k == "farbe":
                    p.fillRect(q.adjusted(4, 4, -4, -4), self.farbe)
                    continue
                p.setPen(QColor("#e6edf3"))
                # VCB-52: reicht die Breite nicht, hinten mit … kuerzen statt
                # mittig an beiden Seiten abzuschneiden.
                text = fm.elidedText(self._knopf_text(k, t),
                                     Qt.TextElideMode.ElideRight, max(1, q.width() - 4))
                p.drawText(q, Qt.AlignmentFlag.AlignCenter, text)
            # Raster
            cols, rows, pos = self.raster()
            fl = self.malflaeche()
            if cols <= 0 or rows <= 0:
                p.setPen(self._fg_color)
                if not self.gebunden():
                    text = "Kein Raster zugeordnet –\nBearbeiten → Eigenschaften"
                elif self.geraet_fid is not None:
                    text = f"Gerät {self.geraet_fid} fehlt"
                else:
                    text = f"Gruppe „{self.gruppe}“ fehlt"
                p.drawText(fl, Qt.AlignmentFlag.AlignCenter, text)
            else:
                s = fl.width() / cols
                belegt = set(self.zellen_ziele())
                for r in range(rows):
                    for c in range(cols):
                        k = _schluessel(c, r)
                        zr = QRectF(fl.x() + c * s, fl.y() + r * s, s, s)
                        farbe = self.pixel.get(k)
                        if farbe:
                            p.fillRect(zr.adjusted(0.5, 0.5, -0.5, -0.5), QColor(farbe))
                        elif k in belegt:
                            p.fillRect(zr.adjusted(0.5, 0.5, -0.5, -0.5), QColor("#30363d"))
                n = self.aufloesung
                if n > 1 and s * n >= 6:
                    p.setPen(QPen(QColor("#6e7681"), 1))
                    for c in range(0, cols + 1, n):
                        x = fl.x() + c * s
                        p.drawLine(int(x), int(fl.top()), int(x), int(fl.bottom()))
                    for r in range(0, rows + 1, n):
                        y = fl.y() + r * s
                        p.drawLine(int(fl.left()), int(y), int(fl.right()), int(y))
            # Pegel
            q = self.pegel_rechteck()
            p.fillRect(q, QColor("#161b22"))
            h = int(q.height() * self.pegel)
            p.fillRect(QRect(q.left(), q.bottom() - h + 1, q.width(), h), QColor("#d29922"))
            p.setPen(QColor("#e6edf3"))
            p.drawText(q, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                       f"{int(round(self.pegel * 100))}")
        finally:
            p.end()

    # ── Eigenschaften ─────────────────────────────────────────────────────

    def _open_properties(self):
        if self._kiosk_active():
            return
        from src.ui.dialog_hilfe import offen
        state = _state()
        dlg = QDialog(self)
        dlg.setWindowTitle("Pixelraster Einstellungen")
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)
        gruppe_cb = QComboBox()
        gruppe_cb.setObjectName("pixelraster_gruppe")
        for text, daten in self.raster_auswahl(state):
            gruppe_cb.addItem(text, daten)
        i = gruppe_cb.findData(self._bindung_daten())
        gruppe_cb.setCurrentIndex(max(0, i))
        form.addRow("Raster aus:", gruppe_cb)
        lay.addLayout(form)
        lay.addWidget(QLabel("Gruppe (Köpfe einzeln, Untergruppen-Blöcke "
                             "aufgelöst) oder ein Matrix-Gerät."))
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        with offen(dlg):
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.caption = cap.text() or self.caption
                self.bindung_setzen(gruppe_cb.currentData())

    def _bindung_daten(self):
        if self.geraet_fid is not None:
            return f"f:{self.geraet_fid}"
        if self.gruppe_uid:
            return f"g:{self.gruppe_uid}"
        return f"n:{self.gruppe}" if self.gruppe else ""

    def raster_auswahl(self, state) -> list[tuple[str, str]]:
        """Eintraege fuer „Raster aus“: ``(Text, Daten)`` mit Daten
        ``"g:<uid>"`` (Gruppe), ``"f:<fid>"`` (Matrix-Geraet) oder ``""``.

        Ein Matrix-Geraet ist jedes Geraet mit mehreren Farbkoepfen (Panel
        mit Rasterform, Leiste). Eine Assistenten-Matrix ueber mehrere
        Universen besteht aus mehreren Geraeten (Teilen); als GANZES steht sie
        ueber ihre Gesamtgruppe „… · Matrix“ in der Liste — sie traegt das
        fertige Gesamtraster, eine zweite Rechnung dafuer braucht es nicht."""
        from src.core.app_state import color_head_count
        out: list[tuple[str, str]] = [("— keine —", "")]
        try:
            steck = state.gruppen_steckbriefe() or {}
        except Exception:
            steck = {}
        gruppen = sorted(((n, u) for n, _o, u in steck.values() if n and u),
                         key=lambda t: t[0].lower())
        for name, uid in gruppen:
            if name.endswith(" · Matrix"):
                out.append((f"Matrix-Gerät: {name} (ganze Matrix)", f"g:{uid}"))
        try:
            fixtures = sorted(state.get_patched_fixtures(), key=lambda f: int(f.fid))
        except Exception:
            fixtures = []
        for fx in fixtures:
            try:
                n = int(color_head_count(fx) or 0)
            except Exception:
                n = 0
            if n > 1:
                label = getattr(fx, "label", "") or f"Gerät {fx.fid}"
                out.append((f"Matrix-Gerät: {label} (#{fx.fid}, {n} Köpfe)",
                            f"f:{fx.fid}"))
        for name, uid in gruppen:
            if not name.endswith(" · Matrix"):
                out.append((f"Gruppe: {name}", f"g:{uid}"))
        if self._bindung_daten() and not any(d == self._bindung_daten() for _t, d in out):
            out.append((f"(fehlt) {self.gruppe or self.geraet_fid}", self._bindung_daten()))
        return out

    def bindung_setzen(self, daten) -> None:
        """Bindung aus einem ``raster_auswahl``-Eintrag uebernehmen."""
        d = str(daten or "")
        if d.startswith("f:"):
            try:
                self.binden_geraet(int(d[2:]))
                return
            except ValueError:
                pass
        if d.startswith("g:"):
            self.gruppe, self.gruppe_uid, self.geraet_fid = "", d[2:], None
            self.raster_neu_laden()
            return
        if d.startswith("n:"):
            d = d[2:]
        elif d.startswith("f:"):
            d = ""
        self.binden(d)

    def binden(self, gruppe: str) -> None:
        """An eine Gruppe (Name) binden; die Kennung wird dabei gemerkt, damit
        Umbenennen die Bindung nicht loest. Eine andere Gruppe verwirft die
        Zeichnung nicht — Zellen ausserhalb des neuen Rasters geben nur
        nichts aus."""
        self.gruppe = str(gruppe or "")
        self.gruppe_uid = ""
        self.geraet_fid = None
        self.raster_neu_laden()

    def binden_geraet(self, fid) -> None:
        """Direkt an ein Matrix-Geraet binden (Raster = seine Kopf-Matrix)."""
        self.gruppe, self.gruppe_uid = "", ""
        self.geraet_fid = int(fid) if fid is not None else None
        self.raster_neu_laden()

    def build_inspector_body(self, host=None):
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 6, 0, 0)
        knopf = QPushButton("Raster zuordnen…")
        knopf.setObjectName("pixelraster_zuordnen")
        knopf.clicked.connect(self._open_properties)
        v.addWidget(knopf)
        neu = QPushButton("Raster neu lesen")
        neu.setToolTip("Nach Änderungen an der Gruppe das Raster neu einlesen.")
        neu.clicked.connect(lambda: self.raster_neu_laden())
        v.addWidget(neu)
        v.addStretch(1)
        self._inspector_apply = lambda: None
        return body

    # ── Serialisierung ────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["gruppe"] = self.gruppe
        d["gruppe_uid"] = self.gruppe_uid
        if self.geraet_fid is not None:
            d["geraet_fid"] = int(self.geraet_fid)
        d["pixel"] = dict(sorted(self.pixel.items()))
        d["bilder"] = [dict(sorted(b.items())) for b in self.bilder]
        d["abruf_index"] = int(self.abruf_index)
        d["pegel"] = round(float(self.pegel), 4)
        d["farbe"] = self.farbe.name()
        d["werkzeug"] = self.werkzeug
        d["aufloesung"] = int(self.aufloesung)
        return d

    @staticmethod
    def _pixel_sauber(roh) -> dict[str, str]:
        out: dict[str, str] = {}
        if not isinstance(roh, dict):
            return out
        for k, v in roh.items():
            try:
                c_s, r_s = str(k).split(",")
                c, r = int(c_s), int(r_s)
            except (TypeError, ValueError):
                continue
            farbe = _farbe_text(v) if isinstance(v, str) else None
            if c >= 0 and r >= 0 and farbe:
                out[_schluessel(c, r)] = farbe
        return out

    def apply_dict(self, d: dict):
        # Die Kennung kann wechseln (gespeicherte uebernehmen) — die Ebene der
        # alten Kennung darf nicht liegenbleiben.
        try:
            _ebenen().entfernen(self.widget_id)
        except Exception:
            pass
        super().apply_dict(d)
        self.gruppe = str(d.get("gruppe") or "")
        # Alte Elemente kennen nur den Namen: die Kennung zieht raster_neu_laden
        # beim ersten Aufloesen nach (Migration beim Laden).
        from src.core.group_ref import uid_lesbar
        self.gruppe_uid = uid_lesbar(d.get("gruppe_uid"))
        try:
            fid = d.get("geraet_fid")
            self.geraet_fid = int(fid) if fid is not None and not isinstance(fid, bool) else None
        except (TypeError, ValueError):
            self.geraet_fid = None
        self.pixel = self._pixel_sauber(d.get("pixel"))
        roh = d.get("bilder")
        self.bilder = [self._pixel_sauber(b) for b in roh[-MAX_BILDER:]] \
            if isinstance(roh, list) else []
        try:
            self.abruf_index = int(d.get("abruf_index", -1))
        except (TypeError, ValueError):
            self.abruf_index = -1
        if not (-1 <= self.abruf_index < len(self.bilder)):
            self.abruf_index = -1
        try:
            self.pegel = max(0.0, min(1.0, float(d.get("pegel", 1.0))))
        except (TypeError, ValueError):
            self.pegel = 1.0
        q = QColor(str(d.get("farbe") or "#ff0000"))
        self.farbe = q if q.isValid() else QColor("#ff0000")
        w = d.get("werkzeug", PINSEL)
        self.werkzeug = w if w in WERKZEUGE else PINSEL
        try:
            a = int(d.get("aufloesung", 1))
        except (TypeError, ValueError):
            a = 1
        self.aufloesung = a if a in AUFLOESUNGEN else 1
        self.raster_neu_laden()
