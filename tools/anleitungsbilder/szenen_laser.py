"""DOC-75: Bilder fuer die Laser-Anleitung — ``docs/anleitung_laser/img/``.

Neu erzeugen::

    venv/bin/python tools/anleitungsbilder.py laser

Die Doku-Demo-Show hat keinen Laser. Die Szenen patchen deshalb den
Laserworld EL-400RGB MK2 aus der LightOS-Bibliothek (``fixtures/bibliothek``,
in der Sandbox eingespielt) — sein Profil macht Laser-Angaben (Betriebsart,
Musterliste, Farbtabelle), der Laser-Reiter zeigt damit die neue Bedienung.
Fuer den Knopf „Scharf“ kommt im GIF ein zweiter Laser dazu, der ueber
Ether Dream angesteuert wuerde (Netzwerk-Adresse 192.0.2.10, ein
Dokumentations-Adressbereich). Die Sandbox startet keinen Ausgabe-Thread
(``LIGHTOS_NO_OUTPUT_THREAD``): nichts wird gesendet, kein Laser wird scharf.

Der NOT-AUS wird im GIF ueber den echten Knopf der Kopfleiste ausgeloest. Die
Rueckfrage zum Loesen (``laser_notaus.loesen_mit_rueckfrage``, modal) wird per
Timer aufgenommen und mit „Abbrechen“ geschlossen; geloest wird danach in der
Sandbox ueber ``AppState.laser_notaus_loesen``.

Die letzte Szene raeumt ab (Laser entpatchen, NOT-AUS geloest, Programmer
leer) — bei ``--alle`` sehen nachfolgende Anleitungen die Doku-Demo
unveraendert. Jede Szene stellt ihren Zustand selbst her.
"""
from __future__ import annotations

from anleitungsbilder.runner import Frame, Szene, SzenenFehler
from anleitungsbilder.szenen_erste_schritte import bild, kreise_malen, rechteck

ZIEL = "docs/anleitung_laser/img"

HERSTELLER = "Laserworld"
MODELL = "EL-400RGB MK2"
LABEL = "Laser 1"
ADRESSE = 121
NETZ_LABEL = "Netz-Laser"
NETZ_HOST = "192.0.2.10"           # RFC 5737, nur Doku


# ── Hilfen ──────────────────────────────────────────────────────────────────

def _pv(ui):
    return ui.win._programmer_view


def _lv(ui):
    lv = getattr(_pv(ui), "_embedded_laser", None)
    if lv is None:
        raise SzenenFehler("Laser-Reiter im Programmer fehlt")
    return lv


def _profil():
    from src.core.database import fixture_db as fdb
    for p in fdb.search_fixtures(MODELL):
        if p.name == MODELL and p.manufacturer and p.manufacturer.name == HERSTELLER:
            modi = fdb.get_modes(p.id)
            if modi:
                return p, modi[0]
    raise SzenenFehler(f"Profil '{HERSTELLER} — {MODELL}' fehlt in der "
                       "Sandbox-Bibliothek (fixtures/bibliothek nicht eingespielt?)")


def _fid(ui, label):
    for f in ui.state.get_patched_fixtures():
        if f.label == label:
            return f.fid
    return None


def _patchen(ui, label, *, netz: bool = False) -> int:
    """Laser patchen (einmal je Lauf); liefert die fid."""
    from src.core.database.models import PatchedFixture
    fid = _fid(ui, label)
    if fid is not None:
        return fid
    p, modus = _profil()
    fid = ui.state.next_fid()
    ui.state.add_fixture(PatchedFixture(
        fid=fid, label=label, fixture_profile_id=p.id, mode_name=modus.name,
        universe=1, address=ADRESSE + (20 if netz else 0),
        channel_count=modus.channel_count, manufacturer_name=HERSTELLER,
        fixture_name=MODELL, fixture_type=p.fixture_type,
        protocol="etherdream" if netz else "dmx",
        net_host=NETZ_HOST if netz else ""), undoable=False)
    ui.win._refresh_all_views()
    ui.pump(0.2)
    return fid


