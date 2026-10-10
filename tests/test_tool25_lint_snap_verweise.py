"""TOOL-25: Der Show-Lint erkennt VC-Knoepfe, die auf geloeschte Snaps zeigen.

Herkunft: Durchsicht einer echten Show. Ein Knopf (Aktion „Bibliothek-Snap")
zeigte auf einen Snap, der aus der Bibliothek geloescht war — der Knopf tat beim
Druecken nichts, und weder ``tools/lint_show.py`` noch das „Issues"-Banner der
App meldeten es. ``VCButton._library_snaps`` ueberspringt fehlende IDs still.

Zusaetzlich (nur Hinweis, keine Korrektur): ein Knopf mit mehreren Snaps, die
auf demselben Kanal desselben Geraets verschiedene Werte setzen — der spaetere
Snap ueberschreibt den frueheren (Beispiel: Snap 44 ueberschreibt das Farbrad).

Alle Shows hier sind kleine Attrappen als Dict bzw. temporaere Datei.
"""
from __future__ import annotations

import json
import os
import sys
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.capability import validate as V  # noqa: E402


def _snap(sid, values, name=None):
    return {"id": sid, "name": name or f"Snap {sid}", "folder": "",
            "values": {str(f): dict(a) for f, a in values.items()}}


def _knopf(caption, snap_id=None, snap_ids=(), action="LibrarySnap", **extra):
    d = {"type": "VCButton", "caption": caption, "action": action,
         "snap_id": snap_id, "snap_ids": list(snap_ids)}
    d.update(extra)
    return d


def _show(widgets, snaps=None, functions=()):
    show = {
        "version": "1.1",
        "functions": {"functions": list(functions)},
        "virtual_console": {"widgets": list(widgets)},
    }
    if snaps is not None:
        show["library"] = {"folders": [], "snaps": list(snaps)}
    return show


def _codes(findings, code):
    return [f for f in findings if f.code == code]


