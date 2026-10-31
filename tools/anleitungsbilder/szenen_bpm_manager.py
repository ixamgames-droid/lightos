"""DOC-77: Bilder fuer ``docs/anleitung_bpm_manager/`` — Quelle „Aus“ setzt den
Takt auf 0 (BPM-33).

Neu erzeugen: ``venv/bin/python tools/anleitungsbilder.py bpm_manager``.

Die uebrigen Bilder dieses Ordners (``erkennung_*.png``, ``tempo_buses.png``,
``generator.png``) entstanden von Hand; hier entstehen nur die Bilder mit
Nummer ``NN_``.

Die Sandbox hat keinen Audio-Server, und OS2L wuerde einen Netz-Server
starten. Der Vorher-Zustand ist deshalb Quelle „Lied-Analyse (Player)“ (kein
Geraet, kein Netz) mit einem Takt von 128 BPM, den die Szene ueber
``request_bpm(…, "timeline")`` anbietet — wie es die Lied-Analyse im Modus Auto
tut. Damit die Statuszeile dazu passt („128,0 BPM aus dem Player-Titel“ statt
„kein analysierter Titel im Player“), liegt im Player ein Platzhalter-Titel mit
fester 128-BPM-Kurve; er wird nie abgespielt (das Audio-Backend entsteht erst
beim Abspielen) und beim Aufraeumen durch die vorige Playlist ersetzt.
Danach wird die Quelle ueber die echte Quelle-Liste auf „Aus“ gestellt; die Anzeige faellt auf „--“ (Takt 0). Am Ende steht die
Quelle wieder auf „Aus“, der Takt auf 0 und der Modus auf Auto.
"""
from __future__ import annotations

from anleitungsbilder.runner import Frame, Szene, SzenenFehler
from anleitungsbilder.szenen_erste_schritte import bild, rechteck

ZIEL = "docs/anleitung_bpm_manager/img"

_VORHER_BPM = 128.0
# GIF-Ausschnitt: Kopfzeile (BPM-Anzeige rechts oben) bis unter die Statuszeile.
_ZUSCHNITT = (0, 28, 1600, 296)
# PNG: ganze Breite mit Menue und Sektionsleiste, bis unter „Erweitert“.
_PNG_AUSSCHNITT = (0, 0, 1600, 364)


def _view(ui):
    return ui.win._bpm_manager_view


def _quelle(ui, daten: str):
    """Quelle ueber die echte Liste waehlen (wie eine Auswahl mit der Maus)."""
    view = _view(ui)
    idx = view._cmb_source.findData(daten)
    if idx < 0:
        raise SzenenFehler(f"BPM-Quelle {daten!r} fehlt in der Liste")
    view._cmb_source.setCurrentIndex(idx)
    view._reflect_state()
    ui.pump(0.4)


_ALTE_PLAYLIST: list = []


def _titel_im_player():
    """Platzhalter-Titel mit analysierter 128-BPM-Kurve in den Player legen
    (nur Playlist-Daten; abgespielt wird nichts)."""
    from src.core.audio.media_player import Track, get_media_player
    mp = get_media_player()
    if mp.current_track is not None and mp.current_track.title == "Beispiel-Titel":
        return
    _ALTE_PLAYLIST[:] = [list(mp.tracks)]
    kurve = {"v": 2, "engine": "builtin", "beats_per_bar": 4,
             "duration_ms": 180000, "step_ms": 5000, "window_ms": 10000,
             "segments": [[0, _VORHER_BPM, 0.9], [180000, _VORHER_BPM, 0.9]]}
    mp.set_tracks([Track(path="Musik/Beispiel-Titel.mp3", title="Beispiel-Titel",
                         genre="House", bpm=_VORHER_BPM, bpm_source="analysis",
                         bpm_timeline=kurve)])


def _vorher(ui):
    """Quelle „Lied-Analyse (Player)“, Modus Auto, Takt 128 BPM."""
    from src.core.engine.bpm_manager import BpmMode, get_bpm_manager
    _titel_im_player()
    mgr = get_bpm_manager()
    mgr.set_mode(BpmMode.AUTO)
    _quelle(ui, "song")
    mgr.request_bpm(_VORHER_BPM, "timeline")
    _view(ui)._reflect_state()
    ui.pump(0.6)
    if abs(mgr.bpm - _VORHER_BPM) > 0.5:
        raise SzenenFehler(f"Vorher-Takt nicht gesetzt (BPM {mgr.bpm})")


def _aus(ui):
    from src.core.engine.bpm_manager import get_bpm_manager
    _quelle(ui, "off")
    ui.pump(0.4)
    if get_bpm_manager().bpm != 0:
        raise SzenenFehler(f"Quelle „Aus“: Takt ist {get_bpm_manager().bpm}, erwartet 0")


def _aufraeumen(ui):
    """Quelle „Aus“, Takt 0, Auto — kein laufender Takt in spaeteren Bildern."""
    from src.core.engine.bpm_manager import BpmMode, get_bpm_manager
    _quelle(ui, "off")
    mgr = get_bpm_manager()
    mgr.reset()
    mgr.set_mode(BpmMode.AUTO)
    if _ALTE_PLAYLIST:
        from src.core.audio.media_player import get_media_player
        get_media_player().set_tracks(_ALTE_PLAYLIST.pop())
    _view(ui)._reflect_state()
    ui.pump(0.3)


def _kreise(ui):
    view = _view(ui)
    w = ui.win
    return [
        (rechteck(w, view._cmb_source), 1, "unten"),
        (rechteck(w, view._lbl_bpm), 2, "unten"),
        (rechteck(w, view._status_box), 3, "unten"),
        (rechteck(w, w._lbl_bpm), 4, "unten"),
    ]


def _bild(ui):
    return bild(ui, kreise=_kreise(ui))


def _bild_aus(ui):
    """Nachher-Bild, unten abgeschnitten: unter „Erweitert“ ist die Seite leer."""
    from PySide6.QtCore import QRect
    _vorher(ui)
    _aus(ui)
    flaeche = bild(ui, kreise=_kreise(ui))
    pix = flaeche.pixmap().copy(QRect(*_PNG_AUSSCHNITT))
    flaeche.setFixedSize(pix.size())
    flaeche.setPixmap(pix)
    return flaeche


SZENEN = [
    Szene("01_quelle_aus", sektion="BPM", unterreiter="Erkennung",
          dialog=_bild_aus, nachher=_aufraeumen,
          titel="Quelle „Aus“: Takt 0 — BPM-Anzeige „--“, Statuszeile „Erkennung aus“"),
    Szene("02_quelle_aus_ablauf", sektion="BPM", unterreiter="Erkennung",
          vorher=_vorher, nachher=_aufraeumen, gif_zuschnitt=_ZUSCHNITT,
          frames=[
              Frame(dauer_s=1.8, dialog=_bild),
              Frame(dauer_s=2.2, schritt=_aus, dialog=_bild),
          ],
          titel="GIF: Quelle von „Lied-Analyse“ auf „Aus“ — der Takt fällt von 128 auf 0"),
]
