// VIZ-15 Schritt 2 + VIZ-BEAM-OCCLUSION Teil 3: Optik IM sichtbaren Kegel.
//
// (A) Weicher Kegelrand (Fresnel). Der Kegel ist eine offene Mantelflaeche mit
//     additivem MeshBasicMaterial — von der Seite gesehen war er bis zur
//     Silhouette gleich hell und endete dort mit einer harten Kante. Echtes
//     Licht im Dunst ist in der Mitte am hellsten (der Blick durchquert dort
//     den dicksten Teil des Lichtvolumens) und laeuft zum Rand aus. Der Shader
//     blendet deshalb mit |N·V| (Mantel-Normale gegen Blickrichtung) aus:
//     Mitte voll, Silhouette dunkel. BLICKWINKELABHAENGIG: schaut man laengs
//     in den Strahl (Achse ~ Blickrichtung), ist der Mantel ueberall fast
//     tangential — dort wuerde der Kegel sonst ganz verschwinden. Der Faktor
//     geht mit |A·V|^4 (A = Kegelachse) wieder gegen 1.
//
// (B) Volumen-Schatten im Strahl. Steht ein Buehnenkoerper (Podest, Box,
//     Traverse, Wand) nur TEILWEISE im Kegel, endet der Strahl nicht (das tut
//     er seit Teil 2 nur, wenn die Strahl-MITTE trifft) — der Teil des Kegels
//     hinter dem Koerper leuchtete aber weiter. Jetzt prueft der Fragment-
//     Shader je Bildpunkt des Mantels, ob die Strecke Linse -> Bildpunkt einen
//     der Koerper schneidet; wenn ja, ist der Punkt dunkel.
//
//     Gewaehlter Ansatz: ANALYTISCHER Strahl-Quader-Test (Slab-Test) gegen
//     hoechstens KOERPER_MAX orientierte Quader je Kegel, statt Schattenkarte
//     oder Raymarch. Begruendung:
//       - Eine Schattenkarte je Strahl braucht je Strahl einen eigenen
//         Tiefen-Durchgang der Szene (8 Strahlen = 8 zusaetzliche Durchgaenge
//         je Bild) und je Kegel-Material einen weiteren Sampler — genau die
//         Textur-Einheiten, die das Schatten-Budget (fixtures.js) schon knapp
//         verteilt. Raymarching durch das Volumen braucht ebenso eine
//         Tiefen-/Schattenquelle und viele Schritte je Bildpunkt.
//       - Die Hindernisse SIND Quader (stage_objects.js baut Box-Geometrien;
//         importierte Modelle und Gruppen gehen ueber ihre Huellbox). Der
//         Slab-Test ist exakt, hat keine Aufloesungs-Treppen und kostet je
//         Bildpunkt KOERPER_MAX x ein paar Dutzend Rechenoperationen — ohne
//         Textur, ohne zusaetzlichen Durchgang, ohne neues Programm je Kegel.
//       - Die Kegel-Mantelpunkte stehen fuer das Lichtvolumen dahinter: ist
//         der Mantelpunkt verdeckt, ist es der Strahl an dieser Stelle auch.
//     Harte Obergrenzen: hoechstens `strahlSchatten` Kegel (Stufe Maximal: 8,
//     die hellsten zuerst) und je Kegel KOERPER_MAX = 4 Koerper (die naechsten
//     zur Linse). Alle uebrigen Kegel rechnen den Test nicht (Uniform n = 0,
//     die Schleife bricht vor dem ersten Durchlauf ab).
//     Grenzen: Prisma-Nebenstrahlen teilen das Material des Hauptstrahls und
//     damit dessen Koerperliste; Mehrkopf-Geraete (Bars/Spider) bleiben ohne
//     Volumen-Schatten.
//
// Stufen (scene/quality_tiers.js): `kegelKante` (Hoch/Maximal) und
// `strahlSchatten` (nur Maximal). Ist beides aus (Niedrig), patcht dieses
// Modul NICHTS — der Kegel-Shader ist Zeichen fuer Zeichen der bisherige.
// Die Entscheidung faellt einmal beim Laden (ein Stufenwechsel laedt die
// Szene neu, VIZ-71); zur Laufzeit schalten nur zwei geteilte Uniforms
// (Diagnose-/Test-Schalter `strahlOptikSchalter`).
"use strict";

import * as THREE from '../three/three.js';

export const KOERPER_MAX = 4;

let _kante = false;         // Stufe: Fresnel-Rand einbauen
let _schattenMax = 0;       // Stufe: hoechstens so viele Kegel mit Schatten

// Geteilte Laufzeit-Schalter (1/0) — ein Objekt fuer alle Kegel-Materialien.
const _kanteAn = { value: 1 };
const _schattenAn = { value: 1 };

