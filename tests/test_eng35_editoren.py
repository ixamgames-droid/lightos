"""ENG-35 Schritt 2: das Feld „Stufe“ in jedem Editor.

* jede Funktionsart hat das Auswahlfeld (Szene, Chaser, Sequenz, Sammlung,
  Skript, Ebenen-Effekt, Carousel, Matrix, Bewegung);
* eine Auswahl schreibt die Zahl der Stufe und ist EIN Rueckgaengig-Schritt;
* eine Zahl aus einer alten Show bleibt als „eigene Zahl (n)“ stehen;
* Matrix- und Bewegungs-Editor haben kein Zahlenfeld „Layer-Priorität“ mehr;
* 20-mal umschalten je Editor in einem eigenen Prozess stuerzt nicht ab.
"""
import gc
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QSpinBox

from src.core.engine import stufen
from src.core.engine.function_manager import get_function_manager
from src.core.undo import get_undo_stack
from src.ui.widgets.stufe_auswahl import (StufeAuswahl, setze_stufe,
                                          setze_stufen, stufen_melder)

REPO = Path(__file__).resolve().parent.parent
_ROLLE = os.environ.get("ENG35_ARBEITER", "")
_MARKE = "ENG35-EDITOREN-FERTIG"

AKZENTE = stufen.stufe_fuer_schluessel("akzente").zahl
STROBE = stufen.stufe_fuer_schluessel("strobe_blinder").zahl
NOTFALL = stufen.stufe_fuer_schluessel("notfall").zahl
GRUNDLICHT = stufen.stufe_fuer_schluessel("grundlicht").zahl


def _app():
    return QApplication.instance() or QApplication([])


def _waehle(feld: StufeAuswahl, zahl: int):
    """Wie der Nutzer: Eintrag in der Liste anklicken."""
    idx = feld.findData(zahl)
    assert idx >= 0, f"Stufe {zahl} fehlt in der Auswahl"
    feld.setCurrentIndex(idx)
    feld.activated.emit(idx)


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


# ── das Feld selbst ──────────────────────────────────────────────────────────

def test_feld_zeigt_fuenf_stufen_staerkste_oben(fm):
    feld = StufeAuswahl()
    assert [feld.itemText(i) for i in range(feld.count())] == [
        "Notfall", "Strobe & Blinder", "Akzente", "Effekte", "Grundlicht"]
    assert feld.zahl() == 0 and feld.currentText() == "Effekte"


def test_feld_fuehrt_eigene_zahl_als_eigenen_eintrag(fm):
    feld = StufeAuswahl()
    feld.setze_zahl(7)
    assert feld.currentText() == "eigene Zahl (7)" and feld.zahl() == 7
    feld.setze_zahl(10)                      # umbeschriften, kein zweiter Eintrag
    texte = [feld.itemText(i) for i in range(feld.count())]
    assert texte.count("eigene Zahl (10)") == 1
    assert not any(t == "eigene Zahl (7)" for t in texte)
    feld.setze_zahl(AKZENTE)
    assert feld.currentText() == "Akzente"


def test_laden_loest_kein_signal_aus(fm):
    feld = StufeAuswahl()
    gesehen = []
    feld.stufe_gewaehlt.connect(gesehen.append)
    feld.setze_zahl(NOTFALL)
    feld.setze_zahl(3)
    assert gesehen == []
    _waehle(feld, AKZENTE)
    assert gesehen == [AKZENTE]


def test_gebundenes_feld_schreibt_und_ist_ein_undo_schritt(fm):
    szene = fm.new_scene("Blinder")
    feld = StufeAuswahl(szene)
    stapel = get_undo_stack()
    assert not stapel.can_undo()
    _waehle(feld, STROBE)
    assert szene.priority == STROBE
    assert stapel.can_undo() and "Strobe & Blinder" in stapel.undo_label()
    assert stapel.undo()
    assert szene.priority == 0
    assert feld.zahl() == 0, "das Feld zieht nach dem Rueckgaengig nach"
    assert not stapel.can_undo(), "genau EIN Schritt je Aenderung"
    assert stapel.redo()
    assert szene.priority == STROBE and feld.zahl() == STROBE


