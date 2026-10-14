"""LIZ-2 (Rest): Sammeldateien fuer Qt WebEngine (Chromium) und Mesa, ohne mido/winrt.

**Befund (14.10.2026):** Die PySide6-Pakete bringen zu zwei Teilen ihre
Fremdlizenzen nicht mit — weder als Datei im Paket noch in
``qtwebengine_resources.pak``:

* Qt WebEngine 6.140.0 (Chromium 140.0.7339.225, in PySide6_WebEngine
  6.12.0.140) mit rund 125 Fremdbibliotheken;
* ``opengl32sw.dll`` (PySide6_Essentials 6.12.0): Mesa 11.2.2 mit statisch
  eingebundenem LLVM 3.6.2 — bis auf die Signatur gleich Qts Archiv
  ``opengl32sw-64-mesa_11_2_2-signed_sha256.7z``.

``packaging/windows/fremdlizenzen_sammeln.py`` baut aus der Qt-Dokumentation
bzw. den Original-Quellarchiven ``licenses/QtWebEngine-THIRD-PARTY.txt`` und
``licenses/Mesa-opengl32sw.txt``; der Bau (``fremdkomponenten.
sammeldatei_befunde``) vergleicht die Version im Kopf mit der DLL im Bundle,
der Selbsttest der gepackten exe verlangt die Dateien, wenn die DLL beiliegt.

Ausserdem: ``mido`` und die ``winrt``-Pakete standen in ``requirements.txt``,
werden aber nirgends importiert (auch nicht dynamisch) und lagen nie im
Bundle — sie sind entfernt.

Ohne Netz: die Werkzeug-Tests laufen gegen kleine nachgestellte Eingaben.
"""
from __future__ import annotations

import io
import os
import re
import sys
import tarfile

import pytest

from src.core import selbsttest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "packaging", "windows"))
import bundle_inhalt                                             # noqa: E402
import fremdkomponenten as fk                                    # noqa: E402
import fremdlizenzen_sammeln as fs                               # noqa: E402


def _lies(*teile) -> str:
    with io.open(os.path.join(_REPO, *teile), encoding="utf-8") as f:
        return f.read()


# ── mido / winrt ─────────────────────────────────────────────────────────────

_WEG = re.compile(r"(?i)\b(mido|winrt)\b")


@pytest.mark.parametrize("datei", ["requirements.txt", "install.py",
                                   ".github/workflows/ci.yml", "INSTALL.md"])
def test_mido_und_winrt_sind_weg(datei):
    treffer = [z for z in _lies(*datei.split("/")).splitlines() if _WEG.search(z)]
    assert treffer == [], f"{datei}: {treffer}"


def test_mido_und_winrt_stehen_nicht_mehr_in_der_tabelle():
    for name in fk.NICHT_IM_BUNDLE:
        assert not _WEG.search(name), name


def test_install_kennt_rtmidi_weiter_als_optional():
    assert re.search(r'OPTIONAL_REQUIREMENTS = \{\s*"python-rtmidi",\s*\}', _lies("install.py"))


# ── Qt WebEngine: Doku-Seiten -> Sammeldatei ─────────────────────────────────

_UEBERSICHT = """<html><head><title>Qt WebEngine Licensing | Qt WebEngine 6.140.0</title></head>
<body><a href="qtwebengine-3rdparty-zlib.html">Seitenleiste</a>
<div class="table"><table class="annotated">
<tr class="odd topAlign"><td class="tblName" translate="no"><p><a href="qtwebengine-3rdparty-abseil.html">Abseil</a></p></td><td class="tblDescr"><p>Apache-2.0</p></td></tr>
<tr class="even topAlign"><td class="tblName" translate="no"><p><a href="qtwebengine-3rdparty-zlib.html">zlib</a></p></td><td class="tblDescr"><p>Zlib &amp; mehr</p></td></tr>
</table></div></body></html>"""


def _seite(name, text, homepage="https://example.org/x"):
    hp = f'<p><a href="{homepage}">Project Homepage</a></p>' if homepage else ""
    return (f'<h1 class="title">{name}</h1><div class="descr">{hp}'
            f'<div class="pre"><pre class="cpp plain"><code class="text">{text}'
            "</code></pre></div></div>")


def _seiten():
    return {"qtwebengine-3rdparty-abseil.html": _seite("Abseil", "Apache License\n  Text"),
            "qtwebengine-3rdparty-zlib.html": _seite(
                "zlib", "(zlib doesn&amp;#x27;t &lt;mind&gt;)", homepage="")}


