"""CDX-72: Codex-Ernte PRs 1255-1294 — Befunde in der Virtuellen Konsole.

Je Befund ein Test, der den Fehler zeigt, und die Gegenprobe:

1. Bankwechsel bei gehaltenem Motorfader: der Fader der neuen Bank kannte
   die Beruehrung nicht und fuhr gegen die Hand.
2. Pickup (Soft-Takeover) blieb nach erfolgreicher Motorfahrt armiert.
3. Pult-LEDs gingen beim Beenden nicht aus (erst nach ``close_all``).
4. VC-Cueliste: nach Seitenwechsel mit gleicher Cue-Zahl veraltete Eintraege,
   der Sprung traf eine andere Cue.
5. Halten + Antippen stellte nur das gehaltene Widget zurueck, nicht die
   ganze gezogene Gruppe.
6. Raum-Pad gab beim Loeschen/Neuladen seine Programmer-Werte nicht frei.
7. „Pfad loeschen" ueberschrieb einen nachtraeglich geaenderten
   EFX-Algorithmus.
"""
from __future__ import annotations

import ast
import inspect
import os
import textwrap
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt        # noqa: E402
from PySide6.QtGui import QMouseEvent                                # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget                  # noqa: E402

import src.core.midi.midi_manager as mgr                             # noqa: E402
from src.core.midi.midi_mapper import MOTOR_NACHLAUF_S               # noqa: E402

_app = QApplication.instance() or QApplication([])

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402


class _FakeMM:
    def __init__(self):
        self.pb: list[tuple[int, int]] = []
        self.roh: list[list[int]] = []
        self.ok = True

    def current_output_name(self):
        return ""

    def send_pitchbend(self, kanal, wert):
        if not self.ok:
            return False
        self.pb.append((kanal, wert))
        return True

    def send_message(self, msg):
        if not self.ok:
            return False
        self.roh.append(list(msg))
        return True

    def __getattr__(self, name):         # alles andere: stumm
        return lambda *a, **k: None


class _Uhr:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _pb(kanal: int, wert14: int):
    return mgr._decode([0xE0 | (kanal - 1), wert14 & 0x7F, (wert14 >> 7) & 0x7F], "X-Touch")


def _note(kanal: int, nummer: int, velocity: int):
    return mgr._decode([0x90 | (kanal - 1), nummer, velocity], "X-Touch")


def _w14(v255: int) -> int:
    return round(v255 / 255 * 16383)


@pytest.fixture
def mm(monkeypatch):
    from src.ui.virtualconsole.vc_slider import VCSlider
    f = _FakeMM()
    monkeypatch.setattr(mgr, "get_midi_manager", lambda: f)
    monkeypatch.setattr(VCSlider, "soft_takeover", False)
    yield f
    destroy_all_top_level_widgets(_app)


def _motor_slider(parent=None, kanal=2, bank=-1):
    from src.ui.virtualconsole.vc_slider import SliderMode, VCSlider
    s = VCSlider("F", parent) if parent is not None else VCSlider("F")
    s.mode = SliderMode.SPEED                   # harmloser Modus
    s.apply_midi_binding("pitchbend", kanal, 0)
    s.midi_motor = True
    s.bank = bank
    uhr = _Uhr()
    s._motor._uhr = uhr
    return s, uhr


# ── 1. Bankwechsel bei gehaltenem Motorfader ────────────────────────────────

def _canvas_zwei_banken(mm):
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    c = VCCanvas()
    c._led_timer.stop()
    a, uhr_a = _motor_slider(c, bank=0)
    b, uhr_b = _motor_slider(c, bank=1)
    a._value = 40
    b._value = 200
    c.set_active_bank(0)
    return c, a, b, uhr_a, uhr_b


def test_bankwechsel_bei_gehaltenem_fader_faehrt_nicht_gegen_die_hand(mm):
    c, a, b, _ua, _ub = _canvas_zwei_banken(mm)
    try:
        c._handle_midi(_note(1, 105, 127))       # Hand auf Fader 2 (Bank 0)
        mm.pb.clear()
        c.set_active_bank(1)                      # Bank wechseln, Hand bleibt
        assert mm.pb == [], "der Motor darf nicht gegen die Hand fahren"
        c._handle_midi(_note(1, 105, 0))          # loslassen
        assert mm.pb == [(2, _w14(200))], "nach dem Loslassen auf den Wert der neuen Bank"
    finally:
        c._teardown_midi()
        c._teardown_keyboard()
        c.deleteLater()


