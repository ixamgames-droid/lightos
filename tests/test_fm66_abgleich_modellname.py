"""FM-66: der Bibliotheks-Abgleich erkennt ein Modell auch in anderer Schreibweise.

``bibliothek_format._abgleichen`` sucht zu einer Bibliotheks-Datei das schon
vorhandene Profil. Den HERSTELLER verglich es seit UI-74 ohne Gross/klein, das
MODELL aber roh (``FixtureProfile.name == modell``). Stand das Geraet als
„Par 7“ in der DB und die Datei schrieb „PAR 7“ (oder ein doppeltes
Leerzeichen war korrigiert), dann

* fand der Abgleich das eigene, schon eingespielte Profil nicht und legte ein
  ZWEITES an — das alte blieb als Leiche liegen;
* verdeckte ein gleichnamiges eigenes Profil oder Builtin die Datei nicht mehr:
  zwei Eintraege fuer dasselbe Geraet, und eine Show von einem anderen Rechner
  loest mehrdeutig auf (FM-43);
* stand neben einem im Editor bearbeiteten Import dauerhaft ein Doppel.

Verglichen wird jetzt ueber ``fixture_db.profil_schluessel`` — dieselbe
Gleichheit wie beim Abloesen (FM-63): Gross/klein und Leerzeichen zaehlen
nicht. **Satzzeichen zaehlen** (Entscheidung zu diesem Item): „PAR-56“ und
„PAR 56“ sind zwei Geraete. Herkunft: Codex-Review #935.
"""
import json
import os
import shutil
import tempfile
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.core.database import bibliothek_format as BF
from src.core.database import fixture_db as fdb
from src.core.database.models import (FixtureChannel, FixtureMode, FixtureProfile,
                                      Manufacturer, create_all_idempotent)


def _datei(hersteller="Eurolite", modell="Par 7", kurz="PAR7"):
    return {
        "format_version": 1, "hersteller": hersteller, "modell": modell,
        "kurzname": kurz, "typ": "par",
        "quelle": {"titel": "Handbuch"},
        "herkunft": {"art": "hersteller-handbuch", "lizenz": "eigen"},
        "autor": "LightOS", "geprueft": {"ok": False, "wie": "nur Handbuch"},
        "modi": [{"name": "1-Kanal", "kanaele": [
            {"name": "Dimmer", "attribut": "intensity", "default": 0, "highlight": 255}]}],
    }


class _Basis(unittest.TestCase):

    def setUp(self):
        self.eng = create_engine("sqlite://")
        self.addCleanup(self.eng.dispose)
        create_all_idempotent(self.eng)
        self.wurzel = tempfile.mkdtemp(prefix="lightos_fm66_")
        self.addCleanup(shutil.rmtree, self.wurzel, True)

    # ── Helfer ───────────────────────────────────────────────────────────────

    def _fremdes_profil(self, name, source, hersteller="Eurolite", herkunft=""):
        """Ein Profil, das NICHT aus der Bibliothek stammt (Builtin, eigenes,
        QLC+-Import)."""
        with Session(self.eng) as s:
            m = s.scalars(select(Manufacturer).where(Manufacturer.name == hersteller)).first()
            if m is None:
                m = Manufacturer(name=hersteller, short_name=hersteller[:8].upper())
                s.add(m)
            p = FixtureProfile(manufacturer=m, name=name, short_name=name[:8].upper(),
                               fixture_type="par", source=source, herkunft=herkunft)
            modus = FixtureMode(fixture=p, name="1-Kanal", channel_count=1)
            modus.channels.append(FixtureChannel(channel_number=1, name="Dimmer",
                                                 attribute="intensity"))
            s.add(p)
            s.commit()
            return p.id

    def _aus_der_bibliothek(self, **kw):
        with Session(self.eng) as s:
            pid = BF._anlegen(s, _datei(**kw), BF.SOURCE_LIGHTOS).id
            s.commit()
            return pid

    def _abgleichen(self, **kw):
        with Session(self.eng) as s:
            status = BF._abgleichen(s, _datei(**kw))
            s.commit()
            return status

    def _profile(self):
        with Session(self.eng) as s:
            return sorted((p.name, p.source) for p in s.scalars(select(FixtureProfile)))


