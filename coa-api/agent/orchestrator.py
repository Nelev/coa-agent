"""C6: the LangGraph StateGraph.

agent -> tools -> agent ... until submit; a router sends to force_submit (REVIEW)
when state.calls_used reaches settings.tool_budget. ask_user pauses with
interrupt() and POST /runs/{id}/answer resumes with Command(resume=...). Tools
are bound with parallel calls off. Checkpointer: AsyncSqliteSaver on
settings.checkpoints_path. recursion_limit is a backstop only.
"""

from functools import lru_cache


@lru_cache
def build_agent():
    """The compiled graph, built on first call rather than at import, so an
    import never needs OPENROUTER_API_KEY."""
    raise NotImplementedError("day 3")
