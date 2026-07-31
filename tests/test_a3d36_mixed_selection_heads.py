"""A3D-36 — bei GEMISCHTER Auswahl verschwand die zweite Tilt-Bar des Spiders.

Der Position-Tab schaltet auf die Spider-Bedienung (SpiderPositionTool statt
Pan/Tilt-Regler) nur um, wenn ``_selection_is_spider`` wahr ist — und das ist ein
hartes ``all(is_dual_tilt_fixture)``. Steht neben dem Spider ein gewoehnlicher
Moving Head in der Auswahl, faellt der Tab also in den generischen Regler-Loop,
und der baut seine Regler aus dem **pro Attribut deduplizierten** Template
(``union[ch.attribute]``).

Am echten Bau gemessen (Spider ``Spider 14ch [14-Kanal]``: 0 Pan, 2 Tilt ·
``HYDRABEAM 4000 RGBW [19-Kanal]``: 4 Pan, 4 Tilt — beide **Builtins**, damit
der Test nicht an einer lokal importierten Library haengt)::

    nur Spider [1]   tilt-Regler: keine (SpiderPositionTool uebernimmt)
    nur Mover  [2]   tilt head=0 -> [2]        pan head=0 -> [2]
    GEMISCHT [1,2]   tilt head=0 -> [1, 2]     pan head=0 -> [1, 2]
                     ^ die zweite Bar des Spiders ist NIRGENDS erreichbar,
                       und der Pan-Regler zielt auf ein Geraet ohne Pan-Kanal.

Der Fix ist die Zwei-Eimer-Aufteilung, die ``_add_color_head_sliders`` seit
FM-HEADLAYOUT Slice 2 vormacht: Mehrkopf-Tilter in den einen Block (ein Regler je
Bar), der Rest in den anderen. Bewusst NICHT gebaut wurde der naheliegende
``(attribute, head)``-Schluessel fuer das ganze Template — ueber die Library
gezaehlt kommt ``raw`` in 831 Modi mehrfach vor, ``macro`` in 822, Spitzenwerte
bis 24 Vorkommen; das erzeugte auf solchen Geraeten Hunderte Regler.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout   # noqa: E402
from sqlalchemy import select                                      # noqa: E402
from sqlalchemy.orm import Session                                 # noqa: E402

from src.core.app_state import get_state, is_dual_tilt_fixture     # noqa: E402
from src.core.database.fixture_db import (engine as fdb_engine,    # noqa: E402
                                          ensure_builtins)
from src.core.database.models import PatchedFixture, FixtureProfile  # noqa: E402
from src.core.show.show_file import reset_show                     # noqa: E402
from src.ui.views.programmer_view import (ProgrammerView,          # noqa: E402
                                          AttributeSlider)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    """Profil-ID ueber den **Kurznamen** eines BUILTIN-Profils.

    ★ Bewusst nicht ueber den Anzeigenamen: der erste Wurf dieses Tests suchte
    `ZQ-B20 Mini Spider` — den gibt es nur in Davids lokal importierter Library,
    nicht in der frisch geseedeten CI-DB. Ergebnis war ein `None` aus der Query,
    das erst als `TypeError: int() argument ...` auffiel, und zwar erst in der
    CI (Fallenklasse QA-23: kein Test darf von Maschinenzustand ausserhalb des
    Repos abhaengen). Beide hier benutzten Profile sind `ensure_builtins`."""
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first())


class _Basis(unittest.TestCase):
    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        self._hosts: list = []          # Qt-GC: Wegwerf-Hosts am Leben halten
        self.state.add_fixture(PatchedFixture(
            fid=1, label="Spider1", fixture_profile_id=_pid("SPIDER14"),
            mode_name="14-Kanal", universe=1, address=1, channel_count=14,
            fixture_type="moving_head"), undoable=False)
        self.state.add_fixture(PatchedFixture(
            fid=2, label="Mover1", fixture_profile_id=_pid("HYDRA4000"),
            mode_name="19-Kanal", universe=1, address=100, channel_count=19,
            fixture_type="moving_head"), undoable=False)

    def _fx(self, fid):
        return next(f for f in self.state.get_patched_fixtures() if f.fid == fid)

    def _view(self):
        v = ProgrammerView()
        self.addCleanup(v.deleteLater)
        return v

    def _position_slider(self, fids):
        """Die Position-Regler einer Auswahl — (attribut, kopf, fids) je Regler.

        Frische View je Messung: eine wiederverwendete View liefert per
        ``findChildren`` auch die Regler frueherer Auswahlen (Qt loescht sie erst
        spaeter) — die Messung zeigte dann Geister."""
        v = self._view()
        self.state.set_selected_fids(list(fids))
        _app().processEvents()
        treffer = []
        tabs = v._main_tabs
        for i in range(tabs.count()):
            if not tabs.tabText(i).startswith("Position"):
                continue
            for s in tabs.widget(i).findChildren(AttributeSlider):
                treffer.append((s._channel.attribute, s._head,
                                tuple(f.fid for f in s._fixtures)))
        return treffer


class VoraussetzungTest(_Basis):
    def test_die_beiden_geraete_sind_wirklich_verschieden(self):
        self.assertTrue(is_dual_tilt_fixture(self._fx(1)),
                        "Spider muss 2 Tilt / 0 Pan haben, sonst misst der Test nichts")
        self.assertFalse(is_dual_tilt_fixture(self._fx(2)))


class GemischteAuswahlTest(_Basis):
    def test_zweite_bar_ist_erreichbar(self):
        """★ Der gemeldete Fehler: ein einziger tilt-Regler fuer beide Geraete."""
        tilts = [(kopf, fids) for attr, kopf, fids in self._position_slider([1, 2])
                 if attr == "tilt"]
        spider_koepfe = sorted(k for k, fids in tilts if fids == (1,))
        self.assertEqual(spider_koepfe, [0, 1],
                         "der Spider braucht einen Regler JE Bar (tilt / tilt#1)")

    def test_pan_zielt_nicht_auf_ein_geraet_ohne_pan(self):
        pans = [fids for attr, _k, fids in self._position_slider([1, 2])
                if attr == "pan"]
        self.assertTrue(pans, "der Moving Head braucht seinen Pan-Regler")
        for fids in pans:
            self.assertNotIn(1, fids,
                             "der Spider hat keinen Pan-Kanal — ein Regler auf ihm "
                             "schreibt einen Programmer-Wert ohne Kanal")

    def test_geraeteweiter_tilt_bleibt_fuer_den_mover(self):
        tilts = [(kopf, fids) for attr, kopf, fids in self._position_slider([1, 2])
                 if attr == "tilt"]
        # FM-17: „geraeteweit" ist am Regler jetzt ``head=None`` statt ``0``.
        # Vorher waren beide dasselbe; seit der Kopf-Karte ist „Kopf 1" bei
        # einem geteilten Master ein ANDERER Kanal als „das ganze Geraet".
        self.assertIn((None, (2,)), tilts,
                      "der Moving Head verliert seinen geraeteweiten Tilt-Regler")


class BestandsverhaltenTest(_Basis):
    """Die beiden reinen Faelle muessen unveraendert bleiben."""

    def test_reine_spider_auswahl_hat_weiter_keine_pan_tilt_regler(self):
        attrs = {attr for attr, _k, _f in self._position_slider([1])}
        self.assertNotIn("tilt", attrs, "SpiderPositionTool uebernimmt beide Bars")
        self.assertNotIn("pan", attrs)

    def test_reine_mover_auswahl_unveraendert(self):
        regler = self._position_slider([2])
        # FM-17: geraeteweit = ``head=None`` (vorher ``0``, s. o.).
        self.assertIn(("tilt", None, (2,)), regler)
        self.assertIn(("pan", None, (2,)), regler)
        self.assertEqual([k for a, k, _f in regler if a == "tilt"], [None],
                         "ohne Spider in der Auswahl entstehen KEINE Kopf-Regler")


class EimerTest(_Basis):
    """Die Aufteilung selbst — auch fuer die Tabs, die sie nichts angeht."""

    def test_nur_der_position_tab_teilt_auf(self):
        v = self._view()
        spider, rest = v._position_head_buckets("Color", [self._fx(1), self._fx(2)])
        self.assertEqual(spider, [], "ausserhalb von Position bleibt alles beim Alten")
        self.assertEqual([f.fid for f in rest], [1, 2])

    def test_position_trennt_nach_dual_tilt(self):
        v = self._view()
        spider, rest = v._position_head_buckets("Position",
                                                [self._fx(1), self._fx(2)])
        self.assertEqual([f.fid for f in spider], [1])
        self.assertEqual([f.fid for f in rest], [2])

    def test_kein_regler_ohne_besitzer(self):
        """Ein ``tilt#N`` auf einem Geraet, das den Kopf nicht hat, faellt im
        DMX-Pfad still auf den Default zurueck (Fehlerklasse FM-9/A5) — der
        Kopf-Regler darf also nur Geraete mit diesem Kopf tragen."""
        v = self._view()
        host = QWidget()
        self._hosts.append(host)
        lay = QVBoxLayout(host)
        v._add_per_head_tilt_sliders(lay, [self._fx(1)])
        sliders = [w for w in (lay.itemAt(i).widget() for i in range(lay.count()))
                   if isinstance(w, AttributeSlider)]
        self.assertEqual([s._head for s in sliders], [0, 1])
        for s in sliders:
            self.assertEqual([f.fid for f in s._fixtures], [1])


if __name__ == "__main__":
    unittest.main()
