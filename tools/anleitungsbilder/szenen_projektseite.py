"""DOC-16: Bilder fuer die Projektseite (README) — ``docs/projektseite/img/``.

Neu erzeugen: ``venv/bin/python tools/anleitungsbilder.py projektseite``.
Die Szenen laufen der Reihe nach im SELBEN Fenster; was eine Szene einstellt
(Auswahl, Programmer-Werte), sieht die naechste noch.
"""
from anleitungsbilder.runner import Szene

ZIEL = "docs/projektseite/img"


def _pars_farbverlauf(ui):
    """PAR 1…8 waehlen, voll aufziehen, Farbverlauf Rot -> Blau setzen."""
    pars = ui.info["pars"]
    ui.waehle(pars)
    ui.wert(pars, "intensity", 255)
    for i, fid in enumerate(pars):
        anteil = i / (len(pars) - 1)
        ui.wert([fid], "color_r", round(255 * (1 - anteil)))
        ui.wert([fid], "color_g", 0)
        ui.wert([fid], "color_b", round(255 * anteil))
    ui.reiter("Color")


def _mover_waehlen(ui):
    mover = ui.info["mover"]
    ui.waehle(mover)
    ui.wert(mover, "intensity", 255)
    ui.reiter("Intensity")


def _nichts_waehlen(ui):
    ui.waehle([])


def _bpm_manuell(ui):
    """Ohne Audio-Geraet: Quelle „Aus", Tempo von Hand auf 128 BPM."""
    from src.core.engine.bpm_manager import BpmMode, get_bpm_manager
    view = ui.win._bpm_manager_view
    idx = view._cmb_source.findData("off")
    if idx >= 0:
        view._cmb_source.setCurrentIndex(idx)
    mgr = get_bpm_manager()
    mgr.set_mode(BpmMode.MANUAL)
    mgr.set_manual_bpm(128.0)
    view._reflect_state()


def _bpm_zurueck(ui):
    """Tempo wieder auf Auto: ein laufender 128-BPM-Takt liesse die
    Beat-Anzeige im Kopf in jedem spaeteren Bild anders blinken."""
    from src.core.engine.bpm_manager import BpmMode, get_bpm_manager
    get_bpm_manager().set_mode(BpmMode.AUTO)
    ui.win._bpm_manager_view._reflect_state()


SZENEN = [
    Szene("01_ueberblick", sektion="Programmer", unterreiter="Attribute",
          titel="Hauptfenster: Programmer mit acht PARs und Farbverlauf",
          vorher=_pars_farbverlauf, warte_s=0.8),
    Szene("02_patch", sektion="Patchen", unterreiter="Patch",
          titel="Patch mit der Doku-Demo",
          marken=[("+ Gerät hinzufügen", 1, "Gerät hinzufügen"),
                  ("Auto-Patch", 2, "Adressen automatisch vergeben")]),
    Szene("03_programmer", sektion="Programmer", unterreiter="Attribute",
          titel="Programmer: Moving Heads gewählt, Werkzeuge",
          vorher=_mover_waehlen,
          marken=[("Farb-Werkzeug...", 1, "Farb-Werkzeug"),
                  ("Positions-Werkzeug...", 2, "Positions-Werkzeug"),
                  ("Bibliothek", 3, "Bibliothek")]),
    Szene("04_vc", sektion="Virtual Console",
          titel="Virtual Console im Bedienmodus"),
    Szene("05_playback", sektion="Playback", unterreiter="Playback",
          titel="Cue-Liste mit drei Cues"),
    Szene("07_buehne", sektion="Bühne", titel="2D-Bühnenansicht",
          vorher=_nichts_waehlen),
    # BPM zuletzt: der Takt laeuft ab hier; ``nachher`` stoppt ihn trotzdem,
    # falls jemand weitere Szenen dahinter haengt.
    Szene("06_bpm", sektion="BPM", unterreiter="Erkennung",
          titel="BPM-Erkennung, Tempo manuell", vorher=_bpm_manuell,
          nachher=_bpm_zurueck, warte_s=1.0),
]
