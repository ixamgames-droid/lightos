"""VCB-39: Tempo-Bus-Fingerabdruck bei VC-gesteuerten Bussen.

Steuert ein VC-Element (Tempo-Bus-Regler, Speed-Knoten) einen Bus, stellt es
``role``/``parent_id``/``bus_multiplier`` beim BEDIENEN selbst um — das ist
Live-Bedienung und darf keine Speichern-Frage ausloesen (UI-69). Bis VCB-39 fiel
damit aber auch eine echte Aenderung derselben Felder im Tempo-Bus-Editor
(Einrichten) aus dem Fingerabdruck: Beenden fragte nicht nach dem Speichern.

Geprueft werden beide Wege:
1. Editor-Aenderung an einem VC-gesteuerten Bus zaehlt (und Zuruecknehmen im
   Editor macht die Show wieder unveraendert). Der Editor laesst beim Wechsel
   auf Master Eltern/Faktor stehen — die stehen dann auch in der Datei, das
   Zuruecknehmen wird deshalb ueber den Faktor geprueft.
2. VC-Bedienung (Quelle Sound/Tap/Fix am Regler) zaehlt weiterhin nicht —
   auch nicht NACH einer Editor-Aenderung, die gespeichert wurde.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from src.core.show import show_file as SF

_app = QApplication.instance() or QApplication([])


_VC = {"widgets": [
    {"type": "VCTempoBusController", "caption": "Tempo B", "x": 10, "y": 10,
     "w": 220, "h": 170, "tempo_bus_id": "B", "source": "tap", "factor": 1.0,
     "fixed_bpm": 128.0},
]}


@pytest.fixture
def umgebung():
    from src.core.app_state import get_state
    from src.core.engine.tempo_bus import get_tempo_bus_manager
    state = get_state()
    SF.reset_show()
    mgr = get_tempo_bus_manager()
    # Die festen Busse A-D legt der Editor beim Aufbau selbst an — vorher
    # anlegen, sonst waere das Anlegen die Aenderung.
    for b in mgr.FIXED_BUSES:
        mgr.ensure_bus(b).set_role("master")
    state._vc_layout = {"widgets": [dict(w) for w in _VC["widgets"]]}
    SF.merke_show_stand(state)
    assert not SF.show_hat_aenderungen(state), "Vorbedingung: frisch gemerkt"
    yield state, mgr
    SF.reset_show()


def _editor(mgr):
    from src.ui.views.tempo_bus_view import TempoBusView
    view = TempoBusView()
    view._refresh_speeds()
    return view


def _bus_waehlen(view, bus_id):
    t = view._bus_table
    for r in range(t.rowCount()):
        if t.item(r, 0).text() == bus_id:
            t.selectRow(r)
            assert view._selected_bus_id() == bus_id
            return
    pytest.fail(f"Bus {bus_id!r} nicht in der Editor-Tabelle")


def _editor_setzen(view, role, parent="", faktor=1.0):
    view._edit_role.setCurrentIndex(view._edit_role.findData(role))
    view._refresh_speeds()           # Parent-Liste wie beim Oeffnen fuellen
    view._edit_parent.setCurrentIndex(view._edit_parent.findData(parent))
    view._edit_factor.setCurrentIndex(view._edit_factor.findData(faktor))
    view._edit_role.setCurrentIndex(view._edit_role.findData(role))
    view._on_apply_bus_edit()


def _regler():
    from src.ui.virtualconsole.vc_tempo_bus_controller import VCTempoBusController
    tbc = VCTempoBusController("Tempo B")
    tbc.tempo_bus_id = "B"
    return tbc


def test_editor_aenderung_an_vc_gesteuertem_bus_zaehlt(umgebung):
    state, mgr = umgebung
    view = _editor(mgr)
    try:
        _bus_waehlen(view, "B")
        _editor_setzen(view, "sub", parent="A", faktor=2.0)
        bus = mgr.get("B")
        assert (bus.role, bus.parent_id, bus.bus_multiplier) == ("sub", "A", 2.0), \
            "Vorbedingung: der Editor hat den Bus umgestellt"
        assert SF.show_hat_aenderungen(state), \
            "Rolle/Eltern/Faktor im Tempo-Bus-Editor sind Einrichtung -> Speichern-Frage"
    finally:
        view.deleteLater()


def test_nur_faktor_im_editor_zaehlt(umgebung):
    state, mgr = umgebung
    mgr.get("B").set_role("sub")
    mgr.get("B").set_parent("A")
    SF.merke_show_stand(state)
    view = _editor(mgr)
    try:
        _bus_waehlen(view, "B")
        _editor_setzen(view, "sub", parent="A", faktor=0.5)
        assert SF.show_hat_aenderungen(state), "Faktor im Editor = Einrichtung"
        # Zuruecknehmen im Editor -> wieder unveraendert
        _bus_waehlen(view, "B")
        _editor_setzen(view, "sub", parent="A", faktor=1.0)
        assert not SF.show_hat_aenderungen(state), \
            "Editor-Aenderung zurueckgenommen = unveraendert"
    finally:
        view.deleteLater()


def test_vc_bedienung_zaehlt_weiter_nicht(umgebung):
    state, mgr = umgebung
    tbc = _regler()
    try:
        tbc.set_source("sound")          # Bus B -> Sub, Eltern "", Faktor 1
        assert mgr.get("B").role == "sub", "Vorbedingung: der Regler stellt um"
        assert not SF.show_hat_aenderungen(state), "Quelle Sound = Live-Bedienung"
        tbc.set_source("tap")
        tbc.set_source("fix")
        assert not SF.show_hat_aenderungen(state), "Tap/Fix = Live-Bedienung"
    finally:
        tbc.deleteLater()


def test_vc_bedienung_nach_gespeicherter_editor_aenderung(umgebung):
    state, mgr = umgebung
    view = _editor(mgr)
    tbc = _regler()
    try:
        _bus_waehlen(view, "B")
        _editor_setzen(view, "sub", parent="A", faktor=2.0)
        assert SF.show_hat_aenderungen(state)
        SF.merke_show_stand(state)       # wie nach dem Speichern
        assert not SF.show_hat_aenderungen(state)
        tbc.set_source("sound")          # Regler haengt B um (Eltern "", Faktor 1)
        assert mgr.get("B").parent_id == "", "Vorbedingung: der Regler stellt um"
        assert not SF.show_hat_aenderungen(state), \
            "VC-Bedienung nach gespeicherter Einrichtung bleibt Live-Bedienung"
        tbc.set_source("tap")
        assert not SF.show_hat_aenderungen(state)
    finally:
        tbc.deleteLater()
        view.deleteLater()


def test_editor_nach_vc_bedienung_zaehlt(umgebung):
    """Der Regler hat B live umgestellt; danach richtet der Nutzer im Editor
    etwas ANDERES ein als gemerkt -> Frage."""
    state, mgr = umgebung
    tbc = _regler()
    view = _editor(mgr)
    try:
        tbc.set_source("sound")
        assert not SF.show_hat_aenderungen(state)
        _bus_waehlen(view, "B")
        _editor_setzen(view, "sub", parent="A", faktor=4.0)
        assert SF.show_hat_aenderungen(state)
    finally:
        tbc.deleteLater()
        view.deleteLater()


def test_geloescht_und_von_vc_neu_angelegt_zaehlt(umgebung):
    """Review-Befund: loescht der Editor einen eingerichteten Sub-Bus und legt
    die VC ihn beim Bedienen neu an (Master, Faktor 1), darf der alte
    eingerichtete Stand das nicht verdecken -> Frage."""
    state, mgr = umgebung
    view = _editor(mgr)
    try:
        _bus_waehlen(view, "B")
        _editor_setzen(view, "sub", parent="A", faktor=2.0)
        # B ans Ende, damit die Bus-Reihenfolge nach dem Neuanlegen gleich ist
        mgr._buses["B"] = mgr._buses.pop("B")
        SF.merke_show_stand(state)       # wie nach dem Speichern
        assert not SF.show_hat_aenderungen(state)
        _bus_waehlen(view, "B")
        view._on_delete_bus()
        mgr.ensure_bus("B")              # VC legt ihn beim Bedienen neu an
        assert mgr.get("B").role == "master", "Vorbedingung: neu als Master"
        assert SF.show_hat_aenderungen(state), \
            "geloescht + neu angelegt mit anderer Einrichtung = Aenderung"
    finally:
        view.deleteLater()