/** Einmal beim Laden aus dem Stufen-Profil setzen (vor dem ersten Kompilieren). */
export function strahlOptikEinstellen(profil) {
  _kante = !!(profil && profil.kegelKante);
  const n = profil && Number(profil.strahlSchatten);
  _schattenMax = (n > 0) ? Math.floor(n) : 0;
}

export function strahlOptikAktiv() { return _kante || _schattenMax > 0; }

const V_ANKER = '#include <project_vertex>';
const F_ANKER = '#include <tonemapping_fragment>';

const V_KOPF = [
  'varying vec3 vLightosW;', 'varying vec3 vLightosN;',
  'varying vec3 vLightosV;', 'varying vec3 vLightosA;', '',
].join('\n');

const V_ZEILEN = [
  '',
  '\tvLightosW = ( modelMatrix * vec4( transformed, 1.0 ) ).xyz;',
  '\tvLightosN = normalize( normalMatrix * normal );',
  '\tvLightosV = - mvPosition.xyz;',
  '\tvLightosA = normalize( normalMatrix * vec3( 0.0, 1.0, 0.0 ) );',
  '',
].join('\n');

function _fKopf(kante, schatten) {
  const z = [
    'varying vec3 vLightosW;', 'varying vec3 vLightosN;',
    'varying vec3 vLightosV;', 'varying vec3 vLightosA;',
  ];
  if (kante) {
    z.push(
      'uniform float lightosKante;',
      'float lightosKantenFaktor() {',
      '\tvec3 v = normalize( vLightosV );',
      '\tfloat ndv = abs( dot( normalize( vLightosN ), v ) );',
      '\tfloat ax = abs( dot( normalize( vLightosA ), v ) );',
      // |N·V| ist (fuer einen Kreisquerschnitt) genau der Anteil der Weglaenge
      // durch das Lichtvolumen relativ zur Mitte: Mitte 1, Silhouette 0.
      '\tfloat rand = smoothstep( 0.0, 0.9, ndv );',
      '\tfloat laengs = ax * ax; laengs *= laengs;',
      '\treturn mix( 1.0, mix( rand, 1.0, laengs ), lightosKante );',
      '}');
  }
  if (schatten) {
    z.push(
      'uniform float lightosSchattenAn;',
      'uniform float lightosSchattenN;',
      'uniform vec3 lightosQuelle;',
      `uniform mat4 lightosKoerper[ ${KOERPER_MAX} ];`,
      'float lightosSchatten() {',
      '\tif ( lightosSchattenAn * lightosSchattenN < 0.5 ) return 1.0;',
      `\tfor ( int i = 0; i < ${KOERPER_MAX}; i ++ ) {`,
      '\t\tif ( float( i ) >= lightosSchattenN ) break;',
      '\t\tvec3 o = ( lightosKoerper[ i ] * vec4( lightosQuelle, 1.0 ) ).xyz;',
      '\t\tvec3 d = ( lightosKoerper[ i ] * vec4( vLightosW, 1.0 ) ).xyz - o;',
      '\t\td += vec3( 1e-6 ) * ( vec3( 1.0 ) - abs( sign( d ) ) );',
      '\t\tvec3 inv = 1.0 / d;',
      '\t\tvec3 t0 = ( vec3( -1.0 ) - o ) * inv;',
      '\t\tvec3 t1 = ( vec3( 1.0 ) - o ) * inv;',
      '\t\tvec3 tn3 = min( t0, t1 ); vec3 tf3 = max( t0, t1 );',
      '\t\tfloat tn = max( max( tn3.x, tn3.y ), tn3.z );',
      '\t\tfloat tf = min( min( tf3.x, tf3.y ), tf3.z );',
      // Getroffen zwischen Linse und Bildpunkt (knapp davor: der Kegel endet
      // seit Teil 2 auf einer getroffenen Oberseite — dort kein Schatten).
      '\t\tif ( tf > max( tn, 0.0 ) && tn < 0.995 ) return 0.0;',
      '\t}',
      '\treturn 1.0;',
      '}');
  }
  return z.join('\n') + '\n';
}

function _genauEinmal(s, anker) {
  const i = s.indexOf(anker);
  return i >= 0 && s.indexOf(anker, i + anker.length) < 0;
}

/** Vertex- und Fragment-Shader eines Kegels patchen. Rein; liefert null,
 *  wenn nichts zu tun ist oder ein Anker nicht genau einmal vorkommt (anderer
 *  three-Stand) — dann bleibt der Kegel wie bisher. */
