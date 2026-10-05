"""VisualizerService — EIN page-freier Kern fuer Takt, Dirty-Diff und

Serialisierung des 3D-Visualizers (VIZ-12).

Design: ``docs/VIZ12_SERVICE_DESIGN.md``. Kernidee: heute baut JEDES
Render-Target (Fenster + Live-View-Spiegel) seinen eigenen ``QTimer(33ms)``,
sein eigenes State-Subscribe und serialisiert bei JEDEM Tick ALLE Fixtures neu
— unabhaengig davon, ob sich etwas geaendert hat. Der Service ersetzt das durch
EINEN Takt, EIN State-Subscribe und ein Dirty-Diff pro Fixture: nur GEAENDERTE
Fixtures werden pro Tick serialisiert und nur an AKTIVE Targets gepusht.

Kritische Invarianten (siehe CLAUDE.md / Design-Dokument):
  1. Der Service arbeitet AUSSCHLIESSLICH ueber die 5 dict-only Legacy-State-
     Felder (``visualizer_positions`` etc. via ``AppState``) — NIE ueber
     ``state._scene`` direkt. Tests duerfen den State per ``SimpleNamespace``
     faken.
  2. Pro-Target-Zustand (Reload-Token, Echo-Guard, RenderCrashGuard) gehoert
     NICHT hierher — der Service kennt nur ``needs_full`` (ob ein Target beim
     naechsten Tick den vollen Bestand statt nur das Diff braucht).
  3. Der Timer laeuft HART nur, wenn mindestens ein Target aktiv ist
     (Orchestrator-Entscheidung 2) — 0 aktive Targets stoppen ihn sofort.

Dieser Schritt (Schritt 1) haengt den Service NOCH NICHT an echte Fenster/Views
an — ``VisualizerTarget`` ist ein einfacher Emit-Empfaenger (Duck-Type: braucht
nur ``emit_batch(json_str)``); Fenster/View-Anbindung folgt in einem
Folgeschritt.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional


class VisualizerTarget:
    """Duenner Handle fuer ein Render-Ziel (Fenster oder Live-View-Spiegel).

    Der Service haelt pro Target nur, was er fuer Takt-Gating und Dirty-Diff
    braucht: ob es aktiv ist (sichtbar/push-relevant) und ob es beim naechsten
    Tick den vollen Bestand statt nur das Diff braucht. Die eigentliche
    Zustellung (``emit_batch``) ist absichtlich ein einfacher Callback/Duck-
    Type-Slot — in Schritt 1 ein Stub, spaeter die echte Bridge-Signal-Emit.

    Pro-Target-Zustand wie Reload-Token/Echo-Guard/RenderCrashGuard gehoert
    NICHT hierher (bleibt in der jeweiligen Bridge/im jeweiligen Fenster).

    ``on_reset_interaction`` (Schritt 5, optional): Callback ohne Argumente,
    den der Besitzer (Fenster/View) registrieren kann, damit
    ``VisualizerService.reset_interaction_state()`` pro Target aufraeumen
    kann (stop_trace + Reload-Guard-Reset) — bleibt bewusst ein duck-typed
    Slot wie ``emit_batch``, der Service kennt den Bridge-Typ nicht.
    ``on_reload`` (Schritt 5, optional): Callback ohne Argumente, den
    ``VisualizerService.reload_all_targets()`` pro Target aufruft, um die
    Page mit Cache-Buster neu zu laden (der eigentliche ``load_stage_html``-
    Aufruf bleibt Sache des Targets/Fensters, s. Design (b) Punkt 3).

    ``emit_payloads`` (VIZ-71, optional): strukturierter Empfaenger
    ``(payloads: list[dict], full: bool, seq: int)``. Ist er gesetzt, ruft der
    Tick IHN statt ``emit_batch`` — ohne den Umweg ueber einen JSON-String, den
    der Push-Kanal (``dmx_push.DmxPushChannel``) sonst wieder zerlegen muesste,
    um je Geraet zusammenzufuehren. Die Payload-Dicts sind GETEILT (Service-
    Cache und alle Targets) und duerfen vom Empfaenger nicht veraendert werden.

    ``tick_ms`` (VIZ-71): gewuenschter Takt dieses Ziels (Qualitaetsstufe:
    Niedrig 15 Hz, Hoch 30 Hz, Maximal 44 Hz). Der Service-Timer laeuft im
    kleinsten Takt aller AKTIVEN Ziele; ein langsameres Ziel drosselt sein
    Push-Kanal selbst."""

    def __init__(self, name: str, emit_batch: Callable[[str], None],
                 on_reset_interaction: Optional[Callable[[], None]] = None,
                 on_reload: Optional[Callable[[], None]] = None,
                 emit_payloads: Optional[Callable[[list, bool, int], None]] = None,
                 tick_ms: Optional[int] = None):
        self.name = name
        self.emit_batch = emit_batch
        self.emit_payloads = emit_payloads
        self.on_reset_interaction = on_reset_interaction
        self.on_reload = on_reload
        self.active: bool = False
        self.needs_full: bool = True
        self.tick_ms: int = int(tick_ms or VisualizerService.TICK_MS)


def _has_own_color(attrs: dict[str, int], suffix: str = "") -> bool:
    """Traegt dieser Kopf/dieses Geraet eigene Farbkanaele? Entscheidet, ob die
    Farbe aus den eigenen Werten kommt oder vom Geraet geerbt wird."""
    return any(f"{k}{suffix}" in attrs
               for k in ("color_r", "color_g", "color_b", "color_w",
                         "color_a", "color_uv"))


# VIZ-77: Gobo-Stil und Prisma-Facetten haengen NUR von der Kanalliste (Ranges
# des Profils) und dem einen DMX-Wert ab — die Range-Suche lief aber bei jedem
# Neubau ueber alle Kanaele und Ranges (gemessen ~25 % des Payload-Baus bei
# Mega Arena). Gemerkt je Kanallisten-OBJEKT: ein Profil-Edit leert den
# Kanal-Cache (``clear_channel_cache``) und liefert eine neue Liste, deren
# Merkzettel leer beginnt. Die Liste selbst wird mitgehalten, damit ihre
# ``id`` nicht an ein anderes Objekt weiterwandert.
_KANAL_MEMO: dict[int, tuple] = {}
_KANAL_MEMO_MAX = 512


def _kanal_memo(channels) -> dict | None:
    if not channels:
        return None
    e = _KANAL_MEMO.get(id(channels))
    if e is not None and e[0] is channels:
        return e[1]
    if len(_KANAL_MEMO) >= _KANAL_MEMO_MAX:
        _KANAL_MEMO.clear()
    d: dict = {}
    _KANAL_MEMO[id(channels)] = (channels, d)
    return d


def _gobo_style_gemerkt(attrs: dict, channels) -> str | None:
    memo = _kanal_memo(channels)
    if memo is None:
        return _gobo_style(attrs, channels)
    k = ("gobo", attrs.get("gobo_wheel"), attrs.get("gobo"))
    try:
        return memo[k]
    except KeyError:
        v = memo[k] = _gobo_style(attrs, channels)
        return v
    except TypeError:                      # unhashbarer Wert (Attrappe)
        return _gobo_style(attrs, channels)


def _prism_facets_gemerkt(attrs: dict, channels) -> int | None:
    memo = _kanal_memo(channels)
    if memo is None:
        return _prism_facets(attrs, channels)
    k = ("prism", attrs.get("prism"))
    try:
        return memo[k]
    except KeyError:
        v = memo[k] = _prism_facets(attrs, channels)
        return v
    except TypeError:
        return _prism_facets(attrs, channels)


def _gobo_style(attrs: dict, channels) -> str | None:
    """Muster-Stil des gerade gewaehlten Gobos ("" = offen/kein Muster).

    ``None`` heisst „dieses Geraet hat gar kein Gobo-Rad" — dann steht auch
    nichts im Payload, und JS laesst den Bodenfleck in Ruhe (dieselbe Regel wie
    bei Zoom/Iris: kein erfundener Default).
    """
    if not channels:
        return None
    wert = None
    kanal = None
    for ch in channels:
        a = (getattr(ch, "attribute", "") or "").lower()
        if a in ("gobo_wheel", "gobo"):
            kanal = ch
            wert = attrs.get(a)
            break
    if kanal is None or wert is None:
        return None
    try:
        from src.ui.widgets.gobo_icons import gobo_style_for
    except Exception:
        return None
    for rg in (getattr(kanal, "ranges", None) or ()):
        try:
            if int(rg.range_from) <= int(wert) <= int(rg.range_to):
                return gobo_style_for(getattr(rg, "name", "") or "")
        except (TypeError, ValueError):
            continue
    return ""

# VIZ-PRISMA-3D: wie viele Strahlen macht das Prisma gerade?
#
# Gleiche Bauart wie ``_gobo_style`` darueber und aus demselben Grund: die
# Zuordnung DMX-Wert -> Range -> Bedeutung lebt im Profil, also wird sie HIER
# aufgeloest und nur die fertige ZAHL wandert nach JS. Ginge der Rohwert
# hinueber, braeuchte JS die Profil-Ranges — eine zweite Quelle fuer dieselbe
# Zuordnung.
#
# ★ Die Range-Namen sind ZWEISPRACHIG, und das ist keine Kleinigkeit:
# ausgezaehlt ueber die gesamte Library schreiben die eingebauten Profile
# deutsch ("6-fach Prisma"), die importierten QXF-Profile englisch
# ("3 Facet Prism", "8-facet prism"). Ein Muster fuer nur eine Sprache haette
# 93 % der Library stillschweigend als "kein Prisma" behandelt.
_PRISM_FACETTEN = re.compile(r"(\d+)\s*[-\s]?\s*(?:fach|facet)", re.IGNORECASE)
# "Aus"-Ranges heissen quer durch die Library so:
_PRISM_AUS = re.compile(r"\b(?:aus|off|open|offen|kein|no|none|blank)\b",
                        re.IGNORECASE)
# Fallback, wenn die Range zwar ein Prisma meint, aber keine Zahl nennt.
# AUSGEZAEHLT (2026-08-01), nicht geraten: von 810 Prisma-Ranges der Library
# nennen nur 49 eine Facettenzahl — und unter denen ist 3 mit 25 von 49 die
# mit Abstand haeufigste (dann 4x8, 8x4, 6x6, 5x3). Die uebrigen 761 sagen
# schlicht "Prism". Drei Facetten sind damit die beste verfuegbare Aussage
# der Daten selbst, nach demselben Verfahren wie der Fokus-Default 128.
PRISM_FACETTEN_FALLBACK = 3


def _prism_facets(attrs: dict, channels) -> int | None:
    """Facettenzahl des aktiven Prismas — ``0`` = aus, ``None`` = kein Prisma.

    ``None`` heisst "dieses Geraet hat gar keinen Prisma-Kanal": dann steht
    nichts im Payload und JS laesst den Strahl in Ruhe. Genau wie bei
    Zoom/Iris/Gobo bekommt ein Geraet ohne den Kanal KEINEN erfundenen Default.
    """
    if not channels:
        return None
    kanal = None
    wert = None
    for ch in channels:
        # Bewusst NUR "prism", nicht "prism_rotation": die Drehung sagt nichts
        # ueber die Facettenzahl und wuerde als eigener Kanal danebenliegen.
        if (getattr(ch, "attribute", "") or "").lower() == "prism":
            kanal = ch
            wert = attrs.get("prism")
            break
    if kanal is None or wert is None:
        return None
    try:
        wert = int(wert)
    except (TypeError, ValueError):
        return None
    for rg in (getattr(kanal, "ranges", None) or ()):
        try:
            if not (int(rg.range_from) <= wert <= int(rg.range_to)):
                continue
        except (TypeError, ValueError):
            continue
        name = getattr(rg, "name", "") or ""
        if _PRISM_AUS.search(name):
            return 0
        m = _PRISM_FACETTEN.search(name)
        if m:
            try:
                n = int(m.group(1))
            except ValueError:
                return PRISM_FACETTEN_FALLBACK
            # Unplausible Zahlen aus Namen wie "Prisma-Makros 1-16" nicht als
            # Facetten durchreichen — 16 Kegel je Geraet waeren ein echter
            # Renderschaden, und gemeint ist dort ohnehin eine Makro-Nummer.
            return n if 2 <= n <= 12 else PRISM_FACETTEN_FALLBACK
        return PRISM_FACETTEN_FALLBACK
    # Keine passende Range (oder gar keine Ranges): dann entscheidet der Wert.
    # Default 0 = aus ist in der Library einhellig (4/4 Profile mit Prisma).
    return 0 if wert <= 0 else PRISM_FACETTEN_FALLBACK


# ── VIZ-79: Laser-Block des Payloads ─────────────────────────────────────────
# Der 3D-Viewer bildet einen Laser als Strahlen-Rig ab (scene_src/fixtures/
# laser.js). Was die Profile an Laser-Kanaelen haben, wird HIER in wenige,
# normierte Zahlen uebersetzt — JS kennt keine Ranges, und die Bedeutung eines
# Werts haengt am Profil: beim L2600 ist laser_x 0-127 eine feste Position und
# 128-255 eine Bewegung, die das Geraet selbst faehrt; beim FB4 ist der ganze
# Bereich 0-255 Position (128 = Mitte).
#
# Regel: der ERSTE Range eines Kanals ist sein statischer Bereich (Position,
# Groesse, Winkel), alles darueber ist Eigenbewegung des Geraets. Ein Kanal
# ohne Ranges gilt ueber 0-255 als statisch. Farbe und Helligkeit kommen wie
# bei jedem Geraet aus r/g/b/intensity — der Block traegt keine Helligkeit.
_LASER_FORMEN = 4   # 0 Faecher · 1 Einzelstrahl · 2 Strahlenkranz · 3 Flaeche


def _laser_statisch(attrs: dict, channels, attr: str):
    """``(anteil 0..1, dynamisch)`` eines Laser-Kanals oder ``None``, wenn das
    Geraet ihn nicht hat."""
    from src.core.color_utils import _chan_by_attr
    if attr not in attrs:
        return None
    v = max(0, min(255, int(attrs.get(attr) or 0)))
    lo, hi = 0, 255
    ch = _chan_by_attr(channels, attr)
    rgs = []
    for rg in (getattr(ch, "ranges", None) or ()) if ch is not None else ():
        try:
            rgs.append((int(rg.range_from), int(rg.range_to)))
        except (TypeError, ValueError):
            continue
    if rgs:
        lo, hi = min(rgs)
    if v > hi:
        return 0.5, True
    return (v - lo) / max(1, hi - lo), False


def _laser_payload(fixture, attrs: dict, channels) -> dict | None:
    """Normierter Laser-Block fuer den 3D-Viewer — ``None`` fuer Nicht-Laser.

    Ein Geraet zaehlt als Laser, wenn es als ``laser`` gepatcht ist oder
    ``laser_*``-Kanaele hat. Position kommt aus ``laser_x``/``laser_y``, sonst
    aus Pan/Tilt; Groesse aus ``laser_zoom_x``/``laser_zoom_y``, sonst ``zoom``;
    der Winkel aus ``gobo_rotation``. Das Muster wird nur GROB abgebildet (vier
    Formen aus Musterbank und Musterauswahl): die echten Muster sind
    Vektorgrafiken im Geraet, die der Viewer nicht kennt."""
    ist_laser = (getattr(fixture, "fixture_type", "") == "laser"
                 or any(k.startswith("laser_") for k in attrs))
    if not ist_laser:
        return None
    out: dict[str, object] = {}
    bewegt_selbst = False
    # Pan/Tilt sind nur dann eine POSITION, wenn das Geraet eine echte Achse hat
    # — beide Kanaele. Ein einzelner „pan" ist bei Party-Lasern ein Drehmotor
    # (PARTYLASER: „Motor"); als Position gelesen schwenkte sein Null-Frame den
    # Faecher ganz nach links (Review VIZ-79, M2).
    echte_achse = "pan" in attrs and "tilt" in attrs
    for achse, quellen in (("x", ("laser_x", "pan")), ("y", ("laser_y", "tilt"))):
        for q in quellen:
            if q in ("pan", "tilt") and not echte_achse:
                continue
            r = _laser_statisch(attrs, channels, q)
            if r is None:
                continue
            anteil, dyn = r
            out[achse] = round(anteil * 2 - 1, 4)
            if dyn:
                out["d" + achse] = True
                bewegt_selbst = True
            break
    for achse, quellen in (("sx", ("laser_zoom_x", "zoom")),
                           ("sy", ("laser_zoom_y", "zoom"))):
        for q in quellen:
            r = _laser_statisch(attrs, channels, q)
            if r is None:
                continue
            anteil, dyn = r
            out[achse] = round(anteil, 4)
            if dyn:
                out["dz"] = True
                bewegt_selbst = True
            break
    r = _laser_statisch(attrs, channels, "gobo_rotation")
    if r is not None:
        out["rot"] = round(r[0], 4)
        if r[1]:
            out["dr"] = True
            bewegt_selbst = True
    bank = int(attrs.get("laser_bank") or 0)
    muster = int(attrs.get("gobo_wheel") or 0) if "laser_bank" in attrs else 0
    out["form"] = (bank // 16 + muster) % _LASER_FORMEN
    motor = None
    if not echte_achse and "pan" in attrs and "laser_x" not in attrs:
        # Drehmotor: 0 = steht, mehr = dreht schneller -> Rollen um die Strahlachse.
        motor = max(0, min(255, int(attrs.get("pan") or 0))) / 255
        if motor > 0:
            out["dr"] = True
            bewegt_selbst = True
            if "speed" not in attrs:
                out["tempo"] = round(motor, 4)
    if "speed" in attrs:
        tempo = max(0, min(255, int(attrs.get("speed") or 0))) / 255
        out["tempo"] = round(tempo, 4)
        # Kein Positionskanal (L2600 im 6-Kanal-Modus): das Geraet faehrt sein
        # Programm selbst — mit Geschwindigkeit > 0 („0 = keine Bewegung“)
        # schwenkt der Faecher langsam.
        if not bewegt_selbst and "x" not in out and tempo > 0:
            out["dx"] = True
    return out


def _mit_fein(pt: dict, achse: str, default: int = 128, sfx: str = ""):
    """Grobwert + ``<achse>_fine``/256 (VIZ-61); ohne oder mit 0 Fein der Grobwert.
    ``sfx`` = Kopf-Suffix (``"#1"`` …) fuer ``pan#1``/``pan_fine#1`` (VIZ-63)."""
    grob = pt.get(f"{achse}{sfx}", default)
    fein = pt.get(f"{achse}_fine{sfx}", 0)
    try:
        fein = int(fein)
    except (TypeError, ValueError):
        return grob
    return grob + fein / 256.0 if fein else grob