def test_gleiche_stufe_nochmal_waehlen_ist_kein_schritt(fm):
    szene = fm.new_scene("Rot")
    feld = StufeAuswahl(szene)
    _waehle(feld, 0)
    assert not get_undo_stack().can_undo()


def test_mehrere_effekte_sind_ein_schritt(fm):
    a, b, c = fm.new_scene("A"), fm.new_scene("B"), fm.new_scene("C")
    b.priority = AKZENTE
    assert setze_stufe([a, b, c], AKZENTE) == 2      # b lag schon dort
    assert (a.priority, b.priority, c.priority) == (AKZENTE,) * 3
    stapel = get_undo_stack()
    assert stapel.undo()
    assert (a.priority, b.priority, c.priority) == (0, AKZENTE, 0)
    assert not stapel.can_undo()


def test_eigene_zahl_bleibt_bis_zur_bewussten_wahl(fm):
    szene = fm.new_scene("Alt")
    szene.priority = 7
    feld = StufeAuswahl(szene)
    assert feld.currentText() == "eigene Zahl (7)"
    assert szene.priority == 7, "Oeffnen des Editors aendert nichts"
    _waehle(feld, GRUNDLICHT)
    assert szene.priority == GRUNDLICHT
    get_undo_stack().undo()
    assert szene.priority == 7 and feld.currentText() == "eigene Zahl (7)"


def test_feld_folgt_aenderung_von_aussen(fm):
    szene = fm.new_scene("Rot")
    feld = StufeAuswahl(szene)
    setze_stufen([(szene, NOTFALL)])
    assert feld.zahl() == NOTFALL


def test_mausrad_ohne_fokus_verstellt_nichts(fm):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    feld = StufeAuswahl()
    feld.setze_zahl(AKZENTE)
    ereignis = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0),
                           QPoint(0, -120), Qt.MouseButton.NoButton,
                           Qt.KeyboardModifier.NoModifier,
                           Qt.ScrollPhase.NoScrollPhase, False)
    feld.wheelEvent(ereignis)
    assert feld.zahl() == AKZENTE


# ── jede Funktionsart ────────────────────────────────────────────────────────

def _editoren(manager):
    """(Name, Funktion, Editor) fuer alle gebundenen Editoren."""
    from src.core.engine.script_func import ScriptFunction
    from src.ui.views.carousel_editor import CarouselEditor
    from src.ui.views.chaser_editor import ChaserEditor
    from src.ui.views.collection_editor import CollectionEditor
    from src.ui.views.effect_layer_editor import EffectLayerEditor
    from src.ui.views.scene_editor import SceneEditor
    from src.ui.views.script_editor import ScriptEditor
    from src.ui.views.sequence_editor import SequenceEditor

    skript = ScriptFunction()
    manager.add(skript)
    paare = [
        ("Szene", manager.new_scene("S"), SceneEditor),
        ("Chaser", manager.new_chaser("C"), ChaserEditor),
        ("Sequenz", manager.new_sequence("Q"), SequenceEditor),
        ("Sammlung", manager.new_collection("K"), CollectionEditor),
        ("Skript", skript, ScriptEditor),
        ("Ebenen-Effekt", manager.new_layered_effect("L"), EffectLayerEditor),
        ("Carousel", manager.new_carousel("R"), CarouselEditor),
    ]
    return [(name, f, klasse(f)) for name, f, klasse in paare]


def test_jeder_gebundene_editor_hat_das_feld_und_schreibt(fm):
    for name, f, editor in _editoren(fm):
        try:
            feld = getattr(editor, "_stufe_combo", None)
            assert isinstance(feld, StufeAuswahl), f"{name}: Feld „Stufe“ fehlt"
            assert feld.zahl() == 0, name
            _waehle(feld, AKZENTE)
            assert f.priority == AKZENTE, f"{name}: Stufe nicht geschrieben"
            _waehle(feld, GRUNDLICHT)
            assert f.priority == GRUNDLICHT, name
        finally:
            editor.close()
            editor.deleteLater()


def test_editor_factory_liefert_das_feld_fuer_szene_chaser_sequenz_sammlung(fm):
    from src.ui.views.function_manager_view import create_function_editor
    for f in (fm.new_scene("S"), fm.new_chaser("C"), fm.new_sequence("Q"),
              fm.new_collection("K")):
        editor = create_function_editor(f)
        try:
            assert isinstance(editor._stufe_combo, StufeAuswahl), type(editor)
        finally:
            editor.deleteLater()


