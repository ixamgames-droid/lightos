"""Processweite Einzelinstanz-Sperre fuer LightOS.

Mehrere parallel gestartete GUI-Prozesse konkurrieren um ALSA-MIDI, Audio,
QtWebEngine-Portale und DMX-Sockets. Ein zweiter Doppelklick soll deshalb sauber
enden, bevor native Backends oder eine QApplication initialisiert werden.
"""
from __future__ import annotations

import os
from typing import BinaryIO


def acquire_instance_lock(path: str) -> BinaryIO | None:
    """Sperrt ``path`` nicht-blockierend und haelt den Dateihandle als Lease.

    Rueckgabe ``None`` bedeutet: eine andere LightOS-Instanz haelt die Sperre.
    Der Aufrufer muss den erfolgreichen Handle fuer die gesamte Prozesslaufzeit
    referenziert halten.
    """
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        handle = open(path, "a+b")
    except OSError:
        return None

    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            if os.path.getsize(path) == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle
    except (OSError, IOError):
        try:
            handle.close()
        except OSError:
            pass
        return None
