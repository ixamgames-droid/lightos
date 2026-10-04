"""DOC-57: Bilder fuer ``docs/anleitung_geraete_bibliothek/`` (Geraete-Bibliothek
und eigene Profile).

Neu erzeugen::

    venv/bin/python tools/anleitungsbilder.py geraete_bibliothek
    DISPLAY=:0 venv/bin/python tools/anleitungsbilder.py geraete_bibliothek --bildschirm

Der zweite Aufruf baut NUR die 3D-Szene (``braucht_gpu``) am echten Bildschirm.

Dialoge werden wie in ``szenen_erste_schritte`` ueber dem Hauptfenster zu EINEM
1600 x 900-Bild zusammengesetzt (:func:`bild`). Was markiert wird, wird gegen
den Code geprueft (Knopftexte, Menuepunkte, Spaltenkopf) — ein umbenannter
Eintrag bricht die Szene mit ``SzenenFehler`` ab.

Kein Netz: der Dialog „Geräte-Bibliothek herunterladen?" wird nur gebaut und
gezeigt. Sein Konstruktor geht nicht ins Netz (die Groesse steht fest je
Quelle); geklickt wird nichts, und beim Schliessen schreibt er keinen Merker.

Das Geraet fuer die Weiss-Segmente (Schritt 4) ist synthetisch: zwei Dimmer,
zwei Weiss-Segmente, vier RGB-Pixel — wie die Testgeraete in
``tests/test_fm46b_rueckfall.py``. Es wird nur in der Sandbox-Bibliothek
angelegt und in die Doku-Demo gepatcht.
"""
from __future__ import annotations

import json

from anleitungsbilder.runner import Szene, SzenenFehler
from anleitungsbilder.szenen_erste_schritte import (bild, feld, knopf, menue_eintraege,
                                                    menue_oeffnen, rechteck,
                                                    reiter_rechteck, vereinigung)

ZIEL = "docs/anleitung_geraete_bibliothek/img"

# Bibliotheksgeraet fuer den Patch-Dialog (fixtures/bibliothek/stairville/).
SUCHE = "Stairville"
BIBLIOTHEK_GERAET = "LED PAR 36 COB RGBW 12W"

# Eigenes Profil fuer den Fixture-Editor (Schritt 3).
EIGEN_HERSTELLER = "Eigenbau"
EIGEN_MODELL = "Mini-PAR RGBW"
EIGEN_KANAELE = [
    ("Dimmer", "intensity", 0, 255),
    ("Rot", "color_r", 0, 255),
    ("Grün", "color_g", 0, 255),
    ("Blau", "color_b", 0, 255),
    ("Weiß", "color_w", 0, 255),
    ("Strobe", "shutter", 0, 0),
]

# Synthetisches Geraet mit eigener Weiss-Leiste (Schritt 4): je Weiss-Segment
# ein Dimmer direkt davor, dahinter vier RGB-Pixel.
LEISTE_HERSTELLER = "Eigenbau"
LEISTE_MODELL = "LED-Leiste 4 Pixel + 2 Weiß"
LEISTE_KURZ = "LEISTE4W2"
LEISTE_MODUS = "14-Kanal"
LEISTE_KANAELE = (
    [("Dimmer 1", "intensity", 0, 255), ("Weiß 1", "color_w", 0, 255),
     ("Dimmer 2", "intensity", 0, 255), ("Weiß 2", "color_w", 0, 255)]
    + [(f"{farbe} {i}", attr, 0, 255) for i in range(1, 5)
       for farbe, attr in (("Rot", "color_r"), ("Grün", "color_g"), ("Blau", "color_b"))])
LEISTE_LABEL = "Weiß-Leiste"
LEISTE_GRUPPE = "Weiß-Leiste"
LEISTE_ADRESSE = 101
MATRIX_NAME = "Leiste Regenbogen"

EDITOR_GROESSE = (1060, 760)


# ── Hilfen ──────────────────────────────────────────────────────────────────

def _zeile_rechteck(baum, item, bezug):
    """Ganze Zeile eines QTreeWidget-Eintrags (bis zur letzten Spalte)."""
    zeile = baum.visualItemRect(item)
    zeile.setLeft(0)
    zeile.setWidth(min(baum.viewport().width(), baum.header().length()))
    zeile.moveTopLeft(baum.viewport().mapTo(bezug, zeile.topLeft()))
    return zeile


