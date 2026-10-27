/* Adapted from Nate Herk's scroll-craft engine (MIT, 2026).
 * See vendor/scroll-craft/LICENSE and UPSTREAM.md.
 * Flow parallax, one-time entry reveals, and interpolated pointer tilt only.
 * All measurements and observers use Spark's nested scroller, not the window.
 */
const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

export function mountScrollCraft(root, scroller) {
    const view = root.ownerDocument.defaultView;
    const preference = view.matchMedia('(prefers-reduced-motion: reduce)');
    const acts = [...root.querySelectorAll('[data-sc-act]')].map(element => ({
        element, top:0, height:0,
        layers:[...element.querySelectorAll('[data-sc-parallax]')].map(layer => ({
            element:layer, rate:clamp(Number(layer.dataset.scParallax) || 0, -2, 2),
        })),
    }));
    const tilts = [...root.querySelectorAll('[data-sc-tilt]')].map(element => ({
        element, max:clamp(Number(element.dataset.scTilt) || 4, 0, 8), x:0,y:0,tx:0,ty:0,
    }));
    const reveals = [...root.querySelectorAll('[data-sc-in]')];
    const savedTransforms = new Map([...acts.flatMap(act => act.layers), ...tilts]
        .map(layer => [layer.element, layer.element.style.transform]));
    let frame = 0, dead = false, measure = true, read = true;
    let observer, resizeObserver;
    const listeners = [];
    const on = (target, event, callback, options) => {
        target.addEventListener(event, callback, options);
        listeners.push(() => target.removeEventListener(event, callback, options));
    };
    const reset = () => {
        for (const [element, transform] of savedTransforms) element.style.transform = transform;
        for (const tilt of tilts) tilt.x = tilt.y = tilt.tx = tilt.ty = 0;
    };
    const schedule = () => {
        if (!dead && !frame && !view.document.hidden && !preference.matches) frame = view.requestAnimationFrame(paint);
    };
    function paint() {
        frame = 0;
        if (dead || preference.matches || view.document.hidden) return;
        const viewport = scroller.clientHeight;
        if (measure) {
            const top = scroller.getBoundingClientRect().top;
            for (const act of acts) {
                const bounds = act.element.getBoundingClientRect();
                act.top = bounds.top - top + scroller.scrollTop;
                act.height = bounds.height;
            }
            measure = false; read = true;
        }
        if (read) {
            for (const act of acts) {
                const progress = clamp((scroller.scrollTop + viewport - act.top) / Math.max(1, act.height + viewport), 0, 1);
                act.element.style.setProperty('--sc-p', progress.toFixed(4));
                for (const layer of act.layers) {
                    layer.element.style.transform = `translate3d(0,${(layer.rate * (progress - .5) * 100).toFixed(2)}px,0)`;
                }
            }
            read = false;
        }
        let moving = false;
        for (const tilt of tilts) {
            tilt.x += (tilt.tx - tilt.x) * .14;
            tilt.y += (tilt.ty - tilt.y) * .14;
            const unsettled = Math.abs(tilt.tx - tilt.x) + Math.abs(tilt.ty - tilt.y) > .005;
            if (!unsettled) {tilt.x = tilt.tx; tilt.y = tilt.ty;}
            tilt.element.style.transform = `perspective(1100px) rotateX(${tilt.x.toFixed(3)}deg) rotateY(${tilt.y.toFixed(3)}deg)`;
            moving ||= unsettled;
        }
        if (moving) schedule();
    }
    on(scroller, 'scroll', () => {read = true; schedule();}, {passive:true});
    on(root, 'pointermove', event => {
        if (preference.matches || event.pointerType !== 'mouse') return;
        const viewport = scroller.getBoundingClientRect();
        for (const tilt of tilts) {
            const bounds = tilt.element.getBoundingClientRect();
            const nx = (event.clientX - bounds.left - bounds.width / 2) / Math.max(1, bounds.width / 2);
            const ny = (event.clientY - bounds.top - bounds.height / 2) / Math.max(1, bounds.height / 2);
            const near = Math.abs(nx) < 1.8 && Math.abs(ny) < 1.8 && bounds.bottom > viewport.top && bounds.top < viewport.bottom;
            tilt.tx = near ? -clamp(ny,-1,1) * tilt.max : 0;
            tilt.ty = near ? clamp(nx,-1,1) * tilt.max : 0;
        }
        schedule();
    }, {passive:true});
    on(root, 'pointerleave', () => {for (const tilt of tilts) tilt.tx = tilt.ty = 0; schedule();});
    on(root, 'focusin', event => {
        const element = event.target.closest?.('[data-sc-in]');
        if (element && root.contains(element)) element.classList.add('sc-in');
    });
    on(preference, 'change', () => {
        if (preference.matches) {
            if (frame) view.cancelAnimationFrame(frame);
            frame = 0; reset();
            for (const element of reveals) element.classList.add('sc-in');
        } else {measure = true; schedule();}
    });
    on(view.document, 'visibilitychange', () => {
        if (view.document.hidden && frame) {view.cancelAnimationFrame(frame); frame = 0;}
        else {measure = true; schedule();}
    });
    const resize = () => {measure = true; schedule();};
    on(view, 'resize', resize, {passive:true});
    if (view.ResizeObserver) {
        resizeObserver = new view.ResizeObserver(resize);
        resizeObserver.observe(scroller); resizeObserver.observe(root);
    }
    if (!preference.matches && view.IntersectionObserver) {
        root.setAttribute('data-sc-mounted', '');
        observer = new view.IntersectionObserver(entries => {
            if (dead) return;
            for (const entry of entries) if (entry.isIntersecting) {
                entry.target.classList.add('sc-in'); observer.unobserve(entry.target);
            }
        }, {root:scroller, rootMargin:'0px 0px -5% 0px',threshold:.05});
        for (const element of reveals) observer.observe(element);
    } else for (const element of reveals) element.classList.add('sc-in');
    schedule();
    return {
        refresh:resize,
        destroy() {
            if (dead) return;
            dead = true;
            for (const remove of listeners) remove();
            if (frame) view.cancelAnimationFrame(frame);
            observer?.disconnect(); resizeObserver?.disconnect();
            reset(); root.removeAttribute('data-sc-mounted');
            for (const act of acts) act.element.style.removeProperty('--sc-p');
        },
    };
}
