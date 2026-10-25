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
                page.get_by_role('link', name='Knowledge visualizations', exact=False).click()
                expect(page.locator('a.viewcard')).to_have_count(12)
                for view in ('operations', 'analytics', 'orbit', 'circle', 'rings', 'graph', 'areas', 'links', 'timeline', 'matrix', 'holo', 'pyramid'):
                    page.goto(origin + '/views/' + view + '.html')
                    expect(page.locator('iframe')).to_have_count(1)
                    frame = page.frame_locator('#view-frame')
                    expect(frame.locator('body')).to_be_visible()
                    expect(frame.locator('iframe')).to_have_count(0)
                    assert page.locator('.nav a[aria-current="page"]').count() == 1
                    if view == 'operations':
                        expect(frame.get_by_text('Spark VAYU acceptance outcome', exact=True).first).to_be_visible()
                        expect(frame.get_by_role('button', name='Projects', exact=True)).to_be_visible()
                        frame.get_by_role('button', name='Projects', exact=True).click()
                        expect(frame.get_by_role('heading', name='Projects', exact=True)).to_be_visible()
                        frame.get_by_role('button', name='Founder Desk', exact=True).click()
                        assert frame.locator('html').evaluate('(el) => el.classList.contains("embedded-workspace")')
                        # An embedded workspace must never open another page wrapper inside itself.
                        targets = frame.locator('a[href="./views/index.html"]').evaluate_all('(links) => links.map(a => a.target)')
                        assert targets and all(target == '_top' for target in targets)
                        frame.get_by_role('link', name='Spark project data', exact=False).click()
                        expect(page).to_have_url(origin + '/spark')
                        expect(page.locator('iframe')).to_have_count(0)
                # Exercise repeated menu/view transitions: frame depth must stay constant.
                for _ in range(2):
                    page.get_by_role('link', name='Visual library', exact=False).click()
                    expect(page.locator('iframe')).to_have_count(0)
                    page.locator('a.viewcard[href="operations.html"]').click()
                    expect(page.locator('iframe')).to_have_count(1)
                    expect(page.frame_locator('#view-frame').locator('#workspace')).to_be_visible()
                evidence = Path(os.environ.get('SPARK_VAYU_EVIDENCE_DIR', Path(__file__).resolve().parents[1] / 'docs' / 'evidence'))
                evidence.mkdir(parents=True, exist_ok=True)
                for width, height in ((1450, 910), (390, 844)):
                    page.set_viewport_size({'width': width, 'height': height})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    assert page.locator('#view-frame').bounding_box()['height'] >= height - 65
                    assert page.frame_locator('#view-frame').locator('html').evaluate('(el) => el.scrollWidth <= innerWidth')
                    expect(page.frame_locator('#view-frame').get_by_role('heading', name='Founder Desk', exact=True)).to_be_in_viewport()
                    page.screenshot(path=str(evidence / f'vayu-command-desk-{width}.png'), full_page=True)
                    if width == 390:
                        menu = page.get_by_role('button', name='Views', exact=False)
                        menu.click()
                        expect(menu).to_have_attribute('aria-expanded', 'true')
                        page.locator('.nav a[href="graph.html"]').click()
                        expect(page.locator('.intro h1')).to_have_text('Graph')
                page.goto(origin + '/views/index.html')
                for width, height in ((1450, 910), (390, 844)):
                    page.set_viewport_size({'width': width, 'height': height})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    page.screenshot(path=str(evidence / f'vayu-views-{width}.png'), full_page=True)
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
