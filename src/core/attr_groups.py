"""Kanonische Attribut-Gruppen-Klassifikation (EINE Quelle).

Wird gemeinsam vom Programmer (Attribut-Tabs, ``programmer_view``) und vom
Speichern-Kanal-Dialog (``snap_file_panel.ChannelSelectDialog``) genutzt, damit
beide nicht auseinanderdriften. Frueher gab es zwei getrennte Maps, die bei
Shutter/Strobe widersprachen -> ein im Intensity-Tab geschobener Strobe-Kanal
wurde beim Speichern faelschlich als "Beam" beschriftet (Bug E).

Hinweis: ``palette.PaletteType.ATTR_GROUPS`` ist BEWUSST eine andere Map
(Paletten-Typen, anderer Zweck -- eine Beam-Palette enthaelt z. B. absichtlich
shutter/gobo_wheel) und bleibt separat.
"""
from __future__ import annotations

# Name -> Menge von Attribut-Namen (oder Substring-Match, siehe classify_attr).
ATTR_GROUPS: dict[str, set[str]] = {
    # Shutter/Strobe liegt bewusst bei Intensity (neben dem Dimmer,
    # Moving-Head-Initiative 2026-06-10). NICHT in eine reine Intensity-Menge
    # aufnehmen, die der Grand Master skaliert -> der Strobe darf nicht
    # grand-master-gedimmt werden (die GM-Maske ist davon unabhaengig).
    "Intensity": {"intensity", "dimmer", "master", "shutter", "strobe"},
    "Color":     {"color_r", "color_g", "color_b", "color_w", "color_a", "color_uv",
                  "cyan", "magenta", "yellow", "color_wheel", "colour_wheel", "color"},
    "Position":  {"pan", "tilt", "pan_fine", "tilt_fine"},
    "Beam":      {"zoom", "focus", "frost", "iris", "prism"},
    "Gobo":      {"gobo", "gobo_rotation", "gobo_wheel", "gobo_fx", "gobo1",
                  "gobo2", "gobo_rot"},
    "Effect":    {"macro", "effect", "effect_speed", "prism_rot", "animation"},
}

# Anzeige-/Sortierreihenfolge inkl. Auffang-Gruppe "Other".
ATTR_GROUP_ORDER: list[str] = ["Intensity", "Color", "Position", "Beam",
                               "Gobo", "Effect", "Other"]


def classify_attr(attr: str) -> str:
    """Ordnet ein Attribut einer Gruppe zu (exakt, sonst Substring). Default 'Other'."""
    a = (attr or "").lower()
    for grp, names in ATTR_GROUPS.items():
        if a in names:
            return grp
        for n in names:
            if n in a:
                return grp
    return "Other"
