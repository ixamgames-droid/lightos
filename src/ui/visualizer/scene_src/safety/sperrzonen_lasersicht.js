// LAS-32 (Slice S1): SICHT DES LASERS als kleines Fenster im 3D.
//
// Ein Bild-im-Bild aus dem Austrittsfenster heraus: das Maximalfeld als
// Rechteck, die Sperrzonen als dunkle Flecken darin — so, wie man eine Blende
// einstellen wuerde. NUR ANZEIGE: das Bild selbst faengt keine Eingabe
// (pointer-events: none) und schaltet nichts am Laser. Bedienbar sind allein
// die kleinen Knoepfe in der Kopfzeile (Laser waehlen, Fenster schliessen)
// und — bei geschlossenem Fenster — der Knopf „Sicht des Lasers", der es
// wieder oeffnet.
//
// Gezeichnet wird mit 2D-Canvas, nicht mit einer zweiten 3D-Kamera: die
// Bildebene ist die Tangens-Ebene des Lasers (u = rechts, v = oben), in der
// das Feld exakt ein Rechteck ist. Alle Punkte kommen schon in
// Laser-Koordinaten an (sperrzonen.js), hier wird nur projiziert.
import { schneide, blick } from './sperrzonen_geo.js';

const BREITE = 420, HOEHE = 362;
const RAND = 10, KOPF = 32, FUSS = 22;
const NAH = 0.05;
/** Bis zu so vielen Lasern je ein Umschalter, darueber „‹ ›". */
const SCHALTER_MAX = 3;

let _kasten = null, _leinwand = null, _leiste = null, _zeiger = null;
let _muster = null, _dpr = 1;
let _letzte = null;
let _leisteSig = '';
let _bedienung = { an: null, waehle: null };

/** Rueckrufe der Knoepfe: { an(bool), waehle(fid) } — gesetzt von sperrzonen.js. */
export function lasersichtBedienung(b) {
  _bedienung = Object.assign({ an: null, waehle: null }, b || {});
}

/** Ein Knopf, dessen Klick NICHT in die 3D-Szene durchfaellt. */
function knopf(text, titel, aktiv, klick) {
  const b = document.createElement('button');
  b.type = 'button';
  b.textContent = text;
  b.title = titel;
  b.style.cssText = [
    'pointer-events:auto', 'cursor:pointer', 'font:bold 11px sans-serif',
    'height:24px', 'min-width:26px', 'padding:0 8px', 'margin:0', 'border-radius:4px',
    'border:1px solid rgba(255,176,0,0.65)',
    'background:' + (aktiv ? '#ffb000' : 'rgba(34,38,48,0.96)'),
    'color:' + (aktiv ? '#1a1400' : '#ffcf70'),
  ].join(';');
  for (const ev of ['pointerdown', 'pointerup', 'mousedown', 'mouseup', 'touchstart',
                    'touchend', 'dblclick', 'wheel', 'contextmenu']) {
    b.addEventListener(ev, e => e.stopPropagation());
  }
  b.addEventListener('click', e => {
    e.stopPropagation();
    e.preventDefault();
    try { klick(); } catch (err) { console.log('sperrzonen: Lasersicht-Knopf', err); }
  });
  return b;
}

function anlegen() {
  if (_kasten) return;
  _kasten = document.createElement('div');
  _kasten.id = 'sperrzonen-lasersicht';
  _kasten.style.cssText = [
    'position:absolute', 'left:12px', 'bottom:40px', 'z-index:6',
    'pointer-events:none', 'display:none',
    'background:rgba(10,12,18,0.90)', 'border:1px solid rgba(255,176,0,0.75)',
    'border-radius:6px', 'box-shadow:0 2px 14px rgba(0,0,0,0.6)',
  ].join(';');
  _leinwand = document.createElement('canvas');
  const dpr = Math.max(1, Math.min(3, window.devicePixelRatio || 1));
  _leinwand.width = Math.round(BREITE * dpr);
  _leinwand.height = Math.round(HOEHE * dpr);
  _leinwand.style.cssText = `display:block;width:${BREITE}px;height:${HOEHE}px`;
  _dpr = dpr;
  _kasten.appendChild(_leinwand);
  _leiste = document.createElement('div');
  _leiste.style.cssText = 'position:absolute;top:4px;right:6px;display:flex;gap:4px;'
                          + 'align-items:center;pointer-events:none';
  _kasten.appendChild(_leiste);
  document.body.appendChild(_kasten);
}

