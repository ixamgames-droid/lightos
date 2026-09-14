"""BPM-07 (S2) + BPM-09 (S4): Persistenz der BPM-Einstellungen — Migration
v1→v2→v3 (byte-genau nach bpm_arbeit/plan.md Abschnitt 3; v3 verwirft
sensitivity/smoothing/subdivision mit Log, beat_latency_ms neu), Typpruefung je Key, unbekannte Keys weg,
Fremd-Sektionen bleiben, atomares Schreiben ohne .tmp-Reste, Abbruch laesst die
alte Datei intakt, neuere Dateiversion bleibt unangetastet, v1-Sicherung genau
einmal, unlesbare Datei wird vor dem Ueberschreiben als .corrupt.bak gesichert,
apply_to_backend je Key abgesichert, Auto-Start liest source/device/mode (device
nur fuer input — ein Loopback bekommt None), die 400-ms-Entprellung der View
(250 Ticks → 1 Schreibvorgang) und dass die View device nur fuer den Eingang
schreibt. Die View-Tests stubben AudioCapture.start: ein echter PulseAudio-Thread
im Testprozess endet mit SIGABRT beim Prozessende (Exit 134).
"""
from __future__ import annotations
import json
import os

import pytest

# ── Beispiel aus plan.md 3. (Hardstyle-Preset 145-160, sens 1,35, smooth 0,35) ──
V1_HARDSTYLE = {"auto_default": True, "mode_default": "auto", "min_bpm": 145, "max_bpm": 160,
                "sensitivity": 1.35, "smoothing": 0.35, "source_mode": "input",
                "input_device": "USB Audio CODEC Analog Stereo",
                "beats_per_bar": 4, "subdivision": 1, "phase_accurate_beats": True}
V2_HARDSTYLE = {"version": 2, "source": "input", "device": "USB Audio CODEC Analog Stereo",
                "mode": "auto", "min_bpm": 145, "max_bpm": 160, "beats_per_bar": 4,
                "phase_accurate_beats": True, "sensitivity": 1.35, "smoothing": 0.35,
                "subdivision": 1}
V3_HARDSTYLE = {"version": 3, "source": "input", "device": "USB Audio CODEC Analog Stereo",
                "mode": "auto", "min_bpm": 145, "max_bpm": 160, "beats_per_bar": 4,
                "phase_accurate_beats": True, "beat_latency_ms": 0}


@pytest.fixture
def bs(tmp_path, monkeypatch):
    from src.core.audio import bpm_settings as _bs
    monkeypatch.setattr(_bs, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(_bs, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))
    return _bs


