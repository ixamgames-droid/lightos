"""QA-12 UI-Verifikations-Checklisten-Generator/-Checker.

Erzeugt eine maschinen-pruefbare Inventar-Tabelle ALLER navigierbaren no-arg
``*View``-Klassen (``src/ui/views/*.py``) UND aller Virtual-Console-Widgets
(``WIDGET_REGISTRY``). Pro Zeile werden headless-gebaute Ist-Fakten erhoben:

* **headless** — laesst sich das Widget ohne Argumente offscreen bauen?
* **Tooltip/Label** — traegt es mindestens einen beschrifteten Text/Tooltip?
* **Aktion/Signal** — hat es eine verdrahtete Aktion (Button/QAction) oder ein
  auf Klassenebene deklariertes ``Signal``?
* **Regressionstest** — Pfad der abdeckenden Testdatei (dedizierte
  ``tests/test_<modul>.py`` falls vorhanden, sonst der enumerierende Smoke).
* **Doc** — passende ``docs/components/…``-Seite, falls vorhanden.
* **Verifikationspfad** — konkreter ``pytest``-Testname ODER ``manuell``.

Discovery ist deckungsgleich mit ``tests/test_ui_smoke_enumerated`` und
``tools/audit_tooltip_coverage`` (no-arg ``*View`` + ``WIDGET_REGISTRY``).

Der Report ist ``docs/UI_VERIFICATION_CHECKLIST.md``. Die bestehende
(handgepflegte) QA-13-Sektion bleibt erhalten — nur der Block zwischen den
GENERATED-Markern wird ueberschrieben (bzw. angehaengt, wenn noch nicht da).

CLI:
  python tools/ui_verification_checklist.py           # Report schreiben/aktualisieren
  python tools/ui_verification_checklist.py --check   # nur Drift-Exit-Code (CI)

Exit 0 = Report ist aktuell / geschrieben, Exit 1 (--check) = Report driftet.
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

REPORT_PATH = REPO / "docs" / "UI_VERIFICATION_CHECKLIST.md"

BEGIN_MARK = "<!-- BEGIN GENERATED: ui_verification_checklist -->"
END_MARK = "<!-- END GENERATED: ui_verification_checklist -->"

# Verifikationspfad je Gruppe: der enumerierende Smoke deckt beide Gruppen
# maschinell ab; das ist der garantierte, ausfuehrbare Regressionsanker.
SMOKE_FILE = "tests/test_ui_smoke_enumerated.py"
VIEW_TESTNAME = "test_every_no_arg_view_builds"
WIDGET_TESTNAME = "test_every_virtual_console_widget_roundtrips"


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _required_init_args(cls) -> list:
    return [
        p for p in inspect.signature(cls).parameters.values()
        if p.default is inspect.Parameter.empty
        and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]


def discover_no_arg_views() -> dict[str, str]:
    """{modulname: klassenname} aller navigierbaren no-arg ``*View``-Klassen.

    Deckungsgleich mit ``test_ui_smoke_enumerated._discover_no_arg_views`` und
    ``audit_tooltip_coverage.discover_views``.
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


def discover_vc_widgets() -> dict[str, type]:
    """{registry_typname: klasse} aus ``WIDGET_REGISTRY`` (VC-Widgets)."""
    from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY
    return dict(WIDGET_REGISTRY)


def _has_label_or_tooltip(widget) -> bool:
    """True, wenn irgendein Kind einen Tooltip traegt oder ein Label Text hat."""
    from PySide6.QtWidgets import QAbstractButton, QLabel, QWidget

    for child in widget.findChildren(QWidget):
        try:
            if (child.toolTip() or "").strip():
                return True
        except RuntimeError:
            continue
    for lbl in widget.findChildren(QLabel):
        try:
            if (lbl.text() or "").strip():
                return True
        except RuntimeError:
            continue
    for btn in widget.findChildren(QAbstractButton):
        try:
            if (btn.text() or "").strip():
                return True
        except RuntimeError:
            continue
    return False


def _has_action_or_signal(cls, widget) -> bool:
    """True bei verdrahteter Aktion (Button/QAction) oder Klassen-``Signal``."""
    from PySide6.QtCore import Signal
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QAbstractButton

    for klass in inspect.getmro(cls):
        for value in vars(klass).values():
            if isinstance(value, Signal):
                return True
    if widget.findChildren(QAbstractButton):
        return True
    if widget.findChildren(QAction):
        return True
    return False


def _doc_for(rel_dir: str, stem: str) -> str:
    """Relativer Doc-Pfad, falls die Seite existiert, sonst leer."""
    candidate = REPO / "docs" / "components" / rel_dir / f"{stem}.md"
    if candidate.exists():
        return f"docs/components/{rel_dir}/{stem}.md"
    return ""


