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
    # CMY-Subtraktivmischung: die REAL emittierten Namen sind cmy_c/cmy_m/cmy_y
    # (QXF-Import IntensityCyan/Magenta/Yellow -> cmy_*, Fixture-Editor
    # CHANNEL_ATTRS). "cyan/magenta/yellow" emittiert KEIN Pfad — ohne die cmy_*
    # fiele jeder importierte CMY-Mover ueber den Substring-Fallback auf 'Other'
    # (kein Color-Tab/Picker). Konsistent mit engine/palette.py (PaletteType.COLOR).
    "Color":     {"color_r", "color_g", "color_b", "color_w", "color_a", "color_uv",
                  "cmy_c", "cmy_m", "cmy_y",
                  "cyan", "magenta", "yellow", "color_wheel", "colour_wheel", "color"},
    "Position":  {"pan", "tilt", "pan_fine", "tilt_fine"},
    "Beam":      {"zoom", "focus", "frost", "iris", "prism"},
    "Gobo":      {"gobo", "gobo_rotation", "gobo_wheel", "gobo_fx", "gobo1",
                  "gobo2", "gobo_rot"},
    # "prism_rot" = synthetische Kurzform; "prism_rotation" = real emittierter
    # Name (QXF-Import, eingebauter Generic-MH) -> BEIDE exakt in Effect, damit der
    # Beam-Substring "prism" sie nicht faelschlich als Beam klassifiziert (ENG-07).
    # laser_color/laser_color_change MUESSEN exakt hier stehen, sonst zieht sie
    # der Color-Substring-Fallback in die Color-Gruppe (Range-Select-Kanaele
    # duerfen nicht vom Color-Feature-Dimmer skaliert werden).
    # "speed" (FIMP-01): ueberladenes Attribut -> gehoert exakt in Effect, sonst
    # faellt es ueber den Substring-Fallback auf 'Other' (kein Tab/Label, gleiche
    # Fallenklasse wie ENG-07). NICHT Position: die REAL emittierten "speed"-Kanaele
    # sind ueberwiegend Funktions-/Programm-Geschwindigkeit (fixture_db "Funk.Speed",
    # "Cue-Geschwindigkeit", generisch "Speed") auf NICHT-Movern (z. B. ZQ01424-PAR);
    # eine Position-Einordnung gaebe diesen PARs faelschlich eine Bewegungs-Capability
    # und wuerde den Bewegungs-Snap-Kompatibilitaetsfilter brechen (snap_editor
    # is_compatible -> test_movement_snap_excludes_par). Effect passt zu effect_speed/
    # macro und aendert deren Gruppen-Set nicht (PAR hat via "macro" schon Effect).
    # Der QXF-SpeedPanTilt*-Mover zeigt seinen Speed-Kanal damit im Effekt-Tab.
    "Effect":    {"macro", "effect", "effect_speed", "speed", "prism_rot",
                  "prism_rotation", "animation",
                  "laser_boundary", "laser_bank", "laser_x", "laser_y",
                  "laser_zoom_x", "laser_zoom_y", "laser_color",
                  "laser_color_change", "laser_dots", "laser_draw",
                  "laser_draw_mode", "laser_twist", "laser_grating",
                  "laser_scan_rate"},
}

# Anzeige-/Sortierreihenfolge inkl. Auffang-Gruppe "Other".
ATTR_GROUP_ORDER: list[str] = ["Intensity", "Color", "Position", "Beam",
                               "Gobo", "Effect", "Other"]