def _spaltenkopf(tbl, bezug, text: str):
    """Rechteck des Spaltenkopfs ``text`` einer QTableWidget-Tabelle."""
    from PySide6.QtCore import QPoint, QRect
    kopf = tbl.horizontalHeader()
    for c in range(tbl.columnCount()):
        it = tbl.horizontalHeaderItem(c)
        if it is not None and it.text() == text:
            x = kopf.sectionViewportPosition(c)
            return QRect(kopf.viewport().mapTo(bezug, QPoint(x, 0)),
                         kopf.viewport().mapTo(bezug, QPoint(x + kopf.sectionSize(c) - 1,
                                                             kopf.height() - 1)))
    raise SzenenFehler(f"Spalte '{text}' fehlt in der Kanaltabelle")


def _text_rechteck(bezug, w):
    """Nur so breit/hoch wie der Inhalt (Text) von ``w`` — Beschriftungen und
    Optionsknoepfe sind im Layout ueber die ganze Dialogbreite gezogen."""
    from PySide6.QtCore import QRect
    r = rechteck(bezug, w)
    hint = w.sizeHint()
    breite = min(r.width(), hint.width() + 6)
    hoehe = min(r.height(), hint.height())
    oben = r.top() + (r.height() - hoehe) // 2
    return QRect(r.left(), oben, breite, hoehe)


def _zeile_text_rechteck(bezug, lab):
    """Wie :func:`_text_rechteck` fuer eine einzeilige Rich-Text-Beschriftung
    mit Innenrand (``sizeHint`` rechnet dort mit der umbrochenen Breite)."""
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QTextDocument
    doc = QTextDocument()
    doc.setHtml(lab.text())
    fm = lab.fontMetrics()
    r = rechteck(bezug, lab)
    rand = lab.contentsMargins()
    breite = min(r.width() - rand.left(), fm.horizontalAdvance(doc.toPlainText()) + 10)
    hoehe = fm.height() + 6
    oben = r.top() + rand.top() + (r.height() - rand.top() - rand.bottom() - hoehe) // 2
    return QRect(r.left() + rand.left() - 4, oben, breite, hoehe)


def _kanal_dicts(kanaele):
    return [{"name": n, "attribute": a, "default": d, "highlight": h}
            for n, a, d, h in kanaele]


def _editor(ui, hersteller, modell, kurz, typ, leistung, modus, kanaele):
    """Fixture-Editor wie „Datenbank → Neues Fixture-Profil..." und von Hand
    ausgefuellt (dieselben Felder, die man eintippt)."""
    from src.ui.widgets.fixture_editor import FixtureEditorDialog
    dlg = FixtureEditorDialog(ui.win)
    dlg._cb_manufacturer.setCurrentText(hersteller)
    dlg._edit_name.setText(modell)
    dlg._edit_short.setText(kurz)
    dlg._cb_type.setCurrentText(typ)
    dlg._spin_power.setValue(leistung)
    while dlg._tabs.count():
        dlg._tabs.removeTab(0)
    tab = dlg._add_mode(name=modus, channels=_kanal_dicts(kanaele))
    dlg.resize(*EDITOR_GROESSE)
    dlg.show()
    ui.pump(0.3)
    # Die grauen Leerzellen der Spalte „Weiß-Segment" nehmen die Fensterfarbe;
    # erst nach dem Zeigen ist das die dunkle des Stils (wie beim Anlegen per
    # „+ Channel" im offenen Editor).
    tab._refresh_segment_cells()
    ui.pump(0.1)
    return dlg, tab


# ── 1: Patch-Dialog mit einem Bibliotheksgeraet ─────────────────────────────

