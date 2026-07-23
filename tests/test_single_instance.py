"""Mehrfachstarts duerfen native Audio/MIDI/Qt-Ressourcen nicht duplizieren."""
import os
import tempfile

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
