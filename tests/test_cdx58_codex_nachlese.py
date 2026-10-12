"""CDX-58: Codex-Befunde zu bereits gemergten PRs (#984, #985, #991, #992).

* TOOL-25 (#985): der Lint verschluckte haengende Funktionsverweise, sobald
  der Funktionskatalog LEER war (letzte Funktion geloescht) — und meldete
  umgekehrt ein uebrig gebliebenes ``function_id`` an Aktionstypen, die das
  Feld gar nicht lesen (``lint_show --strict`` rot bei gueltiger Show).
* TOOL-25 (#985): das „Issues"-Banner zaehlte nur Fehler und Warnungen; der
  Hinweis „Snaps widersprechen sich" erschien allein nie von selbst.
* MIDI-3 (#991): zwei baugleiche Pulte mit Alt-Mappings (ALSA-Nummer) fielen
  nach dem Neustecken beide auf das erste Geraet; eine Modellnummer am
  Namensende („Launchkey 61") wurde als Index abgeschnitten.
* VCB-41 (#984) und TOOL-25: die Anleitungen nennen das neue Verhalten.
* Backlog (#992): eine offene Sichtpruefung darf nicht in einer ``done``-Zeile
  stehen — ``backlog_compact`` archiviert sie sonst mit.

Alle Shows hier sind kleine Attrappen als Dict.
"""
from __future__ import annotations

import os
import sys
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from src.core.capability import validate as V  # noqa: E402
from src.core.midi.midi_manager import MidiMessage  # noqa: E402
import src.core.midi.midi_manager as mgr  # noqa: E402
import src.core.midi.midi_mapper as mm  # noqa: E402


def _lies(*teile) -> str:
    with open(os.path.join(REPO, *teile), encoding="utf-8") as fh:
        return fh.read()


def _show(widgets, functions=(), mit_katalog=True):
    show = {"version": "1.1", "virtual_console": {"widgets": list(widgets)}}
    if mit_katalog:
        show["functions"] = {"functions": list(functions)}
    return show


def _dangling(show):
    return [f for f in V.validate_show_dict(show) if f.code == "VC-DANGLING"]


class LeererKatalogTest(unittest.TestCase):
    """validate.py: ``known_fids and …`` schluckte den Befund bei leerem Katalog."""

    def test_letzte_funktion_geloescht_wird_gemeldet(self):
        knopf = {"type": "VCButton", "caption": "Regen", "action": "Toggle",
                 "function_id": 16}
        treffer = _dangling(_show([knopf], functions=[]))
        self.assertEqual(1, len(treffer), V.format_findings(treffer))
        self.assertIn("16", treffer[0].message)

    def test_mehrfachaktion_bei_leerem_katalog(self):
        knopf = {"type": "VCButton", "caption": "Kombi", "action": "Toggle",
                 "actions": [{"type": "function", "function_id": 404}]}
        treffer = _dangling(_show([knopf], functions=[]))
        self.assertEqual(1, len(treffer), V.format_findings(treffer))
        self.assertIn("actions[0].function_id 404", treffer[0].message)

    def test_katalog_als_leere_liste(self):
        show = _show([{"type": "VCButton", "caption": "X", "function_id": 3}],
                     mit_katalog=False)
        show["functions"] = []
        self.assertEqual(1, len(_dangling(show)))

    def test_ohne_funktionsblock_kein_fehlalarm(self):
        """Fehlt der Block ganz (Teil-Dict, z. B. nur die VC), ist der Katalog
        UNBEKANNT — dann wird weiterhin nichts gemeldet."""
        knopf = {"type": "VCButton", "caption": "Regen", "function_id": 16,
                 "actions": [{"type": "function", "function_id": 404}]}
        self.assertEqual([], _dangling(_show([knopf], mit_katalog=False)))

    def test_vorhandene_funktion_bleibt_ruhig(self):
        knopf = {"type": "VCButton", "caption": "Regen", "function_id": 16}
        show = _show([knopf], functions=[{"id": 16, "type": "Scene", "name": "S"}])
        self.assertEqual([], _dangling(show))


