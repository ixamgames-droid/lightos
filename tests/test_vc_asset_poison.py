"""CDX-15 — VC-Asset-Cache-Poisoning-Schutz.

``store_extracted`` bekommt den Content-Hash-Key aus dem (untrusted) ZIP-Eintrags-
namen einer ``.lshow``. Ohne Prüfung könnte eine manipulierte Show unter einem
legitimen ``<sha1>.png``-Key Fremdinhalt in den GLOBALEN Cache
(`%APPDATA%/LightOS/vc_assets/`) schreiben und ihn dauerhaft vergiften (``_write_atomic``
überschreibt bestehende Dateien nicht). Der Fix prüft ``sha1(data)`` gegen den Key.
"""
from __future__ import annotations
import hashlib
import os

import pytest

from src.core.show import vc_assets


@pytest.fixture()
def cache(tmp_path):
    d = tmp_path / "vc_assets"
    d.mkdir()
    vc_assets.set_cache_dir_for_test(str(d))
    try:
        yield d
    finally:
        vc_assets.set_cache_dir_for_test(None)


def _key_for(data: bytes, ext: str = ".png") -> str:
    return hashlib.sha1(data).hexdigest() + ext


# ── content_matches_key ──────────────────────────────────────────────────────

def test_content_matches_key_true_for_consistent_bytes():
    data = b"the real bytes"
    assert vc_assets.content_matches_key(_key_for(data), data) is True


def test_content_matches_key_false_for_mismatch():
    good = b"the real bytes"
    key = _key_for(good)                       # Key des GUTEN Inhalts
    assert vc_assets.content_matches_key(key, b"evil different bytes") is False


def test_content_matches_key_false_for_invalid_key():
    assert vc_assets.content_matches_key("../evil.png", b"x") is False
    assert vc_assets.content_matches_key("", b"x") is False


# ── store_extracted ──────────────────────────────────────────────────────────

def test_store_extracted_accepts_matching_bytes(cache):
    data = b"legit image payload"
    key = _key_for(data)
    vc_assets.store_extracted(key, data)
    assert vc_assets.resolve(key) != ""        # abgelegt
    assert vc_assets.bytes_for(key) == data


def test_store_extracted_rejects_mismatched_bytes(cache):
    good = b"legit image payload"
    key = _key_for(good)                        # gültiger Key des GUTEN Inhalts
    vc_assets.store_extracted(key, b"evil payload with wrong hash")
    assert vc_assets.resolve(key) == ""         # NICHT abgelegt (Poisoning verhindert)


def test_store_extracted_cannot_poison_existing_legit_key(cache):
    # Der Kern-Angriff: ein legitimes Asset liegt bereits korrekt im Cache; eine
    # manipulierte .lshow will denselben Key mit Fremdinhalt überschreiben.
    good = b"the genuine asset bytes"
    key = vc_assets.store_bytes(good, ".png")   # legit über den sicheren Pfad
    assert vc_assets.bytes_for(key) == good

    vc_assets.store_extracted(key, b"attacker controlled bytes")   # Angriff
    assert vc_assets.bytes_for(key) == good     # Cache unverändert, nicht vergiftet


def test_store_extracted_rejects_nonimage_ext_even_if_hash_matches(cache):
    # Härtung: ein hash-konsistenter, aber exotischer <sha1>.exe-Key (aus einer
    # manipulierten .lshow) darf nicht als Datei im Cache landen.
    data = b"payload that is self-consistent"
    exe_key = hashlib.sha1(data).hexdigest() + ".exe"
    assert vc_assets.is_valid_key(exe_key)            # syntaktisch gültig …
    assert vc_assets.content_matches_key(exe_key, data)   # … und hash-konsistent …
    vc_assets.store_extracted(exe_key, data)
    assert vc_assets.resolve(exe_key) == ""          # … trotzdem NICHT abgelegt

    png_key = hashlib.sha1(data).hexdigest() + ".png"
    vc_assets.store_extracted(png_key, data)         # gleiche Bytes, erlaubte Ext
    assert vc_assets.resolve(png_key) != ""          # -> abgelegt


def test_store_bytes_path_still_consistent(cache):
    # Regression: der sichere Import-Pfad (hasht selbst) bleibt funktionsfähig.
    data = b"imported content"
    key = vc_assets.store_bytes(data, ".gif")
    assert vc_assets.content_matches_key(key, data)
    assert vc_assets.resolve(key) != ""


# ── Integration durch load_show ──────────────────────────────────────────────

def test_load_show_rejects_poisoned_asset_entry(cache):
    import json as _json
    import zipfile
    from src.core.show import show_file

    good = b"what the key legitimately hashes to"
    key = _key_for(good, ".png")                # referenzierter, legitimer Key
    evil = b"malicious substitute content"      # anderer Inhalt unter demselben Key

    show = {"version": "1.1",
            "virtual_console": {"pages": [{"widgets": [{"bg_image": key}]}]}}
    path = os.path.join(str(cache.parent), "poisoned.lshow")
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("show.json", _json.dumps(show))
        zf.writestr(vc_assets.zip_name(key), evil)   # vergifteter Asset-Eintrag

    ok, msg = show_file.load_show(path)
    assert ok, msg
    # Die vergifteten Bytes dürfen NICHT im Cache gelandet sein.
    assert vc_assets.resolve(key) == ""
