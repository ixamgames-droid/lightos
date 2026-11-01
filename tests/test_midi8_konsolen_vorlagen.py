"""MIDI-8: Pult-Vorlagen in der Controller-Bibliothek + Mapping-Generator.

Befund (Konsolen-Check 2026-10-05): Die Controller-Bibliothek kannte nur
MIDI-Controller. Was ein Lichtpult senden muss, damit LightOS es versteht
(MIDI-Noten aus einem Makro, MIDI Show Control), stand nirgends am Geraet. Und
„MIDI-Mapping-Profil erzeugen" ging nur fuer den APC mini — bei jedem anderen
Profil kam „Fuer die Vorlage … ist noch kein Generator hinterlegt."

Geprueft wird:

* die Vorlagen sind ladbar, je Pult mit Hilfetexten; herstellereigene
  Befehlsformen sind als **Beispiel** gekennzeichnet (keine geratenen Befehle
  als Tatsache);
* jede MSC-Beispiel-SysEx einer Vorlage wird vom LightOS-Parser verstanden;
* der Generator erzeugt auch fuer andere Profile (nanoKONTROL2, Pult-Vorlage)
  ein Mapping-Profil, der APC mini bleibt beim bisherigen Profil;
* der Browser bietet die Aktion fuer andere Profile an, zeigt die Vorlagen und
  den Hinweis, dass Hersteller-Wings nicht anschliessbar sind;
* die Anleitung „Externe Pulte" nennt die Vorlagen und die Grenze.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest as _pytest                                        # noqa: E402
from PySide6.QtWidgets import QApplication                     # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets         # noqa: E402

from src.core.controllers.controller_library import ControllerLibrary  # noqa: E402

_app = QApplication.instance() or QApplication([])

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANLEITUNG = os.path.join(REPO, "docs", "anleitung_externe_pulte",
                         "ANLEITUNG_EXTERNE_PULTE.md")

PULT_IDS = ("pult_grandma2", "pult_grandma3", "pult_magicq", "pult_titan",
            "pult_allgemein_msc")


@_pytest.fixture(autouse=True)
def _keine_fenster_uebrig():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _lib():
    lib = ControllerLibrary()
    lib.ensure_loaded()
    return lib


class VorlagenLadbarTest(unittest.TestCase):

    def test_pult_vorlagen_sind_in_der_bibliothek(self):
        lib = _lib()
        for pid in PULT_IDS:
            with self.subTest(pid):
                p = lib.find(pid)
                self.assertIsNotNone(p, f"Vorlage {pid} fehlt")
                self.assertEqual(p.device_type, "console_template")
                self.assertTrue(p.pult_vorlagen, "keine Hilfetexte")
                for zeile in p.pult_vorlagen:
                    self.assertTrue(zeile.get("zweck"))
                    self.assertTrue(zeile.get("am_pult"))
                    self.assertTrue(zeile.get("in_lightos"))

    def test_herstellerbefehle_sind_als_beispiel_gekennzeichnet(self):
        """Nur MSC (offener Standard) darf ohne Beispiel-Marke stehen."""
        lib = _lib()
        for pid in PULT_IDS:
            for zeile in lib.find(pid).pult_vorlagen:
                with self.subTest(pid=pid, zweck=zeile.get("zweck")):
                    if not zeile.get("msc"):
                        self.assertIs(zeile.get("beispiel"), True)

    def test_roundtrip_behaelt_vorlagen(self):
        from src.core.controllers.controller_library import ControllerProfile
        p = _lib().find("pult_grandma3")
        q = ControllerProfile.from_dict(p.to_dict())
        self.assertEqual(q.pult_vorlagen, p.pult_vorlagen)

    def test_msc_beispiele_versteht_der_parser(self):
        from src.core.midi import msc
        gefunden = 0
        for pid in PULT_IDS:
            for zeile in _lib().find(pid).pult_vorlagen:
                hexs = zeile.get("msc")
                if not hexs:
                    continue
                gefunden += 1
                raw = [int(b, 16) for b in hexs.split()]
                with self.subTest(pid=pid, msc=hexs):
                    cmd = msc.parse_msc(raw, own_device=127)
                    self.assertIsNotNone(cmd, "LightOS versteht die Vorlage nicht")
                    self.assertEqual(cmd.name, zeile["msc_befehl"])
        self.assertGreater(gefunden, 0)


class GeneratorTest(unittest.TestCase):

    def test_anderes_profil_bekommt_ein_mapping(self):
        from src.core.controllers.mapping_generator import (
            erzeuge_mapping_profil, kann_mapping_erzeugen)
        from src.core.midi.midi_mapper import (ACTION_EXECUTOR_FADER,
                                               ACTION_EXECUTOR_GO)
        p = _lib().find("behringer_x_touch_mini")
        self.assertTrue(kann_mapping_erzeugen(p))
        prof = erzeuge_mapping_profil(p)
        self.assertTrue(prof.mappings)
        aktionen = {m.action for m in prof.mappings}
        self.assertIn(ACTION_EXECUTOR_FADER, aktionen)
        self.assertIn(ACTION_EXECUTOR_GO, aktionen)
        # Executor-Nummern laufen ab 1, hoechstens 20 je Art.
        for aktion in (ACTION_EXECUTOR_FADER, ACTION_EXECUTOR_GO):
            params = [int(m.param) for m in prof.mappings if m.action == aktion]
            self.assertEqual(params, list(range(1, len(params) + 1)))
            self.assertLessEqual(len(params), 20)

    def test_reiner_cc_controller_bekommt_fader(self):
        from src.core.controllers.mapping_generator import erzeuge_mapping_profil
        from src.core.midi.midi_mapper import ACTION_EXECUTOR_FADER
        prof = erzeuge_mapping_profil(_lib().find("korg_nanokontrol2"))
        self.assertTrue(prof.mappings)
        self.assertTrue(all(m.action == ACTION_EXECUTOR_FADER and m.msg_type == "cc"
                            for m in prof.mappings))

    def test_pult_vorlage_note_n_ist_go_von_executor_n(self):
        from src.core.controllers.mapping_generator import erzeuge_mapping_profil
        from src.core.midi.midi_mapper import ACTION_EXECUTOR_GO
        prof = erzeuge_mapping_profil(_lib().find("pult_grandma3"))
        gos = [m for m in prof.mappings if m.action == ACTION_EXECUTOR_GO]
        self.assertEqual(len(gos), 20)
        self.assertEqual(prof.name.count("Vorlage"), 1, prof.name)
        for m in gos:
            self.assertEqual(m.msg_type, "note_on")
            self.assertEqual(int(m.param), m.data1)
            self.assertEqual(m.channel, 1)     # MIDI-Kanal 1
            self.assertEqual(m.port_filter, "")

    def test_apc_mini_bleibt_beim_bisherigen_profil(self):
        from src.core.controllers.mapping_generator import erzeuge_mapping_profil
        from src.core.input.profile import create_default_apc_mini_profile
        neu = erzeuge_mapping_profil(_lib().find("akai_apc_mini"))
        alt = create_default_apc_mini_profile()
        self.assertEqual(neu.name, alt.name)
        self.assertEqual([m.name for m in neu.mappings],
                         [m.name for m in alt.mappings])

    def test_profil_ohne_noten_und_ccs_hat_keinen_generator(self):
        from src.core.controllers.mapping_generator import kann_mapping_erzeugen
        self.assertFalse(kann_mapping_erzeugen(_lib().find("enttec_dmx_usb_pro")))

    def test_dateiname_ohne_pfadzeichen(self):
        from src.core.controllers.controller_library import (ControllerControl,
                                                             ControllerProfile)
        from src.core.controllers.mapping_generator import erzeuge_mapping_profil
        p = ControllerProfile(id="x", manufacturer="A/B", model="C:D",
                              controls=[ControllerControl(type="note",
                                                          range=[1, 2])])
        prof = erzeuge_mapping_profil(p)
        for zeichen in '/\\:*?"<>|':
            self.assertNotIn(zeichen, prof.name)


class BrowserTest(unittest.TestCase):

    def _dialog(self):
        from src.ui.widgets.controller_browser import ControllerBrowserDialog
        dlg = ControllerBrowserDialog(midi_only=True)
        self.addCleanup(dlg.deleteLater)
        return dlg

    def _waehle(self, dlg, pid):
        from PySide6.QtCore import Qt
        for i in range(dlg._list.count()):
            if dlg._list.item(i).data(Qt.ItemDataRole.UserRole) == pid:
                dlg._list.setCurrentRow(i)
                return
        self.fail(f"{pid} nicht in der MIDI-Liste")

    def test_aktion_fuer_anderes_profil(self):
        from PySide6.QtWidgets import QMessageBox
        from src.core.input import profile as prof_mod
        gespeichert, meldungen = [], []
        alt_save = prof_mod.InputProfile.save
        alt_info = QMessageBox.information
        prof_mod.InputProfile.save = lambda self: gespeichert.append(self) or "/x.json"
        QMessageBox.information = staticmethod(
            lambda *a, **k: meldungen.append(a[2] if len(a) > 2 else ""))
        try:
            dlg = self._dialog()
            self._waehle(dlg, "korg_nanokontrol2")
            self.assertTrue(dlg._btn_mapping.isEnabled())
            dlg._create_mapping_profile()
        finally:
            prof_mod.InputProfile.save = alt_save
            QMessageBox.information = alt_info
        self.assertEqual(len(gespeichert), 1)
        self.assertTrue(gespeichert[0].mappings)
        self.assertNotIn("kein Generator", " ".join(meldungen))

    def test_pult_vorlage_zeigt_hilfetexte_und_wing_hinweis(self):
        dlg = self._dialog()
        self._waehle(dlg, "pult_grandma3")
        text = dlg._details.toPlainText()
        self.assertIn("Beispiel", text)
        self.assertIn("F0 7F", text)
        self.assertIn("proprietär", text)
        self.assertIn("nicht anschließbar", text)


class AnleitungTest(unittest.TestCase):

    def test_anleitung_nennt_vorlagen_und_grenze(self):
        with open(ANLEITUNG, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("Pult-Vorlagen", text)
        self.assertIn("**Controller-Profile…**", text)
        self.assertIn("grundsätzlich nicht anschließbar", text)
