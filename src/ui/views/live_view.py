"""2D Top-Down Live-View - zeigt alle gepatchten Fixtures aus der Vogelperspektive."""
from __future__ import annotations
import json
from src.core.stage.einmessen import effektive_nullpunkte   # VIZ-55
_PT_ATTRS = frozenset(("pan", "tilt", "pan_fine", "tilt_fine"))


def _strobe_hz(ch, val: int) -> float:
    """Blinkfrequenz der 2D-Anzeige fuer einen Shutter-/Strobe-Wert (FM-48).

    Mit Bereichsdaten zaehlt NUR ein Strobe-Bereich; die Frequenz steigt innerhalb
    dieses Bereichs von ~0,5 auf 20 Hz. Bis 2026-09-28 galt pauschal „> 10 =
    Strobe" — gemessen blinkten damit Geraete mit offenem Shutter: Spider 14ch
    („Offen" 8–15), Hero Spot 90 („Open" 251–255, Grundwert 253), ZQ02001/Conti
    („Strobe aus (offen)" 250–255). Ohne Bereichsdaten bleibt die alte Regel."""
    from src.core.app_state import shutter_bereich_art
    try:
        val = int(val)
    except (TypeError, ValueError):
        return 0.0
    ranges = list(getattr(ch, "ranges", None) or ())
    if ranges:
        for r in ranges:
            lo, hi = int(r.range_from), int(r.range_to)
            if lo <= val <= hi:
                if shutter_bereich_art(r) != "strobe":
                    return 0.0
                return 0.5 + (val - lo) / max(1, hi - lo) * 19.5
        return 0.0
    return 0.5 + (val - 11) / 244.0 * 19.5 if val > 10 else 0.0
import math
import os
import time
from src.core.paths import app_data_dir
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QSlider, QFrame, QSizePolicy,
                                QScrollArea, QListWidget, QListWidgetItem,
                                QGroupBox, QFormLayout, QSpinBox, QCheckBox,
                                QTabWidget, QInputDialog, QMessageBox,
                                QTreeWidgetItem, QLineEdit,
                                QButtonGroup, QStackedWidget)
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, Signal, QByteArray, QMimeData
from PySide6.QtGui import (QPainter, QColor, QBrush, QPen, QFont, QPolygonF,
                            QLinearGradient, QRadialGradient, QMouseEvent,
                            QDrag, QFontMetricsF, QImage, QTransform,
                            QPaintEngine)
from src.core.app_state import (
    get_state, get_channels_for_patched, pixel_ring_segments, viz_model_for,
    unapply_pan_tilt_orientation)
from src.core.color_utils import visual_intensity, visual_rgb
from src.core.stage.coords import world3d_to_live
from src.ui.widgets import mini_icons as _mini
from src.ui.weak_slots import weak_slot


# ── UI-Praeferenzen (analog zu programmer_view.py) ───────────────────────────

_PREFS_DIR = app_data_dir()
_PREFS_PATH = os.path.join(_PREFS_DIR, "ui_prefs.json")


