"""TOOL-SMOKEDIM — „leuchtet" heisst nicht „das Geraet ist hell".

Am 2026-08-05 startete Robin in einer frisch gebauten Demo einen Muster-Effekt,
und **nichts leuchtete**. Dem Matrix-Effekt fehlte ``drive_intensity=True``: er
faerbte die Zonen, liess aber den Master-Dimmer auf CH1 unberuehrt. Kein Gate
hat das gemeldet, und zwar prinzipiell nicht — der Render-Smoke bildet
``lit = irgendein Kanal > 0``, und 144 Farbkanaele auf 255 erfuellen das
muehelos. **Der Smoke prueft, ob die Software rechnet — nicht, ob Licht
ankommt.**

Dieses Modul beantwortet die fehlende Frage: *hat das Geraet einen Master-Dimmer,
und wird der jemals hochgezogen?* Zwei Fassungen, dieselbe Aussage:

* :func:`dunkle_geraete` — **gemessen**, aus den Hoechstwerten einer echten
  Render-Probe (``render_diff(..., return_snapshot=True)``).
* :func:`statische_befunde` — **gelesen**, allein aus dem Show-Dict, fuer
  ``tools/lint_show.py``. Ohne Rendern, dafuer nur fuer den Fall, der den
  Anlass gab: ein Farbeffekt bespielt ein Geraet mit Master-Dimmer, ohne ihn
  hochzuziehen.

★ **Beide melden WARNUNGEN, keine Fehler.** Ein Geraet darf bewusst dunkel
bleiben (Blinder, Reserve, per Hand gefahrener Dimmer). Ein harter Fehler
wuerde Bestandsskripte brechen und waere obendrein oft falsch.

★ **Und beide schweigen lieber, als zu raten.** Ist das Profil in der
Bibliothek dieses Rechners unbekannt, haengt das Geraet in einem Universum,
ueber das die Probe nichts weiss, oder enthaelt die Show eine Funktionsart,
deren DMX-Wirkung statisch nicht ablesbar ist — dann gibt es keinen Befund.
Ein Gate, das alles beanstandet, ist so wertlos wie eines, das nichts findet.
"""
from __future__ import annotations

from .validate import Finding, WARNING

# Die Attribute, die „Helligkeit des ganzen Geraets" bedeuten. Deckungsgleich
# mit ``app_state._DIM_INTENSITY_ATTRS`` (= attr_groups "Intensity" ohne
# shutter/strobe) und mit dem Satz, den ``rgb_matrix.write`` selbst als Dimmer
# behandelt — genau diese Kanaele laesst ``drive_intensity=False`` liegen.
DIMMER_ATTRS = frozenset({"intensity", "dimmer", "master"})


# ── Kanal-Aufloesung (eine Quelle fuer beide Fassungen) ──────────────────────

def dimmer_kanaele(fixture) -> list[int]:
    """Absolute DMX-Kanaele (1..512) der Master-Dimmer EINES gepatchten Geraets.

    Leer heisst **„hier ist nichts zu behaupten"** — entweder hat das Geraet
    keinen Master-Dimmer (reiner Farb-PAR), oder die Bibliothek dieses Rechners
    kennt sein Profil gar nicht. Beide Faelle fuehren zum selben Verhalten
    (kein Befund), deshalb bleiben sie hier auch nicht kuenstlich getrennt.
    """
    try:
        from src.core.app_state import get_channels_for_patched
        chans = list(get_channels_for_patched(fixture) or ())
        adresse = int(getattr(fixture, "address", 1))
    except Exception:
        return []
    out: list[int] = []
    for ch in chans:
        if (getattr(ch, "attribute", "") or "").lower() not in DIMMER_ATTRS:
            continue
        try:
            addr = adresse + int(ch.channel_number) - 1
        except (TypeError, ValueError):
            continue
        if 1 <= addr <= 512:
            out.append(addr)
    return out


# ── Fassung 1: gemessen (Render-Probe) ───────────────────────────────────────

def dunkle_geraete(state, hoechstwerte: dict, universe: int = 1) -> list[str]:
    """Meldungen fuer Geraete, deren Master-Dimmer waehrend der Probe nie > 0 war.

    ``hoechstwerte`` ist ``ProbeSchnappschuss.hoechstwert`` — Kanal -> hoechster
    Wert ueber alle Frames der Probe. Geprueft wird absolut („kam Licht an"),
    nicht relativ zur Basis: das ist die Frage, die vor dem Geraet steht.

    Uebersprungen (kein Befund) werden Geraete
    * in einem anderen Universum als dem gemessenen — darueber sagt die Probe
      nichts, und ein Mehr-Universen-Rig wuerde sonst reihenweise Fehlalarme
      liefern (vgl. TOOL-RENDERUNI, wo genau diese Verwechslung schon einmal
      die Diagnose in die Irre schickte);
    * deren Dimmer-Kanaele gar nicht im Schnappschuss stehen (``channels=``
      hat den Ausschnitt eingegrenzt);
    * deren Profil hier unbekannt ist (:func:`dimmer_kanaele` liefert dann
      nichts — und „kenne ich nicht" ist keine Aussage ueber Helligkeit).
    """
    try:
        fixtures = list(state.get_patched_fixtures() or ())
    except Exception:
        return []
    meldungen: list[str] = []
    for fx in fixtures:
        try:
            if int(getattr(fx, "universe", 1)) != int(universe):
                continue
        except (TypeError, ValueError):
            continue
        kanaele = dimmer_kanaele(fx)
        if not kanaele:                       # kein Dimmer oder Profil unbekannt
            continue
        gemessen = [k for k in kanaele if k in hoechstwerte]
        if not gemessen:
            continue
        if any(int(hoechstwerte[k]) > 0 for k in gemessen):
            continue
        label = str(getattr(fx, "label", "") or f"fid {getattr(fx, 'fid', '?')}")
        meldungen.append(
            f"Geraet '{label}' (Universum {universe}, Kanal "
            f"{', '.join(str(k) for k in gemessen)}) hat einen Master-Dimmer, "
            f"den kein gepruefter Effekt hochzieht — die Show bleibt am Geraet "
            f"dunkel. Bei einem Farbeffekt fehlt meist 'drive_intensity=True'.")
    return meldungen


