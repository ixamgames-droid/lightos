"""FM-52: „Rückgängig" im Programmer nimmt die letzte PROGRAMMER-Aenderung zurueck.

Bis FM-52 rief der Knopf den globalen Undo-Stapel. Programmer-Werte landen dort
nie (``set_programmer_value(undoable=False)`` ist Standard) — der Knopf nahm
deshalb still die letzte Patch-/Geraete-Aenderung zurueck: Regler hoch,
„Rückgängig", und das zuletzt gepatchte Geraet war weg.

Soll: der Programmer hat einen eigenen Verlauf. Ein Regler-Zug, ein Knopfdruck
(Hervorheben, Kachel, Einfuegen …) und ein Loeschen sind je EIN Schritt; der
Patch bleibt unberuehrt; Neue Show/Show oeffnen leeren den Verlauf.

Echter Weg: eingebaute Profile, echter AppState, echte ProgrammerView.
"""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                         # noqa: E402
from sqlalchemy import select                                       # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

from src.core.app_state import get_state                            # noqa: E402
from src.core.database.fixture_db import engine, ensure_builtins    # noqa: E402
from src.core.database.models import FixtureProfile, PatchedFixture  # noqa: E402
from src.core.show.show_file import load_show, reset_show, save_show  # noqa: E402
from src.core.undo import get_undo_stack                            # noqa: E402

_app = QApplication.instance() or QApplication([])
BALKEN_MODUS = "154-Kanal 48 Zonen RGB + 8x Weiss"
PAR_ADR = 200


def _pid(short):
    with Session(engine()) as s:
        return s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first()


def _par(fid=2, adr=PAR_ADR, label="PAR"):
    return PatchedFixture(fid=fid, label=label, fixture_profile_id=_pid("ZQ01424"),
                          mode_name="8-Kanal RGBW", universe=1, address=adr,
                          channel_count=8, fixture_type="par")


