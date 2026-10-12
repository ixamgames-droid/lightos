"""STAB-37 — ein doppeltes Profil in der Geraete-Bibliothek ist kein Verlust der Show.

**Der Befund (Bedientest QA-96, 11.10.2026):** die Demo-Show „Große
Bühnen-Show“ meldete beim Oeffnen „Show unvollstaendig geladen … SPEICHERN
SCHREIBT DEN VERLUST FEST“.

**Nachgestellt** (Demo in der Sandbox gebaut, mit einer Kopie einer gewachsenen
Geraete-Bibliothek geladen): ``load_show`` meldete „geladen — ABER 40 Teile
konnten nicht gelesen werden“, vierzigmal derselbe Satz, einer je PAR:
„Cameo / FLAT PRO 7 steht 2× in der Geraetebibliothek — genommen wurde Profil …
(builtin)“. Mit frischer Bibliothek: nichts.

**Ursache:** die Demo traegt die Profil-Nummern ihres Bau-Rechners. Auf einem
Rechner mit gewachsener Bibliothek passt die Nummer nicht, das Profil wird ueber
Hersteller und Modell gesucht — und steht dort zweimal (mitgeliefert und
importiert). Gewaehlt wird richtig (mitgeliefert, Modus passt). Der Satz dazu
ist ein Hinweis auf die BIBLIOTHEK; er stand aber im Sammler fuer verworfene
Show-Teile, und die Oberflaeche macht daraus die Verlust-Warnung.

**Jetzt:** der Hinweis hat seinen eigenen Sammler (``letzte_ladehinweise``),
einmal je Profil statt einmal je Geraet. Die Verlust-Warnung erscheint nur bei
echten Ladeproblemen; ein Hinweis allein steht in der Statuszeile.
"""
import json
import os
import tempfile
import types
import unittest
import zipfile
from unittest import mock

from sqlalchemy.orm import Session

from _fixture_quelle import frische_library     # FIXTEST-FRESH

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.show import show_file as SF

MFR, MODELL = "Doppel AG", "Zwilling 37"
FREMDE_NUMMER = 999999


def _show_json_aendern(pfad, aendern):
    """``show.json`` in der .lshow (ZIP) durch ``aendern(show)`` schicken."""
    with zipfile.ZipFile(pfad) as z:
        teile = {n: z.read(n) for n in z.namelist()}
    show = json.loads(teile["show.json"].decode("utf-8"))
    aendern(show)
    teile["show.json"] = json.dumps(show).encode("utf-8")
    with zipfile.ZipFile(pfad, "w", zipfile.ZIP_DEFLATED) as z:
        for name, daten in teile.items():
            z.writestr(name, daten)


class _MitDublette(unittest.TestCase):
    """Frische Bibliothek, darin dasselbe (Hersteller, Modell) zweimal:
    einmal mitgeliefert, einmal importiert — der Import zuerst (kleinere
    Nummer), wie in einer gewachsenen Bibliothek."""

    @classmethod
    def setUpClass(cls):
        from src.core.database.models import FixtureProfile, Manufacturer
        cls._eng = frische_library(cls)
        with Session(cls._eng) as s:
            m = Manufacturer(name=MFR, short_name="DOPP")
            s.add(m)
            s.flush()
            ids = {}
            for quelle in ("qlcplus", "builtin"):
                p = FixtureProfile(manufacturer=m, name=MODELL,
                                   short_name=f"ZW37{quelle[:3].upper()}",
                                   fixture_type="par", power_w=10, source=quelle)
                s.add(p)
                s.flush()
                ids[quelle] = p.id
            s.commit()
        cls.mitgeliefert, cls.importiert = ids["builtin"], ids["qlcplus"]

    def setUp(self):
        for sammler in (SF._ladeprobleme, getattr(SF, "_ladehinweise", {})):
            sammler.clear()
            self.addCleanup(sammler.clear)

    def _geraet(self, fid):
        return SF._patched_fixture_from_data(
            {"fid": fid, "label": f"PAR {fid}", "fixture_profile_id": FREMDE_NUMMER,
             "manufacturer_name": MFR, "fixture_name": MODELL,
             "universe": 1, "address": fid * 10}, fid)


