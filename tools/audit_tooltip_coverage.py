"""QA-13 Tooltip-/Label-Coverage-Audit fuer interaktive Steuerelemente.

Baut jede no-arg ``*View`` (``src/ui/views/*.py``) headless und durchlaeuft
``findChildren(QAbstractButton)``. Ein Button gilt als **Verstoss**, wenn sein
``text()`` UND sein ``toolTip()`` beide leer sind — ein solcher Button traegt
weder sichtbare Beschriftung noch Hover-Hinweis und ist damit weder fuer
sehende noch fuer Screenreader-Nutzer benennbar.

Der Audit fordert NICHT hart 0 Verstoesse (das waere heute rot). Stattdessen
fuehrt ``BASELINE`` eine dokumentierte Allowlist je View. ``regressions()``
meldet nur Views, deren Verstoss-Zahl die Baseline UEBERSTEIGT — d. h. ein NEU
hinzugefuegter textloser Button ohne Tooltip macht das Gate rot
(Regressionsschutz), waehrend das Beheben bestehender Verstoesse gruen bleibt.

CLI:
  python tools/audit_tooltip_coverage.py            # Report -> stdout + docs/
  python tools/audit_tooltip_coverage.py --check    # nur Exit-Code (CI)

Exit 0 = keine Regression, Exit 1 = neue textlose Buttons ohne Tooltip.
"""
from __future__ import annotations

import importlib
import inspect
import os
import pkgutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPORT_PATH = REPO / "docs" / "UI_TOOLTIP_COVERAGE.md"

# Dokumentierte Baseline/Allowlist: erlaubte Anzahl textloser Buttons OHNE
# Tooltip je View (Stand 2026-07-13). Werte sind Obergrenzen — sie duerfen nur
# SINKEN (Behebung), niemals ueberschritten werden (Regression). Fuer eine NEUE
# View gilt implizit 0: sie muss von Anfang an beschriftete/betooltippte Buttons
# haben oder bewusst hier eingetragen werden.
BASELINE: dict[str, int] = {
    "audio_input_view": 0,
    "bpm_generator_view": 0,
    "bpm_manager_view": 1,
    "channel_groups_view": 1,
    "curve_library_view": 0,
    "dmx_monitor_view": 0,
    "efx_view": 0,
    "fixture_group_view": 0,
    "function_manager_view": 0,
    "laser_view": 0,
    "live_view": 4,
    "midi_view": 1,
    "music_view": 1,
    "output_view": 0,
    "palette_view": 7,
    "patch_view": 1,
    "playback_view": 1,
    "preset_browser_view": 1,
    "programmer_view": 14,
    "rgb_matrix_view": 3,
    "show_manager_view": 0,
    "simple_desk": 0,
    "snapshots_view": 0,
    "virtual_console_view": 0,
}


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _required_init_args(cls) -> list:
    return [
        p for p in inspect.signature(cls).parameters.values()
        if p.default is inspect.Parameter.empty
        and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]


def discover_views() -> dict[str, str]:
    """{modulname: klassenname} aller navigierbaren no-arg ``*View``-Klassen.

    Deckungsgleich mit ``tests/test_ui_smoke_enumerated._discover_no_arg_views``:
    Klasse endet auf ``View``, ist ``QWidget``-Subklasse und braucht keine
    Pflicht-Konstruktorargumente. Helfer-Widgets (DmxGrid, TimelineCanvas) und
    Dialoge (FunctionSelectorDialog) fallen bewusst raus.
    """
    from PySide6.QtWidgets import QWidget
    from src.ui import views

    found: dict[str, str] = {}
    for info in pkgutil.iter_modules(views.__path__):
        if info.name.startswith("_"):
            continue
        module_name = f"{views.__name__}.{info.name}"
        module = importlib.import_module(module_name)
        for name, cls in inspect.getmembers(module, inspect.isclass):
            if (
                cls.__module__ == module_name
                and name.endswith("View")
                and not name.startswith("_")
                and issubclass(cls, QWidget)
                and not _required_init_args(cls)
            ):
                found[info.name] = name
    return found


def _button_violations(widget) -> list[str]:
    """Kennungen der Buttons mit leerem ``text()`` UND leerem ``toolTip()``."""
    from PySide6.QtWidgets import QAbstractButton

    offenders: list[str] = []
    for btn in widget.findChildren(QAbstractButton):
        try:
            text = (btn.text() or "").strip()
            tip = (btn.toolTip() or "").strip()
        except RuntimeError:
            continue  # Widget waehrend Iteration zerstoert
        if not text and not tip:
            ident = btn.objectName() or btn.accessibleName() or "<unbenannt>"
            offenders.append(f"{type(btn).__name__}({ident})")
    return offenders


