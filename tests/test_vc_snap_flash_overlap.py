"""BUG-MIDI-STROBE — ueberlappende Flash-Tasten duerfen keine Werte scharf lassen.

Davids Meldung (2026-08-01, Show „bierpong v2"): zwei Strobe-Taster auf dem
MIDI-Controller schnell hintereinander bzw. gleichzeitig gedrueckt — „sie haengen
sich auf", und NUR ein Clear Programmer loest es wieder.

Die Klasse dahinter: ein Flash-Taster (``ButtonAction.LIBRARY_SNAP`` mit
``snap_mode="flash"``) schreibt beim Druck Werte in den Programmer und merkt sich
den vorherigen Wert, um ihn beim Loslassen zurueckzugeben. Erfasst jede Taste
dieses „vorher" fuer sich, sieht die ZWEITE nicht den Ruhezustand, sondern den
bereits gesetzten Strobe-Wert der ersten — und ihr Loslassen schreibt ihn
zurueck, statt zu raeumen. Dass ausgerechnet nur Clear Programmer hilft, ist der
Fingerabdruck: der haengende Zustand liegt IM Programmer.

Diese Tests messen deshalb nicht, ob eine Taste „funktioniert", sondern das
VERHAELTNIS mehrerer Tasten zueinander ueber eine Druckfolge hinweg — genau das,
was Einzeltests je Taste nicht sehen koennen.
"""
import gc
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.engine.snap_library import get_snap_library
from src.core.midi.midi_manager import MidiMessage
from src.ui.virtualconsole import vc_button
from src.ui.virtualconsole.vc_button import (VCButton, ButtonAction,
                                             forget_snap_claims)

FID = 2
ATTR = "shutter"


class _Ghost:
    """Halter ohne Qt — steht fuer ein Widget, das nicht mehr existiert."""


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _note(kind: str, data1: int, vel: int) -> MidiMessage:
    return MidiMessage(port_name="test", channel=1, msg_type=kind,
                       data1=data1, data2=vel)


