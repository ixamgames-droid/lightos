#!/usr/bin/env python3
"""Vollbild der VC-Widget-Showcase aufnehmen — OHNE Desktop, ohne Fotoapparat.

    ./venv/bin/python tools/build_vc_widgets_showcase.py     # Show + Geometrie
    ./venv/bin/python tools/capture_vc_widgets.py            # Vollbild
    ./venv/bin/python tools/crop_vc_widgets.py docs/anleitung_vc_widgets/_capture/full.png

## Warum nicht `gnome-screenshot`

Bisher entstand das Vollbild als **Bildschirmfoto der laufenden App**: App
starten, Virtuelle Konsole oeffnen, Showcase laden, `tools/app.sh shot`. Das
funktioniert, hat aber drei Eigenschaften, die man erst merkt, wenn die Bilder
falsch sind:

1. **Es braucht Davids Bildschirm.** Ein X11-Screenshot fotografiert den echten
   Desktop — in einer Sitzung ohne Anzeige (CI, Remote-Lauf, Nacht-Loop) geht
   es gar nicht, und waehrend er davorsitzt, uebernimmt es seinen Vordergrund.
2. **Es ist nicht wiederholbar.** Fenstergroesse, Skalierung, Theme, Position
   der Konsole im Fenster — alles geht mit ins Bild ein. Zwei Aufnahmen
   desselben Stands sind nie pixelgleich.
3. **Niemand kann es pruefen.** Ein Bildschirmfoto laesst sich in keinem Test
   erzeugen, also gab es auch keinen, der bemerkt haette, dass ein Widget vom
   Nachbarn ueberdeckt wird.

`QWidget.grab()` rendert dasselbe Canvas offscreen in ein Bild. Kein Fenster,
kein Compositor, keine Fensterdekoration — und deshalb reproduzierbar.

## Was gleich bleibt

Die **Kalibrier-Kacheln** (Magenta/Cyan) werden weiter mitgezeichnet und
`crop_vc_widgets.py` rechnet unveraendert ueber ihren ABSTAND. Das ist Absicht:
der Zuschnitt soll nicht davon abhaengen, womit das Vollbild entstanden ist.
Ein per `app.sh shot` aufgenommenes Bild bleibt also weiterhin gueltiges
Eingangsmaterial — dieses Werkzeug ist der bequemere Weg, nicht der einzige.

⚠️ **Vor dem Ueberschreiben hinsehen.** `--vergleich <alt.png>` legt die
Bildmasse nebeneinander und meldet, wenn das neue Bild kleiner ausfaellt als das
alte; ein Vollbild, das Widgets abschneidet, sieht in der Datei-Liste genauso
aus wie ein gutes.
"""
from __future__ import annotations

import os
import sys
import time

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)

# Offscreen ist hier der Betriebsmodus, nicht der Notnagel — anders als beim
# Render-Benchmark, der ausdruecklich ein echtes Fenster braucht (dort waere
# SwiftShader auf der CPU die falsche Messung). Gezeichnet wird von Qt, nicht
# von der GPU; das Ergebnis ist dasselbe.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# ⚠️ VOR jedem `src.core`-Import: dieses Werkzeug ruft `load_show()` und
# arbeitet damit auf dem globalen AppState. Ohne die Isolation liefe das gegen
# `data/current_show.db` — also gegen Davids echte Show, nur um ein Doku-Bild
# zu machen. `tests/test_tools_db_isolation.py` haelt die Regel fest, und sie
# hat hier beim ersten Gate-Lauf sofort zugeschlagen.
sys.path.insert(0, os.path.join(_REPO, "tools"))
import _gen_env  # noqa: F401,E402  # DEMO-02: spawn-sichere Env-Schalter vor src.core

from PySide6.QtWidgets import QApplication                       # noqa: E402
from PySide6.QtCore import QSize                                 # noqa: E402

SHOW = os.path.join(_REPO, "shows", "VC_Widgets_Showcase.lshow")
OUT = os.path.join(_REPO, "docs", "anleitung_vc_widgets", "_capture", "full.png")

# Rand ueber die belegte Flaeche hinaus. Der Zuschnitt gibt jedem Bild `pad`
# Pixel Luft (Default 8), die muessen im Vollbild vorhanden sein.
_RAND = 40

