"""ENG-36: Klonen — die Programmierung eines Geräts auf andere übertragen.

Klonen ist ein **Plan**. :func:`plane` rechnet aus dem Show-Zustand, den
Quellen, den Zielen und den Optionen eine Liste von :class:`Eintrag` aus und
schreibt dabei NICHTS. Derselbe Plan ist

* die **Vorschau** (``plan.eintraege`` mit Kennzeichen, ``plan.zaehler()``),
* die **Ausführung** (``plan.anwenden(state)``) und
* der **Rückweg** (``plan.zuruecknehmen(state)`` — nimmt nur die Einträge des
  Ziels wieder heraus).

Zwei Arten von Stellen:

* **Mitgliedschaften** (Fixture-Gruppen, Matrix-Raster, Bewegungs-Effekte,
  Gerätelisten von Effekten, Blackout-Ziele und XY-Pads der Konsole) brauchen
  keine Wert-Übersetzung — die Effekte rechnen je Gerät passend aus.
* **Gespeicherte Werte** (Snaps, Snapshots, Szenen, Cues, Sequenzen, Paletten,
  Grundwerte): bei gleichem Typ und Modus 1:1, bei verschiedenem Typ werden
  **Dimmer → Dimmer** und **Farbe → Farbe** übersetzt. Alles andere fällt bei
  verschiedenem Typ in diesem Schritt weg und steht so in der Vorschau.

★ **Farbe und Dimmer bleiben getrennt.** Die Farb-Übersetzung schreibt nie
einen Dimmerwert und die Dimmer-Übernahme nie eine Farbe. Hat die Quelle
keinen Dimmer, bekommt das Ziel keinen — das steht nur als Hinweis im Plan.

★ **„Ersetzen" löscht nichts.** Es überschreibt am Ziel genau die Werte, die
die Quelle an dieser Stelle hat. Was das Ziel dort sonst noch tut und wo die
Quelle gar nicht vorkommt, bleibt unberührt.

Der Rückweg je Stelle (:class:`Schritt`): steht die Stelle noch genau so da,
wie das Klonen sie hinterlassen hat, kommt der Stand von davor zurück —
zeichengleich. Wurde seither von Hand daran gearbeitet, werden nur die vom
Klonen geschriebenen Einträge des Ziels herausgenommen; fremde Handarbeit
bleibt stehen.

Ohne Qt. Die Geräte-Kanäle kommen über ``app_state.get_channels_for_patched``
(zur Laufzeit nachgeschlagen, in Tests ersetzbar).
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Callable

from ..attr_groups import attr_label, classify_attr
from ..group_cells import ACHSE_FARBE, parse_zelle, zelle_fuer

# ── Begriffe ────────────────────────────────────────────────────────────────

UNVERAENDERT = "unveraendert"
UEBERSETZT = "uebersetzt"
FAELLT_WEG = "faellt_weg"
#: Kein viertes Ergebnis des Klonens, sondern „hier passiert nichts": das Ziel
#: steht an der Stelle schon (Mitgliedschaft) bzw. hat dort schon einen Wert
#: und es wurde „Hinzufügen" gewählt.
BLEIBT = "bleibt"

KENNZEICHEN_TEXT = {
    UNVERAENDERT: "unverändert übernommen",
    UEBERSETZT: "übersetzt",
    FAELLT_WEG: "fällt weg",
    BLEIBT: "bleibt, wie es ist",
}

BEREICH_GRUPPEN = "gruppen"
BEREICH_EFFEKTE = "effekte"
BEREICH_SNAPS = "snaps"
BEREICH_CUES = "cues"
BEREICH_PALETTEN = "paletten"
BEREICH_KONSOLE = "konsole"
BEREICH_GRUNDWERTE = "grundwerte"

#: Reihenfolge = Reihenfolge der Häkchen im Dialog und der Vorschau.
BEREICHE = (BEREICH_GRUPPEN, BEREICH_EFFEKTE, BEREICH_SNAPS, BEREICH_CUES,
            BEREICH_PALETTEN, BEREICH_KONSOLE, BEREICH_GRUNDWERTE)

BEREICH_TEXT = {
    BEREICH_GRUPPEN: "Gruppen",
    BEREICH_EFFEKTE: "Matrix & Bewegungs-Effekte",
    BEREICH_SNAPS: "Snaps & Szenen",
    BEREICH_CUES: "Cues",
    BEREICH_PALETTEN: "Paletten",
    BEREICH_KONSOLE: "Tasten der Konsole",
    BEREICH_GRUNDWERTE: "Grundwerte",
}

HINZUFUEGEN = "hinzufuegen"
ERSETZEN = "ersetzen"

POS_ENDE = "ende"
POS_NEBEN = "neben"

GRUND_SPAETER = "kommt in einem späteren Schritt"
GRUND_KOPF = ("Wert eines einzelnen Kopfes — zwischen verschiedenen "
              "Gerätetypen kommt das in einem späteren Schritt")

_DIMMER = ("intensity", "dimmer", "master")
_MISCH = ("color_r", "color_g", "color_b", "color_w")
_EXTRA = ("color_a", "color_uv")
_CMY = (("cmy_c", "cmy_m", "cmy_y"), ("cyan", "magenta", "yellow"))
_RAD = ("color_wheel", "colour_wheel", "color")


class KlonFehler(ValueError):
    """Der Vorgang ist so nicht möglich — der Text geht an den Nutzer."""


@dataclass(frozen=True)
class Optionen:
    #: ``HINZUFUEGEN`` oder ``ERSETZEN`` — bewusst ohne Vorgabe.
    wie: str
    bereiche: frozenset = frozenset(BEREICHE)
    position: str = POS_ENDE


# ── Der eine Baustein für Ausführung und Rückweg ────────────────────────────

class Schritt:
    """Eine Stelle der Show, an der das Ziel eingetragen wird.

    ``lesen()`` liefert den jetzigen Stand als schlichte, vergleichbare Daten,
    ``schreiben(stand)`` setzt ihn, ``einfuegen(stand)`` rechnet den Stand mit
    dem Ziel aus (rein), ``entfernen(jetzt, vor, nach)`` nimmt die Einträge
    des Ziels aus einem inzwischen von Hand veränderten Stand heraus (rein).
    """

    def __init__(self, lesen: Callable, schreiben: Callable,
                 einfuegen: Callable, entfernen: Callable):
        self._lesen = lesen
        self._schreiben = schreiben
        self._einfuegen = einfuegen
        self._entfernen = entfernen
        self._vor = None
        self._nach = None
        self._angewendet = False

    def vorschau(self):
        """``(vor, nach)`` — ohne zu schreiben."""
        vor = self._lesen()
        return vor, self._einfuegen(copy.deepcopy(vor))

    def anwenden(self) -> bool:
        vor, nach = self.vorschau()
        self._vor, self._nach, self._angewendet = vor, nach, True
        if nach == vor:
            return False
        self._schreiben(copy.deepcopy(nach))
        return True

    def zuruecknehmen(self) -> None:
        if not self._angewendet:
            return
        self._angewendet = False
        if self._nach == self._vor:
            return
        jetzt = self._lesen()
        if jetzt == self._nach:
            self._schreiben(copy.deepcopy(self._vor))
        else:
            self._schreiben(self._entfernen(
                copy.deepcopy(jetzt), self._vor, self._nach))


@dataclass
class Eintrag:
    """Eine Zeile der Vorschau."""
    bereich: str
    objekt: str                 # „Snap „Rot““, „Matrix „Lauflicht““ …
    quelle: int
    ziel: int
    kennzeichen: str
    text: str
    #: ``"ergaenzt"`` / ``"ersetzt"`` — leer bei „fällt weg" und „bleibt".
    art: str = ""
    schritte: list = field(default_factory=list)

    @property
    def zeile(self) -> str:
        return f"{self.objekt} · {self.quelle} → {self.ziel}: {self.text}"


@dataclass
class Plan:
    paare: list
    optionen: Optionen
    eintraege: list = field(default_factory=list)
    hinweise: list = field(default_factory=list)
    _melder: Callable | None = None
    _angewendet: bool = False

    def zaehler(self) -> dict:
        out = {UNVERAENDERT: 0, UEBERSETZT: 0, FAELLT_WEG: 0, BLEIBT: 0}
        for e in self.eintraege:
            out[e.kennzeichen] = out.get(e.kennzeichen, 0) + 1
        return out

    @property
    def aenderungen(self) -> int:
        """Zahl der Stellen, an denen wirklich etwas geschrieben wird."""
        return sum(1 for e in self.eintraege
                   if e.kennzeichen in (UNVERAENDERT, UEBERSETZT))

    @property
    def beruehrte_bereiche(self) -> set:
        return {e.bereich for e in self.eintraege if e.schritte}

    @property
    def label(self) -> str:
        quellen = _nummern_text(_ohne_doppelte(q for q, _ in self.paare))
        ziele = _nummern_text(_ohne_doppelte(z for _, z in self.paare))
        return f"Klonen {quellen} → {ziele}"

    def _alle_schritte(self) -> list:
        out, gesehen = [], set()
        for e in self.eintraege:
            for s in e.schritte:
                if id(s) not in gesehen:
                    gesehen.add(id(s))
                    out.append(s)
        return out

    def anwenden(self, state) -> int:
        """Schreibt den Plan. Liefert die Zahl der geänderten Stellen."""
        with _plan_sperre(state):
            for s in self._alle_schritte():
                s.anwenden()
        self._angewendet = True
        self._melden(state)
        return self.aenderungen

    def zuruecknehmen(self, state) -> None:
        if not self._angewendet:
            return
        with _plan_sperre(state):
            for s in reversed(self._alle_schritte()):
                s.zuruecknehmen()
        self._angewendet = False
        self._melden(state)

    def _melden(self, state) -> None:
        if self._melder is not None:
            self._melder(state, self.beruehrte_bereiche)


class _KeineSperre:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _plan_sperre(state):
    holen = getattr(state, "_get_plan_lock", None)
    try:
        return holen() if callable(holen) else _KeineSperre()
    except Exception:
        return _KeineSperre()


def _ohne_doppelte(werte) -> list:
    out: list = []
    for w in werte:
        if w not in out:
            out.append(w)
    return out


def _nummern_text(nummern: list) -> str:
    """``[5, 6, 7, 8, 11]`` → ``"5–8, 11"``."""
    teile: list[str] = []
    geordnet = sorted(set(int(n) for n in nummern))
    i = 0
    while i < len(geordnet):
        j = i
        while j + 1 < len(geordnet) and geordnet[j + 1] == geordnet[j] + 1:
            j += 1
        teile.append(str(geordnet[i]) if j == i
                     else f"{geordnet[i]}–{geordnet[j]}" if j > i + 1
                     else f"{geordnet[i]}, {geordnet[j]}")
        i = j + 1
    return ", ".join(teile)


# ── Geräte ──────────────────────────────────────────────────────────────────

class _Geraet:
    def __init__(self, fx, kanaele):
        self.fx = fx
        self.fid = int(fx.fid)
        self.name = (getattr(fx, "label", "") or "").strip() or f"Gerät {self.fid}"
        self.kanaele = list(kanaele or ())
        self.attrs = {(getattr(c, "attribute", "") or "").lower()
                      for c in self.kanaele}
        self.attrs.discard("")

    @property
    def typ(self) -> tuple:
        return (getattr(self.fx, "fixture_profile_id", None),
                getattr(self.fx, "mode_name", None),
                getattr(self.fx, "channel_count", None))

    @property
    def hat_dimmer(self) -> bool:
        return any(a in self.attrs for a in _DIMMER)

    @property
    def hat_farbe(self) -> bool:
        return any(classify_attr(a) == "Color" for a in self.attrs)

    def schluessel(self) -> list:
        """``(kanalnummer, schlüssel)`` — Mehrkopf-Vorkommen als ``attr#N``."""
        from .. import app_state as A
        return [(int(ch.channel_number), key)
                for ch, key in A.channel_occurrence_keys(self.kanaele)]