class AktionstypTest(unittest.TestCase):
    """Nur ``function`` und ``effect_action`` lesen ``actions[n].function_id``
    (``VCButton._execute_extra``)."""

    FUNKTIONEN = [{"id": 1, "type": "Scene", "name": "S"}]

    def _knopf(self, *aktionen):
        return {"type": "VCButton", "caption": "Kombi", "action": "Toggle",
                "actions": list(aktionen)}

    def test_rest_an_anderen_aktionstypen_ist_inert(self):
        for typ in ("library_snap", "snapshot", "blackout", "stop_all",
                    "clear", "clear_non_vc", "tap"):
            show = _show([self._knopf({"type": typ, "function_id": 404})],
                         functions=self.FUNKTIONEN)
            self.assertEqual([], _dangling(show), typ)

    def test_function_und_effect_action_werden_geprueft(self):
        for typ in ("function", "effect_action"):
            show = _show([self._knopf({"type": typ, "function_id": 404})],
                         functions=self.FUNKTIONEN)
            treffer = _dangling(show)
            self.assertEqual(1, len(treffer), typ)
            self.assertIn("404", treffer[0].message)

    def test_strict_lint_bleibt_gruen_bei_gueltiger_show(self):
        """``lint_show --strict`` wertet jede Warnung als Fehler."""
        show = _show([self._knopf(
            {"type": "library_snap", "snap_id": 5, "function_id": 404},
            {"type": "function", "function_id": 1, "mode": "on"})],
            functions=self.FUNKTIONEN)
        show["library"] = {"folders": [], "snaps": [
            {"id": 5, "name": "S", "folder": "", "values": {}}]}
        befunde = [f for f in V.validate_show_dict(show)
                   if f.severity in (V.ERROR, V.WARNING)]
        self.assertEqual([], befunde, V.format_findings(befunde))


class _Etikett:
    """Attrappe fuer das Banner-Label (kein Fenster noetig)."""

    def __init__(self):
        self.sichtbar = None
        self.text = ""
        self.stil = ""

    def hide(self):
        self.sichtbar = False

    def show(self):
        self.sichtbar = True

    def setText(self, t):
        self.text = t

    def setStyleSheet(self, s):
        self.stil = s


class BannerTest(unittest.TestCase):
    """main_window: das Banner zaehlte den Hinweis (Schwere ``info``) nicht."""

    def _banner(self, issues):
        from src.core import sync
        from src.ui.main_window import MainWindow
        alt = sync.validate_and_repair
        fenster = types.SimpleNamespace(_state=object(), _lbl_validation=_Etikett())
        sync.validate_and_repair = lambda state, fix=True: list(issues)
        try:
            MainWindow._refresh_validation_banner(fenster)
        finally:
            sync.validate_and_repair = alt
        return fenster._lbl_validation

    def _issue(self, schwere, text="x"):
        from src.core.sync import ValidationIssue
        return ValidationIssue(schwere, "VC VCButton 'Gelb Blau'", text)

    def test_hinweis_allein_zeigt_das_banner(self):
        etikett = self._banner([self._issue("info", "Snap 44 überschreibt Snap 43")])
        self.assertTrue(etikett.sichtbar)
        self.assertIn("1 Hinweis", etikett.text)
        self.assertNotIn("Issues", etikett.text)
        # Hinweis sieht nicht wie Warnung/Fehler aus
        self.assertNotIn("#ff4444", etikett.stil)
        self.assertNotIn("#ffaa00", etikett.stil)
        self.assertEqual(1, len(etikett._cached_issues))

    def test_mehrzahl(self):
        etikett = self._banner([self._issue("info"), self._issue("info")])
        self.assertIn("2 Hinweise", etikett.text)

    def test_warnung_und_fehler_wie_bisher(self):
        etikett = self._banner([self._issue("warn"), self._issue("info")])
        self.assertTrue(etikett.sichtbar)
        self.assertIn("1 Issues", etikett.text)
        self.assertIn("#ffaa00", etikett.stil)
        etikett = self._banner([self._issue("error"), self._issue("warn")])
        self.assertIn("2 Issues", etikett.text)
        self.assertIn("#ff4444", etikett.stil)

    def test_saubere_show_ohne_banner(self):
        self.assertFalse(self._banner([]).sichtbar)

    def test_zusammenfassung_ist_rein(self):
        from src.core.sync import banner_zusammenfassung
        self.assertIsNone(banner_zusammenfassung([]))
        text, farbe = banner_zusammenfassung([self._issue("info")])
        self.assertIn("Hinweis", text)
        self.assertTrue(farbe.startswith("#"))

    def test_laden_oeffnet_fuer_hinweis_keinen_dialog(self):
        """Ein Hinweis kann gewollt sein: er steht im Banner, unterbricht das
        Laden aber nicht mit einem Dialog."""
        quelle = _lies("src", "ui", "main_window.py")
        kopf = quelle.index("def _on_show_loaded")
        block = quelle[kopf:kopf + 900]
        self.assertIn("('warn', 'error')", block)
        self.assertNotIn("'info'", block)