def _regression_test_for(module_stem: str) -> str:
    """Dedizierte ``tests/test_<modul>.py`` falls vorhanden, sonst der Smoke."""
    dedicated = REPO / "tests" / f"test_{module_stem}.py"
    if dedicated.exists():
        return f"tests/test_{module_stem}.py"
    return SMOKE_FILE


def _build_view_row(module_name: str, class_name: str) -> dict:
    app = _app()
    cls = getattr(importlib.import_module(f"src.ui.views.{module_name}"), class_name)
    headless = True
    has_labels = False
    has_action = False
    error = ""
    widget = None
    try:
        widget = cls()
        has_labels = _has_label_or_tooltip(widget)
        has_action = _has_action_or_signal(cls, widget)
    except Exception as exc:  # noqa: BLE001 — Ist-Zustand bewusst festhalten
        headless = False
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if widget is not None:
            widget.close()
            widget.deleteLater()
        app.processEvents()
    return {
        "kind": "view",
        "key": module_name,
        "label": f"{module_name}.py",
        "cls": class_name,
        "headless": headless,
        "labels": has_labels,
        "action": has_action,
        "regtest": _regression_test_for(module_name),
        "doc": _doc_for("views", module_name),
        "verify": VIEW_TESTNAME if headless else "manuell",
        "error": error,
    }


def _build_widget_row(type_name: str, cls: type) -> dict:
    app = _app()
    module_stem = cls.__module__.rsplit(".", 1)[-1]
    headless = True
    has_labels = False
    has_action = False
    error = ""
    widget = None
    try:
        widget = cls()
        has_labels = _has_label_or_tooltip(widget)
        has_action = _has_action_or_signal(cls, widget)
    except Exception as exc:  # noqa: BLE001
        headless = False
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if widget is not None:
            widget.close()
            widget.deleteLater()
        app.processEvents()
    return {
        "kind": "widget",
        "key": type_name,
        "label": type_name,
        "cls": module_stem,
        "headless": headless,
        "labels": has_labels,
        "action": has_action,
        "regtest": _regression_test_for(module_stem),
        "doc": _doc_for("vc", module_stem),
        "verify": WIDGET_TESTNAME if headless else "manuell",
        "error": error,
    }


def build_rows() -> tuple[list[dict], list[dict]]:
    """(view_rows, widget_rows) mit headless-gebauten Ist-Fakten je Eintrag."""
    view_rows = [
        _build_view_row(mod, cls)
        for mod, cls in sorted(discover_no_arg_views().items())
    ]
    widget_rows = [
        _build_widget_row(name, cls)
        for name, cls in sorted(discover_vc_widgets().items())
    ]
    return view_rows, widget_rows


def _yn(value: bool) -> str:
    return "ja" if value else "nein"


def _cell(path: str) -> str:
    return f"`{path}`" if path else "—"


def render_block(view_rows: list[dict], widget_rows: list[dict]) -> str:
    view_ok = sum(1 for r in view_rows if r["headless"])
    widget_ok = sum(1 for r in widget_rows if r["headless"])
    lines = [
        BEGIN_MARK,
        "<!-- Auto-generiert von tools/ui_verification_checklist.py — NICHT von Hand editieren. -->",
        "",
        "## Maschinen-Inventar (QA-12)",
        "",
        "Erzeugt von `tools/ui_verification_checklist.py`, abgesichert durch",
        "`tests/test_ui_verification_checklist.py`. Jede Zeile wird headless",
        "(offscreen) gebaut; die Spalten unten sind der geprueft protokollierte",
        "Ist-Zustand. Eine NEUE no-arg View oder ein NEUES `WIDGET_REGISTRY`-Widget",
        "fehlt zunaechst hier und macht das Gate rot (Schutz gegen Doku-Drift).",
        "",
        "Spalten: **headless** = ohne Argumente offscreen baubar · "
        "**Tooltip/Label** = mind. ein beschrifteter Text/Tooltip · "
        "**Aktion/Signal** = Button/`QAction`/Klassen-`Signal` vorhanden · "
        "**Regressionstest** = abdeckende Testdatei · **Doc** = Komponentenseite · "
        "**Verifikationspfad** = ausfuehrbarer `pytest`-Testname ODER `manuell`.",
        "",
        f"**Stand:** {len(view_rows)} no-arg Views ({view_ok} headless baubar), "
        f"{len(widget_rows)} VC-Widgets ({widget_ok} headless baubar).",
        "",
        "### Views (`src/ui/views/*.py`, no-arg `*View`)",
        "",
        "| Modul | Klasse | headless | Tooltip/Label | Aktion/Signal | Regressionstest | Doc | Verifikationspfad |",
        "|---|---|:--:|:--:|:--:|---|---|---|",
    ]
    for r in view_rows:
        lines.append(
            f"| `{r['label']}` | `{r['cls']}` | {_yn(r['headless'])} | "
            f"{_yn(r['labels'])} | {_yn(r['action'])} | {_cell(r['regtest'])} | "
            f"{_cell(r['doc'])} | `{r['verify']}` |"
        )
    lines += [
        "",
        "### Virtual Console (`WIDGET_REGISTRY`)",
        "",
        "| Registry-Typ | Modul | headless | Tooltip/Label | Aktion/Signal | Regressionstest | Doc | Verifikationspfad |",
        "|---|---|:--:|:--:|:--:|---|---|---|",
    ]
    for r in widget_rows:
        lines.append(
            f"| `{r['label']}` | `{r['cls']}.py` | {_yn(r['headless'])} | "
            f"{_yn(r['labels'])} | {_yn(r['action'])} | {_cell(r['regtest'])} | "
            f"{_cell(r['doc'])} | `{r['verify']}` |"
        )
    failed = [r for r in (view_rows + widget_rows) if not r["headless"]]
    if failed:
        lines += ["", "### Nicht headless baubar (Fehlerbild)", ""]
        for r in failed:
            lines.append(f"- `{r['key']}` (`{r['cls']}`): {r['error']}")
    lines += ["", END_MARK]
    return "\n".join(lines)


