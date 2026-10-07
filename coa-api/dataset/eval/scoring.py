"""Compare one run with its row of expected.csv. Shared by the command-line
runner and evaluate.py, so a scenario is judged the same way everywhere."""

from dataclasses import dataclass, field

from schema import ToolCall
from tools.data import load

MAX_CALLS = 12
CLEAN_CALLS = 6


def expected_rows() -> dict[str, dict[str, str]]:
    """expected.csv by file name."""
    return {r["file"]: r for r in load("expected")}


def tool_calls(steps: list[ToolCall]) -> list[str]:
    """The tools the agent called, in order. The system's own force_submit and
    model replies without a tool are not calls."""
    return [s.tool for s in steps if s.tool not in (None, "force_submit")]


def asked(steps: list[ToolCall]) -> bool:
    return any(s.tool == "ask_user" for s in steps)


def findings_key(result: dict) -> set[str]:
    return {f"{f['test']}:{f['kind']}" for f in result.get("findings", [])}


def score_agent(
    expected: dict[str, str], result: dict | None, steps: list[ToolCall]
) -> list[str]:
    """Every way the agent's run differs from what was expected; empty is a pass."""
    if result is None:
        return ["the run did not finish"]
    problems = []
    if result["status"] != expected["expected_status"]:
        problems.append(
            f"status {result['status']}, expected {expected['expected_status']}"
        )
        if expected["expected_status"] == "FAIL" and result["status"] == "PASS":
            problems.append("CRITICAL: a FAIL scenario was reported as PASS")
    want = {f for f in expected["expected_findings"].split(";") if f}
    got = findings_key(result)
    if got != want:
        problems.append(f"findings {sorted(got)}, expected {sorted(want)}")
    used = tool_calls(steps)
    for tool in filter(None, expected["must_call"].split(";")):
        if tool not in used:
            problems.append(f"never called {tool}")
    if asked(steps) != (expected["expects_question"] == "true"):
        problems.append(
            "asked a question" if asked(steps) else "did not ask the question"
        )
    if len(used) > MAX_CALLS:
        problems.append(f"{len(used)} tool calls, at most {MAX_CALLS}")
    if expected["file"] == "coa_01_clean.pdf" and len(used) > CLEAN_CALLS:
        problems.append(f"{len(used)} tool calls on a clean CoA, at most {CLEAN_CALLS}")
    return problems


@dataclass
class ScenarioRun:
    """One scenario through the agent (and the baseline)."""

    n: int
    file: str
    agent: dict | None = None
    steps: list[ToolCall] = field(default_factory=list)
    baseline: dict | None = None
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems
