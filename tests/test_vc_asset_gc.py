"""VC-IMG-GC — Cache-GC für VC-Button-Hintergrund-Assets.

``show_file.load_show`` entpackt die eingebetteten Assets JEDER geladenen Show in
den lokalen Cache (``%APPDATA%/LightOS/vc_assets/``), räumte lokal aber nichts
weg -> unbegrenztes Wachstum. ``vc_assets.prune`` deckelt den Cache per LRU
(mtime), ohne die vom aktuellen Show referenzierten Assets anzutasten.

Die Sicherheits-Invarianten wurden aus einer adversarialen Review abgeleitet
(Cross-Session-Datenverlust, Dedup-mtime, inf-Env, ``.tmp``-Reihenfolge,
Über-Eviction bei paralleler Löschung, verlustfreier Save-Round-Trip).
"""
from __future__ import annotations
import os
import time

import pytest

from src.core.show import vc_assets


@pytest.fixture()
def cache(tmp_path):
    """Cache-Verzeichnis in ein tmp umbiegen (verschmutzt sonst den echten Cache)."""
    d = tmp_path / "vc_assets"
    d.mkdir()
    vc_assets.set_cache_dir_for_test(str(d))
    try:
        yield d
    finally:
        vc_assets.set_cache_dir_for_test(None)


def _key(i: int, ext: str = ".png") -> str:
    """Deterministischer, gültiger Asset-Key (40 Hex + Extension)."""
    k = f"{i:040x}{ext}"
    assert vc_assets.is_valid_key(k), k
    return k


def _write(cache_dir, key: str, size: int, *, age_s: float, now: float) -> str:
    """Datei mit gegebener Größe und (now - age_s)-mtime schreiben -> Pfad."""
    p = os.path.join(str(cache_dir), key)
    with open(p, "wb") as f:
        f.write(b"\0" * size)
    t = now - age_s
    os.utime(p, (t, t))
    return p


NOW = 1_000_000.0
OLD = 10_000.0     # deutlich älter als die Default-min-age


# ── Grund-Verhalten ──────────────────────────────────────────────────────────

def test_noop_when_under_cap(cache):
    for i in range(3):
        _write(cache, _key(i), 10, age_s=OLD, now=NOW)
    removed = vc_assets.prune(max_bytes=10_000, min_age_seconds=1.0, now=NOW)
    assert removed == 0
    assert len(os.listdir(str(cache))) == 3


def test_evicts_oldest_first_over_cap(cache):
    # 3 Dateien à 100 B, Deckel 150 B -> die 2 ältesten weichen, 1 bleibt.
    p0 = _write(cache, _key(0), 100, age_s=OLD + 300, now=NOW)  # ältestes
    p1 = _write(cache, _key(1), 100, age_s=OLD + 200, now=NOW)
    p2 = _write(cache, _key(2), 100, age_s=OLD + 100, now=NOW)  # jüngstes
    removed = vc_assets.prune(max_bytes=150, min_age_seconds=1.0, now=NOW)
    assert removed == 2
    assert not os.path.exists(p0)
    assert not os.path.exists(p1)
    assert os.path.exists(p2)          # jüngstes überlebt


def test_never_evicts_kept_keys(cache):
    keep_key = _key(0)
    p_keep = _write(cache, keep_key, 100, age_s=OLD + 999, now=NOW)  # ältestes!
    p_other = _write(cache, _key(1), 100, age_s=OLD, now=NOW)
    removed = vc_assets.prune(keep={keep_key}, max_bytes=50,
                              min_age_seconds=1.0, now=NOW)
    assert removed == 1
    assert os.path.exists(p_keep)      # referenziert -> tabu, obwohl am ältesten
    assert not os.path.exists(p_other)


def test_respects_min_age(cache):
    # Über dem Deckel, aber alle Dateien frisch -> nichts evicten
    # (schützt frische Entpackungen einer parallelen Session).
    for i in range(3):
        _write(cache, _key(i), 100, age_s=1.0, now=NOW)
    removed = vc_assets.prune(max_bytes=50, min_age_seconds=300.0, now=NOW)
    assert removed == 0
    assert len(os.listdir(str(cache))) == 3


def test_ignores_foreign_files(cache):
    foreign = os.path.join(str(cache), "notes.txt")
    with open(foreign, "wb") as f:
        f.write(b"\0" * 10_000)
    os.utime(foreign, (NOW - OLD, NOW - OLD))
    _write(cache, _key(0), 100, age_s=OLD, now=NOW)
    removed = vc_assets.prune(max_bytes=1, min_age_seconds=1.0, now=NOW)
    assert removed == 1
    assert os.path.exists(foreign)     # fremde Datei nie angetastet


