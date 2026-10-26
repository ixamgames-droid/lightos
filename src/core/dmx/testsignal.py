"""OUT-70: Testsignal fuer einen eingerichteten Ausgang.

Kanal 1 faehrt :data:`DAUER_S` Sekunden langsam auf und ab, danach steht er
wieder auf dem Wert von vorher. Gedacht fuer die Frage „kommt an diesem
Ausgang ueberhaupt etwas an?“ — mit einem Dimmer oder Scheinwerfer auf
Adresse 1.

★ **Kein Sonderweg.** Das Signal wird als Tick-Callback des OutputManagers in
das Universum geschrieben, also VOR ``_send_all``. Blackout, Grand Master,
Aus-Masken und der Laser-NOT-AUS wirken darauf wie auf jedes andere Bild; der
Treiber bekommt nichts, was der Sicherheitsweg nicht gesehen hat.

★ **Sicherheitsregeln (QA-96, nicht verhandelbar):**

* nie bei ausgeloestem Laser-NOT-AUS;
* nie an einem AUSGANG, ueber den ein Laser erreichbar ist — gefragt wird nicht
  nur das eigene Universum, sondern jedes Universum, das ueber denselben
  Ausgabeweg sendet (S-07; dieselbe Wege-Rechnung wie der NOT-AUS, OUT-64);
* „ist das ein Laser?“ beantwortet dieselbe Regel wie NOT-AUS, Aus-Maske und
  Blackout (``laser.erkennung.ist_laser``, LAS-37) — S-03;
* nie, wenn auf Adresse 1 ein Geraet ohne Licht liegt, das ein Kanalwert
  ausloesen koennte (Nebel, Funken, CO2, Flammen, Konfetti …, V-03). Bewusst
  NUR Adresse 1: das Signal bewegt nur diesen Kanal; ein Nebelgeraet auf
  Adresse 40 sieht davon nichts;
* nur nach Rueckfrage (macht die Oberflaeche), jederzeit stoppbar; Stoppen
  stellt Kanal 1 auf den Wert von vorher.

Die Sperre wird nicht nur beim Start, sondern in jedem Takt geprueft — kommt
waehrend des Laufs ein Laser dazu oder wird der NOT-AUS ausgeloest, endet das
Signal sofort. Im Takt (Ausgabe-Thread) wird nur gelesen, was der
OutputManager schon weiss (Laser-Adressen aus dem Render-Plan, Latch, Wege);
die Geraeteliste mit Kanalabfrage gibt es nur beim Start im UI-Thread.

Kein Qt.
"""
from __future__ import annotations

import time

DAUER_S = 5.0
PERIODE_S = 2.5          # einmal 0 -> 255 -> 0
KANAL = 1

FRAGE = ("An diesem Ausgang hängen keine Laser, und mir ist klar, dass "
         "angeschlossene Geräte reagieren.")


# ── Wer liegt wo? ────────────────────────────────────────────────────────────

def _kanaele(fx, kanaele_von=None):
    if kanaele_von is not None:
        try:
            return list(kanaele_von(fx) or ())
        except Exception:                                # noqa: BLE001
            return []
    try:
        from src.core.app_state import get_channels_for_patched
        return list(get_channels_for_patched(fx) or ())
    except Exception:                                    # noqa: BLE001
        return []


def _universum_von(fx) -> int:
    try:
        return int(getattr(fx, "universe", 0))
    except Exception:                                    # noqa: BLE001
        return 0


def _name(fx) -> str:
    return (str(getattr(fx, "label", "") or "")
            or str(getattr(fx, "fixture_name", "") or "")
            or f"Gerät {getattr(fx, 'fid', '?')}")


def _deckt_adresse_1(fx, kanaele) -> bool:
    try:
        start = int(getattr(fx, "address", 0))
    except Exception:                                    # noqa: BLE001
        return False
    n = max(1, len(kanaele or ()))
    return start <= KANAL <= start + n - 1


def _om_laser_universen(om) -> set:
    """Universen mit Laser laut OutputManager — die Adressen stammen aus dem
    Render-Plan und damit aus ``laser.erkennung`` (LAS-37). Ohne Qt, ohne
    Geraeteliste: das darf der Ausgabe-Thread in jedem Takt fragen."""
    raus = set()
    quellen = [getattr(om, "_laser_adressen", None) or {},
               getattr(om, "_laser_estop_mask", None) or {}]
    try:
        quellen.append(om.lade_laser_adressen() or {})
    except Exception:                                    # noqa: BLE001
        pass
    for q in quellen:
        try:
            raus.update(int(u) for u, a in dict(q).items() if a)
        except Exception:                                # noqa: BLE001
            pass
    return raus


