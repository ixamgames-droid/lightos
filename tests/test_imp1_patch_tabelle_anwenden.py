"""IMP-1: Patch aus einer Tabelle — Anwenden gegen einen echten AppState und
der Vorschau-Dialog (offscreen).

Echter ``AppState`` mit eigener Show-Datei unter ``tmp_path`` und die
Geräte-Bibliothek, die die Testumgebung bereitstellt (eine Kopie, nie die
echte). Geprüft wird, was am Ende im Patch steht — und dass EIN Rückgängig
alles zurücknimmt, ohne Vorhandenes anzufassen.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox              # noqa: E402

import src.core.app_state as A                                       # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets             # noqa: E402
from src.core import patch_tabelle as T                              # noqa: E402
from src.core.database.models import PatchedFixture                  # noqa: E402
from src.core.undo import get_undo_stack                             # noqa: E402
from src.ui.widgets import patch_import_dialog as D                  # noqa: E402

_app = QApplication.instance() or QApplication([])

PAR = "Stage Light ZQ01424"          # Generic, Modi 8-Kanal RGBW / 4-Kanal …
MH = "ZQ02001 Mini Moving Head"      # U King, Modi 11-Kanal / 9-Kanal


@pytest.fixture(autouse=True)
def _keine_fenster_uebrig():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


@pytest.fixture(scope="module")
def bib():
    return T.bibliothek_aus_db()


@pytest.fixture
def state(tmp_path):
    stack = get_undo_stack()
    stack.clear()
    st = A.AppState()
    st.open_show(str(tmp_path / "show.db"))
    yield st
    stack.clear()
    try:
        st._show_engine.dispose()
    except Exception:
        pass


def _vorhandenes(state, bib):
    """Ein Gerät, das schon im Patch steht: Universum 1, Kanal 100–107."""
    par = bib.finde("Generic", PAR).profil
    state.add_fixture(PatchedFixture(
        fid=1, label="Altbestand", fixture_profile_id=par.id,
        mode_name="8-Kanal RGBW", universe=1, address=100, channel_count=8,
        manufacturer_name="Generic", fixture_name=PAR, fixture_type="par"),
        undoable=False)


def _bild(state):
    return sorted((f.fid, f.label, f.fixture_profile_id, f.mode_name,
                   f.universe, f.address, f.channel_count)
                  for f in state.get_patched_fixtures())


TABELLE = (
    "Name;Hersteller;Profil;Modus;Universum;Adresse;Anzahl\n"
    f"PAR;Generic;{PAR};8-Kanal RGBW;1;1;3\n"             # 3 Geräte: 1, 9, 17
    f"Kopf links;U King;{MH};11-Kanal;2;2.50;1\n"         # Universum 2, Adresse 50
    f"Kopf rechts;;zq02001 mini moving head;9ch;2;70;1\n"  # ohne Groß/Klein, Modus über Kanalzahl
    f"Kollision;Generic;{PAR};8-Kanal RGBW;1;104;1\n"     # trifft „Altbestand“
    "Unbekannt;;Quantum Wash XJ9000;;1;300;1\n"           # offen
    f"Ohne Modus;U King;{MH};;1;400;1\n"                  # offen (zwei Modi)
)


def _plan(state, bib, text=TABELLE, wahl=None):
    return T.baue_plan(T.lies_tabelle(text), bib, T.belegung_aus_state(state), wahl)


# ── Bibliothek ───────────────────────────────────────────────────────────────

def test_bibliothek_kommt_aus_der_testkopie_und_kennt_die_mitgelieferten(bib):
    par = bib.finde("Generic", PAR)
    assert par.art == T.EXAKT and {m.name for m in par.profil.modi} >= {"8-Kanal RGBW"}
    assert par.profil.modus("8-Kanal RGBW").kanaele == 8
    mh = bib.finde("U King", MH).profil
    assert {m.kanaele for m in mh.modi} >= {9, 11}


def test_vorlage_ist_gegen_die_bibliothek_vollstaendig_anlegbar(tmp_path, state, bib):
    pfad = tmp_path / "vorlage.csv"
    T.schreibe_vorlage(str(pfad))
    plan = T.baue_plan(T.lies_datei(str(pfad)), bib, T.belegung_aus_state(state))
    assert [z.status for z in plan.zeilen] == [T.ANLEGBAR, T.ANLEGBAR], \
        [z.status_text for z in plan.zeilen]
    assert all(z.art == T.EXAKT for z in plan.zeilen)
    assert plan.zaehlerzeile() == "5 Geräte werden angelegt"


# ── Anwenden ─────────────────────────────────────────────────────────────────

def test_anwenden_legt_nur_die_anlegbaren_zeilen_an(state, bib):
    _vorhandenes(state, bib)
    vorher = _bild(state)
    plan = _plan(state, bib)
    assert [z.status for z in plan.zeilen] == [
        T.ANLEGBAR, T.ANLEGBAR, T.ANLEGBAR, T.UEBERSCHNEIDUNG, T.OFFEN, T.OFFEN]

    ergebnis = T.wende_an(state, plan, bib)

    assert ergebnis.geraete == 5 and ergebnis.zeilen == 3
    assert ergebnis.ausgelassen == 3 and ergebnis.fehler == []
    neu = {f.label: f for f in state.get_patched_fixtures() if f.fid in ergebnis.fids}
    assert sorted(neu) == ["Kopf links", "Kopf rechts", "PAR 1", "PAR 2", "PAR 3"]
    assert [(neu[n].universe, neu[n].address, neu[n].channel_count)
            for n in ("PAR 1", "PAR 2", "PAR 3")] == [(1, 1, 8), (1, 9, 8), (1, 17, 8)]
    assert (neu["Kopf links"].universe, neu["Kopf links"].address,
            neu["Kopf links"].mode_name, neu["Kopf links"].channel_count) == (2, 50, "11-Kanal", 11)
    assert (neu["Kopf rechts"].mode_name, neu["Kopf rechts"].channel_count,
            neu["Kopf rechts"].address) == ("9-Kanal", 9, 70)
    assert neu["PAR 1"].manufacturer_name == "Generic"
    assert neu["PAR 1"].fixture_name == PAR and neu["PAR 1"].fixture_type == "par"
    assert neu["Kopf links"].fixture_type == "moving_head"
    # Vorhandenes steht noch genau so da
    assert [b for b in _bild(state) if b[0] == 1] == vorher
    assert len(set(f.fid for f in state.get_patched_fixtures())) == 6


def test_importierte_geraete_sind_im_render_plan_wie_von_hand_gepatcht(state, bib):
    """Derselbe Weg wie von Hand: das Gerät löst seine Kanäle auf."""
    T.wende_an(state, _plan(state, bib, f"Name;Profil;Modus;Adresse\nA;{PAR};8-Kanal RGBW;1\n"), bib)
    fx = state.get_patched_fixtures()[0]
    kanaele = A.get_channels_for_patched(fx)
    assert len(kanaele) == 8
    assert "intensity" in {k.attribute for k in kanaele}


def test_ein_rueckgaengig_nimmt_alles_zurueck_und_wiederholen_bringt_es_wieder(state, bib):
    _vorhandenes(state, bib)
    vorher = _bild(state)
    stack = get_undo_stack()
    assert not stack.can_undo()

    T.wende_an(state, _plan(state, bib), bib)
    nachher = _bild(state)
    assert len(nachher) == 6
    assert len(stack._undo) == 1                       # EIN Schritt
    assert stack.undo_label() == "Patch-Import: 5 Geräte"

    assert stack.undo()
    assert _bild(state) == vorher                      # alles weg, Altbestand unverändert
    assert not stack.can_undo()

    assert stack.redo()
    assert [b[1:] for b in _bild(state)] == [b[1:] for b in nachher]
    assert stack.undo()
    assert _bild(state) == vorher


def test_rueckgaengig_laesst_spaeteres_von_hand_stehen(state, bib):
    """Der Import ist EIN Schritt unter anderen: erst das spätere Gerät
    zurücknehmen, dann den Import — nie mehr als das."""
    T.wende_an(state, _plan(state, bib, f"Name;Profil;Modus;Adresse;Anzahl\nA;{PAR};8-Kanal RGBW;1;2\n"), bib)
    par = bib.finde("Generic", PAR).profil
    state.add_fixture(PatchedFixture(
        fid=state.next_fid(), label="Von Hand", fixture_profile_id=par.id,
        mode_name="8-Kanal RGBW", universe=3, address=1, channel_count=8,
        fixture_type="par"))
    stack = get_undo_stack()
    assert len(stack._undo) == 2
    stack.undo()
    assert sorted(f.label for f in state.get_patched_fixtures()) == ["A 1", "A 2"]
    stack.undo()
    assert state.get_patched_fixtures() == []


def test_nichts_anlegbar_legt_nichts_an_und_keinen_schritt(state, bib):
    ergebnis = T.wende_an(state, _plan(state, bib, "Profil;Adresse\nQuantum Wash XJ9000;1\n"), bib)
    assert ergebnis.geraete == 0 and ergebnis.ausgelassen == 1
    assert state.get_patched_fixtures() == [] and not get_undo_stack().can_undo()


def test_aenderung_zwischen_vorschau_und_anwenden_ueberschreibt_nichts(state, bib):
    """Der Plan ist von vorhin; inzwischen liegt dort ein Gerät. Anwenden
    rechnet neu und lässt die Zeile aus."""
    plan = _plan(state, bib, f"Name;Profil;Modus;Adresse\nA;{PAR};8-Kanal RGBW;100\nB;{PAR};8-Kanal RGBW;200\n")
    assert len(plan.anlegbare()) == 2
    _vorhandenes(state, bib)                                # Kanal 100–107
    ergebnis = T.wende_an(state, plan, bib)
    assert ergebnis.geraete == 1 and ergebnis.ausgelassen == 1
    assert sorted(f.label for f in state.get_patched_fixtures()) == ["Altbestand", "B"]


def test_zweimal_dieselbe_tabelle_legt_beim_zweiten_mal_nichts_an(state, bib):
    text = f"Name;Profil;Modus;Adresse\nA;{PAR};8-Kanal RGBW;1\n"
    assert T.wende_an(state, _plan(state, bib, text), bib).geraete == 1
    plan = _plan(state, bib, text)
    assert plan.zeilen[0].status == T.UEBERSCHNEIDUNG
    assert T.wende_an(state, plan, bib).geraete == 0
    assert len(state.get_patched_fixtures()) == 1


def test_gewaehltes_profil_wird_angelegt(state, bib):
    mh = bib.finde("U King", MH).profil
    plan = _plan(state, bib, f"Name;Profil;Adresse\nKopf;{MH};1\n", wahl={0: (mh.id, "9-Kanal")})
    T.wende_an(state, plan, bib)
    fx = state.get_patched_fixtures()[0]
    assert (fx.label, fx.fixture_profile_id, fx.mode_name, fx.channel_count) == \
        ("Kopf", mh.id, "9-Kanal", 9)


# ── Rückgängig-Gruppe (UndoStack.gruppe) ─────────────────────────────────────

def test_undo_gruppe_fasst_zusammen_und_dreht_die_reihenfolge_um():
    from src.core.undo import Command, UndoStack
    stack, spur = UndoStack(), []
    with stack.gruppe("Sammel"):
        for i in range(3):
            stack.push(Command(label=str(i), do=lambda i=i: spur.append(f"do{i}"),
                               undo=lambda i=i: spur.append(f"undo{i}")))
    assert spur == ["do0", "do1", "do2"] and len(stack._undo) == 1
    assert stack.undo_label() == "Sammel"
    stack.undo()
    assert spur[3:] == ["undo2", "undo1", "undo0"]
    stack.redo()
    assert spur[6:] == ["do0", "do1", "do2"]


def test_undo_gruppe_leer_und_mit_fehler():
    from src.core.undo import Command, UndoStack
    stack, spur = UndoStack(), []
    with stack.gruppe("leer"):
        pass
    assert not stack.can_undo()
    with pytest.raises(RuntimeError):
        with stack.gruppe("halb"):
            stack.push(Command("a", do=lambda: None, undo=lambda: spur.append("a")))
            raise RuntimeError("mittendrin")
    assert len(stack._undo) == 1                    # das Angelegte bleibt rücknehmbar
    stack.push(Command("danach", do=lambda: None, undo=lambda: None))
    assert len(stack._undo) == 2                    # Sammeln ist wieder aus

    def kaputt():
        raise ValueError("x")
    with stack.gruppe("teil wirft"):
        stack.push(Command("1", do=lambda: None, undo=lambda: spur.append("1")))
        stack.push(Command("2", do=lambda: None, undo=kaputt))
    stack.undo()
    assert spur == ["1"]                            # das andere Teil lief trotzdem


# ── Dialog ───────────────────────────────────────────────────────────────────

def _dialog(state, bib, text=TABELLE):
    return D.PatchImportDialog(state, T.lies_tabelle(text), bib, "liste.csv")


def test_dialog_zeigt_zeilen_gruende_und_zaehlerzeile(state, bib):
    _vorhandenes(state, bib)
    dlg = _dialog(state, bib)
    assert dlg._table.rowCount() == 6
    assert dlg.zaehlerzeile() == "5 Geräte werden angelegt, 2 offen, 1 Überschneidung"
    assert dlg.anwenden_moeglich()
    assert dlg.status_text(0) == "wird angelegt (3 Geräte)"
    assert "vorhandenen Gerät „Altbestand“" in dlg.status_text(3)
    assert dlg.status_text(4).startswith("offen — ")
    assert "2 Modi" in dlg.status_text(5)
    assert dlg._table.item(0, D.S_NAME).text() == "PAR  ×3"
    assert dlg._table.item(1, D.S_UNIV).text() == "2"
    assert dlg._table.item(1, D.S_ADRESSE).text() == "50"
    assert dlg._table.item(1, D.S_KANAELE).text() == "11"
    assert dlg._table.item(5, D.S_KANAELE).text() == ""
    assert "liste.csv" in dlg._lbl_kopf.text() and "Semikolon" in dlg._lbl_kopf.text()


def test_dialog_auswahlfelder(state, bib):
    dlg = _dialog(state, bib)
    erkannt, unbekannt, ohne_modus = dlg._auswahl[0], dlg._auswahl[4], dlg._auswahl[5]
    assert "8-Kanal RGBW (8 Kanäle)" in erkannt.currentText()
    assert not unbekannt.isEnabled() and unbekannt.currentText() == D.KEIN_VORSCHLAG
    assert ohne_modus.currentText() == D.MODUS_WAEHLEN
    assert {ohne_modus.itemData(i)[1] for i in range(1, ohne_modus.count())} >= {"11-Kanal", "9-Kanal"}


def test_dialog_ohne_anlegbare_zeile_ist_anwenden_grau(state, bib):
    dlg = _dialog(state, bib, f"Name;Profil;Adresse\nKopf;{MH};1\nX;Quantum Wash XJ9000;20\n")
    assert not dlg.anwenden_moeglich()
    assert dlg.zaehlerzeile() == "Kein Gerät wird angelegt, 2 offen"
    assert dlg._btn_anwenden.toolTip() == D.TIPP_ANWENDEN_AUS
    dlg._anwenden()                                   # auch direkt gerufen: nichts
    assert dlg.ergebnis is None and state.get_patched_fixtures() == []


def test_dialog_profilwahl_macht_die_zeile_anlegbar(state, bib):
    dlg = _dialog(state, bib, f"Name;Profil;Adresse\nKopf;{MH};1\n")
    box = dlg._auswahl[0]
    tabellen_items = [dlg._table.item(0, s) for s in (D.S_NAME, D.S_STATUS)]
    rahmen = dlg._table.cellWidget(0, D.S_PROFIL)
    index = next(i for i in range(box.count()) if (box.itemData(i) or (0, ""))[1] == "9-Kanal")

    dlg.waehle(0, index)

    assert dlg.anwenden_moeglich()
    assert dlg.status_text(0) == "wird angelegt"
    assert dlg._table.item(0, D.S_KANAELE).text() == "9"
    assert dlg.zaehlerzeile() == "1 Gerät wird angelegt"
    assert dlg._btn_anwenden.toolTip() == D.TIPP_ANWENDEN
    # Qt-Falle: weder das Auswahlfeld noch die Zellen wurden ersetzt
    assert dlg._auswahl[0] is box and dlg._table.cellWidget(0, D.S_PROFIL) is rahmen
    assert box.parent() is rahmen
    assert [dlg._table.item(0, s) for s in (D.S_NAME, D.S_STATUS)] == tabellen_items
    # zurück auf „— Modus wählen —“ macht sie wieder offen
    dlg.waehle(0, 0)
    assert not dlg.anwenden_moeglich() and dlg.wahl == {}


def test_dialog_wahl_eines_vorschlags_bei_nur_aehnlichem_namen(state, bib):
    dlg = _dialog(state, bib, "Name;Profil;Adresse\nKopf;ZQ-02001 Mini Moving-Head;1\n")
    box = dlg._auswahl[0]
    assert box.currentText() == D.BITTE_WAEHLEN and not dlg.anwenden_moeglich()
    index = next(i for i in range(1, box.count()) if MH in box.itemText(i)
                 and box.itemData(i)[1] == "11-Kanal")
    dlg.waehle(0, index)
    assert dlg.anwenden_moeglich() and dlg.status_text(0) == "wird angelegt"


def test_dialog_wahl_zeigt_neue_ueberschneidung_in_anderer_zeile(state, bib):
    dlg = _dialog(state, bib, f"Name;Profil;Modus;Adresse\nA;{MH};;1\nB;{PAR};8-Kanal RGBW;10\n")
    assert dlg.status_text(1) == "wird angelegt"
    box = dlg._auswahl[0]
    dlg.waehle(0, next(i for i in range(box.count())
                       if (box.itemData(i) or (0, ""))[1] == "11-Kanal"))
    assert "Überschneidet sich mit Zeile 2" in dlg.status_text(1)
    assert not dlg.anwenden_moeglich()
    assert dlg.zaehlerzeile() == "Kein Gerät wird angelegt, 2 Überschneidungen"


def test_dialog_mausrad_verstellt_kein_auswahlfeld(state, bib):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    dlg = _dialog(state, bib, f"Name;Profil;Adresse\nKopf;{MH};1\n")
    box = dlg._auswahl[0]
    ereignis = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120),
                           Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                           Qt.ScrollPhase.NoScrollPhase, False)
    box.wheelEvent(ereignis)
    assert box.currentIndex() == 0 and dlg.wahl == {}


def test_dialog_anwenden_legt_an_und_ist_ein_schritt(state, bib):
    _vorhandenes(state, bib)
    dlg = _dialog(state, bib)
    dlg._anwenden()
    assert dlg.result() == D.PatchImportDialog.DialogCode.Accepted
    assert dlg.ergebnis.geraete == 5 and dlg.ergebnis.ausgelassen == 3
    assert len(state.get_patched_fixtures()) == 6
    assert len(get_undo_stack()._undo) == 1
    text = D.meldung_nach_import(dlg.ergebnis)
    assert text.startswith("5 Geräte angelegt.")
    assert "3 Zeilen der Tabelle wurden nicht angelegt" in text
    assert "Rückgängig (Strg+Z)" in text


def test_alle_knoepfe_haben_einen_tooltip(state, bib):
    from PySide6.QtWidgets import QPushButton
    dlg = _dialog(state, bib)
    knoepfe = dlg.findChildren(QPushButton)
    assert {k.text() for k in knoepfe} == {"Vorlage speichern …", "Anwenden", "Abbrechen"}
    assert all(k.toolTip().strip() for k in knoepfe)
    assert all(box.toolTip().strip() for box in dlg._auswahl)


# ── Einstiege ────────────────────────────────────────────────────────────────

def test_importieren_starten_meldet_eine_unlesbare_tabelle(tmp_path, state, bib, monkeypatch):
    gezeigt = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: gezeigt.append(a[2]) or QMessageBox.StandardButton.Ok)
    pfad = tmp_path / "kaputt.csv"
    pfad.write_text("Name;Universum\nA;1\n", encoding="utf-8")
    assert D.importieren_starten(None, state, str(pfad), bib) is None
    assert "„Profil“" in gezeigt[0] and "Vorlage speichern …" in gezeigt[0]
    assert state.get_patched_fixtures() == []


def test_importieren_starten_ganzer_weg(tmp_path, state, bib, monkeypatch):
    gezeigt = []
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: gezeigt.append(a[2]) or QMessageBox.StandardButton.Ok)

    def _exec(dlg):                       # der Nutzer klickt „Anwenden“
        dlg._anwenden()
        return dlg.result()
    monkeypatch.setattr(D.PatchImportDialog, "exec", _exec)
    pfad = tmp_path / "liste.csv"
    pfad.write_bytes(TABELLE.encode("cp1252"))
    ergebnis = D.importieren_starten(None, state, str(pfad), bib)
    assert ergebnis.geraete == 6          # ohne Altbestand geht auch „Kollision“
    assert gezeigt and gezeigt[0].startswith("6 Geräte angelegt.")


def test_abbrechen_legt_nichts_an(tmp_path, state, bib, monkeypatch):
    monkeypatch.setattr(D.PatchImportDialog, "exec", lambda dlg: 0)
    pfad = tmp_path / "liste.csv"
    pfad.write_text(TABELLE, encoding="utf-8")
    assert D.importieren_starten(None, state, str(pfad), bib) is None
    assert state.get_patched_fixtures() == [] and not get_undo_stack().can_undo()


def test_vorlage_speichern_schreibt_und_meldet(tmp_path, monkeypatch):
    gezeigt = []
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: gezeigt.append(a[2]) or QMessageBox.StandardButton.Ok)
    pfad = str(tmp_path / "vorlage.csv")
    assert D.vorlage_speichern(None, pfad) == pfad
    assert T.lies_datei(pfad).fehler == "" and "Vorlage gespeichert" in gezeigt[0]


def test_patch_ansicht_hat_den_knopf_mit_beiden_eintraegen(tmp_path, state, bib, monkeypatch):
    import src.ui.views.patch_view as PV
    monkeypatch.setattr(PV, "get_state", lambda: state)
    view = PV.PatchView()
    assert view._btn_import.toolTip().strip()
    aktionen = view._btn_import.menu().actions()
    assert [a.text() for a in aktionen] == ["Aus Tabelle importieren …", "Vorlage speichern …"]
    assert all(a.toolTip().strip() for a in aktionen)
    assert view._btn_import.menu().toolTipsVisible()

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)

    def _exec(dlg):
        dlg._anwenden()
        return dlg.result()
    monkeypatch.setattr(D.PatchImportDialog, "exec", _exec)
    monkeypatch.setattr(T, "bibliothek_aus_db", lambda: bib)
    pfad = tmp_path / "liste.csv"
    pfad.write_text(f"Name;Profil;Modus;Adresse;Anzahl\nPAR;{PAR};8-Kanal RGBW;1;2\n", encoding="utf-8")
    ergebnis = view._aus_tabelle_importieren(str(pfad))
    assert ergebnis.geraete == 2
    # die Patch-Tabelle hat sich über patch_changed selbst aufgefrischt
    assert view._table.rowCount() == 2
    assert [view._table.item(r, 1).text() for r in range(2)] == ["PAR 1", "PAR 2"]


# ── Nachbesserungen: Menüknopf, Spaltenbreiten, Auswahlfeld ──────────────────

LANG = (
    "Name;Hersteller;Profil;Modus;Universum;Adresse;Anzahl\n"
    f"Ein ziemlich langer Gerätename für die vordere Traverse links;Generic;{PAR};8-Kanal RGBW;1;1;3\n"
    f"Kollision mit dem Altbestand;Generic;{PAR};8-Kanal RGBW;1;104;1\n"
    "Unbekannt;;Quantum Wash XJ9000 Extended Professional Edition;;1;300;1\n"
    f"Ohne Modus;U King;{MH};;1;400;1\n"
    f"Ähnlich;;Stage Light ZQ0142;;1;450;1\n"
)


def _gezeigt(state, bib, breite, text=LANG):
    dlg = _dialog(state, bib, text)
    dlg.resize(breite, 600)
    dlg.show()
    _app.processEvents()
    return dlg


@pytest.mark.parametrize("breite", [900, 1100, 1400])
def test_status_spalte_bleibt_im_bild(state, bib, breite):
    """Bei 900 px rutschte „Status“ aus dem Bild — der Grund war nur über den
    waagerechten Rollbalken zu lesen."""
    _vorhandenes(state, bib)
    dlg = _gezeigt(state, bib, breite)
    tabelle, kopf = dlg._table, dlg._table.horizontalHeader()
    assert dlg.width() == breite
    assert kopf.length() <= tabelle.viewport().width()
    assert tabelle.horizontalScrollBar().maximum() == 0
    rechts = kopf.sectionViewportPosition(D.S_STATUS) + kopf.sectionSize(D.S_STATUS)
    assert rechts <= tabelle.viewport().width()
    assert kopf.sectionSize(D.S_STATUS) >= D.STATUS_MIN
    for spalte, (kleinste, groesste) in D.BIEGSAM.items():
        assert kleinste <= kopf.sectionSize(spalte) <= groesste
    for spalte in (D.S_ZEILE, D.S_UNIV, D.S_ADRESSE, D.S_KANAELE):
        assert kopf.sectionSize(spalte) <= D.SCHMAL_MAX


def test_grund_bricht_um_statt_abgeschnitten_zu_werden(state, bib):
    _vorhandenes(state, bib)
    dlg = _gezeigt(state, bib, 900)
    tabelle = dlg._table
    zeile = next(z for z in range(tabelle.rowCount())
                 if "Altbestand" in dlg.status_text(z))
    item = tabelle.item(zeile, D.S_STATUS)
    fm = tabelle.fontMetrics()
    breite = tabelle.columnWidth(D.S_STATUS)
    assert fm.horizontalAdvance(item.text()) > breite      # passt nicht in eine Zeile
    assert tabelle.rowHeight(zeile) >= 2 * fm.height()      # also mehrzeilig
    assert item.toolTip() == item.text()


def test_breiter_dialog_gibt_den_textspalten_mehr_platz(state, bib):
    schmal = _gezeigt(state, bib, 900)
    breit = _gezeigt(state, bib, 1400)
    assert breit._table.columnWidth(D.S_PROFIL) > schmal._table.columnWidth(D.S_PROFIL)
    assert breit._table.columnWidth(D.S_NAME) > schmal._table.columnWidth(D.S_NAME)
    # eng: zuerst bekommt das Auswahlfeld Platz (sein Text bricht nicht um)
    assert schmal._table.columnWidth(D.S_NAME) == D.BIEGSAM[D.S_NAME][0]
    assert schmal._table.columnWidth(D.S_PROFIL) > D.BIEGSAM[D.S_PROFIL][0]


def test_mindestbreite_reicht_fuer_alle_spalten_und_den_grund(state, bib):
    dlg = _gezeigt(state, bib, 400)                  # kleiner geht nicht
    assert dlg.width() == dlg.minimumWidth() <= 900
    kopf = dlg._table.horizontalHeader()
    assert kopf.sectionSize(D.S_STATUS) >= D.STATUS_MIN
    assert dlg._table.horizontalScrollBar().maximum() == 0


def test_startgroesse_passt_zu_inhalt_und_bildschirm(state, bib):
    dlg = _dialog(state, bib, LANG)
    dlg.show()
    _app.processEvents()
    flaeche = _app.primaryScreen().availableGeometry()
    assert dlg.width() <= flaeche.width() and dlg.height() <= flaeche.height()
    assert dlg.width() >= min(D.START_BREITE[0], flaeche.width() - 16)
    assert dlg._table.horizontalScrollBar().maximum() == 0
    # wer vorher selbst eine Größe setzt, behält sie
    eigen = _dialog(state, bib, LANG)
    eigen.resize(950, 500)
    eigen.show()
    _app.processEvents()
    assert (eigen.width(), eigen.height()) == (950, 500)


def test_auswahlfeld_liste_ist_so_breit_wie_der_laengste_eintrag(state, bib):
    """Im Feld stand „… 8-Kanal RGBW (8 Kanael“ — rechts abgeschnitten."""
    dlg = _gezeigt(state, bib, 900)
    for box in dlg._auswahl:
        fm = box.fontMetrics()
        laengster = max(fm.horizontalAdvance(box.itemText(i)) for i in range(box.count()))
        assert box.view().minimumWidth() > laengster
        assert box.toolTip().startswith(box.currentText())
        assert len(box.toolTip()) > len(box.currentText()) + 20   # Erklärung bleibt


def test_auswahlfeld_tooltip_folgt_der_wahl(state, bib):
    dlg = _dialog(state, bib, f"Name;Profil;Adresse\nKopf;{MH};1\n")
    box = dlg._auswahl[0]
    assert box.toolTip().startswith(D.MODUS_WAEHLEN)
    dlg.waehle(0, 1)
    assert box.toolTip().startswith(box.itemText(1)) and "(" in box.itemText(1)
    assert "Modus" in box.toolTip().split("\n\n", 1)[1]


def test_import_knopf_ist_ein_menueknopf_und_per_tastatur_bedienbar(state, monkeypatch):
    """STAB-33: kein QPushButton.setMenu. Leertaste auf dem Knopf klappt das
    Menü auf, Pfeil-ab + Eingabe löst den ersten Eintrag aus.

    IMP-3: das gilt für die Ansicht ALLEIN. Im Hauptfenster gehört die
    Leertaste dem Kürzel GO; dort öffnet die Eingabetaste das Menü
    (tests/test_imp3_dialog_und_patch.py)."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton
    import src.ui.views.patch_view as PV
    from src.ui.widgets.menue_knopf import MenueKnopf
    monkeypatch.setattr(PV, "get_state", lambda: state)
    gerufen = []
    monkeypatch.setattr(PV.PatchView, "_aus_tabelle_importieren",
                        lambda self, pfad=None: gerufen.append("import"))
    monkeypatch.setattr(PV.PatchView, "_import_vorlage_speichern",
                        lambda self: gerufen.append("vorlage"))
    view = PV.PatchView()
    knopf = view._btn_import
    assert isinstance(knopf, MenueKnopf) and knopf.text() == "Tabellen-Import ▾"
    assert QPushButton.menu(knopf) is None            # Qt kennt das Menü nicht
    assert knopf.focusPolicy() & Qt.FocusPolicy.TabFocus
    menu = knopf.menu()
    view.show()
    _app.processEvents()
    try:
        assert not menu.isVisible()
        knopf.setFocus()
        QTest.keyClick(knopf, Qt.Key.Key_Space)
        _app.processEvents()
        assert menu.isVisible()
        QTest.keyClick(menu, Qt.Key.Key_Down)
        assert menu.activeAction() is view._act_import
        QTest.keyClick(menu, Qt.Key.Key_Return)
        _app.processEvents()
        assert gerufen == ["import"] and not menu.isVisible()
        knopf.click()
        _app.processEvents()
        QTest.keyClick(menu, Qt.Key.Key_Down)
        QTest.keyClick(menu, Qt.Key.Key_Down)
        QTest.keyClick(menu, Qt.Key.Key_Return)
        _app.processEvents()
        assert gerufen == ["import", "vorlage"]
    finally:
        menu.hide()
