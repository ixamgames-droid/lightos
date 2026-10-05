"""DOC-59: Bilder fuer ``docs/anleitung_3d_visualizer_2026/`` (3D-Buehne bauen,
Geraete haengen, Kamera, Strahl-Optionen, Top-Down).

Alle Szenen brauchen WebGL und entstehen nur am echten Bildschirm::

    DISPLAY=:0 venv/bin/python tools/anleitungsbilder.py 3d_buehne --bildschirm

Offscreen (``--alle``, ``--pruefen``) werden sie mit Meldung uebersprungen.

Aufgenommen wird nur der Inhalt des Visualizer-Fensters (``QWidget.grab``) —
nie der Desktop und nie die Fensterleiste. Inhalt ist ausschliesslich die
Doku-Demo-Show (Generic-Profile) auf einer Doku-Buehne, die hier in der
Sandbox gebaut wird: Plattform, Front- und Back-Traverse auf 6 m, vier
Stuetzen, Rueckwand. PAR 1–8 haengen an der Front-, die vier Moving Heads an
der Back-Traverse, die LED-Leiste steht vorn auf der Buehnenkante.

Die Szenen laufen der Reihe nach im SELBEN Visualizer-Fenster (es wird nur
einmal geoeffnet, das kostet rund 20 s); jede stellt Modus, Reiter, Kamera
und Werte selbst her.
"""
from __future__ import annotations

import json

from anleitungsbilder.runner import Frame, Szene, SzenenFehler
from anleitungsbilder.szenen_erste_schritte import kreise_malen, rechteck

ZIEL = "docs/anleitung_3d_visualizer_2026/img"

_GROESSE = (1800, 950)
_TRUSS_Y = 6.0
_TRUSS_Z = 2.5
_HAENGEN = _TRUSS_Y - 0.15 - 0.25          # Unterkante Trasse - Clamp (DOCK_HANG_OFFSET)
_BUEHNE = "Doku 3D-Bühne"

# Kameras wie camera/presets.js (theta/phi/radius/target).
_KAM_TOTALE = {"name": "Doku", "mode": "3D", "theta": 0.5, "phi": 1.25,
               "radius": 18.0, "target": [0.0, 2.8, 0.0]}


# ── Aufbau ──────────────────────────────────────────────────────────────────

def _buehne():
    from src.core.stage.stage_definition import StageDefinition, StageElement
    b = StageDefinition(name=_BUEHNE)
    el = b.elements
    el.append(StageElement(type="platform", x=0.0, y=0.5, z=0.0, w=11.0, h=1.0,
                           d=7.0, color="#332520", name="Bühne"))
    el.append(StageElement(type="truss_h", x=0.0, y=_TRUSS_Y, z=_TRUSS_Z, w=12.0,
                           h=0.3, d=0.3, color="#999999", name="Front-Traverse"))
    el.append(StageElement(type="truss_h", x=0.0, y=_TRUSS_Y, z=-_TRUSS_Z, w=12.0,
                           h=0.3, d=0.3, color="#999999", name="Back-Traverse"))
    for i, (x, z) in enumerate(((-6.0, _TRUSS_Z), (6.0, _TRUSS_Z),
                                (-6.0, -_TRUSS_Z), (6.0, -_TRUSS_Z)), 1):
        el.append(StageElement(type="truss_v", x=x, y=_TRUSS_Y / 2.0, z=z, w=0.3,
                               h=_TRUSS_Y, d=0.3, color="#999999",
                               name=f"Stütze {i}"))
    el.append(StageElement(type="wall", x=0.0, y=4.0, z=-3.6, w=13.0, h=8.0, d=0.2,
                           color="#1a1a26", name="Rückwand"))
    return b


