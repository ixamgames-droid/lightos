"""UI-89 — Programmer: nur Reiter, die zur Auswahl etwas Bedienbares haben.

Befund (11.10.2026, Bild aus der Laser-Runde): war ein reiner Laser gewaehlt
(Laserworld EL-400RGB MK2 — Betriebsart, Musterauswahl, X/Y, Geschwindigkeiten,
Groesse, Farbe; kein Dimmer, keine Farbmischung), standen in der Reiterleiste
trotzdem „Intensity", „Gobo", „Weitere" und „Matrix". Ursache: die Betriebsart
ist ein ``shutter``-Kanal (zaehlt zu Intensity, der Reiter blieb ohnehin immer
stehen), die Musterauswahl ein ``gobo_wheel`` (Gobo), Geschwindigkeit/Groesse/
Farbe landen in „Weitere", und „Matrix" hing gar nicht an der Auswahl.

Soll: die Reiterliste folgt den Faehigkeiten der Auswahl. Was ein Laser nur
ueber seinen eigenen Reiter bedient, zaehlt nicht fuer die allgemeinen Reiter;
ein Kombi-Geraet (Laser mit Dimmer/RGB) bekommt sie dazu; eine gemischte
Auswahl zeigt die Vereinigung. Der offene Reiter bleibt, solange es ihn gibt.

Echter ProgrammerView, nur eingebaute Profile (QA-23).
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

LASER, PAR, MH, BALKEN, KOMBI, NEBEL = 1, 2, 3, 4, 5, 6

RIG = [  # fid, Kurzname, Modus, Kanaele, Typ
    (LASER, "EL400RGBMK2", None, 9, "laser"),
    (PAR, "PARD", "4-Kanal Dimmer+RGB", 4, "par"),
    (MH, "MH16", "16-Kanal", 16, "moving_head"),
    (BALKEN, "ZQ06121", "154-Kanal 48 Zonen RGB + 8x Weiss", 154, "matrix"),
    # Laser MIT Dimmer, RGB und Strobe (dazu Cue-Auswahl ueber gobo_wheel,
    # Rotation, Makro) = Kombi-Geraet. Eingebautes Profil — ein Geraet aus der
    # nachgeladenen Bibliothek kennt eine frische Installation nicht (QA-61).
    (KOMBI, "PANGFB4", "39-Kanal", 39, "laser"),
    (NEBEL, "EURON10", "2-Kanal (Nebel + Lüfter)", 2, "hazer"),
]


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _isolate_prefs(tmp_path, monkeypatch):
    import src.ui.views.programmer_view as pv
    monkeypatch.setattr(pv, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(pv, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))


def _reiter(pv) -> list[str]:
    t = pv._main_tabs
    return [t.tabText(i) for i in range(t.count()) if t.isTabVisible(i)]


def _offen(pv) -> str:
    t = pv._main_tabs
    return t.tabText(t.currentIndex())


def _oeffne(pv, name: str):
    t = pv._main_tabs
    idx = next(i for i in range(t.count()) if t.tabText(i) == name)
    assert t.isTabVisible(idx), f"Reiter {name} ist nicht sichtbar"
    t.setCurrentIndex(idx)


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
    st = get_state()
    adr = 1
    with Session(fdb_engine()) as s:
        for fid, kurz, modus, n, typ in RIG:
            prof = s.execute(select(FixtureProfile).where(
                FixtureProfile.short_name == kurz)).scalars().first()
            assert prof is not None, f"Profil {kurz} fehlt"
            if modus is None:
                modus = prof.modes[0].name
            st.add_fixture(PatchedFixture(
                fid=fid, label=kurz, fixture_profile_id=int(prof.id),
                mode_name=modus, universe=1, address=adr, channel_count=n,
                fixture_type=typ), undoable=False)
            adr += n
    pv = ProgrammerView()
    pv.resize(1400, 900)
    pv.show()
    pv._refresh_fixture_list()
    app.processEvents()

    def waehle(*fids):
        st.set_selected_fids(list(fids))
        app.processEvents()
        return _reiter(pv)

    yield pv, waehle
    pv.close()
    pv.deleteLater()
    app.processEvents()
    reset_show()


# ── (1) reiner Laser ────────────────────────────────────────────────────────

def test_reiner_laser_zeigt_nur_seine_reiter(ansicht):
    pv, waehle = ansicht
    assert waehle(LASER) == ["Assistent", "EFX", "Laser", "Paletten"]


def test_reiner_laser_oeffnet_den_laser_reiter(ansicht):
    pv, waehle = ansicht
    waehle(LASER)
    assert _offen(pv) == "Laser"


def test_laser_reiter_traegt_alles_was_ausgeblendet_wurde(ansicht):
    """Kein Kanal des Lasers darf mit den Reitern verschwinden."""
    from src.core.app_state import get_channels_for_patched
    pv, waehle = ansicht
    waehle(LASER)
    fx = next(f for f in pv._state.get_patched_fixtures() if f.fid == LASER)
    attrs = {ch.attribute for ch in get_channels_for_patched(fx)}
    lv = pv._embedded_laser
    # LAS-34: Regler-Zeilen, Bausteine (Umschalter, Galerie, Farbfelder,
    # Lage, Regler) und die Betriebsart-Kacheln zusammen.
    bedienbar = lv.bedienbare_attribute()
    assert attrs <= bedienbar, sorted(attrs - bedienbar)


# ── (2) Kombi-Geraet ────────────────────────────────────────────────────────

def test_kombi_laser_bekommt_die_passenden_reiter_dazu(ansicht):
    pv, waehle = ansicht
    s = waehle(KOMBI)
    assert {"Intensity", "Color", "Matrix", "Laser", "Paletten"} <= set(s), s
    # Musterauswahl/Rotation des Lasers sind kein Gobo-Rad.
    assert "Gobo" not in s, s
    assert "Position" not in s, s


def test_nur_laser_eigene_attribute_zaehlen_nicht():
    from src.ui.views.laser_view import nur_im_laser_reiter
    for attr in ("shutter", "gobo_wheel", "gobo_rotation", "zoom", "speed",
                 "effect_speed", "laser_x", "laser_color"):
        assert nur_im_laser_reiter(attr), attr
    # Dimmer/RGB/Strobe machen den Laser zum Kombi-Geraet; ein zweites
    # Gobo-Rad, Pan/Tilt, Fokus kennt der Laser-Reiter gar nicht.
    for attr in ("intensity", "color_r", "color_g", "color_b", "strobe",
                 "gobo_wheel2", "pan", "tilt", "focus", "color_w", "raw"):
        assert not nur_im_laser_reiter(attr), attr


# ── (3) gemischte Auswahl ───────────────────────────────────────────────────

def test_laser_und_moving_head_zeigen_die_vereinigung(ansicht):
    pv, waehle = ansicht
    nur_mh = waehle(MH)
    beide = waehle(LASER, MH)
    assert beide == [r for r in _alle_reiter(pv)
                     if r in set(nur_mh) | {"Laser"}], beide
    # Im Laser-Reiter stehen weiterhin nur die Laser (er liest die Auswahl
    # erst, wenn er offen ist).
    _oeffne(pv, "Laser")
    _app().processEvents()
    assert [f.fid for f in pv._embedded_laser._fixtures] == [LASER]


def _alle_reiter(pv) -> list[str]:
    t = pv._main_tabs
    return [t.tabText(i) for i in range(t.count())]


# ── (4) Regression: andere Geraete, leere Auswahl ───────────────────────────

def test_ohne_auswahl_unveraendert(ansicht):
    pv, waehle = ansicht
    erwartet = ["Intensity", "Color", "Weitere", "Assistent", "Matrix",
                "Paletten"]
    assert _reiter(pv) == erwartet
    waehle(LASER)
    assert waehle() == erwartet


def test_par_unveraendert(ansicht):
    pv, waehle = ansicht
    assert waehle(PAR) == ["Intensity", "Color", "Assistent", "Matrix",
                           "Paletten"]


def test_moving_head_unveraendert(ansicht):
    pv, waehle = ansicht
    assert waehle(MH) == ["Intensity", "Color", "Position", "Gobo", "Weitere",
                          "Mapping", "Assistent", "EFX", "Matrix", "Paletten"]


def test_matrix_geraet_unveraendert(ansicht):
    pv, waehle = ansicht
    assert waehle(BALKEN) == ["Intensity", "Color", "Assistent", "Matrix",
                              "Paletten"]


def test_nebelmaschine_unveraendert(ansicht):
    pv, waehle = ansicht
    assert waehle(NEBEL) == ["Intensity", "Weitere", "Assistent", "Matrix",
                             "Paletten"]


# ── (5) offener Reiter, kein Flackern ───────────────────────────────────────

def test_offener_reiter_bleibt_solange_es_ihn_gibt(ansicht):
    pv, waehle = ansicht
    waehle(MH)
    _oeffne(pv, "Position")
    waehle(MH, LASER)
    assert _offen(pv) == "Position"
    waehle(LASER)                       # Position gibt es nicht mehr
    assert _offen(pv) == "Laser"
    _oeffne(pv, "EFX")
    waehle(MH)                          # EFX gibt es auch beim Moving Head
    assert _offen(pv) == "EFX"
    waehle(PAR)                         # kein EFX -> erster Attribut-Reiter
    assert _offen(pv) == "Intensity"


def test_laser_abwaehlen_springt_auf_den_ersten_reiter(ansicht):
    pv, waehle = ansicht
    waehle(LASER)
    assert _offen(pv) == "Laser"
    waehle()
    assert _offen(pv) == "Intensity"


def test_fokus_folgt_dem_sichtbaren_reiter(ansicht):
    """ENG-02: der gemeldete Programmer-Fokus passt zum offenen Reiter."""
    pv, waehle = ansicht
    gemeldet = []
    pv._main_tabs.currentChanged.connect(
        lambda i: gemeldet.append(pv._main_tabs.tabText(i)))
    waehle(LASER)
    assert gemeldet == ["Laser"], gemeldet     # ein Wechsel, kein Zwischenhalt
    assert pv._state.programmer_focus == "Laser"


def test_gleiche_auswahl_baut_die_leiste_nicht_um(ansicht, monkeypatch):
    pv, waehle = ansicht
    waehle(LASER)
    rufe, wechsel = [], []
    echt = pv._main_tabs.setTabVisible
    monkeypatch.setattr(pv._main_tabs, "setTabVisible",
                        lambda i, v: (rufe.append((i, v)), echt(i, v))[1])
    pv._main_tabs.currentChanged.connect(wechsel.append)
    pv._rebuild_attr_editor()
    pv._rebuild_attr_editor()
    assert rufe == [] and wechsel == []
    assert _reiter(pv) == ["Assistent", "EFX", "Laser", "Paletten"]


def test_gruppenklick_springt_nicht_auf_ausgeblendete_matrix(ansicht):
    """F-1 oeffnet nach einem Gruppenklick die Matrix — nur wenn es sie gibt."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QListWidgetItem
    pv, waehle = ansicht
    item = QListWidgetItem("Laser-Gruppe")
    item.setData(Qt.ItemDataRole.UserRole, [LASER])
    pv._on_group_clicked(item)
    _app().processEvents()
    assert _reiter(pv) == ["Assistent", "EFX", "Laser", "Paletten"]
    assert _offen(pv) == "Laser"
    item.setData(Qt.ItemDataRole.UserRole, [PAR])
    pv._on_group_clicked(item)
    _app().processEvents()
    assert _offen(pv) == "Matrix"


# ── Laser-Reiter: Betriebsart ohne Wertebereiche bleibt bedienbar ───────────

class _Ch:
    def __init__(self, attr, num, ranges=None):
        self.attribute = attr
        self.channel_number = num
        self.ranges = ranges or []
        self.name = attr


def test_shutter_ohne_bereiche_bekommt_einen_regler():
    """Ohne Wertebereiche gibt es keine Betriebsart-Kacheln — dann braucht
    der Kanal eine Regler-Zeile, sonst waere er nirgends mehr erreichbar."""
    import src.ui.views.laser_view as lv
    _app()
    view = lv.LaserView(follow_selection=False)
    try:
        view._rebuild_rows([_Ch("shutter", 1), _Ch("laser_x", 2)])
        assert "shutter" in view._rows
    finally:
        view.deleteLater()
