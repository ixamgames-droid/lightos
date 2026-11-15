"""LAS-47 — SH-LASER3W-Flips (LAS-28) in Funktionen und VC-Bindungen alter
Shows nachziehen (Rest aus CDX-65).

CDX-65 setzt gespeicherte WERTE alter Shows um (Programmer, Cues, Paletten …):
vor LAS-28 (#1211) trugen alle vier Flip-Kanaele ``laser_twist``, seither
tragen die vertikalen ``laser_twist_y``. Was CDX-65 nicht erreicht, sind
Stellen, die ein Attribut als ZIEL nennen:

* Effekte (``LayeredEffect.target_attribute``) und Kanal-Kopplungen
  (``MappedChannelChange``-Regeln) auf ``laser_twist`` schrieben vorher auf
  ALLE vier Flips, seither nur auf die zwei horizontalen. Verhaltenserhaltend
  umgesetzt: der Effekt bekommt ``laser_twist_y`` als Zusatzziel, die Regel
  eine Kopie mit Ziel ``laser_twist_y`` — dasselbe Signal trifft wieder alle
  vier Flips. Ob Robin den Effekt „auf alle Flips" so wollte, ist aus der
  Datei nicht zu erkennen; gespielt wurde er so, also bleibt er so.
* VC-Fader im Programmer-Modus auf ``laser_twist#N`` (Freitext) zeigten nach
  LAS-28 auf einen anderen bzw. keinen Kanal; ein Fader auf ``laser_twist``
  traf vorher alle vier Flips (Zusatzattribut wie beim Effekt).

Dieselben Regeln wie CDX-65: nur ohne Marker ``LAS-28`` und nur, wenn ein
SH-LASER3W im neuen Profilstand gepatcht ist. Ein blosses ``laser_twist``
bzw. ``laser_twist#1`` ist mehrdeutig (Shows zwischen LAS-28 und CDX-65
tragen keinen Marker) und wird nur bei ``alt_show`` umgesetzt (Altstands-
Merkmal oder ZIP-Zeitstempel vor dem Stichtag, kein ``laser_twist_y``).
``#2``/``#3`` gibt es nur im Altstand (der L2600 hat zwei ``laser_twist``) —
``#3`` wird immer umgesetzt, ``#2`` -> ``#1`` nur, wenn kein anderes Geraet mit
mehreren ``laser_twist`` (L2600) betroffen ist (dort hiesse ``#1`` dann etwas
anderes). Idempotent: ein zweiter Lauf findet ``laser_twist_y`` schon vor.

Alles best-effort: ein Fehler laesst das betroffene Teil unveraendert.
"""
from __future__ import annotations

_TWIST = "laser_twist"
_TWIST_Y = "laser_twist_y"


def _basis(a) -> str:
    return str(a).split("#", 1)[0]


def _ist_neu(a) -> bool:
    return isinstance(a, str) and _basis(a) == _TWIST_Y


def _ist_alt(a) -> bool:
    return a in ("laser_twist#2", "laser_twist#3")


def _vc_regler(knoten):
    """Alle Dicts mit ``programmer_attr`` im rohen VC-Layout (beliebig tief)."""
    stapel = [knoten]
    while stapel:
        k = stapel.pop()
        if isinstance(k, list):
            stapel.extend(x for x in k if isinstance(x, (dict, list)))
        elif isinstance(k, dict):
            if isinstance(k.get("programmer_attr"), str):
                yield k
            stapel.extend(v for v in k.values() if isinstance(v, (dict, list)))


def _funktions_dicts(data) -> list:
    try:
        fl = (data.get("functions") or {}).get("functions") or []
    except Exception:
        return []
    return [f for f in fl if isinstance(f, dict)] if isinstance(fl, list) else []


def ziel_befund(data) -> tuple[int, int]:
    """Altstands- (``laser_twist#2/#3``) und Neustands-Merkmale
    (``laser_twist_y*``) in Effekt-Zielen, Regel-Zielen und VC-Bindungen der
    ROHEN show.json. Ergaenzt ``_las28_befund`` (der nur Werte-Dicts zaehlt)."""
    alt = neu = 0

    def _zaehle(a) -> None:
        nonlocal alt, neu
        if _ist_neu(a):
            neu += 1
        elif _ist_alt(a):
            alt += 1

    try:
        for f in _funktions_dicts(data):
            _zaehle(f.get("target_attribute"))
            for a in f.get("zusatz_ziele") or []:
                _zaehle(a)
            for r in f.get("rules") or []:
                if isinstance(r, dict):
                    _zaehle(r.get("target"))
        for w in _vc_regler(data.get("virtual_console")):
            _zaehle(w.get("programmer_attr"))
            for a in w.get("programmer_attr_zusatz") or []:
                _zaehle(a)
    except Exception as e:
        print(f"[las28_ziele] befund failed: {e}")
    return alt, neu


