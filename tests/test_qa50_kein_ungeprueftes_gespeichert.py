"""QA-50 — keine Erfolgsmeldung mehr ohne geprueften Erfolg.

★ **Die Fehlerklasse.** An fuenf Stellen meldete LightOS „Gespeichert" bzw.
„geladen", ohne dass irgendjemand nachgesehen hatte, ob es stimmt. Der Schaden
entsteht dabei fast nie sofort — sondern **beim naechsten Speichern**:

* Das Einsammeln des VC-Layouts scheitert still → gespeichert wird der ALTE
  Stand, die Statuszeile sagt „Gespeichert".
* Der Show-Loader verwirft tolerant einen Block → „geladen", und das naechste
  Speichern schreibt den Verlust fest.
* ``MidiMapper.load`` scheitert → es passiert gar nichts, die Oberflaeche sagt
  „✓ Mappings geladen", das naechste Speichern ueberschreibt die noch
  vollstaendige Datei mit einer leeren Liste.
* ``_save_universe_config`` schluckt Schreibfehler → der Dialog meldet
  „Gespeichert", die Ausgabe ist nach dem Neustart trotzdem weg.

**Das Vorbild stand schon im Projekt:** ``channel_groups_view`` gibt ``bool``
zurueck und der Aufrufer prueft. Diese Tests nageln fest, dass die fuenf
Stellen es jetzt genauso machen.
"""
import json
import os
import tempfile
import types
import unittest
from unittest import mock


class _Statusbar:
    def __init__(self):
        self.texte = []

    def showMessage(self, text, _ms=0):
        self.texte.append(text)


class _Log:
    def __init__(self):
        self.zeilen = []

    def __call__(self, text):
        self.zeilen.append(text)


class UniversenSchreibfehlerTest(unittest.TestCase):
    """``_save_universe_config`` gab ``None`` zurueck — es GAB keine Antwort,
    die ein Aufrufer haette pruefen koennen."""

    def test_schreibfehler_wird_gemeldet_statt_geschluckt(self):
        from src.ui.widgets import output_config as oc
        with mock.patch("builtins.open", side_effect=PermissionError("nope")):
            self.assertFalse(oc._save_universe_config([{"num": 1}]))

    def test_erfolg_gibt_true(self):
        from src.ui.widgets import output_config as oc
        with tempfile.TemporaryDirectory() as tmp:
            ziel = os.path.join(tmp, "u", "universes.json")
            with mock.patch.object(oc, "_UNIV_CONFIG_PATH", ziel):
                self.assertTrue(oc._save_universe_config([{"num": 3}]))
                with open(ziel, encoding="utf-8") as f:
                    self.assertEqual([{"num": 3}], json.load(f))

    def test_persist_output_reicht_das_ergebnis_durch(self):
        """Sonst haette die Rueckgabe niemanden erreicht: die Statuslabels
        haengen an ``_persist_output``, nicht an der Schreibfunktion."""
        from src.ui.widgets import output_config as oc
        with mock.patch.object(oc, "_load_universe_config", return_value=[]), \
             mock.patch.object(oc, "_save_universe_config", return_value=False):
            self.assertFalse(oc._persist_output(1, "Enttec", "/dev/ttyUSB0"))
        with mock.patch.object(oc, "_load_universe_config", return_value=[]), \
             mock.patch.object(oc, "_save_universe_config", return_value=True):
            self.assertTrue(oc._persist_output(1, "Enttec", "/dev/ttyUSB0"))