def _positionen(ui) -> dict:
    info = ui.info
    pos = {}
    for i, fid in enumerate(info["pars"]):
        pos[fid] = (-4.9 + i * 1.4, _HAENGEN, _TRUSS_Z)
    w1, w2 = info["washes"]
    s1, s2 = info["spots"]
    for fid, x in ((w1, -4.5), (s1, -1.5), (s2, 1.5), (w2, 4.5)):
        pos[fid] = (x, _HAENGEN, -_TRUSS_Z)
    pos[info["leiste"][0]] = (0.0, 1.0 + 0.3, 3.2)
    return pos


_SPOT_CYAN = 88          # Farbrad des Generic-Spots: 80–95 = Cyan


def _farben(ui, pars_rgb=((255, 0, 150), (255, 90, 0)), wash_rgb=(0, 90, 255),
            spot_rad=_SPOT_CYAN, intens=110, spot_intens=50, wash_intens=255):
    """``pars_rgb``: zwei Farben, abwechselnd auf PAR 1, 2, 3 …

    Die Spots nicht offen-weiss auf Vollgas: ihre beiden Flecken auf der
    Plattform waren dann reines Weiss, Farbe und Boden darunter nicht zu
    erkennen (bei 100 noch immer). Deshalb Farbrad Cyan und ``spot_intens`` 50."""
    from anleitungsbilder.szenen_ausgabe_einrichten import frame_wie_ausgabe
    info = ui.info
    ui.wert(info["pars"], "intensity", intens)
    for i, fid in enumerate(info["pars"]):
        r, g, b = pars_rgb[i % 2]
        ui.wert([fid], "color_r", r)
        ui.wert([fid], "color_g", g)
        ui.wert([fid], "color_b", b)
    r, g, b = wash_rgb
    ui.wert(info["washes"], "intensity", wash_intens)
    ui.wert(info["washes"], "color_r", r)
    ui.wert(info["washes"], "color_g", g)
    ui.wert(info["washes"], "color_b", b)
    ui.wert(info["spots"], "intensity", spot_intens)
    ui.wert(info["spots"], "color_wheel", spot_rad)
    frame_wie_ausgabe(ui)


def _pan_tilt(ui, werte):
    """``werte``: {fid: (pan, tilt)}."""
    from anleitungsbilder.szenen_ausgabe_einrichten import frame_wie_ausgabe
    for fid, (pan, tilt) in werte.items():
        ui.wert([fid], "pan", pan)
        ui.wert([fid], "tilt", tilt)
    frame_wie_ausgabe(ui)


def _viz(ui):
    viz = getattr(ui, "_doku_viz", None)
    if viz is None:
        raise SzenenFehler("3D-Visualizer nicht offen")
    return viz


def _viz_auf(ui):
    """Doku-Buehne speichern, Geraete platzieren, Visualizer oeffnen (einmal)."""
    from PySide6.QtCore import Qt
    from anleitungsbilder.szenen_vc_widgets import _viz_bereit
    from src.core.stage.stage_definition import save_stage
    from src.ui.visualizer.visualizer_window import VisualizerWindow
    if getattr(ui, "_doku_viz", None) is not None:
        return
    if not save_stage(_buehne()):
        raise SzenenFehler("Bühne ließ sich in der Sandbox nicht speichern")
    ui.state.active_stage_name = _BUEHNE
    ui.state.visualizer_positions.update(_positionen(ui))
    ui.state.show_fixture_labels = False
    _farben(ui)
    viz = ui.win._visualizer_window
    if viz is None:
        viz = VisualizerWindow(ui.win)
        viz.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        ui.win._visualizer_window = viz
    viz.resize(*_GROESSE)
    viz.show()
    ui._doku_viz = viz
    _viz_bereit(ui, viz)
    kamera(ui, _KAM_TOTALE)


def kamera(ui, kam):
    viz = _viz(ui)
    if isinstance(kam, str):
        viz._bridge.push_camera_preset(kam)
    else:
        viz._bridge.push_camera_preset("applycam:" + json.dumps(kam))
    ui.pump(1.2)