def test_version_und_eintraege_der_uebersicht():
    assert fs.doku_version(_UEBERSICHT) == "6.140.0"
    assert fs.eintraege_der_uebersicht(_UEBERSICHT) == [
        ("qtwebengine-3rdparty-abseil.html", "Abseil", "Apache-2.0"),
        ("qtwebengine-3rdparty-zlib.html", "zlib", "Zlib & mehr")]
    assert fs.seiten_der_uebersicht(_UEBERSICHT) == [
        "qtwebengine-3rdparty-zlib.html", "qtwebengine-3rdparty-abseil.html"]


def test_uebersicht_ohne_version_wird_nicht_still_verarbeitet():
    with pytest.raises(ValueError):
        fs.doku_version(_UEBERSICHT.replace("6.140.0", "neu"))


def test_attribution_doppelt_maskiert_wird_lesbar():
    a = fs.lies_attribution(_seiten()["qtwebengine-3rdparty-zlib.html"])
    assert a == {"name": "zlib", "homepage": "", "texte": ["(zlib doesn't <mind>)"]}


def test_attribution_ohne_lizenztext_bricht_ab():
    with pytest.raises(ValueError):
        fs.lies_attribution('<h1 class="title">x</h1><p>nichts</p>')


def test_sammeldatei_webengine():
    text = fs.webengine_text(_UEBERSICHT, _seiten(), "2026-10-14")
    assert fs.KOPF_WEBENGINE + " 6.140.0" in text.splitlines()
    assert fk._kopf_wert(text, "Qt-WebEngine-Version:") == "6.140.0"
    assert "Eintraege: 2" in text
    assert "Projektseite: https://example.org/x" in text
    assert text.index("\nAbseil\n") < text.index("\nzlib\n"), "Reihenfolge der Tabelle"
    assert "Apache License\n  Text" in text, "Lizenztext unveraendert, mit Einrueckung"


def test_fehlende_seite_gibt_keine_halbe_aufstellung():
    seiten = _seiten()
    del seiten["qtwebengine-3rdparty-zlib.html"]
    with pytest.raises(ValueError, match="fehlen"):
        fs.webengine_text(_UEBERSICHT, seiten, "heute")


# ── Mesa: Quellarchive -> Sammeldatei ────────────────────────────────────────

_MIT = ("Copyright (C) 1999-2007  Brian Paul   All Rights Reserved.\n\n"
        "Permission is hereby granted, free of charge, to any person ...")


def _tar(pfad, wurzel, dateien):
    with tarfile.open(pfad, "w:xz") as t:
        for name, inhalt in dateien.items():
            daten = inhalt.encode("utf-8")
            info = tarfile.TarInfo(f"{wurzel}/{name}")
            info.size = len(daten)
            t.addfile(info, io.BytesIO(daten))
    return str(pfad)


def _archive(tmp_path, mesa_version="11.2.2", llvm_wurzel="llvm-3.6.2.src"):
    mesa = _tar(tmp_path / "mesa.tar.xz", f"mesa-{mesa_version}", {
        "VERSION": mesa_version + "\n",
        "docs/license.html": f"<p>x</p><pre>\n{_MIT}\n</pre><pre>anderes</pre>",
        "include/c11/threads_win32.h": "/*\n * C11 emulation\n * Boost Software License\n */\nint x;",
        "src/gallium/auxiliary/postprocess/pp_mlaa.c": "/**\n * Jimenez MLAA BSD\n */",
    })
    llvm = _tar(tmp_path / "llvm.tar.xz", llvm_wurzel, {
        "LICENSE.TXT": "LLVM Release License\nUniversity of Illinois/NCSA\n",
        "lib/Support/COPYRIGHT.regex": "Henry Spencer\n",
        "lib/Support/MD5.cpp": "/*\n * Alexander Peslyak public domain\n */\n#include <x>",
    })
    return mesa, llvm


def test_sammeldatei_mesa(tmp_path):
    text = fs.mesa_text(*_archive(tmp_path))
    assert fk._kopf_wert(text, "Mesa-Version:") == fs.MESA_VERSION
    for teil in (_MIT, "C11 emulation\nBoost Software License", "Jimenez MLAA BSD",
                 "University of Illinois/NCSA", "Henry Spencer",
                 "Alexander Peslyak public domain", fs.MESA_ARCHIV, fs.LLVM_ARCHIV,
                 "SHA-256 "):
        assert teil in text, teil
    assert "anderes" not in text and "int x;" not in text


def test_mesa_aus_falschem_archiv_bricht_ab(tmp_path):
    with pytest.raises(ValueError, match="Version"):
        fs.mesa_text(*_archive(tmp_path, mesa_version="12.0.0"))
    with pytest.raises(ValueError, match="LLVM"):
        fs.mesa_text(*_archive(tmp_path, llvm_wurzel="llvm-3.9.0.src"))