def laser_universen(om, fixtures=None, kanaele_von=None) -> set:
    """Alle internen Universen, in denen ein Laser steht — die Antwort des
    OutputManagers plus (beim Start) die eigene Pruefung jedes gepatchten
    Geraets mit der EINEN Regel ``laser.erkennung.ist_laser``."""
    raus = _om_laser_universen(om)
    if fixtures:
        try:
            from src.core.laser.erkennung import ist_laser
        except Exception:                                # noqa: BLE001
            ist_laser = None
        for fx in fixtures:
            u = _universum_von(fx)
            if ist_laser is None:
                raus.add(u)              # ohne Klassifikator lieber sperren
                continue
            try:
                if ist_laser(fx, _kanaele(fx, kanaele_von)):
                    raus.add(u)
            except Exception:                            # noqa: BLE001
                raus.add(u)
    return raus


def _wege(om, universum: int) -> set:
    f = getattr(om, "_wege_von", None)
    if f is None:
        return set()
    try:
        return set(f(int(universum)))
    except Exception:                                    # noqa: BLE001
        return set()


def gleicher_ausgang(om, universum: int, andere: int) -> bool:
    """Erreichen die beiden internen Universen denselben Ausgabeweg (Port,
    Art-Net-/sACN-Netzuniversum, uDMX)? Ein Universum erreicht sich selbst."""
    if int(universum) == int(andere):
        return True
    return bool(_wege(om, universum) & _wege(om, andere))


def geraete_auf_adresse_1(om, universum: int, fixtures, kanaele_von=None) -> list:
    """Gepatchte Geraete, die Kanal 1 des Ausgangs von ``universum`` belegen —
    auch die anderer Universen, die ueber denselben Ausgang senden."""
    raus = []
    for fx in fixtures or ():
        u = _universum_von(fx)
        if not gleicher_ausgang(om, universum, u):
            continue
        kanaele = _kanaele(fx, kanaele_von)
        if _deckt_adresse_1(fx, kanaele):
            raus.append((fx, kanaele))
    return raus


# ── Sperre ───────────────────────────────────────────────────────────────────

def _estop_aktiv(om) -> bool:
    return bool(getattr(om, "_laser_estop_aktiv", False)
                or getattr(om, "_laser_estop_wege", None))


def _laser_grund(om, universum: int, laser_us) -> str:
    for v in sorted(laser_us):
        if v == universum:
            return (f"Gesperrt: in Universum {universum} ist ein Laser "
                    f"gepatcht. Ein Testsignal könnte ihn einschalten — an "
                    f"diesem Ausgang gibt es deshalb kein Testsignal.")
    for v in sorted(laser_us):
        if gleicher_ausgang(om, universum, v):
            return (f"Gesperrt: Universum {v} mit Laser sendet über denselben "
                    f"Ausgang wie Universum {universum}. Ein Testsignal könnte "
                    f"den Laser einschalten — an diesem Ausgang gibt es "
                    f"deshalb kein Testsignal.")
    return ""


def sperre_grund(om, universum: int, fixtures=None, kanaele_von=None) -> str:
    """Leer = das Testsignal darf laufen. Sonst ein Satz, warum nicht.

    ``fixtures`` (UI-Thread, beim Start): die gepatchten Geraete. Ohne sie
    prueft die Funktion nur, was der OutputManager weiss (Takt-Pruefung)."""
    universum = int(universum)
    if _estop_aktiv(om):
        return ("Gesperrt: der Laser-NOT-AUS ist ausgelöst. Erst lösen, dann "
                "testen.")
    grund = _laser_grund(om, universum,
                         laser_universen(om, fixtures, kanaele_von))
    if grund:
        return grund
    if fixtures:
        try:
            from src.core.all_white import ist_geraet_ohne_licht
        except Exception:                                # noqa: BLE001
            ist_geraet_ohne_licht = None
        for fx, kanaele in geraete_auf_adresse_1(om, universum, fixtures,
                                                  kanaele_von):
            try:
                ohne_licht = (True if ist_geraet_ohne_licht is None
                              else ist_geraet_ohne_licht(fx, kanaele))
            except Exception:                            # noqa: BLE001
                ohne_licht = True
            if ohne_licht:
                return (f"Gesperrt: auf Adresse 1 liegt „{_name(fx)}“ — ein "
                        f"Gerät ohne Licht (Nebel, Funken, CO2, Flammen o. ä.). "
                        f"Ein Testsignal könnte es auslösen.")
    if universum not in (getattr(om, "universes", None) or {}):
        return f"Universum {universum} ist nicht angelegt."
    return ""


