"""EA-01: Gruppen-Auswahl im Effekt-Assistenten — ein Gruppen-Klick kreuzt die
Mitglieder zusätzlich an (Union), selected_fids() bleibt die einzige Quelle."""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

import src.core.app_state as app_state
from src.ui.widgets.effect_wizard import _FixturePage

_app = QApplication.instance() or QApplication([])


class _FakeSession:
    def __init__(self, groups):
        self._g = groups

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, _stmt):
        return SimpleNamespace(scalars=lambda: list(self._g))


def _fx(fid):
    return SimpleNamespace(label=f"F{fid}", fid=fid, universe=1, address=fid)


class EAGroupSelectionTest(unittest.TestCase):
    def setUp(self):
        self._orig = app_state.get_state
        groups = [SimpleNamespace(name="GrpA"), SimpleNamespace(name="Leer")]
        self.fake = SimpleNamespace(
            get_patched_fixtures=lambda: [_fx(1), _fx(2), _fx(3)],
            get_selected_fids=lambda: [],
            group_fids_by_name=lambda n: {"GrpA": [1, 3]}.get(n, []),
            _session=lambda: _FakeSession(groups),
        )
        app_state.get_state = lambda: self.fake

    def tearDown(self):
        app_state.get_state = self._orig

    def test_default_all_selected(self):
        page = _FixturePage()
        self.assertEqual(sorted(page.selected_fids()), [1, 2, 3])

    def test_select_group_is_union(self):
        page = _FixturePage()
        page._set_all(False)
        self.assertEqual(page.selected_fids(), [])
        page._select_group([1, 3])
        self.assertEqual(sorted(page.selected_fids()), [1, 3])

    def test_select_group_keeps_existing_ticks(self):
        page = _FixturePage()
        page._set_all(False)
        for cb in page.checks:
            if cb.fid == 2:
                cb.setChecked(True)
        page._select_group([1, 3])
        self.assertEqual(sorted(page.selected_fids()), [1, 2, 3])

    def test_group_button_created_and_clicks(self):
        page = _FixturePage()
        page._set_all(False)
        btns = [b for b in page.findChildren(QPushButton) if "GrpA" in b.text()]
        self.assertEqual(len(btns), 1)          # nur GrpA (leere Gruppe gefiltert)
        self.assertIn("(2)", btns[0].text())
        btns[0].click()
        self.assertEqual(sorted(page.selected_fids()), [1, 3])

    def test_empty_group_not_shown(self):
        page = _FixturePage()
        btns = [b for b in page.findChildren(QPushButton) if "Leer" in b.text()]
        self.assertEqual(btns, [])

    def test_unpatched_group_fid_ignored(self):
        page = _FixturePage()
        page._set_all(False)
        page._select_group([1, 99])             # 99 ist nicht gepatcht
        self.assertEqual(sorted(page.selected_fids()), [1])

    def test_duplicate_group_names_deduplicated(self):
        dup = [SimpleNamespace(name="Dup"), SimpleNamespace(name="Dup")]
        self.fake._session = lambda: _FakeSession(dup)
        self.fake.group_fids_by_name = lambda n: [1, 2] if n == "Dup" else []
        page = _FixturePage()
        btns = [b for b in page.findChildren(QPushButton) if "Dup" in b.text()]
        self.assertEqual(len(btns), 1)          # dedupliziert -> nur ein Button


if __name__ == "__main__":
    unittest.main()
