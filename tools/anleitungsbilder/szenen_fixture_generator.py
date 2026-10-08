"""DOC-65: Bilder fuer ``docs/anleitung_fixture_generator/`` — ein eigenes
Geraeteprofil mit dem Fixture Generator anlegen, am Beispiel des Show-Lasers
Laserworld EL-400RGB MK2 (FM-68).

Neu erzeugen::

    venv/bin/python tools/anleitungsbilder.py fixture_generator
    DISPLAY=:0 venv/bin/python tools/anleitungsbilder.py fixture_generator --bildschirm

Der zweite Aufruf baut NUR die 3D-Szene (``braucht_gpu``) am echten Bildschirm.

Die Anleitung tut so, als stuende der Laser noch nicht in der Bibliothek: der
Generator wird mit genau den Angaben gefuellt, die man aus der DMX-Tabelle des
Handbuchs abtippt (:data:`KANAELE` — dieselben Werte wie
``fixtures/bibliothek/laserworld/el-400rgb-mk2.json``; der Test
``test_doc65_fixture_generator_bilder`` haelt beide deckungsgleich).
Gespeichert wird im Bild nichts. Gepatcht wird danach das Bibliotheksprofil —
inhaltlich dasselbe, und die Sandbox-Bibliothek bleibt ohne Doppel.

Alles laeuft in der Sandbox des Werkzeugs (Doku-Demo-Show, Wegwerf-Datenordner).
"""
from __future__ import annotations

import json

from anleitungsbilder.runner import Szene, SzenenFehler
from anleitungsbilder.szenen_erste_schritte import bild, feld, knopf, rechteck

ZIEL = "docs/anleitung_fixture_generator/img"

HERSTELLER = "Laserworld"
MODELL = "EL-400RGB MK2"
KURZNAME = "EL400RGBMK2"
LEISTUNG_W = 30
MODUS = "9-Kanal"
LABEL = "Laser"
ADRESSE = 120

# Handbuch 8.4 „DMX-512“ (Kanal, Name, Attribut, Default, Highlight, Bereiche).
BETRIEBSART = [(0, 49, "Laser aus", "closed"),
               (50, 99, "Musik-Modus", "sound"),
               (100, 149, "Auto-Modus", ""),
               (150, 199, "Statische Muster (DMX)", "open"),
               (200, 255, "Dynamische Muster (DMX)", "open")]
KANAELE = [
    ("Betriebsart", "shutter", 0, 175, BETRIEBSART),
    ("Musterauswahl", "gobo_wheel", 0, 0, []),
    ("Position X (0-10 = Mitte)", "laser_x", 0, 0, []),
    ("Position Y (0-10 = Mitte)", "laser_y", 0, 0, []),
    ("Scangeschwindigkeit", "laser_scan_rate", 0, 0, []),
    ("Geschwindigkeit dynamische Muster", "effect_speed", 0, 0, []),
    ("Zoom / Größe", "zoom", 128, 128, []),
    ("Farbe", "laser_color", 0, 0, []),
    ("Farbsegmente", "laser_color_change", 0, 0, []),
]

GENERATOR_GROESSE = (1200, 1320)
STATISCH = 175          # Betriebsart „Statische Muster (DMX)“


# ── Generator ───────────────────────────────────────────────────────────────

def modell():
    """Generator-Modell, wie man es aus der Handbuch-Tabelle eintippt."""
    from src.ui.widgets.fixture_generator import (GenChannel, GenMode, GenRange,
                                                  GeneratorModel)
    kanaele = [GenChannel(name=n, attribute=a, default_value=d, highlight_value=h,
                          ranges=[GenRange(*b) for b in bereiche])
               for n, a, d, h, bereiche in KANAELE]
    return GeneratorModel(manufacturer=HERSTELLER, model=MODELL,
                          short_name=KURZNAME, fixture_type="laser",
                          power_w=LEISTUNG_W,
                          notes="Handbuch 8.4; Achsrichtungen am Gerät abgleichen",
                          modes=[GenMode(name=MODUS, channels=kanaele)])


