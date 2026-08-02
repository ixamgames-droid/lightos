"""Was heisst „weiss, volle Helligkeit" fuer EIN Geraet? — eine Quelle.

BUG-FBW Slice 2 (Davids Entscheidung 2026-08-02): „Alles Weiß" soll **wirklich
alle gepatchten Geraete** weiss setzen, statt eine gebundene Szene zu starten,
die das Rig von damals kennt.

Dafuer braucht es pro Geraet die richtige Antwort — ein RGBW-PAR, ein Mover mit
Farbrad und ein reiner Dimmer-Kanal werden auf drei verschiedene Arten weiss.
Die Abbildung selbst gibt es schon (``color_utils``); dieses Modul setzt sie mit
Helligkeit und Shutter zu „voll offen, weiss" zusammen.

**Die Shutter-Regel ist die sicherheitsrelevante Stelle.** „Shutter" heisst je
nach Geraet Blende, Strobe oder Betriebsart, und ein geratener Wert kann ein
Geraet mitten in einer Panik-Situation in schnelles Blitzen schicken. Deshalb
wird der Shutter **nur** gesetzt, wenn das Profil ihn belegt — ein
``ChannelRange`` mit ``kind == "open"`` oder ein ``highlight_value``. Fehlt
beides, bleibt der Kanal in Ruhe: ein Geraet, das schon offen ist, bleibt offen,
und eines mit geschlossener Blende bleibt dunkel. Lieber ein dunkles Geraet als
ein unerwartet blitzendes (dieselbe Haltung wie beim Visualizer-Shutter-Zweig,
VIZ-COLORLESS: ohne Range-Daten wird nicht geraten).
"""
from __future__ import annotations

# Sentinel: „das Profil sagt nichts ueber einen offenen Zustand".
_KEINE_ANGABE = -1

# Helligkeits-Attribute, die auf voll gehen. Bewusst eine kleine, explizite
# Liste statt _DIM_INTENSITY_ATTRS aus app_state: dieses Modul soll ohne
# app_state importierbar bleiben (Leaf, vgl. Review-Checkliste Klasse 3).
_HELLIGKEIT = ("intensity", "dimmer", "master_dimmer")


def white_attrs_for_fixture(channels, open_value_of_channel) -> dict[str, int]:
    """``{attribut: wert}``, damit dieses Geraet weiss und voll aufgedreht ist.

    ``channels``   — die Kanaele des gepatchten Geraets (``get_channels_for_patched``).
    ``open_value_of_channel`` — ``app_state.open_value_of_channel``, hereingereicht
    statt importiert, damit dieses Modul ein Leaf bleibt. Bewusst die
    KANAL-Fassung: die Kanaele liegen hier ohnehin schon vor, ein zweiter
    Lookup ueber das Fixture waere nur eine weitere Gelegenheit zur Drift.

    Leeres Ergebnis heisst: an diesem Geraet gibt es nichts, das „weiss/voll"
    bedeuten koennte — dann fasst der Aufrufer es gar nicht erst an.
    """
    from src.core.color_utils import adapt_color_payload, color_attrs_for_fixture

    chans = list(channels or ())
    vorhanden = {getattr(c, "attribute", None) for c in chans}
    out: dict[str, int] = {}

    # 1) Farbe — die bestehende Abbildung entscheidet geraetegerecht (echtes
    #    RGB(W), Farbrad-Slot oder reiner Weiss-Kanal).
    farbe = color_attrs_for_fixture(chans, (255, 255, 255))
    if farbe:
        # Dieselbe RGBW-Reduktion wie ueberall sonst (reines Weiss -> W traegt es).
        out.update(adapt_color_payload(vorhanden, farbe))

    # 2) Helligkeit auf voll — jedes vorhandene Dimm-Attribut.
    for attr in _HELLIGKEIT:
        if attr in vorhanden:
            out[attr] = 255

    # 3) Shutter NUR mit Beleg (s. Modul-Doku).
    shutter_ch = next((c for c in chans
                       if getattr(c, "attribute", None) == "shutter"), None)
    if shutter_ch is not None:
        wert = open_value_of_channel(shutter_ch, _KEINE_ANGABE)
        if wert != _KEINE_ANGABE:
            out["shutter"] = int(wert)

    return out


def white_map(fixtures, channels_of, open_value_of_channel,
              exclude_fids=()) -> dict[int, dict[str, int]]:
    """Die Weiss-Schicht fuer eine ganze Geraeteliste.

    ``exclude_fids`` — Geraete, um die sich schon jemand anderes kuemmert (die
    an den Knopf gebundene Szene). Ihre Werte bleiben unangetastet, damit ein
    bewusst eingestellter Weiss-Look (z. B. warmweisse PARs) erhalten bleibt und
    die Ueberdeckung nur die LUECKE fuellt.
    """
    aus = set(exclude_fids or ())
    layer: dict[int, dict[str, int]] = {}
    for fx in fixtures:
        fid = int(getattr(fx, "fid", -1))
        if fid < 0 or fid in aus:
            continue
        attrs = white_attrs_for_fixture(channels_of(fx), open_value_of_channel)
        if attrs:
            layer[fid] = attrs
    return layer