# Menschenlesbare Labels fuer einzelne Attribute (Kanal-Ebene). Wird vom
# Kanal-Auswahl-Dialog (Snap/Szene speichern) und vom Snap-Editor genutzt, damit
# beide dieselben Bezeichnungen zeigen. Unbekannte Attribute fallen auf den rohen
# Attribut-Namen zurueck.
ATTR_LABELS: dict[str, str] = {
    "intensity": "Intensität", "dimmer": "Dimmer", "master": "Master",
    "shutter": "Shutter", "strobe": "Strobe",
    "color_r": "Rot", "color_g": "Grün", "color_b": "Blau", "color_w": "Weiß",
    "color_a": "Amber", "color_uv": "UV",
    "cyan": "Cyan", "magenta": "Magenta", "yellow": "Gelb",
    "color_wheel": "Farbrad", "colour_wheel": "Farbrad", "color": "Farbe",
    "pan": "Pan", "tilt": "Tilt", "pan_fine": "Pan (fein)", "tilt_fine": "Tilt (fein)",
    "pan_speed": "Pan-Speed", "tilt_speed": "Tilt-Speed",
    "speed": "Speed",
    "zoom": "Zoom", "focus": "Focus", "frost": "Frost", "iris": "Iris", "prism": "Prisma",
    "prism_rot": "Prisma-Rotation", "prism_rotation": "Prisma-Rotation",
    "gobo": "Gobo", "gobo_wheel": "Gobo-Rad", "gobo_rotation": "Gobo-Rotation",
    "gobo_rot": "Gobo-Rotation", "gobo_fx": "Gobo-FX", "gobo1": "Gobo 1", "gobo2": "Gobo 2",
    "macro": "Makro", "effect": "Effekt", "effect_speed": "Effekt-Speed",
    "animation": "Animation",
    "laser_boundary": "Grenzverhalten", "laser_bank": "Musterbank",
    "laser_x": "X-Bewegung", "laser_y": "Y-Bewegung",
    "laser_zoom_x": "X-Zoom", "laser_zoom_y": "Y-Zoom",
    "laser_color": "Punktfarbe", "laser_color_change": "Muster-Farbwechsel",
    "laser_dots": "Punkte", "laser_draw": "Zeichnen-Anteil",
    "laser_draw_mode": "Zeichenmodus", "laser_twist": "Verdrehung",
    "laser_grating": "Raster", "laser_scan_rate": "Scan-Rate",
}


def attr_label(attr: str) -> str:
    """Menschenlesbares Label fuer ein Attribut, inkl. Mehrkopf-Suffix ``#N``.

    ``"color_r"`` -> ``"Rot"``; ``"color_r#1"`` -> ``"Rot (Kopf 2)"`` (Kopf 0 ist
    der Basis-Kopf ohne Suffix). Unbekannte Attribute -> roher Name.
    """
    base, sep, head = (attr or "").partition("#")
    label = ATTR_LABELS.get(base.lower(), base or attr)
    if sep and head:
        try:
            return f"{label} (Kopf {int(head) + 1})"
        except (TypeError, ValueError):
            return f"{label} (#{head})"
    return label


def classify_attr(attr: str) -> str:
    """Ordnet ein Attribut einer Gruppe zu. Erst EXAKTE Mitgliedschaft ueber ALLE
    Gruppen, dann erst Substring-Fallback ueber alle Gruppen. Default 'Other'.

    Die Zwei-Pass-Reihenfolge ist wichtig: bei einem kombinierten Durchlauf
    (exakt+Substring pro Gruppe) greift sonst ein Substring einer FRUEHEREN Gruppe,
    bevor die exakte Mitgliedschaft der richtigen Gruppe geprueft wird. Konkret:
    ``prism_rotation`` (so emittiert von QXF-Import/Generic-MH) ist exakt in Effect,
    enthaelt aber den Substring ``prism`` (Beam, steht davor) -> wurde sonst
    faelschlich als Beam klassifiziert (Snap/Szenen-Label).
    """
    a = (attr or "").lower()
    # ENG-09: Mehrkopf-Suffix (``attr#N``) vor der Klassifikation strippen. Der
    # Kopf-Index aendert die Gruppe nie, aber z. B. ``prism_rotation#1`` wuerde
    # sonst den Exact-Match (Pass 1) verfehlen und ueber den Substring ``prism``
    # faelschlich in Beam statt Effect fallen -> 2. Kopf landet im falschen
    # Snap/Szenen-Label. Gilt generell fuer ALLE Multi-Head-Attribute.
    a = a.split("#", 1)[0]
    # Pass 1: exakte Mitgliedschaft hat IMMER Vorrang (ueber alle Gruppen).
    for grp, names in ATTR_GROUPS.items():
        if a in names:
            return grp
    # Pass 2: Substring-Fallback (Gruppen-Reihenfolge entscheidet bei Mehrdeutigkeit).
    for grp, names in ATTR_GROUPS.items():
        for n in names:
            if n in a:
                return grp
    return "Other"
