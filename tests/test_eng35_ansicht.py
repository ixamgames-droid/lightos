"""ENG-35 Schritt 1: Ansicht „Prioritäten“.

Gruppierung nach Stufen (staerkste oben), feste ausgegraute Snap-Zeile,
„eigene Zahl“ fuer alte Zahlen, Aendern schreibt die Stufe (auch fuer mehrere
Zeilen, ein Rueckgaengig-Schritt), Laufzustand, Modify-Kennzeichen.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.core.engine import stufen
from src.core.engine.function_manager import get_function_manager
from src.core.undo import get_undo_stack
from src.ui.views.prioritaeten_view import (PrioritaetenView, _ROLLE_FID,
                                            _ROLLE_ZAHL)

AKZENTE = stufen.stufe_fuer_schluessel("akzente").zahl
STROBE = stufen.stufe_fuer_schluessel("strobe_blinder").zahl
NOTFALL = stufen.stufe_fuer_schluessel("notfall").zahl
GRUNDLICHT = stufen.stufe_fuer_schluessel("grundlicht").zahl


def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def fm():
    _app()
    manager = get_function_manager()
    manager.stop_all()
    vorher = {f.id for f in manager.all()}
    get_undo_stack().clear()
    yield manager
    manager.stop_all()
    for f in list(manager.all()):
        if f.id not in vorher:
            manager.remove(f.id)
    get_undo_stack().clear()


@pytest.fixture
def ansicht(fm):
    v = PrioritaetenView()
    v.resize(900, 600)
    v.show()
    _app().processEvents()
    yield v
    v.close()
    v.deleteLater()
    _app().processEvents()


def _neu(v):
    v.neu_aufbauen()
    return v


def _koepfe(v):
    wurzel = v._baum.invisibleRootItem()
    return [wurzel.child(i) for i in range(wurzel.childCount())]


def _gruppe(v, zahl):
    for kopf in _koepfe(v):
        if kopf.data(0, _ROLLE_ZAHL) == zahl:
            return kopf
    raise AssertionError(f"Gruppe {zahl} fehlt")


def _namen(kopf):
    return [kopf.child(i).text(0) for i in range(kopf.childCount())]




# ── Aufbau ───────────────────────────────────────────────────────────────────

def test_snap_zeile_steht_fest_und_ausgegraut_ganz_oben(ansicht):
    _neu(ansicht)
    oben = _koepfe(ansicht)[0]
    assert oben.text(0) == "Snaps / Programmer — liegt immer darüber"
    assert oben.flags() == Qt.ItemFlag.NoItemFlags, "nicht waehlbar, nicht ziehbar"
    assert oben.data(0, _ROLLE_ZAHL) is None and oben.data(0, _ROLLE_FID) is None
    assert oben.childCount() == 0


def test_fuenf_stufen_staerkste_oben_auch_wenn_leer(ansicht):
    _neu(ansicht)
    zahlen = [k.data(0, _ROLLE_ZAHL) for k in _koepfe(ansicht)[1:]]
    stufen_zahlen = [z for z in zahlen if stufen.stufe_fuer_zahl(z) is not None]
    assert stufen_zahlen == [60, 40, 20, 0, -20]
    assert zahlen == sorted(zahlen, reverse=True)
    for z in (60, 40, 20, -20):
        assert _gruppe(ansicht, z).text(0).startswith(stufen.stufen_name(z))


def test_alte_show_steht_komplett_in_effekte(fm, ansicht):
    a, b = fm.new_scene("ENG35 Rot"), fm.new_chaser("ENG35 Lauf")
    _neu(ansicht)
    namen = _namen(_gruppe(ansicht, 0))
    assert "ENG35 Rot" in namen and "ENG35 Lauf" in namen
    for z in (60, 40, 20, -20):
        assert not [n for n in _namen(_gruppe(ansicht, z)) if n.startswith("ENG35")]
    assert (a.priority, b.priority) == (0, 0), "Anzeigen aendert nichts"


def test_gruppierung_nach_stufe_und_eigene_zahl_dazwischen(fm, ansicht):
    fm.new_scene("ENG35 Grund").priority = GRUNDLICHT
    fm.new_scene("ENG35 Blinder").priority = STROBE
    fm.new_scene("ENG35 Alt").priority = 10
    _neu(ansicht)
    assert "ENG35 Grund" in _namen(_gruppe(ansicht, GRUNDLICHT))
    assert "ENG35 Blinder" in _namen(_gruppe(ansicht, STROBE))
    eigene = _gruppe(ansicht, 10)
    assert eigene.text(0).startswith("eigene Zahl (10)")
    assert "ENG35 Alt" in _namen(eigene)
    zahlen = [k.data(0, _ROLLE_ZAHL) for k in _koepfe(ansicht)[1:]]
    assert zahlen.index(20) < zahlen.index(10) < zahlen.index(0), (
        "die eigene Zahl 10 steht zwischen Akzente und Effekte")


def test_spalten_art_und_bausteine(fm, ansicht):
    from src.core.engine.efx import EfxFixture
    from src.core.engine.rgb_matrix import MatrixStyle
    m = fm.new_rgb_matrix("ENG35 Dimmerlauf")
    m.style = MatrixStyle.DIMMER
    e = fm.new_efx("ENG35 Kreis")
    e.committed = True
    e.fixtures = [EfxFixture(fid=1)]
    s = fm.new_scene("ENG35 Szene")
    s.set_value(424242, 1, 255)          # Geraet, das nicht gepatcht ist
    _neu(ansicht)
    zeilen = {it.text(0): it for it in ansicht._effekt_zeilen()}
    assert zeilen["ENG35 Dimmerlauf"].text(1) == "Matrix"
    assert zeilen["ENG35 Dimmerlauf"].text(2) == "Dimmer"
    assert zeilen["ENG35 Kreis"].text(1) == "Bewegung (EFX)"
    assert zeilen["ENG35 Kreis"].text(2) == "Bewegung"
    assert zeilen["ENG35 Szene"].text(1) == "Szene"
    assert zeilen["ENG35 Szene"].text(2) == "unbekannt", "nicht geraten"


def test_entwuerfe_und_audio_stehen_nicht_in_der_liste(fm, ansicht):
    e = fm.new_efx("ENG35 Entwurf")
    e.committed = False
    fm.new_audio("ENG35 Ton")
    _neu(ansicht)
    namen = [it.text(0) for it in ansicht._effekt_zeilen()]
    assert "ENG35 Entwurf" not in namen and "ENG35 Ton" not in namen


def test_laufender_effekt_ist_markiert(fm, ansicht):
    s = fm.new_scene("ENG35 Laeuft")
    t = fm.new_scene("ENG35 Steht")
    fm.start(s.id)
    _neu(ansicht)
    zeilen = {it.text(0): it for it in ansicht._effekt_zeilen()}
    assert zeilen["ENG35 Laeuft"].text(3) == "● läuft"
    assert zeilen["ENG35 Steht"].text(3) == ""
    fm.stop(s.id, allow_release=False)
    fm.start(t.id)
    ansicht._laufzustand_nachziehen()
    assert zeilen["ENG35 Laeuft"].text(3) == ""
    assert zeilen["ENG35 Steht"].text(3) == "● läuft"


def test_von_einer_sammlung_gestartetes_kind_ist_markiert(fm, ansicht):
    """Codex-Review #1081 (CDX-59): eine Sammlung startet ihre Kinder selbst
    (``child.start()``), am FunctionManager vorbei — in ``running_ids()``
    fehlen sie. Die Ansicht fragt deshalb auch ``is_running``."""
    s = fm.new_scene("ENG35 Kind laeuft")
    s.start()                                    # wie collection.write es tut
    try:
        assert s.id not in fm.running_ids(), "Vorbedingung"
        _neu(ansicht)
        zeilen = {it.text(0): it for it in ansicht._effekt_zeilen()}
        assert zeilen["ENG35 Kind laeuft"].text(3) == "● läuft"
        s.stop()
        ansicht._laufzustand_nachziehen()
        assert zeilen["ENG35 Kind laeuft"].text(3) == ""
        s.start()
        ansicht._laufzustand_nachziehen()
        assert zeilen["ENG35 Kind laeuft"].text(3) == "● läuft"
    finally:
        s.stop()


def test_mitglied_einer_sammlung_traegt_den_hinweis(fm, ansicht):
    s = fm.new_scene("ENG35 Kind")
    c = fm.new_collection("ENG35 Paket")
    c.function_ids = [s.id]
    _neu(ansicht)
    zeilen = {it.text(0): it for it in ansicht._effekt_zeilen()}
    assert "ENG35 Paket" in zeilen["ENG35 Kind"].toolTip(0)
    assert "deren Stufe" in zeilen["ENG35 Kind"].toolTip(0)


def test_modify_effekt_ist_eigens_gekennzeichnet(fm, ansicht, monkeypatch):
    m = fm.new_rgb_matrix("ENG35 Modify")
    m.modify = True                      # Feld aus ENG-37 (hier ggf. nur gesetzt)
    monkeypatch.setattr(type(m), "modify_wirksam", lambda self: True,
                        raising=False)
    n = fm.new_rgb_matrix("ENG35 Normal")
    _neu(ansicht)
    zeilen = {it.text(0): it for it in ansicht._effekt_zeilen()}
    assert "Modify — rechnet auf das fertige Bild" in zeilen["ENG35 Modify"].text(1)
    assert "Modify" not in zeilen["ENG35 Normal"].text(1)
    assert "untereinander" not in zeilen["ENG35 Normal"].toolTip(0)
    assert "nur unter" in zeilen["ENG35 Modify"].toolTip(0)
    assert n.priority == 0


# ── Aendern ──────────────────────────────────────────────────────────────────

def test_auswahl_in_stufe_schreibt_und_gruppiert_um(fm, ansicht):
    s = fm.new_scene("ENG35 Blinder")
    _neu(ansicht)
    ansicht.waehle([s.id])
    assert ansicht.auswahl_in_stufe(STROBE) == 1
    assert s.priority == STROBE
    _app().processEvents()               # Neuaufbau laeuft verzoegert
    assert "ENG35 Blinder" in _namen(_gruppe(ansicht, STROBE))
    assert "ENG35 Blinder" not in _namen(_gruppe(ansicht, 0))
    assert ansicht.ausgewaehlte_ids() == [s.id], "Auswahl bleibt erhalten"


def test_mehrfachauswahl_ist_ein_rueckgaengig_schritt(fm, ansicht):
    a, b, c = (fm.new_scene("ENG35 A"), fm.new_scene("ENG35 B"),
               fm.new_scene("ENG35 C"))
    _neu(ansicht)
    ansicht.waehle([a.id, b.id, c.id])
    assert sorted(ansicht.ausgewaehlte_ids()) == sorted([a.id, b.id, c.id])
    assert ansicht.auswahl_in_stufe(AKZENTE) == 3
    stapel = get_undo_stack()
    assert "3 Effekte" in stapel.undo_label()
    assert stapel.undo()
    assert (a.priority, b.priority, c.priority) == (0, 0, 0)
    assert not stapel.can_undo()
    _app().processEvents()
    namen = _namen(_gruppe(ansicht, 0))
    assert {"ENG35 A", "ENG35 B", "ENG35 C"} <= set(namen)


def test_knoepfe_stufe_hoeher_und_tiefer(fm, ansicht):
    a = fm.new_scene("ENG35 A")
    b = fm.new_scene("ENG35 B")
    b.priority = 10                       # eigene Zahl
    c = fm.new_scene("ENG35 C")
    c.priority = NOTFALL                  # schon ganz oben
    _neu(ansicht)
    ansicht.waehle([a.id, b.id, c.id])
    ansicht._btn_hoeher.click()
    assert (a.priority, b.priority, c.priority) == (AKZENTE, AKZENTE, NOTFALL)
    assert get_undo_stack().undo()
    assert (a.priority, b.priority, c.priority) == (0, 10, NOTFALL)
    _app().processEvents()
    ansicht.waehle([a.id, b.id, c.id])
    ansicht._btn_tiefer.click()
    assert (a.priority, b.priority, c.priority) == (GRUNDLICHT, 0, STROBE)


def test_knoepfe_ohne_auswahl_gesperrt(fm, ansicht):
    s = fm.new_scene("ENG35 A")
    s.priority = NOTFALL
    _neu(ansicht)
    ansicht._baum.clearSelection()
    ansicht._auswahl_geaendert()
    assert not ansicht._btn_hoeher.isEnabled()
    assert not ansicht._btn_tiefer.isEnabled()
    assert not ansicht._ziel_combo.isEnabled()
    ansicht.waehle([s.id])
    assert not ansicht._btn_hoeher.isEnabled(), "Notfall ist die staerkste Stufe"
    assert ansicht._btn_tiefer.isEnabled()
    assert ansicht._ziel_combo.zahl() == NOTFALL


def test_auswahlfeld_der_leiste_setzt_die_stufe(fm, ansicht):
    s = fm.new_scene("ENG35 A")
    _neu(ansicht)
    ansicht.waehle([s.id])
    feld = ansicht._ziel_combo
    idx = feld.findData(GRUNDLICHT)
    feld.setCurrentIndex(idx)
    feld.activated.emit(idx)
    assert s.priority == GRUNDLICHT


def test_ziehen_in_eine_stufe(fm, ansicht):
    """Der Abwurf auf eine Stufen-Zeile ODER auf einen Effekt darin legt die
    Auswahl in diese Stufe; Qt haengt dabei selbst nichts um."""
    from PySide6.QtCore import QMimeData, QPoint, QPointF
    from PySide6.QtGui import QDropEvent
    a, b = fm.new_scene("ENG35 A"), fm.new_scene("ENG35 B")
    z = fm.new_scene("ENG35 Ziel")
    z.priority = STROBE
    _neu(ansicht)
    _app().processEvents()
    ansicht.waehle([a.id, b.id])
    baum = ansicht._baum

    class _Abwurf(QDropEvent):
        def source(self_inner):
            return baum

    def abwerfen(item):
        mitte = baum.visualItemRect(item).center()
        assert baum.itemAt(mitte) is item, "Zeile nicht sichtbar"
        ev = _Abwurf(QPointF(mitte), Qt.DropAction.MoveAction, QMimeData(),
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        baum.dropEvent(ev)
        return ev

    zahl_vorher = sum(1 for _ in ansicht._effekt_zeilen())
    ev = abwerfen(_gruppe(ansicht, AKZENTE))
    assert (a.priority, b.priority) == (AKZENTE, AKZENTE)
    assert not ev.isAccepted(), "Qt darf die Zeilen nicht selbst verschieben"
    assert sum(1 for _ in ansicht._effekt_zeilen()) == zahl_vorher
    _app().processEvents()
    ansicht.waehle([a.id])
    ziel_zeile = [it for it in ansicht._effekt_zeilen()
                  if it.data(0, _ROLLE_FID) == z.id][0]
    abwerfen(ziel_zeile)
    assert a.priority == STROBE and b.priority == AKZENTE
    # Abwurf auf die feste Snap-Zeile tut nichts.
    _app().processEvents()
    ansicht.waehle([a.id])
    abwerfen(_koepfe(ansicht)[0])
    assert a.priority == STROBE


def test_neuaufbau_nie_im_eigenen_signal(fm, ansicht):
    """Eine Aenderung meldet nur „veraltet“ an; gebaut wird erst im naechsten
    Durchlauf der Ereignisschleife."""
    s = fm.new_scene("ENG35 A")
    _neu(ansicht)
    ansicht.waehle([s.id])
    zeile = [it for it in ansicht._effekt_zeilen()][0]
    eltern_vorher = zeile.parent()
    ansicht.auswahl_in_stufe(NOTFALL)
    assert ansicht._veraltet is True
    assert zeile.parent() is eltern_vorher, "noch nicht umgebaut"
    _app().processEvents()
    assert ansicht._veraltet is False
    assert "ENG35 A" in _namen(_gruppe(ansicht, NOTFALL))


def test_unsichtbar_wird_nicht_gebaut_und_holt_beim_zeigen_nach(fm):
    v = PrioritaetenView()
    try:
        s = fm.new_scene("ENG35 Spaeter")
        v._melde_veraltet()
        _app().processEvents()
        assert v._veraltet is True
        assert not [it for it in v._effekt_zeilen()]
        v.show()
        _app().processEvents()
        assert v._veraltet is False
        assert "ENG35 Spaeter" in [it.text(0) for it in v._effekt_zeilen()]
        assert s.priority == 0
    finally:
        v.close()
        v.deleteLater()


def test_zugeklappte_stufe_bleibt_zugeklappt(fm, ansicht):
    fm.new_scene("ENG35 A")
    _neu(ansicht)
    _gruppe(ansicht, 0).setExpanded(False)
    _neu(ansicht)
    assert not _gruppe(ansicht, 0).isExpanded()
    assert _gruppe(ansicht, AKZENTE).isExpanded()


def test_reiter_prioritaeten_im_programmer_bereich():
    """Die Ansicht haengt als Reiter „Prioritäten“ im Programmer-Bereich —
    neben Snapshots und Preset-Browser."""
    from pathlib import Path
    quelle = (Path(__file__).resolve().parent.parent
              / "src/ui/main_window.py").read_text(encoding="utf-8")
    a = quelle.index("def _build_section_programmer")
    b = quelle.index("def _build_section_playback")
    abschnitt = quelle[a:b]
    assert 'tabs.addTab(self._prioritaeten_view, "Prioritäten")' in abschnitt
    assert abschnitt.index('"Preset-Browser"') < abschnitt.index('"Prioritäten"')


# ── Nachtrag Sichtprobe: „&“ im Stufennamen, Spaltenbreite, Wiederholen ──────

def _wie_qt_es_zeigt(text: str) -> str:
    """Was ein Menue aus dem Text macht: ``&&`` wird ``&``, ein einzelnes
    ``&`` verschwindet (es markiert nur das Tastenkuerzel)."""
    return text.replace("&&", "\0").replace("&", "").replace("\0", "&")


def test_menue_text_verdoppelt_das_kaufmannsund():
    from src.ui.menue_text import menue_text
    assert menue_text("Strobe & Blinder") == "Strobe && Blinder"
    assert menue_text("Akzente") == "Akzente"
    assert menue_text(None) == ""
    for s in stufen.STUFEN:
        assert _wie_qt_es_zeigt(menue_text(s.name)) == s.name


def test_rechtsklick_menue_zeigt_strobe_und_blinder_vollstaendig(fm, ansicht):
    """Sichtprobe: im Menue stand „Strobe _Blinder“ — das „&“ des Stufennamens
    wurde als Tastenkuerzel-Zeichen gelesen."""
    menue = ansicht._stufen_menue()
    gezeigt = {akt.data(): _wie_qt_es_zeigt(akt.text())
               for akt in menue.actions()}
    assert gezeigt[STROBE] == "In Stufe „Strobe & Blinder“"
    assert [akt.data() for akt in menue.actions()] == [
        s.zahl for s in reversed(stufen.STUFEN)]
    for s in stufen.STUFEN:
        assert gezeigt[s.zahl] == f"In Stufe „{s.name}“"
    menue.deleteLater()


def test_rueckgaengig_menue_zeigt_das_kaufmannsund():
    """Der Titel des Rueckgaengig-Schritts („… → Strobe & Blinder“) landet als
    Menuetext unter „Bearbeiten“ — auch dort darf das „&“ nicht verschwinden."""
    from types import SimpleNamespace
    from PySide6.QtGui import QAction
    from src.core.undo import UndoStack
    from src.ui.main_window import MainWindow
    _app()
    stapel = UndoStack()
    attrappe = SimpleNamespace(_undo_stack=stapel, _act_undo=QAction(),
                               _act_redo=QAction(), _vc_verlauf=lambda: None)
    # UI-93: die Menuetexte kommen aus dem gemeinsamen Verlauf.
    attrappe._naechster_verlauf = (
        lambda wiederholen: MainWindow._naechster_verlauf(attrappe, wiederholen))
    stapel.push_simple("Stufe: Blitz → Strobe & Blinder",
                       lambda: None, lambda: None)
    MainWindow._refresh_undo_labels(attrappe)
    assert _wie_qt_es_zeigt(attrappe._act_undo.text()) == \
        "Rückgängig: Stufe: Blitz → Strobe & Blinder"
    stapel.undo()
    MainWindow._refresh_undo_labels(attrappe)
    assert _wie_qt_es_zeigt(attrappe._act_redo.text()) == \
        "Wiederholen: Stufe: Blitz → Strobe & Blinder"
    assert attrappe._act_undo.text() == "Rückgängig"


def test_nur_die_spalte_effekt_dehnt_sich(fm, ansicht):
    """Sichtprobe: „Zustand“ war so breit wie „Effekt“. Der Platz gehoert dem
    Namen; alle anderen Spalten sind so breit wie ihr Inhalt."""
    from PySide6.QtWidgets import QHeaderView
    s = fm.new_scene("ENG35 Breite")
    s.start()
    _neu(ansicht)
    ansicht.resize(1600, 600)
    _app().processEvents()
    kopf = ansicht._baum.header()
    assert not kopf.stretchLastSection()
    assert kopf.sectionResizeMode(0) == QHeaderView.ResizeMode.Stretch
    for spalte in (1, 2, 3):
        assert (kopf.sectionResizeMode(spalte)
                == QHeaderView.ResizeMode.ResizeToContents)
    breiten = [kopf.sectionSize(i) for i in range(4)]
    assert breiten[0] > 3 * breiten[3], breiten
    assert breiten[3] < 200, breiten


def test_ziehen_rueckgaengig_wiederholen(fm, ansicht):
    """Ziehen, Rueckgaengig, Wiederholen: der Schritt liegt danach auf dem
    Wiederholen-Stapel und stellt die Stufe wieder her — auch nachdem die
    Ansicht sich zwischendurch neu aufgebaut hat."""
    a, b = fm.new_scene("ENG35 Redo A"), fm.new_scene("ENG35 Redo B")
    _neu(ansicht)
    _app().processEvents()
    ansicht.waehle([a.id, b.id])
    assert ansicht.auswahl_in_stufe(AKZENTE) == 2     # derselbe Weg wie der Abwurf
    _app().processEvents()
    stapel = get_undo_stack()
    assert stapel.undo()
    _app().processEvents()
    assert (a.priority, b.priority) == (0, 0)
    assert _namen(_gruppe(ansicht, AKZENTE)) == []
    assert stapel.can_redo(), "der Neuaufbau darf den Wiederholen-Stapel nicht leeren"
    assert stapel.redo()
    _app().processEvents()
    assert (a.priority, b.priority) == (AKZENTE, AKZENTE)
    assert _namen(_gruppe(ansicht, AKZENTE)) == ["ENG35 Redo A", "ENG35 Redo B"]
    assert stapel.can_undo() and not stapel.can_redo()