def _leeren(ui):
    ui.state.clear_programmer()
    ui.waehle([])
    pv = _pv(ui)
    pv._fixture_list.clearSelection()
    pv._group_list.clearSelection()
    pv._group_list.setCurrentRow(-1)
    ui.pump(0.1)


def _laser_reiter(ui, fids):
    """Laser waehlen (wie in der Geraeteliste) und den Reiter „Laser“ zeigen."""
    pv = _pv(ui)
    pv._select_fids(list(fids))
    ui.pump(0.3)
    tabs = pv._main_tabs
    for i in range(tabs.count()):
        if tabs.tabText(i) == "Laser" and tabs.isTabVisible(i):
            tabs.setCurrentIndex(i)
            ui.pump(0.4)
            return _lv(ui)
    raise SzenenFehler("Reiter „Laser“ erscheint nicht — Laser nicht erkannt?")


def _plan(lv):
    plan = getattr(lv, "_plan", None)
    if plan is None or not plan.neu:
        raise SzenenFehler("Laser-Reiter zeigt die bisherige Bedienung — "
                           "Profil ohne Laser-Angaben?")
    return plan


def _segment(lv, art: str):
    """Segment der Betriebsart ``art`` (statisch/dynamisch/musik/auto/aus)."""
    _plan(lv)
    for seg in lv._umschalter.segmente:
        if seg.art == art and seg.isVisible():
            return seg
    raise SzenenFehler(f"Betriebsart '{art}' fehlt im Umschalter "
                       f"({[s.art for s in lv._umschalter.segmente]})")


def _kachel(lv, nr: int):
    kacheln = [k for k in lv._galerie.findChildren(_kachel_klasse()) if k.isVisible()]
    if len(kacheln) <= nr:
        raise SzenenFehler(f"Musterkachel {nr} fehlt ({len(kacheln)} da)")
    kacheln.sort(key=lambda k: (k.mapTo(lv, k.rect().topLeft()).y(),
                                k.mapTo(lv, k.rect().topLeft()).x()))
    return kacheln[nr]


def _kachel_klasse():
    from src.ui.widgets.laser_tab_bausteine import MusterKachel
    return MusterKachel


