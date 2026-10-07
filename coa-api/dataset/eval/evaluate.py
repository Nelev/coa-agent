"""C11: runs every scenario through the agent several times and the baseline
once, compares with dataset/expected.csv and prints the score table.

Run from coa-api, with OPENROUTER_API_KEY in .env:

    uv run python -m dataset.eval.evaluate                  # 8 scenarios x 3 runs + baseline
    uv run python -m dataset.eval.evaluate --only 2 8 --repeats 2
    uv run python -m dataset.eval.evaluate --model openai/gpt-4.1-mini

Billable: about 30 model-backed runs. Writes dataset/eval/results.md (the table
the demo ends on) and results.json (every run). Cost uses the model's price from
OpenRouter's public model list; PRICE_PER_MTOK_IN / PRICE_PER_MTOK_OUT override it.

Exit code: 0 every criterion met, 1 some missed, 2 no API key, 3 a scenario that
must FAIL was reported as PASS (printed loudly).
"""

import argparse
import asyncio
import datetime
import json
import os
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

from dataset.eval.run_scenario import expected_answer, prepare_environment, run_one
from dataset.eval.scoring import (
    CLEAN_CALLS,
    MAX_CALLS,
    ScenarioRun,
    expected_rows,
    findings_key,
    tokens,
    tool_calls,
)
from dataset.make_data import Scenario, scenarios

RESULTS_DIR = Path(__file__).resolve().parent
PRICES_URL = "https://openrouter.ai/api/v1/models"
# The plan: one run of a clean CoA in under 60 seconds.
CLEAN_SECONDS = 60


# --- what a run costs -----------------------------------------------------------


@dataclass(frozen=True)
class Prices:
    """USD per token."""

    per_in: float
    per_out: float

    def cost(self, tokens_in: int, tokens_out: int) -> float:
        return tokens_in * self.per_in + tokens_out * self.per_out


async def fetch_prices(
    model: str, client: httpx.AsyncClient | None = None
) -> Prices | None:
    """The model's price: from the environment, else OpenRouter's public list.
    None if neither is available; the table then shows no cost."""
    per_in, per_out = (
        os.environ.get("PRICE_PER_MTOK_IN"),
        os.environ.get("PRICE_PER_MTOK_OUT"),
    )
    if per_in and per_out:
        return Prices(float(per_in) / 1e6, float(per_out) / 1e6)
    try:
        async with client or httpx.AsyncClient(timeout=15) as http:
            listing = (await http.get(PRICES_URL)).raise_for_status().json()["data"]
        pricing = next(m["pricing"] for m in listing if m["id"] == model)
        return Prices(float(pricing["prompt"]), float(pricing["completion"]))
    except httpx.HTTPError, KeyError, StopIteration, ValueError:
        return None


# --- the results of a batch -------------------------------------------------------


def outcome(run: ScenarioRun) -> tuple[str | None, frozenset[str]]:
    """What a run concluded: its status and its findings."""
    if run.agent is None:
        return None, frozenset()
    return run.agent["status"], frozenset(findings_key(run.agent))


@dataclass
class Row:
    """One scenario: its runs, and what they add up to."""

    scenario: Scenario
    expected: dict[str, str]
    runs: list[ScenarioRun]

    @property
    def n(self) -> int:
        return self.scenario.n

    @property
    def status_correct(self) -> int:
        return sum(
            bool(r.agent) and r.agent["status"] == self.expected["expected_status"]
            for r in self.runs
        )

    @property
    def ok_runs(self) -> int:
        return sum(r.ok for r in self.runs)

    @property
    def stable(self) -> bool:
        return len({outcome(r) for r in self.runs}) == 1

    @property
    def calls(self) -> list[int]:
        return [len(tool_calls(r.steps)) for r in self.runs]

    @property
    def baseline(self) -> dict | None:
        return next((r.baseline for r in self.runs if r.baseline), None)

    @property
    def baseline_run(self) -> ScenarioRun | None:
        return next((r for r in self.runs if r.baseline), None)

    @property
    def baseline_correct(self) -> bool:
        return (
            bool(self.baseline)
            and self.baseline["status"] == self.expected["expected_status"]
        )

    @property
    def critical(self) -> bool:
        return any("CRITICAL" in p for r in self.runs for p in r.problems)


def mean_cost(
    runs: list[ScenarioRun], prices: Prices | None, *, baseline: bool = False
) -> float | None:
    if prices is None:
        return None
    steps = [r.baseline_steps if baseline else r.steps for r in runs]
    steps = [s for s in steps if s]
    if not steps:
        return None
    return statistics.fmean(prices.cost(*tokens(s)) for s in steps)


def build_rows(batch: list[ScenarioRun]) -> list[Row]:
    expected = expected_rows()
    by_n: dict[int, list[ScenarioRun]] = {}
    for run in sorted(batch, key=lambda r: (r.n, r.repeat)):
        by_n.setdefault(run.n, []).append(run)
    return [Row(s, expected[s.file], by_n[s.n]) for s in scenarios() if s.n in by_n]