def audit() -> dict[str, dict]:
    """{modulname: {class,total,violations,offenders}} je no-arg View."""
    from PySide6.QtWidgets import QAbstractButton

    app = _app()
    result: dict[str, dict] = {}
    for module_name, class_name in sorted(discover_views().items()):
        cls = getattr(
            importlib.import_module(f"src.ui.views.{module_name}"), class_name
        )
        widget = cls()
        try:
            total = len(widget.findChildren(QAbstractButton))
            offenders = _button_violations(widget)
        finally:
            widget.close()
            widget.deleteLater()
            app.processEvents()
        result[module_name] = {
            "class": class_name,
            "total": total,
            "violations": len(offenders),
            "offenders": offenders,
        }
    return result


def regressions(result: dict[str, dict] | None = None) -> list[tuple[str, int, int]]:
    """(view, violations, baseline) fuer jede View ueber ihrer Baseline."""
    if result is None:
        result = audit()
    out: list[tuple[str, int, int]] = []
    for module_name, rec in result.items():
        allowed = BASELINE.get(module_name, 0)
        if rec["violations"] > allowed:
            out.append((module_name, rec["violations"], allowed))
    return out


def render_report(result: dict[str, dict]) -> str:
    total_views = len(result)
    total_viol = sum(r["violations"] for r in result.values())
    lines = [
        "# UI Tooltip-/Label-Coverage (QA-13)",
        "",
        "Automatisch erzeugt von `tools/audit_tooltip_coverage.py` und",
        "abgesichert durch `tests/test_tooltip_coverage.py`. Ein **Verstoss** ist",
        "ein `QAbstractButton`, dessen `text()` UND `toolTip()` beide leer sind —",
        "er ist weder sichtbar beschriftet noch per Hover/Screenreader benennbar.",
        "",
        "Das Gate fordert nicht hart 0 Verstoesse, sondern haelt die unten",
        "dokumentierte Baseline: es wird rot, sobald eine View NEUE textlose",
        "Buttons ohne Tooltip bekommt (Regressionsschutz). Bestehende Verstoesse",
        "abzubauen ist jederzeit erlaubt (Baseline in der Skript-Datei nachziehen).",
        "",
        f"**Stand:** {total_views} no-arg Views geprueft, {total_viol} Verstoesse "
        "in der aktuellen Baseline.",
        "",
        "## Uebersicht",
        "",
        "| View (`src/ui/views/…`) | Klasse | Buttons | textlos & tooltiplos | Baseline |",
        "|---|---|---:|---:|---:|",
    ]
    for module_name in sorted(result):
        rec = result[module_name]
        allowed = BASELINE.get(module_name, 0)
        lines.append(
            f"| `{module_name}.py` | `{rec['class']}` | {rec['total']} | "
            f"{rec['violations']} | {allowed} |"
        )
    lines.append("")
    lines.append("## Verstoesse im Detail")
    lines.append("")
    lines.append(
        "Pro betroffener View die Button-Kennungen (`Klasse(objectName)`), die "
        "weder Text noch Tooltip tragen — Ansatzpunkte fuer kuenftige Verbesserung."
    )
    lines.append("")
    any_detail = False
    for module_name in sorted(result):
        rec = result[module_name]
        if not rec["offenders"]:
            continue
        any_detail = True
        lines.append(f"### `{module_name}.py` ({rec['violations']})")
        lines.append("")
        for off in rec["offenders"]:
            lines.append(f"- `{off}`")
        lines.append("")
    if not any_detail:
        lines.append("_Keine — alle Buttons tragen Text oder Tooltip._")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    check_only = "--check" in argv
    result = audit()
    regs = regressions(result)
    if not check_only:
        REPORT_PATH.write_text(render_report(result), encoding="utf-8")
        print(f"Report geschrieben: {REPORT_PATH.relative_to(REPO)}")
        for module_name in sorted(result):
            rec = result[module_name]
            print(
                f"  {module_name:24s} {rec['violations']:3d} / "
                f"Baseline {BASELINE.get(module_name, 0)}"
            )
    if regs:
        print("\nREGRESSION — neue textlose Buttons ohne Tooltip:")
        for module_name, count, allowed in regs:
            print(f"  {module_name}: {count} > Baseline {allowed}")
        return 1
    print("\nOK — keine Tooltip-Regression.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
