"""ENG-36: Gleiches mit Gleichem überschreiben ist keine Änderung.

Befund der Sichtprobe: „Ersetzen" bei gleichem Typ meldete „14 Stellen
geklont", obwohl die Show danach inhaltlich unverändert war. Stellen, deren
Zielwert schon der zu schreibende Wert ist, zählen als „bleibt, wie es ist" und
werden nicht geschrieben; „Anwenden" bleibt grau, wenn sich nichts ändern
würde. Ein Klonen mit echter Änderung macht die Show „geändert", Rückgängig
stellt den Stand von vorher her — mit demselben Show-Fingerabdruck.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                           # noqa: E402

from _eng36_show import RGB, show_fixture                            # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets             # noqa: E402
from src.core.engine import palette as palette_mod                   # noqa: E402
from src.core.engine import snap_library as snap_mod                 # noqa: E402
from src.core.engine.cue import Cue                                  # noqa: E402
from src.core.engine.cue_stack import CueStack                       # noqa: E402
from src.core.engine.scene import Scene, SceneValue                  # noqa: E402
from src.core.show import klonen as K                                # noqa: E402
from src.core.show import show_file                                  # noqa: E402
from src.core.undo import get_undo_stack                             # noqa: E402
from src.ui.widgets import klonen_dialog as D                        # noqa: E402

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _keine_fenster_uebrig():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


@pytest.fixture
def show(tmp_path, monkeypatch):
    for sh in show_fixture(tmp_path, monkeypatch):
        # Der Show-Fingerabdruck liest Snaps und Paletten über die
        # Verwalter der App — hier sind es die der Test-Show.
        monkeypatch.setattr(snap_mod, "get_snap_library", lambda: sh.snaps)
        monkeypatch.setattr(palette_mod, "get_palette_manager",
                            lambda: sh.paletten)
        monkeypatch.setattr(show_file, "_gemerkter_stand", None)
        yield sh


class _Umgebung(D.Umgebung):
    def __init__(self, state):
        super().__init__(None, state)
        self.gesichert = 0

    def sichern(self):
        self.gesichert += 1
        return "sicherung.lshow"


def _dialog(show, quellen, ziele):
    umgebung = _Umgebung(show.state)
    dlg = D.KlonenDialog(show.state, quellen, ziele, umgebung=umgebung,
                         snap_library=show.snaps,
                         palette_manager=show.paletten)
    return dlg, umgebung


def _gleiche_show(show, mit_ziel=True):
    """Zwei gleiche Geräte, die an vielen Stellen schon dasselbe tun."""
    show.patch(1, RGB, "EVENTPARIP65 1")
    show.patch(2, RGB, "EVENTPARIP65 2")
    rot = {"intensity": 200, "color_r": 255, "color_g": 0, "color_b": 0}
    for i in range(3):
        show.snaps.add_snap(f"Snap {i}", "", {
            1: dict(rot), **({2: dict(rot)} if mit_ziel else {})})
    for name in ("Hintergrund", "Party", "Alle Strobe"):
        show.gruppe(name, {"0,0": 1, **({"1,0": 2} if mit_ziel else {})})
    show.state.base_levels = {1: {"intensity": 255},
                              **({2: {"intensity": 255}} if mit_ziel else {})}
    return rot


# ── (c) Gleiches mit Gleichem ist keine Änderung ────────────────────────────

def test_ersetzen_von_gleichem_zaehlt_nicht_und_schreibt_nicht(show):
    rot = _gleiche_show(show)
    vorher = show_file.show_fingerabdruck(show.state)
    assert vorher
    for wie in (K.ERSETZEN, K.HINZUFUEGEN):
        plan = show.plane([1], [2], wie=wie)
        z = plan.zaehler()
        assert plan.aenderungen == 0, wie
        assert (z[K.UNVERAENDERT], z[K.UEBERSETZT], z[K.FAELLT_WEG]) == (0, 0, 0)
        # 3 Snaps + 3 Gruppen + Grundwerte
        assert z[K.BLEIBT] == 7
        assert not plan._alle_schritte(), "nichts zu schreiben"
        assert plan.beruehrte_bereiche == set()
    texte = [e.text for e in show.plane([1], [2], wie=K.ERSETZEN).eintraege
             if e.bereich == K.BEREICH_SNAPS]
    assert all("schon denselben Wert" in t for t in texte) and len(texte) == 3
    assert show_file.show_fingerabdruck(show.state) == vorher
    assert show.snaps.snaps()[0].values[2] == rot


def test_ersetzen_zaehlt_nur_die_stellen_die_sich_aendern(show):
    """Ein Snap weicht ab: genau er zählt — die gleichen bleiben „bleibt"."""
    _gleiche_show(show)
    anders = show.snaps.snaps()[1]
    anders.values[2]["color_r"] = 10
    plan = show.plane([1], [2], wie=K.ERSETZEN)
    assert plan.aenderungen == 1
    eintrag = [e for e in plan.eintraege if e.kennzeichen == K.UNVERAENDERT][0]
    assert anders.name in eintrag.objekt and eintrag.art == "ersetzt"
    assert "Rot" in eintrag.text and "Grün" not in eintrag.text
    assert plan.anwenden(show.state) == 1
    assert anders.values[2]["color_r"] == 255
    # Danach ist alles gleich: ein zweiter Durchgang hätte nichts mehr zu tun.
    assert show.plane([1], [2], wie=K.ERSETZEN).aenderungen == 0


