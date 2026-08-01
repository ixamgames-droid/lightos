// VIZ-MH-OPTICS (David-Wunsch 2026-07-16): der 3D-Strahl folgt Zoom und Iris.
//
// Vorher war der Lichtkegel ein FESTER Winkel: die Optik-Attribute waren im
// Programmer laengst steuerbar, kamen aber nie im 3D an (`zoom`/`iris` tauchten
// im Renderer nirgends auf). Ein Zoom-Zug hatte damit null Wirkung — man sah im
// Visualizer etwas anderes als am echten Gerät.
//
// UMGESETZT WIRD ES ALS SKALIERUNG, NICHT ALS NEUE GEOMETRIE: `beam.scale` auf
// X/Z aendert den Kegel-RADIUS und laesst die Laenge, ist also genau eine
// Winkel-Aenderung — und kostet im 44-Hz-Pfad nichts (kein Geometrie-Neubau,
// keine Allokation).
//
// ★ EHRLICH ZUR KONVENTION: DMX sagt nicht, in welche Richtung ein Zoom-Kanal
// laeuft. Der verbreitete Fall ist "0 = eng, 255 = weit" (so auch die
// eingebauten MH-Profile), und genau den nimmt diese Abbildung an. Bei einem
// Geraet mit umgekehrter Kanal-Laufrichtung sieht der Kegel im 3D dann falsch
// herum aus — sichtbar, aber folgenlos: an der DMX-AUSGABE aendert das nichts.
// Eine Umkehr-Angabe pro Profil waere die saubere Loesung und ist als eigener
// Punkt notiert, statt sie hier zu raten.

// ── Kantenschaerfe: Fokus + Frost ───────────────────────────────────────────
//
// Fokus wird NICHT als 0->255-Rampe abgebildet, und das ist der wichtigste
// Punkt an dieser Ergaenzung. Physikalisch ist Fokus eine BEIDSEITIGE
// mechanische Verstellung: die Linse laeuft von nah nach fern, scharf ist sie
// irgendwo dazwischen. Eine monotone Rampe waere schlicht falsch.
//
// Wo "dazwischen" liegt, sagt die Fixture-Library selbst: JEDES eingebaute
// Profil mit Fokus-Kanal setzt den Default auf 128 (4 von 4 nachgezaehlt),
// waehrend Frost und Prisma bei 0 stehen (4 von 4). Ein Default von 128 heisst
// "Mitte des Wegs" — und die Mitte ist die beste verfuegbare Aussage darueber,
// welche Stellung der Profil-Autor fuer normal hielt. Also: scharf bei 128,
// zu beiden Enden hin weicher.
//
// Frost dagegen IST monoton und hat eine eindeutige Konvention: 0 = kein
// Diffusor im Strahl, 255 = voll. Die Range-Tabellen der Library ("Light
// Frost" -> "Medium Frost") bestaetigen die Richtung.
//
// Angefasst wird nur `spot.penumbra` — der echte Kantenschaerfe-Regler, den
// sonst niemand pro Frame schreibt. Beam- und Bodenfleck-Deckkraft setzt
// `applyGenericColor` in jedem Frame neu; dort etwas hineinzuschreiben waere
// ein Kampf um dieselbe Eigenschaft, den der letzte Schreiber gewinnt.
// Zusaetzlich streut Frost den Kegel real etwas auf — das faellt in den
// vorhandenen Skalierungsfaktor und kostet damit ebenfalls nichts.
const ZOOM_ENG = 0.45;    // Faktor auf den Grundwinkel bei DMX 0
const ZOOM_WEIT = 1.90;   // ... bei DMX 255
const IRIS_ZU = 0.30;     // Iris ganz geschlossen laesst 30 % des Kegels
const FOKUS_MITTE = 128;  // Library-Default aller Profile mit Fokus-Kanal
const PENUMBRA_SCHARF = 0.12;
const PENUMBRA_WEICH = 0.95;
const FROST_AUFWEITUNG = 0.25;   // voller Frost weitet den Kegel um 25 %

/** DMX 0..255 -> Skalierungsfaktor des Kegel-Radius. */
export function opticsScale(zoom, iris) {
  let k = 1.0;
  if (typeof zoom === 'number' && isFinite(zoom)) {
    const z = Math.max(0, Math.min(255, zoom)) / 255;
    k *= ZOOM_ENG + (ZOOM_WEIT - ZOOM_ENG) * z;
  }
  if (typeof iris === 'number' && isFinite(iris)) {
    // Iris-Konvention wie beim Zoom: 0 = offen, 255 = zu.
    const i = Math.max(0, Math.min(255, iris)) / 255;
    k *= 1.0 - (1.0 - IRIS_ZU) * i;
  }
  return k;
}

