"""DOC-16: Bilder fuer ``docs/anleitung_vc/`` (Virtual Console bauen & designen).

Neu erzeugen: ``venv/bin/python tools/anleitungsbilder.py vc``.

Grundlage ist Bank 1 der Doku-Demo-Show (drei Farb-Szenen, Lauflicht,
Regenbogen, Kreis, vier Fader). Die frueheren Bilder dieses Ordners stammten aus
einer archivierten Show, die nicht im Repo liegt, und zeigten die alte
Oberflaeche.

Bank 2 „Tempo & Musik“ legen die Szenen selbst an (:func:`bank2_anlegen`) —
genau die Bausteine, die die Anleitung in den Abschnitten 6 und 7 nennt. Die
Musik-Anleitung (``szenen_musik_sync.py``) benutzt dieselbe Bank.

Dialoge (Drop-Karte, Widget-Galerie, Konflikt-Karte, Button-Einstellungen,
MIDI Teach) werden ueber ihre echten Klassen gebaut und NICHT ausgefuehrt: das
Bild entsteht, der Dialog wird geschlossen, an der Show aendert sich nichts.
"""
from __future__ import annotations

from anleitungsbilder.runner import Szene, SzenenFehler
from anleitungsbilder.szenen_erste_schritte import (
    bild, knopf, platz_oben, rechteck, vereinigung)

ZIEL = "docs/anleitung_vc/img"

#: objectNames der Widgets, die Bank 2 anlegt (zum Wiederfinden/Aufraeumen).
BANK2 = "doku_bank2_"


# ── Zugriff ─────────────────────────────────────────────────────────────────

def vc(ui):
    return ui.win._vc_view


def canvas(ui):
    return vc(ui)._canvas


def funktion(name: str) -> int:
    from src.core.engine.function_manager import get_function_manager
    for f in get_function_manager().all():
        if f.name == name:
            return f.id
    raise SzenenFehler(f"Funktion „{name}“ fehlt in der Doku-Demo")


def vc_widget(ui, caption: str):
    """Sichtbares VC-Widget mit dieser Beschriftung auf der aktiven Bank."""
    from src.ui.virtualconsole.vc_widget import VCWidget
    for w in canvas(ui).findChildren(VCWidget):
        if w.isVisible() and getattr(w, "caption", None) == caption:
            return w
    raise SzenenFehler(f"VC-Widget „{caption}“ nicht sichtbar")


def bearbeiten(ui, an: bool):
    btn = vc(ui)._btn_edit
    if btn.isChecked() != an:
        btn.setChecked(an)
    ui.pump(0.3)


def bank(ui, nr: int):
    """Bank ``nr`` (0-basiert) zeigen."""
    canvas(ui).set_active_bank(nr)
    ui.pump(0.3)


# ── Bank 2 „Tempo & Musik“ ──────────────────────────────────────────────────

def bank2_anlegen(ui):
    """Legt Bank 2 an (falls noch nicht da) und zeigt sie.

    Aufbau wie in der Anleitung beschrieben: Ueberschrift, BPM-Anzeige, TAP,
    AUTO/MAN, Musik-BPM, BPM -/+, BPM-Fader; daneben die Musik-Anzeige mit
    den drei Media-Tasten.
    """
    from PySide6.QtCore import QPoint
    from src.ui.virtualconsole.vc_button import ButtonAction
    from src.ui.virtualconsole.vc_slider import SliderMode
    from PySide6.QtWidgets import QWidget
    c = canvas(ui)
    bank(ui, 1)
    if c.findChild(QWidget, BANK2 + "tap") is not None:
        return
    teile = [
        ("titel", "VCLabel", (20, 20), {"caption": "TEMPO & MUSIK"}),
        ("bpm", "VCBpmDisplay", (20, 80), {"caption": "TEMPO"}),
        ("tap", "VCButton", (260, 80), {"caption": "TAP", "action": ButtonAction.TAP}),
        ("modus", "VCButton", (420, 80), {"caption": "AUTO / MAN",
                                           "action": ButtonAction.BPM_MODE_TOGGLE}),
        ("audio", "VCButton", (580, 80), {"caption": "Musik-BPM",
                                           "action": ButtonAction.AUDIO_BPM}),
        ("minus", "VCButton", (260, 180), {"caption": "BPM −",
                                            "action": ButtonAction.BPM_NUDGE_DOWN}),
        ("plus", "VCButton", (420, 180), {"caption": "BPM +",
                                           "action": ButtonAction.BPM_NUDGE_UP}),
        ("fader", "VCSlider", (20, 300), {"caption": "BPM", "mode": SliderMode.BPM}),
        ("musik", "VCSongInfo", (780, 80), {"caption": "MUSIK"}),
        ("zurueck", "VCButton", (780, 300), {"caption": "<<",
                                              "action": ButtonAction.MEDIA_PREV}),
        ("play", "VCButton", (940, 300), {"caption": "> / ||",
                                           "action": ButtonAction.MEDIA_PLAY_PAUSE}),
        ("vor", "VCButton", (1100, 300), {"caption": ">>",
                                           "action": ButtonAction.MEDIA_NEXT}),
    ]
    for name, typ, (x, y), attr in teile:
        w = c._add_widget(typ, QPoint(x, y))
        if w is None:
            raise SzenenFehler(f"VC-Widget-Typ {typ} nicht anlegbar")
        w.setObjectName(BANK2 + name)
        for k, v in attr.items():
            setattr(w, k, v)
        w.setVisible(c.on_active_bank(w))
        w.update()
    ui.pump(0.5)


