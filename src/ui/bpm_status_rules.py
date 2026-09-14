"""Statuszeile der BPM-Erkennung (BPM-11, S6) — reine Regeln, kein Qt.

``status_line(cap_snap, det_snap, mgr_state, os2l_state, now)`` liefert GENAU EINE
``StatusLine`` (Problem — Ursache — Abhilfe, Schwere, optionale Aktion). Die Regeln
laufen in fester Reihenfolge; der erste Treffer gewinnt (Reihenfolge nach Schwere,
ui_diagnose 3.3: Ereignis > Audio nicht verfuegbar > Capture-Fehler > Kein Signal >
Clip > Brumm > Leise > Jitter > Zustandstext). Der Text ist NIE leer — auch der
Normalfall hat eine Zeile („Eingerastet — 128 BPM aus PC-Audio").

Die Messwerte kommen aus zwei unveraenderlichen Snapshots:
``CaptureSnapshot`` (src/core/audio/level_meter.py — Pegel, Clip, DC, Chunk-Abstand)
und ``DetectorSnapshot`` (src/core/audio/tempo_tracker.py — Zustand, Tempo,
Alternativ-Oktave, Brumm, Rueckstand). ``MgrState``/``Os2lState`` sammelt die View
aus Manager, SourceController, Capture und OS2L-Server.

``StatusHysterese`` verhindert Flackern: eine Stoerung (``stabil=True``) erscheint
erst nach ``AN_S`` (2 s) Anhalten und verschwindet erst nach ``AUS_S`` (3 s)
Abwesenheit. Zustandszeilen (Sucht, Eingerastet, Manuell …), Ereignisse und
Capture-Fehler wechseln sofort. ``chips()`` + ``ChipHysterese`` liefern die
Hinweis-Chips am Pegelmeter mit derselben Hysterese.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

# ── Schwellen (EIN Block) ────────────────────────────────────────────────────
# ALLE Werte sind Annahmen bis zur ersten echten Aufnahme vom Rig („Eingang 30 s
# aufnehmen"); danach hier nachziehen. Herkunft je Zeile.
KEIN_SIGNAL_DBFS = -60.0     # RMS 300 ms darunter = kein Signal (ui_diagnose F1)
LEISE_DBFS = -40.0           # RMS 1 s darunter = zu leise (plan.md S6 „−45/−40"; Meter grau ab −45)
BRUMM_RATIO = 0.4            # hum_ratio ab hier = BRUMM. Gemessen 2026-09-14 mit dem echten
                             # BeatDetector („Minimum ueber 5 Bloecke"), bpm_bench/signals.py, t > 3 s:
                             # (i) Kick 128 max 0,000 · (ii) Kick+Bass+Hats 128 max 0,000 ·
                             # (iii) Kick −30 dB + Brumm 50 Hz −30 dBFS (Bassband-SNR 0 dB) min 0,517 /
                             # Median 0,594 · (iv) reiner Brumm −30 dBFS 0,994. SNR +3 dB schwankt
                             # 0,18–0,61, SNR +10 dB 0,000. 0,4 liegt zwischen (i/ii) und min (iii).
                             # ABER: gehaltener tiefer Bass OHNE Kick (Breakdown, Sub-Drone 46–62 Hz)
                             # ergibt ebenfalls 0,75–0,99, und der Detektor faellt nach ~6 s Breakdown
                             # auf „searching". Deshalb gilt BRUMM nur mit ZWEI weiteren Bedingungen
                             # (_brumm_aktiv): Detektor NICHT eingerastet (ui_diagnose F2) UND
                             # CaptureSnapshot.netz_linie >= NETZ_LINIE_MIN.
NETZ_LINIE_MIN = 0.5         # Schaerfe der 50/60-Hz-Linie (level_meter.netz_linie, 4-s-Fenster). Gemessen
                             # 2026-09-14, bpm_bench/signals.py: Bass-Ton 46,2/49/51,9/55/58,3/61,7/98/110 Hz
                             # ≤ 0,089 · Kick 90/128/174 ≤ 0,222 · Kick+Bass+Hats ≤ 0,126 · Rauschen ≤ 0,21 ·
                             # Kick −30 dB + Brumm 50 Hz −40…−20 dBFS ≥ 0,991 · reiner Brumm 50,2 Hz 0,921,
                             # 49,6 Hz 0,501 (Netz driftet real ±0,1 Hz). Blind: Bass-Ton genau 50/60/100/120 Hz.
JITTER_CHUNK_MS = 70.0       # p95 der Chunk-Abstaende darueber (normal 21–43 ms, Briefing G4)
JITTER_BACKLOG_MS = 250.0    # Detektor-Rueckstand darueber
DC_MAX = 0.02                # |DC-Offset| darueber = Chip DC (Bank: +0,05 als Stoerfall)
HALBTEMPO_ALT_SCORE = 0.7    # alt_score ab hier = Doppel-/Halbtempo ist aehnlich plausibel
KEIN_TAKT_S = 15.0           # so lange Signal ohne Lock = „Kein Takt gefunden"
SUCHFENSTER_S = 6.0          # Fenster, das die Erkennung zum Einrasten braucht (MEM_S)
ZIEL_LO_DBFS = -30.0         # Pegel-Zielbereich im Ok-Text (wie level_meter.ZIEL_*)
ZIEL_HI_DBFS = -6.0
EREIGNIS_S = 3.0             # so lange zeigt die Zeile ein Ereignis (×2 ausserhalb Bereich)
EREIGNIS_AUFNAHME_S = 20.0   # „Aufnahme gespeichert — …" steht laenger (Dateiname abschreiben)
AN_S = 2.0                   # Hysterese: Stoerung erscheint nach so viel Anhalten
AUS_S = 3.0                  # Hysterese: Stoerung verschwindet nach so viel Abwesenheit

SCHWEREN = ("ok", "hinweis", "problem")
AKTIONEN = (None, "reconnect", "record", "range", "source")
CHIPS = ("CLIP", "BRUMM", "LEISE", "JITTER", "DC")
AUDIO_KINDS = ("loopback", "input")


@dataclass(frozen=True, slots=True)
class StatusLine:
    schwere: str                 # ok | hinweis | problem
    problem: str
    ursache: str
    abhilfe: str
    aktion: str | None = None    # None | reconnect | record | range | source
    key: str = ""                # Situation (fuer Hysterese/Tests)
    stabil: bool = False         # True = Stoerung mit Hysterese 2 s an / 3 s aus
    # Nur bei stabil: die Zeile, die OHNE Stoerungen gaelte (Zustandszeile). Die Hysterese
    # zeigt sie, solange die Stoerung noch nicht 2 s anhaelt (auch beim allerersten Update).
    basis: "StatusLine | None" = field(default=None, compare=False, repr=False)

    @property
    def text(self) -> str:
        return " — ".join(p for p in (self.problem, self.ursache, self.abhilfe) if p)


@dataclass(frozen=True, slots=True)
class MgrState:
    """Was die View ausser den Snapshots weiss (Manager, SourceController, Capture)."""
    kind: str | None = None                 # loopback | input | os2l | song | off
    device_label: str | None = None         # Anzeigename der Quelle (Geraet)
    manual: bool = False
    bpm: float = 0.0                        # Manager-Tempo
    locked: bool = False                    # Tempo eingefroren
    min_bpm: float = 60.0
    max_bpm: float = 200.0
    audio_available: bool = True            # soundcard/numpy vorhanden
    capture_error: str | None = None        # cap.last_error()
    sink_missing: str | None = None         # gespeicherter Sink fehlt -> Standardausgabe
    song_available: bool | None = None      # Lied-Analyse: analysierter Titel im Player?
    ereignis: StatusLine | None = None      # z. B. „×2 nicht moeglich"
    ereignis_bis: float = 0.0               # bis zu dieser Uhrzeit zeigen
    aufnahme_s: float | None = None         # laufende Aufnahme: Sekunden
    aufnahme_dauer_s: float = 30.0


@dataclass(frozen=True, slots=True)
class Os2lState:
    running: bool = False
    last_bpm: float = 0.0
    port: int | None = None


def _g(snap, name, default):
    if snap is None:
        return default
    v = getattr(snap, name, default)
    return default if v is None else v


def _quelle(m: MgrState) -> str:
    base = {"loopback": "PC-Audio", "input": "Eingang", "os2l": "OS2L",
            "song": "Lied-Analyse", "off": "Aus"}.get(m.kind or "", "—")
    if m.kind in AUDIO_KINDS and m.device_label:
        return f"{base} »{m.device_label}«"
    return base


def _db(v: float, fmt: str = ".0f") -> str:
    """dB-Wert mit echtem Minuszeichen (Anzeige), z. B. „−70"."""
    return format(float(v), fmt).replace("-", "\u2212")