/**
 * DMX 0..255 -> Weichheit der Kegelkante, 0 = knackscharf, 1 = ganz diffus.
 *
 * Fokus ist um `FOKUS_MITTE` herum scharf und wird zu BEIDEN Enden weicher
 * (s. Modulkopf); Frost ist monoton. Beide diffundieren unabhaengig
 * voneinander, deshalb multipliziert sich die verbleibende SCHAERFE.
 */
export function opticsSoftness(focus, frost) {
  let schaerfe = 1.0;
  if (typeof focus === 'number' && isFinite(focus)) {
    const d = Math.abs(Math.max(0, Math.min(255, focus)) - FOKUS_MITTE);
    schaerfe *= 1.0 - d / Math.max(FOKUS_MITTE, 255 - FOKUS_MITTE);
  }
  if (typeof frost === 'number' && isFinite(frost)) {
    schaerfe *= 1.0 - Math.max(0, Math.min(255, frost)) / 255;
  }
  return 1.0 - schaerfe;
}

/** Kegel + SpotLight eines Fixtures an Zoom/Iris/Fokus/Frost angleichen. */
export function applyOptics(f, dmx) {
  if (!f || !dmx) return;
  if (dmx.zoom === undefined && dmx.iris === undefined
      && dmx.focus === undefined && dmx.frost === undefined) return;  // ohne Optik
  // Letzten Stand merken: der Service schickt DIFFERENTIELL, ein Batch ohne
  // zoom heisst "unveraendert" und darf den Kegel nicht zurueckspringen lassen.
  if (dmx.zoom !== undefined) f.lastZoom = dmx.zoom;
  if (dmx.iris !== undefined) f.lastIris = dmx.iris;
  if (dmx.focus !== undefined) f.lastFocus = dmx.focus;
  if (dmx.frost !== undefined) f.lastFrost = dmx.frost;
  const weich = opticsSoftness(f.lastFocus, f.lastFrost);
  // Frost streut den Strahl real etwas auf; Fokus tut das NICHT — eine
  // unscharfe Kante ist keine breitere. Deshalb haengt die Aufweitung allein
  // am Frost-Wert, nicht an der gemeinsamen Weichheit.
  const frostAnteil = (typeof f.lastFrost === 'number' && isFinite(f.lastFrost))
    ? Math.max(0, Math.min(255, f.lastFrost)) / 255 : 0;
  const k = opticsScale(f.lastZoom, f.lastIris) * (1 + FROST_AUFWEITUNG * frostAnteil);
  // ★ Y bleibt STEHEN, statt auf 1 zurueckgesetzt zu werden. Die Y-Achse ist
  // die KEGELLAENGE und gehoert einem anderen Besitzer: setBeamLength in
  // builders.js (Bodenauftreffpunkt aus VIZ-BEAM-OCCLUSION, globale Obergrenze
  // aus VIZ-15). Ein hartes `1` funktionierte bisher nur, WEIL applyFloorAim
  // zufaellig danach lief und die Laenge neu setzte — eine unsichtbare
  // Reihenfolge-Abhaengigkeit, die beim naechsten Umsortieren der
  // updateDmx-Kette gerissen waere (und dazwischen haette der Kegel eine
  // Laenge und eine Position aus zwei verschiedenen Rechnungen gehabt).
  // Zoom/Iris/Frost aendern die WEITE, nie die Laenge — hier also nur X/Z.
  if (f.beam) f.beam.scale.set(k, f.beam.scale.y, k);
  if (f.spot && f.baseSpotAngle) {
    // Der SpotLight traegt die Ausleuchtung — ohne ihn wuerde nur der sichtbare
    // Kegel schmaler, der Bodenfleck aber gleich gross bleiben.
    f.spot.angle = Math.min(Math.PI / 2 - 0.01, f.baseSpotAngle * k);
    // Nur anfassen, wenn das Geraet die Kanaele WIRKLICH hat — sonst bekaeme
    // jeder Scheinwerfer ohne Fokus/Frost eine erfundene Kantenschaerfe
    // (dieselbe Falle wie der erfundene 128er-Zoom-Default).
    if (f.lastFocus !== undefined || f.lastFrost !== undefined) {
      f.spot.penumbra = PENUMBRA_SCHARF + (PENUMBRA_WEICH - PENUMBRA_SCHARF) * weich;
    }
  }
  // VIZ-PRISMA-3D: die Prisma-Nebenstrahlen muessen diese Weite mitmachen.
  // Der Nachzug steht bewusst NICHT hier, sondern in builders.js direkt hinter
  // dem applyOptics-Aufruf — dieses Modul ist absichtlich importfrei und damit
  // als reiner Test-Seam aufrufbar (test_viz_optics_focus_frost_scene.py ruft
  // opticsSoftness/applyOptics mit einem gestellten Objekt auf).
}
