"""VIZ-67 (Teil 2): DXF-Dateien (ASCII) als Buehnenobjekt importieren.

Eigener kleiner Parser ohne neue Abhaengigkeit. Eine DXF-Datei ist eine
Folge von Paaren aus Gruppencode (Zahl) und Wert, je eine Zeile. Gelesen
werden der Abschnitt HEADER (nur ``$INSUNITS``, als Vorschlag fuer die
Einheiten-Abfrage), BLOCKS (fuer INSERT) und ENTITIES.

Unterstuetzt (alles andere wird gezaehlt und als Hinweis gemeldet):

* Flaechen: ``3DFACE`` (Dreieck/Viereck), ``POLYLINE`` als Polyface-Netz
  (Flag 64, Flaechen ueber die VERTEX-Indizes 71-74) und als Polygon-Netz
  (Flag 16, M x N), ``MESH`` (ohne Unterteilung).
* Linien (z. B. ein Hallenplan): ``LINE``, ``LWPOLYLINE``, ``POLYLINE``
  (2D/3D), ``CIRCLE``, ``ARC`` (als Strecken angenaehert). Sie reisen als
  Liniengeometrie im Modell mit oder werden auf Wunsch zu duennen Waenden
  mit einer Hoehe hochgezogen (:func:`linien_zu_waenden`).
* ``INSERT`` setzt Bloecke ein (Verschieben, Strecken, Drehen um Z,
  verschachtelt bis ``_MAX_TIEFE``); Reihen-Einfuegungen (MINSERT) nur das
  erste Exemplar.

Binaer-DXF wird mit einer verstaendlichen Meldung abgelehnt. Kaputte Dateien
enden in :class:`ModellImportFehler` — nie in einer rohen Ausnahme.
Koordinaten bleiben in Datei-Einheiten und Z oben; Umrechnen, Drehen
(Y oben) und Zentrieren macht ``modell_import._normieren``.
"""
from __future__ import annotations

import hashlib
import math
from array import array
from collections import Counter
from dataclasses import dataclass, field

from .modell_import import (MAX_DREIECKE, MAX_LINIEN, ModellImportFehler,
                            _Sammler, _zahl, _zu_viele)

_BINAER_KENNUNG = b"AutoCAD Binary DXF"
_MAX_TIEFE = 8            # verschachtelte Bloecke
_KREIS_SEGMENTE = 32      # Strecken je Vollkreis
# Arbeitsgrenze: Objekte inkl. aller Block-Einsetzungen. Gleiche Strecken werden
# zusammengelegt, die Linien-Grenze greift bei sich vervielfachenden Bloecken
# (Block setzt sich zehnmal selbst ein -> 10^8 Aufrufe) also nie.
_MAX_OBJEKTE = 1_000_000

