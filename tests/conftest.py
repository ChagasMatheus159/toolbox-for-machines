"""Pytest configuration for Toolbox E2E tests."""

import os
import httpx
import pytest


def pytest_addoption(parser):
    """Add custom CLI options."""
    parser.addoption(
        "--run-llm",
        action="store_true",
        default=False,
        help="Run LLM-dependent tests (describe, summarize, extract)",
    )
    parser.addoption(
        "--toolbox-url",
        default=os.environ.get("TOOLBOX_URL", "http://localhost:9600"),
        help="Toolbox API base URL",
    )


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "llm: marks tests that require a working LLM backend")


def pytest_collection_modifyitems(config, items):
    """Skip LLM tests unless --run-llm is passed."""
    if config.getoption("--run-llm"):
        return
    skip_llm = pytest.mark.skip(reason="Need --run-llm option to run")
    for item in items:
        if "llm" in item.keywords:
            item.add_marker(skip_llm)
