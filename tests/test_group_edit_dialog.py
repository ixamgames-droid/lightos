"""Tests für den „Gruppe bearbeiten"-Dialog (group_edit_dialog.py).

Geprüft wird die Kernlogik (Reihenfolge, Zellen-Erhalt, Umsortierung,
Raster-Wachstum) — der Dialog läuft offscreen (QT_QPA_PLATFORM=offscreen,
gesetzt in conftest.py).
"""
import json

import pytest
from PySide6.QtWidgets import QApplication

from src.ui.widgets.group_edit_dialog import GroupEditDialog, group_member_fids


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


LABELS = {1: "MH 1", 2: "MH 2", 3: "PAR 1", 4: "PAR 2", 5: "PAR 3"}
# 2x2-Raster: (0,0)=1, (1,0)=2, (0,1)=3 → Reihenfolge 1, 2, 3
POS = json.dumps({"0,0": 1, "1,0": 2, "0,1": 3})


def make_dialog(positions=POS, cols=2, rows=2, labels=None):
    return GroupEditDialog("Testgruppe", positions, cols, rows,
                           labels or LABELS)


class TestGroupMemberFids:
    def test_row_major_order(self):
        assert group_member_fids(POS) == [1, 2, 3]

    def test_invalid_json(self):
        assert group_member_fids("kaputt") == []

    def test_empty(self):
        assert group_member_fids("") == []


class TestGroupEditDialog:
    def test_initial_members_and_available(self):
        dlg = make_dialog()
        assert dlg.member_fids() == [1, 2, 3]
        avail = [dlg._avail_list.item(i).data(0x0100)  # Qt.UserRole
                 for i in range(dlg._avail_list.count())]
        assert sorted(avail) == [4, 5]

    def test_remove_keeps_other_cells(self):
        dlg = make_dialog()
        dlg._member_list.setCurrentRow(1)  # fid 2 entfernen
        dlg._remove_member()
        assert dlg.member_fids() == [1, 3]
        pos_json, cols, rows = dlg.result_positions()
        pos = json.loads(pos_json)
        assert pos == {"0,0": 1, "0,1": 3}  # Zellen unverändert
        assert (cols, rows) == (2, 2)

    def test_add_uses_first_free_cell(self):
        dlg = make_dialog()
        # fid 4 hinzufügen
        for i in range(dlg._avail_list.count()):
            if dlg._avail_list.item(i).data(0x0100) == 4:
                dlg._avail_list.setCurrentRow(i)
                break
        dlg._add_member()
        assert dlg.member_fids() == [1, 2, 3, 4]
        pos = json.loads(dlg.result_positions()[0])
        assert pos["1,1"] == 4  # erste freie Zelle (zeilenweise)
        # bestehende Zellen bleiben erhalten
        assert pos["0,0"] == 1 and pos["1,0"] == 2 and pos["0,1"] == 3

    def test_reorder_rewrites_row_major(self):
        dlg = make_dialog()
        dlg._member_list.setCurrentRow(2)  # fid 3 nach oben
        dlg._move_member(-1)
        dlg._move_member(-1)
        assert dlg.member_fids() == [3, 1, 2]
        pos = json.loads(dlg.result_positions()[0])
        assert pos == {"0,0": 3, "1,0": 1, "0,1": 2}

    def test_grid_grows_when_needed(self):
        # 1x1-Raster mit 1 Mitglied, dann 2 weitere hinzufügen → rows wächst
        dlg = make_dialog(positions=json.dumps({"0,0": 1}), cols=1, rows=1)
        while dlg._avail_list.count():
            dlg._avail_list.setCurrentRow(0)
            dlg._add_member()
        assert len(dlg.member_fids()) == 5
        pos_json, cols, rows = dlg.result_positions()
        assert cols == 1 and rows >= 5
        assert len(json.loads(pos_json)) == 5

    def test_no_duplicate_members(self):
        dlg = make_dialog()
        fids = dlg.member_fids()
        assert len(fids) == len(set(fids))
        # verfügbare Liste enthält keine Mitglieder
        avail = {dlg._avail_list.item(i).data(0x0100)
                 for i in range(dlg._avail_list.count())}
        assert not (set(fids) & avail)

    def test_unpatched_member_dropped(self):
        # fid 99 ist nicht (mehr) gepatcht → fliegt beim Laden raus
        pos = json.dumps({"0,0": 1, "1,0": 99})
        dlg = make_dialog(positions=pos)
        assert dlg.member_fids() == [1]

    def test_result_name_stripped(self):
        dlg = make_dialog()
        dlg._name_edit.setText("  Neuer Name  ")
        assert dlg.result_name() == "Neuer Name"
