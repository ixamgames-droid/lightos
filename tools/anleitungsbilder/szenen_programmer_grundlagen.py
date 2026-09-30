"""DOC-16: Bilder fuer die Anleitung „Programmer-Grundlagen" —
``docs/anleitung_programmer_grundlagen/img/``.

Neu erzeugen: ``venv/bin/python tools/anleitungsbilder.py programmer_grundlagen``.
Die Szenen laufen der Reihe nach im SELBEN Fenster; was eine Szene einstellt
(Auswahl, Programmer-Werte), sieht die naechste noch. Jede Szene stellt ihren
Zustand deshalb selbst vollstaendig her (erst ``_leeren``).

Zwei lokale Hilfen, die der Werkzeug-Kern (noch) nicht kennt:

* ``_rahmen_*``: der Runner markiert nur ganze Widgets. Fuer einen einzelnen
  Reiter oder Listeneintrag legt die Szene ein unsichtbares, maus-durchlaessiges
  Kind-Widget genau ueber dessen Rechteck und markiert das.
* ``_ueber_fenster`` / ``_im_dialog``: ein Werkzeug-Dialog soll im
  1600 x 900-Bild ueber dem (abgedunkelten) Hauptfenster stehen. Der echte
  Dialog aus ``src`` wird offscreen geoeffnet, sein Bild mittig auf das
  Fensterbild gemalt; Markierungen im Dialog rechnet ``_im_dialog`` auf die
  Flaeche um.
"""
from anleitungsbilder.runner import BREITE, HOEHE, Szene

ZIEL = "docs/anleitung_programmer_grundlagen/img"

_RAHMEN = "doku_rahmen_"


# ── Hilfen ──────────────────────────────────────────────────────────────────

def _pv(ui):
    return ui.win._programmer_view


def _hilfsrahmen(eltern, rect, name):
    """Unsichtbares Kind-Widget ueber ``rect`` (Koordinaten von ``eltern``)."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget
    for alt in eltern.findChildren(QWidget, name):
        alt.hide()
        alt.deleteLater()
    w = QWidget(eltern)
    w.setObjectName(name)
    w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    # Das App-Stylesheet gibt QWidget einen Hintergrund -> ausdruecklich
    # durchsichtig, sonst verdeckt der Rahmen den Eintrag darunter.
    w.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
    w.setAutoFillBackground(False)
    w.setStyleSheet("background: transparent; border: none;")
    w.setGeometry(rect)
    w.show()
    return w


def _rahmen_reiter(text):
    """Finder: Rechteck eines Reiters der Programmer-Reiterleiste."""
    def finder(ui):
        tabs = _pv(ui)._main_tabs
        bar = tabs.tabBar()
        for i in range(tabs.count()):
            if tabs.tabText(i) == text and tabs.isTabVisible(i):
                return _hilfsrahmen(bar, bar.tabRect(i), _RAHMEN + "reiter_" + text)
        return None
    finder.__name__ = f"reiter_{text}"
    return finder


def _rahmen_reiterleiste(ui):
    bar = _pv(ui)._main_tabs.tabBar()
    return bar


def _rahmen_gruppe(name):
    """Finder: Zeile einer Gruppe in der Gruppen-Liste links."""
    def finder(ui):
        lst = _pv(ui)._group_list
        for i in range(lst.count()):
            it = lst.item(i)
            if it.text().startswith(name):
                return _hilfsrahmen(lst.viewport(), lst.visualItemRect(it),
                                    _RAHMEN + "gruppe")
        return None
    finder.__name__ = f"gruppe_{name}"
    return finder


def _geraete_mit_kopf(ui):
    """Ueberschrift „Geräte" + Liste als ein Rechteck (der Nummernkreis
    saesse sonst auf der Ueberschrift)."""
    from PySide6.QtCore import QRect
    lst = _pv(ui)._fixture_list
    eltern = lst.parentWidget()
    r = lst.geometry()
    return _hilfsrahmen(eltern, QRect(r.x(), r.y() - 30, r.width(), r.height() + 30),
                        _RAHMEN + "geraete")


def _gruppenliste(ui):
    return _pv(ui)._group_list.parentWidget()      # QGroupBox „Gruppen"


def _modusleiste(ui):
    """Die Zeile „Gruppe: Verknüpft · Einzeln · Relativ"."""
    from PySide6.QtCore import QRect
    pv = _pv(ui)
    knoepfe = pv._mode_btn_group.buttons()
    links = knoepfe[0]
    rechts = pv._fixture_combo
    tl = links.mapTo(pv, links.rect().topLeft())
    br = rechts.mapTo(pv, rechts.rect().bottomRight())
    return _hilfsrahmen(pv, QRect(tl.x() - 60, tl.y() - 2, br.x() - tl.x() + 62,
                                  br.y() - tl.y() + 4), _RAHMEN + "modus")


