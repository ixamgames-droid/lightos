"""XPLAT-62: baut aus dem PyInstaller-Ordner ein .deb (Mint/Ubuntu/Debian, amd64).

Eingang ist der fertige Programmordner aus ``packaging/linux/LightOS.spec``
(``dist/LightOS/`` mit der Startdatei ``LightOS`` und ``_internal/``). Das
Paket legt ab:

* ``/opt/lightos/``                          — der ganze Programmordner
* ``/usr/bin/lightos``                       — Starter (Shell-Skript)
* ``/usr/share/applications/lightos.desktop`` — Startmenue-Eintrag
* ``/usr/share/icons/hicolor/256x256/apps/lightos.png`` — Symbol
* ``/usr/lib/udev/rules.d/60-lightos-udmx.rules`` — Zugriff auf uDMX-Adapter
* ``/usr/share/doc/lightos/``                — LICENSE, THIRD_PARTY_NOTICES.md,
  die Lizenztexte aus dem Bundle (``licenses/``) und ``copyright``

``postinst`` laedt die udev-Regeln neu und weist auf die Gruppen ``plugdev``
(uDMX) und ``dialout`` (Enttec/FTDI, serielle Ports) hin — Benutzerkonten
aendert das Paket bewusst NICHT. ``postrm`` laedt die Regeln nach dem
Entfernen neu. Benutzerdaten (``~/.local/share/LightOS``) fasst das Paket nie
an, auch nicht beim ``purge``.

Gebaut wird ohne root: ``dpkg-deb --root-owner-group``; Rechte werden vorher
vereinheitlicht (Ordner/ausfuehrbare Dateien 0755, sonst 0644).

Aufruf::

    python packaging/linux/baue_deb.py [--programm dist/LightOS]
        [--ausgabe dist/deb] [--version X.Y.Z]

Ohne ``--version`` gilt ``APP_VERSION`` aus ``main.py`` (wie beim
Windows-Setup). Bewusst ohne LightOS-Importe; laeuft mit der Standardbibliothek.
"""
from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAKET = "lightos"
ARCH = "amd64"
ZIEL_PROGRAMM = "opt/lightos"
STARTDATEI = "LightOS"
REGEL = "60-lightos-udmx.rules"
#: Aus der Repo-Wurzel nach /usr/share/doc/lightos.
DOKU_DATEIEN = ("LICENSE", "THIRD_PARTY_NOTICES.md")

#: Systembibliotheken, die PyInstaller NICHT mitbringt. PyInstaller packt
#: Python, PySide6/Qt (inkl. QtWebEngine), numpy usw. in den Programmordner;
#: was Qt und Chromium aber aus dem System laden, steht hier — knapp gehalten:
#:
#: * ``libc6``            — Grundlage jedes Programms (glibc des Bau-Rechners
#:   ist die Untergrenze; gebaut wird auf ubuntu-22.04, siehe Workflow).
#: * ``libgl1, libegl1``  — OpenGL/EGL fuer Qt und den 3D-Visualizer.
#: * ``libfontconfig1``   — Schriften (Qt laedt fontconfig aus dem System).
#: * ``libxkbcommon-x11-0, libxcb-cursor0`` — Qt-xcb-Plattform (X11); fehlt
#:   ``libxcb-cursor0``, startet Qt >= 6.5 unter X11 gar nicht — auf frischen
#:   Ubuntu-Installationen oft nicht vorhanden.
#: * ``libnss3``          — QtWebEngine (Chromium) braucht NSS aus dem System.
#: * ``libasound2t64 | libasound2`` — ALSA fuer MIDI (python-rtmidi) und
#:   QtWebEngine; Ubuntu 24.04/Mint 22 heissen ``…t64``, aeltere ohne.
#: * ``libusb-1.0-0``     — uDMX-Adapter (pyusb laedt libusb aus dem System).
ABHAENGIGKEITEN = (
    "libc6",
    "libgl1",
    "libegl1",
    "libfontconfig1",
    "libxkbcommon-x11-0",
    "libxcb-cursor0",
    "libnss3",
    "libasound2t64 | libasound2",
    "libusb-1.0-0",
)

STARTER = """#!/bin/sh
# LightOS-Starter (XPLAT-62): startet das Programm aus /opt/lightos.
exec /opt/lightos/LightOS "$@"
"""

#: ``Exec`` bewusst ohne Feldcode (%F/%f): main.py nimmt keine Positions-
#: argumente an — eine auf den Starter gezogene Datei liesse argparse sonst mit
#: Fehler beenden, ohne dass ein Fenster erscheint.
DESKTOP = """[Desktop Entry]
Type=Application
Name=LightOS
GenericName=DMX-Lichtsteuerung
Comment=DMX-Lichtsteuerung fuer Buehne und Veranstaltung
Exec=lightos
Icon=lightos
Terminal=false
Categories=AudioVideo;Video;
Keywords=DMX;Licht;Lichtpult;Light;
StartupNotify=true
StartupWMClass=LightOS
"""

