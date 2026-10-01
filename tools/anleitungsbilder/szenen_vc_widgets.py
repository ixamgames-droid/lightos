"""DOC-19: Bilder fuer die VC-Widget-Referenz — ``docs/anleitung_vc_widgets/img/``.

Neu erzeugen: ``venv/bin/python tools/anleitungsbilder.py vc_widgets``.

Die uebrigen Bilder dieses Ordners (``VCButton.png``, ``dialog_*.png`` …)
stammen aus ``tools/capture_vc_widgets.py`` und einer eigenen Showcase-Show;
hier entstehen nur die Bilder mit Nummer ``NN_``, die die Doku-Demo-Show
brauchen (Gruppen und Geraete fuer das Blackout-Ziel, VCB-11).

Die Szenen legen zwei Blackout-Tasten auf Bank 1 der Doku-Demo an und raeumen
sie in der letzten Szene wieder ab — bei ``--alle`` sollen nachfolgende
Anleitungen die Doku-Demo unveraendert sehen.

Der Einstellungsdialog der Taste ist modal (``VCButton._open_properties`` ruft
``exec()``). Er wird ueber den echten Aufruf geoeffnet; ein Timer im modalen
Ereignis-Loop nimmt ihn auf und schliesst ihn mit „Cancel" — es wird also
nichts uebernommen.
"""
from anleitungsbilder.runner import Szene, SzenenFehler
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
]
