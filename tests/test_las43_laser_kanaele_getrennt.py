"""LAS-43 — Laser ohne Profilangaben: ein Regler bewegte mehrere Kanaele.

Befund (QA96-13): Ein EL-230RGB MK2 aus einem aelteren Import traegt auf
Kanal 1 („Mode“) und Kanal 2 („Pattern“) dasselbe Attribut. Der Rueckfall-
Reiter baute EINEN Regler je Attribut; der schrieb den Basis-Schluessel, und
die Ausgabe spiegelt den auf jedes weitere Vorkommen ohne eigenen Wert
(``AppState``-Render: „Kopf>0 spiegelt Kopf 0“). Betriebsart und Muster liessen
sich nicht getrennt stellen.

Jetzt: Hat die Auswahl keine echte zweite Mustergruppe (L2600), bekommt jedes
Vorkommen eines doppelten Attributs einen eigenen Regler, beschriftet mit
Kanalnummer und Name, in einer NICHT eingeklappten Gruppe — und das Stellen
des einen Kanals laesst den anderen stehen. Die L2600-Bedienung (Gruppe A/B)
bleibt unveraendert (``test_laser_view``).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import test_laser_view as LV  # noqa: E402

_app = LV._app


class _Ch(LV._Ch):
    def __init__(self, attr, num, ranges=None, name="", default=0):
        super().__init__(attr, num, ranges, name)
        self.default_value = default


def _ausgabe(state, fx) -> dict[int, int]:
    """Was die Ausgabe je Kanal schreibt — dieselbe Regel wie der Render-Pfad
    in ``AppState`` (n-tes Vorkommen liest ``attr#n``, sonst ``attr``, sonst
    bleibt der Grundwert des Kanals)."""
    prog = state.programmer.get(fx.fid, {})
    gesehen: dict[str, int] = {}
    out = {}
    for ch in fx._chans:
        n = gesehen.get(ch.attribute, 0)
        gesehen[ch.attribute] = n + 1
        key = ch.attribute if n == 0 else f"{ch.attribute}#{n}"
        if key not in prog and n > 0:
            key = ch.attribute
        out[ch.channel_number] = prog.get(key, ch.default_value)
    return out


def _el230ish(attr="macro", ranges=True):
    """EL-230-artig ohne Profilangaben: Kanal 1 und 2 tragen dasselbe
    Attribut (aelterer Import)."""
    R = LV._Rng
    mode = [R(0, 49, "Aus", "closed"), R(50, 99, "Auto"),
            R(100, 149, "Sound", "sound"), R(150, 255, "DMX", "open")]
    muster = [R(0, 127, "Muster 1-16"), R(128, 255, "Muster 17-32")]
    return [
        _Ch(attr, 1, mode if ranges else [], "Mode"),
        _Ch(attr, 2, muster if ranges else [], "Pattern", default=7),
        _Ch("laser_x", 3, [], "X"),
        _Ch("laser_y", 4, [], "Y"),
        _Ch("speed", 5, [], "Speed"),
    ]


def _zeilen(view, attr):
    return {k: r for k, r in view._rows.items()
            if k.split("#", 1)[0] == attr}


def test_zwei_kanaele_gleichen_attributs_getrennt_stellbar(monkeypatch):
    _app()
    fx = LV._FX(1, _el230ish())
    view, state = _make(monkeypatch, fx)

    zeilen = _zeilen(view, "macro")
    assert len(zeilen) == 2, f"je Kanal ein Regler erwartet: {list(view._rows)}"
    texte = {}
    for row in zeilen.values():
        from PySide6.QtWidgets import QLabel
        texte[row] = " ".join(lb.text() for lb in row.findChildren(QLabel))
    alle = " | ".join(texte.values())
    assert "Kanal 1" in alle and "Mode" in alle
    assert "Kanal 2" in alle and "Pattern" in alle
    # „Mode“ nie in einer zugeklappten Gruppe.
    for row in zeilen.values():
        assert row.isVisibleTo(view), "Regler steckt in zugeklappter Gruppe"
    # Keine echte zweite Mustergruppe -> kein A/B-Umschalter.
    assert view._head_box.isVisibleTo(view) is False

    def zeile(nummer):
        return next(r for r, t in texte.items() if f"Kanal {nummer}" in t)

    vorher = _ausgabe(state, fx)
    zeile(1)._slider.setValue(60)                       # Betriebsart
    nach = _ausgabe(state, fx)
    assert nach[1] == 60
    assert nach[2] == vorher[2] == 7, "Kanal 2 lief mit Kanal 1 mit"

    zeile(2)._slider.setValue(200)                      # Muster
    nach = _ausgabe(state, fx)
    assert nach[2] == 200
    assert nach[1] == 60, "Kanal 1 lief mit Kanal 2 mit"

    # Neu laden zeigt je Kanal seinen eigenen Wert.
    view._load_values()
    assert zeile(1)._slider.value() == 60
    assert zeile(2)._slider.value() == 200
    # Kein Kanal geht verloren, und kein „macro#1“ als Fantasie-Attribut.
    assert "macro" in view.bedienbare_attribute()
    assert not any("#" in a for a in view.bedienbare_attribute())


def test_doppelter_betriebsart_kanal_kachel_trifft_nur_kanal_1(monkeypatch):
    """Tragen beide Kanaele ``shutter`` mit Bereichen, schreiben die
    Betriebsart-Kacheln Kanal 1 — Kanal 2 bleibt stehen und hat einen eigenen
    Regler."""
    _app()
    fx = LV._FX(1, _el230ish("shutter"))
    view, state = _make(monkeypatch, fx)
    zeilen = _zeilen(view, "shutter")
    assert set(zeilen) == {"shutter", "shutter#1"}
    view._on_mode_tile_clicked(0)                       # Kachel „Aus“
    aus = _ausgabe(state, fx)
    assert aus[1] == 0
    assert aus[2] == 7


def test_l2600_bleibt_bei_gruppe_a_b(monkeypatch):
    """Gegenprobe: ein Geraet mit echter zweiter Mustergruppe behaelt den
    A/B-Umschalter und einen Regler je Attribut."""
    _app()
    view, _state = _make(monkeypatch, LV._FX(1, LV._l2600ish_channels()))
    assert not view._head_box.isHidden()
    assert set(view._rows) == {"laser_bank", "gobo_wheel", "laser_x"}


def _make(monkeypatch, fx):
    view, state = LV._make_view(monkeypatch, [fx])
    view.refresh_from_selection()
    return view, state


def test_baustein_kanal_doppelt_weiterer_kanal_bleibt_bedienbar(monkeypatch):
    """Gegenprobe Baustein (LAS-34): Bedient ein Baustein das doppelte
    Attribut (Muster-Galerie auf ``gobo_wheel``), schreibt er Kanal 1 und haelt
    die weiteren Kanaele fest. Die muessen dann ihren EIGENEN Regler behalten —
    sonst stuende der zweite Kanal fest und waere im Reiter nicht bedienbar."""
    _app()
    import test_las34_laser_tab as T34
    import src.core.app_state as A
    chans = T34._el400()
    # Aelterer Import: die Scangeschwindigkeit traegt ohne Laser-Angaben
    # ebenfalls ``gobo_wheel`` (Kanal 5).
    zweit = next(c for c in chans if c.attribute == "laser_scan_rate")
    zweit.attribute, zweit.laser, zweit.default_value = "gobo_wheel", None, 9
    fx = T34._FX(1, chans)
    monkeypatch.setattr(A, "get_channels_for_patched", lambda f: f._chans,
                        raising=False)
    view, state = _make(monkeypatch, fx)
    assert view._plan.muster is not None, "Muster-Baustein erwartet"
    zeilen = _zeilen(view, "gobo_wheel")
    # Kanal 1 bedient der Baustein (samt seiner kompakten „alle 0–255“-
    # Zeile); in „Einzelne Kanäle“ steht nur der zweite Kanal.
    assert "gobo_wheel#1" in zeilen, list(view._rows)
    assert set(view._row_kopf) == {"gobo_wheel#1"}, view._row_kopf
    assert "Kanal 5" in " ".join(
        lb.text() for lb in zeilen["gobo_wheel#1"].findChildren(
            __import__("PySide6.QtWidgets", fromlist=["QLabel"]).QLabel))

    view._write_value("gobo_wheel", 40)            # Baustein-Weg
    aus = _ausgabe(state, fx)
    assert aus[2] == 40 and aus[5] == 9, "Kanal 5 lief mit dem Baustein mit"
    zeilen["gobo_wheel#1"]._slider.setValue(123)
    aus = _ausgabe(state, fx)
    assert aus[5] == 123 and aus[2] == 40
