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
       'virtual_console': dict.
    """
    result = {
        "ok": False,
        "message": "",
        "fixtures": [],
        "functions": [],
        "virtual_console": {},
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
    vc = {}

    for el in _walk(root):
        tag = _strip_ns(el.tag)
        if tag == "Fixture":
            fx = _parse_fixture(el)
            if fx is not None:
                fixtures.append(fx)
        elif tag == "Function":
            fn = _parse_function(el)
            if fn is not None:
                functions.append(fn)
        elif tag == "VirtualConsole":
            vc = _parse_virtual_console(el)

    result["ok"] = True
    result["message"] = (
        f"Importiert: {len(fixtures)} Fixtures, {len(functions)} Funktionen, "
        f"{len(vc.get('widgets', []))} VC-Widgets"
    )
    result["fixtures"] = fixtures
    result["functions"] = functions
    result["virtual_console"] = vc
    return result


# ── Element parsers ────────────────────────────────────────────────────────

def _child_text(el: ET.Element, name: str, default: str = "") -> str:
    for c in el:
        if _strip_ns(c.tag) == name:
            return (c.text or "").strip()
    return default


def _parse_fixture(el: ET.Element) -> dict | None:
    try:
        fid = int(_child_text(el, "ID", "0"))
        manufacturer = _child_text(el, "Manufacturer", "")
        model = _child_text(el, "Model", "")
        mode = _child_text(el, "Mode", "")
        name = _child_text(el, "Name", model or "Fixture")
        univ = int(_child_text(el, "Universe", "0")) + 1  # QLC+ universe is 0-based
        address = int(_child_text(el, "Address", "0")) + 1  # 0-based -> 1-based
        channels = int(_child_text(el, "Channels", "1"))
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
    except Exception as e:
        print(f"[qxw_importer] fixture parse error: {e}")
        return None


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
