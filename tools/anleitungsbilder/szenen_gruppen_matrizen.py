"""DOC-16: Bilder fuer ``docs/anleitung_gruppen_matrizen/`` (Gruppen und Matrizen).

Neu erzeugen: ``venv/bin/python tools/anleitungsbilder.py gruppen_matrizen``.

Die Anleitung erklaert den Weg am LED-Balken mit 48 Zonen. Die Doku-Demo-Show
hat dafuer die „LED-Leiste“ (Generic, 4 × RGB = vier Koepfe) — dieselben Menues
und Knoepfe, nur mit vier statt 48 Elementen. Die Bilder sagen das in der
Bildunterschrift; nachgestellt wird kein echtes Geraet.

Die Szenen legen zwei Gruppen an (``Leiste``, ``PAR · Leiste · PAR``) und
bedienen das Raster ueber die echten Methoden des Gruppen-Editors
(``_build_cell_menu``, ``_cell_menu_split``, ``_cell_menu_collapse``). Menues und
Dialoge werden nur aufgenommen, nicht ausgefuehrt.
"""
from __future__ import annotations

import json

from anleitungsbilder.runner import BREITE, HOEHE, Szene, SzenenFehler
from anleitungsbilder.szenen_erste_schritte import (
    bild, knopf, kreise_malen, rechteck, vereinigung)

ZIEL = "docs/anleitung_gruppen_matrizen/img"

LEISTE = "Leiste"
REIHE = "PAR · Leiste · PAR"


def _view(ui):
    return ui.win._fixture_group_view


def _gruppe_anlegen(ui, name: str, cols: int, rows: int, positionen: dict) -> int:
    """Gruppe direkt in der Show-DB anlegen (oder ueberschreiben) -> id."""
    from sqlalchemy import select
    from src.core.database.models import FixtureGroup
    st = ui.state
    with st._session() as s:
        g = s.execute(select(FixtureGroup).where(FixtureGroup.name == name)).scalar()
        if g is None:
            g = FixtureGroup(name=name)
            s.add(g)
        g.cols, g.rows = cols, rows
        g.positions_json = json.dumps({f"{c},{r}": v for (c, r), v in positionen.items()})
        s.commit()
        return int(g.id)


def _zeige(ui, gid: int):
    _view(ui)._reload_group_list(select_gid=gid)
    ui.pump(0.3)


def _leiste(ui) -> int:
    return ui.info["leiste"][0]


def _gruppe_leiste(ui):
    gid = _gruppe_anlegen(ui, LEISTE, 6, 3, {(0, 0): _leiste(ui)})
    _zeige(ui, gid)


def _zellrechteck(ui, col: int, row: int):
    from PySide6.QtCore import QPoint, QRect
    gw = _view(ui)._grid_widget
    cw, ch = gw.cell_size()
    oben_links = gw.mapTo(ui.win, QPoint(int(col * cw), int(row * ch)))
    return QRect(oben_links.x(), oben_links.y(), int(cw), int(ch))


# ── 1: Ueberblick ───────────────────────────────────────────────────────────

def _vorher_ueberblick(ui):
    _gruppe_leiste(ui)


def _bild_ueberblick(ui):
    v = _view(ui)
    w = ui.win
    return bild(ui, kreise=[
        (rechteck(w, v._combo_group), 1, "rechts"),
        (rechteck(w, knopf(v, "⧉ Matrizen zusammenlegen…")), 2, "rechts"),
        (rechteck(w, v._fixture_list), 3, "rechts"),
        (rechteck(w, v._btn_heads), 4, "rechts"),
        (rechteck(w, v._grid_widget), 5, "unten"),
        (rechteck(w, v._float_panel), 6, "links"),
    ])


# ── 2: Rechtsklick-Menue mit Untermenue ─────────────────────────────────────

