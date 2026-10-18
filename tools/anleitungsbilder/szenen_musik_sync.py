"""DOC-16: Bilder fuer ``docs/anleitung_musik_sync/`` (Musik-Sync & Auto-Show).

Neu erzeugen: ``venv/bin/python tools/anleitungsbilder.py musik_sync``.

Die Playlist besteht aus drei Platzhalter-Titeln (``Musik/Beispiel-Titel N.mp3``,
die Dateien gibt es nicht): kein Musikordner und kein echter Titel gehoeren ins
Bild. Die Sandbox hat keine Audio-Geraete. Fuer das Bild „Play“ meldet der
Player deshalb nur seinen Zustand „spielt“ (``MediaPlayer._set_playing``) und
uebernimmt die Lied-BPM wie beim echten Play (``_apply_track_bpm``) — Musik-
und BPM-Anzeige folgen ueber ihre echten Signale. Zu hoeren ist nichts, und
nach dem Bild steht der Player wieder.

Nebenbefund beim Bauen (DOC-16, 14.10.2026): ``MusicShowDirector.start_show``
kehrt zurueck, wenn die GLOBALE Funktionsliste leer ist — und startet dann
auch den Lied-Look des ersten Titels nicht (der Lied-Look kommt erst beim
naechsten Trackwechsel). Das Bild zeigt deshalb bewusst keinen laufenden
Effekt.

Die VC-Bank „Tempo & Musik“ legt ``szenen_vc.bank2_anlegen`` an.
"""
from __future__ import annotations

from anleitungsbilder.runner import Szene, SzenenFehler
from anleitungsbilder.szenen_erste_schritte import (
    bild, knopf, platz_oben, rechteck, vereinigung)
from anleitungsbilder.szenen_vc import (
    bank, bank2_anlegen, bank2_widget, bearbeiten, funktion, vc)

ZIEL = "docs/anleitung_musik_sync/img"

TITEL = [("Beispiel-Titel 1", "House", 124.0),
         ("Beispiel-Titel 2", "Pop", 118.0),
         ("Beispiel-Titel 3", "Techno", 132.0)]


def _player():
    from src.core.audio.media_player import get_media_player
    return get_media_player()


def _musik(ui):
    return ui.win._music_view


def _playlist(ui):
    """Drei Platzhalter-Titel; Titel 1 bekommt Lauflicht + Kreis als Auto-Show."""
    from src.core.audio.media_player import Track
    mp = _player()
    if [t.title for t in mp.tracks] != [t for t, _g, _b in TITEL]:
        mp.set_tracks([Track(path=f"Musik/{t}.mp3", title=t, genre=g, bpm=b,
                             bpm_source="tag")
                       for t, g, b in TITEL])
    view = _musik(ui)
    view._write_playlist()
    view._assign_autoshow(0, [funktion("Farb-Lauflicht"), funktion("Kreis")])
    if not view._chk_autoshow.isChecked():
        view._chk_autoshow.setChecked(True)         # echter Weg: _on_autoshow
    view._table.selectRow(0)
    ui.pump(0.3)


def _vorher_tab(ui):
    _playlist(ui)


def _bild_tab(ui):
    from PySide6.QtCore import QRect
    view = _musik(ui)
    w = ui.win
    chk = rechteck(w, view._chk_autoshow)
    chk = QRect(chk.x(), chk.y(), min(chk.width(), view._chk_autoshow.sizeHint().width() + 8),
                chk.height())
    return bild(ui, kreise=[
        (rechteck(w, view._table), 1, "unten"),
        (rechteck(w, knopf(view, "Ordner laden…")), 2, "oben"),
        (rechteck(w, view._btn_autoshow), 3, "oben"),
        (chk, 4, "rechts"),
    ])


