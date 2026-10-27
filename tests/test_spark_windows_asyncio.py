import asyncio
import ast
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_windows_asyncio import accept_with_retry, install_windows_policy


def network_reset():
    error = OSError('pending client disconnected')
    error.winerror = 64
    return error


class AcceptRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_aborted_client_retries_without_closing_listener(self):
        listener = Mock()
        listener.fileno.return_value = 1
        accept = AsyncMock(side_effect=[network_reset(), ('connection', 'address')])
        self.assertEqual(await accept_with_retry(accept, listener), ('connection', 'address'))
        listener.close.assert_not_called()
        self.assertEqual(accept.await_count, 2)

    async def test_other_errors_closed_socket_and_cancellation_propagate(self):
        for error, fd in [(OSError('fatal'), 1), (network_reset(), -1), (asyncio.CancelledError(), 1)]:
            with self.subTest(error=type(error).__name__, fd=fd):
                accept = AsyncMock(side_effect=error)
                listener = Mock()
                listener.fileno.return_value = fd
                with self.assertRaises(type(error)):
                    await accept_with_retry(accept, listener)
                self.assertEqual(accept.await_count, 1)


@unittest.skipUnless(sys.platform == 'win32', 'Windows IOCP test')
class WindowsLoopTests(unittest.TestCase):
    def test_listener_serves_after_reset_and_subprocess_pipes_work(self):
        from asyncio.windows_events import IocpProactor
        original_policy = asyncio.get_event_loop_policy()
        install_windows_policy()
        import uvicorn
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'backend' / 'server.py').read_text(encoding='utf-8'))
        startup = next(node for node in ast.walk(tree) if isinstance(node, ast.Call)
                       and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                       and node.func.value.id == 'uvicorn' and node.func.attr == 'run')
        loop_setting = ast.literal_eval(next(keyword.value for keyword in startup.keywords if keyword.arg == 'loop'))
        loop = uvicorn.Config('unused:app', loop=loop_setting).get_loop_factory()()
        original_accept = IocpProactor.accept
        injected = []

        def accept(proactor, listener):
            if not injected:
                injected.append(True)
                future = loop.create_future()
                future.set_exception(network_reset())
                return future
            return original_accept(proactor, listener)

        async def run():
            async def echo(reader, writer):
                writer.write(await reader.readexactly(4))
                await writer.drain()
                writer.close()
                await writer.wait_closed()

            with patch.object(IocpProactor, 'accept', accept):
                server = await asyncio.start_server(echo, '127.0.0.1', 0)
                try:
                    port = server.sockets[0].getsockname()[1]
                    for _ in range(2):
                        reader, writer = await asyncio.open_connection('127.0.0.1', port)
                        writer.write(b'PASS')
                        await writer.drain()
                        self.assertEqual(await asyncio.wait_for(reader.readexactly(4), 3), b'PASS')
                        writer.close()
                        await writer.wait_closed()
                    child = await asyncio.create_subprocess_exec(sys.executable, '-c', 'print("MCP_PIPE_OK")', stdout=asyncio.subprocess.PIPE)
                    stdout, _ = await child.communicate()
                    self.assertEqual(child.returncode, 0)
                    self.assertEqual(stdout.strip(), b'MCP_PIPE_OK')
                finally:
                    server.close()
                    await server.wait_closed()
                    await asyncio.sleep(0.02)
            self.assertTrue(injected)

        try:
            loop.run_until_complete(run())
        finally:
            loop.close()
            asyncio.set_event_loop_policy(original_policy)
