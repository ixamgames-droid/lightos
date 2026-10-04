"""VIZ-71: Lichtdaten schneller und schlanker zum Viewer (Python-Seite).

Bis VIZ-70 holte sich die Seite die DMX-Werte alle 130 ms per ``pollControl``
ab — im Mittel rund 100 ms Verzoegerung, schlimmstenfalls ueber 200 ms, und
jede Poll-Antwort schleppte die volle Geraeteliste mit (rund 18 KB, achtmal je
Sekunde). Jetzt schiebt der Service die Werte im Takt der Qualitaetsstufe per
``runJavaScript`` an die Seite, und der Poll liefert nur noch Geaendertes.

Alles hier laeuft ohne WebEngine: die Seite ist eine Attrappe, die die
``runJavaScript``-Aufrufe aufzeichnet und die Rueckrufe von Hand ausloest. Die
JS-Haelfte steht in ``test_viz71_apply_dmx_scene.py``.
"""
import json
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.visualizer.visualizer_service import (
    VisualizerService, VisualizerTarget, _build_fixture_payload,
)

_app = QApplication.instance() or QApplication([])


# ── Attrappen ────────────────────────────────────────────────────────────────
class _Universe:
    def __init__(self, werte=None):
        self.puffer = bytearray(512)
        for adr, v in (werte or {}).items():
            self.puffer[adr - 1] = v

    def get_channel(self, adr):
        return self.puffer[adr - 1]

    def get_all(self):
        return bytes(self.puffer)

    def set_channel(self, adr, v):
        self.puffer[adr - 1] = v


class _OutputManager:
    """Liefert den GESENDETEN Frame (nach Blackout/NOT-AUS-Masken)."""

    def __init__(self):
        self.frames = {}

    def get_display_frame(self, u):
        return self.frames.get(u)


_KANAELE = [("color_r", 1), ("color_g", 2), ("color_b", 3),
            ("intensity", 4), ("pan", 5), ("tilt", 6)]


def _kanaele():
    return [SimpleNamespace(attribute=a, channel_number=n, ranges=[])
            for a, n in _KANAELE]


def _fixture(fid, adresse):
    return SimpleNamespace(fid=fid, universe=1, address=adresse,
                           invert_pan=False, invert_tilt=False, swap_pan_tilt=False)


def _state(n=2, positions=True):
    fixtures = [_fixture(i + 1, 1 + i * 10) for i in range(n)]
    st = SimpleNamespace(
        universes={1: _Universe()},
        visualizer_positions={f.fid: (0.0, 6.0, 0.0) for f in fixtures} if positions else {},
        visualizer_docks={}, visualizer_rotations={}, live_view_positions={},
        output_manager=_OutputManager(),
        get_patched_fixtures=lambda: fixtures,
        _callbacks=[],
    )
    st.subscribe = st._callbacks.append
    st.unsubscribe = lambda cb: st._callbacks.remove(cb) if cb in st._callbacks else None
    st._fixtures = fixtures
    return st


class _KanalPatch:
    """``get_channels_for_patched`` fuer die Attrappen-Geraete umlenken."""

    def __enter__(self):
        import src.core.app_state as m
        self._m, self._orig = m, m.get_channels_for_patched
        m.get_channels_for_patched = lambda f: _kanaele()
        return self

    def __exit__(self, *a):
        self._m.get_channels_for_patched = self._orig


class _TestBasis(unittest.TestCase):
    def setUp(self):
        self._patch = _KanalPatch().__enter__()

    def tearDown(self):
        self._patch.__exit__()