def _generator(zeile: int = 0):
    """Dialog-Funktion: der Generator, gefuellt, Kanal ``zeile`` gewaehlt.

    Aufgenommen wird der Dialog allein (:data:`GENERATOR_GROESSE`) — ueber das
    1600 x 900-Hauptfenster gelegt war er zu niedrig: die Kanaltabelle schrumpfte
    auf eine Zeile. Die Marken finden ihre Widgets ueber ``ui._doku_gen``."""
    def dialog(ui):
        from src.ui.widgets.fixture_generator import FixtureGeneratorDialog
        dlg = FixtureGeneratorDialog(ui.win, model=modell())
        dlg.resize(*GENERATOR_GROESSE)
        dlg.show()
        ui.pump(0.3)
        tab = dlg._tabs.currentWidget()
        tab._tbl.selectRow(zeile)
        tab._tbl.setCurrentCell(zeile, 1)
        dlg._revalidate()
        ui.pump(0.3)
        ui._doku_gen = dlg
        _pruefen(dlg, tab)
        return dlg
    return dialog


def _pruefen(dlg, tab):
    """Was die Anleitung im Bild zeigt, muss stimmen."""
    attrs = [tab._tbl.cellWidget(i, 2).currentText() for i in range(len(KANAELE))]
    if attrs != [k[1] for k in KANAELE]:
        raise SzenenFehler(f"Kanaltabelle zeigt {attrs}")
    text = dlg._issues.toPlainText()
    if "Laser-Sicherheit" not in text or "Kanal 1" not in text:
        raise SzenenFehler(f"Laser-Sicherheit fehlt in der Prüfung: {text!r}")


def _gen(ui):
    dlg = getattr(ui, "_doku_gen", None)
    if dlg is None:
        raise SzenenFehler("Generator nicht offen")
    return dlg


def _tab(ui):
    return _gen(ui)._tabs.currentWidget()


def _w(name, wie):
    """Finder fuer ein Widget im Generator (``wie(dlg, tab) -> QWidget``)."""
    def finder(ui):
        return wie(_gen(ui), _tab(ui))
    finder.__name__ = name
    return finder


def _knopf_im(text, wo="dlg"):
    def wie(dlg, tab):
        return knopf(dlg if wo == "dlg" else tab, text)
    return _w("knopf_" + text, wie)


def _kopf(dlg, _tab):
    from PySide6.QtWidgets import QGroupBox
    return next(g for g in dlg.findChildren(QGroupBox) if g.title() == "Gerät")


def _speichern(dlg, _tab):
    from PySide6.QtWidgets import QDialogButtonBox
    return dlg._btn_box.button(QDialogButtonBox.StandardButton.Save)


def _zelle(zeile, spalte):
    """Hilfsrahmen ueber einer Tabellenzelle der Kanaltabelle."""
    def wie(_dlg, tab):
        from anleitungsbilder.szenen_programmer_grundlagen import _hilfsrahmen
        tbl = tab._tbl
        r = tbl.visualRect(tbl.model().index(zeile, spalte))
        return _hilfsrahmen(tbl.viewport(), r, f"doku_rahmen_zelle_{zeile}_{spalte}")
    return _w(f"zelle_{zeile}_{spalte}", wie)


def _bereichs_art(_dlg, tab):
    re_ = tab._range_editor
    if len(re_.ranges) != len(BETRIEBSART):
        raise SzenenFehler(f"Bereichs-Editor zeigt {len(re_.ranges)} Bereiche")
    cb = re_._tbl.cellWidget(0, 3)
    if cb.currentText() != "closed":
        raise SzenenFehler(f"„Laser aus“ hat Art {cb.currentText()!r}")
    return cb


def _gen_zu(ui):
    dlg = getattr(ui, "_doku_gen", None)
    if dlg is not None:
        try:
            dlg._live.shutdown()
        except Exception:
            pass
    ui._doku_gen = None


# ── Patchen ─────────────────────────────────────────────────────────────────

def _bild_patch(ui):
    from PySide6.QtWidgets import QTreeWidgetItemIterator
    from src.ui.widgets.fixture_browser import FixtureBrowserDialog
    dlg = FixtureBrowserDialog(ui.state.next_fid(), ui.win)
    dlg._search.setText(HERSTELLER)
    ui.pump(0.2)
    treffer = None
    it = QTreeWidgetItemIterator(dlg._tree)
    while it.value() is not None:
        item = it.value()
        if MODELL in item.text(0):
            treffer = item
            break
        it += 1
    if treffer is None:
        raise SzenenFehler(f"'{MODELL}' nicht in der Suche '{HERSTELLER}'")
    dlg._tree.setCurrentItem(treffer)
    dlg.resize(1000, 620)
    dlg.show()
    ui.pump(0.3)
    zeile = dlg._tree.visualItemRect(treffer)
    zeile.setLeft(0)
    zeile.setWidth(min(dlg._tree.viewport().width(), dlg._tree.header().length()))
    zeile.moveTopLeft(dlg._tree.viewport().mapTo(dlg, zeile.topLeft()))
    return bild(ui, dlg, [
        (rechteck(dlg, dlg._search), 1, "rechts"),
        (zeile, 2, "links"),
        (rechteck(dlg, feld(dlg, "Modus:")), 3, "rechts"),
    ], titel=dlg.windowTitle())


