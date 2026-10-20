"""Context Resolution Stage: an agent searches reference data over MCP and proposes a
Context; code then computes Context Confidence for what it chose (ADR-0004, ADR-0005).
Also the Catalog lookup the matching Stage needs, through the same MCP server.
"""
import asyncio
import json
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import NamedTuple

from anthropic.lib.tools.mcp import async_mcp_tool
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from . import llm
from .config import settings
from .models import Context, ContextField, ContextProposal, InvoiceHeader

SYSTEM = """You identify which sponsor, study and site a clinical trial invoice belongs to,
using the reference-data search tools. Header text may be misspelled or slightly wrong
(company suffixes, a wrong year in a protocol number, a site name that is close but not exact).
Search for each of sponsor, study (by protocol number and by name) and site (by name and PI),
check that the site is linked to the study, then propose the most consistent records.
Use null for a field when no candidate is plausible. Explain your choice briefly, citing the
header text. Do not state how confident you are; that is computed separately."""

# The agent chooses its own lookups among the searches; the list_* tools exist for the Hub's
# correction picker and would let it skip searching altogether.
AGENT_TOOLS = {"search_sponsors", "search_studies", "search_sites", "list_study_sites"}

ToolCall = Callable[..., Awaitable[object]]


def _tool_json(result) -> object:
    # ISSUE-002: the context Stage crashed scoring the agent's choices ("string indices must be
    # integers"). Root cause: the mcp 2.x client names the field `structured_content`; reading the
    # 1.x name `structuredContent` found nothing, so we fell back to the first text block, which
    # holds only one row of a list. Reading the 2.x field returns the whole structured result.
    data = result.structured_content
    if isinstance(data, dict) and set(data) == {"result"}:
        return data["result"]  # FastMCP wraps list returns as {"result": [...]}
    if data is not None:
        return data
    return json.loads(result.content[0].text)


@asynccontextmanager
async def ref_mcp():
    async with streamable_http_client(settings.ref_mcp_url) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            yield session


def tool_caller(session: ClientSession) -> ToolCall:
    async def call(tool: str, **args):
        return _tool_json(await session.call_tool(tool, args))
    return call


class Scored(NamedTuple):
    confidence: float
    name: str | None
    row: dict | None


async def _score(call: ToolCall, tool: str, record_id: int | None, args: dict, key: str = "score") -> Scored:
    """How closely the header text matches the chosen record, from that record's own search score."""
    if record_id is None:
        return Scored(0.0, None, None)
    for row in await call(tool, **args, limit=20):
        if row["id"] == record_id:
            return Scored(row[key], row.get("name"), row)
    return Scored(0.0, None, None)


def _field(name: str, record_id: int | None, scored: Scored, header_text: str | None) -> ContextField:
    return ContextField(record_id=record_id, record_name=scored.name, header_text=header_text,
                        confidence=round(scored.confidence, 3),
                        confident=record_id is not None and scored.confidence >= settings.threshold(name))


async def score_context(call: ToolCall, header: InvoiceHeader, proposal: ContextProposal,
                        lookups: list[str] | None = None) -> Context:
    """Computed Context Confidence: re-score the proposed records against the header text.
    Corroboration (PI, study-site link) is reported but never raises a field's confidence."""
    sponsor = await _score(call, "search_sponsors", proposal.sponsor_id, {"query": header.sponsor_name})
    study = max([await _score(call, "search_studies", proposal.study_id, {"query": q, "sponsor_id": proposal.sponsor_id})
                 for q in (header.protocol_number, header.study_name) if q] or [Scored(0.0, None, None)],
                key=lambda scored: scored.confidence)
    site = await _score(call, "search_sites", proposal.site_id,
                        {"name": header.site_name, "pi_name": header.pi_name}, key="name_score")
    linked = False
    if proposal.study_id is not None and proposal.site_id is not None:
        linked = any(link["site_id"] == proposal.site_id
                     for link in await call("list_study_sites", study_id=proposal.study_id))
    return Context(
        sponsor=_field("sponsor", proposal.sponsor_id, sponsor, header.sponsor_name),
        study=_field("study", proposal.study_id, study, header.protocol_number or header.study_name),
        site=_field("site", proposal.site_id, site, header.site_name),
        site_linked_to_study=linked,
        study_belongs_to_sponsor=study.row is not None and study.row["sponsor_id"] == proposal.sponsor_id,
        explanation=proposal.explanation,
        agent_lookups=lookups or [],
    )


async def _propose(session: ClientSession, header: InvoiceHeader) -> tuple[ContextProposal, list[str]]:
    tools = [t for t in (await session.list_tools()).tools if t.name in AGENT_TOOLS]
    # ISSUE-011: every Invoice opened an async Anthropic client that was never closed. Root cause:
    # resolve() runs this under asyncio.run, which closes its event loop on return, so the client's
    # connections outlived the loop they belong to. Fix: close the client here, inside the loop,
    # whether the agent succeeds or fails.
    client = llm.async_client()
    try:
        return await _run_agent(client, session, tools, header)
    finally:
        await client.close()


async def _run_agent(client, session: ClientSession, tools, header: InvoiceHeader) -> tuple[ContextProposal, list[str]]:
    runner = client.beta.messages.tool_runner(
        model=settings.model,
        max_tokens=16000,
        system=SYSTEM,
        tools=[async_mcp_tool(t, session) for t in tools],
        messages=[{"role": "user", "content": header.model_dump_json()}],
        output_format=ContextProposal,
        output_config={"effort": "medium"},
        max_iterations=12,
        betas=[llm.FALLBACK_BETA],
        fallbacks="default",
    )
    lookups, final = [], None
    async for message in runner:
        final = message
        llm.record_served(message.model)
        lookups += [f"{b.name}({json.dumps(b.input)})" for b in message.content if b.type == "tool_use"]
    if final is None or final.stop_reason == "refusal":
        raise llm.LLMRefusal("context agent produced no proposal")
    text = next(b.text for b in final.content if b.type == "text")
    return ContextProposal.model_validate_json(text), lookups


async def _resolve(header: InvoiceHeader) -> Context:
    async with ref_mcp() as session:
        proposal, lookups = await _propose(session, header)
        return await score_context(tool_caller(session), header, proposal, lookups)


def resolve(header: InvoiceHeader) -> Context:
    return asyncio.run(_resolve(header))


async def _catalog(sponsor_id: int, study_id: int) -> list[dict]:
    async with ref_mcp() as session:
        return (await tool_caller(session)("get_catalog", sponsor_id=sponsor_id, study_id=study_id))["items"]


def catalog(sponsor_id: int, study_id: int) -> list[dict]:
    return asyncio.run(_catalog(sponsor_id, study_id))


class Reference:
    """Every sponsor, study and site, for a Reviewer's Correction picker (via the list_* tools)."""

    def __init__(self, sponsors: list[dict], studies: list[dict], sites: list[dict]):
        self.sponsors, self.studies, self.sites = sponsors, studies, sites

    @classmethod
    def load(cls) -> "Reference":
        async def fetch():
            async with ref_mcp() as session:
                call = tool_caller(session)
                return cls(await call("list_sponsors"), await call("list_studies"), await call("list_sites"))
        return asyncio.run(fetch())

    def study_sites(self, study_id: int) -> list[int]:
        async def fetch():
            async with ref_mcp() as session:
                return [link["site_id"] for link in await tool_caller(session)("list_study_sites", study_id=study_id)]
        return asyncio.run(fetch())
