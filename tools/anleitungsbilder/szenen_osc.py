"""DOC-76: Bilder fuer ``docs/anleitung_osc/`` (OSC: Adressen, Lernen, Rueckmeldung).

Neu erzeugen: ``venv/bin/python tools/anleitungsbilder.py osc``.

Dialog „OSC-Zuordnungen & Rückmeldung" (``src/ui/widgets/osc_einstellungen_dialog.py``).
Menue- und Dialogbilder entstehen mit den Hilfen aus ``szenen_erste_schritte.py``
(:func:`bild` & Co., s. dort).

Netz und Datenschutz:

* Die Beispiel-Zuordnungen stehen in einer eigenen Datei IM Sandbox-Ordner
  (``pfad=`` des Dialogs); die echte ``osc_zuordnungen.json`` wird weder
  gelesen noch geschrieben. **Übernehmen** wird nie gedrueckt — es startet
  damit auch keine Rueckmeldung und kein Sender.
* Der OSC-Server wird NICHT eingeschaltet. Das Lernen bekommt seine Nachricht
  ueber die Lern-API selbst (:meth:`OscZuordnung.empfange`, genau der Aufruf,
  den sonst der OSC-Thread macht) — es geht kein Paket uebers Netz, es wird
  kein Port geoeffnet. Absender und Ziel-IP sind Beispieladressen (RFC 5737).
"""
from __future__ import annotations

import os

from anleitungsbilder.runner import Frame, Szene, SzenenFehler
from anleitungsbilder.szenen_erste_schritte import (
    bild, knopf, menue_eintraege, menue_oeffnen, rechteck, reiter_rechteck,
    vereinigung,
)

ZIEL = "docs/anleitung_osc/img"

#: Beispiel-Absender und -Ziel (RFC 5737, PRIV-07).
BEISPIEL_ABSENDER = "192.0.2.30"
BEISPIEL_ZIEL_IP = "192.0.2.20"
#: Was das „Pult" beim Lernen schickt: grandMA3-artiger Fader 203 auf 75 %.
LERN_ADRESSE = "/Page1/Fader203"
LERN_ARGS = (75.0,)


def _beispiel_konfig():
    from src.core.osc import osc_zuordnung as oz
    zs = [
        oz.Zuordnung(adresse="/1/fader{n}", ziel=oz.ZIEL_FADER, bereich=oz.BEREICH_1),
        oz.Zuordnung(adresse="/1/push{n}", ziel=oz.ZIEL_GO),
        oz.Zuordnung(adresse="/szene/{an,start}", ziel=oz.ZIEL_FKT_START,
                     funktion="Lauflicht"),
        oz.Zuordnung(adresse="/tempo/tap", ziel=oz.ZIEL_TAP),
    ]
    rm = oz.RueckmeldeKonfig(aktiv=True, ziel_ip=BEISPIEL_ZIEL_IP, ziel_port=9000,
                             vorlage="lightos", executoren="1-10")
    return oz.Konfig(aktiv=True, zuordnungen=zs, rueckmeldung=rm)


def _pfad():
    """Beispiel-Datei neben der (umgelenkten) Sandbox-Datei — nie die echte."""
    from src.core.osc import osc_zuordnung as oz
    return os.path.join(os.path.dirname(oz.konfig_pfad()), "doku_osc_beispiel.json")


def _ohne_netz():
    """Sicherheitsnetz: der OSC-Server muss in der Sandbox aus sein."""
    from src.core.osc.osc_server import get_osc_server
    if get_osc_server().is_running():
        raise SzenenFehler("OSC-Server laeuft in der Sandbox — Szene abgebrochen")


def _dialog(ui, reiter: str = "Eingang"):
    from src.core.osc import osc_zuordnung as oz
    from src.ui.widgets.osc_einstellungen_dialog import OscEinstellungenDialog
    _ohne_netz()
    pfad = _pfad()
    if not oz.speichere_konfig(_beispiel_konfig(), pfad):
        raise SzenenFehler("Beispiel-Konfiguration nicht schreibbar")
    # server_laeuft=True: die Statuszeile zeigt den Normalfall (Server an) —
    # gestartet wird er dafuer nicht.
    dlg = OscEinstellungenDialog(ui.win, pfad=pfad, server_laeuft=True)
    for i in range(dlg.tabs.count()):
        if dlg.tabs.tabText(i) == reiter:
            dlg.tabs.setCurrentIndex(i)
            break
    else:
        raise SzenenFehler(f"Reiter '{reiter}' fehlt im OSC-Dialog")
    dlg.resize(940, 520)
    dlg.show()
    ui.pump(0.3)
    return dlg


def _aufraeumen(ui):
    from src.core.osc import osc_zuordnung as oz
    oz.get_osc_zuordnung().lerne(None)
    try:
        os.remove(_pfad())
    except OSError:
        pass


def schmal(bezug, w, zugabe: int = 14):
    """Rechteck von ``w``, aber nur so breit wie sein Inhalt (Haken mit Text,
    Statuszeile): sonst umrahmt die Markierung die ganze leere Zeile."""
    from PySide6.QtCore import QRect
    r = rechteck(bezug, w)
    text = w.text() if hasattr(w, "text") else ""
    breite = w.sizeHint().width() if not hasattr(w, "wordWrap") else \
        w.fontMetrics().horizontalAdvance(text) + zugabe
    return QRect(r.x(), r.y(), min(r.width(), max(24, breite)), r.height())


def _zeile(dlg, r: int):
    """Rechteck einer ganzen Tabellenzeile in Dialog-Koordinaten."""
    from PySide6.QtCore import QRect
    tab = dlg.tabelle
    links = tab.cellWidget(r, 0)
    rechts = tab.cellWidget(r, tab.columnCount() - 1)
    a, b = rechteck(dlg, links), rechteck(dlg, rechts)
    return QRect(a.topLeft(), b.bottomRight()).adjusted(-2, -2, 2, 2)


