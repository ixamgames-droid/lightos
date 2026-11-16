"""UI-136 (2): Halten + Antippen so, wie echte Finger ankommen.

Finger-Probe am Linux- und am Windows-Touchscreen: Finger auf „Rot" halten,
„Gruen" antippen — nichts. Ursache (Probe mit Beruehrungen an das FENSTER, die
Qt selbst den getroffenen Kind-Widgets zustellt): ein Mensch haelt laenger als
``LANG_MENUE_S`` (0,6 s), bevor er den zweiten Finger setzt. Dann ist schon
das Lang-Druck-Menue offen, es liegt ueber dem gehaltenen Widget (und meist
auch ueber dem Nachbarn), und ``_halten_antippen`` brach wegen des offenen
Pop-ups ab. Jetzt schliesst der zweite Finger dieses Menue (bedienen kann er es
ohnehin nicht — Qt macht nur aus dem ersten Finger eine Maus) und das Halten
beginnt. Dazu darf der gehaltene Finger bis zur doppelten Touch-Schwelle
zittern.

Alle Beruehrungen gehen an das Fenster (``QTest.touchEvent`` mit dem
``QWindow``), mit 3–6 px Zittern, zweiter Finger auf einem ANDEREN Kind-Widget.
"""
from __future__ import annotations

import os
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QPoint, QTimer                            # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu, QScrollArea       # noqa: E402

from src.ui import gesten_prefs                                      # noqa: E402
from src.ui import ziehen_scrollen as zs                             # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

_ZITTERN = [QPoint(3, -4), QPoint(-5, 3), QPoint(6, -2), QPoint(-3, 5), QPoint(4, 4)]


@pytest.fixture(autouse=True)
def _aufraeumen():
    f = zs.einrichten(_app)
    f.aktiv = True
    f.gesten = gesten_prefs.GestenSchalter()
    yield
    p = QApplication.activePopupWidget()
    if p is not None:
        p.close()
    f.gesten = gesten_prefs.GestenSchalter()
    f._halten = None
    f._wisch = None
    f._geste = None
    destroy_all_top_level_widgets(_app)


def _filter():
    return zs.einrichten(_app)


def _warte_bis(bedingung, s: float = 4.0) -> bool:
    ende = time.monotonic() + s
    while time.monotonic() < ende:
        QApplication.processEvents()
        if bedingung():
            return True
        time.sleep(0.01)
    return bedingung()


class _Finger:
    """Beruehrungen an das Fenster (Qt stellt sie den Kindern selbst zu)."""

    def __init__(self, oben):
        self.oben = oben
        self.fenster = oben.windowHandle()
        self.i = 0

    def lage(self, w, p: QPoint | None = None) -> QPoint:
        return w.mapTo(self.oben, w.rect().center() if p is None else p)

    def zitter(self) -> QPoint:
        self.i += 1
        return _ZITTERN[self.i % len(_ZITTERN)]

    def druck(self, h: QPoint) -> None:
        hints = QApplication.styleHints()
        alt = hints.mouseDoubleClickInterval()
        hints.setMouseDoubleClickInterval(1)
        try:
            QTest.touchEvent(self.fenster, _DEV).press(0, h).commit()
            QApplication.processEvents()
        finally:
            hints.setMouseDoubleClickInterval(alt)

    def halten(self, h: QPoint, s: float) -> None:
        """Finger 0 liegt ``s`` Sekunden und zittert dabei 3–6 px."""
        ende = time.monotonic() + s
        while time.monotonic() < ende:
            QTest.touchEvent(self.fenster, _DEV).move(0, h + self.zitter()).commit()
            QApplication.processEvents()
            time.sleep(0.03)

    def tippen(self, h: QPoint, t: QPoint, pid: int = 1) -> None:
        QTest.touchEvent(self.fenster, _DEV).move(0, h + self.zitter()) \
            .press(pid, t + self.zitter()).commit()
        QApplication.processEvents()
        QTest.touchEvent(self.fenster, _DEV).move(0, h + self.zitter()) \
            .move(pid, t + self.zitter()).commit()
        QApplication.processEvents()
        QTest.touchEvent(self.fenster, _DEV).move(0, h + self.zitter()) \
            .release(pid, t + self.zitter()).commit()
        QApplication.processEvents()

    def los(self, h: QPoint) -> None:
        QTest.touchEvent(self.fenster, _DEV).release(0, h + self.zitter()).commit()
        QApplication.processEvents()


# ── VC im Bearbeiten-Modus ───────────────────────────────────────────────────

