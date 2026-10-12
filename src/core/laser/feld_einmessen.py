"""LAS-35: Laser-Feld einmessen — Verfahren „Wand und Zollstock".

Der Laser zeigt gerade auf eine Wand. Der Nutzer misst den Abstand
Austrittsfenster → Wand und an der Wand, wie weit das Feld von der Mitte (dem
Punkt, in dem die Geraeteachse die Wand trifft) nach links, rechts, oben und
unten reicht. Daraus werden die vier Randwinkel: ``atan(Weg / Abstand)``.

**Gerechnet wird mit dem, was der Nutzer an der Wand abliest — nie mit
DMX-Werten.** Umkehr-Haken, Kanal-Modifier oder eine am Geraet umgestellte
Spiegelung koennen das Ergebnis deshalb nicht verfaelschen.

Zweiter Teil: :class:`FeldSchalter` — das Einzige in diesem Vorhaben, das den
Laser einschalten kann. Es schreibt ausschliesslich ueber
``state.set_programmer_value`` (der normale Bedienweg; LASER NOT-AUS, Blackout
und Grand Master wirken unveraendert) und nur nach ausdruecklicher
Bestaetigung. An der DMX-Ausgabe selbst aendert dieses Modul nichts.

Kein Qt.
"""
from __future__ import annotations

import datetime
import importlib
import math
from dataclasses import dataclass

from src.core.laser import sperrzonen as S

#: Ab diesem Randwinkel fragt der Assistent nach (ungewoehnlich gross).
WINKEL_RUECKFRAGE_GRAD = 60.0
#: Unter diesem Abstand wird das Ablesen ungenau (Rueckfrage).
ABSTAND_KURZ_M = 1.0

RICHTUNGS_WORT = {"links": "nach links", "rechts": "nach rechts",
                  "oben": "nach oben", "unten": "nach unten"}


def de(zahl: float, stellen: int = 2) -> str:
    """Zahl mit Dezimalkomma."""
    return f"{float(zahl):.{stellen}f}".replace(".", ",")


@dataclass
class Messung:
    """Abstand in Metern, die vier Wege an der Wand in Zentimetern."""
    abstand_m: float = 0.0
    links_cm: float = 0.0
    rechts_cm: float = 0.0
    oben_cm: float = 0.0
    unten_cm: float = 0.0

    def weg_cm(self, rand: str) -> float:
        return float(getattr(self, f"{rand}_cm"))


@dataclass
class Rueckfrage:
    """``sperrt`` = so laesst sich nicht rechnen (erst korrigieren); sonst eine
    Frage, die der Nutzer ausdruecklich bestaetigen muss."""
    text: str
    sperrt: bool = False


def _lesbar(wert) -> bool:
    try:
        return math.isfinite(float(wert)) and not isinstance(wert, bool)
    except (TypeError, ValueError):
        return False


def winkel_grad(abstand_m: float, weg_cm: float) -> float:
    """Randwinkel in Grad. Wirft ``ValueError`` bei Abstand <= 0 oder
    negativem Weg — das wird nie stillschweigend zu 0 oder 90 Grad."""
    if not _lesbar(abstand_m) or not _lesbar(weg_cm):
        raise ValueError("Zahl unlesbar")
    abstand, weg = float(abstand_m), float(weg_cm) / 100.0
    if abstand <= 0.0:
        raise ValueError("Abstand muss größer als 0 sein")
    if weg < 0.0:
        raise ValueError("Weg an der Wand darf nicht negativ sein")
    return math.degrees(math.atan(weg / abstand))


def randwinkel(messung: Messung) -> dict:
    """``{"links": Grad, "rechts": …, "oben": …, "unten": …}``."""
    return {rand: winkel_grad(messung.abstand_m, messung.weg_cm(rand))
            for rand in S.RAENDER}


def gegenprobe(abstand_m: float, weg_cm: float, rand: str) -> str:
    """Der Rechenweg in einem Satz, zum Nachrechnen: „bei 4,00 m Abstand und
    1,45 m nach links: 19,9°"."""
    w = winkel_grad(abstand_m, weg_cm)
    return (f"bei {de(abstand_m)} m Abstand und {de(float(weg_cm) / 100.0)} m "
            f"{RICHTUNGS_WORT[rand]}: {de(w, 1)}°")


