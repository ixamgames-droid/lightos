"""DOC-73: Bilder fuer Abschnitt 5 von
``docs/anleitung_dimmermatrix/ANLEITUNG_DIMMERMATRIX.md`` — Modify-Effekte
(ENG-37, ENG-38, ENG-40).

Neu erzeugen::

    venv/bin/python tools/anleitungsbilder.py dimmermatrix

Die Szenen arbeiten mit der Doku-Demo-Show (acht PARs in einer Reihe, Gruppe
„Alle PAR"): Gruppe in der Programmer-Liste anklicken, Reiter Matrix, „+ Neu",
Felder setzen, „💾 Speichern" — wie in der Anleitung. Die Lampenreihen sind
Ausschnitte der 2D-Bühne (Sektion Bühne). Sie zeigt den Frame, den die
Ausgabe senden wuerde (``get_display_frame``); gerechnet wird mit dem echten
``OutputManager._send_all`` ohne zu senden (``szenen_buehnen_show.ticks``).
Jede Lampenreihe wird vorher per DMX belegt — tut der Effekt nicht, was die
Anleitung sagt, bricht die Szene ab (``BELEG …``-Zeilen im Lauf).

Der Untergrund (40 %) kommt aus dem Programmer — die Anleitung sagt
ausdruecklich, dass Modify auf Snap/Programmer genauso rechnet wie auf einen
Effekt darunter.

Die Bilder 03 bis 13 bauen aufeinander auf (dieselbe Matrix); einzeln mit
``--nur`` laufen sie nur zusammen mit ihren Vorgaengern. Die letzte Szene
raeumt ab (Funktionen weg, Programmer leer).
"""
from __future__ import annotations

from anleitungsbilder.runner import Frame, Szene, SzenenFehler
from anleitungsbilder.szenen_buehnen_effekte import (
    _combo_daten, _combo_text, _oben, _pv, _sichtbar, _zeile, beleg,
    gruppe_waehlen, kanal, reiter)
from anleitungsbilder.szenen_buehnen_show import ticks
from anleitungsbilder.szenen_erste_schritte import bild, knopf, rechteck

ZIEL = "docs/anleitung_dimmermatrix/img"

G = "Alle PAR"
MOD = "Modify-Lauflicht"
MOD_RGB = "Modify Rot"
FUNKELN = "Funkeln"
UNTEN = 102                 # 40 % als DMX-Wert


# ── Grundlagen ──────────────────────────────────────────────────────────────

def _fm():
    from src.core.engine.function_manager import get_function_manager
    return get_function_manager()


def funktion(name):
    for f in _fm().all():
        if f.name == name:
            return f
    raise SzenenFehler(f"Funktion „{name}“ fehlt")


def _mx(ui):
    return _pv(ui)._embedded_rgb


def pars(ui):
    return list(ui.info["pars"])


def dmx(ui, fid, attr):
    u, i = kanal(ui, fid, attr)
    frame = ui.state.output_manager.get_display_frame(u)
    if frame is None:
        raise SzenenFehler("noch kein DMX-Frame gerechnet")
    return int(frame[i])


def prozent(ui, attr="intensity"):
    return [round(dmx(ui, f, attr) * 100 / 255) for f in pars(ui)]


def alles_aus(ui):
    _fm().stop_all()
    ui.state.clear_programmer()
    ui.waehle([])
    ticks(ui, 3)


def programmer_start(ui):
    """Programmer, Reiter Attribute, nichts gewaehlt, Lampen-Vorschau zu."""
    ui.sektion("Programmer")
    ui.reiter("Attribute")
    pv = _pv(ui)
    pv._main_tabs.setCurrentIndex(0)
    ui.pump(0.2)
    pv._fixture_list.clearSelection()
    pv._group_list.clearSelection()
    ui.waehle([])
    pv._tile_preview.set_collapsed(True)
    ui.pump(0.2)


def matrix_neu(ui, name, *, stil="Dimmer", gruppe=G, algo="Chase"):
    """Gruppe anklicken, Reiter Matrix, „+ Neu", Name/Algorithmus/Stil."""
    programmer_start(ui)
    gruppe_waehlen(ui, gruppe)
    reiter(ui, "Matrix")
    m = _mx(ui)
    knopf(m, "+ Neu").click()
    ui.pump(0.3)
    m._name_edit.selectAll()
    m._name_edit.setText(name)
    _combo_text(m._algo_combo, algo)
    _combo_text(m._style_combo, stil)
    ui.pump(0.3)
    return m


