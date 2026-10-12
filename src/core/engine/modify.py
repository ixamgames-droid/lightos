"""ENG-37: Modify-Effekte — verrechnen statt setzen.

Ein normaler Effekt SETZT seine Kanaele (zwischen Funktionen gewinnt, wer
zuletzt schreibt). Ein Modify-Effekt setzt nichts: er rendert in ein leeres
privates Universum und wird danach Adresse fuer Adresse mit dem verrechnet,
was die Effekte unter ihm in diesem Frame geschrieben haben.

    w = Betrag, den der Modify-Effekt fuer die Adresse ausrechnet (0..255)
    s = wirksame Staerke (0..1) = modify_strength/100 * Effekt-Helligkeit * Huellkurve
    u = Wert darunter (0..255)

    Addieren   u + w*s
    Abziehen   u - w*s
    Abdunkeln  u * (1 - w/255 * s)

Gerundet, gekappt bei 0 und 255. In allen drei Arten ist Betrag 0 neutral —
„Lampe ist nicht dran" laesst das Darunterliegende unveraendert.

★ Schreibregel (traegt das Renderer-Verhalten „Effekt treibt Dimmer"):
  - Addieren schreibt IMMER (auch Betrag 0). Laeuft nichts darunter, wirkt es
    auf den Ruhewert und sieht aus wie ein normaler Effekt.
  - Abziehen/Abdunkeln schreiben NUR dort, wo in diesem Frame schon ein Effekt
    geschrieben hat, und nur, wenn sich der Wert aendert. Allein gestartet
    treiben sie also keinen Kanal und koennen Grundwerte/Snaps nicht
    „durch die Hintertuer" verdunkeln.

★ Effekt-Helligkeit und Huellkurve des Modify-Effekts skalieren die STAERKE,
  nie das Ergebnis — sonst wuerde das Darunterliegende mitgedimmt.
"""
from __future__ import annotations

MODIFY_ADD = "add"
MODIFY_SUB = "sub"
MODIFY_DIM = "dim"
MODIFY_MODES: tuple[str, ...] = (MODIFY_ADD, MODIFY_SUB, MODIFY_DIM)
MODIFY_LABELS: dict[str, str] = {
    MODIFY_ADD: "Addieren",
    MODIFY_SUB: "Abziehen",
    MODIFY_DIM: "Abdunkeln",
}


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
    Schritt 1 kennt Modify nur fuer die Matrix im Stil Dimmer."""
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


def write_modify(f, universes, patch_cache, dt, function_registry=None,
                 faktor: float | None = None) -> None:
    """Modify-Effekt ``f`` rendern und in ``universes`` einmischen.

    ``faktor`` = Effekt-Helligkeit * Huellkurve (0..1). ``None`` nimmt die
    Effekt-Helligkeit der Funktion selbst (Kind einer Collection/Show — dort
    treibt niemand die Huellkurven-Uhr)."""
    from src.core.dmx.universe import Universe
    if faktor is None:
        faktor = _clamp01(getattr(f, "intensity", 1.0))
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
    immer = (mode == MODIFY_ADD)
    for u, pu in priv.items():
        touched = pu.end_write_log()
        if not touched:
            continue
        shared = universes[u]
        betrag = pu.get_all()
        for ch in touched:
            unten = shared.get_channel(ch)
            if not immer:
                # Abziehen/Abdunkeln: nur, wo ein Effekt darunter schreibt.
                # Ohne Schreibprotokoll (None) entscheidet allein der Wert.
                ww = getattr(shared, "was_written", None)
                if ww is not None and ww(ch) is False:
                    continue
            neu = modify_wert(mode, unten, betrag[ch - 1], s)
            if immer or neu != unten:
                shared.set_channel(ch, neu)


def write_child(child, universes, patch_cache, dt, function_registry=None) -> None:
    """Kind einer Collection/Show schreiben — Modify-Kinder werden verrechnet,
    alle anderen schreiben unveraendert direkt."""
    if ist_modify(child):
        write_modify(child, universes, patch_cache, dt, function_registry)
    else:
        child.write(universes, patch_cache, dt, function_registry)