class EigenesProfilWirdWiedergefundenTest(_Basis):

    def test_andere_gross_kleinschreibung_pflegt_das_vorhandene_profil(self):
        pid = self._aus_der_bibliothek(modell="Par 7")
        status = self._abgleichen(modell="PAR 7")
        self.assertEqual(self._profile(), [("PAR 7", "lightos")],
                         "die Datei hat ein zweites Profil angelegt")
        self.assertEqual(status, "aktualisiert")
        with Session(self.eng) as s:
            self.assertEqual(s.get(FixtureProfile, pid).name, "PAR 7",
                             "die Profil-ID muss bleiben — gepatchte Geraete haengen daran")

    def test_leerzeichen_zaehlen_nicht(self):
        self._aus_der_bibliothek(modell="LED  PAR 56")
        self._abgleichen(modell=" LED PAR 56 ")
        self.assertEqual(self._profile(), [("LED PAR 56", "lightos")])

    def test_nicht_ascii_wird_in_python_gefaltet(self):
        """SQLite faltet nur ASCII — „STRAßE“/„Straße“ faende ``lower()`` nie."""
        self._aus_der_bibliothek(modell="Bühne Ö 4")
        self._abgleichen(modell="BÜHNE ö 4")
        self.assertEqual(self._profile(), [("BÜHNE ö 4", "lightos")])

    def test_gleiche_schreibweise_bleibt_gleich(self):
        self._aus_der_bibliothek(modell="Par 7")
        self.assertEqual(self._abgleichen(modell="Par 7"), "gleich")
        self.assertEqual(self._profile(), [("Par 7", "lightos")])

    def test_satzzeichen_unterscheiden_weiterhin(self):
        """„PAR-56“ und „PAR 56“ sind zwei Geraete — Satzzeichen werden bewusst
        NICHT angeglichen."""
        self._aus_der_bibliothek(modell="LED PAR-56")
        self.assertEqual(self._abgleichen(modell="LED PAR 56"), "neu")
        self.assertEqual(self._profile(),
                         [("LED PAR 56", "lightos"), ("LED PAR-56", "lightos")])
        for a, b in (("PAR 56", "PAR.56"), ("PAR 56", "PAR56"), ("TMH-46", "TMH 46"),
                     ("X (RGBW)", "X RGBW")):
            with self.subTest(a=a, b=b):
                self.assertNotEqual(fdb.profil_schluessel("", a), fdb.profil_schluessel("", b))

    def test_exakte_schreibweise_gewinnt_unter_zwei_altbestaenden(self):
        """Altbestand aus der Zeit des Fehlers: beide Schreibweisen stehen schon
        in der DB. Gepflegt wird das Profil mit der Schreibweise der Datei."""
        alt = self._aus_der_bibliothek(modell="Par 7")
        neu = self._aus_der_bibliothek(modell="PAR 7")
        self.assertEqual(self._abgleichen(modell="PAR 7", kurz="P7NEU"), "aktualisiert")
        with Session(self.eng) as s:
            self.assertEqual(s.get(FixtureProfile, neu).short_name, "P7NEU")
            self.assertEqual(s.get(FixtureProfile, alt).short_name, "PAR7")


class FremdesProfilVerdecktTest(_Basis):

    def test_eigenes_profil_in_anderer_schreibweise_verdeckt_die_datei(self):
        for quelle in ("user", "builtin"):
            with self.subTest(quelle):
                self.setUp()
                self._fremdes_profil("Led Par 56", quelle)
                self.assertEqual(self._abgleichen(modell="LED PAR 56"), "verdeckt")
                self.assertEqual(self._profile(), [("Led Par 56", quelle)],
                                 "das Geraet steht jetzt zweimal in der Bibliothek")

    def test_bearbeiteter_import_in_anderer_schreibweise_verdeckt(self):
        marke = json.dumps({fdb.BEARBEITET_SCHLUESSEL: "fixture-editor"})
        self._fremdes_profil("led par 56", "qlcplus", herkunft=marke)
        self.assertEqual(self._abgleichen(modell="LED PAR 56"), "verdeckt")
        self.assertEqual(self._profile(), [("led par 56", "qlcplus")])

    def test_unbearbeiteter_import_wird_weiter_abgeloest(self):
        """FM-63 bleibt: das LightOS-Profil entsteht NEBEN dem Import und loest
        ihn ab — jetzt auch, wenn der Import anders geschrieben ist."""
        imp = self._fremdes_profil("led par 56", "qlcplus")
        self.assertEqual(self._abgleichen(modell="LED PAR 56"), "neu")
        self.assertEqual(self._profile(),
                         [("LED PAR 56", "lightos"), ("led par 56", "qlcplus")])
        with Session(self.eng) as s:
            self.assertIn(imp, fdb.abgeloeste_profil_ids(s))

    def test_anderer_hersteller_stoert_nicht(self):
        self._fremdes_profil("Par 7", "user", hersteller="Stairville")
        self.assertEqual(self._abgleichen(modell="PAR 7"), "neu")


class EinspielenTest(_Basis):
    """Ueber den echten Weg: Datei im Bibliotheks-Ordner -> ``einspielen``."""

    def _schreiben(self, **kw):
        d = _datei(**kw)
        BF.schreibe(d, os.path.join(self.wurzel, BF.dateiname(d["hersteller"], d["modell"])))

    def _spielen(self, stempel=None):
        with Session(self.eng) as s:
            geaendert = BF.einspielen(s, self.wurzel, stempel)
            s.commit()
        return geaendert, dict(BF.LETZTES_EINSPIELEN)

    def test_korrigierte_schreibweise_in_der_datei_ergibt_ein_profil(self):
        self._schreiben(modell="Par 7")
        self._spielen()
        self.assertEqual(self._profile(), [("Par 7", "lightos")])
        os.remove(os.path.join(self.wurzel, BF.dateiname("Eurolite", "Par 7")))
        self._schreiben(modell="PAR 7")                 # dieselbe Datei, korrigiert
        _, bericht = self._spielen()
        self.assertEqual(self._profile(), [("PAR 7", "lightos")])
        self.assertEqual(bericht["neu"], [])
        self.assertEqual(len(bericht["aktualisiert"]), 1)
        self.assertEqual(bericht["fehler"], [])

    def test_stempel_abkuerzung_erkennt_das_profil_in_anderer_schreibweise(self):
        """Unveraenderte Datei + Profil in der DB = nichts zu tun. Die Abkuerzung
        muss dieselbe Gleichheit benutzen wie der Abgleich."""
        self._aus_der_bibliothek(modell="Par  7")       # Altbestand, doppeltes Leerzeichen
        self._schreiben(modell="Par 7")
        _, erster = self._spielen()
        geaendert, zweiter = self._spielen(erster["stempel"])
        self.assertFalse(geaendert)
        self.assertEqual(zweiter["neu"] + zweiter["aktualisiert"] + zweiter["fehler"], [])
        self.assertEqual(self._profile(), [("Par 7", "lightos")])


if __name__ == "__main__":
    unittest.main()