def bank2_widget(ui, name: str):
    from PySide6.QtWidgets import QWidget
    w = canvas(ui).findChild(QWidget, BANK2 + name)
    if w is None or not w.isVisible():
        raise SzenenFehler(f"Bank-2-Widget {name} nicht sichtbar")
    return w


# ── Szenen ──────────────────────────────────────────────────────────────────

def _start(ui):
    bearbeiten(ui, False)
    bank(ui, 0)


def statuszeile(ui):
    """Rechteck des TEXTES der Statuszeile „Aktiver Effekt“ (die Zeile selbst
    ist fensterbreit — ein Rahmen darum saesse auf allem)."""
    from PySide6.QtCore import QRect
    lbl = vc(ui)._lbl_active_fx
    r = rechteck(ui.win, lbl)
    b = lbl.fontMetrics().horizontalAdvance(lbl.text()) + 24
    return QRect(r.x(), r.y(), min(r.width(), b), r.height())


def bank_nav(ui):
    v = vc(ui)
    w = ui.win
    return vereinigung([rechteck(w, v._btn_bank_prev), rechteck(w, v._lbl_bank),
                        rechteck(w, v._btn_bank_next)])


def _bild_ueberblick(ui):
    v = vc(ui)
    w = ui.win
    with platz_oben(ui, v):
        return bild(ui, kreise=[
            (rechteck(w, v._btn_edit), 1, "oben"),
            (bank_nav(ui), 2, "oben"),
            (statuszeile(ui), 3, "rechts"),
            (rechteck(w, v._sidebar), 4, "links"),
        ])


def _bild_bearbeiten(ui):
    bearbeiten(ui, True)
    v = vc(ui)
    w = ui.win
    with platz_oben(ui, v):
        knoepfe = [knopf(v._toolbar_widget, t) for t in ("Button", "Live-Edit")]
        leiste = vereinigung([rechteck(w, k) for k in knoepfe])
        undo = vereinigung([rechteck(w, knopf(v._toolbar_widget, t))
                            for t in ("↶", "↷")])
        return bild(ui, kreise=[
            (rechteck(w, v._btn_edit), 1, "oben"),
            (leiste, 2, "oben"),
            (undo, 3, "oben"),
        ])


def _drop_karte(ui):
    from src.ui.virtualconsole.vc_drop_panel import VCDropPanel
    dlg = VCDropPanel(funktion("Regenbogen"), parent=canvas(ui))
    dlg.adjustSize()
    dlg.show()
    ui.pump(0.3)
    return dlg


def _bild_drop_karte(ui):
    from PySide6.QtWidgets import QCheckBox
    bearbeiten(ui, True)
    dlg = _drop_karte(ui)
    zeilen = [r for r in dlg._rows if len(r.choices) > 1]
    if not zeilen:
        raise SzenenFehler("Drop-Karte ohne Zeile mit Widget-Wahl")
    toggle = next((c for c in dlg.findChildren(QCheckBox)
                   if c.isVisible() and c.isChecked()), None)
    if toggle is None:
        raise SzenenFehler("Drop-Karte: keine vorangekreuzte Zeile")
    return bild(ui, dlg, [
        (rechteck(dlg, toggle), 1, "links"),
        (rechteck(dlg, zeilen[0].btn), 2, "rechts"),
        (rechteck(dlg, _mehr_parameter(dlg)), 3, "links"),
        (rechteck(dlg, knopf(dlg, "Erstellen")), 4, "unten"),
    ], titel=dlg.windowTitle())


