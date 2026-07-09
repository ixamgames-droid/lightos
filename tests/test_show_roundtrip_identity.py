"""STAB-10 — persistierte Shows muessen nach der Kanonisierung stabil bleiben."""
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
    """JSON-Objekte vergleichbar machen, auch falls Loader Key-Typen aendert."""
    if isinstance(value, dict):
        return {str(key): _normalized(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalized(item) for item in value]
    return value


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


@pytest.mark.parametrize(
    "address,channel_count,expected_address,expected_channels",
    [(-1, 0, 1, 1), (999, 999, 512, 512)],
)
def test_patch_dump_and_load_share_dmx_bounds(
    address: int, channel_count: int, expected_address: int, expected_channels: int
):
    """Der Dump muss dieselben 1..512-Grenzen wie der Loader anwenden."""
    dumped = show_file._fixture_to_dict(
        {"fid": 1, "address": address, "channel_count": channel_count}
    )
    restored = show_file._patched_fixture_from_data(dumped, fallback_fid=1)

    assert dumped["address"] == expected_address
    assert dumped["channel_count"] == expected_channels
    assert show_file._fixture_to_dict(restored) == dumped
