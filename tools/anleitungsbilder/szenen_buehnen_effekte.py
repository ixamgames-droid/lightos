"""DOC-60: Bilder fuer ``docs/anleitung_buehnen_show/ANLEITUNG.md`` — „Große
Bühnen-Show: Effekte selbst bauen".

Die Szenen bauen die Effekte IN DER ECHTEN OBERFLAECHE der grossen
Buehnen-Show (``tools/build_buehnen_show_2026.py``, in der Sandbox gebaut und
geladen wie in ``szenen_buehnen_show``): Gruppe in der Programmer-Liste
anklicken, Reiter Matrix/EFX/Laser, „+ Neu", Felder setzen, „💾 Speichern",
„▶ Start"; modale Dialoge („Kanäle auswählen", „Programmer → Szene",
„Bearbeiten: …", „Button Einstellungen") werden ueber ihren echten Aufruf
geoeffnet, im modalen Loop ausgefuellt, aufgenommen und mit OK geschlossen.

Jeder Effekt wird nach dem Bau per DMX belegt (``beleg_*``): die Funktion
rechnet mit dem ECHTEN ``OutputManager._send_all`` (ohne zu senden), gelesen
wird ``get_display_frame`` — das, was die Ausgabe senden wuerde. Tut ein
Effekt nicht, was die Anleitung sagt, bricht die Szene ab. Die Belege stehen
als ``BELEG …``-Zeilen im Lauf.

Offscreen (Oberflaechen-Bilder)::

    venv/bin/python tools/anleitungsbilder.py buehnen_effekte

Am echten Bildschirm (3D-GIFs und Visualizer-Einstellungen; jede 3D-Szene baut
ihren Effekt dort selbst noch einmal ueber dieselben Bedienschritte)::

    DISPLAY=:0 venv/bin/python tools/anleitungsbilder.py buehnen_effekte --bildschirm
"""
from __future__ import annotations

import re

from anleitungsbilder.runner import Frame, Szene, SzenenFehler
from anleitungsbilder.szenen_erste_schritte import bild, feld, knopf, rechteck
from anleitungsbilder import szenen_buehnen_show as bs

ZIEL = "docs/anleitung_buehnen_show/img_effekte"

# Namen der selbst gebauten Effekte (so stehen sie auch in der Anleitung).
LAUF = "Mein Lauflicht"
WELLE = "Meine MH-Welle"
SCHWENK = "Meine Schwenker"
STROBE = "Mein Strobe"
LASER_L = "Laser links"
LASER_R = "Laser rechts"
LASER = "Mein Laser langsam"

G_PAR = "PAR alle (links → rechts)"
G_MH = "MH alle (links → rechts)"
G_STROBE = "Strobes"
G_LASER = "Laser"

FREI = ""                     # Tempo-Bus „Frei (nicht taktgebunden)"
LASER_X_LINKS, LASER_X_RECHTS = 10, 118
LASER_FADE_S = 4.0


# ── Grundlagen ──────────────────────────────────────────────────────────────

def _pv(ui):
    return ui.win._programmer_view


def _fm():
    from src.core.engine.function_manager import get_function_manager
    return get_function_manager()


def funktion(name):
    for f in _fm().all():
        if f.name == name:
            return f
    return None


def _win_rect(ui, w):
    return rechteck(ui.win, w)


def _sichtbar(ui, w):
    """Sichtbarer Teil von ``w`` in Fensterkoordinaten (in Scrollbereichen
    nur, was wirklich zu sehen ist) — sonst SzenenFehler."""
    from PySide6.QtCore import QRect
    vr = w.visibleRegion().boundingRect()
    if vr.isEmpty() or vr.height() < w.height() * 0.8:
        raise SzenenFehler(f"{type(w).__name__} {getattr(w, 'text', lambda: '')()!r} "
                           "nicht (ganz) sichtbar — Bildlauf anpassen")
    return QRect(w.mapTo(ui.win, vr.topLeft()), vr.size())


def _zeile(ui, container, beschriftung):
    """Formularzeile (Beschriftung + Feld) in Fensterkoordinaten."""
    from PySide6.QtWidgets import QFormLayout
    fld = feld(container, beschriftung)
    r = _sichtbar(ui, fld)
    for form in container.findChildren(QFormLayout):
        lab = form.labelForField(fld)
        if lab is not None and lab.isVisible():
            r = r.united(_sichtbar(ui, lab))
            break
    return r


def _oben(ui, scroll, w, rand=36):
    """Bildlauf so, dass ``w`` oben im Scrollbereich steht."""
    from PySide6.QtCore import QPoint
    y = w.mapTo(scroll.widget(), QPoint(0, 0)).y()
    scroll.verticalScrollBar().setValue(max(0, y - rand))
    ui.pump(0.3)


def _bild(ui, kreise, popup=None, titel=None, **kw):
    return bild(ui, popup, kreise, titel=titel, **kw)


def start_vorher(ui):
    """Show geladen, alles aus, Programmer leer auf Reiter Attribute."""
    bs.show_laden(ui)
    bs.alles_aus(ui)
    ui.sektion("Programmer")
    ui.reiter("Attribute")
    pv = _pv(ui)
    # ERST weg vom EFX-/Matrix-Reiter, DANN die Auswahl leeren: der gerade
    # angezeigte Effekt folgt der Auswahl und verloere sonst seine Geraete.
    pv._main_tabs.setCurrentIndex(0)
    ui.pump(0.2)
    ui.state.clear_programmer()
    pv._fixture_list.clearSelection()
    ui.waehle([])
    # Lampen-Vorschau unten einklappen (▾): mehr Hoehe fuer die Editoren.
    pv._tile_preview.set_collapsed(True)
    ui.pump(0.2)


def auswahl_leeren(ui):
    """Auswahl leeren, ohne einen angezeigten Effekt umzubinden (erst weg vom
    EFX-/Matrix-Reiter)."""
    pv = _pv(ui)
    pv._main_tabs.setCurrentIndex(0)
    ui.pump(0.2)
    pv._fixture_list.clearSelection()
    pv._group_list.clearSelection()
    ui.waehle([])
    ui.state.clear_programmer()
    ui.pump(0.2)


def gruppe_item(ui, name):
    lst = _pv(ui)._group_list
    for i in range(lst.count()):
        it = lst.item(i)
        t = it.text().strip()
        if t == name or (t.startswith(name) and re.fullmatch(r"\s*\(\d+\)", t[len(name):])):
            return it
    raise SzenenFehler(f"Gruppe '{name}' fehlt in der Programmer-Liste")


def gruppe_waehlen(ui, name):
    """Wie ein Klick auf die Gruppe in der Programmer-Liste (springt in den
    Reiter Matrix)."""
    pv = _pv(ui)
    it = gruppe_item(ui, name)
    pv._group_list.setCurrentItem(it)
    pv._group_list.scrollToItem(it)
    pv._on_group_clicked(it)
    ui.pump(0.3)
    return list(it.data(0x0100) or [])          # Qt.UserRole: fids in Gruppen-Reihenfolge


def gruppe_fids(ui, name):
    return list(gruppe_item(ui, name).data(0x0100) or [])


def gruppe_rechteck(ui, name):
    from PySide6.QtCore import QRect
    lst = _pv(ui)._group_list
    it = gruppe_item(ui, name)
    lst.scrollToItem(it)
    ui.pump(0.1)
    r = lst.visualItemRect(it)
    return QRect(lst.viewport().mapTo(ui.win, r.topLeft()), r.size())


