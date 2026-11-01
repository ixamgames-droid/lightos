"""LAS-28 — SH-LASER3W: die vier Flip-Kanaele trugen alle ``laser_twist``.

**Befund (LAS-26, Sichtpruefung):** Der Shehds 3000mW RGB Laser hat je
Mustergruppe (A und B) einen horizontalen UND einen vertikalen Flip. Alle vier
trugen ``laser_twist``. Die Mehrkopf-Konvention der Laser-Seite zaehlt
Vorkommen desselben Attributs als Kopf (Kopf 0 = A, Kopf 1 = B): beim Flip
war Kopf 1 damit „Pattern A Vertical Flip“ — der Umschalter „Mustergruppe B“
stellte also den zweiten Flip von A, und die beiden Flips von B waren auf der
Laser-Seite gar nicht erreichbar (Kopf 2/3).

**Behoben:** die vertikalen Flips tragen das eigene Attribut
``laser_twist_y``. Je Attribut gibt es jetzt genau zwei Vorkommen (A, B) —
der Mustergruppen-Umschalter ist fuer dieses Geraet richtig (es HAT zwei
Mustergruppen: ``laser_bank``, ``laser_x`` … liegen ebenfalls doppelt) und
meint beim Flip wirklich Gruppe B; beide Flips sind als eigene Zeilen
einzeln stellbar.

Die Bereichsnamen „Capability N“ bleiben offen (am Geraet mit Robin benennen).
"""
from __future__ import annotations

import json
import os
import pathlib
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATEI = ROOT / "fixtures" / "bibliothek" / "shehds" / "3000mw-rgb-laser.json"


def _app():
    return QApplication.instance() or QApplication([])


class _Rng:
    def __init__(self, lo, hi, name, kind=""):
        self.range_from, self.range_to, self.name, self.kind = lo, hi, name, kind


class _Ch:
    def __init__(self, attr, num, ranges, name):
        self.attribute = attr
        self.channel_number = num
        self.ranges = ranges
        self.name = name


class _FX:
    def __init__(self, fid, chans):
        self.fid = fid
        self.label = self.fixture_name = self.name = "SH-LASER3W"
        self.fixture_type = "laser"
        self.universe = 1
        self.address = 1
        self.protocol = "dmx"
        self.net_host = ""
        self._chans = chans


class _State:
    def __init__(self, fixtures):
        self._fixtures = list(fixtures)
        self.programmer: dict = {}
        self.laser_estop_active = False

    def get_patched_fixtures(self):
        return list(self._fixtures)

    def get_selected_fids(self):
        return [f.fid for f in self._fixtures]

    def set_programmer_value(self, fid, attr, value, undoable=False, head=0):
        self.programmer.setdefault(fid, {})[(attr, head)] = int(value)

    def get_programmer_value(self, fid, attr, head=0):
        return self.programmer.get(fid, {}).get((attr, head))


def _modi() -> dict[str, list[_Ch]]:
    daten = json.loads(DATEI.read_text(encoding="utf-8"))
    out = {}
    for modus in daten["modi"]:
        out[modus["name"]] = [
            _Ch(k["attribut"], i + 1,
                [_Rng(b["von"], b["bis"], b.get("name", ""), b.get("art", ""))
                 for b in k.get("bereiche", [])],
                k["name"])
            for i, k in enumerate(modus["kanaele"])]
    return out


def _kopf(chans, attr, head) -> str:
    """Name des Kanals, den ``attr`` mit Kopf ``head`` trifft (n-tes Vorkommen)."""
    return [c.name for c in chans if c.attribute == attr][head]


def test_jeder_flip_hat_je_gruppe_genau_ein_vorkommen():
    for name, chans in _modi().items():
        for attr, richtung in (("laser_twist", "Horizontal"),
                               ("laser_twist_y", "Vertical")):
            namen = [c.name for c in chans if c.attribute == attr]
            assert namen == [f"Pattern A {richtung} Flip",
                             f"Pattern B {richtung} Flip"], (name, attr, namen)


def test_mustergruppe_b_meint_beim_flip_die_gruppe_b():
    for name, chans in _modi().items():
        assert _kopf(chans, "laser_twist", 1) == "Pattern B Horizontal Flip", name
        assert _kopf(chans, "laser_twist_y", 1) == "Pattern B Vertical Flip", name


