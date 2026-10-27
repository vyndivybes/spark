import React, {useEffect, useRef, useState} from 'react';
import {Activity, ArrowLeft, ArrowUpRight, AudioLines, BookOpen, Box, Boxes, BrainCircuit, ChevronRight, Command, Cpu, Database, FlaskConical, GitBranch, Network, Radio, Search, Settings, ShieldCheck, Sparkles, Terminal, Workflow, X} from 'lucide-react';
import DashboardHome from './DashboardHome';
import StartupBriefing from './StartupBriefing';
const WorkspacePanel = React.lazy(() => import('./WorkspacePanel'));

const destinations = [
    ['Overview', Command, null, 'Start'],
    ['Missions', Workflow, 'intelligence:Agents', 'Workspace'],
    ['Knowledge', BookOpen, 'knowledge', 'Workspace'],
    ['Memory', Database, 'intelligence:Memory', 'Workspace'],
    ['Repositories', GitBranch, 'Repository Intelligence', 'Workspace'],
    ['Capabilities Center', Boxes, 'capabilities', 'Create'],
    ['Skill forge', FlaskConical, 'skills', 'Create'],
    ['Workbench', Terminal, 'workbench', 'Create'],
    ['Agent skills', Box, 'intelligence:Skills', 'Create'],
    ['Upgrade studio', Sparkles, 'Self-Upgrade Studio', 'Intelligence'],
    ['Recovery & REA', ShieldCheck, 'evolution', 'Intelligence'],
    ['Models', BrainCircuit, 'intelligence:Models', 'Intelligence'],
    ['Learning', BrainCircuit, 'intelligence:Learning', 'Intelligence'],
    ['Benchmarks', Activity, 'intelligence:Benchmarks', 'Intelligence'],
    ['Model upgrades', Sparkles, 'intelligence:Upgrades', 'Intelligence'],
    ['PC manager', Cpu, 'Windows PC Manager', 'System'],
    ['System health', Activity, 'System Health', 'System'],
    ['Connections', Network, 'System Connectivity', 'System'],
    ['Integrations', Network, 'intelligence:Integrations', 'System'],
    ['Approvals', ShieldCheck, 'Security & Approvals', 'System'],
    ['History', Terminal, 'Upgrade History', 'System'],
    ['Schedules', Radio, 'intelligence:Autonomy', 'System'],
];

