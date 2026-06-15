"""Regression: ein Chaser, der sich selbst (direkt oder zyklisch) als Schritt
referenziert, darf beim Abspielen NICHT in eine Endlos-Rekursion laufen.

`Chaser._render_child_target` rendert jeden Schritt-Child über `child.write()`.
Zeigt ein Schritt auf den Chaser selbst (oder schließt sich ein Zyklus
A→B→A), würde das endlos rekursiv `write()` aufrufen → Stack-Overflow/Absturz.
Ein Re-Entrancy-Guard in `write()` bricht das ab. Zusätzlich blendet der
Chaser-Editor den bearbeiteten Chaser aus der Funktionsauswahl aus.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.function_manager import get_function_manager
from src.core.dmx.universe import Universe


def _fresh_fm():
    fm = get_function_manager()
    fm.stop_all()
    return fm


def test_self_referencing_chaser_does_not_crash():
    """Chaser mit sich selbst als Schritt: write() läuft ohne RecursionError."""
    fm = _fresh_fm()
    pre = {f.id for f in fm.all()}
    c = fm.new_chaser("SelfRef")
    try:
        c.add_step(c.id, hold=1.0)  # Selbstreferenz!
        registry = {f.id: f for f in fm.all()}
        universes = {1: Universe(1)}
        c.start()
        # Mehrere Frames — ohne Guard würde der erste schon abstürzen.
        for _ in range(3):
            c.write(universes, [], 0.05, registry)
        # Guard muss nach jedem write sauber zurückgesetzt sein.
        assert getattr(c, "_rendering", False) is False
    finally:
        c.stop()
        for f in list(fm.all()):
            if f.id not in pre:
                fm.remove(f.id)


def test_cyclic_chasers_do_not_crash():
    """Zyklus A→B→A: write() bricht die Rekursion sauber ab."""
    fm = _fresh_fm()
    pre = {f.id for f in fm.all()}
    a = fm.new_chaser("CycleA")
    b = fm.new_chaser("CycleB")
    try:
        a.add_step(b.id, hold=1.0)
        b.add_step(a.id, hold=1.0)
        registry = {f.id: f for f in fm.all()}
        universes = {1: Universe(1)}
        a.start()
        b.start()
        for _ in range(3):
            a.write(universes, [], 0.05, registry)
        assert getattr(a, "_rendering", False) is False
        assert getattr(b, "_rendering", False) is False
    finally:
        a.stop()
        b.stop()
        for f in list(fm.all()):
            if f.id not in pre:
                fm.remove(f.id)


def test_function_selector_excludes_chaser_itself():
    """Der bearbeitete Chaser darf nicht in der Schritt-Funktionsauswahl stehen."""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    QApplication.instance() or QApplication([])
    fm = _fresh_fm()
    pre = {f.id for f in fm.all()}
    c = fm.new_chaser("ExclSelf")
    try:
        from src.ui.views.chaser_editor import FunctionSelectorDialog
        dlg = FunctionSelectorDialog(exclude_id=c.id)
        ids = [dlg._list.item(i).data(Qt.ItemDataRole.UserRole)
               for i in range(dlg._list.count())]
        assert c.id not in ids, "Der Chaser selbst darf nicht auswählbar sein"
    finally:
        for f in list(fm.all()):
            if f.id not in pre:
                fm.remove(f.id)
