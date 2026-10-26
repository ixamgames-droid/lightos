"""FM-69 — „Bibliotheks-Update erreicht bestehende DBs nicht (SH-LASER3W ohne
laser_x/laser_y)“.

**Der Befund (DEMO-07, 2026-10-08):** der Show-Lint einer Showcase-Show meldete
gegen eine gewachsene ``fixtures.db`` fuer beide SH-LASER3W
``EFX-ACHSE-FEHLT``, gegen eine frische Bibliothek nichts. Vermutet war, dass
der Bibliotheks-Abgleich die Laser-Achsen nicht in bestehende Profile
nachzieht.

**Nachgestellt — die Vermutung stimmt NICHT:**

* Die Profildatei ``fixtures/bibliothek/shehds/3000mw-rgb-laser.json`` hat
  ``laser_x``/``laser_y`` seit ihrem ersten Commit (FM-61, #924); es gab nie
  einen Stand mit anderen Achsen, den eine alte DB tragen koennte.
* Eine selbst gebaute ALTE DB (Achsen per SQL auf ``pan``/``tilt``, Stempel der
  Datei veraltet) zieht ``ensure_builtins`` beim naechsten Start korrekt nach —
  dieselbe Profil-ID, die Datei ist die Wahrheit (``_abgleichen`` vergleicht
  ueber ``_vergleichsform`` auch die Kanal-Attribute). Siehe
  :class:`AlteDbWirdNachgezogen`.

**Die Ursache liegt im Lint:** die Showcase-Shows werden in einer Wegwerf-
Bibliothek gebaut und tragen deren Profil-NUMMERN. Auf einem Rechner mit
gewachsener Bibliothek zeigt dieselbe Nummer auf ein ANDERES Profil. Beim
Laden loest ``show_file._resolve_fixture_profile_id`` das ueber Hersteller +
Modell auf (FM-43/FM-44) — die App faehrt den richtigen Laser. Die DB-Pruefungen
des Lints (``efx_achsen_check``, ``dimmer_check``) bauten das Geraet aber mit der
ROHEN Nummer nach und sahen das fremde Profil: kein ``laser_x``/``laser_y`` ->
zweimal ``EFX-ACHSE-FEHLT`` (zwei Laser). Jetzt loesen sie das Profil so auf
wie der Loader (:func:`dimmer_check.geraet_aus_patch`).
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from _fixture_quelle import frische_library     # FIXTEST-FRESH

LASER_DATEI = "shehds/3000mw-rgb-laser.json"
HERSTELLER, MODELL, MODUS, KANAELE = "Shehds", "3000mW RGB Laser", "25 Channel", 25


def _achsen(s, pid: int) -> set[str]:
    from src.core.database.models import FixtureChannel, FixtureMode
    return set(s.execute(
        select(FixtureChannel.attribute).join(FixtureMode)
        .where(FixtureMode.fixture_id == pid)).scalars())


def _bauen(fall) -> None:
    """Frisch aus dem Quelltext geseedet, dazu die eigene Bibliothek
    eingespielt — wie ein erster Start. ``fall``: Klasse oder Instanz."""
    from src.core.database import bibliothek_format as BF
    from src.core.database.models import FixtureProfile
    from src.core import app_state as A
    fall.eng = frische_library(fall)
    with Session(fall.eng) as s:
        BF.einspielen_wenn_noetig(s)
        s.commit()
        fall.laser_id = s.execute(
            select(FixtureProfile.id).where(FixtureProfile.short_name == "SH-LASER3W")
        ).scalar_one()
        assert s.get(FixtureProfile, fall.laser_id).source == "lightos"
        assert {"laser_x", "laser_y"} <= _achsen(s, fall.laser_id)
        # Ein beliebiges ANDERES Profil ohne Laser-Achsen — das, worauf die
        # Nummer des Bau-Rechners in einer gewachsenen Bibliothek zeigt.
        fall.fremd_id = next(
            p.id for p in s.execute(select(FixtureProfile)
                                    .where(FixtureProfile.source == "builtin")
                                    .order_by(FixtureProfile.id)).scalars()
            if p.id != fall.laser_id
            and not ({"laser_x", "laser_y", "pan", "tilt"} & _achsen(s, p.id)))
    A._channel_cache.clear()
    (fall.addClassCleanup if isinstance(fall, type) else fall.addCleanup)(
        A._channel_cache.clear)


class _MitBibliothek(unittest.TestCase):
    """Je Test eine eigene Bibliothek — die Tests hier aendern sie."""

    def setUp(self):
        _bauen(self)


class AlteDbWirdNachgezogen(_MitBibliothek):
    """Gegenprobe zur Vermutung im Backlog: der Abgleich erreicht alte DBs."""

    def _alt_machen(self):
        from src.core.database.models import FixtureChannel, FixtureMode
        with Session(self.eng) as s:
            modi = [m for m in s.execute(select(FixtureMode.id)
                                         .where(FixtureMode.fixture_id == self.laser_id)).scalars()]
            for alt, neu in (("laser_x", "pan"), ("laser_y", "tilt")):
                s.execute(FixtureChannel.__table__.update()
                          .where(FixtureChannel.mode_id.in_(modi),
                                 FixtureChannel.attribute == alt)
                          .values(attribute=neu))
            s.execute(text("UPDATE bibliothek_stempel SET hash='alt' WHERE pfad=:p"),
                      {"p": LASER_DATEI})
            s.commit()
            self.assertFalse({"laser_x", "laser_y"} & _achsen(s, self.laser_id))

    def test_start_zieht_die_laser_achsen_nach_id_bleibt(self):
        from src.core.database import bibliothek_format as BF
        from src.core.database import fixture_db as F
        self._alt_machen()
        F._BIBLIOTHEK_FUER = None           # wie ein neuer Prozess
        F.ensure_builtins()
        self.assertIn(f"{HERSTELLER} / {MODELL}", BF.LETZTES_EINSPIELEN["aktualisiert"])
        with Session(self.eng) as s:
            achsen = _achsen(s, self.laser_id)
        self.assertTrue({"laser_x", "laser_y"} <= achsen)
        self.assertFalse({"pan", "tilt"} & achsen)

    def test_unveraenderter_stempel_fasst_nichts_an(self):
        """Startzeit: ohne geaenderte Datei wird kein Profil neu aufgebaut."""
        from src.core.database import bibliothek_format as BF
        with Session(self.eng) as s:
            self.assertFalse(BF.einspielen_wenn_noetig(s))
            self.assertEqual(BF.LETZTES_EINSPIELEN["aktualisiert"], [])
            self.assertEqual(BF.LETZTES_EINSPIELEN["neu"], [])

    def test_eigenes_profil_gleichen_namens_bleibt_unangetastet(self):
        """Nutzer-Aenderungen bleiben geschuetzt: ein eigenes Profil gleichen
        Namens verdeckt die Datei und wird nie ueberschrieben."""
        from src.core.database import bibliothek_format as BF
        from src.core.database.models import (FixtureChannel, FixtureMode,
                                              FixtureProfile)
        with Session(self.eng) as s:
            s.get(FixtureProfile, self.laser_id).source = "user"
            modi = [m for m in s.execute(select(FixtureMode.id)
                                         .where(FixtureMode.fixture_id == self.laser_id)).scalars()]
            s.execute(FixtureChannel.__table__.update()
                      .where(FixtureChannel.mode_id.in_(modi),
                             FixtureChannel.attribute == "laser_x")
                      .values(attribute="pan"))
            s.execute(text("UPDATE bibliothek_stempel SET hash='alt' WHERE pfad=:p"),
                      {"p": LASER_DATEI})
            s.commit()
            BF.einspielen_wenn_noetig(s)
            s.commit()
            self.assertIn(f"{HERSTELLER} / {MODELL}", BF.LETZTES_EINSPIELEN["verdeckt"])
            achsen = _achsen(s, self.laser_id)
        self.assertIn("pan", achsen)
        self.assertNotIn("laser_x", achsen)


def _laser_show(profil_id: int, *, hersteller=HERSTELLER, modell=MODELL) -> dict:
    patch = [{"fid": fid, "label": f"Laser {fid}", "fixture_profile_id": profil_id,
              "manufacturer_name": hersteller, "fixture_name": modell,
              "mode_name": MODUS, "channel_count": KANAELE,
              "universe": 3, "address": 1 + (fid - 1) * KANAELE}
             for fid in (1, 2)]
    efx = {"type": "EFX", "name": "Laser-Kreis", "motion": True, "speed_hz": 0.5,
           "fixtures": [{"fid": fid, "offset": 0.0,
                         "pan_attr": "laser_x", "tilt_attr": "laser_y"}
                        for fid in (1, 2)]}
    return {"patch": patch, "functions": [efx]}


class LintLoestWieDerLoader(unittest.TestCase):
    """Der eigentliche Befund: Show-Nummer aus einer anderen Bibliothek.
    Nur lesend — eine Bibliothek fuer die ganze Klasse."""

    @classmethod
    def setUpClass(cls):
        _bauen(cls)

    def _codes(self, show):
        from src.core.capability.efx_achsen_check import efx_achsen_befunde
        return [b.code for b in efx_achsen_befunde(show)]

    def test_frische_bibliothek_sauber(self):
        self.assertEqual(self._codes(_laser_show(self.laser_id)), [])

    def test_fremde_nummer_mit_namen_kein_falschalarm(self):
        """Vor FM-69: zweimal EFX-ACHSE-FEHLT (die Nummer traf das fremde
        Profil) — genau der Befund aus DEMO-07."""
        self.assertEqual(self._codes(_laser_show(self.fremd_id)), [])

    def test_unbekanntes_geraet_meldet_weiter(self):
        """Loest der Name nicht auf, gilt die Nummer der Show — wie beim
        Laden. Ein EFX auf ein Geraet ohne Achsen bleibt ein Befund."""
        show = _laser_show(self.fremd_id, hersteller="Niemand", modell="Gibt es nicht")
        self.assertEqual(self._codes(show), ["EFX-ACHSE-FEHLT"] * 2)

    def test_dimmer_pruefungen_sehen_dasselbe_geraet(self):
        from src.core.capability.dimmer_check import geraet_aus_patch
        pf = _laser_show(self.fremd_id)["patch"][0]
        g = geraet_aus_patch(pf)
        self.assertEqual(g.fixture_profile_id, self.laser_id)
        self.assertEqual((g.mode_name, g.channel_count, g.address), (MODUS, KANAELE, 1))
        # Legacy-Show ohne Namen: die Nummer bleibt.
        alt = {k: v for k, v in pf.items() if k not in ("manufacturer_name", "fixture_name")}
        self.assertEqual(geraet_aus_patch(alt).fixture_profile_id, self.fremd_id)

    def test_lint_hinterlaesst_keine_ladeprobleme(self):
        """Die Aufloesung des Loaders sammelt Meldungen fuer ``load_show`` —
        der Lint darf dort nichts liegen lassen."""
        from src.core.show import show_file as SF
        vorher_p, vorher_h = list(SF._ladeprobleme), dict(SF._ladehinweise)
        self._codes(_laser_show(self.fremd_id))
        self._codes(_laser_show(self.fremd_id, hersteller="Niemand", modell="X"))
        self.assertEqual(SF._ladeprobleme, vorher_p)
        self.assertEqual(SF._ladehinweise, vorher_h)


def _geraete(eng):
    """Alle Modi aller Profile der Bibliothek mit ihren Kanaelen (ueber
    dieselbe Aufloesung wie der Lint) — zum Aussuchen."""
    from types import SimpleNamespace
    from src.core.app_state import get_channels_for_patched
    from src.core.database.models import FixtureProfile
    out = []
    with Session(eng) as s:
        for p in s.execute(select(FixtureProfile)
                           .order_by(FixtureProfile.id)).scalars():
            for m in sorted(p.modes, key=lambda m: m.id):
                g = SimpleNamespace(fixture_profile_id=p.id, mode_name=m.name,
                                    channel_count=m.channel_count, address=1,
                                    spider_dual_tilt=False)
                out.append((p.id, p.manufacturer.name, p.name, m.name,
                            m.channel_count,
                            list(get_channels_for_patched(g) or ())))
    return out


def _attrs(chans) -> set[str]:
    return {(getattr(c, "attribute", "") or "").lower() for c in chans}


class DimmerPruefungenLoesenWieDerLoader(unittest.TestCase):
    """Gegenpruefung zu FM-69: auch ``statische_befunde`` (DIMMER-DUNKEL) und
    ``weiss_zuordnung_befunde`` (WEISS-DIMMER-ZUORDNUNG) nehmen das Profil, das
    der Loader nimmt — nicht die rohe Nummer der Show. Je Pruefung ein Geraet,
    bei dem Name und Nummer auf VERSCHIEDENE Profile zeigen, so gewaehlt, dass
    nur das richtig aufgeloeste Profil einen Befund liefert."""

    @classmethod
    def setUpClass(cls):
        from src.core.capability.dimmer_check import DIMMER_ATTRS
        from src.core.dimmer_segmente import zuordnung_fehlt
        _bauen(cls)
        alle = _geraete(cls.eng)
        cls.ohne_dimmer = next(g for g in alle
                               if g[5] and not (_attrs(g[5]) & DIMMER_ATTRS))
        cls.mit_dimmer = next(g for g in alle if _attrs(g[5]) & DIMMER_ATTRS)
        cls.weiss_offen = next((g for g in alle if zuordnung_fehlt(g[5])), None)

    @staticmethod
    def _patch(geraet, nummer: int) -> dict:
        _, hersteller, modell, modus, kanaele, _ = geraet
        return {"fid": 1, "label": "Geraet 1", "fixture_profile_id": nummer,
                "manufacturer_name": hersteller, "fixture_name": modell,
                "mode_name": modus, "channel_count": kanaele,
                "universe": 1, "address": 1}

    def _dunkel(self, pf):
        from src.core.capability.dimmer_check import statische_befunde
        show = {"patch": [pf], "functions": [
            {"type": "RGBMatrix", "name": "Farbe", "style": "RGB",
             "drive_intensity": False, "fixture_grid": [1]}]}
        return [b.code for b in statische_befunde(show)]

    def _weiss(self, pf):
        from src.core.capability.dimmer_check import weiss_zuordnung_befunde
        show = {"patch": [pf], "functions": [
            {"type": "RGBMatrix", "name": "Weiss", "style": "RGB",
             "fixture_grid": [None], "weiss_grid": [[1, 0]]}]}
        return [b.code for b in weiss_zuordnung_befunde(show)]

    def test_dimmer_dunkel_sieht_das_geraet_hinter_dem_namen(self):
        # Name: Geraet MIT Dimmer, Nummer: fremdes Profil OHNE Dimmer. Mit der
        # rohen Nummer gaebe es keinen Dimmer und damit keinen Befund.
        pf = self._patch(self.mit_dimmer, self.ohne_dimmer[0])
        self.assertEqual(self._dunkel(pf), ["DIMMER-DUNKEL"])
        # Gegenprobe: umgekehrt bleibt es still.
        pf = self._patch(self.ohne_dimmer, self.mit_dimmer[0])
        self.assertEqual(self._dunkel(pf), [])

    def test_weiss_zuordnung_sieht_das_geraet_hinter_dem_namen(self):
        self.assertIsNotNone(self.weiss_offen,
                             "kein Profil mit offener Weiss-Zuordnung")
        pf = self._patch(self.weiss_offen, self.ohne_dimmer[0])
        self.assertEqual(self._weiss(pf), ["WEISS-DIMMER-ZUORDNUNG"])
        pf = self._patch(self.ohne_dimmer, self.weiss_offen[0])
        self.assertEqual(self._weiss(pf), [])

    def test_alte_show_mit_mode_statt_mode_name(self):
        """Alt-Shows tragen den Modus unter ``mode`` — der Loader liest ihn
        als Rueckfall (show_file._patched_fixture_from_data), also auch die
        Kanal-Aufloesung des Lints."""
        from src.core.capability.dimmer_check import geraet_aus_patch
        pf = self._patch(self.mit_dimmer, self.mit_dimmer[0])
        pf["mode"] = pf.pop("mode_name")
        self.assertEqual(geraet_aus_patch(pf).mode_name, self.mit_dimmer[3])


if __name__ == "__main__":
    unittest.main()