def _bpm(v: float) -> str:
    return f"{float(v):.0f}" if abs(float(v) - round(float(v))) < 0.05 else f"{float(v):.1f}"


def ereignis_oktave(step: int, ziel_bpm: float, min_bpm: float, max_bpm: float,
                    now: float) -> tuple[StatusLine, float]:
    """Ereignis „×2/×½ nicht moeglich" (Ziel ausserhalb des Tempo-Bereichs) + Ablaufzeit."""
    knopf = "×2" if step > 0 else "×½"
    grenze = f"endet bei {_bpm(max_bpm)}" if step > 0 else f"beginnt bei {_bpm(min_bpm)}"
    line = StatusLine(
        "hinweis", f"{knopf} nicht möglich",
        f"{_bpm(ziel_bpm)} BPM liegt außerhalb des Tempo-Bereichs {_bpm(min_bpm)}–{_bpm(max_bpm)} "
        f"(Bereich {grenze})",
        "Tempo-Bereich in „Erweitert“ anpassen", "range", key="ereignis_oktave")
    return line, now + EREIGNIS_S


def ereignis_aufnahme(datei_rel: str, dauer_s: float, abgebrochen: bool,
                      now: float) -> tuple[StatusLine, float]:
    """Ereignis nach einer Aufnahme; ``datei_rel`` NUR relativ (audio_diag/<datei>.wav)."""
    if abgebrochen:
        line = StatusLine("hinweis", "Aufnahme abgebrochen",
                          f"{datei_rel} ({dauer_s:.0f} s)",
                          "Datei trotzdem an Robin/Support schicken", None, key="ereignis_aufnahme")
    else:
        line = StatusLine("ok", "Aufnahme gespeichert", datei_rel,
                          "Datei an Robin/Support schicken", None, key="ereignis_aufnahme")
    return line, now + EREIGNIS_AUFNAHME_S