def _gleicher_typ(q: _Geraet, z: _Geraet) -> bool:
    return q.typ[0] is not None and q.typ == z.typ


def _geraete(state) -> dict:
    from .. import app_state as A
    out: dict[int, _Geraet] = {}
    for fx in state.get_patched_fixtures():
        try:
            kanaele = A.get_channels_for_patched(fx)
        except Exception:
            kanaele = []
        out[int(fx.fid)] = _Geraet(fx, kanaele)
    return out


def paare_bilden(quellen, ziele) -> list:
    """Eine Quelle auf beliebig viele Ziele oder gleich viele paarweise."""
    q = _ohne_doppelte(int(x) for x in (quellen or ()))
    z = _ohne_doppelte(int(x) for x in (ziele or ()))
    if not q:
        raise KlonFehler("Keine Quelle gewählt.")
    if not z:
        raise KlonFehler("Kein Ziel gewählt.")
    doppelt = sorted(set(q) & set(z))
    if doppelt:
        raise KlonFehler(
            f"Gerät {_nummern_text(doppelt)} ist zugleich Quelle und Ziel.")
    if len(q) == 1:
        return [(q[0], ziel) for ziel in z]
    if len(q) == len(z):
        return list(zip(q, z))
    raise KlonFehler(
        f"{len(q)} Quellen und {len(z)} Ziele passen nicht zusammen. "
        "Entweder eine Quelle auf beliebig viele Ziele oder gleich viele "
        "Quellen wie Ziele (dann paarweise in Reihenfolge).")


# ── Werte übersetzen ────────────────────────────────────────────────────────

@dataclass
class Uebersetzung:
    """Was aus den Werten EINER Stelle am Ziel wird."""
    gleich: dict = field(default_factory=dict)       # Ziel-Schlüssel → Wert
    uebersetzt: dict = field(default_factory=dict)   # Ziel-Schlüssel → Wert
    texte: list = field(default_factory=list)        # „Farbe … → …"
    weg: list = field(default_factory=list)          # (Quell-Schlüssel, Grund)

    @property
    def werte(self) -> dict:
        out = dict(self.gleich)
        out.update(self.uebersetzt)
        return out


def uebersetze_werte(werte: dict, quelle: _Geraet, ziel: _Geraet) -> Uebersetzung:
    """Attribut-Werte der Quelle → Attribut-Werte des Ziels.

    Gleicher Typ und Modus: alles 1:1. Verschiedener Typ: Dimmer → Dimmer,
    Farbe → Farbe über die sichtbare Farbe; der Rest fällt weg.
    """
    u = Uebersetzung()
    if not isinstance(werte, dict):
        return u
    if _gleicher_typ(quelle, ziel):
        u.gleich = dict(werte)
        return u
    farbe: dict = {}
    for key, val in werte.items():
        basis, _, kopf = str(key).partition("#")
        b = basis.lower()
        if kopf:
            u.weg.append((key, GRUND_KOPF))
        elif b in _DIMMER:
            zk = b if b in ziel.attrs else next(
                (a for a in _DIMMER if a in ziel.attrs), None)
            if zk is None:
                u.weg.append((key, "Ziel hat keinen Dimmer"))
            else:
                u.gleich.setdefault(zk, val)
        elif classify_attr(b) == "Color":
            farbe[b] = val
        else:
            u.weg.append((key, GRUND_SPAETER))
    if farbe:
        _uebersetze_farbe(farbe, quelle, ziel, u)
    return u


def _zahl(wert) -> int:
    try:
        return max(0, min(255, int(wert)))
    except (TypeError, ValueError):
        return 0


