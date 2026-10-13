"""VCB-46: Haken je Snap-Taste „übersteuert laufende Dimmer-Effekte“.

Befund: Ein Dimmer-Wert aus einer Snap-Taste (Programmer-Schicht) wird
uebergangen, sobald ein laufender Effekt den Dimmer der Lampe treibt — eine
Blinder- oder „Strobe Weiß“-Taste als Snap kommt gegen ein Dimmer-Lauflicht
nicht durch.

Mit dem Haken gewinnt der DIMMER des Snaps an genau seinen Lampen, solange die
Taste aktiv ist. Farbe bleibt getrennt und unberuehrt; Master, Fader, Blackout
und NOT-AUS behalten das letzte Wort; ohne Haken bleibt alles wie bisher und
die Show byte-gleich.

Drei Teile: der Renderer, die Taste (Register, Speichern, Eigenschaften) und
beides zusammen.
"""
import json
import os
import threading as _t
import types as _ty
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QCheckBox, QWidget

import src.core.app_state as A
from src.core.app_state import AppState, get_state
from src.core.dmx.output_manager import OutputManager
from src.core.dmx.universe import Universe
from src.core.engine.snap_library import get_snap_library
from src.ui.virtualconsole.vc_button import (ButtonAction, VCButton,
                                             dimmer_override_abgleich,
                                             forget_snap_claims)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class _Ch:
    def __init__(self, attr, num, default=0):
        self.attribute = attr
        self.channel_number = num
        self.default_value = default


class _Fx:
    def __init__(self, fid, universe, address):
        self.fid = fid
        self.universe = universe
        self.address = address


class _FM:
    """Effekt-Ersatz: schreibt vorgegebene {adresse: wert} (wie ein Lauflicht)."""

    def __init__(self):
        self.writes: dict[int, int] = {}

    def tick(self, universes, patch_cache, dt):
        u = universes.get(1)
        if u is None:
            return
        for addr, val in self.writes.items():
            u.set_channel(addr, val)


def _rgb_mit_dimmer():
    return [_Ch("intensity", 1), _Ch("color_r", 2), _Ch("color_g", 3),
            _Ch("color_b", 4)]


# Drei Lampen mit eigenem Dimmer + RGB (7, 8, 9) und eine reine RGB-Lampe (5).
_FIXTURES = {
    7: (10, _rgb_mit_dimmer()),
    8: (20, _rgb_mit_dimmer()),
    9: (30, _rgb_mit_dimmer()),
    5: (40, [_Ch("color_r", 1), _Ch("color_g", 2), _Ch("color_b", 3)]),
}
D7, R7, G7, B7 = 10, 11, 12, 13
D8, R8 = 20, 21
D9 = 30
R5 = 40


def _make_state(om=None):
    st = AppState.__new__(AppState)
    st.universes = om.universes if om is not None else {1: Universe(1)}
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = _FM()
    st._patch_cache = [_Fx(fid, 1, addr) for fid, (addr, _c) in _FIXTURES.items()]
    st._fix_index = {}
    st._default_frame = {}
    st._commit_spans = {}
    st._patched_set = {}
    st._engine_extra_prev = {}
    st.submaster_level = 1.0
    st.fixture_dimmers = {}
    st.selected_fids = []
    st.programmer_focus = None
    st._prog_lock = _t.RLock()
    st.output_manager = om if om is not None else _ty.SimpleNamespace(
        set_gm_address_mask=lambda m: None)
    kanaele = {fid: ch for fid, (_a, ch) in _FIXTURES.items()}
    A.get_channels_for_patched = lambda f: kanaele[f.fid]
    st._rebuild_render_plan()
    return st


# Lauflicht ueber 7, 8, 9: 7 gerade halb, 8 gerade DUNKEL, 9 hell.
_LAUFLICHT = {D7: 40, D8: 0, D9: 200}


