"""TargetListEditor: aufklappbare „Steuert"-Liste — IDs + je-ID-Parameter, add/remove."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from src.ui.virtualconsole.target_list_editor import TargetListEditor


def test_set_get_ids_and_params():
    ed = TargetListEditor(with_params=True)
    ed.set_targets([5, 9], {5: "speed"})
    assert ed.ids() == [5, 9]
    # 9 hat keinen Parameter -> faellt aus param_keys raus; 5 behaelt 'speed'
    assert ed.param_keys() == {5: "speed"}


def test_remove_row_drops_target():
    ed = TargetListEditor(with_params=False)
    ed.set_targets([1, 2, 3])
    assert ed.ids() == [1, 2, 3]
    ed._remove_row(ed._rows[1])     # die "2" entfernen
    assert ed.ids() == [1, 3]


def test_add_empty_row_is_ignored_until_chosen():
    ed = TargetListEditor(with_params=False)
    ed.set_targets([4])
    ed._add_row(None, "")           # leere Zeile -> zaehlt nicht
    assert ed.ids() == [4]


def test_collapse_toggle_hides_body():
    ed = TargetListEditor()
    ed.set_targets([1])
    assert ed._body.isVisibleTo(ed)
    ed._toggle.setChecked(False)
    assert not ed._body.isVisibleTo(ed)


def test_string_param_keys_accepted():
    # from_dict liefert Parameter-Keys teils als String-IDs -> muessen greifen
    ed = TargetListEditor(with_params=True)
    ed.set_targets([7], {"7": "tempo_multiplier"})
    assert ed.param_keys() == {7: "tempo_multiplier"}


def test_set_targets_dedups_duplicate_ids():
    # Duplikate beim Befuellen werden uebersprungen -> keine doppelten Zeilen,
    # kein stiller Parameter-Verlust bei param_keys().
    ed = TargetListEditor(with_params=True)
    ed.set_targets([5, 5, 9], {5: "speed"})
    assert ed.ids() == [5, 9]
    assert ed.param_keys() == {5: "speed"}


def test_duplicate_selection_resets_row():
    # Waehlt eine Zeile einen Effekt, der schon in einer anderen Zeile steckt,
    # wird sie auf „(leer)" zurueckgesetzt (statt stillem Datenverlust).
    ed = TargetListEditor(with_params=False)
    ed._add_row(5, "")
    r2 = ed._add_row(5, "")
    ed._on_func_changed(r2)
    assert ed._row_fid(r2) is None
    assert ed.ids() == [5]
