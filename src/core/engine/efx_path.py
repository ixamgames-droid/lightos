"""Custom-Path-Bibliothek für EFX-Bewegungen (Pan/Tilt).

Ein ``EfxPath`` ist eine benannte Punktfolge im normierten Pan/Tilt-Raum
(0..1, x = Pan links→rechts, y = Tilt oben→unten — gleiche Orientierung wie
die EFX-Vorschau). Die Punkte werden linear oder als Catmull-Rom-Spline
verbunden; ``sample(t)`` liefert die Position bei Pfad-Fortschritt t (0..1)
**bogenlängen-parametrisiert**, d. h. die Bewegung läuft mit konstanter
Geschwindigkeit, egal wie ungleich die Punktabstände sind.

Die ``EfxPathLibrary`` ist ein Singleton analog zur CurveLibrary
(``get_efx_path_library()``) und wird mit der Show gespeichert
(``efx_paths``-Block in show_file.py).
"""
from __future__ import annotations

import math
import uuid


def _catmull_rom(p0, p1, p2, p3, s: float) -> tuple[float, float]:
    """Catmull-Rom-Interpolation zwischen p1 und p2 (s in 0..1)."""
    s2 = s * s
    s3 = s2 * s
    return (
        0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * s
               + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * s2
               + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * s3),
        0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * s
               + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * s2
               + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * s3),
    )


class EfxPath:
    """Benannter Custom Path (Punktliste + Interpolationsmodus)."""

    MODES = ("linear", "spline")

    def __init__(self, name: str = "Pfad",
                 points: list[tuple[float, float]] | None = None,
                 mode: str = "linear",
                 closed: bool = True,
                 path_id: str | None = None):
        self.id: str = path_id or uuid.uuid4().hex[:12]
        self.name = name
        self.points: list[tuple[float, float]] = [
            (float(x), float(y)) for x, y in (points or [])
        ]
        self.mode = mode if mode in self.MODES else "linear"
        self.closed = bool(closed)
        # Bogenlängen-Tabelle (lazy, nach jeder Änderung via invalidate() neu)
        self._tbl_pts: list[tuple[float, float]] | None = None
        self._tbl_cum: list[float] | None = None

    # ── Bearbeitung ───────────────────────────────────────────────────────────

    def invalidate(self):
        """Nach Punkt-/Modus-Änderungen aufrufen — verwirft die Sampling-Tabelle."""
        self._tbl_pts = None
        self._tbl_cum = None

    # ── Sampling ──────────────────────────────────────────────────────────────

    def _segment_count(self) -> int:
        n = len(self.points)
        if n < 2:
            return 0
        return n if self.closed else n - 1

    def _point_at_param(self, s: float) -> tuple[float, float]:
        """Roher Kurvenpunkt bei Parameter s (0..1, NICHT bogenlängen-korrigiert)."""
        pts = self.points
        n = len(pts)
        if n == 0:
            return (0.5, 0.5)
        if n == 1:
            return pts[0]
        segs = self._segment_count()
        s = max(0.0, min(1.0, s))
        f = s * segs
        i = min(segs - 1, int(f))
        local = f - i
        if self.mode == "spline" and n >= 3:
            if self.closed:
                p0 = pts[(i - 1) % n]
                p1 = pts[i % n]
                p2 = pts[(i + 1) % n]
                p3 = pts[(i + 2) % n]
            else:
                p0 = pts[max(0, i - 1)]
                p1 = pts[i]
                p2 = pts[min(n - 1, i + 1)]
                p3 = pts[min(n - 1, i + 2)]
            return _catmull_rom(p0, p1, p2, p3, local)
        # linear (oder zu wenige Punkte für einen Spline)
        a = pts[i % n]
        b = pts[(i + 1) % n]
        return (a[0] + (b[0] - a[0]) * local, a[1] + (b[1] - a[1]) * local)

    def _ensure_table(self):
        if self._tbl_pts is not None:
            return
        steps = max(64, 24 * max(1, len(self.points)))
        pts = [self._point_at_param(i / steps) for i in range(steps + 1)]
        cum = [0.0]
        for i in range(1, len(pts)):
            dx = pts[i][0] - pts[i - 1][0]
            dy = pts[i][1] - pts[i - 1][1]
            cum.append(cum[-1] + math.hypot(dx, dy))
        self._tbl_pts = pts
        self._tbl_cum = cum

    def sample(self, t: float) -> tuple[float, float]:
        """Position bei Fortschritt t (0..1), konstante Geschwindigkeit.

        t außerhalb 0..1 wird geklemmt (Loop-/Phasen-Logik liegt beim EFX).
        """
        if not self.points:
            return (0.5, 0.5)
        if len(self.points) == 1:
            return self.points[0]
        self._ensure_table()
        pts, cum = self._tbl_pts, self._tbl_cum
        if pts is None or cum is None:  # _ensure_table garantiert beides
            return self.points[0]
        total = cum[-1]
        if total <= 0.0:
            return pts[0]
        t = max(0.0, min(1.0, float(t)))
        target = t * total
        # Binäre Suche über die kumulierten Längen
        lo, hi = 0, len(cum) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if cum[mid] < target:
                lo = mid + 1
            else:
                hi = mid
        i = max(1, lo)
        seg = cum[i] - cum[i - 1]
        frac = 0.0 if seg <= 0.0 else (target - cum[i - 1]) / seg
        a, b = pts[i - 1], pts[i]
        return (a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac)

    # ── Serialisierung ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "mode": self.mode,
            "closed": self.closed,
            "points": [[float(x), float(y)] for x, y in self.points],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EfxPath":
        return cls(
            name=str(d.get("name", "Pfad")),
            points=[(float(p[0]), float(p[1])) for p in d.get("points", [])
                    if isinstance(p, (list, tuple)) and len(p) >= 2],
            mode=str(d.get("mode", "linear")),
            closed=bool(d.get("closed", True)),
            path_id=str(d.get("id")) if d.get("id") else None,
        )