class SnapVerweisTest(unittest.TestCase):

    def test_geloeschter_snap_id_wird_gemeldet(self):
        show = _show([_knopf("Gruen", snap_id=23)], snaps=[_snap(5, {1: {"r": 0}})])
        treffer = _codes(V.validate_show_dict(show), "VC-SNAP-DANGLING")
        self.assertEqual(1, len(treffer), V.format_findings(treffer))
        f = treffer[0]
        self.assertEqual(V.WARNING, f.severity)
        text = f"{f.where} {f.message}"
        self.assertIn("Gruen", text)
        self.assertIn("23", text)

    def test_geloeschter_snap_in_snap_ids_wird_gemeldet(self):
        show = _show([_knopf("Mix", snap_id=5, snap_ids=[6, 99])],
                     snaps=[_snap(5, {1: {"r": 0}}), _snap(6, {2: {"g": 9}})])
        treffer = _codes(V.validate_show_dict(show), "VC-SNAP-DANGLING")
        self.assertEqual(1, len(treffer), V.format_findings(treffer))
        self.assertIn("99", treffer[0].message)
        self.assertIn("snap_ids", treffer[0].message)

    def test_vorhandene_snaps_bleiben_ruhig(self):
        show = _show([_knopf("Rot", snap_id=5, snap_ids=[6])],
                     snaps=[_snap(5, {1: {"r": 255}}), _snap(6, {2: {"g": 9}})])
        self.assertEqual([], _codes(V.validate_show_dict(show), "VC-SNAP-DANGLING"))

    def test_show_ohne_bibliotheksblock_wird_nicht_geprueft(self):
        """Alt-Shows ohne ``library`` erben beim Laden die globalen Snaps —
        welche das sind, weiss der Lint nicht. Kein Fehlalarm."""
        show = _show([_knopf("Gruen", snap_id=23)], snaps=None)
        self.assertEqual([], _codes(V.validate_show_dict(show), "VC-SNAP-DANGLING"))

    def test_veraltete_snap_id_bei_anderer_aktion_ist_inert(self):
        """Nur „LibrarySnap" liest die Snaps (VCButton._snap_binding_for_action)."""
        show = _show([_knopf("Alt", snap_id=23, action="Toggle")], snaps=[])
        self.assertEqual([], _codes(V.validate_show_dict(show), "VC-SNAP-DANGLING"))

    def test_mehrfachaktion_snap_und_funktion(self):
        """Mehrfach-Aktionen (``actions``) tragen eigene snap_id/function_id."""
        knopf = {"type": "VCButton", "caption": "Kombi", "action": "MultiAction",
                 "actions": [
                     {"type": "library_snap", "snap_id": 77},
                     {"type": "function", "function_id": 404, "mode": "on"},
                 ]}
        show = _show([knopf], snaps=[_snap(5, {1: {"r": 0}})],
                     functions=[{"id": 1, "type": "Scene", "name": "S"}])
        befunde = V.validate_show_dict(show)
        snap = _codes(befunde, "VC-SNAP-DANGLING")
        self.assertEqual(1, len(snap), V.format_findings(befunde))
        self.assertIn("77", snap[0].message)
        self.assertIn("Kombi", snap[0].where)
        fn = [f for f in _codes(befunde, "VC-DANGLING") if "404" in f.message]
        self.assertEqual(1, len(fn), V.format_findings(befunde))

    def test_knopf_im_rahmen_nennt_seite(self):
        rahmen = {"type": "VCFrame", "caption": "Himmel", "children": [
            dict(_knopf("Gruen", snap_id=23), vc_page=1)]}
        show = _show([rahmen], snaps=[_snap(5, {1: {"r": 0}})])
        treffer = _codes(V.validate_show_dict(show), "VC-SNAP-DANGLING")
        self.assertEqual(1, len(treffer))
        self.assertIn("Himmel", treffer[0].where)
        self.assertIn("Seite 2", treffer[0].where)
        self.assertIn("Gruen", treffer[0].where)

    def test_widerspruechliche_snaps_als_hinweis(self):
        show = _show([_knopf("Gelb Blau", snap_id=43, snap_ids=[44])], snaps=[
            _snap(43, {3: {"color_wheel": 40, "dimmer": 255}}),
            _snap(44, {3: {"color_wheel": 120, "dimmer": 255}, 4: {"r": 1}}),
        ])
        befunde = V.validate_show_dict(show)
        treffer = _codes(befunde, "VC-SNAP-KONFLIKT")
        self.assertEqual(1, len(treffer), V.format_findings(befunde))
        f = treffer[0]
        self.assertEqual(V.INFO, f.severity)
        self.assertIn("Gelb Blau", f.where)
        for teil in ("44", "43", "color_wheel"):
            self.assertIn(teil, f.message)
        # gleicher Wert (dimmer 255) ist kein Widerspruch
        self.assertNotIn("dimmer", f.message)
        # Hinweis blockiert das Speichern nicht
        V.assert_show_dict(show)

    def test_snaps_auf_verschiedenen_kanaelen_kein_hinweis(self):
        show = _show([_knopf("Ok", snap_id=1, snap_ids=[2])], snaps=[
            _snap(1, {3: {"color_wheel": 40}}), _snap(2, {3: {"gobo": 10}})])
        self.assertEqual([], _codes(V.validate_show_dict(show), "VC-SNAP-KONFLIKT"))

    def test_lint_show_meldet_es(self):
        """Ende-zu-Ende ueber die Datei-Ebene, die tools/lint_show.py nutzt."""
        import tempfile
        show = _show([_knopf("Gruen", snap_id=23)], snaps=[_snap(5, {1: {"r": 0}})])
        with tempfile.TemporaryDirectory() as tmp:
            pfad = os.path.join(tmp, "show.json")
            with open(pfad, "w", encoding="utf-8") as fh:
                json.dump(show, fh)
            befunde = V.validate_lshow(pfad)
        self.assertTrue(_codes(befunde, "VC-SNAP-DANGLING"))
        self.assertIn("info ", str(V.Finding(V.INFO, "X", "w", "m")))


class IssuesBannerTest(unittest.TestCase):
    """Das „Issues"-Banner (``sync.validate_and_repair``) zieht die Pruefung mit:
    haengender Snap = 'warn', Widerspruch = 'info'. Nur melden, nie reparieren."""

    def test_banner_meldet_haengenden_snap(self):
        from src.core import sync
        from src.core.engine.snap_library import get_snap_library
        lib = get_snap_library()
        alt = lib.to_dict()
        try:
            lib.from_dict({"folders": [], "snaps": [
                _snap(43, {3: {"color_wheel": 40}}),
                _snap(44, {3: {"color_wheel": 120}})]})
            layout = {"widgets": [_knopf("Gruen", snap_id=23),
                                  _knopf("Gelb Blau", snap_id=43, snap_ids=[44])]}
            state = types.SimpleNamespace(
                _vc_layout=layout, get_patched_fixtures=lambda: [],
                programmer={}, cue_stacks=[])
            issues = sync.validate_and_repair(state, fix=True)
        finally:
            lib.from_dict(alt)
        warn = [i for i in issues if i.severity == "warn" and "23" in i.message]
        self.assertEqual(1, len(warn), [str(i) for i in issues])
        self.assertIn("Gruen", warn[0].location)
        self.assertFalse(warn[0].auto_fixed)
        info = [i for i in issues if i.severity == "info" and "color_wheel" in i.message]
        self.assertEqual(1, len(info), [str(i) for i in issues])
        # nichts korrigiert
        self.assertEqual(23, layout["widgets"][0]["snap_id"])


if __name__ == "__main__":
    unittest.main()