def _bild_patch_bibliothek(ui):
    from src.ui.widgets.fixture_browser import FixtureBrowserDialog
    dlg = FixtureBrowserDialog(ui.state.next_fid(), ui.win)
    dlg._search.setText(SUCHE)
    treffer = None
    for i in range(dlg._tree.topLevelItemCount()):
        it = dlg._tree.topLevelItem(i)
        if it.text(0) == f"{SUCHE} — {BIBLIOTHEK_GERAET}":
            treffer = it
    if treffer is None:
        raise SzenenFehler(f"'{BIBLIOTHEK_GERAET}' nicht in der Suche '{SUCHE}' — "
                           "Bibliothek nicht eingespielt?")
    dlg._tree.setCurrentItem(treffer)
    dlg.resize(1000, 620)
    dlg.show()
    ui.pump(0.3)
    return bild(ui, dlg, [
        (rechteck(dlg, dlg._search), 1, "rechts"),
        (_zeile_rechteck(dlg._tree, treffer, dlg), 2, "links"),
        (vereinigung([rechteck(dlg, feld(dlg, "Hersteller:")),
                      rechteck(dlg, feld(dlg, "Gerät:"))]), 3, "rechts"),
        (rechteck(dlg, feld(dlg, "Modus:")), 4, "rechts"),
    ], titel=dlg.windowTitle())


# ── 2: Menue Datenbank ──────────────────────────────────────────────────────

def _bild_menue_datenbank(ui):
    menu, pos = menue_oeffnen(ui, "Datenbank")
    laden, neu = menue_eintraege(menu, ["Geräte-Bibliothek herunterladen...",
                                        "Neues Fixture-Profil..."])
    return bild(ui, menu, [(laden, 1, "rechts"), (neu, 2, "rechts")],
                pos=pos, abdunkeln=False)


# ── 3: Dialog „Geräte-Bibliothek herunterladen?" (ohne Netz) ────────────────

def _bild_download(ui):
    from PySide6.QtWidgets import QLabel, QRadioButton
    from src.ui.widgets.bibliothek_download_dialog import BibliothekDownloadDialog

    def _kein_netz(*_a, **_k):
        raise SzenenFehler("Der Download-Dialog wollte ins Netz — in der Szene verboten")
    dlg = BibliothekDownloadDialog(ui.win, erststart=True, oeffnen=_kein_netz)
    # Nur zeigen: nichts klicken, beim Schliessen keinen Merker schreiben.
    dlg._nicht_jetzt_merken = lambda: None
    dlg.starten = lambda: (_ for _ in ()).throw(
        SzenenFehler("Download in der Szene gestartet"))
    dlg.resize(620, dlg.sizeHint().height())
    dlg.show()
    ui.pump(0.3)
    knoepfe = [b for b in dlg.findChildren(QRadioButton) if b.isVisible()]
    if len(knoepfe) != 2:
        raise SzenenFehler(f"Erwartet zwei Quellen, gefunden {len(knoepfe)}")
    status = dlg._status
    if not status.text().startswith("Download: ca."):
        raise SzenenFehler(f"Größenangabe fehlt: {status.text()!r}")
    lizenzen = [w for w in dlg.findChildren(QLabel)
                if w.isVisible() and w.text().startswith("Lizenz:")]
    if len(lizenzen) != 2:
        raise SzenenFehler("Lizenz-Zeilen fehlen")
    return bild(ui, dlg, [
        (_text_rechteck(dlg, knoepfe[0]), 1, "rechts"),
        (_text_rechteck(dlg, knoepfe[1]), 2, "rechts"),
        (_zeile_text_rechteck(dlg, lizenzen[0]), 3, "rechts"),
        (_text_rechteck(dlg, status), 4, "rechts"),
        (rechteck(dlg, knopf(dlg, "Herunterladen")), 5, "unten"),
        (rechteck(dlg, knopf(dlg, "Nicht jetzt")), 6, "unten"),
    ], titel=dlg.windowTitle())


# ── 4/5: Fixture-Editor mit eigenem Profil ──────────────────────────────────

def _editor_eigen(ui):
    return _editor(ui, EIGEN_HERSTELLER, EIGEN_MODELL, "MINIPAR", "par", 40,
                   "6-Kanal", EIGEN_KANAELE)


