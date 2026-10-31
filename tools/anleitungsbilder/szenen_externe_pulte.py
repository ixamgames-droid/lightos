"""DOC-76: Bilder fuer ``docs/anleitung_externe_pulte/`` (Externe Pulte).

Neu erzeugen: ``venv/bin/python tools/anleitungsbilder.py externe_pulte``.

Kasten „Fernsteuerung (Pult steuert LightOS)" im Reiter DMX-Eingang des
Dialogs „Ausgabe konfigurieren" (``src/ui/widgets/dmx_fernsteuerung_box.py``).
Der Dialog entsteht wie in ``szenen_ausgabe_einrichten.py`` (Beispiel-Ports
und -Netzwerkkarten, RFC 5737).

Netz und Datenschutz:

* Die Beispiel-Zuordnungen stehen nur in der (umgelenkten) Sandbox-Datei der
  Fernsteuerung und werden danach auf den Stand davor zurueckgesetzt.
* **Übernehmen** wird nie gedrueckt: es startet keinen Empfaenger, es wird
  kein Port geoeffnet. Ein Sicherheitsnetz bricht ab, falls der Empfaenger
  der Fernsteuerung doch laeuft.
* Die Liste der Netzwerkkarten im Kasten „Empfang" wird waehrend des
  Dialog-Aufbaus durch die Beispielkarten ersetzt.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

from anleitungsbilder.runner import Szene, SzenenFehler
from anleitungsbilder.szenen_ausgabe_einrichten import BEISPIEL_NICS, _beispiel_umgebung
from anleitungsbilder.szenen_erste_schritte import bild, knopf, rechteck

ZIEL = "docs/anleitung_externe_pulte/img"


@contextmanager
def _beispiel_fernsteuerung():
    from src.core.dmx import fernsteuerung as fs
    from src.ui.widgets import dmx_empfang_box as eb
    pfad = fs.konfig_pfad()
    alt = open(pfad, encoding="utf-8").read() if os.path.exists(pfad) else None
    konfig = fs.Konfig(aktiv=True, zuordnungen=[
        fs.Zuordnung(quelle=fs.QUELLE_ARTNET, universum=1, kanal=1,
                     ziel=fs.ZIEL_FADER, executor=1),
        fs.Zuordnung(quelle=fs.QUELLE_ARTNET, universum=1, kanal=2,
                     ziel=fs.ZIEL_GO, executor=1, schwelle=50),
        fs.Zuordnung(quelle=fs.QUELLE_SACN, universum=1, kanal=10,
                     ziel=fs.ZIEL_GM),
    ])
    if not fs.speichere_konfig(konfig, pfad):
        raise SzenenFehler("Beispiel-Fernsteuerung nicht schreibbar")
    alt_karten = eb._karten
    eb._karten = lambda: [dict(n) for n in BEISPIEL_NICS]
    try:
        yield
    finally:
        eb._karten = alt_karten
        if alt is None:
            os.remove(pfad)
        else:
            with open(pfad, "w", encoding="utf-8") as f:
                f.write(alt)


def _empfaenger_aus():
    """Sicherheitsnetz: in der Sandbox darf kein Art-Net-/sACN-Empfaenger
    laufen (vorher und nachher geprueft)."""
    from src.core.dmx.artnet_input import get_artnet_receiver
    from src.core.dmx.sacn_input import get_sacn_receiver
    for name, rx in (("Art-Net", get_artnet_receiver()), ("sACN", get_sacn_receiver())):
        if rx.is_running():
            raise SzenenFehler(f"{name}-Empfaenger laeuft in der Sandbox")


def _bild_fernsteuerung(ui):
    from PySide6.QtWidgets import QTabWidget
    from src.ui.widgets.output_config import OutputConfigDialog
    _empfaenger_aus()
    with _beispiel_umgebung(), _beispiel_fernsteuerung():
        dlg = OutputConfigDialog(ui.win)
    dlg.resize(900, 820)
    tabs = dlg.findChild(QTabWidget)
    for i in range(tabs.count()):
        if tabs.tabText(i) == "DMX-Eingang":
            tabs.setCurrentIndex(i)
            break
    else:
        raise SzenenFehler("Reiter 'DMX-Eingang' fehlt")
    dlg.show()
    ui.pump(0.3)
    box = dlg._fernsteuerung_box
    if box.tabelle.rowCount() != 3:
        raise SzenenFehler("Fernsteuerung zeigt die Beispiel-Zuordnungen nicht")
    # bis ganz nach unten rollen: der Kasten steht am Ende des Reiters
    rollen = tabs.currentWidget()
    rollen.ensureWidgetVisible(box, 0, 0)
    rollen.verticalScrollBar().setValue(rollen.verticalScrollBar().maximum())
    box.tabelle.selectRow(1)
    ui.pump(0.3)
    from anleitungsbilder.szenen_osc import schmal
    tab = box.tabelle
    from PySide6.QtCore import QRect

    def _spalte(c):
        kopf = tab.horizontalHeader()
        oben = kopf.mapTo(dlg, kopf.rect().topLeft())
        unten = tab.viewport().mapTo(dlg, tab.visualRect(
            tab.model().index(tab.rowCount() - 1, c)).bottomLeft())
        x = tab.columnViewportPosition(c)
        return QRect(oben.x() + x + 3, oben.y(), tab.columnWidth(c) - 6,
                     unten.y() - oben.y())
    _empfaenger_aus()
    return bild(ui, dlg, [
        (rechteck(dlg, box), 1, "links"),
        (_spalte(4), 2, "oben"),
        (_spalte(5), 3, "oben"),
        (rechteck(dlg, knopf(box, "+ Zuordnung")), 4, "links"),
        (rechteck(dlg, knopf(box, "Entfernen")), 5, "unten"),
        (schmal(dlg, box.check_aktiv), 6, "rechts"),
        (rechteck(dlg, box.btn_uebernehmen), 7, "links"),
    ], titel=dlg.windowTitle())


SZENEN = [
    Szene("01_fernsteuerung", sektion="Programmer", dialog=_bild_fernsteuerung,
          titel="Ausgabe-Dialog, Reiter DMX-Eingang: Kasten Fernsteuerung mit "
                "drei Beispiel-Zuordnungen"),
]
