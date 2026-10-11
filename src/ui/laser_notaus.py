"""LAS-36: der EINE Weg, den Laser-NOT-AUS zu loesen — immer mit Rueckfrage.

Ausloesen darf jeder (fester Knopf oben rechts, Tastenkuerzel, Knopf im
Laser-Tab, VC-Taste „Laser NOT-AUS“, Fernbedienung). Loesen geht nur hier:
``loesen_mit_rueckfrage`` fragt nach und ruft erst dann
``AppState.laser_notaus_loesen``. Kein Programmer-Wert, kein MIDI-Regler, kein
Tastenkuerzel und keine VC-Taste nimmt den Latch zurueck.

Wer einen weiteren Loese-Knopf baut (z. B. in der Virtual Console, VCB-38),
ruft diese Funktion — nie ``laser_notaus_loesen`` oder
``set_laser_estop(False)`` direkt. Der Quelltext-Waechter in
``tests/test_las36_notaus_nur_mit_rueckfrage.py`` haelt das fest.

Die Funktion gehoert in den UI-Thread am Pult: wer loest, muss den
Strahlbereich sehen koennen. Nie aus einem Fernweg (Handy, OSC, MIDI) rufen.
"""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

TITEL = "Laser-NOT-AUS lösen?"
TEXT = (
    "Der Laser-NOT-AUS ist aktiv.\n\n"
    "Der Laser gibt danach sofort wieder aus, was eingestellt ist: alles, was "
    "Programmer, Szenen und Effekte gerade vorgeben — auch Werte, die "
    "während des NOT-AUS gesetzt wurden. Netzwerk-Laser bleiben unscharf.\n\n"
    "Nur lösen, wenn der Strahlbereich frei ist. Jetzt lösen?"
)


def loesen_mit_rueckfrage(parent, state) -> bool:
    """Fragt nach und loest den NOT-AUS nur bei „Ja“. Vorgabe ist „Abbrechen“
    (Enter/Leertaste loesen nicht). Gibt True zurueck, wenn der Latch danach
    nicht mehr steht."""
    if not getattr(state, "laser_estop_active", False):
        return False
    antwort = QMessageBox.warning(
        parent, TITEL, TEXT,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Cancel)
    if antwort != QMessageBox.StandardButton.Yes:
        return False
    try:
        state.laser_notaus_loesen()
    except Exception as e:
        print(f"[laser_notaus] Laser-NOT-AUS lösen Fehler: {e}")
    return not getattr(state, "laser_estop_active", False)