def _build_fixture_payload(fixture, attrs: dict[str, int],
                           channels=None) -> dict[str, object]:
    """Baut den Pro-Fixture-Payload (inkl. Spider-/Bar-``heads``-Array). Seit
    VIZ-13 3c-4 die EINZIGE Quelle dieser Logik — die frueher parallel gepflegte
    ``VisualizerBridge.push_dmx_update`` wurde entfernt. Der Service verpackt das
    Ergebnis pro Tick als ein Batch-Array (``dmxBatch``) statt pro Fixture.

    ``channels`` (optional) sind die Kanal-Objekte des Geraets
    (``get_channels_for_patched``). Sie werden NUR fuer Farbrad-Slots und die
    Shutter-Semantik gebraucht (``ChannelRange.kind``); ohne sie bleibt die
    Ableitung auf den reinen Attribut-Werten und faellt konservativ zurueck —
    darum ist der Parameter optional (Alt-Aufrufer/Tests bleiben gueltig).

    Farbe/Helligkeit kommen aus ``color_utils.visual_rgb``/``visual_intensity``
    statt wie frueher aus ``attrs.get("color_r", 0)`` + ``attrs.get("intensity",
    255)``: Geraete ohne RGB-Kanaele (Dimmer-PAR, Strobe/Blinder, CMY- und
    Farbrad-Mover) wurden sonst SCHWARZ gerendert, Geraete ohne Dimmer-Kanal
    dauerhaft voll hell."""
    from src.core.app_state import unapply_pan_tilt_orientation
    from src.core.color_utils import visual_intensity, visual_rgb

    r, g, b = visual_rgb(attrs, channels)
    intensity = visual_intensity(attrs, channels)
    # VIZ-55: ``attrs`` kommt aus dem GESENDETEN DMX-Frame, traegt also bereits
    # invert/swap des Geraets. Die Winkelformel im JS (builders.js::applyPanTilt)
    # kennt diese Flags nicht — ohne Ruecknahme zeigte der Strahl im Bild
    # gespiegelt zu dem, was der echte Kopf tut. Nur Pan/Tilt betroffen; ohne
    # gesetzte Flag gibt die Funktion das Original unveraendert zurueck (kein
    # Overhead im Takt).
    pt = unapply_pan_tilt_orientation(fixture, attrs)
    # VIZ-61: der Feinkanal gehoert ins Bild. Bis 2026-09-28 trug der Payload nur
    # den Grobwert — eine reine Feinkorrektur (Zielen/Einmessen in 16 Bit) waere
    # am Geraet sichtbar und im 3D unsichtbar gewesen. ``pt`` hat invert/swap
    # schon zurueckgenommen, und zwar als 16-Bit-Paar; die JS-Winkelformel
    # (``builders.js::applyPanTilt``) rechnet ohnehin stufenlos. Fein = 0 laesst
    # den Wert als ganze Zahl stehen (byte-gleicher Payload, kein Diff im Takt).
    pan = _mit_fein(pt, "pan")
    tilt = _mit_fein(pt, "tilt")
    payload: dict[str, object] = {
        "fid": fixture.fid,
        "r": r,
        "g": g,
        "b": b,
        "intensity": intensity,
        "pan": pan,
        "tilt": tilt,
    }
    # VIZ-MH-OPTICS (David-Wunsch 2026-07-16): Optik-Attribute mitschicken.
    # Sie waren im Programmer schon steuerbar, kamen aber NIE im 3D an — der
    # Kegel hatte einen festen Winkel, ein Zoom-Zug hatte null Wirkung.
    # Nur senden, was das Geraet WIRKLICH hat: ein fehlender Schluessel heisst
    # JS-seitig "unveraendert", ein erfundener 128er-Default wuerde jeden
    # Scheinwerfer ohne Zoom auf halbe Weite stellen.
    for _opt in ("zoom", "iris", "focus", "frost"):
        if _opt in attrs:
            payload[_opt] = attrs[_opt]
    # VIZ-GOBO-3D (David-Wunsch 2026-07-16): welches Gobo steckt gerade drin?
    # Nicht der DMX-Wert wandert nach JS, sondern der ERKANNTE MUSTER-STIL —
    # die Zuordnung Wert -> Range-Name -> Muster ist datengetrieben und lebt
    # schon in gobo_icons (dieselbe Quelle wie die 2D-Kacheln im Programmer).
    # Waere der Rohwert gewandert, muesste JS die Ranges des Profils kennen.
    _gobo = _gobo_style_gemerkt(attrs, channels)
    if _gobo is not None:
        payload["gobo"] = _gobo
    # VIZ-PRISMA-3D: aus EINEM Strahl werden mehrere. Auch hier wandert die
    # fertige Facetten-ZAHL nach JS, nicht der Rohwert (Begruendung an
    # _prism_facets). Die Drehung dagegen ist ein reiner Winkel und geht roh
    # mit — dort gibt es keine Profil-Zuordnung aufzuloesen.
    # VIZ-79: Laser-Block (Position, Groesse, Muster, Eigenbewegung).
    _laser = _laser_payload(fixture, attrs, channels)
    if _laser is not None:
        payload["laser"] = _laser
    _prism = _prism_facets_gemerkt(attrs, channels)
    if _prism is not None:
        payload["prism"] = _prism
        if "prism_rotation" in attrs:
            payload["prism_rotation"] = attrs["prism_rotation"]
    # ── Mehrkopf (Spider UND Mover-/PAR-Bars): pro Kopf eigene Farbe/Pan/Tilt ──
    # Multi-Head-Konvention: Kopf 0 = "attr", Kopf N = "attr#N". FM-2: Kopfzahl aus
    # dem hoechsten vorkommenden #N-Index von color_r/pan/tilt ABGELEITET (nicht mehr
    # hart 2) -> beliebige N-Kopf-Bars (4er-Mover-Bar / 4er-PAR-Bar). Pro Kopf jetzt
    # AUCH ein "pan" (fuer echte Mover-Bars). Ein Spider (nur color_r#1/tilt#1) ->
    # head_count 2, byte-identisch zu vorher; JS-Spider-Render ignoriert h.pan.
    head_count = _multihead_count(attrs)
    if head_count >= 2:
        heads = []
        # VIZ-63: Pan/Tilt je Kopf aus ``pt`` (invert/swap zurueckgenommen, wie
        # fuer das Gesamtgeraet) und mit Feinkanal — bis 2026-09-29 kamen sie aus
        # den DRAHT-Werten ``attrs``: eine Mover-Bar mit ``invert_pan`` stand im
        # Bild spiegelverkehrt zum echten Geraet, obwohl ``unapply`` die Koepfe
        # seit OUT-55 laengst kann.
        tilt_keys = [""] + [f"#{h}" for h in range(1, head_count)]
        tilt_sources = [_mit_fein(pt, "tilt", sfx=k) for k in tilt_keys
                        if f"tilt{k}" in pt]
        # Spider-Sonderfall: zwei Tilts aus pan+tilt, wenn zu wenige echte Tilts da
        # sind (der Spider hat kein zweites Tilt-Attribut, nutzt pan als Bar-0-Tilt).
        if len(tilt_sources) < head_count and "pan" in pt:
            tilt_sources = [pan] + tilt_sources
        while len(tilt_sources) < head_count:
            tilt_sources.append(tilt_sources[-1] if tilt_sources else tilt)
        for h in range(head_count):
            sfx = "" if h == 0 else f"#{h}"
            hr = attrs.get(f"color_r{sfx}", 0)
            hg = attrs.get(f"color_g{sfx}", 0)
            hb = attrs.get(f"color_b{sfx}", 0)
            hw = attrs.get(f"color_w{sfx}", 0)
            if _has_own_color(attrs, sfx):
                # Dieselbe Ableitung wie fuer das ganze Geraet (inkl. Amber/UV),
                # statt die RGB(W)-Rechnung hier ein zweites Mal zu fuehren.
                hrgb = visual_rgb(attrs, channels, sfx)
            else:
                # Kopf ohne eigene Farbkanaele (Mover-Bar ohne Farbe, Kopf eines
                # CMY-/Farbrad-Geraets) erbt die Geraetefarbe — sonst blieben
                # seine Einzel-LEDs/Beams schwarz, waehrend das Geraet leuchtet.
                hrgb = (r, g, b)
                hr, hg, hb = hrgb
            heads.append({
                "r": hrgb[0],
                "g": hrgb[1],
                "b": hrgb[2],
                "cr": hr, "cg": hg, "cb": hb, "cw": hw,
                # FM-2: pro-Kopf-Pan (Mover-Bar); VIZ-63: Modellwert mit Fein
                "pan": _mit_fein(pt, "pan", sfx=sfx) if f"pan{sfx}" in pt else pan,
                "tilt": tilt_sources[h],
            })
        payload["heads"] = heads
    return payload


