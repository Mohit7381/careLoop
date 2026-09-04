"""Every module must at least import.

Added after a syntax error sat in app/pipeline/runner.py through a full green
suite: 148 tests passed because nothing imported the runner or the API routes —
they are only exercised by the live server. A broken import is the cheapest
possible bug to catch and was costing a real debugging session instead.
"""
import importlib
import pkgutil

import pytest

import app

MODULES = sorted(
    m.name for m in pkgutil.walk_packages(app.__path__, prefix="app.")
    if not m.ispkg
)


def test_there_are_modules_to_check():
    assert len(MODULES) > 15, MODULES


@pytest.mark.parametrize("module", MODULES)
def test_module_imports(module):
    importlib.import_module(module)
