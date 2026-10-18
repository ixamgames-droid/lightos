"""LAS-36 + LAS-38 zusammen: die zwei Sicherheitsaussagen am zusammengefuehrten Stand.

LAS-36 (kein Wert loest den Laser-NOT-AUS, nur der Knopf mit bestaetigter
Rueckfrage) und LAS-38 (Kombigeraete im Kurz-Modus gelten als Laser) sind
getrennt entstanden. Diese Datei prueft sie GEMEINSAM, an einem Patch mit einem
echten Laser, einem Kombigeraet im Kurz-Modus und einer Lampe:

A) Kein Eingangsweg loest — Szene, Chaser, eine Funktion, die alles aufreisst
   (Matrix/EFX/Skript), Programmer (auch der Weg des VC-Faders und des
   Rueckgaengig), Simple Desk, der DMX-Eingang in jedem Misch-Modus und der
   Einzelkanal von Web/OSC. Der Latch steht danach, beide Laser sind dunkel,
   die Lampe laeuft weiter.
B) Das Kombigeraet bleibt im NOT-AUS dunkel — auch wenn waehrend des NOT-AUS
   umadressiert, der Modus gewechselt oder eine andere Show geladen wird, und
   auch dann, wenn die Profil-Auskunft in diesem Moment ausfaellt.
C) Die Rueckfrage als ECHTER Dialog: Esc, Schliessen, „Abbrechen“ und die
   Eingabetaste loesen nicht; nur „Ja“ loest.

Echter Weg wie in LAS-31: ``_render_frame`` -> ``_send_all`` -> Anzeige-Frame.
Es wird nichts gesendet.
"""
import os
import sys
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

from PySide6.QtCore import Qt, QTimer                                # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox              # noqa: E402

import src.core.app_state as A                                       # noqa: E402
from src.core.app_state import AppState                              # noqa: E402
from src.core.dmx.output_manager import OutputManager                # noqa: E402
from src.core.engine.function_manager import FunctionManager         # noqa: E402
from src.core.laser import erkennung                                 # noqa: E402
from src.ui import laser_notaus                                      # noqa: E402
import test_las31_notaus_kopfleiste as l31                           # noqa: E402

_AUS, _MANUAL = l31._AUS, l31._MANUAL

_LASER_FID, _PAR_FID, _KOMBI_FID = 7, 9, 21
_PROFIL_KOMBI = 990038          # Profil mit Laserkanal in einem ANDEREN Modus
_PROFIL_LAMPE = 990039

# Laser auf 10..12, Lampe auf 20..21, Kombigeraet auf 30..
_LASER_ADR = (10, 11, 12)
_KOMBI_KURZ_ADR = (30, 31, 32)
_KOMBI_LANG_ADR = (30, 31, 32, 33)
_PAR_DIMMER = 20


def _kurz():
    """Kurz-Modus ohne eigenen Laserkanal — der Laser laeuft ueber die
    Automatikprogramme (wie GigBAR 2 „3-channel“)."""
    return [l31._Ch("raw", 1, default=120), l31._Ch("raw", 2, default=120),
            l31._Ch("raw", 3, default=120)]


def _lang():
    """Der lange Modus desselben Profils: hier steht „Laser“ im Kanalnamen."""
    kan = [l31._Ch("intensity", 1), l31._Ch("color_r", 2),
           l31._Ch("shutter", 3, default=120), l31._Ch("raw", 4, default=120)]
    kan[3].name = "Laser Strobe"
    return kan


class _Kombi(l31._Fx):
    """Kombigeraet: weder Typ noch Name sagen „Laser“."""
    fixture_profile_id = _PROFIL_KOMBI
    mode_name = "3-channel"
    manufacturer_name = "Testwerk"
    label = "Bar links"

    def __init__(self, fid, universe, address):
        super().__init__(fid, universe, address, "other")
        self.fixture_name = "Kombi Bar"


