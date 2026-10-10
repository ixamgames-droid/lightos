"""FM-73: gleichnamige Modi — EINE Aufloesungsregel fuer alle Stellen.

FM-67 hat ``app_state._resolve_mode`` beigebracht, unter gleichnamigen Modi
den mit der gespeicherten Kanalzahl zu nehmen. Die Show-Pruefung beim Oeffnen
(``sync.validate_and_repair``) loeste den Modus aber weiter selbst auf — per
Name mit ``scalar_one_or_none()``, und im Rueckfall per Kanalzahl noch einmal.

**Nachgestellt (vor dem Fix), an einer Temp-Bibliothek und einer Temp-Show:**

* Geraet auf einem Profil mit zwei Modi „A“: die Pruefung wirft
  ``MultipleResultsFound``. Das wird je Geraet abgefangen — die Show oeffnet
  sich, das Geraet behaelt seine Werte (STAB: ``valid_fids`` steht davor).
  Aber: bei JEDEM Oeffnen steht eine Fehlerzeile „Fehler beim Prüfen:
  Multiple rows were found …“ in der Liste, das Pruef-Banner ist dauerhaft
  rot, und alle Pruefungen NACH der Modus-Suche fallen fuer dieses Geraet aus
  (Geraetetyp nachziehen, Universum, Adresse > 512).
* Geraet, dessen Modusname im Profil fehlt, und das Profil hat zwei Modi mit
  seiner Kanalzahl (voellig normal, kein doppelter Name noetig): dieselbe
  Ausnahme im Rueckfall. Der Modus wird NIE repariert, die Fehlerzeile kommt
  bei jedem Oeffnen wieder.

Jetzt gibt es die Regel einmal (``src/core/database/modus_wahl.py``); die
Show-Pruefung, ``_resolve_mode`` und die beiden Dialoge, die den Modus eines
gepatchten Geraets aus einer Liste suchten, fragen sie.

Alle DBs sind Temp-DBs — die echte fixtures.db bleibt unberuehrt.
"""
from __future__ import annotations

import io
import os
import shutil
import tempfile
import tokenize
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select                                    # noqa: E402
from sqlalchemy.orm import Session                               # noqa: E402

from src.core import app_state                                   # noqa: E402
from src.core.app_state import AppState                          # noqa: E402
from src.core.database import fixture_db as FDB                  # noqa: E402
from src.core.database.fixture_db import get_engine              # noqa: E402
from src.core.database.models import (                           # noqa: E402
    FixtureChannel, FixtureMode, FixtureProfile, Manufacturer, PatchedFixture)
from src.core.sync import validate_and_repair                    # noqa: E402

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Reihenfolge = ID-Reihenfolge. Zwei Modi „A“ (doppelter Name) und zwei Modi
#: mit 8 Kanaelen (gleiche Kanalzahl, verschiedene Namen — der Normalfall).
MODI = (("A", 4), ("A", 6), ("B", 8), ("C", 8))


def _temp_bibliothek(fall) -> tuple[object, int]:
    """Leere Temp-Bibliothek mit EINEM Profil; ``fixture_db._engine`` zeigt
    waehrend des Tests darauf (Muster: ``tests/_fixture_quelle.py``)."""
    verzeichnis = tempfile.mkdtemp(prefix="lightos_fm73_")
    alt = FDB._engine
    motor = get_engine(os.path.join(verzeichnis, "fixtures.db"))
    FDB._engine = motor

    def zurueck():
        FDB._engine = alt
        motor.dispose()
        shutil.rmtree(verzeichnis, ignore_errors=True)

    fall.addCleanup(zurueck)
    with Session(motor) as s:
        p = FixtureProfile(manufacturer=Manufacturer(name="Testwerk", short_name="TW"),
                           name="Doppel", short_name="DOPPEL", fixture_type="par",
                           source="user")
        for name, n in MODI:
            m = FixtureMode(fixture=p, name=name, channel_count=n)
            for i in range(1, n + 1):
                m.channels.append(FixtureChannel(
                    channel_number=i, name=f"{name}{n}-K{i}", attribute="intensity"))
        s.add(p)
        s.commit()
        return motor, p.id


