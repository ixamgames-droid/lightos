"""WEB-11: QR-Code-Erzeuger in reinem Python — ohne Fremdbibliothek, ohne Internet.

Gebraucht wird er fuer genau eine Sache: den Link der Handy-Konsole
(``http://<IP>:<Port>/konsole?k=<Schluessel>``) als Bild, das die Kamera des
Handys liest. Deshalb bewusst schmal:

  * Byte-Modus (ISO 8859-1 bzw. UTF-8-Bytes) — eine URL braucht nichts anderes,
  * Fehlerkorrektur M (rund 15 % duerfen fehlen),
  * Versionen 1 bis 10 (21 x 21 bis 57 x 57 Module, bis 213 Bytes),
  * automatische Wahl der kleinsten Version und der Maske nach dem Regelwerk
    der Norm (ISO/IEC 18004, Abschnitt „Bewertung der Maskierung").

Das Ergebnis ist eine Matrix aus Wahrheitswerten (``True`` = dunkles Modul),
OHNE Ruhezone — die legt die Darstellung an (``src/ui/widgets/handy_qr.py``).

Kein Qt, keine Ein-/Ausgabe, keine Protokollzeile: der Inhalt ist ein
Geheimnis (der Schluessel steht im Link) und verlaesst dieses Modul nur als
Matrix.
"""
from __future__ import annotations

__all__ = ["QrCode", "QrFehler", "erzeuge", "kapazitaet", "MAX_VERSION"]

MAX_VERSION = 10

# Fehlerkorrektur M je Version: (Korrektur-Codewoerter je Block,
#   ((Anzahl Bloecke, Daten-Codewoerter je Block), …)).  ISO/IEC 18004, Tab. 9.
_BLOECKE_M = {
    1: (10, ((1, 16),)),
    2: (16, ((1, 28),)),
    3: (26, ((1, 44),)),
    4: (18, ((2, 32),)),
    5: (24, ((2, 43),)),
    6: (16, ((4, 27),)),
    7: (18, ((4, 31),)),
    8: (22, ((2, 38), (2, 39))),
    9: (22, ((3, 36), (2, 37))),
    10: (26, ((4, 43), (1, 44))),
}

# Mittelpunkte der Ausrichtungsmuster je Version (Anhang E der Norm).
_AUSRICHTUNG = {
    1: (), 2: (6, 18), 3: (6, 22), 4: (6, 26), 5: (6, 30), 6: (6, 34),
    7: (6, 22, 38), 8: (6, 24, 42), 9: (6, 26, 46), 10: (6, 28, 50),
}

_FORMAT_M = 0b00            # Kennung der Fehlerkorrektur M in der Format-Information
_MODUS_BYTE = 0b0100


class QrFehler(ValueError):
    """Der Inhalt passt nicht in einen Code bis Version 10."""


# ── Rechnen im Koerper GF(256), Polynom x^8+x^4+x^3+x^2+1 ─────────────────────

_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]
del _x, _i


