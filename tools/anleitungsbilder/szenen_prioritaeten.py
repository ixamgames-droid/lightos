"""DOC-73: Bilder fuer ``docs/anleitung_prioritaeten/ANLEITUNG.md`` — „Wer
gewinnt? Prioritäten für Effekte" (ENG-35, ENG-39, VCB-46).

Neu erzeugen::

    venv/bin/python tools/anleitungsbilder.py prioritaeten

Grundlage ist die Doku-Demo-Show (acht PARs, Gruppen „Alle PAR" und „PAR
links"). Die Szenen legen ueber die echten Editoren zwei Effekte an — das
Dimmer-Lauflicht „Lauflicht HG" auf allen PARs und den „Blinder" (Matrix
Plain, Stil Dimmer) auf „PAR links" —, dazu zwei Tasten und eine Snap-Taste
„Blinder (Snap)" in der Virtuellen Konsole. Gerechnet wird mit dem echten
``OutputManager._send_all`` ohne zu senden; die Spalte „Verdeckt" wird nach
einigen gerechneten Frames ueber ``verdeckt_nachziehen`` gefuellt — dieselbe
Funktion, die der Takt der Ansicht ruft.

Modale Dialoge (Eigenschaften einer Taste, „Bearbeiten: …") werden ueber
ihren echten Aufruf geoeffnet, im modalen Loop aufgenommen und mit Abbrechen
bzw. Schliessen ohne Aenderung beendet.

Nicht hier: Bild 1 der Anleitung (Schichten-Schaubild) ist eine Zeichnung,
kein Bildschirmbild.
"""
from __future__ import annotations

from anleitungsbilder.runner import Frame, Szene, SzenenFehler
from anleitungsbilder.szenen_buehnen_effekte import _pv, _zeile, beleg
from anleitungsbilder.szenen_buehnen_show import ticks
from anleitungsbilder.szenen_dimmermatrix import (
    _fm, _mx, alles_aus, erwarte, funktion, lauf_felder, matrix_neu,
    matrix_zeigen, pars, programmer_start, prozent, reihe_aufnehmen,
    reihen_bild, speichern)
from anleitungsbilder.szenen_erste_schritte import bild, feld, knopf, rechteck

ZIEL = "docs/anleitung_prioritaeten/img"

LAUF = "Lauflicht HG"
BLINDER = "Blinder"
G_LINKS = "PAR links"
SNAP = "Blinder links"
STROBE_BLINDER = 40          # Zahl der Stufe „Strobe & Blinder"

_T_LAUF = "doku_prio_taste_lauf"
_T_BLINDER = "doku_prio_taste_blinder"
_T_SNAP = "doku_prio_taste_snap"


# ── Effekte anlegen ─────────────────────────────────────────────────────────

def _gibt(name):
    try:
        funktion(name)
        return True
    except SzenenFehler:
        return False


def effekte_anlegen(ui):
    """Lauflicht HG (Chase, Stil Dimmer, Alle PAR) und Blinder (Plain, Stil
    Dimmer, PAR links) ueber den Matrix-Editor; beide in der Stufe Effekte."""
    if not _gibt(LAUF):
        matrix_neu(ui, LAUF)
        lauf_felder(ui, breite=1, anzahl=1, tempo=1.0)
        speichern(ui)
    if not _gibt(BLINDER):
        matrix_neu(ui, BLINDER, algo="Plain", gruppe=G_LINKS)
        speichern(ui)
    programmer_start(ui)


def weiss(ui):
    """Farbe weiss aus dem Programmer (ohne Dimmer) — den Dimmer treiben die
    Effekte."""
    for attr in ("color_r", "color_g", "color_b"):
        ui.wert(pars(ui), attr, 255)
    ui.waehle([])


def _view(ui):
    return ui.win._prioritaeten_view


def ansicht(ui):
    ui.sektion("Programmer")
    ui.reiter("Prioritäten")
    v = _view(ui)
    v.neu_aufbauen()
    v._baum.clearSelection()
    ui.pump(0.3)
    return v


def _zeile_von(v, fid):
    for it in v._effekt_zeilen():
        if it.data(0, 0x0100) == fid:
            return it
    raise SzenenFehler(f"Effekt {fid} fehlt in der Ansicht")


