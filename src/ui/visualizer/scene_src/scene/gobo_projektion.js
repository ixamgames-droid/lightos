// VIZ-96: Gobo-Projektion mit Verdeckung (Weg B — eigener Shader in r128).
//
// Bis VIZ-96 lag das Gobo-Muster als flache Scheibe auf der Flaeche, die der
// ZENTRALSTRAHL trifft (fixtures/gobo_textures.js). Steht eine Traverse oder
// ein Buehnenkoerper nur teilweise im Strahl, ignorierte das Muster ihn: kein
// Muster auf dem Hindernis, kein Schatten dahinter.
//
// three.js r128 kennt kein `SpotLight.map`. Es rechnet aber fuer jedes
// SCHATTENWERFENDE Spot-Licht schon die projektive Koordinate aus Lichtsicht
// (`vSpotShadowCoord[ i ]`) und multipliziert im Licht-Loop die Verdeckung
// (`getShadow`) auf den Lichtbeitrag. Genau dort haengt dieses Modul EINE
// weitere Multiplikation an: das Gobo-Motiv als Maske. Das Muster faellt damit
// auf alles, was das Licht trifft, und was im Schatten liegt, bleibt dunkel —
// die Verdeckung kommt aus der vorhandenen Shadow-Map, ohne neuen Durchlauf.
//
// Regeln (VIZ-69 / VIZ-PERF):
//   * KEINE Shader-Variante je Gobo. Der Patch ist fuer alle beleuchteten
//     Materialien derselbe (eine Funktion -> ein Programmschluessel-Zusatz);
//     Gobo-Wechsel, Drehung und an/aus schreiben nur `lightosGoboParam`.
//   * Genau EIN zusaetzlicher Sampler (`lightosGoboMap`): ein Atlas mit allen
//     Motiven, unabhaengig von der Zahl der Lichter.
//   * Auf der Stufe Niedrig wird nichts installiert — Shader und Verhalten
//     sind dort exakt wie vor VIZ-96 (flaches Bodenmuster).
//
// Rein (keine Imports): three-Klassen, Chunk-Text und Atlas-Textur reicht der
// Aufrufer herein (scene/spot_pool.js). Node-Tests laden das Modul direkt
// (tests/test_viz96_gobo_projektion.py) und pruefen den Patch gegen die
// echten r128-Chunks aus three_local.js.
"use strict";

/** Raster des Motiv-Atlas (Kacheln). 4 x 2 = 8 Plaetze fuer 7 Motive. */
export const GOBO_ATLAS_SPALTEN = 4;
export const GOBO_ATLAS_ZEILEN = 2;
/** So viele Schatten-Lichter kann `lightosGoboParam` hoechstens bedienen
 *  (= Schatten-Dach der Stufe Maximal, fixtures.js SHADOW_SPOT_HARD_CAP_MAX). */
export const GOBO_MAX_LICHTER = 16;
/** Zusaetzliche Textur-Slots je beleuchtetem Material (der Atlas). */
export const GOBO_SLOTS = 1;
/** Groesster Oeffnungswinkel (rad) eines projizierenden Lichts. */
export const GOBO_MAX_LICHTWINKEL = 1.35;
/** Halbschatten eines projizierenden Lichts: die Blende hat selbst einen
 *  runden Rand (gobo_textures.js#zeichne), der weiche Pool-Verlauf dunkelte
 *  die Motiv-Teile am Rand ab (VIZ-92). */
export const GOBO_HALBSCHATTEN = 0.05;

// ── VIZ-96 B3: Uebergaenge und Angleichung ──────────────────────────────────
/** Dauer EINER Blende (ms): Projektion aus- bzw. einblenden. Wechselt ein
 *  Pool-Licht den Besitzer, laufen zwei nacheinander (alter Halter aus, neuer
 *  ein) — ein Licht kann nur ein Motiv tragen. */
export const GOBO_BLENDE_MS = 180;
/** Laengster Zeitschritt einer Blende (ms). Bilder entstehen nur auf
 *  Anforderung; nach einer Pause darf der erste Schritt die Blende nicht
 *  ueberspringen. Und beim Umzug eines Lichts entstehen die Shadow-Maps neu —
 *  das Bild dauert dann laenger (am Bildschirm gemessen: ein Schritt trug ein
 *  Drittel des ganzen Wechsels). Mit 50 ms traegt kein Bild mehr als gut ein
 *  Viertel; bei niedriger Bildrate dauert die Blende dafuer etwas laenger. */
export const GOBO_BLENDE_SCHRITT_MAX_MS = 50;
/** Ein Geraet, das gerade projiziert, zaehlt bei der Pool-Vergabe um diesen
 *  Faktor heller (zusaetzlich zur Pool-Hysterese): ein Wechsel kostet hier
 *  eine sichtbare Blende, er soll nicht an einer knappen Helligkeits-Differenz
 *  haengen. */
