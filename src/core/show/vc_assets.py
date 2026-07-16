"""VC-IMG: Asset-Cache für VC-Button-Hintergrundbilder/GIFs.

Ein Button speichert nur einen Content-Hash-Key ``<sha1>.<ext>``, NICHT einen
Datei-Pfad -> portabel: das Bild reist im ``.lshow``-ZIP mit (siehe
``show_file.save_show``/``load_show``, die referenzierte Assets unter
``assets/vc/<key>`` einbetten bzw. beim Laden hierher entpacken). Die Bytes
liegen lokal im Cache ``%APPDATA%/LightOS/vc_assets/``; QPixmap/QMovie bekommen
so einen echten Dateipfad (das GIF-Plugin / die Bildformate brauchen einen Pfad).

Content-Hash-Key => automatische Deduplizierung (dasselbe Bild auf N Buttons =
eine Datei) und keine Kollision zwischen unterschiedlichen Bildern.
"""
from __future__ import annotations
import hashlib
import os
import re

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
        return                      # Content-Hash -> identischer Inhalt, nichts zu tun
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
