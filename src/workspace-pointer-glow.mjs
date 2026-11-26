const COLORS = ['#3e82ff', '#569fff', '#69d2e0', '#9877f5', '#bf83f1', '#f4a6aa', '#ffc781'];
const LIFETIME = 480;
const MAX_PARTICLES = 76;
const SPACING = 8;

/** Draw a short, chromatic wake behind the native pointer. */
export function mountPointerGlow() {
  const preference = window.matchMedia(
    '(any-hover: hover) and (any-pointer: fine) and (prefers-reduced-motion: no-preference) and (forced-colors: none)'
  );
  const canvas = document.createElement('canvas');
  canvas.className = 'workspace-pointer-glow';
  canvas.setAttribute('aria-hidden', 'true');
  const context = canvas.getContext('2d');
  if (!context) return () => {};

  const particles = [];
  let last = null;
  let frame = 0;
  let hue = 0;
  let width = 0;
  let height = 0;

  function hide() {
    if (frame) window.cancelAnimationFrame(frame);
    frame = 0;
    particles.length = 0;
    last = null;
    context.clearRect(0, 0, width, height);
  }

  function resize() {
    hide();
    width = window.innerWidth;
    height = window.innerHeight;
    if (!width || !height) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 1.5, Math.sqrt(2304000 / (width * height)));
    canvas.width = Math.ceil(width * ratio);
    canvas.height = Math.ceil(height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
  }

  function paint(now) {
    frame = 0;
    context.clearRect(0, 0, width, height);
    while (particles.length && now - particles[0].time >= LIFETIME) particles.shift();
    for (const particle of particles) {
      const age = Math.max(0, (now - particle.time) / LIFETIME);
      const fade = (1 - age) ** 1.7;
      const drift = age * 19 * particle.side;
      const x = particle.x + particle.nx * drift;
      const y = particle.y + particle.ny * drift;
      context.fillStyle = particle.color;
      context.globalAlpha = fade * 0.12;
      context.beginPath();
      context.ellipse(x, y, 14, 7, particle.angle, 0, Math.PI * 2);
      context.fill();
      context.globalAlpha = fade * 0.85;
      context.beginPath();
      context.ellipse(x, y, 5 + 5 * fade, 1.7 + fade, particle.angle, 0, Math.PI * 2);
      context.fill();
    }
    context.globalAlpha = 1;
    if (particles.length) frame = window.requestAnimationFrame(paint);
  }

  function move(event) {
    if (event.pointerType !== 'mouse') return hide();
    const x = event.clientX;
    const y = event.clientY;
    if (!last) {
      last = { x, y };
      return;
    }
    const dx = x - last.x;
    const dy = y - last.y;
    const distance = Math.hypot(dx, dy);
    if (distance < SPACING) return;
    const count = Math.min(14, Math.floor(distance / SPACING));
    const time = performance.now();
    const angle = Math.atan2(dy, dx);
    for (let index = count; index > 0; index--) {
      const offset = index * SPACING / distance;
      const side = Math.sin(hue * 1.7);
      particles.push({
        x: x - dx * offset, y: y - dy * offset,
        nx: -dy / distance, ny: dx / distance,
        side, angle, time, color: COLORS[hue++ % COLORS.length],
      });
    }
    if (particles.length > MAX_PARTICLES) particles.splice(0, particles.length - MAX_PARTICLES);
    last = { x, y };
    if (!frame) frame = window.requestAnimationFrame(paint);
  }

  function detach() {
    hide();
    window.removeEventListener('pointermove', move);
    window.removeEventListener('resize', resize);
    window.removeEventListener('blur', hide);
    document.documentElement.removeEventListener('pointerleave', hide);
    document.removeEventListener('visibilitychange', hide);
    canvas.remove();
  }

  function update() {
    if (!preference.matches) return detach();
    if (canvas.isConnected) return;
    document.body.append(canvas);
    resize();
    window.addEventListener('pointermove', move, { passive: true });
    window.addEventListener('resize', resize);
    window.addEventListener('blur', hide);
    document.documentElement.addEventListener('pointerleave', hide);
    document.addEventListener('visibilitychange', hide);
  }

  preference.addEventListener('change', update);
  update();
  return () => {
    preference.removeEventListener('change', update);
    detach();
  };
}