def _write(bs, section, extra=None):
    data = dict(extra or {})
    data["bpm_settings"] = section
    with open(bs._PREFS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _read(bs):
    with open(bs._PREFS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _tmp_reste(bs):
    return [n for n in os.listdir(bs._PREFS_DIR) if n.endswith(".tmp")]


# ── Migration ──────────────────────────────────────────────────────────────────

def test_migrationsbeispiel_plan_byte_genau(bs, capsys):
    """plan.md 3.: v1 (Hardstyle) → v3 in einem Zug, mit dem v2->v3-Log."""
    got = bs.migrate(dict(V1_HARDSTYLE))
    assert got == V3_HARDSTYLE
    # byte-genau inkl. Schluesselreihenfolge (= DEFAULTS-Reihenfolge)
    assert json.dumps(got) == json.dumps(V3_HARDSTYLE)
    assert "v2->v3: verworfen sensitivity=1.35, smoothing=0.35, subdivision=1" in capsys.readouterr().out


def test_v2_hardstyle_wird_v3_und_verwirft_altschluessel(bs, capsys):
    """S4: die v2-Datei mit Hardstyle-Altschluesseln (plan.md 3. durchgespielt)."""
    got = bs.migrate(dict(V2_HARDSTYLE))
    assert got == V3_HARDSTYLE
    assert json.dumps(got) == json.dumps(V3_HARDSTYLE)
    out = capsys.readouterr().out
    assert "v2->v3: verworfen sensitivity=1.35, smoothing=0.35, subdivision=1" in out
    assert "unbekannter Key" not in out        # verworfen, nicht als „unbekannt" gemeldet
    # v3-Datei ohne Altschluessel: kein Log mehr
    bs.migrate(dict(V3_HARDSTYLE))
    assert "v2->v3" not in capsys.readouterr().out


def test_hardstyle_datei_wird_beim_laden_und_schreiben_v3(bs):
    _write(bs, V1_HARDSTYLE, {"live_view": {"zoom": 2}})
    s = bs.load_settings()
    assert s["min_bpm"] == 145 and s["max_bpm"] == 160 and s["source"] == "input"
    assert "sensitivity" not in s and s["beat_latency_ms"] == 0
    bs.save_settings(s)
    data = _read(bs)
    assert data["bpm_settings"] == V3_HARDSTYLE
    assert list(data["bpm_settings"].keys()) == list(V3_HARDSTYLE.keys())
    assert data["live_view"] == {"zoom": 2}    # Fremd-Sektion bleibt
    assert _tmp_reste(bs) == []


def test_v2_datei_wird_beim_schreiben_v3_ohne_neue_sicherung(bs):
    """Eine v2-Datei ist keine v1-Datei: kein .v1.bak; die Altschluessel fallen
    beim ersten Schreiben aus der Datei, alles andere bleibt."""
    _write(bs, V2_HARDSTYLE, {"live_view": {"zoom": 2}})
    bs.save_settings({"beat_latency_ms": -40})
    data = _read(bs)
    assert data["bpm_settings"] == {**V3_HARDSTYLE, "beat_latency_ms": -40}
    assert data["live_view"] == {"zoom": 2}
    assert not os.path.exists(bs._PREFS_PATH + ".v1.bak")


def test_auto_default_false_wird_source_off(bs):
    s = bs.migrate({"auto_default": False, "source_mode": "input", "input_device": "Mic"})
    assert s["source"] == "off" and s["device"] == "Mic"
    s = bs.migrate({"auto_default": False, "source_mode": "loopback", "input_device": "Mic"})
    assert s["source"] == "off" and s["device"] is None   # device nur bei input
    s = bs.migrate({"auto_default": True, "source_mode": "loopback", "input_device": "Mic"})
    assert s["source"] == "loopback" and s["device"] is None


def test_fehlende_datei_und_kaputtes_json_geben_defaults(bs):
    assert bs.load_settings() == bs.DEFAULTS
    with open(bs._PREFS_PATH, "w", encoding="utf-8") as f:
        f.write("{ kaputt")
    assert bs.load_settings() == bs.DEFAULTS


def test_typfehler_fallen_auf_default(bs):
    s = bs.migrate({"version": 3, "source": "radio", "device": 7, "mode": 5,
                    "min_bpm": "abc", "max_bpm": 150.5, "beats_per_bar": True,
                    "phase_accurate_beats": "ja", "beat_latency_ms": 301})
    assert s == bs.DEFAULTS
    s = bs.migrate({"version": 3, "beat_latency_ms": -301})
    assert s["beat_latency_ms"] == 0
    s = bs.migrate({"version": 3, "beat_latency_ms": 12.5})
    assert s["beat_latency_ms"] == 0
    # min >= max -> beide auf Default
    s = bs.migrate({"version": 3, "min_bpm": 180, "max_bpm": 120})
    assert s["min_bpm"] == 60 and s["max_bpm"] == 200
    # gueltige Werte bleiben, auch bei bool-aehnlichen Ints
    s = bs.migrate({"version": 3, "min_bpm": 20, "max_bpm": 400, "beats_per_bar": 32,
                    "beat_latency_ms": -300, "phase_accurate_beats": False})
    assert (s["min_bpm"], s["max_bpm"], s["beats_per_bar"]) == (20, 400, 32)
    assert s["beat_latency_ms"] == -300 and s["phase_accurate_beats"] is False


def test_unbekannte_keys_werden_verworfen(bs, capsys):
    _write(bs, {"version": 3, "foo": 1, "min_bpm": 100, "max_bpm": 150, "bar": "x"})
    s = bs.load_settings()
    assert "foo" not in s and "bar" not in s and s["min_bpm"] == 100
    out = capsys.readouterr().out
    assert "foo=1" in out and "bar='x'" in out        # Log je verworfenem Key
    bs.save_settings({"max_bpm": 160})
    sec = _read(bs)["bpm_settings"]
    assert "foo" not in sec and "bar" not in sec and sec["max_bpm"] == 160
    assert set(sec) == set(bs.DEFAULTS)


def test_teil_speichern_behaelt_dateistand_und_verwirft_ungueltiges(bs):
    _write(bs, V3_HARDSTYLE)
    bs.save_settings({"mode": "manual", "min_bpm": "kaputt"})
    sec = _read(bs)["bpm_settings"]
    assert sec["mode"] == "manual" and sec["min_bpm"] == 145 and sec["device"] == V3_HARDSTYLE["device"]


# ── Atomares Schreiben ─────────────────────────────────────────────────────────

def test_kein_tmp_nach_schreiben_und_replace_wird_genutzt(bs, monkeypatch):
    calls = []
    real = os.replace

    def spy(src, dst):
        calls.append((os.path.dirname(src) == os.path.dirname(dst), dst))
        return real(src, dst)
    monkeypatch.setattr(bs.os, "replace", spy)
    bs.save_settings({"min_bpm": 90})
    assert calls == [(True, bs._PREFS_PATH)]        # tmp im SELBEN Ordner
    assert _tmp_reste(bs) == []
    assert _read(bs)["bpm_settings"]["min_bpm"] == 90


def test_abbruch_mitten_im_schreiben_laesst_alte_datei_intakt(bs, monkeypatch):
    _write(bs, V3_HARDSTYLE, {"live_view": {"zoom": 2}})
    vorher = open(bs._PREFS_PATH, "rb").read()

    def boom(src, dst):
        raise OSError("Datentraeger weg")
    monkeypatch.setattr(bs.os, "replace", boom)
    bs.save_settings({"min_bpm": 90})               # loggt, wirft nicht
    assert open(bs._PREFS_PATH, "rb").read() == vorher
    assert _tmp_reste(bs) == []
    assert [n for n in os.listdir(bs._PREFS_DIR) if n.startswith(".ui_prefs-")] == []


# ── Versionen ──────────────────────────────────────────────────────────────────

def test_neuere_version_bleibt_unangetastet_und_liefert_defaults(bs):
    v4 = {"version": 4, "source": "input", "calibration": {}, "min_bpm": 100, "max_bpm": 150}
    _write(bs, v4, {"live_view": {"zoom": 2}})
    vorher = open(bs._PREFS_PATH, "rb").read()
    assert bs.load_settings() == bs.DEFAULTS
    bs.save_settings({"min_bpm": 90})
    assert open(bs._PREFS_PATH, "rb").read() == vorher
    assert not os.path.exists(bs._PREFS_PATH + ".v1.bak")


def test_v1_sicherung_genau_einmal(bs):
    bak = bs._PREFS_PATH + ".v1.bak"
    _write(bs, V1_HARDSTYLE, {"live_view": {"zoom": 2}})
    original = open(bs._PREFS_PATH, "rb").read()
    bs.save_settings({"min_bpm": 100})
    assert open(bak, "rb").read() == original
    assert _read(bs)["bpm_settings"]["version"] == 3
    bs.save_settings({"min_bpm": 110})              # zweites Schreiben: v3 -> keine neue Sicherung
    assert open(bak, "rb").read() == original
    _write(bs, V1_HARDSTYLE)                        # v1 erneut hingelegt: Sicherung bleibt die erste
    bs.save_settings({"min_bpm": 120})
    assert open(bak, "rb").read() == original
    assert len([n for n in os.listdir(bs._PREFS_DIR) if n.endswith(".v1.bak")]) == 1


def test_frische_v3_datei_legt_keine_sicherung_an(bs):
    bs.save_settings({"min_bpm": 100})
    bs.save_settings({"min_bpm": 110})
    assert not os.path.exists(bs._PREFS_PATH + ".v1.bak")
    assert _read(bs)["bpm_settings"]["version"] == 3


def test_unlesbare_datei_wird_vor_dem_ueberschreiben_gesichert(bs, capsys):
    """Halbe Datei eines anderen (nicht atomaren) Schreibers: load → Defaults,
    save darf sie nicht stillschweigend durch eine Nur-bpm_settings-Datei
    ersetzen — erst ui_prefs.json.corrupt.bak (einmalig), dann neu schreiben."""
    halb = '{"live_view": {"zoom": 2}, "bpm_settings": {"version": 3, "min_b'
    with open(bs._PREFS_PATH, "w", encoding="utf-8") as f:
        f.write(halb)
    bak = bs._PREFS_PATH + ".corrupt.bak"
    assert bs.load_settings() == bs.DEFAULTS        # kein Absturz, Defaults
    assert not os.path.exists(bak)                  # Lesen allein sichert nicht
    bs.save_settings({"min_bpm": 90})
    assert open(bak, encoding="utf-8").read() == halb   # byte-genau gesichert
    data = _read(bs)
    assert data["bpm_settings"]["min_bpm"] == 90 and data["bpm_settings"]["version"] == 3
    assert "corrupt" in capsys.readouterr().out     # Log nennt die Sicherung
    # Gueltiges JSON, aber kein Objekt: ebenfalls kaputt — die ERSTE Sicherung bleibt
    with open(bs._PREFS_PATH, "w", encoding="utf-8") as f:
        f.write("[1, 2]")
    bs.save_settings({"min_bpm": 95})
    assert open(bak, encoding="utf-8").read() == halb
    assert _read(bs)["bpm_settings"]["min_bpm"] == 95
    assert _tmp_reste(bs) == []


def test_fehlende_datei_und_datei_ohne_sektion_sichern_nichts(bs):
    bak = bs._PREFS_PATH + ".corrupt.bak"
    bs.save_settings({"min_bpm": 90})               # Datei fehlt: kein Kaputt-Fall
    assert not os.path.exists(bak)
    with open(bs._PREFS_PATH, "w", encoding="utf-8") as f:
        json.dump({"live_view": {"zoom": 2}}, f)    # gueltig, ohne bpm_settings
    bs.save_settings({"min_bpm": 90})
    data = _read(bs)
    assert data["live_view"] == {"zoom": 2} and data["bpm_settings"]["version"] == 3
    assert not os.path.exists(bak)

# ── apply_to_backend / start_auto_if_configured ────────────────────────────────

def test_apply_to_backend_ein_fehler_ueberspringt_nicht_den_rest(bs, monkeypatch):
    from src.core.engine.bpm_manager import get_bpm_manager, BpmMode
    from src.core.audio.beat_detector import get_beat_detector
    det, mgr = get_beat_detector(), get_bpm_manager()

    def boom(*_a, **_k):
        raise RuntimeError("Setter kaputt")
    monkeypatch.setattr(det, "set_beat_latency_ms", boom)
    monkeypatch.setattr(mgr, "set_bounds", boom)
    bs.apply_to_backend({"min_bpm": 110, "max_bpm": 150, "mode": "manual", "beats_per_bar": 8})
    assert mgr.mode == BpmMode.MANUAL and mgr.beats_per_bar == 8   # trotz zwei Fehlern davor
    mgr.set_mode(BpmMode.AUTO)
    mgr.set_beats_per_bar(4)


def test_apply_to_backend_setzt_beat_latenz_und_neutralisiert_unterteilung(bs):
    """v3: beat_latency_ms → Detektor; subdivision hat keinen Regler mehr → 1."""
    from src.core.engine.bpm_manager import get_bpm_manager
    from src.core.audio.beat_detector import get_beat_detector
    det, mgr = get_beat_detector(), get_bpm_manager()
    mgr.set_subdivision(4)
    bs.apply_to_backend({"beat_latency_ms": -40})
    assert det.beat_latency_ms == -40 and det.snapshot().beat_latency_ms == -40
    assert mgr.subdivision == 1
    bs.apply_to_backend({})
    assert det.beat_latency_ms == 0


def test_apply_to_backend_nimmt_defaults_fuer_fehlende_keys(bs):
    from src.core.engine.bpm_manager import get_bpm_manager
    mgr = get_bpm_manager()
    bs.apply_to_backend({})
    assert mgr.min_bpm == bs.DEFAULTS["min_bpm"] and mgr.max_bpm == bs.DEFAULTS["max_bpm"]
    assert mgr.beats_per_bar == bs.DEFAULTS["beats_per_bar"]


class _FakeCap:
    def __init__(self):
        self.calls = []

    def set_source_mode(self, mode, device=None):
        self.calls.append(("source", mode, device))


class _FakeMgr:
    def __init__(self):
        self.calls = []

    def use_audio_source(self, on):
        self.calls.append(("audio", on))

    def set_mode(self, mode):
        self.calls.append(("mode", mode))


@pytest.fixture
def fake_backend(monkeypatch):
    import src.core.audio.capture as cap_mod
    import src.core.engine.bpm_manager as mgr_mod
    cap, mgr = _FakeCap(), _FakeMgr()
    monkeypatch.setattr(cap_mod, "get_audio_capture", lambda: cap)
    monkeypatch.setattr(mgr_mod, "get_bpm_manager", lambda: mgr)
    monkeypatch.delenv("LIGHTOS_NO_AUDIO_AUTOSTART", raising=False)
    return cap, mgr


def test_start_auto_gate_bleibt(bs, fake_backend, monkeypatch):
    cap, mgr = fake_backend
    monkeypatch.setenv("LIGHTOS_NO_AUDIO_AUTOSTART", "1")
    assert bs.start_auto_if_configured({"source": "input"}) is False
    assert cap.calls == [] and mgr.calls == []


def test_start_auto_liest_source_device_mode(bs, fake_backend):
    cap, mgr = fake_backend
    ok = bs.start_auto_if_configured({"source": "input", "device": "USB Audio CODEC Analog Stereo",
                                      "mode": "manual"})
    assert ok is True
    assert cap.calls == [("source", "input", "USB Audio CODEC Analog Stereo")]
    # Capture haengt an der Quelle, der Modus am Manager: MANUAL ueberlebt use_audio_source
    assert mgr.calls == [("audio", True), ("mode", "manual")]


def test_start_auto_off_und_song_starten_nichts(bs, fake_backend):
    cap, mgr = fake_backend
    assert bs.start_auto_if_configured({"source": "off"}) is False
    assert bs.start_auto_if_configured({"source": "song"}) is False
    assert cap.calls == [] and mgr.calls == []


def test_start_auto_loopback_nimmt_kein_eingangsgeraet(bs, fake_backend):
    """Ein gespeicherter Mikrofonname darf den Loopback nicht aufs Mikrofon lenken
    (capture.py loest den Namen mit include_loopback=True auf): PC-Audio startet
    wie beim Live-Wechsel im Tab ohne Geraet; der Sink-Name kommt mit S5."""
    cap, mgr = fake_backend
    assert bs.start_auto_if_configured({"source": "loopback", "device": "Line Out"}) is True
    assert cap.calls == [("source", "loopback", None)]


# ── View: Entprellung ──────────────────────────────────────────────────────────

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def save_counter(bs, monkeypatch):
    calls = []
    real = bs.save_settings
    monkeypatch.setattr(bs, "save_settings", lambda s: (calls.append(dict(s)), real(s)))
    return calls


@pytest.fixture(autouse=True)
def _kein_echtes_capture(monkeypatch):
    """Ein Quellenwechsel in der View startet den echten Capture
    (_on_source_changed → mgr.use_audio_source(True) → cap.start()); der
    PulseAudio-Thread ueberlebt bis zum Prozessende und stirbt dort mit SIGABRT
    (Exit 134 — das segmentierte Gate wertet den Exit-Code). start() ist hier
    ein No-op; danach Quelle und Manager zuruecksetzen."""
    import src.core.audio.capture as cap_mod
    from src.core.engine.bpm_manager import get_bpm_manager
    starts = []

    def _no_start(self):
        starts.append(self.source_mode)
        return False
    monkeypatch.setattr(cap_mod.AudioCapture, "start", _no_start)
    cap, mgr = cap_mod.get_audio_capture(), get_bpm_manager()
    yield starts
    mgr.use_audio_source(False)
    cap.set_source_mode("loopback")
    assert not cap.is_running()


def test_view_250_ticks_ergeben_einen_schreibvorgang(qapp, bs, save_counter):
    from PySide6.QtTest import QTest
    from src.ui.views.bpm_manager_view import BpmManagerView
    v = BpmManagerView()
    v.show()
    qapp.processEvents()
    assert save_counter == []                        # Init schreibt nichts
    for _ in range(250):
        v._save()
    qapp.processEvents()
    assert len(save_counter) == 0                    # noch nichts: Timer laeuft
    QTest.qWait(700)
    assert len(save_counter) == 1                    # genau EIN Schreibvorgang
    assert _tmp_reste(bs) == []
    assert save_counter[0]["source"] == "loopback" and "mode" in save_counter[0]
    v.hide()
    v.deleteLater()
    qapp.processEvents()


def test_view_flush_schreibt_sofort_und_stoppt_timer(qapp, bs, save_counter):
    from PySide6.QtTest import QTest
    from src.ui.views.bpm_manager_view import BpmManagerView
    v = BpmManagerView()
    v.show()
    qapp.processEvents()
    assert v.flush_pending_save() is False           # nichts ausstehend
    for _ in range(250):
        v._save()
    assert v.flush_pending_save() is True
    assert len(save_counter) == 1
    QTest.qWait(700)
    assert len(save_counter) == 1                    # Timer gestoppt: kein zweites Mal
    # Sliderzug -> hideEvent schreibt Ausstehendes sofort
    v._sp_min.setValue(90)
    assert len(save_counter) == 1
    v.hide()
    assert len(save_counter) == 2
    assert save_counter[-1]["min_bpm"] == 90
    assert bs.load_settings()["min_bpm"] == 90
    v.deleteLater()
    qapp.processEvents()


def test_view_liest_backend_statt_datei(qapp, bs):
    """boot() hat die Datei angewandt; die View nimmt Manager/Detektor als Stand."""
    from src.core.engine.bpm_manager import get_bpm_manager
    from src.ui.views.bpm_manager_view import BpmManagerView
    _write(bs, {"version": 2, "min_bpm": 70, "max_bpm": 150, "beats_per_bar": 3,
                "source": "input", "device": "Nicht vorhanden"})
    mgr = get_bpm_manager()
    mgr.set_bounds(100, 180)
    mgr.set_beats_per_bar(8)
    v = BpmManagerView()
    v.show()
    qapp.processEvents()
    assert (v._sp_min.value(), v._sp_max.value(), v._sp_bpb.value()) == (100, 180, 8)
    assert v._rb_input.isChecked()                   # Quelle aus den Prefs
    assert v._source_pref == "input"
    v.hide()
    v.deleteLater()
    qapp.processEvents()
    mgr.set_bounds(60, 200)
    mgr.set_beats_per_bar(4)


def test_view_source_off_ueberlebt_fremde_saves(qapp, bs, save_counter):
    """Alt-Datei mit auto_default=false → source off; ein Grenzen-Save darf das
    nicht auf loopback kippen, erst ein Klick auf die Quelle."""
    from src.ui.views.bpm_manager_view import BpmManagerView
    _write(bs, {"auto_default": False, "source_mode": "loopback"})
    v = BpmManagerView()
    v.show()
    qapp.processEvents()
    assert v._source_pref == "off"
    v._sp_min.setValue(90)
    v.flush_pending_save()
    assert save_counter[-1]["source"] == "off"
    v._rb_input.setChecked(True)                     # Nutzer waehlt die Quelle selbst
    v.flush_pending_save()
    assert save_counter[-1]["source"] == "input"
    v.hide()
    v.deleteLater()
    qapp.processEvents()


def test_view_schreibt_geraet_nur_fuer_eingang(qapp, bs, save_counter, monkeypatch,
                                               _kein_echtes_capture):
    """PC-Audio darf keinen Mikrofonnamen als device speichern: die Combo listet
    nur Eingaenge, und start_auto wuerde den Namen mit include_loopback=True
    aufloesen — nach dem Neustart naehme PC-Audio das Mikrofon auf. Live-Wechsel
    und Neustart muessen dieselbe Quelle/dasselbe Geraet ergeben."""
    import src.core.audio.capture as cap_mod
    from src.ui.views.bpm_manager_view import BpmManagerView
    monkeypatch.setattr(cap_mod.AudioCapture, "list_input_devices",
                        staticmethod(lambda: ["USB Audio CODEC Analog Stereo"]))
    cap = cap_mod.get_audio_capture()
    v = BpmManagerView()
    v.show()
    qapp.processEvents()
    v._rb_input.setChecked(True)
    v.flush_pending_save()
    assert (save_counter[-1]["source"], save_counter[-1]["device"]) == \
        ("input", "USB Audio CODEC Analog Stereo")
    v._rb_loop.setChecked(True)
    v.flush_pending_save()
    assert (save_counter[-1]["source"], save_counter[-1]["device"]) == ("loopback", None)
    assert (cap.source_mode, cap._device_name) == ("loopback", None)   # Live-Wechsel
    assert _kein_echtes_capture[-1] == "loopback" and not cap.is_running()   # nur der Stub lief
    # Neustart mit dieser Datei: derselbe Zustand wie nach dem Live-Wechsel
    monkeypatch.delenv("LIGHTOS_NO_AUDIO_AUTOSTART", raising=False)
    assert bs.load_settings()["device"] is None
    assert bs.start_auto_if_configured(bs.load_settings()) is True
    assert (cap.source_mode, cap._device_name) == ("loopback", None)
    v.hide()
    v.deleteLater()
    qapp.processEvents()