#: $INSUNITS -> Einheit in ``modell_import.EINHEITEN`` (Rest: kein Vorschlag).
INSUNITS = {1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m"}

_LINIEN_TYPEN = ("LINE", "LWPOLYLINE", "CIRCLE", "ARC")


@dataclass
class DxfRoh:
    """Geometrie in Datei-Einheiten, Z oben (noch nicht zentriert)."""

    pos: array
    idx: array
    lin: array
    einheit: str | None = None
    hinweise: tuple = ()

    @property
    def dreiecke(self) -> int:
        return len(self.idx) // 3

    @property
    def linien(self) -> int:
        return len(self.lin) // 2


@dataclass
class _Obj:
    typ: str
    paare: list
    zeile: int
    kinder: list = field(default_factory=list)   # VERTEX einer POLYLINE

    def erster(self) -> dict:
        d = {}
        for c, w in self.paare:
            d.setdefault(c, w)
        return d


# ── Paare lesen und gliedern ─────────────────────────────────────────────────

def _paare(text: str):
    # Nur echte Zeilenumbrueche trennen — ``splitlines`` zaehlt auch U+2028,
    # \x1c, \x0c … als Umbruch und verschoebe dann alle folgenden Paare.
    zeilen = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if len(zeilen) % 2:
        zeilen = zeilen[:-1]   # angehaengte Leerzeile / abgeschnittenes Ende
    for i in range(0, len(zeilen), 2):
        roh = zeilen[i].strip()
        try:
            code = int(roh)
        except ValueError:
            raise ModellImportFehler(
                f"Kaputte DXF-Datei (Zeile {i + 1}): Gruppencode erwartet, "
                f"gefunden {roh[:20]!r}.") from None
        yield code, zeilen[i + 1].strip(), i + 1


def _ganz(wert: str) -> int:
    try:
        return int(float(wert))
    except ValueError:
        raise ModellImportFehler(f"Ungültige Zahl in der Datei: {wert[:30]!r}") from None


def _gliedern(text: str):
    """-> (einheit|None, entities, bloecke{name: (basis, entities)})."""
    einheit = None
    entities: list = []
    bloecke: dict = {}
    abschnitt = None
    name_folgt = False
    variable = None
    obj = None             # gerade gelesenes Objekt
    ziel = None            # Liste, in die fertige Objekte wandern
    polylinie = None       # offene POLYLINE (sammelt VERTEX)
    block = None           # offener BLOCK: [name, basis-obj, liste]

    def abschliessen():
        nonlocal obj, polylinie
        if obj is None:
            return
        if obj.typ == "VERTEX" and polylinie is not None:
            polylinie.kinder.append(obj)
        elif obj.typ == "BLOCK":
            pass   # Kopf des Blocks, s. unten
        elif obj.typ in ("SEQEND", "ENDBLK", "ATTRIB"):
            pass
        elif ziel is not None:
            ziel.append(obj)
        if obj.typ != "VERTEX":
            polylinie = obj if obj.typ == "POLYLINE" else None
        obj = None

    for code, wert, zeile in _paare(text):
        if code == 0:
            typ = wert.upper()
            abschliessen()
            if typ == "SECTION":
                name_folgt = True
                continue
            if typ in ("ENDSEC", "EOF"):
                if block is not None:   # ENDBLK fehlt: Block trotzdem behalten
                    bloecke[block[0]] = (block[1], block[2])
                    block = None
                abschnitt, ziel, polylinie = None, None, None
                if typ == "EOF":
                    break
                continue
            if abschnitt == "BLOCKS":
                if typ == "BLOCK":
                    obj = _Obj(typ, [], zeile)
                    block = [None, obj, []]
                    ziel = block[2]
                    continue
                if typ == "ENDBLK":
                    if block is not None:
                        bloecke[block[0] or ""] = (block[1], block[2])
                    block, ziel, polylinie = None, None, None
                    continue
            if abschnitt in ("ENTITIES", "BLOCKS"):
                obj = _Obj(typ, [], zeile)
            continue
        if name_folgt and code == 2:
            abschnitt = wert.upper()
            name_folgt = False
            ziel = entities if abschnitt == "ENTITIES" else None
            continue
        if abschnitt == "HEADER":
            if code == 9:
                variable = wert.upper()
            elif code == 70 and variable == "$INSUNITS":
                einheit = INSUNITS.get(_ganz(wert))
            continue
        if obj is not None:
            obj.paare.append((code, wert))
            if obj.typ == "BLOCK" and block is not None and code == 2 and block[0] is None:
                block[0] = wert
    abschliessen()
    if block is not None:
        bloecke[block[0] or ""] = (block[1], block[2])
    return einheit, entities, bloecke


# ── Geometrie ───────────────────────────────────────────────────────────────

def _kreuz(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(v):
    laenge = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if laenge < 1e-12:
        return None
    return (v[0] / laenge, v[1] / laenge, v[2] / laenge)


def _ocs(d: dict):
    """Objekt-Koordinatensystem (Gruppencodes 210/220/230, „Arbitrary Axis“).
    None = Standard (0, 0, 1), dann sind OCS und Weltkoordinaten gleich."""
    n = (_zahl(d.get(210, "0")), _zahl(d.get(220, "0")), _zahl(d.get(230, "1")))
    az = _norm(n)
    if az is None or (abs(az[0]) < 1e-12 and abs(az[1]) < 1e-12 and az[2] > 0):
        return None
    if abs(az[0]) < 1 / 64 and abs(az[1]) < 1 / 64:
        ax = _norm(_kreuz((0.0, 1.0, 0.0), az))
    else:
        ax = _norm(_kreuz((0.0, 0.0, 1.0), az))
    ay = _norm(_kreuz(az, ax))

    def nach_welt(p):
        return tuple(p[0] * ax[k] + p[1] * ay[k] + p[2] * az[k] for k in range(3))
    return nach_welt


def _punkt(d: dict, basis: int):
    return (_zahl(d.get(basis, "0")), _zahl(d.get(basis + 10, "0")),
            _zahl(d.get(basis + 20, "0")))


class _Geo:
    def __init__(self):
        self.s = _Sammler()
        self.lin = array("I")
        self._strecken: set = set()   # gleiche Strecke nur einmal

    def dreieck(self, a, b, c):
        if a == b or b == c or a == c:
            return
        self.s.dreieck(a, b, c)
        if len(self.s.idx) > 3 * MAX_DREIECKE:
            raise _zu_viele(len(self.s.idx) // 3)

    def viereck(self, a, b, c, d):
        self.dreieck(a, b, c)
        self.dreieck(a, c, d)

    def linie(self, a, b):
        if a == b:
            return
        i, j = self.s.punkt(*a), self.s.punkt(*b)
        schluessel = (i, j) if i < j else (j, i)
        if schluessel in self._strecken:
            return
        self._strecken.add(schluessel)
        self.lin.extend((i, j))
        if len(self.lin) > 2 * MAX_LINIEN:
            raise ModellImportFehler(
                f"Die Zeichnung hat mehr als {MAX_LINIEN:,} Linien.".replace(",", ".")
                + " Bitte im CAD-Programm vereinfachen (z. B. Beschriftung, Schraffuren "
                "und Möblierung ausblenden).")

    def zug(self, punkte, geschlossen):
        for i in range(len(punkte) - 1):
            self.linie(punkte[i], punkte[i + 1])
        if geschlossen and len(punkte) > 2:
            self.linie(punkte[-1], punkte[0])


class _Kontext:
    def __init__(self, bloecke):
        self.bloecke = bloecke
        self.ignoriert = Counter()
        self.boegen = False
        self.fehlende_bloecke = set()
        self.zu_tief = False
        self.reihen = False
        self.objekte = 0


def _lwpolyline(o: _Obj, tf, geo: _Geo, ctx: _Kontext):
    d = o.erster()
    hoehe = _zahl(d.get(38, "0"))
    ocs = _ocs(d)
    punkte = []
    x = None
    for c, w in o.paare:
        if c == 10:
            x = _zahl(w)
        elif c == 20 and x is not None:
            punkte.append((x, _zahl(w), hoehe))
            x = None
        elif c == 42 and abs(_zahl(w)) > 1e-12:
            ctx.boegen = True
    if ocs:
        punkte = [ocs(p) for p in punkte]
    geo.zug([tf(p) for p in punkte], bool(_ganz(d.get(70, "0")) & 1))


def _polylinie(o: _Obj, tf, geo: _Geo, ctx: _Kontext):
    d = o.erster()
    flags = _ganz(d.get(70, "0"))
    ecken = [(v.erster(), v) for v in o.kinder]
    if flags & 64:   # Polyface-Netz
        punkte, flaechen = [], []
        for vd, _v in ecken:
            vf = _ganz(vd.get(70, "0"))
            if vf & 128 and not vf & 64:
                flaechen.append([abs(_ganz(vd.get(k, "0"))) for k in (71, 72, 73, 74)])
            else:
                punkte.append(tf(_punkt(vd, 10)))
        for f in flaechen:
            idx = [i for i in f if i != 0]
            if any(i > len(punkte) for i in idx):
                raise ModellImportFehler(
                    f"Kaputte DXF-Datei (Zeile {o.zeile}): eine Fläche verweist auf "
                    "einen Eckpunkt, den es nicht gibt.")
            if len(idx) >= 3:
                p = [punkte[i - 1] for i in idx]
                geo.dreieck(p[0], p[1], p[2])
                if len(p) == 4:
                    geo.dreieck(p[0], p[2], p[3])
        return
    if flags & 16:   # Polygon-Netz M x N
        m, n = _ganz(d.get(71, "0")), _ganz(d.get(72, "0"))
        punkte = [tf(_punkt(vd, 10)) for vd, _v in ecken]
        if m < 2 or n < 2 or m * n > len(punkte):
            raise ModellImportFehler(
                f"Kaputte DXF-Datei (Zeile {o.zeile}): das Polygon-Netz hat zu wenige Eckpunkte.")
        if (m - 1) * (n - 1) * 2 > MAX_DREIECKE:
            raise _zu_viele((m - 1) * (n - 1) * 2)
        mi = m if flags & 1 else m - 1
        ni = n if flags & 32 else n - 1
        for i in range(mi):
            for j in range(ni):
                i2, j2 = (i + 1) % m, (j + 1) % n
                geo.viereck(punkte[i * n + j], punkte[i2 * n + j],
                            punkte[i2 * n + j2], punkte[i * n + j2])
        return
    # 2D-/3D-Polylinie
    ist_3d = bool(flags & 8)
    ocs = None if ist_3d else _ocs(d)
    hoehe = _zahl(d.get(30, "0"))
    punkte = []
    for vd, _v in ecken:
        if _ganz(vd.get(70, "0")) & 16:   # Spline-Stuetzpunkt, keine Ecke
            continue
        if abs(_zahl(vd.get(42, "0"))) > 1e-12:
            ctx.boegen = True
        p = _punkt(vd, 10)
        if not ist_3d:
            p = (p[0], p[1], hoehe)
            if ocs:
                p = ocs(p)
        punkte.append(tf(p))
    geo.zug(punkte, bool(flags & 1))


def _mesh(o: _Obj, tf, geo: _Geo):
    punkte, liste = [], []
    rest_punkte = rest_liste = 0
    x = y = None
    for c, w in o.paare:
        if c == 92 and not punkte and not rest_punkte:
            rest_punkte = _ganz(w)
        elif rest_punkte and c in (10, 20, 30):
            if c == 10:
                x = _zahl(w)
            elif c == 20:
                y = _zahl(w)
            elif x is not None and y is not None:
                punkte.append(tf((x, y, _zahl(w))))
                x = y = None
                rest_punkte -= 1
        elif c == 93 and not liste and not rest_liste:
            rest_liste = _ganz(w)
        elif rest_liste and c == 90:
            liste.append(_ganz(w))
            rest_liste -= 1
    i = 0
    while i < len(liste):
        k = liste[i]
        ecken = liste[i + 1:i + 1 + k]
        i += 1 + k
        if k < 0 or len(ecken) < k or any(e < 0 or e >= len(punkte) for e in ecken):
            raise ModellImportFehler(
                f"Kaputte DXF-Datei (Zeile {o.zeile}): das MESH verweist auf einen "
                "Eckpunkt, den es nicht gibt.")
        for j in range(1, k - 1):
            geo.dreieck(punkte[ecken[0]], punkte[ecken[j]], punkte[ecken[j + 1]])


def _bogen(o: _Obj, tf, geo: _Geo, voll: bool):
    d = o.erster()
    mx, my, mz = _punkt(d, 10)
    r = _zahl(d.get(40, "0"))
    if r <= 0:
        return
    if voll:
        start, winkel = 0.0, 2 * math.pi
    else:
        start = math.radians(_zahl(d.get(50, "0")))
        ende = math.radians(_zahl(d.get(51, "360")))
        winkel = (ende - start) % (2 * math.pi) or 2 * math.pi
    n = max(2, math.ceil(_KREIS_SEGMENTE * winkel / (2 * math.pi)))
    ocs = _ocs(d)
    punkte = []
    for k in range(n + 1):
        a = start + winkel * k / n
        p = (mx + r * math.cos(a), my + r * math.sin(a), mz)
        punkte.append(tf(ocs(p) if ocs else p))
    geo.zug(punkte, False)


def _insert(o: _Obj, tf, geo: _Geo, ctx: _Kontext, tiefe: int):
    d = o.erster()
    name = d.get(2, "")
    if name not in ctx.bloecke:
        ctx.fehlende_bloecke.add(name)
        return
    if tiefe >= _MAX_TIEFE:
        ctx.zu_tief = True
        return
    if _ganz(d.get(70, "1")) > 1 or _ganz(d.get(71, "1")) > 1:
        ctx.reihen = True
    kopf, inhalt = ctx.bloecke[name]
    basis = _punkt(kopf.erster(), 10)
    ein = _punkt(d, 10)
    sx, sy, sz = (_zahl(d.get(41, "1")), _zahl(d.get(42, "1")), _zahl(d.get(43, "1")))
    rot = math.radians(_zahl(d.get(50, "0")))
    cos_r, sin_r = math.cos(rot), math.sin(rot)
    ocs = _ocs(d)

    def tf_block(p):
        x, y, z = ((p[0] - basis[0]) * sx, (p[1] - basis[1]) * sy, (p[2] - basis[2]) * sz)
        x, y = x * cos_r - y * sin_r, x * sin_r + y * cos_r
        q = (x + ein[0], y + ein[1], z + ein[2])
        return tf(ocs(q) if ocs else q)

    for kind in inhalt:
        _objekt(kind, tf_block, geo, ctx, tiefe + 1)


def _objekt(o: _Obj, tf, geo: _Geo, ctx: _Kontext, tiefe: int = 0):
    ctx.objekte += 1
    if ctx.objekte > _MAX_OBJEKTE:
        raise ModellImportFehler(
            f"Die Zeichnung setzt zu viele Blöcke ein (mehr als "
            f"{_MAX_OBJEKTE:,} Objekte).".replace(",", ".")
            + " Bitte im CAD-Programm vereinfachen (z. B. Blöcke auflösen "
            "oder Möblierung ausblenden).")
    if o.erster().get(67, "0").strip() == "1":
        return   # Papierbereich (Layout), nicht das Modell
    t = o.typ
    if t == "3DFACE":
        d = o.erster()
        a, b, c = (tf(_punkt(d, 10)), tf(_punkt(d, 11)), tf(_punkt(d, 12)))
        e = tf(_punkt(d, 13)) if 13 in d else c
        geo.dreieck(a, b, c)
        if e != c:
            geo.dreieck(a, c, e)
    elif t == "LINE":
        d = o.erster()
        geo.linie(tf(_punkt(d, 10)), tf(_punkt(d, 11)))
    elif t == "LWPOLYLINE":
        _lwpolyline(o, tf, geo, ctx)
    elif t == "POLYLINE":
        _polylinie(o, tf, geo, ctx)
    elif t == "MESH":
        _mesh(o, tf, geo)
    elif t in ("CIRCLE", "ARC"):
        _bogen(o, tf, geo, t == "CIRCLE")
    elif t == "INSERT":
        _insert(o, tf, geo, ctx, tiefe)
    else:
        ctx.ignoriert[t] += 1


def _hinweise(ctx: _Kontext) -> tuple:
    out = []
    if ctx.ignoriert:
        teile = ", ".join(f"{n}× {t}" for t, n in ctx.ignoriert.most_common(8))
        mehr = " …" if len(ctx.ignoriert) > 8 else ""
        out.append(f"Nicht übernommen (wird nicht unterstützt): {teile}{mehr}.")
        if ctx.ignoriert.keys() & {"3DSOLID", "BODY", "REGION", "SURFACE"}:
            out.append("Volumenkörper (3DSOLID) lassen sich nicht lesen — im CAD-Programm "
                       "als Netz (STL) exportieren.")
    if ctx.boegen:
        out.append("Bögen in Polylinien werden als gerade Strecken gezeigt.")
    if ctx.fehlende_bloecke:
        out.append(f"{len(ctx.fehlende_bloecke)} eingefügte(r) Block/Blöcke fehlt in der "
                   "Datei und wurde weggelassen.")
    if ctx.zu_tief:
        out.append(f"Zu tief verschachtelte Blöcke (mehr als {_MAX_TIEFE} Ebenen) wurden weggelassen.")
    if ctx.reihen:
        out.append("Reihen-Einfügungen (MINSERT) zeigen nur das erste Exemplar.")
    return tuple(out)


_letzter: tuple = (b"", None)


def lies_dxf(daten: bytes) -> DxfRoh:
    """DXF-Bytes -> :class:`DxfRoh`. Das letzte Ergebnis wird gemerkt — die
    Import-Abfrage liest die Datei zuerst fuer den Einheiten-Vorschlag
    (:func:`modell_import.dxf_info`) und gleich danach fuer den Import."""
    global _letzter
    if daten[:len(_BINAER_KENNUNG)] == _BINAER_KENNUNG:
        raise ModellImportFehler(
            "Binäre DXF-Dateien werden nicht unterstützt. Bitte die Zeichnung im "
            "CAD-Programm als DXF im Textformat (ASCII) speichern.")
    schluessel = hashlib.sha1(daten).digest()
    if _letzter[0] == schluessel:
        return _letzter[1]
    text = daten.decode("utf-8", errors="replace")
    einheit, entities, bloecke = _gliedern(text)
    ctx = _Kontext(bloecke)
    geo = _Geo()
    for o in entities:
        _objekt(o, lambda p: p, geo, ctx)
    hinweise = _hinweise(ctx)
    if not geo.s.idx and not geo.lin:
        meldung = ("Die DXF-Datei enthält keine verwendbare Geometrie (unterstützt: 3DFACE, "
                   "Polyface-/Polygon-Netze, MESH, LINE, LWPOLYLINE, POLYLINE, CIRCLE, ARC "
                   "und Blöcke über INSERT).")
        if hinweise:
            meldung += "\n" + "\n".join(hinweise)
        raise ModellImportFehler(meldung)
    roh = DxfRoh(pos=geo.s.pos, idx=geo.s.idx, lin=geo.lin, einheit=einheit,
                 hinweise=hinweise)
    _letzter = (schluessel, roh)
    return roh


def linien_zu_waenden(roh: DxfRoh, hoehe: float) -> tuple[array, array]:
    """Jede Linie als duennen Wandstreifen (zwei Dreiecke) von Z bis Z+hoehe
    hochziehen. ``hoehe`` in Datei-Einheiten. -> (pos, idx) inkl. der
    vorhandenen Flaechen; die Linien entfallen."""
    s = _Sammler()
    p = roh.pos
    def ecke(i):
        return (p[3 * i], p[3 * i + 1], p[3 * i + 2])
    for t in range(roh.dreiecke):
        s.dreieck(ecke(roh.idx[3 * t]), ecke(roh.idx[3 * t + 1]), ecke(roh.idx[3 * t + 2]))
    for k in range(roh.linien):
        a, b = ecke(roh.lin[2 * k]), ecke(roh.lin[2 * k + 1])
        a2, b2 = (a[0], a[1], a[2] + hoehe), (b[0], b[1], b[2] + hoehe)
        s.dreieck(a, b, b2)
        s.dreieck(a, b2, a2)
        if len(s.idx) > 3 * MAX_DREIECKE:
            raise _zu_viele(len(s.idx) // 3)
    return s.pos, s.idx
