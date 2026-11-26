const test = require('node:test');
const assert = require('node:assert/strict');
const {createPhoneUsbBridge} = require('../electron/phone-usb-bridge.cjs');

test('phone controls need separate approval and only dispatch an authenticated fixed command once', async () => {
    const token = 'a'.repeat(64);
    const code = '84012011';
    const commands = [];
    const bridge = createPhoneUsbBridge({
        port: 0,
        generateCode: () => code,
        generateToken: () => token,
        mobileControl: async command => {
            commands.push(command);
            return true;
        }
    });
    const {port} = await bridge.start();
    const post = (route, payload, secret = token) => fetch(
        'http://127.0.0.1:' + port + route, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + secret},
            body: JSON.stringify(payload)
        }
    );
    const request = {sequence: 1, command: 'open-whatsapp'};
    try {
        assert.equal((await post('/pair', {code})).status, 200);
        bridge.setAiEnabled(true);
        assert.equal((await post('/mobile-control', request)).status, 403);
        bridge.setControlEnabled(true);
        assert.equal((await post('/mobile-control', request, 'b'.repeat(64))).status, 403);
        assert.equal((await post('/mobile-control', {...request, command: 'powershell'})).status, 422);
        assert.equal((await post('/mobile-control', {...request, args: ['ignored']})).status, 422);
        const response = await post('/mobile-control', request);
        assert.deepEqual(await response.json(), {ok: true, accepted: true, sequence: 1});
        assert.equal((await post('/mobile-control', request)).status, 409);
        bridge.setControlEnabled(false);
        assert.equal((await post('/mobile-control', {...request, sequence: 2})).status, 403);
        assert.deepEqual(commands, ['open-whatsapp']);
    } finally {
        await bridge.stop();
    }
    assert.equal(bridge.status().controlEnabled, false);
});
