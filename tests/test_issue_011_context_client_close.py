"""ISSUE-011 regression test (recorded after the fact; fixed in 78d8fb3).

Found by: the developer while building P1 (2026-10-20). The context agent opened a new async
Anthropic client for every Invoice and never closed it, so its connections outlived the event loop
that asyncio.run closes when resolve() returns.
"""
import asyncio
from types import SimpleNamespace

import pytest

import invoice_assist.context as context


class FakeClient:
    def __init__(self):
        self.closed_in_running_loop = None

    async def close(self):
        self.closed_in_running_loop = asyncio.get_running_loop().is_running()


class FakeSession:
    async def list_tools(self):
        return SimpleNamespace(tools=[])


@pytest.mark.parametrize("agent_fails", [False, True])
def test_issue_011_context_agent_closes_its_client_inside_the_event_loop(monkeypatch, agent_fails):
    client = FakeClient()
    monkeypatch.setattr(context.llm, "async_client", lambda: client)

    async def run_agent(*args):
        if agent_fails:
            raise RuntimeError("the agent failed")
        return "proposal", []
    monkeypatch.setattr(context, "_run_agent", run_agent)

    if agent_fails:
        with pytest.raises(RuntimeError):
            asyncio.run(context._propose(FakeSession(), header=None))
    else:
        assert asyncio.run(context._propose(FakeSession(), header=None)) == ("proposal", [])
    assert client.closed_in_running_loop is True
