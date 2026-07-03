// VIZ-13 Schritt 3a-1: minimales Blatt-Modul ohne eigene Abhaengigkeiten.
// Zweck: NUR belegen, dass ein importiertes ES-Modul in der echten
// Produktiv-Ladekonstellation (qwebchannel.js qrc-Script + three_local.js
// klassisch + <script type="module">) ausgefuehrt wird UND Zugriff auf das
// von three_local.js gesetzte globale `window.THREE` hat (Ladereihenfolge-
// Beleg fuer Weg A aus dem Design-Dokument, Abschnitt (b)).
//
// Bewusst KEIN Rendering, KEIN Renderer-Objekt: WebGL ist im offscreen-
// Testlauf (QT_QPA_PLATFORM=offscreen) nicht verfuegbar - der Beleg darf nur
// den THREE-Namespace anfassen (siehe Auftrag, "Belegt darf keinen Renderer
// instanziieren").
export function probeThreeNamespace() {
  const hasThree = (typeof window !== 'undefined') && !!window.THREE;
  const hasVector3 = hasThree && typeof window.THREE.Vector3 === 'function';
  return { hasThree, hasVector3 };
}
