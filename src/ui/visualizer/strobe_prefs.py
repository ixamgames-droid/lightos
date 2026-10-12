"""VIZ-104: Strobe im 3D — die Python-Haelfte der Einstellung.

Wie ein Strobe in der 3D-Szene gezeigt wird, ist eine Geraete-Praeferenz
(``ui_prefs.json``, Key ``viz_strobe_mode``) — dieselbe Ablage wie die
Qualitaetsstufe: sie haengt am Menschen vor diesem Bildschirm, nicht an der
Show, die zwischen Rechnern wandert.

===========  ==========================================================
Wert         Bedeutung
===========  ==========================================================
``flash``    Blitzen (Vorgabe): kurz an, lange aus, im Takt des Shutters
``soft``     Gedaempft: langsames, flaches Pulsieren statt An/Aus
``off``      Aus: Dauerlicht wie vor VIZ-104
===========  ==========================================================

Die Rechnung selbst (Periode und Blitzlaenge in ganzen Bildern, Deckel) steht
in ``scene_src/fixtures/strobe.js`` und — fuer die 2D-Live-Ansicht — in
``src/core/strobe.py``. Die Zahlen hier sind deren Gegenstueck fuer Texte und
Tests; ``tests/test_viz104_strobe_im_3d.py`` haelt alle drei gleich.

Die Einstellung aendert AUSSCHLIESSLICH die Darstellung im 3D-Fenster. An der
DMX-Ausgabe aendert sich nichts.
"""
from __future__ import annotations

PREF_KEY = "viz_strobe_mode"
MODES = ("flash", "soft", "off")
DEFAULT_MODE = "flash"

from src.core.strobe import BILDER_JE_BLITZ, DECKEL_HZ, TAST

#: Anteil der Periode, in dem ein blitzendes Geraet leuchtet.
DUTY = TAST
#: Hoechste dargestellte Blitzfrequenz (Hz). 10, weil ein Blitz mindestens
#: FRAMES_PER_FLASH Bilder braucht: das sind 30 Bilder/s — so viel liefert der
#: bei der Sichtprobe gemessene Rechner (Intel UHD 630) beim Blitzen gerade
#: noch; die frueheren 12 Hz hat er nie erreicht (gezeigt wurden 7-10).
CAP_HZ = DECKEL_HZ
#: Eine Periode hat mindestens so viele Bilder (ein Bild an, zwei aus).
FRAMES_PER_FLASH = BILDER_JE_BLITZ
#: ``soft``: hoechste Pulsfrequenz (Hz) und dunkelster Anteil der Helligkeit.
SOFT_MAX_HZ = 2
SOFT_MIN = 0.55

#: (Wert, Beschriftung) in der Reihenfolge der Auswahlliste.
MODE_LABELS = (
    ("flash", "Blitzen"),
    ("soft", "Gedämpft (weiches Pulsieren)"),
    ("off", "Aus (Dauerlicht wie bisher)"),
)

WARNHINWEIS = (
    "Achtung: Schnelle Lichtblitze können bei photosensitiver Epilepsie\n"
    "Anfälle auslösen. Im Zweifel 'Gedämpft' oder 'Aus' wählen."
)


def normalize_mode(mode) -> str:
    """Gespeicherter/gewaehlter Wert -> ``flash``/``soft``/``off`` (Unbekanntes
    -> Vorgabe)."""
    m = str(mode or "").lower()
    return m if m in MODES else DEFAULT_MODE


def strobe_mode_pref() -> str:
    """Geraete-gebundene Einstellung aus ui_prefs.json; kaputte Prefs -> Vorgabe."""
    try:
        from src.ui.views.programmer_view import _load_prefs
        return normalize_mode(_load_prefs().get(PREF_KEY, DEFAULT_MODE))
    except Exception:
        return DEFAULT_MODE


def save_strobe_mode(mode) -> str:
    """Einstellung merken; liefert den gespeicherten (normalisierten) Wert."""
    m = normalize_mode(mode)
    from src.ui.views.programmer_view import _save_prefs
    _save_prefs({PREF_KEY: m})
    return m


def strobe_mode_value(besitzer) -> str:
    """Aktuelle Auswahl des Fensters. Modul-Funktion statt Methode: Bestandstests
    fahren ``_collect_settings`` ungebunden auf Stubs ohne dieses Feld — dann
    gilt die gespeicherte Einstellung."""
    combo = getattr(besitzer, "_combo_strobe", None)
    try:
        if combo is not None:
            return normalize_mode(combo.currentData())
    except Exception:
        pass
    return strobe_mode_pref()