def rueckfragen(messung: Messung) -> list:
    """Was an der Messung nicht stimmen kann. Leer = plausibel."""
    out: list = []
    if not _lesbar(messung.abstand_m) or float(messung.abstand_m) <= 0.0:
        out.append(Rueckfrage(
            "Abstand Laser → Wand ist 0. Ohne Abstand lässt sich kein Winkel "
            "rechnen — bitte den gemessenen Abstand eintragen.", sperrt=True))
    negativ = [r for r in S.RAENDER
               if not _lesbar(messung.weg_cm(r)) or messung.weg_cm(r) < 0.0]
    if negativ:
        out.append(Rueckfrage(
            "Negativer Wert bei " + ", ".join(negativ) + ". Gemessen wird immer "
            "von der Mitte nach außen — bitte als positive Zahl eintragen.",
            sperrt=True))
    if any(r.sperrt for r in out):
        return out
    winkel = randwinkel(messung)
    zu_gross = [r for r in S.RAENDER if winkel[r] > S.WINKEL_MAX]
    if zu_gross:
        out.append(Rueckfrage(
            f"Mehr als {S.WINKEL_MAX:g}° bei " + ", ".join(zu_gross) + ". So "
            "weit reicht keine Feld-Angabe — Abstand und Wege prüfen (Meter und "
            "Zentimeter vertauscht?).", sperrt=True))
        return out
    gross = [r for r in S.RAENDER if winkel[r] > WINKEL_RUECKFRAGE_GRAD]
    if gross:
        out.append(Rueckfrage(
            f"Mehr als {WINKEL_RUECKFRAGE_GRAD:g}° bei " + ", ".join(gross)
            + " — das ist ungewöhnlich viel. Stimmen Abstand (in Metern) und "
            "Wege (in Zentimetern)?"))
    if all(messung.weg_cm(r) <= 0.0 for r in S.RAENDER):
        out.append(Rueckfrage(
            "Alle vier Wege sind 0 — das ergäbe ein Feld ohne Ausdehnung. "
            "Wirklich so übernehmen?"))
    else:
        for a, b in (("links", "rechts"), ("oben", "unten")):
            if messung.weg_cm(a) <= 0.0 and messung.weg_cm(b) <= 0.0:
                out.append(Rueckfrage(
                    f"{a.capitalize()} und {b} sind beide 0. Fehlt diese "
                    "Messung noch?"))
    if float(messung.abstand_m) < ABSTAND_KURZ_M:
        out.append(Rueckfrage(
            f"Abstand unter {de(ABSTAND_KURZ_M, 0)} m: kleine Ablesefehler "
            "machen dann viele Grad aus. Wenn möglich weiter weg messen."))
    return out


def feld_aus_messung(messung: Messung, zuschlag=S.ZUSCHLAG_STANDARD,
                     geraet: str = "", datum: datetime.date | None = None
                     ) -> S.LaserFeld:
    """Das eingemessene Feld, Herkunft „eingemessen am <Datum>". Wirft
    ``ValueError``, solange eine sperrende Rueckfrage offen ist."""
    gesperrt = [r.text for r in rueckfragen(messung) if r.sperrt]
    if gesperrt:
        raise ValueError(gesperrt[0])
    winkel = randwinkel(messung)
    tag = (datum or datetime.date.today()).isoformat()
    return S.LaserFeld(zuschlag=zuschlag, geraet=geraet,
                       quelle=S.QUELLE_EINGEMESSEN, quelle_datum=tag,
                       **{r: round(winkel[r], 1) for r in S.RAENDER})


# ── Schalten: nur nach Bestaetigung, nur ueber den Programmer ───────────────

#: Der Satz, den der Nutzer vor dem Einschalten ausdruecklich anhaken muss.
BESTAETIGUNG = ("Der Laser wird jetzt eingeschaltet. Ich habe den Bereich "
                "abgesichert.")
