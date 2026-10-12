// VIZ-104: der BILLIGE Weg je Blitzwechsel — nur Helligkeiten setzen.
//
// Bis zur ersten Sichtprobe wendete der Takt bei jedem Wechsel den ganzen
// gemerkten DMX-Stand neu an (registry.js#updateFixtureDmx): Gobo, Farbe,
// Optik, Prisma, Pan/Tilt, Zielrechnung mit Weltmatrix und Koerper-Treffer,
// Icon — zweimal je Blitz und Geraet, im weichen Modus bis zu 32-mal je
// Sekunde. Noetig ist davon nichts: ein Blitz aendert allein die Helligkeit.
//
// Deshalb zwei Schritte:
//  * `hellMerken(f, dmx)` — NACH einer vollen Anwendung des Stands OHNE Strobe
//    (einmal je DMX-Update): liest die Helligkeitswerte ab, die der Handler
//    gesetzt hat (Deckkraft der Kegel, Leuchtstaerke der Linsen/Pixel,
//    Lichtstaerke des Parameter-Spots, Bodenfleck).
//  * `hellSetzen(f, fak, kopfFak)` — je Wechsel: schreibt diese Werte mal
//    Faktor zurueck. Zahlen an vorhandenen Objekten, sonst nichts: kein
//    Material entsteht, keine Textur wird angefasst, keine Matrix und keine
//    Zielrechnung laufen, die Shadow-Map bleibt (sie haengt an der Lage der
//    Lichter, nicht an ihrer Helligkeit), und der Spot-Pool verteilt nicht um
//    (scene/spot_pool.js haelt den Platz eines Strobes in der Dunkelphase).
//
// Sichtbarkeit laeuft ueber dieselben Fragen wie im Handler (beamsSichtbar,
// fleckSichtbar) — ein Blitz darf einen abgeschalteten Kegel nicht wieder
// einschalten und den Fleck eines Kopfes, der nichts trifft, nicht zeigen.
//
// Laser gehen NICHT ueber diesen Weg (`hellSchnell`): ihre Strahlen haengen an
// Muster und Eigenbewegung (fixtures/laser.js); fuer sie bleibt die volle
// Anwendung mit skalierter Helligkeit.
"use strict";

import { view } from '../state.js';
import { beamsSichtbar, fleckSichtbar } from './builders.js';
import { tintTopDownIcon } from './topdown_icons.js';

/** Kann dieses Geraet ueber den billigen Weg geschaltet werden? */
export function hellSchnell(f) {
  return !!f && !f.laserBeams && !f.laserRig;
}

// Was am Geraet Helligkeit traegt — einmal je Geraet aufgezaehlt (die Objekte
// stehen seit addFixture fest; gelesen wird immer `o.material`, damit ein vom
// Gobo getauschtes Material mitkommt).
//   art 'e' = emissiveIntensity, 'o' = opacity + Sichtbarkeit als Kegel
//   kopf    = Kopf-Index fuer den Shutter je Kopf, -1 = gehoert zum Ganzen
function _stellen(f) {
  const s = [];
  const e = (o, kopf) => { if (o && o.material) s.push({ o, art: 'e', kopf }); };
  const k = (o, kopf) => { if (o && o.material) s.push({ o, art: 'o', kopf }); };
  if (f.isSpider && f.bars) {
    f.bars.forEach((bar, i) => {
      (bar.lenses || []).forEach(l => e(l, i));
      (bar.beams || []).forEach(b => k(b, i));
    });
  } else if (f.isParBar && f.parHeads) {
    f.parHeads.forEach((ph, i) => { e(ph.lens, i); k(ph.beam, i); });
  } else if (f.isMoverBar && f.moverHeads) {
    f.moverHeads.forEach((mh, i) => { e(mh.lens, i); k(mh.beam, i); });
  } else if (f.isMatrix && f.pixels) {
    f.pixels.forEach((px, i) => e(px.mesh, i));
    (f.whites || []).forEach(w => e(w.mesh, -1));
  } else {
    k(f.beam, -1);
    e(f.lens, -1);
    e(f.lamp, -1);
    if (f.isPixelHead && f.ringPixels) f.ringPixels.forEach(seg => e(seg.mesh, -1));
  }
  return s;
}