def tab_rechteck(ui, text):
    from PySide6.QtCore import QRect
    tabs = _pv(ui)._main_tabs
    bar = tabs.tabBar()
    for i in range(tabs.count()):
        if tabs.tabText(i).replace("&", "") == text and tabs.isTabVisible(i):
            r = bar.tabRect(i)
            return QRect(bar.mapTo(ui.win, r.topLeft()), r.size())
    raise SzenenFehler(f"Reiter '{text}' nicht sichtbar")


def reiter(ui, text):
    tabs = _pv(ui)._main_tabs
    for i in range(tabs.count()):
        if tabs.tabText(i).replace("&", "") == text and tabs.isTabVisible(i):
            tabs.setCurrentIndex(i)
            ui.pump(0.3)
            return
    raise SzenenFehler(f"Reiter '{text}' nicht sichtbar")


def _combo_daten(combo, daten):
    for i in range(combo.count()):
        if combo.itemData(i) == daten:
            combo.setCurrentIndex(i)
            return
    raise SzenenFehler(f"Auswahl {daten!r} fehlt "
                       f"({[combo.itemData(i) for i in range(combo.count())]})")


def _combo_text(combo, text):
    i = combo.findText(text)
    if i < 0:
        raise SzenenFehler(f"Eintrag '{text}' fehlt "
                           f"({[combo.itemText(i) for i in range(combo.count())]})")
    combo.setCurrentIndex(i)


# ── Modale Dialoge ──────────────────────────────────────────────────────────