# ── S1: der Service liefert strukturiert ─────────────────────────────────────
class ServiceStrukturiertTest(_TestBasis):
    def _ziel(self, svc, **kw):
        empfangen = []
        t = VisualizerTarget("t", lambda s: empfangen.append(("json", s)),
                             emit_payloads=lambda arr, full, seq:
                             empfangen.append((arr, full, seq)), **kw)
        svc.attach_target(t)
        svc.set_target_active(t, True)
        return t, empfangen

    def test_emit_payloads_bekommt_liste_full_und_seq(self):
        st = _state()
        svc = VisualizerService(st)
        _t, emp = self._ziel(svc)
        svc._tick()
        self.assertEqual(len(emp), 1)
        arr, full, seq = emp[0]
        self.assertIsInstance(arr, list)
        self.assertTrue(full, "erster Tick nach dem Andocken ist ein Vollbatch")
        self.assertEqual(sorted(p["fid"] for p in arr), [1, 2])
        st.universes[1].set_channel(1, 200)
        svc._tick()
        arr2, full2, seq2 = emp[1]
        self.assertFalse(full2)
        self.assertEqual([p["fid"] for p in arr2], [1], "nur das geaenderte Geraet")
        self.assertGreater(seq2, seq, "jeder gebaute Tick bekommt eine neue Nummer")

    def test_alter_weg_ohne_emit_payloads_bleibt(self):
        st = _state()
        svc = VisualizerService(st)
        empfangen = []
        t = VisualizerTarget("alt", empfangen.append)
        svc.attach_target(t)
        svc.set_target_active(t, True)
        svc._tick()
        self.assertEqual(len(empfangen), 1)
        self.assertEqual(len(json.loads(empfangen[0])), 2)

    def test_fehler_in_einem_ziel_bremst_das_andere_nicht(self):
        st = _state()
        svc = VisualizerService(st)

        def kaputt(arr, full, seq):
            raise RuntimeError("Seite weg")
        a = VisualizerTarget("a", lambda s: None, emit_payloads=kaputt)
        svc.attach_target(a)
        svc.set_target_active(a, True)
        _b, emp = self._ziel(svc)
        svc._tick()
        self.assertEqual(len(emp), 1, "Ziel b bekam seinen Batch trotz Fehler in a")
        self.assertTrue(a.needs_full, "das gestoerte Ziel wird beim naechsten Tick voll beliefert")

    def test_timer_folgt_dem_schnellsten_aktiven_ziel(self):
        st = _state()
        svc = VisualizerService(st)
        langsam, _ = self._ziel(svc, tick_ms=66)
        self.assertEqual(svc._timer.interval(), 66)
        schnell, _ = self._ziel(svc, tick_ms=22)
        self.assertEqual(svc._timer.interval(), 22)
        svc.set_target_active(schnell, False)
        self.assertEqual(svc._timer.interval(), 66, "inaktive Ziele zaehlen nicht")
        svc.set_target_tick_ms(langsam, 33)
        self.assertEqual(svc._timer.interval(), 33)
        svc.shutdown()


# ── S2: Push-Kanal je Seite ─────────────────────────────────────────────────
import re  # noqa: E402

from PySide6.QtCore import QObject, Signal  # noqa: E402

from src.ui.visualizer.dmx_push import DmxPushChannel, push_script  # noqa: E402


class _Seite(QObject):
    renderProcessTerminated = Signal(object, int)

    def __init__(self):
        super().__init__()
        self.aufrufe = []            # [(skript, rueckruf)]

    def runJavaScript(self, skript, rueckruf=None):
        self.aufrufe.append((skript, rueckruf))


class _View(QObject):
    loadStarted = Signal()

    def __init__(self):
        super().__init__()
        self.seite = _Seite()

    def page(self):
        return self.seite


def _zerlegen(skript):
    """Push-Skript -> (payloads, seq) — so, wie JS es sieht."""
    m = re.search(r"L\.applyDmx\((\[.*\]),(\[[^\]]*\]|-?\d+)\):-1", skript)
    assert m, skript
    return json.loads(m.group(1)), json.loads(m.group(2))


class _Uhr:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class _PushBasis(_TestBasis):
    def _aufbau(self, n=2, **kanal_kw):
        self.st = _state(n)
        self.svc = VisualizerService(self.st)
        self.view = _View()
        self.uhr = _Uhr()
        self.geplant = []
        self.poll_eintraege = []
        self.poll_geleert = []
        poll = SimpleNamespace(
            _poll_merge_entries=lambda e: self.poll_eintraege.extend(list(e)),
            _poll_clear_dmx=lambda: self.poll_geleert.append(True))
        self._poll = poll                  # Kanal haelt ihn nur schwach
        self.kanal = DmxPushChannel(
            self.view, on_need_full=lambda: self.svc.force_full_resync(self.ziel),
            poll=poll, clock=self.uhr,
            schedule=lambda ms, fn: self.geplant.append((ms, fn)), **kanal_kw)
        self.ziel = VisualizerTarget("fenster", lambda s: None,
                                     emit_payloads=self.kanal.push)
        self.svc.attach_target(self.ziel)
        self.svc.set_target_active(self.ziel, True)
        self.svc._timer.stop()             # Ticks treibt der Test selbst

    def _aufrufe(self):
        return self.view.seite.aufrufe

    def _antworten(self, r=1, i=-1):
        skript, cb = self._aufrufe()[i]
        cb(r)

    def _tick(self, dt=0.034):
        self.uhr.t += dt
        self.svc._tick()

    def tearDown(self):
        if getattr(self, "svc", None) is not None:
            self.svc.shutdown()
        super().tearDown()