def matrix_zeigen(ui, name, gruppe=G):
    """Gespeicherte Matrix im Editor anzeigen (Gruppe, Reiter, Listen-Klick)."""
    programmer_start(ui)
    gruppe_waehlen(ui, gruppe)
    reiter(ui, "Matrix")
    m = _mx(ui)
    lst = m._list
    for i in range(lst.count()):
        it = lst.item(i)
        if it.text().strip() == name:
            lst.setCurrentItem(it)
            ui.pump(0.3)
            return m
    raise SzenenFehler(f"„{name}“ steht nicht in der Matrix-Liste")


def lauf_felder(ui, *, breite=1, anzahl=2, schritt=1, tempo=2.0):
    m = _mx(ui)
    w = m._param_widgets
    for key, wert in (("runner_count", anzahl), ("runner_width", breite),
                      ("after_fade", 0.0)):
        if key not in w:
            raise SzenenFehler(f"Matrix-Parameter {key} fehlt ({sorted(w)})")
        w[key].setValue(wert)
    m._runner_step_spin.setValue(schritt)
    _combo_daten(m._tempo_bus_combo, "")          # Frei (nicht taktgebunden)
    m._speed_spin.setValue(tempo)
    ui.pump(0.3)


def speichern(ui):
    knopf(_mx(ui), "💾 Speichern").click()
    ui.pump(0.3)


def _scroll_zu(ui, w, rand=40):
    m = _mx(ui)
    _oben(ui, m._editor_scroll, w, rand=rand)


# ── 03/04: Haken Modify-Effekt ─────────────────────────────────────────────

def _b03(ui):
    alles_aus(ui)
    m = matrix_neu(ui, MOD)
    lauf_felder(ui)
    _scroll_zu(ui, m._style_combo, rand=100)
    body = m._editor_body
    return bild(ui, kreise=[
        (_zeile(ui, body, "Stil:"), 1, "rechts"),
        (_sichtbar(ui, m._cb_modify), 2, "rechts"),
    ])


def _b04(ui):
    m = _mx(ui)
    m._cb_modify.setChecked(True)
    ui.pump(0.3)
    body = m._editor_body
    if not m._grp_modify.isVisible():
        raise SzenenFehler("Gruppe „Modify“ erscheint nicht")
    _scroll_zu(ui, m._grp_modify, rand=30)
    return bild(ui, kreise=[
        (_zeile(ui, body, "Betriebsart:"), 1, "rechts"),
        (_zeile(ui, body, "Stärke:"), 2, "rechts"),
        (_sichtbar(ui, m._modify_hint), 3, "rechts"),
    ])


def _n04(ui):
    speichern(ui)
    f = funktion(MOD)
    beleg(f"{MOD}: modify={f.modify} Art={f.modify_mode} Stärke={f.modify_strength}")
    if not f.modify:
        raise SzenenFehler("Haken Modify-Effekt nicht gespeichert")


# ── Lampenreihe aus der 2D-Bühne ────────────────────────────────────────────

def _reihe_rechteck(ui):
    """Rechteck um PAR 1–8 auf der 2D-Bühne (Prozent-Zeile bis Name)."""
    from PySide6.QtCore import QPoint, QRect
    c = ui.win._live_view._canvas
    r = c._fixture_size * c.zoom
    ganz = None
    for fid in pars(ui):
        x, y = c._positions[fid]
        mitte = c.mapTo(ui.win, QPoint(int(x * c.zoom), int(y * c.zoom)))
        q = QRect(int(mitte.x() - 1.5 * r), int(mitte.y() - 1.9 * r),
                  int(3.0 * r), int(3.7 * r))
        ganz = q if ganz is None else ganz.united(q)
    return ganz


def reihe_aufnehmen(ui):
    """Aktuellen Ausgabe-Frame auf der 2D-Bühne als Bild der PAR-Reihe."""
    sektion_alt = ui.win._stack.currentIndex()
    ui.sektion("Bühne")
    c = ui.win._live_view._canvas
    c.update()
    ui.pump(0.4)
    pix = ui.win.grab(_reihe_rechteck(ui))
    ui.win._switch_section(sektion_alt)
    ui.pump(0.1)
    return pix