def modal(ui, ausloeser, handler):
    """``ausloeser()`` oeffnet nacheinander modale Dialoge; ``handler`` ist eine
    Liste ``f(dlg)``, je Dialog einer, der ihn ausfuellt und schliesst (OK).
    Ein Timer im modalen Loop findet den jeweils neuen Dialog."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QDialog
    offen = list(handler)
    erledigt = []
    fehler = {}

    def _dialog():
        dlg = QApplication.activeModalWidget()
        if isinstance(dlg, QDialog) and dlg.isVisible() and dlg not in erledigt:
            return dlg
        for w in QApplication.topLevelWidgets():
            if isinstance(w, QDialog) and w.isVisible() and w.isModal() \
                    and w not in erledigt:
                return w
        return None

    def _tick(versuche=[0]):
        if not offen or fehler:
            return
        dlg = _dialog()
        if dlg is None:
            versuche[0] += 1
            if versuche[0] > 100:
                fehler["e"] = "Dialog ging nicht auf"
                return
            QTimer.singleShot(100, _tick)
            return
        versuche[0] = 0
        erledigt.append(dlg)
        h = offen.pop(0)
        try:
            ui.pump(0.3)
            h(dlg)
        except Exception as e:          # noqa: BLE001 — sauber abbrechen
            fehler["e"] = f"{type(e).__name__}: {e}"
            try:
                dlg.reject()
            except Exception:
                pass
            return
        if offen:
            QTimer.singleShot(250, _tick)

    QTimer.singleShot(300, _tick)
    ausloeser()
    ui.pump(0.3)
    if fehler:
        raise SzenenFehler(str(fehler["e"]))
    if offen:
        raise SzenenFehler(f"{len(offen)} Dialog(e) nicht erschienen")


def dialog_bild(ui, dlg, kreise, *, titel=None, anpassen=True):
    """Bild: Hauptfenster abgedunkelt + Dialog (bleibt offen)."""
    if anpassen:
        dlg.adjustSize()
    ui.pump(0.2)
    alt = dlg.close
    dlg.close = lambda: None        # ``bild`` schliesst das Popup sonst (= Abbrechen)
    try:
        return bild(ui, dlg, kreise, titel=titel or dlg.windowTitle())
    finally:
        dlg.close = alt


def _ok(dlg):
    from PySide6.QtWidgets import QDialogButtonBox
    box = dlg.findChild(QDialogButtonBox)
    if box is not None and box.button(QDialogButtonBox.StandardButton.Ok) is not None:
        box.button(QDialogButtonBox.StandardButton.Ok).click()
    else:
        dlg.accept()


# ── DMX lesen ───────────────────────────────────────────────────────────────

_KANAL = {}


def kanal(ui, fid, attr):
    """(universe, index 0-basiert) des ersten Kanals ``attr`` von ``fid``."""
    if (fid, attr) in _KANAL:
        return _KANAL[(fid, attr)]
    from src.core.app_state import get_channels_for_patched
    fx = next(f for f in ui.state.get_patched_fixtures() if f.fid == fid)
    for c in sorted(get_channels_for_patched(fx), key=lambda c: c.channel_number):
        if c.attribute == attr:
            _KANAL[(fid, attr)] = (int(fx.universe), int(fx.address) - 1 + int(c.channel_number) - 1)
            return _KANAL[(fid, attr)]
    raise SzenenFehler(f"Gerät {fid} hat keinen Kanal {attr}")


def dmx(ui, fid, attr):
    u, i = kanal(ui, fid, attr)
    frame = ui.state.output_manager.get_display_frame(u)
    if frame is None:
        raise SzenenFehler("noch kein DMX-Frame gerechnet")
    return int(frame[i])


def beleg(text):
    print("BELEG " + text, flush=True)


# ── 1: Matrix (Lauflicht Mitte → außen, Strobe) ─────────────────────────────

def _mx(ui):
    return _pv(ui)._embedded_rgb


def matrix_neu(ui, gruppe):
    start_vorher(ui)
    gruppe_waehlen(ui, gruppe)
    reiter(ui, "Matrix")
    knopf(_mx(ui), "+ Neu").click()
    ui.pump(0.3)


def matrix_felder(ui, name, algo, stil, params, tempo):
    m = _mx(ui)
    m._name_edit.selectAll()
    m._name_edit.setText(name)
    _combo_text(m._algo_combo, algo)
    _combo_text(m._style_combo, stil)
    ui.pump(0.2)
    for key, wert in params.items():
        w = m._param_widgets.get(key)
        if w is None:
            raise SzenenFehler(f"Matrix-Parameter {key} fehlt")
        if hasattr(w, "findData"):
            _combo_daten(w, wert)
        else:
            w.setValue(wert)
    _combo_daten(m._tempo_bus_combo, FREI)
    m._speed_spin.setValue(tempo)
    ui.pump(0.3)


def matrix_speichern_starten(ui):
    m = _mx(ui)
    knopf(m, "💾 Speichern").click()
    ui.pump(0.2)
    knopf(m, "▶ Start").click()
    ui.pump(0.2)


LAUF_FELDER = dict(name=LAUF, algo="Chase", stil="Dimmer",
                   params={"movement": "center_out", "runner_width": 3}, tempo=6.0)
STROBE_FELDER = dict(name=STROBE, algo="Strobe", stil="Dimmer", params={}, tempo=9.0)


def lauf_bauen(ui):
    if funktion(LAUF) is None:
        matrix_neu(ui, G_PAR)
        matrix_felder(ui, **LAUF_FELDER)
        matrix_speichern_starten(ui)
    else:
        _fm().start(funktion(LAUF).id)


def strobe_bauen(ui):
    if funktion(STROBE) is None:
        matrix_neu(ui, G_STROBE)
        matrix_felder(ui, **STROBE_FELDER)
        matrix_speichern_starten(ui)
    else:
        _fm().start(funktion(STROBE).id)


def beleg_lauf(ui):
    """Lauflicht Mitte → außen: die hellen PARs liegen symmetrisch zur Mitte
    der Reihe und wandern nach außen."""
    fids = gruppe_fids(ui, G_PAR)
    mitte = (len(fids) - 1) / 2
    abstaende = []
    bs.ticks(ui, 4)
    for schritt in range(10):
        bs.ticks(ui, 4)
        an = [i for i, f in enumerate(fids) if dmx(ui, f, "intensity") >= 128]
        if not an:
            beleg(f"Lauflicht t={schritt * 4 / 44:.2f}s: Pause zwischen zwei Läufen")
            continue
        links = sorted(mitte - i for i in an if i < mitte)
        rechts = sorted(i - mitte for i in an if i > mitte)
        if links != rechts:
            raise SzenenFehler(f"Lauflicht nicht symmetrisch: {an}")
        abstaende.append(round(min(abs(i - mitte) for i in an), 1))
        beleg(f"Lauflicht t={schritt * 4 / 44:.2f}s hell (Platz in der Reihe 1..40): "
              f"{[i + 1 for i in an]}")
    if len(abstaende) < 5 or not any(b > a for a, b in zip(abstaende, abstaende[1:])):
        raise SzenenFehler(f"Lauflicht wandert nicht nach außen: {abstaende}")
    beleg(f"Lauflicht Abstand zur Mitte je Schritt: {abstaende} -> wandert nach außen")


def beleg_welle_matrix(ui):
    """Variante Wave/Ursprung Mitte: Helligkeit symmetrisch zur Mitte."""
    fids = gruppe_fids(ui, G_PAR)
    bs.ticks(ui, 10)
    werte = [dmx(ui, f, "intensity") for f in fids]
    beleg(f"Welle (Wave, Ursprung Mitte) Dimmer je PAR: {werte}")
    if werte != werte[::-1]:
        raise SzenenFehler("Welle Mitte nicht symmetrisch")
    if len(set(werte)) < 4:
        raise SzenenFehler("Welle hat keine Abstufung")


def beleg_strobe(ui):
    fids = gruppe_fids(ui, G_STROBE)
    folge = []
    for _ in range(24):
        bs.ticks(ui, 1)
        folge.append(dmx(ui, fids[0], "intensity"))
    beleg(f"Strobe 1 Dimmer je DMX-Frame (44/s): {folge}")
    wechsel = sum(1 for a, b in zip(folge, folge[1:]) if (a > 127) != (b > 127))
    if wechsel < 4 or set(folge) - {0, 255}:
        raise SzenenFehler(f"Strobe blitzt nicht hart an/aus: {folge}")
    alle = {dmx(ui, f, "intensity") for f in fids}
    beleg(f"Strobe alle 8 gleichzeitig: {sorted(alle)}")
    if len(alle) != 1:
        raise SzenenFehler("Strobes nicht gleichzeitig")


# ── 2/3: EFX (Welle, Schwenker) ─────────────────────────────────────────────

def _efx(ui):
    return _pv(ui)._embedded_efx


def efx_neu(ui):
    start_vorher(ui)
    gruppe_waehlen(ui, G_MH)
    reiter(ui, "EFX")
    knopf(_efx(ui), "+ Neu").click()
    ui.pump(0.3)


def efx_felder(ui, name, *, breite, hoehe, tilt, tempo, modus, streuung=None,
               versatz=None):
    e = _efx(ui)
    e._name_edit.selectAll()
    e._name_edit.setText(name)
    _combo_text(e._algo_combo, "Line")
    e._width_spin.setValue(breite)
    e._height_spin.setValue(hoehe)
    e._yoff_spin.setValue(tilt)
    _combo_daten(e._tempo_bus_combo, FREI)
    e._speed_spin.setValue(tempo)
    _combo_daten(e._phase_mode_combo, modus)
    ui.pump(0.1)
    if streuung is not None:
        e._spread_spin.setValue(streuung)
    if versatz is not None:
        e._offset_spin.setValue(versatz)
    e._open_beam_chk.setChecked(True)
    ui.pump(0.3)


def efx_speichern_starten(ui):
    e = _efx(ui)
    knopf(e, "💾 Speichern").click()
    ui.pump(0.2)
    knopf(e, "▶ Start").click()
    ui.pump(0.2)


WELLE_FELDER = dict(breite=60.0, hoehe=0.0, tilt=96.0, tempo=0.25, modus="fan",
                    streuung=1.0)
SCHWENK_FELDER = dict(breite=80.0, hoehe=0.0, tilt=100.0, tempo=0.3, modus="offset",
                      versatz=180.0)


def welle_bauen(ui):
    if funktion(WELLE) is None:
        efx_neu(ui)
        efx_felder(ui, WELLE, **WELLE_FELDER)
        efx_speichern_starten(ui)
    else:
        _fm().start(funktion(WELLE).id)


def schwenk_bauen(ui):
    if funktion(SCHWENK) is None:
        efx_neu(ui)
        efx_felder(ui, SCHWENK, **SCHWENK_FELDER)
        efx_speichern_starten(ui)
    else:
        _fm().start(funktion(SCHWENK).id)


def _pans(ui, fids):
    return [dmx(ui, f, "pan") for f in fids]


def beleg_welle(ui):
    """Pan-Welle: alle 20 Köpfe schwenken, jeder etwas später als sein
    linker Nachbar (Phasenversatz über die Reihe)."""
    fids = gruppe_fids(ui, G_MH)
    f = funktion(WELLE)
    beleg(f"Welle gebunden an {len(f.fixtures)} Köpfe")
    if len(f.fixtures) != len(fids):
        raise SzenenFehler("Welle nicht an alle 20 Köpfe gebunden")
    bs.ticks(ui, 5)
    a = _pans(ui, fids)
    bs.ticks(ui, 22)
    b = _pans(ui, fids)
    tilt = {dmx(ui, x, "tilt") for x in fids}
    dim = {dmx(ui, x, "intensity") for x in fids}
    beleg(f"Welle Pan t0: {a}")
    beleg(f"Welle Pan t0+0.5s: {b}")
    beleg(f"Welle Tilt (alle): {sorted(tilt)}  Dimmer (alle): {sorted(dim)}")
    if len(set(a)) < 10:
        raise SzenenFehler("Welle: Köpfe stehen fast gleich (kein Versatz)")
    if a == b:
        raise SzenenFehler("Welle bewegt sich nicht")
    if dim != {255}:
        raise SzenenFehler("„Dimmer/Shutter mit öffnen“ öffnet die Köpfe nicht")


def beleg_schwenk(ui):
    """Schwenker: Nachbarn stehen spiegelbildlich (180° Versatz) — schwenkt
    einer nach links, schwenkt der nächste nach rechts."""
    fids = gruppe_fids(ui, G_MH)
    for _ in range(3):
        bs.ticks(ui, 9)
        p = _pans(ui, fids)
        beleg(f"Schwenker Pan: {p}")
        gerade = {p[i] for i in range(0, len(p), 2)}
        ungerade = {p[i] for i in range(1, len(p), 2)}
        if len(gerade) != 1 or len(ungerade) != 1:
            raise SzenenFehler("Schwenker: jeder zweite Kopf nicht gleich")
        g, u = gerade.pop(), ungerade.pop()
        if abs((g - 128) + (u - 128)) > 2:
            raise SzenenFehler(f"Schwenker nicht gegenläufig: {g} / {u}")


# ── 5: Laser (Szenen + Chaser mit Überblendung) ─────────────────────────────

def _laser(ui):
    return _pv(ui)._embedded_laser


def laser_zeile(ui, attr):
    from src.ui.views.laser_view import _ChannelRow
    for r in _laser(ui).findChildren(_ChannelRow):
        if r.attribute == attr and r.isVisible():
            return r
    raise SzenenFehler(f"Laser-Regler {attr} nicht sichtbar")


def laser_vorher(ui):
    start_vorher(ui)
    gruppe_waehlen(ui, G_LASER)
    reiter(ui, "Laser")
    laser_zeile(ui, "laser_x")._spin.setValue(LASER_X_LINKS)
    ui.pump(0.3)


def szene_aus_programmer(ui, name, *, bild_fn=None):
    """Assistent → „Programmer → Szene": Kanäle auswählen (nur die Gruppe mit
    X-Bewegung), Name eingeben, OK."""
    reiter(ui, "Assistent")
    pv = _pv(ui)
    ergebnis = {}

    def kanaele(dlg):
        from PySide6.QtWidgets import QCheckBox
        boxen = [c for c in dlg.findChildren(QCheckBox) if c.isVisible()]
        ziel = None
        for c in boxen:
            c.setChecked(False)
        for c in boxen:
            if c.text().startswith("Effect"):
                ziel = c
        beleg(f"Kanäle-Dialog Häkchen: {[c.text() for c in boxen]}")
        if ziel is None:
            raise SzenenFehler("Kanalgruppe für die X-Bewegung fehlt")
        ziel.setChecked(True)
        ui.pump(0.2)
        if bild_fn is not None:
            ergebnis["kanaele"] = bild_fn(dlg, ziel)
        _ok(dlg)

    def name_eingeben(dlg):
        dlg.setTextValue(name)
        ui.pump(0.1)
        dlg.accept()

    modal(ui, lambda: knopf(pv, "Programmer → Szene").click(), [kanaele, name_eingeben])
    if funktion(name) is None:
        raise SzenenFehler(f"Szene '{name}' wurde nicht angelegt")
    return ergebnis


def chaser_bauen(ui, *, bild_fn=None):
    """Assistent → „+ Chaser": Name, Run Order Loop, Tempo-Bus frei, beide
    Szenen übernehmen, Fade In 4 s, Schließen."""
    from PySide6.QtWidgets import QDoubleSpinBox
    reiter(ui, "Assistent")
    pv = _pv(ui)
    ergebnis = {}

    def editor(dlg):
        from src.ui.views.chaser_editor import ChaserEditor
        ed = dlg.findChild(ChaserEditor)
        if ed is None:
            raise SzenenFehler("Chaser-Editor fehlt im Dialog")
        ed._name_edit.setText(LASER)
        _combo_text(ed._combo_order, "Loop")
        _combo_daten(ed._tempo_bus_combo, FREI)
        ui.pump(0.2)
        if bild_fn is not None:
            # Bild 16 zeigt NUR Schritte 1-3 (Name, Run Order, Tempo-Bus) —
            # aufgenommen, bevor Schritte und Fade-Zeiten (Schritt 4) gesetzt sind.
            dlg.resize(940, 830)
            ui.pump(0.3)
            ed._editor_scroll.verticalScrollBar().setValue(0)
            ui.pump(0.2)
            ergebnis["chaser_tempo"] = bild_fn(dlg, ed, "tempo")
        lst = ed._add_list
        for i in range(lst.count()):
            t = lst.item(i).text().split(": ", 1)[-1]
            lst.item(i).setSelected(t in (LASER_L, LASER_R))
        knopf(dlg, "↳ In Chase übernehmen").click()
        ui.pump(0.3)
        tab = ed._table
        if tab.rowCount() != 2:
            raise SzenenFehler(f"Chaser hat {tab.rowCount()} Schritte statt 2")
        for row in range(2):
            fade = tab.cellWidget(row, 2)
            hold = tab.cellWidget(row, 4)
            if not isinstance(fade, QDoubleSpinBox):
                raise SzenenFehler("Fade-In-Feld fehlt")
            fade.setValue(LASER_FADE_S)
            if isinstance(hold, QDoubleSpinBox):
                hold.setValue(0.5)
        ui.pump(0.3)
        if bild_fn is not None:
            _oben(ui, ed._editor_scroll, ed._table, rand=50)
            ergebnis["chaser_schritte"] = bild_fn(dlg, ed, "schritte")
        knopf(dlg, "Schließen").click()

    modal(ui, lambda: knopf(pv, "+ Chaser").click(), [editor])
    if funktion(LASER) is None:
        raise SzenenFehler("Chaser wurde nicht angelegt")
    return ergebnis


def laser_bauen(ui, *, bild_kanaele=None, bild_chaser=None):
    """Ganzer Laser-Ablauf; liefert die Bilder der Dialoge (falls gewuenscht)."""
    bilder = {}
    if funktion(LASER) is not None:
        return bilder
    laser_vorher(ui)
    bilder.update(szene_aus_programmer(ui, LASER_L, bild_fn=bild_kanaele))
    reiter(ui, "Laser")
    laser_zeile(ui, "laser_x")._spin.setValue(LASER_X_RECHTS)
    ui.pump(0.2)
    szene_aus_programmer(ui, LASER_R)
    # Programmer leeren: sonst haelt er die X-Bewegung fest.
    ui.state.clear_programmer()
    ui.pump(0.2)
    bilder.update(chaser_bauen(ui, bild_fn=bild_chaser))
    return bilder


def beleg_laser(ui):
    fids = gruppe_fids(ui, G_LASER)
    werte = []
    for _ in range(22):
        werte.append(dmx(ui, fids[0], "laser_x"))
        bs.ticks(ui, 22)
    beleg(f"Laser 1 X-Bewegung alle 0,5 s: {werte}")
    alle = {dmx(ui, f, "laser_x") for f in fids}
    beleg(f"Laser alle 10 gleich: {sorted(alle)}")
    if len(alle) != 1:
        raise SzenenFehler("Laser laufen nicht gemeinsam")
    zwischen = [w for w in werte if LASER_X_LINKS < w < LASER_X_RECHTS]
    if len(zwischen) < 4:
        raise SzenenFehler(f"Laser springt statt zu gleiten: {werte}")
    if max(werte) < LASER_X_RECHTS - 5 or min(werte) > LASER_X_LINKS + 5:
        raise SzenenFehler(f"Laser erreicht die Enden nicht: {werte}")


# ── 6: VC-Knopf ─────────────────────────────────────────────────────────────

VC_KNOEPFE = [  # (Beschriftung, Funktion, Live-Edit-Slot)
    ("Lauflicht", LAUF, "PAR"),
    ("MH-Welle", WELLE, "MH"),
    ("Schwenker", SCHWENK, "MH"),
    ("Strobe", STROBE, "STR"),
    ("Mein Laser", LASER, "LAS"),
]


def _vc(ui):
    return ui.win._vc_view


def vc_bank2(ui):
    """Virtual Console, eine freie Seite, Bearbeiten an."""
    ui.sektion("Virtual Console")
    vc = _vc(ui)
    if vc._canvas._edit_mode:
        knopf(vc, "Bearbeiten ✓").click()
    vc._btn_bank_next.click()
    ui.pump(0.3)
    knopf(vc, "Bearbeiten").click()
    ui.pump(0.3)


def vc_knoepfe_der_bank(ui):
    """Alle Knöpfe der AKTUELLEN Bank — die Show selbst belegt Bank 1 mit
    eigenen Knöpfen (darunter „Laser langsam"); eine Suche über alle Bänke
    fand dort einen gleichnamigen Knopf, und der eigene wurde nie angelegt."""
    from src.ui.virtualconsole.vc_button import VCButton
    canvas = _vc(ui)._canvas
    return [w for w in canvas.findChildren(VCButton) if canvas.on_active_bank(w)]


def vc_knopf_finden(ui, text):
    for w in vc_knoepfe_der_bank(ui):
        if (w.caption or "") == text:
            return w
    return None


def vc_bank_pruefen(ui):
    """Auf der eigenen Bank liegen genau die fünf Knöpfe aus VC_KNOEPFE."""
    canvas = _vc(ui)._canvas
    namen = sorted((w.caption or "") for w in vc_knoepfe_der_bank(ui))
    beleg(f"VC Bank {canvas.active_bank + 1}: {len(namen)} Knöpfe {namen}")
    if canvas.active_bank != 1:
        raise SzenenFehler(f"eigene Knöpfe nicht auf Bank 2 (Bank {canvas.active_bank + 1})")
    if namen != sorted(t for t, _f, _s in VC_KNOEPFE):
        raise SzenenFehler(f"Bank 2 hat {namen} statt der fünf eigenen Knöpfe")


def vc_knopf_anlegen(ui, i, text, fn_name, slot, *, bild_fn=None):
    """Kontextmenü „Hinzufügen → Button" (über den echten Menüpunkt-Weg
    ``_add_widget``), Doppelklick → „Button Einstellungen" ausfüllen, OK."""
    from PySide6.QtCore import QPoint
    canvas = _vc(ui)._canvas
    w = canvas._add_widget("VCButton", QPoint(40 + i * 170, 60))
    ui.pump(0.2)
    ergebnis = {}

    def einstellen(dlg):
        from PySide6.QtWidgets import QComboBox, QLineEdit
        feld(dlg, "Beschriftung:").setText(text)
        _combo_text(feld(dlg, "Aktion:"), "Funktion an/aus")
        ui.pump(0.2)
        ziele = feld(dlg, "Ziele:")
        knopf(ziele, "+ Funktion/Effekt hinzufügen").click()
        ui.pump(0.2)
        combos = [c for c in ziele.findChildren(QComboBox) if c.isVisible()]
        if not combos:
            raise SzenenFehler("Funktions-Auswahl im Ziel fehlt")
        f = funktion(fn_name)
        _combo_daten(combos[-1], int(f.id))
        slot_feld = feld(dlg, "Live-Edit-Slot:")
        if not isinstance(slot_feld, QLineEdit):
            raise SzenenFehler("Live-Edit-Slot ist kein Textfeld")
        slot_feld.setText(slot)
        ui.pump(0.3)
        if bild_fn is not None:
            ergebnis["bild"] = bild_fn(dlg, ziele, combos[-1], slot_feld)
        _ok(dlg)

    modal(ui, w._edit_properties, [einstellen])
    if (w.caption or "") != text:
        raise SzenenFehler("Beschriftung nicht übernommen")
    return w, ergebnis


