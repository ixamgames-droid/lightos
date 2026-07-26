"""Eine gespeicherte Show muss nach dem ersten Load ein FIXPUNKT sein.

Geborgen 2026-07-26 aus dem nie gemergten Branch `fix/show-roundtrip-identity`.

Abgrenzung zu `tests/test_show_roundtrip_identity.py` (bereits auf main): das dort
Geprueftte ist der **patch-Block** ueber `_fixture_to_dict`/`_patched_fixture_from_data`.
Dieser Test hier geht ueber den **kompletten** Weg `load_show` -> `save_show` ->
`load_show` -> `save_show` und vergleicht die beiden `show.json` strukturgleich —
ueber ALLE committeten Shows. Damit faellt jede Save/Load-Asymmetrie auf, nicht nur
die im Patch (Funktionen, VC-Layout, Paletten, Szenegraph …).

Konkret gefunden hat der Branch damit die Label-Asymmetrie: der Dump schrieb `''`,
der Loader machte daraus `'Fixture 7'` — der ERSTE save/load/save aenderte eine
Show-Datei also still (Diff-Rauschen in Git). Behoben in `show_file._fixture_to_dict`
(beide Zweige kanonisieren jetzt wie der Loader).

Ein Migrations-Schritt beim ERSTEN Load bleibt ausdruecklich erlaubt — verglichen
werden der zweite und der dritte Stand.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from src.core.show import show_file

ROOT = Path(__file__).resolve().parents[1]
SHOWS = sorted((ROOT / "shows").glob("*.lshow"))


def _show_json(path: Path) -> dict:
    with zipfile.ZipFile(path, "r") as archive:
        return json.loads(archive.read("show.json").decode("utf-8"))


def _normalized(value):
    """JSON-Objekte vergleichbar machen, auch falls der Loader Key-Typen aendert."""
    if isinstance(value, dict):
        return {str(key): _normalized(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalized(item) for item in value]
    return value


@pytest.mark.skipif(not SHOWS, reason="keine committeten Shows im Repo")
@pytest.mark.parametrize("source", SHOWS, ids=lambda path: path.name)
def test_committed_show_is_stable_after_canonical_save_load_save(
    source: Path, tmp_path: Path
):
    """Altshows duerfen beim ersten Load migrieren, danach aber nicht mehr driften."""
    ok, message = show_file.load_show(source)
    assert ok, f"{source.name}: {message}"

    first = tmp_path / "first.lshow"
    second = tmp_path / "second.lshow"
    show_file.save_show(first)
    first_data = _show_json(first)

    ok, message = show_file.load_show(first)
    assert ok, f"{source.name} (canonical): {message}"
    show_file.save_show(second)

    assert _normalized(_show_json(second)) == _normalized(first_data), source.name


def test_empty_label_survives_save_load_save():
    """Regression zur geborgenen Label-Asymmetrie: der Dump kanonisiert wie der Loader.

    Vorher: 1. Dump `''` -> Loader `'Fixture 7'` -> 2. Dump `'Fixture 7'`.
    Der erste Roundtrip aenderte die Datei also still.
    """
    dumped = show_file._fixture_to_dict(
        {"fid": 7, "label": "", "address": 10, "channel_count": 4}
    )
    restored = show_file._patched_fixture_from_data(dumped, fallback_fid=7)
    redumped = show_file._fixture_to_dict(restored)

    assert dumped["label"] == "Fixture 7"
    assert redumped["label"] == dumped["label"]
