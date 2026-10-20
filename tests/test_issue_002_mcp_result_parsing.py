"""ISSUE-002 regression test.

Found by: first S0 end-to-end run (2026-10-19); the context Stage failed with
"TypeError: string indices must be integers" when scoring the agent's choices.
"""
from types import SimpleNamespace

from invoice_assist.context import _tool_json

ROWS = [{"id": 2, "name": "Contoso Therapeutics", "score": 1.0},
        {"id": 1, "name": "Northwind Pharma", "score": 0.333}]


def test_list_result_from_mcp2_client_returns_every_row():
    # mcp 2.x clients expose structured output as `structured_content`; FastMCP wraps lists in "result".
    result = SimpleNamespace(structured_content={"result": ROWS},
                             content=[SimpleNamespace(text='{"id": 2}'), SimpleNamespace(text='{"id": 1}')])

    assert _tool_json(result) == ROWS


def test_dict_result_is_returned_whole():
    catalog = {"sponsor_id": 2, "study_id": 3, "total": 0, "items": []}
    result = SimpleNamespace(structured_content=catalog, content=[])

    assert _tool_json(result) == catalog
