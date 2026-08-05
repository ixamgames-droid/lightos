"""UXT-08/10/11: Kleinvieh aus dem UX-Dogfooding.

- UXT-08: Modus-Umbenennung (Kurzform ⊂ Vollname) wird nicht mehr als „fehlt"
  alarmiert.
- UXT-11b: Show-Dialoge starten in einem sinnvollen Ordner (aktuelle Show bzw.
  ein angelegter shows-Ordner), nicht im Arbeitsverzeichnis.
"""
from __future__ import annotations
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ── UXT-11b: Default-Show-Verzeichnis ─────────────────────────────────────────

def test_default_show_dir_uses_current_show_folder(tmp_path):
    from src.ui.main_window import MainWindow
    show = tmp_path / "meine.lshow"
    show.write_text("x", encoding="utf-8")
    fake = types.SimpleNamespace(_current_show_path=str(show))
    assert MainWindow._default_show_dir(fake) == str(tmp_path)


def test_default_show_dir_fallback_is_shows_folder():
    from src.ui.main_window import MainWindow
    fake = types.SimpleNamespace(_current_show_path=None)
    d = MainWindow._default_show_dir(fake)
    assert d.endswith("shows")
    assert os.path.isdir(d)              # wird angelegt
    # Nicht das Arbeitsverzeichnis / der Repo-Root.
    assert os.path.abspath(d) != os.path.abspath(os.getcwd())


# ── UXT-08: Modus-Umbenennung nicht als „fehlt" melden ────────────────────────

# ★ Diese beiden Tests riefen bis 2026-08-05 den Produktionscode NICHT auf — sie
# bauten die Bedingung im Test nach (`old.strip().lower() in full…`). Damit waren
# sie per Konstruktion immer gruen: sie konnten weder eine geaenderte noch eine
# geloeschte Implementierung bemerken, und die Einseitigkeit der Pruefung haben
# sie mit nachgebaut statt sie aufzudecken. Jetzt gegen `_ist_umbenennung`.

def test_mode_rename_is_substring_of_fullname():
    # Der L2600-Fall: gespeicherter Kurzname ⊂ voller DDF-Name → Umbenennung.
    from src.core.sync import _ist_umbenennung
    assert _ist_umbenennung("34-Kanal", "34-Kanal (Professional DMX)")


def test_mode_real_mismatch_not_substring():
    from src.core.sync import _ist_umbenennung
    assert not _ist_umbenennung("16-Kanal", "34-Kanal (Professional DMX)")


def test_entfernter_vorbehalt_gilt_als_umbenennung():
    """Die Gegenrichtung — der ZQ06121-Fall vom 2026-08-05.

    Reifegrad-Vermerke stehen im Modusnamen, solange etwas unbestaetigt ist, und
    verschwinden, sobald es geprueft wurde. Der neue Name ist dann KUERZER als
    der gespeicherte. Einseitig geprueft meldete sync genau dafuer „Mode fehlt"
    — ein Fehlalarm ausgerechnet beim Verbessern eines Profils.
    """
    from src.core.sync import _ist_umbenennung
    assert _ist_umbenennung("154-Kanal 48 Zonen RGB + 8x Weiss (ungeprueft)",
                            "154-Kanal 48 Zonen RGB + 8x Weiss")
    assert _ist_umbenennung("7-Kanal (Beta)", "7-Kanal")
    assert _ist_umbenennung("Standard (vorlaeufig)", "Standard")


def test_umbenennung_ist_symmetrisch():
    from src.core.sync import _ist_umbenennung
    for a, b in (("34-Kanal", "34-Kanal (Professional DMX)"),
                 ("16-Kanal", "34-Kanal (Professional DMX)"),
                 ("Standard", "Standard")):
        assert _ist_umbenennung(a, b) == _ist_umbenennung(b, a), (a, b)


def test_leere_namen_sind_keine_umbenennung():
    # Ohne die Leer-Pruefung waere "" in jedem Namen enthalten — jeder fehlende
    # Modus wuerde als harmlose Umbenennung durchgewunken.
    from src.core.sync import _ist_umbenennung
    assert not _ist_umbenennung("", "34-Kanal")
    assert not _ist_umbenennung("34-Kanal", "")
    assert not _ist_umbenennung(None, "34-Kanal")
    assert not _ist_umbenennung("   ", "34-Kanal")
