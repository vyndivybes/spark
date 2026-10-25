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
                expect(page.locator('#visual-mode')).to_be_visible()
                page.locator('#visual-tools > summary').click()
                page.get_by_role('link', name='Action register', exact=False).click()
                add = page.get_by_role('button', name='+ Add action / note', exact=True)
                expect(add).to_be_visible()
                add.click()
                page.locator('dialog input[name=title]').fill('Spark VAYU acceptance outcome')
                page.get_by_role('button', name='Save item', exact=True).click()
                expect(page.get_by_text('Spark VAYU acceptance outcome', exact=True).first).to_be_visible()
                page.reload()
                expect(page.get_by_text('Spark VAYU acceptance outcome', exact=True).first).to_be_visible()
                page.get_by_role('link', name='Knowledge visualizations', exact=False).click()
                expect(page.locator('#visual-mode')).to_be_visible()
                expect(page.locator('iframe')).to_have_count(0)
                expect(page.locator('#visual-mode option')).to_have_count(10)
                expect(page.locator('.visual-primary [aria-pressed="true"]')).to_have_count(1)
                # Switching projections keeps the same document, source focus and engine.
                page.locator('#visual-focus').select_option('VYNDI OS')
                document_id = page.evaluate('performance.timeOrigin')
                for view in ('orbit', 'circle', 'rings', 'graph', 'areas', 'links', 'timeline', 'matrix', 'holo', 'pyramid'):
                    page.locator('#visual-mode').select_option(view)
                    expect(page.locator('#visual-mode')).to_have_value(view)
                    assert page.evaluate('window.VAYU_PROJECTION.getState().mode') == view
                    assert page.evaluate('window.VAYU_PROJECTION.getState().focusId') == 'VYNDI OS'
                    assert page.evaluate('performance.timeOrigin') == document_id
                    expect(page.locator('iframe')).to_have_count(0)
                page.locator('#visual-mode').select_option('graph')
                zoom = page.evaluate('window.VYNDI_ALT_CONTROL.info().zoom')
                page.get_by_role('button', name='Zoom in', exact=True).click()
                assert page.evaluate('window.VYNDI_ALT_CONTROL.info().zoom') > zoom
                page.reload()
                expect(page.locator('#visual-mode')).to_have_value('graph')
                # Legacy entry points no longer build catalogues or page frames.
                for view in ('index', 'circle', 'matrix'):
                    page.goto(origin + '/views/' + view + '.html')
                    expect(page.locator('#visual-mode')).to_be_visible()
                    expect(page.locator('iframe')).to_have_count(0)
                    expect(page.locator('#visual-mode')).to_have_value('graph' if view == 'index' else view)
                page.goto(origin + '/views/operations.html')
                expect(page.get_by_text('Spark VAYU acceptance outcome', exact=True).first).to_be_visible()
                page.goto(origin + '/views/analytics.html')
                expect(page.locator('#workspace')).to_be_visible()
                page.goto(origin + '/views/index.html')
                page.locator('#visual-mode').select_option('graph')
                page.locator('#visual-focus').select_option('VYNDI OS')
                expect(page.locator('#visual-inspector')).to_be_visible()
                page.get_by_role('button', name='Details', exact=True).click()
                expect(page.locator('#visual-inspector')).to_be_hidden()
                page.get_by_role('button', name='Data & import', exact=True).click()
                expect(page.locator('#visual-data-panel')).to_be_visible()
                page.keyboard.press('Escape')
                expect(page.locator('#visual-data-panel')).to_be_hidden()
                page.locator('#visual-focus').select_option('enterprise')
                page.get_by_role('button', name='Details', exact=True).click()
                evidence = Path(os.environ.get('SPARK_VAYU_EVIDENCE_DIR', Path(__file__).resolve().parents[1] / 'docs' / 'evidence'))
                evidence.mkdir(parents=True, exist_ok=True)
                for width, height in ((1450, 910), (390, 844)):
                    page.set_viewport_size({'width': width, 'height': height})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    assert page.locator('main.layout .stage').bounding_box()['height'] >= 300
                    expect(page.locator('#visual-mode')).to_be_in_viewport()
                    expect(page.locator('#visual-toolbar')).to_be_in_viewport()
                    expect(page.locator('.qw-sidebar')).to_be_hidden()
                    expect(page.locator('#studio-nav')).to_be_hidden()
                    page.screenshot(path=str(evidence / f'vayu-studio-{width}.png'), full_page=True)
                    page.get_by_role('button', name='Details', exact=True).click()
                    expect(page.locator('#visual-inspector')).to_be_in_viewport()
                    page.get_by_role('button', name='Details', exact=True).click()
                assert page.evaluate('window.VYNDI_GESTURE_STATUS?.getState().active || false') is False
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
