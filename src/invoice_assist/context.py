"""Context Resolution Stage: an agent searches reference data over MCP and proposes a
Context; code then computes Context Confidence for what it chose (ADR-0004, ADR-0005).
"""
import asyncio
import json

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


def _tool_json(result) -> object:
    if getattr(result, "structuredContent", None):
        data = result.structuredContent
        return data.get("result", data) if isinstance(data, dict) else data
    return json.loads(result.content[0].text)


async def _call(session: ClientSession, tool: str, **args) -> object:
    return _tool_json(await session.call_tool(tool, args))


async def _score(session, rows_tool: str, record_id: int | None, args: dict, key: str = "score"):
    if record_id is None:
        return 0.0, None, None
    rows = await _call(session, rows_tool, **args, limit=20)
    for row in rows:
        if row["id"] == record_id:
            return row[key], row.get("name"), row
    return 0.0, None, None


def _field(record_id, name, header_text, confidence) -> ContextField:
    return ContextField(record_id=record_id, record_name=name, header_text=header_text,
                        confidence=round(confidence, 3),
                        confident=record_id is not None and confidence >= settings.context_threshold)


async def _resolve(header: InvoiceHeader) -> Context:
    async with streamable_http_client(settings.ref_mcp_url) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            runner = llm.async_client().beta.messages.tool_runner(
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
                lookups += [f"{b.name}({json.dumps(b.input)})" for b in message.content if b.type == "tool_use"]
            if final is None or final.stop_reason == "refusal":
                raise llm.LLMRefusal("context agent produced no proposal")
            text = next(b.text for b in final.content if b.type == "text")
            proposal = ContextProposal.model_validate_json(text)

            # Computed Context Confidence: re-score the agent's choices against the header text.
            sponsor_score, sponsor_name, _ = await _score(
                session, "search_sponsors", proposal.sponsor_id, {"query": header.sponsor_name})
            study_scores = [await _score(session, "search_studies", proposal.study_id,
                                         {"query": q, "sponsor_id": proposal.sponsor_id})
                            for q in (header.protocol_number, header.study_name) if q]
            study_score, study_name, study_row = max(study_scores, default=(0.0, None, None),
                                                     key=lambda s: s[0])
            site_score, site_name, _ = await _score(
                session, "search_sites", proposal.site_id,
                {"name": header.site_name, "pi_name": header.pi_name}, key="name_score")
            linked = False
            if proposal.study_id is not None and proposal.site_id is not None:
                links = await _call(session, "list_study_sites", study_id=proposal.study_id)
                linked = any(link["site_id"] == proposal.site_id for link in links)

    return Context(
        sponsor=_field(proposal.sponsor_id, sponsor_name, header.sponsor_name, sponsor_score),
        study=_field(proposal.study_id, study_name, header.protocol_number or header.study_name, study_score),
        site=_field(proposal.site_id, site_name, header.site_name, site_score),
        site_linked_to_study=linked,
        study_belongs_to_sponsor=bool(study_row) and study_row["sponsor_id"] == proposal.sponsor_id,
        explanation=proposal.explanation,
        agent_lookups=lookups,
    )


def resolve(header: InvoiceHeader) -> Context:
    return asyncio.run(_resolve(header))


async def _catalog(sponsor_id: int, study_id: int) -> list[dict]:
    async with streamable_http_client(settings.ref_mcp_url) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            return (await _call(session, "get_catalog", sponsor_id=sponsor_id, study_id=study_id))["items"]


def catalog(sponsor_id: int, study_id: int) -> list[dict]:
    return asyncio.run(_catalog(sponsor_id, study_id))
