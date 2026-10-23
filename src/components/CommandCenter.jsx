import React, {useEffect, useState} from 'react';
import {Activity, ArrowUpRight, AudioLines, BookOpen, Box, Boxes, BrainCircuit, ChevronRight, HelpCircle, Command, Cpu, Database, FlaskConical, GitBranch, LayoutDashboard, Menu, Network, Radio, Search, Settings, ShieldCheck, Sparkles, Terminal, Workflow, X} from 'lucide-react';
const WorkspacePanel = React.lazy(() => import('./WorkspacePanel'));
import Visualizer from './Visualizer';

const destinations = [
    ['Overview', LayoutDashboard, null],
    ['Missions', Workflow, 'intelligence:Agents'],
    ['Knowledge', BookOpen, 'knowledge'],
    ['Memory', Database, 'intelligence:Memory'],
    ['Capabilities Center', Boxes, 'capabilities'],
    ['Skill forge', FlaskConical, 'skills'],
    ['Upgrade studio', Sparkles, 'Self-Upgrade Studio'],
    ['Repositories', GitBranch, 'Repository Intelligence'],
    ['PC manager', Cpu, 'Windows PC Manager'],
    ['System health', Activity, 'System Health'],
    ['Connections', Network, 'System Connectivity'],
    ['Approvals', ShieldCheck, 'Security & Approvals'],
    ['History', Terminal, 'Upgrade History'],
    ['Workbench', FlaskConical, 'workbench'],
    ['Recovery & REA', ShieldCheck, 'evolution'],
    ['Models', BrainCircuit, 'intelligence:Models'],
    ['Schedules', Radio, 'intelligence:Autonomy'],
    ['Learning', BrainCircuit, 'intelligence:Learning'],
    ['Benchmarks', Activity, 'intelligence:Benchmarks'],
    ['Integrations', Network, 'intelligence:Integrations'],
    ['Model upgrades', Sparkles, 'intelligence:Upgrades'],
    ['Agent skills', Box, 'intelligence:Skills'],
];

function Signal({online, children}) {
    return <span className={`cc-signal ${online ? 'is-online' : ''}`}><i/>{children}</span>;
}

