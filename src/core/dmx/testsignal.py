"""OUT-70: Testsignal fuer einen eingerichteten Ausgang.

Kanal 1 faehrt :data:`DAUER_S` Sekunden langsam auf und ab, danach steht er
wieder auf 0. Gedacht fuer die Frage „kommt an diesem Ausgang ueberhaupt etwas
an?“ — mit einem Dimmer oder Scheinwerfer auf Adresse 1.

★ **Kein Sonderweg.** Das Signal wird als Tick-Callback des OutputManagers in
das Universum geschrieben, also VOR ``_send_all``. Blackout, Grand Master,
Aus-Masken und der Laser-NOT-AUS wirken darauf wie auf jedes andere Bild; der
Treiber bekommt nichts, was der Sicherheitsweg nicht gesehen hat.

★ **Nie in ein Universum mit Lasern.** :func:`sperre_grund` nennt den Grund;
die Sperre wird nicht nur beim Start, sondern in jedem Takt geprueft — kommt
waehrend des Laufs ein Laser dazu oder wird der NOT-AUS ausgeloest, endet das
Signal sofort mit 0.

Kein Qt.
"""
from __future__ import annotations

import time

DAUER_S = 5.0
PERIODE_S = 2.5          # einmal 0 -> 255 -> 0
KANAL = 1

FRAGE = ("An diesem Ausgang hängen keine Laser, und mir ist klar, dass "
         "angeschlossene Geräte reagieren.")


def _laser_im_universum(om, universum: int, fixtures) -> bool:
    for maske in (getattr(om, "_laser_adressen", None) or {},):
        if maske.get(universum):
            return True
    try:
        if (om.lade_laser_adressen() or {}).get(universum):
            return True
    except Exception:                                    # noqa: BLE001
        pass
    if fixtures:
        try:
            from src.core.laser.capability import is_laser_fixture
        except Exception:                                # noqa: BLE001
            return True              # ohne Klassifikator lieber sperren
        for fx in fixtures:
            try:
                if int(getattr(fx, "universe", 0)) == universum and is_laser_fixture(fx):
                    return True
            except Exception:                            # noqa: BLE001
                return True
    return False


def sperre_grund(om, universum: int, fixtures=None) -> str:
    """Leer = das Testsignal darf laufen. Sonst ein Satz, warum nicht."""
    if getattr(om, "_laser_estop_aktiv", False):
        return ("Gesperrt: der Laser-NOT-AUS ist ausgelöst. Erst lösen, dann "
                "testen.")
    if _laser_im_universum(om, universum, fixtures):
        return (f"Gesperrt: in Universe {universum} ist ein Laser gepatcht. "
                f"Ein Testsignal könnte ihn einschalten — an diesem Ausgang "
                f"gibt es deshalb kein Testsignal.")
    if universum not in (getattr(om, "universes", None) or {}):
        return f"Universe {universum} ist nicht angelegt."
    return ""


def wert(t: float) -> int:
    """Dreieck 0 -> 255 -> 0 je :data:`PERIODE_S`."""
    phase = (max(0.0, t) % PERIODE_S) / PERIODE_S
    return int(round(255 * (1.0 - abs(2.0 * phase - 1.0))))


class Testsignal:
    """Ein Lauf. ``start()`` liefert ``""`` oder den Sperrgrund."""

    def __init__(self, om, universum: int, fixtures=None, uhr=time.monotonic):
        self._om, self.universum = om, int(universum)
        self._fixtures = fixtures
        self._uhr = uhr
        self._t0 = None
        self.laeuft = False
        self.abbruch_grund = ""
        # EIN Objekt fuer An- und Abmelden: ``remove_tick_callback`` vergleicht
        # per Identitaet, und ``self._tick`` waere bei jedem Zugriff ein neues.
        self._cb = self._tick

    def _fixture_liste(self):
        f = self._fixtures
        return f() if callable(f) else f

    def start(self) -> str:
        if self.laeuft:
            return ""
        grund = sperre_grund(self._om, self.universum, self._fixture_liste())
        if grund:
            return grund
        self._t0 = self._uhr()
        self.laeuft = True
        self._om.add_tick_callback(self._cb)
        return ""

    def _tick(self, _dt=None):
        if not self.laeuft:
            return
        t = self._uhr() - self._t0
        grund = sperre_grund(self._om, self.universum, self._fixture_liste())
        if grund or t >= DAUER_S:
            self.abbruch_grund = grund
            self.stopp()
            return
        self._om.universes[self.universum].set_channel(KANAL, wert(t))

    def stopp(self):
        """Signal beenden — Kanal 1 auf 0. Mehrfach aufrufbar."""
        war = self.laeuft
        self.laeuft = False
        try:
            self._om.remove_tick_callback(self._cb)
        except Exception:                                # noqa: BLE001
            pass
        if war:
            u = (getattr(self._om, "universes", None) or {}).get(self.universum)
            if u is not None:
                u.set_channel(KANAL, 0)
