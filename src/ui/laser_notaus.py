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

from PySide6.QtWidgets import QMessageBox as _QtMessageBox

TITEL = "Laser-NOT-AUS lösen?"
TEXT = (
    "Der Laser-NOT-AUS ist aktiv.\n\n"
    "Der Laser gibt danach sofort wieder aus, was eingestellt ist: alles, was "
    "Programmer, Szenen und Effekte gerade vorgeben — auch Werte, die "
    "während des NOT-AUS gesetzt wurden. Netzwerk-Laser bleiben unscharf.\n\n"
    "Nur lösen, wenn der Strahlbereich frei ist. Jetzt lösen?"
)

#: LAS-40: feste Knopftexte (wie in der Anleitung Laser). Ohne sie nimmt Qt
#: die Texte vom Betriebssystem — je nach Sprache/Oberflaeche „Ja“, „Yes“ …,
#: und ein blosses „Ja“ sagt an dieser Stelle nicht, was es ausloest.
KNOPF_LOESEN = "NOT-AUS lösen"
KNOPF_ABBRECHEN = "Abbrechen"


class QMessageBox(_QtMessageBox):          # noqa: F811 — bewusst derselbe Name
    """LAS-40: ``warning`` mit FESTEN Beschriftungen — das Muster aus UI-92
    (``main_window.QMessageBox.question``).

    Als Unterklasse unter demselben Namen, damit die Stelle, an der Tests die
    Antwort einsetzen (``laser_notaus.QMessageBox.warning``), dieselbe bleibt.
    Der Knopf „NOT-AUS lösen“ ist weiter ``StandardButton.Yes``; Vorgabe,
    Escape-Knopf und Fokus sind „Abbrechen“ — Eingabetaste, Escape und
    Leertaste loesen nie."""

    FESTE_TEXTE = (
        (_QtMessageBox.StandardButton.Yes, KNOPF_LOESEN),
        (_QtMessageBox.StandardButton.Cancel, KNOPF_ABBRECHEN),
    )

    @staticmethod
    def warning(parent, title, text,
                buttons=_QtMessageBox.StandardButton.Ok,
                defaultButton=_QtMessageBox.StandardButton.NoButton):
        box = _QtMessageBox(_QtMessageBox.Icon.Warning, title, text, buttons, parent)
        for knopf, beschriftung in QMessageBox.FESTE_TEXTE:
            b = box.button(knopf)
            if b is not None:
                b.setText(beschriftung)
        abbrechen = box.button(_QtMessageBox.StandardButton.Cancel)
        if abbrechen is not None:
            box.setEscapeButton(abbrechen)
        if defaultButton != _QtMessageBox.StandardButton.NoButton:
            box.setDefaultButton(defaultButton)
            vorgabe = box.button(defaultButton)
            if vorgabe is not None:
                vorgabe.setFocus()
        return _QtMessageBox.StandardButton(box.exec())


def loesen_mit_rueckfrage(parent, state) -> bool:
    """Fragt nach und loest den NOT-AUS nur bei „NOT-AUS lösen“. Vorgabe ist
    „Abbrechen“ (Enter/Escape/Leertaste loesen nicht). Gibt True zurueck, wenn der Latch danach
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
