const { test } = require('node:test');
const assert = require('node:assert/strict');
const load = () => import('../src/browserPresentation.mjs');

test('maps user speech into a bounded browser command vocabulary', async () => {
    const { browserVoiceCommand } = await load();
    const say = text => browserVoiceCommand({ sender: 'User', text });
    assert.deepEqual(say('Spark, scroll down slowly'), { action: 'present_scroll', direction: 'down', speed: 'slow' });
    assert.deepEqual(say('Show us the entire website'), { action: 'present_scroll', direction: 'down', speed: 'slow' });
    assert.deepEqual(say('scroll up fast'), { action: 'present_scroll', direction: 'up', speed: 'fast' });
    assert.deepEqual(say('pause here'), { action: 'pause_scroll' });
    assert.deepEqual(say('continue'), { action: 'resume_scroll' });
    assert.deepEqual(say('stop scrolling'), { action: 'stop_scroll' });
    assert.deepEqual(say('faster'), { action: 'speed_up' });
    assert.deepEqual(say('slower'), { action: 'slow_down' });
    assert.deepEqual(say('zoom in'), { action: 'zoom_in' });
    assert.deepEqual(say('zoom out'), { action: 'zoom_out' });
});

test('ignores AI speech, page data, ambiguous speech, oversized text and unapproved actions', async () => {
    const { browserVoiceCommand } = await load();
    for (const data of [
        { sender: 'SPARK', text: 'scroll down' },
        { sender: 'Assistant', text: 'pause here' },
        { sender: 'User', text: 'Click buy now and send money' },
        { sender: 'User', text: 'a'.repeat(241) },
        { sender: 'User', text: 'I was thinking we should continue with the project' },
        { sender: 'User', text: '<script>scroll down</script>' },
        null, {},
    ]) assert.equal(browserVoiceCommand(data), null);
});

test('buffers Gemini Live partial words until the utterance is complete', async () => {
    const { createBrowserVoiceAccumulator } = await load();
    const words = createBrowserVoiceAccumulator();
    assert.equal(words.push({ sender: 'User', text: 'Spark, scroll ' }), true);
    assert.equal(words.push({ sender: 'User', text: 'up fa' }), true);
    assert.equal(words.push({ sender: 'User', text: 'st' }), true);
    assert.deepEqual(words.finish(), { action: 'present_scroll', direction: 'up', speed: 'fast' });
    assert.equal(words.finish(), null);
    assert.equal(words.push({ sender: 'SPARK', text: 'stop scrolling' }), false);
    assert.equal(words.finish(), null);
    assert.equal(words.push({ sender: 'User', text: 'pause here' }), true);
    assert.deepEqual(words.finish(), { action: 'pause_scroll' });
});