def _profil():
    from src.core.database import fixture_db as fdb
    for p in fdb.search_fixtures(MODELL):
        if p.name == MODELL and p.manufacturer and p.manufacturer.name == HERSTELLER:
            modi = fdb.get_modes(p.id)
            if modi:
                return p, modi[0]
    raise SzenenFehler(f"Profil '{HERSTELLER} — {MODELL}' fehlt in der Bibliothek")


def laser_fid(ui) -> int:
    """Den Laser einmal in die Doku-Show patchen (Bibliotheksprofil)."""
    from src.core.database.models import PatchedFixture
    fx = next((f for f in ui.state.get_patched_fixtures() if f.label == LABEL), None)
    if fx is not None:
        return fx.fid
    p, modus = _profil()
    fid = ui.state.next_fid()
    ui.state.add_fixture(PatchedFixture(
        fid=fid, label=LABEL, fixture_profile_id=p.id, mode_name=modus.name,
        universe=1, address=ADRESSE, channel_count=modus.channel_count,
        manufacturer_name=HERSTELLER, fixture_name=MODELL,
        fixture_type=p.fixture_type), undoable=False)
    ui.win._refresh_all_views()
    ui.pump(0.2)
    return fid


def _laser_an(ui, fid):
    ui.wert([fid], "shutter", STATISCH)
    ui.wert([fid], "gobo_wheel", 24)
    ui.wert([fid], "laser_color", 60)
    ui.wert([fid], "zoom", 140)


# ── Programmer ──────────────────────────────────────────────────────────────

def _pv(ui):
    return ui.win._programmer_view


def _laser_waehlen(ui, reiter: str):
    fid = laser_fid(ui)
    ui.waehle([fid])
    _laser_an(ui, fid)
    ui.reiter(reiter)
    ui.pump(0.4)
    return fid


def _vorschau_zu(ui, zu: bool = True):
    """Lampen-Vorschau unter dem Programmer ein-/ausklappen — sie nimmt am
    1600 x 900-Fenster den Platz, den die Laser-Regler im Bild brauchen."""
    tp = getattr(_pv(ui), "_tile_preview", None)
    if tp is not None:
        tp.set_collapsed(zu)
        ui.pump(0.1)


def _vorher_laser(ui):
    _vorschau_zu(ui, True)
    _laser_waehlen(ui, "Laser")
    lv = _pv(ui)._embedded_laser
    lv.refresh_from_selection()
    ui.pump(0.3)


def _laser_view(ui):
    return _pv(ui)._embedded_laser


def _box(titel):
    def finder(ui):
        from PySide6.QtWidgets import QGroupBox
        for g in _laser_view(ui).findChildren(QGroupBox):
            if g.title().replace("&&", "&") == titel and g.isVisible():
                return g
        raise SzenenFehler(f"Gruppe '{titel}' auf der Laser-Seite fehlt")
    finder.__name__ = f"box_{titel}"
    return finder


def _not_aus_knopf(ui):
    return _laser_view(ui)._btn_dmx_estop


def _not_aus_anzeige(ui):
    return _laser_view(ui)._lbl_dmx_estop


def _vorher_not_aus(ui):
    _vorher_laser(ui)
    _laser_view(ui)._btn_dmx_estop.click()
    ui.pump(0.3)
    if not getattr(ui.state, "laser_estop_active", False):
        raise SzenenFehler("NOT-AUS hat den DMX-Laser nicht verriegelt")


def _nachher_not_aus(ui):
    # Wieder an: Betriebsart neu waehlen (wie ein Klick auf die Kachel).
    _laser_view(ui)._on_mode_tile_clicked(STATISCH)
    # Der rote Statuszeilen-Alarm stuende sonst noch 6 s in den Folgebildern.
    ui.win.statusBar().clearMessage()
    ui.win._reset_statusbar_style()
    ui.pump(0.2)


