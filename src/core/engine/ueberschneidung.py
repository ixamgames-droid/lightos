"""ENG-39: Ueberschneidungs-Hinweis — fassen zwei Effekte dasselbe an?

Zwei Funktionen ueberschneiden sich, wenn sie mindestens EIN gemeinsames Geraet
haben UND dort denselben Baustein schreiben (Dimmer, Farbe, Bewegung oder Gobo).
Dieselbe Geraeteart genuegt nicht, und Farbe gegen Dimmer auf denselben Lampen
ist KEINE Ueberschneidung: das sind getrennte Kanaele.

Das Modul sagt nur, WER GEWINNT — nach der Regel, die der Engine-Merge ohnehin
anwendet (``FunctionManager.tick``): die hoehere Stufe gewinnt, bei gleicher
Stufe die zuletzt gestartete Funktion. Es rechnet nichts am Bild und aendert
nichts an der Show.

Gegen Fehlalarme:

- Bausteine werden JE GERAET bestimmt, wo die Funktion das hergibt (Szene,
  Sequenz). Eine Szene mit Dimmer auf Lampe 1 und Farbe auf Lampe 2 kollidiert
  nicht mit einem Farb-Effekt auf Lampe 1.
- Was sich nicht sicher ablesen laesst (``Bausteine.unbekannt``, Skripte),
  meldet nichts. „Sonstiges“ (Shutter, Zoom, …) ist zu grob fuer eine Aussage
  und zaehlt ebenfalls nicht.
- Ein Modify-Effekt (ENG-37) ersetzt nichts — er rechnet auf das fertige Bild.
  Dafuer gibt es nur einen neutralen Satz.

Die Baustein-Erkennung selbst stammt aus ``stufen.py`` (ENG-35) — hier wird sie
nur je Geraet aufgeteilt. Leaf-Modul ohne Qt-/DB-Importe.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from src.core.engine import stufen

# Nur diese vier Bausteine tragen eine Aussage („Sonstiges“ nicht).
_ZAEHLENDE = frozenset({stufen.DIMMER, stufen.FARBE, stufen.BEWEGUNG, stufen.GOBO})

GLEICH, DIESE_HOEHER, DIESE_TIEFER, MODIFY = "gleich", "diese_hoeher", "diese_tiefer", "modify"
_RANG = {GLEICH: 0, DIESE_TIEFER: 1, DIESE_HOEHER: 2, MODIFY: 3}

_AKKUSATIV = {stufen.DIMMER: "den Dimmer", stufen.FARBE: "die Farbe",
              stufen.BEWEGUNG: "die Bewegung", stufen.GOBO: "das Gobo"}
_ZAHLWORT = {1: "eine Stufe", 2: "zwei Stufen", 3: "drei Stufen", 4: "vier Stufen"}

_MAX_TIEFE = 8
MAX_AUSGESCHRIEBEN = 3


def _typ(funktion) -> str:
    return getattr(getattr(funktion, "function_type", None), "value", "")


def kinder_ids(funktion) -> list | None:
    """IDs der Mitglieder eines Behaelters (Chaser, Sammlung, Show) —
    ``None``, wenn ``funktion`` kein Behaelter ist."""
    typ = _typ(funktion)
    if typ == "Chaser":
        return [getattr(s, "function_id", None)
                for s in getattr(funktion, "steps", None) or ()]
    if typ == "Collection":
        return list(getattr(funktion, "function_ids", None) or ())
    if typ == "Show":
        return [getattr(sf, "function_id", None)
                for spur in getattr(funktion, "tracks", None) or ()
                for sf in getattr(spur, "show_functions", None) or ()]
    return None


def geraete_bausteine(funktion,
                      aufloesen: Callable[[int], object | None] | None = None,
                      geraete_von: Callable[[object], Iterable[int]] | None = None,
                      kanal_attribut: Callable[[int, int], str | None] | None = None,
                      cache: dict | None = None,
                      _tiefe: int = 0) -> dict[int, frozenset]:
    """``{Geraete-ID: Bausteine}`` — was ``funktion`` SICHER an welchem Geraet
    schreibt. Nur Dimmer/Farbe/Bewegung/Gobo; Unbestimmbares fehlt.

    ``aufloesen``: Funktions-ID -> Funktion (fuer Behaelter).
    ``geraete_von``: Funktion -> ihre Geraete-IDs (in der App
    ``FunctionManager.affected_fids``). Ohne die Auskunft meldet ein Effekt,
    der seine Geraete nicht selbst je Wert nennt, nichts.
    ``kanal_attribut``: (Geraete-ID, Kanal-Nr.) -> Attribut, fuer Szenen.
    ``cache``: optionales Woerterbuch ``id(funktion) -> Ergebnis`` fuer einen
    Durchlauf ueber viele Funktionen.
    """
    f = funktion
    if f is None or _tiefe > _MAX_TIEFE:
        return {}
    schluessel = id(f)
    if cache is not None and schluessel in cache:
        return cache[schluessel]
    aus = _geraete_bausteine(f, aufloesen, geraete_von, kanal_attribut, cache,
                             _tiefe)
    if cache is not None and _tiefe == 0:
        cache[schluessel] = aus
    return aus


def _geraete_bausteine(f, aufloesen, geraete_von, kanal_attribut, cache,
                       tiefe) -> dict[int, frozenset]:
    if getattr(f, "is_script", False):
        return {}
    typ = _typ(f)
    aus: dict[int, set] = {}

    kinder = kinder_ids(f)
    if kinder is not None:                      # Behaelter: es zaehlt das Ganze
        if aufloesen is None:
            return {}
        for kid in kinder:
            try:
                kind = aufloesen(int(kid))
            except (TypeError, ValueError):
                continue
            for fid, menge in geraete_bausteine(
                    kind, aufloesen, geraete_von, kanal_attribut, None,
                    tiefe + 1).items():
                aus.setdefault(fid, set()).update(menge)
        return {fid: frozenset(m) for fid, m in aus.items()}

    eben_effekt = (getattr(f, "is_layered_effect", False)
                   or getattr(f, "is_carousel", False))

    if typ == "Scene" and not eben_effekt:
        werte = getattr(f, "values", None)
        if not isinstance(werte, list) or kanal_attribut is None:
            return {}
        for sv in werte:
            try:
                fid = int(getattr(sv, "fixture_id"))
                attr = kanal_attribut(fid, int(getattr(sv, "channel")))
            except Exception:
                continue
            if not attr:
                continue
            b = stufen.baustein_fuer_attribut(attr)
            if b in _ZAEHLENDE:
                aus.setdefault(fid, set()).add(b)
        return {fid: frozenset(m) for fid, m in aus.items()}

    if typ == "Sequence" and not eben_effekt:
        for schritt in getattr(f, "steps", None) or ():
            werte = getattr(schritt, "values", None)
            if not isinstance(werte, dict):
                continue
            for fid, attrs in werte.items():
                if not isinstance(attrs, dict):
                    continue
                try:
                    fidi = int(fid)
                except (TypeError, ValueError):
                    continue
                for attr in attrs:
                    b = stufen.baustein_fuer_attribut(str(attr))
                    if b in _ZAEHLENDE:
                        aus.setdefault(fidi, set()).add(b)
        return {fid: frozenset(m) for fid, m in aus.items()}

    # Alles andere (Matrix, Bewegung, Carousel, Ebenen-Effekt, Kanal-Kopplung):
    # ein Baustein-Satz fuer alle Geraete der Funktion.
    if geraete_von is None:
        return {}
    menge = frozenset(stufen.bausteine_von(f, aufloesen, kanal_attribut).menge
                      & _ZAEHLENDE)
    if not menge:
        return {}
    try:
        geraete = list(geraete_von(f) or ())
    except Exception:
        return {}
    ergebnis: dict[int, frozenset] = {}
    for fid in geraete:
        try:
            ergebnis[int(fid)] = menge
        except (TypeError, ValueError):
            continue
    return ergebnis


@dataclass(frozen=True)
class Treffer:
    """Eine Ueberschneidung zwischen ``eigene`` und ``andere``."""
    eigene: object
    andere: object
    bausteine: tuple            # in der Reihenfolge Dimmer, Farbe, Bewegung, Gobo
    geraete: frozenset          # die gemeinsamen Geraete, an denen es kollidiert
    geraete_text: str           # „Hintergrund“ / „4 Geräten“ / „„Spot 1““
    verhaeltnis: str            # GLEICH / DIESE_HOEHER / DIESE_TIEFER / MODIFY
    stufen_abstand: int | None  # Zahl der Stufen dazwischen; None bei eigener Zahl

    @property
    def gewinner(self):
        """Wer nach den Regeln gewinnt — ``None`` bei gleicher Stufe (dann
        entscheidet der Start) und bei Modify (dort ersetzt niemand)."""
        if self.verhaeltnis == DIESE_HOEHER:
            return self.eigene
        if self.verhaeltnis == DIESE_TIEFER:
            return self.andere
        return None

    def bausteine_text(self) -> str:
        teile = [_AKKUSATIV[b] for b in self.bausteine]
        if len(teile) <= 1:
            return "".join(teile)
        return ", ".join(teile[:-1]) + " und " + teile[-1]

    def satz(self, subjekt: str = "Taste", nenne_eigene: bool = False) -> str:
        """Der Hinweis in einem Satz. ``subjekt``: „Taste“ oder „Effekt“."""
        gross, klein = (("Dieser Effekt", "dieser Effekt") if subjekt == "Effekt"
                        else ("Diese Taste", "diese Taste"))
        name = f"„{getattr(self.andere, 'name', '') or '?'}“"
        selbst = gross
        if nenne_eigene:
            selbst += f" („{getattr(self.eigene, 'name', '') or '?'}“)"
        if self.verhaeltnis == MODIFY:
            ihr_modify = stufen.ist_modify(self.andere)
            if ihr_modify and stufen.ist_modify(self.eigene):
                rest = ("beide sind Modify-Effekte: sie rechnen nacheinander "
                        "auf das fertige Bild und ersetzen nichts.")
            elif ihr_modify:
                rest = (f"{name} ist ein Modify-Effekt: er rechnet auf das "
                        "fertige Bild und ersetzt nichts.")
            elif subjekt == "Effekt":
                rest = ("dieser Effekt ist ein Modify-Effekt: er rechnet auf "
                        "das fertige Bild und ersetzt nichts.")
            else:
                rest = ("diese Taste startet einen Modify-Effekt: er rechnet "
                        "auf das fertige Bild und ersetzt nichts.")
            return (f"{selbst} und {name} fassen beide {self.bausteine_text()} "
                    f"von {self.geraete_text} an — {rest}")
        kopf = (f"{selbst} und {name} steuern beide {self.bausteine_text()} "
                f"von {self.geraete_text} — ")
        if self.verhaeltnis == GLEICH:
            return kopf + "gleiche Stufe, es gewinnt, wer zuletzt gestartet wurde."
        oben, unten = ((self.eigene, self.andere)
                       if self.verhaeltnis == DIESE_HOEHER
                       else (self.andere, self.eigene))
        if self.stufen_abstand in _ZAHLWORT:
            abstand = f"{_ZAHLWORT[self.stufen_abstand]} höher"
        else:
            abstand = ("höher ("
                       f"{stufen.stufen_name(getattr(oben, 'priority', 0))} über "
                       f"{stufen.stufen_name(getattr(unten, 'priority', 0))})")
        wer = klein if self.verhaeltnis == DIESE_HOEHER else name
        return kopf + f"{wer} liegt {abstand} und gewinnt."


def _stufen_abstand(a: int, b: int) -> int | None:
    sa, sb = stufen.stufe_fuer_zahl(a), stufen.stufe_fuer_zahl(b)
    if sa is None or sb is None:
        return None
    return abs(stufen.STUFEN.index(sa) - stufen.STUFEN.index(sb))


def geraete_text(geraete: Iterable[int],
                 gruppen: Iterable[tuple[str, Iterable[int]]] | None = None,
                 geraete_name: Callable[[int], str | None] | None = None) -> str:
    """Die gemeinsamen Geraete in Worten (fuer „… von <Text>“): der
    Gruppenname, wenn sie GENAU eine Gruppe bilden; bei einem einzelnen Geraet
    dessen Name; sonst die Zahl."""
    menge = frozenset(int(g) for g in geraete)
    passend = sorted(str(name) for name, fids in (gruppen or ())
                     if name and _als_menge(fids) == menge)
    if passend:
        return passend[0]
    if len(menge) == 1:
        name = None
        if geraete_name is not None:
            try:
                name = geraete_name(next(iter(menge)))
            except Exception:
                name = None
        return f"„{name}“" if name else "1 Gerät"
    return f"{len(menge)} Geräten"


def _als_menge(fids) -> frozenset:
    aus = set()
    for f in fids or ():
        try:
            aus.add(int(f))
        except (TypeError, ValueError):
            continue
    return frozenset(aus)


def ueberschneidungen(funktion, andere_funktionen: Iterable, *,
                      aufloesen: Callable[[int], object | None] | None = None,
                      geraete_von: Callable[[object], Iterable[int]] | None = None,
                      kanal_attribut: Callable[[int, int], str | None] | None = None,
                      gruppen: Iterable[tuple[str, Iterable[int]]] | None = None,
                      geraete_name: Callable[[int], str | None] | None = None,
                      cache: dict | None = None) -> list[Treffer]:
    """Mit welchen der ``andere_funktionen`` ueberschneidet sich ``funktion``?

    Der Aufrufer bestimmt, was „die anderen“ sind — fuer den Hinweis an einer
    Taste nur Funktionen, die selbst auf einer Taste oder einem Fader liegen.
    Sortiert: zuerst gleiche Stufe, dann „die andere gewinnt“, dann „diese
    gewinnt“, zuletzt die neutralen Modify-Saetze; darin nach Name.
    """
    if funktion is None:
        return []
    if cache is None:
        cache = {}
    eigene = geraete_bausteine(funktion, aufloesen, geraete_von, kanal_attribut,
                               cache)
    if not eigene:
        return []
    gruppen = list(gruppen or ())
    eigene_id = getattr(funktion, "id", None)
    eigene_zahl = stufen.zahl_von(getattr(funktion, "priority", 0))
    eigene_modify = stufen.ist_modify(funktion)
    gesehen: set = set()
    treffer: list[Treffer] = []
    for andere in andere_funktionen or ():
        if andere is None or andere is funktion:
            continue
        aid = getattr(andere, "id", None)
        if aid is not None and (aid == eigene_id or aid in gesehen):
            continue
        gesehen.add(aid)
        ihre = geraete_bausteine(andere, aufloesen, geraete_von, kanal_attribut,
                                 cache)
        if not ihre:
            continue
        gemeinsam = eigene.keys() & ihre.keys()
        if not gemeinsam:
            continue
        geraete: set = set()
        bausteine: set = set()
        for fid in gemeinsam:
            schnitt = eigene[fid] & ihre[fid]
            if schnitt:
                geraete.add(fid)
                bausteine |= schnitt
        if not geraete:
            continue                            # z. B. Farbe gegen Dimmer
        ihre_zahl = stufen.zahl_von(getattr(andere, "priority", 0))
        if eigene_modify or stufen.ist_modify(andere):
            verhaeltnis = MODIFY
        elif eigene_zahl == ihre_zahl:
            verhaeltnis = GLEICH
        elif eigene_zahl > ihre_zahl:
            verhaeltnis = DIESE_HOEHER
        else:
            verhaeltnis = DIESE_TIEFER
        treffer.append(Treffer(
            eigene=funktion, andere=andere,
            bausteine=tuple(b for b in stufen.BAUSTEIN_REIHENFOLGE
                            if b in bausteine),
            geraete=frozenset(geraete),
            geraete_text=geraete_text(geraete, gruppen, geraete_name),
            verhaeltnis=verhaeltnis,
            stufen_abstand=(0 if eigene_zahl == ihre_zahl
                            else _stufen_abstand(eigene_zahl, ihre_zahl))))
    treffer.sort(key=lambda t: (_RANG[t.verhaeltnis],
                                str(getattr(t.andere, "name", "")).lower()))
    return treffer


def hinweis_zeilen(treffer: Iterable[Treffer], subjekt: str = "Taste",
                   nenne_eigene: bool = False,
                   hoechstens: int = MAX_AUSGESCHRIEBEN) -> list[str]:
    """Die Saetze fuer die Hinweiszeile: hoechstens ``hoechstens``
    ausgeschrieben, danach „… und n weitere“. Leer = kein Hinweis."""
    treffer = list(treffer)
    zeilen = [t.satz(subjekt, nenne_eigene) for t in treffer[:hoechstens]]
    rest = len(treffer) - len(zeilen)
    if rest > 0:
        zeilen.append(f"… und {rest} weitere")
    return zeilen
