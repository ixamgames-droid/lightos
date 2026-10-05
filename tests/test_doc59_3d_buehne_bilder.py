"""DOC-59: die 3D-Buehnen-Anleitung und ihre Bilder passen zusammen.

Die Bilder entstehen nur am echten Bildschirm (``--bildschirm``), das Gate
kann sie nicht neu bauen. Es haelt deshalb fest, was ohne GPU pruefbar ist:

* jede Szene des Moduls ist eine 3D-Szene (offscreen sonst schwarz),
* jedes Bild aus dem Manifest liegt im Ordner und ist in der Anleitung
  eingebunden — und umgekehrt zeigt jeder Bild-Link der Anleitung auf eine
  vorhandene Datei,
* das GIF bleibt im Groessenziel des Werkzeugs (unter 1 MB).
"""
from __future__ import annotations

import json
import os
import re
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "tools"))

from anleitungsbilder import runner  # noqa: E402

_ORDNER = os.path.join(_REPO, "docs", "anleitung_3d_visualizer_2026")
_IMG = os.path.join(_ORDNER, "img")
_ANLEITUNG = os.path.join(_ORDNER, "ANLEITUNG_3D_BUEHNE.md")


def _links() -> set[str]:
    with open(_ANLEITUNG, encoding="utf-8") as f:
        text = f.read()
    return set(re.findall(r"!\[[^\]]*\]\(img/([^)]+)\)", text))


def test_alle_szenen_brauchen_die_gpu_und_zielen_auf_die_anleitung():
    szenen, ziel = runner.lade_szenen("3d_buehne")
    assert ziel == "docs/anleitung_3d_visualizer_2026/img"
    assert szenen, "keine Szenen"
    assert all(s.braucht_gpu for s in szenen), \
        [s.name for s in szenen if not s.braucht_gpu]
    assert any(s.ist_gif for s in szenen)


def test_manifest_dateien_und_anleitung_decken_sich():
    with open(os.path.join(_IMG, "bilder.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    im_manifest = {b["datei"] for b in manifest["bilder"]}
    szenen, _ziel = runner.lade_szenen("3d_buehne")
    assert im_manifest == {s.datei for s in szenen}
    vorhanden = {n for n in os.listdir(_IMG) if n != "bilder.json"}
    assert vorhanden == im_manifest
    assert _links() == im_manifest


def test_manifest_ohne_absolute_pfade():
    with open(os.path.join(_IMG, "bilder.json"), encoding="utf-8") as f:
        text = f.read()
    assert "/home/" not in text and "/tmp/" not in text and ":\\\\" not in text


def test_gif_im_groessenziel():
    for name in os.listdir(_IMG):
        if name.endswith(".gif"):
            assert os.path.getsize(os.path.join(_IMG, name)) < runner.GIF_ZIEL, name
