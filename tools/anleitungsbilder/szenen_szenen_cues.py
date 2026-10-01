"""DOC-16: Bilder fuer die Anleitung „Szenen, Snaps & Cue-Listen" —
``docs/anleitung_szenen_cues/img/``.

Neu erzeugen: ``venv/bin/python tools/anleitungsbilder.py szenen_cues``.
Die Szenen laufen der Reihe nach im SELBEN Fenster. Was hier angelegt wird
(Snap „PAR Rot", Snapshot-Slot 1, Cueliste „Meine Show", Executor 1, eine
VC-Cueliste), raeumt Szene 10 wieder ab; die Szenen 11/12 (GO ohne Executor,
UI-68) legen sich ihren Stand selbst an und raeumen ihn ebenso ab — bei
``--alle`` sollen nachfolgende Anleitungen die Doku-Demo unveraendert sehen.

Die Hilfen fuer Rahmen ueber Listeneintraegen und fuer Dialoge ueber dem
Fenster stammen aus ``szenen_programmer_grundlagen`` (dort beschrieben).
"""
from anleitungsbilder.runner import Szene
from anleitungsbilder.szenen_programmer_grundlagen import (
    _RAHMEN, _hilfsrahmen, _im_dialog, _leeren, _pv, _ueber_fenster)

ZIEL = "docs/anleitung_szenen_cues/img"

SNAP = "PAR Rot"
STACK = "Meine Show"
_FARBEN = [("Rot", (255, 0, 0)), ("Grün", (0, 255, 0)), ("Blau", (0, 0, 255))]


# ── Hilfen ──────────────────────────────────────────────────────────────────

def _knopf_in(wurzel_fn, text):
    """Finder: sichtbarer Knopf mit ``text`` NUR innerhalb eines Bereichs
    (``Speichern``/``Löschen`` gibt es im Fenster mehrfach)."""
    def finder(ui):
        from PySide6.QtWidgets import QAbstractButton
        for b in wurzel_fn(ui).findChildren(QAbstractButton):
            if b.isVisible() and b.text().replace("&", "") == text:
                return b
        return None
    finder.__name__ = f"knopf_{text}"
    return finder


def _rand_links(widget, px):
    """Linken Innenrand einer Seite vergroessern (nur fuers Bild).

    Der Werkzeug-Kern (``marker.platzieren``) sucht fuer jeden Nummernkreis
    einen freien Platz neben dem Rahmen. Bei Elementen direkt am Fensterrand,
    rundum von beschrifteten Nachbarn umgeben (Snapshot-Raster, Trefferliste,
    Knopfzeilen der Playback-Seite), gibt es keinen — links fehlt schlicht der
    Platz. Ein paar Pixel mehr Rand schaffen ihn; die Bedienelemente selbst
    bleiben unveraendert. ``px=None`` stellt den urspruenglichen Rand wieder her.
    """
    lay = widget.layout()
    if not hasattr(widget, "_doku_rand"):
        widget._doku_rand = lay.contentsMargins()
    m = widget._doku_rand
    if px is None:
        lay.setContentsMargins(m)
    else:
        lay.setContentsMargins(px, max(m.top(), 18), m.right(), m.bottom())


def _bib(ui):
    return _pv(ui)._snap_file_panel


def _pb(ui):
    return ui.win._playback_view


def _rot(ui, fids):
    ui.wert(fids, "intensity", 255)
    ui.wert(fids, "color_r", 255)
    ui.wert(fids, "color_g", 0)
    ui.wert(fids, "color_b", 0)


def _stack(ui):
    for st in ui.state.cue_stacks:
        if st.name == STACK:
            return st
    return None


# ── 1–3: Snap in der Bibliothek ─────────────────────────────────────────────

def _programmer_rot(ui):
    _leeren(ui)
    pars = ui.info["pars"]
    _pv(ui)._select_fids(pars)
    _rot(ui, pars)
    ui.reiter("Color")
    ui.pump(0.2)


def _kanaldialog(ui):
    from src.ui.views.snap_file_panel import ChannelSelectDialog, _scope_heads
    state = ui.state

    def bauen(eltern):
        return ChannelSelectDialog(state.programmer, eltern,
                                   scope_fids=state.active_scope_fids(),
                                   scope_heads=_scope_heads(state))
    return _ueber_fenster(ui, bauen, 460, 260)


def _dialog_checkbox(prefix):
    def finder(ui, dlg):
        from PySide6.QtWidgets import QCheckBox
        for cb in dlg.findChildren(QCheckBox):
            if cb.isVisible() and cb.text().startswith(prefix):
                return cb
        return None
    finder.__name__ = f"checkbox_{prefix}"
    return finder