class PushKanalTest(_PushBasis):
    # T1
    def test_geaenderter_dmx_geht_im_selben_tick_raus(self):
        self._aufbau()
        self._tick()
        self.assertEqual(len(self._aufrufe()), 1, "erster Tick: Vollbatch")
        self._antworten(2)
        self.st.universes[1].set_channel(1, 255)
        vorher = len(self._aufrufe())
        self._tick()
        self.assertEqual(len(self._aufrufe()), vorher + 1,
                         "geaendertes DMX muss im selben Tick per runJavaScript raus")
        arr, seq = _zerlegen(self._aufrufe()[-1][0])
        self.assertEqual([d["fid"] for d in arr], [1])
        self.assertEqual(arr[0]["r"], 255)

    # T2
    def test_unterwegs_wird_je_geraet_ganz_zusammengefuehrt(self):
        self._aufbau()
        self._tick()
        self._antworten(2)
        self.st.universes[1].set_channel(1, 10)
        self._tick()                       # Batch A unterwegs
        n_a = len(self._aufrufe())
        self.st.universes[1].set_channel(1, 20)
        self.st.universes[1].set_channel(11, 30)
        self._tick()
        self.st.universes[1].set_channel(1, 40)
        self._tick()
        self.assertEqual(len(self._aufrufe()), n_a, "zweiter Batch, obwohl einer unterwegs ist")
        self._antworten(1)                 # Rueckruf fuer A
        self.assertEqual(len(self._aufrufe()), n_a + 1, "nach dem Rueckruf genau EIN Batch")
        arr, seq = _zerlegen(self._aufrufe()[-1][0])
        werte = {d["fid"]: d["r"] for d in arr}
        self.assertEqual(werte, {1: 40, 2: 30}, "je Geraet der neueste ganze Eintrag")
        self.assertIsInstance(seq, list, "Eintraege aus verschiedenen Ticks -> Seq je Eintrag")
        self.assertEqual(len(seq), 2)

    def test_kopfzahl_faellt_heads_ueberlebt_nicht(self):
        """A3D-04-Regel im Push-Puffer: ganzer Eintrag, nie dict.update."""
        self._aufbau()
        mit = {"fid": 1, "r": 1, "heads": [{"r": 1}, {"r": 2}]}
        ohne = {"fid": 1, "r": 2}
        self.kanal.push([{"fid": 9}], True, 1)    # Batch unterwegs
        self.kanal.push([mit], False, 2)
        self.kanal.push([ohne], False, 3)
        self.uhr.t += 0.05
        self._antworten(1)
        arr, _seq = _zerlegen(self._aufrufe()[-1][0])
        self.assertEqual(arr, [ohne])

    def test_voller_batch_ersetzt_den_puffer(self):
        self._aufbau()
        self.kanal.push([{"fid": 9}], True, 1)
        self.kanal.push([{"fid": 5, "r": 1}], False, 2)
        self.kanal.push([{"fid": 1, "r": 7}], True, 3)
        self.uhr.t += 0.05
        self._antworten(1)
        arr, seq = _zerlegen(self._aufrufe()[-1][0])
        self.assertEqual(arr, [{"fid": 1, "r": 7}])
        self.assertEqual(seq, 3)

    # T3
    def test_minus_eins_fuehrt_zu_vollbatch(self):
        self._aufbau()
        self._tick()
        self._antworten(-1)                # Seite noch nicht bereit
        self.assertTrue(self.ziel.needs_full)
        self.assertFalse(self.kanal.confirmed)
        self._tick()
        arr, _ = _zerlegen(self._aufrufe()[-1][0])
        self.assertEqual(sorted(d["fid"] for d in arr), [1, 2], "voller Bestand nach -1")

    def test_kein_rueckruf_timeout_und_spaete_antwort_zaehlt_nicht(self):
        self._aufbau()
        self._tick()
        self._antworten(2)
        self.st.universes[1].set_channel(1, 99)
        self._tick()
        alt_cb = self._aufrufe()[-1][1]
        self.uhr.t += 0.6                  # > 500 ms ohne Rueckruf
        # der Waechter (geplant beim Senden) bemerkt den Verlust auch ohne Tick
        for _ms, fn in list(self.geplant):
            fn()
        self.assertTrue(self.ziel.needs_full)
        self.assertEqual(self.kanal.stats["timeouts"], 1)
        self._tick()
        n = len(self._aufrufe())
        alt_cb(1)                          # verspaetet: darf nichts ausloesen
        self.assertEqual(len(self._aufrufe()), n)
        self.assertIsNotNone(self.kanal._inflight, "neuer Batch bleibt unterwegs")

    def test_reload_setzt_zurueck(self):
        self._aufbau()
        self._tick()
        self._antworten(2)
        self.assertTrue(self.kanal.confirmed)
        self.st.universes[1].set_channel(1, 5)
        self._tick()
        alt_cb = self._aufrufe()[-1][1]
        self.view.loadStarted.emit()
        self.assertTrue(self.ziel.needs_full)
        self.assertFalse(self.kanal.confirmed, "nach Reload laeuft der Poll wieder mit")
        self.assertIsNone(self.kanal._inflight)
        alt_cb(1)
        self.assertFalse(self.kanal.confirmed, "Antwort der alten Seite zaehlt nicht")

    def test_poll_laeuft_bis_zur_bestaetigung_mit(self):
        self._aufbau()
        self._tick()
        self.assertEqual(sorted(d["fid"] for _s, d in self.poll_eintraege), [1, 2])
        self.assertTrue(all(s is not None for s, _d in self.poll_eintraege),
                        "Rueckfall-Eintraege tragen die Tick-Nummer")
        self._antworten(2)
        self.assertEqual(self.poll_geleert, [True], "Bestaetigung leert den Poll-Puffer")
        self.poll_eintraege.clear()
        self.st.universes[1].set_channel(1, 1)
        self._tick()
        self.assertEqual(self.poll_eintraege, [], "nach der Bestaetigung kein Poll-DMX mehr")

    def test_takt_der_stufe_wird_eingehalten(self):
        self._aufbau(min_interval_s=1.0 / 15)
        self._tick()
        self._antworten(2)
        self.st.universes[1].set_channel(1, 1)
        self._tick(dt=0.034)               # nur 34 ms seit dem letzten Senden
        n = len(self._aufrufe())
        self.assertEqual(n, 1, "Niedrig (15 Hz) sendet nicht alle 34 ms")
        self.assertTrue(self.geplant, "der Rest wartet auf einen Nachlauf")
        self.uhr.t += 0.04
        ms, fn = [g for g in self.geplant if g[0] < 500][-1]
        fn()
        self.assertEqual(len(self._aufrufe()), 2)

    def test_push_skript_ist_ascii_und_kompakt(self):
        skript = push_script([(7, {"fid": 1, "gobo": "Blume ä"})])
        skript.encode("ascii")
        self.assertIn(",7):-1", skript, "eine gemeinsame Seq als Zahl")
        self.assertNotIn(", ", skript)


