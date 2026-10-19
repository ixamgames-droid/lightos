"""ENG-37: Modify-Effekte — verrechnen statt setzen.

Ein normaler Effekt SETZT seine Kanaele (zwischen Funktionen gewinnt, wer
zuletzt schreibt). Ein Modify-Effekt setzt nichts. Er rendert in ein leeres
privates Universum; uebrig bleibt je Adresse ein BETRAG. Diese Betraege werden
gesammelt und in EINEM spaeten Rechengang mit dem fertigen Bild der Schichten
darunter verrechnet:

    w = Betrag, den der Modify-Effekt fuer die Adresse ausrechnet (0..255)
    s = wirksame Staerke (0..1) = modify_strength/100 * Effekt-Helligkeit
        * Huellkurve (* Helligkeit/Huellkurve der Sammlung, in der er laeuft)
    u = Wert darunter (0..255)

    Addieren   u + w*s
    Abziehen   u - w*s
    Abdunkeln  u * (1 - w/255 * s)

Gerundet, gekappt bei 0 und 255. In allen drei Arten ist Betrag 0 neutral —
„Lampe ist nicht dran" laesst das Darunterliegende unveraendert.

★ EIN Ort, eine Regel: „Modify rechnet auf das fertige Bild vor den Mastern."
  Der Renderer (AppState._render_frame) meldet beim FunctionManager das
  Aufschieben an (``modify_aufschieben``), ruft ``tick`` und wendet die
  gesammelten Posten (``modify_anwenden``) erst NACH Effekten,
  Cuelisten, Programmer/Snaps und automatischer Grundhelligkeit an — und VOR
  Submastern/Gruppen-Fadern, DMX-Eingang, Grand Master, Blackout und
  Laser-NOT-AUS. Ein Modify-Effekt schreibt waehrend des Funktions-Durchlaufs
  NICHTS ins gemeinsame Universum: er „treibt" damit keinen Kanal, besitzt
  keinen Dimmer und schaltet die Grundhelligkeit nicht ab.
  Ohne Renderer (``tick`` allein, Tests/Werkzeuge) werden die Posten am Ende
  von ``tick`` angewandt — dieselbe Rechnung, nur ohne die Schichten darueber.

★ Effekt-Helligkeit und Huellkurve — des Modify-Effekts UND der Sammlung, in
  der er als Kind laeuft — skalieren die STAERKE, nie das Ergebnis. Das
  Darunterliegende wird also nie mitgedimmt.

★ ENG-38, Stil FARBE (RGB/RGBW): dieselbe Rechnung, nur sind die Adressen die
  Farbkanaele. Die Matrix schreibt im Modify-Betrieb ausschliesslich
  color_r/g/b (bei RGBW den Weissanteil auf color_w) ins private Universum —
  keinen Dimmer, kein Farbrad (``RgbMatrixInstance._farb_modify``). Jeder
  Farbkanal wird damit EINZELN verrechnet und einzeln bei 0..255 gekappt; der
  Farbton darf dabei kippen (Orange + Rot -> Rot voll). Ein Farb-Modify fasst
  den Dimmer nie an und laeuft NACH der automatischen Grundhelligkeit: er kann
  sie weder ausloesen noch zuruecknehmen — eine dunkle Lampe bleibt dunkel.

★ ENG-40, Kanalwahl („Wirkt auf"): ``modify_channels`` leer = Vorgabe, die
  Modify-FARBE bestimmt die Kanaele (genau ENG-38, byte-gleich). Sind Kanaele
  angekreuzt (Rot, Gruen, Blau, Weiss, Amber, UV), schreibt die Matrix im
  Farb-Modify NUR diese Farbkanaele — und zwar je Kanal die HELLIGKEIT des
  Effekts an der Lampe (groesster Farbanteil), nicht mehr den Anteil der
  Farbe. „Nur Weiss" trifft also allein color_w; ein Geraet ohne diesen Kanal
  bekommt keinen Posten (kein Umrechnen von Weiss auf RGB). Der Dimmer gehoert
  nicht zur Auswahl: er wird ueber den Stil DIMMER verrechnet (ENG-37) —
  Farbe und Dimmer bleiben getrennt.

★ ENG-43, BEWEGUNG (EFX als Modify): kein Betrag 0..255, sondern ein
  VERSATZ IN GRAD auf Pan/Tilt des fertigen Bildes. Addieren verschiebt die
  laufende Position um +n Grad, Abziehen um -n Grad (gespiegelte Figur);
  Abdunkeln gibt es fuer Bewegung nicht (wird wie Addieren gelesen). Je Geraet
  wird der Winkel ueber dessen Schwenk-/Neigebereich (``pan_range_deg``/
  ``tilt_range_deg``) in DMX umgerechnet — mit Fine-Kanal als EIN 16-Bit-Wert
  (Grob und Fein gemeinsam, kein Sprung am Uebertrag), ohne Fine in 8 Bit.
  Gekappt an 0 und Vollausschlag, nie umgeschlagen. ``swap_pan_tilt`` und
  ``invert_pan``/``invert_tilt`` werden wie in ``apply_pan_tilt_orientation``
  beachtet (erst Tausch, dann Umkehr je Kanal).
  SICHERHEIT: Laser bekommen KEINEN Bewegungs-Versatz. Die Sperrzonen
  (LAS-32) sind reine Anzeige und sitzen nicht im Render-Pfad — es gibt dort
  keinen Schutz, der eine verschobene Laser-Position abfangen koennte. Darum
  schliesst ``bewegung_eintraege`` jedes Geraet aus, das ``ist_laser`` als
  Laser erkennt, und jede Achse, die nicht ``pan``/``tilt`` heisst
  (``laser_x``/``laser_y``). Der Laser-NOT-AUS (4d) liegt ohnehin danach.

★ Kosten: laeuft kein Modify-Effekt, gibt es keinen Posten und der spaete
  Rechengang ist ein leerer Listen-Test.
"""
from __future__ import annotations

