"""QA-121 (Fund 3): README-Linux-Paketliste deckt sich mit INSTALL.md.

PySide6 >= 6.5 braucht fuer das X11-Plugin ``xcb`` das Systempaket
``libxcb-cursor0``. INSTALL.md nennt es, die README-Kurzfassung nicht — wer nur
der README folgt, bekam beim ersten Start „Could not load the Qt platform
plugin "xcb"“. Reiner Text-Test.
"""
from __future__ import annotations

import pathlib
import re

_WURZEL = pathlib.Path(__file__).resolve().parents[1]


def _apt_pakete(text: str) -> set[str]:
    pakete: set[str] = set()
    for m in re.finditer(r"apt-get install -y((?:[^\n]*\\\n)*[^\n]*)", text):
        pakete |= {w for w in m.group(1).replace("\\", " ").split() if not w.startswith("-")}
    return pakete


def _abschnitt(text: str, kopf: str) -> str:
    i = text.index(kopf)
    rest = text[i + len(kopf):]
    m = re.search(r"\n#{1,3} ", rest)
    return rest[: m.start()] if m else rest


def test_readme_linux_pakete_enthalten_xcb_cursor_und_sind_teil_von_install():
    readme = (_WURZEL / "README.md").read_text(encoding="utf-8")
    install = (_WURZEL / "INSTALL.md").read_text(encoding="utf-8")
    r = _apt_pakete(_abschnitt(readme, "### Linux"))
    i = _apt_pakete(install)
    assert r, "README: kein apt-get-Block im Linux-Abschnitt gefunden"
    assert "libxcb-cursor0" in i, "INSTALL.md nennt libxcb-cursor0 nicht mehr"
    assert "libxcb-cursor0" in r, "README: libxcb-cursor0 fehlt (Qt-xcb-Plugin)"
    assert r <= i, f"README nennt Pakete, die INSTALL.md nicht kennt: {sorted(r - i)}"


def test_readme_erklaert_xcb_cursor():
    readme = (_WURZEL / "README.md").read_text(encoding="utf-8")
    abschnitt = _abschnitt(readme, "### Linux")
    assert re.search(r"`libxcb-cursor0`[^\n]*xcb", abschnitt), \
        "README: Halbsatz, wozu libxcb-cursor0 dient, fehlt"
