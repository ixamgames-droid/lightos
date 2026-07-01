"""Algorithmus-Metadaten fuer die Matrix-Param-UI (I2.4).

Trennt Logik/Metadaten von der View: je Algorithmus, welche Parameter sinnvoll
sind (Key, Label, Typ, Default, Min/Max/Step, Tooltip), ob eine Richtung
(Vor/Rueck) sinnvoll ist. Die View baut ihre Param-Felder dynamisch daraus.
Die Param-Keys entsprechen exakt denen, die rgb_matrix.py `_render` aus
`self.params` liest.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from .rgb_matrix import RgbAlgorithm


@dataclass(frozen=True)
class ParamSpec:
    key: str
    label: str
    # "int" | "float" | "bool" | "select" | "color" | "color_sequence" |
    # "dimmer_sequence" | "action"
    kind: str
    default: object
    min: float = 0.0
    max: float = 0.0
    step: float = 1.0
    tooltip: str = ""
    # Auswahlwerte fuer kind=="select" (Tupel aus internen Werten oder
    # (wert, label)-Paaren). Leer fuer alle anderen Typen.
    options: tuple = ()
    # Live-Programming-Metadaten (Phase 2): kann der Parameter auf ein
    # Bedienelement der virtuellen Konsole / MIDI gelegt werden, und darf er
    # im laufenden Effekt live geaendert werden? Die VC liest diese Flags, um
    # dynamisch zu erkennen, was steuerbar ist (Anforderung #13).
    mappable: bool = True
    live_editable: bool = True
    # Style-/Bedingungs-Sichtbarkeit (WP-2, Abschnitte 3/4/10): ein Parameter ist
    # nur relevant (= sichtbar UND wird geschrieben), wenn er zum gewaehlten
    # MatrixStyle passt und seine `when`-Bedingungen erfuellt sind. So zeigt der
    # Random-/Fill-Algorithmus bei Style "Dimmer" nur Helligkeits-Parameter, bei
    # "RGB/RGBW" nur Farb-Parameter usw. — und schreibt auch nur diese (keine
    # gegenseitige Ueberschreibung von Dimmer-/Color-/Effect-Werten).
    #   styles: leer = fuer alle Styles relevant; sonst nur fuer die genannten
    #           MatrixStyle-Werte ("RGB"/"RGBW"/"Dimmer"/"Shutter").
    #   when:   Tupel aus (anderer_key, (erlaubte_werte, …)) — alle Bedingungen
    #           muessen erfuellt sein (z. B. (("mode", ("strobe",)),)).
    styles: tuple = ()
    when: tuple = ()


@dataclass(frozen=True)
class AlgoMeta:
    description: str = ""
    direction: bool = False          # Richtung Vor/Rueck sinnvoll?
    params: tuple = field(default_factory=tuple)
    # Anzahl der Farbfelder (C1..C3), die der Algorithmus tatsaechlich auswertet.
    # 0 = gar keine (z. B. Rainbow erzeugt eigene HSV-Farben). So zeigt die View
    # nur die Farben an, die wirklich programmierbar sind (UI-01).
    colors: int = 1
    # True = der Algorithmus nutzt die GANZE Color-Sequence (beliebig viele
    # aktive Farben) -> die View zeigt den Sequence-Editor. False = er nutzt nur
    # `colors` feste Farbfelder (C1..Cn) -> die View zeigt feste Farbknoepfe.
    # So passt die Farb-UI exakt zur Engine (Wipe/Wave/SinePlasma/Windrad nutzen
    # nur c1/c2, NICHT die ganze Sequence — der Sequence-Editor versprach dort
    # mehr als die Engine einloest, M2).
    sequence: bool = False


# Wiederverwendbare Param-Bausteine
def _runner_count(when=()):
    return ParamSpec("runner_count", "Läufer-Anzahl", "int", 1, 1, 16, 1,
                     "Anzahl gleichzeitiger Läufer (1..16)", when=when)

def _runner_width(label="Läufer-Breite"):
    return ParamSpec("runner_width", label, "int", 1, 1, 16, 1,
                     "Breite in Zellen (1..16)")

def _invert():
    return ParamSpec("invert", "Invertieren", "bool", False)

def _beam_width(label="Strahlbreite"):
    return ParamSpec("beam_width", label, "float", 0.15, 0.02, 1.0, 0.05,
                     "Breite als Anteil (0.02..1.0)")

def _fade():
    return ParamSpec("fade", "Schweif", "float", 0.3, 0.0, 1.0, 0.05,
                     "Schweif-Länge hinter dem Strahl (0..1)")

def _after_fade(when=()):
    # WP-4/Abschnitt 5: räumlicher Schweif (Komet) HINTER dem Lauflicht, in Prozent.
    # 0 % = harte Kante ohne Schweif, 100 % = langer Schweif über die volle Achse.
    # Label bewusst "Schweif (%)" (nicht "After Fade"), damit es NICHT mit dem
    # zeitlichen "Ausblenden" (env_fade_out, Hüllkurve beim Stoppen) verwechselt
    # wird — das ist ein anderer Mechanismus. Eigener Key (after_fade) -> eindeutige
    # Migration der alten 0..1-Werte (siehe apply_dict).
    return ParamSpec("after_fade", "Schweif (%)", "float", 30.0, 0.0, 100.0, 5.0,
                     "Räumlicher Schweif hinter dem Läufer in % (0 = harte Kante ohne "
                     "Schweif, 100 = langer Schweif). Rein räumlich — NICHT das zeitliche "
                     "Ausblenden des Effekts (das ist „Ausblenden“ unter Tempo & Blende).",
                     when=when)

def _color_order():
    # WP-4/Abschnitt 6: Reihenfolge des Farbwechsels pro Runde (nur wenn aktiv).
    return ParamSpec("color_order", "Farb-Reihenfolge", "select", "normal",
                     options=("normal", "random", "pingpong"),
                     when=(("color_cycle", (True,)),), styles=("RGB", "RGBW"),
                     tooltip="Reihenfolge, in der pro Runde durch die Color-Sequence gewechselt wird")

def _turns():
    return ParamSpec("turns", "Windungen", "float", 1.0, 0.25, 8.0, 0.25,
                     "Anzahl Spiral-Windungen")

# ── Bausteine fuer die konsolidierten Grundalgorithmen (Phase 3) ──────────────
def _axis(options=("H", "V", "Diag")):
    return ParamSpec("axis", "Achse", "select", "H", options=options,
                     tooltip="Bewegungsachse (horizontal/vertikal/diagonal)")

def _movement(options):
    return ParamSpec("movement", "Bewegung", "select", "normal", options=options,
                     tooltip="Bewegungsmodus (normal/bounce/center_out/outside_in)")

def _origin():
    return ParamSpec("origin", "Ursprung", "select", "left",
                     options=("left", "right", "top", "bottom", "center", "radial"),
                     tooltip="Ausgangspunkt/Richtung der Welle")

def _blend():
    return ParamSpec("blend", "Verlauf", "select", "smooth",
                     options=("smooth", "steps"),
                     tooltip="weicher Verlauf oder harte Farb-Bänder")

def _edge_fade():
    return ParamSpec("edge_fade", "Kanten-Fade", "float", 0.0, 0.0, 1.0, 0.05,
                     "0 = harte Kante, >0 = weicher Übergang")

def _density():
    return ParamSpec("density", "Dichte", "float", 1.0, 0.25, 8.0, 0.25,
                     "Anzahl Wellenberge")

def _spread():
    return ParamSpec("spread", "Breite", "float", 1.0, 0.25, 8.0, 0.25,
                     "Breite der hellen Wellenbänder")

def _color_cycle():
    # Nur Farb-Styles: bei Dimmer/Shutter greift stattdessen _dimmer_cycle (ENG-08).
    return ParamSpec("color_cycle", "Farbe pro Runde wechseln", "bool", False,
                     styles=("RGB", "RGBW"),
                     tooltip="Läufer wechselt pro Durchlauf durch die Farb-Sequence")

def _color_interval():
    # MXP-01 (Abschnitt 10): Farbe erst alle N Durchlaeufe wechseln. 1 = jeder
    # Durchlauf (= bisheriges Verhalten). Default 1 -> Alt-Shows unveraendert.
    return ParamSpec("color_interval", "Farbwechsel-Intervall", "int", 1, 1, 16, 1,
                     when=(("color_cycle", (True,)),), styles=("RGB", "RGBW"),
                     tooltip="Farbe bleibt N Durchläufe gleich, bevor sie zur nächsten "
                             "Farbe der Sequence wechselt (1 = jeder Durchlauf, 2/4/8 = "
                             "langsamer)")

# ── ENG-08: Dimmerwert-Sequenz fuer den Dimmer-Chase (Pendant zu color_cycle) ──
def _dimmer_cycle():
    # Nur Dimmer-Style: Laeufer wechselt pro Runde durch die Dimmerwert-Sequenz.
    return ParamSpec("dimmer_cycle", "Dimmer pro Runde wechseln", "bool", False,
                     styles=("Dimmer",),
                     tooltip="Läufer wechselt pro Durchlauf durch die Dimmerwert-Sequenz "
                             "(explizite Helligkeitsstufen statt fester Min/Max-Bereich)")

def _dimmer_order():
    return ParamSpec("dimmer_order", "Dimmer-Reihenfolge", "select", "normal",
                     options=("normal", "random", "pingpong"),
                     when=(("dimmer_cycle", (True,)),), styles=("Dimmer",),
                     tooltip="Reihenfolge, in der pro Runde durch die Dimmerwert-Sequenz gewechselt wird")

def _dimmer_interval():
    return ParamSpec("dimmer_interval", "Dimmerwechsel-Intervall", "int", 1, 1, 16, 1,
                     when=(("dimmer_cycle", (True,)),), styles=("Dimmer",),
                     tooltip="Dimmerwert bleibt N Durchläufe gleich, bevor er zur nächsten "
                             "Stufe der Sequenz wechselt (1 = jeder Durchlauf, 2/4/8 = langsamer)")

# ── Bausteine fuer die Phase-4-Algorithmen (Fill / Random / ColorFade / Rainbow) ──
def _fill_dir():
    return ParamSpec("fill_dir", "Reihenfolge", "select", "left",
                     options=("left", "right", "top", "bottom",
                              "center_out", "outside_in", "diag", "random"),
                     tooltip="Reihenfolge, in der die Fixtures nacheinander gefüllt werden")

# ── WP-3/Abschnitt 4: zeitlicher Fill — style-abhängige Parameter ──────────────
def _fill_mode_intensity():
    return ParamSpec("fill_mode", "Füll-Modus", "select", "up",
                     options=("up", "down", "random"), styles=("Dimmer", "Shutter"),
                     tooltip="up=nacheinander heller · down=nacheinander dunkler · random=zufällige Helligkeit")

def _fill_mode_color():
    return ParamSpec("fill_mode", "Füll-Modus", "select", "target",
                     options=("target", "random", "sequence"), styles=("RGB", "RGBW"),
                     tooltip="target=zur aktiven Farbe · random=zufällige Farben · sequence=Farben aus der Color-Sequence")

def _fill_speed():
    return ParamSpec("fill_speed", "Füll-Tempo", "float", 1.0, 0.05, 10.0, 0.05,
                     "wie schnell die Fixtures nacheinander gefüllt werden")

def _fill_fade():
    # #5: eigener Key fixture_fade (NICHT "fade") + Label „Übergang pro Fixture" —
    # "fade" gehoert sonst dem raeumlichen Schweif (RADAR/RAIN) und wuerde beim
    # Algo-Wechsel durchbluten. Engine liest fixture_fade mit Fallback auf "fade".
    return ParamSpec("fixture_fade", "Übergang pro Fixture", "float", 0.4, 0.0, 1.0, 0.05,
                     "weicher Übergang je Fixture (0=harter Schritt, 1=über den ganzen Schritt)")

def _fill_hold():
    return ParamSpec("hold", "Halte-Zeit", "float", 0.0, 0.0, 20.0, 0.5,
                     "Pause (in Füll-Schritten), wenn alles gefüllt ist")

def _loop_mode():
    return ParamSpec("loop_mode", "Loop-Modus", "select", "restart",
                     options=("restart", "stay", "reverse", "fadeout"),
                     tooltip="neu starten / stehen bleiben / rückwärts leeren / ausfaden")

def _edge():
    return ParamSpec("edge", "Kante", "select", "hard", options=("hard", "fade"),
                     tooltip="harte oder weiche Füllkante")

def _mode(options):
    return ParamSpec("mode", "Modus", "select", "color", options=options,
                     tooltip="Random-Art")

# WP-2/Abschnitt 3: style-gefilterte Random-Modi (gleicher Key "mode", aber je
# Style nur der passende sichtbar -> kein Cross-Overwrite Dimmer/Color).
def _mode_color():
    return ParamSpec("mode", "Farb-Modus", "select", "color",
                     options=("color", "flash"), styles=("RGB", "RGBW"),
                     tooltip="zufällige Farbe aus der Color-Sequence / kurzer Farb-Blitz")

def _mode_intensity():
    return ParamSpec("mode", "Helligkeits-Modus", "select", "dimmer",
                     options=("dimmer", "strobe", "pulse", "sparkle"),
                     styles=("Dimmer", "Shutter"),
                     tooltip="zufällige Helligkeit / Strobe / Puls / Funkeln")

def _count():
    return ParamSpec("count", "Aktive Fixtures", "int", 1, 1, 64, 1,
                     "Anzahl gleichzeitig aktiver echter Fixtures")

def _rate():
    return ParamSpec("rate", "Rate", "float", 1.0, 0.1, 20.0, 0.1,
                     "Wie oft die Auswahl wechselt")

def _scope():
    return ParamSpec("scope", "Auswahl", "select", "all",
                     options=("all", "row", "col"),
                     tooltip="komplett zufällig / pro Reihe / pro Spalte")

def _no_repeat():
    return ParamSpec("no_repeat", "Wiederholschutz", "bool", True,
                     tooltip="vermeidet, dass direkt dieselben Fixtures erneut gewählt werden")

def _strobe_rate():
    return ParamSpec("strobe_rate", "Strobe-Rate", "int", 4, 1, 20, 1,
                     "Blitze pro Auswahl (nur Modus Strobe)",
                     when=(("mode", ("strobe",)),))

def _hold():
    # #5: eigener Key crossfade_hold (NICHT "hold") — FILL nutzt "hold" als Halte-
    # Schritte (0..20), ColorFade aber als Anteil (0..0.95). Geteilter Key liess den
    # Wert beim Algo-Wechsel durchbluten. Engine liest crossfade_hold, Fallback "hold".
    return ParamSpec("crossfade_hold", "Übergangs-Pause", "float", 0.0, 0.0, 0.95, 0.05,
                     "Anteil pro Farbe, bevor übergeblendet wird")

def _pingpong():
    return ParamSpec("pingpong", "Ping-Pong", "bool", False,
                     tooltip="Sequence vor und zurück durchlaufen")

def _saturation():
    return ParamSpec("saturation", "Sättigung", "float", 1.0, 0.0, 1.0, 0.05, "Farbsättigung")

def _value():
    # Label „Farb-Helligkeit" (nicht „Helligkeit"), damit es in der VC-Faderliste
    # NICHT mit dem Effekt-Master „Helligkeit" (intensity) kollidiert — der wirkt
    # NACH dem Rendern als Output-Master, value setzt die HSV-Helligkeit der Pixel.
    return ParamSpec("value", "Farb-Helligkeit", "float", 1.0, 0.0, 1.0, 0.05,
                     "HSV-Helligkeit der Regenbogen-Farben (vor dem Effekt-Master „Helligkeit“)")

def _hue_spread():
    # #5: eigener Key hue_spread (NICHT "spread") + Label „Farbzyklen" — sonst
    # blutet die WAVE-„Breite" (spread) beim Algo-Wechsel in die Regenbogen-
    # Farbzyklen. Engine liest hue_spread mit Fallback auf spread.
    return ParamSpec("hue_spread", "Farbzyklen", "float", 1.0, 0.25, 8.0, 0.25,
                     "Farbzyklen über die Matrix")

def _rainbow_movement():
    # #5: eigener Key rainbow_movement (NICHT "movement") + Label „Ausbreitung" —
    # die Regenbogen-Modi (linear/radial/…) sind andere als CHASE/WIPE
    # (normal/bounce/…); geteilter Key liess Werte beim Algo-Wechsel durchbluten.
    # Engine liest rainbow_movement mit Fallback auf movement.
    return ParamSpec("rainbow_movement", "Ausbreitung", "select", "linear",
                     options=("linear", "radial", "center_out", "outside_in"),
                     tooltip="Ausbreitung des Regenbogens")


# ── Baustein fuer CHECKER (Schachbrett/Wechsel) ───────────────────────────────
def _tile():
    return ParamSpec("tile", "Kachelgröße", "int", 1, 1, 8, 1,
                     "Wie viele benachbarte Fixtures dieselbe Farbe bekommen (1 = jedes einzeln)")

def _blink():
    return ParamSpec("blink", "Pro Beat umschalten", "bool", True,
                     tooltip="Farben pro Beat tauschen (Wechsellicht/Blinken). Aus = statisches Muster")


ALGO_META: dict[RgbAlgorithm, AlgoMeta] = {
    RgbAlgorithm.PLAIN:        AlgoMeta("Volle Fläche in C1.", False, (), colors=1),
    # ── Konsolidierte Grundalgorithmen (Phase 3) ──────────────────────────────
    RgbAlgorithm.CHASE:        AlgoMeta(
        "Lauflicht: Achse, Bewegung, Schweif (räumliche Nachzieh-Länge in %), optional "
        "Farb- bzw. Dimmerwechsel pro Runde (je nach Style).",
        True,
        (_axis(), _movement(("normal", "bounce", "center_out", "outside_in")),
         # Läufer-Anzahl + Schweif wertet die Engine NUR bei movement=normal aus
         # (bounce/center_out/outside_in ignorieren sie) -> nur dann anzeigen,
         # statt tote Regler zu zeigen.
         _runner_count(when=(("movement", ("normal",)),)), _runner_width(),
         _after_fade(when=(("movement", ("normal",)),)),
         # Farb-Styles: Farbwechsel pro Runde. Dimmer-Style: Dimmerwert pro Runde
         # (ENG-08) — style-gefiltert, daher nie beide gleichzeitig sichtbar.
         _color_cycle(), _color_order(), _color_interval(),
         _dimmer_cycle(), _dimmer_order(), _dimmer_interval(), _invert()),
        colors=1),
    RgbAlgorithm.WIPE:         AlgoMeta(
        "Wisch über die Matrix (Achse, Bewegung, Kanten-Fade).",
        True,
        (_axis(("H", "V")), _movement(("normal", "center_out", "outside_in", "bounce")),
         _edge_fade()),
        colors=2),
    RgbAlgorithm.WAVE:         AlgoMeta(
        "Welle mit wählbarem Ursprung (links/rechts/oben/unten/Mitte/radial).",
        True,
        (_origin(), _density(), _spread()),
        colors=2),
    RgbAlgorithm.GRADIENT:     AlgoMeta(
        "Scrollender Farbverlauf über die Color-Sequence (Achse, weich/Bänder).",
        True,
        (_axis(("H", "V")), _blend()),
        colors=2, sequence=True),
    RgbAlgorithm.RAINBOW:      AlgoMeta(
        "Regenbogen (Bewegung, Spread, Sättigung, Helligkeit).",
        True, (_rainbow_movement(), _hue_spread(), _saturation(), _value()), colors=0),
    RgbAlgorithm.FILL:         AlgoMeta(
        "Füllt Gruppe/Matrix Schritt für Schritt — je Style: Helligkeit (up/down/"
        "random) oder Farbe (Ziel/zufällig/Sequence). Reihenfolge, Tempo, Fade, Loop.",
        False,
        (_fill_mode_intensity(), _fill_mode_color(), _fill_dir(), _fill_speed(),
         _fill_fade(), _fill_hold(), _loop_mode()), colors=3, sequence=True),
    RgbAlgorithm.RANDOM:       AlgoMeta(
        "Zufalls-Effekt — Parameter richten sich nach dem Style (Color vs. Dimmer/Shutter).",
        False,
        (_mode_color(), _mode_intensity(),
         _count(), _rate(), _scope(), _no_repeat(), _strobe_rate()), colors=3, sequence=True),
    RgbAlgorithm.COLORFADE:    AlgoMeta(
        "Crossfade durch die Color-Sequence (deaktivierte Farben werden übersprungen).",
        True, (_hold(), _pingpong()), colors=3, sequence=True),
    RgbAlgorithm.STROBE:       AlgoMeta("Ganzes Feld blitzt an/aus.",  False, (), colors=1),
    RgbAlgorithm.CHECKER:      AlgoMeta(
        "Schachbrett/Wechsel: benachbarte Fixtures abwechselnd Farbe A/B (z. B. rot-blau "
        "oder rot-aus). Optional pro Beat umschalten (Wechsellicht).",
        False, (_tile(), _blink()), colors=2, sequence=True),
    # ── Texturen / Einzel-Looks (bewusst eigenständig) ────────────────────────
    RgbAlgorithm.RADAR:        AlgoMeta("Rotierender Radarstrahl.", True, (_beam_width("Strahlbreite"), _fade(), _invert()), colors=1),
    RgbAlgorithm.SPIRAL:       AlgoMeta("Rotierender Spiralarm.",  True,  (_turns(), _beam_width("Armbreite"), _invert()), colors=1),
    RgbAlgorithm.SINEPLASMA:   AlgoMeta("Sinus-Plasma C1↔C2.",     True,  (), colors=2),
    RgbAlgorithm.PINWHEEL:     AlgoMeta("Rotierende Segmente C1/C2.", True,
                                        # #5: eigener Key segment_count (NICHT runner_count) —
                                        # sonst blutet die CHASE-„Läufer-Anzahl" beim Algo-Wechsel
                                        # in die Windrad-Segmente (geteilter Param-Key). Engine
                                        # liest segment_count mit Fallback auf runner_count.
                                        (ParamSpec("segment_count", "Segmente", "int", 1, 1, 16, 1,
                                                   "Anzahl Segment-Paare (1..16)"),
                                         _invert()), colors=2),
    RgbAlgorithm.BREATHE:      AlgoMeta("Ganzes Feld pulsiert in C1.", False, (), colors=1),
    RgbAlgorithm.FIRE:         AlgoMeta("Flackernder Flammen-Look C1→C2.", False, (), colors=2),
    RgbAlgorithm.RAIN:         AlgoMeta("Fallende Tropfen je Spalte.", True, (_fade(),), colors=1),
}


def meta_for(algo: RgbAlgorithm) -> AlgoMeta:
    return ALGO_META.get(algo, AlgoMeta())


def spec_relevant(spec: ParamSpec, style_value: str, params: dict) -> bool:
    """True, wenn ``spec`` beim aktuellen Style + aktuellen Param-Werten relevant
    ist (= sichtbar UND schreibbar). Grundlage des style-abhaengigen Param-Systems
    (WP-2, Abschnitte 3/4/10): ein Dimmer-Parameter ist bei Style "RGB" nicht
    relevant, ein Strobe-Detail nur bei Modus "strobe" usw."""
    if spec.styles and style_value not in spec.styles:
        return False
    for cond in (spec.when or ()):
        try:
            key, allowed = cond
        except (TypeError, ValueError):
            continue
        if params.get(key) not in allowed:
            return False
    return True


def visible_specs(algo: RgbAlgorithm, style_value: str, params: dict) -> list:
    """Liste der aktuell relevanten ParamSpecs eines Algorithmus (style-/when-
    gefiltert). Die View baut daraus ihre Felder und schreibt NUR diese Werte."""
    meta = ALGO_META.get(algo)
    if not meta or not meta.params:
        return []
    # Fehlende Keys mit ihrem Default auffuellen, damit `when`-Bedingungen auch
    # greifen, bevor der steuernde Wert einmal explizit gesetzt wurde. Beispiel:
    # CHASE zeigt runner_count/after_fade per Default (movement=normal) — ohne
    # Auffuellen waere movement noch "nicht gesetzt" und beide Regler waeren
    # faelschlich ausgeblendet. (Setzt der Nutzer movement=bounce, ueberschreibt
    # params den Default und die Regler verschwinden korrekt.)
    effective = dict(params)
    for s in meta.params:
        effective.setdefault(s.key, s.default)
    return [s for s in meta.params if spec_relevant(s, style_value, effective)]
