// VIZ-104: Strobe im 3D — wann ist ein blitzendes Geraet AN, wann AUS?
//
// Die Lichtdaten kommen nur 15/30/44-mal je Sekunde (quality_tiers.js). Ein
// Strobe mit 20 Hz laesst sich darueber nicht abbilden. Python schickt deshalb
// nur die Blitzfrequenz mit (`strobe_hz` im Payload, 0 = Dauerlicht;
// src/core/strobe.py) und die Szene schaltet selbst im Bildtakt.
//
// Grundsaetze:
//  * In GANZEN BILDERN gerechnet, nicht aus der Uhr abgetastet. Blitzlaenge und
//    Periode sind eine feste Zahl von Bildern (`strobeBilder`), geschaltet wird
//    nach einem BILDZAEHLER. Die erste Sichtprobe (Intel UHD 630) hat gezeigt,
//    was die Abtastung einer Uhr-Phase gegen eine schwankende Bildrate macht:
//    Doppelblitze mit ungleichen Luecken ('..##....##..##....##'), 7-10 statt
//    12 Blitze je Sekunde und ein An-Anteil zwischen 14 und 33 % — eine
//    Schwebung. Im Bildraster gibt es die nicht: die Folge ist exakt periodisch.
//  * Kurzer Blitz: an fuer rund STROBE_TAST (25 %) der Periode, mindestens ein
//    Bild; eine Periode hat mindestens BILDER_JE_BLITZ (3) Bilder — eins an,
//    zwei aus. Halb an/halb aus saehe aus wie ein Blinker.
//  * EIN Zaehler fuer alle Geraete: gleiche Frequenz -> gleiche Periode ->
//    gleiche Phase (sie blitzen gemeinsam); verschiedene Frequenzen laufen
//    unabhaengig. Ein DMX-Update fasst den Zaehler nicht an.
//  * Ehrlich: dargestellt werden hoechstens STROBE_DECKEL_HZ. 10 Hz, weil das
//    bei drei Bildern je Blitz genau 30 Bilder/s braucht — die untere Grenze
//    dessen, was der gemessene Rechner beim Blitzen liefert (34-52 Bilder/s);
//    12 Hz braeuchten 36 und wurden dort nie erreicht. 10 teilt ausserdem 30
//    und 60 glatt. Zwischen diesen Bildraten weicht die gezeigte Frequenz um
//    eine halbe Bildlaenge je Periode ab (`strobeAnzeigeHz` nennt sie).
//  * Die Bildrate, aus der die Periode entsteht, wird ROBUST gemessen und
//    TRAEGE gehalten (`taktZustand`/`taktMessen`, seit der zweiten Sichtprobe,
//    s. u.): eine leicht schwankende Messung oder ein einzelnes langes Bild
//    darf die Periode nicht umschalten — genau das waere wieder ein
//    stolpernder Takt. Und wechselt die Periode doch (echter Wechsel der
//    Bildrate), wird die PHASE mitgenommen (`taktBild`), statt mit
//    'bild % periode' an eine beliebige Stelle zu springen.
//  * Zweite Sichtprobe (Windows x64, RX 580, 60-Hz-Bildschirm): 53-59 Bilder/s
//    beim Blitzen, dazu 1-4 einzelne lange Bilder (33-83 ms) je 8 s. Das
//    gleitende Mittel (`fpsNachfuehren`, Faktor 0,1) machte aus EINEM 66-ms-Bild
//    46 statt 55 Bilder/s, also mehr als TAKT_TRAEGHEIT: die Periode sprang
//    (bei 5 Hz 20 Wechsel in 10 s zwischen 8 und 12 Bildern) und mit ihr die
//    Phase — Muster '###........##..#.............###.###'. Jetzt: gekapptes
//    Mittel ueber die letzten MESS_FENSTER Abstaende (das obere und untere
//    MESS_KAPPEN-Fuenftel faellt weg, ein einzelnes langes Bild — auch zwei,
//    drei dicht hintereinander — zaehlt also gar nicht). Umgeschaltet wird
//    erst, wenn diese Messung ausserhalb der Traegheit liegt, die der
//    neuesten MESS_NEU Abstaende auf derselben Seite und beide sich bis auf
//    MESS_EINIG einig sind (das Fenster hat den neuen Stand dann ganz
//    aufgenommen — sonst gaebe es einen Zwischenwert und gleich den naechsten
//    Wechsel) — und das TAKT_GEDULD-mal in Folge, bei einer kleinen
//    Abweichung (bis TAKT_GROSS) TAKT_GEDULD_KLEIN-mal. Ein echter Wechsel
//    60 -> 30 Bilder/s ist so nach rund 0,8 s uebernommen (30 -> 60 nach rund
//    0,4 s), genau einmal, auf den neuen Wert. Bis dahin laeuft die alte
//    Periode im neuen Bildtempo weiter (ein Abstand wird laenger bzw. kuerzer,
//    keiner doppelt, kein Blitz faellt aus). Zufaellig gemischte kurze und
//    lange Bilder (wie bei der ersten Sichtprobe) schalten so rund zehnmal
//    seltener um als mit dem gleitenden Mittel.
//  * Ein verlorenes Bild (ein langes Bild statt mehrerer kurzer): der Zaehler
//    laeuft je Tick EINS weiter, er wird nicht aus der Uhr nachgefuehrt. Der
//    Blitz kommt dann um die Ueberlaenge dieses einen Bildes spaeter, aber er
//    kommt. Aus der Uhr nachgefuehrt wuerde der Zaehler Bilder ueberspringen;
//    faellt ein An-Bild hinein, fehlt der ganze Blitz (eine Luecke von zwei
//    Perioden) — gemessen an simulierten Folgen in
//    tests/test_viz104_3d_takt_gleichmaessig.py: je Tick hoechstens die
//    Ueberlaenge des langen Bildes Abweichung im Blitzabstand und kein
//    ausgefallener Blitz, aus der Uhr ausgefallene Blitze.
//  * 'weich' (gedaempft): kein An/Aus, sondern ein langsames, flaches Pulsieren
//    (hoechstens WEICH_MAX_HZ, nie dunkler als WEICH_MIN) in WEICH_STUFEN
//    gleich langen Schritten je Welle — acht Aenderungen je Welle, nicht eine
//    je Bild (jede Aenderung kostet ein neu gezeichnetes Bild).
//  * 'aus': Dauerlicht wie vor VIZ-104.
//  * Nur die Helligkeit wird getaktet. Farbe, Dimmerwert und Kopplungen
//    bleiben unberuehrt; Dimmer-Effekte der Engine kommen weiter ueber die
//    Helligkeit und werden hier nicht noch einmal moduliert.
//
// Rein (keine Imports, Bildzaehler, Bildabstaende und Bildrate werden
// hereingereicht): Node-Tests laden das Modul direkt
// (tests/test_viz104_strobe_im_3d.py, tests/test_viz104_3d_takt_gleichmaessig.py). Die
// Konstanten haben ein Gegenstueck in src/core/strobe.py (dieselbe Rechnung
// fuer die 2D-Live-Ansicht) — der Test haelt beide gleich.
"use strict";

