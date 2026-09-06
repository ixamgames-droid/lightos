"""OUT-56: was die immer sichtbare Ausgabe-Anzeige der Statusleiste sagt.

★ **Warum als eigenes Modul und nicht als Methode am Fenster.** Die Regel sass
in ``MainWindow._update_ausgabe_label`` und war nur pruefbar, indem man ein
ganzes Hauptfenster baute — mit MIDI-Threads, Fixture-Datenbank und Renderer.
Genau daran ist am selben Tag schon die Freeze-Anzeige gescheitert (ENG-23: ein
``repaint()`` auf einem elternlosen Widget riss den Renderer mit,
``Fatal Python error: Aborted``). *Eine Anzeige-Regel gehoert dorthin, wo man
sie befragen kann, ohne sie zu malen.* Vorbild im Haus: ``head_cell_colors.py``.

Hier steht deshalb nur Rechnung, kein Qt: rein → ``(text, farbe, tooltip)``.

──────────────────────────────────────────────────────────────────────────────

**Der Befund, den dieses Modul behebt.** Ein Universum, in dem Geraete gepatcht
sind, das aber **gar keinen Ausgang** hat, wurde in der immer sichtbaren
Statusleiste nicht gemeldet. Und zwar nicht aus Nachlaessigkeit: die beiden
Quellen, aus denen die Anzeige ihren Text baut, kannten es ueberhaupt nicht.
Gemessen mit einem sACN-Ausgang auf U1 und Geraeten in U1 **und** U3::

    sendet_wirklich   {1: True, 3: False}
    ausgabe_status()  [(1, 'sACN')]        <- U3 fehlt
    sende_probleme()  []                   <- U3 fehlt

Die Anzeige konnte es also nicht verschweigen — sie konnte es nicht wissen.

⚠️ **Was der Backlog-Eintrag OUT-56 daneben behauptete, stimmt nicht (mehr).**
„Wird in der laufenden App nirgends gemeldet" ist seit OUT-52 falsch: der
DMX-Monitor sagt woertlich ``⚠ Universe {n} hat keinen Ausgang — nur
gerechnet``. Nur sieht man das erst, wenn man den Monitor oeffnet **und** dort
genau dieses Universum waehlt (Vorgabe ist U1). Ebenso schon erledigt: ein
konfigurierter-aber-toter Enttec-Port steht ueber ``enttec_port_notes`` in
``_lbl_enttec`` (HW-5b), und ein registrierter Adapter, der nicht sendet, kommt
ueber ``ausgabe_status()['verbunden'] is False`` hier als „sendet nicht" an
(OUT-51). Uebrig blieb genau die eine Luecke oben.
"""
from __future__ import annotations

#: Statusleisten-Farben. Rot = etwas ist kaputt, Orange = etwas fehlt.
FARBE_KAPUTT = "color: #ff4444;"
FARBE_FEHLT = "color: #ffb454;"
FARBE_NORMAL = ""

#: So viele Ausgaenge stehen im Text; der Rest wird als „+n" gezaehlt.
MAX_IM_TEXT = 3


def ausgabe_label(wege, probleme, ohne_ausgang) -> tuple[str, str, str]:
    """``(text, stylesheet, tooltip)`` fuer die Ausgabe-Anzeige.

    ``wege``        — ``OutputManager.ausgabe_status()``
    ``probleme``    — ``OutputManager.sende_probleme()``
    ``ohne_ausgang``— Universen MIT Geraeten, die keinen Adapter haben

    ★ **Die Reihenfolge ist die Aussage.** Der Text zeigt nur die ersten
    :data:`MAX_IM_TEXT` Eintraege — bei einem groesseren Rig waere der
    ausgefallene sonst genau der, den man nicht sieht, waehrend drei
    funktionierende Platz wegnehmen. Deshalb: erst was gar nicht ankommt, dann
    was kaputt ist, dann der Rest.
    """
    wege = list(wege or [])
    probleme = list(probleme or [])
    ohne = sorted(set(int(u) for u in (ohne_ausgang or [])))

    # Tick-/Modifier-Stoerungen haengen an keinem Ausgang, wuerden in `wege`
    # also fehlen — sie gehoeren aber genauso gemeldet.
    sonstige = [p for p in probleme if p.get("weg") in ("Tick", "Modifier")]
    kaputt = [w for w in wege if w.get("verbunden") is False]

    if not wege and not ohne:
        return ("Ausgabe: —", FARBE_FEHLT,
                "Kein Universum gibt DMX aus. Output-Einstellungen öffnen und "
                "einem Universum einen Ausgang geben.")

    ohne_teile = [f"U{u} ohne Ausgang" for u in ohne]
    rest = [w for w in wege if w not in kaputt]
    teile = (ohne_teile
             + [f"U{w['universum']} {w['weg']}" for w in kaputt + rest])
    gesamt = len(teile)
    sichtbar = teile[:MAX_IM_TEXT]
    if gesamt > MAX_IM_TEXT:
        sichtbar.append(f"+{gesamt - MAX_IM_TEXT}")
    text = "Ausgabe: " + " · ".join(sichtbar)

    if not (kaputt or sonstige or ohne):
        tooltip = "\n".join(
            f"U{w['universum']} {w['weg']}"
            + (f" → {w['ziel']}" if w.get("ziel") else "")
            for w in wege)
        return (text, FARBE_NORMAL, tooltip)

    zeilen = [f"U{u}: kein Ausgang — die Kanäle werden nur gerechnet" for u in ohne]
    zeilen += [f"U{w['universum']} {w['weg']}: sendet nicht"
               + (f" ({w['problem']})" if w.get("problem") else "")
               for w in kaputt]
    zeilen += [f"{p['weg']}: {p.get('fehler')} Fehler in Folge ({p.get('text')})"
               for p in sonstige]
    if ohne:
        zeilen.append("")
        zeilen.append("In den Output-Einstellungen einen Ausgang zuweisen.")
    # ★ Rot schlaegt Orange: „ist kaputt" ist dringender als „fehlt". Wer beides
    # hat, soll die dringendere Farbe sehen — die Zeilen nennen ohnehin beides.
    farbe = FARBE_KAPUTT if (kaputt or sonstige) else FARBE_FEHLT
    return (f"⚠ {text}", farbe, "\n".join(zeilen))
