// VIZ-13 3c: FixtureType-REGISTRY (Design-Dokument Abschnitt (e)) — pro Typ
// ein deklarativer Eintrag mit `build(opts)` (Teil 1, PR #185) und
// `updateDmx(f, dmx)` (Teil 2: Split des ehemaligen updateFixture-Monolithen,
// verhaltens-identisch). Das Design-Feld `dispose` folgt in einer eigenen
// Runde. Neue Typen deklarativ hier eintragen statt Code-Verzweigung.
//
// updateDmx-Vertrag: f = fixtures[fid]-Instanz, dmx = {r,g,b,intensity,pan,
// tilt,heads,color,intNorm,skipBeam} (gebaut in fixtures.js#updateFixture;
// Payload byte-identisch zum dmxBatch des VisualizerService).
import {
  buildMovingHead, buildSpider, buildPar, buildLedBar, buildStrobe,
  buildDimmer, buildScanner, buildSmoke, buildHazer, buildLaser, buildParBar, buildMoverBar,
  updateSpiderDmx, updateParBarDmx, updateMoverBarDmx, updateMovingHeadDmx, updateGenericDmx,
} from './builders.js';

const REGISTRY = {
  moving_head: { build: ()  => buildMovingHead(),                   updateDmx: updateMovingHeadDmx },
  spider:      { build: (o) => buildSpider(o.mirror),               updateDmx: updateSpiderDmx },
  par_bar:     { build: (o) => buildParBar(o.nHeads, o.pixelBar),   updateDmx: updateParBarDmx },   // FM-3 (+FM-8 Pixel-Variante)
  mover_bar:   { build: (o) => buildMoverBar(o.nHeads),             updateDmx: updateMoverBarDmx }, // FM-4
  par:         { build: ()  => buildPar(),                          updateDmx: updateGenericDmx },
  led_bar:     { build: ()  => buildLedBar(),                       updateDmx: updateGenericDmx },
  strobe:      { build: ()  => buildStrobe(),                       updateDmx: updateGenericDmx },
  dimmer:      { build: ()  => buildDimmer(),                       updateDmx: updateGenericDmx },
  scanner:     { build: ()  => buildScanner(),                      updateDmx: updateMovingHeadDmx }, // FM-1: Spiegel folgt Pan/Tilt
  // smoke/hazer BEWUSST generisch statt No-Op: ihr Indikator-Lamp (f.lamp)
  // und ihr 2D-Icon folgen im Monolith der DMX-Farbe — das bleibt erhalten.
  smoke:       { build: ()  => buildSmoke(),                        updateDmx: updateGenericDmx },
  hazer:       { build: ()  => buildHazer(),                        updateDmx: updateGenericDmx },
  laser:       { build: ()  => buildLaser(),                        updateDmx: updateGenericDmx },
};

// Unbekannter Typ -> PAR-Fallback (identisch zum alten switch-default).
export function buildFixtureModel(type, opts) {
  const entry = REGISTRY[type] || REGISTRY.par;
  return entry.build(opts || {});
}

// DMX-Dispatch pro Typ (ersetzt die if-Kette des updateFixture-Monolithen).
// Fallback wie beim build: unbekannter Typ -> PAR = generischer Single-Head-
// Pfad — exakt der Zweig, den der Monolith fuer solche Fixtures nahm.
export function updateFixtureDmx(f, dmx) {
  const entry = REGISTRY[f.type] || REGISTRY.par;
  entry.updateDmx(f, dmx);
}