export const STROBE_MODI = Object.freeze(['flash', 'soft', 'off']);
export const STROBE_MODUS_VORGABE = 'flash';
/** Anteil der Periode, in dem das Geraet leuchtet (auf ganze Bilder gerundet). */
export const STROBE_TAST = 0.25;
/** Hoechste dargestellte Blitzfrequenz (Hz). */
export const STROBE_DECKEL_HZ = 10;
/** So viele Bilder hat eine Periode mindestens (eins an, der Rest aus). */
export const BILDER_JE_BLITZ = 3;
/** 'weich': hoechste Pulsfrequenz (Hz) und dunkelster Anteil. */
export const WEICH_MAX_HZ = 2;
export const WEICH_MIN = 0.55;
/** Schritte je Welle des weichen Pulsierens (= Aenderungen je Welle). */
export const WEICH_STUFEN = 8;
/** Angenommene Bildrate, bis eine gemessen ist. */
export const FPS_VORGABE = 60;
/** Erst ab dieser Abweichung gilt eine neue Bildrate fuer den Takt. */
export const TAKT_TRAEGHEIT = 0.12;
/** Robuste Messung: so viele letzte Bildabstaende zaehlen ... */
export const MESS_FENSTER = 30;
/** ... davon faellt dieser Anteil oben und unten weg (gekapptes Mittel) ... */
export const MESS_KAPPEN = 0.2;
/** ... und erst ab so vielen Abstaenden gibt es eine Messung. */
export const MESS_MINDESTENS = 10;
/** Die neuesten so vielen Abstaende (ebenso gekappt) muessen den Wechsel bestaetigen ... */
export const MESS_NEU = 12;
/** ... und duerfen vom ganzen Fenster hoechstens um diesen Anteil abweichen. */
export const MESS_EINIG = 0.06;
/** So viele Messungen in Folge muss eine grosse Abweichung (> TAKT_GROSS) anhalten ... */
export const TAKT_GEDULD = 3;
/** ... eine kleine (zwischen TAKT_TRAEGHEIT und TAKT_GROSS) so viele. */
export const TAKT_GEDULD_KLEIN = 30;
export const TAKT_GROSS = 0.25;
/** Ein laengerer Abstand ist eine Pause (Tab im Hintergrund), keine Bildrate. */
export const PAUSE_MS = 500;

