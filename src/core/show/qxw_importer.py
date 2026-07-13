"""QLC+ .qxw workspace importer.

Returns a dictionary with fixtures, functions and virtual_console layout.
Errors are caught and reported - never raises.
"""
from __future__ import annotations
import os
import xml.etree.ElementTree as ET


# QLC+ XML uses default namespace - we just strip it out.
def _strip_ns(tag: str) -> str:
    if '}' in tag:
        return tag.split('}', 1)[1]
    return tag


def _walk(elem: ET.Element):
    yield elem
    for c in elem:
        yield from _walk(c)


def import_qxw(path: str) -> dict:
    """Parse a QLC+ .qxw file. Returns dict with keys:
       'ok': bool, 'message': str,
       'fixtures': list of dicts, 'functions': list of dicts,
       'virtual_console': dict,
       'skipped_fixtures': list of dicts ({'label', 'reason'}).

    FIMP-04: Ein einzelnes defektes Zahlenfeld (z.B. Address='notanumber')
    verwirft das betroffene Fixture NICHT mehr still. Stattdessen wird es mit
    Grund in ``skipped_fixtures`` gesammelt; die Erfolgsmeldung listet die
    übersprungenen Fixtures auf und zählt nur die tatsächlich importierten.
    """
    result = {
        "ok": False,
        "message": "",
        "fixtures": [],
        "functions": [],
        "virtual_console": {},
        "skipped_fixtures": [],
    }
    if not os.path.exists(path):
        result["message"] = f"Datei nicht gefunden: {path}"
        return result
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        result["message"] = f"XML-Parse-Fehler: {e}"
        return result
    except Exception as e:
        result["message"] = f"Lese-Fehler: {e}"
        return result

    root = tree.getroot()
    # Walk through engine + virtualconsole sections
    fixtures = []
    functions = []
    skipped_fixtures = []
    vc = {}

    for el in _walk(root):
        tag = _strip_ns(el.tag)
        if tag == "Fixture":
            try:
                fixtures.append(_parse_fixture(el))
            except Exception as e:
                label = _fixture_label(el)
                reason = str(e)
                print(f"[qxw_importer] fixture '{label}' skipped: {reason}")
                skipped_fixtures.append({"label": label, "reason": reason})
        elif tag == "Function":
            fn = _parse_function(el)
            if fn is not None:
                functions.append(fn)
        elif tag == "VirtualConsole":
            vc = _parse_virtual_console(el)

    result["ok"] = True
    message = (
        f"Importiert: {len(fixtures)} Fixtures, {len(functions)} Funktionen, "
        f"{len(vc.get('widgets', []))} VC-Widgets"
    )
    if skipped_fixtures:
        message += (
            f"\n{len(skipped_fixtures)} Fixture(s) übersprungen (defekte Werte):"
        )
        for s in skipped_fixtures:
            message += f"\n  - {s['label']}: {s['reason']}"
    result["message"] = message
    result["fixtures"] = fixtures
    result["functions"] = functions
    result["virtual_console"] = vc
    result["skipped_fixtures"] = skipped_fixtures
    return result


# ── Element parsers ────────────────────────────────────────────────────────

def _child_text(el: ET.Element, name: str, default: str = "") -> str:
    for c in el:
        if _strip_ns(c.tag) == name:
            return (c.text or "").strip()
    return default


def _fixture_label(el: ET.Element) -> str:
    """Best-effort human label for a Fixture element (for skip reporting).
    Uses only text lookups that never raise, so it works even when the
    fixture is being skipped because a numeric field is broken."""
    name = _child_text(el, "Name", "")
    model = _child_text(el, "Model", "")
    fid = _child_text(el, "ID", "")
    label = name or model or (f"ID {fid}" if fid else "") or "Fixture"
    return label


def _int_field(el: ET.Element, name: str, default: str = "0", offset: int = 0) -> int:
    """Parse a numeric child field, raising a descriptive ValueError on bad
    input so the caller can record *which* field of *which* fixture failed
    (FIMP-04) instead of silently dropping the whole fixture."""
    raw = _child_text(el, name, default)
    try:
        return int(raw) + offset
    except (TypeError, ValueError):
        raise ValueError(f"Feld {name!r} ist keine Zahl: {raw!r}")


def _parse_fixture(el: ET.Element) -> dict:
    """Parse a single <Fixture>. Raises ValueError on a broken numeric field;
    the caller (:func:`import_qxw`) collects the reason in ``skipped_fixtures``."""
    manufacturer = _child_text(el, "Manufacturer", "")
    model = _child_text(el, "Model", "")
    mode = _child_text(el, "Mode", "")
    name = _child_text(el, "Name", model or "Fixture")
    fid = _int_field(el, "ID", "0")
    univ = _int_field(el, "Universe", "0", 1)  # QLC+ universe is 0-based
    address = _int_field(el, "Address", "0", 1)  # 0-based -> 1-based
    channels = _int_field(el, "Channels", "1")
    return {
        "fid": fid,
        "label": name,
        "manufacturer_name": manufacturer,
        "fixture_name": model,
        "mode_name": mode,
        "universe": univ,
        "address": address,
        "channel_count": channels,
    }


def _parse_function(el: ET.Element) -> dict | None:
    try:
        fid = int(el.get("ID", "0"))
        ftype = el.get("Type", "Scene")
        name = el.get("Name", "")
        result = {
            "id": fid,
            "type": ftype,
            "name": name,
        }
        # Capture all child values for downstream conversion
        values = []
        for c in el:
            ctag = _strip_ns(c.tag)
            if ctag == "Value":
                values.append((c.get("Channel", ""), c.text or ""))
            elif ctag == "FixtureVal":
                result.setdefault("fixture_values", []).append({
                    "fid": int(c.get("ID", "0")),
                    "values": c.text or "",
                })
            elif ctag == "Speed":
                result["speed"] = c.attrib
            elif ctag == "Step":
                result.setdefault("steps", []).append(dict(c.attrib))
        if values:
            result["values"] = values
        return result
    except Exception as e:
        print(f"[qxw_importer] function parse error: {e}")
        return None


def _parse_virtual_console(el: ET.Element) -> dict:
    widgets = []
    try:
        for c in _walk(el):
            ctag = _strip_ns(c.tag)
            if ctag in ("Button", "Slider", "XYPad", "Label", "Frame",
                        "CueList", "SoloFrame", "SpeedDial"):
                w = {
                    "kind": ctag,
                    "caption": c.get("Caption", ""),
                }
                # Position/size if present
                for cc in c:
                    cctag = _strip_ns(cc.tag)
                    if cctag == "WindowState":
                        w["x"] = int(cc.get("X", "0"))
                        w["y"] = int(cc.get("Y", "0"))
                        w["w"] = int(cc.get("Width", "60"))
                        w["h"] = int(cc.get("Height", "60"))
                widgets.append(w)
    except Exception as e:
        print(f"[qxw_importer] vc parse error: {e}")
    return {"widgets": widgets}