class _ZusammenBasis(unittest.TestCase):
    def setUp(self):
        # Profil-Auskunft wie aus der Geraete-Datenbank; nachher wie vorgefunden.
        self._quelle_alt = getattr(erkennung, "_profil_quelle", None)
        erkennung.vergiss_profile()
        self.auskunft = {_PROFIL_KOMBI: True, _PROFIL_LAMPE: False, 1: False}
        self.auskunft_ausgefallen = False

        def alle_auf_einmal(profil_ids):
            # steht fuer die EINE Abfrage der Geraete-Datenbank beim Patchen/Laden
            if self.auskunft_ausgefallen:
                raise RuntimeError("Geraete-Datenbank nicht erreichbar")
            return {i: bool(self.auskunft.get(i, False)) for i in profil_ids}

        def einzeln(profil_id):
            return alle_auf_einmal([profil_id]).get(profil_id)
        self._abfrage_alt = A._profile_mit_laserkanal
        A._profile_mit_laserkanal = alle_auf_einmal
        self.addCleanup(setattr, A, "_profile_mit_laserkanal", self._abfrage_alt)
        erkennung.setze_profil_quelle(einzeln)
        self.addCleanup(erkennung.vergiss_profile)
        self.addCleanup(erkennung.setze_profil_quelle, self._quelle_alt)

        self.kombi = _Kombi(_KOMBI_FID, 1, 30)
        self.kanaele = {_LASER_FID: l31._CHANNELS[_LASER_FID],
                        _PAR_FID: l31._CHANNELS[_PAR_FID],
                        _KOMBI_FID: _kurz()}
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: self.kanaele[fx.fid]
        self.addCleanup(setattr, A, "get_channels_for_patched", self._orig)

        self.st, self.om = l31._make_state(patch=(l31._LASER, l31._PAR, self.kombi))
        st = self.st
        st._input_lock = threading.RLock()
        st.input_layer = {}
        st.input_merge_modes = {}
        st.input_last_seen = {}
        st._remote_input_channels = {}
        st._sd_lock = threading.RLock()
        st.simple_desk = {}
        st.simple_desk_override = False
        st._emit_dmx_changed = lambda *a, **k: None

        # Jeder Aufruf, der den Latch zuruecknehmen will, wird mitgeschrieben.
        self.loese_versuche = []
        echt = st.set_laser_estop

        def mitschreiben(aktiv):
            if not aktiv:
                self.loese_versuche.append(aktiv)
            return echt(aktiv)
        st.set_laser_estop = mitschreiben

    def _frame(self):
        self.st._render_frame(0.025)
        self.om._send_all()
        return self.om._display_frame[1]

    def _werte(self, adressen):
        frame = self._frame()
        return [frame[a - 1] for a in adressen]

    def _dunkel(self, was, kombi_adr=_KOMBI_KURZ_ADR):
        """Latch steht, niemand hat zu loesen versucht, beide Laser sind aus,
        die Lampe laeuft."""
        self.assertTrue(self.st.laser_estop_active,
                        f"{was}: der NOT-AUS wurde ohne Rueckfrage geloest")
        self.assertTrue(self.om._laser_estop_aktiv,
                        f"{was}: die Ausgabe-Maske wurde geleert")
        self.assertEqual(self.loese_versuche, [], was)
        for _ in range(3):                     # ueber mehrere Frames stabil
            frame = self._frame()
            self.assertEqual([frame[a - 1] for a in _LASER_ADR], [_AUS, 0, 0],
                             f"{was}: der Laser gibt aus")
            self.assertEqual([frame[a - 1] for a in kombi_adr], [0] * len(kombi_adr),
                             f"{was}: das Kombigeraet gibt aus")
        return frame


# ══════════════════════════════════════════════════════════════════════════════
# A) Kein Eingangsweg loest den NOT-AUS
# ══════════════════════════════════════════════════════════════════════════════

