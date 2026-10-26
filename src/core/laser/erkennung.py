"""LAS-37: EINE Antwort auf „ist in diesem Geraet ein Laser?“ — fuer alle
Sicherheits-Stellen.

Bis hierher gab es drei Antworten:

* NOT-AUS-Adressen, der Zaehler am NOT-AUS-Knopf und die Aus-Maske nahmen nur
  ``fixture_type == 'laser'`` oder einen ``laser_*``-Kanal;
* Blackout und „Alles Weiss“ erkannten zusaetzlich am NAMEN des Geraets
  (``all_white.ist_geraet_ohne_licht``);
* niemand sah auf die Namen der KANAELE.

Folge an einem Geraet der mitgelieferten Bibliothek (Eurolite „LED KLS Laser
Bar FX Light Set“: Typ ``other``, Kanaele „Laser: Red“/„Laser: Green“ mit
Attribut ``raw``): LASER NOT-AUS gedrueckt, der Knopf meldet „verriegelt“ — der
Laser der Bar leuchtet weiter. Der Blackout schaltete ihn dagegen dunkel.

Hier steht deshalb die EINE, weite Regel. Ein Geraet gilt als Laser, wenn

1. sein Typ ``laser`` ist, oder
2. es einen Kanal mit Attribut ``laser_*`` hat, oder
3. ein Kanal „Laser“ im NAMEN traegt („Laser: Red“, „Laser Helligkeit“), oder
4. „Laser“ im Geraete-, Hersteller- oder Patch-Namen steht, oder
5. (LAS-38) ein ANDERER Modus desselben Profils einen Laserkanal nach 2 oder 3
   hat — das Geraet enthaelt dann einen Laser, auch wenn der gepatchte Modus
   ihn nicht einzeln fuehrt.

Im Zweifel gilt ein Geraet als Laser: ein zu Unrecht dunkel geschaltetes
Lichtset ist ein Aergernis, ein Laser, der trotz NOT-AUS strahlt, eine Gefahr.

**Was diese Regel NICHT ist:** die Frage, ob ein Geraet wie ein Laser BEDIENT
wird (Laser-Tab, Musterkacheln). Die beantwortet weiter
``capability.is_laser_fixture`` mit der engen Regel (1 + 2) — ein Moving Head
mit eingebauter Laserdiode bleibt in der Bedienung ein Moving Head, zaehlt aber
fuer NOT-AUS, Blackout und „Alles Weiss“ als Laser.

**Kurz-Modi (LAS-38).** Bis dahin sah die Regel nur die Kanaele des
gepatchten MODUS. Ein Kombigeraet in einem Kurz-Modus ohne eigenen Laserkanal
(Chauvet GigBAR 2 „3-channel“, Cameo Multi FX Bar „2 Channel“ — der Laser
laeuft dort ueber Automatikprogramme) fiel durch, wenn weder Typ noch Name
„Laser“ sagten: der NOT-AUS liess es weiterlaufen. Regel 5 schliesst das. Ob
ein Profil in irgendeinem Modus einen Laserkanal hat, wird je Profil EINMAL
bestimmt und hier gemerkt (``merke_profil``); der Render-Plan liest nur noch.

**Fehlende Auskunft (LAS-39).** Ist die Geraete-Datenbank beim Patchen nicht
erreichbar, fehlt die Antwort fuer Regel 5. Bis LAS-38 galt dann „nein“ — ein
Kombigeraet im Kurz-Modus lief bei einem DANACH ausgeloesten NOT-AUS weiter.
Jetzt gilt: Auskunft fehlt -> das Geraet gilt VORERST als Laser
(``GRUND_PROFIL_UNBEKANNT``) und das Profil steht in der Liste der offenen
Profile (``offene_profile``). Gemerkt wird nichts; die Auskunft wird bei der
naechsten Gelegenheit nachgeholt (naechster Plan-Neubau, naechstes Ausloesen
des NOT-AUS — kein Abfragen im Takt). Eine normale Lampe ist damit nur so
lange mit dunkel, wie die Datenbank fehlt; ``hinweis_unvollstaendig`` liefert
den Satz, der das dem Betreiber sagt.

Blattmodul: kein Qt, keine Abhaengigkeit auf ``app_state`` — und die Datenbank
fragt es nicht selbst. Wer die Profile kennt (``app_state``), traegt die Antwort
ein oder meldet eine Quelle an (``setze_profil_quelle``), die fuer ein noch
unbekanntes Profil einmal gefragt wird.
"""
from __future__ import annotations

import re

#: „laser“ irgendwo im Text — bewusst ohne Wortgrenze („Laserworld“,
#: „Showlaser“, „Laser-Bar“); dieselbe Schreibweise wie bisher in
#: ``all_white._OHNE_LICHT_NAME``.
_LASER = re.compile(r"laser", re.IGNORECASE)