# ── Szenen ──────────────────────────────────────────────────────────────────

def _bild_menue(ui):
    menu, pos = menue_oeffnen(ui, "Ausgabe")
    server, zuordnung = menue_eintraege(
        menu, ["OSC-Server (Port 7770)", "OSC-Zuordnungen && Rückmeldung…"])
    return bild(ui, menu, [(server, 1, "rechts"), (zuordnung, 2, "rechts")],
                pos=pos, abdunkeln=False)


def _bild_eingang(ui):
    dlg = _dialog(ui, "Eingang")
    if dlg.tabelle.rowCount() != 4:
        raise SzenenFehler("OSC-Dialog zeigt die Beispiel-Zuordnungen nicht")
    return bild(ui, dlg, [
        (schmal(dlg, dlg.check_aktiv), 1, "rechts"),
        (rechteck(dlg, dlg.tabelle.cellWidget(0, 0)), 2, "unten"),
        (rechteck(dlg, dlg.tabelle.cellWidget(2, 5)), 3, "unten"),
        (rechteck(dlg, knopf(dlg, "+ Zuordnung")), 4, "oben"),
        (rechteck(dlg, knopf(dlg, "Lernen")), 5, "oben"),
        (rechteck(dlg, knopf(dlg, "Übernehmen")), 6, "oben"),
    ], titel=dlg.windowTitle())


def _bild_rueckmeldung(ui):
    dlg = _dialog(ui, "Rückmeldung")
    if dlg.edit_ip.text() != BEISPIEL_ZIEL_IP:
        raise SzenenFehler("Rückmeldung zeigt das Beispiel-Ziel nicht")
    ziel = vereinigung([rechteck(dlg, dlg.edit_ip), rechteck(dlg, dlg.spin_port)])
    return bild(ui, dlg, [
        (reiter_rechteck(dlg, dlg, "Rückmeldung"), 1, "unten"),
        (schmal(dlg, dlg.check_rm), 2, "rechts"),
        (ziel, 3, "rechts"),
        (rechteck(dlg, dlg.combo_vorlage), 4, "rechts"),
        (rechteck(dlg, dlg.edit_exec), 5, "rechts"),
        (rechteck(dlg, knopf(dlg, "Alles neu senden")), 6, "links"),
    ], titel=dlg.windowTitle())


# ── GIF: Lernen ─────────────────────────────────────────────────────────────

def _lern_dialog(ui, schritt: int):
    """Schritt 0: vor dem Lernen · 1: Lernen gedrueckt, wartet · 2: Nachricht
    kam an (ueber die Lern-API, ohne Netz) und ist eingetragen."""
    from src.core.osc import osc_zuordnung as oz
    dlg = _dialog(ui, "Eingang")
    dlg.tabelle.clearSelection()
    dlg.tabelle.setCurrentCell(-1, -1)
    ui.pump(0.1)
    lernen = dlg.btn_lernen
    if schritt >= 1:
        lernen.setChecked(True)
        ui.pump(0.1)
        if not oz.get_osc_zuordnung().lernt:
            raise SzenenFehler("Lernen ist nicht scharf")
    if schritt >= 2:
        oz.get_osc_zuordnung().empfange(LERN_ADRESSE, LERN_ARGS, BEISPIEL_ABSENDER)
        ui.pump(0.3)
        if dlg.tabelle.rowCount() != 5:
            raise SzenenFehler("Gelernte Adresse wurde nicht eingetragen")
        if dlg.tabelle.cellWidget(4, 0).text() != "/Page1/Fader{n}":
            raise SzenenFehler(f"Gelernt: {dlg.tabelle.cellWidget(4, 0).text()!r}")
    return dlg


def _lern_bild(schritt: int):
    def _f(ui):
        dlg = _lern_dialog(ui, schritt)
        status = schmal(dlg, dlg.lbl_status)
        if schritt == 0:
            kreise = [(rechteck(dlg, dlg.btn_lernen), 1, "oben")]
        elif schritt == 1:
            kreise = [(rechteck(dlg, dlg.btn_lernen), 1, "oben"), (status, 2, "rechts")]
        else:
            kreise = [(_zeile(dlg, 4), 3, "unten"), (status, 4, "rechts")]
        return bild(ui, dlg, kreise, titel=dlg.windowTitle())
    return _f


SZENEN = [
    Szene("01_menue_osc", sektion="Programmer", unterreiter="Attribute",
          dialog=_bild_menue, titel="Menü Ausgabe → OSC-Server und OSC-Zuordnungen"),
    Szene("02_eingang", sektion="Programmer", dialog=_bild_eingang,
          nachher=_aufraeumen,
          titel="Reiter Eingang mit Beispiel-Zuordnungen (Muster, Funktion, Lernen)"),
    Szene("03_rueckmeldung", sektion="Programmer", dialog=_bild_rueckmeldung,
          nachher=_aufraeumen,
          titel="Reiter Rückmeldung: Ziel 192.0.2.20:9000, Vorlage LightOS"),
    Szene("04_lernen", sektion="Programmer", nachher=_aufraeumen,
          titel="Lernen: Knopf → wartet → Adresse /Page1/Fader{n} eingetragen",
          frames=[Frame(dauer_s=1.6, dialog=_lern_bild(0)),
                  Frame(dauer_s=1.8, dialog=_lern_bild(1)),
                  Frame(dauer_s=3.2, dialog=_lern_bild(2))],
          gif_zuschnitt=(329, 171, 943, 555)),
]
