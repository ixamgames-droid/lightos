"""VCG-02: Tastenbild als Momentaufnahme aus der 3D-Ansicht.

Ein Klick im Galerie-Dialog der VC-Taste nimmt das aktuelle Bild der offenen
3D-Ansicht auf (``window.__lightos.momentaufnahme()`` in ``scene_src/app.js``
liefert eine PNG-Data-URL), schneidet die Mitte im Seitenverhaeltnis der Taste
heraus, verkleinert auf hoechstens ``MAX_PX`` und legt das PNG ueber
``vc_assets`` in den inhaltsadressierten Cache — von dort reist es wie jede
Galerie-Grafik in der ``.lshow`` mit.

Bewusst eine MOMENTAUFNAHME (Entscheidung 2026-10-05): das Bild wird nicht
automatisch neu erzeugt, wenn sich die Funktion der Taste aendert. Keine neue
Abhaengigkeit — QImage kann PNG schreiben.
"""
from __future__ import annotations

import base64
from typing import Callable

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from src.core.show import vc_assets

MAX_PX = 256

MELDUNG_KEIN_3D = ("Erst den 3D-Visualizer öffnen und die Funktion der Taste "
                   "starten — dann noch einmal „Aus 3D-Ansicht aufnehmen“.")
MELDUNG_FEHLGESCHLAGEN = ("Die 3D-Ansicht hat kein Bild geliefert. Ist die Szene "
                          "fertig geladen? Bitte kurz warten und erneut versuchen.")

_JS_AUFNAHME = ("(function(){var a=window.__lightos;"
                "return (a && typeof a.momentaufnahme==='function')"
                " ? a.momentaufnahme() : '';})()")


def zuschneiden(bild: QImage, seitenverhaeltnis: float,
                max_px: int = MAX_PX) -> QImage:
    """Mitte im Seitenverhaeltnis ``breite/hoehe`` ausschneiden, dann so
    verkleinern, dass die laengere Seite hoechstens ``max_px`` misst
    (nie vergroessern). Leeres Bild bleibt leer."""
    if bild.isNull() or bild.width() <= 0 or bild.height() <= 0:
        return QImage()
    try:
        sv = float(seitenverhaeltnis)
    except (TypeError, ValueError):
        sv = 1.0
    if not (sv > 0) or sv == float("inf"):
        sv = 1.0
    w, h = bild.width(), bild.height()
    if w / h > sv:                       # zu breit -> links/rechts kappen
        cw, ch = max(1, round(h * sv)), h
    else:                                # zu hoch -> oben/unten kappen
        cw, ch = w, max(1, round(w / sv))
    ausschnitt = bild.copy((w - cw) // 2, (h - ch) // 2, cw, ch)
    if max(cw, ch) > max_px:
        ausschnitt = ausschnitt.scaled(
            max_px, max_px, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
    return ausschnitt


def bild_aus_data_url(data_url) -> QImage:
    """``data:image/png;base64,…`` -> QImage (leer bei allem anderen)."""
    if not isinstance(data_url, str) or "," not in data_url \
            or not data_url.startswith("data:image/"):
        return QImage()
    try:
        roh = base64.b64decode(data_url.split(",", 1)[1], validate=False)
    except (ValueError, TypeError):
        return QImage()
    bild = QImage()
    bild.loadFromData(roh)
    return bild


def png_bytes(bild: QImage) -> bytes:
    puffer = QBuffer()
    puffer.open(QIODevice.OpenModeFlag.WriteOnly)
    bild.save(puffer, "PNG")
    return bytes(puffer.data())


def als_tastenbild(data_url, seitenverhaeltnis: float) -> str | None:
    """Aufnahme -> Zuschnitt -> PNG im Asset-Cache. Liefert den Key oder None."""
    bild = zuschneiden(bild_aus_data_url(data_url), seitenverhaeltnis)
    if bild.isNull():
        return None
    daten = png_bytes(bild)
    if not daten:
        return None
    return vc_assets.store_bytes(daten, ".png")


def finde_3d_ansicht():
    """Die sichtbare 3D-Ansicht (Vollfenster oder eingebettet) oder None.

    Erkannt am Kennzeichen, das ``load_stage_html`` setzt. Bei mehreren gewinnt
    die groesste — das ist in der Regel das 3D-Visualizer-Fenster."""
    app = QApplication.instance()
    if app is None:
        return None
    kandidaten = []
    for w in app.allWidgets():
        try:
            if getattr(w, "_lightos_3d_szene", False) and w.isVisible():
                kandidaten.append(w)
        except RuntimeError:            # C++-Objekt schon weg
            continue
    if not kandidaten:
        return None
    return max(kandidaten, key=lambda v: v.width() * v.height())


def aufnehmen(ansicht, fertig: Callable[[str], None]) -> None:
    """Momentaufnahme anfordern; ``fertig(data_url)`` kommt asynchron
    (``''``, wenn die Szene kein Bild liefern konnte)."""
    ansicht.page().runJavaScript(
        _JS_AUFNAHME, lambda r: fertig(r if isinstance(r, str) else ""))
