"""Undo/Redo - Command-Pattern mit UndoStack.

Verwendung:
    from src.core.undo import get_undo_stack, Command
    stack = get_undo_stack()
    stack.push(Command(label="Fixture +", do=lambda: state.add_fixture(f),
                       undo=lambda: state.remove_fixture(f.fid)))

Im Main Menue: Ctrl+Z (stack.undo()) / Ctrl+Y (stack.redo()).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable


@dataclass
class Command:
    """Eine atomare, rueckgaengig-machbare Aktion."""
    label: str
    do: Callable[[], None]
    undo: Callable[[], None]
    # Optional Redo, falls do() Seiteneffekte hat die nicht wiederholbar sind
    redo: Callable[[], None] | None = None

    def execute(self):
        self.do()

    def revert(self):
        self.undo()

    def reexecute(self):
        if self.redo is not None:
            self.redo()
        else:
            self.do()


class UndoStack:
    """Stack mit Undo/Redo. MAX_SIZE Eintraege als FIFO."""

    MAX_SIZE = 100

    def __init__(self):
        self._undo: list[Command] = []
        self._redo: list[Command] = []
        self._listeners: list[Callable[[], None]] = []
        self._suspended: int = 0   # waehrend undo()/redo() keine push

    # ── Push / Execute ───────────────────────────────────────────────────────

    def push(self, cmd: Command, execute: bool = True):
        """Pusht ein Command auf den Stack und fuehrt es (optional) aus."""
        if self._suspended:
            return
        if execute:
            try:
                cmd.execute()
            except Exception as e:
                print(f"[UndoStack] execute error: {e}")
                return
        self._undo.append(cmd)
        # Cap
        if len(self._undo) > self.MAX_SIZE:
            self._undo = self._undo[-self.MAX_SIZE:]
        self._redo.clear()
        self._notify()

    def push_simple(self, label: str, do, undo):
        """Shortcut: push(Command(label, do, undo))."""
        self.push(Command(label=label, do=do, undo=undo))

    # ── Undo / Redo ──────────────────────────────────────────────────────────

    def undo(self) -> bool:
        if not self._undo:
            return False
        cmd = self._undo.pop()
        self._suspended += 1
        try:
            cmd.revert()
        except Exception as e:
            print(f"[UndoStack] undo error: {e}")
        finally:
            self._suspended -= 1
        self._redo.append(cmd)
        self._notify()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        cmd = self._redo.pop()
        self._suspended += 1
        try:
            cmd.reexecute()
        except Exception as e:
            print(f"[UndoStack] redo error: {e}")
        finally:
            self._suspended -= 1
        self._undo.append(cmd)
        self._notify()
        return True

    def can_undo(self) -> bool:
        return len(self._undo) > 0

    def can_redo(self) -> bool:
        return len(self._redo) > 0

    def undo_label(self) -> str | None:
        return self._undo[-1].label if self._undo else None

    def redo_label(self) -> str | None:
        return self._redo[-1].label if self._redo else None

    def clear(self):
        self._undo.clear()
        self._redo.clear()
        self._notify()

    # ── Listener ─────────────────────────────────────────────────────────────

    def subscribe(self, cb):
        if cb not in self._listeners:
            self._listeners.append(cb)

    def _notify(self):
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                pass


_stack: UndoStack | None = None


def get_undo_stack() -> UndoStack:
    global _stack
    if _stack is None:
        _stack = UndoStack()
    return _stack
