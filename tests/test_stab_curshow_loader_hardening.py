"""STAB-CURSHOW — Loader-Haertung: atomarer Patch-Replace + Concurrency-PRAGMAs.

Fehlerbild (Audit): Der Patch-Loader schrieb in eine GETEILTE ``current_show.db``
NICHT atomar — ``clear_patch()`` committete das DELETE separat, dann committete
jedes ``add_fixture()`` einzeln (N+1 Commits). Ein paralleler Prozess sah den
leeren/halben Zwischenzustand ODER INSERTete hinein; der FLD-FID-Guard wich auf
``next_fid()`` aus -> eine saubere 32-Fixture-Show lud nichtdeterministisch 22-35
Fixtures, und es entstanden Adress-Ueberlapp-Zeilen (zwei distinkte fids auf
derselben universe:address).

Fix (3-Agent-Debatte, einstimmig): (1) ``AppState.replace_patch`` ersetzt den
GESAMTEN Patch in EINER Transaktion (Core-delete + add_all + GENAU EIN commit);
(2) ``busy_timeout=5000`` pro Connection (WAL best-effort mit Netz-/Sync-Guard);
(3) KEIN Auto-Dedup — Adress-Ueberlappungen bleiben report-only (kein stiller
Datenverlust).

Diese Tests laufen headless (conftest: QT_QPA_PLATFORM=offscreen,
LIGHTOS_NO_OUTPUT_THREAD) gegen ECHTE Temp-FILE-DBs (nie :memory:), mit
EXPLIZITEN Pfaden an ``open_show`` (der conftest-``LIGHTOS_SHOW_DB``-Pin wird so
umgangen, sonst Falsch-Gruen im Zwei-Writer-Test).
"""
from __future__ import annotations

import sqlite3
import threading
import time

from sqlalchemy import select
from sqlalchemy.orm import Session as _SASession
from sqlalchemy import event as _sa_event

from src.core.app_state import (
    AppState,
    _is_local_writable_path,
    _set_sqlite_pragmas,
)
from src.core.database.models import PatchedFixture
from src.core.show import show_file
from src.core.sync import validate_and_repair


# ── Helfer ──────────────────────────────────────────────────────────────────

def _payload_dicts(n: int = 32, label_prefix: str = "F") -> list[dict]:
    """n nicht-ueberlappende Fixtures in Universe 1 (8ch je 10er-Slot -> 32*10=320<512)."""
    return [
        {
            "fid": i,
            "label": f"{label_prefix}{i}",
            "fixture_profile_id": 0,
            "mode_name": "",
            "universe": 1,
            "address": 1 + (i - 1) * 10,
            "channel_count": 8,
        }
        for i in range(1, n + 1)
    ]


def _mk_pf(fid: int, universe: int, address: int, channel_count: int = 8,
           label: str | None = None) -> PatchedFixture:
    return PatchedFixture(
        fid=fid, label=label or f"F{fid}", fixture_profile_id=0, mode_name="",
        universe=universe, address=address, channel_count=channel_count,
    )


def _mk_state(path) -> AppState:
    st = AppState()
    st.open_show(str(path))
    return st


def _db_rows(state) -> list[PatchedFixture]:
    with state._session() as s:
        return list(s.execute(select(PatchedFixture).order_by(PatchedFixture.fid)).scalars())


def _overlaps(rows) -> list[tuple[int, int]]:
    """Paare (fid_a, fid_b) mit ueberlappendem Adressbereich im selben Universe."""
    out: list[tuple[int, int]] = []
    by_univ: dict[int, list] = {}
    for r in rows:
        by_univ.setdefault(r.universe, []).append(r)
    for fxs in by_univ.values():
        fxs = sorted(fxs, key=lambda x: x.address)
        for i in range(len(fxs) - 1):
            a, b = fxs[i], fxs[i + 1]
            if a.address + a.channel_count - 1 >= b.address:
                out.append((a.fid, b.fid))
    return out


# ── T1: Zwei-Writer-Contention (Kern — faengt die 22-35-Klasse) ─────────────

def test_t1_two_writer_contention_stays_32(tmp_path):
    """Zwei AppStates mit EIGENER Engine auf DIESELBE FILE-DB, per Barrier
    synchronisiert, laden K-mal denselben sauberen 32er-Patch. Ergebnis MUSS
    exakt 32 sein und darf NULL Adress-Ueberlappungen enthalten. Auf dem alten,
    nicht-atomaren Pfad bumpte der FLD-FID-Guard kollidierende fids -> >32 Zeilen
    mit Ueberlappungen; der atomare replace_patch haelt es deterministisch bei 32."""
    db = tmp_path / "shared_show.db"
    st_a = _mk_state(db)
    st_b = _mk_state(db)
    payload = _payload_dicts(32)

    K = 20
    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def worker(state):
        try:
            for _ in range(K):
                barrier.wait(timeout=30)
                show_file._replace_patch_from_data(state, payload)
        except Exception as e:  # noqa: BLE001
            errors.append(e)
            try:
                barrier.abort()
            except Exception:
                pass

    ta = threading.Thread(target=worker, args=(st_a,))
    tb = threading.Thread(target=worker, args=(st_b,))
    ta.start(); tb.start()
    ta.join(timeout=60); tb.join(timeout=60)

    assert not errors, f"Writer-Fehler: {errors!r}"
    rows = _db_rows(st_a)
    assert len(rows) == 32, f"Erwartet exakt 32, real {len(rows)} (Race-Bumps?)"
    assert _overlaps(rows) == [], f"Adress-Ueberlappungen entstanden: {_overlaps(rows)}"