def vc_alle_anlegen(ui, *, bis=None):
    for i, (text, fn_name, slot) in enumerate(VC_KNOEPFE[:bis]):
        if vc_knopf_finden(ui, text) is None:
            vc_knopf_anlegen(ui, i, text, fn_name, slot)
    if bis is None:
        vc_bank_pruefen(ui)


def alle_effekte_bauen(ui):
    lauf_bauen(ui)
    welle_bauen(ui)
    schwenk_bauen(ui)
    strobe_bauen(ui)
    laser_bauen(ui)
    _fm().stop_all()
    ui.pump(0.2)


def beleg_vc(ui):
    """Knopf drücken startet die Funktion, ein Knopf im selben Slot löst ab."""
    fm = _fm()
    fm.stop_all()
    w_lauf = vc_knopf_finden(ui, "Lauflicht")
    w_welle = vc_knopf_finden(ui, "MH-Welle")
    w_schw = vc_knopf_finden(ui, "Schwenker")
    for w in (w_lauf, w_welle):
        _druecken(w)
    bs.ticks(ui, 3)
    lauf, welle, schw = funktion(LAUF), funktion(WELLE), funktion(SCHWENK)
    beleg(f"VC: nach „Lauflicht“+„MH-Welle“ laufen: Lauflicht={fm.is_running(lauf.id)}, "
          f"Welle={fm.is_running(welle.id)}")
    if not (fm.is_running(lauf.id) and fm.is_running(welle.id)):
        raise SzenenFehler("VC-Knopf startet die Funktion nicht")
    _druecken(w_schw)
    bs.ticks(ui, 3)
    beleg(f"VC: nach „Schwenker“ (Slot MH): Welle={fm.is_running(welle.id)}, "
          f"Schwenker={fm.is_running(schw.id)}, Lauflicht={fm.is_running(lauf.id)}")
    if fm.is_running(welle.id) or not fm.is_running(schw.id) \
            or not fm.is_running(lauf.id):
        raise SzenenFehler("Live-Edit-Slot löst nicht ab")
    beleg_schwenk(ui)
    fm.stop_all()


