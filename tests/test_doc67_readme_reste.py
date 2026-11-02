"""DOC-67: README nachgezogen — Hilfe bei Problemen, Generator-Anleitung,
Showcase-/Bühnen-Show-Links, 3D-Qualitätsstufen.

Reiner Text-Test: liest README und Quelltext als Text, importiert nichts aus
``src`` (kein Datenordner, keine Ausgabe).
"""
from __future__ import annotations

import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _lies(rel: str) -> str:
    with open(os.path.join(REPO, rel), encoding="utf-8") as f:
        return f.read()


def _abschnitt(text: str, ueberschrift: str) -> str:
    m = re.search(rf"^## {re.escape(ueberschrift)}\s*$(.*?)(?=^## |\Z)",
                  text, re.M | re.S)
    assert m, f"README: Abschnitt „## {ueberschrift}“ fehlt"
    return m.group(1)


def test_hilfe_bei_problemen_nennt_diagnosepaket_logs_und_echten_start():
    readme = _lies("README.md")
    teil = _abschnitt(readme, "Hilfe bei Problemen")
    # Menüeintrag und Kommandozeile so, wie der Code sie anbietet
    menue = "Diagnosepaket speichern…"
    assert menue in _lies("src/ui/main_window.py")
    assert menue in teil
    assert '"--diagnose"' in _lies("main.py")
    assert "python main.py --diagnose" in teil
    assert "LightOS.exe --diagnose" in teil
    assert "LightOS-Diagnose-" in _lies("src/core/diagnose_log.py")
    assert "LightOS-Diagnose-" in teil
    # Ort von Sitzungs-Log und crash.log (diagnose_log.log_dir / paths.crash_log_path)
    assert 'os.path.join(app_data_dir(), "logs")' in _lies("src/core/diagnose_log.py")
    assert '"crash.log"' in _lies("src/core/paths.py")
    assert "logs/lightos.log" in teil and "crash.log" in teil
    # STAB-39: echte Daten nur über den normalen Start, Probelauf im Titel
    assert "PROBELAUF (Wegwerf-Daten, keine Ausgabe)" in _lies("src/core/paths.py")
    assert "PROBELAUF" in teil
    assert "normalen Start" in teil
    # Verweis auf die ausführliche Fassung in INSTALL.md
    assert "## Fehler melden / Diagnosepaket" in _lies("INSTALL.md")
    assert "INSTALL.md#fehler-melden--diagnosepaket" in teil


def test_fixture_generator_zeile_verlinkt_generator_anleitung():
    readme = _lies("README.md")
    ziel = "docs/anleitung_fixture_generator/ANLEITUNG_FIXTURE_GENERATOR.md"
    assert os.path.isfile(os.path.join(REPO, ziel))
    zeile = next(z for z in readme.split("\n- ") if z.startswith("**Fixture-Generator:**"))
    assert f"]({ziel})" in zeile, "Fixture-Generator-Zeile verlinkt die Generator-Anleitung nicht"


def test_demo_shows_verlinken_showcase_und_buehnen_show():
    readme = _lies("README.md")
    for ziel in ("docs/showcase/club_nacht.md",
                 "docs/showcase/theater_event.md",
                 "docs/anleitung_buehnen_show/ANLEITUNG_BUEHNEN_SHOW.md"):
        assert os.path.isfile(os.path.join(REPO, ziel)), ziel
        assert f"]({ziel})" in readme, f"README verlinkt {ziel} nicht"
    assert "## Shows & Beispiele" in _lies("docs/ANLEITUNGEN.md")
    assert "](docs/ANLEITUNGEN.md#shows--beispiele)" in readme


def test_qualitaetsstufen_im_readme_passen_zum_code():
    readme = _lies("README.md")
    js = _lies("src/ui/visualizer/scene_src/scene/quality_tiers.js")
    assert "export const TIER_NAMES = Object.freeze(['low', 'high', 'max']);" in js
    fenster = _lies("src/ui/visualizer/visualizer_window.py")
    assert 'QGroupBox("Render-Qualität")' in fenster
    assert '"Einstellungen")' in fenster
    for label in ("Automatisch (empfohlen)", "Hoch (Desktop-GPU)",
                  "Niedrig (schwache/mobile GPU)", "Maximal (starke Desktop-GPU)"):
        assert label in fenster
    assert "Qualitätsstufen Niedrig, Hoch und Maximal" in readme
    assert "Reiter Einstellungen → Render-Qualität" in readme
    assert "„Automatisch“ wählt beim Start Niedrig oder Hoch" in readme
    assert "Maximal nur von Hand" in readme
