// Compatibility routes now enter one studio instead of creating page/iframe shells.
(() => {
  'use strict';
  const modes = new Set(['orbit','circle','rings','graph','areas','links','timeline','matrix','holo','pyramid']);
  const requested = document.body.dataset.projection;
  const target = requested === 'operations'
    ? '../VAYU-Knowledge-Sphere-Live.html?workspace=today'
    : requested === 'analytics'
      ? '../VAYU-Knowledge-Sphere-Live.html?workspace=analytics'
      : '../VYNDI_VAOS_Neural_Schema_Gesture_Hologram_v4.html?projection=' + (modes.has(requested) ? requested : 'graph');
  window.location.replace(target);
})();