# ── Fassung 2: statisch (Show-Dict, ohne Rendern) ────────────────────────────

# Funktionsarten, deren Wirkung auf einen Dimmer-Kanal aus dem Dict ablesbar
# ist. Alles andere (Script, Collection, Show, Audio, MappedChannelChange,
# Carousel/LayeredEffect …) kann Kanaele auf Wegen setzen, die hier nicht
# nachvollziehbar sind -> dann schweigt die Pruefung ganz.
_LESBARE_TYPEN = frozenset({"Scene", "Chaser", "Sequence", "RGBMatrix", "EFX"})

# Regler-Betriebsarten, die einen Kanal von 0 HOCHziehen koennen. GrandMaster,
# GroupDimmer und FeatureDimmer skalieren nur (multiplikativ) — sie machen aus
# einem dunklen Geraet kein helles und unterdruecken die Warnung deshalb nicht.
_HEBENDE_REGLER = frozenset({"Level", "Submaster", "Programmer"})


def _funktionen(show: dict) -> list[dict]:
    block = show.get("functions")
    if isinstance(block, dict):
        block = block.get("functions", []) or []
    if not isinstance(block, list):
        return []
    return [f for f in block if isinstance(f, dict)]


def _widgets(show: dict) -> list[dict]:
    vc = show.get("virtual_console")
    if not isinstance(vc, dict):
        return []
    ws = vc.get("widgets", []) or []
    return [w for w in ws if isinstance(w, dict)] if isinstance(ws, list) else []


def _zahl(x, standard=0):
    try:
        return int(x)
    except (TypeError, ValueError):
        return standard


def _matrix_fids(fd: dict) -> set[int]:
    """Die fids, die diese Matrix bespielt. ``fixture_grid`` ist eine FLACHE
    row-major-Liste und darf ``None``-Luecken enthalten (rgb_matrix.py:440)."""
    fids = {_zahl(x, -1) for x in (fd.get("fixture_grid") or []) if x is not None}
    fids.discard(-1)
    return fids


def _treibt_dimmer(fd: dict, fid: int, offsets: set[int]) -> bool:
    """Zieht diese EINE Funktion den Dimmer von ``fid`` hoch?

    ``offsets`` sind die 1-basierten Kanal-Offsets der Dimmer INNERHALB des
    Geraets (so speichert die Szene ihre Werte).
    """
    typ = fd.get("type")
    if typ == "Scene":
        for sv in (fd.get("values") or []):
            if not isinstance(sv, dict):
                continue
            if _zahl(sv.get("fid"), -1) == fid and _zahl(sv.get("ch"), -1) in offsets \
                    and _zahl(sv.get("val")) > 0:
                return True
        return False
    if typ == "Sequence":
        for step in (fd.get("steps") or []):
            werte = (step or {}).get("values") if isinstance(step, dict) else None
            if not isinstance(werte, dict):
                continue
            attrs = werte.get(str(fid)) or werte.get(fid)
            if not isinstance(attrs, dict):
                continue
            for attr, val in attrs.items():
                if str(attr).split("#", 1)[0].lower() in DIMMER_ATTRS \
                        and _zahl(val) > 0:
                    return True
        return False
    if typ == "RGBMatrix":
        if fid not in _matrix_fids(fd):
            return False
        # Style "Dimmer" schreibt ausschliesslich auf die Dimmer-Kanaele
        # (rgb_matrix.write), unabhaengig von drive_intensity. RGB/RGBW nur mit
        # drive_intensity — genau der Schalter, der am 2026-08-05 fehlte.
        if str(fd.get("style", "RGB")) == "Dimmer":
            return True
        return bool(fd.get("drive_intensity", True))
    if typ == "EFX":
        # Nur die echte Pan/Tilt-EFX (Diskriminator motion/speed_hz) oeffnet mit
        # ``open_beam`` Dimmer und Shutter (efx.write).
        if not (bool(fd.get("motion")) or "speed_hz" in fd):
            return False
        if not fd.get("open_beam"):
            return False
        for f in (fd.get("fixtures") or []):
            if isinstance(f, dict) and _zahl(f.get("fid"), -1) == fid:
                return True
        return False
    # Chaser: schreibt selbst kein DMX, er startet seine Schritt-Funktionen —
    # und die stehen als eigene Eintraege in derselben Liste.
    return False


