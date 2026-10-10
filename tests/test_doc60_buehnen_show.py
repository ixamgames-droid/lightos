"""DOC-60: Generator und Übersicht der großen Bühnen-Show.

Gegenstück zu ``test_doc60_buehnen_effekte_anleitung.py`` (die Bau-Anleitung)
für den Rest des Items:

* ``docs/anleitung_buehnen_show/ANLEITUNG_BUEHNEN_SHOW.md`` und ``img/``:
  Manifest, Szenen, Dateien und Bild-Links decken sich, 3D-Szenen sind
  ``braucht_gpu``, GIFs unter der harten Grenze;
* die VC-Tabelle der Übersicht nennt genau die Knöpfe, die der Generator
  anlegt; die eigenen Knöpfe der Bau-Anleitung heißen anders als jeder
  Show-Knopf (sonst findet die Bild-Szene den Show-Knopf statt des eigenen);
* ``tools/build_buehnen_show_2026.py`` baut in einer Sandbox (die Bühne landet
  NICHT im echten Datenordner, TOOL-13), der Show-Lint ``--strict`` ist
  sauber, und nach dem LADEN bewegen „Laser langsam"/„Laser Welle" die
  Laser-Achsen (LAS-23), „Laser Lauf" öffnet nur mit 60, Grand Master 0
  schaltet die Laser aus (LAS-24), „Laser an" schreibt keine Farbe.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOOLS = os.path.join(_REPO, "tools")
sys.path.insert(0, _TOOLS)

from anleitungsbilder import runner  # noqa: E402

_ORDNER = os.path.join(_REPO, "docs", "anleitung_buehnen_show")
_IMG = os.path.join(_ORDNER, "img")
_UEBERSICHT = os.path.join(_ORDNER, "ANLEITUNG_BUEHNEN_SHOW.md")
_GENERATOR = os.path.join(_TOOLS, "build_buehnen_show_2026.py")


def _lies(pfad) -> str:
    with open(pfad, encoding="utf-8") as f:
        return f.read()


def test_uebersicht_manifest_szenen_dateien_und_links_decken_sich():
    manifest = json.loads(_lies(os.path.join(_IMG, "bilder.json")))
    im_manifest = {b["datei"] for b in manifest["bilder"]}
    szenen, ziel = runner.lade_szenen("buehnen_show")
    assert ziel == "docs/anleitung_buehnen_show/img"
    assert im_manifest == {s.datei for s in szenen}
    vorhanden = {n for n in os.listdir(_IMG) if n != "bilder.json"}
    assert vorhanden == im_manifest
    links = set(re.findall(r"!\[[^\]]*\]\(img/([^)]+)\)", _lies(_UEBERSICHT)))
    assert links == im_manifest
    text = json.dumps(manifest)
    assert "/home/" not in text and "/tmp/" not in text and ":\\\\" not in text


def test_uebersicht_3d_braucht_gpu_und_gifs_unter_der_grenze():
    szenen, _ziel = runner.lade_szenen("buehnen_show")
    for s in szenen:
        assert s.braucht_gpu == (s.name != "01_vc_seite"), s.name
    for name in os.listdir(_IMG):
        if name.endswith(".gif"):
            assert os.path.getsize(os.path.join(_IMG, name)) <= runner.GIF_LIMIT, name


def _show_knoepfe() -> set[str]:
    """Beschriftungen aller Knöpfe, die der Generator anlegt."""
    quelle = _lies(_GENERATOR)
    namen = set(re.findall(r'_knopf\("([^"]+)"', quelle))
    namen |= set(re.findall(r'b\.button\("([^"]+)"', quelle))
    return namen


def test_vc_tabelle_der_uebersicht_nennt_die_knoepfe_des_generators():
    text = _lies(_UEBERSICHT)
    zeilen = [z for z in text.splitlines()
              if z.startswith("| ") and not z.startswith("| Reihe") and " · " in z]
    in_doku = set()
    for z in zeilen:
        knoepfe = z.split("|")[2]
        for k in knoepfe.split(" · "):
            k = re.sub(r"\*\*|\(.*?\)", "", k).strip()
            in_doku.add(k)
    knoepfe = _show_knoepfe()
    regler = {"Grand Master", "Tempo Welle L→R", "PAR", "Moving Heads"}
    assert in_doku - regler == knoepfe, (in_doku - regler) ^ knoepfe
    assert "Laser NOT-AUS" in knoepfe


def test_eigene_vc_knoepfe_der_anleitung_heissen_anders_als_die_show():
    from anleitungsbilder import szenen_buehnen_effekte as e  # noqa: PLC0415
    eigene = [t for t, _f, _s in e.VC_KNOEPFE]
    assert len(eigene) == 5 and len(set(eigene)) == 5
    assert not set(eigene) & _show_knoepfe(), set(eigene) & _show_knoepfe()


_PROBE = r'''
import json, os, subprocess, sys
repo, basis = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(repo, "tools"))
from anleitungsbilder import sandbox
sb = sandbox.einrichten(basis)
out = os.path.join(basis, "show.lshow")
env = dict(os.environ)
bau = subprocess.run([sys.executable, os.path.join(repo, "tools", "build_buehnen_show_2026.py"),
                      "--out", out], env=env, capture_output=True, text=True, timeout=600)
lint = subprocess.run([sys.executable, os.path.join(repo, "tools", "lint_show.py"), "--strict",
                       out], env=env, capture_output=True, text=True, timeout=300)
erg = {"bau_rc": bau.returncode, "bau": (bau.stdout + bau.stderr)[-3000:],
       "lint_rc": lint.returncode, "lint": lint.stdout[-1500:]}
if bau.returncode == 0:
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    from src.core.app_state import get_state, get_channels_for_patched
    from src.core.engine.function_manager import get_function_manager
    from src.core.paths import app_data_dir
    from src.core.show.show_file import load_show
    erg["daten_in_sandbox"] = os.path.realpath(app_data_dir()).startswith(os.path.realpath(basis))
    ok, _m = load_show(out)
    erg["geladen"] = ok
    st, fm = get_state(), get_function_manager()
    om = st.output_manager
    fx = {f.fid: f for f in st.get_patched_fixtures()}
    laser = sorted(f for f in fx if (fx[f].label or "").startswith("Laser"))
    fn = {f.name: f for f in fm._functions.values()}

    def wert(fid, attr):
        f = fx[fid]
        for c in sorted(get_channels_for_patched(f), key=lambda c: c.channel_number):
            if c.attribute == attr:
                i = int(f.address) - 1 + int(c.channel_number) - 1
                return int(om.get_display_frame(int(f.universe))[i])

    def ticks(n):
        for _ in range(n):
            om._send_all()

    def neu(*namen):
        fm.stop_all()
        om.set_grand_master(1.0)
        ticks(2)
        for n in namen:
            fm.start(fn[n].id)
        ticks(2)

    erg["laser"] = len(laser)
    neu()
    erg["shutter_ohne_knopf"] = sorted({wert(f, "shutter") for f in laser})
    neu("Laser an")
    erg["laser_an_farbe"] = sorted({wert(f, "color_wheel") for f in laser})
    for name in ("Laser langsam", "Laser Welle"):
        neu("Laser an", name)
        spuren = {f: set() for f in laser}
        for _ in range(16):
            ticks(22)
            for f in laser:
                spuren[f].add(wert(f, "laser_x"))
        erg[name] = min(max(v) - min(v) for v in spuren.values())
    neu("Laser an", "Laser Lauf")
    werte = set()
    for _ in range(150):
        ticks(1)
        werte |= {wert(f, "shutter") for f in laser}
    erg["lauf_shutter"] = sorted(werte)
    neu("Laser an", "Laser langsam")
    om.set_grand_master(0.0)
    ticks(3)
    erg["gm0_shutter"] = sorted({wert(f, "shutter") for f in laser})
    fm.stop_all()
print("ERGEBNIS " + json.dumps(erg))
'''


@pytest.mark.timeout(900)
def test_generator_baut_in_sandbox_lint_sauber_und_laser_bewegen_nach_dem_laden(tmp_path):
    basis = str(tmp_path / "sandbox")
    os.makedirs(basis)
    skript = tmp_path / "probe.py"
    skript.write_text(_PROBE, encoding="utf-8")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    lauf = subprocess.run([sys.executable, "-I", str(skript), _REPO, basis], env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900, cwd=basis)
    zeile = [z for z in lauf.stdout.splitlines() if z.startswith("ERGEBNIS ")]
    assert zeile, (lauf.stdout[-2000:], lauf.stderr[-2000:])
    erg = json.loads(zeile[-1][len("ERGEBNIS "):])
    assert erg["bau_rc"] == 0, erg["bau"]
    assert "[warn]" not in erg["bau"], erg["bau"]
    assert erg["lint_rc"] == 0 and "0 Fehler, 0 Warnungen" in erg["lint"], erg["lint"]
    assert erg["daten_in_sandbox"] and erg["geladen"]
    assert erg["laser"] == 10
    assert erg["shutter_ohne_knopf"] == [0]
    assert erg["laser_an_farbe"] == [0]           # Farbe getrennt („Laser grün")
    assert erg["Laser langsam"] >= 40, erg        # jeder Laser wandert in X
    assert erg["Laser Welle"] >= 40, erg
    assert erg["lauf_shutter"] == [0, 60]
    assert erg["gm0_shutter"] == [0]