export function patchStrahlOptik(vs, fs, kante, schatten) {
  if (!kante && !schatten) return null;
  if (typeof vs !== 'string' || typeof fs !== 'string') return null;
  if (!_genauEinmal(vs, V_ANKER) || !_genauEinmal(fs, F_ANKER)) return null;
  const vi = vs.indexOf(V_ANKER) + V_ANKER.length;
  const vNeu = V_KOPF + vs.slice(0, vi) + V_ZEILEN + vs.slice(vi);
  const faktoren = [];
  if (kante) faktoren.push('lightosKantenFaktor()');
  if (schatten) faktoren.push('lightosSchatten()');
  const zeile = 'gl_FragColor.a *= ' + faktoren.join(' * ') + ';\n\t';
  const fi = fs.indexOf(F_ANKER);
  const fNeu = _fKopf(kante, schatten) + fs.slice(0, fi) + zeile + fs.slice(fi);
  return { vertexShader: vNeu, fragmentShader: fNeu };
}

function _schattenUniforms(mat) {
  if (!mat.userData) mat.userData = {};
  let u = mat.userData.lightosSchatten;
  if (!u) {
    const koerper = [];
    for (let i = 0; i < KOERPER_MAX; i++) koerper.push(new THREE.Matrix4());
    u = {
      n: { value: 0 }, quelle: { value: new THREE.Vector3() }, koerper: { value: koerper },
    };
    mat.userData.lightosSchatten = u;
  }
  return u;
}

/** Aus dem onBeforeCompile-Hook der Kegel (ausbrennen.js) — `mat` ist das
 *  Material (three ruft den Hook als Methode). Vor dem Ausbrenn-Patch, der
 *  denselben Fragment-Anker braucht. */
export function strahlOptikAnwenden(shader, mat) {
  const schatten = _schattenMax > 0 && !!mat;
  const p = patchStrahlOptik(shader.vertexShader, shader.fragmentShader, _kante, schatten);
  if (!p) return;
  shader.vertexShader = p.vertexShader;
  shader.fragmentShader = p.fragmentShader;
  if (_kante) shader.uniforms.lightosKante = _kanteAn;
  if (schatten) {
    const u = _schattenUniforms(mat);
    shader.uniforms.lightosSchattenAn = _schattenAn;
    shader.uniforms.lightosSchattenN = u.n;
    shader.uniforms.lightosQuelle = u.quelle;
    shader.uniforms.lightosKoerper = u.koerper;
  }
}

// ── Volumen-Schatten: Zuteilung je Bild ──────────────────────────────────────
const _a = new THREE.Vector3(), _b = new THREE.Vector3(), _r = new THREE.Vector3();
const _achse = new THREE.Vector3(), _c = new THREE.Vector3(), _w = new THREE.Vector3();
const _box = new THREE.Box3(), _kugel = new THREE.Sphere();
const _m = new THREE.Matrix4(), _s = new THREE.Matrix4();
let _stats = { kegel: 0, koerper: 0, kandidaten: 0 };

/** Kegel-Geometrie in Weltkoordinaten: Linse (Spitze), Achse, Laenge, Radius
 *  am Ende. null = keine Kegel-Geometrie. */
export function kegelLage(cone) {
  const g = cone && cone.geometry && cone.geometry.parameters;
  if (!g || !(g.height > 0)) return null;
  const h = g.height / 2;
  _a.set(0, h, 0).applyMatrix4(cone.matrixWorld);
  _b.set(0, -h, 0).applyMatrix4(cone.matrixWorld);
  _r.set(g.radius || 0, -h, 0).applyMatrix4(cone.matrixWorld);
  const laenge = _a.distanceTo(_b);
  if (!(laenge > 1e-4)) return null;
  return {
    linse: _a.clone(), achse: _b.clone().sub(_a).divideScalar(laenge),
    laenge, radius: _r.distanceTo(_b),
  };
}

// Welt -> Einheitsquader [-1,1]^3 eines Buehnenkoerpers; null = nicht nutzbar.
function _koerperMatrix(mesh, ziel) {
  const geo = mesh.geometry;
  if (mesh.isMesh && geo) {
    if (!geo.boundingBox) geo.computeBoundingBox();
    _box.copy(geo.boundingBox);
    if (_box.isEmpty()) return null;
    _box.getCenter(_c); _box.getSize(_w);
    _w.multiplyScalar(0.5).max(new THREE.Vector3(0.005, 0.005, 0.005));
    _s.makeScale(_w.x, _w.y, _w.z).setPosition(_c);
    _m.multiplyMatrices(mesh.matrixWorld, _s);
  } else {
    _box.setFromObject(mesh);
    if (_box.isEmpty()) return null;
    _box.getCenter(_c); _box.getSize(_w);
    _w.multiplyScalar(0.5).max(new THREE.Vector3(0.005, 0.005, 0.005));
    _m.makeScale(_w.x, _w.y, _w.z).setPosition(_c);
  }
  if (Math.abs(_m.determinant()) < 1e-12) return null;
  return ziel.copy(_m).invert();
}