def test_cue_mit_gleichen_werten_aber_anderer_verzoegerung_ist_eine_aenderung(show):
    show.patch(1, RGB)
    show.patch(2, RGB)
    cue = Cue(number=1.0, label="Eins")
    cue.values = {1: {"intensity": 200}, 2: {"intensity": 200}}
    cue.attr_delays = {1: {"intensity": 0.5}}
    stack = CueStack("Haupt")
    stack.cues.append(cue)
    show.state.cue_stacks = [stack]
    plan = show.plane([1], [2], wie=K.ERSETZEN, bereiche=[K.BEREICH_CUES])
    assert plan.aenderungen == 1
    plan.anwenden(show.state)
    assert cue.attr_delays[2] == {"intensity": 0.5}
    # Jetzt stimmt auch die Verzögerung: keine Änderung mehr.
    assert show.plane([1], [2], wie=K.ERSETZEN,
                      bereiche=[K.BEREICH_CUES]).aenderungen == 0


def test_szene_mit_gleichen_kanalwerten_ist_keine_aenderung(show):
    show.patch(1, RGB)
    show.patch(2, RGB)
    szene = Scene("Grundlicht")
    szene._values[:] = [SceneValue(1, 1, 200), SceneValue(1, 2, 255),
                        SceneValue(2, 1, 200), SceneValue(2, 2, 255)]
    show.state.function_manager.add(szene)
    vorher = [(v.fixture_id, v.channel, v.value) for v in szene._values]
    plan = show.plane([1], [2], wie=K.ERSETZEN, bereiche=[K.BEREICH_SNAPS])
    assert plan.aenderungen == 0 and plan.zaehler()[K.BLEIBT] == 1
    szene._values[3] = SceneValue(2, 2, 9)
    plan = show.plane([1], [2], wie=K.ERSETZEN, bereiche=[K.BEREICH_SNAPS])
    assert plan.aenderungen == 1
    plan.anwenden(show.state)
    assert [(v.fixture_id, v.channel, v.value) for v in szene._values] == vorher


def test_dialog_anwenden_bleibt_grau_wenn_sich_nichts_aendern_wuerde(show):
    _gleiche_show(show)
    stack = get_undo_stack()
    dlg, umgebung = _dialog(show, [1], [2])
    for knopf in (dlg._ersetzen, dlg._hinzufuegen, dlg._ersetzen):
        knopf.setChecked(True)
        assert not dlg._anwenden.isEnabled()
        assert dlg._anwenden.text() == "Anwenden"
        assert "0 unverändert übernommen" in dlg._zaehler.text()
        assert "7 bleibt, wie es ist" in dlg._zaehler.text()
    dlg._anwenden.click()                # grau: tut nichts
    dlg._anwenden_geklickt()             # auch direkt gerufen: tut nichts
    assert dlg.ergebnis is None and umgebung.gesichert == 0
    assert not stack.can_undo()


def test_echte_aenderung_show_gilt_als_geaendert_und_rueckgaengig_stellt_her(show):
    """Der Fall, den die Sichtprobe NICHT belegt hat: die Quelle hat
    Snap-Werte, das Ziel nicht."""
    _gleiche_show(show, mit_ziel=False)
    state = show.state
    stack = get_undo_stack()
    vorher = show_file.show_fingerabdruck(state)
    show_file.merke_show_stand(state)                # „gerade gespeichert"
    assert not show_file.show_hat_aenderungen(state)
    snaps_vorher = {s.name: {f: dict(w) for f, w in s.values.items()}
                    for s in show.snaps.snaps()}

    dlg, umgebung = _dialog(show, [1], [2])
    dlg._hinzufuegen.setChecked(True)
    # 3 Snaps + 3 Gruppen + Grundwerte, nichts davon hat das Ziel schon
    assert dlg._anwenden.isEnabled()
    assert dlg._anwenden.text() == "Anwenden (7 Stellen)"
    assert not show_file.show_hat_aenderungen(state), "Vorschau schreibt nichts"
    dlg._anwenden.click()
    assert dlg.ergebnis == 7 and umgebung.gesichert == 1

    for snap in show.snaps.snaps():
        assert snap.values[2] == snap.values[1]
    assert state.base_levels[2] == {"intensity": 255}
    assert state.group_fids_by_name("Party") == [1, 2]
    assert show_file.show_hat_aenderungen(state), "Show gilt als geändert"
    nachher = show_file.show_fingerabdruck(state)
    assert nachher != vorher

    assert stack.undo_label() == "Klonen 1 → 2" and len(stack._undo) == 1
    assert stack.undo()
    assert {s.name: s.values for s in show.snaps.snaps()} == snaps_vorher
    assert state.base_levels == {1: {"intensity": 255}}
    assert state.group_fids_by_name("Party") == [1]
    assert show_file.show_fingerabdruck(state) == vorher, \
        "nach Rückgängig derselbe Show-Abdruck wie vor dem Klonen"
    assert not show_file.show_hat_aenderungen(state)

    assert stack.redo()
    assert show_file.show_fingerabdruck(state) == nachher
    assert show_file.show_hat_aenderungen(state)
    assert stack.undo()
    assert show_file.show_fingerabdruck(state) == vorher