def test_bankwechsel_ohne_hand_faehrt_sofort(mm):
    c, a, b, _ua, _ub = _canvas_zwei_banken(mm)
    try:
        c._handle_midi(_note(1, 105, 127))
        c._handle_midi(_note(1, 105, 0))
        mm.pb.clear()
        c.set_active_bank(1)
        assert mm.pb == [(2, _w14(200))]
    finally:
        c._teardown_midi()
        c._teardown_keyboard()
        c.deleteLater()


def test_andere_fader_beruehrung_sperrt_bankwechsel_nicht(mm):
    c, a, b, _ua, _ub = _canvas_zwei_banken(mm)
    try:
        c._handle_midi(_note(1, 104, 127))       # Hand auf Fader 1, nicht 2
        mm.pb.clear()
        c.set_active_bank(1)
        assert mm.pb == [(2, _w14(200))]
    finally:
        c._teardown_midi()
        c._teardown_keyboard()
        c.deleteLater()


# ── 2. Pickup nach erfolgreicher Motorfahrt ─────────────────────────────────

def test_pickup_nach_motorfahrt_entschaerft(mm, monkeypatch):
    from src.ui.virtualconsole.vc_slider import VCSlider
    monkeypatch.setattr(VCSlider, "soft_takeover", True)
    s, uhr = _motor_slider()
    s._value = 100
    s.arm_pickup()
    assert mm.pb, "Motor ist angefahren"
    assert not s._pickup_armed, "der Fader steht am Ziel, kein Pickup noetig"
    uhr.t += MOTOR_NACHLAUF_S + 0.5
    assert s.handle_midi(_pb(2, _w14(200)))
    assert s.value == 200


def test_pickup_bleibt_ohne_motor_oder_bei_fehlschlag(mm, monkeypatch):
    from src.ui.virtualconsole.vc_slider import VCSlider
    monkeypatch.setattr(VCSlider, "soft_takeover", True)
    ohne = VCSlider("G")
    ohne.apply_midi_binding("pitchbend", 3, 0)
    ohne._value = 100
    ohne.arm_pickup()
    assert ohne._pickup_armed
    ohne.handle_midi(_pb(3, _w14(200)))
    assert ohne.value == 100, "Gegenprobe: ohne Motor greift Soft-Takeover"

    mm.ok = False                                 # Ausgang zu: nichts angekommen
    s, _uhr = _motor_slider()
    s._value = 100
    s.arm_pickup()
    assert s._pickup_armed


def test_pickup_entschaerft_nach_loslassen_mit_nachtrag(mm, monkeypatch):
    from src.ui.virtualconsole.vc_slider import VCSlider
    monkeypatch.setattr(VCSlider, "soft_takeover", True)
    s, _uhr = _motor_slider()
    s.handle_midi(_note(1, 105, 127))             # Hand drauf
    s._value = 100
    s.arm_pickup()
    assert s._pickup_armed, "Hand am Fader: der Motor faehrt noch nicht"
    s.handle_midi(_note(1, 105, 0))               # loslassen -> Motor faehrt
    assert mm.pb[-1] == (2, _w14(100))
    assert not s._pickup_armed


# ── 3. Pult-LEDs beim Beenden ───────────────────────────────────────────────

def _led_canvas(mm):
    from src.ui.virtualconsole.vc_button import VCButton
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    c = VCCanvas()
    t = VCButton("Mute", c)
    t.midi_type = "note_on"
    t.midi_ch = 1
    t.midi_data1 = 16
    t.midi_led = True
    t._pressed = True
    c.led_rueckmeldung_pruefen()
    assert [0x90, 16, 127] in mm.roh
    assert c._led_timer.isActive()
    mm.roh.clear()
    return c, t


def test_led_abschalten_loescht_und_stoppt_timer(mm):
    c, _t = _led_canvas(mm)
    try:
        c.led_abschalten()
        assert mm.roh and mm.roh[-1][1] == 16 and mm.roh[-1][2] == 0
        assert not c._led_timer.isActive()
    finally:
        c._teardown_midi()
        c._teardown_keyboard()
        c.deleteLater()


def test_hauptfenster_schaltet_leds_vor_close_all_ab(mm):
    from src.ui.main_window import MainWindow
    c, _t = _led_canvas(mm)
    try:
        fake = SimpleNamespace(_vc_zeichenflaeche=lambda: c)
        MainWindow._vc_leds_abschalten(fake)
        assert mm.roh and mm.roh[-1][2] == 0
        assert not c._led_timer.isActive()
        # ohne Canvas still nichts
        MainWindow._vc_leds_abschalten(SimpleNamespace(_vc_zeichenflaeche=lambda: None))
    finally:
        c._teardown_midi()
        c._teardown_keyboard()
        c.deleteLater()
    # Reihenfolge in closeEvent: erst LEDs, dann close_all
    quelle = textwrap.dedent(inspect.getsource(MainWindow.closeEvent))
    baum = ast.parse(quelle)
    zeilen = {}
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute):
            zeilen.setdefault(knoten.func.attr, knoten.lineno)
    assert "_vc_leds_abschalten" in zeilen
    assert zeilen["_vc_leds_abschalten"] < zeilen["close_all"]


