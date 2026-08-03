// VIZ-13 Schritt 3a-2: Wrapper-Modul, das das globale `window.THREE`
// (gesetzt von three_local.js, klassisches UMD-Script r128, geladen VOR
// allen <script type="module">-Modulen - siehe Design-Dokument Abschnitt
// (b) "Weg A") fuer ES-Module importierbar macht.
//
// KEIN Verhalten geaendert: dieses Modul instanziiert nichts, rendert
// nichts, es re-exportiert nur Referenzen auf bereits existierende
// THREE-Klassen/-Konstanten. Faellt `window.THREE` nicht vor dem ersten
// `import` dieses Moduls vorhanden zu sein (falsche Ladereihenfolge), wirft
// die Destrukturierung unten sofort einen TypeError - das ist gewollt
// (Fail-Fast statt stiller `undefined`-Exports).
//
// Named-Export-Menge = exakt die in stage_scene.html genutzte Menge
// (per `grep -oE 'THREE\.[A-Za-z0-9_]+' stage_scene.html | sort -u`
// ermittelt, Stand 3a-2).
//
// ⚠️ GENAU DAS WAR DIE LUECKE (2026-08-03, VIZ-SHIM): die Liste wurde einmal
// aus `stage_scene.html` erhoben und danach nur noch von Hand nachgezogen —
// die Module unter `scene_src/` greift sie nie ab. Ein hier FEHLENDER Name
// wirft nicht, er ist beim Zugriff ueber den Modul-Namespace schlicht
// `undefined`, und `undefined` ist in three ein gueltig aussehender Wert:
//
//   * `PCFShadowMap` fehlte -> `renderer.shadowMap.type = undefined` auf
//     Low-Spec -> Rueckfall auf SHADOWMAP_TYPE_BASIC, also harte Schatten
//     statt der im Code beschriebenen PCF-Filterung.
//   * `BackSide` fehlte -> die Raum-Huelle (VIZ-14) bekam `side: undefined`,
//     three faellt auf `FrontSide` zurueck. Gemessen mit einem Strahl aus der
//     Raumitte: 2 Treffer mit BackSide, **0** ohne. Die Huelle war also von
//     innen unsichtbar — das gesamte Feature war wirkungslos, seit es gebaut
//     wurde. three warnt dabei sogar („'side' parameter is undefined"), nur
//     liest die Warnung im Qt-Log niemand.
//
// Der Fall ist jetzt gegatet: `tests/test_viz_three_shim_complete.py` sammelt
// JEDEN `THREE.<Name>`-Zugriff aus allen Modulen, die dieses Wrapper-Modul
// importieren, und verlangt ihn in der Liste unten. Wer hier etwas ergaenzt,
// braucht nichts weiter zu tun; wer unten etwas BENUTZT ohne es hier
// einzutragen, wird rot.
//
// OBJLoader/ColladaLoader haengen sich (wie die
// Kernklassen) an `window.THREE` - sie werden als eigene klassische
// Scripts VOR three_local.js... nein, NACH three_local.js aber weiterhin
// klassisch (nicht als Modul) geladen (assets/OBJLoader.js,
// assets/ColladaLoader.js, siehe stage_scene.html <head>) und sind daher
// zum Zeitpunkt des ersten Modul-Imports ebenfalls bereits vorhanden.
export default window.THREE;

export const {
  ACESFilmicToneMapping,
  AdditiveBlending,
  AmbientLight,
  BackSide,
  Box3,
  BoxGeometry,
  BoxHelper,
  BufferGeometry,
  CanvasTexture,
  CircleGeometry,
  ColladaLoader,
  Color,
  ConeGeometry,
  CylinderGeometry,
  DirectionalLight,
  DoubleSide,
  EdgesGeometry,
  FogExp2,
  GridHelper,
  Group,
  HemisphereLight,
  Line,
  LineBasicMaterial,
  LineLoop,
  LineSegments,
  MathUtils,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  OBJLoader,
  Object3D,
  OrthographicCamera,
  PCFShadowMap,
  PCFSoftShadowMap,
  PerspectiveCamera,
  Plane,
  PlaneGeometry,
  Quaternion,
  Raycaster,
  RingGeometry,
  Scene,
  Sphere,
  SpotLight,
  Sprite,
  SpriteMaterial,
  Vector2,
  Vector3,
  WebGLRenderer,
  sRGBEncoding,
} = window.THREE;