ZWEI_ALT_A = "APC MINI:APC MINI MIDI 1 20:0"
ZWEI_ALT_B = "APC MINI:APC MINI MIDI 1 24:0"
ZWEI_NEU_A = "APC MINI:APC MINI MIDI 1 28:0"
ZWEI_NEU_B = "APC MINI:APC MINI MIDI 1 32:0"


def _msg(port):
    return MidiMessage(port_name=port, channel=1, msg_type="note_on",
                       data1=5, data2=127)


class _FakeMidi:
    def __init__(self, eingaenge=()):
        self._eingaenge = list(eingaenge)

    def subscribe(self, cb):
        pass

    def offene_eingaenge(self):
        return list(self._eingaenge)


class ZweiBaugleicheTest(unittest.TestCase):
    """midi_manager._geraet_ziel: beide Alt-Mappings bekamen Ordinal 1."""

    def test_alt_nummern_verteilen_sich_in_reihenfolge(self):
        ports = [ZWEI_NEU_A, ZWEI_NEU_B]
        alt = [ZWEI_ALT_A, ZWEI_ALT_B]
        self.assertTrue(mgr.geraet_passt(ZWEI_ALT_A, ZWEI_NEU_A, ports, alt))
        self.assertFalse(mgr.geraet_passt(ZWEI_ALT_A, ZWEI_NEU_B, ports, alt))
        self.assertTrue(mgr.geraet_passt(ZWEI_ALT_B, ZWEI_NEU_B, ports, alt))
        self.assertFalse(mgr.geraet_passt(ZWEI_ALT_B, ZWEI_NEU_A, ports, alt))

    def test_ein_pult_mit_zwei_alten_nummern_bleibt_ein_pult(self):
        """Mappings desselben Pults aus zwei Sitzungen (20:0, spaeter 24:0):
        steckt nur EIN Geraet, greifen beide darauf."""
        ports = [ZWEI_NEU_A]
        alt = [ZWEI_ALT_A, ZWEI_ALT_B]
        for name in alt:
            self.assertTrue(mgr.geraet_passt(name, ZWEI_NEU_A, ports, alt), name)

    def test_noch_vorhandene_nummer_belegt_ihr_geraet(self):
        """Eine Nummer gibt es noch (exakt), die andere nicht: das verwaiste
        Mapping geht an das FREIE Pult, nicht an das schon belegte."""
        ports = [ZWEI_ALT_B, ZWEI_NEU_B]          # 24:0 steckt noch, 32:0 ist neu
        alt = [ZWEI_ALT_A, ZWEI_ALT_B]
        self.assertTrue(mgr.geraet_passt(ZWEI_ALT_B, ZWEI_ALT_B, ports, alt))
        self.assertTrue(mgr.geraet_passt(ZWEI_ALT_A, ZWEI_NEU_B, ports, alt))
        self.assertFalse(mgr.geraet_passt(ZWEI_ALT_A, ZWEI_ALT_B, ports, alt))

    def test_ohne_geschwister_wie_bisher(self):
        ports = [ZWEI_NEU_A, ZWEI_NEU_B]
        self.assertTrue(mgr.geraet_passt(ZWEI_ALT_B, ZWEI_NEU_A, ports))
        self.assertFalse(mgr.geraet_passt(ZWEI_ALT_B, ZWEI_NEU_B, ports))

    def test_mapper_loest_am_richtigen_pult_aus(self):
        """Ende-zu-Ende durch ``MidiMapper._on_midi``."""
        alt_mgr = mm.get_midi_manager
        fake = _FakeMidi([ZWEI_NEU_A, ZWEI_NEU_B])
        mm.get_midi_manager = lambda: fake
        try:
            mapper = mm.MidiMapper.__new__(mm.MidiMapper)
            mapper._learn_mode = False
            mapper._learn_callback = None
            erstes = mm.MidiMapping(name="A", port_filter=ZWEI_ALT_A,
                                    channel=1, data1=5)
            zweites = mm.MidiMapping(name="B", port_filter=ZWEI_ALT_B,
                                     channel=1, data1=5)
            self.assertEqual(ZWEI_ALT_B, zweites.midi_in.device)
            mapper._mappings = [erstes, zweites]
            ausgeloest = []
            mapper._handle_inbound_mapping = (
                lambda mapping, msg: ausgeloest.append((mapping.name, msg.port_name)))
            mapper._on_midi(_msg(ZWEI_NEU_A))
            mapper._on_midi(_msg(ZWEI_NEU_B))
        finally:
            mm.get_midi_manager = alt_mgr
        self.assertEqual([("A", ZWEI_NEU_A), ("B", ZWEI_NEU_B)], ausgeloest)


