"""DOC-65: Anleitung „Eigenes Gerät mit dem Fixture Generator anlegen“.

Haelt ohne GPU fest:

* Szenen-Modul zielt auf die Anleitung; alle Szenen laufen am echten Bildschirm,
* Manifest, Bildordner und Bild-Links der Anleitung decken sich (plus das
  Typenschild-Foto, das kein Szenenbild ist),
* das Typenschild-Foto ist verkleinert und ohne EXIF,
* die Kanaele, die die Szenen in den Generator tippen, sind genau die des
  Bibliotheksprofils — sonst zeigt die Anleitung ein anderes Profil, als
  LightOS mitliefert,
* die DIP-Tabelle steht in der Anleitung (Schalter 10 AUS = DMX).
"""
from __future__ import annotations

import json
import os
import re
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "tools"))

from anleitungsbilder import runner  # noqa: E402

_ORDNER = os.path.join(_REPO, "docs", "anleitung_fixture_generator")
_IMG = os.path.join(_ORDNER, "img")
_ANLEITUNG = os.path.join(_ORDNER, "ANLEITUNG_FIXTURE_GENERATOR.md")
_FOTO = "typenschild_el400rgb.jpg"
_PROFIL = os.path.join(_REPO, "fixtures", "bibliothek", "laserworld",
                       "el-400rgb-mk2.json")


def _text() -> str:
    with open(_ANLEITUNG, encoding="utf-8") as f:
        return f.read()


def _links() -> set[str]:
    return set(re.findall(r"!\[[^\]]*\]\(img/([^)]+)\)", _text()))


def test_szenen_zielen_auf_die_anleitung():
    szenen, ziel = runner.lade_szenen("fixture_generator")
    assert ziel == "docs/anleitung_fixture_generator/img"
    # Alle am echten Bildschirm: der Durchlauf ist zugleich der Eingabetest der
    # Oberflaeche (QTest-Klicks/Tastatur in Generator, Patch-Dialog, Programmer).
    assert szenen and all(s.braucht_gpu for s in szenen)


def test_manifest_dateien_und_anleitung_decken_sich():
    with open(os.path.join(_IMG, "bilder.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    im_manifest = {b["datei"] for b in manifest["bilder"]}
    szenen, _ziel = runner.lade_szenen("fixture_generator")
    assert im_manifest == {s.datei for s in szenen}
    vorhanden = {n for n in os.listdir(_IMG) if n != "bilder.json"}
    assert vorhanden == im_manifest | {_FOTO}
    assert _links() == im_manifest | {_FOTO}


def test_manifest_ohne_absolute_pfade():
    with open(os.path.join(_IMG, "bilder.json"), encoding="utf-8") as f:
        text = f.read()
    assert "/home/" not in text and "/tmp/" not in text and ":\\\\" not in text


def test_typenschild_klein_und_ohne_exif():
    from PIL import Image
    with Image.open(os.path.join(_IMG, _FOTO)) as im:
        assert im.width <= 900
        assert not dict(im.getexif())
        assert "exif" not in im.info


def test_generator_kanaele_wie_bibliotheksprofil():
    from anleitungsbilder import szenen_fixture_generator as G
    with open(_PROFIL, encoding="utf-8") as f:
        profil = json.load(f)
    assert G.HERSTELLER == profil["hersteller"]
    assert G.MODELL == profil["modell"]
    assert G.KURZNAME == profil["kurzname"]
    assert G.LEISTUNG_W == profil["leistung_w"]
    (modus,) = profil["modi"]
    assert G.MODUS == modus["name"]
    soll = [(k["name"], k["attribut"], k["default"], k["highlight"],
             [(b["von"], b["bis"], b["name"], b.get("art", ""))
              for b in k.get("bereiche", [])])
            for k in modus["kanaele"]]
    ist = [(n, a, d, h, [tuple(b) for b in bereiche])
           for n, a, d, h, bereiche in G.KANAELE]
    assert ist == soll


def test_dip_tabelle_in_der_anleitung():
    text = _text()
    assert "Schalter 10 AUS = DMX-Betrieb" in text
    assert "| Wert | 1 | 2 | 4 | 8 | 16 | 32 | 64 | 128 | 256 | Betriebsart |" in text


def test_im_index_eingetragen():
    with open(os.path.join(_REPO, "docs", "ANLEITUNGEN.md"), encoding="utf-8") as f:
        assert "anleitung_fixture_generator/ANLEITUNG_FIXTURE_GENERATOR.md" in f.read()


def test_vergleich_findet_abweichungen_und_schweigt_bei_gleichheit():
    from anleitungsbilder.szenen_fixture_generator import vergleich_daten
    with open(_PROFIL, encoding="utf-8") as f:
        bib = json.load(f)
    assert vergleich_daten(json.loads(json.dumps(bib)), bib) == []
    anders = json.loads(json.dumps(bib))
    anders["modi"][0]["kanaele"][0]["default"] = 175
    anders["modi"][0]["kanaele"][0]["bereiche"][0]["art"] = ""
    anders["leistung_w"] = 15
    z = vergleich_daten(anders, bib)
    assert any(t.startswith("leistung_w") for t in z)
    assert any(t.startswith("Kanal 1 default") for t in z)
    assert any(t.startswith("Kanal 1 Bereiche") for t in z)
