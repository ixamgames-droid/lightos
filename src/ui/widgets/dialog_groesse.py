"""FM-74: Dialog an Inhalt und Bildschirm anpassen.

Grosse Dialoge (Fixture Generator, Fixture Editor) oeffneten kleiner, als ihr
Inhalt braucht: Tabellenkopf, Knoepfe und Felder lagen uebereinander, von der
Kanaltabelle blieb eine Zeile. Drei Dinge wirkten zusammen:

1. ``setMinimumSize(900, 680)`` im Konstruktor. Ein AUSDRUECKLICH gesetztes
   Mindestmass ersetzt das Mindestmass, das das Layout sonst selbst an das
   Fenster meldet (``QLayout::activate`` uebernimmt den Bedarf des Inhalts nur
   fuer die Richtung, in der nichts gesetzt ist). Das Fenster durfte damit
   kleiner werden als sein Inhalt — und Qt schiebt die Teile dann ineinander.
2. Ohne eigenes ``resize()`` nimmt Qt beim ersten Zeigen ``sizeHint()``,
   begrenzt auf ZWEI DRITTEL des Bildschirms (``QWidget::adjustSize``). Auf
   1920 x 1080 sind das 720 px Hoehe fuer einen Inhalt, der 970 braucht.
3. Es gab keinen Rollbereich: reicht der Bildschirm wirklich nicht (1366 x
   768), konnte der Inhalt nur gequetscht werden.

Die Loesung hat zwei Teile, die zusammengehoeren:

* :class:`InhaltsRollbereich` — der Inhalt des Dialogs liegt in einem
  Rollbereich, der als Wunschgroesse den Bedarf seines Inhalts meldet. Ist das
  Fenster kleiner, erscheint ein Rollbalken; ueberlappen kann nichts mehr.
* :func:`beim_ersten_zeigen_anpassen` — setzt die Startgroesse aus dem
  ``sizeHint()`` des Dialogs (nicht aus festen Zahlen: kommt eine Reiterleiste
  dazu, waechst der Dialog mit), begrenzt auf die verfuegbare Flaeche des
  Bildschirms, auf dem das Elternfenster liegt.
"""
from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QApplication, QFrame, QHeaderView, QScrollArea,
                               QStyle, QTableView, QWidget)

#: Zeilen, die eine Kanaltabelle mindestens zeigen soll, wo der Platz reicht.
MINDESTZEILEN = 5

#: Luft zwischen Fensterrahmen und Rand der verfuegbaren Flaeche (logische px).
_LUFT = 8

_MARKE = "_fm74_angepasst"


