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

Fader (Nachtrag): Ein Effekt-Fader zaehlt IMMER mit — auch ohne den Haken
„bei 0 wirklich stoppen“. Gerade dann laeuft der Effekt bei 0 unsichtbar weiter
und belegt die Geraete; der Hinweis sagt das in einem eigenen Satz
(``haltend`` in :func:`ueberschneidungen`, :func:`halte_zeilen`).

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
# Reihenfolge im Hinweis: zuerst, wogegen man VERLIERT (das muss der Bediener
# sehen), dann der Gleichstand, dann die Gewinne, zuletzt die neutralen
# Modify-Saetze.
_RANG = {DIESE_TIEFER: 0, GLEICH: 1, DIESE_HOEHER: 2, MODIFY: 3}

_AKKUSATIV = {stufen.DIMMER: "den Dimmer", stufen.FARBE: "die Farbe",
              stufen.BEWEGUNG: "die Bewegung", stufen.GOBO: "das Gobo"}
_ZAHLWORT = {1: "eine Stufe", 2: "zwei Stufen", 3: "drei Stufen", 4: "vier Stufen"}

_MAX_TIEFE = 8
MAX_AUSGESCHRIEBEN = 3
# Verlierer-Faelle stehen auch ueber MAX_AUSGESCHRIEBEN hinaus da. Erst weit
# darueber fasst die Zeile zusammen — und sagt dann ausdruecklich, dass die
# Taste gegen die uebrigen ebenfalls verliert.
MAX_VERLIERER_AUSGESCHRIEBEN = 6


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
    geraete_text: str           # „der Gruppe „Hintergrund““ / „von 4 Geräten“
    verhaeltnis: str            # GLEICH / DIESE_HOEHER / DIESE_TIEFER / MODIFY
    stufen_abstand: int | None  # Zahl der Stufen dazwischen; None bei eigener Zahl
    # Liegt der Effekt auf einem Fader OHNE „bei 0 wirklich stoppen“? Dann
    # laeuft er bei 0 weiter und belegt die Geraete.
    eigene_haelt: bool = False
    andere_haelt: bool = False

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
        """Der Hinweis zu EINER Ueberschneidung. ``subjekt``: „Taste“, „Fader“
        oder „Effekt“. Haelt ein Fader den ANDEREN Effekt bei 0 am Laufen,
        steht das als zweiter Satz dahinter; fuer den eigenen Effekt sagt es
        :func:`halte_zeilen` einmal fuer den ganzen Hinweis."""
        text = self._satz(subjekt, nenne_eigene)
        if self.andere_haelt:
            text += " " + _halte_satz(f"„{getattr(self.andere, 'name', '') or '?'}“")
        return text

    def _satz(self, subjekt: str, nenne_eigene: bool) -> str:
        gross, klein = _SUBJEKT.get(subjekt, _SUBJEKT["Taste"])
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
            elif subjekt == "Fader":
                rest = ("dieser Fader steuert einen Modify-Effekt: er rechnet "
                        "auf das fertige Bild und ersetzt nichts.")
            else:
                rest = ("diese Taste startet einen Modify-Effekt: er rechnet "
                        "auf das fertige Bild und ersetzt nichts.")
            return (f"{selbst} und {name} fassen beide {self.bausteine_text()} "
                    f"{self.geraete_text} an — {rest}")
        kopf = (f"{selbst} und {name} steuern beide {self.bausteine_text()} "
                f"{self.geraete_text} — ")
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


_SUBJEKT = {"Taste": ("Diese Taste", "diese Taste"),
            "Fader": ("Dieser Fader", "dieser Fader"),
            "Effekt": ("Dieser Effekt", "dieser Effekt")}

HALTE_SATZ_FADER = ("Dieser Fader hält den Effekt auch bei 0 am Laufen — er "
                    "belegt die Geräte dann weiter.")
HALTE_SATZ_EFFEKT = ("Ein Fader hält diesen Effekt auch bei 0 am Laufen — er "
                     "belegt die Geräte dann weiter.")