def _bild_editor(ui):
    from PySide6.QtWidgets import QDialogButtonBox, QFormLayout
    dlg, tab = _editor_eigen(ui)
    form = dlg.findChildren(QFormLayout)[0]
    kopf = form.geometry()
    if tab.segment_hinweis_sichtbar():
        raise SzenenFehler("FM-46-Hinweis bei einem einfachen PAR sichtbar")
    tbl = tab._tbl
    zeilen = vereinigung([rechteck(dlg, tbl.viewport())])
    attr = tbl.cellWidget(0, 2)
    box = dlg.findChildren(QDialogButtonBox)[0]
    speichern = box.button(QDialogButtonBox.StandardButton.Save)
    return bild(ui, dlg, [
        (kopf, 1, "rechts"),
        (reiter_rechteck(dlg, dlg, "6-Kanal"), 2, "rechts"),
        (zeilen, 3, "rechts"),
        (rechteck(dlg, attr), 4, "unten"),
        (rechteck(dlg, knopf(tab, "+ Channel")), 5, "unten"),
        (rechteck(dlg, knopf(dlg, "+ Mode")), 6, "unten"),
        (rechteck(dlg, speichern), 7, "oben"),
    ], titel=dlg.windowTitle())


def _bild_editor_lightos(ui):
    dlg, _tab = _editor_eigen(ui)
    return bild(ui, dlg, [
        (rechteck(dlg, knopf(dlg, "Als LightOS-Profil exportieren…")), 1, "oben"),
        (rechteck(dlg, knopf(dlg, "LightOS-Profil importieren…")), 2, "oben"),
    ], titel=dlg.windowTitle())


# ── 6/7: Weiss-Segmente (FM-46) ─────────────────────────────────────────────

def _editor_leiste(ui):
    dlg, tab = _editor(ui, LEISTE_HERSTELLER, LEISTE_MODELL, LEISTE_KURZ, "led_bar",
                       60, LEISTE_MODUS, LEISTE_KANAELE)
    tab._spin_white_rows.setValue(1)      # eigene Weiss-Leiste: eine Reihe quer
    tab._spin_grid_rows.setValue(1)       # Pixel-Raster 1 x 4
    tab._spin_grid_cols.setValue(4)
    ui.pump(0.2)
    return dlg, tab


def _segment_zellen(tab):
    from src.core.dimmer_segmente import ist_dimmer
    return [i for i, ch in enumerate(tab.channels) if ist_dimmer(ch.get("attribute"))]


def _bild_segment_hinweis(ui):
    dlg, tab = _editor_leiste(ui)
    if not tab.segment_hinweis_sichtbar():
        raise SzenenFehler("FM-46-Hinweis ist nicht sichtbar")
    tbl = tab._tbl
    zeilen = _segment_zellen(tab)
    zelle = rechteck(dlg, tbl.cellWidget(zeilen[0], 5))
    if tbl.cellWidget(zeilen[0], 5).currentText() != "—":
        raise SzenenFehler("Dimmer 1 hat schon ein Segment")
    return bild(ui, dlg, [
        (rechteck(dlg, tab._lbl_segment_hinweis), 1, "rechts"),
        (_spaltenkopf(tbl, dlg, "Weiß-Segment"), 2, "oben"),
        (zelle, 3, "links"),
        (rechteck(dlg, tab._btn_vorschlag), 4, "unten"),
    ], titel=dlg.windowTitle())


def _bild_segment_gesetzt(ui):
    dlg, tab = _editor_leiste(ui)
    if tab.vorschlag_uebernehmen(ueberschreiben=True) is not True:
        raise SzenenFehler("„Vorschlag aus Reihenfolge“ lieferte keinen Vorschlag")
    ui.pump(0.2)
    if tab.segment_hinweis_sichtbar():
        raise SzenenFehler(f"Hinweis nach dem Vorschlag noch sichtbar: "
                           f"{tab.segment_hinweis_text()!r}")
    tbl = tab._tbl
    zeilen = _segment_zellen(tab)
    werte = [tbl.cellWidget(r, 5).currentText() for r in zeilen]
    if werte != ["1", "2"]:
        raise SzenenFehler(f"Vorschlag ergab {werte}, erwartet ['1', '2']")
    return bild(ui, dlg, [
        (rechteck(dlg, tbl.cellWidget(zeilen[0], 5)), 1, "rechts"),
        (rechteck(dlg, tbl.cellWidget(zeilen[1], 5)), 2, "rechts"),
    ], titel=dlg.windowTitle())


# ── 8: Hinweis im RGB-Matrix-Editor ─────────────────────────────────────────

