"""Kurven-Bibliothek — hält benannte Fade-Kurven show-weit.

Singleton analog zum Palette-Manager (``get_curve_library()``). Eingebaute
Presets sind immer verfügbar; benutzerdefinierte Kurven werden mit der Show
gespeichert (``curves``-Block in show_file.py).
"""
from __future__ import annotations
from . import fade_curve as fc
from .fade_curve import FadeCurve


class CurveLibrary:
    def __init__(self):
        # Presets sind Built-ins (nicht löschbar), User-Kurven kommen dazu.
        self._presets: list[FadeCurve] = fc.presets()
        self._user: list[FadeCurve] = []

    # ── Zugriff ───────────────────────────────────────────────────────────────

    def presets(self) -> list[FadeCurve]:
        return list(self._presets)

    def user_curves(self) -> list[FadeCurve]:
        return list(self._user)

    def all(self) -> list[FadeCurve]:
        return self._presets + self._user

    def find(self, name: str) -> FadeCurve | None:
        for c in self.all():
            if c.name == name:
                return c
        return None

    def is_preset(self, name: str) -> bool:
        return any(c.name == name for c in self._presets)

    # ── Verwaltung ────────────────────────────────────────────────────────────

    def add(self, curve: FadeCurve) -> FadeCurve:
        """Fügt eine User-Kurve hinzu (oder ersetzt eine gleichnamige).
        Preset-Namen können nicht überschrieben werden — der Name wird
        in dem Fall eindeutig gemacht."""
        if self.is_preset(curve.name):
            curve.name = self._unique_name(curve.name)
        for i, c in enumerate(self._user):
            if c.name == curve.name:
                self._user[i] = curve
                return curve
        self._user.append(curve)
        return curve

    def remove(self, name: str) -> bool:
        if self.is_preset(name):
            return False
        before = len(self._user)
        self._user = [c for c in self._user if c.name != name]
        return len(self._user) != before

    def _unique_name(self, base: str) -> str:
        existing = {c.name for c in self.all()}
        if base not in existing:
            return base
        i = 2
        while f"{base} {i}" in existing:
            i += 1
        return f"{base} {i}"

    # ── Serialisierung (nur User-Kurven) ──────────────────────────────────────

    def to_dict(self) -> dict:
        return {"curves": [c.to_dict() for c in self._user]}

    def from_dict(self, d: dict):
        self._user.clear()
        for cd in d.get("curves", []):
            try:
                self._user.append(FadeCurve.from_dict(cd))
            except Exception:
                continue


_library: CurveLibrary | None = None


def get_curve_library() -> CurveLibrary:
    global _library
    if _library is None:
        _library = CurveLibrary()
    return _library
