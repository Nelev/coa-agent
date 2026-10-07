"""C11: runs every scenario through the agent 3 times and the baseline once,
compares with dataset/expected.csv and prints the score table.

Run from coa-api:  uv run python -m dataset.eval.evaluate   (billable)

Reports correct status (agent, baseline), stability over 3 runs, tool calls,
tokens, cost and time per run. Exits non-zero if any FAIL scenario is reported
as PASS.
"""
