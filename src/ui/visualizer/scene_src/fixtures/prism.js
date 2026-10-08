// VIZ-PRISMA-3D (David-Wunsch 2026-07-16): aus EINEM Strahl werden mehrere.
//
// Abgrenzung zu VIZ-MH-OPTICS: Fokus/Frost waren Kantenschaerfe und damit EINE
// Zahl (`spot.penumbra`), Zoom/Iris eine Skalierung. Prisma ist eine andere
// Klasse Arbeit — es braucht zusaetzliche Kegel, also Geometrie statt eines
// Materialwerts, und Geometrie kostet im 44-Hz-Pfad wirklich etwas.
//
// ── Wie die Kosten klein bleiben ────────────────────────────────────────────
//
// Drei Entscheidungen, alle aus derselben Sorge:
//
// 1. **Geteilte Geometrie UND geteiltes Material.** Jeder Prisma-Kegel ist ein
//    `THREE.Mesh` auf EXAKT der Geometrie und dem Material des Hauptstrahls.
//    Damit kostet ein Prisma keine einzige Allokation pro Frame, und — fast
//    wichtiger — Farbe und Deckkraft stimmen automatisch: `applyGenericColor`
//    schreibt sie in JEDEM Frame ins Material, und die Kegel haengen an
//    demselben Objekt. Zwei Materialien waeren zwei Wahrheiten.
//
//    ⚠️ DIE FALLE, DIE DARAUS FOLGT: beim Aufraeumen darf hier NIEMALS
//    `geometry.dispose()`/`material.dispose()` laufen — das wuerde dem
//    Hauptstrahl unter den Fuessen weggezogen. Aufraeumen heisst hier
//    ausschliesslich: aus dem Elternknoten entfernen.
//
// 2. **Faul gebaut, sofort abgeraeumt.** Ein Prisma ist im Normalfall AUS
//    (Default 0 in 4/4 eingebauten Profilen mit Prisma-Kanal). Solange es aus
//    ist, existiert kein einziger zusaetzlicher Kegel. Die Frage aus dem
//    Backlog-Item — "wie viele zusaetzliche Kegel vertraegt die Szene bei 48
//    Fixtures?" — entschaerft sich damit von selbst: die Last entsteht nur an
//    den Geraeten, an denen gerade wirklich ein Prisma steckt.
//
// 3. **Deckel auf schwachen GPUs.** Auf der Low-Spec-Stufe (VIZ-LOWSPEC:
//    fill-rate-limitierte Chips) sind hoechstens 3 Facetten erlaubt. Ein
//    8-fach-Prisma auf jedem Mover waere sonst das Achtfache der
//    Beam-Geometrie — und braeche genau auf den Geraeten ein, fuer die das
//    Dunkel-Culling ueberhaupt gebaut wurde.
//
// ── Was gezeigt wird ────────────────────────────────────────────────────────
//
// Der Hauptstrahl bleibt stehen und bekommt (n-1) geneigte Kopien im Kreis um
// sich. Ein echtes n-Facetten-Prisma wirft die Strahlen streng genommen als
// Ring OHNE Mitte; die Mitte zu behalten ist die deutlich weniger invasive
// Variante — Bodenfleck, SpotLight und die gesamte Optik-Kette (Zoom, Iris,
// Fokus, Frost) haengen am Hauptstrahl und bleiben unangetastet.
import * as THREE from '../three/three.js';
import { isLowSpec } from '../scene/renderer.js';

// Faecherwinkel relativ zum Kegelwinkel: 1,25 setzt die Nachbarstrahlen knapp
// neben den Hauptstrahl — sie ueberlappen noch leicht, wie bei einem echten
// Prisma, statt als getrennte Speichen auseinanderzufallen.
const NEIGUNG_FAKTOR = 1.25;
// Nur fuer Geraete ohne SpotLight (dort fehlt baseSpotAngle als Massstab).
const NEIGUNG_FALLBACK = Math.PI / 10 * 1.2;
export const PRISMA_MAX_LOWSPEC = 3;
export const PRISMA_MAX = 12;

