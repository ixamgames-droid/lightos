"""EINE Quelle fuer das Kopfformular eines Fixture-Profils (FM-35).

Zwei Dialoge legen dasselbe Datenmodell an — ``FixtureGeneratorDialog`` und
``FixtureEditorDialog``. Beide starten mit einem VORBELEGTEN Modellnamen im
Feld, und beide liessen einen Mausklick auf "Speichern" unmittelbar nach dem
Oeffnen ein vollstaendiges Profil in der Bibliothek anlegen (gemessen:
Generator ``Generic / Neues Fixture / NEUES FI`` mit EINEM Klick, Editor
``ADB / Neues Fixture / NEUES FI`` mit zweien). Der Nutzer hat dabei nichts
eingegeben — das Profil traegt ausschliesslich Vorgabewerte.

★ **Warum der Platzhalter der Hebel ist und nicht der Kurzname.** Das Item
  vermutete ein leeres Pflichtfeld. Nachgemessen erreicht der KURZNAME die
  Datenbank nie leer (``build_profile_payload`` ersetzt ihn durch die ersten
  acht Zeichen des Modellnamens, ``fixture_db.create_user_profile`` notfalls
  durch ``"FIXTURE"``; in der echten Bibliothek haben 0 von 1791 Profilen
  einen leeren Kurznamen). Auch der HERSTELLER traegt nicht: ``"Generic"``
  ist ein echter Hersteller mit 21 Profilen. Was den unbeabsichtigten
  Eintrag verlaesslich kennzeichnet, ist der unveraenderte
  PLATZHALTER-Modellname.

★ **Eine Frage, eine Stelle** (Hausregel 7). ``kopf_beanstandung`` ist die
  einzige Funktion, die "ist das Kopfformular ausgefuellt?" beantwortet;
  beide Dialoge rufen sie und zeigen ihre Rueckgabe woertlich an. Auch der
  Platzhalter-TEXT steht nur hier: er war vorher vier Mal im Code
  (Generator-Default, Payload-Rueckfall, Sync-Rueckfall, Editor-Feld) und
  waere sonst genau die Sorte Konstante, die an einer Stelle geaendert wird
  und an drei anderen stehenbleibt.

⚠️ **Bewusst KEIN Praefix-Vergleich** (Hausregel 6, Gegenprobe). Geprueft
  wird auf GLEICHHEIT mit dem Platzhalter, nicht auf "faengt damit an" —
  ``"Neues Fixture Mk II"`` ist ein zulaessiger Geraetename und muss
  gespeichert werden koennen. Verglichen wird nach ``strip``, ohne Beachtung
  der Gross-/Kleinschreibung und mit zusammengefassten Leerraeumen, weil
  ``" neues  fixture "`` derselbe unveraenderte Vorgabewert ist und sonst ein
  zweiter Weg an der Regel vorbei bliebe (Hausregel 8).

Leaf-Modul ohne Projekt-Importe: die UI-Widgets sollen es zyklenfrei
importieren koennen.
"""
from __future__ import annotations

# Der Vorgabewert, der in BEIDEN Dialogen im Feld "Modell" steht.
PLATZHALTER_MODELL = "Neues Fixture"


def _normiert(text) -> str:
    """Vergleichsform eines Feldinhalts: Leerraum zusammengefasst, Rand
    entfernt, Gross-/Kleinschreibung egal. ``None`` wird zu ``""``."""
    return " ".join(str(text or "").split()).casefold()


def ist_platzhalter_modell(modell) -> bool:
    """``True``, wenn ``modell`` noch der unveraenderte Vorgabewert ist.

    Nur GLEICHHEIT zaehlt; ``"Neues Fixture Mk II"`` ist ein echter Name.
    """
    return _normiert(modell) == _normiert(PLATZHALTER_MODELL)


def kopf_beanstandung(hersteller, modell) -> str | None:
    """Die EINE Antwort auf "ist das Kopfformular ausgefuellt?".

    Gibt ``None`` zurueck, wenn gespeichert werden darf, sonst den
    anzuzeigenden Meldungstext (fertig formuliert, damit beide Dialoge
    dieselbe Auskunft geben und nicht jeder seine eigene erfindet).

    Beanstandet wird in dieser Reihenfolge: fehlender Hersteller, fehlender
    Modellname, unveraenderter Platzhalter-Modellname.
    """
    if not str(hersteller or "").strip():
        return "Hersteller fehlt."
    if not str(modell or "").strip():
        return "Modell-Name fehlt."
    if ist_platzhalter_modell(modell):
        return (f"„{PLATZHALTER_MODELL}“ ist nur der Platzhalter. "
                "Bitte einen echten Modell-Namen eintragen.")
    return None