# ── 4. VC-Cueliste nach Seitenwechsel ───────────────────────────────────────

class _Stapel:
    def __init__(self, cues):
        self.cues = cues
        self.current_index = -1
        self.sprung: list[float] = []

    def go_to(self, nummer):
        self.sprung.append(nummer)


def _cue(nummer, label):
    return SimpleNamespace(number=float(nummer), label=label)


def _cueliste(monkeypatch):
    from src.ui.virtualconsole.vc_cuelist import VCCueList
    s1 = _Stapel([_cue(1, "Intro"), _cue(2, "Strophe")])
    s2 = _Stapel([_cue(5, "Finale"), _cue(7, "Applaus")])
    pe = SimpleNamespace(current_page=0, pages=[[SimpleNamespace(stack=s1)],
                                                [SimpleNamespace(stack=s2)]])
    pe.executors = property(lambda self: None)
    w = VCCueList()
    w._refresh_timer.stop()
    w.stack_slot = 0
    w.fixed_page = None

    def _engine():
        pe.executors = pe.pages[pe.current_page]
        return pe
    monkeypatch.setattr(w, "_engine", _engine)
    return w, pe, s1, s2


def test_cueliste_baut_nach_seitenwechsel_neu_auf(monkeypatch):
    w, pe, s1, s2 = _cueliste(monkeypatch)
    w._refresh()
    assert w._cue_list.item(0).data(Qt.ItemDataRole.UserRole) == 1.0
    pe.current_page = 1                           # gleiche Cue-Zahl, andere Cues
    w._refresh()
    texte = [w._cue_list.item(i).text() for i in range(w._cue_list.count())]
    assert "Finale" in texte[0] and "Applaus" in texte[1]
    assert w._cue_list.item(0).data(Qt.ItemDataRole.UserRole) == 5.0


def test_cueliste_umbenannt_gleiche_zahl(monkeypatch):
    w, pe, s1, _s2 = _cueliste(monkeypatch)
    w._refresh()
    s1.cues[1] = _cue(2, "Refrain")
    w._refresh()
    assert "Refrain" in w._cue_list.item(1).text()


def test_cueliste_sprung_mit_veraltetem_eintrag_springt_nicht(monkeypatch):
    w, pe, s1, s2 = _cueliste(monkeypatch)
    w._refresh()
    item = w._cue_list.item(1)                    # „2 Strophe" der Seite 1
    pe.current_page = 1                           # Seite wechselt, Timer noch nicht gelaufen
    gefragt = []
    monkeypatch.setattr(w, "_bestaetige_sprung", lambda t: gefragt.append(t) or True)
    w._on_cue_double(item)
    assert s2.sprung == [] and s1.sprung == []
    assert gefragt == [], "keine Rueckfrage mit dem alten Text"
    # nach dem Neuaufbau springt derselbe Weg richtig
    w._on_cue_double(w._cue_list.item(1))
    assert s2.sprung == [7.0]


def test_gehe_zu_unbekannte_nummer_springt_nicht(monkeypatch):
    w, pe, s1, _s2 = _cueliste(monkeypatch)
    w._gehe_zu(9.0)
    assert s1.sprung == []
    w._gehe_zu(2.0)
    assert s1.sprung == [2.0]


# ── 5. Halten + Antippen stellt die ganze Gruppe zurueck ────────────────────

