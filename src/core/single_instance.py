"""Processweite Einzelinstanz-Sperre fuer LightOS.

Mehrere parallel gestartete GUI-Prozesse konkurrieren um ALSA-MIDI, Audio,
QtWebEngine-Portale und DMX-Sockets. Ein zweiter Doppelklick soll deshalb sauber
enden, bevor native Backends oder eine QApplication initialisiert werden.
"""
from __future__ import annotations

import os
from typing import BinaryIO


class _NoLock:
    """Platzhalter-Lease: eine Sperre war technisch nicht moeglich.

    Bewusst NICHT ``None``: ``None`` heisst ausschliesslich „eine andere
    Instanz laeuft bereits". Ein nicht anlegbares Sperrfile (fehlende Rechte,
    read-only/Netz-/Cloud-Ordner) darf LightOS niemals am Start hindern —
    der Einzelinstanz-Schutz ist eine Komfortfunktion, kein Startkriterium.
    """

    def close(self) -> None:
        return None


def acquire_instance_lock(path: str) -> BinaryIO | _NoLock | None:
    """Sperrt ``path`` nicht-blockierend und haelt den Dateihandle als Lease.

    Rueckgabe ``None`` bedeutet: eine andere LightOS-Instanz haelt die Sperre
    (und NUR das). Laesst sich die Sperrdatei ueberhaupt nicht oeffnen, wird
    ein ``_NoLock``-Platzhalter geliefert — der Aufrufer startet dann normal
    weiter, nur ohne Mehrfachstart-Schutz.
    Der Aufrufer muss den erfolgreichen Handle fuer die gesamte Prozesslaufzeit
    referenziert halten.
    """
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        handle = open(path, "a+b")
    except OSError as exc:
        print(f"[single_instance] Sperrdatei nicht nutzbar ({exc}) — "
              "Mehrfachstart-Schutz deaktiviert, LightOS startet trotzdem.")
        return _NoLock()

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
