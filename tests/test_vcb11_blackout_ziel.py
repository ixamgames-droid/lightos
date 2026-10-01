"""VCB-11: VC-Blackout-Taste mit Ziel (einzelne Geraete und/oder Gruppen).

Neben dem globalen Blackout kann eine VC-Taste mit Aktion BLACKOUT ein Ziel tragen;
sie schaltet dann NUR diese Geraete dunkel — mit derselben Regel wie der globale
Blackout (OUT-57): Dimmer/Farbe/Intensitaet 0, Pan/Tilt/Gobo/Optik bleiben, Lampen
ohne echten Dimmer und Laser/Nebel komplett 0. Der Rest laeuft weiter.

Mechanismus: eigener gezielter Blackout im OutputManager (eine Null-Maske je Slot,
Vereinigung aller aktiven Slots, in ``_send_all`` nach dem Grand-Master angewandt,
Laser-NOT-AUS bleibt letzte Ebene). Der zuweisbare Submaster reicht NICHT: er
skaliert nur Intensitaetsadressen — die Farbe einer Lampe mit Dimmer bliebe
stehen, raw-/Strobe-Kanaele und Laser/Nebel ebenso.
"""
import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from src.core.app_state import AppState
from src.core.dmx.output_manager import OutputManager
import src.core.app_state as app_state_mod
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction

_app = QApplication.instance() or QApplication([])


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num


class _Fx:
    def __init__(self, fid, universe, address, fixture_type="", name=""):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.fixture_type = fixture_type
        self.fixture_name = name


class _FakeSender:
    def __init__(self):
        self.last = None

    def send_dmx(self, data):
        self.last = data

    def close(self):
        pass


# Gruppe A: Moving Head ab 1 (Pan, Tilt, Dimmer, R, G, B, Gobo, Prisma)
_MH = [_Ch("pan", 1), _Ch("tilt", 2), _Ch("dimmer", 3), _Ch("color_r", 4),
       _Ch("color_g", 5), _Ch("color_b", 6), _Ch("gobo", 7), _Ch("prism", 8)]
# Gruppe B: PAR ab 20 (Dimmer, R, G, B, Strobe)
_PAR = [_Ch("dimmer", 1), _Ch("color_r", 2), _Ch("color_g", 3), _Ch("color_b", 4),
        _Ch("strobe", 5)]
# Ohne Gruppe: RGB-Spot OHNE Dimmer ab 40 (Pan, R, G, B)
_RGB_OHNE_DIMMER = [_Ch("pan", 1), _Ch("color_r", 2), _Ch("color_g", 3),
                    _Ch("color_b", 4)]

_WERTE = {1: 200, 2: 128, 3: 255, 4: 255, 5: 100, 6: 50, 7: 64, 8: 90,
          20: 255, 21: 10, 22: 20, 23: 30, 24: 40,
          40: 77, 41: 11, 42: 22, 43: 33,
          100: 150}   # ungepatchte Roh-Adresse


def _setup(gruppen=None):
    """(AppState ohne __init__, OutputManager, FakeSender)."""
    st = AppState.__new__(AppState)
    st._fix_index = {1: (_Fx(1, 1, 1), _MH), 2: (_Fx(2, 1, 20), _PAR),
                     3: (_Fx(3, 1, 40), _RGB_OHNE_DIMMER)}
    om = OutputManager()
    u = om.add_universe(1)
    for a, v in _WERTE.items():
        u.set_channel(a, v)
    fake = _FakeSender()
    om._enttec_outputs[1] = fake
    st.output_manager = om
    st._gruppen = dict(gruppen or {"A": [1], "B": [2]})
    # Gruppen als FEINE Zellen ("fid" bzw. "fid:kopf"), wie group_cells_by_name.
    st.group_cells_by_name = lambda name: [str(c) for c in st._gruppen.get(name, [])]
    st.group_fids_by_name = lambda name: list(dict.fromkeys(
        int(str(c).partition(":")[0]) for c in st._gruppen.get(name, [])))
    st._emit = lambda *a, **k: None
    om.set_blackout_keep_mask(
        {k: frozenset(v) for k, v in st._build_blackout_keep_mask(st._fix_index).items()})
    return st, om, fake


