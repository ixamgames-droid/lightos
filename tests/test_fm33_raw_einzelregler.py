"""FM-33: unerkannte Kanaele (``raw``) im Programmer.

Vorher stand im Reiter EIN geraeteweiter Regler, beschriftet nach einem
einzigen Rohkanal (gemessen 2026-08-25: „Grundfarbe Shutter"). Ein Zug daran
setzte am Spiider 91ch alle 21 Rohkanaele zugleich (Shutter, CTC, Zoom Fein,
Blumeneffekt …), und einzeln war keiner erreichbar.

Entschieden (2026-08-30, bestaetigt durch A am 02.10.):

(a) Einzelregler je Rohkanal **nur bei genau EINEM gewaehlten Geraet** — der
    Schluessel ``raw#k`` ist positionsbezogen, am Nachbargeraet hiesse derselbe
    Index anders;
(b) ab mehr als 8 Rohkanaelen eingeklappt;
(c) der Sammelregler bleibt, ehrlich beschriftet als „Unerkannte Kanäle (N)".

Nur eingebaute Profile (die CI hat keine importierte Bibliothek, QA-23).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                          # noqa: E402
from sqlalchemy import select                                        # noqa: E402
from sqlalchemy.orm import Session                                   # noqa: E402

from src.core.app_state import get_channels_for_patched, get_state   # noqa: E402
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins  # noqa: E402
from src.core.database.models import FixtureProfile, PatchedFixture  # noqa: E402
from src.core.dmx.universe import Universe                           # noqa: E402
from src.core.show.show_file import reset_show                       # noqa: E402
from src.ui.views.programmer_view import AttributeSlider, ProgrammerView  # noqa: E402
from src.ui.widgets.collapsible_section import CollapsibleSection    # noqa: E402

SPIIDER = ("SPIIDER", "91-Kanal Pixel RGB (Mode 7)", 91, "moving_head")
DOTZTPAR = ("DOTZTPAR", "9-Kanal Voll", 9, "par")
MACAURA = ("MACAURA", "14-Kanal (Standard)", 14, "moving_head")
ZQ01424 = ("ZQ01424", "8-Kanal RGBW", 8, "par")


def _app():
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first())


class _Basis(unittest.TestCase):

    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()

    def _patch(self, fid, geraet, addr=1):
        short, mode, n, typ = geraet
        self.state.add_fixture(PatchedFixture(
            fid=fid, label=short, fixture_profile_id=_pid(short), mode_name=mode,
            universe=1, address=addr, channel_count=n, fixture_type=typ), undoable=False)

    def _view(self, fids):
        v = ProgrammerView()
        self.addCleanup(v.deleteLater)
        self.state.set_selected_fids(list(fids))
        _app().processEvents()
        return v

    @staticmethod
    def _raw_regler(view):
        tabs = view._main_tabs
        out = []
        for i in range(tabs.count()):
            out += [s for s in tabs.widget(i).findChildren(AttributeSlider)
                    if s._channel.attribute == "raw"]
        return out

    @staticmethod
    def _sammel(regler):
        return [s for s in regler if type(s).__name__ == "_RawSammelRegler"]

    @staticmethod
    def _einzeln(regler):
        return [s for s in regler if type(s).__name__ == "_RawKanalRegler"]

    @staticmethod
    def _name(s):
        return s._display_name or s._channel.name

    def _fixture(self, fid):
        return next(x for x in self.state.get_patched_fixtures() if x.fid == fid)

    def _raw_kanaele(self, fid):
        return [c for c in get_channels_for_patched(self._fixture(fid))
                if c.attribute == "raw"]

    def _dmx(self, fid):
        """{Kanalname: DMX-Wert} aller Rohkanaele — ueber den echten Flush."""
        uni = Universe(1)
        self.state._apply_fixture_map(
            {1: uni}, {fid: dict(self.state.programmer.get(fid, {}))})
        f = self._fixture(fid)
        return {c.name: uni.get_channel(f.address + c.channel_number - 1)
                for c in self._raw_kanaele(fid)}


class EinGeraet(_Basis):

    def test_spiider_hat_einen_regler_je_rohkanal(self):
        self._patch(1, SPIIDER)
        regler = self._raw_regler(self._view([1]))
        namen = [c.name for c in self._raw_kanaele(1)]
        self.assertEqual(len(namen), 21)
        self.assertEqual([self._name(s) for s in self._einzeln(regler)], namen)
        self.assertEqual(sorted(s._head for s in self._einzeln(regler)), list(range(21)))

    def test_einzelregler_trifft_nur_seinen_kanal(self):
        self._patch(1, SPIIDER)
        regler = self._raw_regler(self._view([1]))
        vorher = self._dmx(1)
        shutter = next(s for s in self._einzeln(regler)
                       if self._name(s) == "Grundfarbe Shutter")
        shutter._slider.setValue(200)
        _app().processEvents()
        nachher = self._dmx(1)
        self.assertEqual(nachher["Grundfarbe Shutter"], 200)
        geaendert = sorted(k for k in nachher if nachher[k] != vorher[k])
        self.assertEqual(geaendert, ["Grundfarbe Shutter"],
                         "ein Einzelregler darf nur seinen Kanal bewegen")

    def test_erster_rohkanal_zieht_die_anderen_nicht_mit(self):
        """Der Basis-Schluessel ``raw`` wird beim Flush auf jeden nie einzeln
        gesetzten Rohkanal gespiegelt — ohne Verankern zoege der Regler des
        ersten Rohkanals die anderen 20 mit."""
        self._patch(1, SPIIDER)
        self.state.set_programmer_value(1, "raw", 120)
        regler = self._einzeln(self._raw_regler(self._view([1])))
        self.state._render_frame(0.02)      # wie im Betrieb: der Frame laeuft
        erster = next(s for s in regler if s._head == 0)
        erster._slider.setValue(99)
        _app().processEvents()
        nachher = self._dmx(1)
        self.assertEqual(nachher.pop(self._name(erster)), 99)
        self.assertEqual(set(nachher.values()), {120})

    def test_anker_ist_die_laufende_ausgabe_nicht_der_standard(self):
        """Review #867: treibt eine Szene die anderen Rohkanaele, darf der Zug
        am ersten sie nicht auf den Profil-Standard springen lassen — verankert
        wird, was das Live-Universe gerade ausgibt."""
        self._patch(1, SPIIDER)
        regler = self._einzeln(self._raw_regler(self._view([1])))
        fm = self.state.function_manager
        szene = fm.new_scene("Rohkanaele 77")
        szene.fade_in = 0
        for c in self._raw_kanaele(1)[1:]:   # eine Szene treibt alle anderen
            szene.set_value(1, c.channel_number, 77)
        fm.start(szene.id)
        self.addCleanup(fm.stop, szene.id)
        for _ in range(3):
            self.state._render_frame(0.05)
        erster = next(s for s in regler if s._head == 0)
        erster._slider.setValue(99)
        _app().processEvents()
        prog = self.state.programmer.get(1, {})
        self.assertEqual({prog.get(f"raw#{k}") for k in range(1, 21)}, {77})
        nachher = self._dmx(1)
        self.assertEqual(nachher.pop(self._name(erster)), 99)
        self.assertEqual(set(nachher.values()), {77})

    def test_sammelregler_zeigt_strich_sobald_ein_kanal_abweicht(self):
        """Review #867: nur ``raw#5`` gesetzt, alle anderen ungesetzt — die
        Rohkanaele stehen verschieden, also „—“ statt einer Zahl."""
        self._patch(1, SPIIDER)
        regler = self._raw_regler(self._view([1]))
        sammel = self._sammel(regler)[0]
        for k, c in enumerate(self._raw_kanaele(1)):
            self.state.set_programmer_value(1, "raw", 0, head=k)
        sammel._load_current_value()
        self.assertNotEqual(sammel._lbl_val.text(), "—", "alle gleich -> Zahl")
        fuenf = next(s for s in self._einzeln(regler) if s._head == 5)
        fuenf._slider.setValue(200)
        self.state.clear_programmer_value(1, "raw#3")
        sammel._load_current_value()
        self.assertEqual(sammel._lbl_val.text(), "—")

    def test_sammelregler_strich_auch_ohne_gesetzte_basis(self):
        self._patch(1, SPIIDER)
        regler = self._raw_regler(self._view([1]))
        sammel = self._sammel(regler)[0]
        self.state.programmer.pop(1, None)
        self.state.set_programmer_value(1, "raw", 200, head=5)
        sammel._load_current_value()
        self.assertEqual(sammel._lbl_val.text(), "—")

    def test_ohne_vorwert_verankert_der_erste_auf_dem_standard(self):
        self._patch(1, SPIIDER)
        regler = self._einzeln(self._raw_regler(self._view([1])))
        self.state._render_frame(0.02)
        erster = next(s for s in regler if s._head == 0)
        erster._slider.setValue(99)
        _app().processEvents()
        nachher = self._dmx(1)
        self.assertEqual(nachher.pop(self._name(erster)), 99)
        standard = {c.name: c.default_value for c in self._raw_kanaele(1)[1:]}
        self.assertEqual(nachher, standard)

    def test_aufbau_schreibt_nichts_in_den_programmer(self):
        """Ein Anker ist ein Programmer-Wert und uebersteuert eine laufende
        Szene — das Oeffnen des Reiters darf keine Kanaele an sich ziehen."""
        self._patch(1, SPIIDER)
        self._view([1])
        self.assertEqual(self.state.programmer.get(1, {}), {})

    def test_sammelregler_setzt_alle_auch_die_einzeln_gesetzten(self):
        self._patch(1, SPIIDER)
        regler = self._raw_regler(self._view([1]))
        sammel = self._sammel(regler)
        self.assertEqual(len(sammel), 1)
        self.assertEqual(self._name(sammel[0]), "Unerkannte Kanäle (21)")
        zoom = next(s for s in self._einzeln(regler) if self._name(s) == "Zoom Fein")
        zoom._slider.setValue(10)
        sammel[0]._slider.setValue(77)
        _app().processEvents()
        self.assertEqual(set(self._dmx(1).values()), {77})

    def test_aufbau_aendert_die_ausgabe_nicht(self):
        """Das Verankern beim Aufbau schreibt nur, was ohnehin ausgegeben wird."""
        self._patch(1, SPIIDER)
        self.state.set_programmer_value(1, "raw", 120)
        vorher = self._dmx(1)
        self.assertEqual(set(vorher.values()), {120})
        self._view([1])
        self.assertEqual(self._dmx(1), vorher)

    def test_mehr_als_acht_rohkanaele_sind_eingeklappt(self):
        self._patch(1, SPIIDER)
        v = self._view([1])
        sektionen = [s for s in v.findChildren(CollapsibleSection)
                     if s._title.startswith("Einzelne Kanäle")]
        self.assertEqual(len(sektionen), 1)
        self.assertEqual(sektionen[0]._title, "Einzelne Kanäle (21)")
        self.assertEqual(len([s for s in sektionen[0].content().findChildren(AttributeSlider)
                              if s._channel.attribute == "raw"]), 21)
        self.assertFalse(sektionen[0].is_expanded())

    def test_wenige_rohkanaele_bleiben_offen(self):
        self._patch(1, DOTZTPAR)
        v = self._view([1])
        regler = self._raw_regler(v)
        self.assertEqual([self._name(s) for s in self._einzeln(regler)],
                         ["Dimmerkurve", "Zusatzlicht 1", "Zusatzlicht 2"])
        self.assertEqual(len(self._sammel(regler)), 1)
        self.assertEqual([s for s in v.findChildren(CollapsibleSection)
                          if s._title.startswith("Einzelne Kanäle")], [])

    def test_ein_rohkanal_ein_regler_mit_kanalnamen(self):
        self._patch(1, MACAURA)
        regler = self._raw_regler(self._view([1]))
        self.assertEqual([self._name(s) for s in regler], ["CTC (Farbtemp.)"])
        self.assertEqual(self._sammel(regler), [])

    def test_kopf_zelle_gewaehlt_gleiche_einzelregler(self):
        """Der Befund kam ueber die Zell-Auswahl (``1:2``) — ein Kopf des EINEN
        Geraets ist weiter EIN Geraet."""
        self._patch(1, SPIIDER)
        v = ProgrammerView()
        self.addCleanup(v.deleteLater)
        self.state.set_selected_cells(["1:2"])
        _app().processEvents()
        regler = self._raw_regler(v)
        self.assertEqual(len(self._einzeln(regler)), 21)
        self.assertEqual(len(self._sammel(regler)), 1)

    def test_geraet_ohne_rohkanal_hat_keinen(self):
        self._patch(1, ZQ01424)
        self.assertEqual(self._raw_regler(self._view([1])), [])


class MehrereGeraete(_Basis):

    def test_zwei_geraete_nur_der_sammelregler(self):
        self._patch(1, SPIIDER, addr=1)
        self._patch(2, SPIIDER, addr=101)
        regler = self._raw_regler(self._view([1, 2]))
        self.assertEqual(len(regler), 1, [self._name(s) for s in regler])
        self.assertEqual(self._name(regler[0]), "Unerkannte Kanäle (21)")
        self.assertEqual(self._sammel(regler), regler)

    def test_gemischte_auswahl_nennt_die_spanne(self):
        self._patch(1, SPIIDER, addr=1)
        self._patch(2, DOTZTPAR, addr=101)
        regler = self._raw_regler(self._view([1, 2]))
        self.assertEqual([self._name(s) for s in regler],
                         ["Unerkannte Kanäle (je Gerät 3–21)"])

    def test_zwei_geraete_ohne_verankern(self):
        """Ohne Einzelregler kein Grund fuer ``raw#k`` im Programmer."""
        self._patch(1, SPIIDER, addr=1)
        self._patch(2, SPIIDER, addr=101)
        self._view([1, 2])
        for fid in (1, 2):
            self.assertEqual([k for k in self.state.programmer.get(fid, {})
                              if k.startswith("raw")], [])


if __name__ == "__main__":
    unittest.main()