POSTINST = """#!/bin/sh
# LightOS (XPLAT-62): udev-Regeln neu laden, damit uDMX-Adapter ohne root
# laufen. Benutzerkonten aendert das Paket NICHT — nur ein Hinweis.
set -e
if [ "$1" = "configure" ]; then
    if command -v udevadm >/dev/null 2>&1; then
        udevadm control --reload-rules >/dev/null 2>&1 || true
        udevadm trigger --subsystem-match=usb >/dev/null 2>&1 || true
    fi
    echo "LightOS ist installiert (Startmenue oder Befehl 'lightos')."
    echo "Hinweis: Fuer DMX-Interfaces mit seriellem Port (z. B. Enttec/FTDI)"
    echo "braucht das Benutzerkonto die Gruppe 'dialout', fuer uDMX-Adapter"
    echo "'plugdev'. Einmalig von Hand, danach ab- und wieder anmelden:"
    echo "    sudo usermod -aG dialout,plugdev \\"\\$USER\\""
fi
exit 0
"""

POSTRM = """#!/bin/sh
# LightOS (XPLAT-62): nach dem Entfernen die udev-Regeln neu laden.
# Benutzerdaten (~/.local/share/LightOS) bleiben immer erhalten.
set -e
case "$1" in
    remove|purge)
        if command -v udevadm >/dev/null 2>&1; then
            udevadm control --reload-rules >/dev/null 2>&1 || true
        fi
        ;;
esac
exit 0
"""

COPYRIGHT = """Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: LightOS
Comment: Lizenz von LightOS selbst: LICENSE. Die mitgelieferten
 Fremd-Komponenten (Python, Qt/PySide6, QtWebEngine, numpy u. a.) und ihre
 Lizenzen: THIRD_PARTY_NOTICES.md und der Ordner licenses/ in diesem
 Verzeichnis (dieselben Texte liegen auch unter /opt/lightos/_internal/licenses).

Files: *
Copyright: LightOS-Mitwirkende
License: siehe /usr/share/doc/lightos/LICENSE
"""


def app_version(repo: str = REPO) -> str:
    """``APP_VERSION`` aus ``main.py`` — die einzige Versionsquelle."""
    with io.open(os.path.join(repo, "main.py"), encoding="utf-8") as f:
        m = re.search(r"""^APP_VERSION\s*=\s*["']([^"']+)""", f.read(), re.M)
    if not m:
        raise RuntimeError("APP_VERSION nicht in main.py gefunden")
    return m.group(1)


def pruefe_version(version: str) -> str:
    """Debian-Version: muss mit einer Ziffer beginnen, keine Leerzeichen."""
    version = version.strip().lstrip("v")
    if not re.fullmatch(r"[0-9][A-Za-z0-9.+~-]*", version):
        raise ValueError(f"ungueltige Paketversion: {version!r}")
    return version


def control_text(version: str, installiert_kb: int) -> str:
    return (
        f"Package: {PAKET}\n"
        f"Version: {version}\n"
        f"Architecture: {ARCH}\n"
        "Maintainer: LightOS-Projekt <noreply@example.invalid>\n"
        f"Installed-Size: {installiert_kb}\n"
        f"Depends: {', '.join(ABHAENGIGKEITEN)}\n"
        "Section: graphics\n"
        "Priority: optional\n"
        "Homepage: https://github.com/ixamgames-droid/lightos\n"
        "Description: DMX-Lichtsteuerung (Vorabversion)\n"
        " LightOS steuert DMX-Licht ueber Art-Net, sACN, Enttec und uDMX.\n"
        " Das Programm bringt seine eigene Python-Laufzeit mit (/opt/lightos);\n"
        " Benutzerdaten liegen in ~/.local/share/LightOS und bleiben beim\n"
        " Entfernen erhalten.\n"
    )


def _schreibe(pfad: str, text: str, modus: int = 0o644) -> None:
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.chmod(pfad, modus)


def _rechte_vereinheitlichen(wurzel: str) -> None:
    """Ordner und ausfuehrbare Dateien 0755, alles andere 0644 — kein
    gruppen-/weltschreibbares Teil im Paket (dpkg/lintian verlangen das)."""
    for ordner, unterordner, dateien in os.walk(wurzel):
        os.chmod(ordner, 0o755)
        for name in dateien:
            p = os.path.join(ordner, name)
            if os.path.islink(p):
                continue
            ausf = os.stat(p).st_mode & stat.S_IXUSR
            os.chmod(p, 0o755 if ausf else 0o644)