def test_szene_und_chaser_binden_bei_wechsel_neu(fm):
    from src.ui.views.chaser_editor import ChaserEditor
    from src.ui.views.scene_editor import SceneEditor
    a, b = fm.new_scene("A"), fm.new_scene("B")
    b.priority = NOTFALL
    ed = SceneEditor(a)
    try:
        ed.set_scene(b)
        assert ed._stufe_combo.zahl() == NOTFALL
        _waehle(ed._stufe_combo, AKZENTE)
        assert (a.priority, b.priority) == (0, AKZENTE)
    finally:
        ed.deleteLater()
    c, d = fm.new_chaser("C"), fm.new_chaser("D")
    d.priority = 7
    ed = ChaserEditor(c)
    try:
        ed.set_chaser(d)
        assert ed._stufe_combo.currentText() == "eigene Zahl (7)"
        _waehle(ed._stufe_combo, STROBE)
        assert (c.priority, d.priority) == (0, STROBE)
    finally:
        ed.deleteLater()


def _keine_layer_prioritaet(view):
    from PySide6.QtWidgets import QLabel
    assert not hasattr(view, "_priority_spin"), "altes Zahlenfeld ist noch da"
    texte = [lbl.text() for lbl in view.findChildren(QLabel)]
    assert not any("Layer-Priorit" in t for t in texte), texte
    assert any(t == "Stufe:" for t in texte), "Beschriftung „Stufe:“ fehlt"
    assert not isinstance(view._stufe_combo, QSpinBox)


def test_matrix_editor_stufe_statt_zahlenfeld(fm):
    from src.ui.views.rgb_matrix_view import RgbMatrixView
    mv = RgbMatrixView()
    try:
        _keine_layer_prioritaet(mv)
        mv._add()
        assert mv._current is not None and mv._saved is not None
        assert mv._stufe_combo.zahl() == 0
        _waehle(mv._stufe_combo, STROBE)
        assert mv._current.priority == STROBE, "Arbeitskopie traegt die Stufe"
        assert mv._saved.priority == 0, "gespeichert wird erst beim Speichern"
        mv._save_edit()
        assert mv._saved.priority == STROBE
    finally:
        mv.deleteLater()


def test_matrix_editor_zieht_stufe_von_aussen_nach(fm):
    """Aendert die Ansicht „Prioritäten“ die Stufe der geoeffneten Matrix,
    darf das naechste Speichern sie nicht zuruecksetzen."""
    from src.ui.views.rgb_matrix_view import RgbMatrixView
    mv = RgbMatrixView()
    try:
        mv._add()
        mv._save_edit()
        setze_stufen([(mv._saved, NOTFALL)])
        assert mv._stufe_combo.zahl() == NOTFALL
        assert mv._current.priority == NOTFALL
        mv._param_change()
        mv._save_edit()
        assert mv._saved.priority == NOTFALL
    finally:
        mv.deleteLater()


def test_matrix_editor_zeigt_eigene_zahl_aus_alter_show(fm):
    from src.ui.views.rgb_matrix_view import RgbMatrixView
    mv = RgbMatrixView()
    try:
        mv._add()
        mv._saved.priority = 5
        mv._make_draft()
        mv._load_ui(mv._current)
        assert mv._stufe_combo.currentText() == "eigene Zahl (5)"
        mv._param_change()
        assert mv._current.priority == 5, "eigene Zahl bleibt erhalten"
    finally:
        mv.deleteLater()


def test_bewegungs_editor_stufe_statt_zahlenfeld(fm):
    from src.ui.views.efx_view import EfxView
    v = EfxView()
    try:
        _keine_layer_prioritaet(v)
        v._add_efx()
        efx = v._current
        assert efx is not None
        _waehle(v._stufe_combo, AKZENTE)
        assert efx.priority == AKZENTE
        setze_stufen([(efx, GRUNDLICHT)])
        assert v._stufe_combo.zahl() == GRUNDLICHT
        v._on_param_change()
        assert efx.priority == GRUNDLICHT, (
            "eine andere Parameter-Aenderung schreibt nicht die alte Stufe zurueck")
    finally:
        v.deleteLater()


