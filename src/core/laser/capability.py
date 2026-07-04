"""Laser-Fähigkeitsklassifikator (LAS-12).

Eine einzige Stelle entscheidet je gepatchtem Fixture, WAS mit einer gemalten
Figur passiert und ob die Zeichen-UI überhaupt eine echte Ausgabe verspricht.
Damit bleiben Zeichen-Studio, Muster-Abruf und VC-Steuerung konsistent —
Davids Vorgabe: „die Zeichen-UI existiert, aber nur für Laser, die so etwas
speichern/anzeigen können."

Klassen (aus der Hardware-Recherche, siehe SecondBrain
``project_laser_support_2026_07_02`` / Verdikt-Workflow):

- **A — BUILTIN_DMX**: reiner Werksmuster-DMX-Laser (z. B. Ehaho L2600). Kann
  über DMX nur seine fest eingebauten Muster abrufen und transformieren. Eine
  beliebige Freihand-Figur ist über DMX **physikalisch nicht** ausgebbar
  (DMX ~44 Hz gegen ~20 000–30 000 Punkte/s nötig; der Chart hat keinen
  Per-Punkt-Galvo-Kanal, das Gerät keinen Upload-Weg).
- **B — NET_STREAM**: Netzwerk-/ILDA-Punktstrom-Laser (Ether Dream, IDN). Die
  gemalte Figur wird als echter Punktstrom **exakt** ausgegeben (Pfad
  ``LaserOutputManager.set_figure``).
- **C — DMX_UPLOAD**: DMX-Laser mit Datei-Upload (SD/ILDA, ShowNET-Klasse).
  Figur wird als ``.ild``-Datei aufs Gerät geladen, DMX triggert sie. Es gibt
  noch keinen Fixture-Marker dafür → aktuell nicht auto-erkannt; der
  Erweiterungspunkt ist unten dokumentiert.

Rein und ohne Qt — testbar ohne UI. Klassifiziert allein aus ``protocol`` und
der Laser-Erkennung.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.core.app_state import LASER_NETWORK_PROTOCOLS


class LaserClass(Enum):
    """Fähigkeitsklasse eines Lasers (siehe Modul-Docstring)."""
    BUILTIN_DMX = "A"
    NET_STREAM = "B"
    DMX_UPLOAD = "C"


@dataclass(frozen=True)
class LaserCapability:
    """Was ein Laser mit einer gemalten Figur tun kann."""
    laser_class: LaserClass
    can_render_freeform: bool   # beliebige gemalte Figur 1:1 ausgebbar?
    figure_output: str          # "exact_stream" | "sd_upload" | "builtin_only"
    label: str                  # kurzes, ehrliches UI-Label


# Vorgefertigte Fähigkeiten je Klasse (Label bewusst ehrlich, kein
# Über-Versprechen). Instanzen sind unveränderlich und wiederverwendbar.
_CAP_NET = LaserCapability(
    LaserClass.NET_STREAM, True, "exact_stream",
    "Netzwerk-Laser — gemalte Figur wird exakt ausgegeben.")
_CAP_BUILTIN = LaserCapability(
    LaserClass.BUILTIN_DMX, False, "builtin_only",
    "DMX-Muster-Laser — nur eingebaute Werksmuster (keine freie Zeichnung).")


def is_laser_fixture(fx) -> bool:
    """True, wenn das gepatchte Gerät als Laser steuerbar ist — entweder per
    ``fixture_type == 'laser'`` oder weil es ``laser_*``-Kanäle besitzt. Die
    kanonische Fassung; die UI (``laser_view.fixture_has_laser_capability``)
    delegiert hierher."""
    if (getattr(fx, "fixture_type", "") or "").lower() == "laser":
        return True
    try:
        from src.core.app_state import get_channels_for_patched
        channels = get_channels_for_patched(fx)
    except Exception:
        return False
    return any((getattr(ch, "attribute", "") or "").startswith("laser_")
               for ch in channels)


def laser_capability(fx):
    """Fähigkeit eines gepatchten Lasers als :class:`LaserCapability` — oder
    ``None``, wenn ``fx`` gar kein Laser ist. Klassifiziert allein aus dem
    Ausgabe-``protocol`` (plus Laser-Erkennung)."""
    if not is_laser_fixture(fx):
        return None
    protocol = (getattr(fx, "protocol", "") or "").lower()
    if protocol in LASER_NETWORK_PROTOCOLS:
        return _CAP_NET
    # Erweiterungspunkt Klasse C (DMX_UPLOAD): sobald ein Fixture einen
    # SD-/ILDA-Upload-Weg kennzeichnet (eigenes Protokoll oder Profil-Flag),
    # hier auf `_CAP_UPLOAD` abbilden. Der L2600 hat keinen solchen Weg.
    return _CAP_BUILTIN
