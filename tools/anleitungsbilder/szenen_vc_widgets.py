"""DOC-19: Bilder fuer die VC-Widget-Referenz — ``docs/anleitung_vc_widgets/img/``.

Neu erzeugen: ``venv/bin/python tools/anleitungsbilder.py vc_widgets``.

Die uebrigen Bilder dieses Ordners (``VCButton.png``, ``dialog_*.png`` …)
stammen aus ``tools/capture_vc_widgets.py`` und einer eigenen Showcase-Show;
hier entstehen nur die Bilder mit Nummer ``NN_``, die die Doku-Demo-Show
brauchen (Gruppen und Geraete fuer das Blackout-Ziel, VCB-11).

``04_blackout_links_ablauf.gif`` (DOC-20) zeigt denselben Vorgang als
Ablauf: vorher, „Blackout Links" gedrueckt, losgelassen. Ueber dem DMX-Monitor
steht dafuer ein Ausschnitt der Virtual Console mit den beiden Tasten.

``05_blackout_links_3d.gif`` (DOC-21) zeigt denselben Ablauf im 3D-Visualizer.
WebGL bleibt offscreen schwarz — diese Szene entsteht nur am echten Bildschirm:
``DISPLAY=:0 venv/bin/python tools/anleitungsbilder.py vc_widgets --bildschirm``.

Die Szenen legen zwei Blackout-Tasten auf Bank 1 der Doku-Demo an und raeumen
sie in der letzten Szene wieder ab — bei ``--alle`` sollen nachfolgende
Anleitungen die Doku-Demo unveraendert sehen.

Der Einstellungsdialog der Taste ist modal (``VCButton._open_properties`` ruft
``exec()``). Er wird ueber den echten Aufruf geoeffnet; ein Timer im modalen
Ereignis-Loop nimmt ihn auf und schliesst ihn mit „Cancel" — es wird also
nichts uebernommen.
"""
import json

from anleitungsbilder.runner import Frame, Szene, SzenenFehler
from anleitungsbilder.szenen_erste_schritte import bild, feld, knopf, rechteck

ZIEL = "docs/anleitung_vc_widgets/img"

_LINKS = "doku_blackout_links"
_ALLES = "doku_blackout_alles"
_GRUPPE = "PAR links"


def _canvas(ui):
    return ui.win._vc_view._canvas


def _taste(ui, name):
    from PySide6.QtWidgets import QWidget
    return _canvas(ui).findChild(QWidget, name)


def _tasten_anlegen(ui):
    """Zwei Tasten mit Aktion Blackout: „Blackout Links" (Gruppe „PAR links"
    + Geraet „Wash 1", der linke Wash der Doku-Demo) und „Blackout alles"
    (leeres Ziel = globaler Blackout)."""
    from PySide6.QtCore import QPoint
    from src.ui.virtualconsole.vc_button import ButtonAction
    canvas = _canvas(ui)
    wash1 = ui.info["washes"][0]
    for name, text, pos, gruppen, fids in (
            (_LINKS, "Blackout Links", QPoint(680, 280), [_GRUPPE], [wash1]),
            (_ALLES, "Blackout alles", QPoint(840, 280), [], [])):
        w = _taste(ui, name)
        if w is None:
            w = canvas._add_widget("VCButton", pos)
            w.setObjectName(name)
        w.caption = text
        w.action = ButtonAction.BLACKOUT
        w.blackout_groups = list(gruppen)
        w.blackout_fids = list(fids)
        w.show()
        w.update()
    ui.pump(0.3)


def _tasten_weg(ui):
    canvas = _canvas(ui)
    for name in (_LINKS, _ALLES):
        w = _taste(ui, name)
        if w is not None:
            canvas._remove_widget(w)
    ui.pump(0.2)


# ── 1: Einstellungsdialog mit Blackout-Ziel ─────────────────────────────────