class SammlerTests(_MitDublette):
    def test_die_dublette_ist_kein_ladeproblem(self):
        """★ Der Kern: nichts von der Show wurde verworfen."""
        pf = self._geraet(1)
        self.assertEqual(pf.fixture_profile_id, self.mitgeliefert,
                         "Vorbedingung: gewaehlt wird das mitgelieferte Profil")
        self.assertEqual(SF.letzte_ladeprobleme(), [])

    def test_sie_wird_trotzdem_gemeldet_als_hinweis(self):
        """FM-43 bleibt: wer ein Geraet sieht, das „fast“ stimmt, soll wissen,
        dass es an der Bibliothek liegt."""
        self._geraet(1)
        hinweise = SF.letzte_ladehinweise()
        self.assertEqual(len(hinweise), 1)
        self.assertIn(MODELL, hinweise[0])
        self.assertIn("2×", hinweise[0])
        self.assertIn("Dublette", hinweise[0])

    def test_vierzig_geraete_ein_hinweis(self):
        """Gemessen: 40 PARs ergaben vierzigmal denselben Satz."""
        for fid in range(1, 41):
            self._geraet(fid)
        hinweise = SF.letzte_ladehinweise()
        self.assertEqual(len(hinweise), 1, hinweise)
        self.assertIn("40 Geräte", hinweise[0])
        self.assertEqual(SF.letzte_ladeprobleme(), [])

    def test_ein_einzelnes_geraet_traegt_keine_anzahl(self):
        self._geraet(1)
        self.assertNotIn("Geräte)", SF.letzte_ladehinweise()[0])

    def test_echte_probleme_bleiben_ladeprobleme(self):
        """Gegenprobe: ein Profil, das es gar nicht gibt, ist weiter ein
        Ladeproblem (das Geraet bleibt dunkel) — und kein blosser Hinweis."""
        SF._resolve_fixture_profile_id(FREMDE_NUMMER, "Phantom GmbH", "Gibt Es Nicht 9000")
        self.assertEqual(len(SF.letzte_ladeprobleme()), 1)
        self.assertEqual(SF.letzte_ladehinweise(), [])

    def test_ein_neuer_ladevorgang_leert_die_hinweise(self):
        self._geraet(1)
        self.assertTrue(SF.letzte_ladehinweise())
        ok, _msg = SF.load_show(os.path.join(os.path.dirname(__file__), "gibt_es_nicht.lshow"))
        self.assertFalse(ok)
        self.assertEqual(SF.letzte_ladehinweise(), [],
                         "Hinweise der vorigen Show duerfen nicht stehen bleiben")


class LadenTests(_MitDublette):
    """Der ganze Weg: eine gespeicherte Show mit drei Geraeten dieses Modells,
    deren Profil-Nummer auf diesem Rechner ins Leere zeigt — wie bei einer
    Demo-Show, die auf einem anderen Rechner gebaut wurde."""

    def setUp(self):
        super().setUp()
        from src.core.app_state import get_state
        from src.core.database.models import PatchedFixture
        self.st = get_state()
        SF.reset_show()
        self.addCleanup(SF.reset_show)
        for fid in (1, 2, 3):
            self.st.add_fixture(PatchedFixture(
                fid=fid, label=f"PAR {fid}", fixture_profile_id=self.mitgeliefert,
                manufacturer_name=MFR, fixture_name=MODELL, mode_name="",
                universe=1, address=fid * 10, channel_count=4,
                fixture_type="par"), undoable=False)
        self.pfad = os.path.join(tempfile.gettempdir(), f"stab37_{os.getpid()}.lshow")
        SF.save_show(self.pfad)
        self.addCleanup(lambda: os.path.exists(self.pfad) and os.remove(self.pfad))
        _show_json_aendern(self.pfad, self._fremde_nummern)
        SF.reset_show()

    @staticmethod
    def _fremde_nummern(show):
        geraete = show["patch"]
        assert len(geraete) == 3, geraete
        for g in geraete:
            assert (g["manufacturer_name"], g["fixture_name"]) == (MFR, MODELL), g
            g["fixture_profile_id"] = FREMDE_NUMMER

    def test_laden_meldet_glatt_geladen(self):
        """★ Vorher: „geladen — ABER 3 Teile konnten nicht gelesen werden.“"""
        ok, msg = SF.load_show(self.pfad)
        self.assertTrue(ok)
        self.assertNotIn("ABER", msg, msg)
        self.assertNotIn("nicht gelesen", msg, msg)
        self.assertEqual(SF.letzte_ladeprobleme(), [])
        self.assertEqual(len(self.st.get_patched_fixtures()), 3)

    def test_der_hinweis_steht_bereit_einmal_fuer_drei_geraete(self):
        SF.load_show(self.pfad)
        hinweise = SF.letzte_ladehinweise()
        self.assertEqual(len(hinweise), 1, hinweise)
        self.assertIn("3 Geräte", hinweise[0])

    def test_alle_drei_bekommen_das_mitgelieferte_profil(self):
        SF.load_show(self.pfad)
        self.assertEqual({f.fixture_profile_id for f in self.st.get_patched_fixtures()},
                         {self.mitgeliefert})


