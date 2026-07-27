"""EINE Quelle fuer den Mehrkopf-Programmiermodus (``PatchedFixture.head_mode``).

FM-HEADLAYOUT: legt fest, WIE ein Mehrkopf-Geraet (Spider/Mover-Bar/Hydrabeam)
programmiert wird — insbesondere, ob beim Patchen automatisch die Pro-Kopf-
Matrix-Gruppe („… · Köpfe", ``AppState.create_head_matrix_group``) entsteht:

* ``"auto"``   – Bestandsverhalten: die Gruppe wird automatisch angelegt (DEFAULT,
  damit Alt-Shows sich exakt wie bisher verhalten).
* ``"heads"``  – Koepfe einzeln: die Kopf-Matrix SOLL existieren (wird beim
  Speichern idempotent angelegt/wiederhergestellt).
* ``"single"`` – als EINE Lampe: keine automatische Kopf-Matrix.

Der Modus loescht NIE eine bestehende Gruppe — ``"single"`` verhindert nur das
automatische Neuanlegen.

Slice 2 (2026-07-27): derselbe Modus steuert die **Programmer-Farbregler** eines
Mehrkopf-Geraets — ``effective_color_head_mode`` unten ist die EINE Quelle fuer
die Vorrang-Regel „Pro-Fixture-Wahl schlaegt die globale Voreinstellung".

Bewusst ein **Leaf-Modul OHNE Projekt-Importe**: die drei Schreibpfade — Show-
Persistenz (``core.show.show_file``), Live-Schreibpfad/Undo (``core.app_state``)
und das Spalten-Modell (``core.database.models``) — muessen es zyklenfrei
importieren koennen. (Zusaetzlich stubben Tests das ``models``-Modul aus; ein
Normalisierer dort waere aus ``show_file`` heraus nicht importierbar.)
"""
from __future__ import annotations

HEAD_MODES = ("auto", "heads", "single")

# Der GLOBALE Programmer-Umschalter fuer Mehrkopf-Farbregler (ui_prefs
# "programmer_color_head_mode"): ein Regler je Farbe fuer alle Koepfe ("sync")
# oder einer je Kopf ("separate").
COLOR_HEAD_MODES = ("sync", "separate")


def normalize_head_mode(value) -> str:
    """Beliebigen Eingabewert auf einen gueltigen ``head_mode`` klemmen.

    Unbekannt/fehlend/leer -> ``"auto"`` (= Bestandsverhalten). Damit koennen
    weder Alt-Shows ohne den Schluessel noch Garbage aus Skript-/Remote-Pfaden
    einen ungueltigen Wert in die Spalte bringen."""
    v = str(value or "auto").strip().lower()
    return v if v in HEAD_MODES else "auto"


def normalize_color_head_mode(value) -> str:
    """Globalen Farb-Kopf-Modus klemmen; unbekannt/fehlend -> ``"sync"``
    (Bestands-Default des Programmers)."""
    v = str(value or "sync").strip().lower()
    return v if v in COLOR_HEAD_MODES else "sync"


def effective_color_head_mode(fixture_head_mode, global_pref="sync") -> str:
    """FM-HEADLAYOUT Slice 2: Welcher Farb-Kopf-Modus gilt fuer DIESES Fixture?

    Der Pro-Fixture-Modus (Patch-Dialog „Mehrkopf-Programmierung", Spalte
    ``PatchedFixture.head_mode``) **schlaegt** die globale Programmer-
    Voreinstellung, weil er eine Eigenschaft des GERAETS am realen Rig ist
    („die vier Koepfe sind vier Lampen" / „das ist eine Lampe"), keine
    Ansichts-Vorliebe:

    * ``"single"`` -> ``"sync"``     — als EINE Lampe programmieren.
    * ``"heads"``  -> ``"separate"`` — Koepfe einzeln programmieren.
    * ``"auto"``   -> ``global_pref`` — Bestandsverhalten: der globale
      Umschalter im Color-Tab entscheidet (Default ``"sync"``).

    Reine Funktion (Leaf-Modul), damit UI, Tests und spaetere Konsumenten
    (Matrix-/EFX-/VC-Kopfwahl) EINE Quelle fuer die Vorrang-Regel haben."""
    mode = normalize_head_mode(fixture_head_mode)
    if mode == "single":
        return "sync"
    if mode == "heads":
        return "separate"
    return normalize_color_head_mode(global_pref)
