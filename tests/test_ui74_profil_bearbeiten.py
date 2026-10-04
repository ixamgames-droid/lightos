"""UI-74: fuenf Befunde aus dem Bebildern der Geraete-Bibliothek (DOC-57).

1. Ein gespeichertes eigenes Profil laesst sich wieder oeffnen: Menue
   Datenbank -> „Fixture-Profil bearbeiten...“ (Suche, nur ``source='user'``
   editierbar, sonst ansehen / als eigenes Profil kopieren) und im Patch ein
   Kontextmenue „Profil bearbeiten“. Bearbeiten eines GEPATCHTEN Profils
   warnt, wenn Modusname, Kanalzahl oder Name sich aendern — gepatchte
   Geraete haengen an Profil-ID + Modusname, nicht an Modus-IDs.
2. Die Geraeteauswahl zeigt Herkunft und Pruefstand des Profils.
3. Links im Bibliotheks-Download-Dialog sind auf dem dunklen Grund lesbar.
4. Graue Leerzellen der Spalte „Weiß-Segment“ sind dunkel, auch wenn die
   Zeilen vor dem Polish gebaut werden.
5. Hersteller-Abgleich beim Einspielen ohne Gross/klein (kein zweiter
   Hersteller nur wegen der Schreibweise).

Alle DBs sind Temp-/Speicher-DBs — die echte fixtures.db bleibt unberuehrt.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt                                        # noqa: E402
from PySide6.QtGui import QColor                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox              # noqa: E402
from sqlalchemy import create_engine, select                         # noqa: E402
from sqlalchemy.orm import Session                                   # noqa: E402

from src.core.database import bibliothek_format as BF                # noqa: E402
from src.core.database import fixture_db as fdb                      # noqa: E402
from src.core.database.fixture_db import get_engine                  # noqa: E402
from src.core.database.models import (FixtureChannel, FixtureMode,   # noqa: E402
                                      FixtureProfile, Manufacturer,
                                      PatchedFixture,
                                      create_all_idempotent)
from src.ui.widgets import fixture_browser as browser_module         # noqa: E402
from src.ui.widgets import fixture_editor as editor_module           # noqa: E402
from src.ui.widgets import fixture_generator as gen_module           # noqa: E402
from src.ui.widgets import profil_auswahl_dialog as auswahl_module   # noqa: E402

_app = QApplication.instance() or QApplication([])
ROOT = pathlib.Path(__file__).resolve().parents[1]

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


def _profil(s, mfr, name, source, modi=(("4-Kanal", 4),), herkunft=""):
    p = FixtureProfile(manufacturer=mfr, name=name, short_name=name[:8].upper(),
                       fixture_type="par", source=source, herkunft=herkunft)
    for mname, n in modi:
        m = FixtureMode(fixture=p, name=mname, channel_count=n)
        for i in range(1, n + 1):
            m.channels.append(FixtureChannel(channel_number=i, name=f"K{i}",
                                             attribute="intensity" if i == 1
                                             else "color_r"))
    s.add(p)
    s.flush()
    return p.id


class _TempDB:
    """Temp-DB mit je einem eigenen, mitgelieferten und importierten Profil;
    alle drei Module lesen sie ueber ihr gepatchtes ``engine``."""

    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        self.engine = get_engine(path)
        self.addCleanup(self.engine.dispose)
        create_all_idempotent(self.engine)
        with Session(self.engine) as s:
            m = Manufacturer(name="Testwerk", short_name="TW")
            self.pid_user = _profil(s, m, "Eigenbau Par", "user",
                                    modi=(("4-Kanal", 4), ("6-Kanal", 6)))
            self.pid_lightos = _profil(s, m, "Bibliothek Par", "lightos")
            self.pid_qlc = _profil(s, m, "Import Par", "qlcplus")
            s.commit()
        for modul in (editor_module, auswahl_module, fdb):
            p = mock.patch.object(modul, "engine", lambda: self.engine)
            p.start()
            self.addCleanup(p.stop)
        for name in ("information", "warning"):
            p = mock.patch.object(editor_module.QMessageBox, name)
            p.start()
            self.addCleanup(p.stop)
        # Kein AppState-Patch aus einer anderen Testdatei: leer, bis ein Test
        # gepatchte Geraete vorgibt.
        self.gepatcht: list = []
        p = mock.patch.object(editor_module, "_gepatchte_geraete",
                              lambda: list(self.gepatcht))
        p.start()
        self.addCleanup(p.stop)

    def _modi(self, pid):
        with Session(self.engine) as s:
            return sorted((m.name, m.channel_count) for m in s.scalars(
                select(FixtureMode).where(FixtureMode.fixture_id == pid)))

    def _profile(self):
        with Session(self.engine) as s:
            return sorted((p.name, p.source) for p in s.scalars(select(FixtureProfile)))


# ── 1. Profil wieder oeffnen ───────────────────────────────────────────────

class MenueTest(unittest.TestCase):

    def test_menue_datenbank_hat_profil_bearbeiten(self):
        quelle = (ROOT / "src" / "ui" / "main_window.py").read_text(encoding="utf-8")
        m = re.search(r'dbm\.addAction\("Fixture-Profil bearbeiten\.\.\."\)'
                      r'\.triggered\.connect\(\s*self\.(\w+)\)', quelle)
        self.assertIsNotNone(m, "Menue Datenbank: „Fixture-Profil bearbeiten...“ fehlt")
        from src.ui.main_window import MainWindow
        self.assertTrue(callable(getattr(MainWindow, m.group(1), None)))


class AuswahlDialogTest(_TempDB, unittest.TestCase):

    def test_suche_hersteller_und_modell(self):
        alle = auswahl_module.profile_suchen("")
        self.assertEqual(len(alle), 3)
        self.assertEqual([r[2] for r in auswahl_module.profile_suchen("testwerk eigen")],
                         ["Eigenbau Par"])
        self.assertEqual(auswahl_module.profile_suchen("gibtsnicht"), [])

    def test_nur_eigene_profile_sind_bearbeitbar(self):
        dlg = auswahl_module.ProfilAuswahlDialog()
        erwartet = {"Eigenbau Par": (True, False), "Bibliothek Par": (False, True),
                    "Import Par": (False, True)}
        for i in range(dlg._liste.topLevelItemCount()):
            it = dlg._liste.topLevelItem(i)
            dlg._liste.setCurrentItem(it)
            with self.subTest(modell=it.text(1)):
                self.assertEqual((dlg.btn_bearbeiten.isEnabled(),
                                  dlg.btn_ansehen.isEnabled()), erwartet[it.text(1)])
                self.assertTrue(dlg.btn_kopieren.isEnabled())

    def test_eigenes_profil_bearbeiten_speichert_an_ort_und_stelle(self):
        dlg = editor_module.FixtureEditorDialog(fixture_id=self.pid_user)
        dlg._edit_name.setText("Eigenbau Par II")
        dlg._save()
        self.assertEqual(dlg.saved_id, self.pid_user)
        self.assertIn(("Eigenbau Par II", "user"), self._profile())

    def test_mitgeliefertes_profil_nur_ansehen(self):
        dlg = editor_module.FixtureEditorDialog(fixture_id=self.pid_lightos,
                                                nur_ansehen=True)
        self.assertFalse(dlg._btn_save.isEnabled())
        self.assertEqual(dlg._edit_name.text(), "Bibliothek Par")
        dlg._edit_name.setText("Veraendert")
        dlg._save()                     # zweiter Riegel neben dem Knopf
        self.assertIsNone(dlg.saved_id)
        self.assertIn(("Bibliothek Par", "lightos"), self._profile())

    def test_als_eigenes_profil_kopieren(self):
        dlg = editor_module.FixtureEditorDialog(fixture_id=self.pid_qlc, als_kopie=True)
        self.assertEqual(dlg._edit_name.text(), "Import Par (eigen)")
        dlg._save()
        self.assertIsNotNone(dlg.saved_id)
        self.assertNotEqual(dlg.saved_id, self.pid_qlc)
        self.assertIn(("Import Par", "qlcplus"), self._profile())
        self.assertIn(("Import Par (eigen)", "user"), self._profile())
        self.assertEqual(self._modi(dlg.saved_id), [("4-Kanal", 4)])

    def test_kein_zweites_profil_unter_gleichem_namen(self):
        dlg = editor_module.FixtureEditorDialog(fixture_id=self.pid_qlc, als_kopie=True)
        dlg._edit_name.setText("Import Par")
        dlg._save()
        self.assertIsNone(dlg.saved_id)
        self.assertEqual(sum(1 for n, _s in self._profile() if n == "Import Par"), 1)

    def test_patch_einstieg_waehlt_nach_herkunft(self):
        aufrufe = []
        with mock.patch.object(auswahl_module, "profil_oeffnen",
                               lambda _p, pid, wie: aufrufe.append((pid, wie)) or pid):
            auswahl_module.profil_bearbeiten_fuer(None, self.pid_user)
            with mock.patch.object(auswahl_module.QMessageBox, "exec"), \
                    mock.patch.object(auswahl_module.QMessageBox, "clickedButton",
                                      return_value=None):
                self.assertIsNone(
                    auswahl_module.profil_bearbeiten_fuer(None, self.pid_lightos))
        self.assertEqual(aufrufe, [(self.pid_user, auswahl_module.BEARBEITEN)])

    def test_patch_tabelle_hat_kontextmenue(self):
        from src.ui.views.patch_view import PatchView
        self.assertTrue(callable(getattr(PatchView, "_kontextmenue", None)))
        self.assertTrue(callable(getattr(PatchView, "_profil_bearbeiten", None)))


class GepatchtesProfilTest(_TempDB, unittest.TestCase):
    """Bearbeiten eines gepatchten Profils: Modus-IDs wechseln (FM-23 baut die
    Modi neu), die Patch-Verweise (Profil-ID + Modusname) halten. Was der Mensch
    am Modus aendert, wird vor dem Speichern gemeldet."""

    def _patch(self, modus="4-Kanal", n=4):
        return PatchedFixture(fid=1, label="Par links", fixture_profile_id=self.pid_user,
                              mode_name=modus, universe=1, address=1, channel_count=n)

    def test_unveraenderte_modi_brechen_den_patch_nicht(self):
        from src.core import app_state
        self.gepatcht = [self._patch()]
        with Session(self.engine) as s:
            alt_id = s.scalars(select(FixtureMode.id).where(
                FixtureMode.fixture_id == self.pid_user,
                FixtureMode.name == "4-Kanal")).one()
        dlg = editor_module.FixtureEditorDialog(fixture_id=self.pid_user)
        with mock.patch.object(editor_module.QMessageBox, "question") as frage:
            dlg._save()
        frage.assert_not_called()           # nichts betroffen -> keine Frage
        with Session(self.engine) as s:
            mode = app_state._resolve_mode(s, self._patch())
            self.assertEqual(mode.name, "4-Kanal")
            self.assertNotEqual(mode.id, alt_id)    # neue ID, Verweis haelt trotzdem

    def test_umbenannter_modus_fragt_und_nein_speichert_nicht(self):
        self.gepatcht = [self._patch()]
        dlg = editor_module.FixtureEditorDialog(fixture_id=self.pid_user)
        dlg._tabs.widget(0).mode_name = "4-Kanal neu"
        dlg._tabs.widget(0)._edit_name.setText("4-Kanal neu")
        with mock.patch.object(editor_module.QMessageBox, "question",
                               return_value=QMessageBox.StandardButton.No) as frage:
            dlg._save()
        frage.assert_called_once()
        self.assertIn("4-Kanal", frage.call_args[0][2])
        self.assertIsNone(dlg.saved_id)
        self.assertEqual(self._modi(self.pid_user), [("4-Kanal", 4), ("6-Kanal", 6)])

    def test_ja_speichert_trotzdem(self):
        self.gepatcht = [self._patch()]
        dlg = editor_module.FixtureEditorDialog(fixture_id=self.pid_user)
        dlg._tabs.widget(0)._edit_name.setText("4-Kanal neu")
        dlg._tabs.widget(0).mode_name = "4-Kanal neu"
        with mock.patch.object(editor_module.QMessageBox, "question",
                               return_value=QMessageBox.StandardButton.Yes):
            dlg._save()
        self.assertEqual(dlg.saved_id, self.pid_user)
        self.assertIn(("4-Kanal neu", 4), self._modi(self.pid_user))

    def test_folgen_einzeln(self):
        f = editor_module.profil_patch_folgen
        p = self._patch()
        self.assertEqual(f(self.pid_user, [p], [("4-Kanal", 4)]), [])
        self.assertEqual(f(None, [p], []), [])
        self.assertEqual(f(self.pid_user + 99, [p], []), [])     # anderes Profil
        self.assertIn("gibt es nicht mehr", f(self.pid_user, [p], [("X", 4)])[0])
        self.assertIn("5 statt 4", f(self.pid_user, [p], [("4-Kanal", 5)])[0])
        umb = f(self.pid_user, [p], [("4-Kanal", 4)], name_alt=("Testwerk", "A"),
                name_neu=("Testwerk", "B"))
        self.assertEqual(len(umb), 1)
        self.assertIn("alten Namen", umb[0])


# ── 2. Herkunft in der Geraeteauswahl ──────────────────────────────────────

def _herkunft_json(art="qlcplus", ok=False, lizenz="Apache-2.0"):
    h = {"art": art, "lizenz": lizenz}
    if art in BF.FREMD_ARTEN:
        h.update(urheber="QLC+-Beitragende", original="x.qxf", geaendert="umgebaut")
    return json.dumps({"quelle": {"titel": "Vorlage"}, "herkunft": h,
                       "geprueft": {"ok": ok, "wie": "gegen das Handbuch"},
                       "autor": "LightOS"})


class HerkunftTest(_TempDB, unittest.TestCase):

    def test_zeilen(self):
        def prof(source, herkunft=""):
            return SimpleNamespace(source=source, herkunft=herkunft)
        z = browser_module.herkunft_zeile
        self.assertEqual(z(prof("lightos", _herkunft_json()))[0],
                         "Herkunft: LightOS-Bibliothek (aus QLC+, überarbeitet) · ungeprüft")
        text, tipp = z(prof("lightos", _herkunft_json(ok=True)))
        self.assertTrue(text.endswith("geprüft ✓"), text)
        self.assertIn("gegen das Handbuch", tipp)
        self.assertEqual(z(prof("builtin"))[0], "Herkunft: LightOS (eingebaut) · ungeprüft")
        self.assertEqual(z(prof("user"))[0], "Herkunft: eigenes Profil · ungeprüft")
        self.assertEqual(z(prof("qlcplus"))[0], "Herkunft: QLC+-Import · ungeprüft")
        self.assertIn("heruntergeladen",
                      z(prof("qlcplus"), {"quelle": "qlcplus", "lizenz": "Apache-2.0"})[0])

    def test_auswahl_zeigt_die_zeile(self):
        with Session(self.engine) as s:
            s.get(FixtureProfile, self.pid_lightos).herkunft = _herkunft_json(ok=True)
            s.commit()
        dlg = browser_module.FixtureBrowserDialog(next_fid=1)
        it = dlg._tree.findItems("Bibliothek Par", Qt.MatchFlag.MatchRecursive)
        self.assertTrue(it)
        dlg._tree.setCurrentItem(it[0])
        self.assertEqual(dlg._lbl_herkunft.text(),
                         "Herkunft: LightOS-Bibliothek (aus QLC+, überarbeitet) · geprüft ✓")

    def test_download_nachweis_liest_nur(self):
        self.assertIsNone(browser_module.download_herkunft(self.pid_qlc, self.engine))
        with self.engine.connect() as c:
            from sqlalchemy import text
            tabellen = {r[0] for r in c.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table'"))}
        self.assertNotIn("profil_herkunft", tabellen)   # nicht angelegt


# ── 3. Linkfarbe im Download-Dialog ────────────────────────────────────────

class LinkFarbeTest(unittest.TestCase):

    def test_links_hell_auf_dunklem_grund(self):
        from PySide6.QtWidgets import QLabel
        from src.ui.widgets.bibliothek_download_dialog import BibliothekDownloadDialog
        eng = create_engine("sqlite://")
        self.addCleanup(eng.dispose)
        dlg = BibliothekDownloadDialog(engine=eng, oeffnen=None)
        links = [l for l in dlg.findChildren(QLabel) if "<a " in l.text()]
        self.assertTrue(links)
        for l in links:
            m = re.search(r'<a [^>]*style="color:\s*(#[0-9a-fA-F]{6})', l.text())
            self.assertIsNotNone(m, l.text())
            # Hell genug fuer den dunklen Grund (#333333): Helligkeit > 50 %.
            self.assertGreater(QColor(m.group(1)).lightnessF(), 0.5)


# ── 4. Graue Leerzellen der Spalte „Weiß-Segment“ ──────────────────────────

class LeerzelleTest(unittest.TestCase):
    """Die Tabs werden NICHT gezeigt — genau der Fall „Zeilen vor dem Polish
    gebaut“. Ohne Stylesheet liefert ``palette().window()`` dort das helle
    Standardgrau."""

    def _pruefe(self, brush):
        # Fensterton des dunklen Themes (bgMedium in assets/themes/dark.qss).
        self.assertEqual(brush.color().name(), "#333333")
        self.assertLess(brush.color().lightnessF(), 0.4)

    def test_editor(self):
        tab = editor_module._ModeTab("Default")
        tab.load_mode_data("Default", [
            {"name": "Rot", "attribute": "color_r", "default": 0, "highlight": 255}])
        self._pruefe(tab._tbl.item(0, editor_module.SEGMENT_COL).background())

    def test_generator(self):
        mode = gen_module.GenMode(name="Default",
                                  channels=[gen_module.GenChannel(name="Rot",
                                                                  attribute="color_r")])
        tab = gen_module._ModeTab(mode)
        self._pruefe(tab._tbl.item(0, gen_module.SEGMENT_COL).background())


# ── 5. Hersteller ohne Gross/klein beim Einspielen ─────────────────────────

def _datei(hersteller="Eurolite", modell="Par 7"):
    return {
        "format_version": 1, "hersteller": hersteller, "modell": modell,
        "kurzname": "PAR7", "typ": "par",
        "quelle": {"titel": "Handbuch"},
        "herkunft": {"art": "hersteller-handbuch", "lizenz": "eigen"},
        "autor": "LightOS", "geprueft": {"ok": False, "wie": "nur Handbuch"},
        "modi": [{"name": "1-Kanal", "kanaele": [
            {"name": "Dimmer", "attribut": "intensity", "default": 0, "highlight": 255}]}],
    }


class HerstellerSchreibweiseTest(unittest.TestCase):

    def setUp(self):
        self.eng = create_engine("sqlite://")
        self.addCleanup(self.eng.dispose)
        create_all_idempotent(self.eng)
        self.wurzel = tempfile.mkdtemp(prefix="lightos_bib_")
        self.addCleanup(shutil.rmtree, self.wurzel, True)

    def _schreiben(self, d):
        BF.schreibe(d, os.path.join(self.wurzel, BF.dateiname(d["hersteller"], d["modell"])))

    def _spielen(self):
        with Session(self.eng) as s:
            BF.einspielen(s, self.wurzel)
            s.commit()

    def _hersteller(self):
        with Session(self.eng) as s:
            return sorted((m.name, sorted(f.name for f in m.fixtures))
                          for m in s.scalars(select(Manufacturer)))

    def test_andere_schreibweise_legt_keinen_zweiten_hersteller_an(self):
        with Session(self.eng) as s:
            s.add(Manufacturer(name="Eurolite", short_name="EUROLITE"))
            s.commit()
        self._schreiben(_datei(hersteller="EuroLite"))
        self._spielen()
        self.assertEqual(self._hersteller(), [("Eurolite", ["Par 7"])])

    def test_alter_datenfehler_zieht_zum_richtigen_hersteller_um(self):
        # Stand vor der Korrektur: das Profil liegt unter „EuroLite“.
        with Session(self.eng) as s:
            s.add(Manufacturer(name="Eurolite", short_name="EUROLITE"))
            s.add(Manufacturer(name="EuroLite", short_name="EUROLITE"))
            s.commit()
            BF._anlegen(s, _datei(hersteller="EuroLite"), BF.SOURCE_LIGHTOS)
            s.commit()
        self.assertIn(("EuroLite", ["Par 7"]), self._hersteller())
        self._schreiben(_datei(hersteller="Eurolite"))      # korrigierte Datei
        self._spielen()
        with Session(self.eng) as s:
            self.assertEqual(len(s.scalars(select(FixtureProfile)).all()), 1)
        self.assertIn(("Eurolite", ["Par 7"]), self._hersteller())
        self.assertIn(("EuroLite", []), self._hersteller())


if __name__ == "__main__":
    unittest.main()