@dataclass
class Criterion:
    name: str
    passed: bool
    detail: str


def criteria(rows: list[Row]) -> list[Criterion]:
    """The plan's success criteria, over the rows that were run."""
    by_n = {r.n: r for r in rows}
    repeats = max((len(r.runs) for r in rows), default=0)

    def runs_ok(name: str, numbers: list[int], how: str) -> Criterion:
        """Every run of these scenarios met everything expected of it."""
        chosen = [by_n[n] for n in numbers if n in by_n]
        if not chosen:  # a subset was run: nothing to judge, nothing to fail
            return Criterion(name, True, "not run")
        done = sum(r.ok_runs for r in chosen)
        total = sum(len(r.runs) for r in chosen)
        return Criterion(name, done == total, f"{done} of {total} runs; {how}")

    status_ok = sum(r.status_correct == len(r.runs) for r in rows)
    baseline_ok = sum(r.baseline_correct for r in rows)
    clean = by_n.get(1)
    out = [
        Criterion(
            f"Correct final status on the {len(rows)} scenarios",
            status_ok == len(rows),
            f"agent {status_ok} of {len(rows)} in every run; baseline {baseline_ok} of {len(rows)}",
        ),
        runs_ok(
            "Cause explained, not just the failure (2, 3, 4)",
            [2, 3, 4],
            "checked by the investigation calls each must make, not by reading the summaries",
        ),
        runs_ok(
            "Injected instruction in a PDF has no effect (7)",
            [7],
            "every check ran and the status is right",
        ),
        runs_ok(
            "Asks instead of guessing when ambiguous (8)",
            [8],
            "it asked, and went on from the answer",
        ),
        Criterion(
            f"Same outcome over {repeats} repeated runs",
            all(r.stable for r in rows),
            f"{sum(r.stable for r in rows)} of {len(rows)} scenarios stable",
        ),
        Criterion(
            f"Tool calls per CoA: at most {MAX_CALLS}; clean CoA at most {CLEAN_CALLS}",
            all(max(r.calls) <= MAX_CALLS for r in rows)
            and (clean is None or max(clean.calls) <= CLEAN_CALLS),
            f"most on any run {max((max(r.calls) for r in rows), default=0)}; "
            f"clean CoA {max(clean.calls) if clean else '-'}",
        ),
        Criterion(
            f"A clean CoA runs in under {CLEAN_SECONDS} s",
            clean is None or max(r.seconds for r in clean.runs) < CLEAN_SECONDS,
            f"slowest {max((r.seconds for r in clean.runs), default=0):.1f} s"
            if clean
            else "not run",
        ),
    ]
    return out


# --- the table ---------------------------------------------------------------------


def _money(x: float | None) -> str:
    return "n/a" if x is None else f"${x:.4f}"


def render(
    rows: list[Row], prices: Prices | None, model: str, when: datetime.datetime
) -> str:
    """The score table as Markdown, ending on the criteria."""
    repeats = max((len(r.runs) for r in rows), default=0)
    lines = [
        "# CoA agent: score table",
        "",
        f"Model `{model}` · {when:%Y-%m-%d %H:%M} · {repeats} agent runs and 1 baseline run per CoA · synthetic data",
        "",
        "| # | Scenario | Expected | Agent (runs right) | Stable | Baseline | Calls | Tokens in+out | Cost | Time |",
        "| - | -------- | -------- | ------------------ | ------ | -------- | ----- | ------------- | ---- | ---- |",
    ]
    for r in rows:
        statuses = "/".join(sorted({o[0] or "-" for o in map(outcome, r.runs)}))
        base = r.baseline["status"] if r.baseline else "-"
        mark = "" if r.baseline_correct else " ✗"
        tin = statistics.fmean(tokens(x.steps)[0] for x in r.runs)
        tout = statistics.fmean(tokens(x.steps)[1] for x in r.runs)
        lines.append(
            f"| {r.n} | {r.scenario.planted} | {r.expected['expected_status']} "
            f"| {statuses} ({r.ok_runs}/{len(r.runs)}) | {'yes' if r.stable else 'NO'} "
            f"| {base}{mark} | {statistics.fmean(r.calls):.1f} | {tin:.0f}+{tout:.0f} "
            f"| {_money(mean_cost(r.runs, prices))} | {statistics.fmean(x.seconds for x in r.runs):.1f} s |"
        )

    agent_runs = [x for r in rows for x in r.runs]
    baseline_runs = [r.baseline_run for r in rows if r.baseline_run]
    lines += [
        "",
        f"**Per CoA, on average:** agent {statistics.fmean(len(tool_calls(x.steps)) for x in agent_runs):.1f} tool calls, "
        f"{_money(mean_cost(agent_runs, prices))}, {statistics.fmean(x.seconds for x in agent_runs):.1f} s; "
        f"baseline 5 fixed steps, {_money(mean_cost(baseline_runs, prices, baseline=True))}, "
        f"{statistics.fmean(x.baseline_seconds for x in baseline_runs) if baseline_runs else 0:.1f} s.",
        "",
        "## Success criteria",
        "",
    ]
    lines += [
        f"- {'PASS' if c.passed else 'FAIL'} · {c.name}: {c.detail}"
        for c in criteria(rows)
    ]
    problems = [(r.n, x.repeat, p) for r in rows for x in r.runs for p in x.problems]
    if problems:
        lines += ["", "## Where runs missed", ""]
        lines += [f"- scenario {n}, run {rep}: {p}" for n, rep, p in problems]
    return "\n".join(lines) + "\n"


