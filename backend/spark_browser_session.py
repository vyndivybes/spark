"""Local browser sessions. No microphone, cloud model, or API key required."""
import asyncio
import base64
import contextlib
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
            session = {"id": session_id, "queue": asyncio.Queue(maxsize=20)}
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
                frame = await page.screenshot(type="jpeg", quality=65, timeout=10000)
                await self.sio.emit("web_browser_frame", {
                    "session_id": session_id, "image": base64.b64encode(frame).decode("ascii"),
                    "mime_type": "image/jpeg", "url": page.url,
                }, room=sid)
                try:
                    data = await asyncio.wait_for(session["queue"].get(), self.interval)
                except asyncio.TimeoutError:
                    continue
                try:
                    await self.status(sid, session_id, "busy", "Loading browser action...")
                    await self._apply(page, data)
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
