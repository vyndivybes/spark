"""Local browser sessions. No microphone, cloud model, or API key required."""
import asyncio
import base64
import contextlib
import time
from urllib.parse import quote_plus, urlsplit


def destination(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 4096:
        raise ValueError("Enter a URL or search text, up to 4096 characters.")
    text = text.strip()
    if "://" not in text and "." in text and " " not in text:
        text = "https://" + text
    parsed = urlsplit(text)
    if parsed.scheme:
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("Only HTTP and HTTPS URLs are supported.")
        return text
    return "https://www.google.com/search?q=" + quote_plus(text)



# Chrome executes scrolling in its own animation frame; the screenshot stream is
# merely an observation channel, not the timer for browser movement.
PRESENTATION_SPEEDS = {"slow": 120, "normal": 240, "fast": 420}

_PRESENTATION_START = r"""({direction, speed}) => {
    const previous = window.__sparkPresenter;
    if (previous) {
        previous.active = false;
        window.cancelAnimationFrame(previous.frame);
    }
    const state = {velocity: (direction === 'down' ? 1 : -1) * speed,
                   active: true, paused: false, frame: 0, last: null};
    const tick = (timestamp) => {
        if (window.__sparkPresenter !== state || !state.active || state.paused) return;
        const max = Math.max(document.body?.scrollHeight || 0,
                             document.documentElement?.scrollHeight || 0) - window.innerHeight;
        const end = state.velocity > 0
            ? window.scrollY >= Math.max(0, max) - 1 : window.scrollY <= 1;
        if (end) { state.active = false; return; }
        if (state.last !== null) {
            // Cap gaps after hidden-tab throttling to avoid jumping several screens.
            const seconds = Math.min(0.1, (timestamp - state.last) / 1000);
            window.scrollBy(0, state.velocity * Math.max(0, seconds));
        }
        state.last = timestamp;
        state.frame = window.requestAnimationFrame(tick);
    };
    state.tick = tick;
    window.__sparkPresenter = state;
    state.frame = window.requestAnimationFrame(tick);
    return true;
}"""

_PRESENTATION_CONTROL = r"""(action) => {
    const state = window.__sparkPresenter;
    if (!state) return false;
    if (action === 'pause_scroll') {
        state.paused = true;
        window.cancelAnimationFrame(state.frame);
    } else if (action === 'resume_scroll' && state.active) {
        state.paused = false;
        state.last = null;
        window.cancelAnimationFrame(state.frame);
        state.frame = window.requestAnimationFrame(state.tick);
    } else if (action === 'stop_scroll') {
        state.active = false;
        state.paused = false;
        window.cancelAnimationFrame(state.frame);
    } else if (action === 'speed_up' || action === 'slow_down') {
        const factor = action === 'speed_up' ? 1.5 : (1 / 1.5);
        state.velocity = Math.sign(state.velocity) *
                         Math.max(60, Math.min(720, Math.abs(state.velocity) * factor));
    }
    return true;
}"""

_PRESENTATION_ZOOM = r"""(direction) => {
    const root = document.documentElement;
    const current = parseFloat(root.style.zoom) || 1;
    const next = Math.max(0.75, Math.min(1.5,
        Math.round((current + (direction === 'in' ? 0.1 : -0.1)) * 100) / 100));
    root.style.zoom = String(next);
    return next;
}"""


class BrowserSessions:
    def __init__(self, sio, allowed, launcher=None, interval=0.5):
        self.sio, self.allowed = sio, allowed
        self.launcher, self.interval = launcher, interval
        self.sessions = {}
        self.lock = asyncio.Lock()

    async def status(self, sid, session_id, state, message):
        await self.sio.emit("web_browser_status", {
            "session_id": session_id, "state": state, "message": message,
        }, room=sid)

    async def start(self, sid, data=None):
        data = data if isinstance(data, dict) else {}
        session_id = data.get("session_id")
        if not isinstance(session_id, str) or not 1 <= len(session_id) <= 100:
            return
        async with self.lock:
            current = self.sessions.get(sid)
            if current and current["id"] == session_id and not current["task"].done():
                return
            await self._stop(sid)
            if not self.allowed(sid):
                await self.status(sid, session_id, "error", "Authenticate and enable Web Agent in Settings.")
                return
            session = {"id": session_id, "queue": asyncio.Queue(maxsize=20), "presenting": False, "last_check": 0}
            self.sessions[sid] = session
            session["task"] = asyncio.create_task(self._run(sid, session))

    async def _stop(self, sid):
        session = self.sessions.pop(sid, None)
        if session:
            session["task"].cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await session["task"]

    async def stop(self, sid, data=None):
        async with self.lock:
            session = self.sessions.get(sid)
            # A delayed close must not stop a newer view.
            if data is not None and (not isinstance(data, dict) or not session
                                     or data.get("session_id") != session["id"]):
                return
            await self._stop(sid)

    async def close(self):
        async with self.lock:
            for sid in list(self.sessions):
                await self._stop(sid)

    async def command(self, sid, data):
        session = self.sessions.get(sid)
        if not session or not isinstance(data, dict) or data.get("session_id") != session["id"]:
            return
        if not self.allowed(sid):
            await self.stop(sid)
            await self.status(sid, session["id"], "error", "Browser access is disabled. Re-enable it and retry.")
            return
        if session["task"].done():
            await self.status(sid, session["id"], "error", "Browser stopped. Select Retry.")
            return
        try:
            session["queue"].put_nowait(data)
        except asyncio.QueueFull:
            await self.status(sid, session["id"], "ready", "Browser is busy. Wait before sending another command.")

    async def _apply(self, page, data):
        action = data.get("action", "navigate")
        if action == "navigate":
            await page.goto(destination(data.get("text", data.get("prompt"))), wait_until="domcontentloaded", timeout=20000)
        elif action == "back":
            await page.go_back(wait_until="domcontentloaded", timeout=20000)
        elif action == "forward":
            await page.go_forward(wait_until="domcontentloaded", timeout=20000)
        elif action == "reload":
            await page.reload(wait_until="domcontentloaded", timeout=20000)
        elif action == "click":
            x, y = data.get("x"), data.get("y")
            if not all(type(v) in (int, float) and 0 <= v <= 1 for v in (x, y)):
                raise ValueError("Invalid browser coordinates.")
            await page.mouse.click(x * 1440, y * 900)
        elif action == "type":
            text = data.get("text")
            if not isinstance(text, str) or len(text) > 4096:
                raise ValueError("Text must be at most 4096 characters.")
            await page.keyboard.insert_text(text)
        elif action == "key" and data.get("key") in ("Enter", "Tab", "Backspace", "Escape", "ArrowDown", "ArrowUp"):
            await page.keyboard.press(data["key"])
        elif action == "scroll" and data.get("direction") in ("up", "down"):
            await page.mouse.wheel(0, 600 if data["direction"] == "down" else -600)
        elif action == "present_scroll":
            direction = data.get("direction")
            speed = data.get("speed", "slow")
            if direction not in ("up", "down") or not isinstance(speed, str) or speed not in PRESENTATION_SPEEDS:
                raise ValueError("Choose up/down and slow/normal/fast presentation speed.")
            await page.evaluate(_PRESENTATION_START, {
                "direction": direction, "speed": PRESENTATION_SPEEDS[speed],
            })
        elif action in ("pause_scroll", "resume_scroll", "stop_scroll", "speed_up", "slow_down"):
            await page.evaluate(_PRESENTATION_CONTROL, action)
        elif action in ("zoom_in", "zoom_out"):
            await page.evaluate(_PRESENTATION_ZOOM, "in" if action == "zoom_in" else "out")
        else:
            raise ValueError("Unsupported browser command.")

    async def _run(self, sid, session):
        driver = browser = None
        session_id = session["id"]
        try:
            await self.status(sid, session_id, "starting", "Starting local Chromium...")
            if self.launcher:
                driver, browser = await self.launcher()
            else:
                from playwright.async_api import async_playwright
                driver = await async_playwright().start()
                browser = await asyncio.wait_for(driver.chromium.launch(headless=True), 30)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            page.set_default_timeout(10000)
            await page.set_content("<html><body style='background:#101820;color:#eee;font:32px sans-serif;padding:60px'><h1>SPARK local browser</h1><p>Enter a URL or search above to begin.</p><p>Click the view, then use Type to fill a field.</p></body></html>")
            await self.status(sid, session_id, "ready", "Local browser ready. URL and search need no AI key.")
            while True:
                if not self.allowed(sid):
                    raise PermissionError("Browser access is disabled. Authenticate and retry.")
                if page.is_closed():
                    raise RuntimeError("The browser page closed. Select Retry.")
                if session["presenting"] and time.monotonic() - session["last_check"] > 2:
                    session["last_check"] = time.monotonic()
                    session["presenting"] = bool(await page.evaluate(
                        "() => Boolean(window.__sparkPresenter?.active && !window.__sparkPresenter?.paused)"
                    ))
                frame = await page.screenshot(type="jpeg", quality=65, timeout=10000)
                await self.sio.emit("web_browser_frame", {
                    "session_id": session_id, "image": base64.b64encode(frame).decode("ascii"),
                    "mime_type": "image/jpeg", "url": page.url,
                }, room=sid)
                try:
                    data = await asyncio.wait_for(
                        session["queue"].get(), min(self.interval, 0.20) if session["presenting"] else self.interval
                    )
                except asyncio.TimeoutError:
                    continue
                try:
                    await self.status(sid, session_id, "busy", "Loading browser action...")
                    await self._apply(page, data)
                    action = data.get("action", "navigate")
                    if action == "present_scroll":
                        session["presenting"] = True
                        session["last_check"] = time.monotonic()
                    elif action in ("pause_scroll", "stop_scroll", "navigate", "back", "forward", "reload"):
                        session["presenting"] = False
                    elif action == "resume_scroll":
                        session["presenting"] = True
                    await self.status(sid, session_id, "ready", "Browser ready.")
                except Exception as exc:
                    # Navigation failures are recoverable; retain the live page.
                    await self.status(sid, session_id, "ready", f"Action failed: {exc}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.status(sid, session_id, "error", (
                f"Local browser unavailable: {exc}. In SPARK's Python environment run "
                "python -m pip install playwright then python -m playwright install chromium. Select Retry."
            ))
        finally:
            if browser:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(browser.close(), 5)
            if driver:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(driver.stop(), 5)


def register_browser_sessions(sio, allowed):
    sessions = BrowserSessions(sio, allowed)
    sio.on("start_web_browser", sessions.start)
    sio.on("stop_web_browser", sessions.stop)
    sio.on("web_browser_command", sessions.command)
    return sessions