def reihen_bild(zeilen, *, titel=None):
    """``zeilen``: Liste ``(beschriftung, pixmap)`` -> QLabel, Zeilen
    untereinander, Beschriftung links."""
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
    from PySide6.QtWidgets import QLabel
    from anleitungsbilder.runner import SCHRIFT_FAMILIE
    links, rand, abstand = 250, 12, 6
    breite = links + max(p.width() for _t, p in zeilen) + rand
    kopf = 34 if titel else 0
    hoehe = kopf + sum(p.height() for _t, p in zeilen) + abstand * (len(zeilen) - 1) + 2 * rand
    pix = QPixmap(breite, hoehe)
    pix.fill(QColor("#0d1117"))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    y = rand
    if titel:
        f = QFont(SCHRIFT_FAMILIE, 13)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#e6edf3"))
        p.drawText(QRect(rand, y, breite - 2 * rand, kopf - 6),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, titel)
        y += kopf
    f = QFont(SCHRIFT_FAMILIE, 12)
    p.setFont(f)
    for text, z in zeilen:
        # „0 %“ nie über zwei Zeilen umbrechen (DOC-73-Prüfung).
        text = text.replace(" %", "\u00a0%")
        p.fillRect(QRect(rand - 4, y, breite - 2 * rand + 8, z.height()), QColor("#161b22"))
        p.setPen(QColor("#e6edf3"))
        p.drawText(QRect(rand + 6, y, links - rand - 16, z.height()),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                   | Qt.TextFlag.TextWordWrap, text)
        p.drawPixmap(links, y, z)
        y += z.height() + abstand
    p.end()
    lab = QLabel()
    lab.setFixedSize(pix.size())
    lab.setPixmap(pix)
    return lab


def untergrund(ui, wert=UNTEN, farbe=(255, 255, 255)):
    """Programmer: alle PARs auf ``wert`` (Dimmer) in ``farbe``."""
    ui.wert(pars(ui), "intensity", wert)
    for attr, v in zip(("color_r", "color_g", "color_b"), farbe):
        ui.wert(pars(ui), attr, v)
    ui.waehle([])


def bis_laeufer(ui, lampen, attr="intensity", schwelle=200, max_ticks=400):
    """Ticken, bis genau die Lampen ``lampen`` (1-basiert) ueber ``schwelle``
    stehen."""
    for _ in range(max_ticks):
        ticks(ui, 1)
        an = [i + 1 for i, f in enumerate(pars(ui)) if dmx(ui, f, attr) >= schwelle]
        if an == list(lampen):
            return
    raise SzenenFehler(f"Läufer erreicht {lampen} nicht (zuletzt {an})")


def _modify_setzen(ui, name, art, staerke):
    f = funktion(name)
    f.modify_mode = art
    f.modify_strength = staerke
    return f


def erwarte(ist, soll, was):
    beleg(f"{was}: {ist}")
    if ist != soll:
        raise SzenenFehler(f"{was}: {ist}, erwartet {soll}")


# ── 05: Untergrund / Modify allein / Addieren ──────────────────────────────

def _lampen_addieren(ui):
    alles_aus(ui)
    f = _modify_setzen(ui, MOD, "add", 100)
    _fm().start(f.id)
    # Modify allein: Dimmer 0 darunter (Farbe weiss) — Addieren rechnet auf 0.
    untergrund(ui, wert=0)
    bis_laeufer(ui, [3, 7])
    allein = reihe_aufnehmen(ui)
    erwarte(prozent(ui), [0, 0, 100, 0, 0, 0, 100, 0], "Modify allein (Dimmer %)")
    untergrund(ui)
    ticks(ui, 1)
    erwarte(prozent(ui), [40, 40, 100, 40, 40, 40, 100, 40], "Addieren 100 % (Dimmer %)")
    ergebnis = reihe_aufnehmen(ui)
    _fm().stop(f.id)
    ticks(ui, 2)
    erwarte(prozent(ui), [40] * 8, "Untergrund allein (Dimmer %)")
    unten = reihe_aufnehmen(ui)
    return reihen_bild([("Darunter: 40 % (Programmer)", unten),
                        ("Modify-Lauflicht allein (darunter 0 %)", allein),
                        ("Ergebnis: Addieren, Stärke 100 %", ergebnis)])


def _lampen_abziehen(ui):
    alles_aus(ui)
    untergrund(ui)
    ticks(ui, 2)
    unten = reihe_aufnehmen(ui)
    zeilen = [("Darunter: 40 % (Programmer)", unten)]
    for art, text, soll in (("sub", "Abziehen, Stärke 50 %", 0),
                            ("dim", "Abdunkeln, Stärke 50 %", 20)):
        f = _modify_setzen(ui, MOD, art, 50)
        _fm().start(f.id)
        _bis_dunkel(ui, [3, 7])
        erwarte(prozent(ui), [40, 40, soll, 40, 40, 40, soll, 40], f"{text} (Dimmer %)")
        zeilen.append((text, reihe_aufnehmen(ui)))
        _fm().stop(f.id)
        ticks(ui, 2)
    return reihen_bild(zeilen)


