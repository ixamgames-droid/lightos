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
//  * Stufe `low`: immer absenken. `high`: nur, wenn die gemessene Frame-Zeit
//    ueber 18 ms liegt (Hysterese: erst unter 14 ms gilt sie wieder als
//    schnell). `max`: nie.
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
export const SLOW_FRAME_MS = 18;
export const FAST_FRAME_MS = 14;

export function createDynamicResolution({
  now, setTimer, clearTimer, applyScale, requestRender, mode = 'slow',
  scale = DYNRES_SCALE,
}) {
  let _mode = mode;
  let _scale = 1;
  let _lastMotion = -Infinity;
  let _prevMotion = -Infinity;
  let _timer = null;
  let _frameMs = 0;          // gleitender Mittelwert der Frame-Abstaende
  let _langsam = false;      // Hysterese-Zustand fuer 'slow'

  function erlaubt() {
    if (_mode === 'always') return true;
    if (_mode === 'never') return false;
    return _langsam;
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
      if (_frameMs > SLOW_FRAME_MS) _langsam = true;
      else if (_frameMs < FAST_FRAME_MS) _langsam = false;
    },
    setMode(m) {
      _mode = m;
      if (_mode === 'never' && _scale !== 1) { setzen(1); requestRender(); }
    },
    scale() { return _scale; },
    info() {
      return { scale: _scale, mode: _mode, frameMs: _frameMs, slow: _langsam };
    },
  };
}