def _regler(attr_name):
    """Finder: ein AttributeSlider nach seiner Beschriftung (z. B. „Dimmer")."""
    def finder(ui):
        from src.ui.views.programmer_view import AttributeSlider
        for s in _pv(ui).findChildren(AttributeSlider):
            if s.isVisible() and s._channel.name == attr_name:
                return s
        return None
    finder.__name__ = f"regler_{attr_name}"
    return finder


def _auswahltext(ui):
    return _pv(ui)._lbl_selection


def _bibliothek(ui):
    return _pv(ui)._snap_file_panel


def _vorschau(ui):
    return _pv(ui)._tile_preview


def _leeren(ui):
    """Programmer leer, keine Auswahl, erster Reiter."""
    ui.state.clear_programmer()
    ui.waehle([])
    pv = _pv(ui)
    pv._fixture_list.clearSelection()
    pv._group_list.clearSelection()
    pv._group_list.setCurrentRow(-1)
    ui.pump(0.1)


def _pars(ui):
    """PAR 1…8 ueber die Liste waehlen (wie ein Klick auf „Alle PAR")."""
    pv = _pv(ui)
    pv._select_fids(ui.info["pars"])
    ui.pump(0.1)


_DIALOG = {}      # der zuletzt ueber das Fenster gelegte Dialog (s. _im_dialog)


def _ueber_fenster(ui, bauen, breite, hoehe):
    """Flaeche 1600 x 900: abgedunkeltes Hauptfenster + echter Dialog darauf.

    Der Dialog laeuft als eigenes (offscreen) Fenster mit seinem echten Stil —
    als Kind-Widget eingebettet erbte er fremde Farben (Checkbox-Texte dunkel
    auf dunkel). Sein Bild wird mittig auf das Fensterbild gemalt, darueber
    eine Titelleiste mit ``windowTitle()`` (offscreen hat kein Fensterrahmen).
    Markierungen im Dialog laufen ueber :func:`_im_dialog`.
    """
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QColor, QFont, QPainter, QPen
    from PySide6.QtWidgets import QLabel
    dlg = bauen(ui.win)
    dlg.resize(breite, hoehe)
    dlg.show()
    ui.pump(0.4)
    kopf = 28
    x = (BREITE - breite) // 2
    y = (HOEHE - hoehe + kopf) // 2
    bild = ui.win.grab()
    p = QPainter(bild)
    p.fillRect(bild.rect(), QColor(0, 0, 0, 120))
    p.fillRect(QRect(x, y - kopf, breite, kopf), QColor("#2d2d2d"))
    schrift = QFont(dlg.font())
    schrift.setBold(True)
    p.setFont(schrift)
    p.setPen(QColor("#dddddd"))
    p.drawText(QRect(x + 10, y - kopf, breite - 20, kopf),
               Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
               dlg.windowTitle())
    p.drawPixmap(x, y, dlg.grab())
    p.setPen(QPen(QColor("#555555"), 1))
    p.drawRect(QRect(x - 1, y - kopf - 1, breite + 1, hoehe + kopf + 1))
    p.end()
    from anleitungsbilder import marker
    from PySide6.QtCore import QPoint
    deckel = QRect(x - 1, y - kopf - 1, breite + 2, hoehe + kopf + 2)
    frei = marker.ohne(marker.hindernisse(ui.win), deckel)
    frei += marker.hindernisse(dlg, versatz=QPoint(x, y))
    frei.append(QRect(x, y - kopf, breite, kopf))          # Titelleiste
    flaeche = QLabel()
    flaeche.setPixmap(bild)
    flaeche.setFixedSize(BREITE, HOEHE)
    # Die Flaeche ist nur ein Bild: ihre beschrifteten Bereiche (fuer die Lage
    # der Nummernkreise, s. ``runner._hindernisse``) bringt sie selbst mit.
    flaeche._doku_hindernisse = frei
    _DIALOG.clear()
    _DIALOG.update(dlg=dlg, x=x, y=y, flaeche=flaeche)
    # Der Runner schliesst nur die Flaeche -> den echten Dialog mitnehmen.
    flaeche.destroyed.connect(lambda *_a, d=dlg: (d.close(), d.deleteLater()))
    return flaeche


