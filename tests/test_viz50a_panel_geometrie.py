"""VIZ-50a — ein Matrix-Panel muss seine Form nicht mehr raten.

**Der Befund.** ``buildMatrixPanel`` bekam bis heute nur die PIXELZAHL und leitete
daraus ein near-square-Raster ab (``panelGrid``: ``cols = ceil(sqrt(n))``). Fuer
Robins ZQ06121-Balken mit 48 RGB-Zonen sind das 7x7 — ein Quadrat mit 49 Feldern,
eines davon leer, wo in Wahrheit eine **4 Reihen x 12 Spalten**-Leiste haengt.
Dazu eine fest quadratische 0,5-m-Kachel als Gehaeuse. Folge: die 3D-Vorschau
taugte fuer dieses Geraet weder zur Positionskontrolle noch zum Programmieren —
ein waagerechtes Lauflicht sprang dort nach 7 statt nach 12 Pixeln in die
naechste Zeile.

**Die Wurzel war nicht das Modell, sondern die fehlende Quelle:** es gab kein
Feld, das die physische Anordnung traegt. Dieses Item legt sie an
(``FixtureMode.grid_rows`` / ``grid_cols``) und reicht sie bis ins 3D durch.

Was hier geprueft wird, in der Reihenfolge des Datenwegs:

1. **Migration** — eine Spalte im Modell ohne ``ALTER TABLE`` macht jede
   bestehende ``fixtures.db`` unbrauchbar (dieselbe Falle wie ``pixel_order``
   in PR #514, nur diesmal an der Bibliothek statt an der Show).
2. **Nachtrag in befuellte DBs** — ``ensure_builtins`` baut ein vorhandenes
   Profil nur bei abweichender ATTRIBUT-Signatur neu; eine Rasterform steht in
   keinem Attribut. Ohne den eigenen Nachtragsweg kaeme die Geometrie nur in
   einer frisch angelegten Bibliothek an.
3. **Die hinterlegten Werte selbst** — rows*cols muss zur Zahl der
   ``color_r``-Baenke des Modus passen, sonst beschreibt die Form ein anderes
   Geraet als die Kanaele.
4. **Auflesen** (``panel_grid_for``) und **Durchreichen** (``_fixture_to_dict``)
   auf dem ECHTEN Weg: DB -> Modus -> Nutzlast.

★ **Positivkontrolle durchgehend:** ein Geraet OHNE hinterlegte Geometrie muss
sich exakt wie bisher verhalten. Eine Aenderung, die jedes Panel umbaut, waere
so unbrauchbar wie gar keine — die Klasse ``OhneGeometrieUnveraendertTest``
steht deshalb gleichberechtigt neben den Wirkungs-Tests.

Die 3D-Wirkung (Gehaeusemasse, Zellenlage, waagerechtes Lauflicht) misst
``test_viz50a_panel_koerper_scene.py`` in echter QWebEngine.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import create_engine, select, text            # noqa: E402
from sqlalchemy.orm import Session, selectinload              # noqa: E402

from _fixture_quelle import frische_library                   # noqa: E402
from src.core.database.models import (                        # noqa: E402
    Base, ChannelRange, FixtureChannel, FixtureMode, FixtureProfile,
    migrate_fixtures_db)


# ════════════════════════════════════════════════════════════════════════════
# 1. Migration: eine Alt-Bibliothek muss die neue Spalte ueberleben
# ════════════════════════════════════════════════════════════════════════════

# Das Schema der Fixture-DB VOR der ersten Light-Migration. Alles, was danach
# dazukam (``channel_ranges.kind``, ``fixtures.viz_model``, jetzt
# ``fixture_modes.grid_rows/grid_cols``), MUSS ``migrate_fixtures_db`` selbst
# nachziehen. Handgepflegt und eingefroren — wer hier eine frisch hinzugefuegte
# Spalte eintraegt, statt die Migration zu ergaenzen, macht jede bestehende
# Bibliothek unlesbar (und muss sich das bewusst antun).
#
# ★ Warum das an der fixtures.db genauso weh tut wie an der Show-DB: sie ist die
#   Datei, die der Nutzer NICHT neu anlegen kann, ohne seine importierten und
#   selbst gebauten Profile zu verlieren — und die gepatchten Geraete jeder Show
#   verweisen ueber ``fixture_profile_id`` genau dorthin.
_URSCHEMA: dict[str, set[str]] = {
    "fixtures": {"id", "manufacturer_id", "name", "short_name", "fixture_type",
                 "power_w", "notes", "source"},
    "fixture_modes": {"id", "fixture_id", "name", "channel_count", "description"},
    "channels": {"id", "mode_id", "channel_number", "name", "attribute",
                 "default_value", "highlight_value", "invert", "resolution"},
    "channel_ranges": {"id", "channel_id", "range_from", "range_to", "name"},
}

_MODELLE = {"fixtures": FixtureProfile, "fixture_modes": FixtureMode,
            "channels": FixtureChannel, "channel_ranges": ChannelRange}


def _alte_bibliothek(pfad: str) -> None:
    """Legt eine Fixture-DB im Urschema an — echte Spaltentypen, echte Tabellen.

    Weg ueber ``create_all`` + ``DROP COLUMN`` (wie in
    ``test_show_db_migration_coverage``): so haben die Bestandsspalten garantiert
    dieselben Typen/Defaults wie im Betrieb, und der Test veraltet nicht, wenn
    sich an ihnen etwas aendert."""
    eng = create_engine(f"sqlite:///{pfad}")
    Base.metadata.create_all(eng)
    with eng.begin() as conn:
        for tabelle, urspalten in _URSCHEMA.items():
            ist = {r[1] for r in conn.execute(text(f"PRAGMA table_info({tabelle})"))}
            for spalte in sorted(ist - urspalten):
                conn.execute(text(f"ALTER TABLE {tabelle} DROP COLUMN {spalte}"))
    eng.dispose()


class FixtureDbMigrationTest(unittest.TestCase):
    """Die Migration muss eine bestehende Bibliothek ueberleben lassen."""

    def setUp(self):
        if sqlite3.sqlite_version_info < (3, 35):
            self.skipTest("ALTER TABLE DROP COLUMN braucht SQLite >= 3.35")
        fd, self.db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(self.db)                 # SQLite legt sie selbst an
        self.addCleanup(lambda: os.path.exists(self.db) and os.unlink(self.db))

    def _migriert(self):
        eng = create_engine(f"sqlite:///{self.db}")
        migrate_fixtures_db(eng)
        self.addCleanup(eng.dispose)
        return eng

    def test_migration_holt_jede_modell_spalte_nach(self):
        """Nach der Migration muss die Alt-DB dem Modell entsprechen.

        Faengt strukturell den Fall „neue Spalte ins Modell, ALTER TABLE
        vergessen": die Spalte steht dann in keiner der beiden Quellen (weder
        Urschema noch Migration) und fehlt hier."""
        _alte_bibliothek(self.db)
        eng = self._migriert()
        with eng.connect() as conn:
            for tabelle, modell in _MODELLE.items():
                ist = {r[1] for r in conn.execute(
                    text(f"PRAGMA table_info({tabelle})"))}
                soll = {c.name for c in modell.__table__.columns}
                self.assertEqual(
                    soll - ist, set(),
                    f"{tabelle}: diese Modell-Spalten fehlen einer Alt-DB nach "
                    f"der Migration. Ergaenze sie in migrate_fixtures_db "
                    f"(additives ALTER TABLE mit Default) — sonst ist jede "
                    f"bestehende Bibliothek nicht mehr lesbar.")

    def test_urschema_bleibt_eingefroren(self):
        """Gegenprobe: der Test darueber waere trivial gruen, wenn jemand die
        neue Spalte einfach ins ``_URSCHEMA`` schriebe. Das Urschema muss eine
        echte TEILmenge des Modells bleiben."""
        for tabelle, modell in _MODELLE.items():
            soll = {c.name for c in modell.__table__.columns}
            self.assertEqual(
                _URSCHEMA[tabelle] - soll, set(),
                f"{tabelle}: _URSCHEMA nennt Spalten, die das Modell nicht hat")

    def test_alte_bibliothek_mit_profilen_bleibt_lesbar(self):
        """Der eigentliche Schadensfall: eine gewachsene Bibliothek.

        Eine vorhandene Spalte belegt noch nicht, dass die Zeilen ueberleben —
        deshalb der ORM-Weg statt nur ``PRAGMA table_info``."""
        _alte_bibliothek(self.db)
        eng = create_engine(f"sqlite:///{self.db}")
        with eng.begin() as conn:
            conn.execute(text(
                "INSERT INTO manufacturers (id, name, short_name) "
                "VALUES (1, 'Alt-Hersteller', 'ALT')"))
            conn.execute(text(
                "INSERT INTO fixtures (id, manufacturer_id, name, short_name, "
                "fixture_type, power_w, notes, source) VALUES "
                "(1, 1, 'Alt-Panel', 'ALTPANEL', 'matrix', 100, '', 'user')"))
            conn.execute(text(
                "INSERT INTO fixture_modes (id, fixture_id, name, channel_count, "
                "description) VALUES (1, 1, 'Alt-Modus', 9, '')"))
        eng.dispose()

        eng = self._migriert()
        with Session(eng) as s:
            modi = s.execute(select(FixtureMode)).scalars().all()
            self.assertEqual([m.name for m in modi], ["Alt-Modus"],
                             "der Alt-Modus muss die Migration ueberleben")
            self.assertEqual(modi[0].channel_count, 9)
            profile = s.execute(select(FixtureProfile)).scalars().all()
            self.assertEqual([p.short_name for p in profile], ["ALTPANEL"])

    def test_die_neue_spalte_bedeutet_bestandsverhalten(self):
        """★ Eine nachgezogene Spalte muss das ALTE Verhalten bedeuten.

        ``0/0`` heisst „keine Geometrie hinterlegt" und damit „der Renderer raet
        wie bisher". Ein Default wie 1 oder 4 waere von einer echten Angabe
        nicht zu unterscheiden — jedes Bestandspanel bekaeme still eine Form
        behauptet, die niemand vermessen hat."""
        _alte_bibliothek(self.db)
        eng = create_engine(f"sqlite:///{self.db}")
        with eng.begin() as conn:
            conn.execute(text(
                "INSERT INTO manufacturers (id, name, short_name) "
                "VALUES (1, 'Alt', 'ALT')"))
            conn.execute(text(
                "INSERT INTO fixtures (id, manufacturer_id, name, short_name, "
                "fixture_type, power_w, notes, source) VALUES "
                "(1, 1, 'Alt-Panel', 'ALTPANEL', 'matrix', 100, '', 'user')"))
            conn.execute(text(
                "INSERT INTO fixture_modes (id, fixture_id, name, channel_count, "
                "description) VALUES (1, 1, 'Alt-Modus', 9, '')"))
        eng.dispose()

        eng = self._migriert()
        with Session(eng) as s:
            modus = s.execute(select(FixtureMode)).scalars().first()
            self.assertEqual((modus.grid_rows, modus.grid_cols), (0, 0))

    def test_migration_ist_idempotent(self):
        """``migrate_fixtures_db`` laeuft bei JEDEM Engine-Aufbau. Ein zweiter
        Lauf darf nicht an „duplicate column" scheitern — und da die Funktion
        ihre Fehler schluckt, waere ein Fehlschlag hier lautlos."""
        _alte_bibliothek(self.db)
        eng = create_engine(f"sqlite:///{self.db}")
        self.addCleanup(eng.dispose)
        migrate_fixtures_db(eng)
        with eng.begin() as conn:
            conn.execute(text(
                "INSERT INTO manufacturers (id, name, short_name) "
                "VALUES (1, 'Alt', 'ALT')"))
            conn.execute(text(
                "INSERT INTO fixtures (id, manufacturer_id, name, short_name, "
                "fixture_type, power_w, notes, source, viz_model) VALUES "
                "(1, 1, 'P', 'ALTPANEL', 'matrix', 0, '', 'user', '')"))
            conn.execute(text(
                "INSERT INTO fixture_modes (id, fixture_id, name, channel_count, "
                "description, grid_rows, grid_cols) "
                "VALUES (1, 1, 'M', 9, '', 4, 12)"))
        migrate_fixtures_db(eng)           # zweiter Lauf
        with Session(eng) as s:
            modus = s.execute(select(FixtureMode)).scalars().first()
            self.assertEqual((modus.grid_rows, modus.grid_cols), (4, 12),
                             "der zweite Migrationslauf hat die Form verloren")


# ════════════════════════════════════════════════════════════════════════════
# 2. Nachtrag in eine bereits befuellte Bibliothek
# ════════════════════════════════════════════════════════════════════════════

def _profil(session, short):
    return session.execute(
        select(FixtureProfile)
        .options(selectinload(FixtureProfile.modes))
        .where(FixtureProfile.short_name == short)
    ).scalars().first()


def _modus(session, short, mode_name):
    return next(m for m in _profil(session, short).modes if m.name == mode_name)


class _LibraryCase(unittest.TestCase):
    """Frisch aus dem Quelltext geseedete Bibliothek (FIXTEST-FRESH)."""

    def setUp(self):
        from src.core.app_state import clear_channel_cache
        self._eng = frische_library(self)
        clear_channel_cache()
        self.addCleanup(clear_channel_cache)

    def _geometrie_loeschen(self):
        """Stellt den Zustand einer VOR VIZ-50a angelegten Bibliothek her: die
        Profile sind da, die Formangabe ist leer."""
        with Session(self._eng) as s:
            s.execute(text("UPDATE fixture_modes SET grid_rows = 0, grid_cols = 0"))
            s.commit()


class NachtragTest(_LibraryCase):
    """★ Der Weg, ohne den die Geometrie NUR in einer frisch angelegten
    Bibliothek ankaeme. ``ensure_builtins`` baut ein vorhandenes Profil
    ausschliesslich bei abweichender ATTRIBUT-Signatur neu — und eine Rasterform
    steht in keinem Attribut. Auf einem gewachsenen Rechner waere das Feld also
    dauerhaft 0 geblieben und der ZQ06121 weiter ein 7x7-Quadrat."""

    def test_ensure_builtins_traegt_die_form_nach(self):
        from src.core.database.fixture_db import ensure_builtins
        self._geometrie_loeschen()
        with Session(self._eng) as s:
            m = _modus(s, "ZQ06121", "154-Kanal 48 Zonen RGB + 8x Weiss")
            self.assertEqual((m.grid_rows, m.grid_cols), (0, 0), "Vorbedingung")
        ensure_builtins()
        with Session(self._eng) as s:
            m = _modus(s, "ZQ06121", "154-Kanal 48 Zonen RGB + 8x Weiss")
            self.assertEqual(
                (m.grid_rows, m.grid_cols), (4, 12),
                "in einer bestehenden Bibliothek kam die Rasterform nie an")

    def test_JEDE_geseedete_form_wird_nachgetragen(self):
        """★★ Der Test, der die Liste in ``ensure_builtins`` bewacht.

        Der Nachtrag laeuft ueber eine aufgezaehlte Liste von Profilen. Wer
        einem weiteren Builtin eine Rasterform gibt und die Liste vergisst, hat
        sie fuer JEDE bestehende Bibliothek nicht eingebaut — und merkt es nie,
        weil eine frisch angelegte DB sie ja hat. Deshalb wird hier nicht ein
        Geraet geprueft, sondern die MENGE: was ein frischer Seed an Formen
        anlegt, muss der Nachtrag in einer geleerten DB wiederherstellen."""
        from src.core.database.fixture_db import ensure_builtins
        with Session(self._eng) as s:
            soll = {(m.fixture.short_name, m.name): (m.grid_rows, m.grid_cols)
                    for m in s.execute(
                        select(FixtureMode)
                        .options(selectinload(FixtureMode.fixture))
                        .where(FixtureMode.grid_rows > 0)).scalars().all()}
        self.assertTrue(soll, "der Seed legt gar keine Formen an (Vorbedingung)")
        self._geometrie_loeschen()
        ensure_builtins()
        with Session(self._eng) as s:
            ist = {(m.fixture.short_name, m.name): (m.grid_rows, m.grid_cols)
                   for m in s.execute(
                       select(FixtureMode)
                       .options(selectinload(FixtureMode.fixture))
                       .where(FixtureMode.grid_rows > 0)).scalars().all()}
        self.assertEqual(
            ist, soll,
            "diese Formen legt der Seed an, der Nachtrag stellt sie aber nicht "
            "wieder her — in jeder bestehenden Bibliothek fehlen sie damit "
            "dauerhaft (Liste in ensure_builtins ergaenzen)")

    def test_nachtrag_ueberschreibt_eine_gesetzte_form_nicht(self):
        """★★ Nur ergaenzend. Wuerde der Nachtrag stumpf ueberschreiben, saesse
        eine spaetere Korrektur des Nutzers nach dem naechsten Programmstart
        wieder auf dem Werkswert — ohne Meldung."""
        from src.core.database.fixture_db import ensure_builtins
        with Session(self._eng) as s:
            m = _modus(s, "ZQ06121", "154-Kanal 48 Zonen RGB + 8x Weiss")
            m.grid_rows, m.grid_cols = 2, 24
            s.commit()
        ensure_builtins()
        with Session(self._eng) as s:
            m = _modus(s, "ZQ06121", "154-Kanal 48 Zonen RGB + 8x Weiss")
            self.assertEqual((m.grid_rows, m.grid_cols), (2, 24),
                             "der Nachtrag hat eine gesetzte Form zerstoert")

    def test_nachtrag_laesst_modi_ohne_angabe_in_ruhe(self):
        """Positivkontrolle: ein Modus, fuer den keine Form hinterlegt IST
        (Dotz Matrix im 3-Kanal-Modus — eine einzige Farbbank, kein Raster),
        bleibt nach dem Nachtrag bei 0/0. Ein Nachtrag, der alles anfasst, waere
        so wertlos wie keiner."""
        from src.core.database.fixture_db import ensure_builtins
        self._geometrie_loeschen()
        ensure_builtins()
        with Session(self._eng) as s:
            m = _modus(s, "DOTZMATRIX", "3-Kanal RGB")
            self.assertEqual((m.grid_rows, m.grid_cols), (0, 0))

    def test_nachtrag_fasst_kanaele_nicht_an(self):
        """★ Der Nachtrag darf NICHT den Signatur-Weg nehmen (Modi verwerfen und
        neu bauen): das loescht per Cascade Kanaele UND Ranges und vergibt neue
        IDs. Fuer eine reine Formangabe waere das ein voellig unverhaeltnis-
        maessiger Eingriff in eine Datei, in der auch Nutzerprofile stehen."""
        from src.core.database.fixture_db import ensure_builtins
        self._geometrie_loeschen()
        with Session(self._eng) as s:
            m = _modus(s, "ZQ06121", "154-Kanal 48 Zonen RGB + 8x Weiss")
            vorher_id = m.id
            vorher_kanaele = s.execute(
                select(FixtureChannel.id).where(FixtureChannel.mode_id == m.id)
            ).scalars().all()
        ensure_builtins()
        with Session(self._eng) as s:
            m = _modus(s, "ZQ06121", "154-Kanal 48 Zonen RGB + 8x Weiss")
            nachher_kanaele = s.execute(
                select(FixtureChannel.id).where(FixtureChannel.mode_id == m.id)
            ).scalars().all()
        self.assertEqual(m.id, vorher_id, "die Modus-ID hat sich geaendert")
        self.assertEqual(nachher_kanaele, vorher_kanaele,
                         "die Kanaele wurden neu angelegt statt in Ruhe gelassen")

    def test_zweiter_lauf_meldet_keine_aenderung_mehr(self):
        """Idempotenz: ``ensure_builtins`` laeuft bei jedem Engine-Aufbau. Ein
        Nachtrag, der immer wieder „geaendert" meldet, schriebe die Bibliothek
        bei jedem Start neu."""
        from src.core.database import fixture_db as FDB
        self._geometrie_loeschen()
        FDB.ensure_builtins()
        with Session(self._eng) as s:
            prof = _profil(s, "ZQ06121")
            self.assertTrue(FDB._ensure_panel_geometrie(
                s, "ZQ06121", FDB._zq06121_modes_data()) is False,
                "der Nachtrag meldet Arbeit, obwohl die Form schon steht")
            self.assertIsNotNone(prof)


class BibliotheksGeometrieTest(_LibraryCase):
    """Was in der Bibliothek STEHT — und ob es zu den Kanaelen passt."""

    def test_zq06121_traegt_die_gemessene_form(self):
        """Robins Balken: 4 Reihen x 12 Zonen, an beiden Pixel-Modi. Der
        Ratewert waere 7x7 gewesen — 49 Felder fuer 48 Zonen."""
        with Session(self._eng) as s:
            for name in ("154-Kanal 48 Zonen RGB + 8x Weiss",
                         "144-Kanal 48 Zonen RGB"):
                m = _modus(s, "ZQ06121", name)
                self.assertEqual((m.grid_rows, m.grid_cols), (4, 12), name)

    def test_form_und_kanaele_beschreiben_dasselbe_geraet(self):
        """★ Der Invarianten-Test ueber die GANZE Bibliothek: wo eine Form
        hinterlegt ist, muss ``rows*cols`` der Zahl der ``color_r``-Baenke des
        Modus entsprechen. Sonst beschreibt die Form ein anderes Geraet als die
        Kanaele — und im 3D blieben Felder leer oder Pixel fielen heraus."""
        with Session(self._eng) as s:
            modi = s.execute(
                select(FixtureMode)
                .options(selectinload(FixtureMode.channels))
                .where(FixtureMode.grid_rows > 0)
            ).scalars().all()
            self.assertGreaterEqual(len(modi), 7,
                                    "es sollten Panel-Modi mit Form dabei sein")
            for m in modi:
                banks = sum(1 for c in m.channels if c.attribute == "color_r")
                self.assertEqual(
                    m.grid_rows * m.grid_cols, banks,
                    f"Modus '{m.name}': Form {m.grid_rows}x{m.grid_cols} passt "
                    f"nicht zu {banks} Farbbaenken")

    def test_nur_pixel_modi_tragen_eine_form(self):
        """Positivkontrolle gegen „alles bekommt eine Form": ein Modus mit einer
        einzigen Farbbank (Dotz Matrix 3ch, Stairville 8ch) hat kein Raster und
        darf keins behaupten."""
        with Session(self._eng) as s:
            for short, name in (("DOTZMATRIX", "3-Kanal RGB"),
                                ("STAIRPP144", "8-Kanal Panel gesamt")):
                m = _modus(s, short, name)
                self.assertEqual((m.grid_rows, m.grid_cols), (0, 0),
                                 f"{short}/{name} behauptet ein Raster")


# ════════════════════════════════════════════════════════════════════════════
# 3. Auflesen: panel_grid_for
# ════════════════════════════════════════════════════════════════════════════

def _patched(profile_id, mode_name, channel_count, **kw):
    from src.core.database.models import PatchedFixture
    return PatchedFixture(fid=kw.pop("fid", 1), label=kw.pop("label", "Panel"),
                          fixture_profile_id=profile_id, mode_name=mode_name,
                          universe=1, address=1, channel_count=channel_count,
                          fixture_type=kw.pop("fixture_type", "matrix"), **kw)


class PanelGridForTest(_LibraryCase):

    def _ids(self, short):
        with Session(self._eng) as s:
            p = _profil(s, short)
            return p.id, {m.name: m.channel_count for m in p.modes}

    def test_zq06121_liest_die_hinterlegte_form(self):
        from src.core.app_state import panel_grid_for
        pid, modi = self._ids("ZQ06121")
        name = "154-Kanal 48 Zonen RGB + 8x Weiss"
        f = _patched(pid, name, modi[name])
        self.assertEqual(panel_grid_for(f), (4, 12))

    def test_ohne_hinterlegte_form_kommt_null(self):
        """★ Positivkontrolle. ``(0, 0)`` ist die Aussage „nicht hinterlegt" —
        nur daran erkennt der Renderer, dass er wie bisher raten soll."""
        from src.core.app_state import panel_grid_for
        pid, modi = self._ids("DOTZMATRIX")
        f = _patched(pid, "3-Kanal RGB", modi["3-Kanal RGB"])
        self.assertEqual(panel_grid_for(f), (0, 0))

    def test_unbekanntes_profil_wirft_nicht(self):
        from src.core.app_state import panel_grid_for
        self.assertEqual(panel_grid_for(_patched(999999, "Egal", 9)), (0, 0))
        self.assertEqual(panel_grid_for(SimpleNamespace()), (0, 0))

    def test_die_form_folgt_dem_MODUS_nicht_dem_profil(self):
        """★ Warum die Angabe am Modus sitzt und nicht am Profil: dasselbe
        Geraet hat je nach Modus eine andere Pixelzahl. Das Stairville-Panel
        faerbt im 8-Kanal-Modus als EINE Flaeche und hat dort kein Raster, im
        432-Kanal-Modus sind es 12x12."""
        from src.core.app_state import panel_grid_for
        pid, modi = self._ids("STAIRPP144")
        gesamt = _patched(pid, "8-Kanal Panel gesamt", modi["8-Kanal Panel gesamt"])
        pixel = _patched(pid, "432-Kanal 144 Pixel RGB",
                         modi["432-Kanal 144 Pixel RGB"])
        self.assertEqual(panel_grid_for(gesamt), (0, 0))
        self.assertEqual(panel_grid_for(pixel), (12, 12))

    def test_cache_wird_mit_dem_kanal_cache_invalidiert(self):
        """★ Die Form haengt am selben Modus wie die Kanaele. Wird sie nicht
        ueber denselben Weg invalidiert, zeigt das 3D-Panel nach einer
        Profil-Aenderung die Form von vorhin — und zwar bis zum Neustart."""
        from src.core.app_state import clear_channel_cache, panel_grid_for
        pid, modi = self._ids("ZQ06121")
        name = "154-Kanal 48 Zonen RGB + 8x Weiss"
        f = _patched(pid, name, modi[name])
        self.assertEqual(panel_grid_for(f), (4, 12))
        with Session(self._eng) as s:
            m = _modus(s, "ZQ06121", name)
            m.grid_rows, m.grid_cols = 6, 8
            s.commit()
        self.assertEqual(panel_grid_for(f), (4, 12),
                         "ohne Invalidierung soll der Cache halten (Vorbedingung)")
        clear_channel_cache()
        self.assertEqual(panel_grid_for(f), (6, 8),
                         "clear_channel_cache hat die Rasterform nicht geleert")

    def test_form_und_kanaele_meinen_denselben_modus(self):
        """★ Beide Wege nutzen dieselbe Fallback-Kette (``_resolve_mode``). Bei
        einem Modusnamen, den es nicht gibt, faellt LightOS auf die KANALZAHL
        zurueck — Form und Kanaele muessen dann DENSELBEN Modus meinen, sonst
        zeigte das Panel die Form des einen mit den Pixeln des anderen.

        Bewusst am Stairville-Panel: dessen erster Modus (8 Kanal, EINE Farbbank,
        keine Form) unterscheidet sich maximal vom Pixel-Modus (144 Baenke,
        12x12). Am ZQ06121 waere der Test blind — dort haben beide Modi
        dieselben 48 Zonen, und jede Fallback-Stufe faende zufaellig dasselbe."""
        from src.core.app_state import get_channels_for_patched, panel_grid_for
        pid, modi = self._ids("STAIRPP144")
        f = _patched(pid, "Modus-den-es-nicht-gibt",
                     modi["432-Kanal 144 Pixel RGB"])
        banks = sum(1 for c in get_channels_for_patched(f)
                    if (getattr(c, "attribute", "") or "") == "color_r")
        rows, cols = panel_grid_for(f)
        self.assertEqual(banks, 144, "die Kanaele kommen aus dem falschen Modus")
        self.assertEqual((rows, cols), (12, 12),
                         "die Form kommt aus einem anderen Modus als die Kanaele")
        self.assertEqual(rows * cols, banks)


# ════════════════════════════════════════════════════════════════════════════
# 4. Durchreichen: die 3D-Nutzlast
# ════════════════════════════════════════════════════════════════════════════

class NutzlastTest(_LibraryCase):
    """``_fixture_to_dict`` ist die EINZIGE Stelle, an der die statische Gestalt
    eines Geraets nach JS geht. Kommt die Form dort nicht an, war die ganze
    Datenhaltung umsonst — genau so ist VIZ-51 fuer ``pixelOrder`` ausgegangen
    (das Feld existierte, die Registry las es, nur die Nutzlast trug es nicht)."""

    def _dict_for(self, f):
        import types
        from src.ui.visualizer.visualizer_window import VisualizerBridge
        fake_state = SimpleNamespace(visualizer_positions={},
                                     visualizer_rotations={},
                                     visualizer_docks={})
        fake_self = SimpleNamespace(_state=fake_state)
        fake_self._viz_model_for = types.MethodType(
            VisualizerBridge._viz_model_for, fake_self)
        return VisualizerBridge._fixture_to_dict(fake_self, f)

    def _ids(self, short):
        with Session(self._eng) as s:
            p = _profil(s, short)
            return p.id, {m.name: m.channel_count for m in p.modes}

    def test_die_form_kommt_in_der_nutzlast_an(self):
        pid, modi = self._ids("ZQ06121")
        name = "154-Kanal 48 Zonen RGB + 8x Weiss"
        d = self._dict_for(_patched(pid, name, modi[name]))
        self.assertEqual(d["model"], "matrix")
        self.assertEqual(d["nHeads"], 48)
        self.assertEqual((d["gridRows"], d["gridCols"]), (4, 12))

    def test_ohne_hinterlegte_form_reisen_nullen_mit(self):
        """★ Positivkontrolle: das Feld ist IMMER da (JS haette sonst zwei
        Faelle zu unterscheiden), aber es sagt 0 — und 0 heisst „raten wie
        bisher"."""
        pid, modi = self._ids("DOTZMATRIX")
        d = self._dict_for(_patched(pid, "48-Kanal 16 Pixel RGB",
                                    modi["48-Kanal 16 Pixel RGB"],
                                    fid=2))
        self.assertEqual((d["gridRows"], d["gridCols"]), (4, 4),
                         "das Dotz-Panel IST 4x4 (und damit gleich dem Ratewert)")
        d3 = self._dict_for(_patched(pid, "3-Kanal RGB", modi["3-Kanal RGB"],
                                     fid=3))
        self.assertEqual((d3["gridRows"], d3["gridCols"]), (0, 0))


