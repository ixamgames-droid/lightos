"""UI-57: ein gehaltener Panik-Taster darf einen Bankwechsel nicht ueberleben —
und „Alles Weiss"/Freeze duerfen keine globale Ruecksetzung ueberleben.

Der Hergang, den diese Tests festnageln:

    Operator haelt BLACKOUT (oder ALLES WEISS) am APC
    -> wechselt dabei die VC-Bank
    -> das ``note_off`` erreicht den Taster nicht mehr (der MIDI-Dispatch laesst
       nur Widgets der AKTIVEN Bank durch, ``VCCanvas._handle_midi``)
    -> der Taster bleibt gedrueckt, das Rig bleibt dunkel bzw. voll weiss

Und der Ausweg fehlte: ``_all_white_map`` ueberlebte STOP ALL, das Leeren des
Programmers und sogar „Neue Show" — danach wirkte der Override auf die fids der
NEUEN Show, also auf voellig andere Geraete. Ein eingefrorener Ausgang ueberlebte
ebenso.

Gemessen wird, wo es geht, am **gesendeten Frame** und nicht am Flag: ein
Zustandsbit sagt nicht, ob das Rig dunkel ist.
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import AppState
from src.ui.virtualconsole.vc_button import ButtonAction, VCButton
from src.ui.virtualconsole.vc_canvas import VCCanvas

_app = QApplication.instance() or QApplication([])


def _midi(msg_type, note=60, vel=127):
    """Die Message-Form, die der VC erwartet (``msg_type``/``data1``/``data2``)."""
    return SimpleNamespace(msg_type=msg_type, channel=0, data1=note, data2=vel)


class _FakeState:
    """Nur so viel AppState, wie der Panik-Pfad anfasst."""

    def __init__(self):
        self.all_white_calls = []
        self.blackout = False

    def set_all_white(self, active, exclude_fids=None):
        self.all_white_calls.append(bool(active))
        return 1 if active else 0


class BankwechselGibtGehalteneTasterFreiTest(unittest.TestCase):
    """Haelfte 1: der Bankwechsel holt das verschluckte Loslassen nach."""

    def _aufbau(self, action, bank=0):
        canvas = VCCanvas()
        btn = VCButton(parent=canvas)
        btn.action = action
        btn.bank = bank
        btn.accept_midi(0, 60, "note_on")
        canvas.set_active_bank(bank)
        return canvas, btn

    def test_gehaltener_all_white_taster_wird_freigegeben(self):
        canvas, btn = self._aufbau(ButtonAction.ALL_WHITE)
        canvas._handle_midi(_midi("note_on"))
        self.assertTrue(btn._pressed, "Vorbedingung: der Taster muss gehalten sein")

        canvas.set_active_bank(1)
        self.assertFalse(
            btn._pressed,
            "Der Taster bleibt nach dem Bankwechsel gedrueckt - genau der Zustand, "
            "aus dem der Operator vor Publikum nicht mehr herausfindet")

    def test_gehaltener_blackout_taster_wird_freigegeben(self):
        canvas, btn = self._aufbau(ButtonAction.BLACKOUT)
        canvas._handle_midi(_midi("note_on"))
        self.assertTrue(btn._pressed)

        canvas.set_active_bank(1)
        self.assertFalse(btn._pressed)

    def test_nachtraegliches_note_off_der_alten_bank_bleibt_wirkungslos(self):
        """Die Freigabe darf nicht doppelt ausloesen.

        Schaltet der Operator spaeter auf die alte Bank zurueck und laesst dort
        los, ist der Taster laengst frei — ein zweites Release waere ein
        zusaetzlicher Trigger.
        """
        canvas, btn = self._aufbau(ButtonAction.BLACKOUT)
        canvas._handle_midi(_midi("note_on"))
        canvas.set_active_bank(1)
        canvas.set_active_bank(0)
        canvas._handle_midi(_midi("note_off", vel=0))
        self.assertFalse(btn._pressed)

    # ── Positivkontrollen ────────────────────────────────────────────────────

    def test_ohne_gehaltenen_taster_passiert_nichts(self):
        canvas, btn = self._aufbau(ButtonAction.BLACKOUT)
        self.assertFalse(btn._pressed)
        canvas.set_active_bank(1)
        self.assertFalse(btn._pressed)

    def test_bankwechsel_auf_dieselbe_bank_gibt_nichts_frei(self):
        """Ein „Wechsel" auf die aktive Bank ist keiner — er darf einen
        gehaltenen Taster nicht abwuergen."""
        canvas, btn = self._aufbau(ButtonAction.BLACKOUT)
        canvas._handle_midi(_midi("note_on"))
        canvas.set_active_bank(0)
        self.assertTrue(
            btn._pressed,
            "Ein Wechsel auf die BEREITS aktive Bank hat den Taster freigegeben")

    def test_taster_einer_anderen_bank_wird_nicht_angefasst(self):
        """Freigegeben wird nur, was auf der VERLASSENEN Bank liegt."""
        canvas = VCCanvas()
        b0 = VCButton(parent=canvas)
        b0.action = ButtonAction.BLACKOUT
        b0.bank = 0
        b1 = VCButton(parent=canvas)
        b1.action = ButtonAction.BLACKOUT
        b1.bank = 1
        canvas.set_active_bank(0)
        b0._pressed = True
        b1._pressed = True          # liegt auf Bank 1, geht uns nichts an

        canvas.set_active_bank(1)
        self.assertFalse(b0._pressed, "Bank 0 wurde verlassen -> freigeben")
        self.assertTrue(b1._pressed, "Bank 1 wurde nicht verlassen -> unberuehrt")

    def test_laufender_toggle_ueberlebt_den_bankwechsel(self):
        """Der Unterschied zu ``deactivate_for_solo``, und er ist Absicht.

        Ein FUNCTION_TOGGLE soll ueber Bankwechsel hinweg WEITERLAUFEN — das ist
        sein Zweck. Freigegeben wird ausschliesslich, was physisch gehalten wird.
        """
        canvas = VCCanvas()
        btn = VCButton(parent=canvas)
        btn.action = ButtonAction.FUNCTION_TOGGLE
        btn.bank = 0
        canvas.set_active_bank(0)
        self.assertFalse(btn._pressed)   # ein Toggle ist nicht „gehalten"

        ausloesungen = []
        btn._trigger = lambda press: ausloesungen.append(press)
        canvas.set_active_bank(1)
        self.assertEqual(ausloesungen, [],
                         "Der Bankwechsel hat einen laufenden Toggle angefasst")


class ReleaseIfHeldVertragTest(unittest.TestCase):
    """Der Vertrag selbst — damit ein neues Widget ihn erben kann."""

    def test_basiswidget_haelt_nichts(self):
        from src.ui.virtualconsole.vc_widget import VCWidget
        self.assertFalse(VCWidget.release_if_held(SimpleNamespace()))

    def test_button_meldet_ob_er_wirklich_freigegeben_hat(self):
        canvas = VCCanvas()
        btn = VCButton(parent=canvas)
        btn.action = ButtonAction.BLACKOUT
        self.assertFalse(btn.release_if_held(), "nichts gehalten -> nichts freigegeben")
        btn._pressed = True
        self.assertTrue(btn.release_if_held())
        self.assertFalse(btn.release_if_held(), "zweimal freigeben gibt es nicht")


class GlobaleRuecksetzungErreichtDieUebersteuerungenTest(unittest.TestCase):
    """Haelfte 2: „Neue Show" muss aus jedem Panik-Zustand herausfuehren.

    Am ECHTEN ``AppState`` und am ECHTEN ``reset_show()`` gemessen — eine
    Nachbildung koennte genau die Reihenfolge verfehlen, um die es hier geht.
    Die Show-DB ist per ``conftest`` ohnehin eine Wegwerf-Datei.
    """

    def _patch_einen_par(self, st, fid=1, address=1):
        from src.core.database.models import PatchedFixture
        st.add_fixture(PatchedFixture(
            fid=fid, label="PAR", fixture_profile_id=1, mode_name="m",
            universe=1, address=address, channel_count=8, fixture_type="par"),
            undoable=False)

    def test_weiss_override_ueberlebt_neue_show_nicht(self):
        """Der eigentliche Fund: der Override wirkte danach auf die fids der
        NEUEN Show, also auf voellig andere Geraete."""
        from src.core.app_state import get_state
        from src.core.show.show_file import reset_show

        st = get_state()
        reset_show()
        self._patch_einen_par(st)
        self.assertGreater(st.set_all_white(True), 0,
                           "Vorbedingung: der Override muss greifen")
        self.assertIsNotNone(st._all_white_map)

        reset_show()
        self.assertIsNone(
            st._all_white_map,
            'Alles Weiss hat die Neue Show ueberlebt — der Override wirkt '
            'jetzt auf die Geraete der NEUEN Show')

    def test_ein_neues_geraet_bleibt_nach_neuer_show_dunkel(self):
        """Dasselbe am gesendeten Frame statt am Flag.

        ★ Der Weiss-Override wird im RENDER-Pfad angewandt (``_render_frame``,
        Schritt 4a³), nicht im Programmer-Flush. Eine erste Fassung dieses Tests
        mass ``_flush_all_to_dmx`` und blieb deshalb bei der Mutations-Gegenprobe
        GRUEN — sie pruefte einen Pfad, den der Override gar nicht beruehrt.
        Aufgefallen ist es nur an der Mutation; eine gruen bleibende Gegenprobe
        ist ein Testfehler, kein Erfolg.
        """
        from src.core.app_state import get_state
        from src.core.show.show_file import reset_show

        st = get_state()
        reset_show()
        self._patch_einen_par(st)
        st.set_all_white(True)

        # Vorbedingung: der Override wirkt ueberhaupt (sonst misst der Test nichts)
        st._render_frame(0.0)
        uni = st.universes.get(1)
        self.assertIsNotNone(uni, "kein Universum 1 — Testaufbau stimmt nicht")
        hell = [uni.get_channel(i) for i in range(1, 9)]
        self.assertNotEqual(hell, [0] * 8,
                            "Vorbedingung verfehlt: der Weiss-Override wirkt gar nicht")

        reset_show()
        self._patch_einen_par(st)          # Geraet der NEUEN Show
        st._render_frame(0.0)
        uni = st.universes.get(1)
        werte = [uni.get_channel(i) for i in range(1, 9)]
        self.assertEqual(
            werte, [0] * 8,
            f"Ein frisch gepatchtes Geraet der NEUEN Show leuchtet: {werte}")

    def test_freeze_ueberlebt_neue_show_nicht(self):
        """Ein eingefrorener Ausgang liesse die neue Show gar nicht erscheinen."""
        from src.core.app_state import get_state
        from src.core.show.show_file import reset_show

        st = get_state()
        reset_show()
        st.set_freeze(True)
        self.assertTrue(st.is_frozen(), "Vorbedingung: eingefroren")

        reset_show()
        self.assertFalse(st.is_frozen(), 'Freeze hat die Neue Show ueberlebt')

    def test_uebersteuerungen_fallen_vor_dem_rest(self):
        """Reihenfolge ist nicht egal: der Reset nullt spaeter die DMX-Puffer und
        flusht. Stuende der Freeze da noch, ginge dieser Flush nicht raus."""
        import inspect

        import src.core.show.show_file as SF

        quelle = inspect.getsource(SF._reset_state)
        i_white = quelle.index("_all_white_map = None")
        i_patch = quelle.index("_replace_patch_from_data")
        self.assertLess(i_white, i_patch,
                        "Die Uebersteuerungen werden erst nach dem Patch-Reset "
                        "aufgehoben — dann ist der Flush schon durch")


if __name__ == "__main__":
    unittest.main()
