import os
from pathlib import Path
import pytest


@pytest.mark.skipif(os.environ.get('SPARK_TEST_REPO_UI') != '1', reason='Opt-in Chromium check against local Vite')
def test_repository_analysis_stage_review_activation_and_rollback():
    from playwright.sync_api import sync_playwright, expect
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1450, 'height': 980})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://localhost:5173/tests/evolution-view.html')
        analyze = page.get_by_role('button', name='Analyze repository with model')
        expect(analyze).to_be_disabled()
        page.get_by_label('Repository directory', exact=True).fill('C:/reference')
        page.get_by_label('Repository upgrade goal').fill('Improve caching')
        page.get_by_label('Repository reference paths').fill('cache.py')
        analyze.click()
        expect(page.get_by_role('heading', name='Bound repeated calculations')).to_be_visible()
        page.get_by_role('button', name='Generate staged Spark upgrade').click()
        expect(page.get_by_text('b' * 24 + ': staged', exact=True)).to_be_visible()
        assert page.evaluate("window.__evolutionRequests.every(r=>r.action!=='test_repair_candidate'&&r.action!=='activate_repair_candidate')")
        page.get_by_text('Inspect complete replacements', exact=True).click()
        expect(page.get_by_role('group').filter(has_text='Inspect complete replacements').locator('pre')).to_contain_text('"value = 2"')
        for width, height in ((1450, 980), (390, 844)):
            page.set_viewport_size({'width': width, 'height': height})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            evidence = Path(__file__).resolve().parents[1] / 'docs' / 'evidence'
            evidence.mkdir(exist_ok=True)
            page.screenshot(path=str(evidence / f'repository-upgrade-{width}.png'), full_page=True)
        page.on('dialog', lambda dialog: dialog.accept())
        page.get_by_role('button', name='Approve local tests').click()
        expect(page.get_by_role('button', name='Approve activation')).to_be_visible()
        page.get_by_role('button', name='Approve activation').click()
        expect(page.get_by_role('button', name='Roll back', exact=True)).to_be_visible()
        page.get_by_role('button', name='Roll back', exact=True).click()
        expect(page.get_by_role('status')).to_contain_text('rolled_back')
        assert page.evaluate("window.__evolutionRequests.find(r=>r.action==='test_repair_candidate').payload.approved === true")
        assert not errors, errors
        browser.close()
