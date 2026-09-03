"""QA-72 — die Herkunft eines Profils steht im Datensatz, nicht in der Rechtschreibung.

``FixtureProfile.source`` sagt, durch welchen **Kanal** ein Profil hereinkam. Der
QXF-Importer stempelte darauf ``"qlcplus"`` — fuer **jede** eingelesene Datei,
unabhaengig davon, woher sie stammte.

**Gemessen (03.09.2026, gewachsene Bibliothek):** 11 handgemachte Eigenbau-Profile
tragen dasselbe Etikett wie die 1730 echten QLC+-Definitionen, und
``source='user'`` — was Editor und Generator eigentlich setzen — kommt **0-mal**
vor. Erkennbar waren die Eigenbauten nur an Tippfehlern in Hersteller- UND
Modellnamen, deutschen Kanalnamen und der unveraenderten Editor-Vorgabe
``Neuer Kanal 1…14``. Das erklaert QA-61 und QA-68 nachtraeglich: man kann ein
nur-lokales Profil am Datensatz gar nicht erkennen.

Jede ``.qxf`` bringt aber eine Angabe **ueber sich selbst** mit — den
``<Creator>``-Block mit Werkzeug, Version und **Autor**. Der wurde beim Import
schlicht weggeworfen (verifiziert: 0 Treffer auf ``Creator|Author`` im Importer,
und das Schema hatte kein Feld dafuer).

★ Der Autor ist ausserdem **Vorbedingung fuer PROC-11**: Apache-2.0 §4(c)
verlangt die Namensnennung, und sie war bisher gar nicht erfuellbar.

★★ **Was hier bewusst NICHT passiert:** ``source`` wird nicht umgedeutet und
keine bestehende Zeile umetikettiert. Genau EINE Stelle baut auf dem Wert —
``fixture_db._ist_dual_tilt_spider``, die Spider-Autokorrektur greift nur bei
QLC+-Importen. Eines der 11 Eigenbau-Profile IST ein Spider und bekommt diese
Korrektur heute, *weil* es falsch etikettiert ist. Ein Umetikettieren waere eine
stille Verhaltensaenderung an einem Geraet am Rig. Die Herkunft kommt deshalb
DANEBEN, nicht statt.
"""
from __future__ import annotations
import io
import os
import unittest
import xml.etree.ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.database.qxf_import import herkunft_aus_creator

_NS = "http://www.qlcplus.org/FixtureDefinition"


def _root(creator_xml: str):
    return ET.fromstring(
        f'<FixtureDefinition xmlns="{_NS}">{creator_xml}</FixtureDefinition>')


class CreatorBlockTest(unittest.TestCase):

    def test_werkzeug_version_und_autor(self):
        """Der Normalfall einer echten QLC+-Bibliotheksdatei."""
        r = _root("<Creator><Name>Q Light Controller Plus</Name>"
                  "<Version>4.12.3 GIT</Version><Author>NiKoyes</Author></Creator>")
        self.assertEqual(herkunft_aus_creator(r),
                         "Q Light Controller Plus 4.12.3 GIT · NiKoyes")

    def test_ohne_creator_block__leer(self):
        """Eine handgetippte Datei bringt oft gar keinen Block mit. Leer ist die
        ehrliche Antwort — und genau der Hinweis, dass sie nicht aus dem
        QLC+-Bestand stammt."""
        self.assertEqual(herkunft_aus_creator(_root("")), "")

    def test_nur_autor(self):
        r = _root("<Creator><Author>Jemand</Author></Creator>")
        self.assertEqual(herkunft_aus_creator(r), "Jemand")

    def test_nur_werkzeug_ohne_autor(self):
        r = _root("<Creator><Name>Fixture Editor</Name><Version>1.0</Version></Creator>")
        self.assertEqual(herkunft_aus_creator(r), "Fixture Editor 1.0")

    def test_leere_felder_erzeugen_keine_trennzeichen_ruine(self):
        """`" · "` mit nichts davor oder dahinter waere schlechter als leer."""
        r = _root("<Creator><Name></Name><Version></Version><Author></Author></Creator>")
        self.assertEqual(herkunft_aus_creator(r), "")

    def test_laenge_ist_gedeckelt(self):
        """Die Spalte ist VARCHAR(200); eine Datei darf sie nicht sprengen."""
        r = _root(f"<Creator><Author>{'x' * 500}</Author></Creator>")
        self.assertLessEqual(len(herkunft_aus_creator(r)), 200)


