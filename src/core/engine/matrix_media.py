"""FM-81: Medien (Bild, animiertes GIF) als Quelle des Matrix-Effekts.

Die Matrix-Art „Bild/Video" (``RgbAlgorithm.MEDIA``) legt ein Bild oder ein
animiertes GIF auf das Raster der Gruppe. Dieses Modul haelt alles, was mit der
Datei zu tun hat — der Render-Takt fasst nie eine Datei an:

* **Ablage:** Medien liegen im Datenordner unter ``matrix_media/`` (wie die
  ``vc_assets``), NICHT in der Show-Datei. Die Show speichert nur den Pfad
  RELATIV zu diesem Ordner (``params["media_path"]``). ``import_file`` kopiert
  eine gewaehlte Datei dorthin und liefert den relativen Namen.
* **Dekodieren ausserhalb des Render-Takts:** ``bilder()`` ist nicht blockierend.
  Ist die Bildfolge fuer (Datei, Rastergroesse, Einpassung, Drehung) noch nicht
  da, startet sie EINEN Hintergrund-Thread, der die Datei mit ``QImageReader``
  liest, dreht, auf ``cols x rows`` abbildet und als fertige Pixel-Listen
  ablegt. Bis dahin liefert sie ``None`` (die Matrix bleibt dunkel). Danach ist
  ein Frame nur noch ein Listenzugriff.
* **Fehler:** fehlende/unlesbare Datei -> klare Meldung, kein Absturz.

Video (MP4 & Co.) ist ein ehrlicher Rest: im venv gibt es keinen Dekoder, der
ohne Ereignisschleife in einem Hintergrund-Thread Einzelbilder liefert
(QtMultimedia braucht QMediaPlayer + Ereignisschleife; imageio/av fehlen).
"""
from __future__ import annotations

import os
import shutil
import threading
from dataclasses import dataclass, field

Color = tuple

FIT_OPTIONS = ("fit", "fill", "stretch")
ROTATION_OPTIONS = ("0", "90", "180", "270")
BILD_ENDUNGEN = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
VIDEO_ENDUNGEN = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".mpg", ".mpeg"}
# Obergrenze der vorberechneten Bilder je Medium (Speicher-Deckel).
MAX_BILDER = 3000
# Standard-Bildzeit, wenn ein GIF keine (oder 0) Verzoegerung angibt.
STANDARD_BILDZEIT = 0.1
# Hoechstzahl gehaltener Bildfolgen. Jede Aenderung an Drehung/Einpassung/
# Rastergroesse/Datei ergibt einen neuen Schluessel; ohne Deckel blieben alle
# alten Folgen (bis MAX_BILDER x Raster Pixel je Folge) im Speicher liegen.
MAX_CACHE = 8

_override_dir: str | None = None


def set_media_dir_for_test(path: str | None) -> None:
    """Test-Hook: Medien-Ordner umbiegen."""
    global _override_dir
    _override_dir = path
    leeren()


def media_dir() -> str:
    if _override_dir:
        os.makedirs(_override_dir, exist_ok=True)
        return _override_dir
    eigen = os.environ.get("LIGHTOS_MATRIX_MEDIA_DIR")
    if eigen:
        os.makedirs(eigen, exist_ok=True)
        return eigen
    from src.core.paths import app_data_dir
    d = os.path.join(app_data_dir(), "matrix_media")
    os.makedirs(d, exist_ok=True)
    return d


def import_file(src: str) -> str:
    """Kopiert ``src`` in den Medien-Ordner (falls nicht schon dort) und liefert
    den RELATIVEN Namen, der in der Show gespeichert wird."""
    base = os.path.realpath(media_dir())
    src_real = os.path.realpath(src)
    if os.path.commonpath([base, src_real]) == base:
        return os.path.relpath(src_real, base).replace(os.sep, "/")
    name = os.path.basename(src_real)
    stamm, endung = os.path.splitext(name)
    ziel = os.path.join(base, name)
    n = 1
    while os.path.exists(ziel):
        try:
            if os.path.getsize(ziel) == os.path.getsize(src_real) and \
                    open(ziel, "rb").read() == open(src_real, "rb").read():
                break
        except OSError:
            pass
        ziel = os.path.join(base, f"{stamm}_{n}{endung}")
        n += 1
    if not os.path.exists(ziel):
        shutil.copyfile(src_real, ziel)
    return os.path.basename(ziel)


