"""QA-13: Tooltip-/Label-Coverage-Gate fuer interaktive Steuerelemente.

Baut jede no-arg ``*View`` headless und meldet ``QAbstractButton``s mit leerem
``text()`` UND leerem ``toolTip()``. Statt hart 0 Verstoesse zu fordern (heute
rot), fuehrt ``tools/audit_tooltip_coverage.BASELINE`` eine dokumentierte
Allowlist. Das Gate wird nur rot, wenn eine View NEUE textlose Buttons ohne
Tooltip bekommt (Regressionsschutz) — Behebung bestehender Verstoesse ist
jederzeit erlaubt (Baseline dort nachziehen).

Der lesbare Report liegt in ``docs/UI_TOOLTIP_COVERAGE.md`` und wird vom selben
Skript erzeugt.
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

from tools.audit_tooltip_coverage import (
    BASELINE,
    audit,
    discover_views,
    regressions,
)


@pytest.fixture(scope="module")
def coverage() -> dict[str, dict]:
    return audit()


def test_target_views_are_covered(coverage: dict[str, dict]):
    """QA-13 Mindestziel: show_manager + dmx_monitor sind erfasst."""
    for required in ("show_manager_view", "dmx_monitor_view"):
        assert required in coverage, f"{required} nicht im Audit"


def test_no_new_textless_buttons_without_tooltip(coverage: dict[str, dict]):
    """Regressionsschutz: keine View ueber ihrer dokumentierten Baseline.

    Schlaegt an, sobald ein neuer Button mit leerem Text UND leerem Tooltip
    dazukommt. Fix-Optionen: dem Button Text/Tooltip geben ODER — falls bewusst
    ikonlos ohne Hint — die Baseline in ``tools/audit_tooltip_coverage.py``
    anpassen und den Report neu erzeugen.
    """
    regs = regressions(coverage)
    assert not regs, "Neue textlose Buttons ohne Tooltip:\n" + "\n".join(
        f"  {view}: {count} > Baseline {allowed} — Offender: "
        + ", ".join(coverage[view]["offenders"])
        for view, count, allowed in regs
    )


def test_baseline_has_no_stale_slack(coverage: dict[str, dict]):
    """Behobene Verstoesse muessen die Baseline enger ziehen.

    Verhindert, dass eine grosszuegige Baseline neue Regressionen maskiert:
    sobald eine View weniger Verstoesse hat als ihre Baseline erlaubt, ist die
    Baseline zu locker und muss auf den Ist-Wert gesenkt werden.
    """
    stale = {
        view: (rec["violations"], BASELINE[view])
        for view, rec in coverage.items()
        if view in BASELINE and rec["violations"] < BASELINE[view]
    }
    assert not stale, (
        "Baseline zu locker (bitte auf Ist-Wert senken): "
        + ", ".join(f"{v}: ist {i} < Baseline {b}" for v, (i, b) in stale.items())
    )


def test_baseline_matches_discovered_views():
    """Jede no-arg View muss eine Baseline haben (neue Views nicht vergessen)."""
    discovered = set(discover_views())
    missing = discovered - set(BASELINE)
    assert not missing, f"Views ohne Baseline-Eintrag: {sorted(missing)}"