def _frame(om, fake):
    om._send_all()
    return fake.last


class GezielterBlackoutTest(unittest.TestCase):

    def _assert_a_dunkel(self, d):
        for a in (3, 4, 5, 6):
            self.assertEqual(d[a - 1], 0, f"MH-Adresse {a} muss dunkel sein")
        # Pan/Tilt/Gobo/Prisma unveraendert
        self.assertEqual((d[0], d[1], d[6], d[7]), (200, 128, 64, 90))

    def _assert_a_hell(self, d):
        for a in range(1, 9):
            self.assertEqual(d[a - 1], _WERTE[a])

    def _assert_b_dunkel(self, d):
        for a in range(20, 25):
            self.assertEqual(d[a - 1], 0, f"PAR-Adresse {a} muss dunkel sein")

    def _assert_b_hell(self, d):
        for a in range(20, 25):
            self.assertEqual(d[a - 1], _WERTE[a])

    def test_gruppe_a_dunkelt_nur_gruppe_a(self):
        st, om, fake = _setup()
        st.set_target_blackout("t1", groups=["A"])
        d = _frame(om, fake)
        self._assert_a_dunkel(d)
        self._assert_b_hell(d)
        self.assertEqual(d[99], 150, "ungepatchte Roh-Adresse laeuft weiter")
        self.assertEqual(d[39], 77)
        # Anzeige folgt (WYSIWYG)
        self.assertEqual(om.get_display_frame(1), d)
        st.clear_target_blackout("t1")
        d = _frame(om, fake)
        self._assert_a_hell(d)
        self.assertEqual(om.target_blackout_slots(), [])

    def test_einzelgeraet_ohne_dimmer_komplett_dunkel(self):
        st, om, fake = _setup()
        st.set_target_blackout("t1", fids=[3])
        d = _frame(om, fake)
        for a in (40, 41, 42, 43):
            self.assertEqual(d[a - 1], 0, "ohne Dimmer: auch Pan geht auf 0")
        self._assert_a_hell(d)
        self._assert_b_hell(d)

    def test_laser_im_ziel_komplett_dunkel(self):
        st, om, fake = _setup()
        st._fix_index[4] = (_Fx(4, 1, 60, fixture_type="laser"),
                            [_Ch("dimmer", 1), _Ch("pan", 2)])
        om.universes[1].set_channel(60, 255)
        om.universes[1].set_channel(61, 99)
        st.set_target_blackout("t1", fids=[4])
        d = _frame(om, fake)
        self.assertEqual((d[59], d[60]), (0, 0))

    def test_zwei_tasten_ueberlagern_sich(self):
        st, om, fake = _setup()
        st.set_target_blackout("t1", groups=["A"])
        st.set_target_blackout("t2", groups=["B"])
        d = _frame(om, fake)
        self._assert_a_dunkel(d)
        self._assert_b_dunkel(d)
        st.clear_target_blackout("t1")
        d = _frame(om, fake)
        self._assert_a_hell(d)
        self._assert_b_dunkel(d)

    def test_ueberlappende_ziele_eines_loesen_haelt_dunkel(self):
        st, om, fake = _setup()
        st.set_target_blackout("t1", groups=["A"])
        st.set_target_blackout("t2", fids=[1, 2])
        st.clear_target_blackout("t1")
        d = _frame(om, fake)
        self._assert_a_dunkel(d)
        self._assert_b_dunkel(d)

    def test_globaler_blackout_unveraendert(self):
        st, om, fake = _setup()
        om.set_blackout(True)
        d = _frame(om, fake)
        self._assert_a_dunkel(d)
        self._assert_b_dunkel(d)
        self.assertEqual(d[99], 0)
        # gezielter Blackout zusaetzlich: am globalen Bild aendert sich nichts
        st.set_target_blackout("t1", groups=["A"])
        self.assertEqual(_frame(om, fake), d)
        om.set_blackout(False)
        st.clear_target_blackout("t1")
        d = _frame(om, fake)
        self._assert_a_hell(d)
        self._assert_b_hell(d)

    def test_gruppe_spaeter_geaendert_wirkt(self):
        st, om, fake = _setup()
        st.set_target_blackout("t1", groups=["A"])
        st._gruppen["A"] = [2]
        st.notify_groups_changed()
        d = _frame(om, fake)
        self._assert_a_hell(d)
        self._assert_b_dunkel(d)

    def test_laser_estop_bleibt_letzte_ebene(self):
        st, om, fake = _setup()
        om.set_laser_estop_mask({1: frozenset({100})})
        st.set_target_blackout("t1", groups=["B"])
        d = _frame(om, fake)
        self.assertEqual(d[99], 0)

    def test_leeres_ziel_wirkt_nicht_global(self):
        st, om, fake = _setup()
        st.set_target_blackout("t1", groups=["Gibt-es-nicht"])
        d = _frame(om, fake)
        self._assert_a_hell(d)
        self._assert_b_hell(d)

    def test_clear_all(self):
        st, om, fake = _setup()
        st.set_target_blackout("t1", groups=["A"])
        st.set_target_blackout("t2", groups=["B"])
        st.clear_all_target_blackouts()
        d = _frame(om, fake)
        self._assert_a_hell(d)
        self._assert_b_hell(d)