GRUND_TYP = "typ"
GRUND_KANAL = "kanal"               # Attribut laser_*
GRUND_KANALNAME = "kanalname"       # „Laser“ im Namen eines Kanals
GRUND_NAME = "name"                 # „Laser“ im Geraete-/Hersteller-/Patch-Namen
GRUND_ANDERER_MODUS = "anderer_modus"   # LAS-38: Laserkanal in einem anderen Modus
#: LAS-39: die Profil-Auskunft fehlt (Geraete-Datenbank nicht erreichbar) —
#: im Zweifel Laser, bis sie nachgeholt ist.
GRUND_PROFIL_UNBEKANNT = "profil_unbekannt"

#: Die Gruende, bei denen weder der Typ noch ein ``laser_*``-Kanal des
#: gepatchten Modus „Laser“ sagen — das Geraet gilt ueber einen Namen oder ueber
#: einen anderen Modus seines Profils als Laser (Hinweis beim Patchen). Den
#: NOT-AUS loest seit LAS-36 ohnehin kein Wert mehr, an keinem Geraet.
NUR_NAME = frozenset((GRUND_KANALNAME, GRUND_NAME, GRUND_ANDERER_MODUS,
                      GRUND_PROFIL_UNBEKANNT))

_NAMENSFELDER = ("fixture_name", "label", "manufacturer_name")


def _attr(ch) -> str:
    return (getattr(ch, "attribute", "") or "").lower()


def ist_laserkanal(ch) -> bool:
    """Traegt DIESER Kanal einen Laser — per Attribut ``laser_*`` oder per
    Kanalname?"""
    return _attr(ch).startswith("laser_") or bool(
        _LASER.search(str(getattr(ch, "name", "") or "")))


# ── LAS-38: was das PROFIL ueber alle seine Modi sagt ───────────────────────

#: Profil-ID -> hat in irgendeinem Modus einen Laserkanal. Je Profil einmal
#: bestimmt (beim Patchen/Laden) und zusammen mit dem Kanal-Cache verworfen.
_profil_laser: dict = {}
_profil_quelle = None
#: LAS-39: Profile, deren Auskunft zuletzt FEHLTE (Quelle warf oder wusste es
#: nicht). Sie gelten vorerst als Laser; beantwortet -> wieder heraus.
_profil_offen: set = set()


def setze_profil_quelle(quelle) -> None:
    """Meldet an, wer ein noch unbekanntes Profil beantwortet:
    ``quelle(profil_id) -> bool`` (``None`` = weiss es nicht, nicht merken)."""
    global _profil_quelle
    _profil_quelle = quelle


def merke_profil(profil_id, hat_laser: bool) -> None:
    """Traegt die Antwort fuer ein Profil ein."""
    if profil_id is not None:
        _profil_laser[profil_id] = bool(hat_laser)
        _profil_offen.discard(profil_id)


def merke_offen(profil_id) -> None:
    """LAS-39: die Auskunft fuer dieses Profil fehlt (Abfrage gescheitert) —
    nichts merken, aber als offen fuehren."""
    if profil_id is not None and profil_id not in _profil_laser:
        _profil_offen.add(profil_id)


def offene_profile() -> frozenset:
    """LAS-39: Profile, deren Auskunft fehlt (sie gelten vorerst als Laser)."""
    return frozenset(_profil_offen)


def profil_bekannt(profil_id) -> bool:
    return profil_id in _profil_laser


def vergiss_profile() -> None:
    """Alle gemerkten Antworten verwerfen (Profil geaendert, Patch neu geladen).

    Codex-Review #1095: OFFENE Profile bleiben offen — ihre Auskunft fehlt ja
    weiterhin. ``clear_channel_cache`` ruft das hier; leerte es auch
    ``_profil_offen``, kehrte ``laser_erkennung_nachholen`` sofort zurueck, und
    der Hinweis verschwand, waehrend der alte Plan das Geraet weiter als Laser
    fuehrte — ohne Rueckweg bis zum naechsten Neuaufbau."""
    _profil_laser.clear()


def zuruecksetzen() -> None:
    """Alles vergessen, auch die offenen Profile — fuer einen frischen Anfang
    (Testlauf), nicht fuer den Kanal-Cache (dort :func:`vergiss_profile`)."""
    _profil_laser.clear()
    _profil_offen.clear()


def kanaele_tragen_laser(kanaele) -> bool:
    """Hat diese Kanal-Liste (EIN Modus) einen Laserkanal nach Regel 2 oder 3?"""
    return any(ist_laserkanal(ch) for ch in kanaele or ())


def profil_auskunft(fx):
    """Was sagt das Profil von ``fx``: ``True`` (ein Modus hat einen
    Laserkanal), ``False`` (keiner) oder ``None`` (LAS-39: Auskunft fehlt).

    Liest die gemerkte Antwort. Ist das Profil noch unbekannt, wird die
    angemeldete Quelle gefragt und die Antwort gemerkt. Bei einem Fehler oder
    bei „weiss nicht“ wird NICHTS gemerkt, das Profil aber als offen gefuehrt
    (``None``) — die naechste Frage versucht es erneut. Ohne Geraet-Profil
    oder ohne angemeldete Quelle (Blattmodul allein, keine Datenbank im Spiel)
    bleibt es bei der Regel je Modus (``False``).
    """
    profil_id = getattr(fx, "fixture_profile_id", None)
    if profil_id is None:
        return False
    bekannt = _profil_laser.get(profil_id)
    if bekannt is not None:
        return bekannt
    quelle = _profil_quelle
    if quelle is None:
        return False
    try:
        antwort = quelle(profil_id)
    except Exception:
        antwort = None
    if antwort is None:
        _profil_offen.add(profil_id)
        return None
    merke_profil(profil_id, antwort)
    return bool(antwort)