# ── Waechter, die schon vor VIZ-71 gruen sein sollten (T7–T9) ─────────────────
class WaechterTest(_PushBasis):
    # T7
    def test_statisches_dmx_kostet_nichts(self):
        self._aufbau()
        self._tick()
        self._antworten(2)
        gebaut = []
        orig = self.svc._build_snapshot
        self.svc._build_snapshot = lambda: (gebaut.append(1), orig())[1]
        n0 = len(self._aufrufe())
        for _ in range(100):
            self._tick()
        self.assertEqual(len(self._aufrufe()), n0, "statisches DMX darf nichts senden")
        self.assertLessEqual(len(gebaut), 100 // VisualizerService.GATE_MAX_SKIPS + 1,
                             "nur das 1-s-Sicherheitsnetz darf bauen")

    # T8
    def test_gesendet_wird_der_display_frame_nie_der_rohpuffer(self):
        self._aufbau(n=1)
        roh = self.st.universes[1]
        for adr, v in ((1, 255), (2, 255), (3, 255), (4, 255)):
            roh.set_channel(adr, v)              # Rohpuffer: voll hell, weiss
        # Display-Frame nach Blackout-Keep/Ziel-Blackout/NOT-AUS: Farbe bleibt
        # (Keep-Maske), Dimmer zu.
        frame = bytearray(512)
        frame[0], frame[1], frame[2], frame[3] = 255, 0, 0, 0
        self.st.output_manager.frames[1] = bytes(frame)
        self._tick()
        arr, _ = _zerlegen(self._aufrufe()[-1][0])
        erwartet = _build_fixture_payload(
            self.st._fixtures[0],
            {"color_r": 255, "color_g": 0, "color_b": 0, "intensity": 0,
             "pan": 0, "tilt": 0}, _kanaele())
        self.assertEqual(arr[0], json.loads(json.dumps(erwartet)))
        self.assertEqual(arr[0]["intensity"], 0, "Rohpuffer-Helligkeit durchgerutscht")

    # T9
    def test_dimmer_aendert_nur_intensity(self):
        self._aufbau(n=1)
        for adr, v in ((1, 200), (2, 100), (3, 50), (4, 255)):
            self.st.universes[1].set_channel(adr, v)
        self._tick()
        self._antworten(1)
        vorher, _ = _zerlegen(self._aufrufe()[-1][0])
        self.st.universes[1].set_channel(4, 64)
        self._tick()
        nachher, _ = _zerlegen(self._aufrufe()[-1][0])
        geaendert = {k for k in nachher[0] if nachher[0][k] != vorher[0].get(k)}
        self.assertEqual(geaendert, {"intensity"},
                         "Farbe und Dimmer muessen getrennte Felder bleiben")