# ── T2: Atomizitaet — GENAU EIN Commit fuer den ganzen Replace ──────────────

def test_t2_replace_is_single_commit(tmp_path):
    """Der gesamte Patch-Replace committet GENAU EINMAL auf der Show-Engine
    (Beweis: kein persistierter Leer-/Halbzustand). Zusaetzlich: der alte Inhalt
    ist vollstaendig durch den neuen ersetzt."""
    db = tmp_path / "commit_show.db"
    state = _mk_state(db)
    show_file._replace_patch_from_data(state, _payload_dicts(32, "OLD"))
    assert len(_db_rows(state)) == 32

    commits = {"n": 0}

    def _after_commit(sess):
        try:
            if sess.bind is state._show_engine:
                commits["n"] += 1
        except Exception:
            pass

    _sa_event.listen(_SASession, "after_commit", _after_commit)
    try:
        show_file._replace_patch_from_data(state, _payload_dicts(32, "NEW"))
    finally:
        _sa_event.remove(_SASession, "after_commit", _after_commit)

    assert commits["n"] == 1, f"Erwartet GENAU 1 Show-DB-Commit, real {commits['n']}"
    rows = _db_rows(state)
    assert len(rows) == 32
    assert all(r.label.startswith("NEW") for r in rows), "Alt-Inhalt nicht vollstaendig ersetzt"


# ── T3: Ueberlapp-Ueberleben / KEIN stiller Datenverlust ────────────────────

def test_t3_overlap_survives_open_and_is_reported(tmp_path):
    """(b) Blosses open_show (Re-Open ohne Load) entfernt NICHTS -> Zeilenzahl
    unveraendert (beweist: kein Auto-Dedup). (c) Der Adress-Konflikt wird als
    ValidationIssue('error') mit BEIDEN fids gemeldet. (a) Ein sauberer atomarer
    Replace heilt die Altzeilen (exakt 32, keine Ueberlappung mehr)."""
    db = tmp_path / "overlap_show.db"
    state = _mk_state(db)
    # 32 saubere + 2 Ueberlapp-/Orphan-Zeilen direkt in die DB (distinkte fids!).
    clean = [_mk_pf(i, 1, 1 + (i - 1) * 10) for i in range(1, 33)]
    overlap = [
        _mk_pf(100, 1, 1, channel_count=4, label="ORPHAN@U1:1"),   # ueberlappt fid 1
        _mk_pf(101, 2, 500, channel_count=8, label="ORPHAN@U2:500"),
    ]
    with state._session() as s:
        s.add_all(clean + overlap)
        s.commit()
    assert len(_db_rows(state)) == 34

    # (b) Re-Open darf NICHTS loeschen.
    state.open_show(str(db))
    assert len(_db_rows(state)) == 34, "open_show hat still Zeilen entfernt (verbotener Dedup)"

    # (c) Konflikt wird gemeldet, nennt beide fids.
    issues = validate_and_repair(state, fix=True)
    conflict = [i for i in issues if "berlapp" in i.message or "Adresskonflikt" in i.message]
    assert conflict, f"Kein Adresskonflikt gemeldet. Issues: {[i.message for i in issues]}"
    # Beide fids EINDEUTIG genannt (die `[fid N]`-Klammer verhindert die
    # Substring-Falle "1" in "100").
    assert any("[fid 100]" in i.message and "[fid 1]" in i.message for i in conflict)
    # Nichts wurde durch den Report entfernt.
    assert len(_db_rows(state)) == 34

    # (a) Sauberer atomarer Replace heilt die Garbage-Zeilen.
    show_file._replace_patch_from_data(state, _payload_dicts(32))
    rows = _db_rows(state)
    assert len(rows) == 32
    assert _overlaps(rows) == []


# ── T4: Einzelprozess-Regression + replace_patch legt KEINE Gruppen an ──────