def test_missing_cache_dir_is_safe(tmp_path):
    missing = tmp_path / "nope"
    vc_assets.set_cache_dir_for_test(str(missing))
    try:
        assert vc_assets.prune(max_bytes=0, min_age_seconds=1.0, now=NOW) == 0
    finally:
        vc_assets.set_cache_dir_for_test(None)


# ── .tmp-Reihenfolge (Review-Fund: valid <hex>.tmp Key vs. Scratch-.tmp) ──────

def test_removes_stale_scratch_tmp_only(cache):
    # <40hex>.png.tmp = zwei Punkte -> KEIN gültiger Key -> Scratch-Rest.
    stale = _write(cache, _key(0) + ".tmp", 100, age_s=OLD, now=NOW)
    fresh = _write(cache, _key(1) + ".tmp", 100, age_s=1.0, now=NOW)
    vc_assets.prune(max_bytes=10 ** 9, min_age_seconds=300.0, now=NOW)
    assert not os.path.exists(stale)   # alter Scratch-Rest weggeräumt
    assert os.path.exists(fresh)       # frischer Rest (evtl. in Arbeit) bleibt


def test_valid_tmp_key_is_keep_protected(cache):
    # Ein GÜLTIGER <40hex>.tmp-Key (z. B. aus einer handgebauten .lshow) darf NICHT
    # über den Scratch-.tmp-Sonderpfad gelöscht werden — keep schützt ihn.
    tmp_key = f"{0:040x}.tmp"
    assert vc_assets.is_valid_key(tmp_key)
    p = _write(cache, tmp_key, 100, age_s=OLD, now=NOW)
    removed = vc_assets.prune(keep={tmp_key}, max_bytes=1,
                              min_age_seconds=1.0, now=NOW)
    assert removed == 0
    assert os.path.exists(p)


# ── Robustheit gegen parallele Sessions ──────────────────────────────────────

def test_locked_file_does_not_abort_run(cache, monkeypatch):
    # Ein Datei-Lock (OSError beim Löschen, z. B. laufendes QMovie) übersprungen,
    # die übrigen evictbaren Dateien werden trotzdem geräumt.
    p0 = _write(cache, _key(0), 100, age_s=OLD + 200, now=NOW)   # ältestes -> Lock
    p1 = _write(cache, _key(1), 100, age_s=OLD + 100, now=NOW)
    real_remove = os.remove

    def flaky_remove(path, *a, **k):
        if os.path.normpath(path) == os.path.normpath(p0):
            raise PermissionError("locked (QMovie hält die Datei)")
        return real_remove(path, *a, **k)

    monkeypatch.setattr(os, "remove", flaky_remove)
    removed = vc_assets.prune(max_bytes=50, min_age_seconds=1.0, now=NOW)
    assert removed == 1
    assert os.path.exists(p0)          # gelockt -> übersprungen, nicht geworfen
    assert not os.path.exists(p1)


def test_concurrent_deletion_does_not_over_evict(cache, monkeypatch):
    # Review-Fund: löscht eine PARALLELE prune-Session eine Datei schon weg
    # (FileNotFoundError), darf `total` trotzdem sinken — sonst würde diese Session
    # unter den Deckel hinaus weitere, jüngere Assets über-evicten.
    pA = _write(cache, _key(0), 100, age_s=OLD + 300, now=NOW)   # ältestes, "schon weg"
    pB = _write(cache, _key(1), 100, age_s=OLD + 200, now=NOW)
    pC = _write(cache, _key(2), 100, age_s=OLD + 100, now=NOW)   # jüngstes
    real_remove = os.remove

    def fnf_remove(path, *a, **k):
        if os.path.normpath(path) == os.path.normpath(pA):
            raise FileNotFoundError("parallele Session hat's schon geräumt")
        return real_remove(path, *a, **k)

    monkeypatch.setattr(os, "remove", fnf_remove)
    removed = vc_assets.prune(max_bytes=150, min_age_seconds=1.0, now=NOW)
    assert removed == 1                # nur B echt entfernt (A war schon weg)
    assert not os.path.exists(pB)
    assert os.path.exists(pC)          # jüngstes NICHT über-evictet