def _halte_satz(name: str, wer: str = "Ein Fader") -> str:
    """Der Satz ueber einen Effekt, den ein Fader ohne „bei 0 wirklich
    stoppen“ steuert. ``name`` steht schon in Anfuehrungszeichen."""
    return (f"{wer} hält {name} auch bei 0 am Laufen — der Effekt belegt "
            "die Geräte dann weiter.")


def halte_zeilen(treffer: Iterable["Treffer"], subjekt: str = "Taste",
                 selbst_haelt: bool | None = None) -> list[str]:
    """Die Zusatzzeilen „… haelt den Effekt auch bei 0 am Laufen“ fuer die
    EIGENEN Effekte — je Effekt einmal, nicht hinter jedem Satz wieder. Leer,
    wenn kein eigener Effekt auf einem Fader ohne „bei 0 wirklich stoppen“
    liegt.

    ``selbst_haelt`` (nur Subjekt „Fader“): ``False`` heisst, DIESER Fader
    stoppt bei 0 wirklich — den Effekt haelt dann ein ANDERER Fader, und so
    steht es da. Ohne Angabe gilt der Fader selbst als der haltende."""
    zeilen: list[str] = []
    for t in treffer:
        if not t.eigene_haelt:
            continue
        if subjekt == "Fader" and selbst_haelt is False:
            zeile = _halte_satz(f"„{getattr(t.eigene, 'name', '') or '?'}“",
                                "Ein anderer Fader")
        elif subjekt == "Fader":
            zeile = HALTE_SATZ_FADER
        elif subjekt == "Effekt":
            zeile = HALTE_SATZ_EFFEKT
        else:
            zeile = _halte_satz(f"„{getattr(t.eigene, 'name', '') or '?'}“")
        if zeile not in zeilen:
            zeilen.append(zeile)
    return zeilen


def _stufen_abstand(a: int, b: int) -> int | None:
    sa, sb = stufen.stufe_fuer_zahl(a), stufen.stufe_fuer_zahl(b)
    if sa is None or sb is None:
        return None
    return abs(stufen.STUFEN.index(sa) - stufen.STUFEN.index(sb))