class ModellnummerTest(unittest.TestCase):
    """midi_manager._WIN_INDEX: die Endzahl ist nur dort ein Index, wo das
    Backend wirklich einen anhaengt (rtmidi unter Windows)."""

    def setUp(self):
        self._alt = mgr._INDEX_BACKEND

    def tearDown(self):
        mgr._INDEX_BACKEND = self._alt

    def test_modellnummer_bleibt_ohne_index_backend(self):
        mgr._INDEX_BACKEND = False        # WinMM-Rohname, macOS, Linux
        self.assertEqual("Launchkey 61", mgr.port_basisname("Launchkey 61"))
        ports = ["Launchkey 49", "Launchkey 61"]
        self.assertFalse(mgr.geraet_passt("Launchkey 61", "Launchkey 49", ports))
        self.assertTrue(mgr.geraet_passt("Launchkey 61", "Launchkey 61", ports))
        # das 49er steckt allein: die Bindung des 61ers wandert NICHT dorthin
        self.assertFalse(mgr.geraet_passt("Launchkey 61", "Launchkey 49",
                                          ["Launchkey 49"]))
        self.assertEqual("Launchkey 61",
                         mgr.stabiler_portname("Launchkey 61", ports))
        self.assertIsNone(mgr.loese_portnamen_auf("Launchkey 61", ["Launchkey 49"]))

    def test_rtmidi_windows_schneidet_nur_den_index_ab(self):
        mgr._INDEX_BACKEND = True
        self.assertEqual("Launchkey 61", mgr.port_basisname("Launchkey 61 1"))
        self.assertEqual("APC MINI", mgr.port_basisname("APC MINI 1"))
        ports = ["Launchkey 49 0", "Launchkey 61 1"]
        self.assertTrue(mgr.geraet_passt("Launchkey 61 3", "Launchkey 61 1", ports))
        self.assertFalse(mgr.geraet_passt("Launchkey 61 3", "Launchkey 49 0", ports))

    def test_alsa_nummer_unabhaengig_vom_backend(self):
        for an in (False, True):
            mgr._INDEX_BACKEND = an
            self.assertEqual("APC MINI:APC MINI MIDI 1",
                             mgr.port_basisname(ZWEI_ALT_A))

    def test_vorgabe_folgt_plattform_und_backend(self):
        self.assertEqual(sys.platform == "win32" and not mgr._USE_WINMM
                         and mgr.RTMIDI_OK, self._alt)


