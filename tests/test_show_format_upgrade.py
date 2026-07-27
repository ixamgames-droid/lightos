"""Show-Format-Upgrade (2026-07-26): Alt-Shows auf SHOW_VERSION + Fremdformat-Gate.

Hintergrund: die committeten Demo-Shows lagen auf ``version "1.1"`` (aktuell ist
``1.2``) — sie luden zwar weiter, die DATEIEN blieben aber alt, bis sie einmal
gespeichert wurden. ``tools/upgrade_shows.py`` macht genau diesen Schritt.

Dabei fiel ``shows/demo_rgb_par.lshow`` auf: KEINE Alt-Show, sondern ein nie
implementierter Format-Entwurf (``format_version``/``universes`` + eigene
ZIP-Eintraege). ``load_show`` fand darin keinen einzigen bekannten Block und
meldete trotzdem ok=True — der Nutzer stand vor einer leeren Buehne. Seitdem
lehnt der Loader solche Dateien ab (und laesst den bisherigen Show-Zustand
stehen); die Datei selbst wurde per ``tools/build_demo_rgb_par.py`` als echte
Show im aktuellen Format neu gebaut.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import zipfile

import pytest

from src.core.show import show_file
from src.core.show.show_file import SHOW_VERSION, load_show, save_show

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOWS = sorted(glob.glob(os.path.join(REPO, "shows", "*.lshow")))
sys.path.insert(0, os.path.join(REPO, "tools"))

# Die show.json des Fremd-Entwurfs, wie sie bis 2026-07-26 in shows/ lag.
FOREIGN = {
    "format_version": "1.0",
    "name": "Demo RGB PAR Show",
    "created": "2026-05-27T00:00:00",
    "author": "LightOS",
    "notes": "Demo-Show: 4 x RGB-PAR, 4 Cues",
    "universes": 1,
    "software_version": "1.0.0",
}


def _write_lshow(path, show: dict) -> str:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("show.json", json.dumps(show, ensure_ascii=False))
    return str(path)


def _show_json(path) -> dict:
    with zipfile.ZipFile(path, "r") as zf:
        return json.loads(zf.read("show.json").decode("utf-8"))


# ── Fremdformat-Gate ────────────────────────────────────────────────────────────

def test_foreign_show_json_is_rejected_instead_of_loading_empty(tmp_path):
    """Eine show.json ohne jeden LightOS-Block MUSS abgelehnt werden.

    Vorher lief sie durch den kompletten Loader: jedes ``data.get(...)`` traf ins
    Leere -> ok=True samt "Show '<Name>' geladen." und eine LEERE Show. Die
    Fehlermeldung nennt den Grund und die Fremd-Marker."""
    path = _write_lshow(tmp_path / "fremd.lshow", FOREIGN)

    ok, msg = load_show(path)

    assert not ok, f"Fremdformat wurde geladen: {msg}"
    assert "Unbekanntes Show-Format" in msg, msg
    assert "format_version" in msg, msg          # der konkrete Fremd-Marker


def test_rejected_foreign_show_leaves_the_current_show_untouched(tmp_path):
    """Das Gate greift VOR dem reset-first des Loaders: eine abgelehnte Datei
    darf die offene Show nicht wegraeumen (sonst waere 'nicht geladen' eine
    Luege und der Nutzer haette seinen Stand verloren)."""
    from src.core.app_state import get_state
    state = get_state()
    state.show_name = "Laufende Show"
    state.programmer[4711] = {"intensity": 200}

    ok, _msg = load_show(_write_lshow(tmp_path / "fremd2.lshow", FOREIGN))

    assert not ok
    assert state.show_name == "Laufende Show"
    assert state.programmer.get(4711) == {"intensity": 200}


def test_gate_never_rejects_a_show_written_by_save_show(tmp_path):
    """Gegenprobe: das Gate darf niemals eine ECHTE Show abweisen. ``save_show``
    schreibt immer ``version`` + mehrere bekannte Bloecke -> muss laden."""
    path = str(tmp_path / "echt.lshow")
    save_show(path)

    data = _show_json(path)
    assert "version" in data
    assert show_file._KNOWN_SHOW_BLOCKS & set(data), sorted(data)
    ok, msg = load_show(path)
    assert ok, msg


def test_gate_accepts_legacy_show_without_version_key(tmp_path):
    """Alt-Shows OHNE ``version``, aber mit echten Bloecken, bleiben ladbar —
    das Gate darf nur wirklich fremde Dateien treffen."""
    path = _write_lshow(tmp_path / "alt.lshow",
                        {"name": "Ganz alt", "patch": [], "functions": {"functions": []}})
    ok, msg = load_show(path)
    assert ok, msg


# ── Committete Shows sind auf dem aktuellen Format ──────────────────────────────

@pytest.mark.skipif(not SHOWS, reason="keine committeten Shows im Repo")
@pytest.mark.parametrize("path", SHOWS, ids=lambda p: os.path.basename(p))
def test_committed_show_is_at_current_version(path):
    """Jede committete Show traegt SHOW_VERSION.

    Faellt das nach einem ``SHOW_VERSION``-Bump um: die Dateien einmal mit
    ``venv/Scripts/python.exe tools/upgrade_shows.py`` anheben (macht load->save
    und prueft, dass nichts verloren geht)."""
    version = _show_json(path).get("version")
    assert version == SHOW_VERSION, (
        f"{os.path.basename(path)} liegt auf {version!r} statt {SHOW_VERSION!r} — "
        "`tools/upgrade_shows.py` laufen lassen.")


@pytest.mark.skipif(not SHOWS, reason="keine committeten Shows im Repo")
def test_upgrade_tool_check_mode_is_green():
    """Das Werkzeug selbst muss die committeten Shows als aktuell melden
    (Exit 0) — haelt Tool und Dateien zusammen."""
    import upgrade_shows

    assert upgrade_shows.main(["--check"]) == 0


# ── Der neu gebaute RGB-PAR-Demo (ersetzt den Fremd-Entwurf) ────────────────────

@pytest.mark.skipif(not os.path.isfile(os.path.join(REPO, "shows", "demo_rgb_par.lshow")),
                    reason="demo_rgb_par.lshow nicht vorhanden")
def test_demo_rgb_par_loads_with_content():
    """Regression zum Ausloeser: die Datei muss echten Inhalt laden — 4 PARs auf
    den Original-Adressen und die 4-Cue-Cueliste des Entwurfs. Gebaut von
    ``tools/build_demo_rgb_par.py``."""
    from src.core.app_state import get_state
    path = os.path.join(REPO, "shows", "demo_rgb_par.lshow")

    ok, msg = load_show(path)
    assert ok, msg
    state = get_state()

    patched = sorted(state.get_patched_fixtures(), key=lambda p: p.fid)
    assert [pf.address for pf in patched] == [1, 4, 7, 10], [pf.address for pf in patched]
    assert [pf.label for pf in patched] == ["PAR 1", "PAR 2", "PAR 3", "PAR 4"], \
        [pf.label for pf in patched]

    assert len(state.cue_stacks) == 1, [s.name for s in state.cue_stacks]
    stack = state.cue_stacks[0]
    assert stack.name == "Demo-Show" and stack.mode == "single"
    assert [(c.label, c.fade_in, c.fade_out) for c in stack.cues] == [
        ("Blackout", 0.0, 0.0), ("Warm White", 3.0, 2.0),
        ("Rot", 2.0, 1.5), ("Blau", 2.0, 1.5),
    ], [(c.label, c.fade_in, c.fade_out) for c in stack.cues]
    # Die Cues treffen alle vier Geraete mit RGB-Werten.
    for cue in stack.cues:
        assert set(cue.values) == {pf.fid for pf in patched}, (cue.label, cue.values)
        for vals in cue.values.values():
            assert set(vals) == {"color_r", "color_g", "color_b"}, (cue.label, vals)
