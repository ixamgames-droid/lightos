"""Mehrfachstarts duerfen native Audio/MIDI/Qt-Ressourcen nicht duplizieren."""
import os
import tempfile

import pytest

from src.core import single_instance
from src.core.single_instance import acquire_instance_lock


def test_second_instance_lock_is_rejected_until_first_closes():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "lightos.instance.lock")
        first = acquire_instance_lock(path)
        assert first is not None
        try:
            assert acquire_instance_lock(path) is None
        finally:
            first.close()

        again = acquire_instance_lock(path)
        assert again is not None
        again.close()


def test_unusable_lock_file_does_not_block_startup(monkeypatch, tmp_path):
    """Nicht anlegbare Sperrdatei != "laeuft schon".

    Rechteproblem, read-only Ordner oder ein zickiger Cloud-/Netzpfad duerfen
    LightOS NICHT am Start hindern. Nur ``None`` heisst "andere Instanz laeuft";
    hier muss eine benutzbare (wenn auch wirkungslose) Lease zurueckkommen.
    """
    def _boom(*_a, **_kw):
        raise PermissionError("Zugriff verweigert")

    monkeypatch.setattr(single_instance.os, "makedirs", _boom)
    lease = acquire_instance_lock(str(tmp_path / "sub" / "lightos.instance.lock"))
    assert lease is not None, "Startabbruch bei nicht anlegbarer Sperrdatei"
    lease.close()   # muss ohne Fehler durchlaufen


@pytest.mark.skipif(os.name != "nt", reason="Windows-spezifischer msvcrt-Pfad")
def test_windows_lock_holds_across_reacquire(tmp_path):
    """Windows: die msvcrt-Sperre muss den zweiten Versuch wirklich abweisen."""
    path = str(tmp_path / "lightos.instance.lock")
    first = acquire_instance_lock(path)
    assert first is not None
    try:
        assert acquire_instance_lock(path) is None
    finally:
        first.close()