def ereignis(problem: str, ursache: str, abhilfe: str = "", schwere: str = "hinweis",
             aktion: str | None = None, now: float = 0.0,
             dauer_s: float = EREIGNIS_S) -> tuple[StatusLine, float]:
    """Allgemeines kurzes Ereignis (z. B. „Aufnahme nicht möglich")."""
    return StatusLine(schwere, problem, ursache, abhilfe, aktion, key="ereignis"), now + dauer_s


# ── Regeln ───────────────────────────────────────────────────────────────────

def status_line(cap_snap, det_snap, mgr_state: MgrState | None, os2l_state: Os2lState | None,
                now: float) -> StatusLine:
    """Die EINE Statuszeile; erster Treffer gewinnt. Nie leerer Text."""
    m = mgr_state if mgr_state is not None else MgrState()
    o = os2l_state if os2l_state is not None else Os2lState()
    erste: StatusLine | None = None
    for rule in _RULES:
        line = rule(cap_snap, det_snap, m, o, now)
        if line is None:
            continue
        if not line.stabil:
            if erste is None:
                return line
            return replace(erste, basis=line)
        if erste is None:
            erste = line
    return replace(erste, basis=_fallback(m)) if erste is not None else _fallback(m)


def _r_ereignis(cap, det, m, o, now):
    if m.ereignis is not None and now < m.ereignis_bis:
        return m.ereignis
    return None


def _r_aufnahme(cap, det, m, o, now):
    if m.aufnahme_s is None:
        return None
    return StatusLine(
        "hinweis", "Aufnahme läuft",
        f"{int(m.aufnahme_s)} / {int(m.aufnahme_dauer_s)} s vom Eingang {_quelle(m)}",
        "Musik so laufen lassen wie im Problemfall", None, key="aufnahme")