class RendererTest(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched
        self.st = _make_state()
        self.st.function_manager.writes = dict(_LAUFLICHT)

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _v(self, addr):
        return self.st.universes[1].get_channel(addr)

    def _bild(self):
        self.st._render_frame(0.02)
        return self.st.universes[1].get_all()[:45]

    # ── ohne Haken: wie bisher ───────────────────────────────────────────────

    def test_ohne_haken_behaelt_der_effekt_den_dimmer(self):
        self.st.programmer = {7: {"intensity": 255}, 8: {"intensity": 255}}
        self.st._render_frame(0.02)
        self.assertEqual((self._v(D7), self._v(D8), self._v(D9)), (40, 0, 200))

    def test_ohne_haken_ist_das_bild_gleich_wie_ohne_das_neue_feld(self):
        """Stub ohne ``snap_dimmer_override`` (alter Stand) und leeres Feld
        liefern dasselbe Bild — die neue Stelle kostet ohne Haken nichts."""
        self.st.programmer = {7: {"intensity": 255, "color_r": 200}}
        ohne_feld = self._bild()
        self.st.snap_dimmer_override = {}
        self.assertEqual(self._bild(), ohne_feld)
        self.st.set_snap_dimmer_override({})
        self.assertEqual(self._bild(), ohne_feld)
        self.assertEqual(ohne_feld[D7 - 1], 40)

    # ── mit Haken ────────────────────────────────────────────────────────────

    def test_mit_haken_gewinnt_der_snap_dimmer_an_genau_seinen_lampen(self):
        self.st.programmer = {7: {"intensity": 255}, 8: {"intensity": 255}}
        self.st.set_snap_dimmer_override({7: {"intensity": 255},
                                          8: {"intensity": 255}})
        self.st._render_frame(0.02)
        self.assertEqual(self._v(D7), 255, "Blinder kommt durch")
        self.assertEqual(self._v(D8), 255, "auch auf der gerade dunklen Lampe")
        self.assertEqual(self._v(D9), 200, "Lampe 9 gehoert nicht zum Snap")

    def test_snap_dimmer_null_gewinnt_auch(self):
        """Uebersteuern heisst „der Wert des Snaps gilt“ — auch ein dunkler."""
        self.st.programmer = {9: {"intensity": 0}}
        self.st.set_snap_dimmer_override({9: {"intensity": 0}})
        self.st._render_frame(0.02)
        self.assertEqual(self._v(D9), 0)
        self.assertEqual(self._v(D7), 40)

    def test_farbe_bleibt_unberuehrt_und_getrennt(self):
        """Der Haken fasst nur den Dimmer an: eine vom Effekt getriebene Farbe
        bleibt beim Effekt, eine nicht getriebene bleibt, was sie war — die
        Farbe zieht nicht mit, und der Dimmer zieht keine Farbe nach."""
        self.st.function_manager.writes.update({R7: 100})      # Farb-Effekt auf 7
        self.st.programmer = {7: {"intensity": 255, "color_r": 10, "color_g": 20}}
        ohne = self._bild()
        self.st.set_snap_dimmer_override({7: {"intensity": 255}})
        mit = self._bild()
        self.assertEqual(mit[D7 - 1], 255)
        self.assertEqual(mit[R7 - 1], 100, "Farbe des Effekts bleibt")
        self.assertEqual(mit[G7 - 1], 20, "freie Farbe wie ohne Haken")
        self.assertEqual(mit[B7 - 1], 0, "nichts wird dazugemischt")
        anders = [i + 1 for i in range(len(mit)) if mit[i] != ohne[i]]
        self.assertEqual(anders, [D7], "nur der eine Dimmer-Kanal aendert sich")

    def test_reiner_dimmer_snap_macht_keine_farbe(self):
        self.st.programmer = {7: {"intensity": 255}}
        self.st.set_snap_dimmer_override({7: {"intensity": 255}})
        self.st._render_frame(0.02)
        self.assertEqual((self._v(R7), self._v(G7), self._v(B7)), (0, 0, 0))

    def test_nach_dem_ausschalten_ist_der_effekt_wieder_da(self):
        self.st.programmer = {7: {"intensity": 255}}
        self.st.set_snap_dimmer_override({7: {"intensity": 255}})
        self.st._render_frame(0.02)
        self.assertEqual(self._v(D7), 255)
        # Taste aus: Wert aus dem Programmer, Haken-Eintrag weg.
        self.st.programmer = {}
        self.st.set_snap_dimmer_override({})
        self.st.function_manager.writes[D7] = 90          # das Lauflicht lief weiter
        self.st._render_frame(0.02)
        self.assertEqual(self._v(D7), 90)

    def test_programmer_geleert_haken_eintrag_noch_da_effekt_gewinnt(self):
        """„Programmer leeren“ nimmt den Wert weg — ein noch gemeldeter Eintrag
        darf dann nichts mehr erzwingen."""
        self.st.set_snap_dimmer_override({7: {"intensity": 255}})
        self.st.programmer = {}
        self.st._render_frame(0.02)
        self.assertEqual(self._v(D7), 40)

    def test_fremder_wert_im_programmer_uebersteuert_nicht(self):
        """Steht dort nicht mehr der Wert der Taste (jemand hat den Dimmer von
        Hand gezogen), gilt wieder die alte Regel: der Effekt behaelt ihn."""
        self.st.set_snap_dimmer_override({7: {"intensity": 255}})
        self.st.programmer = {7: {"intensity": 128}}
        self.st._render_frame(0.02)
        self.assertEqual(self._v(D7), 40)

    def test_ohne_laufenden_dimmer_effekt_aendert_der_haken_nichts(self):
        self.st.function_manager.writes = {}
        self.st.programmer = {7: {"intensity": 180}}
        ohne = self._bild()
        self.st.set_snap_dimmer_override({7: {"intensity": 180}})
        self.assertEqual(self._bild(), ohne)
        self.assertEqual(ohne[D7 - 1], 180)

    def test_lampe_ohne_eigenen_dimmer_bleibt_wie_bisher(self):
        """Grenze: eine reine RGB-Lampe hat keinen Dimmer-Kanal, den der Haken
        uebersteuern koennte — dort aendert sich nichts."""
        self.st.function_manager.writes = {R5: 120}
        self.st.programmer = {5: {"intensity": 255}}
        ohne = self._bild()
        self.st.set_snap_dimmer_override({5: {"intensity": 255}})
        self.assertEqual(self._bild(), ohne)

    def test_nur_dimmer_attribute_werden_angenommen(self):
        self.st.set_snap_dimmer_override({7: {"shutter": 200, "color_r": 255,
                                              "intensity": 255, "dimmer#1": 9},
                                          "x": {"intensity": 1},
                                          8: {"strobe": 255}})
        self.assertEqual(self.st.snap_dimmer_override,
                         {7: {"intensity": 255, "dimmer#1": 9}})

    # ── Master, Fader, NOT-AUS behalten das letzte Wort ──────────────────────

    def test_submaster_und_geraete_dimmer_wirken_weiter(self):
        self.st.programmer = {7: {"intensity": 255}, 8: {"intensity": 255}}
        self.st.set_snap_dimmer_override({7: {"intensity": 255},
                                          8: {"intensity": 255}})
        self.st.submaster_level = 0.5
        self.st.fixture_dimmers = {8: 0.0}                # Gruppen-Fader ganz zu
        self.st._render_frame(0.02)
        self.assertEqual(self._v(D7), 127)
        self.assertEqual(self._v(D8), 0)

    def test_laser_not_aus_bleibt_dunkel(self):
        self.st.programmer = {7: {"intensity": 255}}
        self.st.set_snap_dimmer_override({7: {"intensity": 255}})
        self.st._laser_estop_addrs = {1: frozenset({D7})}
        self.st.laser_estop_active = True
        self.st._render_frame(0.02)
        self.assertEqual(self._v(D7), 0)

    def test_intensity_reiter_gewinnt_weiter_wie_bisher(self):
        """Die vorhandene Ausnahme (Reiter Intensity + Lampe gewaehlt) und der
        Haken benutzen denselben Weg und stoeren einander nicht."""
        self.st.programmer = {7: {"intensity": 128}, 8: {"intensity": 255}}
        self.st.selected_fids = [7]
        self.st.programmer_focus = "Intensity"
        self.st.set_snap_dimmer_override({8: {"intensity": 255}})
        self.st._render_frame(0.02)
        self.assertEqual((self._v(D7), self._v(D8), self._v(D9)), (128, 255, 200))


class SendePfadTest(unittest.TestCase):
    """Blackout und Grand Master liegen hinter dem Renderer im Sendepfad."""

    def setUp(self):
        self._orig = A.get_channels_for_patched
        self.om = OutputManager()
        self.om.add_universe(1)
        self.om.grand_master = 1.0
        self.st = _make_state(self.om)
        self.st.function_manager.writes = dict(_LAUFLICHT)
        self.st.programmer = {7: {"intensity": 255}}
        self.st.set_snap_dimmer_override({7: {"intensity": 255}})

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _gesendet(self):
        self.st._render_frame(0.02)
        self.om._send_all()
        return self.om._display_frame[1]

    def test_ohne_blackout_kommt_der_blinder_an(self):
        self.assertEqual(self._gesendet()[D7 - 1], 255)

    def test_blackout_bleibt_dunkel(self):
        self.om.set_blackout(True)
        try:
            bild = self._gesendet()
            self.assertEqual(bild[D7 - 1], 0)
            self.assertEqual(bild[D9 - 1], 0)
        finally:
            self.om.set_blackout(False)

    def test_grand_master_dimmt_auch_den_uebersteuernden_snap(self):
        self.om.grand_master = 0.0
        self.assertEqual(self._gesendet()[D7 - 1], 0)
        self.om.grand_master = 0.5
        self.assertIn(self._gesendet()[D7 - 1], (127, 128))


# ── die Taste ────────────────────────────────────────────────────────────────

FID_A, FID_B = 9101, 9102


class TasteTest(unittest.TestCase):
    def setUp(self):
        _app()
        self.state = get_state()
        self.state.clear_programmer()
        self.state.set_snap_dimmer_override({})
        self.lib = get_snap_library()
        self._sids: list[int] = []
        self._btns: list[VCButton] = []

    def tearDown(self):
        for btn in self._btns:
            forget_snap_claims(btn)
        self.state.clear_programmer()
        self.state.set_snap_dimmer_override({})
        for sid in self._sids:
            try:
                self.lib.remove_snap(sid)
            except Exception:
                pass

    def _taste(self, werte: dict, *, haken: bool, mode: str = "flash") -> VCButton:
        snap = self.lib.add_snap(f"TEST_vcb46_{len(self._sids)}", "", werte)
        self._sids.append(snap.id)
        btn = VCButton()
        btn.action = ButtonAction.LIBRARY_SNAP
        btn.snap_id = snap.id
        btn.snap_mode = mode
        btn.snap_dimmer_override = haken
        self._btns.append(btn)
        return btn

    def _ovr(self):
        return self.state.snap_dimmer_override

    def test_vorgabe_ist_aus(self):
        self.assertIs(VCButton().snap_dimmer_override, False)

    def test_ohne_haken_meldet_die_taste_nichts(self):
        btn = self._taste({FID_A: {"intensity": 255}}, haken=False)
        btn._apply_library_snap()
        self.assertEqual(self.state.get_programmer_value(FID_A, "intensity"), 255)
        self.assertEqual(self._ovr(), {})
        btn._restore_library_snap()
        self.assertEqual(self._ovr(), {})

    def test_mit_haken_meldet_die_taste_nur_ihre_dimmer(self):
        btn = self._taste({FID_A: {"intensity": 255, "color_r": 255, "shutter": 180},
                           FID_B: {"color_b": 255}}, haken=True)
        btn._apply_library_snap()
        self.assertEqual(self._ovr(), {FID_A: {"intensity": 255}},
                         "nur Dimmer, nur Lampen mit Dimmer-Wert im Snap")
        btn._restore_library_snap()
        self.assertEqual(self._ovr(), {}, "nach dem Loslassen faellt alles zurueck")
        self.assertIsNone(self.state.get_programmer_value(FID_A, "intensity"))

    def test_umschalt_taste_haelt_bis_zum_zweiten_druck(self):
        btn = self._taste({FID_A: {"dimmer": 200}}, haken=True, mode="toggle")
        btn._trigger(True)
        self.assertEqual(self._ovr(), {FID_A: {"dimmer": 200}})
        btn._trigger(False)                      # Loslassen aendert nichts
        self.assertEqual(self._ovr(), {FID_A: {"dimmer": 200}})
        btn._trigger(True)
        self.assertEqual(self._ovr(), {})

    def test_zuletzt_gedrueckt_bestimmt_auch_den_haken(self):
        """Zwei Tasten auf demselben Dimmer: es gilt die oberste im Stapel —
        ihr Wert UND ihr Haken. Beim Loslassen geht beides an die vorige."""
        mit = self._taste({FID_A: {"intensity": 255}}, haken=True)
        ohne = self._taste({FID_A: {"intensity": 80}}, haken=False)
        mit._apply_library_snap()
        self.assertEqual(self._ovr(), {FID_A: {"intensity": 255}})
        ohne._apply_library_snap()
        self.assertEqual(self._ovr(), {}, "die Taste ohne Haken liegt oben")
        ohne._restore_library_snap()
        self.assertEqual(self.state.get_programmer_value(FID_A, "intensity"), 255)
        self.assertEqual(self._ovr(), {FID_A: {"intensity": 255}})
        mit._restore_library_snap()
        self.assertEqual(self._ovr(), {})

    def test_abmelden_der_taste_nimmt_den_haken_mit(self):
        btn = self._taste({FID_A: {"intensity": 255}}, haken=True, mode="set")
        btn._trigger(True)
        self.assertEqual(self._ovr(), {FID_A: {"intensity": 255}})
        forget_snap_claims(btn)                    # Show neu geladen / Taste weg
        self.assertEqual(self._ovr(), {})

    def test_haken_nachtraeglich_gesetzt_wirkt_nach_dem_abgleich(self):
        btn = self._taste({FID_A: {"intensity": 255}}, haken=False, mode="toggle")
        btn._trigger(True)
        self.assertEqual(self._ovr(), {})
        btn.snap_dimmer_override = True
        dimmer_override_abgleich(halter=btn)       # wie der Eigenschaften-Dialog
        self.assertEqual(self._ovr(), {FID_A: {"intensity": 255}})

    # ── der Vorrang verfaellt mit dem Wert / mit der Taste ───────────────────

    def test_programmer_leeren_bei_gehaltener_taste_nimmt_den_vorrang(self):
        """Gegenpruefung: nach „Programmer leeren“ blieb der Eintrag der noch
        gehaltenen Taste stehen — ein danach von Hand gezogener, exakt gleicher
        Dimmerwert uebersteuerte den Effekt, obwohl er nicht von der Taste kam."""
        btn = self._taste({FID_A: {"intensity": 255},
                           FID_B: {"intensity": 255}}, haken=True)
        btn._apply_library_snap()                  # gehalten
        self.assertEqual(self._ovr(), {FID_A: {"intensity": 255},
                                       FID_B: {"intensity": 255}})
        self.state.clear_programmer()
        self.assertEqual(self._ovr(), {}, "mit dem Wert geht der Vorrang")
        self.state.set_programmer_value(FID_A, "intensity", 255)   # von Hand
        self.assertEqual(self._ovr(), {}, "ein Handwert uebersteuert nicht")
        # Auch eine ANDERE Taste, die jetzt abgleicht, belebt ihn nicht wieder.
        andere = self._taste({9103: {"intensity": 10}}, haken=True)
        andere._apply_library_snap()
        self.assertEqual(self._ovr(), {9103: {"intensity": 10}})
        andere._restore_library_snap()
        btn._restore_library_snap()                # spaetes Loslassen
        self.assertEqual(self._ovr(), {})

    def test_leeren_eines_geraets_nimmt_nur_dessen_vorrang(self):
        btn = self._taste({FID_A: {"intensity": 255},
                           FID_B: {"intensity": 255}}, haken=True)
        btn._apply_library_snap()
        self.state.clear_programmer(FID_A)
        self.assertEqual(self._ovr(), {FID_B: {"intensity": 255}})

    def test_ueberschriebener_wert_verliert_den_vorrang_dauerhaft(self):
        btn = self._taste({FID_A: {"intensity": 255}}, haken=True)
        btn._apply_library_snap()
        self.state.set_programmer_value(FID_A, "intensity", 90)    # von Hand
        self.assertEqual(self._ovr(), {})
        self.state.set_programmer_value(FID_A, "intensity", 255)   # wieder hoch
        self.assertEqual(self._ovr(), {}, "kommt nicht von der Taste")
        self.state.clear_programmer_value(FID_A, "intensity")
        self.assertEqual(self._ovr(), {})

    def test_erneuter_druck_stellt_den_vorrang_wieder_her(self):
        btn = self._taste({FID_A: {"intensity": 255}}, haken=True)
        btn._apply_library_snap()
        self.state.clear_programmer()
        self.assertEqual(self._ovr(), {})
        btn._apply_library_snap()                  # neu gedrueckt
        self.assertEqual(self._ovr(), {FID_A: {"intensity": 255}})

    def _auf_flaeche(self, btn):
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        canvas = VCCanvas()
        self.addCleanup(canvas.deleteLater)
        btn.setParent(canvas)
        return canvas

    def test_loeschen_einer_aktiven_taste_nimmt_den_vorrang(self):
        """Gegenpruefung: eine AKTIVE Taste mit Haken wird geloescht — ihr
        Eintrag blieb stehen (das Python-Objekt lebt weiter, der Halter-Stapel
        auch). Der Wert bleibt im Programmer, aber ohne Vorrang."""
        btn = self._taste({FID_A: {"intensity": 255}}, haken=True, mode="toggle")
        canvas = self._auf_flaeche(btn)
        btn._trigger(True)
        self.assertEqual(self._ovr(), {FID_A: {"intensity": 255}})
        canvas._remove_widget(btn)
        self.assertEqual(self._ovr(), {})
        self.state.set_programmer_value(FID_A, "intensity", 255)   # von Hand
        dimmer_override_abgleich()
        self.assertEqual(self._ovr(), {})

    def test_loeschen_eines_rahmens_meldet_auch_seine_tasten_ab(self):
        from src.ui.virtualconsole.vc_frame import VCFrame
        btn = self._taste({FID_A: {"intensity": 255}}, haken=True, mode="toggle")
        canvas = self._auf_flaeche(btn)
        rahmen = VCFrame(parent=canvas)
        btn.setParent(rahmen)
        btn._trigger(True)
        self.assertEqual(self._ovr(), {FID_A: {"intensity": 255}})
        canvas._remove_widget(rahmen)
        self.assertEqual(self._ovr(), {})

    def test_konsole_neu_laden_nimmt_den_vorrang(self):
        """Show-Wechsel / Rueckgaengig in der Konsole: alle Tasten werden
        abgebaut und neu angelegt — die neuen sind nicht aktiv."""
        btn = self._taste({FID_A: {"intensity": 255}}, haken=True, mode="toggle")
        canvas = self._auf_flaeche(btn)
        btn._trigger(True)
        self.assertEqual(self._ovr(), {FID_A: {"intensity": 255}})
        canvas.from_dict({"widgets": []})
        self.assertEqual(self._ovr(), {})

    # ── Speichern ────────────────────────────────────────────────────────────

    def test_ohne_haken_bleibt_die_gespeicherte_taste_byte_gleich(self):
        btn = self._taste({FID_A: {"intensity": 255}}, haken=False)
        d = btn.to_dict()
        self.assertNotIn("snap_dimmer_override", d)
        vorher = json.dumps(d, sort_keys=True, ensure_ascii=False)
        neu = VCButton()
        neu.apply_dict(json.loads(vorher))
        self._btns.append(neu)
        self.assertIs(neu.snap_dimmer_override, False)
        self.assertEqual(json.dumps(neu.to_dict(), sort_keys=True,
                                    ensure_ascii=False), vorher)

    def test_mit_haken_wird_gespeichert_und_geladen(self):
        btn = self._taste({FID_A: {"intensity": 255}}, haken=True)
        d = btn.to_dict()
        self.assertIs(d["snap_dimmer_override"], True)
        neu = VCButton()
        neu.apply_dict(json.loads(json.dumps(d)))
        self._btns.append(neu)
        self.assertIs(neu.snap_dimmer_override, True)
        self.assertEqual(neu.to_dict(), d)

    def test_alte_show_ohne_das_feld_laedt_mit_haken_aus(self):
        btn = self._taste({FID_A: {"intensity": 255}}, haken=True)
        d = btn.to_dict()
        d.pop("snap_dimmer_override")
        btn.apply_dict(d)
        self.assertIs(btn.snap_dimmer_override, False)

    # ── Eigenschaften ────────────────────────────────────────────────────────

    def _haken_feld(self, S) -> QCheckBox:
        for key, _titel, _zu, _prefs, rows in S["sections"]:
            if key != "target":
                continue
            labels = [lbl for lbl, _w in rows]
            self.assertLess(labels.index("Tasten-Modus (Snap):"),
                            labels.index("Dimmer (Snap):"))
            self.assertEqual(labels.index("Dimmer (Snap):"),
                             labels.index("Tasten-Modus (Snap):") + 1,
                             "der Haken steht direkt beim Tasten-Modus")
            for lbl, w in rows:
                if lbl == "Dimmer (Snap):":
                    return w
        self.fail("Zeile „Dimmer (Snap):“ fehlt")

    def test_haken_steht_bei_den_snap_optionen_und_schreibt(self):
        btn = self._taste({FID_A: {"intensity": 255}}, haken=False)
        host = QWidget()
        try:
            S = btn._build_settings(host, live=False)
            feld = self._haken_feld(S)
            self.assertIsInstance(feld, QCheckBox)
            self.assertEqual(feld.text(), "übersteuert laufende Dimmer-Effekte")
            self.assertFalse(feld.isChecked())
            feld.setChecked(True)
            S["apply"]()
            self.assertIs(btn.snap_dimmer_override, True)
            self.assertIs(btn.to_dict()["snap_dimmer_override"], True)
            feld.setChecked(False)
            S["apply"]()
            self.assertIs(btn.snap_dimmer_override, False)
        finally:
            host.deleteLater()

    def test_haken_nur_bei_snap_tasten_sichtbar_und_wirksam(self):
        btn = self._taste({FID_A: {"intensity": 255}}, haken=True)
        host = QWidget()
        try:
            S = btn._build_settings(host, live=False)
            feld = self._haken_feld(S)
            self.assertTrue(feld.isChecked())
            sichtbar = {}
            S["update_visibility"](lambda w, an: sichtbar.__setitem__(id(w), an))
            self.assertTrue(sichtbar[id(feld)])
            combo = S["action_combo"]
            combo.setCurrentIndex(combo.findData(ButtonAction.FUNCTION_TOGGLE.value))
            S["update_visibility"](lambda w, an: sichtbar.__setitem__(id(w), an))
            self.assertFalse(sichtbar[id(feld)])
            S["apply"]()
            self.assertIs(btn.snap_dimmer_override, False,
                          "kein unsichtbarer Haken an einer Nicht-Snap-Taste")
            self.assertNotIn("snap_dimmer_override", btn.to_dict())
        finally:
            host.deleteLater()


# ── beides zusammen ──────────────────────────────────────────────────────────

class ZusammenTest(unittest.TestCase):
    """Echte Taste, echter Renderer: Blinder-Snap gegen ein Dimmer-Lauflicht."""

    def setUp(self):
        _app()
        self._orig_ch = A.get_channels_for_patched
        self._orig_state = A.get_state
        st = _make_state()
        st.function_manager.writes = dict(_LAUFLICHT)
        st.set_programmer_value = (
            lambda fid, attr, val, *a, **k: st.programmer.setdefault(int(fid), {})
            .__setitem__(attr, int(val)))
        st.get_programmer_value = (
            lambda fid, attr, *a, **k: st.programmer.get(int(fid), {}).get(attr))

        def _weg(fid, attr):
            st.programmer.get(int(fid), {}).pop(attr, None)
            if not st.programmer.get(int(fid)):
                st.programmer.pop(int(fid), None)

        st.clear_programmer_value = _weg
        self.st = st
        A.get_state = lambda: st
        self.lib = get_snap_library()
        self._sids: list[int] = []
        self._btns: list[VCButton] = []

    def tearDown(self):
        for btn in self._btns:
            forget_snap_claims(btn)
        A.get_state = self._orig_state
        A.get_channels_for_patched = self._orig_ch
        for sid in self._sids:
            try:
                self.lib.remove_snap(sid)
            except Exception:
                pass

    def _blinder(self, haken: bool) -> VCButton:
        snap = self.lib.add_snap("TEST_vcb46_blinder", "", {
            7: {"intensity": 255, "color_r": 255, "color_g": 255, "color_b": 255},
            8: {"intensity": 255, "color_r": 255, "color_g": 255, "color_b": 255}})
        self._sids.append(snap.id)
        btn = VCButton()
        btn.action = ButtonAction.LIBRARY_SNAP
        btn.snap_id = snap.id
        btn.snap_mode = "flash"
        btn.snap_dimmer_override = haken
        self._btns.append(btn)
        return btn

    def _dimmer(self):
        self.st._render_frame(0.02)
        u = self.st.universes[1]
        return u.get_channel(D7), u.get_channel(D8), u.get_channel(D9)

    def test_ohne_haken_kommt_der_blinder_nicht_durch(self):
        btn = self._blinder(haken=False)
        self.assertEqual(self._dimmer(), (40, 0, 200))
        btn._trigger(True)
        self.assertEqual(self._dimmer(), (40, 0, 200), "wie bisher")
        self.assertEqual(self.st.universes[1].get_channel(R7), 255,
                         "die Farbe des Snaps kam schon immer durch")
        btn._trigger(False)
        self.assertEqual(self._dimmer(), (40, 0, 200))

    def test_mit_haken_gewinnt_der_blinder_und_gibt_sauber_zurueck(self):
        btn = self._blinder(haken=True)
        self.assertEqual(self._dimmer(), (40, 0, 200))
        btn._trigger(True)
        self.assertEqual(self._dimmer(), (255, 255, 200),
                         "Blinder an 7 und 8, Lampe 9 laeuft weiter")
        self.st.function_manager.writes.update({D7: 0, D8: 180})   # Lauflicht wandert
        self.assertEqual(self._dimmer(), (255, 255, 200), "solange gehalten")
        btn._trigger(False)
        self.assertEqual(self._dimmer(), (0, 180, 200), "Effekt wieder da")
        self.assertEqual(self.st.programmer, {}, "nichts bleibt im Programmer")
        self.assertEqual(self.st.snap_dimmer_override, {})
        self.assertEqual(self.st.universes[1].get_channel(R7), 0)


if __name__ == "__main__":
    unittest.main()
