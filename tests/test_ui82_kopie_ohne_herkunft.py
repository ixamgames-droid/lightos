"""UI-82: Fixture-Editor — Kopie ohne belegbare Herkunft wird abgelehnt.

Befund (Codex-Review #934): liess sich die Herkunft der Vorlage nicht
ableiten (``herkunft_fuer`` wirft ``ProfilFehler``), speicherte der Editor die
Kopie still mit ``herkunft=""`` als eigenes Profil (``source='user'``) — und
``herkunft_fuer`` machte daraus spaeter „eigen“. Eine Kopie eines
Bibliotheksprofils oder fremden Imports verlor so ihre Lizenzangabe (UI-74).

Jetzt: Hinweis „Kopie nicht möglich“, nichts in der DB. Kopien mit ableitbarer
Herkunft (QLC+-Import, eigenes Profil, Bibliotheksprofil mit gespeicherter
Herkunft) laufen unveraendert.

Alle DBs sind Temp-DBs, der Bibliotheksordner ist ein leerer Temp-Ordner —
die echte fixtures.db bleibt unberuehrt.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                          # noqa: E402
from sqlalchemy import select                                       # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

from src.core.database import bibliothek_format as BF               # noqa: E402
from src.core.database.fixture_db import get_engine                 # noqa: E402
from src.core.database.models import (FixtureChannel, FixtureMode,  # noqa: E402
                                      FixtureProfile, Manufacturer,
                                      create_all_idempotent)
from src.ui.widgets import fixture_editor as editor_module          # noqa: E402

_app = QApplication.instance() or QApplication([])

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _profil(s, mfr, name, source, herkunft=""):
    p = FixtureProfile(manufacturer=mfr, name=name, short_name=name[:8].upper(),
                       fixture_type="par", source=source, herkunft=herkunft,
                       notes="Notiz", viz_model="par_can")
    m = FixtureMode(fixture=p, name="4-Kanal", channel_count=4)
    for i in range(1, 5):
        m.channels.append(FixtureChannel(channel_number=i, name=f"K{i}",
                                         attribute="intensity" if i == 1
                                         else "color_r"))
    s.add(p)
    s.flush()
    return p.id


def _herkunft_ofl() -> str:
    return json.dumps({
        "quelle": {"titel": "Open Fixture Library"},
        "herkunft": {"art": "ofl", "lizenz": "MIT", "urheber": "OFL-Beitragende",
                     "original": "x.json", "geaendert": "umgebaut"},
        "geprueft": {"ok": False, "wie": "nicht geprueft"},
        "autor": "Test"}, ensure_ascii=False)


class _Basis(unittest.TestCase):

    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        self.engine = get_engine(path)
        self.addCleanup(self.engine.dispose)
        create_all_idempotent(self.engine)
        with Session(self.engine) as s:
            m = Manufacturer(name="Testwerk", short_name="TW")
            self.pid_user = _profil(s, m, "Eigenbau Par", "user")
            self.pid_qlc = _profil(s, m, "Import Par", "qlcplus")
            # Bibliotheksprofil OHNE gespeicherte Herkunft und ohne Datei.
            self.pid_lightos = _profil(s, m, "Bibliothek Par", "lightos")
            self.pid_lightos_ok = _profil(s, m, "Bibliothek Spot", "lightos",
                                          herkunft=_herkunft_ofl())
            # Quelle, aus der sich nichts ableiten laesst.
            self.pid_fremd = _profil(s, m, "Fremd Par", "unbekannt")
            s.commit()
        p = mock.patch.object(editor_module, "engine", lambda: self.engine)
        p.start()
        self.addCleanup(p.stop)
        # Leerer Bibliotheksordner: ein ``lightos``-Profil ohne gespeicherte
        # Herkunft findet garantiert keine Datei.
        leer = tempfile.TemporaryDirectory()
        self.addCleanup(leer.cleanup)
        p = mock.patch.object(BF, "BIBLIOTHEK_DIR", leer.name)
        p.start()
        self.addCleanup(p.stop)
        self.meldungen: dict[str, list] = {"information": [], "warning": [],
                                           "question": []}
        for name in self.meldungen:
            p = mock.patch.object(
                editor_module.QMessageBox, name,
                lambda *a, _n=name, **k: self.meldungen[_n].append(a))
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(editor_module, "_gepatchte_geraete", lambda: [])
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch("src.core.app_state.profil_geaendert", lambda *_a: None)
        p.start()
        self.addCleanup(p.stop)

    def _anzahl(self) -> int:
        with Session(self.engine) as s:
            return len(s.scalars(select(FixtureProfile)).all())

    def _hersteller(self) -> list[str]:
        with Session(self.engine) as s:
            return sorted(m.name for m in s.scalars(select(Manufacturer)))

    def _kopieren(self, pid):
        dlg = editor_module.FixtureEditorDialog(fixture_id=pid, als_kopie=True)
        dlg._save()
        return dlg

    def _abgelehnt(self, dlg, vorher: int):
        self.assertIsNone(dlg.saved_id)
        self.assertEqual(self._anzahl(), vorher, "es wurde trotzdem gespeichert")
        titel = [a[1] for a in self.meldungen["warning"]]
        self.assertIn("Kopie nicht möglich", titel)
        text = self.meldungen["warning"][-1][2]
        self.assertIn("Herkunft", text)
        self.assertIn("nichts gespeichert", text)
        self.assertEqual(self.meldungen["information"], [], "„Gespeichert“ gemeldet")


class KopieAbgelehntTest(_Basis):

    def test_bibliotheksprofil_ohne_belegbare_herkunft(self):
        vorher = self._anzahl()
        self._abgelehnt(self._kopieren(self.pid_lightos), vorher)

    def test_unbekannte_quelle(self):
        vorher = self._anzahl()
        self._abgelehnt(self._kopieren(self.pid_fremd), vorher)

    def test_vorlage_inzwischen_geloescht(self):
        dlg = editor_module.FixtureEditorDialog(fixture_id=self.pid_qlc, als_kopie=True)
        with Session(self.engine) as s:
            s.delete(s.get(FixtureProfile, self.pid_qlc))
            s.commit()
        vorher = self._anzahl()
        dlg._save()
        self._abgelehnt(dlg, vorher)

    def test_neuer_hersteller_wird_nicht_angelegt(self):
        dlg = editor_module.FixtureEditorDialog(fixture_id=self.pid_lightos,
                                                als_kopie=True)
        dlg._cb_manufacturer.setCurrentText("Neuwerk")
        vorher = self._anzahl()
        dlg._save()
        self._abgelehnt(dlg, vorher)
        self.assertEqual(self._hersteller(), ["Testwerk"])

    def test_zweiter_riegel_beim_schreiben(self):
        """Faellt die Herkunft erst zwischen Pruefung und Schreiben weg,
        bleibt die Schreib-Sitzung ohne Commit (auch kein neuer Hersteller)."""
        dlg = editor_module.FixtureEditorDialog(fixture_id=self.pid_qlc, als_kopie=True)
        dlg._cb_manufacturer.setCurrentText("Neuwerk")
        echt = dlg._kopie_herkunft
        aufrufe = []

        def einmal_gut(s):
            aufrufe.append(1)
            if len(aufrufe) == 1:
                return echt(s)
            raise BF.ProfilFehler(["Herkunft verschwunden"])

        vorher = self._anzahl()
        with mock.patch.object(dlg, "_kopie_herkunft", einmal_gut):
            dlg._save()
        self.assertEqual(len(aufrufe), 2)
        self._abgelehnt(dlg, vorher)
        self.assertEqual(self._hersteller(), ["Testwerk"])

    def test_kein_stilles_leeres_herkunftsfeld_mehr(self):
        import inspect
        quelle = inspect.getsource(editor_module.FixtureEditorDialog._neues_profil)
        self.assertNotIn('herkunft = ""', quelle)


class KopieErlaubtTest(_Basis):

    def _kopie(self, dlg):
        self.assertIsNotNone(dlg.saved_id)
        self.assertEqual([a[1] for a in self.meldungen["warning"]], [])
        with Session(self.engine) as s:
            k = s.get(FixtureProfile, dlg.saved_id)
            return k.source, k.name, BF.herkunft_fuer(k), k.notes, k.viz_model

    def test_qlc_import_behaelt_apache(self):
        quelle, name, h, notiz, modell = self._kopie(self._kopieren(self.pid_qlc))
        self.assertEqual((quelle, name), ("user", "Import Par (eigen)"))
        self.assertEqual(h["herkunft"]["lizenz"], "Apache-2.0")
        self.assertEqual((notiz, modell), ("Notiz", "par_can"))

    def test_eigenes_profil_ist_ableitbar(self):
        """Ein eigenes Profil ohne gespeicherte Herkunft ist KEIN Fall fuer
        UI-82 — seine Herkunft ist „eigen“, die Kopie bleibt erlaubt."""
        quelle, name, h, _n, _m = self._kopie(self._kopieren(self.pid_user))
        self.assertEqual((quelle, name), ("user", "Eigenbau Par (eigen)"))
        self.assertEqual(h["herkunft"]["lizenz"], "eigen")

    def test_bibliotheksprofil_mit_gespeicherter_herkunft(self):
        _q, _n, h, _no, _m = self._kopie(self._kopieren(self.pid_lightos_ok))
        self.assertEqual(h["herkunft"]["lizenz"], "MIT")
        self.assertEqual(h["herkunft"]["art"], "ofl")


class OhneKopieUnveraendertTest(_Basis):

    def test_eigenes_profil_bearbeiten(self):
        """Bearbeiten (keine Kopie) speichert wie bisher an Ort und Stelle."""
        dlg = editor_module.FixtureEditorDialog(fixture_id=self.pid_user)
        dlg._spin_power.setValue(dlg._spin_power.value() + 5)
        vorher = self._anzahl()
        dlg._save()
        self.assertEqual(dlg.saved_id, self.pid_user)
        self.assertEqual(self._anzahl(), vorher)
        self.assertEqual([a[1] for a in self.meldungen["warning"]], [])

    def test_bibliotheksprofil_bearbeiten_bleibt_gesperrt(self):
        """Nur die Kopie wird geprueft — das Ansehen eines mitgelieferten
        Profils loest keine UI-82-Meldung aus."""
        dlg = editor_module.FixtureEditorDialog(fixture_id=self.pid_lightos)
        dlg._save()
        self.assertNotIn("Kopie nicht möglich",
                         [a[1] for a in self.meldungen["warning"]])


if __name__ == "__main__":
    unittest.main()