class KeinEingangswegLoestTest(_ZusammenBasis):

    def test_vorbedingung_beide_sind_laser_und_ohne_notaus_an(self):
        self.assertEqual(erkennung.laser_grund(self.kombi, self.kanaele[_KOMBI_FID]),
                         erkennung.GRUND_ANDERER_MODUS)
        self.assertEqual(set(self.st._laser_fids), {_LASER_FID, _KOMBI_FID})
        self.assertEqual(set(self.st._laser_estop_addrs[1]),
                         set(_LASER_ADR) | set(_KOMBI_KURZ_ADR))
        self.assertEqual(self._werte(_LASER_ADR)[0], _MANUAL)
        self.assertEqual(self._werte(_KOMBI_KURZ_ADR), [120, 120, 120])

    def _szene(self, fm):
        szene = fm.new_scene("Laser an")
        szene.set_value(_LASER_FID, 1, 200)
        szene.set_value(_LASER_FID, 2, 77)
        for kanal in (1, 2, 3):
            szene.set_value(_KOMBI_FID, kanal, 180)
        szene.set_value(_PAR_FID, 1, 255)
        return szene

    def test_szene_loest_nicht(self):
        fm = FunctionManager()
        self.st.function_manager = fm
        szene = self._szene(fm)
        fm.start(szene.id)
        # Ohne NOT-AUS erreicht die Szene beide Geraete (sonst bewiese der
        # Rest nichts).
        self.assertEqual(self._werte(_LASER_ADR)[:2], [200, 77])
        self.assertEqual(self._werte(_KOMBI_KURZ_ADR), [180, 180, 180])
        fm.stop(szene.id)
        self.st.set_laser_estop(True)
        fm.start(szene.id)                     # Szene bei stehendem NOT-AUS
        frame = self._dunkel("Szene")
        self.assertEqual(frame[_PAR_DIMMER - 1], 255)
        # Nach dem bestaetigten Loesen kommt, was eingestellt ist.
        self.st.laser_notaus_loesen()
        self.assertEqual(self._werte(_KOMBI_KURZ_ADR), [180, 180, 180])

    def test_chaser_loest_nicht(self):
        fm = FunctionManager()
        self.st.function_manager = fm
        szene = self._szene(fm)
        chaser = fm.new_chaser("Lauf")
        chaser.add_step(szene.id, fade_in=0.0, hold=0.05)
        chaser.add_step(szene.id, fade_in=0.0, hold=0.05)
        fm.start(chaser.id)
        for _ in range(4):
            frame = self._frame()
        self.assertEqual([frame[a - 1] for a in _KOMBI_KURZ_ADR], [180, 180, 180],
                         "der Chaser erreicht das Kombigeraet gar nicht")
        self.st.set_laser_estop(True)
        for _ in range(8):                     # ueber mehrere Schrittwechsel
            self._frame()
        self._dunkel("Chaser")

    def test_funktion_die_alles_aufreisst_loest_nicht(self):
        """Matrix, EFX, Skript: was immer eine laufende Funktion in den Frame
        schreibt, der NOT-AUS liegt darueber."""
        class _AllesAuf:
            def tick(self, universes, patch_cache, dt):
                for u in universes.values():
                    for adresse in range(1, 513):
                        u.set_channel(adresse, 255)
        self.st.function_manager = _AllesAuf()
        self.assertEqual(self._werte(_KOMBI_KURZ_ADR), [255, 255, 255])
        self.st.set_laser_estop(True)
        frame = self._dunkel("Funktion schreibt alles auf 255")
        self.assertEqual(frame[_PAR_DIMMER - 1], 255)

    def test_programmer_an_beiden_geraeten_loest_nicht(self):
        """Der Weg des VC-Faders (Stufen-Modus), der Muster-Taste und des
        Laser-Tabs: ``set_programmer_value``."""
        self.st.set_laser_estop(True)
        for fid in (_LASER_FID, _KOMBI_FID):
            for attribut in ("shutter", "laser_bank", "gobo_wheel", "macro",
                             "intensity", "raw", "shutter#1", "gobo_wheel#1"):
                self.st.set_programmer_value(fid, attribut, 255)
                self.assertTrue(self.st.laser_estop_active, (fid, attribut))
        self._dunkel("Programmer-Werte")

    def test_rueckgaengig_weg_loest_nicht(self):
        self.st.set_laser_estop(True)
        self.st._programmer_werte_anwenden({
            (_LASER_FID, "shutter"): 200, (_LASER_FID, "laser_bank"): 77,
            (_KOMBI_FID, "raw"): 200, (_KOMBI_FID, "shutter"): 200})
        self._dunkel("Rueckgaengig/Wiederholen")

    def test_simple_desk_loest_nicht(self):
        self.st.set_simple_desk_override(True)
        self.st.set_simple_desk_all(1, 255)
        self.assertEqual(self._werte(_KOMBI_KURZ_ADR), [255, 255, 255])
        self.st.set_laser_estop(True)
        self._dunkel("Simple Desk, alles auf 255")

    def test_dmx_eingang_loest_in_keinem_misch_modus(self):
        voll = bytes([255] * 512)
        for modus in ("HTP", "LTP", "REPLACE"):
            with self.subTest(modus=modus):
                self.st.set_laser_estop(False)
                self.loese_versuche.clear()
                self.st.apply_input_merge(1, voll, modus)
                self.assertEqual(self._werte(_KOMBI_KURZ_ADR), [255, 255, 255],
                                 "der Eingang erreicht das Kombigeraet gar nicht")
                self.st.set_laser_estop(True)
                self.st.apply_input_merge(1, voll, modus)   # laufender Strom
                self._dunkel(f"DMX-Eingang {modus}")
                self.st.clear_input_merge()

    def test_einzelkanal_von_web_und_osc_loest_nicht(self):
        self.st.set_laser_estop(True)
        for quelle, adressen in (("web", _LASER_ADR), ("osc", _KOMBI_KURZ_ADR)):
            for adresse in adressen:
                self.st.set_input_channel(1, adresse, 255, source=quelle)
        self.assertEqual(self.st.input_layer[1][_LASER_ADR[0]], 255,
                         "der Fernweg hat den Kanal gar nicht gesetzt")
        self._dunkel("Einzelkanal von Web/OSC")

    def test_ausloesen_bei_stehendem_latch_loest_nicht(self):
        """Erneut ausloesen (VC-Taste, Tastenkuerzel, Laser-Tab) ist kein
        Umschalter."""
        self.st.set_laser_estop(True)
        self.st.set_laser_estop(True)
        self.st.laser_notaus_ausloesen()
        self._dunkel("erneutes Ausloesen")