def _menue_aufnahme(ui, menu, unter_titel: str, kreise_haupt, kreise_unter, zelle):
    """Hauptfenster + Kontextmenue + aufgeklapptes Untermenue in EIN Bild.

    ``kreise_*``: ``(text, nummer, lage)`` — Menuetexte im jeweiligen Menue.
    """
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtGui import QColor, QPainter, QPixmap
    from PySide6.QtWidgets import QLabel, QMenu
    from anleitungsbilder import marker

    def _norm(t):
        return t.replace("&", "").replace("…", "...").strip()

    sub_act = next((a for a in menu.actions()
                    if a.menu() is not None and _norm(a.text()) == _norm(unter_titel)), None)
    if sub_act is None:
        raise SzenenFehler(f"Untermenü „{unter_titel}“ fehlt — vorhanden: "
                           f"{[a.text() for a in menu.actions() if a.text()]}")
    sub = sub_act.menu()
    # Rechts NEBEN der Zelle aufklappen: der Rahmen um die Zelle liefe sonst
    # quer durch die Menuetexte.
    pos = QPoint(zelle.right() + 48, zelle.center().y())
    menu.popup(ui.win.mapToGlobal(pos))
    ui.pump(0.3)
    sub_pos = pos + QPoint(menu.width() + 2, menu.actionGeometry(sub_act).y())
    sub.popup(ui.win.mapToGlobal(sub_pos))
    ui.pump(0.3)

    def _rechtecke(m: QMenu, versatz, eintraege):
        vorhanden = {_norm(a.text()): a for a in m.actions()}
        aus = []
        for text, nr, lage in eintraege:
            act = vorhanden.get(_norm(text))
            if act is None:
                raise SzenenFehler(f"Menüpunkt „{text}“ fehlt (vorhanden: "
                                   f"{sorted(k for k in vorhanden if k)})")
            aus.append((m.actionGeometry(act).translated(versatz), nr, lage))
        return aus

    frei = marker.hindernisse(ui.win)
    pix = QPixmap(BREITE, HOEHE)
    p = QPainter(pix)
    p.drawPixmap(0, 0, ui.win.grab())
    for m, at in ((menu, pos), (sub, sub_pos)):
        mp = m.grab()
        p.drawPixmap(at, mp)
        p.setPen(QColor("#59636e"))
        p.drawRect(QRect(at.x() - 1, at.y() - 1, mp.width() + 1, mp.height() + 1))
        deckel = QRect(at.x() - 1, at.y() - 1, mp.width() + 2, mp.height() + 2)
        frei = marker.ohne(frei, deckel) + marker.hindernisse(m, versatz=at)
    p.end()
    kreise = (_rechtecke(menu, pos, kreise_haupt)
              + _rechtecke(sub, sub_pos, kreise_unter)
              + [(zelle, 1, "oben")])
    sub.close()
    menu.close()
    kreise_malen(pix, kreise, frei)
    flaeche = QLabel()
    flaeche.setFixedSize(BREITE, HOEHE)
    flaeche.setPixmap(pix)
    return flaeche


def _bild_menue(ui):
    _gruppe_leiste(ui)
    v = _view(ui)
    menu = v._build_cell_menu(0, 0)
    if menu is None:
        raise SzenenFehler("Kein Kontextmenü auf der Leisten-Zelle")
    titel = '„LED-Leiste“ aufteilen (4 Elemente)'
    return _menue_aufnahme(ui, menu, titel,
                           [(titel, 2, "links")],
                           [("als Zeile", 3, "rechts"), ("als Block...", 4, "rechts")],
                           _zellrechteck(ui, 0, 0))


# ── 3: aufgeteilt ───────────────────────────────────────────────────────────

def _aufteilen(ui):
    _gruppe_leiste(ui)
    v = _view(ui)
    fx = v._fixture_by_fid(_leiste(ui))
    if fx is None:
        raise SzenenFehler("LED-Leiste fehlt im Gruppen-Editor")
    v._cell_menu_split(fx, 4, "row", 0, 0)
    ui.pump(0.3)
    koepfe = [w for w in v._grid_widget.positions.values() if isinstance(w, str)]
    if len(koepfe) != 4:
        raise SzenenFehler(f"Aufteilen ergab {len(koepfe)} statt 4 Kopf-Zellen")