# FM-2: Kopfzahl aus dem hoechsten #N-Index der Multi-Head-Attribute (color_r/pan/
# tilt) ableiten. 0 relevante #N-Attribute -> 1 (kein heads-Array). Ein color_r#1
# (Spider) -> 2 (byte-identisch zum alten hart-kodierten head_count=2).
_MULTIHEAD_BASES = ("color_r", "pan", "tilt")


def _attr_layout(address: int, channels) -> tuple[tuple, int, int]:
    """VIZ-77: welche Frame-Bytes ein Geraet liest — ``((attr_key, index), …)``
    plus der Ausschnitt ``[lo, hi)``, den diese Indizes ueberspannen.

    Dieselbe Vergabe wie ``VisualizerService._collect_attrs`` (Kopf 0 =
    ``attr``, Kopf N = ``attr#N``; Kanaele ausserhalb 1..512 fallen weg) —
    beide nutzen diese Funktion, damit sie nicht auseinanderlaufen."""
    layout = []
    seen: dict[str, int] = {}
    for ch in channels:
        dmx_addr = address + ch.channel_number - 1
        if 1 <= dmx_addr <= 512:
            a = ch.attribute
            h = seen.get(a, 0)
            seen[a] = h + 1
            layout.append((a if h == 0 else f"{a}#{h}", dmx_addr - 1))
    if not layout:
        return (), 0, 0
    idx = [i for _k, i in layout]
    lo = min(idx)
    hi = max(idx) + 1
    return tuple((k, i - lo) for k, i in layout), lo, hi