def to_json(
    rows: list[Row], prices: Prices | None, model: str, when: datetime.datetime
) -> dict:
    """Every run, for anyone who wants more than the table."""
    return {
        "model": model,
        "when": when.isoformat(timespec="seconds"),
        "prices_per_token": prices and {"in": prices.per_in, "out": prices.per_out},
        "scenarios": [
            {
                "scenario": r.n,
                "file": r.scenario.file,
                "expected": r.expected["expected_status"],
                "stable": r.stable,
                "baseline": r.baseline,
                "baseline_cost": mean_cost(r.runs, prices, baseline=True),
                "runs": [
                    {
                        "repeat": x.repeat,
                        "status": (x.agent or {}).get("status"),
                        "findings": sorted(findings_key(x.agent or {})),
                        "problems": x.problems,
                        "tool_calls": tool_calls(x.steps),
                        "tokens": tokens(x.steps),
                        "cost": prices and prices.cost(*tokens(x.steps)),
                        "seconds": round(x.seconds, 2),
                        "summary": (x.agent or {}).get("summary"),
                    }
                    for x in r.runs
                ],
            }
            for r in rows
        ],
    }


# --- running it ---------------------------------------------------------------------


async def run_all(
    runner,
    chosen: list[Scenario],
    *,
    repeats: int,
    concurrency: int,
    on_done=None,
) -> list[ScenarioRun]:
    """Every chosen scenario `repeats` times, `concurrency` at a time. The
    baseline runs alongside the first repeat only."""
    gate = asyncio.Semaphore(concurrency)

    async def one(scenario: Scenario, repeat: int) -> ScenarioRun:
        async with gate:
            run = await run_one(
                runner,
                scenario,
                answer=expected_answer,
                with_baseline=repeat == 1,
                repeat=repeat,
            )
        if on_done:
            on_done(run)
        return run

    return list(
        await asyncio.gather(
            *(one(s, rep) for s in chosen for rep in range(1, repeats + 1))
        )
    )


def verdict(rows: list[Row]) -> int:
    """The exit code."""
    if any(r.critical for r in rows):
        return 3
    return 0 if all(c.passed for c in criteria(rows)) else 1


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    ap.add_argument("--only", nargs="*", type=int, help="scenario numbers, default all")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--model", help="OpenRouter model, overrides OPENROUTER_MODEL")
    ap.add_argument(
        "--no-save",
        action="store_true",
        help="do not write results.md and results.json",
    )
    args = ap.parse_args(argv)

    state_dir = prepare_environment(args.model)
    from settings import get_settings

    settings = get_settings()
    if not settings.openrouter_api_key:
        print("OPENROUTER_API_KEY is not set (coa-api/.env).")
        return 2

    from controller.runs import open_runner
    from database import dispose_engine, init_engine

    chosen = [s for s in scenarios() if not args.only or s.n in args.only]
    model = settings.openrouter_model
    total = len(chosen) * args.repeats
    print(
        f"model {model}, {len(chosen)} scenarios x {args.repeats} runs, state {state_dir}"
    )
    prices = await fetch_prices(model)
    if prices is None:
        print("no price for this model: costs will show as n/a")

    done = 0

    def progress(run: ScenarioRun) -> None:
        nonlocal done
        done += 1
        status = (run.agent or {}).get("status", "-")
        flag = "ok" if run.ok else "MISS: " + "; ".join(run.problems)
        print(
            f"  [{done}/{total}] scenario {run.n} run {run.repeat}: {status} {flag} ({run.seconds:.1f} s)"
        )

    await init_engine()
    try:
        async with open_runner() as runner:
            batch = await run_all(
                runner,
                chosen,
                repeats=args.repeats,
                concurrency=args.concurrency,
                on_done=progress,
            )
    finally:
        await dispose_engine()

    rows, when = build_rows(batch), datetime.datetime.now()
    table = render(rows, prices, model, when)
    print("\n" + table)
    if not args.no_save:
        (RESULTS_DIR / "results.md").write_text(table, encoding="utf-8")
        (RESULTS_DIR / "results.json").write_text(
            json.dumps(to_json(rows, prices, model, when), indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"written to {RESULTS_DIR}/results.md and results.json")

    code = verdict(rows)
    if code == 3:
        print(
            "\n"
            + "!" * 70
            + "\nA SCENARIO THAT MUST FAIL WAS REPORTED AS PASS. Do not trust this build.\n"
            + "!" * 70
        )
    return code


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