def _druecken(w):
    w._pressed = True
    w._trigger(True)
    w._pressed = False
    w._trigger(False)
    w.update()


# ── Bilder: Oberfläche ──────────────────────────────────────────────────────

def _matrix_dirty_beleg(ui):
    """Nebenbefund: zeigt der Editor bei einer unberuehrten Matrix
    „ungespeicherte Änderungen“, steht hier, welche Felder abweichen."""
    m = _mx(ui)
    cur, saved = getattr(m, "_current", None), getattr(m, "_saved", None)
    if cur is None or saved is None:
        beleg("Matrix-Editor: keine Matrix geladen")
        return
    a, b = cur.to_dict(), saved.to_dict()
    diff = {k: (b.get(k), a.get(k)) for k in set(a) | set(b) if a.get(k) != b.get(k)}
    beleg(f"Matrix-Editor „{saved.name}“ nach Gruppenwahl: Abweichung gespeichert→Editor {diff}")


def _b01(ui):
    start_vorher(ui)
    gruppe_waehlen(ui, G_PAR)
    reiter(ui, "Matrix")
    _matrix_dirty_beleg(ui)
    return _bild(ui, [(gruppe_rechteck(ui, G_PAR), 1, "rechts"),
                      (tab_rechteck(ui, "Matrix"), 2, "oben"),
                      (_win_rect(ui, knopf(_mx(ui), "+ Neu")), 3, "rechts")])


def _b02(ui):
    matrix_neu(ui, G_PAR)
    matrix_felder(ui, **LAUF_FELDER)
    m = _mx(ui)
    body = m._editor_body
    m._editor_scroll.verticalScrollBar().setValue(0)
    ui.pump(0.2)
    tempo = _zeile(ui, body, "Geschwindigkeit:").united(_zeile(ui, body, "Tempo-Bus:"))
    return _bild(ui, [(_zeile(ui, body, "Name:"), 1, "rechts"),
                      (_zeile(ui, body, "Algorithmus:"), 2, "rechts"),
                      (_zeile(ui, body, "Stil:"), 3, "rechts"),
                      (tempo, 4, "rechts"),
                      (_win_rect(ui, knopf(m, "💾 Speichern")), 6, "links")])


def _b03(ui):
    m = _mx(ui)
    body = m._editor_body
    _oben(ui, m._editor_scroll, m._param_box)
    kreise = [(_zeile(ui, body, "Bewegung:").united(_zeile(ui, body, "Läufer-Breite:")),
               5, "rechts"),
              (_win_rect(ui, knopf(m, "▶ Start")), 7, "rechts")]
    return _bild(ui, kreise)


def _n03(ui):
    matrix_speichern_starten(ui)
    beleg_lauf(ui)
    # Variante „Welle": dieselbe Matrix, Algorithmus Wave, Ursprung Mitte.
    m = _mx(ui)
    _combo_text(m._algo_combo, "Wave")
    ui.pump(0.2)
    _combo_daten(m._param_widgets["origin"], "center")
    knopf(m, "💾 Speichern").click()
    ui.pump(0.2)
    beleg_welle_matrix(ui)
    _combo_text(m._algo_combo, "Chase")
    ui.pump(0.2)
    _combo_daten(m._param_widgets["movement"], "center_out")
    m._param_widgets["runner_width"].setValue(3)
    knopf(m, "💾 Speichern").click()
    ui.pump(0.2)
    beleg_lauf(ui)
    bs.alles_aus(ui)


