"""DOC-16: Bilder fuer ``docs/anleitung_erste_schritte/`` (Erste Schritte).

Neu erzeugen: ``venv/bin/python tools/anleitungsbilder.py erste_schritte``.

Die Szenen laufen der Reihe nach im SELBEN Fenster wie alle anderen
Anleitungen. Diese hier beginnt mit „Neue Show" (leerer Patch) und patcht dann
EIN Geraet — die letzte Szene laedt deshalb in ``nachher`` die Doku-Demo-Show
wieder, damit spaetere Anleitungen den gewohnten Stand vorfinden.

Zwei Dinge kann der Runner (noch) nicht, beide sind hier lokal geloest und
werden von ``szenen_ausgabe_einrichten.py`` mitbenutzt:

* **Menues und Rueckfragen** sind eigene Top-Level-Fenster und fehlen in
  ``win.grab()``. :func:`bild` setzt Hauptfenster und Menue/Dialog zu EINEM
  1600 x 900-Bild zusammen (ueber den ``dialog``-Weg des Runners).
* **Markierungen auf dem zusammengesetzten Bild:** :func:`bild` malt Rahmen
  und Kreise selbst ueber ``marker.zeichnen`` und gibt dabei die beschrifteten
  Bereiche von Fenster UND Menue/Dialog als Hindernisse mit — der Kreis sucht
  sich so einen freien Platz neben dem eigenen Element (die Lage in der Szene
  ist nur ein Vorzug). Folge: im Manifest stehen fuer diese Szenen keine
  ``marken`` — die Texte werden stattdessen hier gegen den Code geprueft
  (:func:`knopf`, :func:`feld`, :func:`menue_eintraege`,
  :func:`reiter_rechteck`); ein umbenannter Eintrag bricht die Szene mit
  ``SzenenFehler`` ab.

Wo eine Zeile Bedienelemente dicht unter der naechsten liegt, gibt es auch fuer
den Kern keinen freien Platz; :func:`platz_oben` schafft ihn nur fuers Bild.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

from anleitungsbilder.runner import BREITE, HOEHE, Szene, SzenenFehler

ZIEL = "docs/anleitung_erste_schritte/img"

# Profil aus den eingebauten Generic-Geraeten (fixture_db.py, Kurzname ``PARD``).
PROFIL = "LED PAR Dimmer+RGB 4ch"
SUCHE = "LED PAR"


# ── Bild zusammensetzen und markieren ───────────────────────────────────────

def _norm(text: str) -> str:
    return text.replace("&", "").replace("…", "...").strip()


def kreise_malen(pix, kreise, hindernisse=()) -> None:
    """Rahmen + Nummernkreis ueber ``marker.zeichnen``: ``(QRect, nummer, lage)``.

    ``lage`` (``links``/``rechts``/``oben``/``unten``) ist ein Vorzug; verdeckt
    der Kreis dort einen beschrifteten Bereich aus ``hindernisse``, einen
    anderen Rahmen oder Kreis, waehlt der Kern einen freien Platz.
    """
    from anleitungsbilder import marker
    marker.zeichnen(pix, [(r, nr, "", lage) for r, nr, lage in kreise],
                    hindernisse=hindernisse)


def _titelleiste_malen(p, x, y, b, titel):
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QColor, QFont
    p.fillRect(QRect(x, y, b, 28), QColor("#2b3036"))
    p.setPen(QColor("#e6edf3"))
    f = QFont(p.font())
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRect(x + 10, y, b - 20, 28),
               int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), titel)


def bild(ui, popup=None, kreise=(), *, pos=None, titel: str | None = None,
         abdunkeln: bool = True, fenster_kreise=(), hindernisse=()):
    """Hauptfenster (+ optional ``popup``) -> ein 1600 x 900-Bild-Widget.

    ``kreise``: ``(QRect, nummer, lage)`` — Rechtecke in Popup-Koordinaten,
    ohne Popup in Fensterkoordinaten; ``fenster_kreise`` immer in
    Fensterkoordinaten (z. B. die Statusleiste neben einem Menue).
    ``hindernisse``: zusaetzliche beschriftete Bereiche in Fensterkoordinaten,
    die ``marker.hindernisse`` nicht selbst findet (selbst gemalte Anzeigen
    wie das DMX-Raster: Werte und Kanalnamen sind dort keine Widgets). ``pos``: linke obere Ecke des Popups im
    Fenster (Standard: mittig). ``titel`` malt eine Titelleiste darueber
    (offscreen gibt es keine Fensterrahmen; bei Dialogen ist es der echte
    ``windowTitle``). Das Popup wird danach geschlossen.
    """
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtGui import QColor, QPainter, QPixmap
    from PySide6.QtWidgets import QLabel
    from anleitungsbilder import marker

    ui.pump(0.3)
    frei = marker.hindernisse(ui.win) + [QRect(r) for r in hindernisse]
    grund = ui.win.grab()
    bild_pix = QPixmap(BREITE, HOEHE)
    p = QPainter(bild_pix)
    p.drawPixmap(0, 0, grund)
    versatz = QPoint(0, 0)
    if popup is not None:
        pop = popup.grab()
        kopf = 28 if titel else 0
        if pos is None:
            pos = QPoint((BREITE - pop.width()) // 2,
                         max(40, (HOEHE - pop.height() - kopf) // 2) + kopf)
        if abdunkeln:
            p.fillRect(QRect(0, 0, BREITE, HOEHE), QColor(0, 0, 0, 120))
        if titel:
            _titelleiste_malen(p, pos.x(), pos.y() - kopf, pop.width(), titel)
        p.drawPixmap(pos, pop)
        p.setPen(QColor("#59636e"))
        p.drawRect(QRect(pos.x() - 1, pos.y() - kopf - 1,
                         pop.width() + 1, pop.height() + kopf + 1))
        versatz = pos
        # Was das Popup verdeckt, ist kein Hindernis mehr; seine eigenen
        # Bereiche kommen dazu (verschoben an seine Stelle im Bild).
        deckel = QRect(pos.x() - 1, pos.y() - kopf - 1,
                       pop.width() + 2, pop.height() + kopf + 2)
        frei = marker.ohne(frei, deckel)
        frei += marker.hindernisse(popup, versatz=pos)
        if titel:
            frei.append(QRect(pos.x(), pos.y() - kopf, pop.width(), kopf))
    p.end()
    if popup is not None:
        popup.close()
    kreise_malen(bild_pix, [(QRect(r).translated(versatz), nr, lage)
                            for r, nr, lage in kreise] + list(fenster_kreise), frei)
    flaeche = QLabel()
    flaeche.setFixedSize(BREITE, HOEHE)
    flaeche.setPixmap(bild_pix)
    return flaeche


@contextmanager
def platz_oben(ui, widget, px: int = 34):
    """Nur fuer ein Bild: ``widget`` bekommt oben ``px`` mehr Innenrand.

    Wo eine Zeile Bedienelemente dicht unter einer anderen liegt, findet der
    Nummernkreis sonst keinen freien Platz und saesse auf einem fremden
    Element. Die Bedienelemente selbst bleiben unveraendert, sie ruecken nur
    ein Stueck nach unten; danach gilt wieder der alte Rand.
    """
    lay = widget.layout()
    if lay is None:
        raise SzenenFehler(f"{type(widget).__name__} ohne Layout — Innenrand "
                           "nicht einstellbar")
    alt = lay.contentsMargins()
    lay.setContentsMargins(alt.left(), alt.top() + px, alt.right(), alt.bottom())
    try:
        ui.pump(0.2)
        yield
    finally:
        lay.setContentsMargins(alt)
        ui.pump(0.1)


# ── Rechtecke finden (mit Pruefung gegen den Code) ─────────────────────────

def rechteck(bezug, w):
    """Rechteck von ``w`` in Koordinaten von ``bezug`` (Fenster oder Dialog)."""
    from PySide6.QtCore import QPoint, QRect
    return QRect(w.mapTo(bezug, QPoint(0, 0)), w.size())


def vereinigung(rechtecke):
    r = rechtecke[0]
    for x in rechtecke[1:]:
        r = r.united(x)
    return r


def knopf(wurzel, text: str):
    """Sichtbarer Knopf mit genau diesem Text (sonst SzenenFehler)."""
    from PySide6.QtWidgets import QAbstractButton
    for w in wurzel.findChildren(QAbstractButton):
        if w.isVisible() and _norm(w.text()) == _norm(text):
            return w
    raise SzenenFehler(f"Knopf '{text}' nicht sichtbar — umbenannt?")


def feld(dlg, beschriftung: str):
    """Eingabefeld hinter einer Formular-Beschriftung (``QFormLayout``)."""
    from PySide6.QtWidgets import QFormLayout, QLabel
    for form in dlg.findChildren(QFormLayout):
        for zeile in range(form.rowCount()):
            lab = form.itemAt(zeile, QFormLayout.ItemRole.LabelRole)
            fld = form.itemAt(zeile, QFormLayout.ItemRole.FieldRole)
            if lab and fld and isinstance(lab.widget(), QLabel) \
                    and _norm(lab.widget().text()) == _norm(beschriftung) \
                    and fld.widget() is not None and fld.widget().isVisible():
                return fld.widget()
    raise SzenenFehler(f"Feld '{beschriftung}' fehlt im Dialog {dlg.windowTitle()!r}")


def reiter_rechteck(wurzel, bezug, text: str):
    """Rechteck eines sichtbaren Reiters (Tab) mit genau diesem Text."""
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QTabBar
    for bar in wurzel.findChildren(QTabBar):
        if not bar.isVisible():
            continue
        for i in range(bar.count()):
            if _norm(bar.tabText(i)) == _norm(text):
                r = bar.tabRect(i)
                return QRect(bar.mapTo(bezug, r.topLeft()), r.size())
    raise SzenenFehler(f"Reiter '{text}' nicht sichtbar")


def menue_oeffnen(ui, titel: str):
    """Menue der Menueleiste per Titel (ohne ``&``) aufklappen -> ``(menu, pos)``."""
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QMenu
    mb = ui.win.menuBar()
    # Ueber findChildren statt ``QAction.menu()``: dessen Python-Wrapper
    # uebernahm offscreen das C++-Objekt und loeschte das Menue beim Aufraeumen.
    for menu in mb.findChildren(QMenu):
        if _norm(menu.title()) == titel and menu.menuAction() in mb.actions():
            geo = mb.actionGeometry(menu.menuAction())
            pos = mb.mapTo(ui.win, geo.bottomLeft()) + QPoint(0, 1)
            menu.popup(ui.win.mapToGlobal(pos))
            ui.pump(0.2)
            return menu, pos
    raise SzenenFehler(f"Menü '{titel}' nicht in der Menüleiste")


def menue_eintraege(menu, texte):
    """Menuetexte -> Rechtecke im Menue; prueft, dass jeder Eintrag existiert."""
    vorhanden = {_norm(a.text()): a for a in menu.actions()}
    aus = []
    for text in texte:
        act = vorhanden.get(_norm(text))
        if act is None:
            raise SzenenFehler(f"Menüpunkt '{text}' fehlt (vorhanden: "
                               f"{sorted(k for k in vorhanden if k)})")
        aus.append(menu.actionGeometry(act))
    return aus


# ── Rueckfragen abfangen ────────────────────────────────────────────────────

def rueckfrage_abfangen(aufruf):
    """Ruft ``aufruf()`` auf und faengt die erste ``QMessageBox.question`` ab.

    Liefert ``(titel, text, knoepfe)`` genau so, wie der Code sie stellt, und
    antwortet ``No`` — es passiert also nichts.
    """
    from PySide6.QtWidgets import QMessageBox
    gefangen = {}
    alt = QMessageBox.question

    def _falle(parent, titel, text, knoepfe=None, *_a, **_k):
        gefangen.setdefault("frage", (titel, text, knoepfe))
        return QMessageBox.StandardButton.No
    QMessageBox.question = staticmethod(_falle)
    try:
        aufruf()
    finally:
        QMessageBox.question = alt
    if "frage" not in gefangen:
        raise SzenenFehler("Es kam keine Rückfrage")
    return gefangen["frage"]


def mit_antwort_ja(aufruf):
    """``aufruf()`` mit ``QMessageBox.question`` -> ``Yes`` (wie ein Klick)."""
    from PySide6.QtWidgets import QMessageBox
    alt = QMessageBox.question
    QMessageBox.question = staticmethod(
        lambda *_a, **_k: QMessageBox.StandardButton.Yes)
    try:
        aufruf()
    finally:
        QMessageBox.question = alt


def demo_show_zurueck(ui):
    """Doku-Demo-Show wieder laden (fuer die Anleitungen nach dieser)."""
    from src.core.show.show_file import load_show
    pfad = os.path.join(os.getcwd(), "Doku_Demo.lshow")
    ok, meldung = load_show(pfad)
    if not ok:
        raise SzenenFehler(f"Doku-Demo-Show laedt nicht wieder: {meldung}")
    ui.win._refresh_all_views()
    pv = getattr(ui.win, "_playback_view", None)
    if pv is not None and hasattr(pv, "_refresh_stack_combo"):
        pv._refresh_stack_combo()
    ui.state.set_selected_fids([])
    ui.pump(0.3)


# ── Szenen ──────────────────────────────────────────────────────────────────

def _neue_show(ui):
    """„Datei → Neue Show" mit „Yes" beantwortet — der echte Weg."""
    mit_antwort_ja(ui.win._new_show)
    ui.win._refresh_all_views()
    ui.win._switch_section(0)
    ui.pump(0.3)


def _bild_hauptfenster(ui):
    w = ui.win
    mb = w.menuBar()
    menues = vereinigung([mb.actionGeometry(a) for a in mb.actions() if a.isVisible()])
    menues.translate(mb.mapTo(w, menues.topLeft()) - menues.topLeft())
    status = vereinigung([rechteck(w, x) for x in (w._lbl_enttec, w._lbl_fixtures)])
    return bild(ui, kreise=[
        (menues, 1, "rechts"),
        (rechteck(w, w._tab_container), 2, "rechts"),
        (rechteck(w, w._slider_gm.parentWidget()), 3, "unten"),
        (rechteck(w, knopf(w, "TAP")), 4, "unten"),
        (rechteck(w, knopf(w, "STOP ALL")), 5, "unten"),
        (rechteck(w, knopf(w, "BLACKOUT")), 6, "unten"),
        (rechteck(w, w._command_line), 7, "oben"),
        (status, 8, "rechts"),
    ])


SEKTIONEN = ["Bühne", "Patchen", "Programmer", "Virtual Console",
             "Simple Desk", "Playback", "E/A", "BPM"]


def _bild_sektionen(ui):
    w = ui.win
    kreise = []
    for i, name in enumerate(SEKTIONEN):
        btn = w._section_btns[i]
        if _norm(btn.text()) != name:
            raise SzenenFehler(f"Sektion {i + 1} heisst '{btn.text()}', erwartet '{name}'")
        kreise.append((rechteck(w, btn), i + 1, "unten"))
    # Direkt unter der Sektionsleiste liegen Beschriftungen und Knoepfe der
    # Buehne („LIVE", „Mehrfachauswahl" …) — fuer acht Kreise nebeneinander
    # ist dort kein freier Platz, jeder saesse auf einem fremden Element.
    with platz_oben(ui, ui.seite()):
        return bild(ui, kreise=kreise)


def _bild_datei_neu(ui):
    menu, pos = menue_oeffnen(ui, "Datei")
    (neu,) = menue_eintraege(menu, ["Neue Show"])
    return bild(ui, menu, [(neu, 1, "rechts")], pos=pos, abdunkeln=False)


def _bild_rueckfrage(ui):
    from PySide6.QtWidgets import QMessageBox
    titel, text, knoepfe = rueckfrage_abfangen(ui.win._new_show)
    box = QMessageBox(QMessageBox.Icon.Question, titel, text, knoepfe, ui.win)
    box.show()
    ui.pump(0.2)
    ja = box.button(QMessageBox.StandardButton.Yes)
    # Qt-Standardknopf, deutsch ueber den Qt-Uebersetzer (wie in der App).
    if ja is None or _norm(ja.text()) != "Ja":
        raise SzenenFehler("Rückfrage ohne Knopf 'Ja'")
    return bild(ui, box, [(rechteck(box, ja), 1, "links")], titel=box.windowTitle())


def _bild_patch_leer(ui):
    w = ui.win
    return bild(ui, kreise=[(rechteck(w, knopf(w, "+ Gerät hinzufügen")), 1, "unten")])


def _profil_waehlen(dlg):
    dlg._search.setText(SUCHE)
    for i in range(dlg._tree.topLevelItemCount()):
        it = dlg._tree.topLevelItem(i)
        if it.text(0).endswith(PROFIL):
            dlg._tree.setCurrentItem(it)
            return it
    raise SzenenFehler(f"Profil '{PROFIL}' nicht in der Suche '{SUCHE}'")


def _bild_geraet(ui):
    """Den Dialog so bauen wie ``PatchView._add_fixture`` und das Profil waehlen."""
    from src.ui.widgets.fixture_browser import FixtureBrowserDialog
    dlg = FixtureBrowserDialog(ui.state.next_fid(), ui.win)
    treffer = _profil_waehlen(dlg)
    dlg.resize(1000, 620)
    dlg.show()
    ui.pump(0.3)
    baum = dlg._tree
    zeile = baum.visualItemRect(treffer)
    # Ganze Zeile von der linken Kante bis zur letzten Spalte — nicht breiter:
    # der Rahmen stuende sonst rechts neben der Liste auf „Modus:".
    zeile.setLeft(0)
    zeile.setWidth(min(baum.viewport().width(), baum.header().length()))
    zeile.moveTopLeft(baum.viewport().mapTo(dlg, zeile.topLeft()))
    return bild(ui, dlg, [
        (rechteck(dlg, dlg._search), 1, "rechts"),
        (zeile, 2, "links"),
        (rechteck(dlg, feld(dlg, "Modus:")), 3, "rechts"),
        (rechteck(dlg, feld(dlg, "Universe:")), 4, "rechts"),
        (rechteck(dlg, feld(dlg, "DMX-Adresse:")), 5, "rechts"),
        (rechteck(dlg, knopf(dlg, "Hinzufügen")), 6, "rechts"),
    ], titel=dlg.windowTitle())


def _geraet_patchen(ui):
    """„+ Gerät hinzufügen" → Profil waehlen → „Hinzufügen" — ueber den echten
    ``PatchView._add_fixture``; nur ``exec()`` des Dialogs ist ersetzt."""
    from src.ui.widgets.fixture_browser import FixtureBrowserDialog
    alt = FixtureBrowserDialog.exec

    def _exec(dlg):
        _profil_waehlen(dlg)
        if not dlg._btn_add.isEnabled():
            raise SzenenFehler("„Hinzufügen“ bleibt gesperrt")
        dlg._on_add()
        return 1
    FixtureBrowserDialog.exec = _exec
    try:
        ui.win._patch_view._add_fixture()
    finally:
        FixtureBrowserDialog.exec = alt
    ui.pump(0.3)
    if len(ui.state.get_patched_fixtures()) != 1:
        raise SzenenFehler("Nach „Hinzufügen“ steht nicht genau ein Gerät im Patch")


def _bild_patch_ein_geraet(ui):
    w = ui.win
    tab = w._patch_view._table
    r = tab.visualRect(tab.model().index(0, 0))
    breite = sum(tab.columnWidth(c) for c in range(tab.columnCount()))
    r.setLeft(0)
    r.setWidth(min(breite, tab.viewport().width()))
    r.moveTopLeft(tab.viewport().mapTo(w, r.topLeft()))
    return bild(ui, kreise=[(r, 1, "unten"), (rechteck(w, w._lbl_fixtures), 2, "rechts")])


def _programmer_wert(ui):
    """Geraet in der Liste waehlen, Reiter Intensity, Dimmer auf 255 — dieselben
    Aufrufe wie Klick in die Liste und Ziehen am Fader."""
    fids = [f.fid for f in ui.state.get_patched_fixtures()]
    ui.waehle(fids)
    ui.reiter("Intensity")
    ui.wert(fids, "intensity", 255)
    ui.pump(0.2)


def _bild_programmer(ui):
    from PySide6.QtWidgets import QLabel
    w = ui.win
    pv = w._programmer_view
    liste = pv._fixture_list
    item = liste.topLevelItem(0)
    if item is None or not item.isSelected():
        raise SzenenFehler("Gerät ist in der Programmer-Liste nicht gewählt")
    zeile = liste.visualItemRect(item)
    zeile.moveTopLeft(liste.viewport().mapTo(w, zeile.topLeft()))
    dimmer = next((lab.parentWidget() for lab in pv.findChildren(QLabel)
                   if lab.isVisible() and lab.text().strip() == "Dimmer"), None)
    if dimmer is None:
        raise SzenenFehler("Zeile 'Dimmer' nicht im Programmer")
    return bild(ui, kreise=[
        (zeile, 1, "rechts"),
        (reiter_rechteck(pv, w, "Intensity"), 2, "links"),
        (rechteck(w, dimmer), 3, "unten"),
    ])


def _programmer_farbe(ui):
    """Reiter Color, Klick auf die Schnellwahl-Kachel „Rot" — der Weg aus dem
    Text (Schritt 6). Ein echter Mausklick auf die Kachel, kein Setzen der
    Werte von hinten; danach wird geprueft, dass Rot/Gruen/Blau so stehen, wie
    der Text es verspricht."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    fids = [f.fid for f in ui.state.get_patched_fixtures()]
    ui.reiter("Color")
    ui.pump(0.2)
    kachel = _zeile_mit_text(ui.win._programmer_view, "Rot")
    QTest.mouseClick(kachel, Qt.MouseButton.LeftButton)
    ui.pump(0.3)
    werte = ui.state.programmer.get(fids[0], {})
    ist = tuple(werte.get(k) for k in ("color_r", "color_g", "color_b"))
    if ist != (255, 0, 0):
        raise SzenenFehler(f"Kachel „Rot“ setzte Rot/Grün/Blau auf {ist}, erwartet (255, 0, 0)")


