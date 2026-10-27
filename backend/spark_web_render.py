"""Bounded, disposable public-page rendering for JavaScript-only site reads."""
import asyncio
from urllib.parse import urlsplit


async def render_public_page(url):
    from spark_web import fetch_resource, public_url
    public_url(url)
    failures = []
    phase = 'starting_browser_driver'
    try:
        from playwright.async_api import async_playwright
        async with asyncio.timeout(35):
            async with async_playwright() as driver:
                phase = 'launching_isolated_browser'
                browser = await driver.chromium.launch(headless=True)
                try:
                    phase = 'creating_isolated_context'
                    context = await browser.new_context(viewport={'width': 1440, 'height': 900},
                        service_workers='block', accept_downloads=False, permissions=[])
                    budget = {'requests': 0, 'bytes': 0}
                    transfers = asyncio.Semaphore(3)
                    # Browser requests never use its own DNS/cookie transport.
                    # Every GET is fetched through Spark's pinned public-only
                    # connector, including redirects and subresources.
                    async def handle_request(route):
                        request = route.request
                        if request.method != 'GET' or request.resource_type in ('media', 'font'):
                            await route.abort()
                            return
                        budget['requests'] += 1
                        if budget['requests'] > 64 or budget['bytes'] > 12_000_000:
                            await route.abort()
                            return
                        try:
                            _, data, _, kind = await fetch_resource(request.url,
                                max_bytes=min(4_000_000, max(1, 12_000_000-budget['bytes'])), text_only=False)
                            budget['bytes'] += len(data)
                            if budget['bytes'] > 12_000_000:
                                await route.abort()
                                return
                            await route.fulfill(status=200, body=data,
                                headers={'content-type': kind, 'access-control-allow-origin': '*'})
                        except Exception as error:
                            failures.append(type(error).__name__ + ': ' + str(error)[:160])
                            await route.abort()
                    async def route_request(route):
                        async with transfers:
                            await handle_request(route)
                    await context.route('**/*', route_request)
                    await context.route_web_socket('**/*', lambda ws: ws.close())
                    page = await context.new_page()
                    page.on('pageerror', lambda error: failures.append(str(error)[:200]))
                    page.on('console', lambda message: failures.append(message.text[:200]) if message.type == 'error' else None)
                    phase = 'loading_public_page'
                    await page.goto(url, wait_until='domcontentloaded', timeout=25000)
                    try:
                        await page.wait_for_function("document.body && (document.body.innerText.trim().length > 40 || document.querySelector('canvas'))", timeout=9000)
                    except Exception:
                        pass  # Preserve metadata and observed loading failures.
                    phase = 'reading_rendered_content'
                    data = await page.evaluate('''() => ({
                        text: (document.body?.innerText || '').slice(0,14001),
                        title: document.title,
                        canvas_count: document.querySelectorAll('canvas').length,
                        headings: [...document.querySelectorAll('h1,h2,h3')].slice(0,15).map(e=>e.innerText.slice(0,160)),
                        links: [...document.querySelectorAll('a[href]')].filter(e=>e.innerText.trim()).slice(0,20).map(e=>({text:e.innerText.slice(0,120),url:e.href})),
                        animated_elements: [...document.querySelectorAll('body *')].slice(0,300).filter(e=>getComputedStyle(e).animationName!=='none').length
                    })''')
                    return {'ok': bool(data['text'].strip() or data['canvas_count']),
                            **data, 'text': data['text'][:14000], 'truncated': len(data['text']) > 14000,
                            'resource_failures': failures[:5],
                            'scope': 'Observed rendered DOM and layout signals only. Canvas pixels, interactions and private backend behavior are not verified.'}
                finally:
                    phase = 'closing_isolated_browser'
                    await browser.close()
    except Exception as error:
        return {'ok': False, 'failure_type': type(error).__name__, 'phase': phase, 'resource_failures': failures[:5],
                'error': 'The isolated page renderer was unavailable, blocked, or exceeded its resource budget.'}