export default function CommandCenter({brainGraph, brainError, socket, connected, liveState, diagnostics, project, messages = [], muted, requestedNavigation, onCockpit, onSettings, onExperiences, onRefresh}) {
    const [page, setPage] = useState('Overview');
    const [search, setSearch] = useState('');
    const [menuOpen, setMenuOpen] = useState(false);
    const [help, setHelp] = useState(false);
    const [clock, setClock] = useState(() => new Date());
    useEffect(() => {const timer = setInterval(() => setClock(new Date()), 60000); return () => clearInterval(timer);}, []);
    const navigate = name => {setPage(name); setMenuOpen(false); setSearch('');};
    useEffect(() => {
        const requested = requestedNavigation?.screen;
        if (destinations.some(([name]) => name === requested)) {
            setPage(requested);
            setMenuOpen(false);
            setSearch('');
        }
    }, [requestedNavigation]);
    const target = destinations.find(([name]) => name === page)?.[2];
    const host = diagnostics?.host || {};
    const percentage = number => typeof number === 'number' && Number.isFinite(number) ? `${number.toFixed(0)}%` : '—';
    const ready = connected && liveState?.state === 'connected';
    const matches = search.trim() ? destinations.filter(([name]) => name.toLowerCase().includes(search.trim().toLowerCase())) : [];
    return <div id="spark-workspace-panel" className={`command-center ${menuOpen ? 'cc-menu-open' : ''}`}>
        <a href="#cc-content" className="cc-skip">Skip to workspace</a>
        <aside className="cc-sidebar" aria-label="Command navigation">
            <div className="cc-identity"><span className="cc-mark"><Command size={22}/></span><div><strong>Spark</strong><small>Personal workspace</small></div><button className="cc-mobile-close" onClick={() => setMenuOpen(false)} aria-label="Close navigation"><X size={18}/></button></div>
            <div className="cc-project"><span className="cc-project-icon"><Box size={17}/></span><div><small>Current workspace</small><strong>{project || 'default'}</strong></div><span className="cc-project-local">LOCAL</span></div>

            <nav><button type="button" aria-current={page==='Overview'?'page':undefined} onClick={()=>navigate('Overview')}><LayoutDashboard size={17}/>Overview</button>{[
                ['Workspace',['Missions','Knowledge','Memory']],
                ['Build',['Capabilities Center','Missions','Knowledge','Memory','Skill forge','Repositories','Workbench','Agent skills']],
                ['Evolution',['Upgrade studio','Recovery & REA','Models','Learning','Benchmarks','Model upgrades']],
                ['Systems',['PC manager','System health','Connections','Integrations']],
                ['Governance',['Approvals','History','Schedules']],
            ].map(([group,names])=><details className="cc-nav-group" key={group} open={names.includes(page)}><summary>{group}<ChevronRight size={14}/></summary>{destinations.filter(([name])=>names.includes(name)).map(([name,Icon])=><button type="button" key={name} aria-current={page===name?'page':undefined} onClick={()=>navigate(name)}><Icon size={16}/>{name}</button>)}</details>)}</nav>
            <div className="cc-sidebar-bottom"><button onClick={onExperiences}><BrainCircuit size={17}/>Experience library<ArrowUpRight size={14}/></button><button onClick={onSettings}><Settings size={17}/>Settings</button><div className="cc-local-status"><span>Local workspace</span><small>Runs on your machine</small></div></div>
        </aside>
        {menuOpen && <button className="cc-scrim" aria-label="Dismiss navigation" onClick={() => setMenuOpen(false)}/>}
        <div className="cc-workspace">
            <header className="cc-topbar"><button className="cc-menu-toggle" aria-label="Open navigation" onClick={() => setMenuOpen(true)}><Menu size={20}/></button><div className="cc-breadcrumb">Workspace <ChevronRight size={13}/><strong>{page}</strong></div><div className="cc-search"><Search size={16}/><input aria-label="Find a Spark screen" placeholder="Find a screen…" value={search} onChange={event => setSearch(event.target.value)} onKeyDown={event => {if (event.key === 'Escape') setSearch(''); if (event.key === 'Enter' && matches[0]) navigate(matches[0][0]);}}/>{search && <div className="cc-search-results">{matches.length ? matches.map(([name, Icon]) => <button key={name} onClick={() => navigate(name)}><Icon size={15}/>{name}<ArrowUpRight size={13}/></button>) : <p>No matching screens</p>}</div>}</div><button className="cc-icon-button" aria-label="Show workspace help" aria-expanded={help} onClick={() => setHelp(value => !value)}><HelpCircle size={18}/></button><span className="cc-avatar" aria-label="Local workspace">S</span></header>
            <main id="cc-content" className="cc-content" tabIndex={-1}>
                {help && <div className="cc-help" role="status">Choose a screen on the left, or search by its name. Voice opens your existing cockpit. Repairs and upgrades keep their review and approval steps.<button onClick={() => setHelp(false)} aria-label="Dismiss help"><X size={16}/></button></div>}
                {page === 'Overview' ? <>
                    <div className="cc-heading"><div><span className="cc-overline">Your personal command center</span><h2>Everything in orbit.</h2><p>Your intelligence, projects, and machine. One workspace.</p></div><div className="cc-heading-meta"><span>{clock.toLocaleDateString(undefined, {weekday:'short', month:'short', day:'numeric'})}</span><Signal online={ready}>{ready ? 'AI session ready' : connected ? 'AI session idle' : 'Awaiting core'}</Signal></div></div>
                    <section className="cc-hero" aria-label="Spark session"><div className="cc-hero-copy"><span className="cc-overline"><Radio size={13}/> SPARK intelligence</span><h3>Your workspace,<br/>in motion.</h3><p>{ready ? 'Your AI session is connected. Open the cockpit to continue your conversation.' : 'Open your voice cockpit to connect, talk, and work with Spark.'}</p><button className="cc-primary" onClick={onCockpit}><AudioLines size={18}/>Open voice cockpit<ArrowUpRight size={16}/></button><span className="cc-privacy"><ShieldCheck size={12}/>{muted ? 'Microphone muted' : 'Microphone enabled'} · Camera requires consent</span></div><div className="cc-spatial-preview"><Visualizer graph={brainGraph} graphError={brainError} isListening={false} width={400} height={300}/></div></section>
                    <section className="cc-metrics" aria-label="Runtime readings"><article><span><Activity size={15}/>Core status</span><strong className={connected ? 'cc-value-good' : ''}>{connected ? 'Online' : 'Offline'}</strong><small>{connected ? 'Local backend connected' : 'No backend connection'}</small></article><article><span><Cpu size={15}/>CPU usage</span><strong>{connected ? percentage(host.cpu_percent) : '—'}</strong><small>{connected ? 'Latest diagnostic reading' : 'Connect core for readings'}</small></article><article><span><Database size={15}/>Memory usage</span><strong>{connected ? percentage(host.ram_percent) : '—'}</strong><small>{connected ? 'Latest diagnostic reading' : 'Connect core for readings'}</small></article><article><span><AudioLines size={15}/>AI session</span><strong>{ready ? 'Connected' : 'Standby'}</strong><small>{connected ? diagnostics?.ai_provider || 'Provider not reported' : 'Waiting for local core'}</small></article></section>
                    <div className="cc-lower-grid"><section className="cc-panel cc-session-panel"><div className="cc-section-heading"><div><span className="cc-overline">Current workspace</span><h3>Session activity</h3></div><span className="cc-count">{messages.length}</span></div>{messages.length ? <ol className="cc-activity">{messages.slice(-3).map((message, index) => <li key={index}><span className="cc-activity-dot"/><div><strong>{message.role === 'user' || message.sender === 'user' ? 'You' : 'Spark'}</strong><p>{String(message.text || message.content || 'Session message')}</p></div></li>)}</ol> : <div className="cc-empty"><Terminal size={26}/><strong>A fresh starting point</strong><p>Your conversation activity appears here once you begin a session.</p></div>}</section></div>

                </> : <><div className="cc-heading cc-page-heading"><div><span className="cc-overline">SPARK / {project}</span><h2>{page}</h2></div><button className="cc-secondary" onClick={() => navigate('Overview')}>Back to overview</button></div><React.Suspense fallback={<p role="status">Loading workspace tools…</p>}><WorkspacePanel key={page} socket={socket} visible project={project} onClose={onCockpit} embedded initialTab={target?.startsWith('intelligence:') ? 'intelligence' : ['knowledge','workbench','skills','evolution','capabilities'].includes(target) ? target : 'screens'} initialScreen={target} initialIntelligencePage={target?.split(':')[1]}/></React.Suspense></>}
                <footer className="cc-footer"><span><i/>SPARK / Personal intelligence workstation</span><button onClick={onRefresh} disabled={!connected}><Activity size={13}/>Refresh diagnostics</button></footer>
            </main>
        </div>
    </div>;
}
