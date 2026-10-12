"""ENG-36: die kleine Show, an der die Klon-Tests arbeiten.

Echter ``AppState`` mit eigener Show-DB, eigene Snap-Bibliothek, eigener
Paletten- und Funktions-Verwalter — nichts davon ist ein Singleton der App,
und nichts stammt aus einer echten Show. Nur die Kanal-Auflösung ist ersetzt
(sechs kleine Gerätetypen).
"""
from __future__ import annotations

import json
from types import SimpleNamespace as NS

import src.core.app_state as A
from sqlalchemy.orm import Session
from src.core.database.models import FixtureGroup, PatchedFixture
from src.core.engine.function_manager import FunctionManager
from src.core.engine.palette import PaletteManager
from src.core.engine.snap_library import SnapLibrary
from src.core.show import klonen as K
from src.core.undo import get_undo_stack

RGB, RGBW, CMY, DIM, RAD, RGB_OHNE_DIMMER = 1, 2, 3, 4, 5, 6


def kanal(nr, attr, ranges=()):
    return NS(channel_number=nr, attribute=attr, default_value=0, name=attr,
              ranges=[NS(range_from=a, range_to=b, name=n, kind=k)
                      for a, b, n, k in ranges])


_TYPEN = {
    RGB: ["intensity", "color_r", "color_g", "color_b"],
    RGBW: ["dimmer", "color_r", "color_g", "color_b", "color_w"],
    CMY: ["intensity", "cmy_c", "cmy_m", "cmy_y", "pan", "tilt"],
    DIM: ["intensity"],
    RAD: ["intensity", "color_wheel", "pan", "tilt"],
    RGB_OHNE_DIMMER: ["color_r", "color_g", "color_b"],
}
_RAD_PLAETZE = ((0, 9, "Weiß / Offen", "open"), (10, 19, "Rot", "color"),
                (20, 29, "Blau", "color"), (30, 39, "Gobo-Wechsel", "rotate"))


def _kanaele(fx):
    attrs = _TYPEN[fx.fixture_profile_id]
    return [kanal(i + 1, a, _RAD_PLAETZE if a == "color_wheel" else ())
            for i, a in enumerate(attrs)]


class Show:
    """Eine kleine Show im Speicher."""

    def __init__(self, tmp_path):
        self.state = A.AppState()
        self.state.open_show(str(tmp_path / "show.db"))
        self.state.function_manager = FunctionManager()
        self.snaps = SnapLibrary()
        self.paletten = PaletteManager()
        self._adresse = 1

    def patch(self, fid, typ, label=None):
        n = len(_TYPEN[typ])
        self.state.add_fixture(PatchedFixture(
            fid=fid, label=label or f"L{fid}", fixture_profile_id=typ,
            mode_name="Standard", universe=1, address=self._adresse,
            channel_count=n, fixture_type="par"), undoable=False)
        self._adresse += n

    def gruppe(self, name, zellen, cols=4, rows=1):
        with Session(self.state._show_engine) as s:
            g = FixtureGroup(name=name, cols=cols, rows=rows,
                             positions_json=json.dumps(zellen))
            s.add(g)
            s.commit()
            return g.id

    def gruppe_lesen(self, gid):
        with Session(self.state._show_engine) as s:
            g = s.get(FixtureGroup, gid)
            return g.cols, g.rows, json.loads(g.positions_json)

    def plane(self, quellen, ziele, wie=K.HINZUFUEGEN, bereiche=None,
              position=K.POS_ENDE):
        opt = K.Optionen(wie=wie, position=position,
                         bereiche=frozenset(bereiche or K.BEREICHE))
        return K.plane(self.state, quellen, ziele, opt,
                       snap_library=self.snaps, palette_manager=self.paletten)


def show_fixture(tmp_path, monkeypatch):
    """Rumpf der ``show``-Fixture (als Generator, für ``yield from``)."""
    monkeypatch.setattr(A, "get_channels_for_patched", _kanaele)
    stack = get_undo_stack()
    stack.clear()
    sh = Show(tmp_path)
    yield sh
    stack.clear()
    try:
        sh.state._show_engine.dispose()
    except Exception:
        pass