def _geraet(fid, pid, mode_name, channel_count, address, **mehr) -> PatchedFixture:
    werte = dict(fid=fid, label=f"G{fid}", fixture_profile_id=pid,
                 mode_name=mode_name, channel_count=channel_count,
                 universe=1, address=address, fixture_type="other",
                 manufacturer_name="Testwerk", fixture_name="Doppel")
    werte.update(mehr)
    return PatchedFixture(**werte)


class ShowOeffnenTest(unittest.TestCase):
    """Die Show-Pruefung beim Oeffnen, an echter Temp-Show + Temp-Bibliothek."""

    def setUp(self):
        self.motor, self.pid = _temp_bibliothek(self)
        self.show_dir = tempfile.mkdtemp(prefix="lightos_fm73_show_")
        self.addCleanup(shutil.rmtree, self.show_dir, ignore_errors=True)
        self.pfad = os.path.join(self.show_dir, "show.db")
        self.state = AppState()
        self.state.open_show(self.pfad)
        self.addCleanup(lambda: self.state._show_engine.dispose())

    def _patchen(self, *geraete):
        with self.state._session() as s:
            s.add_all(geraete)
            s.commit()
        self.state._reload_patch_cache()

    def _zeile(self, fid):
        with self.state._session() as s:
            f = s.execute(select(PatchedFixture)
                          .where(PatchedFixture.fid == fid)).scalar_one()
            return f.mode_name, f.channel_count, f.fixture_type

    def _fuer(self, issues, fid):
        return [i for i in issues if f"PatchedFixture[{fid}]" in i.location]

    def test_doppelter_modusname_gibt_keinen_prueffehler(self):
        self._patchen(_geraet(1, self.pid, "A", 6, 1))
        issues = validate_and_repair(self.state, fix=True)
        fehler = [str(i) for i in self._fuer(issues, 1) if i.severity == "error"]
        self.assertEqual(fehler, [],
                         "ein doppelter Modusname darf die Pruefung nicht werfen")
        # Der Modus ist da — also wird nichts „repariert“.
        self.assertEqual(self._zeile(1)[:2], ("A", 6))

    def test_pruefungen_nach_der_modus_suche_laufen_weiter(self):
        """Vor dem Fix brach die Ausnahme den Rest der Geraete-Pruefung ab:
        kein Geraetetyp-Abgleich, keine Universums-/Adress-Pruefung."""
        self._patchen(_geraet(1, self.pid, "A", 6, 510))       # 510+6-1 > 512
        issues = validate_and_repair(self.state, fix=True)
        texte = [i.message for i in self._fuer(issues, 1)]
        self.assertTrue(any("> 512" in t for t in texte), texte)
        self.assertEqual(self._zeile(1)[2], "par",
                         "Geraetetyp wurde nicht aus dem Profil nachgezogen")

    def test_rueckfall_bei_zwei_modi_gleicher_kanalzahl_repariert(self):
        """Kein doppelter Name noetig: Modus „weg“ fehlt, zwei Modi haben 8
        Kanaele. Vor dem Fix: Ausnahme, keine Reparatur, bei jedem Oeffnen."""
        self._patchen(_geraet(2, self.pid, "weg", 8, 1))
        issues = validate_and_repair(self.state, fix=True)
        meine = self._fuer(issues, 2)
        self.assertEqual([str(i) for i in meine if i.severity == "error"], [])
        self.assertTrue(any(i.auto_fixed and "'B'" in i.message for i in meine),
                        [str(i) for i in meine])
        self.assertEqual(self._zeile(2)[:2], ("B", 8))        # erster nach ID
        # Zweiter Durchlauf (= naechstes Oeffnen): nichts mehr zu melden.
        nochmal = self._fuer(validate_and_repair(self.state, fix=True), 2)
        self.assertEqual([str(i) for i in nochmal], [])

    def test_rueckfall_ohne_passende_kanalzahl_nimmt_den_ersten_modus(self):
        self._patchen(_geraet(3, self.pid, "weg", 99, 1))
        validate_and_repair(self.state, fix=True)
        self.assertEqual(self._zeile(3)[:2], ("A", 4))

    def test_show_oeffnen_selbst_meldet_keinen_prueffehler(self):
        """Der ganze Weg: Show mit dem Geraet schliessen und wieder oeffnen —
        die Meldungen von ``open_show`` kommen ueber SHOW_LOADED."""
        self._patchen(_geraet(1, self.pid, "A", 6, 1),
                      _geraet(2, self.pid, "weg", 8, 20))
        from src.core.sync import SyncEvent
        gesehen = []

        def merken(_ereignis, daten):
            gesehen.append(daten)

        self.state.sync.subscribe(SyncEvent.SHOW_LOADED, merken)
        self.addCleanup(self.state.sync.unsubscribe, SyncEvent.SHOW_LOADED, merken)
        self.state.open_show(self.pfad)
        self.assertEqual(len(gesehen), 1)
        fehler = [str(i) for i in gesehen[0]["issues"]
                  if "PatchedFixture[" in i.location and i.severity == "error"]
        self.assertEqual(fehler, [])
        self.assertEqual(len(self.state.get_patched_fixtures()), 2)

    def test_sync_und_resolve_mode_meinen_denselben_modus(self):
        """Nach der Reparatur muss ``_resolve_mode`` genau den Modus liefern,
        den die Show-Pruefung eingetragen hat — sonst sind es zwei Regeln."""
        faelle = (("A", 6), ("A", 4), ("A", 10), ("weg", 8), ("weg", 6), ("weg", 99))
        self._patchen(*[_geraet(10 + k, self.pid, n, c, 1 + 20 * k)
                        for k, (n, c) in enumerate(faelle)])
        vorher = {}
        with Session(self.motor) as s:
            for k, (n, c) in enumerate(faelle):
                m = app_state._resolve_mode(s, SimpleNamespace(
                    fixture_profile_id=self.pid, mode_name=n, channel_count=c))
                vorher[10 + k] = (m.name, m.channel_count)
        validate_and_repair(self.state, fix=True)
        for k, (n, c) in enumerate(faelle):
            fid = 10 + k
            with self.subTest(fall=(n, c)):
                name, zahl, _typ = self._zeile(fid)
                if n == "weg":                       # repariert -> eingetragen
                    self.assertEqual((name, zahl), vorher[fid])
                else:                                # Name vorhanden -> bleibt
                    self.assertEqual((name, zahl), (n, c))


