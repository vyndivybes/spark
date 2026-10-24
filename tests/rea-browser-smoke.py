"""Real Chromium behavioral smoke for the shipped notes recipe; no downloads."""
import json
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright

print('Starting installed-browser smoke',flush=True)
checks=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
recipe=Path(__file__).resolve().parents[1]/'backend'/'spark_rea_notes.html'
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True,timeout=15000,args=['--disable-gpu'])
    try:
        context=browser.new_context(offline=True)
        page=context.new_page()
        errors=[]
        page.on('pageerror',lambda error: errors.append(str(error)))
        page.goto(recipe.as_uri())
        results=page.evaluate(checks['behavior'])
        page.reload()
        results.extend(page.evaluate(checks['reload']))
        if errors:raise RuntimeError('Browser errors: '+str(errors))
        print(json.dumps({'state':'PASS','checks':results,'count':len(results),'engine':'installed Edge Chromium, headless, offline, isolated context'}))
    finally:browser.close()