def test_kein_layer_prioritaet_mehr_im_quelltext_der_editoren():
    for datei in ("src/ui/views/rgb_matrix_view.py", "src/ui/views/efx_view.py"):
        text = (REPO / datei).read_text(encoding="utf-8")
        assert '"Layer-Priorität:"' not in text, datei
        assert '"Stufe:"' in text, datei


# ── 20-mal umschalten im eigenen Prozess ─────────────────────────────────────

@pytest.mark.skipif(_ROLLE != "umschalten", reason="nur als Kindprozess")
def test_arbeiter():
    """Jeden Editor zeigen, 20-mal durch alle Stufen schalten, dazwischen
    rueckgaengig machen und von aussen aendern, dann abbauen."""
    app = _app()
    manager = get_function_manager()
    from src.ui.views.efx_view import EfxView
    from src.ui.views.rgb_matrix_view import RgbMatrixView
    zahlen = [s.zahl for s in stufen.STUFEN]
    runden = int(os.environ.get("ENG35_RUNDEN", "20"))

    gebunden = _editoren(manager)
    mv = RgbMatrixView()
    mv._add()
    ev = EfxView()
    ev._add_efx()
    lose = [("Matrix", mv), ("Bewegung", ev)]
    for _n, _f, ed in gebunden:
        ed.show()
    for _n, ed in lose:
        ed.show()
    app.processEvents()

    stapel = get_undo_stack()
    for runde in range(runden):
        for name, f, ed in gebunden:
            for z in zahlen:
                _waehle(ed._stufe_combo, z)
                assert f.priority == z, (name, z)
            stapel.undo()
            setze_stufen([(f, zahlen[runde % 5])])
            f.priority = 7                      # eigene Zahl von aussen
            stufen_melder().geaendert.emit(frozenset({f.id}))
            assert ed._stufe_combo.currentText() == "eigene Zahl (7)", name
        for name, ed in lose:
            for z in zahlen:
                _waehle(ed._stufe_combo, z)
                assert ed._current.priority == z, (name, z)
        app.processEvents()
        print(f"RUNDE {runde + 1}", flush=True)

    for _n, _f, ed in gebunden:
        ed.close()
        ed.deleteLater()
    for _n, ed in lose:
        ed.close()
        ed.deleteLater()
    del gebunden, lose, mv, ev
    for _ in range(3):
        app.processEvents()
        gc.collect()
    # Nach dem Abbau darf eine Meldung an die (toten) Felder nichts anrichten.
    stufen_melder().geaendert.emit(frozenset({1, 2, 3}))
    app.processEvents()
    print(_MARKE, flush=True)
    sys.stdout.flush()
    os._exit(0)


def _kind_umgebung(tmp_path, runden: int) -> dict:
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["ENG35_ARBEITER"] = "umschalten"
    env["ENG35_RUNDEN"] = str(runden)
    env["LIGHTOS_SHOW_DB"] = str(tmp_path / "show.db")
    env["LIGHTOS_CRASH_LOG"] = str(tmp_path / "crash.log")
    daten = tmp_path / "daten"
    daten.mkdir(exist_ok=True)
    env["XDG_DATA_HOME"] = str(daten)
    env["APPDATA"] = str(daten)
    env.pop("LIGHTOS_UNIVERSES_JSON", None)
    env.pop("LIGHTOS_SACN_CID", None)
    env.pop("PYTEST_CURRENT_TEST", None)
    return env


@pytest.mark.skipif(bool(_ROLLE), reason="Arbeiter-Lauf")
@pytest.mark.timeout(170)
def test_20_mal_umschalten_stuerzt_nicht_ab(tmp_path):
    import re
    fertig = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "-s",
         "-p", "no:cacheprovider", "-o", "addopts=",
         f"tests/{Path(__file__).name}::test_arbeiter"],
        cwd=str(REPO), env=_kind_umgebung(tmp_path, 20),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=150)
    aus = (fertig.stdout or "") + "\n" + (fertig.stderr or "")
    runden = len(re.findall(r"^RUNDE ", aus, flags=re.M))
    assert fertig.returncode == 0 and _MARKE in aus, (
        f"Kindprozess endete mit {fertig.returncode} nach {runden} von 20 "
        f"Runden — nativer Absturz oder Fehler:\n{aus[-3000:]}")
    assert runden == 20