def _uebersetze_farbe(farbe: dict, quelle: _Geraet, ziel: _Geraet,
                      u: Uebersetzung) -> None:
    from .. import color_utils as C
    misch = {k: v for k, v in farbe.items() if k in _MISCH}
    cmy = next(({k: farbe[k] for k in t if k in farbe}
                for t in _CMY if any(k in farbe for k in t)), {})
    gemischt = False

    # Amber/UV: eigene Emitter — nur, wenn beide Geräte sie haben.
    for k in _EXTRA:
        if k in farbe:
            if k in ziel.attrs:
                u.gleich[k] = farbe[k]
            else:
                u.weg.append((k, f"Ziel hat kein {attr_label(k)}"))

    if misch:
        if (quelle.attrs & set(_MISCH)) == (ziel.attrs & set(_MISCH)):
            u.gleich.update(misch)          # dieselbe Mischung → Werte 1:1
            gemischt = True
        else:
            rgb = C.rgbw_to_display(misch.get("color_r"), misch.get("color_g"),
                                    misch.get("color_b"), misch.get("color_w"))
            gemischt = _schreibe_farbe(rgb, list(misch), ziel, u)
        for k in cmy:
            u.weg.append((k, "die Farbe kommt schon aus der RGB-Mischung"))
    elif cmy:
        if all(k in ziel.attrs for k in cmy):
            u.gleich.update(cmy)
            gemischt = True
        else:
            namen = next(t for t in _CMY if any(k in cmy for k in t))
            rgb = tuple(255 - _zahl(cmy.get(k, 0)) for k in namen)
            gemischt = _schreibe_farbe(rgb, list(cmy), ziel, u)

    bekannt = set(_MISCH) | set(_EXTRA) | set(_RAD) | {k for t in _CMY for k in t}
    for k in farbe:
        if k not in bekannt:            # z. B. Farbtemperatur, Farb-Makro
            u.weg.append((k, "für diesen Farbkanal gibt es keine Übersetzung"))

    for k in _RAD:
        if k not in farbe:
            continue
        kanal = next((c for c in quelle.kanaele
                      if (getattr(c, "attribute", "") or "").lower() == k), None)
        slot = C._wheel_slot_rgb(kanal, _zahl(farbe[k])) if kanal is not None else None
        ziel_rad = any(r in ziel.attrs for r in _RAD)
        if slot is None:
            u.weg.append((k, "Farbrad-Stellung ohne erkennbare Farbe "
                             "(kein Farbwort im Namen oder Rotation)"))
        elif gemischt and not ziel_rad:
            u.weg.append((k, "die Farbe kommt schon aus der Farbmischung"))
        else:
            _schreibe_farbe(slot, [k], ziel, u, nur_rad=gemischt)


def _schreibe_farbe(rgb, quell_keys: list, ziel: _Geraet, u: Uebersetzung,
                    nur_rad: bool = False) -> bool:
    """Sichtbare Farbe ``rgb`` ins Ziel schreiben. ``True`` = geschrieben."""
    from .. import color_utils as C
    kanaele = ziel.kanaele
    if nur_rad:
        kanaele = [c for c in kanaele
                   if (getattr(c, "attribute", "") or "").lower() in _RAD]
    roh = C.color_attrs_for_fixture(kanaele, rgb, cmy=True)
    farbtext = f"Farbe ({rgb[0]}, {rgb[1]}, {rgb[2]})"
    if any(k in roh for k in ("color_r", "color_g", "color_b")):
        werte = {k: v for k, v in C.adapt_color_payload(ziel.attrs, roh).items()
                 if k in _MISCH and k in ziel.attrs}
        zusatz = ""
    elif any(k in roh for t in _CMY for k in t):
        werte, zusatz = roh, ""
    elif any(k in roh for k in _RAD):
        werte = {k: v for k, v in roh.items() if k in _RAD}
        zusatz = " (ungefähr: nächster Farbrad-Platz)"
    else:
        grund = ("im Farbrad des Ziels gibt es keinen passenden Platz"
                 if any(r in ziel.attrs for r in _RAD)
                 else "Ziel hat nur Weiß, keine Farbmischung"
                 if ("color_w" in ziel.attrs or "white" in ziel.attrs)
                 else "Ziel hat keine Farbe")
        for k in quell_keys:
            u.weg.append((k, grund))
        return False
    u.uebersetzt.update(werte)
    u.texte.append(farbtext + " → "
                   + " · ".join(f"{attr_label(k)} {v}" for k, v in werte.items())
                   + zusatz)
    return True


# ── Schritte für Werte ──────────────────────────────────────────────────────

def _finde_schluessel(behaelter, fid: int):
    """Der Schlüssel, unter dem ``fid`` in einem Werte-Dict steht (int oder
    Text — Sequenzen und Snapshots halten Text), sonst ``None``."""
    if not isinstance(behaelter, dict):
        return None
    if fid in behaelter:
        return fid
    if str(fid) in behaelter:
        return str(fid)
    return None


def _werte_mischen(stand, neu: dict, wie: str):
    out = dict(stand) if isinstance(stand, dict) else {}
    for k, v in neu.items():
        if wie == ERSETZEN or k not in out:
            out[k] = v
    return out or (None if stand is None else out)


def _werte_entfernen(jetzt, vor, nach):
    if not isinstance(jetzt, dict):
        return jetzt
    vor = vor if isinstance(vor, dict) else {}
    out = dict(jetzt)
    for k, v in (nach or {}).items():
        if k in out and out[k] == v and vor.get(k, _FEHLT) != v:
            if k in vor:
                out[k] = vor[k]
            else:
                del out[k]
    return out or (None if not vor else out)


_FEHLT = object()


def _werte_schritt(behaelter: Callable, schluessel, neu: dict, wie: str) -> Schritt:
    """Schritt auf ``behaelter()[schluessel]`` (ein ``{attr: wert}``-Dict)."""
    def lesen():
        d = behaelter()
        v = d.get(schluessel) if isinstance(d, dict) else None
        return dict(v) if isinstance(v, dict) else None

    def schreiben(stand):
        d = behaelter()
        if not isinstance(d, dict):
            return
        if stand is None:
            d.pop(schluessel, None)
            return
        alt = d.get(schluessel)
        if isinstance(alt, dict):           # Objekt behalten, Inhalt tauschen
            alt.clear()
            alt.update(stand)
        else:
            d[schluessel] = dict(stand)

    return Schritt(lesen, schreiben,
                   lambda stand: _werte_mischen(stand, neu, wie),
                   _werte_entfernen)


# ── Schritte für Listen, Bewegungs-Effekte, Matrix, Gruppen, Szenen ─────────

def _liste_einfuegen(liste: list, q: int, z: int, position: str) -> list:
    if z in liste or q not in liste:
        return liste
    out = list(liste)
    if position == POS_NEBEN:
        letzter = max(i for i, x in enumerate(out) if x == q)
        out.insert(letzter + 1, z)
    else:
        out.append(z)
    return out


def _listen_schritt(holen: Callable, setzen: Callable, q: int, z: int,
                    position: str) -> Schritt:
    def lesen():
        l = holen()
        return [_als_int(x) for x in l] if isinstance(l, list) else None

    def einfuegen(stand):
        return stand if stand is None else _liste_einfuegen(stand, q, z, position)

    def entfernen(jetzt, _vor, _nach):
        return jetzt if jetzt is None else [x for x in jetzt if x != z]

    return Schritt(lesen, lambda stand: stand is not None and setzen(list(stand)),
                   einfuegen, entfernen)


def _als_int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return x


_EFX_FELDER = ("fid", "start_offset", "pan_attr", "tilt_attr", "head")


