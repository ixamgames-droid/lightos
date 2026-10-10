"""DOC-65: Bilder fuer ``docs/anleitung_fixture_generator/`` — ein eigenes
Geraeteprofil mit dem Fixture Generator anlegen, am Beispiel des Show-Lasers
Laserworld EL-400RGB MK2 (FM-68).

**Zugleich der Test, ob man das Geraet mit der echten Oberflaeche anlegen
kann.** Alles laeuft wie ein Mensch es bedienen wuerde, ueber die sichtbaren
Widgets (``QTest``-Klicks und Tastatur):

* „Gerät erstellen…“ im Patch-Reiter oeffnet den Generator (modal, wie in der
  App); waehrend sein ``exec()`` laeuft, tippt ein Ablauf-Skript Kopf,
  Modusname, neun Kanaele (Name, Attribut, Default, Highlight) und die fuenf
  Bereiche der Betriebsart ein, klickt „Prüfen“ und „Speichern“;
* „+ Gerät hinzufügen“ oeffnet den Patch-Dialog: Suche tippen, Geraet waehlen,
  Adresse tippen, „Hinzufügen“;
* Programmer: Geraet in der Liste anklicken, Reiter Laser/EFX, Kacheln und
  NOT-AUS klicken.

Die Bilder 02–06 entstehen MITTEN in diesem Durchlauf. Damit es wirklich
„neu“ ist, nimmt der Durchlauf das mitgelieferte Bibliotheksprofil vorher aus
der SANDBOX-Datenbank. Danach vergleicht er das gespeicherte Profil mit
``fixtures/bibliothek/laserworld/el-400rgb-mk2.json`` und schreibt die
Unterschiede ins Protokoll (``[doc65]``-Zeilen).

Am echten Bildschirm (alle Szenen ``braucht_gpu``: Eingabetest und 3D)::

    DISPLAY=:0 venv/bin/python tools/anleitungsbilder.py fixture_generator --bildschirm

Optional ``LIGHTOS_DOKU_VIDEO_ORDNER=<ordner>``: legt jedes Zwischenbild des
Durchlaufs als PNG-Folge dort ab (fuer ein Video mit ffmpeg).
"""
from __future__ import annotations

import json
import os

from anleitungsbilder.runner import Szene, SzenenFehler
from anleitungsbilder.szenen_erste_schritte import (bild, feld, kreise_malen,
                                                    rechteck)

ZIEL = "docs/anleitung_fixture_generator/img"

HERSTELLER = "Laserworld"
MODELL = "EL-400RGB MK2"
KURZNAME = "EL400RGBMK2"
LEISTUNG_W = 30
NOTIZ = "Handbuch 8.4; Achsrichtungen am Gerät abgleichen"
MODUS = "9-Kanal"
ADRESSE = 120

# Handbuch 8.4 „DMX-512“ (Name, Attribut, Default, Highlight, Bereiche).
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

GENERATOR_GROESSE = (1200, 1000)    # passt auf einen 1080er-Bildschirm
STATISCH = 175          # Betriebsart „Statische Muster (DMX)“
_SCHRITT_S = 0.04       # Pause nach jeder Eingabe (sichtbar am Bildschirm)


# ── Eingabe wie ein Mensch (QTest auf den sichtbaren Widgets) ───────────────

def _tasten(w, text: str):
    """Text Taste fuer Taste an ``w`` schicken. ``QTest.keyClicks`` kennt nur
    ASCII (Umlaute brechen mit einem Qt-ASSERT ab) — Nicht-ASCII-Zeichen gehen
    als Tastenereignis mit Text, wie sie eine Tastatur mit Umlauten liefert."""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    for ch in text:
        if ch.isascii():
            QTest.keyClicks(w, ch)
            continue
        for art in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(w, QKeyEvent(art, 0, Qt.KeyboardModifier.NoModifier, ch))


def _log(text):
    if os.environ.get("LIGHTOS_DOKU_DEBUG"):
        print(f"[doc65-debug] {text}", flush=True)


