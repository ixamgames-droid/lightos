// VIZ-13 3c: FixtureType-REGISTRY (Design-Dokument Abschnitt (e)) — ersetzt den
// switch-Dispatcher aus 3a-4. Pro Typ ein Eintrag; heute nur `build(opts)`,
// die weiteren Design-Felder (`updateDmx` = Split des monolithischen
// updateFixture, `dispose`) ziehen in einer eigenen Folgerunde nach — der
// updateFixture-Split beruehrt ALLE Render-Pfade und ist bewusst separat
// mergebar. Neue Typen deklarativ hier eintragen statt Code-Verzweigung.
import {
  buildMovingHead, buildSpider, buildPar, buildLedBar, buildStrobe,
  buildDimmer, buildScanner, buildSmoke, buildHazer, buildLaser, buildParBar, buildMoverBar,
} from './builders.js';

const REGISTRY = {
  moving_head: { build: ()  => buildMovingHead() },
  spider:      { build: (o) => buildSpider(o.mirror) },
  par_bar:     { build: (o) => buildParBar(o.nHeads, o.pixelBar) },  // FM-3 (+FM-8 Pixel-Variante)
  mover_bar:   { build: (o) => buildMoverBar(o.nHeads) },            // FM-4
  par:         { build: ()  => buildPar() },
  led_bar:     { build: ()  => buildLedBar() },
  strobe:      { build: ()  => buildStrobe() },
  dimmer:      { build: ()  => buildDimmer() },
  scanner:     { build: ()  => buildScanner() },
  smoke:       { build: ()  => buildSmoke() },
  hazer:       { build: ()  => buildHazer() },
  laser:       { build: ()  => buildLaser() },
};

// Unbekannter Typ -> PAR-Fallback (identisch zum alten switch-default).
export function buildFixtureModel(type, opts) {
  const entry = REGISTRY[type] || REGISTRY.par;
  return entry.build(opts || {});
}