def _b05(ui):
    efx_neu(ui)
    e = _efx(ui)
    return _bild(ui, [(gruppe_rechteck(ui, G_MH), 1, "rechts"),
                      (tab_rechteck(ui, "EFX"), 2, "oben"),
                      (_win_rect(ui, knopf(e, "+ Neu")), 3, "rechts")])


def _b06(ui):
    efx_felder(ui, WELLE, **WELLE_FELDER)
    e = _efx(ui)
    body = e._editor_body
    e._editor_scroll.ensureWidgetVisible(e._algo_combo, 0, 40)
    ui.pump(0.3)
    geo = _zeile(ui, body, "Breite (Pan-Hub):").united(_zeile(ui, body, "Zentrum Tilt:"))
    return _bild(ui, [(_zeile(ui, body, "Name:"), 1, "rechts"),
                      (_zeile(ui, body, "Algorithmus:"), 2, "rechts"),
                      (geo, 3, "rechts")])


def _b06b(ui):
    e = _efx(ui)
    body = e._editor_body
    _oben(ui, e._editor_scroll, e._speed_spin)
    tempo = _zeile(ui, body, "Geschwindigkeit (Hz):").united(_zeile(ui, body, "Tempo-Bus:"))
    return _bild(ui, [(tempo, 4, "rechts")])


def _b06c(ui):
    e = _efx(ui)
    body = e._editor_body
    _oben(ui, e._editor_scroll, e._phase_mode_combo, rand=60)
    rel = _zeile(ui, body, "Verhältnis:").united(_zeile(ui, body, "Fächer-Streuung:"))
    return _bild(ui, [(rel, 5, "rechts"),
                      (_zeile(ui, body, "Sichtbarkeit:"), 6, "rechts"),
                      (_win_rect(ui, knopf(e, "💾 Speichern")), 7, "rechts"),
                      (_win_rect(ui, knopf(e, "▶ Start")), 8, "rechts")])


def _n06(ui):
    efx_speichern_starten(ui)
    beleg_welle(ui)
    bs.alles_aus(ui)


def _b08(ui):
    efx_neu(ui)
    efx_felder(ui, SCHWENK, **SCHWENK_FELDER)
    e = _efx(ui)
    body = e._editor_body
    _oben(ui, e._editor_scroll, e._phase_mode_combo, rand=60)
    rel = _zeile(ui, body, "Verhältnis:").united(_zeile(ui, body, "Versatz pro Gerät:"))
    return _bild(ui, [(rel, 1, "rechts"),
                      (_zeile(ui, body, "Sichtbarkeit:"), 2, "rechts"),
                      (_win_rect(ui, knopf(e, "💾 Speichern")), 3, "rechts"),
                      (_win_rect(ui, knopf(e, "▶ Start")), 4, "rechts")])


def _n08(ui):
    efx_speichern_starten(ui)
    beleg_schwenk(ui)
    bs.alles_aus(ui)


def _b10(ui):
    matrix_neu(ui, G_STROBE)
    matrix_felder(ui, **STROBE_FELDER)
    m = _mx(ui)
    body = m._editor_body
    m._editor_scroll.verticalScrollBar().setValue(0)
    ui.pump(0.2)
    return _bild(ui, [(gruppe_rechteck(ui, G_STROBE), 1, "rechts"),
                      (_zeile(ui, body, "Algorithmus:").united(_zeile(ui, body, "Stil:")),
                       2, "rechts"),
                      (_win_rect(ui, knopf(m, "💾 Speichern")), 3, "links"),
                      (_win_rect(ui, knopf(m, "▶ Start")), 4, "rechts")])


def _n10(ui):
    m = _mx(ui)
    m._editor_scroll.ensureWidgetVisible(m._speed_spin, 0, 30)
    matrix_speichern_starten(ui)
    beleg_strobe(ui)
    bs.alles_aus(ui)


def _b12(ui):
    laser_vorher(ui)
    zeile = laser_zeile(ui, "laser_x")
    lv = _laser(ui)
    from PySide6.QtWidgets import QScrollArea
    for sc in lv.findChildren(QScrollArea):
        if sc.isAncestorOf(zeile):
            sc.ensureWidgetVisible(zeile, 0, 60)
    ui.pump(0.3)
    return _bild(ui, [(gruppe_rechteck(ui, G_LASER), 1, "rechts"),
                      (tab_rechteck(ui, "Laser"), 2, "oben"),
                      (_win_rect(ui, zeile), 3, "oben")])


_LASER_BILDER = {}


def _v13(ui):
    """Laser-Ablauf bauen; die beiden Dialog-Bilder entstehen dabei."""
    def kanaele_bild(dlg, ziel):
        return dialog_bild(ui, dlg, [(rechteck(dlg, ziel), 1, "rechts")])

    def chaser_bild(dlg, ed, teil):
        if teil == "tempo":
            return dialog_bild(ui, dlg, [
                (_zeile_dlg(dlg, "Name:"), 1, "rechts"),
                (_zeile_dlg(dlg, "Run Order:"), 2, "rechts"),
                (_zeile_dlg(dlg, "Tempo-Bus:"), 3, "rechts")], anpassen=False)
        return dialog_bild(ui, dlg, [
            (_sicht_dlg(dlg, ed._table), 4, "rechts"),
            (_sicht_dlg(dlg, knopf(dlg, "↳ In Chase übernehmen")), 5, "rechts"),
            (_sicht_dlg(dlg, knopf(dlg, "Schließen")), 6, "rechts")], anpassen=False)
    _LASER_BILDER.update(laser_bauen(ui, bild_kanaele=kanaele_bild,
                                     bild_chaser=chaser_bild))


def _sicht_dlg(dlg, w):
    """Sichtbarer Teil von ``w`` in Dialog-Koordinaten (sonst SzenenFehler)."""
    from PySide6.QtCore import QRect
    vr = w.visibleRegion().boundingRect()
    if vr.isEmpty() or vr.height() < min(w.height(), 120) * 0.8:
        raise SzenenFehler(f"{type(w).__name__} im Dialog nicht sichtbar — Bildlauf anpassen")
    return QRect(w.mapTo(dlg, vr.topLeft()), vr.size())


def _zeile_dlg(dlg, beschriftung):
    from PySide6.QtWidgets import QFormLayout
    fld = feld(dlg, beschriftung)
    r = _sicht_dlg(dlg, fld)
    for form in dlg.findChildren(QFormLayout):
        lab = form.labelForField(fld)
        if lab is not None and lab.isVisible():
            r = r.united(_sicht_dlg(dlg, lab))
            break
    return r


def _b13(ui):
    if "kanaele" not in _LASER_BILDER:
        raise SzenenFehler("Dialog „Kanäle auswählen“ wurde nicht aufgenommen")
    return _LASER_BILDER["kanaele"]


def _b14(ui):
    if "chaser_tempo" not in _LASER_BILDER:
        raise SzenenFehler("Chaser-Dialog wurde nicht aufgenommen")
    return _LASER_BILDER["chaser_tempo"]


def _b14b(ui):
    if "chaser_schritte" not in _LASER_BILDER:
        raise SzenenFehler("Chaser-Dialog wurde nicht aufgenommen")
    return _LASER_BILDER["chaser_schritte"]


def _n14(ui):
    bs.alles_aus(ui)
    bs.druecken(ui, "Laser an")
    _fm().start(funktion(LASER).id)
    bs.ticks(ui, 2)
    beleg_laser(ui)
    bs.alles_aus(ui)


_VC_BILD = {}


