/** Decorative mouse glow. Keep native cursors and leave input handling to the app. */
export function mountPointerGlow() {
  const preference = window.matchMedia('(any-hover: hover) and (any-pointer: fine) and (prefers-reduced-motion: no-preference)');
  const glow = document.createElement('div');
  glow.className = 'workspace-pointer-glow';
  glow.setAttribute('aria-hidden', 'true');

  let frame = 0;
  let x = 0;
  let y = 0;

  function hide() {
    if (frame) window.cancelAnimationFrame(frame);
    frame = 0;
    glow.classList.remove('is-visible');
  }

  function move(event) {
    if (event.pointerType !== 'mouse') return hide();
    x = event.clientX;
    y = event.clientY;
    if (frame) return;
    frame = window.requestAnimationFrame(() => {
      frame = 0;
      glow.style.transform = 'translate3d(' + x + 'px,' + y + 'px,0)';
      glow.classList.add('is-visible');
    });
  }

  function detach() {
    hide();
    window.removeEventListener('pointermove', move);
    window.removeEventListener('blur', hide);
    document.documentElement.removeEventListener('pointerleave', hide);
    document.removeEventListener('visibilitychange', hide);
    glow.remove();
  }

  function update() {
    if (!preference.matches) return detach();
    if (glow.isConnected) return;
    document.body.append(glow);
    window.addEventListener('pointermove', move, { passive: true });
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