def _sichtbar(viz, w):
    """Sichtbarer Teil von ``w`` in Fensterkoordinaten: Gruppen im rechten
    Reiter sind breiter als ihr Scrollbereich — ein Rahmen um die ganze
    Gruppe ragte sonst ins Leere."""
    from PySide6.QtCore import QRect
    vr = w.visibleRegion().boundingRect()
    if vr.isEmpty():
        return rechteck(viz, w)
    return QRect(w.mapTo(viz, vr.topLeft()), vr.size())


def _overlays(viz):
    """Von der 3D-Seite selbst gemalte Beschriftungen — Qt kennt sie nicht als
    Widgets; dort soll kein Nummernkreis landen: Titel-Pille links oben,
    Modus-Pille rechts oben, im Bauen-Modus Banner und Werkzeugleiste oben in
    der Mitte, unten rechts der Bedienhinweis."""
    from PySide6.QtCore import QRect
    r = rechteck(viz, viz._view)
    aus = [QRect(r.x(), r.y(), 200, 44),
           QRect(r.right() - 140, r.y(), 140, 44),
           QRect(r.x() + r.width() // 2, r.bottom() - 30, r.width() // 2, 30)]
    if viz._combo_edit.currentData() == "build":
        aus.append(QRect(r.x() + r.width() // 2 - 320, r.y(), 640, 140))
    return aus


def _fensterbild(ui, kreise=(), extra=None):
    """Inhalt des Visualizer-Fensters (ohne Fensterrahmen) als Bild-Widget.

    ``kreise``: ``(finder_oder_QRect, nummer, lage)`` — Finder relativ zum
    Visualizer-Fenster. ``extra(p, pix)`` darf vor den Marken malen."""
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QPainter
    from PySide6.QtWidgets import QLabel
    from anleitungsbilder import marker
    viz = _viz(ui)
    ui.pump(1.2)
    pix = viz.grab()
    if pix.isNull() or pix.width() < 400:
        raise SzenenFehler("Visualizer-Fenster liess sich nicht aufnehmen")
    # Die WebGL-Flaeche getrennt holen und einsetzen: im Fenster-Grab bleibt
    # sie je nach Treiber leer.
    flaeche = viz._view.grab()
    p = QPainter(pix)
    p.drawPixmap(rechteck(viz, viz._view).topLeft(), flaeche)
    if extra is not None:
        extra(p, pix)
    p.end()
    rechtecke = []
    for finder, nr, lage in kreise:
        r = finder if isinstance(finder, QRect) else _sichtbar(viz, ui.finde(finder, wurzel=viz))
        rechtecke.append((r, nr, lage))
    if rechtecke:
        kreise_malen(pix, rechtecke, marker.hindernisse(viz) + _overlays(viz))
    lbl = QLabel()
    lbl.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    lbl.setFixedSize(pix.width(), pix.height())
    lbl.setPixmap(pix)
    return lbl


# ── Helfer ──────────────────────────────────────────────────────────────────

def _gruppe(titel: str):
    """Finder: sichtbare QGroupBox mit diesem Titel (``&&`` = ``&``)."""
    def finder(ui):
        from PySide6.QtWidgets import QGroupBox
        for g in _viz(ui).findChildren(QGroupBox):
            if g.isVisible() and g.title().replace("&&", "&") == titel:
                return g
        raise SzenenFehler(f"Gruppe '{titel}' nicht sichtbar")
    finder.__name__ = f"gruppe_{titel}"
    return finder


def _werkzeug(attr: str):
    """Finder: Toolbar-Knopf einer QAction bzw. ein Widget-Attribut."""
    def finder(ui):
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QToolBar
        viz = _viz(ui)
        obj = getattr(viz, attr)
        if isinstance(obj, QAction):
            for tb in viz.findChildren(QToolBar):
                w = tb.widgetForAction(obj)
                if w is not None and w.isVisible():
                    return w
            raise SzenenFehler(f"Toolbar-Knopf für {attr} nicht sichtbar")
        if not obj.isVisible():
            raise SzenenFehler(f"{attr} nicht sichtbar")
        return obj
    finder.__name__ = f"werkzeug_{attr}"
    return finder


def _reiter_rechteck(viz, text: str):
    bar = viz._tabs.tabBar()
    for i in range(viz._tabs.count()):
        if viz._tabs.tabText(i).replace("&", "") == text:
            from PySide6.QtCore import QPoint, QRect
            r = bar.tabRect(i)
            return QRect(bar.mapTo(viz, r.topLeft()), r.size())
    raise SzenenFehler(f"Reiter '{text}' fehlt im Visualizer")


def _reiter(ui, text: str):
    viz = _viz(ui)
    for i in range(viz._tabs.count()):
        if viz._tabs.tabText(i).replace("&", "") == text:
            viz._tabs.setCurrentIndex(i)
            ui.pump(0.3)
            return
    raise SzenenFehler(f"Reiter '{text}' fehlt im Visualizer")


def _modus(ui, bauen: bool):
    _viz(ui)._set_build_mode(bauen)
    ui.pump(0.6)


def _ansicht(ui, modus: str):
    viz = _viz(ui)
    for i in range(viz._combo_view.count()):
        if viz._combo_view.itemData(i) == modus:
            viz._combo_view.setCurrentIndex(i)
            ui.pump(1.0)
            return
    raise SzenenFehler(f"Ansicht '{modus}' fehlt")


def _einstellung(ui, *, opacity=None, helligkeit=None, kegel=None, nebel=None,
                 boden=None):
    viz = _viz(ui)
    if opacity is not None:
        viz._sld_opacity.setValue(opacity)
    if helligkeit is not None:
        viz._sld_brightness.setValue(helligkeit)
        # Auch bei unveraendertem Reglerwert als Handwert melden: sonst bliebe
        # die Auto-Helligkeit eines vorigen Bauen-Bilds stehen.
        viz._on_brightness_changed(helligkeit)
    for chk, wert in ((viz._chk_cones, kegel), (viz._chk_fog, nebel),
                      (viz._chk_floor, boden)):
        if wert is not None:
            chk.setChecked(wert)
    viz._bridge.push_settings(viz._collect_settings())
    ui.pump(0.5)


def _geraet_waehlen(ui, fid):
    from PySide6.QtCore import Qt
    viz = _viz(ui)
    lst = viz._patch_list
    for i in range(lst.count()):
        it = lst.item(i)
        if it.data(Qt.ItemDataRole.UserRole) == fid:
            lst.clearSelection()
            lst.setCurrentItem(it)
            it.setSelected(True)
            lst.scrollToItem(it)
            ui.pump(0.5)
            return
    raise SzenenFehler(f"Gerät {fid} fehlt in der Visualizer-Liste")


def _auto_helligkeit(ui):
    """Wie „Auto-Werte anwenden“: Handwert verwerfen, damit die Szene im
    Bauen-Modus so hell wird wie bei einem Nutzer mit Standardwerten (65 %).
    Danach ist die 3D-Auswahl leer (``setEditMode``) — erst dann waehlen."""
    _viz(ui)._on_auto_brightness_apply()
    ui.pump(0.6)
    # Bei 65 % Grundlicht ueberstrahlten PARs (110) und Washes (255) die
    # Plattform zu weissen Flaechen; zum Bauen reicht weniger.
    _farben(ui, intens=60, wash_intens=90)


def _element_waehlen(ui, name):
    from PySide6.QtCore import Qt
    viz = _viz(ui)
    tree = viz._stage_tree
    for i in range(tree.topLevelItemCount()):
        it = tree.topLevelItem(i)
        el = viz._current_stage.get(it.data(0, Qt.ItemDataRole.UserRole))
        if el is not None and el.name == name:
            tree.setCurrentItem(it)
            ui.pump(0.8)
            return
    raise SzenenFehler(f"Bühnen-Element '{name}' fehlt im Baum")


# Moving Heads: Spots kreuzen sich zur Buehnenmitte, Washes fallen nach vorn.
def _mh_mitte(ui):
    w1, w2 = ui.info["washes"]
    s1, s2 = ui.info["spots"]
    return {w1: (128, 95), w2: (128, 95), s1: (110, 100), s2: (146, 100)}


def _alles_grundstellung(ui):
    """Ausgangslage aller Bilder: Ansehen, Fixtures-Reiter, 3D, Totale.

    Helligkeit 12 % von Hand (Strahlen gut sichtbar); die Bauen-Bilder holen
    danach die Auto-Helligkeit zurueck (:func:`_auto_helligkeit`)."""
    _viz_auf(ui)
    _ansicht(ui, "3D")
    _modus(ui, False)
    _reiter(ui, "Fixtures")
    _einstellung(ui, opacity=35, helligkeit=12, kegel=True, nebel=True, boden=True)
    _viz(ui)._patch_list.clearSelection()
    _viz(ui)._patch_list.scrollToTop()
    ui.state.set_selected_fids([])
    ui.pump(0.3)
    _farben(ui)
    _pan_tilt(ui, _mh_mitte(ui))


# ── 1: Uebersicht ───────────────────────────────────────────────────────────

def _par1_waehlen(ui):
    """PAR 1 waehlen: „Position & Ausrichtung“ zeigt sonst Werte ohne Auswahl
    (Startwert Y 6.50 bzw. die Werte des zuletzt gewaehlten Geraets, VIZ-76).
    Danach warten, bis der Identify-Puls der Auswahl (1,5 s) verklungen ist."""
    _geraet_waehlen(ui, ui.info["pars"][0])
    ui.pump(1.6)


def _v01(ui):
    _alles_grundstellung(ui)
    _par1_waehlen(ui)
    kamera(ui, _KAM_TOTALE)


def _b01(ui):
    viz = _viz(ui)
    return _fensterbild(ui, kreise=[
        (_werkzeug("_combo_view"), 1, "unten"),
        (_werkzeug("_combo_edit"), 2, "unten"),
        (_werkzeug("_combo_stage"), 3, "unten"),
        (_reiter_rechteck(viz, "Fixtures").united(_reiter_rechteck(viz, "Einstellungen")),
         4, "oben"),
    ])


# ── 2: Buehne bauen ─────────────────────────────────────────────────────────

_KAM_BAUEN = {"name": "Doku", "mode": "3D", "theta": 0.45, "phi": 1.12,
              "radius": 19.0, "target": [0.0, 3.0, 0.5]}


def _v02(ui):
    _alles_grundstellung(ui)
    _modus(ui, True)
    _auto_helligkeit(ui)
    _reiter(ui, "Bühne")
    _element_waehlen(ui, "Front-Traverse")
    kamera(ui, _KAM_BAUEN)


def _modus_rechteck(ui):
    """„Modus:“-Beschriftung + Combo als ein Rahmen: unter der Combo allein
    laegen Banner und Werkzeugleiste der 3D-Seite."""
    viz = _viz(ui)
    return _sichtbar(viz, ui.finde("Modus:", wurzel=viz)).united(
        _sichtbar(viz, viz._combo_edit))


def _b02(ui):
    return _fensterbild(ui, kreise=[
        (_modus_rechteck(ui), 1, "unten"),
        (_reiter_rechteck(_viz(ui), "Bühne"), 2, "oben"),
        (_gruppe("Element hinzufügen"), 3, "links"),
        (_gruppe("Eigenschaften (Selektion)"), 4, "links"),
    ])


# ── 3: Geraet platzieren / andocken ─────────────────────────────────────────

def _v03(ui):
    _alles_grundstellung(ui)
    _modus(ui, True)
    _auto_helligkeit(ui)
    _reiter(ui, "Fixtures")
    _viz(ui)._act_dock.setChecked(True)
    _geraet_waehlen(ui, ui.info["spots"][0])
    kamera(ui, _KAM_BAUEN)


def _b03(ui):
    return _fensterbild(ui, kreise=[
        (_werkzeug("_patch_list"), 1, "links"),
        ("Im Raum platzieren", 2, "unten"),
        (_werkzeug("_act_dock"), 3, "unten"),
        (_gruppe("Position & Ausrichtung"), 4, "links"),
    ])


def _n03(ui):
    _viz(ui)._act_dock.setChecked(False)
    _modus(ui, False)


# ── 4: Kamera-Presets ───────────────────────────────────────────────────────

def _v04(ui):
    _alles_grundstellung(ui)
    _par1_waehlen(ui)
    kamera(ui, "front")


def _b04(ui):
    """Kamera-Menue geoeffnet: das Popup getrennt aufnehmen und an seiner
    echten Stelle ins Fensterbild setzen (ein Popup ist ein eigenes Fenster)."""
    from PySide6.QtCore import QPoint, QRect
    viz = _viz(ui)
    knopf = viz._btn_cam_saved
    menu = viz._menu_cam_saved
    unten_links = knopf.mapTo(viz, QPoint(0, knopf.height()))
    menu.popup(knopf.mapToGlobal(QPoint(0, knopf.height())))
    ui.pump(0.6)
    menu_pix = menu.grab()
    menu.hide()
    ui.pump(0.2)
    ziel = QRect(unten_links, menu_pix.size())

    def malen(p, _pix):
        p.drawPixmap(ziel.topLeft(), menu_pix)
    knopf_r = rechteck(viz, knopf)
    return _fensterbild(ui, extra=malen, kreise=[(ziel.united(knopf_r), 1, "links")])


# ── 5: Einstellungen: Qualitaet, Helligkeit, Strahlen ───────────────────────

_KAM_NAH = {"name": "Doku", "mode": "3D", "theta": 0.3, "phi": 1.32,
            "radius": 15.0, "target": [0.0, 3.2, 0.0]}


def _v05(ui):
    _alles_grundstellung(ui)
    _reiter(ui, "Einstellungen")
    kamera(ui, _KAM_NAH)


def _b05(ui):
    viz = _viz(ui)
    strahl = _sichtbar(viz, ui.finde("Beam Opacity:", wurzel=viz))
    for w in (viz._sld_opacity, viz._sld_beam_range, viz._chk_fog):
        strahl = strahl.united(_sichtbar(viz, w))
    strahl.adjust(-6, -4, 6, 4)
    return _fensterbild(ui, kreise=[
        (_gruppe("Render-Qualität"), 1, "links"),
        (_gruppe("Szenen-Helligkeit"), 2, "links"),
        (strahl, 3, "links"),
    ])


# ── 6: Top-Down ─────────────────────────────────────────────────────────────

def _v06(ui):
    _alles_grundstellung(ui)
    _par1_waehlen(ui)
    _ansicht(ui, "2D")
    kamera(ui, "fit")


def _b06(ui):
    return _fensterbild(ui, kreise=[(_werkzeug("_combo_view"), 1, "unten")])


def _n06(ui):
    _ansicht(ui, "3D")


# ── 7: GIF Moving Heads fahren + Farbwechsel ────────────────────────────────

def _v07(ui):
    _alles_grundstellung(ui)
    kamera(ui, _KAM_NAH)


def _gif_schritt(pan_tilt, pars_rgb, wash_rgb, spot_rad):
    def schritt(ui):
        w1, w2 = ui.info["washes"]
        s1, s2 = ui.info["spots"]
        # Spots heller als in den Standbildern: im GIF sollen sie sichtbar
        # auffaechern und sich kreuzen.
        _farben(ui, pars_rgb=pars_rgb, wash_rgb=wash_rgb, spot_rad=spot_rad,
                spot_intens=150)
        werte = dict(zip((w1, w2, s1, s2), pan_tilt))
        _pan_tilt(ui, werte)
    return schritt


def _b07(ui):
    """Nur die 3D-Flaeche (ohne Bedienhinweis unten)."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel
    from anleitungsbilder.szenen_vc_widgets import _VIZ_HINWEIS_H
    viz = _viz(ui)
    ui.pump(1.2)
    pix = viz._view.grab()
    if pix.isNull() or pix.width() < 200:
        raise SzenenFehler("3D-Ansicht liess sich nicht aufnehmen")
    pix = pix.copy(0, 0, pix.width(), pix.height() - _VIZ_HINWEIS_H)
    lbl = QLabel()
    lbl.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    lbl.setFixedSize(pix.width(), pix.height())
    lbl.setPixmap(pix)
    return lbl


_MAG, _AMB, _BLAU, _CYAN = (255, 0, 150), (255, 90, 0), (0, 60, 255), (0, 200, 255)
_GIF_SCHRITTE = [
    # (Wash1, Wash2, Spot1, Spot2) je (pan, tilt), PAR-Farben, Wash-Farbe, Spot-Rad
    (((128, 95), (128, 95), (110, 100), (146, 100)), (_MAG, _AMB), (0, 90, 255), _SPOT_CYAN),
    (((114, 95), (142, 95), (100, 100), (156, 100)), (_MAG, _AMB), (0, 90, 255), _SPOT_CYAN),
    (((114, 95), (142, 95), (100, 100), (156, 100)), (_BLAU, _CYAN), (255, 90, 0), 20),
    (((142, 95), (114, 95), (156, 100), (100, 100)), (_BLAU, _CYAN), (255, 90, 0), 20),
]

SZENEN = [
    Szene("01_uebersicht", sektion="Bühne", vorher=_v01, dialog=_b01,
          braucht_gpu=True, groesse=_GROESSE,
          titel="3D-Visualizer: Doku-Bühne mit Traversen, PARs und Moving Heads im Nebel"),
    Szene("02_buehne_bauen", sektion="Bühne", vorher=_v02, dialog=_b02,
          braucht_gpu=True, groesse=_GROESSE,
          titel="Modus Bauen, Reiter Bühne: Front-Traverse gewählt, Eigenschaften"),
    Szene("03_geraet_platzieren", sektion="Bühne", vorher=_v03, dialog=_b03,
          nachher=_n03, braucht_gpu=True, groesse=_GROESSE,
          titel="Modus Bauen, Reiter Fixtures: Gerät wählen, platzieren, Andocken"),
    Szene("04_kamera", sektion="Bühne", vorher=_v04, dialog=_b04,
          braucht_gpu=True, groesse=_GROESSE,
          titel="Kamera-Menü mit Presets, Ansicht Front"),
    Szene("05_einstellungen", sektion="Bühne", vorher=_v05, dialog=_b05,
          braucht_gpu=True, groesse=_GROESSE,
          titel="Reiter Einstellungen: Qualitätsstufe, Helligkeit, Strahl-Optionen"),
    Szene("06_top_down", sektion="Bühne", vorher=_v06, dialog=_b06, nachher=_n06,
          braucht_gpu=True, groesse=_GROESSE,
          titel="Ansicht 2D Top-Down"),
    Szene("07_moving_heads", sektion="Bühne", vorher=_v07, braucht_gpu=True,
          groesse=_GROESSE, gif_breite=900, gif_zuschnitt=(0, 120, 1210, 660),
          frames=[Frame(dauer_s=1.3, schritt=_gif_schritt(*s), dialog=_b07, warte_s=0.8)
                  for s in _GIF_SCHRITTE],
          titel="GIF: Moving Heads fahren, Farben wechseln"),
]