def _r_audio_fehlt(cap, det, m, o, now):
    if m.kind in AUDIO_KINDS and not m.audio_available:
        return StatusLine(
            "problem", "Audio nicht verfügbar",
            "Paket soundcard oder numpy fehlt",
            "pip install soundcard numpy (INSTALL.md) — oder OS2L/Lied-Analyse wählen",
            "source", key="audio_fehlt")
    return None


def _r_monitor(cap, det, m, o, now):
    err = m.capture_error or ""
    if m.kind == "input" and "Monitor of" in err:
        return StatusLine(
            "problem", "Eingang nicht gefunden",
            "der Standard-Eingang ist ein Loopback-Gerät (Monitor), kein Eingang",
            "Eingang aus der Liste wählen", "source", key="monitor_als_eingang")
    return None


def _r_capture_fehler(cap, det, m, o, now):
    if m.kind not in AUDIO_KINDS or not m.capture_error:
        return None
    err = m.capture_error
    if "haengt" in err or "hängt" in err:
        return StatusLine(
            "problem", "Audio-Thread hängt",
            "Gerät wurde im Betrieb entfernt",
            "bis zum Neustart von LightOS nicht nutzbar — anderes Gerät wählen",
            "source", key="capture_haengt")
    return StatusLine(
        "problem", "Audio-Fehler", err,
        "Gerät prüfen/neu anstecken, dann erneut verbinden", "reconnect", key="capture_fehler")


def _r_capture_gestoppt(cap, det, m, o, now):
    if m.kind in AUDIO_KINDS and cap is not None and not bool(_g(cap, "running", False)):
        return StatusLine(
            "problem", "Audio gestoppt",
            f"{_quelle(m)} liefert keine Daten (Aufnahme läuft nicht)",
            "erneut verbinden", "reconnect", key="capture_gestoppt")
    return None


def _pausiert(det) -> bool:
    return _g(det, "state", "") == "locked" and int(_g(det, "hold_stage", 0)) in (1, 2)


def _r_kein_signal(cap, det, m, o, now):
    if m.kind not in AUDIO_KINDS or cap is None:
        return None
    rms = float(_g(cap, "rms_dbfs_300ms", -120.0))
    if rms >= KEIN_SIGNAL_DBFS or _pausiert(det):
        return None
    wert = "Stille (digital 0)" if rms <= -119.0 else f"{_db(rms)} dBFS"
    ursache = f"{_quelle(m)} liefert {wert}"
    if m.sink_missing:
        ursache += f"; gespeichertes Ausgabegerät »{m.sink_missing}« fehlt, Capture hört die Standardausgabe"
    if m.kind == "loopback":
        abhilfe = "läuft die Musik über dieses Ausgabegerät? Sonst anderes Gerät wählen"
    else:
        abhilfe = "Kabel/Gerät prüfen oder anderen Eingang wählen"
    return StatusLine("problem", "Kein Signal", ursache, abhilfe, "source",
                      key="kein_signal", stabil=True)


def _r_sink_fehlt(cap, det, m, o, now):
    if m.kind == "loopback" and m.sink_missing:
        return StatusLine(
            "hinweis", "Ausgabegerät nicht gefunden",
            f"gespeichertes Gerät »{m.sink_missing}« fehlt — Capture läuft auf der Standardausgabe",
            "Gerät anstecken oder in der Quelle-Liste ein vorhandenes wählen", "source",
            key="sink_fehlt")
    return None


def _r_clip(cap, det, m, o, now):
    if m.kind not in AUDIO_KINDS or cap is None or not bool(_g(cap, "clipping", False)):
        return None
    return StatusLine(
        "problem", "Übersteuert",
        f"Spitze {_db(_g(cap, 'peak_hold_dbfs', 0.0), '.1f')} dBFS, "
        f"{int(_g(cap, 'clip_samples_1s', 0))} Clip-Samples/s",
        f"Pegel am Mischpult/Interface senken (Ziel {_db(ZIEL_LO_DBFS)}…{_db(ZIEL_HI_DBFS)} dBFS)",
        None, key="clip", stabil=True)