# ── S4: Resync bei Neubau und Show-Wechsel (T4) ──────────────────────────────
class ResyncTest(_TestBasis):
    def test_show_loaded_setzt_needs_full_fuer_alle_ziele(self):
        st = _state()
        svc = VisualizerService(st)
        ziele = []
        for name in ("fenster", "spiegel"):
            t = VisualizerTarget(name, lambda s: None,
                                 emit_payloads=lambda a, f, q: None)
            svc.attach_target(t)
            svc.set_target_active(t, True)
            ziele.append(t)
        svc._tick()
        self.assertFalse(any(t.needs_full for t in ziele))
        svc._on_state("show_loaded", None)
        self.assertTrue(all(t.needs_full for t in ziele),
                        "Show-Wechsel muss jedes Ziel voll beliefern")
        self.assertEqual(svc._last_payload, {})
        svc.shutdown()

    def test_request_fixtures_fordert_den_vollen_bestand_an(self):
        from src.core.app_state import get_state
        from src.core.show.show_file import reset_show
        import src.ui.visualizer.visualizer_window as VW
        reset_show()
        bridge = VW.VisualizerBridge(get_state())
        try:
            reihenfolge = []
            bridge.allFixtures.connect(lambda j: reihenfolge.append("liste"))
            bridge.full_resync_cb = lambda: reihenfolge.append("resync")
            bridge.requestFixtures()
            self.assertEqual(reihenfolge, ["liste", "resync"],
                             "nach dem Geraete-Neubau muss der volle DMX-Bestand folgen")
        finally:
            bridge.dispose()

    def test_build_fixture_list_liest_positionen_einmal(self):
        import src.ui.visualizer.visualizer_window as VW

        class _St:
            zugriffe = 0

            @property
            def visualizer_positions(self):
                _St.zugriffe += 1
                return {1: (0, 6, 0), 2: (1, 6, 0), 3: (2, 6, 0)}

            def get_patched_fixtures(self):
                return [SimpleNamespace(fid=i) for i in (1, 2, 3, 4)]
        fake = SimpleNamespace(
            _state=_St(),
            _fixture_to_dict=lambda f, positions=None: {"fid": f.fid, "pos": positions[f.fid]})
        liste = VW.VisualizerBridge._build_fixture_list(fake)
        self.assertEqual([d["fid"] for d in liste], [1, 2, 3])
        self.assertEqual(_St.zugriffe, 1, "visualizer_positions in der Schleife gelesen (O(n^2))")


if __name__ == "__main__":
    unittest.main()