def _v16(ui):
    alle_effekte_bauen(ui)
    vc_bank2(ui)
    for i, (text, fn_name, slot) in enumerate(VC_KNOEPFE):
        if vc_knopf_finden(ui, text) is not None:
            continue
        bild_fn = None
        if i == 0:
            def bild_fn(dlg, ziele, combo, slot_feld):
                return dialog_bild(ui, dlg, [
                    (_zeile_dlg(dlg, "Beschriftung:"), 1, "rechts"),
                    (_zeile_dlg(dlg, "Aktion:"), 2, "rechts"),
                    (rechteck(dlg, combo), 3, "rechts"),
                    (_zeile_dlg(dlg, "Live-Edit-Slot:"), 4, "rechts")])
        _w, erg = vc_knopf_anlegen(ui, i, text, fn_name, slot, bild_fn=bild_fn)
        _VC_BILD.update(erg)
    vc_bank_pruefen(ui)


def _b16(ui):
    if "bild" not in _VC_BILD:
        raise SzenenFehler("Dialog „Button Einstellungen“ wurde nicht aufgenommen")
    return _VC_BILD["bild"]


def _b17(ui):
    vc = _vc(ui)
    if vc._canvas._edit_mode:
        knopf(vc, "Bearbeiten ✓").click()
        ui.pump(0.3)
    beleg_vc(ui)
    _druecken(vc_knopf_finden(ui, "Lauflicht"))
    _druecken(vc_knopf_finden(ui, "Schwenker"))
    bs.ticks(ui, 10)
    ui.pump(0.4)
    vc_bank_pruefen(ui)
    kn = [vc_knopf_finden(ui, t) for t, _f, _s in VC_KNOEPFE]
    r = _win_rect(ui, kn[0])
    for w in kn[1:]:
        r = r.united(_win_rect(ui, w))
    r.adjust(-4, -4, 4, 4)
    return _bild(ui, [(r, 1, "unten"),
                      (_win_rect(ui, knopf(vc, "Bearbeiten")), 2, "unten")])


def _n17(ui):
    bs.alles_aus(ui)


# ── Bilder: 3D ──────────────────────────────────────────────────────────────

KAM_LAUF = {"name": "Doku", "mode": "3D", "theta": -0.35, "phi": 1.30, "radius": 27.0,
            "target": [0.0, 3.8, 0.5]}
KAM_MH = {"name": "Doku", "mode": "3D", "theta": 0.35, "phi": 1.42, "radius": 25.0,
          "target": [0.0, 5.5, 0.0]}
KAM_SCHWENK_A = {"name": "Doku", "mode": "3D", "theta": 0.0, "phi": 1.45, "radius": 36.0,
                 "target": [0.0, 5.0, 0.5]}
KAM_SCHWENK_B = dict(KAM_SCHWENK_A, radius=22.0, target=[0.0, 5.8, 0.0])
# Strobes: nah an die Mittel-Traverse, von schraeg unten aus dem Publikum —
# aus der Totalen gehen die acht schmalen Kegel zwischen den Movern unter.
KAM_STROBE = {"name": "Doku", "mode": "3D", "theta": 0.35, "phi": 1.72, "radius": 11.0,
              "target": [0.0, 7.6, 2.0]}
KAM_LASER = {"name": "Doku", "mode": "3D", "theta": -0.3, "phi": 1.40, "radius": 30.0,
             "target": [0.0, 5.0, 0.0]}


def _gif(name, titel, bauen, knoepfe, kam_a, kam_b, *, n=16, schritt_s=0.15,
         breite=640, beleg_fn=None, deckkraft=None, frame_fn=None, warte_s=0.12):
    """3D-GIF: Effekt ueber die Oberflaeche bauen (falls noch nicht da),
    Show-Knoepfe fuer Farbe/Licht druecken, Kamera faehrt langsam."""
    uhr = bs.Uhr()

    def vorher(ui):
        bs.viz_auf(ui)
        bs.einstellung(ui, opacity=deckkraft or STRAHL)
        bs.alles_aus(ui)
        bauen(ui)
        bs.alles_aus(ui)
        auswahl_leeren(ui)
        for k in knoepfe:
            bs.druecken(ui, k)
        bauen(ui)            # (startet die vorhandene Funktion)
        bs.sekunden(ui, 1.0)
        if beleg_fn is not None:
            beleg_fn(ui)
        bs.kamera(ui, kam_a)

    def frame_schritt(i):
        def schritt(ui):
            uhr.weiter(ui, schritt_s)
            bs.kamera_sofort(ui, bs.kamera_zwischen(kam_a, kam_b, i / max(1, n - 1)))
            if frame_fn is not None:
                frame_fn(ui, i)
        return schritt

    return Szene(name, sektion="Programmer", vorher=vorher, nachher=bs._aufraeumen,
                 braucht_gpu=True, groesse=bs._GROESSE, gif_breite=breite,
                 gif_zuschnitt=bs._GIF_ZUSCHNITT, warte_s=0.3, titel=titel,
                 frames=[Frame(dauer_s=schritt_s, schritt=frame_schritt(i),
                               dialog=bs.flaeche, warte_s=warte_s) for i in range(n)])


STRAHL = 20


def _v18(ui):
    bs.viz_auf(ui)
    v = bs.viz(ui)
    split = v.centralWidget()
    split.widget(1).show()
    for i in range(v._tabs.count()):
        if v._tabs.tabText(i).replace("&", "") == "Einstellungen":
            v._tabs.setCurrentIndex(i)
    bs.einstellung(ui, opacity=STRAHL)
    bs.alles_aus(ui)
    alle_effekte_bauen(ui)
    auswahl_leeren(ui)
    for k in ("Haze an", "Magenta", "MH Licht an", "MH Blau", "Beam schmal"):
        bs.druecken(ui, k)
    for name in (LAUF, WELLE):
        _fm().start(funktion(name).id)
    bs.sekunden(ui, 2.0)
    bs.kamera(ui, bs.KAM_SCHRAEG)
    s = v._collect_settings()
    beleg(f"3D-Einstellungen: {({k: s[k] for k in s if k in ('beamOpacity', 'opacity', 'fog', 'showFog', 'cones', 'showCones')})}")
    hz = gruppe_fids(ui, "Hazer")
    beleg(f"Hazer Nebel/Lüfter: {[(dmx(ui, f, 'dimmer'), dmx(ui, f, 'fan')) for f in hz]}")
    ui.pump(1.0)


def _b18(ui):
    from anleitungsbilder.szenen_3d_buehne import _fensterbild, _gruppe, _sichtbar
    v = bs.viz(ui)
    strahl = _sichtbar(v, ui.finde("Beam Opacity:", wurzel=v))
    for w in (v._sld_opacity, v._lbl_opacity):
        strahl = strahl.united(_sichtbar(v, w))
    strahl.adjust(-6, -4, 6, 4)
    spalte = _sichtbar(v, v._tabs)
    hell = _sichtbar(v, _gruppe("Szenen-Helligkeit")(ui)).intersected(spalte)
    ui._doku_viz = v
    return _fensterbild(ui, kreise=[
        (hell, 1, "links"),
        (strahl.intersected(spalte), 2, "links"),
        (_sichtbar(v, v._chk_fog).intersected(spalte), 3, "links"),
    ])


def _n18(ui):
    v = bs.viz(ui)
    v.centralWidget().widget(1).hide()
    ui.pump(0.5)
    bs.alles_aus(ui)