class EfxPathLibrary:
    """Show-weite Sammlung der Custom Paths (analog CurveLibrary)."""

    def __init__(self):
        self._paths: list[EfxPath] = []

    def all(self) -> list[EfxPath]:
        return list(self._paths)

    def find(self, path_id: str | None) -> EfxPath | None:
        if not path_id:
            return None
        for p in self._paths:
            if p.id == path_id:
                return p
        return None

    def find_by_name(self, name: str) -> EfxPath | None:
        for p in self._paths:
            if p.name == name:
                return p
        return None

    def add(self, path: EfxPath) -> EfxPath:
        """Fügt einen Pfad hinzu; gleiche id ersetzt (Update), gleicher Name
        eines ANDEREN Pfads wird eindeutig gemacht."""
        for i, p in enumerate(self._paths):
            if p.id == path.id:
                if any(o.name == path.name and o.id != path.id for o in self._paths):
                    path.name = self._unique_name(path.name, skip_id=path.id)
                self._paths[i] = path
                return path
        if any(p.name == path.name for p in self._paths):
            path.name = self._unique_name(path.name)
        self._paths.append(path)
        return path

    def remove(self, path_id: str) -> bool:
        before = len(self._paths)
        self._paths = [p for p in self._paths if p.id != path_id]
        return len(self._paths) != before

    def _unique_name(self, base: str, skip_id: str | None = None) -> str:
        existing = {p.name for p in self._paths if p.id != skip_id}
        if base not in existing:
            return base
        i = 2
        while f"{base} {i}" in existing:
            i += 1
        return f"{base} {i}"

    # ── Serialisierung ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {"paths": [p.to_dict() for p in self._paths]}

    def from_dict(self, d: dict):
        self._paths.clear()
        for pd in (d or {}).get("paths", []):
            try:
                self._paths.append(EfxPath.from_dict(pd))
            except Exception:
                continue


_library: EfxPathLibrary | None = None


def get_efx_path_library() -> EfxPathLibrary:
    global _library
    if _library is None:
        _library = EfxPathLibrary()
    return _library