export const GOBO_HALTE_BONUS = 1.2;
/** Helligkeit des flachen Rueckfall-Musters, solange die Projektion aktiv ist
 *  (Stufen Hoch/Maximal). Die Projektion ist echtes Licht (Flaechenfarbe x
 *  Licht), das flache Muster eine additive Scheibe — am Bildschirm gemessen
 *  war die Scheibe bei gleichem Dimmer deutlich heller (Sichtpruefung B2).
 *  Angeglichen wird die SCHEIBE: die Projektion teilt sich die Lichtstaerke mit
 *  allen offenen Strahlen (VIZ-91-Abstimmung), ein Faktor dort haette Gobo-
 *  Strahlen gegen offene verschoben; und dunkler brennt nichts aus. */
export const GOBO_FLACH_HELL = 0.8;
/** Buehnen-Elemente bis zu dieser mittleren Kantenlaenge (m) koennen fuer ein
 *  Gobo-Muster "schmal" sein (Traverse, Stuetze, kleines Podest). */
export const GOBO_SCHMAL_MAX = 1.2;
/** VIZ-102: Reichweite der Projektion entlang der Lichtachse.
 *
 *  B3 schnitt die Projektion an der Buehnenkante ab. Jetzt laeuft sie ueber
 *  Kanten weiter (die Buehne wirft ihren Schatten), gehoert aber zum KEGEL:
 *
 *   * `quadrat`: Achsabstand des fernen Kegelrands auf der getroffenen
 *     Flaeche. Bis dahin volle Staerke (das Muster auf seiner Flaeche bleibt,
 *     wie es war); was tiefer faellt (Hallenboden hinter der Kante), wird mit
 *     dem Abstandsquadrat schwaecher — es ist dort nie heller als oben.
 *   * `reich`: so weit reicht der sichtbare Kegel (mindestens `quadrat`).
 *     Dahinter blendet die Projektion bis GOBO_AUSBLENDE x `reich` weich aus:
 *     kein Muster ohne Strahl, auch wenn der Kegel an seiner Grundlaenge
 *     endet.
 */
export const GOBO_AUSBLENDE = 1.15;
/** "Keine Grenze" (kein Auftreffpunkt, Licht ohne Gobo). */
export const GOBO_FERN_AUS = 1e6;

/** Ein Zeitschritt der Blende: `anteil` (0..1) laeuft linear auf `ziel`. */
export function goboBlendeSchritt(anteil, ziel, dtMs, dauerMs = GOBO_BLENDE_MS) {
  const a = (typeof anteil === 'number' && isFinite(anteil)) ? Math.max(0, Math.min(1, anteil)) : 0;
  const z = ziel > 0.5 ? 1 : 0;
  if (!(dauerMs > 0)) return z;
  const dt = Math.max(0, Math.min(GOBO_BLENDE_SCHRITT_MAX_MS, dtMs || 0));
  const schritt = dt / dauerMs;
  if (z > a) return Math.min(1, a + schritt);
  return z < a ? Math.max(0, a - schritt) : a;
}

/** Deckkraft der flachen Scheibe: `basis` (aus Dimmer), angeglichen an die
 *  Projektion und mit dem Anteil des flachen Musters (1 = nur flach). Anteil 0
 *  laesst die Deckkraft stehen — die Scheibe ist dann ueber ihre Ebenen-Maske
 *  ausgeblendet, und "Deckkraft > 0" bleibt das Mass fuer "leuchtet". */
export function goboFlachDeckkraft(basis, anteil) {
  const a = (typeof anteil === 'number' && isFinite(anteil)) ? Math.max(0, Math.min(1, anteil)) : 1;
  return basis * GOBO_FLACH_HELL * (a > 0 ? a : 1);
}

/** Ist ein Buehnen-Element fuer ein Muster mit `durchmesser` (m, Kegelrand)
 *  zu schmal, um es zu tragen? Massgeblich ist die MITTLERE Kantenlaenge:
 *  Traverse 2,4 x 0,3 x 0,3 -> 0,3 (schmal), Wand 10 x 6 x 0,2 -> 6,
 *  Buehnenplatte 8 x 1 x 5 -> 5 (beide Ziel). */
export function goboSchmal(groesse, durchmesser) {
  if (!groesse || !(durchmesser > 0)) return false;
  const k = [Math.abs(groesse.x), Math.abs(groesse.y), Math.abs(groesse.z)];
  if (!k.every(v => typeof v === 'number' && isFinite(v))) return false;
  k.sort((a, b) => a - b);
  return k[1] < Math.min(GOBO_SCHMAL_MAX, durchmesser);
}

/** VIZ-102: Reichweiten-Paar [quadrat, reich] eines projizierenden Lichts.
 *  Unbrauchbare Werte: keine Grenze. */
export function goboFern(quadrat, reich) {
  const ok = (v) => v > 0 && isFinite(v) && v < 90;
  if (!ok(quadrat)) return [GOBO_FERN_AUS, GOBO_FERN_AUS];
  return [quadrat, ok(reich) ? Math.max(quadrat, reich) : GOBO_FERN_AUS];
}

/** Faktor, den der Shader bei Achsabstand `w` anlegt (Test-Seam, dieselbe
 *  Rechnung wie GOBO_GLSL_MASKE). */
export function goboFernFaktor(fern, w) {
  const q = fern[0] / Math.max(w, 0.0001);
  const a = fern[1], b = fern[1] * GOBO_AUSBLENDE;
  const t = Math.max(0, Math.min(1, (w - a) / (b - a)));
  return Math.min(1, q * q) * (1 - t * t * (3 - 2 * t));
}

