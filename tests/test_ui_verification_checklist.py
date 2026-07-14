"""QA-12: Gate fuer die maschinen-pruefbare UI-Verifikationscheckliste.

Sichert ``docs/UI_VERIFICATION_CHECKLIST.md`` gegen Doku-Drift ab. Der
generierte Block (siehe ``tools/ui_verification_checklist``) muss:

* (a) **jede** entdeckte no-arg ``*View`` und **jedes** ``WIDGET_REGISTRY``-
  Widget als Zeile enthalten — eine neue/umbenannte Komponente ist damit sofort
  rot, bis sie im Report auftaucht (Regressionsschutz);
* (b) in der **headless**-Spalte mit dem echten Bau uebereinstimmen — der Report
  wird gegen den frisch offscreen gebauten Ist-Zustand geprueft;
* (c) je Zeile einen ausfuehrbaren Verifikationspfad (`pytest`-Testname) ODER
  `manuell` nennen, und die genannten Regressionstest-Pfade muessen existieren.

Roter Test heisst: `python tools/ui_verification_checklist.py` neu laufen lassen.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from tools.ui_verification_checklist import (
    REPORT_PATH,
    SMOKE_FILE,
    build_rows,
    compose,
    discover_no_arg_views,
    discover_vc_widgets,
    parse_block,
    render_block,
)


def test_checklist_links_to_the_enumerating_smoke_gate():
    """QA-13-Erbe: der Report verweist auf den enumerierenden Smoke + Registry."""
    text = (Path(__file__).parents[1] / "docs" / "UI_VERIFICATION_CHECKLIST.md").read_text(encoding="utf-8")
    assert "test_ui_smoke_enumerated.py" in text
    assert "WIDGET_REGISTRY" in text


@pytest.fixture(scope="module")
def rows() -> tuple[list[dict], list[dict]]:
    return build_rows()


@pytest.fixture(scope="module")
def report_text() -> str:
    assert REPORT_PATH.exists(), (
        "docs/UI_VERIFICATION_CHECKLIST.md fehlt — "
        "python tools/ui_verification_checklist.py ausfuehren."
    )
    return REPORT_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def parsed(report_text: str) -> dict[str, dict]:
    block = parse_block(report_text)
    assert block, "GENERATED-Block nicht gefunden/leer im Report."
    return block


def test_every_view_and_widget_is_listed(parsed: dict[str, dict]):
    """(a) Jede entdeckte View/jedes Widget kommt in der Checkliste vor."""
    expected = set(discover_no_arg_views()) | set(discover_vc_widgets())
    missing = sorted(expected - set(parsed))
    assert not missing, (
        "Nicht in docs/UI_VERIFICATION_CHECKLIST.md (Report neu erzeugen): "
        + ", ".join(missing)
    )


def test_no_stale_rows(parsed: dict[str, dict]):
    """Keine Karteileichen: jede Zeile entspricht einer echten Komponente."""
    expected = set(discover_no_arg_views()) | set(discover_vc_widgets())
    stale = sorted(set(parsed) - expected)
    assert not stale, (
        "Ueberzaehlige Zeilen in der Checkliste (Report neu erzeugen): "
        + ", ".join(stale)
    )


def test_headless_column_matches_real_build(
    parsed: dict[str, dict], rows: tuple[list[dict], list[dict]]
):
    """(b) Die dokumentierte headless-Spalte trifft den echten Bau."""
    view_rows, widget_rows = rows
    mismatches = []
    for r in view_rows + widget_rows:
        doc_row = parsed.get(r["key"])
        if doc_row is None:
            continue  # von (a) abgedeckt
        if doc_row["headless"] != r["headless"]:
            mismatches.append(
                f"{r['key']}: Report={doc_row['headless']} vs. Bau={r['headless']}"
            )
    assert not mismatches, (
        "headless-Spalte driftet vom Ist-Zustand (Report neu erzeugen): "
        + "; ".join(mismatches)
    )


def test_all_discovered_components_build_headless(
    rows: tuple[list[dict], list[dict]]
):
    """Kern-Invariante: alle enumerierten Views/Widgets bauen offscreen."""
    view_rows, widget_rows = rows
    broken = [
        f"{r['key']} ({r['cls']}): {r['error']}"
        for r in view_rows + widget_rows
        if not r["headless"]
    ]
    assert not broken, "Nicht headless baubar:\n" + "\n".join(broken)


def test_verification_path_is_executable(parsed: dict[str, dict]):
    """(c) Jede Zeile nennt einen Testnamen ODER 'manuell'."""
    empty = [k for k, v in parsed.items() if not v["verify"].strip()]
    assert not empty, f"Zeilen ohne Verifikationspfad: {empty}"


def test_regression_test_paths_exist(rows: tuple[list[dict], list[dict]]):
    """Jeder referenzierte Regressionstest-Pfad existiert wirklich."""
    view_rows, widget_rows = rows
    missing = sorted(
        {
            r["regtest"]
            for r in view_rows + widget_rows
            if not (ROOT / r["regtest"]).exists()
        }
    )
    assert not missing, f"Referenzierte Testdateien fehlen: {missing}"
    assert (ROOT / SMOKE_FILE).exists(), f"{SMOKE_FILE} fehlt (Verifikationsanker)."


def test_report_is_up_to_date(
    report_text: str, rows: tuple[list[dict], list[dict]]
):
    """Der Report auf Platte entspricht exakt der frischen Generierung."""
    view_rows, widget_rows = rows
    expected = compose(report_text, render_block(view_rows, widget_rows))
    assert report_text == expected, (
        "docs/UI_VERIFICATION_CHECKLIST.md ist nicht aktuell — "
        "python tools/ui_verification_checklist.py ausfuehren."
    )
