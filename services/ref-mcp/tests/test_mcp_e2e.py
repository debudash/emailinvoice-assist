"""End to end: start the server, connect with the mcp client over streamable HTTP, call tools."""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


pytestmark = pytest.mark.live

SERVICE_DIR = Path(__file__).resolve().parents[1]
EXPECTED_TOOLS = {
    "search_sponsors", "search_studies", "search_sites", "list_study_sites",
    "get_catalog", "list_sponsors", "list_studies", "list_sites",
}


@pytest.fixture(scope="module")
def server_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "MCP_HOST": "127.0.0.1", "MCP_PORT": str(port)}
    proc = subprocess.Popen([sys.executable, "server.py"], cwd=SERVICE_DIR, env=env)
    url = f"http://127.0.0.1:{port}/mcp"
    try:
        for _ in range(100):
            try:
                httpx.get(url, timeout=0.5)
                break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            pytest.fail("ref-mcp server did not start")
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


async def _session_call(url: str, tool: str, args: dict):
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            return {t.name for t in tools.tools}, await session.call_tool(tool, args)


async def test_list_tools_and_full_catalog_over_mcp(server_url):
    names, result = await _session_call(server_url, "get_catalog", {"sponsor_id": 1, "study_id": 1})
    assert names == EXPECTED_TOOLS
    assert not result.isError
    catalog = json.loads(result.content[0].text)
    assert catalog["total"] == 100 and len(catalog["items"]) == 100


async def test_list_result_is_structured_over_mcp(server_url):
    _, result = await _session_call(server_url, "search_studies", {"query": "NWD-VER-2024-002"})
    assert not result.isError
    assert result.structuredContent["result"][0]["id"] == 2