def _vorher_efx(ui):
    from src.core.engine.efx import EfxAlgorithm
    _vorschau_zu(ui, True)
    _laser_waehlen(ui, "EFX")
    efx = _pv(ui)._embedded_efx
    efx._add_efx()                      # eigener Entwurf, Demo-EFX bleibt
    efx._sync_follow_selection()
    cur = efx._current
    if cur is None:
        raise SzenenFehler("EFX-Editor hat keine Bewegung")
    cur.algorithm = EfxAlgorithm.CIRCLE
    ziele = [(f.fid, f.pan_attr, f.tilt_attr) for f in cur.fixtures]
    if not ziele or ziele[0][1:] != ("laser_x", "laser_y"):
        raise SzenenFehler(f"EFX-Ziel bewegt nicht laser_x/laser_y: {ziele}")
    _sichtbar_machen(efx._fx_box)
    ui.pump(0.3)


def _sichtbar_machen(w):
    """Den Scrollbereich um ``w`` so schieben, dass ``w`` im Bild ist."""
    from PySide6.QtWidgets import QScrollArea
    p = w.parentWidget()
    while p is not None and not isinstance(p, QScrollArea):
        p = p.parentWidget()
    if p is not None:
        p.ensureWidgetVisible(w, 10, 10)


def _efx_geraete(ui):
    return _pv(ui)._embedded_efx._fx_box


def _efx_reiter(ui):
    from anleitungsbilder.szenen_programmer_grundlagen import _rahmen_reiter
    return _rahmen_reiter("EFX")(ui)


def _aufraeumen(ui):
    _vorschau_zu(ui, False)
    try:
        efx = _pv(ui)._embedded_efx
        cur = efx._current
        if cur is not None and getattr(cur, "_running", False):
            cur._running = False
        efx._discard_draft()            # den Laser-Entwurf nicht behalten
    except Exception:
        pass
    ui.state.set_selected_fids([])
    ui.pump(0.1)


# ── 3D (nur am echten Bildschirm) ───────────────────────────────────────────

_VIZ_GROESSE = (1700, 900)
_VIZ_KAMERA = {"name": "Doku", "mode": "3D", "theta": 0.35, "phi": 1.32,
               "radius": 11.0, "target": [0.0, 2.2, 0.0]}
_TRUSS_Y = 4.0


def _viz_aufbauen(ui):
    from PySide6.QtCore import Qt
    from anleitungsbilder.szenen_ausgabe_einrichten import frame_wie_ausgabe
    from anleitungsbilder.szenen_vc_widgets import _viz_bereit
    from src.core.stage.stage_definition import StageDefinition, StageElement, save_stage
    from src.ui.visualizer.visualizer_window import VisualizerWindow
    fid = laser_fid(ui)
    buehne = StageDefinition(name="Doku Laser")
    buehne.elements.append(StageElement(type="truss_h", x=0.0, y=_TRUSS_Y, z=0.0,
                                        w=6.0, h=0.29, d=0.29, name="Traverse"))
    if not save_stage(buehne):
        raise SzenenFehler("Bühne ließ sich in der Sandbox nicht speichern")
    ui.state.active_stage_name = buehne.name
    pos = {fid: (0.0, _TRUSS_Y - 0.4, 0.0)}
    info = ui.info
    weg = info["pars"] + info["mover"] + info["leiste"]
    for i, f in enumerate(weg):
        pos[f] = (40.0 + i, 0.2, 0.0)
    ui.state.visualizer_positions.update(pos)
    ui.waehle([fid])
    _laser_an(ui, fid)
    ui.wert([fid], "laser_x", 150)
    ui.wert([fid], "laser_y", 120)
    frame_wie_ausgabe(ui)
    ui._doku_labels_alt = getattr(ui.state, "show_fixture_labels", True)
    ui.state.show_fixture_labels = False
    viz = ui.win._visualizer_window
    if viz is None:
        viz = VisualizerWindow(ui.win)
        viz.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        ui.win._visualizer_window = viz
    viz.resize(*_VIZ_GROESSE)
    viz.show()
    ui._doku_viz = viz
    _viz_bereit(ui, viz)
    viz._bridge.push_settings(viz._collect_settings())
    viz._bridge.push_camera_preset("applycam:" + json.dumps(_VIZ_KAMERA))
    ui.pump(2.0)


def _bild_3d(ui):
    from anleitungsbilder.szenen_geraete_bibliothek import _bild_3d as grab3d
    return grab3d(ui)


def _viz_zu(ui):
    viz = getattr(ui, "_doku_viz", None)
    if viz is not None:
        viz.hide()
        ui.pump(0.2)
    ui.state.show_fixture_labels = getattr(ui, "_doku_labels_alt", True)
    ui.state.set_selected_fids([])