def _default_preamble() -> str:
    """Kopf fuer eine frische Datei (falls noch keine existiert)."""
    return (
        "# UI-Verifikationscheckliste\n\n"
        "Diese Datei kombiniert eine handgepflegte Uebersicht mit einem\n"
        "auto-generierten Maschinen-Inventar (QA-12). Der Block zwischen den\n"
        "GENERATED-Markern wird von `tools/ui_verification_checklist.py`\n"
        "geschrieben — dort NICHT von Hand editieren.\n\n"
    )


def compose(existing: str | None, block: str) -> str:
    """Fuegt/ersetzt den GENERATED-Block, ohne Handgeschriebenes zu verlieren."""
    if existing is None:
        return _default_preamble() + block + "\n"
    if BEGIN_MARK in existing and END_MARK in existing:
        head = existing.split(BEGIN_MARK, 1)[0].rstrip("\n")
        tail = existing.split(END_MARK, 1)[1].lstrip("\n")
        parts = [head, "", block]
        if tail.strip():
            parts += ["", tail.rstrip("\n")]
        return "\n".join(parts) + "\n"
    return existing.rstrip("\n") + "\n\n" + block + "\n"


def parse_block(text: str) -> dict[str, dict]:
    """Liest den GENERATED-Block zu {key: {headless, verify, kind}} zurueck.

    Erlaubt dem Gate-Test, die dokumentierten Werte gegen den echten Bau zu
    pruefen, ohne die Render-Logik zu duplizieren.
    """
    if BEGIN_MARK not in text or END_MARK not in text:
        return {}
    block = text.split(BEGIN_MARK, 1)[1].split(END_MARK, 1)[0]
    rows: dict[str, dict] = {}
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 8:
            continue
        key = cells[0].strip("`").strip()
        if not key or key in ("Modul", "Registry-Typ"):
            continue
        # Views: erster Cell endet auf ".py" -> Modul-Stem als Key.
        norm_key = key[:-3] if key.endswith(".py") else key
        rows[norm_key] = {
            "headless": cells[2] == "ja",
            "verify": cells[7].strip("`"),
        }
    return rows


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    check_only = "--check" in argv
    view_rows, widget_rows = build_rows()
    block = render_block(view_rows, widget_rows)
    existing = REPORT_PATH.read_text(encoding="utf-8") if REPORT_PATH.exists() else None
    composed = compose(existing, block)
    if check_only:
        if existing != composed:
            print("DRIFT — docs/UI_VERIFICATION_CHECKLIST.md ist nicht aktuell.")
            print("  Neu erzeugen: python tools/ui_verification_checklist.py")
            return 1
        print("OK — Checkliste ist aktuell.")
        return 0
    REPORT_PATH.write_text(composed, encoding="utf-8")
    print(f"Report geschrieben: {REPORT_PATH.relative_to(REPO)}")
    print(f"  Views:   {len(view_rows)} ({sum(r['headless'] for r in view_rows)} headless)")
    print(f"  Widgets: {len(widget_rows)} ({sum(r['headless'] for r in widget_rows)} headless)")
    failed = [r for r in view_rows + widget_rows if not r["headless"]]
    if failed:
        print("  NICHT baubar:")
        for r in failed:
            print(f"    {r['key']}: {r['error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