def _bis_dunkel(ui, lampen, max_ticks=400):
    """Ticken, bis genau ``lampen`` unter dem Untergrund liegen."""
    for _ in range(max_ticks):
        ticks(ui, 1)
        werte = [dmx(ui, f, "intensity") for f in pars(ui)]
        unter = [i + 1 for i, v in enumerate(werte) if v < UNTEN - 5]
        if unter == list(lampen):
            return
    raise SzenenFehler(f"Läufer erreicht {lampen} nicht (zuletzt {unter})")


def _n_lampen(ui):
    alles_aus(ui)


# ── 07/08: Taste und Fader an der Virtuellen Konsole, GIF an/aus ───────────

_TASTE = "doku_dm_modify_taste"
_FADER = "doku_dm_modify_fader"


def _canvas(ui):
    return ui.win._vc_view._canvas


def _vc_widget(ui, name):
    from PySide6.QtWidgets import QWidget
    return _canvas(ui).findChild(QWidget, name)


def vc_anlegen(ui):
    """Taste (Funktion an/aus) und Fader (Effekt-Parameter Modify-Stärke)
    für das Modify-Lauflicht auf Bank 1."""
    from PySide6.QtCore import QPoint
    from src.ui.virtualconsole.vc_button import ButtonAction
    from src.ui.virtualconsole.vc_slider import SliderMode
    ui.sektion("Virtual Console")
    canvas = _canvas(ui)
    fid = funktion(MOD).id
    t = _vc_widget(ui, _TASTE)
    if t is None:
        t = canvas._add_widget("VCButton", QPoint(700, 300))
        t.setObjectName(_TASTE)
    t.caption = "Modify-Lauflicht"
    t.resize(150, 70)
    t.action = ButtonAction.FUNCTION_TOGGLE
    t.function_id = fid
    t.function_ids = []
    t.show()
    f = _vc_widget(ui, _FADER)
    if f is None:
        f = canvas._add_widget("VCSlider", QPoint(880, 250))
        f.setObjectName(_FADER)
    f.caption = "Modify-Stärke"
    f.resize(100, 230)
    f.mode = SliderMode.EFFECT_PARAM
    f.function_id = fid
    f.param_key = "modify_strength"
    f.value = 255
    f.show()
    for w in (t, f):
        w.update()
    ui.pump(0.4)
    if t._modify_arten() != ["add"]:
        raise SzenenFehler(f"Taste zeigt {t._modify_arten()} statt [add]")


def vc_weg(ui):
    canvas = _canvas(ui)
    for n in (_TASTE, _FADER):
        w = _vc_widget(ui, n)
        if w is not None:
            canvas._remove_widget(w)
    ui.pump(0.2)


def _vc_rechteck(ui, rand=16):
    t = rechteck(ui.win, _vc_widget(ui, _TASTE))
    f = rechteck(ui.win, _vc_widget(ui, _FADER))
    return t.united(f).adjusted(-rand, -rand, rand, rand)


def _b07(ui):
    alles_aus(ui)
    _modify_setzen(ui, MOD, "add", 100)
    vc_anlegen(ui)
    return bild(ui, kreise=[
        (rechteck(ui.win, _vc_widget(ui, _TASTE)), 1, "links"),
        (rechteck(ui.win, _vc_widget(ui, _FADER)), 2, "rechts"),
    ])


def funkeln_anlegen(ui):
    """Funkeln (Matrix Random/Sparkle, Stil Dimmer) auf denselben Lampen wie
    das Modify-Lauflicht."""
    from src.core.engine.rgb_matrix import MatrixStyle, RgbAlgorithm
    try:
        return funktion(FUNKELN)
    except SzenenFehler:
        pass
    vorbild = funktion(MOD)
    f = _fm().new_rgb_matrix(FUNKELN)
    f.cols, f.rows = vorbild.cols, vorbild.rows
    f.fixture_grid = list(vorbild.fixture_grid)
    f.head_grid = list(vorbild.head_grid)
    f.source_group = vorbild.source_group
    f.style = MatrixStyle.DIMMER
    f.algorithm = RgbAlgorithm.RANDOM
    # Jede Lampe zufällig 30–100 %, mit Helligkeit 50 % -> 15–50 %: ein
    # ruhiges Funkeln, über dem der Läufer (100 %) klar zu sehen ist.
    f.params = {"mode": "dimmer", "count": 8, "rate": 1.0}
    f.intensity = 0.5
    f.tempo_bus_id = ""
    f.matrix_speed = 2.0
    return f


