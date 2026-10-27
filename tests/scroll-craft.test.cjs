const test = require('node:test');
const assert = require('node:assert/strict');

class Element extends EventTarget {
    constructor(bounds = {}) {
        super();
        this.bounds = {top:100,left:0,width:400,height:400,bottom:500,...bounds};
        this.dataset = {};
        this.attributes = new Map();
        this.properties = new Map();
        this.classes = new Set();
        this.style = {transform:'',setProperty:(key,value)=>this.properties.set(key,value),removeProperty:key=>this.properties.delete(key)};
        this.classList = {add:name=>this.classes.add(name),contains:name=>this.classes.has(name)};
        this.querySelectorAll = () => [];
    }
    getBoundingClientRect() {return this.bounds;}
    setAttribute(key,value) {this.attributes.set(key,value);}
    removeAttribute(key) {this.attributes.delete(key);}
}

function fixture(reduced = false) {
    const frames = new Map();
    let frameId = 0, frameCount = 0;
    const preference = new EventTarget(); preference.matches = reduced;
    const document = new EventTarget(); document.hidden = false;
    const view = new EventTarget();
    Object.assign(view, {
        document, scrollY:9999, innerHeight:1000,
        matchMedia:()=>preference,
        requestAnimationFrame:callback=>{frames.set(++frameId,callback);return frameId;},
        cancelAnimationFrame:id=>frames.delete(id),
    });
    const observers = [];
    class Observer {
        constructor(callback, options) {this.callback=callback;this.options=options;this.nodes=new Set();observers.push(this);}
        observe(node) {this.nodes.add(node);}
        unobserve(node) {this.nodes.delete(node);}
        disconnect() {this.nodes.clear();this.disconnected=true;}
    }
    view.IntersectionObserver = Observer;
    view.ResizeObserver = Observer;
    const root = new Element(); root.ownerDocument = {defaultView:view};
    const scroller = new Element({height:600,bottom:700});
    scroller.clientHeight = 600; scroller.scrollTop = 0;
    const act = new Element();
    const layer = new Element(); layer.dataset.scParallax = '1'; layer.style.transform = 'rotate(2deg)';
    const tilt = new Element(); tilt.dataset.scTilt = '5';
    const reveal = new Element();
    act.querySelectorAll = selector => selector === '[data-sc-parallax]' ? [layer] : [];
    root.querySelectorAll = selector => ({'[data-sc-act]':[act],'[data-sc-tilt]':[tilt],'[data-sc-in]':[reveal]})[selector] || [];
    const flush = () => {
        let steps = 0;
        while (frames.size) {
            assert.ok(++steps < 150, 'Animation must settle, not run forever');
            const batch = [...frames.values()];frames.clear();
            for (const callback of batch) {frameCount++;callback(frameCount * 16);}
        }
        return steps;
    };
    return {root,scroller,act,layer,tilt,reveal,view,document,preference,frames,observers,flush};
}

test('ScrollCraft follows the nested workspace scroller and sleeps while idle', async () => {
    const {mountScrollCraft} = await import('../src/motion/scrollCraft.mjs');
    const f = fixture();
    const craft = mountScrollCraft(f.root,f.scroller);
    f.flush();
    assert.equal(f.layer.style.transform,'translate3d(0,10.00px,0)');
    assert.equal(f.frames.size,0);
    f.scroller.scrollTop = 200;
    f.scroller.dispatchEvent(new Event('scroll'));
    f.scroller.dispatchEvent(new Event('scroll'));
    assert.equal(f.frames.size,1,'Scroll events coalesce into one animation frame');
    f.flush();
    assert.equal(f.layer.style.transform,'translate3d(0,30.00px,0)');
    const revealObserver = f.observers.find(observer=>observer.options?.root);
    assert.equal(revealObserver.options.root,f.scroller);
    revealObserver.callback([{target:f.reveal,isIntersecting:true}]);
    assert.ok(f.reveal.classes.has('sc-in'));
    assert.equal(revealObserver.nodes.size,0,'Reveals run once');
    craft.destroy();
});

test('Pointer tilt settles, touch is ignored, and reduced motion resets it', async () => {
    const {mountScrollCraft} = await import('../src/motion/scrollCraft.mjs');
    const f = fixture(); const craft = mountScrollCraft(f.root,f.scroller); f.flush();
    const pointer = pointerType => {
        const event = new Event('pointermove');
        Object.assign(event,{pointerType,clientX:350,clientY:150});
        f.root.dispatchEvent(event);
    };
    pointer('touch'); assert.equal(f.frames.size,0);
    pointer('mouse'); assert.ok(f.flush()>1);
    assert.match(f.tilt.style.transform,/rotateX\(3.750deg\) rotateY\(3.750deg\)/);
    assert.equal(f.frames.size,0);
    f.preference.matches = true; f.preference.dispatchEvent(new Event('change'));
    assert.equal(f.layer.style.transform,'rotate(2deg)');
    assert.equal(f.tilt.style.transform,'');
    assert.ok(f.reveal.classes.has('sc-in'));
    pointer('mouse'); f.scroller.dispatchEvent(new Event('scroll'));
    assert.equal(f.frames.size,0);
    craft.destroy();
});

test('Route teardown removes observers, scheduled work and owned transforms', async () => {
    const {mountScrollCraft} = await import('../src/motion/scrollCraft.mjs');
    const f = fixture(); const craft = mountScrollCraft(f.root,f.scroller);
    assert.equal(f.frames.size,1);
    craft.destroy();craft.destroy();
    assert.equal(f.frames.size,0);
    assert.equal(f.root.attributes.has('data-sc-mounted'),false);
    assert.equal(f.layer.style.transform,'rotate(2deg)');
    assert.ok(f.observers.every(observer=>observer.disconnected));
    f.scroller.dispatchEvent(new Event('scroll'));f.view.dispatchEvent(new Event('resize'));
    for (const observer of f.observers) observer.callback(observer.options?.root ? [{target:f.reveal,isIntersecting:true}] : []);
    assert.equal(f.frames.size,0);
    assert.equal(f.reveal.classes.has('sc-in'),false);
});

test('Reduced-motion startup leaves readable content and schedules no animation', async () => {
    const {mountScrollCraft} = await import('../src/motion/scrollCraft.mjs');
    const f = fixture(true); const craft = mountScrollCraft(f.root,f.scroller);
    assert.equal(f.frames.size,0);
    assert.equal(f.root.attributes.has('data-sc-mounted'),false);
    assert.ok(f.reveal.classes.has('sc-in'));
    craft.destroy();
});
