"""Welle 3 / Cluster F: Chaser Inline-Funktions-Picker.

Im ChaserEditor unten: ganze Liste verfuegbarer Funktionen (ohne den Chaser
selbst), Mehrfachauswahl -> direkt als Schritte ans Ende. (Der <2-Snaps-Fall in
snap_file_panel legt dafuer einen leeren Chaser an + oeffnet diesen Editor.)
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt


def _app():
    return QApplication.instance() or QApplication([])


def test_chaser_inline_picker_adds_steps():
    _app()
    from src.core.engine.function_manager import get_function_manager
    from src.ui.views.chaser_editor import ChaserEditor
    fm = get_function_manager()
    chaser = fm.new_chaser("C")
    s1 = fm.new_scene("Scene A")
    s2 = fm.new_scene("Scene B")

    ed = ChaserEditor(chaser)
    assert chaser.steps == []   # frisch leer

    # Picker enthaelt s1+s2, aber NICHT den Chaser selbst (Selbstreferenz-Schutz)
    ids = {ed._add_list.item(i).data(Qt.ItemDataRole.UserRole)
           for i in range(ed._add_list.count())}
    assert {s1.id, s2.id} <= ids
    assert chaser.id not in ids

    def _item(fid):
        for i in range(ed._add_list.count()):
            it = ed._add_list.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == fid:
                return it
        raise AssertionError(f"fid {fid} nicht in der Picker-Liste")

    # Doppelklick-Pfad: einen hinzufuegen
    ed._add_from_picker_item(_item(s1.id))
    assert [st.function_id for st in chaser.steps] == [s1.id]

    # Mehrfachauswahl-Pfad: zweiten markieren + uebernehmen
    _item(s2.id).setSelected(True)
    ed._add_selected_from_picker()
    assert len(chaser.steps) == 2
    assert s2.id in [st.function_id for st in chaser.steps]


def test_new_empty_chaser_creates_a_real_chaser():
    """★★ QA-52: Dieser Test prueste nur ``hasattr(SnapFilePanel,
    "_new_empty_chaser")``.

    Damit war er gruen, solange der Name existiert — auch bei einem leeren
    Rumpf, einem sofortigen ``return`` oder einem Editor, der gar nicht
    aufgeht. Der Dialogaufbau dahinter lief in **keinem** Test (dieselbe Falle
    wie beim PatchFixtureEditDialog). Jetzt wird der Helfer wirklich gerufen
    und geprueft, dass ein leerer Chaser entsteht.
    """
    import types
    from unittest import mock
    from src.core.engine.function_manager import get_function_manager
    from src.ui.views.snap_file_panel import SnapFilePanel

    fm = get_function_manager()
    vorher = {f.id for f in fm.all()}

    # Ein ECHTES QWidget: der Helfer baut `QDialog(self)` und haengt den Editor
    # hinein — die Lebensdauer-Kopplung an das Panel ist Teil des Vertrags.
    from PySide6.QtWidgets import QWidget, QDialog, QLabel
    _app()

    class _PanelStub(QWidget):
        pass

    stub = _PanelStub()
    stub._target_folder = lambda: None
    stub._refresh_tree = lambda: None
    geoeffnet = []

    def _editor(ch):
        geoeffnet.append(ch)
        return QLabel("Editor-Attrappe")     # ein echtes Widget fuer das Layout

    # `dlg.exec()` blockiert bis zum Schliessen — der Aufbau davor ist echt.
    with mock.patch("src.ui.views.function_manager_view.create_function_editor",
                    _editor), \
         mock.patch.object(QDialog, "exec", lambda self: 0):
        SnapFilePanel._new_empty_chaser(stub)

    neue = [f for f in fm.all() if f.id not in vorher]
    try:
        assert len(neue) == 1, f"erwartet genau einen neuen Chaser, wurde: {neue}"
        chaser = neue[0]
        assert not chaser.steps, "ein NEUER Chase faengt leer an"
        assert geoeffnet == [chaser], "der Editor muss genau diesen Chase oeffnen"
    finally:
        for f in neue:
            fm.remove(f.id)