def _mehr_parameter(dlg):
    """Kopf des zugeklappten Bereichs „Mehr Parameter (N)“."""
    from PySide6.QtWidgets import QAbstractButton, QLabel
    for klasse in (QAbstractButton, QLabel):
        for w in dlg.findChildren(klasse):
            if w.isVisible() and "Mehr Parameter" in w.text():
                return w
    raise SzenenFehler("Drop-Karte: „Mehr Parameter“ fehlt")


def _bild_galerie(ui):
    from src.ui.virtualconsole.vc_widget_gallery import VCWidgetGallery
    bearbeiten(ui, True)
    karte = _drop_karte(ui)
    zeile = next(r for r in karte._rows if len(r.choices) > 1)
    dlg = VCWidgetGallery(zeile.choices, current=zeile.widget_type, parent=karte)
    karte.close()
    dlg.adjustSize()
    dlg.show()
    ui.pump(0.3)
    from PySide6.QtWidgets import QDialogButtonBox
    ok = dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok)
    return bild(ui, dlg, [(rechteck(dlg, ok), 1, "links")], titel=dlg.windowTitle())


def _bild_konflikt(ui):
    # Wie ``VCCanvas._ask_coupling_resolution``: „Kreis“ auf den Fader „Tempo“
    # gezogen, der schon den Regenbogen steuert.
    from src.ui.virtualconsole.vc_conflict_card import VCConflictCard
    from src.ui.virtualconsole.vc_effect_meta import effect_name
    bearbeiten(ui, True)
    fader = vc_widget(ui, "Tempo")
    dlg = VCConflictCard(effect_name(funktion("Kreis")), [fader.caption],
                         parent=canvas(ui))
    dlg.adjustSize()
    dlg.show()
    ui.pump(0.3)
    from src.ui.virtualconsole.vc_conflict_card import _CHOICES
    kreise = [(rechteck(dlg, knopf(dlg, label)), i, "rechts")
              for i, (_k, label, _t) in enumerate(_CHOICES, 1)]
    return bild(ui, dlg, kreise, titel=dlg.windowTitle())