def test_dedup_write_refreshes_mtime(cache):
    # Review-Fund: erneutes Referenzieren (Content-Hash-Dedup) muss die mtime
    # auffrischen, sonst altert ein noch aktiv gebrauchtes Asset unter min_age.
    data = b"dedup-mtime-content"
    key = vc_assets.store_bytes(data, ".png")
    p = os.path.join(str(cache), key)
    old = time.time() - 10_000
    os.utime(p, (old, old))
    assert (time.time() - os.stat(p).st_mtime) > 5_000
    vc_assets.store_extracted(key, data)               # Dedup-Pfad (Datei existiert)
    assert (time.time() - os.stat(p).st_mtime) < 60     # mtime aufgefrischt


# ── Env-Override / inf-Guard (Review-Fund) ───────────────────────────────────

@pytest.mark.parametrize("val", ["inf", "Infinity", "1e400", "nan", "-5", "abc", "0"])
def test_bad_env_max_bytes_falls_back_and_never_throws(cache, monkeypatch, val):
    monkeypatch.setenv("LIGHTOS_VC_ASSET_CACHE_MB", val)
    _write(cache, _key(0), 100, age_s=OLD, now=NOW)
    # Fällt auf DEFAULT_MAX_BYTES (256 MB) zurück, wirft nie -> 100 B < Deckel -> 0.
    assert vc_assets.prune(min_age_seconds=1.0, now=NOW) == 0


def test_env_override_applies_when_valid(cache, monkeypatch):
    monkeypatch.setenv("LIGHTOS_VC_ASSET_CACHE_MB", "0.0001")   # ~104 B
    _write(cache, _key(0), 100, age_s=OLD + 100, now=NOW)
    _write(cache, _key(1), 100, age_s=OLD, now=NOW)
    assert vc_assets.prune(min_age_seconds=1.0, now=NOW) == 1   # 200 B > ~104 B


# ── Integration durch load_show / save_show (echte Wege, kein Mock) ───────────

def test_load_show_evicts_orphan_keeps_referenced(cache, monkeypatch):
    # End-to-End: load_show ruft prune real auf. Verwaistes Asset weg, das vom
    # geladenen Show referenzierte (obwohl alt) bleibt.
    import json as _json
    import zipfile
    from src.core.show import show_file

    referenced = _key(7)
    orphan = _key(8)
    real_now = time.time()
    p_ref = _write(cache, referenced, 200, age_s=10_000, now=real_now)
    p_orph = _write(cache, orphan, 200, age_s=10_000, now=real_now)
    monkeypatch.setenv("LIGHTOS_VC_ASSET_CACHE_MB", "0.0001")   # ~104 B -> Cache über Limit

    show = {"version": "1.1",
            "virtual_console": {"pages": [{"widgets": [{"bg_image": referenced}]}]}}
    path = os.path.join(str(cache.parent), "orphan_evict.lshow")
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("show.json", _json.dumps(show))

    ok, msg = show_file.load_show(path)
    assert ok, msg
    assert not os.path.exists(p_orph), "verwaistes Asset wurde nicht evictet"
    assert os.path.exists(p_ref), "referenziertes (live) Asset fälschlich evictet"


def test_save_show_carries_forward_missing_asset(cache, tmp_path):
    # Review-Fund (high): evictet eine parallele Session das Asset aus dem Cache,
    # darf der nächste Save es NICHT still fallenlassen — es wird verlustfrei aus
    # der bestehenden .lshow übernommen (und der Cache re-geheilt).
    import zipfile
    from src.core.app_state import get_state
    from src.core.show import show_file

    data = b"carry-forward-fake-png-bytes"
    key = vc_assets.store_bytes(data, ".png")
    state = get_state()
    state._vc_layout = {"pages": [{"widgets": [{"bg_image": key}]}]}

    path = os.path.join(str(tmp_path), "carry.lshow")
    show_file.save_show(path)                       # 1) Asset eingebettet
    with zipfile.ZipFile(path) as zf:
        assert vc_assets.zip_name(key) in zf.namelist()

    # Cross-Session-Eviction simulieren:
    os.remove(os.path.join(str(cache), key))
    assert vc_assets.resolve(key) == ""

    show_file.save_show(path)                       # 2) Save darf Asset nicht verlieren
    with zipfile.ZipFile(path) as zf:
        assert vc_assets.zip_name(key) in zf.namelist(), \
            "carry-forward verlor das referenzierte Asset -> Datenverlust!"
    assert vc_assets.resolve(key) != ""             # Cache re-geheilt