// ── VIZ-102: Kante der getroffenen Oberseite ────────────────────────────────
// `kante` beschreibt die Oberseite eines Buehnenkoerpers als gedrehtes
// Rechteck in der Welt: Mitte (cx, cz), halbe Kanten (hx, hz), Drehung um y
// als (c, s) = (cos, sin), Hoehe y. Lokale x-Achse = (c, -s), z-Achse = (s, c).

/** Abstand (m) des Punkts (x, z) zur naechsten Kante, von innen gemessen;
 *  negativ = ausserhalb. */
export function kantenAbstand(kante, x, z) {
  const dx = x - kante.cx, dz = z - kante.cz;
  const lx = dx * kante.c - dz * kante.s;
  const lz = dx * kante.s + dz * kante.c;
  return Math.min(kante.hx - Math.abs(lx), kante.hz - Math.abs(lz));
}

/** Wie weit ragt ein Muster mit Radius `radius` um den Auftreffpunkt ueber
 *  die Kante (0 = ganz auf der Flaeche, 1 = Mitte auf der Kante)? Weich
 *  (smoothstep): daran haengt die Kegellaenge, sie soll nicht springen. */
export function goboUeberhang(randAbstand, radius) {
  if (!(radius > 0) || typeof randAbstand !== 'number' || !isFinite(randAbstand)) return 0;
  const u = Math.max(0, Math.min(1, 1 - randAbstand / radius));
  return u * u * (3 - 2 * u);
}

// Groesster Winkel (rad) eines Randstrahls zur Senkrechten, mit dem gerechnet
// wird — flacher trifft er die Flaeche erst in beliebiger Ferne.
const FLACH_DACH = 1.45;

/** Fussabdruck eines geneigten Kegels auf einer waagerechten Flaeche: wie weit
 *  reicht er vom Auftreffpunkt der Achse aus in acht Richtungen?
 *
 *  Ein geneigter Kegel schneidet die Flaeche in einer Ellipse, die vom Geraet
 *  WEG viel weiter reicht als zu ihm hin (Neigung 42 Grad, halber Winkel 24
 *  Grad: 5,7 m nach vorn, 1,6 m zurueck). Ob ein Muster ueber eine Kante ragt,
 *  entscheidet deshalb die Richtung, nicht ein Radius.
 *
 *  @param dx,dy,dz  Strahlrichtung (normiert, dy < 0 = nach unten)
 *  @param abstand   Achse: Spitze -> Auftreffpunkt (m)
 *  @param tanA      Tangens des halben Oeffnungswinkels
 *  @returns [{dx, dz, weit}] — Richtung in der Flaeche (normiert), Reichweite (m)
 */
export function strahlFussabdruck(dx, dy, dz, abstand, tanA) {
  if (!(abstand > 0) || !(tanA > 0) || !isFinite(abstand) || !isFinite(tanA)) return [];
  const th = Math.acos(Math.max(-1, Math.min(1, -dy)));
  if (!(th < FLACH_DACH)) return [];
  const a = Math.atan(tanA), H = abstand * Math.cos(th);
  const vor = H * (Math.tan(Math.min(th + a, FLACH_DACH)) - Math.tan(th));
  const zurueck = H * (Math.tan(th) - Math.tan(th - a));
  const quer = abstand * tanA;
  let ux = dx, uz = dz;
  const l = Math.hypot(ux, uz);
  if (l > 1e-6) { ux /= l; uz /= l; } else { ux = 1; uz = 0; }
  const px = -uz, pz = ux;
  const schraeg = (laengs) => 1 / Math.sqrt(0.5 / (laengs * laengs) + 0.5 / (quer * quer));
  const w = Math.SQRT1_2;
  return [
    { dx: ux, dz: uz, weit: vor }, { dx: -ux, dz: -uz, weit: zurueck },
    { dx: px, dz: pz, weit: quer }, { dx: -px, dz: -pz, weit: quer },
    { dx: (ux + px) * w, dz: (uz + pz) * w, weit: schraeg(vor) },
    { dx: (ux - px) * w, dz: (uz - pz) * w, weit: schraeg(vor) },
    { dx: (-ux + px) * w, dz: (-uz + pz) * w, weit: schraeg(zurueck) },
    { dx: (-ux - px) * w, dz: (-uz - pz) * w, weit: schraeg(zurueck) },
  ];
}

/** Ueberhang (0..1, weich) eines Fussabdrucks ueber die Kante: je Richtung
 *  der Weg vom Auftreffpunkt bis zur Kante gegen die Reichweite dorthin. */
