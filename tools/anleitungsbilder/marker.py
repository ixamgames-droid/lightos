"""DOC-16: Markierungen fuer Anleitungsbilder — roter Rahmen + Nummernkreis.

Gezeichnet wird direkt mit QPainter auf das gegrabbte QPixmap, also in echten
Widget-Koordinaten (``widget.mapTo(quelle, …)``) statt nachtraeglich in einem
Bildprogramm. Benennt jemand einen Knopf um, findet der Runner ihn nicht mehr
und bricht ab — die Markierung kann nicht still an die falsche Stelle rutschen.

**Lage des Nummernkreises** (Review-Befund: ein fest an die linke obere Ecke
gesetzter Kreis landete oft auf einem NACHBAR-Bedienelement und wirkte wie
dessen Nummer). :func:`platzieren` probiert Kandidaten rund um den Rahmen —
aussen links, rechts, oben, unten, die Ecken, dieselben Seiten weiter weg (dann
mit kurzer Verbindungslinie zum Rahmen), zuletzt innen — und nimmt den ersten,
der

* ganz im Bild liegt,
* keinen fremden beschrifteten Bereich verdeckt (Knoepfe, Beschriftungen,
  Eingabefelder, Reiter, Listen-/Baum-/Tabelleneintraege, Menuepunkte — s.
  :func:`hindernisse`) und
* keinen anderen Rahmen und keinen anderen Kreis beruehrt.

Eine in der Szene angegebene Lage (``links``/``rechts``/``oben``/``unten``)
wird zuerst probiert, bei einer Kollision aber verworfen. :func:`platzieren`
ist reine Geometrie (nur ``QRect``/``QPoint``) und ohne App testbar.
"""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen

ROT = QColor(230, 30, 30)
_RADIUS = 13
_RAND = 4
LAGEN = ("links", "rechts", "oben", "unten")
# Abstand Kreisrand -> Rahmenlinie. Der erste Wert ist „haengt direkt dran",
# ab dem zweiten zeichnet :func:`zeichnen` eine Verbindungslinie.
_ABSTAENDE = (3, 14, 28, 46, 70)


def _geklemmt(c: QPoint, r: int, breite: int, hoehe: int) -> QPoint:
    """Kreis-Mittelpunkt so verschieben, dass der Kreis ganz im Bild liegt
    (in der ersten Probe war die „1" am linken Rand halb abgeschnitten)."""
    x = min(max(c.x(), r + 2), breite - r - 2)
    y = min(max(c.y(), r + 2), hoehe - r - 2)
    return QPoint(x, y)


def rahmen_von(rect: QRect, breite: int, hoehe: int) -> QRect:
    """Gezeichneter Rahmen um ``rect`` (etwas groesser, ins Bild geklemmt)."""
    return rect.adjusted(-_RAND, -_RAND, _RAND, _RAND).intersected(
        QRect(1, 1, breite - 2, hoehe - 2))


def _kreisfeld(c: QPoint, r: int = _RADIUS) -> QRect:
    """Quadrat um den Kreis samt weissem Rand — die Flaeche, die er belegt."""
    return QRect(c.x() - r - 2, c.y() - r - 2, 2 * r + 5, 2 * r + 5)


def _flaeche(r: QRect) -> int:
    return max(0, r.width()) * max(0, r.height())