class InhaltsRollbereich(QScrollArea):
    """Rollbereich, der so gross sein WILL wie sein Inhalt.

    ``QScrollArea.sizeHint()`` deckelt die Wunschgroesse auf rund 36 x 24
    Zeichen — ein Dialog, der seinen Inhalt in einen gewoehnlichen Rollbereich
    legt, oeffnet deshalb winzig. Hier ist die Wunschgroesse der Bedarf des
    Inhalts; das MINDESTmass bleibt klein, damit das Fenster auf einem kleinen
    Bildschirm schrumpfen darf und dann rollt.
    """

    def __init__(self, inhalt: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        # Kein eigener Hintergrund: der Rollbereich soll aussehen wie der
        # Dialog, in dem er liegt.
        self.viewport().setAutoFillBackground(False)
        inhalt.setAutoFillBackground(False)
        self.setWidget(inhalt)

    def sizeHint(self) -> QSize:
        inhalt = self.widget()
        if inhalt is None:
            return super().sizeHint()
        rand = 2 * self.frameWidth()
        bedarf = inhalt.sizeHint().expandedTo(inhalt.minimumSize())
        return bedarf + QSize(rand, rand)


def verfuegbare_flaeche(widget: QWidget | None) -> QRect:
    """Verfuegbare Flaeche (ohne Leisten, logische Pixel) des Bildschirms, auf
    dem das ELTERNFENSTER von ``widget`` liegt — dort oeffnet der Dialog. Ohne
    Elternfenster der Bildschirm des Widgets, sonst der Hauptbildschirm."""
    schirm = None
    if widget is not None:
        eltern = widget.parentWidget()
        if eltern is not None:
            schirm = eltern.window().screen()
        if schirm is None:
            schirm = widget.screen()
    if schirm is None:
        schirm = QGuiApplication.primaryScreen()
    if schirm is None:                       # kein Bildschirm (sehr frueh)
        return QRect(0, 0, 1280, 720)
    return schirm.availableGeometry()


def groesste_fenstergroesse(dialog: QWidget | None) -> QSize:
    """Groesste Fenstergroesse (ohne Rahmen), die samt Titelleiste noch auf die
    verfuegbare Flaeche passt."""
    flaeche = verfuegbare_flaeche(dialog)
    stil = dialog.style() if dialog is not None else QApplication.style()
    titel = stil.pixelMetric(QStyle.PixelMetric.PM_TitleBarHeight, None, dialog)
    return QSize(max(200, flaeche.width() - 2 * _LUFT),
                 max(150, flaeche.height() - max(0, titel) - 2 * _LUFT))


def an_inhalt_und_bildschirm_anpassen(dialog: QWidget, *,
                                      wunsch: QSize | None = None,
                                      zugabe: QSize | None = None) -> QSize:
    """Setzt die Groesse von ``dialog`` auf seinen ``sizeHint()`` plus
    ``zugabe`` — mindestens ``wunsch``, hoechstens die verfuegbare
    Bildschirmflaeche — und zieht ein zu grosses Mindestmass auf den Bildschirm
    herunter. Gibt die Groesse zurueck.

    ``zugabe`` ist Luft UEBER den Bedarf hinaus (z. B. drei Tabellenzeilen
    mehr), ``wunsch`` eine Untergrenze fuer die STARTgroesse. Beides ist kein
    Mindestmass: braucht der Inhalt mehr, gewinnt der Inhalt; ist der
    Bildschirm kleiner, gewinnt der Bildschirm.
    """
    lay = dialog.layout()
    if lay is not None:
        lay.activate()
    grenze = groesste_fenstergroesse(dialog)
    ziel = dialog.sizeHint()
    if zugabe is not None:
        ziel = ziel + zugabe
    if wunsch is not None:
        ziel = ziel.expandedTo(wunsch)
    ziel = ziel.boundedTo(grenze)
    mindest = dialog.minimumSize()
    if mindest.width() > grenze.width() or mindest.height() > grenze.height():
        dialog.setMinimumSize(mindest.boundedTo(grenze))
    dialog.resize(ziel)
    return ziel


def beim_ersten_zeigen_anpassen(dialog: QWidget, *,
                                wunsch: QSize | None = None,
                                zugabe: QSize | None = None) -> bool:
    """Fuer ``showEvent`` (VOR ``super().showEvent``, damit Qt den Dialog mit
    der endgueltigen Groesse ueber dem Elternfenster einmittet): passt die
    Groesse genau einmal an — beim ersten Zeigen, wenn der Inhalt (geladenes
    Profil, Modi) steht. Wer vorher selbst ``resize()`` gerufen hat, behaelt
    seine Groesse. Gibt zurueck, ob angepasst wurde."""
    if getattr(dialog, _MARKE, False):
        return False
    setattr(dialog, _MARKE, True)
    if dialog.testAttribute(Qt.WidgetAttribute.WA_Resized):
        return False
    an_inhalt_und_bildschirm_anpassen(dialog, wunsch=wunsch, zugabe=zugabe)
    return True


def mindestzeilen_setzen(tabelle: QTableView,
                         zeilen: int = MINDESTZEILEN) -> int:
    """Mindesthoehe einer Tabelle so, dass Kopf und ``zeilen`` Zeilen sichtbar
    sind — gerechnet aus Kopf- und Zeilenhoehe statt aus einer festen Zahl.
    Gibt die gesetzte Hoehe zurueck."""
    kopf: QHeaderView = tabelle.horizontalHeader()
    kopf_h = 0 if kopf.isHidden() else kopf.sizeHint().height()
    zeile_h = tabelle.verticalHeader().defaultSectionSize()
    hoehe = kopf_h + zeilen * zeile_h + 2 * tabelle.frameWidth()
    tabelle.setMinimumHeight(max(tabelle.minimumHeight(), hoehe))
    return tabelle.minimumHeight()
