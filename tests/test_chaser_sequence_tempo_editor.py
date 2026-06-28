"""Tempo-Panel in Chaser- & Sequence-Editor.

Beide Editoren bekommen — wie Matrix/EFX — ein Tempo-Bedienfeld (Tempo-Bus +
Multiplikator + Phasenversatz), damit man pro Funktion zwischen beatgenau
(Bus-Sync) und Free-Run (zeitbasierter Crossfade) waehlen kann. Der Test prueft
das Laden aus der Funktion UND das Zurueckschreiben in die Funktion.

Die erzeugten Editor-Widgets werden im finally deterministisch abgebaut
(deleteLater + processEvents) — sonst sammeln sich C++-QWidgets bis zum GC an,
was unter PySide6/Python 3.14 zusammen mit Hintergrund-Threads Native-Crashes in
spaeteren Tests beguenstigen kann.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from src.core.engine.chaser import Chaser
from src.core.engine.sequence import Sequence


def _app():
    return QApplication.instance() or QApplication([])


def _close(ed):
    """Editor-Widget deterministisch abbauen (kein Leak bis zum GC)."""
    ed.setParent(None)
    ed.deleteLater()
    QApplication.processEvents()


def test_chaser_editor_loads_and_writes_tempo():
    _app()
    from src.ui.views.chaser_editor import ChaserEditor
    ch = Chaser("C")
    ch.tempo_bus_id = "A"
    ch.tempo_multiplier = 2.0
    ch.phase_offset = 0.25

    ed = ChaserEditor(ch)
    try:
        # Laden: Panel spiegelt die Funktionswerte
        assert ed._tempo_bus_combo.currentData() == "A"
        assert abs(ed._tempo_mult_spin.value() - 2.0) < 1e-6
        assert abs(ed._tempo_phase_spin.value() - 0.25) < 1e-6

        # Auf Free-Run umstellen -> schreibt "" in den Chaser (zeitbasierter Crossfade)
        ed._tempo_bus_combo.setCurrentIndex(ed._tempo_bus_combo.findData(""))
        assert ch.tempo_bus_id == ""

        # Multiplikator/Phase zurueckschreiben
        ed._tempo_mult_spin.setValue(0.5)
        ed._tempo_phase_spin.setValue(0.5)
        assert abs(ch.tempo_multiplier - 0.5) < 1e-6
        assert abs(ch.phase_offset - 0.5) < 1e-6
    finally:
        _close(ed)


def test_chaser_editor_default_is_global():
    _app()
    from src.ui.views.chaser_editor import ChaserEditor
    ch = Chaser("C2")            # frisch -> tempo_sync_default => "Global"
    ed = ChaserEditor(ch)
    try:
        assert ed._tempo_bus_combo.currentData() == "Global"
    finally:
        _close(ed)


def test_sequence_editor_loads_and_writes_tempo():
    _app()
    from src.ui.views.sequence_editor import SequenceEditor
    seq = Sequence("S")
    seq.tempo_bus_id = "B"
    seq.tempo_multiplier = 4.0
    seq.phase_offset = 0.1

    ed = SequenceEditor(seq)
    try:
        assert ed._tempo_bus_combo.currentData() == "B"
        assert abs(ed._tempo_mult_spin.value() - 4.0) < 1e-6
        assert abs(ed._tempo_phase_spin.value() - 0.1) < 1e-6

        # Free-Run + neue Werte zurueckschreiben
        ed._tempo_bus_combo.setCurrentIndex(ed._tempo_bus_combo.findData(""))
        assert seq.tempo_bus_id == ""
        ed._tempo_mult_spin.setValue(2.0)
        ed._tempo_phase_spin.setValue(0.75)
        assert abs(seq.tempo_multiplier - 2.0) < 1e-6
        assert abs(seq.phase_offset - 0.75) < 1e-6
    finally:
        _close(ed)


def test_sequence_editor_default_is_global():
    _app()
    from src.ui.views.sequence_editor import SequenceEditor
    seq = Sequence("S2")        # frisch -> tempo_sync_default => "Global"
    ed = SequenceEditor(seq)
    try:
        assert ed._tempo_bus_combo.currentData() == "Global"
    finally:
        _close(ed)