@pytest.fixture
def vc():
    from src.ui.views.virtual_console_view import GrowingScrollArea
    from src.ui.virtualconsole.vc_button import ButtonAction
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    canvas = VCCanvas()
    knoepfe = []
    for x, name in ((20, "Rot"), (180, "Gruen"), (340, "Blau")):
        b = canvas._add_widget("VCButton", QPoint(x, 20))
        b.resize(120, 90)
        b.caption = name
        b.action = ButtonAction.FLASH
        b._trigger = lambda an: None
        knoepfe.append(b)
    fr = canvas._add_widget("VCFrame", QPoint(20, 200))
    fr.resize(360, 220)
    kind = canvas._add_widget("VCButton", QPoint(0, 0))
    fr.add_child_to_page(kind, 0)
    kind.move(40, 60)
    kind.resize(120, 90)
    kind.caption = "Im Kasten"
    area = GrowingScrollArea()
    area.setWidget(canvas)
    area.resize(1300, 900)
    area.show()
    QTest.qWaitForWindowExposed(area)
    canvas.set_edit_mode(True)
    canvas._undo_stack.clear()
    QApplication.processEvents()
    yield SimpleNamespace(canvas=canvas, b=knoepfe, kind=kind, fr=fr, area=area,
                          f=_Finger(area))


def test_vc_halten_auf_rot_antippen_gruen_mit_zittern(vc):
    v = vc
    lagen = [QPoint(w.pos()) for w in v.b]
    h, t = v.f.lage(v.b[0]), v.f.lage(v.b[1])
    v.f.druck(h)
    v.f.halten(h, zs.HALTEN_MIN_S + 0.1)
    v.f.tippen(h, t)
    assert _filter().halten_laeuft
    v.f.los(h)
    assert v.canvas.ausgewaehlte() == v.b[:2]
    assert [QPoint(w.pos()) for w in v.b] == lagen, "Zittern verschiebt nichts"
    assert not _filter().halten_laeuft


def test_vc_kasten_kind_und_flaeche(vc):
    """Gehalten im Kasten, angetippt auf der Flaeche — und umgekehrt."""
    v = vc
    h, t = v.f.lage(v.kind), v.f.lage(v.b[2])
    v.f.druck(h)
    v.f.halten(h, zs.HALTEN_MIN_S + 0.1)
    v.f.tippen(h, t)
    v.f.los(h)
    assert set(map(id, v.canvas.ausgewaehlte())) == {id(v.kind), id(v.b[2])}
    v.canvas.auswahl_aufheben()
    h, t = v.f.lage(v.b[1]), v.f.lage(v.kind)
    v.f.druck(h)
    v.f.halten(h, zs.HALTEN_MIN_S + 0.1)
    v.f.tippen(h, t)
    v.f.los(h)
    assert set(map(id, v.canvas.ausgewaehlte())) == {id(v.kind), id(v.b[1])}


def test_vc_lang_gehalten_menue_offen_zweiter_finger_schliesst_es(vc):
    """Der eigentliche Fehler: nach 0,6 s ist das Lang-Druck-Menue offen."""
    v = vc
    h, t = v.f.lage(v.b[0]), v.f.lage(v.b[1])
    ablauf = {"menue": None, "fertig": False}

    def im_menue():
        pop = QApplication.activePopupWidget()
        if pop is None:
            QTimer.singleShot(20, im_menue)
            return
        ablauf["menue"] = pop
        v.f.tippen(h, t)
        ablauf["halten"] = _filter().halten_laeuft
        ablauf["popup_danach"] = QApplication.activePopupWidget()
        if ablauf["popup_danach"] is not None:
            ablauf["popup_danach"].close()     # roter Lauf haengt nicht im Menue
        ablauf["fertig"] = True

    v.f.druck(h)
    QTimer.singleShot(20, im_menue)
    assert _warte_bis(lambda: ablauf["fertig"], 5.0)
    assert isinstance(ablauf["menue"], QMenu)
    assert ablauf["popup_danach"] is None, "Menue geschlossen"
    assert ablauf["halten"]
    v.f.los(h)
    assert v.canvas.ausgewaehlte() == v.b[:2]


def test_vc_lang_gehalten_ohne_zweiten_finger_bleibt_menue(vc):
    """Ohne zweiten Finger zeigt langes Druecken weiter das Menue."""
    v = vc
    h = v.f.lage(v.b[0])
    gesehen = {}

    def schauen():
        pop = QApplication.activePopupWidget()
        if pop is None:
            QTimer.singleShot(20, schauen)
            return
        gesehen["menue"] = pop
        pop.close()

    v.f.druck(h)
    QTimer.singleShot(20, schauen)
    assert _warte_bis(lambda: "menue" in gesehen, 5.0)
    v.f.los(h)
    assert not _filter().halten_laeuft


