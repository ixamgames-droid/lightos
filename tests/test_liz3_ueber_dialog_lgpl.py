"""LIZ-3: „Über LightOS“ nennt die LGPL-Bibliotheken und zeigt auf die Lizenztexte.

Das Fenster „Über LightOS“ zeigt den Urhebervermerk von LightOS. Die LGPL
verlangt fuer ein Programm, das waehrend des Laufs Urhebervermerke anzeigt,
dass dort auch der Vermerk der Bibliothek steht und ein Verweis auf die
Lizenztexte (LGPL-3.0 Abschnitt 4 c, LGPL-2.1 Abschnitt 6). Vorher nannte das
Fenster weder Qt/PySide6 noch FFmpeg oder libusb.

Welche Bestandteile unter der LGPL stehen, liest der Test aus der Tabelle des
Setup-Baus (``packaging/windows/fremdkomponenten.py``) — kommt dort eine
LGPL-Bibliothek dazu, muss sie auch im Fenster stehen.
"""
import os
import re
import sys
from urllib.parse import unquote, urlparse

from src.ui import hilfe

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "packaging", "windows"))
import fremdkomponenten  # noqa: E402

#: Paketname (PEP 503) -> Name, unter dem das Fenster den Bestandteil nennt.
_ANZEIGE = {"shiboken6": "Shiboken6"}


def _lgpl_namen():
    namen = set()
    for paket, eintrag in fremdkomponenten.PAKETE.items():
        if "LGPL" in eintrag["lizenz"]:
            namen.add(_ANZEIGE.get(paket, "PySide6" if paket.startswith("pyside6") else paket))
    for name, lizenz, _quelle, _muster in fremdkomponenten.EINGEBETTET:
        if "LGPL" in lizenz:
            namen.add(name)
    return namen


def _text():
    return hilfe.ueber_text()


def test_tabelle_kennt_die_lgpl_bestandteile():
    # Positivkontrolle: sonst waere der naechste Test leer und gruen.
    assert {"PySide6", "Shiboken6", "FFmpeg", "libusb"} <= _lgpl_namen()


def test_jede_lgpl_bibliothek_steht_im_fenster():
    text = _text()
    fehlt = sorted(n for n in _lgpl_namen() if n not in text)
    assert not fehlt, f"„Über LightOS“ nennt nicht: {fehlt}"
    assert "Qt" in text


def test_lizenzen_und_urheber_der_bibliothek_genannt():
    text = _text()
    assert "GNU LGPL 3.0" in text and "GNU LGPL 2.1" in text
    assert "The Qt Company" in text
    assert "FFmpeg-Entwickler" in text


def test_verweis_auf_den_ordner_mit_den_lizenztexten():
    text = _text()
    links = re.findall(r"href='([^']+)'", text)
    ordner = [unquote(urlparse(u).path).lstrip("/") for u in links if u.startswith("file:")]
    assert len(ordner) == 1, links
    pfad = os.path.normpath(ordner[0] if os.name == "nt" else "/" + ordner[0])
    assert os.path.isdir(pfad), pfad
    assert os.path.normcase(pfad) == os.path.normcase(os.path.join(hilfe.programm_dir(), "licenses"))
    # Die Texte, auf die die LGPL verweist, liegen dort.
    dateien = os.listdir(pfad)
    assert "LGPL-3.0.txt" in dateien and "GPL-3.0.txt" in dateien
    assert any(d.startswith("LGPL-2.1") for d in dateien), dateien
    assert "THIRD_PARTY_NOTICES.md" in text


def test_im_setup_build_zeigt_der_verweis_in_den_programmordner(monkeypatch, tmp_path):
    (tmp_path / "licenses").mkdir()
    monkeypatch.setattr(hilfe, "programm_dir", lambda: str(tmp_path))
    links = re.findall(r"href='(file:[^']+)'", hilfe.ueber_text())
    assert len(links) == 1
    pfad = unquote(urlparse(links[0]).path).lstrip("/")
    pfad = os.path.normpath(pfad if os.name == "nt" else "/" + pfad)
    assert os.path.normcase(pfad) == os.path.normcase(str(tmp_path / "licenses"))


def test_ohne_ordner_kein_toter_verweis(monkeypatch, tmp_path):
    monkeypatch.setattr(hilfe, "programm_dir", lambda: str(tmp_path))
    text = hilfe.ueber_text()
    assert "file:" not in text
    assert "GNU LGPL 3.0" in text and "licenses" in text