def _strobe_frame(ui, i):
    """Je GIF-Frame: Dimmer der Strobes im Display-Frame (Beleg, dass das GIF
    hell/dunkel im Wechsel zeigt)."""
    werte = {dmx(ui, f, "intensity") for f in gruppe_fids(ui, G_STROBE)}
    beleg(f"Strobe-GIF Frame {i}: Dimmer {sorted(werte)}")


def _alles_bauen_und_vc(ui):
    alle_effekte_bauen(ui)
    vc_bank2(ui)
    vc_alle_anlegen(ui)
    vc = _vc(ui)
    if vc._canvas._edit_mode:
        knopf(vc, "Bearbeiten ✓").click()
    ui.sektion("Programmer")


def _alles_vorher(ui):
    bs.viz_auf(ui)
    bs.einstellung(ui, opacity=15)
    bs.alles_aus(ui)
    _alles_bauen_und_vc(ui)
    bs.alles_aus(ui)
    auswahl_leeren(ui)
    for k in ("Haze an", "Farbwechsel", "MH Licht an", "Beam schmal", "Farbrad",
              "Laser an", "Laser Farbe"):
        bs.druecken(ui, k)
    for t in ("Lauflicht", "Schwenker", "Mein Laser"):
        _druecken(vc_knopf_finden(ui, t))
    bs.sekunden(ui, 1.5)


def _alles_gif():
    uhr = bs.Uhr()
    n, schritt_s = 16, 0.2
    kam_a = {"name": "Doku", "mode": "3D", "theta": -0.3, "phi": 1.42, "radius": 36.0,
             "target": [0.0, 5.0, 1.0]}
    kam_b = {"name": "Doku", "mode": "3D", "theta": 0.3, "phi": 1.36, "radius": 28.0,
             "target": [0.0, 5.0, 0.0]}
    wechsel = {6: ("Strobe",), 12: ("MH-Welle",)}

    def frame_schritt(i):
        def schritt(ui):
            for t in wechsel.get(i, ()):
                _druecken(vc_knopf_finden(ui, t))
            uhr.weiter(ui, schritt_s)
            bs.kamera_sofort(ui, bs.kamera_zwischen(kam_a, kam_b, i / (n - 1)))
        return schritt
    return Szene("22_alles_3d", sektion="Programmer", vorher=_alles_vorher,
                 nachher=bs._aufraeumen, braucht_gpu=True, groesse=bs._GROESSE,
                 gif_breite=560, gif_zuschnitt=bs._GIF_ZUSCHNITT, warte_s=0.3,
                 titel="GIF: alle selbst gebauten Effekte über die eigenen VC-Knöpfe, "
                       "Kamera fährt aus dem Publikum heran",
                 frames=[Frame(dauer_s=schritt_s, schritt=frame_schritt(i),
                               dialog=bs.flaeche, warte_s=0.12) for i in range(n)])


SZENEN = [
    # 1 Matrix: Lauflicht Mitte → außen
    Szene("01_matrix_gruppe", sektion="Programmer", dialog=_b01,
          titel="Gruppe „PAR alle (links → rechts)“ wählen, Reiter Matrix, „+ Neu“"),
    Szene("02_matrix_grundeinstellungen", sektion="Programmer", dialog=_b02,
          titel="Matrix: Name, Algorithmus Chase, Stil Dimmer, Geschwindigkeit, Tempo-Bus"),
    Szene("03_matrix_bewegung", sektion="Programmer", dialog=_b03, nachher=_n03,
          titel="Matrix: Bewegung Mitte→außen, Läufer-Breite, Start"),
    _gif("04_lauflicht_3d", "GIF: Lauflicht Mitte → außen über 40 PARs (Farbe: Magenta)",
         lauf_bauen, ["Magenta", "Haze an"], KAM_LAUF, dict(KAM_LAUF, theta=0.35), n=18,
         schritt_s=0.12),
    # 2 EFX-Welle
    Szene("05_efx_neu", sektion="Programmer", dialog=_b05,
          titel="Gruppe „MH alle (links → rechts)“, Reiter EFX, „+ Neu“"),
    Szene("06_efx_form", sektion="Programmer", dialog=_b06,
          titel="EFX: Name, Algorithmus Line, Breite/Höhe/Zentrum"),
    Szene("07_efx_tempo", sektion="Programmer", dialog=_b06b,
          titel="EFX: Geschwindigkeit, Tempo-Bus frei"),
    Szene("08_efx_verhaeltnis", sektion="Programmer", dialog=_b06c, nachher=_n06,
          titel="EFX: Verhältnis Fächer, Dimmer/Shutter mit öffnen, Speichern, Start"),
    _gif("09_welle_3d", "GIF: Pan-Welle über 20 Moving Heads (Farbe: MH Blau)",
         welle_bauen, ["MH Blau", "Beam schmal", "Haze an"], KAM_MH,
         dict(KAM_MH, theta=-0.3), n=15, schritt_s=0.24, deckkraft=15),
    # 3 Schwenker
    Szene("10_schwenker", sektion="Programmer", dialog=_b08, nachher=_n08,
          titel="EFX: Fester Versatz pro Gerät 180° — Schwenker im Wechsel"),
    _gif("11_schwenker_3d", "GIF: Schwenker im Wechsel, Kamera fährt heran",
         schwenk_bauen, ["Farbrad", "Beam schmal", "Haze an"],
         KAM_SCHWENK_A, KAM_SCHWENK_B, n=18, schritt_s=0.2, deckkraft=15),
    # 4 Strobe
    Szene("12_strobe", sektion="Programmer", dialog=_b10, nachher=_n10,
          titel="Matrix auf der Gruppe Strobes: Algorithmus Strobe, Stil Dimmer"),
    _gif("13_strobe_3d", "GIF: Strobe auf der Mittel-Traverse",
         strobe_bauen, ["Haze an"], KAM_STROBE,
         dict(KAM_STROBE, theta=-0.1), n=16, schritt_s=0.07, frame_fn=_strobe_frame),
    # 5 Laser
    Szene("14_laser_tab", sektion="Programmer", dialog=_b12,
          titel="Gruppe Laser, Reiter Laser, Regler X-Bewegung"),
    Szene("15_laser_kanaele", sektion="Programmer", vorher=_v13, dialog=_b13,
          titel="Programmer → Szene: Kanäle auswählen"),
    Szene("16_laser_chaser", sektion="Programmer", dialog=_b14,
          titel="Chaser „Mein Laser langsam“: Name, Run Order Loop, Tempo-Bus frei"),
    Szene("17_laser_schritte", sektion="Programmer", dialog=_b14b, nachher=_n14,
          titel="Chaser: zwei Szenen übernommen, Fade In 4 s, Schließen"),
    _gif("18_laser_3d", "GIF: Laser an, Chaser „Mein Laser langsam“ schwenkt die Strahlen",
         lambda ui: (laser_bauen(ui), _fm().start(funktion(LASER).id)),
         ["Laser an", "Laser Farbe", "Haze an"], KAM_LASER, dict(KAM_LASER, theta=0.3),
         n=14, schritt_s=0.25),
    # 6 VC
    Szene("19_vc_button", sektion="Virtual Console", vorher=_v16, dialog=_b16,
          titel="Button Einstellungen: Beschriftung, Funktion an/aus, Funktion, Slot"),
    Szene("20_vc_seite", sektion="Virtual Console", dialog=_b17, nachher=_n17,
          titel="Eigene VC-Seite mit fünf Effekt-Knöpfen"),
    # 7 3D
    Szene("21_3d_einstellungen", sektion="Programmer", vorher=_v18, dialog=_b18,
          nachher=_n18, braucht_gpu=True, groesse=bs._GROESSE,
          titel="3D-Visualizer, Reiter Einstellungen: Helligkeit, Beam Opacity, Nebel"),
    _alles_gif(),
]
