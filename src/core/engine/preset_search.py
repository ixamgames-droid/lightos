"""Preset-Browser-Suche (UI-01).

Qt-freie Filterlogik für den Preset-Browser: normalisiert Paletten und
Fixture-Gruppen zu einheitlichen ``PresetEntry``-Einträgen und filtert sie per
Suchbegriff. Bewusst ohne UI-/DB-Abhängigkeit, damit die Logik headless
testbar bleibt — die View baut die Einträge und ruft nur ``filter_entries``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class PresetEntry:
    """Ein durchsuchbarer Treffer: eine Palette ODER eine Fixture-Gruppe."""
    kind: str                       # "palette" | "group"
    name: str
    subtitle: str = ""              # Typ-Label / Ordner / Geräteanzahl
    tags: tuple[str, ...] = ()
    ref: Any = None                 # Original-Palette bzw. Gruppenname (zum Anwenden)

    def haystack(self) -> str:
        """Kleingeschriebener Suchtext über Name, Untertitel, Art und Tags."""
        parts = [self.name, self.subtitle, self.kind, *self.tags]
        return " ".join(p for p in parts if p).lower()


def palette_entries(palettes: Iterable[Any]) -> list[PresetEntry]:
    """Paletten → Einträge (Untertitel = Typ-Label · Ordner)."""
    out: list[PresetEntry] = []
    for p in palettes:
        tlabel = getattr(getattr(p, "type", None), "value", "") or ""
        folder = getattr(p, "folder", "") or ""
        subtitle = " · ".join(x for x in (tlabel, folder) if x)
        tags = tuple(str(t) for t in (getattr(p, "tags", None) or []))
        out.append(PresetEntry("palette", getattr(p, "name", "") or "",
                               subtitle, tags, ref=p))
    return out


def group_entries(groups: Iterable[Any]) -> list[PresetEntry]:
    """Fixture-Gruppen → Einträge. ``groups`` sind Dicts
    ``{"name", "folder", "fids"}`` oder Tupel ``(name, folder, fids)``."""
    out: list[PresetEntry] = []
    for g in groups:
        if isinstance(g, dict):
            name = g.get("name", "") or ""
            folder = g.get("folder", "") or ""
            fids = g.get("fids", []) or []
        else:
            name, folder, fids = g
            name, folder, fids = (name or ""), (folder or ""), (fids or [])
        n = len(fids)
        subtitle = " · ".join(x for x in (folder, f"{n} Geräte") if x)
        out.append(PresetEntry("group", name, subtitle, (), ref=name))
    return out


def build_entries(palettes: Iterable[Any], groups: Iterable[Any]) -> list[PresetEntry]:
    """Paletten + Gruppen zu einer gemeinsamen Trefferliste zusammenführen."""
    return palette_entries(palettes) + group_entries(groups)


def filter_entries(query: str, entries: Iterable[PresetEntry]) -> list[PresetEntry]:
    """Filtert Einträge: jeder Whitespace-getrennte Begriff muss (als Teilstring,
    case-insensitiv) im Suchtext vorkommen (UND-Verknüpfung). Leere Suche =
    alle Einträge, Reihenfolge unverändert."""
    terms = (query or "").strip().lower().split()
    items = list(entries)
    if not terms:
        return items
    return [e for e in items if all(t in e.haystack() for t in terms)]
