"""Phase 4: die typisierte ShowBuilder-DSL.

Kern-Garantie: jeder halluzinierte Baustein wirft SOFORT am Aufruf (BuildError),
nicht erst beim stillen Laden; eine echte Show speichert garantiert sauber
(save() validiert statisch + live).
"""
from __future__ import annotations

import pytest


def _db_seeded() -> bool:
    try:
        from src.core.database.fixture_db import get_all_manufacturers
        return bool(get_all_manufacturers())
    except Exception:
        return False


def test_fake_primitives_raise_at_call_time():
    """ACCEPTANCE: jedes fake Primitive → BuildError beim Aufruf."""
    from src.core.show.showbuilder import ShowBuilder, BuildError
    from src.core.engine.rgb_matrix import RgbAlgorithm

    b = ShowBuilder()
    with pytest.raises(BuildError):
        b.matrix("x", algorithm="Schachbret")                       # Tippfehler-Algo
    with pytest.raises(BuildError):
        b.matrix("x", algorithm=RgbAlgorithm.PLAIN, style="Regenbogen")  # fake Style
    with pytest.raises(BuildError):
        b.matrix("x", algorithm=RgbAlgorithm.PLAIN, params={"speeed": 1})  # fake Param
    with pytest.raises(BuildError):
        b.efx("e", algorithm="Kreisel")                             # fake EFX-Algo
    with pytest.raises(BuildError):
        b.button("b", action="Foo")                                 # fake ButtonAction
    with pytest.raises(BuildError):
        b.slider("s", mode="Bar")                                   # fake SliderMode
    with pytest.raises(BuildError):
        b.color("c", target="Gibtsnicht")                           # fake ColorTarget
    with pytest.raises(BuildError):
        b.speed_dial("d", target_mode="Nope")                       # fake SpeedTarget


def test_live_binding_validation_raises():
    """param_key/effect_action_key, die an der gebundenen Funktion nicht existieren,
    werden am Aufruf gefangen (bindungs-bewusst)."""
    from src.core.show.showbuilder import ShowBuilder, BuildError
    from src.core.engine.rgb_matrix import RgbAlgorithm
    from src.ui.virtualconsole.vc_button import ButtonAction

    b = ShowBuilder()
    mx = b.matrix("M", algorithm=RgbAlgorithm.PLAIN, style="RGB")    # PLAIN: kein runner_count
    with pytest.raises(BuildError):
        b.slider("s", mode="EffectParam", param_key="runner_count", function=mx)
    with pytest.raises(BuildError):
        b.button("b", action=ButtonAction.EFFECT_ACTION,
                 effect_action_key="capture_step", function=mx)     # Chaser-Aktion an Matrix


def test_real_build_saves_clean(tmp_path):
    """Eine echte Mini-Show baut + speichert sauber (save() validiert doppelt)."""
    from src.core.show.showbuilder import ShowBuilder
    from src.core.engine.rgb_matrix import RgbAlgorithm
    from src.ui.virtualconsole.vc_button import ButtonAction
    from src.core.capability.validate import validate_lshow, ERROR

    b = ShowBuilder()
    mx = b.matrix("Chase", algorithm=RgbAlgorithm.CHASE, style="RGB",
                  colors=[(255, 0, 0), (0, 0, 255)], params={"runner_count": 2})
    b.button("Go", action=ButtonAction.FUNCTION_TOGGLE, function=mx, bank=0)
    b.slider("Tempo", mode="EffectSpeed", param_key="speed", function=mx, bank=0)
    b.color("Aktiv", target="Effekt (aktive Farbe)", function=mx, bank=0)
    b.speed_dial("Speed", target_mode="Function", function=mx, bank=0)

    out = str(tmp_path / "mini.lshow")
    b.save(out, name="Builder Mini")           # wirft, wenn nicht sauber
    assert not [f for f in validate_lshow(out) if f.severity == ERROR]


def test_patch_unknown_profile_raises():
    from src.core.show.showbuilder import ShowBuilder, BuildError
    b = ShowBuilder()
    with pytest.raises(BuildError):
        b.patch("NICHTEXISTENT_XYZ_999", count=1, channel_count=8)


@pytest.mark.skipif(not _db_seeded(), reason="Fixture-DB nicht geseedet")
def test_patched_show_renders(tmp_path):
    """End-to-End mit echtem Patch: patchen → Matrix → speichern → Render-Smoke."""
    from src.core.show.showbuilder import ShowBuilder, BuildError
    from src.core.engine.rgb_matrix import RgbAlgorithm

    b = ShowBuilder()
    # Davids RGBW-PAR (wie build_demo_show_full); fehlt es, überspringen.
    try:
        fids = b.patch("ZQ01424", count=2, channel_count=8, mode_name="8-Kanal RGBW")
    except BuildError:
        pytest.skip("Profil ZQ01424 nicht in dieser Bibliothek")

    mx = b.matrix("Voll Weiss", algorithm=RgbAlgorithm.PLAIN, style="RGB",
                  fixtures=fids, colors=[(255, 255, 255)])
    out = str(tmp_path / "patched.lshow")
    b.save(out)
    lit, moved, _changed = b.verify_render([mx], channels=range(1, 33))
    assert lit or moved, "gepatchte Matrix erzeugt kein DMX"


@pytest.mark.skipif(not _db_seeded(), reason="Fixture-DB nicht geseedet")
def test_patch_inherits_fixture_type_from_profile():
    """VIZ-BUILDER-FIXTYPE: patch() übernimmt den fixture_type des Profils, sonst
    rendert der 3D-Visualizer Skript-gepatchte Fixtures als PAR-Fallback ('other' ->
    keine DMX->Farbe/Pan/Tilt-Abbildung)."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from src.core.database.fixture_db import engine as fdb_engine
    from src.core.database.models import FixtureProfile
    from src.core.show.showbuilder import ShowBuilder

    # Profil-Typ unabhängig aus der Bibliothek holen (nicht über den Builder-Helfer,
    # damit der Test die Auswirkung prüft, nicht die Implementierung).
    with Session(fdb_engine()) as s:
        profile_type = s.execute(
            select(FixtureProfile.fixture_type)
            .where(FixtureProfile.short_name == "ZQ01424")).scalar_one_or_none()
    if profile_type in (None, "", "other"):
        pytest.skip("ZQ01424 fehlt oder hat keinen spezifischen Typ in dieser Bibliothek")

    b = ShowBuilder()
    fids = b.patch("ZQ01424", count=2, channel_count=8, mode_name="8-Kanal RGBW")
    patched = {pf.fid: pf for pf in b.state.get_patched_fixtures()}
    for fid in fids:
        assert patched[fid].fixture_type == profile_type, (
            f"patch() ließ fixture_type='{patched[fid].fixture_type}' statt "
            f"'{profile_type}' (aus FixtureProfile ZQ01424)")