# Wie lange das Canvas vor dem Grab laufen darf. 2 s reichen fuer die
# 200-ms-Timer der Cue-Liste und ein paar Durchlaeufe der Effekt-Vorschau.
_AUFWAERMEN_S = 2.0

# Diese drei Widgets zeigen ohne laufenden Effekt nichts Brauchbares und werden
# deshalb aus der zweiten Aufnahme geschnitten (Begruendung im Code unten).
_BRAUCHT_LAUFENDEN_EFFEKT = {"VCEffectDisplay", "VCEffectEditor", "VCColorList"}


def main() -> int:
    ziel = OUT
    vergleich = None
    argv = sys.argv[1:]
    while argv:
        a = argv.pop(0)
        if a == "--vergleich" and argv:
            vergleich = argv.pop(0)
        elif not a.startswith("-"):
            ziel = a

    if not os.path.exists(SHOW):
        print(f"FEHLER: {SHOW} fehlt — erst tools/build_vc_widgets_showcase.py "
              f"laufen lassen.", file=sys.stderr)
        return 2

    app = QApplication.instance() or QApplication([])
    from src.core.app_state import get_state
    from src.core.show.show_file import load_show
    from src.ui.virtualconsole.vc_canvas import VCCanvas

    ok, meldung = load_show(SHOW)
    if not ok:
        print(f"FEHLER: Show nicht ladbar: {meldung}", file=sys.stderr)
        return 2
    layout = get_state()._vc_layout
    anzahl = len(layout.get("widgets", []))
    if not anzahl:
        print("FEHLER: die Show hat kein VC-Layout — nichts aufzunehmen.",
              file=sys.stderr)
        return 2

    canvas = VCCanvas()
    canvas.from_dict(layout)

    from src.core.engine.function_manager import get_function_manager
    fm = get_function_manager()

    # Groesse aus dem INHALT, nicht geraten: sonst schneidet das Vollbild genau
    # die Widgets ab, um derentwillen es entsteht.
    rechts = unten = 0
    from src.ui.virtualconsole.vc_widget import VCWidget
    kinder = [w for w in canvas.children() if isinstance(w, VCWidget)]
    for w in kinder:
        g = w.geometry()
        rechts = max(rechts, g.right())
        unten = max(unten, g.bottom())
    canvas.resize(QSize(rechts + _RAND, unten + _RAND))
    canvas.show()

    def laufen_lassen(sekunden: float) -> None:
        """Echte Zeit vergehen lassen, nicht nur Events pumpen.

        Die Widget-Timer (Cue-Liste 200 ms, Effekt-Anzeige 60 ms) feuern in
        einer engen `processEvents()`-Schleife nie — ohne Wartezeit blieben
        beide Widgets leer, und ein leeres Widget sieht im Bild aus wie ein
        funktionierendes.
        """
        ende = time.monotonic() + sekunden
        while time.monotonic() < ende:
            app.processEvents()
            time.sleep(0.02)

    laufen_lassen(_AUFWAERMEN_S)
    bild = canvas.grab()
    if bild.isNull() or bild.width() < 100:
        print("FEHLER: leerer Grab — das Canvas hat nicht gezeichnet.",
              file=sys.stderr)
        return 2

    # ── Zweite Aufnahme MIT laufenden Effekten ───────────────────────────────
    #
    # ⚠️ **Ein laufender Effekt macht zwei Bilder besser und drei schlechter.**
    # Gemessen beim Abgleich gegen den alten Stand:
    #
    # * **braucht ihn:** `VCEffectDisplay` und `VCEffectEditor` zeichnen ihre
    #   Pixel-Vorschau nur bei `fn._running`, sonst steht dort „keine
    #   Pixel-Vorschau". `VCColorList` zeigt „laeuft" statt „gestoppt".
    # * **leidet darunter:** `VCColor` faellt in den gesperrten Zustand
    #   (Schloss-Symbol, abgedunkelt), weil der Effekt die Farbkanaele haelt —
    #   fuer eine Anleitung „so sieht das Farb-Widget aus" ist das irrefuehrend.
    #   Und die **Kalibrier-Kacheln** sind selbst `VCColor` mit Ziel PROGRAMMER:
    #   der Demo-Chase faerbt sie orange, womit der bildbasierte Cropper-Weg
    #   ausfaellt (deshalb die mitgeschriebene `calibration.json`).
    #
    # Also beide Zustaende aufnehmen und je Widget den passenden verwenden.
    # Die Cue-Liste braucht dafuer uebrigens NICHTS Laufendes — ihre Eintraege
    # sind statisch; sie war nur leer, solange die Timer nicht liefen.
    for fn in fm.all():
        try:
            fm.start(fn.id)
        except Exception as e:
            print(f"  Hinweis: {getattr(fn, 'name', fn.id)} startet nicht: {e}")
    laufend = [f for f in fm.all() if getattr(f, "_running", False)]
    print(f"laufende Funktionen: {len(laufend)}/{len(fm.all())}")
    laufen_lassen(_AUFWAERMEN_S)
    bild_laufend = canvas.grab()

    if vergleich and os.path.exists(vergleich):
        from PIL import Image
        alt = Image.open(vergleich)
        print(f"Vergleich: alt {alt.size[0]}x{alt.size[1]} · "
              f"neu {bild.width()}x{bild.height()}")
        if bild.width() < alt.size[0] or bild.height() < alt.size[1]:
            print("WARNUNG: das neue Vollbild ist KLEINER als das alte — pruefen, "
                  "ob am Rand etwas fehlt, bevor es uebernommen wird.",
                  file=sys.stderr)

    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    if not bild.save(ziel):
        print(f"FEHLER: {ziel} nicht schreibbar", file=sys.stderr)
        return 2

    # ⚠️ **Die Kalibrierung wird MITGESCHRIEBEN, nicht zurueckgerechnet.**
    #
    # `crop_vc_widgets.py` sucht sonst die Magenta-Kachel im Bild und leitet
    # Massstab und Ursprung daraus ab. Das ist beim Foto der laufenden App
    # richtig — dort kennt niemand die Skalierung. Hier ist es falsch, aus zwei
    # Gruenden:
    #
    # 1. **Es ist keine Messung.** Dieses Werkzeug hat das Canvas selbst
    #    gerendert: Massstab 1:1, Ursprung (0,0). Das zurueckzurechnen ist
    #    Ritual, das nur schiefgehen kann.
    # 2. **Es GEHT hier nicht mehr.** Die Kalibrier-Kacheln sind `VCColor` mit
    #    Ziel `PROGRAMMER` — sobald die Effekte laufen (und laufen muessen sie,
    #    sonst sind Cue-Liste und Pixel-Vorschau leer), faerbt der Effekt sie um.
    #    Gemessen: statt Magenta stand dort das Orange des Demo-Chase, und der
    #    Cropper brach mit „Kachel nicht gefunden" ab.
    #
    # Der Foto-Weg bleibt unveraendert: fehlt diese Datei, sucht der Cropper
    # weiter nach der Kachel.
    ziel_laufend = os.path.join(os.path.dirname(ziel), "full_running.png")
    if not bild_laufend.isNull():
        bild_laufend.save(ziel_laufend)

    seite = os.path.join(os.path.dirname(ziel), "calibration.json")
    import json
    with open(seite, "w", encoding="utf-8") as f:
        json.dump({
            "quelle": "capture_vc_widgets.py (offscreen grab)",
            "bild": os.path.basename(ziel),
            "bild_laufend": os.path.basename(ziel_laufend),
            # Welche Widgets aus der Aufnahme MIT laufenden Effekten kommen —
            # alle anderen aus der ruhenden (s. Begruendung oben).
            "aus_laufendem_bild": sorted(_BRAUCHT_LAUFENDEN_EFFEKT),
            "groesse": [bild.width(), bild.height()],
            "scale": 1.0,
            "origin": [0, 0],
        }, f, indent=2)
    print(f"{anzahl} Widgets · Canvas {bild.width()}x{bild.height()}")
    print(f"  ruhend  -> {ziel}")
    print(f"  laufend -> {ziel_laufend}")
    print(f"  Kalibrierung (1:1, Ursprung 0,0) -> {seite}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