export default function CommandCenter({brainGraph, brainError, socket, connected, liveState, diagnostics, startupVoice, project, messages = [], muted, requestedNavigation, onCockpit, onSettings, onExperiences, onRefresh, onUtility}) {
    const [page, setPage] = useState('Overview');
    const [search, setSearch] = useState('');
    const [commandOpen, setCommandOpen] = useState(false);
    const [clock, setClock] = useState(() => new Date());
    const scrollRef = useRef(null);
    const dialogRef = useRef(null);
    const searchRef = useRef(null);
    const commandTriggerRef = useRef(null);
    const pageHeadingRef = useRef(null);
    const navigate = name => {setPage(name); setCommandOpen(false); setSearch(''); scrollRef.current?.scrollTo({top:0});};
    useEffect(() => {const timer = setInterval(() => setClock(new Date()), 60000); return () => clearInterval(timer);}, []);
    useEffect(() => {
        const requested = requestedNavigation?.screen;
        if (destinations.some(([name]) => name === requested)) {setPage(requested); setCommandOpen(false); setSearch('');}
    }, [requestedNavigation]);
    useEffect(() => {
        scrollRef.current?.scrollTo({top:0});
        if (page !== 'Overview') pageHeadingRef.current?.focus({preventScroll:true});
    }, [page]);
    useEffect(() => {
        const keyboard = event => {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
                event.preventDefault(); setCommandOpen(open => !open);
            }
        };
        window.addEventListener('keydown', keyboard);
        return () => window.removeEventListener('keydown', keyboard);
    }, []);
    useEffect(() => {
        if (commandOpen) {dialogRef.current?.showModal(); searchRef.current?.focus();}
        else if (dialogRef.current?.open) {dialogRef.current.close(); commandTriggerRef.current?.focus();}
    }, [commandOpen]);
    const target = destinations.find(([name]) => name === page)?.[2];
    const matches = destinations.filter(([name, , , group]) => `${name} ${group}`.toLowerCase().includes(search.trim().toLowerCase()));
    const ready = connected && liveState?.state === 'connected';
    const session = ready ? 'AI session ready' : !connected ? 'Awaiting core' : liveState?.state === 'connecting' ? 'AI connecting' : ['error','setup_required','audio_error'].includes(liveState?.state) ? 'AI needs attention' : 'AI session idle';
    return <div id="spark-workspace-panel" className="command-center spark-dashboard holo-dashboard">
        <a href="#sd-content" className="sd-skip">Skip to workspace</a>
        <header className="sd-nav">
            <button className="sd-brand" aria-label="Spark home" onClick={() => navigate('Overview')}><span className="sd-brand-symbol"><Sparkles size={20}/></span>spark<span className="sd-brand-dot">.</span></button>
            <nav className="sd-primary-nav" aria-label="Main workspace">{['Overview','Knowledge','Missions','Connections'].map(name => <button key={name} aria-current={page === name ? 'page' : undefined} onClick={() => navigate(name)}>{name === 'Overview' ? 'Home' : name}</button>)}</nav>
            <div className="sd-nav-actions"><button ref={commandTriggerRef} className="sd-command-trigger" aria-label="Find workspace tools" aria-haspopup="dialog" onClick={() => setCommandOpen(true)}><Search size={16}/><span>All tools</span><kbd>Ctrl K</kbd></button><button className="sd-icon-button" onClick={onSettings} aria-label="Settings"><Settings size={18}/></button><span className="sd-profile" title="Personal workspace">S</span></div>
        </header>
        <main id="sd-content" className="sd-scroll" ref={scrollRef} tabIndex={-1}><div className="sd-page">
            <div className="sd-context"><span><i/>Personal intelligence<ChevronRight size={12}/><b>{project || 'default'}</b></span><span>{clock.toLocaleDateString(undefined, {weekday:'short',month:'short',day:'numeric'})}<span className={`sd-session ${ready ? 'is-ready' : ''}`}><i/>{session}</span></span></div>
            <div hidden={page !== 'Overview'}><StartupBriefing socket={socket} connected={connected} startupVoice={startupVoice}/></div>
            {page === 'Overview' ? <DashboardHome brainGraph={brainGraph} brainError={brainError} connected={connected} ready={ready} diagnostics={diagnostics} messages={messages} muted={muted} scrollRef={scrollRef} navigate={navigate} onCockpit={onCockpit} onTools={() => setCommandOpen(true)}/> : <section className="sd-tool-page">
                <div className="sd-tool-heading"><div><button className="sd-back" onClick={() => navigate('Overview')}><ArrowLeft size={14}/>Home</button><h1 ref={pageHeadingRef} tabIndex={-1}>{page}</h1></div><button className="sd-text-button" onClick={() => setCommandOpen(true)}>Switch tool<Command size={16}/></button></div>
                <React.Suspense fallback={<div className="sd-loading" role="status"><span/>Loading workspace tools…</div>}><WorkspacePanel key={page} socket={socket} visible project={project} onClose={() => navigate('Overview')} embedded initialTab={target?.startsWith('intelligence:') ? 'intelligence' : ['knowledge','workbench','skills','evolution','capabilities'].includes(target) ? target : 'screens'} initialScreen={target} initialIntelligencePage={target?.split(':')[1]}/></React.Suspense>
            </section>}
            <footer className="sd-footer"><span><span className="sd-footer-mark">✳</span>SPARK · Personal intelligence interface</span><button onClick={onRefresh} disabled={!connected}><Activity size={13}/>Refresh diagnostics</button><span>LOCAL CORE / YOUR CONTROL</span></footer>
        </div></main>
        <dialog ref={dialogRef} className="sd-command-dialog" aria-labelledby="sd-command-title" onCancel={() => setCommandOpen(false)} onClick={event => {if (event.target === event.currentTarget) setCommandOpen(false);}}><div className="sd-command-inner">
            <header><div><span className="sd-eyebrow">YOUR WORKSPACE, ONE SHORTCUT AWAY</span><h2 id="sd-command-title">Where to?</h2></div><button className="sd-icon-button" onClick={() => setCommandOpen(false)} aria-label="Close tool finder"><X size={20}/></button></header>
            <div className="sd-command-input"><Search size={19}/><input ref={searchRef} aria-label="Find a Spark screen" placeholder="Search tools, knowledge, systems…" value={search} onChange={event => setSearch(event.target.value)} onKeyDown={event => {if (event.key === 'Enter' && matches[0]) {event.preventDefault(); navigate(matches[0][0]);}}}/><kbd>ESC</kbd></div>
            <div className="sd-command-results">{matches.length ? ['Start','Workspace','Create','Intelligence','System'].map(group => {
                const tools = matches.filter(item => item[3] === group);
                return tools.length > 0 && <section key={group}><h3>{group}</h3>{tools.map(([name, Icon]) => <button key={name} onClick={() => navigate(name)}><Icon size={17}/>{name}<ArrowUpRight size={14}/></button>)}</section>;
            }) : <p className="sd-no-results">No matching tools. Try “knowledge” or “system”.</p>}</div>
            <div className="sd-command-utilities"><button onClick={() => {setCommandOpen(false); onCockpit();}}><AudioLines size={16}/>Voice cockpit</button><button onClick={() => {setCommandOpen(false); onExperiences();}}><Sparkles size={16}/>Experiences</button>{onUtility && ['Focus timer','Phone / watch','REA audit'].map(name => <button key={name} onClick={() => {setCommandOpen(false); onUtility(name);}}>{name}</button>)}</div>
        </div></dialog>
    </div>;
}
