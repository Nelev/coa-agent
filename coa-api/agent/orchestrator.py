"""C6: the LangGraph StateGraph.

    START -> agent -+-> tools -> account -+-> agent ...
                    |                     +-> END (submit accepted)
                    +-> nudge -> agent    +-> force_submit (budget / 2 failures)
                    +-> force_submit -> END

`agent` calls the model. `tools` is the registry's ToolNode. `account` counts
the calls (refused ones too) and consecutive failures per tool. The budget and
the failure rule route to `force_submit`, which submits REVIEW. ask_user pauses
the run with interrupt(); the caller resumes it with Command(resume=answer).
`recursion_limit` is a backstop only.
"""

from functools import lru_cache

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph

from agent import guard
from agent.prompt import NUDGE, SYSTEM_PROMPT
from agent.registry import TOOLS, tool_node
from agent.state import RunState
from settings import get_settings
from tools.llm import chat_model

MAX_FAILURES = 2
MAX_NUDGES = 2


def bind_model(model=None):
    """The chat model with the tools bound, one call at a time. Parallel calls
    are off so the budget count is exact and ask_user is never mixed with other
    calls."""
    model = model or chat_model()
    return model.bind_tools(TOOLS, parallel_tool_calls=False)


def build_graph(model, checkpointer=None, budget: int | None = None):
    """The compiled graph. `model` is anything with an async `ainvoke` that
    returns an AIMessage (already bound to the tools)."""
    budget = budget if budget is not None else get_settings().tool_budget

    async def agent(state: RunState) -> dict:
        reply = await model.ainvoke([SystemMessage(SYSTEM_PROMPT), *state["messages"]])
        return {"messages": [reply]}

    def after_agent(state: RunState) -> str:
        calls = getattr(state["messages"][-1], "tool_calls", None)
        if not calls:
            return "nudge" if state.get("nudges", 0) < MAX_NUDGES else "force_submit"
        if state.get("calls_used", 0) + len(calls) > budget:
            return "force_submit"
        return "tools"

    def nudge(state: RunState) -> dict:
        return {
            "messages": [HumanMessage(NUDGE)],
            "nudges": state.get("nudges", 0) + 1,
        }

    def account(state: RunState) -> dict:
        """Count the calls the last AI message made, and the failures."""
        messages = state["messages"]
        last_ai = max(i for i, m in enumerate(messages) if isinstance(m, AIMessage))
        failures = dict(state.get("failures", {}))
        for m in messages[last_ai + 1 :]:
            if isinstance(m, ToolMessage):
                failures[m.name] = (
                    failures.get(m.name, 0) + 1 if m.status == "error" else 0
                )
        return {
            "calls_used": state.get("calls_used", 0)
            + len(messages[last_ai].tool_calls),
            "failures": failures,
        }

    def after_account(state: RunState) -> str:
        if state.get("result"):
            return END
        if any(n >= MAX_FAILURES for n in state.get("failures", {}).values()):
            return "force_submit"
        if state.get("calls_used", 0) >= budget:
            return "force_submit"
        return "agent"

    def force_submit(state: RunState) -> dict:
        failed = [t for t, n in state.get("failures", {}).items() if n >= MAX_FAILURES]
        if failed:
            reason = f"{failed[0]} failed {MAX_FAILURES} times in a row"
        elif (
            isinstance(state["messages"][-1], AIMessage)
            and not state["messages"][-1].tool_calls
        ):
            reason = "the agent did not call submit"
        else:
            reason = f"the budget of {budget} tool calls was used"
        result = guard.forced_result(state, reason)
        return {
            "result": result.model_dump(mode="json"),
            "decision": {"forced": True, "reason": reason},
        }

    g = StateGraph(RunState)
    g.add_node("agent", agent)
    g.add_node("nudge", nudge)
    g.add_node("tools", tool_node())
    g.add_node("account", account)
    g.add_node("force_submit", force_submit)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", after_agent, ["tools", "nudge", "force_submit"])
    g.add_edge("nudge", "agent")
    g.add_edge("tools", "account")
    g.add_conditional_edges("account", after_account, ["agent", "force_submit", END])
    g.add_edge("force_submit", END)
    return g.compile(checkpointer=checkpointer)


@lru_cache
def build_agent(checkpointer=None):
    """The compiled graph on the real model, built on first call rather than at
    import, so an import never needs OPENROUTER_API_KEY."""
    return build_graph(bind_model(), checkpointer)
