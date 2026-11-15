"""UI-83: Touch-Gesten — Schalter und Drei-Finger-Aktion.

Welche Gesten am Finger wirken, haengt am Menschen vor diesem Bildschirm,
nicht an der Show: Ablage in ``ui_prefs.json`` (Abschnitt ``touch_gesten``),
dieselbe Datei wie die uebrigen Geraete-Vorlieben. Andere Abschnitte der Datei
bleiben unangetastet; eine unlesbare Datei wird nicht ueberschrieben.

===================  ========  ==============================================
Schluessel           Vorgabe   Geste
===================  ========  ==============================================
``lang_menue``       an        langes Druecken = Kontextmenue (UI-114)
``lang_erklaerung``  an        langes Druecken = Erklaerung (UI-123)
``zwei_finger_zoom`` an        zwei Finger zoomen/verschieben (UI-117)
``mehr_finger``      an        weitere Finger bedienen VC-Fader/-Knoepfe (UI-118)
``halten_antippen``  an        Halten + Antippen = Mehrfachauswahl (UI-83)
``zwei_finger_bank`` an        zwei Finger waagerecht = VC-Bank blaettern (UI-83)
``drei_finger``      ``aus``   Drei-Finger-Tippen: Aktion aus ``DREI_FINGER_AKTIONEN``
===================  ========  ==============================================

Die Drei-Finger-Aktion ist bewusst nie eine Sicherheitsaktion (BLACKOUT,
STOP ALL, GO, LASER NOT-AUS, Touch-Sperre): ein versehentliches Tippen mit
drei Fingern darf die Show nicht anhalten oder dunkel machen. Die Liste unten
ist abschliessend; ein unbekannter gespeicherter Wert gilt als ``aus``.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields

ABSCHNITT = "touch_gesten"

#: (Wert, Beschriftung). Abschliessend — keine Sicherheitsaktion.
DREI_FINGER_AKTIONEN = (
    ("aus", "Aus (nichts tun)"),
    ("programmer_leeren", "Programmer leeren"),
    ("page_naechste", "Nächste Page"),
    ("page_vorherige", "Vorherige Page"),
)
DREI_FINGER_WERTE = tuple(w for w, _ in DREI_FINGER_AKTIONEN)


@dataclass
class GestenSchalter:
    lang_menue: bool = True
    lang_erklaerung: bool = True
    zwei_finger_zoom: bool = True
    mehr_finger: bool = True
    halten_antippen: bool = True
    zwei_finger_bank: bool = True
    drei_finger: str = "aus"

    @classmethod
    def aus_dict(cls, daten) -> "GestenSchalter":
        s = cls()
        if not isinstance(daten, dict):
            return s
        for f in fields(cls):
            if f.name not in daten:
                continue
            wert = daten[f.name]
            if f.name == "drei_finger":
                s.drei_finger = wert if wert in DREI_FINGER_WERTE else "aus"
            elif isinstance(wert, bool):
                setattr(s, f.name, wert)
        return s

    def als_dict(self) -> dict:
        return asdict(self)


#: (Schluessel, Titel, Erklaerung) fuer die Uebersicht in den Einstellungen.
UEBERSICHT = (
    ("lang_menue", "Lange drücken = Kontextmenü",
     "Finger 0,6 s still halten öffnet das Menü, das die Maus per Rechtsklick "
     "bekommt. Nie bei VC-Elementen im Spielbetrieb (FLASH halten)."),
    ("lang_erklaerung", "Lange drücken = Erklärung",
     "Ohne Menü zeigt langes Drücken die Erklärung (Tooltip) groß über dem Finger."),
    ("zwei_finger_zoom", "Zwei Finger: zoomen und verschieben",
     "2D-Bühne und Show-Zeitleiste: Finger spreizen/zusammenziehen zoomt."),
    ("mehr_finger", "Mehrere Fader gleichzeitig",
     "In der Virtual Console bedient jeder Finger sein eigenes Element."),
    ("halten_antippen", "Halten + Antippen = Mehrfachauswahl",
     "Einen Finger auf einem Gerät (2D-Bühne) oder VC-Element (Bearbeiten-"
     "Modus) liegen lassen und mit einem zweiten Finger weitere antippen."),
    ("zwei_finger_bank", "Zwei Finger waagerecht = Bank blättern",
     "Auf freier Fläche der Virtual Console mit zwei Fingern nach links "
     "(nächste Bank) oder rechts (vorherige Bank) wischen. Nie, wenn ein "
     "Finger auf einem Fader oder Knopf liegt."),
)


def _pfad() -> str:
    from src.core.paths import app_data_dir
    return os.path.join(app_data_dir(), "ui_prefs.json")


def _lies(pfad: str):
    if not os.path.exists(pfad):
        return {}
    try:
        with open(pfad, encoding="utf-8") as f:
            daten = json.load(f)
    except Exception:                                    # noqa: BLE001
        return None
    return daten if isinstance(daten, dict) else None


def laden(pfad: str | None = None) -> GestenSchalter:
    daten = _lies(pfad or _pfad())
    return GestenSchalter.aus_dict((daten or {}).get(ABSCHNITT))


def speichern(schalter: GestenSchalter, pfad: str | None = None) -> bool:
    """Schreibt nur den eigenen Abschnitt. ``False`` = nicht gespeichert."""
    pfad = pfad or _pfad()
    try:
        daten = _lies(pfad)
        if daten is None:
            print("[gesten] ui_prefs.json unlesbar - Gesten nicht gespeichert")
            return False
        daten[ABSCHNITT] = schalter.als_dict()
        os.makedirs(os.path.dirname(pfad) or ".", exist_ok=True)
        tmp = f"{pfad}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(daten, f, indent=2, ensure_ascii=False)
        os.replace(tmp, pfad)
        return True
    except Exception as e:                               # noqa: BLE001
        print(f"[gesten] nicht gespeichert: {e}")
        return False
