"""VIZ-67: eigene 3D-Dateien (STL, OBJ, DXF) als Buehnenobjekt importieren.

Reines Python-Modul ohne Qt und ohne neue Abhaengigkeit. Es liest eine
STL- (binaer oder ASCII) oder OBJ-Datei, macht daraus ein indiziertes
Dreiecksnetz in Metern (Mittelpunkt der Bounding-Box im Ursprung, Y oben)
und packt es in eine kompakte Zeichenkette (``lsm1:`` + base64 von
zlib-komprimierten Binaerdaten). Diese Zeichenkette steht im Buehnenobjekt
(``StageElement.model``) und reist damit im Szenengraph der ``.lshow`` mit —
die Show laedt auf einem anderen Rechner ohne die Originaldatei.

Bewusst einfach gehalten:

* OBJ: nur ``v`` und ``f`` (Polygone als Faecher trianguliert, negative
  Indizes erlaubt). Normalen, Texturkoordinaten, Materialien und Gruppen
  werden ignoriert — das Objekt wird neutral grau, die Normalen rechnet die
  3D-Seite aus der Geometrie (``computeVertexNormals``).
* STL: binaer oder ASCII. Die Normalen in der Datei werden ignoriert (viele
  Programme schreiben dort Nullen); gleiche Eckpunkte werden zusammengelegt.
* DXF (Teil 2): eigener Parser in :mod:`dxf_import`. Linien (z. B. ein
  Hallenplan) reisen als Liniengeometrie mit (Format ``LSM2``) oder werden
  auf Wunsch zu Wandstreifen hochgezogen. Ohne Linien bleibt das gepackte
  Format byte-gleich ``LSM1`` — alte Shows laden unveraendert.
* Grenzen: ``MAX_DATEI_BYTES``, ``MAX_DREIECKE`` und ``MAX_LINIEN``. Alles, was nicht passt
  oder kaputt ist, endet in :class:`ModellImportFehler` mit einer deutschen
  Meldung fuer den Nutzer — nie in einer rohen Ausnahme.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import math
import os
import struct
import sys
import zlib
from array import array
from dataclasses import dataclass, field
from functools import lru_cache

MAX_DATEI_BYTES = 20 * 1024 * 1024
MAX_DREIECKE = 200_000
MAX_LINIEN = 200_000      # Strecken (DXF-Linien)
# Groesste Kante in Metern nach der Einheiten-Umrechnung. Groesser als das
# Eingabefeld der Buehnenobjekte (60 m) heisst fast immer: falsche Einheit.
MAX_KANTE_M = 60.0
MAX_HOEHE_M = 30.0   # Eingabefeld Hoehe
# Kleinste gespeicherte Objektgroesse je Achse (flache Modelle, z. B. ein Schild).
MIN_GROESSE_M = 0.01

EINHEITEN = {"mm": 0.001, "cm": 0.01, "m": 1.0, "in": 0.0254, "ft": 0.3048}

_PRAEFIX = "lsm1:"
_MAGIC = b"LSM1"
_MAGIC_LINIEN = b"LSM2"   # wie LSM1, dazu Linien (Index-Paare)
# Obergrenze fuer das Entpacken einer gespeicherten Zeichenkette (Schutz vor
# einer manipulierten Show, die beim Laden Gigabytes aufblaeht).
_MAX_ENTPACKT = 64 * 1024 * 1024


class ModellImportFehler(ValueError):
    """Datei passt nicht — die Meldung ist fuer den Nutzer gedacht."""


class ModellZuGross(ModellImportFehler):
    """VIZ-113: das Modell waere groesser als die Buehne erlaubt. ``groesse``
    (x, y, z in m) und ``passend`` (Massstab, mit dem es gerade hineinpasst)
    erlauben dem Aufrufer, ein Verkleinern anzubieten."""

    def __init__(self, text: str, groesse: tuple, passend: float):
        super().__init__(text)
        self.groesse = groesse
        self.passend = passend


@dataclass
class Netz:
    """Indiziertes Dreiecksnetz in Metern, Mittelpunkt im Ursprung."""

    positionen: array      # 'f', x,y,z je Eckpunkt
    indizes: array         # 'I', drei je Dreieck
    groesse: tuple[float, float, float]   # Bounding-Box (Breite, Hoehe, Tiefe)
    # VIZ-67 Teil 2: Linien als Index-Paare in ``positionen`` (DXF-Grundriss)
    linien: array = field(default_factory=lambda: array("I"))
    # Hinweise fuer den Nutzer (z. B. nicht unterstuetzte DXF-Objekte)
    hinweise: tuple = ()

    @property
    def eckpunkte(self) -> int:
        return len(self.positionen) // 3

    @property
    def dreiecke(self) -> int:
        return len(self.indizes) // 3

    @property
    def strecken(self) -> int:
        return len(self.linien) // 2


# ── Lesen ──────────────────────────────────────────────────────────────────

def _zahl(text: str) -> float:
    try:
        wert = float(text)
    except (TypeError, ValueError):
        raise ModellImportFehler(f"Ungültige Zahl in der Datei: {text[:30]!r}") from None
    if not math.isfinite(wert):
        raise ModellImportFehler("Die Datei enthält ungültige Koordinaten (unendlich/NaN).")
    return wert


def _zu_viele(n: int) -> ModellImportFehler:
    return ModellImportFehler(
        f"Das Modell hat {n:,} Dreiecke — erlaubt sind höchstens "
        f"{MAX_DREIECKE:,}.".replace(",", ".")
        + " Bitte das Modell im 3D-Programm vereinfachen (Polygone reduzieren).")


class _Sammler:
    """Legt gleiche Eckpunkte zusammen (STL ist eine Dreiecks-Suppe)."""

    def __init__(self):
        self.pos = array("d")  # CDX-70: volle Genauigkeit bis nach dem Zentrieren
        self.idx = array("I")
        self._index: dict = {}

    def punkt(self, x: float, y: float, z: float) -> int:
        schluessel = (x, y, z)
        i = self._index.get(schluessel)
        if i is None:
            i = len(self._index)
            self._index[schluessel] = i
            self.pos.extend((x, y, z))
        return i

    def dreieck(self, a, b, c) -> None:
        self.idx.extend((self.punkt(*a), self.punkt(*b), self.punkt(*c)))


def _ist_binaer_stl(daten: bytes) -> bool:
    if len(daten) < 84:
        return False
    n = struct.unpack_from("<I", daten, 80)[0]
    return 84 + 50 * n == len(daten)


def _lies_stl_binaer(daten: bytes) -> _Sammler:
    n = struct.unpack_from("<I", daten, 80)[0]
    if n == 0:
        raise ModellImportFehler("Die STL-Datei enthält keine Dreiecke.")
    if n > MAX_DREIECKE:
        raise _zu_viele(n)
    s = _Sammler()
    for werte in struct.iter_unpack("<12x9f2x", daten[84:84 + 50 * n]):
        for w in werte:
            if not math.isfinite(w):
                raise ModellImportFehler(
                    "Die Datei enthält ungültige Koordinaten (unendlich/NaN).")
        s.dreieck(werte[0:3], werte[3:6], werte[6:9])
    return s


def _lies_stl_ascii(text: str) -> _Sammler:
    punkte = []
    for zeile in text.splitlines():
        teile = zeile.split()
        if teile and teile[0].lower() == "vertex":
            if len(teile) < 4:
                raise ModellImportFehler("Kaputte STL-Datei: ein Eckpunkt hat zu wenige Koordinaten.")
            punkte.append((_zahl(teile[1]), _zahl(teile[2]), _zahl(teile[3])))
            if len(punkte) > 3 * MAX_DREIECKE:
                raise _zu_viele(len(punkte) // 3)
    if not punkte:
        raise ModellImportFehler("Die STL-Datei enthält keine Dreiecke.")
    if len(punkte) % 3:
        raise ModellImportFehler("Kaputte STL-Datei: die Eckpunkte ergeben keine ganzen Dreiecke.")
    s = _Sammler()
    for i in range(0, len(punkte), 3):
        s.dreieck(punkte[i], punkte[i + 1], punkte[i + 2])
    return s


def _lies_obj(text: str) -> _Sammler:
    pos = array("d")  # CDX-70
    idx = array("I")
    n_ecken = 0
    for nr, zeile in enumerate(text.splitlines(), 1):
        teile = zeile.split()
        if not teile:
            continue
        kopf = teile[0]
        if kopf == "v":
            if len(teile) < 4:
                raise ModellImportFehler(f"Kaputte OBJ-Datei (Zeile {nr}): Eckpunkt mit zu wenigen Koordinaten.")
            pos.extend((_zahl(teile[1]), _zahl(teile[2]), _zahl(teile[3])))
            n_ecken += 1
        elif kopf == "f":
            ecken = []
            for t in teile[1:]:
                roh = t.split("/", 1)[0]
                try:
                    i = int(roh)
                except ValueError:
                    raise ModellImportFehler(
                        f"Kaputte OBJ-Datei (Zeile {nr}): ungültiger Flächen-Index {t[:20]!r}.") from None
                # OBJ zaehlt ab 1; negative Indizes zaehlen vom bisherigen Ende.
                i = i - 1 if i > 0 else n_ecken + i
                if i < 0 or i >= n_ecken:
                    raise ModellImportFehler(
                        f"Kaputte OBJ-Datei (Zeile {nr}): Fläche verweist auf einen Eckpunkt, den es nicht gibt.")
                ecken.append(i)
            if len(ecken) < 3:
                continue   # Linien/Punkte haben keine Flaeche
            for k in range(1, len(ecken) - 1):   # Faecher-Triangulierung
                idx.extend((ecken[0], ecken[k], ecken[k + 1]))
            if len(idx) > 3 * MAX_DREIECKE:
                raise _zu_viele(len(idx) // 3)
    if not idx:
        raise ModellImportFehler("Die OBJ-Datei enthält keine Flächen (nur Punkte oder Linien?).")
    s = _Sammler()
    s.pos, s.idx = pos, idx
    return s


def _text(daten: bytes) -> str:
    return daten.decode("utf-8", errors="replace")


def _datei_bytes(pfad: str) -> bytes:
    try:
        groesse = os.path.getsize(pfad)
    except OSError:
        raise ModellImportFehler("Die Datei lässt sich nicht öffnen.") from None
    if groesse > MAX_DATEI_BYTES:
        raise ModellImportFehler(
            f"Die Datei ist {groesse / 1024 / 1024:.1f} MB groß — erlaubt sind höchstens "
            f"{MAX_DATEI_BYTES // 1024 // 1024} MB. Bitte das Modell vereinfachen.")
    try:
        with open(pfad, "rb") as f:
            daten = f.read()
    except OSError:
        raise ModellImportFehler("Die Datei lässt sich nicht lesen.") from None
    return daten


def lies_datei(pfad: str, einheit: str = "mm", z_oben: bool = False,
               wand_hoehe_m: float | None = None, massstab: float = 1.0) -> Netz:
    """Datei lesen und als :class:`Netz` (Meter, zentriert, Y oben) liefern.
    ``wand_hoehe_m`` (nur DXF): Linien als Waende dieser Hoehe hochziehen."""
    daten = _datei_bytes(pfad)
    endung = os.path.splitext(pfad)[1].lower()
    return lies_bytes(daten, endung, einheit, z_oben, wand_hoehe_m, massstab)


@dataclass
class DxfInfo:
    """Was die Import-Abfrage vorab ueber eine DXF-Datei wissen muss."""

    einheit: str | None    # aus $INSUNITS, None = nicht angegeben
    dreiecke: int
    linien: int


def dxf_info(pfad: str) -> DxfInfo:
    """DXF vorab lesen: Einheiten-Vorschlag und ob es Linien gibt."""
    from .dxf_import import lies_dxf
    roh = lies_dxf(_pruefe_bytes(_datei_bytes(pfad)))
    return DxfInfo(einheit=roh.einheit, dreiecke=roh.dreiecke, linien=roh.linien)


def _pruefe_bytes(daten: bytes) -> bytes:
    if len(daten) > MAX_DATEI_BYTES:
        raise ModellImportFehler(
            f"Die Datei ist {len(daten) / 1024 / 1024:.1f} MB groß — erlaubt sind höchstens "
            f"{MAX_DATEI_BYTES // 1024 // 1024} MB. Bitte das Modell vereinfachen.")
    if not daten:
        raise ModellImportFehler("Die Datei ist leer.")
    return daten


def lies_bytes(daten: bytes, endung: str, einheit: str = "mm",
               z_oben: bool = False, wand_hoehe_m: float | None = None,
               massstab: float = 1.0) -> Netz:
    """Wie :func:`lies_datei`, aber aus Bytes (``endung`` = ``.stl``/``.obj``/``.dxf``)."""
    if einheit not in EINHEITEN:
        raise ModellImportFehler(f"Unbekannte Einheit: {einheit}")
    if not (0.0 < massstab <= 1.0):
        raise ModellImportFehler("Der Maßstab muss zwischen 0 und 1 liegen.")
    _pruefe_bytes(daten)
    faktor = EINHEITEN[einheit] * massstab       # VIZ-113: auf Wunsch verkleinert
    endung = (endung or "").lower()
    if endung == ".dxf":
        return _lies_dxf(daten, faktor, wand_hoehe_m)
    if endung == ".stl":
        if _ist_binaer_stl(daten):
            s = _lies_stl_binaer(daten)
        elif daten.lstrip()[:5].lower() == b"solid":
            s = _lies_stl_ascii(_text(daten))
        else:
            raise ModellImportFehler(
                "Die STL-Datei ist beschädigt oder unvollständig (weder gültiges Binär- noch Text-STL).")
    elif endung == ".obj":
        s = _lies_obj(_text(daten))
    else:
        raise ModellImportFehler("Nur STL-, OBJ- und DXF-Dateien lassen sich importieren.")
    return _normieren(s.pos, s.idx, faktor, z_oben)


def _lies_dxf(daten: bytes, faktor: float, wand_hoehe_m: float | None) -> Netz:
    from .dxf_import import lies_dxf, linien_zu_waenden
    roh = lies_dxf(daten)
    # DXF-Weltkoordinaten haben immer Z oben.
    if wand_hoehe_m is not None and roh.linien:
        if not (0.0 < wand_hoehe_m <= MAX_HOEHE_M):
            raise ModellImportFehler(
                f"Die Wandhöhe muss zwischen 0 und {MAX_HOEHE_M:.0f} m liegen.")
        pos, idx = linien_zu_waenden(roh, wand_hoehe_m / faktor)
        netz = _normieren(pos, idx, faktor, True)
    else:
        netz = _normieren(roh.pos, roh.idx, faktor, True, roh.lin)
    netz.hinweise = roh.hinweise
    return netz


def _normieren(pos: array, idx: array, faktor: float, z_oben: bool,
               linien: array | None = None) -> Netz:
    n = len(pos) // 3
    if n == 0 or not (idx or linien):
        raise ModellImportFehler("Das Modell enthält keine Geometrie.")
    # CDX-70: in doppelter Genauigkeit rechnen und erst NACH dem Zentrieren auf
    # float32 runden — sonst gehen bei grossen Absolutkoordinaten (CAD-Plaene
    # im Landeskoordinatensystem) feine Details schon beim Einlesen verloren.
    out = array("d", bytes(8 * 3 * n))
    for i in range(n):
        x, y, z = pos[3 * i], pos[3 * i + 1], pos[3 * i + 2]
        if z_oben:                       # CAD/STL: Z zeigt nach oben -> Y oben
            y, z = z, -y
        out[3 * i], out[3 * i + 1], out[3 * i + 2] = x * faktor, y * faktor, z * faktor
    mins = [min(out[a::3]) for a in range(3)]
    maxs = [max(out[a::3]) for a in range(3)]
    groesse = tuple(maxs[a] - mins[a] for a in range(3))
    if max(groesse) <= 0.0:
        raise ModellImportFehler("Das Modell hat keine Ausdehnung (alle Punkte liegen aufeinander).")
    if max(groesse[0], groesse[2]) > MAX_KANTE_M or groesse[1] > MAX_HOEHE_M:
        grenzen = [MAX_KANTE_M / g for g in (groesse[0], groesse[2]) if g > 0]
        if groesse[1] > 0:
            grenzen.append(MAX_HOEHE_M / groesse[1])
        raise ModellZuGross(
            f"Das Modell wäre {groesse[0]:.1f} × {groesse[1]:.1f} × {groesse[2]:.1f} m groß — das passt nicht auf die Bühne "
            f"(höchstens {MAX_KANTE_M:.0f} m breit/tief und {MAX_HOEHE_M:.0f} m hoch). Stimmt die Einheit? Für CAD- und "
            "3D-Druck-Dateien meist Millimeter wählen.",
            tuple(float(g) for g in groesse), min(grenzen) * 0.999)
    mitte = [(mins[a] + maxs[a]) / 2.0 for a in range(3)]
    for i in range(n):
        for a in range(3):
            out[3 * i + a] -= mitte[a]
    return Netz(positionen=array("f", out), indizes=array("I", idx),
                groesse=tuple(float(g) for g in groesse),
                linien=array("I", linien or ()))


# ── Einbetten (Zeichenkette in der Show) ────────────────────────────────────

def _le(a: array) -> bytes:
    if sys.byteorder != "little":
        a = array(a.typecode, a)
        a.byteswap()
    return a.tobytes()


def packen(netz: Netz) -> str:
    """Netz -> ``lsm1:<base64(zlib(...))>`` (fuer ``StageElement.model``).

    Ohne Linien: Binaerformat ``LSM1`` wie seit Teil 1. Mit Linien: ``LSM2``
    (Kopf mit dritter Zahl, Linien-Indizes am Ende)."""
    if netz.strecken:
        roh = (_MAGIC_LINIEN + struct.pack("<III", netz.eckpunkte, netz.dreiecke, netz.strecken)
               + _le(netz.positionen) + _le(netz.indizes) + _le(netz.linien))
    else:
        roh = (_MAGIC + struct.pack("<II", netz.eckpunkte, netz.dreiecke)
               + _le(netz.positionen) + _le(netz.indizes))
    return _PRAEFIX + base64.b64encode(zlib.compress(roh, 6)).decode("ascii")


def entpacken(text: str) -> Netz:
    """Gegenstueck zu :func:`packen`. Prueft alles (die Show kann manipuliert sein)."""
    if not isinstance(text, str) or not text.startswith(_PRAEFIX):
        raise ModellImportFehler("Kein eingebettetes 3D-Modell.")
    try:
        gepackt = base64.b64decode(text[len(_PRAEFIX):], validate=True)
        d = zlib.decompressobj()
        roh = d.decompress(gepackt, _MAX_ENTPACKT)
        if d.unconsumed_tail:
            raise ModellImportFehler("Eingebettetes 3D-Modell ist zu groß.")
        if not d.eof:                    # CDX-70: abgeschnitten (Pruefsumme fehlt)
            raise ModellImportFehler("Eingebettetes 3D-Modell ist beschädigt.")
    except (binascii.Error, zlib.error, ValueError) as e:
        if isinstance(e, ModellImportFehler):
            raise
        raise ModellImportFehler("Eingebettetes 3D-Modell ist beschädigt.") from None
    if len(roh) >= 16 and roh[:4] == _MAGIC_LINIEN:
        nv, nt, nl = struct.unpack_from("<III", roh, 4)
        kopf = 16
        if nl == 0:
            raise ModellImportFehler("Eingebettetes 3D-Modell ist beschädigt.")
    elif len(roh) >= 12 and roh[:4] == _MAGIC:
        nv, nt = struct.unpack_from("<II", roh, 4)
        nl, kopf = 0, 12
        if nt == 0:
            raise ModellImportFehler("Eingebettetes 3D-Modell ist beschädigt.")
    else:
        raise ModellImportFehler("Eingebettetes 3D-Modell ist beschädigt.")
    if (nt > MAX_DREIECKE or nl > MAX_LINIEN or nv == 0
            or len(roh) != kopf + 12 * nv + 12 * nt + 8 * nl):
        raise ModellImportFehler("Eingebettetes 3D-Modell ist beschädigt.")
    a, b = kopf + 12 * nv, kopf + 12 * nv + 12 * nt
    pos = array("f")
    pos.frombytes(roh[kopf:a])
    idx = array("I")
    idx.frombytes(roh[a:b])
    lin = array("I")
    lin.frombytes(roh[b:])
    if sys.byteorder != "little":
        pos.byteswap()
        idx.byteswap()
        lin.byteswap()
    if (max(idx, default=0) >= nv or max(lin, default=0) >= nv
            or not all(math.isfinite(v) for v in pos)):
        raise ModellImportFehler("Eingebettetes 3D-Modell ist beschädigt.")
    groesse = tuple(float(max(pos[a::3]) - min(pos[a::3])) for a in range(3))
    return Netz(positionen=pos, indizes=idx, groesse=groesse, linien=lin)


@lru_cache(maxsize=16)
def js_daten(text: str) -> dict | None:
    """Payload fuer die 3D-Seite: ``{key, pos, idx}`` (base64, Little Endian;
    mit Linien zusaetzlich ``lin``),
    oder None bei einer kaputten Zeichenkette. Gemerkt, weil jedes Neuladen
    der Buehne jedes Objekt erneut schickt."""
    try:
        netz = entpacken(text)
    except ModellImportFehler as e:
        print(f"[stage] Importiertes Modell nicht lesbar: {e}")
        return None
    out = {
        "key": hashlib.sha1(text.encode("ascii", "replace")).hexdigest()[:16],
        "pos": base64.b64encode(_le(netz.positionen)).decode("ascii"),
        "idx": base64.b64encode(_le(netz.indizes)).decode("ascii"),
    }
    if netz.strecken:
        out["lin"] = base64.b64encode(_le(netz.linien)).decode("ascii")
    return out


def element_groesse(netz: Netz) -> tuple[float, float, float]:
    """Startgroesse des Buehnenobjekts (je Achse mindestens ``MIN_GROESSE_M``)."""
    return tuple(max(MIN_GROESSE_M, round(g, 4)) for g in netz.groesse)