export function goboUeberhangGerichtet(kante, x, z, fuss) {
  if (!kante || !fuss || !fuss.length) return 0;
  const ox = x - kante.cx, oz = z - kante.cz;
  const lx = ox * kante.c - oz * kante.s, lz = ox * kante.s + oz * kante.c;
  if (Math.abs(lx) >= kante.hx || Math.abs(lz) >= kante.hz) return 1;
  let u = 0;
  for (const r of fuss) {
    if (!(r.weit > 0)) continue;
    const rx = r.dx * kante.c - r.dz * kante.s, rz = r.dx * kante.s + r.dz * kante.c;
    let platz = Infinity;
    if (rx > 1e-9) platz = Math.min(platz, (kante.hx - lx) / rx);
    else if (rx < -1e-9) platz = Math.min(platz, (-kante.hx - lx) / rx);
    if (rz > 1e-9) platz = Math.min(platz, (kante.hz - lz) / rz);
    else if (rz < -1e-9) platz = Math.min(platz, (-kante.hz - lz) / rz);
    u = Math.max(u, 1 - platz / r.weit);
  }
  u = Math.max(0, Math.min(1, u));
  return u * u * (3 - 2 * u);
}

/** VIZ-107: Gegenstueck zum Ueberhang fuer einen Punkt NEBEN der Oberseite —
 *  wie weit reicht der Fussabdruck noch auf sie (0 = gar nicht, 1 = der Punkt
 *  liegt auf der Kante oder auf der Oberseite)? Je Richtung der Weg vom Punkt
 *  bis zum Eintritt ins Rechteck gegen die Reichweite dorthin. Weich
 *  (smoothstep) wie der Ueberhang: daran haengen Kegelwinkel und Helligkeit,
 *  nachdem die Strahlmitte die Kante ueberquert hat — sie sollen nicht
 *  springen. */
export function goboInnenGerichtet(kante, x, z, fuss) {
  if (!kante || !fuss || !fuss.length) return 0;
  const ox = x - kante.cx, oz = z - kante.cz;
  const lx = ox * kante.c - oz * kante.s, lz = ox * kante.s + oz * kante.c;
  if (Math.abs(lx) <= kante.hx && Math.abs(lz) <= kante.hz) return 1;
  let u = 0;
  for (const r of fuss) {
    if (!(r.weit > 0)) continue;
    const rx = r.dx * kante.c - r.dz * kante.s, rz = r.dx * kante.s + r.dz * kante.c;
    // Strahl (lx, lz) + s * (rx, rz), s >= 0, gegen das Rechteck: Eintritt
    // und Austritt je Achse (Scheiben-Verfahren).
    let ein = 0, aus = Infinity, trifft = true;
    for (const [p, d, h] of [[lx, rx, kante.hx], [lz, rz, kante.hz]]) {
      if (Math.abs(d) < 1e-9) {
        if (Math.abs(p) > h) trifft = false;
        continue;
      }
      const a = (-h - p) / d, b = (h - p) / d;
      ein = Math.max(ein, Math.min(a, b));
      aus = Math.min(aus, Math.max(a, b));
    }
    if (!trifft || !(ein <= aus)) continue;
    u = Math.max(u, 1 - ein / r.weit);
  }
  u = Math.max(0, Math.min(1, u));
  return u * u * (3 - 2 * u);
}

/** Wie lang (m, entlang der Achse) muss der Kegel sein, damit sein FERNER
 *  Rand die Flaeche unter der Kante erreicht? `untenAbstand` = Achse bis zu
 *  dieser Flaeche. Senkrecht nach unten ist das genau `untenAbstand`. */
export function kegelFernLaenge(dy, tanA, untenAbstand) {
  if (!(untenAbstand > 0) || !isFinite(untenAbstand)) return untenAbstand;
  const th = Math.acos(Math.max(-1, Math.min(1, -dy)));
  const a = Math.atan(Math.max(0, tanA) || 0);
  if (!(th < FLACH_DACH)) return untenAbstand;
  const H = untenAbstand * Math.cos(th);
  return Math.max(untenAbstand, H / Math.cos(Math.min(th + a, FLACH_DACH)) * Math.cos(a));
}

/** VIZ-102: Schattenraum UNTER einer Oberseite, vom Lichtpunkt aus — die
 *  Pyramide durch die vier Kanten, unterhalb der Oberseite. Der Lichtkegel
 *  wird darin nicht gezeichnet: was auf der Oberseite auftrifft, endet dort;
 *  nur was an der Kante vorbeigeht, laeuft weiter.
 *
 *  @returns fuenf Ebenen [nx, ny, nz, d] — ein Punkt liegt im Schattenraum,
 *           wenn n * p + d fuer ALLE fuenf negativ ist (clipIntersection);
 *           null, wenn das Licht nicht ueber der Oberseite steht.
 */
export function schattenPyramide(kante, ax, ay, az) {
  if (!kante || !(ay - kante.y > 1e-3)) return null;
  const ecke = (ex, ez) => {
    const lx = ex * kante.hx, lz = ez * kante.hz;
    return [kante.cx + lx * kante.c + lz * kante.s, kante.y, kante.cz - lx * kante.s + lz * kante.c];
  };
  const e = [ecke(1, 1), ecke(1, -1), ecke(-1, -1), ecke(-1, 1)];
  const out = [];
  for (let k = 0; k < 4; k++) {
    const p = e[k], q = e[(k + 1) % 4];
    const ux = p[0] - ax, uy = p[1] - ay, uz = p[2] - az;
    const vx = q[0] - ax, vy = q[1] - ay, vz = q[2] - az;
    let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    const l = Math.hypot(nx, ny, nz);
    if (!(l > 1e-9)) return null;
    nx /= l; ny /= l; nz /= l;
    let d = -(nx * ax + ny * ay + nz * az);
    // Innen (Mitte der Oberseite) negativ.
    if (nx * kante.cx + ny * kante.y + nz * kante.cz + d > 0) { nx = -nx; ny = -ny; nz = -nz; d = -d; }
    out.push([nx, ny, nz, d]);
  }
  out.push([0, 1, 0, -kante.y]);      // unterhalb der Oberseite negativ
  return out;
}

