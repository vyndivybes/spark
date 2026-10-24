import React, { useEffect, useRef, useState } from 'react';

const button = 'rounded-lg border border-cyan-500/40 px-3 py-2 text-sm text-cyan-100 disabled:opacity-40';
const card = 'rounded-xl border border-cyan-500/20 bg-slate-950/70 p-4 space-y-3';

export default function TelegramIntegrationPanel({ socket }) {
  const [status, setStatus] = useState(null);
  const [notice, setNotice] = useState('Loading Telegram status…');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const handler = (data) => {
      setStatus(data || null);
      if (data?.state === 'running') {
        setNotice('Owner-only long polling is active.');
      } else if (data?.configured === false) {
        setNotice('Not enrolled. Run the secure enrollment script on this PC to store the bot token in DPAPI.');
      } else {
        setNotice(data?.last_failure?.message || 'Telegram worker state updated.');
      }
    };
    socket?.on('telegram_status', handler);
    function refresh() {
      if (!socket?.connected) {
        setNotice('Local backend disconnected.');
        return;
      }
      setLoading(true);
      socket.emit('get_telegram_status');
      setTimeout(() => setLoading(false), 800);
    }
    socket?.on('connect', refresh);
    refresh();
    const interval = setInterval(() => {
      if (socket?.connected) socket.emit('get_telegram_status');
    }, 15000);
    return () => {
      clearInterval(interval);
      socket?.off('telegram_status', handler);
      socket?.off('connect', refresh);
    };
  }, [socket]);

  const data = status || {};
  const running = data.state === 'running' && data.polling;

  return (
    <section className={card} aria-label="Telegram integration">
      <div>
        <h3 className="font-semibold text-cyan-200">Telegram (@vayusparkbot)</h3>
        <p className="mt-1 text-sm text-slate-400">
          Owner-only private chat to SPARK. Token stored in Windows DPAPI (never in SQLite or logs). Long polling only; no webhook.
        </p>
      </div>
      <p role="status" className="text-sm text-slate-300">{notice}</p>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded border border-cyan-500/40 px-2 py-0.5 text-xs text-cyan-100">
          {data.configured ? (running ? 'running' : data.state || 'stopped') : 'unconfigured'}
        </span>
        {data.bot_username ? <span className="text-xs text-slate-400">@{data.bot_username}</span> : null}
        {data.authorized_chat_id ? <span className="text-xs text-slate-400">chat {data.authorized_chat_id}</span> : null}
        {data.model ? <span className="text-xs text-slate-400">model {data.model}</span> : null}
        {data.transport ? <span className="text-xs text-slate-400">{data.transport}</span> : null}
      </div>
      {data.configured && (
        <div className="grid gap-2 text-sm text-slate-300 md:grid-cols-2">
          <div>Last poll: {data.last_poll ? new Date(data.last_poll * 1000).toLocaleString() : '—'}</div>
          <div>Last inbound: {data.last_inbound ? new Date(data.last_inbound * 1000).toLocaleString() : '—'}</div>
          <div>Last outbound: {data.last_outbound ? new Date(data.last_outbound * 1000).toLocaleString() : '—'}</div>
          <div>Processed updates: {data.processed_updates ?? 0}</div>
          <div>Consecutive failures: {data.consecutive_failures ?? 0}</div>
          <div>Last digest: {data.last_digest?.sent_at ? new Date(data.last_digest.sent_at * 1000).toLocaleString() : data.last_digest?.date || '—'}</div>
        </div>
      )}
      <details className="text-sm text-slate-400">
        <summary className="cursor-pointer text-cyan-200">Commands & limits</summary>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          <li>/start /help /status /digest /missions /agents /integrations /memory</li>
          <li>Text or voice notes; voice is transcribed then answered</li>
          <li>Free chat has no shell/file/install/credential/purchase/security actions</li>
          <li>Live data only via real commands; failures are reported honestly</li>
          <li>Digest uses SPARK's opt-in IST schedule</li>
        </ul>
      </details>
      <button className={button} disabled={loading || !socket?.connected} onClick={() => {
        if (!socket?.connected) return;
        socket.emit('get_telegram_status');
        setNotice('Refreshing Telegram status…');
      }}>Refresh</button>
    </section>
  );
}