def _bild_aufgeteilt(ui):
    v = _view(ui)
    w = ui.win
    zellen = vereinigung([_zellrechteck(ui, c, 0) for c in range(4)])
    return bild(ui, kreise=[
        (zellen, 1, "unten"),
        (rechteck(w, knopf(v, "Speichern")), 2, "rechts"),
    ])


# ── 4: Leiste als EIN Element zwischen zwei PAR ─────────────────────────────

def _reihe(ui):
    pars = ui.info["pars"]
    gid = _gruppe_anlegen(ui, REIHE, 3, 1, {
        (0, 0): pars[0], (1, 0): _leiste(ui), (2, 0): pars[-1]})
    _zeige(ui, gid)


def _bild_reihe(ui):
    v = _view(ui)
    w = ui.win
    return bild(ui, kreise=[
        (_zellrechteck(ui, 1, 0), 1, "unten"),
        (rechteck(w, v._float_panel), 2, "links"),
        (rechteck(w, knopf(v, "Speichern")), 3, "rechts"),
    ])


# ── 5: Matrizen zusammenlegen ───────────────────────────────────────────────

def _bild_zusammenlegen(ui):
    """Dialog ueber den echten Knopf; im modalen Loop aufgenommen, mit
    Cancel geschlossen — es entsteht keine neue Gruppe."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox,
                                   QListWidget)
    v = _view(ui)
    ergebnis = {}

    def _aufnehmen():
        dlg = QApplication.activeModalWidget()
        if not isinstance(dlg, QDialog):
            ergebnis["fehler"] = "Dialog „Matrizen zusammenlegen“ ging nicht auf"
            return
        try:
            liste = dlg.findChild(QListWidget)
            for i in range(liste.count()):
                if liste.item(i).text() in ("PAR links", "PAR rechts"):
                    liste.item(i).setSelected(True)
            dlg.resize(420, 340)
            ui.pump(0.3)
            ok = dlg.findChild(QDialogButtonBox).button(
                QDialogButtonBox.StandardButton.Ok)
            ergebnis["bild"] = bild(ui, dlg, [
                (rechteck(dlg, liste), 1, "rechts"),
                (rechteck(dlg, ok), 2, "links"),
            ], titel=dlg.windowTitle())
        except SzenenFehler as e:
            ergebnis["fehler"] = str(e)
        finally:
            dlg.reject()

    QTimer.singleShot(300, _aufnehmen)
    knopf(v, "⧉ Matrizen zusammenlegen…").click()
    if "fehler" in ergebnis:
        raise SzenenFehler(ergebnis["fehler"])
    if "bild" not in ergebnis:
        raise SzenenFehler("Dialog wurde nicht aufgenommen")
    return ergebnis["bild"]


SZENEN = [
    Szene("01_gruppen_editor", sektion="Patchen", unterreiter="Fixture-Gruppen",
          vorher=_vorher_ueberblick, dialog=_bild_ueberblick,
          titel="Gruppen-Editor: Gruppe, Zusammenlegen, Gerätebaum, Köpfe-Knopf, "
                "Raster, Rastergröße"),
    Szene("02_rechtsklick_aufteilen", sektion="Patchen", unterreiter="Fixture-Gruppen",
          dialog=_bild_menue,
          titel="Rechtsklick auf die Leisten-Zelle: „aufteilen (4 Elemente)“"),
    Szene("03_koepfe_als_zeile", sektion="Patchen", unterreiter="Fixture-Gruppen",
          vorher=_aufteilen, dialog=_bild_aufgeteilt,
          titel="Nach „als Zeile“: vier Kopf-Zellen"),
    Szene("04_leiste_zwischen_par", sektion="Patchen", unterreiter="Fixture-Gruppen",
          vorher=_reihe, dialog=_bild_reihe,
          titel="PAR / Leiste / PAR — die Leiste als EIN Element"),
    Szene("05_matrizen_zusammenlegen", sektion="Patchen",
          unterreiter="Fixture-Gruppen", dialog=_bild_zusammenlegen,
          titel="Dialog „Matrizen zusammenlegen“"),
]