def test_vc_weit_gerutschter_finger_ist_kein_halten(vc):
    v = vc
    h, t = v.f.lage(v.b[0]), v.f.lage(v.b[1])
    v.f.druck(h)
    weit = h + QPoint(zs.ZiehenScrollen._schwelle() * 2 + 4, 0)
    QTest.touchEvent(v.f.fenster, _DEV).move(0, weit).commit()
    QApplication.processEvents()
    time.sleep(zs.HALTEN_MIN_S + 0.05)
    QApplication.processEvents()
    QTest.touchEvent(v.f.fenster, _DEV).move(0, weit).press(1, t).commit()
    QApplication.processEvents()
    assert not _filter().halten_laeuft
    QTest.touchEvent(v.f.fenster, _DEV).move(0, weit).release(1, t).commit()
    QTest.touchEvent(v.f.fenster, _DEV).release(0, weit).commit()
    QApplication.processEvents()


def test_vc_spielbetrieb_kein_halten(vc):
    v = vc
    v.canvas.set_edit_mode(False)
    h, t = v.f.lage(v.b[0]), v.f.lage(v.b[1])
    v.f.druck(h)
    v.f.halten(h, zs.HALTEN_MIN_S + 0.1)
    v.f.tippen(h, t)
    v.f.los(h)
    assert v.canvas.ausgewaehlte() == []


# ── 2D-Buehne ────────────────────────────────────────────────────────────────

@pytest.fixture
def buehne():
    from src.ui.views.live_view import StageCanvas
    c = StageCanvas()
    fx = [SimpleNamespace(fid=i, universe=1, address=i, label=f"PAR-{i}", fixture_type="PAR")
          for i in (1, 2, 3)]
    c._state.get_patched_fixtures = lambda: list(fx)
    c.world_w, c.world_h = 1200, 800
    c.set_zoom(1.0)
    c.snap_enabled = False
    area = QScrollArea()
    area.setWidgetResizable(False)
    area.setWidget(c)
    area.resize(520, 420)
    area.show()
    QTest.qWaitForWindowExposed(area)
    QApplication.processEvents()
    c._positions = {1: (100.0, 100.0), 2: (300.0, 100.0), 3: (300.0, 300.0)}
    c.uebernommen = []
    c._verschiebung_uebernehmen = lambda fids: c.uebernommen.append(list(fids))
    c._selected_fids = []
    menue = QMenu(area)
    menue.addAction("Gruppe …")

    def zeigen(_fid, glob):
        menue.exec(glob)        # wie die LiveView: blockierendes Menue
    c.context_menu_requested.connect(zeigen)
    try:
        yield SimpleNamespace(c=c, area=area, vp=area.viewport(), f=_Finger(area))
    finally:
        c._state.__dict__.pop("get_patched_fixtures", None)


def _welt(b, x, y) -> QPoint:
    return b.vp.mapTo(b.area, QPoint(x, y))


def test_buehne_halten_mit_zittern(buehne):
    b = buehne
    h = _welt(b, 100, 100)
    b.f.druck(h)
    b.f.halten(h, zs.HALTEN_MIN_S + 0.1)
    b.f.tippen(h, _welt(b, 300, 100))
    b.f.tippen(h, _welt(b, 300, 300), pid=2)
    b.f.los(h)
    assert sorted(b.c._selected_fids) == [1, 2, 3]
    assert b.c.uebernommen == [], "nichts verschoben"


def test_buehne_lang_gehalten_menue_offen(buehne):
    b = buehne
    h, t = _welt(b, 100, 100), _welt(b, 300, 100)
    ablauf = {"fertig": False}

    def im_menue():
        if QApplication.activePopupWidget() is None:
            QTimer.singleShot(20, im_menue)
            return
        b.f.tippen(h, t)
        ablauf["popup_danach"] = QApplication.activePopupWidget()
        if ablauf["popup_danach"] is not None:
            ablauf["popup_danach"].close()     # roter Lauf haengt nicht im Menue
        ablauf["fertig"] = True

    b.f.druck(h)
    QTimer.singleShot(20, im_menue)
    assert _warte_bis(lambda: ablauf["fertig"], 5.0)
    assert ablauf["popup_danach"] is None
    b.f.los(h)
    assert sorted(b.c._selected_fids) == [1, 2]