def _kopf_von(v, text_anfang):
    w = v._baum.invisibleRootItem()
    for i in range(w.childCount()):
        if w.child(i).text(0).startswith(text_anfang):
            return w.child(i)
    raise SzenenFehler(f"Zeile „{text_anfang}…“ fehlt")


def _item_rechteck(ui, v, it, spalte=None):
    from PySide6.QtCore import QRect
    baum = v._baum
    baum.scrollToItem(it)
    ui.pump(0.1)
    if spalte is None:
        r = baum.visualItemRect(it)
        r.setRight(baum.viewport().width() - 2)
    else:
        r = baum.visualRect(baum.indexFromItem(it, spalte))
    return QRect(baum.viewport().mapTo(ui.win, r.topLeft()), r.size()).adjusted(0, 1, 0, -1)


def _spalte_rechteck(ui, v, spalte):
    from PySide6.QtCore import QRect
    kopf = v._baum.header()
    x = kopf.sectionViewportPosition(spalte)
    r = QRect(x, 0, kopf.sectionSize(spalte), kopf.height())
    return QRect(kopf.viewport().mapTo(ui.win, r.topLeft()), r.size())


# ── 02: Ansicht mit laufender Show ──────────────────────────────────────────

def _b02(ui):
    alles_aus(ui)
    effekte_anlegen(ui)
    weiss(ui)
    for name in (LAUF, "Regenbogen", "Kreis"):
        _fm().start(funktion(name).id)
    ticks(ui, 10)
    v = ansicht(ui)
    lauf = _zeile_von(v, funktion(LAUF).id)
    if lauf.text(3) != "● läuft":
        raise SzenenFehler("Lauflicht HG steht nicht auf „● läuft“")
    return bild(ui, kreise=[
        (_item_rechteck(ui, v, _kopf_von(v, "Snaps / Programmer")), 1, "rechts"),
        (_item_rechteck(ui, v, _kopf_von(v, "Effekte")), 2, "rechts"),
        (_spalte_rechteck(ui, v, 2), 3, "oben"),
        (_item_rechteck(ui, v, lauf, 3), 4, "rechts"),
    ])


# ── 03: Stufe ändern (GIF vorher/nachher) ───────────────────────────────────

def _gif03_vorher(ui):
    alles_aus(ui)
    effekte_anlegen(ui)
    f = funktion(BLINDER)
    f.priority = 0
    v = ansicht(ui)
    v.waehle([f.id])
    ui.pump(0.2)


def _gif03_schritt(klick):
    def schritt(ui):
        v = _view(ui)
        if klick:
            v._btn_hoeher.click()
            ui.pump(0.2)
            v.neu_aufbauen()
            ui.pump(0.2)
        beleg(f"Blinder Stufe: {funktion(BLINDER).priority}")
    return schritt


def _gif03_bild(ui):
    v = _view(ui)
    it = _zeile_von(v, funktion(BLINDER).id)
    return bild(ui, kreise=[
        (_item_rechteck(ui, v, it), 1, "rechts"),
        (rechteck(ui.win, v._btn_hoeher), 2, "rechts"),
    ])


def _gif03_nachher(ui):
    if funktion(BLINDER).priority != STROBE_BLINDER:
        raise SzenenFehler(f"Blinder landet in {funktion(BLINDER).priority}, "
                           f"nicht in Strobe & Blinder")


# ── 04: Feld Stufe im Matrix-Editor ─────────────────────────────────────────

def _b04(ui):
    from anleitungsbilder.szenen_buehnen_effekte import _oben
    alles_aus(ui)
    effekte_anlegen(ui)
    m = matrix_zeigen(ui, BLINDER, gruppe=G_LINKS)
    _oben(ui, m._editor_scroll, m._speed_spin, rand=60)
    body = m._editor_body
    return bild(ui, kreise=[(_zeile(ui, body, "Stufe:"), 1, "rechts")])


# ── 05: Feld Stufe im Szenen-Editor ─────────────────────────────────────────

