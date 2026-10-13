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
    weiter). ``faktor`` = alles, was die Staerke zusaetzlich skaliert (0..1)."""
    from src.core.dmx.universe import Universe
    mode = normalize_mode(getattr(f, "modify_mode", MODIFY_ADD))
    s = (normalize_strength(getattr(f, "modify_strength", 100)) / 100.0
         ) * _clamp01(faktor)
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


def posten_anwenden(posten, universes) -> None:
    """Gesammelte Modify-Posten der Reihe nach auf ``universes`` verrechnen.

    Geschrieben wird nur, wo sich der Wert aendert."""
    for mode, s, betraege in posten:
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