# ══════════════════════════════════════════════════════════════════════════════
# B) Das Kombigeraet bleibt dunkel, was auch immer waehrend des NOT-AUS passiert
# ══════════════════════════════════════════════════════════════════════════════

class KombiBleibtDunkelTest(_ZusammenBasis):

    def _neu_planen(self, vergessen=True):
        """Was Patchen und Laden tun: gemerkte Profile verwerfen, neu
        bestimmen, Plan neu bauen."""
        if vergessen:
            erkennung.vergiss_profile()
        self.st._laser_profile_bestimmen()
        self.st._rebuild_render_plan()

    def test_umadressieren_im_notaus(self):
        self.st.set_laser_estop(True)
        self._dunkel("vor dem Umadressieren")
        self.kombi.address = 40
        self._neu_planen()
        frame = self._dunkel("nach dem Umadressieren", kombi_adr=(40, 41, 42))
        # Die alte Adresse bleibt ebenfalls gedeckt (klebrige Maske, OUT-63).
        self.assertTrue({30, 31, 32, 40, 41, 42} <= set(self.om._laser_estop_mask[1]))
        self.assertEqual([frame[a - 1] for a in _KOMBI_KURZ_ADR], [0, 0, 0])

    def test_moduswechsel_lang_nach_kurz_im_notaus(self):
        """Im langen Modus sagt der Kanalname „Laser“. Wechselt das Geraet
        waehrend des NOT-AUS in den Kurz-Modus, gilt es weiter als Laser."""
        self.kanaele[_KOMBI_FID] = _lang()
        self.kombi.mode_name, self.kombi.channel_count = "11-channel", 4
        self._neu_planen()
        self.assertEqual(self._werte(_KOMBI_LANG_ADR)[2:], [120, 120])
        self.st.set_laser_estop(True)
        self._dunkel("langer Modus", kombi_adr=_KOMBI_LANG_ADR)
        self.kanaele[_KOMBI_FID] = _kurz()
        self.kombi.mode_name, self.kombi.channel_count = "3-channel", 3
        self._neu_planen()
        self.assertIn(_KOMBI_FID, self.st._laser_fids)
        self.assertTrue(set(_KOMBI_KURZ_ADR) <= set(self.st._laser_estop_addrs[1]))
        self._dunkel("nach dem Wechsel in den Kurz-Modus")
        self.st.set_programmer_value(_KOMBI_FID, "raw", 255)
        self._dunkel("Wert nach dem Moduswechsel")

    def test_moduswechsel_kurz_nach_lang_im_notaus(self):
        self.st.set_laser_estop(True)
        self.kanaele[_KOMBI_FID] = _lang()
        self.kombi.mode_name, self.kombi.channel_count = "11-channel", 4
        self._neu_planen()
        self._dunkel("nach dem Wechsel in den langen Modus", kombi_adr=_KOMBI_LANG_ADR)

    def test_moduswechsel_bei_ausgefallener_profil_auskunft(self):
        """Faellt die Auskunft genau beim Wechsel aus (Datenbank-Fehler), kennt
        der neue Plan das Geraet nicht mehr als Laser. Seine Adressen bleiben
        trotzdem dunkel: die Ausgabe-Maske wird bei stehendem NOT-AUS nie
        eingeengt."""
        self.st.set_laser_estop(True)
        self._dunkel("vor dem Ausfall")
        self.auskunft_ausgefallen = True       # jede Abfrage scheitert
        self._neu_planen()
        # LAS-39: ohne Auskunft gilt das Geraet weiter als Laser (vorher fiel es
        # aus dem Plan). Die Aussage hier gilt in beiden Faellen: dunkel.
        self.assertIn(_KOMBI_FID, self.st._laser_fids)
        self.st.set_programmer_value(_KOMBI_FID, "raw", 255)
        self._dunkel("Profil-Auskunft ausgefallen")

    def test_show_laden_mit_kombigeraet_im_notaus(self):
        """NOT-AUS steht, dann kommt ein anderer Patch (Show laden): ein
        Kombigeraet im Kurz-Modus auf neuer Adresse und mit einem Profil, das
        bisher niemand kannte. Der Latch bleibt, das neue Geraet ist vom ersten
        Frame an dunkel, das alte bleibt gedeckt."""
        self.st.set_laser_estop(True)
        self._dunkel("vor dem Laden")
        neu = _Kombi(31, 1, 100)
        neu.fixture_profile_id = 990040
        self.auskunft[990040] = True
        self.kanaele[31] = _kurz()
        self.st.programmer = {31: {"raw": 255}, _PAR_FID: {"intensity": 200}}
        self.st._patch_cache = [l31._PAR, neu]
        self._neu_planen()
        self.assertTrue(self.st.laser_estop_active)
        self.assertEqual(self.loese_versuche, [])
        self.assertIn(31, self.st._laser_fids)
        for _ in range(3):
            frame = self._frame()
            self.assertEqual([frame[a - 1] for a in (100, 101, 102)], [0, 0, 0])
            # der Laser der alten Show haengt physisch weiter an seiner Adresse
            self.assertEqual([frame[a - 1] for a in _LASER_ADR], [_AUS, 0, 0])
            self.assertEqual([frame[a - 1] for a in _KOMBI_KURZ_ADR], [0, 0, 0])
        self.assertEqual(frame[_PAR_DIMMER - 1], 200)

    def test_notaus_im_kurzmodus_haelt_ueber_blackout_hinweg(self):
        """Blackout an und wieder aus aendert am NOT-AUS nichts."""
        self.st.set_laser_estop(True)
        self.om.set_blackout(True)
        frame = self._frame()
        self.assertEqual([frame[a - 1] for a in _KOMBI_KURZ_ADR], [0, 0, 0])
        self.om.set_blackout(False)
        self._dunkel("nach dem Blackout")


