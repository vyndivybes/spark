import React, {useId} from 'react';

// Decorative geometry, not a representation of live records or performance.
const particles = Array.from({length:460}, (_, index) => {
    const y = 1 - (index / 459) * 2;
    const radius = Math.sqrt(1 - y * y);
    const angle = index * 2.3999632297;
    return {x:Math.cos(angle) * radius, y, z:Math.sin(angle) * radius};
}).sort((a,b) => a.z - b.z);

export default function SparkOrbit() {
    const id = useId().replace(/:/g, '');
    return <svg viewBox="0 0 540 500" className="sd-orbit" aria-hidden="true">
        <defs><radialGradient id={`${id}-halo`}><stop stopColor="#badb8c" stopOpacity=".15"/><stop offset="1" stopColor="#badb8c" stopOpacity="0"/></radialGradient><radialGradient id={`${id}-sphere`} cx="35%" cy="25%"><stop stopColor="#3d4b36"/><stop offset=".55" stopColor="#1c251d"/><stop offset="1" stopColor="#101711"/></radialGradient><linearGradient id={`${id}-ring`}><stop stopColor="#def4ac" stopOpacity=".1"/><stop offset=".5" stopColor="#d8f5a0"/><stop offset="1" stopColor="#a9c87a" stopOpacity=".2"/></linearGradient></defs>
        <circle cx="270" cy="248" r="240" fill={`url(#${id}-halo)`}/>
        <g className="sd-orbit-guides" fill="none" stroke="currentColor" strokeWidth=".6"><circle cx="270" cy="248" r="222" strokeDasharray="2 7"/><path d="M270 4V24M270 472V492M26 248H46M494 248H514"/><ellipse cx="270" cy="248" rx="224" ry="74" transform="rotate(-28 270 248)"/></g>
        <g className="sd-orbit-sphere"><circle cx="270" cy="248" r="147" fill={`url(#${id}-sphere)`} stroke="#b8d28b" strokeOpacity=".4" strokeWidth=".7"/>{[-72,-48,-24,0,24,48,72].map(angle => <ellipse key={angle} cx="270" cy="248" rx={Math.max(12,147 * Math.cos(angle * Math.PI / 180))} ry="147" fill="none" stroke="#bedc8b" strokeOpacity=".11" strokeWidth=".6" transform="rotate(25 270 248)"/>)}{particles.map((p,index) => <circle key={index} cx={270 + p.x * 147} cy={248 + p.y * 147} r={p.z > .4 ? 1 : .65} fill="#d4efa9" opacity={.12 + (p.z + 1) * .3}/>)}</g>
        <g fill="none" stroke={`url(#${id}-ring)`} strokeWidth="1.4"><ellipse cx="270" cy="248" rx="209" ry="53" transform="rotate(-28 270 248)"/><ellipse cx="270" cy="248" rx="199" ry="49" transform="rotate(-28 270 248)"/></g>
        <g className="sd-orbit-satellite"><circle cx="461" cy="156" r="7" fill="#d3efa2"/><circle cx="461" cy="156" r="14" fill="none" stroke="#d3efa2" strokeOpacity=".2"/></g>
        <g fill="currentColor" fontFamily="Consolas,monospace" fontSize="8" letterSpacing="2"><text x="40" y="60">SPK—01</text></g><path d="M46 419h28m-14-14v28" stroke="currentColor" strokeWidth=".6"/>
    </svg>;
}