def _bearbeiten_dialog(ui, fid, aufnahme):
    """Bibliothek → „Bearbeiten" (modal) öffnen, ``aufnahme(dlg)`` -> Bild,
    danach „Schließen" ohne Änderung."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QDialog
    panel = _pv(ui)._snap_file_panel
    ergebnis = {}

    def _auf():
        dlg = QApplication.activeModalWidget()
        if not isinstance(dlg, QDialog):
            ergebnis["fehler"] = "Dialog „Bearbeiten“ ging nicht auf"
            return
        try:
            ergebnis["bild"] = aufnahme(dlg)
        except Exception as e:      # noqa: BLE001
            ergebnis["fehler"] = f"{type(e).__name__}: {e}"
        finally:
            dlg.accept()

    QTimer.singleShot(400, _auf)
    panel._edit_function(fid)
    if "fehler" in ergebnis:
        raise SzenenFehler(ergebnis["fehler"])
    return ergebnis["bild"]


def _dialog_bild(ui, dlg, kreise):
    alt = dlg.close
    dlg.close = lambda: None
    try:
        return bild(ui, dlg, kreise, titel=dlg.windowTitle())
    finally:
        dlg.close = alt


def _b05(ui):
    alles_aus(ui)
    programmer_start(ui)
    sc = funktion("Alle PAR Blau")

    def aufnahme(dlg):
        from src.ui.widgets.stufe_auswahl import StufeAuswahl
        dlg.resize(760, 560)
        ui.pump(0.4)
        combo = dlg.findChild(StufeAuswahl)
        if combo is None:
            raise SzenenFehler("Feld Stufe fehlt im Szenen-Editor")
        from PySide6.QtCore import QPoint, QRect
        r = QRect(combo.mapTo(dlg, QPoint(0, 0)), combo.size())
        lab = None
        from PySide6.QtWidgets import QLabel
        for l in dlg.findChildren(QLabel):
            if l.isVisible() and l.text().replace("&", "").strip() == "Stufe:":
                lab = l
        if lab is not None:
            r = r.united(QRect(lab.mapTo(dlg, QPoint(0, 0)), lab.size()))
        return _dialog_bild(ui, dlg, [(r.adjusted(-3, -3, 3, 3), 1, "rechts")])
    return _bearbeiten_dialog(ui, sc.id, aufnahme)


# ── 06: alte Show mit eigener Zahl ──────────────────────────────────────────

def _b06(ui):
    alles_aus(ui)
    kreis = funktion("Kreis")
    alt = kreis.priority
    ui.info["doku_prio_kreis"] = alt
    kreis.priority = 5               # wie aus einer Show mit „Layer-Priorität" 5
    v = ansicht(ui)
    kopf = _kopf_von(v, "eigene Zahl")
    beleg(f"Zeile: {kopf.text(0)!r}")
    return bild(ui, kreise=[
        (_item_rechteck(ui, v, kopf).united(
            _item_rechteck(ui, v, _zeile_von(v, kreis.id))), 1, "rechts"),
    ])


def _n06(ui):
    funktion("Kreis").priority = ui.info.pop("doku_prio_kreis", 0)


# ── VC: Tasten anlegen ──────────────────────────────────────────────────────

def _canvas(ui):
    return ui.win._vc_view._canvas


def _vc(ui, name):
    from PySide6.QtWidgets import QWidget
    return _canvas(ui).findChild(QWidget, name)


def snap_anlegen(ui):
    from src.core.engine.snap_library import get_snap_library
    lib = get_snap_library()
    for s in lib.snaps():
        if s.name == SNAP:
            return s
    return lib.add_snap(SNAP, "", {f: {"intensity": 255} for f in pars(ui)[:4]})


def tasten_anlegen(ui, *, haken=False):
    from PySide6.QtCore import QPoint
    from src.ui.virtualconsole.vc_button import ButtonAction
    effekte_anlegen(ui)
    ui.sektion("Virtual Console")
    c = _canvas(ui)
    for name, text, fn, pos in ((_T_LAUF, "Lauflicht HG", LAUF, (680, 300)),
                                (_T_BLINDER, "Blinder", BLINDER, (850, 300))):
        w = _vc(ui, name)
        if w is None:
            w = c._add_widget("VCButton", QPoint(*pos))
            w.setObjectName(name)
        w.caption = text
        w.resize(150, 70)
        w.action = ButtonAction.FUNCTION_TOGGLE
        w.function_id = funktion(fn).id
        w.function_ids = []
        w.show()
        w.update()
    snap = snap_anlegen(ui)
    w = _vc(ui, _T_SNAP)
    if w is None:
        w = c._add_widget("VCButton", QPoint(1020, 300))
        w.setObjectName(_T_SNAP)
    w.caption = "Blinder (Snap)"
    w.resize(150, 70)
    w.action = ButtonAction.LIBRARY_SNAP
    w.snap_id = snap.id
    w.snap_ids = []
    w.snap_mode = "flash"
    w.snap_dimmer_override = bool(haken)
    w.show()
    w.update()
    ui.pump(0.4)


def tasten_weg(ui):
    c = _canvas(ui)
    for n in (_T_LAUF, _T_BLINDER, _T_SNAP):
        w = _vc(ui, n)
        if w is not None:
            c._remove_widget(w)
    ui.pump(0.2)


def eigenschaften(ui, name, aufnahme):
    """Eigenschaften einer Taste (modal) aufnehmen, mit Abbrechen schliessen."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QDialog
    w = _vc(ui, name)
    ergebnis = {}

    def _auf():
        dlg = QApplication.activeModalWidget()
        if not isinstance(dlg, QDialog):
            ergebnis["fehler"] = "Dialog „Button Einstellungen“ ging nicht auf"
            return
        try:
            dlg.adjustSize()
            ui.pump(0.3)
            ergebnis["bild"] = aufnahme(dlg)
        except Exception as e:      # noqa: BLE001
            ergebnis["fehler"] = f"{type(e).__name__}: {e}"
        finally:
            dlg.reject()            # = Abbrechen: nichts wird uebernommen

    QTimer.singleShot(400, _auf)
    w._open_properties()
    if "fehler" in ergebnis:
        raise SzenenFehler(ergebnis["fehler"])
    return ergebnis["bild"]


