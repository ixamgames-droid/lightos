// VIZ-69: Shadow-Maps nur neu zeichnen, wenn sich ihre Eingangsgroessen
// aendern — nicht in jedem Frame.
//
// Gemessen (Bierpong-Show, 24 Spots, Intel UHD 630): der Schatten-Durchlauf
// ist der groesste Einzelposten eines Frames (rund 30 %, s. Docstring von
// tools/viz_render_benchmark.py). three.js zeichnet ihn mit
// `shadowMap.autoUpdate = true` bei JEDEM render() neu — auch beim reinen
// Kamera-Orbit und bei reinen Farb-/Dimmer-Aenderungen. Eine Shadow-Map
// haengt aber nur an der LAGE der Lichter und der schattenwerfenden Objekte:
//
//   * Kamera          -> NEIN (die Map wird aus Sicht des LICHTS gerendert)
//   * Farbe/Intensitaet -> NEIN (auch nicht der Sprung 0 -> hell: die Map
//                        speichert Tiefe, keine Helligkeit)
//   * Pan/Tilt, Fixture-Transform, Stage-CRUD/Docking, Zoom (Spot-Winkel =
//     FOV der Schattenkamera), Sichtbarkeit von Schattenwerfern -> JA
//
// ★ Warum eine Signatur statt Dirty-Hooks an jeder dieser Stellen: die Liste
// oben verteilt sich auf ein gutes Dutzend Pfade (dmxBatch, Gizmo-Drag,
// Bridge-Transforms, Align/Distribute/Arrange, Docking, Stage-Resize,
// 2D/3D-Umschaltung, Optik, Raum-Huelle, ...). Ein vergessener Hook waere ein
// STILLER Fehler — der Schatten bliebe stehen, waehrend der Kopf schwenkt,
// und kein Test faellt um. Die Signatur liest stattdessen genau das, was
// three.js im Schatten-Durchlauf selbst liest (Weltmatrizen der sichtbaren
// Schattenwerfer + Schattenkamera-Parameter der Lichter) und kann deshalb
// keinen Pfad vergessen. Kosten: ein traverseVisible + Vergleich von rund
// 20 Zahlen je Schattenwerfer — gegenueber einem Schatten-Durchlauf
// (8 Lichter x ganze Szene) vernachlaessigbar.
//
// requestShadowUpdate() bleibt als expliziter Notausgang fuer Aenderungen,
// die keine Matrix beruehren (z.B. eine ausgetauschte Geometrie mit gleicher
// id waere einer) — und als Test-/Benchmark-Seam.
import { renderer, scene } from './renderer.js';

renderer.shadowMap.autoUpdate = false;
renderer.shadowMap.needsUpdate = true;   // erster Frame zeichnet immer

let _erzwungen = true;
let _sig = new Float64Array(1024);
let _sigLaenge = -1;                     // -1 = noch nie gemessen
let _neubauten = 0;                      // Messbarkeit (Tests/Abnahme)

export function requestShadowUpdate() { _erzwungen = true; }

/** Nur fuer Tests: wie oft wurde die Shadow-Map seit Start neu gezeichnet? */
export function shadowUpdateStats() {
  return { neubauten: _neubauten, autoUpdate: renderer.shadowMap.autoUpdate };
}

let _schreib = 0;
let _geaendert = false;
function _push(v) {
  if (_schreib >= _sig.length) {
    const neu = new Float64Array(_sig.length * 2);
    neu.set(_sig);
    _sig = neu;
  }
  if (!_geaendert && (_schreib >= _sigLaenge || _sig[_schreib] !== v)) _geaendert = true;
  _sig[_schreib++] = v;
}

function _pushMatrix(m) {
  const e = m.elements;
  for (let i = 0; i < 16; i += 1) _push(e[i]);
}

function _besuche(o) {
  if (!o.castShadow) return;
  _push(o.id);
  _pushMatrix(o.matrixWorld);
  if (o.isLight) {
    // Schattenkamera des SpotLights (three r128 SpotLightShadow.updateMatrices):
    // fov aus angle (+focus), far aus distance, Blickrichtung aus dem Target.
    _push(o.angle || 0);
    _push(o.distance || 0);
    if (o.target) _pushMatrix(o.target.matrixWorld);
    if (o.shadow) {
      _push(o.shadow.mapSize.x);
      _push(o.shadow.mapSize.y);
      _push(o.shadow.focus || 0);
    }
  } else {
    _push(o.geometry ? o.geometry.id : -1);
    _push(o.material && !Array.isArray(o.material) ? o.material.id : -1);
  }
}

// Vor JEDEM renderer.render() der App aufrufen (app.js-Render-Closure).
// Aktualisiert die Weltmatrizen selbst — der Aufrufer kann scene.autoUpdate
// fuer den folgenden render() deshalb abschalten (doppelte Traversierung
// gespart). Liefert true, wenn die Shadow-Map in diesem Frame neu entsteht.
export function prepareShadowMap() {
  scene.updateMatrixWorld();
  _schreib = 0;
  _geaendert = false;
  scene.traverseVisible(_besuche);
  if (_schreib !== _sigLaenge) _geaendert = true;
  _sigLaenge = _schreib;
  const neu = _geaendert || _erzwungen;
  _erzwungen = false;
  if (neu) {
    renderer.shadowMap.needsUpdate = true;
    _neubauten += 1;
  }
  return neu;
}