class MidiMappingsTest(unittest.TestCase):
    """★ Die gefaehrlichste der fuenf Stellen: aus einem LESEfehler wurde ein
    SCHREIBverlust."""

    def _mapper(self):
        from src.core.midi.midi_mapper import MidiMapper
        m = MidiMapper.__new__(MidiMapper)
        m._mappings = []
        m.replace_mappings = lambda neu: setattr(m, "_mappings", list(neu))
        return m

    def test_kaputte_datei_meldet_nicht_geladen(self):
        m = self._mapper()
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{kein json")
            pfad = f.name
        try:
            self.assertFalse(m.load(pfad))
        finally:
            os.unlink(pfad)

    def test_fehlende_datei_meldet_nicht_geladen(self):
        m = self._mapper()
        self.assertFalse(m.load("/gibt/es/nicht/mappings.json"))

    def test_gute_datei_meldet_geladen(self):
        m = self._mapper()
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump([], f)
            pfad = f.name
        try:
            self.assertTrue(m.load(pfad))
        finally:
            os.unlink(pfad)

    def test_die_ui_setzt_keinen_haken_ohne_erfolg(self):
        """★ Der Kern: der Haken „✓ Mappings geladen" stand da, egal was
        passiert war — und lud den Nutzer geradezu ein, danach zu speichern."""
        from src.ui.views import midi_view as mv
        stub = types.SimpleNamespace()
        stub._mapper = types.SimpleNamespace(load=lambda _p: False)
        stub._refresh_map_table = lambda: None
        stub._append_log = _Log()
        mv.MidiView._load_mappings(stub)
        text = " ".join(stub._append_log.zeilen)
        self.assertNotIn("✓", text, f"Haken trotz Fehlschlag: {text!r}")
        self.assertIn("NICHT geladen", text)
        self.assertIn("Speichern", text,
                      "die Folge (Ueberschreiben) gehoert in die Warnung")

    def test_die_ui_setzt_den_haken_bei_erfolg(self):
        """Positivkontrolle — eine Warnung, die immer erscheint, ist keine."""
        from src.ui.views import midi_view as mv
        stub = types.SimpleNamespace()
        stub._mapper = types.SimpleNamespace(load=lambda _p: True)
        stub._refresh_map_table = lambda: None
        stub._append_log = _Log()
        mv.MidiView._load_mappings(stub)
        self.assertIn("✓ Mappings geladen", " ".join(stub._append_log.zeilen))


class ShowLadeproblemeTest(unittest.TestCase):
    """Der tolerante Loader darf tolerant bleiben — aber nicht schweigen."""

    def test_lenient_sammelt_und_wird_je_ladevorgang_geleert(self):
        from src.core.show import show_file as sf
        sf._ladeprobleme.clear()
        sf._lenient("load patch error", ValueError("kaputt"))
        self.assertEqual(1, len(sf.letzte_ladeprobleme()))
        self.assertIn("kaputt", sf.letzte_ladeprobleme()[0])
        # Die Liste gehoert dem jeweiligen Ladevorgang: `load_show` leert sie
        # am Anfang. Ohne das truege die zweite Show die Probleme der ersten.
        self.assertIn("_ladeprobleme.clear()",
                      open(sf.__file__, encoding="utf-8").read(),
                      "load_show muss den Sammler zu Beginn leeren")

    def test_letzte_ladeprobleme_gibt_eine_kopie(self):
        """Sonst koennte ein Aufrufer den Sammler des Loaders leeren."""
        from src.core.show import show_file as sf
        sf._ladeprobleme.clear()
        sf._lenient("x", ValueError("y"))
        sf.letzte_ladeprobleme().clear()
        self.assertEqual(1, len(sf.letzte_ladeprobleme()))


class SpeichernMitLueckenTest(unittest.TestCase):
    """★★ Die Stelle mit dem groessten Schadenspotenzial: `_do_save` meldete
    „Gespeichert", obwohl ein Teil im alten Stand in der Datei landete."""

    def _stub(self, vc_kaputt: bool):
        from src.ui import main_window as mw
        sb = _Statusbar()
        stub = types.SimpleNamespace()
        stub.statusBar = lambda: sb
        stub.setWindowTitle = lambda _t: None
        stub._rebuild_recent_menu = lambda: None
        stub._backup_pre_viz11_show = lambda _p: None
        stub._state = types.SimpleNamespace()

        def kaputt():
            raise RuntimeError("Widget zerstoert")

        stub._vc_view = types.SimpleNamespace(
            to_dict=kaputt if vc_kaputt else (lambda: {"widgets": []}))
        stub._snapshots_view = None
        stub._channel_groups_view = None
        return mw, stub, sb

    def test_lueckenhaftes_speichern_meldet_nicht_einfach_gespeichert(self):
        mw, stub, sb = self._stub(vc_kaputt=True)
        gewarnt = []
        with mock.patch.object(mw, "save_show", create=True), \
             mock.patch("src.core.show.show_file.save_show"), \
             mock.patch.object(mw, "_add_recent_file", lambda _p: None), \
             mock.patch.object(mw.QMessageBox, "warning",
                               lambda *a, **k: gewarnt.append(a)):
            mw.MainWindow._do_save(stub, "/tmp/qa50_test.lshow")
        self.assertTrue(sb.texte, "keine Statusmeldung")
        self.assertIn("LUECKEN", sb.texte[-1],
                      f"Statuszeile behauptet Erfolg: {sb.texte[-1]!r}")
        self.assertTrue(gewarnt, "kein Hinweis auf den unvollstaendigen Stand")
        text = " ".join(str(x) for x in gewarnt[0])
        self.assertIn("Virtual Console", text,
                      "welcher Teil fehlt, gehoert in die Meldung")

    def test_vollstaendiges_speichern_meldet_schlicht_gespeichert(self):
        """Positivkontrolle: die Warnung darf nicht im Normalfall erscheinen —
        sonst liest sie nach zwei Tagen niemand mehr."""
        mw, stub, sb = self._stub(vc_kaputt=False)
        gewarnt = []
        with mock.patch("src.core.show.show_file.save_show"), \
             mock.patch.object(mw, "_add_recent_file", lambda _p: None), \
             mock.patch.object(mw.QMessageBox, "warning",
                               lambda *a, **k: gewarnt.append(a)):
            mw.MainWindow._do_save(stub, "/tmp/qa50_test.lshow")
        self.assertEqual([], gewarnt)
        self.assertIn("Gespeichert:", sb.texte[-1])
        self.assertNotIn("LUECKEN", sb.texte[-1])

    def test_uebersprungene_vc_widgets_werden_vor_dem_loeschen_gemeldet(self):
        """★ Der VC-Loader ueberspringt ein defektes Bedienelement (richtig so —
        eine kaputte Taste darf nicht die ganze Konsole kosten). Es steht dann
        aber nicht mehr in ``to_dict``, und **dieses Speichern loescht es
        endgueltig**. Die Warnung gehoert deshalb hierher und nicht ins Laden:
        dort war der Verlust noch nicht eingetreten."""
        mw, stub, sb = self._stub(vc_kaputt=False)
        stub._vc_view = types.SimpleNamespace(
            to_dict=lambda: {"widgets": []},
            uebersprungene_widgets=lambda: ["button: unbekannte Aktion 'xyz'"])
        gewarnt = []
        with mock.patch("src.core.show.show_file.save_show"), \
             mock.patch.object(mw, "_add_recent_file", lambda _p: None), \
             mock.patch.object(mw.QMessageBox, "warning",
                               lambda *a, **k: gewarnt.append(a)):
            mw.MainWindow._do_save(stub, "/tmp/qa50_test.lshow")
        self.assertTrue(gewarnt, "kein Hinweis auf die geloeschten Elemente")
        text = " ".join(str(x) for x in gewarnt[0])
        self.assertIn("GELOESCHT", text)
        self.assertIn("xyz", text, "der Grund gehoert in die Meldung")

    def test_gespeichert_wird_trotzdem(self):
        """Bewusste Entscheidung: ein Sammelfehler darf das Speichern nicht
        verhindern — sonst gingen auch die Teile verloren, die in Ordnung sind.
        Nur die MELDUNG aendert sich."""
        mw, stub, _sb = self._stub(vc_kaputt=True)
        gerufen = []
        with mock.patch("src.core.show.show_file.save_show",
                        side_effect=lambda *a, **k: gerufen.append(a)), \
             mock.patch.object(mw, "_add_recent_file", lambda _p: None), \
             mock.patch.object(mw.QMessageBox, "warning", lambda *a, **k: None):
            mw.MainWindow._do_save(stub, "/tmp/qa50_test.lshow")
        self.assertEqual(1, len(gerufen), "save_show wurde nicht gerufen")


if __name__ == "__main__":
    unittest.main()
