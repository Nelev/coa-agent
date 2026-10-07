import datetime
import json
import re

import httpx
import pytest

from dataset.eval import evaluate
from dataset.eval.evaluate import (
    Prices,
    build_rows,
    criteria,
    fetch_prices,
    render,
    run_all,
    to_json,
    verdict,
)
from dataset.eval.scoring import ScenarioRun, expected_rows, score_agent
from dataset.ground_truth import truth
from dataset.make_data import scenarios
from schema import Draft
from tests.helpers import call, head, ideal, ideal_8, runner_for
from tools import ai_tools

WHEN = datetime.datetime(2026, 10, 7, 12, 0)
PRICES = Prices(per_in=1e-6, per_out=2e-6)


@pytest.fixture
def stubbed(db, monkeypatch):
    """read_coa returns the ground truth of whichever scenario the PDF is a copy
    of (the run's PDF is named scenario<n>-r<repeat>); the draft is canned."""
    monkeypatch.setenv("REFERENCE_DATE", "2026-10-07")

    async def fake_read(path, *, model=None):
        return truth(scenarios()[int(re.match(r"scenario(\d)", path.stem)[1]) - 1])

    async def fake_draft(supplier, issue, evidence, *, model=None):
        return Draft(draft_id="d1", subject=issue, body=evidence)

    monkeypatch.setattr(ai_tools, "read_coa", fake_read)
    monkeypatch.setattr(ai_tools, "draft_supplier_request", fake_draft)


def full_script(repeats: int, skip_claim_in: tuple[int, int] | None = None):
    """The calls of a good agent for every scenario, in the order they run."""
    script = []
    for n in range(1, 9):
        for rep in range(1, repeats + 1):
            if n == 8:
                before, after = ideal_8()
                script += [*before, *after]
            elif (n, rep) == skip_claim_in:
                script += [*head(2), call("submit", summary="Assay is out of spec.")]
            else:
                script += ideal(n)
    return script


async def evaluate_batch(repeats=2, **script_args):
    runner = runner_for(full_script(repeats, **script_args))
    batch = await run_all(runner, scenarios(), repeats=repeats, concurrency=1)
    return build_rows(batch)


# --- a whole evaluation with a scripted agent ------------------------------------


async def test_a_good_agent_meets_every_criterion(stubbed):
    rows = await evaluate_batch(repeats=2)

    assert [r.n for r in rows] == list(range(1, 9)) and all(
        len(r.runs) == 2 for r in rows
    )
    assert all(c.passed for c in criteria(rows)), [
        c for c in criteria(rows) if not c.passed
    ]
    assert verdict(rows) == 0
    assert all(r.stable and r.ok_runs == 2 for r in rows)
    # The baseline ran once per scenario, on the first repeat, and gets 6 of 8.
    assert [bool(r.baseline) for r in rows] == [True] * 8
    assert sum(r.baseline_correct for r in rows) == 6
    assert [r.baseline["status"] for r in rows][1] == "FAIL" and rows[7].baseline[
        "status"
    ] == "ERROR"
    assert len([x for r in rows for x in r.runs if x.baseline]) == 8


async def test_the_clean_coa_takes_six_calls_and_scenario_8_asks(stubbed):
    rows = {r.n: r for r in await evaluate_batch(repeats=2)}
    assert rows[1].calls == [6, 6]
    assert all(any(s.tool == "ask_user" for s in x.steps) for x in rows[8].runs)


async def test_the_table_has_a_row_per_scenario_and_the_criteria(stubbed):
    rows = await evaluate_batch(repeats=2)
    text = render(rows, PRICES, "openai/gpt-4.1-mini", WHEN)

    assert "Model `openai/gpt-4.1-mini` · 2026-10-07 12:00 · 2 agent runs" in text
    assert len(re.findall(r"^\| [1-8] \|", text, re.M)) == 8
    assert (
        "| 2 | Assay printed 9.85 % instead of 98.5 % | REVIEW | REVIEW (2/2) | yes | FAIL ✗ |"
        in text
    )
    assert "| 6 | " in text and "PASS · Correct final status on the 8 scenarios" in text
    assert "agent 8 of 8 in every run; baseline 6 of 8" in text
    assert "Same outcome over 2 repeated runs: 8 of 8 scenarios stable" in text
    assert "$0." in text and "Where runs missed" not in text