def _brumm_aktiv(cap, det) -> bool:
    """BRUMM nur, wenn ALLE drei gelten: ``hum_ratio >= BRUMM_RATIO`` (Detektor),
    Detektor nicht eingerastet (F2 — eingerastet stoert der Brumm die Erkennung nicht)
    und die Energie liegt als scharfe Linie auf 50/60 Hz (``netz_linie >= NETZ_LINIE_MIN``).
    Ein gehaltener Bass im Breakdown hat hohen ``hum_ratio``, aber keine Netzlinie."""
    if det is None or cap is None or _g(det, "state", "no_signal") == "locked":
        return False
    if float(_g(cap, "netz_linie", 0.0)) < NETZ_LINIE_MIN:
        return False
    return float(_g(det, "hum_ratio", 0.0)) >= BRUMM_RATIO


def _r_brumm(cap, det, m, o, now):
    if m.kind not in AUDIO_KINDS or not _brumm_aktiv(cap, det):
        return None
    ratio = float(_g(det, "hum_ratio", 0.0))
    hz = int(_g(cap, "netz_hz", 0)) or int(_g(det, "hum_hz", 0)) or 50
    return StatusLine(
        "problem", f"Netzbrumm {hz} Hz",
        f"Brummanteil im Bassband {ratio * 100:.0f} % (Erkennung kippt ab ~50 %)",
        "Masseschleife: DI-Box/Ground-Lift, anderes Netzteil, symmetrisches Kabel — "
        "Aufnahme machen und schicken", "record", key="brumm", stabil=True)


def _r_leise(cap, det, m, o, now):
    if m.kind not in AUDIO_KINDS or cap is None:
        return None
    rms = float(_g(cap, "rms_dbfs_1s", -120.0))
    if not (KEIN_SIGNAL_DBFS <= rms < LEISE_DBFS):
        return None
    return StatusLine(
        "hinweis", "Pegel niedrig",
        f"Eingang liefert {_db(rms)} dBFS RMS, Ziel {_db(ZIEL_LO_DBFS)}…{_db(ZIEL_HI_DBFS)}",
        "Ausgangspegel am Mischpult bzw. Interface-Gain anheben; die Erkennung ist so störanfälliger",
        None, key="leise", stabil=True)


def _r_jitter(cap, det, m, o, now):
    if m.kind not in AUDIO_KINDS:
        return None
    p95 = float(_g(cap, "chunk_ms_p95", 0.0))
    back = float(_g(det, "backlog_ms", 0.0))
    if p95 <= JITTER_CHUNK_MS and back <= JITTER_BACKLOG_MS:
        return None
    wert = (f"Chunk-Abstand p95 {p95:.0f} ms (normal 21–43)" if p95 > JITTER_CHUNK_MS
            else f"Rückstand {back:.0f} ms")
    return StatusLine(
        "hinweis", "Audio kommt stoßweise (Aussetzer)", wert,
        "Rechner ausgelastet? Andere Programme schließen; Beats bleiben im Takt, kommen aber später",
        "record", key="jitter", stabil=True)


def _r_dc(cap, det, m, o, now):
    if m.kind not in AUDIO_KINDS:
        return None
    dc = float(_g(cap, "dc_offset", 0.0))
    if abs(dc) <= DC_MAX:
        return None
    return StatusLine(
        "hinweis", "Gleichspannungsversatz",
        f"DC-Offset {dc:+.3f} (Grenze ±{DC_MAX:.2f})",
        "Interface/Kabel prüfen (defekter Eingang, Phantomspeisung am Line-Eingang?)",
        "record", key="dc", stabil=True)


def _r_eingefroren(cap, det, m, o, now):
    if not m.locked:
        return None
    return StatusLine(
        "hinweis", "Eingefroren", f"{_bpm(m.bpm)} BPM, Quellen ändern das Tempo nicht",
        "„Tempo einfrieren“ in „Erweitert“ lösen", "range", key="eingefroren")