def _leiste_profil() -> int:
    """Das synthetische Geraet als eigenes Profil in die SANDBOX-Bibliothek
    (``bibliothek_format.importiere`` wie „LightOS-Profil importieren…")."""
    from src.core.database import bibliothek_format as BF
    from src.core.database import fixture_db as fdb
    for p in fdb.search_fixtures(LEISTE_MODELL):
        if p.name == LEISTE_MODELL:
            return p.id
    daten = BF.daten_aus_feldern(
        hersteller=LEISTE_HERSTELLER, modell=LEISTE_MODELL, kurzname=LEISTE_KURZ,
        typ="led_bar", leistung_w=60,
        modi=[(LEISTE_MODUS, _kanal_dicts(LEISTE_KANAELE), "", (1, 4), (1, 0))])
    return BF.importiere(daten)


def _matrix_vorher(ui):
    """Leiste patchen, Gruppe mit Pixel- UND Weiss-Raster anlegen (wie im
    Gruppen-Editor), Matrix fuer die Gruppe anlegen, Gruppe waehlen und den
    Programmer-Reiter „Matrix" zeigen."""
    from sqlalchemy import select
    from src.core.database.models import FixtureGroup, PatchedFixture
    from src.core.engine.rgb_matrix import MatrixStyle, RgbAlgorithm
    from src.core.group_cells import ACHSE_WEISS, zelle_fuer
    st = ui.state
    pid = _leiste_profil()
    fx = next((f for f in st.get_patched_fixtures() if f.label == LEISTE_LABEL), None)
    if fx is None:
        fid = st.next_fid()
        st.add_fixture(PatchedFixture(
            fid=fid, label=LEISTE_LABEL, fixture_profile_id=pid,
            mode_name=LEISTE_MODUS, universe=1, address=LEISTE_ADRESSE,
            channel_count=len(LEISTE_KANAELE), manufacturer_name=LEISTE_HERSTELLER,
            fixture_name=LEISTE_MODELL, fixture_type="led_bar"), undoable=False)
    else:
        fid = fx.fid
    pos = {f"{i},0": zelle_fuer(fid, "rgb", i) for i in range(4)}
    pos.update({"0,1": zelle_fuer(fid, ACHSE_WEISS, 0), "1,1": zelle_fuer(fid, ACHSE_WEISS, 0),
                "2,1": zelle_fuer(fid, ACHSE_WEISS, 1), "3,1": zelle_fuer(fid, ACHSE_WEISS, 1)})
    with st._session() as s:
        g = s.execute(select(FixtureGroup).where(
            FixtureGroup.name == LEISTE_GRUPPE)).scalar_one_or_none()
        if g is None:
            g = FixtureGroup(name=LEISTE_GRUPPE, cols=4, rows=2,
                             positions_json=json.dumps(pos))
            s.add(g)
        s.commit()
        gid = g.id
    fm = st.function_manager
    m = next((f for f in fm.all() if getattr(f, "name", "") == MATRIX_NAME), None)
    if m is None:
        m = fm.new_rgb_matrix(MATRIX_NAME)
        m.algorithm = RgbAlgorithm.RAINBOW
        m.style = MatrixStyle.RGB
        m.source_group = LEISTE_GRUPPE
    ui.win._refresh_all_views()
    ui.pump(0.2)
    # Wie ein Klick auf die Gruppe in der Programmer-Liste: setzt die Gruppe,
    # waehlt Pixel und Weiss-Segmente und oeffnet den Reiter „Matrix".
    pv = ui.win._programmer_view
    pv._refresh_group_list()
    eintraege = [pv._group_list.item(i) for i in range(pv._group_list.count())]
    item = next((it for it in eintraege
                 if it.text().strip().startswith(LEISTE_GRUPPE)), None)
    if item is None:
        raise SzenenFehler(f"Gruppe '{LEISTE_GRUPPE}' fehlt in der Programmer-Liste "
                           f"({[it.text() for it in eintraege]})")
    pv._group_list.setCurrentItem(item)
    pv._on_group_clicked(item)
    ui.pump(0.3)
    if ui.state.get_selected_group_id() != gid:
        raise SzenenFehler("Gruppe ist nach dem Klick nicht aktiv")
    view = pv._embedded_rgb
    vis = view._visible_instances()
    idx = next((i for i, x in enumerate(vis) if x is m), -1)
    if idx < 0:
        raise SzenenFehler("Matrix nicht in der Liste des Matrix-Editors")
    view._list.setCurrentRow(idx)
    view._sync_follow_selection()
    ui.pump(0.4)