def _bild_dialog(ui):
    """Echten Dialog ueber ``_open_properties`` oeffnen, im modalen Loop
    aufnehmen, mit Cancel schliessen."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox
    _tasten_anlegen(ui)
    taste = _taste(ui, _LINKS)
    ergebnis = {}

    def _aufnehmen():
        dlg = QApplication.activeModalWidget()
        if not isinstance(dlg, QDialog):
            for w in QApplication.topLevelWidgets():
                if isinstance(w, QDialog) and w.isVisible() \
                        and w.windowTitle() == "Button Einstellungen":
                    dlg = w
                    break
        if not isinstance(dlg, QDialog):
            ergebnis["fehler"] = "Dialog „Button Einstellungen“ ging nicht auf"
            return
        try:
            dlg.adjustSize()
            ui.pump(0.3)
            ziel = feld(dlg, "Blackout-Ziel:")
            aktion = feld(dlg, "Aktion:")
            hinzu = knopf(ziel, "+ Gerät/Gruppe hinzufügen")
            ok = dlg.findChild(QDialogButtonBox).button(
                QDialogButtonBox.StandardButton.Ok)
            ergebnis["bild"] = bild(ui, dlg, [
                (rechteck(dlg, aktion), 1, "rechts"),
                (rechteck(dlg, ziel), 2, "rechts"),
                (rechteck(dlg, hinzu), 3, "rechts"),
                (rechteck(dlg, ok), 4, "links"),
            ], titel=dlg.windowTitle())
        except SzenenFehler as e:
            ergebnis["fehler"] = str(e)
        finally:
            dlg.reject()          # = Cancel: nichts wird uebernommen

    QTimer.singleShot(300, _aufnehmen)
    taste._open_properties()
    if "fehler" in ergebnis:
        raise SzenenFehler(ergebnis["fehler"])
    if "bild" not in ergebnis:
        raise SzenenFehler("Dialog wurde nicht aufgenommen")
    return ergebnis["bild"]


# ── 2: Konsole mit zwei Blackout-Tasten ─────────────────────────────────────

def _bild_konsole(ui):
    _tasten_anlegen(ui)
    w = ui.win
    return bild(ui, kreise=[
        (rechteck(w, _taste(ui, _LINKS)), 1, "unten"),
        (rechteck(w, _taste(ui, _ALLES)), 2, "unten"),
    ])


# ── 3: Wirkung im DMX-Monitor ───────────────────────────────────────────────

def _links_gehalten(ui):
    """PAR 1–4 rot, PAR 5–8 blau, dann „Blackout Links" gedrueckt halten
    (echter Tastenweg ``_trigger(True)``) und einen Frame mit dem echten
    Ausgabe-Code rechnen (ohne Senden, s. ``frame_wie_ausgabe``)."""
    from anleitungsbilder.szenen_ausgabe_einrichten import (
        _werte_setzen, frame_wie_ausgabe)
    _tasten_anlegen(ui)
    _werte_setzen(ui)
    ui.sektion("E/A")
    ui.reiter("DMX Monitor")
    _taste(ui, _LINKS)._trigger(True)
    if not ui.state.output_manager.target_blackout_slots():
        raise SzenenFehler("„Blackout Links“ hat keinen Ziel-Blackout gesetzt")
    frame_wie_ausgabe(ui)


def _bild_links(ui):
    from anleitungsbilder.szenen_ausgabe_einrichten import (
        STREIFEN_H, oberer_streifen, platz_ueber_raster, zellen)
    w = ui.win
    dm = w._dmx_monitor_view
    with platz_ueber_raster(ui):
        flaeche = bild(ui, kreise=[
            (zellen(ui, 1, 16), 1, "oben"),
            (zellen(ui, 17, 32), 2, "oben"),
        ], hindernisse=[rechteck(w, dm._grid)])
    return oberer_streifen(flaeche, STREIFEN_H)


def _loslassen(ui):
    from anleitungsbilder.szenen_ausgabe_einrichten import _monitor_zurueck
    w = _taste(ui, _LINKS)
    if w is not None:
        w._trigger(False)
    _monitor_zurueck(ui)
    _tasten_weg(ui)

# ── 4: Ablauf als GIF (DOC-20) ──────────────────────────────────────────────

def _wash1_dimmer(ui) -> int:
    """DMX-Adresse des Dimmer-Kanals von Wash 1 (Universum 1)."""
    from src.core.app_state import get_channels_for_patched
    wash1 = ui.info["washes"][0]
    for f in ui.state.get_patched_fixtures():
        if f.fid != wash1:
            continue
        for c in get_channels_for_patched(f):
            if (getattr(c, "attribute", "") or "") == "intensity":
                return f.address + c.channel_number - 1
    raise SzenenFehler("Wash 1 hat keinen Dimmer-Kanal")


def _ablauf_vorher(ui):
    """PAR 1–4 rot, PAR 5–8 blau, beide Washes mit Dimmer voll; Tasten da."""
    from anleitungsbilder.szenen_ausgabe_einrichten import _werte_setzen
    _tasten_anlegen(ui)
    _werte_setzen(ui)
    ui.wert(ui.info["washes"], "intensity", 255)
    ui.waehle([])


def _druecken(gedrueckt: bool):
    def schritt(ui):
        """Wie eine MIDI-Note/ein Hotkey: Tastenzustand + echter ``_trigger``."""
        taste = _taste(ui, _LINKS)
        taste._pressed = gedrueckt
        taste._trigger(gedrueckt)
        taste.update()
        ziel = bool(ui.state.output_manager.target_blackout_slots())
        if ziel != gedrueckt:
            raise SzenenFehler("„Blackout Links“ setzt/loest den Ziel-Blackout nicht")
    schritt.__name__ = "druecken" if gedrueckt else "loslassen"
    return schritt


def _ablauf_bild(*, taste: bool, kanaele: bool):
    """DMX-Monitor (oberer Streifen) mit eingesetztem VC-Ausschnitt rechts
    oben; Kreis 1 auf „Blackout Links“, Kreis 2 auf PAR 1–4, Kreis 3 auf
    den Dimmer von Wash 1."""
    def bauen(ui):
        from PySide6.QtCore import QPoint, QRect
        from PySide6.QtGui import QColor, QPainter
        from PySide6.QtWidgets import QLabel
        from anleitungsbilder import marker
        from anleitungsbilder.szenen_ausgabe_einrichten import (
            STREIFEN_H, frame_wie_ausgabe, platz_ueber_raster, zellen)
        from anleitungsbilder.szenen_erste_schritte import kreise_malen
        w = ui.win
        # VC-Ausschnitt: beide Tasten mit etwas Rand.
        ui.sektion("Virtual Console")
        ui.pump(0.2)
        links = rechteck(w, _taste(ui, _LINKS))
        alles = rechteck(w, _taste(ui, _ALLES))
        vc_rect = links.united(alles).adjusted(-24, -14, 24, 14)
        vc_pix = w.grab(vc_rect)
        # DMX-Monitor mit dem Frame, den die Ausgabe senden wuerde.
        ui.sektion("E/A")
        ui.reiter("DMX Monitor")
        frame_wie_ausgabe(ui)
        dm = w._dmx_monitor_view
        with platz_ueber_raster(ui):
            ui.pump(0.2)
            frei = marker.hindernisse(w) + [rechteck(w, dm._grid)]
            pix = w.grab()
            raster = rechteck(w, dm._grid)
            # Einsatz rechts ueber dem Raster, neben der Legende.
            pos = QPoint(BREITE_EINSATZ_RECHTS - vc_pix.width(),
                         raster.top() - vc_pix.height() - 40)
            p = QPainter(pix)
            p.drawPixmap(pos, vc_pix)
            p.setPen(QColor("#59636e"))
            p.drawRect(QRect(pos.x() - 1, pos.y() - 1,
                             vc_pix.width() + 1, vc_pix.height() + 1))
            p.end()
            einsatz = QRect(pos.x() - 1, pos.y() - 1,
                            vc_pix.width() + 2, vc_pix.height() + 2)
            frei = marker.ohne(frei, einsatz)
            frei.append(QRect(alles.translated(pos - vc_rect.topLeft())))
            kreise = []
            if taste:
                kreise.append((links.translated(pos - vc_rect.topLeft()), 1, "links"))
            if kanaele:
                kreise.append((zellen(ui, 1, 16), 2, "oben"))
                adr = _wash1_dimmer(ui)
                kreise.append((zellen(ui, adr, adr), 3, "oben"))
            kreise_malen(pix, kreise, frei)
        pix = pix.copy(0, 0, pix.width(), STREIFEN_H)
        flaeche = QLabel()
        flaeche.setFixedSize(pix.width(), pix.height())
        flaeche.setPixmap(pix)
        return flaeche
    return bauen


BREITE_EINSATZ_RECHTS = 1588


# ── 5: dieselbe Taste im 3D-Visualizer (DOC-21) ─────────────────────────────
#
# WebGL bekommt offscreen keinen Kontext — diese Szene entsteht nur am echten
# Bildschirm: ``tools/anleitungsbilder.py vc_widgets --bildschirm``.

_VIZ_GROESSE = (1700, 900)
_VIZ_HINWEIS_H = 40      # unten: Bedienhinweis der 3D-Ansicht, kommt nicht ins GIF
# Kamera: von vorn (Publikum) leicht erhoeht auf die Reihe — links bleibt
# links. theta/phi/radius wie camera/presets.js (persp = 0.3/1.1/22).
_VIZ_KAMERA = {"name": "Doku", "mode": "3D", "theta": 0.0, "phi": 1.38,
               "radius": 16.0, "target": [0.0, 3.0, -0.5]}


def _viz(ui):
    return getattr(ui, "_doku_viz", None)


def _viz_positionen(ui) -> None:
    """3D-Lage fuer die Doku-Demo: PARs in einer Reihe auf 4,5 m, die Moving
    Heads dahinter auf 5,5 m, die (dunkle) LED-Leiste weit seitlich ausserhalb
    des Bildes. Die Demo selbst
    hat bewusst keine ``visualizer_positions`` (sonst leitete der Szenengraph
    die 2D-Lage daraus ab); die Auto-Ableitung aus der Live View legte alle
    Geraete auf 0,6 m neben die Buehnenmitte. Diese Szene laeuft nur mit
    ``--bildschirm`` und dort als einzige — nachfolgende Szenen sehen die
    geaenderte Lage nicht."""
    info = ui.info
    pos = {}
    for i, fid in enumerate(info["pars"]):
        pos[fid] = (-7.0 + i * 2.0, 4.5, 0.0)
    w1, w2 = info["washes"]
    s1, s2 = info["spots"]
    pos[w1] = (-5.0, 5.5, -2.0)
    pos[w2] = (5.0, 5.5, -2.0)
    pos[s1] = (-1.5, 5.5, -2.0)
    pos[s2] = (1.5, 5.5, -2.0)
    pos[info["leiste"][0]] = (40.0, 0.2, 0.0)    # weit seitlich, ausserhalb des Bildes
    ui.state.visualizer_positions.update(pos)


def _viz_auf(ui):
    """Ausgangslage wie beim DMX-GIF, dazu Wash 1/2 warmweiss; dann den
    3D-Visualizer oeffnen (wie Menue „Visualizer → 3D Visualizer öffnen",
    aber ohne den Fokus an sich zu reissen) und warten, bis die Szene steht."""
    from PySide6.QtCore import Qt
    from anleitungsbilder.szenen_ausgabe_einrichten import frame_wie_ausgabe
    from src.ui.visualizer.visualizer_window import VisualizerWindow
    _ablauf_vorher(ui)
    washes = ui.info["washes"]
    ui.wert(washes, "color_r", 255)
    ui.wert(washes, "color_g", 190)
    ui.wert(washes, "color_b", 110)
    frame_wie_ausgabe(ui)
    _viz_positionen(ui)
    viz = ui.win._visualizer_window
    if viz is None:
        viz = VisualizerWindow(ui.win)
        viz.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        ui.win._visualizer_window = viz
    viz.resize(*_VIZ_GROESSE)
    viz.show()
    ui._doku_viz = viz
    _viz_bereit(ui, viz)
    # Wie „Kamera → gespeicherte Kamera anwenden" (applycam: voller Dict).
    viz._bridge.push_camera_preset("applycam:" + json.dumps(_VIZ_KAMERA))
    ui.pump(1.5)


def _viz_bereit(ui, viz, timeout_s: float = 60.0) -> None:
    """Warten, bis die 3D-Szene steht (``window.__lightosAppReady``) UND der
    Start-Waechter des Fensters seine Pruefung hinter sich hat: der laedt die
    Seite ``SCENE_START_TIMEOUT_S`` nach jedem ``loadFinished`` sonst womoeglich
    neu — mitten in den Frames."""
    import time
    from src.ui.visualizer.visualizer_window import SCENE_START_TIMEOUT_S
    stand = {"bereit": None, "geladen": time.monotonic()}

    def _geladen(_ok):
        stand["geladen"] = time.monotonic()
    viz._view.loadFinished.connect(_geladen)

    def _antwort(r):
        stand["bereit"] = r
    try:
        ende = time.monotonic() + timeout_s
        while time.monotonic() < ende:
            stand["bereit"] = None
            # Als Text abfragen: ein JS-Array kommt in PySide 6.11 als ''
            # zurueck (gemessen) — dieselbe Falle, an der der Start-Waechter
            # des Fensters die fertige Szene fuer tot haelt.
            viz._view.page().runJavaScript(
                "String(window.__lightosAppReady === true)", 0, _antwort)
            ui.pump(0.5)
            if stand["bereit"] == "true" \
                    and time.monotonic() - stand["geladen"] > SCENE_START_TIMEOUT_S + 1.5:
                ui.pump(1.0)
                return
    finally:
        viz._view.loadFinished.disconnect(_geladen)
    raise SzenenFehler("3D-Szene kam nicht hoch (WebGL?) — am echten Bildschirm "
                       "mit --bildschirm bauen")


def _viz_zu(ui):
    viz = _viz(ui)
    if viz is not None:
        viz.hide()
        ui.pump(0.2)
    _loslassen(ui)


def _viz_druecken(gedrueckt: bool):
    inner = _druecken(gedrueckt)

    def schritt(ui):
        from anleitungsbilder.szenen_ausgabe_einrichten import frame_wie_ausgabe
        inner(ui)
        frame_wie_ausgabe(ui)       # Anzeige-Frame inkl. Ziel-Blackout
    schritt.__name__ = inner.__name__
    return schritt


def _viz_bild(*, taste: bool):
    """3D-Ansicht (nur die WebGL-Flaeche) mit eingesetztem VC-Ausschnitt
    links oben; Kreis 1 auf „Blackout Links“."""
    def bauen(ui):
        from PySide6.QtCore import QPoint, QRect, Qt
        from PySide6.QtGui import QColor, QPainter
        from PySide6.QtWidgets import QLabel
        from anleitungsbilder.szenen_erste_schritte import kreise_malen
        w = ui.win
        ui.sektion("Virtual Console")
        ui.pump(0.2)
        links = rechteck(w, _taste(ui, _LINKS))
        alles = rechteck(w, _taste(ui, _ALLES))
        vc_rect = links.united(alles).adjusted(-24, -14, 24, 14)
        vc_pix = w.grab(vc_rect)
        viz = _viz(ui)
        ui.pump(1.2)                 # zwei, drei Polls: DMX-Stand ist gezeichnet
        pix = viz._view.grab()
        if pix.isNull() or pix.width() < 200:
            raise SzenenFehler("3D-Ansicht liess sich nicht aufnehmen")
        pix = pix.copy(0, 0, pix.width(), pix.height() - _VIZ_HINWEIS_H)
        pos = QPoint(8, 8)       # deckt die Titel-Pille „LightOS Visualizer“ ab
        p = QPainter(pix)
        p.drawPixmap(pos, vc_pix)
        p.setPen(QColor("#59636e"))
        p.drawRect(QRect(pos.x() - 1, pos.y() - 1,
                         vc_pix.width() + 1, vc_pix.height() + 1))
        p.end()
        if taste:
            kreise_malen(pix, [(links.translated(pos - vc_rect.topLeft()), 1, "unten")],
                         [QRect(alles.translated(pos - vc_rect.topLeft()))])
        flaeche = QLabel()
        flaeche.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        flaeche.setFixedSize(pix.width(), pix.height())
        flaeche.setPixmap(pix)
        return flaeche
    return bauen


SZENEN = [
    Szene("01_blackout_ziel_dialog", sektion="Virtual Console",
          dialog=_bild_dialog,
          titel="Button-Einstellungen: Aktion Blackout mit Blackout-Ziel"),
    Szene("02_blackout_tasten", sektion="Virtual Console",
          dialog=_bild_konsole,
          titel="Zwei Blackout-Tasten: mit Ziel und global"),
    Szene("03_blackout_links_monitor", sektion="E/A",
          vorher=_links_gehalten, dialog=_bild_links, nachher=_loslassen,
          groesse=(1600, 325),
          titel="„Blackout Links“ gehalten: PAR 1–4 dunkel, PAR 5–8 leuchten"),
    Szene("04_blackout_links_ablauf", sektion="E/A",
          vorher=_ablauf_vorher, nachher=_loslassen,
          groesse=(1600, 325),
          frames=[
              Frame(dauer_s=1.4, dialog=_ablauf_bild(taste=True, kanaele=False)),
              Frame(dauer_s=1.6, schritt=_druecken(True),
                    dialog=_ablauf_bild(taste=True, kanaele=True)),
              Frame(dauer_s=1.4, schritt=_druecken(False),
                    dialog=_ablauf_bild(taste=False, kanaele=True)),
          ],
          titel="GIF: „Blackout Links“ drücken und loslassen — DMX-Monitor"),
    Szene("05_blackout_links_3d", sektion="Virtual Console",
          vorher=_viz_auf, nachher=_viz_zu, braucht_gpu=True,
          groesse=(1600, 900), gif_breite=1100,
          frames=[
              Frame(dauer_s=1.4, dialog=_viz_bild(taste=True)),
              Frame(dauer_s=1.8, schritt=_viz_druecken(True),
                    dialog=_viz_bild(taste=True)),
              Frame(dauer_s=1.4, schritt=_viz_druecken(False),
                    dialog=_viz_bild(taste=False)),
          ],
          titel="GIF: „Blackout Links“ im 3D-Visualizer (am echten Bildschirm)"),
]
