"""CDX-62: Codex-Befunde zu #1166 (ENG-32), #1181 (ENG-33) und #1200 (ENG-41).

* Speed-Dial (TEMPO_BUS_MULT, Free-Run): eine Faktor-Runde ueber die
  speed-Grenze eines Effekts darf die Grundgeschwindigkeit nicht verlieren.
* Follow-Nachholen: der rueckdatierte Folge-Fade startet vom Stand des alten
  Fades ZUR FAELLIGKEIT, nicht vom jetzigen — sonst haengt die Ausgabe an
  ausgelassenen Bildern.
* Ueberschneidungs-Hinweis: „Andere Effekte auf denselben Geräten stoppen“
  unterdrueckt den Hinweis nur, wenn die Laufzeit die geteilten Geraete auch
  sieht (eine Show wird ueber ihre Spuren gerechnet, vom Stopp aber nicht).
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
import pytest

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def fm():
    from src.core.engine.function_manager import get_function_manager
    manager = get_function_manager()
    manager.stop_all()
    vorher = {f.id for f in manager.all()}
    yield manager
    manager.stop_all()
    for f in list(manager.all()):
        if f.id not in vorher:
            manager.remove(f.id)


# ── #1166: Speed-Basis ueber geklemmte Faktorwechsel ────────────────────────

def _dial(fids, factors, active):
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
    d = VCSpeedDial("x")
    d.target_mode = SpeedTarget.TEMPO_BUS_MULT
    d.function_ids = list(fids)
    d.factor_buttons = list(factors)
    d._active_factor = d._mult = float(active)
    return d


def test_faktor_runde_ueber_speed_grenze_behaelt_grundtempo(fm):
    e = fm.new_efx("Kreis")
    e.tempo_bus_id = ""                      # Free-Run
    e.tempo_multiplier = 1.0
    e.speed_hz = 5.0
    d = _dial([e.id], [1.0, 4.0], 1.0)
    d._set_factor(4.0)                       # 20 Hz -> an der EFX-Grenze 10 Hz
    assert abs(e.speed_hz - 10.0) < 1e-9
    d._set_factor(1.0)
    assert abs(e.speed_hz - 5.0) < 1e-6, f"Grundtempo verloren: {e.speed_hz}"
    for _ in range(3):                       # wiederholt: kein schleichender Verlust
        d._set_factor(4.0)
        d._set_factor(1.0)
    assert abs(e.speed_hz - 5.0) < 1e-6, f"Grundtempo verloren: {e.speed_hz}"


def test_aussen_geaenderter_speed_wird_neue_basis(fm):
    e = fm.new_efx("Kreis2")
    e.tempo_bus_id = ""
    e.tempo_multiplier = 1.0
    e.speed_hz = 2.0
    d = _dial([e.id], [1.0, 2.0], 1.0)
    d._set_factor(2.0)
    assert abs(e.speed_hz - 4.0) < 1e-9
    e.speed_hz = 3.0                         # Nutzer stellt am Effekt um
    d._set_factor(1.0)
    assert abs(e.speed_hz - 1.5) < 1e-6


# ── #1181: Folge-Fade startet vom Stand zur Faelligkeit ─────────────────────

def _follow_stack():
    from src.core.engine.cue import Cue
    from src.core.engine.cue_stack import CueStack
    s = CueStack("CDX-62")
    c1 = Cue(1.0, "Eins", values={1: {"intensity": 200}}, fade_in=1.0)
    c1.fade_curve = "linear"
    c1.delay_in = 1.0
    c1.follow = 0.0
    c2 = Cue(2.0, "Zwei", values={1: {"intensity": 0}}, fade_in=2.0)
    c2.fade_curve = "linear"
    s.cues = [c1, c2]
    return s


@pytest.mark.parametrize("ticks", [[1.0, 1.5], [1.5]],
                         ids=["jedes_bild", "bild_ausgelassen"])
def test_follow_mit_delay_haengt_nicht_an_ausgelassenen_bildern(ticks):
    from src.core.engine import show_zeit
    with show_zeit.manuelle_uhr() as uhr:
        s = _follow_stack()
        s.go()
        jetzt = 0.0
        out = None
        for t in ticks:
            uhr.vorruecken(t - jetzt)
            jetzt = t
            out = s.tick()
        assert s.current_index == 1
        # Faellig bei 1.0 s (follow 0 + fade 1, ohne Delay): Cue 1 steht dort
        # noch auf 0 -> der Folge-Fade (0 -> 0) liefert 0, egal wie getaktet.
        assert out[1]["intensity"] == 0, out
        s.stop()


def test_follow_mit_attribut_delay_nimmt_stand_zur_faelligkeit():
    from src.core.engine import show_zeit
    from src.core.engine.cue import Cue
    from src.core.engine.cue_stack import CueStack
    with show_zeit.manuelle_uhr() as uhr:
        s = CueStack("CDX-62b")
        c1 = Cue(1.0, "Eins", values={1: {"intensity": 200}}, fade_in=1.0)
        c1.fade_curve = "linear"
        c1.attr_delays = {1: {"intensity": 1.0}}
        c1.follow = 0.0
        c2 = Cue(2.0, "Zwei", values={1: {"intensity": 0}}, fade_in=2.0)
        c2.fade_curve = "linear"
        s.cues = [c1, c2]
        s.go()
        uhr.vorruecken(1.5)                  # Bild bei 1.0 s ausgelassen
        out = s.tick()
        assert s.current_index == 1
        assert out[1]["intensity"] == 0, out
        s.stop()


# ── #1200: Geraete-Solo nur mit Laufzeit-Abdeckung ──────────────────────────

GERAETE = [9101, 9102, 9103]


def _matrix(fm, name):
    m = fm.new_rgb_matrix(name)
    m.fixture_grid = list(GERAETE)
    return m


def test_show_mit_geraete_solo_unterdrueckt_keinen_hinweis(fm):
    from src.core.engine.show_engine import ShowFunction
    from src.ui.widgets.ueberschneidung_hinweis import StartRegeln, stoppt_beim_start
    kind = _matrix(fm, "Lauf in Show")
    show = fm.new_show("Show")
    show.add_track("Spur").add_function(ShowFunction(kind.id, 0.0, 10.0))
    effekt = _matrix(fm, "Puls")
    solo = StartRegeln(gleiche_geraete=True)
    # Laufzeit: die Show nennt keine eigenen Geraete -> kein Stopp in beide Richtungen.
    assert fm.affected_fids(show.id) == set()
    assert not stoppt_beim_start(solo, [show.id], solo, [effekt.id], effekt.id)
    assert not stoppt_beim_start(solo, [effekt.id], solo, [show.id], show.id)
    # Gegenprobe: zwei Effekte auf denselben Geraeten stoppen sich wirklich.
    assert stoppt_beim_start(solo, [kind.id], solo, [effekt.id], effekt.id)
    assert stoppt_beim_start(solo, [effekt.id], solo, [kind.id], kind.id)


def test_hinweis_bleibt_gegen_show_mit_geraete_solo(fm):
    from src.core.engine import ueberschneidung
    from src.core.engine.show_engine import ShowFunction
    from src.ui.widgets.ueberschneidung_hinweis import (StartRegeln,
                                                        stopp_regeln_anwenden)
    kind = _matrix(fm, "Lauf in Show")
    show = fm.new_show("Show")
    show.add_track("Spur").add_function(ShowFunction(kind.id, 0.0, 10.0))
    effekt = _matrix(fm, "Puls")
    solo = StartRegeln(gleiche_geraete=True)

    import dataclasses

    @dataclasses.dataclass(frozen=True)
    class Treffer:
        eigene: object
        andere: object
        stoppt: str = ""

    t = Treffer(effekt, show)
    aus = stopp_regeln_anwenden([t], [effekt.id], solo, [((show.id,), solo)])
    assert aus, "Hinweis faelschlich unterdrueckt — der Stopp greift zur Laufzeit nicht"
    assert getattr(aus[0], "stoppt", "") not in (ueberschneidung.DIESE_STOPPT,
                                                 ueberschneidung.ANDERE_STOPPT)


def test_grundtempo_ueberlebt_neuaufbau_und_zweiten_dial(fm):
    """Review CDX-62: die Basis haengt am Effekt, nicht an einer Dial-Instanz —
    ein neu aufgebautes Pult (Seitenwechsel/Laden) oder ein zweiter Dial auf
    denselben Effekt darf das geklemmte Tempo nicht als Grundwert nehmen."""
    e = fm.new_efx("Kreis3")
    e.tempo_bus_id = ""
    e.tempo_multiplier = 1.0
    e.speed_hz = 5.0
    a = _dial([e.id], [1.0, 4.0], 1.0)
    a._set_factor(4.0)
    assert abs(e.speed_hz - 10.0) < 1e-9
    b = _dial([e.id], [1.0, 4.0], 4.0)       # neu aufgebaut / zweiter Dial
    b._set_factor(1.0)
    assert abs(e.speed_hz - 5.0) < 1e-6, f"Grundtempo verloren: {e.speed_hz}"


def test_fremder_effekt_mit_gleicher_id_erbt_keine_basis(fm):
    """Gleiche fid nach Loeschen/Show-Wechsel, anderer Multiplikator: keine
    uebernommene Basis."""
    e = fm.new_efx("Kreis4")
    e.tempo_bus_id = ""
    e.tempo_multiplier = 1.0
    e.speed_hz = 5.0
    d = _dial([e.id], [1.0, 2.0, 4.0], 1.0)
    d._set_factor(4.0)                       # gemerkt: Basis 5, speed 10, mult 4
    e.tempo_multiplier = 1.0                 # „neuer“ Effekt: 10 Hz bei ×1
    d._set_factor(1.0)
    assert abs(e.speed_hz - 10.0) < 1e-6, e.speed_hz
