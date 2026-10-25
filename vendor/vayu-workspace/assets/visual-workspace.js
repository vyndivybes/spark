(() => {
  'use strict';
  const projection = window.VAYU_PROJECTION;
  const main = document.querySelector('main.layout');
  if (!projection || !main) return;
  const body = document.body;
  body.classList.remove('separate-projection', 'studio-focus', 'holo-immersive');
  body.classList.add('visual-workspace');
  document.title = 'VĀYÚ · Visualization studio';
  const header = document.createElement('header');
  header.id = 'visual-workspace';
  header.innerHTML = `<div class="visual-identity"><b>VĀYÚ</b><span>Visualization studio</span></div>
    <div class="visual-header-actions"><span class="visual-snapshot">Source snapshot</span>
    <details id="visual-tools"><summary>Tools</summary><div class="visual-tools-menu">
      <a href="./VAYU-Knowledge-Sphere-Live.html?workspace=today">Action register ↗</a>
      <a href="./VAYU-Knowledge-Sphere-Live.html?workspace=analytics">Analytics & ledgers ↗</a>
      <button type="button" id="visual-wiki">Business knowledge</button>
      <div id="visual-motion"></div><div id="visual-camera"></div>
    </div></details><button type="button" id="visual-fullscreen">Fullscreen</button></div>`;
  if(document.documentElement.dataset.sparkProjects === 'true') {
    const link = document.createElement('a'); link.href = '/spark'; link.textContent = 'Spark project snapshots ↗'; header.querySelector('.visual-tools-menu').prepend(link);
  }
  const toolbar = document.createElement('nav');
  toolbar.id = 'visual-toolbar';
  toolbar.setAttribute('aria-label', 'Visualization controls');
  toolbar.innerHTML = `<div class="visual-view-row"><div class="visual-primary" role="group" aria-label="Quick views"></div>
    <label class="visual-view-select">All views <select id="visual-mode" aria-label="Visualization view"></select></label></div>
    <div class="visual-context-row"><label>Focus <select id="visual-focus" aria-label="Source focus"></select></label>
      <div id="visual-search-slot"></div><button type="button" id="visual-up">Up one level</button>
      <button type="button" id="visual-data" aria-expanded="false" aria-controls="visual-data-panel">Data & import</button>
      <div class="visual-zoom" role="group" aria-label="Zoom controls"></div>
      <button type="button" id="visual-inspect" aria-expanded="false" aria-controls="visual-inspector">Details</button></div>`;
  body.prepend(header, toolbar);
  const primary = toolbar.querySelector('.visual-primary');
  const select = toolbar.querySelector('#visual-mode');
  for (const {id, label} of projection.modes) {
    const option = new Option(label, id); select.add(option);
    if (['graph','orbit','rings','matrix'].includes(id)) {
      const button = document.createElement('button');
      button.type = 'button'; button.textContent = label; button.dataset.view = id;
      button.onclick = () => projection.activate(id); primary.append(button);
    }
  }
  select.onchange = () => projection.activate(select.value);
  const focus = toolbar.querySelector('#visual-focus');
  const sources = [['enterprise','All systems'],['VYNDI OS','VYNDI OS'],['VAOS','VAOS'],['VAOS:agents','Digital roles'],['vibpe','VIBPE'],['vedm','VEDM'],['jarvis','Jarvis'],['studio','Design studio']];
  for (const [id,label] of sources) focus.add(new Option(label,id));
  const selectedFocus = new Option('Selected node', '__selected'); selectedFocus.disabled = true;
  focus.add(selectedFocus);
  focus.onchange = () => projection.focus(focus.value);
  const search = document.querySelector('.projection-command input');
  if (search) { search.placeholder = 'Find a node…'; toolbar.querySelector('#visual-search-slot').append(search); }
  for (const id of ['zoom-out','zoom-in']) {
    const button = document.getElementById(id);
    if (button) { const originalZoom = button.onclick;
      button.onclick = event => { if(window.VYNDI_ALT_CONTROL?.active()) window.VYNDI_ALT_CONTROL.zoom(id === 'zoom-in' ? 1.15 : 1/1.15); else originalZoom?.call(button,event); };
      button.setAttribute('aria-label', id === 'zoom-out' ? 'Zoom out' : 'Zoom in'); toolbar.querySelector('.visual-zoom').append(button); }
  }
  for (const id of ['pause','pulse-toggle']) {
    const control = document.getElementById(id); if (control) header.querySelector('#visual-motion').append(control);
  }
  // Move existing controls rather than cloning listeners or maintaining another engine.
  const camera = document.querySelector('.qw-camera');
  if (camera) header.querySelector('#visual-camera').append(camera);
  const data = document.createElement('section');
  data.id = 'visual-data-panel'; data.hidden = true; data.setAttribute('aria-label','Sources and data import');
  data.innerHTML = '<div class="visual-panel-heading"><h2>Sources & import</h2><button type="button" id="visual-close-data">Close</button></div><p class="visual-data-note">Schema definitions describe structure. Import reviewed records to show actual values.</p>';
  const sidebar = document.querySelector('.qw-sidebar'); if (sidebar) data.append(sidebar);
  const advanced = document.getElementById('holo-advanced'); if (advanced) data.append(advanced);
  body.append(data);
  const inspector = main.querySelector('.inspector');
  inspector.id = 'visual-inspector';
  const inspectButton = toolbar.querySelector('#visual-inspect');
  function inspect(open) { body.classList.toggle('visual-details-open', open); inspectButton.setAttribute('aria-expanded', String(open)); inspector.inert = !open; }
  inspect(false);
  inspectButton.onclick = () => inspect(!body.classList.contains('visual-details-open'));
  const dataButton = toolbar.querySelector('#visual-data');
  function showData(open) { data.hidden = !open; dataButton.setAttribute('aria-expanded',String(open)); if(open)data.querySelector('button').focus(); else dataButton.focus(); }
  dataButton.onclick = () => showData(data.hidden);
  data.querySelector('#visual-close-data').onclick = () => showData(false);
  toolbar.querySelector('#visual-up').onclick = () => document.getElementById('map-up')?.click();
  header.querySelector('#visual-wiki').onclick = () => { header.querySelector('#visual-tools').open = false; window.VYNDI_BUSINESS_WIKI.open(); };
  header.querySelector('#visual-fullscreen').onclick = () => { if(document.fullscreenElement) document.exitFullscreen?.(); else document.documentElement.requestFullscreen?.().catch(() => {}); };
  document.addEventListener('keydown', event => { if(event.key === 'Escape' && !data.hidden) showData(false); });
  const status = document.createElement('div'); status.className = 'visual-status'; status.setAttribute('aria-live','polite');
  main.querySelector('.stage').append(status);
  let previousFocus = projection.getState().focusId;
  function sync() {
    const state = projection.getState(); select.value = state.mode;
    primary.querySelectorAll('[data-view]').forEach(b => b.setAttribute('aria-pressed',String(b.dataset.view === state.mode)));
    focus.value = sources.some(([id]) => id === state.focusId) ? state.focusId : '__selected';
    selectedFocus.textContent = state.focus;
    status.textContent = `${state.focus} · ${state.nodes} nodes · ${state.links} relationships · Schema snapshot`;
    const url = new URL(location.href); url.searchParams.delete('separate'); url.searchParams.set('projection',state.mode); history.replaceState(null,'',url);
    if(state.focusId !== previousFocus) { inspect(true); previousFocus = state.focusId; }
  }
  window.addEventListener('vayu:view-change',sync);
  const originalPaint = paintStage;
  paintStage = function() { const result = originalPaint(); sync(); return result; };
  // Keep deferred hand controls accessible if their module mounts after this script.
  const controls = document.getElementById('holo-projection-bar');
  const moveCamera = () => { const control = controls?.querySelector('.qw-camera'); if(control) header.querySelector('#visual-camera').append(control); };
  if(controls) new MutationObserver(moveCamera).observe(controls,{childList:true,subtree:true});
  sync(); window.dispatchEvent(new Event('resize'));
})();
