"""DOC-60: die Anleitung „Große Bühnen-Show: Effekte selbst bauen" und ihre
Bilder passen zusammen.

Die Bilder entstehen mit ``tools/anleitungsbilder.py buehnen_effekte`` (die
3D-GIFs nur am echten Bildschirm). Das Gate kann sie nicht neu bauen; es
haelt fest, was ohne GPU pruefbar ist:

* jedes Bild aus dem Manifest liegt im Ordner, ist eine Szene des Moduls und
  in der Anleitung eingebunden — und jeder Bild-Link zeigt auf eine Datei,
* jede 3D-Szene ist ``braucht_gpu`` (offscreen sonst schwarz),
* die GIFs bleiben unter der harten Grenze des Werkzeugs,
* die Knopf- und Feldnamen, die die Anleitung fett nennt und die die Szenen
  bedienen, stehen so im Quelltext der Oberflaeche.
"""
from __future__ import annotations

import json
import os
import re
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "tools"))

from anleitungsbilder import runner  # noqa: E402

_ORDNER = os.path.join(_REPO, "docs", "anleitung_buehnen_show")
_IMG = os.path.join(_ORDNER, "img_effekte")
_ANLEITUNG = os.path.join(_ORDNER, "ANLEITUNG.md")


def _text() -> str:
    with open(_ANLEITUNG, encoding="utf-8") as f:
        return f.read()


def _links() -> set[str]:
    return set(re.findall(r"!\[[^\]]*\]\(img_effekte/([^)]+)\)", _text()))


def test_szenen_zielen_auf_den_ordner_und_3d_braucht_gpu():
    szenen, ziel = runner.lade_szenen("buehnen_effekte")
    assert ziel == "docs/anleitung_buehnen_show/img_effekte"
    for s in szenen:
        if s.name.endswith("_3d") or s.name.startswith("21_3d"):
            assert s.braucht_gpu, s.name
        else:
            assert not s.braucht_gpu, s.name


def test_manifest_dateien_szenen_und_anleitung_decken_sich():
    with open(os.path.join(_IMG, "bilder.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    im_manifest = {b["datei"] for b in manifest["bilder"]}
    szenen, _ziel = runner.lade_szenen("buehnen_effekte")
    assert im_manifest == {s.datei for s in szenen}
    vorhanden = {n for n in os.listdir(_IMG) if n != "bilder.json"}
    assert vorhanden == im_manifest
    assert _links() == im_manifest


def test_manifest_ohne_private_pfade():
    with open(os.path.join(_IMG, "bilder.json"), encoding="utf-8") as f:
        text = f.read()
    assert "/home/" not in text and "/tmp/" not in text and ":\\\\" not in text


def test_gifs_unter_der_grenze():
    for name in os.listdir(_IMG):
        if name.endswith(".gif"):
            assert os.path.getsize(os.path.join(_IMG, name)) <= runner.GIF_LIMIT, name


def _quelle(*pfade) -> str:
    teile = []
    for p in pfade:
        with open(os.path.join(_REPO, p), encoding="utf-8") as f:
            teile.append(f.read())
    return "\n".join(teile)


def test_bedien_namen_stehen_so_im_code():
    """Was die Anleitung als Knopf/Feld/Eintrag nennt, gibt es wirklich."""
    code = _quelle(
        "src/ui/views/programmer_view.py", "src/ui/views/rgb_matrix_view.py",
        "src/ui/views/efx_view.py", "src/ui/views/chaser_editor.py",
        "src/ui/views/snap_file_panel.py", "src/ui/views/virtual_console_view.py",
        "src/ui/virtualconsole/vc_button.py", "src/ui/virtualconsole/vc_canvas.py",
        "src/ui/virtualconsole/target_list_editor.py",
        "src/ui/visualizer/visualizer_window.py", "src/ui/main_window.py",
        "src/core/engine/rgb_matrix_meta.py", "src/core/attr_groups.py",
        "src/core/engine/rgb_matrix.py", "src/core/engine/efx.py",
        "src/ui/widgets/fixture_tile_preview.py")
    namen = [
        "+ Neu", "💾 Speichern", "▶ Start", "Lampen-Vorschau", "Algorithmus:", "Stil:",
        "Geschwindigkeit:", "Tempo-Bus:", "Frei (nicht taktgebunden)",
        "Global (taktgleich, Standard)", "Läufer-Breite", "Breite (Pan-Hub):",
        "Höhe (Tilt-Hub):", "Zentrum Tilt:", "Geschwindigkeit (Hz):",
        "Gleichmäßig verteilt (Fächer)", "Fächer-Streuung:", "Fester Versatz pro Gerät (°)",
        "Versatz pro Gerät:", "Dimmer/Shutter mit öffnen", "Sichtbarkeit:",
        "Programmer → Szene", "Kanäle auswählen", "Name der Szene:", "+ Chaser",
        "Run Order:", "Fade In", "Hold", "↳ In Chase übernehmen", "Schließen",
        "Funktionen zum Chase hinzufügen", "Bearbeiten", "Hinzufügen",
        "Button Einstellungen", "Beschriftung:", "Aktion:", "Funktion an/aus",
        "+ Funktion/Effekt hinzufügen", "Live-Edit-Slot:", "3D Visualizer öffnen",
        "Szenen-Helligkeit", "Konzert (10%)", "Beam Opacity:", "Nebel/Haze anzeigen",
        "X-Bewegung", "✖ Clear ▾", "Programmer leeren",
    ]
    text = _text()
    fehlt_code = [n for n in namen if n not in code]
    assert not fehlt_code, fehlt_code
    fehlt_text = [n for n in namen if n.rstrip(":") not in text]
    assert not fehlt_text, fehlt_text
    # Optionen, die die Anleitung als Anzeigetext nennt (wie im Matrix-Editor)
    sys.path.insert(0, _REPO)
    from src.ui.virtualconsole.vc_effect_meta import option_label  # noqa: PLC0415
    assert option_label("center_out", "movement") == "Mitte→außen"
    assert option_label("center", "origin") == "Mitte"


def test_effekt_namen_der_szenen_stehen_in_der_anleitung():
    from anleitungsbilder import szenen_buehnen_effekte as e  # noqa: PLC0415
    text = _text()
    for name in (e.LAUF, e.WELLE, e.SCHWENK, e.STROBE, e.LASER, e.LASER_L, e.LASER_R):
        assert f"`{name}`" in text, name
    for beschriftung, funktion, slot in e.VC_KNOEPFE:
        assert f"| {beschriftung} | {funktion} | {slot} |" in text, beschriftung