# ── Bau: Version im Bundle gegen die Sammeldatei ─────────────────────────────

def _pe(version=(6, 140, 0, 0)):
    a, b, c, d = version
    return (b"MZ" + b"\0" * 100 + b"\xbd\x04\xef\xfe" + b"\0\0\x01\0"
            + ((a << 16) | b).to_bytes(4, "little") + ((c << 16) | d).to_bytes(4, "little")
            + b"\0" * 40)


def test_versionen_aus_den_dlls():
    assert fk.pe_dateiversion(_pe()) == "6.140.0"
    assert fk.pe_dateiversion(b"MZ ohne Ressource") is None
    assert fk.mesa_version(b"\0%s%u.%u%s Mesa 11.2.2\0") == "11.2.2"
    assert fk.mesa_version(b"kein mesa") is None


def _bundle(tmp_path, webengine=(6, 140, 0, 0), mesa=b"Mesa 11.2.2"):
    lic = tmp_path / "licenses"
    lic.mkdir()
    (lic / "QtWebEngine-THIRD-PARTY.txt").write_text(
        "Titel\n\nQt-WebEngine-Version: 6.140.0\n", encoding="utf-8")
    (lic / "Mesa-opengl32sw.txt").write_text("Titel\n\nMesa-Version: 11.2.2\n",
                                             encoding="utf-8")
    (tmp_path / "core.dll").write_bytes(_pe(webengine))
    (tmp_path / "sw.dll").write_bytes(b"\0" + mesa + b"\0")
    eintraege = [("PySide6\\Qt6WebEngineCore.dll", str(tmp_path / "core.dll"), "BINARY"),
                 ("PySide6/opengl32sw.dll", str(tmp_path / "sw.dll"), "BINARY"),
                 ("PySide6/Qt6Core.dll", str(tmp_path / "gibt-es-nicht"), "BINARY")]
    return eintraege, str(lic)


_TEXTE = {"QtWebEngine-THIRD-PARTY.txt", "Mesa-opengl32sw.txt", "LGPL-3.0.txt"}


def test_passende_versionen_sind_ruhig(tmp_path):
    eintraege, lic = _bundle(tmp_path)
    assert fk.sammeldatei_befunde(eintraege, lic, _TEXTE) == []


def test_neues_qt_webengine_bricht_den_bau(tmp_path):
    eintraege, lic = _bundle(tmp_path, webengine=(6, 146, 0, 0))
    b = fk.sammeldatei_befunde(eintraege, lic, _TEXTE)
    assert len(b) == 1 and "6.146.0" in b[0] and "fremdlizenzen_sammeln.py webengine" in b[0]


def test_anderes_mesa_bricht_den_bau(tmp_path):
    eintraege, lic = _bundle(tmp_path, mesa=b"Mesa 24.0.1")
    b = fk.sammeldatei_befunde(eintraege, lic, _TEXTE)
    assert len(b) == 1 and "24.0.1" in b[0] and "fremdlizenzen_sammeln.py mesa" in b[0]


def test_sammeldatei_die_nicht_ins_bundle_kommt_bricht_den_bau(tmp_path):
    eintraege, lic = _bundle(tmp_path)
    b = fk.sammeldatei_befunde(eintraege, lic, _TEXTE - {"Mesa-opengl32sw.txt"})
    assert len(b) == 1 and "Mesa-opengl32sw.txt" in b[0]


def test_ohne_webengine_und_mesa_im_bundle_nichts_zu_pruefen(tmp_path):
    assert fk.sammeldatei_befunde([("PySide6/Qt6Core.dll", "x", "BINARY")],
                                  str(tmp_path), set()) == []


def test_der_bau_ruft_die_pruefung_auf():
    quelle = _lies("packaging", "windows", "fremdkomponenten.py")
    rumpf = quelle.split("def pruefe_und_schreibe", 1)[1]
    assert "sammeldatei_befunde(" in rumpf.split("if gefunden:", 1)[0]


def test_liste_des_builds_nennt_die_sammeldateien():
    erfasst = {"pakete": {}, "python": [], "ohne": [],
               "eingebettet": {"Mesa llvmpipe (opengl32sw.dll)": ["PySide6/opengl32sw.dll"]}}
    text = fk.liste_text(erfasst, {}, "3.12.10",
                         qt_dateien=["PySide6/Qt6WebEngineCore.dll"])
    assert "QtWebEngine-THIRD-PARTY.txt" in text
    assert "Lizenztext: Mesa-opengl32sw.txt" in text


# ── Die eingecheckten Sammeldateien ──────────────────────────────────────────