def _snap_anlegen(ui):
    """Wie „Speichern" → Kanäle „Color" → Name „PAR Rot"."""
    from src.core.engine.snap_library import get_snap_library
    _programmer_rot(ui)
    lib = get_snap_library()
    if not any(s.name == SNAP for s in lib.snaps()):
        werte = {fid: {k: v for k, v in attrs.items() if k.startswith("color_")}
                 for fid, attrs in ui.state.programmer.items()}
        lib.add_snap(SNAP, "", werte)
    _bib(ui)._refresh_tree()
    # Programmer leeren und Auswahl weg: so sieht man, dass „Anwenden" die
    # Farbe zurueckholt (Bild zeigt den Zustand VOR dem Klick).
    _leeren(ui)
    ui.reiter("Intensity")
    ui.pump(0.2)


def _snap_eintrag(ui):
    tree = _bib(ui)._tree
    it = next(iter(tree.findItems(SNAP, _match_rekursiv())), None)
    if it is None:
        return None
    tree.setCurrentItem(it)
    return _hilfsrahmen(tree.viewport(), tree.visualItemRect(it), _RAHMEN + "snap")


def _match_rekursiv():
    from PySide6.QtCore import Qt
    return Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive


def _szene_eintrag(name):
    def finder(ui):
        tree = _bib(ui)._tree
        it = next(iter(tree.findItems(name, _match_rekursiv())), None)
        if it is None:
            return None
        return _hilfsrahmen(tree.viewport(), tree.visualItemRect(it),
                            _RAHMEN + "szene")
    finder.__name__ = f"eintrag_{name}"
    return finder


# ── 4: Assistent ────────────────────────────────────────────────────────────

def _assistent(ui):
    _programmer_rot(ui)
    ui.reiter("Assistent")
    ui.pump(0.2)


def _effektliste(ui):
    return _pv(ui)._effects_list


# ── 5: Snapshots ────────────────────────────────────────────────────────────

def _snapshots(ui):
    from src.ui.views.snapshots_view import Snapshot
    _leeren(ui)
    view = ui.win._snapshots_view
    werte = {fid: {"intensity": 255, "color_r": 255, "color_g": 0, "color_b": 0}
             for fid in ui.info["pars"]}
    # Wie ein Klick auf den leeren Slot 1 mit Name „PAR Rot" — ohne Schreiben
    # der Arbeitsdatei (_save_to_disk), das Bild braucht sie nicht.
    view._snapshots[0] = Snapshot(name=SNAP, values=werte)
    view._buttons[0].refresh()
    _rand_links(view, 36)
    ui.pump(0.2)


def _slot(nr):
    def finder(ui):
        return ui.win._snapshots_view._buttons[nr - 1]
    finder.__name__ = f"slot_{nr}"
    return finder


def _snapshots_weg(ui):
    from src.ui.views.snapshots_view import Snapshot
    view = ui.win._snapshots_view
    view._snapshots[0] = Snapshot()
    view._buttons[0].refresh()
    _rand_links(view, None)


# ── 6: Preset-Browser ───────────────────────────────────────────────────────

def _preset_browser(ui):
    _leeren(ui)
    view = ui.win._preset_browser_view
    view._reload_entries()
    view._search.setText("PAR")
    _rand_links(view, 36)
    ui.pump(0.2)


def _preset_suche(ui):
    return ui.win._preset_browser_view._search


def _preset_treffer(ui):
    lst = ui.win._preset_browser_view._list
    if lst.count() == 0:
        return None
    return _hilfsrahmen(lst.viewport(), lst.visualItemRect(lst.item(0)),
                        _RAHMEN + "treffer")


def _preset_status(ui):
    return ui.win._preset_browser_view._status


def _preset_zurueck(ui):
    view = ui.win._preset_browser_view
    view._search.setText("")
    _rand_links(view, None)


# ── 7–9: Playback ───────────────────────────────────────────────────────────

def _neue_cueliste(ui):
    """Wie „+ Neu" mit dem Namen „Meine Show"."""
    _leeren(ui)
    if _stack(ui) is None:
        ui.state.new_cue_stack(STACK)
    pb = _pb(ui)
    _rand_links(pb, 36)
    pb._refresh_stack_combo()
    i = pb._combo_stack.findText(STACK)
    pb._combo_stack.setCurrentIndex(i)
    ui.pump(0.2)


