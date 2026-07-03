// VIZ-13 Schritt 3a-4: buildFixtureModel-Dispatcher (ehem. stage_scene.html:1502-1517).
// In 3a nur verschoben (Design-Dokument Abschnitt (a)) - Umbau zur
// FixtureType-Registry folgt in 3c (Abschnitt (e)).
import {
  buildMovingHead, buildSpider, buildPar, buildLedBar, buildStrobe,
  buildDimmer, buildScanner, buildSmoke, buildHazer, buildLaser,
} from './builders.js';

export function buildFixtureModel(type, opts) {
  opts = opts || {};
  switch (type) {
    case 'moving_head': return buildMovingHead();
    case 'spider':      return buildSpider(opts.mirror);
    case 'par':         return buildPar();
    case 'led_bar':     return buildLedBar();
    case 'strobe':      return buildStrobe();
    case 'dimmer':      return buildDimmer();
    case 'scanner':     return buildScanner();
    case 'smoke':       return buildSmoke();
    case 'hazer':       return buildHazer();
    case 'laser':       return buildLaser();
    default:            return buildPar();
  }
}
