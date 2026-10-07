"""Run scenarios through the agent (and the baseline) from the command line.

Run from coa-api, with OPENROUTER_API_KEY in .env:

    uv run python -m dataset.eval.run_scenario            # all 8, agent + baseline
    uv run python -m dataset.eval.run_scenario 2 3        # just these
    uv run python -m dataset.eval.run_scenario 2 --no-baseline
    uv run python -m dataset.eval.run_scenario 1 --model anthropic/claude-sonnet-4.5

Prints each run's trace as it was recorded, then whether it matched expected.csv.
Scenario 8 pauses with a question; it is answered from expected.csv, or from the
keyboard with --ask. Uses a temporary state directory. Billable. Exits 1 if any
scenario did not reach its expected status.
"""

import argparse
import asyncio
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import tracing
from controller.runs import Runner, open_runner
from database import dispose_engine, init_engine
from dataset.eval.scoring import ScenarioRun, expected_rows, score_agent, tool_calls
from dataset.make_data import DATASET_DIR, Scenario, scenarios
from settings import get_settings
from tools.data import load


def install(scenario: Scenario) -> str:
    """Put a scenario's PDF where read_coa looks, as an upload would."""
    pdf_id = f"scenario{scenario.n}"
    uploads = get_settings().uploads_dir
    uploads.mkdir(parents=True, exist_ok=True)
    shutil.copy(DATASET_DIR / "coa" / scenario.file, uploads / f"{pdf_id}.pdf")
    return pdf_id


async def run_one(
    runner: Runner,
    scenario: Scenario,
    *,
    answer: Callable[[dict], str],
    with_baseline: bool = True,
) -> ScenarioRun:
    """The agent on one scenario, answering its question if it asks, scored."""
    expected = expected_rows()[scenario.file]
    pdf_id = install(scenario)
    run_id = f"agent-{scenario.n}"

    outcome = await runner.start(run_id, pdf_id)
    while outcome.phase == "waiting":
        outcome = await runner.resume(run_id, answer(outcome.question))
    steps = await tracing.tail(run_id)

    out = ScenarioRun(scenario.n, scenario.file, agent=outcome.result, steps=steps)
    out.problems = (
        [f"run ended in {outcome.phase}: {outcome.error}"]
        if outcome.phase == "error"
        else score_agent(expected, outcome.result, steps)
    )
    if with_baseline:
        out.baseline = (await runner.baseline(f"baseline-{scenario.n}", pdf_id)).result
    return out


def expected_answer(question: dict) -> str:
    """The answer expected.csv gives to scenario 8's question: the option that
    names the expected material, or its code if no option does."""
    code = expected_rows()[scenarios()[7].file]["answer"]
    name = next(m["name"] for m in load("materials") if m["code"] == code)
    return name if name in question["options"] else code


def show(run: ScenarioRun, expected: dict[str, str]) -> None:
    print(f"\n=== {run.n}. {run.file}  (expected {expected['expected_status']}) ===")
    for s in run.steps:
        out = s.output if isinstance(s.output, str) else str(s.output)
        arg = ", ".join(f"{k}={v!r}" for k, v in (s.input or {}).items())[:60]
        print(f"  {s.seq:>2}. {s.tool or '(reply)':<22} {arg}")
        if s.reasoning and s.tool is None:
            print(f"      says: {s.reasoning[:100]}")
        print(f"      -> {out[:110]}   [{s.tokens_in}+{s.tokens_out} tok, {s.ms} ms]")
    if run.agent:
        print(f"  agent:    {run.agent['status']:<7} {run.agent['summary'][:120]}")
    if run.baseline:
        print(
            f"  baseline: {run.baseline['status']:<7} {run.baseline['summary'][:120]}"
        )
    print(
        f"  calls: {len(tool_calls(run.steps))}   " + ("OK" if run.ok else "MISMATCH")
    )
    for p in run.problems:
        print(f"    - {p}")


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    ap.add_argument(
        "numbers", nargs="*", type=int, help="scenario numbers, default all"
    )
    ap.add_argument("--no-baseline", action="store_true")
    ap.add_argument(
        "--ask", action="store_true", help="answer questions from the keyboard"
    )
    ap.add_argument("--model", help="OpenRouter model, overrides OPENROUTER_MODEL")
    args = ap.parse_args(argv)

    if args.model:
        os.environ["OPENROUTER_MODEL"] = args.model
    state_dir = Path(tempfile.mkdtemp(prefix="coa-run-"))
    os.environ["STATE_DIR"] = str(state_dir)
    get_settings.cache_clear()
    settings = get_settings()
    if not settings.openrouter_api_key:
        print("OPENROUTER_API_KEY is not set (coa-api/.env).")
        return 2

    expected = expected_rows()
    chosen = [s for s in scenarios() if not args.numbers or s.n in args.numbers]
    print(f"model {settings.openrouter_model}, state {state_dir}")

    def answer(question: dict) -> str:
        if args.ask:
            return input(f"\n? {question['question']} {question['options']}\n> ")
        chosen_answer = expected_answer(question)
        print(
            f"\n? {question['question']} {question['options']}\n> {chosen_answer}   (from expected.csv)"
        )
        return chosen_answer

    await init_engine()
    runs: list[ScenarioRun] = []
    try:
        async with open_runner() as runner:
            for s in chosen:
                run = await run_one(
                    runner, s, answer=answer, with_baseline=not args.no_baseline
                )
                show(run, expected[s.file])
                runs.append(run)
    finally:
        await dispose_engine()

    print("\n--- summary ---")
    for r in runs:
        base = f"  baseline {r.baseline['status']}" if r.baseline else ""
        print(
            f"  {r.n}. {r.file:<24} {'ok  ' if r.ok else 'FAIL'} agent {(r.agent or {}).get('status', '-')}{base}"
        )
    right = sum(r.ok for r in runs)
    print(f"{right}/{len(runs)} scenarios reached the expected result")
    return 0 if right == len(runs) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