export function strobeModus(m) {
  return STROBE_MODI.indexOf(m) >= 0 ? m : STROBE_MODUS_VORGABE;
}

/**
 * Periode und Blitzlaenge in ganzen Bildern: { periode, an }.
 * Zielfrequenz = min(hz, deckel); periode = max(runde(fps / ziel), 3);
 * an = max(1, runde(periode * tast)). Kein Strobe -> { periode: 0, an: 0 }.
 */
export function strobeBilder(hz, fps = FPS_VORGABE, deckelHz = STROBE_DECKEL_HZ,
                             tast = STROBE_TAST) {
  if (!(hz > 0) || !(deckelHz > 0)) return { periode: 0, an: 0 };
  const ziel = Math.min(hz, deckelHz);
  const f = (fps > 0) ? fps : FPS_VORGABE;
  const periode = Math.max(Math.round(f / ziel), BILDER_JE_BLITZ);
  const an = Math.min(periode - 1, Math.max(1, Math.round(periode * tast)));
  return { periode, an };
}

/** Frequenz, die wirklich gezeigt wird: fps / Periode. 0 = kein Strobe. */
export function strobeAnzeigeHz(hz, fps = FPS_VORGABE, deckelHz = STROBE_DECKEL_HZ) {
  const p = strobeBilder(hz, fps, deckelHz).periode;
  return p > 0 ? ((fps > 0) ? fps : FPS_VORGABE) / p : 0;
}

function _rest(bild, periode) {
  const r = Math.floor(bild) % periode;
  return r < 0 ? r + periode : r;
}

/**
 * Die Blitz-Funktion: leuchtet das Geraet im Bild Nummer `bild`?
 * hz <= 0 -> immer an (Dauerlicht).
 */
export function strobeAn(bild, hz, fps = FPS_VORGABE, deckelHz = STROBE_DECKEL_HZ,
                         tast = STROBE_TAST) {
  const b = strobeBilder(hz, fps, deckelHz, tast);
  if (!b.periode) return true;
  return _rest(bild, b.periode) < b.an;
}

/** 'weich': Bilder je Welle — ein Vielfaches von WEICH_STUFEN, nie schneller als WEICH_MAX_HZ. */
export function weichBilder(hz, fps = FPS_VORGABE) {
  if (!(hz > 0)) return 0;
  const h = Math.min(hz, WEICH_MAX_HZ);
  const f = (fps > 0) ? fps : FPS_VORGABE;
  return WEICH_STUFEN * Math.max(1, Math.ceil(f / h / WEICH_STUFEN - 1e-9));
}

/**
 * Helligkeitsfaktor 0..1 je Modus — damit wird die gemeldete Helligkeit des
 * Geraets multipliziert. `bild` = Bildzaehler, `fps` = Bildrate des Takts.
 */
export function strobeFaktor(bild, hz, modus = STROBE_MODUS_VORGABE, fps = FPS_VORGABE) {
  if (!(hz > 0) || modus === 'off') return 1;
  if (modus === 'soft') {
    const periode = weichBilder(hz, fps);
    const schritt = Math.floor(_rest(bild, periode) * WEICH_STUFEN / periode);
    const welle = 0.5 + 0.5 * Math.cos(schritt / WEICH_STUFEN * 2 * Math.PI);
    return WEICH_MIN + (1 - WEICH_MIN) * (Math.round(welle * 1e6) / 1e6);
  }
  return strobeAn(bild, hz, fps) ? 1 : 0;
}