# VIZ-77: diese State-Events aendern nachweislich KEINE Eingabe des Payloads.
# Der Programmer (und sein Verlauf) wirkt nur ueber den DMX-Frame, und genau
# der steckt Byte fuer Byte im Cache-Schluessel. Ein Fader- oder XY-Pad-Zug
# feuert ``programmer_changed`` bei jeder Bewegung — als Invalidierung haette
# er den Cache genau dann leergefegt, wenn er am meisten bringt. JEDES andere
# Event (auch ein kuenftiges, hier unbekanntes) leert den Cache: lieber einmal
# zu viel bauen als ein Geraeteattribut verpassen.
_PAYLOAD_NEUTRAL_EVENTS = frozenset({
    "programmer_changed", "programmer_verlauf_changed", "hinweis",
    "show_saved", "cue_recorded",
})


def _fixture_ident(fixture) -> tuple:
    """VIZ-77: alle Geraete-Felder, die der Payload liest — direkt oder ueber
    ``get_channels_for_patched`` (Profil/Modus/Kanalzahl/Spider) und
    ``unapply_pan_tilt_orientation`` (invert/swap). Steht als Teil des
    Cache-Schluessels da, damit eine Aenderung auch OHNE Event greift."""
    g = getattr
    return (g(fixture, "address", None), g(fixture, "universe", None),
            bool(g(fixture, "invert_pan", False)),
            bool(g(fixture, "invert_tilt", False)),
            bool(g(fixture, "swap_pan_tilt", False)),
            g(fixture, "fixture_profile_id", None), g(fixture, "mode_name", None),
            g(fixture, "channel_count", None),
            bool(g(fixture, "spider_dual_tilt", False)))