def _cues_aufnehmen(ui):
    """Drei Cues wie mit „+ Cue aufnehmen": Farbe setzen, aufnehmen, leeren."""
    _neue_cueliste(ui)
    st = _stack(ui)
    pars = ui.info["pars"]
    if not st.cues:
        for nr, (name, (r, g, b)) in enumerate(_FARBEN, 1):
            ui.state.clear_programmer()
            ui.wert(pars, "intensity", 255)
            ui.wert(pars, "color_r", r)
            ui.wert(pars, "color_g", g)
            ui.wert(pars, "color_b", b)
            ui.state.record_cue(st, float(nr), f"Alle PAR {name}")
    ui.state.clear_programmer()
    pb = _pb(ui)
    pb._refresh_table()
    ui.pump(0.2)


def _executor_zuweisen(ui):
    pb = _pb(ui)
    ex = pb._executors_widgets[0]
    ex.refresh_from_state()
    ex._combo.setCurrentIndex(ex._combo.findText(STACK))
    ui.pump(0.1)


def _cues_und_executor(ui):
    _cues_aufnehmen(ui)
    _executor_zuweisen(ui)


def _go(ui):
    """Cues aufgenommen, Executor 1 belegt, einmal GO gedrueckt."""
    _cues_aufnehmen(ui)
    _executor_zuweisen(ui)
    st = _stack(ui)
    st.stop()
    _pb(ui)._go()
    ui.pump(0.3)


def _executor(nr):
    def finder(ui):
        return _pb(ui)._executors_widgets[nr - 1]
    finder.__name__ = f"executor_{nr}"
    return finder


def _aktive_cue(ui):
    return _pb(ui)._lbl_current.parentWidget()        # QGroupBox „Aktive Cue"


def _cuetabelle(ui):
    return _pb(ui)._table


# ── 10: VC-Cueliste ─────────────────────────────────────────────────────────

_VC_CUELISTE = "doku_vc_cueliste"


def _vc_cueliste(ui):
    """Eine VC-Cueliste auf Bank 1, Executor-Slot 0 (= „Ex 1")."""
    from PySide6.QtCore import QPoint
    canvas = ui.win._vc_view._canvas
    alt = canvas.findChild(object, _VC_CUELISTE)
    if alt is None:
        w = canvas._add_widget("VCCueList", QPoint(720, 360))
        w.setObjectName(_VC_CUELISTE)
        w.stack_slot = 0
        w.show()
    ui.pump(0.5)


def _vc_widget(ui):
    from PySide6.QtWidgets import QWidget
    return ui.win._vc_view._canvas.findChild(QWidget, _VC_CUELISTE)


def _vc_go(ui):
    w = _vc_widget(ui)
    return w._btn_go if w is not None else None


def _alles_abraeumen(ui):
    """Alles, was diese Anleitung angelegt hat, wieder entfernen."""
    from src.core.engine.snap_library import get_snap_library
    canvas = ui.win._vc_view._canvas
    w = _vc_widget(ui)
    if w is not None:
        canvas._remove_widget(w)
    st = _stack(ui)
    if st is not None:
        st.stop()
        ui.state.remove_cue_stack(st)
    _pb(ui)._executors_widgets[0].refresh_from_state()
    _rand_links(_pb(ui), None)
    lib = get_snap_library()
    for s in list(lib.snaps()):
        if s.name == SNAP:
            lib.remove_snap(s.id)
    _bib(ui)._refresh_tree()
    _leeren(ui)
    ui.pump(0.2)


# ── 11–12: GO ohne Executor (UI-68) ────────────────────────────────────────

def _hinweis(ui):
    return _pb(ui)._lbl_hinweis


def _go_ohne_executor(ui):
    """Cues aufgenommen, Liste auf KEINEM Executor, GO im Playback-Tab:
    der echte Weg (``PlaybackView._go``) legt sie auf den ersten freien
    Executor und zeigt den Hinweis."""
    _cues_aufnehmen(ui)
    st = _stack(ui)
    st.stop()
    _pb(ui)._go()
    ui.pump(0.3)


def _fader_null(ui):
    """Alle sichtbaren Executoren ohne Liste mit Fader auf 0: GO bindet nicht,
    sondern meldet den freien Executor mit Fader 0."""
    _alles_abraeumen(ui)
    _cues_aufnehmen(ui)
    pe = ui.state.playback_engine
    sichtbar = len(_pb(ui)._executors_widgets)
    for ex in pe.executors:
        if ex.slot <= sichtbar and ex.stack is None:
            ex.fader_value = 0.0
    _pb(ui)._refresh_executors()
    # „Aktive Cue" stammt sonst noch aus Szene 11 (andere Liste) — wie STOP.
    _pb(ui)._stop()
    _pb(ui)._go()
    ui.pump(0.3)


