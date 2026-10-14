"""IMP-2: Gegenprüfung des nicht modalen Mitschnitt-Assistenten.

Der Assistent sperrt die App nicht mehr. Hier steht, was daneben passieren
kann, während er offen ist: „Neue Show“ und „Show öffnen“ über den echten
Lade-Weg, ein abgeschalteter Eingang, eine geänderte Adresse — und die
Bedienung per Tastatur, weil die Leertaste im Assistenten festhält und damit
für Knöpfe und Haken nicht mehr frei ist.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, Qt                         # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget                  # noqa: E402

import src.core.app_state as A                                       # noqa: E402
from src.core import mitschnitt as M                                 # noqa: E402
from src.core.engine.function import FunctionType                    # noqa: E402
from src.ui.widgets import mitschnitt_dialog as D                    # noqa: E402
from test_imp2_mitschnitt_dialog import (                            # noqa: E402,F401
    _FLAECHEN, _Rx, _Uhr, _aktiviere, _bild, _keine_fenster_uebrig,
    _laengste_meldung, _pruefe_fenster, _sichtbare_zeilen, _spiele_ruhig,
    _stelle_bildschirm, _verarbeite, _zeige, aufbau, rig, state,
)

_app = QApplication.instance() or QApplication([])


def _gezeigt(dlg):
    return [dlg._liste.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(dlg._liste.count())]


def _halte_fest(dlg, art, uhr, adressen, werte):
    ids = []
    for wert in werte:
        _spiele_ruhig(art, uhr, _bild(adressen, wert))
        ids.append(dlg.festhalten().id)
    return ids


# ── Show-Wechsel über den echten Lade-Weg ────────────────────────────────────

def test_neue_show_und_show_oeffnen_ueber_den_echten_weg(
        state, rig, aufbau, tmp_path, monkeypatch):
    """„Neue Show“ (``reset_show``) und „Show öffnen“ (``load_show``) laufen
    NICHT über ``open_show``. Auch dort beginnt die Liste neu — und die
    geladene Show bringt Szenen mit DENSELBEN Nummern mit, die der Assistent
    nie für seine eigenen halten darf."""
    from src.core.show import show_file
    monkeypatch.setattr(A, "_state", state, raising=False)
    dlg, art, sacn, uhr = aufbau
    fm = state.function_manager
    ids = _halte_fest(dlg, art, uhr, rig["adressen"], (10, 20, 30))
    datei = tmp_path / "gespeichert.lshow"
    show_file.save_show(str(datei))

    show_file.reset_show()                                   # „Neue Show“
    assert dlg._lage.show_gewechselt
    dlg.aktualisiere()
    assert dlg._lbl_meldung.text() == D.MELDUNG_SHOW_GEWECHSELT
    assert _gezeigt(dlg) == [] and dlg.szenen_ids == []
    assert fm.all() == [] and state.get_patched_fixtures() == []
    assert dlg._edit_name.text() == "Mitschnitt 1"
    # Der leere Patch wird gesagt, es entsteht nichts.
    _spiele_ruhig(art, uhr, _bild(rig["adressen"], 70))
    assert dlg.festhalten() is None
    assert dlg._lbl_meldung.text() == D.GRUND_KEIN_PATCH

    ok, meldung = show_file.load_show(str(datei))            # „Show öffnen“
    assert ok, meldung
    assert dlg._lage.show_gewechselt
    geladen = {f.id for f in fm.by_type(FunctionType.Scene)}
    assert set(ids) <= geladen                               # dieselben Nummern
    dlg._check_chaser.setChecked(True)
    dlg.fertig()                         # bleibt offen und sagt, warum
    assert not dlg._abgebaut and dlg.chaser is None
    assert _gezeigt(dlg) == [] and dlg.szenen_ids == []
    dlg.entferne_markierte()
    assert {f.id for f in fm.by_type(FunctionType.Scene)} == geladen
    assert fm.by_type(FunctionType.Chaser) == []
    # Weiter in der geladenen Show: der Name weicht den vorhandenen aus, und
    # in die neue Szene kommen nur Geräte, die es jetzt gibt.
    assert dlg._edit_name.text() == "Mitschnitt 4"
    _spiele_ruhig(art, uhr, _bild(rig["adressen"], 90))
    neu = dlg.festhalten()
    assert neu is not None and neu.name == "Mitschnitt 4"
    vorhanden = {int(f.fid) for f in state.get_patched_fixtures()}
    assert {v.fixture_id for v in neu.values} <= vorhanden
    dlg.fertig()
    assert dlg._abgebaut
    assert [s.function_id for s in dlg.chaser.steps] == [neu.id]


# ── Eingang wird abgeschaltet, während der Assistent offen ist ───────────────

def test_abgeschalteter_eingang_liefert_sofort_kein_bild_mehr(state, rig, aufbau):
    """Der Puffer hält das letzte Bild fünf Sekunden. Schaltet man den Eingang
    in dieser Zeit ab, darf der Assistent nicht „Eingang ist aus“ melden und
    trotzdem aus dem alten Bild eine Szene machen."""
    dlg, art, sacn, uhr = aufbau
    _spiele_ruhig(art, uhr, _bild(rig["adressen"], 40))
    dlg.aktualisiere()
    assert "bekommen gerade Werte" in dlg._lbl_live.text()
    art.laeuft = False                                       # Haken weg, Übernehmen
    dlg.aktualisiere()
    assert dlg._lbl_status[M.ARTNET].text() == "Art-Net: Eingang ist aus."
    assert dlg._lbl_live.text() == "Kein Signal."
    assert dlg.festhalten() is None
    assert dlg._lbl_meldung.text().startswith(D.GRUND_KEIN_SIGNAL)
    assert state.function_manager.all() == []
    # Wieder eingeschaltet: erst ein NEUES Bild zählt, nicht das von vorhin.
    art.laeuft = True
    dlg.aktualisiere()
    assert dlg._lbl_live.text() == "Kein Signal."
    assert dlg.festhalten() is None
    _spiele_ruhig(art, uhr, _bild(rig["adressen"], 80))
    assert dlg.festhalten() is not None


def test_geaenderte_zuordnung_und_adresse_gelten_sofort(state, rig, aufbau):
    dlg, art, sacn, uhr = aufbau
    daten = bytearray(512)
    daten[0] = 200                                           # Adresse 1
    daten[299] = 77                                          # Adresse 300
    _spiele_ruhig(art, uhr, bytes(daten))
    erste = dlg.festhalten()
    assert {(v.fixture_id, v.channel): v.value for v in erste.values}[(1, 1)] == 200
    # Gerät 1 zieht auf Adresse 300: die nächste Szene liest dort.
    assert state.update_fixture(1, undoable=False, address=300)
    assert dlg._lage.patch_geaendert
    _spiele_ruhig(art, uhr, bytes(daten))
    zweite = dlg.festhalten()
    assert {(v.fixture_id, v.channel): v.value for v in zweite.values}[(1, 1)] == 77
    # Der Eingang zeigt jetzt auf ein anderes LightOS-Universum: für die
    # Geräte in Universum 2 gibt es kein Bild mehr — es entsteht keine Szene.
    art.zuordnung = {1: 3}
    _spiele_ruhig(art, uhr, bytes(daten))
    assert dlg.festhalten() is None
    assert dlg._lbl_meldung.text() == D.GRUND_KEINE_WERTE
    assert len(state.function_manager.all()) == 2


def test_umbenennen_im_hauptfenster_zeigt_die_liste(state, rig, aufbau):
    """Die Funktionsliste bleibt bedienbar: wird eine festgehaltene Szene dort
    umbenannt, zeigt die Liste des Assistenten den neuen Namen — sonst
    entfernt man unter dem alten Namen eine Szene, die anders heißt."""
    dlg, art, sacn, uhr = aufbau
    fm = state.function_manager
    ids = _halte_fest(dlg, art, uhr, rig["adressen"], (10, 20))
    assert dlg._liste.item(1).text().startswith("Mitschnitt 2 — ")
    fm.get(ids[1]).name = "Rot voll"
    dlg.aktualisiere()
    assert dlg._liste.item(1).text().startswith("Rot voll — ")
    assert dlg._liste.item(1).text().endswith("Kanäle")
    assert dlg._liste.item(0).text().startswith("Mitschnitt 1 — ")
    assert dlg._liste.currentRow() == 1                  # Markierung bleibt
    dlg.entferne_markierte()
    assert dlg._lbl_meldung.text() == "„Rot voll“ entfernt."
    assert fm.get(ids[1]) is None and fm.get(ids[0]) is not None


def test_nach_dem_abriss_des_hauptfensters_oeffnet_ein_neuer_assistent(
        state, rig, monkeypatch):
    import shiboken6
    echt = M.EingangsLeser
    monkeypatch.setattr(M, "EingangsLeser", lambda *a, **k: echt(
        M.Eingangspuffer(), {M.ARTNET: _Rx({1: 2}), M.SACN: _Rx({}, laeuft=False)}))
    try:
        haupt = QWidget()
        haupt.show()
        erster = D.zeige_assistent(haupt, state=state)
        _verarbeite()
        assert D.offener_assistent() is erster
        shiboken6.delete(haupt)                  # ohne closeEvent, ohne finished
        assert D.offener_assistent() is None
        haupt2 = QWidget()
        haupt2.show()
        zweiter = D.zeige_assistent(haupt2, state=state)
        _verarbeite()
        assert zweiter is not erster and zweiter.isVisible()
        assert D.zeige_assistent(haupt2, state=state) is zweiter
        zweiter.close()
        _verarbeite()
        assert D.offener_assistent() is None
    finally:
        D._vergiss()


# ── Tastatur ─────────────────────────────────────────────────────────────────

def _offen_und_aktiv(dlg):
    dlg.show()
    _verarbeite()
    _aktiviere(dlg)


def test_leertaste_haelt_auch_auf_knopf_und_haken_genau_einmal_fest(
        state, rig, aufbau):
    """Steht der Fokus auf einem anderen Knopf oder Haken, hält die Leertaste
    trotzdem fest — einmal, und ohne den Knopf darunter mit auszulösen."""
    dlg, art, sacn, uhr = aufbau
    _offen_und_aktiv(dlg)
    fm = state.function_manager
    _halte_fest(dlg, art, uhr, rig["adressen"], (10,))
    for i, w in enumerate((dlg._btn_entfernen, dlg._check_laser,
                           dlg._check_chaser, dlg._btn_fertig,
                           dlg._btn_festhalten, dlg._liste), start=2):
        _spiele_ruhig(art, uhr, _bild(rig["adressen"], 10 * i))
        dlg.aktualisiere()
        w.setFocus()
        _verarbeite()
        assert dlg.focusWidget() is w
        QTest.keyClick(w, Qt.Key.Key_Space)
        _verarbeite()
        assert len(fm.all()) == i, type(w).__name__
        assert not dlg._abgebaut
    assert not dlg._check_laser.isChecked() and not dlg._check_chaser.isChecked()
    assert dlg._liste.count() == 7
    # In den Zahlenfeldern tippt man; dort legt die Leertaste nichts an.
    for feld in (dlg._spin_ruhe, dlg._spin_schritt, dlg._edit_name):
        _spiele_ruhig(art, uhr, _bild(rig["adressen"], 99))
        feld.setFocus()
        _verarbeite()
        QTest.keyClick(feld, Qt.Key.Key_Space)
        _verarbeite()
        assert len(fm.all()) == 7, type(feld).__name__


def test_eingeklappte_hilfe_laesst_sich_per_tastatur_aufklappen(
        state, rig, aufbau, monkeypatch):
    dlg, art, sacn, uhr = aufbau
    _stelle_bildschirm(monkeypatch, _FLAECHEN["1024x600"])
    _offen_und_aktiv(dlg)
    knopf = dlg._btn_hilfe
    assert knopf.isVisible() and not knopf.isChecked() and dlg._lbl_hilfe.isHidden()
    assert knopf.focusPolicy() & Qt.FocusPolicy.TabFocus
    # Mit der Tabulatortaste erreichbar …
    dlg._btn_festhalten.setFocus()
    for _ in range(40):
        if dlg.focusWidget() is knopf:
            break
        QTest.keyClick(dlg.focusWidget(), Qt.Key.Key_Tab)
        _verarbeite()
    assert dlg.focusWidget() is knopf
    # … und mit der Eingabetaste bedienbar (die Leertaste hält hier fest).
    for taste in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
        vorher = knopf.isChecked()
        QTest.keyClick(knopf, taste)
        _verarbeite()
        assert knopf.isChecked() is (not vorher)
        assert dlg._lbl_hilfe.isHidden() is vorher
        assert knopf.text() == (D.TEXT_HILFE_ZEIGEN if vorher else D.TEXT_HILFE_WEG)
    assert not dlg._abgebaut and state.function_manager.all() == []
    # Der Tooltip sagt, was der Knopf tut und wie man ihn ohne Maus bedient.
    tipp = knopf.toolTip()
    assert "Wegbeschreibung" in tipp and "Eingabetaste" in tipp
    assert "Eingabetaste" in D.TIPP_FESTHALTEN


def test_haken_und_knoepfe_gehen_mit_der_eingabetaste(state, rig, aufbau):
    """Die Leertaste ist im Assistenten vergeben. Damit Haken und Knöpfe per
    Tastatur bedienbar bleiben, löst die Eingabetaste das Teil mit dem Fokus
    aus — und nichts sonst: im Namensfeld tut sie nichts."""
    dlg, art, sacn, uhr = aufbau
    _offen_und_aktiv(dlg)
    fm = state.function_manager
    _spiele_ruhig(art, uhr, _bild(rig["adressen"], 10))
    dlg._edit_name.setFocus()
    QTest.keyClick(dlg._edit_name, Qt.Key.Key_Return)
    _verarbeite()
    assert fm.all() == [] and not dlg._abgebaut
    for haken in (dlg._check_chaser, dlg._check_unruhig, dlg._check_laser):
        haken.setFocus()
        QTest.keyClick(haken, Qt.Key.Key_Return)
        _verarbeite()
        assert haken.isChecked()
        QTest.keyClick(haken, Qt.Key.Key_Return)
        _verarbeite()
        assert not haken.isChecked()
    assert fm.all() == []
    dlg._btn_festhalten.setFocus()
    QTest.keyClick(dlg._btn_festhalten, Qt.Key.Key_Return)
    _verarbeite()
    assert [f.name for f in fm.all()] == ["Mitschnitt 1"]
    dlg._btn_entfernen.setFocus()
    QTest.keyClick(dlg._btn_entfernen, Qt.Key.Key_Return)
    _verarbeite()
    assert fm.all() == [] and not dlg._abgebaut
    dlg._btn_fertig.setFocus()
    QTest.keyClick(dlg._btn_fertig, Qt.Key.Key_Return)
    _verarbeite()
    assert dlg._abgebaut


# ── Layout: acht Szenen und die lange rote Meldung ───────────────────────────

@pytest.mark.parametrize("flaeche", sorted(_FLAECHEN))
def test_acht_szenen_und_lange_rote_meldung_bei_jeder_flaeche(
        state, rig, aufbau, monkeypatch, flaeche):
    dlg, art, sacn, uhr = aufbau
    bildschirm = _stelle_bildschirm(monkeypatch, _FLAECHEN[flaeche])
    _spiele_ruhig(art, uhr, _bild(rig["adressen"], 40))
    dlg.aktualisiere()
    _zeige(dlg)
    _halte_fest(dlg, art, uhr, rig["adressen"], range(20, 180, 20))
    _verarbeite()
    assert dlg._liste.count() == 8
    _pruefe_fenster(dlg, bildschirm)
    dlg._melde(_laengste_meldung(dlg), fehler=True)
    _verarbeite()
    _pruefe_fenster(dlg, bildschirm)
    # Das Signal bricht ab: rote Meldung UND eingeblendete Wegbeschreibung —
    # mehr steht nie gleichzeitig im Fenster.
    uhr.vor(M.SIGNAL_TIMEOUT + 1)
    assert dlg.festhalten() is None
    _verarbeite()
    assert dlg._lbl_meldung.text() == D.GRUND_KEIN_SIGNAL + " " + D.VERWEIS_HILFE
    assert "#e0705a" in dlg._lbl_meldung.styleSheet()
    assert not dlg._lbl_hilfe.isHidden() and dlg._liste.count() == 8
    _pruefe_fenster(dlg, bildschirm)
    # Die Liste rollt selbst; die zuletzt festgehaltene Szene ist zu sehen.
    assert _sichtbare_zeilen(dlg) >= D.MINDESTZEILEN
    letzte = dlg._liste.visualItemRect(dlg._liste.item(7))
    assert dlg._liste.viewport().rect().contains(letzte), letzte
    # Die Meldung ist ganz zu lesen und liegt unter dem Knopf, über der Liste.
    meldung = QRect(dlg._lbl_meldung.mapTo(dlg, QPoint(0, 0)), dlg._lbl_meldung.size())
    assert meldung.height() >= dlg._lbl_meldung.heightForWidth(meldung.width())
    print(f"\n[{flaeche}] Fenster {dlg.width()}x{dlg.height()}, Rollbereich "
          f"{dlg._rollbereich.viewport().height()} von {dlg._inhalt.height()} px, "
          f"Liste {_sichtbare_zeilen(dlg)} Zeilen, Meldung {meldung.height()} px")
