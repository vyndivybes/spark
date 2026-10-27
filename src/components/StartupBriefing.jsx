import React, {useEffect, useState} from 'react';
import {CloudSun, MapPin, RefreshCw, Volume2, Wind} from 'lucide-react';

const savedCity = () => {try {return localStorage.getItem('spark-weather-city') || 'Coimbatore';} catch {return 'Coimbatore';}};

export default function StartupBriefing({socket, connected, startupVoice}) {
    const [city, setCity] = useState(savedCity);
    const [draft, setDraft] = useState(city);
    const [editing, setEditing] = useState(false);
    const [weather, setWeather] = useState(null);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const [refresh, setRefresh] = useState(0);
    const [now, setNow] = useState(() => new Date());
    useEffect(() => {const timer = setInterval(() => setNow(new Date()), 60000); return () => clearInterval(timer);}, []);
    useEffect(() => {
        if (!connected || !socket) return undefined;
        let active = true;
        const load = () => {
            setLoading(true); setError('');
            socket.timeout(25000).emit('get_dashboard_weather', {city}, (failure, result) => {
                if (!active) return;
                setLoading(false);
                if (failure || !result?.ok) {setWeather(null); setError(result?.message || 'Weather connection unavailable. Try refreshing.');}
                else setWeather(result);
            });
        };
        load();
        const timer = setInterval(load, 600000);
        return () => {active = false; clearInterval(timer);};
    }, [socket, connected, city, refresh]);
    let local = now;
    if (weather?.timezone) {try {local = new Date(now.toLocaleString('en-US', {timeZone:weather.timezone}));} catch { /* Fall back to device time. */ }}
    const greeting = local.getHours() < 12 ? 'Good morning' : local.getHours() < 17 ? 'Good afternoon' : 'Good evening';
    const fresh = connected && weather && now.getTime() / 1000 - weather.observed_at < 3600;
    return <section className="holo-briefing" aria-labelledby="briefing-title">
        <div className="holo-briefing-copy"><span className="sd-eyebrow"><span className={`holo-status-dot ${connected ? 'online' : ''}`}/>{connected ? 'STARTUP ACKNOWLEDGED' : 'AWAITING CORE CONNECTION'}</span><h2 id="briefing-title">{greeting}, <span>sir.</span></h2><p role="status">{connected ? 'Spark core is online. Ready when you are.' : 'Dashboard ready. Waiting for the core connection.'}</p><button className="holo-speak" onClick={startupVoice?.active ? startupVoice.stop : startupVoice?.play} aria-pressed={!!startupVoice?.active} disabled={!connected || !startupVoice}><Volume2 size={14}/>{startupVoice?.active ? 'Stop Spark briefing' : 'Replay Spark briefing'}</button><p className="holo-voice-status" role="status">{startupVoice?.message || 'Your welcome, weather, and Morning Digest play automatically in Spark’s voice.'}</p></div>
        <div className="holo-weather"><div className="holo-weather-head"><span><MapPin size={13}/>{weather?.city || city}</span><button aria-label="Change weather city" onClick={() => {setDraft(city); setEditing(!editing);}}>Change city</button><button aria-label="Refresh weather" disabled={!connected || loading} onClick={() => setRefresh(n => n + 1)}><RefreshCw size={13} className={loading ? 'holo-refreshing' : ''}/></button></div>
            {editing && <form className="holo-city-form" onSubmit={event => {event.preventDefault(); const next = draft.trim(); if (next.length < 2 || next.length > 80) return; setWeather(null); setCity(next); try {localStorage.setItem('spark-weather-city', next);} catch { /* Still usable for this session. */ } setEditing(false); setRefresh(n => n + 1);}}><label htmlFor="holo-city">Weather city</label><div><input id="holo-city" value={draft} maxLength={80} minLength={2} required onChange={event => setDraft(event.target.value)}/><button type="submit">Set city</button></div></form>}
            <div className="holo-weather-reading" aria-live="polite"><CloudSun size={34} strokeWidth={1}/><strong>{fresh ? `${Math.round(weather.temperature)}°` : '—'}<small>C</small></strong><div><b>{fresh ? weather.condition : loading ? 'Fetching current weather…' : 'Weather unavailable'}</b><span>{fresh ? `Feels like ${Math.round(weather.feels_like)}° · Humidity ${Math.round(weather.humidity)}%` : !connected ? 'Connect Spark to load weather.' : error || 'Waiting for current conditions.'}</span></div></div>
            <div className="holo-weather-meta"><span><Wind size={12}/>{fresh ? `${Math.round(weather.wind_kmh)} km/h` : 'No live reading'}</span><time>{local.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}{weather?.timezone ? ' · Local time' : ' · Device time'}</time></div>
            <div className="holo-weather-source"><a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Weather by Open-Meteo</a><span>{fresh ? `Updated ${new Date(weather.observed_at * 1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',timeZone:weather.timezone})}` : 'Current conditions only'}</span></div>
        </div>
    </section>;
}
