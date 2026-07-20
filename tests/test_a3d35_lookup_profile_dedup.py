"""A3D-35: ShowBuilder._lookup_profile bei mehrdeutigem short_name.

``FixtureProfile.short_name`` hat KEINE Unique-Constraint (models.py) — Builtins
und Importe (source 'qlcplus'/'user') können denselben short_name tragen. Das
frühere ``.first()`` OHNE ``ORDER BY`` lieferte einen rowid-abhängigen, stillen
Zufalls-Treffer → mal das FALSCHE Profil (falsche channel_count/fixture_type/
DMX-Abbildung), nicht reproduzierbar.

Fix (3-Agent-Debatte → C_hybrid): TOTAL-deterministisch wählen — ``builtin`` vor
Import, dann kleinste ``id`` (PK unique → keine Rest-Ties) — und bei Mehrdeutigkeit
laut warnen (``[showbuilder] WARN``, 1× pro short_name), bzw. im strict-Modus
(``strict_profiles=True`` / env ``LIGHTOS_STRICT_PROFILES=1``) hart ``BuildError``.
"""
from __future__ import annotations

import os
import tempfile

import pytest
from sqlalchemy.orm import Session

from src.core.database import fixture_db as fdb
from src.core.database.fixture_db import get_engine
from src.core.database.models import Manufacturer, FixtureProfile
from src.core.show.showbuilder import ShowBuilder, BuildError


def _seed(rows):
    """rows: list of (id, short_name, source, fixture_type) → temp Fixture-DB engine."""
    eng = get_engine(os.path.join(tempfile.mkdtemp(), "fx.db"))   # create_all_idempotent legt Schema an
    with Session(eng) as s:
        mfr = Manufacturer(name="TestMfr", short_name="TSTM")
        s.add(mfr)
        s.flush()
        for (pid, sn, src, ft) in rows:
            s.add(FixtureProfile(id=pid, manufacturer_id=mfr.id, name=f"Profile{pid}",
                                 short_name=sn, source=src, fixture_type=ft))
        s.commit()
    return eng


def _builder(strict: bool = False):
    """Leichte ShowBuilder-Instanz NUR für _lookup_profile — ohne die schwere
    __init__ (QApplication/State/Capabilities/reset_show), aber mit den Feldern,
    die _lookup_profile liest."""
    b = object.__new__(ShowBuilder)
    b._strict_profiles = strict
    b._ambig_warned = set()
    return b


def test_duplicate_prefers_builtin_over_smaller_id(monkeypatch):
    # builtin hat die GRÖSSERE id, der Import die kleinere → builtin gewinnt trotzdem.
    # (Das alte .first() nach rowid hätte hier den Import id=10 geliefert.)
    eng = _seed([(10, "DUPE", "qlcplus", "moving_head"),
                 (90, "DUPE", "builtin", "laser")])
    monkeypatch.setattr(fdb, "engine", lambda: eng)
    pid, ftype = _builder()._lookup_profile("DUPE")
    assert pid == 90, "builtin muss vor Import gewinnen (auch bei größerer id)"
    assert ftype == "laser"


def test_duplicate_two_builtins_smallest_id_wins(monkeypatch):
    eng = _seed([(20, "DUPE", "builtin", "par"),
                 (5, "DUPE", "builtin", "wash")])
    monkeypatch.setattr(fdb, "engine", lambda: eng)
    pid, ftype = _builder()._lookup_profile("DUPE")
    assert pid == 5, "bei gleicher source gewinnt die kleinste id (total order)"
    assert ftype == "wash"


def test_deterministic_regardless_of_insertion_order(monkeypatch):
    # DISKRIMINIEREND: der builtin bekommt die GRÖSSERE id (11), der Import die
    # kleinere (7) — so weichen „kleinste rowid/id" und „builtin-Regel" voneinander
    # ab. Das alte `.first()` OHNE ORDER BY (kleinste rowid = 7 = user) LÄGE hier
    # falsch; der Fix wählt in BEIDEN Insert-Reihenfolgen deterministisch die
    # builtin id=11 (builtin vor Import). Zusätzlich: gleiche Zeilen in UMGEKEHRTER
    # Insert-Reihenfolge → identisches Ergebnis (storage-/order-unabhängig).
    eng_a = _seed([(7, "DUPE", "user", "spot"), (11, "DUPE", "builtin", "spot")])
    monkeypatch.setattr(fdb, "engine", lambda: eng_a)
    a = _builder()._lookup_profile("DUPE")
    eng_b = _seed([(11, "DUPE", "builtin", "spot"), (7, "DUPE", "user", "spot")])
    monkeypatch.setattr(fdb, "engine", lambda: eng_b)
    b = _builder()._lookup_profile("DUPE")
    assert a == b == (11, "spot")


