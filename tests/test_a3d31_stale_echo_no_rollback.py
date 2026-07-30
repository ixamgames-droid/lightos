"""A3D-31 — ein überholtes Stage-Echo rollt keine Transform mehr zurück.

``_on_stage_list_from_js`` prüfte ``is_stale`` nur im **Create**-Zweig. Der
Update-Zweig für bereits vorhandene Elemente wendete Position, Größe, Rotation
und Farbe aus dem Echo **unbedingt** an — der Docstring behauptete, das sei
„idempotent-harmlos".

Das stimmt aber nur, wenn der überholte Snapshot zufällig dieselben Werte trägt.
Trägt ein Echo mit älterem Token ALTE Werte für eine id, die inzwischen
verschoben/gedreht/umgefärbt wurde, dann schrieb der Update-Zweig sie ins
autoritative Modell, setzte ``_stage_dirty`` und pushte sie über
``_sync_stage_node_to_scene`` + ``_push_stage_rotation_to_children`` an JS und an
gedockte Fixtures weiter: ein **Rollback** statt eines No-op — bis in die
gespeicherte Bühne hinein.

Der Guard steht jetzt vor beiden Zweigen. Die Reparatur-Teile der Funktion
(Nachsenden fehlender Elemente, Pending-Gate) laufen davon unberührt weiter —
die kümmern sich darum, was JS fehlt, nicht darum, was Python glauben soll.
"""
import os
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _El:
    def __init__(self, sid, x=0.0, rot=0.0, color="#111111"):
        self.id, self.type, self.name = sid, "platform", ""
        self.x, self.y, self.z = x, 0.0, 0.0
        self.w, self.h, self.d = 1.0, 1.0, 1.0
        self.rotation, self.color = rot, color


class _Stage:
    def __init__(self, els):
        self.elements = list(els)

    def get(self, sid):
        return next((e for e in self.elements if e.id == sid), None)


def _item(sid, x, rot=0.0, color="#111111"):
    return {"id": sid, "type": "platform",
            "position": {"x": x, "y": 0.0, "z": 0.0},
            "size": {"x": 1.0, "y": 1.0, "z": 1.0},
            "rotation": rot, "color": color, "name": ""}


def _window(els):
    """Minimal-Objekt für die ECHTE, ungebundene Methode.

    Kein echtes Fenster: das zöge QtWebEngine hoch, und geprüft wird die
    Echo-Logik. (Und Hilfsmethoden auf ``self`` wären hier genau die Falle, die
    heute schon dreimal zugeschlagen hat — siehe Second Brain
    ``reference_lightos_trap_stub_state_attributes``.)"""
    w = types.SimpleNamespace()
    w._current_stage = _Stage(els)
    w._pending_stage_ids = None
    w._stage_dirty = False
    w._bridge = types.SimpleNamespace(
        push_add_stage_object_data=lambda el, **k: None)
    w.gepusht = []
    w._sync_stage_node_to_scene = lambda el: w.gepusht.append(("sync", el.id))
    w._push_stage_rotation_to_children = lambda el: w.gepusht.append(("rot", el.id))
    w._refresh_stage_tree = lambda: None
    w._update_status_counts = lambda: None
    # Der Schwanz der Funktion spiegelt das gewaehlte Element in die
    # Eigenschaften-Spinboxen. Ohne Auswahl faellt der ganze Block weg — genau
    # das wollen wir hier, geprueft wird die Echo-Logik davor.
    w._selected_stage_element = lambda: None
    return w


def _call(w, items, *, is_stale):
    from src.ui.visualizer.visualizer_window import VisualizerWindow as W
    W._on_stage_list_from_js(w, items, is_stale)


class UeberholtesEchoTests(unittest.TestCase):
    def test_stale_echo_rollt_position_nicht_zurueck(self):
        """★ Der Kern-Fall: Element steht bei x=7, ein überholtes Echo trägt
        noch x=1. Vorher landete die 1 im autoritativen Modell."""
        el = _El("truss-1", x=7.0)
        w = _window([el])
        _call(w, [_item("truss-1", x=1.0)], is_stale=True)
        self.assertEqual(el.x, 7.0, "ein ueberholtes Echo darf den autoritativen "
                                    "Zustand nicht zurueckrollen")

    def test_stale_echo_rollt_rotation_und_farbe_nicht_zurueck(self):
        el = _El("truss-1", rot=1.5, color="#ff0000")
        w = _window([el])
        _call(w, [_item("truss-1", x=0.0, rot=0.0, color="#111111")], is_stale=True)
        self.assertEqual((el.rotation, el.color), (1.5, "#ff0000"))

    def test_stale_echo_setzt_kein_stage_dirty(self):
        """Sonst behauptet der Editor „ungespeicherte Aenderungen", obwohl der
        Nutzer nichts getan hat — und ein Speichern schriebe den Rollback fest."""
        w = _window([_El("truss-1", x=7.0)])
        _call(w, [_item("truss-1", x=1.0)], is_stale=True)
        self.assertFalse(w._stage_dirty)

    def test_stale_echo_pusht_nichts_an_js_und_gedockte_fixtures(self):
        """`_push_stage_rotation_to_children` bewegt angedockte Scheinwerfer —
        ein Rollback wäre dort sofort sichtbar."""
        w = _window([_El("truss-1", x=7.0, rot=1.5)])
        _call(w, [_item("truss-1", x=1.0, rot=0.0)], is_stale=True)
        self.assertEqual(w.gepusht, [])

    def test_stale_echo_legt_weiterhin_nichts_neu_an(self):
        """Der Resurrection-Guard von vorher bleibt erhalten."""
        w = _window([])
        _call(w, [_item("neu-1", x=1.0)], is_stale=True)
        self.assertEqual(w._current_stage.elements, [])


class FrischesEchoTests(unittest.TestCase):
    """Gegenprobe: ohne `is_stale` muss weiterhin ALLES ankommen — sonst hätte
    der Fix das Drag-Ende mit kaputtgemacht."""

    def test_frisches_echo_uebernimmt_die_transform(self):
        el = _El("truss-1", x=7.0)
        w = _window([el])
        _call(w, [_item("truss-1", x=1.0, rot=0.5, color="#00ff00")], is_stale=False)
        self.assertEqual((el.x, el.rotation, el.color), (1.0, 0.5, "#00ff00"))
        self.assertTrue(w._stage_dirty)
        self.assertIn(("sync", "truss-1"), w.gepusht)
        self.assertIn(("rot", "truss-1"), w.gepusht)

    def test_frisches_echo_legt_neue_elemente_an(self):
        w = _window([])
        _call(w, [_item("neu-1", x=2.0)], is_stale=False)
        self.assertEqual([e.id for e in w._current_stage.elements], ["neu-1"])

    def test_frisches_echo_ohne_aenderung_pusht_nicht(self):
        """Unveränderte Werte dürfen keinen Kinder-Push auslösen."""
        el = _El("truss-1", x=7.0)
        w = _window([el])
        _call(w, [_item("truss-1", x=7.0)], is_stale=False)
        self.assertEqual(w.gepusht, [])
        self.assertFalse(w._stage_dirty)


if __name__ == "__main__":
    unittest.main()
