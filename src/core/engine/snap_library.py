"""Snap-Bibliothek — hält benannte Programmer-Snaps show-weit.

Singleton analog zum Palette-Manager / Kurven-Bibliothek (``get_snap_library()``).
Snaps werden **mit der Show** gespeichert (``library``-Block in show_file.py) —
nicht mehr als globale Einzeldateien. Beim ersten Start (oder beim Laden einer
Alt-Show ohne ``library``-Block) werden vorhandene globale Snap-Dateien aus
``SNAPS_DIR`` **automatisch importiert** (Originaldateien bleiben erhalten).

Siehe docs/PROGRAMMER_REBUILD.md (Phase 2).
"""
from __future__ import annotations
import os
import json
from pathlib import Path

# Alt-Speicherort der globalen Snap-Dateien (nur noch Migrations-Quelle).
SNAPS_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "LightOS", "snaps"
)


def _clean_values(raw: dict) -> dict[int, dict[str, int]]:
    """Normalisiert ein roh geladenes values-Dict zu {fid:int -> {attr:str -> 0..255}}."""
    result: dict[int, dict[str, int]] = {}
    if not isinstance(raw, dict):
        return result
    for fid_key, attrs in raw.items():
        try:
            fid = int(fid_key)
        except (TypeError, ValueError):
            continue
        if not isinstance(attrs, dict):
            continue
        clean: dict[str, int] = {}
        for attr, val in attrs.items():
            try:
                clean[str(attr)] = max(0, min(255, int(val)))
            except (TypeError, ValueError):
                continue
        if clean:
            result[fid] = clean
    return result


class Snap:
    """Ein benannter Programmer-Snap in der Bibliothek."""

    def __init__(self, sid: int, name: str, folder: str,
                 values: dict[int, dict[str, int]]):
        self.id: int = sid
        self.name: str = name
        self.folder: str = folder  # "" = Wurzel, "/"-getrennt verschachtelt
        self.values: dict[int, dict[str, int]] = values

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "folder": self.folder,
            "values": {str(fid): attrs for fid, attrs in self.values.items()},
        }

    @classmethod
    def from_dict(cls, d: dict, fallback_id: int) -> "Snap":
        try:
            sid = int(d.get("id", fallback_id))
        except (TypeError, ValueError):
            sid = fallback_id
        return cls(
            sid=sid,
            name=str(d.get("name") or f"Snap {sid}"),
            folder=str(d.get("folder", "") or ""),
            values=_clean_values(d.get("values", {})),
        )


