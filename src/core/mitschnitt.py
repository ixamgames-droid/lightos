"""IMP-2: DMX-Mitschnitt — aus dem empfangenen DMX eines anderen Lichtprogramms
Szenen machen (ohne Qt).

Wer umsteigt, laesst das alte Programm seine Szenen nacheinander ausgeben.
LightOS empfaengt das ueber den vorhandenen Art-Net-/sACN-Eingang; dieses
Modul haelt den Stand fest und baut daraus eine Szene, die an den gepatchten
Adressen exakt dieselben Bytes wieder ausgibt.

Drei Teile:

* :class:`Eingangspuffer` — merkt je Quelle (Protokoll, Universum) das letzte
  Bild und wann es sich zuletzt geaendert hat. Daraus: „Signal seit …“,
  „kein Signal“ und die Ruhe-Erkennung (keine Aenderung ueber eine
  einstellbare Zeit). Die Uhr wird hereingereicht, Tests spielen die Zeit vor.
* :func:`lies_abbild` — Bytes je Universum + Patch -> Werte je Geraet. Nur
  gepatchte Adressen; Laser werden ohne ausdrueckliche Freigabe ausgelassen.
* :func:`baue_szene` / :func:`baue_chaser` — legen die Funktionen an, je ein
  Rueckgaengig-Schritt.

★ Das Modul LIEST nur. Es schreibt in kein Universum, fasst weder Programmer
noch laufende Funktionen an und aendert am Eingang nichts (kein Start, kein
Stopp, keine Merge-Zuordnung). Master, Blackout und Laser-NOT-AUS liegen im
Ausgabepfad und bleiben davon unberuehrt.

★ Eine Szene speichert Kanalnummern je Geraet, keine Attribute
(``Scene.set_value(fid, kanal, wert)``). Deshalb ist der Rundlauf byte-gleich,
ganz gleich, wie das Profil die Kanaele nennt — die Attribut-Sicht
(:attr:`GeraeteBild.attribute`, :attr:`GeraeteBild.werte16`) dient nur der
Anzeige und der Auswahlregel fuer 16-Bit-Paare.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable

from src.core.dimmer_segmente import ist_dimmer

#: Vorgabe der Ruhe-Erkennung: so lange darf sich das Bild nicht geaendert haben.
RUHEZEIT_VORGABE = 0.5
#: Nach so vielen Sekunden ohne Paket gilt eine Quelle als „kein Signal“.
#: Art-Net wiederholt ein stehendes Bild spaetestens alle 4 s, sACN deutlich
#: oefter — 5 s lassen dem langsamsten Sender Luft.
SIGNAL_TIMEOUT = 5.0

ARTNET = "Art-Net"
SACN = "sACN"

# ── Auswahlregeln ────────────────────────────────────────────────────────────

#: Jeder Kanal jedes gepatchten Geraets, auch mit Wert 0. Vorgabe: die Szene
#: ist dann das ganze Bild — was im alten Programm dunkel war, ist es auch hier.
AUSWAHL_ALLE = "alle"
#: Nur Kanaele mit Wert ungleich 0.
AUSWAHL_UNGLEICH_NULL = "ungleich_null"
#: Nur Kanaele, deren Wert vom Bezugsbild abweicht (ohne Bezugsbild: ungleich 0).
AUSWAHL_GEAENDERT = "geaendert"

AUSWAHL_VORGABE = AUSWAHL_ALLE
AUSWAHLEN = (AUSWAHL_ALLE, AUSWAHL_UNGLEICH_NULL, AUSWAHL_GEAENDERT)


# ── Eingangspuffer ───────────────────────────────────────────────────────────

@dataclass
class _Quelle:
    daten: bytes
    signal_seit: float
    letztes_paket: float
    letzte_aenderung: float


@dataclass(frozen=True)
class QuellenStand:
    """Momentaufnahme einer Quelle fuer die Anzeige."""
    protokoll: str
    universum: int            # Nummer, wie sie der Sender nennt (1-basiert)
    hat_signal: bool
    signal_seit: float        # Sekunden, seit das Signal (wieder) da ist
    letztes_paket_vor: float  # Sekunden seit dem letzten Paket
    ruhig_seit: float         # Sekunden seit der letzten Aenderung
    kanaele: int              # Laenge des letzten Bildes


class Eingangspuffer:
    """Letztes Bild je Quelle, mit Zeitstempeln. Von den Empfangs-Threads
    beschrieben (:meth:`melde`), von der Oberflaeche gelesen."""

    def __init__(self, uhr: Callable[[], float] | None = None,
                 signal_timeout: float = SIGNAL_TIMEOUT):
        self._uhr = uhr or time.monotonic
        self._timeout = float(signal_timeout)
        self._lock = threading.Lock()
        self._quellen: dict[tuple[str, int], _Quelle] = {}

    def melde(self, protokoll: str, universum: int, daten) -> None:
        """Ein empfangenes Bild. ``universum`` 1-basiert, ``daten`` bis 512 Bytes."""
        bild = bytes(daten)[:512]
        jetzt = self._uhr()
        schluessel = (str(protokoll), int(universum))
        with self._lock:
            q = self._quellen.get(schluessel)
            if q is None or (jetzt - q.letztes_paket) > self._timeout:
                # Neu oder nach einer Pause zurueck: „Signal seit“ beginnt neu,
                # und das erste Bild zaehlt als Aenderung.
                self._quellen[schluessel] = _Quelle(bild, jetzt, jetzt, jetzt)
                return
            if bild != q.daten:
                q.daten = bild
                q.letzte_aenderung = jetzt
            q.letztes_paket = jetzt

    def leeren(self) -> None:
        with self._lock:
            self._quellen.clear()

    def vergiss(self, protokoll: str) -> None:
        """Alle Bilder eines Protokolls verwerfen (sein Eingang ist aus)."""
        with self._lock:
            for schluessel in [k for k in self._quellen if k[0] == str(protokoll)]:
                del self._quellen[schluessel]

    def stand(self) -> list[QuellenStand]:
        """Alle je gesehenen Quellen, sortiert nach Protokoll und Universum."""
        jetzt = self._uhr()
        with self._lock:
            eintraege = sorted(self._quellen.items())
            return [QuellenStand(
                protokoll=p, universum=u,
                hat_signal=(jetzt - q.letztes_paket) <= self._timeout,
                signal_seit=max(0.0, jetzt - q.signal_seit),
                letztes_paket_vor=max(0.0, jetzt - q.letztes_paket),
                ruhig_seit=max(0.0, jetzt - q.letzte_aenderung),
                kanaele=len(q.daten)) for (p, u), q in eintraege]

    def bild(self, protokoll: str, universum: int) -> bytes | None:
        """Das letzte Bild einer Quelle — ``None`` ohne (aktuelles) Signal."""
        jetzt = self._uhr()
        with self._lock:
            q = self._quellen.get((str(protokoll), int(universum)))
            if q is None or (jetzt - q.letztes_paket) > self._timeout:
                return None
            return q.daten


@dataclass
class Eingangsbild:
    """Was gerade mitgeschnitten werden kann: je LightOS-Universum ein Bild."""
    abbild: dict[int, bytes] = field(default_factory=dict)
    #: (Protokoll, Universum des Senders, LightOS-Universum) der benutzten Quellen
    quellen: list[tuple[str, int, int]] = field(default_factory=list)
    #: Sekunden seit der letzten Aenderung (kleinster Wert ueber alle Quellen)
    ruhig_seit: float = 0.0
    #: Sekunden, seit das Signal da ist (kleinster Wert ueber alle Quellen)
    signal_seit: float = 0.0
    #: Quellen mit Signal, die keinem LightOS-Universum zugeordnet sind
    nicht_zugeordnet: list[tuple[str, int]] = field(default_factory=list)
    #: LightOS-Universen, auf die mehr als eine Quelle zeigt (die juengste gilt)
    doppelt: list[int] = field(default_factory=list)

    @property
    def hat_signal(self) -> bool:
        return bool(self.abbild)

    def ist_ruhig(self, ruhezeit: float = RUHEZEIT_VORGABE) -> bool:
        return self.hat_signal and self.ruhig_seit >= float(ruhezeit)


def eingangsbild(puffer: Eingangspuffer,
                 ziel: Callable[[str, int], int | None]) -> Eingangsbild:
    """Fasst den Puffer zu einem Bild je LightOS-Universum zusammen.

    ``ziel(protokoll, universum)`` nennt das LightOS-Universum einer Quelle
    oder ``None``, wenn sie nicht zugeordnet ist — solche Quellen werden
    genannt, aber NICHT mitgeschnitten (es wird keine Zuordnung geraten)."""
    ergebnis = Eingangsbild()
    juengstes: dict[int, float] = {}
    ruhig: list[float] = []
    seit: list[float] = []
    for st in puffer.stand():
        if not st.hat_signal:
            continue
        nach = ziel(st.protokoll, st.universum)
        if nach is None:
            ergebnis.nicht_zugeordnet.append((st.protokoll, st.universum))
            continue
        nach = int(nach)
        daten = puffer.bild(st.protokoll, st.universum)
        if daten is None:
            continue
        ergebnis.quellen.append((st.protokoll, st.universum, nach))
        ruhig.append(st.ruhig_seit)
        seit.append(st.signal_seit)
        if nach in juengstes:
            if nach not in ergebnis.doppelt:
                ergebnis.doppelt.append(nach)
            if st.letztes_paket_vor >= juengstes[nach]:
                continue
        juengstes[nach] = st.letztes_paket_vor
        ergebnis.abbild[nach] = daten
    ergebnis.ruhig_seit = min(ruhig) if ruhig else 0.0
    ergebnis.signal_seit = min(seit) if seit else 0.0
    return ergebnis


# ── Abbild -> Werte je Geraet ────────────────────────────────────────────────

@dataclass(frozen=True)
class KanalWert:
    kanal: int          # 1-basiert innerhalb des Geraets
    schluessel: str     # Attribut wie im Programmer, Mehrkopf als ``attr#N``
    wert: int           # 0..255
    adresse: int        # DMX-Adresse 1..512


@dataclass
class GeraeteBild:
    fid: int
    name: str
    universum: int
    kanaele: list[KanalWert] = field(default_factory=list)
    #: 16-Bit-Paare als (Schluessel grob, Schluessel fein)
    paare: list[tuple[str, str]] = field(default_factory=list)

    @property
    def attribute(self) -> dict[str, int]:
        """Wert je Attribut-Schluessel (8 Bit, Fein-Kanaele eigener Schluessel)."""
        return {k.schluessel: k.wert for k in self.kanaele}

    @property
    def werte16(self) -> dict[str, int]:
        """16-Bit-Wert (grob * 256 + fein) je Grob-Schluessel mit Fein-Kanal."""
        a = self.attribute
        return {grob: a[grob] * 256 + a[fein] for grob, fein in self.paare
                if grob in a and fein in a}


@dataclass
class Mitschnitt:
    """Ergebnis von :func:`lies_abbild`."""
    geraete: list[GeraeteBild] = field(default_factory=list)
    #: Namen der ausgelassenen Laser (Sicherheitsvorgabe)
    laser_ausgelassen: list[str] = field(default_factory=list)
    #: Namen gepatchter Geraete, fuer deren Universum kein Bild vorliegt
    ohne_bild: list[str] = field(default_factory=list)
    #: Geraete, die im Bild gerade irgendeinen Wert ungleich 0 bekommen
    #: (Laser zaehlen nur mit, wenn sie mitgenommen werden)
    geraete_mit_wert: int = 0
    #: Gepatchte Geraete, die ueberhaupt in Frage kamen (mit Bild, ohne Laser)
    geraete_gesehen: int = 0

    @property
    def kanalzahl(self) -> int:
        return sum(len(g.kanaele) for g in self.geraete)

    def szenenwerte(self) -> list[tuple[int, int, int]]:
        """``(fid, kanal, wert)`` — genau das, was ``Scene.set_value`` nimmt."""
        return [(g.fid, k.kanal, k.wert) for g in self.geraete for k in g.kanaele]


def _kanaele_aus_profil(fixture):
    from src.core.app_state import get_channels_for_patched
    return get_channels_for_patched(fixture)


def _ist_laser(fixture, kanaele) -> bool:
    from src.core.laser.erkennung import ist_laser
    return ist_laser(fixture, kanaele)


def _nutzt_dmx(fixture) -> bool:
    from src.core.app_state import fixture_uses_dmx
    return fixture_uses_dmx(fixture)


def _schluessel_je_kanal(fixture, kanaele) -> dict[int, str]:
    """Kanalnummer -> Programmer-Schluessel. Kennt das Profil einen Kanal
    nicht (oder gibt es gar kein Profil), heisst er ``kanal_N`` — die Szene
    haelt ihn trotzdem, sie braucht nur die Nummer."""
    from src.core.app_state import channel_occurrence_keys
    anzahl = int(getattr(fixture, "channel_count", 0) or 0)
    bekannt: dict[int, str] = {}
    for ch, schluessel in channel_occurrence_keys(list(kanaele or ())):
        nr = int(getattr(ch, "channel_number", 0) or 0)
        if nr >= 1:
            bekannt[nr] = str(schluessel)
    if anzahl <= 0:
        anzahl = max(bekannt, default=0)
    return {nr: bekannt.get(nr, f"kanal_{nr}") for nr in range(1, anzahl + 1)}


def _paare_16bit(schluessel: dict[int, str]) -> list[tuple[int, int]]:
    """16-Bit-Paare als (Kanal grob, Kanal fein): ein ``x_fine`` gehoert zum
    ``x`` desselben Kopfes (``x#N`` / ``x_fine#N``)."""
    nach_name = {name: nr for nr, name in schluessel.items()}
    paare = []
    for nr, name in sorted(schluessel.items()):
        basis, _, kopf = name.partition("#")
        if not basis.endswith("_fine"):
            continue
        grob = basis[:-len("_fine")] + (f"#{kopf}" if kopf else "")
        if grob in nach_name:
            paare.append((nach_name[grob], nr))
    return paare


def lies_abbild(abbild: dict[int, bytes], patch: Iterable, *,
                auswahl: str = AUSWAHL_VORGABE,
                bezug: dict[int, bytes] | None = None,
                laser_mitnehmen: bool = False,
                kanaele_fuer: Callable | None = None,
                ist_laser: Callable | None = None) -> Mitschnitt:
    """Leitet aus einem DMX-Abbild die Werte je gepatchtem Geraet ab.

    ``abbild``: Bytes je LightOS-Universum (kuerzer als 512 = der Rest ist 0).
    ``patch``: die gepatchten Geraete. Gelesen werden NUR deren Adressen; was
    auf unbelegten Adressen ankommt, faellt weg.

    ``auswahl``: :data:`AUSWAHL_ALLE` (Vorgabe), :data:`AUSWAHL_UNGLEICH_NULL`
    oder :data:`AUSWAHL_GEAENDERT` (gegen ``bezug``; ohne Bezugsbild wie
    „ungleich 0“). Ein 16-Bit-Paar bleibt zusammen: zaehlt einer der beiden
    Kanaele, kommen beide mit — sonst spraenge der Wert beim Abspielen.

    Laser bleiben ohne ``laser_mitnehmen=True`` draussen und werden in
    ``laser_ausgelassen`` genannt. Netzwerk-Laser haben gar keine DMX-Adresse
    und werden nie gelesen. Ein Geraet, fuer dessen Universum kein Bild
    vorliegt, bekommt keine Werte (es werden keine Nullen erfunden)."""
    if auswahl not in AUSWAHLEN:
        raise ValueError(f"Unbekannte Auswahl: {auswahl!r}")
    kanaele_fuer = kanaele_fuer or _kanaele_aus_profil
    ist_laser = ist_laser or _ist_laser
    ergebnis = Mitschnitt()

    for fx in sorted(patch, key=lambda f: int(getattr(f, "fid", 0) or 0)):
        name = str(getattr(fx, "label", "") or "") or f"Gerät {getattr(fx, 'fid', '?')}"
        try:
            profil_kanaele = list(kanaele_fuer(fx) or ())
        except Exception:
            profil_kanaele = []
        laser = bool(ist_laser(fx, profil_kanaele))
        if not _nutzt_dmx(fx):
            if laser:
                ergebnis.laser_ausgelassen.append(name)
            continue
        if laser and not laser_mitnehmen:
            ergebnis.laser_ausgelassen.append(name)
            continue
        uni = int(getattr(fx, "universe", 0) or 0)
        daten = abbild.get(uni)
        if daten is None:
            ergebnis.ohne_bild.append(name)
            continue
        alt = (bezug or {}).get(uni)
        start = int(getattr(fx, "address", 0) or 0)
        schluessel = _schluessel_je_kanal(fx, profil_kanaele)

        def _wert(bild, adresse):
            return bild[adresse - 1] if 1 <= adresse <= len(bild) else 0

        werte: dict[int, int] = {}
        for nr in schluessel:
            adresse = start + nr - 1
            if 1 <= adresse <= 512:
                werte[nr] = _wert(daten, adresse)
        ergebnis.geraete_gesehen += 1
        if any(werte.values()):
            ergebnis.geraete_mit_wert += 1

        if auswahl == AUSWAHL_ALLE:
            gewaehlt = set(werte)
        elif auswahl == AUSWAHL_GEAENDERT and alt is not None:
            gewaehlt = {nr for nr, w in werte.items()
                        if w != _wert(alt, start + nr - 1)}
        else:
            gewaehlt = {nr for nr, w in werte.items() if w != 0}
        paare = [(g, f) for g, f in _paare_16bit(schluessel)
                 if g in werte and f in werte]
        for grob, fein in paare:
            if grob in gewaehlt or fein in gewaehlt:
                gewaehlt.update((grob, fein))
        if not gewaehlt:
            continue
        # Farbe und Dimmer bleiben getrennt: Wird ein Geraet aufgenommen, gehen
        # seine Dimmer-Kanaele immer mit — auch mit Wert 0. Sonst zoege die
        # Grundhelligkeit aelterer Shows eine Farbe ohne Dimmer auf Voll.
        gewaehlt.update(nr for nr in werte
                        if ist_dimmer(str(schluessel[nr]).split("#", 1)[0]))
        bild = GeraeteBild(fid=int(fx.fid), name=name, universum=uni)
        for nr in sorted(gewaehlt):
            bild.kanaele.append(KanalWert(kanal=nr, schluessel=schluessel[nr],
                                          wert=int(werte[nr]),
                                          adresse=start + nr - 1))
        bild.paare = [(schluessel[g], schluessel[f]) for g, f in paare
                      if g in gewaehlt]
        ergebnis.geraete.append(bild)
    return ergebnis


# ── Szene / Chaser anlegen ───────────────────────────────────────────────────

def _undo_anlegen(fm, funktion, label: str) -> None:
    """Die Funktion ist schon angelegt; der Schritt nimmt sie zurueck bzw.
    stellt dasselbe Objekt (gleiche ID) wieder her."""
    from src.core.undo import Command, get_undo_stack
    get_undo_stack().push(Command(
        label=label,
        do=lambda: None,
        undo=lambda: fm.remove(funktion.id),
        redo=lambda: fm.add(funktion),
    ), execute=False)


def baue_szene(fm, name: str, mitschnitt: Mitschnitt, *, undo: bool = True):
    """Legt eine Szene mit den mitgeschnittenen Kanalwerten an — derselbe Weg
    wie „Programmer → Szene“ (``new_scene`` + ``set_value``), dazu EIN
    Rueckgaengig-Schritt. Einblendzeit 0: Zeiten setzt man von Hand."""
    werte = mitschnitt.szenenwerte()
    if not werte:
        raise ValueError("Der Mitschnitt enthält keine Kanalwerte.")
    szene = fm.new_scene(str(name).strip() or "Mitschnitt")
    for fid, kanal, wert in werte:
        szene.set_value(fid, kanal, wert)
    if undo:
        _undo_anlegen(fm, szene, f"Mitschnitt „{szene.name}“ festhalten")
    return szene


def baue_chaser(fm, name: str, szenen_ids: Iterable[int], schrittzeit: float = 1.0,
                *, undo: bool = True):
    """Fasst Szenen in der gegebenen Reihenfolge zu einem Chaser zusammen —
    EIN Rueckgaengig-Schritt (die Szenen selbst bleiben).

    Jeder Schritt haelt ``schrittzeit`` Sekunden, ohne Ueberblendung. Der
    Chaser laeuft nach diesen Zeiten und nicht im Takt der Haupt-BPM — die
    Zeiten des alten Programms kommen ueber DMX nicht mit."""
    ids = [int(i) for i in szenen_ids]
    if not ids:
        raise ValueError("Ohne Szenen kein Chaser.")
    chaser = fm.new_chaser(str(name).strip() or "Mitschnitt")
    chaser.tempo_bus_id = ""
    halt = max(0.05, float(schrittzeit))
    for sid in ids:
        chaser.add_step(sid, fade_in=0.0, hold=halt, fade_out=0.0)
    if undo:
        _undo_anlegen(fm, chaser, f"Chaser „{chaser.name}“ aus Mitschnitt")
    return chaser


def freier_name(fm, stamm: str = "Mitschnitt", ab: int = 1) -> tuple[str, int]:
    """Naechster freier Name ``<stamm> <n>`` und sein Zaehler."""
    vergeben = {str(getattr(f, "name", "")) for f in fm.all()}
    n = max(1, int(ab))
    while f"{stamm} {n}" in vergeben:
        n += 1
    return f"{stamm} {n}", n


# ── Anbindung an die Empfaenger ──────────────────────────────────────────────

class EingangsLeser:
    """Haengt einen :class:`Eingangspuffer` an die vorhandenen Empfaenger.

    Meldet sich dort nur als Zuhoerer an (``subscribe``) — startet und stoppt
    nichts und aendert keine Merge-Zuordnung. Die Zuordnung „Universum des
    Senders -> LightOS-Universum“ wird aus der Eingangs-Einstellung gelesen
    (Ausgabe → Konfigurieren); derzeit ist das EIN Universum je Protokoll."""

    def __init__(self, puffer: Eingangspuffer | None = None,
                 empfaenger: dict | None = None):
        self.puffer = puffer or Eingangspuffer()
        self._empfaenger = empfaenger
        self._angemeldet: list[tuple[object, Callable]] = []

    def empfaenger(self) -> dict:
        if self._empfaenger is None:
            from src.core.dmx.artnet_input import get_artnet_receiver
            from src.core.dmx.sacn_input import get_sacn_receiver
            self._empfaenger = {ARTNET: get_artnet_receiver(),
                                SACN: get_sacn_receiver()}
        return self._empfaenger

    def verbinden(self) -> None:
        if self._angemeldet:
            return
        for protokoll, rx in self.empfaenger().items():
            def _cb(universum, daten, _p=protokoll):
                self.puffer.melde(_p, universum, daten)
            rx.subscribe(_cb)
            self._angemeldet.append((rx, _cb))

    def trennen(self) -> None:
        for rx, cb in self._angemeldet:
            try:
                rx.unsubscribe(cb)
            except Exception:
                pass
        self._angemeldet.clear()

    def laeuft(self, protokoll: str) -> bool:
        rx = self.empfaenger().get(protokoll)
        try:
            return bool(rx is not None and rx.is_running())
        except Exception:
            return False

    def zuordnungen(self, protokoll: str) -> dict[int, int]:
        """Universum des Senders -> LightOS-Universum, wie eingestellt."""
        rx = self.empfaenger().get(protokoll)
        try:
            return {int(k): int(v[0]) for k, v in dict(rx.merges()).items()}
        except Exception:
            return {}

    def ziel(self, protokoll: str, universum: int) -> int | None:
        return self.zuordnungen(protokoll).get(int(universum))

    def bild(self) -> Eingangsbild:
        # Ein abgeschalteter Eingang liefert kein Bild. Der Puffer haelt das
        # letzte sonst noch `SIGNAL_TIMEOUT` Sekunden — der Assistent ist nicht
        # modal, der Eingang kann also abgeschaltet werden, waehrend er offen
        # ist, und aus dem Bild von vorhin darf dann keine Szene mehr werden.
        # Nach dem Wiedereinschalten zaehlt erst ein neues Paket.
        for protokoll in self.empfaenger():
            if not self.laeuft(protokoll):
                self.puffer.vergiss(protokoll)
        return eingangsbild(self.puffer, self.ziel)