# ── Texte fuer die Rueckfrage ────────────────────────────────────────────────

def adresse_1_text(om, universum: int, fixtures, kanaele_von=None) -> str:
    """V-03: was laut Patch auf Adresse 1 liegt — fuer die Rueckfrage."""
    treffer = geraete_auf_adresse_1(om, universum, fixtures, kanaele_von)
    if not treffer:
        return ("Auf Adresse 1 liegt laut Patch kein Gerät. Reagieren kann "
                "trotzdem ein Gerät, das LightOS nicht kennt.")
    namen = ", ".join(f"„{_name(fx)}“" for fx, _ in treffer)
    return f"Auf Adresse 1 liegt laut Patch: {namen}."


def sichtbarkeit_text(om) -> str:
    """V-03: warum das Signal gerade nicht zu sehen waere — leer, wenn nichts
    dagegen spricht. Sperrt nicht: Blackout und Grand Master gelten weiter."""
    teile = []
    try:
        if om._blackout_wirksam():
            teile.append("BLACKOUT ist aktiv")
    except Exception:                                    # noqa: BLE001
        if getattr(om, "_blackout", False):
            teile.append("BLACKOUT ist aktiv")
    try:
        if float(getattr(om, "grand_master", 1.0)) <= 0.0:
            teile.append("der Grand Master steht auf 0 %")
    except Exception:                                    # noqa: BLE001
        pass
    if not teile:
        return ""
    satz = " und ".join(teile)
    return satz[:1].upper() + satz[1:] + " — das Signal wäre nicht zu sehen."


def frage_text(om, universum: int, fixtures, kanaele_von=None) -> str:
    """Die ganze Rueckfrage vor dem Start."""
    teile = [f"Testsignal auf Universum {int(universum)} senden?",
             adresse_1_text(om, universum, fixtures, kanaele_von)]
    sicht = sichtbarkeit_text(om)
    if sicht:
        teile.append(sicht)
    teile.append(FRAGE)
    return "\n\n".join(teile)


def wert(t: float) -> int:
    """Dreieck 0 -> 255 -> 0 je :data:`PERIODE_S`."""
    phase = (max(0.0, t) % PERIODE_S) / PERIODE_S
    return int(round(255 * (1.0 - abs(2.0 * phase - 1.0))))


class Testsignal:
    """Ein Lauf. ``start()`` liefert ``""`` oder den Sperrgrund."""

    def __init__(self, om, universum: int, fixtures=None, uhr=time.monotonic,
                 kanaele_von=None):
        self._om, self.universum = om, int(universum)
        self._fixtures = fixtures
        self._kanaele_von = kanaele_von
        self._uhr = uhr
        self._t0 = None
        self._vorher = None
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
        grund = sperre_grund(self._om, self.universum, self._fixture_liste(),
                             self._kanaele_von)
        if grund:
            return grund
        u = (getattr(self._om, "universes", None) or {}).get(self.universum)
        try:
            self._vorher = int(u.get_channel(KANAL)) if u is not None else 0
        except Exception:                                # noqa: BLE001
            self._vorher = 0
        self._t0 = self._uhr()
        self.laeuft = True
        self._om.add_tick_callback(self._cb)
        return ""

    def _tick(self, _dt=None):
        if not self.laeuft:
            return
        t = self._uhr() - self._t0
        # Im Takt nur, was der OutputManager weiss (kein Qt, keine Datenbank).
        grund = sperre_grund(self._om, self.universum)
        if grund or t >= DAUER_S:
            self.abbruch_grund = grund
            self.stopp()
            return
        self._om.universes[self.universum].set_channel(KANAL, wert(t))

    def stopp(self):
        """Signal beenden — Kanal 1 zurueck auf den Wert von vorher.
        Mehrfach aufrufbar."""
        war = self.laeuft
        self.laeuft = False
        try:
            self._om.remove_tick_callback(self._cb)
        except Exception:                                # noqa: BLE001
            pass
        if war:
            u = (getattr(self._om, "universes", None) or {}).get(self.universum)
            if u is not None:
                u.set_channel(KANAL, int(self._vorher or 0))