def _bild_dialog(ui):
    """„Auto-Show für Lied…“ ueber den echten Knopfweg; im modalen Loop
    aufgenommen und mit Cancel geschlossen (die Zuweisung bleibt wie in
    :func:`_playlist` gesetzt)."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox,
                                   QListWidget)
    _playlist(ui)
    view = _musik(ui)
    ergebnis = {}

    def _aufnehmen():
        dlg = QApplication.activeModalWidget()
        if not isinstance(dlg, QDialog):
            ergebnis["fehler"] = "Dialog „Auto-Show für …“ ging nicht auf"
            return
        try:
            dlg.resize(460, 380)
            ui.pump(0.3)
            liste = dlg.findChild(QListWidget)
            ok = dlg.findChild(QDialogButtonBox).button(
                QDialogButtonBox.StandardButton.Ok)
            ergebnis["bild"] = bild(ui, dlg, [
                (rechteck(dlg, liste), 1, "rechts"),
                (rechteck(dlg, ok), 2, "links"),
            ], titel=dlg.windowTitle())
        except SzenenFehler as e:
            ergebnis["fehler"] = str(e)
        finally:
            dlg.reject()

    QTimer.singleShot(300, _aufnehmen)
    view._btn_autoshow.click()
    if "fehler" in ergebnis:
        raise SzenenFehler(ergebnis["fehler"])
    if "bild" not in ergebnis:
        raise SzenenFehler("Dialog wurde nicht aufgenommen")
    return ergebnis["bild"]


def quelle_aus(ui):
    """BPM-Quelle „Aus“: die Sandbox hat keinen Audio-Server; mit PC-Audio
    stuende im Bild ein Fehlerbanner, das beim Nutzer nicht erscheint."""
    view = ui.win._bpm_manager_view
    idx = view._cmb_source.findData("off")
    if idx < 0:
        raise SzenenFehler("BPM-Quelle „Aus“ fehlt in der Liste")
    view._cmb_source.setCurrentIndex(idx)
    view._reflect_state()
    ui.pump(0.3)


def _spielt(ui):
    quelle_aus(ui)
    _playlist(ui)
    bearbeiten(ui, False)
    bank2_anlegen(ui)
    mp = _player()
    mp.index = 0
    mp._apply_track_bpm()          # wie MediaPlayer.play(): Lied-BPM uebernehmen
    mp._set_playing(True)          # Zustand „spielt“ (ohne Audio-Geraet)
    ui.pump(1.5)
    if not mp.is_playing:
        raise SzenenFehler("Player meldet nicht „spielt“")


def _bild_spielt(ui):
    w = ui.win
    with platz_oben(ui, vc(ui)):
        musik = vereinigung([rechteck(w, bank2_widget(ui, n))
                             for n in ("musik", "zurueck", "play", "vor")])
        return bild(ui, kreise=[(musik, 1, "rechts")])


def _stopp(ui):
    from src.core.engine.function_manager import get_function_manager
    _player()._set_playing(False)
    get_function_manager().stop_all()
    bank(ui, 0)
    ui.pump(0.5)


def _bild_quelle(ui):
    quelle_aus(ui)
    view = ui.win._bpm_manager_view
    w = ui.win
    return bild(ui, kreise=[
        (rechteck(w, view._cmb_source), 1, "unten"),
        (rechteck(w, knopf(view, "TAP")), 2, "unten"),
        (rechteck(w, knopf(view, "Auto")), 3, "unten"),
    ])


SZENEN = [
    Szene("01_musik_tab", sektion="E/A", unterreiter="Musik", vorher=_vorher_tab,
          dialog=_bild_tab,
          titel="Musik-Tab: Playlist, Ordner laden, Auto-Show für Lied, globaler Schalter"),
    Szene("02_autoshow_fuer_lied", sektion="E/A", unterreiter="Musik",
          dialog=_bild_dialog,
          titel="Dialog „Auto-Show für …“: Funktionen je Lied"),
    Szene("03_play_vc", sektion="Virtual Console", vorher=_spielt,
          dialog=_bild_spielt, nachher=_stopp,
          titel="Play: Musik-Anzeige mit Media-Tasten in der VC"),
    Szene("04_bpm_quelle", sektion="BPM", unterreiter="Erkennung",
          dialog=_bild_quelle,
          titel="BPM-Sektion, Erkennung: Quelle (hier „Aus“), TAP, Auto"),
]