class DokuTest(unittest.TestCase):

    def test_solo_ausnahme_gleiche_funktion_deutsch(self):
        text = _lies("docs", "anleitung_vc_widgets", "17_container.md")
        self.assertIn("dieselbe Funktion", text)
        self.assertIn("Zwei Knöpfe, dieselbe Funktion", text)
        # die pauschale Aussage steht nirgends mehr ohne die Ausnahme
        for zeile in text.splitlines():
            if "automatisch aus" in zeile and "Solo" in zeile:
                self.assertIn("dieselbe Funktion", zeile, zeile[:80])

    def test_solo_ausnahme_gleiche_funktion_englisch(self):
        text = _lies("docs", "anleitung_vc_widgets", "17_container.en.md")
        self.assertIn("same function", text)
        self.assertIn("Two buttons, same function", text)
        for zeile in text.splitlines():
            if "switched off automatically" in zeile or "switches off all other" in zeile:
                self.assertIn("same function", zeile, zeile[:80])

    def test_komponentendoku_nennt_activator(self):
        text = _lies("docs", "components", "vc", "vc_button.md")
        self.assertIn("deactivate_for_solo(activator", text)
        self.assertIn("VCB-41", text)

    def test_anleitung_nennt_die_neuen_lint_meldungen(self):
        text = _lies("docs", "ANLEITUNG.md")
        for teil in ("VC-SNAP-DANGLING", "VC-SNAP-KONFLIKT", "VC-DANGLING",
                     "Hinweis", "lint_show.py"):
            self.assertIn(teil, text, teil)

    def test_meldungscodes_der_doku_gibt_es_im_code(self):
        quelle = _lies("src", "core", "capability", "validate.py")
        for code in ("VC-SNAP-DANGLING", "VC-SNAP-KONFLIKT", "VC-DANGLING"):
            self.assertIn(f'"{code}"', quelle, code)


class BacklogTest(unittest.TestCase):
    """Eine offene Sichtpruefung steht als EIGENE offene Zeile im Backlog."""

    @classmethod
    def setUpClass(cls):
        from tools import backlog_compact as bc
        cls.bc = bc
        with open(os.path.join(REPO, "BACKLOG.md"), encoding="utf-8") as fh:
            cls.zeilen = fh.read().splitlines()
        cls.rows = {r.id: r for r in bc.parse_rows(cls.zeilen)}

    def test_sichtpruefungen_sind_eigene_offene_zeilen(self):
        for neu, alt in (("QA-94", "VIZ-83"), ("QA-95", "VIZ-92")):
            self.assertTrue(neu in self.rows, f"{neu} fehlt im Backlog")
            row = self.rows[neu]
            self.assertFalse(row.is_done, neu)
            self.assertIn(alt, row.line)

    def test_done_zeilen_tragen_keine_offene_pruefung_mehr(self):
        for rid in ("VIZ-83", "VIZ-92"):
            if rid not in self.rows:      # schon archiviert: dann ist es gut
                continue
            status = self.rows[rid].status_low
            self.assertNotIn("offen", status, rid)
            self.assertIn("qa-9", status, rid)

    def test_verdichten_laesst_die_pruefung_stehen(self):
        _rest, archiviert = self.bc.archive_split(self.zeilen)
        ids = {r.id for r in archiviert}
        self.assertFalse({"QA-94", "QA-95"} & ids)


if __name__ == "__main__":
    unittest.main()
