"""LIZ-2: Sammeldateien fuer Fremdlizenzen, die den PySide6-Paketen NICHT beiliegen.

Zwei Teile des Windows-Setups kommen fertig gebaut aus den PySide6-Paketen,
ohne dass die Pakete ihre Lizenzen mitbringen:

1. **Qt WebEngine** (``Qt6WebEngineCore.dll``, ``QtWebEngineProcess.exe``,
   ``resources/*.pak``) enthaelt Chromium und mit ihm rund 150 fremde
   Bibliotheken. Chromium erzeugt seine Aufstellung (``about_credits.html``) mit
   ``tools/licenses/licenses.py``; in den PySide6-Paketen liegt sie nicht, auch
   nicht in ``qtwebengine_resources.pak``. Qt veroeffentlicht dieselbe
   Aufstellung — Name, Lizenz, Projektseite, Lizenztext — in der Dokumentation
   „Qt WebEngine Licensing“ (je Bibliothek eine Seite). Aus diesen Seiten baut
   ``webengine`` die Datei ``licenses/QtWebEngine-THIRD-PARTY.txt``.
2. **Mesa llvmpipe** (``opengl32sw.dll``, Software-OpenGL). Qt legt die Datei
   als fertigen Bau bei (``download.qt.io/development_releases/prebuilt/
   llvmpipe/windows/``); sie enthaelt Mesa und, statisch gebunden, LLVM. Aus den
   Original-Quellarchiven beider Projekte baut ``mesa`` die Datei
   ``licenses/Mesa-opengl32sw.txt``.

Beide Dateien sind eingecheckt; der Bau (``LightOS.spec`` ueber
``fremdkomponenten.pruefe_und_schreibe``) vergleicht die Version im Kopf der
Datei mit der Datei im Bundle und bricht ab, wenn sie nicht passt — dann dieses
Werkzeug neu laufen lassen (Aufrufe unten) und das Ergebnis einchecken.

Nur Dateien lesen und schreiben: kein Qt-Import, keine App. Die Tests laufen
ohne Netz gegen kleine nachgestellte Eingaben.

Aufrufe (im Repo-Root)::

    # Qt WebEngine: Seiten holen (Netz), dann daraus die Sammeldatei bauen
    python packaging/windows/fremdlizenzen_sammeln.py webengine --ordner <tmp> --holen
    python packaging/windows/fremdlizenzen_sammeln.py webengine --ordner <tmp>

    # Mesa: die beiden Quellarchive vorher von den offiziellen Adressen laden
    # (MESA_ARCHIV / LLVM_ARCHIV unten), dann
    python packaging/windows/fremdlizenzen_sammeln.py mesa \\
        --mesa <mesa-11.2.2.tar.xz> --llvm <llvm-3.6.2.src.tar.xz>
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import html
import os
import re
import sys
import tarfile
import time
import urllib.request

# ── Ablage ───────────────────────────────────────────────────────────────────

DATEI_WEBENGINE = "QtWebEngine-THIRD-PARTY.txt"
DATEI_MESA = "Mesa-opengl32sw.txt"

#: Kopfzeilen, die der Bau liest (``fremdkomponenten.sammeldatei_befunde``).
KOPF_WEBENGINE = "Qt-WebEngine-Version:"
KOPF_MESA = "Mesa-Version:"

# ── Qt WebEngine ─────────────────────────────────────────────────────────────

WEBENGINE_DOKU = "https://doc.qt.io/qt-6/"
WEBENGINE_UEBERSICHT = "qtwebengine-licensing.html"
WEBENGINE_QUELLE = "https://code.qt.io/cgit/qt/qtwebengine.git/"
WEBENGINE_CHROMIUM_QUELLE = "https://code.qt.io/cgit/qt/qtwebengine-chromium.git/"

_SEITE = re.compile(r'href="(qtwebengine-3rdparty-[^"#/]+\.html)"')
_TITEL_VERSION = re.compile(r"<title>[^<]*\|\s*Qt WebEngine\s+(\d+\.\d+\.\d+)\s*</title>")
_ZEILE = re.compile(
    r'<tr[^>]*>\s*<td class="tblName"[^>]*>\s*<p>\s*<a href="(qtwebengine-3rdparty-[^"]+)">'
    r"(.*?)</a>\s*</p>\s*</td>\s*<td class=\"tblDescr\"[^>]*>\s*<p>(.*?)</p>", re.S)
_H1 = re.compile(r'<h1 class="title"[^>]*>(.*?)</h1>', re.S)
_HOMEPAGE = re.compile(r'<a href="([^"]+)">Project Homepage</a>')
_PRE = re.compile(r"<pre[^>]*>(.*?)</pre>", re.S)


def _klartext(fragment: str) -> str:
    """HTML-Fragment -> Text. Die Qt-Seiten maskieren manche Zeichen doppelt
    (``&amp;#x27;``), deshalb zweimal entschluesseln."""
    text = re.sub(r"<[^>]+>", "", fragment)
    return html.unescape(html.unescape(text))


def doku_version(uebersicht_html: str) -> str:
    """Version von Qt WebEngine, die die Doku-Seite beschreibt (aus dem Titel)."""
    m = _TITEL_VERSION.search(uebersicht_html)
    if not m:
        raise ValueError("Titel der Doku-Seite nennt keine Qt-WebEngine-Version")
    return m.group(1)


def eintraege_der_uebersicht(uebersicht_html: str) -> list[tuple[str, str, str]]:
    """``[(seite, name, lizenz), …]`` aus der Tabelle „Third-Party Licenses“,
    in der Reihenfolge der Seite, jede Seite einmal."""
    aus, gesehen = [], set()
    for seite, name, lizenz in _ZEILE.findall(uebersicht_html):
        if seite in gesehen:
            continue
        gesehen.add(seite)
        aus.append((seite, _klartext(name).strip(), _klartext(lizenz).strip()))
    return aus


def seiten_der_uebersicht(uebersicht_html: str) -> list[str]:
    """Alle verlinkten Attributions-Seiten (auch ausserhalb der Tabelle)."""
    aus = []
    for s in _SEITE.findall(uebersicht_html):
        if s not in aus:
            aus.append(s)
    return aus


def lies_attribution(seite_html: str) -> dict:
    """Eine Attributions-Seite -> ``{"name", "homepage", "texte": [...]}``."""
    m = _H1.search(seite_html)
    if not m:
        raise ValueError("Attributions-Seite ohne Ueberschrift")
    hp = _HOMEPAGE.search(seite_html)
    texte = [_klartext(t).strip("\n") for t in _PRE.findall(seite_html)]
    texte = [t for t in texte if t.strip()]
    if not texte:
        raise ValueError(f"{_klartext(m.group(1)).strip()}: Seite ohne Lizenztext")
    return {"name": _klartext(m.group(1)).strip(),
            "homepage": html.unescape(hp.group(1)) if hp else "",
            "texte": texte}


def webengine_text(uebersicht_html: str, seiten: dict[str, str], abgerufen: str) -> str:
    """Inhalt von ``QtWebEngine-THIRD-PARTY.txt``.

    ``seiten``: ``{Dateiname der Seite: HTML}`` fuer JEDEN Eintrag der Tabelle —
    fehlt einer, bricht das ab (eine unvollstaendige Aufstellung waere schlechter
    als keine, weil sie vollstaendig aussieht).
    """
    version = doku_version(uebersicht_html)
    eintraege = eintraege_der_uebersicht(uebersicht_html)
    if not eintraege:
        raise ValueError("Tabelle „Third-Party Licenses“ nicht gefunden")
    fehlen = [s for s, _n, _l in eintraege if s not in seiten]
    if fehlen:
        raise ValueError(f"{len(fehlen)} Attributions-Seiten fehlen, z. B. {fehlen[:3]}")
    trenn = "=" * 78
    z = [
        "Qt WebEngine (Chromium) — Fremdbibliotheken und ihre Lizenzen",
        trenn,
        "",
        f"{KOPF_WEBENGINE} {version}",
        f"Quelle: {WEBENGINE_DOKU}{WEBENGINE_UEBERSICHT} (Abschnitt "
        "„Third-Party Licenses“) und die dort verlinkten Seiten je Bibliothek",
        f"Abgerufen: {abgerufen}",
        f"Eintraege: {len(eintraege)}",
        "",
        "Qt WebEngine (Qt6WebEngineCore.dll, QtWebEngineProcess.exe und die Dateien",
        "unter PySide6/resources/) enthaelt den Browser-Kern Chromium und die unten",
        "aufgefuehrten Bibliotheken. Die PySide6-Pakete bringen diese Aufstellung",
        "nicht mit; sie stammt unveraendert aus der Dokumentation von Qt WebEngine",
        "in genau der Version, die im Setup steckt (Kopfzeile oben; der Bau von",
        "LightOS prueft sie gegen Qt6WebEngineCore.dll). Erzeugt mit",
        "packaging/windows/fremdlizenzen_sammeln.py — nicht von Hand bearbeiten.",
        "",
        "Hinweis von Qt zu dieser Aufstellung: GPL-Lizenzen darin betreffen nur",
        "den Zugriff auf Systemdienste unter Linux; die Qt-WebEngine-Bibliotheken",
        "binden keinen GPL-Code ein und liefern keinen mit.",
        "",
        f"Quelltext: Qt WebEngine {WEBENGINE_QUELLE} (Zweig {version}),",
        f"Chromium in der Fassung von Qt {WEBENGINE_CHROMIUM_QUELLE}.",
        "",
        "Inhalt",
        "------",
    ]
    for _s, name, lizenz in eintraege:
        z.append(f"  {name} — {lizenz}")
    for seite, name, lizenz in eintraege:
        a = lies_attribution(seiten[seite])
        z += ["", "", trenn, a["name"] or name, trenn, f"Lizenz: {lizenz}"]
        if a["homepage"]:
            z.append(f"Projektseite: {a['homepage']}")
        for t in a["texte"]:
            z += ["", t.rstrip()]
    return "\n".join(z).rstrip() + "\n"


def holen(ordner: str, warten: float = 0.2) -> None:
    """Laedt Uebersicht und alle Attributions-Seiten nach ``ordner`` (Netz)."""
    os.makedirs(ordner, exist_ok=True)

    def lade(name: str) -> str:
        with urllib.request.urlopen(WEBENGINE_DOKU + name, timeout=60) as r:
            daten = r.read()
        with open(os.path.join(ordner, name), "wb") as f:
            f.write(daten)
        return daten.decode("utf-8")

    uebersicht = lade(WEBENGINE_UEBERSICHT)
    seiten = seiten_der_uebersicht(uebersicht)
    for i, s in enumerate(seiten, 1):
        lade(s)
        print(f"  {i}/{len(seiten)} {s}")
        time.sleep(warten)
    with open(os.path.join(ordner, "ABGERUFEN"), "w", encoding="utf-8") as f:
        f.write(datetime.date.today().isoformat() + "\n")


def webengine_aus_ordner(ordner: str) -> str:
    def lies(name: str) -> str:
        with open(os.path.join(ordner, name), encoding="utf-8") as f:
            return f.read()
    uebersicht = lies(WEBENGINE_UEBERSICHT)
    seiten = {s: lies(s) for s, _n, _l in eintraege_der_uebersicht(uebersicht)
              if os.path.isfile(os.path.join(ordner, s))}
    try:
        abgerufen = lies("ABGERUFEN").strip()
    except OSError:
        abgerufen = "unbekannt"
    return webengine_text(uebersicht, seiten, abgerufen)


# ── Mesa llvmpipe (opengl32sw.dll) ───────────────────────────────────────────

#: Was in ``opengl32sw.dll`` der PySide6-Pakete steckt. Nachgelesen in der Datei
#: selbst (PySide6_Essentials 6.12.0, win_amd64): Versionskennung „Mesa 11.2.2“,
#: „llvm-mc (based on LLVM 3.6.2)“. Bis auf die Signatur gleich der Datei aus
#: Qts Archiv ``opengl32sw-64-mesa_11_2_2-signed_sha256.7z`` (unten).
MESA_VERSION = "11.2.2"
LLVM_VERSION = "3.6.2"
MESA_ARCHIV = ("https://archive.mesa3d.org/older-versions/11.x/11.2.2/"
               "mesa-11.2.2.tar.xz")
LLVM_ARCHIV = "https://releases.llvm.org/3.6.2/llvm-3.6.2.src.tar.xz"
QT_LLVMPIPE = ("https://download.qt.io/development_releases/prebuilt/llvmpipe/"
               "windows/opengl32sw-64-mesa_11_2_2-signed_sha256.7z")

_MIT_ANFANG = "Copyright (C) 1999-2007  Brian Paul"


def _tar_text(archiv: str, endung: str) -> tuple[str, str]:
    """``(Pfad im Archiv, Text)`` des einen Mitglieds, dessen Pfad auf ``endung``
    endet (unter dem obersten Ordner)."""
    with tarfile.open(archiv) as t:
        for m in t.getmembers():
            teile = m.name.split("/", 1)
            if m.isfile() and len(teile) == 2 and teile[1] == endung:
                f = t.extractfile(m)
                return m.name, f.read().decode("utf-8", errors="replace")
    raise ValueError(f"{os.path.basename(archiv)}: {endung} fehlt")


def _kommentarkopf(quelltext: str) -> str:
    """Der erste ``/* … */``-Block, ohne die Sternchen am Zeilenanfang."""
    m = re.search(r"/\*+(.*?)\*/", quelltext, re.S)
    if not m:
        raise ValueError("kein Kommentarkopf")
    zeilen = [re.sub(r"^\s?\*+ ?", "", z).rstrip() for z in m.group(1).splitlines()]
    return "\n".join(zeilen).strip("\n")


def mesa_mit_text(license_html: str) -> str:
    """Die Standard-Lizenz von Mesa aus ``docs/license.html`` (MIT)."""
    m = re.search(r"<pre>\s*(" + re.escape(_MIT_ANFANG) + r".*?)</pre>", license_html, re.S)
    if not m:
        raise ValueError("docs/license.html: MIT-Text von Mesa nicht gefunden")
    return html.unescape(m.group(1)).strip()


def mesa_text(mesa_archiv: str, llvm_archiv: str) -> str:
    """Inhalt von ``Mesa-opengl32sw.txt`` aus den beiden Original-Quellarchiven."""
    def sha(p: str) -> str:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()

    _p, version = _tar_text(mesa_archiv, "VERSION")
    if version.strip() != MESA_VERSION:
        raise ValueError(f"Mesa-Archiv hat Version {version.strip()}, erwartet {MESA_VERSION}")
    _p, lic_html = _tar_text(mesa_archiv, "docs/license.html")
    _p, threads = _tar_text(mesa_archiv, "include/c11/threads_win32.h")
    _p, mlaa = _tar_text(mesa_archiv, "src/gallium/auxiliary/postprocess/pp_mlaa.c")
    pfad, llvm = _tar_text(llvm_archiv, "LICENSE.TXT")
    if pfad.split("/", 1)[0] != f"llvm-{LLVM_VERSION}.src":
        raise ValueError(f"LLVM-Archiv ist nicht {LLVM_VERSION}: {pfad}")
    _p, regex = _tar_text(llvm_archiv, "lib/Support/COPYRIGHT.regex")
    _p, md5 = _tar_text(llvm_archiv, "lib/Support/MD5.cpp")
    trenn = "=" * 78
    md5_kopf = _kommentarkopf(md5)
    z = [
        "Mesa llvmpipe (opengl32sw.dll) — Lizenzen",
        trenn,
        "",
        f"{KOPF_MESA} {MESA_VERSION}",
        f"LLVM-Version: {LLVM_VERSION} (statisch eingebunden)",
        "",
        "opengl32sw.dll liegt den PySide6-Paketen bei (OpenGL in Software; Qt laedt",
        "sie nur, wenn kein Grafiktreiber-OpenGL verfuegbar ist oder Software-OpenGL",
        "verlangt wird). Qt baut sie nicht selbst mit, sondern legt einen fertigen",
        "Bau von Mesa bei:",
        f"  {QT_LLVMPIPE}",
        "Die Datei nennt sich selbst „Mesa 11.2.2“ und enthaelt LLVM 3.6.2 (Text",
        "„llvm-mc (based on LLVM 3.6.2)“); der Bau von LightOS prueft die",
        "Mesa-Version gegen die Kopfzeile oben.",
        "",
        "Quelltext (Originalarchive, aus denen die Texte unten stammen):",
        f"  Mesa {MESA_VERSION}: {MESA_ARCHIV}",
        f"    SHA-256 {sha(mesa_archiv)}",
        f"  LLVM {LLVM_VERSION}: {LLVM_ARCHIV}",
        f"    SHA-256 {sha(llvm_archiv)}",
        "",
        "Welche Lizenzen gelten: Mesa steht ueberwiegend unter der MIT-Lizenz",
        "(docs/license.html, unten); einzelne Dateien haben eigene Lizenzen. Fuer die",
        "Teile, aus denen der Windows-Bau von opengl32sw.dll besteht (Ziel",
        "„libgl-gdi“: src/mesa, src/compiler, src/mapi, src/util, src/gallium mit",
        "llvmpipe, softpipe, trace, rbug, wgl, gdi), wurden die Kopfzeilen der",
        "Quelldateien durchgesehen: ausser MIT kommen vor die Boost Software",
        "License 1.0 (C11-Thread-Emulation, include/c11/threads_win32.h), eine",
        "BSD-Lizenz (Jimenez's MLAA, src/gallium/auxiliary/postprocess) und die",
        "Ausnahmeklausel von GNU Bison in erzeugten Parser-Dateien (sie stellt den",
        "erzeugten Code frei). Die Datei docs/COPYING des Mesa-Archivs enthaelt",
        "ausserdem den Text der GNU Library GPL 2 mit dem Satz „Some parts of Mesa",
        "are copyrighted under the GNU LGPL“; in den oben genannten Teilen fand",
        "sich keine Datei unter dieser Lizenz. LLVM steht unter der University of",
        "Illinois/NCSA Open Source License; von seinen Fremdteilen betrifft den",
        "eingebundenen Teil (LLVMSupport) der regex-Code aus OpenBSD (Henry",
        "Spencer) und die MD5-Implementierung (gemeinfrei/BSD-artig).",
        "",
        "Erzeugt mit packaging/windows/fremdlizenzen_sammeln.py — nicht von Hand",
        "bearbeiten.",
        "",
        "",
        trenn,
        "Mesa — Standardlizenz (MIT), aus docs/license.html",
        trenn,
        "",
        mesa_mit_text(lic_html),
        "",
        "",
        trenn,
        "Mesa — C11-Thread-Emulation, include/c11/threads_win32.h (BSL-1.0)",
        trenn,
        "",
        _kommentarkopf(threads),
        "",
        "",
        trenn,
        "Mesa — Jimenez's MLAA, src/gallium/auxiliary/postprocess/pp_mlaa.c (BSD)",
        trenn,
        "",
        "Uses Jimenez's MLAA. Copyright (C) 2010 by Jorge Jimenez, Belen Masia,",
        "Jose I. Echevarria, Fernando Navarro and Diego Gutierrez.",
        "",
        _kommentarkopf(mlaa),
        "",
        "",
        trenn,
        f"LLVM {LLVM_VERSION} — LICENSE.TXT",
        trenn,
        "",
        llvm.strip("\n"),
        "",
        "",
        trenn,
        "LLVM — lib/Support/COPYRIGHT.regex (OpenBSD regex)",
        trenn,
        "",
        regex.strip("\n"),
        "",
        "",
        trenn,
        "LLVM — lib/Support/MD5.cpp (Kopf)",
        trenn,
        "",
        md5_kopf,
    ]
    return "\n".join(z).rstrip() + "\n"


def _schreibe(ziel: str, text: str) -> None:
    with open(ziel, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"geschrieben: {ziel} ({len(text.splitlines())} Zeilen)")


def main(argv=None) -> int:
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = p.add_subparsers(dest="was", required=True)
    w = sub.add_parser("webengine")
    w.add_argument("--ordner", required=True, help="Ordner mit den Doku-Seiten")
    w.add_argument("--holen", action="store_true", help="Seiten vorher laden (Netz)")
    m = sub.add_parser("mesa")
    m.add_argument("--mesa", required=True, help=f"Archiv {MESA_ARCHIV}")
    m.add_argument("--llvm", required=True, help=f"Archiv {LLVM_ARCHIV}")
    a = p.parse_args(argv)
    if a.was == "webengine":
        if a.holen:
            holen(a.ordner)
            return 0
        _schreibe(os.path.join(repo, "licenses", DATEI_WEBENGINE),
                  webengine_aus_ordner(a.ordner))
    else:
        _schreibe(os.path.join(repo, "licenses", DATEI_MESA), mesa_text(a.mesa, a.llvm))
    return 0


if __name__ == "__main__":
    sys.exit(main())