def _efx_schritt(efx, q: _Geraet, z: _Geraet, position: str) -> Schritt:
    gleich = _gleicher_typ(q, z)

    def lesen():
        return [{f: getattr(x, f, None) for f in _EFX_FELDER}
                for x in (efx.fixtures or [])]

    def schreiben(stand):
        from ..engine.efx import EfxFixture
        alt = list(efx.fixtures or [])
        neu = []
        for d in stand:
            treffer = next((x for x in alt if all(
                getattr(x, f, None) == d[f] for f in _EFX_FELDER)), None)
            if treffer is not None:
                alt.remove(treffer)          # vorhandenes Objekt weiterbenutzen
                neu.append(treffer)
            else:
                neu.append(EfxFixture(
                    fid=d["fid"], start_offset=d["start_offset"] or 0.0,
                    pan_attr=d["pan_attr"] or "pan",
                    tilt_attr=d["tilt_attr"] or "tilt", head=d["head"]))
        efx.fixtures = neu

    def einfuegen(stand):
        if any(d["fid"] == z.fid for d in stand):
            return stand
        quell = [(i, d) for i, d in enumerate(stand) if d["fid"] == q.fid]
        if not quell:
            return stand
        neu = []
        for _i, d in quell:
            if gleich or d["head"] is None:
                neu.append(dict(d, fid=z.fid))
        if not neu:                          # nur Kopf-Ziele, anderer Typ
            neu.append(dict(quell[0][1], fid=z.fid, head=None))
        out = list(stand)
        if position == POS_NEBEN:
            stelle = quell[-1][0] + 1
            out[stelle:stelle] = neu
        else:
            out.extend(neu)
        return out

    def entfernen(jetzt, _vor, _nach):
        return [d for d in jetzt if d["fid"] != z.fid]

    return Schritt(lesen, schreiben, einfuegen, entfernen)


def _auffuellen(liste: list, laenge: int) -> None:
    while len(liste) < laenge:
        liste.append(None)


def _matrix_schritt(m, q: _Geraet, z: _Geraet, position: str) -> Schritt:
    gleich = _gleicher_typ(q, z)

    def lesen():
        return {"cols": int(m.cols), "rows": int(m.rows),
                "fixture_grid": list(m.fixture_grid or []),
                "head_grid": list(m.head_grid or []),
                "weiss_grid": [tuple(w) if isinstance(w, (list, tuple)) else None
                               for w in (m.weiss_grid or [])]}

    def schreiben(stand):
        m.cols, m.rows = stand["cols"], stand["rows"]
        m.fixture_grid = list(stand["fixture_grid"])
        m.head_grid = list(stand["head_grid"])
        m.weiss_grid = list(stand["weiss_grid"])
        # Der Live-Rückfall (``reset_live``) spielt ``_preset`` als Ganzes
        # zurück — ohne das hier verschwände das Ziel beim nächsten Reset.
        preset = getattr(m, "_preset", None)
        if isinstance(preset, dict):
            for k in ("cols", "rows", "fixture_grid", "head_grid", "weiss_grid"):
                preset[k] = copy.deepcopy(stand[k])

    def einfuegen(stand):
        return _matrix_einfuegen(stand, q.fid, z.fid, gleich, position)[0]

    def entfernen(jetzt, _vor, _nach):
        fg, hg, wg = jetzt["fixture_grid"], jetzt["head_grid"], jetzt["weiss_grid"]
        for i, f in enumerate(fg):
            if f == z.fid:
                fg[i] = None
                if i < len(hg):
                    hg[i] = None
        for i, w in enumerate(wg):
            if w and w[0] == z.fid:
                wg[i] = None
        return jetzt

    return Schritt(lesen, schreiben, einfuegen, entfernen)


def _matrix_einfuegen(stand: dict, q: int, z: int, gleich: bool,
                      position: str) -> tuple:
    """``(neuer Stand, info)``. ``info``: ``neu`` (Zellen), ``schon``,
    ``koepfe_zusammen``, ``weiss_weg``, ``gewachsen``."""
    info = {"neu": 0, "schon": False, "koepfe_zusammen": False,
            "weiss_weg": 0, "gewachsen": False, "quelle": False}
    fg, hg, wg = stand["fixture_grid"], stand["head_grid"], stand["weiss_grid"]
    i_f = [i for i, f in enumerate(fg) if f == q]
    i_w = [i for i, w in enumerate(wg) if w and w[0] == q]
    if not i_f and not i_w:
        return stand, info
    info["quelle"] = True
    if z in fg or any(w and w[0] == z for w in wg):
        info["schon"] = True
        return stand, info
    neu: list[tuple] = []        # (fid | None, kopf | None, weiss | None)
    if gleich:
        for i in sorted(set(i_f) | set(i_w)):
            neu.append((z if i in i_f else None,
                        hg[i] if i in i_f and i < len(hg) else None,
                        (z, wg[i][1]) if i in i_w else None))
    else:
        for i in i_f:
            if i >= len(hg) or hg[i] is None:
                neu.append((z, None, None))
        if not neu and i_f:
            neu.append((z, None, None))
            info["koepfe_zusammen"] = True
        info["weiss_weg"] = len(i_w)
    if not neu:
        return stand, info
    cols, rows = max(1, stand["cols"]), max(1, stand["rows"])
    eindimensional = rows == 1 or cols == 1
    eine_zeile = rows == 1          # sonst Spalte oder echtes Raster

    def wachsen():
        nonlocal cols, rows
        if eine_zeile:
            cols += 1               # eine Zeile wird länger
        else:
            rows += 1               # Spalte wird länger / Raster bekommt eine Zeile
        info["gewachsen"] = True

    def setzen(i, zelle, schieben=False):
        fid, kopf, weiss = zelle
        for liste, wert, noetig in ((fg, fid, True),
                                    (hg, kopf, bool(hg) or kopf is not None),
                                    (wg, weiss, bool(wg) or weiss is not None)):
            if not noetig:
                continue
            _auffuellen(liste, i if schieben else i + 1)
            if schieben:
                liste.insert(i, wert)
            else:
                liste[i] = wert

    if position == POS_NEBEN and eindimensional:
        stelle = max(i_f + i_w) + 1
        for zelle in neu:
            setzen(stelle, zelle, schieben=True)
            stelle += 1
            wachsen()
    else:
        belegt = [i for i, f in enumerate(fg) if f is not None]
        belegt += [i for i, w in enumerate(wg) if w]
        stelle = (max(belegt) + 1) if belegt else 0
        for zelle in neu:
            while stelle >= cols * rows:
                wachsen()
            setzen(stelle, zelle)
            stelle += 1
    info["neu"] = len(neu)
    stand["cols"], stand["rows"] = cols, rows
    return stand, info


