"""Crash-/Session-Log ernten und als Loop-Bug-Intake ausgeben (TOOLS-CRASHINTAKE).

``%APPDATA%/LightOS/crash.log`` wächst still vor sich hin (bei David 1,3 MB) und
wurde von KEINEM Werkzeug gelesen — echte Abstürze und UI-Freezes aus Davids
Sitzungen kamen nie im Backlog an. Dieses Skript liest das Log rückwärts entlang
der Sitzungs-Marker, dedupliziert die Crash-Signaturen und gibt einen fertigen
Report im ``/lightos-loop``-Intake-Format aus.

    tools/collect_crash_report.py                 # Report über alle Sitzungen
    tools/collect_crash_report.py --sessions 5    # nur die letzten 5 Sitzungen
    tools/collect_crash_report.py --count-only    # "N neue Signaturen" (Statuszeile)
    tools/collect_crash_report.py --mark-seen     # Signaturen als gesehen ablegen
    tools/collect_crash_report.py --json          # maschinenlesbar

**Was als Befund zählt:** ungefangene Python-Exceptions und erkannte UI-Freezes.
Standby/Resume (``WATCHDOG: System-Standby``) ist ausdrücklich KEIN Befund — der
Watchdog kennzeichnet das selbst als Nicht-Freeze, und es als Bug zu melden
würde den Intake mit Schlafmodus-Rauschen füllen.

Die Marker-Formate werden NICHT hier dupliziert, sondern aus
``src.core.crash_logging`` abgeleitet (dieselbe Quelle, die sie schreibt) —
ändert sich dort ein Präfix, folgt der Parser mit.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.core import crash_logging as _cl          # noqa: E402
from src.core.paths import app_data_dir            # noqa: E402


def _marker_prefix(text: str) -> str:
    """Stabiles Präfix einer Marker-Zeile — bis zum ersten Zeitstempel bzw.
    Platzhalter. So bleibt der Parser an die schreibende Quelle gekoppelt."""
    line = text.strip().splitlines()[0] if text.strip() else ""
    cut = re.split(r"\d{4}-\d{2}-\d{2}T|\{|\(", line, maxsplit=1)[0]
    return cut.rstrip()


# Aus den echten Schreibfunktionen abgeleitet (keine zweite Format-Quelle).
P_STARTED = _marker_prefix(_cl.session_banner(version="?", pid=0))
P_CLEAN = _marker_prefix(_cl.clean_exit_marker())
P_FATAL = _marker_prefix(_cl.fatal_exit_marker())
P_UNCLEAN = _marker_prefix(_cl.previous_crash_notice(None))
P_FREEZE = _marker_prefix(_cl.freeze_header(0.0))
P_SUSPEND = _marker_prefix(_cl.suspend_notice(0.0))
P_EXC = "=== Python Exception"

TS = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")
# Frame-Zeile in ZWEI Formaten:
#   Traceback:     File "<pfad>", line <n>, in <name>
#   faulthandler:  File "<pfad>", line <n> in <name>     (Freeze-Dumps, KEIN Komma)
# Nur eines von beiden zu kennen kostet still die halbe Auswertung — die
# Freeze-Stacks kommen ausschliesslich in der zweiten Form.
FRAME = re.compile(r'^\s+File "(?P<file>[^"]+)", line (?P<line>\d+)'
                   r'(?:,? in (?P<fn>.+))?$')
# Abschliessende Exception-Zeile: "ExcType: Meldung" (nicht eingerückt).
EXC_LINE = re.compile(r"^(?P<type>[A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning))"
                      r"(?::\s*(?P<msg>.*))?$")
FREEZE_SECS = re.compile(r"\((\d+)s ohne Event-Loop\)")


@dataclass
class Finding:
    kind: str                 # "exception" | "freeze"
    signature: str
    exc_type: str = ""
    message: str = ""
    top_src_frame: str = ""   # oberster Frame AUS src/ (die interessante Stelle)
    deepest_frame: str = ""
    count: int = 0
    first_ts: str = ""
    last_ts: str = ""
    sessions: set = field(default_factory=set)
    sample: list = field(default_factory=list)


def _is_src_frame(path: str) -> bool:
    p = path.replace("\\", "/").lower()
    return "/src/" in p or p.endswith("/main.py")


def _is_test_frame(path: str) -> bool:
    """Stammt der Frame aus der Testsuite? Die pytest-Laeufe schreiben in
    DASSELBE crash.log wie die App — mehrere Tests werfen absichtlich (z. B.
    ``ValueError("kaputt")``). Ohne Filter besteht der Intake zum grossen Teil
    aus diesen gewollten Fehlern und begraebt die echten."""
    p = path.replace("\\", "/").lower()
    return "/tests/" in p or os.path.basename(p).startswith("test_")


def _short(path: str) -> str:
    p = path.replace("\\", "/")
    i = p.lower().rfind("/src/")
    if i >= 0:
        return p[i + 1:]
    return os.path.basename(p)


def parse_log(text: str, include_tests: bool = False) -> list[Finding]:
    """Zerlegt den Log-Text in deduplizierte Befunde. Reine Funktion — testbar
    ohne Dateisystem.

    ``include_tests`` nimmt auch Fehler auf, die aus der Testsuite stammen —
    Default aus, s. :func:`_is_test_frame`."""
    lines = text.splitlines()
    findings: dict[str, Finding] = {}
    session_idx = 0
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.startswith(P_STARTED):
            session_idx += 1
            i += 1
            continue
        if line.startswith(P_EXC):
            ts = (TS.search(line).group(1) if TS.search(line) else "")
            block: list[str] = []
            i += 1
            while i < n and not lines[i].startswith("=== "):
                block.append(lines[i])
                i += 1
            _add_exception(findings, block, ts, session_idx, include_tests)
            continue
        if line.startswith(P_FREEZE):
            ts = (TS.search(line).group(1) if TS.search(line) else "")
            m = FREEZE_SECS.search(line)
            secs = m.group(1) if m else "?"
            block = []
            i += 1
            while i < n and not lines[i].startswith("=== "):
                block.append(lines[i])
                i += 1
            _add_freeze(findings, block, ts, secs, session_idx, include_tests)
            continue
        i += 1
    out = list(findings.values())
    out.sort(key=lambda f: (-f.count, f.signature))
    return out


def _record(findings: dict, sig: str, make, ts: str, session_idx: int, sample: list):
    f = findings.get(sig)
    if f is None:
        f = make()
        f.sample = sample[:24]
        f.first_ts = ts
        findings[sig] = f
    f.count += 1
    f.last_ts = ts or f.last_ts
    if not f.first_ts:
        f.first_ts = ts
    f.sessions.add(session_idx)


def _add_exception(findings: dict, block: list[str], ts: str, session_idx: int,
                   include_tests: bool = False):
    frames = []
    exc_type, message = "", ""
    for ln in block:
        m = FRAME.match(ln)
        if m:
            frames.append((m.group("file"), int(m.group("line")), m.group("fn") or ""))
            continue
        s = ln.strip()
        if not s or s.startswith(("Traceback", "^", "~", "|")):
            continue
        m2 = EXC_LINE.match(s)
        if m2:
            exc_type, message = m2.group("type"), (m2.group("msg") or "").strip()
    if not frames and not exc_type:
        return
    if not include_tests and any(_is_test_frame(f[0]) for f in frames):
        return
    deepest = frames[-1] if frames else ("", 0, "")
    src_frames = [f for f in frames if _is_src_frame(f[0])]
    top_src = src_frames[-1] if src_frames else deepest
    # Signatur wie crash_logging.exc_signature: Typ@datei:zeile des UNTERSTEN
    # Frames — derselbe Sturm bekommt denselben Schlüssel. OHNE Frames (z. B. der
    # QtWebEngine-Renderabsturz, der nur eine Meldung liefert) waere "@:0" fuer
    # jeden solchen Fall gleich; dann traegt die Meldung die Unterscheidung.
    if frames:
        sig = f"{exc_type or 'Unbekannt'}@{os.path.basename(deepest[0])}:{deepest[1]}"
    else:
        sig = f"{exc_type or 'Unbekannt'}@ohne-Traceback: {message[:60]}".rstrip(": ")
    _record(findings, sig,
            lambda: Finding(kind="exception", signature=sig, exc_type=exc_type,
                            message=message,
                            top_src_frame=f"{_short(top_src[0])}:{top_src[1]}"
                                          + (f" in {top_src[2]}" if top_src[2] else ""),
                            deepest_frame=f"{_short(deepest[0])}:{deepest[1]}"),
            ts, session_idx, block)


def _gui_thread_frames(block: list[str]) -> list[tuple[str, int, str]]:
    """Frames des EINGEFRORENEN Threads aus einem faulthandler-Dump.

    Der Dump listet alle Threads. Der GUI-Thread ist der **unbenannte**
    (``Thread 0x... (most recent call first):`` ohne ``[Name]``) — die benannten
    sind Watchdog, Audio, DMX, MIDI usw. und laufen bei einem UI-Freeze
    definitionsgemaess weiter. Ohne diese Unterscheidung zeigt die Signatur auf
    ``main.py`` im FreezeWatchdog, also auf die Stelle, die den Freeze MELDET
    statt auf die, die ihn VERURSACHT.
    """
    sections: list[tuple[bool, list]] = []
    named = True
    for ln in block:
        if ln.startswith(("Current thread 0x", "Thread 0x")):
            named = "[" in ln
            sections.append((named, []))
            continue
        m = FRAME.match(ln)
        if m and sections:
            sections[-1][1].append(
                (m.group("file"), int(m.group("line")), m.group("fn") or ""))
    unnamed = [frames for is_named, frames in sections if not is_named and frames]
    if unnamed:
        return unnamed[0]
    return [f for _n, frames in sections for f in frames]


def _add_freeze(findings: dict, block: list[str], ts: str, secs: str,
                session_idx: int, include_tests: bool = False):
    frames = _gui_thread_frames(block)
    if not include_tests and any(_is_test_frame(f[0]) for f in frames):
        return
    top = ""
    for path, lineno, fn in frames:
        if _is_src_frame(path):
            top = f"{_short(path)}:{lineno}" + (f" in {fn}" if fn else "")
            break
    sig = f"UI-FREEZE@{top.split(' in ')[0] or 'unbekannt'}"
    _record(findings, sig,
            lambda: Finding(kind="freeze", signature=sig, exc_type="UI-FREEZE",
                            message=f"{secs}s ohne Event-Loop",
                            top_src_frame=top, deepest_frame=top),
            ts, session_idx, block)


# ── Zustand: was wurde schon gemeldet? ───────────────────────────────────────
def _seen_path() -> str:
    return os.path.join(app_data_dir(), "crash_report_seen.json")


def load_seen(path: str | None = None) -> set:
    p = path or _seen_path()
    try:
        with open(p, encoding="utf-8") as fh:
            return set(json.load(fh).get("signatures", []))
    except Exception:
        return set()


def save_seen(signatures, path: str | None = None) -> None:
    p = path or _seen_path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"signatures": sorted(signatures)}, fh, indent=1)
    os.replace(tmp, p)


def format_report(findings: list[Finding], seen: set) -> str:
    if not findings:
        return "Keine Abstürze oder UI-Freezes im Log."
    neu = [f for f in findings if f.signature not in seen]
    out = [
        f"# Crash-Intake — {len(findings)} Signatur(en), davon {len(neu)} neu",
        "",
        "Kopiervorlage für `/lightos-loop` (eine Signatur = ein Bug-Report):",
        "",
    ]
    for f in findings:
        mark = "🆕 " if f.signature not in seen else ""
        out.append(f"## {mark}{f.signature}  ({f.count}×, {len(f.sessions)} Sitzung(en))")
        if f.kind == "exception":
            out.append(f"- **Fehler:** `{f.exc_type}`"
                       + (f" — {f.message}" if f.message else ""))
        else:
            out.append(f"- **UI-Freeze:** {f.message}")
        out.append(f"- **Stelle im Code:** `{f.top_src_frame}`")
        if f.deepest_frame and f.deepest_frame != f.top_src_frame:
            out.append(f"- **Unterster Frame:** `{f.deepest_frame}`")
        out.append(f"- **Zeitraum:** {f.first_ts or '?'} … {f.last_ts or '?'}")
        out.append("")
        out.append("<details><summary>Auszug</summary>")
        out.append("")
        out.append("```")
        out.extend(f.sample)
        out.append("```")
        out.append("</details>")
        out.append("")
    return "\n".join(out)


def default_log_path() -> str:
    return os.path.join(app_data_dir(), "crash.log")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--log", default=None, help="Pfad zur crash.log (Default: AppData)")
    ap.add_argument("--sessions", type=int, default=0,
                    help="nur die letzten N Sitzungen betrachten (0 = alle)")
    ap.add_argument("--count-only", action="store_true",
                    help="nur die Zahl NEUER Signaturen ausgeben (Statuszeile)")
    ap.add_argument("--mark-seen", action="store_true",
                    help="alle gefundenen Signaturen als gemeldet ablegen")
    ap.add_argument("--json", action="store_true", help="maschinenlesbare Ausgabe")
    ap.add_argument("--include-tests", action="store_true",
                    help="auch Fehler aus der Testsuite melden (Default: aus)")
    args = ap.parse_args(argv)

    path = args.log or default_log_path()
    if not os.path.exists(path):
        print(f"Kein Crash-Log gefunden: {path}")
        return 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    if args.sessions > 0:
        parts = text.split(P_STARTED)
        if len(parts) > args.sessions:
            text = P_STARTED + P_STARTED.join(parts[-args.sessions:])

    findings = parse_log(text, include_tests=args.include_tests)
    seen = load_seen()
    neu = [f for f in findings if f.signature not in seen]

    if args.count_only:
        print(len(neu))
    elif args.json:
        print(json.dumps([{
            "kind": f.kind, "signature": f.signature, "exc_type": f.exc_type,
            "message": f.message, "top_src_frame": f.top_src_frame,
            "count": f.count, "sessions": len(f.sessions),
            "first_ts": f.first_ts, "last_ts": f.last_ts,
            "neu": f.signature not in seen,
        } for f in findings], ensure_ascii=False, indent=1))
    else:
        print(format_report(findings, seen))

    if args.mark_seen:
        save_seen(seen | {f.signature for f in findings})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