class OhneGeometrieUnveraendertTest(_LibraryCase):
    """★ Die Abnahmebedingung, die nicht verhandelbar ist: ein Geraet ohne
    hinterlegte Geometrie verhaelt sich EXAKT wie bisher."""

    def _dict_for(self, f):
        import types
        from src.ui.visualizer.visualizer_window import VisualizerBridge
        fake_self = SimpleNamespace(_state=SimpleNamespace(
            visualizer_positions={}, visualizer_rotations={}, visualizer_docks={}))
        fake_self._viz_model_for = types.MethodType(
            VisualizerBridge._viz_model_for, fake_self)
        return VisualizerBridge._fixture_to_dict(fake_self, f)

    def test_kein_matrix_geraet_fragt_die_geometrie_gar_nicht_ab(self):
        """Ein Moving-Head hat kein Raster. Die Nutzlast traegt trotzdem die
        Felder (ein fehlendes Feld waere JS-seitig ein zweiter Fall), aber
        immer als 0 — und der DB-Weg wird fuer ihn gar nicht erst betreten."""
        import src.ui.visualizer.visualizer_window as VW
        pid, _ = self._ids_mh()
        aufrufe = []
        echt = VW.panel_grid_for
        VW.panel_grid_for = lambda f: (aufrufe.append(f), echt(f))[1]
        try:
            d = self._dict_for(_patched(pid, "Egal", 11, fixture_type="moving_head"))
        finally:
            VW.panel_grid_for = echt
        self.assertEqual((d["gridRows"], d["gridCols"]), (0, 0))
        self.assertEqual(aufrufe, [],
                         "fuer ein Nicht-Panel darf die DB gar nicht befragt werden")

    def _ids_mh(self):
        with Session(self._eng) as s:
            p = _profil(s, "MH8")
            return (p.id if p else 1), None

    def test_bestandsfelder_der_nutzlast_bleiben_unveraendert(self):
        """Die neuen Schluessel duerfen nichts verdraengen: alles, was die
        3D-Seite bisher aus der Nutzlast liest, muss weiter drinstehen."""
        pid, modi = self._ids("DOTZMATRIX")
        d = self._dict_for(_patched(pid, "3-Kanal RGB", modi["3-Kanal RGB"]))
        for schluessel in ("fid", "label", "type", "model", "nHeads", "pixelOrder",
                           "elementRotation", "elementFlip", "mirror", "x", "y",
                           "z", "rotX", "rotY", "rotZ", "panRange", "tiltRange",
                           "panZero", "tiltZero", "dockedTo", "r", "g", "b",
                           "intensity", "pan", "tilt"):
            self.assertIn(schluessel, d)

    def _ids(self, short):
        with Session(self._eng) as s:
            p = _profil(s, short)
            return p.id, {m.name: m.channel_count for m in p.modes}


if __name__ == "__main__":
    unittest.main()