def test_duplicate_emits_warning_listing_all_candidates(monkeypatch, capsys):
    eng = _seed([(4, "SPIDER14", "builtin", "moving_head"),
                 (88, "SPIDER14", "qlcplus", "moving_head"),
                 (91, "SPIDER14", "user", "moving_head")])
    monkeypatch.setattr(fdb, "engine", lambda: eng)
    _builder()._lookup_profile("SPIDER14")
    out = capsys.readouterr().out
    assert "[showbuilder] WARN" in out
    assert "SPIDER14" in out
    for token in ("id=4", "id=88", "id=91"):      # ALLE Kandidaten benannt
        assert token in out, f"Kandidat {token} fehlt in WARN: {out!r}"
    assert "gewaehlt id=4" in out                  # der Gewinner benannt


def test_single_match_is_silent(monkeypatch, capsys):
    eng = _seed([(3, "SOLO", "builtin", "par")])
    monkeypatch.setattr(fdb, "engine", lambda: eng)
    pid, ftype = _builder()._lookup_profile("SOLO")
    assert (pid, ftype) == (3, "par")
    assert "WARN" not in capsys.readouterr().out    # kein Rausch-Warnen im Normalfall


def test_missing_profile_raises_builderror(monkeypatch):
    eng = _seed([(3, "OTHER", "builtin", "par")])
    monkeypatch.setattr(fdb, "engine", lambda: eng)
    with pytest.raises(BuildError) as ei:
        _builder()._lookup_profile("NICHTDA")
    assert "existiert nicht" in str(ei.value)


def test_strict_mode_kwarg_raises_on_duplicate(monkeypatch):
    eng = _seed([(4, "DUPE", "builtin", "par"), (9, "DUPE", "user", "par")])
    monkeypatch.setattr(fdb, "engine", lambda: eng)
    with pytest.raises(BuildError) as ei:
        _builder(strict=True)._lookup_profile("DUPE")
    m = str(ei.value)
    # der strict-BuildError listet die Kandidaten UND ist NICHT der
    # "Fixture-DB nicht lesbar"-Wrapper (Raise sitzt außerhalb des try/except).
    assert "id=4" in m and "id=9" in m
    assert "nicht lesbar" not in m


def test_strict_mode_env_wires_flag(monkeypatch):
    monkeypatch.setenv("LIGHTOS_STRICT_PROFILES", "1")
    b = ShowBuilder(reset=False)
    assert b._strict_profiles is True
    monkeypatch.delenv("LIGHTOS_STRICT_PROFILES", raising=False)
    b2 = ShowBuilder(reset=False)
    assert b2._strict_profiles is False
    # explizites kwarg gewinnt über die (leere) Umgebung
    assert ShowBuilder(reset=False, strict_profiles=True)._strict_profiles is True


def test_warning_deduped_once_per_short_name(monkeypatch, capsys):
    eng = _seed([(4, "DUPE", "builtin", "par"), (9, "DUPE", "user", "par")])
    monkeypatch.setattr(fdb, "engine", lambda: eng)
    b = _builder()
    b._lookup_profile("DUPE")
    b._lookup_profile("DUPE")   # zweiter Aufruf (wie profile_id + patch) → kein 2. WARN
    assert capsys.readouterr().out.count("[showbuilder] WARN") == 1


def test_db_unreadable_raises_builderror(monkeypatch):
    def _boom():
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(fdb, "engine", _boom)
    with pytest.raises(BuildError) as ei:
        _builder()._lookup_profile("DUPE")
    assert "nicht lesbar" in str(ei.value)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