def profil_traegt_laser(fx) -> bool:
    """Hat das Profil von ``fx`` BEKANNTERMASSEN in irgendeinem Modus einen
    Laserkanal? Eine fehlende Auskunft ist hier „nein“ — wer im Zweifel
    vorsichtig sein muss, fragt ``laser_grund`` (das macht daraus
    ``GRUND_PROFIL_UNBEKANNT``)."""
    return profil_auskunft(fx) is True


def laser_grund(fx, channels=()) -> str:
    """Warum ``fx`` als Laser gilt (``GRUND_*``) — ``""``, wenn nicht.

    ``channels``: die Kanaele des gepatchten Modus (wer sie schon hat, reicht
    sie herein; ohne sie entscheiden nur Typ und Namen)."""
    if (getattr(fx, "fixture_type", "") or "").strip().lower() == "laser":
        return GRUND_TYP
    kanaele = list(channels or ())
    if any(_attr(c).startswith("laser_") for c in kanaele):
        return GRUND_KANAL
    if any(_LASER.search(str(getattr(c, "name", "") or "")) for c in kanaele):
        return GRUND_KANALNAME
    text = " ".join(str(getattr(fx, feld, "") or "") for feld in _NAMENSFELDER)
    if _LASER.search(text):
        return GRUND_NAME
    # LAS-38: zuletzt, damit ein schon erkanntes Geraet seinen Grund behaelt und
    # fuer es kein Profil nachgeschlagen wird.
    auskunft = profil_auskunft(fx)
    if auskunft is True:
        return GRUND_ANDERER_MODUS
    if auskunft is None:
        # LAS-39: Sicherheit vor Bequemlichkeit — ohne Auskunft vorerst Laser.
        return GRUND_PROFIL_UNBEKANNT
    return ""


def ist_laser(fx, channels=()) -> bool:
    """Die eine Antwort fuer NOT-AUS-Maske, Aus-Maske, Blackout, „Alles
    Weiss“, Zaehler und Testsignal-Sperre."""
    return bool(laser_grund(fx, channels))


def nur_ueber_namen(fx, channels=()) -> bool:
    """Gilt ``fx`` NUR ueber einen Namen als Laser (kein Typ, kein
    ``laser_*``-Kanal)? Dann lohnt beim Patchen ein Hinweis."""
    return laser_grund(fx, channels) in NUR_NAME


def hinweis_text(fx, channels=()) -> str:
    """Satz fuer den Hinweis beim Patchen — leer, wenn keiner noetig ist."""
    grund = laser_grund(fx, channels)
    if grund not in NUR_NAME:
        return ""
    name = (str(getattr(fx, "label", "") or "")
            or str(getattr(fx, "fixture_name", "") or "") or "Das Gerät")
    if grund == GRUND_PROFIL_UNBEKANNT:
        return (f"„{name}“ gilt vorerst als Laser: {UNVOLLSTAENDIG} — LASER "
                f"NOT-AUS und Blackout schalten das ganze Gerät dunkel, bis die "
                f"Auskunft des Profils nachgeholt ist.")
    woran = {GRUND_KANALNAME: "an einem Kanalnamen",
             GRUND_ANDERER_MODUS: "an einem Laserkanal in einem anderen Modus "
                                  "des Profils"}.get(grund, "am Namen")
    return (f"„{name}“ gilt als Laser (erkannt {woran}): LASER NOT-AUS und "
            f"Blackout schalten das ganze Gerät dunkel, „Alles Weiß“ lässt es aus.")


#: LAS-39: der Satz fuer Statuszeile und NOT-AUS-Knopf.
UNVOLLSTAENDIG = "Laser-Erkennung unvollständig: Geräte-Datenbank nicht erreichbar"


def hinweis_unvollstaendig(anzahl: int) -> str:
    """LAS-39: Hinweis, wenn fuer ``anzahl`` gepatchte Geraete die
    Profil-Auskunft fehlt — leer bei 0."""
    if anzahl <= 0:
        return ""
    wort = "Gerät gilt" if anzahl == 1 else "Geräte gelten"
    return (f"{UNVOLLSTAENDIG} — {anzahl} {wort} bis dahin als Laser "
            f"(LASER NOT-AUS und Blackout schalten sie dunkel).")


def hinweis_vollstaendig() -> str:
    """LAS-39: Rueckmeldung, sobald die fehlende Auskunft nachgeholt ist."""
    return "Laser-Erkennung wieder vollständig: Geräte-Datenbank antwortet."
