"""Schwache Slot-Adapter gegen GC-unsichtbare Wrapper-Pins (STAB-09/STAB-10).

Hintergrund (PySide6 6.11 / Python 3.14, empirisch verifiziert): verbindet man
ein Qt-Signal mit einem **Lambda** (oder ``functools.partial``), haelt die
C++-Connection den Callable STARK und fuer die Python-GC UNSICHTBAR. Faengt
die Closure ``self``, ist der Widget-Wrapper damit von aussen gepinnt:

- er stirbt NIE per Refcount und ist auch fuer die zyklische GC unerreichbar
  (Leak bis zum C++-Tod des Senders), und
- stirbt sein C++-Objekt ueber die Qt-Eltern-Kaskade trotzdem, existiert ein
  lebender Wrapper auf freiem Speicher -> native Access Violation beim
  GC-Teardown (faulthandler: "Garbage-collecting"), die Crash-Klasse STAB-09.

**Bound-Method-Slots** bindet PySide6 dagegen schwach - fuer argumentlose
Slots ist ``sig.connect(self._methode)`` die beste Loesung. Fuer Slots mit
gebundenen Zusatz-Argumenten (das klassische ``lambda v, k=key: ...``-Muster)
liefern die Adapter hier denselben Komfort OHNE den Pin: sie halten den
Receiver nur ueber eine ``weakref`` und werden nach dessen Tod zum No-Op.

Verwendung::

    from src.ui.weak_slots import weak_slot, weak_slot_fwd

    btn.clicked.connect(weak_slot(self._do_clear, "programmer"))
    #   -> ruft self._do_clear("programmer"); Signal-Argumente werden VERWORFEN.

    spin.valueChanged.connect(weak_slot_fwd(self._on_row_changed, fid))
    #   -> ruft self._on_row_changed(fid, <signal-args...>).

Nicht verwenden fuer ``self.destroyed``-Teardown-Slots: dort ist der starke
Lambda-Pin GEWOLLT (ein schwach gebundener Slot wuerde abgemeldet, bevor das
C++-Objekt stirbt, und der Teardown liefe nie).
"""
from __future__ import annotations

import weakref


def _unbind(method):
    """(weakref auf Receiver, ungebundener Aufrufer) fuer eine gebundene
    Methode. Qt-Builtin-Methoden (z. B. ``setValue``) haben kein ``__func__``
    — dort wird ueber den Methodennamen am lebenden Objekt aufgeloest."""
    ref = weakref.ref(method.__self__)
    func = getattr(method, "__func__", None)
    if func is None:
        name = method.__name__

        def func(obj, *a):          # Builtin: spaet am Objekt nachschlagen
            return getattr(obj, name)(*a)

    return ref, func


def weak_slot(method, *args):
    """Slot-Adapter: ruft die gebundene Methode mit ``args`` auf und VERWIRFT
    alle Signal-Argumente. Haelt den Receiver nur schwach; nach dessen Tod
    ist der Slot ein stilles No-Op (die Connection stirbt mit dem Sender)."""
    ref, func = _unbind(method)

    def _slot(*_sig_args):
        obj = ref()
        if obj is not None:
            return func(obj, *args)

    return _slot


def weak_slot_fwd(method, *args):
    """Wie :func:`weak_slot`, reicht die Signal-Argumente aber NACH den
    gebundenen ``args`` an die Methode weiter."""
    ref, func = _unbind(method)

    def _slot(*sig_args):
        obj = ref()
        if obj is not None:
            return func(obj, *args, *sig_args)

    return _slot