def _load_prefs() -> dict:
    try:
        with open(_PREFS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_prefs(updates: dict) -> None:
    data = _load_prefs()
    data.update(updates)
    try:
        os.makedirs(_PREFS_DIR, exist_ok=True)
        with open(_PREFS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[live_view] save prefs error: {e}")


# ── Pan/Tilt-Winkel (EINE Quelle fuer 2D-Glyph, Info-Box UND 3D-Visualizer) ──

def dmx_to_angle_deg(dmx: float, zero_dmx: float = 128.0,
                     range_deg: float = 540.0) -> float:
    """DMX-Wert (0..255) -> Auslenkung in Grad ueber den physischen Bereich des
    Geraets. Spiegelt exakt aim.py / stage_scene.html:
    ``winkel = (dmx - zero)/128 * (range_deg/2)``. Dadurch zeigen 2D-Beam-Glyph,
    Info-Box und 3D-Visualizer denselben Winkel fuer denselben DMX-Wert."""
    half = max(1.0, range_deg) / 2.0
    return (dmx - zero_dmx) / 128.0 * half


# Render-Typen, deren 2D-Glyph einen RICHTUNGS-gedrehten Strahl zeichnet.
# Muss zu den beam-zeichnenden Zweigen des FixtureRenderer passen.
# VIZ-53: 'pixel_head' zeichnet seit dem eigenen Zweig ebenfalls einen Strahl.
_BEAM_DIRECTED_TYPES = frozenset({"moving_head", "scanner", "mover_bar",
                                  "pixel_head"})


def _has_pan_tilt(fixture, render_type: str | None = None) -> bool:
    """Soll die Info-Box eine Pan/Tilt-Zeile zeigen?

    Frueher entschied ein Substring auf ``fixture_type`` (``"moving"``/``"head"``).
    Der Renderer zeichnet einen gedrehten Strahl aber auch fuer ``scanner`` und
    ``mover_bar`` — dort zeigte das Glyph also eine sichtbare, DMX-abhaengige
    Strahlrichtung, waehrend die Info-Box dazu schwieg (A3D-21). Massgeblich ist
    jetzt derselbe Render-Typ wie fuer das Glyph, plus als Rueckfall die real
    vorhandenen Pan/Tilt-Kanaele des Geraets.
    """
    rt = (render_type or getattr(fixture, "fixture_type", "") or "").lower()
    if rt in _BEAM_DIRECTED_TYPES or "moving" in rt or "head" in rt or "scanner" in rt:
        return True
    try:
        attrs = {ch.attribute for ch in get_channels_for_patched(fixture)}
    except Exception:
        return False
    return "pan" in attrs or "tilt" in attrs


# ── Fixture-Renderer ──────────────────────────────────────────────────────────

# VIZ-70: Schriften fuer FixtureRenderer.draw werden je (Punktgroesse, fett)
# einmal gebaut statt je Geraet und Bild neu (draw lief bis zu 3x QFont +
# QFontMetricsF je Geraet). Der Painter kopiert die Schrift bei setFont — die
# gecachten Objekte werden nie veraendert. Begrenzt, weil die Groesse mit dem
# (stufenlosen) Zoom variiert.
_SCHRIFT_CACHE: dict = {}
_METRIK_CACHE: dict = {}


def _schrift(pt: float, bold: bool = False) -> QFont:
    key = (pt, bold)
    f = _SCHRIFT_CACHE.get(key)
    if f is None:
        if len(_SCHRIFT_CACHE) > 256:
            _SCHRIFT_CACHE.clear()
            _METRIK_CACHE.clear()
        f = QFont("Arial")
        f.setPointSizeF(pt)
        if bold:
            f.setBold(True)
        _SCHRIFT_CACHE[key] = f
    return f


def _text_breite(pt: float, text: str) -> float:
    m = _METRIK_CACHE.get(pt)
    if m is None:
        m = QFontMetricsF(_schrift(pt))
        _METRIK_CACHE[pt] = m
    return m.horizontalAdvance(text)


# ── VIZ-78: Kachel-Cache fuer einzelne Zeichen-Durchgaenge ───────────────────
# Gemessen (headless, Mega-Arena, 32 Geraete mit Effekten): ~2/3 eines Bilds
# steckten in ``drawEllipse`` — geglaettete Ringe, Verlaufs-Kreise, Gehaeuse,
# jedes Bild fuer jedes Geraet neu gerastert, obwohl z. B. der Pulsring in
# einem Bild bei ALLEN Geraeten gleich aussieht.
#
# Pixelgleich, weil EIN Durchgang (nur Fuellung ODER nur Kontur) jedes Pixel
# genau einmal mit „Source Over" mischt: auf eine durchsichtige Kachel gemalt
# steht dort exakt die vormultiplizierte Quellfarbe s' (s' + 0·…), und das
# Aufblenden der Kachel rechnet danach dieselbe Formel s' + d·(1−a') wie das
# direkte Zeichnen. Eine Form mit Fuellung UND Kontur wird deshalb als zwei
# Durchgaenge gezeichnet (genau das tut Qt intern auch: erst fuellen, dann
# konturieren). Die Kachel liegt um eine GANZE Zahl Geraetepixel verschoben;
# Matrix-Skalierung und Nachkomma-Anteil der Verschiebung sind Teil des
# Schluessels. Gedrehte/gescherte Painter, Deckkraft != 1, anderer
# Zeichenmodus als „Source Over", skalierte oder nicht ganzzahlige Umlenkung
# (JEDE Pixeldichte != 1, also auch 2,0 / Retina / 200 %-Windows) und Ziele,
# die nicht 8 Bit je Kanal vormultipliziert speichern (10-Bit-X11, RGBA64,
# ARGB32 ohne Vormultiplikation, RGB16 — dort rundet das Aufblenden anders),
# -> direkt wie bisher. Bitgleich ist der Cache also nur auf 8-Bit-Zielen.
#
# Eine Kachel entsteht erst, wenn derselbe Schluessel ZUM DRITTEN Mal kommt
# (``KACHEL_AB``). Einzelstuecke und Paare kosten so nichts extra — z. B. ein
# symmetrischer Chase, bei dem je zwei Geraete eine Farbe teilen, die sich
# jedes Bild aendert: beim Bau schon beim zweiten Mal wurde dort jede Kachel
# gebaut, einmal benutzt und nie wieder getroffen (gemessen: doppelt so teuer
# wie direkt).
_KACHELN: dict = {}
_GESEHEN: dict = {}                   # Schluessel -> bisherige Vorkommen
KACHEL_AB = 3
GESEHEN_MAX = 20_000
_KACHEL_PIXEL = [0]
KACHEL_MAX_PIXEL = 4_000_000          # Summe aller Kacheln (~16 MB), dann leeren
KACHEL_MAX_FLAECHE = 160_000          # groessere Einzelform -> direkt
_IDENTITAET = QTransform()
_KACHEL_STATS = {"treffer": 0, "gebaut": 0, "direkt": 0}


def _ck(c: QColor) -> tuple:
    """Hashbarer Schluessel einer Farbe in der Genauigkeit, mit der Qt sie
    rastert (16 Bit je Kanal — ``lighter()``/``darker()`` landen dazwischen)."""
    r = c.rgba64()
    return (r.red(), r.green(), r.blue(), r.alpha())


def _form_direkt(painter: QPainter, art: str, geo: tuple, pen, brush) -> None:
    painter.setPen(pen if pen is not None else Qt.PenStyle.NoPen)
    painter.setBrush(brush if brush is not None else Qt.BrushStyle.NoBrush)
    if art == "e":
        painter.drawEllipse(QRectF(*geo))
    elif art == "r":
        painter.drawRect(QRectF(*geo[:4]))
    else:
        painter.drawRoundedRect(QRectF(*geo[:4]), geo[4], geo[5])


# Zielformate, auf denen das Aufblenden einer Kachel bitgleich zum direkten
# Zeichnen ist (8 Bit je Kanal, vormultipliziert bzw. ohne Alpha).
_KACHEL_FORMATE = frozenset((
    QImage.Format.Format_RGB32, QImage.Format.Format_ARGB32_Premultiplied,
    QImage.Format.Format_RGBX8888, QImage.Format.Format_RGBA8888_Premultiplied,
    QImage.Format.Format_RGB888))
_SOURCE_OVER = QPainter.CompositionMode.CompositionMode_SourceOver


def _kachel_ziel_ok(painter: QPainter) -> bool:
    """Rastert der Painter in ein 8-Bit-Ziel? Nur Raster-Engine (kein Druck/
    SVG/OpenGL); Bild -> Format aus der Erlaubt-Liste; Widget/Pixmap -> Tiefe
    24/32 (ein 10-Bit-Bildschirm meldet 30, RGB16 meldet 16)."""
    eng = painter.paintEngine()
    if eng is None or eng.type() != QPaintEngine.Type.Raster:
        return False
    dev = painter.device()
    if isinstance(dev, QImage):
        return dev.format() in _KACHEL_FORMATE
    try:
        return dev.depth() in (24, 32)
    except Exception:
        return False


def _kachel_kontext(painter: QPainter):
    """Einmal je Geraet (nach ``translate``): Matrix, Umlenkung und Hinweise
    fuer :func:`_form`. ``None`` = Kachel-Cache hier nicht anwendbar (gedreht,
    Deckkraft != 1, Zeichenmodus != Source Over, Ziel nicht 8 Bit, Umlenkung
    skaliert oder nicht ganzzahlig — jede Pixeldichte != 1)."""
    t = painter.deviceTransform()
    if (t.isRotating() or painter.opacity() != 1.0
            or painter.compositionMode() != _SOURCE_OVER
            or not _kachel_ziel_ok(painter)):
        return None
    wt = painter.worldTransform()
    painter.setWorldTransform(_IDENTITAET)
    r = painter.deviceTransform()
    painter.setWorldTransform(wt)
    rdx, rdy = r.dx(), r.dy()
    if r.isScaling() or r.isRotating() or rdx != int(rdx) or rdy != int(rdy):
        return None
    return (t.m11(), t.m22(), t.dx(), t.dy(), rdx, rdy, wt, painter.renderHints())


def _form_durchgang(painter: QPainter, kx, art: str, geo: tuple, pen, brush,
                    schluessel) -> None:
    """Ein Durchgang (pen ODER brush) ueber den Kachel-Cache."""
    # Rechtecke rastert Qt mit einem eigenen Rasterer, der Kanten per floor()
    # in 1/65536 Pixel setzt: liegt eine Kante (rechnerisch) genau auf einer
    # Pixelgrenze, entscheidet das letzte Bit der Gleitkommarechnung — und das
    # faellt in der Kachel (kleinere Koordinaten) anders. Rechtecke sind
    # ohnehin billig -> immer direkt.
    if kx is None or schluessel is None or art == "r":
        _KACHEL_STATS["direkt"] += 1
        _form_direkt(painter, art, geo, pen, brush)
        return
    m11, m22, dx, dy, rdx, rdy, wt, hints = kx
    # Verlaeufe rechnet Qt je Pixel ueber die INVERSE Matrix zurueck; nur ohne
    # Skalierung (Zoom 1) ist das in der Kachel bitgleich (reine, exakte
    # Verschiebung um ganze Pixel). Sonst direkt.
    if schluessel[1][0] == "g" and (m11 != 1.0 or m22 != 1.0):
        _KACHEL_STATS["direkt"] += 1
        _form_direkt(painter, art, geo, pen, brush)
        return
    # Duenne Stifte (<= 1 Geraetepixel) zeichnet Qt mit dem Kosmetik-Stroker,
    # der Pixel an Stossstellen mehrfach mischt -> nicht kachelbar.
    if pen is not None and pen.widthF() * max(abs(m11), abs(m22)) <= 1.0:
        _KACHEL_STATS["direkt"] += 1
        _form_direkt(painter, art, geo, pen, brush)
        return
    x, y, w, h = geo[0], geo[1], geo[2], geo[3]
    rand = (pen.widthF() + 2.0) if pen is not None else 1.0
    x0, x1 = m11 * (x - rand) + dx, m11 * (x + w + rand) + dx
    y0, y1 = m22 * (y - rand) + dy, m22 * (y + h + rand) + dy
    if x0 > x1:
        x0, x1 = x1, x0
    if y0 > y1:
        y0, y1 = y1, y0
    ox, oy = math.floor(x0) - 2, math.floor(y0) - 2
    bw, bh = math.ceil(x1) - ox + 2, math.ceil(y1) - oy + 2
    if bw * bh > KACHEL_MAX_FLAECHE or bw <= 0 or bh <= 0:
        _KACHEL_STATS["direkt"] += 1
        _form_direkt(painter, art, geo, pen, brush)
        return
    # Ganzzahlige Verschiebung: dx - ox ist exakt (beide Vielfache derselben
    # Zweierpotenz, Ergebnis kleiner) -> gleiche Kachel fuer jede Lage mit
    # demselben Nachkomma-Anteil.
    tdx, tdy = dx - ox, dy - oy
    key = (art, geo, schluessel, m11, m22, tdx, tdy, bw, bh, hints.value)
    img = _KACHELN.get(key)
    if img is None:
        n = _GESEHEN.get(key, 0) + 1
        if n < KACHEL_AB:
            # Erst beim dritten Mal bauen; die Merkliste waechst mit jeder
            # neuen Farbe (Chase) und wird deshalb eigenstaendig geleert.
            if n == 1 and len(_GESEHEN) > GESEHEN_MAX:
                _GESEHEN.clear()
            _GESEHEN[key] = n
            _KACHEL_STATS["direkt"] += 1
            _form_direkt(painter, art, geo, pen, brush)
            return
        if _KACHEL_PIXEL[0] + bw * bh > KACHEL_MAX_PIXEL:
            _kacheln_leeren()
        img = QImage(bw, bh, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        kp = QPainter(img)
        try:
            kp.setRenderHints(hints)
            kp.setTransform(QTransform(m11, 0.0, 0.0, m22, tdx, tdy))
            _form_direkt(kp, art, geo, pen, brush)
        finally:
            kp.end()
        _KACHELN[key] = img
        _GESEHEN.pop(key, None)
        _KACHEL_PIXEL[0] += bw * bh
        _KACHEL_STATS["gebaut"] += 1
    else:
        _KACHEL_STATS["treffer"] += 1
    painter.setWorldTransform(_IDENTITAET)
    painter.drawImage(QPointF(ox - rdx, oy - rdy), img)
    painter.setWorldTransform(wt)


def _kacheln_leeren() -> None:
    _KACHELN.clear()
    _GESEHEN.clear()
    _KACHEL_PIXEL[0] = 0


def _form(painter: QPainter, kx, art: str, geo: tuple, pen=None, brush=None,
          pen_key=None, brush_key=None) -> None:
    """Zeichnet eine Form wie ``drawEllipse``/``drawRect``/``drawRoundedRect``
    mit ``pen``/``brush`` — Fuellung und Kontur je als eigener Durchgang ueber
    den Kachel-Cache. ``art``: ``"e"`` Ellipse, ``"r"`` Rechteck, ``"rr"``
    abgerundet; ``geo`` = (x, y, w, h[, rx, ry]) in lokalen Koordinaten;
    ``kx`` = :func:`_kachel_kontext` des Painters in genau diesem Zustand.
    ``*_key`` beschreibt Stift/Pinsel vollstaendig (``None`` = nicht cachen)."""
    if brush is not None:
        _form_durchgang(painter, kx, art, geo, None, brush,
                        None if brush_key is None else ("b", brush_key))
    if pen is not None:
        _form_durchgang(painter, kx, art, geo, pen, None,
                        None if pen_key is None else ("p", pen_key))


def _ellipse(cx: float, cy: float, rx: float, ry: float) -> tuple:
    """Geometrie wie ``QPainter.drawEllipse(QPointF(cx, cy), rx, ry)``."""
    return (cx - rx, cy - ry, 2 * rx, 2 * ry)


_SOLID = Qt.PenStyle.SolidLine
_STIL_NR = {Qt.PenStyle.SolidLine: 1, Qt.PenStyle.DashLine: 2}


def _stift(color: QColor, breite: float, stil=_SOLID):
    """(QPen, Schluessel) — gleicher Konstruktor wie ``QPen(color, breite[, stil])``."""
    return QPen(color, breite, stil), (_ck(color), breite, _STIL_NR[stil])


def _pinsel(color: QColor):
    return QBrush(color), ("s", _ck(color))


def _verlauf(cx: float, cy: float, r: float, stops):
    """Radialer Verlauf wie ``QRadialGradient(cx, cy, r)`` + ``setColorAt``.

    Ein durchgehend DECKENDER Verlauf bekommt keinen Schluessel: Qt mischt ihn
    als „Source" mit Abdeckung (eine Rundung: s·c + d·(1−c)), die Kachel
    rechnet zweimal gerundet — bis zu 2 Stufen Unterschied an den Kanten.
    Sobald ein Stop durchscheint (Glow), mischt Qt „Source Over" wie die
    Kachel."""
    g = QRadialGradient(cx, cy, r)
    keys = []
    for pos, c in stops:
        g.setColorAt(pos, c)
        keys.append((pos, _ck(c)))
    if all(k[1][3] == 0xFFFF for k in keys):
        return QBrush(g), None
    return QBrush(g), ("g", cx, cy, r, tuple(keys))


def _pb(brush_hex: str, pen_hex: str, breite: float) -> tuple:
    """(pen, brush, pen_key, brush_key) fuer ``_form(painter, _kx, art, geo, *…)``."""
    pen, pk = _stift(QColor(pen_hex), breite)
    br, bk = _pinsel(QColor(brush_hex))
    return (pen, br, pk, bk)


# Feste Gehaeuse-Stifte/-Pinsel einmal statt je Bild und Geraet.
_PB_161616_555_15 = _pb("#161616", "#555", 1.5)
_PB_222_666_15 = _pb("#222", "#666", 1.5)
_PB_2a2a2a_666_1 = _pb("#2a2a2a", "#666", 1)
_PB_1c1c22_888_15 = _pb("#1c1c22", "#888", 1.5)
_PB_1a1a1a_555_2 = _pb("#1a1a1a", "#555", 2)
_PB_1a1a1a_555_15 = _pb("#1a1a1a", "#555", 1.5)
_PB_1a1a1a_888_1 = _pb("#1a1a1a", "#888", 1)
_PB_1e1e28_555_15 = _pb("#1e1e28", "#555", 1.5)
_PB_333_777_1 = _pb("#333", "#777", 1)
_P_222_1 = _stift(QColor("#222"), 1)
_P_888_15 = _stift(QColor("#888"), 1.5)
_P_444_1 = _stift(QColor("#444"), 1)
_B_FX = _pinsel(QColor(60, 130, 255, 200))


class FixtureRenderer:
    """Zeichnet ein Fixture je nach Typ unterscheidbar."""

    @staticmethod
    def draw(painter: QPainter, fixture_type: str, x: float, y: float,
             size: float, color: QColor, intensity: int, label: str,
             selected: bool = False, pan: int = 128, tilt: int = 128,
             effects: list | None = None, anim_phase: float = 0.0,
             blink_off: bool = False, highlighted: bool = False,
             zoom: float = 1.0, pan_range_deg: float = 540.0,
             tilt_range_deg: float = 270.0, pan_zero_dmx: float = 128.0,
             tilt_zero_dmx: float = 128.0, lod: int = 0,
             ring_segments: int = 0):
        # ring_segments (VIZ-53): Zahl der Ring-Segmente eines 'pixel_head'.
        # Sie ist eine Eigenschaft des GEPATCHTEN Geraets und kommt deshalb vom
        # Canvas mit (`app_state.pixel_ring_segments`) — dieselbe Zahl, die auch
        # die 3D-Nutzlast bekommt. 0 = unbekannt -> schematischer Kranz.
        # lod (Level-of-Detail, QOL/UI-26): 0 = volles Label + Intensity% + FX-Badge,
        # 1 = nur Kurz-Label (ohne Typ-Praefix), 2 = gar kein Text. Wird vom Canvas
        # aus dem Bildschirm-Nachbarabstand bestimmt -> keine ueberlappenden Labels
        # bei dichten Fixtures/kleinem Zoom. Default 0 = rueckwaertskompatibel.
        effects = effects or []
        painter.save()
        painter.translate(x, y)
        _kx = _kachel_kontext(painter)      # VIZ-78
        # Texte in konstanter Bildschirmgroesse: der Painter ist global mit dem
        # Zoom skaliert, also Punktgroessen/Badge-Geometrie mit 1/Zoom
        # gegenrechnen, damit Labels bei kleinem Zoom lesbar bleiben und bei
        # grossem Zoom nicht ueberlaufen.
        tscale = 1.0 / zoom if zoom > 0 else 1.0

        # Blinkt die Fixture gerade im "Aus"-Phase → Licht ausschalten
        if blink_off:
            color = QColor(18, 18, 22)
            intensity = 0

        # 2D-Helligkeit an die Intensitaet koppeln (wie 3D): bei niedriger
        # Intensitaet die Fixture-Farbe Richtung dunkel mischen, statt sie immer
        # voll gesaettigt zu zeichnen — ein auf 0% geparktes Geraet sieht dann
        # auch im 2D dunkel aus (3D faerbt das Icon bei ~0% nach 0x3a3a4a).
        _inorm = max(0.0, min(1.0, intensity / 255.0))
        _off = QColor(0x3a, 0x3a, 0x4a)
        color = QColor(
            int(_off.red()   + (color.red()   - _off.red())   * _inorm),
            int(_off.green() + (color.green() - _off.green()) * _inorm),
            int(_off.blue()  + (color.blue()  - _off.blue())  * _inorm),
        )

        # Effekt-Ring (pulsierend, blau) — hinter Selection-Ring
        if effects:
            pulse = 0.5 + 0.5 * math.sin(anim_phase * 2 * math.pi)
            ring_alpha = int(60 + 160 * pulse)
            ring_color = QColor(80, 160, 255, ring_alpha)
            _pen, _pk = _stift(ring_color, 2, Qt.PenStyle.DashLine)
            _form(painter, _kx, "e", _ellipse(0, 0, size * 0.72, size * 0.72),
                  pen=_pen, pen_key=_pk)

        # Highlight-Ring (cyan, dicker Ring) — Gruppen-Hervorhebung
        if highlighted:
            painter.setPen(QPen(QColor("#00E5FF"), 4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(-size*0.82, -size*0.82, size*1.64, size*1.64))

        # Selection-Ring (gold)
        if selected:
            painter.setPen(QPen(QColor("#FFD700"), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(-size*0.7, -size*0.7, size*1.4, size*1.4))

        intensity_alpha = max(0, min(255, intensity))  # kein Floor mehr: 0% -> kein Glow
        glow_color = QColor(color)
        glow_color.setAlpha(intensity_alpha // 2)

        ft = (fixture_type or "").lower()

        if ft == "par_bar":
            # PAR-Bar (FM-3): Gehaeuse-Balken mit N einzelnen PAR-Zellen
            # (grandMA3-Lichtplan-Stil). Exakter Match VOR "par"/"bar", sonst
            # faengt der PAR- bzw. LED-Bar-Zweig es ab.
            _form(painter, _kx, "rr", (-size*0.95, -size*0.30, size*1.9, size*0.6, 4, 4),
                  *_PB_161616_555_15)
            n_cells = 4
            step = size*1.7 / n_cells
            cell_r = min(size*0.20, step*0.42)
            _stops = ((0, color.lighter(180)), (0.6, color), (1, glow_color))
            for i in range(n_cells):
                cx = -size*0.85 + step*(i+0.5)
                _br, _bk = _verlauf(cx, 0, cell_r, _stops)
                _form(painter, _kx, "e", _ellipse(cx, 0, cell_r, cell_r),
                      _P_222_1[0], _br, _P_222_1[1], _bk)
            label_prefix = "PARBAR"

        elif ft == "mover_bar":
            # Mover-Bar (FM-4): Gehaeuse-Balken mit N kleinen Moving-Heads, je mit
            # Beam-Richtung (gemeinsamer Pan im 2D; Pro-Kopf-Pan nur 3D/DMX).
            from math import cos, sin
            _form(painter, _kx, "rr", (-size*0.95, -size*0.24, size*1.9, size*0.48, 4, 4),
                  *_PB_222_666_15)
            n_cells = 4
            step = size*1.7 / n_cells
            head_r = min(size*0.16, step*0.36)
            pan_rad = math.radians(dmx_to_angle_deg(pan, pan_zero_dmx, pan_range_deg))
            for i in range(n_cells):
                cx = -size*0.85 + step*(i+0.5)
                grad = QRadialGradient(cx, 0, head_r)
                grad.setColorAt(0, color.lighter(150))
                grad.setColorAt(0.7, color)
                grad.setColorAt(1, color.darker(120))
                painter.setBrush(QBrush(grad))
                painter.setPen(QPen(QColor("#888"), 1))
                painter.drawEllipse(QPointF(cx, 0), head_r, head_r)
                bx = cx + cos(pan_rad - 1.5708) * size*0.26
                by = sin(pan_rad - 1.5708) * size*0.26
                painter.setPen(QPen(color, 1.5))
                painter.drawLine(QPointF(cx, 0), QPointF(bx, by))
            label_prefix = "MOVBAR"

        elif ft == "matrix":
            # FM-13: Pixel-Panel — quadratisches Gehaeuse mit kleinem Zell-Raster
            # (schematisch in der Fixture-Farbe; Per-Pixel-Farbe zeigt das 3D).
            painter.setBrush(QBrush(QColor("#161616")))
            painter.setPen(QPen(QColor("#555"), 1.5))
            painter.drawRoundedRect(QRectF(-size*0.55, -size*0.55, size*1.1, size*1.1), 4, 4)
            n = 4
            inner = size * 0.9
            step = inner / n
            cw = step * 0.7
            x0 = -inner/2 + step*0.5
            lit = intensity > 12
            painter.setPen(Qt.PenStyle.NoPen)
            _br, _bk = _pinsel(color if lit else QColor("#3a3a44"))
            for r in range(n):
                for c in range(n):
                    cx = x0 + c*step
                    cy = x0 + r*step
                    _form(painter, _kx, "rr", (cx - cw/2, cy - cw/2, cw, cw, 1.5, 1.5),
                          brush=_br, brush_key=_bk)
            label_prefix = "MTX"

        elif ft == "pixel_head":
            # FM-14/VIZ-53: Pixel-Moving-Head (Robe Spiider) — EIN Kopf, dessen
            # Lichtquelle in Ring-Segmente zerlegt ist. Exakter Match VOR dem
            # Moving-Head-Zweig: `"head" in ft` faengt ihn sonst ab, und genau
            # dort stand er bis hierher als gewoehnlicher Kopf, waehrend das
            # 3D-Top-Down-Icon laengst seinen Ring zeigte.
            from math import cos, sin
            # Yoke wie beim Moving Head (es IST einer).
            _form(painter, _kx, "r", (-size*0.5, -size*0.15, size*0.15, size*0.3),
                  *_PB_2a2a2a_666_1)
            _form(painter, _kx, "r", (size*0.35, -size*0.15, size*0.15, size*0.3),
                  *_PB_2a2a2a_666_1)
            # Kopf-Gehaeuse dunkel: die Farbe tragen die Segmente, nicht die
            # geschlossene Linse des gewoehnlichen Kopfes.
            _form(painter, _kx, "e", (-size*0.42, -size*0.42, size*0.84, size*0.84),
                  *_PB_1c1c22_888_15)
            # Die Segmente: so viele, wie das Geraet hat — dieselbe Zahl, die
            # das 3D bekommt (`app_state.pixel_ring_segments`), und dieselbe
            # Kranz-Geometrie wie das Listen-Icon (`mini_icons.ring_offsets`).
            painter.setPen(Qt.PenStyle.NoPen)
            _stops = ((0, color.lighter(160)), (0.7, color), (1, glow_color))
            for dx, dy, cell_r in _mini.ring_offsets(
                    ring_segments or _mini.RING_SCHEMA_SEGMENTE,
                    size*0.27, size*0.10):
                _br, _bk = _verlauf(dx, dy, max(0.5, cell_r), _stops)
                _form(painter, _kx, "e", (dx - cell_r, dy - cell_r, cell_r*2, cell_r*2),
                      brush=_br, brush_key=_bk)
            # Beam-Richtung (Pan) wie beim Moving Head — der Kopf bewegt sich.
            pan_rad = math.radians(dmx_to_angle_deg(pan, pan_zero_dmx, pan_range_deg))
            painter.setPen(QPen(color, 2))
            painter.drawLine(QPointF(0, 0),
                             QPointF(cos(pan_rad - 1.5708) * size * 0.6,
                                     sin(pan_rad - 1.5708) * size * 0.6))
            label_prefix = "PIX"

        elif "moving" in ft or "head" in ft:
            # Moving Head: Diamant + Yoke
            # Yoke (2 Arme links/rechts)
            _form(painter, _kx, "r", (-size*0.5, -size*0.15, size*0.15, size*0.3),
                  *_PB_2a2a2a_666_1)
            _form(painter, _kx, "r", (size*0.35, -size*0.15, size*0.15, size*0.3),
                  *_PB_2a2a2a_666_1)
            # Head (Kreis)
            _br, _bk = _verlauf(0, 0, size*0.4, ((0, color.lighter(140)), (0.7, color),
                                                 (1, color.darker(120))))
            _form(painter, _kx, "e", _ellipse(0, 0, size*0.4, size*0.4),
                  _P_888_15[0], _br, _P_888_15[1], _bk)
            # Beam-Richtung (Pan) — Winkel ueber den ECHTEN Pan-Bereich, damit
            # 2D-Glyph, Info-Box und 3D-Visualizer uebereinstimmen.
            from math import cos, sin
            pan_rad = math.radians(dmx_to_angle_deg(pan, pan_zero_dmx, pan_range_deg))
            beam_x = cos(pan_rad - 1.5708) * size * 0.6
            beam_y = sin(pan_rad - 1.5708) * size * 0.6
            painter.setPen(QPen(color, 2))
            painter.drawLine(QPointF(0, 0), QPointF(beam_x, beam_y))
            label_prefix = "MH"

        elif any(_t.startswith("par") for _t in ft.split()):  # nicht bloss "par" in ft (sonst matcht z.B. "Sparkular")
            # PAR: Kreis (von oben gesehen)
            _form(painter, _kx, "e", _ellipse(0, 0, size*0.5, size*0.5),
                  *_PB_1a1a1a_555_2)
            # Innen-Glow (LED-Farbe)
            _br, _bk = _verlauf(0, 0, size*0.45, ((0, color.lighter(180)), (0.6, color),
                                                  (1, glow_color)))
            _form(painter, _kx, "e", _ellipse(0, 0, size*0.4, size*0.4),
                  _P_222_1[0], _br, _P_222_1[1], _bk)
            label_prefix = "PAR"

        elif "bar" in ft:
            # LED Bar: langes Rechteck horizontal
            _form(painter, _kx, "rr", (-size*0.9, -size*0.15, size*1.8, size*0.3, 3, 3),
                  *_PB_1a1a1a_555_15)
            # Pixel-Segments
            n_seg = 8
            seg_w = size*1.7 / n_seg
            _br, _bk = _pinsel(color)
            for i in range(n_seg):
                px = -size*0.85 + i*seg_w
                _form(painter, _kx, "r", (px+1, -size*0.1, seg_w-2, size*0.2),
                      brush=_br, brush_key=_bk)
            label_prefix = "BAR"

        elif "strobe" in ft:
            # Strobe: Hexagon
            painter.setBrush(QBrush(QColor("#222")))
            painter.setPen(QPen(QColor("#888"), 1.5))
            from math import cos, sin, pi
            pts = QPolygonF([QPointF(cos(i*pi/3)*size*0.5, sin(i*pi/3)*size*0.5) for i in range(6)])
            painter.drawPolygon(pts)
            # Inner glow (weiss bei Strobe)
            white_glow = QColor(255, 255, 255, intensity_alpha)
            _br, _bk = _pinsel(white_glow)
            _form(painter, _kx, "e", _ellipse(0, 0, size*0.3, size*0.3),
                  brush=_br, brush_key=_bk)
            label_prefix = "STR"

        elif "dimmer" in ft:
            # Dimmer: einfacher Kreis
            _br, _bk = _pinsel(color)
            _form(painter, _kx, "e", _ellipse(0, 0, size*0.35, size*0.35),
                  _P_444_1[0], _br, _P_444_1[1], _bk)
            label_prefix = "DIM"

        elif "spider" in ft:
            # Spider: zwei parallele, leicht schraege Balken (Scheren-Symbol)
            from math import cos, sin, pi
            # Oberer Balken: leicht nach rechts geneigt
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(color.darker(120), 1))
            angle1 = 0.35  # ~20 Grad
            bw = size * 0.7
            bh = size * 0.18
            painter.save()
            painter.rotate(-angle1 * 180.0 / pi)
            painter.drawRoundedRect(QRectF(-bw*0.5, -size*0.45, bw, bh), 2, 2)
            painter.restore()
            # Unterer Balken: leicht nach links geneigt (Spiegel)
            painter.save()
            painter.rotate(angle1 * 180.0 / pi)
            painter.drawRoundedRect(QRectF(-bw*0.5, size*0.27, bw, bh), 2, 2)
            painter.restore()
            # Verbindungs-Mittelstreifen (Gehaeuse)
            _form(painter, _kx, "rr", (-size*0.18, -size*0.22, size*0.36, size*0.44, 3, 3),
                  *_PB_2a2a2a_666_1)
            # Glow-Punkte an Balken-Enden
            glow_c = QColor(color)
            glow_c.setAlpha(intensity_alpha)
            _br, _bk = _pinsel(glow_c)
            for _gx, _gy in ((-0.38, -0.35), (0.38, -0.35), (-0.38, 0.35), (0.38, 0.35)):
                _form(painter, _kx, "e", _ellipse(size*_gx, size*_gy, size*0.07, size*0.07),
                      brush=_br, brush_key=_bk)
            label_prefix = "SPI"

        elif "scanner" in ft:
            # Scanner: Sockel-Box + gekippter Spiegel-Flap + abgelenkter Strahlstreifen
            from math import cos, sin, pi
            # Sockel
            painter.setBrush(QBrush(QColor("#2a2a2a")))
            painter.setPen(QPen(QColor("#666"), 1))
            painter.drawRoundedRect(QRectF(-size*0.45, size*0.05, size*0.9, size*0.4), 3, 3)
            # Spiegel-Flap (gekippt ~45 Grad)
            painter.setBrush(QBrush(QColor("#888888")))
            painter.setPen(QPen(QColor("#aaa"), 1.5))
            painter.save()
            painter.rotate(-45)
            painter.drawRoundedRect(QRectF(-size*0.08, -size*0.32, size*0.16, size*0.45), 2, 2)
            painter.restore()
            # Abgelenkter Strahl (vom Spiegel) — Auslenkung ueber den ECHTEN
            # Pan-Bereich des Geraets (statt fix +-90 Grad).
            pan_rad = math.radians(dmx_to_angle_deg(pan, pan_zero_dmx, pan_range_deg))
            beam_ex = cos(pan_rad - 0.785) * size * 0.7
            beam_ey = sin(pan_rad - 0.785) * size * 0.7
            painter.setPen(QPen(color, 2))
            painter.drawLine(QPointF(0, -size*0.05), QPointF(beam_ex, beam_ey - size*0.05))
            label_prefix = "SCAN"

        elif "laser" in ft:
            # Laser: kleines Emitter-Gehaeuse + Faecher aus 4 Strahlen
            from math import cos, sin, pi
            # Emitter-Box
            _form(painter, _kx, "rr", (-size*0.2, -size*0.2, size*0.4, size*0.4, 3, 3),
                  *_PB_1a1a1a_888_1)
            # Emitter-Punkt
            _br, _bk = _pinsel(color.lighter(160))
            _form(painter, _kx, "e", _ellipse(0, 0, size*0.09, size*0.09),
                  brush=_br, brush_key=_bk)
            # Strahlen-Faecher (4 Strahlen, symmetrisch aufgefaechert)
            n_beams = 4
            spread = 1.2  # Gesamtwinkel in Rad
            base_angle = -1.5708  # nach oben zeigend
            painter.setPen(QPen(color, 1.5))
            for i in range(n_beams):
                a = base_angle - spread/2 + spread * i / max(1, n_beams - 1)
                ex = cos(a) * size * 0.75
                ey = sin(a) * size * 0.75
                beam_col = QColor(color)
                beam_col.setAlpha(max(60, intensity_alpha - i * 20))
                painter.setPen(QPen(beam_col, 1.5))
                painter.drawLine(QPointF(0, 0), QPointF(ex, ey))
            label_prefix = "LSR"

        elif "smoke" in ft or "hazer" in ft or "fog" in ft:
            # Smoke/Hazer/Fog: Maschinen-Box + Duese + Puff-Boegen
            from math import cos, sin, pi
            # Geraete-Box
            _form(painter, _kx, "rr", (-size*0.35, -size*0.25, size*0.7, size*0.5, 4, 4),
                  *_PB_1e1e28_555_15)
            # Duese oben
            _form(painter, _kx, "rr", (-size*0.08, -size*0.45, size*0.16, size*0.22, 2, 2),
                  *_PB_333_777_1)
            # Puff-Arcs (helle Boegen ueber der Duese)
            fog_col = QColor(color)
            fog_col.setAlpha(max(30, intensity_alpha // 2))
            painter.setPen(QPen(fog_col, 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for i in range(1, 3):
                r_puff = size * (0.22 + i * 0.14)
                painter.drawArc(
                    QRectF(-r_puff, -size*0.55 - r_puff, r_puff*2, r_puff*2),
                    30 * 16, 120 * 16
                )
            label_prefix = "FOG"

        elif ft == "other":
            # FLA-4: echte Geräteklasse statt namenlosem Default. Das neutrale
            # Gehäuse entspricht dem dedizierten 3D-/Listen-Modell und behauptet
            # weder PAR noch Moving Head (QLC+ mappt Fan/Effect/Other hierhin).
            painter.setBrush(QBrush(QColor("#252833")))
            painter.setPen(QPen(QColor("#7d8494"), 1.5))
            painter.drawRoundedRect(
                QRectF(-size*0.46, -size*0.40, size*0.92, size*0.80), 4, 4)
            painter.setBrush(QBrush(QColor("#343947")))
            painter.drawRoundedRect(
                QRectF(-size*0.30, -size*0.50, size*0.60, size*0.12), 2, 2)
            # DMX-Statuspanel: `color` ist oben bereits mit der Intensitaet
            # gegen den Unlit-Farbton gemischt. Damit bleiben Farbe, Dimmer und
            # Blink-Phase wie beim frueheren Default-Quadrat direkt sichtbar.
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(color.lighter(145), 1))
            painter.drawRoundedRect(
                QRectF(-size*0.34, -size*0.27, size*0.68, size*0.54), 3, 3)
            painter.setFont(_schrift(12 * tscale, True))
            painter.setPen(color.lighter(185))
            painter.drawText(
                QRectF(-size*0.35, -size*0.32, size*0.70, size*0.64),
                Qt.AlignmentFlag.AlignCenter, "?")
            label_prefix = "OTHER"

        else:
            # Unbekannt: Quadrat
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(QColor("#666"), 1))
            painter.drawRect(QRectF(-size*0.4, -size*0.4, size*0.8, size*0.8))
            label_prefix = "?"

        # Label darunter (konstante Bildschirmgroesse, nicht abschneiden).
        # LOD 0 = "PREFIX Name", LOD 1 = nur Kurz-Label (spart Breite bei Dichte),
        # LOD 2 = kein Label (Selektion/Hover bekommt vom Canvas immer LOD 0).
        if lod <= 1:
            painter.setPen(QColor("#bbb"))
            painter.setFont(_schrift(8 * tscale))
            text_rect = label_rect(size, tscale)
            if lod == 0:
                _txt = (f"{label_prefix} {label}" if label else label_prefix)
            else:
                _txt = (label if label else label_prefix)
            painter.drawText(text_rect,
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
                             | Qt.TextFlag.TextDontClip,
                             _txt)

        # Intensity-Wert oben — nur bei voller Detailstufe (sonst Text-Salat)
        _pct_w = 0.0
        if intensity > 0 and lod == 0:
            painter.setPen(QColor("#FFD700") if intensity > 200 else QColor("#aaa"))
            painter.setFont(_schrift(7 * tscale))
            inten_pct = int(intensity / 255 * 100)
            _pct_txt = f"{inten_pct}%"
            _pct_w = _text_breite(7 * tscale, _pct_txt)
            painter.drawText(oben_rect(size, tscale),
                            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom
                            | Qt.TextFlag.TextDontClip,
                            _pct_txt)

        # FX-Badge oben rechts (Geometrie + Schrift bildschirm-konstant) — nur LOD 0
        if effects and lod == 0:
            badge_rect = fx_badge_rect(size, tscale, _pct_w)
            _form(painter, _kx, "rr", (badge_rect.x(), badge_rect.y(), badge_rect.width(),
                                  badge_rect.height(), 3 * tscale, 3 * tscale),
                  brush=_B_FX[0], brush_key=_B_FX[1])
            painter.setPen(QColor(210, 230, 255))
            painter.setFont(_schrift(6 * tscale, True))
            painter.drawText(badge_rect,
                             Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextDontClip,
                             f"FX{len(effects)}" if len(effects) > 1 else "FX")

        painter.restore()


# ── UI-64(g): Text-Geometrie rund um das Symbol ─────────────────────────────
# Die Ringe (Effekt 0.72, Auswahl 0.70, Gruppe 0.82 x size plus halbe
# Stiftbreite) liegen in Weltkoordinaten. Frueher sass das Label ab
# ``size*0.55`` — der gelbe Auswahlring lief mitten durch die Schrift — und das
# FX-Badge ab ``size*0.25`` rechts der Mitte, also ueber dem zentrierten
# „100%". Jetzt beginnen alle Texte ausserhalb des AEUSSERSTEN Rings, auch wenn
# er gerade nicht gezeichnet wird: so springt beim Anklicken nichts.

def ring_aussenradius(size: float) -> float:
    """Aeusserer Rand des groessten Rings (Gruppen-Highlight, Stift 4)."""
    return size * 0.82 + 2.0


def label_rect(size: float, tscale: float = 1.0) -> QRectF:
    """Rahmen des Labels unter dem Symbol (Text oben buendig darin)."""
    top = ring_aussenradius(size) + 2.0 * tscale
    return QRectF(-size, top, size * 2, 16 * tscale)


def oben_rect(size: float, tscale: float = 1.0) -> QRectF:
    """Rahmen des %-Schilds ueber dem Symbol (Text unten buendig darin)."""
    h = 12 * tscale
    bottom = -(ring_aussenradius(size) + 2.0 * tscale)
    return QRectF(-size, bottom - h, size * 2, h)


def fx_badge_rect(size: float, tscale: float = 1.0,
                  pct_breite: float = 0.0) -> QRectF:
    """FX-Badge auf Hoehe des %-Schilds, rechts NEBEN dessen Text.

    ``pct_breite`` = Breite des zentrierten %-Texts (0, wenn keiner da ist)."""
    bw, bh = 22 * tscale, 12 * tscale
    oben = oben_rect(size, tscale)
    x = max(size * 0.25, pct_breite / 2 + 3.0 * tscale)
    return QRectF(x, oben.bottom() - bh, bw, bh)


def _lod_for_screen_gap(screen_gap: float) -> int:
    """UI-26/QOL: Bildschirm-Abstand zum naechsten Nachbarn -> Label-Detailgrad.
    0 = volles Label + Intensity% + FX-Badge, 1 = nur Kurz-Label, 2 = kein Text.
    Reine Schwellenfunktion (kein Qt) -> trivial unit-testbar. Schwellen so, dass
    das ~72 px breite Label-Rect erst faellt, wenn Nachbarn wirklich zu nah sind."""
    if screen_gap >= 48.0:
        return 0
    if screen_gap >= 22.0:
        return 1
    return 2


def _grid_positions(n: int, world_w: float, world_h: float,
                    min_step: float = 90.0,
                    margin: float = 60.0) -> list[tuple[float, float]]:
    """QOL-01: n Fixtures ohne gespeicherte Position in ein zeilenweises Raster
    INNERHALB der Welt legen (frueher ein dicht gedraengter Halbkreis -> beim ersten
    Start unlesbarer Label-Salat). Normalfall: Schrittweite ``min_step`` (>= Label-
    Breite ~72 px) -> bei Zoom 1.0 sind alle Labels frei. Passen bei ``min_step``
    nicht alle Zeilen in ``world_h`` (sehr grosse Rigs), wird die Schrittweite so
    geschrumpft, dass ALLE Fixtures im sichtbaren, fix-grossen Canvas
    ``[margin, world-margin]`` bleiben (die dann dichteren Labels uebernimmt das
    LOD-System) — statt sie wie zuvor unbegrenzt ueber ``world_h`` hinaus
    off-canvas/unerreichbar wachsen zu lassen. Reine Funktion -> testbar."""
    if n <= 0:
        return []
    usable_w = max(1.0, world_w - 2.0 * margin)
    usable_h = max(1.0, world_h - 2.0 * margin)
    cols = max(1, min(n, int(usable_w // min_step) or 1))
    rows = (n + cols - 1) // cols
    step_x = step_y = min_step
    if rows > 1 and (rows - 1) * step_y > usable_h:
        # Zeilen sprengen die Hoehe -> flaechenfuellendes Raster, das sicher passt.
        from math import sqrt, ceil
        cols = max(1, min(n, int(ceil(sqrt(n * usable_w / usable_h)))))
        rows = (n + cols - 1) // cols
        step_x = usable_w / (cols - 1) if cols > 1 else 0.0
        step_y = usable_h / (rows - 1) if rows > 1 else 0.0
    out: list[tuple[float, float]] = []
    for i in range(n):
        r, c = divmod(i, cols)
        out.append((margin + c * step_x, margin + r * step_y))
    return out


def _compute_fit_zoom(bbox_w: float, bbox_h: float, view_w: float, view_h: float,
                      margin: float = 1.3, lo: float = 0.25, hi: float = 4.0) -> float:
    """QOL-05: Zoom, der ein ``bbox_w × bbox_h`` (Welt-px) grosses Fixture-Rechteck
    in ein ``view_w × view_h`` Sichtfeld einpasst (mit etwas Rand), geklemmt auf
    ``[lo, hi]``. Reine Funktion — die 2D-Ansicht zoomt damit beim Laden so, dass
    ein kompaktes (aus 3D projiziertes) Rig die Flaeche fuellt statt zu klumpen."""
    bw = max(1.0, float(bbox_w)) * max(1.0, margin)
    bh = max(1.0, float(bbox_h)) * max(1.0, margin)
    z = min(max(1.0, view_w) / bw, max(1.0, view_h) / bh)
    return max(lo, min(hi, z))


# ── Stage-Canvas ──────────────────────────────────────────────────────────────

class StageCanvas(QWidget):
    """Zeichnet die Stage von oben mit allen Fixtures."""

    fixture_clicked = Signal(int)   # fid
    selection_changed = Signal()    # Auswahl geaendert (Phase 7b)
    zoom_requested = Signal(int)    # Strg+Mausrad -> gewuenschter Zoom in %
    context_menu_requested = Signal(int, object)  # (fid|-1, global QPoint)

    # Takt der 2D-Vorschau. Sie zeichnet Raster, Fixtures und Overlays komplett
    # in Python/QPainter; 50 ms (20 FPS) belegten auf dem Linux-Zielrechner
    # schon im Leerlauf einen grossen Teil eines CPU-Kerns. 100 ms sind fuer die
    # Vorschau fluessig genug — DMX-Ausgabe und Playback haben ihren EIGENEN
    # Takt und sind davon nicht betroffen. Eine Zahl, beide Startstellen:
    # wer die Vorschau wieder fluessiger will, aendert nur diese Konstante.
    RENDER_INTERVAL_MS = 100

    def __init__(self, parent=None):
        super().__init__(parent)

        # Welt-Groesse und Raster aus Prefs laden
        lv_prefs = _load_prefs().get("live_view", {})
        self.world_w: int = int(lv_prefs.get("world_w", 1200))
        self.world_h: int = int(lv_prefs.get("world_h", 800))
        self.grid_size: int = int(lv_prefs.get("grid_size", 50))
        self.snap_enabled: bool = bool(lv_prefs.get("snap", True))
        self.grid_visible: bool = bool(lv_prefs.get("grid_visible", True))
        self.zoom: float = max(0.25, min(4.0, float(lv_prefs.get("zoom", 1.0))))

        self._apply_canvas_size()
        self.setStyleSheet("background:#0d1117;")
        # VIZ-70: paintEvent deckt die ganze Flaeche selbst deckend ab
        # (Hintergrund-Pixmap bzw. fillRect ueber die Welt, Canvas = Welt x Zoom)
        # -> Qt muss den Stylesheet-Hintergrund vorher nicht extra fuellen.
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAcceptDrops(True)
        # Fokus annehmen, damit Tastatur (Esc = Auswahl leeren) ankommt
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._state = get_state()
        # Fixture-Positionen (fid -> (x, y) in Welt-Koordinaten)
        self._positions: dict[int, tuple[float, float]] = {}
        # QOL/UI-26: Nachbar-Abstand (Welt-px) je Fixture fuer die LOD-Label-Wahl;
        # in _load_positions() UND _notify_layout_changed() (nach Drag/place_fixture)
        # neu berechnet -> bleibt nach jeder Positions-Aenderung konsistent.
        self._nn_gap: dict[int, float] = {}
        # Icon-Groesse per Pref justierbar (Davids "kleiner skalieren"-Wunsch als
        # Self-Service); Default moderat 30 -> MH-Kopf (size*0.4) bleibt erkennbar.
        self._fixture_size: float = float(lv_prefs.get("fixture_size", 30.0))
        self._selected_fids: list[int] = []
        # FM-51 C: Geraete, die NUR ueber Weiss-Segmente gewaehlt sind ("1:w3").
        # Reine ANZEIGE (Ring) — bewusst getrennt von ``_selected_fids``, denn
        # die Canvas-Auswahl wird bei Klick/Gummiband/„Gruppe aus Auswahl"
        # zurueckgeschrieben und machte das Segment sonst zum ganzen Geraet.
        self._teil_fids: set[int] = set()
        self._drag_fid: int | None = None
        self._drag_offset: QPointF = QPointF()
        # Drag-Schwelle: ein reiner Klick (ohne Bewegung) darf das Fixture weder
        # ans Raster snappen noch die Show als "geaendert" markieren.
        self._drag_press: QPointF = QPointF()
        self._drag_moved: bool = False

        # Gruppen-Hervorhebung (Phase 7a)
        self._highlight_fids: set[int] = set()

        # Rubber-Band + Multi-Drag (Phase 7b)
        self._band_origin: QPointF | None = None
        self._band_rect: QRectF | None = None
        self._multi_drag_start: dict[int, tuple] | None = None
        self._multi_mouse_start: QPointF | None = None
        self._multi_moved: bool = False

        # Touch-Mehrfachauswahl-Modus: Antippen toggelt die Auswahl (kein Shift noetig)
        self._multi_select_mode: bool = False

        # Positionen aus der Show laden (eigener 2D-Store, Migration aus 3D-Viz)
        self._load_positions()

        # VIZ-70: Zustand fuer gedrosseltes Neuzeichnen und den Hintergrund-Cache.
        # ``_paint_sig`` = Signatur der angezeigten Werte beim letzten Takt,
        # ``_animiert`` = das letzte Bild hatte Pulsringe/Strobe-Blinken (dann
        # aendert sich das Bild auch ohne neue Werte und jeder Takt zeichnet).
        self._paint_sig: tuple | None = None
        self._animiert: bool = True
        self._takte_ohne_paint: int = 0
        self._bg_pixmap = None
        self._bg_key: tuple | None = None
        # VIZ-78: Geraete-Steckbriefe (siehe _steckbrief).
        self._steckbriefe: dict = {}
        self._tick_fp: dict | None = None
        self._steckbrief_zeit: float = time.monotonic()

        # Live-Update: der Takt fragt erst, ob sich ueberhaupt etwas zeigt
        # (siehe _on_render_tick), statt blind update() zu rufen.
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._on_render_tick)
        self._update_timer.start(self.RENDER_INTERVAL_MS)

        # Bei Show-Load / Refresh die Positionen neu laden
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            sync.subscribe(SyncEvent.SHOW_LOADED, lambda *_: self._reload_positions_safe())
            sync.subscribe(SyncEvent.REFRESH_ALL, lambda *_: self._reload_positions_safe())
            # VIZ-70: Patch-/Profil-Aenderung (Umadressieren, Mode, Bereiche,
            # Invert …) -> beim naechsten Takt sofort neu zeichnen, nicht erst
            # nach dem Sicherheitsnetz. An die Widget-Lebenszeit gebunden.
            sync.subscribe_widget(SyncEvent.PATCH_CHANGED, self,
                                  weak_slot(self._patch_geaendert))
        except Exception as e:
            print(f"[live_view] sync subscribe error: {e}")

    # ── Highlight (Gruppen-Hervorhebung) ─────────────────────────────────────

    def set_highlight(self, fids: set[int]) -> None:
        """Setzt die Menge der hervorgehobenen Fixtures (Gruppen-Highlight, cyan Ring)."""
        self._highlight_fids = set(fids)
        self.update()

    def set_selection(self, fids) -> None:
        """P2: Auswahl von aussen setzen (linke Liste → Canvas-Highlight).
        Bewusst OHNE selection_changed-Emit — der Aufrufer pflegt den globalen
        State selbst (sonst Ping-Pong zwischen Liste und Canvas)."""
        self._selected_fids = list(fids)
        self.update()

    def _teil_auswahl_entfernen(self, fid: int) -> None:
        """Nimmt die Weiss-Segment-Zellen von ``fid`` aus der globalen Auswahl."""
        try:
            from src.core.group_cells import ACHSE_WEISS, parse_zelle
            st = get_state()
            rest = []
            for z in st.get_selected_cells():
                zf, achse, _idx = parse_zelle(z)
                if zf is not None and int(zf) == int(fid) and achse == ACHSE_WEISS:
                    continue
                rest.append(z)
            self._teil_fids.discard(int(fid))
            st.set_selected_cells(rest)
        except Exception as e:
            print(f"[live_view] Teil-Auswahl entfernen: {e}")

    def set_teil_markierung(self, fids) -> None:
        """FM-51 C: nur ueber Weiss-Segmente gewaehlte Geraete markieren (Ring),
        ohne sie in die Canvas-Auswahl aufzunehmen."""
        self._teil_fids = {int(f) for f in (fids or ())}
        self.update()

    # ── Canvas-Groesse (Welt × Zoom) ─────────────────────────────────────────

    def _apply_canvas_size(self) -> None:
        """Berechnet Canvas-Groesse aus Welt-Groesse mal Zoom und setzt setFixedSize."""
        self.setFixedSize(int(self.world_w * self.zoom), int(self.world_h * self.zoom))

    def set_zoom(self, z: float) -> None:
        """Setzt neuen Zoom-Faktor (geklemmt auf [0.25, 4.0])."""
        self.zoom = max(0.25, min(4.0, float(z)))
        self._apply_canvas_size()
        self.update()

    def set_active(self, on: bool) -> None:
        """Startet/stoppt den 20-FPS-Render-Timer — pausiert, wenn die Live View
        nicht der sichtbare Tab ist (spart CPU im Hintergrund)."""
        try:
            if on:
                # Nach dem Wiedereinblenden sofort ein frisches Bild.
                self._paint_sig = None
                if not self._update_timer.isActive():
                    self._update_timer.start(self.RENDER_INTERVAL_MS)
            else:
                self._update_timer.stop()
        except (RuntimeError, AttributeError):
            pass

    # ── VIZ-70: gedrosseltes Neuzeichnen ─────────────────────────────────────
    # Gemessen am Windows-Rig (Extremfall, 2D-Buehne sichtbar, 3D-Fenster
    # offen): ~65 % des Hauptthreads in paintEvent/draw — und genau dort setzt
    # QtWebEngine auch das 3D-Bild zusammen (3,6 FPS statt 57,7). Der Takt
    # zeichnet deshalb nur noch, wenn (1) die Flaeche ueberhaupt zu sehen ist
    # und (2) sich die angezeigten Werte geaendert haben oder das Bild animiert
    # ist. Hoechstens ein Bild je RENDER_INTERVAL_MS bleibt die Obergrenze.

    # Sicherheitsnetz: spaetestens nach so vielen Takten ohne Bild wird doch
    # gezeichnet (~1 s) — fuer Aenderungen, die die Signatur nicht sieht
    # (z. B. umbenanntes Geraet ohne Patch-Event).
    MAX_TAKTE_OHNE_PAINT = 10

    def _darf_zeichnen(self) -> bool:
        """Ist die Buehnenflaeche gerade irgendwo zu sehen?"""
        try:
            if not self.isVisible():
                return False
            win = self.window()
            if win is not None and win.isMinimized():
                return False
            if self.visibleRegion().isEmpty():
                return False
        except RuntimeError:
            return False
        return True

    def _anzeige_signatur(self) -> tuple | None:
        """Billige Signatur von allem, was paintEvent aus dem State liest:
        Rohwerte der Universen, laufende Funktionen (Effekt-Badges/Strobe),
        Programmer-Belegung (Badge „Programmer") und gepatchte Geraete.
        ``None`` = nicht ermittelbar -> immer zeichnen (altes Verhalten)."""
        try:
            st = self._state
            unis = tuple((u, bytes(uni.get_all()))
                         for u, uni in sorted(st.universes.items()))
            running = tuple(st.function_manager.running_ids())
            with st._prog_lock:
                prog = frozenset(f for f, v in st.programmer.items() if v)
            fids = tuple(self._patch_fingerabdruck(f)
                         for f in st.get_patched_fixtures())
        except Exception:
            return None
        return (unis, running, prog, fids)

    # Alles am gepatchten Geraet, was das 2D-Bild bestimmt (Adresse, Profil/
    # Mode, Typ, Label, Pan/Tilt-Bereich, Nullpunkte, Einmess-Versatz,
    # Invert/Swap). Fehlt ein Feld, steht None — die Signatur bleibt billig.
    _PATCH_FELDER = ("universe", "address", "fixture_profile_id", "mode_name",
                     "channel_count", "fixture_type", "label",
                     "pan_range_deg", "tilt_range_deg", "pan_zero_dmx",
                     "tilt_zero_dmx", "aim_offset_pan", "aim_offset_tilt",
                     "invert_pan", "invert_tilt", "swap_pan_tilt",
                     # get_channels_for_patched schluesselt auch danach
                     "spider_dual_tilt")

    @classmethod
    def _patch_fingerabdruck(cls, f) -> tuple:
        return (f.fid,) + tuple(getattr(f, k, None) for k in cls._PATCH_FELDER)

    def _patch_geaendert(self, *_a) -> None:
        self._paint_sig = None
        self._steckbriefe.clear()

    def _on_render_tick(self) -> None:
        if not self._darf_zeichnen():
            return
        sig = self._anzeige_signatur()
        self._takte_ohne_paint += 1
        if (not self._animiert and sig is not None and sig == self._paint_sig
                and self._takte_ohne_paint < self.MAX_TAKTE_OHNE_PAINT):
            return
        self._paint_sig = sig
        self._takte_ohne_paint = 0
        # VIZ-78: die Fingerabdruecke hat die Signatur eben schon gelesen —
        # das gleich folgende Bild nimmt sie, statt sie erneut abzufragen.
        self._tick_fp = ({fp[0]: fp for fp in sig[3]} if sig is not None else None)
        self.update()

    # ── VIZ-70: statischer Hintergrund als Pixmap ────────────────────────────
    # Raster (gepunktete, geglaettete Linien), Buehne und Publikum aendern sich
    # nur mit Welt-/Raster-/Zoom-Einstellung, wurden aber jedes Bild neu
    # gezeichnet. Ab dieser Pixelzahl wird nicht gecacht (Speicher: 4 Byte je
    # Pixel; Zoom 4 auf 1200x800 waeren ~61 MB) — dann wie bisher direkt.
    BG_CACHE_MAX_PIXEL = 6_000_000

    def _zeichne_hintergrund(self, painter: QPainter, tscale: float,
                             flaechen: bool = True, texte: bool = True) -> None:
        """Hintergrund, Raster, Buehne, Publikum — Painter ist bereits mit dem
        Zoom skaliert (Weltkoordinaten). ``flaechen``/``texte`` trennen, was in
        den Cache darf: die zwei Beschriftungen bekommen auf dem Widget
        Subpixel-Glaettung, in einem Bild nur Graustufen — sie werden deshalb
        immer direkt gezeichnet (liegen ueber ihrer Flaeche, nichts darueber)."""
        stage_rect = QRectF(self.world_w*0.15, 20, self.world_w*0.7, 60)
        aud_rect = QRectF(self.world_w*0.1, self.world_h - 60, self.world_w*0.8, 40)
        if not flaechen:
            self._zeichne_bereichstexte(painter, tscale, stage_rect, aud_rect)
            return
        painter.fillRect(QRectF(0, 0, self.world_w, self.world_h), QColor("#0d1117"))

        # Raster (ersetzt Punkt-Raster, wenn grid_visible)
        if self.grid_visible and self.grid_size > 0:
            painter.setPen(QPen(QColor("#1a1a25"), 1, Qt.PenStyle.DotLine))
            gs = self.grid_size
            x = 0
            while x <= self.world_w:
                painter.drawLine(x, 0, x, self.world_h)
                x += gs
            y = 0
            while y <= self.world_h:
                painter.drawLine(0, y, self.world_w, y)
                y += gs

        # "Stage"-Bereich oben (vereinfacht)
        painter.setPen(QPen(QColor("#444"), 2))
        painter.setBrush(QBrush(QColor("#1a1a2a")))
        painter.drawRoundedRect(stage_rect, 6, 6)

        # "Publikum"-Bereich unten
        painter.setPen(QPen(QColor("#333"), 1))
        painter.setBrush(QBrush(QColor("#0a0a10")))
        painter.drawRoundedRect(aud_rect, 4, 4)
        if texte:
            self._zeichne_bereichstexte(painter, tscale, stage_rect, aud_rect)

    @staticmethod
    def _zeichne_bereichstexte(painter: QPainter, tscale: float,
                               stage_rect: QRectF, aud_rect: QRectF) -> None:
        painter.setPen(QColor("#666"))
        painter.setFont(_schrift(9 * tscale, True))
        painter.drawText(stage_rect, Qt.AlignmentFlag.AlignCenter, "BÜHNE")
        painter.setPen(QColor("#555"))
        painter.setFont(_schrift(8 * tscale))
        painter.drawText(aud_rect, Qt.AlignmentFlag.AlignCenter, "PUBLIKUM")

    def _hintergrund_pixmap(self):
        """Gecachter Hintergrund in Geraetepixeln (oder ``None`` = direkt
        zeichnen). Neu gebaut nur, wenn sich Welt, Raster, Zoom oder die
        Pixeldichte des Bildschirms aendern."""
        try:
            dpr = float(self.devicePixelRatioF()) or 1.0
        except Exception:
            dpr = 1.0
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0 or w * h * dpr * dpr > self.BG_CACHE_MAX_PIXEL:
            return None
        key = (self.world_w, self.world_h, self.zoom, self.grid_visible,
               self.grid_size, w, h, dpr)
        if key == self._bg_key and self._bg_pixmap is not None:
            return self._bg_pixmap
        # Deckendes RGB32-Bild; die Beschriftungen kommen NICHT hinein (siehe
        # _zeichne_hintergrund).
        from PySide6.QtGui import QImage
        # Aufrunden: bei gebrochenem DPR (1,25/1,5/1,75) waere round() eine
        # Geraetepixel-Spalte zu schmal — wegen WA_OpaquePaintEvent bliebe dort
        # Altes bzw. Schwarz stehen.
        pm = QImage(max(1, math.ceil(w * dpr)), max(1, math.ceil(h * dpr)),
                    QImage.Format.Format_RGB32)
        pm.setDevicePixelRatio(dpr)
        pm.fill(QColor("#0d1117"))
        p = QPainter(pm)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.scale(self.zoom, self.zoom)
            self._zeichne_hintergrund(p, 1.0 / self.zoom if self.zoom > 0 else 1.0,
                                      texte=False)
        finally:
            p.end()
        self._bg_pixmap = pm
        self._bg_key = key
        return pm

    # ── Koordinaten-Umrechnung Canvas→Welt ───────────────────────────────────

    def _to_world(self, pt) -> QPointF:
        """Rechnet Canvas-Pixel-Koordinaten in Welt-Koordinaten um."""
        return QPointF(pt.x() / self.zoom, pt.y() / self.zoom)

    def set_multi_select_mode(self, on: bool) -> None:
        """Touch-Modus: Antippen toggelt Fixtures in die Auswahl (statt zu ersetzen).

        Ohne Shift-Taste (Touch-Display) kann man so mehrere Geraete sammeln.
        Auf leerer Flaeche ziehen waehlt weiterhin einen Rahmen (im Modus additiv).
        """
        self._multi_select_mode = bool(on)

    # ── Welt-Groesse ──────────────────────────────────────────────────────────

    def set_world_size(self, w: int, h: int) -> None:
        """Setzt neue Welt-Groesse und passt Canvas-Groesse an."""
        self.world_w = int(w)
        self.world_h = int(h)
        self._apply_canvas_size()
        self.update()

    # ── Snap-Helfer ───────────────────────────────────────────────────────────

    def _snap(self, x: float, y: float) -> tuple[float, float]:
        """Snappt Koordinaten ans Raster und clampt in Welt-Grenzen."""
        if self.snap_enabled and self.grid_size > 0:
            gs = self.grid_size
            x = round(x / gs) * gs
            y = round(y / gs) * gs
        x = max(0.0, min(float(self.world_w), x))
        y = max(0.0, min(float(self.world_h), y))
        return x, y

    # ── Auswahl-Helfer (Phase 7b) ─────────────────────────────────────────────

    def _fixture_at(self, pos: QPointF):
        """Gibt die fid des Fixtures an Canvas-Position pos zurueck, oder None.

        Touch: Es gewinnt das NÄCHSTE Fixture im Trefferradius (nicht das
        erste in Dict-Reihenfolge — wichtig bei dicht platzierten Geräten).
        Im Mehrfachauswahl-Modus ist der Radius mindestens ~24 Bildschirm-
        Pixel, damit auch bei kleinem Zoom mit dem Finger getroffen wird."""
        r = self._fixture_size * 0.6
        if self._multi_select_mode:
            r = max(r, 24.0 / max(0.25, self.zoom))
        best_fid, best_d = None, r * r
        for fid, (x, y) in self._positions.items():
            dx = pos.x() - x
            dy = pos.y() - y
            d = dx * dx + dy * dy
            if d < best_d:
                best_fid, best_d = fid, d
        return best_fid

    def _select_in_rect(self, rect: QRectF | None, additive: bool) -> None:
        """Waehlt alle Fixtures innerhalb von rect aus (canvas-Koordinaten)."""
        inside = [
            fid for fid, (x, y) in self._positions.items()
            if rect is not None and rect.contains(QPointF(x, y))
        ]
        if additive:
            for fid in inside:
                if fid not in self._selected_fids:
                    self._selected_fids.append(fid)
        else:
            self._selected_fids = inside
        self._emit_selection()

    def _emit_selection(self) -> None:
        """Feuert selection_changed und synchronisiert den globalen State."""
        try:
            self.selection_changed.emit()
        except Exception:
            pass

    # ── Platzier-Methode (auch von dropEvent genutzt) ─────────────────────────

    def place_fixture(self, fid: int, x: float, y: float) -> None:
        """Platziert ein Fixture an Position (x, y) — mit Snap und Persistenz."""
        x, y = self._snap(x, y)
        self._positions[fid] = (x, y)
        try:
            self._state.live_view_positions[fid] = (float(x), float(y))
        except Exception:
            pass
        self._notify_layout_changed()
        self.update()

    def _notify_layout_changed(self) -> None:
        """P4: Layout-Aenderung melden (Dirty-Flag fuer Auto-Save).

        UI-26: Dieser Hook laeuft nach JEDER Positions-Mutation ausserhalb von
        ``_load_positions`` (place_fixture, Einzel-/Multi-Drag-Release, Snap) — hier
        die Nachbar-Abstaende fuer die LOD-Label-Wahl neu berechnen. Sonst blieb der
        ``_nn_gap``-Cache nach dem Verschieben stale: zusammengeschobene Fixtures
        zeigten weiter volle, ueberlappende Labels (und auseinandergezogene blieben
        faelschlich abgekuerzt), bis erst der naechste Show-Reload korrigierte."""
        self._compute_label_gaps()
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.LIVE_VIEW_CHANGED, None)
        except Exception:
            pass

    # ── Drag & Drop von der Fixture-Liste ─────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-fid"):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-fid"):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat("application/x-fid"):
            return
        try:
            fid = int(bytes(event.mimeData().data("application/x-fid")).decode())
        except Exception:
            return
        raw = event.position() if hasattr(event, "position") else QPointF(event.pos())
        pos = self._to_world(raw)
        self.place_fixture(fid, float(pos.x()), float(pos.y()))
        event.acceptProposedAction()

    # ── Positions-Laden ───────────────────────────────────────────────────────

    def _reload_positions_safe(self):
        try:
            self._steckbriefe.clear()
            self._load_positions()
            self._apply_meta_from_state()
            self.update()
        except RuntimeError:
            pass  # Widget beim Layout-Wechsel geloescht

    def _apply_meta_from_state(self):
        """P4: Show-spezifische Live-View-Einstellungen (Zoom/Grid/Snap/Welt)
        aus state.live_view_meta anwenden. Alte Shows ohne Meta-Block behalten
        die ui_prefs-Defaults (Fallback) — kein Fehler, kein Reset."""
        meta = getattr(self._state, "live_view_meta", None)
        if not isinstance(meta, dict) or not meta:
            return
        try:
            if "world_w" in meta and "world_h" in meta:
                self.set_world_size(int(meta["world_w"]), int(meta["world_h"]))
            if "grid_size" in meta:
                self.grid_size = int(meta["grid_size"])
            if "snap" in meta:
                self.snap_enabled = bool(meta["snap"])
            if "grid_visible" in meta:
                self.grid_visible = bool(meta["grid_visible"])
            if "zoom" in meta:
                self.set_zoom(float(meta["zoom"]))
        except Exception as e:
            print(f"[live_view] apply meta error: {e}")

    def _load_positions(self):
        """Live-View-Positionen aus dem persistenten 2D-Store laden.

        Reihenfolge: (1) gespeicherte 2D-Positionen, (2) Migration aus dem
        3D-Visualizer (x,z), (3) Auto-Layout im Halbkreis. Das Ergebnis wird in
        ``state.live_view_positions`` zurueckgeschrieben, damit es mit der Show
        persistiert — auch ohne dass ein Fixture verschoben wurde.
        """
        state = self._state
        lv = getattr(state, "live_view_positions", None)
        if lv is None:
            state.live_view_positions = {}
            lv = state.live_view_positions
        try:
            fixtures = state.get_patched_fixtures()
        except Exception:
            fixtures = []
        if not fixtures:
            return
        self._positions = {}
        # 1) gespeicherte 2D-Positionen
        for f in fixtures:
            if f.fid in lv:
                try:
                    x, y = lv[f.fid]
                    self._positions[f.fid] = (float(x), float(y))
                except Exception:
                    pass
        # 2) Migration aus dem 3D-Visualizer (x=links/rechts, z=vorne/hinten)
        viz = getattr(state, "visualizer_positions", {}) or {}
        for f in fixtures:
            if f.fid not in self._positions and f.fid in viz:
                try:
                    x3d, _y3d, z3d = viz[f.fid]
                    # EINE Quelle fuer die 2D<->3D-Umrechnung (coords), statt die
                    # Konstanten PX_PER_M/ORIGIN_PX hier ein drittes Mal zu verdrahten.
                    self._positions[f.fid] = world3d_to_live(x3d, z3d)
                except Exception:
                    pass
        # 3) Auto-Layout: gleichmaessiges Raster mit label-sicherem Abstand.
        #    QOL-01: frueher ein dicht gedraengter Halbkreis -> beim ersten Start
        #    (Patch ohne gespeicherte Positionen) lagen die Fixtures fast
        #    uebereinander und die Labels wurden zu unlesbarem Salat. Ein Raster mit
        #    STEP_X >= Label-Breite (~72 px) zeigt bei Zoom 1.0 ALLE Labels. Nur der
        #    Auto-Layout-Zweig aendert sich -> gespeicherte 2D-/3D-Positionen (1+2)
        #    bleiben unangetastet und persistieren wie bisher.
        missing = [f for f in fixtures if f.fid not in self._positions]
        if missing:
            for f, (px, py) in zip(missing, _grid_positions(len(missing),
                                                            self.world_w, self.world_h)):
                self._positions[f.fid] = (px, py)
        # zurueckschreiben -> persistiert mit der Show
        for fid, (x, y) in self._positions.items():
            lv[fid] = (float(x), float(y))
        # UI-26: Nachbar-Abstaende fuer die LOD-Label-Wahl neu berechnen. Weitere
        # Positions-Mutationen (Drag/place_fixture) frischen ueber
        # _notify_layout_changed() ebenfalls auf -> nn_gap bleibt konsistent.
        self._compute_label_gaps()

    def _compute_label_gaps(self) -> None:
        """UI-26: pro Fixture den WELT-Abstand zum naechsten Nachbarn cachen
        (``self._nn_gap``). Mal Zoom ergibt das den Bildschirm-Abstand, aus dem
        ``_lod_for_screen_gap`` den Label-Detailgrad waehlt. Naiv O(n^2) — reicht
        fuer reale Rigs (Dutzende bis wenige hundert Fixtures); Einzel-Fixture ->
        Default 1e9 (immer volles Label)."""
        pts = list(self._positions.items())
        gaps: dict[int, float] = {}
        for i, (fid, (x, y)) in enumerate(pts):
            best = 1e9
            for j, (_ofid, (ox, oy)) in enumerate(pts):
                if i == j:
                    continue
                d = ((x - ox) ** 2 + (y - oy) ** 2) ** 0.5
                if d < best:
                    best = d
            gaps[fid] = best
        self._nn_gap = gaps

    # ── Strobe / Effekte ──────────────────────────────────────────────────────

    def _running_functions(self) -> list:
        """Thread-sicherer Snapshot der laufenden Funktionen (einmal pro Frame
        bauen und an _get_strobe_info / _get_active_effects durchreichen, statt
        pro Fixture erneut fm.running_ids()/get() aufzurufen — B-8)."""
        out = []
        try:
            fm = self._state.function_manager
            for func_id in fm.running_ids():
                func = fm.get(func_id)
                if func is not None:
                    out.append(func)
        except Exception:
            pass
        return out

    @staticmethod
    def _menge(seq) -> set:
        """``set(seq)`` ohne Ausnahme bei nicht hashbaren Elementen (die ohnehin
        nie gleich einer fid sind) — ``fid in menge`` == ``fid in seq``."""
        out = set()
        for x in seq:
            try:
                out.add(x)
            except TypeError:
                pass
        return out

    def _effekt_vorab(self, running) -> dict:
        """VIZ-70: EINMAL je Bild, was bisher je Fixture ueber ALLE laufenden
        Funktionen und deren Geraetelisten lief (O(Fixtures x Funktionen x
        Mitglieder)). Liefert dieselben Ergebnisse wie die Schleifen in
        ``_get_strobe_info``/``_get_active_effects``:

        - ``"namen"``: fid -> Funktionsnamen in Laufreihenfolge
        - ``"square"``: fid -> Frequenz der ersten SQUARE-Ebene (erste > 0 gewinnt,
          sonst der zuletzt gefundene Wert — wie dort)
        - ``"prog"``: fids mit Programmer-Werten"""
        namen: dict[int, list[str]] = {}
        square: dict[int, float] = {}
        prog: set = set()
        try:
            from src.core.engine.effect_layers import LayerType
            _square = LayerType.SQUARE
        except Exception:
            _square = None
        for func in running:
            try:
                fixture_ids = getattr(func, 'fixture_ids', None)
                fixtures = getattr(func, 'fixtures', None)
                grid = getattr(func, 'fixture_grid', None)
                vals = getattr(func, '_values', None)
                hit: set = set()
                if isinstance(fixture_ids, (list, tuple, set)):
                    hit |= self._menge(fixture_ids)
                if isinstance(fixtures, (list, tuple)):
                    hit |= self._menge(getattr(fx, 'fid', None) for fx in fixtures)
                if isinstance(grid, (list, tuple)):
                    hit |= self._menge(grid)
                if isinstance(vals, (list, tuple)):
                    hit |= self._menge(getattr(sv, 'fixture_id', None) for sv in vals)
                for fid in hit:
                    namen.setdefault(fid, []).append(func.name)
            except Exception:
                pass
            try:
                if (_square is not None and hasattr(func, 'fixture_ids')
                        and hasattr(func, 'layers')
                        and getattr(func, 'target_attribute', '') == 'intensity'):
                    freq = None
                    for layer in func.layers:
                        if layer.type == _square:
                            freq = layer.frequency
                            break
                    if freq is not None:
                        for fid in self._menge(func.fixture_ids):
                            if square.get(fid, 0.0) > 0.0:
                                continue
                            square[fid] = freq
            except Exception:
                pass
        try:
            with self._state._prog_lock:
                prog = {f for f, v in self._state.programmer.items() if v}
        except Exception:
            prog = set()
        return {"namen": namen, "square": square, "prog": prog}

    def _get_strobe_info(self, fid: int, fixture, running=None,
                         vorab: dict | None = None) -> tuple[float, bool]:
        """Gibt (freq_hz, is_currently_on) zurück. freq_hz=0 → kein Blinken.
        ``vorab`` (VIZ-70): Ergebnis von ``_effekt_vorab`` fuer dieses Bild."""
        freq_hz = 0.0

        # 1. Shutter/Strobe-DMX-Kanal auslesen
        try:
            universe = self._state.universes.get(fixture.universe)
            if universe:
                channels = get_channels_for_patched(fixture)
                for ch in channels:
                    if ch.attribute in ("shutter", "strobe"):
                        addr = fixture.address + ch.channel_number - 1
                        if 1 <= addr <= 512:
                            freq_hz = max(freq_hz, _strobe_hz(ch, universe.get_channel(addr)))
        except Exception:
            pass

        # 2. LayeredEffect mit Square-Wave auf Intensity
        if freq_hz == 0.0 and vorab is not None:
            freq_hz = vorab["square"].get(fid, 0.0)
        elif freq_hz == 0.0:
            try:
                from src.core.engine.effect_layers import LayerType
                funcs = running if running is not None else self._running_functions()
                for func in funcs:
                    if (hasattr(func, 'fixture_ids') and fid in func.fixture_ids
                            and hasattr(func, 'layers')
                            and getattr(func, 'target_attribute', '') == 'intensity'):
                        for layer in func.layers:
                            if layer.type == LayerType.SQUARE:
                                freq_hz = layer.frequency
                                break
                    if freq_hz > 0.0:
                        break
            except Exception:
                pass

        if freq_hz == 0.0:
            return 0.0, True

        # Aktueller On/Off-Zustand anhand Systemzeit berechnen
        phase = (time.time() * freq_hz) % 1.0
        return freq_hz, phase < 0.5

    def _get_active_effects(self, fid: int, strobe_hz: float = 0.0,
                            running=None, vorab: dict | None = None) -> list[str]:
        """Gibt Liste der aktiven Effekt-/Funktionsnamen zurück, die dieses Fixture betreffen."""
        effects = []
        if strobe_hz > 0.0:
            effects.append(f"Strobe {strobe_hz:.1f} Hz")
        if vorab is not None:
            # VIZ-70: einmal je Bild vorberechnet (gleiche Treffer-Regeln).
            effects.extend(vorab["namen"].get(fid, ()))
            if fid in vorab["prog"]:
                effects.append("Programmer")
            return effects
        try:
            funcs = running if running is not None else self._running_functions()
            for func in funcs:
                # Welche Geraete steuert die Funktion? Je Typ anders gespeichert —
                # und nur ECHTE Sequenz-Attribute pruefen: EfxInstance._values() ist
                # eine Methode (nicht Scene's Liste), daher isinstance-Guard. Vorher
                # warf das bei laufenden EFX/Matrix eine Exception -> sie wurden in
                # der Info-Box NIE als aktiv angezeigt.
                fixture_ids = getattr(func, 'fixture_ids', None)   # Carousel/LayeredEffect
                fixtures = getattr(func, 'fixtures', None)         # EFX (Objekte mit .fid)
                grid = getattr(func, 'fixture_grid', None)         # RGB-Matrix
                vals = getattr(func, '_values', None)              # Scene
                hit = False
                if isinstance(fixture_ids, (list, tuple, set)) and fid in fixture_ids:
                    hit = True
                elif isinstance(fixtures, (list, tuple)) and \
                        any(getattr(fx, 'fid', None) == fid for fx in fixtures):
                    hit = True
                elif isinstance(grid, (list, tuple)) and fid in grid:
                    hit = True
                elif isinstance(vals, (list, tuple)) and \
                        any(getattr(sv, 'fixture_id', None) == fid for sv in vals):
                    hit = True
                if hit:
                    effects.append(func.name)
        except Exception:
            pass
        # Programmer-Werte (unter demselben Lock lesen, den der Output-/MIDI-
        # Thread beim Mutieren haelt — sonst "dict changed size").
        try:
            with self._state._prog_lock:
                has_prog = bool(self._state.programmer.get(fid))
            if has_prog:
                effects.append("Programmer")
        except Exception:
            pass
        return effects

    # ── Info-Box ──────────────────────────────────────────────────────────────

    def _draw_info_box(self, painter: QPainter, fixture, color: QColor,
                       intensity: int, pan: int, tilt: int,
                       effects: list[str], fx: float, fy: float,
                       render_type: str | None = None):
        """Zeichnet ein Info-Overlay neben dem selektierten Fixture.

        Geometrie und Schrift werden mit 1/Zoom skaliert, damit die Box auf dem
        Bildschirm immer gleich gross und lesbar bleibt (der Painter ist global
        mit dem Zoom skaliert)."""
        s = 1.0 / self.zoom if self.zoom > 0 else 1.0
        has_pantilt = _has_pan_tilt(fixture, render_type)

        line_h = 15 * s
        # +1 Zeile fuer "Keine Effekte aktiv", wenn keine Effekte aktiv sind
        eff_lines = min(len(effects), 3) if effects else 1
        n_lines = 4 + (1 if has_pantilt else 0) + eff_lines
        box_w, box_h = 185 * s, 14 * s + n_lines * line_h

        # Position: rechts neben Fixture, bei Randüberschreitung links — und in
        # beide Richtungen in die Welt geklemmt (kein Abschneiden am Rand).
        bx = fx + self._fixture_size * 0.85
        by = fy - box_h / 2
        if bx + box_w > self.world_w - 8:
            bx = fx - self._fixture_size * 0.85 - box_w
        bx = max(8.0, min(bx, self.world_w - box_w - 8))
        by = max(8.0, min(by, self.world_h - box_h - 8))

        # Hintergrund (Rahmen bildschirm-konstant ~1 px)
        painter.setBrush(QBrush(QColor(12, 14, 32, 230)))
        painter.setPen(QPen(QColor("#FFD700"), 1 * s))
        painter.drawRoundedRect(QRectF(bx, by, box_w, box_h), 7 * s, 7 * s)

        tx = bx + 9 * s
        ty = by + 12 * s
        inner_w = box_w - 18 * s
        _AL = Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextDontClip

        def _font(pt, bold=False):
            f = QFont("Arial"); f.setPointSizeF(pt * s); f.setBold(bold)
            return f

        # Titel
        painter.setFont(_font(10, True))
        painter.setPen(QColor("#FFD700"))
        name = fixture.label or fixture.fixture_type or "?"
        painter.drawText(QRectF(tx, ty, inner_w, line_h), _AL, f"#{fixture.fid}  {name}")
        ty += line_h + 1 * s

        painter.setFont(_font(9))
        painter.setPen(QColor("#aaaaaa"))
        painter.drawText(QRectF(tx, ty, inner_w, line_h), _AL,
                         f"Typ: {fixture.fixture_type or '?'}")
        ty += line_h

        # Farb-Swatch + Hex
        swatch = QRectF(tx, ty + 2 * s, 11 * s, 11 * s)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(swatch)
        painter.setPen(QColor("#cccccc"))
        painter.setFont(_font(9))
        painter.drawText(QRectF(tx + 14 * s, ty, inner_w - 14 * s, line_h), _AL,
                         f"#{color.red():02X}{color.green():02X}{color.blue():02X}"
                         f"  ({color.red()},{color.green()},{color.blue()})")
        ty += line_h

        # Intensitäts-Balken
        pct = int(intensity / 255 * 100)
        bar_max = inner_w
        bar_fill = bar_max * intensity / 255
        painter.setBrush(QBrush(QColor(255, 200, 0, 40)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(QRectF(tx, ty + 3 * s, bar_max, 9 * s))
        painter.setBrush(QBrush(QColor(255, 200, 0, 130)))
        painter.drawRect(QRectF(tx, ty + 3 * s, bar_fill, 9 * s))
        painter.setPen(QColor("#FFD700"))
        painter.setFont(_font(8))
        painter.drawText(QRectF(tx, ty, inner_w, line_h), _AL, f"Intensität: {pct}%")
        ty += line_h

        # Pan/Tilt — Grad ueber den ECHTEN Bereich des Geraets (gleiche Quelle wie
        # 2D-Beam-Glyph und 3D-Visualizer), nicht mehr fix +-270/+-135.
        if has_pantilt:
            pan_rng = float(getattr(fixture, "pan_range_deg", 540) or 540)
            tilt_rng = float(getattr(fixture, "tilt_range_deg", 270) or 270)
            pan_z, tilt_z = effektive_nullpunkte(fixture)     # VIZ-55: inkl. Versatz
            pan_deg = int(dmx_to_angle_deg(pan, pan_z, pan_rng))
            tilt_deg = int(dmx_to_angle_deg(tilt, tilt_z, tilt_rng))
            painter.setPen(QColor("#aaaaaa"))
            painter.setFont(_font(9))
            painter.drawText(QRectF(tx, ty, inner_w, line_h), _AL,
                             f"Pan: {pan_deg:+d}°  Tilt: {tilt_deg:+d}°")
            ty += line_h

        # Effekte
        if effects:
            painter.setPen(QColor("#6699ff"))
            painter.setFont(_font(8))
            for eff in effects[:3]:
                painter.drawText(QRectF(tx, ty, inner_w, line_h), _AL, f"~ {eff}")
                ty += line_h
        else:
            painter.setPen(QColor("#555555"))
            painter.setFont(_font(8))
            painter.drawText(QRectF(tx, ty, inner_w, line_h), _AL, "Keine Effekte aktiv")

    # ── Farbe / Intensität ────────────────────────────────────────────────────

    def _fixture_color_and_intensity(self, fixture) -> tuple[QColor, int]:
        """Liest aktuelle DMX-Werte und gibt Farbe + Intensity zurueck.

        Farbe/Helligkeit kommen aus derselben Quelle wie im 3D-Visualizer
        (``color_utils.visual_rgb``/``visual_intensity``) — sonst driften 2D und
        3D auseinander. Insbesondere: Geraete OHNE RGB-Kanaele (Strobe/Blinder,
        Farbrad-Mover, reiner Dimmer-PAR) sind weiss statt schwarz, und Geraete
        OHNE Dimmer-Kanal folgen dem Shutter statt konstant 255 zu sein.
        """
        try:
            universe = self._state.universes.get(fixture.universe)
            if universe is None:
                return QColor(60, 60, 60), 0
            channels = get_channels_for_patched(fixture)
            # Mehrkopf-Geraete (Spider) liefern mehrere color_r/g/b-Kanaele —
            # wie der 3D-Top-Down-Icon den ERSTEN Satz (Kopf 0) verwenden, sonst
            # weicht die 2D-Farbe von der 3D-Farbe ab (letzter-gewinnt = Bank 2).
            attrs: dict[str, int] = {}
            for ch in channels:
                addr = fixture.address + ch.channel_number - 1
                if not (1 <= addr <= 512):
                    continue
                attr = ch.attribute
                if attr in attrs:
                    continue        # nur das ERSTE Vorkommen = Kopf 0
                attrs[attr] = universe.get_channel(addr)
            r, g, b = visual_rgb(attrs, channels)
            return QColor(r, g, b), visual_intensity(attrs, channels)
        except Exception:
            return QColor(60, 60, 60), 0

    # ── VIZ-78: Geraete-Steckbrief (was sich nur mit dem Patch aendert) ──────
    # Bis hierher fragte jedes Bild je Geraet Kanalliste, Render-Typ, Ring-
    # Segmente, Pan/Tilt-Bereich und Nullpunkte neu ab — ~140 ORM-Attribut-
    # zugriffe je Geraet und Bild. Der Steckbrief haelt das, gueltig solange
    # der Patch-Fingerabdruck gleich bleibt; Patch-Event, Show-Laden und
    # spaetestens STECKBRIEF_MAX_ALTER_S verwerfen ihn (Profil-Bearbeitung
    # ohne Fingerabdruck-Aenderung).
    STECKBRIEF_MAX_ALTER_S = 1.0

    def _steckbriefe_verwerfen(self) -> None:
        self._steckbriefe.clear()

    def _steckbrief(self, fixture, fp_map=None) -> dict:
        fp = fp_map.get(fixture.fid) if fp_map else None
        if fp is None:
            fp = self._patch_fingerabdruck(fixture)
        sb = self._steckbriefe.get(fixture.fid)
        if sb is not None and sb["fp"] == fp:
            return sb
        sb = {"fp": fp, "uni": fixture.universe, "label": f"{fixture.fid}",
              "farbe": [], "kanaele": [], "pt": [], "strobe": [], "ok": True}
        try:
            channels = get_channels_for_patched(fixture)
            sb["kanaele"] = channels
            gesehen = set()
            for ch in channels:
                addr = fixture.address + ch.channel_number - 1
                if not (1 <= addr <= 512):
                    continue
                attr = ch.attribute
                if attr not in gesehen:     # nur das ERSTE Vorkommen = Kopf 0
                    gesehen.add(attr)
                    sb["farbe"].append((attr, addr))
                if attr in _PT_ATTRS:
                    sb["pt"].append((attr, addr))
                if attr in ("shutter", "strobe"):
                    sb["strobe"].append((ch, addr, {}))
        except Exception:
            sb["ok"] = False
        # Verfeinerter Render-Typ: par_bar/mover_bar/spider werden von
        # moving_head getrennt — dieselbe zentrale Quelle wie das 3D-Modell
        # (viz_model_for), damit 2D-Symbol und 3D-Render nicht driften (FM-6/7).
        _base_type = fixture.fixture_type or "par"
        try:
            sb["render_type"] = viz_model_for(fixture) or _base_type
        except Exception:
            sb["render_type"] = _base_type
        # VIZ-53: Ring-Segmente eines Pixel-Kopfs stehen in den Kanaelen des
        # GEPATCHTEN Geraets — dieselbe Funktion beliefert die 3D-Nutzlast.
        sb["ring"] = 0
        if sb["render_type"] == "pixel_head":
            try:
                sb["ring"] = pixel_ring_segments(fixture)
            except Exception:
                sb["ring"] = 0
        sb["pr"] = float(getattr(fixture, "pan_range_deg", 540) or 540)
        sb["tr"] = float(getattr(fixture, "tilt_range_deg", 270) or 270)
        # VIZ-55: effektiver Nullpunkt (inkl. Einmess-Versatz), dieselbe Quelle
        # wie Zielen und 3D.
        sb["pz"], sb["tz"] = effektive_nullpunkte(fixture)
        self._steckbriefe[fixture.fid] = sb
        return sb

    def _wert_leser(self):
        """Liest DMX-Werte EINES Bilds: je Universum einmal ``get_all()``
        (ein Lock statt einer je Kanal), sonst ``get_channel``. Liefert
        ``None``, wenn es das Universum nicht gibt."""
        unis = self._state.universes
        puffer: dict = {}

        def lese(u, addr):
            b = puffer.get(u)
            if b is None:
                uni = unis.get(u)
                if not uni:
                    return None
                ga = getattr(uni, "get_all", None)
                b = ga() if ga is not None else uni
                puffer[u] = b
            if isinstance(b, (bytes, bytearray)):
                return b[addr - 1]
            return b.get_channel(addr)
        return lese

    def _farbe_aus_steckbrief(self, sb: dict, lese) -> tuple[QColor, int]:
        """Wie :meth:`_fixture_color_and_intensity`, aus dem Steckbrief."""
        try:
            if not sb["ok"] or lese(sb["uni"], 1) is None:
                return QColor(60, 60, 60), 0
            uni = sb["uni"]
            attrs = {a: lese(uni, addr) for a, addr in sb["farbe"]}
            r, g, b = visual_rgb(attrs, sb["kanaele"])
            return QColor(r, g, b), visual_intensity(attrs, sb["kanaele"])
        except Exception:
            return QColor(60, 60, 60), 0

    def _strobe_aus_steckbrief(self, sb: dict, lese, vorab) -> tuple[float, bool]:
        """Wie :meth:`_get_strobe_info` mit ``vorab``, aus dem Steckbrief;
        ``_strobe_hz`` je Kanal und Wert gemerkt."""
        freq_hz = 0.0
        try:
            if sb["strobe"] and lese(sb["uni"], 1) is not None:
                for ch, addr, memo in sb["strobe"]:
                    val = lese(sb["uni"], addr)
                    hz = memo.get(val)
                    if hz is None:
                        hz = memo[val] = _strobe_hz(ch, val)
                    freq_hz = max(freq_hz, hz)
        except Exception:
            pass
        if freq_hz == 0.0:
            freq_hz = vorab["square"].get(sb["fp"][0], 0.0)
        if freq_hz == 0.0:
            return 0.0, True
        phase = (time.time() * freq_hz) % 1.0
        return freq_hz, phase < 0.5

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        # VIZ-70: statischer Hintergrund aus dem Pixmap-Cache (1:1 in
        # Geraetepixeln, VOR Skalierung/Antialiasing) — sonst direkt wie bisher.
        bg = self._hintergrund_pixmap()
        if bg is not None:
            painter.drawImage(0, 0, bg)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(self.zoom, self.zoom)
        # Bereichs-Beschriftungen bildschirm-konstant halten (Painter ist skaliert)
        tscale = 1.0 / self.zoom if self.zoom > 0 else 1.0
        if bg is None:
            self._zeichne_hintergrund(painter, tscale)
        else:
            self._zeichne_hintergrund(painter, tscale, flaechen=False)

        # VIZ-70: nur Geraete im neu zu zeichnenden Bereich bearbeiten (Scroll-
        # Ausschnitt, Teil-Repaint unter der Minimap). Rand in Weltkoordinaten
        # grosszuegig: Symbol (<1x size), Ringe, Beam, Label/%/FX (bildschirm-
        # konstant, daher x tscale). Ausgewaehlte Geraete werden nie
        # uebersprungen (Info-Box).
        # Nur ein Bild, das die ganze SICHTBARE Flaeche neu zeichnet, darf
        # entscheiden, ob noch etwas animiert ist (``_voll``).
        try:
            _er = event.rect()
            _rand = self._fixture_size * 1.5 + 150 * tscale
            _clip = QRectF(_er.x() / self.zoom - _rand, _er.y() / self.zoom - _rand,
                           _er.width() / self.zoom + 2 * _rand,
                           _er.height() / self.zoom + 2 * _rand)
            _sichtbar = self.visibleRegion().boundingRect()
            _voll = _sichtbar.isEmpty() or _er.contains(_sichtbar)
        except Exception:
            _clip = None
            _voll = True

        # Fixtures
        try:
            fixtures = self._state.get_patched_fixtures()
        except Exception:
            fixtures = []
        # Falls neue Fixtures dazugekommen sind - Auto-Layout
        new_fids = [f.fid for f in fixtures if f.fid not in self._positions]
        if new_fids:
            self._load_positions()

        anim_phase = time.time() % 2.0 / 2.0  # 0..1 über 2 Sekunden (0.5 Hz)
        running = self._running_functions()  # einmal pro Frame statt pro Fixture
        vorab = self._effekt_vorab(running)  # VIZ-70: Effekt-Zuordnung je Bild
        animiert = False
        info_box_data = None  # (fixture, color, intensity, pan, tilt, effects, x, y)

        lese = self._wert_leser()
        fp_map, self._tick_fp = self._tick_fp, None
        jetzt_t = time.monotonic()
        if jetzt_t - self._steckbrief_zeit > self.STECKBRIEF_MAX_ALTER_S:
            self._steckbriefe.clear()
            self._steckbrief_zeit = jetzt_t
        for fixture in fixtures:
            if fixture.fid not in self._positions:
                continue
            x, y = self._positions[fixture.fid]
            if (_clip is not None and not _clip.contains(x, y)
                    and fixture.fid not in self._selected_fids):
                continue    # ausserhalb des Neuzeichen-Bereichs
            sb = self._steckbrief(fixture, fp_map)
            color, intensity = self._farbe_aus_steckbrief(sb, lese)
            pan = tilt = 128
            try:
                if sb["pt"] and lese(sb["uni"], 1) is not None:
                    _pt = {a: lese(sb["uni"], addr) for a, addr in sb["pt"]}
                    # VIZ-55: DRAHT -> MODELL wie im 3D (visualizer_service): die
                    # Ausgabestufe hat invert/swap angewandt, die 2D-Winkelformel
                    # kennt sie nicht — ohne Ruecknahme stand der Beam bei solchen
                    # Geraeten gespiegelt, und der Einmess-Versatz (Modellraum)
                    # bekam das falsche Vorzeichen. Feinkanal wie im 3D mit.
                    _pt = unapply_pan_tilt_orientation(fixture, _pt)
                    pan = _pt.get("pan", 128) + (_pt.get("pan_fine", 0) or 0) / 256.0
                    tilt = _pt.get("tilt", 128) + (_pt.get("tilt_fine", 0) or 0) / 256.0
            except Exception:
                pass
            strobe_hz, blink_on = self._strobe_aus_steckbrief(sb, lese, vorab)
            effects = self._get_active_effects(fixture.fid, strobe_hz, running, vorab)
            if effects or strobe_hz != 0.0:
                animiert = True
            label = sb["label"]
            _render_type = sb["render_type"]
            _ring = sb["ring"]
            _pr, _tr = sb["pr"], sb["tr"]
            _pz, _tz = sb["pz"], sb["tz"]
            # UI-26: Label-Detailgrad aus dem Bildschirm-Nachbarabstand. Selektierte
            # oder hervorgehobene Fixtures bekommen IMMER das volle Label (der Nutzer
            # will genau die sehen), unabhaengig von der Dichte.
            _lod = _lod_for_screen_gap(self._nn_gap.get(fixture.fid, 1e9) * self.zoom)
            _teil = fixture.fid in self._teil_fids
            if (fixture.fid in self._selected_fids or _teil
                    or fixture.fid in self._highlight_fids):
                _lod = 0
            FixtureRenderer.draw(
                painter, _render_type, x, y,
                self._fixture_size, color, intensity, label,
                selected=(fixture.fid in self._selected_fids or _teil),
                pan=pan, tilt=tilt,
                effects=effects, anim_phase=anim_phase,
                blink_off=not blink_on,
                highlighted=(fixture.fid in self._highlight_fids),
                zoom=self.zoom,
                pan_range_deg=_pr, tilt_range_deg=_tr,
                pan_zero_dmx=_pz, tilt_zero_dmx=_tz,
                lod=_lod, ring_segments=_ring,
            )
            # Info-Box für genau ein selektiertes Fixture vorbereiten
            if fixture.fid in self._selected_fids and len(self._selected_fids) == 1:
                # Render-Typ mitgeben: die Info-Box muss dieselbe Quelle nutzen
                # wie das Glyph, sonst zeigt der Strahl eine Richtung an, ueber
                # die die Box schweigt (A3D-21).
                info_box_data = (fixture, color, intensity, pan, tilt, effects,
                                 x, y, _render_type)

        # VIZ-70: Pulsring/Blinken aendern das Bild ohne neue Werte -> der
        # Takt muss weiter zeichnen. Ein Teil-Repaint sieht nicht alle
        # sichtbaren Geraete; dort nur einschalten, nie ausschalten.
        if _voll:
            self._animiert = animiert
        elif animiert:
            self._animiert = True

        # Info-Box über allem zeichnen
        if info_box_data:
            self._draw_info_box(painter, *info_box_data)

        # Rubber-Band-Auswahlrahmen (Phase 7b)
        if self._band_rect is not None:
            painter.setBrush(QBrush(QColor(80, 160, 255, 40)))
            band_pen = QPen(QColor(120, 180, 255), 1, Qt.PenStyle.DashLine)
            painter.setPen(band_pen)
            painter.drawRect(self._band_rect)

        painter.end()

    # ── Maus-Events ───────────────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus()  # Tastaturfokus holen (Esc = Auswahl leeren)
            pos = self._to_world(event.position())
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            hit = self._fixture_at(pos)

            if hit is not None:
                x, y = self._positions[hit]
                if shift or self._multi_select_mode:
                    # Toggle ohne Drag (Shift ODER Touch-Mehrfachauswahl-Modus)
                    if hit in self._teil_fids and hit not in self._selected_fids:
                        # FM-51 C (Review): Das Geraet ist nur ueber Weiss-Segmente
                        # gewaehlt und traegt den Ring der Teil-Markierung. Umschalten
                        # heisst hier ABWAEHLEN (seine Segment-Zellen raus) — nicht
                        # hinzufuegen, sonst wuerde aus dem Segment das ganze Geraet.
                        self._teil_auswahl_entfernen(hit)
                        self.fixture_clicked.emit(hit)
                        self.update()
                        return
                    if hit in self._selected_fids:
                        self._selected_fids.remove(hit)
                    else:
                        self._selected_fids.append(hit)
                    self._emit_selection()
                    self.fixture_clicked.emit(hit)
                    self.update()
                    return
                elif hit in self._selected_fids and len(self._selected_fids) > 1:
                    # Multi-Drag starten (Auswahl unveraendert)
                    self._multi_mouse_start = QPointF(pos)
                    self._multi_moved = False
                    self._multi_drag_start = {
                        fid: self._positions[fid]
                        for fid in self._selected_fids
                        if fid in self._positions
                    }
                else:
                    # Einzel-Select + Einzel-Drag
                    self._selected_fids = [hit]
                    self._drag_fid = hit
                    self._drag_offset = QPointF(pos.x() - x, pos.y() - y)
                    self._drag_press = QPointF(pos)
                    self._drag_moved = False
                    self._emit_selection()
                self.fixture_clicked.emit(hit)
                self.update()
                return

            # Klick ins Leere → Rubber-Band starten
            # (im Mehrfachauswahl-Modus NICHT leeren, damit man additiv sammeln kann)
            if not shift and not self._multi_select_mode:
                self._selected_fids = []
                self._emit_selection()
            self._band_origin = QPointF(pos)
            self._band_rect = QRectF(pos, pos)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = self._to_world(event.position())
        if self._drag_fid is not None:
            if (abs(pos.x() - self._drag_press.x())
                    + abs(pos.y() - self._drag_press.y())) > 3:
                self._drag_moved = True
            self._positions[self._drag_fid] = (
                pos.x() - self._drag_offset.x(),
                pos.y() - self._drag_offset.y()
            )
            self.update()
        elif self._multi_drag_start is not None:
            dx = pos.x() - self._multi_mouse_start.x()
            dy = pos.y() - self._multi_mouse_start.y()
            if abs(dx) + abs(dy) > 3:
                self._multi_moved = True
            for fid, (sx, sy) in self._multi_drag_start.items():
                self._positions[fid] = (sx + dx, sy + dy)
            self.update()
        elif self._band_origin is not None:
            self._band_rect = QRectF(self._band_origin, pos).normalized()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._drag_fid is not None:
            # Einzel-Drag: nur bei echter Bewegung snappen + persistieren
            # (ein reiner Klick darf das Fixture nicht versetzen / dirty machen).
            if self._drag_moved and self._drag_fid in self._positions:
                x, y = self._positions[self._drag_fid]
                x, y = self._snap(x, y)
                self._positions[self._drag_fid] = (x, y)
                try:
                    self._state.live_view_positions[self._drag_fid] = (float(x), float(y))
                except Exception:
                    pass
                self._notify_layout_changed()
            self._drag_fid = None
            self._drag_moved = False
        elif self._multi_drag_start is not None:
            # Multi-Drag: nur bei echter Bewegung snappen + persistieren
            if self._multi_moved:
                for fid in self._multi_drag_start:
                    if fid in self._positions:
                        x, y = self._snap(*self._positions[fid])
                        self._positions[fid] = (x, y)
                        try:
                            self._state.live_view_positions[fid] = (float(x), float(y))
                        except Exception:
                            pass
                self._notify_layout_changed()
            self._multi_drag_start = None
            self._multi_mouse_start = None
            self._multi_moved = False
            self.update()
        elif self._band_origin is not None:
            # Rubber-Band abschliessen: Fixtures in Rechteck auswaehlen
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self._select_in_rect(self._band_rect,
                                 additive=(shift or self._multi_select_mode))
            self._band_origin = None
            self._band_rect = None
            self.update()

    # ── Tastatur / Mausrad / Kontextmenue ─────────────────────────────────────

    def keyPressEvent(self, event):
        """Esc leert die Auswahl (und das Gruppen-Highlight)."""
        if event.key() == Qt.Key.Key_Escape and (self._selected_fids
                                                  or self._highlight_fids):
            self._selected_fids = []
            self._highlight_fids = set()
            self._emit_selection()
            self.update()
            event.accept()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        """Strg+Mausrad zoomt (über die LiveView, die Slider/Persistenz pflegt);
        ohne Strg läuft das Ereignis an die ScrollArea (normales Scrollen)."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            step = 10 if event.angleDelta().y() > 0 else -10
            new_pct = int(max(25, min(400, round(self.zoom * 100) + step)))
            self.zoom_requested.emit(new_pct)
            event.accept()
        else:
            event.ignore()

    def contextMenuEvent(self, event):
        """Rechtsklick: trifft er ein (noch nicht ausgewähltes) Fixture, wird es
        selektiert; danach baut die LiveView das Menü (Gruppe / Auswahl leeren)."""
        pos = self._to_world(QPointF(event.pos()))
        hit = self._fixture_at(pos)
        if hit is not None and hit not in self._selected_fids:
            self._selected_fids = [hit]
            self._emit_selection()
            self.update()
        self.context_menu_requested.emit(
            hit if hit is not None else -1, event.globalPos())


# ── Minimap / Navigator ───────────────────────────────────────────────────────

class Minimap(QWidget):
    """Schwebende Minimap unten rechts im Viewport — zeigt Welt + Viewport-Ausschnitt."""

    def __init__(self, scroll: QScrollArea, canvas: "StageCanvas", parent=None):
        super().__init__(parent)
        self._scroll = scroll
        self._canvas = canvas
        self.setFixedSize(170, 120)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(
            "background: rgba(10, 12, 22, 210); border: 1px solid #334; border-radius: 5px;"
        )
        # VIZ-70: nur neu zeichnen, wenn sich Inhalt (Positionen, Ausschnitt,
        # Welt/Zoom) aendert — die halbtransparente Minimap liegt UEBER der
        # Canvas, jedes Neuzeichnen zieht dort ein Teil-Repaint der Canvas nach.
        self._last_sig: tuple | None = None
        self._repaint_timer = QTimer(self)
        self._repaint_timer.timeout.connect(self._on_repaint_tick)
        self._repaint_timer.start(200)

    def _on_repaint_tick(self) -> None:
        try:
            if not self.isVisible():
                return
            win = self.window()
            if win is not None and win.isMinimized():
                return
            c = self._canvas
            vp = self._scroll.viewport()
            sig = (tuple(c._positions.items()), c.world_w, c.world_h, c.zoom,
                   self._scroll.horizontalScrollBar().value(),
                   self._scroll.verticalScrollBar().value(),
                   vp.width(), vp.height(), self.width(), self.height())
        except (RuntimeError, AttributeError):
            return
        if sig == self._last_sig:
            return
        self._last_sig = sig
        self.update()

    def set_active(self, on: bool) -> None:
        """Startet/stoppt das Repaint-Timer der Minimap (Pause im Hintergrund)."""
        try:
            if on:
                self._last_sig = None
                if not self._repaint_timer.isActive():
                    self._repaint_timer.start(200)
            else:
                self._repaint_timer.stop()
        except (RuntimeError, AttributeError):
            pass

    def _scale(self) -> float:
        """Welt→Minimap-Faktor (mit 6 px Rand)."""
        margin = 6
        sx = (self.width() - margin * 2) / max(1, self._canvas.world_w)
        sy = (self.height() - margin * 2) / max(1, self._canvas.world_h)
        return min(sx, sy)

    def _margin_xy(self, scale: float) -> tuple[float, float]:
        """Gibt (mx, my) zurueck, damit die Welt zentriert auf der Minimap liegt."""
        map_w = self._canvas.world_w * scale
        map_h = self._canvas.world_h * scale
        mx = (self.width() - map_w) / 2
        my = (self.height() - map_h) / 2
        return mx, my

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Hintergrund
        painter.fillRect(self.rect(), QColor(10, 12, 22, 210))
        painter.setPen(QPen(QColor("#334"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 5, 5)

        scale = self._scale()
        mx, my = self._margin_xy(scale)
        canvas = self._canvas
        zoom = max(0.001, canvas.zoom)

        # Welt-Rechteck
        world_rect = QRectF(mx, my, canvas.world_w * scale, canvas.world_h * scale)
        painter.setPen(QPen(QColor("#445"), 1))
        painter.setBrush(QBrush(QColor(20, 22, 35, 180)))
        painter.drawRect(world_rect)

        # Fixture-Punkte (Welt-Koordinaten → Minimap-Koordinaten)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(180, 200, 255, 200)))
        for (fx, fy) in canvas._positions.values():
            px = mx + fx * scale
            py = my + fy * scale
            painter.drawEllipse(QPointF(px, py), 2.0, 2.0)

        # Viewport-Rechteck (sichtbarer Ausschnitt)
        hbar = self._scroll.horizontalScrollBar()
        vbar = self._scroll.verticalScrollBar()
        vp = self._scroll.viewport()
        vp_world_x = hbar.value() / zoom
        vp_world_y = vbar.value() / zoom
        vp_world_w = vp.width() / zoom
        vp_world_h = vp.height() / zoom
        vp_rect = QRectF(
            mx + vp_world_x * scale,
            my + vp_world_y * scale,
            vp_world_w * scale,
            vp_world_h * scale,
        )
        painter.setPen(QPen(QColor(255, 220, 60, 200), 1.5))
        painter.setBrush(QBrush(QColor(255, 220, 60, 18)))
        painter.drawRect(vp_rect)

        painter.end()

    def _navigate_to(self, mx_widget: float, my_widget: float) -> None:
        """Scrollt die ScrollArea so, dass Minimap-Klickpunkt zentriert wird."""
        scale = self._scale()
        mmx, mmy = self._margin_xy(scale)
        canvas = self._canvas
        zoom = max(0.001, canvas.zoom)
        # Welt-Koordinate des Klick-Punkts
        world_x = (mx_widget - mmx) / scale
        world_y = (my_widget - mmy) / scale
        vp = self._scroll.viewport()
        hbar = self._scroll.horizontalScrollBar()
        vbar = self._scroll.verticalScrollBar()
        hbar.setValue(int(world_x * zoom - vp.width() / 2))
        vbar.setValue(int(world_y * zoom - vp.height() / 2))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._navigate_to(event.position().x(), event.position().y())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._navigate_to(event.position().x(), event.position().y())


# ── Live View ─────────────────────────────────────────────────────────────────

class LiveView(QWidget):
    """Komplette Live-View: Geraete-Liste | 2D-Top-Down Canvas | Editor-Panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = get_state()
        self._setup_ui()
        self._refresh_fixture_list()
        self._refresh_group_list()

        # Sync-Subscription fuer Fixture-Liste + Gruppen-Liste
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            sync.subscribe(SyncEvent.PATCH_CHANGED, lambda *_: self._on_patch_changed())
            sync.subscribe(SyncEvent.REFRESH_ALL, lambda *_: self._on_patch_changed())
            # Gruppe anderswo erstellt/geaendert (Gruppen-Editor, …) -> Liste auffrischen.
            sync.subscribe(SyncEvent.GROUP_CHANGED, lambda *_: self._refresh_group_list())
            # Globale Programmer-Auswahl (anderswo gesetzt) in der Live View
            # spiegeln (goldener Ring + Listen-Markierung). cb(event, data).
            sync.subscribe(SyncEvent.SELECTION_CHANGED,
                           lambda *a: self._on_global_selection_changed(
                               a[1] if len(a) > 1 else None))
            # P4: Nach Show-Load die Steuerelemente (Zoom/Grid/Snap/Welt) an den
            # wiederhergestellten Canvas-Zustand angleichen; QOL-05: danach die
            # 2D-Ansicht auf die Fixtures einpassen (kompakte, aus 3D migrierte Rigs
            # lagen sonst als ueberlappender Klumpen im Weltraum).
            sync.subscribe(SyncEvent.SHOW_LOADED,
                           lambda *_: self._on_show_loaded_2d())
        except Exception as e:
            print(f"[live_view] sync (fixture list) subscribe error: {e}")

        # UI-21: Gerätezähler + Auswahl-Label gleich beim Bau füllen (Initial-Pull),
        # sonst zeigt die Kopfzeile "0 Geräte im Patch" bis zum ersten 500ms-Tick des
        # _info_timer — auch wenn beim Bau schon gepatcht ist (Bug-Klasse UI-05/UI-09).
        self._refresh_info()

    def _on_patch_changed(self):
        """Wird bei PATCH_CHANGED und REFRESH_ALL aufgerufen."""
        # Hinweis: live_view_positions werden hier BEWUSST nicht geprunt — das
        # Event feuert auch beim Laden einer Show (vor/waehrend dem Wiederher-
        # stellen), ein Prune wuerde gerade geladene Positionen loeschen. Das
        # Aufraeumen verwaister Eintraege beim echten Unpatch macht die
        # VisualizerBridge (_on_state, dort ist `stale` beim Laden leer).
        self._refresh_fixture_list()
        self._refresh_group_list()

    def _set_view_3d(self, on: bool):
        """Umschalten zwischen 2D-Top-Down-Canvas und eingebetteter 3D-Ansicht.

        Die eingebettete 3D-Ansicht dient der Live-Vorschau und dem Verschieben
        von Strahlern; das Bauen der Buehne bleibt dem separaten 3D-Editor-
        Fenster vorbehalten. Die 3D-View wird beim ersten Umschalten lazy erzeugt.
        """
        # VIZ-POPOUT: ist die 3D-Ansicht bereits in ein eigenes Fenster
        # ausgeklinkt, KEIN zweites eingebettetes GL-Fenster oeffnen (GPU-
        # Invariante: nur EINE WebGL-Szene gleichzeitig). Stattdessen in 2D
        # bleiben und das Pop-out nach vorne holen.
        if on and self._viz_popout is not None:
            self._view_stack.setCurrentWidget(self._page2d)
            self._btn_view2d.setChecked(True)
            self._btn_view3d.setChecked(False)
            try:
                self._viz_popout.raise_()
                self._viz_popout.activateWindow()
            except Exception:
                pass
            return
        self._btn_view2d.setChecked(not on)
        self._btn_view3d.setChecked(on)
        if on:
            if self._viz3d is None:
                try:
                    from src.ui.visualizer.visualizer_view import Visualizer3DView
                    # show_popout_button=True: nur die eingebettete View bietet das
                    # Ausklinken an (das Pop-out-Fenster selbst braucht es nicht).
                    self._viz3d = Visualizer3DView(self, show_popout_button=True)
                    self._viz3d.popOutRequested.connect(self._pop_out_3d)
                    self._view_stack.addWidget(self._viz3d)   # index 1
                except Exception as e:
                    print(f"[live_view] 3D-Ansicht nicht verfügbar: {e}")
                    self._set_view_3d(False)
                    return
            self._view_stack.setCurrentWidget(self._viz3d)
            try:
                self._minimap.hide()
            except Exception:
                pass
            try:
                self._viz3d.on_shown()
            except Exception:
                pass
        else:
            if self._viz3d is not None:
                try:
                    self._viz3d.on_hidden()
                except Exception:
                    pass
            self._view_stack.setCurrentWidget(self._page2d)
            try:
                self._minimap.show()
            except Exception:
                pass
            # 2D-Canvas neu aus dem State laden -> spiegelt im 3D vorgenommene
            # Verschiebungen (Live View ist die Quelle der Top-Down-Positionen).
            try:
                self._canvas._reload_positions_safe()
            except Exception:
                pass

    # ── VIZ-POPOUT: 3D-Ansicht ausklinken / andocken ────────────────────────
    def _build_popout_banner(self) -> QFrame:
        """Schmaler Hinweis-Balken oben in der 2D-Seite, sichtbar nur solange die
        3D-Ansicht ausgeklinkt ist. Bietet den sichtbaren Rueckhol-Weg (zweiter
        Weg: Pop-out-Fenster schliessen)."""
        bar = QFrame()
        bar.setStyleSheet(
            "QFrame { background:#14263a; border-bottom:1px solid #2a4a6a; }"
            "QLabel { color:#9acbff; font-size:12px; }"
            "QPushButton { background:#1f6feb; color:#fff; border:none;"
            " border-radius:4px; padding:5px 12px; font-size:12px; }"
            "QPushButton:hover { background:#3b82f6; }"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.addWidget(QLabel("🧊 3D läuft im separaten Fenster (Zweitmonitor)."))
        lay.addStretch()
        btn = QPushButton("⇲ Zurückholen")
        btn.setToolTip("3D-Fenster schließen und wieder hier einbetten")
        btn.clicked.connect(weak_slot(self._redock_popout))
        lay.addWidget(btn)
        return bar

    def _pop_out_3d(self):
        """Eingebettete 3D-Ansicht in ein eigenes Fenster loesen (Zweitmonitor).
        Bereits offen -> nur nach vorne holen. Sonst: ZUERST das Pop-out-Fenster
        bauen (das kann bei WebEngine/GL-Init fehlschlagen) und ERST bei Erfolg
        die eingebettete View auf 2D zuruecknehmen (GPU-Invariante: nur EINE
        GL-Szene) + Banner zeigen. Scheitert der Bau, bleibt die eingebettete
        3D-Ansicht stehen und der Nutzer bekommt einen sichtbaren Hinweis statt
        still in einer nackten 2D-Ansicht zu landen (Review-Fix)."""
        if self._viz_popout is not None:
            try:
                self._viz_popout.raise_()
                self._viz_popout.activateWindow()
            except Exception:
                pass
            return
        try:
            from src.ui.visualizer.visualizer_view import VisualizerPopoutWindow
            # Als Sekundaerfenster des Hauptfensters: frei auf einen zweiten
            # Monitor ziehbar, aber an die App-Lebenszeit gebunden (blockiert den
            # App-Exit nicht, wird beim Beenden mit abgeraeumt). Noch NICHT gezeigt
            # -> Page-Visibility 'hidden' -> rAF gedrosselt, rendert noch nicht.
            win = VisualizerPopoutWindow(self.window())
        except Exception as e:
            print(f"[live_view] Pop-out-Fenster-Fehler: {e}")
            try:
                self._set_status("3D-Fenster konnte nicht geöffnet werden — Ansicht bleibt eingebettet.")
            except Exception:
                pass
            return
        # Fenster steht -> jetzt die eingebettete 3D-View auf 2D zuruecknehmen
        # (on_hidden: Target inaktiv + dispose) und das Pop-out zeigen; so rendert
        # nur die Pop-out-Szene.
        self._set_view_3d(False)
        self._viz_popout = win
        try:
            win.closed.connect(weak_slot(self._on_popout_closed))
            win.show()
            win.raise_()
            win.activateWindow()
        except Exception as e:
            print(f"[live_view] Pop-out-Show-Fehler: {e}")
        try:
            self._popout_banner.show()
        except Exception:
            pass

    def _on_popout_closed(self):
        """Dock-back-Einstieg: Pop-out geschlossen (X-Knopf, Banner-Button, App-
        Ende). Banner weg + Referenz loesen SOFORT; das eigentliche Wieder-
        Andocken wird per singleShot AUS dem synchronen closeEvent-Pfad des
        Pop-outs geloest, damit das Fenster sicher versteckt/compositor-
        suspendiert ist, bevor die eingebettete Szene wieder rendert (Review-Fix
        Reentrancy)."""
        self._viz_popout = None
        try:
            self._popout_banner.hide()
        except Exception:
            pass
        QTimer.singleShot(0, self._redock_after_popout)

    def _redock_after_popout(self):
        """Deferred Dock-back: eingebettete 3D-Ansicht wieder einblenden — aber
        nur AKTIV schalten, wenn der Live-View-Tab ueberhaupt sichtbar ist. Sonst
        wuerde on_shown das Service-Target trotz verborgenem Tab aktivieren
        (Umgehung des Sichtbarkeits-Gates, Review-Fix)."""
        if self._viz_popout is not None:
            return   # zwischenzeitlich erneut ausgeklinkt
        self._set_view_3d(True)
        # Sichtbarkeits-Gate idempotent nachziehen: verborgener Tab -> das gerade
        # aktivierte 3D-Target wieder deaktivieren.
        try:
            self._set_views_active(self.isVisible())
        except Exception:
            pass

    def _redock_popout(self):
        """Banner-Button '⇲ Zurückholen': schliesst das Pop-out — der closeEvent
        laeuft ueber _on_popout_closed (gemeinsamer Dock-back-Pfad)."""
        if self._viz_popout is not None:
            try:
                self._viz_popout.close()
            except Exception:
                pass

    def _setup_ui(self):
        # Zeitpunkt, bis zu dem eine sticky-Statusmeldung im Footer nicht vom
        # Info-Timer ueberschrieben wird (siehe _set_status / _update_selection_label).
        self._sticky_until: float = 0.0
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(8, 4, 8, 4)
        title = QLabel("LIVE")
        title.setStyleSheet("color:#FFD700; font-weight:bold; font-size:13px;")
        header.addWidget(title)

        self._lbl_info = QLabel("0 Geräte im Patch")
        self._lbl_info.setStyleSheet("color:#888; padding-left:20px;")
        header.addWidget(self._lbl_info)
        header.addStretch()

        legend = QLabel("PAR  Bar  Moving-Head  Spider  Scanner  Laser  Strobe  Dimmer  Fog")
        legend.setStyleSheet("color:#666; font-size:10px;")
        header.addWidget(legend)
        root.addLayout(header)

        # ── Aktionsleiste (touch-tauglich, immer sichtbar) ────────────────────
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 2, 8, 4)
        toolbar.setSpacing(6)
        _tb_style = (
            "QPushButton { background:#1a2a3a; color:#9acbff; border:1px solid #2a4a6a;"
            " border-radius:4px; padding:7px 12px; font-size:12px; }"
            " QPushButton:hover { background:#223344; color:#bfe0ff; }"
            " QPushButton:checked { background:#1f6feb; color:#fff; border-color:#1f6feb; }"
        )
        self._btn_multi = QPushButton("☑ Mehrfachauswahl")
        self._btn_multi.setCheckable(True)
        self._btn_multi.setMinimumHeight(34)
        self._btn_multi.setStyleSheet(_tb_style)
        self._btn_multi.setToolTip(
            "An: Antippen sammelt mehrere Geräte (für Touch, kein Shift nötig).\n"
            "Aus: Antippen wählt einzeln. Auf leerer Fläche ziehen = Auswahlrahmen."
        )
        self._btn_multi.toggled.connect(self._on_multi_toggle)
        toolbar.addWidget(self._btn_multi)

        self._btn_make_group = QPushButton("＋ Gruppe aus Auswahl")
        self._btn_make_group.setMinimumHeight(34)
        self._btn_make_group.setStyleSheet(_tb_style)
        self._btn_make_group.clicked.connect(self._on_create_group_clicked)
        toolbar.addWidget(self._btn_make_group)

        self._btn_clear_sel = QPushButton("Auswahl leeren")
        self._btn_clear_sel.setMinimumHeight(34)
        self._btn_clear_sel.setStyleSheet(_tb_style)
        self._btn_clear_sel.clicked.connect(self._on_clear_selection)
        toolbar.addWidget(self._btn_clear_sel)
        toolbar.addStretch()

        # ── 2D/3D-Umschalter (eingebettete 3D-Ansicht ohne Extra-Fenster) ─────
        self._btn_view2d = QPushButton("🗺 2D")
        self._btn_view3d = QPushButton("🧊 3D")
        for b in (self._btn_view2d, self._btn_view3d):
            b.setCheckable(True)
            b.setMinimumHeight(34)
            b.setStyleSheet(_tb_style)
        self._btn_view2d.setChecked(True)
        self._btn_view2d.setToolTip("2D Top-Down-Arbeitsfläche (Strahler platzieren)")
        self._btn_view3d.setToolTip(
            "Eingebettete 3D-Ansicht (Live-Vorschau). Zum Bauen der Bühne das\n"
            "separate 3D-Editor-Fenster nutzen (Menü Visualizer)."
        )
        self._view_mode_group = QButtonGroup(self)
        self._view_mode_group.setExclusive(True)
        self._view_mode_group.addButton(self._btn_view2d, 0)
        self._view_mode_group.addButton(self._btn_view3d, 1)
        self._btn_view2d.clicked.connect(weak_slot(self._set_view_3d, False))
        self._btn_view3d.clicked.connect(weak_slot(self._set_view_3d, True))
        toolbar.addWidget(self._btn_view2d)
        toolbar.addWidget(self._btn_view3d)
        root.addLayout(toolbar)

        # ── Mittlere Zeile: Links | Canvas | Rechts ───────────────────────────
        mid = QHBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(0)

        # -- Linkes Panel: Tab-Widget mit "Fixtures" und "Gruppen" --
        self._left_panel = QWidget()
        self._left_panel.setFixedWidth(190)
        self._left_panel.setStyleSheet("background:#10121a; border-right:1px solid #222;")
        left_layout = QVBoxLayout(self._left_panel)
        left_layout.setContentsMargins(4, 6, 4, 6)
        left_layout.setSpacing(4)

        # QTabWidget für Fixtures / Gruppen
        self._left_tabs = QTabWidget()
        self._left_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #333;
                background: #10121a;
            }
            QTabBar::tab {
                background: #1a1c28;
                color: #aaa;
                padding: 4px 8px;
                font-size: 11px;
                border: 1px solid #333;
                border-bottom: none;
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
            }
            QTabBar::tab:selected {
                background: #10121a;
                color: #FFD700;
                border-bottom: 1px solid #10121a;
            }
            QTabBar::tab:hover { background: #252838; }
        """)

        # ── Reiter 1: Fixtures ────────────────────────────────────────────────
        tab_fixtures = QWidget()
        tab_fixtures.setStyleSheet("background:#10121a;")
        tf_layout = QVBoxLayout(tab_fixtures)
        tf_layout.setContentsMargins(2, 4, 2, 4)
        tf_layout.setSpacing(4)

        from src.ui.views.fixture_group_view import FixtureTreeWithDrag
        self._fixture_search = QLineEdit()
        self._fixture_search.setPlaceholderText("Suchen…")
        self._fixture_search.setStyleSheet(
            "QLineEdit{background:#12141c;color:#ccc;border:1px solid #333;"
            "border-radius:3px;padding:3px 6px;font-size:11px;}")
        self._fixture_search.textChanged.connect(self._apply_fixture_filter)
        tf_layout.addWidget(self._fixture_search)
        self._fixture_list = FixtureTreeWithDrag()
        # P2: Mehrfachauswahl (Klick / Strg+Klick / Shift+Klick) — Auswahl
        # spiegelt sich als goldener Ring auf der Canvas und in der globalen
        # Programmer-Auswahl (Gruppenbildung ueber die Toolbar).
        from PySide6.QtWidgets import QAbstractItemView
        self._fixture_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self._fixture_list.itemSelectionChanged.connect(
            self._on_tree_selection_changed)
        self._tree_sync_guard = False
        tf_layout.addWidget(self._fixture_list)
        _hint_fx = QLabel("Tipp: Geräte auf die Fläche ziehen. Auswählen & gruppieren\nüber die Leiste oben.")
        _hint_fx.setStyleSheet("color:#667; font-size:9px; padding:2px 4px;")
        _hint_fx.setWordWrap(True)
        tf_layout.addWidget(_hint_fx)

        self._left_tabs.addTab(tab_fixtures, "Fixtures")

        # ── Reiter 2: Gruppen ─────────────────────────────────────────────────
        tab_groups = QWidget()
        tab_groups.setStyleSheet("background:#10121a;")
        tg_layout = QVBoxLayout(tab_groups)
        tg_layout.setContentsMargins(2, 4, 2, 4)
        tg_layout.setSpacing(4)

        self._group_list = QListWidget()
        self._group_list.setStyleSheet("""
            QListWidget {
                background: #12141c;
                color: #cccccc;
                border: 1px solid #333;
                border-radius: 4px;
                font-size: 11px;
            }
            QListWidget::item { padding: 3px 6px; }
            QListWidget::item:hover { background: #2a2a3a; }
            QListWidget::item:selected { background: #1a4a2a; color: #88ffaa; }
        """)
        self._group_list.itemClicked.connect(self._on_group_selected)
        tg_layout.addWidget(self._group_list)

        # Buttons unter der Gruppenliste
        grp_btn_row = QHBoxLayout()
        grp_btn_row.setSpacing(4)

        btn_refresh_groups = QPushButton("Aktualisieren")
        btn_refresh_groups.setStyleSheet("""
            QPushButton {
                background: #1a1c28;
                color: #aaa;
                border: 1px solid #333;
                border-radius: 3px;
                padding: 3px 5px;
                font-size: 10px;
            }
            QPushButton:hover { background: #252838; color: #ccc; }
        """)
        btn_refresh_groups.clicked.connect(self._refresh_group_list)
        grp_btn_row.addWidget(btn_refresh_groups)

        btn_delete_group = QPushButton("Gruppe löschen")
        btn_delete_group.setStyleSheet("""
            QPushButton {
                background: #2a1a1a;
                color: #ff8888;
                border: 1px solid #5a2a2a;
                border-radius: 3px;
                padding: 3px 5px;
                font-size: 10px;
            }
            QPushButton:hover { background: #3a2020; color: #ffaaaa; }
            QPushButton:pressed { background: #1a0f0f; }
        """)
        btn_delete_group.clicked.connect(self._on_delete_group_clicked)
        grp_btn_row.addWidget(btn_delete_group)

        tg_layout.addLayout(grp_btn_row)

        self._left_tabs.addTab(tab_groups, "Gruppen")

        left_layout.addWidget(self._left_tabs)
        mid.addWidget(self._left_panel)

        # -- Mitte: ScrollArea + Canvas --
        self._canvas = StageCanvas()
        self._canvas.fixture_clicked.connect(self._on_fixture_clicked)
        self._canvas.selection_changed.connect(self._on_canvas_selection_changed)
        self._canvas.context_menu_requested.connect(self._on_canvas_context_menu)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setWidget(self._canvas)
        self._scroll.setStyleSheet(
            "QScrollArea { border: none; background: #0d1117; }"
        )

        # VIZ-POPOUT: 2D-Seite = Banner (verborgen) ueber dem Canvas. Der Banner
        # erscheint nur, waehrend die 3D-Ansicht in ein eigenes Fenster ausgeklinkt
        # ist, und bietet einen sichtbaren Weg zurueck (der zweite Weg: Pop-out-
        # Fenster schliessen). So bleibt der 2D-Ueberblick auf Monitor 1, waehrend
        # die 3D-Schoenheit auf Monitor 2 laeuft.
        self._page2d = QWidget()
        _p2 = QVBoxLayout(self._page2d)
        _p2.setContentsMargins(0, 0, 0, 0)
        _p2.setSpacing(0)
        self._popout_banner = self._build_popout_banner()
        self._popout_banner.hide()
        _p2.addWidget(self._popout_banner)
        _p2.addWidget(self._scroll, 1)

        # QStackedWidget: Seite 0 = 2D-Canvas(+Banner), Seite 1 = eingebettete
        # 3D-Ansicht (lazy erzeugt beim ersten Umschalten auf 3D).
        self._view_stack = QStackedWidget()
        self._view_stack.addWidget(self._page2d)        # index 0
        self._viz3d = None                              # type: ignore[assignment]
        self._viz_popout = None                         # aktives Pop-out-Fenster (VIZ-POPOUT)
        mid.addWidget(self._view_stack, 1)

        # Minimap als schwebende Overlay-Widget im Viewport
        self._minimap = Minimap(self._scroll, self._canvas, self._scroll.viewport())
        self._minimap.raise_()
        QTimer.singleShot(0, self._position_minimap)

        # -- Rechtes Panel: Editor --
        self._right_panel = QWidget()
        self._right_panel.setFixedWidth(210)
        self._right_panel.setStyleSheet("background:#10121a; border-left:1px solid #222;")
        right_layout = QVBoxLayout(self._right_panel)
        right_layout.setContentsMargins(6, 8, 6, 8)
        right_layout.setSpacing(6)

        gb = QGroupBox("Welt / Ansicht")
        gb.setStyleSheet("""
            QGroupBox {
                color: #aaa;
                font-size: 11px;
                border: 1px solid #333;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 6px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; }
        """)
        form = QFormLayout(gb)
        form.setContentsMargins(6, 4, 6, 6)
        form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        lv_prefs = _load_prefs().get("live_view", {})

        # World-Breite
        self._sb_world_w = QSpinBox()
        self._sb_world_w.setRange(400, 8000)
        self._sb_world_w.setSingleStep(50)
        self._sb_world_w.setValue(int(lv_prefs.get("world_w", 1200)))
        self._sb_world_w.setStyleSheet(self._spinbox_style())
        form.addRow("Breite (px):", self._sb_world_w)

        # World-Hoehe
        self._sb_world_h = QSpinBox()
        self._sb_world_h.setRange(400, 8000)
        self._sb_world_h.setSingleStep(50)
        self._sb_world_h.setValue(int(lv_prefs.get("world_h", 800)))
        self._sb_world_h.setStyleSheet(self._spinbox_style())
        form.addRow("Höhe (px):", self._sb_world_h)

        # Raster-Groesse
        self._sb_grid = QSpinBox()
        self._sb_grid.setRange(5, 200)
        self._sb_grid.setSingleStep(5)
        self._sb_grid.setValue(int(lv_prefs.get("grid_size", 50)))
        self._sb_grid.setStyleSheet(self._spinbox_style())
        form.addRow("Raster (px):", self._sb_grid)

        # Snap
        self._cb_snap = QCheckBox()
        self._cb_snap.setChecked(bool(lv_prefs.get("snap", True)))
        self._cb_snap.setStyleSheet("color:#ccc;")
        form.addRow("Snap:", self._cb_snap)

        # Raster sichtbar
        self._cb_grid_vis = QCheckBox()
        self._cb_grid_vis.setChecked(bool(lv_prefs.get("grid_visible", True)))
        self._cb_grid_vis.setStyleSheet("color:#ccc;")
        form.addRow("Raster zeigen:", self._cb_grid_vis)

        # ── Zoom-Overlay (I2.9): schwebend unten rechts ueber der Minimap, gross/touch-tauglich ──
        zoom_init = max(0.25, min(4.0, float(lv_prefs.get("zoom", 1.0))))
        self._zoom_overlay = QWidget(self._scroll.viewport())
        self._zoom_overlay.setStyleSheet(
            "background: rgba(16,18,26,215); border:1px solid #333; border-radius:6px;")
        zo = QHBoxLayout(self._zoom_overlay)
        zo.setContentsMargins(8, 4, 8, 4)
        zo.setSpacing(6)

        _zlbl = QLabel("Zoom")
        _zlbl.setStyleSheet("color:#FFD700; font-size:12px; font-weight:bold;")
        zo.addWidget(_zlbl)

        self._btn_zoom_out = QPushButton("−")  # echtes Minuszeichen
        self._btn_zoom_in = QPushButton("+")
        for _b in (self._btn_zoom_out, self._btn_zoom_in):
            _b.setFixedSize(30, 30)
            _b.setStyleSheet(
                "QPushButton{background:#1a1c28;color:#ccc;border:1px solid #333;"
                "border-radius:4px;font-size:18px;} QPushButton:hover{background:#252838;color:#fff;}")
        zo.addWidget(self._btn_zoom_out)

        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setRange(25, 400)
        self._zoom_slider.setSingleStep(5)
        self._zoom_slider.setPageStep(25)
        self._zoom_slider.setFixedWidth(200)
        self._zoom_slider.blockSignals(True)
        self._zoom_slider.setValue(int(round(zoom_init * 100)))
        self._zoom_slider.blockSignals(False)
        self._zoom_slider.setStyleSheet("""
            QSlider::groove:horizontal { height:8px; background:#333; border-radius:4px; }
            QSlider::handle:horizontal { width:22px; height:22px; margin:-7px 0;
                background:#FFD700; border-radius:11px; }
            QSlider::handle:horizontal:hover { background:#ffe34d; }
            QSlider::sub-page:horizontal { background:#0978FF; border-radius:4px; }
        """)
        zo.addWidget(self._zoom_slider)
        zo.addWidget(self._btn_zoom_in)

        # QOL-05: „Einpassen" — Ansicht auf die Fixtures zoomen/zentrieren.
        self._btn_fit = QPushButton("⤢")
        self._btn_fit.setFixedSize(30, 30)
        self._btn_fit.setToolTip("Ansicht auf die Geräte einpassen")
        self._btn_fit.setStyleSheet(
            "QPushButton{background:#1a1c28;color:#ccc;border:1px solid #333;"
            "border-radius:4px;font-size:15px;} QPushButton:hover{background:#252838;color:#fff;}")
        self._btn_fit.clicked.connect(weak_slot(self._fit_view_clicked))
        zo.addWidget(self._btn_fit)

        self._lbl_zoom = QLabel(f"{int(round(zoom_init * 100))} %")
        self._lbl_zoom.setStyleSheet("color:#ccc; font-size:12px; min-width:44px;")
        self._lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        zo.addWidget(self._lbl_zoom)

        self._zoom_overlay.adjustSize()
        self._btn_zoom_out.clicked.connect(weak_slot(self._zoom_step, -10))
        self._btn_zoom_in.clicked.connect(weak_slot(self._zoom_step, +10))
        self._zoom_overlay.raise_()

        right_layout.addWidget(gb)

        # ── Gruppen-Detail-Box (Phase 7a) ─────────────────────────────────────
        _grp_detail_style = """
            QGroupBox {
                color: #88ffaa;
                font-size: 11px;
                border: 1px solid #2a5a3a;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 6px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; }
        """
        self._group_detail_box = QGroupBox("Gruppe")
        self._group_detail_box.setStyleSheet(_grp_detail_style)
        detail_layout = QVBoxLayout(self._group_detail_box)
        detail_layout.setContentsMargins(6, 4, 6, 6)
        detail_layout.setSpacing(4)

        # P3: Gruppenname ist direkt editierbar (Enter/Fokusverlust speichert).
        name_row = QHBoxLayout()
        name_row.setSpacing(4)
        self._edit_group_name = QLineEdit()
        self._edit_group_name.setPlaceholderText("Gruppenname")
        self._edit_group_name.setStyleSheet(
            "QLineEdit { background:#0e1318; color:#88ffaa; font-weight:bold;"
            " font-size:11px; border:1px solid #2a4a3a; border-radius:3px;"
            " padding:2px 4px; }"
        )
        self._edit_group_name.editingFinished.connect(self._on_group_name_edited)
        name_row.addWidget(self._edit_group_name, 1)
        self._lbl_group_count = QLabel("")
        self._lbl_group_count.setStyleSheet("color:#7d8590; font-size:10px;")
        name_row.addWidget(self._lbl_group_count)
        detail_layout.addLayout(name_row)

        self._group_members = QListWidget()
        self._group_members.setStyleSheet("""
            QListWidget {
                background: #0e1318;
                color: #cccccc;
                border: 1px solid #2a4a3a;
                border-radius: 3px;
                font-size: 10px;
            }
            QListWidget::item { padding: 2px 4px; }
            QListWidget::item:selected { background: #1a4a2a; color: #88ffaa; }
        """)
        self._group_members.setMaximumHeight(120)
        # Entf-Taste in der Mitglieder-Liste entfernt das markierte Fixture
        from PySide6.QtGui import QShortcut, QKeySequence
        _sc_del = QShortcut(QKeySequence(Qt.Key.Key_Delete), self._group_members)
        _sc_del.setContext(Qt.ShortcutContext.WidgetShortcut)
        _sc_del.activated.connect(self._on_remove_member_clicked)
        detail_layout.addWidget(self._group_members)

        btn_add_sel = QPushButton("＋ Auswahl zur Gruppe hinzufügen")
        btn_add_sel.setStyleSheet("""
            QPushButton {
                background: #14321f;
                color: #88ffaa;
                border: 1px solid #2a5a3a;
                border-radius: 3px;
                padding: 5px 6px;
                font-size: 10px;
            }
            QPushButton:hover { background: #1c4429; color: #aaffcc; }
            QPushButton:pressed { background: #0e2014; }
        """)
        btn_add_sel.setMinimumHeight(30)
        btn_add_sel.setToolTip("Fügt die aktuell im Bühnen-Layout ausgewählten Geräte dieser Gruppe hinzu.")
        btn_add_sel.clicked.connect(self._on_add_selection_to_group_clicked)
        detail_layout.addWidget(btn_add_sel)

        btn_remove_member = QPushButton("Fixture aus Gruppe entfernen")
        btn_remove_member.setStyleSheet("""
            QPushButton {
                background: #2a1a1a;
                color: #ff8888;
                border: 1px solid #5a2a2a;
                border-radius: 3px;
                padding: 3px 5px;
                font-size: 10px;
            }
            QPushButton:hover { background: #3a2020; color: #ffaaaa; }
            QPushButton:pressed { background: #1a0f0f; }
        """)
        btn_remove_member.clicked.connect(self._on_remove_member_clicked)
        detail_layout.addWidget(btn_remove_member)

        self._group_detail_box.setVisible(False)
        right_layout.addWidget(self._group_detail_box)

        right_layout.addStretch()
        mid.addWidget(self._right_panel)

        root.addLayout(mid, 1)

        # ── Footer ────────────────────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.setContentsMargins(8, 2, 8, 2)
        self._lbl_selected = QLabel("Selektion: -")
        self._lbl_selected.setStyleSheet("color:#aaa; font-size:11px;")
        footer.addWidget(self._lbl_selected)
        footer.addStretch()
        hint = QLabel("Tippen = Auswahl  ·  Rahmen ziehen = mehrere  ·  'Mehrfachauswahl' (oben) = sammeln  ·  Ziehen = verschieben  ·  Liste→Fläche = platzieren")
        hint.setStyleSheet("color:#555; font-size:10px;")
        footer.addWidget(hint)
        root.addLayout(footer)

        # ── Signals verbinden ─────────────────────────────────────────────────
        self._sb_world_w.valueChanged.connect(self._on_world_size_changed)
        self._sb_world_h.valueChanged.connect(self._on_world_size_changed)
        self._sb_grid.valueChanged.connect(self._on_grid_changed)
        self._cb_snap.toggled.connect(self._on_snap_toggled)
        self._cb_grid_vis.toggled.connect(self._on_grid_vis_toggled)
        self._zoom_slider.valueChanged.connect(self._on_zoom_changed)
        # Strg+Mausrad auf der Canvas -> Slider setzen (treibt set_zoom + Persistenz)
        self._canvas.zoom_requested.connect(self._on_zoom_requested)

        # Refresh-Timer fuer Status-Texte
        self._info_timer = QTimer(self)
        self._info_timer.timeout.connect(self._refresh_info)
        self._info_timer.start(500)

        # Interne Referenz: aktuell in der Gruppen-Detail-Box angezeigte Gruppen-ID
        self._detail_group_id: int | None = None

    # ── Hilfsmethode: SpinBox-Style ───────────────────────────────────────────

    @staticmethod
    def _spinbox_style() -> str:
        return """
            QSpinBox {
                background: #1a1c28;
                color: #ccc;
                border: 1px solid #333;
                border-radius: 3px;
                padding: 2px 4px;
            }
            QSpinBox::up-button, QSpinBox::down-button { width: 16px; }
        """

    # ── Editor-Handler ────────────────────────────────────────────────────────

    def _on_world_size_changed(self):
        w = self._sb_world_w.value()
        h = self._sb_world_h.value()
        self._canvas.set_world_size(w, h)
        self._persist_live_view_prefs()

    def _on_grid_changed(self, value: int):
        self._canvas.grid_size = value
        self._canvas.update()
        self._persist_live_view_prefs()

    def _on_snap_toggled(self, checked: bool):
        self._canvas.snap_enabled = checked
        self._persist_live_view_prefs()

    def _on_grid_vis_toggled(self, checked: bool):
        self._canvas.grid_visible = checked
        self._canvas.update()
        self._persist_live_view_prefs()

    def _zoom_step(self, delta: int):
        self._zoom_slider.setValue(self._zoom_slider.value() + delta)

    def _on_zoom_requested(self, p):
        self._zoom_slider.setValue(int(p))

    def _on_zoom_changed(self, value: int):
        self._canvas.set_zoom(value / 100.0)
        self._lbl_zoom.setText(f"{int(round(self._canvas.zoom * 100))} %")
        self._persist_live_view_prefs()   # P4: Zoom-Aenderung persistieren (Show + ui_prefs)

    def _fit_2d_to_fixtures(self, *, force: bool = False) -> None:
        """QOL-05: Auto-Fit-Zoom — die 2D-Ansicht so zoomen/zentrieren, dass die
        Fixtures die Flaeche mit etwas Rand fuellen. Positionen bleiben unveraendert
        (nur die Ansicht skaliert — treu zur 3D-Projektion). Ohne ``force`` nur, wenn
        das Rig das Sichtfeld aktuell schlecht ausfuellt (kompakter Klumpen) — eine
        bewusst gesetzte Zoom-Stufe bleibt so erhalten."""
        canvas = getattr(self, "_canvas", None)
        scroll = getattr(self, "_scroll", None)
        if canvas is None or scroll is None:
            return
        pts = list(getattr(canvas, "_positions", {}).values())
        if len(pts) < 2:
            return
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        bw = max(xs) - min(xs)
        bh = max(ys) - min(ys)
        vp = scroll.viewport().size()
        vw, vh = max(1, vp.width()), max(1, vp.height())
        if not force:
            # CDX-09: nur beim kompakten KLUMPEN eingreifen. `or` statt `and`: fuellt
            # das Rig schon EINE Achse gut aus (breite flache Reihe / hohe schmale
            # Saeule), gilt es als ausreichend gespreizt und wird NICHT geschrumpft;
            # nur ein Rig, das BEIDE Achsen schlecht ausfuellt, ist ein echter Klumpen.
            if bw * canvas.zoom >= 0.35 * vw or bh * canvas.zoom >= 0.35 * vh:
                return
        z = _compute_fit_zoom(bw, bh, vw, vh)
        self._zoom_slider.setValue(int(round(z * 100)))   # -> _on_zoom_changed: Canvas-Zoom + Label
        # Fixture-Bbox-Mitte ins Sichtfeld zentrieren
        cx = (min(xs) + max(xs)) / 2 * canvas.zoom
        cy = (min(ys) + max(ys)) / 2 * canvas.zoom
        scroll.horizontalScrollBar().setValue(int(cx - vw / 2))
        scroll.verticalScrollBar().setValue(int(cy - vh / 2))

    def _on_show_loaded_2d(self) -> None:
        """Show-Load: Steuerelemente angleichen. QOL-05: die 2D-Ansicht NUR
        auto-einpassen, wenn die Show KEINEN eigenen 2D-Zoom gespeichert hat (z. B.
        aus 3D projiziert) — ein bewusst gewaehlter Zoom bleibt so unangetastet.
        Deferred, damit Viewport + Positionen stehen. Nach dem Fit ist der Zoom
        gespeichert -> ein Reload passt nicht erneut ungefragt an."""
        self._sync_controls_from_canvas()
        meta = getattr(self._state, "live_view_meta", None) or {}
        if "zoom" not in meta:
            QTimer.singleShot(0, self._fit_2d_to_fixtures)

    def _fit_view_clicked(self, *_) -> None:
        """„Einpassen"-Button (QOL-05): Ansicht bewusst (force) auf die Geräte fitten.
        Die Zoom-Aenderung persistiert ueber ``_on_zoom_changed`` mit."""
        self._fit_2d_to_fixtures(force=True)

    def _persist_live_view_prefs(self):
        meta = {
            "world_w": self._canvas.world_w,
            "world_h": self._canvas.world_h,
            "grid_size": self._canvas.grid_size,
            "snap": self._canvas.snap_enabled,
            "grid_visible": self._canvas.grid_visible,
            "zoom": self._canvas.zoom,
        }
        # Nutzer-Default fuer NEUE Shows (ui_prefs.json) ...
        _save_prefs({"live_view": meta})
        # ... und P4: Show-spezifischer Zustand — wandert mit save_show /
        # Auto-Save in die .lshow und wird beim Laden wiederhergestellt.
        try:
            self._state.live_view_meta = dict(meta)
            self._canvas._notify_layout_changed()
        except Exception:
            pass

    def _sync_controls_from_canvas(self):
        """P4: Slider/Checkboxen an den (z. B. nach Show-Load) geaenderten
        Canvas-Zustand angleichen — ohne Echo-Persistierung."""
        try:
            widgets = [
                (self._zoom_slider, int(round(self._canvas.zoom * 100))),
                (self._sb_grid, int(self._canvas.grid_size)),
                (self._sb_world_w, int(self._canvas.world_w)),
                (self._sb_world_h, int(self._canvas.world_h)),
            ]
            for w, val in widgets:
                w.blockSignals(True)
                w.setValue(val)
                w.blockSignals(False)
            for cb, val in ((self._cb_snap, self._canvas.snap_enabled),
                            (self._cb_grid_vis, self._canvas.grid_visible)):
                cb.blockSignals(True)
                cb.setChecked(bool(val))
                cb.blockSignals(False)
            self._lbl_zoom.setText(f"{int(round(self._canvas.zoom * 100))} %")
        except (RuntimeError, AttributeError):
            pass  # View/Widgets (noch) nicht gebaut oder bereits zerstoert

    # ── Minimap positionieren ─────────────────────────────────────────────────

    def _position_minimap(self):
        """Positioniert die Minimap unten rechts im Viewport."""
        vp = self._scroll.viewport()
        mm = self._minimap
        mm.move(vp.width() - mm.width() - 10,
                vp.height() - mm.height() - 10)
        mm.raise_()
        self._position_zoom_overlay()

    def _position_zoom_overlay(self):
        """Positioniert das Zoom-Overlay unten rechts, direkt ueber der Minimap."""
        if not hasattr(self, "_zoom_overlay") or not hasattr(self, "_minimap"):
            return
        vp = self._scroll.viewport()
        zo = self._zoom_overlay
        zo.adjustSize()
        x = vp.width() - zo.width() - 10
        y = vp.height() - self._minimap.height() - zo.height() - 18
        zo.move(max(4, x), max(4, y))
        zo.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._position_minimap)

    # ── Timer pausieren, wenn die Live View nicht der sichtbare Tab ist ───────

    def showEvent(self, event):
        super().showEvent(event)
        self._set_views_active(True)
        QTimer.singleShot(0, self._position_minimap)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._set_views_active(False)

    def _set_views_active(self, on: bool):
        """Startet/stoppt Canvas-, Minimap- und Info-Timer (CPU sparen, wenn der
        Live-View-Tab nicht sichtbar ist)."""
        for obj in (getattr(self, "_canvas", None), getattr(self, "_minimap", None)):
            try:
                if obj is not None:
                    obj.set_active(on)
            except RuntimeError:
                pass
        try:
            if on:
                if not self._info_timer.isActive():
                    self._info_timer.start(500)
            else:
                self._info_timer.stop()
        except (RuntimeError, AttributeError):
            pass
        # Eingebettete 3D-Ansicht: DMX-Timer nur laufen lassen, wenn der Live-View-
        # Tab sichtbar UND die 3D-Seite aktiv ist.
        try:
            viz = getattr(self, "_viz3d", None)
            if viz is not None:
                if on and self._view_stack.currentWidget() is viz:
                    viz.on_shown()
                else:
                    viz.on_hidden()
        except (RuntimeError, AttributeError):
            pass

    # ── Fixture-Liste befuellen ───────────────────────────────────────────────

    def _refresh_fixture_list(self):
        """Befuellt den Geraete-Baum aus dem aktuellen Patch (Universe-Ordner)."""
        try:
            fixtures = self._state.get_patched_fixtures()
        except Exception:
            fixtures = []
        self._fixture_list.clear()
        by_universe: dict[int, list] = {}
        for f in fixtures:
            by_universe.setdefault(getattr(f, "universe", 0), []).append(f)
        for uni in by_universe.values():
            uni.sort(key=lambda x: getattr(x, "address", 0))
        for uni_num in sorted(by_universe.keys()):
            uni_item = QTreeWidgetItem(self._fixture_list, [f"Universe {uni_num}"])
            uni_item.setFlags(uni_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            uni_item.setExpanded(True)
            for f in by_universe[uni_num]:
                label = getattr(f, "label", None) or getattr(f, "fixture_type", "?") or "?"
                _txt = f"[{f.fid:03d}] {label}"
                child = QTreeWidgetItem(uni_item, [_txt])
                child.setToolTip(0, _txt)  # QOL-03: Vollname auch bei Kuerzung
                child.setData(0, Qt.ItemDataRole.UserRole, f.fid)
                child.setIcon(0, _mini.fixture_icon_for(f))
        self._apply_fixture_filter()

    def _apply_fixture_filter(self):
        """Blendet Kind-Items aus, deren Label nicht zum Suchtext passt;
        leere Universe-Ordner werden ausgeblendet."""
        text = (self._fixture_search.text() or "").strip().lower()
        root = self._fixture_list.invisibleRootItem()
        for i in range(root.childCount()):
            uni = root.child(i)
            visible = 0
            for j in range(uni.childCount()):
                child = uni.child(j)
                match = (text == "") or (text in child.text(0).lower())
                child.setHidden(not match)
                if match:
                    visible += 1
            uni.setHidden(visible == 0)

    # ── Gruppen-Liste befuellen ───────────────────────────────────────────────

    def _refresh_group_list(self):
        """Liest alle FixtureGroups aus der DB und befuellt self._group_list."""
        eng = getattr(self._state, "_show_engine", None)
        if eng is None:
            return
        try:
            import json as _json
            from sqlalchemy.orm import Session as _Session
            from src.core.database.models import FixtureGroup as _FG
            from sqlalchemy import select as _select
            with _Session(eng) as s:
                groups = list(
                    s.execute(_select(_FG).order_by(_FG.name)).scalars()
                )
                self._group_list.clear()
                from src.core.group_cells import base_fids_in_grid_order
                for g in groups:
                    # Anzahl GERAETE (Basis-fids) — Kopf-Matrix-Zellen "fid:head"
                    # zaehlen als EIN Geraet, nicht als N Zellen (FM16E-HEADCOUNT).
                    try:
                        pos = _json.loads(g.positions_json or "{}")
                        n = len(base_fids_in_grid_order(pos))
                    except Exception:
                        n = 0
                    item = QListWidgetItem(f"{g.name} ({n})")
                    item.setData(Qt.ItemDataRole.UserRole, g.id)
                    item.setIcon(_mini.folder_icon())
                    self._group_list.addItem(item)
        except Exception as e:
            print(f"[live_view] _refresh_group_list error: {e}")

    # ── Gruppe aus Auswahl erstellen ──────────────────────────────────────────

    def create_group_from_selection(self, name: str) -> int | None:
        """Erstellt eine neue FixtureGroup aus der aktuellen Canvas-Auswahl.

        Speichert als 1×N-Gruppe (cols=N, rows=1) in Auswahl-Reihenfolge.
        Gibt die neue Gruppen-ID zurueck, oder None bei Fehler.
        """
        fids = list(self._canvas._selected_fids)
        if not fids or not name.strip():
            return None
        eng = getattr(self._state, "_show_engine", None)
        if eng is None:
            return None
        # 1xN in Auswahl-Reihenfolge -> Programmer-Reihenfolge = Auswahl
        # Format: {"col,row": fid}  row-major → sortiere nach (row, col)
        positions = {f"{i},0": fid for i, fid in enumerate(fids)}
        import json as _json
        from sqlalchemy.orm import Session as _Session
        from src.core.database.models import FixtureGroup as _FG
        gid = None
        try:
            with _Session(eng) as s:
                g = _FG(name=name.strip(), cols=len(fids), rows=1,
                        positions_json=_json.dumps(positions))
                s.add(g)
                s.commit()
                gid = g.id
        except Exception as e:
            print(f"[live_view] create group error: {e}")
            return None
        # Programmer + Patcher aktualisieren (beide lauschen auf PATCH_CHANGED)
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.GROUP_CHANGED, None)
        except Exception:
            pass
        self._refresh_group_list()
        return gid

    # ── Gruppen-Button-Handler ────────────────────────────────────────────────

    def _on_create_group_clicked(self):
        """Handler fuer 'Gruppe aus Auswahl…' Button."""
        if not self._canvas._selected_fids:
            QMessageBox.information(
                self, "Gruppe erstellen",
                "Erst Fixtures auswählen — 'Mehrfachauswahl' oben einschalten und antippen, "
                "oder auf leerer Fläche einen Rahmen ziehen."
            )
            return
        name, ok = QInputDialog.getText(
            self, "Gruppe erstellen",
            f"Name der neuen Gruppe ({len(self._canvas._selected_fids)} Fixture(s)):"
        )
        if not ok or not name.strip():
            return
        gid = self.create_group_from_selection(name)
        if gid is not None:
            # Auf den Gruppen-Reiter wechseln
            self._left_tabs.setCurrentIndex(1)
            # Statushinweis im Footer (sticky, wird nicht sofort ueberschrieben)
            self._set_status(f"Gruppe \"{name.strip()}\" erstellt (ID {gid})")

    def _on_multi_toggle(self, checked: bool):
        """Schaltet den Touch-Mehrfachauswahl-Modus um.

        Wirkt auf Canvas UND linke Liste: im Modus toggelt einfaches Antippen
        eines Listeneintrags die Auswahl (Qt MultiSelection — kein Strg/Shift
        nötig); aus = gewohnte ExtendedSelection mit Strg/Shift."""
        self._canvas.set_multi_select_mode(checked)
        from PySide6.QtWidgets import QAbstractItemView
        mode = (QAbstractItemView.SelectionMode.MultiSelection if checked
                else QAbstractItemView.SelectionMode.ExtendedSelection)
        self._fixture_list.setSelectionMode(mode)
        if checked:
            self._set_status("Mehrfachauswahl AN: Antippen sammelt (Fläche und Liste)")
        else:
            self._clear_status()
            self._update_selection_label()

    def _on_clear_selection(self):
        """Leert die aktuelle Auswahl in der Live View."""
        self._canvas._selected_fids = []
        self._canvas._emit_selection()
        self._canvas.update()

    def _on_add_selection_to_group_clicked(self):
        """Fügt die aktuell ausgewählten Fixtures der angezeigten Gruppe hinzu."""
        gid = self._detail_group_id
        if gid is None:
            return
        to_add = list(self._canvas._selected_fids)
        if not to_add:
            QMessageBox.information(
                self, "Zur Gruppe hinzufügen",
                "Erst Fixtures im Bühnen-Layout auswählen — 'Mehrfachauswahl' oben "
                "einschalten und antippen, oder auf leerer Fläche einen Rahmen ziehen."
            )
            return
        eng = getattr(self._state, "_show_engine", None)
        if eng is None:
            return
        try:
            import json as _json
            from sqlalchemy.orm import Session as _Session
            from src.core.database.models import FixtureGroup as _FG
            with _Session(eng) as s:
                g = s.get(_FG, gid)
                if g is None:
                    return
                try:
                    pos = _json.loads(g.positions_json or "{}")
                except Exception:
                    pos = {}
                # bestehende Reihenfolge (row-major) + neue fids anhängen (keine Duplikate)
                merged = [
                    fid for _, fid in sorted(
                        pos.items(),
                        key=lambda kv: (int(kv[0].split(",")[1]),
                                        int(kv[0].split(",")[0]))
                    )
                ]
                added = 0
                for fid in to_add:
                    if fid not in merged:
                        merged.append(fid)
                        added += 1
                new_pos = {f"{i},0": fid for i, fid in enumerate(merged)}
                g.positions_json = _json.dumps(new_pos)
                g.cols = max(1, len(merged))
                s.commit()
        except Exception as e:
            print(f"[live_view] _on_add_selection_to_group_clicked error: {e}")
            return
        # Sync + Detail/Liste/Highlight aktualisieren (gleiches Muster wie entfernen)
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.GROUP_CHANGED, None)
        except Exception:
            pass
        self._refresh_group_list()
        for i in range(self._group_list.count()):
            it = self._group_list.item(i)
            if it and it.data(Qt.ItemDataRole.UserRole) == gid:
                self._on_group_selected(it)
                break
        self._set_status(f"{added} Fixture(s) zur Gruppe hinzugefügt")

    def _on_delete_group_clicked(self):
        """Loescht die aktuell in der Gruppen-Liste gewaehlte Gruppe."""
        item = self._group_list.currentItem()
        if item is None:
            return
        gid = item.data(Qt.ItemDataRole.UserRole)
        group_name = item.text()
        reply = QMessageBox.question(
            self, "Gruppe löschen",
            f'Gruppe "{group_name}" wirklich löschen?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        eng = getattr(self._state, "_show_engine", None)
        if eng is None:
            return
        try:
            from sqlalchemy.orm import Session as _Session
            from src.core.database.models import FixtureGroup as _FG
            from sqlalchemy import delete as _delete
            with _Session(eng) as s:
                s.execute(_delete(_FG).where(_FG.id == gid))
                s.commit()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))
            return
        # Wenn die gerade im Detail angezeigte Gruppe gelöscht wurde → verstecken
        if self._detail_group_id == gid:
            self._detail_group_id = None
            self._group_detail_box.setVisible(False)
            self._canvas.set_highlight(set())
        # Sync + Refresh
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.GROUP_CHANGED, None)
        except Exception:
            pass
        self._refresh_group_list()

    # ── Gruppen-Selektion → Highlight + Detail ────────────────────────────────

    def _on_group_selected(self, item: QListWidgetItem):
        """Wird aufgerufen wenn eine Gruppe in der Liste angeklickt wird."""
        gid = item.data(Qt.ItemDataRole.UserRole)
        if gid is None:
            return
        eng = getattr(self._state, "_show_engine", None)
        if eng is None:
            return
        try:
            import json as _json
            from sqlalchemy.orm import Session as _Session
            from src.core.database.models import FixtureGroup as _FG
            with _Session(eng) as s:
                g = s.get(_FG, gid)
                if g is None:
                    return
                try:
                    pos = _json.loads(g.positions_json or "{}")
                except Exception:
                    pos = {}
                # FM16E-HEADCOUNT: Basis-fids in Rasterreihenfolge (eine Quelle
                # group_cells). Kopf-Zellen "fid:head" -> int-Basis-fid -> Canvas-
                # Highlight matcht, Count zeigt GERAETE, und f"{fid:03d}" unten wirft
                # nicht mehr auf einem Roh-String.
                from src.core.group_cells import base_fids_in_grid_order
                fids = base_fids_in_grid_order(pos)
                self._detail_group_id = gid
                # Canvas Highlight setzen
                self._canvas.set_highlight(set(fids))
                # Detail-Panel befuellen
                self._edit_group_name.blockSignals(True)
                self._edit_group_name.setText(g.name or "")
                self._edit_group_name.blockSignals(False)
                self._lbl_group_count.setText(f"{len(fids)} Fixtures")
                self._group_members.clear()
                # Fixture-Labels holen
                try:
                    fixtures = self._state.get_patched_fixtures()
                    label_map = {f.fid: (getattr(f, "label", None) or
                                         getattr(f, "fixture_type", "?") or "?")
                                 for f in fixtures}
                    fixture_map = {f.fid: f for f in fixtures}
                except Exception:
                    label_map = {}
                    fixture_map = {}
                for fid in fids:
                    lbl = label_map.get(fid, "?")
                    member_item = QListWidgetItem(f"[{fid:03d}] {lbl}")
                    member_item.setData(Qt.ItemDataRole.UserRole, fid)
                    if fid in fixture_map:
                        member_item.setIcon(_mini.fixture_icon_for(fixture_map[fid]))
                    self._group_members.addItem(member_item)
                self._group_detail_box.setVisible(True)
        except Exception as e:
            print(f"[live_view] _on_group_selected error: {e}")

    def _on_group_name_edited(self):
        """P3: Gruppenname aus dem Detail-Panel speichern. Leerer Name wird
        verworfen (alter Name bleibt); der neue Name verteilt sich ueber
        GROUP_CHANGED an Programmer/Patch/Matrix."""
        gid = getattr(self, "_detail_group_id", None)
        if gid is None:
            return
        name = (self._edit_group_name.text() or "").strip()
        eng = getattr(self._state, "_show_engine", None)
        if eng is None:
            return
        try:
            from sqlalchemy.orm import Session as _Session
            from src.core.database.models import FixtureGroup as _FG
            with _Session(eng) as s:
                g = s.get(_FG, gid)
                if g is None:
                    return
                if not name:
                    # leeren Namen nicht zulassen -> Feld zuruecksetzen
                    self._edit_group_name.blockSignals(True)
                    self._edit_group_name.setText(g.name or "")
                    self._edit_group_name.blockSignals(False)
                    return
                if name == (g.name or ""):
                    return
                g.name = name
                s.commit()
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.GROUP_CHANGED, None)
        except Exception as e:
            print(f"[live_view] group rename error: {e}")

    # ── Fixture aus Gruppe entfernen ──────────────────────────────────────────

    def _on_remove_member_clicked(self):
        """Entfernt das gewaehlte Fixture aus der aktuell angezeigten Gruppe."""
        member_item = self._group_members.currentItem()
        if member_item is None:
            return
        fid_to_remove = member_item.data(Qt.ItemDataRole.UserRole)
        if fid_to_remove is None:
            return
        gid = self._detail_group_id
        if gid is None:
            return
        eng = getattr(self._state, "_show_engine", None)
        if eng is None:
            return
        try:
            import json as _json
            from sqlalchemy.orm import Session as _Session
            from src.core.database.models import FixtureGroup as _FG
            with _Session(eng) as s:
                g = s.get(_FG, gid)
                if g is None:
                    return
                try:
                    pos = _json.loads(g.positions_json or "{}")
                except Exception:
                    pos = {}
                # Reihenfolge der uebrigen beibehalten (row-major), neu nummerieren
                remaining = [
                    fid for _, fid in sorted(
                        pos.items(),
                        key=lambda kv: (int(kv[0].split(",")[1]),
                                        int(kv[0].split(",")[0]))
                    )
                    if fid != fid_to_remove
                ]
                new_pos = {f"{i},0": fid for i, fid in enumerate(remaining)}
                g.positions_json = _json.dumps(new_pos)
                g.cols = max(1, len(remaining))
                s.commit()
        except Exception as e:
            print(f"[live_view] _on_remove_member_clicked error: {e}")
            return
        # Sync + Refresh Detail + Liste + Highlight
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.GROUP_CHANGED, None)
        except Exception:
            pass
        self._refresh_group_list()
        # Detail neu laden: Gruppe aus Liste neu selektieren
        for i in range(self._group_list.count()):
            it = self._group_list.item(i)
            if it and it.data(Qt.ItemDataRole.UserRole) == gid:
                self._on_group_selected(it)
                break

    # ── Status-Refresh ────────────────────────────────────────────────────────

    def _refresh_info(self):
        try:
            fixtures = self._state.get_patched_fixtures()
        except Exception:
            fixtures = []
        self._lbl_info.setText(f"{len(fixtures)} Geräte im Patch")
        self._update_selection_label()

    # ── Footer-Status (sticky-faehig) ─────────────────────────────────────────

    def _set_status(self, msg: str, sticky_sec: float = 4.0):
        """Zeigt eine kurzlebige Statusmeldung im Footer, die der Info-Timer
        sticky_sec Sekunden lang NICHT mit dem Auswahl-Text ueberschreibt."""
        self._sticky_until = time.time() + sticky_sec
        self._lbl_selected.setText(msg)

    def _clear_status(self):
        """Hebt eine sticky-Meldung sofort auf (z. B. bei neuer Auswahl)."""
        self._sticky_until = 0.0

    def _update_selection_label(self):
        """Schreibt den Auswahl-Text in den Footer — respektiert sticky-Meldungen
        und nutzt ein einheitliches, lesbares Format (kein rohes fids=[…])."""
        if time.time() < getattr(self, "_sticky_until", 0.0):
            return
        sel = self._canvas._selected_fids
        n = len(sel)
        if n == 0:
            self._lbl_selected.setText("Selektion: -")
        elif n == 1:
            self._lbl_selected.setText(f"Selektion: 1 Fixture (fid={sel[0]})")
        else:
            self._lbl_selected.setText(f"Selektion: {n} Fixtures")

    def _on_fixture_clicked(self, fid: int):
        # Globaler State + Footer werden bereits ueber selection_changed
        # (_on_canvas_selection_changed) gepflegt — hier nichts doppelt setzen,
        # sonst zwei SELECTION_CHANGED-Emits pro Klick.
        pass

    def _on_tree_selection_changed(self):
        """P2: Auswahl in der linken Liste -> Canvas-Highlight + globaler State.
        Universe-Ordner (UserRole=None) werden ignoriert."""
        if self._tree_sync_guard:
            return
        fids: list[int] = []
        for it in self._fixture_list.selectedItems():
            fid = it.data(0, Qt.ItemDataRole.UserRole)
            if fid is not None:
                fids.append(int(fid))
        self._canvas.set_selection(fids)
        try:
            self._state.set_selected_fids(fids)
        except Exception:
            pass
        self._clear_status()
        self._update_selection_label()

    def _mirror_selection_to_tree(self, fids):
        """Canvas-Auswahl in der linken Liste markieren (ohne Echo)."""
        self._tree_sync_guard = True
        try:
            wanted = set(int(f) for f in fids)
            for i in range(self._fixture_list.topLevelItemCount()):
                top = self._fixture_list.topLevelItem(i)
                for j in range(top.childCount()):
                    ch = top.child(j)
                    fid = ch.data(0, Qt.ItemDataRole.UserRole)
                    ch.setSelected(fid is not None and int(fid) in wanted)
        except Exception:
            pass
        finally:
            self._tree_sync_guard = False

    def _on_canvas_selection_changed(self):
        """Wird bei jeder Aenderung der Canvas-Auswahl aufgerufen (Phase 7b)."""
        try:
            self._state.set_selected_fids(list(self._canvas._selected_fids))
        except Exception:
            pass
        self._mirror_selection_to_tree(self._canvas._selected_fids)
        self._clear_status()
        self._update_selection_label()

    def _on_global_selection_changed(self, fids=None):
        """Globale Programmer-Auswahl in der Live View spiegeln (goldener Ring +
        Listen-Markierung). set_selection emittiert NICHT zurueck -> kein Loop;
        set_selected_fids feuert bei gleicher Auswahl ohnehin nicht erneut."""
        try:
            if fids is None:
                fids = self._state.get_selected_fids()
            self._canvas.set_selection(list(fids))
            # FM-51 C: ein nur ueber Weiss gewaehltes Geraet fehlt im Payload
            # (selected_fids) — es bekommt trotzdem seinen Ring.
            nur_weiss = getattr(self._state, "nur_weiss_fids", None)
            self._canvas.set_teil_markierung(
                nur_weiss() if callable(nur_weiss) else ())
            self._mirror_selection_to_tree(fids)
            self._clear_status()
            self._update_selection_label()
        except (RuntimeError, AttributeError):
            pass

    def _on_canvas_context_menu(self, fid: int, global_pos):
        """Kontextmenue auf der Canvas (Rechtsklick) — bleibt im Live-View-Umfang."""
        from PySide6.QtWidgets import QMenu
        n = len(self._canvas._selected_fids)
        menu = QMenu(self)
        act_group = menu.addAction("＋ Gruppe aus Auswahl …")
        act_group.setEnabled(n > 0)
        act_clear = menu.addAction("Auswahl leeren")
        act_clear.setEnabled(n > 0)
        chosen = menu.exec(global_pos)
        if chosen is act_group:
            self._on_create_group_clicked()
        elif chosen is act_clear:
            self._on_clear_selection()