class EineRegelTest(unittest.TestCase):
    """Die Regel steht an EINER Stelle, und alle fragen sie."""

    def _modi(self):
        return [SimpleNamespace(id=i + 1, name=n, channel_count=c)
                for i, (n, c) in enumerate(MODI)]

    def _wahl(self, name, zahl, modi=None):
        from src.core.database.modus_wahl import modus_waehlen
        m = modus_waehlen(self._modi() if modi is None else modi, name, zahl)
        return None if m is None else (m.name, m.channel_count)

    def test_regel(self):
        self.assertEqual(self._wahl("A", 6), ("A", 6))
        self.assertEqual(self._wahl("A", 4), ("A", 4))
        self.assertEqual(self._wahl("A", 10), ("A", 4))
        self.assertEqual(self._wahl("A", None), ("A", 4))
        self.assertEqual(self._wahl("A", 8), ("A", 4))     # Name schlaegt Kanalzahl
        self.assertEqual(self._wahl("weg", 8), ("B", 8))
        self.assertEqual(self._wahl("weg", 99), ("A", 4))
        self.assertIsNone(self._wahl("A", 4, modi=[]))

    def test_reihenfolge_der_liste_ist_egal_es_zaehlt_die_id(self):
        """``fixture_db.get_modes`` sortiert nicht — die Regel muss es tun."""
        self.assertEqual(self._wahl("A", 10, modi=list(reversed(self._modi()))),
                         ("A", 4))
        self.assertEqual(self._wahl("weg", 8, modi=list(reversed(self._modi()))),
                         ("B", 8))

    def test_resolve_mode_fragt_die_gemeinsame_regel(self):
        motor, pid = _temp_bibliothek(self)
        from src.core.database import modus_wahl
        merker = SimpleNamespace(name="Attrappe", channel_count=1)
        f = SimpleNamespace(fixture_profile_id=pid, mode_name="A", channel_count=6)
        with mock.patch.object(modus_wahl, "modus_waehlen",
                               return_value=merker) as attrappe:
            with Session(motor) as s:
                self.assertIs(app_state._resolve_mode(s, f), merker)
        self.assertEqual(attrappe.call_count, 1)

    def test_show_pruefung_loest_den_modus_nicht_mehr_selbst_auf(self):
        """Statisch, ohne Kommentare: in ``sync.py`` steht keine eigene
        Namens-/Kanalzahl-Abfrage auf ``FixtureMode`` mehr."""
        with open(os.path.join(WURZEL, "src", "core", "sync.py"),
                  encoding="utf-8") as f:
            text = f.read()
        code = " ".join(t.string for t in tokenize.generate_tokens(
            io.StringIO(text).readline) if t.type != tokenize.COMMENT)
        for verboten in ("FixtureMode . name ==", "FixtureMode . channel_count ==",
                         "scalar_one_or_none"):
            with self.subTest(muster=verboten):
                self.assertNotIn(verboten, code)
        self.assertIn("modus_waehlen", code)


