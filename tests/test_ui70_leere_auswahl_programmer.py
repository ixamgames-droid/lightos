"""UI-70 — Programmer: leere Auswahl stellt den Grundzustand her.

Befund aus der Bilder-Auffrisch-Runde (DOC-22): wurde die Geraeteauswahl
geleert (auch ein zweites Mal, als schon nichts mehr gewaehlt war), blieb die
Einzelgeraete-Combo neben „Verknüpft / Einzeln / Relativ" mit dem zuletzt
gewaehlten Geraet („[1] PARD") stehen. Im Einzelmodus zielte sie damit auf ein
Geraet, das gar nicht mehr gewaehlt war. Ebenso blieb ein Faehigkeits-Reiter
der alten Auswahl (Laser) offen.

Soll: leere Auswahl = Combo leer und aus, Reiter wie bei einem frisch
geoeffneten Programmer ohne Auswahl. Echter ProgrammerView, eingebautes
Generic-Profil ``PARD`` (wie die Doku-Demo-Show).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _isolate_prefs(tmp_path, monkeypatch):
    import src.ui.views.programmer_view as pv
    monkeypatch.setattr(pv, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(pv, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))


def _sichtbare_reiter(pv) -> list[str]:
    t = pv._main_tabs
    return [t.tabText(i) for i in range(t.count()) if t.isTabVisible(i)]


def _combo(pv) -> list[str]:
    c = pv._fixture_combo
    return [c.itemText(i) for i in range(c.count())]


@pytest.fixture
def ansicht(tmp_path, monkeypatch):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from src.core.app_state import get_state
    from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
    from src.core.database.models import FixtureProfile, PatchedFixture
    from src.core.show.show_file import reset_show
    from src.ui.views.programmer_view import ProgrammerView

    app = _app()
    _isolate_prefs(tmp_path, monkeypatch)
    ensure_builtins()
    reset_show()
    with Session(fdb_engine()) as s:
        pid = int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == "PARD")).scalars().first())
    st = get_state()
    st.add_fixture(PatchedFixture(
        fid=1, label="PARD", fixture_profile_id=pid,
        mode_name="4-Kanal Dimmer+RGB", universe=1, address=1,
        channel_count=4, fixture_type="par"), undoable=False)
    pv = ProgrammerView()
    pv.resize(1400, 900)
    pv.show()
    pv._refresh_fixture_list()
    app.processEvents()
    yield app, pv, st
    pv.close()
    pv.deleteLater()
    app.processEvents()
    reset_show()


def _leeren_ueber(weg, pv, st):
    if weg == "liste":
        pv._fixture_list.clearSelection()     # Klick ins Leere / „Keine"
    else:
        st.set_selected_fids([])              # andere Ansicht leert die Auswahl


@pytest.mark.parametrize("weg", ["liste", "zustand"])
@pytest.mark.parametrize("modus", ["linked", "individual"])
def test_leeren_setzt_combo_und_reiter_zurueck(ansicht, weg, modus):
    app, pv, st = ansicht
    pv._set_group_mode(modus)
    app.processEvents()
    grund_reiter = _sichtbare_reiter(pv)
    assert _combo(pv) == [] and not pv._fixture_combo.isEnabled()

    pv._select_fids([1])
    app.processEvents()
    assert _combo(pv) == ["[1] PARD"]
    assert pv._fixture_combo.isEnabled() is (modus == "individual")

    for durchgang in (1, 2):                  # zweites Leeren: war schon leer
        _leeren_ueber(weg, pv, st)
        app.processEvents()
        assert pv._editor_fids == []
        assert _combo(pv) == [], (
            f"Durchgang {durchgang}: Einzelgeraete-Combo zeigt noch {_combo(pv)}")
        assert pv._fixture_combo.currentIndex() == -1
        assert not pv._fixture_combo.isEnabled()
        assert pv.active_fixture_fid() is None   # zielt auf kein altes Geraet
        assert _sichtbare_reiter(pv) == grund_reiter
        assert "Weitere" in _sichtbare_reiter(pv)


def test_laser_reiter_geht_beim_leeren_wieder_zu(ansicht, monkeypatch):
    """Faehigkeits-Reiter der alten Auswahl (hier Laser) bleiben nicht offen."""
    app, pv, st = ansicht
    import src.ui.views.laser_view as lv
    grund_reiter = _sichtbare_reiter(pv)
    assert "Laser" not in grund_reiter
    monkeypatch.setattr(lv, "fixture_has_laser_capability", lambda f: True)
    pv._select_fids([1])
    app.processEvents()
    assert "Laser" in _sichtbare_reiter(pv)
    pv._fixture_list.clearSelection()
    app.processEvents()
    assert _sichtbare_reiter(pv) == grund_reiter