# 4-Kopf-Pixelbar ab 200: geteilter Master-Dimmer, 4x RGB, geteilter Strobe
_BAR = ([_Ch("dimmer", 1)]
        + [_Ch(a, 2 + 3 * k + i) for k in range(4)
           for i, a in enumerate(("color_r", "color_g", "color_b"))]
        + [_Ch("strobe", 14)])


def _kopf_adressen(k):
    return [202 + 3 * k + i - 1 for i in range(3)]   # Adressen von Kopf k


class KopfGruppeTest(unittest.TestCase):
    """Review-Befund 1: eine Gruppe aus Kopf-Zellen dunkelt nur diese Koepfe."""

    def _setup(self, zellen):
        st, om, fake = _setup({"K": zellen})
        st._fix_index[5] = (_Fx(5, 1, 200), _BAR)
        for a in range(200, 214):
            om.universes[1].set_channel(a, 100 + (a - 200))
        return st, om, fake

    def test_kopf_zellen_nur_diese_koepfe(self):
        st, om, fake = self._setup(["5:1", "5:2"])
        st.set_target_blackout("t1", groups=["K"])
        d = _frame(om, fake)
        for k in (1, 2):
            for a in _kopf_adressen(k):
                self.assertEqual(d[a - 1], 0, f"Kopf {k}, Adresse {a} muss dunkel sein")
        for k in (0, 3):
            for a in _kopf_adressen(k):
                self.assertEqual(d[a - 1], 100 + (a - 200), f"Kopf {k} bleibt hell")
        # geteilter Master-Dimmer und Strobe bleiben (sonst ganzes Geraet aus)
        self.assertEqual(d[199], 100)
        self.assertEqual(d[212], 113)
        # Rest der Show unberuehrt
        self._assert_rest(d)

    def _assert_rest(self, d):
        for a in range(1, 9):
            self.assertEqual(d[a - 1], _WERTE[a])

    def test_alle_koepfe_heisst_ganzes_geraet(self):
        st, om, fake = self._setup(["5:0", "5:1", "5:2", "5:3"])
        st.set_target_blackout("t1", groups=["K"])
        d = _frame(om, fake)
        for a in range(200, 214):
            self.assertEqual(d[a - 1], 0)

    def test_ganze_zelle_schlaegt_kopf_zelle(self):
        st, om, fake = self._setup(["5", "5:1"])
        st.set_target_blackout("t1", groups=["K"])
        d = _frame(om, fake)
        self.assertEqual(d[199], 0, "ganzes Geraet: auch der Master-Dimmer")

    def test_direktes_fid_ziel_schlaegt_kopf_gruppe(self):
        st, om, fake = self._setup(["5:1"])
        st.set_target_blackout("t1", fids=[5], groups=["K"])
        d = _frame(om, fake)
        self.assertEqual(d[199], 0)