class SchemaTest(unittest.TestCase):

    def test_das_modell_hat_die_spalte(self):
        from src.core.database.models import FixtureProfile
        self.assertIn("provenance", FixtureProfile.__table__.columns)

    def test_bestehende_bibliothek_wird_migriert(self):
        """★ Die teuerste Falle bei einer neuen Spalte: ohne ALTER TABLE ist
        JEDE bestehende `fixtures.db` unbrauchbar, weil das ORM alle Spalten
        abfragt („no such column"). Die Bibliothek ist die eine Datei, die der
        Nutzer nicht mal eben neu anlegt (Lehre VIZ-50a/pixel_order)."""
        import tempfile
        from sqlalchemy import create_engine, text
        from src.core.database.models import migrate_fixtures_db
        with tempfile.TemporaryDirectory() as d:
            pfad = os.path.join(d, "alt.db")
            eng = create_engine(f"sqlite:///{pfad}")
            with eng.begin() as c:
                # Eine Bibliothek OHNE die neue Spalte nachstellen.
                c.execute(text(
                    "CREATE TABLE fixtures (id INTEGER PRIMARY KEY, "
                    "manufacturer_id INTEGER, name VARCHAR, short_name VARCHAR, "
                    "fixture_type VARCHAR, power_w INTEGER, notes TEXT, "
                    "source VARCHAR, viz_model VARCHAR)"))
                c.execute(text("INSERT INTO fixtures (id, name) VALUES (1, 'Alt')"))
            migrate_fixtures_db(eng)
            with eng.begin() as c:
                spalten = {r[1] for r in c.execute(text("PRAGMA table_info(fixtures)"))}
                self.assertIn("provenance", spalten)
                # Bestandsdaten muessen erhalten sein — eine Migration, die
                # Zeilen verliert, waere schlimmer als die fehlende Spalte.
                self.assertEqual(
                    c.execute(text("SELECT name FROM fixtures WHERE id=1")).scalar(),
                    "Alt")
            eng.dispose()

    def test_migration_ist_wiederholbar(self):
        """`ensure_builtins`/`get_engine` laufen bei jedem Start — ein zweiter
        Durchgang darf nicht an „duplicate column name" scheitern."""
        import tempfile
        from sqlalchemy import create_engine, text
        from src.core.database.models import migrate_fixtures_db
        with tempfile.TemporaryDirectory() as d:
            eng = create_engine(f"sqlite:///{os.path.join(d, 'zwei.db')}")
            with eng.begin() as c:
                c.execute(text("CREATE TABLE fixtures (id INTEGER PRIMARY KEY, "
                               "name VARCHAR, source VARCHAR)"))
            migrate_fixtures_db(eng)
            migrate_fixtures_db(eng)          # darf nicht werfen
            with eng.begin() as c:
                spalten = [r[1] for r in c.execute(text("PRAGMA table_info(fixtures)"))]
            self.assertEqual(spalten.count("provenance"), 1)
            eng.dispose()


