import React, { useEffect, useRef, useState } from 'react';
import { Globe, X } from 'lucide-react';
import { connectBrowserView } from '../browserSession.mjs';

const BrowserWindow = ({ imageSrc, logs = [], onClose, socket }) => {
    const [input, setInput] = useState('');
    const [local, setLocal] = useState(!imageSrc);
    const [view, setView] = useState({ state: 'connecting', logs: [] });
    const session = useRef(null);
    const logsEndRef = useRef(null);
    useEffect(() => { if (imageSrc) setLocal(false); }, [imageSrc]);
    useEffect(() => {
        if (!local) return;
        const connection = connectBrowserView(socket, setView);
        session.current = connection;
        return () => { connection.dispose(); session.current = null; };
    }, [socket, local]);
    useEffect(() => { logsEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [logs, view.logs]);
    const command = data => session.current?.command(data);
    const send = action => {
        if (!input.trim()) return;
        if (command({ action, text: input })) setInput('');
    };
    const image = local ? view.image : imageSrc && `data:${imageSrc.startsWith('iVBOR') ? 'image/png' : 'image/jpeg'};base64,${imageSrc}`;
    const disabled = !local || !view.image || !['ready', 'busy'].includes(view.state);
    const buttonClass = 'px-2 py-1 text-xs border border-gray-700 rounded disabled:opacity-40';
    return (
        <div className="w-full h-full relative bg-[#111] rounded-lg overflow-hidden flex flex-col border border-gray-800 text-gray-300">
            <div data-drag-handle className="h-8 bg-[#222] border-b border-gray-700 flex items-center justify-between px-2 shrink-0 cursor-grab">
                <div className="flex items-center gap-2 text-xs font-mono"><Globe size={14} className="text-cyan-500" /><span>WEB_AGENT_VIEW</span></div>
                <div className="flex items-center gap-2">
                    {!local && <button className={buttonClass} onClick={() => setLocal(true)}>Browse locally</button>}
                    <button aria-label="Close browser" onClick={onClose} className="p-1 hover:text-red-400"><X size={14} /></button>
                </div>
            </div>
            {local && <form className="flex gap-1 p-1 bg-[#161616] shrink-0" onSubmit={e => { e.preventDefault(); send('navigate'); }}>
                <button type="button" aria-label="Back" className={buttonClass} disabled={disabled} onClick={() => command({ action: 'back' })}>←</button>
                <button type="button" aria-label="Forward" className={buttonClass} disabled={disabled} onClick={() => command({ action: 'forward' })}>→</button>
                <button type="button" aria-label="Reload" className={buttonClass} disabled={disabled} onClick={() => command({ action: 'reload' })}>↻</button>
                <input aria-label="URL, search, or text to type" value={input} onChange={e => setInput(e.target.value)} placeholder="URL, search, or text to type" className="min-w-0 flex-1 bg-transparent px-1 text-xs outline-none" />
                <button className={buttonClass} disabled={disabled}>Go</button>
                <button type="button" className={buttonClass} disabled={disabled} onClick={() => send('type')}>Type</button>
            </form>}
            {local && <div role="status" className="flex items-center justify-between gap-1 px-2 py-1 text-xs shrink-0">
                <span className={view.state === 'error' ? 'text-red-400' : 'text-cyan-400'}>{view.message}</span>
                {view.state === 'error' && <button className={buttonClass} onClick={() => session.current?.retry()}>Retry</button>}
            </div>}
            <div className="flex-1 min-h-0 relative bg-black flex items-center justify-center overflow-hidden">
                {image ? <img src={image} alt="Browser View" draggable={false} tabIndex={local ? 0 : undefined}
                    className="max-w-full max-h-full object-contain outline-cyan-600"
                    onMouseDown={e => { if (local) e.stopPropagation(); }}
                    onClick={e => {
                        if (!local) return;
                        e.currentTarget.focus();
                        const rect = e.currentTarget.getBoundingClientRect();
                        // object-contain can letterbox the actual image inside the element.
                        const scale = Math.min(rect.width / 1440, rect.height / 900);
                        const width = scale * 1440, height = scale * 900;
                        const x = (e.clientX - rect.left - (rect.width - width) / 2) / width;
                        const y = (e.clientY - rect.top - (rect.height - height) / 2) / height;
                        if (x >= 0 && x <= 1 && y >= 0 && y <= 1) command({ action: 'click', x, y });
                    }}
                    onKeyDown={e => {
                        if (local && ['Enter', 'Tab', 'Backspace', 'Escape', 'ArrowUp', 'ArrowDown'].includes(e.key)) {
                            e.preventDefault(); command({ action: 'key', key: e.key });
                        }
                    }}
                    onWheel={e => { if (local) command({ action: 'scroll', direction: e.deltaY > 0 ? 'down' : 'up' }); }}
                /> : <span className="text-gray-500 text-xs">{view.state === 'error' ? 'Browser unavailable. See the error above.' : 'Starting browser...'}</span>}
            </div>
            {local && <div className="px-2 text-[10px] text-gray-500 truncate shrink-0" title={view.url}>{view.url || 'Local browser · no AI key required'}</div>}
            <div className="h-16 shrink-0 bg-black/90 border-t border-gray-800 p-2 font-mono text-[10px] overflow-y-auto text-green-500/80">
                {(local ? view.logs : logs).map((log, i) => <div key={i} className="mb-1 break-words">{log}</div>)}
                <div ref={logsEndRef} />
            </div>
        </div>
    );
};
export default BrowserWindow;