function _hell(cone) {
  const m = cone && cone.material;
  return (m && m.opacity > 0) ? m.opacity : 0;
}

function _sichtbar(o) {
  for (let p = o; p; p = p.parent) if (!p.visible) return false;
  return true;
}

/** Je Bild vor dem Rendern: den hellsten sichtbaren Kegeln (hoechstens
 *  `strahlSchatten`) die Koerper in ihrem Kegel zuteilen, allen anderen n = 0.
 *  Weltmatrizen muessen aktuell sein (renderFrame: nach prepareShadowMap). */
export function syncStrahlSchatten(fixtures, stageObjects) {
  if (!(_schattenMax > 0)) return;
  const kegel = [];
  for (const fid in fixtures) {
    const f = fixtures[fid];
    const cone = f && f.beam;
    const u = cone && cone.material && cone.material.userData
      && cone.material.userData.lightosSchatten;
    if (!u) continue;
    u.n.value = 0;
    if (_hell(cone) > 0 && _sichtbar(cone)) kegel.push(cone);
  }
  let koerperGesamt = 0, kandidaten = 0;
  kegel.sort((x, y) => _hell(y) - _hell(x));
  const n = Math.min(kegel.length, _schattenMax);
  let belegt = 0;
  for (let k = 0; k < n; k++) {
    const cone = kegel[k];
    const lage = kegelLage(cone);
    if (!lage) continue;
    const tanA = lage.radius / lage.laenge;
    const liste = [];
    for (const id in stageObjects) {
      const so = stageObjects[id];
      const mesh = so && so.mesh;
      // Sichtbarkeit bewusst NICHT pruefen: im Ansehen-Modus versteckt
      // umgebung_merge.js die Einzelkoerper und zeichnet sie zusammengefasst
      // (wie koerperTreffer in builders.js).
      if (!mesh) continue;
      // Grobtest ueber die Huellkugel: liegt sie im Kegel (laengs und quer)?
      if (mesh.isMesh && mesh.geometry) {
        if (!mesh.geometry.boundingSphere) mesh.geometry.computeBoundingSphere();
        _kugel.copy(mesh.geometry.boundingSphere).applyMatrix4(mesh.matrixWorld);
      } else {
        _box.setFromObject(mesh);
        if (_box.isEmpty()) continue;
        _box.getBoundingSphere(_kugel);
      }
      _c.copy(_kugel.center).sub(lage.linse);
      const s = _c.dot(lage.achse);
      const rad = _kugel.radius;
      if (s < -rad || s > lage.laenge + rad) continue;
      const quer = Math.sqrt(Math.max(0, _c.lengthSq() - s * s));
      if (quer > Math.max(0, s) * tanA + rad) continue;
      kandidaten += 1;
      liste.push({ mesh, s });
    }
    if (!liste.length) continue;
    liste.sort((x, y) => x.s - y.s);
    const u = cone.material.userData.lightosSchatten;
    let i = 0;
    for (const e of liste) {
      if (i >= KOERPER_MAX) break;
      const ziel = u.koerper.value[i];
      if (!_koerperMatrix(e.mesh, ziel)) continue;
      // Linse IM Koerper (Geraet haengt in der Traverse): der Koerper
      // verdeckte den ganzen Strahl — er zaehlt nicht.
      _w.copy(lage.linse).applyMatrix4(ziel);
      if (Math.abs(_w.x) <= 1.0 && Math.abs(_w.y) <= 1.0 && Math.abs(_w.z) <= 1.0) continue;
      i += 1;
    }
    if (!i) continue;
    u.quelle.value.copy(lage.linse);
    u.n.value = i;
    koerperGesamt += i;
    belegt += 1;
  }
  _stats = { kegel: belegt, koerper: koerperGesamt, kandidaten };
}

/** Diagnose-/Test-Schalter (Laufzeit, ohne Shader-Neubau). */
export function strahlOptikSchalter(o) {
  if (o && typeof o.kante === 'boolean') _kanteAn.value = o.kante ? 1 : 0;
  if (o && typeof o.schatten === 'boolean') _schattenAn.value = o.schatten ? 1 : 0;
}

export function strahlOptikInfo() {
  return {
    kante: _kante, schattenMax: _schattenMax, koerperMax: KOERPER_MAX,
    kanteAn: _kanteAn.value === 1, schattenAn: _schattenAn.value === 1,
    zuteilung: Object.assign({}, _stats),
  };
}