/** Schatten der Oberseite auf der Ebene `yUnten`, vom Lichtpunkt (ax, ay, az)
 *  aus: wieder ein Rechteck gleicher Drehung (zentrische Streckung um den
 *  Lichtfusspunkt). null, wenn das Licht nicht ueber der Oberseite steht. */
export function schattenRechteck(kante, ax, ay, az, yUnten) {
  const oben = ay - kante.y, ganz = ay - yUnten;
  if (!(oben > 1e-3) || !(ganz > oben)) return null;
  const k = ganz / oben;
  if (!isFinite(k) || k > 50) return null;
  return {
    cx: ax + (kante.cx - ax) * k, cz: az + (kante.cz - az) * k,
    hx: kante.hx * k, hz: kante.hz * k, c: kante.c, s: kante.s, y: yUnten,
  };
}

// ── Shader-Patch ────────────────────────────────────────────────────────────
// Anker: die Schatten-Zeile des SPOT-Blocks in `lights_fragment_begin` (r128).
// Sie steht innerhalb von
//   #if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
// — die Maske erbt diese Bedingung und liegt damit nur auf Lichtern, die eine
// Shadow-Map (und damit `vSpotShadowCoord[ i ]`) haben.
export const GOBO_INCLUDE = '#include <lights_fragment_begin>';
export const GOBO_ANKER =
  'spotLightShadow.shadowRadius, vSpotShadowCoord[ i ] ) : 1.0;';

// ⚠️ `[ i ]` genau so schreiben: three rollt die Licht-Schleife per Textersatz
// aus (/\[\s*i\s*\]/ -> `[ 0 ]`, `[ 1 ]`, ...). Ein nacktes `i` bliebe stehen.
// `w` wird nach unten begrenzt: hinter dem Licht waere die Division sonst
// 0/0 -> NaN, und NaN * 0 (Licht dort ohnehin aus) bliebe NaN.
// ── VIZ-102: weicher Schattenrand im Gobo-Bild ──────────────────────────────
// Der Schatten einer Kante (Buehnenplatte, Wuerfel) schneidet hart durch die
// Motiv-Teile; was die Schattengrenze nur knapp ueberragt, blieb als duenner
// Keil oder Splitter stehen. Fuer projizierende Lichter liest die Maske die
// Shadow-Map deshalb an acht Stellen im Umkreis (zwei Ringe) und laesst das
// Bild dort weich auslaufen, wo ein Teil der Umgebung im Schatten liegt:
// schmale Reste verschwinden, die Grenze bekommt einen Halbschatten.
// Als verdeckt zaehlt eine Stelle nur, wenn der Schattenwerfer DEUTLICH
// naeher am Licht liegt (GOBO_SAUM_TIEFE) — so wirft eine schraeg getroffene
// Flaeche keinen Scheinschatten auf sich selbst (die Tiefe aendert sich dort
// ueber den Umkreis um Zentimeter), ein Hindernis mit Abstand aber schon.
/** Radien der beiden Ringe in Texeln der Shadow-Map. */
export const GOBO_SAUM_RINGE = [3, 7];
/** Mindestabstand (m) Schattenwerfer -> Flaeche fuer den weichen Rand. */
export const GOBO_SAUM_TIEFE = 0.3;
/** Near-Ebene der Schattenkamera der Pool-Lichter (spot_pool.js#SCHATTEN_NEAR;
 *  ein Szenen-Test haelt beide gleich). Damit wird GOBO_SAUM_TIEFE in
 *  Tiefenpuffer-Einheiten umgerechnet: dz = 0,5 * near * dm / w^2 (far >> near). */
export const GOBO_SCHATTEN_NAH = 0.5;
/** Anteil unverdeckter Stellen, ab dem das Bild beginnt bzw. voll steht. */
export const GOBO_SAUM_STUFE = [0.3, 0.9];

