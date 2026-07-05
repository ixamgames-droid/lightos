"""Werksmuster-Slots für DMX-Muster-Laser (LAS-18b).

Ein :class:`PatternSlot` merkt sich EIN eingebautes Werksmuster eines
Klasse-A-Lasers (z. B. Ehaho L2600) über seine rohen Kanalwerte:
``bank`` = Musterbank-Kanal (L2600 CH3, ``laser_bank``) und ``pattern`` =
Musterauswahl-Kanal (L2600 CH4, ``gobo_wheel``). Optional ein Foto
(``image_path``), das der Nutzer vom realen Laser-Output gemacht hat — die
Werksmuster sind herstellerseitig unbenannt/unbebildert (Handbuch verifiziert),
also baut sich der Nutzer seine eigene Vorschau-Bibliothek.

Rein und ohne Qt; Persistenz als additiver ``.lshow``-Block (Muster wie
``laser_figures`` aus LAS-07b).
"""
from __future__ import annotations

from dataclasses import dataclass


def _clamp255(v) -> int:
    try:
        return max(0, min(255, int(v)))
    except (TypeError, ValueError):
        return 0


@dataclass
class PatternSlot:
    """Ein gemerktes Werksmuster: Name + rohe Bank-/Muster-Kanalwerte +
    optionaler Foto-Pfad (leer = nummerierte Kachel)."""
    name: str = ""
    bank: int = 0            # Wert des Musterbank-Kanals (laser_bank)
    pattern: int = 0         # Wert des Musterauswahl-Kanals (gobo_wheel)
    image_path: str = ""     # Foto vom realen Output ("" = keins)

    def to_dict(self) -> dict:
        d = {"name": self.name, "bank": int(self.bank),
             "pattern": int(self.pattern)}
        if self.image_path:
            d["image_path"] = self.image_path
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PatternSlot":
        return cls(
            name=str(d.get("name", "") or ""),
            bank=_clamp255(d.get("bank", 0)),
            pattern=_clamp255(d.get("pattern", 0)),
            image_path=str(d.get("image_path", "") or ""))

    @property
    def label(self) -> str:
        """Anzeigename: gesetzter Name oder „B<bank>/M<pattern>"."""
        return self.name or f"B{int(self.bank)}/M{int(self.pattern)}"