def resolve(rel: str) -> str | None:
    """Absoluter Pfad zu einem gespeicherten Medium oder ``None``.

    Relative Namen werden im Medien-Ordner aufgeloest und duerfen ihn nicht
    verlassen (kein ``../``). Absolute Pfade werden toleriert (Handeintrag)."""
    if not rel:
        return None
    if os.path.isabs(rel):
        pfad = rel
    else:
        base = os.path.realpath(media_dir())
        pfad = os.path.realpath(os.path.join(base, rel))
        if os.path.commonpath([base, pfad]) != base:
            return None
    return pfad if os.path.isfile(pfad) else None


@dataclass
class Bildfolge:
    """Vorberechnete Bildfolge in Rastergroesse."""
    bilder: list = field(default_factory=list)      # je Bild: list[Color] (row-major)
    zeiten: list = field(default_factory=list)      # Dauer je Bild in s
    gesamt: float = 0.0

    def index_bei(self, t: float, schleife: bool) -> int:
        n = len(self.bilder)
        if n <= 1 or self.gesamt <= 0:
            return 0
        if schleife:
            t = t % self.gesamt
        elif t <= 0:
            return 0
        elif t >= self.gesamt:
            return n - 1
        acc = 0.0
        for i, d in enumerate(self.zeiten):
            acc += d
            if t < acc:
                return i
        return n - 1


@dataclass
class Ergebnis:
    folge: Bildfolge | None = None
    meldung: str = ""          # leer = alles gut
    laedt: bool = False


_lock = threading.Lock()
_cache: dict = {}               # key -> Ergebnis
_threads: dict = {}             # key -> Thread


def leeren() -> None:
    with _lock:
        _cache.clear()