class ImporterSchreibtSieTest(unittest.TestCase):
    """Der Weg von der Datei bis in die Zeile — nicht nur die Hilfsfunktion."""

    def _importiere(self, creator_xml: str):
        import tempfile
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session
        from src.core.database.models import Base, FixtureProfile
        from src.core.database.qxf_import import import_qxf_file
        qxf = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
               f'<FixtureDefinition xmlns="{_NS}">'
               f'{creator_xml}'
               f'<Manufacturer>Testhaus</Manufacturer>'
               f'<Model>Pruefling 1</Model><Type>Color Changer</Type>'
               f'<Channel Name="Rot"><Group Byte="0">Intensity</Group>'
               f'<Capability Min="0" Max="255">Rot</Capability></Channel>'
               f'<Mode Name="1-Kanal"><Channel Number="0">Rot</Channel></Mode>'
               f'</FixtureDefinition>')
        with tempfile.TemporaryDirectory() as d:
            pfad = os.path.join(d, "pruefling.qxf")
            io.open(pfad, "w", encoding="utf-8").write(qxf)
            eng = create_engine(f"sqlite:///{os.path.join(d, 'lib.db')}")
            Base.metadata.create_all(eng)
            with Session(eng) as s:
                ok = import_qxf_file(pfad, s, {})
                s.commit()
                self.assertTrue(ok, "der Prueflings-Import ist gescheitert")
                p = s.execute(select(FixtureProfile).where(
                    FixtureProfile.name == "Pruefling 1")).scalars().first()
                ergebnis = (p.source, p.provenance)
            eng.dispose()
            return ergebnis

    def test_die_herkunft_landet_in_der_zeile(self):
        quelle, herkunft = self._importiere(
            "<Creator><Name>Q Light Controller Plus</Name>"
            "<Version>4.12.3</Version><Author>NiKoyes</Author></Creator>")
        self.assertEqual(herkunft, "Q Light Controller Plus 4.12.3 · NiKoyes")
        self.assertEqual(quelle, "qlcplus",
                         "source ist der KANAL und bleibt unveraendert")

    def test_datei_ohne_creator__herkunft_leer_source_unveraendert(self):
        """★ Der Fall der 11 Eigenbauten: leere Herkunft ist der Hinweis. Und
        `source` bleibt trotzdem `qlcplus` — das Umetikettieren waere eine
        stille Verhaltensaenderung (Spider-Autokorrektur)."""
        quelle, herkunft = self._importiere("")
        self.assertEqual(herkunft, "")
        self.assertEqual(quelle, "qlcplus")


class BerichtsWerkzeugTest(unittest.TestCase):
    """`tools/fixture_herkunft.py` — der Bericht fuer den Bibliotheks-Durchgang.

    Reine Funktionen gegen erfundene Zeilen: das Werkzeug darf nicht die
    gewachsene Bibliothek DIESES Rechners brauchen, um pruefbar zu sein.
    """

    def _werkzeug(self):
        import importlib.util
        pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "tools", "fixture_herkunft.py")
        spec = importlib.util.spec_from_file_location("_fh", pfad)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    ZEILEN = [
        ("Robe", "Robin 600E Spot", "qlcplus",
         "Q Light Controller Plus 4.12.3 · NiKoyes"),
        ("Robe", "Robin Pointe", "qlcplus",
         "Q Light Controller Plus 4.12.3 · NiKoyes"),
        ("Testhaus", "Eigenbau", "qlcplus", ""),
        ("Generic", "LED PAR RGB 3ch", "builtin", ""),
    ]

    def test_autor_wird_aus_der_herkunft_gelesen(self):
        w = self._werkzeug()
        self.assertEqual(w._autor("Q Light Controller Plus 4.12.3 · NiKoyes"),
                         "NiKoyes")
        self.assertEqual(w._autor("Fixture Editor 1.0"), "",
                         "ohne Autor-Teil darf nichts erfunden werden")
        self.assertEqual(w._autor(""), "")

    def test_bericht_zaehlt_kanal_und_herkunft_getrennt(self):
        """Die beiden Zahlen beantworten verschiedene Fragen — „wie kam es
        herein" und „was sagt die Datei ueber sich"."""
        text = self._werkzeug().bericht(self.ZEILEN)
        self.assertIn("Profile gesamt: 4", text)
        self.assertIn("qlcplus", text)
        self.assertIn("builtin", text)
        self.assertIn("mit Angabe       2", text)
        self.assertIn("ohne Angabe      2", text)

    def test_bericht_deutet_fehlende_angabe_nicht_um(self):
        """★ Der Satz muss dastehen: „ohne Angabe" heisst NICHT „selbstgebaut".
        Die `.qxf` der Altbestaende liegen nicht mehr auf dem Rechner — wer aus
        der leeren Spalte eine Aussage ableitet, irrt sich systematisch."""
        text = self._werkzeug().bericht(self.ZEILEN)
        self.assertIn("wir wissen es nicht", text)

    def test_autorenliste_dedupliziert(self):
        """Fuer die Namensnennung zaehlt der Autor, nicht die Profilzahl."""
        text = self._werkzeug().bericht(self.ZEILEN, nur_autoren=True)
        self.assertIn("1 verschiedene", text)
        self.assertIn("NiKoyes", text)

    def test_leere_bibliothek_sagt_es_statt_leer_zu_bleiben(self):
        text = self._werkzeug().bericht([], nur_autoren=True)
        self.assertIn("keine", text)


if __name__ == "__main__":
    unittest.main()
