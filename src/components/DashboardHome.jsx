import React, {useEffect, useRef} from 'react';
import {motion, useReducedMotion} from 'framer-motion';
import {Activity, ArrowDown, ArrowUpRight, AudioLines, BookOpen, ChevronRight, Cpu, Database, MicOff, Network, ShieldCheck, Workflow} from 'lucide-react';
import HolographicCore from './HolographicCore';
import {mountScrollCraft} from '../motion/scrollCraft.mjs';

const percentage = value => typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(0)}%` : '—';
const senderName = sender => ['user','User','You'].includes(sender) ? 'You' : ['SPARK','Spark','assistant'].includes(sender) ? 'Spark' : sender || 'Spark';

export default function DashboardHome({brainGraph, brainError, connected, ready, diagnostics, messages, muted, scrollRef, navigate, onCockpit, onTools}) {
    const reduced = useReducedMotion();
    const motionRoot = useRef(null);
    useEffect(() => {
        if (!motionRoot.current || !scrollRef.current) return undefined;
        const craft = mountScrollCraft(motionRoot.current, scrollRef.current);
        return () => craft.destroy();
    }, [scrollRef]);
    const launchRef = useRef(null);
    const host = diagnostics?.host || {};
    const graphCount = brainGraph?.totalNodes ?? brainGraph?.nodes?.length;
    const metrics = [
        ['Core status', Activity, connected ? 'Online' : 'Offline', connected ? 'Local backend connected' : 'No backend connection'],
        ['CPU usage', Cpu, connected ? percentage(host.cpu_percent) : '—', connected ? 'Latest diagnostic reading' : 'Connect core for readings'],
        ['Memory usage', Database, connected ? percentage(host.ram_percent) : '—', connected ? 'Latest diagnostic reading' : 'Connect core for readings'],
        ['AI session', AudioLines, ready ? 'Connected' : 'Standby', connected ? diagnostics?.ai_provider || 'Provider not reported' : 'Waiting for local core'],
    ];
    return <div ref={motionRoot} className="sd-home">
        <section className="sd-hero" data-sc-act="flow" aria-labelledby="sd-hero-title">
            <div className="sd-hero-atmosphere" data-sc-parallax="-.5" aria-hidden="true"/>
            <div className="sd-hero-copy"><span className="sd-eyebrow"><span className="sd-mini-cross">✳</span>PERSONAL INTELLIGENCE / COMMAND DECK</span><h1 id="sd-hero-title">Intelligence.<br/><span>At your command.</span></h1><p>Your knowledge, missions, and connected systems.<br className="sd-desktop-break"/> One interface. Ready for your next move.</p><div className="sd-hero-actions"><button className="sd-primary" onClick={onCockpit}><AudioLines size={18}/>Open voice cockpit<ArrowUpRight size={18}/></button><button className="sd-text-button" onClick={onTools}>Explore tools<ChevronRight size={16}/></button></div><span className="sd-privacy"><MicOff size={12}/>{muted ? 'Microphone muted' : 'Microphone enabled'}<span/>Camera requires consent</span><div className="holo-knowledge-count"><Database size={13}/><strong>{typeof graphCount === 'number' ? graphCount.toLocaleString() : '—'}<small> records in view</small></strong><span>{brainGraph ? 'LOCAL KNOWLEDGE' : brainError || 'Waiting for local records.'}</span></div></div>
            <div className="sd-orbit-stage" data-sc-parallax=".35"><HolographicCore connected={connected} ready={ready} graphCount={graphCount} cpu={percentage(host.cpu_percent)} memory={percentage(host.ram_percent)} provider={diagnostics?.ai_provider}/></div>
            <button className="sd-scroll-cue" onClick={() => launchRef.current?.scrollIntoView({behavior:reduced ? 'instant' : 'smooth',block:'start'})}><ArrowDown size={14}/><span>Access your workspace</span></button><span className="sd-hero-index" aria-hidden="true">01 / NEURAL INTERFACE</span>
        </section>
        <section className="sd-metrics" aria-label="Runtime readings">{metrics.map(([label,Icon,value,note]) => <article key={label}><span><Icon size={14}/>{label}</span><div><strong>{value}</strong>{label === 'Core status' && <i className={connected ? 'is-online' : ''}/>}</div><small>{note}</small></article>)}</section>
        <section className="sd-launch-section" ref={launchRef} aria-labelledby="sd-launch-title"><div className="sd-section-heading" data-sc-in=""><div><span className="sd-eyebrow">CONNECTED WORKSPACE</span><h2 id="sd-launch-title">Choose your<br/><span>next operation.</span></h2></div><p>From a thought to a mission.<br/>Your tools are one step away.</p><button className="sd-text-button" onClick={onTools}>All workspace tools<ArrowUpRight size={15}/></button></div>
            <div className="sd-lower-grid"><div className="sd-launch-stack">{[
                ['Knowledge',BookOpen,'Connect the dots.','Your notes, documents, and discoveries. One place to find the thread.','01'],
                ['Missions',Workflow,'Give an idea momentum.','Bring a goal into focus and work through it with your agents.','02'],
                ['Connections',Network,'Keep your world connected.','Check your services and see what needs your attention.','03'],
            ].map(([name,Icon,title,copy,index]) => <motion.button key={name} className="sd-launch-card" data-sc-in="" style={{'--sc-delay':`${Number(index) * 50}ms`}} onClick={() => navigate(name)} whileHover={reduced ? {} : {y:-4}}><span className="sd-card-top"><span><Icon size={17}/>{name}</span><span>{index}</span></span><strong>{title}</strong><span className="sd-card-copy">{copy}</span><span className="sd-card-link">Open {name.toLowerCase()}<ArrowUpRight size={18}/></span></motion.button>)}</div>
                <aside className="sd-activity" aria-label="Session activity"><div className="sd-activity-heading"><span className="sd-eyebrow">THE HERE & NOW</span><span className="sd-activity-count">{messages.length.toString().padStart(2,'0')}</span></div><h3>In the loop.</h3>{messages.length ? <ol className="sd-activity-list">{messages.slice(-4).map((message,index) => <li key={index}><span className="sd-activity-role">{senderName(message.sender || message.role)}<time>{message.time || 'This session'}</time></span><p>{String(message.text || message.content || 'Session message')}</p></li>)}</ol> : <div className="sd-empty"><div className="sd-empty-orbits" aria-hidden="true"><i/><i/><i/><span>✳</span></div><strong>A fresh starting point</strong><p>Your conversation activity appears here once you begin a session.</p><button className="sd-text-button" onClick={onCockpit}>Start a conversation<ArrowUpRight size={15}/></button></div>}<div className="sd-local-note"><ShieldCheck size={16}/><span>Your space, your control.<small>Tools keep their existing approval steps.</small></span></div></aside>
            </div>
        </section>
    </div>;
}