# ── 07: Snap-Taste mit Haken ────────────────────────────────────────────────

def _b07(ui):
    alles_aus(ui)
    tasten_anlegen(ui, haken=True)

    def aufnahme(dlg):
        haken = knopf(dlg, "übersteuert laufende Dimmer-Effekte")
        if not haken.isChecked():
            raise SzenenFehler("Haken steht nicht")
        modus = feld(dlg, "Tasten-Modus (Snap):")
        return _dialog_bild(ui, dlg, [
            (rechteck(dlg, modus), 1, "rechts"),
            (rechteck(dlg, haken).adjusted(-3, -3, 3, 3), 2, "rechts"),
        ])
    return eigenschaften(ui, _T_SNAP, aufnahme)


# ── 08: Blinder-Snap gegen das Lauflicht, ohne und mit Haken ───────────────

def _snap_halten(ui, gedrueckt):
    w = _vc(ui, _T_SNAP)
    w._pressed = gedrueckt
    w._trigger(gedrueckt)
    w.update()


def _b08(ui):
    alles_aus(ui)
    tasten_anlegen(ui, haken=False)
    weiss(ui)
    _fm().start(funktion(LAUF).id)
    from anleitungsbilder.szenen_dimmermatrix import bis_laeufer
    bis_laeufer(ui, [6])
    zeilen = []
    erwarte(prozent(ui), [0, 0, 0, 0, 0, 100, 0, 0], "Lauflicht allein (Dimmer %)")
    zeilen.append(("Lauflicht HG läuft", reihe_aufnehmen(ui)))
    for haken in (False, True):
        _vc(ui, _T_SNAP).snap_dimmer_override = haken
        _snap_halten(ui, True)
        ticks(ui, 1)
        soll = ([100] * 4 if haken else [0] * 4) + [0, 100, 0, 0]
        erwarte(prozent(ui), soll,
                f"Blinder-Snap gehalten, Haken {'an' if haken else 'aus'} (Dimmer %)")
        zeilen.append((f"Blinder (Snap) gehalten — {'mit' if haken else 'ohne'} Haken",
                       reihe_aufnehmen(ui)))
        _snap_halten(ui, False)
        ticks(ui, 1)
    _fm().stop(funktion(LAUF).id)
    return reihen_bild(zeilen)


def _n08(ui):
    alles_aus(ui)
    _vc(ui, _T_SNAP).snap_dimmer_override = False


# ── 09: gelber Hinweis bei Überschneidung ───────────────────────────────────