class DialogeTest(unittest.TestCase):
    """Die zwei Dialoge, die den Modus eines Geraets aus ``get_modes`` suchten."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.motor, self.pid = _temp_bibliothek(self)

    def test_kanal_ranges_dialog_zeigt_die_kanaele_des_richtigen_modus(self):
        """Der Dialog liest ``ch.ranges`` an abgehaengten Objekten — das geht
        mit ``get_modes`` (laedt die Bereiche nicht mit) ohnehin nicht, und der
        Dialog wird derzeit nirgends geoeffnet. Geprueft wird deshalb nur die
        Modus-WAHL, mit Modi, deren Kanaele ihre Bereiche schon tragen."""
        from src.ui.widgets import channel_range_lock_dialog as modul
        modi = [SimpleNamespace(id=i + 1, name=n, channel_count=c, channels=[
                    SimpleNamespace(channel_number=k, name=f"{n}{c}-K{k}",
                                    attribute="intensity", ranges=[])
                    for k in range(1, c + 1)])
                for i, (n, c) in enumerate(MODI)]
        with mock.patch.object(modul.fdb, "get_modes", return_value=modi):
            for name, zahl, erwartet in (("A", 6, "A6"), ("A", 4, "A4"),
                                         ("weg", 8, "B8")):
                with self.subTest(modus=(name, zahl)):
                    dlg = modul.ChannelRangeLockDialog(
                        _geraet(1, self.pid, name, zahl, 1), mock.MagicMock())
                    self.addCleanup(dlg.deleteLater)
                    # Vor dem Fix: bei „A“ immer die 4 Kanaele des aelteren,
                    # bei fehlendem Namen die des ersten Modus.
                    self.assertEqual([c.name for c in dlg._channels],
                                     [f"{erwartet}-K{k}" for k in range(1, zahl + 1)])

    def test_geraet_bearbeiten_waehlt_den_richtigen_modus_vor(self):
        from src.ui.views.patch_view import PatchFixtureEditDialog
        zustand = mock.MagicMock()
        zustand.get_patched_fixtures.return_value = []
        for name, zahl in (("A", 4), ("A", 6)):
            with self.subTest(modus=(name, zahl)):
                dlg = PatchFixtureEditDialog(zustand, _geraet(1, self.pid, name, zahl, 1))
                self.addCleanup(dlg.deleteLater)
                # Vor dem Fix gewann immer der LETZTE gleichnamige Eintrag.
                self.assertEqual(tuple(dlg._combo_mode.currentData()), (name, zahl))


class SpeichernTest(unittest.TestCase):
    """Woher doppelte Modusnamen kamen — und dass sie nicht mehr entstehen."""

    def test_eindeutiger_name(self):
        from src.core.database.modus_wahl import eindeutiger_modusname
        vergeben: set[str] = set()
        namen = [eindeutiger_modusname(n, vergeben) for n in ("A", "A", "B", "A")]
        self.assertEqual(namen, ["A", "A (2)", "B", "A (3)"])
        lang = "x" * 80
        zweiter = [eindeutiger_modusname(lang, vergeben) for _ in range(2)][1]
        self.assertLessEqual(len(zweiter), 80)             # Spaltenbreite
        self.assertTrue(zweiter.endswith(" (2)"))

    def test_generator_meldet_doppelte_modusnamen(self):
        from src.ui.widgets.fixture_generator import (GenChannel, GeneratorModel,
                                                      GenMode, validate_model)
        modell = GeneratorModel(manufacturer="Testwerk", model="Zwilling", modes=[
            GenMode("A", [GenChannel("Dimmer", "intensity")]),
            GenMode("A", [GenChannel("Dimmer", "intensity"), GenChannel("Rot", "color_r")]),
        ])
        fehler = [t for s, t in validate_model(modell) if s == "error"]
        self.assertTrue(any("doppelt" in t and "„A“" in t for t in fehler), fehler)
        modell.modes[1].name = "B"
        self.assertFalse(any("doppelt" in t for _s, t in validate_model(modell)))

    def test_generator_speichert_keine_gleichnamigen_modi(self):
        motor, _pid = _temp_bibliothek(self)
        kanal = {"name": "Dimmer", "attribute": "intensity"}
        neu = FDB.create_user_profile({
            "manufacturer": "Testwerk", "name": "Zwilling", "short_name": "ZW",
            "modes": [{"name": "A", "channels": [kanal]},
                      {"name": "A", "channels": [kanal, kanal]},
                      {"name": "B", "channels": [kanal]}],
        }, engine=motor)
        with Session(motor) as s:
            modi = s.execute(select(FixtureMode.name, FixtureMode.channel_count)
                             .where(FixtureMode.fixture_id == neu)
                             .order_by(FixtureMode.id)).all()
        self.assertEqual([tuple(m) for m in modi], [("A", 1), ("A (2)", 2), ("B", 1)])

    def test_qxf_import_speichert_keine_gleichnamigen_modi(self):
        from src.core.database.qxf_import import QXF_NS, import_qxf_file
        motor, _pid = _temp_bibliothek(self)
        modus = ('<Mode Name="Standard"><Channel Number="0">Rot</Channel>'
                 '{mehr}</Mode>')
        xml = (f'<?xml version="1.0" encoding="UTF-8"?>'
               f'<FixtureDefinition xmlns="{QXF_NS}">'
               f'<Manufacturer>Testwerk</Manufacturer><Model>QXF-Zwilling</Model>'
               f'<Type>Color Changer</Type>'
               f'<Channel Name="Rot" Preset="IntensityRed"/>'
               f'<Channel Name="Gruen" Preset="IntensityGreen"/>'
               + modus.format(mehr="")
               + modus.format(mehr='<Channel Number="1">Gruen</Channel>')
               + '</FixtureDefinition>')
        fd, pfad = tempfile.mkstemp(suffix=".qxf")
        self.addCleanup(lambda: os.path.exists(pfad) and os.remove(pfad))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(xml)
        with Session(motor) as s:
            self.assertTrue(import_qxf_file(pfad, s, {}))
            s.commit()
            modi = s.execute(
                select(FixtureMode.name, FixtureMode.channel_count)
                .join(FixtureProfile, FixtureProfile.id == FixtureMode.fixture_id)
                .where(FixtureProfile.name == "QXF-Zwilling")
                .order_by(FixtureMode.id)).all()
        self.assertEqual([tuple(m) for m in modi],
                         [("Standard", 1), ("Standard (2)", 2)])


if __name__ == "__main__":
    unittest.main()