def _gruppe_einfuegen(stand, q: int, z: int, gleich: bool, position: str) -> tuple:
    """``(neuer Stand, info)`` für eine Fixture-Gruppe
    (``stand = {"cols", "rows", "roh": positions_json}``)."""
    info = {"neu": 0, "schon": False, "koepfe_zusammen": False, "weiss_weg": 0,
            "ans_ende_statt_neben": False, "quelle": False, "unlesbar": False}
    if stand is None:
        return stand, info
    try:
        pos = json.loads(stand["roh"] or "{}")
    except Exception:
        pos = None
    if not isinstance(pos, dict):
        info["unlesbar"] = True
        return stand, info
    rc: dict[tuple, str] = {}
    for key in pos:
        try:
            c_s, r_s = str(key).split(",")
            rc[(int(r_s), int(c_s))] = key
        except (TypeError, ValueError):
            continue
    quell = sorted((r, c) for (r, c), key in rc.items()
                   if parse_zelle(pos[key])[0] == q)
    if not quell:
        return stand, info
    info["quelle"] = True
    if any(parse_zelle(v)[0] == z for v in pos.values()):
        info["schon"] = True
        return stand, info
    neu: list[tuple] = []                  # (anker, zellwert)
    kopf_anker = None
    for anker in quell:
        wert = pos[rc[anker]]
        _f, achse, index = parse_zelle(wert)
        if achse is None:
            neu.append((anker, z if isinstance(wert, int) else zelle_fuer(z)))
        elif gleich:
            neu.append((anker, zelle_fuer(z, achse, index)))
        elif achse == ACHSE_FARBE:
            kopf_anker = kopf_anker or anker
        else:
            info["weiss_weg"] += 1
    if kopf_anker is not None and not any(
            parse_zelle(w)[1] is None for _a, w in neu):
        neu.append((kopf_anker, zelle_fuer(z)))
        info["koepfe_zusammen"] = True
    if not neu:
        return stand, info
    cols, rows = max(1, int(stand["cols"] or 1)), max(1, int(stand["rows"] or 1))

    def setze(r, c, wert):
        key = f"{c},{r}"
        pos[key] = wert
        rc[(r, c)] = key

    def ans_ende(wert):
        nonlocal rows
        r, c = max(rc) if rc else (0, -1)
        c += 1
        if c >= cols:
            r, c = r + 1, 0
        rows = max(rows, r + 1)
        setze(r, c, wert)

    def daneben(anker, wert) -> bool:
        nonlocal cols
        r, c = anker
        einzeilig = len({rr for rr, _ in rc}) == 1
        if (r, c + 1) not in rc and (c + 1 < cols or einzeilig):
            cols = max(cols, c + 2)
            setze(r, c + 1, wert)
            return True
        if not einzeilig:
            return False
        for cc in sorted((cc for (rr, cc) in rc if rr == r and cc > c),
                         reverse=True):
            alt = rc.pop((r, cc))
            setze(r, cc + 1, pos.pop(alt))
        cols = max(cols, max(cc for _rr, cc in rc) + 1, c + 2)
        setze(r, c + 1, wert)
        return True

    # „Neben die Quelle" heißt: als Block hinter ihre LETZTE Zelle — ein
    # Mehrkopf-Gerät wird nicht Kopf für Kopf mit dem Ziel verzahnt.
    anker = quell[-1]
    neben = position == POS_NEBEN
    for _quelle, wert in neu:
        if neben and daneben(anker, wert):
            anker = (anker[0], anker[1] + 1)
            continue
        if neben:
            info["ans_ende_statt_neben"] = True
            neben = False
        ans_ende(wert)
    info["neu"] = len(neu)
    return {"cols": cols, "rows": rows, "roh": json.dumps(pos)}, info


def _gruppen_schritt(state, gid: int, q: _Geraet, z: _Geraet,
                     position: str) -> Schritt:
    gleich = _gleicher_typ(q, z)

    def lesen():
        from ..database.models import FixtureGroup
        with state._session() as s:
            g = s.get(FixtureGroup, gid)
            if g is None:
                return None
            return {"cols": g.cols, "rows": g.rows, "roh": g.positions_json or "{}"}

    def schreiben(stand):
        if stand is None:
            return
        from ..database.models import FixtureGroup
        with state._session() as s:
            g = s.get(FixtureGroup, gid)
            if g is None:
                return
            g.cols, g.rows, g.positions_json = stand["cols"], stand["rows"], stand["roh"]
            s.commit()

    def einfuegen(stand):
        return _gruppe_einfuegen(stand, q.fid, z.fid, gleich, position)[0]

    def entfernen(jetzt, _vor, _nach):
        if jetzt is None:
            return None
        try:
            pos = json.loads(jetzt["roh"] or "{}")
        except Exception:
            return jetzt
        if not isinstance(pos, dict):
            return jetzt
        rest = {k: v for k, v in pos.items() if parse_zelle(v)[0] != z.fid}
        return dict(jetzt, roh=json.dumps(rest))

    return Schritt(lesen, schreiben, einfuegen, entfernen)


def _szenen_schritt(szene, z: int, neu: dict, wie: str) -> Schritt:
    """``neu`` = ``{kanalnummer: wert}`` für das Ziel."""
    def lesen():
        return [(sv.fixture_id, sv.channel, sv.value) for sv in szene._values]

    def schreiben(stand):
        from ..engine.scene import SceneValue
        szene._values[:] = [SceneValue(f, c, v) for f, c, v in stand]

    def einfuegen(stand):
        out = list(stand)
        stellen = {c: i for i, (f, c, _v) in enumerate(out) if f == z}
        for ch, val in neu.items():
            if ch in stellen:
                if wie == ERSETZEN:
                    out[stellen[ch]] = (z, ch, val)
            else:
                out.append((z, ch, val))
        return out

    def entfernen(jetzt, vor, nach):
        vor_z = {c: v for f, c, v in (vor or []) if f == z}
        nach_z = {c: v for f, c, v in (nach or []) if f == z}
        out = []
        for f, c, v in jetzt:
            if f == z and nach_z.get(c, _FEHLT) == v and vor_z.get(c, _FEHLT) != v:
                if c in vor_z:
                    out.append((f, c, vor_z[c]))
                continue
            out.append((f, c, v))
        return out

    return Schritt(lesen, schreiben, einfuegen, entfernen)


# ── Vorschau-Zeilen aus Übersetzungen sammeln ───────────────────────────────

def _labels(keys) -> str:
    return ", ".join(_ohne_doppelte(attr_label(str(k)) for k in keys))


class _Sammler:
    """Fasst die Stellen EINES Objekts für EIN Paar zu wenigen Zeilen zusammen
    (eine Cueliste mit 40 Cues wird eine Zeile je Kennzeichen, nicht 120)."""

    def __init__(self, bereich: str, objekt: str, q: _Geraet, z: _Geraet, wie: str):
        self.bereich, self.objekt, self.q, self.z, self.wie = bereich, objekt, q, z, wie
        self.gleich: list = []
        self.uebersetzt_texte: list = []
        self.weg: dict[str, list] = {}
        self.bleibt: list = []
        self.ersetzt = False
        self.stellen = 0
        self.schritte: list = []

    def nimm(self, u: Uebersetzung, vorhandene, schritt) -> None:
        """``vorhandene``: Ziel-Schlüssel, die das Ziel an der Stelle schon hat."""
        vorhandene = set(vorhandene or ())
        for key, grund in u.weg:
            self.weg.setdefault(grund, []).append(key)
        schreibt = False
        for key in u.gleich:
            if key in vorhandene and self.wie != ERSETZEN:
                self.bleibt.append(key)
            else:
                self.gleich.append(key)
                schreibt = True
        offen = [k for k in u.uebersetzt
                 if not (k in vorhandene and self.wie != ERSETZEN)]
        self.bleibt.extend(k for k in u.uebersetzt if k not in offen)
        if offen:
            self.uebersetzt_texte.extend(u.texte)
            schreibt = True
        if schreibt:
            self.stellen += 1
            if vorhandene & set(u.werte) and self.wie == ERSETZEN:
                self.ersetzt = True
            if schritt is not None:
                self.schritte.append(schritt)

    def eintraege(self) -> list:
        out: list[Eintrag] = []
        art = "ersetzt" if self.ersetzt else "ergaenzt"
        mal = f" · {self.stellen} Stellen" if self.stellen > 1 else ""
        schritte = list(self.schritte)

        def neu(kennzeichen, text, mit_schritten=False):
            out.append(Eintrag(self.bereich, self.objekt, self.q.fid, self.z.fid,
                               kennzeichen, text,
                               art=art if mit_schritten else "",
                               schritte=schritte if mit_schritten else []))

        if self.gleich:
            neu(UNVERAENDERT, _labels(self.gleich) + mal, True)
        if self.uebersetzt_texte:
            texte = _ohne_doppelte(self.uebersetzt_texte)
            neu(UEBERSETZT, "; ".join(texte[:3])
                + (f" … und {len(texte) - 3} weitere" if len(texte) > 3 else ""),
                True)
        for grund, keys in self.weg.items():
            neu(FAELLT_WEG, f"{_labels(keys)} — {grund}")
        if self.bleibt:
            neu(BLEIBT, f"{_labels(self.bleibt)} — das Ziel hat dort schon einen Wert")
        return out


