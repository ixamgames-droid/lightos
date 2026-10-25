"""LIZ-4: Die Microsoft-Laufzeit oben im Bundle ist die neueste, die es mitbringt.

Befund (19.10.2026, Bundle von #1101): im Bundle liegen ``VCRUNTIME140.dll`` und
``VCRUNTIME140_1.dll`` dreimal — oben in ``_internal\\`` in 14.42 (aus der
Python-Installation des Bau-Rechners), unter ``PySide6\\`` und ``shiboken6\\``
in 14.44. Windows laedt je Name nur EINE Datei, und zwar die, die zuerst
gebraucht wird: ``python312.dll`` zieht die obere. Qt und PySide6 sind mit 14.44
gebaut und liefen damit gegen eine aeltere Laufzeit; Microsoft verlangt eine
Laufzeit, die mindestens so neu ist wie das neueste Werkzeug, mit dem ein Teil
gebaut wurde. Entscheidung des Projektinhabers (20.10.2026): die neueste Fassung
nach oben.

Regel dieses Moduls: fuer jeden Namen aus ``OBEN`` nimmt der Bau als obere Datei
die neueste gleichnamige Datei, die irgendwo im Bundle liegt. Die Kopien in den
Paketordnern bleiben, wo sie sind (sie gehoeren zu den Paketen).

Bewusst OHNE PyInstaller-Import (wie ``qt_umfang.py``): die Tests laufen auch
auf Linux. ``LightOS.spec`` reicht die Listen aus ``Analysis`` herein und
bekommt sie mit der neuesten oberen Datei zurueck. Den Gegencheck am FERTIGEN
Paket macht ``src/core/selbsttest.py`` (``pruefe_vc_laufzeit``).
"""
from __future__ import annotations

import os

#: Laufzeit-Dateien, die oben im Bundle (neben ``python312.dll``) liegen und von
#: dort fuer den ganzen Prozess geladen werden (Namen klein). Die Universal C
#: Runtime gehoert nicht dazu — sie kommt von Windows (``qt_umfang``).
OBEN: tuple[str, ...] = ("vcruntime140.dll", "vcruntime140_1.dll")


def _ziel(eintrag) -> str:
    """Zielpfad eines TOC-Eintrags in ``/``-Schreibweise."""
    return str(eintrag[0]).replace("\\", "/")


def dateifassung(pfad: str) -> tuple[int, ...] | None:
    """Dateiversion einer DLL als Zahlen-Tupel (``(14, 44, 35211)``), ``None``,
    wenn die Datei keine Versionsressource hat. Liest wie die Lizenzpruefung
    (``fremdkomponenten.pe_dateiversion``) — kein ``pefile`` noetig."""
    from fremdkomponenten import pe_dateiversion
    with open(pfad, "rb") as f:
        text = pe_dateiversion(f.read())
    return tuple(int(t) for t in text.split(".")) if text else None


def fassung_text(fassung) -> str:
    return ".".join(str(t) for t in fassung) if fassung else "?"


def angleichen(binaries, datas, fassung=dateifassung):
    """Legt fuer jeden Namen aus ``OBEN`` die neueste gleichnamige Datei des
    Bundles nach oben.

    ``binaries``/``datas``: Listen aus ``(ziel, quelle, typ)``; ``fassung(quelle)``
    liefert die Dateiversion als Tupel (oder ``None``).

    Rueckgabe ``(binaries, datas, bericht)``. ``bericht``: ``oben`` (Name ->
    Fassung oben als Text), ``ersetzt`` (Zeilen „alt -> neu“), ``fehler`` (Liste —
    leer heisst in Ordnung).
    """
    binaries = list(binaries)
    datas = list(datas)
    oben: dict[str, str] = {}
    ersetzt: list[str] = []
    fehler: list[str] = []

    for name in OBEN:
        treffer = [(liste, i, e) for liste in (binaries, datas)
                   for i, e in enumerate(liste)
                   if os.path.basename(_ziel(e)).lower() == name]
        if not treffer:
            continue
        lesbar = []
        for liste, i, e in treffer:
            try:
                f = fassung(e[1])
            except OSError as ex:
                f = None
                fehler.append(f"{_ziel(e)}: nicht lesbar ({type(ex).__name__}: {ex})")
            if f is None:
                fehler.append(f"{_ziel(e)}: keine Dateiversion — welche Laufzeit "
                              "oben liegen muss, ist so nicht zu entscheiden")
            else:
                lesbar.append((f, liste, i, e))
        obere = [t for t in lesbar if "/" not in _ziel(t[3])]
        if not obere or len(lesbar) < len(treffer):
            continue
        neueste = max(lesbar, key=lambda t: t[0])
        f_oben, liste, i, e = obere[0]
        if neueste[0] > f_oben:
            liste[i] = (e[0], neueste[3][1], e[2]) + tuple(e[3:])
            ersetzt.append(f"{_ziel(e)}: {fassung_text(f_oben)} -> "
                           f"{fassung_text(neueste[0])} (aus {_ziel(neueste[3])})")
            f_oben = neueste[0]
        oben[_ziel(e)] = fassung_text(f_oben)
        # Waechter: oben liegt jetzt keine aeltere Fassung als irgendwo sonst.
        for f, _l, _i, x in lesbar:
            if f > f_oben:
                fehler.append(f"{_ziel(e)} oben ist {fassung_text(f_oben)}, "
                              f"{_ziel(x)} ist neuer ({fassung_text(f)})")
    return binaries, datas, {"oben": oben, "ersetzt": ersetzt, "fehler": fehler}
