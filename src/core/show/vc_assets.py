"""VC-IMG: Asset-Cache für VC-Button-Hintergrundbilder/GIFs.

Ein Button speichert nur einen Content-Hash-Key ``<sha1>.<ext>``, NICHT einen
Datei-Pfad -> portabel: das Bild reist im ``.lshow``-ZIP mit (siehe
``show_file.save_show``/``load_show``, die referenzierte Assets unter
``assets/vc/<key>`` einbetten bzw. beim Laden hierher entpacken). Die Bytes
liegen lokal im Cache ``%APPDATA%/LightOS/vc_assets/``; QPixmap/QMovie bekommen
so einen echten Dateipfad (das GIF-Plugin / die Bildformate brauchen einen Pfad).

Content-Hash-Key => automatische Deduplizierung (dasselbe Bild auf N Buttons =
eine Datei) und keine Kollision zwischen unterschiedlichen Bildern.

Der Cache wächst beim Laden vieler Shows an (jede Show entpackt ihre Assets
hierher). ``prune`` (VC-IMG-GC) deckelt ihn per LRU auf ``DEFAULT_MAX_BYTES`` und
wird aus ``show_file.load_show`` heraus aufgerufen; die vom aktuellen Show
referenzierten Assets bleiben dabei immer erhalten.
"""
from __future__ import annotations
import hashlib
import math
import os
import re
import time

_ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
# Key-Form: 40 Hex (sha1) + kurze Extension. Schuetzt beim Entpacken aus dem ZIP
# vor Pfad-Traversal (../, absolute Pfade) — nur genau dieses Muster wird abgelegt.
_KEY_RE = re.compile(r"[0-9a-f]{40}\.[a-z0-9]{1,5}")

_override_dir: str | None = None   # nur für Tests (set_cache_dir_for_test)


def set_cache_dir_for_test(path: str | None) -> None:
    """Test-Hook: Cache-Verzeichnis umbiegen (verschmutzt sonst den echten Cache)."""
    global _override_dir
    _override_dir = path


def cache_dir() -> str:
    if _override_dir:
        os.makedirs(_override_dir, exist_ok=True)
        return _override_dir
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "LightOS", "vc_assets")
    os.makedirs(d, exist_ok=True)
    return d


def is_valid_key(key: str) -> bool:
    return bool(key) and _KEY_RE.fullmatch(key) is not None


def _key_for(data: bytes, ext: str) -> str:
    ext = (ext or "").lower()
    if ext not in _ALLOWED_EXT:
        ext = ".png"
    return hashlib.sha1(data).hexdigest() + ext


def _write_atomic(dst: str, data: bytes) -> None:
    if os.path.isfile(dst):
        # Content-Hash -> identischer Inhalt, nichts neu zu schreiben. Aber die mtime
        # auffrischen: ein erneutes Referenzieren (Show-Load) zählt so als "kürzlich
        # benutzt", damit der LRU-Pruner einer PARALLELEN Session dieses noch aktiv
        # gebrauchte Asset nicht innerhalb seines min_age-Fensters wegräumt (VC-IMG-GC).
        try:
            os.utime(dst, None)
        except OSError:
            pass
        return
    tmp = dst + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, dst)


def store_bytes(data: bytes, ext: str) -> str:
    """Bytes in den Cache legen, Content-Hash-Key zurückgeben (idempotent)."""
    key = _key_for(data, ext)
    _write_atomic(os.path.join(cache_dir(), key), data)
    return key


def import_file(path: str) -> str:
    """Eine gewählte Bild-/GIF-Datei in den Cache importieren -> Key."""
    with open(path, "rb") as f:
        data = f.read()
    ext = os.path.splitext(path)[1] or ".png"
    return store_bytes(data, ext)


def resolve(key: str) -> str:
    """Key -> absoluter Cache-Pfad, oder "" wenn leer/ungültig/nicht vorhanden."""
    if not is_valid_key(key):
        return ""
    p = os.path.join(cache_dir(), key)
    return p if os.path.isfile(p) else ""


def bytes_for(key: str) -> bytes | None:
    """Cache-Bytes eines Keys (zum Einbetten ins ``.lshow``-ZIP). None wenn weg."""
    p = resolve(key)
    if not p:
        return None
    try:
        with open(p, "rb") as f:
            return f.read()
    except OSError:
        return None


def store_extracted(key: str, data: bytes) -> None:
    """Beim Laden: aus dem ZIP entpackte Bytes unter dem (bereits gehashten) Key
    ablegen. Ungültige Keys (Pfad-Traversal) werden verworfen."""
    if not is_valid_key(key):
        return
    _write_atomic(os.path.join(cache_dir(), key), data)


# ── Show-Datei-Integration ───────────────────────────────────────────────────
_ZIP_PREFIX = "assets/vc/"


def collect_keys(obj) -> set[str]:
    """Rekursiv alle ``bg_image``-Keys aus einem serialisierten Show-Dict sammeln
    (VC-Layout ist beliebig verschachtelt: Seiten/Bänke/Widgets)."""
    found: set[str] = set()

    def _walk(o):
        if isinstance(o, dict):
            v = o.get("bg_image")
            if isinstance(v, str) and is_valid_key(v):
                found.add(v)
            for val in o.values():
                _walk(val)
        elif isinstance(o, (list, tuple)):
            for val in o:
                _walk(val)

    _walk(obj)
    return found


def zip_name(key: str) -> str:
    return _ZIP_PREFIX + key


def is_asset_entry(name: str) -> bool:
    return name.startswith(_ZIP_PREFIX)


