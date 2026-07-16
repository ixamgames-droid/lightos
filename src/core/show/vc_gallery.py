"""VC-IMG: eingebaute Button-Grafik-Galerie (``assets/vc_gallery/``).

Reines Python (KEIN Qt) -> auch von Generator/Lint/Headless-Tests nutzbar. Laedt
``manifest.json``, loest einen stabilen Namen -> Datei und importiert die Grafik
bei Bedarf in den Asset-Cache (``vc_assets``), sodass sie wie eine user-Datei
portabel in die ``.lshow`` eingebettet wird (Content-Hash-Key).

Die Grafiken werden von ``tools/gen_vc_gallery.py`` erzeugt und mit-committed.
Pfad ``__file__``-relativ (dev + Source-Install; ein frozen Build braeuchte einen
Resource-Helper — bewusst nicht abgedeckt, es gibt keinen PyInstaller-Build)."""
from __future__ import annotations
import json
import os

from . import vc_assets

_GALLERY_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "assets", "vc_gallery"))


def gallery_dir() -> str:
    return _GALLERY_DIR


def _manifest() -> dict:
    try:
        with open(os.path.join(_GALLERY_DIR, "manifest.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"items": []}


def entries() -> list[dict]:
    """Liste ``{name,file,kind,category,title,path}`` der vorhandenen Grafiken
    (nur Eintraege, deren Datei wirklich existiert)."""
    out = []
    for it in _manifest().get("items", []):
        f = it.get("file", "")
        path = os.path.join(_GALLERY_DIR, f)
        if f and os.path.isfile(path):
            out.append({**it, "path": path})
    return out


def names() -> list[str]:
    return [e["name"] for e in entries()]


def resolve_path(name: str) -> str | None:
    for e in entries():
        if e.get("name") == name:
            return e["path"]
    return None


def import_to_cache(name: str) -> str:
    """Eine Galerie-Grafik in den Asset-Cache importieren -> Content-Hash-Key
    (embeddet danach wie eine user-Datei in die ``.lshow``). ``KeyError`` bei
    unbekanntem Namen."""
    path = resolve_path(name)
    if not path:
        raise KeyError(
            f"VC-Galerie: unbekannte Grafik '{name}' "
            f"(verfuegbar: {', '.join(names()) or '—'})")
    return vc_assets.import_file(path)
