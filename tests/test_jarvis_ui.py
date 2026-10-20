import os
from pathlib import Path
import pytest


@pytest.mark.skipif(os.environ.get('SPARK_TEST_JARVIS_UI')!='1',reason='Opt-in Chromium check against local Vite')
def test_jarvis_panel_signin_question_and_disconnect():
    from playwright.sync_api import sync_playwright,expect
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={'width':1450,'height':910})
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto('http://localhost:5173/tests/jarvis-view.html')
        page.get_by_role('button',name='Ask VAOS Jarvis',exact=True).click()
        expect(page.get_by_role('status')).to_have_text('Sign in to VAOS first.')
        page.get_by_role('button',name='Open VAOS / sign in',exact=True).click()
        page.get_by_role('button',name='Refresh connection',exact=True).click()
        expect(page.get_by_text('https://vaos.example · Session present; verified on each question')).to_be_visible()
        page.get_by_role('button',name='Ask VAOS Jarvis',exact=True).click()
        expect(page.get_by_role('article',name='Jarvis advisory answer')).to_contain_text('Source evidence HOLD.')
        expect(page.locator('article img')).to_have_count(0)
        page.get_by_role('button',name='Prepare report task',exact=True).click()
        approval=page.get_by_role('button',name='Approve and run these steps',exact=True)
        expect(approval).to_be_enabled()
        assert page.evaluate("window.__pcRequests.every(x=>x.action!=='pc_task_run')")
        approval.click()
        expect(page.get_by_text('Task state: completed',exact=True)).to_be_visible()
        assert page.evaluate("window.__pcRequests.find(x=>x.action==='pc_task_run').payload.approved===true")
        assert page.evaluate("window.__pcRequests.find(x=>x.action==='pc_task_run').payload.plan_hash==='reviewed-fixture-hash'")
        for width,height in ((1450,910),(390,844)):
            page.set_viewport_size({'width':width,'height':height})
            dialog=page.get_by_role('dialog',name='VAOS Jarvis connection')
            box=dialog.bounding_box()
            assert box['x']>=0 and box['x']+box['width']<=width
            evidence=Path(__file__).resolve().parents[1]/'docs/evidence'
            evidence.mkdir(exist_ok=True)
            page.screenshot(path=str(evidence/f'jarvis-panel-{width}.png'))
        page.get_by_role('button',name='Disconnect VAOS',exact=True).click()
        expect(page.get_by_role('article',name='Jarvis advisory answer')).to_have_count(0)
        expect(page.get_by_role('status')).to_have_text('VAOS session removed from Spark.')
        assert not errors,errors
        browser.close()