def _bild_matrix_hinweis(ui):
    w = ui.win
    view = w._programmer_view._embedded_rgb
    hinweis = view._weiss_dimmer_hint
    if not hinweis.isVisible() or "Weiß-Segment" not in hinweis.text():
        raise SzenenFehler(f"Hinweis im Matrix-Editor fehlt: {hinweis.text()!r} "
                           f"(Raster: {view._grid_label.text()!r}, "
                           f"weiss={getattr(view._current, 'weiss_grid', None)!r}, "
                           f"stil={getattr(view._current, 'style', None)!r})")
    if not any(x is not None for x in (view._current.weiss_grid or [])):
        raise SzenenFehler("Matrix hat keine Weiß-Zellen")
    return bild(ui, kreise=[
        (rechteck(w, view._preview), 1, "rechts"),
        (rechteck(w, hinweis), 2, "rechts"),
    ])


def _matrix_nachher(ui):
    ui.state.set_selected_fids([])
    ui.state.set_selected_group_id(None)
    ui.pump(0.1)


# ── 9: neue 3D-Modelle (VIZ-66) — nur am echten Bildschirm ──────────────────

_VIZ_GROESSE = (1700, 900)
_VIZ_KAMERA = {"name": "Doku", "mode": "3D", "theta": 0.12, "phi": 1.3,
               "radius": 5.0, "target": [0.0, 1.6, 0.0]}
_TRUSS_Y = 3.0


def _profil(hersteller: str, modell: str):
    from src.core.database import fixture_db as fdb
    for p in fdb.search_fixtures(modell):
        if p.name == modell and p.manufacturer and p.manufacturer.name == hersteller:
            modi = fdb.get_modes(p.id)
            if not modi:
                break
            return p, modi[0]
    raise SzenenFehler(f"Profil '{hersteller} — {modell}' fehlt in der Bibliothek")


def _patch(ui, hersteller, modell, label, adresse):
    from src.core.database.models import PatchedFixture
    p, modus = _profil(hersteller, modell)
    fid = ui.state.next_fid()
    ui.state.add_fixture(PatchedFixture(
        fid=fid, label=label, fixture_profile_id=p.id, mode_name=modus.name,
        universe=1, address=adresse, channel_count=modus.channel_count,
        manufacturer_name=hersteller, fixture_name=modell,
        fixture_type=p.fixture_type), undoable=False)
    return fid


def _viz_aufbauen(ui):
    """Demo-Show + zwei Strobes (Generic) + Nebelmaschine (Stairville AF-150
    aus der Bibliothek) + eine 12-m-Traverse; PARs und Strobes haengen an der
    Traverse, die Nebelmaschine steht auf dem Boden."""
    from PySide6.QtCore import Qt
    from anleitungsbilder.szenen_ausgabe_einrichten import frame_wie_ausgabe
    from anleitungsbilder.szenen_vc_widgets import _viz_bereit
    from src.core.stage.stage_definition import StageDefinition, StageElement, save_stage
    from src.ui.visualizer.visualizer_window import VisualizerWindow
    info = ui.info
    strobes = [_patch(ui, "Generic", "Strobe 2ch", f"Strobe {i}", 201 + 2 * i)
               for i in (1, 2)]
    nebel = _patch(ui, "Stairville", "AF-150", "Nebel", 220)

    buehne = StageDefinition(name="Doku 3D-Modelle")
    buehne.elements.append(StageElement(type="truss_h", x=0.0, y=_TRUSS_Y, z=0.0,
                                        w=6.0, h=0.29, d=0.29, name="Traverse"))
    if not save_stage(buehne):
        raise SzenenFehler("Bühne ließ sich in der Sandbox nicht speichern")
    ui.state.active_stage_name = buehne.name

    haengen = _TRUSS_Y - 0.4
    pos = {}
    pars = info["pars"][:4]
    for fid, x in zip(pars, (-2.4, -1.4, 1.4, 2.4)):
        pos[fid] = (x, haengen, 0.0)
    pos[strobes[0]] = (-0.45, haengen, 0.0)
    pos[strobes[1]] = (0.45, haengen, 0.0)
    pos[nebel] = (0.0, 0.2, 0.9)
    weg = [f for f in info["pars"][4:] + info["mover"] + info["leiste"]]
    for i, fid in enumerate(weg):
        pos[fid] = (40.0 + i, 0.2, 0.0)       # weit seitlich, ausserhalb des Bildes
    ui.state.visualizer_positions.update(pos)

    farben = [(255, 40, 0), (0, 80, 255), (0, 80, 255), (255, 40, 0)]
    for fid, (r, g, b) in zip(pars, farben):
        ui.wert([fid], "intensity", 200)
        ui.wert([fid], "color_r", r)
        ui.wert([fid], "color_g", g)
        ui.wert([fid], "color_b", b)
    frame_wie_ausgabe(ui)

    # Ohne Namensschilder: sie lagen bei dieser Naehe uebereinander und
    # verdeckten die Modelle, um die es im Bild geht.
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
    # Ohne Lichtkegel und Bodenflecken: das Bild zeigt die Koerper der Modelle.
    viz._chk_cones.setChecked(False)
    viz._chk_floor.setChecked(False)
    viz._bridge.push_settings(viz._collect_settings())
    viz._bridge.push_camera_preset("applycam:" + json.dumps(_VIZ_KAMERA))
    ui.pump(2.0)