# ── Der Plan ────────────────────────────────────────────────────────────────

def plane(state, quellen, ziele, optionen: Optionen, *,
          snap_library=None, palette_manager=None) -> Plan:
    """Rechnet den Klon-Plan. Schreibt nichts."""
    if optionen.wie not in (HINZUFUEGEN, ERSETZEN):
        raise KlonFehler("Bitte wählen: Hinzufügen oder Ersetzen.")
    paare = paare_bilden(quellen, ziele)
    geraete = _geraete(state)
    fehlend = sorted({f for paar in paare for f in paar if f not in geraete})
    if fehlend:
        raise KlonFehler(f"Gerät {_nummern_text(fehlend)} ist nicht gepatcht.")
    plan = Plan(paare=paare, optionen=optionen)
    plan._melder = lambda st, bereiche: _benachrichtigen(
        st, bereiche, palette_manager)
    for q_fid, z_fid in paare:
        q, z = geraete[q_fid], geraete[z_fid]
        _hinweise(plan, q, z)
        for bereich in BEREICHE:
            if bereich in optionen.bereiche:
                _PLANER[bereich](plan, state, q, z, optionen,
                                 snap_library, palette_manager)
    plan.hinweise = _ohne_doppelte(plan.hinweise)
    return plan


def _hinweise(plan: Plan, q: _Geraet, z: _Geraet) -> None:
    if not _gleicher_typ(q, z):
        plan.hinweise.append(
            f"{q.fid} „{q.name}“ und {z.fid} „{z.name}“ sind verschiedene "
            "Gerätetypen: Dimmer und Farbe werden übersetzt; Bewegung, Zoom, "
            "Fokus, Gobo, Prisma, Shutter und Makros kommen in einem späteren "
            "Schritt und fallen bei gespeicherten Werten weg.")
        if not z.kanaele:
            plan.hinweise.append(
                f"Zu {z.fid} „{z.name}“ sind keine Kanäle bekannt (Profil fehlt) "
                "— gespeicherte Werte können nicht übertragen werden.")
    if not q.hat_dimmer and z.hat_dimmer:
        plan.hinweise.append(
            f"{q.fid} „{q.name}“ hat keinen Dimmer: {z.fid} „{z.name}“ bekommt "
            "keinen Dimmerwert. Farbe und Dimmer bleiben getrennt — den Dimmer "
            "des Ziels stellst du selbst ein.")


def _mitglied(plan: Plan, bereich: str, objekt: str, q: _Geraet, z: _Geraet,
              schritt: Schritt | None, *, schon: bool, text: str,
              kennzeichen: str = UNVERAENDERT) -> None:
    if schon:
        plan.eintraege.append(Eintrag(bereich, objekt, q.fid, z.fid, BLEIBT,
                                      "das Ziel ist schon dabei"))
        return
    plan.eintraege.append(Eintrag(bereich, objekt, q.fid, z.fid, kennzeichen, text,
                                  art="ergaenzt",
                                  schritte=[schritt] if schritt else []))


def _weg(plan: Plan, bereich: str, objekt: str, q: _Geraet, z: _Geraet,
         text: str) -> None:
    plan.eintraege.append(Eintrag(bereich, objekt, q.fid, z.fid, FAELLT_WEG, text))


def _wo(position: str) -> str:
    return "neben die Quelle" if position == POS_NEBEN else "ans Ende"


def _plane_gruppen(plan, state, q, z, opt, _snaps, _pal) -> None:
    if getattr(state, "_show_engine", None) is None:
        return
    from sqlalchemy import select
    from ..database.models import FixtureGroup
    with state._session() as s:
        gruppen = [(g.id, g.name or "", g.cols, g.rows, g.positions_json or "{}")
                   for g in s.execute(select(FixtureGroup)).scalars()]
    eigene = None
    finde = getattr(state, "find_head_matrix_group", None)
    if callable(finde):
        eigene = finde(q.fid, dedicated=True)
    gleich = _gleicher_typ(q, z)
    for gid, name, cols, rows, roh in gruppen:
        if gid == eigene:
            continue          # die automatische Köpfe-Gruppe gehört der Quelle
        _neu, info = _gruppe_einfuegen({"cols": cols, "rows": rows, "roh": roh},
                                       q.fid, z.fid, gleich, opt.position)
        objekt = f"Gruppe „{name}“"
        if info["unlesbar"]:
            _weg(plan, BEREICH_GRUPPEN, objekt, q, z,
                 "das Raster der Gruppe ist nicht lesbar — nicht angefasst")
            continue
        if not info["quelle"] and not info["schon"]:
            continue
        if not info["schon"] and not info["neu"]:
            _weg(plan, BEREICH_GRUPPEN, objekt, q, z,
                 "die Quelle steht hier nur mit Weiß-Segmenten — zwischen "
                 "verschiedenen Gerätetypen kommt das in einem späteren Schritt")
            continue
        wo = ("ans Ende (neben der Quelle ist im Raster kein Platz)"
              if info["ans_ende_statt_neben"] else _wo(opt.position))
        text = (f"Mitglied, {wo}" if info["neu"] == 1
                else f"Mitglied mit {info['neu']} Zellen, {wo}")
        kennz = UNVERAENDERT
        if info["koepfe_zusammen"]:
            kennz = UEBERSETZT
            text += " — die Kopf-Zellen der Quelle werden zu einer Zelle für das ganze Gerät"
        _mitglied(plan, BEREICH_GRUPPEN, objekt, q, z,
                  _gruppen_schritt(state, gid, q, z, opt.position),
                  schon=info["schon"], text=text, kennzeichen=kennz)
        if info["weiss_weg"] and not info["schon"]:
            _weg(plan, BEREICH_GRUPPEN, objekt, q, z,
                 f"{info['weiss_weg']} Weiß-Segment-Zelle(n) — {GRUND_SPAETER}")


def _funktionen(state) -> list:
    fm = getattr(state, "function_manager", None)
    return list(fm.all()) if fm is not None else []