def _klick(ui, w):
    """Echter Mausklick auf ``w`` (Mitte)."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    QTest.mouseClick(w, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     w.rect().center())
    ui.pump(0.3)


def _grundstellung(ui, art="statisch", muster=0, farbe_nr=None):
    """Laser 1 waehlen, Betriebsart + Muster + Farbe ueber die Bausteine."""
    _leeren(ui)
    fid = _patchen(ui, LABEL)
    lv = _laser_reiter(ui, [fid])
    _klick(ui, _segment(lv, art))
    if muster is not None and art in ("statisch", "dynamisch"):
        _klick(ui, _kachel(lv, muster))
    if farbe_nr is not None:
        felder = [f for f in lv._farbfelder.findChildren(_farbfeld_klasse())
                  if f.isVisible()]
        if len(felder) <= farbe_nr:
            raise SzenenFehler(f"Farbfeld {farbe_nr} fehlt ({len(felder)} da)")
        _klick(ui, felder[farbe_nr])
    ui.pump(0.3)
    return lv


def _farbfeld_klasse():
    from src.ui.widgets.laser_tab_bausteine import FarbFeld
    return FarbFeld


# ── 1: Laser-Reiter im Ueberblick ──────────────────────────────────────────

def _bild_ueberblick(ui):
    lv = _grundstellung(ui, "statisch", muster=0, farbe_nr=3)
    w = ui.win
    return bild(ui, kreise=[
        (rechteck(w, lv._dmx_safety_box), 1, "unten"),
        (rechteck(w, lv._umschalter), 2, "rechts"),
        (rechteck(w, lv._lage_box), 3, "unten"),
        (rechteck(w, lv._btn_mitte), 4, "rechts"),
        (rechteck(w, lv._galerie), 5, "rechts"),
        (rechteck(w, lv._farbfelder), 6, "rechts"),
    ])


# ── Ausschnitt eines zusammengesetzten Bildes ──────────────────────────────

def _zuschnitt(flaeche, rect):
    """``bild()``-Flaeche (QLabel) auf ``rect`` (Fensterkoordinaten) schneiden."""
    from PySide6.QtWidgets import QLabel
    pix = flaeche.pixmap().copy(rect)
    aus = QLabel()
    aus.setFixedSize(pix.width(), pix.height())
    aus.setPixmap(pix)
    return aus


def _bausteine_rechteck(ui, lv, *, oben, unten_widget, rand=10):
    """Bereich von ``oben`` (Widget) bis Unterkante ``unten_widget`` ueber die
    Breite des Laser-Reiters."""
    from PySide6.QtCore import QRect
    w = ui.win
    r_lv = rechteck(w, lv)
    top = rechteck(w, oben).top() - 26          # mit Ueberschrift „Betriebsart“
    bottom = rechteck(w, unten_widget).bottom() + rand
    return QRect(r_lv.left() - 4, top, r_lv.width() + 12, bottom - top)


# ── 2: Statische Muster, angeklickte Kachel (Nahaufnahme) ───────────────────

def _bild_muster(ui):
    lv = _grundstellung(ui, "statisch", muster=6, farbe_nr=5)
    w = ui.win
    kachel = _kachel(lv, 6)
    if not kachel.gewaehlt():
        raise SzenenFehler("Angeklickte Musterkachel ist nicht gewählt")
    flaeche = bild(ui, kreise=[
        (rechteck(w, _segment(lv, "statisch")), 1, "unten"),
        (rechteck(w, kachel), 2, "unten"),
        (rechteck(w, lv._lage_feld), 3, "rechts"),
    ])
    return _zuschnitt(flaeche, _bausteine_rechteck(
        ui, lv, oben=lv._umschalter, unten_widget=lv._lage_box))


# ── 3: Musik/Auto: gelber Hinweis neben „Betriebsart“ ───────────────────────

def _bild_musik(ui):
    lv = _grundstellung(ui, "musik", muster=None)
    w = ui.win
    hinweis = lv._lbl_gesperrt
    if not hinweis.isVisible():
        raise SzenenFehler("Gelber Hinweis neben „Betriebsart“ fehlt bei Musik")
    if lv._galerie.isEnabled():
        raise SzenenFehler("Muster sind bei Musik nicht ausgegraut")
    flaeche = bild(ui, kreise=[
        (rechteck(w, _segment(lv, "musik")), 1, "unten"),
        (rechteck(w, hinweis), 2, "links"),
        (rechteck(w, lv._galerie), 3, "rechts"),
    ])
    return _zuschnitt(flaeche, _bausteine_rechteck(
        ui, lv, oben=lv._umschalter, unten_widget=lv._galerie))


# ── 4: GIF NOT-AUS ausloesen, Scharf verweigert, loesen mit Rueckfrage ─────

def _kopf_notaus(ui):
    return ui.win._btn_laser_notaus


def _gif_vorher(ui):
    """Laser 1 (DMX) + Netz-Laser (Ether Dream) gewaehlt, Reiter Laser."""
    _leeren(ui)
    f1 = _patchen(ui, LABEL)
    f2 = _patchen(ui, NETZ_LABEL, netz=True)
    lv = _laser_reiter(ui, [f1, f2])
    _klick(ui, _segment(lv, "statisch"))
    if not lv._safety_box.isVisible():
        raise SzenenFehler("Bereich „Laser-Ausgabe (Netzwerk)“ fehlt")
    if ui.state.laser_estop_active:
        raise SzenenFehler("NOT-AUS steht schon vor dem GIF")


def _ausloesen(ui):
    """Klick auf LASER NOT-AUS in der Kopfleiste (echter Knopf)."""
    _kopf_notaus(ui).click()
    ui.pump(0.6)
    if not ui.state.laser_estop_active:
        raise SzenenFehler("Klick auf LASER NOT-AUS hat nicht ausgelöst")
    if "AKTIV" not in _kopf_notaus(ui).text():
        raise SzenenFehler(f"Kopfleiste zeigt {_kopf_notaus(ui).text()!r}")


def _scharf_klicken(ui):
    """Klick auf „Scharf“ — wird bei stehendem NOT-AUS verweigert."""
    lv = _lv(ui)
    lv._btn_arm.click()
    ui.pump(0.3)
    if lv._btn_arm.isChecked():
        raise SzenenFehler("„Scharf“ wurde trotz NOT-AUS angenommen")
    lo = getattr(ui.state, "_laser_output", None)
    if lo is not None and lo.armed:
        raise SzenenFehler("Laser-Ausgang ist scharf")


def _gif_bild(kreise_fn, *, tooltip=False):
    def bauen(ui):
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QPainter
        from PySide6.QtWidgets import QLabel
        flaeche = bild(ui, kreise=kreise_fn(ui))
        if tooltip:
            # Offscreen gibt es kein Tooltip-Fenster im Bild: den echten
            # Tooltip-Text des Knopfs als Tooltip-Kaestchen dazumalen.
            btn = _lv(ui)._btn_arm
            text = btn.toolTip()
            if "NOT-AUS aktiv" not in text:
                raise SzenenFehler(f"Tooltip von „Scharf“: {text!r}")
            tip = QLabel(text)
            tip.setStyleSheet("QLabel{background:#ffffdc;color:#000;"
                              "border:1px solid #767676;padding:4px 6px;}")
            tip.adjustSize()
            pix = flaeche.pixmap()
            r = rechteck(ui.win, btn)
            p = QPainter(pix)
            p.drawPixmap(QPoint(r.center().x() - 60, r.bottom() + 6), tip.grab())
            p.end()
            flaeche.setPixmap(pix)
        return flaeche
    return bauen


def _k_vorher(ui):
    return [(rechteck(ui.win, _kopf_notaus(ui)), 1, "unten")]


def _k_ausgeloest(ui):
    lv = _lv(ui)
    return [(rechteck(ui.win, _kopf_notaus(ui)), 1, "unten"),
            (rechteck(ui.win, lv._lbl_dmx_estop), 2, "unten")]


def _k_scharf(ui):
    return [(rechteck(ui.win, _lv(ui)._btn_arm), 3, "links")]


def _rueckfrage_bild(ui):
    """Erneuter Klick auf LASER NOT-AUS AKTIV -> Rueckfrage (modal). Per Timer
    aufnehmen und mit „Abbrechen“ schliessen — die Szene uebernimmt nie etwas
    in einem Dialog. Geloest wird erst im naechsten Frame in der Sandbox
    (``_loesen``), mit derselben Zustandsaenderung wie „NOT-AUS lösen“."""
    from PySide6.QtCore import QPoint, QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox
    from src.ui import laser_notaus
    ui.pump(1.2)                      # Sperre nach dem Ausloesen (1 s) abwarten
    ergebnis = {}

    def _aufnehmen():
        dlg = QApplication.activeModalWidget()
        if not isinstance(dlg, QMessageBox):
            for w in QApplication.topLevelWidgets():
                if isinstance(w, QMessageBox) and w.isVisible():
                    dlg = w
        if not isinstance(dlg, QMessageBox):
            ergebnis["fehler"] = "Rückfrage „Laser-NOT-AUS lösen?“ ging nicht auf"
            return
        loesen = dlg.button(QMessageBox.StandardButton.Yes)
        abbr = dlg.button(QMessageBox.StandardButton.Cancel)
        try:
            if dlg.windowTitle() != laser_notaus.TITEL:
                raise SzenenFehler(f"Falsche Rückfrage: {dlg.windowTitle()!r}")
            if loesen is None or abbr is None:
                raise SzenenFehler("Rückfrage ohne „NOT-AUS lösen“/„Abbrechen“")
            if dlg.defaultButton() is not abbr:
                raise SzenenFehler("Vorgabe der Rückfrage ist nicht „Abbrechen“")
            dlg.adjustSize()
            ui.pump(0.2)
            ergebnis["bild"] = bild(ui, dlg, [
                (rechteck(dlg, loesen), 4, "unten"),
            ], pos=QPoint(640, 150), titel=dlg.windowTitle(),
                fenster_kreise=[(rechteck(ui.win, _kopf_notaus(ui)), 1, "unten")])
        except SzenenFehler as e:
            ergebnis["fehler"] = str(e)
        abbr.click() if abbr is not None else dlg.reject()

    QTimer.singleShot(300, _aufnehmen)
    _kopf_notaus(ui).click()
    ui.pump(0.3)
    if "fehler" in ergebnis:
        raise SzenenFehler(ergebnis["fehler"])
    if "bild" not in ergebnis:
        raise SzenenFehler("Rückfrage wurde nicht aufgenommen")
    if not ui.state.laser_estop_active:
        raise SzenenFehler("„Abbrechen“ hat den NOT-AUS gelöst")
    return ergebnis["bild"]


def _loesen(ui):
    """Sandbox: loesen wie „NOT-AUS lösen“ (``laser_notaus.loesen_mit_rueckfrage``
    ruft bei Ja genau ``state.laser_notaus_loesen()``), danach pruefen."""
    ui.state.laser_notaus_loesen()
    ui.pump(0.6)
    if ui.state.laser_estop_active:
        raise SzenenFehler("NOT-AUS steht nach dem Lösen noch")


def _k_geloest(ui):
    lv = _lv(ui)
    return [(rechteck(ui.win, _kopf_notaus(ui)), 1, "unten"),
            (rechteck(ui.win, lv._lbl_dmx_estop), 2, "unten")]


def notaus_aufraeumen(ui):
    """NOT-AUS sicher geloest, rote Statuszeile weg."""
    if getattr(ui.state, "laser_estop_active", False):
        ui.state.laser_notaus_loesen()
    try:
        ui.win.statusBar().clearMessage()
        ui.win._reset_statusbar_style()
    except Exception:
        pass
    ui.pump(0.2)


def _abbauen(ui):
    """Laser entpatchen, NOT-AUS geloest, Programmer leer, Reiter Attribute."""
    notaus_aufraeumen(ui)
    _leeren(ui)
    for label in (LABEL, NETZ_LABEL):
        fid = _fid(ui, label)
        if fid is not None:
            ui.state.remove_fixture(fid, undoable=False)
    ui.win._refresh_all_views()
    _pv(ui)._main_tabs.setCurrentIndex(0)
    ui.pump(0.3)
    if any(f.label in (LABEL, NETZ_LABEL) for f in ui.state.get_patched_fixtures()):
        raise SzenenFehler("Laser liess sich nicht entpatchen")


# GIF-Ausschnitt: volle Breite (der lange NOT-AUS-Text verschiebt das Layout),
# oben bis unter die Sicherheitsleiste.
_GIF_ZUSCHNITT = (0, 0, 1600, 456)


SZENEN = [
    Szene("01_laser_reiter", sektion="Programmer", unterreiter="Attribute",
          dialog=_bild_ueberblick,
          titel="Laser-Reiter: Sicherheitsleiste, Betriebsart, Vorschau, Muster, Farbe"),
    Szene("02_statische_muster", sektion="Programmer", unterreiter="Attribute",
          dialog=_bild_muster,
          titel="Statische Muster: Musterkachel angeklickt, Vorschau folgt"),
    Szene("03_musik_hinweis", sektion="Programmer", unterreiter="Attribute",
          dialog=_bild_musik,
          titel="Betriebsart Musik: gelber Hinweis, Muster/Lage/Farbe ausgegraut"),
    Szene("04_notaus_ablauf", sektion="Programmer", unterreiter="Attribute",
          vorher=_gif_vorher, nachher=_abbauen,
          gif_zuschnitt=_GIF_ZUSCHNITT, gif_breite=1280,
          frames=[
              Frame(dauer_s=1.6, dialog=_gif_bild(_k_vorher)),
              Frame(dauer_s=2.2, schritt=_ausloesen,
                    dialog=_gif_bild(_k_ausgeloest)),
              Frame(dauer_s=2.6, schritt=_scharf_klicken,
                    dialog=_gif_bild(lambda ui: _k_ausgeloest(ui) + _k_scharf(ui),
                                     tooltip=True)),
              Frame(dauer_s=3.0, dialog=_rueckfrage_bild),
              Frame(dauer_s=2.0, schritt=_loesen,
                    dialog=_gif_bild(_k_geloest)),
          ],
          titel="GIF: LASER NOT-AUS auslösen, „Scharf“ verweigert, lösen mit Rückfrage"),
]