def _seiten_punkte(rahmen: QRect, lage: str, abstand: int, r: int,
                   dicht: bool = False):
    """Mittelpunkte an einer Seite: erst mittig, dann an beiden Enden; mit
    ``dicht`` zusaetzlich in kleinen Schritten entlang der Seite (fuer weiter entfernte
    Plaetze, deren Verbindungslinie eine Luecke zwischen zwei Elementen
    treffen muss)."""
    d = abstand + r
    m = rahmen.center()
    if lage in ("links", "rechts"):
        a, b, mitte = rahmen.top(), rahmen.bottom(), m.y()
    else:
        a, b, mitte = rahmen.left(), rahmen.right(), m.x()
    werte = [mitte]
    if b - a > 4 * r:
        werte += [a + r + 2, b - r - 2]
    if dicht:
        # Auch ueber die Ecken hinaus: die Linie laeuft dann schraeg zur Ecke.
        rand = abstand + r
        werte += list(range(a - rand, b + rand + 1, max(3, (b - a) // 40)))
    if lage in ("links", "rechts"):
        x = rahmen.left() - d if lage == "links" else rahmen.right() + d
        return [QPoint(x, y) for y in werte]
    y = rahmen.top() - d if lage == "oben" else rahmen.bottom() + d
    return [QPoint(x, y) for x in werte]


def kandidaten(rahmen: QRect, vorzug: str | None = None, r: int = _RADIUS):
    """Kandidaten-Mittelpunkte in Probier-Reihenfolge -> ``[(QPoint, aussen)]``."""
    aus: list[tuple[QPoint, bool]] = []
    gesehen: set[tuple[int, int]] = set()

    def dazu(punkte, aussen=True):
        for p in punkte:
            if (p.x(), p.y()) not in gesehen:
                gesehen.add((p.x(), p.y()))
                aus.append((p, aussen))
    nah = _ABSTAENDE[0]
    if vorzug in LAGEN:
        dazu(_seiten_punkte(rahmen, vorzug, nah, r, dicht=True))
    for lage in LAGEN:
        dazu(_seiten_punkte(rahmen, lage, nah, r)[:1])
    # Ecken: Kreis diagonal ueber der Rahmenecke (der bisherige Platz).
    k = r - 5
    dazu([QPoint(rahmen.left() - k, rahmen.top() - k),
          QPoint(rahmen.right() + k, rahmen.top() - k),
          QPoint(rahmen.left() - k, rahmen.bottom() + k),
          QPoint(rahmen.right() + k, rahmen.bottom() + k)])
    for lage in LAGEN:
        dazu(_seiten_punkte(rahmen, lage, nah, r, dicht=True))
    for abstand in _ABSTAENDE[1:]:
        reihe = ([vorzug] if vorzug in LAGEN else []) + list(LAGEN)
        for lage in reihe:
            dazu(_seiten_punkte(rahmen, lage, abstand, r, dicht=True))
    # Zuletzt innen: Ecken, dann Seitenmitten.
    i = r + 4
    m = rahmen.center()
    dazu([QPoint(rahmen.left() + i, rahmen.top() + i),
          QPoint(rahmen.right() - i, rahmen.top() + i),
          QPoint(rahmen.left() + i, rahmen.bottom() - i),
          QPoint(rahmen.right() - i, rahmen.bottom() - i),
          QPoint(rahmen.left() + i, m.y()), QPoint(rahmen.right() - i, m.y()),
          QPoint(m.x(), rahmen.top() + i), QPoint(m.x(), rahmen.bottom() - i)],
         aussen=False)
    return aus


def _anteil(a: QRect, b: QRect) -> float:
    """Wie viel von ``a`` liegt in ``b`` (0…1)?"""
    s = a.intersected(b)
    return _flaeche(s) / _flaeche(a) if not s.isEmpty() and _flaeche(a) else 0.0


def _eigene(ziel: QRect, h: QRect) -> bool:
    """Gehoert der beschriftete Bereich ``h`` zum markierten Element selbst?
    (liegt ueberwiegend darin — oder das Ziel ueberwiegend in ihm)."""
    return _anteil(h, ziel) >= 0.5 or _anteil(ziel, h) >= 0.5


def _linienkosten(c: QPoint, rahmen: QRect, r: int, hindernisse) -> int:
    """Wie viele Punkte der Verbindungslinie (Kreisrand -> Rahmen) liegen auf
    einem beschrifteten Bereich oder einem fremden Rahmen?"""
    ziel = _naechster_punkt(rahmen, c)
    dx, dy = ziel.x() - c.x(), ziel.y() - c.y()
    laenge = (dx * dx + dy * dy) ** 0.5
    if laenge - r <= 5:                        # haengt direkt dran, keine Linie
        return 0
    kosten = 0
    t = float(r)
    while t < laenge:
        p = QPoint(round(c.x() + dx * t / laenge), round(c.y() + dy * t / laenge))
        kosten += sum(1 for h in hindernisse if h.contains(p))
        t += 2.0
    return kosten


def platzieren(ziele, breite: int, hoehe: int, hindernisse=(), vorzuege=None,
               r: int = _RADIUS):
    """Kreis-Mittelpunkte fuer alle Markierungen.

    ``ziele``: markierte Rechtecke (ohne Rahmenzugabe) in Bildkoordinaten;
    ``hindernisse``: beschriftete Bereiche, die kein Kreis verdecken darf;
    ``vorzuege``: je Ziel ``None`` oder eine Lage aus :data:`LAGEN`.
    Rueckgabe je Ziel ``(mittelpunkt, verbindungslinie, gefunden)``.

    Reihenfolge der Wahl: (1) der erste Platz aussen, an dem weder Kreis
    noch Verbindungslinie etwas Fremdes beruehren; (2) sonst der erste freie
    Platz innen, der auch die eigene Beschriftung frei laesst; (3) sonst der
    Platz aussen, dessen Linie am wenigsten Fremdes kreuzt (der Kreis selbst
    bleibt frei); (4) sonst der Platz, der am wenigsten verdeckt
    (``gefunden=False``, der Lauf meldet das).
    """
    bild = QRect(0, 0, breite, hoehe)
    ziele = [QRect(z) for z in ziele]
    rahmen = [rahmen_von(z, breite, hoehe) for z in ziele]
    vorzuege = list(vorzuege or [None] * len(ziele))
    hindernisse = [QRect(h) for h in hindernisse]
    belegt: list[QRect] = []
    aus = []
    reichweite = _ABSTAENDE[-1] + 2 * r + 6
    for i, ziel in enumerate(ziele):
        # Nur was in Reichweite eines Kandidaten liegt (spart Rechenzeit).
        umfeld = rahmen[i].adjusted(-reichweite, -reichweite, reichweite, reichweite)
        nahe = [h for h in hindernisse if h.intersects(umfeld)]
        fremd = [h for h in nahe if not _eigene(ziel, h)]
        # Innen darf der Kreis auch die EIGENE Beschriftung nicht verdecken;
        # nur ein Bereich, der das ganze Ziel traegt (Reiter), zaehlt nicht.
        fremd_innen = [h for h in nahe if _anteil(ziel, h) < 0.5]
        andere = [rahmen[j] for j in range(len(ziele))
                  if j != i and not rahmen[j].contains(rahmen[i])]

        gross = rahmen[i].width() >= 6 * r and rahmen[i].height() >= 4 * r

        def eindeutig(c):
            """Der Kreis muss seinem EIGENEN Rahmen am naechsten sein — sonst
            liest man ihn als Nummer des Nachbarn (Menuezeilen, Reiter). Bei
            etwa gleichem Abstand entscheidet, neben wem er steht: er muss auf
            Hoehe (bzw. in der Breite) des eigenen Rahmens liegen, nicht auf
            der des Nachbarn."""
            eigen = _abstand(rahmen[i], c)
            neben_eigen = _neben(rahmen[i], c)
            for a in andere:
                d = _abstand(a, c)
                if d < eigen - 6:
                    return False
                if d <= eigen + 6 and not (neben_eigen and not _neben(a, c)):
                    return False
            # Dasselbe gegen fremde beschriftete Elemente: ein Kreis schraeg
            # an der eigenen Ecke, aber auf Hoehe der naechsten Menuezeile,
            # gehoert optisch zu dieser Zeile. (Haengt er an einer deutlichen
            # Verbindungslinie, zeigt die, wohin er gehoert.)
            if _luecke(rahmen[i], c, r) > 12:
                return True
            for h in fremd:
                d = _abstand(h, c)
                if d < eigen - 6:
                    return False
                if d <= eigen + 6 and not neben_eigen and _neben(h, c):
                    return False
            return True

        def frei(feld, hs):
            return (bild.contains(feld)
                    and not any(feld.intersects(h) for h in hs)
                    and not any(feld.intersects(a) for a in andere)
                    and not any(feld.intersects(b) for b in belegt))
        wahl = innen = None
        beste = None                           # (kosten, c) fuer Stufe 3
        notfall = None                         # (kosten, c, aussen) fuer Stufe 4
        liste = []
        for c, aussen in kandidaten(rahmen[i], vorzuege[i], r):
            # Am Bildrand ein Stueck ins Bild schieben (ein Kreis neben der
            # Statusleiste passt sonst nie) — aber nur wenig, sonst haengt er
            # nicht mehr neben seinem Rahmen.
            g = _geklemmt(c, r + 2, breite, hoehe)
            if abs(g.x() - c.x()) + abs(g.y() - c.y()) <= r:
                liste.append((g, aussen))
        for c, aussen in liste:
            feld = _kreisfeld(c, r)
            if not aussen:
                # Innen nur in grossen Rahmen (Bereiche, Listen) — in einem
                # Knopf oder Reiter saesse der Kreis auf dessen Text.
                if innen is None and gross and frei(feld, fremd_innen) \
                        and eindeutig(c):
                    innen = c
                continue
            if not frei(feld, fremd) or not eindeutig(c):
                continue
            kosten = _linienkosten(c, rahmen[i], r, fremd + andere + belegt)
            if kosten == 0:
                wahl = (c, True)
                break
            # Stufe 3 nur, wenn die Linie bloss eine schmale Stelle kreuzt
            # (hoechstens ~16 px); sonst lieber Stufe 4.
            if kosten <= 8 and (beste is None or kosten < beste[0]):
                beste = (kosten, c)
        if wahl is None and innen is not None:
            wahl = (innen, False)
        if wahl is None and beste is not None:
            wahl = (beste[1], True)
        if wahl is None:
            # Stufe 4: moeglichst wenig verdecken; einen fremden Rahmen zu
            # streifen kostet viel, einen anderen Kreis zu beruehren ist aus.
            for c, aussen in liste:
                feld = _kreisfeld(c, r)
                if not bild.contains(feld) or any(feld.intersects(b) for b in belegt):
                    continue
                # Hier zaehlt auch die EIGENE Beschriftung: lieber ein wenig
                # Fremdes streifen als den eigenen Text verdecken.
                k = sum(_flaeche(feld.intersected(h)) for h in fremd)
                k += sum(_flaeche(feld.intersected(h)) for h in nahe
                         if _eigene(ziel, h)) \
                    + 60 * _linienkosten(c, rahmen[i], r, fremd + andere)
                k += sum(_flaeche(feld.intersected(a)) for a in andere)
                if not eindeutig(c):
                    k += 5000
                if notfall is None or k < notfall[0]:
                    notfall = (k, c, aussen)
        if wahl is None and notfall is not None:
            aus.append((notfall[1], notfall[2] and _luecke(rahmen[i], notfall[1], r) > 5,
                        False))
        elif wahl is None:
            # Gar nichts: alter Platz (Ecke oben links, ins Bild geklemmt).
            c = _geklemmt(QPoint(rahmen[i].left() - r + 5, rahmen[i].top() - r + 5),
                          r, breite, hoehe)
            aus.append((c, False, False))
        else:
            c, aussen = wahl
            aus.append((c, aussen and _luecke(rahmen[i], c, r) > 5, True))
        belegt.append(_kreisfeld(aus[-1][0], r))
    return aus


def _naechster_punkt(rahmen: QRect, c: QPoint) -> QPoint:
    return QPoint(min(max(c.x(), rahmen.left()), rahmen.right()),
                  min(max(c.y(), rahmen.top()), rahmen.bottom()))


def _neben(rahmen: QRect, c: QPoint) -> bool:
    """Liegt ``c`` auf Hoehe oder in der Breite von ``rahmen``?"""
    return (rahmen.top() <= c.y() <= rahmen.bottom()
            or rahmen.left() <= c.x() <= rahmen.right())


def _abstand(rahmen: QRect, c: QPoint) -> float:
    """Abstand Punkt -> Rechteck (0, wenn er darin liegt)."""
    p = _naechster_punkt(rahmen, c)
    return ((p.x() - c.x()) ** 2 + (p.y() - c.y()) ** 2) ** 0.5


def _luecke(rahmen: QRect, c: QPoint, r: int) -> float:
    """Abstand Kreisrand -> Rahmen (0, wenn der Kreis den Rahmen beruehrt)."""
    p = _naechster_punkt(rahmen, c)
    d = ((p.x() - c.x()) ** 2 + (p.y() - c.y()) ** 2) ** 0.5
    return max(0.0, d - r)


# ── beschriftete Bereiche eines Widget-Baums ───────────────────────────────

def ohne(bereiche, deckel: QRect):
    """``bereiche`` ohne das, was ``deckel`` verdeckt (z. B. ein Menue oder
    Dialog ueber dem Fenster). Ein halb verdeckter Knopf bleibt mit seinem
    sichtbaren Teil ein Hindernis."""
    from PySide6.QtGui import QRegion
    aus = []
    for r in bereiche:
        if not r.intersects(deckel):
            aus.append(QRect(r))
            continue
        aus.extend(QRect(x) for x in QRegion(r).subtracted(QRegion(deckel)))
    return aus


def hindernisse(wurzel, bezug=None, versatz: QPoint | None = None):
    """Beschriftete, sichtbare Bereiche unter ``wurzel`` in Koordinaten von
    ``bezug`` (Standard: ``wurzel``), um ``versatz`` verschoben.

    Erfasst: Knoepfe (``QAbstractButton``), Beschriftungen mit Text (nur die
    Textflaeche), Eingabefelder, Auswahllisten, Drehfelder, anklickbare
    Kacheln (Hand-Mauszeiger), Reiter (``tabRect``), Eintraege und Kopfzeilen
    von Listen/Baeumen/Tabellen, Menuepunkte und die Menueleiste.
    """
    from PySide6.QtWidgets import (
        QAbstractButton, QAbstractItemView, QAbstractSpinBox, QComboBox,
        QGroupBox, QHeaderView, QLabel, QLineEdit, QMenu, QMenuBar, QTabBar,
        QWidget)
    bezug = bezug or wurzel
    versatz = versatz or QPoint(0, 0)
    aus: list[QRect] = []

    def nimm(w, r: QRect):
        """``r`` in Koordinaten von ``w`` -> sichtbarer Teil in ``bezug``."""
        sichtbar = w.visibleRegion().boundingRect()
        r = r.intersected(sichtbar) if not sichtbar.isEmpty() else QRect()
        if r.isEmpty():
            return
        oben = w.mapTo(bezug, r.topLeft()) if w is not bezug else r.topLeft()
        aus.append(QRect(oben + versatz, r.size()))

    fenster = wurzel.window()
    alle = [wurzel] + wurzel.findChildren(QWidget)
    for w in alle:
        # Eigene Fenster (Dialoge mit ``wurzel`` als Eltern) liegen nicht im Bild.
        if not w.isVisible() or w.window() is not fenster:
            continue
        if isinstance(w, QAbstractButton):
            if w.text().strip() or not w.icon().isNull():
                nimm(w, w.rect())
        elif isinstance(w, QLabel):
            text = w.text().strip()
            if not text:
                continue
            reich = w.textFormat() == Qt.TextFormat.RichText or (
                w.textFormat() == Qt.TextFormat.AutoText and _reichtext(text))
            if reich:
                nimm(w, w.rect())
                continue
            flags = int(w.alignment().value)
            if w.wordWrap():
                flags |= int(Qt.TextFlag.TextWordWrap.value)
            roh = w.fontMetrics().boundingRect(w.contentsRect(), flags, text)
            nimm(w, roh.adjusted(-2, -1, 2, 1).intersected(w.rect()))
        elif isinstance(w, (QLineEdit, QComboBox, QAbstractSpinBox)):
            nimm(w, w.rect())
        elif isinstance(w, QTabBar):
            for i in range(w.count()):
                if w.isTabVisible(i):
                    # Ohne den Innenabstand: eine Verbindungslinie darf die
                    # leere Kante eines Reiters streifen, nicht seinen Text.
                    nimm(w, w.tabRect(i).adjusted(4, 6, -4, -6))
        elif isinstance(w, QHeaderView):
            if w.isHidden():
                continue
            for s in range(w.count()):
                if w.isSectionHidden(s):
                    continue
                pos, groesse = w.sectionViewportPosition(s), w.sectionSize(s)
                if w.orientation() == Qt.Orientation.Horizontal:
                    # Nur der (mittig stehende) Spaltentitel mit reichlich
                    # Abstand: auf einem leeren Stueck Kopfleiste unter einem
                    # Knopf darf ein Kreis sitzen, direkt neben einem Titel
                    # laese er sich als dessen Nummer.
                    titel = w.model().headerData(s, w.orientation()) \
                        if w.model() is not None else None
                    breite = min(groesse, w.fontMetrics().horizontalAdvance(
                        str(titel or "")) + 16)
                    r = QRect(pos + (groesse - breite) // 2 - 16, 0, breite + 32,
                              w.height())
                else:
                    r = QRect(0, pos, w.width(), groesse)
                nimm(w.viewport(), r)
        elif isinstance(w, QAbstractItemView):
            _eintraege(w, nimm)
        elif isinstance(w, QGroupBox) and w.title().strip():
            # Den Titel malt der Stil selbst (hier als Reiter oben links);
            # ungefaehr: Textbreite plus Innenabstand, eine Zeile hoch.
            fm = w.fontMetrics()
            nimm(w, QRect(0, 0, fm.horizontalAdvance(w.title()) + 24,
                          fm.height() + 8))
        elif isinstance(w, QMenu):
            for a in w.actions():
                if a.isVisible() and not a.isSeparator():
                    nimm(w, w.actionGeometry(a))
        elif isinstance(w, QMenuBar):
            for a in w.actions():
                if a.isVisible():
                    nimm(w, w.actionGeometry(a))
        elif w.cursor().shape() == Qt.CursorShape.PointingHandCursor \
                and w.parentWidget() is not None and w.children():
            # Anklickbare Kachel (z. B. Farb-Schnellwahl): die ganze Flaeche
            # gehoert zu ihr, nicht nur ihr Text.
            nimm(w, w.rect())
    return aus


def _reichtext(text: str) -> bool:
    try:
        from PySide6.QtGui import Qt as QtGuiQt
        return bool(QtGuiQt.mightBeRichText(text))
    except Exception:
        return "<" in text and ">" in text


def _eintraege(view, nimm, grenze: int = 400) -> None:
    """Sichtbare Eintraege einer Liste/eines Baums/einer Tabelle."""
    from PySide6.QtCore import QModelIndex
    from PySide6.QtWidgets import QTreeView
    baum = isinstance(view, QTreeView)
    model = view.model()
    if model is None:
        return
    vp = view.viewport()
    sicht = vp.rect()
    zaehler = 0
    stapel = [QModelIndex()]
    while stapel and zaehler < grenze:
        eltern = stapel.pop(0)
        try:
            spalten = max(1, model.columnCount(eltern))
        except TypeError:            # Listen-Modelle verbergen columnCount
            spalten = 1
        for zeile in range(model.rowCount(eltern)):
            for spalte in range(spalten):
                idx = model.index(zeile, spalte, eltern)
                r = view.visualRect(idx)
                if r.isEmpty() or not r.intersects(sicht):
                    continue
                zaehler += 1
                if model.data(idx) not in (None, ""):
                    # Zeilen haben Innenabstand; ein Kreis darf die Kante
                    # streifen, nicht den Text.
                    nimm(vp, r.adjusted(2, 2, -2, -2))
            if baum:
                idx0 = model.index(zeile, 0, eltern)
                if view.isExpanded(idx0) and model.rowCount(idx0) > 0:
                    stapel.append(idx0)


# ── zeichnen ────────────────────────────────────────────────────────────────

def zeichnen(pix, marken, *, beschriftungen: bool = False, hindernisse=()):
    """``marken``: Liste von ``(QRect, nummer, beschriftung[, lage])`` in
    Bildkoordinaten; ``lage`` ist ein Vorzug (s. :func:`platzieren`).

    ``hindernisse``: beschriftete Bereiche im Bild (:func:`hindernisse`),
    die kein Nummernkreis verdecken soll.

    ``beschriftungen=True`` schreibt den Text zusaetzlich als kleines Schild
    neben den Kreis; sonst steht er nur im Manifest (fuer den Anleitungstext).
    """
    if not marken:
        return pix
    b, h = pix.width(), pix.height()
    plaetze = platzieren([m[0] for m in marken], b, h, hindernisse,
                         [m[3] if len(m) > 3 else None for m in marken])
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    schrift = QFont("DejaVu Sans")
    schrift.setBold(True)
    schrift.setPixelSize(15)
    klein = QFont("DejaVu Sans")
    klein.setPixelSize(13)
    klein.setBold(True)
    if os.environ.get("LIGHTOS_DOKU_HINDERNISSE"):
        # Fehlersuche: erkannte beschriftete Bereiche duenn gruen einzeichnen.
        p.setPen(QPen(QColor(0, 220, 0), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for r in hindernisse:
            p.drawRect(r)
    # Erst alle Rahmen, dann Linien und Kreise: ein Kreis liegt nie unter
    # einem spaeter gezeichneten Rahmen.
    for rect, *_rest in marken:
        p.setPen(QPen(ROT, 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rahmen_von(rect, b, h), 6, 6)
    for (rect, nr, text, *_lage), (c, linie, gefunden) in zip(marken, plaetze):
        if not gefunden:
            print(f"[anleitungsbilder] Hinweis: Marke {nr} hat keinen freien Platz — "
                  "Kreis verdeckt so wenig wie moeglich — Bild pruefen.", file=sys.stderr, flush=True)
        if linie:
            ziel = _naechster_punkt(rahmen_von(rect, b, h), c)
            p.setPen(QPen(ROT, 3))
            p.drawLine(c, ziel)
        p.setBrush(QBrush(ROT))
        p.setPen(QPen(Qt.GlobalColor.white, 2))
        p.drawEllipse(c, _RADIUS, _RADIUS)
        p.setFont(schrift)
        p.drawText(QRect(c.x() - _RADIUS, c.y() - _RADIUS, 2 * _RADIUS, 2 * _RADIUS),
                   Qt.AlignmentFlag.AlignCenter, str(nr))
        if beschriftungen and text:
            p.setFont(klein)
            fm = QFontMetrics(klein)
            w = fm.horizontalAdvance(text) + 12
            x = c.x() + _RADIUS + 4
            if x + w > b - 2:                      # rechts kein Platz -> links
                x = c.x() - _RADIUS - 4 - w
            schild = QRect(x, c.y() - 11, w, 22)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(ROT))
            p.drawRoundedRect(schild, 4, 4)
            p.setPen(QPen(Qt.GlobalColor.white))
            p.drawText(schild, Qt.AlignmentFlag.AlignCenter, text)
    p.end()
    return pix