/**
 * (Vor der zweiten Sichtprobe benutzt, bleibt als Vergleich fuer die Tests:
 * ein einzelnes langes Bild verschiebt dieses Mittel um mehr als die
 * Traegheit — s. Kopf. Der Takt laeuft jetzt ueber `taktMessen`.)
 * Geglaettete Bildrate aus dem Abstand zweier Bilder (ms). Gemittelt wird der
 * ABSTAND, nicht sein Kehrwert: wechseln lange und kurze Bilder (ein
 * gezeichnetes Bild dauert laenger als ein uebersprungenes), ergibt nur das
 * die Zahl der Bilder je Sekunde, mit der eine Periode aus N Bildern auch
 * wirklich N / fps Sekunden dauert.
 */
export function fpsNachfuehren(fps, dtMs) {
  if (!(dtMs >= 2 && dtMs <= PAUSE_MS)) return fps;     // Pause/Tab im Hintergrund
  const alt = 1000 / ((fps > 0) ? fps : FPS_VORGABE);
  return 1000 / (alt + (dtMs - alt) * 0.1);
}

/**
 * Bildrate, aus der die Perioden entstehen: folgt der gemessenen erst, wenn
 * sie um mehr als TAKT_TRAEGHEIT abweicht. Sonst bleibt sie stehen — und mit
 * ihr jede Periode.
 */
export function taktFps(takt, fps) {
  if (!(fps > 0)) return (takt > 0) ? takt : FPS_VORGABE;
  if (!(takt > 0)) return fps;
  return Math.abs(fps - takt) > takt * TAKT_TRAEGHEIT ? fps : takt;
}

// ── Robuster Takt (zweite Sichtprobe) ───────────────────────────────────────

/**
 * Bildrate aus einer Liste von Bildabstaenden (ms): gekapptes Mittel — die
 * Abstaende sortiert, oben und unten je MESS_KAPPEN weg, der Rest gemittelt.
 * Gemittelt wird weiter der ABSTAND (s. `fpsNachfuehren`): wechseln lange und
 * kurze Bilder gleichmaessig, bleibt beides im Mittel. 0 = zu wenig Abstaende.
 */
export function fpsRobust(abstaende) {
  return abstaende ? _gekappt(abstaende, 0, []) : 0;
}

// Gekapptes Mittel ueber quelle[von..], sortiert in `puffer` (wird
// wiederverwendet: taktMessen laeuft JEDES Bild, auch ohne Strobe — so
// entsteht dabei kein neues Array). Einfuegesortieren: hoechstens
// MESS_FENSTER Werte, fast schon sortiert.
function _gekappt(quelle, von, puffer) {
  const n = quelle.length - von;
  if (n < MESS_MINDESTENS) return 0;
  puffer.length = n;
  for (let i = 0; i < n; i++) {
    const v = quelle[von + i];
    let j = i - 1;
    while (j >= 0 && puffer[j] > v) { puffer[j + 1] = puffer[j]; j -= 1; }
    puffer[j + 1] = v;
  }
  const k = Math.floor(n * MESS_KAPPEN);
  let summe = 0;
  for (let i = k; i < n - k; i++) summe += puffer[i];
  return 1000 / (summe / (n - 2 * k));
}

/**
 * Zustand des Takts — EINER fuer alle Geraete. `fps` = gemessen, `takt` =
 * daraus traege uebernommen (aus ihm entstehen die Perioden), `wechsel` =
 * Zahl der Takt-Wechsel, `wechselBild` = erstes Bild mit dem neuen Takt,
 * `phasen` = Versatz je Frequenz (s. `taktBild`).
 */
export function taktZustand(fps = FPS_VORGABE) {
  const f = (fps > 0) ? fps : FPS_VORGABE;
  return { abst: [], fps: f, takt: f, geduld: 0, wechsel: 0, wechselBild: 0,
           phasen: Object.create(null), nPhasen: 0, puffer: [] };
}

/**
 * Ein Bildabstand (ms) vor dem Bild Nummer `bild`. Liefert true, wenn der
 * Takt ab diesem Bild ein anderer ist. Pausen (> PAUSE_MS) und Unsinn zaehlen
 * nicht. Umgeschaltet wird erst, wenn die robuste Messung des Fensters und
 * die der neuesten MESS_NEU Abstaende auf derselben Seite um mehr als
 * TAKT_TRAEGHEIT neben dem Takt liegen und sich bis auf MESS_EINIG einig
 * sind — TAKT_GEDULD-mal in Folge (kleine Abweichung: TAKT_GEDULD_KLEIN) —,
 * dann auf die Messung des Fensters.
 */
