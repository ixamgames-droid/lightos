"""Tests fuer die atomare, verlustsichere Persistenz des BPM-Analyse-Caches (BPM-03).

Der Cache (`src/core/audio/bpm_cache.py`) schrieb die JSON-Datei frueher direkt per
``open(_PATH, "w")`` — ein Absturz oder ein paralleler Schreiber konnte eine halbe/
0-Byte-grosse (also korrupte) Datei = stiller Totalverlust hinterlassen; zudem war das
Read-modify-write ungelockt (Lost-Update bei paralleler Stapelanalyse).

Diese Tests sichern die Reparatur ab:
(a) eine bereits korrupte/halbe Cache-Datei fuehrt zu keinem Crash und wird sauber
    ueberschrieben,
(b) ein Schreibvorgang laesst NIE eine 0-Byte-/halbe Ziel-Datei zurueck — der Schreibpfad
    geht ueber eine Temp-Datei + os.replace() (kein direktes open(w) auf der Zieldatei),
    und ein Fehler mitten im Schreiben laesst die vorhandene gute Datei unangetastet.
"""
from __future__ import annotations
import json
import os

import pytest

from src.core.audio import bpm_cache


@pytest.fixture()
def cache_env(tmp_path, monkeypatch):
    """Lenkt den modul-globalen Cache-Pfad in ein Temp-Verzeichnis um und liefert
    einen realen 'Audio'-Dateipfad (noetig, weil _key() os.stat() darauf ruft)."""
    cdir = tmp_path / "LightOS"
    cdir.mkdir()
    monkeypatch.setattr(bpm_cache, "_DIR", str(cdir))
    monkeypatch.setattr(bpm_cache, "_PATH", str(cdir / "bpm_analysis_cache.json"))
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"\x00" * 64)          # Inhalt egal, muss nur existieren (mtime/size)
    return str(audio), str(cdir), str(cdir / "bpm_analysis_cache.json")


_TL = {"bpm": 128.0, "beats_ms": [0, 469, 938]}


def test_corrupt_existing_file_rebuilds_cleanly(cache_env):
    """(a) Halb/korrupt vorhandene Cache-Datei -> put() baut sauber neu, kein Crash."""
    audio, _cdir, path = cache_env
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"halb": {"timeline": {"bpm": 1')   # abgeschnittenes JSON

    # get() auf korrupter Datei darf nicht werfen und liefert keinen Treffer
    assert bpm_cache.get(audio, "eng", "genre", 4) is None

    # put() ueberschreibt die korrupte Datei sauber
    bpm_cache.put(audio, "eng", "genre", 4, _TL, [0.1, 0.2])

    hit = bpm_cache.get(audio, "eng", "genre", 4)
    assert hit is not None and hit["timeline"] == _TL
    # Datei ist jetzt valides JSON
    with open(path, encoding="utf-8") as f:
        json.load(f)


def test_zero_byte_file_is_tolerated(cache_env):
    """(a') 0-Byte-Datei (typischer Rest eines abgebrochenen Schreibers) -> kein Crash."""
    audio, _cdir, path = cache_env
    open(path, "w").close()                          # 0 Bytes
    assert os.path.getsize(path) == 0

    assert bpm_cache.get(audio, "eng", "genre", 4) is None
    bpm_cache.put(audio, "eng", "genre", 4, _TL, [])
    assert bpm_cache.get(audio, "eng", "genre", 4)["timeline"] == _TL


def test_write_goes_through_tempfile_and_replace(cache_env, monkeypatch):
    """(b) Der Schreibpfad oeffnet die ZIELDATEI NIE direkt zum Schreiben — er geht
    ueber os.replace(). Wir spionieren os.replace und stellen sicher, dass genau die
    Zieldatei per Rename (nicht per open(w)) entsteht."""
    audio, _cdir, path = cache_env
    real_replace = os.replace
    calls = []

    def spy_replace(src, dst, *a, **kw):
        calls.append((src, dst))
        return real_replace(src, dst, *a, **kw)

    monkeypatch.setattr(bpm_cache.os, "replace", spy_replace)

    # Ziel darf zu Beginn nicht existieren
    assert not os.path.exists(path)
    bpm_cache.put(audio, "eng", "genre", 4, _TL, [0.5])

    # Genau ein Rename auf die Zieldatei; Quelle war eine ANDERE (Temp-)Datei
    assert len(calls) == 1
    src, dst = calls[0]
    assert os.path.abspath(dst) == os.path.abspath(path)
    assert os.path.abspath(src) != os.path.abspath(path)
    # Ergebnis vollstaendig lesbar
    assert bpm_cache.get(audio, "eng", "genre", 4)["timeline"] == _TL


def test_failed_write_leaves_previous_file_intact(cache_env, monkeypatch):
    """(b) Bricht der Schreibvorgang ab, bleibt KEINE 0-Byte-/halbe Zieldatei zurueck:
    die vorher gueltige Datei ueberlebt byte-identisch (Beweis, dass NICHT direkt auf die
    Zieldatei geschrieben wird)."""
    audio, _cdir, path = cache_env
    # 1) gueltigen Erst-Stand schreiben
    bpm_cache.put(audio, "eng", "genre", 4, _TL, [0.1])
    good_bytes = open(path, "rb").read()
    assert len(good_bytes) > 0

    # 2) json.dump beim naechsten Schreiben mitten im Vorgang crashen lassen
    def boom(*a, **kw):
        raise RuntimeError("disk full mid-write")

    monkeypatch.setattr(bpm_cache.json, "dump", boom)

    # put() faengt intern und darf nicht werfen
    bpm_cache.put(audio, "eng2", "genre", 4, {"bpm": 90.0}, [])

    # Zieldatei ist unveraendert (nicht 0 Byte, nicht halb) und weiterhin valide
    assert open(path, "rb").read() == good_bytes
    with open(path, encoding="utf-8") as f:
        json.load(f)
    # Keine Temp-Reste im Verzeichnis liegen geblieben
    leftovers = [n for n in os.listdir(_cdir) if n.startswith(".bpm_cache-")]
    assert leftovers == []


def test_concurrent_puts_no_lost_update(cache_env):
    """RMW-Absicherung: parallele put()-Aufrufe aus mehreren Threads cachen jeweils einen
    eigenen Song -> am Ende sind ALLE Eintraege da (kein Lost-Update)."""
    import threading

    audio_base, cdir, _path = cache_env
    songs = []
    for i in range(12):
        p = os.path.join(cdir, f"song_{i}.wav")
        with open(p, "wb") as f:
            f.write(bytes([i]) * (100 + i))
        songs.append(p)

    barrier = threading.Barrier(len(songs))

    def worker(p):
        barrier.wait()                               # moeglichst gleichzeitig starten
        bpm_cache.put(p, "eng", "genre", 4, {"bpm": 120.0, "who": p}, [0.0])

    threads = [threading.Thread(target=worker, args=(p,)) for p in songs]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Jeder Song muss einen eigenen Cache-Treffer haben
    for p in songs:
        hit = bpm_cache.get(p, "eng", "genre", 4)
        assert hit is not None and hit["timeline"]["who"] == p