def _plane_effekte(plan, state, q, z, opt, _snaps, _pal) -> None:
    from ..engine.efx import EfxInstance
    from ..engine.rgb_matrix import RgbMatrixInstance
    gleich = _gleicher_typ(q, z)
    for f in _funktionen(state):
        name = getattr(f, "name", "") or f"Funktion {getattr(f, 'id', '?')}"
        if isinstance(f, RgbMatrixInstance):
            schritt = _matrix_schritt(f, q, z, opt.position)
            vor, _nach = schritt.vorschau()
            _n, info = _matrix_einfuegen(copy.deepcopy(vor), q.fid, z.fid,
                                         gleich, opt.position)
            objekt = f"Matrix „{name}“"
            if not info["quelle"] and not info["schon"]:
                continue
            if not info["schon"] and not (z.hat_farbe or z.hat_dimmer):
                _weg(plan, BEREICH_EFFEKTE, objekt, q, z,
                     "das Ziel hat weder Farbe noch Dimmer")
                continue
            if not info["schon"] and not info["neu"]:
                _weg(plan, BEREICH_EFFEKTE, objekt, q, z,
                     f"Weiß-Segment-Zellen — {GRUND_SPAETER}")
                continue
            text = (f"im Raster {_wo(opt.position)}"
                    + (f" ({info['neu']} Zellen)" if info["neu"] > 1 else "")
                    + (f", Raster wächst auf {_n['cols']}×{_n['rows']}"
                       if info["gewachsen"] else ""))
            kennz = UNVERAENDERT
            if info["koepfe_zusammen"]:
                kennz = UEBERSETZT
                text += " — die Kopf-Zellen der Quelle werden zu einer Zelle für das ganze Gerät"
            _mitglied(plan, BEREICH_EFFEKTE, objekt, q, z, schritt,
                      schon=info["schon"], text=text, kennzeichen=kennz)
            if info["weiss_weg"] and not info["schon"]:
                _weg(plan, BEREICH_EFFEKTE, objekt, q, z,
                     f"{info['weiss_weg']} Weiß-Segment-Zelle(n) — {GRUND_SPAETER}")
        elif isinstance(f, EfxInstance):
            ziele = list(f.fixtures or [])
            quell = [x for x in ziele if x.fid == q.fid]
            if not quell:
                continue
            schon = any(x.fid == z.fid for x in ziele)
            objekt = f"Bewegung „{name}“"
            achsen = [(quell[0].pan_attr or "pan").lower(),
                      (quell[0].tilt_attr or "tilt").lower()]
            if not schon and not (set(achsen) & z.attrs):
                _weg(plan, BEREICH_EFFEKTE, objekt, q, z,
                     "das Ziel hat die Bewegungs-Kanäle nicht ("
                     + ", ".join(attr_label(a) for a in achsen) + ")")
                continue
            schritt = _efx_schritt(f, q, z, opt.position)
            vor, nach = schritt.vorschau()
            text = (f"in den Fächer {_wo(opt.position)} — der Fächer verteilt "
                    f"sich neu ({len(vor)} → {len(nach)} Ziele)")
            kennz = UNVERAENDERT
            if not gleich and all(x.head is not None for x in quell):
                kennz = UEBERSETZT
                text += ("; die Kopf-Ziele der Quelle werden zu einem Ziel "
                         "für das ganze Gerät")
            _mitglied(plan, BEREICH_EFFEKTE, objekt, q, z, schritt,
                      schon=schon, text=text, kennzeichen=kennz)
        elif isinstance(getattr(f, "fixture_ids", None), list):
            liste = f.fixture_ids
            if q.fid not in liste:
                continue
            _mitglied(plan, BEREICH_EFFEKTE, f"Effekt „{name}“", q, z,
                      _listen_schritt(lambda f=f: f.fixture_ids,
                                      lambda l, f=f: setattr(f, "fixture_ids", l),
                                      q.fid, z.fid, opt.position),
                      schon=z.fid in liste,
                      text=f"in die Geräteliste {_wo(opt.position)}")


def _plane_werte(sammler: _Sammler, behaelter: Callable, q: _Geraet, z: _Geraet,
                 wie: str, zusatz: tuple = ()) -> None:
    """Eine ``{fid: {attr: wert}}``-Stelle. ``zusatz``: weitere Behälter mit
    derselben Form (Cue-Verzögerungen), die den geschriebenen Attributen folgen."""
    d = behaelter()
    qk = _finde_schluessel(d, q.fid)
    if qk is None or not isinstance(d.get(qk), dict):
        return
    u = uebersetze_werte(d[qk], q, z)
    zk = _finde_schluessel(d, z.fid)
    if zk is None:
        zk = str(z.fid) if isinstance(qk, str) else z.fid
    vorhandene = set(d.get(zk) or {}) if isinstance(d.get(zk), dict) else set()
    schritt = _werte_schritt(behaelter, zk, u.werte, wie) if u.werte else None
    vorher = len(sammler.schritte)
    sammler.nimm(u, vorhandene, schritt)
    if len(sammler.schritte) == vorher:
        return
    for neben in zusatz:
        nd = neben()
        nqk = _finde_schluessel(nd, q.fid)
        if nqk is None or not isinstance(nd.get(nqk), dict):
            continue
        mit = {k: v for k, v in nd[nqk].items() if k in u.werte}
        if mit:
            nzk = _finde_schluessel(nd, z.fid)
            if nzk is None:
                nzk = str(z.fid) if isinstance(nqk, str) else z.fid
            sammler.schritte.append(_werte_schritt(neben, nzk, mit, wie))


def _plane_snaps(plan, state, q, z, opt, snap_library, _pal) -> None:
    if snap_library is None:
        from ..engine.snap_library import get_snap_library
        snap_library = get_snap_library()
    for snap in snap_library.snaps():
        ort = f"{snap.folder} / " if getattr(snap, "folder", "") else ""
        sm = _Sammler(BEREICH_SNAPS, f"Snap „{ort}{snap.name}“", q, z, opt.wie)
        _plane_werte(sm, lambda snap=snap: snap.values, q, z, opt.wie)
        plan.eintraege.extend(sm.eintraege())
    for i, slot in enumerate(getattr(state, "_snapshots_data", None) or []):
        if not isinstance(slot, dict) or not isinstance(slot.get("values"), dict):
            continue
        name = slot.get("name") or f"Platz {i + 1}"
        sm = _Sammler(BEREICH_SNAPS, f"Snapshot „{name}“", q, z, opt.wie)
        _plane_werte(sm, lambda i=i: _snapshot_werte(state, i), q, z, opt.wie)
        plan.eintraege.extend(sm.eintraege())
    from ..engine.scene import Scene
    for f in _funktionen(state):
        if isinstance(f, Scene):
            _plane_szene(plan, f, q, z, opt)


def _snapshot_werte(state, i: int) -> dict:
    daten = getattr(state, "_snapshots_data", None) or []
    if i < len(daten) and isinstance(daten[i], dict):
        werte = daten[i].get("values")
        if isinstance(werte, dict):
            return werte
    return {}


def _plane_szene(plan, szene, q: _Geraet, z: _Geraet, opt) -> None:
    """★ Eine Szene speichert KANALNUMMERN, keine Attribute. Zwischen
    verschiedenen Typen geht der Weg Kanal → Attribut → (übersetzen) → Kanal."""
    from .. import app_state as A
    quell = {sv.channel: sv.value for sv in szene._values if sv.fixture_id == q.fid}
    if not quell:
        return
    sm = _Sammler(BEREICH_SNAPS, f"Szene „{szene.name}“", q, z, opt.wie)
    vorhandene_kanaele = {sv.channel for sv in szene._values if sv.fixture_id == z.fid}
    if _gleicher_typ(q, z):
        je_kanal = dict(quell)
        namen = {ch: key for ch, key in q.schluessel()}
        u = Uebersetzung(gleich={namen.get(ch, f"Kanal {ch}"): v
                                 for ch, v in quell.items()})
        vorhandene = {namen.get(ch, f"Kanal {ch}") for ch in vorhandene_kanaele}
    else:
        namen = dict(q.schluessel())
        werte = {namen[ch]: v for ch, v in quell.items() if ch in namen}
        u = uebersetze_werte(werte, q, z)
        for ch in quell:
            if ch not in namen:
                u.weg.append((f"Kanal {ch}", "die Quelle hat diesen Kanal nicht "
                                             "(Szene aus einem größeren Modus)"))
        je_kanal, vorhandene = {}, set()
        for ch, key, val in A.resolve_attr_channels(z.kanaele, u.werte):
            je_kanal[int(ch)] = _zahl(val)
            if int(ch) in vorhandene_kanaele:
                vorhandene.add(key)
    schritt = _szenen_schritt(szene, z.fid, je_kanal, opt.wie) if je_kanal else None
    sm.nimm(u, vorhandene, schritt)
    plan.eintraege.extend(sm.eintraege())


