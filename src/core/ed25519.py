"""LIZ-1: Ed25519 (RFC 8032, Abschnitt 5.1) in reinem Python.

Die Lizenzpruefung (``src/core/lizenz.py``) braucht genau EINE Signaturpruefung
je Programmstart. Dafuer eine Krypto-Bibliothek als Pflichtabhaengigkeit
einzufuehren, waere unverhaeltnismaessig — die Rechnung hier ist kurz, folgt der
Referenz aus dem RFC (Abschnitt 6) und wird gegen dessen Testvektoren
(Abschnitt 7.1) geprueft: ``tests/test_liz1_ed25519.py``.

Nur Standardbibliothek (``hashlib``), kein Qt, kein Netz.

**Nicht** fuer geheime Schluessel in feindlicher Umgebung gedacht: die Rechnung
laeuft nicht in konstanter Zeit. Fuer das Pruefen (oeffentliche Daten) ist das
ohne Belang; signiert wird nur am Rechner des Urhebers.
"""
from __future__ import annotations

import hashlib

__all__ = ["oeffentlicher_schluessel", "signiere", "pruefe"]

_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_WURZEL_MINUS_EINS = pow(2, (_P - 1) // 4, _P)


def _sha512(daten: bytes) -> bytes:
    return hashlib.sha512(daten).digest()


def _sha512_mod_l(daten: bytes) -> int:
    return int.from_bytes(_sha512(daten), "little") % _L


# Punkte in erweiterten Koordinaten (X, Y, Z, T) mit x = X/Z, y = Y/Z, x*y = T/Z.
def _addiere(a, b):
    f = (a[1] - a[0]) * (b[1] - b[0]) % _P
    g = (a[1] + a[0]) * (b[1] + b[0]) % _P
    c = 2 * a[3] * b[3] * _D % _P
    d = 2 * a[2] * b[2] % _P
    e, ff, gg, h = g - f, d - c, d + c, g + f
    return (e * ff % _P, gg * h % _P, ff * gg % _P, e * h % _P)


def _mal(s: int, punkt):
    ergebnis = (0, 1, 1, 0)                      # neutrales Element
    while s > 0:
        if s & 1:
            ergebnis = _addiere(ergebnis, punkt)
        punkt = _addiere(punkt, punkt)
        s >>= 1
    return ergebnis


def _gleich(a, b) -> bool:
    # x1/z1 == x2/z2  <=>  x1*z2 == x2*z1 (ebenso fuer y)
    if (a[0] * b[2] - b[0] * a[2]) % _P != 0:
        return False
    return (a[1] * b[2] - b[1] * a[2]) % _P == 0


def _x_aus_y(y: int, vorzeichen: int):
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if x2 == 0:
        return None if vorzeichen else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _WURZEL_MINUS_EINS % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != vorzeichen:
        x = _P - x
    return x


_GY = 4 * pow(5, _P - 2, _P) % _P
_GX = _x_aus_y(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _packe(punkt) -> bytes:
    zinv = pow(punkt[2], _P - 2, _P)
    x = punkt[0] * zinv % _P
    y = punkt[1] * zinv % _P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _entpacke(daten: bytes):
    if len(daten) != 32:
        return None
    y = int.from_bytes(daten, "little")
    vorzeichen = y >> 255
    y &= (1 << 255) - 1
    x = _x_aus_y(y, vorzeichen)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _geheim_erweitern(geheim: bytes):
    if len(geheim) != 32:
        raise ValueError("Ed25519: der geheime Schluessel hat 32 Bytes")
    h = _sha512(geheim)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def oeffentlicher_schluessel(geheim: bytes) -> bytes:
    """Der oeffentliche Schluessel (32 Bytes) zum geheimen Schluessel (32 Bytes)."""
    a, _ = _geheim_erweitern(geheim)
    return _packe(_mal(a, _G))


def signiere(geheim: bytes, nachricht: bytes) -> bytes:
    """Signatur (64 Bytes) der Nachricht. Ohne den geheimen Schluessel wertlos —
    im Programm selbst wird nur :func:`pruefe` gebraucht."""
    a, praefix = _geheim_erweitern(geheim)
    oeffentlich = _packe(_mal(a, _G))
    r = _sha512_mod_l(praefix + nachricht)
    rs = _packe(_mal(r, _G))
    h = _sha512_mod_l(rs + oeffentlich + nachricht)
    s = (r + h * a) % _L
    return rs + s.to_bytes(32, "little")


def pruefe(oeffentlich: bytes, nachricht: bytes, signatur: bytes) -> bool:
    """True, wenn ``signatur`` zu ``nachricht`` und ``oeffentlich`` passt.

    Wirft nie: falsche Laengen, kaputte Punkte und Fremdtypen sind schlicht
    ``False``."""
    try:
        if len(oeffentlich) != 32 or len(signatur) != 64:
            return False
        a = _entpacke(bytes(oeffentlich))
        if a is None:
            return False
        rs = bytes(signatur[:32])
        r = _entpacke(rs)
        if r is None:
            return False
        s = int.from_bytes(signatur[32:], "little")
        if s >= _L:
            return False
        h = _sha512_mod_l(rs + bytes(oeffentlich) + bytes(nachricht))
        return _gleich(_mal(s, _G), _addiere(r, _mal(h, a)))
    except Exception:                               # noqa: BLE001
        return False