def test_t4_single_process_regression(tmp_path):
    """Happy-Path unveraendert: sauberer 32er-Load -> exakt 32/32 mit korrekten
    fids. Leerer Replace -> 0 Zeilen (Spiegel des Leer-Loads). replace_patch legt
    KEINE (Auto-Kopf-)FixtureGroup an (Gruppen kommen separat via
    _restore_fixture_groups)."""
    from src.core.database.models import FixtureGroup
    db = tmp_path / "single_show.db"
    state = _mk_state(db)

    show_file._replace_patch_from_data(state, _payload_dicts(32))
    rows = _db_rows(state)
    assert [r.fid for r in rows] == list(range(1, 33))
    assert len(state.get_patched_fixtures()) == 32

    # replace_patch beruehrt die Gruppen-Tabelle nie.
    with state._session() as s:
        assert s.execute(select(FixtureGroup)).scalars().first() is None

    # Leerer Patch -> 0 Zeilen (Spiegel des reset/Leer-Loads).
    state.replace_patch([])
    assert _db_rows(state) == []
    assert state.get_patched_fixtures() == []


# ── T5: busy_timeout serialisiert statt sofort 'database is locked' ─────────

def test_t5_busy_timeout_waits_instead_of_erroring(tmp_path):
    """Haelt ein Fremd-Writer kurz einen EXCLUSIVE-Lock, WARTET der zweite Writer
    (busy_timeout=5000) und gelingt, statt sofort OperationalError zu werfen."""
    db = tmp_path / "busy_show.db"
    state = _mk_state(db)  # setzt busy_timeout=5000 pro Connection

    locked = threading.Event()
    release = threading.Event()

    def holder():
        conn = sqlite3.connect(str(db), timeout=10)
        conn.isolation_level = None
        # BEGIN IMMEDIATE erlangt SOFORT den Write-Lock (ohne dass ein Statement
        # noetig waere) und haelt ihn bis zum COMMIT.
        conn.execute("BEGIN IMMEDIATE")
        locked.set()
        release.wait(timeout=5)
        time.sleep(0.6)   # Lock ~0.6s halten
        conn.commit()
        conn.close()

    th = threading.Thread(target=holder)
    th.start()
    assert locked.wait(timeout=5), "Holder hat den Lock nicht erlangt"

    t0 = time.perf_counter()
    release.set()
    # Zweiter Writer ueber die state-Engine (busy_timeout aktiv) — muss WARTEN,
    # nicht sofort OperationalError('database is locked') werfen.
    state.replace_patch([_mk_pf(6000, 1, 410)])
    elapsed = time.perf_counter() - t0
    th.join(timeout=5)

    assert elapsed >= 0.3, f"Write hat nicht gewartet ({elapsed:.3f}s) -> busy_timeout wirkt nicht"
    fids = {r.fid for r in _db_rows(state)}
    assert 6000 in fids, "Der wartende Write muss danach persistiert sein"


# ── WAL-Guard-Einheitstests (kein DB-Zugriff) ───────────────────────────────

def test_wal_guard_rejects_unc_and_sync_folders():
    assert _is_local_writable_path(r"\\server\share\data\current_show.db") is False
    assert _is_local_writable_path(r"C:\Users\X\OneDrive\data\current_show.db") is False
    assert _is_local_writable_path(r"C:\Users\X\Dropbox\lightos\current_show.db") is False


def test_pragmas_never_crash_on_bad_connection():
    class _BoomConn:
        def cursor(self):
            raise RuntimeError("kaputt")
    # Darf NIE werfen (open_show muss robust bleiben).
    _set_sqlite_pragmas(_BoomConn(), True)
    _set_sqlite_pragmas(_BoomConn(), False)


def test_pragmas_enable_wal_and_busy_timeout(tmp_path):
    """wal_ok=True setzt busy_timeout=5000 UND journal_mode=WAL."""
    db = tmp_path / "wal_on.db"
    conn = sqlite3.connect(str(db))
    _set_sqlite_pragmas(conn, wal_ok=True)
    assert int(conn.execute("PRAGMA busy_timeout").fetchone()[0]) == 5000
    assert str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal"
    conn.close()


def test_wal_downgraded_when_path_becomes_unsafe(tmp_path):
    """Regression F2 (HIGH): eine bereits (an sicherem Ort) auf WAL gesetzte DB
    wird bei wal_ok=False AKTIV auf DELETE zurückgeschaltet — reines
    'WAL nicht einschalten' reicht nicht, weil journal_mode persistent ist."""
    db = tmp_path / "wal_inherited.db"
    # 1. DB persistent in WAL versetzen (frühere, sichere Session).
    seed = sqlite3.connect(str(db))
    seed.execute("PRAGMA journal_mode=WAL")
    seed.execute("CREATE TABLE t(x)")
    seed.commit()
    assert str(seed.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal"
    seed.close()
    # 2. Pfad gilt jetzt als unsicher -> Downgrade erzwingen.
    conn = sqlite3.connect(str(db))
    _set_sqlite_pragmas(conn, wal_ok=False)
    mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
    conn.close()
    assert mode != "wal", f"geerbtes WAL nicht heruntergeschaltet (mode={mode})"
