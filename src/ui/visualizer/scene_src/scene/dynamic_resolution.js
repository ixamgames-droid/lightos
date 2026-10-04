// VIZ-71 (S6): dynamische Aufloesung bei Kamerabewegung.
//
// Waehrend die Kamera faehrt (Orbit, Zoom, Pinch), rendert die Szene mit
// abgesenkter Pixeldichte; 200 ms nach der letzten Bewegung kommt die volle
// zurueck — mit einem frischen Frame (`requestRender`), sonst bliebe das
// Standbild unscharf. Die Pixelzahl geht quadratisch in die Fragment-Last:
// Skala 0,65 heisst rund 42 % der Pixel.
//
// Regeln (Entwurf VIZ-71 + Qualitaetsstufen):
//  * Bewegung = mindestens 2 Kamera-Updates in 120 ms, die in verschiedenen
//    Frames liegen (>= 8 ms auseinander). Ein einzelner Preset-/Reset-Sprung
//    (der updateCamera + resizeOrtho im selben Task ruft) senkt nichts ab.
//  * Stufe `low`: immer absenken. `high`: nur, wenn die Grafikkarte Frames
//    verpasst (s. u.). `max`: nie.
//  * "Verpasst" ist relativ zum Bildschirmtakt, nicht absolut: gemessen wird
//    der Abstand zweier rAF-Frames, und der faellt bei Vsync nie unter das
//    Bildschirmintervall (60 Hz: 16,7 ms, 50 Hz: 20 ms, Fernzugriff: 33 ms).
//    Eine absolute 14-ms-Grenze war auf 60 Hz nie erreichbar — ein einziger
//    Ausreisser hielt Hoch dann bis zum Neuladen unscharf (Review VIZ-71 B1).
//    Das Intervall wird als (langsam nachgefuehrtes) Minimum geschaetzt; ein
//    Frame zaehlt als verpasst ab 1,5 Intervallen. Langsam = gedaempfter
//    Anteil verpasster Frames > 30 %, schnell wieder < 10 %.
//  * Die Einstufung "langsam" verfaellt nach 30 s ohne Bestaetigung: die
//    naechste Fahrt laeuft dann voll aufgeloest als Probe (abgesenkte Frames
//    werden nicht gemessen, sonst kaeme Hoch aus "langsam" nie heraus).
//  * Waehrend einer Bewegung wird die Skala nicht neu bewertet (die Frames
//    werden durch die Absenkung ja schneller — ohne Sperre flackerte es).
//  * `setPixelRatio` legt den Canvas-Puffer neu an: nur beim WECHSEL rufen.
//
// Rein: Uhr, Zeitgeber und Wirkungen werden hereingereicht — der Node-Test
// faehrt den Zustandsautomaten mit einer Fake-Uhr.
"use strict";

export const DYNRES_SCALE = 0.65;
export const MOTION_WINDOW_MS = 120;
export const MOTION_MIN_GAP_MS = 8;
export const REST_MS = 200;
export const MISSED_FACTOR = 1.5;      // Frame > 1,5 Intervalle = verpasst
export const SLOW_SHARE = 0.3;         // Anteil verpasst -> langsam
export const FAST_SHARE = 0.1;         // Anteil verpasst -> wieder schnell
export const SHARE_ALPHA = 0.1;        // Daempfung des Anteils
export const VSYNC_CREEP = 0.01;       // Nachfuehren der Intervall-Schaetzung
export const SLOW_EXPIRE_MS = 30000;   // "langsam" ohne Bestaetigung verfaellt

export function createDynamicResolution({
  now, setTimer, clearTimer, applyScale, requestRender, mode = 'slow',
  scale = DYNRES_SCALE,
}) {
  let _mode = mode;
  let _scale = 1;
  let _lastMotion = -Infinity;
  let _prevMotion = -Infinity;
  let _timer = null;
  let _frameMs = 0;          // gleitender Mittelwert (nur Info)
  let _vsyncMs = 0;          // geschaetztes Bildschirmintervall
  let _verpasst = 0;         // gedaempfter Anteil verpasster Frames
  let _langsam = false;      // Hysterese-Zustand fuer 'slow'
  let _bestaetigt = -Infinity;

  function langsam() {
    if (_langsam && now() - _bestaetigt > SLOW_EXPIRE_MS) {
      _langsam = false;
      _verpasst = 0;          // Probe misst frisch, nicht mit altem Anteil
    }
    return _langsam;
  }

  function erlaubt() {
    if (_mode === 'always') return true;
    if (_mode === 'never') return false;
    return langsam();
  }

  function setzen(s) {
    if (s === _scale) return;
    _scale = s;
    applyScale(s);
  }

  function ruhe() {
    _timer = null;
    const t = now();
    if (t - _lastMotion < REST_MS) {
      _timer = setTimer(ruhe, REST_MS - (t - _lastMotion));
      return;
    }
    if (_scale !== 1) {
      setzen(1);
      requestRender();       // scharfes Endbild
    }
  }

  return {
    noteCameraMotion() {
      const t = now();
      if (t - _lastMotion < MOTION_MIN_GAP_MS) return;   // selber Frame/Task
      _prevMotion = _lastMotion;
      _lastMotion = t;
      const bewegt = (t - _prevMotion) <= MOTION_WINDOW_MS;
      if (bewegt && _scale === 1 && erlaubt()) setzen(scale);
      if (_scale !== 1) {
        if (_timer !== null) clearTimer(_timer);
        _timer = setTimer(ruhe, REST_MS);
      }
    },
    // Abstand zwischen zwei gerenderten Frames (ms). Nur aufeinander
    // folgende Frames zaehlen — eine Pause (On-Demand-Render) ist keine
    // Frame-Zeit.
    noteFrameInterval(ms) {
      if (!(ms > 0) || ms > 100) return;
      if (_scale !== 1) return;               // abgesenkte Frames sagen nichts
      _frameMs = _frameMs ? (_frameMs * 0.8 + ms * 0.2) : ms;
      if (!_vsyncMs || ms < _vsyncMs) _vsyncMs = ms;
      else _vsyncMs += (ms - _vsyncMs) * VSYNC_CREEP;   // z. B. Monitorwechsel
      const verpasst = ms > _vsyncMs * MISSED_FACTOR ? 1 : 0;
      _verpasst = _verpasst * (1 - SHARE_ALPHA) + verpasst * SHARE_ALPHA;
      langsam();                                // ggf. verfallen lassen
      if (_verpasst > SLOW_SHARE) _langsam = true;
      else if (_verpasst < FAST_SHARE) _langsam = false;
      if (_langsam) _bestaetigt = now();
    },
    setMode(m) {
      _mode = m;
      if (_mode === 'never' && _scale !== 1) { setzen(1); requestRender(); }
    },
    scale() { return _scale; },
    info() {
      return { scale: _scale, mode: _mode, frameMs: _frameMs, vsyncMs: _vsyncMs,
               missed: _verpasst, slow: langsam() };
    },
  };
}