def _b09(ui):
    alles_aus(ui)
    tasten_anlegen(ui)
    funktion(BLINDER).priority = STROBE_BLINDER

    def aufnahme(dlg):
        from src.ui.widgets.ueberschneidung_hinweis import UeberschneidungsHinweis
        h = dlg.findChild(UeberschneidungsHinweis)
        if h is None or not h.isVisible():
            raise SzenenFehler("gelber Hinweis fehlt")
        from PySide6.QtWidgets import QLabel
        texte = [l.text() for l in h.findChildren(QLabel) if l.text()] or [
            getattr(h, "text", lambda: "")()]
        beleg(f"Hinweis: {texte}")
        aktion = feld(dlg, "Aktion:")
        return _dialog_bild(ui, dlg, [
            (rechteck(dlg, aktion), 1, "rechts"),
            (rechteck(dlg, h), 2, "rechts"),
        ])
    return eigenschaften(ui, _T_LAUF, aufnahme)


# ── 10: Spalte Verdeckt ─────────────────────────────────────────────────────

def _b10(ui):
    alles_aus(ui)
    effekte_anlegen(ui)
    funktion(BLINDER).priority = STROBE_BLINDER
    weiss(ui)
    v = ansicht(ui)
    for name in (LAUF, BLINDER, "Regenbogen"):
        _fm().start(funktion(name).id)
    v._wg_einschalten()
    ticks(ui, 6)
    v.verdeckt_nachziehen()
    v._laufzustand_nachziehen()
    ui.pump(0.3)
    lauf = _zeile_von(v, funktion(LAUF).id)
    text = lauf.text(4)
    beleg(f"Verdeckt (Lauflicht HG): {text!r}")
    if not text.startswith("verdeckt von Blinder auf 4"):
        raise SzenenFehler(f"Spalte Verdeckt zeigt {text!r}")
    return bild(ui, kreise=[
        (_spalte_rechteck(ui, v, 4), 1, "oben"),
        (_item_rechteck(ui, v, lauf, 4), 2, "rechts"),
        (_item_rechteck(ui, v, _zeile_von(v, funktion(BLINDER).id)), 3, "rechts"),
    ])


def _abraeumen(ui):
    from src.core.engine.snap_library import get_snap_library
    alles_aus(ui)
    tasten_weg(ui)
    lib = get_snap_library()
    for s in lib.snaps():
        if s.name == SNAP:
            lib.remove_snap(s.id)
    for name in (LAUF, BLINDER):
        if _gibt(name):
            _fm().remove(funktion(name).id)
    ui.pump(0.2)


SZENEN = [
    Szene("02_ansicht", sektion="Programmer", dialog=_b02,
          titel="Reiter Prioritäten mit laufender Show: Snap-Zeile, Stufen, Fasst an, ● läuft"),
    Szene("03_stufe_aendern", sektion="Programmer", vorher=_gif03_vorher,
          nachher=_gif03_nachher, gif_breite=1200, gif_zuschnitt=(0, 100, 1600, 540),
          frames=[Frame(dauer_s=1.6, schritt=_gif03_schritt(False), dialog=_gif03_bild),
                  Frame(dauer_s=1.2, schritt=_gif03_schritt(True), dialog=_gif03_bild),
                  Frame(dauer_s=2.0, schritt=_gif03_schritt(True), dialog=_gif03_bild)],
          titel="GIF: „Blinder“ mit ▲ Stufe höher von Effekte nach Strobe & Blinder"),
    Szene("04_stufe_matrix", sektion="Programmer", dialog=_b04,
          titel="Feld Stufe im Matrix-Editor (Tempo & Blende)"),
    Szene("05_stufe_szene", sektion="Programmer", dialog=_b05,
          titel="Feld Stufe im Szenen-Editor"),
    Szene("06_eigene_zahl", sektion="Programmer", dialog=_b06, nachher=_n06,
          titel="Effekt aus einer älteren Show: Gruppe „eigene Zahl (5)“"),
    Szene("07_snap_haken", sektion="Virtual Console", dialog=_b07,
          titel="Snap-Taste: Haken „übersteuert laufende Dimmer-Effekte“"),
    Szene("08_blinder_gegen_lauflicht", sektion="Programmer", dialog=_b08, nachher=_n08,
          titel="Blinder-Snap gegen ein Dimmer-Lauflicht: ohne und mit Haken"),
    Szene("09_ueberschneidung", sektion="Virtual Console", dialog=_b09,
          titel="Eigenschaften einer Taste mit dem gelben Hinweis bei Überschneidung"),
    Szene("10_verdeckt", sektion="Programmer", dialog=_b10, nachher=_abraeumen,
          titel="Spalte Verdeckt: „verdeckt von Blinder auf 4 Geräten“"),
]