# ══════════════════════════════════════════════════════════════════════════════
# C) Die Rueckfrage als echter Dialog
# ══════════════════════════════════════════════════════════════════════════════

class _Zustand:
    """Nur was ``loesen_mit_rueckfrage`` anfasst."""

    def __init__(self):
        self.laser_estop_active = True
        self.geloest = 0

    def laser_notaus_loesen(self):
        self.geloest += 1
        self.laser_estop_active = False


class EchteRueckfrageTest(unittest.TestCase):
    """Hier wird ``QMessageBox.warning`` NICHT ersetzt: der Dialog laeuft, eine
    Zeitschaltung bedient ihn. So ist auch geprueft, was die Knoepfe und ihre
    Vorgabe wirklich tun (Esc und Schliessen = „Abbrechen“)."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _fragen(self, bedienen):
        zustand = _Zustand()
        gesehen = []
        versuche = [0]
        takt = QTimer()
        takt.setInterval(20)

        def tick():
            versuche[0] += 1
            box = QApplication.activeModalWidget()
            if not isinstance(box, QMessageBox):
                box = next((w for w in QApplication.topLevelWidgets()
                            if isinstance(w, QMessageBox) and w.isVisible()), None)
            if box is None:
                return
            if not gesehen:
                gesehen.append((box.windowTitle(), box.text(),
                                box.standardButton(box.defaultButton()),
                                box.standardButton(box.escapeButton())
                                if box.escapeButton() is not None else None))
                bedienen(box)
            elif versuche[0] > 150:            # Notbremse: nie haengen bleiben
                box.reject()

        takt.timeout.connect(tick)
        takt.start()
        try:
            ergebnis = laser_notaus.loesen_mit_rueckfrage(None, zustand)
        finally:
            takt.stop()
        self.assertEqual(len(gesehen), 1, "die Rueckfrage ist nicht erschienen")
        return ergebnis, zustand, gesehen[0]

    def _loest_nicht(self, bedienen, was):
        ergebnis, zustand, _ = self._fragen(bedienen)
        self.assertFalse(ergebnis, was)
        self.assertEqual(zustand.geloest, 0, f"{was} hat den NOT-AUS geloest")
        self.assertTrue(zustand.laser_estop_active, was)

    def test_vorgabe_und_esc_sind_abbrechen(self):
        _, _, (titel, text, vorgabe, _esc) = self._fragen(lambda box: box.reject())
        self.assertEqual(titel, laser_notaus.TITEL)
        self.assertEqual(text, laser_notaus.TEXT)
        self.assertEqual(vorgabe, QMessageBox.StandardButton.Cancel)

    def test_esc_loest_nicht(self):
        self._loest_nicht(lambda box: QTest.keyClick(box, Qt.Key.Key_Escape), "Esc")

    def test_schliessen_loest_nicht(self):
        self._loest_nicht(lambda box: box.close(), "Schliessen der Rueckfrage")

    def test_abbrechen_loest_nicht(self):
        self._loest_nicht(
            lambda box: box.button(QMessageBox.StandardButton.Cancel).click(),
            "Abbrechen")

    def test_eingabetaste_loest_nicht(self):
        self._loest_nicht(lambda box: QTest.keyClick(box, Qt.Key.Key_Return),
                          "die Eingabetaste")

    def test_leertaste_loest_nicht(self):
        self._loest_nicht(lambda box: QTest.keyClick(box, Qt.Key.Key_Space),
                          "die Leertaste")

    def test_nur_ja_loest(self):
        ergebnis, zustand, _ = self._fragen(
            lambda box: box.button(QMessageBox.StandardButton.Yes).click())
        self.assertTrue(ergebnis)
        self.assertEqual(zustand.geloest, 1)
        self.assertFalse(zustand.laser_estop_active)

    def test_ohne_stehenden_notaus_keine_frage_und_kein_loesen(self):
        zustand = _Zustand()
        zustand.laser_estop_active = False
        self.assertFalse(laser_notaus.loesen_mit_rueckfrage(None, zustand))
        self.assertEqual(zustand.geloest, 0)


# ══════════════════════════════════════════════════════════════════════════════
# D) Die Meldung „geloest“ / „ausgeloest“ kommt bei allen Anzeigen an
# ══════════════════════════════════════════════════════════════════════════════

class _ToterAbonnent:
    """Wie die Methode eines schon abgebauten Fensters: der Aufruf scheitert
    mit „Signal source has been deleted“, und selbst ``repr`` wirft."""

    def __call__(self, *_a):
        raise RuntimeError("Signal source has been deleted")

    def __repr__(self):
        raise RuntimeError("libshiboken: Internal C++ object (Fenster) already deleted.")


class MeldungTrotzTotemAbonnentenTest(_ZusammenBasis):
    """Ein abgebautes Fenster in der Abonnentenliste darf die Meldung fuer die
    uebrigen Anzeigen nicht verschlucken. Vorher brach ``StateSync.emit`` an
    dieser Stelle ab (beim Bilden der Fehlermeldung), und alle Abonnenten
    dahinter — etwa die Anzeige im Laser-Tab — erfuhren nichts."""

    def setUp(self):
        super().setUp()
        from src.core.sync import get_sync, SyncEvent
        self.sync, self.ereignis = get_sync(), SyncEvent.LASER_ESTOP
        self.tot = _ToterAbonnent()
        self.gesehen = []

        def merke(_ereignis, daten):
            self.gesehen.append((daten, bool(self.st.laser_estop_active)))
        self.merke = merke
        liste = self.sync._subscribers[self.ereignis]
        liste.append(self.tot)                 # steht VOR der lebenden Anzeige
        self.sync.subscribe(self.ereignis, merke)
        self.addCleanup(self._abmelden)

    def _abmelden(self):
        liste = self.sync._subscribers[self.ereignis]
        liste[:] = [c for c in liste if c is not self.tot and c is not self.merke]

    def test_loesen_erreicht_die_anzeige_hinter_dem_toten_abonnenten(self):
        self.st.set_laser_estop(True)
        self.st.laser_notaus_loesen()
        self.assertEqual(self.gesehen, [(False, False)])

    def test_ausloesen_erreicht_die_anzeige_hinter_dem_toten_abonnenten(self):
        self.sync.emit(self.ereignis, None)
        self.assertEqual(len(self.gesehen), 1)

    def test_der_tote_abonnent_wird_abgemeldet(self):
        self.sync.emit(self.ereignis, None)
        self.assertFalse(any(c is self.tot
                             for c in self.sync._subscribers[self.ereignis]))


if __name__ == "__main__":
    unittest.main()
