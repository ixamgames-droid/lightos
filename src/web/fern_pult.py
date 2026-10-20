"""WEB-12: Blackout und Grand Master aus der Ferne — nur zuruecknehmen, was man
selbst gesetzt hat.

**Blackout (Befund QA96-19/20, „Fertig, wenn“ von WEB-12):** ein Blackout wird
nie von fern aufgehoben, den nicht DIESES Geraet gesetzt hat. Steht der
Blackout, weil jemand am Pult (Kopfzeile, Taste, MIDI, OSC, Kommandozeile)
oder ein anderes Handy ihn gesetzt hat, kann das Handy ihn nicht loesen — das
Licht geht nicht ueberraschend an, waehrend der Bediener am Pult glaubt, es sei
dunkel.

Gemerkt wird, wer den Schalter von AUS auf AN gelegt hat, zusammen mit der
``blackout_epoch`` des ``OutputManager`` (zaehlt jede echte Aenderung des
Schalters, OUT-57). Hat seitdem irgendwer den Schalter angefasst (die Epoche ist
weiter), gilt die Urheberschaft nicht mehr.

„Dieses Geraet“ ist die Kennung der Browser-Sitzung (``app.geraet()``), nicht
die Socket-Verbindung: ein Handy, das kurz das WLAN verliert und neu verbindet,
darf seinen Blackout weiterhin aufheben.

**Grand Master und Laser:** steht ein Laser im Patch, zieht der Sende-Pfad ihn
bei Grand Master ~0 auf seinen Aus-Wert (LAS-24). Den Grand Master vom Handy
aus dieser Zone wieder hochzuziehen, schaltet den Laser also wieder ein. Ohne
den Schalter „Laser vom Handy erlauben“ darf das Handy das nur, wenn es den
Grand Master selbst hineingezogen hat (gleiche Regel wie beim Blackout).

Reines Python, keine Qt-Klasse; laeuft im UI-Thread der Konsole (``pult``) bzw.
im Web-Thread (feste Fernbedienung). Ein Lock haelt Pruefung und Aenderung
zusammen.
"""
from __future__ import annotations

import threading

BLACKOUT_NICHT_VON_HIER = "blackout_nicht_von_hier"
LASER_GESPERRT = "laser_gesperrt"

_lock = threading.Lock()
_blackout_von: tuple | None = None     # (geraet, epoche nach dem Setzen)
_gm_von: tuple | None = None           # (geraet, gesetzter Wert 0..1)


def _nein(code: str) -> dict:
    return {"ok": False, "fehler": code}


def blackout_setzen(om, an: bool, geraet: str) -> dict:
    """Blackout-Schalter aus der Ferne. ``an`` muss schon ein ``bool`` sein."""
    global _blackout_von
    with _lock:
        if an:
            if not om.blackout_schalter:
                om.set_blackout(True)
                _blackout_von = (geraet, om.blackout_epoch) if geraet else None
            return {"ok": True}
        if not om.blackout_schalter:
            # Nichts zu loesen. (Haelt eine Taste den Blackout, bleibt es dunkel —
            # das loest nur, wer die Taste haelt.)
            return {"ok": True}
        von = _blackout_von
        if geraet and von == (geraet, om.blackout_epoch):
            om.set_blackout(False)
            _blackout_von = None
            return {"ok": True}
        return _nein(BLACKOUT_NICHT_VON_HIER)


def blackout_urheber() -> tuple | None:
    """Fuer Tests und Fehlersuche."""
    with _lock:
        return _blackout_von


def gm_setzen(state, wert: float, geraet: str, laser_erlaubt: bool) -> dict:
    """Grand Master (0..1) aus der Ferne setzen."""
    global _gm_von
    om = state.output_manager
    schwelle = float(getattr(type(om), "GM_LASER_AUS_SCHWELLE", 0.01))
    with _lock:
        jetzt = float(om.grand_master)
        heraus = jetzt <= schwelle < wert
        if heraus and not laser_erlaubt:
            from src.core.laser import fern_freigabe
            if fern_freigabe.gibt_laser(state):
                von = _gm_von
                selbst = (geraet and von is not None and von[0] == geraet
                          and abs(von[1] - jetzt) < 1e-6)
                if not selbst:
                    return _nein(LASER_GESPERRT)
        von = _gm_von
        eigen = bool(geraet and von is not None and von[0] == geraet
                     and abs(von[1] - jetzt) < 1e-6)
        om.set_grand_master(wert)
        neu = float(om.grand_master)
        if neu > schwelle:
            _gm_von = None
        elif jetzt > schwelle or eigen:
            # selbst hineingezogen (oder innerhalb der Zone weiterbewegt)
            _gm_von = (geraet, neu) if geraet else None
        return {"ok": True}


def vergessen() -> None:
    """Alle Urheberschaften verwerfen (Tests, Show-Wechsel)."""
    global _blackout_von, _gm_von
    with _lock:
        _blackout_von = None
        _gm_von = None
