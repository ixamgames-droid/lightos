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
  ``192.0.2.x``, RFC 5737) — echte Portnamen, Seriennummern oder IP-Adressen landen so
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

from anleitungsbilder.runner import Frame, Szene, SzenenFehler
from anleitungsbilder.szenen_erste_schritte import (
    bild, feld, knopf, menue_eintraege, menue_oeffnen, platz_oben, rechteck,
    reiter_rechteck,
)

ZIEL = "docs/anleitung_ausgabe_einrichten/img"

# Beispiel-Konfiguration: U1 ueber einen Enttec an USB, U2 ueber Art-Net an
# einen Node im Lichtnetz. Nur Beispieladressen (RFC 5737, PRIV-07).
BEISPIEL_PORT = "/dev/ttyUSB0"
BEISPIEL_NODE = "192.0.2.50"
BEISPIEL_UNIVERSEN = [
    {"num": 1, "name": "Bühne", "output": "Enttec", "patch": BEISPIEL_PORT},
    {"num": 2, "name": "Traverse", "output": "ArtNet", "patch": BEISPIEL_NODE},
]
BEISPIEL_NICS = [
    {"name": "eth0", "ip": "192.0.2.10", "broadcast": "192.0.2.255"},
    {"name": "wlan0", "ip": "198.51.100.20", "broadcast": "198.51.100.255"},
]


class _BeispielPort:
    """Wie ein Eintrag aus ``serial.tools.list_ports.comports()``."""

    def __init__(self, device, description, vid=None, pid=None):
        self.device, self.description, self.vid, self.pid = device, description, vid, pid
        # OUT-70: der Zusatz in der Portliste kommt aus dem Produkttext.
        self.manufacturer, self.product = "ENTTEC", description
        self.serial_number = None


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
        (rechteck(dlg, feld(dlg, "Universum:")), 3, "rechts"),
        (rechteck(dlg, knopf(dlg, "Verbinden")), 4, "rechts"),
        (rechteck(dlg, _status(dlg, "Gespeichert:")), 5, "unten"),
    ], titel=dlg.windowTitle())


def _bild_artnet(ui):
    dlg = _dialog(ui, "Art-Net")
    return bild(ui, dlg, [
        (rechteck(dlg, knopf(dlg, "Art-Net aktivieren")), 1, "rechts"),
        (rechteck(dlg, feld(dlg, "Netzwerkkarte:")), 2, "rechts"),
        (rechteck(dlg, feld(dlg, "Universum:")), 3, "rechts"),
        (rechteck(dlg, feld(dlg, "Ziel-IP / Broadcast:")), 4, "rechts"),
        (rechteck(dlg, feld(dlg, "Art-Net Startuniversum:")), 5, "rechts"),
        (rechteck(dlg, knopf(dlg, "Übernehmen")), 6, "rechts"),
    ], titel=dlg.windowTitle())


