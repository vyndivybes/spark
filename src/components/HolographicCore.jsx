import React, {useId, useState} from 'react';
import {Activity, AudioLines, BrainCircuit, Pause, Play} from 'lucide-react';

export default function HolographicCore({connected, ready, graphCount, cpu, memory, provider}) {
    const id = useId().replace(/:/g, '');
    const [mode, setMode] = useState('core');
    const [paused, setPaused] = useState(false);
    const views = {core:{label:'SYSTEM TELEMETRY', value:connected ? 'CORE ONLINE' : 'CORE OFFLINE', detail:connected ? `CPU ${cpu} / MEMORY ${memory}` : 'Awaiting local backend'}, knowledge:{label:'LOCAL KNOWLEDGE',value:typeof graphCount === 'number' ? graphCount.toLocaleString() : '—',detail:'Records in view · open Knowledge to explore'}, voice:{label:'VOICE CHANNEL',value:ready ? 'CONNECTED' : 'STANDBY',detail:ready ? `${provider || 'AI'} session connected` : 'Open the voice cockpit to connect'}};
    const selected = views[mode];
    return <div className={`holo-core ${paused ? 'is-paused' : ''}`}>
        <div className="holo-core-top"><span><i/>SPARK / NEURAL INTERFACE</span><button onClick={() => setPaused(!paused)} aria-label={paused ? 'Resume hologram motion' : 'Pause hologram motion'}>{paused ? <Play size={12}/> : <Pause size={12}/>}</button></div>
        <div className="holo-projection" data-sc-tilt="6"><svg className="holo-core-svg" viewBox="0 0 560 440" role="img" aria-label="Interactive artificial intelligence core visualization">
            <defs><radialGradient id={`${id}glow`}><stop stopColor="#1fcde3" stopOpacity=".16"/><stop offset="1" stopColor="#1fcde3" stopOpacity="0"/></radialGradient><linearGradient id={`${id}metal`} x2="1" y2="1"><stop stopColor="#28434e"/><stop offset=".5" stopColor="#101f2a"/><stop offset="1" stopColor="#060e15"/></linearGradient></defs>
            <circle cx="280" cy="218" r="210" fill={`url(#${id}glow)`}/>
            <g fill="none" stroke="currentColor"><circle cx="280" cy="218" r="182" strokeOpacity=".14"/><circle cx="280" cy="218" r="174" strokeDasharray="1 9" strokeWidth="3" strokeOpacity=".35"/>
                <g className="holo-ring-one"><circle cx="280" cy="218" r="164" strokeDasharray="160 65 25 90" strokeWidth="2"/><circle cx="280" cy="218" r="157" strokeDasharray="60 180" strokeOpacity=".25"/></g>
                <g className="holo-ring-two"><ellipse cx="280" cy="218" rx="209" ry="77" transform="rotate(-30 280 218)" strokeOpacity=".6"/><ellipse cx="280" cy="218" rx="209" ry="77" transform="rotate(30 280 218)" strokeOpacity=".25"/></g>
                <path d="M24 218h60m392 0h60M280 13v26m0 358v26M132 80l18 18m260 260 18 18M132 356l18-18m260-240 18-18" strokeOpacity=".45"/>
                {Array.from({length:36},(_,i) => <path key={i} d="M280 33v5" transform={`rotate(${i*10} 280 218)`} strokeOpacity=".4"/>)}
            </g>
            <g className="holo-mask" stroke="#7fd5e6" strokeWidth=".8" strokeLinejoin="round"><path d="M280 84l62 20 35 56-9 93-34 66-54 35-54-35-34-66-9-93 35-56Z" fill={`url(#${id}metal)`}/><path d="M280 84v69l-36 22-26-71m62 49 36 22 26-71M183 160l61 15-22 45-30 33m185-93-61 15 22 45 30 33M244 175l36 34 36-34m-36 34v55m-58-44 32 18-7 44-21 37m112-99-32 18 7 44 21 37M254 238l26-12 26 12M247 282l33 16 33-16m-33 16v56m-54-35 54 5 54-5" fill="none" strokeOpacity=".5"/>
                <path d="M211 191l47 12-9 16-28-8Zm138 0-47 12 9 16 28-8Z" fill="#fc6b6f" stroke="#ffa7a2"/><path d="M216 198l34 10m94-10-34 10" stroke="#ffe0d4" strokeWidth="2"/>
                <path d="M259 271h42l-8 7h-26Z" fill="#69dbe9" stroke="none"/>
            </g>
            <g fill="currentColor" fontFamily="Consolas,monospace" fontSize="8" letterSpacing="1.6"><text x="24" y="53">NEURAL CORE / 01</text><text x="409" y="390">VISUAL INTERFACE</text></g>
            <path className="holo-scan-line" d="M157 218h246" stroke="#8ce9f8" strokeOpacity=".35"/>
        </svg></div>
        <div className="holo-readout" aria-live="polite"><span>{selected.label}</span><strong>{selected.value}</strong><small>{selected.detail}</small></div>
        <div className="holo-core-tabs" role="group" aria-label="Hologram data view">{[['core',Activity,'System'],['knowledge',BrainCircuit,'Knowledge'],['voice',AudioLines,'Voice']].map(([key,Icon,label]) => <button key={key} aria-pressed={mode === key} onClick={() => setMode(key)}><Icon size={13}/>{label}</button>)}</div>
    </div>;
}