def geraete_text(geraete: Iterable[int],
                 gruppen: Iterable[tuple[str, Iterable[int]]] | None = None,
                 geraete_name: Callable[[int], str | None] | None = None) -> str:
    """Die gemeinsamen Geraete in Worten, fertig fuer den Satz „… steuern
    beide den Dimmer <Text>“: ``der Gruppe „Alle PAR“``, wenn sie GENAU eine
    Gruppe bilden; bei einem einzelnen Geraet ``des Geräts „Spot 1“``; sonst
    die Zahl (``von 4 Geräten``). Namen stehen immer in Anfuehrungszeichen."""
    menge = frozenset(int(g) for g in geraete)
    passend = sorted(str(name) for name, fids in (gruppen or ())
                     if name and _als_menge(fids) == menge)
    if passend:
        return f"der Gruppe „{passend[0]}“"
    if len(menge) == 1:
        name = None
        if geraete_name is not None:
            try:
                name = geraete_name(next(iter(menge)))
            except Exception:
                name = None
        return f"des Geräts „{name}“" if name else "eines Geräts"
    return f"von {len(menge)} Geräten"


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
                      cache: dict | None = None,
                      haltend: Iterable[int] | None = None) -> list[Treffer]:
    """Mit welchen der ``andere_funktionen`` ueberschneidet sich ``funktion``?

    ``haltend``: IDs der Funktionen, die auf einem Fader OHNE „bei 0 wirklich
    stoppen“ liegen — sie laufen bei 0 weiter. Die Treffer tragen das als
    ``eigene_haelt`` / ``andere_haelt``.

    Der Aufrufer bestimmt, was „die anderen“ sind — fuer den Hinweis an einer
    Taste nur Funktionen, die selbst auf einer Taste oder einem Fader liegen.
    Sortiert: zuerst „die andere gewinnt“ (dagegen verliert ``funktion``),
    dann gleiche Stufe, dann „diese gewinnt“, zuletzt die neutralen
    Modify-Saetze; darin nach Name.
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
    haltend = _als_menge(haltend)
    eigene_haelt = _id_in(eigene_id, haltend)
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
                            else _stufen_abstand(eigene_zahl, ihre_zahl)),
            eigene_haelt=eigene_haelt, andere_haelt=_id_in(aid, haltend)))
    treffer.sort(key=sortier_schluessel)
    return treffer


def _id_in(fid, menge: frozenset) -> bool:
    try:
        return int(fid) in menge
    except (TypeError, ValueError):
        return False


def sortier_schluessel(t: Treffer):
    """Verlierer-Faelle zuerst, dann Gleichstand, Gewinne, Modify; darin nach
    dem Namen des anderen Effekts."""
    return (_RANG[t.verhaeltnis], str(getattr(t.andere, "name", "")).lower(),
            str(getattr(t.eigene, "name", "")).lower())


def _weitere(n: int) -> str:
    return ("1 weitere Überschneidung" if n == 1
            else f"{n} weitere Überschneidungen")


def _rest_zeile(rest: list, subjekt: str) -> str:
    """Die Zusammenfassung der nicht ausgeschriebenen Treffer. Sie sagt immer,
    wie es um die uebrigen steht — nie nur „und n weitere“."""
    klein = _SUBJEKT.get(subjekt, _SUBJEKT["Taste"])[1]
    zahl = {v: sum(1 for t in rest if t.verhaeltnis == v) for v in _RANG}
    teile = []
    if zahl[DIESE_TIEFER]:
        teile.append(f"gegen {zahl[DIESE_TIEFER]} verliert {klein}")
    if zahl[GLEICH]:
        teile.append(f"bei {zahl[GLEICH]} entscheidet, wer zuletzt gestartet wurde")
    if zahl[DIESE_HOEHER]:
        teile.append(f"gegen {zahl[DIESE_HOEHER]} gewinnt {klein}")
    if zahl[MODIFY]:
        teile.append(f"{zahl[MODIFY]} mit Modify-Effekt, dort wird nichts ersetzt"
                     if zahl[MODIFY] > 1 else
                     "1 mit Modify-Effekt, dort wird nichts ersetzt")
    return f"… und {_weitere(len(rest))}: " + "; ".join(teile) + "."


def hinweis_zeilen(treffer: Iterable[Treffer], subjekt: str = "Taste",
                   nenne_eigene: bool = False,
                   hoechstens: int | None = MAX_AUSGESCHRIEBEN,
                   selbst_haelt: bool | None = None) -> list[str]:
    """Die Saetze fuer die Hinweiszeile. Leer = kein Hinweis.

    Reihenfolge: zuerst alle, gegen die man VERLIERT, dann Gleichstand, dann
    die Gewinne, zuletzt Modify; darin nach Name. Ausgeschrieben werden
    ``hoechstens`` Saetze — die Verlierer-Faelle aber auch darueber hinaus
    (bis ``MAX_VERLIERER_AUSGESCHRIEBEN``): der Effekt, gegen den die Taste
    verliert, verschwindet nie hinter „… und n weitere“. Der Rest steht in
    einer Zeile, die sagt, wie viele davon gewinnen, verlieren oder gleich
    liegen. ``hoechstens=None`` schreibt alles aus (Tooltip).

    Liegt ein eigener Effekt auf einem Fader ohne „bei 0 wirklich stoppen“,
    steht das als letzte Zeile (:func:`halte_zeilen`, dort auch
    ``selbst_haelt``)."""
    treffer = sorted(treffer, key=sortier_schluessel)
    halten = halte_zeilen(treffer, subjekt, selbst_haelt)
    if hoechstens is None:
        return [t.satz(subjekt, nenne_eigene) for t in treffer] + halten
    verlierer = sum(1 for t in treffer if t.verhaeltnis == DIESE_TIEFER)
    anzahl = max(int(hoechstens), min(verlierer, MAX_VERLIERER_AUSGESCHRIEBEN))
    zeilen = [t.satz(subjekt, nenne_eigene) for t in treffer[:anzahl]]
    rest = treffer[anzahl:]
    if rest:
        zeilen.append(_rest_zeile(rest, subjekt))
    return zeilen + halten