SZENEN = [
    Szene("01_patch_geraet_erstellen", sektion="Patchen", unterreiter="Patch",
          marken=[("Gerät erstellen…", 1, "", "unten")],
          titel="Patchen: „Gerät erstellen…“ öffnet den Fixture Generator"),
    Szene("02_generator_kopf", sektion="Patchen", unterreiter="Patch",
          dialog=_generator(), groesse=GENERATOR_GROESSE, nachher=_gen_zu,
          marken=[(_w("kopf", _kopf), 1, "", "rechts"),
                  (_w("typ", lambda d, t: d._cb_type), 2, "", "rechts"),
                  (_w("leistung", lambda d, t: d._spin_power), 3, "", "rechts"),
                  (_knopf_im("QLC+ (.qxf) importieren…"), 4, "", "rechts")],
          titel="Fixture Generator: Hersteller, Modell, Typ „laser“, Leistung"),
    Szene("03_generator_kanaele", sektion="Patchen", unterreiter="Patch",
          dialog=_generator(zeile=2), groesse=GENERATOR_GROESSE,
          nachher=_gen_zu,
          marken=[(_w("tabelle", lambda d, t: t._tbl), 1, "", "links"),
                  (_w("attr_x", lambda d, t: t._tbl.cellWidget(2, 2)), 2, "", "rechts"),
                  (_w("attr_y", lambda d, t: t._tbl.cellWidget(3, 2)), 3, "", "rechts"),
                  (_knopf_im("+ Kanal", "tab"), 4, "", "unten")],
          titel="Fixture Generator: Modus „9-Kanal“, neun Kanäle mit Attribut"),
    Szene("04_generator_bereiche", sektion="Patchen", unterreiter="Patch",
          dialog=_generator(zeile=0), groesse=GENERATOR_GROESSE,
          nachher=_gen_zu,
          marken=[(_w("bereiche", lambda d, t: t._range_editor._tbl), 1, "", "oben"),
                  (_w("art_aus", _bereichs_art), 2, "", "rechts"),
                  (_zelle(0, 3), 3, "", "unten"),
                  (_w("vorschau", lambda d, t: t._range_editor._preview), 4, "", "unten")],
          titel="Fixture Generator: Bereiche der Betriebsart, „Laser aus“ = closed"),
    Szene("05_generator_pruefen", sektion="Patchen", unterreiter="Patch",
          dialog=_generator(), groesse=GENERATOR_GROESSE, nachher=_gen_zu,
          marken=[(_knopf_im("Prüfen"), 1, "", "links"),
                  (_w("hinweise", lambda d, t: d._issues), 2, "", "oben"),
                  (_w("live", lambda d, t: d._live), 3, "", "oben"),
                  (_w("speichern", _speichern), 4, "", "oben")],
          titel="Fixture Generator: Prüfung mit Laser-Sicherheit, Live-Test, Speichern"),
    Szene("06_patch_dialog", sektion="Patchen", unterreiter="Patch",
          dialog=_bild_patch,
          titel="Gerät hinzufügen: das neue Profil unter Laserworld"),
    Szene("07_programmer_laser", sektion="Programmer", vorher=_vorher_laser,
          marken=[(_box("Betriebsart"), 1, "", "rechts"),
                  (_not_aus_knopf, 2, "", "unten"),
                  (_box("Farbe"), 3, "", "links"),
                  (_box("Bewegung & Geschwindigkeit"), 4, "", "links")],
          nachher=_aufraeumen, warte_s=0.8,
          titel="Programmer, Reiter Laser: Betriebsart, NOT-AUS, Farbe, Bewegung"),
    Szene("08_laser_not_aus", sektion="Programmer", vorher=_vorher_not_aus,
          marken=[(_not_aus_knopf, 1, "", "unten"),
                  (_not_aus_anzeige, 2, "", "unten")],
          nachher=lambda ui: (_nachher_not_aus(ui), _aufraeumen(ui)),
          warte_s=0.8,
          titel="Laser-NOT-AUS gedrückt: alle Laser dunkel, Anzeige rot"),
    Szene("09_programmer_efx", sektion="Programmer", vorher=_vorher_efx,
          marken=[(_efx_reiter, 1, "", "unten"),
                  (_efx_geraete, 2, "", "rechts")],
          nachher=_aufraeumen, warte_s=0.8,
          titel="Programmer, Reiter EFX: Kreis auf den Laser-Achsen X/Y"),
    Szene("10_3d_laser", sektion="Bühne", vorher=_viz_aufbauen,
          dialog=_bild_3d, nachher=_viz_zu, braucht_gpu=True,
          groesse=_VIZ_GROESSE,
          titel="3D-Visualizer: der Laser an der Traverse, Muster an"),
]