def _fader_zurueck(ui):
    for ex in ui.state.playback_engine.executors:
        ex.fader_value = 1.0
    _alles_abraeumen(ui)


SZENEN = [
    Szene("01_speichern", sektion="Programmer", unterreiter="Attribute",
          titel="Programmer-Stand: acht PARs rot, Bibliothek",
          vorher=_programmer_rot,
          marken=[(_knopf_in(_bib, "Speichern"), 1, "Speichern"),
                  (_knopf_in(_bib, "Ordner +"), 2, "Ordner +")]),
    Szene("02_kanaele", sektion="Programmer", unterreiter="Attribute",
          titel="Welche Kanäle sollen gespeichert werden?",
          vorher=_programmer_rot, dialog=_kanaldialog,
          marken=[(_im_dialog(_dialog_checkbox("Intensity")), 1, "Intensity"),
                  (_im_dialog(_dialog_checkbox("Color")), 2, "Color"),
                  (_im_dialog("OK"), 3, "OK")]),
    Szene("03_snap_abrufen", sektion="Programmer", unterreiter="Attribute",
          titel="Snap „PAR Rot“ in der Bibliothek",
          vorher=_snap_anlegen,
          marken=[(_snap_eintrag, 1, "Snap"),
                  (_knopf_in(_bib, "Anwenden"), 2, "Anwenden"),
                  (_szene_eintrag("Alle PAR Rot"), 3, "Szene")]),
    Szene("04_assistent", sektion="Programmer", unterreiter="Attribute",
          titel="Reiter Assistent: Programmer → Szene",
          vorher=_assistent,
          marken=[("Programmer → Szene", 1, "Programmer → Szene"),
                  (_effektliste, 2, "Funktionen"),
                  ("Start", 3, "Start"),
                  ("Stop", 4, "Stop")]),
    Szene("05_snapshots", sektion="Programmer", unterreiter="Snapshots",
          titel="Snapshots: 48 Schnellzugriff-Slots",
          vorher=_snapshots, nachher=_snapshots_weg,
          marken=[(_slot(1), 1, "gefüllter Slot"),
                  (_slot(2), 2, "leerer Slot")]),
    Szene("06_preset_browser", sektion="Programmer", unterreiter="Preset-Browser",
          titel="Preset-Browser: Suche nach „PAR“",
          vorher=_preset_browser, nachher=_preset_zurueck,
          marken=[(_preset_suche, 1, "Suche"),
                  (_preset_treffer, 2, "Treffer"),
                  (_preset_status, 3, "Status")]),
    Szene("07_cueliste_neu", sektion="Playback", unterreiter="Playback",
          titel="Neue, leere Cueliste",
          vorher=_neue_cueliste,
          marken=[("+ Neu", 1, "+ Neu"),
                  ("+ Cue aufnehmen", 2, "+ Cue aufnehmen"),
                  ("⚡ Quick-Rec", 3, "Quick-Rec")]),
    Szene("08_executor", sektion="Playback", unterreiter="Playback",
          titel="Drei Cues, Cueliste auf Executor 1",
          vorher=_cues_und_executor,
          marken=[(_cuetabelle, 1, "Cues"),
                  (_executor(1), 2, "Executor 1")]),
    Szene("09_go", sektion="Playback", unterreiter="Playback",
          titel="Nach dem ersten GO",
          vorher=_go,
          marken=[("GO", 1, "GO"),
                  ("◀ BACK", 2, "BACK"),
                  ("■ STOP", 3, "STOP"),
                  (_aktive_cue, 4, "Aktive Cue")]),
    Szene("10_vc_cueliste", sektion="Virtual Console",
          titel="Cueliste in der Virtual Console",
          vorher=_vc_cueliste, nachher=_alles_abraeumen, warte_s=0.8,
          marken=[(_vc_widget, 1, "Cueliste"),
                  (_vc_go, 2, "GO")]),
    Szene("11_go_ohne_executor", sektion="Playback", unterreiter="Playback",
          titel="GO ohne Executor: Liste liegt jetzt auf einem freien Executor",
          vorher=_go_ohne_executor, nachher=_alles_abraeumen,
          marken=[("GO", 1, "GO"),
                  (_hinweis, 2, "Hinweis"),
                  (_executor(1), 3, "Executor 1")]),
    Szene("12_go_fader_null", sektion="Playback", unterreiter="Playback",
          titel="GO ohne Executor: freier Executor hat den Fader auf 0",
          vorher=_fader_null, nachher=_fader_zurueck,
          marken=[(_hinweis, 1, "Hinweis"),
                  (_executor(1), 2, "Executor 1")]),
]
