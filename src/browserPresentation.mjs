// Deterministic and local: no model prompt, site content, or external request can
// generate browser control instructions. React invokes this only for user speech.
export function browserVoiceCommand(transcript) {
    if (!transcript || !['user', 'you', 'human'].includes(String(transcript.sender || '').toLowerCase())) return null;
    const raw = transcript.text;
    if (typeof raw !== 'string' || raw.length > 240) return null;
    const phrase = raw.toLowerCase().replace(/[,.!?]/g, ' ').replace(/\s+/g, ' ').trim()
        .replace(/^(?:(?:hey|okay|ok) )?spark\s+/, '')
        .replace(/^(?:please |can you |could you )+/, '');
    if (/^(?:show (?:me|us) the (?:whole|entire) (?:website|web page|page)|scroll (?:to the )?bottom)/.test(phrase)) {
        return { action: 'present_scroll', direction: 'down', speed: 'slow' };
    }
    const scroll = phrase.match(/^(?:start |begin )?scroll(?:ing)? (down|up)\b/);
    if (scroll) {
        const speed = /\b(?:fast|quickly|faster)\b/.test(phrase) ? 'fast'
            : /\bnormal\b/.test(phrase) ? 'normal' : 'slow';
        return { action: 'present_scroll', direction: scroll[1], speed };
    }
    if (/^(?:pause(?: here| scrolling)?|hold (?:here|scrolling))$/.test(phrase)) return { action: 'pause_scroll' };
    if (/^(?:resume(?: scrolling)?|continue(?: scrolling)?)$/.test(phrase)) return { action: 'resume_scroll' };
    if (/^(?:stop(?: scrolling)?|end (?:the )?presentation)$/.test(phrase)) return { action: 'stop_scroll' };
    if (/^(?:scroll )?(?:faster|speed up)$/.test(phrase)) return { action: 'speed_up' };
    if (/^(?:scroll )?(?:slower|slow down)$/.test(phrase)) return { action: 'slow_down' };
    if (/^zoom in$/.test(phrase)) return { action: 'zoom_in' };
    if (/^zoom out$/.test(phrase)) return { action: 'zoom_out' };
    return null;
}