def _klick(ui, w, pos=None):
    _log(f"klick {type(w).__name__} {getattr(w, 'text', lambda: '')() if hasattr(w, 'text') else ''}")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    if pos is None:
        QTest.mouseClick(w, Qt.MouseButton.LeftButton)
    else:
        QTest.mouseClick(w, Qt.MouseButton.LeftButton, pos=pos)
    ui.pump(_SCHRITT_S)
    _video(ui)


def _tippen(ui, w, text: str, *, enter: bool = False):
    """Feld anklicken, Inhalt markieren (Strg+A), ``text`` tippen."""
    _log(f"tippen {type(w).__name__} {text!r}")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    w.setFocus()
    QTest.mouseClick(w, Qt.MouseButton.LeftButton)
    QTest.keyClick(w, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    _tasten(w, text)
    if enter:
        QTest.keyClick(w, Qt.Key.Key_Return)
    ui.pump(_SCHRITT_S)
    _video(ui)


def _zelle(ui, tbl, zeile: int, spalte: int, text: str):
    """Tabellenzelle doppelklicken, im Editor tippen, Enter."""
    _log(f"zelle {zeile},{spalte} {text!r}")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    idx = tbl.model().index(zeile, spalte)
    tbl.scrollTo(idx)
    ui.pump(0.02)
    pos = tbl.visualRect(idx).center()
    QTest.mouseClick(tbl.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    QTest.mouseDClick(tbl.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    ui.pump(0.05)
    ed = QApplication.focusWidget()
    if ed is None or ed is tbl or not tbl.isAncestorOf(ed):
        raise SzenenFehler(f"Kein Zellen-Editor in Zeile {zeile + 1}, Spalte "
                           f"{spalte + 1} nach Doppelklick")
    QTest.keyClick(ed, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    _tasten(ed, text)
    QTest.keyClick(ed, Qt.Key.Key_Return)
    ui.pump(_SCHRITT_S)
    _video(ui)


def _combo_tippen(ui, combo, text: str):
    """Editierbare Combo: ins Textfeld tippen. Nicht editierbare: mit der
    Tastatur-Suche des geschlossenen Feldes waehlen (wie Tippen bei Fokus)."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    if combo.isEditable():
        _tippen(ui, combo.lineEdit(), text, enter=True)
    else:
        combo.setFocus()
        _tasten(combo, text)
        ui.pump(_SCHRITT_S)
        _video(ui)
    if combo.currentText() != text:
        raise SzenenFehler(f"Auswahl '{text}' liess sich nicht eintippen "
                           f"(steht: {combo.currentText()!r})")
    _ = Qt


# ── Video (optional) ────────────────────────────────────────────────────────

_VIDEO = {"n": 0}
_VIDEO_GROESSE = (1600, 1000)


def _video(ui, wiederholen: int = 3):
    ordner = os.environ.get("LIGHTOS_DOKU_VIDEO_ORDNER")
    if not ordner:
        return
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QColor, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication
    os.makedirs(ordner, exist_ok=True)
    w = QApplication.activeModalWidget() or ui.win
    pix = w.grab()
    leinwand = QPixmap(*_VIDEO_GROESSE)
    leinwand.fill(QColor("#0d1117"))
    p = QPainter(leinwand)
    if w is not ui.win:
        p.drawPixmap(0, 0, ui.win.grab())
        p.fillRect(leinwand.rect(), QColor(0, 0, 0, 120))
    p.drawPixmap(QPoint(max(0, (_VIDEO_GROESSE[0] - pix.width()) // 2), 0), pix)
    p.end()
    for _ in range(wiederholen):
        leinwand.save(os.path.join(ordner, f"{_VIDEO['n']:05d}.png"))
        _VIDEO["n"] += 1


# ── Bilder aus dem laufenden Dialog ─────────────────────────────────────────

def _dialog_bild(ui, dlg, kreise):
    """``dlg`` (offen, modal) als Bild mit Nummernkreisen merken.
    ``kreise``: ``(widget_oder_QRect, nummer, lage)`` in Dialog-Koordinaten."""
    from PySide6.QtCore import QRect
    from anleitungsbilder import marker
    ui.pump(0.2)
    pix = dlg.grab()
    ziele = [(r if isinstance(r, QRect) else rechteck(dlg, r), nr, lage)
             for r, nr, lage in kreise]
    kreise_malen(pix, ziele, marker.hindernisse(dlg))
    return pix


def _als_flaeche(pix):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel
    flaeche = QLabel()
    flaeche.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    flaeche.setFixedSize(pix.width(), pix.height())
    flaeche.setPixmap(pix)
    return flaeche


def _gemerkt(name):
    def dialog(ui):
        bilder = getattr(ui, "_doku_bilder", {})
        if name not in bilder:
            raise SzenenFehler(f"Bild {name} entstand nicht im Durchlauf "
                               f"({getattr(ui, '_doku_fehler', '')})")
        return _als_flaeche(bilder[name])
    dialog.__name__ = f"bild_{name}"
    return dialog


def _modal_treiben(ui, klasse, schritte, knopf_widget):
    """``knopf_widget`` klicken; sobald der modale Dialog ``klasse`` offen ist,
    ``schritte(dlg)`` darin ausfuehren. Ein Fehler schliesst den Dialog
    (sonst haengt ``exec()``) und wird danach als SzenenFehler gemeldet."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    ui._doku_fehler = ""

    def treiber():
        dlg = QApplication.activeModalWidget()
        if not isinstance(dlg, klasse):
            ui._doku_fehler = f"{klasse.__name__} ging nicht auf ({dlg!r})"
            if dlg is not None:
                dlg.reject()
            return
        try:
            schritte(dlg)
        except Exception as e:          # noqa: BLE001 — muss exec() verlassen
            ui._doku_fehler = f"{type(e).__name__}: {e}"
            dlg.reject()

    QTimer.singleShot(400, treiber)
    _klick(ui, knopf_widget)
    if ui._doku_fehler:
        raise SzenenFehler(ui._doku_fehler)


def _meldungen_beantworten(ui, runden: int = 6):
    """Rueckfragen/Warnungen (``QMessageBox``), die nach einem Klick modal
    aufgehen, festhalten und beantworten — „Ja“, sonst „OK“. Jede ist eine
    Huerde im Ablauf und landet im Protokoll (``[doc65] MELDUNG``)."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox

    def pruefen(rest=runden):
        m = QApplication.activeModalWidget()
        if isinstance(m, QMessageBox):
            text = f"{m.windowTitle()}: {m.text()}".replace("\n", " ")
            ui._doku_meldungen = getattr(ui, "_doku_meldungen", []) + [text]
            print(f"[doc65] MELDUNG {text}", flush=True)
            _video(ui, 20)
            knopf = (m.button(QMessageBox.StandardButton.Yes)
                     or m.button(QMessageBox.StandardButton.Ok))
            if knopf is not None:
                knopf.click()
            else:
                m.accept()
        if rest > 0:
            QTimer.singleShot(400, lambda: pruefen(rest - 1))
    QTimer.singleShot(400, pruefen)


def _knopf(wurzel, text):
    from PySide6.QtWidgets import QPushButton
    for b in wurzel.findChildren(QPushButton):
        if b.text().replace("&", "") == text and b.isVisible():
            return b
    raise SzenenFehler(f"Knopf '{text}' fehlt")


# ── Durchlauf 1: Fixture Generator ──────────────────────────────────────────

def _bibliotheksprofil_ausblenden(ui):
    """So tun, als stuende der Laser nicht in der Bibliothek: das mitgelieferte
    Profil aus der SANDBOX-Datenbank nehmen (nie die echte)."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from src.core.database import fixture_db as fdb
    from src.core.database.models import FixtureProfile, Manufacturer
    with Session(fdb.get_engine()) as s:
        for p in s.execute(select(FixtureProfile).join(Manufacturer).where(
                FixtureProfile.name == MODELL,
                Manufacturer.name == HERSTELLER)).scalars().all():
            s.delete(p)
        s.commit()
    try:
        from src.core.app_state import clear_channel_cache
        clear_channel_cache()
    except Exception:
        pass


def _generator_schritte(ui):
    def schritte(dlg):
        from PySide6.QtWidgets import QDialogButtonBox, QGroupBox
        bilder = ui._doku_bilder = getattr(ui, "_doku_bilder", {})
        dlg.resize(*GENERATOR_GROESSE)
        ui.pump(0.3)
        _video(ui, 10)
        # Kopf
        _tippen(ui, dlg._edit_mfr, HERSTELLER)
        _tippen(ui, dlg._edit_model, MODELL)
        _tippen(ui, dlg._edit_short, KURZNAME)
        _combo_tippen(ui, dlg._cb_type, "laser")
        _tippen(ui, dlg._spin_power.lineEdit(), str(LEISTUNG_W))
        _tippen(ui, dlg._edit_notes, NOTIZ)
        kopf = next(g for g in dlg.findChildren(QGroupBox) if g.title() == "Gerät")
        bilder["02_generator_kopf"] = _dialog_bild(ui, dlg, [
            (kopf, 1, "rechts"), (dlg._cb_type, 2, "rechts"),
            (dlg._spin_power, 3, "rechts"),
            (_knopf(dlg, "QLC+ (.qxf) importieren…"), 4, "rechts")])
        # Modus + Kanaele
        tab = dlg._tabs.currentWidget()
        _tippen(ui, tab._edit_name, MODUS, enter=True)
        while tab._tbl.rowCount() < len(KANAELE):
            _klick(ui, _knopf(tab, "+ Kanal"))
        tbl = tab._tbl
        for i, (name, attr, default, highlight, _b) in enumerate(KANAELE):
            _zelle(ui, tbl, i, 1, name)
            _combo_tippen(ui, tbl.cellWidget(i, 2), attr)
            _zelle(ui, tbl, i, 3, str(default))
            _zelle(ui, tbl, i, 4, str(highlight))
        tbl.scrollToTop()
        ui._doku_reiter_text = dlg._tabs.tabText(dlg._tabs.currentIndex())
        bilder["03_generator_kanaele"] = _dialog_bild(ui, dlg, [
            (tbl, 1, "links"), (tbl.cellWidget(2, 2), 2, "rechts"),
            (tbl.cellWidget(3, 2), 3, "rechts"),
            (_knopf(tab, "+ Kanal"), 4, "unten")])
        # Bereiche der Betriebsart
        _zelle_waehlen(ui, tbl, 0)
        re_ = tab._range_editor
        for _ in BETRIEBSART:
            _klick(ui, _knopf(re_, "+ Bereich"))
        for j, (von, bis, name, art) in enumerate(BETRIEBSART):
            _zelle(ui, re_._tbl, j, 0, str(von))
            _zelle(ui, re_._tbl, j, 1, str(bis))
            _zelle(ui, re_._tbl, j, 2, name)
            if art:
                _combo_tippen(ui, re_._tbl.cellWidget(j, 3), art)
        _zelle_waehlen(ui, tbl, 1)        # Bereiche ins Modell uebernehmen
        _zelle_waehlen(ui, tbl, 0)
        default = tbl.visualRect(tbl.model().index(0, 3))
        default.moveTopLeft(tbl.viewport().mapTo(dlg, default.topLeft()))
        bilder["04_generator_bereiche"] = _dialog_bild(ui, dlg, [
            (re_._tbl, 1, "oben"), (re_._tbl.cellWidget(0, 3), 2, "rechts"),
            (default, 3, "unten"), (re_._preview, 4, "unten")])
        # Pruefen, Speichern
        _klick(ui, _knopf(dlg, "Prüfen"))
        speichern = dlg._btn_box.button(QDialogButtonBox.StandardButton.Save)
        ui._doku_pruefung = dlg._issues.toPlainText()
        bilder["05_generator_pruefen"] = _dialog_bild(ui, dlg, [
            (_knopf(dlg, "Prüfen"), 1, "links"), (dlg._issues, 2, "oben"),
            (dlg._live, 3, "oben"), (speichern, 4, "oben")])
        _video(ui, 15)
        ui._doku_generator = dlg
        _meldungen_beantworten(ui)
        _klick(ui, speichern)
    return schritte


def _zelle_waehlen(ui, tbl, zeile):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    idx = tbl.model().index(zeile, 0)
    tbl.scrollTo(idx)
    QTest.mouseClick(tbl.viewport(), Qt.MouseButton.LeftButton,
                     pos=tbl.visualRect(idx).center())
    ui.pump(0.1)
    _video(ui)


def _durchlauf_generator(ui):
    if getattr(ui, "_doku_profil_id", None) is not None:
        return
    from src.ui.widgets.fixture_generator import FixtureGeneratorDialog
    _bibliotheksprofil_ausblenden(ui)
    ui.sektion("Patchen")
    ui.reiter("Patch")
    _modal_treiben(ui, FixtureGeneratorDialog, _generator_schritte(ui),
                   ui.finde("Gerät erstellen…"))
    dlg = getattr(ui, "_doku_generator", None)
    pid = getattr(dlg, "saved_id", None)
    if pid is None:
        raise SzenenFehler("Speichern im Generator legte kein Profil an")
    ui._doku_profil_id = pid
    _vergleich(ui, pid)


# ── Vergleich mit dem Bibliotheksprofil ─────────────────────────────────────

def vergleich_daten(gespeichert: dict, bibliothek: dict) -> list[str]:
    """Unterschiede zwischen dem im Generator angelegten Profil und dem
    Bibliotheksprofil, je Feld eine Zeile. Leer = gleich."""
    aus: list[str] = []
    for feld_ in ("hersteller", "modell", "kurzname", "typ", "leistung_w"):
        a, b = gespeichert.get(feld_), bibliothek.get(feld_)
        if a != b:
            aus.append(f"{feld_}: Generator {a!r} / Bibliothek {b!r}")
    gm = {m["name"]: m for m in gespeichert.get("modi", [])}
    for bm in bibliothek.get("modi", []):
        m = gm.get(bm["name"])
        if m is None:
            aus.append(f"Modus {bm['name']!r} fehlt (Generator: {sorted(gm)})")
            continue
        ka, kb = m["kanaele"], bm["kanaele"]
        if len(ka) != len(kb):
            aus.append(f"Modus {bm['name']!r}: {len(ka)} statt {len(kb)} Kanäle")
        for n, (x, y) in enumerate(zip(ka, kb), 1):
            for f in ("name", "attribut", "default", "highlight"):
                if x.get(f) != y.get(f):
                    aus.append(f"Kanal {n} {f}: Generator {x.get(f)!r} / "
                               f"Bibliothek {y.get(f)!r}")
            bx = [(r["von"], r["bis"], r["name"], r.get("art", ""))
                  for r in x.get("bereiche", [])]
            by = [(r["von"], r["bis"], r["name"], r.get("art", ""))
                  for r in y.get("bereiche", [])]
            if bx != by:
                aus.append(f"Kanal {n} Bereiche: Generator {bx} / Bibliothek {by}")
    return aus


def _vergleich(ui, pid):
    from src.core.database import bibliothek_format as BF
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(repo, "fixtures", "bibliothek", "laserworld",
                           "el-400rgb-mk2.json"), encoding="utf-8") as f:
        bib = json.load(f)
    from sqlalchemy.orm import Session
    from src.core.database import fixture_db as fdb
    with Session(fdb.get_engine()) as s:
        daten = BF.profil_zu_daten(BF._profil_laden(s, pid))
    unterschiede = vergleich_daten(daten, bib)
    ui._doku_vergleich = unterschiede
    print(f"[doc65] Generator-Profil id={pid} gespeichert; Prüfung: "
          f"{ui._doku_pruefung!r}", flush=True)
    print(f"[doc65] Reitertext nach Modusname: {ui._doku_reiter_text!r}", flush=True)
    if unterschiede:
        for z in unterschiede:
            print(f"[doc65] UNTERSCHIED {z}", flush=True)
    else:
        print("[doc65] Profil aus dem Generator = Bibliotheksprofil "
              "(Kopf, Modus, Kanäle, Defaults, Bereiche)", flush=True)


# ── Durchlauf 2: Patchen ────────────────────────────────────────────────────

def _patch_schritte(ui):
    def schritte(dlg):
        from PySide6.QtWidgets import QTreeWidgetItemIterator
        dlg.resize(1000, 620)
        ui.pump(0.3)
        _tippen(ui, dlg._search, HERSTELLER)
        treffer = None
        it = QTreeWidgetItemIterator(dlg._tree)
        while it.value() is not None:
            if MODELL in it.value().text(0):
                treffer = it.value()
                break
            it += 1
        if treffer is None:
            raise SzenenFehler(f"'{MODELL}' nicht in der Suche '{HERSTELLER}'")
        dlg._tree.scrollToItem(treffer)
        _klick(ui, dlg._tree.viewport(), dlg._tree.visualItemRect(treffer).center())
        _tippen(ui, dlg._spin_address.lineEdit(), str(ADRESSE))
        zeile = dlg._tree.visualItemRect(treffer)
        zeile.setLeft(0)
        zeile.setWidth(min(dlg._tree.viewport().width(), dlg._tree.header().length()))
        zeile.moveTopLeft(dlg._tree.viewport().mapTo(dlg, zeile.topLeft()))
        ui._doku_patch_kreise = [
            (rechteck(dlg, dlg._search), 1, "rechts"), (zeile, 2, "links"),
            (rechteck(dlg, feld(dlg, "Modus:")), 3, "rechts"),
            (rechteck(dlg, dlg._spin_address), 4, "rechts")]
        ui._doku_patch_label = dlg._edit_label.text()
        ui._doku_bilder["06_patch_dialog"] = _patch_bild(ui, dlg)
        _klick(ui, dlg._btn_add)
    return schritte


def _patch_bild(ui, dlg):
    """Wie die anderen Patch-Bilder: Dialog ueber dem abgedunkelten Fenster.
    ``bild`` schliesst das Popup danach — beim modalen Dialog waere das ein
    Abbruch; deshalb hier ein Abbild des Dialogs als Popup."""
    flaeche = _als_flaeche(dlg.grab())
    flaeche.setWindowTitle(dlg.windowTitle())
    return bild(ui, flaeche, ui._doku_patch_kreise,
                titel=dlg.windowTitle()).pixmap()


def _durchlauf_patch(ui):
    if getattr(ui, "_doku_fid", None) is not None:
        return
    from src.ui.widgets.fixture_browser import FixtureBrowserDialog
    _durchlauf_generator(ui)
    ui.sektion("Patchen")
    ui.reiter("Patch")
    _modal_treiben(ui, FixtureBrowserDialog, _patch_schritte(ui),
                   ui.finde("+ Gerät hinzufügen"))
    fx = next((f for f in ui.state.get_patched_fixtures()
               if f.fixture_profile_id == ui._doku_profil_id), None)
    if fx is None:
        raise SzenenFehler("„Hinzufügen“ hat das Gerät nicht gepatcht")
    if fx.address != ADRESSE:
        raise SzenenFehler(f"Gepatcht auf Adresse {fx.address}, getippt {ADRESSE}")
    ui._doku_fid = fx.fid
    print(f"[doc65] gepatcht: fid {fx.fid}, Label {fx.label!r}, "
          f"U{fx.universe}.{fx.address}, Modus {fx.mode_name!r}", flush=True)


def laser_fid(ui) -> int:
    _durchlauf_patch(ui)
    return ui._doku_fid


def _laser_an(ui, fid):
    """Laser einschalten wie am Bildschirm: Betriebs-Kachel und Regler."""
    lv = _laser_view(ui)
    lv.refresh_from_selection()
    ui.pump(0.2)
    from src.ui.widgets.preset_tile import PresetTile
    kacheln = [t for t in lv._mode_box.findChildren(PresetTile) if t.isVisible()]
    kachel = next((t for t in kacheln if t._payload == (150 + 199) // 2), None)
    if kachel is None:
        raise SzenenFehler("Kachel „Statische Muster (DMX)“ fehlt auf der Laser-Seite")
    _klick(ui, kachel)
    for attr, wert in (("gobo_wheel", 24), ("laser_color", 60), ("zoom", 140)):
        row = lv._rows.get(attr)
        if row is None:
            raise SzenenFehler(f"Kein Regler für {attr} auf der Laser-Seite")
        _tippen(ui, row._spin.lineEdit(), str(wert), enter=True)
    _ = fid


# ── Programmer ──────────────────────────────────────────────────────────────

def _pv(ui):
    return ui.win._programmer_view


def _reiter_klicken(ui, text):
    """Programmer-Reiter per Mausklick auf die Reiterleiste."""
    tabs = _pv(ui)._main_tabs
    bar = tabs.tabBar()
    for i in range(tabs.count()):
        if tabs.tabText(i) == text:
            if not tabs.isTabVisible(i):
                raise SzenenFehler(f"Reiter '{text}' ist für die Auswahl ausgeblendet")
            _klick(ui, bar, bar.tabRect(i).center())
            ui.pump(0.2)
            return
    raise SzenenFehler(f"Reiter '{text}' fehlt")


def _geraet_anklicken(ui, fid):
    """Das Geraet in der Programmer-Geraeteliste anklicken."""
    lst = _pv(ui)._fixture_list
    lst.clearSelection()
    ui.pump(0.05)
    for i in range(lst.topLevelItemCount()):
        it = lst.topLevelItem(i)
        if str(it.data(0, 0x0100)) == str(fid):     # Qt.UserRole
            lst.scrollToItem(it)
            ui.pump(0.05)
            _klick(ui, lst.viewport(), lst.visualItemRect(it).center())
            if [int(f) for f in ui.state.get_selected_fids()] != [int(fid)]:
                raise SzenenFehler("Klick in die Geräteliste wählte den Laser nicht")
            return
    raise SzenenFehler(f"Gerät {fid} fehlt in der Programmer-Geräteliste")


def _laser_waehlen(ui, reiter: str):
    fid = laser_fid(ui)
    ui.sektion("Programmer")
    ui.reiter("Attribute")
    _geraet_anklicken(ui, fid)
    _reiter_klicken(ui, "Laser")
    _laser_an(ui, fid)
    if reiter != "Laser":
        _reiter_klicken(ui, reiter)
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
    _klick(ui, _laser_view(ui)._btn_dmx_estop)
    ui.pump(0.3)
    if not getattr(ui.state, "laser_estop_active", False):
        raise SzenenFehler("NOT-AUS hat den DMX-Laser nicht verriegelt")


def _nachher_not_aus(ui):
    # Wieder an: Betriebsart neu waehlen (Klick auf die Kachel).
    from PySide6.QtWidgets import QApplication
    _laser_an(ui, None)
    if getattr(ui.state, "laser_estop_active", False):
        raise SzenenFehler("Klick auf „Statische Muster“ löste den NOT-AUS nicht")
    _ = QApplication
    # Der rote Statuszeilen-Alarm stuende sonst noch 6 s in den Folgebildern.
    ui.win.statusBar().clearMessage()
    ui.win._reset_statusbar_style()
    ui.pump(0.2)


def _vorher_efx(ui):
    from src.core.engine.efx import EfxAlgorithm
    _vorschau_zu(ui, True)
    _laser_waehlen(ui, "EFX")
    efx = _pv(ui)._embedded_efx
    _klick(ui, _knopf(efx, "+ Neu"))     # eigener Entwurf, Demo-EFX bleibt
    _combo_tippen(ui, efx._algo_combo, "Circle")
    cur = efx._current
    if cur is None:
        raise SzenenFehler("EFX-Editor hat keine Bewegung")
    if cur.algorithm != EfxAlgorithm.CIRCLE:
        raise SzenenFehler(f"Algorithmus nach Eingabe: {cur.algorithm}")
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
    for attr, wert in (("shutter", STATISCH), ("gobo_wheel", 24),
                       ("laser_color", 60), ("zoom", 140)):
        ui.wert([fid], attr, wert)
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
    ui.pump(0.1)


SZENEN = [
    Szene("01_patch_geraet_erstellen", sektion="Patchen", unterreiter="Patch",
          marken=[("Gerät erstellen…", 1, "", "unten")], braucht_gpu=True,
          titel="Patchen: „Gerät erstellen…“ öffnet den Fixture Generator"),
    Szene("02_generator_kopf", sektion="Patchen", unterreiter="Patch",
          vorher=_durchlauf_generator, dialog=_gemerkt("02_generator_kopf"),
          groesse=GENERATOR_GROESSE, braucht_gpu=True,
          titel="Fixture Generator: Hersteller, Modell, Typ „laser“, Leistung (eingetippt)"),
    Szene("03_generator_kanaele", sektion="Patchen", unterreiter="Patch",
          vorher=_durchlauf_generator, dialog=_gemerkt("03_generator_kanaele"),
          groesse=GENERATOR_GROESSE, braucht_gpu=True,
          titel="Fixture Generator: Modus „9-Kanal“, neun Kanäle mit Attribut (eingetippt)"),
    Szene("04_generator_bereiche", sektion="Patchen", unterreiter="Patch",
          vorher=_durchlauf_generator, dialog=_gemerkt("04_generator_bereiche"),
          groesse=GENERATOR_GROESSE, braucht_gpu=True,
          titel="Fixture Generator: Bereiche der Betriebsart, „Laser aus“ = closed"),
    Szene("05_generator_pruefen", sektion="Patchen", unterreiter="Patch",
          vorher=_durchlauf_generator, dialog=_gemerkt("05_generator_pruefen"),
          groesse=GENERATOR_GROESSE, braucht_gpu=True,
          titel="Fixture Generator: Prüfung mit Laser-Sicherheit, Live-Test, Speichern"),
    Szene("06_patch_dialog", sektion="Patchen", unterreiter="Patch",
          vorher=_durchlauf_patch, dialog=_gemerkt("06_patch_dialog"),
          braucht_gpu=True,
          titel="Gerät hinzufügen: das neue Profil unter Laserworld, Adresse 120"),
    Szene("07_programmer_laser", sektion="Programmer", vorher=_vorher_laser,
          marken=[(_box("Betriebsart"), 1, "", "rechts"),
                  (_not_aus_knopf, 2, "", "unten"),
                  (_box("Farbe"), 3, "", "links"),
                  (_box("Bewegung & Geschwindigkeit"), 4, "", "links")],
          nachher=_aufraeumen, warte_s=0.8,
          braucht_gpu=True,
          titel="Programmer, Reiter Laser: Betriebsart, NOT-AUS, Farbe, Bewegung"),
    Szene("08_laser_not_aus", sektion="Programmer", vorher=_vorher_not_aus,
          marken=[(_not_aus_knopf, 1, "", "unten"),
                  (_not_aus_anzeige, 2, "", "unten")],
          nachher=lambda ui: (_nachher_not_aus(ui), _aufraeumen(ui)),
          warte_s=0.8,
          braucht_gpu=True,
          titel="Laser-NOT-AUS gedrückt: alle Laser dunkel, Anzeige rot"),
    Szene("09_programmer_efx", sektion="Programmer", vorher=_vorher_efx,
          marken=[(_efx_reiter, 1, "", "unten"),
                  (_efx_geraete, 2, "", "rechts")],
          nachher=_aufraeumen, warte_s=0.8,
          braucht_gpu=True,
          titel="Programmer, Reiter EFX: Kreis auf den Laser-Achsen X/Y"),
    Szene("10_3d_laser", sektion="Bühne", vorher=_viz_aufbauen,
          dialog=_bild_3d, nachher=_viz_zu, braucht_gpu=True,
          groesse=_VIZ_GROESSE,
          titel="3D-Visualizer: der Laser an der Traverse, Muster an"),
]