def _r_manuell(cap, det, m, o, now):
    if not m.manual:
        return None
    if float(m.bpm) <= 0:
        return StatusLine("ok", "Manuell", "Tempo aus", "TAP tippen oder Nudge", None,
                          key="manuell_aus")
    zusatz = ""
    if m.kind in AUDIO_KINDS and _g(det, "state", "") == "locked":
        zusatz = f"; Erkennung würde {_bpm(float(_g(det, 'bpm', 0.0)))} sagen"
    return StatusLine("ok", "Manuell", f"{_bpm(m.bpm)} BPM per Tap/Nudge{zusatz}",
                      "Auto setzt die Erkennung fort", None, key="manuell")


def _r_os2l(cap, det, m, o, now):
    if m.kind != "os2l":
        return None
    port = f" auf Port {o.port}" if o.port else ""
    if not o.running:
        return StatusLine("problem", "OS2L läuft nicht", f"Server nicht gestartet{port} (Port belegt?)",
                          "erneut verbinden", "reconnect", key="os2l_aus")
    if float(o.last_bpm or 0) <= 0:
        return StatusLine("hinweis", "OS2L wartet", f"Server läuft{port}, keine DJ-Software verbunden",
                          "in VirtualDJ OS2L aktivieren", None, key="os2l_wartet")
    return StatusLine("ok", "OS2L verbunden", f"{_bpm(o.last_bpm)} BPM von der DJ-Software",
                      "nichts zu tun", None, key="os2l_ok")


def _r_song(cap, det, m, o, now):
    if m.kind != "song":
        return None
    if m.song_available is False:
        return StatusLine("hinweis", "Lied-Analyse", "kein analysierter Titel im Player",
                          "im Tab „Generator“ bzw. Player einen Titel analysieren", None,
                          key="song_ohne_titel")
    return StatusLine("ok", "Lied-Analyse", f"{_bpm(m.bpm)} BPM aus dem Player-Titel" if m.bpm > 0
                      else "Tempo aus dem Player-Titel", "nichts zu tun", None, key="song_ok")


def _r_aus(cap, det, m, o, now):
    if m.kind in (None, "off"):
        return StatusLine("hinweis", "Erkennung aus", "keine Beat-Quelle gewählt",
                          "Quelle wählen", "source", key="aus")
    return None


def _r_halbtempo(cap, det, m, o, now):
    if m.kind not in AUDIO_KINDS or _g(det, "state", "") != "locked" or _pausiert(det):
        return None
    alt, score, bpm = float(_g(det, "alt_bpm", 0.0)), float(_g(det, "alt_score", 0.0)), float(_g(det, "bpm", 0.0))
    if alt <= 0 or bpm <= 0 or score < HALBTEMPO_ALT_SCORE:
        return None
    knopf = "×2" if alt > bpm else "×½"
    art = "Doppeltempo" if alt > bpm else "Halbtempo"
    im_bereich = m.min_bpm <= alt <= m.max_bpm
    return StatusLine(
        "hinweis", f"Eingerastet — {_bpm(bpm)} BPM",
        f"{art} {_bpm(alt)} ist ähnlich plausibel ({score:.2f})",
        (f"läuft das Licht {'zu langsam' if alt > bpm else 'zu schnell'}: {knopf} klicken" if im_bereich
         else f"{_bpm(alt)} liegt außerhalb des Tempo-Bereichs — Bereich anpassen"),
        None if im_bereich else "range", key="halbtempo", stabil=True)


def _r_pause(cap, det, m, o, now):
    if m.kind not in AUDIO_KINDS or not _pausiert(det):
        return None
    return StatusLine("ok", "Pause", f"Tempo {_bpm(float(_g(det, 'bpm', 0.0)))} gehalten, Beats laufen weiter",
                      "nichts zu tun", None, key="pause")


def _r_kein_takt(cap, det, m, o, now):
    if m.kind not in AUDIO_KINDS or _g(det, "state", "") != "searching":
        return None
    sig = float(_g(det, "signal_s", 0.0))
    if sig < KEIN_TAKT_S:
        return None
    rms = float(_g(cap, "rms_dbfs_1s", _g(det, "level_rms_dbfs", -100.0)))
    return StatusLine(
        "hinweis", "Kein Takt gefunden",
        f"Signal da ({_db(rms)} dBFS), aber kein stabiles Tempo seit {sig:.0f} s",
        "Musik ohne klaren Beat? TAP viermal tippen — oder Aufnahme machen und schicken",
        "record", key="kein_takt", stabil=True)