class _Basis(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        ensure_builtins()

    def setUp(self):
        reset_show()
        self.st = get_state()
        self.stack = get_undo_stack()
        self.addCleanup(self.stack.clear)
        self.addCleanup(self.st.set_selected_fids, [])
        self.addCleanup(reset_show)

    def _view(self):
        from src.ui.views.programmer_view import ProgrammerView
        v = ProgrammerView()
        self.addCleanup(v.deleteLater)
        return v

    def _waehle(self, v, fids):
        self.st.set_selected_cells([str(f) for f in fids])
        v._sync_follow_selection()

    def _slider(self, v, attr):
        from src.ui.views.programmer_view import AttributeSlider
        for s in v.findChildren(AttributeSlider):
            if s._channel.attribute == attr:
                return s
        self.fail(f"kein Regler fuer {attr}")

    def _kanal(self, n):
        return self.st.output_manager.universes[1].get_channel(n)

    def _ausgabe(self):
        return [self._kanal(n) for n in range(1, 513)]

    def _prog(self, fid):
        return dict(self.st.programmer.get(fid, {}))

    @property
    def verlauf(self):
        return self.st.programmer_verlauf


class ReglerRueckgaengigTest(_Basis):
    """(a) + (b) + (c): Regler -> Rueckgaengig -> Wiederholen."""

    def test_a_rueckgaengig_nimmt_den_reglerwert_zurueck_nicht_den_patch(self):
        # Gegenprobe: ein ruecknehmbarer Patch-Schritt liegt im GLOBALEN Stapel.
        self.st.add_fixture(_par(), undoable=True)
        self.assertTrue(self.stack.can_undo(), "Vorbedingung")
        v = self._view()
        self._waehle(v, [2])
        s = self._slider(v, "intensity")
        s._slider.setValue(200)
        self.assertEqual(self._prog(2).get("intensity"), 200)
        self.assertEqual(self._kanal(PAR_ADR), 200)

        v._undo()

        self.assertEqual([2], [f.fid for f in self.st.get_patched_fixtures()],
                         "Programmer-Rückgängig hat das Gerät entpatcht")
        self.assertIsNone(self._prog(2).get("intensity"))
        self.assertEqual(self._kanal(PAR_ADR), 0)
        self.assertTrue(self.stack.can_undo(), "globaler Stapel angefasst")

    def test_b_wiederholen(self):
        self.st.add_fixture(_par(), undoable=False)
        v = self._view()
        self._waehle(v, [2])
        self._slider(v, "intensity")._slider.setValue(150)
        v._undo()
        self.assertIsNone(self._prog(2).get("intensity"))
        v._redo()
        self.assertEqual(self._prog(2).get("intensity"), 150)
        self.assertEqual(self._kanal(PAR_ADR), 150)
        self.assertFalse(self.verlauf.kann_wiederholen())

    def test_c_ein_reglerzug_ist_ein_schritt(self):
        self.st.add_fixture(_par(), undoable=False)
        self.st.add_fixture(_par(fid=3, adr=210, label="PAR 2"), undoable=False)
        v = self._view()
        self._waehle(v, [2, 3])
        sl = self._slider(v, "intensity")._slider
        sl.sliderPressed.emit()
        for wert in (10, 60, 120, 240):
            sl.setValue(wert)
        sl.sliderReleased.emit()
        self.assertEqual(self.verlauf.anzahl(), 1)
        self.assertEqual(self._prog(3).get("intensity"), 240)
        v._undo()
        self.assertIsNone(self._prog(2).get("intensity"))
        self.assertIsNone(self._prog(3).get("intensity"))
        self.assertFalse(self.verlauf.kann_rueckgaengig())

    def test_c_viele_werte_in_einer_aktion_sind_ein_schritt(self):
        self.st.add_fixture(_par(), undoable=False)
        with self.st.programmer_schritt("Test"):
            for attr in ("intensity", "color_r", "color_g", "color_b"):
                self.st.set_programmer_value(2, attr, 99)
        self.assertEqual(self.verlauf.anzahl(), 1)
        self.assertEqual(self.st.programmer_rueckgaengig(), "Test")
        self.assertEqual(self._prog(2), {})

    def test_c_zwei_aktionen_sind_zwei_schritte(self):
        self.st.add_fixture(_par(), undoable=False)
        with self.st.programmer_schritt("eins"):
            self.st.set_programmer_value(2, "intensity", 10)
        with self.st.programmer_schritt("zwei"):
            self.st.set_programmer_value(2, "intensity", 20)
        self.st.programmer_rueckgaengig()
        self.assertEqual(self._prog(2).get("intensity"), 10)
        self.st.programmer_rueckgaengig()
        self.assertIsNone(self._prog(2).get("intensity"))


class AktionenTest(_Basis):
    """(d) Loeschen, (e) Hervorheben/Kachel/Einfuegen."""

    def setUp(self):
        super().setUp()
        self.st.add_fixture(_par(), undoable=False)
        self.st.add_fixture(_par(fid=3, adr=210, label="PAR 2"), undoable=False)
        self.v = self._view()

    def test_d_loeschen_ist_ruecknehmbar(self):
        with self.st.programmer_schritt("Werte"):
            self.st.set_programmer_value(2, "intensity", 180)
            self.st.set_programmer_value(3, "color_r", 70)
        vorher = self._ausgabe()
        self._waehle(self.v, [])
        self.v._clear_programmer()                   # ohne Auswahl: alles
        self.assertEqual(self.st.programmer, {})
        self.v._undo()
        self.assertEqual(self._prog(2), {"intensity": 180})
        self.assertEqual(self._prog(3), {"color_r": 70})
        self.assertEqual(self._ausgabe(), vorher)

    def test_d_teil_loeschen_ueber_mehrere_geraete_ist_ein_schritt(self):
        with self.st.programmer_schritt("Werte"):
            self.st.set_programmer_value(2, "intensity", 180)
            self.st.set_programmer_value(3, "intensity", 90)
        self._waehle(self.v, [2, 3])
        n = self.verlauf.anzahl()
        self.v._clear_programmer()
        self.verlauf.abschliessen()
        self.assertEqual(self.verlauf.anzahl(), n + 1)
        self.v._undo()
        self.assertEqual(self._prog(2).get("intensity"), 180)
        self.assertEqual(self._prog(3).get("intensity"), 90)

    def test_e_hervorheben_ist_ein_schritt(self):
        self._waehle(self.v, [2, 3])
        self.v._highlight()
        self.verlauf.abschliessen()
        self.assertEqual(self.verlauf.anzahl(), 1)
        self.assertEqual(self.verlauf.label_rueckgaengig(), "Hervorheben")
        self.v._undo()
        self.assertEqual(self.st.programmer, {})

    def test_e_kachel_ist_ein_schritt(self):
        from src.ui.widgets.preset_tile import _ApplyMixin

        class _Kachel(_ApplyMixin):
            pass
        k = _Kachel()
        k._state = self.st
        k._fixtures = list(self.st.get_patched_fixtures())
        k._apply_payload_on(k._fixtures, {"color_r": 255, "color_g": 0, "color_b": 0})
        self.verlauf.abschliessen()
        self.assertEqual(self.verlauf.anzahl(), 1)
        self.st.programmer_rueckgaengig()
        self.assertEqual(self.st.programmer, {})

    def test_e_einfuegen_ist_ein_schritt(self):
        self.st.set_programmer_value(2, "color_g", 33)
        self.st.set_programmer_value(2, "intensity", 44)
        self._waehle(self.v, [2])
        self.v._copy_to_clipboard()
        self._waehle(self.v, [3])
        self.verlauf.abschliessen()
        n = self.verlauf.anzahl()
        self.v._paste_from_clipboard()
        self.verlauf.abschliessen()
        self.assertEqual(self.verlauf.anzahl(), n + 1)
        self.assertEqual(self._prog(3), {"color_g": 33, "intensity": 44})
        self.v._undo()
        self.assertEqual(self._prog(3), {})
        self.assertEqual(self._prog(2), {"color_g": 33, "intensity": 44})


class ShowwechselTest(_Basis):
    """(f) Neue Show / Show oeffnen leeren den Programmer-Verlauf."""

    def test_neue_show_leert(self):
        self.st.add_fixture(_par(), undoable=False)
        self.st.set_programmer_value(2, "intensity", 50)
        self.assertTrue(self.verlauf.kann_rueckgaengig(), "Vorbedingung")
        reset_show()
        self.assertFalse(self.verlauf.kann_rueckgaengig())
        self.assertFalse(self.verlauf.kann_wiederholen())

    def test_show_oeffnen_leert(self):
        pfad = os.path.join(tempfile.mkdtemp(), "andere.lshow")
        self.st.add_fixture(_par(), undoable=False)
        self.st.set_programmer_value(2, "color_b", 77)
        save_show(pfad)
        reset_show()
        self.st.add_fixture(_par(), undoable=False)
        self.st.set_programmer_value(2, "intensity", 50)
        self.st.programmer_rueckgaengig()
        self.st.set_programmer_value(2, "intensity", 60)
        self.assertTrue(self.verlauf.kann_rueckgaengig(), "Vorbedingung")
        load_show(pfad)
        self.assertFalse(self.verlauf.kann_rueckgaengig())
        self.assertFalse(self.verlauf.kann_wiederholen())
        self.assertIsNone(self.st.programmer_rueckgaengig())


class KnoepfeTest(_Basis):
    """(g) Knoepfe nur aktiv, wenn es etwas gibt; Hilfetexte ehrlich."""

    def test_aktiv_inaktiv(self):
        self.st.add_fixture(_par(), undoable=False)
        v = self._view()
        self.assertFalse(v._btn_undo.isEnabled())
        self.assertFalse(v._btn_redo.isEnabled())
        with self.st.programmer_schritt("Hervorheben"):
            self.st.set_programmer_value(2, "intensity", 255)
        self.assertTrue(v._btn_undo.isEnabled())
        self.assertIn("Hervorheben", v._btn_undo.toolTip())
        self.assertFalse(v._btn_redo.isEnabled())
        v._undo()
        self.assertFalse(v._btn_undo.isEnabled())
        self.assertTrue(v._btn_redo.isEnabled())
        reset_show()
        self.assertFalse(v._btn_redo.isEnabled())

    def test_hilfetext_verspricht_nichts_falsches(self):
        from src.ui.views.programmer_view import _PROGRAMMER_HELP
        self.assertIn("Programmer-Schritt", _PROGRAMMER_HELP["Rückgängig"])
        self.assertIn("Strg+Z", _PROGRAMMER_HELP["Rückgängig"])


class TiefeTest(_Basis):
    """(h) begrenzte Tiefe."""

    def test_tiefe_begrenzt(self):
        self.st.add_fixture(_par(), undoable=False)
        maxi = self.verlauf.MAX
        for i in range(maxi + 5):
            with self.st.programmer_schritt(f"s{i}"):
                self.st.set_programmer_value(2, "intensity", i % 256)
        self.assertEqual(self.verlauf.anzahl(), maxi)
        n = 0
        while self.st.programmer_rueckgaengig() is not None:
            n += 1
        self.assertEqual(n, maxi)
        # die aeltesten fuenf sind verfallen: Stand nach Schritt 4
        self.assertEqual(self._prog(2).get("intensity"), 4)


class WeissUndKoepfeTest(_Basis):
    """(i) FM-41-Weiss-Segmente und Kopf-Schluessel werden korrekt zurueckgestellt."""

    def setUp(self):
        super().setUp()
        self.st.add_fixture(PatchedFixture(
            fid=1, label="Balken", fixture_profile_id=_pid("ZQ06121"),
            mode_name=BALKEN_MODUS, universe=1, address=1, channel_count=154,
            fixture_type="matrix"), undoable=False)

    def test_weiss_setzen_wird_ganz_zurueckgenommen(self):
        vorher = self._ausgabe()
        self.assertTrue(self.st.weiss_setzen(1, 3, 200))
        self.assertGreater(len(self._prog(1)), 1, "Anker gesetzt")
        self.assertNotEqual(self._ausgabe(), vorher)
        self.st.programmer_rueckgaengig()
        self.assertEqual(self._prog(1), {})
        self.assertEqual(self._ausgabe(), vorher)

    def test_weiss_zweiter_schritt_laesst_ersten_stehen(self):
        with self.st.programmer_schritt("erst"):
            self.st.weiss_setzen(1, 0, 100)
        nach_erst = (self._prog(1), self._ausgabe())
        with self.st.programmer_schritt("dann"):
            self.st.weiss_setzen(1, 5, 250)
        self.st.programmer_rueckgaengig()
        self.assertEqual((self._prog(1), self._ausgabe()), nach_erst)
        self.st.programmer_wiederholen()
        self.assertEqual(self._prog(1)[self.st.weiss_programmer_key(1, 5)], 250)

    def test_kopf_mit_geteiltem_master(self):
        vorher = self._ausgabe()
        with self.st.programmer_schritt("Kopf"):
            self.st.set_programmer_value(1, "color_r", 180, head=4)
        self.assertTrue(self._prog(1), "Vorbedingung")
        self.assertNotEqual(self._ausgabe(), vorher)
        self.st.programmer_rueckgaengig()
        self.assertEqual(self._prog(1), {})
        self.assertEqual(self._ausgabe(), vorher)


class AusgabeUndEreignisTest(_Basis):
    """(j) nach dem Wiederherstellen: Ausgabe, Ereignis, Regler zieht nach."""

    def test_ausgabe_ereignis_und_regler(self):
        self.st.add_fixture(_par(), undoable=False)
        v = self._view()
        self._waehle(v, [2])
        with self.st.programmer_schritt("vorher"):
            self.st.set_programmer_value(2, "intensity", 40)
        sl = self._slider(v, "intensity")
        sl._slider.setValue(220)
        self.assertEqual(self._kanal(PAR_ADR), 220)
        ereignisse = []

        def cb(ev, _d):
            ereignisse.append(ev)
        self.st.subscribe(cb)
        self.addCleanup(self.st.unsubscribe, cb)
        v._undo()
        self.assertIn("programmer_changed", ereignisse)
        self.assertEqual(self._kanal(PAR_ADR), 40)
        # Editor neu aufgebaut: die alten Regler warten nur noch auf deleteLater
        from PySide6.QtCore import QCoreApplication, QEvent
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        sl = self._slider(v, "intensity")
        self.assertEqual(sl._slider.value(), 40)

    def test_rueckgaengig_hebt_laser_notaus_nicht_auf(self):
        self.st.add_fixture(_par(), undoable=False)
        with self.st.programmer_schritt("x"):
            self.st.set_programmer_value(2, "shutter", 200)
        self.st.laser_estop_active = True
        self.addCleanup(setattr, self.st, "laser_estop_active", False)
        self.st.programmer_rueckgaengig()
        self.st.programmer_wiederholen()
        self.assertTrue(self.st.laser_estop_active)

    def test_entpatchtes_geraet_wird_uebersprungen(self):
        self.st.add_fixture(_par(), undoable=False)
        self.st.set_programmer_value(2, "intensity", 90)
        self.st.remove_fixture(2, undoable=False)
        self.st.programmer_rueckgaengig()
        self.assertNotIn(2, self.st.programmer)



# ── Review-Befunde FM-52 ──────────────────────────────────────────────────────

class ReviewShowOeffnenKnoepfeTest(_Basis):
    """R1: „Show öffnen" leert den Verlauf teils unter ``_suppress_emits`` — die
    Meldung ging verloren, der Status-Cache stand aber schon auf „leer"; das
    zweite Leeren meldete nichts mehr. „Rückgängig" blieb aktiv mit altem
    Tooltip."""

    def test_leeren_meldet_auch_nach_verworfener_meldung(self):
        from src.core.programmer_verlauf import ProgrammerVerlauf
        meldungen = []
        v = ProgrammerVerlauf(on_change=lambda: meldungen.append(1))
        v.notiere([(1, "intensity", None, 10)])
        cb = v._on_change
        v._on_change = None          # wie _emit unter _suppress_emits: verworfen
        v.leeren()
        v._on_change = cb
        meldungen.clear()
        v.leeren()                   # zweites Leeren nach dem Laden
        self.assertTrue(meldungen, "zweites Leeren hat nicht gemeldet")

    def test_voll_refresh_zieht_verlaufsknoepfe_nach(self):
        self.st.add_fixture(_par(), undoable=False)
        v = self._view()
        with self.st.programmer_schritt("Hervorheben"):
            self.st.set_programmer_value(2, "intensity", 255)
        self.assertTrue(v._btn_undo.isEnabled(), "Vorbedingung")
        self.st._suppress_emits = True
        try:
            self.verlauf.leeren()
        finally:
            self.st._suppress_emits = False
        v._sync_refresh()            # REFRESH_ALL / PATCH_CHANGED
        self.assertFalse(v._btn_undo.isEnabled())

    def test_show_oeffnen_deaktiviert_rueckgaengig(self):
        from src.ui.views.programmer_view import _PROGRAMMER_HELP
        pfad = os.path.join(tempfile.mkdtemp(), "andere.lshow")
        self.st.add_fixture(_par(), undoable=False)
        save_show(pfad)
        v = self._view()
        with self.st.programmer_schritt("Hervorheben"):
            self.st.set_programmer_value(2, "intensity", 255)
        self.assertTrue(v._btn_undo.isEnabled(), "Vorbedingung")
        load_show(pfad)
        self.assertFalse(v._btn_undo.isEnabled(),
                         "„Rückgängig“ nach „Show öffnen“ noch aktiv")
        self.assertFalse(v._btn_redo.isEnabled())
        self.assertEqual(v._btn_undo.toolTip(), _PROGRAMMER_HELP["Rückgängig"])


class ReviewMovingHeadResetTest(_Basis):
    """R2: der Moving-Head-Reset ist eine Geraete-Aktion mit Rueckfrage, kein
    Verlaufsschritt — sonst loest „Wiederholen" ihn ohne Rueckfrage erneut aus
    und laesst ihn stehen."""

    def _reset_knopf(self):
        from src.ui.widgets.preset_tile import ResetActionButton

        class _Range:
            def __init__(self, a, b, kind):
                self.range_from, self.range_to, self.kind = a, b, kind
                self.label = ""

        class _Ch:
            attribute = "reset"
            default_value = 0
            ranges = [_Range(0, 149, ""), _Range(150, 255, "reset")]
        knopf = ResetActionButton(_Ch(), list(self.st.get_patched_fixtures()),
                                  self.st)
        self.addCleanup(knopf.deleteLater)
        return knopf

    def test_reset_steht_nicht_im_verlauf(self):
        from unittest import mock
        from PySide6.QtWidgets import QMessageBox
        self.st.add_fixture(_par(), undoable=False)
        with self.st.programmer_schritt("vorher"):
            self.st.set_programmer_value(2, "intensity", 100)
        knopf = self._reset_knopf()
        with mock.patch.object(QMessageBox, "question",
                               return_value=QMessageBox.StandardButton.Yes):
            knopf._on_clicked()
        self.assertEqual(self._prog(2).get("reset"), 202, "Vorbedingung: ausgelöst")
        self.verlauf.abschliessen()
        self.assertEqual(self.verlauf.anzahl(), 1, "Reset als Schritt aufgezeichnet")
        self.assertEqual(self.verlauf.label_rueckgaengig(), "vorher")
        knopf._make_revert()()        # Zuruecksetzen nach HOLD_MS
        self.assertEqual(self._prog(2).get("reset"), 0)
        self.assertEqual(self.st.programmer_rueckgaengig(), "vorher")
        self.assertEqual(self._prog(2).get("reset"), 0)
        self.assertEqual(self.st.programmer_wiederholen(), "vorher")
        self.assertEqual(self._prog(2).get("reset"), 0,
                         "Wiederholen hat den Reset erneut ausgelöst")
        self.assertEqual(self._prog(2).get("intensity"), 100)


class ReviewWeissBlockEinSchrittTest(_Basis):
    """R3: ein Wert am Weiss-Block ueber n Geraete = EIN Schritt (weiss_setzen
    oeffnete je Aufruf einen eigenen)."""

    def setUp(self):
        super().setUp()
        plaetze = [(1, 1), (1, 155), (1, 309), (2, 1)]
        self.fids = []
        for i, (uni, adr) in enumerate(plaetze, start=1):
            self.st.add_fixture(PatchedFixture(
                fid=i, label=f"Balken {i}", fixture_profile_id=_pid("ZQ06121"),
                mode_name=BALKEN_MODUS, universe=uni, address=adr,
                channel_count=154, fixture_type="matrix"), undoable=False)
            self.fids.append(i)

    def test_ein_reglerwert_ueber_vier_geraete_ist_ein_schritt(self):
        from src.ui.views.programmer_view import WeissSegmentBlock
        ziele = [(f, self.st.weiss_programmer_key(f, 3), 3) for f in self.fids]
        self.assertTrue(all(z[1] for z in ziele), "Vorbedingung: Weiss-Segmente")
        block = WeissSegmentBlock({3: ziele}, self.st)
        self.addCleanup(block.deleteLater)
        block._regler[3][0].setValue(200)          # Rad/Taste: ohne Pressed
        self.verlauf.abschliessen()
        self.assertEqual(self.verlauf.anzahl(), 1)
        for f in self.fids:
            self.assertEqual(self._prog(f)[self.st.weiss_programmer_key(f, 3)], 200)
        self.st.programmer_rueckgaengig()
        for f in self.fids:
            self.assertEqual(self._prog(f), {}, f"Gerät {f} nicht zurückgestellt")

    def test_weiss_setzen_oeffnet_keinen_eigenen_schritt(self):
        # Ohne aeussere Klammer greift das Ruhe-Zeitfenster: zwei Aufrufe
        # direkt hintereinander (Rad-Ticks) sind EIN Schritt, nicht zwei.
        self.st.weiss_setzen(1, 3, 100)
        self.st.weiss_setzen(2, 3, 100)
        self.verlauf.abschliessen()
        self.assertEqual(self.verlauf.anzahl(), 1)

    def test_einzelnes_weiss_setzen_landet_im_schritt_des_aufrufers(self):
        # wie Kommandozeile „hi" / Hervorheben: ein aeusserer Schritt.
        with self.st.programmer_schritt("Befehl hi"):
            self.st.set_programmer_value(2, "intensity", 255)
            self.st.weiss_setzen(1, 0, 255)
            self.st.weiss_setzen(3, 2, 255)
        self.verlauf.abschliessen()
        self.assertEqual(self.verlauf.anzahl(), 1)
        self.assertEqual(self.verlauf.label_rueckgaengig(), "Befehl hi")


class ReviewFarbwaehlerLiveTest(_Basis):
    """R4: der Live-Modus (33-ms-Tick) schrieb UNBEDINGT — jedes „Rückgängig"
    war nach einem Tick ueberschrieben und „Wiederholen" weg."""

    def test_live_tick_ueberschreibt_rueckgaengig_nicht(self):
        from PySide6.QtGui import QColor
        from src.ui.widgets.color_picker import ColorPicker
        self.st.add_fixture(_par(), undoable=False)
        self.st.set_selected_fids([2])
        p = ColorPicker()
        self.addCleanup(p.deleteLater)
        p.set_color(QColor(200, 0, 0))
        p._btn_live.setChecked(True)
        p._live_timer.stop()                 # Ticks von Hand
        p._live_timer.timeout.emit()
        self.assertEqual(self._prog(2).get("color_r"), 200, "Vorbedingung")
        self.verlauf.abschliessen()
        self.st.programmer_rueckgaengig()
        self.assertIsNone(self._prog(2).get("color_r"))
        for _ in range(3):
            p._live_timer.timeout.emit()
        self.assertIsNone(self._prog(2).get("color_r"),
                          "Live-Tick hat das Rückgängig überschrieben")
        self.assertTrue(self.verlauf.kann_wiederholen())
        # Eine NEUE Farbe geht weiterhin sofort raus.
        p.set_color(QColor(0, 0, 90))
        p._live_timer.timeout.emit()
        self.assertEqual(self._prog(2).get("color_b"), 90)


class ReviewTexteTest(unittest.TestCase):
    """R5 + R6: Anleitung und Hilfetexte beschreiben den eigenen Verlauf und
    nennen kein plattformfalsches Kuerzel."""

    def test_hilfetexte_ohne_strg_y(self):
        from src.ui.views.programmer_view import _PROGRAMMER_HELP
        for k in ("Rückgängig", "Wiederholen"):
            self.assertNotIn("Strg+Y", _PROGRAMMER_HELP[k])
        self.assertIn("Bearbeiten → Wiederherstellen", _PROGRAMMER_HELP["Wiederholen"])

    def test_anleitung_beschreibt_eigenen_verlauf(self):
        pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
            __file__))), "docs", "anleitung_programmer_grundlagen", "ANLEITUNG.md")
        with open(pfad, encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("Reglerwerte im Programmer landen nicht darin", text)
        self.assertNotIn("Reglerwerte stehen nicht im Verlauf", text)
        self.assertNotIn("arbeiten auf demselben Verlauf", text)
        self.assertIn("eigenen Programmer-Verlauf", text)
        self.assertIn("**ein** Schritt", text)

if __name__ == "__main__":
    unittest.main()