class VcSnapFlashOverlapTest(unittest.TestCase):

    def setUp(self):
        _app()
        self.state = get_state()
        # Kein Register-Reset: das Register ist Modulzustand und ueberlebt den
        # Test — aber genau dafuer gibt es die Uebernahme-Erkennung. Ein
        # ``clear_programmer()`` entwertet jeden Anspruch, und dass die Tests
        # ohne Sonder-Reset sauber laufen, ist der Beweis dafuer.
        self.state.clear_programmer()
        self.lib = get_snap_library()
        self._sids: list[int] = []
        self._btns: list[VCButton] = []

    def tearDown(self):
        for btn in self._btns:
            forget_snap_claims(btn)
        self.state.clear_programmer()
        for sid in self._sids:
            try:
                self.lib.remove_snap(sid)
            except Exception:
                pass

    # ── Hilfen ───────────────────────────────────────────────────────────────

    def _strobe_button(self, value: int, note: int, *, mode: str = "flash") -> VCButton:
        """Eine Strobe-Taste: Bibliothek-Snap auf ``shutter`` von Fixture ``FID``."""
        snap = self.lib.add_snap(f"TEST_strobe_{note}", "", {FID: {ATTR: value}})
        self._sids.append(snap.id)
        btn = VCButton()
        btn.action = ButtonAction.LIBRARY_SNAP
        btn.snap_id = snap.id
        btn.snap_mode = mode
        btn.midi_type = "note_on"
        btn.midi_ch = 1
        btn.midi_data1 = note
        self._btns.append(btn)
        return btn

    def _prog(self):
        return self.state.get_programmer_value(FID, ATTR)

    # ── Der gemeldete Fehler ─────────────────────────────────────────────────

    def test_doppeldruck_ohne_release_laesst_nichts_scharf(self):
        """Zweites note_on ohne dazwischenliegendes note_off (schnelles
        Doppeldruecken / verschlucktes Release) darf den eigenen Wert nicht als
        Ruhewert merken."""
        btn = self._strobe_button(210, 40)

        btn.handle_midi(_note("note_on", 40, 127))
        self.assertEqual(self._prog(), 210, "Strobe muss beim Druck stehen")
        btn.handle_midi(_note("note_on", 40, 127))
        self.assertEqual(self._prog(), 210, "zweiter Druck aendert den Wert nicht")
        btn.handle_midi(_note("note_off", 40, 0))

        self.assertIsNone(self._prog(),
                          "nach dem Loslassen darf KEIN Wert scharf bleiben "
                          "(sonst haengt der Strobe wie bei David)")

    def test_zwei_taster_ueberlappend_lassen_nichts_scharf(self):
        """A druecken, B druecken, A loslassen, B loslassen → Ruhezustand.

        Das ist Davids Fall woertlich: zwei Strobe-Taster gleichzeitig.
        """
        a = self._strobe_button(210, 41)
        b = self._strobe_button(250, 42)

        a.handle_midi(_note("note_on", 41, 127))
        b.handle_midi(_note("note_on", 42, 127))
        a.handle_midi(_note("note_off", 41, 0))
        b.handle_midi(_note("note_off", 42, 0))

        self.assertIsNone(self._prog(),
                          "beide Taster sind los — es darf nichts scharf bleiben")

    def test_ueberlappung_stellt_echten_ruhewert_wieder_her(self):
        """Ein Ruhewert ungleich „ungesetzt" muss die Ueberlappung ueberleben.

        Ohne gemeinsames Register erbt der zweite Taster den Wert des ersten als
        „vorher" — dann kaeme 210 zurueck statt der urspruenglichen 40.
        """
        self.state.set_programmer_value(FID, ATTR, 40)
        a = self._strobe_button(210, 43)
        b = self._strobe_button(250, 44)

        a.handle_midi(_note("note_on", 43, 127))
        b.handle_midi(_note("note_on", 44, 127))
        a.handle_midi(_note("note_off", 43, 0))
        b.handle_midi(_note("note_off", 44, 0))

        self.assertEqual(self._prog(), 40,
                         "der Ruhewert VOR dem ersten Druck muss zurueckkommen")

    def test_loslassen_loescht_den_gehaltenen_nachbarn_nicht(self):
        """Die Rueckseite desselben Fehlers: A loslassen, waehrend B noch haelt,
        darf Bs Strobe nicht mitloeschen."""
        a = self._strobe_button(210, 45)
        b = self._strobe_button(250, 46)

        a.handle_midi(_note("note_on", 45, 127))
        b.handle_midi(_note("note_on", 46, 127))
        a.handle_midi(_note("note_off", 45, 0))

        self.assertEqual(self._prog(), 250,
                         "B haelt noch — sein Wert muss stehen bleiben")

    def test_mittlerer_halter_gibt_an_den_verbliebenen_zurueck(self):
        """B loslassen, waehrend A noch haelt, gibt an As Wert zurueck —
        nicht an den Ruhewert."""
        a = self._strobe_button(210, 47)
        b = self._strobe_button(250, 48)

        a.handle_midi(_note("note_on", 47, 127))
        b.handle_midi(_note("note_on", 48, 127))
        b.handle_midi(_note("note_off", 48, 0))

        self.assertEqual(self._prog(), 210,
                         "A haelt noch — sein Wert gilt wieder")

        a.handle_midi(_note("note_off", 47, 0))
        self.assertIsNone(self._prog(), "danach ist wirklich Ruhe")

    def test_clear_programmer_waehrend_gehalten_kommt_nicht_zurueck(self):
        """„Programmer leeren" ist Davids Notausgang — danach darf das Loslassen
        einer noch gedrueckten Taste den alten Ruhewert nicht zurueckschreiben.

        Sonst raeumt genau die Rettung nur kurz auf: der Wert von VOR dem Druck
        kaeme beim Loslassen wieder in den Programmer.
        """
        self.state.set_programmer_value(FID, ATTR, 40)
        btn = self._strobe_button(210, 57)

        btn.handle_midi(_note("note_on", 57, 127))
        self.state.clear_programmer()                 # Davids Rettung
        btn.handle_midi(_note("note_off", 57, 0))

        self.assertIsNone(self._prog(),
                          "nach dem Leeren darf nichts wieder auftauchen")

    def test_handwert_waehrend_gehalten_ueberlebt_das_loslassen(self):
        """Dieselbe Regel von der anderen Seite: greift jemand den Kanal
        waehrend des Drucks von Hand an, gilt sein Wert — das Loslassen darf ihn
        nicht durch den alten Ruhewert ersetzen."""
        self.state.set_programmer_value(FID, ATTR, 40)
        btn = self._strobe_button(210, 58)

        btn.handle_midi(_note("note_on", 58, 127))
        self.state.set_programmer_value(FID, ATTR, 90)   # Hand/Palette dazwischen
        btn.handle_midi(_note("note_off", 58, 0))

        self.assertEqual(self._prog(), 90,
                         "der neuere Wert gehoert dem, der ihn gesetzt hat")

    # ── Gegenproben: bestehendes Verhalten bleibt ────────────────────────────

    def test_sauber_gepaarter_einzeldruck_unveraendert(self):
        """Der Normalfall darf sich nicht aendern."""
        btn = self._strobe_button(210, 49)

        btn.handle_midi(_note("note_on", 49, 127))
        self.assertEqual(self._prog(), 210)
        btn.handle_midi(_note("note_off", 49, 0))
        self.assertIsNone(self._prog())

    def test_toggle_modus_bleibt_ein_aus(self):
        """snap_mode="toggle" schaltet weiterhin auf den Druck um."""
        btn = self._strobe_button(210, 50, mode="toggle")

        btn.handle_midi(_note("note_on", 50, 127))
        btn.handle_midi(_note("note_off", 50, 0))
        self.assertEqual(self._prog(), 210, "Toggle bleibt nach dem Loslassen an")

        btn.handle_midi(_note("note_on", 50, 127))
        btn.handle_midi(_note("note_off", 50, 0))
        self.assertIsNone(self._prog(), "zweiter Druck schaltet aus")

    def test_neu_zuweisen_gibt_den_ruhewert_frei(self):
        """Wird ein Snap neu zugewiesen (oder eine Show geladen), darf die alte
        Taste den Ruhewert nicht fuer alle anderen blockieren.

        As Wert bleibt beim Abmelden als Waise im Programmer stehen — erbte B ihn
        als „vorher", schriebe Bs Loslassen ihn fest und der Strobe haenge
        endgueltig. Genau dieser Endzustand ist Davids Symptom.
        """
        a = self._strobe_button(210, 51)
        b = self._strobe_button(250, 52)

        a.handle_midi(_note("note_on", 51, 127))
        forget_snap_claims(a)          # wie beim Show-Neuladen / Snap-Wechsel
        a._snap_prev = {}

        b.handle_midi(_note("note_on", 52, 127))
        b.handle_midi(_note("note_off", 52, 0))

        self.assertIsNone(self._prog(),
                          "B muss den Kanal wieder freigeben koennen, obwohl A "
                          "ihn vor dem Abmelden gehalten hat")

    def test_waise_wird_nicht_geerbt_wenn_jemand_den_kanal_aendert(self):
        """Die Gegenprobe zur Waisen-Regel: hat nach dem Abmelden jemand ANDERES
        den Kanal gesetzt, ist dessen Wert der Ruhezustand — nicht der von vor
        dem verwaisten Druck. Sonst loeschte ein Flash den manuellen Wert."""
        a = self._strobe_button(210, 53)
        b = self._strobe_button(250, 54)

        a.handle_midi(_note("note_on", 53, 127))
        forget_snap_claims(a)
        a._snap_prev = {}
        self.state.set_programmer_value(FID, ATTR, 40)   # manuell dazwischen

        b.handle_midi(_note("note_on", 54, 127))
        b.handle_midi(_note("note_off", 54, 0))

        self.assertEqual(self._prog(), 40,
                         "der manuell gesetzte Wert ist der Ruhezustand")

    def test_zerstoerter_halter_blockiert_den_kanal_nicht(self):
        """Stirbt ein Halter (Widget geloescht, VC-Seite verworfen), darf sein
        Wert den Kanal nicht dauerhaft besetzen — der naechste Taster raeumt ihn.

        Der Halter wird hier direkt ueber die Register-Funktionen gesetzt und
        dann freigegeben: ein echtes QWidget stirbt ohne laufende Event-Loop
        nicht zuverlaessig, und gemessen werden soll das Register, nicht Qts
        Abbau-Zeitpunkt.
        """
        state = self.state
        ghost = _Ghost()
        vc_button._snap_claim(ghost, (FID, ATTR), None, 210)
        state.set_programmer_value(FID, ATTR, 210)
        del ghost
        gc.collect()

        b = self._strobe_button(250, 56)
        b.handle_midi(_note("note_on", 56, 127))
        b.handle_midi(_note("note_off", 56, 0))

        self.assertIsNone(self._prog(),
                          "der Wert des gestorbenen Halters muss aufloesbar bleiben")


if __name__ == "__main__":
    unittest.main()