function _saumGlsl() {
  const [r1, r2] = GOBO_SAUM_RINGE;
  const d = (r2 * Math.SQRT1_2).toFixed(3);
  const versatz = [
    [r1.toFixed(1), '0.0'], ['-' + r1.toFixed(1), '0.0'], ['0.0', r1.toFixed(1)], ['0.0', '-' + r1.toFixed(1)],
    [d, d], ['-' + d, d], [d, '-' + d], ['-' + d, '-' + d],
  ];
  const k = (0.5 * GOBO_SCHATTEN_NAH * GOBO_SAUM_TIEFE).toFixed(4);
  const zeilen = [
    '\t\t\tif ( receiveShadow && lightosGp.x > 0.0 && lightosGm > 0.0 ) {',
    '\t\t\t\tvec3 lightosGc = vSpotShadowCoord[ i ].xyz / lightosGw;',
    '\t\t\t\tfloat lightosGz = lightosGc.z + spotLightShadow.shadowBias - ' + k + ' / ( lightosGw * lightosGw );',
    '\t\t\t\tvec2 lightosGt = 1.0 / spotLightShadow.shadowMapSize;',
    '\t\t\t\tfloat lightosGs = 0.0;',
  ];
  for (const [x, y] of versatz) {
    zeilen.push('\t\t\t\tlightosGs += texture2DCompare( spotShadowMap[ i ], lightosGc.xy + vec2( '
                + x + ', ' + y + ' ) * lightosGt, lightosGz );');
  }
  zeilen.push('\t\t\t\tlightosGm *= smoothstep( ' + GOBO_SAUM_STUFE[0].toFixed(2) + ', '
              + GOBO_SAUM_STUFE[1].toFixed(2) + ', lightosGs * 0.125 );');
  zeilen.push('\t\t\t}');
  return zeilen;
}

/** Dieselbe Rechnung wie im Shader (Test-Seam): `frei` = Zahl der acht
 *  Stellen, die NICHT verdeckt sind. */
export function goboSaumFaktor(frei) {
  const t = Math.max(0, Math.min(1, (frei / 8 - GOBO_SAUM_STUFE[0]) / (GOBO_SAUM_STUFE[1] - GOBO_SAUM_STUFE[0])));
  return t * t * (3 - 2 * t);
}

export const GOBO_GLSL_MASKE = [
  '',
  '\t\t{',
  '\t\t\tvec4 lightosGp = lightosGoboParam[ i ];',
  '\t\t\tvec2 lightosGd = vSpotShadowCoord[ i ].xy / max( vSpotShadowCoord[ i ].w, 0.0001 ) - 0.5;',
  '\t\t\tlightosGd = vec2( lightosGp.y * lightosGd.x - lightosGp.z * lightosGd.y, lightosGp.z * lightosGd.x + lightosGp.y * lightosGd.y ) + 0.5;',
  '\t\t\tfloat lightosGin = step( 0.0, lightosGd.x ) * step( lightosGd.x, 1.0 ) * step( 0.0, lightosGd.y ) * step( lightosGd.y, 1.0 );',
  '\t\t\tfloat lightosGnr = floor( lightosGp.w + 0.5 );',
  '\t\t\tvec2 lightosGk = vec2( mod( lightosGnr, ' + GOBO_ATLAS_SPALTEN + '.0 ), floor( lightosGnr / ' + GOBO_ATLAS_SPALTEN + '.0 ) );',
  '\t\t\tfloat lightosGm = texture2D( lightosGoboMap, ( lightosGk + clamp( lightosGd, 0.002, 0.998 ) ) / vec2( ' + GOBO_ATLAS_SPALTEN + '.0, ' + GOBO_ATLAS_ZEILEN + '.0 ) ).r * lightosGin;',
  '\t\t\tfloat lightosGw = max( vSpotShadowCoord[ i ].w, 0.0001 );',
  '\t\t\tfloat lightosGf = lightosGoboFern[ i ].x / lightosGw;',
  '\t\t\tlightosGm *= min( 1.0, lightosGf * lightosGf ) * ( 1.0 - smoothstep( lightosGoboFern[ i ].y, lightosGoboFern[ i ].y * ' + GOBO_AUSBLENDE.toFixed(2) + ', lightosGw ) );',
].concat(_saumGlsl(), [
  '\t\t\tdirectLight.color *= mix( 1.0, lightosGm, lightosGp.x );',
  '\t\t}',
]).join('\n');

export const GOBO_GLSL_KOPF = [
  '#if defined( USE_SHADOWMAP ) && NUM_SPOT_LIGHT_SHADOWS > 0',
  'uniform sampler2D lightosGoboMap;',
  'uniform vec4 lightosGoboParam[ NUM_SPOT_LIGHT_SHADOWS ];',
  'uniform vec2 lightosGoboFern[ NUM_SPOT_LIGHT_SHADOWS ];',
  '#endif',
  '',
].join('\n');

function _genauEinmal(text, teil) {
  const i = text.indexOf(teil);
  return i >= 0 && text.indexOf(teil, i + teil.length) < 0;
}

/** `lights_fragment_begin` um die Gobo-Maske erweitern. Liefert null, wenn der
 *  Anker nicht GENAU einmal vorkommt (anderer three-Stand) — dann wird nichts
 *  gepatcht, und die Szene bleibt beim flachen Bodenmuster. */
export function patchLichtChunk(chunk) {
  if (typeof chunk !== 'string' || !_genauEinmal(chunk, GOBO_ANKER)) return null;
  return chunk.replace(GOBO_ANKER, GOBO_ANKER + GOBO_GLSL_MASKE);
}

/** Fragment-Shader eines beleuchteten Materials (noch mit `#include`-Zeilen,
 *  so wie `onBeforeCompile` ihn bekommt) patchen. null = nicht patchbar. */