def _bild_sacn(ui):
    dlg = _dialog(ui, "sACN (E1.31)")
    return bild(ui, dlg, [
        (rechteck(dlg, knopf(dlg, "sACN (E1.31) aktivieren")), 1, "rechts"),
        (rechteck(dlg, feld(dlg, "Universum:")), 2, "rechts"),
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
    if kopf[:5] != ["#", "Name", "Ausgang", "Patch (Port/IP)", "Ext. Universum"]:
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
        (rechteck(dlg, knopf(dlg, "+ Universum hinzufügen")), 4, "oben"),
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
    if not dm._lbl_ausgang.text().startswith("Universum 1 geht raus"):
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


# ── OUT-70: Assistent „Interface einrichten…“ ───────────────────────────────
# Nur gestellte Befunde (Beispiel-Ports, Beispiel-Kennungen, keine echte
# Seriennummer): der Assistent sucht dabei NICHT selbst (``befunde=``), es wird
# kein Port und kein USB-Geraet angefasst. Fuer den Testsignal-Reiter traegt
# :func:`_test_vorher` zwei Attrappen-Ausgaenge ein, die nichts senden (der
# Ausgabe-Thread ist in der Sandbox aus); :func:`_test_nachher` raeumt ab.

class _AttrappeAusgang:
    def __init__(self, port="", target_ip=""):
        self.port, self.target_ip = port, target_ip

    def send_dmx(self, data):
        pass

    def is_connected(self):
        return True

    def close(self):
        pass


def _beispiel_befunde():
    from src.core.dmx import interfaces as ifc
    roh = [
        ifc.RohGeraet(vid=0x0403, pid=0x6001, produkt="DMX USB PRO",
                      hersteller="ENTTEC", port=BEISPIEL_PORT, ort="1-2"),
        ifc.RohGeraet(vid=0x2008, pid=0x1066, produkt="USBDMX512",
                      hersteller="Sun-light", ort="1-3",
                      dev_pfad="/dev/bus/usb/001/007"),
        ifc.RohGeraet(vid=0x1A86, pid=0x7523, produkt="USB Serial",
                      hersteller="QinHeng", port="/dev/ttyUSB1", ort="1-4"),
    ]
    return ifc.erkenne(quellen=(roh, []), system="linux",
                       zugriff=lambda p: True, belegt=lambda p: [],
                       usb_bibliothek=True)


def _assistent(ui, reiter: int):
    from src.ui.widgets.interface_assistent import InterfaceAssistent
    dlg = InterfaceAssistent(ui.win, befunde=_beispiel_befunde(),
                             state=ui.state,
                             netzkarten=[dict(n) for n in BEISPIEL_NICS])
    dlg.resize(820, 640)
    dlg.tabs.setCurrentIndex(reiter)
    dlg.show()
    ui.pump(0.3)
    return dlg


def _bild_assistent(ui):
    from PySide6.QtWidgets import QLabel
    dlg = _assistent(ui, 0)
    pro = next(k for k in dlg.karten if "Enttec" in k.befund.titel)
    pro.zeige_ergebnis(f"Eingerichtet: {BEISPIEL_PORT} → Universum 1 (gespeichert)")
    pro.zeige_testen(1)
    ui.pump(0.3)
    kopf = next(lab for lab in dlg.findChildren(QLabel)
                if lab.text().startswith("LightOS liest nur"))
    cyl = next(k for k in dlg.karten if "CYL" in k.befund.titel)
    return bild(ui, dlg, [
        (rechteck(dlg, kopf), 1, "unten"),
        (rechteck(dlg, pro.lbl_ampel), 2, "links"),
        (rechteck(dlg, pro.btn_testen), 3, "rechts"),
        (rechteck(dlg, cyl.btn_einrichten), 4, "rechts"),
    ], titel=dlg.windowTitle())


def _test_vorher(ui):
    om = ui.state.output_manager
    om.add_universe(1)
    om.add_universe(2)
    om._enttec_outputs[1] = _AttrappeAusgang(port=BEISPIEL_PORT)
    om._artnet_outputs[2] = _AttrappeAusgang(target_ip=BEISPIEL_NODE)
    ui.info["_laser_vorher"] = dict(getattr(om, "_laser_adressen", {}) or {})
    om.set_laser_adressen({2: frozenset({1, 2, 3})})


def _test_nachher(ui):
    om = ui.state.output_manager
    for cb in list(om._tick_callbacks):
        if getattr(getattr(cb, "__self__", None), "universum", None) is not None:
            cb.__self__.stopp()
    om._enttec_outputs.pop(1, None)
    om._artnet_outputs.pop(2, None)
    om.set_laser_adressen(ui.info.pop("_laser_vorher", {}))


def _bild_testsignal(ui):
    from unittest import mock
    dlg = _assistent(ui, 2)
    with mock.patch.object(dlg, "_frage", lambda text, ja: True):
        dlg.testsignal_senden(1)
    ui.pump(0.3)
    zeilen = {z["universum"]: z for z in dlg.test_zeilen}
    if sorted(zeilen) != [1, 2]:
        raise SzenenFehler(f"unerwartete Ausgaenge im Testsignal-Reiter: {sorted(zeilen)}")
    laeuft, gesperrt = zeilen[1], zeilen[2]
    return bild(ui, dlg, [
        (rechteck(dlg, laeuft["knopf"]), 1, "links"),
        (rechteck(dlg, gesperrt["stand"]), 2, "unten"),
    ], titel=dlg.windowTitle())


# ── DOC-76: Assistent ohne Geraet, Testsignal als Ablauf ────────────────────

def schmal(bezug, w):
    from anleitungsbilder.szenen_osc import schmal as _schmal
    return _schmal(bezug, w)


def _bild_assistent_leer(ui):
    """Assistent mit leerem Suchergebnis (``befunde=[]``: es wird NICHT
    gesucht, kein USB-Geraet und kein Port wird angefasst)."""
    from src.ui.widgets.interface_assistent import InterfaceAssistent
    dlg = InterfaceAssistent(ui.win, befunde=[], state=ui.state,
                             netzkarten=[dict(n) for n in BEISPIEL_NICS])
    dlg.resize(820, 640)
    dlg.tabs.setCurrentIndex(0)
    dlg.show()
    ui.pump(0.3)
    if dlg.lbl_usb_stand.text() != "Nichts gefunden":
        raise SzenenFehler(f"Assistent meldet {dlg.lbl_usb_stand.text()!r}")
    leer = dlg._lbl_leer
    if leer is None or not leer.text().startswith("Kein DMX-Interface"):
        raise SzenenFehler("Erklärung für „Nichts gefunden“ fehlt")
    return bild(ui, dlg, [
        (schmal(dlg, dlg.lbl_usb_stand), 1, "rechts"),
        (rechteck(dlg, leer), 2, "unten"),
        (rechteck(dlg, dlg.btn_suchen), 3, "links"),
    ], titel=dlg.windowTitle())


def _ohne_sendethread(ui):
    """Sicherheitsnetz fuers Testsignal: der Ausgabe-Thread muss in der Sandbox
    aus sein — das Testsignal schreibt dann nur in den Universums-Puffer, es
    geht kein Paket hinaus."""
    if getattr(ui.state.output_manager, "_running", False):
        raise SzenenFehler("Ausgabe-Thread laeuft in der Sandbox — Testsignal-Szene abgebrochen")


def _zeilen(dlg):
    zeilen = {z["universum"]: z for z in dlg.test_zeilen}
    if sorted(zeilen) != [1, 2]:
        raise SzenenFehler(f"unerwartete Ausgaenge im Testsignal-Reiter: {sorted(zeilen)}")
    return zeilen


def _mit_rueckfrage(ui, dlg):
    """„Testsignal senden" fuer Universum 1 klicken; die Rueckfrage im modalen
    Loop aufnehmen und mit **Abbrechen** schliessen (es startet nichts).
    Liefert ein Bild-Widget: Assistent mit der Rueckfrage darueber."""
    from PySide6.QtCore import QPoint, QRect, QTimer
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtWidgets import QApplication, QLabel, QMessageBox
    from anleitungsbilder.szenen_erste_schritte import _titelleiste_malen
    ergebnis = {}

    def _aufnehmen():
        box = QApplication.activeModalWidget()
        if not isinstance(box, QMessageBox):
            ergebnis["fehler"] = "Rückfrage zum Testsignal ging nicht auf"
            return
        try:
            box.adjustSize()
            ui.pump(0.3)
            nein = knopf(box, "Abbrechen")
            if box.defaultButton() is not nein:
                ergebnis["fehler"] = "Vorgabe der Rückfrage ist nicht „Abbrechen“"
                return
            ergebnis["box"] = box.grab()
            ergebnis["titel"] = box.windowTitle()
            ergebnis["nein"] = rechteck(box, nein)
            ergebnis["ja"] = rechteck(box, knopf(box, "Testsignal senden"))
        finally:
            knopf(box, "Abbrechen").click()     # nichts wird gesendet

    QTimer.singleShot(400, _aufnehmen)
    antwort = dlg.testsignal_senden(1)
    if "fehler" in ergebnis:
        raise SzenenFehler(ergebnis["fehler"])
    if antwort != "abgebrochen" or dlg._laeufe:
        raise SzenenFehler(f"Rückfrage nicht abgebrochen ({antwort!r})")
    ui.pump(0.2)
    grund = dlg.grab()
    kasten = ergebnis["box"]
    kopf = 28
    x = (grund.width() - kasten.width()) // 2
    y = max(kopf + 4, (grund.height() - kasten.height() - kopf) // 2 + kopf)
    pix = QPixmap(grund)
    p = QPainter(pix)
    _titelleiste_malen(p, x, y - kopf, kasten.width(), ergebnis["titel"])
    p.drawPixmap(x, y, kasten)
    from PySide6.QtGui import QColor
    p.setPen(QColor("#59636e"))
    p.drawRect(QRect(x - 1, y - kopf - 1, kasten.width() + 1, kasten.height() + kopf + 1))
    p.end()
    flaeche = QLabel()
    flaeche.setFixedSize(pix.size())
    flaeche.setPixmap(pix)
    versatz = QPoint(x, y)
    return flaeche, [ergebnis["nein"].translated(versatz),
                     ergebnis["ja"].translated(versatz)], dlg.windowTitle()


def _test_frame(schritt: int):
    """0: Reiter Testsignal · 1: Rueckfrage (Vorgabe Abbrechen) · 2: laeuft,
    Knopf heisst Stopp · 3: gestoppt."""
    def _f(ui):
        from unittest import mock
        _ohne_sendethread(ui)
        dlg = _assistent(ui, 2)
        z = _zeilen(dlg)
        laeuft, gesperrt = z[1], z[2]
        if not gesperrt["gesperrt"]:
            raise SzenenFehler("Laser-Ausgang ist nicht gesperrt")
        if schritt == 0:
            return bild(ui, dlg, [
                (rechteck(dlg, laeuft["knopf"]), 1, "links"),
                (rechteck(dlg, gesperrt["stand"]), 2, "unten"),
            ], titel=dlg.windowTitle())
        if schritt == 1:
            flaeche, (nein, ja), titel = _mit_rueckfrage(ui, dlg)
            return bild(ui, flaeche, [(nein, 3, "unten"), (ja, 4, "unten")],
                        titel=titel)
        with mock.patch.object(dlg, "_frage", lambda text, ja: True):
            if dlg.testsignal_senden(1):
                raise SzenenFehler("Testsignal startet nicht")
        ui.pump(0.3)
        if schritt == 2:
            if laeuft["knopf"].text() != "Stopp":
                raise SzenenFehler("Knopf heisst waehrend des Laufs nicht „Stopp“")
            return bild(ui, dlg, [
                (rechteck(dlg, laeuft["knopf"]), 5, "links"),
                (schmal(dlg, laeuft["stand"]), 6, "rechts"),
            ], titel=dlg.windowTitle())
        dlg.testsignal_stoppen(1)
        ui.pump(0.2)
        if dlg._laeufe or not laeuft["stand"].text().startswith("Gestoppt"):
            raise SzenenFehler("Testsignal nicht gestoppt")
        return bild(ui, dlg, [
            (schmal(dlg, laeuft["stand"]), 7, "rechts"),
        ], titel=dlg.windowTitle())
    return _f


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
          titel="E/A → Output: Kanalwerte von Universum 1"),
    Szene("07_dmx_monitor", sektion="E/A", vorher=_dmx_monitor,
          dialog=_bild_dmx_monitor, nachher=_monitor_zurueck,
          titel="E/A → DMX Monitor"),
    Szene("08_warnungen", sektion="E/A", vorher=_ohne_ausgang,
          dialog=_bild_warnungen, nachher=_ausgang_zurueck,
          titel="Warnungen: Universum ohne Ausgang"),
    Szene("09_blackout_dmx_monitor", sektion="E/A", vorher=_blackout_an,
          dialog=_bild_blackout, nachher=_blackout_aus, groesse=(1600, STREIFEN_H),
          titel="BLACKOUT im DMX-Monitor: Licht 0, Pan/Tilt bleibt"),
    Szene("10_assistent", sektion="Programmer", dialog=_bild_assistent,
          titel="Assistent „Interface einrichten…“: Reiter USB-Geräte"),
    Szene("11_testsignal", sektion="Programmer", vorher=_test_vorher,
          dialog=_bild_testsignal, nachher=_test_nachher,
          titel="Assistent: Testsignal läuft (Stopp), Laser-Ausgang gesperrt"),
    Szene("12_assistent_nichts_gefunden", sektion="Programmer",
          dialog=_bild_assistent_leer,
          titel="Assistent ohne angeschlossenes Interface: „Nichts gefunden“ + Erklärung"),
    Szene("13_testsignal_ablauf", sektion="Programmer", vorher=_test_vorher,
          nachher=_test_nachher,
          titel="Testsignal: senden → Rückfrage (Vorgabe Abbrechen) → läuft (Stopp) → "
                "gestoppt; Laser-Ausgang gesperrt",
          frames=[Frame(dauer_s=2.0, dialog=_test_frame(0)),
                  Frame(dauer_s=3.0, dialog=_test_frame(1)),
                  Frame(dauer_s=2.0, dialog=_test_frame(2)),
                  Frame(dauer_s=2.2, dialog=_test_frame(3))],
          gif_zuschnitt=(388, 98, 824, 690)),
]
