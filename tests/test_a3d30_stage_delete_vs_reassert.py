"""A3D-30 / A3D-12 — eine echte 3D-Löschung überlebt jetzt einen eingereihten
Reassert-Add.

**Der Fehler:** ``_on_stage_object_deleted_from_js`` verwarf eine Löschung,
sobald IRGENDEIN ``addStageData`` für dieselbe id in der Poll-Queue hing.
Gerechtfertigt war das nur mit Undo/Redo-Interleaving — aber genau dieselbe
Event-Form entsteht bei der **automatischen Wiederherstellung**: der
1200-ms-Reassert nach jedem Stage-Load und der ``<=3x``-Nachsende-Mechanismus
bei einem Teil-Snapshot füllen die Queue mit ``addStageData`` für JEDES Element.

Der Guard konnte beides nicht unterscheiden (kein Token). Folgen, beide still:
die Löschung erreichte das autoritative ``_current_stage`` nie, und das noch
eingereihte Add baute das Objekt in JS wieder auf — **das gelöschte
Bühnenobjekt kam zurück.**

Es gibt vier Sender von ``addStageData``; sie teilen sich sauber:

===============================================  ===================
``_reassert_current_stage_after_load`` (+1200ms)  automatisch
``_on_stage_list_from_js`` (<=3x Nachsenden)      automatisch
``_on_add_change`` (Nutzer legt an / Redo)        Nutzergeste
``_on_delete_change`` else-Zweig (Undo)           Nutzergeste
===============================================  ===================

Genau diese Unterscheidung trägt jetzt das Flag ``reassert`` in der Payload —
in der Payload, weil die JS-Seite es auch braucht (dort entscheidet es, ob der
Lösch-Tombstone ``_userRemovedIds`` respektiert wird, A3D-12).
"""
import json
import os
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _Bridge:
    """Nur die von den Guards berührte Oberfläche des echten Bridge-Objekts."""

    def __init__(self, events=None, reloading=False):
        self._poll_events = list(events or [])
        self._reloading_stage = reloading


def _add_event(sid, *, reassert=False):
    payload = {"id": sid, "type": "truss"}
    if reassert:
        payload["reassert"] = True
    return {"t": "addStageData", "j": json.dumps(payload)}


class _Stage:
    def __init__(self, ids):
        self._ids = list(ids)

    def get(self, sid):
        return types.SimpleNamespace(id=sid) if sid in self._ids else None

    def remove(self, sid):
        if sid in self._ids:
            self._ids.remove(sid)

    @property
    def ids(self):
        return list(self._ids)


def _window(stage_ids, bridge):
    """Ein Minimal-Objekt, auf dem die ECHTEN ungebundenen Methoden laufen.

    Bewusst kein echtes ``Visualizer3DWindow``: das zieht QtWebEngine hoch und
    machte den Test langsam und teardown-anfällig — geprüft werden soll die
    Guard-Logik, nicht der Fensterbau."""
    from src.ui.visualizer.visualizer_window import VisualizerWindow as W
    w = types.SimpleNamespace()
    w._bridge = bridge
    w._current_stage = _Stage(stage_ids)
    w._pending_stage_ids = None
    w._selected_stage_id = ""
    w._stage_dirty = False
    w._remove_stage_node_from_scene = lambda sid: None
    w._refresh_stage_tree = lambda: None
    w._update_status_counts = lambda: None
    w._delete = lambda sid: W._on_stage_object_deleted_from_js(w, sid)
    return w


