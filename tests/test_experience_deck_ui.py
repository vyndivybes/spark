"""Regression for the deck scrolling above the viewport in the real cockpit."""
import os
from pathlib import Path
import pytest


@pytest.mark.skipif(os.environ.get('SPARK_TEST_DECK_UI')!='1',reason='Opt-in Chromium check against local Vite')
def test_deck_stays_visible_when_cockpit_scrolls_and_jarvis_opens():
    from playwright.sync_api import sync_playwright,expect
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page()
        page.add_init_script("window.__sparkInvocations=[]; window.require=()=>({ipcRenderer:{invoke:async(channel,value)=>{window.__sparkInvocations.push({channel,value});return channel==='spark:open-experience'?{opened:true,reused:false}:'a'.repeat(64);},send(){},on(){},removeListener(){}}});")
        page.route('**/socket.io/**',lambda route:route.abort())
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        for width,height in ((1440,765),(1920,1020),(1024,600)):
            page.set_viewport_size({'width':width,'height':height})
            page.goto('http://localhost:5173/')
            expect(page.get_by_role('button',name='Close Spark',exact=True)).to_be_in_viewport()
            toolbar=page.locator('.spark-toolbar').bounding_box()
            assert toolbar['height']==64
            page.get_by_role('button',name='EXPERIENCE DECK',exact=False).click()
            deck=page.get_by_role('region',name='SPARK experiences')
            expect(deck).to_be_visible()
            # Native focus can scroll an overflow:hidden cockpit. The panel
            # must stay anchored even after this reproduced scroll state.
            page.locator('.spark-cockpit').evaluate('el=>el.scrollTop=500')
            box=deck.bounding_box()
            assert box['y']>=0 and box['y']+box['height']<=height
            assert box['x']>=0 and box['x']+box['width']<=width
            expect(deck.get_by_role('button',name='Close experience deck')).to_be_in_viewport()
            modes=deck.get_by_role('group',name='VAYU Workspace modes')
            expect(modes.get_by_role('button')).to_have_count(3)
            for label in ('Open workspace','Neural Atlas · notes graph','HOLO Deck · hand interaction'):
                button=modes.get_by_role('button',name=label,exact=False)
                button.click()
                expect(button).to_be_enabled()
            launched=page.evaluate("window.__sparkInvocations.filter(x=>x.channel==='spark:open-experience').map(x=>x.value)")
            assert launched==['vayu','brain','holo']
            jarvis=deck.get_by_role('button',name='CONNECTED FOUNDER INTELLIGENCE VAOS JARVIS',exact=False)
            jarvis.scroll_into_view_if_needed()
            expect(jarvis).to_be_in_viewport()
            expect(deck.get_by_role('button',name='Close experience deck')).to_be_in_viewport()
            assert deck.bounding_box()['y']==box['y']
            evidence=Path(__file__).resolve().parents[1]/'docs/evidence'
            evidence.mkdir(exist_ok=True)
            page.screenshot(path=str(evidence/f'experience-deck-{width}.png'))
            jarvis.click()
            expect(page.get_by_role('dialog',name='VAOS Jarvis connection')).to_be_visible()
            expect(deck).to_have_count(0)
        assert not errors,errors
        browser.close()