/** Facettenzahl aus dem Payload auf das begrenzen, was gezeichnet wird.
 *
 *  Rein und ohne Szene — der Test rechnet damit Zahlen nach, statt eine
 *  laufende Seite zu befragen. `0`/`1` heissen "kein Prisma": ein einzelner
 *  Strahl IST der Hauptstrahl, da gibt es nichts zu ergaenzen.
 */
export function prismFacetCount(roh, lowSpec = isLowSpec) {
  const n = Math.floor(Number(roh));
  if (!isFinite(n) || n <= 1) return 0;
  return Math.min(n, lowSpec ? PRISMA_MAX_LOWSPEC : PRISMA_MAX);
}

// VIZ-80: abgeraeumt wird nur noch das EINHAENGEN, nicht der Bestand. Bis
// VIZ-80 kamen die Prisma-Werte im Betrieb gar nicht an; seither schaltet ein
// Prisma-Chaser (an/aus, 3er/6er im Wechsel) die Kegel mit DMX-Takt — ein
// Neubau je Wechsel waere Allokation im 44-Hz-Pfad. Die Gelenke bleiben am
// Fixture (`f.prismPool`) und werden beim naechsten Einschalten nur neu
// ausgerichtet; ueberzaehlige werden unsichtbar geschaltet.
function _raeumePrisma(f) {
  if (!f.prismGroup) return;
  // KEIN dispose: Geometrie und Material gehoeren dem Hauptstrahl (s. oben).
  if (f.prismGroup.parent) f.prismGroup.parent.remove(f.prismGroup);
  f.prismGroup = null;
  f.prismCones = null;
  f.prismFacetten = 0;
}

function _bauePrisma(f, n) {
  const beam = f.beam;
  if (!beam || !beam.parent || n < 2) { _raeumePrisma(f); return; }
  let pool = f.prismPool;
  // Pool gehoert zu GENAU diesem Strahl (Neubau des Geraets -> neues f, also
  // ohnehin neuer Pool; die Pruefung faengt nur einen getauschten Strahl ab).
  if (!pool || pool.beam !== beam) {
    pool = f.prismPool = { beam, grp: new THREE.Group(), gelenke: [], kegel: [] };
  }
  const neigung = (f.baseSpotAngle || NEIGUNG_FALLBACK) * NEIGUNG_FAKTOR;
  while (pool.gelenke.length < n - 1) {
    // Ein Drehgelenk je Nebenstrahl, Ursprung = Linse. 'YXZ' heisst: erst um
    // X neigen, dann um Y in den Kreis drehen — in dieser Reihenfolge bleibt
    // der Neigungswinkel fuer alle Strahlen gleich gross.
    const gelenk = new THREE.Group();
    gelenk.rotation.order = 'YXZ';
    const m = new THREE.Mesh(beam.geometry, beam.material);
    m.position.copy(beam.position);
    // Wie der Hauptstrahl aus der Fit-Bounding-Box heraushalten, sonst zoomt
    // "Auswahl einpassen" wegen der Faecher-Kegel viel zu weit raus.
    m.userData.excludeFromFit = true;
    // Reine Deko, kein Koerper: three r128 prueft `visible` beim Raycast
    // NICHT. Ohne No-Op fingen ueberzaehlige (unsichtbare) Pool-Kegel nach
    // 6-fach -> 3-fach weiter Klicks ab und waehlten das Geraet statt Boden
    // oder Buehnenobjekt (Review VIZ-80, L1; dieselbe Regel wie laser.js).
    // Getroffen wird ueber Gehaeuse und Hauptstrahl.
    m.raycast = () => {};
    gelenk.add(m);
    pool.grp.add(gelenk);
    pool.gelenke.push(gelenk);
    pool.kegel.push(m);
  }
  const aktiv = [];
  for (let i = 0; i < pool.gelenke.length; i++) {
    const an = i < n - 1;
    pool.gelenke[i].visible = an;
    if (!an) continue;
    pool.gelenke[i].rotation.set(neigung, (i * 2 * Math.PI) / (n - 1), 0);
    const m = pool.kegel[i];
    m.position.copy(beam.position);
    m.scale.copy(beam.scale);
    m.visible = beam.visible;
    aktiv.push(m);
  }
  if (pool.grp.parent !== beam.parent) {
    if (pool.grp.parent) pool.grp.parent.remove(pool.grp);
    beam.parent.add(pool.grp);
  }
  f.prismGroup = pool.grp;
  f.prismCones = aktiv;
  f.prismFacetten = n;
}