def _taste_klick(ui):
    t = _vc_widget(ui, _TASTE)
    t._pressed = True
    t._trigger(True)
    t._pressed = False
    t._trigger(False)
    t.update()


def _gif_vorher(ui):
    alles_aus(ui)
    _modify_setzen(ui, MOD, "add", 100)
    vc_anlegen(ui)
    fk = funkeln_anlegen(ui)
    # Farbe weiss aus dem Programmer, den Dimmer treibt das Funkeln.
    for attr in ("color_r", "color_g", "color_b"):
        ui.wert(pars(ui), attr, 255)
    ui.waehle([])
    _fm().start(fk.id)
    ticks(ui, 20)
    ui.info["doku_dm_uhr"] = 0


def _gif_schritt(klick, an):
    def schritt(ui):
        if klick:
            _taste_klick(ui)
        ticks(ui, 22)
        werte = prozent(ui)
        beleg(f"GIF Taste {'an' if an else 'aus'}: Dimmer % {werte}")
        if an and werte.count(100) != 2:
            raise SzenenFehler("Taste an: Läufer (2 × 100 %) fehlt")
        if not an and (100 in werte or max(werte) == 0):
            raise SzenenFehler("Taste aus: kein ruhiges Funkeln")
    return schritt


def _gif_bild(an):
    def bauen(ui):
        from PySide6.QtCore import QPoint, QRect
        from PySide6.QtGui import QColor, QPainter, QPixmap
        from PySide6.QtWidgets import QLabel
        from anleitungsbilder.szenen_erste_schritte import kreise_malen
        ui.sektion("Virtual Console")
        _vc_widget(ui, _TASTE).update()
        ui.pump(0.2)
        vr = _vc_rechteck(ui)
        vc = ui.win.grab(vr)
        taste = rechteck(ui.win, _vc_widget(ui, _TASTE)).translated(-vr.topLeft())
        reihe = reihen_bild([("Taste aus: nur das Funkeln" if not an
                              else "Taste an: Funkeln + Modify-Lauflicht (Addieren)",
                              reihe_aufnehmen(ui))]).pixmap()
        b = max(vc.width(), reihe.width())
        pix = QPixmap(b, vc.height() + reihe.height() + 8)
        pix.fill(QColor("#0d1117"))
        p = QPainter(pix)
        p.drawPixmap((b - vc.width()) // 2, 0, vc)
        p.drawPixmap(0, vc.height() + 8, reihe)
        p.end()
        kreise_malen(pix, [(taste.translated((b - vc.width()) // 2, 0), 1, "links")])
        lab = QLabel()
        lab.setFixedSize(pix.size())
        lab.setPixmap(pix)
        return lab
    return bauen


def _gif_nachher(ui):
    alles_aus(ui)


# ── 09/10: Schrittweite, Zweierblöcke ──────────────────────────────────────

def _b09(ui):
    alles_aus(ui)
    m = matrix_zeigen(ui, MOD)
    lauf_felder(ui, breite=2, anzahl=1, schritt=0, tempo=1.0)
    speichern(ui)
    _scroll_zu(ui, m._param_box, rand=30)
    body = m._editor_body
    if m._runner_step_spin.text().strip() != "wie Breite":
        raise SzenenFehler(f"Schrittweite zeigt {m._runner_step_spin.text()!r}")
    return bild(ui, kreise=[
        (_zeile(ui, body, "Schrittweite:"), 1, "rechts"),
        (_zeile(ui, body, "Läufer-Anzahl:").united(_zeile(ui, body, "Läufer-Breite:")),
         2, "rechts"),
        (_zeile(ui, body, "Schweif (%):"), 3, "rechts"),
    ])


def _bloecke_vorher(ui):
    alles_aus(ui)
    programmer_start(ui)
    _modify_setzen(ui, MOD, "add", 100)
    untergrund(ui)
    _fm().start(funktion(MOD).id)


def _block(n):
    lampen = [2 * n - 1, 2 * n]

    def schritt(ui):
        bis_laeufer(ui, lampen)
        soll = [100 if i + 1 in lampen else 40 for i in range(8)]
        erwarte(prozent(ui), soll, f"Zweierblock Schritt {n} (Dimmer %)")

    def bauen(ui):
        return reihen_bild([(f"Schritt {n}: Lampe {lampen[0]} + {lampen[1]}",
                             reihe_aufnehmen(ui))])
    return schritt, bauen


def _block_frames():
    aus = []
    for n in (1, 2, 3, 4):
        schritt, bauen = _block(n)
        aus.append(Frame(dauer_s=0.9, schritt=schritt, dialog=bauen, warte_s=0.1))
    return aus


# ── 11–13: Farbe ────────────────────────────────────────────────────────────

def _body_ausschnitt(ui, oben_w, unten_w, kreise, rand=12, links=46):
    """Ausschnitt des ganzen Editor-Inhalts (auch was im Scrollbereich nicht
    zu sehen ist) von ``oben_w`` bis ``unten_w``; ``kreise``: (QRect in
    Body-Koordinaten, nr, lage). Links bleibt ein Rand fuer die Kreise."""
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtGui import QColor, QPainter, QPixmap
    from PySide6.QtWidgets import QLabel
    from anleitungsbilder import marker
    from anleitungsbilder.szenen_erste_schritte import kreise_malen
    body = _mx(ui)._editor_body
    ui.pump(0.2)
    y0 = max(0, oben_w.mapTo(body, QPoint(0, 0)).y() - rand)
    y1 = unten_w.mapTo(body, QPoint(0, unten_w.height())).y() + rand
    bereich = QRect(0, y0, body.width(), y1 - y0)
    inhalt = body.grab(bereich)
    pix = QPixmap(inhalt.width() + links, inhalt.height())
    pix.fill(QColor("#0d1117"))
    p = QPainter(pix)
    p.drawPixmap(links, 0, inhalt)
    p.end()
    v = QPoint(links, -y0)
    frei = marker.hindernisse(body, versatz=v)
    k = [(QRect(r).translated(v), nr, lage) for r, nr, lage in kreise]
    kreise_malen(pix, k, frei)
    lab = QLabel()
    lab.setFixedSize(pix.size())
    lab.setPixmap(pix)
    return lab


def _formzeile(ui, form_w, feld_w):
    """Rechteck Beschriftung + Feld in Body-Koordinaten."""
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtWidgets import QFormLayout
    body = _mx(ui)._editor_body
    r = QRect(feld_w.mapTo(body, QPoint(0, 0)), feld_w.size())
    for form in body.findChildren(QFormLayout):
        lab = form.labelForField(feld_w)
        if lab is not None and lab.isVisible():
            r = r.united(QRect(lab.mapTo(body, QPoint(0, 0)), lab.size()))
            break
    return r.adjusted(-3, -3, 3, 3)


def _b11(ui):
    alles_aus(ui)
    m = matrix_neu(ui, MOD_RGB, stil="RGB")
    lauf_felder(ui)
    m._cb_modify.setChecked(True)
    ui.pump(0.3)
    speichern(ui)
    hinweis = m._modify_hint.text()
    beleg(f"Hinweis Farb-Modify: {hinweis}")
    if "Dimmer" not in hinweis:
        raise SzenenFehler("Hinweis zum Dimmer fehlt in der Gruppe Modify")
    return _body_ausschnitt(ui, m._style_combo, m._grp_modify, [
        (_formzeile(ui, None, m._style_combo), 1, "rechts"),
        (QRectAus(ui, m._cb_modify), 2, "rechts"),
        (_formzeile(ui, None, m._modify_mode_combo), 3, "links"),
        (QRectAus(ui, m._modify_hint), 4, "links"),
    ])


def QRectAus(ui, w):
    from PySide6.QtCore import QPoint, QRect
    body = _mx(ui)._editor_body
    return QRect(w.mapTo(body, QPoint(0, 0)), w.size()).adjusted(-3, -3, 3, 3)


def _farbe_reihen(ui):
    alles_aus(ui)
    f = funktion(MOD_RGB)
    f.modify_mode, f.modify_strength = "add", 100
    # Modify allein: Dimmer voll, Farbe 0 darunter.
    untergrund(ui, wert=255, farbe=(0, 0, 0))
    _fm().start(f.id)
    bis_laeufer(ui, [3, 7], attr="color_r")
    erwarte([dmx(ui, x, "color_r") for x in pars(ui)],
            [0, 0, 255, 0, 0, 0, 255, 0], "Rot-Modify allein (Rot)")
    allein = reihe_aufnehmen(ui)
    untergrund(ui, wert=255, farbe=(0, 0, 255))
    ticks(ui, 1)
    erwarte([(dmx(ui, x, "color_r"), dmx(ui, x, "color_b")) for x in pars(ui)],
            [(0, 255)] * 2 + [(255, 255)] + [(0, 255)] * 3 + [(255, 255)] + [(0, 255)],
            "Addieren auf Blau (Rot, Blau)")
    ergebnis = reihe_aufnehmen(ui)
    _fm().stop(f.id)
    ticks(ui, 2)
    unten = reihe_aufnehmen(ui)
    return reihen_bild([("Darunter: Blau (Programmer)", unten),
                        ("Modify Rot allein (darunter keine Farbe)", allein),
                        ("Ergebnis: Addieren — unter dem Läufer Magenta", ergebnis)])


def _b13(ui):
    """Stil RGBW, Abziehen, nur Weiß: Gruppe Modify + Vorschau nebeneinander."""
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtGui import QColor, QPainter, QPixmap
    from PySide6.QtWidgets import QLabel
    from anleitungsbilder.szenen_erste_schritte import kreise_malen
    alles_aus(ui)
    m = matrix_zeigen(ui, MOD_RGB)
    _combo_text(m._style_combo, "RGBW")
    ui.pump(0.2)
    _combo_daten(m._modify_mode_combo, "sub")
    m._modify_kanal_cbs["w"].setChecked(True)
    ui.pump(0.4)
    if m._cb_modify_standard.isChecked():
        raise SzenenFehler("„Kanäle der Modify-Farbe“ bleibt gesetzt")
    speichern(ui)
    f = funktion(MOD_RGB)
    beleg(f"Wirkt auf: {f.modify_channels} Art={f.modify_mode}")
    from anleitungsbilder import marker
    grp = m._grp_modify.grab()
    pv = m._preview
    # Die Vorschau laeuft mit eigener Uhr: warten, bis die Beschriftung oben
    # links frei steht (kein heller Läufer darunter).
    for _ in range(80):
        pv.update()
        ui.pump(0.05)
        vor = pv.grab()
        img = vor.toImage()
        if all(QColor(img.pixel(x, 40)).lightness() < 60 for x in range(6, 90, 6)):
            break
    else:
        raise SzenenFehler("Vorschau-Beschriftung bleibt verdeckt")
    luecke, rand, rechts = 40, 12, 50
    pix = QPixmap(rand + vor.width() + luecke + grp.width() + rechts,
                  max(vor.height() + 50, grp.height()) + 2 * rand)
    pix.fill(QColor("#0d1117"))
    p = QPainter(pix)
    p.drawPixmap(rand, rand, vor)
    gx = rand + vor.width() + luecke
    p.drawPixmap(gx, rand, grp)
    p.end()

    def im_grp(w):
        return QRect(w.mapTo(m._grp_modify, QPoint(0, 0)), w.size()).translated(
            gx, rand).adjusted(-3, -3, 3, 3)
    frei = marker.hindernisse(m._grp_modify, versatz=QPoint(gx, rand))
    frei.append(QRect(rand, rand, vor.width(), vor.height()))
    kreise_malen(pix, [
        (im_grp(m._modify_mode_combo), 1, "rechts"),
        (im_grp(m._modify_kanal_cbs["w"]), 2, "unten"),
        (QRect(rand + 2, rand + 2, 110, 26), 3, "unten"),
    ], frei)
    lab = QLabel()
    lab.setFixedSize(pix.size())
    lab.setPixmap(pix)
    return lab


# ── 14: Chaser-Editor mit Modify-Schritt ────────────────────────────────────

CHASER = "Chaser mit Modify"


def _b14(ui):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QDialog
    from src.core.engine.chaser import ChaserStep
    alles_aus(ui)
    fm = _fm()
    try:
        ch = funktion(CHASER)
    except SzenenFehler:
        ch = fm.new_chaser(CHASER)
        ch.name = CHASER
        ch.steps = [ChaserStep(function_id=funktion("Alle PAR Rot").id),
                    ChaserStep(function_id=funktion(MOD).id),
                    ChaserStep(function_id=funktion("Alle PAR Blau").id)]
    programmer_start(ui)
    panel = _pv(ui)._snap_file_panel
    ergebnis = {}

    def _aufnehmen():
        dlg = QApplication.activeModalWidget()
        if not isinstance(dlg, QDialog):
            ergebnis["fehler"] = "Dialog „Bearbeiten“ ging nicht auf"
            return
        try:
            from src.ui.views.chaser_editor import ChaserEditor
            dlg.resize(900, 800)
            ui.pump(0.3)
            ed = dlg.findChild(ChaserEditor)
            tab = ed._table
            ed._editor_scroll.ensureWidgetVisible(ed._modify_hinweis, 0, 20)
            ui.pump(0.3)
            r = tab.visualItemRect(tab.item(1, 1))
            from PySide6.QtCore import QRect
            zeile = QRect(tab.viewport().mapTo(dlg, r.topLeft()), r.size())
            hinweis = ed._modify_hinweis
            if not hinweis.isVisible():
                ergebnis["fehler"] = "Hinweiszeile zum Modify-Schritt fehlt"
                return
            beleg(f"Chaser-Hinweis: {hinweis.text()}")
            ergebnis["bild"] = _dialog_bild(ui, dlg, [
                (zeile, 1, "rechts"),
                (rechteck(dlg, hinweis), 2, "oben"),
            ])
        except Exception as e:      # noqa: BLE001
            ergebnis["fehler"] = f"{type(e).__name__}: {e}"
        finally:
            dlg.accept()

    QTimer.singleShot(400, _aufnehmen)
    panel._edit_function(ch.id)
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


def _abraeumen(ui):
    alles_aus(ui)
    vc_weg(ui)
    fm = _fm()
    for name in (CHASER, FUNKELN, MOD_RGB, MOD):
        try:
            fm.remove(funktion(name).id)
        except SzenenFehler:
            pass
    ui.pump(0.2)


SZENEN = [
    Szene("03_modify_aus", sektion="Programmer", dialog=_b03,
          titel="Matrix-Editor, Stil Dimmer, Haken „Modify-Effekt“ noch aus"),
    Szene("04_modify_an", sektion="Programmer", dialog=_b04, nachher=_n04,
          titel="Haken „Modify-Effekt“ gesetzt: Gruppe Modify mit Betriebsart und Stärke"),
    Szene("05_lampen_addieren", sektion="Programmer", dialog=_lampen_addieren,
          nachher=_n_lampen,
          titel="Lampenreihe: Untergrund 40 % / Modify-Lauflicht allein / Ergebnis Addieren"),
    Szene("06_lampen_abziehen_abdunkeln", sektion="Programmer", dialog=_lampen_abziehen,
          nachher=_n_lampen,
          titel="Lampenreihe: Abziehen und Abdunkeln mit Stärke 50 %"),
    Szene("07_vc_taste_fader", sektion="Virtual Console", dialog=_b07,
          titel="Virtuelle Konsole: Taste für das Modify-Lauflicht (Zeichen +) und Fader Modify-Stärke"),
    Szene("08_taste_an_aus", sektion="Virtual Console", vorher=_gif_vorher,
          nachher=_gif_nachher,
          frames=[Frame(dauer_s=1.0, schritt=_gif_schritt(False, False), dialog=_gif_bild(False)),
                  Frame(dauer_s=1.0, schritt=_gif_schritt(False, False), dialog=_gif_bild(False)),
                  Frame(dauer_s=1.0, schritt=_gif_schritt(True, True), dialog=_gif_bild(True)),
                  Frame(dauer_s=1.0, schritt=_gif_schritt(False, True), dialog=_gif_bild(True)),
                  Frame(dauer_s=1.0, schritt=_gif_schritt(False, True), dialog=_gif_bild(True)),
                  Frame(dauer_s=1.0, schritt=_gif_schritt(True, False), dialog=_gif_bild(False))],
          titel="GIF: Modify-Taste an und aus über einem laufenden Funkeln"),
    Szene("09_schrittweite", sektion="Programmer", dialog=_b09,
          titel="Bewegung & Parameter: Schrittweite „wie Breite“, Läufer-Breite 2, Schweif 0 %"),
    Szene("10_zweierbloecke", sektion="Programmer", vorher=_bloecke_vorher,
          nachher=_n_lampen, frames=_block_frames(),
          titel="GIF: Modify-Lauflicht in Zweierblöcken über 40 %"),
    Szene("11_modify_rgb", sektion="Programmer", dialog=_b11,
          titel="Stil RGB mit Haken Modify-Effekt: Gruppe Modify mit dem Hinweis zum Dimmer"),
    Szene("12_farbe_lampen", sektion="Programmer", dialog=_farbe_reihen,
          nachher=_n_lampen,
          titel="Lampenreihe in Farbe: Blau / Modify Rot allein / Ergebnis Addieren"),
    Szene("13_wirkt_auf", sektion="Programmer", dialog=_b13,
          titel="Gruppe Modify: Wirkt auf nur Weiß, Abziehen; Vorschau „− nur Weiß“"),
    Szene("14_chaser_modify", sektion="Programmer", dialog=_b14, nachher=_abraeumen,
          titel="Chaser-Editor: Modify-Schritt gelb mit ⚠ und Hinweiszeile"),
]
