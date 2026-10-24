import React, {useEffect, useRef, useState} from 'react';
import socket from '../sparkSocket.mjs';
import {getPressureAdvice} from '../utils/systemPressure.mjs';
const size = bytes => `${(bytes / 1024 / 1024).toFixed(2)} MB`;
export default function PcOptimizationPanel() {
  const [scan, setScan] = useState(null), [busy, setBusy] = useState(false);
  const [confirmed, setConfirmed] = useState(false), [notice, setNotice] = useState('Scan for resource pressure and old temporary files.');
  const pending = useRef(null);
  useEffect(() => {
    const receive = data => {
      if (!pending.current || data.request_id !== pending.current.id) return;
      const action = pending.current.action;
      clearTimeout(pending.current.timer); pending.current = null; setBusy(false);
      if (!data.ok) {setScan(null); setNotice(data.message); return;}
      if (action === 'scan') {setScan(data.result); setConfirmed(false); setNotice('Scan complete. Review files before cleanup.');}
      else {setScan(null); setConfirmed(false); setNotice(`Removed ${data.result.deleted} files (${size(data.result.reclaimed_bytes)}). Skipped ${data.result.skipped} changed or inaccessible files. Scan again for updated readings.`);}
    };
    socket.on('pc_optimizer_result', receive);
    return () => {socket.off('pc_optimizer_result', receive); clearTimeout(pending.current?.timer);};
  }, []);
  function request(action) {
    if (!socket.connected) {setNotice('Connect the local backend first.'); return;}
    if (pending.current) return;
    const id = `pc-opt-${Date.now()}`;
    const payload = action === 'cleanup' ? {scan_id: scan.scan_id, confirmed} : {};
    setBusy(true); setNotice(action === 'scan' ? 'Scanning…' : 'Cleaning previewed files…');
    pending.current = {id, action, timer: setTimeout(() => {pending.current = null; setBusy(false); setScan(null); setNotice('Request timed out. Scan again to check the current state.');}, 30000)};
    socket.emit('pc_optimizer_action', {request_id: id, workspace_token: socket.workspaceToken, action, payload});
  }
  return <section className="mt-4 border border-cyan-600/40 rounded-xl p-4" aria-label="PC optimisation">
    <h3 className="font-bold text-cyan-200">PC optimisation</h3>
    <p className="mt-2 text-sm text-slate-200" role="status">{notice}</p>
    <button disabled={busy} onClick={() => request('scan')} className="mt-3 rounded-lg border border-cyan-600 px-3 py-2 disabled:opacity-40">Scan PC</button>
    {scan && <>
      <p className="mt-3 text-sm">CPU: {scan.host.cpu_percent ?? 'Unavailable'}% · RAM available: {scan.host.ram_available_gb ?? 'Unavailable'} GB · Disk free: {scan.host.disk_free_gb ?? 'Unavailable'} GB</p>
      <ul className="mt-3 space-y-2">{getPressureAdvice(scan.host).map(item => <li key={item.id}><strong>{item.label}:</strong> {item.text}</li>)}</ul>
      <p className="mt-3 text-sm">Review Startup apps in Windows Settings and close unused apps in Task Manager. Run heavy SPARK audits one at a time.</p>
      <p className="mt-3 text-sm">{scan.scope} {scan.limited && 'Scan limit reached; partial preview.'}</p>
      <p className="mt-2 font-semibold">{scan.files.length} eligible files · {size(scan.eligible_bytes)}</p>
      <ul aria-label="Temporary file preview" className="mt-2 max-h-40 overflow-auto break-all text-xs">{scan.files.map(file => <li key={file.name}>{file.name} · {size(file.bytes)}</li>)}</ul>
      {scan.files.length > 0 && <>
        <label className="mt-3 flex gap-2 items-start"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)}/>I reviewed these files and approve permanent deletion. This bypasses the Recycle Bin; close apps using these files first.</label>
        <button disabled={busy || !confirmed} onClick={() => request('cleanup')} className="mt-3 rounded-lg border border-amber-500 px-3 py-2 disabled:opacity-40">Delete previewed temporary files</button>
      </>}
    </>}
    <p className="mt-3 text-xs text-slate-400">Local and free. Cleanup runs only on your click. No registry edits, service changes, RAM flushing or automatic app termination.</p>
  </section>;
}