export function patchFragmentShader(fragmentShader, chunk) {
  if (typeof fragmentShader !== 'string' || !_genauEinmal(fragmentShader, GOBO_INCLUDE)) return null;
  const gepatcht = patchLichtChunk(chunk);
  if (gepatcht === null) return null;
  return GOBO_GLSL_KOPF + fragmentShader.replace(GOBO_INCLUDE, gepatcht);
}

// ── Atlas ───────────────────────────────────────────────────────────────────
/** Platz (Spalte, Zeile ab UNTEN) der Kachel `nr`. */
export function goboKachelPlatz(nr) {
  return [nr % GOBO_ATLAS_SPALTEN, Math.floor(nr / GOBO_ATLAS_SPALTEN)];
}

/** Alle Motive auf EIN Canvas zeichnen.
 *
 *  @param stile        Stil-Namen in Kachel-Reihenfolge
 *  @param canvasFuer   stil -> Canvas des Motivs (oder null)
 *  @param neuesCanvas  (breite, hoehe) -> leeres Canvas
 *  @param kachelPx     Kantenlaenge einer Kachel
 *  @returns { canvas, index: { stil: kachelNr } } oder null
 *
 *  Zeile 0 liegt UNTEN im Bild: eine CanvasTexture wird mit flipY geladen,
 *  v = 0 ist also die Unterkante — und innerhalb der Kachel steht das Motiv
 *  damit genauso wie in seiner Einzeltextur am Bodenfleck. */
export function baueGoboAtlas(stile, canvasFuer, neuesCanvas, kachelPx) {
  const plaetze = GOBO_ATLAS_SPALTEN * GOBO_ATLAS_ZEILEN;
  if (!stile || !stile.length || stile.length > plaetze || !(kachelPx > 0)) return null;
  const canvas = neuesCanvas(GOBO_ATLAS_SPALTEN * kachelPx, GOBO_ATLAS_ZEILEN * kachelPx);
  const g = canvas && canvas.getContext && canvas.getContext('2d');
  if (!g) return null;
  g.fillStyle = '#000';                       // schwarz = kein Licht
  g.fillRect(0, 0, canvas.width, canvas.height);
  const index = {};
  for (let nr = 0; nr < stile.length; nr++) {
    const motiv = canvasFuer(stile[nr]);
    if (!motiv) return null;
    const [spalte, zeile] = goboKachelPlatz(nr);
    g.drawImage(motiv, spalte * kachelPx, (GOBO_ATLAS_ZEILEN - 1 - zeile) * kachelPx,
                kachelPx, kachelPx);
    index[stile[nr]] = nr;
  }
  return { canvas, index };
}

// ── Abbildung Licht -> Motiv (reine Zahlen) ─────────────────────────────────
/** Oeffnungswinkel des projizierenden Lichts und Massstab des Motivs.
 *
 *  Das Motiv traegt den Kegelrand bei `rand` (GOBO_RAND) seines Radius, die
 *  Motiv-Teile reichen darueber hinaus. Das Licht oeffnet deshalb so weit,
 *  dass die GANZE Kachel in seinen Kegel passt: tan(winkel) = tanKegel / rand
 *  (Massstab 1). Erst am Deckel `maxWinkel` schrumpft stattdessen der
 *  Massstab — der Kegelrand bleibt in jedem Fall auf `rand`.
 *
 *  @param tanKegel  Tangens des halben Oeffnungswinkels des SICHTBAREN Kegels
 */
export function goboLichtWinkel(tanKegel, rand, maxWinkel = GOBO_MAX_LICHTWINKEL) {
  if (!(tanKegel > 0) || !(rand > 0)) return null;
  const winkel = Math.min(maxWinkel, Math.atan(tanKegel / rand));
  return { winkel, skala: rand * Math.tan(winkel) / tanKegel };
}

/** Drehung Schatten-Kamera -> Motiv als [cos, sin].
 *
 *  Die Schattenkamera von three blickt per lookAt mit Welt-Up auf das Ziel —
 *  Pan und Gobo-Drehung des Kopfes stecken NICHT in ihrer Matrix. Hier wird
 *  die fehlende Drehung aus den Achsen berechnet: `ex`/`ez` sind die lokalen
 *  x-/z-Achsen des Kegels (Welt, normiert; sie tragen Kopfstellung UND
 *  Gobo-Winkel `beam.rotation.y`), `R`/`U` Rechts- und Hoch-Achse der
 *  Schattenkamera. Uebergeben werden die vier Skalarprodukte.
 *
 *  Herleitung: ein Randstrahl bei Umfangswinkel th liegt im Kamerabild bei
 *  d ~ B * (sin th, cos th) mit B = [[ex.R, ez.R], [ex.U, ez.U]]; im Motiv
 *  gehoert er nach (sin th, -cos th) (gobo_textures.js: Canvas-Winkel
 *  pi/2 - th, v nach oben). Also Motiv = diag(1,-1) * B^T * d — eine reine
 *  Drehung, weil (ex, ez) und (R, U) entgegengesetzt orientiert sind. Beide
 *  Schaetzungen je Eintrag werden gemittelt (Kegelachse und Blickrichtung
 *  weichen um den Linsen-Vorsprung minimal ab).
 */
