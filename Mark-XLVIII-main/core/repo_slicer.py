"""Deterministic semantic slicing of source code into structured units.

Extracted and cleaned from the DAG Engine's `semantic_slicer_AG.py` (Jake's
knowledge-compiler pipeline). Purpose: turn a repository into structured,
deduplicated code *slices* — one per function/method/class — carrying the
signal a model needs to reason about a codebase, instead of raw whole-file text.

This is Stage 1 of the repo-pattern pipeline and, on its own, a large upgrade to
`project_learning`: the learning assessment on 2026-07-23 failed its synthesis
partly because the model was fed crudely-selected raw files. Structured slices —
with real signatures, call graphs, docstrings, and complexity — are a far better
input, and they dedupe identical code so the model's budget isn't wasted.

Pure standard-library `ast`; no external services, no heavy deps. Non-Python and
malformed sources degrade to empty rather than raising.
"""

from __future__ import annotations

import ast
import hashlib
from typing import Any


def _short_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:16]


def _arg_repr(arg: ast.arg, default: ast.AST | None) -> str:
    text = arg.arg
    if arg.annotation is not None:
        text += f": {_annotation(arg.annotation)}"
    if default is not None:
        text += f" = {_annotation(default)}"
    return text


def _annotation(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return getattr(node, "id", "") or "?"


def _signature(node: ast.AST) -> dict[str, Any]:
    args_node = getattr(node, "args", None)
    if args_node is None:
        return {"args": [], "returns": None}
    positional = list(getattr(args_node, "posonlyargs", [])) + list(args_node.args)
    defaults = list(args_node.defaults)
    pad = [None] * (len(positional) - len(defaults)) + defaults
    rendered = [_arg_repr(arg, default) for arg, default in zip(positional, pad)]
    if args_node.vararg:
        rendered.append(f"*{args_node.vararg.arg}")
    for kwarg, default in zip(args_node.kwonlyargs, args_node.kw_defaults):
        rendered.append(_arg_repr(kwarg, default))
    if args_node.kwarg:
        rendered.append(f"**{args_node.kwarg.arg}")
    returns = _annotation(getattr(node, "returns", None)) or None
    return {"args": rendered, "returns": returns}


class _CallCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name):
            self.calls.add(func.id)
        elif isinstance(func, ast.Attribute):
            self.calls.add(func.attr)
        self.generic_visit(node)


_BRANCH_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With,
                 ast.AsyncWith, ast.BoolOp, ast.IfExp, ast.comprehension)


def _complexity(node: ast.AST) -> int:
    """A cheap cyclomatic-ish score: 1 + count of branch/loop constructs."""
    return 1 + sum(1 for child in ast.walk(node) if isinstance(child, _BRANCH_NODES))


def _slice_for(node: ast.AST, source_lines: list[str], filename: str, parent: str) -> dict[str, Any]:
    name = getattr(node, "name", "<anonymous>")
    qualname = f"{parent}.{name}" if parent else name
    start = int(getattr(node, "lineno", 1))
    end = int(getattr(node, "end_lineno", start))
    code = "\n".join(source_lines[max(0, start - 1):end]).rstrip()
    if isinstance(node, ast.ClassDef):
        kind = "class"
    elif isinstance(node, ast.AsyncFunctionDef):
        kind = "async_function"
    elif parent:
        kind = "method"
    else:
        kind = "function"
    collector = _CallCollector()
    collector.visit(node)
    decorators = [_annotation(d) for d in getattr(node, "decorator_list", [])]
    doc = ast.get_docstring(node) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else None
    return {
        "slice_id": f"{filename}::{qualname}@{start}-{end}",
        "content_id": _short_hash("\n".join(line.strip() for line in code.splitlines())),
        "kind": kind,
        "name": name,
        "qualname": qualname,
        "file": filename,
        "start_line": start,
        "end_line": end,
        "signature": _signature(node),
        "decorators": decorators,
        "calls": sorted(collector.calls),
        "docstring": (doc.strip().splitlines()[0].strip() if doc else ""),
        "complexity": _complexity(node),
        "code": code,
        "seen_in": [filename],
    }


