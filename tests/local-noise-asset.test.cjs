const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..');

test('cinematic grain is local and cannot depend on a remote asset', () => {
    const components = [
        'src/App.jsx',
        'src/components/MemoryPrompt.jsx',
        'src/components/ConfirmationPopup.jsx',
    ];
    for (const file of components) {
        const source = fs.readFileSync(path.join(root, file), 'utf8');
        assert.doesNotMatch(source, /grainy-gradients\.vercel\.app/, file);
        assert.match(source, /spark-noise/, file);
    }

    const css = fs.readFileSync(path.join(root, 'src/index.css'), 'utf8');
    assert.match(css, /\.spark-noise\s*\{/);
    assert.match(css, /url\("data:image\/svg\+xml,/);
    assert.doesNotMatch(css, /url\(["']?https?:\/\//);
});