def _r_sucht(cap, det, m, o, now):
    if m.kind not in AUDIO_KINDS:
        return None
    if det is None:
        return StatusLine("hinweis", "Erkennung nicht verfügbar", "kein Detektor geladen",
                          "LightOS neu starten; Tempo per TAP", None, key="kein_detektor")
    st = _g(det, "state", "no_signal")
    if st == "locked":
        return None
    gefuellt = float(_g(det, "window_filled_s", 0.0))
    return StatusLine(
        "hinweis", "Sucht Tempo",
        f"{gefuellt:.0f} s Musik gehört, Fenster braucht ~{SUCHFENSTER_S:.0f} s",
        "warten; schneller: TAP im Takt tippen", None, key="sucht")


def _r_ok(cap, det, m, o, now):
    if m.kind not in AUDIO_KINDS or _g(det, "state", "") != "locked":
        return None
    bpm = float(_g(det, "bpm", 0.0)) or float(m.bpm)
    rms = float(_g(cap, "rms_dbfs_1s", -120.0))
    pegel = ("Pegel im Zielbereich" if ZIEL_LO_DBFS <= rms <= ZIEL_HI_DBFS
             else f"Pegel {_db(rms)} dBFS")
    return StatusLine("ok", f"Eingerastet — {_bpm(bpm)} BPM aus {_quelle(m)}", pegel, "", None,
                      key="ok")


def _fallback(m: MgrState) -> StatusLine:
    return StatusLine("hinweis", "Zustand unbekannt", f"Quelle {_quelle(m)}", "Quelle neu wählen",
                      "source", key="unbekannt")


_RULES = (
    _r_ereignis, _r_aufnahme, _r_audio_fehlt, _r_monitor, _r_capture_fehler, _r_capture_gestoppt,
    _r_kein_signal, _r_sink_fehlt, _r_clip, _r_brumm, _r_leise, _r_jitter, _r_dc,
    _r_os2l, _r_song, _r_aus, _r_eingefroren, _r_manuell,
    _r_halbtempo, _r_pause, _r_kein_takt, _r_sucht, _r_ok,
)


# ── Hysterese ────────────────────────────────────────────────────────────────

_RANG = {"ok": 0, "hinweis": 1, "problem": 2}
SOFORT_KEYS = ("ereignis", "aufnahme")   # Rueckmeldung auf einen Klick: nie verzoegert
# Zustandszeilen, die der Detektor von selbst (frameweise) wechselt. Sie verdraengen eine
# gehaltene Stoerung nur, wenn sie STRIKT schwerer sind — sonst loescht ein einzelner Frame
# „Sucht" ein gehaltenes LEISE. Alle anderen nicht stabilen Zeilen (Fehler, Quellenwechsel,
# Manuell, Eingefroren …) folgen einer Handlung oder einem Fehler und gelten ab gleicher Schwere.
ZUSTAND_KEYS = ("sucht", "ok", "pause", "kein_detektor")