export function goboDrehung(exR, exU, ezR, ezU) {
  const c = (exR - ezU) / 2, s = -(exU + ezR) / 2;
  const l = Math.hypot(c, s);
  if (!(l > 1e-9)) return [1, 0];
  return [c / l, s / l];
}

// ── Zustand + Installation ──────────────────────────────────────────────────
let _aktiv = false;
let _index = {};
let _gepatcht = 0;          // wie oft lief der Hook (Diagnose)
let _chunk = null;
const _uniforms = {
  lightosGoboMap: { value: null },
  lightosGoboParam: { value: [] },
  // VIZ-102: [quadrat, reich] je Schatten-Licht (goboFern), flach abgelegt
  // (2 Zahlen je Licht); GOBO_FERN_AUS = keine Grenze.
  lightosGoboFern: { value: [] },
};

// EINE Funktion fuer alle Materialien: three nimmt `onBeforeCompile.toString()`
// in den Programmschluessel — gleiche Funktion, gleiche Programme wie vorher.
function lightosGoboHook(shader) {
  const fs = patchFragmentShader(shader.fragmentShader, _chunk);
  if (fs === null) return;
  shader.fragmentShader = fs;
  shader.uniforms.lightosGoboMap = _uniforms.lightosGoboMap;
  shader.uniforms.lightosGoboParam = _uniforms.lightosGoboParam;
  shader.uniforms.lightosGoboFern = _uniforms.lightosGoboFern;
  _gepatcht += 1;
}

/** Projektion einschalten — EINMAL beim Start, vor dem ersten Bild.
 *
 *  @param opt.materialKlassen  beleuchtete Materialklassen (MeshStandardMaterial)
 *  @param opt.lichtChunk       THREE.ShaderChunk.lights_fragment_begin
 *  @param opt.Vector4          THREE.Vector4
 *  @param opt.atlas            Textur des Motiv-Atlas
 *  @param opt.index            { stil: kachelNr }
 *  @returns true, wenn installiert. false laesst alles wie vor VIZ-96.
 */
export function installGoboProjektion(opt) {
  if (_aktiv) return true;
  const o = opt || {};
  if (!o.atlas || !o.Vector4 || !o.materialKlassen || !o.materialKlassen.length) return false;
  if (patchLichtChunk(o.lichtChunk) === null) return false;
  _chunk = o.lichtChunk;
  _index = Object.assign({}, o.index);
  _uniforms.lightosGoboMap.value = o.atlas;
  const werte = [];
  for (let i = 0; i < GOBO_MAX_LICHTER; i++) werte.push(new o.Vector4(0, 1, 0, 0));
  _uniforms.lightosGoboParam.value = werte;
  const fern = [];
  for (let i = 0; i < 2 * GOBO_MAX_LICHTER; i++) fern.push(GOBO_FERN_AUS);
  _uniforms.lightosGoboFern.value = fern;
  for (const klasse of o.materialKlassen) klasse.prototype.onBeforeCompile = lightosGoboHook;
  _aktiv = true;
  return true;
}

export function goboProjektionAktiv() { return _aktiv; }

/** Kachel-Nummer eines Stils, -1 = kein Motiv (offen/unbekannt). */
export function goboKachel(stil) {
  const nr = _index[String(stil || '')];
  return (typeof nr === 'number') ? nr : -1;
}

/** Maske des Schatten-Lichts `i` setzen (nur Uniform-Werte).
 *  @param an     0..1 — Anteil der Maske (0 = Licht unveraendert)
 *  @param cs,sn  cos/sin der Drehung, bereits mit dem Massstab multipliziert
 */
export function setzeGoboLicht(i, an, cs, sn, kachel) {
  const v = _uniforms.lightosGoboParam.value[i];
  if (!v) return false;
  v.set(an, cs, sn, kachel);
  return true;
}

export function loescheGoboLicht(i) {
  const v = _uniforms.lightosGoboParam.value[i];
  if (v && v.x !== 0) v.set(0, 1, 0, 0);
  setzeGoboFern(i, null);
}

/** VIZ-102: Reichweiten-Paar des Schatten-Lichts `i` (Ergebnis von goboFern);
 *  null = keine Grenze. */
export function setzeGoboFern(i, fern) {
  const a = _uniforms.lightosGoboFern.value;
  if (!(i >= 0 && 2 * i + 1 < a.length)) return false;
  a[2 * i] = fern ? fern[0] : GOBO_FERN_AUS;
  a[2 * i + 1] = fern ? fern[1] : GOBO_FERN_AUS;
  return true;
}

/** Test-/Diagnose-Seam. */
export function goboProjektionInfo() {
  return {
    aktiv: _aktiv,
    slots: _aktiv ? GOBO_SLOTS : 0,
    hookLaeufe: _gepatcht,
    spalten: GOBO_ATLAS_SPALTEN,
    zeilen: GOBO_ATLAS_ZEILEN,
    index: Object.assign({}, _index),
    param: _uniforms.lightosGoboParam.value.map(v => [v.x, v.y, v.z, v.w]),
    fern: _uniforms.lightosGoboFern.value.filter((v, k) => k % 2 === 0)
      .map((v, k) => [v, _uniforms.lightosGoboFern.value[2 * k + 1]]),
  };
}