def slice_python_source(source: str, filename: str) -> list[dict[str, Any]]:
    """Slice one Python source string into structured units. Never raises."""
    try:
        tree = ast.parse(source or "")
    except (SyntaxError, ValueError):
        return []
    source_lines = source.splitlines()
    slices: list[dict[str, Any]] = []

    def walk(node: ast.AST, parent: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                slices.append(_slice_for(child, source_lines, filename, parent))
                child_parent = f"{parent}.{child.name}" if parent else child.name
                if isinstance(child, ast.ClassDef):
                    walk(child, child_parent)
            # do not descend into function bodies for nested-def slicing (kept flat)

    walk(tree, "")
    return slices


def module_summary(source: str, filename: str) -> dict[str, Any]:
    """Module-level facts: imports and top-level symbol names."""
    try:
        tree = ast.parse(source or "")
    except (SyntaxError, ValueError):
        return {"file": filename, "imports": [], "symbols": []}
    imports: set[str] = set()
    symbols: list[str] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.update(f"{module}.{alias.name}" if module else alias.name for alias in node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append(node.name)
    return {"file": filename, "imports": sorted(imports), "symbols": symbols}


def dedupe_slices(slices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse slices with identical normalised code, recording every file seen."""
    by_content: dict[str, dict[str, Any]] = {}
    for item in slices:
        key = item["content_id"]
        if key in by_content:
            existing = by_content[key]
            for f in item["seen_in"]:
                if f not in existing["seen_in"]:
                    existing["seen_in"].append(f)
        else:
            by_content[key] = dict(item, seen_in=list(item["seen_in"]))
    return list(by_content.values())


def render_slices(
    slices: list[dict[str, Any]],
    *,
    max_chars: int = 6000,
    cite: bool = True,
    symbol_degree: dict[tuple[str, str], int] | None = None,
) -> str:
    """Render slices as compact, code-bearing model-input text within a char budget.

    Ranked by real cross-file usage first, then complexity: a function with many
    callers elsewhere in the codebase outranks a complex-but-unused private
    helper, and among equally-(un)used slices the higher-complexity one still
    goes first so a truncated budget keeps the most informative units. Slices
    that no longer fit degrade to a signature-only line.

    ``symbol_degree`` (optional): a ``{(file, name): cross_file_caller_count}``
    map, typically built from a pre-built graphify knowledge graph
    (``project_learning._graphify_symbol_degree``). Omit it (default) for
    byte-identical behaviour to before this signal existed -- every slice's
    degree defaults to 0 and the ranking collapses back to complexity-only.

    ``cite=True`` (default) keeps the ``[file:path]`` prefix so the standalone
    citation convention and clickable-link rendering both still work. Set
    ``cite=False`` when the caller supplies its own file provenance (e.g. the
    ``project_learning`` batch wrapper, whose ``_defuse_source_text`` step would
    otherwise strip the ``[file:`` token out of the source body).
    """
    degree = symbol_degree or {}
    ranked = sorted(
        slices,
        key=lambda s: (-degree.get((s["file"], s["name"]), 0), -s["complexity"], s["file"], s["start_line"]),
    )
    parts: list[str] = []
    used = 0
    for item in ranked:
        sig = item["signature"]
        prefix = f"[file:{item['file']}] " if cite else ""
        header = f"{prefix}{item['kind']} {item['qualname']}({', '.join(sig['args'])})"
        if sig["returns"]:
            header += f" -> {sig['returns']}"
        if len(item["seen_in"]) > 1:
            header += f"  (also in: {', '.join(item['seen_in'][1:4])})"
        block = f"{header}\n{item['code']}"
        if used + len(block) + 2 > max_chars:
            # Fall back to a signature-only line so the slice is still mapped.
            if used + len(header) + 2 <= max_chars:
                parts.append(header)
                used += len(header) + 2
            continue
        parts.append(block)
        used += len(block) + 2
    return "\n\n".join(parts)