def _bild_einstellungen(ui):
    """„Button Einstellungen“ der Taste „Rot“ — echter Aufruf, im modalen
    Loop aufgenommen und mit Cancel geschlossen."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox
    from anleitungsbilder.szenen_erste_schritte import feld
    bearbeiten(ui, True)
    taste = vc_widget(ui, "Rot")
    ergebnis = {}

    def _aufnehmen():
        dlg = QApplication.activeModalWidget()
        if not isinstance(dlg, QDialog):
            ergebnis["fehler"] = "Dialog „Button Einstellungen“ ging nicht auf"
            return
        try:
            dlg.adjustSize()
            ui.pump(0.3)
            aktion = feld(dlg, "Aktion:")
            ok = dlg.findChild(QDialogButtonBox).button(
                QDialogButtonBox.StandardButton.Ok)
            ergebnis["bild"] = bild(ui, dlg, [
                (rechteck(dlg, aktion), 1, "rechts"),
                (rechteck(dlg, ok), 2, "links"),
            ], titel=dlg.windowTitle())
        except SzenenFehler as e:
            ergebnis["fehler"] = str(e)
        finally:
            dlg.reject()

    QTimer.singleShot(300, _aufnehmen)
    taste._open_properties()
    if "fehler" in ergebnis:
        raise SzenenFehler(ergebnis["fehler"])
    if "bild" not in ergebnis:
        raise SzenenFehler("Dialog wurde nicht aufgenommen")
    return ergebnis["bild"]


def _lauflicht_an(ui):
    bearbeiten(ui, False)
    bank(ui, 0)
    vc_widget(ui, "Lauflicht")._trigger(True)
    vc_widget(ui, "Lauflicht")._trigger(False)
    ui.pump(1.0)


def _bild_aktiv(ui):
    w = ui.win
    return bild(ui, kreise=[
        (rechteck(w, vc_widget(ui, "Lauflicht")), 1, "unten"),
        (statuszeile(ui), 2, "rechts"),
    ])


def _alles_aus(ui):
    from src.core.engine.function_manager import get_function_manager
    get_function_manager().stop_all()
    ui.pump(0.5)


def _bild_bank2(ui):
    bearbeiten(ui, False)
    bank2_anlegen(ui)
    w = ui.win

    def _flaeche(*namen):
        return vereinigung([rechteck(w, bank2_widget(ui, n)) for n in namen])
    with platz_oben(ui, vc(ui)):
        return bild(ui, kreise=[
            (bank_nav(ui), 1, "oben"),
            (_flaeche("bpm"), 2, "unten"),
            (_flaeche("tap", "modus", "audio", "minus", "plus"), 3, "rechts"),
            (_flaeche("fader"), 4, "rechts"),
            (_flaeche("musik", "zurueck", "play", "vor"), 5, "rechts"),
        ])


def _bild_midi_teach(ui):
    from src.ui.widgets.midi_teach_dialog import MidiTeachDialog
    bearbeiten(ui, True)
    bank(ui, 0)
    taste = vc_widget(ui, "Rot")
    # Der Dialog nennt die MIDI-Eingaenge DIESES Rechners (Portnamen des
    # Baurechners gehoeren nicht ins Bild): fuers Bild wie ohne Geraet.
    from src.core.midi.midi_manager import get_midi_manager
    mm = get_midi_manager()
    alt = mm.list_inputs
    mm.list_inputs = lambda: []
    try:
        dlg = MidiTeachDialog(taste, current=taste.current_midi_binding(),
                              accept_kinds=taste._midi_teach_kinds(),
                              title=f"MIDI Teach — {taste.caption}")
    finally:
        mm.list_inputs = alt
    dlg.adjustSize()
    dlg.show()
    ui.pump(0.3)
    from PySide6.QtWidgets import QDialogButtonBox
    ok = dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok)
    return bild(ui, dlg, [
        (rechteck(dlg, dlg._view), 1, "rechts"),
        (rechteck(dlg, knopf(dlg, "Bindung entfernen")), 2, "rechts"),
        (rechteck(dlg, ok), 3, "unten"),
    ], titel=dlg.windowTitle())


def _ende(ui):
    _alles_aus(ui)
    bearbeiten(ui, False)
    bank(ui, 0)


# ── 10: Kiosk-Streifen mit NOT-AUS-Bestaetigung (DOC-75) ──────────────────
#
# Der Streifen existiert nur in einem Fenster, das mit ``kiosk=True`` gebaut
# wurde. Die Szene baut dafuer ein ZWEITES Hauptfenster im Kiosk-Modus (wie
# ``tests/test_las41_kiosk_notaus_bestaetigung.py``) auf demselben Zustand,
# loest den LASER NOT-AUS ueber dessen echten Knopf aus (Sandbox, kein
# Ausgabe-Thread — nichts wird gesendet), nimmt den oberen Rand auf, loest
# den NOT-AUS in der Sandbox wieder und baut das Fenster ab.

_KIOSK_H = 110          # Hoehe aus dem Fenster: Streifen, roter Balken, Rand
_KIOSK_X0 = 400         # links abgeschnitten (dort steht nur leere Konsole)
_KIOSK_RAND = 44        # Rand oben fuer die Nummernkreise


def _bild_kiosk(ui):
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtGui import QColor, QPainter, QPixmap
    from PySide6.QtWidgets import QLabel, QWidget
    from anleitungsbilder import marker
    from anleitungsbilder.szenen_erste_schritte import kreise_malen
    from anleitungsbilder.szenen_laser import notaus_aufraeumen
    from src.ui.main_window import MainWindow
    if getattr(ui.state, "laser_estop_active", False):
        raise SzenenFehler("NOT-AUS steht schon vor dem Kiosk-Bild")
    kw = MainWindow(kiosk=True, touch=False)
    try:
        kw._hw_timer.stop()
        kw.resize(1600, 900)
        kw.show()
        ui.pump(1.0)
        leiste = getattr(kw, "_notaus_leiste", None)
        if leiste is None or not leiste.isVisible():
            raise SzenenFehler("Kiosk-Streifen fehlt")
        kw._btn_laser_notaus.click()
        ui.pump(0.6)
        meldung = getattr(kw, "_kiosk_notaus_meldung", None)
        if meldung is None or not meldung.isVisible():
            raise SzenenFehler("Roter NOT-AUS-Balken im Kiosk erscheint nicht")
        if "NOT-AUS ausgelöst" not in meldung.text():
            raise SzenenFehler(f"Balkentext: {meldung.text()!r}")
        gm = leiste.findChild(QWidget, "kioskGmGruppe")
        teile = [gm, kw._btn_stop_all_kiosk, kw._btn_blackout_kiosk,
                 kw._btn_laser_notaus]
        if any(t is None or not t.isVisible() for t in teile):
            raise SzenenFehler("GM, STOP ALL, BLACKOUT oder LASER NOT-AUS fehlt im Streifen")
        # Ausschnitt rechts (Streifen + Balkentext); oben ein Rand fuer die
        # Nummernkreise — der Streifen ist zu schmal, Kreise saessen sonst
        # auf den Knopftexten.
        x0 = _KIOSK_X0
        roh = kw.grab(QRect(x0, 0, kw.width() - x0, _KIOSK_H))
        pix = QPixmap(roh.width(), roh.height() + _KIOSK_RAND)
        pix.fill(QColor("#202020"))
        p = QPainter(pix)
        p.drawPixmap(0, _KIOSK_RAND, roh)
        p.end()
        versatz = QPoint(-x0, _KIOSK_RAND)

        def r(widget):
            return rechteck(kw, widget).translated(versatz)
        frei = [q.translated(versatz) for q in marker.hindernisse(kw)
                if q.top() < _KIOSK_H]
        kreise_malen(pix, [
            (r(gm), 1, "oben"),
            (r(kw._btn_stop_all_kiosk), 2, "oben"),
            (r(kw._btn_blackout_kiosk), 3, "oben"),
            (r(kw._btn_laser_notaus), 4, "oben"),
            (r(meldung), 5, "unten"),
        ], frei)
    finally:
        notaus_aufraeumen(ui)
        kw.hide()
        kw.deleteLater()
        ui.pump(0.3)
    flaeche = QLabel()
    flaeche.setFixedSize(pix.width(), pix.height())
    flaeche.setPixmap(pix)
    return flaeche


SZENEN = [
    Szene("01_vc_ueberblick", sektion="Virtual Console", vorher=_start,
          dialog=_bild_ueberblick,
          titel="Virtual Console: Bank 1 der Doku-Demo, Bearbeiten, Bänke, "
                "Statuszeile, Bibliothek"),
    Szene("02_bearbeiten_modus", sektion="Virtual Console", dialog=_bild_bearbeiten,
          titel="Bearbeiten-Modus mit Werkzeugleiste und Rückgängig/Wiederholen"),
    Szene("03_drop_karte", sektion="Virtual Console", dialog=_bild_drop_karte,
          titel="Drop-Karte „Effekt einrichten“ für den Regenbogen"),
    Szene("04_widget_galerie", sektion="Virtual Console", dialog=_bild_galerie,
          titel="Widget-Galerie „Widget wählen“"),
    Szene("05_konflikt_karte", sektion="Virtual Console", dialog=_bild_konflikt,
          titel="Konflikt-Karte „Regler ist schon belegt“ (Kreis auf den Fader Tempo)"),
    Szene("06_button_einstellungen", sektion="Virtual Console",
          dialog=_bild_einstellungen,
          titel="Button-Einstellungen: Aktion wählen"),
    Szene("07_taste_aktiv", sektion="Virtual Console", vorher=_lauflicht_an,
          dialog=_bild_aktiv, nachher=_alles_aus,
          titel="Run-Modus: „Lauflicht“ läuft, Statuszeile nennt den Effekt"),
    Szene("08_bank2_tempo_musik", sektion="Virtual Console", dialog=_bild_bank2,
          titel="Bank 2: Tempo- und Musik-Bausteine"),
    Szene("09_midi_teach", sektion="Virtual Console", dialog=_bild_midi_teach,
          nachher=_ende,
          titel="MIDI Teach mit APC-mini-Abbild"),
    Szene("10_kiosk_streifen", sektion="Virtual Console", dialog=_bild_kiosk,
          groesse=(1600 - _KIOSK_X0, _KIOSK_H + _KIOSK_RAND),
          titel="Kiosk: Streifen GM, STOP ALL, BLACKOUT, LASER NOT-AUS und "
                "roter NOT-AUS-Balken"),
]