def _groesse_kb(wurzel: str) -> int:
    summe = 0
    for ordner, _u, dateien in os.walk(wurzel):
        for name in dateien:
            p = os.path.join(ordner, name)
            if not os.path.islink(p):
                summe += os.path.getsize(p)
    return max(1, (summe + 1023) // 1024)


def baue_baum(programm: str, baum: str, version: str, repo: str = REPO) -> None:
    """Legt den Paketbaum (inkl. ``DEBIAN/``) unter ``baum`` an."""
    start = os.path.join(programm, STARTDATEI)
    if not os.path.isfile(start):
        raise FileNotFoundError(f"{STARTDATEI} fehlt im Programmordner {programm}")
    ziel = os.path.join(baum, ZIEL_PROGRAMM)
    shutil.copytree(programm, ziel, symlinks=True)
    os.chmod(os.path.join(ziel, STARTDATEI), 0o755)

    _schreibe(os.path.join(baum, "usr", "bin", "lightos"), STARTER, 0o755)
    _schreibe(os.path.join(baum, "usr", "share", "applications", "lightos.desktop"),
              DESKTOP)
    icon_ziel = os.path.join(baum, "usr", "share", "icons", "hicolor", "256x256",
                             "apps", "lightos.png")
    os.makedirs(os.path.dirname(icon_ziel), exist_ok=True)
    shutil.copyfile(os.path.join(repo, "assets", "icons", "lightos.png"), icon_ziel)
    regel_ziel = os.path.join(baum, "usr", "lib", "udev", "rules.d", REGEL)
    os.makedirs(os.path.dirname(regel_ziel), exist_ok=True)
    shutil.copyfile(os.path.join(repo, "packaging", "linux", REGEL), regel_ziel)

    doku = os.path.join(baum, "usr", "share", "doc", PAKET)
    os.makedirs(doku, exist_ok=True)
    for name in DOKU_DATEIEN:
        shutil.copyfile(os.path.join(repo, name), os.path.join(doku, name))
    _schreibe(os.path.join(doku, "copyright"), COPYRIGHT)
    # Fremdlizenzen wie unter Windows: was der PyInstaller-Bau in licenses/
    # gelegt hat, zusaetzlich nach /usr/share/doc (dort sucht man sie).
    for kandidat in (os.path.join(programm, "_internal", "licenses"),
                     os.path.join(programm, "licenses")):
        if os.path.isdir(kandidat):
            shutil.copytree(kandidat, os.path.join(doku, "licenses"))
            break
    else:
        print("baue_deb: WARNUNG keine licenses/ im Programmordner — nur "
              "LICENSE und THIRD_PARTY_NOTICES.md im Paket.", file=sys.stderr)

    _rechte_vereinheitlichen(baum)
    debian = os.path.join(baum, "DEBIAN")
    os.makedirs(debian, exist_ok=True)
    _schreibe(os.path.join(debian, "postinst"), POSTINST, 0o755)
    _schreibe(os.path.join(debian, "postrm"), POSTRM, 0o755)
    kb = _groesse_kb(baum) - _groesse_kb(debian)
    _schreibe(os.path.join(debian, "control"), control_text(version, kb))
    os.chmod(debian, 0o755)


def baue(programm: str, ausgabe: str, version: str | None = None,
         repo: str = REPO) -> str:
    """Baut das .deb und gibt seinen Pfad zurueck."""
    version = pruefe_version(version or app_version(repo))
    os.makedirs(ausgabe, exist_ok=True)
    deb = os.path.join(os.path.abspath(ausgabe), f"{PAKET}_{version}_{ARCH}.deb")
    with tempfile.TemporaryDirectory(prefix="lightos-deb-") as tmp:
        baum = os.path.join(tmp, f"{PAKET}_{version}_{ARCH}")
        baue_baum(os.path.abspath(programm), baum, version, repo)
        subprocess.run(["dpkg-deb", "--root-owner-group", "-Zxz", "--build",
                        baum, deb], check=True, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return deb


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--programm", default=os.path.join(REPO, "dist", "LightOS"),
                   help="PyInstaller-Ordner (Standard: dist/LightOS)")
    p.add_argument("--ausgabe", default=os.path.join(REPO, "dist", "deb"))
    p.add_argument("--version", default=None,
                   help="Paketversion (Standard: APP_VERSION aus main.py)")
    a = p.parse_args(argv)
    try:
        deb = baue(a.programm, a.ausgabe, a.version)
    except subprocess.CalledProcessError as e:
        print(f"baue_deb: FEHLER dpkg-deb: {e.stderr}", file=sys.stderr)
        return 1
    except Exception as e:      # noqa: BLE001 — Meldung + Exit-Code fuer die CI
        print(f"baue_deb: FEHLER {e}", file=sys.stderr)
        return 1
    print(f"baue_deb: {deb}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