def _mal(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _generator(grad: int) -> list[int]:
    """Erzeugerpolynom (x-a^0)(x-a^1)…(x-a^(grad-1)), hoechste Potenz zuerst,
    ohne den fuehrenden Koeffizienten 1."""
    poly = [1]
    for i in range(grad):
        neu = [0] * (len(poly) + 1)
        for j, k in enumerate(poly):
            neu[j] ^= k
            neu[j + 1] ^= _mal(k, _EXP[i])
        poly = neu
    return poly[1:]


def _korrektur(daten: list[int], grad: int) -> list[int]:
    """Rest der Division daten·x^grad durch das Erzeugerpolynom."""
    gen = _generator(grad)
    rest = [0] * grad
    for byte in daten:
        faktor = byte ^ rest[0]
        rest = rest[1:] + [0]
        if faktor:
            for i in range(grad):
                rest[i] ^= _mal(gen[i], faktor)
    return rest


# ── Kapazitaet und Datenstrom ────────────────────────────────────────────────

def _daten_codewoerter(version: int) -> int:
    return sum(n * k for n, k in _BLOECKE_M[version][1])


def _laengen_bits(version: int) -> int:
    return 8 if version <= 9 else 16


def kapazitaet(version: int) -> int:
    """Groesste Zahl an Bytes, die Version ``version`` (Stufe M) fasst."""
    if version not in _BLOECKE_M:
        raise QrFehler(f"Version {version} wird nicht unterstuetzt (1–{MAX_VERSION}).")
    return (_daten_codewoerter(version) * 8 - 4 - _laengen_bits(version)) // 8


def _kleinste_version(laenge: int) -> int:
    for version in range(1, MAX_VERSION + 1):
        if laenge <= kapazitaet(version):
            return version
    raise QrFehler(
        f"Inhalt zu lang fuer einen QR-Code: {laenge} Bytes, "
        f"hoechstens {kapazitaet(MAX_VERSION)}.")


def _codewoerter(daten: bytes, version: int) -> list[int]:
    """Daten-Codewoerter: Modus, Laenge, Bytes, Abschluss, Fuellbytes."""
    gesamt = _daten_codewoerter(version) * 8
    bits: list[int] = []

    def haenge_an(wert: int, breite: int) -> None:
        for i in range(breite - 1, -1, -1):
            bits.append((wert >> i) & 1)

    haenge_an(_MODUS_BYTE, 4)
    haenge_an(len(daten), _laengen_bits(version))
    for b in daten:
        haenge_an(b, 8)
    haenge_an(0, min(4, gesamt - len(bits)))            # Abschluss
    haenge_an(0, (-len(bits)) % 8)                       # auf Bytegrenze
    raus = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    fuell = (0xEC, 0x11)
    i = 0
    while len(raus) < gesamt // 8:
        raus.append(fuell[i % 2])
        i += 1
    return raus


def _verschraenkt(codewoerter: list[int], version: int) -> list[int]:
    """In Bloecke teilen, je Block die Korrektur rechnen, spaltenweise mischen."""
    grad, gruppen = _BLOECKE_M[version]
    bloecke, pos = [], 0
    for anzahl, laenge in gruppen:
        for _ in range(anzahl):
            bloecke.append(codewoerter[pos:pos + laenge])
            pos += laenge
    korrektur = [_korrektur(b, grad) for b in bloecke]
    raus = []
    for i in range(max(len(b) for b in bloecke)):
        raus += [b[i] for b in bloecke if i < len(b)]
    for i in range(grad):
        raus += [k[i] for k in korrektur]
    return raus


# ── Matrix ───────────────────────────────────────────────────────────────────

_MASKEN = (
    lambda x, y: (x + y) % 2 == 0,
    lambda x, y: y % 2 == 0,
    lambda x, y: x % 3 == 0,
    lambda x, y: (x + y) % 3 == 0,
    lambda x, y: (x // 3 + y // 2) % 2 == 0,
    lambda x, y: (x * y) % 2 + (x * y) % 3 == 0,
    lambda x, y: ((x * y) % 2 + (x * y) % 3) % 2 == 0,
    lambda x, y: ((x + y) % 2 + (x * y) % 3) % 2 == 0,
)


def _bch(wert: int, breite: int, polynom: int, grad: int) -> int:
    rest = wert
    for _ in range(grad):
        rest = (rest << 1) ^ ((rest >> (grad - 1)) * polynom)
    return (wert << grad) | (rest & ((1 << grad) - 1))


class _Gitter:
    """Die Module und daneben die Karte, welche davon Funktionsmuster sind."""

    def __init__(self, version: int):
        self.version = version
        self.n = n = 17 + 4 * version
        self.dunkel = [[False] * n for _ in range(n)]
        self.fest = [[False] * n for _ in range(n)]
        self._funktionsmuster()

    def _setze(self, x: int, y: int, dunkel: bool) -> None:
        self.dunkel[y][x] = bool(dunkel)
        self.fest[y][x] = True

    def _funktionsmuster(self) -> None:
        n = self.n
        # Taktmuster (Zeile 6, Spalte 6)
        for i in range(n):
            self._setze(6, i, i % 2 == 0)
            self._setze(i, 6, i % 2 == 0)
        # Suchmuster in drei Ecken, samt hellem Trenner
        for mx, my in ((3, 3), (n - 4, 3), (3, n - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = mx + dx, my + dy
                    if 0 <= x < n and 0 <= y < n:
                        abstand = max(abs(dx), abs(dy))
                        self._setze(x, y, abstand not in (2, 4))
        # Ausrichtungsmuster (nicht dort, wo ein Suchmuster liegt)
        mitten = _AUSRICHTUNG[self.version]
        letzte = len(mitten) - 1
        for i, my in enumerate(mitten):
            for j, mx in enumerate(mitten):
                if (i, j) in ((0, 0), (0, letzte), (letzte, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self._setze(mx + dx, my + dy, max(abs(dx), abs(dy)) != 1)
        # Format-Information vormerken (Wert kommt mit der Maske), Version eintragen
        self.format_eintragen(0)
        self._version_eintragen()

    def format_eintragen(self, maske: int) -> None:
        n = self.n
        bits = _bch((_FORMAT_M << 3) | maske, 5, 0x537, 10) ^ 0x5412

        def bit(i: int) -> bool:
            return bool((bits >> i) & 1)

        # erste Kopie: um das Suchmuster oben links
        for i in range(6):
            self._setze(8, i, bit(i))
        self._setze(8, 7, bit(6))
        self._setze(8, 8, bit(7))
        self._setze(7, 8, bit(8))
        for i in range(9, 15):
            self._setze(14 - i, 8, bit(i))
        # zweite Kopie: geteilt auf oben rechts und unten links
        for i in range(8):
            self._setze(n - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self._setze(8, n - 15 + i, bit(i))
        self._setze(8, n - 8, True)                     # das immer dunkle Modul

    def _version_eintragen(self) -> None:
        if self.version < 7:
            return
        bits = _bch(self.version, 6, 0x1F25, 12)
        for i in range(18):
            b = bool((bits >> i) & 1)
            a, c = self.n - 11 + i % 3, i // 3
            self._setze(a, c, b)
            self._setze(c, a, b)

    def daten_eintragen(self, codewoerter: list[int]) -> None:
        """Im Zickzack von unten rechts, je zwei Spalten, Spalte 6 ausgelassen."""
        n = self.n
        i = 0
        gesamt = len(codewoerter) * 8
        rechts = n - 1
        while rechts >= 1:
            if rechts == 6:
                rechts = 5
            for schritt in range(n):
                for j in range(2):
                    x = rechts - j
                    aufwaerts = ((rechts + 1) & 2) == 0
                    y = n - 1 - schritt if aufwaerts else schritt
                    if not self.fest[y][x] and i < gesamt:
                        self.dunkel[y][x] = bool(
                            (codewoerter[i >> 3] >> (7 - (i & 7))) & 1)
                        i += 1
                    # uebrige Module (Restbits) bleiben hell
            rechts -= 2
        if i != gesamt:
            raise QrFehler("interner Fehler: Codewoerter passen nicht in die Matrix")

    def maskiere(self, maske: int) -> None:
        """XOR mit dem Maskenmuster — zweimal angewandt hebt es sich auf."""
        regel = _MASKEN[maske]
        for y in range(self.n):
            zeile, fest = self.dunkel[y], self.fest[y]
            for x in range(self.n):
                if not fest[x] and regel(x, y):
                    zeile[x] = not zeile[x]

    def strafpunkte(self) -> int:
        return strafpunkte(self.dunkel)


def strafpunkte(matrix) -> int:
    """Bewertung einer maskierten Matrix nach den vier Regeln der Norm
    (kleiner ist besser)."""
    n = len(matrix)
    punkte = 0
    spalten = [[matrix[y][x] for y in range(n)] for x in range(n)]
    # Regel 1: fuenf oder mehr gleiche Module in Folge (Zeile und Spalte)
    for linien in (matrix, spalten):
        for linie in linien:
            lauf = 1
            for i in range(1, n):
                if linie[i] == linie[i - 1]:
                    lauf += 1
                else:
                    if lauf >= 5:
                        punkte += lauf - 2
                    lauf = 1
            if lauf >= 5:
                punkte += lauf - 2
    # Regel 2: 2x2-Bloecke gleicher Farbe
    for y in range(n - 1):
        oben, unten = matrix[y], matrix[y + 1]
        for x in range(n - 1):
            if oben[x] == oben[x + 1] == unten[x] == unten[x + 1]:
                punkte += 3
    # Regel 3: das Suchmuster-Verhaeltnis 1:1:3:1:1 mit vier hellen Modulen
    # davor oder dahinter. Die Ruhezone um den Code ist hell und zaehlt mit:
    # ein solches Muster direkt am Rand ist fuer einen Leser genauso
    # verwechselbar wie eines mitten im Code.
    a = (True, False, True, True, True, False, True, False, False, False, False)
    b = a[::-1]
    rand = (False,) * 4
    for linien in (matrix, spalten):
        for linie in linien:
            t = rand + tuple(linie) + rand
            for i in range(len(t) - 10):
                stueck = t[i:i + 11]
                if stueck == a or stueck == b:
                    punkte += 40
    # Regel 4: Abweichung des Dunkelanteils von 50 %, je 5 % zehn Punkte
    dunkel = sum(sum(1 for m in zeile if m) for zeile in matrix)
    anteil = dunkel * 100 / (n * n)
    punkte += int(abs(anteil - 50) / 5) * 10
    return punkte


class QrCode:
    """Ein fertiger Code: ``matrix[y][x]`` ist ``True`` fuer ein dunkles Modul."""

    __slots__ = ("version", "maske", "matrix")

    def __init__(self, version: int, maske: int, matrix):
        self.version = version
        self.maske = maske
        self.matrix = tuple(tuple(bool(m) for m in zeile) for zeile in matrix)

    @property
    def groesse(self) -> int:
        """Kantenlaenge in Modulen, ohne Ruhezone."""
        return len(self.matrix)

    def als_text(self, dunkel: str = "#", hell: str = ".") -> str:
        return "\n".join("".join(dunkel if m else hell for m in zeile)
                         for zeile in self.matrix)

    def __repr__(self) -> str:      # nie den Inhalt zeigen — er ist ein Geheimnis
        return f"<QrCode Version {self.version}, Maske {self.maske}>"


def erzeuge(inhalt, *, version: int | None = None, maske: int | None = None) -> QrCode:
    """Baut den QR-Code fuer ``inhalt`` (Text wird als UTF-8 kodiert).

    ``version``/``maske`` legen die Wahl fest (fuer Tests und Gegenproben);
    ohne sie waehlt die Funktion die kleinste passende Version und die Maske
    mit den wenigsten Strafpunkten. Wirft ``QrFehler``, wenn der Inhalt nicht
    passt.
    """
    daten = inhalt.encode("utf-8") if isinstance(inhalt, str) else bytes(inhalt)
    if version is None:
        version = _kleinste_version(len(daten))
    elif version not in _BLOECKE_M:
        raise QrFehler(f"Version {version} wird nicht unterstuetzt (1–{MAX_VERSION}).")
    elif len(daten) > kapazitaet(version):
        raise QrFehler(
            f"Inhalt zu lang fuer Version {version}: {len(daten)} Bytes, "
            f"hoechstens {kapazitaet(version)}.")
    if maske is not None and maske not in range(8):
        raise QrFehler("Maske muss zwischen 0 und 7 liegen.")

    gitter = _Gitter(version)
    gitter.daten_eintragen(_verschraenkt(_codewoerter(daten, version), version))
    if maske is None:
        beste, wenigste = 0, None
        for kandidat in range(8):
            gitter.maskiere(kandidat)
            gitter.format_eintragen(kandidat)
            punkte = gitter.strafpunkte()
            if wenigste is None or punkte < wenigste:
                beste, wenigste = kandidat, punkte
            gitter.maskiere(kandidat)                    # zuruecknehmen
        maske = beste
    gitter.maskiere(maske)
    gitter.format_eintragen(maske)
    return QrCode(version, maske, gitter.dunkel)