BETRIEBSART_ATTRIBUT = "shutter"


@dataclass
class Schreibschritt:
    attribut: str
    wert: int
    text: str


def _profilangaben_modul():
    """Die Profilangaben (LAS-33), FALLS dieser Programmstand sie hat. Kein
    harter Import: fehlt das Modul, gibt es nur den Weg „Ich stelle den Laser
    selbst ein"."""
    try:
        return importlib.import_module("src.core.laser.profilangaben")
    except Exception:                                    # noqa: BLE001
        return None


def _kanaele(fx) -> list:
    try:
        from src.core.app_state import get_channels_for_patched
        return list(get_channels_for_patched(fx) or ())
    except Exception:                                    # noqa: BLE001
        return []


def _aus_wert_kanal(ch) -> int:
    """Der „Aus"-Wert eines Betriebsart-Kanals: dieselbe Regel wie die
    Aus-Maske der Ausgabe (LAS-24); ohne sie die Laser-Konvention 0."""
    try:
        from src.core.app_state import AppState
        wert = AppState._laser_aus_wert(ch)
        if wert is not None:
            return int(wert)
    except Exception:                                    # noqa: BLE001
        pass
    for rg in getattr(ch, "ranges", None) or ():
        if (getattr(rg, "kind", "") or "").lower() == "closed":
            try:
                return max(0, min(255, int(rg.range_from)))
            except (TypeError, ValueError):
                continue
    return 0


