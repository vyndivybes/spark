"""Browser interaction acceptance using a fixture socket, never a cloud model."""
import os
from pathlib import Path
import subprocess
import tempfile
import pytest


@pytest.mark.skipif(os.environ.get('SPARK_TEST_REPOSITORY_SCREEN') != '1', reason='Opt-in Chromium interaction check')
def test_repository_preview_analysis_reopen_stage_errors_and_workspace_isolation():
    from playwright.sync_api import sync_playwright, expect
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='spark-repository-ui-') as folder, sync_playwright() as p:
        bundle = Path(folder) / 'fixture.js'
        # Use installed esbuild and compiled production styles. Route the fixture
        # in-process so browser verification needs no running SPARK/Vite server.
        subprocess.run(['node', '-e', "require('esbuild').buildSync({entryPoints:['tests/repository-screen-view.jsx'],bundle:true,format:'iife',loader:{'.css':'empty'},outfile:process.argv[1]})", str(bundle)], cwd=root, check=True)
        styles = next((root / 'dist' / 'assets').glob('index-*.css')).read_text(encoding='utf-8')
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1450, 'height': 980})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        def fixture_route(route):
            if route.request.url.endswith('/fixture.js'):
                route.fulfill(content_type='application/javascript', body=bundle.read_text(encoding='utf-8'))
            else:
                route.fulfill(content_type='text/html', body='<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><style>' + styles + '</style></head><body><div id="root"></div><script src="/fixture.js"></script></body></html>')
        page.route('http://spark.test/**', fixture_route)
        page.goto('http://spark.test/')
        expect(page.get_by_text('No saved analyses in this workspace yet.')).to_be_visible()
        analyze = page.get_by_role('button', name='Analyze repository with model', exact=True)
        expect(analyze).to_be_disabled()
        page.get_by_label('Repository path or GitHub URL').fill('C:/reference')
        page.get_by_role('button', name='Preview source without model').click()
        expect(page.get_by_role('region', name='Repository source preview')).to_contain_text('1 sampled file(s)')
        assert page.evaluate("!window.__repositoryRequests.some(r=>r.action==='analyze_repository')")
        page.get_by_label('Repository upgrade goal').fill('Improve caching')
        analyze.click()
        expect(page.get_by_text('Use a bounded cache.', exact=True)).to_be_visible()
        page.get_by_role('button', name='Improve caching', exact=True).click()
        expect(page.get_by_label('Reference paths', exact=True)).to_have_value('cache.py')
        expect(page.get_by_label('Repository path or GitHub URL')).to_have_value('https://github.com/example/repo')
        expect(page.get_by_text('Acceptance check: Cache size stays within capacity.')).to_be_visible()
        page.get_by_role('button', name='Generate staged Spark upgrade', exact=True).click()
        review = page.get_by_role('region', name='Repository upgrade review')
        expect(review).to_contain_text('Upgrade status: staged')
        assert page.evaluate("!window.__repositoryRequests.some(r=>['test_repair_candidate','activate_repair_candidate'].includes(r.action))")
        review.get_by_text('Inspect complete replacements', exact=True).click()
        expect(review.locator('pre')).to_contain_text('value = 2')
        page.on('dialog', lambda dialog: dialog.accept())
        review.get_by_role('button', name='Approve local tests').click()
        expect(review.get_by_role('button', name='Approve activation')).to_be_visible()
        page.get_by_label('GitHub URL', exact=True).fill('https://github.com/example/repo')
        page.get_by_role('button', name='Import license and dependency evidence').click()
        expect(page.get_by_role('status')).to_contain_text('Clone timed out')
        for width in (1450, 390):
            page.set_viewport_size({'width':width, 'height':980})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.get_by_role('button', name='Switch test workspace').click()
        expect(page.get_by_text('No saved analyses in this workspace yet.')).to_be_visible()
        expect(page.get_by_text('Use a bounded cache.', exact=True)).to_have_count(0)
        expect(review.get_by_text('Upgrade status: tested')).to_have_count(0)
        assert not errors, errors
        browser.close()