def _zeile_mit_text(pv, text, *, mit_regler=False):
    """Eltern-Widget der sichtbaren Beschriftung ``text``: mit ``mit_regler``
    die Fader-Zeile (enthaelt einen QSlider), sonst z. B. die Farbkachel."""
    from PySide6.QtWidgets import QLabel, QSlider
    for lab in pv.findChildren(QLabel):
        if lab.isVisible() and lab.text().strip() == text:
            zeile = lab.parentWidget()
            if bool(zeile.findChildren(QSlider)) == mit_regler:
                return zeile
    raise SzenenFehler(f"Zeile '{text}' nicht im Programmer")


def _bild_programmer_farbe(ui):
    from src.ui.widgets.fixture_tile_preview import FixtureTilePreview
    w = ui.win
    pv = w._programmer_view
    vorschau = next((x for x in pv.findChildren(FixtureTilePreview) if x.isVisible()), None)
    if vorschau is None:
        raise SzenenFehler("Lampen-Vorschau nicht sichtbar")
    return bild(ui, kreise=[
        (reiter_rechteck(pv, w, "Color"), 1, "unten"),
        (rechteck(w, _zeile_mit_text(pv, "Rot")), 2, "unten"),
        (rechteck(w, _zeile_mit_text(pv, "Rot", mit_regler=True)), 3, "rechts"),
        (rechteck(w, vorschau), 4, "rechts"),
    ])