async def test_tokens_cost_and_time_come_from_the_trace(stubbed):
    rows = {r.n: r for r in await evaluate_batch(repeats=1)}
    one = rows[1].runs[0]
    # six calls, each with the fake model's 100 in and 20 out
    assert (
        sum(s.tokens_in for s in one.steps),
        sum(s.tokens_out for s in one.steps),
    ) == (600, 120)
    assert evaluate.mean_cost([one], PRICES) == pytest.approx(600e-6 + 120 * 2e-6)
    assert one.seconds > 0 and one.baseline_seconds >= 0
    data = to_json(list(rows.values()), PRICES, "m", WHEN)
    first = data["scenarios"][0]
    assert first["runs"][0]["tokens"] == (600, 120)
    assert first["runs"][0]["cost"] == pytest.approx(0.000840)
    json.dumps(data)  # it must serialise


# --- when it goes wrong -----------------------------------------------------------


async def test_a_run_that_differs_makes_the_scenario_unstable_and_the_table_say_so(
    stubbed,
):
    rows = await evaluate_batch(repeats=2, skip_claim_in=(2, 2))
    two = rows[1]
    assert not two.stable and two.ok_runs == 1  # only run 2 skipped the claim
    unmet = {c.name for c in criteria(rows) if not c.passed}
    assert any(name.startswith("Same outcome") for name in unmet)
    assert verdict(rows) == 1
    text = render(rows, PRICES, "m", WHEN)
    assert "| 2 | " in text and "| NO |" in text and "Where runs missed" in text
    assert "scenario 2, run 2: status FAIL, expected REVIEW" in text


def test_a_fail_scenario_reported_as_pass_is_the_loudest_verdict():
    scenario = scenarios()[4]
    expected = expected_rows()[scenario.file]
    agent = {"status": "PASS", "findings": [], "summary": "fine"}
    run = ScenarioRun(5, scenario.file, agent=agent)
    run.problems = score_agent(expected, agent, [])
    rows = build_rows([run])
    assert rows[0].critical and verdict(rows) == 3


async def test_a_subset_is_judged_only_on_what_ran(stubbed):
    runner = runner_for([*ideal(1), *ideal(1)])
    batch = await run_all(runner, scenarios()[:1], repeats=2, concurrency=1)
    rows = build_rows(batch)
    assert len(rows) == 1
    found = {c.name: c for c in criteria(rows)}
    assert found["Correct final status on the 1 scenarios"].passed
    # Nothing was run for 2, 3, 4, 7 or 8: they are reported as not run, and
    # do not count against the verdict.
    cause = found["Cause explained, not just the failure (2, 3, 4)"]
    assert cause.passed and cause.detail == "not run"
    assert verdict(rows) == 0


# --- prices ------------------------------------------------------------------------

LISTING = {
    "data": [
        {"id": "x/other", "pricing": {"prompt": "0.001", "completion": "0.002"}},
        {
            "id": "openai/gpt-4.1-mini",
            "pricing": {"prompt": "0.0000004", "completion": "0.0000016"},
        },
    ]
}


def client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_price_comes_from_the_model_list(monkeypatch):
    monkeypatch.delenv("PRICE_PER_MTOK_IN", raising=False)
    prices = await fetch_prices(
        "openai/gpt-4.1-mini", client(lambda r: httpx.Response(200, json=LISTING))
    )
    assert prices == Prices(per_in=4e-7, per_out=1.6e-6)
    assert prices.cost(1_000_000, 1_000_000) == pytest.approx(2.0)


async def test_the_environment_overrides_the_list(monkeypatch):
    monkeypatch.setenv("PRICE_PER_MTOK_IN", "2")
    monkeypatch.setenv("PRICE_PER_MTOK_OUT", "8")

    def never(request):
        raise AssertionError("the list should not be asked")

    assert await fetch_prices("anything", client(never)) == Prices(2e-6, 8e-6)


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(500),
        lambda r: httpx.Response(200, json={"data": []}),
        lambda r: httpx.Response(200, json={"nope": 1}),
        lambda r: (_ for _ in ()).throw(httpx.ConnectError("down")),
    ],
)
async def test_no_price_is_none_not_a_crash(monkeypatch, handler):
    monkeypatch.delenv("PRICE_PER_MTOK_IN", raising=False)
    assert await fetch_prices("openai/gpt-4.1-mini", client(handler)) is None


async def test_the_table_still_renders_without_a_price(stubbed):
    rows = await evaluate_batch(repeats=1)
    text = render(rows, None, "m", WHEN)
    assert "n/a" in text and "$" not in text.split("## Success criteria")[0]


async def test_without_a_key_it_says_so_and_exits_2(monkeypatch, capsys):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert await evaluate.main(["--no-save"]) == 2
    assert "OPENROUTER_API_KEY is not set" in capsys.readouterr().out
