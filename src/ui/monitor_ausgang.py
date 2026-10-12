"""OUT-75: was der DMX-Monitor ueber den Ausgang des gezeigten Universums sagt.

**Der Befund (Bedientest QA-96).** Der Monitor meldete gruen „Universe 1 geht
raus“, waehrend Statusleiste und Banner fuer dasselbe Universum „sendet NICHT“
zeigten. Er fragte nur ``sendet_wirklich`` (ist ein Adapter REGISTRIERT?) und
die Fehlerserie des Sendens — nicht den Zustand des Geraets. Ein Enttec auf
einem Anschluss, der sich nicht oeffnen laesst, ist registriert, wirft beim
Senden nichts und sendet trotzdem nicht.

**Eine Wahrheit.** Die Regel hier liest dieselbe Quelle wie Statusleiste
(``ausgabe_label.py``) und Banner (``ausgabe_banner.py``):
``OutputManager.ausgabe_status()``, in der Geraetezustand und Fehlerserie schon
zusammengefuehrt sind. Den Grund eines Ausfalls formuliert dieselbe Funktion wie
im Banner.

Reine Rechnung ohne Widgets — die Ansicht setzt nur Text, Farbe und Tooltip.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.ui.ausgabe_banner import _grund, _weg_name

STIL_OK = "color: #9DFF52; font-size: 11px;"
STIL_KAPUTT = "color: #ff4444; font-size: 11px;"
STIL_FEHLT = "color: #ffb454; font-size: 11px;"
STIL_NEUTRAL = "color: #b0b6c0; font-size: 11px;"

ART_LEER = ""
ART_NICHT_ANGELEGT = "nicht_angelegt"
ART_OHNE_AUSGANG = "ohne_ausgang"
ART_SENDET_NICHT = "sendet_nicht"
ART_VERBINDET = "verbindet"
ART_ROHWERTE = "rohwerte"
ART_GEHT_RAUS = "geht_raus"


@dataclass(frozen=True)
class Aussage:
    art: str = ART_LEER
    text: str = ""
    stil: str = "font-size: 11px;"
    tooltip: str = ""


KEINE = Aussage()


def aussage(universum: int, wege, gesendet: bool, angelegt: bool = True) -> Aussage:
    """Die Zeile neben der Universums-Auswahl.

    ``wege`` — ``OutputManager.ausgabe_status()`` (alle Universen; gefiltert
    wird hier). ``gesendet`` — es gibt schon einen gesendeten Frame.
    ``angelegt`` — das Universum existiert ueberhaupt.

    Reihenfolge: was am staerksten von „hier kommt etwas an“ abweicht, gewinnt.
    """
    if not angelegt:
        return Aussage(
            ART_NICHT_ANGELEGT,
            f"Universe {universum} ist nicht angelegt — keine Werte",
            STIL_NEUTRAL,
            "In diesem Universum ist kein Gerät gepatcht, und kein Ausgang ist "
            "dafür eingerichtet. Es wird nichts gerechnet und nichts gesendet.")
    meine = [w for w in (wege or []) if w.get("universum") == universum]
    if not meine:
        return Aussage(
            ART_OHNE_AUSGANG,
            f"⚠ Universe {universum} hat keinen Ausgang — nur gerechnet",
            STIL_FEHLT,
            "Diese Werte berechnet LightOS, aber kein Adapter gibt sie "
            "aus. In den Output-Einstellungen einen Ausgang zuweisen.")
    kaputt = [w for w in meine if w.get("verbunden") is False]
    if kaputt:
        text = f"⚠ Universe {universum}: {kaputt[0].get('weg')} sendet NICHT"
        if len(kaputt) > 1:
            text += f" (+{len(kaputt) - 1} weitere)"
        laeuft = [w for w in meine if w.get("verbunden") is not False]
        if laeuft:
            text += " — " + ", ".join(str(w.get("weg")) for w in laeuft) + " geht raus"
        return Aussage(ART_SENDET_NICHT, text, STIL_KAPUTT,
                       "\n".join(f"{_weg_name(w)}: {_grund(w)}" for w in kaputt))
    wartet = [w for w in meine if w.get("zustand") == "verbindet"]
    if wartet:
        return Aussage(
            ART_VERBINDET,
            f"Universe {universum}: {wartet[0].get('weg')} verbindet …",
            STIL_FEHLT,
            "Der Port wird gerade geöffnet. Bleibt es dabei, ist der Adapter "
            "nicht erreichbar.")
    if not gesendet:
        return Aussage(ART_ROHWERTE,
                       f"Universe {universum}: Rohwerte (noch kein Frame gesendet)",
                       STIL_NEUTRAL)
    return Aussage(ART_GEHT_RAUS, f"Universe {universum} geht raus", STIL_OK)


def weg_text(eintrag: dict) -> str:
    """Ein Ausgabeweg in der Auswahl „Ausgang“: „Art-Net → 2.0.0.1“."""
    weg, ziel = str(eintrag.get("weg") or ""), str(eintrag.get("ziel") or "")
    return f"{weg} → {ziel}" if ziel else weg


def sperre_text(gesperrt: int) -> str:
    """Zusatz, wenn der gezeigte Ausgang wegen der NOT-AUS-Sperre des
    Ausgabewegs etwas anderes sendet als gerechnet."""
    if gesperrt <= 0:
        return ""
    wort = "Adresse" if gesperrt == 1 else "Adressen"
    return f" · NOT-AUS-Sperre auf diesem Ausgang: {gesperrt} {wort}"