def key_from_entry(name: str) -> str:
    return name[len(_ZIP_PREFIX):]


# ── Cache-GC (VC-IMG-GC) ─────────────────────────────────────────────────────
# ``load_show`` entpackt die eingebetteten Assets JEDER geladenen Show hierher,
# räumt lokal aber nichts weg -> über viele Shows (oder eine bösartig große
# ``.lshow``) wächst der Ordner unbegrenzt. ``prune`` deckelt ihn: verwaiste
# Assets werden per LRU (mtime) entfernt, sobald der Cache das Limit überschreitet.
DEFAULT_MAX_BYTES = 256 * 1024 * 1024   # ~256 MB weicher Cache-Deckel
# Frisch geschriebene Dateien (< min_age) werden NIE evictet: mehrere LightOS-/
# Test-Prozesse teilen sich denselben Cache — eine parallele Session könnte gerade
# ein Asset entpackt haben, das sie gleich braucht. So räumen wir es ihr nicht weg.
_DEFAULT_MIN_AGE = 300.0                 # Sekunden


def _cache_max_bytes() -> int:
    """Deckel aus ``LIGHTOS_VC_ASSET_CACHE_MB`` (MB) oder ``DEFAULT_MAX_BYTES``."""
    raw = os.environ.get("LIGHTOS_VC_ASSET_CACHE_MB")
    if raw:
        try:
            mb = float(raw)
            # math.isfinite: 'inf'/'1e400'/riesige Zahlen (ein naheliegender Versuch,
            # "kein Limit" auszudrücken) ergäben int(inf) -> OverflowError. Der würde
            # aus prune() propagieren (Vertrag: wirft nie) und im load_show-except
            # verschluckt -> GC still deaktiviert. Solche Werte fallen auf den Default.
            if mb > 0 and math.isfinite(mb):
                return int(mb * 1024 * 1024)
        except ValueError:
            pass
    return DEFAULT_MAX_BYTES


def _unlink_quiet(path: str) -> bool:
    """Datei löschen; auf einem Windows-Dateilock (laufendes QMovie/QPixmap) oder
    einer parallel schon gelöschten Datei still ``False`` liefern statt zu werfen."""
    try:
        os.remove(path)
        return True
    except OSError:
        return False


def prune(keep: "set[str] | None" = None, *, max_bytes: "int | None" = None,
          min_age_seconds: float = _DEFAULT_MIN_AGE,
          now: "float | None" = None) -> int:
    """Verwaiste VC-Assets aus dem lokalen Cache räumen, bis er unter ``max_bytes``
    liegt. Gibt die Zahl gelöschter Asset-Dateien zurück. Darf nie werfen.

    Sicherheits-Invarianten:
      * Keys in ``keep`` (= vom AKTUELLEN Show referenziert) werden nie gelöscht —
        die live sichtbaren Buttons dürfen ihr Bild nicht verlieren.
      * Dateien jünger als ``min_age_seconds`` werden nie gelöscht (schützt frische
        Entpackungen paralleler Sessions, die sich den Cache teilen).
      * Es wird nur evictet, wenn der Cache das Limit ÜBERSCHREITET (kein Thrashing
        im Normalbetrieb; ein wieder geöffnetes Show entpackt seine Assets ohnehin
        erneut aus dem ZIP -> Löschen ist verlustfrei, nur Disk-Hygiene).
      * Pro-Datei-``try/except`` -> ein einzelner Fehler bricht den Lauf nicht ab.
    """
    keep = keep or set()
    if max_bytes is None:
        max_bytes = _cache_max_bytes()
    now = time.time() if now is None else now
    d = cache_dir()

    entries: list[tuple[float, int, str, str]] = []   # (mtime, size, path, key)
    total = 0
    try:
        scan = os.scandir(d)
    except OSError:
        return 0
    with scan:
        for de in scan:
            try:
                if not de.is_file():
                    continue
                st = de.stat()
            except OSError:
                continue
            name = de.name
            if not is_valid_key(name):
                # Verwaister Rest eines abgebrochenen _write_atomic heißt
                # ``<sha1>.<ext>.tmp`` (zwei Punkte -> KEIN gültiger Key). Nur solche
                # fremden .tmp-Reste mitentsorgen; ein gültiger ``<sha1>.tmp``-Key
                # (aus einer handgebauten .lshow) läuft hingegen unten durch die
                # normale keep-/LRU-Logik und ist nicht via .tmp-Sonderpfad löschbar.
                if name.endswith(".tmp") and (now - st.st_mtime) >= min_age_seconds:
                    _unlink_quiet(de.path)
                continue                 # fremde/unbekannte Datei nie mitzählen
            total += st.st_size
            entries.append((st.st_mtime, st.st_size, de.path, name))

    if total <= max_bytes:
        return 0

    removed = 0
    entries.sort(key=lambda e: e[0])     # ältestes mtime zuerst (LRU)
    for mtime, size, path, key in entries:
        if total <= max_bytes:
            break
        if key in keep:
            continue                     # vom aktuellen Show referenziert -> tabu
        if (now - mtime) < min_age_seconds:
            continue                     # zu frisch (evtl. parallele Session)
        try:
            os.remove(path)
        except FileNotFoundError:
            total -= size                # parallele Session hat's schon geräumt ->
            continue                     # Bytes sind wirklich weg (nicht mehr evicten)
        except OSError:
            continue                     # gelockt (laufendes QMovie) -> liegt noch da
        total -= size
        removed += 1
    return removed
