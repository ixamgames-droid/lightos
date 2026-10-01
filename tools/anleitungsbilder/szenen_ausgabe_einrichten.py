"""DOC-16: Bilder fuer ``docs/anleitung_ausgabe_einrichten/`` (Ausgabe einrichten).

Neu erzeugen: ``venv/bin/python tools/anleitungsbilder.py ausgabe_einrichten``.

Dialog „Ausgabe konfigurieren" (``src/ui/widgets/output_config.py``), Output-
und DMX-Monitor (Sektion E/A) und die Warnungen der Statusleiste. Menue- und
Dialogbilder entstehen mit den Hilfen aus ``szenen_erste_schritte.py``
(:func:`bild` & Co., s. dort).

Datenschutz — der Dialog zeigt sonst Dinge DIESES Rechners:

* Die Portliste (``serial.tools.list_ports.comports``) und die Liste der
  Netzwerkkarten (``output_config._list_ifaces``) werden NUR waehrend des
  Dialog-Aufbaus durch feste Beispiele ersetzt (``/dev/ttyUSB0``,
  ``192.168.1.x``) — echte Portnamen, Seriennummern oder IP-Adressen landen so
  nie im Bild.
* Die Beispiel-Konfiguration steht nur in der ``universes.json`` der Sandbox
  und wird danach wieder auf den Stand davor zurueckgesetzt. Angewendet wird
  sie nie (kein ``apply_output_config``): es oeffnet sich kein Port und es
  geht kein Paket raus.

Fuer die Monitor-Bilder rechnet :func:`_frame_rechnen` einen Frame (Tick-
Callbacks wie im Ausgabe-Thread) und legt ihn als Anzeige-Stand ab, OHNE zu
senden — der Ausgabe-Thread ist in der Sandbox aus. ``nachher`` raeumt das
wieder ab.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager

from anleitungsbilder.runner import Szene, SzenenFehler
from anleitungsbilder.szenen_erste_schritte import (
    bild, feld, knopf, menue_eintraege, menue_oeffnen, platz_oben, rechteck,
    reiter_rechteck,
)

ZIEL = "docs/anleitung_ausgabe_einrichten/img"

# Beispiel-Konfiguration: U1 ueber einen Enttec an USB, U2 ueber Art-Net an
# einen Node im Heimnetz. Nur Beispieladressen.
BEISPIEL_PORT = "/dev/ttyUSB0"
BEISPIEL_NODE = "192.168.1.50"
BEISPIEL_UNIVERSEN = [
    {"num": 1, "name": "Bühne", "output": "Enttec", "patch": BEISPIEL_PORT},
    {"num": 2, "name": "Traverse", "output": "ArtNet", "patch": BEISPIEL_NODE},
]
BEISPIEL_NICS = [
    {"name": "eth0", "ip": "192.168.1.10", "broadcast": "192.168.1.255"},
    {"name": "wlan0", "ip": "192.168.178.20", "broadcast": "192.168.178.255"},
]


class _BeispielPort:
    """Wie ein Eintrag aus ``serial.tools.list_ports.comports()``."""

    def __init__(self, device, description, vid=None, pid=None):
        self.device, self.description, self.vid, self.pid = device, description, vid, pid


@contextmanager
def _beispiel_umgebung():
    """Beispiel-Ports, -Netzwerkkarten und -``universes.json`` fuer den
    Dialog-Aufbau; danach alles wie vorher."""
    import serial.tools.list_ports as lp
    from src.ui.widgets import output_config as oc
    from src.core.dmx.enttec_pro import ENTTEC_VID, ENTTEC_PID
    pfad = oc._UNIV_CONFIG_PATH
    alt_datei = open(pfad, encoding="utf-8").read() if os.path.exists(pfad) else None
    alt_ports, alt_nics = lp.comports, oc._list_ifaces
    lp.comports = lambda *a, **k: [
        _BeispielPort(BEISPIEL_PORT, "DMX USB PRO", ENTTEC_VID, ENTTEC_PID)]
    oc._list_ifaces = lambda: [dict(n) for n in BEISPIEL_NICS]
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(BEISPIEL_UNIVERSEN, f, ensure_ascii=False, indent=2)
    try:
        yield
    finally:
        lp.comports, oc._list_ifaces = alt_ports, alt_nics
        if alt_datei is None:
            os.remove(pfad)
        else:
            with open(pfad, "w", encoding="utf-8") as f:
                f.write(alt_datei)


def _dialog(ui, reiter: str):
    """``OutputConfigDialog`` wie ``MainWindow._open_output_config``, sichtbar,
    mit gewaehltem Reiter."""
    from PySide6.QtWidgets import QTabWidget
    from src.ui.widgets.output_config import OutputConfigDialog
    with _beispiel_umgebung():
        dlg = OutputConfigDialog(ui.win)
    dlg.resize(820, 560)
    tabs = dlg.findChild(QTabWidget)
    for i in range(tabs.count()):
        if tabs.tabText(i) == reiter:
            tabs.setCurrentIndex(i)
            break
    else:
        raise SzenenFehler(f"Reiter '{reiter}' fehlt im Dialog")
    dlg.show()
    ui.pump(0.3)
    return dlg


def _status(dlg, text_anfang: str):
    """Sichtbares Status-Label, dessen Text so beginnt."""
    from PySide6.QtWidgets import QLabel
    for lab in dlg.findChildren(QLabel):
        if lab.isVisible() and lab.text().startswith(text_anfang):
            return lab
    raise SzenenFehler(f"Status '{text_anfang}…' nicht sichtbar")


# ── Szenen ──────────────────────────────────────────────────────────────────

def _bild_menue(ui):
    w = ui.win
    menu, pos = menue_oeffnen(ui, "Ausgabe")
    (konf,) = menue_eintraege(menu, ["Konfigurieren..."])
    return bild(ui, menu, [(konf, 1, "rechts")], pos=pos, abdunkeln=False,
                fenster_kreise=[(rechteck(w, w._lbl_enttec), 2, "oben")])


def _bild_enttec(ui):
    dlg = _dialog(ui, "Enttec Pro USB")
    return bild(ui, dlg, [
        (rechteck(dlg, feld(dlg, "COM-Port:")), 1, "rechts"),
        (rechteck(dlg, knopf(dlg, "Ports aktualisieren")), 2, "rechts"),
        (rechteck(dlg, feld(dlg, "Universe:")), 3, "rechts"),
        (rechteck(dlg, knopf(dlg, "Verbinden")), 4, "rechts"),
        (rechteck(dlg, _status(dlg, "Gespeichert:")), 5, "unten"),
    ], titel=dlg.windowTitle())


def _bild_artnet(ui):
    dlg = _dialog(ui, "Art-Net")
    return bild(ui, dlg, [
        (rechteck(dlg, knopf(dlg, "Art-Net aktivieren")), 1, "rechts"),
        (rechteck(dlg, feld(dlg, "Netzwerkkarte:")), 2, "rechts"),
        (rechteck(dlg, feld(dlg, "Universe:")), 3, "rechts"),
        (rechteck(dlg, feld(dlg, "Ziel-IP / Broadcast:")), 4, "rechts"),
        (rechteck(dlg, feld(dlg, "Art-Net Startuniversum:")), 5, "rechts"),
        (rechteck(dlg, knopf(dlg, "Übernehmen")), 6, "rechts"),
    ], titel=dlg.windowTitle())


def _bild_sacn(ui):
    dlg = _dialog(ui, "sACN (E1.31)")
    return bild(ui, dlg, [
        (rechteck(dlg, knopf(dlg, "sACN (E1.31) aktivieren")), 1, "rechts"),
        (rechteck(dlg, feld(dlg, "Universe:")), 2, "rechts"),
        (rechteck(dlg, knopf(dlg, "Multicast (239.255.0.x)")), 3, "rechts"),
        (rechteck(dlg, feld(dlg, "Unicast Ziel-IP:")), 4, "rechts"),
        (rechteck(dlg, knopf(dlg, "Übernehmen")), 5, "rechts"),
    ], titel=dlg.windowTitle())


def _bild_universen(ui):
    from PySide6.QtCore import QRect
    dlg = _dialog(ui, "Universen")
    tab = dlg._univ_table
    if tab.rowCount() != len(BEISPIEL_UNIVERSEN):
        raise SzenenFehler("Universen-Tabelle zeigt die Beispiel-Konfiguration nicht")
    kopf = [tab.horizontalHeaderItem(c).text() for c in range(tab.columnCount())]
    if kopf != ["#", "Name", "Output", "Patch (Port/IP)", "Ext-Universe"]:
        raise SzenenFehler(f"Spalten der Universen-Tabelle geaendert: {kopf}")

    def _spalte(c):
        x = tab.columnViewportPosition(c)
        oben = tab.horizontalHeader().mapTo(dlg, tab.horizontalHeader().rect().topLeft())
        unten = tab.viewport().mapTo(dlg, tab.visualRect(
            tab.model().index(tab.rowCount() - 1, c)).bottomLeft())
        # 4 px schmaler als die Spalte: sonst ueberlappen sich die Rahmen
        # zweier Nachbarspalten und verdecken den Zellanfang.
        return QRect(oben.x() + x + 4, oben.y(), tab.columnWidth(c) - 8,
                     unten.y() - oben.y())
    return bild(ui, dlg, [
        (_spalte(2), 1, "unten"),
        (_spalte(3), 2, "unten"),
        (_spalte(4), 3, "unten"),
        (rechteck(dlg, knopf(dlg, "+ Universe hinzufügen")), 4, "oben"),
        (rechteck(dlg, knopf(dlg, "Speichern")), 5, "oben"),
    ], titel=dlg.windowTitle())


def _werte_setzen(ui):
    """PAR 1…4 rot, PAR 5…8 blau, jeweils voll — damit der Monitor etwas zeigt."""
    pars = ui.info["pars"]
    ui.waehle(pars)
    ui.wert(pars, "intensity", 255)
    for i, fid in enumerate(pars):
        rot = i < len(pars) // 2
        ui.wert([fid], "color_r", 255 if rot else 0)
        ui.wert([fid], "color_g", 0)
        ui.wert([fid], "color_b", 0 if rot else 255)


def _frame_rechnen(ui):
    """Einen Frame rechnen wie ``OutputManager._send_all`` — nur die Tick-
    Callbacks und den Anzeige-Stand, OHNE Channel-Modifier/GM (hier neutral)
    und ohne jedes Senden."""
    om = ui.state.output_manager
    for cb in list(om._tick_callbacks):
        cb(1.0 / 40)
    for num, universe in list(om.universes.items()):
        om._display_frame[num] = universe.get_all()
    ui.pump(0.3)


def _monitor(ui):
    _werte_setzen(ui)
    _frame_rechnen(ui)
    ui.reiter("Output")


def _monitor_zurueck(ui):
    om = ui.state.output_manager
    om._display_frame.clear()
    ui.state.clear_programmer()
    ui.waehle([])


def _bild_output(ui):
    from PySide6.QtCore import QRect
    w = ui.win
    ov = w._output_view
    zellen = ov._cells.get(1) or []
    if len(zellen) < 32:
        raise SzenenFehler("Output-Monitor ohne Kanal-Zellen")
    erste = rechteck(w, zellen[0])
    letzte = rechteck(w, zellen[31])
    block = QRect(erste.topLeft(), letzte.bottomRight())
    # Die Kanal-Kacheln malen Wert und Nummer selbst -> als Hindernisse
    # mitgeben, sonst saesse ein Kreis auf einer Nachbar-Kachel.
    return bild(ui, kreise=[
        (rechteck(w, ov._spin_univ), 1, "rechts"),
        (block, 2, "rechts"),
    ], hindernisse=[rechteck(w, z) for z in zellen if z.isVisible()])


def _dmx_monitor(ui):
    _werte_setzen(ui)
    _frame_rechnen(ui)
    ui.reiter("DMX Monitor")
    ui.win._dmx_monitor_view._refresh()
    ui.pump(0.2)


def _bild_dmx_monitor(ui):
    w = ui.win
    dm = w._dmx_monitor_view
    if not dm._lbl_ausgang.text().startswith("Universe 1 geht raus"):
        raise SzenenFehler(f"DMX-Monitor meldet '{dm._lbl_ausgang.text()}'")
    # Das DMX-Raster malt Werte und Kanalnamen selbst -> ganze Flaeche als
    # Hindernis. Darunter ist also kein Platz, darueber liegen die Reiter:
    # fuer die Kreise bekommt die Ansicht oben etwas mehr Rand.
    with platz_oben(ui, dm):
        return bild(ui, kreise=[
            (rechteck(w, dm._combo_univ), 1, "oben"),
            (rechteck(w, dm._edit_filter), 2, "oben"),
            (rechteck(w, dm._lbl_ausgang), 3, "oben"),
            (rechteck(w, dm._lbl_legend), 4, "oben"),
        ], hindernisse=[rechteck(w, dm._grid)])


def _ohne_ausgang(ui):
    """U1 den Ausgang nehmen — so sieht es aus, wenn Geraete auf einem
    Universum ohne Ausgang stehen. ``nachher`` stellt ihn wieder her."""
    _werte_setzen(ui)
    _frame_rechnen(ui)
    ui.state.output_manager.remove_output(1)
    ui.state.output_manager._display_frame.clear()
    ui.reiter("DMX Monitor")
    ui.win._check_hardware()
    ui.win._dmx_monitor_view._refresh()
    ui.pump(0.3)


def _ausgang_zurueck(ui):
    """Sandbox-Ausgang (Art-Net an die eigene Loopback-Adresse) wiederherstellen;
    der Ausgabe-Thread bleibt aus, es wird nichts gesendet."""
    ui.state.apply_output_config()
    ui.win._check_hardware()
    _monitor_zurueck(ui)
    ui.pump(0.2)


def _bild_warnungen(ui):
    w = ui.win
    dm = w._dmx_monitor_view
    if "ohne Ausgang" not in w._lbl_universe.text():
        raise SzenenFehler(f"Statusleiste meldet '{w._lbl_universe.text()}'")
    return bild(ui, kreise=[
        (rechteck(w, dm._lbl_ausgang), 1, "unten"),
        (rechteck(w, w._lbl_enttec), 2, "oben"),
        (rechteck(w, w._lbl_universe), 3, "oben"),
    ], hindernisse=[rechteck(w, dm._grid)])


# ── 9: Blackout im DMX-Monitor (OUT-57) ─────────────────────────────────────
#
# Die Hilfen hier benutzt auch ``szenen_vc_widgets`` (Blackout-Taste mit Ziel).

def frame_wie_ausgabe(ui):
    """Einen Frame mit dem ECHTEN ``OutputManager._send_all`` rechnen — mit
    Channel-Modifier, Grand-Master, Blackout und Ziel-Blackout —, aber ohne
    zu senden: die Sender-Tabellen sind waehrenddessen leer und werden danach
    unveraendert zurueckgelegt. So zeigt der Monitor genau das, was die
    Ausgabe senden wuerde (anders als :func:`_frame_rechnen`, das Blackout
    und GM bewusst auslaesst)."""
    om = ui.state.output_manager
    tabellen = (om._enttec_outputs, om._artnet_outputs, om._sacn_outputs)
    gemerkt = [dict(t) for t in tabellen]
    try:
        for t in tabellen:
            t.clear()
        om._send_all()
    finally:
        for t, alt in zip(tabellen, gemerkt):
            t.clear()
            t.update(alt)
    ui.win._dmx_monitor_view._refresh()
    ui.pump(0.3)


def zellen(ui, von: int, bis: int):
    """Rechteck der DMX-Monitor-Kacheln ``von``…``bis`` (eine Zeile) in
    Fensterkoordinaten."""
    from PySide6.QtCore import QPoint, QRect
    from src.ui.views.dmx_monitor_view import COLS, ROWS
    grid = ui.win._dmx_monitor_view._grid
    if (von - 1) // COLS != (bis - 1) // COLS:
        raise SzenenFehler(f"Kanäle {von}–{bis} liegen nicht in einer Zeile")
    cw, ch = grid.width() / COLS, grid.height() / ROWS
    zeile, s1, s2 = (von - 1) // COLS, (von - 1) % COLS, (bis - 1) % COLS
    oben_links = grid.mapTo(ui.win, QPoint(int(s1 * cw), int(zeile * ch)))
    return QRect(oben_links.x(), oben_links.y(),
                 int((s2 - s1 + 1) * cw), int(ch))


def oberer_streifen(flaeche, hoehe: int):
    """Nur den oberen Teil eines :func:`bild` behalten (Monitor-Zeilen 1–3;
    darunter stehen nur Nullen)."""
    from PySide6.QtWidgets import QLabel
    pix = flaeche.pixmap().copy(0, 0, flaeche.width(), hoehe)
    aus = QLabel()
    aus.setFixedSize(pix.width(), pix.height())
    aus.setPixmap(pix)
    flaeche.deleteLater()
    return aus


STREIFEN_H = 325


@contextmanager
def platz_ueber_raster(ui, px: int = 34):
    """Nur fuer ein Bild: Abstand zwischen Legende und DMX-Raster. Ueber Zeile 1
    steht sonst die Legende, und die Kreise fuer Kanalbereiche saessen auf
    einer Nachbar-Kachel. Das Raster wird dafuer minimal flacher."""
    dm = ui.win._dmx_monitor_view
    lay = dm.layout()
    idx = lay.indexOf(dm._grid)
    if idx < 0:
        raise SzenenFehler("DMX-Raster nicht im Layout des Monitors")
    lay.insertSpacing(idx, px)
    try:
        ui.pump(0.2)
        yield
    finally:
        lay.takeAt(idx)
        lay.invalidate()
        ui.pump(0.1)

# Doku-Demo: Wash 1/2 ab 41/48, Spot 1/2 ab 61/69 — bei beiden Profilen sind
# die ersten zwei Kanaele Pan und Tilt (siehe Kachel-Kuerzel im Bild).
_BEWEGUNG = "41,42,48,49,61,62,69,70"


def _blackout_knopf(ui):
    return knopf(ui.win, "BLACKOUT")


def _blackout_an(ui):
    """PARs rot, Moving Heads an und auf eine Position gefahren, dann der
    BLACKOUT-Knopf der Kopfleiste (echter Klick)."""
    _werte_setzen(ui)
    mover = ui.info["mover"]
    ui.wert(mover, "intensity", 255)
    ui.wert(mover, "pan", 200)
    ui.wert(mover, "tilt", 60)
    ui.reiter("DMX Monitor")
    dm = ui.win._dmx_monitor_view
    dm._edit_filter.setText(_BEWEGUNG)
    b = _blackout_knopf(ui)
    if not b.isChecked():
        b.click()
    if not ui.state.output_manager.blackout:
        raise SzenenFehler("BLACKOUT-Knopf schaltet den Blackout nicht ein")
    frame_wie_ausgabe(ui)


def _blackout_aus(ui):
    b = _blackout_knopf(ui)
    if b.isChecked():
        b.click()
    ui.win._dmx_monitor_view._edit_filter.setText("")
    _monitor_zurueck(ui)


def _bild_blackout(ui):
    w = ui.win
    dm = w._dmx_monitor_view
    with platz_ueber_raster(ui):
        flaeche = bild(ui, kreise=[
            (rechteck(w, _blackout_knopf(ui)), 1, "unten"),
            (zellen(ui, 1, 32), 2, "oben"),
            (rechteck(w, dm._edit_filter), 3, "oben"),
        ], hindernisse=[rechteck(w, dm._grid)])
    return oberer_streifen(flaeche, STREIFEN_H)


SZENEN = [
    Szene("01_menue_ausgabe", sektion="Programmer", unterreiter="Attribute",
          dialog=_bild_menue, titel="Menü Ausgabe → Konfigurieren…"),
    Szene("02_enttec", sektion="Programmer", dialog=_bild_enttec,
          titel="Reiter Enttec Pro USB (Beispiel-Port)"),
    Szene("03_artnet", sektion="Programmer", dialog=_bild_artnet,
          titel="Reiter Art-Net (Beispiel-Node)"),
    Szene("04_sacn", sektion="Programmer", dialog=_bild_sacn,
          titel="Reiter sACN (E1.31)"),
    Szene("05_universen", sektion="Programmer", dialog=_bild_universen,
          titel="Reiter Universen mit zwei Beispiel-Universen"),
    Szene("06_output_monitor", sektion="E/A", vorher=_monitor,
          dialog=_bild_output, nachher=_monitor_zurueck,
          titel="E/A → Output: Kanalwerte von Universe 1"),
    Szene("07_dmx_monitor", sektion="E/A", vorher=_dmx_monitor,
          dialog=_bild_dmx_monitor, nachher=_monitor_zurueck,
          titel="E/A → DMX Monitor"),
    Szene("08_warnungen", sektion="E/A", vorher=_ohne_ausgang,
          dialog=_bild_warnungen, nachher=_ausgang_zurueck,
          titel="Warnungen: Universe ohne Ausgang"),
    Szene("09_blackout_dmx_monitor", sektion="E/A", vorher=_blackout_an,
          dialog=_bild_blackout, nachher=_blackout_aus, groesse=(1600, STREIFEN_H),
          titel="BLACKOUT im DMX-Monitor: Licht 0, Pan/Tilt bleibt"),
]
