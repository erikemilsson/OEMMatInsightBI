"""Shared notebook-function extractor for the parity harness.

The Fabric notebooks are valid Python (markdown cells are `# MARKDOWN` comments),
so each can be parsed with `ast` and only the requested top-level FunctionDef nodes
compiled into a shared namespace. This keeps the parity check bound to the *live*
notebook text — if someone edits the notebook's key logic, these tests fail on the
next run, which is the whole point of the reference-implementation contract (root
CLAUDE.md "Testable transforms"; task-032).

Supersedes the per-file copies that previously lived in test_key_generation,
test_procurement_dates, and test_watermark. The `notebook_path`-parametrized shape
is canonical; the old hardcoded-path variants are migrated to pass the path
explicitly so a single definition serves bronze, gold, and any future notebook.
"""

import ast
from pathlib import Path

from pyspark.sql import functions as F

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLD_NOTEBOOK = REPO_ROOT / "fabric" / "silver-to-gold2.Notebook" / "notebook-content.py"
BRONZE_NOTEBOOK = REPO_ROOT / "fabric" / "bronze_to_silver.Notebook" / "notebook-content.py"


def load_notebook_functions(notebook_path, names, extra_globals=None):
    """Extract named top-level functions from a Fabric notebook's source.

    Args:
        notebook_path: Path to the notebook's notebook-content.py.
        names: Function names to extract, in dependency order (a function that
            calls another must come after it).
        extra_globals: Optional module-level names the extracted functions read
            from the notebook's global scope (e.g. LOG_UNMAPPED / FAIL_ON_UNMAPPED
            config flags, or DATE_SWAP_EPOCH). Only the FunctionDefs are compiled,
            so any notebook-global the function reads must be injected here.

    Returns:
        dict[str, callable]: the extracted functions, sharing one namespace so
        inter-function calls resolve to the notebook's own definitions.
    """
    assert notebook_path.exists(), f"Notebook not found: {notebook_path}"

    tree = ast.parse(notebook_path.read_text(encoding="utf-8"), filename=str(notebook_path))
    found = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in set(names)
    }

    missing = [n for n in names if n not in found]
    assert not missing, (
        f"Notebook {notebook_path.name} no longer defines {missing} at top level — "
        f"the parity harness cannot verify src/ against production. Update the "
        f"harness (or restore the notebook definitions) rather than deleting this test."
    )

    module = ast.Module(body=[found[n] for n in names], type_ignores=[])
    ast.fix_missing_locations(module)

    namespace = {"F": F}
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(module, str(notebook_path), "exec"), namespace)  # noqa: S102

    return {n: namespace[n] for n in names}