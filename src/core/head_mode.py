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

Bewusst ein **Leaf-Modul OHNE Projekt-Importe**: die drei Schreibpfade — Show-
Persistenz (``core.show.show_file``), Live-Schreibpfad/Undo (``core.app_state``)
und das Spalten-Modell (``core.database.models``) — muessen es zyklenfrei
importieren koennen. (Zusaetzlich stubben Tests das ``models``-Modul aus; ein
Normalisierer dort waere aus ``show_file`` heraus nicht importierbar.)
"""
from __future__ import annotations

HEAD_MODES = ("auto", "heads", "single")


def normalize_head_mode(value) -> str:
    """Beliebigen Eingabewert auf einen gueltigen ``head_mode`` klemmen.

    Unbekannt/fehlend/leer -> ``"auto"`` (= Bestandsverhalten). Damit koennen
    weder Alt-Shows ohne den Schluessel noch Garbage aus Skript-/Remote-Pfaden
    einen ungueltigen Wert in die Spalte bringen."""
    v = str(value or "auto").strip().lower()
    return v if v in HEAD_MODES else "auto"