def _im_dialog(finder):
    """Finder fuer ein Widget IM ueber das Fenster gelegten Dialog: sucht es
    im echten Dialog und legt einen Hilfsrahmen an dieselbe Stelle der Flaeche."""
    def f(ui):
        from PySide6.QtCore import QPoint, QRect
        dlg, flaeche = _DIALOG.get("dlg"), _DIALOG.get("flaeche")
        if dlg is None:
            return None
        w = finder(ui, dlg) if callable(finder) else ui.finde(finder, wurzel=dlg)
        if w is None:
            return None
        oben_links = w.mapTo(dlg, QPoint(0, 0))
        r = QRect(oben_links.x() + _DIALOG["x"], oben_links.y() + _DIALOG["y"],
                  w.width(), w.height())
        return _hilfsrahmen(flaeche, r, _RAHMEN + "dialog_" + str(id(w)))
    f.__name__ = f"im_dialog_{getattr(finder, '__name__', finder)}"
    return f


# ── Zustaende ───────────────────────────────────────────────────────────────

def _start(ui):
    _leeren(ui)
    _pv(ui)._main_tabs.setCurrentIndex(0)


def _gruppe_links(ui):
    """Klick auf „PAR links" — genau wie ``itemClicked`` der Gruppen-Liste."""
    _leeren(ui)
    pv = _pv(ui)
    lst = pv._group_list
    for i in range(lst.count()):
        if lst.item(i).text().startswith("PAR links"):
            lst.setCurrentRow(i)
            pv._on_group_clicked(lst.item(i))
            break
    ui.pump(0.2)


def _intensity(ui):
    _leeren(ui)
    _pars(ui)
    ui.wert(ui.info["pars"], "intensity", 255)
    ui.reiter("Intensity")
    ui.pump(0.2)


def _color(ui):
    _leeren(ui)
    _pars(ui)
    ui.wert(ui.info["pars"], "intensity", 255)
    ui.wert(ui.info["pars"], "color_r", 255)
    ui.wert(ui.info["pars"], "color_g", 0)
    ui.wert(ui.info["pars"], "color_b", 160)
    ui.reiter("Color")
    ui.pump(0.2)


def _position(ui):
    _leeren(ui)
    _pv(ui)._select_fids(ui.info["spots"])
    ui.wert(ui.info["spots"], "intensity", 255)
    ui.wert(ui.info["spots"], "pan", 96)
    ui.wert(ui.info["spots"], "tilt", 150)
    ui.reiter("Position")
    ui.pump(0.2)


_PALETTE = "Pink"


def _paletten(ui):
    """PARs pink, dann wie „+ Neu aufzeichnen" eine Farb-Palette daraus."""
    from src.core.engine.palette import Palette, PaletteType, get_palette_manager
    _leeren(ui)
    _pars(ui)
    ui.wert(ui.info["pars"], "intensity", 255)
    ui.wert(ui.info["pars"], "color_r", 255)
    ui.wert(ui.info["pars"], "color_g", 0)
    ui.wert(ui.info["pars"], "color_b", 160)
    pal = Palette(name=_PALETTE, type=PaletteType.COLOR)
    pal.record_from_programmer(ui.info["pars"])
    get_palette_manager().add(pal)
    ui.reiter("Paletten")
    ui.pump(0.3)