def _bild_datei_speichern(ui):
    menu, pos = menue_oeffnen(ui, "Datei")
    oeffnen, speichern, unter, zuletzt = menue_eintraege(
        menu, ["Öffnen...", "Speichern", "Speichern unter...", "Zuletzt verwendet"])
    return bild(ui, menu, [(oeffnen, 1, "rechts"), (speichern, 2, "rechts"),
                           (unter, 3, "rechts"), (zuletzt, 4, "rechts")],
                pos=pos, abdunkeln=False)


# ── Beenden mit ungespeicherten Aenderungen (UI-69) ─────────────────────────

def _show_geaendert(ui):
    """Doku-Demo wie ueber „Datei → Öffnen" laden (echter Weg, merkt den
    gespeicherten Stand), dann eine Cueliste anlegen — eine echte Aenderung."""
    pfad = os.path.join(os.getcwd(), "Doku_Demo.lshow")
    ui.win._open_show_path(pfad)
    ui.win._refresh_all_views()
    ui.pump(0.5)
    ui.state.new_cue_stack("Meine Show")
    ui.pump(0.2)
    if not ui.win._has_unsaved_changes():
        raise SzenenFehler("Show gilt nach der Änderung nicht als geändert")


def _bild_beenden(ui):
    """Rueckfrage aus dem ECHTEN ``closeEvent`` abfangen.

    Offscreen unterdrueckt ``_exit_prompt_suppressed`` die Frage — fuer die
    Dauer des Aufrufs gilt deshalb der Desktop-Fall. Die Falle antwortet
    ``Cancel``: ``closeEvent`` ignoriert das Ereignis und kehrt zurueck, bevor
    irgendetwas heruntergefahren wird. Zur Sicherheit wird vorher geprueft,
    dass die Frage wirklich kommt (ungespeicherte Aenderung, kein Visualizer
    mit eigener Rueckfrage), und nachher, dass das Ereignis ignoriert wurde.
    """
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QMessageBox
    from src.ui import main_window
    if not ui.win._has_unsaved_changes():
        raise SzenenFehler("Keine ungespeicherte Änderung — Beenden fragte nicht")
    if getattr(ui.win, "_visualizer_window", None) is not None:
        raise SzenenFehler("Visualizer offen — dessen Rückfrage käme zuerst")
    gefangen = {}
    alt_frage = QMessageBox.question
    alt_unterdrueckt = main_window._exit_prompt_suppressed

    def _falle(parent, titel, text, knoepfe=None, *_a, **_k):
        gefangen.setdefault("frage", (titel, text, knoepfe))
        return QMessageBox.StandardButton.Cancel
    QMessageBox.question = staticmethod(_falle)
    main_window._exit_prompt_suppressed = lambda: False
    ereignis = QCloseEvent()
    try:
        ui.win.closeEvent(ereignis)
    finally:
        QMessageBox.question = alt_frage
        main_window._exit_prompt_suppressed = alt_unterdrueckt
    if "frage" not in gefangen:
        raise SzenenFehler("Beenden stellte keine Rückfrage")
    if ereignis.isAccepted():
        raise SzenenFehler("Beenden lief trotz „Abbrechen“ weiter")
    titel, text, knoepfe = gefangen["frage"]
    box = QMessageBox(QMessageBox.Icon.Question, titel, text, knoepfe, ui.win)
    box.show()
    ui.pump(0.2)
    kreise = []
    for nr, art in enumerate((QMessageBox.StandardButton.Save,
                              QMessageBox.StandardButton.Discard,
                              QMessageBox.StandardButton.Cancel), 1):
        b = box.button(art)
        if b is None:
            raise SzenenFehler(f"Rückfrage ohne Knopf {art.name}")
        kreise.append((rechteck(box, b), nr, "unten"))
    return bild(ui, box, kreise, titel=box.windowTitle())