def _abbilden(img, cols: int, rows: int, fit: str, rotation: int) -> list:
    """Ein QImage drehen und auf cols x rows abbilden -> row-major Pixel."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter, QTransform
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    if rotation % 360:
        img = img.transformed(QTransform().rotate(rotation % 360),
                              Qt.TransformationMode.SmoothTransformation)
    ziel = QImage(cols, rows, QImage.Format.Format_ARGB32)
    ziel.fill(0xFF000000)
    w, h = img.width(), img.height()
    if w <= 0 or h <= 0:
        return [(0, 0, 0)] * (cols * rows)
    if fit == "stretch":
        mode = Qt.AspectRatioMode.IgnoreAspectRatio
    elif fit == "fill":
        mode = Qt.AspectRatioMode.KeepAspectRatioByExpanding
    else:
        mode = Qt.AspectRatioMode.KeepAspectRatio
    skaliert = img.scaled(cols, rows, mode, Qt.TransformationMode.SmoothTransformation)
    x = (cols - skaliert.width()) // 2
    y = (rows - skaliert.height()) // 2
    p = QPainter(ziel)
    try:
        p.drawImage(x, y, skaliert)
    finally:
        p.end()
    out = []
    for r in range(rows):
        for c in range(cols):
            px = ziel.pixel(c, r)
            a = (px >> 24) & 0xFF
            rr, gg, bb = (px >> 16) & 0xFF, (px >> 8) & 0xFF, px & 0xFF
            if a < 255:   # Transparenz gegen Schwarz
                rr, gg, bb = rr * a // 255, gg * a // 255, bb * a // 255
            out.append((rr, gg, bb))
    return out


def dekodieren(pfad: str, cols: int, rows: int, fit: str, rotation: int) -> Ergebnis:
    """Liest die Datei vollstaendig (blockierend) — nur im Hintergrund-Thread
    oder beim Zuweisen aufrufen, nie im Render-Takt."""
    endung = os.path.splitext(pfad)[1].lower()
    if endung in VIDEO_ENDUNGEN:
        return Ergebnis(meldung="Video wird noch nicht unterstützt — bitte Bild oder "
                                "animiertes GIF verwenden.")
    from PySide6.QtGui import QImageReader
    reader = QImageReader(pfad)
    reader.setAutoTransform(True)
    folge = Bildfolge()
    while len(folge.bilder) < MAX_BILDER:
        img = reader.read()
        if img.isNull():
            break
        dauer = reader.nextImageDelay() / 1000.0
        folge.bilder.append(_abbilden(img, cols, rows, fit, rotation))
        folge.zeiten.append(dauer if dauer > 0 else STANDARD_BILDZEIT)
        if not reader.supportsAnimation() or not reader.canRead():
            break
    if not folge.bilder:
        return Ergebnis(meldung=f"Medium nicht lesbar: {os.path.basename(pfad)} "
                                f"({reader.errorString()})")
    folge.gesamt = sum(folge.zeiten)
    return Ergebnis(folge=folge)


def _key(rel: str, cols: int, rows: int, fit: str, rotation: int):
    pfad = resolve(rel)
    try:
        mtime = os.path.getmtime(pfad) if pfad else None
    except OSError:
        mtime = None
    return (pfad, mtime, int(cols), int(rows), fit, int(rotation)), pfad


def _normieren(fit, rotation):
    fit = fit if fit in FIT_OPTIONS else "fit"
    try:
        rotation = int(rotation) % 360
    except (TypeError, ValueError):
        rotation = 0
    if rotation not in (0, 90, 180, 270):
        rotation = 0
    return fit, rotation


def bilder(rel: str, cols: int, rows: int, fit: str = "fit", rotation=0) -> Ergebnis:
    """NICHT blockierend: fertige Bildfolge, Fehlermeldung oder „laedt".
    Startet beim ersten Aufruf das Dekodieren im Hintergrund."""
    if not rel:
        return Ergebnis(meldung="Kein Medium gewählt.")
    fit, rotation = _normieren(fit, rotation)
    key, pfad = _key(rel, cols, rows, fit, rotation)
    if pfad is None:
        return Ergebnis(meldung=f"Medium fehlt: {rel} (erwartet im Medien-Ordner "
                                f"neben den Show-Daten)")
    with _lock:
        fertig = _cache.get(key)
        if fertig is not None:
            # Zuletzt benutzt -> ans Ende, damit der Deckel die alten trifft.
            _cache[key] = _cache.pop(key)
            return fertig
        t = _threads.get(key)
        if t is None or not t.is_alive():
            t = threading.Thread(target=_arbeiter, args=(key, pfad, cols, rows, fit, rotation),
                                 name="matrix-medien", daemon=True)
            _threads[key] = t
            t.start()
    return Ergebnis(laedt=True, meldung="Medium wird geladen …")


def _arbeiter(key, pfad, cols, rows, fit, rotation):
    try:
        erg = dekodieren(pfad, cols, rows, fit, rotation)
    except Exception as exc:  # pragma: no cover - Schutz gegen Dekoder-Fehler
        erg = Ergebnis(meldung=f"Medium nicht lesbar: {exc}")
    with _lock:
        _cache[key] = erg
        _threads.pop(key, None)
        # Aelteste Folgen verwerfen (dict haelt die Einfuegereihenfolge).
        while len(_cache) > MAX_CACHE:
            _cache.pop(next(iter(_cache)))


def vorbereiten(rel: str, cols: int, rows: int, fit: str = "fit", rotation=0,
                warten: float = 0.0) -> Ergebnis:
    """Beim Zuweisen aufrufen: stoesst das Dekodieren an; mit ``warten`` > 0
    wird bis zu so viele Sekunden auf das Ergebnis gewartet."""
    erg = bilder(rel, cols, rows, fit, rotation)
    if warten > 0 and erg.laedt:
        fit, rotation = _normieren(fit, rotation)
        key, _ = _key(rel, cols, rows, fit, rotation)
        with _lock:
            t = _threads.get(key)
        if t is not None:
            t.join(warten)
        erg = bilder(rel, cols, rows, fit, rotation)
    return erg
