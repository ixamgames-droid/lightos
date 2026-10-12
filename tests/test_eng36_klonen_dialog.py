"""ENG-36: Dialog „Klonen" und der Einstieg im Patch.

Geprüft wird das Verhalten des Dialogs (kein Bild): ohne Wahl von
„Hinzufügen/Ersetzen" kein „Anwenden", die Zähler stimmen mit der Liste
überein, vor „Anwenden" wird nichts geschrieben, davor entsteht die
Sicherung, danach liegt EIN Schritt im Rückgängig-Verlauf.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt                                        # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox              # noqa: E402

from _eng36_show import CMY, RGB, RGBW, show_fixture                 # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets             # noqa: E402
from src.core.show import klonen as K                                # noqa: E402
from src.core.undo import get_undo_stack                             # noqa: E402
from src.ui.widgets import klonen_dialog as D                        # noqa: E402

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _keine_fenster_uebrig():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


@pytest.fixture
def show(tmp_path, monkeypatch):
    yield from show_fixture(tmp_path, monkeypatch)


class _Umgebung(D.Umgebung):
    def __init__(self, state, sicherung="sicherung.lshow", pruefe=None):
        super().__init__(None, state)
        self.sicherung, self.pruefe = sicherung, pruefe
        self.gesichert = 0
        self.nachgezogen = 0

    def sichern(self):
        self.gesichert += 1
        if self.pruefe:
            self.pruefe()
        return self.sicherung

    def nachziehen(self, plan):
        self.nachgezogen += 1


def _dialog(show, quellen, ziele, **kw):
    umgebung = kw.pop("umgebung", None) or _Umgebung(show.state)
    return D.KlonenDialog(show.state, quellen, ziele, umgebung=umgebung,
                          snap_library=show.snaps,
                          palette_manager=show.paletten), umgebung


def _beispiel(show):
    show.patch(1, RGB, "PAR links")
    show.patch(2, RGBW, "PAR neu")
    show.patch(3, CMY, "Kopf")
    snap = show.snaps.add_snap("Rot", "", {1: {"color_r": 255, "color_g": 0,
                                              "color_b": 0, "intensity": 200}})
    show.snaps.add_snap("Position", "", {3: {"pan": 1, "tilt": 2, "cmy_c": 9}})
    show.gruppe("Front", {"0,0": 1})
    return snap


def _zeilen(dlg) -> dict:
    out: dict = {}
    for i in range(dlg._liste.count()):
        k = dlg._liste.item(i).data(Qt.ItemDataRole.UserRole)
        if k:
            out[k] = out.get(k, 0) + 1
    return out


def test_anwenden_erst_nach_wahl_und_keine_vorauswahl(show):
    _beispiel(show)
    dlg, _u = _dialog(show, [1], [2])
    assert not dlg._hinzufuegen.isChecked() and not dlg._ersetzen.isChecked()
    assert not dlg._anwenden.isEnabled()
    assert dlg.plan() is None and _zeilen(dlg) == {}
    assert "Hinzufügen" in dlg._zaehler.text() and "Ersetzen" in dlg._zaehler.text()
    assert dlg._ans_ende.isChecked(), "Vorgabe der Position: ans Ende"
    assert all(cb.isChecked() for cb in dlg._haekchen.values())
    assert list(dlg._haekchen) == list(K.BEREICHE)
    dlg._ersetzen.setChecked(True)
    assert dlg._anwenden.isEnabled()
    assert "Sicherung" in dlg._sicherung.text() and "vor dem Klonen" in dlg._sicherung.text()


def test_vorschau_zaehler_stimmen_mit_liste_und_plan(show):
    _beispiel(show)
    dlg, _u = _dialog(show, [1, 3], [2])         # 2 Quellen, 1 Ziel
    dlg._hinzufuegen.setChecked(True)
    assert "passen nicht zusammen" in dlg._zaehler.text()
    assert not dlg._anwenden.isEnabled()

    dlg, _u = _dialog(show, [1], [2])
    dlg._hinzufuegen.setChecked(True)
    plan = dlg.plan()
    z = plan.zaehler()
    assert _zeilen(dlg) == {k: n for k, n in z.items() if n}
    # Gruppe + Dimmer 1:1 = unverändert, Farbe RGB → RGBW = übersetzt
    assert (z[K.UNVERAENDERT], z[K.UEBERSETZT], z[K.FAELLT_WEG]) == (2, 1, 0)
    text = dlg._zaehler.text()
    assert "2 unverändert übernommen" in text and "1 übersetzt" in text \
        and "0 fällt weg" in text
    assert "verschiedene Gerätetypen" in dlg._hinweise.text()
    assert "(3 Stellen)" in dlg._anwenden.text()

    # ein Häkchen weniger → die Vorschau rechnet neu
    dlg._haekchen[K.BEREICH_GRUPPEN].setChecked(False)
    assert dlg.plan().zaehler()[K.UNVERAENDERT] == 1
    assert _zeilen(dlg)[K.UNVERAENDERT] == 1


def test_ohne_aenderung_kein_anwenden(show):
    _beispiel(show)
    dlg, _u = _dialog(show, [2], [1])            # Gerät 2 kommt nirgends vor
    dlg._hinzufuegen.setChecked(True)
    assert dlg.plan() is not None and dlg.plan().aenderungen == 0
    assert not dlg._anwenden.isEnabled()
    assert "nirgends" in dlg._liste.item(0).text()


def test_faellt_weg_steht_in_der_vorschau(show):
    _beispiel(show)
    dlg, _u = _dialog(show, [3], [1])            # Kopf (CMY, Pan/Tilt) → RGB-PAR
    dlg._hinzufuegen.setChecked(True)
    z = dlg.plan().zaehler()
    assert z[K.UEBERSETZT] == 1 and z[K.FAELLT_WEG] == 1
    weg = [dlg._liste.item(i).text() for i in range(dlg._liste.count())
           if dlg._liste.item(i).data(Qt.ItemDataRole.UserRole) == K.FAELLT_WEG]
    assert "Pan" in weg[0] and "späteren Schritt" in weg[0]


def test_nichts_wird_geschrieben_vor_anwenden_und_sicherung_kommt_zuerst(show):
    snap = _beispiel(show)
    stack = get_undo_stack()
    beim_sichern = []
    umgebung = _Umgebung(show.state, pruefe=lambda: beim_sichern.append(dict(snap.values)))
    dlg, _ = _dialog(show, [1], [2], umgebung=umgebung)
    dlg._hinzufuegen.setChecked(True)
    dlg._neben.setChecked(True)
    dlg._ersetzen.setChecked(True)
    assert 2 not in snap.values and not stack.can_undo()
    assert umgebung.gesichert == 0

    dlg._anwenden.click()
    assert umgebung.gesichert == 1
    assert beim_sichern == [{1: snap.values[1]}], "gesichert wurde der Stand DAVOR"
    assert snap.values[2] == {"dimmer": 200, "color_r": 255, "color_g": 0,
                              "color_b": 0, "color_w": 0}
    assert dlg.ergebnis == 3 and dlg.result() == D.QDialog.DialogCode.Accepted
    assert stack.undo_label() == "Klonen 1 → 2" and len(stack._undo) == 1
    assert umgebung.nachgezogen == 1
    assert stack.undo()
    assert 2 not in snap.values
    assert show.state.group_fids_by_name("Front") == [1]
    assert umgebung.nachgezogen == 2


def test_ohne_sicherung_wird_gefragt_und_nein_schreibt_nichts(show, monkeypatch):
    snap = _beispiel(show)
    fragen = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: (fragen.append(a[2]),
                                         QMessageBox.StandardButton.No)[1])
    dlg, _u = _dialog(show, [1], [2], umgebung=_Umgebung(show.state, sicherung=None))
    dlg._hinzufuegen.setChecked(True)
    dlg._anwenden.click()
    assert fragen and "Sicherung" in fragen[0]
    assert 2 not in snap.values and dlg.ergebnis is None
    assert not get_undo_stack().can_undo()


def test_zielauswahl_ok_erst_bei_passender_anzahl(show):
    _beispiel(show)
    dlg = D.ZielAuswahlDialog(show.state, [1, 3])
    assert dlg._liste.count() == 1, "Quellen stehen nicht zur Wahl"
    assert not dlg._ok.isEnabled()
    dlg._liste.item(0).setSelected(True)
    assert not dlg._ok.isEnabled() and "passen nicht zusammen" in dlg._hinweis.text()
    dlg = D.ZielAuswahlDialog(show.state, [1])
    dlg._liste.item(0).setSelected(True)
    dlg._liste.item(1).setSelected(True)
    assert dlg._ok.isEnabled() and dlg.ziele() == [2, 3]


def test_umgebung_holt_ansichten_ab_und_schont_uebersprungene_konsole(show):
    class _VC:
        def __init__(self, uebersprungen):
            self._u, self.geladen = uebersprungen, []

        def uebersprungene_widgets(self):
            return self._u

        def from_dict(self, d):
            self.geladen.append(d)

    class _Fenster:
        def __init__(self, vc):
            self._vc_view = vc

        def _views_in_state(self, nur_vergleich=None):
            nur_vergleich["virtual_console"] = {"widgets": [
                {"type": "VCButton", "caption": "BO", "blackout_fids": [1]}]}
            nur_vergleich["snapshots"] = []

        def _sicherungs_name(self):
            return "Abend"

    show.patch(1, RGB)
    show.patch(2, RGB)
    alt = {"widgets": ["übersprungen"]}
    show.state._vc_layout = alt
    u = D.Umgebung(_Fenster(_VC(["Kaputt"])), show.state)
    u.abholen()
    assert u.konsole_gesperrt and show.state._vc_layout is alt
    dlg = D.KlonenDialog(show.state, [1], [2], umgebung=u,
                         snap_library=show.snaps, palette_manager=show.paletten)
    assert not dlg._haekchen[K.BEREICH_KONSOLE].isEnabled()
    assert K.BEREICH_KONSOLE not in dlg.optionen().bereiche

    vc = _VC([])
    u = D.Umgebung(_Fenster(vc), show.state)
    u.abholen()
    assert not u.konsole_gesperrt
    plan = K.plane(show.state, [1], [2], K.Optionen(wie=K.HINZUFUEGEN),
                   snap_library=show.snaps, palette_manager=show.paletten)
    K.anwenden_mit_rueckweg(show.state, plan, davor=u.abholen, danach=u.nachziehen)
    assert vc.geladen[-1]["widgets"][0]["blackout_fids"] == [1, 2]


def test_patch_einstieg_knopf_und_kontextmenue(show, monkeypatch):
    import src.ui.views.patch_view as PV
    _beispiel(show)
    monkeypatch.setattr(PV, "get_state", lambda: show.state)
    aufrufe = []
    monkeypatch.setattr(D, "klonen_starten",
                        lambda parent, state, quellen, fenster=None:
                        aufrufe.append(list(quellen)))
    pv = PV.PatchView()
    assert pv._btn_klonen.text() == "Klonen…"
    zeile = {pv._fid_at_row(r): r for r in range(pv._table.rowCount())}
    assert set(zeile) == {1, 2, 3}

    texte = [t for t, _ in pv._kontextmenue_eintraege(zeile[1])]
    assert "Klonen auf …" in texte
    dict(pv._kontextmenue_eintraege(zeile[1]))["Klonen auf …"]()
    assert aufrufe == [[1]]

    pv._table.selectRow(zeile[1])
    pv._table.setSelectionMode(pv._table.SelectionMode.MultiSelection)
    pv._table.selectRow(zeile[3])
    eintraege = dict(pv._kontextmenue_eintraege(zeile[3]))
    assert "2 Geräte klonen auf …" in eintraege
    eintraege["2 Geräte klonen auf …"]()
    assert sorted(aufrufe[-1]) == [1, 3]
    # Rechtsklick auf eine NICHT markierte Zeile: nur diese
    assert "Klonen auf …" in dict(pv._kontextmenue_eintraege(zeile[2]))
    pv._btn_klonen.click()
    assert sorted(aufrufe[-1]) == [1, 3]
