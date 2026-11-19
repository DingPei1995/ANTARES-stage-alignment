"""The agent interface follows ARPES viewer (the reference for Ding's programs).

- src/quickalignment/agent/API.md is generated and up to date (python -m quickalignment.agent.catalog --write);
- the MCP server answers as ARPES viewer's: protocol versions, readOnlyHint on every tool, the same error texts,
  every error inside a tool as a tool error.
"""

import json

from quickalignment.agent import catalog
from quickalignment.agent.mcp_server import ACTING, PROTOCOL_VERSIONS, TOOLS, Server


def test_api_reference_is_up_to_date():
    with open(catalog.PATH, encoding="utf-8") as handle:
        current = handle.read()
    assert current == catalog.build(), "run: python -m quickalignment.agent.catalog --write"


def test_every_tool_is_in_the_reference():
    text = catalog.build()
    assert all(f"`{t['name']}`" in text for t in TOOLS)


def test_protocol_as_arpes_viewer():
    assert PROTOCOL_VERSIONS == ("2025-06-18", "2025-03-26", "2024-11-05")
    server = Server()
    init = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {"protocolVersion": "1999-01-01"}})["result"]
    assert init["protocolVersion"] == "2025-06-18" and init["capabilities"]["tools"] == {"listChanged": False}
    tools = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    assert {t["name"] for t in tools} == {t["name"] for t in TOOLS}
    assert all(t["annotations"]["readOnlyHint"] == (t["name"] not in ACTING) for t in tools)
    assert set(ACTING) <= {t["name"] for t in TOOLS}
    unknown = server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "nope"}})
    assert unknown["error"] == {"code": -32602, "message": "no tool called 'nope'"}
    method = server.handle({"jsonrpc": "2.0", "id": 4, "method": "nope"})
    assert method["error"]["message"] == "method not found: nope"


def test_missing_argument_says_what_the_tool_takes():
    server = Server()
    res = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                         "params": {"name": "align_photo_info", "arguments": {}}})["result"]
    assert res["isError"] and "align_photo_info takes: path" in res["content"][0]["text"]


def test_an_error_inside_a_tool_is_a_tool_error():
    server = Server()
    res = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                         "params": {"name": "align_photo_info", "arguments": {"path": "/no/such/file.jpg"}}})
    assert "result" in res and res["result"]["isError"] and res["result"]["content"][0]["text"]


def test_results_are_json_text():
    server = Server()
    res = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                         "params": {"name": "align_plates", "arguments": {}}})["result"]
    assert not res["isError"] and isinstance(json.loads(res["content"][0]["text"]), (dict, list))