import threading

MODIFY_ADD = "add"
MODIFY_SUB = "sub"
MODIFY_DIM = "dim"
MODIFY_MODES: tuple[str, ...] = (MODIFY_ADD, MODIFY_SUB, MODIFY_DIM)
MODIFY_LABELS: dict[str, str] = {
    MODIFY_ADD: "Addieren",
    MODIFY_SUB: "Abziehen",
    MODIFY_DIM: "Abdunkeln",
}


# ENG-40: Kanalwahl eines Farb-Modify. Kurzzeichen (so stehen sie in der Show)
# -> Kanal-Attribut des Geraets. Die Reihenfolge ist die der Oberflaeche und
# der gespeicherten Liste. Amber und UV kennt die Engine als Farbkanaele
# (app_state._DIM_COLOR_ATTRS); CMY ist subtraktiv und bleibt draussen.
MODIFY_KANAL_ATTR: dict[str, str] = {
    "r": "color_r",
    "g": "color_g",
    "b": "color_b",
    "w": "color_w",
    "a": "color_a",
    "uv": "color_uv",
}
MODIFY_KANAELE: tuple[str, ...] = tuple(MODIFY_KANAL_ATTR)
MODIFY_KANAL_LABELS: dict[str, str] = {
    "r": "Rot",
    "g": "Grün",
    "b": "Blau",
    "w": "Weiß",
    "a": "Amber",
    "uv": "UV",
}


def normalize_channels(value) -> tuple[str, ...]:
    """Kanalwahl als Tupel der Kurzzeichen in fester Reihenfolge.

    Leer = Vorgabe („Kanaele der Modify-Farbe"). Fehlendes, Unlesbares und
    unbekannte Zeichen fallen weg — eine Alt-Show ohne das Feld bleibt damit
    beim bisherigen Verhalten."""
    if not value:
        return ()
    if isinstance(value, str):
        teile = value.replace(";", ",").split(",")
    else:
        try:
            teile = list(value)
        except TypeError:
            return ()
    gewaehlt = {str(t or "").strip().lower() for t in teile}
    return tuple(k for k in MODIFY_KANAELE if k in gewaehlt)


def normalize_mode(value) -> str:
    """Unbekannte/fehlende Betriebsart -> Addieren (Vorgabe)."""
    s = str(value or "").strip().lower()
    return s if s in MODIFY_MODES else MODIFY_ADD


def normalize_strength(value) -> int:
    """Staerke in ganzen Prozent, 0..100; Unlesbares -> 100 (Vorgabe)."""
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        return 100
    return 0 if v < 0 else 100 if v > 100 else v


