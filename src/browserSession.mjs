// One view owns one local browser. Generation IDs reject late frames on retry.
export function connectBrowserView(socket, update, { timeout = 45000 } = {}) {
    let sessionId, timer, disposed = false;
    let state = { state: 'connecting', message: 'Connecting to SPARK...', image: null, url: '', logs: [] };
    const publish = patch => { state = { ...state, ...patch }; update(state); };
    const fail = message => {
        clearTimeout(timer);
        publish({ state: 'error', message });
    };
    const arm = () => {
        clearTimeout(timer);
        timer = setTimeout(() => fail('No browser frames received. Check the backend, then select Retry.'), timeout);
    };
    const start = () => {
        if (disposed) return;
        clearTimeout(timer);
        if (sessionId && socket?.connected) socket.emit('stop_web_browser', { session_id: sessionId });
        sessionId = globalThis.crypto.randomUUID();
        publish({ state: socket?.connected ? 'starting' : 'connecting', image: null, message: socket?.connected ? 'Starting local browser...' : 'Connecting to SPARK...' });
        if (socket?.connected) socket.emit('start_web_browser', { session_id: sessionId });
        arm();
    };
    const status = data => {
        if (disposed || data?.session_id !== sessionId) return;
        if (data.state === 'error') clearTimeout(timer);
        if (data.state === 'busy') arm();
        publish({ state: data.state, message: data.message, logs: [...state.logs, data.message].filter(Boolean).slice(-50) });
    };
    const frame = data => {
        if (disposed || data?.session_id !== sessionId || !data.image) return;
        arm();
        publish({ image: `data:${data.mime_type === 'image/png' ? 'image/png' : 'image/jpeg'};base64,${data.image}`, url: data.url, state: 'ready' });
    };
    const disconnected = () => fail('SPARK disconnected. The browser will restart when the connection returns.');
    socket?.on('connect', start);
    socket?.on('disconnect', disconnected);
    socket?.on('web_browser_status', status);
    socket?.on('web_browser_frame', frame);
    start();
    return {
        retry: start,
        command(data) {
            if (!socket?.connected || !state.image || state.state === 'error') return false;
            socket.emit('web_browser_command', { ...data, session_id: sessionId });
            arm();
            return true;
        },
        dispose() {
            disposed = true;
            clearTimeout(timer);
            socket?.off('connect', start);
            socket?.off('disconnect', disconnected);
            socket?.off('web_browser_status', status);
            socket?.off('web_browser_frame', frame);
            if (socket?.connected) socket.emit('stop_web_browser', { session_id: sessionId });
        },
    };
}