def _multihead_count(attrs: dict[str, int]) -> int:
    mx = 0
    for key in attrs:
        base, sep, idx = key.rpartition("#")
        if sep and base in _MULTIHEAD_BASES and idx.isdigit():
            n = int(idx)
            if n > mx:
                mx = n
    return mx + 1


class VisualizerService:
    """Page-freier Takt-/Dirty-Diff-/Serialisierungs-Kern (VIZ-12).

    Ein Service pro ``AppState`` (Singleton via ``get_visualizer_service``,
    siehe unten) — NICHT modul-global, damit Tests mit frischem State auch
    einen frischen Service bekommen (Orchestrator-Entscheidung 5).
    """

    TICK_MS = 33
    # VIZ-70: so viele Ticks am Stueck darf das Frame-Gate hoechstens
    # ueberspringen (30 x 33 ms ~ 1 s), danach wird trotzdem einmal gebaut.
    GATE_MAX_SKIPS = 30

    def __init__(self, state):
        self._state = state
        self._targets: list[VisualizerTarget] = []
        # Service-globaler Snapshot-Cache: {fid: payload_dict}. Wird pro Tick
        # gegen den frisch gebauten Payload verglichen (value-equality, nicht
        # Objekt-Identitaet) -> nur GEAENDERTE Fixtures wandern ins Batch-Array.
        self._last_payload: dict[int, dict[str, object]] = {}
        self._timer: Optional[Any] = None
        self._subscribed = False
        # VIZ-70 Frame-Gate: Signatur des letzten GEBAUTEN Ticks (siehe
        # ``_frame_signature``). Gleiche Signatur -> der Tick baut keinen
        # Snapshot. ``_state_rev`` zaehlt JEDES State-Event (Patch, Show-Load,
        # Programmer, …) — konservativ: lieber einmal zu viel bauen als ein
        # Geraete-Attribut (Nullpunkt, Bereich, Profil) verpassen, das sich
        # ohne DMX-Aenderung aendert. ``_gate_skips`` begrenzt das Ueberspringen
        # zusaetzlich auf ``GATE_MAX_SKIPS`` Ticks am Stueck (Sicherheitsnetz
        # fuer Aenderungen ganz ohne Event).
        self._gate_sig: Optional[tuple] = None
        self._gate_skips = 0
        self._state_rev = 0
        # VIZ-71: Sequenznummer je GEBAUTEM Tick. Der Push-Kanal reicht sie je
        # Eintrag an JS weiter; JS verwirft einen Eintrag, der aelter ist als
        # der zuletzt angewandte derselben fid. Noetig, solange Push und der
        # Poll-Rueckfall nebeneinander laufen: die Antworten reisen ueber zwei
        # verschiedene IPC-Wege und koennen sich ueberholen.
        self._seq = 0
        # VIZ-77 Payload-Cache je Geraet: {fid: (fixture, channels, ident,
        # layout, ausschnitt_bytes, payload)}. Ein Treffer verlangt dasselbe
        # Geraete-Objekt, dasselbe Kanal-Objekt (ein Profil-Edit leert den
        # Kanal-Cache und liefert eine NEUE Liste), dieselben Geraete-Felder
        # (``_fixture_ident``) und Byte-gleichen Ausschnitt des Display-Frames.
        # Geleert wird er bei jedem nicht-neutralen State-Event
        # (``_payload_rev``), spaetestens nach ``GATE_MAX_SKIPS`` Bauten und
        # bei jedem Bau, den nur das Sicherheitsnetz der Frame-Sperre erzwingt.
        self._payload_cache: dict[int, tuple] = {}
        self._payload_rev = 0
        # -1: der erste Bau gilt als voller Bau (Alter 0).
        self._payload_cache_rev = -1
        self._payload_cache_age = 0
        # Zaehler fuer Tests/Messung: Treffer und Neubauten des letzten Baus.
        self.payload_cache_stats = {"hits": 0, "builds": 0}

    # ── Timer-Lazy-Init (Qt-Objekt erst bei Bedarf, damit Tests ohne
    #    QApplication den Service instanzieren koennen) ─────────────────────
    def _timer_alive(self) -> bool:
        """Lebt die C++-Seite des Timers noch?

        Beim Beenden zerstoert Qt das C++-Objekt, waehrend der Python-Wrapper
        bestehen bleibt: ``self._timer is not None`` ist dann WAHR, aber jeder
        Zugriff wirft ``RuntimeError: Internal C++ object … already deleted``.
        Real passiert (crash.log 2026-07-21): ``QWidget.destroyed`` -> Lambda ->
        ``detach_target`` -> ``_update_timer_gate`` -> ``isActive()`` — also
        ausgerechnet auf dem Aufraeumpfad, auf dem niemand mit einer Exception
        rechnet. Ein toter Timer wird hier vergessen, damit die naechste
        Anforderung sauber einen neuen baut."""
        t = self._timer
        if t is None:
            return False
        try:
            t.isActive()
        except RuntimeError:
            self._timer = None
            return False
        return True

    def _ensure_timer(self):
        if self._timer_alive():
            return
        from PySide6.QtCore import QTimer
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)

    def _ensure_subscribed(self):
        if self._subscribed:
            return
        self._state.subscribe(self._on_state)
        self._subscribed = True

    # ── Target-Registrierung ─────────────────────────────────────────────────
    def attach_target(self, target: VisualizerTarget) -> None:
        """Neues Render-Ziel andocken. Braucht beim ersten Tick den vollen
        Bestand (Design-Risiko: frisch geoeffnetes Target darf bei statischer
        Szene nicht leer bleiben, da eine unveraenderte Szene sonst gar kein
        Batch mehr ausloest)."""
        if target not in self._targets:
            self._targets.append(target)
        target.needs_full = True
        self._ensure_subscribed()

    def detach_target(self, target: VisualizerTarget) -> None:
        if target in self._targets:
            self._targets.remove(target)
        self._update_timer_gate()

    def set_target_active(self, target: VisualizerTarget, active: bool) -> None:
        was_active = target.active
        target.active = active
        if active and not was_active:
            # Erneut aktiv gewordenes Target (z.B. nach hide/show) braucht
            # wieder den vollen Bestand -> siehe attach_target-Begruendung.
            target.needs_full = True
        self._update_timer_gate()

    def _tick_interval_ms(self) -> int:
        """VIZ-71: kleinster gewuenschter Takt aller AKTIVEN Ziele."""
        werte = [int(getattr(t, "tick_ms", self.TICK_MS) or self.TICK_MS)
                 for t in self._targets if t.active]
        return max(10, min(werte)) if werte else self.TICK_MS

    def set_target_tick_ms(self, target: VisualizerTarget, tick_ms: int) -> None:
        """VIZ-71: Takt eines Ziels aendern (Qualitaetsstufe gemeldet/gewechselt)
        und den laufenden Timer sofort nachziehen."""
        target.tick_ms = int(tick_ms)
        self._update_timer_gate()

    def _update_timer_gate(self) -> None:
        """Timer laeuft HART nur bei >=1 aktivem Target (Orchestrator-
        Entscheidung 2). Der State-Patch-Prune haengt NICHT am Timer, sondern
        am State-Subscribe (bleibt auch bei gestopptem Timer aktiv).

        VIZ-71: das Intervall folgt dem schnellsten aktiven Ziel (Maximal 44 Hz,
        Hoch 30 Hz, Niedrig 15 Hz)."""
        any_active = any(t.active for t in self._targets)
        if any_active:
            self._ensure_timer()
            soll = self._tick_interval_ms()
            if not self._timer.isActive():
                self._timer.start(soll)
            elif self._timer.interval() != soll:
                self._timer.setInterval(soll)
        else:
            if self._timer_alive() and self._timer.isActive():
                self._timer.stop()

    @property
    def timer_running(self) -> bool:
        return self._timer_alive() and self._timer.isActive()

    # ── Dirty-Diff + Batch-Payload-Bau ───────────────────────────────────────
    def _collect_attrs(self, fixture) -> dict[str, int]:
        """1:1 aus der heutigen ``_push_dmx_updates``-Schleife (Bridge/View)
        uebernommen: baut die rohen Attribut-Kanaele fuer EIN Fixture."""
        from src.core.app_state import get_channels_for_patched

        universe = self._state.universes[fixture.universe]
        # WYSIWYG: den GESENDETEN Output speisen (POST Grand-Master/Blackout), damit
        # der 3D-Visualizer den echten Output zeigt — bei Blackout also dunkel.
        # Fallback auf den Rohpuffer (get_channel), solange noch kein Frame gesendet
        # wurde. NUR LESEN: der Snapshot wird nie zurueckgeschrieben.
        frame = None
        om = getattr(self._state, "output_manager", None)
        if om is not None:
            frame = om.get_display_frame(fixture.universe)
        channels = get_channels_for_patched(fixture)
        layout, lo, _hi = _attr_layout(fixture.address, channels)
        if frame is not None:
            return {k: frame[lo + i] for k, i in layout}
        return {k: universe.get_channel(lo + i + 1) for k, i in layout}

    def _frame_bytes(self, u) -> Optional[bytes]:
        """VIZ-77: der Frame, aus dem ``_collect_attrs`` fuer Universum ``u``
        liest — Display-Frame, sonst der Rohpuffer am Stueck. ``None``, wenn
        das Universum keinen ganzen Puffer liefern kann (Test-Attrappen mit
        nur ``get_channel``): dann baut der Snapshot ohne Cache wie bisher."""
        om = getattr(self._state, "output_manager", None)
        if om is not None:
            frame = om.get_display_frame(u)
            if frame is not None:
                return frame
        get_all = getattr(self._state.universes[u], "get_all", None)
        if get_all is None:
            return None
        try:
            return get_all()
        except Exception:
            return None

    def _build_snapshot(self) -> dict[int, dict[str, object]]:
        """Baut den Payload fuer JEDES aktuell platzierte, gepatchte Fixture.
        Dict-only: liest nur ueber ``get_patched_fixtures``/``universes``/
        ``visualizer_positions`` — nie ``state._scene`` direkt."""
        snapshot: dict[int, dict[str, object]] = {}
        # VIZ-70: EINMAL je Tick lesen. ``visualizer_positions`` ist am echten
        # AppState eine Property, die bei JEDEM Zugriff alle Weltpositionen aus
        # dem SceneGraph neu rechnet — in der Schleife war das O(n^2) und
        # gemessen gut die Haelfte der Tick-Zeit.
        placed = self._state.visualizer_positions
        universes = self._state.universes
        try:
            from src.core.app_state import get_channels_for_patched
        except Exception:
            get_channels_for_patched = None
        # VIZ-77: Cache verwerfen, wenn seit dem letzten Bau ein nicht-neutrales
        # Event kam oder er GATE_MAX_SKIPS Bauten alt ist (Sicherheitsnetz fuer
        # Aenderungen, die weder Event noch Schluessel sehen).
        if (self._payload_cache_rev != self._payload_rev
                or self._payload_cache_age >= self.GATE_MAX_SKIPS):
            self._payload_cache = {}
            self._payload_cache_rev = self._payload_rev
            self._payload_cache_age = 0
            # Der Gobo-/Prisma-Merkzettel faellt mit: auch er soll das
            # Sicherheitsnetz nicht ueberdauern.
            _KANAL_MEMO.clear()
        else:
            self._payload_cache_age += 1
        cache = self._payload_cache
        neu: dict[int, tuple] = {}
        frames: dict = {}
        hits = builds = 0
        for fixture in self._state.get_patched_fixtures():
            fid = fixture.fid
            if fid not in placed:
                continue
            u = fixture.universe
            if u not in universes:
                continue
            # Kanal-Objekte (gecached) mitgeben: nur so kennt die Payload-
            # Ableitung Farbrad-Slots und Shutter-Semantik (ChannelRange.kind).
            try:
                channels = get_channels_for_patched(fixture)
            except Exception:
                channels = None
            if u not in frames:
                frames[u] = self._frame_bytes(u)
            frame = frames[u]
            builds += 1
            if frame is None or channels is None:
                # Ohne ganzen Frame bzw. Kanalliste kein Schluessel -> wie bisher.
                attrs = self._collect_attrs(fixture)
                snapshot[fid] = _build_fixture_payload(fixture, attrs, channels)
                continue
            ident = _fixture_ident(fixture)
            alt = cache.get(fid)
            if (alt is not None and alt[0] is fixture and alt[1] is channels
                    and alt[2] == ident):
                layout = alt[3]
            else:
                alt = None
                layout = _attr_layout(fixture.address, channels)
            rel, lo, hi = layout
            # Ausschnitt EINMAL kopieren und Attribute aus genau dieser Kopie
            # lesen: Schluessel und Payload stammen so sicher aus denselben Bytes.
            aus = bytes(frame[lo:hi])
            if alt is not None and alt[4] == aus:
                payload = alt[5]
                builds -= 1
                hits += 1
            else:
                attrs = {k: aus[i] for k, i in rel}
                payload = _build_fixture_payload(fixture, attrs, channels)
            neu[fid] = (fixture, channels, ident, layout, aus, payload)
            snapshot[fid] = payload
        # Nur Geraete dieses Baus behalten: entfernte/unplatzierte fallen raus.
        self._payload_cache = neu
        self.payload_cache_stats = {"hits": hits, "builds": builds}
        return snapshot

    def _frame_signature(self) -> Optional[tuple]:
        """VIZ-70: billige Signatur aller Eingaben des Snapshots.

        Der Payload eines Geraets haengt nur ab von (a) seinem DMX — gelesen aus
        dem gesendeten Frame bzw. dem Rohpuffer, genau wie ``_collect_attrs`` —,
        (b) seinen Patch-/Profil-Daten und (c) davon, ob es im 3D platziert ist.
        (a) steckt hier als Bytes je Universum drin, (c) als Menge der
        platzierten fids, (b) ueber den Event-Zaehler ``_state_rev`` (Patch-
        Aenderungen melden sich als ``patch_changed``). Programmer, Funktionen
        und Stage wirken alle ueber den DMX-Frame. Kamera und Auswahl laufen
        gar nicht ueber den Tick (eigene Bridge-Pushes) — sie haengen also
        nicht an diesem Gate.

        ``None`` = keine verlaessliche Signatur (z. B. Test-Attrappe ohne
        ``get_all``) -> das Gate bleibt aus, der Tick baut wie bisher."""
        try:
            universes = self._state.universes
            om = getattr(self._state, "output_manager", None)
            frames = []
            for u in sorted(universes):
                frame = om.get_display_frame(u) if om is not None else None
                if frame is None:
                    frame = universes[u].get_all()
                frames.append((u, bytes(frame)))
            placed = frozenset(self._state.visualizer_positions)
            n_fix = len(self._state.get_patched_fixtures())
        except Exception:
            return None
        return (self._state_rev, n_fix, placed, tuple(frames))

    def _tick(self) -> None:
        if not any(t.active for t in self._targets):
            return
        # VIZ-70 Frame-Gate: hat sich seit dem letzten gebauten Tick keine
        # Eingabe geaendert, gibt es auch kein Diff — dann weder Snapshot bauen
        # noch senden. Gemessen lief der Bau sonst ~31x/s auch bei stehendem
        # DMX (ein Viertel bis ein Drittel eines Kerns, im UI-Thread). Ein
        # Target, das den vollen Bestand braucht, geht immer durch.
        sig = self._frame_signature()
        needs_full = any(t.active and t.needs_full for t in self._targets)
        if (sig is not None and sig == self._gate_sig and not needs_full
                and self._gate_skips < self.GATE_MAX_SKIPS):
            self._gate_skips += 1
            return
        if sig is not None and sig == self._gate_sig and not needs_full:
            # VIZ-77: dieser Bau kommt NUR vom Sicherheitsnetz der Sperre
            # (GATE_MAX_SKIPS Ticks ohne Aenderung). Dann auch den Payload-
            # Cache verwerfen — sonst wuerde er im Leerlauf erst nach
            # GATE_MAX_SKIPS solcher Bauten (rund 30 s statt 1 s) geleert.
            self._payload_cache_age = self.GATE_MAX_SKIPS
        self._gate_sig = sig
        self._gate_skips = 0
        snapshot = self._build_snapshot()
        self._seq += 1
        seq = self._seq

        # Diff ggue. dem service-globalen Cache: nur GEAENDERTE Fixtures.
        changed: dict[int, dict[str, object]] = {}
        last = self._last_payload
        for fid, payload in snapshot.items():
            alt = last.get(fid)
            # VIZ-77: ein Cache-Treffer liefert DASSELBE Objekt -> unveraendert.
            if alt is not payload and alt != payload:
                changed[fid] = payload
        # Fixtures, die aus dem Snapshot verschwunden sind (unpatched/entfernt),
        # werden hier bewusst NICHT nachgeschickt — das Aufraeumen laeuft ueber
        # den State-Patch-Prune (_on_state), nicht ueber den Tick.
        self._last_payload = snapshot

        batch_json = None
        for target in self._targets:
            if not target.active:
                continue
            full = bool(target.needs_full)
            if full:
                arr = list(snapshot.values())
                target.needs_full = False
            else:
                arr = list(changed.values())
            if not arr:
                continue
            emit_payloads = getattr(target, "emit_payloads", None)
            if emit_payloads is not None:
                # VIZ-71: strukturiert an den Push-Kanal. Ein Fehler in EINEM
                # Ziel darf die anderen nicht um ihren Batch bringen — der
                # Service-Cache ist oben schon weitergesetzt, ein verlorener
                # Diff kaeme nie wieder (A3D-04-Klasse). Darum: dieses Ziel
                # beim naechsten Tick voll beliefern.
                try:
                    emit_payloads(arr, full, seq)
                except Exception as e:                   # noqa: BLE001
                    target.needs_full = True
                    print(f"[VisualizerService] ERROR: Push an {target.name}: {e}")
                continue
            if full or batch_json is None:
                js = json.dumps(arr)
                if not full:
                    batch_json = js
            else:
                js = batch_json
            target.emit_batch(js)

    def force_full_resync(self, target: Optional[VisualizerTarget] = None) -> None:
        """Leert den Dirty-Cache (nach Reload/Stage-Wechsel/Target-Attach), so
        dass der naechste Tick wieder ALLES pusht statt nur das Diff. Ohne
        ``target`` betrifft es die globale Baseline UND alle Targets; mit
        ``target`` nur dieses eine (z.B. nach Page-Reload eines einzelnen
        Fensters)."""
        if target is None:
            self._last_payload = {}
            self._gate_sig = None
            self._payload_cache = {}
            for t in self._targets:
                t.needs_full = True
        else:
            target.needs_full = True

    # ── Interaktions-Reset (Schritt 5) ───────────────────────────────────────
    def reset_interaction_state(self) -> None:
        """Zentral bei ``show_loaded``/Stage-Wechsel aufrufen: stoppt pro
        Target laufende Interaktionen (Live-Trace) und setzt pro-Target
        Reload-Guards zurueck. Der Service kennt die konkrete Bridge/den
        Reload-Token-Mechanismus NICHT (Invariante 2 — Pro-Target-Zustand
        bleibt im Target) — er ruft nur den optionalen, vom Target
        registrierten ``on_reset_interaction``-Callback auf. Fehler in einem
        Target duerfen die anderen Targets nicht blockieren."""
        for target in self._targets:
            cb = target.on_reset_interaction
            if cb is None:
                continue
            try:
                cb()
            except Exception:
                pass

    # ── Szene neu laden (Schritt 5) ──────────────────────────────────────────
    def reload_all_targets(self, target: Optional[VisualizerTarget] = None) -> None:
        """"Szene neu laden": laedt die Page(s) frisch (Cache-Buster) neu und
        leert danach den Dirty-Cache, damit der naechste Tick wieder ALLES
        pusht statt nur das Diff. Mehrtarget-faehig von Anfang an (Design-
        Entscheidung 4): ohne ``target`` alle angedockten Targets mit
        registriertem ``on_reload``, mit ``target`` nur dieses eine. Der
        eigentliche ``load_stage_html``-Aufruf + RenderCrashGuard-Reset bleibt
        Sache des Targets (Invariante 2) — der Service stoesst nur an +
        resynct danach."""
        # Review-Fix (Entscheidung 4): nur AKTIVE Targets reloaden — der
        # dauerhaft angedockte, aber unsichtbare Live-View-Spiegel (active=False
        # bei 2D-Modus/anderem Tab) soll keinen Chromium-Reload abbekommen.
        # Er holt sich den vollen Bestand ohnehin via needs_full beim naechsten
        # Aktivieren.
        targets = ([t for t in self._targets if t.active]
                   if target is None else [target])
        for t in targets:
            cb = t.on_reload
            if cb is None:
                continue
            try:
                cb()
            except Exception:
                pass
        self.force_full_resync(target)

    # ── State-Subscribe (aus der Bridge gehobene Prune-Logik, dict-only) ────
    def _on_state(self, event: str, data) -> None:
        # VIZ-70: jedes Event macht die Frame-Gate-Signatur ungueltig (siehe
        # ``_frame_signature``) — auch die, die hier sonst nichts ausloesen.
        self._state_rev += 1
        if event not in _PAYLOAD_NEUTRAL_EVENTS:
            # VIZ-77: Payload-Cache beim naechsten Bau verwerfen.
            self._payload_rev += 1
        if event == "show_loaded":
            # VIZ-71 (S4): neue Show -> JEDES Ziel bekommt beim naechsten Tick
            # den vollen Bestand. Die fids der neuen Show koennen dieselben
            # Nummern wie in der alten tragen; ein Diff gegen den alten Cache
            # hielte unveraenderte Werte faelschlich fuer zugestellt.
            self.force_full_resync()
            return
        if event != "patch_changed":
            return
        current_fids = {f.fid for f in self._state.get_patched_fixtures()}
        stale = [fid for fid in list(self._state.visualizer_positions)
                 if fid not in current_fids]
        for fid in stale:
            self._state.visualizer_positions.pop(fid, None)
            self._state.visualizer_docks.pop(fid, None)
            self._state.visualizer_rotations.pop(fid, None)
            self._last_payload.pop(fid, None)
        lv = getattr(self._state, "live_view_positions", None)
        if isinstance(lv, dict):
            for fid in [f for f in list(lv) if f not in current_fids]:
                lv.pop(fid, None)

    def shutdown(self) -> None:
        """Einziger vollstaendiger Teardown-Pfad (App-Ende): meldet den EINEN
        Service-Subscriber ab und stoppt den Timer. ``hide()``/``detach_target``
        melden bewusst NICHTS ab (Hintergrund-Updates fuer andere Targets
        bleiben moeglich)."""
        if self._subscribed:
            self._state.unsubscribe(self._on_state)
            self._subscribed = False
        if self._timer_alive():
            self._timer.stop()
        self._targets.clear()
        self._last_payload = {}
        self._payload_cache = {}


# ── Singleton am AppState (Orchestrator-Entscheidung 5) ─────────────────────
def get_visualizer_service(state) -> VisualizerService:
    """Lazy-Singleton, gehalten als Attribut AM uebergebenen ``state`` (nicht
    modul-global) — ein frischer State (z.B. in Tests) bekommt automatisch
    einen frischen Service."""
    svc = getattr(state, "_visualizer_service", None)
    if svc is None:
        svc = VisualizerService(state)
        state._visualizer_service = svc
    return svc
