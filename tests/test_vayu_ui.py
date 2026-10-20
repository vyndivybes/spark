"""Opt-in real Chromium acceptance for the bundled workspace."""
import os
import importlib.util
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
import pytest
spec = importlib.util.spec_from_file_location('vayu_ui_launcher', Path(__file__).resolve().parents[1] / 'scripts/vayu_launcher.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


@pytest.mark.skipif(os.environ.get('SPARK_TEST_VAYU_UI') != '1', reason='Opt-in local Chromium check')
def test_vayu_rendered_workspace():
    from playwright.sync_api import sync_playwright, expect
    with tempfile.TemporaryDirectory() as folder:
        launcher.upstream.ROOT = Path(folder)
        server = ThreadingHTTPServer(('127.0.0.1', 0), launcher.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={'width': 1450, 'height': 910})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(origin + '/' + launcher.upstream.PAGE)
                add = page.get_by_role('button', name='+ Add action / note', exact=True)
                expect(add).to_be_visible()
                add.click()
                page.locator('dialog input[name=title]').fill('Spark VAYU acceptance outcome')
                page.get_by_role('button', name='Save item', exact=True).click()
                expect(page.get_by_text('Spark VAYU acceptance outcome', exact=True).first).to_be_visible()
                page.reload()
                expect(page.get_by_text('Spark VAYU acceptance outcome', exact=True).first).to_be_visible()
                page.goto(origin + '/views/index.html')
                expect(page.locator('a.viewcard')).to_have_count(12)
                for view in ('operations', 'analytics', 'orbit', 'circle', 'rings', 'graph', 'areas', 'links', 'timeline', 'matrix', 'holo', 'pyramid'):
                    page.goto(origin + '/views/' + view + '.html')
                    frame = page.frame_locator('#view-frame')
                    expect(frame.locator('body')).to_be_visible()
                    if view == 'operations':
                        expect(frame.get_by_text('Spark VAYU acceptance outcome', exact=True).first).to_be_visible()
                page.goto(origin + '/views/index.html')
                for width, height in ((1450, 910), (390, 844)):
                    page.set_viewport_size({'width': width, 'height': height})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    evidence = Path(__file__).resolve().parents[1] / 'docs' / 'evidence'
                    evidence.mkdir(exist_ok=True)
                    page.screenshot(path=str(evidence / f'vayu-views-{width}.png'), full_page=True)
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