export function taktMessen(z, dtMs, bild) {
  if (!(dtMs >= 2 && dtMs <= PAUSE_MS)) return false;
  z.abst.push(dtMs);
  if (z.abst.length > MESS_FENSTER) z.abst.shift();
  const fps = _gekappt(z.abst, 0, z.puffer);
  if (!(fps > 0)) return false;
  z.fps = fps;
  const neu = _gekappt(z.abst, Math.max(0, z.abst.length - MESS_NEU), z.puffer);
  const grenze = z.takt * TAKT_TRAEGHEIT;
  const da = fps - z.takt, dn = neu - z.takt;
  if (!(Math.abs(da) > grenze && Math.abs(dn) > grenze && (da > 0) === (dn > 0)
        && Math.abs(fps - neu) <= fps * MESS_EINIG)) {
    z.geduld = 0;
    return false;
  }
  z.geduld += 1;
  const geduld = Math.abs(da) > z.takt * TAKT_GROSS ? TAKT_GEDULD : TAKT_GEDULD_KLEIN;
  if (z.geduld < geduld) return false;
  z.takt = fps;
  z.geduld = 0;
  z.wechsel += 1;
  z.wechselBild = bild;
  return true;
}

const PHASEN_MAX = 256;

function _taktPeriode(hz, modus, fps) {
  return modus === 'soft' ? weichBilder(hz, fps) : strobeBilder(hz, fps).periode;
}

/**
 * Bildnummer, mit der `strobeFaktor` fuer diese Frequenz rechnet: der
 * Zaehler plus ein Versatz je Frequenz. Ohne Takt-Wechsel ist der Versatz 0 —
 * dann gilt wie immer 'bild % periode', und gleiche Frequenz heisst gleiche
 * Phase. Beim Wechsel wird die Phase MITGENOMMEN: wo die alte Periode im Bild
 * `wechselBild` stand (Anteil der Periode), steht die neue auch — kein
 * Doppelblitz, keine Luecke. Der Versatz haengt an der Frequenz, nicht am
 * Geraet: Geraete gleicher Frequenz bleiben gemeinsam in Phase.
 */
export function taktBild(z, bild, hz, modus = STROBE_MODUS_VORGABE) {
  if (!(hz > 0) || modus === 'off') return bild;
  const soft = modus === 'soft';
  const ziel = Math.min(hz, soft ? WEICH_MAX_HZ : STROBE_DECKEL_HZ);
  const schl = (soft ? 's' : 'f') + Math.round(ziel * 1000);
  let e = z.phasen[schl];
  if (!e) {
    // Gleitet die Frequenz (Shutter wird gezogen), entstehen viele Eintraege:
    // ab PHASEN_MAX faengt die Liste neu an (die Phasen starten dann neu).
    if (z.nPhasen >= PHASEN_MAX) { z.phasen = Object.create(null); z.nPhasen = 0; }
    e = z.phasen[schl] = { nr: z.wechsel, takt: z.takt, versatz: 0 };
    z.nPhasen += 1;
  } else if (e.nr !== z.wechsel) {
    const pAlt = _taktPeriode(hz, modus, e.takt);
    const pNeu = _taktPeriode(hz, modus, z.takt);
    const s = z.wechselBild;
    const rAlt = _rest(s + e.versatz, pAlt);
    let rNeu = Math.floor(rAlt * pNeu / pAlt);
    if (!soft) {
      // Rundung: war das Geraet im alten Takt schon AUS, darf es im neuen
      // nicht mitten in der Periode wieder angehen — das waere ein
      // Doppelblitz (z. B. 144 -> 60 bei 2 Hz: 18 an, 1 aus, wieder an).
      const anAlt = strobeBilder(hz, e.takt).an;
      const anNeu = strobeBilder(hz, z.takt).an;
      if (rAlt >= anAlt && rNeu < anNeu) rNeu = anNeu;
    }
    e.versatz = _rest(rNeu - s, pNeu);
    e.nr = z.wechsel;
    e.takt = z.takt;
  }
  return bild + e.versatz;
}

/** `strobeFaktor` im laufenden Takt `z`: Periode aus z.takt, Phase mitgenommen. */
export function taktFaktor(z, bild, hz, modus = STROBE_MODUS_VORGABE) {
  return strobeFaktor(taktBild(z, bild, hz, modus), hz, modus, z.takt);
}