def _beenden_aufraeumen(ui):
    """Doku-Demo wieder wie beim Start: ohne Datei-Pfad, ohne „Meine Show"."""
    demo_show_zurueck(ui)
    ui.win._current_show_path = None
    ui.pump(0.1)


SZENEN = [
    Szene("01_hauptfenster", sektion="Bühne", vorher=_neue_show,
          dialog=_bild_hauptfenster, titel="Hauptfenster nach „Neue Show“ — leer"),
    Szene("02_sektionen", sektion="Bühne", dialog=_bild_sektionen,
          titel="Die acht Sektionen"),
    Szene("03_datei_neu", sektion="Bühne", dialog=_bild_datei_neu,
          titel="Menü Datei → Neue Show"),
    Szene("04_rueckfrage", sektion="Bühne", dialog=_bild_rueckfrage,
          titel="Rückfrage „Neue Show“"),
    Szene("05_patch_leer", sektion="Patchen", unterreiter="Patch",
          dialog=_bild_patch_leer, titel="Patch einer neuen Show"),
    Szene("06_geraet_waehlen", sektion="Patchen", unterreiter="Patch",
          dialog=_bild_geraet, titel="Dialog „Gerät hinzufügen“"),
    Szene("07_patch_ein_geraet", sektion="Patchen", unterreiter="Patch",
          vorher=_geraet_patchen, dialog=_bild_patch_ein_geraet,
          titel="Ein Gerät gepatcht"),
    Szene("08_programmer", sektion="Programmer", unterreiter="Attribute",
          vorher=_programmer_wert, dialog=_bild_programmer, warte_s=0.8,
          titel="Programmer: Dimmer auf 255"),
    Szene("09_programmer_farbe", sektion="Programmer", unterreiter="Attribute",
          vorher=_programmer_farbe, dialog=_bild_programmer_farbe, warte_s=0.8,
          titel="Programmer: Rot auf 255"),
    # Hintergrund E/A statt Programmer: rechts neben dem Menue steht dort
    # nichts, die vier Kreise passen direkt neben ihre Zeilen.
    Szene("10_datei_speichern", sektion="E/A", unterreiter="Output",
          dialog=_bild_datei_speichern, nachher=demo_show_zurueck,
          titel="Menü Datei: Speichern und Öffnen"),
    Szene("11_beenden", sektion="Playback", unterreiter="Playback",
          vorher=_show_geaendert, dialog=_bild_beenden,
          nachher=_beenden_aufraeumen,
          titel="Beenden mit ungespeicherten Änderungen: Rückfrage"),
]