class StatusHysterese:
    """Entprellt die Statuszeile. Eine Stoerung (``stabil``) erscheint erst nach
    ``an_s`` Anhalten und verschwindet erst nach ``aus_s`` Abwesenheit; alles
    andere wechselt sofort. Eine gehaltene Stoerung verdraengen: Zustandszeilen
    (``ZUSTAND_KEYS``) nur, wenn strikt schwerer; sonstige sofortige Zeilen ab gleicher
    Schwere; Ereignisse und die laufende Aufnahme (``SOFORT_KEYS``) immer. Solange eine
    Stoerung noch nicht ``an_s`` anhaelt, zeigt die Hysterese deren ``basis`` (die
    Zustandszeile darunter) — auch beim ersten Update. Uhr injizierbar."""

    def __init__(self, clock=None, an_s: float = AN_S, aus_s: float = AUS_S):
        import time
        self._clock = clock if clock is not None else time.monotonic
        self.an_s, self.aus_s = float(an_s), float(aus_s)
        self._shown: StatusLine | None = None
        self._shown_seen = 0.0
        self._cand_key: str | None = None
        self._cand_since = 0.0

    @property
    def shown(self) -> StatusLine | None:
        return self._shown

    def reset(self) -> None:
        self._shown = None
        self._cand_key = None

    def update(self, line: StatusLine, now: float | None = None) -> StatusLine:
        t = self._clock() if now is None else float(now)
        shown = self._shown
        if line.key.startswith(SOFORT_KEYS) or (shown is not None and line.key == shown.key):
            return self._zeige(line, t)
        if line.key != self._cand_key:
            self._cand_key, self._cand_since = line.key, t
        if line.stabil:
            reif = t - self._cand_since >= self.an_s
            if shown is None:
                if reif:
                    return self._zeige(line, t)
                return self._zeige_basis(line, t)
            weg = (not shown.stabil) or (t - self._shown_seen >= self.aus_s)
            if reif and (weg or _RANG[line.schwere] > _RANG[shown.schwere]):
                return self._zeige(line, t)
            if not shown.stabil or weg:
                self._zeige_basis(line, t)       # Zustandszeile darunter aktuell halten
            return self._shown  # type: ignore[return-value]
        if shown is None or not shown.stabil or t - self._shown_seen >= self.aus_s:
            return self._zeige(line, t)
        if line.key in ZUSTAND_KEYS:
            nimm = _RANG[line.schwere] > _RANG[shown.schwere]
        else:
            nimm = _RANG[line.schwere] >= _RANG[shown.schwere]
        if nimm:
            return self._zeige(line, t)
        return shown

    def _zeige(self, line: StatusLine, t: float) -> StatusLine:
        self._shown, self._shown_seen = line, t
        self._cand_key = None
        return line

    def _zeige_basis(self, line: StatusLine, t: float) -> StatusLine:
        """Stoerung ``line`` noch nicht reif: deren Basis zeigen, Kandidat behalten."""
        b = line.basis
        if b is not None:
            self._shown, self._shown_seen = b, t
        return self._shown if self._shown is not None else line


def chips(cap_snap, det_snap) -> set[str]:
    """Rohe Chip-Menge (ohne Hysterese) aus {CLIP, BRUMM, LEISE, JITTER, DC}."""
    out: set[str] = set()
    if cap_snap is not None:
        if bool(_g(cap_snap, "clipping", False)):
            out.add("CLIP")
        rms = float(_g(cap_snap, "rms_dbfs_1s", -120.0))
        if KEIN_SIGNAL_DBFS <= rms < LEISE_DBFS:
            out.add("LEISE")
        if float(_g(cap_snap, "chunk_ms_p95", 0.0)) > JITTER_CHUNK_MS:
            out.add("JITTER")
        if abs(float(_g(cap_snap, "dc_offset", 0.0))) > DC_MAX:
            out.add("DC")
    if _brumm_aktiv(cap_snap, det_snap):
        out.add("BRUMM")
    if det_snap is not None:
        if float(_g(det_snap, "backlog_ms", 0.0)) > JITTER_BACKLOG_MS:
            out.add("JITTER")
    return out


@dataclass
class ChipHysterese:
    """Je Chip: sichtbar nach ``an_s`` durchgehender Bedingung, weg nach ``aus_s`` ohne."""
    an_s: float = AN_S
    aus_s: float = AUS_S
    _an_seit: dict = field(default_factory=dict)
    _zuletzt: dict = field(default_factory=dict)
    _sichtbar: set = field(default_factory=set)

    def update(self, roh: set[str], now: float) -> set[str]:
        t = float(now)
        for c in CHIPS:
            if c in roh:
                self._an_seit.setdefault(c, t)
                self._zuletzt[c] = t
                if t - self._an_seit[c] >= self.an_s:
                    self._sichtbar.add(c)
            else:
                self._an_seit.pop(c, None)
                if c in self._sichtbar and t - self._zuletzt.get(c, t) >= self.aus_s:
                    self._sichtbar.discard(c)
        return set(self._sichtbar)

    def reset(self) -> None:
        self._an_seit.clear()
        self._zuletzt.clear()
        self._sichtbar.clear()


__all__ = ["StatusLine", "MgrState", "Os2lState", "status_line", "StatusHysterese", "chips",
           "ChipHysterese", "ereignis_oktave", "ereignis_aufnahme", "ereignis"]