def _paletten_weg(ui):
    """Palette wieder entfernen — spaetere Anleitungen im selben Lauf sollen
    sie nicht sehen."""
    from src.core.engine.palette import get_palette_manager
    mgr = get_palette_manager()
    pal = mgr.find(_PALETTE)
    if pal is not None:
        mgr.remove(pal)
    ui.pump(0.1)


def _palettenkachel(ui):
    from src.ui.views.palette_view import PaletteButton
    for b in _pv(ui).findChildren(PaletteButton):
        # PaletteButton.palette ist das Palette-Objekt (verdeckt QWidget.palette)
        if b.isVisible() and getattr(b.palette, "name", None) == _PALETTE:
            return b
    return None


def _hervorheben(ui):
    """Wash 1+2 gewaehlt, „Hervorheben" + „Abdunkeln" gedrueckt."""
    _leeren(ui)
    pv = _pv(ui)
    alle = ui.info["pars"] + ui.info["mover"] + ui.info["leiste"]
    ui.wert(alle, "intensity", 255)
    ui.wert(alle, "color_r", 0)
    ui.wert(alle, "color_g", 80)
    ui.wert(alle, "color_b", 255)
    pv._select_fids(ui.info["washes"])
    pv._highlight()
    pv._lowlight()
    ui.reiter("Intensity")
    ui.pump(0.3)


def _farbwerkzeug(ui):
    from src.ui.views.programmer_view import _ToolDialog
    from src.ui.widgets.color_picker import ColorPicker

    def bauen(eltern):
        dlg = _ToolDialog("Color Tool", eltern)
        dlg.set_content(ColorPicker())
        return dlg
    return _ueber_fenster(ui, bauen, 640, 600)


def _positionswerkzeug(ui):
    from src.ui.views.programmer_view import _ToolDialog
    from src.ui.widgets.position_tool import PositionTool

    def bauen(eltern):
        dlg = _ToolDialog("Position Tool", eltern)
        dlg.set_content(PositionTool())
        return dlg
    return _ueber_fenster(ui, bauen, 760, 580)


def _faecher(ui):
    from src.ui.views.programmer_view import _ToolDialog
    from src.ui.widgets.fan_tool import FanTool

    def bauen(eltern):
        dlg = _ToolDialog("Fan Tool", eltern)
        ft = FanTool()
        _pv(ui)._feed_fan_targets(ft)
        for i in range(ft._combo_attr.count()):
            if ft._combo_attr.itemData(i) == "intensity":
                ft._combo_attr.setCurrentIndex(i)
                break
        ft._combo_mode.setCurrentIndex(2)      # „Start": steigt von links an
        dlg.set_content(ft)
        return dlg
    return _ueber_fenster(ui, bauen, 700, 600)


def _pars_fuer_werkzeug(ui):
    _leeren(ui)
    _pars(ui)
    ui.wert(ui.info["pars"], "intensity", 255)
    ui.reiter("Color")


def _spots_fuer_werkzeug(ui):
    _leeren(ui)
    _pv(ui)._select_fids(ui.info["spots"])
    ui.wert(ui.info["spots"], "intensity", 255)
    ui.reiter("Position")


def _loeschen(ui):
    """PAR 1–8 mit Farbe im Programmer, PAR 1–4 gewaehlt → „Auswahl löschen (4)"."""
    _leeren(ui)
    ui.wert(ui.info["pars"], "intensity", 255)
    ui.wert(ui.info["pars"], "color_r", 255)
    ui.wert(ui.info["pars"], "color_g", 120)
    ui.wert(ui.info["pars"], "color_b", 0)
    _pv(ui)._select_fids(ui.info["pars"][:4])
    ui.reiter("Intensity")
    ui.pump(0.2)


def _aufraeumen(ui):
    _leeren(ui)