def test_laser_seite_beide_flips_einzeln_umschalter_nur_a_b(monkeypatch):
    _app()
    import src.ui.views.laser_view as lv
    for name, chans in _modi().items():
        st = _State([_FX(1, chans)])
        monkeypatch.setattr(lv, "get_state", lambda st=st: st)
        monkeypatch.setattr(lv, "get_channels_for_patched", lambda f: f._chans)
        v = lv.LaserView(follow_selection=False)
        v.refresh_from_selection()
        try:
            bedienbar = v.bedienbare_attribute()
            assert {"laser_twist", "laser_twist_y"} <= bedienbar, (name, bedienbar)
            # Zwei echte Mustergruppen (A/B) — kein Kopf 2/3 durch die Flips.
            assert v._max_head_count() == 2, name
        finally:
            v.deleteLater()


class BibliothekNimmtDasProfil(unittest.TestCase):
    """Das neue Attribut kennt der Bibliotheks-Waechter; die DB traegt es."""

    def test_eingespielt_mit_laser_twist_y(self):
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from _fixture_quelle import frische_library
        from src.core.database import bibliothek_format as BF
        from src.core.database.models import (FixtureChannel, FixtureMode,
                                              FixtureProfile)

        self.assertIn("laser_twist_y", BF.ATTRIBUTE)
        eng = frische_library(self)
        with Session(eng) as s:
            BF.einspielen_wenn_noetig(s)
            s.commit()
            pid = s.execute(select(FixtureProfile.id).where(
                FixtureProfile.short_name == "SH-LASER3W")).scalar_one()
            zeilen = s.execute(
                select(FixtureMode.name, FixtureChannel.name,
                       FixtureChannel.attribute)
                .join(FixtureMode)
                .where(FixtureMode.fixture_id == pid)).all()
        flips = {(m, n): a for m, n, a in zeilen if "Flip" in (n or "")}
        self.assertEqual(len(flips), 8)
        for (m, n), a in flips.items():
            soll = "laser_twist_y" if "Vertical" in n else "laser_twist"
            self.assertEqual(a, soll, (m, n))

    def test_bestehende_db_zieht_den_vertikalen_flip_nach_id_bleibt(self):
        """Resync: eine gewachsene DB mit dem ALTEN Stand (alle vier Flips
        ``laser_twist``, Stempel veraltet) bekommt beim naechsten Einspielen
        ``laser_twist_y`` — dieselbe Profil-ID, damit Shows sie weiter finden."""
        from sqlalchemy import select, text
        from sqlalchemy.orm import Session

        from _fixture_quelle import frische_library
        from src.core.database import bibliothek_format as BF
        from src.core.database.models import (FixtureChannel, FixtureMode,
                                              FixtureProfile)

        eng = frische_library(self)
        with Session(eng) as s:
            BF.einspielen_wenn_noetig(s)
            s.commit()
            pid = s.execute(select(FixtureProfile.id).where(
                FixtureProfile.short_name == "SH-LASER3W")).scalar_one()
            modi = list(s.execute(select(FixtureMode.id).where(
                FixtureMode.fixture_id == pid)).scalars())
            s.execute(FixtureChannel.__table__.update()
                      .where(FixtureChannel.mode_id.in_(modi),
                             FixtureChannel.attribute == "laser_twist_y")
                      .values(attribute="laser_twist"))
            s.execute(text("UPDATE bibliothek_stempel SET hash='alt' "
                           "WHERE pfad='shehds/3000mw-rgb-laser.json'"))
            s.commit()
        with Session(eng) as s:
            self.assertTrue(BF.einspielen_wenn_noetig(s))
            s.commit()
            self.assertIn("Shehds / 3000mW RGB Laser",
                          BF.LETZTES_EINSPIELEN["aktualisiert"])
            pid2 = s.execute(select(FixtureProfile.id).where(
                FixtureProfile.short_name == "SH-LASER3W")).scalar_one()
            attrs = [a for n, a in s.execute(
                select(FixtureChannel.name, FixtureChannel.attribute)
                .join(FixtureMode).where(FixtureMode.fixture_id == pid2)).all()
                if "Vertical Flip" in (n or "")]
        self.assertEqual(pid2, pid)
        self.assertEqual(attrs, ["laser_twist_y"] * 4)
