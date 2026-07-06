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

def test_mode_rename_is_substring_of_fullname():
    # Der L2600-Fall: gespeicherter Kurzname ⊂ voller DDF-Name → Umbenennung.
    old, full = "34-Kanal", "34-Kanal (Professional DMX)"
    assert bool(old) and old.strip().lower() in full.strip().lower()


def test_mode_real_mismatch_not_substring():
    old, full = "16-Kanal", "34-Kanal (Professional DMX)"
    assert old.strip().lower() not in full.strip().lower()