class GruppenSyncTest(unittest.TestCase):
    """Review-Befund 2: GROUP_CHANGED direkt am Bus (Gruppen-View, Live View)."""

    def setUp(self):
        from src.core.sync import get_sync, SyncEvent
        self.sync, self.ev = get_sync(), SyncEvent.GROUP_CHANGED
        self.st, self.om, self.fake = _setup()
        self.st._abo_gruppen_sync()
        self.addCleanup(self.sync.unsubscribe, self.ev, self.st._gruppen_sync_cb)

    def test_direktes_sync_event_wirkt(self):
        self.st.set_target_blackout("t1", groups=["A"])
        self.st._gruppen["A"] = [2]
        self.sync.emit(self.ev, None)
        d = _frame(self.om, self.fake)
        self.assertEqual(d[2], 255, "MH wieder hell")
        self.assertEqual(d[19], 0, "PAR jetzt dunkel")

    def test_abo_einmalig_und_kein_doppelter_refresh(self):
        self.st._abo_gruppen_sync()        # zweiter Aufruf: kein zweites Abo
        n = sum(1 for cb in self.sync._subscribers[self.ev]
                if cb is self.st._gruppen_sync_cb)
        self.assertEqual(n, 1)
        # notify_groups_changed mit echtem _emit -> GENAU ein Refresh
        del self.st._emit
        self.st._callbacks = []
        self.st._ui_marshaller = None
        self.st.sync = self.sync
        aufrufe = []
        orig = self.st._refresh_target_blackouts
        self.st._refresh_target_blackouts = lambda *a: (aufrufe.append(1), orig())
        self.st.notify_groups_changed()
        self.assertEqual(len(aufrufe), 1)

    def test_abo_weg_dann_direkter_refresh(self):
        # Bus geleert (Reset/Test-Isolation): notify_groups_changed refresht selbst.
        self.sync.unsubscribe(self.ev, self.st._gruppen_sync_cb)
        self.st.set_target_blackout("t1", groups=["A"])
        self.st._gruppen["A"] = [2]
        self.st.notify_groups_changed()
        d = _frame(self.om, self.fake)
        self.assertEqual(d[19], 0)


class _FakeState:
    def __init__(self):
        self.output_manager = OutputManager()
        self.aktiv = {}
        self.global_calls = []
        self.output_manager.set_blackout = self.global_calls.append

    def set_target_blackout(self, slot, fids=(), groups=()):
        self.aktiv[slot] = (list(fids), list(groups))

    def clear_target_blackout(self, slot):
        self.aktiv.pop(slot, None)