def _plane_cues(plan, state, q, z, opt, _snaps, _pal) -> None:
    for si, stack in enumerate(getattr(state, "cue_stacks", None) or []):
        name = getattr(stack, "name", "") or f"Cueliste {si + 1}"
        sm = _Sammler(BEREICH_CUES, f"Cueliste „{name}“", q, z, opt.wie)
        for cue in (getattr(stack, "cues", None) or []):
            _plane_werte(sm, lambda cue=cue: cue.values, q, z, opt.wie,
                         zusatz=(lambda cue=cue: cue.attr_delays,
                                 lambda cue=cue: cue.attr_delays_out))
        plan.eintraege.extend(sm.eintraege())
    from ..engine.sequence import Sequence
    for f in _funktionen(state):
        if not isinstance(f, Sequence):
            continue
        sm = _Sammler(BEREICH_CUES, f"Sequenz „{f.name}“", q, z, opt.wie)
        for step in f.steps:
            _plane_werte(sm, lambda step=step: step.values, q, z, opt.wie)
        if sm.schritte and q.fid in f.bound_fixtures and z.fid not in f.bound_fixtures:
            sm.schritte.append(_listen_schritt(
                lambda f=f: f.bound_fixtures,
                lambda l, f=f: setattr(f, "bound_fixtures", l),
                q.fid, z.fid, opt.position))
        plan.eintraege.extend(sm.eintraege())


def _plane_paletten(plan, _state, q, z, opt, _snaps, palette_manager) -> None:
    if palette_manager is None:
        from ..engine.palette import get_palette_manager
        palette_manager = get_palette_manager()
    for pal in palette_manager.get_all():
        sm = _Sammler(BEREICH_PALETTEN, f"Palette „{pal.name}“", q, z, opt.wie)
        _plane_werte(sm, lambda pal=pal: pal.fixture_values, q, z, opt.wie)
        plan.eintraege.extend(sm.eintraege())


def _plane_grundwerte(plan, state, q, z, opt, _snaps, _pal) -> None:
    sm = _Sammler(BEREICH_GRUNDWERTE, "Grundwerte", q, z, opt.wie)
    _plane_werte(sm, lambda: state.base_levels, q, z, opt.wie)
    plan.eintraege.extend(sm.eintraege())


#: Felder eines Konsolen-Elements, die Geräte direkt nennen.
_VC_FELDER = {"blackout_fids": "Blackout-Ziel", "fixture_ids": "XY-Pad"}


def _vc_knoten(state, pfad: tuple, typ: str, caption: str):
    """Das Element am ``pfad`` des Konsolen-Layouts — nur, wenn dort noch
    dasselbe Element steht (Typ und Beschriftung)."""
    vc = getattr(state, "_vc_layout", None)
    knoten = vc if isinstance(vc, dict) else None
    for n, i in enumerate(pfad):
        kinder = (knoten or {}).get("widgets" if n == 0 else "children")
        if not isinstance(kinder, list) or i >= len(kinder):
            return None
        knoten = kinder[i]
        if not isinstance(knoten, dict):
            return None
    if knoten is None or knoten.get("type") != typ or knoten.get("caption") != caption:
        return None
    return knoten


def _vc_alle(state):
    vc = getattr(state, "_vc_layout", None)
    stapel = [((i,), w) for i, w in enumerate(
        vc.get("widgets") or [] if isinstance(vc, dict) else [])]
    while stapel:
        pfad, w = stapel.pop(0)
        if not isinstance(w, dict):
            continue
        yield pfad, w
        kinder = w.get("children")
        if isinstance(kinder, list):
            stapel.extend((pfad + (i,), k) for i, k in enumerate(kinder))


def _plane_konsole(plan, state, q, z, opt, _snaps, _pal) -> None:
    for pfad, w in _vc_alle(state):
        for feld, was in _VC_FELDER.items():
            liste = w.get(feld)
            if not isinstance(liste, list):
                continue
            ids = [_als_int(x) for x in liste]
            if q.fid not in ids:
                continue
            typ, caption = w.get("type"), w.get("caption")
            objekt = f"{was} „{caption or typ}“"
            if (feld == "fixture_ids" and z.fid not in ids
                    and not ({(w.get("pan_attr") or "pan").lower(),
                              (w.get("tilt_attr") or "tilt").lower()} & z.attrs)):
                _weg(plan, BEREICH_KONSOLE, objekt, q, z,
                     "das Ziel hat die Bewegungs-Kanäle dieses XY-Pads nicht")
                continue

            def holen(pfad=pfad, typ=typ, caption=caption, feld=feld):
                k = _vc_knoten(state, pfad, typ, caption)
                return k.get(feld) if k is not None else None

            def setzen(l, pfad=pfad, typ=typ, caption=caption, feld=feld):
                k = _vc_knoten(state, pfad, typ, caption)
                if k is not None:
                    k[feld] = l

            _mitglied(plan, BEREICH_KONSOLE, objekt, q, z,
                      _listen_schritt(holen, setzen, q.fid, z.fid, opt.position),
                      schon=z.fid in ids,
                      text=f"in die Geräteliste {_wo(opt.position)}")


_PLANER = {
    BEREICH_GRUPPEN: _plane_gruppen,
    BEREICH_EFFEKTE: _plane_effekte,
    BEREICH_SNAPS: _plane_snaps,
    BEREICH_CUES: _plane_cues,
    BEREICH_PALETTEN: _plane_paletten,
    BEREICH_KONSOLE: _plane_konsole,
    BEREICH_GRUNDWERTE: _plane_grundwerte,
}


# ── Nach dem Schreiben: Ansichten und Renderer nachziehen ───────────────────

def _benachrichtigen(state, bereiche: set, palette_manager=None) -> None:
    def still(fn):
        try:
            fn()
        except Exception as e:                       # noqa: BLE001
            try:
                from ..diagnose_log import melde_still
                melde_still("klonen", e, "Benachrichtigung nach dem Klonen")
            except Exception:
                pass

    if BEREICH_GRUNDWERTE in bereiche:
        still(lambda: state._rebuild_render_plan())
    if BEREICH_GRUPPEN in bereiche:
        still(lambda: state.notify_groups_changed())
    if bereiche & {BEREICH_EFFEKTE, BEREICH_SNAPS, BEREICH_CUES}:
        fm = getattr(state, "function_manager", None)
        if fm is not None:
            still(lambda: fm._notify_functions_changed())
    if BEREICH_CUES in bereiche:
        still(lambda: state._emit("cue_stack_changed", None))
    if BEREICH_PALETTEN in bereiche:
        def _pal():
            from ..engine.palette import PaletteManager
            PaletteManager._notify_palettes_changed()
        still(_pal)


# ── Sicherung und der eine Rückgängig-Schritt ───────────────────────────────

def sicherung_anlegen(show_name: str | None = None) -> str | None:
    """Den jetzigen Stand der Show als Version „vor dem Klonen" ablegen —
    über den vorhandenen Sicherungs-Mechanismus. Wirft nie; ``None`` heißt:
    es gibt keine Sicherung."""
    try:
        from . import sicherungen
        from .show_file import save_show
        return sicherungen.sichere_stand(
            save_show, show_name or sicherungen.UNBENANNT,
            sicherungen.ANLASS_VOR_KLONEN)
    except Exception:
        return None


def anwenden_mit_rueckweg(state, plan: Plan, *, davor: Callable | None = None,
                          danach: Callable | None = None) -> int:
    """Plan schreiben und als EINEN Schritt in den Rückgängig-Verlauf legen.

    ``danach(plan)`` läuft nach Anwenden, Rückgängig und Wiederholen: die
    Oberfläche zieht damit Ansichten nach, die ihren Stand selbst halten.
    ``davor()`` läuft VOR Rückgängig und Wiederholen: dort holt sie den Stand
    dieser Ansichten zuerst ab — sonst überschriebe das Nachziehen, was dort
    seit dem Klonen von Hand gebaut wurde.
    """
    def nachziehen():
        if danach is not None:
            danach(plan)

    anzahl = plan.anwenden(state)
    nachziehen()

    def zurueck():
        if davor is not None:
            davor()
        plan.zuruecknehmen(state)
        nachziehen()

    def nochmal():
        if davor is not None:
            davor()
        plan.anwenden(state)
        nachziehen()

    from ..undo import Command, get_undo_stack
    get_undo_stack().push(Command(label=plan.label, do=nochmal, undo=zurueck,
                                  redo=nochmal), execute=False)
    return anzahl