def test_sammeldateien_liegen_im_repo_und_kommen_ins_bundle():
    im_bundle = set(bundle_inhalt.dateien(_REPO))
    for datei, _kopf, _art in fk.SAMMELDATEIEN.values():
        assert f"licenses/{datei}" in im_bundle, (
            f"licenses/{datei}: Git kennt die Datei nicht — bundle_inhalt packt "
            "nur, was eingecheckt ist")
    assert set(fk.EINGEBETTET_TEXTE.values()) <= {d for d, _k, _a in fk.SAMMELDATEIEN.values()}


def test_webengine_sammeldatei_ist_vollstaendig():
    text = _lies("licenses", fs.DATEI_WEBENGINE)
    assert fk._kopf_wert(text, "Qt-WebEngine-Version:") == "6.140.0"
    n = int(re.search(r"(?m)^Eintraege: (\d+)$", text).group(1))
    assert n > 100, "die Aufstellung von Qt WebEngine hat weit ueber 100 Eintraege"
    assert len(re.findall(r"(?m)^Lizenz: ", text)) == n, "jeder Eintrag mit Lizenz"
    for name in ("The Chromium Project", "BoringSSL", "icu", "WebKit", "zlib"):
        assert re.search(rf"(?m)^{re.escape(name)}$", text), name
    assert "Redistribution and use in source and binary forms" in text
    assert "&amp;" not in text and "&#x27;" not in text, "HTML-Reste"


def test_mesa_sammeldatei_hat_alle_texte():
    text = _lies("licenses", fs.DATEI_MESA)
    assert fk._kopf_wert(text, "Mesa-Version:") == fs.MESA_VERSION == "11.2.2"
    for teil in ("Copyright (C) 1999-2007  Brian Paul",
                 "Permission is hereby granted, free of charge",
                 "Boost Software License, Version 1.0",
                 "Uses Jimenez's MLAA",
                 "LLVM Release License", "University of Illinois/NCSA",
                 "Henry Spencer", "Alexander Peslyak",
                 fs.MESA_ARCHIV, fs.LLVM_ARCHIV, fs.QT_LLVMPIPE):
        assert teil in text, teil


def test_hinweise_nennen_die_sammeldateien_und_nichts_mehr_offen():
    text = _lies("THIRD_PARTY_NOTICES.md")
    assert "(licenses/QtWebEngine-THIRD-PARTY.txt)" in text
    assert "(licenses/Mesa-opengl32sw.txt)" in text
    glatt = re.sub(r"\s+", " ", text)
    assert "ein Lizenztext liegt der Datei nicht bei" not in glatt
    assert "PySide6-Pakete bringen diese Aufstellung nicht als Datei mit. Ob" not in glatt


# ── Selbsttest der gepackten exe ─────────────────────────────────────────────

def _programmordner(tmp_path, texte=True):
    w = tmp_path / "_internal"
    (w / "licenses" / "pakete" / "Flask-3.1.3").mkdir(parents=True)
    (w / "licenses" / "pakete" / "Flask-3.1.3" / "LICENSE.txt").write_text("x", "utf-8")
    for name in ("Python-LICENSE.txt", "LGPL-3.0.txt", "GPL-3.0.txt"):
        (w / "licenses" / name).write_text("x", encoding="utf-8")
    (w / "licenses" / "BUNDLE-KOMPONENTEN.txt").write_text(
        "Qt6WebEngineCore.dll | Qt WebEngine\n", encoding="utf-8")
    (w / "PySide6").mkdir()
    for name in ("Qt6WebEngineCore.dll", "opengl32sw.dll"):
        (w / "PySide6" / name).write_bytes(b"")
    if texte:
        for name in ("QtWebEngine-THIRD-PARTY.txt", "Mesa-opengl32sw.txt"):
            (w / "licenses" / name).write_text("x", encoding="utf-8")
    return str(w)


def test_selbsttest_mit_sammeldateien_ist_ruhig(tmp_path):
    assert selbsttest.pruefe_fremdlizenzen(_programmordner(tmp_path), gefroren=True) == []


def test_selbsttest_vermisst_die_sammeldateien(tmp_path):
    f = selbsttest.pruefe_fremdlizenzen(_programmordner(tmp_path, texte=False), gefroren=True)
    assert any("QtWebEngine-THIRD-PARTY.txt" in x for x in f), f
    assert any("Mesa-opengl32sw.txt" in x for x in f), f


def test_selbsttest_und_bau_kennen_dieselben_dateien():
    bau = {(k, f"licenses/{d}") for k, (d, _k, _a) in fk.SAMMELDATEIEN.items()}
    exe = {(dll.lower(), text) for dll, text in selbsttest.SAMMELDATEIEN_JE_BIBLIOTHEK}
    assert bau == exe