class VCButtonBlackoutZielTest(unittest.TestCase):

    def setUp(self):
        self.fake = _FakeState()
        self._orig = app_state_mod.get_state
        app_state_mod.get_state = lambda: self.fake
        self.addCleanup(setattr, app_state_mod, "get_state", self._orig)

    def _btn(self, fids=(), groups=()):
        b = VCButton("BO")
        b.action = ButtonAction.BLACKOUT
        b.blackout_fids = list(fids)
        b.blackout_groups = list(groups)
        return b

    def test_taste_mit_ziel_setzt_und_loest_nur_ihren_slot(self):
        b = self._btn(fids=[5], groups=["A"])
        self.addCleanup(b.deleteLater)
        b._trigger_primary(True)
        self.assertEqual(self.fake.aktiv, {id(b): ([5], ["A"])})
        self.assertEqual(self.fake.global_calls, [])
        b._trigger_primary(False)
        self.assertEqual(self.fake.aktiv, {})

    def test_taste_ohne_ziel_global_wie_bisher(self):
        b = self._btn()
        self.addCleanup(b.deleteLater)
        b._trigger_primary(True)
        b._trigger_primary(False)
        self.assertEqual(self.fake.global_calls, [True, False])
        self.assertEqual(self.fake.aktiv, {})

    def test_speichern_laden_behaelt_ziel(self):
        b = self._btn(fids=[3, 7], groups=["Bühne links"])
        self.addCleanup(b.deleteLater)
        d = json.loads(json.dumps(b.to_dict()))
        b2 = VCButton("X")
        self.addCleanup(b2.deleteLater)
        b2.apply_dict(d)
        self.assertEqual(b2.action, ButtonAction.BLACKOUT)
        self.assertEqual(b2.blackout_fids, [3, 7])
        self.assertEqual(b2.blackout_groups, ["Bühne links"])
        self.assertTrue(b2.has_blackout_target())

    def test_altes_layout_ohne_feld_ist_global(self):
        b = VCButton("X")
        self.addCleanup(b.deleteLater)
        b.apply_dict({"type": "VCButton", "action": "Blackout", "caption": "BO"})
        self.assertEqual(b.blackout_fids, [])
        self.assertEqual(b.blackout_groups, [])
        self.assertFalse(b.has_blackout_target())
        b._trigger_primary(True)
        self.assertEqual(self.fake.global_calls, [True])

    def test_taste_loeschen_gibt_frei(self):
        b = self._btn(groups=["A"])
        b._trigger_primary(True)
        self.assertIn(id(b), self.fake.aktiv)
        b.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertEqual(self.fake.aktiv, {})

    def test_ansichtswechsel_haelt_dunkel(self):
        # Review-Befund 3: Hauptansicht wechselt (QStackedWidget) bzw. Fenster
        # minimiert, waehrend das MIDI-Pad gehalten ist -> bleibt dunkel, wie
        # beim globalen Blackout.
        from PySide6.QtWidgets import QStackedWidget, QWidget
        stack = QStackedWidget()
        self.addCleanup(stack.deleteLater)
        seite = QWidget()
        b = self._btn(groups=["A"])
        b.setParent(seite)
        stack.addWidget(seite)
        stack.addWidget(QWidget())
        stack.show()
        b._pressed = True
        b._trigger(True)
        stack.setCurrentIndex(1)
        self.assertFalse(b.isVisible())
        self.assertIn(id(b), self.fake.aktiv)
        stack.hide()
        self.assertIn(id(b), self.fake.aktiv)

    def test_bankwechsel_gibt_frei(self):
        from PySide6.QtCore import QPoint
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        canvas = VCCanvas()
        self.addCleanup(canvas.deleteLater)
        b = canvas._add_widget("VCButton", QPoint(10, 10))
        b.action = ButtonAction.BLACKOUT
        b.blackout_groups = ["A"]
        b.bank = 0
        canvas.set_active_bank(0)
        b._pressed = True
        b._trigger(True)
        self.assertIn(id(b), self.fake.aktiv)
        canvas.set_active_bank(1)
        self.assertEqual(self.fake.aktiv, {})

    def test_show_laden_gibt_frei(self):
        b = self._btn(groups=["A"])
        self.addCleanup(b.deleteLater)
        b._trigger_primary(True)
        b.apply_dict(b.to_dict())
        self.assertEqual(self.fake.aktiv, {})

    def test_dialog_ziel_auswahl(self):
        from PySide6.QtWidgets import QDialog
        from src.ui.virtualconsole.target_list_editor import BlackoutTargetEditor
        b = self._btn(fids=[9])
        self.addCleanup(b.deleteLater)

        def _exec(dlg):
            ed = dlg.findChild(BlackoutTargetEditor)
            assert ed is not None, "Blackout-Ziel fehlt im Button-Dialog"
            self.assertEqual(ed.fids(), [9])
            ed.set_targets(["g:A", "f:2", "f:2", "kaputt"])
            return QDialog.DialogCode.Accepted

        orig = QDialog.exec
        QDialog.exec = _exec
        try:
            b._open_properties()
        finally:
            QDialog.exec = orig
        self.assertEqual(b.blackout_groups, ["A"])
        self.assertEqual(b.blackout_fids, [2])

    def test_andere_aktion_verwirft_ziel(self):
        b = self._btn(fids=[9])
        self.addCleanup(b.deleteLater)
        S = b._build_settings(b, live=False)
        combo = S["action_combo"]
        combo.setCurrentIndex(combo.findData(ButtonAction.TOGGLE.value))
        S["apply"]()
        self.assertEqual(b.blackout_fids, [])


if __name__ == "__main__":
    unittest.main()
