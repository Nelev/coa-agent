"""What the provider will be sent, built offline with a dummy key."""

import json

from langchain_openai import ChatOpenAI

from agent.orchestrator import bind_model
from agent.registry import TOOLS


def specs():
    model = bind_model(ChatOpenAI(model="openai/gpt-4.1", api_key="not-a-real-key"))
    return {
        t["function"]["name"]: t["function"] for t in model.kwargs["tools"]
    }, model.kwargs


def test_all_nine_tools_are_sent_with_parallel_calls_off():
    tools, kwargs = specs()
    assert sorted(tools) == sorted(t.name for t in TOOLS) and len(tools) == 9
    assert kwargs["parallel_tool_calls"] is False


def test_injected_state_never_reaches_the_provider():
    tools, _ = specs()
    for name, fn in tools.items():
        props = set(fn["parameters"].get("properties", {}))
        assert not props & {"state", "tool_call_id"}, name
    assert set(tools["submit"]["parameters"]["properties"]) == {
        "summary",
        "draft_id",
        "claims",
    }
    assert tools["submit"]["parameters"]["required"] == ["summary"]
    # The whole thing must serialize: nested ErrorClaim included.
    json.dumps(tools)


def test_every_tool_has_a_description_the_model_can_use():
    tools, _ = specs()
    assert all(len(fn["description"]) > 40 for fn in tools.values())