function zeigerAnlegen() {
  if (_zeiger) return;
  _zeiger = knopf('Sicht des Lasers ▸', 'Fenster „Sicht des Lasers" einblenden', false,
                  () => { if (_bedienung.an) _bedienung.an(true); });
  _zeiger.id = 'sperrzonen-lasersicht-auf';
  _zeiger.style.position = 'absolute';
  _zeiger.style.left = '12px';
  _zeiger.style.bottom = '40px';
  _zeiger.style.zIndex = '6';
  _zeiger.style.height = '26px';
  _zeiger.style.display = 'none';
  _zeiger.style.boxShadow = '0 2px 10px rgba(0,0,0,0.5)';
  document.body.appendChild(_zeiger);
}

/** Kopfzeile: Umschalter je Laser (nur bei mehreren) und das Schliessen-Kreuz. */
function leisteFuellen(d) {
  const laser = d.laser || [d.fid];
  const sig = laser.join(',') + '|' + d.fid;
  if (sig === _leisteSig) return;
  _leisteSig = sig;
  while (_leiste.firstChild) _leiste.removeChild(_leiste.firstChild);
  const waehle = fid => () => { if (_bedienung.waehle) _bedienung.waehle(fid); };
  if (laser.length > 1 && laser.length <= SCHALTER_MAX) {
    for (const fid of laser) {
      const b = knopf('Laser ' + fid, 'Sicht von Laser ' + fid, fid === d.fid, waehle(fid));
      b.dataset.fid = String(fid);
      _leiste.appendChild(b);
    }
  } else if (laser.length > SCHALTER_MAX) {
    const i = Math.max(0, laser.indexOf(d.fid)), n = laser.length;
    const vor = knopf('‹', 'voriger Laser', false, waehle(laser[(i + n - 1) % n]));
    vor.dataset.fid = String(laser[(i + n - 1) % n]);
    const nach = knopf('›', 'nächster Laser', false, waehle(laser[(i + 1) % n]));
    nach.dataset.fid = String(laser[(i + 1) % n]);
    const wo = document.createElement('span');
    wo.textContent = (i + 1) + '/' + n;
    wo.style.cssText = 'font:11px sans-serif;color:#ffcf70;padding:0 2px';
    _leiste.appendChild(vor);
    _leiste.appendChild(wo);
    _leiste.appendChild(nach);
  }
  const zu = knopf('✕', 'Fenster ausblenden (wieder einblenden: Knopf „Sicht des Lasers" '
                        + 'unten links oder im Sperrzonen-Fenster)', false,
                   () => { if (_bedienung.an) _bedienung.an(false); });
  zu.id = 'sperrzonen-lasersicht-zu';
  _leiste.appendChild(zu);
}

function schraffur(g) {
  if (_muster) return _muster;
  const c = document.createElement('canvas');
  c.width = c.height = 8;
  const m = c.getContext('2d');
  m.fillStyle = 'rgba(255,40,40,0.55)';
  m.fillRect(0, 0, 8, 8);
  m.strokeStyle = 'rgba(255,225,225,0.95)';
  m.lineWidth = 2;
  for (const d of [-8, 0, 8]) {
    m.beginPath(); m.moveTo(d, 8); m.lineTo(d + 8, 0); m.stroke();
  }
  _muster = g.createPattern(c, 'repeat');
  return _muster;
}

function vorn(polygon) {
  return schneide(polygon, p => NAH - p[2]);
}

/**
 * @param {?object} d  null = Fenster ausblenden. Sonst
 *   { fid, laser:[fid…], titel, tan:{l,r,o,u}, tanOhne:{l,r,o,u},
 *     winkel:{links,rechts,oben,unten,zuschlag},
 *     zonen:[{name, erreicht, flaechen:[polygon]}], linien:[[a,b]], koerper:[[a,b]] }
 *   — alle Punkte in Laser-Koordinaten.
 * @param {boolean} moeglich  es gibt etwas zu zeigen (pruefbarer Laser UND
 *   Zone): bei ausgeblendetem Fenster steht dann der Knopf zum Einblenden da.
 */