/** Prisma-Facetten + Drehung auf den Strahl anwenden.
 *
 *  Der Service schickt DIFFERENTIELL: ein Batch ohne `prism` heisst
 *  "unveraendert" und darf das Prisma nicht abschalten — deshalb derselbe
 *  `last*`-Merker wie in `applyOptics`.
 */
export function applyPrism(f, dmx) {
  if (!f || !dmx) return;
  if (dmx.prism === undefined && dmx.prism_rotation === undefined) return;
  // VIZ-80: `null` = Profil ohne den Kanal (s. fixtures.js#OPTIK_FELDER).
  if (dmx.prism !== undefined) f.lastPrism = (dmx.prism === null) ? undefined : dmx.prism;
  if (dmx.prism_rotation !== undefined) {
    f.lastPrismRot = (dmx.prism_rotation === null) ? undefined : dmx.prism_rotation;
  }

  const n = prismFacetCount(f.lastPrism);
  if (n < 2) {
    _raeumePrisma(f);
    return;
  }
  if (f.prismFacetten !== n) _bauePrisma(f, n);
  if (!f.prismGroup) return;

  // Drehung: 0..255 auf eine volle Umdrehung. Ein Prisma dreht sich real
  // langsam weiter, aber der DMX-Wert ist eine POSITION (Index), keine
  // Geschwindigkeit — eine fortlaufende Eigendrehung waere hier erfunden.
  const rot = (typeof f.lastPrismRot === 'number' && isFinite(f.lastPrismRot))
    ? (Math.max(0, Math.min(255, f.lastPrismRot)) / 255) * 2 * Math.PI : 0;
  f.prismGroup.rotation.y = rot;

  // Sichtbarkeit und Kegelweite folgen dem Hauptstrahl — der traegt beides
  // (applyGenericColor bzw. applyOptics) und ist die einzige Wahrheit.
  const beam = f.beam;
  if (!beam) return;
  for (const m of f.prismCones) {
    m.visible = beam.visible;
    m.scale.copy(beam.scale);
    // VIZ-80: auch die Lage — setBeamLength (Auftreffpunkt) verschiebt den
    // Hauptstrahl mit seiner Laenge; ohne Nachzug hingen die Nebenkegel bei
    // geaenderter Laenge versetzt zur Linse.
    m.position.copy(beam.position);
  }
}

/** Die Prisma-Kegel dem Hauptstrahl nachziehen (Weite + Sichtbarkeit).
 *
 *  Noetig, weil `applyOptics` und `resyncBeamVisibility` den Hauptstrahl auch
 *  dann anfassen, wenn im Batch gar kein Prisma-Schluessel steht (Zoom-Zug,
 *  Settings-Toggle, 2D/3D-Wechsel). Ohne diesen Nachzug blieben die
 *  Nebenstrahlen auf einer alten Weite stehen oder haengen sichtbar, waehrend
 *  der Hauptstrahl schon aus ist.
 */
export function syncPrismToBeam(f) {
  if (!f || !f.prismCones || !f.beam) return;
  for (const m of f.prismCones) {
    m.visible = f.beam.visible;
    m.scale.copy(f.beam.scale);
    m.position.copy(f.beam.position);   // VIZ-80, s. applyPrism
    // VIZ-83: Gobo-Drehung — jeder Nebenstrahl dreht sein (geteiltes)
    // Teilstrahl-Muster um die eigene Achse mit.
    m.rotation.y = f.beam.rotation.y;
  }
}
