"""UI-140: Haken-Bild fuer Kontrollkaestchen und ankreuzbare Menue-Eintraege.

Das dunkle Theme (``assets/themes/dark.qss``) zeichnet AUS als leeren Rahmen
und AN als blau gefuelltes Kaestchen. Der weisse Haken darin kommt von hier:
ein ``url()`` braucht einen absoluten Pfad, und der haengt davon ab, wo das
Programm liegt (auch gefroren). Der Zustand haengt so nicht mehr allein an
der Farbe.

Im Touch-Modus wird das Menue-Kaestchen groesser; die Zeilenhoehe (>= 44 px)
kommt unveraendert aus ``touch_keyboard.allgemein_touch_qss``.
"""
from __future__ import annotations

import os

#: Kaestchen in Menue-Eintraegen im Touch-Modus (Zeile bleibt >= 44 px).
MENUE_INDIKATOR_TOUCH = 22


def haken_url(name: str = "haken.svg") -> str:
    try:
        from src.core.paths import programm_datei
        pfad = programm_datei("assets", "icons", name)
    except Exception:
        pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "assets", "icons", name)
    return os.path.abspath(pfad).replace("\\", "/")


def haken_qss(touch: bool = False) -> str:
    """Regeln, die das Hauptfenster hinter ``dark.qss`` anhaengt."""
    h = haken_url()
    # Nachbesserung UI-140: TEILWEISE (Tri-State) bekommt einen Strich.
    strich = haken_url("strich.svg")
    qss = (
        f"QCheckBox::indicator:checked {{ image: url({h}); }}\n"
        f"QCheckBox::indicator:indeterminate {{ image: url({strich}); }}\n"
        f"QMenu::indicator:non-exclusive:checked {{ image: url({h}); }}\n"
    )
    if touch:
        r = MENUE_INDIKATOR_TOUCH // 2
        qss += (
            f"QMenu::indicator {{ width: {MENUE_INDIKATOR_TOUCH}px; "
            f"height: {MENUE_INDIKATOR_TOUCH}px; left: 8px; }}\n"
            f"QMenu::indicator:exclusive:unchecked, QMenu::indicator:exclusive:checked "
            f"{{ border-radius: {r}px; }}\n"
        )
    return qss