def statische_befunde(show: dict) -> list[Finding]:
    """Ohne Rendern: Geraete, die ein FARBEFFEKT bespielt, ohne ihren
    Master-Dimmer hochzuziehen.

    ★ Bewusst enger als die gemessene Fassung. Ein blosses „dieses gepatchte
    Geraet kommt in keiner Funktion vor" waere in fast jeder Show wahr
    (Reserve-Geraete, per Hand gefahrene Kanaele) und damit ein Dauer-Fehlalarm.
    Gemeldet wird nur die Konstellation, die den Anlass gab: eine Matrix faerbt
    das Geraet, sein Master-Dimmer bleibt liegen, und **keine andere Funktion**
    der Show zieht ihn hoch.

    Schweigt vollstaendig, wenn die Show eine Funktionsart enthaelt, deren
    DMX-Wirkung statisch nicht ablesbar ist, oder einen Regler, der Kanaele von
    Hand hochzieht — dann kann die Show hell sein, ohne dass man es hier sieht.
    """
    patch = show.get("patch")
    if not isinstance(patch, list):
        return []
    funcs = _funktionen(show)
    if any(f.get("type") not in _LESBARE_TYPEN for f in funcs):
        return []
    for w in _widgets(show):
        if w.get("type") == "VCSlider" and str(w.get("mode", "")) in _HEBENDE_REGLER:
            return []

    from types import SimpleNamespace
    befunde: list[Finding] = []
    for i, pf in enumerate(patch):
        if not isinstance(pf, dict):
            continue
        fid = _zahl(pf.get("fid"), -1)
        if fid < 0:
            continue
        # Das gepatchte Geraet nur so weit nachbilden, wie die Kanal-Aufloesung
        # es liest — dieselbe Funktion wie im Live-Pfad, kein zweiter Nachbau.
        fake = SimpleNamespace(
            fixture_profile_id=_zahl(pf.get("fixture_profile_id"), 0),
            mode_name=str(pf.get("mode_name") or ""),
            channel_count=_zahl(pf.get("channel_count"), 1),
            address=_zahl(pf.get("address"), 1),
            spider_dual_tilt=bool(pf.get("spider_dual_tilt", False)))
        absolut = dimmer_kanaele(fake)
        if not absolut:
            continue
        offsets = {k - fake.address + 1 for k in absolut}
        faerber = [f for f in funcs
                   if f.get("type") == "RGBMatrix" and fid in _matrix_fids(f)]
        if not faerber:
            continue
        if any(_treibt_dimmer(f, fid, offsets) for f in funcs):
            continue
        # Ein Basiswert auf dem Dimmer haelt das Geraet ohne jede Funktion hell.
        if _basiswert_auf_dimmer(show, fid):
            continue
        label = str(pf.get("label") or f"fid {fid}")
        namen = ", ".join(f"'{f.get('name', '?')}'" for f in faerber)
        befunde.append(Finding(
            WARNING, "DIMMER-DUNKEL", f"patch[{i}] '{label}'",
            f"hat einen Master-Dimmer (Kanal "
            f"{', '.join(str(k) for k in absolut)}), den kein Effekt hochzieht "
            f"— {namen} faerbt das Geraet, die Show bleibt daran trotzdem "
            f"dunkel. Fehlt 'drive_intensity=True'?",
            "rgb_matrix.py:867-869 (Dimmer-Kanal wird uebersprungen)"))
    return befunde


def befunde_lshow(path: str) -> list[Finding]:
    """:func:`statische_befunde` fuer eine ``.lshow``/``show.json``-Datei.

    Ein Fehler beim Lesen ist hier KEIN Befund: ``validate_lshow`` laeuft im
    Linter vorher ueber dieselbe Datei und meldet das bereits — zweimal
    dasselbe zu melden macht die Ausgabe nur unleserlich.
    """
    try:
        from .validate import _load_show_json
        return statische_befunde(_load_show_json(path))
    except Exception:
        return []


def _basiswert_auf_dimmer(show: dict, fid: int) -> bool:
    """Haelt ein gespeicherter Basiswert/Programmer-Wert den Dimmer oben?

    ``base_levels``/``programmer`` sind ``{fid: {attribut: wert}}`` — sie wirken
    ohne jede laufende Funktion. Ohne diese Ausnahme bekaeme eine Show, die den
    Dimmer bewusst fest auf 255 legt, eine Warnung fuer etwas Richtiges.
    """
    for block in ("base_levels", "programmer"):
        werte = show.get(block)
        if not isinstance(werte, dict):
            continue
        attrs = werte.get(str(fid)) or werte.get(fid)
        if not isinstance(attrs, dict):
            continue
        for attr, val in attrs.items():
            if str(attr).split("#", 1)[0].lower() in DIMMER_ATTRS and _zahl(val) > 0:
                return True
    return False
