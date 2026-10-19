"""Persistent REA MCP client. One task owns the stdio session and its cleanup."""
import asyncio
import json
import os
import shutil
from datetime import timedelta
from contextlib import asynccontextmanager


class ReaError(ValueError):
    pass


def validate_schema_references(schema,depth=0):
    if depth>32:
        raise ReaError('Tool schema nesting exceeds its limit.')
    if isinstance(schema,dict):
        for key,value in schema.items():
            if key in ('$ref','$dynamicRef') and (not isinstance(value,str) or not (value=='#' or value.startswith('#/'))):
                raise ReaError('External tool schema references are prohibited.')
            validate_schema_references(value,depth+1)
    elif isinstance(schema,list):
        for value in schema:
            validate_schema_references(value,depth+1)


class ReaClient:
    def __init__(self, command=None, args=None, env=None, *, url=None, headers=None):
        self.queue = asyncio.Queue(maxsize=8)
        self.worker = None
        self.command, self.args, self.env = command, args, env
        self.url,self.headers=url,headers

    @asynccontextmanager
    async def _transport(self,params):
        if self.url:
            import httpx
            from mcp.client.streamable_http import streamable_http_client
            async with httpx.AsyncClient(headers=self.headers or {},timeout=120,trust_env=False,follow_redirects=False) as client:
                async with streamable_http_client(self.url,http_client=client) as (read,write,_):
                    yield read,write
        else:
            from mcp.client.stdio import stdio_client
            async with stdio_client(params) as streams:
                yield streams

    async def request(self, action, payload):
        if self.worker is None or self.worker.done():
            self.worker = asyncio.create_task(self._serve())
        future = asyncio.get_running_loop().create_future()
        try:
            self.queue.put_nowait((action, payload, future))
        except asyncio.QueueFull:
            raise ReaError("REA is busy; wait for pending operations.") from None
        try:
            return await asyncio.wait_for(future, 150)
        except asyncio.TimeoutError:
            await self.close()
            raise ReaError("REA operation timed out.") from None
        except asyncio.CancelledError:
            await self.close()
            raise

    async def close(self):
        if self.worker:
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)

    async def _serve(self):
        current = None
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            from jsonschema import Draft202012Validator
            # Host configuration only. Never accept executable paths from a socket.
            command = self.command or os.environ.get("SPARK_REA_COMMAND")
            args = self.args if self.args is not None else json.loads(os.environ.get("SPARK_REA_ARGS", "[]"))
            if not isinstance(args, list) or any(not isinstance(a, str) for a in args):
                raise ReaError("SPARK_REA_ARGS must be a JSON array of strings.")
            if not command:
                if os.name == "nt":
                    command = os.environ.get("COMSPEC", "cmd.exe")
                    args = ["/d", "/c", "npx", "--offline", "-y", "rea-agents@6.5.0", "mcp"]
                else:
                    command = shutil.which("npx") or "npx"
                    args = ["--offline", "-y", "rea-agents@6.5.0", "mcp"]
            params = StdioServerParameters(command=command, args=args, env=self.env)
            async with self._transport(params) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=120)) as session:
                    await session.initialize()
                    tools = {}
                    while True:
                        action, payload, current = await self.queue.get()
                        if current.cancelled():
                            continue
                        try:
                            if action == "rea_discover" or not tools:
                                cursor = None
                                discovered = {}
                                for _ in range(32):
                                    page = await session.list_tools(cursor=cursor)
                                    discovered.update({t.name: t.model_dump(by_alias=True, exclude_none=True) for t in page.tools})
                                    cursor = page.nextCursor
                                    if not cursor:
                                        break
                                else:
                                    raise ReaError("REA tool catalog pagination limit exceeded.")
                                tools = discovered
                            if action == "rea_discover":
                                value = list(tools.values())
                            elif action == "rea_call":
                                name, arguments = payload.get("name"), payload.get("arguments")
                                if name not in tools or not isinstance(arguments, dict):
                                    raise ReaError("Discover and select a valid REA tool and arguments.")
                                validate_schema_references(tools[name]['inputSchema'])
                                Draft202012Validator.check_schema(tools[name]['inputSchema'])
                                errors = list(Draft202012Validator(tools[name]["inputSchema"]).iter_errors(arguments))
                                if errors:
                                    raise ReaError("Arguments do not match the discovered REA tool schema.")
                                result = await session.call_tool(name, arguments)
                                value = result.model_dump(by_alias=True, exclude_none=True)
                            else:
                                raise ReaError("Unknown REA operation.")
                            if len(json.dumps(value).encode()) > 4_000_000:
                                raise ReaError("REA result exceeds 4 MB. Request a narrower result.")
                            if not current.done():
                                current.set_result(value)
                        except (ReaError, ValueError) as error:
                            if not current.done():
                                current.set_exception(ReaError(str(error)[:200]))
                        current = None
        except asyncio.CancelledError:
            raise
        except Exception:
            if current is not None and not current.done():
                current.set_exception(ReaError("REA connection failed. Check the installed MCP runtime and host configuration."))
        finally:
            if current is not None and not current.done():
                current.set_exception(ReaError("REA connection closed."))
            while not self.queue.empty():
                _, _, future = self.queue.get_nowait()
                if not future.done():
                    future.set_exception(ReaError("REA connection closed. Discover tools to reconnect."))