export function zeichneLasersicht(d, moeglich) {
  _letzte = d ? { sichtbar: true, titel: d.titel, fid: d.fid, laser: (d.laser || []).slice(),
                  zonen: d.zonen.map(z => z.name),
                  erreicht: d.zonen.filter(z => z.erreicht).map(z => z.name) }
              : { sichtbar: false };
  if (!d && moeglich) zeigerAnlegen();
  if (_zeiger) _zeiger.style.display = (!d && moeglich) ? 'block' : 'none';
  if (!d) {
    if (_kasten) _kasten.style.display = 'none';
    return;
  }
  anlegen();
  leisteFuellen(d);
  _kasten.style.display = 'block';
  const g = _leinwand.getContext('2d');
  const dpr = _dpr;
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, BREITE, HOEHE);

  const t = d.tan;
  const px = RAND, py = KOPF, pw = BREITE - 2 * RAND, ph = HOEHE - KOPF - FUSS;
  // Massstab: Feld mit gut einem Drittel Luft rundherum.
  const fb = t.l + t.r, fh = t.o + t.u;
  const k = Math.min(pw / (fb * 1.75), ph / (fh * 1.75));
  const mu = (t.r - t.l) / 2, mv = (t.o - t.u) / 2;       // Feldmitte
  const X = u => px + pw / 2 + (u - mu) * k;
  const Y = v => py + ph / 2 - (v - mv) * k;
  const weg = pts => {
    g.beginPath();
    pts.forEach((p, i) => { const b = blick(p); if (i) g.lineTo(X(b[0]), Y(b[1])); else g.moveTo(X(b[0]), Y(b[1])); });
    g.closePath();
  };

  // Kopf
  g.font = 'bold 12px sans-serif';
  g.textBaseline = 'middle';
  g.textAlign = 'left';
  g.fillStyle = '#ffb000';
  g.fillText(d.titel, RAND, KOPF / 2 + 1);
  const erreicht = d.zonen.filter(z => z.erreicht).map(z => z.name);

  g.save();
  g.beginPath();
  g.rect(px, py, pw, ph);
  g.clip();
  g.fillStyle = '#05070b';
  g.fillRect(px, py, pw, ph);

  // Boden-Raster und Buehnenkoerper: nur zur Orientierung.
  const strecken = (liste, farbe, breite) => {
    g.strokeStyle = farbe;
    g.lineWidth = breite;
    g.beginPath();
    for (const s of liste) {
      const v = vorn(s);
      if (v.length < 2) continue;
      const a = blick(v[0]), b = blick(v[1]);
      g.moveTo(X(a[0]), Y(a[1]));
      g.lineTo(X(b[0]), Y(b[1]));
    }
    g.stroke();
  };
  strecken(d.linien || [], 'rgba(150,170,210,0.16)', 1);
  strecken(d.koerper || [], 'rgba(190,200,220,0.42)', 1);

  // Zonen: dunkle Flecken …
  const feldWeg = () => {
    g.beginPath();
    g.rect(X(-t.l), Y(t.o), (t.l + t.r) * k, (t.o + t.u) * k);
  };
  const schilder = [];
  for (const z of d.zonen) {
    let su = 0, sv = 0, n = 0;
    const sichtbar = z.flaechen.map(vorn).filter(p => p.length >= 3);
    g.fillStyle = 'rgba(120,10,10,0.50)';
    g.strokeStyle = 'rgba(255,90,90,0.9)';
    g.lineWidth = 1;
    for (const p of sichtbar) {
      weg(p); g.fill(); g.stroke();
      for (const q of p) {
        const b = blick(q);
        su += Math.max(mu - pw / 2 / k, Math.min(mu + pw / 2 / k, b[0]));
        sv += Math.max(mv - ph / 2 / k, Math.min(mv + ph / 2 / k, b[1]));
        n++;
      }
    }
    // … und der Teil IM Feld kraeftig schraffiert.
    if (sichtbar.length) {
      g.save();
      feldWeg(); g.clip();
      g.fillStyle = schraffur(g);
      for (const p of sichtbar) { weg(p); g.fill(); }
      g.restore();
    }
    if (n) schilder.push({ name: z.name, x: X(su / n), y: Y(sv / n), erreicht: z.erreicht });
  }

  // Feld: aussen = mit Zuschlag (damit wird gerechnet), innen = Randwinkel.
  const o = d.tanOhne;
  g.setLineDash([5, 4]);
  g.strokeStyle = 'rgba(255,176,0,0.75)';
  g.lineWidth = 1;
  g.strokeRect(X(-o.l), Y(o.o), (o.l + o.r) * k, (o.o + o.u) * k);
  g.setLineDash([]);
  g.strokeStyle = '#ffb000';
  g.lineWidth = 2;
  g.strokeRect(X(-t.l), Y(t.o), (t.l + t.r) * k, (t.o + t.u) * k);
  // Achse
  g.strokeStyle = 'rgba(255,255,255,0.75)';
  g.lineWidth = 1;
  g.beginPath();
  g.moveTo(X(0) - 6, Y(0)); g.lineTo(X(0) + 6, Y(0));
  g.moveTo(X(0), Y(0) - 6); g.lineTo(X(0), Y(0) + 6);
  g.stroke();

  // Randwinkel an den vier Seiten
  const w = d.winkel || {};
  g.font = '10px sans-serif';
  g.fillStyle = 'rgba(255,200,90,0.95)';
  const grad = v => (Math.round(Number(v) * 10) / 10) + '°';
  g.textBaseline = 'middle';
  const beschrifte = (text, x, y, ausrichtung) => {
    const b = g.measureText(text).width + 6;
    const x0 = ausrichtung === 'center' ? x - b / 2 : (ausrichtung === 'right' ? x - b + 3 : x - 3);
    g.fillStyle = 'rgba(5,7,11,0.78)';
    g.fillRect(x0, y - 7, b, 14);
    g.fillStyle = 'rgba(255,200,90,0.98)';
    g.textAlign = ausrichtung;
    g.fillText(text, x, y + 1);
  };
  beschrifte('oben ' + grad(w.oben), X(mu), Y(t.o) - 10, 'center');
  beschrifte('unten ' + grad(w.unten), X(mu), Y(-t.u) + 11, 'center');
  beschrifte('links ' + grad(w.links), X(-t.l) - 6, Y(mv), 'right');
  beschrifte('rechts ' + grad(w.rechts), X(t.r) + 6, Y(mv), 'left');

  // Zonen-Namen
  g.font = 'bold 11px sans-serif';
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  for (const s of schilder) {
    const b = g.measureText(s.name).width + 10;
    const x = Math.max(px + b / 2 + 2, Math.min(px + pw - b / 2 - 2, s.x));
    const y = Math.max(py + 10, Math.min(py + ph - 10, s.y));
    g.fillStyle = 'rgba(70,0,0,0.92)';
    g.fillRect(x - b / 2, y - 8, b, 16);
    g.strokeStyle = '#ff5050';
    g.lineWidth = 1;
    g.strokeRect(x - b / 2 + 0.5, y - 7.5, b - 1, 15);
    g.fillStyle = '#ffffff';
    g.fillText(s.name, x, y + 1);
  }
  // Befund oben links im Bild (die Kopfzeile gehoert den Knoepfen).
  {
    const text = erreicht.length ? '⚠ im Feld: ' + erreicht.join(', ') : 'keine Zone im Feld';
    g.font = 'bold 12px sans-serif';
    g.textAlign = 'left';
    g.textBaseline = 'middle';
    const b = Math.min(pw - 8, g.measureText(text).width + 14);
    g.fillStyle = erreicht.length ? 'rgba(110,0,0,0.92)' : 'rgba(20,24,30,0.88)';
    g.fillRect(px + 4, py + 4, b, 20);
    g.fillStyle = erreicht.length ? '#ffd0d0' : '#b9c4cf';
    g.fillText(text, px + 11, py + 15, b - 12);
  }
  g.restore();
  g.strokeStyle = 'rgba(255,255,255,0.18)';
  g.lineWidth = 1;
  g.strokeRect(px + 0.5, py + 0.5, pw - 1, ph - 1);

  // Fuss
  g.font = '10px sans-serif';
  g.textBaseline = 'middle';
  g.textAlign = 'left';
  g.fillStyle = 'rgba(200,205,215,0.85)';
  g.fillText('gelb: Feld + ' + grad(w.zuschlag) + ' Zuschlag · gestrichelt: Randwinkel',
             RAND, HOEHE - FUSS / 2);
  g.textAlign = 'right';
  g.fillStyle = '#ffcc00';
  g.fillText('Nur Anzeige', BREITE - RAND, HOEHE - FUSS / 2);
}

/** Test-/Diagnose-Seam. */
export function lasersichtInfo() {
  const sichtbar = !!(_kasten && _kasten.style.display !== 'none');
  return Object.assign({}, _letzte || { sichtbar: false }, {
    sichtbar,
    faengtEingabe: !!(_kasten && _kasten.style.pointerEvents !== 'none'),
    breite: _leinwand ? _leinwand.width : 0,
    knopfAuf: !!(_zeiger && _zeiger.style.display !== 'none'),
    schalter: (sichtbar && _leiste)
      ? Array.from(_leiste.querySelectorAll('button[data-fid]')).map(b => Number(b.dataset.fid))
      : [],
  });
}
