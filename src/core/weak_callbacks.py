"""Schwache Adapter fuer Callbacks langlebiger Nicht-Qt-Services.

Worker-Singletons (MIDI, Audio, Timecode) speichern Python-Callbacks stark.
Ein direkt registriertes ``self.method`` wuerde deshalb eine kurzlebige View
festhalten, wenn ihr Teardown ausbleibt.  Dieser Adapter behaelt nur den
Receiver schwach und meldet sich beim naechsten Dispatch selbst ab, falls die
View bereits verschwunden ist.
"""
from __future__ import annotations

from collections.abc import Callable
import weakref

try:
    from shiboken6 import isValid as _qt_is_valid
except Exception:  # pragma: no cover - non-Qt runtime
    _qt_is_valid = None


def weak_callback(method: Callable, unsubscribe: Callable[[Callable], None]) -> Callable:
    """Erzeuge einen Callback ohne starke Referenz auf ``method.__self__``.

    ``unsubscribe`` darf den langlebigen Service referenzieren.  Der Receiver
    wird ueber den Methodennamen spaet aufgeloest, damit auch Test-Overrides
    und reguläre Instanzmethoden unveraendert funktionieren.
    """
    receiver = getattr(method, "__self__", None)
    name = getattr(method, "__name__", None)
    if receiver is None or not name:
        raise TypeError("weak_callback erwartet eine gebundene Methode")

    receiver_ref = weakref.ref(receiver)

    def callback(*args, **kwargs):
        target = receiver_ref()
        valid = target is not None
        if valid and _qt_is_valid is not None:
            try:
                valid = _qt_is_valid(target)
            except TypeError:
                pass  # reguläres Python-Objekt, nicht von Shiboken verwaltet
        if not valid:
            try:
                unsubscribe(callback)
            except Exception:
                pass
            return None
        return getattr(target, name)(*args, **kwargs)

    return callback