def _bild_3d(ui):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel
    from anleitungsbilder.szenen_vc_widgets import _VIZ_HINWEIS_H
    viz = getattr(ui, "_doku_viz", None)
    if viz is None:
        raise SzenenFehler("3D-Visualizer nicht offen")
    ui.pump(1.2)
    pix = viz._view.grab()
    if pix.isNull() or pix.width() < 200:
        raise SzenenFehler("3D-Ansicht liess sich nicht aufnehmen")
    pix = pix.copy(0, 0, pix.width(), pix.height() - _VIZ_HINWEIS_H)
    flaeche = QLabel()
    flaeche.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    flaeche.setFixedSize(pix.width(), pix.height())
    flaeche.setPixmap(pix)
    return flaeche


def _viz_zu(ui):
    viz = getattr(ui, "_doku_viz", None)
    if viz is not None:
        viz.hide()
        ui.pump(0.2)
    ui.state.show_fixture_labels = getattr(ui, "_doku_labels_alt", True)


SZENEN = [
    Szene("01_patch_bibliothek", sektion="Patchen", unterreiter="Patch",
          dialog=_bild_patch_bibliothek,
          titel="Gerät hinzufügen: Stairville-Gerät aus der LightOS-Bibliothek"),
    Szene("02_menue_datenbank", sektion="E/A", unterreiter="Output",
          dialog=_bild_menue_datenbank,
          titel="Menü Datenbank: Bibliothek herunterladen, neues Profil"),
    Szene("03_download_dialog", sektion="Patchen", unterreiter="Patch",
          dialog=_bild_download,
          titel="Dialog „Geräte-Bibliothek herunterladen?“ (nur gezeigt, ohne Netz)"),
    Szene("04_fixture_editor", sektion="Patchen", unterreiter="Patch",
          dialog=_bild_editor, titel="Fixture-Editor mit eigenem Profil"),
    Szene("05_lightos_profil", sektion="Patchen", unterreiter="Patch",
          dialog=_bild_editor_lightos,
          titel="Fixture-Editor: als LightOS-Profil exportieren/importieren"),
    Szene("06_weiss_segment_hinweis", sektion="Patchen", unterreiter="Patch",
          dialog=_bild_segment_hinweis,
          titel="Weiß-Segment: Hinweis bei fehlender Zuordnung"),
    Szene("07_weiss_segment_gesetzt", sektion="Patchen", unterreiter="Patch",
          dialog=_bild_segment_gesetzt,
          titel="Weiß-Segment: Zuordnung aus dem Vorschlag"),
    Szene("08_matrix_hinweis", sektion="Programmer", unterreiter="Attribute",
          vorher=_matrix_vorher, dialog=_bild_matrix_hinweis,
          nachher=_matrix_nachher, warte_s=0.8,
          titel="RGB-Matrix-Editor: Hinweis zur fehlenden Weiß-Zuordnung"),
    Szene("09_3d_modelle", sektion="Bühne", vorher=_viz_aufbauen,
          dialog=_bild_3d, nachher=_viz_zu, braucht_gpu=True, groesse=_VIZ_GROESSE,
          titel="3D-Visualizer: PAR, Strobe, Nebelmaschine und Traverse"),
]
