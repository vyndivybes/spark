"""Keep Windows listeners alive when a pending client disappears.

CPython issue 93821: Proactor's server closes its listening socket on WinError
64 during AcceptEx. Retry that client-level failure while retaining Proactor's
subprocess support for MCP. Other errors and cancellation still propagate.
"""
import asyncio
import sys


async def accept_with_retry(accept, listener):
    while True:
        try:
            return await accept(listener)
        except OSError as error:
            if getattr(error, 'winerror', None) != 64 or listener.fileno() < 0:
                raise
            # Yield between retries so a shutdown or a faulty network cannot spin.
            await asyncio.sleep(0.01)


def create_loop():
    """Uvicorn's explicit loop factory must retain our listener retry behavior."""
    install_windows_policy()
    return asyncio.new_event_loop()


def install_windows_policy():
    if sys.platform != 'win32':
        return
    from asyncio.windows_events import IocpProactor

    class SparkProactor(IocpProactor):
        def accept(self, listener):
            return self._loop.create_task(accept_with_retry(super().accept, listener))

    class SparkProactorLoop(asyncio.ProactorEventLoop):
        def __init__(self):
            super().__init__(proactor=SparkProactor())

    class SparkWindowsPolicy(asyncio.WindowsProactorEventLoopPolicy):
        _loop_factory = SparkProactorLoop

    asyncio.set_event_loop_policy(SparkWindowsPolicy())
