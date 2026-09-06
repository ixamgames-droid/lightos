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

# ENG-24: Farb-Attribute, die KEINE additiven Emitter sind und deshalb NICHT auf
# 0 duerfen. Ein Farbrad ist eine ORTSANGABE, kein Pegel — der Wert 0 waere dort
# irgendein Slot, meist „offen", aber eben geraten (Lehre aus ENG-15). Es wird
# stattdessen ueber dieselbe Abbildung auf seinen weissen Slot gefahren.
#
# ⚠️ Waechst die Bibliothek um ein weiteres `color*`-Attribut, muss hier
# entschieden werden: additiver Emitter (dann auf 0) oder Ortsangabe (dann
# hierher). `tests/test_eng24_panik_weiss.py` faellt rot, sobald ein unbekanntes
# auftaucht — damit die Entscheidung nicht still uebergangen wird.
_KEINE_EMITTER = ("color_wheel", "colour_wheel", "color")


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

    # 1b) ENG-24: JEDER weitere Farb-Emitter ausdruecklich auf 0.
    #
    # ``color_attrs_for_fixture`` beantwortet „welche Kanaele machen weiss?" —
    # es nennt deshalb nur `color_r/g/b/w`. Was es NICHT nennt, behaelt seinen
    # Vorwert, und genau das war der Fehler: auf einem RGBWA+UV-PAR blieben
    # Amber und UV stehen, wo sie gerade standen. Das Ergebnis war hell, aber
    # nicht weiss — bei einer PANIK-Funktion die falscheste Art zu scheitern.
    #
    # Gemessen: 11 Modi der Bibliothek tragen `color_a` und/oder `color_uv`.
    # Ein Override, der „alles weiss" verspricht, muss auch die Kanaele
    # bestimmen, die er auf 0 will — sonst ist er kein Override, sondern ein
    # Zuschlag auf einen unbekannten Zustand.
    for attr in sorted(a for a in vorhanden
                       if a and a.startswith("color") and a not in _KEINE_EMITTER):
        out.setdefault(attr, 0)

    # 1c) Das Farbrad / der Farb-Makro-Kanal, falls er NEBEN echten
    #     Farbkanaelen sitzt.
    #
    # ``color_attrs_for_fixture`` hat zwar einen Zweig fuer „weiss auf dem Rad",
    # aber er wird nur erreicht, wenn das Geraet KEIN RGB hat. Gemessen haben
    # **17 Modi** beides — dort faellt das Rad hinten runter, und ein auf einem
    # Farbslot stehendes Rad faerbt das Panik-Weiss weiter ein.
    #
    # ★★★ Den Rad-Zweig hier einfach mitzubenutzen waere ein FEHLER GEWESEN, und
    # zwar ein sichtbarer. Er beantwortet die Frage „welcher Slot kommt der
    # Wunschfarbe am naechsten?" — sinnvoll, wenn das Rad die EINZIGE Farbquelle
    # ist. Hier ist die Frage eine andere: „welcher Slot legt das Rad AUS DEM
    # WEG, damit die echten Farbkanaele gelten?" Gemessen mit der ersten
    # Fassung: DOTZ TPAR und DOTZ MATRIX haben keinen weiss benannten Slot, also
    # gewann der naechstgelegene bunte — die Panik-Funktion haette die Lampen
    # auf **Blau** gestellt. Schlimmer als gar nichts zu tun.
    #
    # Die richtige Antwort steht schon im Haus und ist hier schon importiert:
    # ``open_value_of_channel`` liefert den Slot mit ``kind == "open"`` (sonst
    # ``highlight_value``, sonst nichts). Genau dieselbe Regel wie beim Shutter
    # unten, samt derselben Haltung: ohne Beleg wird nicht geraten. Gemessen
    # trifft sie „Manuelle RGB-Steuerung" (DOTZ TPAR), „Aus" (FPQ WH12X) und
    # „Offen (RGBW-Mischung aktiv)" (MAC Aura) — und laesst den ADJ 5PX HEX in
    # Ruhe, dessen Makro-Kanal gar keine Slots hinterlegt hat.
    rad = next((c for c in chans
                if (getattr(c, "attribute", None) or "") in _KEINE_EMITTER), None)
    if rad is not None and getattr(rad, "attribute", None) not in out:
        wert = open_value_of_channel(rad, _KEINE_ANGABE)
        if wert != _KEINE_ANGABE:
            out[rad.attribute] = int(wert)

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