class LoeschungVsReassertTests(unittest.TestCase):
    def test_reassert_add_darf_die_loeschung_nicht_ueberstimmen(self):
        """★ Der Kern-Fall: +1200ms-Reassert hängt in der Queue, der Nutzer
        löscht. Vorher wurde die Löschung verworfen und das Objekt kam zurück."""
        bridge = _Bridge([_add_event("truss-1", reassert=True)])
        w = _window(["truss-1", "truss-2"], bridge)
        w._delete("truss-1")
        self.assertEqual(w._current_stage.ids, ["truss-2"],
                         "die Loeschung muss das autoritative Modell erreichen")

    def test_reassert_add_wird_dabei_aus_der_queue_geworfen(self):
        """Sonst stellt der nächste Poll genau das wieder her, was gerade
        gelöscht wurde — und beim nächsten Mal merkt es der Guard nicht einmal,
        weil das Element dann gar nicht mehr in `_current_stage` steht."""
        bridge = _Bridge([_add_event("truss-1", reassert=True),
                          _add_event("truss-2", reassert=True),
                          {"t": "cameraReset"}])
        w = _window(["truss-1", "truss-2"], bridge)
        w._delete("truss-1")
        verbleibend = [json.loads(e["j"])["id"]
                       for e in bridge._poll_events if e.get("t") == "addStageData"]
        self.assertEqual(verbleibend, ["truss-2"])
        self.assertIn({"t": "cameraReset"}, bridge._poll_events,
                      "fremde Events duerfen nicht mit weggeraeumt werden")

    def test_echtes_undo_re_add_ueberstimmt_die_loeschung_weiterhin(self):
        """Das ursprüngliche Schutzziel bleibt: ein Lösch-Echo, das von einem
        bereits rückgängig gemachten Remove stammt, ist überholt."""
        bridge = _Bridge([_add_event("truss-1")])          # kein reassert
        w = _window(["truss-1"], bridge)
        w._delete("truss-1")
        self.assertEqual(w._current_stage.ids, ["truss-1"])
        self.assertEqual(len(bridge._poll_events), 1,
                         "bei verworfener Loeschung wird nichts aus der Queue "
                         "geraeumt")

    def test_gemischte_queue_der_nutzer_gewinnt(self):
        bridge = _Bridge([_add_event("truss-1", reassert=True),
                          _add_event("truss-1")])
        w = _window(["truss-1"], bridge)
        w._delete("truss-1")
        self.assertEqual(w._current_stage.ids, ["truss-1"])

    def test_ohne_queue_loescht_es_normal(self):
        bridge = _Bridge([])
        w = _window(["truss-1"], bridge)
        w._delete("truss-1")
        self.assertEqual(w._current_stage.ids, [])

    def test_waehrend_eines_reloads_wird_nichts_geloescht(self):
        bridge = _Bridge([], reloading=True)
        w = _window(["truss-1"], bridge)
        w._delete("truss-1")
        self.assertEqual(w._current_stage.ids, ["truss-1"])

    def test_kaputtes_json_in_der_queue_wirft_nicht(self):
        bridge = _Bridge([{"t": "addStageData", "j": "{kaputt"}])
        w = _window(["truss-1"], bridge)
        w._delete("truss-1")
        self.assertEqual(w._current_stage.ids, [])


class PayloadFlagTests(unittest.TestCase):
    """Das Flag muss in der Payload reisen — JS braucht es auch (A3D-12)."""

    def _emit(self, **kwargs):
        from src.ui.visualizer.visualizer_window import VisualizerBridge as B
        gesendet = []
        el = types.SimpleNamespace(
            to_js_dict=lambda: {"id": "truss-1", "type": "truss"})
        b = types.SimpleNamespace(
            addStageObjectData=types.SimpleNamespace(emit=gesendet.append))
        B.push_add_stage_object_data(b, el, **kwargs)
        return json.loads(gesendet[0])

    def test_normales_add_bleibt_byte_identisch(self):
        self.assertEqual(self._emit(), {"id": "truss-1", "type": "truss"},
                         "ohne reassert darf sich die Payload nicht aendern")

    def test_reassert_add_traegt_das_flag(self):
        self.assertTrue(self._emit(reassert=True).get("reassert"))


class GegenprobeTests(unittest.TestCase):
    """★ Zeigt, dass der ALTE Guard den Bug wirklich hatte — sonst belegt der
    Test oben nur, dass der neue Code tut was er tut."""

    def test_alter_guard_haette_die_loeschung_verworfen(self):
        bridge = _Bridge([_add_event("truss-1", reassert=True)])
        # Der alte Guard, wörtlich: jedes Add derselben id zaehlte.
        alt_verworfen = any(
            json.loads(ev.get("j") or "{}").get("id") == "truss-1"
            for ev in bridge._poll_events if ev.get("t") == "addStageData")
        self.assertTrue(alt_verworfen,
                        "der alte Guard haette hier abgebrochen — genau das war "
                        "der Bug")
        # Der neue unterscheidet.
        w = _window(["truss-1"], bridge)
        from src.ui.visualizer.visualizer_window import _queued_user_readd
        self.assertFalse(_queued_user_readd(bridge, "truss-1"))


if __name__ == "__main__":
    unittest.main()