def mehrfach_twist_fids(state, laser_fids: set) -> set[int] | None:
    """fids ANDERER gepatchter Geraete (nicht ``laser_fids``) mit mindestens
    zwei ``laser_twist``-Kanaelen (L2600, SH-LASER3W-Kopie im Altstand).
    ``None`` = nicht bestimmbar (dann gilt: jedes Ziel koennte betroffen sein)."""
    try:
        from src.core.app_state import get_channels_for_patched
        out: set[int] = set()
        for f in state.get_patched_fixtures():
            fid = int(getattr(f, "fid"))
            if fid in laser_fids:
                continue
            n = sum(1 for c in get_channels_for_patched(f)
                    if getattr(c, "attribute", None) == _TWIST)
            if n >= 2:
                out.add(fid)
        return out
    except Exception:
        return None


def _umbenennen(a: str, alt_show: bool, andere: bool) -> tuple[str | None, bool]:
    """Neuer Name fuer ein Einzelziel ``laser_twist#N`` (oder ``None`` =
    bleibt). Zweiter Wert: mehrdeutig/nicht umsetzbar (fuer die Meldung)."""
    if a == "laser_twist#3":
        return "laser_twist_y#1", False
    if a == "laser_twist#2":
        return (None, True) if andere else ("laser_twist#1", False)
    if a == "laser_twist#1":
        if alt_show and not andere:
            return _TWIST_Y, False
        return None, True
    return None, False


def _fids(werte) -> set[int]:
    out: set[int] = set()
    for x in werte or ():
        try:
            out.add(int(x))
        except (TypeError, ValueError):
            pass
    return out


def funktionen_nachziehen(fm, laser_fids: set, alt_show: bool,
                          andere_fids: set | None) -> tuple[int, int]:
    """Effekte und Kanal-Kopplungen der geladenen Funktionen umsetzen.
    Rueckgabe ``(umgesetzt, offen)``."""
    umgesetzt = offen = 0
    if fm is None or not laser_fids:
        return 0, 0
    try:
        funktionen = list(fm.all())
    except Exception:
        try:
            funktionen = list(getattr(fm, "_functions", {}).values())
        except Exception:
            return 0, 0
    for f in funktionen:
        try:
            if getattr(f, "is_layered_effect", False):
                if not (_fids(getattr(f, "fixture_ids", ())) & laser_fids):
                    continue
                zz = getattr(f, "zusatz_ziele", None)
                if not isinstance(zz, list):
                    continue
                if f.target_attribute == _TWIST and _TWIST_Y not in zz:
                    if alt_show:
                        zz.append(_TWIST_Y)
                        umgesetzt += 1
                    else:
                        offen += 1
                continue
            if getattr(getattr(f, "function_type", None), "value", "") \
                    != "MappedChannelChange":
                continue
            ziele = _fids(getattr(f, "fids", ()))
            if not (ziele & laser_fids):
                continue
            regeln = list(getattr(f, "rules", []) or [])
            if any(_ist_neu(getattr(r, "target", "")) for r in regeln):
                continue          # schon im LAS-28-Stand (idempotent)
            andere = andere_fids is None or bool(ziele & andere_fids)
            neu_regeln = []
            for r in regeln:
                neu_regeln.append(r)
                if getattr(r, "mode", "value") != "value":
                    continue
                t = getattr(r, "target", "")
                if t == _TWIST:
                    if alt_show:
                        from dataclasses import replace
                        neu_regeln.append(replace(r, target=_TWIST_Y))
                        umgesetzt += 1
                    else:
                        offen += 1
                    continue
                neu_t, unklar = _umbenennen(t, alt_show, andere)
                if neu_t is not None:
                    r.target = neu_t
                    umgesetzt += 1
                elif unklar:
                    offen += 1
            f.rules = neu_regeln
        except Exception as e:
            print(f"[las28_ziele] function migration failed: {e}")
    return umgesetzt, offen


def vc_nachziehen(vc_layout, alt_show: bool, andere: bool) -> tuple[int, int]:
    """VC-Fader-Bindungen (``programmer_attr``) im ROHEN Layout umsetzen.
    ``andere``: ein anderes Geraet mit mehreren ``laser_twist`` ist gepatcht
    (ein Fader trifft je nach Reichweite beliebige Geraete). Rueckgabe
    ``(umgesetzt, offen)``."""
    umgesetzt = offen = 0
    try:
        regler = list(_vc_regler(vc_layout))
    except Exception:
        return 0, 0
    for w in regler:
        try:
            a = w.get("programmer_attr")
            zz = w.get("programmer_attr_zusatz")
            if zz is not None and not isinstance(zz, list):
                continue
            if any(_ist_neu(x) for x in (zz or [])):
                continue          # schon umgesetzt (idempotent)
            if a == _TWIST:
                if alt_show:
                    w["programmer_attr_zusatz"] = list(zz or []) + [_TWIST_Y]
                    umgesetzt += 1
                else:
                    offen += 1
                continue
            neu_a, unklar = _umbenennen(a, alt_show, andere)
            if neu_a is not None:
                w["programmer_attr"] = neu_a
                umgesetzt += 1
            elif unklar:
                offen += 1
        except Exception as e:
            print(f"[las28_ziele] vc migration failed: {e}")
    return umgesetzt, offen
