import React, {useEffect, useRef, useState} from 'react';

export default function ReminderToast({socket, project, enabled}) {
    const [items, setItems] = useState([]);
    const seen = useRef(new Set());
    useEffect(() => {
        setItems([]);
        if (!enabled) return undefined;
        const slug = String(project || 'default').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0,40).replace(/-+$/, '') || 'default';
        const requestId = `reminder-${slug}-${Date.now()}`;
        const poll = () => {if (socket.connected) socket.emit('workspace_action', {workspace_token:socket.workspaceToken,request_id: requestId, action:'due_agenda', project:slug, payload:{}});};
        const receive = response => {
            if (response?.ok && ['add_agenda','complete_agenda','remove_workbench_item'].includes(response.action)) poll();
            if (response?.request_id !== requestId || !response.ok || !Array.isArray(response.result)) return;
            const fresh = response.result.filter(item => !seen.current.has(item.id));
            fresh.forEach(item => seen.current.add(item.id));
            const dueIds = new Set(response.result.map(item => item.id));
            setItems(previous => [...previous.filter(item => dueIds.has(item.id)), ...fresh].slice(-10));
        };
        socket.on('workspace_result', receive);
        poll();
        const timer = setInterval(poll, 30000);
        return () => {clearInterval(timer); socket.off('workspace_result', receive);};
    }, [socket, project, enabled]);
    if (!enabled || !items.length) return null;
    return <aside aria-label="Due reminders" aria-live="polite" className="absolute right-4 top-20 z-50 max-w-sm space-y-2">
        {items.map(item => <div key={item.id} className="rounded-xl border border-amber-400/60 bg-slate-950 p-4 text-amber-100 shadow-xl">
            <strong>{item.title}</strong><p className="text-sm">Due {new Date(item.due).toLocaleString()}</p>
            <button type="button" className="mt-2 rounded border border-white/30 px-3 py-1" onClick={() => setItems(previous => previous.filter(value => value.id !== item.id))}>Dismiss</button>
        </div>)}
    </aside>;
}