class SnapLibrary:
    """Show-gebundene Sammlung von Ordnern + Snaps (in-memory, mit Show serialisiert)."""

    def __init__(self):
        self._snaps: dict[int, Snap] = {}
        self._folders: set[str] = set()  # explizite Ordnerpfade (auch leere)
        self._next_id: int = 1
        # Beim allerersten Erzeugen mit den globalen Alt-Snaps befüllen.
        self.migrate_from_disk(replace=False)

    # ── Zugriff ───────────────────────────────────────────────────────────────

    def get(self, sid: int) -> Snap | None:
        return self._snaps.get(int(sid))

    def snaps(self) -> list[Snap]:
        return list(self._snaps.values())

    def snaps_sorted(self) -> list[Snap]:
        return sorted(self._snaps.values(), key=lambda s: (s.folder.lower(), s.name.lower()))

    def folders(self) -> set[str]:
        """Alle Ordnerpfade: explizit angelegte ∪ von Snaps referenzierte."""
        result = set(self._folders)
        for s in self._snaps.values():
            if s.folder:
                result.add(s.folder)
        # Übergeordnete Pfade ergänzen (z. B. "Intros" für "Intros/Slow").
        for path in list(result):
            parts = path.split("/")
            for i in range(1, len(parts)):
                result.add("/".join(parts[:i]))
        result.discard("")
        return result

    # ── Snap-CRUD ─────────────────────────────────────────────────────────────

    def add_snap(self, name: str, folder: str,
                 values: dict[int, dict[str, int]]) -> Snap:
        sid = self._next_id
        self._next_id += 1
        snap = Snap(sid, name.strip() or f"Snap {sid}", folder or "", values)
        self._snaps[sid] = snap
        return snap

    def remove_snap(self, sid: int) -> bool:
        return self._snaps.pop(int(sid), None) is not None

    def rename_snap(self, sid: int, new_name: str) -> bool:
        snap = self._snaps.get(int(sid))
        if snap is None or not new_name.strip():
            return False
        snap.name = new_name.strip()
        return True

    def move_snap(self, sid: int, dest_folder: str) -> bool:
        snap = self._snaps.get(int(sid))
        if snap is None:
            return False
        snap.folder = dest_folder or ""
        return True

    # ── Ordner-Verwaltung ──────────────────────────────────────────────────────

    def add_folder(self, path: str) -> bool:
        path = (path or "").strip("/")
        if not path:
            return False
        self._folders.add(path)
        return True

    def rename_folder(self, old_path: str, new_name: str) -> str | None:
        """Benennt einen Ordner um und zieht Unterordner + enthaltene Snaps mit.
        Gibt den neuen Pfad zurück oder None bei Fehler."""
        new_name = (new_name or "").strip().strip("/")
        if not old_path or not new_name:
            return None
        parent, _, _ = old_path.rpartition("/")
        new_path = f"{parent}/{new_name}" if parent else new_name
        if new_path == old_path:
            return old_path
        prefix = old_path + "/"
        # Ordner-Set umschreiben
        updated: set[str] = set()
        for f in self._folders:
            if f == old_path:
                updated.add(new_path)
            elif f.startswith(prefix):
                updated.add(new_path + "/" + f[len(prefix):])
            else:
                updated.add(f)
        self._folders = updated
        # Snaps mitziehen
        for s in self._snaps.values():
            if s.folder == old_path:
                s.folder = new_path
            elif s.folder.startswith(prefix):
                s.folder = new_path + "/" + s.folder[len(prefix):]
        return new_path

    def move_folder(self, old_path: str, dest_parent: str) -> str | None:
        """Verschiebt einen Ordner UNTER ``dest_parent`` (zieht Unterordner +
        enthaltene Snaps mit). Anders als ``rename_folder`` aendert das den ELTERN-
        Ordner, nicht den Namen. ``dest_parent=""`` = in die Wurzel.

        Gibt den neuen Pfad zurueck — oder ``None``, wenn der Zug ungueltig ist
        (Ordner in sich selbst / einen eigenen Unterordner). Ein Namenskonflikt im
        Ziel fuehrt zu einer Verschmelzung (beide Inhalte landen im selben Pfad)."""
        old_path = (old_path or "").strip("/")
        dest_parent = (dest_parent or "").strip("/")
        if not old_path:
            return None
        name = old_path.rpartition("/")[2]
        new_path = f"{dest_parent}/{name}" if dest_parent else name
        if new_path == old_path:
            return old_path                      # schon dort — No-op
        # In sich selbst oder einen eigenen Unterordner schieben: verboten.
        if dest_parent == old_path or dest_parent.startswith(old_path + "/"):
            return None
        prefix = old_path + "/"
        updated: set[str] = set()
        for f in self._folders:
            if f == old_path:
                updated.add(new_path)
            elif f.startswith(prefix):
                updated.add(new_path + "/" + f[len(prefix):])
            else:
                updated.add(f)
        updated.add(new_path)                    # Ordner existiert danach garantiert
        self._folders = updated
        for s in self._snaps.values():
            if s.folder == old_path:
                s.folder = new_path
            elif s.folder.startswith(prefix):
                s.folder = new_path + "/" + s.folder[len(prefix):]
        return new_path

    def remove_folder(self, path: str) -> None:
        """Löscht einen Ordner inkl. Unterordner und enthaltener Snaps."""
        if not path:
            return
        prefix = path + "/"
        self._folders = {
            f for f in self._folders if f != path and not f.startswith(prefix)
        }
        for sid in [
            s.id for s in self._snaps.values()
            if s.folder == path or s.folder.startswith(prefix)
        ]:
            self._snaps.pop(sid, None)

    def clear(self) -> None:
        self._snaps.clear()
        self._folders.clear()
        self._next_id = 1

    # ── Serialisierung ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "folders": sorted(self._folders),
            "snaps": [s.to_dict() for s in self.snaps_sorted()],
        }

    def from_dict(self, d: dict) -> None:
        self.clear()
        if not isinstance(d, dict):
            return
        for f in d.get("folders", []) or []:
            if isinstance(f, str) and f.strip("/"):
                self._folders.add(f.strip("/"))
        max_id = 0
        for sd in d.get("snaps", []) or []:
            if not isinstance(sd, dict):
                continue
            snap = Snap.from_dict(sd, fallback_id=self._next_id)
            self._snaps[snap.id] = snap
            max_id = max(max_id, snap.id)
        self._next_id = max(self._next_id, max_id + 1)

    # ── Migration aus globalen Alt-Dateien ──────────────────────────────────────

    def migrate_from_disk(self, replace: bool = False) -> int:
        """Importiert globale Snap-Dateien aus SNAPS_DIR. Originale bleiben liegen.
        Gibt die Anzahl importierter Snaps zurück."""
        if replace:
            self.clear()
        base = Path(SNAPS_DIR)
        if not base.is_dir():
            return 0
        count = 0
        for json_path in base.rglob("*.json"):
            try:
                rel = json_path.parent.relative_to(base)
                folder = "" if str(rel) == "." else str(rel).replace(os.sep, "/")
                with open(json_path, encoding="utf-8") as f:
                    data = json.load(f)
                values = _clean_values(data.get("values", {}))
                if not values:
                    continue
                name = str(data.get("name") or json_path.stem)
                self.add_snap(name, folder, values)
                if folder:
                    self.add_folder(folder)
                count += 1
            except Exception as e:
                print(f"[snap_library] migrate skip {json_path}: {e}")
        return count


_library: SnapLibrary | None = None


def get_snap_library() -> SnapLibrary:
    global _library
    if _library is None:
        _library = SnapLibrary()
    return _library