class FeldSchalter:
    """Schaltet EINEN Laser fuer das Einmessen — und wieder aus.

    * :meth:`einschalten` schreibt nur mit ``bestaetigt=True`` (der Haken im
      Dialog), nur wenn ein Plan aus den Profilangaben vorliegt, nur wenn es
      einen Betriebsart-Kanal zum Wieder-Ausschalten gibt und nie bei
      gedruecktem LASER NOT-AUS (ein Schreibzugriff auf die Betriebsart wuerde
      ihn loesen — das tut dieser Assistent nicht).
    * :meth:`stopp` setzt die Betriebsart auf „Aus".
    * :meth:`beenden` schaltet aus, falls der Assistent eingeschaltet hat, und
      nimmt die uebrigen von ihm gesetzten Werte zurueck.
    """

    def __init__(self, state, fid: int, kanaele_holen=None):
        self._state = state
        self.fid = int(fid)
        self._kanaele_holen = kanaele_holen or _kanaele
        self.eingeschaltet = False
        self._vorher: dict = {}

    # -- was es zu wissen gibt ------------------------------------------------
    def _geraet(self):
        for fx in self._state.get_patched_fixtures():
            if int(getattr(fx, "fid", -1)) == self.fid:
                return fx
        return None

    def notaus_aktiv(self) -> bool:
        return bool(getattr(self._state, "laser_estop_active", False))

    def aus_schritt(self) -> Schreibschritt | None:
        """Betriebsart „Aus" — oder ``None``, wenn das Geraet keinen
        Betriebsart-Kanal hat."""
        fx = self._geraet()
        if fx is None:
            return None
        for ch in self._kanaele_holen(fx):
            if (getattr(ch, "attribute", "") or "") == BETRIEBSART_ATTRIBUT:
                return Schreibschritt(BETRIEBSART_ATTRIBUT, _aus_wert_kanal(ch),
                                      "Betriebsart → Aus")
        return None

    def plan(self) -> list | None:
        """Was „groesstes Feld zeigen" senden wuerde — aus den Profilangaben.
        ``None`` = dieser Programmstand/dieses Profil sagt es nicht; dann
        bleibt nur der Weg von Hand."""
        fx = self._geraet()
        modul = _profilangaben_modul()
        if fx is None or modul is None or self.aus_schritt() is None:
            return None
        try:
            angaben = modul.laser_profilangaben(self._kanaele_holen(fx))
            if angaben is None:
                return None
            art_kanal = angaben.betriebsart_kanal
            if art_kanal is None or art_kanal.attribut != BETRIEBSART_ATTRIBUT:
                return None
            arten = [b for b in art_kanal.betriebsart if b.steuert]
            art = next((b for b in arten if b.art == "statisch"),
                       arten[0] if arten else None)
            if art is None:
                return None
            schritte = []
            groesse = angaben.richtung("zoom")
            if groesse is not None and "gross" in (groesse.ende_niedrig,
                                                   groesse.ende_hoch):
                schritte.append(Schreibschritt(
                    "zoom", int(groesse.regler_zu_dmx(1.0)), "Größe → größte"))
            schritte.append(Schreibschritt(
                BETRIEBSART_ATTRIBUT, int(art.mitte),
                f"Betriebsart → {art.name or art.art}"))
            return schritte
        except Exception as e:                           # noqa: BLE001
            print(f"[feld_einmessen] Profilangaben nicht lesbar: {e}")
            return None

    def kann_einschalten(self) -> tuple[bool, str]:
        if self._geraet() is None:
            return False, "Das Gerät ist nicht mehr gepatcht."
        if self.aus_schritt() is None:
            return False, ("Dieses Gerät hat keinen Betriebsart-Kanal — LightOS "
                           "könnte es nicht wieder ausschalten.")
        if not self.plan():
            return False, ("Das Geräteprofil sagt nicht, welche Werte das "
                           "größte Feld ergeben.")
        if self.notaus_aktiv():
            return False, ("LASER NOT-AUS ist gedrückt. Der Assistent löst ihn "
                           "nicht — erst oben rechts selbst lösen.")
        return True, ""

    # -- schreiben ------------------------------------------------------------
    def einschalten(self, bestaetigt) -> bool:
        """Groesstes Feld zeigen. Ohne ``bestaetigt is True`` passiert nichts."""
        if bestaetigt is not True:
            return False
        ok, _grund = self.kann_einschalten()
        if not ok:
            return False
        plan = self.plan()
        st = self._state
        for schritt in plan:
            if schritt.attribut not in self._vorher:
                self._vorher[schritt.attribut] = st.get_programmer_value(
                    self.fid, schritt.attribut)
        self.eingeschaltet = True      # ab jetzt schaltet jedes Ende wieder aus
        for schritt in plan:           # Betriebsart steht im Plan zuletzt
            st.set_programmer_value(self.fid, schritt.attribut, int(schritt.wert))
        return True

    def stopp(self) -> bool:
        """Betriebsart auf „Aus". Bei gedruecktem LASER NOT-AUS ist der Laser
        schon dunkel; dann wird der Betriebsart-Wert nur aus dem Programmer
        genommen (ein Schreiben wuerde den NOT-AUS loesen)."""
        aus = self.aus_schritt()
        if aus is None:
            return False
        try:
            if self.notaus_aktiv():
                self._state.clear_programmer_value(self.fid, aus.attribut)
            else:
                self._state.set_programmer_value(self.fid, aus.attribut,
                                                 int(aus.wert))
        except Exception as e:                           # noqa: BLE001
            print(f"[feld_einmessen] ERROR: Ausschalten fehlgeschlagen: {e}")
            return False
        return True

    def beenden(self) -> bool:
        """Ende oder Abbruch: aus, falls der Assistent eingeschaltet hat.
        ``False`` = das Ausschalten ist fehlgeschlagen (der Aufrufer darf dann
        nicht „steht auf Aus" behaupten)."""
        if not self.eingeschaltet:
            return True
        ok = self.stopp()
        self.eingeschaltet = False
        for attribut, alt in self._vorher.items():
            if attribut == BETRIEBSART_ATTRIBUT:
                continue               # bleibt auf „Aus"
            try:
                if alt is None:
                    self._state.clear_programmer_value(self.fid, attribut)
                else:
                    self._state.set_programmer_value(self.fid, attribut, int(alt))
            except Exception as e:                       # noqa: BLE001
                print(f"[feld_einmessen] ERROR: Wert {attribut} nicht "
                      f"zurückgenommen: {e}")
        self._vorher = {}
        return ok
