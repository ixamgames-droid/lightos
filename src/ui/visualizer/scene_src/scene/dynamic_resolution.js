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
//    Ein Frame zaehlt als verpasst ab 1,5 Intervallen. Langsam = gedaempfter
//    Anteil verpasster Frames > 30 %, schnell wieder < 10 %.
//  * Schaetzung des Bildschirmintervalls (VIZ-85): NICHT als Minimum. Chromium
//    liefert gelegentlich zwei rAF-Ticks dicht hintereinander (Windows,
//    29,97-Hz-Fernseher: 33,4 ms wurden zu 8 + 25 ms). Das Minimum fiel damit
//    auf 8-17 ms, jeder normale 33-ms-Frame galt als verpasst, und eine GPU,
//    die jeden Vsync schaffte, wurde "langsam". Jetzt:
//      1. Fenster der letzten VSYNC_WINDOW Abstaende.
//      2. Doppel-rAF zusammenfassen: ein Abstand unter SHORT_FACTOR x Median
//         wird mit dem naechsten addiert (8 + 25 = 33,4) — oder mit dem
//         vorigen, wenn das Paar zusammen einen Vsync ergibt (25 + 8).
//      3. Intervall = VSYNC_PERCENTILE-Perzentil der zusammengefassten Werte
//         (ein Ausreisser nach unten zieht es nicht mehr mit).
//      4. Abgleich mit der tatsaechlichen Renderrate: das Intervall ist
//         mindestens MEDIAN_FLOOR x Median. So zaehlt ein typischer Frame nie
//         als verpasst — wer gleichmaessig im Bildschirmtakt rendert (30, 50,
//         60, 144 Hz), ist nie "langsam".
//      5. Untergrenze VSYNC_MIN_MS (360-Hz-Bildschirme).
//    Grenze: der typische Frame (Median) definiert den Takt. Eine GPU, die
//    dauerhaft MEHR ALS DIE HAELFTE der Vsyncs verpasst, sieht deshalb aus wie
//    ein Bildschirm mit niedrigerem Takt und gilt als schnell — ohne die echte
//    Bildwiederholrate ist das nicht unterscheidbar, und der Fehler faellt zur
//    sicheren Seite (volle Aufloesung). Wechselnde Last, bei der bis knapp
//    die Haelfte der Frames verpasst wird, wird erkannt.
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
export const VSYNC_WINDOW = 48;        // VIZ-85: Abstaende im Schaetzfenster
export const VSYNC_MIN_SAMPLES = 6;    // vorher keine Bewertung
export const VSYNC_PERCENTILE = 0.2;   // unteres Quintil = Bildschirmtakt
export const SHORT_FACTOR = 0.6;       // kuerzer als 0,6 x Median = Doppel-rAF
export const PAIR_FACTOR = 1.25;       // Doppel-rAF-Paar ergibt hoechstens 1,25 x Median
export const MEDIAN_FLOOR = 0.75;      // Intervall >= 0,75 x Median
export const VSYNC_MIN_MS = 2.5;       // 400 Hz — kein Bildschirm ist schneller
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
  const _fenster = [];       // VIZ-85: rohe Abstaende (Ringpuffer)
  let _rest = 0;             // angefangener Doppel-rAF-Abstand
  let _letzter = 0;          // zuletzt bewerteter Abstand (Paar-Erkennung)
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

  // VIZ-85: robuste Schaetzung des Bildschirmintervalls (s. Kopf).
  function schaetzen() {
    if (_fenster.length < VSYNC_MIN_SAMPLES) return 0;
    const median = (werte) => {
      const v = werte.slice().sort((a, b) => a - b);
      const m = v.length >> 1;
      return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
    };
    const roh = median(_fenster);
    const zus = [];
    let rest = 0;
    for (const x of _fenster) {
      const summe = rest + x;
      if (summe < roh * SHORT_FACTOR) {
        // Kurzer Teil: gehoert er zum VORIGEN Abstand (erst lang, dann kurz:
        // 25 + 8), wird er dort angehaengt, sonst an den naechsten (8 + 25).
        const n = zus.length;
        if (!rest && n && zus[n - 1] + x <= roh * PAIR_FACTOR) zus[n - 1] += x;
        else rest = summe;
        continue;
      }
      zus.push(summe);
      rest = 0;
    }
    if (!zus.length) return Math.max(roh, VSYNC_MIN_MS);
    const sortiert = zus.slice().sort((a, b) => a - b);
    const idx = Math.min(sortiert.length - 1,
                         Math.floor(sortiert.length * VSYNC_PERCENTILE));
    const perz = sortiert[idx];
    return Math.max(perz, median(zus) * MEDIAN_FLOOR, VSYNC_MIN_MS);
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
      if (_scale !== 1) { _rest = 0; _letzter = 0; return; }  // abgesenkte Frames sagen nichts
      _frameMs = _frameMs ? (_frameMs * 0.8 + ms * 0.2) : ms;
      // VIZ-85: Fenster statt Minimum — folgt auch einem Monitorwechsel.
      _fenster.push(ms);
      if (_fenster.length > VSYNC_WINDOW) _fenster.shift();
      _vsyncMs = schaetzen();
      if (!_vsyncMs) return;                  // noch zu wenig gesehen
      // Doppel-rAF: der kurze Teil wird mit dem naechsten Abstand bewertet,
      // nicht als eigener (schneller) Frame.
      const abstand = _rest + ms;
      if (abstand < _vsyncMs * SHORT_FACTOR) {
        // Gehoert der kurze Teil zum eben bewerteten Abstand (erst lang, dann
        // kurz), ist das Paar schon gezaehlt — sonst mit dem naechsten werten.
        if (!_rest && _letzter && _letzter + ms <= _vsyncMs * PAIR_FACTOR) {
          _letzter = 0;
        } else {
          _rest = abstand;
        }
        return;
      }
      _rest = 0;
      _letzter = abstand;
      const verpasst = abstand > _vsyncMs * MISSED_FACTOR ? 1 : 0;
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
               missed: _verpasst, slow: langsam(), samples: _fenster.length };
    },
  };
}