def ist_modify(f) -> bool:
    """True, wenn ``f`` in diesem Frame als Modify-Effekt verrechnet wird.

    Fragt ``modify_wirksam()`` der Funktion — der Haken allein genuegt nicht:
    Modify kennt nur die Matrix, in den Stilen Dimmer (ENG-37) und RGB/RGBW
    (ENG-38); beim Stil Shutter laeuft sie trotz Haken normal."""
    fn = getattr(f, "modify_wirksam", None)
    if fn is None:
        return False
    try:
        return bool(fn())
    except Exception:
        return False


def modify_wert(mode: str, u: int, w: int, s: float) -> int:
    """Eine Adresse verrechnen. ``u`` darunter, ``w`` Betrag, ``s`` Staerke 0..1."""
    if mode == MODIFY_SUB:
        v = u - w * s
    elif mode == MODIFY_DIM:
        v = u * (1.0 - (w / 255.0) * s)
    else:
        v = u + w * s
    v = int(round(v))
    return 0 if v < 0 else 255 if v > 255 else v


def _clamp01(value, default: float = 1.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


class ModifySammler:
    """Sammelt die Modify-Posten EINES Frames.

    ``posten``: Liste ``(mode, s, {universum: [(adresse, betrag), …]})`` in der
    Reihenfolge, in der sie wirken sollen. ``faktor``: Helligkeit x Huellkurve
    der Funktion, die gerade oben im Durchlauf schreibt (Sammlung/Show) — ein
    Modify-Kind bekommt ihn als Staerke-Faktor."""
    __slots__ = ("posten", "faktor")

    def __init__(self):
        self.posten: list = []
        self.faktor: float = 1.0


_lokal = threading.local()


def aktiver_sammler() -> ModifySammler | None:
    """Der Sammler des laufenden ``FunctionManager.tick`` (nur in dessen Thread)."""
    return getattr(_lokal, "sammler", None)


def setze_sammler(sammler: ModifySammler | None) -> ModifySammler | None:
    """Sammler fuer diesen Thread setzen; gibt den vorherigen zurueck."""
    alt = getattr(_lokal, "sammler", None)
    _lokal.sammler = sammler
    return alt


def modify_posten(f, universes, patch_cache, dt, function_registry=None,
                  faktor: float = 1.0):
    """Modify-Effekt ``f`` rendern und seinen Posten liefern (oder ``None``).

    Gerendert wird IMMER (die Uhr des Effekts laeuft auch bei Staerke 0
    weiter). ``faktor`` = alles, was die Staerke zusaetzlich skaliert (0..1).

    ENG-43: Bietet ``f`` ``modify_bewegung`` (EFX), entsteht ein
    :class:`BewegungsPosten` (Versatz in Grad) statt eines Betrag-Postens."""
    from src.core.dmx.universe import Universe
    mode = normalize_mode(getattr(f, "modify_mode", MODIFY_ADD))
    s = (normalize_strength(getattr(f, "modify_strength", 100)) / 100.0
         ) * _clamp01(faktor)
    bewegung = getattr(f, "modify_bewegung", None)
    if callable(bewegung):
        # Die Figur laeuft immer weiter (Uhr), auch bei Staerke 0.
        versaetze = bewegung(patch_cache, dt)
        if s <= 0.0 or not versaetze:
            return None
        return bewegung_posten(versaetze, mode, s)
    # LEERES privates Universum (nicht mit dem Scratch vorbelegt): gebraucht
    # wird der reine Betrag des Effekts, nicht „Betrag ueber dem Untergrund".
    priv: dict[int, Universe] = {}
    for u in universes:
        pu = Universe(u)
        pu.begin_write_log()
        priv[u] = pu
    f.write(priv, patch_cache, dt, function_registry)
    betraege: dict[int, list] = {}
    for u, pu in priv.items():
        touched = pu.end_write_log()
        if not touched or s <= 0.0:
            continue
        roh = pu.get_all()
        # Betrag 0 ist in allen drei Arten neutral -> gar nicht erst merken.
        liste = [(ch, roh[ch - 1]) for ch in sorted(touched) if roh[ch - 1]]
        if liste:
            betraege[u] = liste
    if not betraege:
        return None
    return (mode, s, betraege)


# ── ENG-43: Bewegung als Versatz in Grad ────────────────────────────────────

#: Bereich, wenn ein Geraet keinen (sinnvollen) Schwenk-/Neigebereich traegt —
#: dieselben Vorgaben wie Patch/Show (540/270).
PAN_BEREICH_VORGABE = 540.0
TILT_BEREICH_VORGABE = 270.0


def _bereich(fx, attr: str, vorgabe: float) -> float:
    try:
        v = float(getattr(fx, attr, vorgabe) or 0.0)
    except (TypeError, ValueError):
        v = 0.0
    return v if v > 0.0 else vorgabe


def verschiebe_wert(grob: int, fein: int | None, anteil: float):
    """Einen Pan- oder Tilt-Kanal um ``anteil`` (Bruchteil des Vollausschlags,
    vorzeichenbehaftet) verschieben. Mit Fein-Kanal als EIN 16-Bit-Wert
    (``grob*256+fein``) — kein Sprung am Uebertrag —, ohne in 8 Bit.
    Gekappt an 0 und am Vollausschlag (kein Umschlag). Gibt ``(grob, fein)``
    zurueck (``fein`` None, wenn es keinen gibt)."""
    if fein is None:
        v = int(round(grob + anteil * 255.0))
        return (0 if v < 0 else 255 if v > 255 else v), None
    v = int(round(((grob << 8) | fein) + anteil * 65535.0))
    v = 0 if v < 0 else 65535 if v > 65535 else v
    return v >> 8, v & 0xFF


class BewegungsPosten:
    """ENG-43: Modify-Posten einer Bewegung. ``eintraege`` = Liste
    ``(universum, grob_adresse, fein_adresse | None, anteil)``; ``anteil`` ist
    der fertig skalierte (Staerke, Betriebsart, Umkehr) Bruchteil des
    Vollausschlags dieses Kanals."""
    __slots__ = ("eintraege",)

    def __init__(self, eintraege):
        self.eintraege = list(eintraege)

    def anwenden(self, universes) -> None:
        for u, grob_adr, fein_adr, anteil in self.eintraege:
            shared = universes.get(u)
            if shared is None or not anteil:
                continue
            grob = shared.get_channel(grob_adr)
            fein = shared.get_channel(fein_adr) if fein_adr else None
            g, f = verschiebe_wert(grob, fein, anteil)
            if g != grob:
                shared.set_channel(grob_adr, g)
            if fein_adr and f != fein:
                shared.set_channel(fein_adr, f)


def _paare(chans, achse: str):
    """(grob, fein|None)-Kanalpaare einer Achse in Kanal-Reihenfolge — das
    k-te Grob-Vorkommen gehoert zum k-ten Fein-Vorkommen (Mehrkopf)."""
    grob = [c for c in chans if (getattr(c, "attribute", "") or "") == achse]
    fein = [c for c in chans
            if (getattr(c, "attribute", "") or "") == f"{achse}_fine"]
    return [(g, fein[k] if k < len(fein) else None) for k, g in enumerate(grob)]


def bewegung_eintraege(fx, chans, dpan_grad: float, dtilt_grad: float,
                       head=None) -> list:
    """Logischen Versatz (Grad Pan, Grad Tilt) eines Geraets in Kanal-Eintraege
    ``(universum, grob, fein, anteil)`` umrechnen.

    * Laser (``ist_laser``) und Geraete ohne DMX-Ausgabe: KEIN Eintrag.
    * ``swap_pan_tilt``: der Pan-Versatz faehrt auf den Tilt-Kanal und
      umgekehrt; danach kehrt ``invert_pan``/``invert_tilt`` das Vorzeichen
      des jeweiligen KANALS um (Reihenfolge wie ``apply_pan_tilt_orientation``).
    * Umrechnung ueber den Bereich des Kanals: Pan-Kanal ``pan_range_deg``,
      Tilt-Kanal ``tilt_range_deg``.
    * ``head``: nur die Kanaele dieses Kopfes; sonst alle Koepfe gleich."""
    from src.core.laser.erkennung import ist_laser
    from .function import gibt_ueber_dmx_aus
    try:
        if ist_laser(fx, chans):
            return []
    except Exception:
        return []          # im Zweifel: nicht bewegen
    if not gibt_ueber_dmx_aus(fx):
        return []
    if getattr(fx, "swap_pan_tilt", False):
        dpan_grad, dtilt_grad = dtilt_grad, dpan_grad
    if getattr(fx, "invert_pan", False):
        dpan_grad = -dpan_grad
    if getattr(fx, "invert_tilt", False):
        dtilt_grad = -dtilt_grad
    anteile = {
        "pan": dpan_grad / _bereich(fx, "pan_range_deg", PAN_BEREICH_VORGABE),
        "tilt": dtilt_grad / _bereich(fx, "tilt_range_deg", TILT_BEREICH_VORGABE),
    }
    if head is not None:
        from src.core.app_state import channels_for_head
        try:
            kopf = channels_for_head(chans, int(head))
        except Exception:
            return []
        paare = {a: [(kopf[a], kopf.get(f"{a}_fine"))] if a in kopf else []
                 for a in anteile}
    else:
        paare = {a: _paare(chans, a) for a in anteile}
    out = []
    for achse, anteil in anteile.items():
        if not anteil:
            continue
        for grob, fein in paare[achse]:
            ga = fx.address + grob.channel_number - 1
            if not (1 <= ga <= 512):
                continue
            fa = None
            if fein is not None:
                fa = fx.address + fein.channel_number - 1
                if not (1 <= fa <= 512):
                    fa = None
            out.append((fx.universe, ga, fa, anteil))
    return out


def bewegung_posten(versaetze, mode: str, s: float):
    """Aus den Versaetzen eines Bewegungs-Modify einen :class:`BewegungsPosten`
    bauen. ``versaetze``: ``(fx, head, dpan_grad, dtilt_grad, pan_attr,
    tilt_attr)`` je Ziel. Achsen, die nicht ``pan``/``tilt`` heissen (Laser-
    Achsen), werden nie verschoben."""
    from src.core.app_state import get_channels_for_patched
    vz = -1.0 if mode == MODIFY_SUB else 1.0
    eintraege = []
    for fx, head, dpan, dtilt, pa, ta in versaetze:
        if fx is None:
            continue
        dp = dpan * s * vz if pa == "pan" else 0.0
        dt_ = dtilt * s * vz if ta == "tilt" else 0.0
        if not dp and not dt_:
            continue
        try:
            chans = get_channels_for_patched(fx)
        except Exception:
            continue
        eintraege.extend(bewegung_eintraege(fx, chans, dp, dt_, head))
    return BewegungsPosten(eintraege) if eintraege else None


def posten_anwenden(posten, universes) -> None:
    """Gesammelte Modify-Posten der Reihe nach auf ``universes`` verrechnen.

    Geschrieben wird nur, wo sich der Wert aendert."""
    for p in posten:
        if isinstance(p, BewegungsPosten):
            p.anwenden(universes)
            continue
        mode, s, betraege = p
        for u, liste in betraege.items():
            shared = universes.get(u)
            if shared is None:
                continue
            for ch, w in liste:
                unten = shared.get_channel(ch)
                neu = modify_wert(mode, unten, w, s)
                if neu != unten:
                    shared.set_channel(ch, neu)


def write_modify(f, universes, patch_cache, dt, function_registry=None,
                 faktor: float | None = None) -> None:
    """Modify-Effekt ``f`` rendern und verrechnen.

    Laeuft gerade ein ``FunctionManager.tick`` (Sammler aktiv), wird der Posten
    nur GEMERKT und spaeter auf das fertige Bild angewandt. Ohne Sammler
    (direkter Aufruf) wird sofort mit ``universes`` verrechnet.

    ``faktor`` = Effekt-Helligkeit * Huellkurve (0..1). ``None`` nimmt die
    Effekt-Helligkeit der Funktion selbst."""
    if faktor is None:
        faktor = _clamp01(getattr(f, "intensity", 1.0))
    p = modify_posten(f, universes, patch_cache, dt, function_registry, faktor)
    if p is None:
        return
    sammler = aktiver_sammler()
    if sammler is not None:
        sammler.posten.append(p)
    else:
        posten_anwenden((p,), universes)


def write_child(child, universes, patch_cache, dt, function_registry=None) -> None:
    """Kind einer Collection/Show schreiben — Modify-Kinder werden verrechnet,
    alle anderen schreiben unveraendert direkt.

    Der Faktor der Sammlung (Helligkeit x Huellkurve, vom FunctionManager im
    Sammler hinterlegt) wird dem Modify-Kind als STAERKE-Faktor mitgegeben.
    Die Sammlung dimmt damit nur, wie kraeftig das Kind zugreift — nicht das,
    was darunter laeuft."""
    if ist_modify(child):
        sammler = aktiver_sammler()
        eltern = sammler.faktor if sammler is not None else 1.0
        write_modify(child, universes, patch_cache, dt, function_registry,
                     faktor=_clamp01(eltern)
                     * _clamp01(getattr(child, "intensity", 1.0)))
    else:
        child.write(universes, patch_cache, dt, function_registry)