# ── die Oberflaeche ─────────────────────────────────────────────────────────

class _Statuszeile:
    def __init__(self):
        self.texte = []

    def showMessage(self, text, _ms=0):
        self.texte.append(text)


def _fenster():
    """Stellvertreter fuer ``MainWindow._open_show_path`` (Muster: QA-50)."""
    sb = _Statuszeile()
    stub = types.SimpleNamespace(
        _demo_dateiname=None, _current_show_path=None, _aus_auto_save=False,
        _sicherung_herkunft=None, titel=[],
        statusBar=lambda: sb,
        _show_stand_merken=lambda **_k: None,
        _rebuild_recent_menu=lambda: None,
        _sync_render_toggles=lambda: None,
    )
    stub.setWindowTitle = stub.titel.append
    return stub, sb


class OberflaecheTests(unittest.TestCase):
    HINWEIS = ("„Cameo / FLAT PRO 7“ steht 2× in der Geraetebibliothek — genommen wurde "
               "Profil 1775 (builtin). Wenn das Geraet falsch aussieht, liegt es an der "
               "Dublette, nicht an der Show. (betrifft 40 Geräte)")
    PROBLEM = "load patch error: database is locked"

    def _oeffnen(self, probleme, hinweise, **kw):
        from src.ui import main_window as mw
        stub, sb = _fenster()
        gewarnt = []
        with mock.patch("src.core.show.show_file.load_show",
                        return_value=(True, "Show 'X' geladen.")), \
             mock.patch("src.core.show.show_file.letzte_ladeprobleme",
                        return_value=list(probleme)), \
             mock.patch("src.core.show.show_file.letzte_ladehinweise",
                        return_value=list(hinweise), create=True), \
             mock.patch.object(mw, "_add_recent_file", lambda _p: None), \
             mock.patch.object(mw.QMessageBox, "warning",
                               lambda *a, **k: gewarnt.append(a)):
            mw.MainWindow._open_show_path(stub, "/tmp/stab37.lshow", **kw)
        return gewarnt, sb

    def test_hinweis_allein_ist_keine_verlust_warnung(self):
        """★ Der gemeldete Fall: kein Dialog, der einen Verlust behauptet."""
        gewarnt, sb = self._oeffnen([], [self.HINWEIS])
        self.assertEqual(gewarnt, [], "ein Hinweis auf die Bibliothek ist kein Warndialog")
        self.assertTrue(any("FLAT PRO 7" in t for t in sb.texte),
                        f"der Hinweis muss trotzdem zu sehen sein: {sb.texte}")
        self.assertFalse(any("VERLUST" in t.upper() for t in sb.texte))

    def test_hinweis_allein_auch_bei_der_demo_show(self):
        demo = types.SimpleNamespace(dateiname="Buehnen_Show_2026.lshow",
                                     titel="Große Bühnen-Show")
        gewarnt, sb = self._oeffnen([], [self.HINWEIS], demo=demo)
        self.assertEqual(gewarnt, [])
        self.assertIn("FLAT PRO 7", sb.texte[-1],
                      "der Hinweis steht zuletzt in der Statuszeile, nicht verdeckt")

    def test_nichts_zu_melden_bleibt_still(self):
        gewarnt, sb = self._oeffnen([], [])
        self.assertEqual(gewarnt, [])
        self.assertEqual(sb.texte, ["Show 'X' geladen."])

    def test_echtes_ladeproblem_warnt_wie_bisher(self):
        gewarnt, _sb = self._oeffnen([self.PROBLEM], [])
        self.assertEqual(len(gewarnt), 1)
        text = " ".join(str(x) for x in gewarnt[0])
        self.assertIn("database is locked", text)
        self.assertIn("VERLUST", text)
        self.assertNotIn("Hinweis", text)

    def test_problem_und_hinweis_stehen_getrennt_im_selben_dialog(self):
        """Ein Dialog, kein zweiter — aber der Hinweis steht nicht unter
        „konnten nicht gelesen werden“."""
        gewarnt, _sb = self._oeffnen([self.PROBLEM], [self.HINWEIS])
        self.assertEqual(len(gewarnt), 1)
        text = " ".join(str(x) for x in gewarnt[0])
        vor, _trenner, nach = text.partition("Außerdem")
        self.assertIn("database is locked", vor)
        self.assertNotIn("FLAT PRO 7", vor)
        self.assertIn("FLAT PRO 7", nach)
        self.assertIn("kein Verlust", nach)


if __name__ == "__main__":
    unittest.main()