def _maus(w, typ, glob: QPoint):
    lokal = w.mapFromGlobal(glob)
    knopf = Qt.MouseButton.NoButton if typ == QEvent.Type.MouseMove else Qt.MouseButton.LeftButton
    knoepfe = (Qt.MouseButton.NoButton if typ == QEvent.Type.MouseButtonRelease
               else Qt.MouseButton.LeftButton)
    ev = QMouseEvent(typ, QPointF(lokal), QPointF(glob), knopf, knoepfe,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(w, ev)


def test_halten_antippen_setzt_ganze_gruppe_zurueck(mm):
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    c = VCCanvas()
    c.resize(900, 600)
    c.show()
    QTest.qWaitForWindowExposed(c)
    try:
        c.set_edit_mode(True)
        ws = [c._add_widget("VCButton", QPoint(40 + 160 * i, 60)) for i in range(3)]
        for w in ws:
            w._snap_grid = 0
        c.auswahl_setzen(ws)
        QApplication.processEvents()
        vorher = [QRect(w.geometry()) for w in ws]
        undo_vorher = len(c._undo_stack)
        start = ws[0].mapToGlobal(ws[0].rect().center())
        _maus(ws[0], QEvent.Type.MouseButtonPress, start)
        _maus(ws[0], QEvent.Type.MouseMove, start + QPoint(3, 2))   # Zittern
        assert ws[1].geometry() != vorher[1], "die Gruppe ist mitgewandert"
        assert c.halten_antippen_start(QPointF(start))
        assert [w.geometry() for w in ws] == vorher
        _maus(ws[0], QEvent.Type.MouseButtonRelease, start + QPoint(3, 2))
        assert [w.geometry() for w in ws] == vorher
        assert len(c._undo_stack) == undo_vorher, "kein Undo-Schritt"
    finally:
        c._teardown_midi()
        c._teardown_keyboard()
        c.close()
        c.deleteLater()


# ── 6. Raum-Pad gibt beim Loeschen/Neuladen frei ────────────────────────────

class _ProgState:
    def __init__(self):
        self.werte: dict = {}

    def get_programmer_value(self, fid, attr, head=None):
        return self.werte.get((fid, attr, head))

    def set_programmer_value(self, fid, attr, wert, head=None):
        self.werte[(fid, attr, head)] = wert

    def clear_programmer_value(self, fid, key):
        self.werte.pop((fid, key, None), None)

    def _head_key(self, fid, attr, kopf):
        return f"{attr}#{kopf}"


@pytest.fixture
def raum(mm, monkeypatch):
    from src.ui.virtualconsole import vc_raumpad
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    st = _ProgState()
    monkeypatch.setattr(vc_raumpad, "_state", lambda: st)
    c = VCCanvas()
    yield c, st
    c._teardown_midi()
    c._teardown_keyboard()
    c.deleteLater()


def _eingerastetes_pad(c, st, wo=None):
    ziel = wo if wo is not None else c
    if wo is None:
        p = c._add_widget("VCRaumPad", QPoint(20, 20))
    else:
        p = wo._add_child_widget("VCRaumPad", QPoint(10, 30))
    assert p.position_lock, "Vorgabe: Lock AN"
    st.werte[(5, "pan", None)] = 128              # Vorher-Wert von jemand anderem
    p._eigene[(5, "pan", None)] = [128, 200]
    p._eigene[(5, "tilt", None)] = [None, 90]
    st.werte[(5, "pan", None)] = 200
    st.werte[(5, "tilt", None)] = 90
    p.aktiv = True
    del ziel
    return p


def test_raumpad_loeschen_gibt_frei(raum):
    c, st = raum
    p = _eingerastetes_pad(c, st)
    c._remove_widget(p, undo=False)
    assert st.werte.get((5, "pan", None)) == 128
    assert (5, "tilt", None) not in st.werte


def test_raumpad_im_kasten_loeschen_gibt_frei(raum):
    c, st = raum
    kasten = c._add_widget("VCFrame", QPoint(300, 20))
    kasten.resize(400, 400)
    _eingerastetes_pad(c, st, kasten)
    c._remove_widget(kasten, undo=False)
    assert st.werte.get((5, "pan", None)) == 128
    assert (5, "tilt", None) not in st.werte


def test_raumpad_neuladen_gibt_frei_fremde_werte_bleiben(raum):
    c, st = raum
    p = _eingerastetes_pad(c, st)
    st.werte[(5, "tilt", None)] = 33              # inzwischen fremd ueberschrieben
    c._clear()
    assert st.werte.get((5, "pan", None)) == 128
    assert st.werte.get((5, "tilt", None)) == 33
    del p


def test_raumpad_bankwechsel_behaelt_werte_bei_lock_an(raum):
    c, st = raum
    p = _eingerastetes_pad(c, st)
    p.hide()
    assert st.werte.get((5, "pan", None)) == 200
    assert p.aktiv


# ── 7. Pfad loeschen und geaenderter Algorithmus ────────────────────────────

@pytest.fixture
def efx():
    from src.core.engine.efx import EfxAlgorithm, EfxFixture, EfxInstance
    from src.core.engine.function_manager import get_function_manager
    fm = get_function_manager()
    fm.stop_all()
    vorher = {f.id for f in fm.all()}
    e = EfxInstance("mh")
    e.algorithm = EfxAlgorithm.EIGHT
    e.fixtures = [EfxFixture(fid=5)]
    e.x_offset, e.y_offset, e.width, e.height = 100.0, 140.0, 80.0, 60.0
    fm.add(e)
    yield e
    destroy_all_top_level_widgets(_app)
    fm.stop_all()
    for f in list(fm.all()):
        if f.id not in vorher:
            fm.remove(f.id)


def _pfad_zeichnen(e):
    from src.ui.virtualconsole.vc_xypad import VCXYPad
    p = VCXYPad("XY")
    p.mode = "path"
    p.efx_function_id = e.id
    p.resize(240, 240)
    eltern = QWidget()
    eltern.resize(280, 280)
    p.setParent(eltern)
    p.move(20, 20)
    eltern.show()
    p._traeger = eltern
    QApplication.processEvents()
    pr = p._pad_rect()
    a = QPoint(pr.x() + 20, pr.y() + 20)
    b = QPoint(pr.right() - 20, pr.bottom() - 30)
    for typ, pos in ([(QEvent.Type.MouseButtonPress, a)]
                     + [(QEvent.Type.MouseMove, a + (b - a) * (i / 6)) for i in range(1, 7)]
                     + [(QEvent.Type.MouseButtonRelease, b)]):
        knopf = Qt.MouseButton.NoButton if typ == QEvent.Type.MouseMove else Qt.MouseButton.LeftButton
        knoepfe = (Qt.MouseButton.NoButton if typ == QEvent.Type.MouseButtonRelease
                   else Qt.MouseButton.LeftButton)
        QApplication.sendEvent(p, QMouseEvent(typ, QPointF(pos), QPointF(p.mapToGlobal(pos)),
                                              knopf, knoepfe, Qt.KeyboardModifier.NoModifier))
    return p


def test_pfad_loeschen_behaelt_spaeter_gewaehlten_algorithmus(efx):
    from src.core.engine.efx import EfxAlgorithm
    p = _pfad_zeichnen(efx)
    assert efx.algorithm == EfxAlgorithm.CUSTOM
    vc_pfad = efx.path_id
    efx.set_param("algorithm", "Circle")
    assert efx.algorithm == EfxAlgorithm.CIRCLE and efx.path_id == vc_pfad
    assert p.pfad_loeschen()
    assert efx.algorithm == EfxAlgorithm.CIRCLE, "Fremdaenderung bleibt"
    assert efx.path_id != vc_pfad


def test_pfad_loeschen_ohne_fremdaenderung_alter_algorithmus(efx):
    from src.core.engine.efx import EfxAlgorithm
    p = _pfad_zeichnen(efx)
    assert p.pfad_loeschen()
    assert efx.algorithm == EfxAlgorithm.EIGHT
    assert efx.path_id is None


# ── Alte Show laedt unveraendert ────────────────────────────────────────────

def test_alte_show_laedt_und_neuladen_gibt_raumpad_frei(raum):
    """Layout im alten Format (ohne neue Schluessel): Cueliste, Motor-Fader,
    Raum-Pad und XY-Pad laden wie bisher; ein zweites Laden gibt die Werte
    eines eingerasteten Pads frei. Gespeichert wird nichts Neues."""
    c, st = raum
    alt = {"widgets": [
        {"type": "VCCueList", "x": 10, "y": 10, "w": 200, "h": 220, "caption": "Cues",
         "stack_slot": 0},
        {"type": "VCSlider", "x": 230, "y": 10, "w": 60, "h": 220, "caption": "F1",
         "midi_type": "pitchbend", "midi_cc": 0, "midi_ch": 1, "midi_motor": True},
        {"type": "VCRaumPad", "x": 300, "y": 10, "w": 300, "h": 260, "caption": "Raum",
         "fixture_ids": [5], "ziel": [1.0, 2.0]},
        {"type": "VCXYPad", "x": 620, "y": 10, "w": 200, "h": 200, "caption": "XY"},
    ]}
    c.from_dict(alt)
    from src.ui.virtualconsole.vc_raumpad import VCRaumPad
    typen = sorted(w["type"] for w in c.to_dict()["widgets"])
    assert typen == ["VCCueList", "VCRaumPad", "VCSlider", "VCXYPad"]
    pad = c.findChildren(VCRaumPad)[0]
    assert pad.position_lock and pad.ziel == (1.0, 2.0)
    for w in c.to_dict()["widgets"]:
        assert "eigener_algo" not in w and "_sig" not in w
    st.werte[(5, "pan", None)] = 200
    pad._eigene[(5, "pan", None)] = [None, 200]
    pad.aktiv = True
    c.from_dict(alt)
    assert (5, "pan", None) not in st.werte
