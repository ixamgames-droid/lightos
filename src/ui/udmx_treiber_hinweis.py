"""OUT-76: Was der Reiter „uDMX (USB)“ sagt, wenn unter Windows der Treiber fehlt.

**Der Befund.** uDMX-Adapter haben unter Windows keinen eigenen Treiber. Die
Adapter-Liste zeigte einen angesteckten Adapter trotzdem, als waere alles in
Ordnung; erst nach „Verbinden“ stand da „lässt sich nicht öffnen“ — mit einem
einzelnen Satz statt eines Wegs. Im LightOS aus dem Installationspaket hiess es
sogar „pip install pyusb“, was dort niemand ausfuehren kann.

**Die Regel des Projekts.** LightOS liefert und installiert NIE Treiber. Es
erkennt, was fehlt, erklaert den Weg Schritt fuer Schritt und verlinkt die
Seite des Anbieters. Geoeffnet wird ein Link nur durch einen Klick.

Reine Texte ohne Widgets — die Schritte selbst stehen in
``udmx.windows_treiber_schritte`` (eine Quelle fuer Dialog, Diagnosepaket und
INSTALL.md).
"""
from __future__ import annotations

import re
from html import escape

from src.core.dmx import udmx
from src.core.dmx.udmx_treiber_text import befund_satz, ohne_treiber

_LINK = re.compile(r"https://[^\s<>()]+[^\s<>().,;:]")


def _mit_links(text: str) -> str:
    """Text maskieren und Adressen anklickbar machen."""
    return _LINK.sub(lambda m: f'<a href="{m.group(0)}">{m.group(0)}</a>',
                     escape(text, quote=False))


def schritte_html(kennung: str = "", einleitung: str = "", zusatz: str = "") -> str:
    """Die Schritte als HTML fuer das Hinweisfeld (Links anklickbar)."""
    teile = ["<html>"]
    if einleitung:
        teile.append(f"<p><b>{_mit_links(einleitung)}</b></p>")
    teile.append(
        "<p>Windows bringt für uDMX-Adapter keinen Treiber mit, und LightOS "
        "liefert und installiert keinen. Dem Adapter muss einmalig von Hand "
        "der allgemeine Treiber „WinUSB“ zugewiesen werden:</p>")
    teile.append("<ol>" + "".join(
        f"<li>{_mit_links(s)}</li>"
        for s in udmx.windows_treiber_schritte(kennung)) + "</ol>")
    teile.append(f"<p>{_mit_links(udmx.windows_treiber_achtung())}</p>")
    teile.append(
        f"<p>Hintergrund bei Microsoft: {_mit_links(udmx.LINK_WINUSB)} · "
        f"dieselben Schritte stehen in INSTALL.md, Abschnitt „uDMX-Adapter“. "
        f"Noch nicht an einem Gerät unter Windows erprobt — klappt es nicht, "
        f"einen Art-Net-/sACN-Node oder einen ENTTEC DMX USB Pro verwenden.</p>")
    if zusatz:
        teile.append(f"<p>{_mit_links(zusatz)}</p>")
    teile.append("</html>")
    return "".join(teile)


def nach_suche(ergebnis: dict) -> tuple[str, str] | None:
    """``(status, hinweis_html)``, wenn ein angesteckter Adapter am Treiber
    scheitert — sonst ``None`` (dann gilt die bisherige Anzeige).

    ``ergebnis`` = Rueckgabe von ``output_config._udmx_suchen``; gelesen
    werden ``treiber`` (Befunde als Daten) und ``code``/``text`` (fehlt
    zusaetzlich pyusb, steht das als zweiter Absatz dabei).
    """
    betroffen = ohne_treiber(ergebnis.get("treiber"))
    if not betroffen:
        return None
    erster = betroffen[0]
    einleitung = befund_satz(erster)
    if len(betroffen) > 1:
        einleitung += f" Das gilt für {len(betroffen)} angesteckte Adapter."
    zusatz = ""
    code = int(ergebnis.get("code") or udmx.G_OK)
    if code in (udmx.G_PYUSB_FEHLT, udmx.G_LIBUSB_FEHLT):
        zusatz = "Außerdem: " + str(ergebnis.get("text") or udmx.grund_text(code))
    if not erster.get("sicher", True):
        zusatz = ("Nur zuweisen, wenn das Gerät sicher dein uDMX-Adapter ist — "
                  "die Kennung tragen auch andere Bastelgeräte. " + zusatz).strip()
    wort = "Treiber fehlt" if erster.get("lage") == udmx.T_FEHLT else "falscher Treiber"
    anzahl = "1 Adapter" if len(betroffen) == 1 else f"{len(betroffen)} Adapter"
    status = f"{anzahl} am USB gefunden — {wort} (Windows), Schritte unten"
    return status, schritte_html(erster.get("kennung") or "", einleitung, zusatz)