SZENEN = [
    Szene("01_ueberblick", sektion="Programmer", unterreiter="Attribute",
          titel="Programmer ohne Auswahl: die Bereiche",
          vorher=_start,
          marken=[(_geraete_mit_kopf, 1, "Geräte"),
                  ("Alle", 2, "Alle"),
                  ("Keine", 3, "Keine"),
                  (_gruppenliste, 4, "Gruppen"),
                  (_rahmen_reiterleiste, 5, "Reiter"),
                  (_bibliothek, 6, "Bibliothek")]),
    Szene("02_gruppe", sektion="Programmer", unterreiter="Attribute",
          titel="Klick auf eine Gruppe wählt ihre Geräte und öffnet Matrix",
          vorher=_gruppe_links,
          marken=[(_rahmen_gruppe("PAR links"), 1, "Gruppe"),
                  (_geraete_mit_kopf, 2, "Auswahl"),
                  (_rahmen_reiter("Matrix"), 3, "Matrix")]),
    Szene("03_intensity", sektion="Programmer", unterreiter="Attribute",
          titel="Reiter Intensity mit acht PARs",
          vorher=_intensity,
          marken=[(_auswahltext, 1, "Auswahl"),
                  (_modusleiste, 2, "Gruppen-Modus"),
                  (_rahmen_reiter("Intensity"), 3, "Intensity"),
                  (_regler("Dimmer"), 4, "Dimmer"),
                  (_vorschau, 5, "Lampen-Vorschau")]),
    Szene("04_color", sektion="Programmer", unterreiter="Attribute",
          titel="Reiter Color mit acht PARs",
          vorher=_color,
          marken=[("Color Picker (Fenster)", 1, "Farbwähler als Fenster"),
                  ("Schnellwahl:", 2, "Schnellwahl"),
                  (_regler("Rot"), 3, "Rot")]),
    Szene("05_position", sektion="Programmer", unterreiter="Attribute",
          titel="Reiter Position mit zwei Spots",
          vorher=_position,
          marken=[(_rahmen_reiter("Position"), 1, "Position")]),
    Szene("06_paletten", sektion="Programmer", unterreiter="Attribute",
          titel="Reiter Paletten",
          vorher=_paletten, nachher=_paletten_weg,
          marken=[(_rahmen_reiter("Paletten"), 1, "Paletten"),
                  ("+ Neu aufzeichnen", 2, "Neu aufzeichnen"),
                  (_palettenkachel, 3, "Palette")]),
    Szene("07_hervorheben", sektion="Programmer", unterreiter="Attribute",
          titel="Hervorheben und Abdunkeln",
          vorher=_hervorheben,
          marken=[("Hervorheben", 1, "Hervorheben"),
                  ("Abdunkeln", 2, "Abdunkeln"),
                  (_vorschau, 3, "Lampen-Vorschau")]),
    Szene("08_farbwerkzeug", sektion="Programmer", unterreiter="Attribute",
          titel="Farb-Werkzeug (Color Tool)",
          vorher=_pars_fuer_werkzeug, dialog=_farbwerkzeug,
          marken=[(_im_dialog("Auf Auswahl anwenden"), 1, "Anwenden"),
                  (_im_dialog("Live AUS"), 2, "Live"),
                  (_im_dialog("Als Palette…"), 3, "Als Palette")]),
    Szene("09_positionswerkzeug", sektion="Programmer", unterreiter="Attribute",
          titel="Positions-Werkzeug (Position Tool)",
          vorher=_spots_fuer_werkzeug, dialog=_positionswerkzeug,
          marken=[(_im_dialog("Auf Auswahl anwenden"), 1, "Anwenden"),
                  (_im_dialog("Live"), 2, "Live"),
                  (_im_dialog("Mitte"), 3, "Mitte")]),
    Szene("10_faecher", sektion="Programmer", unterreiter="Attribute",
          titel="Fächer-Werkzeug (Fan Tool)",
          vorher=_pars_fuer_werkzeug, dialog=_faecher,
          marken=[(_im_dialog("Fächer anwenden"), 1, "Anwenden")]),
    Szene("11_loeschen", sektion="Programmer", unterreiter="Attribute",
          titel="Auswahl löschen, Rückgängig",
          vorher=_loeschen, nachher=_aufraeumen,
          marken=[("Auswahl löschen (4)", 1, "Löschen"),
                  ("Rückgängig", 2, "Rückgängig"),
                  ("Wiederholen", 3, "Wiederholen")]),
]
