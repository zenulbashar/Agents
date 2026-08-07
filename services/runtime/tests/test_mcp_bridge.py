"""The MCP->Ollama schema bridge.

Every fixture here is a shape a REAL MCP server emits, not an invented edge case. MCP servers
derive schemas from Python type hints via Pydantic, so `Optional[str]` becomes anyOf[str,null]
and a nested model becomes $defs/$ref by construction. Any server with one optional argument
ships composition keywords Ollama's parser rejects.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from services.runtime.mcp_bridge import (                 # noqa: E402
    SchemaError, build_toolset, namespaced, sanitise_schema, to_ollama_tool,
)


# ------------------------------------------------------- what Pydantic actually emits
def test_optional_argument_anyof_is_collapsed_to_the_real_type():
    """Optional[str] -> anyOf[string, null]. The null branch carries nothing actionable."""
    reduced = sanitise_schema({
        "type": "object",
        "properties": {"cursor": {"anyOf": [{"type": "string"}, {"type": "null"}],
                                  "description": "page cursor"}},
    })
    assert reduced["properties"]["cursor"]["type"] == "string"
    assert reduced["properties"]["cursor"]["description"] == "page cursor"
    assert "anyOf" not in reduced["properties"]["cursor"]


def test_nested_model_ref_and_defs_are_inlined():
    """A nested Pydantic model becomes $defs + $ref. Ollama cannot follow a $ref."""
    reduced = sanitise_schema({
        "type": "object",
        "$defs": {"Filter": {"type": "object",
                             "properties": {"status": {"type": "string"}},
                             "required": ["status"]}},
        "properties": {"filter": {"$ref": "#/$defs/Filter"}},
    })
    inlined = reduced["properties"]["filter"]
    assert inlined["type"] == "object"
    assert inlined["properties"]["status"]["type"] == "string"
    assert "$ref" not in str(reduced)


def test_type_as_a_list_is_narrowed():
    reduced = sanitise_schema({"type": "object",
                               "properties": {"q": {"type": ["string", "null"]}}})
    assert reduced["properties"]["q"]["type"] == "string"


def test_allof_is_merged_rather_than_dropped():
    reduced = sanitise_schema({
        "type": "object",
        "allOf": [{"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]},
                  {"type": "object", "properties": {"b": {"type": "integer"}}}],
    })
    assert set(reduced["properties"]) == {"a", "b"}
    assert reduced["required"] == ["a"]


def test_unsupported_keywords_are_stripped_not_passed_through():
    """A keyword Ollama cannot parse fails the whole tool call, not just that field."""
    reduced = sanitise_schema({
        "type": "object",
        "properties": {"n": {"type": "integer", "exclusiveMinimum": 0, "multipleOf": 2}},
        "if": {"properties": {"n": {"const": 1}}},
        "unevaluatedProperties": False,
    })
    assert "if" not in reduced and "unevaluatedProperties" not in reduced
    assert "exclusiveMinimum" not in reduced["properties"]["n"]
    assert reduced["properties"]["n"]["type"] == "integer"


# --------------------------------------------------------------------------- security
def test_network_refs_are_refused_not_fetched():
    """The spec: implementations MUST NOT auto-dereference network $refs."""
    for ref in ["https://evil.example/schema.json", "http://169.254.169.254/latest/meta-data"]:
        with pytest.raises(SchemaError, match="refusing to dereference"):
            sanitise_schema({"type": "object", "properties": {"x": {"$ref": ref}}})


def test_unresolvable_local_ref_is_an_error_not_a_silent_empty_object():
    with pytest.raises(SchemaError):
        sanitise_schema({"type": "object", "properties": {"x": {"$ref": "#/$defs/Missing"}}})


def test_deeply_nested_schema_is_bounded():
    node = {"type": "object", "properties": {}}
    deep = node
    for _ in range(40):
        deep["properties"] = {"n": {"type": "object", "properties": {}}}
        deep = deep["properties"]["n"]
    with pytest.raises(SchemaError, match="nested deeper"):
        sanitise_schema(node)


# ------------------------------------------------------------------------ namespacing
def test_names_are_namespaced_because_the_protocol_does_not_do_it():
    assert namespaced("m365", "send_mail") == "m365_send_mail"


def test_identical_tool_names_from_two_servers_do_not_collide():
    tools, routing, _ = build_toolset({
        "m365": [{"name": "search", "inputSchema": {"type": "object"}}],
        "gitea": [{"name": "search", "inputSchema": {"type": "object"}}],
    })
    names = [t["function"]["name"] for t in tools]
    assert len(set(names)) == 2, names
    assert routing["m365_search"] == ("m365", "search")
    assert routing["gitea_search"] == ("gitea", "search")


def test_names_are_flattened_to_identifier_safe_characters():
    assert namespaced("srv", "read-file.v2") == "srv_read_file_v2"


# ------------------------------------------------------------------- SDK v1/v2 spelling
def test_both_input_schema_spellings_are_accepted():
    """v2 renamed the attribute to snake_case; a bridge indexing ['inputSchema'] KeyErrors."""
    v1 = to_ollama_tool({"name": "t", "inputSchema": {"type": "object",
                                                      "properties": {"a": {"type": "string"}}}})
    v2 = to_ollama_tool({"name": "t", "input_schema": {"type": "object",
                                                       "properties": {"a": {"type": "string"}}}})
    assert v1["function"]["parameters"] == v2["function"]["parameters"]


def test_sdk_object_with_snake_case_attribute_is_accepted():
    class Tool:
        name = "fetch"
        description = "fetch a thing"
        input_schema = {"type": "object", "properties": {"url": {"type": "string"}}}

    converted = to_ollama_tool(Tool(), "srv")
    assert converted["function"]["name"] == "srv_fetch"
    assert converted["function"]["parameters"]["properties"]["url"]["type"] == "string"


# ---------------------------------------------------------------------------- failure
def test_one_unconvertible_tool_does_not_take_down_the_others():
    tools, routing, skipped = build_toolset({
        "srv": [
            {"name": "good", "inputSchema": {"type": "object",
                                             "properties": {"a": {"type": "string"}}}},
            {"name": "poisoned", "inputSchema": {"type": "object",
                                                 "properties": {"x": {"$ref": "https://evil/s"}}}},
        ]})
    assert [t["function"]["name"] for t in tools] == ["srv_good"]
    assert len(skipped) == 1 and skipped[0]["tool"] == "poisoned"
    assert "refusing to dereference" in skipped[0]["reason"]


def test_result_is_json_serialisable():
    """It goes straight into an HTTP body; a stray Pydantic object would fail at request time."""
    import json

    schema = {"type": "object",
              "properties": {"o": {"anyOf": [{"type": "string"}, {"type": "null"}]}}}
    tools, _, _ = build_toolset({"srv": [{"name": "t", "inputSchema": schema}]})
    json.dumps(tools)
