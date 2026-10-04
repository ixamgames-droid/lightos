// VIZ-71: letzter bekannter DMX-Stand je fid — auch fuer Geraete, die es in
// der Szene (noch) nicht gibt.
//
// Warum es das braucht (N1/N2 aus dem VIZ-71-Entwurf):
//  * Geraete-Neubau (`fixtureAdded`/`allFixtures`) und DMX reisen auf
//    VERSCHIEDENEN Wegen: der Bau ueber den Poll (130 ms), DMX seit VIZ-71 per
//    Push (Takt der Qualitaetsstufe). Kam DMX fuer ein noch unbekanntes Geraet
//    an, verpuffte die Zeile — `updateFixture` tut fuer eine unbekannte fid
//    nichts, und Python hielt den Wert trotzdem fuer zugestellt.
//  * `addFixture` setzte beim (Neu-)Bau feste Nullen (dunkel, Pan/Tilt Mitte).
//    Platzieren, Einmessen, Wiedereinblenden, Show-Wechsel: das Geraet blieb
//    dunkel, bis sich sein DMX das naechste Mal aenderte.
// Jetzt merkt sich die Seite den letzten Stand je fid und `addFixture` baut
// damit statt mit Nullen.
//
// Bewusst ein import-freies Blatt (wie render_loop.js): fixtures.js liest den
// Cache beim Bau, dmx_apply.js schreibt ihn — ohne Modul-Zyklus.
"use strict";

export const DMX_CACHE_MAX = 2048;

// fid (String) -> { seq: number|null, d: payload }
export const dmxCache = new Map();

export function cachedDmx(fid) {
  const e = dmxCache.get(String(fid));
  return e ? e.d : null;
}

export function cachedSeq(fid) {
  const e = dmxCache.get(String(fid));
  return e ? e.seq : null;
}

export function rememberDmx(fid, seq, d) {
  const key = String(fid);
  // delete + set: die Map-Reihenfolge ist damit „zuletzt beschrieben zuletzt"
  // und der Deckel unten wirft wirklich die AELTESTEN Eintraege.
  dmxCache.delete(key);
  dmxCache.set(key, { seq: (seq === undefined) ? null : seq, d });
  if (dmxCache.size > DMX_CACHE_MAX) {
    const zuViel = dmxCache.size - DMX_CACHE_MAX;
    let i = 0;
    for (const k of dmxCache.keys()) {
      if (i++ >= zuViel) break;
      dmxCache.delete(k);
    }
  }
}

// Das Geraet ist aus der Show entfernt (nicht nur neu gebaut!): Stand vergessen.
// `addFixture` ruft intern `removeFixture` — dort darf das NICHT passieren,
// sonst waere der Neubau wieder dunkel. Darum ein eigener Aufruf.
export function forgetDmx(fid) {
  dmxCache.delete(String(fid));
}

// Eine VOLLE Geraeteliste ist angekommen: Eintraege fuer fids, die es darin
// nicht gibt, sind Reste (alte Show, entpatchte Geraete).
export function pruneDmxCache(fids) {
  const behalten = new Set((fids || []).map(f => String(f)));
  for (const k of Array.from(dmxCache.keys())) {
    if (!behalten.has(k)) dmxCache.delete(k);
  }
}

export function dmxCacheInfo() {
  return { size: dmxCache.size, max: DMX_CACHE_MAX };
}
