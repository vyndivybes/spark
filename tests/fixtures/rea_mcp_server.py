"""Local MCP transport fixture; deliberately maintains state between calls."""
from mcp.server.fastmcp import FastMCP
import os

server = FastMCP("spark-rea-transport-test",host='127.0.0.1',port=int(os.environ.get('SPARK_TEST_MCP_HTTP_PORT','8194')))
counter = 0


@server.tool()
def increment(amount: int) -> int:
    global counter
    counter += amount
    return counter


@server.tool()
def read_counter() -> int:
    return counter


if os.environ.get('SPARK_TEST_MCP_SLOW')=='1':
    @server.tool()
    async def wait_for_test(seconds: float) -> int:
        import asyncio
        await asyncio.sleep(min(seconds,5))
        return counter


if __name__ == "__main__":
    server.run(transport="streamable-http" if os.environ.get('SPARK_TEST_MCP_HTTP_PORT') else "stdio")
