"""Ein Layout leeren, ohne tote Layout-Eintraege in PySide zurueckzulassen (STAB-36).

Hintergrund (PySide6 6.11, gemessen): ``layout.itemAt(i)`` liefert einen
Python-Wrapper fuer den Layout-Eintrag (``QWidgetItem``), den PySide als KIND
des Layouts fuehrt — er lebt also weiter, auch wenn die Python-Variable laengst
weg ist. Loescht man danach nur das Widget (``itemAt(i).widget().deleteLater()``),
raeumt Qt den Eintrag beim verzoegerten Loeschen selbst ab, und PySide erfaehrt
davon nichts: der Wrapper bleibt „gueltig“ auf freigegebenem Speicher und unter
dessen Adresse eingetragen.

Legt Qt spaeter ein anderes, in Python erzeugtes Objekt (Widget, Listen- oder
Tabellenzeile, Layout …) an genau diese Adresse, findet PySide beim Abbau dieses
Objekts den ALTEN Wrapper und gibt ihn frei, waehrend es ihn noch benutzt —
``free(): invalid pointer`` bzw. Speicherzugriffsfehler an einer voellig anderen
Stelle (wo gerade eine Liste geleert oder ein Reiter neu gebaut wird).

Sicher ist: den Eintrag AUS dem Layout nehmen, solange sein Wrapper bekannt ist.
``takeAt`` loest ihn aus der Eltern-Beziehung und uebergibt ihn Python; mit dem
letzten Verweis wird der Eintrag ordentlich geloescht und ausgetragen.
"""
from __future__ import annotations

__all__ = ["layout_leeren"]


def layout_leeren(layout) -> None:
    """Alle Eintraege aus ``layout`` entfernen; Widgets werden versteckt und
    verzoegert geloescht, Abstandhalter und Unter-Layouts mit abgeraeumt."""
    if layout is None:
        return
    for i in reversed(range(layout.count())):
        # Erst ansehen, dann herausnehmen: ``takeAt`` liefert DENSELBEN Wrapper
        # und macht Python zum Besitzer — der Eintrag wird mit ``del`` unten
        # wirklich geloescht (ein frischer ``takeAt``-Wrapper besaesse ihn
        # nicht, der Eintrag bliebe als Speicherrest liegen).
        item = layout.itemAt(i)
        if item is None:
            continue
        widget = item.widget()
        unter = item.layout()
        layout.takeAt(i)
        if widget is not None:
            # Bis das verzoegerte Loeschen greift, bliebe das Widget an alter
            # Stelle sichtbar (vgl. UI-64a).
            widget.hide()
            widget.deleteLater()
        elif unter is not None:
            layout_leeren(unter)
            unter.deleteLater()
        del item
