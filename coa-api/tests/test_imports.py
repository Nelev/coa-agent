"""Importing any module must not need credentials or a database: CI has neither."""

import importlib

import pytest

MODULES = [
    "main",
    "baseline",
    "tracing",
    "controller.runs",
    "agent.orchestrator",
    "agent.registry",
    "agent.prompt",
    "agent.state",
    "agent.guard",
    "agent.callbacks",
    "tools.ai_tools",
    "tools.code_tools",
    "tools.rules",
    "tools.data",
    "tools.llm",
    "dataset.ground_truth",
    "dataset.eval.check_extraction",
    "dataset.make_data",
    "dataset.eval.evaluate",
]


@pytest.mark.parametrize("name", MODULES)
def test_module_imports_without_credentials(name):
    importlib.import_module(name)