/** Nach der vollen Anwendung des Stands OHNE Strobe: Helligkeiten ablesen. */
export function hellMerken(f, dmx) {
  const m = f._hell || (f._hell = { stellen: _stellen(f), basis: [], spot: 0,
                                    fleck: 0, fleckBasis: undefined, lum: 0 });
  const st = m.stellen;
  for (let i = 0; i < st.length; i++) {
    const mat = st[i].o.material;
    m.basis[i] = (st[i].art === 'e') ? mat.emissiveIntensity : mat.opacity;
  }
  m.spot = f.spot ? f.spot.intensity : 0;
  m.fleck = f.floorSpot ? f.floorSpot.material.opacity : 0;
  m.fleckBasis = f._fleckBasis;
  // Dasselbe Mass wie applyGenericColor (A3D-25/28): Dimmer mal hellste Farbe.
  const c = dmx && dmx.color;
  m.lum = (dmx && c) ? dmx.intNorm * Math.max(c.r, c.g, c.b) : 0;
  m.dmx = dmx || null;
}

function _iconFaerben(f, m, fak) {
  const d = m.dmx;
  if (!f.icon || !d) return;
  const rgb = { r: d.r, g: d.g, b: d.b };
  if (f.isPixelHead && f.ringPixels) {
    tintTopDownIcon(f.icon, rgb, d.intNorm * fak, (f.lastHeads || []).slice(f.pixelBase || 0));
  } else if ((f.isSpider && f.bars) || (f.isParBar && f.parHeads)
             || (f.isMoverBar && f.moverHeads) || (f.isMatrix && f.pixels)) {
    tintTopDownIcon(f.icon, rgb, d.intNorm * fak, f.lastHeads);
  } else {
    tintTopDownIcon(f.icon, d.color, d.intNorm * fak);
  }
}

/**
 * Je Wechsel: gemerkte Helligkeiten mal Faktor. `kopfFak` (Shutter je Kopf)
 * gilt nur fuer die Stellen eines Kopfes; dann bleibt das Ganze bei 1.
 */
export function hellSetzen(f, fak, kopfFak) {
  const m = f._hell;
  if (!m) return false;
  const st = m.stellen;
  const ganz = kopfFak ? 1 : fak;
  for (let i = 0; i < st.length; i++) {
    const s = st[i];
    let k = ganz;
    if (kopfFak && s.kopf >= 0) {
      const v = kopfFak[s.kopf < kopfFak.length ? s.kopf : 0];
      k = (v == null) ? 1 : v;
    }
    const wert = m.basis[i] * k;
    const mat = s.o.material;
    if (s.art === 'e') mat.emissiveIntensity = wert;
    else {
      mat.opacity = wert;
      // Einzelkegel: am Mass des Handlers (Dimmer mal Farbe); Kopf-Kegel an
      // ihrer Deckkraft — dieselbe Konvention wie resyncBeamVisibility.
      s.o.visible = beamsSichtbar(f, (s.o === f.beam) ? m.lum * k : wert);
    }
  }
  if (f.prismCones && f.beam) {
    // Die Nebenstrahlen teilen das Material des Hauptstrahls; nur ihre
    // Sichtbarkeit ist eigen (prism.js#syncPrismToBeam, ohne dessen Geometrie).
    for (const c of f.prismCones) c.visible = f.beam.visible;
  }
  if (f.spot) f.spot.intensity = m.spot * ganz;
  if (f.floorSpot) {
    f.floorSpot.material.opacity = m.fleck * ganz;
    // VIZ-96: der Spot-Pool fuehrt die Deckkraft des flachen Musters aus
    // dieser Basis nach; VIZ-98: applyFloorAim schaltet mit `_fleckHell` um.
    if (m.fleckBasis !== undefined) f._fleckBasis = m.fleckBasis * ganz;
    f._fleckHell = m.lum * ganz;
    f.floorSpot.visible = fleckSichtbar(f, m.lum * ganz);
  }
  // Das Icon ist nur im 2D-Plan zu sehen; im 3D bleibt es beim gemeldeten Stand.
  if (!kopfFak && view.mode === '2D') _iconFaerben(f, m, fak);
  return true;
}
