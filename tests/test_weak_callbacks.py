"""Unit-Tests fuer schwache Worker-Callback-Adapter (STAB-21)."""
from __future__ import annotations

import gc
import weakref

from src.core.weak_callbacks import weak_callback


class _Source:
    def __init__(self):
        self.callbacks = []

    def subscribe(self, callback):
        self.callbacks.append(callback)

    def unsubscribe(self, callback):
        self.callbacks.remove(callback)

    def emit(self, value):
        for callback in list(self.callbacks):
            callback(value)


class _Receiver:
    def __init__(self):
        self.values = []

    def receive(self, value):
        self.values.append(value)


def test_weak_callback_forwards_while_receiver_is_alive():
    source = _Source()
    receiver = _Receiver()
    callback = weak_callback(receiver.receive, source.unsubscribe)
    source.subscribe(callback)

    source.emit(7)

    assert receiver.values == [7]
    assert source.callbacks == [callback]


def test_weak_callback_does_not_pin_receiver_and_self_unregisters():
    source = _Source()
    receiver = _Receiver()
    callback = weak_callback(receiver.receive, source.unsubscribe)
    source.subscribe(callback)
    receiver_ref = weakref.ref(receiver)

    del receiver
    gc.collect()
    assert receiver_ref() is None

    source.emit(7)
    assert source.callbacks == []
